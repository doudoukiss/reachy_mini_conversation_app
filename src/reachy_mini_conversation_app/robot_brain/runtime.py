"""Runtime wrapper around robot body adapters."""

from __future__ import annotations

import uuid
from dataclasses import replace
from typing import Any

from reachy_mini_conversation_app.robot_brain.adapters.base import BaseRobotBodyAdapter
from reachy_mini_conversation_app.robot_brain.contracts import (
    ActionResult,
    CapabilityCatalog,
    ExecutionMode,
    RobotAction,
    RobotHealth,
    RobotState,
)
from reachy_mini_conversation_app.robot_brain.state_store import RobotBrainStateStore


class RobotBrainRuntime:
    """Thin runtime that owns one adapter plus an in-memory state store."""

    def __init__(
        self,
        adapter: BaseRobotBodyAdapter,
        *,
        default_mode: ExecutionMode = "mock",
        state_store: RobotBrainStateStore | None = None,
    ) -> None:
        self.adapter = adapter
        self.default_mode = default_mode
        self.state_store = state_store or RobotBrainStateStore()

    async def get_capabilities(self) -> CapabilityCatalog:
        """Fetch and cache the current capability catalog."""
        return self.state_store.remember_capabilities(await self.adapter.get_capabilities())

    async def get_health(self) -> RobotHealth:
        """Fetch and cache the current robot health."""
        return self.state_store.remember_health(await self.adapter.get_health())

    async def get_state(self) -> RobotState:
        """Fetch and cache the current robot state."""
        return self.state_store.remember_state(await self.adapter.get_state())

    async def execute_action(
        self,
        action: RobotAction | str,
        *,
        args: dict[str, Any] | None = None,
        mode: ExecutionMode | None = None,
    ) -> ActionResult:
        """Execute a semantic action and journal the result."""
        request = self._normalize_action(action, args=args, mode=mode)
        result = await self.adapter.execute(request)
        return self.state_store.record_action(result)

    async def cancel_action(self, action_id: str) -> ActionResult:
        """Cancel an action and journal the result."""
        return self.state_store.record_action(await self.adapter.cancel(action_id))

    async def go_neutral(self, mode: ExecutionMode | None = None) -> ActionResult:
        """Return the robot to a neutral state and journal the result."""
        resolved_mode = mode or self.default_mode
        return self.state_store.record_action(await self.adapter.go_neutral(resolved_mode))

    def _normalize_action(
        self,
        action: RobotAction | str,
        *,
        args: dict[str, Any] | None = None,
        mode: ExecutionMode | None = None,
    ) -> RobotAction:
        """Normalize string and object actions to a fully-populated RobotAction."""
        if isinstance(action, str):
            return RobotAction(
                action_type=action,
                args=dict(args or {}),
                mode=mode or self.default_mode,
                action_id=str(uuid.uuid4()),
            )

        request = action
        if mode is not None and request.mode != mode:
            request = replace(request, mode=mode)
        if request.action_id is None:
            request = replace(request, action_id=str(uuid.uuid4()))
        return request
