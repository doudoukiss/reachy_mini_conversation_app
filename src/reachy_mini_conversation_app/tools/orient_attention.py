from __future__ import annotations

from typing import Any

from reachy_mini_conversation_app.tools.core_tools import Tool, ToolDependencies
from reachy_mini_conversation_app.tools.semantic_helpers import action_result_to_payload, missing_runtime_payload


class OrientAttention(Tool):
    """Direct semantic attention toward a target."""

    name = "orient_attention"
    description = (
        "Orient attention toward a semantic target such as left, right, up, down, front, "
        "an image point, or a named person."
    )
    parameters_schema = {
        "type": "object",
        "properties": {
            "target": {
                "type": "string",
                "enum": ["left", "right", "up", "down", "front", "image_point", "named_person"],
                "description": "Semantic attention target to orient toward.",
            },
            "x": {
                "type": "number",
                "description": "Optional X coordinate for image_point. Use normalized 0-1 values when practical.",
            },
            "y": {
                "type": "number",
                "description": "Optional Y coordinate for image_point. Use normalized 0-1 values when practical.",
            },
            "person": {
                "type": "string",
                "description": "Optional person identifier when target is named_person.",
            },
            "reason": {
                "type": "string",
                "description": "Short semantic reason for the reorientation.",
            },
            "duration": {
                "type": "number",
                "description": "Optional movement duration in seconds.",
            },
        },
        "required": ["target"],
    }

    async def __call__(self, deps: ToolDependencies, **kwargs: Any) -> dict[str, Any]:
        """Orient attention via the semantic robot runtime."""
        if deps.robot_runtime is None:
            return missing_runtime_payload(self.name)

        target = str(kwargs.get("target") or "").strip()
        if not target:
            return {"error": "target must be a non-empty string"}

        args: dict[str, Any] = {"target": target}
        for key in ("x", "y", "reason", "duration"):
            if kwargs.get(key) is not None:
                args[key] = kwargs[key]
        if kwargs.get("person"):
            args["person"] = str(kwargs["person"])

        result = await deps.robot_runtime.execute_action("orient_attention", args=args)
        return action_result_to_payload(result)
