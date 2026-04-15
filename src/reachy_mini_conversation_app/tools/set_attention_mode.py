from __future__ import annotations

from typing import Any

from reachy_mini_conversation_app.robot_brain.capability_catalog import current_capability_catalog, format_allowed_values
from reachy_mini_conversation_app.tools.core_tools import Tool, ToolDependencies
from reachy_mini_conversation_app.tools.semantic_helpers import action_result_to_payload, missing_runtime_payload


class SetAttentionMode(Tool):
    """Set the semantic attention mode for the robot."""

    name = "set_attention_mode"
    description = "Set the robot attention mode."
    parameters_schema = {
        "type": "object",
        "properties": {
            "mode": {
                "type": "string",
                "description": "Semantic attention mode to activate.",
            },
        },
        "required": ["mode"],
    }

    def spec(self) -> dict[str, Any]:
        """Return a capability-aware function spec."""
        catalog = current_capability_catalog()
        modes = list(catalog.attention_modes)
        mode_property: dict[str, Any] = {
            "type": "string",
            "description": "Attention mode to activate.",
        }
        if modes:
            mode_property["enum"] = modes
        return {
            "type": "function",
            "name": self.name,
            "description": (
                "Set the robot attention mode. "
                f"Available attention modes on this backend: {format_allowed_values(modes)}."
            ),
            "parameters": {
                "type": "object",
                "properties": {"mode": mode_property},
                "required": ["mode"],
            },
        }

    async def __call__(self, deps: ToolDependencies, **kwargs: Any) -> dict[str, Any]:
        """Set the current semantic attention mode."""
        if deps.robot_runtime is None:
            return missing_runtime_payload(self.name)

        mode = str(kwargs.get("mode") or "").strip()
        if not mode:
            return {"error": "mode must be a non-empty string"}

        result = await deps.robot_runtime.execute_action("set_attention_mode", args={"mode": mode})
        return action_result_to_payload(result)
