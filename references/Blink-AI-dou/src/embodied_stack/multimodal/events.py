from __future__ import annotations

from embodied_stack.shared.models import (
    PerceptionAnnotationInput,
    PerceptionEventType,
    PerceptionObservationType,
    PerceptionProviderMode,
    PerceptionSnapshotSubmitRequest,
    PerceptionTier,
)
from embodied_stack.multimodal.normalization import normalize_engagement_text


PERCEPTION_EVENT_TYPES = tuple(item.value for item in PerceptionEventType)

ENGAGEMENT_LABEL_TO_SCORE = {
    "low": 0.25,
    "medium": 0.55,
    "high": 0.82,
    "engaged": 0.82,
    "disengaged": 0.18,
}


def normalize_engagement(value: float | str | None) -> float | None:
    if value is None:
        return None
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in ENGAGEMENT_LABEL_TO_SCORE:
            return ENGAGEMENT_LABEL_TO_SCORE[lowered]
        try:
            return max(0.0, min(1.0, float(lowered)))
        except ValueError:
            return None
    return max(0.0, min(1.0, float(value)))


def build_scene_annotations(
    *,
    person_present: bool | None = None,
    people_count: int | None = None,
    engagement: float | str | None = None,
    scene_note: str | None = None,
    confidence: float = 0.82,
) -> list[PerceptionAnnotationInput]:
    items: list[PerceptionAnnotationInput] = []
    if person_present is not None:
        items.append(
            PerceptionAnnotationInput(
                observation_type=PerceptionObservationType.PERSON_VISIBILITY,
                bool_value=person_present,
                confidence=confidence,
            )
        )
    if people_count is not None:
        items.append(
            PerceptionAnnotationInput(
                observation_type=PerceptionObservationType.PEOPLE_COUNT,
                number_value=float(max(0, people_count)),
                confidence=confidence,
            )
        )
    engagement_score = normalize_engagement(engagement)
    if engagement_score is not None:
        items.append(
            PerceptionAnnotationInput(
                observation_type=PerceptionObservationType.ENGAGEMENT_ESTIMATE,
                text_value=normalize_engagement_text(None, engagement_score),
                confidence=confidence,
            )
        )
    if scene_note:
        items.append(
            PerceptionAnnotationInput(
                observation_type=PerceptionObservationType.SCENE_SUMMARY,
                text_value=scene_note,
                confidence=confidence,
                metadata={"source": "desktop_scene_note"},
            )
        )
    return items


def build_scene_request(
    *,
    session_id: str | None = None,
    source: str = "desktop_runtime",
    person_present: bool | None = None,
    people_count: int | None = None,
    engagement: float | str | None = None,
    scene_note: str | None = None,
    provider_mode: PerceptionProviderMode = PerceptionProviderMode.MANUAL_ANNOTATIONS,
    tier: PerceptionTier = PerceptionTier.WATCHER,
    trigger_reason: str | None = None,
    metadata: dict[str, object] | None = None,
    publish_events: bool = True,
) -> PerceptionSnapshotSubmitRequest:
    return PerceptionSnapshotSubmitRequest(
        session_id=session_id,
        provider_mode=provider_mode,
        tier=tier,
        trigger_reason=trigger_reason,
        source=source,
        annotations=build_scene_annotations(
            person_present=person_present,
            people_count=people_count,
            engagement=engagement,
            scene_note=scene_note,
        ),
        metadata=dict(metadata or {}),
        publish_events=publish_events,
    )

__all__ = [
    "ENGAGEMENT_LABEL_TO_SCORE",
    "PERCEPTION_EVENT_TYPES",
    "build_scene_annotations",
    "build_scene_request",
    "normalize_engagement",
]
