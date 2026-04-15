from __future__ import annotations

from typing import Any

from reachy_mini_conversation_app.robot_brain.capability_catalog import current_capability_catalog, format_allowed_values
from reachy_mini_conversation_app.tools.core_tools import Tool, ToolDependencies
from reachy_mini_conversation_app.tools.semantic_helpers import action_result_to_payload, missing_runtime_payload


class PerformMotif(Tool):
    """Perform a semantic movement or expression motif."""

    name = "perform_motif"
    description = "Perform a semantic motif."
    parameters_schema = {
        "type": "object",
        "properties": {
            "motif": {
                "type": "string",
                "description": "Motif name to perform.",
            },
            "intensity": {
                "type": "string",
                "enum": ["low", "medium", "high"],
                "description": "Optional semantic intensity for the motif.",
            },
            "reason": {
                "type": "string",
                "description": "Optional reason for choosing the motif.",
            },
        },
        "required": ["motif"],
    }

    def spec(self) -> dict[str, Any]:
        """Return a capability-aware function spec."""
        catalog = current_capability_catalog()
        motifs = list(catalog.motifs)
        motif_property: dict[str, Any] = {
            "type": "string",
            "description": "Motif to perform.",
        }
        if motifs:
            motif_property["enum"] = motifs
        return {
            "type": "function",
            "name": self.name,
            "description": (
                "Perform a semantic motif rather than inventing low-level motion. "
                f"Available motifs on this backend: {format_allowed_values(motifs)}."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "motif": motif_property,
                    "intensity": {
                        "type": "string",
                        "enum": ["low", "medium", "high"],
                        "description": "Optional semantic intensity for the motif.",
                    },
                    "reason": {
                        "type": "string",
                        "description": "Optional reason for the motif choice.",
                    },
                },
                "required": ["motif"],
            },
        }

    async def __call__(self, deps: ToolDependencies, **kwargs: Any) -> dict[str, Any]:
        """Perform a semantic motif."""
        if deps.robot_runtime is None:
            return missing_runtime_payload(self.name)

        motif = str(kwargs.get("motif") or "").strip()
        if not motif:
            return {"error": "motif must be a non-empty string"}

        args: dict[str, Any] = {"motif": motif}
        if kwargs.get("intensity") is not None:
            args["intensity"] = kwargs["intensity"]
        if kwargs.get("reason") is not None:
            args["reason"] = kwargs["reason"]

        result = await deps.robot_runtime.execute_action("perform_motif", args=args)
        return action_result_to_payload(result)
