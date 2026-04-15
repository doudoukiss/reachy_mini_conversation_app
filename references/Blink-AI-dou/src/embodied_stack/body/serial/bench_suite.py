from __future__ import annotations

import argparse
import json
import platform
import socket
import sys
from pathlib import Path
from time import perf_counter
from typing import Any, Callable

from embodied_stack.backends.router import BackendRouter
from embodied_stack.body import calibration as calibration_module
from embodied_stack.body.serial.evidence import (
    DEFAULT_BENCH_SUITE_DIR,
    SerialBenchStepRecord,
    SerialBenchSuiteRecord,
    build_motion_report_index,
    build_serial_failure_summary,
    collect_request_response_history,
    load_motion_reports,
    summarize_motion_metrics,
)
from embodied_stack.brain.live_voice import LiveVoiceRuntimeManager
from embodied_stack.brain.operator.service import OperatorConsoleService
from embodied_stack.brain.orchestrator import BrainOrchestrator
from embodied_stack.brain.perception import PerceptionService
from embodied_stack.config import Settings
from embodied_stack.demo.coordinator import DemoCoordinator
from embodied_stack.demo.episodes.service import EpisodeStore, build_exporter
from embodied_stack.demo.shift_reports import ShiftReportStore
from embodied_stack.desktop.devices import build_desktop_device_registry
from embodied_stack.desktop.runtime import build_inprocess_embodiment_gateway
from embodied_stack.persistence import normalize_json_payload, write_json_atomic
from embodied_stack.shared.contracts._common import utc_now


def _base_namespace(args: argparse.Namespace, **overrides: object) -> argparse.Namespace:
    payload = {
        "profile": args.profile,
        "calibration": args.calibration,
        "transport": args.transport,
        "port": args.port,
        "baud": args.baud,
        "timeout_seconds": args.timeout_seconds,
        "fixture": args.fixture,
        "author": args.author,
    }
    payload.update(overrides)
    return argparse.Namespace(**payload)


def _machine_metadata() -> dict[str, object]:
    return {
        "hostname": socket.gethostname(),
        "platform": platform.platform(),
        "python_version": sys.version.split()[0],
        "machine": platform.machine(),
        "processor": platform.processor() or None,
    }


def _write_artifact(path: Path, payload: object) -> str:
    normalized = json.loads(json.dumps(normalize_json_payload(payload), default=str))
    write_json_atomic(path, normalized)
    return str(path)


def _step_success(step_name: str, payload: dict[str, object]) -> tuple[bool, str | None, str | None]:
    if step_name == "doctor":
        responsive_ids = payload.get("responsive_ids") or []
        failure_summary = payload.get("failure_summary") or []
        if not responsive_ids or failure_summary:
            return False, "transport_unconfirmed", ";".join(str(item) for item in failure_summary) or "doctor_no_responsive_ids"
        return True, None, None
    if step_name == "scan":
        baud_results = payload.get("baud_results") or []
        max_found = max((len(item.get("found_ids") or []) for item in baud_results if isinstance(item, dict)), default=0)
        if max_found == 0:
            return False, "transport_unconfirmed", "scan_found_no_responsive_ids"
        return True, None, None
    if step_name == "read_position":
        errors = [str(item.get("error")) for item in (payload.get("positions") or {}).values() if isinstance(item, dict) and item.get("error")]
        if errors:
            return False, "timeout", ";".join(errors)
        return True, None, None
    if step_name == "read_health":
        errors = [str(item.get("error")) for item in (payload.get("health_reads") or {}).values() if isinstance(item, dict) and item.get("error")]
        if errors:
            return False, "health_degraded", ";".join(errors)
        return True, None, None
    if step_name == "calibration_snapshot":
        joint_errors = [str(item.get("error")) for item in payload.get("joint_records") or [] if isinstance(item, dict) and item.get("error")]
        if joint_errors:
            return False, "health_degraded", ";".join(joint_errors)
        return True, None, None
    if step_name == "arm_live_motion":
        arm_status = payload.get("arm_status") or {}
        if not arm_status.get("armed"):
            return False, "motion_not_armed", str(payload.get("detail") or "arm_live_motion_failed")
        return True, None, None
    if step_name in {"write_neutral", "move_joint", "semantic_smoke", "safe_idle"}:
        if payload.get("success") is False or payload.get("failure_reason"):
            return False, str(payload.get("failure_reason") or "health_degraded"), str(payload.get("stop_notes") or payload.get("detail"))
        return True, None, None
    if step_name == "disarm_live_motion":
        return bool(payload.get("cleared") or payload.get("previous_lease") is None), None, None
    return True, None, None


def _load_profile(profile_path: str):
    return calibration_module.load_head_profile(profile_path)


def _collect_console_artifacts(args: argparse.Namespace, *, suite_dir: Path) -> tuple[dict[str, object], dict[str, object]]:
    runtime_root = suite_dir / "console_runtime"
    settings = Settings(
        _env_file=None,
        brain_store_path=str(runtime_root / "brain_store.json"),
        demo_report_dir=str(runtime_root / "demo_runs"),
        demo_check_dir=str(runtime_root / "demo_checks"),
        shift_report_dir=str(runtime_root / "shift_reports"),
        episode_export_dir=str(runtime_root / "episodes"),
        perception_frame_dir=str(runtime_root / "perception_frames"),
        operator_auth_runtime_file=str(runtime_root / "operator_auth.json"),
        blink_appliance_profile_file=str(runtime_root / "appliance_profile.json"),
        brain_dialogue_backend="rule_based",
        brain_voice_backend="stub",
        shift_background_tick_enabled=False,
        blink_runtime_mode="desktop_serial_body",
        blink_body_driver="serial",
        blink_serial_transport=args.transport,
        blink_serial_port=args.port,
        blink_servo_baud=int(args.baud),
        blink_serial_timeout_seconds=float(args.timeout_seconds),
        blink_serial_fixture=args.fixture,
        blink_head_profile=args.profile,
        blink_head_calibration=args.calibration,
    )
    backend_router = BackendRouter(settings=settings)
    edge_gateway = build_inprocess_embodiment_gateway(settings)
    orchestrator = BrainOrchestrator(settings=settings, store_path=settings.brain_store_path, backend_router=backend_router)
    coordinator = DemoCoordinator(
        orchestrator=orchestrator,
        edge_gateway=edge_gateway,
        report_dir=settings.demo_report_dir,
    )
    device_registry = build_desktop_device_registry(settings)
    voice_manager = LiveVoiceRuntimeManager(
        settings=settings,
        device_registry=device_registry,
        macos_voice_name=settings.macos_tts_voice,
        macos_rate=settings.macos_tts_rate,
    )
    perception_service = PerceptionService(
        settings=settings,
        memory=orchestrator.memory,
        event_handler=orchestrator.handle_event,
        providers=backend_router.build_perception_providers(),
    )
    operator_console = OperatorConsoleService(
        settings=settings,
        orchestrator=orchestrator,
        edge_gateway=coordinator.edge_gateway,
        demo_coordinator=coordinator,
        shift_report_store=ShiftReportStore(settings.shift_report_dir),
        voice_manager=voice_manager,
        backend_router=backend_router,
        device_registry=device_registry,
        perception_service=perception_service,
        episode_exporter=build_exporter(
            settings=settings,
            orchestrator=orchestrator,
            report_store=coordinator.report_store,
            episode_store=EpisodeStore(settings.episode_export_dir),
            edge_gateway=coordinator.edge_gateway,
        ),
    )
    snapshot = operator_console.get_snapshot()
    telemetry = coordinator.edge_gateway.get_telemetry()
    return snapshot.model_dump(mode="json"), telemetry.model_dump(mode="json")


def run_serial_bench(args: argparse.Namespace) -> dict[str, object]:
    suite_root = Path(args.report_root)
    suite = SerialBenchSuiteRecord(
        transport_mode=args.transport,
        profile_path=str(Path(args.profile)),
        calibration_path=str(Path(args.calibration)),
        port=args.port,
        baud_rate=int(args.baud),
        timeout_seconds=float(args.timeout_seconds),
        machine=_machine_metadata(),
    )
    suite_dir = suite_root / suite.suite_id
    suite_dir.mkdir(parents=True, exist_ok=True)

    artifact_files: dict[str, str] = {}
    named_histories: list[tuple[str, list[dict[str, object]] | None]] = []
    motion_report_paths: list[str] = []
    stop_step: str | None = None
    armed_live_motion = False
    motion_phase_started = False

    command_order = ["doctor", "scan", "read_position", "read_health", "calibration_snapshot"]
    if args.transport == "live_serial":
        command_order.append("arm_live_motion")
    command_order.extend(["write_neutral", "move_joint", "semantic_smoke", "safe_idle"])
    if args.transport == "live_serial":
        command_order.append("disarm_live_motion")
    suite.command_order = command_order

    def execute_step(
        step_name: str,
        artifact_name: str | None,
        fn: Callable[[], dict[str, object]],
        *,
        motion_step: bool = False,
    ) -> dict[str, object]:
        nonlocal stop_step, armed_live_motion
        started_at = utc_now()
        timer = perf_counter()
        reason_code: str | None = None
        detail: str | None = None
        status = "ok"
        payload: dict[str, object]
        try:
            payload = fn()
            success, reason_code, detail = _step_success(step_name, payload)
            if not success:
                status = "degraded"
                stop_step = stop_step or step_name
        except Exception as exc:  # pragma: no cover - exercised via error-path tests
            detail = str(exc)
            reason_code = getattr(exc, "classification", "error")
            status = "error"
            payload = {
                "operation": step_name,
                "accepted": False,
                "reason_code": reason_code,
                "detail": detail,
                "error": f"{reason_code}:{detail}",
            }
            stop_step = stop_step or step_name
        latency_ms = round((perf_counter() - timer) * 1000.0, 2)
        report_path = None
        if artifact_name is not None:
            report_path = _write_artifact(suite_dir / artifact_name, payload)
            artifact_files[artifact_name] = report_path
        elif payload.get("report_path"):
            report_path = str(payload["report_path"])
        if motion_step and payload.get("report_path"):
            motion_report_paths.append(str(payload["report_path"]))
        if step_name == "arm_live_motion" and status == "ok":
            arm_status = payload.get("arm_status") or {}
            armed_live_motion = bool(arm_status.get("armed"))
        suite.steps.append(
            SerialBenchStepRecord(
                step_name=step_name,
                status=status,
                started_at=started_at,
                completed_at=utc_now(),
                latency_ms=latency_ms,
                success=status == "ok",
                report_path=report_path,
                reason_code=reason_code,
                detail=detail,
            )
        )
        history = payload.get("request_response_history")
        if isinstance(history, list):
            named_histories.append((step_name, history))
        return payload

    profile = _load_profile(args.profile)
    step_payloads: dict[str, dict[str, object]] = {}

    doctor_args = _base_namespace(
        args,
        ids=args.ids,
        auto_scan_baud=args.auto_scan_baud,
        report=str(suite_dir / "doctor_report.json"),
        command="doctor",
    )
    step_payloads["doctor"] = execute_step("doctor", "doctor_report.json", lambda: calibration_module.doctor_command(doctor_args))

    if stop_step is None:
        scan_args = _base_namespace(
            args,
            ids=args.ids,
            auto_scan_baud=args.auto_scan_baud,
            command="scan",
        )
        step_payloads["scan"] = execute_step("scan", "scan_report.json", lambda: calibration_module.scan_bus(scan_args))

    if stop_step is None:
        position_args = _base_namespace(args, ids=args.ids, command="read_position")
        step_payloads["read_position"] = execute_step(
            "read_position",
            "position_report.json",
            lambda: calibration_module.read_positions(position_args),
        )

    if stop_step is None:
        health_args = _base_namespace(args, ids=args.ids, command="read_health")
        step_payloads["read_health"] = execute_step(
            "read_health",
            "health_report.json",
            lambda: calibration_module.read_health_report(health_args),
        )

    if stop_step is None:
        dump_args = _base_namespace(
            args,
            output=str(suite_dir / "calibration_snapshot.json"),
            command="dump_profile_calibration",
        )
        step_payloads["calibration_snapshot"] = execute_step(
            "calibration_snapshot",
            "calibration_snapshot.json",
            lambda: calibration_module.dump_calibration(dump_args),
        )

    if stop_step is None and args.transport == "live_serial":
        arm_args = _base_namespace(
            args,
            ttl_seconds=float(args.live_motion_ttl),
            command="arm_live_motion",
        )
        step_payloads["arm_live_motion"] = execute_step(
            "arm_live_motion",
            None,
            lambda: calibration_module.arm_live_motion(arm_args),
        )

    if stop_step is None:
        neutral_args = _base_namespace(
            args,
            duration_ms=int(args.neutral_duration_ms),
            confirm_live_write=bool(args.confirm_live_write),
            command="write_neutral",
        )
        motion_phase_started = True
        step_payloads["write_neutral"] = execute_step(
            "write_neutral",
            None,
            lambda: calibration_module.write_neutral_pose(neutral_args),
            motion_step=True,
        )

    if stop_step is None:
        move_args = _base_namespace(
            args,
            joint=args.joint,
            delta=int(args.joint_delta),
            target=None,
            duration_ms=int(args.motion_duration_ms),
            command="move_joint",
        )
        motion_phase_started = True
        step_payloads["move_joint"] = execute_step(
            "move_joint",
            None,
            lambda: calibration_module.move_joint_command(move_args),
            motion_step=True,
        )

    if stop_step is None:
        semantic_args = _base_namespace(
            args,
            action=args.semantic_action,
            intensity=float(args.semantic_intensity),
            repeat_count=int(args.semantic_repeat_count),
            note=args.semantic_note,
            allow_bench_actions=bool(args.allow_bench_actions),
            confirm_live_write=bool(args.confirm_live_write),
            command="semantic_smoke",
        )
        motion_phase_started = True
        step_payloads["semantic_smoke"] = execute_step(
            "semantic_smoke",
            None,
            lambda: calibration_module.semantic_smoke_command(semantic_args),
            motion_step=True,
        )

    safe_idle_already_run = False
    if stop_step is not None and motion_phase_started:
        safe_idle_args = _base_namespace(args, command="safe_idle")
        step_payloads["safe_idle"] = execute_step(
            "safe_idle",
            None,
            lambda: calibration_module.safe_idle_command(safe_idle_args),
            motion_step=True,
        )
        safe_idle_already_run = True

    if not safe_idle_already_run and stop_step is None:
        safe_idle_args = _base_namespace(args, command="safe_idle")
        step_payloads["safe_idle"] = execute_step(
            "safe_idle",
            None,
            lambda: calibration_module.safe_idle_command(safe_idle_args),
            motion_step=True,
        )

    if args.transport == "live_serial" and armed_live_motion:
        disarm_args = _base_namespace(args, command="disarm_live_motion")
        step_payloads["disarm_live_motion"] = execute_step(
            "disarm_live_motion",
            None,
            lambda: calibration_module.disarm_live_motion(disarm_args),
        )

    motion_reports = load_motion_reports(motion_report_paths)
    motion_report_index = build_motion_report_index(motion_report_paths)
    artifact_files["motion_reports_index.json"] = _write_artifact(suite_dir / "motion_reports_index.json", motion_report_index)

    request_history = collect_request_response_history(
        named_histories=named_histories,
        motion_reports=motion_reports,
    )
    artifact_files["request_response_history.json"] = _write_artifact(
        suite_dir / "request_response_history.json",
        request_history,
    )

    responsive_ids = step_payloads.get("doctor", {}).get("responsive_ids") or []
    suite.metrics = summarize_motion_metrics(
        motion_reports=motion_reports,
        responsive_ids=responsive_ids,
        profile=profile,
        request_history=request_history,
    )
    suite.failure_summary = build_serial_failure_summary(
        steps=suite.steps,
        motion_reports=motion_reports,
        stop_step=stop_step,
    )
    artifact_files["failure_summary.json"] = _write_artifact(
        suite_dir / "failure_summary.json",
        suite.failure_summary.model_dump(mode="json"),
    )

    try:
        console_snapshot, body_telemetry = _collect_console_artifacts(args, suite_dir=suite_dir)
    except Exception as exc:  # pragma: no cover - best effort on machine-specific paths
        console_snapshot = {"error": str(exc)}
        body_telemetry = {"error": str(exc)}
    artifact_files["console_snapshot.json"] = _write_artifact(suite_dir / "console_snapshot.json", console_snapshot)
    artifact_files["body_telemetry.json"] = _write_artifact(suite_dir / "body_telemetry.json", body_telemetry)

    suite.completed_at = utc_now()
    suite_path = suite_dir / "suite.json"
    suite.artifact_files = {**artifact_files, "suite.json": str(suite_path)}
    _write_artifact(suite_path, suite.model_dump(mode="json"))
    return suite.model_dump(mode="json")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the maintained Stage E serial bench suite.")
    parser.add_argument("--profile", default="src/embodied_stack/body/profiles/robot_head_v1.json")
    parser.add_argument("--calibration", default=str(calibration_module.DEFAULT_STAGE_B_CALIBRATION_PATH))
    parser.add_argument("--transport", default="dry_run", choices=["dry_run", "fixture_replay", "live_serial"])
    parser.add_argument("--port", default=None)
    parser.add_argument("--baud", type=int, default=1000000)
    parser.add_argument("--timeout-seconds", type=float, default=0.2)
    parser.add_argument("--fixture", default=None)
    parser.add_argument("--author", default=None)
    parser.add_argument("--ids", default="1-11")
    parser.add_argument("--report-root", default=str(DEFAULT_BENCH_SUITE_DIR))
    parser.add_argument("--joint", default="head_yaw")
    parser.add_argument("--joint-delta", type=int, default=40)
    parser.add_argument("--neutral-duration-ms", type=int, default=800)
    parser.add_argument("--motion-duration-ms", type=int, default=600)
    parser.add_argument("--semantic-action", default="look_left")
    parser.add_argument("--semantic-intensity", type=float, default=1.0)
    parser.add_argument("--semantic-repeat-count", type=int, default=1)
    parser.add_argument("--semantic-note", default=None)
    parser.add_argument("--live-motion-ttl", type=float, default=60.0)
    parser.add_argument("--confirm-live-write", action="store_true")
    parser.add_argument("--allow-bench-actions", action="store_true")
    parser.set_defaults(auto_scan_baud=True)
    parser.add_argument("--no-auto-scan-baud", dest="auto_scan_baud", action="store_false")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    result = run_serial_bench(args)
    print(json.dumps(result, indent=2))
    return 0 if result.get("failure_summary", {}).get("status") == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
