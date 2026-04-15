from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from embodied_stack.config import Settings
from embodied_stack.shared.contracts.body import (
    AnimationRequest,
    BodyCommandOutcomeRecord,
    BodyDriverMode,
    BodyState,
    ExpressionRequest,
    GazeRequest,
    GestureRequest,
    HeadCalibrationRecord,
    HeadProfile,
    JointCalibrationRecord,
    utc_now,
)

from .compiler import SemanticBodyCompiler
from .library import expression_pose
from .live_range_revalidation import (
    DEFAULT_REVALIDATION_REPORT_DIR,
    apply_revalidation_overrides,
    available_revalidation_families,
    build_live_limits_table_rows,
    recenter_neck_pair_neutral,
    resolve_revalidation_sequence,
    run_family_revalidation,
    write_revalidation_artifacts,
)
from .profile import load_head_profile
from .range_demo import available_range_demo_presets, available_range_demo_sequences, build_range_demo_plan
from .semantics import build_semantic_smoke_request
from .serial import (
    LIVE_SERIAL_MODE,
    FeetechBodyBridge,
    ServoTransportError,
    build_servo_transport,
    list_serial_ports,
    read_bench_health_many,
)
from .serial.bench import (
    DEFAULT_ARM_LEASE_PATH,
    DEFAULT_MOTION_REPORT_DIR,
    RANGE_CONFLICT_NOTE_PREFIX,
    SAFE_SYNC_GROUPS,
    clear_arm_lease,
    confirm_live_transport,
    conflicting_range_joints,
    coupling_validation_ready,
    execute_bench_command,
    execute_servo_lab_sweep,
    neutral_targets,
    profile_servo_ids,
    read_arm_lease,
    read_bench_snapshot,
    resolve_joint_targets,
    resolve_sync_group_targets,
    snapshot_has_errors,
    validate_motion_arm,
    write_arm_lease,
)
from .servo_lab import (
    ServoLabError,
    build_servo_lab_catalog,
    motion_control_payload,
    readback_payload,
    resolve_servo_lab_move,
    resolve_servo_lab_sweep,
    save_servo_lab_calibration,
    servo_lab_capabilities,
)
from .serial.doctor import (
    DEFAULT_BRINGUP_REPORT_PATH,
    DEFAULT_STAGE_B_CALIBRATION_PATH,
    build_suggested_env,
    choose_preferred_port,
    parse_servo_ids,
    resolve_baud_candidates,
    run_serial_doctor,
)
from .tuning import (
    DEFAULT_SEMANTIC_TUNING_PATH,
    DEFAULT_TEACHER_REVIEW_PATH,
    load_semantic_tuning,
    record_teacher_review,
    semantic_library_payload,
    tuning_override_names,
)

DEFAULT_HEAD_CALIBRATION_PATH = Path(__file__).resolve().parent / "profiles" / "robot_head_v1.calibration_template.json"
READ_SAFE_OPERATIONS = {
    "scan",
    "ping",
    "read_position",
    "read_health",
    "dump_profile_calibration",
    "validate_coupling",
    "health",
    "ports",
    "doctor",
    "suggest_env",
    "bench_health",
    "disarm_live_motion",
    "list_semantic_actions",
}
LIVE_GATED_OPERATIONS = {
    "write_neutral",
    "capture_neutral",
    "move_joint",
    "sync_move",
    "torque_on",
    "semantic_smoke",
    "range_demo",
    "servo_lab_move",
    "servo_lab_sweep",
    "revalidate_live_ranges",
}


def build_settings_from_args(args: argparse.Namespace) -> Settings:
    payload: dict[str, Any] = {
        "_env_file": None,
        "blink_head_profile": args.profile,
        "blink_head_calibration": args.calibration,
        "blink_serial_transport": args.transport,
        "blink_serial_timeout_seconds": args.timeout_seconds,
        "blink_serial_fixture": args.fixture,
    }
    if getattr(args, "port", None) is not None:
        payload["blink_serial_port"] = args.port
    if getattr(args, "baud", None) is not None:
        payload["blink_servo_baud"] = int(args.baud)
    return Settings(**payload)


def unique_servo_ids(profile: HeadProfile) -> list[int]:
    ids: list[int] = []
    for joint in profile.joints:
        ids.extend(joint.servo_ids)
    return sorted(set(ids))


def resolve_cli_baud(args: argparse.Namespace, profile: HeadProfile) -> int:
    return int(args.baud) if getattr(args, "baud", None) is not None else int(profile.baud_rate)


def transport_summary(transport) -> dict:
    return {
        "mode": transport.status.mode,
        "port": transport.status.port,
        "baud_rate": transport.status.baud_rate,
        "timeout_seconds": transport.status.timeout_seconds,
        "healthy": transport.status.healthy,
        "confirmed_live": transport.status.confirmed_live,
        "reason_code": transport.status.reason_code,
        "last_error": transport.status.last_error,
        "last_operation": transport.status.last_operation,
        "last_good_reply": transport.status.last_good_reply,
        "transaction_count": transport.status.transaction_count,
    }


def calibration_provenance_source(*, transport_mode: str | None, confirmed_live: bool | None) -> str:
    if transport_mode == LIVE_SERIAL_MODE and confirmed_live:
        return "live_hardware"
    if transport_mode == "fixture_replay":
        return "fixture_replay"
    if transport_mode == "dry_run":
        return "dry_run"
    return "template"


def stamp_calibration_provenance(
    record: HeadCalibrationRecord,
    *,
    profile: HeadProfile,
    transport: object | None,
    author: str | None = None,
    provenance_source: str | None = None,
) -> HeadCalibrationRecord:
    transport_status = getattr(transport, "status", None)
    if author:
        record.author = author
    record.profile_name = profile.profile_name
    record.profile_version = profile.profile_version
    record.profile_path = record.profile_path or profile.source_path
    record.transport_boundary_version = profile.transport_boundary_version
    record.transport_mode = getattr(transport_status, "mode", record.transport_mode)
    record.transport_port = getattr(transport_status, "port", record.transport_port)
    record.baud_rate = getattr(transport_status, "baud_rate", record.baud_rate)
    record.timeout_seconds = getattr(transport_status, "timeout_seconds", record.timeout_seconds)
    record.transport_confirmed_live = getattr(transport_status, "confirmed_live", record.transport_confirmed_live)
    record.provenance_source = provenance_source or calibration_provenance_source(
        transport_mode=getattr(transport_status, "mode", record.transport_mode),
        confirmed_live=getattr(transport_status, "confirmed_live", record.transport_confirmed_live),
    )
    return record


def require_live_write_confirmation(
    args: argparse.Namespace,
    *,
    operation: str,
    transport,
    calibration: HeadCalibrationRecord,
    bridge: FeetechBodyBridge | None = None,
    allow_template_bootstrap: bool = False,
) -> None:
    if transport.status.mode != LIVE_SERIAL_MODE:
        return
    if operation not in LIVE_GATED_OPERATIONS:
        return
    if not getattr(args, "confirm_live_write", False):
        raise ServoTransportError(
            "transport_unconfirmed",
            f"{operation}_requires_confirm_live_write_flag",
        )
    if not transport.status.confirmed_live or not transport.status.healthy:
        raise ServoTransportError(
            "transport_unconfirmed",
            f"{operation}_requires_confirmed_transport",
        )
    if bridge is not None and not bridge.live_motion_enabled and not allow_template_bootstrap:
        raise ServoTransportError(
            "transport_unconfirmed",
            f"{operation}_requires_confirmed_transport_and_saved_calibration",
        )
    if calibration.calibration_kind == "template" and not allow_template_bootstrap:
        raise ServoTransportError(
            "calibration_template",
            f"{operation}_requires_saved_non_template_calibration",
        )


def calibration_from_profile(
    profile: HeadProfile,
    *,
    calibration_kind: str = "template",
    transport: object | None = None,
    author: str | None = None,
    notes: list[str] | None = None,
) -> HeadCalibrationRecord:
    record = HeadCalibrationRecord(
        profile_name=profile.profile_name,
        profile_version=profile.profile_version,
        profile_path=profile.source_path,
        transport_boundary_version=profile.transport_boundary_version,
        calibration_kind=calibration_kind,
        author=author,
        transport_mode=getattr(getattr(transport, "status", None), "mode", None),
        transport_port=getattr(getattr(transport, "status", None), "port", None),
        baud_rate=getattr(getattr(transport, "status", None), "baud_rate", profile.baud_rate),
        timeout_seconds=getattr(getattr(transport, "status", None), "timeout_seconds", None),
        transport_confirmed_live=getattr(getattr(transport, "status", None), "confirmed_live", None),
        provenance_source=calibration_provenance_source(
            transport_mode=getattr(getattr(transport, "status", None), "mode", None),
            confirmed_live=getattr(getattr(transport, "status", None), "confirmed_live", None),
        ),
        safe_speed=profile.safe_speed,
        safe_acceleration=profile.safe_acceleration,
        joint_records=[
            JointCalibrationRecord(
                joint_name=joint.joint_name,
                servo_ids=list(joint.servo_ids),
                neutral=joint.neutral,
                raw_min=joint.raw_min,
                raw_max=joint.raw_max,
                notes=list(joint.notes),
            )
            for joint in profile.joints
            if joint.enabled
        ],
        notes=list(notes or []),
    )
    return stamp_calibration_provenance(record, profile=profile, transport=transport, author=author)


def _upgrade_v1_calibration(payload: dict, *, profile: HeadProfile) -> HeadCalibrationRecord:
    transport = payload.get("transport_status") or {}
    joint_records = [
        JointCalibrationRecord(
            joint_name=item["joint_name"],
            servo_ids=[int(item.get("servo_id"))] if item.get("servo_id") is not None else [],
            neutral=int(item["neutral"]),
            raw_min=int(item["raw_min"]),
            raw_max=int(item["raw_max"]),
            current_position=item.get("current_position"),
            mirrored_direction_confirmed=None,
            error=item.get("error"),
        )
        for item in payload.get("joint_records", [])
    ]
    recorded_at = utc_now()
    return HeadCalibrationRecord(
        profile_name=str(payload.get("profile_name") or profile.profile_name),
        profile_version=profile.profile_version,
        profile_path=str(payload.get("profile_path") or profile.source_path),
        transport_boundary_version=profile.transport_boundary_version,
        calibration_kind="template" if "template" in " ".join(payload.get("notes", [])).lower() else "saved",
        transport_mode=transport.get("mode"),
        transport_port=transport.get("port"),
        baud_rate=transport.get("baud_rate"),
        timeout_seconds=transport.get("timeout_seconds"),
        transport_confirmed_live=transport.get("confirmed_live"),
        provenance_source=payload.get("provenance_source")
        or calibration_provenance_source(
            transport_mode=transport.get("mode"),
            confirmed_live=transport.get("confirmed_live"),
        ),
        safe_speed=profile.safe_speed,
        safe_acceleration=profile.safe_acceleration,
        joint_records=joint_records,
        notes=list(payload.get("notes", [])),
        recorded_at=recorded_at,
        updated_at=recorded_at,
    )


def load_head_calibration(path: str | Path | None, *, profile: HeadProfile | None = None) -> HeadCalibrationRecord:
    resolved_profile = profile or load_head_profile(None)
    calibration_path = Path(path) if path else DEFAULT_HEAD_CALIBRATION_PATH
    if not calibration_path.exists():
        record = calibration_from_profile(
            resolved_profile,
            calibration_kind="template",
            notes=[f"calibration_path_missing:{calibration_path}"],
        )
        return record
    payload = json.loads(calibration_path.read_text(encoding="utf-8"))
    schema_version = str(payload.get("schema_version") or "")
    if schema_version == "blink_head_calibration/v2":
        record = HeadCalibrationRecord.model_validate(payload)
    else:
        record = _upgrade_v1_calibration(payload, profile=resolved_profile)
    record.profile_name = resolved_profile.profile_name
    record.profile_version = resolved_profile.profile_version
    record.profile_path = record.profile_path or resolved_profile.source_path
    record.transport_boundary_version = record.transport_boundary_version or resolved_profile.transport_boundary_version
    if record.provenance_source is None:
        record.provenance_source = calibration_provenance_source(
            transport_mode=record.transport_mode,
            confirmed_live=record.transport_confirmed_live,
        )
    return record


def save_head_calibration(record: HeadCalibrationRecord, path: str | Path) -> Path:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(record.model_dump(mode="json"), indent=2) + "\n", encoding="utf-8")
    return output_path


def _calibration_output_path(args: argparse.Namespace) -> Path | None:
    output = getattr(args, "output", None)
    if output:
        return Path(output)
    if getattr(args, "in_place", False):
        return Path(args.calibration)
    return None


def _motion_report_dir() -> Path:
    return Path(DEFAULT_MOTION_REPORT_DIR)


def _live_revalidation_dir(args: argparse.Namespace) -> Path:
    output_dir = getattr(args, "output_dir", None)
    if output_dir:
        return Path(output_dir)
    timestamp = utc_now().strftime("%Y%m%dT%H%M%S%fZ")
    return Path(DEFAULT_REVALIDATION_REPORT_DIR) / f"{timestamp}_live_joint_revalidation"


def _arm_lease_path() -> Path:
    return Path(DEFAULT_ARM_LEASE_PATH)


def _semantic_tuning_path() -> Path:
    return Path(DEFAULT_SEMANTIC_TUNING_PATH)


def _teacher_review_path() -> Path:
    return Path(DEFAULT_TEACHER_REVIEW_PATH)


def _default_live_calibration_path() -> Path:
    return Path(DEFAULT_STAGE_B_CALIBRATION_PATH)


def _capture_output_path(args: argparse.Namespace) -> Path | None:
    output_path = _calibration_output_path(args)
    if output_path is not None:
        return output_path
    if getattr(args, "transport", None) == LIVE_SERIAL_MODE:
        return _default_live_calibration_path()
    return None


def _range_conflict_note(current: int, raw_min: int, raw_max: int) -> str:
    return f"{RANGE_CONFLICT_NOTE_PREFIX}:{current}:{raw_min}-{raw_max}"


def _bench_context(args: argparse.Namespace) -> tuple[Settings, HeadProfile, HeadCalibrationRecord, Any, FeetechBodyBridge]:
    settings = build_settings_from_args(args)
    profile = load_head_profile(settings.blink_head_profile)
    settings = settings.model_copy(update={"blink_servo_baud": resolve_cli_baud(args, profile)}, deep=True)
    calibration = load_head_calibration(settings.blink_head_calibration, profile=profile)
    transport = build_servo_transport(settings, profile)
    if transport.status.mode == LIVE_SERIAL_MODE:
        confirm_live_transport(transport, profile)
    bridge = FeetechBodyBridge(transport=transport, profile=profile, calibration=calibration)
    return settings, profile, calibration, transport, bridge


def _saved_calibration_required(calibration: HeadCalibrationRecord, *, operation: str) -> None:
    if calibration.calibration_kind == "template":
        raise ServoTransportError("calibration_template", f"{operation}_requires_saved_non_template_calibration")


def _require_coupling_validation(calibration: HeadCalibrationRecord, *, operation: str) -> None:
    if not coupling_validation_ready(calibration):
        raise ServoTransportError("coupling_unvalidated", f"{operation}_requires_validate_coupling")


def _require_clear_ranges(calibration: HeadCalibrationRecord, *, operation: str, joint_names: set[str] | None = None) -> None:
    conflicts = conflicting_range_joints(calibration)
    if joint_names is not None:
        conflicts &= set(joint_names)
    if conflicts:
        joined = ",".join(sorted(conflicts))
        raise ServoTransportError("range_conflict_from_capture", f"{operation}_range_conflict:{joined}")


def _arm_status_payload(
    *,
    port: str | None,
    baud_rate: int,
    calibration_path: str | Path,
) -> dict[str, Any]:
    lease = read_arm_lease(_arm_lease_path())
    if lease is None:
        return {"armed": False, "lease": None}
    try:
        validate_motion_arm(
            port=port,
            baud_rate=baud_rate,
            calibration_path=calibration_path,
            path=_arm_lease_path(),
        )
    except ServoTransportError as exc:
        return {
            "armed": False,
            "lease": lease,
            "reason_code": exc.classification,
            "detail": exc.detail,
        }
    return {"armed": True, "lease": lease}


def _semantic_smoke_state(
    *,
    compiler: SemanticBodyCompiler,
    command_type: str,
    payload: dict[str, object],
) -> BodyState:
    state = BodyState(driver_mode=BodyDriverMode.SERIAL)
    if command_type == "set_gaze":
        return compiler.apply_gaze(state, request=GazeRequest.model_validate(payload))
    if command_type == "set_expression":
        return compiler.apply_expression(state, ExpressionRequest.model_validate(payload))
    if command_type == "perform_gesture":
        return compiler.apply_gesture(state, GestureRequest.model_validate(payload))
    if command_type == "perform_animation":
        return compiler.apply_animation(state, AnimationRequest.model_validate(payload))
    raise ServoTransportError("out_of_range", f"unsupported_semantic_command_type:{command_type}")


def _parse_tuning_delta(raw: str | None) -> dict[str, object]:
    if not raw:
        return {}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ServoTransportError("out_of_range", f"invalid_tuning_delta_json:{exc.msg}") from exc
    if not isinstance(payload, dict):
        raise ServoTransportError("out_of_range", "tuning_delta_must_be_json_object")
    return payload


def _servo_lab_joint_lookup(profile: HeadProfile, joint_name: str):
    for joint in profile.joints:
        if joint.enabled and joint.joint_name == joint_name:
            return joint
    raise ServoTransportError("out_of_range", f"unknown_joint:{joint_name}")


def _servo_lab_read_positions(
    *,
    profile: HeadProfile,
    transport,
    joint_name: str | None = None,
) -> tuple[dict[str, int], dict[str, str]]:
    current_positions: dict[str, int] = {}
    readback_errors: dict[str, str] = {}
    joints = [joint for joint in profile.joints if joint.enabled]
    if joint_name is not None:
        joints = [joint for joint in joints if joint.joint_name == joint_name]
        if not joints:
            raise ServoTransportError("out_of_range", f"unknown_joint:{joint_name}")
    for joint in joints:
        servo_id = int(joint.servo_ids[0]) if joint.servo_ids else None
        if servo_id is None:
            readback_errors[joint.joint_name] = "servo_id_missing"
            continue
        try:
            current_positions[joint.joint_name] = int(transport.read_position(servo_id))
        except ServoTransportError as exc:
            readback_errors[joint.joint_name] = f"{exc.classification}:{exc.detail}"
    return current_positions, readback_errors


def _servo_lab_read_current_position(*, profile: HeadProfile, transport, joint_name: str) -> int | None:
    current_positions, readback_errors = _servo_lab_read_positions(profile=profile, transport=transport, joint_name=joint_name)
    if joint_name in readback_errors:
        raise ServoTransportError("transport_unconfirmed", f"servo_lab_readback_failed:{joint_name}:{readback_errors[joint_name]}")
    return current_positions.get(joint_name)


def _servo_lab_health_reads(*, profile: HeadProfile, transport, joint_name: str | None = None) -> dict[str, object]:
    joints = [joint for joint in profile.joints if joint.enabled]
    if joint_name is not None:
        joints = [joint for joint in joints if joint.joint_name == joint_name]
        if not joints:
            raise ServoTransportError("out_of_range", f"unknown_joint:{joint_name}")
    payload: dict[str, object] = {}
    for joint in joints:
        servo_ids = [int(servo_id) for servo_id in joint.servo_ids]
        payload[joint.joint_name] = {
            "servo_ids": servo_ids,
            "health": read_bench_health_many(transport, servo_ids),
        }
    return payload


def scan_bus(args: argparse.Namespace) -> dict:
    settings = build_settings_from_args(args)
    profile = load_head_profile(settings.blink_head_profile)
    settings = settings.model_copy(update={"blink_servo_baud": resolve_cli_baud(args, profile)}, deep=True)
    servo_ids = parse_servo_ids(args.ids, default_ids=unique_servo_ids(profile))
    candidate_bauds = resolve_baud_candidates(
        profile,
        explicit_baud=getattr(args, "baud", None),
        auto_scan_baud=bool(args.auto_scan_baud),
    )

    baud_results: list[dict] = []
    for baud in candidate_bauds:
        probe_settings = settings.model_copy(update={"blink_servo_baud": baud}, deep=True)
        transport = build_servo_transport(probe_settings, profile)
        found: list[int] = []
        missing: dict[int, str] = {}
        history: list[dict[str, object]] = []
        try:
            for servo_id in servo_ids:
                try:
                    transport.ping(servo_id)
                except ServoTransportError as exc:
                    missing[servo_id] = f"{exc.classification}:{exc.detail}"
                else:
                    found.append(servo_id)
            history = transport.history_payload()
        finally:
            transport.close()
        baud_results.append({"baud_rate": baud, "found_ids": found, "missing_ids": missing, "request_response_history": history})
    return {
        "operation": "scan",
        "operation_group": "read_safe",
        "profile_name": profile.profile_name,
        "transport": settings.blink_serial_transport,
        "servo_ids": servo_ids,
        "baud_results": baud_results,
    }


def ping_ids(args: argparse.Namespace) -> dict:
    settings = build_settings_from_args(args)
    profile = load_head_profile(settings.blink_head_profile)
    settings = settings.model_copy(update={"blink_servo_baud": resolve_cli_baud(args, profile)}, deep=True)
    servo_ids = parse_servo_ids(args.ids, default_ids=unique_servo_ids(profile))
    transport = build_servo_transport(settings, profile)
    results: dict[int, dict] = {}
    try:
        for servo_id in servo_ids:
            try:
                reply = transport.ping(servo_id)
            except ServoTransportError as exc:
                results[servo_id] = {"ok": False, "error": f"{exc.classification}:{exc.detail}"}
            else:
                results[servo_id] = {"ok": True, "error": reply.error}
        return {
            "operation": "ping",
            "operation_group": "read_safe",
            "profile_name": profile.profile_name,
            "results": results,
            "transport_status": transport_summary(transport),
            "request_response_history": transport.history_payload(),
        }
    finally:
        transport.close()


def read_positions(args: argparse.Namespace) -> dict:
    settings = build_settings_from_args(args)
    profile = load_head_profile(settings.blink_head_profile)
    settings = settings.model_copy(update={"blink_servo_baud": resolve_cli_baud(args, profile)}, deep=True)
    servo_ids = parse_servo_ids(args.ids, default_ids=unique_servo_ids(profile))
    transport = build_servo_transport(settings, profile)
    positions: dict[int, dict] = {}
    try:
        for servo_id in servo_ids:
            try:
                positions[servo_id] = {"position": transport.read_position(servo_id)}
            except ServoTransportError as exc:
                positions[servo_id] = {"error": f"{exc.classification}:{exc.detail}"}
        return {
            "operation": "read_position",
            "operation_group": "read_safe",
            "profile_name": profile.profile_name,
            "positions": positions,
            "transport_status": transport_summary(transport),
            "request_response_history": transport.history_payload(),
        }
    finally:
        transport.close()


def list_ports_command(args: argparse.Namespace) -> dict:
    available_ports = [item.to_dict() for item in list_serial_ports()]
    chosen_port, selection_reason = choose_preferred_port(available_ports, explicit_port=getattr(args, "port", None))
    return {
        "operation": "ports",
        "available_ports": available_ports,
        "chosen_port": chosen_port,
        "selection_reason": selection_reason,
    }


def doctor_command(args: argparse.Namespace) -> dict:
    return run_serial_doctor(
        profile_path=args.profile,
        calibration_path=args.calibration,
        transport_mode=args.transport,
        port=args.port,
        explicit_baud=args.baud,
        timeout_seconds=float(args.timeout_seconds),
        fixture_path=args.fixture,
        ids=args.ids,
        auto_scan_baud=bool(args.auto_scan_baud),
        report_path=getattr(args, "report", None) or DEFAULT_BRINGUP_REPORT_PATH,
    )


def read_health_report(args: argparse.Namespace) -> dict:
    settings = build_settings_from_args(args)
    profile = load_head_profile(settings.blink_head_profile)
    settings = settings.model_copy(update={"blink_servo_baud": resolve_cli_baud(args, profile)}, deep=True)
    servo_ids = parse_servo_ids(args.ids, default_ids=unique_servo_ids(profile))
    transport = build_servo_transport(settings, profile)
    try:
        health = read_bench_health_many(transport, servo_ids)
        return {
            "operation": "read_health",
            "operation_group": "read_safe",
            "profile_name": profile.profile_name,
            "servo_ids": servo_ids,
            "health_reads": health,
            "transport_status": transport_summary(transport),
            "request_response_history": transport.history_payload(),
        }
    finally:
        transport.close()


def suggest_env_command(args: argparse.Namespace) -> dict:
    settings = build_settings_from_args(args)
    profile = load_head_profile(settings.blink_head_profile)
    available_ports = [item.to_dict() for item in list_serial_ports()]
    chosen_port, selection_reason = choose_preferred_port(available_ports, explicit_port=settings.blink_serial_port)
    env = build_suggested_env(
        profile_path=profile.source_path or settings.blink_head_profile,
        calibration_path=DEFAULT_STAGE_B_CALIBRATION_PATH,
        port=chosen_port,
        baud=resolve_cli_baud(args, profile),
    )
    return {
        "operation": "suggest_env",
        "profile_name": profile.profile_name,
        "available_ports": available_ports,
        "chosen_port": chosen_port,
        "selection_reason": selection_reason,
        "suggested_env": env,
    }


def motion_config_command(args: argparse.Namespace) -> dict:
    settings, profile, calibration, transport, bridge = _bench_context(args)
    try:
        if transport.status.mode == LIVE_SERIAL_MODE and getattr(args, "apply_live_acceleration", False):
            require_live_write_confirmation(
                args,
                operation="range_demo",
                transport=transport,
                calibration=calibration,
                bridge=bridge,
            )
            validate_motion_arm(
                port=transport.status.port,
                baud_rate=transport.status.baud_rate,
                calibration_path=settings.blink_head_calibration,
                path=_arm_lease_path(),
            )
        motion_control = bridge.inspect_motion_control_settings(
            speed_override=getattr(args, "speed_override", None),
            acceleration_override=getattr(args, "acceleration_override", None),
            apply_acceleration=bool(getattr(args, "apply_live_acceleration", False)),
        )
        return {
            "operation": "motion_config",
            "operation_group": "live_write" if transport.status.mode == LIVE_SERIAL_MODE and getattr(args, "apply_live_acceleration", False) else "read_safe",
            "profile_name": profile.profile_name,
            "calibration_status": bridge.calibration_status,
            "live_motion_enabled": bridge.live_motion_enabled,
            "transport_status": transport_summary(transport),
            "motion_control": motion_control.model_dump(mode="json"),
            "arm_status": _arm_status_payload(
                port=transport.status.port,
                baud_rate=transport.status.baud_rate,
                calibration_path=settings.blink_head_calibration,
            ),
        }
    finally:
        transport.close()


def usable_range_command(args: argparse.Namespace) -> dict:
    settings = build_settings_from_args(args)
    profile = load_head_profile(settings.blink_head_profile)
    calibration = load_head_calibration(settings.blink_head_calibration, profile=profile)
    compiler = SemanticBodyCompiler(profile=profile, calibration=calibration)
    plan = build_range_demo_plan(
        profile=profile,
        calibration=calibration,
        preset_name=getattr(args, "preset", None),
        sequence_name=getattr(args, "sequence", None),
        neutral_pose=compiler.neutral_pose(),
        calibration_source_path=settings.blink_head_calibration,
    )
    return {
        "operation": "usable_range",
        "operation_group": "read_safe",
        "profile_name": profile.profile_name,
        "range_demo_preset": plan.preset_name,
        "range_demo_sequence": plan.sequence_name,
        "usable_range_audit": plan.usable_range_audit.model_dump(mode="json") if plan.usable_range_audit is not None else None,
        "range_demo_plan": plan.to_payload(),
    }


def revalidate_live_ranges_command(args: argparse.Namespace) -> dict:
    settings, profile, calibration, transport, bridge = _bench_context(args)
    output_dir = _live_revalidation_dir(args)
    try:
        require_live_write_confirmation(
            args,
            operation="revalidate_live_ranges",
            transport=transport,
            calibration=calibration,
            bridge=bridge,
        )
        if transport.status.mode != LIVE_SERIAL_MODE:
            raise ServoTransportError("transport_unconfirmed", "revalidate_live_ranges_requires_live_serial")
        if not getattr(args, "confirm_mechanical_clearance", False):
            raise ServoTransportError(
                "operator_confirmation_required",
                "revalidate_live_ranges_requires_confirm_mechanical_clearance",
            )
        if not getattr(args, "confirm_widen_beyond_profile", False):
            raise ServoTransportError(
                "operator_confirmation_required",
                "revalidate_live_ranges_requires_confirm_widen_beyond_profile",
            )
        _saved_calibration_required(calibration, operation="revalidate_live_ranges")
        validate_motion_arm(
            port=transport.status.port,
            baud_rate=transport.status.baud_rate,
            calibration_path=settings.blink_head_calibration,
            path=_arm_lease_path(),
        )
        _require_coupling_validation(calibration, operation="revalidate_live_ranges")

        output_dir.mkdir(parents=True, exist_ok=True)
        backup_path = output_dir / "calibration_backup.json"
        save_head_calibration(calibration, backup_path)

        start_snapshot = read_bench_snapshot(transport, profile_servo_ids(profile))
        if snapshot_has_errors(start_snapshot):
            raise ServoTransportError("health_degraded", "revalidate_live_ranges_requires_stable_starting_snapshot")

        family_sequence = resolve_revalidation_sequence(
            family=getattr(args, "family", None),
            resume_from=getattr(args, "resume_from", None),
        )
        session_payload: dict[str, object] = {
            "operation": "revalidate_live_ranges",
            "operation_group": "live_write",
            "profile_name": profile.profile_name,
            "calibration_path": settings.blink_head_calibration,
            "backup_path": str(backup_path),
            "transport_status": transport_summary(transport),
            "family_sequence": family_sequence,
            "starting_snapshot": start_snapshot,
            "neck_recenter": None,
            "family_results": [],
            "final_calibration_path": settings.blink_head_calibration,
        }

        working_calibration, neck_payload = recenter_neck_pair_neutral(
            profile=profile,
            calibration=calibration,
            calibration_source_path=settings.blink_head_calibration,
            transport=transport,
            bridge=bridge,
            report_dir=output_dir / "motion_reports",
        )
        stamp_calibration_provenance(
            working_calibration,
            profile=profile,
            transport=transport,
            author=getattr(args, "author", None) or "range_revalidation",
        )
        save_head_calibration(working_calibration, settings.blink_head_calibration)
        session_payload["neck_recenter"] = neck_payload

        accumulated_side_overrides: dict[str, dict[str, int]] = {}
        for family_name in family_sequence:
            family_result = run_family_revalidation(
                profile=profile,
                calibration=working_calibration,
                transport=transport,
                bridge=bridge,
                family_name=family_name,
                report_dir=output_dir / "motion_reports",
                allow_widen_beyond_profile=True,
            )
            session_payload["family_results"].append(family_result)
            if family_name != "neck_tilt":
                for joint_name, overrides in family_result["side_overrides"].items():
                    target = accumulated_side_overrides.setdefault(joint_name, {})
                    for side_name, value in overrides.items():
                        if side_name == "low":
                            target[side_name] = min(int(target.get(side_name, value)), int(value))
                        else:
                            target[side_name] = max(int(target.get(side_name, value)), int(value))
            working_calibration = apply_revalidation_overrides(
                calibration=working_calibration,
                side_overrides=accumulated_side_overrides,
            )
            stamp_calibration_provenance(
                working_calibration,
                profile=profile,
                transport=transport,
                author=getattr(args, "author", None) or "range_revalidation",
            )
            save_head_calibration(working_calibration, settings.blink_head_calibration)

        usable_range = build_range_demo_plan(
            profile=profile,
            calibration=working_calibration,
            sequence_name="servo_range_showcase_v1",
            neutral_pose=SemanticBodyCompiler(profile=profile, calibration=working_calibration).neutral_pose(),
            calibration_source_path=settings.blink_head_calibration,
        )
        final_snapshot = read_bench_snapshot(transport, profile_servo_ids(profile))
        session_payload["final_snapshot"] = final_snapshot
        session_payload["final_usable_range_audit"] = (
            usable_range.usable_range_audit.model_dump(mode="json")
            if usable_range.usable_range_audit is not None
            else None
        )
        joint_rows, family_rows = build_live_limits_table_rows(
            profile=profile,
            calibration=working_calibration,
        )
        session_payload["markdown_table_data"] = {
            "joint_rows": joint_rows,
            "family_rows": family_rows,
        }
        session_payload["completed_at"] = utc_now()

        save_head_calibration(working_calibration, settings.blink_head_calibration)
        session_payload["doc_preview_path"] = str(output_dir / "robot_head_live_limits.preview.md")
        session_payload["artifact_paths"] = {
            "session_summary": str(output_dir / "session_summary.json"),
            "doc_preview": str(output_dir / "robot_head_live_limits.preview.md"),
        }
        artifact_paths = write_revalidation_artifacts(
            output_dir=output_dir,
            session_payload=session_payload,
            profile=profile,
            calibration=working_calibration,
        )
        preview_path = Path(artifact_paths["doc_preview"])

        return {
            "operation": "revalidate_live_ranges",
            "operation_group": "live_write",
            "profile_name": profile.profile_name,
            "calibration_path": settings.blink_head_calibration,
            "backup_path": str(backup_path),
            "output_dir": str(output_dir),
            "doc_preview_path": str(preview_path),
            "artifact_paths": artifact_paths,
            "family_sequence": family_sequence,
            "neck_recenter": neck_payload,
            "family_results": session_payload["family_results"],
            "final_usable_range_audit": session_payload["final_usable_range_audit"],
            "transport_status": transport_summary(transport),
        }
    except KeyboardInterrupt:
        execute_bench_command(
            transport=transport,
            bridge=bridge,
            profile=profile,
            calibration=calibration,
            command_family="safe_idle",
            requested_targets=None,
            resolved_targets=None,
            duration_ms=max(int(profile.neutral_recovery_ms or 220), int(profile.minimum_transition_ms or 80)),
            report_dir=output_dir / "motion_reports",
            author="range_revalidation:operator_abort",
        )
        raise ServoTransportError("operator_abort", "revalidate_live_ranges_aborted_by_operator")
    finally:
        transport.close()


def list_semantic_actions_command(args: argparse.Namespace) -> dict:
    settings = build_settings_from_args(args)
    profile = load_head_profile(settings.blink_head_profile)
    tuning = load_semantic_tuning(
        profile_name=profile.profile_name,
        calibration_path=settings.blink_head_calibration,
        path=_semantic_tuning_path(),
    )
    actions = [
        item.model_dump(mode="json")
        for item in semantic_library_payload(tuning, smoke_safe_only=bool(getattr(args, "smoke_safe_only", False)))
    ]
    return {
        "operation": "list_semantic_actions",
        "operation_group": "read_safe",
        "profile_name": profile.profile_name,
        "tuning_path": str(_semantic_tuning_path()),
        "teacher_review_path": str(_teacher_review_path()),
        "semantic_actions": actions,
    }


def semantic_smoke_command(args: argparse.Namespace) -> dict:
    settings, profile, calibration, transport, bridge = _bench_context(args)
    try:
        tuning = load_semantic_tuning(
            profile_name=profile.profile_name,
            calibration_path=settings.blink_head_calibration,
            path=_semantic_tuning_path(),
        )
        try:
            descriptor, command_type, payload = build_semantic_smoke_request(
                args.action,
                intensity=float(args.intensity),
                repeat_count=int(args.repeat_count),
                note=getattr(args, "note", None),
                tuning_overrides=tuning_override_names(tuning),
                allow_bench_actions=bool(getattr(args, "allow_bench_actions", False)),
            )
        except ValueError as exc:
            raise ServoTransportError("out_of_range", str(exc)) from exc

        if command_type == "safe_idle":
            report = execute_bench_command(
                transport=transport,
                bridge=bridge,
                profile=profile,
                calibration=calibration,
                command_family="safe_idle",
                requested_targets=neutral_targets(calibration, profile),
                resolved_targets=neutral_targets(calibration, profile),
                duration_ms=max(int(profile.neutral_recovery_ms or 220), int(profile.minimum_transition_ms or 80)),
                report_dir=_motion_report_dir(),
                author=getattr(args, "author", None),
            )
        else:
            require_live_write_confirmation(
                args,
                operation="semantic_smoke",
                transport=transport,
                calibration=calibration,
                bridge=bridge,
            )
            if transport.status.mode == LIVE_SERIAL_MODE:
                _saved_calibration_required(calibration, operation="semantic_smoke")
                validate_motion_arm(
                    port=transport.status.port,
                    baud_rate=transport.status.baud_rate,
                    calibration_path=settings.blink_head_calibration,
                    path=_arm_lease_path(),
                )
                _require_coupling_validation(calibration, operation="semantic_smoke")
            compiler = SemanticBodyCompiler(
                profile=profile,
                calibration=calibration,
                tuning=tuning,
                tuning_path=str(_semantic_tuning_path()),
            )
            semantic_state = _semantic_smoke_state(
                compiler=compiler,
                command_type=command_type,
                payload=payload,
            )
            compiled = semantic_state.compiled_animation
            if compiled is None or not compiled.frames:
                raise ServoTransportError("out_of_range", "semantic_smoke_requires_compiled_frames")
            final_targets = dict(compiled.frames[-1].servo_targets)
            if transport.status.mode == LIVE_SERIAL_MODE:
                _require_clear_ranges(calibration, operation="semantic_smoke", joint_names=set(final_targets))
            report = execute_bench_command(
                transport=transport,
                bridge=bridge,
                profile=profile,
                calibration=calibration,
                command_family="semantic_smoke",
                requested_targets=final_targets,
                resolved_targets=final_targets,
                duration_ms=int(compiled.total_duration_ms or compiled.frames[-1].duration_ms),
                compiled_animation=compiled,
                semantic_action_name=descriptor.canonical_name,
                semantic_family=descriptor.family,
                tuning_path=str(_semantic_tuning_path()),
                report_dir=_motion_report_dir(),
                author=getattr(args, "author", None),
            )
        report.update(
            {
                "operation": "semantic_smoke",
                "operation_group": "live_write" if transport.status.mode == LIVE_SERIAL_MODE else "read_safe",
                "profile_name": profile.profile_name,
                "action": descriptor.model_dump(mode="json"),
                "calibration_status": bridge.calibration_status,
                "live_motion_enabled": bridge.live_motion_enabled,
                "tuning_path": str(_semantic_tuning_path()),
                "teacher_review_path": str(_teacher_review_path()),
                "arm_status": _arm_status_payload(
                    port=transport.status.port,
                    baud_rate=transport.status.baud_rate,
                    calibration_path=settings.blink_head_calibration,
                ),
            }
        )
        return report
    finally:
        transport.close()


def range_demo_command(args: argparse.Namespace) -> dict:
    settings, profile, calibration, transport, bridge = _bench_context(args)
    try:
        compiler = SemanticBodyCompiler(profile=profile, calibration=calibration)
        friendly = compiler.compile_frame(
            expression_pose("friendly", intensity=0.58, neutral_pose=compiler.neutral_pose()),
            frame_name="friendly_settle",
            animation_name=f"body_range_demo:{getattr(args, 'sequence', None) or args.preset}",
            duration_ms=620,
            hold_ms=320,
        )
        friendly.compiler_notes.extend(
            [
                f"range_demo_sequence:{getattr(args, 'sequence', None) or args.preset}",
                f"range_demo_preset:{args.preset}",
                "range_demo_friendly_settle",
            ]
        )
        plan = build_range_demo_plan(
            profile=profile,
            calibration=calibration,
            preset_name=args.preset,
            sequence_name=getattr(args, "sequence", None),
            neutral_pose=compiler.neutral_pose(),
            friendly_frame=friendly,
            calibration_source_path=settings.blink_head_calibration,
        )
        if transport.status.mode == LIVE_SERIAL_MODE:
            _saved_calibration_required(calibration, operation="range_demo")
            validate_motion_arm(
                port=transport.status.port,
                baud_rate=transport.status.baud_rate,
                calibration_path=settings.blink_head_calibration,
                path=_arm_lease_path(),
            )
            _require_clear_ranges(calibration, operation="range_demo", joint_names=set(plan.joint_plans))
            _require_coupling_validation(calibration, operation="range_demo")
        require_live_write_confirmation(
            args,
            operation="range_demo",
            transport=transport,
            calibration=calibration,
            bridge=bridge,
        )
        report = execute_bench_command(
            transport=transport,
            bridge=bridge,
            profile=profile,
            calibration=calibration,
            command_family="range_demo",
            requested_targets=dict(plan.animation.frames[-1].servo_targets),
            resolved_targets=dict(plan.animation.frames[-1].servo_targets),
            duration_ms=int(plan.animation.total_duration_ms),
            compiled_animation=plan.animation,
            range_demo_plan=plan.to_payload(),
            semantic_action_name=plan.sequence_name,
            semantic_family="range_demo",
            report_dir=_motion_report_dir(),
            author=getattr(args, "author", None),
        )
        report.update(
            {
                "operation": "range_demo",
                "operation_group": "live_write" if transport.status.mode == LIVE_SERIAL_MODE else "read_safe",
                "profile_name": profile.profile_name,
                "sequence_name": plan.sequence_name,
                "preset_name": plan.preset_name,
                "calibration_status": bridge.calibration_status,
                "live_motion_enabled": bridge.live_motion_enabled,
                "arm_status": _arm_status_payload(
                    port=transport.status.port,
                    baud_rate=transport.status.baud_rate,
                    calibration_path=settings.blink_head_calibration,
                ),
            }
        )
        return report
    finally:
        transport.close()


def teacher_review_command(args: argparse.Namespace) -> dict:
    settings = build_settings_from_args(args)
    profile = load_head_profile(settings.blink_head_profile)
    proposed_tuning_delta = _parse_tuning_delta(getattr(args, "proposed_tuning_delta", None))
    try:
        result = record_teacher_review(
            action=args.action,
            review=args.review,
            note=getattr(args, "note", None),
            proposed_tuning_delta=proposed_tuning_delta,
            apply_tuning=bool(getattr(args, "apply_tuning", False)),
            latest_command_audit=None,
            tuning_path=_semantic_tuning_path(),
            reviews_path=_teacher_review_path(),
            profile_name=profile.profile_name,
            calibration_path=settings.blink_head_calibration,
        )
    except ValueError as exc:
        raise ServoTransportError("out_of_range", str(exc)) from exc
    return {
        "operation": "teacher_review",
        "operation_group": "persistent_state_write",
        "profile_name": profile.profile_name,
        "tuning_path": str(_semantic_tuning_path()),
        "teacher_review_path": str(_teacher_review_path()),
        "review": result["review"].model_dump(mode="json"),
        "descriptor": result["descriptor"].model_dump(mode="json"),
        "tuning": result["tuning"].model_dump(mode="json"),
    }


def arm_live_motion(args: argparse.Namespace) -> dict:
    settings, profile, calibration, transport, bridge = _bench_context(args)
    try:
        _saved_calibration_required(calibration, operation="arm_live_motion")
        if snapshot_has_errors(read_bench_snapshot(transport, profile_servo_ids(profile))):
            raise ServoTransportError("transport_unconfirmed", "arm_live_motion_requires_stable_readback")
        lease = write_arm_lease(
            port=transport.status.port,
            baud_rate=transport.status.baud_rate,
            calibration_path=settings.blink_head_calibration,
            ttl_seconds=float(args.ttl_seconds),
            path=_arm_lease_path(),
            author=getattr(args, "author", None) or "body.calibration.arm_live_motion",
        )
        return {
            "operation": "arm_live_motion",
            "operation_group": "persistent_state_write",
            "profile_name": profile.profile_name,
            "calibration_status": bridge.calibration_status,
            "live_motion_enabled": bridge.live_motion_enabled,
            "transport_status": transport_summary(transport),
            "arm_status": {"armed": True, "lease": lease},
        }
    finally:
        transport.close()


def disarm_live_motion(args: argparse.Namespace) -> dict:
    return {
        "operation": "disarm_live_motion",
        "operation_group": "persistent_state_write",
        **clear_arm_lease(_arm_lease_path()),
    }


def bench_health_command(args: argparse.Namespace) -> dict:
    settings, profile, calibration, transport, bridge = _bench_context(args)
    try:
        snapshot = read_bench_snapshot(transport, profile_servo_ids(profile))
        return {
            "operation": "bench_health",
            "operation_group": "read_safe",
            "profile_name": profile.profile_name,
            "calibration_status": bridge.calibration_status,
            "live_motion_enabled": bridge.live_motion_enabled,
            "arm_status": _arm_status_payload(
                port=transport.status.port,
                baud_rate=transport.status.baud_rate,
                calibration_path=settings.blink_head_calibration,
            ),
            "transport_status": transport_summary(transport),
            "position_reads": snapshot["positions"],
            "health_reads": snapshot["health"],
            "request_response_history": transport.history_payload(),
        }
    finally:
        transport.close()


def power_preflight_command(args: argparse.Namespace) -> dict:
    settings, profile, calibration, transport, bridge = _bench_context(args)
    try:
        outcome, health = bridge.run_live_power_preflight()
        return {
            "operation": "power_preflight",
            "operation_group": "read_safe",
            "profile_name": profile.profile_name,
            "calibration_status": bridge.calibration_status,
            "live_motion_enabled": bridge.live_motion_enabled,
            "transport_status": transport_summary(transport),
            "arm_status": _arm_status_payload(
                port=transport.status.port,
                baud_rate=transport.status.baud_rate,
                calibration_path=settings.blink_head_calibration,
            ),
            "preflight_passed": outcome.preflight_passed,
            "power_health_classification": outcome.power_health_classification,
            "preflight_failure_reason": outcome.preflight_failure_reason,
            "idle_voltage_snapshot": dict(outcome.idle_voltage_snapshot),
            "servo_health": {
                joint_name: record.model_dump(mode="json")
                for joint_name, record in health.items()
            },
            "outcome": outcome.model_dump(mode="json"),
            "request_response_history": transport.history_payload(),
        }
    finally:
        transport.close()


def write_neutral_pose(args: argparse.Namespace) -> dict:
    settings, profile, calibration, transport, bridge = _bench_context(args)
    try:
        resolved_targets = neutral_targets(calibration, profile)
        if transport.status.mode == LIVE_SERIAL_MODE:
            _saved_calibration_required(calibration, operation="write_neutral")
            validate_motion_arm(
                port=transport.status.port,
                baud_rate=transport.status.baud_rate,
                calibration_path=settings.blink_head_calibration,
                path=_arm_lease_path(),
            )
            _require_clear_ranges(calibration, operation="write_neutral", joint_names=set(resolved_targets))
            _require_coupling_validation(calibration, operation="write_neutral")
        report = execute_bench_command(
            transport=transport,
            bridge=bridge,
            profile=profile,
            calibration=calibration,
            command_family="write_neutral",
            requested_targets=dict(resolved_targets),
            resolved_targets=resolved_targets,
            duration_ms=max(400, int(args.duration_ms)),
            report_dir=_motion_report_dir(),
            author=getattr(args, "author", None),
        )
        report.update(
            {
                "operation": "write_neutral",
                "operation_group": "live_write" if transport.status.mode == LIVE_SERIAL_MODE else "read_safe",
                "profile_name": profile.profile_name,
                "calibration_status": bridge.calibration_status,
                "live_motion_enabled": bridge.live_motion_enabled,
                "arm_status": _arm_status_payload(
                    port=transport.status.port,
                    baud_rate=transport.status.baud_rate,
                    calibration_path=settings.blink_head_calibration,
                ),
            }
        )
        return report
    finally:
        transport.close()


def servo_lab_catalog_command(args: argparse.Namespace) -> dict:
    settings, profile, calibration, transport, _bridge = _bench_context(args)
    try:
        current_positions, readback_errors = _servo_lab_read_positions(profile=profile, transport=transport)
        catalog = build_servo_lab_catalog(
            profile=profile,
            calibration=calibration,
            current_positions=current_positions,
            readback_errors=readback_errors,
            transport=transport,
            calibration_path=settings.blink_head_calibration,
        )
        return {
            "operation": "servo_lab_catalog",
            "operation_group": "read_safe",
            "profile_name": profile.profile_name,
            "transport_status": transport_summary(transport),
            "payload": catalog.to_payload(),
        }
    finally:
        transport.close()


def servo_lab_readback_command(args: argparse.Namespace) -> dict:
    settings, profile, calibration, transport, _bridge = _bench_context(args)
    try:
        joint_name = getattr(args, "joint", None)
        current_positions, readback_errors = _servo_lab_read_positions(
            profile=profile,
            transport=transport,
            joint_name=joint_name,
        )
        catalog = build_servo_lab_catalog(
            profile=profile,
            calibration=calibration,
            current_positions=current_positions,
            readback_errors=readback_errors,
            transport=transport,
            calibration_path=settings.blink_head_calibration,
        )
        payload = readback_payload(
            catalog=catalog,
            selected_joint_name=joint_name,
            include_health=bool(getattr(args, "include_health", True)),
            health_reads=(
                _servo_lab_health_reads(profile=profile, transport=transport, joint_name=joint_name)
                if bool(getattr(args, "include_health", True))
                else {}
            ),
        )
        return {
            "operation": "servo_lab_readback",
            "operation_group": "read_safe",
            "profile_name": profile.profile_name,
            "transport_status": transport_summary(transport),
            "payload": payload,
        }
    finally:
        transport.close()


def servo_lab_move_command(args: argparse.Namespace) -> dict:
    settings, profile, calibration, transport, bridge = _bench_context(args)
    try:
        joint_name = str(args.joint)
        current_position = _servo_lab_read_current_position(profile=profile, transport=transport, joint_name=joint_name)
        try:
            move_plan = resolve_servo_lab_move(
                profile=profile,
                calibration=calibration,
                joint_name=joint_name,
                reference_mode=str(args.reference_mode),
                target_raw=getattr(args, "target_raw", None),
                delta_counts=getattr(args, "delta_counts", None),
                current_position=current_position,
                lab_min=getattr(args, "lab_min", None),
                lab_max=getattr(args, "lab_max", None),
            )
        except ServoLabError as exc:
            raise ServoTransportError(exc.code, exc.detail) from exc
        require_live_write_confirmation(
            args,
            operation="servo_lab_move",
            transport=transport,
            calibration=calibration,
            bridge=bridge,
        )
        if transport.status.mode == LIVE_SERIAL_MODE:
            _saved_calibration_required(calibration, operation="servo_lab_move")
            validate_motion_arm(
                port=transport.status.port,
                baud_rate=transport.status.baud_rate,
                calibration_path=settings.blink_head_calibration,
                path=_arm_lease_path(),
            )
            _require_clear_ranges(calibration, operation="servo_lab_move", joint_names={joint_name})
            _require_coupling_validation(calibration, operation="servo_lab_move")
        report = execute_bench_command(
            transport=transport,
            bridge=bridge,
            profile=profile,
            calibration=calibration,
            command_family="servo_lab_move",
            requested_targets={joint_name: move_plan.requested_target},
            resolved_targets={joint_name: move_plan.effective_target},
            duration_ms=max(int(args.duration_ms), int(profile.minimum_transition_ms or 80)),
            speed_override=getattr(args, "speed_override", None),
            acceleration_override=getattr(args, "acceleration_override", None),
            report_dir=_motion_report_dir(),
            author=getattr(args, "note", None) or getattr(args, "author", None),
        )
        capabilities = servo_lab_capabilities(transport)
        outcome = BodyCommandOutcomeRecord.model_validate(report.get("outcome") or {})
        report.update(
            {
                "operation": "servo_lab_move",
                "operation_group": "live_write" if transport.status.mode == LIVE_SERIAL_MODE else "read_safe",
                "profile_name": profile.profile_name,
                "servo_lab_move": move_plan.to_payload(),
                "capabilities": capabilities.to_payload(),
                "motion_control_summary": motion_control_payload(
                    outcome.motion_control,
                    acceleration_supported=capabilities.acceleration_supported,
                    acceleration_status=capabilities.acceleration_status,
                ),
                "arm_status": _arm_status_payload(
                    port=transport.status.port,
                    baud_rate=transport.status.baud_rate,
                    calibration_path=settings.blink_head_calibration,
                ),
            }
        )
        return report
    finally:
        transport.close()


def servo_lab_sweep_command(args: argparse.Namespace) -> dict:
    settings, profile, calibration, transport, bridge = _bench_context(args)
    try:
        joint_name = str(args.joint)
        current_position = _servo_lab_read_current_position(profile=profile, transport=transport, joint_name=joint_name)
        try:
            sweep_plan = resolve_servo_lab_sweep(
                profile=profile,
                calibration=calibration,
                joint_name=joint_name,
                current_position=current_position,
                lab_min=getattr(args, "lab_min", None),
                lab_max=getattr(args, "lab_max", None),
                cycles=int(args.cycles),
                duration_ms=int(args.duration_ms),
                dwell_ms=int(args.dwell_ms),
                return_to_neutral=bool(args.return_to_neutral),
            )
        except ServoLabError as exc:
            raise ServoTransportError(exc.code, exc.detail) from exc
        require_live_write_confirmation(
            args,
            operation="servo_lab_sweep",
            transport=transport,
            calibration=calibration,
            bridge=bridge,
        )
        if transport.status.mode == LIVE_SERIAL_MODE:
            _saved_calibration_required(calibration, operation="servo_lab_sweep")
            validate_motion_arm(
                port=transport.status.port,
                baud_rate=transport.status.baud_rate,
                calibration_path=settings.blink_head_calibration,
                path=_arm_lease_path(),
            )
            _require_clear_ranges(calibration, operation="servo_lab_sweep", joint_names={joint_name})
            _require_coupling_validation(calibration, operation="servo_lab_sweep")
        report = execute_servo_lab_sweep(
            transport=transport,
            bridge=bridge,
            profile=profile,
            calibration=calibration,
            joint_name=joint_name,
            requested_targets={joint_name: current_position if current_position is not None else sweep_plan.bounds.neutral},
            sweep_plan=sweep_plan.to_payload(),
            speed_override=getattr(args, "speed_override", None),
            acceleration_override=getattr(args, "acceleration_override", None),
            report_dir=_motion_report_dir(),
            author=getattr(args, "note", None) or getattr(args, "author", None),
        )
        capabilities = servo_lab_capabilities(transport)
        outcome = BodyCommandOutcomeRecord.model_validate(report.get("outcome") or {})
        report.update(
            {
                "operation": "servo_lab_sweep",
                "operation_group": "live_write" if transport.status.mode == LIVE_SERIAL_MODE else "read_safe",
                "profile_name": profile.profile_name,
                "servo_lab_sweep": sweep_plan.to_payload(),
                "capabilities": capabilities.to_payload(),
                "motion_control_summary": motion_control_payload(
                    outcome.motion_control,
                    acceleration_supported=capabilities.acceleration_supported,
                    acceleration_status=capabilities.acceleration_status,
                ),
                "arm_status": _arm_status_payload(
                    port=transport.status.port,
                    baud_rate=transport.status.baud_rate,
                    calibration_path=settings.blink_head_calibration,
                ),
            }
        )
        return report
    finally:
        transport.close()


def servo_lab_save_calibration_command(args: argparse.Namespace) -> dict:
    settings = build_settings_from_args(args)
    profile = load_head_profile(settings.blink_head_profile)
    calibration = load_head_calibration(settings.blink_head_calibration, profile=profile)
    transport = None
    current_position: int | None = None
    try:
        if calibration.calibration_kind == "template":
            raise ServoTransportError("calibration_template", "servo_lab_save_calibration_requires_saved_non_template_calibration")
        if bool(getattr(args, "save_current_as_neutral", False)):
            settings = settings.model_copy(update={"blink_servo_baud": resolve_cli_baud(args, profile)}, deep=True)
            transport = build_servo_transport(settings, profile)
            if transport.status.mode == LIVE_SERIAL_MODE:
                confirm_live_transport(transport, profile)
            current_position = _servo_lab_read_current_position(profile=profile, transport=transport, joint_name=str(args.joint))
        output_path = _calibration_output_path(args) or Path(settings.blink_head_calibration)
        try:
            updated, update = save_servo_lab_calibration(
                profile=profile,
                calibration=calibration,
                joint_name=str(args.joint),
                output_path=output_path,
                current_position=current_position,
                save_current_as_neutral=bool(getattr(args, "save_current_as_neutral", False)),
                raw_min=getattr(args, "raw_min", None),
                raw_max=getattr(args, "raw_max", None),
                confirm_mirrored=(
                    True if getattr(args, "confirm_mirrored", None) == "true" else False if getattr(args, "confirm_mirrored", None) == "false" else None
                ),
            )
        except ServoLabError as exc:
            raise ServoTransportError(exc.code, exc.detail) from exc
        save_head_calibration(updated, output_path)
        return {
            "operation": "servo_lab_save_calibration",
            "operation_group": "persistent_config_write",
            "profile_name": profile.profile_name,
            "payload": {
                "calibration_update": update.to_payload(),
                "output_path": str(output_path),
            },
            "transport_status": transport_summary(transport) if transport is not None else None,
        }
    finally:
        if transport is not None:
            transport.close()


def dump_calibration(args: argparse.Namespace) -> dict:
    settings = build_settings_from_args(args)
    profile = load_head_profile(settings.blink_head_profile)
    settings = settings.model_copy(update={"blink_servo_baud": resolve_cli_baud(args, profile)}, deep=True)
    transport = build_servo_transport(settings, profile)
    try:
        record = calibration_from_profile(
            profile,
            calibration_kind="captured" if transport.status.mode == LIVE_SERIAL_MODE else "template",
            transport=transport,
            author=getattr(args, "author", None),
            notes=[
                "Pre-power dumps may come from dry-run or fixture replay transports.",
                "Bench-confirmed calibration should replace template values only after powered verification.",
            ],
        )
        for joint_record in record.joint_records:
            servo_id = joint_record.servo_ids[0] if joint_record.servo_ids else None
            if servo_id is None:
                continue
            try:
                joint_record.current_position = transport.read_position(servo_id)
            except ServoTransportError as exc:
                joint_record.error = f"{exc.classification}:{exc.detail}"
        output_path = _calibration_output_path(args)
        if output_path is not None:
            save_head_calibration(record, output_path)
        payload = record.model_dump(mode="json")
        payload["operation"] = "dump_profile_calibration"
        payload["operation_group"] = "read_safe"
        if output_path is not None:
            payload["output_path"] = str(output_path)
        return payload
    finally:
        transport.close()


def capture_neutral(args: argparse.Namespace) -> dict:
    settings, profile, calibration, transport, _bridge = _bench_context(args)
    try:
        if transport.status.mode == LIVE_SERIAL_MODE and not getattr(args, "confirm_visual_neutral", False):
            raise ServoTransportError(
                "transport_unconfirmed",
                "capture_neutral_requires_confirm_visual_neutral_flag",
            )
        require_live_write_confirmation(
            args,
            operation="capture_neutral",
            transport=transport,
            calibration=calibration,
            allow_template_bootstrap=True,
        )
        calibration.calibration_kind = (
            "captured"
            if transport.status.mode == LIVE_SERIAL_MODE
            else ("saved" if calibration.calibration_kind == "template" else calibration.calibration_kind)
        )
        calibration.updated_at = utc_now()
        stamp_calibration_provenance(
            calibration,
            profile=profile,
            transport=transport,
            author=getattr(args, "author", None),
        )
        calibration.notes.append("neutral_capture_completed")
        conflict_joints: list[str] = []
        for joint_record in calibration.joint_records:
            servo_id = joint_record.servo_ids[0] if joint_record.servo_ids else None
            if servo_id is None:
                continue
            joint_record.notes = [
                note for note in joint_record.notes if not str(note).startswith(RANGE_CONFLICT_NOTE_PREFIX)
            ]
            try:
                current = transport.read_position(servo_id)
            except ServoTransportError as exc:
                joint_record.error = f"{exc.classification}:{exc.detail}"
            else:
                joint_record.current_position = current
                joint_record.neutral = current
                joint_record.error = None
                previous_min = int(joint_record.raw_min)
                previous_max = int(joint_record.raw_max)
                if current < previous_min:
                    joint_record.raw_min = current
                    joint_record.notes.append(_range_conflict_note(current, previous_min, previous_max))
                    joint_record.error = "range_conflict_from_capture"
                    conflict_joints.append(joint_record.joint_name)
                elif current > previous_max:
                    joint_record.raw_max = current
                    joint_record.notes.append(_range_conflict_note(current, previous_min, previous_max))
                    joint_record.error = "range_conflict_from_capture"
                    conflict_joints.append(joint_record.joint_name)
        if conflict_joints:
            calibration.coupling_validation["range_conflicts"] = "range_conflict_from_capture"
        else:
            calibration.coupling_validation.pop("range_conflicts", None)
        output_path = _capture_output_path(args)
        if output_path is not None:
            save_head_calibration(calibration, output_path)
        payload = calibration.model_dump(mode="json")
        payload["operation"] = "capture_neutral"
        payload["operation_group"] = "live_write" if transport.status.mode == LIVE_SERIAL_MODE else "read_safe"
        payload["range_conflict_joints"] = sorted(set(conflict_joints))
        if output_path is not None:
            payload["output_path"] = str(output_path)
        return payload
    finally:
        transport.close()


def move_joint_command(args: argparse.Namespace) -> dict:
    settings, profile, calibration, transport, bridge = _bench_context(args)
    try:
        requested_targets, resolved_targets, clamp_notes = resolve_joint_targets(
            calibration=calibration,
            joint_name=args.joint,
            delta=args.delta,
            target=args.target,
        )
        if transport.status.mode == LIVE_SERIAL_MODE:
            _saved_calibration_required(calibration, operation="move_joint")
            validate_motion_arm(
                port=transport.status.port,
                baud_rate=transport.status.baud_rate,
                calibration_path=settings.blink_head_calibration,
                path=_arm_lease_path(),
            )
            _require_clear_ranges(calibration, operation="move_joint", joint_names=set(resolved_targets))
            _require_coupling_validation(calibration, operation="move_joint")
        report = execute_bench_command(
            transport=transport,
            bridge=bridge,
            profile=profile,
            calibration=calibration,
            command_family="move_joint",
            requested_targets=requested_targets,
            resolved_targets=resolved_targets,
            duration_ms=max(int(args.duration_ms), int(profile.minimum_transition_ms or 80)),
            report_dir=_motion_report_dir(),
            author=getattr(args, "author", None),
        )
        report.update(
            {
                "operation": "move_joint",
                "operation_group": "live_write" if transport.status.mode == LIVE_SERIAL_MODE else "read_safe",
                "profile_name": profile.profile_name,
                "requested_joint": args.joint,
                "calibration_status": bridge.calibration_status,
                "live_motion_enabled": bridge.live_motion_enabled,
                "clamp_notes": clamp_notes,
                "arm_status": _arm_status_payload(
                    port=transport.status.port,
                    baud_rate=transport.status.baud_rate,
                    calibration_path=settings.blink_head_calibration,
                ),
            }
        )
        return report
    finally:
        transport.close()


def sync_move_command(args: argparse.Namespace) -> dict:
    settings, profile, calibration, transport, bridge = _bench_context(args)
    try:
        requested_targets, resolved_targets, clamp_notes = resolve_sync_group_targets(
            calibration=calibration,
            group_name=args.group,
        )
        if transport.status.mode == LIVE_SERIAL_MODE:
            _saved_calibration_required(calibration, operation="sync_move")
            validate_motion_arm(
                port=transport.status.port,
                baud_rate=transport.status.baud_rate,
                calibration_path=settings.blink_head_calibration,
                path=_arm_lease_path(),
            )
            _require_clear_ranges(calibration, operation="sync_move", joint_names=set(resolved_targets))
            _require_coupling_validation(calibration, operation="sync_move")
        report = execute_bench_command(
            transport=transport,
            bridge=bridge,
            profile=profile,
            calibration=calibration,
            command_family="sync_move",
            requested_targets=requested_targets,
            resolved_targets=resolved_targets,
            duration_ms=max(int(args.duration_ms), int(profile.minimum_transition_ms or 80)),
            report_dir=_motion_report_dir(),
            author=getattr(args, "author", None),
        )
        report.update(
            {
                "operation": "sync_move",
                "operation_group": "live_write" if transport.status.mode == LIVE_SERIAL_MODE else "read_safe",
                "profile_name": profile.profile_name,
                "sync_group": args.group,
                "calibration_status": bridge.calibration_status,
                "live_motion_enabled": bridge.live_motion_enabled,
                "clamp_notes": clamp_notes,
                "safe_groups": sorted(SAFE_SYNC_GROUPS),
                "arm_status": _arm_status_payload(
                    port=transport.status.port,
                    baud_rate=transport.status.baud_rate,
                    calibration_path=settings.blink_head_calibration,
                ),
            }
        )
        return report
    finally:
        transport.close()


def torque_on_command(args: argparse.Namespace) -> dict:
    settings, profile, calibration, transport, bridge = _bench_context(args)
    try:
        if transport.status.mode == LIVE_SERIAL_MODE:
            _saved_calibration_required(calibration, operation="torque_on")
            validate_motion_arm(
                port=transport.status.port,
                baud_rate=transport.status.baud_rate,
                calibration_path=settings.blink_head_calibration,
                path=_arm_lease_path(),
            )
        report = execute_bench_command(
            transport=transport,
            bridge=bridge,
            profile=profile,
            calibration=calibration,
            command_family="torque_on",
            requested_targets=None,
            resolved_targets=None,
            duration_ms=None,
            report_dir=_motion_report_dir(),
            author=getattr(args, "author", None),
        )
        report.update(
            {
                "operation": "torque_on",
                "operation_group": "live_write" if transport.status.mode == LIVE_SERIAL_MODE else "read_safe",
                "profile_name": profile.profile_name,
                "calibration_status": bridge.calibration_status,
                "live_motion_enabled": bridge.live_motion_enabled,
                "arm_status": _arm_status_payload(
                    port=transport.status.port,
                    baud_rate=transport.status.baud_rate,
                    calibration_path=settings.blink_head_calibration,
                ),
            }
        )
        return report
    finally:
        transport.close()


def torque_off_command(args: argparse.Namespace) -> dict:
    settings, profile, calibration, transport, bridge = _bench_context(args)
    try:
        report = execute_bench_command(
            transport=transport,
            bridge=bridge,
            profile=profile,
            calibration=calibration,
            command_family="torque_off",
            requested_targets=None,
            resolved_targets=None,
            duration_ms=None,
            report_dir=_motion_report_dir(),
            author=getattr(args, "author", None),
        )
        report.update(
            {
                "operation": "torque_off",
                "operation_group": "live_write" if transport.status.mode == LIVE_SERIAL_MODE else "read_safe",
                "profile_name": profile.profile_name,
                "calibration_status": bridge.calibration_status,
                "live_motion_enabled": bridge.live_motion_enabled,
                "arm_status": _arm_status_payload(
                    port=transport.status.port,
                    baud_rate=transport.status.baud_rate,
                    calibration_path=settings.blink_head_calibration,
                ),
            }
        )
        return report
    finally:
        transport.close()


def safe_idle_command(args: argparse.Namespace) -> dict:
    settings, profile, calibration, transport, bridge = _bench_context(args)
    try:
        report = execute_bench_command(
            transport=transport,
            bridge=bridge,
            profile=profile,
            calibration=calibration,
            command_family="safe_idle",
            requested_targets=neutral_targets(calibration, profile),
            resolved_targets=neutral_targets(calibration, profile),
            duration_ms=max(int(profile.neutral_recovery_ms or 220), int(profile.minimum_transition_ms or 80)),
            report_dir=_motion_report_dir(),
            author=getattr(args, "author", None),
        )
        report.update(
            {
                "operation": "safe_idle",
                "operation_group": "live_write" if transport.status.mode == LIVE_SERIAL_MODE else "read_safe",
                "profile_name": profile.profile_name,
                "calibration_status": bridge.calibration_status,
                "live_motion_enabled": bridge.live_motion_enabled,
                "arm_status": _arm_status_payload(
                    port=transport.status.port,
                    baud_rate=transport.status.baud_rate,
                    calibration_path=settings.blink_head_calibration,
                ),
            }
        )
        return report
    finally:
        transport.close()


def set_range(args: argparse.Namespace) -> dict:
    settings = build_settings_from_args(args)
    profile = load_head_profile(settings.blink_head_profile)
    calibration = load_head_calibration(settings.blink_head_calibration, profile=profile)
    stamp_calibration_provenance(calibration, profile=profile, transport=None, author=getattr(args, "author", None))
    joint = next((item for item in calibration.joint_records if item.joint_name == args.joint), None)
    if joint is None:
        raise SystemExit(f"unknown_joint:{args.joint}")
    joint.raw_min = int(args.raw_min)
    joint.raw_max = int(args.raw_max)
    if args.confirm_mirrored is not None:
        joint.mirrored_direction_confirmed = args.confirm_mirrored.lower() == "true"
    joint.error = None if joint.error == "range_conflict_from_capture" else joint.error
    joint.notes = [note for note in joint.notes if not str(note).startswith(RANGE_CONFLICT_NOTE_PREFIX)]
    joint.notes.append("range_updated")
    calibration.updated_at = utc_now()
    output_path = _calibration_output_path(args)
    if output_path is not None:
        save_head_calibration(calibration, output_path)
    payload = calibration.model_dump(mode="json")
    payload["operation"] = "set_range"
    payload["operation_group"] = "persistent_config_write"
    if output_path is not None:
        payload["output_path"] = str(output_path)
    return payload


def validate_coupling(args: argparse.Namespace) -> dict:
    settings = build_settings_from_args(args)
    profile = load_head_profile(settings.blink_head_profile)
    calibration = load_head_calibration(settings.blink_head_calibration, profile=profile)
    joint_names = {joint.joint_name for joint in profile.joints if joint.enabled}
    mirrored_confirmations = {
        joint.joint_name: joint.mirrored_direction_confirmed
        for joint in calibration.joint_records
    }
    results: dict[str, dict[str, object]] = {}
    for rule in profile.coupling_rules:
        affected_present = all(name in joint_names for name in rule.affected_joints)
        detail = "ok" if affected_present else "missing_joint_definition"
        if affected_present and rule.name in {"mirrored_eyelids", "mirrored_brows"}:
            confirmed = [
                mirrored_confirmations.get(name)
                for name in rule.affected_joints
                if name in mirrored_confirmations
            ]
            if confirmed and not all(item is True for item in confirmed):
                detail = "needs_bench_confirmation"
        results[rule.name] = {
            "ok": detail == "ok",
            "detail": detail,
            "affected_joints": rule.affected_joints,
        }
    conflicted_joints = sorted(conflicting_range_joints(calibration))
    results["range_conflicts"] = {
        "ok": not conflicted_joints,
        "detail": "ok" if not conflicted_joints else "range_conflict_from_capture",
        "affected_joints": conflicted_joints,
    }
    calibration.coupling_validation = {name: str(item["detail"]) for name, item in results.items()}
    output_path = _calibration_output_path(args)
    if output_path is not None:
        save_head_calibration(calibration, output_path)
    return {
        "operation": "validate_coupling",
        "profile_name": profile.profile_name,
        "results": results,
        "all_ok": all(item["ok"] for item in results.values()),
        **({"output_path": str(output_path)} if output_path is not None else {}),
    }


def save_calibration(args: argparse.Namespace) -> dict:
    settings = build_settings_from_args(args)
    profile = load_head_profile(settings.blink_head_profile)
    calibration = load_head_calibration(settings.blink_head_calibration, profile=profile)
    calibration.updated_at = utc_now()
    stamp_calibration_provenance(calibration, profile=profile, transport=None, author=getattr(args, "author", None))
    output_path = _calibration_output_path(args) or Path(args.calibration)
    save_head_calibration(calibration, output_path)
    payload = calibration.model_dump(mode="json")
    payload["operation"] = "save_calibration"
    payload["operation_group"] = "persistent_config_write"
    payload["output_path"] = str(output_path)
    return payload


def health_report(args: argparse.Namespace) -> dict:
    settings = build_settings_from_args(args)
    profile = load_head_profile(settings.blink_head_profile)
    settings = settings.model_copy(update={"blink_servo_baud": resolve_cli_baud(args, profile)}, deep=True)
    calibration = load_head_calibration(settings.blink_head_calibration, profile=profile)
    transport = build_servo_transport(settings, profile)
    bridge = FeetechBodyBridge(transport=transport, profile=profile, calibration=calibration)
    try:
        health = bridge.poll_health()
        return {
            "operation": "health",
            "operation_group": "read_safe",
            "profile_name": profile.profile_name,
            "calibration_status": bridge.calibration_status,
            "live_motion_enabled": bridge.live_motion_enabled,
            "transport_status": transport_summary(transport),
            "servo_health": {name: record.model_dump(mode="json") for name, record in health.items()},
        }
    finally:
        transport.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Blink-AI Feetech/ST head calibration and bring-up tool.")
    parser.add_argument("--profile", default="src/embodied_stack/body/profiles/robot_head_v1.json")
    parser.add_argument("--calibration", default=str(DEFAULT_STAGE_B_CALIBRATION_PATH))
    parser.add_argument("--transport", default="dry_run", choices=["dry_run", "fixture_replay", "live_serial"])
    parser.add_argument("--port", default=None)
    parser.add_argument("--baud", type=int, default=None)
    parser.add_argument("--timeout-seconds", type=float, default=0.2)
    parser.add_argument("--fixture", default=None)
    parser.add_argument("--author", default=None)

    subparsers = parser.add_subparsers(dest="command", required=True)

    scan = subparsers.add_parser("scan", help="Ping a range of servo IDs, optionally across likely baud rates.")
    scan.add_argument("--ids", default=None, help="Comma-separated list or ranges, e.g. 1-11 or 1,2,3")
    scan.add_argument("--auto-scan-baud", action="store_true", help="Probe profile auto-scan baud rates in addition to --baud.")
    scan.set_defaults(handler=scan_bus)

    ports = subparsers.add_parser("ports", help="List local serial devices and mark the preferred Mac bring-up port.")
    ports.set_defaults(handler=list_ports_command)

    doctor = subparsers.add_parser("doctor", help="Run the read-only Stage A bring-up workflow and write an artifact report.")
    doctor.add_argument("--ids", default=None, help="Comma-separated list or ranges, e.g. 1-11 or 1,2,3")
    doctor.add_argument("--auto-scan-baud", action="store_true", help="Probe profile auto-scan baud rates in addition to --baud.")
    doctor.add_argument("--report", default=str(DEFAULT_BRINGUP_REPORT_PATH))
    doctor.set_defaults(handler=doctor_command)

    arm = subparsers.add_parser("arm-live-motion", help="Create a short-lived arm lease for Stage B live motion.")
    arm.add_argument("--ttl-seconds", type=float, default=60.0)
    arm.set_defaults(handler=arm_live_motion)

    disarm = subparsers.add_parser("disarm-live-motion", help="Clear the Stage B live motion arm lease.")
    disarm.set_defaults(handler=disarm_live_motion)

    ping = subparsers.add_parser("ping", help="Ping specific servo IDs.")
    ping.add_argument("--ids", default=None)
    ping.set_defaults(handler=ping_ids)

    read_position = subparsers.add_parser("read-position", help="Read current position from specific servo IDs.")
    read_position.add_argument("--ids", default=None)
    read_position.set_defaults(handler=read_positions)

    read_health = subparsers.add_parser("read-health", help="Read richer bench health from specific servo IDs.")
    read_health.add_argument("--ids", default=None)
    read_health.set_defaults(handler=read_health_report)

    bench_health = subparsers.add_parser("bench-health", help="Read full Stage B bench health plus arm and calibration status.")
    bench_health.set_defaults(handler=bench_health_command)

    power_preflight = subparsers.add_parser("power-preflight", help="Run the investor-show idle power preflight with two bench-health reads.")
    power_preflight.set_defaults(handler=power_preflight_command)

    suggest_env = subparsers.add_parser("suggest-env", help="Print the recommended environment values for desktop_serial_body.")
    suggest_env.set_defaults(handler=suggest_env_command)

    motion_config = subparsers.add_parser("motion-config", help="Report effective motion-control settings and optional live acceleration verification.")
    motion_config.add_argument("--speed-override", type=int, default=None)
    motion_config.add_argument("--acceleration-override", type=int, default=None)
    motion_config.add_argument("--apply-live-acceleration", action="store_true")
    motion_config.add_argument(
        "--confirm-live-write",
        action="store_true",
        help="Required when applying acceleration to live hardware for verification.",
    )
    motion_config.set_defaults(handler=motion_config_command)

    usable_range = subparsers.add_parser("usable-range", help="Report calibration health and the maximum-safe range-demo envelope.")
    usable_range.add_argument("--preset", choices=sorted(available_range_demo_presets()), default="servo_range_showcase_joint_envelope_v1")
    usable_range.add_argument("--sequence", choices=sorted(available_range_demo_sequences()), default=None)
    usable_range.set_defaults(handler=usable_range_command)

    revalidate = subparsers.add_parser(
        "revalidate-live-ranges",
        help="Run operator-confirmed live joint-family revalidation and persist the saved live calibration.",
    )
    revalidate.add_argument("--family", choices=sorted(available_revalidation_families()), default=None)
    revalidate.add_argument("--resume-from", choices=sorted(available_revalidation_families()), default=None)
    revalidate.add_argument("--output-dir", default=None)
    revalidate.add_argument(
        "--confirm-live-write",
        action="store_true",
        help="Required for live revalidation writes.",
    )
    revalidate.add_argument(
        "--confirm-mechanical-clearance",
        action="store_true",
        help="Required to confirm mechanical clearance before widening beyond the template profile.",
    )
    revalidate.add_argument(
        "--confirm-widen-beyond-profile",
        action="store_true",
        help="Required to allow the revalidation lane to search beyond the template profile JSON.",
    )
    revalidate.set_defaults(handler=revalidate_live_ranges_command)

    range_demo = subparsers.add_parser("range-demo", help="Run the canonical standalone servo range showcase through the bench transport.")
    range_demo.add_argument("--preset", choices=sorted(available_range_demo_presets()), default="servo_range_showcase_joint_envelope_v1")
    range_demo.add_argument("--sequence", choices=sorted(available_range_demo_sequences()), default="servo_range_showcase_v1")
    range_demo.add_argument(
        "--confirm-live-write",
        action="store_true",
        help="Required for live range-demo playback.",
    )
    range_demo.set_defaults(handler=range_demo_command)

    list_semantic = subparsers.add_parser("list-semantic-actions", help="List the Stage D semantic action library and tuning override status.")
    list_semantic.add_argument("--smoke-safe-only", action="store_true")
    list_semantic.set_defaults(handler=list_semantic_actions_command)

    semantic_smoke = subparsers.add_parser("semantic-smoke", help="Run one semantic action through the Stage D compiler and bench transport.")
    semantic_smoke.add_argument("--action", required=True)
    semantic_smoke.add_argument("--intensity", type=float, default=1.0)
    semantic_smoke.add_argument("--repeat-count", type=int, default=1)
    semantic_smoke.add_argument("--note", default=None)
    semantic_smoke.add_argument("--allow-bench-actions", action="store_true", help="Allow D3 bench-only semantic actions.")
    semantic_smoke.add_argument(
        "--confirm-live-write",
        action="store_true",
        help="Required for live semantic smoke actions that move hardware.",
    )
    semantic_smoke.set_defaults(handler=semantic_smoke_command)

    teacher_review = subparsers.add_parser("teacher-review", help="Record Stage D teacher feedback and optional tuning deltas.")
    teacher_review.add_argument("--action", required=True)
    teacher_review.add_argument("--review", required=True, choices=["good", "adjust", "bad"])
    teacher_review.add_argument("--note", default=None)
    teacher_review.add_argument("--proposed-tuning-delta", default=None, help="JSON object with top-level tuning fields or action_overrides.")
    teacher_review.add_argument("--apply-tuning", action="store_true")
    teacher_review.set_defaults(handler=teacher_review_command)

    move_joint = subparsers.add_parser("move-joint", help="Apply a clamped small bench move to one joint.")
    move_joint.add_argument("--joint", required=True)
    move_joint_targets = move_joint.add_mutually_exclusive_group(required=True)
    move_joint_targets.add_argument("--delta", type=int, default=None)
    move_joint_targets.add_argument("--target", type=int, default=None)
    move_joint.add_argument("--duration-ms", type=int, default=600)
    move_joint.set_defaults(handler=move_joint_command)

    sync_move = subparsers.add_parser("sync-move", help="Run one fixed safe Stage B sync move group.")
    sync_move.add_argument("--group", required=True, choices=sorted(SAFE_SYNC_GROUPS))
    sync_move.add_argument("--duration-ms", type=int, default=600)
    sync_move.set_defaults(handler=sync_move_command)

    torque_on = subparsers.add_parser("torque-on", help="Enable torque on all enabled servos after arm and saved calibration checks.")
    torque_on.set_defaults(handler=torque_on_command)

    torque_off = subparsers.add_parser("torque-off", help="Disable torque on all enabled servos as a recovery action.")
    torque_off.set_defaults(handler=torque_off_command)

    safe_idle = subparsers.add_parser("safe-idle", help="Enter Stage B safe idle using torque-off or neutral recovery.")
    safe_idle.set_defaults(handler=safe_idle_command)

    write_neutral = subparsers.add_parser("write-neutral", help="Write the profile neutral pose slowly.")
    write_neutral.add_argument("--duration-ms", type=int, default=800)
    write_neutral.add_argument(
        "--confirm-live-write",
        action="store_true",
        help="Required for live_serial writes after external power, bus wiring, and safe stop handling are confirmed.",
    )
    write_neutral.set_defaults(handler=write_neutral_pose)

    servo_lab_catalog = subparsers.add_parser("servo-lab-catalog", help="List the Mac Servo Lab joint catalog with current readback and bounds.")
    servo_lab_catalog.set_defaults(handler=servo_lab_catalog_command)

    servo_lab_readback = subparsers.add_parser("servo-lab-readback", help="Read current raw position and metadata for one Servo Lab joint or the full catalog.")
    servo_lab_readback.add_argument("--joint", default=None)
    servo_lab_readback.add_argument("--include-health", action="store_true", default=True)
    servo_lab_readback.add_argument("--no-include-health", action="store_false", dest="include_health")
    servo_lab_readback.set_defaults(handler=servo_lab_readback_command)

    servo_lab_move = subparsers.add_parser("servo-lab-move", help="Run one raw Servo Lab move without the Stage B smoke clamp.")
    servo_lab_move.add_argument("--joint", required=True)
    servo_lab_move.add_argument(
        "--reference-mode",
        required=True,
        choices=["absolute_raw", "neutral_delta", "current_delta"],
    )
    servo_lab_move.add_argument("--target-raw", type=int, default=None)
    servo_lab_move.add_argument("--delta-counts", type=int, default=None)
    servo_lab_move.add_argument("--lab-min", type=int, default=None)
    servo_lab_move.add_argument("--lab-max", type=int, default=None)
    servo_lab_move.add_argument("--duration-ms", type=int, default=600)
    servo_lab_move.add_argument("--speed-override", type=int, default=None)
    servo_lab_move.add_argument("--acceleration-override", type=int, default=None)
    servo_lab_move.add_argument("--note", default=None)
    servo_lab_move.add_argument(
        "--confirm-live-write",
        action="store_true",
        help="Required for live Servo Lab move commands.",
    )
    servo_lab_move.set_defaults(handler=servo_lab_move_command)

    servo_lab_sweep = subparsers.add_parser("servo-lab-sweep", help="Run a bounded Servo Lab min↔max sweep with explicit sequential dwell.")
    servo_lab_sweep.add_argument("--joint", required=True)
    servo_lab_sweep.add_argument("--lab-min", type=int, default=None)
    servo_lab_sweep.add_argument("--lab-max", type=int, default=None)
    servo_lab_sweep.add_argument("--cycles", type=int, default=1)
    servo_lab_sweep.add_argument("--duration-ms", type=int, default=600)
    servo_lab_sweep.add_argument("--dwell-ms", type=int, default=250)
    servo_lab_sweep.add_argument("--speed-override", type=int, default=None)
    servo_lab_sweep.add_argument("--acceleration-override", type=int, default=None)
    servo_lab_sweep.add_argument("--return-to-neutral", action="store_true", default=True)
    servo_lab_sweep.add_argument("--no-return-to-neutral", action="store_false", dest="return_to_neutral")
    servo_lab_sweep.add_argument("--note", default=None)
    servo_lab_sweep.add_argument(
        "--confirm-live-write",
        action="store_true",
        help="Required for live Servo Lab sweep commands.",
    )
    servo_lab_sweep.set_defaults(handler=servo_lab_sweep_command)

    servo_lab_save = subparsers.add_parser("servo-lab-save-calibration", help="Save Servo Lab neutral or range updates back into calibration.")
    servo_lab_save.add_argument("--joint", required=True)
    servo_lab_save.add_argument("--save-current-as-neutral", action="store_true")
    servo_lab_save.add_argument("--raw-min", type=int, default=None)
    servo_lab_save.add_argument("--raw-max", type=int, default=None)
    servo_lab_save.add_argument("--confirm-mirrored", choices=["true", "false"], default=None)
    servo_lab_save.add_argument("--output", default=None)
    servo_lab_save.add_argument("--in-place", action="store_true")
    servo_lab_save.set_defaults(handler=servo_lab_save_calibration_command)

    dump = subparsers.add_parser("dump-profile-calibration", help="Read current positions and save a calibration JSON record.")
    dump.add_argument("--output", default=None)
    dump.add_argument("--in-place", action="store_true")
    dump.set_defaults(handler=dump_calibration)

    capture = subparsers.add_parser("capture-neutral", help="Capture current positions as neutral values in a v2 calibration record.")
    capture.add_argument("--output", default=None)
    capture.add_argument("--in-place", action="store_true")
    capture.add_argument(
        "--confirm-live-write",
        action="store_true",
        help="Required when capturing neutral from live hardware into a saved calibration record.",
    )
    capture.add_argument(
        "--confirm-visual-neutral",
        action="store_true",
        help="Required for live capture to confirm the operator has visually verified the looking-forward neutral pose.",
    )
    capture.set_defaults(handler=capture_neutral)

    set_range_parser = subparsers.add_parser("set-range", help="Update min/max values for a joint in a calibration record.")
    set_range_parser.add_argument("--joint", required=True)
    set_range_parser.add_argument("--raw-min", required=True, type=int)
    set_range_parser.add_argument("--raw-max", required=True, type=int)
    set_range_parser.add_argument("--confirm-mirrored", choices=["true", "false"], default=None)
    set_range_parser.add_argument("--output", default=None)
    set_range_parser.add_argument("--in-place", action="store_true")
    set_range_parser.set_defaults(handler=set_range)

    validate = subparsers.add_parser("validate-coupling", help="Validate that the current profile/calibration covers the required coupling rules.")
    validate.add_argument("--output", default=None)
    validate.add_argument("--in-place", action="store_true")
    validate.set_defaults(handler=validate_coupling)

    save = subparsers.add_parser("save-calibration", help="Write the current calibration record back out as blink_head_calibration/v2.")
    save.add_argument("--output", default=None)
    save.add_argument("--in-place", action="store_true")
    save.set_defaults(handler=save_calibration)

    health = subparsers.add_parser("health", help="Poll per-joint health from the current transport.")
    health.set_defaults(handler=health_report)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        result = args.handler(args)
    except ServoTransportError as exc:
        print(
            json.dumps(
                {
                    "operation": getattr(args, "command", "unknown"),
                    "accepted": False,
                    "reason_code": exc.classification,
                    "detail": exc.detail,
                    "error": f"{exc.classification}:{exc.detail}",
                },
                indent=2,
                default=str,
            )
        )
        return 1
    print(json.dumps(result, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
