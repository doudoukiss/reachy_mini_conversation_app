from __future__ import annotations

from embodied_stack.body.presence_shell import build_character_presence_shell
from embodied_stack.shared.contracts import (
    CompanionPresenceState,
    CompanionPresenceStatus,
    CompanionVoiceLoopState,
    CompanionVoiceLoopStatus,
    FallbackState,
    InitiativeDecision,
    InitiativeStage,
    InitiativeStatus,
    RelationshipContinuityStatus,
)


def test_presence_shell_maps_listening_to_attentive_semantics() -> None:
    shell = build_character_presence_shell(
        presence_status=CompanionPresenceStatus(state=CompanionPresenceState.LISTENING, message="listening"),
        voice_status=CompanionVoiceLoopStatus(state=CompanionVoiceLoopState.CAPTURING),
        initiative_status=InitiativeStatus(),
        relationship_status=RelationshipContinuityStatus(known_user=True, returning_user=True),
        fallback_state=FallbackState(),
    )

    assert shell.surface_state == "listening"
    assert shell.expression_name == "listen_attentively"
    assert shell.gaze_target == "look_at_user"
    assert shell.listening_active is True
    assert shell.warmth >= 0.7


def test_presence_shell_marks_thinking_as_curious_when_initiative_is_active() -> None:
    shell = build_character_presence_shell(
        presence_status=CompanionPresenceStatus(
            state=CompanionPresenceState.THINKING_FAST,
            last_user_text_preview="Can you check the open reminders and tell me what matters first?",
            slow_path_active=True,
        ),
        voice_status=CompanionVoiceLoopStatus(state=CompanionVoiceLoopState.THINKING),
        initiative_status=InitiativeStatus(current_stage=InitiativeStage.SCORE, last_decision=InitiativeDecision.ASK),
        relationship_status=RelationshipContinuityStatus(open_follow_ups=["return to the planning thread"]),
        fallback_state=FallbackState(),
    )

    assert shell.surface_state == "thinking"
    assert shell.expression_name == "thinking"
    assert shell.gesture_name == "tilt_curious"
    assert shell.curiosity >= 0.6
    assert shell.slow_path_active is True


def test_presence_shell_marks_recent_interruption() -> None:
    shell = build_character_presence_shell(
        presence_status=CompanionPresenceStatus(state=CompanionPresenceState.REENGAGING, interruption_count=1),
        voice_status=CompanionVoiceLoopStatus(
            state=CompanionVoiceLoopState.INTERRUPTED,
            interruption_count=1,
        ),
        initiative_status=InitiativeStatus(),
        relationship_status=RelationshipContinuityStatus(),
        fallback_state=FallbackState(),
    )

    assert shell.surface_state == "interrupted"
    assert shell.interruption_active is True
    assert shell.gesture_name == "blink_soft"
    assert shell.animation_name is None


def test_presence_shell_enters_safe_idle_when_runtime_is_degraded() -> None:
    shell = build_character_presence_shell(
        presence_status=CompanionPresenceStatus(
            state=CompanionPresenceState.DEGRADED,
            degraded_reason="microphone_unavailable",
        ),
        voice_status=CompanionVoiceLoopStatus(state=CompanionVoiceLoopState.DEGRADED_TYPED),
        initiative_status=InitiativeStatus(),
        relationship_status=RelationshipContinuityStatus(known_user=True),
        fallback_state=FallbackState(active=True, safe_idle_active=True),
    )

    assert shell.surface_state == "degraded"
    assert shell.expression_name == "safe_idle"
    assert shell.animation_name == "recover_neutral"
    assert "fallback:active" in shell.source_signals
