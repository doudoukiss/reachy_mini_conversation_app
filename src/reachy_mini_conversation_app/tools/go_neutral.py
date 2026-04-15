from __future__ import annotations

from typing import Any

from reachy_mini_conversation_app.tools.core_tools import Tool, ToolDependencies
from reachy_mini_conversation_app.tools.semantic_helpers import action_result_to_payload, missing_runtime_payload


class GoNeutral(Tool):
    """Return the robot to a neutral semantic state."""

    name = "go_neutral"
    description = "Return the robot to its neutral semantic pose and state."
    parameters_schema = {
        "type": "object",
        "properties": {},
        "required": [],
    }

    async def __call__(self, deps: ToolDependencies, **kwargs: Any) -> dict[str, Any]:
        """Return the robot to neutral via the semantic runtime."""
        if deps.robot_runtime is None:
            return missing_runtime_payload(self.name)

        result = await deps.robot_runtime.go_neutral()
        return action_result_to_payload(result)
