from __future__ import annotations

from pathlib import Path

import pytest

from embodied_stack.body import SemanticBodyCompiler, build_body_driver
from embodied_stack.body.animations import gesture_timeline
from embodied_stack.body.calibration import load_head_calibration
from embodied_stack.body.profile import load_head_profile
from embodied_stack.body.primitives import PrimitiveSequenceStepSpec, primitive_action_names
from embodied_stack.body.semantics import lookup_action_descriptor
from embodied_stack.body.tuning import load_semantic_tuning
from embodied_stack.config import Settings
from embodied_stack.shared.contracts import BodyState, RobotCommand, RobotMode


PROFILE_PATH = "src/embodied_stack/body/profiles/robot_head_v1.json"
CALIBRATION_PATH = "runtime/calibrations/robot_head_live_v1.json"
TUNING_PATH = Path("runtime/body/semantic_tuning/robot_head_investor_show_v8.json")


def _grounded_compiler() -> SemanticBodyCompiler:
    profile = load_head_profile(PROFILE_PATH)
    calibration = load_head_calibration(CALIBRATION_PATH, profile=profile)
    tuning = load_semantic_tuning(profile_name=profile.profile_name, path=TUNING_PATH)
    return SemanticBodyCompiler(profile=profile, calibration=calibration, tuning=tuning)


def _build_settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        brain_store_path=str(tmp_path / "brain_store.json"),
        demo_report_dir=str(tmp_path / "demo_runs"),
        demo_check_dir=str(tmp_path / "demo_checks"),
        episode_export_dir=str(tmp_path / "episodes"),
        shift_report_dir=str(tmp_path / "shift_reports"),
        operator_auth_token="primitive-test-token",
        operator_auth_runtime_file=str(tmp_path / "operator_auth.json"),
        blink_runtime_mode=RobotMode.DESKTOP_VIRTUAL_BODY,
        blink_head_profile=PROFILE_PATH,
        blink_head_calibration=CALIBRATION_PATH,
        blink_body_semantic_tuning_path=str(TUNING_PATH),
    )


def _target_frame(animation_name: str, compiler: SemanticBodyCompiler):
    state = compiler.apply_animation(BodyState(), animation_name)
    return state.compiled_animation.frames[0]


def _assert_pose_close(left, right, *, tolerance: float = 1e-6) -> None:
    for field_name, left_value in left.model_dump().items():
        right_value = right.model_dump()[field_name]
        if left_value is None or right_value is None:
            continue
        assert abs(float(left_value) - float(right_value)) <= tolerance, field_name


def test_primitive_registry_is_publicly_available_to_the_body_layer() -> None:
    names = primitive_action_names()
    assert "neutral_settle_slow" in names
    assert "attend_left_slow" in names
    assert "close_both_eyes_hold_slow" in names
    assert "brows_lower_hold_slow" in names
    assert "brows_neutral_slow" in names
    assert "lids_neutral_slow" in names
    assert "double_blink_slow" in names
    assert "double_blink_fast" in names
    assert "tiny_nod_fast" in names


@pytest.mark.parametrize(
    "action_name",
    [
        "head_turn_left_slow",
        "head_tilt_right_fast",
        "blink_both_fast",
        "brows_raise_both_slow",
        "tiny_nod_fast",
        "attend_left_fast",
    ],
)
def test_primitives_are_neutral_anchored_and_return_to_neutral(action_name: str) -> None:
    compiler = _grounded_compiler()
    shifted_state = compiler.apply_expression(BodyState(), "friendly")

    from_neutral = compiler.apply_animation(BodyState(), action_name).compiled_animation
    from_shifted = compiler.apply_animation(shifted_state, action_name).compiled_animation

    assert from_neutral.grounding == "primitive"
    assert from_neutral.primitive_steps == [action_name]
    assert from_neutral.returns_to_neutral is True
    _assert_pose_close(from_neutral.frames[0].pose, from_shifted.frames[0].pose)
    _assert_pose_close(from_neutral.frames[-1].pose, compiler.neutral_pose(), tolerance=0.02)


def test_primitive_slow_and_fast_timings_and_kinetics_are_fixed() -> None:
    compiler = _grounded_compiler()

    slow = compiler.apply_animation(BodyState(), "attend_left_slow").compiled_animation
    fast = compiler.apply_animation(BodyState(), "blink_both_fast").compiled_animation
    double_blink_slow = compiler.apply_animation(BodyState(), "double_blink_slow").compiled_animation
    double_blink = compiler.apply_animation(BodyState(), "double_blink_fast").compiled_animation

    assert [frame.duration_ms for frame in slow.frames] == [180, 220]
    assert [frame.hold_ms for frame in slow.frames] == [140, 0]
    assert slow.frames[0].requested_speed == 100
    assert slow.frames[0].requested_acceleration == 32

    assert [frame.duration_ms for frame in fast.frames] == [95, 120]
    assert [frame.hold_ms for frame in fast.frames] == [55, 0]
    assert fast.frames[0].requested_speed == 120
    assert fast.frames[0].requested_acceleration == 40

    assert [frame.duration_ms for frame in double_blink_slow.frames] == [180, 220, 180, 220]
    assert [frame.hold_ms for frame in double_blink_slow.frames] == [140, 0, 140, 0]
    assert double_blink_slow.frames[0].requested_speed == 100
    assert double_blink_slow.frames[0].requested_acceleration == 32

    assert [frame.duration_ms for frame in double_blink.frames] == [95, 120, 95, 120]
    assert [frame.hold_ms for frame in double_blink.frames] == [55, 0, 55, 0]


def test_primitive_amplitudes_stay_within_grounded_backoff_policy() -> None:
    compiler = _grounded_compiler()

    head_turn = _target_frame("head_turn_left_slow", compiler)
    eyes_left = _target_frame("eyes_left_slow", compiler)
    tiny_nod = _target_frame("tiny_nod_fast", compiler)
    brows_raise = _target_frame("brows_raise_both_slow", compiler)

    assert abs(float(head_turn.pose.head_yaw or 0.0)) <= 0.8
    assert abs(float(eyes_left.pose.eye_yaw or 0.0)) <= 0.55
    assert abs(float(tiny_nod.pose.head_pitch or 0.0)) <= 0.02
    neutral = compiler.neutral_pose()
    brow_delta = 0.7 * compiler.operating_band().brow.positive_limit
    assert float(brows_raise.pose.brow_raise_left - neutral.brow_raise_left) <= brow_delta + 1e-6
    assert float(brows_raise.pose.brow_raise_right - neutral.brow_raise_right) <= brow_delta + 1e-6


def test_legacy_show_actions_expand_into_primitive_recipes() -> None:
    compiler = _grounded_compiler()
    expectations = {
        "acknowledge_light": ["tiny_nod_fast"],
        "youthful_greeting": ["attend_left_fast", "attend_right_fast", "double_blink_fast"],
        "soft_reengage": ["brows_raise_both_slow", "neutral_settle_slow"],
    }

    for action_name, primitive_steps in expectations.items():
        descriptor = lookup_action_descriptor(action_name)
        assert descriptor is not None
        if descriptor.family == "gesture":
            state = compiler.apply_gesture(BodyState(), action_name)
        else:
            state = compiler.apply_animation(BodyState(), action_name)
        compiled = state.compiled_animation
        assert compiled.grounding == "recipe"
        assert compiled.recipe_name == action_name
        assert compiled.primitive_steps == primitive_steps
        assert compiled.returns_to_neutral is True


def test_grounded_expression_states_compile_as_held_states_not_recipes() -> None:
    compiler = _grounded_compiler()

    compiled = compiler.apply_expression(BodyState(), "friendly").compiled_animation

    assert compiled.grounding == "state"
    assert compiled.recipe_name is None
    assert compiled.returns_to_neutral is False
    assert compiled.frames[-1].pose != compiler.neutral_pose()


def test_unsupported_public_expression_rejects_instead_of_falling_back_to_direct_pose() -> None:
    compiler = _grounded_compiler()

    with pytest.raises(ValueError, match="unsupported_grounded_expression:not_a_real_expression"):
        compiler.apply_expression(BodyState(), "not_a_real_expression")


def test_body_command_audit_records_recipe_and_primitive_steps(tmp_path: Path) -> None:
    driver = build_body_driver(_build_settings(tmp_path))

    driver.apply_command(
        RobotCommand(command_type="set_expression", payload={"expression": "friendly"}),
        {"expression": "friendly"},
    )
    recipe_outcome = driver.state.last_command_outcome
    assert recipe_outcome is not None
    assert recipe_outcome.grounding == "state"
    assert recipe_outcome.recipe_name is None
    assert recipe_outcome.primitive_steps == []
    assert recipe_outcome.returned_to_neutral is False

    driver.apply_command(
        RobotCommand(command_type="perform_animation", payload={"animation": "attend_left_fast"}),
        {"animation": "attend_left_fast"},
    )
    primitive_outcome = driver.state.last_command_outcome
    assert primitive_outcome is not None
    assert primitive_outcome.grounding == "primitive"
    assert primitive_outcome.recipe_name is None
    assert primitive_outcome.primitive_steps == ["attend_left_fast"]
    assert primitive_outcome.returned_to_neutral is True


def test_primitive_sequence_compiles_into_one_animation_with_final_neutral_confirm() -> None:
    compiler = _grounded_compiler()

    compiled = compiler.compile_primitive_sequence(
        sequence_name="v2_atomic_open",
        steps=[
            PrimitiveSequenceStepSpec("head_turn_left_slow"),
            PrimitiveSequenceStepSpec("brows_raise_both_slow"),
        ],
    )

    assert compiled.grounding == "primitive_sequence"
    assert compiled.primitive_steps == ["head_turn_left_slow", "brows_raise_both_slow"]
    assert compiled.sequence_step_count == 2
    assert compiled.returns_to_neutral is True
    assert compiled.frames[-1].frame_name is not None
    assert "sequence_step_count:2" in compiled.compiler_notes
    _assert_pose_close(compiled.frames[-1].pose, compiler.neutral_pose(), tolerance=0.02)


def test_primitive_sequence_rejects_recipe_names() -> None:
    compiler = _grounded_compiler()

    with pytest.raises(ValueError, match="primitive_sequence_step_not_primitive:friendly"):
        compiler.compile_primitive_sequence(
            sequence_name="invalid_sequence",
            steps=[PrimitiveSequenceStepSpec("friendly")],
        )


def test_tiny_nod_stays_shallower_than_legacy_nod_small() -> None:
    compiler = _grounded_compiler()
    tiny_nod = _target_frame("tiny_nod_fast", compiler)
    legacy = gesture_timeline("nod_small", intensity=1.0)
    legacy_min_pitch = min(frame.pose.head_pitch for frame in legacy.keyframes)

    assert abs(tiny_nod.pose.head_pitch) < abs(legacy_min_pitch)
