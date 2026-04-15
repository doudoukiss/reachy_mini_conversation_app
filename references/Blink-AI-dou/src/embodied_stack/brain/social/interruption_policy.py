from __future__ import annotations

from datetime import datetime, timedelta

from embodied_stack.shared.models import EmbodiedWorldModel, InteractionExecutiveState


def is_recent_interrupt(world_model: EmbodiedWorldModel, *, now: datetime, interruption_window_seconds: float) -> bool:
    if world_model.turn_state != InteractionExecutiveState.RESPONDING:
        return False
    if world_model.last_robot_speech_at is None:
        return False
    return now - world_model.last_robot_speech_at <= timedelta(seconds=interruption_window_seconds)


def should_keep_listening(lowered: str) -> bool:
    phrases = {
        "wait",
        "hold on",
        "one sec",
        "one second",
        "just a second",
        "hang on",
        "uh",
        "um",
        "hmm",
        "still looking",
        "let me think",
    }
    return lowered in phrases


__all__ = [
    "is_recent_interrupt",
    "should_keep_listening",
]
