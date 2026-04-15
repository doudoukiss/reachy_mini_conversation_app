from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from embodied_stack.brain.freshness import DEFAULT_FRESHNESS_POLICY, FreshnessPolicy
from embodied_stack.shared.models import (
    FactFreshness,
    PerceptionSnapshotRecord,
    PerceptionSnapshotStatus,
    SceneClaimKind,
    utc_now,
)


@dataclass(frozen=True)
class SemanticRefreshDecision:
    should_refresh: bool
    reason: str | None
    dialogue_eligible: bool


class SemanticRefreshPolicy:
    def __init__(
        self,
        *,
        min_interval_seconds: float,
        freshness_policy: FreshnessPolicy = DEFAULT_FRESHNESS_POLICY,
    ) -> None:
        self.min_interval_seconds = min_interval_seconds
        self.freshness_policy = freshness_policy

    def snapshot_freshness(self, snapshot: PerceptionSnapshotRecord | None) -> FactFreshness:
        if snapshot is None:
            return FactFreshness.UNKNOWN
        observed_at = snapshot.source_frame.captured_at or snapshot.created_at
        return self.freshness_policy.assessment(
            observed_at=observed_at,
            claim_kind=SceneClaimKind.SEMANTIC_OBSERVATION,
        ).freshness

    def snapshot_dialogue_eligible(self, snapshot: PerceptionSnapshotRecord | None) -> bool:
        if snapshot is None:
            return False
        freshness = self.snapshot_freshness(snapshot)
        return (
            snapshot.tier.value == "semantic"
            and snapshot.status == PerceptionSnapshotStatus.OK
            and not snapshot.limited_awareness
            and self.freshness_policy.dialogue_grounding_eligible(
                claim_kind=SceneClaimKind.SEMANTIC_OBSERVATION,
                freshness=freshness,
                limited_awareness=snapshot.limited_awareness,
            )
        )

    def should_refresh(
        self,
        *,
        refresh_recommended: bool,
        refresh_reason: str | None,
        fresh_semantic_scene_available: bool,
        last_semantic_refresh_at: datetime | None,
        now: datetime | None = None,
    ) -> SemanticRefreshDecision:
        current = now or utc_now()
        if fresh_semantic_scene_available and not refresh_recommended:
            return SemanticRefreshDecision(
                should_refresh=False,
                reason=refresh_reason or "fresh_semantic_scene_available",
                dialogue_eligible=True,
            )
        if not refresh_recommended:
            return SemanticRefreshDecision(
                should_refresh=False,
                reason=refresh_reason or "refresh_not_recommended",
                dialogue_eligible=fresh_semantic_scene_available,
            )
        if last_semantic_refresh_at is None:
            return SemanticRefreshDecision(
                should_refresh=True,
                reason=refresh_reason or "semantic_refresh_missing",
                dialogue_eligible=False,
            )
        due = (current - last_semantic_refresh_at).total_seconds() >= self.min_interval_seconds
        return SemanticRefreshDecision(
            should_refresh=due,
            reason=refresh_reason or ("semantic_refresh_due" if due else "semantic_refresh_throttled"),
            dialogue_eligible=fresh_semantic_scene_available and not due,
        )


__all__ = [
    "SemanticRefreshDecision",
    "SemanticRefreshPolicy",
]
