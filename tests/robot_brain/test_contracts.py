"""Tests for robot-brain contract objects."""

from reachy_mini_conversation_app.robot_brain.contracts import (
    ActionResult,
    CapabilityCatalog,
    RobotAction,
    RobotHealth,
    RobotState,
)


def test_contracts_serialize_to_plain_dicts() -> None:
    """Contracts should remain easy to serialize and inspect in tests."""
    catalog = CapabilityCatalog(
        robot_name="mock-head",
        backend="mock",
        modes_supported=["mock"],
        persistent_states=["neutral", "friendly"],
        motifs=["guarded_close_right"],
        attention_modes=["manual", "disabled"],
    )
    state = RobotState(
        mode="mock",
        persistent_state="friendly",
        attention_mode="manual",
        last_observation_summary="A desk and operator are visible.",
    )
    health = RobotHealth(overall="ok", message="Healthy.")
    action = RobotAction(
        action_type="set_persistent_state",
        args={"state": "friendly"},
        mode="mock",
        action_id="action-123",
    )
    result = ActionResult(
        action_id="action-123",
        action_type="set_persistent_state",
        status="completed",
        mode="mock",
        summary="Set persistent state to friendly.",
        state_snapshot=state,
        health_snapshot=health,
        details={"state": "friendly"},
        started_at=1.0,
        finished_at=2.0,
    )

    assert catalog.to_dict()["persistent_states"] == ["neutral", "friendly"]
    assert state.to_dict()["attention_mode"] == "manual"
    assert health.to_dict()["overall"] == "ok"
    assert action.to_dict()["action_id"] == "action-123"
    assert result.to_dict()["state_snapshot"]["persistent_state"] == "friendly"
    assert result.to_dict()["health_snapshot"]["message"] == "Healthy."
