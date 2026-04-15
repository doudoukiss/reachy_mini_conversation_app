from __future__ import annotations

import asyncio
from typing import Any

from reachy_mini_conversation_app.robot_brain.capability_catalog import summarize_robot_context
from reachy_mini_conversation_app.tools.core_tools import Tool, ToolDependencies
from reachy_mini_conversation_app.tools.semantic_helpers import missing_runtime_payload


class ReportRobotStatus(Tool):
    """Report the semantic robot status, health, and capability surface."""

    name = "report_robot_status"
    description = "Report robot health, current semantic state, and available capabilities."
    parameters_schema = {
        "type": "object",
        "properties": {},
        "required": [],
    }

    async def __call__(self, deps: ToolDependencies, **kwargs: Any) -> dict[str, Any]:
        """Fetch the current robot status from the semantic runtime."""
        if deps.robot_runtime is None:
            return missing_runtime_payload(self.name)

        capabilities, health, state = await asyncio.gather(
            deps.robot_runtime.get_capabilities(),
            deps.robot_runtime.get_health(),
            deps.robot_runtime.get_state(),
        )
        return {
            "status": health.overall,
            "summary": summarize_robot_context(capabilities, health=health, state=state),
            "capabilities": capabilities.to_dict(),
            "health": health.to_dict(),
            "state": state.to_dict(),
        }
