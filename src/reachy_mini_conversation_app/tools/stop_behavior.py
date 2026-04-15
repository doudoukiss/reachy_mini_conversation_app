from __future__ import annotations

from typing import Any

from reachy_mini_conversation_app.tools.core_tools import Tool, ToolDependencies
from reachy_mini_conversation_app.tools.semantic_helpers import action_result_to_payload, missing_runtime_payload


class StopBehavior(Tool):
    """Stop semantic robot behavior."""

    name = "stop_behavior"
    description = "Stop the current semantic behavior, attention loop, expression, or all behavior."
    parameters_schema = {
        "type": "object",
        "properties": {
            "behavior": {
                "type": "string",
                "enum": ["current", "attention", "expression", "all"],
                "description": "Behavior scope to stop.",
            },
        },
        "required": ["behavior"],
    }

    async def __call__(self, deps: ToolDependencies, **kwargs: Any) -> dict[str, Any]:
        """Stop semantic robot behavior."""
        if deps.robot_runtime is None:
            return missing_runtime_payload(self.name)

        behavior = str(kwargs.get("behavior") or "").strip()
        if not behavior:
            return {"error": "behavior must be a non-empty string"}

        result = await deps.robot_runtime.execute_action("stop_behavior", args={"behavior": behavior})
        return action_result_to_payload(result)
