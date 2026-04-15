from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from embodied_stack.body.calibration import main
from embodied_stack.body import calibration as calibration_module
from embodied_stack.body.profile import default_head_profile
from embodied_stack.body.serial.transport import SerialPortRecord
from embodied_stack.shared.contracts.body import ServoHealthRecord


def test_calibration_cli_scan_runs_in_dry_run_mode(capsys) -> None:
    exit_code = main(
        [
            "--profile",
            "src/embodied_stack/body/profiles/robot_head_v1.json",
            "--transport",
            "dry_run",
            "scan",
            "--ids",
            "1-3",
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 0
    assert payload["operation"] == "scan"
    assert payload["baud_results"][0]["found_ids"] == [1, 2, 3]


def test_calibration_cli_dump_writes_v2_record(tmp_path: Path, capsys) -> None:
    output_path = tmp_path / "head_calibration.json"

    exit_code = main(
        [
            "--profile",
            "src/embodied_stack/body/profiles/robot_head_v1.json",
            "--transport",
            "dry_run",
            "dump-profile-calibration",
            "--output",
            str(output_path),
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 0
    assert payload["schema_version"] == "blink_head_calibration/v2"
    assert payload["operation"] == "dump_profile_calibration"
    assert payload["provenance_source"] == "dry_run"
    assert payload["transport_boundary_version"] == "semantic_body_transport/v1"
    assert output_path.exists()


def test_calibration_cli_capture_neutral_updates_joint_records(capsys) -> None:
    exit_code = main(
        [
            "--profile",
            "src/embodied_stack/body/profiles/robot_head_v1.json",
            "--transport",
            "dry_run",
            "capture-neutral",
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 0
    assert payload["operation"] == "capture_neutral"
    assert payload["operation_group"] == "read_safe"
    assert payload["provenance_source"] == "dry_run"
    assert payload["joint_records"][0]["neutral"] == 2047


def test_calibration_cli_power_preflight_reports_idle_power_truth(monkeypatch, capsys) -> None:
    profile = default_head_profile()
    calibration = calibration_module.calibration_from_profile(profile, calibration_kind="saved")
    calibration.coupling_validation = {
        "neck_pitch_roll": "ok",
        "mirrored_eyelids": "ok",
        "mirrored_brows": "ok",
        "eyes_follow_lids": "ok",
        "range_conflicts": "ok",
    }

    class FakeStatus:
        mode = "live_serial"
        port = "/dev/tty.fake"
        baud_rate = 1000000
        timeout_seconds = 0.2
        healthy = True
        confirmed_live = True
        reason_code = "ok"
        last_error = None
        last_operation = None
        last_good_reply = None
        transaction_count = 0

    class FakeTransport:
        status = FakeStatus()

        def history_payload(self) -> list[dict[str, object]]:
            return []

        def close(self) -> None:
            return None

    monkeypatch.setattr(calibration_module, "build_servo_transport", lambda settings, profile: FakeTransport())
    monkeypatch.setattr(calibration_module, "load_head_calibration", lambda path, *, profile=None: calibration)

    def _fake_preflight(self):
        outcome = calibration_module.BodyCommandOutcomeRecord(
            command_type="body_power_preflight",
            requested_action_name="live_power_preflight",
            canonical_action_name="live_power_preflight",
            source_action_name="live_power_preflight",
            outcome_status="preflight_blocked",
            accepted=False,
            rejected=True,
            transport_mode="live_serial",
            reason_code="unhealthy_idle",
            power_health_classification="unhealthy_idle",
            preflight_passed=False,
            preflight_failure_reason="bench_voltage_low:11",
            idle_voltage_snapshot={
                "head_yaw": {
                    "voltage_raw": 35,
                    "voltage_volts": 3.5,
                    "error_bits": ["input_voltage"],
                }
            },
        )
        health = {
            "head_yaw": ServoHealthRecord(
                joint_name="head_yaw",
                servo_id=1,
                current_position=2047,
                voltage_raw=35,
                voltage_volts=3.5,
                error_bits=["input_voltage"],
                power_health_classification="unhealthy_idle",
            )
        }
        return outcome, health

    monkeypatch.setattr(calibration_module.FeetechBodyBridge, "run_live_power_preflight", _fake_preflight)

    exit_code = main(
        [
            "--profile",
            "src/embodied_stack/body/profiles/robot_head_v1.json",
            "--transport",
            "live_serial",
            "--port",
            "/dev/tty.fake",
            "power-preflight",
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 0
    assert payload["operation"] == "power_preflight"
    assert payload["preflight_passed"] is False
    assert payload["power_health_classification"] == "unhealthy_idle"
    assert payload["preflight_failure_reason"] == "bench_voltage_low:11"
    assert payload["idle_voltage_snapshot"]["head_yaw"]["voltage_raw"] == 35
    assert payload["servo_health"]["head_yaw"]["power_health_classification"] == "unhealthy_idle"


def test_calibration_cli_live_write_requires_arm(monkeypatch) -> None:
    profile = default_head_profile()
    calibration = calibration_module.calibration_from_profile(profile, calibration_kind="saved")
    calibration.coupling_validation = {
        "neck_pitch_roll": "ok",
        "mirrored_eyelids": "ok",
        "mirrored_brows": "ok",
        "eyes_follow_lids": "ok",
        "range_conflicts": "ok",
    }

    class FakeStatus:
        mode = "live_serial"
        port = "/dev/tty.fake"
        baud_rate = 1000000
        timeout_seconds = 0.2
        healthy = True
        confirmed_live = True
        reason_code = "ok"
        last_error = None
        last_operation = None
        last_good_reply = None
        transaction_count = 0

    class FakeTransport:
        status = FakeStatus()

        def write_target_position(self, *args, **kwargs):
            return None

        def close(self) -> None:
            return None

    monkeypatch.setattr(calibration_module, "build_servo_transport", lambda settings, profile: FakeTransport())
    monkeypatch.setattr(calibration_module, "load_head_calibration", lambda path, *, profile=None: calibration)

    args = calibration_module.build_parser().parse_args(
        [
            "--profile",
            "src/embodied_stack/body/profiles/robot_head_v1.json",
            "--transport",
            "live_serial",
            "--port",
            "/dev/tty.fake",
            "write-neutral",
        ]
    )

    with pytest.raises(calibration_module.ServoTransportError) as exc_info:
        args.handler(args)

    assert exc_info.value.classification == "motion_not_armed"


def test_revalidate_live_ranges_requires_explicit_widen_confirmation(monkeypatch, tmp_path: Path) -> None:
    profile = default_head_profile()
    calibration = calibration_module.calibration_from_profile(profile, calibration_kind="saved")
    calibration.coupling_validation = {
        "neck_pitch_roll": "ok",
        "mirrored_eyelids": "ok",
        "mirrored_brows": "ok",
        "eyes_follow_lids": "ok",
        "range_conflicts": "ok",
    }

    class FakeStatus:
        mode = "live_serial"
        port = "/dev/tty.fake"
        baud_rate = 1000000
        timeout_seconds = 0.2
        healthy = True
        confirmed_live = True
        reason_code = "ok"
        last_error = None
        last_operation = None
        last_good_reply = None
        transaction_count = 0

    class FakeTransport:
        status = FakeStatus()

        def close(self) -> None:
            return None

    monkeypatch.setattr(calibration_module, "build_servo_transport", lambda settings, profile: FakeTransport())
    monkeypatch.setattr(calibration_module, "load_head_calibration", lambda path, *, profile=None: calibration)

    args = calibration_module.build_parser().parse_args(
        [
            "--profile",
            "src/embodied_stack/body/profiles/robot_head_v1.json",
            "--calibration",
            str(tmp_path / "robot_head_live_v1.json"),
            "--transport",
            "live_serial",
            "--port",
            "/dev/tty.fake",
            "revalidate-live-ranges",
            "--confirm-live-write",
            "--confirm-mechanical-clearance",
        ]
    )

    with pytest.raises(calibration_module.ServoTransportError) as exc_info:
        args.handler(args)

    assert exc_info.value.classification == "operator_confirmation_required"
    assert "confirm_widen_beyond_profile" in exc_info.value.detail


def test_revalidate_live_ranges_persists_updated_calibration(monkeypatch, tmp_path: Path) -> None:
    profile_path = "src/embodied_stack/body/profiles/robot_head_v1.json"
    calibration_path = tmp_path / "runtime" / "calibrations" / "robot_head_live_v1.json"
    output_dir = tmp_path / "runtime" / "serial" / "revalidation"
    profile = default_head_profile()
    calibration = calibration_module.calibration_from_profile(profile, calibration_kind="saved")
    calibration.coupling_validation = {
        "neck_pitch_roll": "ok",
        "mirrored_eyelids": "ok",
        "mirrored_brows": "ok",
        "eyes_follow_lids": "ok",
        "range_conflicts": "ok",
    }
    calibration_module.save_head_calibration(calibration, calibration_path)

    class FakeStatus:
        mode = "live_serial"
        port = "/dev/tty.fake"
        baud_rate = 1000000
        timeout_seconds = 0.2
        healthy = True
        confirmed_live = True
        reason_code = "ok"
        last_error = None
        last_operation = None
        last_good_reply = None
        transaction_count = 0

    class FakeTransport:
        status = FakeStatus()

        def close(self) -> None:
            return None

    monkeypatch.setattr(calibration_module, "build_servo_transport", lambda settings, profile: FakeTransport())
    monkeypatch.setattr(calibration_module, "validate_motion_arm", lambda **kwargs: {"ok": True})
    monkeypatch.setattr(
        calibration_module,
        "read_bench_snapshot",
        lambda transport, servo_ids: {
            "positions": {int(servo_id): {"position": 2047} for servo_id in servo_ids},
            "health": {int(servo_id): {"servo_id": int(servo_id), "error_bits": [], "load": 0} for servo_id in servo_ids},
        },
    )
    monkeypatch.setattr(
        calibration_module,
        "recenter_neck_pair_neutral",
        lambda **kwargs: (
            calibration_module.apply_revalidation_overrides(
                calibration=kwargs["calibration"],
                neutral_overrides={"head_pitch_pair_a": 2042, "head_pitch_pair_b": 2054},
            ),
            {"operation": "neck_pair_neutral_recenter", "readback": {"head_pitch_pair_a": 2042, "head_pitch_pair_b": 2054}},
        ),
    )
    monkeypatch.setattr(
        calibration_module,
        "run_family_revalidation",
        lambda **kwargs: {
            "family_name": kwargs["family_name"],
            "probe_results": [],
            "side_overrides": {"head_yaw": {"low": 1600, "high": 2500}} if kwargs["family_name"] == "head_yaw" else {},
            "widened_beyond_profile": {"head_yaw": True} if kwargs["family_name"] == "head_yaw" else {},
        },
    )
    monkeypatch.setattr(
        calibration_module,
        "build_range_demo_plan",
        lambda **kwargs: SimpleNamespace(usable_range_audit=None),
    )

    args = calibration_module.build_parser().parse_args(
        [
            "--profile",
            profile_path,
            "--calibration",
            str(calibration_path),
            "--transport",
            "live_serial",
            "--port",
            "/dev/tty.fake",
            "--baud",
            "1000000",
            "revalidate-live-ranges",
            "--output-dir",
            str(output_dir),
            "--confirm-live-write",
            "--confirm-mechanical-clearance",
            "--confirm-widen-beyond-profile",
        ]
    )

    payload = args.handler(args)
    updated = calibration_module.load_head_calibration(calibration_path, profile=profile)
    head_yaw = next(item for item in updated.joint_records if item.joint_name == "head_yaw")
    pitch_a = next(item for item in updated.joint_records if item.joint_name == "head_pitch_pair_a")
    pitch_b = next(item for item in updated.joint_records if item.joint_name == "head_pitch_pair_b")

    assert payload["operation"] == "revalidate_live_ranges"
    assert head_yaw.raw_min == 1600
    assert head_yaw.raw_max == 2500
    assert pitch_a.neutral == 2042
    assert pitch_b.neutral == 2054
    assert Path(payload["artifact_paths"]["session_summary"]).exists()
    assert Path(payload["artifact_paths"]["doc_preview"]).exists()


def test_calibration_cli_read_health_reports_bench_fields(capsys) -> None:
    exit_code = main(
        [
            "--profile",
            "src/embodied_stack/body/profiles/robot_head_v1.json",
            "--transport",
            "dry_run",
            "read-health",
            "--ids",
            "1",
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 0
    assert payload["operation"] == "read_health"
    assert payload["health_reads"]["1"]["position"] == 2047
    assert payload["health_reads"]["1"]["speed"] == 0
    assert payload["health_reads"]["1"]["load"] == 0
    assert payload["health_reads"]["1"]["voltage"] == 120
    assert payload["health_reads"]["1"]["temperature"] == 25
    assert payload["health_reads"]["1"]["moving"] is False


def test_revalidate_live_ranges_does_not_persist_neck_tilt_as_global_joint_bounds(
    monkeypatch, tmp_path: Path
) -> None:
    profile_path = "src/embodied_stack/body/profiles/robot_head_v1.json"
    profile = calibration_module.load_head_profile(profile_path)
    calibration = calibration_module.calibration_from_profile(profile, calibration_kind="captured")
    calibration.coupling_validation = {
        "neck_pitch_roll": "ok",
        "mirrored_eyelids": "ok",
        "mirrored_brows": "ok",
        "eyes_follow_lids": "ok",
        "range_conflicts": "ok",
    }
    calibration_path = tmp_path / "robot_head_live_v1.json"
    calibration_module.save_head_calibration(calibration, calibration_path)
    output_dir = tmp_path / "artifacts"

    class FakeStatus:
        mode = "live_serial"
        port = "/dev/tty.fake"
        baud_rate = 1_000_000
        timeout_seconds = 0.2
        healthy = True
        confirmed_live = True
        reason_code = "ok"
        last_error = None
        last_operation = "read"
        last_good_reply = "ok"
        transaction_count = 1

    class FakeTransport:
        status = FakeStatus()

        def close(self) -> None:
            return None

    monkeypatch.setattr(calibration_module, "build_servo_transport", lambda settings, profile: FakeTransport())
    monkeypatch.setattr(calibration_module, "validate_motion_arm", lambda **kwargs: {"ok": True})
    monkeypatch.setattr(
        calibration_module,
        "read_bench_snapshot",
        lambda transport, servo_ids: {
            "positions": {int(servo_id): {"position": 2047} for servo_id in servo_ids},
            "health": {int(servo_id): {"servo_id": int(servo_id), "error_bits": [], "load": 0} for servo_id in servo_ids},
        },
    )
    monkeypatch.setattr(
        calibration_module,
        "recenter_neck_pair_neutral",
        lambda **kwargs: (
            calibration_module.apply_revalidation_overrides(
                calibration=kwargs["calibration"],
                neutral_overrides={"head_pitch_pair_a": 2042, "head_pitch_pair_b": 2054},
            ),
            {"operation": "neck_pair_neutral_recenter", "readback": {"head_pitch_pair_a": 2042, "head_pitch_pair_b": 2054}},
        ),
    )
    monkeypatch.setattr(
        calibration_module,
        "run_family_revalidation",
        lambda **kwargs: {
            "family_name": kwargs["family_name"],
            "probe_results": [],
            "side_overrides": {"head_pitch_pair_b": {"low": 2009}, "head_pitch_pair_a": {"high": 2251}},
            "widened_beyond_profile": {},
        },
    )
    monkeypatch.setattr(
        calibration_module,
        "build_range_demo_plan",
        lambda **kwargs: SimpleNamespace(usable_range_audit=None),
    )

    args = calibration_module.build_parser().parse_args(
        [
            "--profile",
            profile_path,
            "--calibration",
            str(calibration_path),
            "--transport",
            "live_serial",
            "--port",
            "/dev/tty.fake",
            "--baud",
            "1000000",
            "revalidate-live-ranges",
            "--family",
            "neck_tilt",
            "--output-dir",
            str(output_dir),
            "--confirm-live-write",
            "--confirm-mechanical-clearance",
            "--confirm-widen-beyond-profile",
        ]
    )

    payload = args.handler(args)
    updated = calibration_module.load_head_calibration(calibration_path, profile=profile)
    pitch_a = next(item for item in updated.joint_records if item.joint_name == "head_pitch_pair_a")
    pitch_b = next(item for item in updated.joint_records if item.joint_name == "head_pitch_pair_b")

    assert payload["operation"] == "revalidate_live_ranges"
    assert pitch_a.raw_max == 2647
    assert pitch_b.raw_min == 1447
    assert payload["family_results"][0]["side_overrides"]["head_pitch_pair_b"]["low"] == 2009
    assert payload["family_results"][0]["side_overrides"]["head_pitch_pair_a"]["high"] == 2251


def test_calibration_cli_doctor_writes_report(monkeypatch, tmp_path: Path, capsys) -> None:
    monkeypatch.setattr(
        "embodied_stack.body.serial.doctor.list_serial_ports",
        lambda: [SerialPortRecord(device="/dev/cu.usbserial-demo", recommended=True, kind="recommended")],
    )
    report_path = tmp_path / "bringup_report.json"

    exit_code = main(
        [
            "--profile",
            "src/embodied_stack/body/profiles/robot_head_v1.json",
            "--transport",
            "dry_run",
            "doctor",
            "--ids",
            "1-2",
            "--report",
            str(report_path),
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 0
    assert payload["report_path"] == str(report_path)
    assert payload["responsive_ids"] == [1, 2]
    assert payload["suggested_env"]["env"]["BLINK_SERIAL_PORT"] == "/dev/cu.usbserial-demo"
    assert report_path.exists()


def test_calibration_cli_suggest_env_uses_preferred_port(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        calibration_module,
        "list_serial_ports",
        lambda: [SerialPortRecord(device="/dev/cu.usbserial-demo", recommended=True, kind="recommended")],
    )

    exit_code = main(
        [
            "--profile",
            "src/embodied_stack/body/profiles/robot_head_v1.json",
            "suggest-env",
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 0
    assert payload["operation"] == "suggest_env"
    assert payload["chosen_port"] == "/dev/cu.usbserial-demo"
    assert "BLINK_RUNTIME_MODE=desktop_serial_body" in payload["suggested_env"]["shell_block"]


def test_build_settings_from_args_preserves_env_serial_port_when_cli_port_is_omitted(monkeypatch) -> None:
    monkeypatch.setenv("BLINK_SERIAL_PORT", "/dev/cu.env-port")

    args = calibration_module.build_parser().parse_args(
        [
            "--profile",
            "src/embodied_stack/body/profiles/robot_head_v1.json",
            "--transport",
            "live_serial",
            "arm-live-motion",
        ]
    )

    settings = calibration_module.build_settings_from_args(args)

    assert settings.blink_serial_port == "/dev/cu.env-port"


def test_calibration_cli_lists_stage_d_semantic_actions(capsys) -> None:
    exit_code = main(
        [
            "--profile",
            "src/embodied_stack/body/profiles/robot_head_v1.json",
            "list-semantic-actions",
            "--smoke-safe-only",
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 0
    assert payload["operation"] == "list_semantic_actions"
    assert any(item["canonical_name"] == "look_left" for item in payload["semantic_actions"])


def test_calibration_cli_motion_config_reports_effective_speed_and_acceleration(capsys) -> None:
    exit_code = main(
        [
            "--profile",
            "src/embodied_stack/body/profiles/robot_head_v1.json",
            "--transport",
            "dry_run",
            "motion-config",
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 0
    assert payload["operation"] == "motion_config"
    assert payload["motion_control"]["speed"]["effective_value"] == 120
    assert payload["motion_control"]["acceleration"]["effective_value"] == 40


def test_calibration_cli_usable_range_reports_showcase_plan(capsys) -> None:
    exit_code = main(
        [
            "--profile",
            "src/embodied_stack/body/profiles/robot_head_v1.json",
            "usable-range",
            "--sequence",
            "servo_range_showcase_v1",
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 0
    assert payload["operation"] == "usable_range"
    assert payload["range_demo_sequence"] == "servo_range_showcase_v1"
    assert payload["range_demo_preset"] == "servo_range_showcase_joint_envelope_v1"
    assert payload["range_demo_plan"]["executed_frame_count"] >= 35


def test_calibration_cli_range_demo_runs_in_dry_run_mode(capsys) -> None:
    exit_code = main(
        [
            "--profile",
            "src/embodied_stack/body/profiles/robot_head_v1.json",
            "--transport",
            "dry_run",
            "range-demo",
            "--sequence",
            "servo_range_showcase_v1",
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 0
    assert payload["operation"] == "range_demo"
    assert payload["sequence_name"] == "servo_range_showcase_v1"
    assert payload["range_demo_plan"]["preset_name"] == "servo_range_showcase_joint_envelope_v1"
    assert payload["outcome"]["motion_control"]["acceleration"]["effective_value"] == 40


def test_calibration_cli_teacher_review_writes_stage_d_artifacts(tmp_path: Path, monkeypatch, capsys) -> None:
    tuning_path = tmp_path / "runtime" / "body" / "semantic_tuning" / "robot_head_live_v1.json"
    review_path = tmp_path / "runtime" / "body" / "semantic_tuning" / "teacher_reviews.jsonl"
    monkeypatch.setattr(calibration_module, "DEFAULT_SEMANTIC_TUNING_PATH", tuning_path)
    monkeypatch.setattr(calibration_module, "DEFAULT_TEACHER_REVIEW_PATH", review_path)

    exit_code = main(
        [
            "--profile",
            "src/embodied_stack/body/profiles/robot_head_v1.json",
            "teacher-review",
            "--action",
            "look_left",
            "--review",
            "adjust",
            "--proposed-tuning-delta",
            '{"action_overrides":{"look_left":{"pose_offsets":{"eye_yaw":-0.05}}}}',
            "--apply-tuning",
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 0
    assert payload["operation"] == "teacher_review"
    assert payload["review"]["action"] == "look_left"
    assert tuning_path.exists()
    assert review_path.exists()


def test_calibration_cli_servo_lab_catalog_lists_all_joints(capsys) -> None:
    exit_code = main(
        [
            "--profile",
            "src/embodied_stack/body/profiles/robot_head_v1.json",
            "--transport",
            "dry_run",
            "servo-lab-catalog",
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 0
    assert payload["operation"] == "servo_lab_catalog"
    assert payload["payload"]["joint_count"] == 11


def test_calibration_cli_servo_lab_move_bypasses_stage_b_smoke_limit(capsys) -> None:
    exit_code = main(
        [
            "--profile",
            "src/embodied_stack/body/profiles/robot_head_v1.json",
            "--transport",
            "dry_run",
            "servo-lab-move",
            "--joint",
            "head_yaw",
            "--reference-mode",
            "current_delta",
            "--delta-counts",
            "150",
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 0
    assert payload["operation"] == "servo_lab_move"
    assert payload["servo_lab_move"]["effective_target"] == 2197
    assert payload["motion_control_summary"]["speed_override_supported"] is True


def test_calibration_cli_servo_lab_save_calibration_updates_output(tmp_path: Path, capsys) -> None:
    output_path = tmp_path / "servo_lab_saved.json"
    saved = tmp_path / "robot_head_live_v1.json"
    profile = default_head_profile()
    calibration = calibration_module.calibration_from_profile(profile, calibration_kind="saved")
    calibration_module.save_head_calibration(calibration, saved)

    exit_code = main(
        [
            "--profile",
            "src/embodied_stack/body/profiles/robot_head_v1.json",
            "--calibration",
            str(saved),
            "--transport",
            "dry_run",
            "servo-lab-save-calibration",
            "--joint",
            "head_yaw",
            "--raw-min",
            "1700",
            "--raw-max",
            "2400",
            "--output",
            str(output_path),
        ]
    )

    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert exit_code == 0
    assert payload["operation"] == "servo_lab_save_calibration"
    assert payload["payload"]["output_path"] == str(output_path)
    written = json.loads(output_path.read_text(encoding="utf-8"))
    head_yaw = next(item for item in written["joint_records"] if item["joint_name"] == "head_yaw")
    assert head_yaw["raw_min"] == 1700
    assert head_yaw["raw_max"] == 2400
