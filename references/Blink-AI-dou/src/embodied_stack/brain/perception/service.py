from __future__ import annotations

import base64
import io
import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Any, Callable, Protocol

import httpx
from PIL import Image

from embodied_stack.brain.memory import MemoryStore
from embodied_stack.brain.perception.semantic_refresh import SemanticRefreshPolicy
from embodied_stack.config import Settings, get_settings
from embodied_stack.multimodal.normalization import normalize_snapshot_content
from embodied_stack.observability import log_event
from embodied_stack.shared.models import (
    CommandBatch,
    LatencyBreakdownRecord,
    PerceptionAnnotationInput,
    PerceptionConfidence,
    PerceptionEventRecord,
    PerceptionEventType,
    PerceptionFixtureCatalogResponse,
    PerceptionFixtureDefinition,
    PerceptionHistoryResponse,
    PerceptionObservation,
    PerceptionObservationType,
    PerceptionProviderMode,
    PerceptionPublishedResult,
    PerceptionReplayRequest,
    PerceptionReplayResult,
    PerceptionTier,
    SceneClaimKind,
    SemanticQualityClass,
    PerceptionSnapshotRecord,
    PerceptionSnapshotStatus,
    PerceptionSnapshotSubmitRequest,
    PerceptionSourceFrame,
    PerceptionSubmissionResult,
    RobotEvent,
    utc_now,
)

logger = logging.getLogger(__name__)


class PerceptionProviderError(RuntimeError):
    pass


_OLLAMA_VISION_MAX_DIMENSION_PX = 512
_JSON_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE | re.DOTALL)
_SANITIZE_FRAME_NAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


class PerceptionProvider(Protocol):
    mode: PerceptionProviderMode

    def analyze_snapshot(self, request: PerceptionSnapshotSubmitRequest) -> PerceptionSnapshotRecord:
        ...


class StubPerceptionProvider:
    mode = PerceptionProviderMode.STUB

    def analyze_snapshot(self, request: PerceptionSnapshotSubmitRequest) -> PerceptionSnapshotRecord:
        source_frame = build_source_frame(request, source_kind="stub")
        summary = "Perception is running in stub mode. Situational awareness is limited."
        return PerceptionSnapshotRecord(
            session_id=request.session_id,
            provider_mode=self.mode,
            source=request.source,
            status=PerceptionSnapshotStatus.DEGRADED,
            limited_awareness=True,
            message="stub_perception_mode",
            scene_summary=summary,
            source_frame=source_frame,
            observations=[
                PerceptionObservation(
                    observation_type=PerceptionObservationType.SCENE_SUMMARY,
                    text_value=summary,
                    confidence=confidence_from_score(0.18),
                    source_frame=source_frame,
                    metadata={"reason": "stub_mode"},
                )
            ],
        )


class ManualAnnotationsPerceptionProvider:
    mode = PerceptionProviderMode.MANUAL_ANNOTATIONS

    def analyze_snapshot(self, request: PerceptionSnapshotSubmitRequest) -> PerceptionSnapshotRecord:
        source_frame = build_source_frame(request, source_kind="manual_annotations")
        if not request.annotations:
            summary = "No manual annotations were provided. Situational awareness is limited."
            return PerceptionSnapshotRecord(
                session_id=request.session_id,
                provider_mode=self.mode,
                source=request.source,
                status=PerceptionSnapshotStatus.DEGRADED,
                limited_awareness=True,
                message="manual_annotations_missing",
                scene_summary=summary,
                source_frame=source_frame,
                observations=[
                    PerceptionObservation(
                        observation_type=PerceptionObservationType.SCENE_SUMMARY,
                        text_value=summary,
                        confidence=confidence_from_score(0.2),
                        source_frame=source_frame,
                        metadata={"reason": "missing_annotations"},
                    )
                ],
            )

        observations = [observation_from_annotation(item, source_frame=source_frame) for item in request.annotations]
        observations = normalize_manual_observations(observations, source_frame=source_frame)
        scene_summary = extract_scene_summary(observations) or summarize_observations(observations)
        if scene_summary and extract_scene_summary(observations) is None:
            observations.append(
                PerceptionObservation(
                    observation_type=PerceptionObservationType.SCENE_SUMMARY,
                    text_value=scene_summary,
                    confidence=confidence_from_score(average_confidence(observations)),
                    source_frame=source_frame,
                    metadata={"generated": True},
                )
            )

        return PerceptionSnapshotRecord(
            session_id=request.session_id,
            provider_mode=self.mode,
            source=request.source,
            status=PerceptionSnapshotStatus.OK,
            limited_awareness=False,
            message="manual_annotations_processed",
            scene_summary=scene_summary,
            source_frame=source_frame,
            observations=observations,
        )


class NativeCameraSnapshotPerceptionProvider:
    mode = PerceptionProviderMode.NATIVE_CAMERA_SNAPSHOT

    def analyze_snapshot(self, request: PerceptionSnapshotSubmitRequest) -> PerceptionSnapshotRecord:
        if not request.image_data_url:
            raise PerceptionProviderError("native_camera_snapshot_missing_image")

        source_frame = build_source_frame(request, source_kind="native_camera_snapshot")
        source_frame.mime_type = source_frame.mime_type or mime_type_from_data_url(request.image_data_url)
        summary = (
            "Native webcam snapshot captured successfully, but native_camera_snapshot mode does not perform semantic scene analysis. "
            "Situational awareness remains limited until manual annotations, fixture replay, or a multimodal provider is used."
        )
        return PerceptionSnapshotRecord(
            session_id=request.session_id,
            provider_mode=self.mode,
            source=request.source,
            status=PerceptionSnapshotStatus.DEGRADED,
            limited_awareness=True,
            message="native_snapshot_captured_without_semantic_analysis",
            scene_summary=summary,
            source_frame=source_frame,
            observations=[
                PerceptionObservation(
                    observation_type=PerceptionObservationType.SCENE_SUMMARY,
                    text_value=summary,
                    confidence=confidence_from_score(0.24),
                    source_frame=source_frame,
                    metadata={"image_present": True},
                )
            ],
        )


class BrowserSnapshotPerceptionProvider:
    mode = PerceptionProviderMode.BROWSER_SNAPSHOT

    def analyze_snapshot(self, request: PerceptionSnapshotSubmitRequest) -> PerceptionSnapshotRecord:
        if not request.image_data_url:
            raise PerceptionProviderError("browser_snapshot_missing_image")

        source_frame = build_source_frame(request, source_kind="browser_snapshot")
        source_frame.mime_type = source_frame.mime_type or mime_type_from_data_url(request.image_data_url)
        summary = (
            "Browser snapshot captured successfully, but browser_snapshot mode does not perform semantic scene analysis. "
            "Situational awareness remains limited until manual annotations, fixture replay, or a multimodal provider is used."
        )
        return PerceptionSnapshotRecord(
            session_id=request.session_id,
            provider_mode=self.mode,
            source=request.source,
            status=PerceptionSnapshotStatus.DEGRADED,
            limited_awareness=True,
            message="snapshot_captured_without_semantic_analysis",
            scene_summary=summary,
            source_frame=source_frame,
            observations=[
                PerceptionObservation(
                    observation_type=PerceptionObservationType.SCENE_SUMMARY,
                    text_value=summary,
                    confidence=confidence_from_score(0.24),
                    source_frame=source_frame,
                    metadata={"image_present": True},
                )
            ],
        )


class MultimodalLLMPerceptionProvider:
    mode = PerceptionProviderMode.MULTIMODAL_LLM

    def __init__(
        self,
        *,
        api_key: str | None,
        base_url: str,
        model: str,
        timeout_seconds: float,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.transport = transport

    def analyze_snapshot(self, request: PerceptionSnapshotSubmitRequest) -> PerceptionSnapshotRecord:
        if not request.image_data_url:
            raise PerceptionProviderError("multimodal_llm_missing_image")
        if not self.api_key:
            raise PerceptionProviderError("multimodal_llm_api_key_missing")
        if not self.base_url:
            raise PerceptionProviderError("multimodal_llm_base_url_missing")
        if not self.model:
            raise PerceptionProviderError("multimodal_llm_model_missing")

        source_frame = build_source_frame(request, source_kind="multimodal_llm")
        source_frame.mime_type = source_frame.mime_type or mime_type_from_data_url(request.image_data_url)

        payload = {
            "model": self.model,
            "stream": False,
            "temperature": 0.1,
            "messages": [
                {
                    "role": "system",
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                "You analyze one camera frame for Blink-AI, a local-first companion system with optional embodiment. "
                                "Return JSON only. Do not identify people. Do not claim face recognition, venue facts, or capabilities not visible in the frame. "
                                "If the frame is unclear, set limited_awareness=true and keep confidence low."
                            ),
                        }
                    ],
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                "Return JSON with keys: scene_summary, limited_awareness, message, observations. "
                                "Each observation must include observation_type, text_value, number_value, bool_value, confidence, and metadata. "
                                "Allowed observation_type values: person_visibility, people_count, engagement_estimate, visible_text, named_object, location_anchor, scene_summary."
                            ),
                        },
                        {
                            "type": "image_url",
                            "image_url": {"url": request.image_data_url},
                        },
                    ],
                },
            ],
        }

        try:
            with httpx.Client(timeout=self.timeout_seconds, transport=self.transport) as client:
                response = client.post(
                    chat_completions_url(self.base_url),
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                        "Accept": "application/json",
                    },
                    json=payload,
                )
                response.raise_for_status()
                body = response.json()
        except httpx.TimeoutException as exc:
            raise PerceptionProviderError("multimodal_llm_timeout") from exc
        except httpx.HTTPError as exc:
            raise PerceptionProviderError(f"multimodal_llm_transport_error:{exc}") from exc
        except ValueError as exc:
            raise PerceptionProviderError("multimodal_llm_invalid_json") from exc

        content = extract_chat_completion_text(body)
        if not content:
            raise PerceptionProviderError("multimodal_llm_empty_response")

        try:
            parsed = json.loads(content)
        except ValueError as exc:
            raise PerceptionProviderError("multimodal_llm_non_json_response") from exc

        observations = parse_multimodal_observations(parsed.get("observations"), source_frame=source_frame)
        scene_summary = parsed.get("scene_summary") if isinstance(parsed.get("scene_summary"), str) else None
        limited_awareness = bool(parsed.get("limited_awareness", False))
        message = parsed.get("message") if isinstance(parsed.get("message"), str) else "multimodal_llm_processed"

        if scene_summary:
            observations.append(
                PerceptionObservation(
                    observation_type=PerceptionObservationType.SCENE_SUMMARY,
                    text_value=scene_summary,
                    confidence=confidence_from_score(average_confidence(observations) or 0.55),
                    source_frame=source_frame,
                    metadata={"generated": False},
                )
            )

        if not observations:
            raise PerceptionProviderError("multimodal_llm_no_observations")

        return PerceptionSnapshotRecord(
            session_id=request.session_id,
            provider_mode=self.mode,
            source=request.source,
            status=PerceptionSnapshotStatus.DEGRADED if limited_awareness else PerceptionSnapshotStatus.OK,
            limited_awareness=limited_awareness,
            message=message,
            scene_summary=scene_summary,
            source_frame=source_frame,
            observations=observations,
        )


class OllamaVisionPerceptionProvider:
    mode = PerceptionProviderMode.OLLAMA_VISION

    def __init__(
        self,
        *,
        base_url: str,
        model: str | None,
        timeout_seconds: float,
        transport: httpx.BaseTransport | None = None,
        keep_alive: str | None = None,
        success_reporter: Callable[[str, float], None] | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.transport = transport
        self.keep_alive = keep_alive
        self.success_reporter = success_reporter

    def analyze_snapshot(self, request: PerceptionSnapshotSubmitRequest) -> PerceptionSnapshotRecord:
        if not request.image_data_url:
            raise PerceptionProviderError("ollama_vision_missing_image")
        if not self.base_url:
            raise PerceptionProviderError("ollama_vision_base_url_missing")
        if not self.model:
            raise PerceptionProviderError("ollama_vision_model_missing")

        source_frame = build_source_frame(request, source_kind="ollama_vision")
        try:
            prepared_image = prepare_semantic_vision_image(request.image_data_url)
        except Exception as exc:  # pragma: no cover - defensive normalization around local image decode failures
            raise PerceptionProviderError("ollama_vision_invalid_image") from exc
        source_frame.mime_type = source_frame.mime_type or prepared_image.mime_type
        if source_frame.width_px is None:
            source_frame.width_px = prepared_image.original_width_px
        if source_frame.height_px is None:
            source_frame.height_px = prepared_image.original_height_px

        payload = {
            "model": self.model,
            "stream": False,
            "keep_alive": self.keep_alive,
            "think": False,
            "format": "json",
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You analyze one camera frame for Blink-AI, a local-first companion system with optional embodiment. "
                        "Return one JSON object only, with no markdown fences. Do not identify people. "
                        "Do not claim face recognition, venue facts, or hidden capabilities. "
                        "If the frame is unclear, set limited_awareness to true and keep confidence low. "
                        "When lighting is poor, prefer coarse facts like people count, approximate position, and whether someone appears seated or focused on something below the camera. "
                        "Only mention clothing, glasses, or finer visual details if they are directly clear in the frame."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        "Return JSON with keys scene_summary, limited_awareness, message, and observations. "
                        "observations must be a JSON array of objects. "
                        "Each observation object may include observation_type, text_value, number_value, bool_value, confidence, and metadata. "
                        "Allowed observation_type values are person_visibility, people_count, engagement_estimate, visible_text, named_object, location_anchor, and scene_summary. "
                        "Use bool_value for person_visibility, number_value for people_count, and text_value for visible_text, named_object, location_anchor, and engagement_estimate. "
                        "Prefer 3 to 6 grounded observations. If details are unclear, still return a careful scene_summary."
                    ),
                    "images": [prepared_image.base64_payload],
                },
            ],
        }

        try:
            start = perf_counter()
            with httpx.Client(timeout=self.timeout_seconds, transport=self.transport) as client:
                response = client.post(
                    f"{self.base_url}/api/chat",
                    json=payload,
                )
                response.raise_for_status()
                body = response.json()
        except httpx.TimeoutException as exc:
            raise PerceptionProviderError("ollama_vision_timeout") from exc
        except httpx.HTTPError as exc:
            raise PerceptionProviderError(f"ollama_vision_transport_error:{exc}") from exc
        except ValueError as exc:
            raise PerceptionProviderError("ollama_vision_invalid_json") from exc

        content = extract_ollama_chat_text(body)
        if not content:
            raise PerceptionProviderError("ollama_vision_empty_response")

        try:
            parsed = json.loads(extract_json_object_text(content))
        except ValueError as exc:
            raise PerceptionProviderError("ollama_vision_non_json_response") from exc

        if not isinstance(parsed, dict):
            raise PerceptionProviderError("ollama_vision_non_object_response")
        observations = parse_ollama_vision_observations(parsed.get("observations"), source_frame=source_frame)
        scene_summary = parsed.get("scene_summary") if isinstance(parsed.get("scene_summary"), str) else None
        limited_awareness = coerce_boolean_value(parsed.get("limited_awareness"))
        message = parsed.get("message") if isinstance(parsed.get("message"), str) else "ollama_vision_processed"
        if scene_summary:
            observations.append(
                PerceptionObservation(
                    observation_type=PerceptionObservationType.SCENE_SUMMARY,
                    text_value=scene_summary,
                    confidence=confidence_from_score(average_confidence(observations) or 0.5),
                    source_frame=source_frame,
                    metadata={"generated": False},
                )
            )
        if not observations and scene_summary:
            limited_awareness = True
            observations.append(
                PerceptionObservation(
                    observation_type=PerceptionObservationType.SCENE_SUMMARY,
                    text_value=scene_summary,
                    confidence=confidence_from_score(0.35),
                    source_frame=source_frame,
                    metadata={"generated": True, "fallback": "scene_summary_only"},
                )
            )
        if not observations:
            raise PerceptionProviderError("ollama_vision_no_observations")
        if self.success_reporter is not None:
            self.success_reporter(self.model, round((perf_counter() - start) * 1000.0, 2))

        return PerceptionSnapshotRecord(
            session_id=request.session_id,
            provider_mode=self.mode,
            source=request.source,
            status=PerceptionSnapshotStatus.DEGRADED if limited_awareness else PerceptionSnapshotStatus.OK,
            limited_awareness=limited_awareness,
            message=message,
            scene_summary=scene_summary,
            source_frame=source_frame,
            observations=observations,
        )


class VideoFileReplayPerceptionProvider:
    mode = PerceptionProviderMode.VIDEO_FILE_REPLAY

    def __init__(self, *, manual_provider: ManualAnnotationsPerceptionProvider) -> None:
        self.manual_provider = manual_provider

    def load_fixture(self, request: PerceptionReplayRequest) -> list[PerceptionSnapshotSubmitRequest]:
        fixture_path = Path(request.fixture_path)
        if not fixture_path.exists():
            raise PerceptionProviderError("video_fixture_not_found")

        try:
            payload = json.loads(fixture_path.read_text(encoding="utf-8"))
        except ValueError as exc:
            raise PerceptionProviderError("video_fixture_invalid_json") from exc

        frames = payload.get("frames")
        if not isinstance(frames, list) or not frames:
            raise PerceptionProviderError("video_fixture_missing_frames")

        requests: list[PerceptionSnapshotSubmitRequest] = []
        for index, frame in enumerate(frames):
            if not isinstance(frame, dict):
                continue
            source_frame = PerceptionSourceFrame(
                source_kind=str(frame.get("source_kind") or payload.get("source_kind") or "video_file_replay"),
                source_label=payload.get("title") if isinstance(payload.get("title"), str) else fixture_path.stem,
                frame_id=str(frame.get("frame_id") or f"frame-{index + 1:04d}"),
                fixture_path=str(fixture_path),
                clip_offset_ms=float(frame.get("clip_offset_ms")) if frame.get("clip_offset_ms") is not None else None,
                clip_duration_ms=float(frame.get("clip_duration_ms")) if frame.get("clip_duration_ms") is not None else None,
                file_name=fixture_path.name,
            )
            annotations = [
                PerceptionAnnotationInput.model_validate(item)
                for item in frame.get("annotations", [])
                if isinstance(item, dict)
            ]
            metadata: dict[str, Any] = {}
            if isinstance(frame.get("metadata"), dict):
                metadata.update(frame["metadata"])
            if isinstance(frame.get("scene_summary"), str):
                annotations.append(
                    PerceptionAnnotationInput(
                        observation_type=PerceptionObservationType.SCENE_SUMMARY,
                        text_value=frame["scene_summary"],
                        confidence=frame.get("summary_confidence") if isinstance(frame.get("summary_confidence"), (int, float)) else 0.72,
                        metadata={"generated": False},
                    )
                )
            requests.append(
                PerceptionSnapshotSubmitRequest(
                    session_id=request.session_id,
                    provider_mode=PerceptionProviderMode.MANUAL_ANNOTATIONS,
                    source=request.source,
                    source_frame=source_frame,
                    annotations=annotations,
                    metadata=metadata,
                    publish_events=request.publish_events,
                )
            )
        return requests


class PerceptionEventBus:
    def build_events(
        self,
        snapshot: PerceptionSnapshotRecord,
        previous_snapshot: PerceptionSnapshotRecord | None,
    ) -> list[PerceptionEventRecord]:
        events: list[PerceptionEventRecord] = []

        previous_people = integer_observation_value(previous_snapshot, PerceptionObservationType.PEOPLE_COUNT) if previous_snapshot else None
        current_people = integer_observation_value(snapshot, PerceptionObservationType.PEOPLE_COUNT)
        previous_visible = boolean_observation_value(previous_snapshot, PerceptionObservationType.PERSON_VISIBILITY) if previous_snapshot else None
        current_visible = boolean_observation_value(snapshot, PerceptionObservationType.PERSON_VISIBILITY)

        if current_visible is None and current_people is not None:
            current_visible = current_people > 0
        if previous_visible is None and previous_people is not None:
            previous_visible = previous_people > 0

        if current_visible is True and previous_visible is not True:
            events.append(
                event_from_observation(
                    snapshot=snapshot,
                    event_type=PerceptionEventType.PERSON_VISIBLE,
                    observation=find_first_observation(snapshot, PerceptionObservationType.PERSON_VISIBILITY)
                    or find_first_observation(snapshot, PerceptionObservationType.PEOPLE_COUNT),
                    payload={"people_count": current_people},
                )
            )
        if current_visible is False and previous_visible is True:
            events.append(
                event_from_observation(
                    snapshot=snapshot,
                    event_type=PerceptionEventType.PERSON_LEFT,
                    observation=find_first_observation(snapshot, PerceptionObservationType.PERSON_VISIBILITY),
                    payload={"people_count": current_people or 0},
                )
            )
        if current_people is not None and current_people != previous_people:
            events.append(
                event_from_observation(
                    snapshot=snapshot,
                    event_type=PerceptionEventType.PEOPLE_COUNT_CHANGED,
                    observation=find_first_observation(snapshot, PerceptionObservationType.PEOPLE_COUNT),
                    payload={
                        "people_count": current_people,
                        "previous_people_count": previous_people,
                    },
                )
            )

        previous_engagement = text_observation_value(previous_snapshot, PerceptionObservationType.ENGAGEMENT_ESTIMATE) if previous_snapshot else None
        current_engagement = text_observation_value(snapshot, PerceptionObservationType.ENGAGEMENT_ESTIMATE)
        if current_engagement and current_engagement != previous_engagement:
            events.append(
                event_from_observation(
                    snapshot=snapshot,
                    event_type=PerceptionEventType.ENGAGEMENT_ESTIMATE_CHANGED,
                    observation=find_first_observation(snapshot, PerceptionObservationType.ENGAGEMENT_ESTIMATE),
                    payload={
                        "engagement_estimate": current_engagement,
                        "previous_engagement_estimate": previous_engagement,
                    },
                )
            )

        for observation in filter_observations(snapshot, PerceptionObservationType.VISIBLE_TEXT):
            events.append(
                event_from_observation(
                    snapshot=snapshot,
                    event_type=PerceptionEventType.VISIBLE_TEXT_DETECTED,
                    observation=observation,
                    payload={"text": observation.text_value},
                )
            )
        for observation in filter_observations(snapshot, PerceptionObservationType.NAMED_OBJECT):
            events.append(
                event_from_observation(
                    snapshot=snapshot,
                    event_type=PerceptionEventType.NAMED_OBJECT_DETECTED,
                    observation=observation,
                    payload={"object_name": observation.text_value},
                )
            )
        for observation in filter_observations(snapshot, PerceptionObservationType.LOCATION_ANCHOR):
            events.append(
                event_from_observation(
                    snapshot=snapshot,
                    event_type=PerceptionEventType.LOCATION_ANCHOR_DETECTED,
                    observation=observation,
                    payload={"anchor_name": observation.text_value},
                )
            )
        for observation in filter_observations(snapshot, PerceptionObservationType.PARTICIPANT_ATTRIBUTE):
            if not observation.text_value or not observation.justification:
                continue
            events.append(
                event_from_observation(
                    snapshot=snapshot,
                    event_type=PerceptionEventType.PARTICIPANT_ATTRIBUTE_DETECTED,
                    observation=observation,
                    payload={
                        "attribute_text": observation.text_value,
                        "justification": observation.justification,
                    },
                )
            )

        previous_summary = previous_snapshot.scene_summary if previous_snapshot else None
        if snapshot.scene_summary and snapshot.scene_summary != previous_summary:
            events.append(
                event_from_observation(
                    snapshot=snapshot,
                    event_type=PerceptionEventType.SCENE_SUMMARY_UPDATED,
                    observation=find_first_observation(snapshot, PerceptionObservationType.SCENE_SUMMARY),
                    payload={"scene_summary": snapshot.scene_summary},
                )
            )

        return events


class PerceptionService:
    def __init__(
        self,
        *,
        settings: Settings | None = None,
        memory: MemoryStore,
        event_handler: Callable[[RobotEvent], CommandBatch] | None = None,
        providers: dict[PerceptionProviderMode, PerceptionProvider] | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.memory = memory
        self.event_handler = event_handler
        manual_provider = ManualAnnotationsPerceptionProvider()
        self.providers = providers or {
            PerceptionProviderMode.STUB: StubPerceptionProvider(),
            PerceptionProviderMode.MANUAL_ANNOTATIONS: manual_provider,
            PerceptionProviderMode.OLLAMA_VISION: OllamaVisionPerceptionProvider(
                base_url=self.settings.ollama_base_url,
                model=self.settings.ollama_vision_model or self.settings.ollama_model,
                timeout_seconds=self.settings.ollama_vision_timeout_seconds,
            ),
            PerceptionProviderMode.NATIVE_CAMERA_SNAPSHOT: NativeCameraSnapshotPerceptionProvider(),
            PerceptionProviderMode.BROWSER_SNAPSHOT: BrowserSnapshotPerceptionProvider(),
            PerceptionProviderMode.MULTIMODAL_LLM: MultimodalLLMPerceptionProvider(
                api_key=self.settings.perception_multimodal_api_key,
                base_url=self.settings.perception_multimodal_base_url,
                model=self.settings.perception_multimodal_model,
                timeout_seconds=self.settings.perception_multimodal_timeout_seconds,
            ),
        }
        self.fixture_provider = VideoFileReplayPerceptionProvider(manual_provider=manual_provider)
        self.event_bus = PerceptionEventBus()
        self.semantic_refresh_policy = SemanticRefreshPolicy(
            min_interval_seconds=float(
                getattr(
                    self.settings,
                    "blink_semantic_refresh_min_interval_seconds",
                    20.0,
                )
            ),
        )

    def default_mode(self) -> PerceptionProviderMode:
        configured = self.settings.perception_default_provider
        if configured in PerceptionProviderMode._value2member_map_:
            return PerceptionProviderMode(configured)
        return PerceptionProviderMode.STUB

    def submit_snapshot(self, request: PerceptionSnapshotSubmitRequest) -> PerceptionSubmissionResult:
        request = self._persist_snapshot_frame(request)
        log_event(
            logger,
            logging.INFO,
            "perception_snapshot_started",
            session_id=request.session_id,
            provider_mode=request.provider_mode.value,
            source=request.source,
            trigger_reason=request.trigger_reason,
        )
        provider = self.providers.get(request.provider_mode)
        if provider is None:
            snapshot = degraded_snapshot_for_error(
                request=request,
                message=f"Unsupported perception mode: {request.provider_mode.value}",
                error_code="perception_mode_unsupported",
            )
            self.memory.append_perception_snapshot(snapshot)
            log_event(
                logger,
                logging.WARNING,
                "perception_provider_missing",
                session_id=request.session_id,
                provider_mode=request.provider_mode.value,
                snapshot_id=snapshot.snapshot_id,
            )
            return PerceptionSubmissionResult(
                session_id=request.session_id,
                snapshot=snapshot,
                success=False,
                message=snapshot.message,
                latency_breakdown=LatencyBreakdownRecord(),
            )

        previous_snapshot = self.memory.get_latest_perception(request.session_id)
        with self.memory.batch_update():
            perception_start = perf_counter()
            try:
                snapshot = provider.analyze_snapshot(request)
            except PerceptionProviderError as exc:
                log_event(
                    logger,
                    logging.WARNING,
                    "perception_provider_degraded",
                    session_id=request.session_id,
                    provider_mode=request.provider_mode.value,
                    error_code=str(exc),
                )
                snapshot = degraded_snapshot_for_error(
                    request=request,
                    message="Perception is currently limited, so Blink-AI cannot make confident scene claims from this input.",
                    error_code=str(exc),
                )
            perception_ms = round((perf_counter() - perception_start) * 1000.0, 2)

            snapshot = normalize_snapshot_record(snapshot, request)
            snapshot.events = self.event_bus.build_events(snapshot, previous_snapshot)
            self.memory.append_perception_snapshot(snapshot)
            publish_start = perf_counter()
            published_results = self._publish_events(snapshot) if request.publish_events else []
            publish_ms = round((perf_counter() - publish_start) * 1000.0, 2)
            log_event(
                logger,
                logging.INFO,
                "perception_snapshot_completed",
                session_id=request.session_id,
                provider_mode=snapshot.provider_mode.value,
                snapshot_id=snapshot.snapshot_id,
                event_count=len(snapshot.events),
                published_count=len(published_results),
                total_ms=round(perception_ms + publish_ms, 2),
            )

            return PerceptionSubmissionResult(
                session_id=request.session_id,
                snapshot=snapshot,
                published_results=published_results,
                success=snapshot.status != PerceptionSnapshotStatus.FAILED,
                message=snapshot.message,
                latency_breakdown=LatencyBreakdownRecord(
                    perception_ms=perception_ms,
                    publish_ms=publish_ms,
                    total_ms=round(perception_ms + publish_ms, 2),
                ),
            )

    def replay_fixture(self, request: PerceptionReplayRequest) -> PerceptionReplayResult:
        start = perf_counter()
        try:
            frame_requests = self.fixture_provider.load_fixture(request)
        except PerceptionProviderError as exc:
            return PerceptionReplayResult(
                session_id=request.session_id,
                fixture_path=request.fixture_path,
                success=False,
                message=str(exc),
                latency_breakdown=LatencyBreakdownRecord(),
            )

        snapshots = [self.submit_snapshot(frame_request) for frame_request in frame_requests]
        return PerceptionReplayResult(
            session_id=request.session_id,
            fixture_path=request.fixture_path,
            snapshots=snapshots,
            success=all(item.success for item in snapshots),
            message="fixture_replay_completed",
            latency_breakdown=LatencyBreakdownRecord(
                perception_ms=round(sum(item.latency_breakdown.perception_ms or 0.0 for item in snapshots), 2),
                publish_ms=round(sum(item.latency_breakdown.publish_ms or 0.0 for item in snapshots), 2),
                total_ms=round((perf_counter() - start) * 1000.0, 2),
            ),
        )

    def _persist_snapshot_frame(self, request: PerceptionSnapshotSubmitRequest) -> PerceptionSnapshotSubmitRequest:
        if not request.image_data_url:
            return request
        if request.source_frame and request.source_frame.fixture_path:
            existing_path = Path(request.source_frame.fixture_path)
            if existing_path.exists():
                return request

        try:
            image_bytes = decode_data_url_bytes(request.image_data_url)
        except ValueError:
            return request

        source_frame = request.source_frame.model_copy(deep=True) if request.source_frame else PerceptionSourceFrame()
        source_kind = source_frame.source_kind or request.provider_mode.value
        if source_kind == "unknown":
            source_kind = request.provider_mode.value
        source_frame.source_kind = source_kind
        source_frame.source_label = source_frame.source_label or request.source
        source_frame.mime_type = source_frame.mime_type or mime_type_from_data_url(request.image_data_url)
        captured_at = source_frame.captured_at or utc_now()
        source_frame.captured_at = captured_at

        frame_root = Path(self.settings.perception_frame_dir)
        if not frame_root.is_absolute():
            frame_root = Path.cwd() / frame_root
        frame_dir = frame_root / captured_at.strftime("%Y%m%d")
        frame_dir.mkdir(parents=True, exist_ok=True)

        suffix = suffix_for_mime_type(source_frame.mime_type, fallback=Path(source_frame.file_name or "").suffix)
        label = sanitize_frame_component(source_frame.source_label or source_kind or request.source, default="snapshot")
        frame_id = sanitize_frame_component(source_frame.frame_id, default="frame")
        file_name = f"{captured_at.strftime('%Y%m%dT%H%M%S%f')}_{label}_{frame_id}{suffix}"
        persisted_path = frame_dir / file_name
        persisted_path.write_bytes(image_bytes)

        latest_path = frame_root / latest_snapshot_name(source_kind, suffix=suffix)
        latest_path.write_bytes(image_bytes)

        source_frame.fixture_path = str(persisted_path)
        source_frame.file_name = persisted_path.name
        source_frame.received_at = source_frame.received_at or utc_now()
        return request.model_copy(update={"source_frame": source_frame})

    def get_latest_snapshot(self, session_id: str | None = None) -> PerceptionSnapshotRecord | None:
        return self.memory.get_latest_perception(session_id)

    def list_history(self, session_id: str | None = None, limit: int = 20) -> PerceptionHistoryResponse:
        return self.memory.list_perception_history(session_id=session_id, limit=limit)

    def list_fixtures(self) -> PerceptionFixtureCatalogResponse:
        fixture_dir = resolve_fixture_dir(self.settings.perception_fixture_dir)
        items: list[PerceptionFixtureDefinition] = []
        if fixture_dir.exists():
            for path in sorted(fixture_dir.glob("perception_*.json")):
                try:
                    payload = json.loads(path.read_text(encoding="utf-8"))
                except ValueError:
                    continue
                items.append(
                    PerceptionFixtureDefinition(
                        fixture_name=str(payload.get("fixture_name") or path.stem),
                        title=str(payload.get("title") or path.stem.replace("_", " ").title()),
                        description=str(payload.get("description") or "Perception replay fixture."),
                        fixture_path=str(path),
                        source_kind=str(payload.get("source_kind") or "video_file_replay"),
                    )
                )
        return PerceptionFixtureCatalogResponse(items=items)

    def _publish_events(self, snapshot: PerceptionSnapshotRecord) -> list[PerceptionPublishedResult]:
        if self.event_handler is None:
            return []

        results: list[PerceptionPublishedResult] = []
        for item in snapshot.events:
            robot_event = RobotEvent(
                event_type=item.event_type.value,
                source=item.source,
                session_id=item.session_id,
                payload=item.payload,
            )
            response: CommandBatch = self.event_handler(robot_event)
            item.robot_event_id = robot_event.event_id
            item.trace_id = response.trace_id
            log_event(
                logger,
                logging.INFO,
                "perception_event_published",
                session_id=item.session_id,
                perception_event_id=item.perception_event_id,
                event_type=item.event_type.value,
                trace_id=response.trace_id,
                command_count=len(response.commands),
            )
            results.append(PerceptionPublishedResult(event=robot_event, response=response))
        return results


def build_source_frame(request: PerceptionSnapshotSubmitRequest, *, source_kind: str) -> PerceptionSourceFrame:
    source_frame = request.source_frame.model_copy(deep=True) if request.source_frame else PerceptionSourceFrame()
    if not source_frame.source_kind or source_frame.source_kind == "unknown":
        source_frame.source_kind = source_kind
    source_frame.source_label = source_frame.source_label or request.source
    return source_frame


def decode_data_url_bytes(image_data_url: str) -> bytes:
    if "," not in image_data_url:
        raise ValueError("invalid_data_url")
    return base64.b64decode(image_data_url.split(",", 1)[1])


def sanitize_frame_component(value: str | None, *, default: str) -> str:
    raw = (value or "").strip()
    if not raw:
        return default
    sanitized = _SANITIZE_FRAME_NAME_RE.sub("_", raw).strip("._-")
    return sanitized[:80] or default


def suffix_for_mime_type(mime_type: str | None, *, fallback: str | None = None) -> str:
    normalized = (mime_type or "").strip().lower()
    if normalized == "image/png":
        return ".png"
    if normalized == "image/webp":
        return ".webp"
    if normalized in {"image/jpg", "image/jpeg"}:
        return ".jpg"
    if fallback:
        candidate = Path(fallback).suffix if Path(fallback).suffix else fallback
        if candidate.startswith("."):
            return candidate
    return ".jpg"


def latest_snapshot_name(source_kind: str | None, *, suffix: str) -> str:
    normalized = (source_kind or "snapshot").strip().lower()
    if "browser" in normalized:
        stem = "latest_browser_snapshot"
    elif "camera" in normalized:
        stem = "latest_camera_snapshot"
    else:
        stem = "latest_snapshot"
    return f"{stem}{suffix}"


def degraded_snapshot_for_error(
    *,
    request: PerceptionSnapshotSubmitRequest,
    message: str,
    error_code: str,
) -> PerceptionSnapshotRecord:
    source_frame = build_source_frame(request, source_kind=request.provider_mode.value)
    return PerceptionSnapshotRecord(
        session_id=request.session_id,
        provider_mode=request.provider_mode,
        source=request.source,
        status=PerceptionSnapshotStatus.FAILED,
        limited_awareness=True,
        message=error_code,
        scene_summary=message,
        source_frame=source_frame,
        observations=[
            PerceptionObservation(
                observation_type=PerceptionObservationType.SCENE_SUMMARY,
                text_value=message,
                confidence=confidence_from_score(0.1),
                source_frame=source_frame,
                metadata={"error_code": error_code},
            )
        ],
    )


def normalize_snapshot_record(
    snapshot: PerceptionSnapshotRecord,
    request: PerceptionSnapshotSubmitRequest,
) -> PerceptionSnapshotRecord:
    content = normalize_snapshot_content(
        observations=snapshot.observations,
        source_frame=snapshot.source_frame,
        tier=request.tier,
        provider_mode=snapshot.provider_mode,
        scene_summary=snapshot.scene_summary,
        limited_awareness=snapshot.limited_awareness,
        message=snapshot.message,
        metadata={
            **request.metadata,
            **snapshot.provenance,
        },
    )
    scene_summary = (
        content.scene_summary
        or extract_scene_summary(content.observations)
        or summarize_observations(content.observations)
    )
    claim_kind = claim_kind_for_request(request)
    observations = [
        normalize_observation_claim(item, claim_kind=claim_kind)
        for item in content.observations
    ]
    if scene_summary and not any(
        item.observation_type == PerceptionObservationType.SCENE_SUMMARY and item.text_value == scene_summary
        for item in observations
    ):
        observations.append(
            PerceptionObservation(
                observation_type=PerceptionObservationType.SCENE_SUMMARY,
                text_value=scene_summary,
                confidence=confidence_from_score(average_confidence(observations) or 0.35),
                claim_kind=claim_kind,
                quality_class=quality_class_for_confidence(average_confidence(observations) or 0.35, claim_kind=claim_kind),
                source_frame=snapshot.source_frame,
                metadata={"generated": True, "normalization_layer": True},
            )
        )
    return snapshot.model_copy(
        update={
            "tier": request.tier,
            "trigger_reason": request.trigger_reason,
            "dialogue_eligible": request.tier == PerceptionTier.SEMANTIC and snapshot.status == PerceptionSnapshotStatus.OK and not snapshot.limited_awareness,
            "scene_summary": scene_summary,
            "observations": observations,
            "device_awareness_constraints": content.device_awareness_constraints,
            "uncertainty_markers": content.uncertainty_markers,
            "provenance": content.provenance,
        }
    )


def observation_from_annotation(
    annotation: PerceptionAnnotationInput,
    *,
    source_frame: PerceptionSourceFrame,
) -> PerceptionObservation:
    return PerceptionObservation(
        observation_type=annotation.observation_type,
        text_value=annotation.text_value,
        number_value=annotation.number_value,
        bool_value=annotation.bool_value,
        confidence=confidence_from_score(annotation.confidence if annotation.confidence is not None else 0.85),
        justification=str(annotation.metadata.get("justification") or "").strip() or None,
        source_frame=source_frame,
        metadata=dict(annotation.metadata),
    )


def normalize_manual_observations(
    observations: list[PerceptionObservation],
    *,
    source_frame: PerceptionSourceFrame,
) -> list[PerceptionObservation]:
    normalized = list(observations)
    people_count = next(
        (
            int(item.number_value)
            for item in normalized
            if item.observation_type == PerceptionObservationType.PEOPLE_COUNT and item.number_value is not None
        ),
        None,
    )
    if people_count is not None and not any(
        item.observation_type == PerceptionObservationType.PERSON_VISIBILITY for item in normalized
    ):
        normalized.append(
            PerceptionObservation(
                observation_type=PerceptionObservationType.PERSON_VISIBILITY,
                bool_value=people_count > 0,
                confidence=confidence_from_score(0.9),
                source_frame=source_frame,
                metadata={"derived_from": "people_count"},
            )
        )
    return normalized


def claim_kind_for_request(request: PerceptionSnapshotSubmitRequest) -> SceneClaimKind:
    explicit = str(request.metadata.get("claim_kind") or "").strip()
    if explicit in SceneClaimKind._value2member_map_:
        return SceneClaimKind(explicit)
    if request.tier == PerceptionTier.WATCHER:
        return SceneClaimKind.WATCHER_HINT
    if request.provider_mode == PerceptionProviderMode.MANUAL_ANNOTATIONS and request.source.startswith("operator"):
        return SceneClaimKind.OPERATOR_ANNOTATION
    return SceneClaimKind.SEMANTIC_OBSERVATION


def claim_kind_for_snapshot(snapshot: PerceptionSnapshotRecord) -> SceneClaimKind:
    explicit = str(snapshot.provenance.get("claim_kind") or "").strip()
    if explicit in SceneClaimKind._value2member_map_:
        return SceneClaimKind(explicit)
    if snapshot.tier == PerceptionTier.WATCHER:
        return SceneClaimKind.WATCHER_HINT
    if any(item.claim_kind == SceneClaimKind.OPERATOR_ANNOTATION for item in snapshot.observations):
        return SceneClaimKind.OPERATOR_ANNOTATION
    if snapshot.provider_mode == PerceptionProviderMode.MANUAL_ANNOTATIONS and snapshot.source.startswith("operator"):
        return SceneClaimKind.OPERATOR_ANNOTATION
    return SceneClaimKind.SEMANTIC_OBSERVATION


def quality_class_for_confidence(score: float, *, claim_kind: SceneClaimKind) -> SemanticQualityClass | None:
    if claim_kind == SceneClaimKind.WATCHER_HINT:
        return None
    label = confidence_from_score(score).label
    if label in SemanticQualityClass._value2member_map_:
        return SemanticQualityClass(label)
    return None


def normalize_observation_claim(
    observation: PerceptionObservation,
    *,
    claim_kind: SceneClaimKind,
) -> PerceptionObservation:
    score = observation.confidence.score if observation.confidence is not None else 0.0
    resolved_claim_kind = observation.claim_kind
    if resolved_claim_kind == SceneClaimKind.SEMANTIC_OBSERVATION and claim_kind != SceneClaimKind.SEMANTIC_OBSERVATION:
        resolved_claim_kind = claim_kind
    return observation.model_copy(
        update={
            "claim_kind": resolved_claim_kind,
            "quality_class": observation.quality_class or quality_class_for_confidence(score, claim_kind=resolved_claim_kind),
            "justification": observation.justification or str(observation.metadata.get("justification") or "").strip() or None,
        }
    )


def parse_multimodal_observations(
    raw_items: Any,
    *,
    source_frame: PerceptionSourceFrame,
) -> list[PerceptionObservation]:
    if not isinstance(raw_items, list):
        return []

    observations: list[PerceptionObservation] = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        observation_type = item.get("observation_type")
        if observation_type not in PerceptionObservationType._value2member_map_:
            continue
        confidence_value = item.get("confidence")
        text_value = item.get("text_value") if isinstance(item.get("text_value"), str) else None
        text_value = text_value.strip() if text_value is not None else None
        if text_value == "":
            text_value = None
        bool_value = item.get("bool_value") if isinstance(item.get("bool_value"), bool) else None
        if bool_value is None and observation_type == PerceptionObservationType.PERSON_VISIBILITY.value:
            bool_value = coerce_person_visibility_bool(text_value)
        observations.append(
            PerceptionObservation(
                observation_type=PerceptionObservationType(observation_type),
                text_value=text_value,
                number_value=float(item["number_value"]) if isinstance(item.get("number_value"), (int, float)) else None,
                bool_value=bool_value,
                confidence=confidence_from_score(float(confidence_value) if isinstance(confidence_value, (int, float)) else 0.55),
                justification=str(item.get("justification") or "").strip() or None,
                source_frame=source_frame,
                metadata=item.get("metadata") if isinstance(item.get("metadata"), dict) else {},
            )
        )
    return observations


def parse_ollama_vision_observations(
    raw_items: Any,
    *,
    source_frame: PerceptionSourceFrame,
) -> list[PerceptionObservation]:
    observations = parse_multimodal_observations(raw_items, source_frame=source_frame)
    if observations:
        return observations
    if not isinstance(raw_items, list):
        return []

    rescued: list[PerceptionObservation] = []
    for item in raw_items[:6]:
        if not isinstance(item, str):
            continue
        text_value = item.strip()
        if not text_value:
            continue
        lowered = text_value.lower()
        number_match = re.search(r"\b(\d+)\b", lowered)
        if "people" in lowered and number_match is not None:
            rescued.append(
                PerceptionObservation(
                    observation_type=PerceptionObservationType.PEOPLE_COUNT,
                    number_value=float(number_match.group(1)),
                    confidence=confidence_from_score(0.45),
                    source_frame=source_frame,
                    metadata={"rescued_from": "string_observation"},
                )
            )
            continue
        observation_type = PerceptionObservationType.NAMED_OBJECT
        if any(term in lowered for term in ("text", "sign", "label", "screen", "poster")):
            observation_type = PerceptionObservationType.VISIBLE_TEXT
        elif any(term in lowered for term in ("desk", "counter", "door", "room", "hall", "lobby")):
            observation_type = PerceptionObservationType.LOCATION_ANCHOR
        rescued.append(
            PerceptionObservation(
                observation_type=observation_type,
                text_value=text_value,
                confidence=confidence_from_score(0.4),
                source_frame=source_frame,
                metadata={"rescued_from": "string_observation"},
            )
        )
    return rescued


def summarize_observations(observations: list[PerceptionObservation]) -> str | None:
    parts: list[str] = []
    people_count = next(
        (
            int(item.number_value)
            for item in observations
            if item.observation_type == PerceptionObservationType.PEOPLE_COUNT and item.number_value is not None
        ),
        None,
    )
    if people_count is not None:
        noun = "person" if people_count == 1 else "people"
        parts.append(f"{people_count} {noun} visible")

    anchors = [item.text_value for item in observations if item.observation_type == PerceptionObservationType.LOCATION_ANCHOR and item.text_value]
    if anchors:
        parts.append(f"location anchors: {', '.join(anchors)}")

    visible_text = [item.text_value for item in observations if item.observation_type == PerceptionObservationType.VISIBLE_TEXT and item.text_value]
    if visible_text:
        parts.append(f"visible text: {', '.join(visible_text)}")

    objects = [item.text_value for item in observations if item.observation_type == PerceptionObservationType.NAMED_OBJECT and item.text_value]
    if objects:
        parts.append(f"objects: {', '.join(objects)}")

    engagement = next(
        (
            item.text_value
            for item in observations
            if item.observation_type == PerceptionObservationType.ENGAGEMENT_ESTIMATE and item.text_value
        ),
        None,
    )
    if engagement:
        parts.append(f"engagement: {engagement}")

    if not parts:
        return None
    return ". ".join(parts).strip().capitalize() + "."


def extract_scene_summary(observations: list[PerceptionObservation]) -> str | None:
    for item in observations:
        if item.observation_type == PerceptionObservationType.SCENE_SUMMARY and item.text_value:
            return item.text_value
    return None


def filter_observations(snapshot: PerceptionSnapshotRecord, observation_type: PerceptionObservationType) -> list[PerceptionObservation]:
    return [item for item in snapshot.observations if item.observation_type == observation_type]


def find_first_observation(
    snapshot: PerceptionSnapshotRecord,
    observation_type: PerceptionObservationType,
) -> PerceptionObservation | None:
    for item in snapshot.observations:
        if item.observation_type == observation_type:
            return item
    return None


def integer_observation_value(
    snapshot: PerceptionSnapshotRecord | None,
    observation_type: PerceptionObservationType,
) -> int | None:
    if snapshot is None:
        return None
    observation = find_first_observation(snapshot, observation_type)
    if observation and observation.number_value is not None:
        return int(observation.number_value)
    return None


def boolean_observation_value(
    snapshot: PerceptionSnapshotRecord | None,
    observation_type: PerceptionObservationType,
) -> bool | None:
    if snapshot is None:
        return None
    observation = find_first_observation(snapshot, observation_type)
    if observation is None:
        return None
    return observation.bool_value


def text_observation_value(
    snapshot: PerceptionSnapshotRecord | None,
    observation_type: PerceptionObservationType,
) -> str | None:
    if snapshot is None:
        return None
    observation = find_first_observation(snapshot, observation_type)
    if observation is None:
        return None
    return observation.text_value


def event_from_observation(
    *,
    snapshot: PerceptionSnapshotRecord,
    event_type: PerceptionEventType,
    observation: PerceptionObservation | None,
    payload: dict[str, Any],
) -> PerceptionEventRecord:
    confidence = observation.confidence if observation is not None else confidence_from_score(0.35)
    source_frame = observation.source_frame if observation is not None else snapshot.source_frame
    merged_payload = {
        **payload,
        "confidence": confidence.score,
        "confidence_label": confidence.label,
        "claim_kind": (
            observation.claim_kind.value
            if observation is not None and observation.claim_kind is not None
            else claim_kind_for_snapshot(snapshot).value
        ),
        "quality_class": (
            observation.quality_class.value
            if observation is not None and observation.quality_class is not None
            else None
        ),
        "justification": observation.justification if observation is not None else None,
        "dialogue_eligible": snapshot.dialogue_eligible,
        "provider_mode": snapshot.provider_mode.value,
        "tier": snapshot.tier.value,
        "trigger_reason": snapshot.trigger_reason,
        "source_kind": source_frame.source_kind,
        "frame_id": source_frame.frame_id,
        "captured_at": source_frame.captured_at.isoformat() if source_frame.captured_at else None,
        "received_at": source_frame.received_at.isoformat(),
        "limited_awareness": snapshot.limited_awareness,
        "uncertainty_markers": list(snapshot.uncertainty_markers),
        "device_awareness_constraints": list(snapshot.device_awareness_constraints),
    }
    return PerceptionEventRecord(
        event_type=event_type,
        session_id=snapshot.session_id,
        source=f"perception:{snapshot.provider_mode.value}",
        provider_mode=snapshot.provider_mode,
        confidence=confidence,
        source_frame=source_frame,
        payload=merged_payload,
    )


def confidence_from_score(score: float) -> PerceptionConfidence:
    bounded = max(0.0, min(1.0, float(score)))
    if bounded >= 0.8:
        label = "high"
    elif bounded >= 0.55:
        label = "medium"
    else:
        label = "low"
    return PerceptionConfidence(score=bounded, label=label)


def average_confidence(observations: list[PerceptionObservation]) -> float:
    if not observations:
        return 0.0
    return sum(item.confidence.score for item in observations) / len(observations)


def mime_type_from_data_url(value: str) -> str | None:
    if not value.startswith("data:"):
        return None
    header = value.split(",", 1)[0]
    if ";" not in header:
        return None
    return header[5:].split(";", 1)[0]


def base64_payload_from_data_url(value: str) -> str:
    if ";base64," not in value:
        raise PerceptionProviderError("snapshot_image_missing_base64_payload")
    return value.split(";base64,", 1)[1]


@dataclass(frozen=True)
class PreparedSemanticVisionImage:
    data_url: str
    base64_payload: str
    mime_type: str
    original_width_px: int | None
    original_height_px: int | None


def prepare_semantic_vision_image(value: str) -> PreparedSemanticVisionImage:
    original_payload = base64_payload_from_data_url(value)
    raw_bytes = base64.b64decode(original_payload)
    with Image.open(io.BytesIO(raw_bytes)) as image:
        width, height = image.size
        working = image.copy()
    if max(width, height) > _OLLAMA_VISION_MAX_DIMENSION_PX:
        working.thumbnail((_OLLAMA_VISION_MAX_DIMENSION_PX, _OLLAMA_VISION_MAX_DIMENSION_PX), Image.Resampling.LANCZOS)
    if working.mode not in {"RGB", "L"}:
        converted = Image.new("RGB", working.size, (255, 255, 255))
        converted.paste(working, mask=working.getchannel("A") if "A" in working.getbands() else None)
        working = converted
    elif working.mode == "L":
        working = working.convert("RGB")

    output = io.BytesIO()
    working.save(output, format="JPEG", quality=78, optimize=True)
    processed_payload = base64.b64encode(output.getvalue()).decode("ascii")
    return PreparedSemanticVisionImage(
        data_url=f"data:image/jpeg;base64,{processed_payload}",
        base64_payload=processed_payload,
        mime_type="image/jpeg",
        original_width_px=width,
        original_height_px=height,
    )


def extract_json_object_text(value: str) -> str:
    stripped = value.strip()
    stripped = _JSON_FENCE_RE.sub("", stripped).strip()
    object_start = stripped.find("{")
    object_end = stripped.rfind("}")
    if object_start != -1 and object_end != -1 and object_end > object_start:
        return stripped[object_start : object_end + 1]
    return stripped


def coerce_boolean_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "yes", "1"}:
            return True
        if lowered in {"false", "no", "0"}:
            return False
        if any(term in lowered for term in ("limited", "unclear", "cannot", "can't", "insufficient")):
            return True
    return False


def coerce_person_visibility_bool(value: str | None) -> bool | None:
    if value is None:
        return None
    lowered = value.strip().lower()
    if lowered in {"visible", "yes", "true", "partial", "present", "person present"}:
        return True
    if lowered in {"not visible", "none", "no", "false", "absent"}:
        return False
    return None


def chat_completions_url(base_url: str) -> str:
    normalized = base_url.rstrip("/")
    if normalized.endswith("/v1"):
        normalized = normalized[:-3]
    return f"{normalized}/v1/chat/completions"


def extract_chat_completion_text(body: dict[str, Any]) -> str:
    choices = body.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    choice = choices[0]
    if not isinstance(choice, dict):
        return ""
    message = choice.get("message")
    if not isinstance(message, dict):
        return ""
    content = message.get("content")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"].strip())
        return "\n".join(part for part in parts if part).strip()
    return ""


def extract_ollama_chat_text(body: dict[str, Any]) -> str:
    message = body.get("message")
    if not isinstance(message, dict):
        return ""
    content = message.get("content")
    return content.strip() if isinstance(content, str) else ""


def resolve_fixture_dir(configured_path: str) -> Path:
    candidate = Path(configured_path)
    if candidate.exists():
        return candidate
    return Path(__file__).resolve().parents[2] / "demo" / "data"
