from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable, Sequence

from embodied_stack.shared.contracts._common import BaseModel, Field, datetime, utc_now, uuid4
from embodied_stack.shared.contracts.body import BodyState, HeadProfile

DEFAULT_BENCH_SUITE_DIR = Path("runtime/serial/bench_suites")


class SerialFailureEventRecord(BaseModel):
    source: str
    step_name: str | None = None
    reason_code: str | None = None
    detail: str | None = None
    report_path: str | None = None


class SerialFailureSummaryRecord(BaseModel):
    status: str = "ok"
    stop_step: str | None = None
    failed_steps: list[str] = Field(default_factory=list)
    degraded_steps: list[str] = Field(default_factory=list)
    reason_codes: list[str] = Field(default_factory=list)
    current_transport_reason_code: str | None = None
    current_transport_error: str | None = None
    events: list[SerialFailureEventRecord] = Field(default_factory=list)


class SerialBenchMetricSummary(BaseModel):
    responsive_id_count: int = 0
    clamp_count: int = 0
    degraded_count: int = 0
    request_count: int = 0
    readback_drift_by_joint: dict[str, int] = Field(default_factory=dict)
    max_abs_readback_drift: int = 0


class SerialBenchStepRecord(BaseModel):
    step_name: str
    status: str
    started_at: datetime
    completed_at: datetime
    latency_ms: float = 0.0
    success: bool = False
    report_path: str | None = None
    reason_code: str | None = None
    detail: str | None = None


class SerialBenchSuiteRecord(BaseModel):
    suite_id: str = Field(default_factory=lambda: str(uuid4()))
    schema_version: str = "blink_serial_bench_suite/v1"
    transport_mode: str
    started_at: datetime = Field(default_factory=utc_now)
    completed_at: datetime | None = None
    machine: dict[str, object] = Field(default_factory=dict)
    profile_path: str
    calibration_path: str
    port: str | None = None
    baud_rate: int
    timeout_seconds: float
    command_order: list[str] = Field(default_factory=list)
    steps: list[SerialBenchStepRecord] = Field(default_factory=list)
    metrics: SerialBenchMetricSummary = Field(default_factory=SerialBenchMetricSummary)
    failure_summary: SerialFailureSummaryRecord = Field(default_factory=SerialFailureSummaryRecord)
    artifact_files: dict[str, str] = Field(default_factory=dict)


def load_json_artifact(path: str | Path) -> dict[str, object] | None:
    resolved = Path(path)
    if not resolved.exists():
        return None
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def normalize_request_response_history(
    history: Sequence[dict[str, object]] | None,
    *,
    source: str,
    step_name: str | None = None,
    report_path: str | None = None,
) -> list[dict[str, object]]:
    normalized: list[dict[str, object]] = []
    for index, item in enumerate(history or [], start=1):
        normalized.append(
            {
                "source": source,
                "step_name": step_name,
                "report_path": report_path,
                "sequence": index,
                "operation": item.get("operation"),
                "request_hex": item.get("request_hex"),
                "response_hex": list(item.get("response_hex") or []),
                "ok": bool(item.get("ok", False)),
                "reason_code": item.get("reason_code"),
                "error": item.get("error"),
            }
        )
    return normalized


def collect_request_response_history(
    *,
    named_histories: Sequence[tuple[str, Sequence[dict[str, object]] | None]] = (),
    motion_reports: Sequence[dict[str, object]] = (),
    current_history: Sequence[dict[str, object]] | None = None,
) -> list[dict[str, object]]:
    combined: list[dict[str, object]] = []
    for source, history in named_histories:
        combined.extend(normalize_request_response_history(history, source=source, step_name=source))
    for report in motion_reports:
        source = str(report.get("command_family") or "motion_report")
        combined.extend(
            normalize_request_response_history(
                report.get("request_response_history"),
                source=source,
                step_name=source,
                report_path=str(report.get("report_path")) if report.get("report_path") else None,
            )
        )
    combined.extend(normalize_request_response_history(current_history, source="runtime_transport", step_name="runtime_transport"))
    return combined


def load_motion_reports(paths: Iterable[str | Path]) -> list[dict[str, object]]:
    reports: list[dict[str, object]] = []
    for path in paths:
        if payload := load_json_artifact(path):
            payload["report_path"] = str(path)
            reports.append(payload)
    return reports


def build_motion_report_index(paths: Iterable[str | Path]) -> list[dict[str, object]]:
    index: list[dict[str, object]] = []
    for path in paths:
        resolved = Path(path)
        payload = load_json_artifact(resolved)
        index.append(
            {
                "report_path": str(resolved),
                "exists": resolved.exists(),
                "modified_at": datetime.fromtimestamp(resolved.stat().st_mtime).isoformat() if resolved.exists() else None,
                "command_family": payload.get("command_family") if payload else None,
                "generated_at": payload.get("generated_at") if payload else None,
                "success": bool(payload.get("success")) if payload else False,
                "failure_reason": payload.get("failure_reason") if payload else "missing_report",
                "request_count": len(payload.get("request_response_history") or []) if payload else 0,
            }
        )
    return index


def _servo_to_joint_map(profile: HeadProfile | None) -> dict[int, str]:
    if profile is None:
        return {}
    mapping: dict[int, str] = {}
    for joint in profile.joints:
        if not joint.enabled:
            continue
        for servo_id in joint.servo_ids:
            mapping[int(servo_id)] = joint.joint_name
    return mapping


def summarize_motion_metrics(
    *,
    motion_reports: Sequence[dict[str, object]],
    responsive_ids: Sequence[int] | None = None,
    profile: HeadProfile | None = None,
    request_history: Sequence[dict[str, object]] | None = None,
) -> SerialBenchMetricSummary:
    servo_to_joint = _servo_to_joint_map(profile)
    clamp_count = 0
    degraded_count = 0
    drift_by_joint: dict[str, int] = {}

    for report in motion_reports:
        if report.get("failure_reason") or not report.get("success", False):
            degraded_count += 1
        requested_targets = report.get("requested_targets") or {}
        clamped_targets = report.get("clamped_targets") or {}
        clamp_count += sum(1 for joint, value in requested_targets.items() if clamped_targets.get(joint) != value)
        after_health = report.get("after_health") or {}
        for servo_key, payload in after_health.items():
            if not isinstance(payload, dict):
                continue
            try:
                servo_id = int(servo_key)
            except (TypeError, ValueError):
                continue
            joint_name = servo_to_joint.get(servo_id)
            if not joint_name or joint_name not in clamped_targets:
                continue
            position = payload.get("position")
            if position is None:
                continue
            drift_by_joint[joint_name] = int(position) - int(clamped_targets[joint_name])

    max_abs_drift = max((abs(value) for value in drift_by_joint.values()), default=0)
    return SerialBenchMetricSummary(
        responsive_id_count=len(list(responsive_ids or [])),
        clamp_count=clamp_count,
        degraded_count=degraded_count,
        request_count=len(list(request_history or [])),
        readback_drift_by_joint=drift_by_joint,
        max_abs_readback_drift=max_abs_drift,
    )


def build_serial_failure_summary(
    *,
    steps: Sequence[SerialBenchStepRecord] = (),
    motion_reports: Sequence[dict[str, object]] = (),
    body_state: BodyState | dict[str, object] | None = None,
    stop_step: str | None = None,
) -> SerialFailureSummaryRecord:
    failed_steps = [item.step_name for item in steps if item.status in {"failed", "error"}]
    degraded_steps = [item.step_name for item in steps if item.status == "degraded"]
    events: list[SerialFailureEventRecord] = []

    for item in steps:
        if item.reason_code or item.detail or item.status in {"failed", "error", "degraded"}:
            events.append(
                SerialFailureEventRecord(
                    source="bench_step",
                    step_name=item.step_name,
                    reason_code=item.reason_code,
                    detail=item.detail,
                    report_path=item.report_path,
                )
            )

    for report in motion_reports:
        failure_reason = report.get("failure_reason")
        if failure_reason or not report.get("success", False):
            events.append(
                SerialFailureEventRecord(
                    source="motion_report",
                    step_name=str(report.get("command_family") or "motion_report"),
                    reason_code=str(failure_reason) if failure_reason else "degraded",
                    detail=";".join(str(item) for item in (report.get("stop_notes") or [])) or None,
                    report_path=str(report.get("report_path")) if report.get("report_path") else None,
                )
            )

    if isinstance(body_state, BodyState):
        current_transport_reason_code = body_state.transport_reason_code
        current_transport_error = body_state.transport_error
    elif isinstance(body_state, dict):
        current_transport_reason_code = str(body_state.get("transport_reason_code")) if body_state.get("transport_reason_code") else None
        current_transport_error = str(body_state.get("transport_error")) if body_state.get("transport_error") else None
    else:
        current_transport_reason_code = None
        current_transport_error = None

    if current_transport_error or (current_transport_reason_code and current_transport_reason_code != "ok"):
        events.append(
            SerialFailureEventRecord(
                source="body_state",
                step_name=None,
                reason_code=current_transport_reason_code,
                detail=current_transport_error,
            )
        )

    reason_codes = [item.reason_code for item in events if item.reason_code]
    status = "ok" if not reason_codes and not failed_steps and not degraded_steps and not current_transport_error else "degraded"
    return SerialFailureSummaryRecord(
        status=status,
        stop_step=stop_step,
        failed_steps=failed_steps,
        degraded_steps=degraded_steps,
        reason_codes=list(dict.fromkeys(reason_codes)),
        current_transport_reason_code=current_transport_reason_code,
        current_transport_error=current_transport_error,
        events=events,
    )


__all__ = [
    "DEFAULT_BENCH_SUITE_DIR",
    "SerialBenchMetricSummary",
    "SerialBenchStepRecord",
    "SerialBenchSuiteRecord",
    "SerialFailureEventRecord",
    "SerialFailureSummaryRecord",
    "build_motion_report_index",
    "build_serial_failure_summary",
    "collect_request_response_history",
    "load_json_artifact",
    "load_motion_reports",
    "normalize_request_response_history",
    "summarize_motion_metrics",
]
