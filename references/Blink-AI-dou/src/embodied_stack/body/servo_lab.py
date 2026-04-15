from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from embodied_stack.shared.contracts import BodyMotionControlAuditRecord, HeadCalibrationRecord, HeadJointProfile, HeadProfile, utc_now

_RANGE_CONFLICT_NOTE_PREFIX = "range_conflict_from_capture"


class ServoLabError(ValueError):
    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(detail)


@dataclass(frozen=True)
class ServoLabCapabilities:
    speed_override_supported: bool = True
    acceleration_supported: bool = False
    acceleration_status: str = "unsupported_on_current_transport"

    def to_payload(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class ServoLabJointCatalogItem:
    joint_name: str
    servo_ids: tuple[int, ...]
    positive_direction: str
    neutral: int
    raw_min: int
    raw_max: int
    profile_neutral: int
    profile_raw_min: int
    profile_raw_max: int
    current_position: int | None
    readback_error: str | None
    coupling_group: str
    coupling_hint: str
    mirrored_direction_confirmed: bool | None
    supports_absolute_move: bool = True
    supports_current_delta: bool = True
    supports_sweep: bool = True
    speed_override_supported: bool = True
    acceleration_supported: bool = False
    warnings: tuple[str, ...] = ()

    def to_payload(self) -> dict[str, object]:
        payload = asdict(self)
        payload["servo_ids"] = list(self.servo_ids)
        payload["warnings"] = list(self.warnings)
        return payload


@dataclass(frozen=True)
class ServoLabCatalog:
    joints: tuple[ServoLabJointCatalogItem, ...]
    capabilities: ServoLabCapabilities
    calibration_path: str | None = None
    calibration_kind: str | None = None

    def to_payload(self) -> dict[str, object]:
        return {
            "joint_count": len(self.joints),
            "joints": [item.to_payload() for item in self.joints],
            "capabilities": self.capabilities.to_payload(),
            "calibration_path": self.calibration_path,
            "calibration_kind": self.calibration_kind,
        }


@dataclass(frozen=True)
class ServoLabBounds:
    joint_name: str
    hard_min: int
    hard_max: int
    neutral: int
    lab_min: int
    lab_max: int
    clamp_notes: tuple[str, ...] = ()

    def to_payload(self) -> dict[str, object]:
        payload = asdict(self)
        payload["clamp_notes"] = list(self.clamp_notes)
        return payload


@dataclass(frozen=True)
class ServoLabMovePlan:
    joint_name: str
    reference_mode: str
    current_position: int | None
    requested_target: int
    effective_target: int
    bounds: ServoLabBounds
    clamp_notes: tuple[str, ...] = ()

    def to_payload(self) -> dict[str, object]:
        payload = asdict(self)
        payload["bounds"] = self.bounds.to_payload()
        payload["clamp_notes"] = list(self.clamp_notes)
        return payload


@dataclass(frozen=True)
class ServoLabSweepStep:
    step_id: str
    label: str
    target: int
    duration_ms: int
    dwell_ms: int

    def to_payload(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class ServoLabSweepPlan:
    joint_name: str
    current_position: int | None
    bounds: ServoLabBounds
    cycles: int
    return_to_neutral: bool
    steps: tuple[ServoLabSweepStep, ...]
    clamp_notes: tuple[str, ...] = ()

    def to_payload(self) -> dict[str, object]:
        return {
            "joint_name": self.joint_name,
            "current_position": self.current_position,
            "bounds": self.bounds.to_payload(),
            "cycles": self.cycles,
            "return_to_neutral": self.return_to_neutral,
            "steps": [item.to_payload() for item in self.steps],
            "clamp_notes": list(self.clamp_notes),
        }


@dataclass(frozen=True)
class ServoLabCalibrationUpdate:
    joint_name: str
    output_path: str
    calibration_kind: str
    save_current_as_neutral: bool
    raw_min: int
    raw_max: int
    neutral: int
    clamp_notes: tuple[str, ...] = ()

    def to_payload(self) -> dict[str, object]:
        payload = asdict(self)
        payload["clamp_notes"] = list(self.clamp_notes)
        return payload


def servo_lab_capabilities(transport: object | None) -> ServoLabCapabilities:
    acceleration_supported = bool(
        transport is not None
        and hasattr(transport, "sync_write_start_acceleration")
        and hasattr(transport, "sync_read_start_acceleration")
    )
    return ServoLabCapabilities(
        speed_override_supported=True,
        acceleration_supported=acceleration_supported,
        acceleration_status=(
            "supported_and_readback_verifiable"
            if acceleration_supported
            else "unsupported_on_current_transport"
        ),
    )


def build_servo_lab_catalog(
    *,
    profile: HeadProfile,
    calibration: HeadCalibrationRecord | None,
    current_positions: dict[str, int] | None = None,
    readback_errors: dict[str, str] | None = None,
    transport: object | None = None,
    calibration_path: str | None = None,
) -> ServoLabCatalog:
    capabilities = servo_lab_capabilities(transport)
    joints: list[ServoLabJointCatalogItem] = []
    records_by_joint = _records_by_joint(calibration)
    current_positions = current_positions or {}
    readback_errors = readback_errors or {}
    for joint in profile.joints:
        if not joint.enabled:
            continue
        record = records_by_joint.get(joint.joint_name)
        hard_min, hard_max, neutral = _hard_bounds(joint=joint, calibration_record=record)
        warnings: list[str] = []
        if calibration is None or calibration.calibration_kind == "template":
            warnings.append("using_profile_fallback")
        if readback_errors.get(joint.joint_name):
            warnings.append("readback_unavailable")
        joints.append(
            ServoLabJointCatalogItem(
                joint_name=joint.joint_name,
                servo_ids=tuple(int(servo_id) for servo_id in joint.servo_ids),
                positive_direction=str(joint.positive_direction),
                neutral=neutral,
                raw_min=hard_min,
                raw_max=hard_max,
                profile_neutral=int(joint.neutral),
                profile_raw_min=int(joint.raw_min),
                profile_raw_max=int(joint.raw_max),
                current_position=current_positions.get(joint.joint_name),
                readback_error=readback_errors.get(joint.joint_name),
                coupling_group=_coupling_group(joint.joint_name),
                coupling_hint=_coupling_hint(joint.joint_name),
                mirrored_direction_confirmed=(
                    record.mirrored_direction_confirmed if record is not None else None
                ),
                speed_override_supported=capabilities.speed_override_supported,
                acceleration_supported=capabilities.acceleration_supported,
                warnings=tuple(warnings),
            )
        )
    return ServoLabCatalog(
        joints=tuple(joints),
        capabilities=capabilities,
        calibration_path=calibration_path,
        calibration_kind=(calibration.calibration_kind if calibration is not None else None),
    )


def resolve_servo_lab_move(
    *,
    profile: HeadProfile,
    calibration: HeadCalibrationRecord | None,
    joint_name: str,
    reference_mode: str,
    target_raw: int | None,
    delta_counts: int | None,
    current_position: int | None,
    lab_min: int | None,
    lab_max: int | None,
) -> ServoLabMovePlan:
    joint, record = _joint_and_record(profile=profile, calibration=calibration, joint_name=joint_name)
    bounds = resolve_servo_lab_bounds(
        joint=joint,
        calibration_record=record,
        lab_min=lab_min,
        lab_max=lab_max,
    )
    normalized_mode = str(reference_mode).strip().lower()
    if normalized_mode == "absolute_raw":
        if target_raw is None:
            raise ServoLabError("out_of_range", f"servo_lab_target_required:{joint_name}:absolute_raw")
        requested_target = int(target_raw)
    elif normalized_mode == "neutral_delta":
        if delta_counts is None:
            raise ServoLabError("out_of_range", f"servo_lab_delta_required:{joint_name}:neutral_delta")
        requested_target = int(bounds.neutral) + int(delta_counts)
    elif normalized_mode == "current_delta":
        if current_position is None:
            raise ServoLabError("readback_required", f"servo_lab_current_position_required:{joint_name}")
        if delta_counts is None:
            raise ServoLabError("out_of_range", f"servo_lab_delta_required:{joint_name}:current_delta")
        requested_target = int(current_position) + int(delta_counts)
    else:
        raise ServoLabError("out_of_range", f"servo_lab_reference_mode_unsupported:{joint_name}:{reference_mode}")

    effective_target = requested_target
    clamp_notes = list(bounds.clamp_notes)
    if effective_target < bounds.lab_min:
        clamp_notes.append(f"lab_min_clamp:{joint_name}:{effective_target}->{bounds.lab_min}")
        effective_target = bounds.lab_min
    if effective_target > bounds.lab_max:
        clamp_notes.append(f"lab_max_clamp:{joint_name}:{effective_target}->{bounds.lab_max}")
        effective_target = bounds.lab_max

    return ServoLabMovePlan(
        joint_name=joint_name,
        reference_mode=normalized_mode,
        current_position=current_position,
        requested_target=requested_target,
        effective_target=effective_target,
        bounds=bounds,
        clamp_notes=tuple(clamp_notes),
    )


def resolve_servo_lab_sweep(
    *,
    profile: HeadProfile,
    calibration: HeadCalibrationRecord | None,
    joint_name: str,
    current_position: int | None,
    lab_min: int | None,
    lab_max: int | None,
    cycles: int,
    duration_ms: int,
    dwell_ms: int,
    return_to_neutral: bool,
) -> ServoLabSweepPlan:
    joint, record = _joint_and_record(profile=profile, calibration=calibration, joint_name=joint_name)
    bounds = resolve_servo_lab_bounds(
        joint=joint,
        calibration_record=record,
        lab_min=lab_min,
        lab_max=lab_max,
    )
    if cycles < 1:
        raise ServoLabError("out_of_range", f"servo_lab_cycles_invalid:{joint_name}:{cycles}")
    if duration_ms < 0 or dwell_ms < 0:
        raise ServoLabError("out_of_range", f"servo_lab_negative_timing:{joint_name}")
    steps: list[ServoLabSweepStep] = []
    for index in range(int(cycles)):
        cycle_number = index + 1
        steps.append(
            ServoLabSweepStep(
                step_id=f"cycle_{cycle_number}_min",
                label=f"cycle_{cycle_number}:move_to_min",
                target=bounds.lab_min,
                duration_ms=int(duration_ms),
                dwell_ms=int(dwell_ms),
            )
        )
        steps.append(
            ServoLabSweepStep(
                step_id=f"cycle_{cycle_number}_max",
                label=f"cycle_{cycle_number}:move_to_max",
                target=bounds.lab_max,
                duration_ms=int(duration_ms),
                dwell_ms=int(dwell_ms),
            )
        )
    if return_to_neutral:
        steps.append(
            ServoLabSweepStep(
                step_id="return_to_neutral",
                label="return_to_neutral",
                target=bounds.neutral,
                duration_ms=int(duration_ms),
                dwell_ms=int(dwell_ms),
            )
        )
    return ServoLabSweepPlan(
        joint_name=joint_name,
        current_position=current_position,
        bounds=bounds,
        cycles=int(cycles),
        return_to_neutral=bool(return_to_neutral),
        steps=tuple(steps),
        clamp_notes=tuple(bounds.clamp_notes),
    )


def resolve_servo_lab_bounds(
    *,
    joint: HeadJointProfile,
    calibration_record,
    lab_min: int | None,
    lab_max: int | None,
) -> ServoLabBounds:
    hard_min, hard_max, neutral = _hard_bounds(joint=joint, calibration_record=calibration_record)
    resolved_lab_min = hard_min if lab_min is None else int(lab_min)
    resolved_lab_max = hard_max if lab_max is None else int(lab_max)
    clamp_notes: list[str] = []
    if resolved_lab_min < hard_min:
        clamp_notes.append(f"hard_min_clamp:{joint.joint_name}:{resolved_lab_min}->{hard_min}")
        resolved_lab_min = hard_min
    if resolved_lab_max > hard_max:
        clamp_notes.append(f"hard_max_clamp:{joint.joint_name}:{resolved_lab_max}->{hard_max}")
        resolved_lab_max = hard_max
    if resolved_lab_min > resolved_lab_max:
        raise ServoLabError(
            "out_of_range",
            f"servo_lab_invalid_lab_bounds:{joint.joint_name}:{resolved_lab_min}>{resolved_lab_max}",
        )
    return ServoLabBounds(
        joint_name=joint.joint_name,
        hard_min=hard_min,
        hard_max=hard_max,
        neutral=neutral,
        lab_min=resolved_lab_min,
        lab_max=resolved_lab_max,
        clamp_notes=tuple(clamp_notes),
    )


def save_servo_lab_calibration(
    *,
    profile: HeadProfile,
    calibration: HeadCalibrationRecord,
    joint_name: str,
    output_path: str,
    current_position: int | None,
    save_current_as_neutral: bool,
    raw_min: int | None,
    raw_max: int | None,
    confirm_mirrored: bool | None,
) -> tuple[HeadCalibrationRecord, ServoLabCalibrationUpdate]:
    joint, record = _joint_and_record(profile=profile, calibration=calibration, joint_name=joint_name)
    clamp_notes: list[str] = []
    updated = calibration.model_copy(deep=True)
    updated_record = next(item for item in updated.joint_records if item.joint_name == joint_name)

    if save_current_as_neutral:
        if current_position is None:
            raise ServoLabError("readback_required", f"servo_lab_current_position_required:{joint_name}")
        updated_record.neutral = int(current_position)
        updated_record.notes.append("servo_lab_saved_current_as_neutral")

    next_raw_min = int(updated_record.raw_min)
    next_raw_max = int(updated_record.raw_max)
    if raw_min is not None:
        requested = int(raw_min)
        next_raw_min = max(int(joint.raw_min), min(int(joint.raw_max), requested))
        if next_raw_min != requested:
            clamp_notes.append(f"profile_raw_min_clamp:{joint_name}:{requested}->{next_raw_min}")
    if raw_max is not None:
        requested = int(raw_max)
        next_raw_max = max(int(joint.raw_min), min(int(joint.raw_max), requested))
        if next_raw_max != requested:
            clamp_notes.append(f"profile_raw_max_clamp:{joint_name}:{requested}->{next_raw_max}")
    if next_raw_min > next_raw_max:
        raise ServoLabError("out_of_range", f"servo_lab_invalid_saved_range:{joint_name}:{next_raw_min}>{next_raw_max}")
    updated_record.raw_min = next_raw_min
    updated_record.raw_max = next_raw_max
    if raw_min is not None or raw_max is not None:
        updated_record.notes = [
            note for note in updated_record.notes if not str(note).startswith(_RANGE_CONFLICT_NOTE_PREFIX)
        ]
        updated_record.notes.append("servo_lab_saved_range")
    if confirm_mirrored is not None:
        updated_record.mirrored_direction_confirmed = bool(confirm_mirrored)
    updated_record.error = None if updated_record.error == "range_conflict_from_capture" else updated_record.error
    updated.updated_at = utc_now()
    return updated, ServoLabCalibrationUpdate(
        joint_name=joint_name,
        output_path=output_path,
        calibration_kind=str(updated.calibration_kind),
        save_current_as_neutral=save_current_as_neutral,
        raw_min=int(updated_record.raw_min),
        raw_max=int(updated_record.raw_max),
        neutral=int(updated_record.neutral),
        clamp_notes=tuple(clamp_notes),
    )


def motion_control_payload(
    audit: BodyMotionControlAuditRecord | None,
    *,
    acceleration_supported: bool,
    acceleration_status: str,
) -> dict[str, object]:
    speed = audit.speed if audit is not None else None
    acceleration = audit.acceleration if audit is not None else None
    requested_speed = speed.configured_value if speed is not None and speed.source == "override" else None
    requested_acceleration = (
        acceleration.configured_value
        if acceleration is not None and acceleration.source == "override"
        else None
    )
    return {
        "speed_override_supported": True,
        "requested_speed_override": requested_speed,
        "effective_speed": speed.effective_value if speed is not None else None,
        "speed_clamped": bool(
            speed is not None
            and requested_speed is not None
            and speed.effective_value is not None
            and speed.effective_value != requested_speed
        ),
        "speed_source": speed.source if speed is not None else None,
        "speed_verified": speed.verified if speed is not None else False,
        "acceleration_supported": acceleration_supported,
        "acceleration_status": acceleration_status,
        "requested_acceleration_override": requested_acceleration,
        "effective_acceleration": (
            acceleration.effective_value
            if acceleration_supported and acceleration is not None
            else None
        ),
        "acceleration_verified": (
            acceleration.verified
            if acceleration_supported and acceleration is not None
            else False
        ),
    }


def readback_payload(
    *,
    catalog: ServoLabCatalog,
    selected_joint_name: str | None = None,
    include_health: bool = True,
    health_reads: dict[str, object] | None = None,
) -> dict[str, object]:
    selected = None
    if selected_joint_name is not None:
        selected = next((item for item in catalog.joints if item.joint_name == selected_joint_name), None)
    return {
        "catalog": catalog.to_payload(),
        "selected_joint": selected.to_payload() if selected is not None else None,
        "include_health": include_health,
        "health_reads": dict(health_reads or {}),
    }


def _records_by_joint(calibration: HeadCalibrationRecord | None) -> dict[str, object]:
    return {
        record.joint_name: record
        for record in (calibration.joint_records if calibration is not None else [])
    }


def _joint_and_record(
    *,
    profile: HeadProfile,
    calibration: HeadCalibrationRecord | None,
    joint_name: str,
):
    joint = next((item for item in profile.joints if item.enabled and item.joint_name == joint_name), None)
    if joint is None:
        raise ServoLabError("out_of_range", f"unknown_joint:{joint_name}")
    return joint, _records_by_joint(calibration).get(joint_name)


def _hard_bounds(*, joint: HeadJointProfile, calibration_record) -> tuple[int, int, int]:
    if calibration_record is not None:
        return int(calibration_record.raw_min), int(calibration_record.raw_max), int(calibration_record.neutral)
    return int(joint.raw_min), int(joint.raw_max), int(joint.neutral)


def _coupling_group(joint_name: str) -> str:
    if joint_name == "head_yaw":
        return "neck_yaw"
    if joint_name in {"head_pitch_pair_a", "head_pitch_pair_b"}:
        return "neck_pitch_roll_pair"
    if joint_name in {"eye_pitch", "eye_yaw"}:
        return "eyes"
    if joint_name.startswith("upper_lid") or joint_name.startswith("lower_lid"):
        return "lids"
    if joint_name.startswith("brow_"):
        return "brows"
    return "joint"


def _coupling_hint(joint_name: str) -> str:
    if joint_name == "head_yaw":
        return "Single-joint head yaw. Raw plus turns right and raw minus turns left."
    if joint_name == "head_pitch_pair_a":
        return "Single-joint raw plus adds right tilt. Paired A+/B- creates pitch up and A-/B+ creates pitch down."
    if joint_name == "head_pitch_pair_b":
        return "Single-joint raw minus adds left tilt. Paired A+/B- creates pitch up and A-/B+ creates pitch down."
    if joint_name == "eye_pitch":
        return "Eye pitch is single-joint here. Semantic mode may coordinate lids, but Servo Lab leaves lids independent."
    if joint_name == "eye_yaw":
        return "Eye yaw is single-joint here. Use it for direct horizontal eye characterization without semantic gaze coupling."
    if joint_name.startswith("upper_lid") or joint_name.startswith("lower_lid"):
        return "Lids are mirrored mechanically in semantic mode, but Servo Lab allows independent raw inspection and tuning."
    if joint_name.startswith("brow_"):
        return "Brows are mirrored semantically, but Servo Lab uses the saved per-side calibration exactly as configured."
    return "Direct raw joint control."


__all__ = [
    "ServoLabCapabilities",
    "ServoLabCatalog",
    "ServoLabCalibrationUpdate",
    "ServoLabError",
    "ServoLabJointCatalogItem",
    "ServoLabMovePlan",
    "ServoLabSweepPlan",
    "ServoLabSweepStep",
    "build_servo_lab_catalog",
    "motion_control_payload",
    "readback_payload",
    "resolve_servo_lab_bounds",
    "resolve_servo_lab_move",
    "resolve_servo_lab_sweep",
    "save_servo_lab_calibration",
    "servo_lab_capabilities",
]
