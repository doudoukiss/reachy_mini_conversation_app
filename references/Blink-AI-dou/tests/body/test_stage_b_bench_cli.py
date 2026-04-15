from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

from embodied_stack.body import calibration as calibration_module
from embodied_stack.body.profile import default_head_profile
from embodied_stack.body.serial.bench import RANGE_CONFLICT_NOTE_PREFIX, execute_bench_command, neutral_targets, write_arm_lease
from embodied_stack.body.serial.driver import FeetechBodyBridge
from embodied_stack.body.serial.transport import DryRunServoTransport, LIVE_SERIAL_MODE
from embodied_stack.shared.contracts.body import utc_now


def _run_cli(args: list[str], capsys) -> tuple[int, dict]:
    exit_code = calibration_module.main(args)
    payload = json.loads(capsys.readouterr().out)
    return exit_code, payload


def _configure_stage_b_paths(monkeypatch, tmp_path: Path) -> tuple[Path, Path, Path]:
    calibration_path = tmp_path / "runtime" / "calibrations" / "robot_head_live_v1.json"
    arm_path = tmp_path / "runtime" / "serial" / "live_motion_arm.json"
    report_dir = tmp_path / "runtime" / "serial" / "motion_reports"
    monkeypatch.setattr(calibration_module, "DEFAULT_STAGE_B_CALIBRATION_PATH", str(calibration_path))
    monkeypatch.setattr(calibration_module, "DEFAULT_ARM_LEASE_PATH", arm_path)
    monkeypatch.setattr(calibration_module, "DEFAULT_MOTION_REPORT_DIR", report_dir)
    return calibration_path, arm_path, report_dir


def _live_like_transport(*, neutral_positions: dict[int, int]) -> DryRunServoTransport:
    profile = default_head_profile()
    transport = DryRunServoTransport(
        baud_rate=1000000,
        timeout_seconds=0.2,
        known_ids=sorted({servo_id for joint in profile.joints for servo_id in joint.servo_ids}),
        neutral_positions=neutral_positions,
    )
    transport.status.mode = LIVE_SERIAL_MODE
    transport.status.port = "/dev/tty.fake"
    transport.status.healthy = False
    transport.status.confirmed_live = False
    transport.status.reason_code = "transport_unconfirmed"
    return transport


def _saved_calibration(path: Path) -> None:
    profile = default_head_profile()
    calibration = calibration_module.calibration_from_profile(profile, calibration_kind="saved")
    for joint in calibration.joint_records:
        if joint.joint_name in {
            "lower_lid_left",
            "upper_lid_left",
            "lower_lid_right",
            "upper_lid_right",
            "brow_left",
            "brow_right",
        }:
            joint.mirrored_direction_confirmed = True
    calibration.coupling_validation = {
        "neck_pitch_roll": "ok",
        "mirrored_eyelids": "ok",
        "mirrored_brows": "ok",
        "eyes_follow_lids": "ok",
        "range_conflicts": "ok",
    }
    calibration_module.save_head_calibration(calibration, path)


def test_capture_neutral_live_bootstraps_and_marks_range_conflicts(monkeypatch, tmp_path: Path, capsys) -> None:
    calibration_path, _, _ = _configure_stage_b_paths(monkeypatch, tmp_path)
    live_positions = {
        1: 1665,
        2: 1372,
        3: 2681,
        4: 2050,
        5: 2048,
        6: 2045,
        7: 2006,
        8: 2148,
        9: 2073,
        10: 2094,
        11: 2205,
    }
    monkeypatch.setattr(
        calibration_module,
        "build_servo_transport",
        lambda settings, profile: _live_like_transport(neutral_positions=live_positions),
    )

    exit_code, payload = _run_cli(
        [
            "--transport",
            "live_serial",
            "--port",
            "/dev/tty.fake",
            "--baud",
            "1000000",
            "capture-neutral",
            "--confirm-live-write",
            "--confirm-visual-neutral",
        ],
        capsys,
    )

    assert exit_code == 0
    assert payload["calibration_kind"] == "captured"
    assert payload["output_path"] == str(calibration_path)
    assert set(payload["range_conflict_joints"]) == {"head_pitch_pair_a", "head_pitch_pair_b", "brow_right"}

    saved = json.loads(calibration_path.read_text(encoding="utf-8"))
    joint_records = {item["joint_name"]: item for item in saved["joint_records"]}
    assert joint_records["head_pitch_pair_a"]["neutral"] == 1372
    assert joint_records["head_pitch_pair_a"]["raw_min"] == 1372
    assert any(note.startswith(RANGE_CONFLICT_NOTE_PREFIX) for note in joint_records["head_pitch_pair_a"]["notes"])
    assert joint_records["head_pitch_pair_b"]["raw_max"] == 2681
    assert joint_records["brow_right"]["raw_max"] == 2205
    assert saved["coupling_validation"]["range_conflicts"] == "range_conflict_from_capture"


def test_stage_b_dry_run_flow_generates_reports(monkeypatch, tmp_path: Path, capsys) -> None:
    calibration_path, arm_path, report_dir = _configure_stage_b_paths(monkeypatch, tmp_path)
    profile = default_head_profile()
    joint_limits = {joint.joint_name: (joint.raw_min, joint.raw_max) for joint in profile.joints}

    exit_code, payload = _run_cli(
        [
            "--transport",
            "dry_run",
            "capture-neutral",
            "--output",
            str(calibration_path),
        ],
        capsys,
    )
    assert exit_code == 0
    assert payload["calibration_kind"] == "saved"

    for joint_name in [
        "lower_lid_left",
        "upper_lid_left",
        "lower_lid_right",
        "upper_lid_right",
        "brow_left",
        "brow_right",
    ]:
        raw_min, raw_max = joint_limits[joint_name]
        exit_code, _ = _run_cli(
            [
                "--calibration",
                str(calibration_path),
                "set-range",
                "--joint",
                joint_name,
                "--raw-min",
                str(raw_min),
                "--raw-max",
                str(raw_max),
                "--confirm-mirrored",
                "true",
                "--in-place",
            ],
            capsys,
        )
        assert exit_code == 0

    exit_code, payload = _run_cli(
        [
            "--calibration",
            str(calibration_path),
            "validate-coupling",
            "--in-place",
        ],
        capsys,
    )
    assert exit_code == 0
    assert payload["all_ok"] is True

    exit_code, payload = _run_cli(
        [
            "--transport",
            "dry_run",
            "--calibration",
            str(calibration_path),
            "arm-live-motion",
        ],
        capsys,
    )
    assert exit_code == 0
    assert payload["arm_status"]["armed"] is True
    assert arm_path.exists()

    exit_code, payload = _run_cli(
        [
            "--transport",
            "dry_run",
            "--calibration",
            str(calibration_path),
            "move-joint",
            "--joint",
            "head_yaw",
            "--delta",
            "500",
        ],
        capsys,
    )
    assert exit_code == 0
    assert payload["clamped_targets"]["head_yaw"] == 2147
    assert payload["success"] is True

    exit_code, payload = _run_cli(
        [
            "--transport",
            "dry_run",
            "--calibration",
            str(calibration_path),
            "write-neutral",
        ],
        capsys,
    )
    assert exit_code == 0
    assert payload["success"] is True

    exit_code, payload = _run_cli(
        [
            "--transport",
            "dry_run",
            "--calibration",
            str(calibration_path),
            "sync-move",
            "--group",
            "eyes_left_small",
        ],
        capsys,
    )
    assert exit_code == 0
    assert payload["clamped_targets"]["eye_yaw"] == 1947

    exit_code, payload = _run_cli(
        [
            "--transport",
            "dry_run",
            "--calibration",
            str(calibration_path),
            "safe-idle",
        ],
        capsys,
    )
    assert exit_code == 0
    assert payload["success"] is True

    exit_code, payload = _run_cli(
        [
            "disarm-live-motion",
        ],
        capsys,
    )
    assert exit_code == 0
    assert payload["cleared"] is True
    assert not arm_path.exists()
    assert len(list(report_dir.glob("*.json"))) >= 4


def test_execute_bench_command_waits_for_live_settle(monkeypatch, tmp_path: Path) -> None:
    calibration_path, _, report_dir = _configure_stage_b_paths(monkeypatch, tmp_path)
    profile = default_head_profile()
    _saved_calibration(calibration_path)
    calibration = calibration_module.load_head_calibration(str(calibration_path), profile=profile)
    neutral_positions = {
        servo_id: joint.neutral
        for joint in profile.joints
        for servo_id in joint.servo_ids
    }
    transport = _live_like_transport(neutral_positions=neutral_positions)
    transport.status.healthy = True
    transport.status.confirmed_live = True
    transport.status.reason_code = "ok"
    bridge = FeetechBodyBridge(transport=transport, profile=profile, calibration=calibration)

    slept: list[float] = []
    monkeypatch.setattr("embodied_stack.body.serial.bench.time.sleep", lambda seconds: slept.append(seconds))

    report = execute_bench_command(
        transport=transport,
        bridge=bridge,
        profile=profile,
        calibration=calibration,
        command_family="write_neutral",
        requested_targets=neutral_targets(calibration, profile),
        resolved_targets=neutral_targets(calibration, profile),
        duration_ms=800,
        report_dir=report_dir,
    )

    assert report["success"] is True
    assert report["settle_seconds"] == 0.95
    assert slept == [0.95]


def test_move_joint_refuses_range_conflict_after_capture(monkeypatch, tmp_path: Path, capsys) -> None:
    calibration_path, arm_path, _ = _configure_stage_b_paths(monkeypatch, tmp_path)
    _saved_calibration(calibration_path)
    payload = json.loads(calibration_path.read_text(encoding="utf-8"))
    for joint in payload["joint_records"]:
        if joint["joint_name"] == "head_yaw":
            joint["notes"].append(f"{RANGE_CONFLICT_NOTE_PREFIX}:2047:1647-2447")
            joint["error"] = "range_conflict_from_capture"
    payload["coupling_validation"]["range_conflicts"] = "range_conflict_from_capture"
    calibration_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    write_arm_lease(
        port="/dev/tty.fake",
        baud_rate=1000000,
        calibration_path=calibration_path,
        ttl_seconds=60,
        path=arm_path,
    )
    monkeypatch.setattr(
        calibration_module,
        "build_servo_transport",
        lambda settings, profile: _live_like_transport(neutral_positions={servo_id: 2047 for servo_id in range(1, 12)}),
    )

    exit_code, payload = _run_cli(
        [
            "--transport",
            "live_serial",
            "--port",
            "/dev/tty.fake",
            "--baud",
            "1000000",
            "--calibration",
            str(calibration_path),
            "move-joint",
            "--joint",
            "head_yaw",
            "--delta",
            "10",
        ],
        capsys,
    )

    assert exit_code == 1
    assert payload["reason_code"] == "range_conflict_from_capture"


def test_move_joint_rejects_expired_arm_lease(monkeypatch, tmp_path: Path, capsys) -> None:
    calibration_path, arm_path, _ = _configure_stage_b_paths(monkeypatch, tmp_path)
    _saved_calibration(calibration_path)
    arm_path.parent.mkdir(parents=True, exist_ok=True)
    arm_path.write_text(
        json.dumps(
            {
                "port": "/dev/tty.fake",
                "baud_rate": 1000000,
                "calibration_path": str(calibration_path.resolve()),
                "armed_at": str(utc_now() - timedelta(seconds=120)),
                "expires_at": str(utc_now() - timedelta(seconds=60)),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        calibration_module,
        "build_servo_transport",
        lambda settings, profile: _live_like_transport(neutral_positions={servo_id: 2047 for servo_id in range(1, 12)}),
    )

    exit_code, payload = _run_cli(
        [
            "--transport",
            "live_serial",
            "--port",
            "/dev/tty.fake",
            "--baud",
            "1000000",
            "--calibration",
            str(calibration_path),
            "move-joint",
            "--joint",
            "head_yaw",
            "--delta",
            "10",
        ],
        capsys,
    )

    assert exit_code == 1
    assert payload["reason_code"] == "motion_not_armed"
    assert "expired" in payload["detail"]


def test_fixture_replay_stage_b_commands_work(monkeypatch, tmp_path: Path, capsys) -> None:
    calibration_path, _, report_dir = _configure_stage_b_paths(monkeypatch, tmp_path)
    fixture_path = "src/embodied_stack/body/fixtures/robot_head_serial_fixture.json"

    exit_code, payload = _run_cli(
        [
            "--transport",
            "fixture_replay",
            "--fixture",
            fixture_path,
            "capture-neutral",
            "--output",
            str(calibration_path),
        ],
        capsys,
    )
    assert exit_code == 0
    assert payload["calibration_kind"] == "saved"

    exit_code, payload = _run_cli(
        [
            "--transport",
            "fixture_replay",
            "--fixture",
            fixture_path,
            "--calibration",
            str(calibration_path),
            "arm-live-motion",
        ],
        capsys,
    )
    assert exit_code == 0

    exit_code, payload = _run_cli(
        [
            "--transport",
            "fixture_replay",
            "--fixture",
            fixture_path,
            "--calibration",
            str(calibration_path),
            "move-joint",
            "--joint",
            "head_yaw",
            "--delta",
            "10",
        ],
        capsys,
    )
    assert exit_code == 0
    assert payload["success"] is True
    assert list(report_dir.glob("*.json"))


def test_stage_d_semantic_smoke_generates_bench_report(monkeypatch, tmp_path: Path, capsys) -> None:
    calibration_path, arm_path, report_dir = _configure_stage_b_paths(monkeypatch, tmp_path)
    _saved_calibration(calibration_path)

    exit_code, payload = _run_cli(
        [
            "--transport",
            "dry_run",
            "--calibration",
            str(calibration_path),
            "arm-live-motion",
        ],
        capsys,
    )
    assert exit_code == 0
    assert arm_path.exists()

    exit_code, payload = _run_cli(
        [
            "--transport",
            "dry_run",
            "--calibration",
            str(calibration_path),
            "semantic-smoke",
            "--action",
            "look_left",
            "--intensity",
            "0.8",
        ],
        capsys,
    )
    assert exit_code == 0
    assert payload["operation"] == "semantic_smoke"
    assert payload["action"]["canonical_name"] == "look_left"
    assert payload["success"] is True
    assert Path(payload["report_path"]).exists()
    assert list(report_dir.glob("*.json"))
