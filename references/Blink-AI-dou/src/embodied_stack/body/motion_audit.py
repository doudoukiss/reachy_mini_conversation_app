from __future__ import annotations

from embodied_stack.shared.contracts import (
    BodyCalibrationJointAuditRecord,
    BodyMotionControlAuditRecord,
    BodyMotionControlSettingRecord,
    BodyUsableRangeAuditRecord,
    HeadCalibrationRecord,
    HeadProfile,
)

SUSPICIOUS_NEUTRAL_MARGIN_PERCENT = 8.0
MAX_ACCELERATION_REGISTER_VALUE = 150


def build_motion_control_audit(
    *,
    profile: HeadProfile,
    calibration: HeadCalibrationRecord | None,
    transport_mode: str | None,
    transport_confirmed_live: bool | None,
    addressed_servo_ids: list[int] | None = None,
    speed_override: int | None = None,
    acceleration_override: int | None = None,
    speed_readback: dict[int, int] | None = None,
    acceleration_readback: dict[int, int] | None = None,
    acceleration_applied: bool = False,
) -> BodyMotionControlAuditRecord:
    notes: list[str] = []
    speed = _resolve_speed_setting(
        profile=profile,
        calibration=calibration,
        override_value=speed_override,
        readback=speed_readback,
        notes=notes,
    )
    acceleration = _resolve_acceleration_setting(
        profile=profile,
        calibration=calibration,
        override_value=acceleration_override,
        readback=acceleration_readback,
        applied=acceleration_applied,
        notes=notes,
    )
    return BodyMotionControlAuditRecord(
        profile_safe_speed=profile.safe_speed,
        profile_safe_acceleration=profile.safe_acceleration,
        calibration_safe_speed=(calibration.safe_speed if calibration is not None else None),
        calibration_safe_acceleration=(calibration.safe_acceleration if calibration is not None else None),
        speed=speed,
        acceleration=acceleration,
        transport_mode=transport_mode,
        transport_confirmed_live=transport_confirmed_live,
        addressed_servo_ids=sorted({int(servo_id) for servo_id in (addressed_servo_ids or [])}),
        notes=notes,
    )


def build_usable_range_audit(
    *,
    profile: HeadProfile,
    calibration: HeadCalibrationRecord | None,
    calibration_source_path: str | None = None,
) -> BodyUsableRangeAuditRecord:
    profile_joints = {joint.joint_name: joint for joint in profile.joints}
    calibration_records = {
        record.joint_name: record
        for record in (calibration.joint_records if calibration is not None else [])
    }
    using_profile_fallback = calibration is None or calibration.calibration_kind == "template"
    joint_audits: list[BodyCalibrationJointAuditRecord] = []
    suspicious_joint_names: list[str] = []
    notes: list[str] = []

    for joint in profile.joints:
        if not joint.enabled:
            continue
        record = calibration_records.get(joint.joint_name)
        raw_min = int(joint.raw_min if using_profile_fallback or record is None else record.raw_min)
        raw_max = int(joint.raw_max if using_profile_fallback or record is None else record.raw_max)
        neutral = int(joint.neutral if using_profile_fallback or record is None else record.neutral)
        suspicion_reason = _neutral_suspicion_reason(
            raw_min=raw_min,
            raw_max=raw_max,
            neutral=neutral,
            threshold_percent=SUSPICIOUS_NEUTRAL_MARGIN_PERCENT,
        )
        suspicious = suspicion_reason is not None
        if suspicious:
            suspicious_joint_names.append(joint.joint_name)
        joint_audits.append(
            BodyCalibrationJointAuditRecord(
                joint_name=joint.joint_name,
                raw_min=raw_min,
                raw_max=raw_max,
                neutral=neutral,
                profile_raw_min=int(joint.raw_min),
                profile_raw_max=int(joint.raw_max),
                profile_neutral=int(joint.neutral),
                neutral_margin_percent=round(_neutral_margin_percent(raw_min=raw_min, raw_max=raw_max, neutral=neutral), 4),
                suspicious_neutral=suspicious,
                suspicion_reason=suspicion_reason,
                notes=list(record.notes) if record is not None and not using_profile_fallback else [],
            )
        )

    if using_profile_fallback:
        notes.append("using_profile_fallback_for_usable_range")
    if suspicious_joint_names:
        notes.append(f"suspicious_neutral_joints:{','.join(sorted(suspicious_joint_names))}")

    return BodyUsableRangeAuditRecord(
        calibration_source_path=calibration_source_path,
        calibration_kind=(
            "profile_fallback"
            if using_profile_fallback
            else str(calibration.calibration_kind)
        ),
        using_profile_fallback=using_profile_fallback,
        suspicious_joint_names=sorted(suspicious_joint_names),
        joints=joint_audits,
        notes=notes,
    )


def usable_range_joint_audit(
    audit: BodyUsableRangeAuditRecord,
    joint_name: str,
) -> BodyCalibrationJointAuditRecord | None:
    for record in audit.joints:
        if record.joint_name == joint_name:
            return record
    return None


def _resolve_speed_setting(
    *,
    profile: HeadProfile,
    calibration: HeadCalibrationRecord | None,
    override_value: int | None,
    readback: dict[int, int] | None,
    notes: list[str],
) -> BodyMotionControlSettingRecord:
    if override_value is not None:
        configured = int(override_value)
        source = "override"
    elif calibration is not None and calibration.safe_speed is not None:
        configured = int(calibration.safe_speed)
        source = "calibration"
    else:
        configured = int(profile.safe_speed or 120)
        source = "profile"
    effective = max(0, configured)
    if profile.safe_speed_ceiling is not None and effective > int(profile.safe_speed_ceiling):
        notes.append(
            f"safe_speed_clamped_to_profile_ceiling:{effective}->{int(profile.safe_speed_ceiling)}"
        )
        effective = int(profile.safe_speed_ceiling)
    return _setting_record(
        configured=configured,
        effective=effective,
        source=source,
        readback=readback,
        applied=True,
        unavailable_note="speed_register_verification_pending_motion_command",
    )


def _resolve_acceleration_setting(
    *,
    profile: HeadProfile,
    calibration: HeadCalibrationRecord | None,
    override_value: int | None,
    readback: dict[int, int] | None,
    applied: bool,
    notes: list[str],
) -> BodyMotionControlSettingRecord:
    if override_value is not None:
        configured = int(override_value)
        source = "override"
    elif calibration is not None and calibration.safe_acceleration is not None:
        configured = int(calibration.safe_acceleration)
        source = "calibration"
    elif profile.safe_acceleration is not None:
        configured = int(profile.safe_acceleration)
        source = "profile"
    else:
        configured = None
        source = "missing"

    if configured is None:
        return BodyMotionControlSettingRecord(
            configured_value=None,
            effective_value=None,
            source=source,
            applied=False,
            verified=False,
            note="safe_acceleration_not_configured",
        )

    effective = max(0, min(MAX_ACCELERATION_REGISTER_VALUE, configured))
    if effective != configured:
        notes.append(
            f"safe_acceleration_clamped_to_register_limit:{configured}->{effective}"
        )
    return _setting_record(
        configured=configured,
        effective=effective,
        source=source,
        readback=readback,
        applied=applied,
        unavailable_note="acceleration_register_not_verified",
    )


def _setting_record(
    *,
    configured: int,
    effective: int,
    source: str,
    readback: dict[int, int] | None,
    applied: bool,
    unavailable_note: str,
) -> BodyMotionControlSettingRecord:
    readback_payload = {
        str(int(servo_id)): int(value)
        for servo_id, value in sorted((readback or {}).items())
    }
    readback_values = sorted({int(value) for value in readback_payload.values()})
    verified = bool(readback_payload) and readback_values == [effective]
    note = None
    readback_value = readback_values[0] if len(readback_values) == 1 else None
    if not readback_payload:
        note = unavailable_note
    elif not verified:
        note = "readback_mismatch"
    return BodyMotionControlSettingRecord(
        configured_value=configured,
        effective_value=effective,
        source=source,
        applied=applied,
        verified=verified,
        readback_value=readback_value,
        readback_by_servo=readback_payload,
        note=note,
    )


def _neutral_margin_percent(*, raw_min: int, raw_max: int, neutral: int) -> float:
    span = max(1, int(raw_max) - int(raw_min))
    low_margin = max(0, int(neutral) - int(raw_min))
    high_margin = max(0, int(raw_max) - int(neutral))
    return min(low_margin, high_margin) / span * 100.0


def _neutral_suspicion_reason(
    *,
    raw_min: int,
    raw_max: int,
    neutral: int,
    threshold_percent: float,
) -> str | None:
    if neutral < raw_min or neutral > raw_max:
        return "neutral_outside_range"
    margin_percent = _neutral_margin_percent(raw_min=raw_min, raw_max=raw_max, neutral=neutral)
    if margin_percent < threshold_percent:
        return f"neutral_margin_below_{threshold_percent:.1f}_percent"
    return None


__all__ = [
    "MAX_ACCELERATION_REGISTER_VALUE",
    "SUSPICIOUS_NEUTRAL_MARGIN_PERCENT",
    "build_motion_control_audit",
    "build_usable_range_audit",
    "usable_range_joint_audit",
]
