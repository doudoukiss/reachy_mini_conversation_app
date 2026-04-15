from __future__ import annotations

import pytest

from embodied_stack.body import SemanticBodyCompiler, default_head_profile, expression_pose
from embodied_stack.body import calibration as calibration_module
from embodied_stack.body.range_demo import build_range_demo_plan


def _saved_calibration():
    profile = default_head_profile()
    calibration = calibration_module.calibration_from_profile(profile, calibration_kind="saved")
    for joint in calibration.joint_records:
        joint.mirrored_direction_confirmed = True
    return profile, calibration


def _friendly_frame(profile, calibration):
    compiler = SemanticBodyCompiler(profile=profile, calibration=calibration)
    neutral_pose = compiler.neutral_pose()
    friendly = compiler.compile_frame(
        expression_pose("friendly", intensity=0.58, neutral_pose=neutral_pose),
        frame_name="friendly_settle",
        animation_name="body_range_demo:investor_show_joint_envelope_v1",
        duration_ms=620,
        hold_ms=320,
        semantic_name="friendly",
    )
    return neutral_pose, friendly


def _neutral_targets(plan):
    return {joint_name: item.neutral for joint_name, item in plan.joint_plans.items()}


def _changed_joints(frame, neutral_targets):
    return {
        joint_name
        for joint_name, target in frame.servo_targets.items()
        if target != neutral_targets[joint_name]
    }


def test_range_demo_plan_exercises_all_enabled_joints_and_stays_within_bounds() -> None:
    profile, calibration = _saved_calibration()
    neutral_pose, friendly = _friendly_frame(profile, calibration)
    plan = build_range_demo_plan(
        profile=profile,
        calibration=calibration,
        preset_name="investor_show_joint_envelope_v1",
        neutral_pose=neutral_pose,
        friendly_frame=friendly,
        calibration_source_path="runtime/calibrations/robot_head_live_v1.json",
    )

    enabled_joints = {joint.joint_name for joint in profile.joints if joint.enabled}
    assert set(plan.joint_plans) == enabled_joints
    assert len(plan.joint_plans) == 11
    assert plan.using_profile_fallback is False
    assert plan.calibration_kind == "saved"
    assert plan.animation.frames[0].frame_name == "neutral_settle"
    assert plan.animation.frames[-1].frame_name == "friendly_settle"
    assert len(plan.animation.frames) == 41
    assert plan.animation.total_duration_ms >= 32000
    assert plan.usable_range_audit is not None

    for joint_name, joint_plan in plan.joint_plans.items():
        assert joint_plan.raw_min <= joint_plan.target_low <= joint_plan.raw_max
        assert joint_plan.raw_min <= joint_plan.target_high <= joint_plan.raw_max
        assert joint_plan.usable_min <= joint_plan.target_low <= joint_plan.usable_max
        assert joint_plan.usable_min <= joint_plan.target_high <= joint_plan.usable_max
        assert joint_plan.target_low <= joint_plan.target_high


def test_range_demo_plan_has_distinct_single_servo_lid_and_brow_beats() -> None:
    profile, calibration = _saved_calibration()
    neutral_pose, friendly = _friendly_frame(profile, calibration)
    plan = build_range_demo_plan(
        profile=profile,
        calibration=calibration,
        preset_name="investor_show_joint_envelope_v1",
        neutral_pose=neutral_pose,
        friendly_frame=friendly,
    )

    frame_names = [frame.frame_name for frame in plan.animation.frames]
    assert "upper_lid_left_open" in frame_names
    assert "upper_lid_right_open" in frame_names
    assert "lower_lid_left_open" in frame_names
    assert "lower_lid_right_open" in frame_names
    assert "brow_left_raise" in frame_names
    assert "brow_right_raise" in frame_names
    assert "upper_lids_open" not in frame_names
    assert "lower_lids_open" not in frame_names
    assert "brows_raise" not in frame_names
    assert "expressive_warm_right" in frame_names
    assert "expressive_curious_left" in frame_names
    assert "expressive_focused_center" in frame_names


def test_range_demo_plan_uses_profile_fallback_when_saved_calibration_is_missing() -> None:
    profile = default_head_profile()
    compiler = SemanticBodyCompiler(profile=profile, calibration=calibration_module.calibration_from_profile(profile, calibration_kind="template"))
    plan = build_range_demo_plan(
        profile=profile,
        calibration=None,
        preset_name="investor_show_joint_envelope_v1",
        neutral_pose=compiler.neutral_pose(),
        calibration_source_path=None,
    )

    assert plan.using_profile_fallback is True
    assert plan.calibration_kind == "profile_fallback"
    for joint in profile.joints:
        if not joint.enabled:
            continue
        joint_plan = plan.joint_plans[joint.joint_name]
        assert joint_plan.raw_min == joint.raw_min
        assert joint_plan.raw_max == joint.raw_max
        assert joint_plan.neutral == joint.neutral


def test_range_demo_plan_accepts_captured_live_calibration() -> None:
    profile = default_head_profile()
    calibration = calibration_module.calibration_from_profile(profile, calibration_kind="captured")
    calibration.joint_records[0].neutral = 2096
    neutral_pose, friendly = _friendly_frame(profile, calibration)
    plan = build_range_demo_plan(
        profile=profile,
        calibration=calibration,
        preset_name="investor_show_joint_envelope_v1",
        neutral_pose=neutral_pose,
        friendly_frame=friendly,
        calibration_source_path="runtime/calibrations/robot_head_live_v1.json",
    )

    assert plan.using_profile_fallback is False
    assert plan.calibration_kind == "captured"
    assert plan.joint_plans["head_yaw"].neutral == 2096


def test_range_demo_roll_frames_do_not_stack_paired_pitch_axes() -> None:
    profile, calibration = _saved_calibration()
    neutral_pose, friendly = _friendly_frame(profile, calibration)
    plan = build_range_demo_plan(
        profile=profile,
        calibration=calibration,
        preset_name="investor_show_joint_envelope_v1",
        neutral_pose=neutral_pose,
        friendly_frame=friendly,
    )

    neutrals = {joint_name: item.neutral for joint_name, item in plan.joint_plans.items()}
    frames = {frame.frame_name: frame for frame in plan.animation.frames}

    pitch_up = frames["head_pitch_up"].servo_targets
    pitch_down = frames["head_pitch_down"].servo_targets
    roll_right = frames["head_roll_right"].servo_targets
    roll_left = frames["head_roll_left"].servo_targets

    assert pitch_up["head_pitch_pair_a"] != neutrals["head_pitch_pair_a"]
    assert pitch_up["head_pitch_pair_b"] != neutrals["head_pitch_pair_b"]
    assert pitch_down["head_pitch_pair_a"] != neutrals["head_pitch_pair_a"]
    assert pitch_down["head_pitch_pair_b"] != neutrals["head_pitch_pair_b"]
    assert roll_right["head_pitch_pair_a"] != neutrals["head_pitch_pair_a"]
    assert roll_right["head_pitch_pair_b"] == neutrals["head_pitch_pair_b"]
    assert roll_left["head_pitch_pair_a"] == neutrals["head_pitch_pair_a"]
    assert roll_left["head_pitch_pair_b"] != neutrals["head_pitch_pair_b"]


def test_range_demo_sequence_uses_full_limit_showcase_preset() -> None:
    profile, calibration = _saved_calibration()
    neutral_pose, friendly = _friendly_frame(profile, calibration)
    plan = build_range_demo_plan(
        profile=profile,
        calibration=calibration,
        sequence_name="servo_range_showcase_v1",
        neutral_pose=neutral_pose,
        friendly_frame=friendly,
    )

    assert plan.sequence_name == "servo_range_showcase_v1"
    assert plan.preset_name == "servo_range_showcase_joint_envelope_v1"
    assert plan.animation.total_duration_ms >= 70000
    assert plan.animation.frames[-1].frame_name == "neutral_complete"


def test_investor_head_yaw_v3_sequence_is_head_yaw_only_and_hits_raw_endpoints() -> None:
    profile, calibration = _saved_calibration()
    neutral_pose, friendly = _friendly_frame(profile, calibration)
    plan = build_range_demo_plan(
        profile=profile,
        calibration=calibration,
        sequence_name="investor_head_yaw_v3",
        neutral_pose=neutral_pose,
        friendly_frame=friendly,
    )

    assert plan.sequence_name == "investor_head_yaw_v3"
    assert plan.preset_name == "servo_range_showcase_joint_envelope_v1"
    assert plan.motion_control_override is not None
    assert plan.motion_control_override.speed == 100
    assert plan.motion_control_override.acceleration == 32

    frames = {frame.frame_name: frame for frame in plan.animation.frames}
    joint_plan = plan.joint_plans["head_yaw"]
    neutral_targets = {
        joint_name: item.neutral for joint_name, item in plan.joint_plans.items()
    }

    expected_frames = {
        "neutral_settle",
        "rotate_left_max",
        "rotate_left_center",
        "rotate_right_max",
        "rotate_right_center",
        "sweep_left_prep_right",
        "sweep_left_max",
        "sweep_left_center",
        "sweep_right_prep_left",
        "sweep_right_max",
        "sweep_right_center",
    }
    assert {frame.frame_name for frame in plan.animation.frames} == expected_frames
    assert frames["rotate_left_max"].servo_targets["head_yaw"] == joint_plan.raw_min
    assert frames["rotate_right_max"].servo_targets["head_yaw"] == joint_plan.raw_max
    assert frames["sweep_left_prep_right"].servo_targets["head_yaw"] == joint_plan.raw_max
    assert frames["sweep_left_max"].servo_targets["head_yaw"] == joint_plan.raw_min
    assert frames["sweep_right_prep_left"].servo_targets["head_yaw"] == joint_plan.raw_min
    assert frames["sweep_right_max"].servo_targets["head_yaw"] == joint_plan.raw_max
    assert frames["sweep_right_center"].servo_targets["head_yaw"] == joint_plan.neutral

    for frame in plan.animation.frames:
        for joint_name, target in frame.servo_targets.items():
            if joint_name == "head_yaw":
                continue
            assert target == neutral_targets[joint_name]


@pytest.mark.parametrize(
    ("sequence_name", "joint_name", "expected_frames"),
    [
        (
            "investor_eye_yaw_v4",
            "eye_yaw",
            {
                "neutral_settle",
                "left_max",
                "left_center",
                "right_max",
                "right_center",
                "sweep_left_prep_right",
                "sweep_left_max",
                "sweep_left_center",
                "sweep_right_prep_left",
                "sweep_right_max",
                "sweep_right_center",
            },
        ),
        (
            "investor_eye_pitch_v4",
            "eye_pitch",
            {
                "neutral_settle",
                "down_max",
                "down_center",
                "up_max",
                "up_center",
                "sweep_down_prep_up",
                "sweep_down_max",
                "sweep_down_center",
                "sweep_up_prep_down",
                "sweep_up_max",
                "sweep_up_center",
            },
        ),
    ],
)
def test_post_v3_eye_sequences_are_single_joint_atomic_range_demos(
    sequence_name: str,
    joint_name: str,
    expected_frames: set[str],
) -> None:
    profile, calibration = _saved_calibration()
    neutral_pose, friendly = _friendly_frame(profile, calibration)
    plan = build_range_demo_plan(
        profile=profile,
        calibration=calibration,
        sequence_name=sequence_name,
        neutral_pose=neutral_pose,
        friendly_frame=friendly,
    )

    neutral_targets = _neutral_targets(plan)
    assert plan.motion_control_override is not None
    assert plan.motion_control_override.speed == 100
    assert plan.motion_control_override.acceleration == 32
    assert {frame.frame_name for frame in plan.animation.frames} == expected_frames
    assert plan.animation.frames[0].servo_targets == neutral_targets
    assert plan.animation.frames[-1].servo_targets == neutral_targets
    for frame in plan.animation.frames:
        assert _changed_joints(frame, neutral_targets) in (set(), {joint_name})


def test_post_v3_lid_sequences_are_expressive_unit_atomic_range_demos() -> None:
    profile, calibration = _saved_calibration()
    neutral_pose, friendly = _friendly_frame(profile, calibration)
    both = build_range_demo_plan(
        profile=profile,
        calibration=calibration,
        sequence_name="investor_both_lids_v5",
        neutral_pose=neutral_pose,
        friendly_frame=friendly,
    )
    left = build_range_demo_plan(
        profile=profile,
        calibration=calibration,
        sequence_name="investor_left_eye_lids_v5",
        neutral_pose=neutral_pose,
        friendly_frame=friendly,
    )
    right = build_range_demo_plan(
        profile=profile,
        calibration=calibration,
        sequence_name="investor_right_eye_lids_v5",
        neutral_pose=neutral_pose,
        friendly_frame=friendly,
    )
    blink = build_range_demo_plan(
        profile=profile,
        calibration=calibration,
        sequence_name="investor_blink_v5",
        neutral_pose=neutral_pose,
        friendly_frame=friendly,
    )

    for plan in (both, left, right, blink):
        assert plan.motion_control_override is not None
        assert plan.motion_control_override.speed == 100
        assert plan.motion_control_override.acceleration == 32
        assert plan.animation.frames[0].servo_targets == _neutral_targets(plan)
        assert plan.animation.frames[-1].servo_targets == _neutral_targets(plan)

    assert {
        frame.frame_name for frame in both.animation.frames
    } == {
        "neutral_settle",
        "both_eyes_close_max",
        "both_eyes_close_center",
        "both_eyes_open_max",
        "both_eyes_open_center",
    }
    assert {
        frame.frame_name for frame in left.animation.frames
    } == {
        "neutral_settle",
        "left_eye_close_max",
        "left_eye_close_center",
        "left_eye_open_max",
        "left_eye_open_center",
    }
    assert {
        frame.frame_name for frame in right.animation.frames
    } == {
        "neutral_settle",
        "right_eye_close_max",
        "right_eye_close_center",
        "right_eye_open_max",
        "right_eye_open_center",
    }
    assert {
        frame.frame_name for frame in blink.animation.frames
    } == {
        "neutral_settle",
        "full_blink_close",
        "full_blink_center",
        "double_blink_close_1",
        "double_blink_center_1",
        "double_blink_close_2",
        "double_blink_center_2",
    }

    both_neutral = _neutral_targets(both)
    left_neutral = _neutral_targets(left)
    right_neutral = _neutral_targets(right)
    blink_neutral = _neutral_targets(blink)
    for frame in both.animation.frames:
        assert _changed_joints(frame, both_neutral) in (
            set(),
            {"upper_lid_left", "upper_lid_right", "lower_lid_left", "lower_lid_right"},
        )
    for frame in left.animation.frames:
        assert _changed_joints(frame, left_neutral) in (
            set(),
            {"upper_lid_left", "lower_lid_left"},
        )
    for frame in right.animation.frames:
        assert _changed_joints(frame, right_neutral) in (
            set(),
            {"upper_lid_right", "lower_lid_right"},
        )
    for frame in blink.animation.frames:
        assert _changed_joints(frame, blink_neutral) in (
            set(),
            {"upper_lid_left", "upper_lid_right", "lower_lid_left", "lower_lid_right"},
        )


def test_post_v3_brow_sequences_are_family_atomic_range_demos() -> None:
    profile, calibration = _saved_calibration()
    neutral_pose, friendly = _friendly_frame(profile, calibration)
    both = build_range_demo_plan(
        profile=profile,
        calibration=calibration,
        sequence_name="investor_brows_both_v6",
        neutral_pose=neutral_pose,
        friendly_frame=friendly,
    )
    left = build_range_demo_plan(
        profile=profile,
        calibration=calibration,
        sequence_name="investor_brow_left_v6",
        neutral_pose=neutral_pose,
        friendly_frame=friendly,
    )
    right = build_range_demo_plan(
        profile=profile,
        calibration=calibration,
        sequence_name="investor_brow_right_v6",
        neutral_pose=neutral_pose,
        friendly_frame=friendly,
    )

    for plan in (both, left, right):
        assert plan.motion_control_override is not None
        assert plan.motion_control_override.speed == 100
        assert plan.motion_control_override.acceleration == 32
        assert plan.animation.frames[0].servo_targets == _neutral_targets(plan)
        assert plan.animation.frames[-1].servo_targets == _neutral_targets(plan)

    both_neutral = _neutral_targets(both)
    left_neutral = _neutral_targets(left)
    right_neutral = _neutral_targets(right)
    for frame in both.animation.frames:
        assert _changed_joints(frame, both_neutral) in (set(), {"brow_left", "brow_right"})
    for frame in left.animation.frames:
        assert _changed_joints(frame, left_neutral) in (set(), {"brow_left"})
    for frame in right.animation.frames:
        assert _changed_joints(frame, right_neutral) in (set(), {"brow_right"})


def test_post_v3_neck_sequences_keep_pitch_and_tilt_separate() -> None:
    profile, calibration = _saved_calibration()
    neutral_pose, friendly = _friendly_frame(profile, calibration)
    tilt = build_range_demo_plan(
        profile=profile,
        calibration=calibration,
        sequence_name="investor_neck_tilt_v7",
        neutral_pose=neutral_pose,
        friendly_frame=friendly,
    )
    pitch = build_range_demo_plan(
        profile=profile,
        calibration=calibration,
        sequence_name="investor_neck_pitch_v7",
        neutral_pose=neutral_pose,
        friendly_frame=friendly,
    )

    for plan in (tilt, pitch):
        assert plan.motion_control_override is not None
        assert plan.motion_control_override.speed == 100
        assert plan.motion_control_override.acceleration == 32
        assert plan.animation.frames[0].servo_targets == _neutral_targets(plan)
        assert plan.animation.frames[-1].servo_targets == _neutral_targets(plan)

    tilt_neutral = _neutral_targets(tilt)
    pitch_neutral = _neutral_targets(pitch)
    for frame in tilt.animation.frames:
        assert _changed_joints(frame, tilt_neutral) in (
            set(),
            {"head_pitch_pair_a"},
            {"head_pitch_pair_b"},
        )
    for frame in pitch.animation.frames:
        assert _changed_joints(frame, pitch_neutral) in (
            set(),
            {"head_pitch_pair_a", "head_pitch_pair_b"},
        )


def test_servo_range_showcase_sequence_hits_calibrated_raw_min_and_max_for_each_joint() -> None:
    profile, calibration = _saved_calibration()
    neutral_pose, friendly = _friendly_frame(profile, calibration)
    plan = build_range_demo_plan(
        profile=profile,
        calibration=calibration,
        sequence_name="servo_range_showcase_v1",
        neutral_pose=neutral_pose,
        friendly_frame=friendly,
    )

    frames = {frame.frame_name: frame for frame in plan.animation.frames}
    for joint_name, joint_plan in plan.joint_plans.items():
        pre_min_frame = frames[f"{joint_name}_pre_min_hold"]
        raw_min_frame = frames[f"{joint_name}_raw_min"]
        raw_max_frame = frames[f"{joint_name}_raw_max"]
        between_frame = frames[f"{joint_name}_between_hold"]
        neutral_frame = frames[f"{joint_name}_neutral"]

        assert pre_min_frame.servo_targets[joint_name] == joint_plan.neutral
        assert raw_min_frame.servo_targets[joint_name] == joint_plan.raw_min
        assert raw_max_frame.servo_targets[joint_name] == joint_plan.raw_max
        assert between_frame.servo_targets[joint_name] == joint_plan.neutral
        assert neutral_frame.servo_targets[joint_name] == joint_plan.neutral


def test_range_demo_plan_falls_back_to_profile_neutral_when_saved_joint_neutral_is_suspicious() -> None:
    profile, calibration = _saved_calibration()
    for joint in calibration.joint_records:
        if joint.joint_name == "head_pitch_pair_a":
            joint.neutral = joint.raw_min
        if joint.joint_name == "head_pitch_pair_b":
            joint.neutral = joint.raw_max
    neutral_pose, friendly = _friendly_frame(profile, calibration)

    plan = build_range_demo_plan(
        profile=profile,
        calibration=calibration,
        sequence_name="servo_range_showcase_v1",
        neutral_pose=neutral_pose,
        friendly_frame=friendly,
    )

    assert plan.usable_range_audit is not None
    assert "head_pitch_pair_a" in plan.usable_range_audit.suspicious_joint_names
    assert "head_pitch_pair_b" in plan.usable_range_audit.suspicious_joint_names
    assert plan.joint_plans["head_pitch_pair_a"].planning_source == "profile_due_to_suspicious_neutral"
    assert plan.joint_plans["head_pitch_pair_b"].planning_source == "profile_due_to_suspicious_neutral"
    assert plan.joint_plans["head_pitch_pair_a"].neutral == profile.joints[1].neutral
    assert plan.joint_plans["head_pitch_pair_b"].neutral == profile.joints[2].neutral
