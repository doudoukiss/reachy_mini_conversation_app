"""Base robot adapter interfaces and compatibility placeholders."""

from __future__ import annotations

import time
import uuid
from abc import ABC, abstractmethod

from reachy_mini_conversation_app.robot_brain.capability_catalog import empty_capability_catalog
from reachy_mini_conversation_app.robot_brain.contracts import (
    ActionResult,
    CapabilityCatalog,
    ExecutionMode,
    RobotAction,
    RobotHealth,
    RobotState,
)


class BaseRobotBodyAdapter(ABC):
    """Abstract base class for robot body adapters."""

    @abstractmethod
    async def get_capabilities(self) -> CapabilityCatalog:
        """Return the current capability catalog."""

    @abstractmethod
    async def get_health(self) -> RobotHealth:
        """Return the current health snapshot."""

    @abstractmethod
    async def get_state(self) -> RobotState:
        """Return the current semantic state."""

    @abstractmethod
    async def execute(self, action: RobotAction) -> ActionResult:
        """Execute a semantic action."""

    @abstractmethod
    async def cancel(self, action_id: str) -> ActionResult:
        """Cancel a previously-started action."""

    @abstractmethod
    async def go_neutral(self, mode: ExecutionMode = "mock") -> ActionResult:
        """Return the robot to a neutral state."""


class UnavailableRobotAdapter(BaseRobotBodyAdapter):
    """Compatibility placeholder used before a real adapter exists."""

    def __init__(self, *, backend: str, message: str):
        self.backend = backend
        self.message = message

    async def get_capabilities(self) -> CapabilityCatalog:
        """Return a placeholder capability catalog with an explanatory warning."""
        return empty_capability_catalog(
            backend=self.backend,
            robot_name=f"{self.backend}-unavailable",
            warning=self.message,
        )

    async def get_health(self) -> RobotHealth:
        """Return an unknown health snapshot."""
        return RobotHealth(
            overall="unknown",
            message=self.message,
            details={"backend": self.backend},
        )

    async def get_state(self) -> RobotState:
        """Return a placeholder robot state."""
        return RobotState(
            mode="mock",
            extra={"backend": self.backend, "available": False},
        )

    async def execute(self, action: RobotAction) -> ActionResult:
        """Reject execution while preserving a typed result surface."""
        return await self._rejected_result(action_id=action.action_id, action_type=action.action_type, mode=action.mode)

    async def cancel(self, action_id: str) -> ActionResult:
        """Reject cancellation while preserving a typed result surface."""
        return await self._rejected_result(action_id=action_id, action_type="cancel_action", mode="mock")

    async def go_neutral(self, mode: ExecutionMode = "mock") -> ActionResult:
        """Reject neutral requests while preserving a typed result surface."""
        return await self._rejected_result(action_id=None, action_type="go_neutral", mode=mode)

    async def _rejected_result(
        self,
        *,
        action_id: str | None,
        action_type: str,
        mode: ExecutionMode,
    ) -> ActionResult:
        """Build a consistent rejection result."""
        started_at = time.monotonic()
        finished_at = time.monotonic()
        return ActionResult(
            action_id=action_id or str(uuid.uuid4()),
            action_type=action_type,
            status="rejected",
            mode=mode,
            summary=self.message,
            warnings=[self.message],
            state_snapshot=await self.get_state(),
            health_snapshot=await self.get_health(),
            details={"backend": self.backend},
            started_at=started_at,
            finished_at=finished_at,
        )
