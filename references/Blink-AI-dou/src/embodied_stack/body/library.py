from __future__ import annotations

from embodied_stack.shared.contracts.body import BodyPose

from .semantics import (
    CANONICAL_EXPRESSIONS,
    CANONICAL_GAZE_TARGETS,
    CANONICAL_GESTURES,
    normalize_expression_name,
    normalize_gaze_name,
)

SIGNED_FIELDS = ("head_yaw", "head_pitch", "head_roll", "eye_yaw", "eye_pitch")
RATIO_FIELDS = (
    "upper_lids_open",
    "lower_lids_open",
    "upper_lid_left_open",
    "upper_lid_right_open",
    "lower_lid_left_open",
    "lower_lid_right_open",
    "brow_raise_left",
    "brow_raise_right",
)

SUPPORTED_GAZE_TARGETS = [*CANONICAL_GAZE_TARGETS]
SUPPORTED_EXPRESSIONS = [*CANONICAL_EXPRESSIONS]
SUPPORTED_GESTURES = [*CANONICAL_GESTURES]

_TEMPLATE_NEUTRAL_POSE = BodyPose(
    upper_lid_left_open=0.7142857,
    upper_lid_right_open=0.7142857,
    lower_lid_left_open=0.75,
    lower_lid_right_open=0.75,
    brow_raise_left=0.5,
    brow_raise_right=0.5,
)


def _clamp_ratio(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _compose_neutral_pose(
    neutral_pose: BodyPose,
    *,
    head_yaw: float | None = None,
    head_pitch: float | None = None,
    head_roll: float | None = None,
    eye_yaw: float | None = None,
    eye_pitch: float | None = None,
    upper_lids_delta: float = 0.0,
    lower_lids_delta: float = 0.0,
    upper_lid_left_delta: float = 0.0,
    upper_lid_right_delta: float = 0.0,
    lower_lid_left_delta: float = 0.0,
    lower_lid_right_delta: float = 0.0,
    brow_delta: float = 0.0,
    brow_raise_left_delta: float = 0.0,
    brow_raise_right_delta: float = 0.0,
) -> BodyPose:
    return BodyPose(
        head_yaw=neutral_pose.head_yaw if head_yaw is None else head_yaw,
        head_pitch=neutral_pose.head_pitch if head_pitch is None else head_pitch,
        head_roll=neutral_pose.head_roll if head_roll is None else head_roll,
        eye_yaw=neutral_pose.eye_yaw if eye_yaw is None else eye_yaw,
        eye_pitch=neutral_pose.eye_pitch if eye_pitch is None else eye_pitch,
        upper_lid_left_open=_clamp_ratio(neutral_pose.upper_lid_left_open + upper_lids_delta + upper_lid_left_delta),
        upper_lid_right_open=_clamp_ratio(neutral_pose.upper_lid_right_open + upper_lids_delta + upper_lid_right_delta),
        lower_lid_left_open=_clamp_ratio(neutral_pose.lower_lid_left_open + lower_lids_delta + lower_lid_left_delta),
        lower_lid_right_open=_clamp_ratio(neutral_pose.lower_lid_right_open + lower_lids_delta + lower_lid_right_delta),
        brow_raise_left=_clamp_ratio(neutral_pose.brow_raise_left + brow_delta + brow_raise_left_delta),
        brow_raise_right=_clamp_ratio(neutral_pose.brow_raise_right + brow_delta + brow_raise_right_delta),
    )


def _expression_target(name: str, *, neutral_pose: BodyPose) -> BodyPose:
    builders = {
        "neutral": lambda base: base.model_copy(deep=True),
        "friendly": lambda base: _compose_neutral_pose(
            base,
            head_pitch=0.04,
            head_yaw=0.05,
            eye_pitch=0.02,
            upper_lids_delta=-0.04,
            lower_lids_delta=-0.02,
            brow_delta=0.1,
        ),
        "attentive_ready": lambda base: _compose_neutral_pose(
            base,
            head_pitch=0.0,
            head_yaw=0.02,
            upper_lids_delta=-0.03,
            lower_lids_delta=-0.02,
            brow_delta=0.08,
        ),
        "listen_attentively": lambda base: _compose_neutral_pose(
            base,
            head_pitch=0.01,
            head_yaw=0.02,
            eye_pitch=0.04,
            upper_lids_delta=-0.05,
            lower_lids_delta=-0.03,
            brow_delta=0.1,
        ),
        "listen_soft": lambda base: _compose_neutral_pose(
            base,
            head_pitch=0.0,
            head_yaw=0.01,
            upper_lids_delta=-0.06,
            lower_lids_delta=-0.04,
            brow_delta=0.08,
        ),
        "thinking": lambda base: _compose_neutral_pose(
            base,
            head_pitch=0.06,
            head_yaw=0.05,
            head_roll=0.14,
            eye_yaw=0.04,
            eye_pitch=0.14,
            upper_lids_delta=-0.08,
            lower_lids_delta=-0.04,
            brow_raise_left_delta=0.08,
            brow_raise_right_delta=0.16,
        ),
        "thinking_deep": lambda base: _compose_neutral_pose(
            base,
            head_pitch=0.08,
            head_yaw=0.08,
            head_roll=0.16,
            eye_yaw=0.06,
            eye_pitch=0.18,
            upper_lids_delta=-0.12,
            lower_lids_delta=-0.06,
            brow_raise_left_delta=0.12,
            brow_raise_right_delta=0.22,
        ),
        "concerned": lambda base: _compose_neutral_pose(
            base,
            head_pitch=0.0,
            head_yaw=0.02,
            head_roll=-0.08,
            eye_pitch=0.02,
            upper_lids_delta=-0.12,
            lower_lids_delta=-0.04,
            brow_raise_left_delta=0.02,
            brow_raise_right_delta=0.14,
        ),
        "confused": lambda base: _compose_neutral_pose(
            base,
            head_pitch=0.02,
            head_yaw=0.08,
            head_roll=0.16,
            eye_yaw=0.04,
            eye_pitch=0.08,
            upper_lids_delta=-0.08,
            lower_lids_delta=-0.02,
            brow_raise_left_delta=0.16,
            brow_raise_right_delta=-0.04,
        ),
        "brows_soft_raise": lambda base: _compose_neutral_pose(
            base,
            upper_lids_delta=-0.02,
            brow_delta=0.2,
        ),
        "eyelids_soft_focus": lambda base: _compose_neutral_pose(
            base,
            upper_lids_delta=-0.12,
            lower_lids_delta=-0.05,
            brow_delta=0.04,
        ),
        "surprised": lambda base: _compose_neutral_pose(
            base,
            head_pitch=0.06,
            eye_pitch=0.08,
            upper_lids_delta=0.12,
            lower_lids_delta=0.04,
            brow_delta=0.28,
        ),
        "sleepy": lambda base: _compose_neutral_pose(
            base,
            head_pitch=-0.08,
            upper_lids_delta=-0.24,
            lower_lids_delta=-0.1,
            brow_delta=-0.08,
        ),
        "safe_idle": lambda base: _compose_neutral_pose(
            base,
            head_pitch=0.0,
            upper_lids_delta=-0.08,
            lower_lids_delta=-0.06,
            brow_delta=0.02,
        ),
        "curious_bright": lambda base: _compose_neutral_pose(
            base,
            head_pitch=0.08,
            head_yaw=0.14,
            head_roll=0.05,
            eye_yaw=0.06,
            eye_pitch=0.18,
            upper_lids_delta=0.03,
            brow_raise_left_delta=0.16,
            brow_raise_right_delta=0.2,
        ),
        "focused_soft": lambda base: _compose_neutral_pose(
            base,
            head_pitch=0.01,
            head_yaw=0.02,
            eye_pitch=0.08,
            upper_lids_delta=-0.1,
            lower_lids_delta=-0.03,
            brow_delta=0.06,
        ),
        "playful": lambda base: _compose_neutral_pose(
            base,
            head_pitch=0.04,
            head_yaw=0.14,
            head_roll=0.16,
            eye_yaw=0.08,
            eye_pitch=0.08,
            upper_lid_left_delta=0.02,
            upper_lid_right_delta=-0.08,
            lower_lid_left_delta=-0.02,
            lower_lid_right_delta=-0.06,
            brow_raise_left_delta=0.2,
            brow_raise_right_delta=0.08,
        ),
        "bashful": lambda base: _compose_neutral_pose(
            base,
            head_pitch=-0.04,
            head_yaw=-0.12,
            head_roll=-0.08,
            eye_yaw=-0.06,
            eye_pitch=-0.08,
            upper_lids_delta=-0.12,
            lower_lids_delta=-0.06,
            brow_raise_left_delta=0.02,
            brow_raise_right_delta=0.08,
        ),
        "eyes_widen": lambda base: _compose_neutral_pose(
            base,
            head_pitch=0.04,
            eye_pitch=0.08,
            upper_lids_delta=0.12,
            lower_lids_delta=0.04,
            brow_delta=0.24,
        ),
        "half_lid_focus": lambda base: _compose_neutral_pose(
            base,
            eye_pitch=0.06,
            upper_lids_delta=-0.14,
            lower_lids_delta=-0.04,
            brow_delta=0.04,
        ),
        "brow_raise_soft": lambda base: _compose_neutral_pose(
            base,
            upper_lids_delta=-0.02,
            brow_delta=0.18,
        ),
        "brow_knit_soft": lambda base: _compose_neutral_pose(
            base,
            upper_lids_delta=-0.08,
            lower_lids_delta=-0.02,
            brow_delta=-0.1,
        ),
    }
    builder = builders.get(name, builders["neutral"])
    return builder(neutral_pose)

_GAZE_OVERRIDES = {
    "look_forward": {"head_yaw": 0.0, "eye_yaw": 0.0, "eye_pitch": 0.0, "head_pitch": 0.0},
    "look_down_briefly": {"head_pitch": 0.0, "eye_pitch": -0.4, "eye_yaw": 0.0},
    "look_left": {"head_yaw": -0.34, "eye_yaw": -0.2, "eye_pitch": 0.0},
    "look_right": {"head_yaw": 0.34, "eye_yaw": 0.2, "eye_pitch": 0.0},
    "look_up": {"head_pitch": 0.08, "eye_pitch": 0.42, "eye_yaw": 0.0},
    "look_far_left": {"head_yaw": -0.54, "eye_yaw": -0.24, "eye_pitch": 0.0},
    "look_far_right": {"head_yaw": 0.54, "eye_yaw": 0.24, "eye_pitch": 0.0},
    "look_far_up": {"head_pitch": 0.14, "eye_pitch": 0.56, "eye_yaw": 0.0},
    "look_far_down": {"head_pitch": 0.0, "eye_pitch": -0.58, "eye_yaw": 0.0},
}


def apply_pose_overrides(base_pose: BodyPose, **overrides: float) -> BodyPose:
    payload = base_pose.model_dump()
    payload.update(overrides)
    return BodyPose.model_validate(payload)


def blend_pose(target_pose: BodyPose, intensity: float, *, base_pose: BodyPose | None = None) -> BodyPose:
    intensity = max(0.0, min(1.0, intensity))
    base = base_pose or BodyPose()
    payload: dict[str, float] = {}
    for field_name in SIGNED_FIELDS + RATIO_FIELDS:
        base_value = getattr(base, field_name)
        target_value = getattr(target_pose, field_name)
        if base_value is None:
            base_value = 0.0
        if target_value is None:
            target_value = base_value
        payload[field_name] = float(base_value + (target_value - base_value) * intensity)
    return BodyPose.model_validate(payload)


def expression_pose(
    name: str,
    intensity: float = 1.0,
    *,
    base_pose: BodyPose | None = None,
    neutral_pose: BodyPose | None = None,
) -> BodyPose:
    normalized = normalize_expression_name(name).canonical_name
    if normalized == "freeze_expression":
        return base_pose.model_copy(deep=True) if base_pose is not None else (neutral_pose or _TEMPLATE_NEUTRAL_POSE).model_copy(deep=True)
    if normalized == "recover_neutral":
        normalized = "neutral"
    neutral = neutral_pose.model_copy(deep=True) if neutral_pose is not None else _TEMPLATE_NEUTRAL_POSE.model_copy(deep=True)
    target = _expression_target(normalized, neutral_pose=neutral)
    return blend_pose(target, intensity, base_pose=base_pose or neutral)

def gaze_pose(
    name: str,
    intensity: float = 1.0,
    *,
    base_pose: BodyPose | None = None,
    neutral_pose: BodyPose | None = None,
) -> BodyPose:
    normalized = normalize_gaze_name(name).canonical_name
    if normalized == "look_at_user":
        normalized = "look_forward"
    overrides = _GAZE_OVERRIDES.get(normalized, _GAZE_OVERRIDES["look_forward"])
    scaled = {field_name: float(value) * max(0.0, min(1.0, intensity)) for field_name, value in overrides.items()}
    neutral = neutral_pose or _TEMPLATE_NEUTRAL_POSE
    return apply_pose_overrides(base_pose or neutral, **scaled)


__all__ = [
    "RATIO_FIELDS",
    "SIGNED_FIELDS",
    "SUPPORTED_EXPRESSIONS",
    "SUPPORTED_GAZE_TARGETS",
    "SUPPORTED_GESTURES",
    "apply_pose_overrides",
    "blend_pose",
    "expression_pose",
    "gaze_pose",
]
