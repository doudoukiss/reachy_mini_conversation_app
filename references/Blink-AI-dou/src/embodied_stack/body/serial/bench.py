from __future__ import annotations

import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from embodied_stack.shared.contracts.body import BodyCommandOutcomeRecord, CompiledAnimation, CompiledBodyFrame, HeadCalibrationRecord, HeadProfile, utc_now

from .driver import FeetechBodyBridge
from .health import read_bench_health_many
from .transport import BaseServoTransport, LIVE_SERIAL_MODE, ServoTransportError

DEFAULT_ARM_LEASE_PATH = Path("runtime/serial/live_motion_arm.json")
DEFAULT_MOTION_REPORT_DIR = Path("runtime/serial/motion_reports")
LIVE_CONFIRM_MAX_ATTEMPTS = 3
LIVE_CONFIRM_RETRY_DELAY_SECONDS = 0.03
RANGE_CONFLICT_NOTE_PREFIX = "range_conflict_from_capture"
SAFE_SYNC_GROUPS: dict[str, dict[str, int]] = {
    "head_up_small": {"head_pitch_pair_a": 100, "head_pitch_pair_b": -100},
    "head_down_small": {"head_pitch_pair_a": -100, "head_pitch_pair_b": 100},
    "head_tilt_right_small": {"head_pitch_pair_a": 100},
    "head_tilt_left_small": {"head_pitch_pair_b": -100},
    "eyes_left_small": {"eye_yaw": -100},
    "eyes_right_small": {"eye_yaw": 100},
    "eyes_up_small": {"eye_pitch": 100},
    "eyes_down_small": {"eye_pitch": -100},
    "lids_open_small": {
        "lower_lid_left": -60,
        "upper_lid_left": 60,
        "lower_lid_right": 60,
        "upper_lid_right": -60,
    },
    "lids_close_small": {
        "lower_lid_left": 60,
        "upper_lid_left": -60,
        "lower_lid_right": -60,
        "upper_lid_right": 60,
    },
    "brows_raise_small": {"brow_left": 60, "brow_right": -60},
    "brows_lower_small": {"brow_left": -60, "brow_right": 60},
}


def transport_summary(transport: BaseServoTransport) -> dict[str, Any]:
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


def profile_servo_ids(profile: HeadProfile) -> list[int]:
    ids: list[int] = []
    for joint in profile.joints:
        if joint.enabled:
            ids.extend(joint.servo_ids)
    return sorted({int(servo_id) for servo_id in ids})


def calibration_record_by_joint(calibration: HeadCalibrationRecord) -> dict[str, Any]:
    return {record.joint_name: record for record in calibration.joint_records}


def neutral_targets(calibration: HeadCalibrationRecord, profile: HeadProfile) -> dict[str, int]:
    joint_records = calibration_record_by_joint(calibration)
    targets: dict[str, int] = {}
    for joint in profile.joints:
        if not joint.enabled:
            continue
        record = joint_records.get(joint.joint_name)
        targets[joint.joint_name] = int(record.neutral if record is not None else joint.neutral)
    return targets


def conflicting_range_joints(calibration: HeadCalibrationRecord) -> set[str]:
    conflicts: set[str] = set()
    for record in calibration.joint_records:
        if any(str(note).startswith(RANGE_CONFLICT_NOTE_PREFIX) for note in record.notes):
            conflicts.add(record.joint_name)
    return conflicts


def coupling_validation_ready(calibration: HeadCalibrationRecord) -> bool:
    return bool(calibration.coupling_validation) and all(
        str(detail) == "ok" for detail in calibration.coupling_validation.values()
    )


def motion_smoke_limit(joint_name: str) -> int:
    if joint_name in {"head_yaw", "head_pitch_pair_a", "head_pitch_pair_b", "eye_pitch", "eye_yaw"}:
        return 100
    return 60


def post_command_settle_seconds(
    *,
    transport: BaseServoTransport,
    profile: HeadProfile,
    command_family: str,
    duration_ms: int | None,
    compiled_animation: CompiledAnimation | None,
) -> float:
    if transport.status.mode != LIVE_SERIAL_MODE:
        return 0.0
    if command_family in {"torque_on", "torque_off"}:
        return 0.05
    if command_family in {"semantic_smoke", "range_demo"} and compiled_animation is not None:
        settle_ms = int(compiled_animation.total_duration_ms or 0)
    elif command_family == "safe_idle":
        settle_ms = int(profile.neutral_recovery_ms or profile.default_transition_ms or 220)
    else:
        settle_ms = int(duration_ms or profile.default_transition_ms or 120)
    padded_ms = min(max(settle_ms + 150, 150), 2000)
    return padded_ms / 1000.0


def normalize_path(value: str | Path) -> str:
    return str(Path(value).expanduser().resolve())


def _parse_timestamp(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        return datetime.fromisoformat(value)
    raise ServoTransportError("motion_not_armed", f"invalid_arm_timestamp:{value!r}")


def read_arm_lease(path: str | Path = DEFAULT_ARM_LEASE_PATH) -> dict[str, Any] | None:
    lease_path = Path(path)
    if not lease_path.exists():
        return None
    return json.loads(lease_path.read_text(encoding="utf-8"))


def write_arm_lease(
    *,
    port: str | None,
    baud_rate: int,
    calibration_path: str | Path,
    ttl_seconds: float,
    path: str | Path = DEFAULT_ARM_LEASE_PATH,
    author: str | None = None,
) -> dict[str, Any]:
    armed_at = utc_now()
    lease = {
        "port": port,
        "baud_rate": int(baud_rate),
        "calibration_path": normalize_path(calibration_path),
        "armed_at": armed_at,
        "expires_at": armed_at + timedelta(seconds=max(float(ttl_seconds), 1.0)),
    }
    if author:
        lease["author"] = author
    lease_path = Path(path)
    lease_path.parent.mkdir(parents=True, exist_ok=True)
    lease_path.write_text(json.dumps(lease, indent=2, default=str) + "\n", encoding="utf-8")
    lease["lease_path"] = str(lease_path)
    return lease


def clear_arm_lease(path: str | Path = DEFAULT_ARM_LEASE_PATH) -> dict[str, Any]:
    lease_path = Path(path)
    previous = read_arm_lease(lease_path)
    if lease_path.exists():
        lease_path.unlink()
    return {
        "lease_path": str(lease_path),
        "cleared": previous is not None,
        "previous_lease": previous,
    }


def validate_motion_arm(
    *,
    port: str | None,
    baud_rate: int,
    calibration_path: str | Path,
    path: str | Path = DEFAULT_ARM_LEASE_PATH,
) -> dict[str, Any]:
    lease = read_arm_lease(path)
    if lease is None:
        raise ServoTransportError("motion_not_armed", "live_motion_arm_missing")
    expires_at = lease.get("expires_at")
    if expires_at is None or utc_now() > _parse_timestamp(expires_at):
        raise ServoTransportError("motion_not_armed", "live_motion_arm_expired")
    if lease.get("port") != port:
        raise ServoTransportError("motion_not_armed", f"live_motion_arm_port_mismatch:{lease.get('port')}:{port}")
    if int(lease.get("baud_rate") or 0) != int(baud_rate):
        raise ServoTransportError("motion_not_armed", f"live_motion_arm_baud_mismatch:{lease.get('baud_rate')}:{baud_rate}")
    if normalize_path(lease.get("calibration_path") or "") != normalize_path(calibration_path):
        raise ServoTransportError("motion_not_armed", "live_motion_arm_calibration_mismatch")
    return lease


def confirm_live_transport(transport: BaseServoTransport, profile: HeadProfile) -> list[int]:
    if transport.status.mode != LIVE_SERIAL_MODE:
        return []
    if not hasattr(transport, "confirm_live"):
        if transport.status.confirmed_live and transport.status.healthy:
            return []
        raise ServoTransportError(
            "transport_unconfirmed",
            transport.status.last_error or "live_transport_not_confirmed",
        )
    last_error = transport.status.last_error or "live_transport_not_confirmed"
    for attempt in range(LIVE_CONFIRM_MAX_ATTEMPTS):
        found = transport.confirm_live(profile_servo_ids(profile))
        if found and transport.status.confirmed_live and transport.status.healthy:
            return found
        last_error = transport.status.last_error or "live_transport_not_confirmed"
        transient = last_error.startswith(("timeout:", "invalid_reply:", "transport_unconfirmed:"))
        if attempt + 1 >= LIVE_CONFIRM_MAX_ATTEMPTS or not transient:
            break
        time.sleep(LIVE_CONFIRM_RETRY_DELAY_SECONDS)
    raise ServoTransportError(
        "transport_unconfirmed",
        last_error,
    )


def resolve_joint_targets(
    *,
    calibration: HeadCalibrationRecord,
    joint_name: str,
    delta: int | None,
    target: int | None,
) -> tuple[dict[str, int], dict[str, int], list[str]]:
    records = calibration_record_by_joint(calibration)
    record = records.get(joint_name)
    if record is None:
        raise ServoTransportError("out_of_range", f"unknown_joint:{joint_name}")
    neutral = int(record.neutral)
    requested_value = neutral + int(delta) if delta is not None else int(target)
    smoke_limit = motion_smoke_limit(joint_name)
    clamped_value = requested_value
    notes: list[str] = []
    lower_smoke = neutral - smoke_limit
    upper_smoke = neutral + smoke_limit
    if clamped_value < lower_smoke:
        notes.append(f"smoke_limit_clamp:{joint_name}:{clamped_value}->{lower_smoke}")
        clamped_value = lower_smoke
    if clamped_value > upper_smoke:
        notes.append(f"smoke_limit_clamp:{joint_name}:{clamped_value}->{upper_smoke}")
        clamped_value = upper_smoke
    if clamped_value < int(record.raw_min):
        notes.append(f"raw_min_clamp:{joint_name}:{clamped_value}->{record.raw_min}")
        clamped_value = int(record.raw_min)
    if clamped_value > int(record.raw_max):
        notes.append(f"raw_max_clamp:{joint_name}:{clamped_value}->{record.raw_max}")
        clamped_value = int(record.raw_max)
    return {joint_name: requested_value}, {joint_name: clamped_value}, notes


def resolve_sync_group_targets(
    *,
    calibration: HeadCalibrationRecord,
    group_name: str,
) -> tuple[dict[str, int], dict[str, int], list[str]]:
    if group_name not in SAFE_SYNC_GROUPS:
        raise ServoTransportError("out_of_range", f"unknown_sync_group:{group_name}")
    requested: dict[str, int] = {}
    clamped: dict[str, int] = {}
    notes: list[str] = []
    for joint_name, delta in SAFE_SYNC_GROUPS[group_name].items():
        joint_requested, joint_clamped, joint_notes = resolve_joint_targets(
            calibration=calibration,
            joint_name=joint_name,
            delta=delta,
            target=None,
        )
        requested.update(joint_requested)
        clamped.update(joint_clamped)
        notes.extend(joint_notes)
    return requested, clamped, notes


def read_position_snapshot(transport: BaseServoTransport, servo_ids: list[int]) -> dict[int, dict[str, Any]]:
    positions: dict[int, dict[str, Any]] = {}
    for servo_id in servo_ids:
        try:
            positions[servo_id] = {"position": transport.read_position(servo_id)}
        except ServoTransportError as exc:
            positions[servo_id] = {"error": f"{exc.classification}:{exc.detail}"}
    return positions


def read_bench_snapshot(transport: BaseServoTransport, servo_ids: list[int]) -> dict[str, dict[int, dict[str, Any]]]:
    return {
        "positions": read_position_snapshot(transport, servo_ids),
        "health": read_bench_health_many(transport, servo_ids),
    }


def snapshot_has_errors(snapshot: dict[str, dict[int, dict[str, Any]]]) -> bool:
    return any("error" in payload for payload in snapshot["positions"].values()) or any(
        "error" in payload for payload in snapshot["health"].values()
    )


def failure_reason_from_snapshot(
    *,
    command_family: str,
    targeted_joints: dict[str, int] | None,
    transport: BaseServoTransport,
    snapshot: dict[str, dict[int, dict[str, Any]]],
) -> tuple[str | None, list[str]]:
    notes: list[str] = []
    if transport.status.reason_code in {"timeout", "serial_unavailable"}:
        return transport.status.reason_code, notes
    for servo_id, payload in snapshot["positions"].items():
        if "error" in payload:
            notes.append(f"post_position_error:{servo_id}:{payload['error']}")
    for servo_id, payload in snapshot["health"].items():
        if "error" in payload:
            notes.append(f"post_health_error:{servo_id}:{payload['error']}")
    if notes:
        if targeted_joints and len(targeted_joints) > 1:
            return "power_sag_suspected", notes
        return "health_degraded", notes
    return None, notes


def build_motion_report_path(
    *,
    report_dir: str | Path,
    command_family: str,
) -> Path:
    timestamp = utc_now().strftime("%Y%m%dT%H%M%S%fZ")
    return Path(report_dir) / f"{timestamp}_{command_family}.json"


def execute_bench_command(
    *,
    transport: BaseServoTransport,
    bridge: FeetechBodyBridge,
    profile: HeadProfile,
    calibration: HeadCalibrationRecord,
    command_family: str,
    requested_targets: dict[str, int] | None,
    resolved_targets: dict[str, int] | None,
    duration_ms: int | None,
    compiled_animation: CompiledAnimation | None = None,
    range_demo_plan: dict[str, Any] | None = None,
    semantic_action_name: str | None = None,
    semantic_family: str | None = None,
    tuning_path: str | None = None,
    cleanup_mode: str | None = None,
    speed_override: int | None = None,
    acceleration_override: int | None = None,
    limit_overrides: dict[str, tuple[int, int]] | None = None,
    report_dir: str | Path = DEFAULT_MOTION_REPORT_DIR,
    author: str | None = None,
) -> dict[str, Any]:
    servo_ids = profile_servo_ids(profile)
    targeted_joint_names = sorted((resolved_targets or {}).keys())
    if snapshot_has_errors(pre_snapshot := read_bench_snapshot(transport, servo_ids)):
        raise ServoTransportError("health_degraded", "preflight_readback_unstable")

    outcome: BodyCommandOutcomeRecord
    failure_reason: str | None = None
    failure_notes: list[str] = []
    cleanup_result: dict[str, Any] | None = None

    try:
        if command_family in {"move_joint", "sync_move", "write_neutral", "servo_lab_move", "range_revalidation"}:
            if not resolved_targets:
                raise ServoTransportError("out_of_range", "no_resolved_targets")
            outcome, _ = bridge.execute_joint_targets(
                servo_targets=resolved_targets,
                duration_ms=duration_ms,
                command_type=command_family,
                requested_action_name=command_family,
                outcome_notes=[
                    *([f"author:{author}"] if author else []),
                    *([f"cleanup_mode:{cleanup_mode}"] if cleanup_mode else []),
                ],
                speed_override=speed_override,
                acceleration_override=acceleration_override,
                limit_overrides=limit_overrides,
            )
        elif command_family in {"semantic_smoke", "range_demo"}:
            if compiled_animation is None:
                raise ServoTransportError("out_of_range", f"{command_family}_requires_compiled_animation")
            outcome, _ = bridge.apply_compiled_animation(compiled_animation)
        elif command_family == "torque_on":
            transport.set_torque(servo_ids, enabled=True)
            outcome = BodyCommandOutcomeRecord(
                command_type="torque_on",
                requested_action_name="torque_on",
                canonical_action_name="torque_on",
                source_action_name="torque_on",
                outcome_status="torque_enabled",
                accepted=True,
                transport_mode=transport.status.mode,
                reason_code=transport.status.reason_code,
            )
        elif command_family == "torque_off":
            transport.set_torque(servo_ids, enabled=False)
            outcome = BodyCommandOutcomeRecord(
                command_type="torque_off",
                requested_action_name="torque_off",
                canonical_action_name="torque_off",
                source_action_name="torque_off",
                outcome_status="torque_disabled",
                accepted=True,
                transport_mode=transport.status.mode,
                reason_code=transport.status.reason_code,
            )
        elif command_family == "safe_idle":
            neutral_frame = CompiledBodyFrame(
                frame_name="safe_idle",
                servo_targets=neutral_targets(calibration, profile),
                duration_ms=max(int(profile.neutral_recovery_ms or 220), int(profile.minimum_transition_ms or 80)),
                compiler_notes=["stage_b_safe_idle"],
            )
            outcome, _ = bridge.safe_idle(
                torque_off=bool(profile.safe_idle_torque_off),
                neutral_frame=neutral_frame,
            )
        else:
            raise ServoTransportError("out_of_range", f"unsupported_command_family:{command_family}")

        if cleanup_mode == "neutral":
            cleanup_targets = neutral_targets(calibration, profile)
            cleanup_outcome, _ = bridge.execute_joint_targets(
                servo_targets=cleanup_targets,
                duration_ms=max(int(profile.neutral_recovery_ms or 220), int(profile.minimum_transition_ms or 80)),
                command_type=f"{command_family}_cleanup",
                requested_action_name="write_neutral",
                outcome_notes=["cleanup:neutral"],
            )
            cleanup_result = cleanup_outcome.model_dump(mode="json")
    except ServoTransportError as exc:
        failure_reason = exc.classification
        failure_notes.append(f"command_error:{exc.classification}:{exc.detail}")
        outcome = BodyCommandOutcomeRecord(
            command_type=command_family,
            requested_action_name=command_family,
            canonical_action_name=command_family,
            source_action_name=command_family,
            outcome_status="failed",
            accepted=False,
            rejected=True,
            transport_mode=transport.status.mode,
            reason_code=exc.classification,
            detail=exc.detail,
        )

    settle_seconds = post_command_settle_seconds(
        transport=transport,
        profile=profile,
        command_family=command_family,
        duration_ms=duration_ms,
        compiled_animation=compiled_animation,
    )
    if settle_seconds > 0:
        time.sleep(settle_seconds)
    post_snapshot = read_bench_snapshot(transport, servo_ids)
    if failure_reason is None:
        failure_reason, post_notes = failure_reason_from_snapshot(
            command_family=command_family,
            targeted_joints=resolved_targets,
            transport=transport,
            snapshot=post_snapshot,
        )
        failure_notes.extend(post_notes)
        if failure_reason is not None:
            outcome = outcome.model_copy(
                update={
                    "outcome_status": "health_degraded",
                    "reason_code": failure_reason,
                    "detail": ";".join(failure_notes) if failure_notes else None,
                }
            )

    report = {
        "generated_at": utc_now(),
        "command_family": command_family,
        "requested_targets": requested_targets or {},
        "clamped_targets": resolved_targets or {},
        "targeted_joints": targeted_joint_names,
        "semantic_action_name": semantic_action_name,
        "semantic_family": semantic_family,
        "compiled_animation": compiled_animation.model_dump(mode="json") if compiled_animation is not None else None,
        "range_demo_plan": range_demo_plan,
        "tuning_path": tuning_path,
        "duration_ms": duration_ms,
        "speed_override": speed_override,
        "acceleration_override": acceleration_override,
        "limit_overrides": {
            joint_name: [int(bounds[0]), int(bounds[1])]
            for joint_name, bounds in (limit_overrides or {}).items()
        },
        "settle_seconds": settle_seconds,
        "transport_status": transport_summary(transport),
        "before_position": pre_snapshot["positions"],
        "before_health": pre_snapshot["health"],
        "after_position": post_snapshot["positions"],
        "after_health": post_snapshot["health"],
        "request_response_history": transport.history_payload(),
        "outcome": outcome.model_dump(mode="json"),
        "cleanup_result": cleanup_result,
        "failure_reason": failure_reason,
        "stop_notes": failure_notes,
        "success": failure_reason is None and outcome.accepted,
    }
    report_path = build_motion_report_path(report_dir=report_dir, command_family=command_family)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
    report["report_path"] = str(report_path)
    return report


def execute_servo_lab_sweep(
    *,
    transport: BaseServoTransport,
    bridge: FeetechBodyBridge,
    profile: HeadProfile,
    calibration: HeadCalibrationRecord,
    joint_name: str,
    requested_targets: dict[str, int],
    sweep_plan: dict[str, Any],
    speed_override: int | None = None,
    acceleration_override: int | None = None,
    report_dir: str | Path = DEFAULT_MOTION_REPORT_DIR,
    author: str | None = None,
) -> dict[str, Any]:
    servo_ids = profile_servo_ids(profile)
    pre_snapshot = read_bench_snapshot(transport, servo_ids)
    if snapshot_has_errors(pre_snapshot):
        raise ServoTransportError("health_degraded", "preflight_readback_unstable")

    steps = list(sweep_plan.get("steps") or [])
    step_reports: list[dict[str, Any]] = []
    failure_reason: str | None = None
    failure_notes: list[str] = []
    final_snapshot = pre_snapshot
    last_outcome: BodyCommandOutcomeRecord | None = None
    started = time.perf_counter()

    for step in steps:
        step_id = str(step.get("step_id") or f"step_{len(step_reports) + 1}")
        target = int(step.get("target"))
        duration_ms = int(step.get("duration_ms") or 0)
        dwell_ms = int(step.get("dwell_ms") or 0)
        resolved_targets = {joint_name: target}
        try:
            last_outcome, _ = bridge.execute_joint_targets(
                servo_targets=resolved_targets,
                duration_ms=duration_ms,
                command_type="servo_lab_sweep",
                requested_action_name=f"{joint_name}:{step_id}",
                outcome_notes=[
                    f"servo_lab_sweep_step:{step_id}",
                    *([f"author:{author}"] if author else []),
                ],
                speed_override=speed_override,
                acceleration_override=acceleration_override,
            )
        except ServoTransportError as exc:
            failure_reason = exc.classification
            failure_notes.append(f"command_error:{exc.classification}:{exc.detail}")
            step_reports.append(
                {
                    "step_id": step_id,
                    "label": step.get("label"),
                    "requested_target": target,
                    "resolved_target": target,
                    "duration_ms": duration_ms,
                    "dwell_ms": dwell_ms,
                    "failure_reason": failure_reason,
                    "failure_detail": exc.detail,
                }
            )
            break

        if transport.status.mode == LIVE_SERIAL_MODE:
            settle_seconds = max(float(duration_ms + dwell_ms), 0.0) / 1000.0
            if settle_seconds > 0:
                time.sleep(settle_seconds)

        final_snapshot = read_bench_snapshot(transport, servo_ids)
        step_failure_reason, post_notes = failure_reason_from_snapshot(
            command_family="servo_lab_sweep",
            targeted_joints=resolved_targets,
            transport=transport,
            snapshot=final_snapshot,
        )
        if post_notes:
            failure_notes.extend(post_notes)
        step_reports.append(
            {
                "step_id": step_id,
                "label": step.get("label"),
                "requested_target": target,
                "resolved_target": target,
                "duration_ms": duration_ms,
                "dwell_ms": dwell_ms,
                "outcome": last_outcome.model_dump(mode="json"),
                "after_position": final_snapshot["positions"],
                "after_health": final_snapshot["health"],
                "failure_reason": step_failure_reason,
            }
        )
        if step_failure_reason is not None:
            failure_reason = step_failure_reason
            break

    elapsed_wall_clock_ms = round((time.perf_counter() - started) * 1000.0, 2)
    executed_frame_names = [str(step.get("step_id") or f"step_{index + 1}") for index, step in enumerate(steps)]
    if last_outcome is None:
        outcome = BodyCommandOutcomeRecord(
            command_type="servo_lab_sweep",
            requested_action_name=joint_name,
            canonical_action_name="servo_lab_sweep",
            source_action_name=joint_name,
            outcome_status="failed",
            accepted=False,
            rejected=True,
            clamped=bool(sweep_plan.get("clamp_notes")),
            transport_mode=transport.status.mode,
            reason_code=failure_reason,
            detail=";".join(failure_notes) if failure_notes else None,
            outcome_notes=[*([f"author:{author}"] if author else []), "servo_lab_sweep_failed_before_execution"],
            executed_frame_count=0,
            elapsed_wall_clock_ms=elapsed_wall_clock_ms,
            usable_range_audit=None,
        )
    else:
        outcome = last_outcome.model_copy(
            update={
                "command_type": "servo_lab_sweep",
                "requested_action_name": joint_name,
                "canonical_action_name": "servo_lab_sweep",
                "source_action_name": joint_name,
                "outcome_status": "health_degraded" if failure_reason else "sent",
                "accepted": failure_reason is None and last_outcome.accepted,
                "rejected": failure_reason is not None,
                "clamped": bool(sweep_plan.get("clamp_notes")),
                "reason_code": failure_reason or last_outcome.reason_code,
                "detail": ";".join(failure_notes) if failure_notes else last_outcome.detail,
                "outcome_notes": [
                    *last_outcome.outcome_notes,
                    *([f"author:{author}"] if author else []),
                    f"servo_lab_sweep_steps:{len(step_reports)}",
                ],
                "executed_frame_count": len(step_reports),
                "executed_frame_names": executed_frame_names[: len(step_reports)],
                "per_frame_duration_ms": [int(step.get("duration_ms") or 0) for step in steps[: len(step_reports)]],
                "per_frame_hold_ms": [int(step.get("dwell_ms") or 0) for step in steps[: len(step_reports)]],
                "elapsed_wall_clock_ms": elapsed_wall_clock_ms,
                "final_frame_name": executed_frame_names[min(len(step_reports), len(executed_frame_names)) - 1]
                if step_reports
                else None,
                "peak_compiled_targets": {
                    joint_name: max(int(step.get("target") or 0) for step in steps) if steps else 0
                },
            }
        )

    report = {
        "generated_at": utc_now(),
        "command_family": "servo_lab_sweep",
        "requested_targets": requested_targets,
        "clamped_targets": {
            joint_name: int(steps[-1]["target"]) if steps else None
        },
        "targeted_joints": [joint_name],
        "duration_ms": None,
        "sweep_plan": sweep_plan,
        "speed_override": speed_override,
        "acceleration_override": acceleration_override,
        "transport_status": transport_summary(transport),
        "before_position": pre_snapshot["positions"],
        "before_health": pre_snapshot["health"],
        "after_position": final_snapshot["positions"],
        "after_health": final_snapshot["health"],
        "steps": step_reports,
        "request_response_history": transport.history_payload(),
        "outcome": outcome.model_dump(mode="json"),
        "failure_reason": failure_reason,
        "stop_notes": failure_notes,
        "success": failure_reason is None and outcome.accepted,
    }
    report_path = build_motion_report_path(report_dir=report_dir, command_family="servo_lab_sweep")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
    report["report_path"] = str(report_path)
    return report


__all__ = [
    "DEFAULT_ARM_LEASE_PATH",
    "DEFAULT_MOTION_REPORT_DIR",
    "RANGE_CONFLICT_NOTE_PREFIX",
    "SAFE_SYNC_GROUPS",
    "clear_arm_lease",
    "confirm_live_transport",
    "conflicting_range_joints",
    "coupling_validation_ready",
    "execute_bench_command",
    "execute_servo_lab_sweep",
    "motion_smoke_limit",
    "neutral_targets",
    "normalize_path",
    "profile_servo_ids",
    "read_arm_lease",
    "read_bench_snapshot",
    "resolve_joint_targets",
    "resolve_sync_group_targets",
    "snapshot_has_errors",
    "transport_summary",
    "validate_motion_arm",
    "write_arm_lease",
]
