from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from embodied_stack.shared.models import (
    AttentionTargetRecord,
    AttentionTargetType,
    FactFreshness,
    PerceptionConfidence,
    PerceptionTier,
    SceneClaimKind,
    SemanticQualityClass,
    utc_now,
)


@dataclass(frozen=True)
class AttentionDecision:
    target: AttentionTargetRecord
    likely_speaker_participant_id: str | None = None
    speaker_source: str | None = None


def build_attention_decision(
    *,
    target_type: AttentionTargetType,
    target_label: str,
    confidence: PerceptionConfidence,
    ttl_seconds: float,
    rationale: str,
    provenance: list[str] | None = None,
    source_tier: PerceptionTier = PerceptionTier.WATCHER,
    claim_kind: SceneClaimKind = SceneClaimKind.WATCHER_HINT,
    likely_speaker_participant_id: str | None = None,
    speaker_source: str | None = None,
) -> AttentionDecision:
    now = utc_now()
    return AttentionDecision(
        target=AttentionTargetRecord(
            target_type=target_type,
            target_label=target_label,
            confidence=confidence,
            claim_kind=claim_kind,
            quality_class=(
                SemanticQualityClass(confidence.label)
                if confidence.label in SemanticQualityClass._value2member_map_
                else None
            ),
            observed_at=now,
            expires_at=now + timedelta(seconds=ttl_seconds),
            freshness=FactFreshness.FRESH,
            provenance=list(provenance or []),
            rationale=rationale,
            source_tier=source_tier,
        ),
        likely_speaker_participant_id=likely_speaker_participant_id,
        speaker_source=speaker_source,
    )


__all__ = ["AttentionDecision", "build_attention_decision"]
