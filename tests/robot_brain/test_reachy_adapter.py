"""Tests for the Reachy compatibility adapter."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import numpy as np
import pytest

from reachy_mini_conversation_app.main import build_robot_app_context
from reachy_mini_conversation_app.robot_brain.adapters import MockRobotAdapter, build_robot_adapter
from reachy_mini_conversation_app.robot_brain.adapters.reachy_adapter import ReachyAdapter
from reachy_mini_conversation_app.robot_brain.contracts import RobotAction


class FakeMovementManager:
    """Small fake movement manager for Reachy adapter tests."""

    def __init__(self, current_robot: object | None = None, camera_worker: object | None = None) -> None:
        self.current_robot = current_robot
        self.camera_worker = camera_worker
        self.go_neutral_calls: list[float] = []
        self.queue_calls: list[dict[str, object]] = []
        self.clear_count = 0

    def set_speech_offsets(self, *_args: object, **_kwargs: object) -> None:
        """Compatibility no-op used by HeadWobbler construction."""

    def go_neutral(self, *, duration: float = 1.0) -> None:
        """Record neutral requests."""
        self.go_neutral_calls.append(duration)

    def queue_goto_pose(
        self,
        target_head_pose: np.ndarray,
        *,
        duration: float = 1.0,
        target_antennas: tuple[float, float] = (0.0, 0.0),
        target_body_yaw: float = 0.0,
    ) -> None:
        """Record orientation requests."""
        self.queue_calls.append(
            {
                "target_head_pose": target_head_pose,
                "duration": duration,
                "target_antennas": target_antennas,
                "target_body_yaw": target_body_yaw,
            }
        )

    def clear_move_queue(self) -> None:
        """Record stop requests."""
        self.clear_count += 1

    def get_status(self) -> dict[str, object]:
        """Return a lightweight fake status surface."""
        return {"queue_size": len(self.queue_calls), "clear_count": self.clear_count}


class FakeCameraWorker:
    """Fake camera worker with head-tracking toggles and a frame buffer."""

    def __init__(self) -> None:
        self.enabled = False
        self.frame = np.zeros((8, 10, 3), dtype=np.uint8)

    def set_head_tracking_enabled(self, enabled: bool) -> None:
        """Record tracking state changes."""
        self.enabled = enabled

    def supports_attention_tracking(self) -> bool:
        """Report that tracking is available."""
        return True

    def get_attention_mode(self) -> str:
        """Expose the current semantic attention mode."""
        return "face_tracking" if self.enabled else "manual"

    def get_latest_frame(self) -> np.ndarray:
        """Return a stable fake frame."""
        return self.frame.copy()


class FakeVisionProcessor:
    """Small fake vision processor for observe_scene tests."""

    def process_image(self, frame: np.ndarray, question: str) -> str:
        """Return a deterministic string summary."""
        return f"Observed {frame.shape[1]}x{frame.shape[0]} image for: {question}"


class FakeHeadWobbler:
    """Compatibility stub for startup tests."""

    def __init__(self, *_args: object, **_kwargs: object) -> None:
        self.started = False

    def start(self) -> None:
        """Record start."""
        self.started = True

    def stop(self) -> None:
        """Record stop."""
        self.started = False


def _fake_robot() -> object:
    """Build a minimal fake Reachy robot object."""
    return SimpleNamespace(
        robot_name="reachy-test",
        look_at_image=lambda *_args, **_kwargs: np.eye(4, dtype=np.float32),
        client=SimpleNamespace(get_status=lambda: {"simulation_enabled": False, "mockup_sim_enabled": False}),
    )


def test_build_robot_adapter_selects_mock_and_reachy() -> None:
    """Factory should create the correct adapter for each configured backend."""
    mock_adapter = build_robot_adapter("mock")
    reachy_adapter = build_robot_adapter(
        "reachy",
        robot=_fake_robot(),
        movement_manager=FakeMovementManager(),
        camera_worker=FakeCameraWorker(),
        head_wobbler=MagicMock(),
        vision_processor=FakeVisionProcessor(),
    )

    assert isinstance(mock_adapter, MockRobotAdapter)
    assert isinstance(reachy_adapter, ReachyAdapter)


@pytest.mark.asyncio
async def test_reachy_adapter_translates_live_motion_actions() -> None:
    """Live semantic actions should map onto the current Reachy runtime helpers."""
    movement_manager = FakeMovementManager()
    camera_worker = FakeCameraWorker()
    adapter = ReachyAdapter(
        robot=_fake_robot(),  # type: ignore[arg-type]
        movement_manager=movement_manager,
        camera_worker=camera_worker,
        head_wobbler=MagicMock(),
        vision_processor=FakeVisionProcessor(),
    )

    neutral = await adapter.execute(RobotAction(action_type="go_neutral", mode="live", args={"duration": 1.5}))
    attention = await adapter.execute(
        RobotAction(action_type="set_attention_mode", mode="live", args={"mode": "face_tracking"})
    )
    orient = await adapter.execute(
        RobotAction(action_type="orient_attention", mode="live", args={"target": "left", "duration": 0.75})
    )

    assert neutral.status == "completed"
    assert movement_manager.go_neutral_calls == [1.5]
    assert attention.status == "completed"
    assert camera_worker.enabled is True
    assert orient.status == "completed"
    assert len(movement_manager.queue_calls) == 1
    assert movement_manager.queue_calls[0]["duration"] == 0.75


@pytest.mark.asyncio
async def test_reachy_adapter_translates_observe_and_stop_actions() -> None:
    """Observe and stop actions should route through camera and movement helpers."""
    movement_manager = FakeMovementManager()
    camera_worker = FakeCameraWorker()
    adapter = ReachyAdapter(
        robot=_fake_robot(),  # type: ignore[arg-type]
        movement_manager=movement_manager,
        camera_worker=camera_worker,
        head_wobbler=MagicMock(),
        vision_processor=FakeVisionProcessor(),
    )

    camera_worker.enabled = True
    observation = await adapter.execute(
        RobotAction(action_type="observe_scene", mode="live", args={"question": "What do you see?"})
    )
    stop = await adapter.execute(
        RobotAction(action_type="stop_behavior", mode="live", args={"behavior": "all"})
    )

    assert observation.status == "completed"
    assert observation.observation is not None
    assert observation.observation["image_description"].startswith("Observed 10x8 image")
    assert stop.status == "completed"
    assert movement_manager.clear_count == 1
    assert camera_worker.enabled is False


def test_build_robot_app_context_supports_reachy_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reachy startup should construct a ReachyAdapter-backed runtime."""
    logger = MagicMock()
    args = SimpleNamespace(
        gradio=False,
        no_camera=False,
        head_tracker=None,
        robot_name=None,
    )
    fake_robot = _fake_robot()
    fake_camera_worker = FakeCameraWorker()
    fake_vision = FakeVisionProcessor()

    monkeypatch.setattr(
        "reachy_mini_conversation_app.main.initialize_camera_and_vision",
        lambda _args, _robot: (fake_camera_worker, fake_vision),
    )
    monkeypatch.setattr("reachy_mini_conversation_app.moves.MovementManager", FakeMovementManager)
    monkeypatch.setattr("reachy_mini_conversation_app.audio.head_wobbler.HeadWobbler", FakeHeadWobbler)

    from reachy_mini_conversation_app.config import config

    monkeypatch.setattr(config, "ROBOT_BACKEND", "reachy")
    context = build_robot_app_context(args, logger, robot=fake_robot)  # type: ignore[arg-type]

    assert context.robot is fake_robot
    assert isinstance(context.robot_adapter, ReachyAdapter)
    assert context.robot_runtime.adapter is context.robot_adapter
    assert context.movement_manager is context.robot_adapter.movement_manager
    assert context.camera_worker is fake_camera_worker
