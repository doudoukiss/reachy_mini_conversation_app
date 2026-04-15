from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from embodied_stack.brain.perception.semantic_refresh import SemanticRefreshPolicy
from embodied_stack.brain.social.attract_mode_policy import proactive_eligible, suppressed_reason
from embodied_stack.desktop.watcher import SceneObservationEvent, SceneObserverEngine
from embodied_stack.shared.models import CompanionTriggerDecision, ShiftSupervisorSnapshot, utc_now


@dataclass(frozen=True)
class TriggerEvaluation:
    decision: CompanionTriggerDecision
    reason: str
    proactive_eligible: bool
    suppressed_reason: str | None = None


class CompanionTriggerEngine:
    def __init__(
        self,
        *,
        attract_prompt_delay_seconds: float,
        semantic_refresh_min_interval_seconds: float,
    ) -> None:
        self.attract_prompt_delay_seconds = attract_prompt_delay_seconds
        self.semantic_refresh_min_interval_seconds = semantic_refresh_min_interval_seconds
        self.semantic_refresh_policy = SemanticRefreshPolicy(
            min_interval_seconds=semantic_refresh_min_interval_seconds,
        )

    def evaluate(
        self,
        *,
        observer_event: SceneObservationEvent | None,
        shift_snapshot: ShiftSupervisorSnapshot,
        fallback_active: bool,
        semantic_provider_available: bool,
        fresh_semantic_scene_available: bool,
        last_semantic_refresh_at: datetime | None,
        now: datetime | None = None,
    ) -> TriggerEvaluation:
        current = now or utc_now()
        proactive_ready = proactive_eligible(
            shift_snapshot=shift_snapshot,
            now=current,
            attract_prompt_delay_seconds=self.attract_prompt_delay_seconds,
        )
        due_follow_up = bool(
            shift_snapshot.follow_up_deadline_at
            and shift_snapshot.follow_up_deadline_at <= current
        )
        due_scheduled_prompt = bool(
            shift_snapshot.next_scheduled_prompt_at
            and shift_snapshot.next_scheduled_prompt_at <= current
        )
        if fallback_active and not due_follow_up and not due_scheduled_prompt:
            return TriggerEvaluation(
                decision=CompanionTriggerDecision.SAFE_IDLE,
                reason="fallback_active",
                proactive_eligible=False,
                suppressed_reason="fallback_active",
            )
        if due_follow_up or due_scheduled_prompt:
            return TriggerEvaluation(
                decision=CompanionTriggerDecision.ASK_FOLLOW_UP,
                reason="scheduled_prompt_due" if due_scheduled_prompt else "follow_up_due",
                proactive_eligible=proactive_ready,
                suppressed_reason=None
                if proactive_ready
                else suppressed_reason(
                    shift_snapshot=shift_snapshot,
                    now=current,
                    attract_prompt_delay_seconds=self.attract_prompt_delay_seconds,
                ),
            )
        if observer_event is None:
            return TriggerEvaluation(
                decision=CompanionTriggerDecision.WAIT,
                reason="no_observer_event",
                proactive_eligible=proactive_ready,
                suppressed_reason=None
                if proactive_ready
                else suppressed_reason(
                    shift_snapshot=shift_snapshot,
                    now=current,
                    attract_prompt_delay_seconds=self.attract_prompt_delay_seconds,
                ),
            )
        if observer_event.person_transition == "entered":
            if not semantic_provider_available:
                return TriggerEvaluation(
                    decision=CompanionTriggerDecision.OBSERVE_ONLY,
                    reason="person_entered_without_semantic_provider",
                    proactive_eligible=False,
                    suppressed_reason="semantic_provider_unavailable",
                )
            refresh_decision = self._refresh_decision(
                current=current,
                fresh_semantic_scene_available=fresh_semantic_scene_available,
                observer_event=observer_event,
                last_semantic_refresh_at=last_semantic_refresh_at,
            )
            if refresh_decision.should_refresh:
                return TriggerEvaluation(
                    decision=CompanionTriggerDecision.REFRESH_SCENE,
                    reason=(
                        "person_entered_scene_refresh"
                        if observer_event.person_transition == "entered"
                        else refresh_decision.reason or "person_entered_scene_refresh"
                    ),
                    proactive_eligible=proactive_ready,
                )
            if proactive_ready:
                return TriggerEvaluation(
                    decision=CompanionTriggerDecision.SPEAK_NOW,
                    reason="person_entered_with_fresh_scene",
                    proactive_eligible=True,
                )
        refresh_decision = self._refresh_decision(
            current=current,
            fresh_semantic_scene_available=fresh_semantic_scene_available,
            observer_event=observer_event,
            last_semantic_refresh_at=last_semantic_refresh_at,
        )
        if refresh_decision.should_refresh:
            return TriggerEvaluation(
                decision=CompanionTriggerDecision.REFRESH_SCENE,
                reason=refresh_decision.reason or "observer_change_requires_refresh",
                proactive_eligible=proactive_ready,
            )
        if observer_event.motion_changed:
            return TriggerEvaluation(
                decision=CompanionTriggerDecision.OBSERVE_ONLY,
                reason="motion_changed",
                proactive_eligible=proactive_ready,
                suppressed_reason=None
                if proactive_ready
                else suppressed_reason(
                    shift_snapshot=shift_snapshot,
                    now=current,
                    attract_prompt_delay_seconds=self.attract_prompt_delay_seconds,
                ),
            )
        return TriggerEvaluation(
            decision=CompanionTriggerDecision.WAIT,
            reason="idle",
            proactive_eligible=proactive_ready,
            suppressed_reason=None
            if proactive_ready
            else suppressed_reason(
                shift_snapshot=shift_snapshot,
                now=current,
                attract_prompt_delay_seconds=self.attract_prompt_delay_seconds,
            ),
        )

    def _refresh_decision(
        self,
        *,
        current: datetime,
        fresh_semantic_scene_available: bool,
        observer_event: SceneObservationEvent,
        last_semantic_refresh_at: datetime | None,
    ):
        return self.semantic_refresh_policy.should_refresh(
            refresh_recommended=observer_event.semantic_refresh_recommended,
            refresh_reason=observer_event.refresh_reason,
            fresh_semantic_scene_available=fresh_semantic_scene_available,
            last_semantic_refresh_at=last_semantic_refresh_at,
            now=current,
        )


__all__ = [
    "CompanionTriggerEngine",
    "SceneObservationEvent",
    "SceneObserverEngine",
    "TriggerEvaluation",
]
