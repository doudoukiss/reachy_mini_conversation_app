from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from embodied_stack.shared.models import FactFreshness, PerceptionTier, SceneClaimKind, utc_now


@dataclass(frozen=True)
class FreshnessWindow:
    ttl_seconds: float
    fresh_window_seconds: float


@dataclass(frozen=True)
class FreshnessAssessment:
    freshness: FactFreshness
    age_seconds: float | None
    expires_in_seconds: float | None


DEFAULT_WATCHER_HINT_WINDOW = FreshnessWindow(ttl_seconds=10.0, fresh_window_seconds=10.0)
DEFAULT_SPEAKER_HYPOTHESIS_WINDOW = FreshnessWindow(ttl_seconds=12.0, fresh_window_seconds=12.0)
DEFAULT_ATTENTION_WINDOW = FreshnessWindow(ttl_seconds=12.0, fresh_window_seconds=12.0)
DEFAULT_ENGAGEMENT_WINDOW = FreshnessWindow(ttl_seconds=15.0, fresh_window_seconds=15.0)
DEFAULT_SEMANTIC_WINDOW = FreshnessWindow(ttl_seconds=45.0, fresh_window_seconds=15.0)
DEFAULT_OPERATOR_ANNOTATION_WINDOW = FreshnessWindow(ttl_seconds=300.0, fresh_window_seconds=15.0)


class FreshnessPolicy:
    watcher_hint_window = DEFAULT_WATCHER_HINT_WINDOW
    speaker_hypothesis_window = DEFAULT_SPEAKER_HYPOTHESIS_WINDOW
    attention_window = DEFAULT_ATTENTION_WINDOW
    engagement_window = DEFAULT_ENGAGEMENT_WINDOW
    semantic_window = DEFAULT_SEMANTIC_WINDOW
    operator_annotation_window = DEFAULT_OPERATOR_ANNOTATION_WINDOW

    def expires_at(
        self,
        observed_at: datetime,
        *,
        claim_kind: SceneClaimKind,
    ) -> datetime | None:
        ttl_seconds = self.window_for_claim_kind(claim_kind).ttl_seconds
        if ttl_seconds <= 0:
            return None
        return observed_at + timedelta(seconds=ttl_seconds)

    def assessment(
        self,
        *,
        observed_at: datetime | None,
        now: datetime | None = None,
        expires_at: datetime | None = None,
        claim_kind: SceneClaimKind = SceneClaimKind.SEMANTIC_OBSERVATION,
    ) -> FreshnessAssessment:
        if observed_at is None:
            return FreshnessAssessment(
                freshness=FactFreshness.UNKNOWN,
                age_seconds=None,
                expires_in_seconds=None,
            )
        current = now or utc_now()
        age_seconds = round(max(0.0, (current - observed_at).total_seconds()), 2)
        window = self.window_for_claim_kind(claim_kind)
        if expires_at is not None:
            expires_in_seconds = round((expires_at - current).total_seconds(), 2)
            if expires_in_seconds < 0:
                return FreshnessAssessment(
                    freshness=FactFreshness.EXPIRED,
                    age_seconds=age_seconds,
                    expires_in_seconds=0.0,
                )
        else:
            expires_in_seconds = round(max(0.0, window.ttl_seconds - age_seconds), 2)

        if age_seconds <= window.fresh_window_seconds:
            freshness = FactFreshness.FRESH
        elif age_seconds <= window.ttl_seconds:
            freshness = FactFreshness.AGING
        else:
            freshness = FactFreshness.STALE
        return FreshnessAssessment(
            freshness=freshness,
            age_seconds=age_seconds,
            expires_in_seconds=max(0.0, expires_in_seconds) if expires_in_seconds is not None else None,
        )

    def dialogue_grounding_eligible(
        self,
        *,
        claim_kind: SceneClaimKind,
        freshness: FactFreshness,
        limited_awareness: bool,
        source_tier: PerceptionTier | None = None,
    ) -> bool:
        if limited_awareness:
            return False
        if freshness in {FactFreshness.STALE, FactFreshness.EXPIRED, FactFreshness.UNKNOWN}:
            return False
        if claim_kind == SceneClaimKind.MEMORY_ASSUMPTION:
            return False
        if claim_kind == SceneClaimKind.WATCHER_HINT:
            return False
        if claim_kind == SceneClaimKind.OPERATOR_ANNOTATION:
            return True
        if source_tier is not None and source_tier != PerceptionTier.SEMANTIC:
            return False
        return True

    def window_for_claim_kind(self, claim_kind: SceneClaimKind) -> FreshnessWindow:
        if claim_kind == SceneClaimKind.WATCHER_HINT:
            return self.watcher_hint_window
        if claim_kind == SceneClaimKind.OPERATOR_ANNOTATION:
            return self.operator_annotation_window
        if claim_kind == SceneClaimKind.MEMORY_ASSUMPTION:
            return FreshnessWindow(ttl_seconds=0.0, fresh_window_seconds=0.0)
        return self.semantic_window


DEFAULT_FRESHNESS_POLICY = FreshnessPolicy()


__all__ = [
    "DEFAULT_ATTENTION_WINDOW",
    "DEFAULT_ENGAGEMENT_WINDOW",
    "DEFAULT_FRESHNESS_POLICY",
    "DEFAULT_OPERATOR_ANNOTATION_WINDOW",
    "DEFAULT_SEMANTIC_WINDOW",
    "DEFAULT_SPEAKER_HYPOTHESIS_WINDOW",
    "DEFAULT_WATCHER_HINT_WINDOW",
    "FreshnessAssessment",
    "FreshnessPolicy",
    "FreshnessWindow",
]
