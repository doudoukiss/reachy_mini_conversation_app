from __future__ import annotations

from typing import Any

from reachy_mini_conversation_app.tools.core_tools import Tool, ToolDependencies
from reachy_mini_conversation_app.tools.semantic_helpers import action_result_to_payload, missing_runtime_payload


class ObserveScene(Tool):
    """Ask the robot to inspect the current scene semantically."""

    name = "observe_scene"
    description = "Observe the current scene and answer a grounded question about what is visible."
    parameters_schema = {
        "type": "object",
        "properties": {
            "question": {
                "type": "string",
                "description": "What to inspect in the scene, for example 'What is in front of you?'",
            },
            "include_image": {
                "type": "boolean",
                "description": "Request raw image availability when the backend supports it.",
            },
        },
        "required": ["question"],
    }

    async def __call__(self, deps: ToolDependencies, **kwargs: Any) -> dict[str, Any]:
        """Observe the scene via the semantic robot runtime."""
        if deps.robot_runtime is None:
            return missing_runtime_payload(self.name)

        question = str(kwargs.get("question") or "").strip()
        if not question:
            return {"error": "question must be a non-empty string"}

        result = await deps.robot_runtime.execute_action(
            "observe_scene",
            args={
                "question": question,
                "include_image": bool(kwargs.get("include_image", False)),
            },
        )
        payload = action_result_to_payload(result)
        if result.observation is not None and "b64_im" in result.observation:
            payload["b64_im"] = result.observation["b64_im"]
        return payload
