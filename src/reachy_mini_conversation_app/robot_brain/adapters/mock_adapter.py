"""Deterministic mock robot adapter for hardware-free development."""

from __future__ import annotations

import asyncio
import copy
import time
import uuid
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


class MockRobotAdapter(BaseRobotBodyAdapter):
    """Semantic robot adapter backed by a deterministic in-memory state machine."""

    def __init__(self, *, robot_name: str = "mock-head") -> None:
        self._capabilities = CapabilityCatalog(
            robot_name=robot_name,
            backend="mock",
            modes_supported=["mock"],
            structural_units=["head_turn", "neck_pitch", "neck_tilt"],
            expressive_units=["eye_yaw", "eye_pitch", "lids", "brows"],
            persistent_states=["neutral", "friendly", "listen_attentively", "thinking", "safe_idle"],
            motifs=["guarded_close_left", "guarded_close_right"],
            attention_modes=["manual", "face_tracking", "idle_scan", "disabled"],
            warnings=[],
        )
        self._health = RobotHealth(
            overall="ok",
            message="Mock robot backend healthy.",
            details={"backend": "mock"},
        )
        self._state = RobotState(
            mode="mock",
            persistent_state="neutral",
            attention_mode="disabled",
        )
        self._journal: list[ActionResult] = []
        self._pending_cancellations: dict[str, asyncio.Event] = {}

    @property
    def journal(self) -> list[ActionResult]:
        """Return the recorded action journal."""
        return list(self._journal)

    async def get_capabilities(self) -> CapabilityCatalog:
        """Return the mock capability catalog."""
        return copy.deepcopy(self._capabilities)

    async def get_health(self) -> RobotHealth:
        """Return the current mock health."""
        return copy.deepcopy(self._health)

    async def get_state(self) -> RobotState:
        """Return the current mock state."""
        return copy.deepcopy(self._state)

    async def execute(self, action: RobotAction) -> ActionResult:
        """Execute a semantic action against the mock state machine."""
        action_id = action.action_id or str(uuid.uuid4())
        started_at = time.monotonic()

        if action.mode != "mock":
            return self._record_result(
                ActionResult(
                    action_id=action_id,
                    action_type=action.action_type,
                    status="rejected",
                    mode=action.mode,
                    summary=f"Mock adapter supports only mock mode, not {action.mode}.",
                    warnings=[f"unsupported_mode:{action.mode}"],
                    state_snapshot=await self.get_state(),
                    health_snapshot=await self.get_health(),
                    details={"backend": "mock"},
                    started_at=started_at,
                    finished_at=time.monotonic(),
                )
            )

        cancel_event = asyncio.Event()
        self._pending_cancellations[action_id] = cancel_event
        try:
            result = await self._dispatch_action(action_id=action_id, action=action, started_at=started_at, cancel_event=cancel_event)
            return self._record_result(result)
        finally:
            self._pending_cancellations.pop(action_id, None)

    async def cancel(self, action_id: str) -> ActionResult:
        """Request cancellation for a pending mock action."""
        started_at = time.monotonic()
        cancel_event = self._pending_cancellations.get(action_id)
        if cancel_event is None:
            return self._record_result(
                ActionResult(
                    action_id=action_id,
                    action_type="cancel_action",
                    status="rejected",
                    mode="mock",
                    summary=f"No running mock action with id {action_id}.",
                    warnings=["unknown_action_id"],
                    state_snapshot=await self.get_state(),
                    health_snapshot=await self.get_health(),
                    details={"backend": "mock"},
                    started_at=started_at,
                    finished_at=time.monotonic(),
                )
            )

        cancel_event.set()
        return self._record_result(
            ActionResult(
                action_id=action_id,
                action_type="cancel_action",
                status="cancelled",
                mode="mock",
                summary=f"Cancellation requested for action {action_id}.",
                state_snapshot=await self.get_state(),
                health_snapshot=await self.get_health(),
                details={"backend": "mock"},
                started_at=started_at,
                finished_at=time.monotonic(),
            )
        )

    async def go_neutral(self, mode: ExecutionMode = "mock") -> ActionResult:
        """Reset the mock robot to a neutral state."""
        return await self.execute(RobotAction(action_type="go_neutral", mode=mode))

    async def _dispatch_action(
        self,
        *,
        action_id: str,
        action: RobotAction,
        started_at: float,
        cancel_event: asyncio.Event,
    ) -> ActionResult:
        """Route an action to the deterministic mock handlers."""
        args = dict(action.args)
        delay_s = float(args.get("simulate_delay_s", 0.0) or 0.0)
        if delay_s > 0:
            cancelled = await self._sleep_with_cancellation(delay_s, cancel_event)
            if cancelled:
                return self._make_result(
                    action_id=action_id,
                    action_type=action.action_type,
                    status="cancelled",
                    summary=f"Cancelled {action.action_type} before completion.",
                    started_at=started_at,
                )

        action_type = action.action_type
        if action_type == "go_neutral":
            self._state.active_behavior = None
            self._state.persistent_state = "neutral"
            self._state.attention_mode = "disabled"
            return self._make_result(
                action_id=action_id,
                action_type=action_type,
                summary="Returned to neutral mock state.",
                started_at=started_at,
            )

        if action_type == "set_persistent_state":
            state_name = str(args.get("state") or "").strip()
            if state_name not in self._capabilities.persistent_states:
                return self._make_result(
                    action_id=action_id,
                    action_type=action_type,
                    status="failed",
                    summary=f"Persistent state '{state_name}' is not supported by the mock adapter.",
                    warnings=["unsupported_persistent_state"],
                    details={"requested_state": state_name},
                    started_at=started_at,
                )
            self._state.persistent_state = state_name
            return self._make_result(
                action_id=action_id,
                action_type=action_type,
                summary=f"Set persistent state to {state_name}.",
                details={"state": state_name},
                started_at=started_at,
            )

        if action_type == "perform_motif":
            motif = str(args.get("motif") or "").strip()
            if motif not in self._capabilities.motifs:
                return self._make_result(
                    action_id=action_id,
                    action_type=action_type,
                    status="failed",
                    summary=f"Motif '{motif}' is not supported by the mock adapter.",
                    warnings=["unsupported_motif"],
                    details={"requested_motif": motif},
                    started_at=started_at,
                )
            self._state.active_behavior = motif
            return self._make_result(
                action_id=action_id,
                action_type=action_type,
                summary=f"Performed motif {motif}.",
                details={"motif": motif, "intensity": args.get("intensity")},
                started_at=started_at,
            )

        if action_type == "set_attention_mode":
            mode_name = str(args.get("mode") or "").strip()
            if mode_name not in self._capabilities.attention_modes:
                return self._make_result(
                    action_id=action_id,
                    action_type=action_type,
                    status="failed",
                    summary=f"Attention mode '{mode_name}' is not supported by the mock adapter.",
                    warnings=["unsupported_attention_mode"],
                    details={"requested_mode": mode_name},
                    started_at=started_at,
                )
            self._state.attention_mode = mode_name
            return self._make_result(
                action_id=action_id,
                action_type=action_type,
                summary=f"Set attention mode to {mode_name}.",
                details={"mode": mode_name},
                started_at=started_at,
            )

        if action_type == "orient_attention":
            target = str(args.get("target") or "").strip()
            allowed_targets = {"left", "right", "up", "down", "front", "image_point", "named_person"}
            if target not in allowed_targets:
                return self._make_result(
                    action_id=action_id,
                    action_type=action_type,
                    status="failed",
                    summary=f"Attention target '{target}' is not supported by the mock adapter.",
                    warnings=["unsupported_attention_target"],
                    details={"requested_target": target},
                    started_at=started_at,
                )
            self._state.active_behavior = f"orient_attention:{target}"
            self._state.attention_mode = "manual"
            return self._make_result(
                action_id=action_id,
                action_type=action_type,
                summary=f"Oriented mock attention toward {target}.",
                details={
                    "target": target,
                    "x": args.get("x"),
                    "y": args.get("y"),
                    "reason": args.get("reason"),
                },
                started_at=started_at,
            )

        if action_type == "observe_scene":
            question = str(args.get("question") or "What is in front of me?")
            observation = {
                "summary": "Mock scene: a desk, a laptop, and an operator standing nearby.",
                "question": question,
                "visible_objects": ["desk", "laptop", "operator"],
                "include_image": bool(args.get("include_image", False)),
            }
            self._state.last_observation_summary = observation["summary"]
            return self._make_result(
                action_id=action_id,
                action_type=action_type,
                summary=f"Observed the mock scene for: {question}",
                observation=observation,
                started_at=started_at,
            )

        if action_type == "stop_behavior":
            behavior = str(args.get("behavior") or "current")
            if behavior in {"current", "expression", "all"}:
                self._state.active_behavior = None
            if behavior in {"attention", "all"}:
                self._state.attention_mode = "disabled"
            return self._make_result(
                action_id=action_id,
                action_type=action_type,
                summary=f"Stopped mock behavior scope: {behavior}.",
                details={"behavior": behavior},
                started_at=started_at,
            )

        if action_type == "query_health":
            return self._make_result(
                action_id=action_id,
                action_type=action_type,
                summary=self._health.message,
                details=self._health.details,
                started_at=started_at,
            )

        if action_type == "query_capabilities":
            return self._make_result(
                action_id=action_id,
                action_type=action_type,
                summary="Returned mock capability catalog.",
                details={"capabilities": self._capabilities.to_dict()},
                started_at=started_at,
            )

        return self._make_result(
            action_id=action_id,
            action_type=action_type,
            status="rejected",
            summary=f"Mock adapter does not support action '{action_type}'.",
            warnings=["unsupported_action"],
            started_at=started_at,
        )

    async def _sleep_with_cancellation(self, delay_s: float, cancel_event: asyncio.Event) -> bool:
        """Sleep in short steps so cancellation can interrupt long-running actions."""
        remaining = delay_s
        while remaining > 0:
            if cancel_event.is_set():
                return True
            step = min(remaining, 0.01)
            await asyncio.sleep(step)
            remaining -= step
        return cancel_event.is_set()

    def _make_result(
        self,
        *,
        action_id: str,
        action_type: str,
        summary: str,
        started_at: float,
        status: str = "completed",
        warnings: list[str] | None = None,
        observation: dict[str, Any] | None = None,
        details: dict[str, Any] | None = None,
    ) -> ActionResult:
        """Create a typed mock action result from the current adapter state."""
        return ActionResult(
            action_id=action_id,
            action_type=action_type,
            status=status,  # type: ignore[arg-type]
            mode="mock",
            summary=summary,
            warnings=list(warnings or []),
            observation=copy.deepcopy(observation),
            state_snapshot=copy.deepcopy(self._state),
            health_snapshot=copy.deepcopy(self._health),
            details=dict(details or {}),
            started_at=started_at,
            finished_at=time.monotonic(),
        )

    def _record_result(self, result: ActionResult) -> ActionResult:
        """Append the result to the adapter journal and return it."""
        self._journal.append(copy.deepcopy(result))
        return result
