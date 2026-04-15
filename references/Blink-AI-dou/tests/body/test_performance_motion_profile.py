from __future__ import annotations

import json
from pathlib import Path

import pytest

from embodied_stack.body import SemanticBodyCompiler
from embodied_stack.body.animations import gesture_timeline
from embodied_stack.body.calibration import load_head_calibration
from embodied_stack.body.expressive_motifs import resolve_expressive_motif
from embodied_stack.body.profile import load_head_profile
from embodied_stack.body.semantics import lookup_action_descriptor
from embodied_stack.body.tuning import load_semantic_tuning
from embodied_stack.demo.performance_show import ACTION_INTENSITY_LIMITS, LIVE_SAFE_ACTIONS, load_show_definition
from embodied_stack.shared.contracts import AnimationRequest, BodyState, ExpressionRequest, GazeRequest, GestureRequest
from embodied_stack.shared.models import PerformanceCueKind


SHOW_TUNING_PATH = Path("runtime/body/semantic_tuning/robot_head_investor_show_v8.json")


def _show_compiler() -> SemanticBodyCompiler:
    profile = load_head_profile("src/embodied_stack/body/profiles/robot_head_v1.json")
    calibration = load_head_calibration("runtime/calibrations/robot_head_live_v1.json", profile=profile)
    tuning = load_semantic_tuning(profile_name=profile.profile_name, path=SHOW_TUNING_PATH)
    return SemanticBodyCompiler(profile=profile, calibration=calibration, tuning=tuning)


def _default_compiler() -> SemanticBodyCompiler:
    profile = load_head_profile("src/embodied_stack/body/profiles/robot_head_v1.json")
    calibration = load_head_calibration("runtime/calibrations/robot_head_live_v1.json", profile=profile)
    return SemanticBodyCompiler(profile=profile, calibration=calibration)


def _compile_action(compiler: SemanticBodyCompiler, action_name: str):
    descriptor = lookup_action_descriptor(action_name)
    assert descriptor is not None
    state = BodyState()
    if descriptor.family == "gaze":
        return compiler.apply_gaze(state, target=action_name).compiled_animation.frames[-1]
    if descriptor.family == "expression":
        return compiler.apply_expression(state, action_name).compiled_animation.frames[-1]
    if descriptor.family == "gesture":
        return compiler.apply_gesture(state, action_name).compiled_animation.frames[-1]
    return compiler.apply_animation(state, action_name).compiled_animation.frames[-1]


def _apply_action(
    compiler: SemanticBodyCompiler,
    state: BodyState,
    action_name: str,
    *,
    intensity: float = 1.0,
) -> BodyState:
    descriptor = lookup_action_descriptor(action_name)
    assert descriptor is not None
    if descriptor.family == "gaze":
        return compiler.apply_gaze(state, request=GazeRequest(target=action_name, intensity=intensity))
    if descriptor.family == "expression":
        return compiler.apply_expression(state, ExpressionRequest(expression_name=action_name, intensity=intensity))
    if descriptor.family == "gesture":
        return compiler.apply_gesture(state, GestureRequest(gesture_name=action_name, intensity=intensity))
    return compiler.apply_animation(state, AnimationRequest(animation_name=action_name, intensity=intensity))


def test_v8_motion_profile_uses_only_live_safe_catalog_actions() -> None:
    definition = load_show_definition("investor_expressive_motion_v8")

    body_cues = [
        cue
        for segment in definition.segments
        for cue in segment.cues
        if cue.cue_kind == PerformanceCueKind.BODY_EXPRESSIVE_MOTIF
    ]

    assert body_cues
    for cue in body_cues:
        motif = resolve_expressive_motif(cue.expressive_motif.motif_name)
        assert motif is not None
        for step in motif.steps:
            if step.action_name is None:
                continue
            assert step.action_name in LIVE_SAFE_ACTIONS
            descriptor = lookup_action_descriptor(step.action_name)
            assert descriptor is not None
            assert descriptor.smoke_safe is True
            if step.intensity is not None:
                assert step.intensity <= ACTION_INTENSITY_LIMITS[step.action_name]


def test_v8_tuning_file_keeps_grounded_notes_and_live_safe_overrides() -> None:
    payload = json.loads(SHOW_TUNING_PATH.read_text(encoding="utf-8"))

    assert payload["schema_version"] == "blink_head_semantic_tuning/v1"
    assert payload["tuning_lane"] == "demo_live"
    assert "investor_expressive_motion_v8" in payload["notes"]
    assert "staged_atomic_structural_then_expressive_sequences" in payload["notes"]

    overrides = payload.get("action_overrides", {})
    assert set(overrides).issubset(LIVE_SAFE_ACTIONS)

    for action_name, override in overrides.items():
        descriptor = lookup_action_descriptor(action_name)
        assert descriptor is not None
        assert descriptor.smoke_safe is True
        assert override.get("notes")


def test_acknowledge_light_has_no_downward_head_pitch_travel() -> None:
    animation = gesture_timeline("acknowledge_light", intensity=1.0)
    pitch_values = [frame.pose.head_pitch for frame in animation.keyframes]
    assert min(pitch_values) >= 0.0


def test_show_safe_acknowledge_light_stays_shallow_under_grounded_recipe_path() -> None:
    compiler = _show_compiler()
    state = compiler.apply_expression(BodyState(), "listen_attentively")
    result = compiler.apply_gesture(state, "acknowledge_light")
    pitch_values = [frame.pose.head_pitch for frame in result.compiled_animation.frames]
    assert min(pitch_values) >= -0.02
    assert max(pitch_values) <= 0.0


def test_show_safe_downward_search_uses_eye_pitch_not_head_drop() -> None:
    compiler = _show_compiler()

    far_down_animation = compiler.apply_gaze(
        compiler.apply_expression(BodyState(), "friendly"),
        target="look_far_down",
    ).compiled_animation
    far_down = max(
        far_down_animation.frames,
        key=lambda frame: abs(frame.pose.eye_pitch),
    )
    brief_down_animation = compiler.apply_gaze(
        compiler.apply_expression(BodyState(), "friendly"),
        target="look_down_briefly",
    ).compiled_animation
    brief_down = max(
        brief_down_animation.frames,
        key=lambda frame: abs(frame.pose.eye_pitch),
    )

    assert far_down.pose.head_pitch >= 0.0
    assert abs(far_down.pose.eye_pitch) >= 0.45
    assert abs(far_down.pose.eye_pitch) > abs(far_down.pose.head_pitch)
    assert brief_down.pose.head_pitch >= 0.0
    assert abs(brief_down.pose.eye_pitch) > abs(brief_down.pose.head_pitch)


def test_show_safe_listening_family_stays_out_of_downward_pitch() -> None:
    compiler = _show_compiler()

    listening = compiler.apply_expression(BodyState(), ExpressionRequest(expression_name="listen_attentively", intensity=1.0)).compiled_animation.frames[-1]
    greeting = compiler.apply_animation(BodyState(), AnimationRequest(animation_name="youthful_greeting", intensity=1.0)).compiled_animation.frames[-1]
    reengage = compiler.apply_animation(BodyState(), AnimationRequest(animation_name="soft_reengage", intensity=1.0)).compiled_animation.frames[-1]
    safe_idle = compiler.apply_expression(BodyState(), ExpressionRequest(expression_name="safe_idle", intensity=1.0)).compiled_animation.frames[-1]

    assert listening.pose.head_pitch >= 0.0
    assert greeting.pose.head_pitch >= 0.0
    assert reengage.pose.head_pitch >= 0.0
    assert safe_idle.pose.head_pitch >= 0.0


def test_nod_small_is_shallow_and_nod_medium_is_not_in_public_show_allowlist() -> None:
    animation = gesture_timeline("nod_small", intensity=1.0)
    pitch_values = [frame.pose.head_pitch for frame in animation.keyframes]
    assert min(pitch_values) == pytest.approx(-0.04)
    assert max(pitch_values) == pytest.approx(0.02)
    assert "nod_medium" not in LIVE_SAFE_ACTIONS
    assert "nod_small" not in LIVE_SAFE_ACTIONS


def test_grounded_v8_tuning_preserves_catalog_state_shapes_for_core_actions() -> None:
    default_compiler = _default_compiler()
    show_compiler = _show_compiler()

    default_left = _compile_action(default_compiler, "look_left")
    show_left = _compile_action(show_compiler, "look_left")
    default_friendly = _compile_action(default_compiler, "friendly")
    show_friendly = _compile_action(show_compiler, "friendly")
    default_curious = _compile_action(default_compiler, "curious_bright")
    show_curious = _compile_action(show_compiler, "curious_bright")

    assert show_left.pose.head_yaw == default_left.pose.head_yaw
    assert show_left.pose.eye_yaw == default_left.pose.eye_yaw
    assert show_friendly.pose.brow_raise_left == default_friendly.pose.brow_raise_left
    assert show_friendly.pose.brow_raise_right == default_friendly.pose.brow_raise_right
    assert show_curious.pose.head_yaw == default_curious.pose.head_yaw
    assert show_curious.pose.brow_raise_left == default_curious.pose.brow_raise_left
    assert show_curious.pose.brow_raise_right == default_curious.pose.brow_raise_right


def test_public_investor_show_profile_keeps_eye_and_lid_travel_inside_public_safe_envelope() -> None:
    compiler = _show_compiler()
    neutral = compiler.neutral_pose()

    for action_name in ("look_left", "look_far_left", "look_up", "look_far_up", "thinking", "curious_bright", "focused_soft"):
        frame = _compile_action(compiler, action_name)
        assert abs(frame.pose.eye_yaw) <= 0.28
        assert abs(frame.pose.eye_pitch) <= 0.48
        if lookup_action_descriptor(action_name).family == "expression":
            assert abs(frame.pose.upper_lid_left_open - neutral.upper_lid_left_open) <= 0.15
            assert abs(frame.pose.upper_lid_right_open - neutral.upper_lid_right_open) <= 0.15
            assert abs(frame.pose.lower_lid_left_open - neutral.lower_lid_left_open) <= 0.15
            assert abs(frame.pose.lower_lid_right_open - neutral.lower_lid_right_open) <= 0.15


def test_grounded_gaze_lane_returns_to_neutral_after_search_actions() -> None:
    compiler = _show_compiler()
    state = BodyState()

    state = _apply_action(compiler, state, "curious_bright")
    state = _apply_action(compiler, state, "tilt_curious")
    state = _apply_action(compiler, state, "friendly")
    friendly_frame = state.compiled_animation.frames[-1]

    state = _apply_action(compiler, state, "look_far_left")
    far_left = state.compiled_animation.frames[-1]
    state = _apply_action(compiler, state, "look_far_up")
    far_up = state.compiled_animation.frames[-1]
    state = _apply_action(compiler, state, "look_far_down")
    far_down = state.compiled_animation.frames[-1]
    state = _apply_action(compiler, state, "look_forward")
    forward = state.compiled_animation.frames[-1]

    assert far_left.pose.brow_raise_left != friendly_frame.pose.brow_raise_left
    assert far_up.pose.brow_raise_left == far_left.pose.brow_raise_left
    assert far_down.pose.brow_raise_left == far_left.pose.brow_raise_left
    assert forward.pose.brow_raise_left == far_down.pose.brow_raise_left


def test_v8_show_uses_sequential_release_before_structural_return() -> None:
    definition = load_show_definition("investor_expressive_motion_v8")

    for segment in definition.segments:
        cue = next(item for item in segment.cues if item.cue_kind == PerformanceCueKind.BODY_EXPRESSIVE_MOTIF)
        motif = resolve_expressive_motif(cue.expressive_motif.motif_name)
        assert motif is not None
        step_kinds = [step.step_kind for step in motif.steps]
        assert step_kinds[0] == "structural_set"
        assert step_kinds[-1] == "return_to_neutral"
        assert "expressive_release" in step_kinds
        assert step_kinds.index("expressive_release") < step_kinds.index("return_to_neutral")


def test_v8_pitch_led_motifs_keep_structural_motion_conservative() -> None:
    compiler = _show_compiler()
    definition = load_show_definition("investor_expressive_motion_v8")
    pitch_led = {"curious_lift", "reflective_lower"}

    for segment in definition.segments:
        if segment.segment_id not in pitch_led:
            continue
        cue = next(item for item in segment.cues if item.cue_kind == PerformanceCueKind.BODY_EXPRESSIVE_MOTIF)
        motif = resolve_expressive_motif(cue.expressive_motif.motif_name)
        assert motif is not None
        structural_step = next(step for step in motif.steps if step.step_kind == "structural_set")
        state = _apply_action(compiler, BodyState(), structural_step.action_name, intensity=float(structural_step.intensity or 1.0))
        targets = state.servo_targets or {}
        a = targets.get("head_pitch_pair_a")
        b = targets.get("head_pitch_pair_b")
        assert a is not None and b is not None
        assert abs(a - 2047) + abs(b - 2047) <= 120
