"""Reachy compatibility adapter for the robot-brain runtime."""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass
from typing import Any

import numpy as np
from numpy.typing import NDArray

from reachy_mini import ReachyMini
from reachy_mini.utils import create_head_pose

from reachy_mini_conversation_app.robot_brain.adapters.base import BaseRobotBodyAdapter
from reachy_mini_conversation_app.robot_brain.contracts import (
    ActionResult,
    CapabilityCatalog,
    ExecutionMode,
    RobotAction,
    RobotHealth,
    RobotState,
)


_DIRECTION_POSES: dict[str, tuple[int, int, int, int, int, int]] = {
    "left": (0, 0, 0, 0, 0, 40),
    "right": (0, 0, 0, 0, 0, -40),
    "up": (0, 0, 0, 0, -30, 0),
    "down": (0, 0, 0, 0, 30, 0),
    "front": (0, 0, 0, 0, 0, 0),
}


@dataclass(slots=True)
class ReachyAdapter(BaseRobotBodyAdapter):
    """Compatibility adapter that wraps the current Reachy runtime objects."""

    robot: ReachyMini
    movement_manager: Any
    camera_worker: Any | None = None
    head_wobbler: Any | None = None
    vision_processor: Any | None = None

    def __post_init__(self) -> None:
        """Initialize semantic state tracked by the adapter."""
        self._persistent_state: str | None = None
        self._active_behavior: str | None = None
        self._attention_mode: str = self._derive_attention_mode()
        self._last_observation_summary: str | None = None
        self._last_mode: ExecutionMode = "mock"

    async def get_capabilities(self) -> CapabilityCatalog:
        """Return the Reachy compatibility capability catalog."""
        attention_modes = ["manual", "disabled"]
        warnings = [
            "set_persistent_state is not implemented on the Reachy compatibility adapter.",
            "perform_motif is not implemented on the Reachy compatibility adapter.",
        ]
        if self.camera_worker is not None and getattr(self.camera_worker, "supports_attention_tracking", lambda: False)():
            attention_modes.extend(["face_tracking", "idle_scan"])

        return CapabilityCatalog(
            robot_name=getattr(self.robot, "robot_name", "reachy-mini"),
            backend="reachy",
            modes_supported=["mock", "preview", "live"],
            structural_units=["head_turn", "neck_pitch", "neck_tilt", "antennas"],
            expressive_units=["antennas"],
            persistent_states=[],
            motifs=[],
            attention_modes=attention_modes,
            warnings=warnings,
        )

    async def get_health(self) -> RobotHealth:
        """Return a lightweight health snapshot for the Reachy adapter."""
        details: dict[str, Any] = {
            "camera_available": self.camera_worker is not None,
            "head_wobbler_available": self.head_wobbler is not None,
        }
        try:
            details["movement"] = self.movement_manager.get_status()
            return RobotHealth(
                overall="ok",
                message="Reachy compatibility adapter ready.",
                details=details,
            )
        except Exception as exc:
            details["error"] = str(exc)
            return RobotHealth(
                overall="degraded",
                message="Reachy compatibility adapter is available, but status polling failed.",
                details=details,
            )

    async def get_state(self) -> RobotState:
        """Return the semantic state tracked by the Reachy adapter."""
        return RobotState(
            mode=self._last_mode,
            active_behavior=self._active_behavior,
            persistent_state=self._persistent_state,
            attention_mode=self._attention_mode,
            last_observation_summary=self._last_observation_summary,
            extra={"backend": "reachy"},
        )

    async def execute(self, action: RobotAction) -> ActionResult:
        """Execute a semantic action using the current Reachy runtime objects."""
        action_id = action.action_id or str(uuid.uuid4())
        started_at = time.monotonic()
        self._last_mode = action.mode

        if action.action_type == "query_health":
            return await self._result(
                action_id=action_id,
                action_type=action.action_type,
                mode=action.mode,
                summary=(await self.get_health()).message,
                details=(await self.get_health()).details,
                started_at=started_at,
            )
        if action.action_type == "query_capabilities":
            catalog = await self.get_capabilities()
            return await self._result(
                action_id=action_id,
                action_type=action.action_type,
                mode=action.mode,
                summary="Returned Reachy compatibility capabilities.",
                details={"capabilities": catalog.to_dict()},
                started_at=started_at,
            )

        if action.action_type in {"set_persistent_state", "perform_motif"}:
            return await self._result(
                action_id=action_id,
                action_type=action.action_type,
                mode=action.mode,
                status="rejected",
                summary=f"{action.action_type} is not implemented on the Reachy compatibility adapter.",
                warnings=["not_supported"],
                started_at=started_at,
            )

        if action.mode == "mock":
            return await self._result(
                action_id=action_id,
                action_type=action.action_type,
                mode=action.mode,
                summary=f"Recorded mock request for {action.action_type} without moving Reachy hardware.",
                warnings=["mock_mode_no_execution"],
                details={"args": dict(action.args)},
                started_at=started_at,
            )

        if action.mode == "preview" and action.action_type != "observe_scene":
            return await self._result(
                action_id=action_id,
                action_type=action.action_type,
                mode=action.mode,
                summary=f"Previewed Reachy action {action.action_type} without executing it.",
                warnings=["preview_mode_no_execution"],
                details={"args": dict(action.args)},
                started_at=started_at,
            )

        if action.action_type == "go_neutral":
            duration = self._coerce_duration(action.args.get("duration"), default=1.0)
            self.movement_manager.go_neutral(duration=duration)
            self._persistent_state = "neutral"
            self._active_behavior = None
            return await self._result(
                action_id=action_id,
                action_type=action.action_type,
                mode=action.mode,
                summary="Queued Reachy neutral pose.",
                details={"duration": duration},
                started_at=started_at,
            )

        if action.action_type == "set_attention_mode":
            return await self._handle_set_attention_mode(action_id=action_id, action=action, started_at=started_at)

        if action.action_type == "orient_attention":
            return await self._handle_orient_attention(action_id=action_id, action=action, started_at=started_at)

        if action.action_type == "observe_scene":
            return await self._handle_observe_scene(action_id=action_id, action=action, started_at=started_at)

        if action.action_type == "stop_behavior":
            return await self._handle_stop_behavior(action_id=action_id, action=action, started_at=started_at)

        return await self._result(
            action_id=action_id,
            action_type=action.action_type,
            mode=action.mode,
            status="rejected",
            summary=f"Reachy compatibility adapter does not support action '{action.action_type}'.",
            warnings=["unsupported_action"],
            started_at=started_at,
        )

    async def cancel(self, action_id: str) -> ActionResult:
        """Cancel the current Reachy behavior by clearing the movement queue."""
        started_at = time.monotonic()
        self.movement_manager.clear_move_queue()
        self._active_behavior = None
        return await self._result(
            action_id=action_id,
            action_type="cancel_action",
            mode=self._last_mode,
            status="cancelled",
            summary=f"Cleared current Reachy motion queue for action {action_id}.",
            started_at=started_at,
        )

    async def go_neutral(self, mode: ExecutionMode = "mock") -> ActionResult:
        """Compatibility wrapper for the neutral action."""
        return await self.execute(RobotAction(action_type="go_neutral", mode=mode))

    async def _handle_set_attention_mode(
        self,
        *,
        action_id: str,
        action: RobotAction,
        started_at: float,
    ) -> ActionResult:
        """Translate semantic attention modes into the current camera worker behavior."""
        mode_name = str(action.args.get("mode") or "").strip()
        if not mode_name:
            return await self._result(
                action_id=action_id,
                action_type=action.action_type,
                mode=action.mode,
                status="failed",
                summary="set_attention_mode requires a non-empty mode.",
                warnings=["missing_mode"],
                started_at=started_at,
            )

        if mode_name == "face_tracking":
            if self.camera_worker is None or not getattr(self.camera_worker, "supports_attention_tracking", lambda: False)():
                return await self._result(
                    action_id=action_id,
                    action_type=action.action_type,
                    mode=action.mode,
                    status="rejected",
                    summary="Reachy face tracking is unavailable because no tracking-capable camera worker is attached.",
                    warnings=["tracking_unavailable"],
                    started_at=started_at,
                )
            self.camera_worker.set_head_tracking_enabled(True)
            self._attention_mode = "face_tracking"
            return await self._result(
                action_id=action_id,
                action_type=action.action_type,
                mode=action.mode,
                summary="Enabled Reachy face tracking.",
                details={"mode": "face_tracking"},
                started_at=started_at,
            )

        if mode_name == "idle_scan":
            if self.camera_worker is not None:
                self.camera_worker.set_head_tracking_enabled(False)
            self._attention_mode = "manual"
            return await self._result(
                action_id=action_id,
                action_type=action.action_type,
                mode=action.mode,
                summary="Reachy idle_scan is not implemented; falling back to manual attention.",
                warnings=["idle_scan_fallback_manual"],
                details={"mode": "idle_scan"},
                started_at=started_at,
            )

        if mode_name in {"manual", "disabled"}:
            if self.camera_worker is not None:
                self.camera_worker.set_head_tracking_enabled(False)
            self._attention_mode = mode_name
            return await self._result(
                action_id=action_id,
                action_type=action.action_type,
                mode=action.mode,
                summary=f"Set Reachy attention mode to {mode_name}.",
                details={"mode": mode_name},
                started_at=started_at,
            )

        return await self._result(
            action_id=action_id,
            action_type=action.action_type,
            mode=action.mode,
            status="failed",
            summary=f"Unsupported Reachy attention mode '{mode_name}'.",
            warnings=["unsupported_attention_mode"],
            started_at=started_at,
        )

    async def _handle_orient_attention(
        self,
        *,
        action_id: str,
        action: RobotAction,
        started_at: float,
    ) -> ActionResult:
        """Translate semantic attention targets into Reachy head motions."""
        target = str(action.args.get("target") or "front").strip()
        duration = self._coerce_duration(action.args.get("duration"), default=1.0)

        try:
            target_pose = self._resolve_attention_target_pose(target, action.args)
        except ValueError as exc:
            return await self._result(
                action_id=action_id,
                action_type=action.action_type,
                mode=action.mode,
                status="failed",
                summary=str(exc),
                warnings=["invalid_attention_target"],
                started_at=started_at,
            )
        except NotImplementedError as exc:
            return await self._result(
                action_id=action_id,
                action_type=action.action_type,
                mode=action.mode,
                status="rejected",
                summary=str(exc),
                warnings=["unsupported_attention_target"],
                started_at=started_at,
            )

        self.movement_manager.queue_goto_pose(target_pose, duration=duration, target_antennas=(0.0, 0.0), target_body_yaw=0.0)
        self._active_behavior = f"orient_attention:{target}"
        return await self._result(
            action_id=action_id,
            action_type=action.action_type,
            mode=action.mode,
            summary=f"Queued Reachy attention target '{target}'.",
            details={"target": target, "duration": duration},
            started_at=started_at,
        )

    async def _handle_observe_scene(
        self,
        *,
        action_id: str,
        action: RobotAction,
        started_at: float,
    ) -> ActionResult:
        """Capture the latest frame and optionally run local vision."""
        question = str(action.args.get("question") or "What is in front of me?")
        if self.camera_worker is None:
            return await self._result(
                action_id=action_id,
                action_type=action.action_type,
                mode=action.mode,
                status="failed",
                summary="Reachy camera worker is unavailable.",
                warnings=["camera_unavailable"],
                started_at=started_at,
            )

        frame = self.camera_worker.get_latest_frame()
        if frame is None:
            return await self._result(
                action_id=action_id,
                action_type=action.action_type,
                mode=action.mode,
                status="failed",
                summary="No camera frame is currently available from Reachy.",
                warnings=["no_frame_available"],
                started_at=started_at,
            )

        observation: dict[str, Any] = {
            "question": question,
            "frame_shape": tuple(frame.shape),
            "image_available": True,
        }
        if self.vision_processor is not None:
            description = await asyncio.to_thread(self.vision_processor.process_image, frame, question)
            observation["image_description"] = description
            summary = str(description)
        else:
            summary = "Captured a Reachy camera frame for multimodal follow-up."
            observation["image_description"] = summary

        self._last_observation_summary = summary
        return await self._result(
            action_id=action_id,
            action_type=action.action_type,
            mode=action.mode,
            summary=summary,
            observation=observation,
            started_at=started_at,
        )

    async def _handle_stop_behavior(
        self,
        *,
        action_id: str,
        action: RobotAction,
        started_at: float,
    ) -> ActionResult:
        """Stop Reachy motion and/or attention behaviors."""
        behavior = str(action.args.get("behavior") or "current").strip()
        if behavior in {"current", "expression", "all"}:
            self.movement_manager.clear_move_queue()
            self._active_behavior = None
        if behavior in {"attention", "all"} and self.camera_worker is not None:
            self.camera_worker.set_head_tracking_enabled(False)
            self._attention_mode = "manual"

        return await self._result(
            action_id=action_id,
            action_type=action.action_type,
            mode=action.mode,
            summary=f"Stopped Reachy behavior scope '{behavior}'.",
            details={"behavior": behavior},
            started_at=started_at,
        )

    async def _result(
        self,
        *,
        action_id: str,
        action_type: str,
        mode: ExecutionMode,
        summary: str,
        started_at: float,
        status: str = "completed",
        warnings: list[str] | None = None,
        observation: dict[str, Any] | None = None,
        details: dict[str, Any] | None = None,
    ) -> ActionResult:
        """Construct a typed action result with fresh state and health snapshots."""
        return ActionResult(
            action_id=action_id,
            action_type=action_type,
            status=status,  # type: ignore[arg-type]
            mode=mode,
            summary=summary,
            warnings=list(warnings or []),
            observation=observation,
            state_snapshot=await self.get_state(),
            health_snapshot=await self.get_health(),
            details=dict(details or {}),
            started_at=started_at,
            finished_at=time.monotonic(),
        )

    def _derive_attention_mode(self) -> str:
        """Infer the current semantic attention mode from the attached camera worker."""
        if self.camera_worker is None:
            return "disabled"
        mode_getter = getattr(self.camera_worker, "get_attention_mode", None)
        if callable(mode_getter):
            return str(mode_getter())
        return "manual"

    def _resolve_attention_target_pose(self, target: str, args: dict[str, Any]) -> NDArray[np.float32]:
        """Resolve a semantic attention target into a Reachy head pose."""
        if target in _DIRECTION_POSES:
            return create_head_pose(*_DIRECTION_POSES[target], degrees=True)

        if target == "image_point":
            x = float(args.get("x", 0.5))
            y = float(args.get("y", 0.5))
            frame = self.camera_worker.get_latest_frame() if self.camera_worker is not None else None
            width = int(frame.shape[1]) if frame is not None else 640
            height = int(frame.shape[0]) if frame is not None else 480
            if 0.0 <= x <= 1.0 and 0.0 <= y <= 1.0:
                x_px = x * width
                y_px = y * height
            else:
                x_px = x
                y_px = y
            return self.robot.look_at_image(x_px, y_px, duration=0.0, perform_movement=False)

        if target == "named_person":
            raise NotImplementedError("named_person attention is not supported by the Reachy compatibility adapter.")

        raise ValueError(f"Unsupported attention target '{target}'.")

    @staticmethod
    def _coerce_duration(value: Any, *, default: float) -> float:
        """Coerce duration-like values to positive floats."""
        try:
            duration = float(value)
        except (TypeError, ValueError):
            return default
        return duration if duration > 0 else default
