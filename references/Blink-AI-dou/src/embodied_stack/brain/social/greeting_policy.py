from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from embodied_stack.shared.models import EmbodiedWorldModel


@dataclass(frozen=True)
class GreetingPolicyOutcome:
    policy_name: str = "greeting_policy"
    outcome: str = "idle"
    suppressed_reason: str | None = None


def greet_suppressed_recently(last_greet_at: datetime | None, *, now: datetime, cooldown_seconds: float) -> bool:
    if last_greet_at is None:
        return False
    return now - last_greet_at < timedelta(seconds=cooldown_seconds)


def greeting_suppression_reason(
    *,
    world_model: EmbodiedWorldModel,
    policy_enabled: bool,
    max_people_for_auto_greet: int | None,
    last_greet_at: datetime | None,
    now: datetime,
    cooldown_seconds: float,
) -> GreetingPolicyOutcome:
    if not policy_enabled:
        return GreetingPolicyOutcome(outcome="suppressed", suppressed_reason="auto_greet_disabled_by_site_policy")
    if max_people_for_auto_greet is not None and len(world_model.active_participants_in_view) > max_people_for_auto_greet:
        return GreetingPolicyOutcome(outcome="suppressed", suppressed_reason="auto_greet_suppressed_crowd_policy")
    if greet_suppressed_recently(last_greet_at, now=now, cooldown_seconds=cooldown_seconds):
        return GreetingPolicyOutcome(outcome="suppressed", suppressed_reason="auto_greet_suppressed_recently")
    if (
        world_model.current_speaker_participant_id
        and world_model.attention_target is not None
        and (
            (
                world_model.last_robot_speech_at is not None
                and now - world_model.last_robot_speech_at < timedelta(seconds=cooldown_seconds)
            )
            or (
                world_model.last_user_speech_at is not None
                and now - world_model.last_user_speech_at < timedelta(seconds=cooldown_seconds)
            )
        )
    ):
        return GreetingPolicyOutcome(outcome="suppressed", suppressed_reason="same_participant_already_active")
    if world_model.engagement_state.value == "disengaging" and world_model.engagement_observed_at is not None:
        if now - world_model.engagement_observed_at < timedelta(seconds=cooldown_seconds):
            return GreetingPolicyOutcome(outcome="suppressed", suppressed_reason="recent_disengagement_cooldown")
    return GreetingPolicyOutcome(outcome="greet")


def reengagement_allowed(
    *,
    new_entrant: bool,
    direct_interaction: bool,
    attention_returned: bool,
    due_follow_up: bool,
) -> GreetingPolicyOutcome:
    if new_entrant:
        return GreetingPolicyOutcome(outcome="reengage")
    if direct_interaction:
        return GreetingPolicyOutcome(outcome="reengage")
    if attention_returned:
        return GreetingPolicyOutcome(outcome="reengage")
    if due_follow_up:
        return GreetingPolicyOutcome(outcome="reengage")
    return GreetingPolicyOutcome(outcome="suppressed", suppressed_reason="reengagement_not_triggered")


__all__ = [
    "GreetingPolicyOutcome",
    "greet_suppressed_recently",
    "greeting_suppression_reason",
    "reengagement_allowed",
]
