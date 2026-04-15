"""Tests for the mock robot adapter."""

from __future__ import annotations

import asyncio

import pytest

from reachy_mini_conversation_app.robot_brain.adapters.mock_adapter import MockRobotAdapter
from reachy_mini_conversation_app.robot_brain.contracts import RobotAction


@pytest.mark.asyncio
async def test_mock_adapter_exposes_expected_capabilities() -> None:
    """The mock adapter should provide a stable semantic capability catalog."""
    adapter = MockRobotAdapter()

    capabilities = await adapter.get_capabilities()

    assert capabilities.backend == "mock"
    assert capabilities.modes_supported == ["mock"]
    assert "friendly" in capabilities.persistent_states
    assert "guarded_close_right" in capabilities.motifs
    assert "face_tracking" in capabilities.attention_modes


@pytest.mark.asyncio
async def test_mock_adapter_executes_and_updates_state() -> None:
    """Supported semantic actions should update the in-memory mock state."""
    adapter = MockRobotAdapter()

    state_result = await adapter.execute(
        RobotAction(action_type="set_persistent_state", args={"state": "friendly"}, action_id="state-1")
    )
    attention_result = await adapter.execute(
        RobotAction(action_type="set_attention_mode", args={"mode": "face_tracking"}, action_id="attn-1")
    )
    observation_result = await adapter.execute(
        RobotAction(action_type="observe_scene", args={"question": "What is in front of me?"}, action_id="obs-1")
    )

    assert state_result.status == "completed"
    assert state_result.state_snapshot is not None
    assert state_result.state_snapshot.persistent_state == "friendly"
    assert attention_result.state_snapshot is not None
    assert attention_result.state_snapshot.attention_mode == "face_tracking"
    assert observation_result.observation is not None
    assert "desk" in observation_result.observation["summary"]
    assert len(adapter.journal) == 3


@pytest.mark.asyncio
async def test_mock_adapter_supports_long_running_action_cancellation() -> None:
    """Long-running mock actions should be cancellable through the adapter surface."""
    adapter = MockRobotAdapter()
    action = RobotAction(
        action_type="perform_motif",
        args={"motif": "guarded_close_right", "simulate_delay_s": 0.05},
        action_id="motif-1",
    )

    task = asyncio.create_task(adapter.execute(action))
    await asyncio.sleep(0.01)
    cancel_result = await adapter.cancel("motif-1")
    action_result = await task

    assert cancel_result.status == "cancelled"
    assert action_result.status == "cancelled"
    assert any(entry.action_id == "motif-1" for entry in adapter.journal)
