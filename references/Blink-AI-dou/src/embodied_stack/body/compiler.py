from __future__ import annotations

from dataclasses import dataclass

from embodied_stack.shared.contracts.body import (
    AnimationRequest,
    AnimationTimeline,
    BodyKeyframe,
    BodyPose,
    BodyState,
    CompiledAnimation,
    CompiledBodyFrame,
    DerivedOperatingBand,
    ExpressionRequest,
    GazeRequest,
    GestureRequest,
    HeadCalibrationRecord,
    HeadProfile,
    MotionKineticsProfile,
    MotionEnvelope,
    SemanticTuningRecord,
    VirtualBodyPreview,
)

from .animations import animation_timeline, gesture_timeline
from .grounded_catalog import build_grounded_state_pose
from .library import (
    RATIO_FIELDS,
    SIGNED_FIELDS,
    SUPPORTED_EXPRESSIONS,
    SUPPORTED_GAZE_TARGETS,
    SUPPORTED_GESTURES,
    apply_pose_overrides,
    expression_pose,
    gaze_pose,
)
from .expressive_motifs import (
    ExpressiveSequenceStepSpec,
    expressive_motif_unit,
)
from .motion_tuning import derive_operating_band, resolve_motion_kinetics_profiles
from .primitives import (
    PRIMITIVE_FAST_KINETICS,
    PRIMITIVE_MOTION_ENVELOPE,
    PRIMITIVE_SLOW_KINETICS,
    PrimitiveSequenceStepSpec,
    build_primitive_sequence_timeline,
    build_registered_action_timeline,
    is_primitive_action,
    is_recipe_action,
    primitive_target_pose,
)
from .semantics import (
    CANONICAL_ANIMATIONS,
    normalize_animation_name,
    normalize_expression_name,
    normalize_gaze_name,
    normalize_gesture_name,
)

SUPPORTED_ANIMATIONS = [*CANONICAL_ANIMATIONS]
STAGED_SEQUENCE_MOTION_ENVELOPE = "investor_expressive_sequence_joint_envelope_v1"
STAGED_SEQUENCE_SLOW_KINETICS = "staged_sequence_slow"
EXPRESSIVE_MOTIF_MOTION_ENVELOPE = "investor_expressive_sequence_joint_envelope_v1"
EXPRESSIVE_MOTIF_SLOW_KINETICS = "staged_sequence_slow"
_STAGED_YAW_STRUCTURAL_DEFAULTS = {
    "move_ms": 2600,
    "hold_ms": 1400,
}
_STAGED_PITCH_ROLL_STRUCTURAL_DEFAULTS = {
    "move_ms": 3000,
    "hold_ms": 1600,
}
_STAGED_YAW_RETURN_DEFAULTS = {
    "move_ms": 2200,
    "hold_ms": 0,
}
_STAGED_PITCH_ROLL_RETURN_DEFAULTS = {
    "move_ms": 2400,
    "hold_ms": 0,
}
_STAGED_EYE_SETTLE_MS = 650
_STAGED_FINAL_CONFIRM_MS = 120
_STAGED_FINAL_CONFIRM_HOLD_MS = 1800
_STAGED_EXPRESSIVE_DURATION_SCALE = 1.5
_STAGED_EXPRESSIVE_HOLD_SCALE = 1.7
_STAGED_EXPRESSIVE_EYE_YAW_GAIN = 1.82
_STAGED_EXPRESSIVE_EYE_PITCH_GAIN = 1.82
_STAGED_EXPRESSIVE_LID_GAIN = 1.15
_STAGED_EXPRESSIVE_BROW_GAIN = 1.30
_MOTIF_YAW_STRUCTURAL_DEFAULTS = {
    "move_ms": 2400,
    "hold_ms": 900,
}
_MOTIF_PITCH_ROLL_STRUCTURAL_DEFAULTS = {
    "move_ms": 3000,
    "hold_ms": 1100,
}
_MOTIF_YAW_RETURN_DEFAULTS = {
    "move_ms": 2200,
    "hold_ms": 0,
}
_MOTIF_PITCH_ROLL_RETURN_DEFAULTS = {
    "move_ms": 2400,
    "hold_ms": 0,
}
_MOTIF_EXPRESSIVE_SET_DEFAULTS = {
    "move_ms": 900,
    "hold_ms": 700,
}
_MOTIF_EXPRESSIVE_RELEASE_DEFAULTS = {
    "move_ms": 900,
    "hold_ms": 350,
}
_MOTIF_HOLD_DEFAULT_MS = 500
_MOTIF_FINAL_CONFIRM_MS = 120
_MOTIF_FINAL_CONFIRM_HOLD_MS = 1500
_STRUCTURAL_POSE_FIELDS = ("head_yaw", "head_pitch", "head_roll")
_EXPRESSIVE_POSE_FIELDS = (
    "eye_yaw",
    "eye_pitch",
    "upper_lids_open",
    "lower_lids_open",
    "upper_lid_left_open",
    "upper_lid_right_open",
    "lower_lid_left_open",
    "lower_lid_right_open",
    "brow_raise_left",
    "brow_raise_right",
)
_EXPRESSIVE_GROUP_FIELDS = {
    "eye_yaw": ("eye_yaw",),
    "eye_pitch": ("eye_pitch",),
    "upper_lids": ("upper_lid_left_open", "upper_lid_right_open"),
    "lower_lids": ("lower_lid_left_open", "lower_lid_right_open"),
    "lids": (
        "upper_lid_left_open",
        "upper_lid_right_open",
        "lower_lid_left_open",
        "lower_lid_right_open",
    ),
    "brows": ("brow_raise_left", "brow_raise_right"),
}


@dataclass(frozen=True)
class StagedSequenceAccentSpec:
    action_name: str
    intensity: float = 1.0
    note: str | None = None


@dataclass(frozen=True)
class StagedSequenceStageSpec:
    stage_kind: str
    action_name: str | None = None
    intensity: float = 1.0
    move_ms: int | None = None
    hold_ms: int | None = None
    settle_ms: int | None = None
    accents: tuple[StagedSequenceAccentSpec, ...] = ()
    note: str | None = None


def _clamp(value: float, lower: float, upper: float) -> float:
    return max(lower, min(upper, float(value)))


def _overlay_expressive_pose(*, structural_pose: BodyPose, expressive_pose: BodyPose) -> BodyPose:
    payload = structural_pose.model_dump()
    expressive_payload = expressive_pose.model_dump()
    for field_name in _EXPRESSIVE_POSE_FIELDS:
        payload[field_name] = expressive_payload[field_name]
    return BodyPose.model_validate(payload)


def _merge_expressive_groups(
    *,
    base_expressive_pose: BodyPose,
    accent_pose: BodyPose,
    expressive_groups: set[str],
) -> BodyPose:
    payload = base_expressive_pose.model_dump()
    accent_payload = accent_pose.model_dump()
    for group_name in expressive_groups:
        for field_name in _EXPRESSIVE_GROUP_FIELDS.get(group_name, ()):
            payload[field_name] = accent_payload[field_name]
    return BodyPose.model_validate(payload)


def _amplify_staged_expressive_pose(*, neutral_pose: BodyPose, expressive_pose: BodyPose) -> BodyPose:
    payload = expressive_pose.model_dump()
    neutral_payload = neutral_pose.model_dump()
    for field_name in _EXPRESSIVE_POSE_FIELDS:
        neutral_value = float(neutral_payload[field_name])
        current_value = float(payload[field_name])
        gain = 1.0
        if field_name == "eye_yaw":
            gain = _STAGED_EXPRESSIVE_EYE_YAW_GAIN
        elif field_name == "eye_pitch":
            gain = _STAGED_EXPRESSIVE_EYE_PITCH_GAIN
        elif "lid" in field_name:
            gain = _STAGED_EXPRESSIVE_LID_GAIN
        elif "brow" in field_name:
            gain = _STAGED_EXPRESSIVE_BROW_GAIN
        if gain == 1.0:
            continue
        amplified = neutral_value + ((current_value - neutral_value) * gain)
        if field_name in {"eye_yaw", "eye_pitch"}:
            payload[field_name] = _clamp(amplified, -1.0, 1.0)
        else:
            payload[field_name] = _clamp(amplified, 0.0, 1.0)
    return BodyPose.model_validate(payload)


def _is_pitch_or_roll_structural_action(action_name: str) -> bool:
    return action_name.startswith("head_pitch_") or action_name.startswith("head_tilt_")


def _staged_structural_defaults_for_action(action_name: str) -> dict[str, int]:
    if _is_pitch_or_roll_structural_action(action_name):
        return _STAGED_PITCH_ROLL_STRUCTURAL_DEFAULTS
    return _STAGED_YAW_STRUCTURAL_DEFAULTS


def _staged_return_defaults_for_action(action_name: str) -> dict[str, int]:
    if _is_pitch_or_roll_structural_action(action_name):
        return _STAGED_PITCH_ROLL_RETURN_DEFAULTS
    return _STAGED_YAW_RETURN_DEFAULTS


def _motif_structural_defaults_for_action(action_name: str) -> dict[str, int]:
    if _is_pitch_or_roll_structural_action(action_name):
        return _MOTIF_PITCH_ROLL_STRUCTURAL_DEFAULTS
    return _MOTIF_YAW_STRUCTURAL_DEFAULTS


def _motif_return_defaults_for_action(action_name: str) -> dict[str, int]:
    if _is_pitch_or_roll_structural_action(action_name):
        return _MOTIF_PITCH_ROLL_RETURN_DEFAULTS
    return _MOTIF_YAW_RETURN_DEFAULTS


def _scale_staged_ms(value: int, scale: float) -> int:
    return max(1, int(round(float(value) * scale)))


def _neutralize_expressive_groups(
    *,
    expressive_pose: BodyPose,
    neutral_pose: BodyPose,
    groups: set[str],
) -> BodyPose:
    payload = expressive_pose.model_dump()
    neutral_payload = neutral_pose.model_dump()
    for group_name in groups:
        for field_name in _EXPRESSIVE_GROUP_FIELDS.get(group_name, ()):
            payload[field_name] = neutral_payload[field_name]
    return BodyPose.model_validate(payload)


def _expressive_groups_are_neutral(
    *,
    expressive_pose: BodyPose,
    neutral_pose: BodyPose,
) -> bool:
    expressive_payload = expressive_pose.model_dump()
    neutral_payload = neutral_pose.model_dump()
    for field_name in _EXPRESSIVE_POSE_FIELDS:
        if float(expressive_payload[field_name]) != float(neutral_payload[field_name]):
            return False
    return True


_RATIO_FIELD_TO_JOINT = {
    "upper_lid_left_open": "upper_lid_left",
    "upper_lid_right_open": "upper_lid_right",
    "lower_lid_left_open": "lower_lid_left",
    "lower_lid_right_open": "lower_lid_right",
    "brow_raise_left": "brow_left",
    "brow_raise_right": "brow_right",
}
_SIGNED_ENVELOPE_FIELDS = {
    "head_yaw": "head_yaw",
    "head_pitch": "head_pitch",
    "head_roll": "head_roll",
    "eye_yaw": "eye_yaw",
    "eye_pitch": "eye_pitch",
}
_ACCENT_ACTIONS = {
    "acknowledge_light",
    "blink_soft",
    "brow_knit_soft",
    "brow_raise_soft",
    "curious_bright",
    "double_blink",
    "double_blink_emphasis",
    "eyes_widen",
    "look_far_down",
    "look_far_left",
    "look_far_right",
    "look_far_up",
    "nod_medium",
    "nod_small",
    "playful",
    "playful_peek_left",
    "playful_peek_right",
    "playful_react",
    "recover_neutral",
    "soft_reengage",
    "tilt_curious",
    "wink_left",
    "wink_right",
    "youthful_greeting",
}
_IDLE_ACTIONS = {"neutral", "safe_idle"}


class SemanticBodyCompiler:
    def __init__(
        self,
        *,
        profile: HeadProfile,
        calibration: HeadCalibrationRecord | None = None,
        tuning: SemanticTuningRecord | None = None,
        tuning_path: str | None = None,
    ) -> None:
        self.profile = profile
        self.calibration = calibration
        self.tuning = tuning or SemanticTuningRecord(profile_name=profile.profile_name)
        self.tuning_path = tuning_path
        self._ratio_neutral_pose = self._build_ratio_neutral_pose()
        self._motion_envelopes = self._build_motion_envelopes()
        self._operating_band = self._build_operating_band()
        self._kinetics_profiles = self._build_motion_kinetics_profiles()

    def set_tuning(self, tuning: SemanticTuningRecord, *, tuning_path: str | None = None) -> None:
        self.tuning = tuning
        self.tuning_path = tuning_path
        self._motion_envelopes = self._build_motion_envelopes()
        self._operating_band = self._build_operating_band()
        self._kinetics_profiles = self._build_motion_kinetics_profiles()

    def neutral_pose(self) -> BodyPose:
        return self._ratio_neutral_pose.model_copy(deep=True)

    def operating_band(self) -> DerivedOperatingBand:
        return self._operating_band.model_copy(deep=True)

    def kinetics_profiles(self) -> dict[str, MotionKineticsProfile]:
        return {name: profile.model_copy(deep=True) for name, profile in self._kinetics_profiles.items()}

    def clamp_pose(self, pose: BodyPose) -> BodyPose:
        payload: dict[str, float | None] = {}
        for field_name in SIGNED_FIELDS:
            payload[field_name] = _clamp(getattr(pose, field_name, 0.0), -1.0, 1.0)
        for field_name in RATIO_FIELDS:
            value = getattr(pose, field_name, None)
            payload[field_name] = None if value is None else _clamp(value, 0.0, 1.0)
        return BodyPose.model_validate(payload)

    def apply_expression(self, state: BodyState, expression: str | ExpressionRequest) -> BodyState:
        request = expression if isinstance(expression, ExpressionRequest) else ExpressionRequest(expression_name=str(expression))
        semantic = normalize_expression_name(request.expression_name)
        grounded_pose = build_grounded_state_pose(
            semantic.canonical_name,
            intensity=request.intensity,
            neutral_pose=self.neutral_pose(),
        )
        if grounded_pose is not None:
            timeline = AnimationTimeline(
                animation_name=semantic.canonical_name,
                keyframes=[
                    BodyKeyframe(
                        keyframe_name=semantic.canonical_name,
                        pose=grounded_pose,
                        duration_ms=180,
                        hold_ms=180,
                        semantic_name=semantic.canonical_name,
                        note=request.note,
                    )
                ],
            )
            compiled = self.compile_timeline(timeline)
            compiled.grounding = "state"
            compiled.returns_to_neutral = self._returned_to_neutral(compiled)
            updated = self._apply_compiled(
                state,
                compiled=compiled,
                timeline=timeline,
                active_expression=semantic.canonical_name,
                note=request.note,
            )
            self._decorate_preview(
                updated,
                semantic_name=semantic.canonical_name,
                source_name=request.expression_name,
                alias_used=semantic.alias_used,
                alias_source_name=semantic.source_name if semantic.alias_used else None,
            )
            return updated
        resolved = self._registered_action_timeline(semantic.canonical_name, intensity=request.intensity)
        if resolved is not None:
            return self._apply_registered_timeline(
                state,
                resolved=resolved,
                requested_name=request.expression_name,
                active_expression=semantic.canonical_name,
                note=request.note,
                alias_used=semantic.alias_used,
                alias_source_name=semantic.source_name if semantic.alias_used else None,
            )
        raise ValueError(f"unsupported_grounded_expression:{semantic.canonical_name}")

    def apply_gaze(
        self,
        state: BodyState,
        *,
        target: str | None = None,
        yaw: float | None = None,
        pitch: float | None = None,
        request: GazeRequest | None = None,
    ) -> BodyState:
        gaze_request = request or GazeRequest(target=target, yaw=yaw, pitch=pitch)
        semantic = normalize_gaze_name(gaze_request.target or "look_forward")
        intensity = gaze_request.intensity
        resolved = self._registered_action_timeline(semantic.canonical_name, intensity=intensity)
        if resolved is not None:
            return self._apply_registered_timeline(
                state,
                resolved=resolved,
                requested_name=gaze_request.target,
                gaze_target=semantic.canonical_name if gaze_request.target is not None else "custom_gaze",
                note=gaze_request.note,
                alias_used=semantic.alias_used,
                alias_source_name=semantic.source_name if semantic.alias_used else None,
            )
        anchor_pose = state.pose if state.current_frame is not None else self.neutral_pose()

        if semantic.canonical_name == "look_down_briefly":
            timeline = animation_timeline(
                semantic.canonical_name,
                anchor_pose=anchor_pose,
                intensity=intensity,
                neutral_pose=self.neutral_pose(),
            )
        elif semantic.canonical_name == "look_at_user":
            if gaze_request.yaw is None and gaze_request.pitch is None:
                pose = gaze_pose(
                    "look_forward",
                    intensity=intensity,
                    base_pose=anchor_pose,
                    neutral_pose=self.neutral_pose(),
                )
            else:
                pose = apply_pose_overrides(
                    anchor_pose,
                    eye_yaw=_clamp(gaze_request.yaw or 0.0, -1.0, 1.0) * intensity,
                    eye_pitch=_clamp(gaze_request.pitch or 0.0, -1.0, 1.0) * intensity,
                    head_yaw=_clamp((gaze_request.yaw or 0.0) * 0.35, -1.0, 1.0) * intensity,
                    head_pitch=_clamp((gaze_request.pitch or 0.0) * 0.2, -1.0, 1.0) * intensity,
                )
            timeline = AnimationTimeline(
                animation_name=semantic.canonical_name,
                keyframes=[BodyKeyframe(keyframe_name="look_at_user", pose=pose, duration_ms=140, hold_ms=160, note=gaze_request.note)],
            )
        elif semantic.canonical_name in SUPPORTED_GAZE_TARGETS:
            pose = gaze_pose(
                semantic.canonical_name,
                intensity=intensity,
                base_pose=anchor_pose,
                neutral_pose=self.neutral_pose(),
            )
            timeline = AnimationTimeline(
                animation_name=semantic.canonical_name,
                keyframes=[
                    BodyKeyframe(
                        keyframe_name=semantic.canonical_name,
                        pose=pose,
                        duration_ms=140,
                        hold_ms=160,
                        note=gaze_request.note,
                    )
                ],
            )
        else:
            pose = apply_pose_overrides(
                state.pose,
                eye_yaw=_clamp(gaze_request.yaw or 0.0, -1.0, 1.0) * intensity,
                eye_pitch=_clamp(gaze_request.pitch or 0.0, -1.0, 1.0) * intensity,
                head_yaw=_clamp((gaze_request.yaw or 0.0) * 0.35, -1.0, 1.0) * intensity,
                head_pitch=_clamp((gaze_request.pitch or 0.0) * 0.2, -1.0, 1.0) * intensity,
            )
            timeline = AnimationTimeline(
                animation_name="custom_gaze",
                keyframes=[BodyKeyframe(keyframe_name="custom_gaze", pose=pose, duration_ms=140, hold_ms=160, note=gaze_request.note)],
            )

        compiled = self.compile_timeline(timeline)
        updated = self._apply_compiled(
            state,
            compiled=compiled,
            timeline=timeline,
            gaze_target=semantic.canonical_name if gaze_request.target is not None else "custom_gaze",
            note=gaze_request.note,
        )
        self._decorate_preview(
            updated,
            semantic_name=semantic.canonical_name if gaze_request.target is not None else "custom_gaze",
            source_name=gaze_request.target,
            alias_used=semantic.alias_used,
            alias_source_name=semantic.source_name if semantic.alias_used else None,
        )
        return updated

    def apply_gesture(self, state: BodyState, gesture: str | GestureRequest) -> BodyState:
        request = gesture if isinstance(gesture, GestureRequest) else GestureRequest(gesture_name=str(gesture))
        semantic = normalize_gesture_name(request.gesture_name)
        resolved = self._registered_action_timeline(semantic.canonical_name, intensity=request.intensity)
        if resolved is not None:
            return self._apply_registered_timeline(
                state,
                resolved=resolved,
                requested_name=request.gesture_name,
                last_gesture=semantic.canonical_name,
                note=request.note,
                alias_used=semantic.alias_used,
                alias_source_name=semantic.source_name if semantic.alias_used else None,
            )
        timeline = gesture_timeline(
            semantic.canonical_name,
            anchor_pose=state.pose if state.current_frame is not None else self.neutral_pose(),
            intensity=request.intensity,
            repeat_count=request.repeat_count,
            neutral_pose=self.neutral_pose(),
        )
        if request.note:
            timeline.note = request.note
        compiled = self.compile_timeline(timeline)
        updated = self._apply_compiled(
            state,
            compiled=compiled,
            timeline=timeline,
            last_gesture=semantic.canonical_name,
            note=request.note,
        )
        self._decorate_preview(
            updated,
            semantic_name=semantic.canonical_name,
            source_name=request.gesture_name,
            alias_used=semantic.alias_used,
            alias_source_name=semantic.source_name if semantic.alias_used else None,
        )
        return updated

    def apply_animation(self, state: BodyState, animation: str | AnimationRequest) -> BodyState:
        request = animation if isinstance(animation, AnimationRequest) else AnimationRequest(animation_name=str(animation))
        semantic = normalize_animation_name(request.animation_name)
        resolved = self._registered_action_timeline(semantic.canonical_name, intensity=request.intensity)
        if resolved is not None:
            return self._apply_registered_timeline(
                state,
                resolved=resolved,
                requested_name=request.animation_name,
                active_expression=semantic.canonical_name if semantic.canonical_name in SUPPORTED_EXPRESSIONS else state.active_expression,
                gaze_target=semantic.canonical_name if semantic.canonical_name in SUPPORTED_GAZE_TARGETS else state.gaze_target,
                last_animation=semantic.canonical_name,
                note=request.note,
                alias_used=semantic.alias_used,
                alias_source_name=semantic.source_name if semantic.alias_used else None,
            )
        timeline = animation_timeline(
            semantic.canonical_name,
            anchor_pose=state.pose if state.current_frame is not None else self.neutral_pose(),
            intensity=request.intensity,
            repeat_count=request.repeat_count,
            loop=request.loop,
            neutral_pose=self.neutral_pose(),
        )
        if request.note:
            timeline.note = request.note
        compiled = self.compile_timeline(timeline)
        updated = self._apply_compiled(
            state,
            compiled=compiled,
            timeline=timeline,
            active_expression=semantic.canonical_name if semantic.canonical_name in SUPPORTED_EXPRESSIONS else state.active_expression,
            gaze_target=semantic.canonical_name if semantic.canonical_name in SUPPORTED_GAZE_TARGETS else state.gaze_target,
            last_animation=semantic.canonical_name,
            note=request.note,
        )
        self._decorate_preview(
            updated,
            semantic_name=semantic.canonical_name,
            source_name=request.animation_name,
            alias_used=semantic.alias_used,
            alias_source_name=semantic.source_name if semantic.alias_used else None,
        )
        return updated

    def apply_legacy_head_pose(self, state: BodyState, *, head_yaw_deg: float, head_pitch_deg: float) -> BodyState:
        pose = apply_pose_overrides(
            state.pose,
            head_yaw=_clamp(head_yaw_deg / 60.0, -1.0, 1.0),
            head_pitch=_clamp(head_pitch_deg / 25.0, -1.0, 1.0),
        )
        timeline = AnimationTimeline(
            animation_name="legacy_head_pose",
            keyframes=[BodyKeyframe(keyframe_name="legacy_head_pose", pose=pose, duration_ms=140)],
        )
        compiled = self.compile_timeline(timeline)
        updated = self._apply_compiled(state, compiled=compiled, timeline=timeline)
        self._decorate_preview(updated, semantic_name="legacy_head_pose", source_name="legacy_head_pose")
        return updated

    def compile_timeline(self, timeline: AnimationTimeline) -> CompiledAnimation:
        frames: list[CompiledBodyFrame] = []
        repeats = max(1, timeline.repeat_count)
        previous_pose: BodyPose | None = None
        kinetics_profiles_used: list[str] = []
        for repeat_index in range(repeats):
            for keyframe_index, keyframe in enumerate(timeline.keyframes):
                frame_name = keyframe.keyframe_name or f"frame_{keyframe_index + 1}"
                if repeats > 1:
                    frame_name = f"{frame_name}:{repeat_index + 1}"
                compiled_frame = self.compile_frame(
                    keyframe.pose,
                    frame_name=frame_name,
                    duration_ms=keyframe.duration_ms,
                    hold_ms=keyframe.hold_ms,
                    transient=keyframe.transient,
                    animation_name=timeline.animation_name,
                    semantic_name=keyframe.semantic_name or timeline.animation_name,
                    previous_pose=previous_pose,
                    motion_envelope_name_override=keyframe.motion_envelope,
                    kinetics_profile_name_override=keyframe.kinetics_profile,
                )
                frames.append(compiled_frame)
                if compiled_frame.kinetics_profile:
                    kinetics_profiles_used.append(compiled_frame.kinetics_profile)
                previous_pose = compiled_frame.pose
        total_duration_ms = sum(frame.duration_ms + frame.hold_ms for frame in frames)
        compiler_notes = [f"{frame.frame_name}:{note}" for frame in frames for note in frame.compiler_notes]
        resolved_kinetics = list(dict.fromkeys(kinetics_profiles_used))
        requested_speeds = [int(frame.requested_speed) for frame in frames if frame.requested_speed is not None]
        requested_accelerations = [
            int(frame.requested_acceleration) for frame in frames if frame.requested_acceleration is not None
        ]
        return CompiledAnimation(
            animation_name=timeline.animation_name,
            frames=frames,
            loop=timeline.loop,
            total_duration_ms=total_duration_ms,
            kinetics_profiles_used=resolved_kinetics,
            requested_speed=max(requested_speeds) if requested_speeds else None,
            requested_acceleration=max(requested_accelerations) if requested_accelerations else None,
            tuning_lane=self.tuning.tuning_lane,
            grounding=None,
            recipe_name=None,
            motif_name=None,
            primitive_steps=[],
            expressive_steps=[],
            step_kinds=[],
            sequence_step_count=None,
            returns_to_neutral=False,
            primary_actuator_group=None,
            support_actuator_groups=[],
            max_active_families=None,
            compiler_notes=compiler_notes,
        )

    def compile_primitive_sequence(
        self,
        *,
        sequence_name: str,
        steps: list[PrimitiveSequenceStepSpec],
    ) -> CompiledAnimation:
        resolved = build_primitive_sequence_timeline(
            sequence_name,
            steps=tuple(steps),
            neutral_pose=self.neutral_pose(),
            operating_band=self._operating_band,
        )
        compiled = self.compile_timeline(resolved.timeline)
        compiled.grounding = "primitive_sequence"
        compiled.recipe_name = None
        compiled.primitive_steps = list(resolved.primitive_steps)
        compiled.sequence_step_count = resolved.sequence_step_count
        compiled.returns_to_neutral = self._returned_to_neutral(compiled)
        compiled.primary_actuator_group = (
            resolved.primary_actuator_groups[0]
            if len(resolved.primary_actuator_groups) == 1
            else None
        )
        compiled.support_actuator_groups = list(resolved.support_actuator_groups)
        compiled.max_active_families = resolved.max_active_families
        compiled.compiler_notes.extend(
            [
                f"primitive_sequence:{sequence_name}",
                f"sequence_step_count:{resolved.sequence_step_count}",
                *[f"sequence_step:{name}" for name in resolved.primitive_steps],
            ]
        )
        return compiled

    def compile_staged_sequence(
        self,
        *,
        sequence_name: str,
        stages: list[StagedSequenceStageSpec],
    ) -> CompiledAnimation:
        if len(stages) != 3:
            raise ValueError("staged_sequence_requires_three_stages")
        structural_stage, expressive_stage, return_stage = stages
        if [stage.stage_kind for stage in stages] != ["structural", "expressive", "return"]:
            raise ValueError("staged_sequence_requires_structural_expressive_return")
        if not structural_stage.action_name:
            raise ValueError("staged_sequence_structural_stage_requires_action")

        neutral_pose = self.neutral_pose()
        structural_intensity = max(0.0, min(1.0, float(structural_stage.intensity)))
        structural_pose = primitive_target_pose(
            structural_stage.action_name,
            intensity=structural_intensity,
            neutral_pose=neutral_pose,
            operating_band=self._operating_band,
        )
        structural_resolved = build_registered_action_timeline(
            structural_stage.action_name,
            intensity=structural_intensity,
            neutral_pose=neutral_pose,
            operating_band=self._operating_band,
        )
        if structural_resolved is None or structural_resolved.grounding != "primitive":
            raise ValueError(f"staged_sequence_structural_action_not_primitive:{structural_stage.action_name}")
        structural_defaults = _staged_structural_defaults_for_action(structural_stage.action_name)
        return_defaults = _staged_return_defaults_for_action(structural_stage.action_name)

        structural_keyframe = BodyKeyframe(
            keyframe_name=f"{sequence_name}:structural",
            pose=structural_pose,
            duration_ms=(
                structural_stage.move_ms
                if structural_stage.move_ms is not None
                else structural_defaults["move_ms"]
            ),
            hold_ms=(
                structural_stage.hold_ms
                if structural_stage.hold_ms is not None
                else structural_defaults["hold_ms"]
            ),
            semantic_name=structural_stage.action_name,
            motion_envelope=STAGED_SEQUENCE_MOTION_ENVELOPE,
            kinetics_profile=STAGED_SEQUENCE_SLOW_KINETICS,
            note=structural_stage.note or "staged_sequence:structural",
        )

        expressive_actions: list[str] = []
        expressive_groups: set[str] = set()
        max_active_families = int(structural_resolved.max_active_families or 1)
        expressive_keyframes: list[BodyKeyframe] = []
        persistent_expressive_pose = neutral_pose.model_copy(deep=True)
        for accent_index, accent in enumerate(expressive_stage.accents, start=1):
            accent_intensity = max(0.0, min(1.0, float(accent.intensity)))
            accent_resolved = build_registered_action_timeline(
                accent.action_name,
                intensity=accent_intensity,
                neutral_pose=neutral_pose,
                operating_band=self._operating_band,
            )
            if accent_resolved is None or accent_resolved.grounding != "primitive":
                raise ValueError(f"staged_sequence_expressive_action_not_primitive:{accent.action_name}")
            expressive_actions.append(accent.action_name)
            accent_groups = {
                group
                for group in (
                    accent_resolved.primary_actuator_group,
                    *accent_resolved.support_actuator_groups,
                )
                if group
            }
            expressive_groups.update(accent_groups)
            max_active_families = max(
                max_active_families,
                1 + len(accent_groups),
            )
            last_merged_pose = persistent_expressive_pose
            for frame_index, frame in enumerate(accent_resolved.timeline.keyframes, start=1):
                amplified_pose = _amplify_staged_expressive_pose(
                    neutral_pose=neutral_pose,
                    expressive_pose=frame.pose,
                )
                merged_expressive_pose = _merge_expressive_groups(
                    base_expressive_pose=persistent_expressive_pose,
                    accent_pose=amplified_pose,
                    expressive_groups=accent_groups,
                )
                last_merged_pose = merged_expressive_pose
                expressive_keyframes.append(
                    frame.model_copy(
                        update={
                            "keyframe_name": (
                                f"{sequence_name}:expressive:{accent_index}:"
                                f"{frame_index}:{frame.keyframe_name}"
                            ),
                            "pose": _overlay_expressive_pose(
                                structural_pose=structural_pose,
                                expressive_pose=merged_expressive_pose,
                            ),
                            "duration_ms": _scale_staged_ms(
                                int(frame.duration_ms),
                                _STAGED_EXPRESSIVE_DURATION_SCALE,
                            ),
                            "hold_ms": _scale_staged_ms(
                                int(frame.hold_ms),
                                _STAGED_EXPRESSIVE_HOLD_SCALE,
                            )
                            if int(frame.hold_ms) > 0
                            else 0,
                            "motion_envelope": STAGED_SEQUENCE_MOTION_ENVELOPE,
                            "kinetics_profile": STAGED_SEQUENCE_SLOW_KINETICS,
                            "note": accent.note or f"staged_sequence:expressive:{accent.action_name}",
                        }
                    )
                )
            if not accent_resolved.returns_to_neutral:
                persistent_expressive_pose = last_merged_pose

        eye_settle_keyframe = BodyKeyframe(
            keyframe_name=f"{sequence_name}:expressive_settle",
            pose=_overlay_expressive_pose(
                structural_pose=structural_pose,
                expressive_pose=persistent_expressive_pose,
            ),
            duration_ms=(
                expressive_stage.settle_ms
                if expressive_stage.settle_ms is not None
                else _STAGED_EYE_SETTLE_MS
            ),
            hold_ms=0,
            semantic_name=structural_stage.action_name,
            motion_envelope=STAGED_SEQUENCE_MOTION_ENVELOPE,
            kinetics_profile=STAGED_SEQUENCE_SLOW_KINETICS,
            note=expressive_stage.note or "staged_sequence:expressive_settle",
        )
        return_keyframe = BodyKeyframe(
            keyframe_name=f"{sequence_name}:return",
            pose=neutral_pose.model_copy(deep=True),
            duration_ms=(
                return_stage.move_ms
                if return_stage.move_ms is not None
                else return_defaults["move_ms"]
            ),
            hold_ms=(
                return_stage.hold_ms
                if return_stage.hold_ms is not None
                else return_defaults["hold_ms"]
            ),
            semantic_name=structural_stage.action_name,
            motion_envelope=STAGED_SEQUENCE_MOTION_ENVELOPE,
            kinetics_profile=STAGED_SEQUENCE_SLOW_KINETICS,
            note=return_stage.note or "staged_sequence:return",
        )
        final_neutral_keyframe = BodyKeyframe(
            keyframe_name=f"{sequence_name}:final_neutral_confirm",
            pose=neutral_pose.model_copy(deep=True),
            duration_ms=_STAGED_FINAL_CONFIRM_MS,
            hold_ms=_STAGED_FINAL_CONFIRM_HOLD_MS,
            semantic_name="neutral",
            motion_envelope=STAGED_SEQUENCE_MOTION_ENVELOPE,
            kinetics_profile=STAGED_SEQUENCE_SLOW_KINETICS,
            note="staged_sequence:final_neutral_confirm",
        )
        timeline = AnimationTimeline(
            animation_name=sequence_name,
            keyframes=[
                structural_keyframe,
                *expressive_keyframes,
                eye_settle_keyframe,
                return_keyframe,
                final_neutral_keyframe,
            ],
            repeat_count=1,
            loop=False,
            note="staged_sequence",
        )
        compiled = self.compile_timeline(timeline)
        compiled.grounding = "staged_sequence"
        compiled.recipe_name = None
        compiled.primitive_steps = list(expressive_actions)
        compiled.sequence_step_count = len(expressive_actions)
        compiled.structural_action = structural_stage.action_name
        compiled.expressive_accents = list(expressive_actions)
        compiled.stage_count = 3
        compiled.returns_to_neutral = self._returned_to_neutral(compiled)
        compiled.primary_actuator_group = structural_resolved.primary_actuator_group
        compiled.support_actuator_groups = sorted(expressive_groups)
        compiled.max_active_families = max_active_families
        compiled.compiler_notes.extend(
            [
                f"staged_sequence:{sequence_name}",
                f"structural_action:{structural_stage.action_name}",
                *[f"expressive_accent:{name}" for name in expressive_actions],
                "stage_count:3",
            ]
        )
        return compiled

    def compile_expressive_sequence(
        self,
        *,
        sequence_name: str,
        motif_name: str | None = None,
        steps: list[ExpressiveSequenceStepSpec],
    ) -> CompiledAnimation:
        if not steps:
            raise ValueError("expressive_motif_requires_steps")
        if steps[0].step_kind != "structural_set":
            raise ValueError("expressive_motif_requires_structural_open")
        if steps[-1].step_kind != "return_to_neutral":
            raise ValueError("expressive_motif_requires_return_close")

        neutral_pose = self.neutral_pose()
        structural_pose = neutral_pose.model_copy(deep=True)
        expressive_pose = neutral_pose.model_copy(deep=True)
        structural_action: str | None = None
        structural_group: str | None = None
        expressive_actions: list[str] = []
        step_kinds: list[str] = []
        support_groups: set[str] = set()
        max_active_families = 1
        keyframes: list[BodyKeyframe] = []

        for step_index, step in enumerate(steps, start=1):
            step_kinds.append(step.step_kind)
            match step.step_kind:
                case "structural_set":
                    if structural_action is not None:
                        raise ValueError("expressive_motif_allows_single_structural_set")
                    if not step.action_name:
                        raise ValueError("expressive_motif_structural_step_requires_action")
                    structural_action = step.action_name
                    structural_intensity = max(0.0, min(1.0, float(step.intensity)))
                    structural_resolved = build_registered_action_timeline(
                        structural_action,
                        intensity=structural_intensity,
                        neutral_pose=neutral_pose,
                        operating_band=self._operating_band,
                    )
                    if structural_resolved is None or structural_resolved.grounding != "primitive":
                        raise ValueError(
                            f"expressive_motif_structural_action_not_primitive:{structural_action}"
                        )
                    structural_group = structural_resolved.primary_actuator_group
                    structural_pose = primitive_target_pose(
                        structural_action,
                        intensity=structural_intensity,
                        neutral_pose=neutral_pose,
                        operating_band=self._operating_band,
                    )
                    defaults = _motif_structural_defaults_for_action(structural_action)
                    keyframes.append(
                        BodyKeyframe(
                            keyframe_name=f"{sequence_name}:step{step_index}:structural_set",
                            pose=_overlay_expressive_pose(
                                structural_pose=structural_pose,
                                expressive_pose=expressive_pose,
                            ),
                            duration_ms=step.move_ms if step.move_ms is not None else defaults["move_ms"],
                            hold_ms=step.hold_ms if step.hold_ms is not None else defaults["hold_ms"],
                            semantic_name=structural_action,
                            motion_envelope=EXPRESSIVE_MOTIF_MOTION_ENVELOPE,
                            kinetics_profile=EXPRESSIVE_MOTIF_SLOW_KINETICS,
                            note=step.note or "expressive_motif:structural_set",
                        )
                    )
                case "expressive_set":
                    if structural_action is None:
                        raise ValueError("expressive_motif_requires_structural_before_expression")
                    if not step.action_name:
                        raise ValueError("expressive_motif_expressive_step_requires_action")
                    unit = expressive_motif_unit(step.action_name)
                    if unit is None:
                        raise ValueError(
                            f"expressive_motif_expressive_action_not_supported:{step.action_name}"
                        )
                    expressive_actions.append(step.action_name)
                    action_groups = set(unit.groups)
                    for group_name in action_groups:
                        if group_name == "lids":
                            support_groups.update({"upper_lids", "lower_lids"})
                        else:
                            support_groups.add(group_name)
                    max_active_families = max(max_active_families, 1 + len(action_groups))
                    expressive_intensity = max(0.0, min(1.0, float(step.intensity)))
                    if unit.transient:
                        transient_resolved = build_registered_action_timeline(
                            step.action_name,
                            intensity=expressive_intensity,
                            neutral_pose=neutral_pose,
                            operating_band=self._operating_band,
                        )
                        if transient_resolved is None:
                            raise ValueError(
                                f"expressive_motif_transient_action_not_supported:{step.action_name}"
                            )
                        for frame_index, frame in enumerate(transient_resolved.timeline.keyframes, start=1):
                            amplified_pose = _amplify_staged_expressive_pose(
                                neutral_pose=neutral_pose,
                                expressive_pose=frame.pose,
                            )
                            transient_pose = _merge_expressive_groups(
                                base_expressive_pose=expressive_pose,
                                accent_pose=amplified_pose,
                                expressive_groups=action_groups,
                            )
                            keyframes.append(
                                frame.model_copy(
                                    update={
                                        "keyframe_name": (
                                            f"{sequence_name}:step{step_index}:{frame_index}:"
                                            f"{frame.keyframe_name}"
                                        ),
                                        "pose": _overlay_expressive_pose(
                                            structural_pose=structural_pose,
                                            expressive_pose=transient_pose,
                                        ),
                                        "duration_ms": _scale_staged_ms(
                                            int(frame.duration_ms),
                                            _STAGED_EXPRESSIVE_DURATION_SCALE,
                                        ),
                                        "hold_ms": _scale_staged_ms(
                                            int(frame.hold_ms),
                                            _STAGED_EXPRESSIVE_HOLD_SCALE,
                                        )
                                        if int(frame.hold_ms) > 0
                                        else 0,
                                        "motion_envelope": EXPRESSIVE_MOTIF_MOTION_ENVELOPE,
                                        "kinetics_profile": EXPRESSIVE_MOTIF_SLOW_KINETICS,
                                        "note": step.note or f"expressive_motif:expressive_set:{step.action_name}",
                                    }
                                )
                            )
                    else:
                        target_pose = primitive_target_pose(
                            step.action_name,
                            intensity=expressive_intensity,
                            neutral_pose=neutral_pose,
                            operating_band=self._operating_band,
                        )
                        amplified_pose = _amplify_staged_expressive_pose(
                            neutral_pose=neutral_pose,
                            expressive_pose=target_pose,
                        )
                        expressive_pose = _merge_expressive_groups(
                            base_expressive_pose=expressive_pose,
                            accent_pose=amplified_pose,
                            expressive_groups=action_groups,
                        )
                        keyframes.append(
                            BodyKeyframe(
                                keyframe_name=f"{sequence_name}:step{step_index}:expressive_set",
                                pose=_overlay_expressive_pose(
                                    structural_pose=structural_pose,
                                    expressive_pose=expressive_pose,
                                ),
                                duration_ms=(
                                    step.move_ms
                                    if step.move_ms is not None
                                    else _MOTIF_EXPRESSIVE_SET_DEFAULTS["move_ms"]
                                ),
                                hold_ms=(
                                    step.hold_ms
                                    if step.hold_ms is not None
                                    else _MOTIF_EXPRESSIVE_SET_DEFAULTS["hold_ms"]
                                ),
                                semantic_name=step.action_name,
                                motion_envelope=EXPRESSIVE_MOTIF_MOTION_ENVELOPE,
                                kinetics_profile=EXPRESSIVE_MOTIF_SLOW_KINETICS,
                                note=step.note or f"expressive_motif:expressive_set:{step.action_name}",
                            )
                        )
                case "expressive_release":
                    if structural_action is None:
                        raise ValueError("expressive_motif_requires_structural_before_release")
                    if not step.release_groups:
                        raise ValueError("expressive_motif_release_requires_groups")
                    expressive_pose = _neutralize_expressive_groups(
                        expressive_pose=expressive_pose,
                        neutral_pose=neutral_pose,
                        groups=set(step.release_groups),
                    )
                    keyframes.append(
                        BodyKeyframe(
                            keyframe_name=f"{sequence_name}:step{step_index}:expressive_release",
                            pose=_overlay_expressive_pose(
                                structural_pose=structural_pose,
                                expressive_pose=expressive_pose,
                            ),
                            duration_ms=(
                                step.move_ms
                                if step.move_ms is not None
                                else _MOTIF_EXPRESSIVE_RELEASE_DEFAULTS["move_ms"]
                            ),
                            hold_ms=(
                                step.hold_ms
                                if step.hold_ms is not None
                                else _MOTIF_EXPRESSIVE_RELEASE_DEFAULTS["hold_ms"]
                            ),
                            semantic_name="neutral",
                            motion_envelope=EXPRESSIVE_MOTIF_MOTION_ENVELOPE,
                            kinetics_profile=EXPRESSIVE_MOTIF_SLOW_KINETICS,
                            note=step.note or "expressive_motif:expressive_release",
                        )
                    )
                case "hold":
                    keyframes.append(
                        BodyKeyframe(
                            keyframe_name=f"{sequence_name}:step{step_index}:hold",
                            pose=_overlay_expressive_pose(
                                structural_pose=structural_pose,
                                expressive_pose=expressive_pose,
                            ),
                            duration_ms=120,
                            hold_ms=step.hold_ms if step.hold_ms is not None else _MOTIF_HOLD_DEFAULT_MS,
                            semantic_name=structural_action or "neutral",
                            motion_envelope=EXPRESSIVE_MOTIF_MOTION_ENVELOPE,
                            kinetics_profile=EXPRESSIVE_MOTIF_SLOW_KINETICS,
                            note=step.note or "expressive_motif:hold",
                        )
                    )
                case "return_to_neutral":
                    if structural_action is None:
                        raise ValueError("expressive_motif_requires_structural_before_return")
                    if not _expressive_groups_are_neutral(
                        expressive_pose=expressive_pose,
                        neutral_pose=neutral_pose,
                    ):
                        raise ValueError("expressive_motif_requires_expressive_release_before_return")
                    defaults = _motif_return_defaults_for_action(structural_action)
                    structural_pose = neutral_pose.model_copy(deep=True)
                    keyframes.append(
                        BodyKeyframe(
                            keyframe_name=f"{sequence_name}:step{step_index}:return_to_neutral",
                            pose=neutral_pose.model_copy(deep=True),
                            duration_ms=step.move_ms if step.move_ms is not None else defaults["move_ms"],
                            hold_ms=step.hold_ms if step.hold_ms is not None else defaults["hold_ms"],
                            semantic_name=structural_action,
                            motion_envelope=EXPRESSIVE_MOTIF_MOTION_ENVELOPE,
                            kinetics_profile=EXPRESSIVE_MOTIF_SLOW_KINETICS,
                            note=step.note or "expressive_motif:return_to_neutral",
                        )
                    )
                case _:
                    raise ValueError(f"expressive_motif_step_kind_not_supported:{step.step_kind}")

        final_neutral_keyframe = BodyKeyframe(
            keyframe_name=f"{sequence_name}:final_neutral_confirm",
            pose=neutral_pose.model_copy(deep=True),
            duration_ms=_MOTIF_FINAL_CONFIRM_MS,
            hold_ms=_MOTIF_FINAL_CONFIRM_HOLD_MS,
            semantic_name="neutral",
            motion_envelope=EXPRESSIVE_MOTIF_MOTION_ENVELOPE,
            kinetics_profile=EXPRESSIVE_MOTIF_SLOW_KINETICS,
            note="expressive_motif:final_neutral_confirm",
        )
        timeline = AnimationTimeline(
            animation_name=sequence_name,
            keyframes=[*keyframes, final_neutral_keyframe],
            repeat_count=1,
            loop=False,
            note="expressive_motif",
        )
        compiled = self.compile_timeline(timeline)
        compiled.grounding = "expressive_motif"
        compiled.recipe_name = None
        compiled.motif_name = motif_name
        compiled.primitive_steps = []
        compiled.expressive_steps = list(expressive_actions)
        compiled.step_kinds = list(step_kinds)
        compiled.sequence_step_count = len(steps)
        compiled.structural_action = structural_action
        compiled.expressive_accents = list(expressive_actions)
        compiled.stage_count = None
        compiled.returns_to_neutral = self._returned_to_neutral(compiled)
        compiled.primary_actuator_group = structural_group
        compiled.support_actuator_groups = sorted(support_groups)
        compiled.max_active_families = max_active_families
        compiled.compiler_notes.extend(
            [
                f"expressive_motif:{motif_name or sequence_name}",
                f"structural_action:{structural_action}",
                *[f"expressive_step:{name}" for name in expressive_actions],
                *[f"step_kind:{name}" for name in step_kinds],
            ]
        )
        return compiled

    def compile_frame(
        self,
        pose: BodyPose,
        *,
        frame_name: str | None = None,
        duration_ms: int = 120,
        hold_ms: int = 0,
        transient: bool = False,
        animation_name: str | None = None,
        semantic_name: str | None = None,
        source_name: str | None = None,
        previous_pose: BodyPose | None = None,
        motion_envelope_name_override: str | None = None,
        kinetics_profile_name_override: str | None = None,
    ) -> CompiledBodyFrame:
        action_name = semantic_name or animation_name
        resolved_pose, tuning_notes, envelope_name = self._resolve_pose_with_notes(
            pose,
            action_name=action_name,
            transient=transient,
            motion_envelope_name_override=motion_envelope_name_override,
        )
        kinetics_profile_name, kinetics_profile = self._resolve_kinetics_profile(
            action_name=action_name,
            kinetics_profile_name_override=kinetics_profile_name_override,
        )
        safe_duration_ms, safe_hold_ms, transition_notes = self._apply_timing_rules(
            duration_ms,
            hold_ms=hold_ms,
            kinetics_profile=kinetics_profile,
        )
        clamp_notes = self._clamp_notes(source_pose=pose, resolved_pose=resolved_pose)
        transition_profile = self._transition_profile(
            animation_name=animation_name,
            duration_ms=safe_duration_ms,
            hold_ms=safe_hold_ms,
        )
        coupling_notes = self._coupling_notes(resolved_pose)
        safe_idle_compatible = self._safe_idle_compatible(resolved_pose)
        compiler_notes = list(transition_notes)
        compiler_notes.extend(f"tuning:{note}" for note in tuning_notes)
        compiler_notes.extend(f"clamp:{note}" for note in clamp_notes)
        compiler_notes.extend(f"coupling:{note}" for note in coupling_notes)
        if previous_pose is not None:
            compiler_notes.extend(self._delta_notes(previous_pose, resolved_pose))
        if kinetics_profile_name:
            compiler_notes.append(f"kinetics:{kinetics_profile_name}")
        if self.tuning.tuning_lane:
            compiler_notes.append(f"lane:{self.tuning.tuning_lane}")
        compiler_notes.append(f"transition_profile:{transition_profile}")
        compiler_notes.append(f"safe_idle_compatible:{str(safe_idle_compatible).lower()}")
        return CompiledBodyFrame(
            frame_name=frame_name,
            pose=resolved_pose,
            servo_targets=self.compile_servo_targets(resolved_pose),
            duration_ms=safe_duration_ms,
            hold_ms=safe_hold_ms,
            transient=transient,
            motion_envelope=envelope_name,
            kinetics_profile=kinetics_profile_name,
            requested_speed=kinetics_profile.speed if kinetics_profile is not None else None,
            requested_acceleration=kinetics_profile.acceleration if kinetics_profile is not None else None,
            tuning_lane=self.tuning.tuning_lane,
            transition_profile=transition_profile,
            safe_idle_compatible=safe_idle_compatible,
            compiler_notes=compiler_notes,
            preview=self.build_preview(
                resolved_pose,
                animation_name=animation_name,
                semantic_name=semantic_name or animation_name,
                source_name=source_name,
                clamp_notes=clamp_notes,
                transition_profile=transition_profile,
                compiler_notes=compiler_notes,
                safe_idle_compatible=safe_idle_compatible,
            ),
        )

    def compile_servo_targets(self, pose: BodyPose) -> dict[str, int]:
        pose = self._resolve_pose(pose)
        targets: dict[str, int] = {}
        joints = {joint.joint_name: joint for joint in self.profile.joints if joint.enabled}

        if "head_yaw" in joints:
            targets["head_yaw"] = self._signed_target("head_yaw", joints["head_yaw"], pose.head_yaw)
        if "head_pitch_pair_a" in joints:
            targets["head_pitch_pair_a"] = self._pitch_roll_target(
                "head_pitch_pair_a",
                joints["head_pitch_pair_a"],
                pose.head_pitch,
                pose.head_roll,
                pair="a",
            )
        if "head_pitch_pair_b" in joints:
            targets["head_pitch_pair_b"] = self._pitch_roll_target(
                "head_pitch_pair_b",
                joints["head_pitch_pair_b"],
                pose.head_pitch,
                pose.head_roll,
                pair="b",
            )
        if "eye_pitch" in joints:
            targets["eye_pitch"] = self._signed_target("eye_pitch", joints["eye_pitch"], pose.eye_pitch)
        if "eye_yaw" in joints:
            targets["eye_yaw"] = self._signed_target("eye_yaw", joints["eye_yaw"], pose.eye_yaw)

        per_joint_ratios = {
            "lower_lid_left": pose.lower_lid_left_open,
            "upper_lid_left": pose.upper_lid_left_open,
            "lower_lid_right": pose.lower_lid_right_open,
            "upper_lid_right": pose.upper_lid_right_open,
            "brow_left": pose.brow_raise_left,
            "brow_right": pose.brow_raise_right,
        }
        for joint_name, ratio in per_joint_ratios.items():
            if joint_name in joints and ratio is not None:
                targets[joint_name] = self._ratio_target(joint_name, joints[joint_name], ratio)

        return targets

    def build_preview(
        self,
        pose: BodyPose,
        *,
        animation_name: str | None = None,
        semantic_name: str | None = None,
        source_name: str | None = None,
        clamp_notes: list[str] | None = None,
        transition_profile: str | None = None,
        compiler_notes: list[str] | None = None,
        safe_idle_compatible: bool = True,
    ) -> VirtualBodyPreview:
        pose = self.clamp_pose(pose)
        left_eye_open = round((pose.upper_lid_left_open + pose.lower_lid_left_open) / 2.0, 2)
        right_eye_open = round((pose.upper_lid_right_open + pose.lower_lid_right_open) / 2.0, 2)
        gaze_direction = self._describe_gaze(pose)
        neck_pose = self._describe_neck(pose)
        lid_state = self._describe_lids(left_eye_open, right_eye_open)
        brow_state = self._describe_brows(pose)
        coupling_notes = self._coupling_notes(pose)
        preview = VirtualBodyPreview(
            gaze_direction=gaze_direction,
            gaze_summary=self._gaze_summary(pose, gaze_direction=gaze_direction),
            neck_pose=neck_pose,
            lid_state=lid_state,
            brow_state=brow_state,
            current_animation_name=animation_name,
            semantic_name=semantic_name,
            source_name=source_name,
            transition_profile=transition_profile,
            safe_idle_compatible=safe_idle_compatible,
            head_yaw=pose.head_yaw,
            head_pitch=pose.head_pitch,
            head_roll=pose.head_roll,
            eye_yaw=pose.eye_yaw,
            eye_pitch=pose.eye_pitch,
            left_eye_open=left_eye_open,
            right_eye_open=right_eye_open,
            brow_left=pose.brow_raise_left,
            brow_right=pose.brow_raise_right,
            clamp_notes=list(clamp_notes or []),
            coupling_notes=coupling_notes,
            outcome_notes=list(compiler_notes or []),
        )
        preview.summary = self._preview_summary(preview)
        return preview

    def _resolve_pose(self, pose: BodyPose, *, action_name: str | None = None) -> BodyPose:
        return self._resolve_pose_with_notes(pose, action_name=action_name)[0]

    def _resolve_pose_with_notes(
        self,
        pose: BodyPose,
        *,
        action_name: str | None = None,
        transient: bool = False,
        motion_envelope_name_override: str | None = None,
    ) -> tuple[BodyPose, list[str], str | None]:
        resolved = self.clamp_pose(pose)
        notes: list[str] = []
        override = self.tuning.action_overrides.get(action_name or "")
        envelope_name = self._resolve_motion_envelope_name(
            action_name,
            override=override,
            motion_envelope_name_override=motion_envelope_name_override,
        )
        if override is not None:
            if abs(float(override.intensity_multiplier) - 1.0) >= 0.001:
                resolved = self._scale_pose_intensity(resolved, float(override.intensity_multiplier))
                notes.append(f"action_override:{action_name}:intensity={override.intensity_multiplier:.2f}")
            if override.pose_offsets:
                resolved = self._apply_pose_offsets(resolved, override.pose_offsets)
                notes.append(f"action_override:{action_name}:pose_offsets")

        neck_pitch_weight = float(
            override.neck_pitch_weight if override is not None and override.neck_pitch_weight is not None else self.tuning.neck_pitch_weight
        )
        neck_roll_weight = float(
            override.neck_roll_weight if override is not None and override.neck_roll_weight is not None else self.tuning.neck_roll_weight
        )
        if abs(neck_pitch_weight - 1.0) >= 0.001 or abs(neck_roll_weight - 1.0) >= 0.001:
            resolved = apply_pose_overrides(
                resolved,
                head_pitch=_clamp(resolved.head_pitch * neck_pitch_weight, -1.0, 1.0),
                head_roll=_clamp(resolved.head_roll * neck_roll_weight, -1.0, 1.0),
            )
            notes.append(f"global_weight:neck={neck_pitch_weight:.2f}/{neck_roll_weight:.2f}")

        upper_lid_left_open = resolved.upper_lid_left_open
        upper_lid_right_open = resolved.upper_lid_right_open
        coupling_coefficient = float(self.tuning.eye_lid_coupling_coefficient)
        if override is not None and override.upper_lid_coupling_scale is not None:
            coupling_coefficient *= float(override.upper_lid_coupling_scale)
            notes.append(f"action_override:{action_name}:lid_coupling_scale={override.upper_lid_coupling_scale:.2f}")
        if abs(resolved.eye_pitch) >= float(self.tuning.eye_lid_coupling_threshold):
            compensation = resolved.eye_pitch * coupling_coefficient
            upper_lid_left_open = _clamp(upper_lid_left_open + compensation, 0.0, 1.0)
            upper_lid_right_open = _clamp(upper_lid_right_open + compensation, 0.0, 1.0)
            notes.append(f"global_coupling:upper_lids={coupling_coefficient:.2f}")

        resolved = self.clamp_pose(
            BodyPose.model_validate(
                {
                    **resolved.model_dump(),
                    "upper_lid_left_open": upper_lid_left_open,
                    "upper_lid_right_open": upper_lid_right_open,
                }
            )
        )
        brow_correction = float(
            override.brow_asymmetry_correction
            if override is not None and override.brow_asymmetry_correction is not None
            else self.tuning.brow_asymmetry_correction
        )
        if brow_correction > 0.0:
            average = (resolved.brow_raise_left + resolved.brow_raise_right) / 2.0
            resolved = self.clamp_pose(
                apply_pose_overrides(
                    resolved,
                    brow_raise_left=_clamp(
                        resolved.brow_raise_left + ((average - resolved.brow_raise_left) * brow_correction),
                        0.0,
                        1.0,
                    ),
                    brow_raise_right=_clamp(
                        resolved.brow_raise_right + ((average - resolved.brow_raise_right) * brow_correction),
                        0.0,
                        1.0,
                    ),
                )
            )
            notes.append(f"global_coupling:brow_asymmetry={brow_correction:.2f}")
        if envelope_name is not None:
            resolved, envelope_notes = self._apply_motion_envelope(
                resolved,
                action_name=action_name,
                envelope_name=envelope_name,
                transient=transient,
            )
            notes.extend(envelope_notes)
        resolved, operating_band_notes = self._apply_operating_band(resolved, transient=transient)
        notes.extend(operating_band_notes)
        resolved, combination_notes = self._apply_combination_rules(
            resolved,
            transient=transient,
            envelope_name=envelope_name,
        )
        notes.extend(combination_notes)
        return self.clamp_pose(resolved), notes, envelope_name

    def _scale_pose_intensity(self, pose: BodyPose, multiplier: float) -> BodyPose:
        multiplier = max(0.0, float(multiplier))
        payload = pose.model_dump()
        for field_name in SIGNED_FIELDS:
            payload[field_name] = _clamp(float(payload.get(field_name, 0.0)) * multiplier, -1.0, 1.0)
        for field_name in RATIO_FIELDS:
            value = payload.get(field_name)
            if value is None:
                continue
            neutral_value = getattr(self._ratio_neutral_pose, field_name)
            payload[field_name] = _clamp(
                float(neutral_value) + ((float(value) - float(neutral_value)) * multiplier),
                0.0,
                1.0,
            )
        return self.clamp_pose(BodyPose.model_validate(payload))

    def _apply_pose_offsets(self, pose: BodyPose, offsets: dict[str, float]) -> BodyPose:
        payload = pose.model_dump()
        for field_name, delta in offsets.items():
            if field_name not in payload:
                continue
            base_value = payload.get(field_name)
            if base_value is None:
                continue
            if field_name in SIGNED_FIELDS:
                payload[field_name] = _clamp(float(base_value) + float(delta), -1.0, 1.0)
            else:
                payload[field_name] = _clamp(float(base_value) + float(delta), 0.0, 1.0)
        return self.clamp_pose(BodyPose.model_validate(payload))

    def _build_ratio_neutral_pose(self) -> BodyPose:
        payload = BodyPose().model_dump()
        for field_name, joint_name in _RATIO_FIELD_TO_JOINT.items():
            payload[field_name] = self._joint_neutral_ratio(joint_name)
        return BodyPose.model_validate(payload)

    def _joint_neutral_ratio(self, joint_name: str) -> float:
        joint_lookup = {joint.joint_name: joint for joint in self.profile.joints if joint.enabled}
        joint = joint_lookup[joint_name]
        calibration_lookup = {
            record.joint_name: record
            for record in (self.calibration.joint_records if self.calibration is not None else [])
        }
        source = calibration_lookup.get(joint_name)
        raw_min = int(source.raw_min if source is not None else joint.raw_min)
        raw_max = int(source.raw_max if source is not None else joint.raw_max)
        neutral = int(source.neutral if source is not None else joint.neutral)
        span = max(1, raw_max - raw_min)
        direction = str(joint.positive_direction).lower()
        positive = "raw_minus" not in direction and "close" not in direction
        if positive:
            return _clamp((neutral - raw_min) / span, 0.0, 1.0)
        return _clamp((raw_max - neutral) / span, 0.0, 1.0)

    def _build_motion_envelopes(self) -> dict[str, MotionEnvelope]:
        envelopes = {
            "idle": MotionEnvelope(
                head_yaw=0.12,
                head_pitch=0.08,
                head_roll=0.08,
                eye_yaw=0.16,
                eye_pitch=0.2,
                upper_lid_deviation=0.1,
                lower_lid_deviation=0.1,
                brow_deviation=0.08,
                transient_upper_lid_deviation=0.72,
                transient_lower_lid_deviation=0.72,
                pitch_roll_budget=0.14,
            ),
            "social": MotionEnvelope(
                head_yaw=0.44,
                head_pitch=0.22,
                head_roll=0.18,
                eye_yaw=0.24,
                eye_pitch=0.38,
                upper_lid_deviation=0.14,
                lower_lid_deviation=0.14,
                brow_deviation=0.18,
                transient_upper_lid_deviation=0.74,
                transient_lower_lid_deviation=0.74,
                pitch_roll_budget=0.34,
            ),
            "accent": MotionEnvelope(
                head_yaw=0.62,
                head_pitch=0.3,
                head_roll=0.24,
                eye_yaw=0.28,
                eye_pitch=0.48,
                upper_lid_deviation=0.18,
                lower_lid_deviation=0.18,
                brow_deviation=0.24,
                transient_upper_lid_deviation=0.8,
                transient_lower_lid_deviation=0.8,
                pitch_roll_budget=0.44,
            ),
            PRIMITIVE_MOTION_ENVELOPE: MotionEnvelope(
                head_yaw=1.0,
                head_pitch=1.0,
                head_roll=1.0,
                eye_yaw=1.0,
                eye_pitch=1.0,
                upper_lid_deviation=1.0,
                lower_lid_deviation=1.0,
                brow_deviation=1.0,
                transient_upper_lid_deviation=1.0,
                transient_lower_lid_deviation=1.0,
                transient_brow_deviation=1.0,
                pitch_roll_budget=2.0,
            ),
        }
        envelopes.update({name: envelope.model_copy(deep=True) for name, envelope in self.tuning.motion_envelopes.items()})
        return envelopes

    def _build_operating_band(self) -> DerivedOperatingBand:
        return derive_operating_band(
            profile=self.profile,
            calibration=self.calibration,
            policy=self.tuning.operating_band_policy,
        )

    def _build_motion_kinetics_profiles(self) -> dict[str, MotionKineticsProfile]:
        return resolve_motion_kinetics_profiles(self.tuning)

    def _resolve_motion_envelope_name(
        self,
        action_name: str | None,
        *,
        override,
        motion_envelope_name_override: str | None = None,
    ) -> str | None:
        if motion_envelope_name_override:
            return motion_envelope_name_override
        if override is not None and override.motion_envelope:
            return override.motion_envelope
        normalized = str(action_name or "").strip().lower()
        if not normalized:
            return None
        if is_primitive_action(normalized):
            return PRIMITIVE_MOTION_ENVELOPE
        if is_recipe_action(normalized) and self._primitive_grounded_mode():
            return PRIMITIVE_MOTION_ENVELOPE
        if normalized in _IDLE_ACTIONS:
            return "idle"
        if normalized in _ACCENT_ACTIONS or normalized.startswith("look_far_"):
            return "accent"
        return self.tuning.default_motion_envelope or "social"

    def _motion_envelope(self, name: str) -> MotionEnvelope:
        return self._motion_envelopes.get(name, self._motion_envelopes["social"])

    def _resolve_kinetics_profile(
        self,
        *,
        action_name: str | None,
        kinetics_profile_name_override: str | None = None,
    ) -> tuple[str | None, MotionKineticsProfile | None]:
        if kinetics_profile_name_override:
            return kinetics_profile_name_override, self._kinetics_profiles.get(kinetics_profile_name_override)
        override = self.tuning.action_overrides.get(action_name or "")
        profile_name = (
            override.kinetics_profile
            if override is not None and override.kinetics_profile
            else self._default_kinetics_profile_name(action_name)
        )
        if not profile_name:
            return None, None
        return profile_name, self._kinetics_profiles.get(profile_name)

    def _default_kinetics_profile_name(self, action_name: str | None) -> str:
        normalized = str(action_name or "").strip().lower()
        if normalized.endswith("_slow"):
            return PRIMITIVE_SLOW_KINETICS
        if normalized.endswith("_fast"):
            return PRIMITIVE_FAST_KINETICS
        if normalized in {"safe_idle", "recover_neutral", "neutral"}:
            return "calm_settle"
        if normalized in {"blink_soft", "double_blink", "double_blink_emphasis", "wink_left", "wink_right"}:
            return "blink_transient"
        if normalized in _ACCENT_ACTIONS or normalized.startswith("look_far_"):
            return "accent_punctuate"
        return self.tuning.default_kinetics_profile or "social_shift"

    def _apply_motion_envelope(
        self,
        pose: BodyPose,
        *,
        action_name: str | None,
        envelope_name: str,
        transient: bool,
    ) -> tuple[BodyPose, list[str]]:
        envelope = self._motion_envelope(envelope_name)
        payload = pose.model_dump()
        notes: list[str] = []

        for field_name, envelope_field in _SIGNED_ENVELOPE_FIELDS.items():
            limit = float(getattr(envelope, envelope_field))
            original = float(payload.get(field_name, 0.0))
            clamped = _clamp(original, -limit, limit)
            if abs(clamped - original) >= 0.0001:
                notes.append(f"envelope:{envelope_name}:{field_name}")
            payload[field_name] = clamped

        pitch = abs(float(payload["head_pitch"]))
        roll = abs(float(payload["head_roll"]))
        combined = pitch + roll
        if combined > 0 and combined > float(envelope.pitch_roll_budget):
            scale = float(envelope.pitch_roll_budget) / combined
            payload["head_pitch"] = float(payload["head_pitch"]) * scale
            payload["head_roll"] = float(payload["head_roll"]) * scale
            notes.append(f"envelope:{envelope_name}:pitch_roll_budget")

        for field_name, joint_name in _RATIO_FIELD_TO_JOINT.items():
            original = payload.get(field_name)
            if original is None:
                continue
            neutral = float(getattr(self._ratio_neutral_pose, field_name))
            if joint_name.startswith("upper_lid"):
                limit = envelope.transient_upper_lid_deviation if transient and envelope.transient_upper_lid_deviation is not None else envelope.upper_lid_deviation
            elif joint_name.startswith("lower_lid"):
                limit = envelope.transient_lower_lid_deviation if transient and envelope.transient_lower_lid_deviation is not None else envelope.lower_lid_deviation
            else:
                limit = envelope.transient_brow_deviation if transient and envelope.transient_brow_deviation is not None else envelope.brow_deviation
            delta = _clamp(float(original) - neutral, -float(limit), float(limit))
            clamped = _clamp(neutral + delta, 0.0, 1.0)
            if abs(clamped - float(original)) >= 0.0001:
                notes.append(f"envelope:{envelope_name}:{field_name}")
            payload[field_name] = clamped

        return self.clamp_pose(BodyPose.model_validate(payload)), notes

    def _apply_operating_band(
        self,
        pose: BodyPose,
        *,
        transient: bool,
    ) -> tuple[BodyPose, list[str]]:
        payload = pose.model_dump()
        notes: list[str] = []
        axis_bands = {
            "head_yaw": self._operating_band.head_yaw,
            "head_pitch": self._operating_band.head_pitch,
            "head_roll": self._operating_band.head_roll,
            "eye_yaw": self._operating_band.eye_yaw,
            "eye_pitch": self._operating_band.eye_pitch,
        }
        for field_name, band in axis_bands.items():
            original = float(payload.get(field_name, 0.0))
            lower = -float(band.negative_limit)
            upper = float(band.positive_limit)
            clamped = _clamp(original, lower, upper)
            if abs(clamped - original) >= 0.0001:
                notes.append(f"operating_band:{field_name}")
            payload[field_name] = clamped

        ratio_bands = {
            "upper_lid_left_open": self._operating_band.upper_lid,
            "upper_lid_right_open": self._operating_band.upper_lid,
            "lower_lid_left_open": self._operating_band.lower_lid,
            "lower_lid_right_open": self._operating_band.lower_lid,
            "brow_raise_left": self._operating_band.brow,
            "brow_raise_right": self._operating_band.brow,
        }
        for field_name, band in ratio_bands.items():
            original = payload.get(field_name)
            if original is None:
                continue
            neutral = float(getattr(self._ratio_neutral_pose, field_name))
            negative_limit = (
                band.transient_negative_limit
                if transient and band.transient_negative_limit is not None
                else band.negative_limit
            )
            positive_limit = (
                band.transient_positive_limit
                if transient and band.transient_positive_limit is not None
                else band.positive_limit
            )
            delta = float(original) - neutral
            clamped_delta = _clamp(delta, -float(negative_limit), float(positive_limit))
            clamped = _clamp(neutral + clamped_delta, 0.0, 1.0)
            if abs(clamped - float(original)) >= 0.0001:
                notes.append(f"operating_band:{field_name}")
            payload[field_name] = clamped
        return self.clamp_pose(BodyPose.model_validate(payload)), notes

    def _apply_combination_rules(
        self,
        pose: BodyPose,
        *,
        transient: bool,
        envelope_name: str | None,
    ) -> tuple[BodyPose, list[str]]:
        if transient:
            return pose, []

        payload = pose.model_dump()
        notes: list[str] = []
        envelope = self._motion_envelope(envelope_name or self.tuning.default_motion_envelope or "social")

        pitch_limit = min(
            max(float(self._operating_band.head_pitch.negative_limit), float(self._operating_band.head_pitch.positive_limit)),
            float(envelope.head_pitch),
        )
        if float(payload.get("head_roll", 0.0)) >= 0:
            roll_operating_limit = float(self._operating_band.head_roll.positive_limit)
        else:
            roll_operating_limit = float(self._operating_band.head_roll.negative_limit)
        roll_limit = min(roll_operating_limit, float(envelope.head_roll))
        pitch = abs(float(payload.get("head_pitch", 0.0)))
        roll = abs(float(payload.get("head_roll", 0.0)))
        if pitch_limit > 0 and roll_limit > 0:
            neck_combined_occupancy = (pitch / pitch_limit) + (roll / roll_limit)
            if neck_combined_occupancy > 1.35:
                scale = 1.35 / neck_combined_occupancy
                payload["head_pitch"] = float(payload["head_pitch"]) * scale
                payload["head_roll"] = float(payload["head_roll"]) * scale
                notes.append("combination:neck_pitch_tilt_budget")

        eye_pitch_limit = min(
            max(float(self._operating_band.eye_pitch.negative_limit), float(self._operating_band.eye_pitch.positive_limit)),
            float(envelope.eye_pitch),
        )
        eye_pitch = abs(float(payload.get("eye_pitch", 0.0)))
        upper_dev = max(
            abs(float(payload["upper_lid_left_open"]) - float(self._ratio_neutral_pose.upper_lid_left_open)),
            abs(float(payload["upper_lid_right_open"]) - float(self._ratio_neutral_pose.upper_lid_right_open)),
        )
        lower_dev = max(
            abs(float(payload["lower_lid_left_open"]) - float(self._ratio_neutral_pose.lower_lid_left_open)),
            abs(float(payload["lower_lid_right_open"]) - float(self._ratio_neutral_pose.lower_lid_right_open)),
        )
        lid_dev = max(upper_dev, lower_dev)
        held_upper_limit = min(
            max(float(self._operating_band.upper_lid.negative_limit), float(self._operating_band.upper_lid.positive_limit)),
            float(envelope.upper_lid_deviation),
        )
        held_lower_limit = min(
            max(float(self._operating_band.lower_lid.negative_limit), float(self._operating_band.lower_lid.positive_limit)),
            float(envelope.lower_lid_deviation),
        )
        held_lid_limit = max(held_upper_limit, held_lower_limit)
        lid_occupancy = lid_dev / held_lid_limit if held_lid_limit > 0 else 0.0
        eye_pitch_occupancy = eye_pitch / eye_pitch_limit if eye_pitch_limit > 0 else 0.0
        if (
            eye_pitch_limit > 0
            and held_lid_limit > 0
            and (
                (eye_pitch_occupancy >= 0.82 and lid_occupancy >= 0.78)
                or (eye_pitch >= 0.3 and lid_dev >= 0.1)
            )
        ):
            scale = 0.74
            payload["upper_lid_left_open"] = self._scaled_ratio_field(
                payload["upper_lid_left_open"],
                neutral=float(self._ratio_neutral_pose.upper_lid_left_open),
                scale=scale,
            )
            payload["upper_lid_right_open"] = self._scaled_ratio_field(
                payload["upper_lid_right_open"],
                neutral=float(self._ratio_neutral_pose.upper_lid_right_open),
                scale=scale,
            )
            payload["lower_lid_left_open"] = self._scaled_ratio_field(
                payload["lower_lid_left_open"],
                neutral=float(self._ratio_neutral_pose.lower_lid_left_open),
                scale=scale,
            )
            payload["lower_lid_right_open"] = self._scaled_ratio_field(
                payload["lower_lid_right_open"],
                neutral=float(self._ratio_neutral_pose.lower_lid_right_open),
                scale=scale,
            )
            notes.append("combination:eye_pitch_vs_lids")

        brow_dev = max(
            abs(float(payload["brow_raise_left"]) - float(self._ratio_neutral_pose.brow_raise_left)),
            abs(float(payload["brow_raise_right"]) - float(self._ratio_neutral_pose.brow_raise_right)),
        )
        brow_limit = min(
            max(float(self._operating_band.brow.negative_limit), float(self._operating_band.brow.positive_limit)),
            float(envelope.brow_deviation),
        )
        brow_occupancy = brow_dev / brow_limit if brow_limit > 0 else 0.0
        if brow_limit > 0 and held_lid_limit > 0 and brow_occupancy >= 0.72 and lid_occupancy >= 0.72:
            scale = 0.82
            for field_name, neutral in (
                ("upper_lid_left_open", float(self._ratio_neutral_pose.upper_lid_left_open)),
                ("upper_lid_right_open", float(self._ratio_neutral_pose.upper_lid_right_open)),
                ("lower_lid_left_open", float(self._ratio_neutral_pose.lower_lid_left_open)),
                ("lower_lid_right_open", float(self._ratio_neutral_pose.lower_lid_right_open)),
                ("brow_raise_left", float(self._ratio_neutral_pose.brow_raise_left)),
                ("brow_raise_right", float(self._ratio_neutral_pose.brow_raise_right)),
            ):
                payload[field_name] = self._scaled_ratio_field(payload[field_name], neutral=neutral, scale=scale)
            notes.append("combination:held_lid_brow_budget")
        return self.clamp_pose(BodyPose.model_validate(payload)), notes

    def _scaled_ratio_field(self, value: float, *, neutral: float, scale: float) -> float:
        return _clamp(neutral + ((float(value) - neutral) * scale), 0.0, 1.0)

    def _apply_compiled(
        self,
        state: BodyState,
        *,
        compiled: CompiledAnimation,
        timeline: AnimationTimeline | None = None,
        active_expression: str | None = None,
        gaze_target: str | None = None,
        last_gesture: str | None = None,
        last_animation: str | None = None,
        note: str | None = None,
    ) -> BodyState:
        final_frame = compiled.frames[-1] if compiled.frames else self.compile_frame(self.neutral_pose())
        state.pose = final_frame.pose
        state.servo_targets = final_frame.servo_targets
        state.current_frame = final_frame
        state.virtual_preview = final_frame.preview
        state.active_timeline = timeline
        state.compiled_animation = compiled
        if active_expression is not None:
            state.active_expression = active_expression
        if gaze_target is not None:
            state.gaze_target = gaze_target
        if last_gesture is not None:
            state.last_gesture = last_gesture
        if last_animation is not None:
            state.last_animation = last_animation
        state.clamp_notes = list(final_frame.preview.clamp_notes) if final_frame.preview is not None else []
        state.notes = [note] if note else []
        return state

    def _decorate_preview(
        self,
        state: BodyState,
        *,
        semantic_name: str,
        source_name: str | None,
        alias_used: bool = False,
        alias_source_name: str | None = None,
    ) -> None:
        preview = state.virtual_preview
        if preview is None:
            return
        preview.semantic_name = semantic_name
        preview.source_name = source_name
        preview.alias_used = alias_used
        preview.alias_source_name = alias_source_name
        preview.summary = self._preview_summary(preview)
        if state.current_frame is not None and state.current_frame.preview is not None:
            state.current_frame.preview = preview.model_copy(deep=True)

    def _registered_action_timeline(self, action_name: str, *, intensity: float):
        if not is_primitive_action(action_name) and not is_recipe_action(action_name):
            return None
        return build_registered_action_timeline(
            action_name,
            intensity=intensity,
            neutral_pose=self.neutral_pose(),
            operating_band=self._operating_band,
        )

    def _primitive_grounded_mode(self) -> bool:
        return (self.tuning.default_motion_envelope or "").strip().lower() == PRIMITIVE_MOTION_ENVELOPE

    def _apply_registered_timeline(
        self,
        state: BodyState,
        *,
        resolved,
        requested_name: str | None,
        active_expression: str | None = None,
        gaze_target: str | None = None,
        last_gesture: str | None = None,
        last_animation: str | None = None,
        note: str | None = None,
        alias_used: bool = False,
        alias_source_name: str | None = None,
    ) -> BodyState:
        timeline = resolved.timeline.model_copy(deep=True)
        if note:
            timeline.note = note
        compiled = self.compile_timeline(timeline)
        compiled.grounding = resolved.grounding
        compiled.recipe_name = resolved.recipe_name
        compiled.primitive_steps = list(resolved.primitive_steps)
        compiled.returns_to_neutral = self._returned_to_neutral(compiled)
        compiled.primary_actuator_group = resolved.primary_actuator_group
        compiled.support_actuator_groups = list(resolved.support_actuator_groups)
        compiled.max_active_families = resolved.max_active_families
        updated = self._apply_compiled(
            state,
            compiled=compiled,
            timeline=timeline,
            active_expression=active_expression,
            gaze_target=gaze_target,
            last_gesture=last_gesture,
            last_animation=last_animation,
            note=note,
        )
        self._decorate_preview(
            updated,
            semantic_name=resolved.canonical_name,
            source_name=requested_name,
            alias_used=alias_used,
            alias_source_name=alias_source_name,
        )
        return updated

    def _returned_to_neutral(self, compiled: CompiledAnimation) -> bool:
        if not compiled.frames:
            return False
        final_pose = compiled.frames[-1].pose
        neutral_pose = self.neutral_pose()
        for field_name in SIGNED_FIELDS + RATIO_FIELDS:
            final_value = getattr(final_pose, field_name, None)
            neutral_value = getattr(neutral_pose, field_name, None)
            if final_value is None or neutral_value is None:
                continue
            if abs(float(final_value) - float(neutral_value)) > 0.02:
                return False
        return True

    def _joint_raw_values(self, joint_name: str, joint) -> tuple[int, int, int]:
        if self.calibration is not None:
            for record in self.calibration.joint_records:
                if record.joint_name == joint_name:
                    return int(record.neutral), int(record.raw_min), int(record.raw_max)
        return int(joint.neutral), int(joint.raw_min), int(joint.raw_max)

    def _signed_target(self, joint_name: str, joint, normalized: float) -> int:
        normalized = _clamp(normalized, -1.0, 1.0)
        neutral, raw_min, raw_max = self._joint_raw_values(joint_name, joint)
        positive_span = raw_max - neutral
        negative_span = neutral - raw_min
        if normalized >= 0:
            raw = neutral + positive_span * normalized
        else:
            raw = neutral + negative_span * normalized
        return int(round(_clamp(raw, raw_min, raw_max)))

    def _ratio_target(self, joint_name: str, joint, ratio: float) -> int:
        ratio = _clamp(ratio, 0.0, 1.0)
        direction = str(joint.positive_direction).lower()
        positive = "raw_minus" not in direction and "close" not in direction
        _, raw_min, raw_max = self._joint_raw_values(joint_name, joint)
        if positive:
            raw = raw_min + (raw_max - raw_min) * ratio
        else:
            raw = raw_max - (raw_max - raw_min) * ratio
        return int(round(_clamp(raw, raw_min, raw_max)))

    def _pitch_roll_target(self, joint_name: str, joint, pitch: float, roll: float, *, pair: str) -> int:
        pitch = _clamp(pitch, -1.0, 1.0)
        roll = _clamp(roll, -1.0, 1.0)
        neutral, raw_min, raw_max = self._joint_raw_values(joint_name, joint)
        positive_span = raw_max - neutral
        negative_span = neutral - raw_min
        pitch_delta = positive_span * pitch if pitch >= 0 else negative_span * pitch
        raw = neutral + pitch_delta if pair == "a" else neutral - pitch_delta
        if pair == "a" and roll > 0:
            raw += positive_span * roll
        if pair == "b" and roll < 0:
            raw += negative_span * roll
        return int(round(_clamp(raw, raw_min, raw_max)))

    def _describe_gaze(self, pose: BodyPose) -> str:
        horizontal = ""
        vertical = ""
        if pose.eye_yaw >= 0.22:
            horizontal = "right"
        elif pose.eye_yaw <= -0.22:
            horizontal = "left"
        if pose.eye_pitch >= 0.2:
            vertical = "up"
        elif pose.eye_pitch <= -0.2:
            vertical = "down"
        if vertical and horizontal:
            return f"{vertical}-{horizontal}"
        return vertical or horizontal or "forward"

    def _gaze_summary(self, pose: BodyPose, *, gaze_direction: str) -> str:
        head = f"head({pose.head_yaw:.2f},{pose.head_pitch:.2f})"
        eyes = f"eyes({pose.eye_yaw:.2f},{pose.eye_pitch:.2f})"
        return f"{gaze_direction} {head} {eyes}"

    def _describe_neck(self, pose: BodyPose) -> str:
        parts = []
        parts.append("yaw:right" if pose.head_yaw >= 0.15 else "yaw:left" if pose.head_yaw <= -0.15 else "yaw:center")
        parts.append("pitch:up" if pose.head_pitch >= 0.1 else "pitch:down" if pose.head_pitch <= -0.1 else "pitch:level")
        parts.append("roll:right" if pose.head_roll >= 0.1 else "roll:left" if pose.head_roll <= -0.1 else "roll:level")
        return " ".join(parts)

    def _describe_lids(self, left_eye_open: float, right_eye_open: float) -> str:
        if left_eye_open <= 0.15 and right_eye_open <= 0.15:
            return "blink"
        if left_eye_open <= 0.2 and right_eye_open >= 0.45:
            return "wink_left"
        if right_eye_open <= 0.2 and left_eye_open >= 0.45:
            return "wink_right"
        average = (left_eye_open + right_eye_open) / 2.0
        if average <= 0.5:
            return "sleepy"
        if average >= 0.92:
            return "wide_open"
        return "open"

    def _describe_brows(self, pose: BodyPose) -> str:
        delta = pose.brow_raise_left - pose.brow_raise_right
        average = (pose.brow_raise_left + pose.brow_raise_right) / 2.0
        if delta >= 0.12:
            return "left_raised"
        if delta <= -0.12:
            return "right_raised"
        if average >= 0.45:
            return "raised"
        if average <= 0.08:
            return "neutral"
        return "soft_raise"

    def _clamp_notes(self, *, source_pose: BodyPose, resolved_pose: BodyPose) -> list[str]:
        notes: list[str] = []
        source_payload = source_pose.model_dump()
        resolved_payload = resolved_pose.model_dump()
        for field_name in SIGNED_FIELDS + RATIO_FIELDS:
            source_value = source_payload.get(field_name)
            resolved_value = resolved_payload.get(field_name)
            if source_value is None or resolved_value is None:
                continue
            if abs(float(source_value) - float(resolved_value)) >= 0.001:
                notes.append(f"{field_name}:{source_value:.3f}->{resolved_value:.3f}")
        return notes

    def _delta_notes(self, previous_pose: BodyPose, resolved_pose: BodyPose) -> list[str]:
        notes: list[str] = []
        for field_name in SIGNED_FIELDS + RATIO_FIELDS:
            previous_value = getattr(previous_pose, field_name, None)
            resolved_value = getattr(resolved_pose, field_name, None)
            if previous_value is None or resolved_value is None:
                continue
            delta = abs(float(previous_value) - float(resolved_value))
            if delta >= 0.35:
                notes.append(f"rate_limited_review:{field_name}:{delta:.3f}")
        return notes

    def _apply_timing_rules(
        self,
        duration_ms: int,
        *,
        hold_ms: int,
        kinetics_profile: MotionKineticsProfile | None,
    ) -> tuple[int, int, list[str]]:
        notes: list[str] = []
        resolved_duration = int(duration_ms)
        resolved_hold = max(0, int(hold_ms or 0))
        if kinetics_profile is not None:
            if abs(float(kinetics_profile.duration_scale) - 1.0) >= 0.001:
                scaled_duration = max(1, int(round(resolved_duration * float(kinetics_profile.duration_scale))))
                notes.append(f"timing_scale:duration:{resolved_duration}->{scaled_duration}")
                resolved_duration = scaled_duration
            if resolved_hold > 0 and abs(float(kinetics_profile.hold_scale) - 1.0) >= 0.001:
                scaled_hold = max(0, int(round(resolved_hold * float(kinetics_profile.hold_scale))))
                notes.append(f"timing_scale:hold:{resolved_hold}->{scaled_hold}")
                resolved_hold = scaled_hold
        if resolved_duration <= 0:
            notes.append(f"transition_default:{resolved_duration}->{self.profile.default_transition_ms}")
            resolved_duration = int(self.profile.default_transition_ms)
        if resolved_duration < self.profile.minimum_transition_ms:
            notes.append(f"transition_minimum:{resolved_duration}->{self.profile.minimum_transition_ms}")
            resolved_duration = int(self.profile.minimum_transition_ms)
        return resolved_duration, resolved_hold, notes

    def _transition_profile(self, *, animation_name: str | None, duration_ms: int, hold_ms: int) -> str:
        if animation_name == "safe_idle":
            return "safe_idle"
        if duration_ms >= max(self.profile.neutral_recovery_ms, 220):
            return "settled"
        if hold_ms >= 120:
            return "hold"
        if duration_ms <= max(self.profile.minimum_transition_ms, 80):
            return "quick"
        return "standard"

    def _safe_idle_compatible(self, pose: BodyPose) -> bool:
        return (
            abs(pose.head_yaw) <= 0.35
            and abs(pose.head_pitch) <= 0.35
            and abs(pose.head_roll) <= 0.3
            and abs(pose.eye_yaw) <= 0.7
            and abs(pose.eye_pitch) <= 0.7
        )

    def _coupling_notes(self, pose: BodyPose) -> list[str]:
        notes: list[str] = []
        if abs(pose.head_pitch) >= 0.01 or abs(pose.head_roll) >= 0.01:
            notes.append("neck_pitch_roll")
        if abs(pose.eye_pitch) >= float(self.tuning.eye_lid_coupling_threshold):
            notes.append("eyes_follow_lids")
        if abs((pose.upper_lid_left_open or 0.0) - (pose.upper_lid_right_open or 0.0)) >= 0.01 or abs((pose.lower_lid_left_open or 0.0) - (pose.lower_lid_right_open or 0.0)) >= 0.01:
            notes.append("mirrored_eyelids")
        if abs(pose.brow_raise_left - pose.brow_raise_right) >= 0.01:
            notes.append("mirrored_brows")
        return notes

    def _preview_summary(self, preview: VirtualBodyPreview) -> str:
        parts = [
            f"semantic={preview.semantic_name or preview.current_animation_name or 'static'}",
            f"source={preview.source_name or '-'}",
            f"gaze={preview.gaze_direction}",
            f"gaze_summary={preview.gaze_summary}",
            f"neck={preview.neck_pose}",
            f"lids={preview.lid_state}",
            f"brows={preview.brow_state}",
            f"transition={preview.transition_profile or '-'}",
            f"safe_idle={'yes' if preview.safe_idle_compatible else 'no'}",
        ]
        if preview.alias_used:
            parts.append(f"alias={preview.alias_source_name or preview.source_name or '-'}")
        if preview.clamp_notes:
            parts.append(f"clamps={','.join(preview.clamp_notes)}")
        if preview.coupling_notes:
            parts.append(f"couplings={','.join(preview.coupling_notes)}")
        if preview.outcome_notes:
            parts.append(f"notes={','.join(preview.outcome_notes[:4])}")
        return " | ".join(parts)


__all__ = ["SUPPORTED_ANIMATIONS", "SUPPORTED_EXPRESSIONS", "SUPPORTED_GAZE_TARGETS", "SUPPORTED_GESTURES", "SemanticBodyCompiler"]
