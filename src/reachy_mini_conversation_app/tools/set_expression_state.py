from __future__ import annotations

from typing import Any

from reachy_mini_conversation_app.robot_brain.capability_catalog import current_capability_catalog, format_allowed_values
from reachy_mini_conversation_app.tools.core_tools import Tool, ToolDependencies
from reachy_mini_conversation_app.tools.semantic_helpers import action_result_to_payload, missing_runtime_payload


class SetExpressionState(Tool):
    """Set a persistent semantic expression state."""

    name = "set_expression_state"
    description = "Set a persistent semantic expression state."
    parameters_schema = {
        "type": "object",
        "properties": {
            "state": {
                "type": "string",
                "description": "Persistent expression state to apply.",
            },
        },
        "required": ["state"],
    }

    def spec(self) -> dict[str, Any]:
        """Return a capability-aware function spec."""
        catalog = current_capability_catalog()
        states = list(catalog.persistent_states)
        state_property: dict[str, Any] = {
            "type": "string",
            "description": "Persistent semantic state to apply.",
        }
        if states:
            state_property["enum"] = states
        return {
            "type": "function",
            "name": self.name,
            "description": (
                "Set a persistent semantic expression state. "
                f"Available persistent states on this backend: {format_allowed_values(states)}."
            ),
            "parameters": {
                "type": "object",
                "properties": {"state": state_property},
                "required": ["state"],
            },
        }

    async def __call__(self, deps: ToolDependencies, **kwargs: Any) -> dict[str, Any]:
        """Set the persistent semantic expression state."""
        if deps.robot_runtime is None:
            return missing_runtime_payload(self.name)

        state = str(kwargs.get("state") or "").strip()
        if not state:
            return {"error": "state must be a non-empty string"}

        result = await deps.robot_runtime.execute_action("set_persistent_state", args={"state": state})
        return action_result_to_payload(result)
