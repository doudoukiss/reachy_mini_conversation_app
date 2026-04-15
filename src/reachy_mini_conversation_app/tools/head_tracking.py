import logging
from typing import Any, Dict

from reachy_mini_conversation_app.tools.core_tools import Tool, ToolDependencies
from reachy_mini_conversation_app.tools.semantic_helpers import action_result_to_payload


logger = logging.getLogger(__name__)


class HeadTracking(Tool):
    """Toggle head tracking state."""

    name = "head_tracking"
    description = "Toggle head tracking state."
    parameters_schema = {
        "type": "object",
        "properties": {"start": {"type": "boolean"}},
        "required": ["start"],
    }

    async def __call__(self, deps: ToolDependencies, **kwargs: Any) -> Dict[str, Any]:
        """Enable or disable head tracking."""
        enable = bool(kwargs.get("start"))

        if deps.robot_runtime is not None:
            result = await deps.robot_runtime.execute_action(
                "set_attention_mode",
                args={"mode": "face_tracking" if enable else "disabled"},
            )
            payload = action_result_to_payload(result)
            payload["legacy_tool"] = self.name
            return payload

        # Update camera worker head tracking state
        if deps.camera_worker is not None:
            deps.camera_worker.set_head_tracking_enabled(enable)

        status = "started" if enable else "stopped"
        logger.info("Tool call: head_tracking %s", status)
        return {"status": f"head tracking {status}"}
