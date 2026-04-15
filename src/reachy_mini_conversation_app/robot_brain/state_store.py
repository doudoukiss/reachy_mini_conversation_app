"""Lightweight in-memory state and action journal for the robot brain."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from reachy_mini_conversation_app.robot_brain.contracts import ActionResult, CapabilityCatalog, RobotHealth, RobotState


@dataclass(slots=True)
class RobotBrainStateStore:
    """Keep the latest robot context plus a simple action journal."""

    capabilities: CapabilityCatalog | None = None
    health: RobotHealth | None = None
    state: RobotState | None = None
    action_journal: list[ActionResult] = field(default_factory=list)

    def remember_capabilities(self, capabilities: CapabilityCatalog) -> CapabilityCatalog:
        """Store and return the latest capabilities."""
        self.capabilities = capabilities
        return capabilities

    def remember_health(self, health: RobotHealth) -> RobotHealth:
        """Store and return the latest health."""
        self.health = health
        return health

    def remember_state(self, state: RobotState) -> RobotState:
        """Store and return the latest state."""
        self.state = state
        return state

    def record_action(self, result: ActionResult) -> ActionResult:
        """Append an action result and refresh derived snapshots."""
        self.action_journal.append(result)
        if result.health_snapshot is not None:
            self.health = result.health_snapshot
        if result.state_snapshot is not None:
            self.state = result.state_snapshot
        return result

    def snapshot(self) -> dict[str, Any]:
        """Return a serializable runtime snapshot."""
        return {
            "capabilities": self.capabilities.to_dict() if self.capabilities is not None else None,
            "health": self.health.to_dict() if self.health is not None else None,
            "state": self.state.to_dict() if self.state is not None else None,
            "action_journal": [result.to_dict() for result in self.action_journal],
        }
