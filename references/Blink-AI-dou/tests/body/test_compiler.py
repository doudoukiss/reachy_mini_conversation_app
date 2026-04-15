from __future__ import annotations

from pathlib import Path

import pytest

from embodied_stack.body import SemanticBodyCompiler, build_body_driver, default_head_profile
from embodied_stack.body.compiler import StagedSequenceAccentSpec, StagedSequenceStageSpec
from embodied_stack.body.expressive_motifs import ExpressiveSequenceStepSpec
from embodied_stack.body.calibration import load_head_calibration
from embodied_stack.body.profile import load_head_profile
from embodied_stack.body.tuning import load_semantic_tuning
from embodied_stack.config import Settings
from embodied_stack.shared.contracts import (
    AnimationRequest,
    BodyPose,
    BodyState,
    GestureRequest,
    MotionEnvelope,
    RobotCommand,
    RobotMode,
    SemanticActionTuningOverride,
    SemanticTuningRecord,
)


def build_settings(tmp_path: Path, **overrides) -> Settings:
    return Settings(
        _env_file=None,
        brain_store_path=str(tmp_path / "brain_store.json"),
        demo_report_dir=str(tmp_path / "demo_runs"),
        demo_check_dir=str(tmp_path / "demo_checks"),
        episode_export_dir=str(tmp_path / "episodes"),
        shift_report_dir=str(tmp_path / "shift_reports"),
        operator_auth_token="body-test-token",
        operator_auth_runtime_file=str(tmp_path / "operator_auth.json"),
        **overrides,
    )


def test_pitch_and_roll_follow_uploaded_neck_coupling_rules() -> None:
    compiler = SemanticBodyCompiler(profile=default_head_profile())

    pitch_up_targets = compiler.compile_servo_targets(BodyPose(head_pitch=0.5))
    assert pitch_up_targets["head_pitch_pair_a"] > 2047
    assert pitch_up_targets["head_pitch_pair_b"] < 2047

    tilt_right_targets = compiler.compile_servo_targets(BodyPose(head_roll=0.4))
    assert tilt_right_targets["head_pitch_pair_a"] > 2047
    assert tilt_right_targets["head_pitch_pair_b"] == 2047

    tilt_left_targets = compiler.compile_servo_targets(BodyPose(head_roll=-0.4))
    assert tilt_left_targets["head_pitch_pair_a"] == 2047
    assert tilt_left_targets["head_pitch_pair_b"] < 2047


def test_mirrored_lids_and_brows_compile_to_opposite_raw_directions() -> None:
    compiler = SemanticBodyCompiler(profile=default_head_profile())
    targets = compiler.compile_servo_targets(
        BodyPose(
            upper_lids_open=1.0,
            lower_lids_open=1.0,
            brow_raise_left=1.0,
            brow_raise_right=1.0,
        )
    )
    joints = {joint.joint_name: joint for joint in default_head_profile().joints}

    assert targets["upper_lid_left"] > joints["upper_lid_left"].neutral
    assert targets["upper_lid_right"] < joints["upper_lid_right"].neutral
    assert targets["lower_lid_left"] < joints["lower_lid_left"].neutral
    assert targets["lower_lid_right"] > joints["lower_lid_right"].neutral
    assert targets["brow_left"] > joints["brow_left"].neutral
    assert targets["brow_right"] < joints["brow_right"].neutral


def test_neutral_uses_calibration_center_for_ratio_joints_instead_of_endstops() -> None:
    profile = load_head_profile("src/embodied_stack/body/profiles/robot_head_v1.json")
    calibration = load_head_calibration("runtime/calibrations/robot_head_live_v1.json", profile=profile)
    compiler = SemanticBodyCompiler(profile=profile, calibration=calibration)

    frame = compiler.compile_frame(compiler.neutral_pose(), semantic_name="neutral")

    assert frame.servo_targets["upper_lid_left"] == 2048
    assert frame.servo_targets["upper_lid_right"] == 2006
    assert frame.servo_targets["lower_lid_left"] == 2050
    assert frame.servo_targets["lower_lid_right"] == 2045
    assert frame.servo_targets["brow_left"] == 2094
    assert frame.servo_targets["brow_right"] == 2000

    joints = {joint.joint_name: joint for joint in profile.joints}
    for joint_name in ("upper_lid_left", "upper_lid_right", "lower_lid_left", "lower_lid_right", "brow_left", "brow_right"):
        joint = joints[joint_name]
        assert frame.servo_targets[joint_name] not in {joint.raw_min, joint.raw_max}


def test_safe_idle_stays_close_to_neutral_and_not_wide_open() -> None:
    profile = load_head_profile("src/embodied_stack/body/profiles/robot_head_v1.json")
    calibration = load_head_calibration("runtime/calibrations/robot_head_live_v1.json", profile=profile)
    compiler = SemanticBodyCompiler(profile=profile, calibration=calibration)

    neutral_frame = compiler.compile_frame(compiler.neutral_pose(), semantic_name="neutral")
    safe_idle_frame = compiler.apply_expression(BodyState(), "safe_idle").compiled_animation.frames[-1]

    assert safe_idle_frame.pose.upper_lid_left_open < neutral_frame.pose.upper_lid_left_open
    assert safe_idle_frame.pose.upper_lid_right_open < neutral_frame.pose.upper_lid_right_open
    assert safe_idle_frame.pose.brow_raise_left >= neutral_frame.pose.brow_raise_left - 0.02
    assert safe_idle_frame.pose.brow_raise_right >= neutral_frame.pose.brow_raise_right - 0.02


def test_eye_pitch_applies_upper_lid_compensation() -> None:
    compiler = SemanticBodyCompiler(profile=default_head_profile())

    look_up_frame = compiler.compile_frame(BodyPose(eye_pitch=0.8, upper_lids_open=0.7))
    look_down_frame = compiler.compile_frame(BodyPose(eye_pitch=-0.8, upper_lids_open=0.7))

    assert look_up_frame.pose.upper_lid_left_open > 0.7
    assert look_up_frame.pose.upper_lid_right_open > 0.7
    assert look_down_frame.pose.upper_lid_left_open < 0.7
    assert look_down_frame.pose.upper_lid_right_open < 0.7


def test_clamping_keeps_pose_and_targets_inside_safe_ranges() -> None:
    compiler = SemanticBodyCompiler(profile=default_head_profile())
    unclamped_pose = BodyPose.model_construct(
        head_yaw=2.0,
        head_pitch=-2.0,
        head_roll=2.0,
        eye_yaw=2.0,
        eye_pitch=-2.0,
        upper_lids_open=2.0,
        lower_lids_open=-1.0,
        upper_lid_left_open=2.0,
        upper_lid_right_open=-1.0,
        lower_lid_left_open=2.0,
        lower_lid_right_open=-1.0,
        brow_raise_left=2.0,
        brow_raise_right=-1.0,
    )

    clamped = compiler.clamp_pose(unclamped_pose)
    targets = compiler.compile_servo_targets(unclamped_pose)
    joint_limits = {joint.joint_name: joint for joint in default_head_profile().joints}

    assert clamped.head_yaw == 1.0
    assert clamped.head_pitch == -1.0
    assert clamped.head_roll == 1.0
    assert clamped.upper_lid_left_open == 1.0
    assert clamped.upper_lid_right_open == 0.0
    assert clamped.brow_raise_left == 1.0
    assert clamped.brow_raise_right == 0.0
    for joint_name, raw in targets.items():
        assert joint_limits[joint_name].raw_min <= raw <= joint_limits[joint_name].raw_max


def test_wink_gestures_preserve_left_right_asymmetry_in_compiled_frames() -> None:
    compiler = SemanticBodyCompiler(profile=default_head_profile())

    wink_left_state = compiler.apply_gesture(BodyState(), GestureRequest(gesture_name="wink_left"))
    wink_right_state = compiler.apply_gesture(BodyState(), GestureRequest(gesture_name="wink_right"))

    left_frame = wink_left_state.compiled_animation.frames[0]
    right_frame = wink_right_state.compiled_animation.frames[0]

    assert left_frame.pose.upper_lid_left_open < left_frame.pose.upper_lid_right_open
    assert left_frame.pose.lower_lid_left_open < left_frame.pose.lower_lid_right_open
    assert right_frame.pose.upper_lid_right_open < right_frame.pose.upper_lid_left_open
    assert right_frame.pose.lower_lid_right_open < right_frame.pose.lower_lid_left_open


def test_grounded_alias_expression_snapshot_for_surprised_pose() -> None:
    compiler = SemanticBodyCompiler(profile=default_head_profile())
    surprised = compiler.compile_frame(compiler.apply_expression(BodyState(), "surprised").pose, semantic_name="surprised")
    friendly = compiler.compile_frame(compiler.apply_expression(BodyState(), "friendly").pose, semantic_name="friendly")

    assert surprised.servo_targets["head_pitch_pair_a"] == 2047
    assert surprised.servo_targets["head_pitch_pair_b"] == 2047
    assert surprised.servo_targets["head_yaw"] == 2047
    assert surprised.servo_targets["upper_lid_left"] == friendly.servo_targets["upper_lid_left"]
    assert surprised.servo_targets["upper_lid_right"] == friendly.servo_targets["upper_lid_right"]
    assert surprised.servo_targets["brow_left"] == friendly.servo_targets["brow_left"]
    assert surprised.servo_targets["brow_right"] == friendly.servo_targets["brow_right"]


def test_virtual_driver_exposes_preview_state_for_demos(tmp_path: Path) -> None:
    settings = build_settings(tmp_path, blink_runtime_mode=RobotMode.DESKTOP_VIRTUAL_BODY)
    driver = build_body_driver(settings)

    driver.apply_command(
        command=RobotCommand(command_type="set_expression", payload={"expression": "thinking"}),
        payload={"expression": "thinking"},
    )

    assert driver.capabilities.supports_virtual_preview is True
    assert driver.state.virtual_preview is not None
    assert driver.state.virtual_preview.current_animation_name == "thinking"
    assert "gaze=" in driver.state.virtual_preview.summary
    assert driver.state.virtual_preview.transition_profile is not None
    assert driver.state.virtual_preview.safe_idle_compatible is True


def test_virtual_driver_runs_primitive_sequence_without_serial_lock(tmp_path: Path) -> None:
    settings = build_settings(tmp_path, blink_runtime_mode=RobotMode.DESKTOP_VIRTUAL_BODY)
    driver = build_body_driver(settings)

    result = driver.run_primitive_sequence(
        sequence_name="test_sequence",
        steps=[
            {"action": "head_turn_left_slow", "intensity": 1.0},
            {"action": "blink_both_fast", "intensity": 1.0},
        ],
    )

    assert result["status"] == "ok"
    assert result["payload"]["sequence_name"] == "test_sequence"
    assert result["payload"]["primitive_steps"] == ["head_turn_left_slow", "blink_both_fast"]
    assert result["payload"]["sequence_step_count"] == 2
    assert result["payload"]["returned_to_neutral"] is True
    assert result["payload"]["preview_only"] is True
    assert driver.state.last_command_outcome is not None
    assert driver.state.last_command_outcome.command_type == "body_primitive_sequence"
    assert driver.state.last_command_outcome.sequence_step_count == 2
    assert driver.state.current_frame is not None
    assert driver.state.current_frame.frame_name is not None
    neutral_frame = driver.compiler.compile_frame(driver.compiler.neutral_pose(), semantic_name="neutral")
    assert driver.state.current_frame.pose == neutral_frame.pose


def test_compiler_staged_sequence_holds_structural_pose_during_expressive_frames() -> None:
    profile = load_head_profile("src/embodied_stack/body/profiles/robot_head_v1.json")
    calibration = load_head_calibration("runtime/calibrations/robot_head_live_v1.json", profile=profile)
    tuning = load_semantic_tuning(
        profile_name=profile.profile_name,
        calibration_path="runtime/calibrations/robot_head_live_v1.json",
        path="runtime/body/semantic_tuning/robot_head_investor_show_v8.json",
    )
    compiler = SemanticBodyCompiler(profile=profile, calibration=calibration, tuning=tuning)

    compiled = compiler.compile_staged_sequence(
        sequence_name="v8_hold_test",
        stages=[
            StagedSequenceStageSpec(
                stage_kind="structural",
                action_name="head_turn_right_slow",
                intensity=0.8,
                move_ms=2000,
                hold_ms=900,
            ),
            StagedSequenceStageSpec(
                stage_kind="expressive",
                settle_ms=420,
                accents=(
                    StagedSequenceAccentSpec("eyes_right_slow", 0.8),
                    StagedSequenceAccentSpec("blink_both_slow", 0.8),
                ),
            ),
            StagedSequenceStageSpec(
                stage_kind="return",
                move_ms=1800,
                hold_ms=1300,
            ),
        ],
    )

    assert compiled.grounding == "staged_sequence"
    assert compiled.structural_action == "head_turn_right_slow"
    assert compiled.expressive_accents == ["eyes_right_slow", "blink_both_slow"]
    assert compiled.stage_count == 3
    assert compiled.returns_to_neutral is True
    assert compiled.requested_speed == 90
    assert compiled.requested_acceleration == 24

    structural_frame = compiled.frames[0]
    expressive_frames = [frame for frame in compiled.frames if ":expressive:" in str(frame.frame_name)]
    assert expressive_frames
    for frame in expressive_frames:
        assert frame.pose.head_yaw == pytest.approx(structural_frame.pose.head_yaw)
        assert frame.pose.head_pitch == pytest.approx(structural_frame.pose.head_pitch)
        assert frame.pose.head_roll == pytest.approx(structural_frame.pose.head_roll)
        assert frame.requested_speed == 90
        assert frame.requested_acceleration == 24
    assert expressive_frames[0].duration_ms == 270
    assert expressive_frames[0].hold_ms == 238
    assert expressive_frames[1].duration_ms == 330
    assert expressive_frames[1].hold_ms == 0
    base_eye_right = compiler.apply_animation(
        BodyState(),
        AnimationRequest(animation_name="eyes_right_slow", intensity=0.8),
    ).compiled_animation.frames[0].pose.eye_yaw
    assert expressive_frames[0].pose.eye_yaw > base_eye_right
    assert expressive_frames[0].pose.eye_yaw >= 0.78

    base_blink = compiler.apply_animation(
        BodyState(),
        AnimationRequest(animation_name="blink_both_slow", intensity=0.8),
    ).compiled_animation.frames[0].pose
    staged_blink_target = next(
        frame
        for frame in expressive_frames
        if str(frame.frame_name).endswith(":expressive:2:1:target")
    )
    assert staged_blink_target.pose.upper_lid_left_open < base_blink.upper_lid_left_open
    assert staged_blink_target.pose.upper_lid_right_open < base_blink.upper_lid_right_open
    assert staged_blink_target.pose.lower_lid_left_open < base_blink.lower_lid_left_open
    assert staged_blink_target.pose.lower_lid_right_open < base_blink.lower_lid_right_open

    return_frame = next(frame for frame in compiled.frames if str(frame.frame_name).endswith(":return"))
    assert return_frame.pose.eye_yaw == pytest.approx(compiler.neutral_pose().eye_yaw)
    assert return_frame.pose.eye_pitch == pytest.approx(compiler.neutral_pose().eye_pitch)
    assert compiled.frames[-1].pose == compiler.compile_frame(compiler.neutral_pose(), semantic_name="neutral").pose


def test_compiler_staged_sequence_amplifies_brow_stage_toward_v6_scale() -> None:
    profile = load_head_profile("src/embodied_stack/body/profiles/robot_head_v1.json")
    calibration = load_head_calibration("runtime/calibrations/robot_head_live_v1.json", profile=profile)
    tuning = load_semantic_tuning(
        profile_name=profile.profile_name,
        calibration_path="runtime/calibrations/robot_head_live_v1.json",
        path="runtime/body/semantic_tuning/robot_head_investor_show_v8.json",
    )
    compiler = SemanticBodyCompiler(profile=profile, calibration=calibration, tuning=tuning)

    compiled = compiler.compile_staged_sequence(
        sequence_name="v8_brow_scale_test",
        stages=[
            StagedSequenceStageSpec(
                stage_kind="structural",
                action_name="head_turn_right_slow",
                intensity=0.8,
                move_ms=2600,
                hold_ms=1400,
            ),
            StagedSequenceStageSpec(
                stage_kind="expressive",
                settle_ms=650,
                accents=(StagedSequenceAccentSpec(action_name="brows_raise_both_slow", intensity=1.0),),
            ),
            StagedSequenceStageSpec(stage_kind="return", move_ms=2200, hold_ms=0),
        ],
    )

    base_brow = compiler.apply_animation(
        BodyState(),
        AnimationRequest(animation_name="brows_raise_both_slow", intensity=1.0),
    ).compiled_animation.frames[0].pose
    staged_brow_target = next(
        frame
        for frame in compiled.frames
        if str(frame.frame_name).endswith(":expressive:1:1:target")
    )
    assert staged_brow_target.pose.brow_raise_left > base_brow.brow_raise_left
    assert staged_brow_target.pose.brow_raise_right > base_brow.brow_raise_right


def test_compiler_staged_sequence_can_hold_eye_closure_while_brows_move() -> None:
    profile = load_head_profile("src/embodied_stack/body/profiles/robot_head_v1.json")
    calibration = load_head_calibration("runtime/calibrations/robot_head_live_v1.json", profile=profile)
    tuning = load_semantic_tuning(
        profile_name=profile.profile_name,
        calibration_path="runtime/calibrations/robot_head_live_v1.json",
        path="runtime/body/semantic_tuning/robot_head_investor_show_v8.json",
    )
    compiler = SemanticBodyCompiler(profile=profile, calibration=calibration, tuning=tuning)

    compiled = compiler.compile_staged_sequence(
        sequence_name="v8_hold_close_frown_test",
        stages=[
            StagedSequenceStageSpec(
                stage_kind="structural",
                action_name="head_turn_right_slow",
                intensity=1.0,
                move_ms=2600,
                hold_ms=1400,
            ),
            StagedSequenceStageSpec(
                stage_kind="expressive",
                settle_ms=650,
                accents=(
                    StagedSequenceAccentSpec(action_name="close_both_eyes_hold_slow", intensity=1.0),
                    StagedSequenceAccentSpec(action_name="brows_lower_hold_slow", intensity=1.0),
                    StagedSequenceAccentSpec(action_name="brows_neutral_slow", intensity=1.0),
                    StagedSequenceAccentSpec(action_name="lids_neutral_slow", intensity=1.0),
                ),
            ),
            StagedSequenceStageSpec(stage_kind="return", move_ms=2200, hold_ms=0),
        ],
    )

    neutral = compiler.neutral_pose()
    brow_hold_frame = next(
        frame
        for frame in compiled.frames
        if str(frame.frame_name).endswith(":expressive:2:1:target")
    )
    assert brow_hold_frame.pose.upper_lid_left_open < neutral.upper_lid_left_open
    assert brow_hold_frame.pose.upper_lid_right_open < neutral.upper_lid_right_open
    assert brow_hold_frame.pose.lower_lid_left_open < neutral.lower_lid_left_open
    assert brow_hold_frame.pose.lower_lid_right_open < neutral.lower_lid_right_open
    assert brow_hold_frame.pose.brow_raise_left < neutral.brow_raise_left
    assert brow_hold_frame.pose.brow_raise_right < neutral.brow_raise_right

    brow_release_frame = next(
        frame
        for frame in compiled.frames
        if str(frame.frame_name).endswith(":expressive:3:1:target")
    )
    assert brow_release_frame.pose.upper_lid_left_open < neutral.upper_lid_left_open
    assert brow_release_frame.pose.upper_lid_right_open < neutral.upper_lid_right_open
    assert brow_release_frame.pose.brow_raise_left == pytest.approx(neutral.brow_raise_left)
    assert brow_release_frame.pose.brow_raise_right == pytest.approx(neutral.brow_raise_right)

    lids_release_frame = next(
        frame
        for frame in compiled.frames
        if str(frame.frame_name).endswith(":expressive:4:1:target")
    )
    assert lids_release_frame.pose.upper_lid_left_open == pytest.approx(neutral.upper_lid_left_open)
    assert lids_release_frame.pose.upper_lid_right_open == pytest.approx(neutral.upper_lid_right_open)
    assert lids_release_frame.pose.lower_lid_left_open == pytest.approx(neutral.lower_lid_left_open)
    assert lids_release_frame.pose.lower_lid_right_open == pytest.approx(neutral.lower_lid_right_open)


def test_compiler_expressive_motif_preserves_held_eye_closure_during_brow_release() -> None:
    profile = load_head_profile("src/embodied_stack/body/profiles/robot_head_v1.json")
    calibration = load_head_calibration("runtime/calibrations/robot_head_live_v1.json", profile=profile)
    tuning = load_semantic_tuning(
        profile_name=profile.profile_name,
        calibration_path="runtime/calibrations/robot_head_live_v1.json",
        path="runtime/body/semantic_tuning/robot_head_investor_show_v8.json",
    )
    compiler = SemanticBodyCompiler(profile=profile, calibration=calibration, tuning=tuning)

    compiled = compiler.compile_expressive_sequence(
        sequence_name="guarded_close_right",
        motif_name="guarded_close_right",
        steps=[
            ExpressiveSequenceStepSpec(
                step_kind="structural_set",
                action_name="head_turn_right_slow",
                intensity=1.0,
                move_ms=2600,
                hold_ms=1200,
            ),
            ExpressiveSequenceStepSpec(
                step_kind="expressive_set",
                action_name="close_both_eyes_slow",
                intensity=1.0,
                move_ms=950,
                hold_ms=800,
            ),
            ExpressiveSequenceStepSpec(
                step_kind="expressive_set",
                action_name="brows_lower_both_slow",
                intensity=1.0,
                move_ms=900,
                hold_ms=800,
            ),
            ExpressiveSequenceStepSpec(
                step_kind="expressive_release",
                release_groups=("brows",),
                move_ms=850,
                hold_ms=500,
            ),
            ExpressiveSequenceStepSpec(
                step_kind="expressive_release",
                release_groups=("lids",),
                move_ms=900,
                hold_ms=500,
            ),
            ExpressiveSequenceStepSpec(
                step_kind="return_to_neutral",
                move_ms=2200,
                hold_ms=0,
            ),
        ],
    )

    neutral = compiler.neutral_pose()
    assert compiled.grounding == "expressive_motif"
    assert compiled.motif_name == "guarded_close_right"
    assert compiled.structural_action == "head_turn_right_slow"
    assert compiled.step_kinds == [
        "structural_set",
        "expressive_set",
        "expressive_set",
        "expressive_release",
        "expressive_release",
        "return_to_neutral",
    ]
    brow_release_frame = next(
        frame
        for frame in compiled.frames
        if str(frame.frame_name).endswith(":step4:expressive_release")
    )
    assert brow_release_frame.pose.upper_lid_left_open < neutral.upper_lid_left_open
    assert brow_release_frame.pose.upper_lid_right_open < neutral.upper_lid_right_open
    assert brow_release_frame.pose.brow_raise_left == pytest.approx(neutral.brow_raise_left)
    assert brow_release_frame.pose.brow_raise_right == pytest.approx(neutral.brow_raise_right)

    lid_release_frame = next(
        frame
        for frame in compiled.frames
        if str(frame.frame_name).endswith(":step5:expressive_release")
    )
    assert lid_release_frame.pose.upper_lid_left_open == pytest.approx(neutral.upper_lid_left_open)
    assert lid_release_frame.pose.upper_lid_right_open == pytest.approx(neutral.upper_lid_right_open)
    assert lid_release_frame.pose.lower_lid_left_open == pytest.approx(neutral.lower_lid_left_open)
    assert lid_release_frame.pose.lower_lid_right_open == pytest.approx(neutral.lower_lid_right_open)
    assert compiled.frames[-1].pose == compiler.compile_frame(compiler.neutral_pose(), semantic_name="neutral").pose


def test_virtual_driver_runs_expressive_motif_without_serial_lock(tmp_path: Path) -> None:
    settings = build_settings(
        tmp_path,
        blink_runtime_mode=RobotMode.DESKTOP_VIRTUAL_BODY,
        blink_body_semantic_tuning_path="runtime/body/semantic_tuning/robot_head_investor_show_v8.json",
    )
    driver = build_body_driver(settings)

    result = driver.run_expressive_sequence(
        motif_name="guarded_close_right",
        sequence_name="guarded_close_right_run",
    )

    assert result["status"] == "ok"
    assert result["payload"]["motif_name"] == "guarded_close_right"
    assert result["payload"]["structural_action"] == "head_turn_right_slow"
    assert result["payload"]["step_kinds"] == [
        "structural_set",
        "expressive_set",
        "expressive_set",
        "expressive_release",
        "expressive_release",
        "return_to_neutral",
    ]
    assert result["payload"]["returned_to_neutral"] is True
    assert driver.state.last_command_outcome is not None
    assert driver.state.last_command_outcome.command_type == "body_expressive_motif"
    assert driver.state.last_command_outcome.motif_name == "guarded_close_right"
    assert driver.state.current_frame is not None
    neutral_frame = driver.compiler.compile_frame(driver.compiler.neutral_pose(), semantic_name="neutral")
    assert driver.state.current_frame.pose == neutral_frame.pose


def test_virtual_driver_runs_staged_sequence_without_serial_lock(tmp_path: Path) -> None:
    settings = build_settings(
        tmp_path,
        blink_runtime_mode=RobotMode.DESKTOP_VIRTUAL_BODY,
        blink_body_semantic_tuning_path="runtime/body/semantic_tuning/robot_head_investor_show_v8.json",
    )
    driver = build_body_driver(settings)

    result = driver.run_staged_sequence(
        sequence_name="v8_virtual_test",
        stages=[
            {
                "stage_kind": "structural",
                "action": "head_turn_right_slow",
                "intensity": 0.8,
                "move_ms": 2000,
                "hold_ms": 900,
            },
            {
                "stage_kind": "expressive",
                "settle_ms": 420,
                "accents": [
                    {"action": "eyes_right_slow", "intensity": 0.8},
                    {"action": "blink_both_slow", "intensity": 0.8},
                ],
            },
            {
                "stage_kind": "return",
                "move_ms": 1800,
                "hold_ms": 1300,
            },
        ],
    )

    assert result["status"] == "ok"
    assert result["payload"]["sequence_name"] == "v8_virtual_test"
    assert result["payload"]["structural_action"] == "head_turn_right_slow"
    assert result["payload"]["expressive_accents"] == ["eyes_right_slow", "blink_both_slow"]
    assert result["payload"]["stage_count"] == 3
    assert result["payload"]["returned_to_neutral"] is True
    assert driver.state.last_command_outcome is not None
    assert driver.state.last_command_outcome.command_type == "body_staged_sequence"
    assert driver.state.last_command_outcome.structural_action == "head_turn_right_slow"
    assert driver.state.last_command_outcome.expressive_accents == ["eyes_right_slow", "blink_both_slow"]
    assert driver.state.current_frame is not None
    neutral_frame = driver.compiler.compile_frame(driver.compiler.neutral_pose(), semantic_name="neutral")
    assert driver.state.current_frame.pose == neutral_frame.pose


def test_stage4_semantics_compile_and_preview_aliases(tmp_path: Path) -> None:
    settings = build_settings(tmp_path, blink_runtime_mode=RobotMode.DESKTOP_VIRTUAL_BODY)
    driver = build_body_driver(settings)

    driver.apply_command(
        command=RobotCommand(command_type="set_expression", payload={"expression": "listening"}),
        payload={"expression": "listening"},
    )
    driver.apply_command(
        command=RobotCommand(command_type="set_gaze", payload={"target": "look_at_user", "yaw": 0.5, "pitch": -0.2}),
        payload={"target": "look_at_user", "yaw": 0.5, "pitch": -0.2},
    )

    assert driver.state.virtual_preview is not None
    assert driver.state.virtual_preview.semantic_name == "look_at_user"
    assert driver.state.virtual_preview.source_name == "look_at_user"
    assert driver.state.active_expression == "listen_attentively"
    assert driver.state.virtual_preview.alias_used is False
    assert driver.state.last_command_outcome is not None
    assert driver.state.last_command_outcome.canonical_action_name == "look_at_user"


def test_compiler_adds_transition_notes_for_zero_duration_frames() -> None:
    compiler = SemanticBodyCompiler(profile=default_head_profile())

    frame = compiler.compile_frame(
        BodyPose(head_pitch=0.2),
        frame_name="fast",
        duration_ms=0,
        animation_name="attention_settle",
    )

    assert frame.duration_ms == default_head_profile().default_transition_ms
    assert frame.transition_profile is not None
    assert any(note.startswith("transition_default:") for note in frame.compiler_notes)


def test_stage_d_tuning_adjusts_compiled_semantic_pose_and_records_notes() -> None:
    compiler = SemanticBodyCompiler(
        profile=default_head_profile(),
        tuning=SemanticTuningRecord(
            profile_name="robot_head_v1",
            brow_asymmetry_correction=0.5,
            action_overrides={
                "look_left": SemanticActionTuningOverride(
                    intensity_multiplier=0.5,
                    pose_offsets={"eye_yaw": -0.1},
                    notes=["test_override"],
                )
            },
        ),
    )

    state = compiler.apply_gaze(BodyState(), target="look_left")
    frame = state.compiled_animation.frames[0]

    assert frame.pose.eye_yaw <= -0.18
    assert frame.pose.head_yaw < 0.0
    assert any(note.startswith("tuning:action_override:look_left") for note in frame.compiler_notes)


def test_two_lane_operating_bands_derive_from_live_calibration() -> None:
    profile = load_head_profile("src/embodied_stack/body/profiles/robot_head_v1.json")
    calibration = load_head_calibration("runtime/calibrations/robot_head_live_v1.json", profile=profile)
    default_tuning = load_semantic_tuning(
        profile_name=profile.profile_name,
        calibration_path="runtime/calibrations/robot_head_live_v1.json",
        path="runtime/body/semantic_tuning/robot_head_live_v1.json",
    )
    demo_tuning = load_semantic_tuning(
        profile_name=profile.profile_name,
        calibration_path="runtime/calibrations/robot_head_live_v1.json",
        path="runtime/body/semantic_tuning/robot_head_investor_show_v8.json",
    )

    default_band = SemanticBodyCompiler(profile=profile, calibration=calibration, tuning=default_tuning).operating_band()
    demo_band = SemanticBodyCompiler(profile=profile, calibration=calibration, tuning=demo_tuning).operating_band()

    assert default_band.head_yaw.negative_limit == pytest.approx(0.7)
    assert default_band.head_yaw.positive_limit == pytest.approx(0.7)
    assert demo_band.head_yaw.negative_limit == pytest.approx(0.95)
    assert demo_band.head_yaw.positive_limit == pytest.approx(0.95)
    assert demo_band.head_roll.positive_limit > default_band.head_roll.positive_limit
    assert demo_band.head_roll.negative_limit > default_band.head_roll.negative_limit
    assert demo_band.head_roll.negative_limit < 0.1
    assert demo_band.upper_lid.positive_limit > default_band.upper_lid.positive_limit
    assert demo_band.brow.negative_limit > default_band.brow.negative_limit


def test_compiled_frames_record_lane_and_kinetics_metadata() -> None:
    profile = load_head_profile("src/embodied_stack/body/profiles/robot_head_v1.json")
    calibration = load_head_calibration("runtime/calibrations/robot_head_live_v1.json", profile=profile)
    tuning = load_semantic_tuning(
        profile_name=profile.profile_name,
        calibration_path="runtime/calibrations/robot_head_live_v1.json",
        path="runtime/body/semantic_tuning/robot_head_investor_show_v8.json",
    )
    compiler = SemanticBodyCompiler(profile=profile, calibration=calibration, tuning=tuning)

    animation = compiler.apply_gesture(BodyState(), GestureRequest(gesture_name="double_blink")).compiled_animation
    assert animation is not None
    assert animation.tuning_lane == "demo_live"
    assert "primitive_fast" in animation.kinetics_profiles_used
    assert animation.requested_speed == 120
    assert animation.requested_acceleration == 40
    assert all(frame.kinetics_profile == "primitive_fast" for frame in animation.frames)


def test_combination_rules_clamp_held_eye_pitch_and_lid_occupancy() -> None:
    profile = load_head_profile("src/embodied_stack/body/profiles/robot_head_v1.json")
    calibration = load_head_calibration("runtime/calibrations/robot_head_live_v1.json", profile=profile)
    tuning = load_semantic_tuning(
        profile_name=profile.profile_name,
        calibration_path="runtime/calibrations/robot_head_live_v1.json",
        path="runtime/body/semantic_tuning/robot_head_investor_show_v8.json",
    )
    compiler = SemanticBodyCompiler(profile=profile, calibration=calibration, tuning=tuning)
    neutral = compiler.neutral_pose()

    frame = compiler.compile_frame(
        BodyPose(
            eye_pitch=0.46,
            upper_lid_left_open=min(1.0, neutral.upper_lid_left_open + 0.16),
            upper_lid_right_open=min(1.0, neutral.upper_lid_right_open + 0.16),
            lower_lid_left_open=min(1.0, neutral.lower_lid_left_open + 0.12),
            lower_lid_right_open=min(1.0, neutral.lower_lid_right_open + 0.12),
        ),
        semantic_name="combination_test",
    )

    assert any("combination:eye_pitch_vs_lids" in note for note in frame.compiler_notes)
    assert abs(frame.pose.upper_lid_left_open - neutral.upper_lid_left_open) < 0.16


def test_combination_rules_limit_large_neck_pitch_and_tilt_stack() -> None:
    profile = load_head_profile("src/embodied_stack/body/profiles/robot_head_v1.json")
    calibration = load_head_calibration("runtime/calibrations/robot_head_live_v1.json", profile=profile)
    tuning = load_semantic_tuning(
        profile_name=profile.profile_name,
        calibration_path="runtime/calibrations/robot_head_live_v1.json",
        path="runtime/body/semantic_tuning/robot_head_investor_show_v8.json",
    )
    compiler = SemanticBodyCompiler(profile=profile, calibration=calibration, tuning=tuning)

    frame = compiler.compile_frame(
        BodyPose(head_pitch=0.2, head_roll=0.22),
        semantic_name="neck_combination_test",
    )

    assert any("coupling:neck_pitch_roll" in note for note in frame.compiler_notes)
    assert frame.servo_targets["head_pitch_pair_a"] > 2047
    assert frame.servo_targets["head_pitch_pair_b"] < 2047


def test_motion_envelope_pitch_roll_budget_is_enforced() -> None:
    compiler = SemanticBodyCompiler(
        profile=default_head_profile(),
        tuning=SemanticTuningRecord(
            profile_name="robot_head_v1",
            motion_envelopes={
                "accent": MotionEnvelope(
                    head_yaw=1.0,
                    head_pitch=1.0,
                    head_roll=1.0,
                    eye_yaw=1.0,
                    eye_pitch=1.0,
                    upper_lid_deviation=1.0,
                    lower_lid_deviation=1.0,
                    brow_deviation=1.0,
                    pitch_roll_budget=0.18,
                )
            },
        ),
    )

    frame = compiler.compile_frame(
        BodyPose(head_pitch=0.18, head_roll=0.12),
        semantic_name="tilt_curious",
    )

    assert abs(frame.pose.head_pitch) + abs(frame.pose.head_roll) == pytest.approx(0.18)
    assert any("pitch_roll_budget" in note for note in frame.compiler_notes)


def test_transient_blink_frames_can_close_strongly_but_held_expressions_do_not() -> None:
    compiler = SemanticBodyCompiler(profile=default_head_profile())

    blink = compiler.apply_gesture(BodyState(), GestureRequest(gesture_name="double_blink"))
    closed_frames = [frame for frame in blink.compiled_animation.frames if frame.transient]
    assert closed_frames
    assert min(frame.pose.upper_lid_left_open for frame in closed_frames) < 0.1
    assert min(frame.pose.upper_lid_right_open for frame in closed_frames) < 0.1

    friendly = compiler.apply_expression(BodyState(), "friendly").compiled_animation.frames[-1]
    eyes_widen = compiler.apply_expression(BodyState(), "eyes_widen").compiled_animation.frames[-1]
    assert friendly.pose.upper_lid_left_open > 0.6
    assert friendly.pose.upper_lid_right_open > 0.6
    assert eyes_widen.pose.upper_lid_left_open < 0.87
    assert eyes_widen.pose.upper_lid_right_open < 0.87


def test_expressive_upgrade_actions_compile_into_previewable_frames() -> None:
    compiler = SemanticBodyCompiler(profile=default_head_profile())

    playful_frame = compiler.compile_frame(compiler.apply_expression(BodyState(), "playful").pose)
    bashful_frame = compiler.compile_frame(compiler.apply_expression(BodyState(), "bashful").pose)
    friendly_frame = compiler.compile_frame(compiler.apply_expression(BodyState(), "friendly").pose)
    focused_soft_frame = compiler.compile_frame(compiler.apply_expression(BodyState(), "focused_soft").pose)
    greeting_state = compiler.apply_animation(BodyState(), "youthful_greeting")
    peek_state = compiler.apply_gesture(BodyState(), GestureRequest(gesture_name="playful_peek_left"))

    assert playful_frame.servo_targets["head_yaw"] == 2047
    assert playful_frame.servo_targets["upper_lid_left"] == friendly_frame.servo_targets["upper_lid_left"]
    assert playful_frame.servo_targets["brow_left"] == friendly_frame.servo_targets["brow_left"]
    assert bashful_frame.servo_targets["eye_pitch"] == focused_soft_frame.servo_targets["eye_pitch"]
    assert bashful_frame.servo_targets["upper_lid_left"] == focused_soft_frame.servo_targets["upper_lid_left"]
    assert greeting_state.compiled_animation is not None
    assert greeting_state.compiled_animation.animation_name == "youthful_greeting"
    assert len(greeting_state.compiled_animation.frames) >= 4
    assert peek_state.compiled_animation is not None
    assert peek_state.compiled_animation.frames[0].servo_targets["eye_yaw"] < 2047
