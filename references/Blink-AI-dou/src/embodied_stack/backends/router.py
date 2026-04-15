from __future__ import annotations

import shutil
from dataclasses import dataclass
from datetime import datetime
from time import monotonic

import httpx

from embodied_stack.backends.local_paths import resolve_whisper_cpp_binary_path, resolve_whisper_cpp_model_path
from embodied_stack.brain.llm import (
    DialogueEngine,
    FallbackDialogueEngine,
    GRSAIDialogueEngine,
    OllamaDialogueEngine,
    RuleBasedDialogueEngine,
)
from embodied_stack.brain.perception import (
    BrowserSnapshotPerceptionProvider,
    ManualAnnotationsPerceptionProvider,
    MultimodalLLMPerceptionProvider,
    NativeCameraSnapshotPerceptionProvider,
    OllamaVisionPerceptionProvider,
    PerceptionProvider,
    StubPerceptionProvider,
)
from embodied_stack.config import Settings
from embodied_stack.multimodal.camera import describe_camera_source
from embodied_stack.shared.models import (
    LocalModelResidencyRecord,
    PerceptionProviderMode,
    RuntimeBackendAvailability,
    RuntimeBackendKind,
    RuntimeBackendStatus,
    utc_now,
)

from .embeddings import FallbackEmbeddingBackend, HashEmbeddingBackend, OllamaEmbeddingBackend
from .profiles import backend_candidates_for, resolve_backend_profile
from .types import BackendRouteDecision, EmbeddingBackend


_OLLAMA_STATUS_TTL_SECONDS = 3.0


@dataclass(frozen=True)
class OllamaProbeSnapshot:
    reachable: bool
    installed_models: set[str]
    running_models: set[str]
    latency_ms: float | None = None
    error: str | None = None


@dataclass
class OllamaRuntimeNote:
    active_model: str | None = None
    last_success_latency_ms: float | None = None
    last_failure_reason: str | None = None
    last_failure_at: datetime | None = None
    last_timeout_seconds: float | None = None
    cold_start_retry_used: bool = False


class OllamaRuntimeProbe:
    def __init__(self, *, base_url: str, timeout_seconds: float) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self._cached_at = 0.0
        self._cached_snapshot = OllamaProbeSnapshot(
            reachable=False,
            installed_models=set(),
            running_models=set(),
            error="ollama_not_probed",
        )

    def snapshot(self) -> OllamaProbeSnapshot:
        now = monotonic()
        if now - self._cached_at < _OLLAMA_STATUS_TTL_SECONDS:
            return self._cached_snapshot

        if not self.base_url:
            self._cached_at = now
            self._cached_snapshot = OllamaProbeSnapshot(
                reachable=False,
                installed_models=set(),
                running_models=set(),
                error="ollama_base_url_missing",
            )
            return self._cached_snapshot

        try:
            start = monotonic()
            with httpx.Client(timeout=self.timeout_seconds) as client:
                tags_response = client.get(f"{self.base_url}/api/tags")
                tags_response.raise_for_status()
                tags_payload = tags_response.json()
                try:
                    ps_response = client.get(f"{self.base_url}/api/ps")
                    ps_response.raise_for_status()
                    ps_payload = ps_response.json()
                except httpx.HTTPError:
                    ps_payload = {}
        except httpx.TimeoutException:
            snapshot = OllamaProbeSnapshot(
                reachable=False,
                installed_models=set(),
                running_models=set(),
                error="ollama_probe_timeout",
            )
        except httpx.HTTPError as exc:
            snapshot = OllamaProbeSnapshot(
                reachable=False,
                installed_models=set(),
                running_models=set(),
                error=f"ollama_probe_http_error:{exc}",
            )
        except ValueError:
            snapshot = OllamaProbeSnapshot(reachable=False, installed_models=set(), running_models=set(), error="ollama_probe_invalid_json")
        else:
            latency_ms = round((monotonic() - start) * 1000.0, 2)
            installed = {
                str(item.get("name") or "").strip()
                for item in tags_payload.get("models", [])
                if isinstance(item, dict) and str(item.get("name") or "").strip()
            }
            running = {
                str(item.get("name") or "").strip()
                for item in ps_payload.get("models", [])
                if isinstance(item, dict) and str(item.get("name") or "").strip()
            }
            snapshot = OllamaProbeSnapshot(
                reachable=True,
                installed_models=installed,
                running_models=running,
                latency_ms=latency_ms,
            )

        self._cached_at = now
        self._cached_snapshot = snapshot
        return snapshot


class BackendRouter:
    def __init__(
        self,
        *,
        settings: Settings,
        ollama_probe: OllamaRuntimeProbe | None = None,
    ) -> None:
        self.settings = settings
        self.profile = resolve_backend_profile(settings)
        probe_timeout = min(max(self._ollama_timeout_seconds_for(RuntimeBackendKind.TEXT_REASONING), 0.25), 1.0)
        self.ollama_probe = ollama_probe or OllamaRuntimeProbe(
            base_url=settings.ollama_base_url,
            timeout_seconds=probe_timeout,
        )
        self._ollama_runtime: dict[RuntimeBackendKind, OllamaRuntimeNote] = {}
        self._model_residency: dict[RuntimeBackendKind, LocalModelResidencyRecord] = {}

    def resolved_backend_profile(self) -> str:
        return self.profile.name

    def route_decisions(self) -> list[BackendRouteDecision]:
        return [
            self._resolve_kind(RuntimeBackendKind.TEXT_REASONING),
            self._resolve_kind(RuntimeBackendKind.VISION_ANALYSIS),
            self._resolve_kind(RuntimeBackendKind.EMBEDDINGS),
            self._resolve_kind(RuntimeBackendKind.SPEECH_TO_TEXT),
            self._resolve_kind(RuntimeBackendKind.TEXT_TO_SPEECH),
        ]

    def runtime_statuses(self) -> list[RuntimeBackendStatus]:
        return [item.to_status_model() for item in self.route_decisions()]

    def report_ollama_success(
        self,
        *,
        kind: RuntimeBackendKind,
        model: str,
        latency_ms: float,
        retry_used: bool = False,
    ) -> None:
        note = self._ollama_runtime.get(kind, OllamaRuntimeNote())
        note.active_model = model
        note.last_success_latency_ms = round(latency_ms, 2)
        note.cold_start_retry_used = retry_used
        self._ollama_runtime[kind] = note
        keep_warm = kind in {RuntimeBackendKind.TEXT_REASONING, RuntimeBackendKind.EMBEDDINGS}
        self._model_residency[kind] = LocalModelResidencyRecord(
            kind=kind,
            backend_id={
                RuntimeBackendKind.TEXT_REASONING: "ollama_text",
                RuntimeBackendKind.VISION_ANALYSIS: "ollama_vision",
                RuntimeBackendKind.EMBEDDINGS: "ollama_embed",
            }[kind],
            model=model,
            keep_warm=keep_warm,
            resident=True,
            status="resident",
            last_used_at=utc_now(),
            idle_timeout_seconds=None if keep_warm else float(self.settings.blink_model_idle_unload_seconds),
            detail=f"last_success_latency_ms={round(latency_ms, 2)}",
        )

    def report_ollama_failure(
        self,
        *,
        kind: RuntimeBackendKind,
        reason: str,
        timeout_seconds: float | None = None,
        retry_used: bool = False,
    ) -> None:
        note = self._ollama_runtime.get(kind, OllamaRuntimeNote())
        note.last_failure_reason = reason
        note.last_failure_at = utc_now()
        note.last_timeout_seconds = timeout_seconds
        note.cold_start_retry_used = retry_used
        self._ollama_runtime[kind] = note

    def model_residency(self) -> list[LocalModelResidencyRecord]:
        records: list[LocalModelResidencyRecord] = []
        for kind, backend_id, model, keep_warm in (
            (RuntimeBackendKind.TEXT_REASONING, self.selected_backend_id(RuntimeBackendKind.TEXT_REASONING), self._ollama_text_model(), True),
            (RuntimeBackendKind.VISION_ANALYSIS, self.selected_backend_id(RuntimeBackendKind.VISION_ANALYSIS), self._ollama_vision_model(), False),
            (RuntimeBackendKind.EMBEDDINGS, self.selected_backend_id(RuntimeBackendKind.EMBEDDINGS), self.settings.ollama_embedding_model, True),
        ):
            if not backend_id.startswith("ollama"):
                continue
            record = self._model_residency.get(kind)
            if record is None:
                record = LocalModelResidencyRecord(
                    kind=kind,
                    backend_id=backend_id,
                    model=model,
                    keep_warm=keep_warm,
                    resident=False,
                    status="configured" if model else "inactive",
                    idle_timeout_seconds=None if keep_warm else float(self.settings.blink_model_idle_unload_seconds),
                    detail="awaiting_first_use",
                )
            shared_record = self._shared_resident_record(kind=kind, model=record.model)
            if shared_record is not None and not record.resident:
                record = record.model_copy(
                    update={
                        "resident": True,
                        "status": "shared_resident",
                        "last_used_at": shared_record.last_used_at,
                        "detail": f"shared_model_with={shared_record.kind.value}",
                    }
                )
            records.append(record.model_copy(deep=True))
        return records

    def apply_model_residency_policy(self) -> list[LocalModelResidencyRecord]:
        updated: list[LocalModelResidencyRecord] = []
        snapshot = self.ollama_probe.snapshot()
        if not snapshot.reachable:
            return self.model_residency()
        now = utc_now()
        for kind, record in list(self._model_residency.items()):
            if record.keep_warm or not record.resident or record.last_used_at is None:
                updated.append(record.model_copy(deep=True))
                continue
            shared_record = self._shared_resident_record(kind=kind, model=record.model)
            if shared_record is not None:
                next_record = record.model_copy(
                    update={
                        "resident": True,
                        "status": "shared_resident",
                        "detail": f"shared_model_with={shared_record.kind.value}",
                    }
                )
                self._model_residency[kind] = next_record
                updated.append(next_record.model_copy(deep=True))
                continue
            idle_timeout = float(record.idle_timeout_seconds or self.settings.blink_model_idle_unload_seconds)
            idle_seconds = (now - record.last_used_at).total_seconds()
            if idle_seconds < idle_timeout:
                updated.append(record.model_copy(deep=True))
                continue
            unload_requested = self._request_ollama_unload(record.model)
            next_record = record.model_copy(
                update={
                    "resident": not unload_requested,
                    "status": "unloaded" if unload_requested else "resident",
                    "unload_requested_at": now,
                    "detail": "idle_unload_requested" if unload_requested else "idle_unload_failed",
                }
            )
            self._model_residency[kind] = next_record
            updated.append(next_record.model_copy(deep=True))
        return updated

    def prewarm_local_models(self) -> None:
        if not self.settings.blink_local_model_prewarm:
            return
        snapshot = self.ollama_probe.snapshot()
        if not snapshot.reachable:
            return
        try:
            text_model = self._ollama_text_model()
            if text_model and text_model in snapshot.installed_models:
                with httpx.Client(
                    timeout=self._ollama_timeout_seconds_for(
                        RuntimeBackendKind.TEXT_REASONING,
                        cold_start=True,
                    )
                ) as client:
                    client.post(
                        f"{self.settings.ollama_base_url.rstrip('/')}/api/chat",
                        json={
                            "model": text_model,
                            "stream": False,
                            "keep_alive": self.settings.ollama_keep_alive,
                            "messages": [{"role": "user", "content": "ping"}],
                            "options": {"temperature": 0.0, "num_predict": 1},
                        },
                    )
            if self.settings.ollama_embedding_model and self.settings.ollama_embedding_model in snapshot.installed_models:
                with httpx.Client(timeout=self._ollama_timeout_seconds_for(RuntimeBackendKind.EMBEDDINGS)) as client:
                    client.post(
                        f"{self.settings.ollama_base_url.rstrip('/')}/api/embed",
                        json={
                            "model": self.settings.ollama_embedding_model,
                            "input": ["warm"],
                        },
                    )
        except httpx.HTTPError:
            return

    def selected_backend_id(self, kind: RuntimeBackendKind) -> str:
        return self._resolve_kind(kind).backend_id

    def build_dialogue_engine(self) -> DialogueEngine:
        engines: list[DialogueEngine] = []
        seen: set[str] = set()
        for backend_id in backend_candidates_for(self.settings, RuntimeBackendKind.TEXT_REASONING):
            if backend_id in seen:
                continue
            seen.add(backend_id)
            engine = self._dialogue_engine_for(backend_id)
            if engine is not None:
                engines.append(engine)
        if not engines:
            return RuleBasedDialogueEngine()
        chain = engines[-1]
        for engine in reversed(engines[:-1]):
            chain = FallbackDialogueEngine(primary=engine, fallback=chain)
        return chain

    def build_embedding_backend(self) -> EmbeddingBackend:
        candidates: list[EmbeddingBackend] = []
        seen: set[str] = set()
        for backend_id in backend_candidates_for(self.settings, RuntimeBackendKind.EMBEDDINGS):
            if backend_id in seen:
                continue
            seen.add(backend_id)
            backend = self._embedding_backend_for(backend_id)
            if backend is not None:
                candidates.append(backend)
        if not candidates:
            return HashEmbeddingBackend()
        chain = candidates[-1]
        for backend in reversed(candidates[:-1]):
            chain = FallbackEmbeddingBackend(primary=backend, fallback=chain)
        return chain

    def build_perception_providers(self) -> dict[PerceptionProviderMode, PerceptionProvider]:
        manual_provider = ManualAnnotationsPerceptionProvider()
        return {
            PerceptionProviderMode.STUB: StubPerceptionProvider(),
            PerceptionProviderMode.MANUAL_ANNOTATIONS: manual_provider,
            PerceptionProviderMode.OLLAMA_VISION: OllamaVisionPerceptionProvider(
                base_url=self.settings.ollama_base_url,
                model=self._ollama_vision_model(),
                timeout_seconds=self._ollama_timeout_seconds_for(RuntimeBackendKind.VISION_ANALYSIS),
                keep_alive=self.settings.ollama_keep_alive,
                success_reporter=self._report_ollama_vision_success,
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

    def selected_perception_mode(self) -> PerceptionProviderMode:
        backend_id = self.selected_backend_id(RuntimeBackendKind.VISION_ANALYSIS)
        return {
            "multimodal_llm": PerceptionProviderMode.MULTIMODAL_LLM,
            "ollama_vision": PerceptionProviderMode.OLLAMA_VISION,
            "native_camera_snapshot": PerceptionProviderMode.NATIVE_CAMERA_SNAPSHOT,
            "browser_snapshot": PerceptionProviderMode.BROWSER_SNAPSHOT,
            "stub_vision": PerceptionProviderMode.STUB,
        }.get(backend_id, PerceptionProviderMode.STUB)

    def selected_semantic_vision_backend_id(self) -> str | None:
        decision = self._semantic_vision_decision()
        return decision.backend_id if decision is not None else None

    def selected_semantic_perception_mode(self) -> PerceptionProviderMode | None:
        backend_id = self.selected_semantic_vision_backend_id()
        return {
            "multimodal_llm": PerceptionProviderMode.MULTIMODAL_LLM,
            "ollama_vision": PerceptionProviderMode.OLLAMA_VISION,
        }.get(backend_id)

    def legacy_dialogue_backend(self) -> str:
        backend_id = self.selected_backend_id(RuntimeBackendKind.TEXT_REASONING)
        return {
            "grsai_chat": "grsai",
            "ollama_text": "ollama",
            "rule_based": "rule_based",
        }.get(backend_id, "rule_based")

    def _resolve_kind(self, kind: RuntimeBackendKind) -> BackendRouteDecision:
        candidates = backend_candidates_for(self.settings, kind)
        requested = candidates[0]
        evaluated = [self._evaluate_candidate(kind, backend_id) for backend_id in candidates]
        for decision in evaluated:
            if decision.status != RuntimeBackendAvailability.UNAVAILABLE:
                if decision.backend_id != requested:
                    return BackendRouteDecision(
                        kind=decision.kind,
                        backend_id=decision.backend_id,
                        status=RuntimeBackendAvailability.FALLBACK_ACTIVE,
                        provider=decision.provider,
                        model=decision.model,
                        local=decision.local,
                        cloud=decision.cloud,
                        requested_backend_id=requested,
                        fallback_from=requested,
                        detail=decision.detail,
                        requested_model=decision.requested_model,
                        active_model=decision.active_model,
                        reachable=decision.reachable,
                        installed=decision.installed,
                        warm=decision.warm,
                        keep_alive=decision.keep_alive,
                        last_success_latency_ms=decision.last_success_latency_ms,
                        last_failure_reason=decision.last_failure_reason,
                        last_failure_at=decision.last_failure_at,
                        last_timeout_seconds=decision.last_timeout_seconds,
                        cold_start_retry_used=decision.cold_start_retry_used,
                    )
                return decision
        unavailable = evaluated[0]
        return BackendRouteDecision(
            kind=kind,
            backend_id=unavailable.backend_id,
            status=RuntimeBackendAvailability.UNAVAILABLE,
            provider=unavailable.provider,
            model=unavailable.model,
            local=unavailable.local,
            cloud=unavailable.cloud,
            requested_backend_id=requested,
            detail=unavailable.detail,
            requested_model=unavailable.requested_model,
            active_model=unavailable.active_model,
            reachable=unavailable.reachable,
            installed=unavailable.installed,
            warm=unavailable.warm,
            keep_alive=unavailable.keep_alive,
            last_success_latency_ms=unavailable.last_success_latency_ms,
            last_failure_reason=unavailable.last_failure_reason,
            last_failure_at=unavailable.last_failure_at,
            last_timeout_seconds=unavailable.last_timeout_seconds,
            cold_start_retry_used=unavailable.cold_start_retry_used,
        )

    def _evaluate_candidate(self, kind: RuntimeBackendKind, backend_id: str) -> BackendRouteDecision:
        if kind == RuntimeBackendKind.TEXT_REASONING:
            return self._evaluate_text_backend(backend_id)
        if kind == RuntimeBackendKind.VISION_ANALYSIS:
            return self._evaluate_vision_backend(backend_id)
        if kind == RuntimeBackendKind.EMBEDDINGS:
            return self._evaluate_embedding_backend(backend_id)
        if kind == RuntimeBackendKind.SPEECH_TO_TEXT:
            return self._evaluate_stt_backend(backend_id)
        return self._evaluate_tts_backend(backend_id)

    def _evaluate_text_backend(self, backend_id: str) -> BackendRouteDecision:
        if backend_id == "grsai_chat":
            configured = bool(self.settings.grsai_api_key and self.settings.grsai_base_url and self.settings.grsai_model)
            return BackendRouteDecision(
                kind=RuntimeBackendKind.TEXT_REASONING,
                backend_id=backend_id,
                status=RuntimeBackendAvailability.CONFIGURED if configured else RuntimeBackendAvailability.UNAVAILABLE,
                provider="grsai",
                model=self.settings.grsai_model,
                cloud=True,
                detail="grsai_chat_ready" if configured else "grsai_chat_missing_configuration",
            )
        if backend_id == "ollama_text":
            return self._evaluate_ollama_model(
                kind=RuntimeBackendKind.TEXT_REASONING,
                backend_id=backend_id,
                model=self._ollama_text_model(),
            )
        return BackendRouteDecision(
            kind=RuntimeBackendKind.TEXT_REASONING,
            backend_id="rule_based",
            status=RuntimeBackendAvailability.WARM,
            provider="rule_based",
            local=True,
            detail="deterministic_local_reply_engine",
        )

    def _evaluate_vision_backend(self, backend_id: str) -> BackendRouteDecision:
        if backend_id == "multimodal_llm":
            configured = bool(
                self.settings.perception_multimodal_api_key
                and self.settings.perception_multimodal_base_url
                and self.settings.perception_multimodal_model
            )
            return BackendRouteDecision(
                kind=RuntimeBackendKind.VISION_ANALYSIS,
                backend_id=backend_id,
                status=RuntimeBackendAvailability.CONFIGURED if configured else RuntimeBackendAvailability.UNAVAILABLE,
                provider="openai_compatible_multimodal",
                model=self.settings.perception_multimodal_model,
                cloud=True,
                detail="multimodal_llm_ready" if configured else "multimodal_llm_missing_configuration",
            )
        if backend_id == "ollama_vision":
            return self._evaluate_ollama_model(
                kind=RuntimeBackendKind.VISION_ANALYSIS,
                backend_id=backend_id,
                model=self._ollama_vision_model(),
            )
        if backend_id == "browser_snapshot":
            return BackendRouteDecision(
                kind=RuntimeBackendKind.VISION_ANALYSIS,
                backend_id=backend_id,
                status=RuntimeBackendAvailability.DEGRADED,
                provider="browser_snapshot",
                local=True,
                detail="browser_snapshot_requires_browser_permission_and_does_not_analyze_frames_on_its_own",
            )
        if backend_id == "native_camera_snapshot":
            source = describe_camera_source(self.settings)
            available = source.mode in {"webcam", "fixture_replay", "browser_snapshot"} and source.available
            return BackendRouteDecision(
                kind=RuntimeBackendKind.VISION_ANALYSIS,
                backend_id=backend_id,
                status=RuntimeBackendAvailability.DEGRADED if available else RuntimeBackendAvailability.UNAVAILABLE,
                provider="desktop_camera",
                local=True,
                detail=source.note or "native_camera_snapshot_limited_awareness",
            )
        return BackendRouteDecision(
            kind=RuntimeBackendKind.VISION_ANALYSIS,
            backend_id="stub_vision",
            status=RuntimeBackendAvailability.DEGRADED,
            provider="stub_perception",
            local=True,
            detail="stub_perception_mode",
        )

    def _evaluate_embedding_backend(self, backend_id: str) -> BackendRouteDecision:
        if backend_id == "ollama_embed":
            return self._evaluate_ollama_model(
                kind=RuntimeBackendKind.EMBEDDINGS,
                backend_id=backend_id,
                model=self.settings.ollama_embedding_model,
            )
        return BackendRouteDecision(
            kind=RuntimeBackendKind.EMBEDDINGS,
            backend_id="hash_embed",
            status=RuntimeBackendAvailability.WARM,
            provider="local_hash_embedding",
            local=True,
            detail="deterministic_local_embedding_fallback",
        )

    def _evaluate_stt_backend(self, backend_id: str) -> BackendRouteDecision:
        if backend_id == "whisper_cpp_local":
            binary_path = self._whisper_binary_path()
            model_path = self._whisper_model_path()
            available = bool(shutil.which("ffmpeg") and binary_path and model_path)
            return BackendRouteDecision(
                kind=RuntimeBackendKind.SPEECH_TO_TEXT,
                backend_id=backend_id,
                status=RuntimeBackendAvailability.CONFIGURED if available else RuntimeBackendAvailability.UNAVAILABLE,
                provider="whisper_cpp",
                model=model_path,
                local=True,
                detail="whisper_cpp_local_ready" if available else "whisper_cpp_local_dependency_missing",
            )
        if backend_id == "apple_speech_local":
            available = bool(
                shutil.which("ffmpeg")
                and shutil.which("swiftc")
                and self._apple_speech_helper_path().exists()
            )
            return BackendRouteDecision(
                kind=RuntimeBackendKind.SPEECH_TO_TEXT,
                backend_id=backend_id,
                status=RuntimeBackendAvailability.WARM if available else RuntimeBackendAvailability.UNAVAILABLE,
                provider="apple_speech",
                local=True,
                detail="native_mac_stt_ready" if available else "apple_speech_local_dependency_missing",
            )
        return BackendRouteDecision(
            kind=RuntimeBackendKind.SPEECH_TO_TEXT,
            backend_id="typed_input",
            status=RuntimeBackendAvailability.DEGRADED,
            provider="typed_input",
            local=True,
            detail="typed_input_only_no_audio_transcription",
        )

    def _evaluate_tts_backend(self, backend_id: str) -> BackendRouteDecision:
        if backend_id == "piper_local":
            binary_path = self._piper_binary_path()
            model_path = self._piper_model_path()
            available = bool(binary_path and model_path and shutil.which("afplay"))
            return BackendRouteDecision(
                kind=RuntimeBackendKind.TEXT_TO_SPEECH,
                backend_id=backend_id,
                status=RuntimeBackendAvailability.CONFIGURED if available else RuntimeBackendAvailability.UNAVAILABLE,
                provider="piper",
                model=model_path,
                local=True,
                detail="piper_local_ready" if available else "piper_local_dependency_missing",
            )
        if backend_id == "macos_say":
            available = bool(shutil.which("say"))
            return BackendRouteDecision(
                kind=RuntimeBackendKind.TEXT_TO_SPEECH,
                backend_id=backend_id,
                status=RuntimeBackendAvailability.WARM if available else RuntimeBackendAvailability.UNAVAILABLE,
                provider="macos_say",
                model=self.settings.macos_tts_voice,
                local=True,
                detail="macos_say_ready" if available else "say_command_missing",
            )
        return BackendRouteDecision(
            kind=RuntimeBackendKind.TEXT_TO_SPEECH,
            backend_id="stub_tts",
            status=RuntimeBackendAvailability.DEGRADED,
            provider="stub_tts",
            local=True,
            detail="simulated_speech_output_only",
        )

    def _evaluate_ollama_model(
        self,
        *,
        kind: RuntimeBackendKind,
        backend_id: str,
        model: str | None,
    ) -> BackendRouteDecision:
        if not model:
            return BackendRouteDecision(
                kind=kind,
                backend_id=backend_id,
                status=RuntimeBackendAvailability.UNAVAILABLE,
                provider="ollama",
                model=model,
                local=True,
                detail="ollama_model_missing",
                requested_model=model,
                keep_alive=self.settings.ollama_keep_alive,
            )

        snapshot = self.ollama_probe.snapshot()
        active_model, last_success_latency_ms = self._ollama_runtime_state(kind)
        runtime_note = self._ollama_runtime_note(kind)
        if not snapshot.reachable:
            return BackendRouteDecision(
                kind=kind,
                backend_id=backend_id,
                status=RuntimeBackendAvailability.UNAVAILABLE,
                provider="ollama",
                model=model,
                local=True,
                detail=snapshot.error or "ollama_unreachable",
                requested_model=model,
                active_model=active_model,
                reachable=False,
                installed=False,
                warm=False,
                keep_alive=self.settings.ollama_keep_alive,
                last_success_latency_ms=last_success_latency_ms or snapshot.latency_ms,
                last_failure_reason=runtime_note.last_failure_reason,
                last_failure_at=runtime_note.last_failure_at,
                last_timeout_seconds=runtime_note.last_timeout_seconds,
                cold_start_retry_used=runtime_note.cold_start_retry_used,
            )
        if model in snapshot.running_models:
            status = RuntimeBackendAvailability.WARM
            detail = "ollama_model_running"
        elif model in snapshot.installed_models:
            status = RuntimeBackendAvailability.CONFIGURED
            detail = "ollama_model_installed_not_running"
        else:
            status = RuntimeBackendAvailability.UNAVAILABLE
            detail = "ollama_model_not_installed"
        return BackendRouteDecision(
            kind=kind,
            backend_id=backend_id,
            status=status,
            provider="ollama",
            model=model,
            local=True,
            detail=detail,
            requested_model=model,
            active_model=active_model or (model if model in snapshot.running_models else None),
            reachable=True,
            installed=model in snapshot.installed_models,
            warm=model in snapshot.running_models,
            keep_alive=self.settings.ollama_keep_alive,
            last_success_latency_ms=last_success_latency_ms or snapshot.latency_ms,
            last_failure_reason=runtime_note.last_failure_reason,
            last_failure_at=runtime_note.last_failure_at,
            last_timeout_seconds=runtime_note.last_timeout_seconds,
            cold_start_retry_used=runtime_note.cold_start_retry_used,
        )

    def _dialogue_engine_for(self, backend_id: str) -> DialogueEngine | None:
        if backend_id == "grsai_chat":
            if not (self.settings.grsai_base_url and self.settings.grsai_model):
                return None
            return GRSAIDialogueEngine(
                api_key=self.settings.grsai_api_key,
                base_url=self.settings.grsai_base_url,
                text_base_url=self.settings.grsai_text_base_url,
                model=self.settings.grsai_model,
                timeout_seconds=self.settings.grsai_timeout_seconds,
            )
        if backend_id == "ollama_text":
            if not (self.settings.ollama_base_url and self._ollama_text_model()):
                return None
            return OllamaDialogueEngine(
                base_url=self.settings.ollama_base_url,
                model=self._ollama_text_model() or "",
                timeout_seconds=self._ollama_timeout_seconds_for(RuntimeBackendKind.TEXT_REASONING),
                cold_start_timeout_seconds=self._ollama_timeout_seconds_for(
                    RuntimeBackendKind.TEXT_REASONING,
                    cold_start=True,
                ),
                keep_alive=self.settings.ollama_keep_alive,
                success_reporter=self._report_ollama_text_success,
                failure_reporter=self._report_ollama_text_failure,
                warm_checker=self._ollama_text_is_warm,
            )
        if backend_id == "rule_based":
            return RuleBasedDialogueEngine()
        return None

    def _embedding_backend_for(self, backend_id: str) -> EmbeddingBackend | None:
        if backend_id == "ollama_embed":
            if not (self.settings.ollama_base_url and self.settings.ollama_embedding_model):
                return None
            return OllamaEmbeddingBackend(
                base_url=self.settings.ollama_base_url,
                model=self.settings.ollama_embedding_model,
                timeout_seconds=self._ollama_timeout_seconds_for(RuntimeBackendKind.EMBEDDINGS),
                success_reporter=self._report_ollama_embedding_success,
            )
        if backend_id == "hash_embed":
            return HashEmbeddingBackend()
        return None

    def _ollama_text_model(self) -> str | None:
        return self.settings.ollama_text_model or self.settings.ollama_model

    def _ollama_vision_model(self) -> str | None:
        return self.settings.ollama_vision_model or self.settings.ollama_model

    def _report_ollama_text_success(self, model: str, latency_ms: float, retry_used: bool = False) -> None:
        self.report_ollama_success(
            kind=RuntimeBackendKind.TEXT_REASONING,
            model=model,
            latency_ms=latency_ms,
            retry_used=retry_used,
        )

    def _report_ollama_text_failure(self, reason: str, timeout_seconds: float | None, retry_used: bool) -> None:
        self.report_ollama_failure(
            kind=RuntimeBackendKind.TEXT_REASONING,
            reason=reason,
            timeout_seconds=timeout_seconds,
            retry_used=retry_used,
        )

    def _report_ollama_vision_success(self, model: str, latency_ms: float, retry_used: bool = False) -> None:
        self.report_ollama_success(
            kind=RuntimeBackendKind.VISION_ANALYSIS,
            model=model,
            latency_ms=latency_ms,
            retry_used=retry_used,
        )

    def _report_ollama_embedding_success(self, model: str, latency_ms: float, retry_used: bool = False) -> None:
        self.report_ollama_success(
            kind=RuntimeBackendKind.EMBEDDINGS,
            model=model,
            latency_ms=latency_ms,
            retry_used=retry_used,
        )

    def _whisper_binary_path(self) -> str | None:
        return resolve_whisper_cpp_binary_path(self.settings)

    def _whisper_model_path(self) -> str | None:
        model_path = resolve_whisper_cpp_model_path(self.settings)
        return str(model_path) if model_path is not None else None

    def _piper_binary_path(self) -> str | None:
        return self.settings.piper_binary or shutil.which("piper")

    def _piper_model_path(self) -> str | None:
        return self.settings.piper_model_path

    def _ollama_runtime_state(self, kind: RuntimeBackendKind) -> tuple[str | None, float | None]:
        note = self._ollama_runtime.get(kind)
        if note is None:
            return None, None
        return note.active_model, note.last_success_latency_ms

    def _ollama_runtime_note(self, kind: RuntimeBackendKind) -> OllamaRuntimeNote:
        return self._ollama_runtime.get(kind, OllamaRuntimeNote())

    def _semantic_vision_decision(self) -> BackendRouteDecision | None:
        for backend_id in backend_candidates_for(self.settings, RuntimeBackendKind.VISION_ANALYSIS):
            if backend_id not in {"multimodal_llm", "ollama_vision"}:
                continue
            decision = self._evaluate_candidate(RuntimeBackendKind.VISION_ANALYSIS, backend_id)
            if decision.status != RuntimeBackendAvailability.UNAVAILABLE:
                return decision
        return None

    def _shared_resident_record(
        self,
        *,
        kind: RuntimeBackendKind,
        model: str | None,
    ) -> LocalModelResidencyRecord | None:
        if not model:
            return None
        for other_kind, other_record in self._model_residency.items():
            if other_kind == kind:
                continue
            if other_record.model == model and other_record.resident:
                return other_record
        return None

    def _ollama_text_is_warm(self) -> bool:
        snapshot = self.ollama_probe.snapshot()
        model = self._ollama_text_model()
        return bool(snapshot.reachable and model and model in snapshot.running_models)

    def _ollama_timeout_seconds_for(
        self,
        kind: RuntimeBackendKind,
        *,
        cold_start: bool = False,
    ) -> float:
        if kind == RuntimeBackendKind.TEXT_REASONING:
            return (
                float(self.settings.ollama_text_cold_start_timeout_seconds)
                if cold_start
                else float(self.settings.ollama_text_timeout_seconds)
            )
        if kind == RuntimeBackendKind.VISION_ANALYSIS:
            return float(self.settings.ollama_vision_timeout_seconds)
        if kind == RuntimeBackendKind.EMBEDDINGS:
            return float(self.settings.ollama_embed_timeout_seconds)
        return float(self.settings.ollama_timeout_seconds)

    def _request_ollama_unload(self, model: str | None) -> bool:
        if not model or not self.settings.ollama_base_url:
            return False
        try:
            with httpx.Client(timeout=min(self._ollama_timeout_seconds_for(RuntimeBackendKind.TEXT_REASONING), 2.0)) as client:
                response = client.post(
                    f"{self.settings.ollama_base_url.rstrip('/')}/api/chat",
                    json={
                        "model": model,
                        "stream": False,
                        "keep_alive": 0,
                        "messages": [{"role": "user", "content": "unload"}],
                        "options": {"temperature": 0.0, "num_predict": 1},
                    },
                )
                response.raise_for_status()
                return True
        except httpx.HTTPError:
            return False

    def _apple_speech_helper_path(self):
        from pathlib import Path

        return Path(__file__).resolve().parents[1] / "desktop" / "native_helpers" / "apple_speech_transcribe.swift"
