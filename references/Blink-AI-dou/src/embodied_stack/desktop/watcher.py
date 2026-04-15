from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import datetime

from embodied_stack.shared.models import (
    EnvironmentState,
    WatcherEngagementShift,
    WatcherMotionState,
    WatcherPresenceState,
    utc_now,
)

try:  # pragma: no cover - optional dependency
    import cv2  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    cv2 = None

try:  # pragma: no cover - optional dependency
    import numpy as np  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    np = None

try:  # pragma: no cover - optional dependency
    import mediapipe as mp  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    mp = None


@dataclass(frozen=True)
class SceneObservationEvent:
    observed_at: datetime
    backend: str
    change_score: float
    motion_changed: bool
    presence_state: WatcherPresenceState = WatcherPresenceState.UNKNOWN
    motion_state: WatcherMotionState = WatcherMotionState.UNKNOWN
    new_entrant: bool = False
    attention_target_hint: str | None = None
    engagement_shift_hint: WatcherEngagementShift = WatcherEngagementShift.UNKNOWN
    signal_confidence: float | None = None
    person_present: bool | None = None
    people_count_estimate: int | None = None
    person_transition: str | None = None
    attention_state: str | None = None
    attention_toward_device_score: float | None = None
    environment_state: EnvironmentState = EnvironmentState.UNKNOWN
    semantic_refresh_recommended: bool = False
    refresh_reason: str | None = None
    capability_limits: tuple[str, ...] = ()
    source_kind: str | None = None


def _decode_image_bytes(image_data_url: str) -> bytes:
    if "," not in image_data_url:
        return b""
    encoded = image_data_url.split(",", 1)[1]
    return base64.b64decode(encoded)


class SceneObserverEngine:
    def __init__(self, *, change_threshold: float) -> None:
        self.change_threshold = change_threshold
        self._previous_bytes: bytes | None = None
        self._previous_person_present: bool | None = None
        self._previous_attention_state: str | None = None
        self._face_detection = None
        if mp is not None:  # pragma: no branch - optional runtime path
            self._face_detection = mp.solutions.face_detection.FaceDetection(
                model_selection=0,
                min_detection_confidence=0.5,
            )

    @property
    def supports_mediapipe(self) -> bool:
        return self._face_detection is not None

    @property
    def backend_name(self) -> str:
        if cv2 is not None and np is not None and self._face_detection is not None:
            return "opencv_frame_diff+mediapipe"
        if cv2 is not None and np is not None:
            return "opencv_frame_diff"
        return "frame_diff_fallback"

    def observe(
        self,
        *,
        image_data_url: str,
        source_kind: str | None = None,
        observed_at: datetime | None = None,
    ) -> SceneObservationEvent:
        frame_bytes = _decode_image_bytes(image_data_url)
        now = observed_at or utc_now()
        change_score = self._change_score(frame_bytes)
        motion_changed = change_score >= self.change_threshold
        person_present, people_count_estimate, attention_state, attention_toward_device_score = self._person_and_attention(frame_bytes)
        person_transition = None
        if person_present is not None and self._previous_person_present is not None and person_present != self._previous_person_present:
            person_transition = "entered" if person_present else "left"
        elif person_present is not None and self._previous_person_present is None:
            person_transition = "entered" if person_present else None
        attention_changed = (
            attention_state is not None
            and self._previous_attention_state is not None
            and attention_state != self._previous_attention_state
        )
        refresh_reason = None
        if person_transition == "entered":
            refresh_reason = "new_arrival"
        elif person_transition == "left":
            refresh_reason = "departure"
        elif attention_changed:
            refresh_reason = "attention_changed"
        elif motion_changed:
            refresh_reason = "scene_changed"

        presence_state = self._presence_state(person_present)
        motion_state = WatcherMotionState.CHANGED if motion_changed else WatcherMotionState.STEADY
        engagement_shift_hint = self._engagement_shift_hint(
            person_transition=person_transition,
            attention_state=attention_state,
            attention_changed=attention_changed,
        )
        event = SceneObservationEvent(
            observed_at=now,
            backend=self.backend_name,
            change_score=change_score,
            motion_changed=motion_changed,
            presence_state=presence_state,
            motion_state=motion_state,
            new_entrant=person_transition == "entered",
            attention_target_hint=self._attention_target_hint(attention_state),
            engagement_shift_hint=engagement_shift_hint,
            signal_confidence=self._signal_confidence(
                person_present=person_present,
                attention_toward_device_score=attention_toward_device_score,
                motion_changed=motion_changed,
            ),
            person_present=person_present,
            people_count_estimate=people_count_estimate,
            person_transition=person_transition,
            attention_state=attention_state,
            attention_toward_device_score=attention_toward_device_score,
            environment_state=self._environment_state(
                people_count_estimate=people_count_estimate,
                change_score=change_score,
            ),
            semantic_refresh_recommended=bool(motion_changed or person_transition or attention_changed),
            refresh_reason=refresh_reason,
            capability_limits=tuple(self._capability_limits()),
            source_kind=source_kind,
        )
        self._previous_bytes = frame_bytes
        if person_present is not None:
            self._previous_person_present = person_present
        if attention_state is not None:
            self._previous_attention_state = attention_state
        return event

    def _change_score(self, frame_bytes: bytes) -> float:
        previous = self._previous_bytes
        if not previous or not frame_bytes:
            return 1.0
        if cv2 is not None and np is not None:
            previous_frame = self._decode_frame(previous)
            current_frame = self._decode_frame(frame_bytes)
            if previous_frame is not None and current_frame is not None:
                if previous_frame.shape != current_frame.shape:
                    return 1.0
                diff = cv2.absdiff(previous_frame, current_frame)
                return round(float(diff.mean()) / 255.0, 4)
        sample_count = max(1, min(len(previous), len(frame_bytes)) // 2048)
        previous_sample = previous[::sample_count]
        current_sample = frame_bytes[::sample_count]
        pair_count = min(len(previous_sample), len(current_sample))
        if pair_count == 0:
            return 1.0
        total = sum(
            abs(int(left) - int(right)) / 255.0
            for left, right in zip(previous_sample[:pair_count], current_sample[:pair_count], strict=True)
        )
        length_penalty = abs(len(previous) - len(frame_bytes)) / max(len(previous), len(frame_bytes), 1)
        return round(min(1.0, (total / pair_count) + length_penalty), 4)

    def _person_and_attention(self, frame_bytes: bytes) -> tuple[bool | None, int | None, str | None, float | None]:
        if self._face_detection is None or cv2 is None or np is None:
            return None, None, None, None
        frame = self._decode_frame(frame_bytes, color=True)
        if frame is None:
            return None, None, None, None
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        result = self._face_detection.process(rgb)
        detections = list(result.detections or [])
        if not detections:
            return False, 0, "unknown", 0.0
        bbox = detections[0].location_data.relative_bounding_box
        center_x = bbox.xmin + (bbox.width / 2.0)
        attention_state = "toward_device" if 0.3 <= center_x <= 0.7 else "away"
        attention_score = 0.85 if attention_state == "toward_device" else 0.25
        return True, len(detections), attention_state, attention_score

    def _environment_state(
        self,
        *,
        people_count_estimate: int | None,
        change_score: float,
    ) -> EnvironmentState:
        if people_count_estimate is not None and people_count_estimate >= 2:
            return EnvironmentState.BUSY
        if change_score >= max(0.6, self.change_threshold * 2.0):
            return EnvironmentState.BUSY
        if people_count_estimate == 0:
            return EnvironmentState.QUIET
        if people_count_estimate == 1:
            return EnvironmentState.QUIET
        return EnvironmentState.UNKNOWN

    def _capability_limits(self) -> list[str]:
        limits: list[str] = []
        if cv2 is None or np is None:
            limits.append("opencv_frame_diff_unavailable")
        if self._face_detection is None:
            limits.append("person_attention_detection_unavailable")
        return limits

    @staticmethod
    def _presence_state(person_present: bool | None) -> WatcherPresenceState:
        if person_present is True:
            return WatcherPresenceState.PERSON_PRESENT
        if person_present is False:
            return WatcherPresenceState.NO_PERSON
        return WatcherPresenceState.UNKNOWN

    @staticmethod
    def _attention_target_hint(attention_state: str | None) -> str | None:
        if attention_state == "toward_device":
            return "device"
        if attention_state == "away":
            return "away_from_device"
        return None

    @staticmethod
    def _engagement_shift_hint(
        *,
        person_transition: str | None,
        attention_state: str | None,
        attention_changed: bool,
    ) -> WatcherEngagementShift:
        if person_transition == "entered":
            return WatcherEngagementShift.ENGAGING
        if person_transition == "left":
            return WatcherEngagementShift.DISENGAGING
        if attention_changed and attention_state == "toward_device":
            return WatcherEngagementShift.ENGAGING
        if attention_changed and attention_state == "away":
            return WatcherEngagementShift.DISENGAGING
        if attention_state is not None:
            return WatcherEngagementShift.STABLE
        return WatcherEngagementShift.UNKNOWN

    @staticmethod
    def _signal_confidence(
        *,
        person_present: bool | None,
        attention_toward_device_score: float | None,
        motion_changed: bool,
    ) -> float | None:
        values: list[float] = []
        if person_present is not None:
            values.append(0.8 if person_present else 0.65)
        if attention_toward_device_score is not None:
            values.append(float(attention_toward_device_score))
        if motion_changed:
            values.append(0.7)
        if not values:
            return None
        return round(sum(values) / len(values), 2)

    def _decode_frame(self, frame_bytes: bytes, *, color: bool = False):
        if cv2 is None or np is None:
            return None
        mode = cv2.IMREAD_COLOR if color else cv2.IMREAD_GRAYSCALE
        return cv2.imdecode(np.frombuffer(frame_bytes, dtype=np.uint8), mode)


__all__ = [
    "SceneObservationEvent",
    "SceneObserverEngine",
]
