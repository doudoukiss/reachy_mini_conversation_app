"""Tests for the robot-brain runtime wrapper."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from reachy_mini_conversation_app.main import build_robot_app_context
from reachy_mini_conversation_app.robot_brain.adapters.mock_adapter import MockRobotAdapter
from reachy_mini_conversation_app.robot_brain.runtime import RobotBrainRuntime


@pytest.mark.asyncio
async def test_runtime_wraps_adapter_and_records_results() -> None:
    """The runtime should normalize actions and update its state store."""
    runtime = RobotBrainRuntime(MockRobotAdapter(), default_mode="mock")

    capabilities = await runtime.get_capabilities()
    result = await runtime.execute_action("set_persistent_state", args={"state": "friendly"})
    neutral_result = await runtime.go_neutral()

    assert capabilities.backend == "mock"
    assert result.status == "completed"
    assert result.action_id
    assert runtime.state_store.state is not None
    assert runtime.state_store.state.persistent_state == "neutral"
    assert neutral_result.summary == "Returned to neutral mock state."
    assert len(runtime.state_store.action_journal) == 2


def test_build_robot_app_context_supports_mock_backend_without_reachy(monkeypatch: pytest.MonkeyPatch) -> None:
    """Mock startup should build a context without trying to connect to Reachy."""
    sentinel_runtime = object()
    logger = MagicMock()
    args = SimpleNamespace(
        gradio=False,
        no_camera=False,
        head_tracker=None,
        robot_name=None,
    )

    monkeypatch.setattr("reachy_mini_conversation_app.main.build_robot_runtime", lambda: sentinel_runtime)
    monkeypatch.setattr("reachy_mini_conversation_app.main.ReachyMini", MagicMock(side_effect=AssertionError("should not connect")))

    from reachy_mini_conversation_app.config import config

    monkeypatch.setattr(config, "ROBOT_BACKEND", "mock")
    context = build_robot_app_context(args, logger)

    assert context.robot is None
    assert context.robot_runtime is sentinel_runtime
    assert context.is_simulation is True
    assert args.gradio is True
