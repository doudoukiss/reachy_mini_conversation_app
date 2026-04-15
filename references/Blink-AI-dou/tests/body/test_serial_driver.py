from __future__ import annotations

from pathlib import Path

import pytest

from embodied_stack.body import BodyCommandApplyError, SemanticBodyCompiler, build_body_driver
from embodied_stack.body import calibration as calibration_module
from embodied_stack.body.projection import build_character_semantic_intent
from embodied_stack.body.profile import default_head_profile
from embodied_stack.body.range_demo import available_range_demo_sequences
from embodied_stack.body.semantics import lookup_action_descriptor
from embodied_stack.body.tuning import load_semantic_tuning
from embodied_stack.body.serial.driver import FeetechBodyBridge
from embodied_stack.body.serial.bench import confirm_live_transport, write_arm_lease
from embodied_stack.body.serial.transport import DryRunServoTransport, LIVE_SERIAL_MODE, ServoTransportError
from embodied_stack.config import Settings
from embodied_stack.desktop.runtime import DesktopRuntimeGateway
from embodied_stack.shared.contracts import (
    AnimationRequest,
    BodyCommandOutcomeRecord,
    BodyState,
    CharacterProjectionProfile,
    CommandAckStatus,
    CompanionPresenceState,
    CompanionPresenceStatus,
    CompanionVoiceLoopState,
    CompanionVoiceLoopStatus,
    CompiledAnimation,
    CompiledBodyFrame,
    FallbackState,
    GestureRequest,
    InitiativeStatus,
    RelationshipContinuityStatus,
    RobotCommand,
    RobotMode,
    ServoHealthRecord,
)


def build_settings(tmp_path: Path, **overrides) -> Settings:
    return Settings(
        _env_file=None,
        brain_store_path=str(tmp_path / "brain_store.json"),
        demo_report_dir=str(tmp_path / "demo_runs"),
        demo_check_dir=str(tmp_path / "demo_checks"),
        episode_export_dir=str(tmp_path / "episodes"),
        shift_report_dir=str(tmp_path / "shift_reports"),
        operator_auth_token="serial-test-token",
        operator_auth_runtime_file=str(tmp_path / "operator_auth.json"),
        blink_runtime_mode=RobotMode.DESKTOP_SERIAL_BODY,
        blink_body_driver="serial",
        **overrides,
    )


def _saved_calibration(path: Path) -> None:
    profile = default_head_profile()
    calibration = calibration_module.calibration_from_profile(profile, calibration_kind="saved")
    for joint in calibration.joint_records:
        joint.mirrored_direction_confirmed = True
    calibration.coupling_validation = {
        "neck_pitch_roll": "ok",
        "mirrored_eyelids": "ok",
        "mirrored_brows": "ok",
        "eyes_follow_lids": "ok",
        "range_conflicts": "ok",
    }
    calibration_module.save_head_calibration(calibration, path)


def _live_like_transport():
    profile = default_head_profile()
    neutral_positions = {
        servo_id: joint.neutral
        for joint in profile.joints
        for servo_id in joint.servo_ids
    }
    transport = DryRunServoTransport(
        baud_rate=1000000,
        timeout_seconds=0.2,
        known_ids=sorted({servo_id for joint in profile.joints for servo_id in joint.servo_ids}),
        neutral_positions=neutral_positions,
    )
    transport.status.mode = LIVE_SERIAL_MODE
    transport.status.port = "/dev/tty.fake"
    transport.status.healthy = True
    transport.status.confirmed_live = True
    transport.status.reason_code = "ok"
    return transport


def _saved_compiler() -> SemanticBodyCompiler:
    profile = default_head_profile()
    calibration = calibration_module.calibration_from_profile(profile, calibration_kind="saved")
    for joint in calibration.joint_records:
        joint.mirrored_direction_confirmed = True
    return SemanticBodyCompiler(profile=profile, calibration=calibration)


def _compiled_animation_for_action(action_name: str) -> CompiledAnimation:
    compiler = _saved_compiler()
    descriptor = lookup_action_descriptor(action_name)
    assert descriptor is not None
    if descriptor.family == "gesture":
        state = compiler.apply_gesture(BodyState(), GestureRequest(gesture_name=action_name))
    elif descriptor.family == "animation":
        state = compiler.apply_animation(BodyState(), AnimationRequest(animation_name=action_name))
    else:
        raise AssertionError(f"unsupported action family for test: {descriptor.family}")
    assert state.compiled_animation is not None
    return state.compiled_animation


def _health_record(
    *,
    joint_name: str,
    servo_id: int,
    target: int,
    current: int,
    error_bits: list[str] | None = None,
) -> ServoHealthRecord:
    return ServoHealthRecord(
        servo_id=servo_id,
        joint_name=joint_name,
        current_position=current,
        target_position=target,
        torque_enabled=True,
        error_bits=list(error_bits or []),
        last_poll_status="ok",
        reason_code="ok",
        status_summary="ok",
        last_command_outcome="sent",
    )


def test_serial_driver_dry_run_applies_compiled_targets_and_feedback(tmp_path: Path) -> None:
    settings = build_settings(tmp_path, blink_serial_transport="dry_run")
    driver = build_body_driver(settings)

    state = driver.apply_command(
        RobotCommand(command_type="set_expression", payload={"expression": "listening"}),
        {"expression": "listening"},
    )

    assert state.transport_mode == "dry_run"
    assert state.transport_healthy is True
    assert state.transport_reason_code == "ok"
    assert state.feedback_positions["head_yaw"] == state.servo_targets["head_yaw"]
    assert state.calibration_status == "template"
    assert state.last_command_outcome is not None
    assert state.last_command_outcome.outcome_status == "sent"


def test_serial_driver_refuses_out_of_range_frame(tmp_path: Path) -> None:
    settings = build_settings(tmp_path, blink_serial_transport="dry_run")
    driver = build_body_driver(settings)
    driver.state.compiled_animation = CompiledAnimation(
        animation_name="bad_frame",
        frames=[
            CompiledBodyFrame(
                frame_name="bad",
                servo_targets={"head_yaw": 99999},
            )
        ],
    )

    with pytest.raises(BodyCommandApplyError) as exc_info:
        driver._apply_compiled_animation()

    assert exc_info.value.classification == "out_of_range"


def test_desktop_gateway_marks_unhealthy_live_serial_as_transport_error(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr("embodied_stack.body.driver.DEFAULT_ARM_LEASE_PATH", tmp_path / "runtime" / "serial" / "live_motion_arm.json")
    settings = build_settings(
        tmp_path,
        blink_serial_transport="live_serial",
        blink_serial_port=None,
    )
    gateway = DesktopRuntimeGateway(settings=settings)

    ack = gateway.apply_command(
        RobotCommand(command_type="set_expression", payload={"expression": "listening"})
    )

    telemetry = gateway.get_telemetry()
    assert ack.status == CommandAckStatus.TRANSPORT_ERROR
    assert ack.accepted is False
    assert telemetry.body_state is not None
    assert telemetry.body_state.transport_mode == "live_serial"
    assert telemetry.body_state.transport_healthy is False
    assert telemetry.body_state.transport_error is not None
    assert telemetry.body_state.transport_reason_code is not None
    assert telemetry.transport_ok is False
    assert gateway.get_heartbeat().transport_ok is False


def test_live_serial_runtime_hydrates_port_from_active_arm_lease(monkeypatch, tmp_path: Path) -> None:
    calibration_path = tmp_path / "runtime" / "calibrations" / "robot_head_live_v1.json"
    _saved_calibration(calibration_path)
    arm_path = tmp_path / "runtime" / "serial" / "live_motion_arm.json"
    captured: dict[str, object] = {}

    def _build_transport(settings, profile):
        captured["port"] = settings.blink_serial_port
        captured["baud_rate"] = settings.blink_servo_baud
        transport = _live_like_transport()
        transport.status.port = settings.blink_serial_port
        transport.status.baud_rate = settings.blink_servo_baud
        return transport

    write_arm_lease(
        port="/dev/tty.lease",
        baud_rate=1000000,
        calibration_path=str(calibration_path),
        ttl_seconds=60,
        path=arm_path,
    )
    monkeypatch.setattr("embodied_stack.body.driver.build_servo_transport", _build_transport)
    monkeypatch.setattr("embodied_stack.body.driver.DEFAULT_ARM_LEASE_PATH", arm_path)
    settings = build_settings(
        tmp_path,
        blink_serial_transport="live_serial",
        blink_serial_port=None,
        blink_servo_baud=1000000,
        blink_head_calibration=str(calibration_path),
    )

    driver = build_body_driver(settings)

    assert captured["port"] == "/dev/tty.lease"
    assert captured["baud_rate"] == 1000000
    assert driver.state.transport_port == "/dev/tty.lease"
    assert driver.state.transport_confirmed_live is True
    assert driver.state.live_motion_armed is True


def test_live_serial_requires_saved_calibration_for_motion(tmp_path: Path) -> None:
    settings = build_settings(
        tmp_path,
        blink_serial_transport="live_serial",
        blink_serial_port="/dev/tty.fake",
        blink_head_calibration="src/embodied_stack/body/profiles/robot_head_v1.calibration_template.json",
    )
    driver = build_body_driver(settings)

    with pytest.raises(BodyCommandApplyError) as exc_info:
        driver.apply_command(
            RobotCommand(command_type="set_expression", payload={"expression": "friendly"}),
            {"expression": "friendly"},
        )

    assert exc_info.value.classification in {"transport_unconfirmed", "missing_profile", "transport_unavailable"}


def test_live_serial_runtime_requires_arm_and_records_command_audit(monkeypatch, tmp_path: Path) -> None:
    calibration_path = tmp_path / "runtime" / "calibrations" / "robot_head_live_v1.json"
    _saved_calibration(calibration_path)
    monkeypatch.setattr("embodied_stack.body.driver.build_servo_transport", lambda settings, profile: _live_like_transport())
    monkeypatch.setattr("embodied_stack.body.driver.DEFAULT_ARM_LEASE_PATH", tmp_path / "runtime" / "serial" / "live_motion_arm.json")
    settings = build_settings(
        tmp_path,
        blink_serial_transport="live_serial",
        blink_serial_port="/dev/tty.fake",
        blink_servo_baud=1000000,
        blink_head_calibration=str(calibration_path),
    )
    driver = build_body_driver(settings)

    with pytest.raises(BodyCommandApplyError) as exc_info:
        driver.apply_command(
            RobotCommand(command_type="set_expression", payload={"expression": "friendly"}),
            {"expression": "friendly"},
        )

    assert exc_info.value.classification == "motion_not_armed"

    write_arm_lease(
        port="/dev/tty.fake",
        baud_rate=1000000,
        calibration_path=str(calibration_path),
        ttl_seconds=60,
        path=tmp_path / "runtime" / "serial" / "live_motion_arm.json",
    )
    driver.refresh_live_status(force=True)
    state = driver.apply_command(
        RobotCommand(command_type="set_expression", payload={"expression": "friendly"}),
        {"expression": "friendly"},
    )

    assert state.live_motion_armed is True
    assert state.last_transport_poll_at is not None
    assert state.latest_command_audit is not None
    assert state.latest_command_audit.command_type == "set_expression"
    assert state.latest_command_audit.semantic_family == "expression"
    assert state.latest_command_audit.compiled_targets
    assert state.latest_command_audit.after_readback


def test_live_serial_semantic_smoke_supports_expression_gesture_and_animation(monkeypatch, tmp_path: Path) -> None:
    calibration_path = tmp_path / "runtime" / "calibrations" / "robot_head_live_v1.json"
    _saved_calibration(calibration_path)
    monkeypatch.setattr("embodied_stack.body.driver.build_servo_transport", lambda settings, profile: _live_like_transport())
    monkeypatch.setattr("embodied_stack.body.driver.DEFAULT_ARM_LEASE_PATH", tmp_path / "runtime" / "serial" / "live_motion_arm.json")
    settings = build_settings(
        tmp_path,
        blink_serial_transport="live_serial",
        blink_serial_port="/dev/tty.fake",
        blink_servo_baud=1000000,
        blink_head_calibration=str(calibration_path),
    )
    driver = build_body_driver(settings)

    write_arm_lease(
        port="/dev/tty.fake",
        baud_rate=1000000,
        calibration_path=str(calibration_path),
        ttl_seconds=60,
        path=tmp_path / "runtime" / "serial" / "live_motion_arm.json",
    )
    driver.refresh_live_status(force=True)

    expression = driver.run_semantic_smoke(action="friendly", intensity=0.6)
    assert expression["status"] == "ok"
    assert expression["action"] == "friendly"
    assert driver.state.latest_command_audit is not None
    assert driver.state.latest_command_audit.command_type == "set_expression"
    assert driver.state.latest_command_audit.canonical_action_name == "friendly"

    gesture = driver.run_semantic_smoke(action="blink_soft", intensity=0.5, repeat_count=2)
    assert gesture["status"] == "ok"
    assert gesture["action"] == "blink_soft"
    assert driver.state.latest_command_audit is not None
    assert driver.state.latest_command_audit.command_type == "perform_gesture"
    assert driver.state.latest_command_audit.canonical_action_name == "blink_soft"

    animation = driver.run_semantic_smoke(action="recover_neutral", intensity=0.7, repeat_count=2)
    assert animation["status"] == "ok"
    assert animation["action"] == "recover_neutral"
    assert driver.state.latest_command_audit is not None
    assert driver.state.latest_command_audit.command_type == "perform_animation"
    assert driver.state.latest_command_audit.canonical_action_name == "recover_neutral"


def test_live_serial_servo_lab_move_uses_raw_bounds_and_reports_motion_control(monkeypatch, tmp_path: Path) -> None:
    calibration_path = tmp_path / "runtime" / "calibrations" / "robot_head_live_v1.json"
    _saved_calibration(calibration_path)
    monkeypatch.setattr("embodied_stack.body.driver.build_servo_transport", lambda settings, profile: _live_like_transport())
    monkeypatch.setattr("embodied_stack.body.driver.DEFAULT_ARM_LEASE_PATH", tmp_path / "runtime" / "serial" / "live_motion_arm.json")
    settings = build_settings(
        tmp_path,
        blink_serial_transport="live_serial",
        blink_serial_port="/dev/tty.fake",
        blink_servo_baud=1000000,
        blink_head_calibration=str(calibration_path),
    )
    driver = build_body_driver(settings)

    write_arm_lease(
        port="/dev/tty.fake",
        baud_rate=1000000,
        calibration_path=str(calibration_path),
        ttl_seconds=60,
        path=tmp_path / "runtime" / "serial" / "live_motion_arm.json",
    )
    driver.refresh_live_status(force=True)

    result = driver.servo_lab_move(
        joint_name="head_yaw",
        reference_mode="current_delta",
        delta_counts=150,
        speed_override=100,
        acceleration_override=55,
    )

    assert result["success"] is True
    assert result["servo_lab_move"]["effective_target"] == 2197
    assert result["clamped_targets"]["head_yaw"] == 2197
    assert result["motion_control_summary"]["requested_speed_override"] == 100
    assert result["motion_control_summary"]["effective_speed"] == 100
    assert result["motion_control_summary"]["speed_clamped"] is False
    assert result["motion_control_summary"]["acceleration_supported"] is True
    assert result["motion_control_summary"]["requested_acceleration_override"] == 55
    assert result["motion_control_summary"]["effective_acceleration"] == 55
    assert driver.state.latest_command_audit is not None
    assert driver.state.latest_command_audit.command_type == "servo_lab_move"


def test_live_serial_servo_lab_move_clamps_to_calibrated_hard_limits(monkeypatch, tmp_path: Path) -> None:
    calibration_path = tmp_path / "runtime" / "calibrations" / "robot_head_live_v1.json"
    _saved_calibration(calibration_path)
    monkeypatch.setattr("embodied_stack.body.driver.build_servo_transport", lambda settings, profile: _live_like_transport())
    monkeypatch.setattr("embodied_stack.body.driver.DEFAULT_ARM_LEASE_PATH", tmp_path / "runtime" / "serial" / "live_motion_arm.json")
    settings = build_settings(
        tmp_path,
        blink_serial_transport="live_serial",
        blink_serial_port="/dev/tty.fake",
        blink_servo_baud=1000000,
        blink_head_calibration=str(calibration_path),
    )
    driver = build_body_driver(settings)

    write_arm_lease(
        port="/dev/tty.fake",
        baud_rate=1000000,
        calibration_path=str(calibration_path),
        ttl_seconds=60,
        path=tmp_path / "runtime" / "serial" / "live_motion_arm.json",
    )
    driver.refresh_live_status(force=True)

    result = driver.servo_lab_move(
        joint_name="head_yaw",
        reference_mode="current_delta",
        delta_counts=1000,
    )

    assert result["success"] is True
    assert result["servo_lab_move"]["effective_target"] == 2447
    assert any("lab_max_clamp:head_yaw" in note for note in result["servo_lab_move"]["clamp_notes"])


def test_live_serial_character_projection_falls_back_to_preview_until_motion_is_armed(monkeypatch, tmp_path: Path) -> None:
    calibration_path = tmp_path / "runtime" / "calibrations" / "robot_head_live_v1.json"
    _saved_calibration(calibration_path)
    monkeypatch.setattr("embodied_stack.body.driver.build_servo_transport", lambda settings, profile: _live_like_transport())
    monkeypatch.setattr("embodied_stack.body.driver.DEFAULT_ARM_LEASE_PATH", tmp_path / "runtime" / "serial" / "live_motion_arm.json")
    settings = build_settings(
        tmp_path,
        blink_serial_transport="live_serial",
        blink_serial_port="/dev/tty.fake",
        blink_servo_baud=1000000,
        blink_head_calibration=str(calibration_path),
    )
    driver = build_body_driver(settings)
    intent = build_character_semantic_intent(
        presence_status=CompanionPresenceStatus(state=CompanionPresenceState.LISTENING),
        voice_status=CompanionVoiceLoopStatus(state=CompanionVoiceLoopState.CAPTURING),
        initiative_status=InitiativeStatus(),
        relationship_status=RelationshipContinuityStatus(known_user=True),
        fallback_state=FallbackState(),
        body_state=driver.state,
    )

    state = driver.apply_character_projection(intent=intent, profile=CharacterProjectionProfile.AVATAR_AND_ROBOT_HEAD)

    assert state.character_projection is not None
    assert state.character_projection.robot_head_applied is False
    assert state.character_projection.outcome == "robot_head_blocked_preview_only"
    assert state.character_projection.blocked_reason is not None
    assert state.character_projection.blocked_reason.startswith("motion_not_armed:")


def test_live_serial_character_projection_drives_head_once_motion_is_armed(monkeypatch, tmp_path: Path) -> None:
    calibration_path = tmp_path / "runtime" / "calibrations" / "robot_head_live_v1.json"
    _saved_calibration(calibration_path)
    monkeypatch.setattr("embodied_stack.body.driver.build_servo_transport", lambda settings, profile: _live_like_transport())
    monkeypatch.setattr("embodied_stack.body.driver.DEFAULT_ARM_LEASE_PATH", tmp_path / "runtime" / "serial" / "live_motion_arm.json")
    settings = build_settings(
        tmp_path,
        blink_serial_transport="live_serial",
        blink_serial_port="/dev/tty.fake",
        blink_servo_baud=1000000,
        blink_head_calibration=str(calibration_path),
    )
    driver = build_body_driver(settings)
    write_arm_lease(
        port="/dev/tty.fake",
        baud_rate=1000000,
        calibration_path=str(calibration_path),
        ttl_seconds=60,
        path=tmp_path / "runtime" / "serial" / "live_motion_arm.json",
    )
    driver.refresh_live_status(force=True)
    intent = build_character_semantic_intent(
        presence_status=CompanionPresenceStatus(state=CompanionPresenceState.TOOL_WORKING, slow_path_active=True),
        voice_status=CompanionVoiceLoopStatus(state=CompanionVoiceLoopState.THINKING),
        initiative_status=InitiativeStatus(),
        relationship_status=RelationshipContinuityStatus(open_follow_ups=["check reminders"]),
        fallback_state=FallbackState(),
        body_state=driver.state,
    )

    state = driver.apply_character_projection(intent=intent, profile=CharacterProjectionProfile.AVATAR_AND_ROBOT_HEAD)

    assert state.character_projection is not None
    assert state.character_projection.robot_head_applied is True
    assert state.character_projection.outcome == "robot_head_applied"
    assert state.last_command_outcome is not None
    assert state.last_command_outcome.command_type == "character_projection"
    assert state.latest_command_audit is not None
    assert state.latest_command_audit.command_type == "character_projection"
    assert state.latest_command_audit.after_readback


def test_safe_idle_recovers_neutral_before_torque_off(monkeypatch) -> None:
    transport = _live_like_transport()
    profile = default_head_profile()
    bridge = FeetechBodyBridge(transport=transport, profile=profile)
    neutral_frame = CompiledBodyFrame(
        frame_name="neutral_safe_idle",
        servo_targets={joint.joint_name: joint.neutral for joint in profile.joints if joint.enabled},
        duration_ms=profile.neutral_recovery_ms,
        hold_ms=200,
        compiler_notes=["test_safe_idle"],
    )

    recorded_sleep: list[float] = []
    torque_calls: list[tuple[list[int], bool]] = []
    monkeypatch.setattr("embodied_stack.body.serial.driver.time.sleep", lambda seconds: recorded_sleep.append(seconds))
    original_set_torque = transport.set_torque

    def recording_set_torque(servo_ids, enabled):
        torque_calls.append((list(servo_ids), enabled))
        return original_set_torque(servo_ids, enabled=enabled)

    monkeypatch.setattr(transport, "set_torque", recording_set_torque)

    outcome, health = bridge.safe_idle(torque_off=True, neutral_frame=neutral_frame)

    assert outcome.outcome_status == "neutral_recovered_torque_disabled"
    assert recorded_sleep == [0.42]
    assert torque_calls == [(sorted({servo_id for joint in profile.joints for servo_id in joint.servo_ids}), False)]
    assert all(item.target_position == neutral_frame.servo_targets[item.joint_name] for item in health.values())


@pytest.mark.parametrize("action_name", ["double_blink", "youthful_greeting", "soft_reengage"])
def test_apply_compiled_animation_records_frame_dwell_for_multi_frame_actions(monkeypatch, action_name: str) -> None:
    compiled = _compiled_animation_for_action(action_name)
    transport = _live_like_transport()
    profile = default_head_profile()
    calibration = calibration_module.calibration_from_profile(profile, calibration_kind="saved")
    bridge = FeetechBodyBridge(transport=transport, profile=profile, calibration=calibration)

    clock = {"now": 0.0}
    sleep_calls: list[float] = []

    def fake_perf_counter() -> float:
        return clock["now"]

    def fake_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)
        clock["now"] += seconds

    monkeypatch.setattr("embodied_stack.body.serial.driver.time.perf_counter", fake_perf_counter)
    monkeypatch.setattr("embodied_stack.body.serial.driver.time.sleep", fake_sleep)

    outcome, _health = bridge.apply_compiled_animation(compiled)

    expected_elapsed_ms = sum(frame.duration_ms + frame.hold_ms for frame in compiled.frames)
    assert outcome.executed_frame_count == len(compiled.frames)
    assert outcome.executed_frame_count > 1
    assert outcome.executed_frame_names == [frame.frame_name or f"frame_{index}" for index, frame in enumerate(compiled.frames)]
    assert outcome.per_frame_duration_ms == [int(frame.duration_ms) for frame in compiled.frames]
    assert outcome.per_frame_hold_ms == [int(frame.hold_ms) for frame in compiled.frames]
    assert outcome.elapsed_wall_clock_ms == pytest.approx(expected_elapsed_ms, abs=0.01)
    assert sum(sleep_calls) == pytest.approx(expected_elapsed_ms / 1000.0, abs=0.001)
    assert any(seconds > 0 for seconds in sleep_calls)
    assert outcome.final_frame_name == compiled.frames[-1].frame_name


def test_serial_driver_range_demo_records_live_execution_metadata(monkeypatch, tmp_path: Path) -> None:
    elapsed = {"value": 0.0}

    def fake_perf_counter() -> float:
        return elapsed["value"]

    def fake_sleep(seconds: float) -> None:
        elapsed["value"] += float(seconds)

    monkeypatch.setattr("embodied_stack.body.serial.driver.time.perf_counter", fake_perf_counter)
    monkeypatch.setattr("embodied_stack.body.serial.driver.time.sleep", fake_sleep)

    calibration_path = tmp_path / "runtime" / "calibrations" / "robot_head_live_v1.json"
    _saved_calibration(calibration_path)
    monkeypatch.setattr("embodied_stack.body.driver.build_servo_transport", lambda settings, profile: _live_like_transport())
    monkeypatch.setattr("embodied_stack.body.driver.DEFAULT_ARM_LEASE_PATH", tmp_path / "runtime" / "serial" / "live_motion_arm.json")
    settings = build_settings(
        tmp_path,
        blink_serial_transport="live_serial",
        blink_serial_port="/dev/tty.fake",
        blink_servo_baud=1000000,
        blink_head_calibration=str(calibration_path),
    )
    driver = build_body_driver(settings)
    write_arm_lease(
        port="/dev/tty.fake",
        baud_rate=1000000,
        calibration_path=str(calibration_path),
        ttl_seconds=60,
        path=tmp_path / "runtime" / "serial" / "live_motion_arm.json",
    )
    driver.refresh_live_status(force=True)

    result = driver.run_range_demo(preset_name="investor_show_joint_envelope_v1")

    assert result["status"] == "ok"
    assert result["payload"]["preview_only"] is False
    assert result["payload"]["live_requested"] is True
    assert result["payload"]["range_demo"]["joint_plans"]
    assert driver.state.latest_command_audit is not None
    assert driver.state.latest_command_audit.command_type == "body_range_demo"
    assert driver.state.latest_command_audit.executed_frame_count == len(driver.state.compiled_animation.frames)
    assert driver.state.latest_command_audit.executed_frame_count > 10
    assert driver.state.latest_command_audit.final_frame_name == "friendly_settle"
    assert driver.state.latest_command_audit.peak_normalized_pose["head_yaw"] != 0.0
    assert driver.state.latest_command_audit.tuning_lane == "default_live"
    assert "calm_settle" in driver.state.latest_command_audit.kinetics_profiles_used
    assert "head_yaw" in driver.state.latest_command_audit.remaining_margin_percent_by_family
    assert driver.state.latest_command_audit.motion_control is not None
    assert driver.state.latest_command_audit.motion_control.speed.effective_value == 120
    assert driver.state.latest_command_audit.motion_control.speed.verified is True
    assert driver.state.latest_command_audit.motion_control.acceleration.effective_value == 40
    assert driver.state.latest_command_audit.motion_control.acceleration.verified is True


def test_bridge_applies_compiled_animation_kinetics_settings() -> None:
    profile = default_head_profile()
    calibration = calibration_module.calibration_from_profile(profile, calibration_kind="saved")
    for joint in calibration.joint_records:
        joint.mirrored_direction_confirmed = True
    tuning = load_semantic_tuning(
        profile_name=profile.profile_name,
        calibration_path="runtime/calibrations/robot_head_live_v1.json",
        path="runtime/body/semantic_tuning/robot_head_live_v1.json",
    )
    compiler = SemanticBodyCompiler(profile=profile, calibration=calibration, tuning=tuning)
    transport = _live_like_transport()
    bridge = FeetechBodyBridge(transport=transport, profile=profile, calibration=calibration)

    compiled = compiler.apply_expression(BodyState(), "friendly").compiled_animation
    assert compiled is not None
    outcome, _ = bridge.apply_compiled_animation(compiled)

    assert outcome.tuning_lane == "default_live"
    assert "calm_settle" in outcome.kinetics_profiles_used
    assert outcome.motion_control is not None
    assert outcome.motion_control.speed.effective_value == 100
    assert outcome.motion_control.acceleration.effective_value == 32


def test_serial_driver_range_demo_blocks_without_live_motion_prerequisites(monkeypatch, tmp_path: Path) -> None:
    calibration_path = tmp_path / "runtime" / "calibrations" / "robot_head_live_v1.json"
    _saved_calibration(calibration_path)
    monkeypatch.setattr("embodied_stack.body.driver.build_servo_transport", lambda settings, profile: _live_like_transport())
    monkeypatch.setattr("embodied_stack.body.driver.DEFAULT_ARM_LEASE_PATH", tmp_path / "runtime" / "serial" / "live_motion_arm.json")
    settings = build_settings(
        tmp_path,
        blink_serial_transport="live_serial",
        blink_serial_port="/dev/tty.fake",
        blink_servo_baud=1000000,
        blink_head_calibration=str(calibration_path),
    )
    driver = build_body_driver(settings)

    result = driver.run_range_demo(preset_name="investor_show_joint_envelope_v1")

    assert result["status"] == "blocked"
    assert result["payload"]["blocked_reason"].startswith("motion_not_armed:")
    assert result["payload"]["preview_only"] is False
    assert driver.state.latest_command_audit is not None
    assert driver.state.latest_command_audit.command_type == "body_range_demo"
    assert driver.state.latest_command_audit.reason_code == "motion_not_armed"
    assert driver.state.latest_command_audit.executed_frame_count > 0


def test_serial_driver_range_demo_supports_named_sequence(monkeypatch, tmp_path: Path) -> None:
    elapsed = {"value": 0.0}

    def fake_perf_counter() -> float:
        return elapsed["value"]

    def fake_sleep(seconds: float) -> None:
        elapsed["value"] += float(seconds)

    monkeypatch.setattr("embodied_stack.body.serial.driver.time.perf_counter", fake_perf_counter)
    monkeypatch.setattr("embodied_stack.body.serial.driver.time.sleep", fake_sleep)

    calibration_path = tmp_path / "runtime" / "calibrations" / "robot_head_live_v1.json"
    _saved_calibration(calibration_path)
    monkeypatch.setattr("embodied_stack.body.driver.build_servo_transport", lambda settings, profile: _live_like_transport())
    monkeypatch.setattr("embodied_stack.body.driver.DEFAULT_ARM_LEASE_PATH", tmp_path / "runtime" / "serial" / "live_motion_arm.json")
    settings = build_settings(
        tmp_path,
        blink_serial_transport="live_serial",
        blink_serial_port="/dev/tty.fake",
        blink_servo_baud=1000000,
        blink_head_calibration=str(calibration_path),
    )
    driver = build_body_driver(settings)
    write_arm_lease(
        port="/dev/tty.fake",
        baud_rate=1000000,
        calibration_path=str(calibration_path),
        ttl_seconds=60,
        path=tmp_path / "runtime" / "serial" / "live_motion_arm.json",
    )
    driver.refresh_live_status(force=True)

    result = driver.run_range_demo(sequence_name="servo_range_showcase_v1")

    assert result["status"] == "ok"
    assert result["sequence_name"] == "servo_range_showcase_v1"
    assert result["preset_name"] == "servo_range_showcase_joint_envelope_v1"
    assert result["payload"]["available_sequences"] == list(available_range_demo_sequences())


def test_bridge_treats_packet_voltage_bits_alone_as_suspect(monkeypatch) -> None:
    profile = default_head_profile()
    calibration = calibration_module.calibration_from_profile(profile, calibration_kind="saved")
    bridge = FeetechBodyBridge(transport=_live_like_transport(), profile=profile, calibration=calibration)
    joint_ids = {joint.joint_name: joint.servo_ids[0] for joint in profile.joints if joint.enabled}
    targets = {
        "head_yaw": 2100,
        "eye_yaw": 2050,
        "eye_pitch": 2140,
        "upper_lid_left": 2050,
    }
    polls = [
        {
            joint_name: _health_record(
                joint_name=joint_name,
                servo_id=joint_ids[joint_name],
                target=target,
                current=target,
                error_bits=["input_voltage"],
            )
            for joint_name, target in targets.items()
        },
        {
            joint_name: _health_record(
                joint_name=joint_name,
                servo_id=joint_ids[joint_name],
                target=target,
                current=target,
            )
            for joint_name, target in targets.items()
        },
    ]

    monkeypatch.setattr(bridge, "poll_health", lambda **kwargs: polls.pop(0))
    monkeypatch.setattr("embodied_stack.body.serial.driver.time.sleep", lambda _seconds: None)

    outcome = BodyCommandOutcomeRecord(command_type="perform_animation", accepted=True, outcome_status="sent")
    health, updated_outcome = bridge._poll_health_with_confirmation(  # noqa: SLF001
        target_positions=targets,
        last_command_outcome=outcome,
        servo_ids=sorted(joint_ids.values()),
    )

    assert updated_outcome.fault_classification == "suspect_voltage_event"
    assert updated_outcome.confirmation_read_performed is True
    assert updated_outcome.confirmation_result == "cleared_on_retry"
    assert all(record.error_bits == [] for record in health.values())


def test_bridge_confirms_power_fault_when_voltage_and_divergence_persist(monkeypatch) -> None:
    profile = default_head_profile()
    calibration = calibration_module.calibration_from_profile(profile, calibration_kind="saved")
    bridge = FeetechBodyBridge(transport=_live_like_transport(), profile=profile, calibration=calibration)
    joint_ids = {joint.joint_name: joint.servo_ids[0] for joint in profile.joints if joint.enabled}
    targets = {
        "head_yaw": 2096,
        "eye_yaw": 2073,
        "eye_pitch": 2147,
        "upper_lid_left": 2048,
    }
    first_or_retry = {
        "head_yaw": _health_record(joint_name="head_yaw", servo_id=joint_ids["head_yaw"], target=2096, current=1641, error_bits=["input_voltage"]),
        "eye_yaw": _health_record(joint_name="eye_yaw", servo_id=joint_ids["eye_yaw"], target=2073, current=1756, error_bits=["input_voltage"]),
        "eye_pitch": _health_record(joint_name="eye_pitch", servo_id=joint_ids["eye_pitch"], target=2147, current=2440, error_bits=["input_voltage"]),
        "upper_lid_left": _health_record(joint_name="upper_lid_left", servo_id=joint_ids["upper_lid_left"], target=2048, current=1550, error_bits=["input_voltage"]),
    }
    polls = [first_or_retry, first_or_retry]

    monkeypatch.setattr(bridge, "poll_health", lambda **kwargs: polls.pop(0))
    monkeypatch.setattr("embodied_stack.body.serial.driver.time.sleep", lambda _seconds: None)
    monkeypatch.setattr(
        "embodied_stack.body.serial.driver.read_bench_health_many",
        lambda transport, servo_ids: {
            int(servo_id): {
                "servo_id": int(servo_id),
                "voltage": 85,
                "load": 120,
                "current": 80,
                "temperature": 26,
                "moving": False,
                "status_summary": "voltage=85",
            }
            for servo_id in servo_ids
        },
    )

    outcome = BodyCommandOutcomeRecord(command_type="perform_animation", accepted=True, outcome_status="sent")
    health, updated_outcome = bridge._poll_health_with_confirmation(  # noqa: SLF001
        target_positions=targets,
        last_command_outcome=outcome,
        servo_ids=sorted(joint_ids.values()),
    )

    assert updated_outcome.fault_classification == "confirmed_power_fault"
    assert updated_outcome.confirmation_result.startswith("confirmed_low_voltage:")
    assert all(record.voltage == 85 for record in health.values())


def test_bridge_retries_implausible_readback_before_trusting_it(monkeypatch) -> None:
    profile = default_head_profile()
    calibration = calibration_module.calibration_from_profile(profile, calibration_kind="saved")
    bridge = FeetechBodyBridge(transport=_live_like_transport(), profile=profile, calibration=calibration)
    joint_ids = {joint.joint_name: joint.servo_ids[0] for joint in profile.joints if joint.enabled}
    targets = {
        "head_yaw": 2096,
        "eye_yaw": 2073,
        "eye_pitch": 2147,
        "upper_lid_left": 2048,
    }
    polls = [
        {
            "head_yaw": _health_record(joint_name="head_yaw", servo_id=joint_ids["head_yaw"], target=2096, current=1641),
            "eye_yaw": _health_record(joint_name="eye_yaw", servo_id=joint_ids["eye_yaw"], target=2073, current=1756),
            "eye_pitch": _health_record(joint_name="eye_pitch", servo_id=joint_ids["eye_pitch"], target=2147, current=2440),
            "upper_lid_left": _health_record(joint_name="upper_lid_left", servo_id=joint_ids["upper_lid_left"], target=2048, current=1550),
        },
        {
            joint_name: _health_record(
                joint_name=joint_name,
                servo_id=joint_ids[joint_name],
                target=target,
                current=target,
            )
            for joint_name, target in targets.items()
        },
    ]

    monkeypatch.setattr(bridge, "poll_health", lambda **kwargs: polls.pop(0))
    monkeypatch.setattr("embodied_stack.body.serial.driver.time.sleep", lambda _seconds: None)

    outcome = BodyCommandOutcomeRecord(command_type="perform_animation", accepted=True, outcome_status="sent")
    health, updated_outcome = bridge._poll_health_with_confirmation(  # noqa: SLF001
        target_positions=targets,
        last_command_outcome=outcome,
        servo_ids=sorted(joint_ids.values()),
    )

    assert updated_outcome.fault_classification == "readback_implausible"
    assert updated_outcome.confirmation_result == "cleared_on_retry"
    assert all(record.current_position == record.target_position for record in health.values())


def test_bridge_keeps_live_write_accepted_when_post_write_health_poll_is_corrupt(monkeypatch) -> None:
    profile = default_head_profile()
    calibration = calibration_module.calibration_from_profile(profile, calibration_kind="saved")
    bridge = FeetechBodyBridge(transport=_live_like_transport(), profile=profile, calibration=calibration)
    joint_ids = {joint.joint_name: joint.servo_ids[0] for joint in profile.joints if joint.enabled}
    targets = {
        "head_yaw": 2115,
        "eye_yaw": 2073,
        "eye_pitch": 2170,
        "brow_left": 2111,
    }

    def _raise_poll(**_kwargs):
        raise ServoTransportError("invalid_reply", "checksum_mismatch:expected=0x8D:actual=0x03")

    monkeypatch.setattr(bridge, "poll_health", _raise_poll)
    monkeypatch.setattr(
        "embodied_stack.body.serial.driver.read_bench_health_many",
        lambda transport, servo_ids: {
            int(servo_id): {
                "servo_id": int(servo_id),
                "position": (
                    2125
                    if int(servo_id) == joint_ids["head_yaw"]
                    else 2291
                    if int(servo_id) == joint_ids["eye_pitch"]
                    else 2060
                    if int(servo_id) == joint_ids["eye_yaw"]
                    else 2115
                    if int(servo_id) == joint_ids["brow_left"]
                    else 2047
                ),
                "load": 0,
                "voltage": 110,
                "voltage_raw": 110,
                "voltage_volts": 11.0,
                "temperature": 26,
                "current": 0,
                "moving": False,
                "torque_enabled": True,
                "error_bits": [],
                "status_summary": "ok",
            }
            for servo_id in servo_ids
        },
    )

    outcome = BodyCommandOutcomeRecord(command_type="perform_animation", accepted=True, outcome_status="sent")
    health, updated_outcome = bridge._poll_health_with_confirmation(  # noqa: SLF001
        target_positions=targets,
        last_command_outcome=outcome,
        servo_ids=sorted(joint_ids.values()),
    )

    assert updated_outcome.accepted is True
    assert updated_outcome.rejected is False
    assert updated_outcome.outcome_status == "sent_with_readback_warning"
    assert updated_outcome.reason_code == "invalid_reply"
    assert updated_outcome.fault_classification == "readback_degraded"
    assert updated_outcome.confirmation_result == "health_poll_error:invalid_reply:checksum_mismatch:expected=0x8D:actual=0x03"
    assert health["head_yaw"].current_position == 2125
    assert health["eye_pitch"].current_position == 2291


def test_confirm_live_transport_retries_transient_invalid_reply(monkeypatch) -> None:
    profile = default_head_profile()

    class _FakeTransport:
        def __init__(self) -> None:
            self.status = type(
                "_Status",
                (),
                {
                    "mode": LIVE_SERIAL_MODE,
                    "confirmed_live": False,
                    "healthy": False,
                    "last_error": "invalid_reply:frame_too_short:4",
                },
            )()
            self.calls = 0

        def confirm_live(self, _servo_ids):
            self.calls += 1
            if self.calls < 2:
                self.status.confirmed_live = False
                self.status.healthy = False
                self.status.last_error = "invalid_reply:frame_too_short:4"
                return []
            self.status.confirmed_live = True
            self.status.healthy = True
            self.status.last_error = None
            return [1]

    transport = _FakeTransport()
    monkeypatch.setattr("embodied_stack.body.serial.bench.time.sleep", lambda _seconds: None)

    found = confirm_live_transport(transport, profile)

    assert found == [1]
    assert transport.calls == 2


def test_bridge_live_power_preflight_blocks_buswide_idle_input_voltage(monkeypatch) -> None:
    profile = default_head_profile()
    calibration = calibration_module.calibration_from_profile(profile, calibration_kind="saved")
    bridge = FeetechBodyBridge(transport=_live_like_transport(), profile=profile, calibration=calibration)

    def _bench_payload(_transport, servo_ids):
        return {
            int(servo_id): {
                "servo_id": int(servo_id),
                "position": 2047,
                "load": 80,
                "voltage": 35,
                "voltage_raw": 35,
                "voltage_volts": 3.5,
                "temperature": 25,
                "current": 40,
                "moving": False,
                "torque_enabled": True,
                "error_bits": ["input_voltage"],
                "status_summary": "voltage_raw=35; voltage_volts=3.5",
            }
            for servo_id in servo_ids
        }

    monkeypatch.setattr("embodied_stack.body.serial.driver.read_bench_health_many", _bench_payload)
    monkeypatch.setattr("embodied_stack.body.serial.driver.time.sleep", lambda _seconds: None)

    outcome, health = bridge.run_live_power_preflight()

    assert outcome.preflight_passed is False
    assert outcome.power_health_classification == "unhealthy_idle"
    assert outcome.preflight_failure_reason is not None
    assert all(record.voltage_raw == 35 for record in health.values())
    assert all(record.voltage_volts == 3.5 for record in health.values())
    assert all(record.power_health_classification == "unhealthy_idle" for record in health.values())


def test_bridge_live_power_preflight_passes_when_idle_health_is_clean(monkeypatch) -> None:
    profile = default_head_profile()
    calibration = calibration_module.calibration_from_profile(profile, calibration_kind="saved")
    bridge = FeetechBodyBridge(transport=_live_like_transport(), profile=profile, calibration=calibration)

    def _bench_payload(_transport, servo_ids):
        return {
            int(servo_id): {
                "servo_id": int(servo_id),
                "position": 2047,
                "load": 80,
                "voltage": 120,
                "voltage_raw": 120,
                "voltage_volts": 12.0,
                "temperature": 25,
                "current": 40,
                "moving": False,
                "torque_enabled": True,
                "error_bits": [],
                "status_summary": "voltage_raw=120; voltage_volts=12.0",
            }
            for servo_id in servo_ids
        }

    monkeypatch.setattr("embodied_stack.body.serial.driver.read_bench_health_many", _bench_payload)
    monkeypatch.setattr("embodied_stack.body.serial.driver.time.sleep", lambda _seconds: None)

    outcome, health = bridge.run_live_power_preflight()

    assert outcome.preflight_passed is True
    assert outcome.power_health_classification == "healthy"
    assert outcome.preflight_failure_reason is None
    assert all(record.voltage_raw == 120 for record in health.values())
    assert all(record.power_health_classification == "healthy" for record in health.values())
