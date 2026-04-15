from __future__ import annotations

from pathlib import Path

from embodied_stack.config import Settings
from embodied_stack.desktop.runtime import DesktopRuntimeGateway
from embodied_stack.shared.contracts import CommandType, RobotCommand, RobotMode


def build_settings(tmp_path: Path, **overrides) -> Settings:
    return Settings(
        _env_file=None,
        brain_store_path=str(tmp_path / "brain_store.json"),
        demo_report_dir=str(tmp_path / "demo_runs"),
        episode_export_dir=str(tmp_path / "episodes"),
        shift_report_dir=str(tmp_path / "shift_reports"),
        operator_auth_token="desktop-test-token",
        operator_auth_runtime_file=str(tmp_path / "operator_auth.json"),
        **overrides,
    )


def test_virtual_body_runtime_applies_semantic_commands(tmp_path: Path):
    settings = build_settings(tmp_path, blink_runtime_mode=RobotMode.DESKTOP_VIRTUAL_BODY)
    gateway = DesktopRuntimeGateway(settings=settings)

    expression_ack = gateway.apply_command(
        RobotCommand(command_type=CommandType.SET_EXPRESSION, payload={"expression": "listening"})
    )
    gaze_ack = gateway.apply_command(
        RobotCommand(command_type=CommandType.SET_GAZE, payload={"target": "left"})
    )

    telemetry = gateway.get_telemetry()
    assert expression_ack.accepted is True
    assert gaze_ack.accepted is True
    assert telemetry.mode == RobotMode.DESKTOP_VIRTUAL_BODY
    assert telemetry.body_driver_mode.value == "virtual"
    assert telemetry.body_state is not None
    assert telemetry.body_state.active_expression == "listen_attentively"
    assert telemetry.body_state.gaze_target == "look_left"
    assert abs(telemetry.body_state.servo_targets["head_yaw"] - 2047) > abs(
        telemetry.body_state.servo_targets["eye_yaw"] - 2047
    )
    assert telemetry.body_state.virtual_preview is not None
    assert telemetry.body_state.virtual_preview.semantic_name == "look_left"
    assert telemetry.body_state.last_command_outcome is not None
    assert telemetry.body_state.last_command_outcome.source_action_name == "left"


def test_bodyless_runtime_accepts_semantic_commands_without_robot(tmp_path: Path):
    settings = build_settings(tmp_path, blink_runtime_mode=RobotMode.DESKTOP_BODYLESS)
    gateway = DesktopRuntimeGateway(settings=settings)

    ack = gateway.apply_command(
        RobotCommand(command_type=CommandType.PERFORM_GESTURE, payload={"gesture": "blink"})
    )

    telemetry = gateway.get_telemetry()
    assert ack.accepted is True
    assert telemetry.mode == RobotMode.DESKTOP_BODYLESS
    assert telemetry.body_driver_mode.value == "bodyless"
    assert telemetry.body_state is not None
    assert telemetry.body_state.last_gesture == "blink_soft"
    assert telemetry.body_state.last_command_outcome is not None
    assert telemetry.body_state.last_command_outcome.source_action_name == "blink"


def test_safe_idle_command_switches_desktop_runtime_into_degraded_mode(tmp_path: Path):
    settings = build_settings(tmp_path, blink_runtime_mode=RobotMode.DESKTOP_VIRTUAL_BODY)
    gateway = DesktopRuntimeGateway(settings=settings)

    ack = gateway.apply_command(
        RobotCommand(command_type=CommandType.SAFE_IDLE, payload={"reason": "operator_override"})
    )

    telemetry = gateway.get_telemetry()
    heartbeat = gateway.get_heartbeat()
    assert ack.accepted is True
    assert telemetry.mode == RobotMode.DEGRADED_SAFE_IDLE
    assert telemetry.safe_idle_reason == "operator_override"
    assert heartbeat.safe_idle_active is True


def test_serial_body_semantic_library_uses_cached_driver_state(tmp_path, monkeypatch):
    settings = build_settings(
        tmp_path,
        blink_runtime_mode=RobotMode.DESKTOP_SERIAL_BODY,
        blink_body_driver="serial",
        blink_serial_transport="dry_run",
    )
    gateway = DesktopRuntimeGateway(settings=settings)

    refresh_calls: list[bool] = []

    def counted_refresh(*, force: bool = False):
        refresh_calls.append(force)
        return gateway.runtime.body_driver.state.model_copy(deep=True)

    monkeypatch.setattr(gateway.runtime.body_driver, "refresh_live_status", counted_refresh)

    response = gateway.get_body_semantic_library(smoke_safe_only=True)

    assert response["ok"] is True
    assert response["payload"]["semantic_actions"]
    assert refresh_calls == []
