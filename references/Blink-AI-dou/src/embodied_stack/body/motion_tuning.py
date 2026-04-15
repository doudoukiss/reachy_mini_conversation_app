from __future__ import annotations

from embodied_stack.shared.contracts.body import (
    BodyCommandOutcomeRecord,
    DerivedOperatingBand,
    HeadCalibrationRecord,
    HeadProfile,
    MotionKineticsProfile,
    OperatingBandPolicy,
    RatioDeviationBand,
    SemanticTuningRecord,
    SignedAxisBand,
)

_FAMILY_JOINTS = {
    "head_yaw": ("head_yaw",),
    "head_pitch_pair": ("head_pitch_pair_a", "head_pitch_pair_b"),
    "eye_yaw": ("eye_yaw",),
    "eye_pitch": ("eye_pitch",),
    "upper_lids": ("upper_lid_left", "upper_lid_right"),
    "lower_lids": ("lower_lid_left", "lower_lid_right"),
    "brows": ("brow_left", "brow_right"),
}


def default_motion_kinetics_profiles() -> dict[str, MotionKineticsProfile]:
    return {
        "primitive_slow": MotionKineticsProfile(
            speed=100,
            acceleration=32,
            duration_scale=1.0,
            hold_scale=1.0,
            notes=["primitive_grounded_slow"],
        ),
        "primitive_fast": MotionKineticsProfile(
            speed=120,
            acceleration=40,
            duration_scale=1.0,
            hold_scale=1.0,
            notes=["primitive_grounded_fast"],
        ),
        "calm_settle": MotionKineticsProfile(
            speed=100,
            acceleration=32,
            duration_scale=1.12,
            hold_scale=1.08,
            notes=["stable_recovery_and_safe_idle"],
        ),
        "social_shift": MotionKineticsProfile(
            speed=120,
            acceleration=40,
            duration_scale=1.0,
            hold_scale=1.0,
            notes=["standard_live_companion_shift"],
        ),
        "accent_punctuate": MotionKineticsProfile(
            speed=120,
            acceleration=40,
            duration_scale=0.92,
            hold_scale=0.88,
            notes=["sharper_demo_accent_without_higher_global_speed"],
        ),
        "blink_transient": MotionKineticsProfile(
            speed=120,
            acceleration=40,
            duration_scale=0.82,
            hold_scale=0.74,
            notes=["brief_lid_punctuation"],
        ),
    }


def resolve_motion_kinetics_profiles(tuning: SemanticTuningRecord) -> dict[str, MotionKineticsProfile]:
    profiles = {name: item.model_copy(deep=True) for name, item in default_motion_kinetics_profiles().items()}
    profiles.update({name: item.model_copy(deep=True) for name, item in tuning.motion_kinetics_profiles.items()})
    return profiles


def derive_operating_band(
    *,
    profile: HeadProfile,
    calibration: HeadCalibrationRecord | None,
    policy: OperatingBandPolicy,
) -> DerivedOperatingBand:
    joint_lookup = {joint.joint_name: joint for joint in profile.joints if joint.enabled}
    calibration_lookup = {
        record.joint_name: record
        for record in (calibration.joint_records if calibration is not None else [])
    }

    def _record(joint_name: str):
        return calibration_lookup.get(joint_name) or joint_lookup[joint_name]

    def _signed_band(ratio: float) -> SignedAxisBand:
        resolved = _clamp_ratio(ratio)
        return SignedAxisBand(negative_limit=resolved, positive_limit=resolved)

    def _ratio_band(joint_names: tuple[str, ...], *, held_ratio: float, transient_ratio: float) -> RatioDeviationBand:
        neutral_ratios = [_joint_neutral_ratio(joint_name, profile=profile, calibration=calibration) for joint_name in joint_names]
        negative_full = min(neutral_ratios)
        positive_full = min(1.0 - item for item in neutral_ratios)
        return RatioDeviationBand(
            negative_limit=_clamp_ratio(negative_full * held_ratio),
            positive_limit=_clamp_ratio(positive_full * held_ratio),
            transient_negative_limit=_clamp_ratio(negative_full * transient_ratio),
            transient_positive_limit=_clamp_ratio(positive_full * transient_ratio),
        )

    roll_negative = _clamp_ratio(policy.neck_tilt_ratio)
    roll_positive = _clamp_ratio(policy.neck_tilt_ratio)
    pitch_a = _record("head_pitch_pair_a")
    pitch_b = _record("head_pitch_pair_b")
    if policy.neck_tilt_negative_reference_raw is not None:
        negative_full = max(1, int(pitch_b.neutral) - int(pitch_b.raw_min))
        negative_safe = max(0, int(pitch_b.neutral) - int(policy.neck_tilt_negative_reference_raw))
        roll_negative = _clamp_ratio((negative_safe / negative_full) * policy.neck_tilt_ratio)
    if policy.neck_tilt_positive_reference_raw is not None:
        positive_full = max(1, int(pitch_a.raw_max) - int(pitch_a.neutral))
        positive_safe = max(0, int(policy.neck_tilt_positive_reference_raw) - int(pitch_a.neutral))
        roll_positive = _clamp_ratio((positive_safe / positive_full) * policy.neck_tilt_ratio)

    notes = list(policy.notes)
    if calibration is None or calibration.calibration_kind == "template":
        notes.append("operating_band_using_profile_fallback")

    return DerivedOperatingBand(
        head_yaw=_signed_band(policy.head_yaw_ratio),
        head_pitch=_signed_band(policy.neck_pitch_ratio),
        head_roll=SignedAxisBand(negative_limit=roll_negative, positive_limit=roll_positive),
        eye_yaw=_signed_band(policy.eye_yaw_ratio),
        eye_pitch=_signed_band(policy.eye_pitch_ratio),
        upper_lid=_ratio_band(
            ("upper_lid_left", "upper_lid_right"),
            held_ratio=policy.upper_lid_held_ratio,
            transient_ratio=policy.transient_lid_ratio,
        ),
        lower_lid=_ratio_band(
            ("lower_lid_left", "lower_lid_right"),
            held_ratio=policy.lower_lid_held_ratio,
            transient_ratio=policy.transient_lid_ratio,
        ),
        brow=_ratio_band(
            ("brow_left", "brow_right"),
            held_ratio=policy.brow_held_ratio,
            transient_ratio=policy.transient_brow_ratio,
        ),
        notes=notes,
    )


def remaining_margin_percent_by_family(
    *,
    compiled_targets: dict[str, int],
    profile: HeadProfile,
    calibration: HeadCalibrationRecord | None,
) -> dict[str, float]:
    if not compiled_targets:
        return {}
    joint_lookup = {joint.joint_name: joint for joint in profile.joints if joint.enabled}
    calibration_lookup = {
        record.joint_name: record
        for record in (calibration.joint_records if calibration is not None else [])
    }
    results: dict[str, float] = {}

    for family_name, joint_names in _FAMILY_JOINTS.items():
        family_margins: list[float] = []
        for joint_name in joint_names:
            if joint_name not in compiled_targets:
                continue
            joint = joint_lookup.get(joint_name)
            if joint is None:
                continue
            source = calibration_lookup.get(joint_name)
            raw_min = int(source.raw_min if source is not None else joint.raw_min)
            raw_max = int(source.raw_max if source is not None else joint.raw_max)
            target = int(compiled_targets[joint_name])
            span = max(1, raw_max - raw_min)
            margin = min(max(0, target - raw_min), max(0, raw_max - target)) / span * 100.0
            family_margins.append(round(margin, 4))
        if family_margins:
            results[family_name] = min(family_margins)
    return results


def extract_clamp_reasons(*notes: str) -> list[str]:
    reasons: list[str] = []
    for note in notes:
        value = str(note or "")
        if value.startswith(("envelope:", "operating_band:", "combination:")):
            reasons.append(value)
    return list(dict.fromkeys(reasons))


def outcome_margin_payload(
    outcome: BodyCommandOutcomeRecord,
    *,
    profile: HeadProfile,
    calibration: HeadCalibrationRecord | None,
) -> BodyCommandOutcomeRecord:
    outcome.remaining_margin_percent_by_family = remaining_margin_percent_by_family(
        compiled_targets=outcome.peak_compiled_targets,
        profile=profile,
        calibration=calibration,
    )
    outcome.clamp_reasons = extract_clamp_reasons(*outcome.outcome_notes)
    return outcome


def _joint_neutral_ratio(
    joint_name: str,
    *,
    profile: HeadProfile,
    calibration: HeadCalibrationRecord | None,
) -> float:
    joint_lookup = {joint.joint_name: joint for joint in profile.joints if joint.enabled}
    calibration_lookup = {
        record.joint_name: record
        for record in (calibration.joint_records if calibration is not None else [])
    }
    joint = joint_lookup[joint_name]
    source = calibration_lookup.get(joint_name)
    raw_min = int(source.raw_min if source is not None else joint.raw_min)
    raw_max = int(source.raw_max if source is not None else joint.raw_max)
    neutral = int(source.neutral if source is not None else joint.neutral)
    span = max(1, raw_max - raw_min)
    direction = str(joint.positive_direction).lower()
    positive = "raw_minus" not in direction and "close" not in direction
    if positive:
        return _clamp_ratio((neutral - raw_min) / span)
    return _clamp_ratio((raw_max - neutral) / span)


def _clamp_ratio(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


__all__ = [
    "default_motion_kinetics_profiles",
    "derive_operating_band",
    "extract_clamp_reasons",
    "outcome_margin_payload",
    "remaining_margin_percent_by_family",
    "resolve_motion_kinetics_profiles",
]
