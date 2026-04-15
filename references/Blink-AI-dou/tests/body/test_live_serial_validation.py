from __future__ import annotations

import argparse
import os
from pathlib import Path

import pytest

from embodied_stack.body import calibration as calibration_module


def _required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        pytest.skip(f"{name} is required for live serial hardware validation.")
    return value


def _live_args(command: str, **overrides) -> argparse.Namespace:
    payload = {
        "profile": os.getenv("BLINK_HEAD_PROFILE", "src/embodied_stack/body/profiles/robot_head_v1.json"),
        "calibration": os.getenv("BLINK_HEAD_CALIBRATION", "runtime/calibrations/robot_head_live_v1.json"),
        "transport": "live_serial",
        "port": _required_env("BLINK_SERIAL_PORT"),
        "baud": int(os.getenv("BLINK_SERVO_BAUD", "1000000")),
        "timeout_seconds": float(os.getenv("BLINK_SERIAL_TIMEOUT_SECONDS", "0.2")),
        "fixture": None,
        "author": "pytest_live_serial",
        "command": command,
    }
    payload.update(overrides)
    return argparse.Namespace(**payload)


@pytest.mark.live_serial
def test_live_serial_readback_and_safe_idle(tmp_path: Path) -> None:
    doctor = calibration_module.doctor_command(
        _live_args(
            "doctor",
            ids="1-11",
            auto_scan_baud=True,
            report=str(tmp_path / "doctor_report.json"),
        )
    )
    assert doctor["responsive_ids"]

    positions = calibration_module.read_positions(_live_args("read_position", ids="1-11"))
    assert all("position" in payload for payload in positions["positions"].values())

    health = calibration_module.read_health_report(_live_args("read_health", ids="1-11"))
    assert all("error" not in payload for payload in health["health_reads"].values())

    safe_idle = calibration_module.safe_idle_command(_live_args("safe_idle"))
    assert safe_idle["success"] is True


@pytest.mark.live_serial_motion
def test_live_serial_motion_smoke_sequence() -> None:
    calibration_path = Path(_required_env("BLINK_HEAD_CALIBRATION"))
    if not calibration_path.exists():
        pytest.skip("BLINK_HEAD_CALIBRATION must point to an existing saved calibration for live serial motion tests.")

    arm_payload = calibration_module.arm_live_motion(_live_args("arm_live_motion", ttl_seconds=60.0))
    assert arm_payload["arm_status"]["armed"] is True
    try:
        move = calibration_module.move_joint_command(
            _live_args(
                "move_joint",
                joint="head_yaw",
                delta=20,
                target=None,
                duration_ms=600,
            )
        )
        assert move["success"] is True

        semantic = calibration_module.semantic_smoke_command(
            _live_args(
                "semantic_smoke",
                action="look_left",
                intensity=0.5,
                repeat_count=1,
                note="pytest_live_serial_motion",
                allow_bench_actions=False,
                confirm_live_write=True,
            )
        )
        assert semantic["success"] is True

        safe_idle = calibration_module.safe_idle_command(_live_args("safe_idle"))
        assert safe_idle["success"] is True
    finally:
        calibration_module.disarm_live_motion(_live_args("disarm_live_motion"))
