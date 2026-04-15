from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from embodied_stack.shared.models import (
    PerceptionObservation,
    PerceptionObservationType,
    PerceptionProviderMode,
    PerceptionSourceFrame,
    PerceptionTier,
)


@dataclass(frozen=True)
class NormalizedSnapshotContent:
    observations: list[PerceptionObservation]
    scene_summary: str | None
    device_awareness_constraints: list[str]
    uncertainty_markers: list[str]
    provenance: dict[str, Any]


_ENGAGEMENT_ALIASES = {
    "high": "engaged",
    "engaged": "engaged",
    "focused": "engaged",
    "toward_device": "engaged",
    "medium": "noticing",
    "noticing": "noticing",
    "watching": "noticing",
    "low": "disengaging",
    "disengaging": "disengaging",
    "away": "disengaging",
    "lost": "lost",
    "none": "lost",
    "absent": "lost",
}


def normalize_snapshot_content(
    *,
    observations: list[PerceptionObservation],
    source_frame: PerceptionSourceFrame,
    tier: PerceptionTier,
    provider_mode: PerceptionProviderMode,
    scene_summary: str | None,
    limited_awareness: bool,
    message: str | None,
    metadata: dict[str, Any] | None = None,
) -> NormalizedSnapshotContent:
    normalized = normalize_observations(observations, source_frame=source_frame)
    constraints = _device_constraints(metadata)
    uncertainty_markers = _uncertainty_markers(
        tier=tier,
        limited_awareness=limited_awareness,
        message=message,
        provider_mode=provider_mode,
        metadata=metadata,
    )
    provenance = dict(metadata or {})
    if scene_summary:
        provenance.setdefault("raw_scene_summary", scene_summary)
    provenance.setdefault("normalized_observation_count", len(normalized))
    if tier == PerceptionTier.WATCHER:
        provenance.setdefault("watcher_only", True)
    return NormalizedSnapshotContent(
        observations=normalized,
        scene_summary=(scene_summary or "").strip() or None,
        device_awareness_constraints=constraints,
        uncertainty_markers=uncertainty_markers,
        provenance=provenance,
    )


def normalize_observations(
    observations: list[PerceptionObservation],
    *,
    source_frame: PerceptionSourceFrame,
) -> list[PerceptionObservation]:
    normalized: list[PerceptionObservation] = []
    for item in observations:
        normalized_item = item.model_copy(deep=True)
        normalized_item.source_frame = source_frame
        if normalized_item.text_value is not None:
            normalized_item.text_value = normalized_item.text_value.strip() or None
        if normalized_item.observation_type == PerceptionObservationType.ENGAGEMENT_ESTIMATE:
            normalized_item.text_value = normalize_engagement_text(
                normalized_item.text_value,
                normalized_item.number_value,
            )
        elif normalized_item.observation_type == PerceptionObservationType.PEOPLE_COUNT and normalized_item.number_value is not None:
            normalized_item.number_value = float(max(0, int(round(normalized_item.number_value))))
        elif normalized_item.observation_type == PerceptionObservationType.PERSON_VISIBILITY:
            if normalized_item.bool_value is None and normalized_item.number_value is not None:
                normalized_item.bool_value = normalized_item.number_value > 0
        normalized.append(normalized_item)

    people_count = next(
        (
            int(item.number_value)
            for item in normalized
            if item.observation_type == PerceptionObservationType.PEOPLE_COUNT and item.number_value is not None
        ),
        None,
    )
    if people_count is not None and not any(
        item.observation_type == PerceptionObservationType.PERSON_VISIBILITY
        for item in normalized
    ):
        normalized.append(
            PerceptionObservation(
                observation_type=PerceptionObservationType.PERSON_VISIBILITY,
                bool_value=people_count > 0,
                confidence=next(
                    (
                        item.confidence
                        for item in normalized
                        if item.observation_type == PerceptionObservationType.PEOPLE_COUNT
                    ),
                    None,
                )
                or normalized[0].confidence,
                source_frame=source_frame,
                metadata={"derived_from": "people_count"},
            )
        )
    return normalized


def normalize_engagement_text(text_value: str | None, number_value: float | None) -> str | None:
    if text_value:
        lowered = text_value.strip().lower()
        if lowered in _ENGAGEMENT_ALIASES:
            return _ENGAGEMENT_ALIASES[lowered]
        try:
            number_value = float(lowered)
        except ValueError:
            return lowered or None
    if number_value is None:
        return None
    bounded = max(0.0, min(1.0, float(number_value)))
    if bounded >= 0.75:
        return "engaged"
    if bounded >= 0.45:
        return "noticing"
    if bounded >= 0.2:
        return "disengaging"
    return "lost"


def _device_constraints(metadata: dict[str, Any] | None) -> list[str]:
    if not isinstance(metadata, dict):
        return []
    raw = metadata.get("device_awareness_constraints") or metadata.get("observer_capability_limits") or []
    if isinstance(raw, list):
        return [str(item).strip() for item in raw if str(item).strip()]
    if isinstance(raw, str) and raw.strip():
        return [raw.strip()]
    return []


def _uncertainty_markers(
    *,
    tier: PerceptionTier,
    limited_awareness: bool,
    message: str | None,
    provider_mode: PerceptionProviderMode,
    metadata: dict[str, Any] | None,
) -> list[str]:
    markers: list[str] = []
    if tier == PerceptionTier.WATCHER:
        markers.append("watcher_only_scene_facts")
    if limited_awareness:
        markers.append(message or f"{provider_mode.value}_limited_awareness")
    constraints = _device_constraints(metadata)
    markers.extend(item for item in constraints if item not in markers)
    return markers


__all__ = [
    "NormalizedSnapshotContent",
    "normalize_engagement_text",
    "normalize_observations",
    "normalize_snapshot_content",
]
