"""Robot adapter exports and factory helpers."""

from __future__ import annotations

from typing import Any

from reachy_mini_conversation_app.robot_brain.adapters.base import BaseRobotBodyAdapter, UnavailableRobotAdapter
from reachy_mini_conversation_app.robot_brain.adapters.mock_adapter import MockRobotAdapter
from reachy_mini_conversation_app.robot_brain.adapters.reachy_adapter import ReachyAdapter


def build_robot_adapter(backend: str, **kwargs: Any) -> BaseRobotBodyAdapter:
    """Create a robot adapter for the requested backend."""
    backend_name = backend.strip().lower()
    if backend_name == "mock":
        return MockRobotAdapter()
    if backend_name == "reachy":
        from reachy_mini_conversation_app.robot_brain.adapters.reachy_adapter import ReachyAdapter

        robot = kwargs.get("robot")
        movement_manager = kwargs.get("movement_manager")
        if robot is None or movement_manager is None:
            raise RuntimeError("ReachyAdapter requires 'robot' and 'movement_manager' dependencies.")
        return ReachyAdapter(
            robot=robot,
            movement_manager=movement_manager,
            camera_worker=kwargs.get("camera_worker"),
            head_wobbler=kwargs.get("head_wobbler"),
            vision_processor=kwargs.get("vision_processor"),
        )
    if backend_name == "embodied_stack":
        return UnavailableRobotAdapter(
            backend=backend_name,
            message=f"{backend_name} adapter is not implemented yet; using compatibility placeholder for this pass.",
        )
    raise RuntimeError(
        f"Unsupported ROBOT_BACKEND={backend!r}. Expected one of: mock, reachy, embodied_stack."
    )


__all__ = [
    "BaseRobotBodyAdapter",
    "MockRobotAdapter",
    "ReachyAdapter",
    "UnavailableRobotAdapter",
    "build_robot_adapter",
]
