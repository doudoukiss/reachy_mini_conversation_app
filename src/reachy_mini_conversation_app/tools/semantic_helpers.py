"""Shared helpers for semantic robot-brain tools."""

from __future__ import annotations

from typing import Any

from reachy_mini_conversation_app.robot_brain.contracts import ActionResult
from reachy_mini_conversation_app.tools.core_tools import ToolDependencies


def require_robot_runtime(deps: ToolDependencies) -> object | None:
    """Return the injected robot runtime, if present."""
    return deps.robot_runtime


def action_result_to_payload(result: ActionResult, **extra: Any) -> dict[str, Any]:
    """Serialize a semantic action result into a tool-friendly payload."""
    payload: dict[str, Any] = {
        "action_id": result.action_id,
        "action_type": result.action_type,
        "status": result.status,
        "mode": result.mode,
        "summary": result.summary,
    }
    if result.warnings:
        payload["warnings"] = list(result.warnings)
    if result.observation is not None:
        payload["observation"] = result.observation
    if result.details:
        payload["details"] = result.details
    if result.state_snapshot is not None:
        payload["state"] = result.state_snapshot.to_dict()
    if result.health_snapshot is not None:
        payload["health"] = result.health_snapshot.to_dict()
    payload.update(extra)
    return payload


def missing_runtime_payload(tool_name: str) -> dict[str, Any]:
    """Return a standard error payload when the semantic runtime is unavailable."""
    return {
        "error": f"{tool_name} requires robot_runtime, but no robot runtime is configured.",
        "status": "unavailable",
    }
