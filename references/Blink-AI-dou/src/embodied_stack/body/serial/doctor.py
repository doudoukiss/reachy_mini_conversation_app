from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from embodied_stack.config import Settings
from embodied_stack.shared.contracts.body import HeadProfile, utc_now

from ..profile import load_head_profile
from .health import read_bench_health_many
from .transport import LIVE_SERIAL_MODE, ServoTransportError, build_servo_transport, list_serial_ports

DEFAULT_BRINGUP_REPORT_PATH = Path("runtime/serial/bringup_report.json")
DEFAULT_STAGE_B_CALIBRATION_PATH = "runtime/calibrations/robot_head_live_v1.json"


def profile_servo_ids(profile: HeadProfile) -> list[int]:
    ids: list[int] = []
    for joint in profile.joints:
        if joint.enabled:
            ids.extend(joint.servo_ids)
    return sorted({int(servo_id) for servo_id in ids})


def parse_servo_ids(value: str | None, *, default_ids: list[int]) -> list[int]:
    if not value:
        return list(default_ids)
    parsed: list[int] = []
    for token in value.split(","):
        token = token.strip()
        if not token:
            continue
        if "-" in token:
            start_text, end_text = token.split("-", 1)
            start = int(start_text)
            end = int(end_text)
            parsed.extend(range(start, end + 1))
        else:
            parsed.append(int(token))
    return sorted({int(item) for item in parsed})


def resolve_baud_candidates(profile: HeadProfile, *, explicit_baud: int | None, auto_scan_baud: bool) -> list[int]:
    candidates: list[int] = []
    if explicit_baud is not None:
        candidates.append(int(explicit_baud))
    candidates.append(int(profile.baud_rate))
    if auto_scan_baud:
        candidates.extend(int(item) for item in profile.auto_scan_baud_rates)
    return list(dict.fromkeys(candidates))


def choose_preferred_port(available_ports: list[dict[str, Any]], *, explicit_port: str | None) -> tuple[str | None, str]:
    if explicit_port:
        return explicit_port, "explicit"
    recommended = [item for item in available_ports if item.get("recommended")]
    if len(recommended) == 1:
        return str(recommended[0]["device"]), "single_recommended"
    return None, "requires_explicit_selection"


def build_doctor_settings(
    *,
    profile_path: str,
    calibration_path: str,
    transport_mode: str,
    port: str | None,
    baud: int,
    timeout_seconds: float,
    fixture_path: str | None,
) -> Settings:
    return Settings(
        _env_file=None,
        blink_head_profile=profile_path,
        blink_head_calibration=calibration_path,
        blink_serial_transport=transport_mode,
        blink_serial_port=port,
        blink_servo_baud=baud,
        blink_serial_timeout_seconds=timeout_seconds,
        blink_serial_fixture=fixture_path,
    )


def transport_summary(transport: object | None) -> dict[str, Any]:
    if transport is None:
        return {
            "mode": None,
            "port": None,
            "baud_rate": None,
            "timeout_seconds": None,
            "healthy": False,
            "confirmed_live": False,
            "reason_code": "transport_unconfirmed",
            "last_error": None,
            "last_operation": None,
            "last_good_reply": None,
            "transaction_count": 0,
        }
    status = getattr(transport, "status", None)
    return {
        "mode": getattr(status, "mode", None),
        "port": getattr(status, "port", None),
        "baud_rate": getattr(status, "baud_rate", None),
        "timeout_seconds": getattr(status, "timeout_seconds", None),
        "healthy": getattr(status, "healthy", False),
        "confirmed_live": getattr(status, "confirmed_live", False),
        "reason_code": getattr(status, "reason_code", "transport_unconfirmed"),
        "last_error": getattr(status, "last_error", None),
        "last_operation": getattr(status, "last_operation", None),
        "last_good_reply": getattr(status, "last_good_reply", None),
        "transaction_count": getattr(status, "transaction_count", 0),
    }


def build_suggested_env(
    *,
    profile_path: str,
    calibration_path: str,
    port: str | None,
    baud: int | None,
) -> dict[str, Any]:
    env = {
        "BLINK_RUNTIME_MODE": "desktop_serial_body",
        "BLINK_BODY_DRIVER": "serial",
        "BLINK_SERIAL_TRANSPORT": "live_serial",
        "BLINK_HEAD_PROFILE": profile_path,
        "BLINK_HEAD_CALIBRATION": calibration_path,
    }
    if port is not None:
        env["BLINK_SERIAL_PORT"] = port
    if baud is not None:
        env["BLINK_SERVO_BAUD"] = str(int(baud))
    shell_lines = [f"{key}={value}" for key, value in env.items()]
    missing_keys = []
    if port is None:
        missing_keys.append("BLINK_SERIAL_PORT")
    if baud is None:
        missing_keys.append("BLINK_SERVO_BAUD")
    return {
        "env": env,
        "shell_lines": shell_lines,
        "shell_block": "\n".join(shell_lines),
        "missing_keys": missing_keys,
    }


def _scan_baud_attempt(
    *,
    profile: HeadProfile,
    profile_path: str,
    calibration_path: str,
    transport_mode: str,
    chosen_port: str | None,
    baud: int,
    timeout_seconds: float,
    fixture_path: str | None,
    servo_ids: list[int],
) -> dict[str, Any]:
    settings = build_doctor_settings(
        profile_path=profile_path,
        calibration_path=calibration_path,
        transport_mode=transport_mode,
        port=chosen_port,
        baud=baud,
        timeout_seconds=timeout_seconds,
        fixture_path=fixture_path,
    )
    try:
        transport = build_servo_transport(settings, profile)
    except ServoTransportError as exc:
        return {
            "baud_rate": baud,
            "found_ids": [],
            "missing_ids": {servo_id: f"{exc.classification}:{exc.detail}" for servo_id in servo_ids},
            "transport_status": {
                "mode": transport_mode,
                "port": chosen_port,
                "baud_rate": baud,
                "timeout_seconds": timeout_seconds,
                "healthy": False,
                "confirmed_live": False,
                "reason_code": exc.classification,
                "last_error": f"{exc.classification}:{exc.detail}",
                "last_operation": None,
                "last_good_reply": None,
                "transaction_count": 0,
            },
            "transaction_history": [],
        }

    found_ids: list[int] = []
    missing_ids: dict[int, str] = {}
    try:
        for servo_id in servo_ids:
            try:
                transport.ping(servo_id)
            except ServoTransportError as exc:
                missing_ids[servo_id] = f"{exc.classification}:{exc.detail}"
            else:
                found_ids.append(servo_id)
        return {
            "baud_rate": baud,
            "found_ids": found_ids,
            "missing_ids": missing_ids,
            "transport_status": transport_summary(transport),
            "transaction_history": transport.history_payload(),
        }
    finally:
        transport.close()


def _read_positions(transport: object, servo_ids: list[int]) -> dict[int, dict[str, Any]]:
    results: dict[int, dict[str, Any]] = {}
    for servo_id in servo_ids:
        try:
            results[servo_id] = {"position": transport.read_position(servo_id)}
        except ServoTransportError as exc:
            results[servo_id] = {"error": f"{exc.classification}:{exc.detail}"}
    return results


def _read_health(transport: object, servo_ids: list[int]) -> dict[int, dict[str, Any]]:
    return read_bench_health_many(transport, servo_ids)


def _build_failure_summary(
    *,
    transport_mode: str,
    chosen_port: str | None,
    responsive_ids: list[int],
    requested_ids: list[int],
    position_reads: dict[int, dict[str, Any]],
    health_reads: dict[int, dict[str, Any]],
) -> list[str]:
    failures: list[str] = []
    if transport_mode == LIVE_SERIAL_MODE and chosen_port is None:
        failures.append("port_selection_required")
    if not responsive_ids:
        failures.append("ping_all_failed")
    if responsive_ids and len(responsive_ids) < len(requested_ids):
        failures.append("partial_id_reply")
    if responsive_ids and len(responsive_ids) != len(position_reads):
        failures.append("position_result_mismatch")
    if any("error" in payload for payload in position_reads.values()):
        failures.append("read_position_unstable")
    if any("error" in payload for payload in health_reads.values()):
        failures.append("read_health_unstable")
    return failures


def _build_next_steps(
    *,
    transport_mode: str,
    chosen_port: str | None,
    responsive_ids: list[int],
    requested_ids: list[int],
    failure_summary: list[str],
) -> list[str]:
    if transport_mode == LIVE_SERIAL_MODE and chosen_port is None:
        return ["Select a recommended /dev/cu.* port and rerun the doctor with --port before attempting Stage B."]
    if not responsive_ids:
        return [
            "Verify cable, power, and port ownership first.",
            "Retry with --auto-scan-baud and confirm the bus baud matches the hardware.",
        ]
    if len(responsive_ids) < len(requested_ids):
        return [
            "Do not proceed to motion yet.",
            "Resolve missing IDs and rerun doctor until the full requested set replies consistently.",
        ]
    if failure_summary:
        return [
            "Keep Stage A read-only until read-position and read-health are stable.",
            "Use the bring-up report hex history to debug remaining serial failures before calibration capture.",
        ]
    return [
        "Stage A read-only bring-up is complete.",
        "Proceed to Stage B: capture a non-template live calibration before enabling any motion.",
    ]


def run_serial_doctor(
    *,
    profile_path: str,
    calibration_path: str,
    transport_mode: str,
    port: str | None,
    explicit_baud: int | None,
    timeout_seconds: float,
    fixture_path: str | None,
    ids: str | None,
    auto_scan_baud: bool,
    report_path: str | Path | None = None,
) -> dict[str, Any]:
    profile = load_head_profile(profile_path)
    requested_ids = parse_servo_ids(ids, default_ids=profile_servo_ids(profile))
    available_ports = [item.to_dict() for item in list_serial_ports()]
    chosen_port, port_selection_reason = choose_preferred_port(available_ports, explicit_port=port)
    baud_candidates = resolve_baud_candidates(profile, explicit_baud=explicit_baud, auto_scan_baud=auto_scan_baud)

    baud_results = [
        _scan_baud_attempt(
            profile=profile,
            profile_path=profile_path,
            calibration_path=calibration_path,
            transport_mode=transport_mode,
            chosen_port=chosen_port,
            baud=baud,
            timeout_seconds=timeout_seconds,
            fixture_path=fixture_path,
            servo_ids=requested_ids,
        )
        for baud in baud_candidates
    ]
    best_attempt = max(baud_results, key=lambda item: (len(item["found_ids"]), -baud_candidates.index(item["baud_rate"]))) if baud_results else None
    detected_baud = best_attempt["baud_rate"] if best_attempt and best_attempt["found_ids"] else None
    responsive_ids = list(best_attempt["found_ids"]) if best_attempt else []

    position_reads: dict[int, dict[str, Any]] = {}
    health_reads: dict[int, dict[str, Any]] = {}
    final_transport_status: dict[str, Any] = {
        "mode": transport_mode,
        "port": chosen_port,
        "baud_rate": detected_baud,
        "timeout_seconds": timeout_seconds,
        "healthy": False,
        "confirmed_live": False,
        "reason_code": "transport_unconfirmed",
        "last_error": None,
        "last_operation": None,
        "last_good_reply": None,
        "transaction_count": 0,
    }
    final_history: list[dict[str, Any]] = []
    if detected_baud is not None and responsive_ids:
        settings = build_doctor_settings(
            profile_path=profile_path,
            calibration_path=calibration_path,
            transport_mode=transport_mode,
            port=chosen_port,
            baud=detected_baud,
            timeout_seconds=timeout_seconds,
            fixture_path=fixture_path,
        )
        try:
            transport = build_servo_transport(settings, profile)
        except ServoTransportError as exc:
            final_transport_status.update(
                {
                    "reason_code": exc.classification,
                    "last_error": f"{exc.classification}:{exc.detail}",
                }
            )
        else:
            try:
                position_reads = _read_positions(transport, responsive_ids)
                health_reads = _read_health(transport, responsive_ids)
                final_transport_status = transport_summary(transport)
                final_history = transport.history_payload()
            finally:
                transport.close()

    failure_summary = _build_failure_summary(
        transport_mode=transport_mode,
        chosen_port=chosen_port,
        responsive_ids=responsive_ids,
        requested_ids=requested_ids,
        position_reads=position_reads,
        health_reads=health_reads,
    )
    suggested_env = build_suggested_env(
        profile_path=profile_path,
        calibration_path=DEFAULT_STAGE_B_CALIBRATION_PATH,
        port=chosen_port,
        baud=detected_baud,
    )
    report = {
        "generated_at": utc_now(),
        "profile_name": profile.profile_name,
        "profile_path": profile.source_path or profile_path,
        "transport_mode": transport_mode,
        "available_ports": available_ports,
        "chosen_port": chosen_port,
        "port_selection_reason": port_selection_reason,
        "requested_ids": requested_ids,
        "responsive_ids": responsive_ids,
        "tested_bauds": baud_candidates,
        "detected_baud": detected_baud,
        "baud_results": baud_results,
        "position_reads": position_reads,
        "health_reads": health_reads,
        "transport_status": final_transport_status,
        "request_response_history": final_history,
        "failure_summary": failure_summary,
        "next_steps": _build_next_steps(
            transport_mode=transport_mode,
            chosen_port=chosen_port,
            responsive_ids=responsive_ids,
            requested_ids=requested_ids,
            failure_summary=failure_summary,
        ),
        "suggested_env": suggested_env,
        "ready_for_stage_b": bool(responsive_ids) and not failure_summary,
    }
    output_path = Path(report_path or DEFAULT_BRINGUP_REPORT_PATH)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
    report["report_path"] = str(output_path)
    return report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Read-only Mac serial bring-up doctor for the Blink-AI head.")
    parser.add_argument("--profile", default="src/embodied_stack/body/profiles/robot_head_v1.json")
    parser.add_argument("--calibration", default=DEFAULT_STAGE_B_CALIBRATION_PATH)
    parser.add_argument("--transport", default=LIVE_SERIAL_MODE, choices=["dry_run", "fixture_replay", "live_serial"])
    parser.add_argument("--port", default=None)
    parser.add_argument("--baud", type=int, default=None)
    parser.add_argument("--timeout-seconds", type=float, default=0.2)
    parser.add_argument("--fixture", default=None)
    parser.add_argument("--ids", default=None)
    parser.add_argument("--auto-scan-baud", action="store_true")
    parser.add_argument("--report", default=str(DEFAULT_BRINGUP_REPORT_PATH))
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    report = run_serial_doctor(
        profile_path=args.profile,
        calibration_path=args.calibration,
        transport_mode=args.transport,
        port=args.port,
        explicit_baud=args.baud,
        timeout_seconds=float(args.timeout_seconds),
        fixture_path=args.fixture,
        ids=args.ids,
        auto_scan_baud=bool(args.auto_scan_baud),
        report_path=args.report,
    )
    print(json.dumps(report, indent=2, default=str))
    return 0


__all__ = [
    "DEFAULT_BRINGUP_REPORT_PATH",
    "DEFAULT_STAGE_B_CALIBRATION_PATH",
    "build_doctor_settings",
    "build_parser",
    "build_suggested_env",
    "choose_preferred_port",
    "main",
    "parse_servo_ids",
    "profile_servo_ids",
    "resolve_baud_candidates",
    "run_serial_doctor",
]
