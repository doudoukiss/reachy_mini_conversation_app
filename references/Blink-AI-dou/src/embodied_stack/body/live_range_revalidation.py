from __future__ import annotations

from dataclasses import dataclass
import json
import time
from pathlib import Path
from typing import Any

from embodied_stack.shared.contracts import HeadCalibrationRecord, HeadProfile, utc_now

from .motion_audit import build_usable_range_audit
from .serial import LIVE_SERIAL_MODE, ServoTransportError
from .serial.bench import execute_bench_command, profile_servo_ids, read_bench_snapshot

COUNT_TO_DEGREES = 360.0 / 4096.0
DEFAULT_REVALIDATION_REPORT_DIR = Path("runtime/serial/live_range_revalidation")
SERVO_RAW_MIN = 0
SERVO_RAW_MAX = 4095
NECK_NEUTRAL_TARGET = 2047
NECK_NEUTRAL_TOLERANCE_COUNTS = 80
NECK_NEUTRAL_ASYMMETRY_TOLERANCE_COUNTS = 40


@dataclass(frozen=True)
class RevalidationProbe:
    probe_name: str
    family_name: str
    direction_label: str
    joint_signs: tuple[tuple[str, int], ...]
    limit_sides: tuple[tuple[str, str], ...]
    step_counts: int
    max_extension_counts: int
    duration_ms: int
    dwell_ms: int
    load_threshold: int


def available_revalidation_families() -> tuple[str, ...]:
    return tuple(_FAMILY_ORDER)


def resolve_revalidation_sequence(*, family: str | None, resume_from: str | None) -> list[str]:
    if family and resume_from:
        raise ServoTransportError(
            "out_of_range",
            "revalidate_live_ranges_family_and_resume_from_are_mutually_exclusive",
        )
    if family:
        if family not in _PROBES_BY_FAMILY:
            raise ServoTransportError("out_of_range", f"unknown_revalidation_family:{family}")
        return [family]
    if resume_from:
        if resume_from not in _FAMILY_ORDER:
            raise ServoTransportError("out_of_range", f"unknown_revalidation_resume_from:{resume_from}")
        index = _FAMILY_ORDER.index(resume_from)
        return list(_FAMILY_ORDER[index:])
    return list(_FAMILY_ORDER)


def recenter_neck_pair_neutral(
    *,
    profile: HeadProfile,
    calibration: HeadCalibrationRecord,
    calibration_source_path: str | None,
    transport,
    bridge,
    report_dir: str | Path,
) -> tuple[HeadCalibrationRecord, dict[str, object]]:
    center_targets = {
        "head_pitch_pair_a": NECK_NEUTRAL_TARGET,
        "head_pitch_pair_b": NECK_NEUTRAL_TARGET,
    }
    limit_overrides = _union_limit_overrides(
        profile=profile,
        calibration=calibration,
        joint_names=set(center_targets),
        extension_counts=0,
    )
    report = execute_bench_command(
        transport=transport,
        bridge=bridge,
        profile=profile,
        calibration=calibration,
        command_family="range_revalidation",
        requested_targets=dict(center_targets),
        resolved_targets=dict(center_targets),
        duration_ms=1200,
        limit_overrides=limit_overrides,
        report_dir=report_dir,
        author="range_revalidation:neck_recenter",
    )
    time.sleep(0.35)
    snapshot = read_bench_snapshot(
        transport,
        _servo_ids_for_joints(profile=profile, joint_names=set(center_targets)),
    )
    readback = _snapshot_readback_by_joint(
        profile=profile,
        snapshot=snapshot,
        joint_names=set(center_targets),
    )
    if set(readback) != set(center_targets):
        raise ServoTransportError(
            "revalidation_failed",
            "neck_recenter_missing_readback",
        )

    candidate = calibration.model_copy(deep=True)
    for joint_name, target in readback.items():
        record = _record_by_joint(candidate, joint_name)
        record.neutral = int(target)
        record.current_position = int(target)
        if "neck_pair_live_recentered" not in record.notes:
            record.notes.append("neck_pair_live_recentered")
    candidate.updated_at = utc_now()

    usable_audit = build_usable_range_audit(
        profile=profile,
        calibration=candidate,
        calibration_source_path=calibration_source_path,
    )
    suspicious = set(usable_audit.suspicious_joint_names)
    asymmetry = abs(int(readback["head_pitch_pair_a"]) - int(readback["head_pitch_pair_b"]))
    max_distance = max(abs(int(value) - NECK_NEUTRAL_TARGET) for value in readback.values())
    if {
        "head_pitch_pair_a",
        "head_pitch_pair_b",
    } & suspicious or asymmetry > NECK_NEUTRAL_ASYMMETRY_TOLERANCE_COUNTS or max_distance > NECK_NEUTRAL_TOLERANCE_COUNTS:
        raise ServoTransportError(
            "revalidation_failed",
            (
                "neck_recenter_unverified:"
                f"suspicious={sorted(suspicious)}:"
                f"asymmetry={asymmetry}:"
                f"max_distance={max_distance}"
            ),
        )

    return candidate, {
        "operation": "neck_pair_neutral_recenter",
        "center_target": NECK_NEUTRAL_TARGET,
        "requested_targets": center_targets,
        "readback": readback,
        "report_path": report["report_path"],
        "usable_range_audit": usable_audit.model_dump(mode="json"),
        "neutral_overrides": dict(readback),
        "asymmetry_counts": asymmetry,
    }


def run_family_revalidation(
    *,
    profile: HeadProfile,
    calibration: HeadCalibrationRecord,
    transport,
    bridge,
    family_name: str,
    report_dir: str | Path,
    allow_widen_beyond_profile: bool,
) -> dict[str, object]:
    if family_name not in _PROBES_BY_FAMILY:
        raise ServoTransportError("out_of_range", f"unknown_revalidation_family:{family_name}")
    probes = _PROBES_BY_FAMILY[family_name]
    side_overrides: dict[str, dict[str, int]] = {}
    probe_results: list[dict[str, object]] = []

    for probe in probes:
        probe_result = _run_probe(
            profile=profile,
            calibration=calibration,
            transport=transport,
            bridge=bridge,
            probe=probe,
            report_dir=report_dir,
            allow_widen_beyond_profile=allow_widen_beyond_profile,
        )
        probe_results.append(probe_result)
        for joint_name, side in probe_result["limit_sides"]:
            value = int(probe_result["confirmed_targets"][joint_name])
            joint_override = side_overrides.setdefault(joint_name, {})
            current = joint_override.get(side)
            if current is None:
                joint_override[side] = value
            elif side == "low":
                joint_override[side] = min(int(current), value)
            else:
                joint_override[side] = max(int(current), value)

    widened_beyond_profile = _widened_beyond_profile(
        profile=profile,
        side_overrides=side_overrides,
    )
    return {
        "family_name": family_name,
        "probe_results": probe_results,
        "side_overrides": side_overrides,
        "widened_beyond_profile": widened_beyond_profile,
    }


def apply_revalidation_overrides(
    *,
    calibration: HeadCalibrationRecord,
    neutral_overrides: dict[str, int] | None = None,
    side_overrides: dict[str, dict[str, int]] | None = None,
) -> HeadCalibrationRecord:
    updated = calibration.model_copy(deep=True)
    for joint_name, neutral in (neutral_overrides or {}).items():
        record = _record_by_joint(updated, joint_name)
        record.neutral = int(neutral)
        record.current_position = int(neutral)
    for joint_name, overrides in (side_overrides or {}).items():
        record = _record_by_joint(updated, joint_name)
        if "low" in overrides:
            record.raw_min = int(overrides["low"])
        if "high" in overrides:
            record.raw_max = int(overrides["high"])
        if "range_revalidated" not in record.notes:
            record.notes.append("range_revalidated")
        record.current_position = int(record.neutral)
    if side_overrides:
        updated.notes = [note for note in updated.notes if note != "live_range_revalidation_completed"]
        updated.notes.append("live_range_revalidation_completed")
    updated.updated_at = utc_now()
    return updated


def build_live_limits_table_rows(
    *,
    profile: HeadProfile,
    calibration: HeadCalibrationRecord,
) -> tuple[list[str], list[str]]:
    joint_rows = []
    records = {record.joint_name: record for record in calibration.joint_records}
    for joint in [item for item in profile.joints if item.enabled]:
        record = records[joint.joint_name]
        low_counts = int(record.neutral) - int(record.raw_min)
        high_counts = int(record.raw_max) - int(record.neutral)
        span_counts = int(record.raw_max) - int(record.raw_min)
        joint_rows.append(
            (
                f"| `{joint.joint_name}` | {record.raw_min} | {record.neutral} | {record.raw_max} | "
                f"{low_counts} / {_degrees(low_counts):.2f} | {high_counts} / {_degrees(high_counts):.2f} | "
                f"{span_counts} / {_degrees(span_counts):.2f} |"
            )
        )

    family_rows = []
    for row in _family_summary_rows(profile=profile, calibration=calibration):
        family_rows.append(
            f"| `{row['family_name']}` | {row['direction_low']} | {row['direction_high']} | "
            f"{row['counts_low']} / {row['degrees_low']:.2f} | {row['counts_high']} / {row['degrees_high']:.2f} | "
            f"{row['span_counts']} / {row['span_degrees']:.2f} |"
        )
    return joint_rows, family_rows


def render_live_limits_markdown(
    *,
    profile: HeadProfile,
    calibration: HeadCalibrationRecord,
    artifact_dir: str | None = None,
) -> str:
    joint_rows, family_rows = build_live_limits_table_rows(profile=profile, calibration=calibration)
    updated_at = calibration.updated_at.isoformat()
    artifact_pointer = artifact_dir or "`<update after next live revalidation>`"
    joint_directions = _joint_direction_notes()
    return "\n".join(
        [
            "# Robot Head Live Limits",
            "",
            "This document is the checked-in human-facing numeric truth for the currently calibrated live robot head.",
            "",
            "Executable authority:",
            f"- `runtime/calibrations/robot_head_live_v1.json`",
            "",
            "Template fallback only:",
            f"- `src/embodied_stack/body/profiles/robot_head_v1.json`",
            "",
            "Motion-policy companion:",
            f"- `docs/body_motion_tuning.md`",
            "",
            f"Last saved live-calibration update: `{updated_at}`",
            f"Most recent live artifact directory: {artifact_pointer}",
            "",
            "Conversion:",
            "- STS3032 raw counts run from `0..4095` for one full turn.",
            "- `1 count = 360 / 4096 = 0.087890625°`.",
            "- Degree values below are servo-shaft equivalent angles, not guaranteed visible head-output angles after linkage geometry.",
            "",
            "## Scope",
            "",
            "- Applies to the connected 11-servo robot head using the saved live calibration above.",
            "- Planner/runtime semantic behavior still compiles through `body/`; this doc only records calibrated raw limits and direction semantics.",
            "- If future live revalidation changes the saved calibration, update this doc from the same calibration file and revalidation artifact.",
            "",
            "## Per-Joint Live Limits",
            "",
            "| Joint | Raw Min | Neutral | Raw Max | Neutral→Low (cts/deg) | Neutral→High (cts/deg) | Total Span (cts/deg) |",
            "|---|---:|---:|---:|---:|---:|---:|",
            *joint_rows,
            "",
            "## Family Practical Summary",
            "",
            "| Family | Low Direction | High Direction | Low Side (cts/deg) | High Side (cts/deg) | Total Span (cts/deg) |",
            "|---|---|---|---:|---:|---:|",
            *family_rows,
            "",
            "## Direction Semantics",
            "",
            *joint_directions,
            "",
            "## Neck Pair Coupling",
            "",
            "- `head_pitch_pair_a` raw `+` with `head_pitch_pair_b` raw `-` = head up.",
            "- `head_pitch_pair_a` raw `-` with `head_pitch_pair_b` raw `+` = head down.",
            "- `head_pitch_pair_a` raw `+` alone = tilt right.",
            "- `head_pitch_pair_b` raw `-` alone = tilt left.",
            "- The neck-pair neutral should stay near a level center. If either pitch servo becomes suspicious in `usable-range`, recenter the pair before trusting any bold pitch demo.",
            "",
            "## Validation Method",
            "",
            "- Live revalidation is bench-only and operator-confirmed.",
            "- The workflow starts from a saved non-template live calibration and an active arm lease.",
            "- The neck pair is first recentered to a level neutral and saved from live readback.",
            "- Each joint family is then stepped outward with real dwell and readback until the first failing condition, and the last confirmed passing readback becomes the practical saved limit.",
            "- Failing conditions include serial instability, servo error bits, repeated abnormal load, non-convergence, or operator abort on visible strain.",
            "",
            "## Caveats",
            "",
            "- These values are for this assembled head and its saved live calibration, not a universal hardware template.",
            "- The checked-in doc is the human-facing numeric truth; the live calibration file is the executable truth.",
            "- The `neck_tilt` family row above is derived from the current saved neck-pair bounds. Isolated live tilt on this head is narrower than that geometric summary; use the latest family-by-family revalidation findings before treating `neck_tilt` as a bold demo envelope.",
            "- This document mirrors the saved live calibration snapshot. If a fresh family-by-family revalidation session stops early, keep the generated artifacts with the saved file before treating every limit as fully revalidated.",
            "- If the body is absent or live transport is unavailable, the rest of Blink-AI remains usable through bodyless or virtual-body paths.",
            "",
        ]
    )


def write_revalidation_artifacts(
    *,
    output_dir: str | Path,
    session_payload: dict[str, object],
    profile: HeadProfile,
    calibration: HeadCalibrationRecord,
) -> dict[str, str]:
    root = Path(output_dir)
    root.mkdir(parents=True, exist_ok=True)
    summary_path = root / "session_summary.json"
    summary_path.write_text(json.dumps(session_payload, indent=2, default=str) + "\n", encoding="utf-8")
    doc_preview = render_live_limits_markdown(
        profile=profile,
        calibration=calibration,
        artifact_dir=str(root),
    )
    doc_path = root / "robot_head_live_limits.preview.md"
    doc_path.write_text(doc_preview, encoding="utf-8")
    return {
        "session_summary": str(summary_path),
        "doc_preview": str(doc_path),
    }


def _run_probe(
    *,
    profile: HeadProfile,
    calibration: HeadCalibrationRecord,
    transport,
    bridge,
    probe: RevalidationProbe,
    report_dir: str | Path,
    allow_widen_beyond_profile: bool,
) -> dict[str, object]:
    _reset_probe_joints_to_neutral(
        profile=profile,
        calibration=calibration,
        transport=transport,
        bridge=bridge,
        probe=probe,
        report_dir=report_dir,
    )
    limit_overrides = _union_limit_overrides(
        profile=profile,
        calibration=calibration,
        joint_names={joint_name for joint_name, _sign in probe.joint_signs},
        extension_counts=probe.max_extension_counts if allow_widen_beyond_profile else 0,
    )
    passing_steps: list[dict[str, object]] = []
    previous_readback: dict[str, int] | None = None
    previous_requested: dict[str, int] | None = None
    consecutive_abnormal_load = 0
    stop_reason = "search_bound_reached"

    for step_index in range(1, 128):
        requested_targets = _requested_targets_for_step(
            calibration=calibration,
            probe=probe,
            step_index=step_index,
            limit_overrides=limit_overrides,
        )
        if previous_requested is not None and requested_targets == previous_requested:
            break
        report = execute_bench_command(
            transport=transport,
            bridge=bridge,
            profile=profile,
            calibration=calibration,
            command_family="range_revalidation",
            requested_targets=dict(requested_targets),
            resolved_targets=dict(requested_targets),
            duration_ms=probe.duration_ms,
            limit_overrides=limit_overrides,
            report_dir=report_dir,
            author=f"range_revalidation:{probe.probe_name}:step:{step_index}",
        )
        time.sleep(max(0, probe.dwell_ms) / 1000.0)
        snapshot = read_bench_snapshot(
            transport,
            _servo_ids_for_joints(
                profile=profile,
                joint_names={joint_name for joint_name, _sign in probe.joint_signs},
            ),
        )
        readback = _snapshot_readback_by_joint(
            profile=profile,
            snapshot=snapshot,
            joint_names={joint_name for joint_name, _sign in probe.joint_signs},
        )
        analysis = _analyze_probe_step(
            profile=profile,
            probe=probe,
            requested_targets=requested_targets,
            readback=readback,
            snapshot=snapshot,
            previous_readback=previous_readback,
            convergence_tolerance=max(12, probe.step_counts // 2),
            load_threshold=probe.load_threshold,
            report=report,
        )
        step_payload = {
            "step_index": step_index,
            "requested_targets": requested_targets,
            "live_readback": readback,
            "report_path": report["report_path"],
            "success": analysis["success"],
            "stop_reason": analysis["stop_reason"],
            "notes": analysis["notes"],
            "load_magnitude_by_joint": analysis["load_magnitude_by_joint"],
        }
        if analysis["success"]:
            passing_steps.append(step_payload)
            previous_readback = dict(readback)
            previous_requested = dict(requested_targets)
            consecutive_abnormal_load = 0 if not analysis["abnormal_load"] else consecutive_abnormal_load + 1
            if consecutive_abnormal_load >= 3:
                stop_reason = "repeated_abnormal_load"
                break
            continue
        stop_reason = str(analysis["stop_reason"] or "probe_failed")
        break

    if not passing_steps:
        raise ServoTransportError(
            "revalidation_failed",
            f"{probe.probe_name}_no_passing_step:{stop_reason}",
        )

    confirmed_payload = None
    confirmation_notes: list[str] = []
    for candidate in reversed(passing_steps):
        report = execute_bench_command(
            transport=transport,
            bridge=bridge,
            profile=profile,
            calibration=calibration,
            command_family="range_revalidation",
            requested_targets=dict(candidate["live_readback"]),
            resolved_targets=dict(candidate["live_readback"]),
            duration_ms=probe.duration_ms,
            limit_overrides=limit_overrides,
            report_dir=report_dir,
            author=f"range_revalidation:{probe.probe_name}:confirm:{candidate['step_index']}",
        )
        time.sleep(max(0, probe.dwell_ms) / 1000.0)
        snapshot = read_bench_snapshot(
            transport,
            _servo_ids_for_joints(
                profile=profile,
                joint_names={joint_name for joint_name, _sign in probe.joint_signs},
            ),
        )
        readback = _snapshot_readback_by_joint(
            profile=profile,
            snapshot=snapshot,
            joint_names={joint_name for joint_name, _sign in probe.joint_signs},
        )
        analysis = _analyze_probe_step(
            profile=profile,
            probe=probe,
            requested_targets=dict(candidate["live_readback"]),
            readback=readback,
            snapshot=snapshot,
            previous_readback=None,
            convergence_tolerance=max(8, probe.step_counts // 3),
            load_threshold=probe.load_threshold,
            report=report,
            confirmation=True,
        )
        if analysis["success"]:
            confirmed_payload = {
                "step_index": candidate["step_index"],
                "requested_targets": dict(candidate["live_readback"]),
                "confirmed_targets": readback,
                "report_path": report["report_path"],
                "notes": analysis["notes"],
            }
            break
        confirmation_notes.extend(analysis["notes"])

    if confirmed_payload is None:
        raise ServoTransportError(
            "revalidation_failed",
            f"{probe.probe_name}_confirmation_failed:{';'.join(confirmation_notes)}",
        )

    widened = {}
    for joint_name, side in probe.limit_sides:
        joint = _profile_joint(profile, joint_name)
        value = int(confirmed_payload["confirmed_targets"][joint_name])
        if side == "low":
            widened[joint_name] = value < int(joint.raw_min)
        else:
            widened[joint_name] = value > int(joint.raw_max)

    return {
        "probe_name": probe.probe_name,
        "family_name": probe.family_name,
        "direction_label": probe.direction_label,
        "limit_sides": list(probe.limit_sides),
        "step_counts": probe.step_counts,
        "max_extension_counts": probe.max_extension_counts,
        "duration_ms": probe.duration_ms,
        "dwell_ms": probe.dwell_ms,
        "step_results": passing_steps,
        "chosen_last_passing_limit": dict(passing_steps[-1]["live_readback"]),
        "confirmed_targets": dict(confirmed_payload["confirmed_targets"]),
        "confirmation_report_path": confirmed_payload["report_path"],
        "stop_reason": stop_reason,
        "widened_beyond_profile": widened,
    }


def _reset_probe_joints_to_neutral(
    *,
    profile: HeadProfile,
    calibration: HeadCalibrationRecord,
    transport,
    bridge,
    probe: RevalidationProbe,
    report_dir: str | Path,
) -> dict[str, object]:
    is_neck_pair_probe = any(joint_name.startswith("head_pitch_pair_") for joint_name, _sign in probe.joint_signs)
    neutral_targets = {
        joint_name: int(_record_by_joint(calibration, joint_name).neutral)
        for joint_name, _sign in probe.joint_signs
    }
    limit_overrides = _union_limit_overrides(
        profile=profile,
        calibration=calibration,
        joint_names=set(neutral_targets),
        extension_counts=0,
    )
    current_positions: dict[str, int] = {}
    max_distance = 0
    for joint_name, target in neutral_targets.items():
        joint = _profile_joint(profile, joint_name)
        servo_id = int(joint.servo_ids[0])
        current = transport.read_position(servo_id)
        current_positions[joint_name] = int(current)
        max_distance = max(max_distance, abs(int(target) - int(current)))
    reset_step_counts = max(20, int(probe.step_counts)) if is_neck_pair_probe else max(40, int(probe.step_counts) * 2)
    readback = dict(current_positions)
    last_report_path: str | None = None
    for reset_index in range(1, 33):
        requested_targets = {}
        for joint_name, target in neutral_targets.items():
            current = int(readback.get(joint_name, current_positions[joint_name]))
            delta = int(target) - current
            if abs(delta) <= 16:
                requested_targets[joint_name] = int(target)
            else:
                step = max(-reset_step_counts, min(reset_step_counts, delta))
                requested_targets[joint_name] = int(current + step)
        duration_scale = 4 if is_neck_pair_probe else 3
        minimum_duration = 900 if is_neck_pair_probe else 600
        duration_ms = max(
            minimum_duration,
            min(
                2200 if is_neck_pair_probe else 1800,
                500
                + max(
                    abs(int(requested_targets[name]) - int(readback.get(name, current_positions[name])))
                    for name in requested_targets
                )
                * duration_scale,
            ),
        )
        report = execute_bench_command(
            transport=transport,
            bridge=bridge,
            profile=profile,
            calibration=calibration,
            command_family="range_revalidation",
            requested_targets=dict(requested_targets),
            resolved_targets=dict(requested_targets),
            duration_ms=duration_ms,
            limit_overrides=limit_overrides,
            report_dir=report_dir,
            author=f"range_revalidation:{probe.probe_name}:reset_neutral:{reset_index}",
        )
        last_report_path = report["report_path"]
        settle_padding_ms = 450 if is_neck_pair_probe else 250
        time.sleep(max(0.35 if is_neck_pair_probe else 0.25, (duration_ms + settle_padding_ms) / 1000.0))
        snapshot = read_bench_snapshot(
            transport,
            _servo_ids_for_joints(
                profile=profile,
                joint_names={joint_name for joint_name, _sign in probe.joint_signs},
            ),
        )
        previous_readback = dict(readback)
        readback = _snapshot_readback_by_joint(
            profile=profile,
            snapshot=snapshot,
            joint_names={joint_name for joint_name, _sign in probe.joint_signs},
        )
        if all(abs(int(readback.get(joint_name, 10**9)) - int(target)) <= 16 for joint_name, target in neutral_targets.items()):
            break
        progressed = any(
            abs(int(readback.get(joint_name, previous_readback[joint_name])) - int(previous_readback[joint_name])) >= 4
            for joint_name in neutral_targets
        )
        if not progressed:
            raise ServoTransportError(
                "revalidation_failed",
                f"{probe.probe_name}_neutral_reset_stall",
            )
    for joint_name, target in neutral_targets.items():
        actual = readback.get(joint_name)
        if actual is None:
            raise ServoTransportError(
                "revalidation_failed",
                f"{probe.probe_name}_neutral_reset_missing_readback:{joint_name}",
            )
        if abs(int(actual) - int(target)) > 16:
            raise ServoTransportError(
                "revalidation_failed",
                f"{probe.probe_name}_neutral_reset_non_convergence:{joint_name}:{target}->{actual}",
            )
    return {
        "requested_targets": neutral_targets,
        "readback": readback,
        "duration_ms": duration_ms,
        "report_path": last_report_path,
    }


def _analyze_probe_step(
    *,
    profile: HeadProfile,
    probe: RevalidationProbe,
    requested_targets: dict[str, int],
    readback: dict[str, int],
    snapshot: dict[str, dict[int, dict[str, Any]]],
    previous_readback: dict[str, int] | None,
    convergence_tolerance: int,
    load_threshold: int,
    report: dict[str, object],
    confirmation: bool = False,
) -> dict[str, object]:
    notes: list[str] = []
    if not report.get("success", False):
        return {
            "success": False,
            "stop_reason": report.get("failure_reason") or "motion_report_failed",
            "notes": [str(note) for note in (report.get("stop_notes") or [])],
            "load_magnitude_by_joint": {},
            "abnormal_load": False,
        }

    load_magnitudes: dict[str, int] = {}
    for joint_name, requested in requested_targets.items():
        if joint_name not in readback:
            return {
                "success": False,
                "stop_reason": f"missing_readback:{joint_name}",
                "notes": notes,
                "load_magnitude_by_joint": load_magnitudes,
                "abnormal_load": False,
            }
        if abs(int(readback[joint_name]) - int(requested)) > convergence_tolerance:
            return {
                "success": False,
                "stop_reason": f"non_convergence:{joint_name}:{requested}->{readback[joint_name]}",
                "notes": notes,
                "load_magnitude_by_joint": load_magnitudes,
                "abnormal_load": False,
            }
        if previous_readback is not None:
            previous = int(previous_readback.get(joint_name, requested))
            if abs(int(readback[joint_name]) - previous) <= 3 and abs(int(requested) - previous) >= max(8, probe.step_counts // 2):
                return {
                    "success": False,
                    "stop_reason": f"readback_stall:{joint_name}",
                    "notes": notes,
                    "load_magnitude_by_joint": load_magnitudes,
                    "abnormal_load": False,
                }

    abnormal_load = False
    for payload in snapshot["health"].values():
        if "error" in payload:
            return {
                "success": False,
                "stop_reason": f"health_error:{payload['error']}",
                "notes": notes,
                "load_magnitude_by_joint": load_magnitudes,
                "abnormal_load": False,
            }
    for joint_name, payload in _health_by_joint(
        profile=profile,
        snapshot=snapshot,
        requested_joints=set(requested_targets),
    ).items():
        error_bits = list(payload.get("error_bits") or [])
        if error_bits:
            return {
                "success": False,
                "stop_reason": f"servo_error:{joint_name}:{','.join(error_bits)}",
                "notes": notes,
                "load_magnitude_by_joint": load_magnitudes,
                "abnormal_load": False,
            }
        load_magnitude = int(payload.get("load", 0)) & 0x3FF
        load_magnitudes[joint_name] = load_magnitude
        if load_magnitude >= load_threshold and not confirmation:
            abnormal_load = True
    if abnormal_load:
        notes.append("abnormal_load_detected")
    return {
        "success": True,
        "stop_reason": None,
        "notes": notes,
        "load_magnitude_by_joint": load_magnitudes,
        "abnormal_load": abnormal_load,
    }


def _requested_targets_for_step(
    *,
    calibration: HeadCalibrationRecord,
    probe: RevalidationProbe,
    step_index: int,
    limit_overrides: dict[str, tuple[int, int]],
) -> dict[str, int]:
    requested: dict[str, int] = {}
    for joint_name, sign in probe.joint_signs:
        record = _record_by_joint(calibration, joint_name)
        low, high = limit_overrides[joint_name]
        target = int(record.neutral) + int(sign) * int(probe.step_counts) * int(step_index)
        requested[joint_name] = max(low, min(high, target))
    return requested


def _union_limit_overrides(
    *,
    profile: HeadProfile,
    calibration: HeadCalibrationRecord,
    joint_names: set[str],
    extension_counts: int,
) -> dict[str, tuple[int, int]]:
    overrides: dict[str, tuple[int, int]] = {}
    for joint_name in joint_names:
        record = _record_by_joint(calibration, joint_name)
        joint = _profile_joint(profile, joint_name)
        baseline_low = min(int(record.raw_min), int(joint.raw_min))
        baseline_high = max(int(record.raw_max), int(joint.raw_max))
        low = max(SERVO_RAW_MIN, baseline_low - int(extension_counts))
        high = min(SERVO_RAW_MAX, baseline_high + int(extension_counts))
        overrides[joint_name] = (low, high)
    return overrides


def _widened_beyond_profile(
    *,
    profile: HeadProfile,
    side_overrides: dict[str, dict[str, int]],
) -> dict[str, bool]:
    widened: dict[str, bool] = {}
    for joint_name, overrides in side_overrides.items():
        joint = _profile_joint(profile, joint_name)
        widened[joint_name] = bool(
            ("low" in overrides and int(overrides["low"]) < int(joint.raw_min))
            or ("high" in overrides and int(overrides["high"]) > int(joint.raw_max))
        )
    return widened


def _snapshot_readback_by_joint(
    *,
    profile: HeadProfile,
    snapshot: dict[str, dict[int, dict[str, Any]]],
    joint_names: set[str],
) -> dict[str, int]:
    readback: dict[str, int] = {}
    joint_to_servo = {joint.joint_name: int(joint.servo_ids[0]) for joint in profile.joints if joint.enabled and joint.servo_ids}
    for joint_name in joint_names:
        servo_id = joint_to_servo[joint_name]
        payload = snapshot["positions"].get(servo_id) or snapshot["positions"].get(str(servo_id))
        if payload and "position" in payload:
            readback[joint_name] = int(payload["position"])
    return readback


def _health_by_joint(
    *,
    profile: HeadProfile,
    snapshot: dict[str, dict[int, dict[str, Any]]],
    requested_joints: set[str],
) -> dict[str, dict[str, Any]]:
    servo_to_joint = {
        int(joint.servo_ids[0]): joint.joint_name
        for joint in profile.joints
        if joint.enabled and joint.servo_ids
    }
    result: dict[str, dict[str, Any]] = {}
    for servo_key, payload in snapshot["health"].items():
        try:
            servo_id = int(servo_key)
        except (TypeError, ValueError):
            continue
        joint_name = servo_to_joint.get(servo_id)
        if joint_name in requested_joints:
            result[joint_name] = payload
    return result


def _servo_ids_for_joints(*, profile: HeadProfile, joint_names: set[str]) -> list[int]:
    servo_ids: list[int] = []
    for joint in profile.joints:
        if joint.enabled and joint.joint_name in joint_names:
            servo_ids.extend(int(servo_id) for servo_id in joint.servo_ids)
    return sorted(set(servo_ids))


def _record_by_joint(calibration: HeadCalibrationRecord, joint_name: str):
    for record in calibration.joint_records:
        if record.joint_name == joint_name:
            return record
    raise ServoTransportError("out_of_range", f"unknown_joint:{joint_name}")


def _profile_joint(profile: HeadProfile, joint_name: str):
    for joint in profile.joints:
        if joint.joint_name == joint_name:
            return joint
    raise ServoTransportError("out_of_range", f"unknown_joint:{joint_name}")


def _degrees(counts: int) -> float:
    return float(counts) * COUNT_TO_DEGREES


def _joint_direction_notes() -> list[str]:
    return [
        "- `head_yaw`: raw `+` = right, raw `-` = left.",
        "- `eye_yaw`: raw `+` = eyes right, raw `-` = eyes left.",
        "- `eye_pitch`: raw `+` = eyes up, raw `-` = eyes down.",
        "- `upper_lid_left`: raw `+` = open, raw `-` = close.",
        "- `upper_lid_right`: raw `+` = close, raw `-` = open.",
        "- `lower_lid_left`: raw `+` = close, raw `-` = open.",
        "- `lower_lid_right`: raw `+` = open, raw `-` = close.",
        "- `brow_left`: raw `+` = raise, raw `-` = lower.",
        "- `brow_right`: raw `+` = lower, raw `-` = raise.",
    ]


def _family_summary_rows(
    *,
    profile: HeadProfile,
    calibration: HeadCalibrationRecord,
) -> list[dict[str, object]]:
    records = {record.joint_name: record for record in calibration.joint_records}
    head_yaw = records["head_yaw"]
    eye_yaw = records["eye_yaw"]
    eye_pitch = records["eye_pitch"]
    upper_left = records["upper_lid_left"]
    upper_right = records["upper_lid_right"]
    lower_left = records["lower_lid_left"]
    lower_right = records["lower_lid_right"]
    brow_left = records["brow_left"]
    brow_right = records["brow_right"]
    pitch_a = records["head_pitch_pair_a"]
    pitch_b = records["head_pitch_pair_b"]

    pitch_up = min(int(pitch_a.raw_max) - int(pitch_a.neutral), int(pitch_b.neutral) - int(pitch_b.raw_min))
    pitch_down = min(int(pitch_a.neutral) - int(pitch_a.raw_min), int(pitch_b.raw_max) - int(pitch_b.neutral))
    tilt_right = int(pitch_a.raw_max) - int(pitch_a.neutral)
    tilt_left = int(pitch_b.neutral) - int(pitch_b.raw_min)

    def row(family_name: str, direction_low: str, direction_high: str, counts_low: int, counts_high: int) -> dict[str, object]:
        return {
            "family_name": family_name,
            "direction_low": direction_low,
            "direction_high": direction_high,
            "counts_low": counts_low,
            "degrees_low": _degrees(counts_low),
            "counts_high": counts_high,
            "degrees_high": _degrees(counts_high),
            "span_counts": counts_low + counts_high,
            "span_degrees": _degrees(counts_low + counts_high),
        }

    return [
        row("head_yaw", "left", "right", int(head_yaw.neutral) - int(head_yaw.raw_min), int(head_yaw.raw_max) - int(head_yaw.neutral)),
        row("neck_pitch", "down", "up", pitch_down, pitch_up),
        row("neck_tilt", "left", "right", tilt_left, tilt_right),
        row("eye_yaw", "left", "right", int(eye_yaw.neutral) - int(eye_yaw.raw_min), int(eye_yaw.raw_max) - int(eye_yaw.neutral)),
        row("eye_pitch", "down", "up", int(eye_pitch.neutral) - int(eye_pitch.raw_min), int(eye_pitch.raw_max) - int(eye_pitch.neutral)),
        row(
            "upper_lids",
            "close",
            "open",
            min(int(upper_left.neutral) - int(upper_left.raw_min), int(upper_right.raw_max) - int(upper_right.neutral)),
            min(int(upper_left.raw_max) - int(upper_left.neutral), int(upper_right.neutral) - int(upper_right.raw_min)),
        ),
        row(
            "lower_lids",
            "close",
            "open",
            min(int(lower_left.raw_max) - int(lower_left.neutral), int(lower_right.neutral) - int(lower_right.raw_min)),
            min(int(lower_left.neutral) - int(lower_left.raw_min), int(lower_right.raw_max) - int(lower_right.neutral)),
        ),
        row(
            "brows",
            "lower",
            "raise",
            min(int(brow_left.neutral) - int(brow_left.raw_min), int(brow_right.raw_max) - int(brow_right.neutral)),
            min(int(brow_left.raw_max) - int(brow_left.neutral), int(brow_right.neutral) - int(brow_right.raw_min)),
        ),
    ]


_PROBES: tuple[RevalidationProbe, ...] = (
    RevalidationProbe(
        probe_name="head_yaw_left",
        family_name="head_yaw",
        direction_label="left",
        joint_signs=(("head_yaw", -1),),
        limit_sides=(("head_yaw", "low"),),
        step_counts=20,
        max_extension_counts=420,
        duration_ms=1600,
        dwell_ms=2200,
        load_threshold=260,
    ),
    RevalidationProbe(
        probe_name="head_yaw_right",
        family_name="head_yaw",
        direction_label="right",
        joint_signs=(("head_yaw", 1),),
        limit_sides=(("head_yaw", "high"),),
        step_counts=20,
        max_extension_counts=420,
        duration_ms=1600,
        dwell_ms=2200,
        load_threshold=260,
    ),
    RevalidationProbe(
        probe_name="neck_pitch_down",
        family_name="neck_pitch",
        direction_label="down",
        joint_signs=(("head_pitch_pair_a", -1), ("head_pitch_pair_b", 1)),
        limit_sides=(("head_pitch_pair_a", "low"), ("head_pitch_pair_b", "high")),
        step_counts=30,
        max_extension_counts=220,
        duration_ms=720,
        dwell_ms=320,
        load_threshold=280,
    ),
    RevalidationProbe(
        probe_name="neck_pitch_up",
        family_name="neck_pitch",
        direction_label="up",
        joint_signs=(("head_pitch_pair_a", 1), ("head_pitch_pair_b", -1)),
        limit_sides=(("head_pitch_pair_a", "high"), ("head_pitch_pair_b", "low")),
        step_counts=30,
        max_extension_counts=220,
        duration_ms=720,
        dwell_ms=320,
        load_threshold=280,
    ),
    RevalidationProbe(
        probe_name="neck_tilt_left",
        family_name="neck_tilt",
        direction_label="left",
        joint_signs=(("head_pitch_pair_b", -1),),
        limit_sides=(("head_pitch_pair_b", "low"),),
        step_counts=30,
        max_extension_counts=180,
        duration_ms=720,
        dwell_ms=320,
        load_threshold=260,
    ),
    RevalidationProbe(
        probe_name="neck_tilt_right",
        family_name="neck_tilt",
        direction_label="right",
        joint_signs=(("head_pitch_pair_a", 1),),
        limit_sides=(("head_pitch_pair_a", "high"),),
        step_counts=30,
        max_extension_counts=180,
        duration_ms=720,
        dwell_ms=320,
        load_threshold=260,
    ),
    RevalidationProbe(
        probe_name="eye_yaw_left",
        family_name="eye_yaw",
        direction_label="left",
        joint_signs=(("eye_yaw", -1),),
        limit_sides=(("eye_yaw", "low"),),
        step_counts=30,
        max_extension_counts=120,
        duration_ms=520,
        dwell_ms=220,
        load_threshold=220,
    ),
    RevalidationProbe(
        probe_name="eye_yaw_right",
        family_name="eye_yaw",
        direction_label="right",
        joint_signs=(("eye_yaw", 1),),
        limit_sides=(("eye_yaw", "high"),),
        step_counts=30,
        max_extension_counts=120,
        duration_ms=520,
        dwell_ms=220,
        load_threshold=220,
    ),
    RevalidationProbe(
        probe_name="eye_pitch_down",
        family_name="eye_pitch",
        direction_label="down",
        joint_signs=(("eye_pitch", -1),),
        limit_sides=(("eye_pitch", "low"),),
        step_counts=30,
        max_extension_counts=160,
        duration_ms=520,
        dwell_ms=220,
        load_threshold=220,
    ),
    RevalidationProbe(
        probe_name="eye_pitch_up",
        family_name="eye_pitch",
        direction_label="up",
        joint_signs=(("eye_pitch", 1),),
        limit_sides=(("eye_pitch", "high"),),
        step_counts=30,
        max_extension_counts=160,
        duration_ms=520,
        dwell_ms=220,
        load_threshold=220,
    ),
    RevalidationProbe(
        probe_name="upper_lid_left_close",
        family_name="upper_lids",
        direction_label="upper_lid_left_close",
        joint_signs=(("upper_lid_left", -1),),
        limit_sides=(("upper_lid_left", "low"),),
        step_counts=20,
        max_extension_counts=120,
        duration_ms=420,
        dwell_ms=180,
        load_threshold=180,
    ),
    RevalidationProbe(
        probe_name="upper_lid_left_open",
        family_name="upper_lids",
        direction_label="upper_lid_left_open",
        joint_signs=(("upper_lid_left", 1),),
        limit_sides=(("upper_lid_left", "high"),),
        step_counts=20,
        max_extension_counts=120,
        duration_ms=420,
        dwell_ms=180,
        load_threshold=180,
    ),
    RevalidationProbe(
        probe_name="upper_lid_right_open",
        family_name="upper_lids",
        direction_label="upper_lid_right_open",
        joint_signs=(("upper_lid_right", -1),),
        limit_sides=(("upper_lid_right", "low"),),
        step_counts=20,
        max_extension_counts=120,
        duration_ms=420,
        dwell_ms=180,
        load_threshold=180,
    ),
    RevalidationProbe(
        probe_name="upper_lid_right_close",
        family_name="upper_lids",
        direction_label="upper_lid_right_close",
        joint_signs=(("upper_lid_right", 1),),
        limit_sides=(("upper_lid_right", "high"),),
        step_counts=20,
        max_extension_counts=120,
        duration_ms=420,
        dwell_ms=180,
        load_threshold=180,
    ),
    RevalidationProbe(
        probe_name="lower_lid_left_open",
        family_name="lower_lids",
        direction_label="lower_lid_left_open",
        joint_signs=(("lower_lid_left", -1),),
        limit_sides=(("lower_lid_left", "low"),),
        step_counts=16,
        max_extension_counts=100,
        duration_ms=420,
        dwell_ms=180,
        load_threshold=170,
    ),
    RevalidationProbe(
        probe_name="lower_lid_left_close",
        family_name="lower_lids",
        direction_label="lower_lid_left_close",
        joint_signs=(("lower_lid_left", 1),),
        limit_sides=(("lower_lid_left", "high"),),
        step_counts=16,
        max_extension_counts=100,
        duration_ms=420,
        dwell_ms=180,
        load_threshold=170,
    ),
    RevalidationProbe(
        probe_name="lower_lid_right_close",
        family_name="lower_lids",
        direction_label="lower_lid_right_close",
        joint_signs=(("lower_lid_right", -1),),
        limit_sides=(("lower_lid_right", "low"),),
        step_counts=16,
        max_extension_counts=100,
        duration_ms=420,
        dwell_ms=180,
        load_threshold=170,
    ),
    RevalidationProbe(
        probe_name="lower_lid_right_open",
        family_name="lower_lids",
        direction_label="lower_lid_right_open",
        joint_signs=(("lower_lid_right", 1),),
        limit_sides=(("lower_lid_right", "high"),),
        step_counts=16,
        max_extension_counts=100,
        duration_ms=420,
        dwell_ms=180,
        load_threshold=170,
    ),
    RevalidationProbe(
        probe_name="brow_left_lower",
        family_name="brows",
        direction_label="brow_left_lower",
        joint_signs=(("brow_left", -1),),
        limit_sides=(("brow_left", "low"),),
        step_counts=12,
        max_extension_counts=80,
        duration_ms=380,
        dwell_ms=160,
        load_threshold=160,
    ),
    RevalidationProbe(
        probe_name="brow_left_raise",
        family_name="brows",
        direction_label="brow_left_raise",
        joint_signs=(("brow_left", 1),),
        limit_sides=(("brow_left", "high"),),
        step_counts=12,
        max_extension_counts=80,
        duration_ms=380,
        dwell_ms=160,
        load_threshold=160,
    ),
    RevalidationProbe(
        probe_name="brow_right_raise",
        family_name="brows",
        direction_label="brow_right_raise",
        joint_signs=(("brow_right", -1),),
        limit_sides=(("brow_right", "low"),),
        step_counts=12,
        max_extension_counts=80,
        duration_ms=380,
        dwell_ms=160,
        load_threshold=160,
    ),
    RevalidationProbe(
        probe_name="brow_right_lower",
        family_name="brows",
        direction_label="brow_right_lower",
        joint_signs=(("brow_right", 1),),
        limit_sides=(("brow_right", "high"),),
        step_counts=12,
        max_extension_counts=80,
        duration_ms=380,
        dwell_ms=160,
        load_threshold=160,
    ),
)

_FAMILY_ORDER = (
    "head_yaw",
    "neck_pitch",
    "neck_tilt",
    "eye_yaw",
    "eye_pitch",
    "upper_lids",
    "lower_lids",
    "brows",
)

_PROBES_BY_FAMILY = {
    family_name: [probe for probe in _PROBES if probe.family_name == family_name]
    for family_name in _FAMILY_ORDER
}
