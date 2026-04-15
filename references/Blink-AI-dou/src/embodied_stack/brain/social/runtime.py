from __future__ import annotations

from embodied_stack.shared.models import (
    EmbodiedWorldModel,
    ExecutiveDecisionRecord,
    ExecutiveDecisionType,
    FactFreshness,
    InteractionExecutiveState,
    SocialRuntimeMode,
)


def social_mode_for_event(
    *,
    event_type: str,
    limited_awareness: bool,
    scene_freshness: FactFreshness = FactFreshness.UNKNOWN,
) -> SocialRuntimeMode:
    if limited_awareness or scene_freshness in {FactFreshness.STALE, FactFreshness.EXPIRED}:
        return SocialRuntimeMode.DEGRADED_AWARENESS
    if event_type in {"person_detected", "person_visible"}:
        return SocialRuntimeMode.GREETING
    if event_type == "speech_transcript":
        return SocialRuntimeMode.LISTENING
    if event_type in {"low_battery", "heartbeat"}:
        return SocialRuntimeMode.SAFE_IDLE
    return SocialRuntimeMode.MONITORING


def social_mode_for_response(
    *,
    world_model: EmbodiedWorldModel,
    intent: str,
    decisions: list[ExecutiveDecisionRecord],
    response_has_speech: bool,
) -> SocialRuntimeMode:
    decision_types = {item.decision_type for item in decisions}
    if world_model.perception_limited_awareness or world_model.scene_freshness in {FactFreshness.STALE, FactFreshness.EXPIRED}:
        if any(item.policy_outcome in {"uncertainty_admission", "stale_scene_suppressed"} for item in decisions):
            return SocialRuntimeMode.DEGRADED_AWARENESS
        if world_model.perception_limited_awareness:
            return SocialRuntimeMode.DEGRADED_AWARENESS
    if ExecutiveDecisionType.FORCE_SAFE_IDLE in decision_types:
        return SocialRuntimeMode.SAFE_IDLE
    if ExecutiveDecisionType.ESCALATE_TO_HUMAN in decision_types or intent.startswith("operator_handoff"):
        return SocialRuntimeMode.OPERATOR_HANDOFF
    if any(item.policy_name == "greeting_policy" and item.policy_outcome == "greeted" for item in decisions):
        return SocialRuntimeMode.GREETING
    if ExecutiveDecisionType.AUTO_GREET in decision_types:
        return SocialRuntimeMode.GREETING
    if ExecutiveDecisionType.KEEP_LISTENING in decision_types:
        return SocialRuntimeMode.LISTENING
    if ExecutiveDecisionType.DEFER_REPLY in decision_types:
        return SocialRuntimeMode.FOLLOW_UP_WAITING
    if response_has_speech:
        return SocialRuntimeMode.SPEAKING
    if world_model.turn_state == InteractionExecutiveState.THINKING:
        return SocialRuntimeMode.THINKING
    return SocialRuntimeMode.MONITORING


__all__ = [
    "social_mode_for_event",
    "social_mode_for_response",
]
