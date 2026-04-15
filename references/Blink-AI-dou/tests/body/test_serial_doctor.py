from __future__ import annotations

import json
from pathlib import Path

from embodied_stack.body.profile import default_head_profile
from embodied_stack.body.serial.doctor import choose_preferred_port, resolve_baud_candidates, run_serial_doctor
from embodied_stack.body.serial.health import decode_bench_health_payload
from embodied_stack.body.serial.transport import SerialPortRecord, classify_open_failure


def test_resolve_baud_candidates_prefers_explicit_then_profile_then_auto_scan() -> None:
    profile = default_head_profile().model_copy(
        update={"baud_rate": 115200, "auto_scan_baud_rates": [115200, 1000000, 38400]}
    )

    assert resolve_baud_candidates(profile, explicit_baud=57600, auto_scan_baud=True) == [57600, 115200, 1000000, 38400]


def test_choose_preferred_port_auto_selects_single_recommended() -> None:
    ports = [
        SerialPortRecord(device="/dev/tty.usbserial-demo", recommended=False, kind="alternate").to_dict(),
        SerialPortRecord(device="/dev/cu.usbserial-demo", recommended=True, kind="recommended").to_dict(),
    ]

    chosen_port, reason = choose_preferred_port(ports, explicit_port=None)

    assert chosen_port == "/dev/cu.usbserial-demo"
    assert reason == "single_recommended"


def test_classify_open_failure_maps_missing_and_busy() -> None:
    missing_classification, _ = classify_open_failure(FileNotFoundError("No such file or directory"))
    busy_classification, _ = classify_open_failure(PermissionError("Resource busy"))

    assert missing_classification == "missing_port"
    assert busy_classification == "port_busy"


def test_decode_bench_health_payload_handles_optional_current() -> None:
    payload = bytes.fromhex("FF 07 10 00 20 00 78 19 00 05 01")

    health = decode_bench_health_payload(payload, current_payload=bytes.fromhex("34 12"), torque_enabled=True, packet_error=0)

    assert health["position"] == 2047
    assert health["speed"] == 16
    assert health["load"] == 32
    assert health["voltage"] == 120
    assert health["temperature"] == 25
    assert health["status_bits"] == 5
    assert health["status_flags"] == ["bit0", "bit2"]
    assert health["moving"] is True
    assert health["current"] == 0x1234


def test_run_serial_doctor_writes_report_in_dry_run_mode(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        "embodied_stack.body.serial.doctor.list_serial_ports",
        lambda: [SerialPortRecord(device="/dev/cu.usbserial-demo", recommended=True, kind="recommended")],
    )
    report_path = tmp_path / "bringup_report.json"

    report = run_serial_doctor(
        profile_path="src/embodied_stack/body/profiles/robot_head_v1.json",
        calibration_path="src/embodied_stack/body/profiles/robot_head_v1.calibration_template.json",
        transport_mode="dry_run",
        port=None,
        explicit_baud=None,
        timeout_seconds=0.2,
        fixture_path=None,
        ids="1-3",
        auto_scan_baud=True,
        report_path=report_path,
    )

    assert report["responsive_ids"] == [1, 2, 3]
    assert report["detected_baud"] == 1000000
    assert report["suggested_env"]["env"]["BLINK_SERIAL_PORT"] == "/dev/cu.usbserial-demo"
    assert report["report_path"] == str(report_path)
    assert json.loads(report_path.read_text(encoding="utf-8"))["responsive_ids"] == [1, 2, 3]
