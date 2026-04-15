from __future__ import annotations

from dataclasses import asdict, dataclass
from math import floor

from embodied_stack.shared.contracts import (
    BodyPose,
    BodyUsableRangeAuditRecord,
    CompiledAnimation,
    CompiledBodyFrame,
    HeadCalibrationRecord,
    HeadProfile,
)

from .library import apply_pose_overrides, expression_pose
from .motion_audit import build_usable_range_audit, usable_range_joint_audit


@dataclass(frozen=True)
class RangeDemoEnvelope:
    demo_fraction: float
    margin_counts: int


@dataclass(frozen=True)
class RangeDemoMotionControlOverride:
    speed: int | None = None
    acceleration: int | None = None


@dataclass(frozen=True)
class RangeDemoPreset:
    name: str
    head_yaw: RangeDemoEnvelope
    head_pitch_pair: RangeDemoEnvelope
    head_roll: RangeDemoEnvelope
    eye_yaw: RangeDemoEnvelope
    eye_pitch: RangeDemoEnvelope
    lids: RangeDemoEnvelope
    brows: RangeDemoEnvelope


@dataclass(frozen=True)
class RangeDemoSequenceDefinition:
    name: str
    title: str
    preset_name: str
    target_duration_ms: int
    motion_control_override: RangeDemoMotionControlOverride | None = None


@dataclass(frozen=True)
class RangeDemoTimingProfile:
    neutral_settle_duration_ms: int
    neutral_settle_hold_ms: int
    endpoint_duration_ms: int
    endpoint_hold_ms: int
    center_duration_ms: int
    center_hold_ms: int
    sweep_prep_duration_ms: int
    sweep_prep_hold_ms: int
    sweep_endpoint_duration_ms: int
    sweep_endpoint_hold_ms: int
    final_neutral_duration_ms: int
    final_neutral_hold_ms: int


@dataclass(frozen=True)
class RangeDemoJointPlan:
    joint_name: str
    servo_ids: tuple[int, ...]
    raw_min: int
    raw_max: int
    neutral: int
    usable_min: int
    usable_max: int
    target_low: int
    target_high: int
    positive_direction: str
    calibration_kind: str
    control_label_low: str
    control_label_high: str
    planning_source: str
    neutral_margin_percent: float
    suspicious_neutral: bool
    profile_raw_min: int
    profile_raw_max: int
    profile_neutral: int

    def to_payload(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class RangeDemoPlan:
    sequence_name: str
    sequence_title: str
    preset_name: str
    animation: CompiledAnimation
    joint_plans: dict[str, RangeDemoJointPlan]
    calibration_source_path: str | None
    calibration_kind: str
    using_profile_fallback: bool
    motion_control_override: RangeDemoMotionControlOverride | None = None
    usable_range_audit: BodyUsableRangeAuditRecord | None = None
    clamping_notes: tuple[str, ...] = ()

    def to_payload(self) -> dict[str, object]:
        return {
            "sequence_name": self.sequence_name,
            "sequence_title": self.sequence_title,
            "preset_name": self.preset_name,
            "calibration_source_path": self.calibration_source_path,
            "calibration_kind": self.calibration_kind,
            "using_profile_fallback": self.using_profile_fallback,
            "clamping_notes": list(self.clamping_notes),
            "motion_control_override": (
                asdict(self.motion_control_override)
                if self.motion_control_override is not None
                else None
            ),
            "usable_range_audit": (
                self.usable_range_audit.model_dump(mode="json")
                if self.usable_range_audit is not None
                else None
            ),
            "joint_plans": {
                joint_name: item.to_payload()
                for joint_name, item in self.joint_plans.items()
            },
            "executed_frame_count": len(self.animation.frames),
            "executed_frame_names": [frame.frame_name for frame in self.animation.frames],
        }


_PRESETS = {
    "investor_neck_protective_joint_envelope_v1": RangeDemoPreset(
        name="investor_neck_protective_joint_envelope_v1",
        head_yaw=RangeDemoEnvelope(demo_fraction=0.92, margin_counts=30),
        head_pitch_pair=RangeDemoEnvelope(demo_fraction=0.82, margin_counts=85),
        head_roll=RangeDemoEnvelope(demo_fraction=0.82, margin_counts=85),
        eye_yaw=RangeDemoEnvelope(demo_fraction=0.92, margin_counts=25),
        eye_pitch=RangeDemoEnvelope(demo_fraction=0.92, margin_counts=25),
        lids=RangeDemoEnvelope(demo_fraction=0.90, margin_counts=20),
        brows=RangeDemoEnvelope(demo_fraction=0.92, margin_counts=15),
    ),
    "investor_show_joint_envelope_v1": RangeDemoPreset(
        name="investor_show_joint_envelope_v1",
        head_yaw=RangeDemoEnvelope(demo_fraction=0.92, margin_counts=30),
        head_pitch_pair=RangeDemoEnvelope(demo_fraction=0.90, margin_counts=50),
        head_roll=RangeDemoEnvelope(demo_fraction=0.90, margin_counts=50),
        eye_yaw=RangeDemoEnvelope(demo_fraction=0.92, margin_counts=25),
        eye_pitch=RangeDemoEnvelope(demo_fraction=0.92, margin_counts=25),
        lids=RangeDemoEnvelope(demo_fraction=0.90, margin_counts=20),
        brows=RangeDemoEnvelope(demo_fraction=0.92, margin_counts=15),
    ),
    "servo_range_showcase_joint_envelope_v1": RangeDemoPreset(
        name="servo_range_showcase_joint_envelope_v1",
        head_yaw=RangeDemoEnvelope(demo_fraction=1.0, margin_counts=0),
        head_pitch_pair=RangeDemoEnvelope(demo_fraction=1.0, margin_counts=0),
        head_roll=RangeDemoEnvelope(demo_fraction=1.0, margin_counts=0),
        eye_yaw=RangeDemoEnvelope(demo_fraction=1.0, margin_counts=0),
        eye_pitch=RangeDemoEnvelope(demo_fraction=1.0, margin_counts=0),
        lids=RangeDemoEnvelope(demo_fraction=1.0, margin_counts=0),
        brows=RangeDemoEnvelope(demo_fraction=1.0, margin_counts=0),
    ),
}

_POST_V3_TIMING = RangeDemoTimingProfile(
    neutral_settle_duration_ms=1800,
    neutral_settle_hold_ms=1200,
    endpoint_duration_ms=2200,
    endpoint_hold_ms=1800,
    center_duration_ms=1600,
    center_hold_ms=1200,
    sweep_prep_duration_ms=1200,
    sweep_prep_hold_ms=900,
    sweep_endpoint_duration_ms=2200,
    sweep_endpoint_hold_ms=1500,
    final_neutral_duration_ms=1800,
    final_neutral_hold_ms=1500,
)

_SEQUENCES = {
    "investor_eye_pitch_v4": RangeDemoSequenceDefinition(
        name="investor_eye_pitch_v4",
        title="Investor V4 eye-pitch motion proof",
        preset_name="servo_range_showcase_joint_envelope_v1",
        target_duration_ms=48000,
        motion_control_override=RangeDemoMotionControlOverride(speed=100, acceleration=32),
    ),
    "investor_eye_yaw_v4": RangeDemoSequenceDefinition(
        name="investor_eye_yaw_v4",
        title="Investor V4 eye-yaw motion proof",
        preset_name="servo_range_showcase_joint_envelope_v1",
        target_duration_ms=48000,
        motion_control_override=RangeDemoMotionControlOverride(speed=100, acceleration=32),
    ),
    "investor_blink_v5": RangeDemoSequenceDefinition(
        name="investor_blink_v5",
        title="Investor V5 blink motion proof",
        preset_name="servo_range_showcase_joint_envelope_v1",
        target_duration_ms=32000,
        motion_control_override=RangeDemoMotionControlOverride(speed=100, acceleration=32),
    ),
    "investor_both_lids_v5": RangeDemoSequenceDefinition(
        name="investor_both_lids_v5",
        title="Investor V5 both-eye lid motion proof",
        preset_name="servo_range_showcase_joint_envelope_v1",
        target_duration_ms=20000,
        motion_control_override=RangeDemoMotionControlOverride(speed=100, acceleration=32),
    ),
    "investor_left_eye_lids_v5": RangeDemoSequenceDefinition(
        name="investor_left_eye_lids_v5",
        title="Investor V5 left-eye lid motion proof",
        preset_name="servo_range_showcase_joint_envelope_v1",
        target_duration_ms=20000,
        motion_control_override=RangeDemoMotionControlOverride(speed=100, acceleration=32),
    ),
    "investor_right_eye_lids_v5": RangeDemoSequenceDefinition(
        name="investor_right_eye_lids_v5",
        title="Investor V5 right-eye lid motion proof",
        preset_name="servo_range_showcase_joint_envelope_v1",
        target_duration_ms=20000,
        motion_control_override=RangeDemoMotionControlOverride(speed=100, acceleration=32),
    ),
    "investor_brow_left_v6": RangeDemoSequenceDefinition(
        name="investor_brow_left_v6",
        title="Investor V6 left-brow motion proof",
        preset_name="investor_show_joint_envelope_v1",
        target_duration_ms=36000,
        motion_control_override=RangeDemoMotionControlOverride(speed=100, acceleration=32),
    ),
    "investor_brow_right_v6": RangeDemoSequenceDefinition(
        name="investor_brow_right_v6",
        title="Investor V6 right-brow motion proof",
        preset_name="investor_show_joint_envelope_v1",
        target_duration_ms=36000,
        motion_control_override=RangeDemoMotionControlOverride(speed=100, acceleration=32),
    ),
    "investor_brows_both_v6": RangeDemoSequenceDefinition(
        name="investor_brows_both_v6",
        title="Investor V6 both-brows motion proof",
        preset_name="investor_show_joint_envelope_v1",
        target_duration_ms=36000,
        motion_control_override=RangeDemoMotionControlOverride(speed=100, acceleration=32),
    ),
    "investor_head_yaw_v3": RangeDemoSequenceDefinition(
        name="investor_head_yaw_v3",
        title="Investor V3 head-yaw motion proof",
        preset_name="servo_range_showcase_joint_envelope_v1",
        target_duration_ms=48000,
        motion_control_override=RangeDemoMotionControlOverride(speed=100, acceleration=32),
    ),
    "investor_neck_pitch_v7": RangeDemoSequenceDefinition(
        name="investor_neck_pitch_v7",
        title="Investor V7 neck-pitch motion proof",
        preset_name="investor_neck_protective_joint_envelope_v1",
        target_duration_ms=48000,
        motion_control_override=RangeDemoMotionControlOverride(speed=100, acceleration=32),
    ),
    "investor_neck_tilt_v7": RangeDemoSequenceDefinition(
        name="investor_neck_tilt_v7",
        title="Investor V7 neck-tilt motion proof",
        preset_name="investor_neck_protective_joint_envelope_v1",
        target_duration_ms=48000,
        motion_control_override=RangeDemoMotionControlOverride(speed=100, acceleration=32),
    ),
    "servo_range_showcase_v1": RangeDemoSequenceDefinition(
        name="servo_range_showcase_v1",
        title="Explicit servo endpoint showcase",
        preset_name="servo_range_showcase_joint_envelope_v1",
        target_duration_ms=115000,
    ),
}

_POSITIVE_DIRECTION_LABELS = {
    "look_right": ("left", "right"),
    "look_up": ("down", "up"),
    "raise_brow": ("lower", "raise"),
    "raise_brow_raw_minus": ("lower", "raise"),
    "open": ("close", "open"),
    "close": ("open", "close"),
    "head_up_raw_plus": ("down", "up"),
    "head_up_raw_minus": ("down", "up"),
}


def available_range_demo_presets() -> tuple[str, ...]:
    return tuple(sorted(_PRESETS))


def available_range_demo_sequences() -> tuple[str, ...]:
    return tuple(sorted(_SEQUENCES))


def range_demo_preset(name: str) -> RangeDemoPreset:
    if name not in _PRESETS:
        raise KeyError(name)
    return _PRESETS[name]


def range_demo_sequence(name: str) -> RangeDemoSequenceDefinition:
    if name not in _SEQUENCES:
        raise KeyError(name)
    return _SEQUENCES[name]


def build_range_demo_plan(
    *,
    profile: HeadProfile,
    calibration: HeadCalibrationRecord | None,
    preset_name: str | None = None,
    sequence_name: str | None = None,
    neutral_pose: BodyPose,
    friendly_frame: CompiledBodyFrame | None = None,
    calibration_source_path: str | None = None,
    tuning_lane: str | None = None,
    default_kinetics_profile: str | None = None,
    requested_speed: int | None = None,
    requested_acceleration: int | None = None,
) -> RangeDemoPlan:
    sequence = range_demo_sequence(sequence_name) if sequence_name else None
    resolved_preset_name = preset_name or (sequence.preset_name if sequence is not None else "investor_show_joint_envelope_v1")
    preset = range_demo_preset(resolved_preset_name)
    usable_range_audit = build_usable_range_audit(
        profile=profile,
        calibration=calibration,
        calibration_source_path=calibration_source_path,
    )
    using_profile_fallback = usable_range_audit.using_profile_fallback
    calibration_kind = usable_range_audit.calibration_kind or "profile_fallback"
    joint_plans: dict[str, RangeDemoJointPlan] = {}
    notes: list[str] = []

    for joint in profile.joints:
        if not joint.enabled:
            continue
        audit = usable_range_joint_audit(usable_range_audit, joint.joint_name)
        if audit is None or using_profile_fallback:
            planning_source = "profile_fallback"
            raw_min = int(joint.raw_min)
            raw_max = int(joint.raw_max)
            neutral = int(joint.neutral)
            suspicious_neutral = False
            neutral_margin_percent = 50.0
        elif audit.suspicious_neutral:
            planning_source = "profile_due_to_suspicious_neutral"
            raw_min = int(joint.raw_min)
            raw_max = int(joint.raw_max)
            neutral = int(joint.neutral)
            suspicious_neutral = True
            neutral_margin_percent = float(audit.neutral_margin_percent)
            notes.append(f"{joint.joint_name}:fallback_to_profile_due_to_suspicious_neutral")
        else:
            planning_source = "calibration"
            raw_min = int(audit.raw_min)
            raw_max = int(audit.raw_max)
            neutral = int(audit.neutral)
            suspicious_neutral = False
            neutral_margin_percent = float(audit.neutral_margin_percent)

        envelope = _envelope_for_joint(preset, joint.joint_name)
        usable_min = min(max(raw_min, raw_min + envelope.margin_counts), raw_max)
        usable_max = max(min(raw_max, raw_max - envelope.margin_counts), raw_min)
        if usable_min >= usable_max:
            usable_min = raw_min
            usable_max = raw_max
            notes.append(f"{joint.joint_name}:fallback_to_raw_bounds")
        low_span = max(0, neutral - usable_min)
        high_span = max(0, usable_max - neutral)
        target_low = max(raw_min, neutral - floor(low_span * envelope.demo_fraction))
        target_high = min(raw_max, neutral + floor(high_span * envelope.demo_fraction))
        label_low, label_high = _control_labels(joint.positive_direction)
        joint_plans[joint.joint_name] = RangeDemoJointPlan(
            joint_name=joint.joint_name,
            servo_ids=tuple(int(servo_id) for servo_id in joint.servo_ids),
            raw_min=raw_min,
            raw_max=raw_max,
            neutral=neutral,
            usable_min=usable_min,
            usable_max=usable_max,
            target_low=target_low,
            target_high=target_high,
            positive_direction=str(joint.positive_direction),
            calibration_kind=calibration_kind,
            control_label_low=label_low,
            control_label_high=label_high,
            planning_source=planning_source,
            neutral_margin_percent=round(neutral_margin_percent, 4),
            suspicious_neutral=suspicious_neutral,
            profile_raw_min=int(joint.raw_min),
            profile_raw_max=int(joint.raw_max),
            profile_neutral=int(joint.neutral),
        )

    neutral_targets = {name: plan.neutral for name, plan in joint_plans.items()}
    friendly = friendly_frame or CompiledBodyFrame(
        frame_name="friendly_settle",
        pose=expression_pose("friendly", neutral_pose=neutral_pose),
        servo_targets=dict(neutral_targets),
        duration_ms=620,
        hold_ms=320,
        compiler_notes=["range_demo_friendly_settle"],
    )
    frames = _sequence_frames(
        sequence_name=(sequence.name if sequence is not None else None),
        neutral_pose=neutral_pose,
        neutral_targets=neutral_targets,
        joint_plans=joint_plans,
        friendly=friendly,
    )
    if tuning_lane is not None or default_kinetics_profile is not None:
        frames = [
            frame.model_copy(
                update={
                    "tuning_lane": frame.tuning_lane or tuning_lane,
                    "kinetics_profile": frame.kinetics_profile or default_kinetics_profile,
                    "requested_speed": frame.requested_speed if frame.requested_speed is not None else requested_speed,
                    "requested_acceleration": (
                        frame.requested_acceleration if frame.requested_acceleration is not None else requested_acceleration
                    ),
                }
            )
            for frame in frames
        ]
    total_duration_ms = sum(max(0, int(frame.duration_ms)) + max(0, int(frame.hold_ms)) for frame in frames)
    animation_name = sequence.name if sequence is not None else resolved_preset_name
    kinetics_profiles_used = list(
        dict.fromkeys(frame.kinetics_profile for frame in frames if frame.kinetics_profile)
    )
    requested_speeds = [int(frame.requested_speed) for frame in frames if frame.requested_speed is not None]
    requested_accelerations = [
        int(frame.requested_acceleration) for frame in frames if frame.requested_acceleration is not None
    ]
    animation = CompiledAnimation(
        animation_name=f"body_range_demo:{animation_name}",
        frames=frames,
        total_duration_ms=total_duration_ms,
        kinetics_profiles_used=kinetics_profiles_used,
        requested_speed=max(requested_speeds) if requested_speeds else None,
        requested_acceleration=max(requested_accelerations) if requested_accelerations else None,
        tuning_lane=tuning_lane,
        compiler_notes=[
            "range_demo",
            f"preset:{resolved_preset_name}",
            f"sequence:{sequence.name if sequence is not None else 'custom_preset'}",
            f"calibration_kind:{calibration_kind}",
        ],
    )
    return RangeDemoPlan(
        sequence_name=sequence.name if sequence is not None else resolved_preset_name,
        sequence_title=sequence.title if sequence is not None else "Range demo",
        preset_name=resolved_preset_name,
        animation=animation,
        joint_plans=joint_plans,
        calibration_source_path=calibration_source_path,
        calibration_kind=calibration_kind,
        using_profile_fallback=using_profile_fallback,
        motion_control_override=(sequence.motion_control_override if sequence is not None else None),
        usable_range_audit=usable_range_audit,
        clamping_notes=tuple(notes),
    )


def _sequence_frames(
    *,
    sequence_name: str | None,
    neutral_pose: BodyPose,
    neutral_targets: dict[str, int],
    joint_plans: dict[str, RangeDemoJointPlan],
    friendly: CompiledBodyFrame,
) -> list[CompiledBodyFrame]:
    if sequence_name == "investor_eye_yaw_v4":
        return _bidirectional_axis_sequence_frames(
            neutral_pose=neutral_pose,
            neutral_targets=neutral_targets,
            joint_plans=joint_plans,
            low_name="left",
            high_name="right",
            low_overrides={"eye_yaw": joint_plans["eye_yaw"].raw_min},
            high_overrides={"eye_yaw": joint_plans["eye_yaw"].raw_max},
            low_pose_overrides={"eye_yaw": -0.98},
            high_pose_overrides={"eye_yaw": 0.98},
        )
    if sequence_name == "investor_eye_pitch_v4":
        return _bidirectional_axis_sequence_frames(
            neutral_pose=neutral_pose,
            neutral_targets=neutral_targets,
            joint_plans=joint_plans,
            low_name="down",
            high_name="up",
            low_overrides={"eye_pitch": joint_plans["eye_pitch"].raw_min},
            high_overrides={"eye_pitch": joint_plans["eye_pitch"].raw_max},
            low_pose_overrides={"eye_pitch": -0.98},
            high_pose_overrides={"eye_pitch": 0.98},
        )
    if sequence_name == "investor_both_lids_v5":
        return _open_close_sequence_frames(
            neutral_pose=neutral_pose,
            neutral_targets=neutral_targets,
            joint_plans=joint_plans,
            close_name="both_eyes_close",
            open_name="both_eyes_open",
            close_overrides={
                "upper_lid_left": _target_for_label(joint_plans["upper_lid_left"], "close"),
                "upper_lid_right": _target_for_label(joint_plans["upper_lid_right"], "close"),
                "lower_lid_left": _target_for_label(joint_plans["lower_lid_left"], "close"),
                "lower_lid_right": _target_for_label(joint_plans["lower_lid_right"], "close"),
            },
            open_overrides={
                "upper_lid_left": _target_for_label(joint_plans["upper_lid_left"], "open"),
                "upper_lid_right": _target_for_label(joint_plans["upper_lid_right"], "open"),
                "lower_lid_left": _target_for_label(joint_plans["lower_lid_left"], "open"),
                "lower_lid_right": _target_for_label(joint_plans["lower_lid_right"], "open"),
            },
            close_pose_overrides={
                "upper_lid_left_open": 0.0,
                "upper_lid_right_open": 0.0,
                "lower_lid_left_open": 0.0,
                "lower_lid_right_open": 0.0,
            },
            open_pose_overrides={
                "upper_lid_left_open": 1.0,
                "upper_lid_right_open": 1.0,
                "lower_lid_left_open": 1.0,
                "lower_lid_right_open": 1.0,
            },
        )
    if sequence_name == "investor_left_eye_lids_v5":
        return _open_close_sequence_frames(
            neutral_pose=neutral_pose,
            neutral_targets=neutral_targets,
            joint_plans=joint_plans,
            close_name="left_eye_close",
            open_name="left_eye_open",
            close_overrides={
                "upper_lid_left": _target_for_label(joint_plans["upper_lid_left"], "close"),
                "lower_lid_left": _target_for_label(joint_plans["lower_lid_left"], "close"),
            },
            open_overrides={
                "upper_lid_left": _target_for_label(joint_plans["upper_lid_left"], "open"),
                "lower_lid_left": _target_for_label(joint_plans["lower_lid_left"], "open"),
            },
            close_pose_overrides={
                "upper_lid_left_open": 0.0,
                "lower_lid_left_open": 0.0,
            },
            open_pose_overrides={
                "upper_lid_left_open": 1.0,
                "lower_lid_left_open": 1.0,
            },
        )
    if sequence_name == "investor_right_eye_lids_v5":
        return _open_close_sequence_frames(
            neutral_pose=neutral_pose,
            neutral_targets=neutral_targets,
            joint_plans=joint_plans,
            close_name="right_eye_close",
            open_name="right_eye_open",
            close_overrides={
                "upper_lid_right": _target_for_label(joint_plans["upper_lid_right"], "close"),
                "lower_lid_right": _target_for_label(joint_plans["lower_lid_right"], "close"),
            },
            open_overrides={
                "upper_lid_right": _target_for_label(joint_plans["upper_lid_right"], "open"),
                "lower_lid_right": _target_for_label(joint_plans["lower_lid_right"], "open"),
            },
            close_pose_overrides={
                "upper_lid_right_open": 0.0,
                "lower_lid_right_open": 0.0,
            },
            open_pose_overrides={
                "upper_lid_right_open": 1.0,
                "lower_lid_right_open": 1.0,
            },
        )
    if sequence_name == "investor_blink_v5":
        return _blink_sequence_frames(
            neutral_pose=neutral_pose,
            neutral_targets=neutral_targets,
            joint_plans=joint_plans,
        )
    if sequence_name == "investor_brows_both_v6":
        return _bidirectional_axis_sequence_frames(
            neutral_pose=neutral_pose,
            neutral_targets=neutral_targets,
            joint_plans=joint_plans,
            low_name="lower",
            high_name="raise",
            low_overrides={
                "brow_left": _target_for_label(joint_plans["brow_left"], "lower"),
                "brow_right": _target_for_label(joint_plans["brow_right"], "lower"),
            },
            high_overrides={
                "brow_left": _target_for_label(joint_plans["brow_left"], "raise"),
                "brow_right": _target_for_label(joint_plans["brow_right"], "raise"),
            },
            low_pose_overrides={"brow_raise_left": 0.0, "brow_raise_right": 0.0},
            high_pose_overrides={"brow_raise_left": 1.0, "brow_raise_right": 1.0},
            include_low_sweep_from_high=False,
            include_high_sweep_from_low=True,
        )
    if sequence_name == "investor_brow_left_v6":
        return _bidirectional_axis_sequence_frames(
            neutral_pose=neutral_pose,
            neutral_targets=neutral_targets,
            joint_plans=joint_plans,
            low_name="lower",
            high_name="raise",
            low_overrides={"brow_left": _target_for_label(joint_plans["brow_left"], "lower")},
            high_overrides={"brow_left": _target_for_label(joint_plans["brow_left"], "raise")},
            low_pose_overrides={"brow_raise_left": 0.0},
            high_pose_overrides={"brow_raise_left": 1.0},
            include_low_sweep_from_high=False,
            include_high_sweep_from_low=True,
        )
    if sequence_name == "investor_brow_right_v6":
        return _bidirectional_axis_sequence_frames(
            neutral_pose=neutral_pose,
            neutral_targets=neutral_targets,
            joint_plans=joint_plans,
            low_name="lower",
            high_name="raise",
            low_overrides={"brow_right": _target_for_label(joint_plans["brow_right"], "lower")},
            high_overrides={"brow_right": _target_for_label(joint_plans["brow_right"], "raise")},
            low_pose_overrides={"brow_raise_right": 0.0},
            high_pose_overrides={"brow_raise_right": 1.0},
            include_low_sweep_from_high=False,
            include_high_sweep_from_low=True,
        )
    if sequence_name == "investor_head_yaw_v3":
        return _investor_head_yaw_v3_frames(
            neutral_pose=neutral_pose,
            neutral_targets=neutral_targets,
            joint_plans=joint_plans,
        )
    if sequence_name == "investor_neck_tilt_v7":
        return _bidirectional_axis_sequence_frames(
            neutral_pose=neutral_pose,
            neutral_targets=neutral_targets,
            joint_plans=joint_plans,
            low_name="left",
            high_name="right",
            low_overrides={"head_pitch_pair_b": joint_plans["head_pitch_pair_b"].target_low},
            high_overrides={"head_pitch_pair_a": joint_plans["head_pitch_pair_a"].target_high},
            low_pose_overrides={"head_roll": -0.82},
            high_pose_overrides={"head_roll": 0.82},
        )
    if sequence_name == "investor_neck_pitch_v7":
        return _bidirectional_axis_sequence_frames(
            neutral_pose=neutral_pose,
            neutral_targets=neutral_targets,
            joint_plans=joint_plans,
            low_name="down",
            high_name="up",
            low_overrides={
                "head_pitch_pair_a": joint_plans["head_pitch_pair_a"].target_low,
                "head_pitch_pair_b": joint_plans["head_pitch_pair_b"].target_high,
            },
            high_overrides={
                "head_pitch_pair_a": joint_plans["head_pitch_pair_a"].target_high,
                "head_pitch_pair_b": joint_plans["head_pitch_pair_b"].target_low,
            },
            low_pose_overrides={"head_pitch": -0.9},
            high_pose_overrides={"head_pitch": 0.9},
        )
    if sequence_name == "servo_range_showcase_v1":
        return _servo_limit_sequence_frames(
            neutral_pose=neutral_pose,
            neutral_targets=neutral_targets,
            joint_plans=joint_plans,
        )
    return [
        _frame("neutral_settle", neutral_pose, neutral_targets, 720, 440),
        _axis_frame(
            frame_name="head_yaw_left",
            neutral_pose=neutral_pose,
            servo_targets=neutral_targets,
            joint_plans=joint_plans,
            overrides={"head_yaw": joint_plans["head_yaw"].target_low},
            pose_overrides={"head_yaw": -0.98},
            duration_ms=560,
            hold_ms=320,
        ),
        _axis_frame(
            frame_name="head_yaw_right",
            neutral_pose=neutral_pose,
            servo_targets=neutral_targets,
            joint_plans=joint_plans,
            overrides={"head_yaw": joint_plans["head_yaw"].target_high},
            pose_overrides={"head_yaw": 0.98},
            duration_ms=560,
            hold_ms=320,
        ),
        _frame("head_yaw_center", neutral_pose, neutral_targets, 420, 340),
        _axis_frame(
            frame_name="head_pitch_up",
            neutral_pose=neutral_pose,
            servo_targets=neutral_targets,
            joint_plans=joint_plans,
            overrides={
                "head_pitch_pair_a": joint_plans["head_pitch_pair_a"].target_high,
                "head_pitch_pair_b": joint_plans["head_pitch_pair_b"].target_low,
            },
            pose_overrides={"head_pitch": 0.9},
            duration_ms=560,
            hold_ms=320,
        ),
        _axis_frame(
            frame_name="head_pitch_down",
            neutral_pose=neutral_pose,
            servo_targets=neutral_targets,
            joint_plans=joint_plans,
            overrides={
                "head_pitch_pair_a": joint_plans["head_pitch_pair_a"].target_low,
                "head_pitch_pair_b": joint_plans["head_pitch_pair_b"].target_high,
            },
            pose_overrides={"head_pitch": -0.9},
            duration_ms=560,
            hold_ms=320,
        ),
        _frame("head_pitch_center", neutral_pose, neutral_targets, 420, 340),
        _axis_frame(
            frame_name="head_roll_right",
            neutral_pose=neutral_pose,
            servo_targets=neutral_targets,
            joint_plans=joint_plans,
            overrides={"head_pitch_pair_a": joint_plans["head_pitch_pair_a"].target_high},
            pose_overrides={"head_roll": 0.9},
            duration_ms=520,
            hold_ms=320,
        ),
        _frame("head_roll_center_right", neutral_pose, neutral_targets, 400, 300),
        _axis_frame(
            frame_name="head_roll_left",
            neutral_pose=neutral_pose,
            servo_targets=neutral_targets,
            joint_plans=joint_plans,
            overrides={"head_pitch_pair_b": joint_plans["head_pitch_pair_b"].target_low},
            pose_overrides={"head_roll": -0.9},
            duration_ms=520,
            hold_ms=320,
        ),
        _frame("head_roll_center_left", neutral_pose, neutral_targets, 400, 300),
        _axis_frame(
            frame_name="eye_yaw_left",
            neutral_pose=neutral_pose,
            servo_targets=neutral_targets,
            joint_plans=joint_plans,
            overrides={"eye_yaw": joint_plans["eye_yaw"].target_low},
            pose_overrides={"eye_yaw": -0.88},
            duration_ms=520,
            hold_ms=300,
        ),
        _axis_frame(
            frame_name="eye_yaw_right",
            neutral_pose=neutral_pose,
            servo_targets=neutral_targets,
            joint_plans=joint_plans,
            overrides={"eye_yaw": joint_plans["eye_yaw"].target_high},
            pose_overrides={"eye_yaw": 0.88},
            duration_ms=520,
            hold_ms=300,
        ),
        _frame("eye_yaw_center", neutral_pose, neutral_targets, 380, 280),
        _axis_frame(
            frame_name="eye_pitch_up",
            neutral_pose=neutral_pose,
            servo_targets=neutral_targets,
            joint_plans=joint_plans,
            overrides={"eye_pitch": joint_plans["eye_pitch"].target_high},
            pose_overrides={"eye_pitch": 0.88},
            duration_ms=520,
            hold_ms=300,
        ),
        _axis_frame(
            frame_name="eye_pitch_down",
            neutral_pose=neutral_pose,
            servo_targets=neutral_targets,
            joint_plans=joint_plans,
            overrides={"eye_pitch": joint_plans["eye_pitch"].target_low},
            pose_overrides={"eye_pitch": -0.88},
            duration_ms=520,
            hold_ms=300,
        ),
        _frame("eye_pitch_center", neutral_pose, neutral_targets, 380, 280),
        _axis_frame(
            frame_name="upper_lid_left_open",
            neutral_pose=neutral_pose,
            servo_targets=neutral_targets,
            joint_plans=joint_plans,
            overrides={"upper_lid_left": _target_for_label(joint_plans["upper_lid_left"], "open")},
            pose_overrides={"upper_lid_left_open": min(1.0, neutral_pose.upper_lid_left_open + 0.24)},
            duration_ms=480,
            hold_ms=300,
        ),
        _axis_frame(
            frame_name="upper_lid_left_close",
            neutral_pose=neutral_pose,
            servo_targets=neutral_targets,
            joint_plans=joint_plans,
            overrides={"upper_lid_left": _target_for_label(joint_plans["upper_lid_left"], "close")},
            pose_overrides={"upper_lid_left_open": max(0.0, neutral_pose.upper_lid_left_open - 0.34)},
            duration_ms=480,
            hold_ms=300,
        ),
        _frame("upper_lid_left_center", neutral_pose, neutral_targets, 360, 220),
        _axis_frame(
            frame_name="upper_lid_right_open",
            neutral_pose=neutral_pose,
            servo_targets=neutral_targets,
            joint_plans=joint_plans,
            overrides={"upper_lid_right": _target_for_label(joint_plans["upper_lid_right"], "open")},
            pose_overrides={"upper_lid_right_open": min(1.0, neutral_pose.upper_lid_right_open + 0.24)},
            duration_ms=480,
            hold_ms=300,
        ),
        _axis_frame(
            frame_name="upper_lid_right_close",
            neutral_pose=neutral_pose,
            servo_targets=neutral_targets,
            joint_plans=joint_plans,
            overrides={"upper_lid_right": _target_for_label(joint_plans["upper_lid_right"], "close")},
            pose_overrides={"upper_lid_right_open": max(0.0, neutral_pose.upper_lid_right_open - 0.34)},
            duration_ms=480,
            hold_ms=300,
        ),
        _frame("upper_lid_right_center", neutral_pose, neutral_targets, 360, 220),
        _axis_frame(
            frame_name="lower_lid_left_open",
            neutral_pose=neutral_pose,
            servo_targets=neutral_targets,
            joint_plans=joint_plans,
            overrides={"lower_lid_left": _target_for_label(joint_plans["lower_lid_left"], "open")},
            pose_overrides={"lower_lid_left_open": min(1.0, neutral_pose.lower_lid_left_open + 0.2)},
            duration_ms=460,
            hold_ms=280,
        ),
        _axis_frame(
            frame_name="lower_lid_left_close",
            neutral_pose=neutral_pose,
            servo_targets=neutral_targets,
            joint_plans=joint_plans,
            overrides={"lower_lid_left": _target_for_label(joint_plans["lower_lid_left"], "close")},
            pose_overrides={"lower_lid_left_open": max(0.0, neutral_pose.lower_lid_left_open - 0.26)},
            duration_ms=460,
            hold_ms=280,
        ),
        _frame("lower_lid_left_center", neutral_pose, neutral_targets, 360, 200),
        _axis_frame(
            frame_name="lower_lid_right_open",
            neutral_pose=neutral_pose,
            servo_targets=neutral_targets,
            joint_plans=joint_plans,
            overrides={"lower_lid_right": _target_for_label(joint_plans["lower_lid_right"], "open")},
            pose_overrides={"lower_lid_right_open": min(1.0, neutral_pose.lower_lid_right_open + 0.2)},
            duration_ms=460,
            hold_ms=280,
        ),
        _axis_frame(
            frame_name="lower_lid_right_close",
            neutral_pose=neutral_pose,
            servo_targets=neutral_targets,
            joint_plans=joint_plans,
            overrides={"lower_lid_right": _target_for_label(joint_plans["lower_lid_right"], "close")},
            pose_overrides={"lower_lid_right_open": max(0.0, neutral_pose.lower_lid_right_open - 0.26)},
            duration_ms=460,
            hold_ms=280,
        ),
        _frame("lower_lid_right_center", neutral_pose, neutral_targets, 360, 200),
        _axis_frame(
            frame_name="brow_left_raise",
            neutral_pose=neutral_pose,
            servo_targets=neutral_targets,
            joint_plans=joint_plans,
            overrides={"brow_left": _target_for_label(joint_plans["brow_left"], "raise")},
            pose_overrides={"brow_raise_left": min(1.0, neutral_pose.brow_raise_left + 0.3)},
            duration_ms=500,
            hold_ms=300,
        ),
        _axis_frame(
            frame_name="brow_left_lower",
            neutral_pose=neutral_pose,
            servo_targets=neutral_targets,
            joint_plans=joint_plans,
            overrides={"brow_left": _target_for_label(joint_plans["brow_left"], "lower")},
            pose_overrides={"brow_raise_left": max(0.0, neutral_pose.brow_raise_left - 0.28)},
            duration_ms=500,
            hold_ms=300,
        ),
        _frame("brow_left_center", neutral_pose, neutral_targets, 360, 220),
        _axis_frame(
            frame_name="brow_right_raise",
            neutral_pose=neutral_pose,
            servo_targets=neutral_targets,
            joint_plans=joint_plans,
            overrides={"brow_right": _target_for_label(joint_plans["brow_right"], "raise")},
            pose_overrides={"brow_raise_right": min(1.0, neutral_pose.brow_raise_right + 0.3)},
            duration_ms=500,
            hold_ms=300,
        ),
        _axis_frame(
            frame_name="brow_right_lower",
            neutral_pose=neutral_pose,
            servo_targets=neutral_targets,
            joint_plans=joint_plans,
            overrides={"brow_right": _target_for_label(joint_plans["brow_right"], "lower")},
            pose_overrides={"brow_raise_right": max(0.0, neutral_pose.brow_raise_right - 0.28)},
            duration_ms=500,
            hold_ms=300,
        ),
        _frame("brow_right_center", neutral_pose, neutral_targets, 360, 220),
        _combined_expression_frame(
            frame_name="expressive_warm_right",
            neutral_pose=neutral_pose,
            servo_targets=neutral_targets,
            joint_plans=joint_plans,
            labeled_targets={
                "head_yaw": ("right", 0.45),
                "eye_yaw": ("right", 0.28),
                "eye_pitch": ("up", 0.16),
                "brow_left": ("raise", 0.52),
                "brow_right": ("raise", 0.48),
                "upper_lid_left": ("open", 0.36),
                "upper_lid_right": ("open", 0.36),
            },
            pose_overrides={
                "head_yaw": 0.42,
                "head_pitch": 0.12,
                "eye_yaw": 0.24,
                "eye_pitch": 0.12,
                "upper_lid_left_open": min(1.0, neutral_pose.upper_lid_left_open + 0.16),
                "upper_lid_right_open": min(1.0, neutral_pose.upper_lid_right_open + 0.16),
                "brow_raise_left": min(1.0, neutral_pose.brow_raise_left + 0.18),
                "brow_raise_right": min(1.0, neutral_pose.brow_raise_right + 0.18),
            },
            duration_ms=620,
            hold_ms=420,
        ),
        _combined_expression_frame(
            frame_name="expressive_curious_left",
            neutral_pose=neutral_pose,
            servo_targets=neutral_targets,
            joint_plans=joint_plans,
            labeled_targets={
                "head_yaw": ("left", 0.52),
                "head_pitch_pair_a": ("up", 0.16),
                "head_pitch_pair_b": ("up", 0.16),
                "eye_yaw": ("left", 0.36),
                "eye_pitch": ("up", 0.36),
                "brow_left": ("raise", 0.62),
                "brow_right": ("raise", 0.54),
                "upper_lid_left": ("open", 0.26),
                "upper_lid_right": ("open", 0.26),
            },
            pose_overrides={
                "head_yaw": -0.46,
                "head_pitch": 0.18,
                "head_roll": -0.16,
                "eye_yaw": -0.28,
                "eye_pitch": 0.26,
                "upper_lid_left_open": min(1.0, neutral_pose.upper_lid_left_open + 0.12),
                "upper_lid_right_open": min(1.0, neutral_pose.upper_lid_right_open + 0.12),
                "brow_raise_left": min(1.0, neutral_pose.brow_raise_left + 0.24),
                "brow_raise_right": min(1.0, neutral_pose.brow_raise_right + 0.2),
            },
            duration_ms=680,
            hold_ms=360,
        ),
        _combined_expression_frame(
            frame_name="expressive_focused_center",
            neutral_pose=neutral_pose,
            servo_targets=neutral_targets,
            joint_plans=joint_plans,
            labeled_targets={
                "eye_pitch": ("down", 0.32),
                "brow_left": ("lower", 0.26),
                "brow_right": ("lower", 0.24),
                "upper_lid_left": ("close", 0.18),
                "upper_lid_right": ("close", 0.18),
            },
            pose_overrides={
                "head_pitch": 0.08,
                "eye_pitch": -0.22,
                "upper_lid_left_open": max(0.0, neutral_pose.upper_lid_left_open - 0.1),
                "upper_lid_right_open": max(0.0, neutral_pose.upper_lid_right_open - 0.1),
                "brow_raise_left": max(0.0, neutral_pose.brow_raise_left - 0.12),
                "brow_raise_right": max(0.0, neutral_pose.brow_raise_right - 0.12),
            },
            duration_ms=620,
            hold_ms=380,
        ),
        _axis_frame(
            frame_name="accent_blink_raise",
            neutral_pose=neutral_pose,
            servo_targets=neutral_targets,
            joint_plans=joint_plans,
            overrides={
                "upper_lid_left": _target_for_label(joint_plans["upper_lid_left"], "close"),
                "upper_lid_right": _target_for_label(joint_plans["upper_lid_right"], "close"),
                "lower_lid_left": _target_for_label(joint_plans["lower_lid_left"], "close"),
                "lower_lid_right": _target_for_label(joint_plans["lower_lid_right"], "close"),
                "brow_left": _target_for_label(joint_plans["brow_left"], "raise"),
                "brow_right": _target_for_label(joint_plans["brow_right"], "raise"),
            },
            pose_overrides={
                "upper_lid_left_open": max(0.0, neutral_pose.upper_lid_left_open - 0.34),
                "upper_lid_right_open": max(0.0, neutral_pose.upper_lid_right_open - 0.34),
                "lower_lid_left_open": max(0.0, neutral_pose.lower_lid_left_open - 0.18),
                "lower_lid_right_open": max(0.0, neutral_pose.lower_lid_right_open - 0.18),
                "brow_raise_left": min(1.0, neutral_pose.brow_raise_left + 0.26),
                "brow_raise_right": min(1.0, neutral_pose.brow_raise_right + 0.26),
            },
            duration_ms=360,
            hold_ms=260,
        ),
        _axis_frame(
            frame_name="accent_recover",
            neutral_pose=neutral_pose,
            servo_targets=neutral_targets,
            joint_plans=joint_plans,
            overrides=neutral_targets,
            pose_overrides={},
            duration_ms=420,
            hold_ms=340,
        ),
        friendly.model_copy(update={"frame_name": friendly.frame_name or "friendly_settle"}, deep=True),
    ]


def _investor_head_yaw_v3_frames(
    *,
    neutral_pose: BodyPose,
    neutral_targets: dict[str, int],
    joint_plans: dict[str, RangeDemoJointPlan],
) -> list[CompiledBodyFrame]:
    head_yaw = joint_plans["head_yaw"]
    return _bidirectional_axis_sequence_frames(
        neutral_pose=neutral_pose,
        neutral_targets=neutral_targets,
        joint_plans=joint_plans,
        low_name="left",
        high_name="right",
        low_overrides={"head_yaw": head_yaw.raw_min},
        high_overrides={"head_yaw": head_yaw.raw_max},
        low_pose_overrides={"head_yaw": -0.98},
        high_pose_overrides={"head_yaw": 0.98},
        low_max_frame_name="rotate_left_max",
        low_center_frame_name="rotate_left_center",
        high_max_frame_name="rotate_right_max",
        high_center_frame_name="rotate_right_center",
    )


_SERVO_LIMIT_SEQUENCE_ORDER = (
    "head_yaw",
    "head_pitch_pair_a",
    "head_pitch_pair_b",
    "eye_yaw",
    "eye_pitch",
    "upper_lid_left",
    "upper_lid_right",
    "lower_lid_left",
    "lower_lid_right",
    "brow_left",
    "brow_right",
)


def _servo_limit_sequence_frames(
    *,
    neutral_pose: BodyPose,
    neutral_targets: dict[str, int],
    joint_plans: dict[str, RangeDemoJointPlan],
) -> list[CompiledBodyFrame]:
    frames = [
        _frame("neutral_settle", neutral_pose, neutral_targets, 1400, 900),
    ]
    for joint_name in _SERVO_LIMIT_SEQUENCE_ORDER:
        plan = joint_plans.get(joint_name)
        if plan is None:
            continue
        frames.append(_frame(f"{joint_name}_pre_min_hold", neutral_pose, neutral_targets, 700, 700))
        frames.append(
            _axis_frame(
                frame_name=f"{joint_name}_raw_min",
                neutral_pose=neutral_pose,
                servo_targets=neutral_targets,
                joint_plans=joint_plans,
                overrides={joint_name: plan.raw_min},
                pose_overrides=_servo_limit_pose_overrides(plan, limit="raw_min", neutral_pose=neutral_pose),
                duration_ms=1300,
                hold_ms=1200,
            )
        )
        frames.append(_frame(f"{joint_name}_between_hold", neutral_pose, neutral_targets, 900, 800))
        frames.append(
            _axis_frame(
                frame_name=f"{joint_name}_raw_max",
                neutral_pose=neutral_pose,
                servo_targets=neutral_targets,
                joint_plans=joint_plans,
                overrides={joint_name: plan.raw_max},
                pose_overrides=_servo_limit_pose_overrides(plan, limit="raw_max", neutral_pose=neutral_pose),
                duration_ms=1300,
                hold_ms=1200,
            )
        )
        frames.append(_frame(f"{joint_name}_neutral", neutral_pose, neutral_targets, 1000, 900))
    frames.append(_frame("neutral_complete", neutral_pose, neutral_targets, 1400, 900))
    return frames


def _servo_limit_pose_overrides(
    plan: RangeDemoJointPlan,
    *,
    limit: str,
    neutral_pose: BodyPose,
) -> dict[str, float]:
    if limit == "raw_min":
        label = plan.control_label_low
        direction = -1.0
    else:
        label = plan.control_label_high
        direction = 1.0

    if plan.joint_name == "head_yaw":
        return {"head_yaw": 0.98 * direction}
    if plan.joint_name in {"head_pitch_pair_a", "head_pitch_pair_b"}:
        return {"head_roll": 0.82 * direction}
    if plan.joint_name == "eye_yaw":
        return {"eye_yaw": 0.98 * direction}
    if plan.joint_name == "eye_pitch":
        return {"eye_pitch": 0.98 * direction}

    if plan.joint_name.startswith("upper_lid_"):
        field_name = f"{plan.joint_name}_open"
        return {field_name: 1.0 if label == "open" else 0.0}
    if plan.joint_name.startswith("lower_lid_"):
        field_name = f"{plan.joint_name}_open"
        return {field_name: 1.0 if label == "open" else 0.0}
    if plan.joint_name.startswith("brow_"):
        suffix = plan.joint_name.removeprefix("brow_")
        field_name = f"brow_raise_{suffix}"
        return {field_name: 1.0 if label == "raise" else 0.0}
    return {}


def _bidirectional_axis_sequence_frames(
    *,
    neutral_pose: BodyPose,
    neutral_targets: dict[str, int],
    joint_plans: dict[str, RangeDemoJointPlan],
    low_name: str,
    high_name: str,
    low_overrides: dict[str, int],
    high_overrides: dict[str, int],
    low_pose_overrides: dict[str, float],
    high_pose_overrides: dict[str, float],
    low_max_frame_name: str | None = None,
    low_center_frame_name: str | None = None,
    high_max_frame_name: str | None = None,
    high_center_frame_name: str | None = None,
    include_low_sweep_from_high: bool = True,
    include_high_sweep_from_low: bool = True,
    timing: RangeDemoTimingProfile = _POST_V3_TIMING,
) -> list[CompiledBodyFrame]:
    frames = [
        _frame(
            "neutral_settle",
            neutral_pose,
            neutral_targets,
            timing.neutral_settle_duration_ms,
            timing.neutral_settle_hold_ms,
        ),
        _axis_frame(
            frame_name=low_max_frame_name or f"{low_name}_max",
            neutral_pose=neutral_pose,
            servo_targets=neutral_targets,
            joint_plans=joint_plans,
            overrides=low_overrides,
            pose_overrides=low_pose_overrides,
            duration_ms=timing.endpoint_duration_ms,
            hold_ms=timing.endpoint_hold_ms,
        ),
        _frame(
            low_center_frame_name or f"{low_name}_center",
            neutral_pose,
            neutral_targets,
            timing.center_duration_ms,
            timing.center_hold_ms,
        ),
        _axis_frame(
            frame_name=high_max_frame_name or f"{high_name}_max",
            neutral_pose=neutral_pose,
            servo_targets=neutral_targets,
            joint_plans=joint_plans,
            overrides=high_overrides,
            pose_overrides=high_pose_overrides,
            duration_ms=timing.endpoint_duration_ms,
            hold_ms=timing.endpoint_hold_ms,
        ),
        _frame(
            high_center_frame_name or f"{high_name}_center",
            neutral_pose,
            neutral_targets,
            timing.center_duration_ms,
            timing.center_hold_ms,
        ),
    ]
    if include_low_sweep_from_high:
        frames.extend(
            [
                _axis_frame(
                    frame_name=f"sweep_{low_name}_prep_{high_name}",
                    neutral_pose=neutral_pose,
                    servo_targets=neutral_targets,
                    joint_plans=joint_plans,
                    overrides=high_overrides,
                    pose_overrides=high_pose_overrides,
                    duration_ms=timing.sweep_prep_duration_ms,
                    hold_ms=timing.sweep_prep_hold_ms,
                ),
                _axis_frame(
                    frame_name=f"sweep_{low_name}_max",
                    neutral_pose=neutral_pose,
                    servo_targets=neutral_targets,
                    joint_plans=joint_plans,
                    overrides=low_overrides,
                    pose_overrides=low_pose_overrides,
                    duration_ms=timing.sweep_endpoint_duration_ms,
                    hold_ms=timing.sweep_endpoint_hold_ms,
                ),
                _frame(
                    f"sweep_{low_name}_center",
                    neutral_pose,
                    neutral_targets,
                    timing.center_duration_ms,
                    timing.center_hold_ms,
                ),
            ]
        )
    if include_high_sweep_from_low:
        frames.extend(
            [
                _axis_frame(
                    frame_name=f"sweep_{high_name}_prep_{low_name}",
                    neutral_pose=neutral_pose,
                    servo_targets=neutral_targets,
                    joint_plans=joint_plans,
                    overrides=low_overrides,
                    pose_overrides=low_pose_overrides,
                    duration_ms=timing.sweep_prep_duration_ms,
                    hold_ms=timing.sweep_prep_hold_ms,
                ),
                _axis_frame(
                    frame_name=f"sweep_{high_name}_max",
                    neutral_pose=neutral_pose,
                    servo_targets=neutral_targets,
                    joint_plans=joint_plans,
                    overrides=high_overrides,
                    pose_overrides=high_pose_overrides,
                    duration_ms=timing.sweep_endpoint_duration_ms,
                    hold_ms=timing.sweep_endpoint_hold_ms,
                ),
                _frame(
                    f"sweep_{high_name}_center",
                    neutral_pose,
                    neutral_targets,
                    timing.final_neutral_duration_ms,
                    timing.final_neutral_hold_ms,
                ),
            ]
        )
    elif frames[-1].frame_name != "neutral_settle":
        frames[-1] = _frame(
            frames[-1].frame_name,
            neutral_pose,
            neutral_targets,
            timing.final_neutral_duration_ms,
            timing.final_neutral_hold_ms,
        )
    return frames


def _open_close_sequence_frames(
    *,
    neutral_pose: BodyPose,
    neutral_targets: dict[str, int],
    joint_plans: dict[str, RangeDemoJointPlan],
    close_name: str,
    open_name: str,
    close_overrides: dict[str, int],
    open_overrides: dict[str, int],
    close_pose_overrides: dict[str, float],
    open_pose_overrides: dict[str, float],
    timing: RangeDemoTimingProfile = _POST_V3_TIMING,
) -> list[CompiledBodyFrame]:
    return [
        _frame(
            "neutral_settle",
            neutral_pose,
            neutral_targets,
            timing.neutral_settle_duration_ms,
            timing.neutral_settle_hold_ms,
        ),
        _axis_frame(
            frame_name=f"{close_name}_max",
            neutral_pose=neutral_pose,
            servo_targets=neutral_targets,
            joint_plans=joint_plans,
            overrides=close_overrides,
            pose_overrides=close_pose_overrides,
            duration_ms=timing.endpoint_duration_ms,
            hold_ms=timing.endpoint_hold_ms,
        ),
        _frame(
            f"{close_name}_center",
            neutral_pose,
            neutral_targets,
            timing.center_duration_ms,
            timing.center_hold_ms,
        ),
        _axis_frame(
            frame_name=f"{open_name}_max",
            neutral_pose=neutral_pose,
            servo_targets=neutral_targets,
            joint_plans=joint_plans,
            overrides=open_overrides,
            pose_overrides=open_pose_overrides,
            duration_ms=timing.endpoint_duration_ms,
            hold_ms=timing.endpoint_hold_ms,
        ),
        _frame(
            f"{open_name}_center",
            neutral_pose,
            neutral_targets,
            timing.final_neutral_duration_ms,
            timing.final_neutral_hold_ms,
        ),
    ]


def _blink_sequence_frames(
    *,
    neutral_pose: BodyPose,
    neutral_targets: dict[str, int],
    joint_plans: dict[str, RangeDemoJointPlan],
    timing: RangeDemoTimingProfile = _POST_V3_TIMING,
) -> list[CompiledBodyFrame]:
    close_overrides = {
        "upper_lid_left": _target_for_label(joint_plans["upper_lid_left"], "close"),
        "upper_lid_right": _target_for_label(joint_plans["upper_lid_right"], "close"),
        "lower_lid_left": _target_for_label(joint_plans["lower_lid_left"], "close"),
        "lower_lid_right": _target_for_label(joint_plans["lower_lid_right"], "close"),
    }
    close_pose_overrides = {
        "upper_lid_left_open": 0.0,
        "upper_lid_right_open": 0.0,
        "lower_lid_left_open": 0.0,
        "lower_lid_right_open": 0.0,
    }
    return [
        _frame(
            "neutral_settle",
            neutral_pose,
            neutral_targets,
            timing.neutral_settle_duration_ms,
            timing.neutral_settle_hold_ms,
        ),
        _axis_frame(
            frame_name="full_blink_close",
            neutral_pose=neutral_pose,
            servo_targets=neutral_targets,
            joint_plans=joint_plans,
            overrides=close_overrides,
            pose_overrides=close_pose_overrides,
            duration_ms=timing.endpoint_duration_ms,
            hold_ms=timing.endpoint_hold_ms,
        ),
        _frame(
            "full_blink_center",
            neutral_pose,
            neutral_targets,
            timing.center_duration_ms,
            timing.center_hold_ms,
        ),
        _axis_frame(
            frame_name="double_blink_close_1",
            neutral_pose=neutral_pose,
            servo_targets=neutral_targets,
            joint_plans=joint_plans,
            overrides=close_overrides,
            pose_overrides=close_pose_overrides,
            duration_ms=timing.endpoint_duration_ms,
            hold_ms=timing.endpoint_hold_ms,
        ),
        _frame(
            "double_blink_center_1",
            neutral_pose,
            neutral_targets,
            timing.center_duration_ms,
            timing.center_hold_ms,
        ),
        _axis_frame(
            frame_name="double_blink_close_2",
            neutral_pose=neutral_pose,
            servo_targets=neutral_targets,
            joint_plans=joint_plans,
            overrides=close_overrides,
            pose_overrides=close_pose_overrides,
            duration_ms=timing.endpoint_duration_ms,
            hold_ms=timing.endpoint_hold_ms,
        ),
        _frame(
            "double_blink_center_2",
            neutral_pose,
            neutral_targets,
            timing.final_neutral_duration_ms,
            timing.final_neutral_hold_ms,
        ),
    ]


def _envelope_for_joint(preset: RangeDemoPreset, joint_name: str) -> RangeDemoEnvelope:
    if joint_name == "head_yaw":
        return preset.head_yaw
    if joint_name in {"head_pitch_pair_a", "head_pitch_pair_b"}:
        return preset.head_pitch_pair
    if joint_name in {"upper_lid_left", "upper_lid_right", "lower_lid_left", "lower_lid_right"}:
        return preset.lids
    if joint_name in {"brow_left", "brow_right"}:
        return preset.brows
    if joint_name == "eye_yaw":
        return preset.eye_yaw
    if joint_name == "eye_pitch":
        return preset.eye_pitch
    return preset.head_roll


def _control_labels(positive_direction: str) -> tuple[str, str]:
    return _POSITIVE_DIRECTION_LABELS.get(positive_direction, ("low", "high"))


def _target_for_label(plan: RangeDemoJointPlan, label: str) -> int:
    normalized = label.strip().lower()
    if normalized == plan.control_label_low:
        return plan.target_low
    if normalized == plan.control_label_high:
        return plan.target_high
    raise ValueError(f"unsupported_range_demo_label:{plan.joint_name}:{label}")


def _blend_target(plan: RangeDemoJointPlan, label: str, fraction: float) -> int:
    fraction = max(0.0, min(1.0, float(fraction)))
    labeled_target = _target_for_label(plan, label)
    return int(round(plan.neutral + (labeled_target - plan.neutral) * fraction))


def _frame(
    frame_name: str,
    pose: BodyPose,
    servo_targets: dict[str, int],
    duration_ms: int,
    hold_ms: int,
) -> CompiledBodyFrame:
    return CompiledBodyFrame(
        frame_name=frame_name,
        pose=pose.model_copy(deep=True),
        servo_targets=dict(servo_targets),
        duration_ms=duration_ms,
        hold_ms=hold_ms,
        compiler_notes=[f"range_demo_frame:{frame_name}"],
    )


def _axis_frame(
    *,
    frame_name: str,
    neutral_pose: BodyPose,
    servo_targets: dict[str, int],
    joint_plans: dict[str, RangeDemoJointPlan],
    overrides: dict[str, int],
    pose_overrides: dict[str, float],
    duration_ms: int,
    hold_ms: int,
) -> CompiledBodyFrame:
    resolved_targets = dict(servo_targets)
    resolved_targets.update({name: int(value) for name, value in overrides.items() if name in joint_plans})
    pose = apply_pose_overrides(neutral_pose, **pose_overrides)
    return _frame(
        frame_name=frame_name,
        pose=pose,
        servo_targets=resolved_targets,
        duration_ms=duration_ms,
        hold_ms=hold_ms,
    )


def _combined_expression_frame(
    *,
    frame_name: str,
    neutral_pose: BodyPose,
    servo_targets: dict[str, int],
    joint_plans: dict[str, RangeDemoJointPlan],
    labeled_targets: dict[str, tuple[str, float]],
    pose_overrides: dict[str, float],
    duration_ms: int,
    hold_ms: int,
) -> CompiledBodyFrame:
    resolved_targets = dict(servo_targets)
    for joint_name, (label, fraction) in labeled_targets.items():
        plan = joint_plans.get(joint_name)
        if plan is None:
            continue
        resolved_targets[joint_name] = _blend_target(plan, label, fraction)
    pose = apply_pose_overrides(neutral_pose, **pose_overrides)
    return _frame(
        frame_name=frame_name,
        pose=pose,
        servo_targets=resolved_targets,
        duration_ms=duration_ms,
        hold_ms=hold_ms,
    )


__all__ = [
    "RangeDemoEnvelope",
    "RangeDemoJointPlan",
    "RangeDemoMotionControlOverride",
    "RangeDemoPlan",
    "RangeDemoPreset",
    "RangeDemoSequenceDefinition",
    "available_range_demo_presets",
    "available_range_demo_sequences",
    "build_range_demo_plan",
    "range_demo_preset",
    "range_demo_sequence",
]
