from __future__ import annotations

import time

from embodied_stack.brain.presence import PresenceRuntime
from embodied_stack.config import Settings
from embodied_stack.shared.models import CompanionPresenceState


def _settings(**overrides) -> Settings:
    return Settings(
        _env_file=None,
        blink_fast_presence_ack_delay_seconds=0.01,
        blink_fast_presence_tool_delay_seconds=0.03,
        **overrides,
    )


def test_presence_runtime_runs_fast_and_slow_loop_states() -> None:
    history: list[dict[str, object]] = []
    runtime = PresenceRuntime(
        settings=_settings(),
        transition_callback=lambda _status, entry: history.append(entry),
    )

    runtime.begin_turn(
        session_id="presence-unit",
        input_text="Can you check the camera feed?",
        source="local_companion_typed",
        listening=False,
    )
    time.sleep(0.05)
    runtime.begin_reply(
        session_id="presence-unit",
        reply_text="I can see the front desk sign from here.",
        audible=False,
    )
    summary = runtime.finish_turn(
        session_id="presence-unit",
        reply_text="I can see the front desk sign from here.",
        spoken=False,
    )

    states = [item["state"] for item in history]

    assert states[:3] == ["thinking_fast", "acknowledging", "tool_working"]
    assert "reengaging" in states
    assert states[-1] == "idle"
    assert summary.acknowledged is True
    assert summary.tool_working is True
    assert runtime.status().state == CompanionPresenceState.IDLE
