from __future__ import annotations

from dataclasses import dataclass

from embodied_stack.shared.contracts.body import (
    AnimationTimeline,
    BodyKeyframe,
    BodyPose,
    DerivedOperatingBand,
)

PRIMITIVE_MOTION_ENVELOPE = "primitive"
PRIMITIVE_SLOW_KINETICS = "primitive_slow"
PRIMITIVE_FAST_KINETICS = "primitive_fast"
PRIMITIVE_SLOW_TIMING = (180, 140, 220)
PRIMITIVE_FAST_TIMING = (95, 55, 120)
_SUPPORT_FAMILY_RATIO = 0.35
_HEAD_TURN_RATIO = 0.80
_HEAD_TILT_RATIO = 0.60
_HEAD_PITCH_RATIO = 0.60
_EYE_SHIFT_RATIO = 0.55
_CLOSE_EYES_RATIO = 0.70
_BLINK_RATIO = 0.90
_WINK_RATIO = 0.85
_BROW_BOTH_RATIO = 0.70
_BROW_SINGLE_RATIO = 0.75
_TINY_NOD_DEPTH = 0.02
_HELD_CLOSE_EYES_RATIO = 1.0
_HELD_BROW_RATIO = 1.0


def _apply_pose_overrides(base_pose: BodyPose, **overrides: float) -> BodyPose:
    payload = base_pose.model_dump()
    payload.update(overrides)
    return BodyPose.model_validate(payload)


@dataclass(frozen=True)
class PrimitiveSpec:
    canonical_name: str
    primary_actuator_group: str | None
    support_actuator_groups: tuple[str, ...] = ()
    tempo_variant: str | None = None
    returns_to_neutral: bool = True
    max_active_families: int = 1


@dataclass(frozen=True)
class RecipeStep:
    primitive_name: str
    intensity_scale: float = 1.0


@dataclass(frozen=True)
class RecipeSpec:
    canonical_name: str
    steps: tuple[RecipeStep, ...]
    primary_actuator_group: str | None
    support_actuator_groups: tuple[str, ...] = ()
    max_active_families: int = 1


@dataclass(frozen=True)
class ResolvedPrimitiveTimeline:
    canonical_name: str
    grounding: str
    timeline: AnimationTimeline
    recipe_name: str | None
    primitive_steps: tuple[str, ...]
    returns_to_neutral: bool
    primary_actuator_group: str | None
    support_actuator_groups: tuple[str, ...]
    max_active_families: int
    tempo_variant: str | None


@dataclass(frozen=True)
class PrimitiveSequenceStepSpec:
    primitive_name: str
    intensity: float = 1.0
    note: str | None = None


@dataclass(frozen=True)
class ResolvedPrimitiveSequence:
    sequence_name: str
    timeline: AnimationTimeline
    primitive_steps: tuple[str, ...]
    sequence_step_count: int
    returns_to_neutral: bool
    max_active_families: int
    primary_actuator_groups: tuple[str, ...]
    support_actuator_groups: tuple[str, ...]


def _tempo_variant(name: str) -> str | None:
    if name.endswith("_slow"):
        return "slow"
    if name.endswith("_fast"):
        return "fast"
    return None


def _timing_for(name: str) -> tuple[int, int, int]:
    return PRIMITIVE_SLOW_TIMING if _tempo_variant(name) == "slow" else PRIMITIVE_FAST_TIMING


def _kinetics_for(name: str) -> str:
    return PRIMITIVE_SLOW_KINETICS if _tempo_variant(name) == "slow" else PRIMITIVE_FAST_KINETICS


def _matching_neutral_settle(name: str) -> str:
    return "neutral_settle_slow" if _tempo_variant(name) == "slow" else "neutral_settle_fast"


def _signed_limit(negative: float, positive: float, *, direction: str, ratio: float) -> float:
    limit = negative if direction in {"left", "down"} else positive
    sign = -1.0 if direction in {"left", "down"} else 1.0
    return sign * float(limit) * ratio


def _ratio_from_neutral(neutral: float, negative: float, positive: float, *, direction: str, ratio: float) -> float:
    if direction in {"close", "lower"}:
        return max(0.0, neutral - (negative * ratio))
    return min(1.0, neutral + (positive * ratio))


def _with_lid_closure(
    neutral_pose: BodyPose,
    operating_band: DerivedOperatingBand,
    *,
    ratio: float,
    left: bool = True,
    right: bool = True,
) -> BodyPose:
    payload = neutral_pose.model_dump()
    upper_negative = float(operating_band.upper_lid.transient_negative_limit or operating_band.upper_lid.negative_limit)
    lower_negative = float(operating_band.lower_lid.transient_negative_limit or operating_band.lower_lid.negative_limit)
    if left:
        payload["upper_lid_left_open"] = _ratio_from_neutral(
            float(neutral_pose.upper_lid_left_open),
            upper_negative,
            float(operating_band.upper_lid.transient_positive_limit or operating_band.upper_lid.positive_limit),
            direction="close",
            ratio=ratio,
        )
        payload["lower_lid_left_open"] = _ratio_from_neutral(
            float(neutral_pose.lower_lid_left_open),
            lower_negative,
            float(operating_band.lower_lid.transient_positive_limit or operating_band.lower_lid.positive_limit),
            direction="close",
            ratio=ratio,
        )
    if right:
        payload["upper_lid_right_open"] = _ratio_from_neutral(
            float(neutral_pose.upper_lid_right_open),
            upper_negative,
            float(operating_band.upper_lid.transient_positive_limit or operating_band.upper_lid.positive_limit),
            direction="close",
            ratio=ratio,
        )
        payload["lower_lid_right_open"] = _ratio_from_neutral(
            float(neutral_pose.lower_lid_right_open),
            lower_negative,
            float(operating_band.lower_lid.transient_positive_limit or operating_band.lower_lid.positive_limit),
            direction="close",
            ratio=ratio,
        )
    return BodyPose.model_validate(payload)


def _with_brow_shift(
    neutral_pose: BodyPose,
    operating_band: DerivedOperatingBand,
    *,
    direction: str,
    ratio: float,
    left: bool,
    right: bool,
) -> BodyPose:
    payload = neutral_pose.model_dump()
    negative = float(operating_band.brow.negative_limit)
    positive = float(operating_band.brow.positive_limit)
    if left:
        payload["brow_raise_left"] = _ratio_from_neutral(
            float(neutral_pose.brow_raise_left),
            negative,
            positive,
            direction=direction,
            ratio=ratio,
        )
    if right:
        payload["brow_raise_right"] = _ratio_from_neutral(
            float(neutral_pose.brow_raise_right),
            negative,
            positive,
            direction=direction,
            ratio=ratio,
        )
    return BodyPose.model_validate(payload)


def _primitive_specs() -> dict[str, PrimitiveSpec]:
    specs = {
        "neutral_settle_slow": PrimitiveSpec("neutral_settle_slow", None, tempo_variant="slow"),
        "neutral_settle_fast": PrimitiveSpec("neutral_settle_fast", None, tempo_variant="fast"),
        "head_turn_left_slow": PrimitiveSpec("head_turn_left_slow", "head_yaw", tempo_variant="slow"),
        "head_turn_left_fast": PrimitiveSpec("head_turn_left_fast", "head_yaw", tempo_variant="fast"),
        "head_turn_right_slow": PrimitiveSpec("head_turn_right_slow", "head_yaw", tempo_variant="slow"),
        "head_turn_right_fast": PrimitiveSpec("head_turn_right_fast", "head_yaw", tempo_variant="fast"),
        "head_pitch_up_slow": PrimitiveSpec("head_pitch_up_slow", "head_pitch_pair", tempo_variant="slow"),
        "head_pitch_up_fast": PrimitiveSpec("head_pitch_up_fast", "head_pitch_pair", tempo_variant="fast"),
        "head_pitch_down_slow": PrimitiveSpec("head_pitch_down_slow", "head_pitch_pair", tempo_variant="slow"),
        "head_pitch_down_fast": PrimitiveSpec("head_pitch_down_fast", "head_pitch_pair", tempo_variant="fast"),
        "head_tilt_left_slow": PrimitiveSpec("head_tilt_left_slow", "head_pitch_pair", tempo_variant="slow"),
        "head_tilt_left_fast": PrimitiveSpec("head_tilt_left_fast", "head_pitch_pair", tempo_variant="fast"),
        "head_tilt_right_slow": PrimitiveSpec("head_tilt_right_slow", "head_pitch_pair", tempo_variant="slow"),
        "head_tilt_right_fast": PrimitiveSpec("head_tilt_right_fast", "head_pitch_pair", tempo_variant="fast"),
        "eyes_left_slow": PrimitiveSpec("eyes_left_slow", "eye_yaw", tempo_variant="slow"),
        "eyes_left_fast": PrimitiveSpec("eyes_left_fast", "eye_yaw", tempo_variant="fast"),
        "eyes_right_slow": PrimitiveSpec("eyes_right_slow", "eye_yaw", tempo_variant="slow"),
        "eyes_right_fast": PrimitiveSpec("eyes_right_fast", "eye_yaw", tempo_variant="fast"),
        "eyes_up_slow": PrimitiveSpec("eyes_up_slow", "eye_pitch", tempo_variant="slow"),
        "eyes_up_fast": PrimitiveSpec("eyes_up_fast", "eye_pitch", tempo_variant="fast"),
        "eyes_down_slow": PrimitiveSpec("eyes_down_slow", "eye_pitch", tempo_variant="slow"),
        "eyes_down_fast": PrimitiveSpec("eyes_down_fast", "eye_pitch", tempo_variant="fast"),
        "close_both_eyes_slow": PrimitiveSpec("close_both_eyes_slow", "upper_lids", ("lower_lids",), "slow", max_active_families=2),
        "close_both_eyes_fast": PrimitiveSpec("close_both_eyes_fast", "upper_lids", ("lower_lids",), "fast", max_active_families=2),
        "close_both_eyes_hold_slow": PrimitiveSpec(
            "close_both_eyes_hold_slow",
            "upper_lids",
            ("lower_lids",),
            "slow",
            returns_to_neutral=False,
            max_active_families=2,
        ),
        "blink_both_slow": PrimitiveSpec("blink_both_slow", "upper_lids", ("lower_lids",), "slow", max_active_families=2),
        "blink_both_fast": PrimitiveSpec("blink_both_fast", "upper_lids", ("lower_lids",), "fast", max_active_families=2),
        "double_blink_slow": PrimitiveSpec("double_blink_slow", "upper_lids", ("lower_lids",), "slow", max_active_families=2),
        "double_blink_fast": PrimitiveSpec("double_blink_fast", "upper_lids", ("lower_lids",), "fast", max_active_families=2),
        "wink_left_slow": PrimitiveSpec("wink_left_slow", "upper_lids", ("lower_lids",), "slow", max_active_families=2),
        "wink_left_fast": PrimitiveSpec("wink_left_fast", "upper_lids", ("lower_lids",), "fast", max_active_families=2),
        "wink_right_slow": PrimitiveSpec("wink_right_slow", "upper_lids", ("lower_lids",), "slow", max_active_families=2),
        "wink_right_fast": PrimitiveSpec("wink_right_fast", "upper_lids", ("lower_lids",), "fast", max_active_families=2),
        "brows_raise_both_slow": PrimitiveSpec("brows_raise_both_slow", "brows", tempo_variant="slow"),
        "brows_raise_both_fast": PrimitiveSpec("brows_raise_both_fast", "brows", tempo_variant="fast"),
        "brows_lower_both_slow": PrimitiveSpec("brows_lower_both_slow", "brows", tempo_variant="slow"),
        "brows_lower_both_fast": PrimitiveSpec("brows_lower_both_fast", "brows", tempo_variant="fast"),
        "brows_lower_hold_slow": PrimitiveSpec(
            "brows_lower_hold_slow",
            "brows",
            tempo_variant="slow",
            returns_to_neutral=False,
        ),
        "brows_neutral_slow": PrimitiveSpec(
            "brows_neutral_slow",
            "brows",
            tempo_variant="slow",
            returns_to_neutral=False,
        ),
        "brow_left_raise_slow": PrimitiveSpec("brow_left_raise_slow", "brows", tempo_variant="slow"),
        "brow_left_raise_fast": PrimitiveSpec("brow_left_raise_fast", "brows", tempo_variant="fast"),
        "brow_left_lower_slow": PrimitiveSpec("brow_left_lower_slow", "brows", tempo_variant="slow"),
        "brow_left_lower_fast": PrimitiveSpec("brow_left_lower_fast", "brows", tempo_variant="fast"),
        "brow_right_raise_slow": PrimitiveSpec("brow_right_raise_slow", "brows", tempo_variant="slow"),
        "brow_right_raise_fast": PrimitiveSpec("brow_right_raise_fast", "brows", tempo_variant="fast"),
        "brow_right_lower_slow": PrimitiveSpec("brow_right_lower_slow", "brows", tempo_variant="slow"),
        "brow_right_lower_fast": PrimitiveSpec("brow_right_lower_fast", "brows", tempo_variant="fast"),
        "lids_neutral_slow": PrimitiveSpec(
            "lids_neutral_slow",
            "upper_lids",
            ("lower_lids",),
            "slow",
            returns_to_neutral=False,
            max_active_families=2,
        ),
        "tiny_nod_slow": PrimitiveSpec("tiny_nod_slow", "head_pitch_pair", tempo_variant="slow"),
        "tiny_nod_fast": PrimitiveSpec("tiny_nod_fast", "head_pitch_pair", tempo_variant="fast"),
        "attend_left_slow": PrimitiveSpec("attend_left_slow", "head_yaw", ("eye_yaw",), "slow", max_active_families=2),
        "attend_left_fast": PrimitiveSpec("attend_left_fast", "head_yaw", ("eye_yaw",), "fast", max_active_families=2),
        "attend_right_slow": PrimitiveSpec("attend_right_slow", "head_yaw", ("eye_yaw",), "slow", max_active_families=2),
        "attend_right_fast": PrimitiveSpec("attend_right_fast", "head_yaw", ("eye_yaw",), "fast", max_active_families=2),
        "curious_left_slow": PrimitiveSpec("curious_left_slow", "head_yaw", ("brows",), "slow", max_active_families=2),
        "curious_left_fast": PrimitiveSpec("curious_left_fast", "head_yaw", ("brows",), "fast", max_active_families=2),
        "curious_right_slow": PrimitiveSpec("curious_right_slow", "head_yaw", ("brows",), "slow", max_active_families=2),
        "curious_right_fast": PrimitiveSpec("curious_right_fast", "head_yaw", ("brows",), "fast", max_active_families=2),
        "warm_blink_slow": PrimitiveSpec("warm_blink_slow", "upper_lids", ("brows",), "slow", max_active_families=2),
        "warm_blink_fast": PrimitiveSpec("warm_blink_fast", "upper_lids", ("brows",), "fast", max_active_families=2),
        "wink_left_emphasis_fast": PrimitiveSpec("wink_left_emphasis_fast", "upper_lids", ("brows",), "fast", max_active_families=2),
        "wink_right_emphasis_fast": PrimitiveSpec("wink_right_emphasis_fast", "upper_lids", ("brows",), "fast", max_active_families=2),
    }
    return specs


_PRIMITIVE_SPECS = _primitive_specs()


def _recipe_specs() -> dict[str, RecipeSpec]:
    return {
        "neutral": RecipeSpec("neutral", (RecipeStep("neutral_settle_slow"),), None),
        "safe_idle": RecipeSpec("safe_idle", (RecipeStep("neutral_settle_slow"),), None),
        "look_forward": RecipeSpec("look_forward", (RecipeStep("neutral_settle_slow"),), None),
        "look_at_user": RecipeSpec("look_at_user", (RecipeStep("neutral_settle_slow"),), None),
        "look_left": RecipeSpec("look_left", (RecipeStep("attend_left_slow"),), "head_yaw", ("eye_yaw",), 2),
        "look_right": RecipeSpec("look_right", (RecipeStep("attend_right_slow"),), "head_yaw", ("eye_yaw",), 2),
        "look_up": RecipeSpec("look_up", (RecipeStep("eyes_up_slow"),), "eye_pitch"),
        "look_down_briefly": RecipeSpec("look_down_briefly", (RecipeStep("eyes_down_fast"),), "eye_pitch"),
        "look_far_left": RecipeSpec("look_far_left", (RecipeStep("head_turn_left_fast"),), "head_yaw"),
        "look_far_right": RecipeSpec("look_far_right", (RecipeStep("head_turn_right_fast"),), "head_yaw"),
        "look_far_up": RecipeSpec("look_far_up", (RecipeStep("eyes_up_fast"),), "eye_pitch"),
        "look_far_down": RecipeSpec("look_far_down", (RecipeStep("eyes_down_fast"),), "eye_pitch"),
        "friendly": RecipeSpec("friendly", (RecipeStep("brows_raise_both_slow"),), "brows"),
        "focused_soft": RecipeSpec(
            "focused_soft",
            (RecipeStep("eyes_down_slow"), RecipeStep("neutral_settle_slow")),
            "eye_pitch",
        ),
        "listen_attentively": RecipeSpec(
            "listen_attentively",
            (RecipeStep("attend_right_slow"), RecipeStep("neutral_settle_slow")),
            "head_yaw",
            ("eye_yaw",),
            2,
        ),
        "thinking": RecipeSpec(
            "thinking",
            (RecipeStep("eyes_down_slow"), RecipeStep("brow_left_raise_slow")),
            "eye_pitch",
            ("brows",),
            1,
        ),
        "acknowledge_light": RecipeSpec("acknowledge_light", (RecipeStep("tiny_nod_fast"),), "head_pitch_pair"),
        "youthful_greeting": RecipeSpec(
            "youthful_greeting",
            (RecipeStep("attend_left_fast"), RecipeStep("attend_right_fast"), RecipeStep("double_blink_fast")),
            "head_yaw",
            ("eye_yaw", "upper_lids", "lower_lids"),
            2,
        ),
        "soft_reengage": RecipeSpec(
            "soft_reengage",
            (RecipeStep("brows_raise_both_slow"), RecipeStep("neutral_settle_slow")),
            "brows",
        ),
        "concerned": RecipeSpec(
            "concerned",
            (RecipeStep("brows_lower_both_slow"), RecipeStep("eyes_down_slow", 0.8)),
            "brows",
            ("eye_pitch",),
        ),
        "confused": RecipeSpec(
            "confused",
            (RecipeStep("brow_left_raise_slow"), RecipeStep("head_turn_right_slow")),
            "brows",
            ("head_yaw",),
        ),
        "curious_bright": RecipeSpec(
            "curious_bright",
            (RecipeStep("curious_right_slow"), RecipeStep("eyes_up_slow")),
            "head_yaw",
            ("brows", "eye_pitch"),
            2,
        ),
        "playful": RecipeSpec(
            "playful",
            (RecipeStep("wink_left_emphasis_fast"), RecipeStep("attend_right_fast")),
            "upper_lids",
            ("brows", "head_yaw", "eye_yaw"),
            2,
        ),
        "bashful": RecipeSpec(
            "bashful",
            (RecipeStep("eyes_down_slow"), RecipeStep("head_turn_left_slow")),
            "eye_pitch",
            ("head_yaw",),
        ),
        "eyes_widen": RecipeSpec(
            "eyes_widen",
            (RecipeStep("brows_raise_both_fast"),),
            "brows",
        ),
        "half_lid_focus": RecipeSpec(
            "half_lid_focus",
            (RecipeStep("close_both_eyes_slow", 0.45),),
            "upper_lids",
            ("lower_lids",),
            2,
        ),
        "brow_raise_soft": RecipeSpec(
            "brow_raise_soft",
            (RecipeStep("brows_raise_both_slow", 0.8),),
            "brows",
        ),
        "brow_knit_soft": RecipeSpec(
            "brow_knit_soft",
            (RecipeStep("brows_lower_both_slow", 0.8),),
            "brows",
        ),
        "blink_soft": RecipeSpec("blink_soft", (RecipeStep("blink_both_slow"),), "upper_lids", ("lower_lids",), 2),
        "double_blink": RecipeSpec("double_blink", (RecipeStep("double_blink_fast"),), "upper_lids", ("lower_lids",), 2),
        "wink_left": RecipeSpec("wink_left", (RecipeStep("wink_left_slow"),), "upper_lids", ("lower_lids",), 2),
        "wink_right": RecipeSpec("wink_right", (RecipeStep("wink_right_slow"),), "upper_lids", ("lower_lids",), 2),
        "playful_peek_left": RecipeSpec(
            "playful_peek_left",
            (RecipeStep("attend_left_fast"), RecipeStep("wink_left_fast")),
            "head_yaw",
            ("eye_yaw", "upper_lids", "lower_lids"),
            2,
        ),
        "playful_peek_right": RecipeSpec(
            "playful_peek_right",
            (RecipeStep("attend_right_fast"), RecipeStep("wink_right_fast")),
            "head_yaw",
            ("eye_yaw", "upper_lids", "lower_lids"),
            2,
        ),
        "tilt_curious": RecipeSpec("tilt_curious", (RecipeStep("head_tilt_right_slow"),), "head_pitch_pair"),
        "recover_neutral": RecipeSpec("recover_neutral", (RecipeStep("neutral_settle_slow"),), None),
        "playful_react": RecipeSpec(
            "playful_react",
            (RecipeStep("attend_left_fast"), RecipeStep("brows_raise_both_fast")),
            "head_yaw",
            ("eye_yaw", "brows"),
            2,
        ),
    }


_RECIPE_SPECS = _recipe_specs()


def primitive_action_names() -> tuple[str, ...]:
    return tuple(_PRIMITIVE_SPECS)


def recipe_action_names() -> tuple[str, ...]:
    return tuple(_RECIPE_SPECS)


def is_primitive_action(name: str | None) -> bool:
    return str(name or "") in _PRIMITIVE_SPECS


def is_recipe_action(name: str | None) -> bool:
    return str(name or "") in _RECIPE_SPECS


def action_grounding(name: str | None) -> str | None:
    if is_primitive_action(name):
        return "primitive"
    if is_recipe_action(name):
        return "recipe"
    return None


def action_descriptor_metadata(name: str | None) -> dict[str, object]:
    if is_primitive_action(name):
        spec = _PRIMITIVE_SPECS[str(name)]
        return {
            "grounding": "primitive",
            "primary_actuator_group": spec.primary_actuator_group,
            "support_actuator_groups": list(spec.support_actuator_groups),
            "returns_to_neutral": spec.returns_to_neutral,
            "max_active_families": spec.max_active_families,
            "tempo_variant": spec.tempo_variant,
        }
    if is_recipe_action(name):
        spec = _RECIPE_SPECS[str(name)]
        return {
            "grounding": "recipe",
            "primary_actuator_group": spec.primary_actuator_group,
            "support_actuator_groups": list(spec.support_actuator_groups),
            "returns_to_neutral": True,
            "max_active_families": spec.max_active_families,
            "tempo_variant": None,
        }
    return {
        "grounding": None,
        "primary_actuator_group": None,
        "support_actuator_groups": [],
        "returns_to_neutral": False,
        "max_active_families": None,
        "tempo_variant": None,
    }


def primitive_only_coverage() -> dict[str, set[str]]:
    coverage: dict[str, set[str]] = {}
    for name, spec in _PRIMITIVE_SPECS.items():
        groups = {group for group in (spec.primary_actuator_group, *spec.support_actuator_groups) if group}
        coverage[name] = groups
    return coverage


def primitive_total_duration_ms(name: str) -> int:
    if name in {
        "close_both_eyes_hold_slow",
        "brows_lower_hold_slow",
        "brows_neutral_slow",
        "lids_neutral_slow",
    }:
        move_ms, hold_ms, _ = PRIMITIVE_SLOW_TIMING
        return move_ms + hold_ms
    if name.endswith("_slow"):
        return sum(PRIMITIVE_SLOW_TIMING)
    if name == "double_blink_slow":
        return sum(PRIMITIVE_SLOW_TIMING) * 2
    if name == "double_blink_fast":
        return sum(PRIMITIVE_FAST_TIMING) * 2
    if name.endswith("_fast"):
        return sum(PRIMITIVE_FAST_TIMING)
    return 0


def primitive_move_hold_recover_ms(name: str) -> tuple[int, int, int]:
    if not is_primitive_action(name):
        raise ValueError(f"unknown_primitive_action:{name}")
    return _timing_for(name)


def primitive_kinetics_profile_name(name: str) -> str:
    if not is_primitive_action(name):
        raise ValueError(f"unknown_primitive_action:{name}")
    return _kinetics_for(name)


def primitive_target_pose(
    name: str,
    *,
    intensity: float,
    neutral_pose: BodyPose,
    operating_band: DerivedOperatingBand,
) -> BodyPose:
    if not is_primitive_action(name):
        raise ValueError(f"unknown_primitive_action:{name}")
    return _primitive_target_pose(
        name,
        intensity=max(0.0, min(1.0, float(intensity))),
        neutral_pose=neutral_pose,
        operating_band=operating_band,
    )


def build_primitive_sequence_timeline(
    sequence_name: str,
    *,
    steps: tuple[PrimitiveSequenceStepSpec, ...],
    neutral_pose: BodyPose,
    operating_band: DerivedOperatingBand,
) -> ResolvedPrimitiveSequence:
    if not steps:
        raise ValueError("primitive_sequence_requires_steps")
    requested_steps: list[PrimitiveSequenceStepSpec] = []
    for step in steps:
        if not is_primitive_action(step.primitive_name):
            raise ValueError(f"primitive_sequence_step_not_primitive:{step.primitive_name}")
        requested_steps.append(
            PrimitiveSequenceStepSpec(
                primitive_name=step.primitive_name,
                intensity=max(0.0, min(1.0, float(step.intensity))),
                note=step.note,
            )
        )

    injected_steps: list[PrimitiveSequenceStepSpec] = []
    first_requested = requested_steps[0]
    if not first_requested.primitive_name.startswith("neutral_settle"):
        injected_steps.append(
            PrimitiveSequenceStepSpec(
                primitive_name=_matching_neutral_settle(first_requested.primitive_name),
                intensity=1.0,
                note="sequence_pre_neutral",
            )
        )
    injected_steps.extend(requested_steps)
    injected_steps.append(
        PrimitiveSequenceStepSpec(
            primitive_name=_matching_neutral_settle(requested_steps[-1].primitive_name),
            intensity=1.0,
            note="sequence_final_neutral_confirm",
        )
    )

    keyframes: list[BodyKeyframe] = []
    primary_groups: list[str] = []
    support_groups: set[str] = set()
    max_active_families = 0
    for step_index, step in enumerate(injected_steps, start=1):
        resolved = build_registered_action_timeline(
            step.primitive_name,
            intensity=step.intensity,
            neutral_pose=neutral_pose,
            operating_band=operating_band,
        )
        if resolved is None or resolved.grounding != "primitive":
            raise ValueError(f"primitive_sequence_step_not_primitive:{step.primitive_name}")
        if not step.primitive_name.startswith("neutral_settle"):
            if resolved.primary_actuator_group is not None:
                primary_groups.append(resolved.primary_actuator_group)
            support_groups.update(group for group in resolved.support_actuator_groups if group)
            max_active_families = max(max_active_families, int(resolved.max_active_families or 1))
        for frame_index, frame in enumerate(resolved.timeline.keyframes, start=1):
            note_parts = [f"sequence:{sequence_name}", f"step:{step_index}", f"primitive:{step.primitive_name}"]
            if step.note:
                note_parts.append(f"note:{step.note}")
            keyframes.append(
                frame.model_copy(
                    update={
                        "keyframe_name": f"{sequence_name}:step{step_index}:frame{frame_index}:{frame.keyframe_name}",
                        "note": ",".join(note_parts),
                    }
                )
            )
    return ResolvedPrimitiveSequence(
        sequence_name=sequence_name,
        timeline=AnimationTimeline(animation_name=sequence_name, keyframes=keyframes, repeat_count=1, loop=False),
        primitive_steps=tuple(step.primitive_name for step in requested_steps),
        sequence_step_count=len(requested_steps),
        returns_to_neutral=True,
        max_active_families=max_active_families,
        primary_actuator_groups=tuple(dict.fromkeys(primary_groups)),
        support_actuator_groups=tuple(sorted(support_groups)),
    )


def build_registered_action_timeline(
    name: str,
    *,
    intensity: float,
    neutral_pose: BodyPose,
    operating_band: DerivedOperatingBand,
) -> ResolvedPrimitiveTimeline | None:
    normalized_intensity = max(0.0, min(1.0, float(intensity)))
    if name in _PRIMITIVE_SPECS:
        spec = _PRIMITIVE_SPECS[name]
        timeline = _primitive_timeline(
            name,
            intensity=normalized_intensity,
            neutral_pose=neutral_pose,
            operating_band=operating_band,
        )
        return ResolvedPrimitiveTimeline(
            canonical_name=name,
            grounding="primitive",
            timeline=timeline,
            recipe_name=None,
            primitive_steps=(name,),
            returns_to_neutral=spec.returns_to_neutral,
            primary_actuator_group=spec.primary_actuator_group,
            support_actuator_groups=spec.support_actuator_groups,
            max_active_families=spec.max_active_families,
            tempo_variant=spec.tempo_variant,
        )
    if name in _RECIPE_SPECS:
        spec = _RECIPE_SPECS[name]
        keyframes: list[BodyKeyframe] = []
        primitive_steps: list[str] = []
        for step_index, step in enumerate(spec.steps, start=1):
            primitive_steps.append(step.primitive_name)
            step_timeline = _primitive_timeline(
                step.primitive_name,
                intensity=max(0.0, min(1.0, normalized_intensity * step.intensity_scale)),
                neutral_pose=neutral_pose,
                operating_band=operating_band,
            )
            for frame in step_timeline.keyframes:
                renamed = frame.model_copy(
                    update={
                        "keyframe_name": f"{name}:step{step_index}:{frame.keyframe_name}",
                        "semantic_name": name,
                        "note": f"recipe:{name}",
                    }
                )
                keyframes.append(renamed)
        return ResolvedPrimitiveTimeline(
            canonical_name=name,
            grounding="recipe",
            timeline=AnimationTimeline(animation_name=name, keyframes=keyframes, repeat_count=1, loop=False),
            recipe_name=name,
            primitive_steps=tuple(primitive_steps),
            returns_to_neutral=True,
            primary_actuator_group=spec.primary_actuator_group,
            support_actuator_groups=spec.support_actuator_groups,
            max_active_families=spec.max_active_families,
            tempo_variant=None,
        )
    return None


def _primitive_timeline(
    name: str,
    *,
    intensity: float,
    neutral_pose: BodyPose,
    operating_band: DerivedOperatingBand,
) -> AnimationTimeline:
    move_ms, hold_ms, recover_ms = _timing_for(name)
    kinetics_profile = _kinetics_for(name)
    intensity = max(0.0, min(1.0, float(intensity)))
    target_pose = _primitive_target_pose(
        name,
        intensity=intensity,
        neutral_pose=neutral_pose,
        operating_band=operating_band,
    )
    transient = "blink" in name or "wink" in name
    if name in {
        "close_both_eyes_hold_slow",
        "brows_lower_hold_slow",
        "brows_neutral_slow",
        "lids_neutral_slow",
    }:
        return AnimationTimeline(
            animation_name=name,
            keyframes=[
                BodyKeyframe(
                    keyframe_name="target",
                    pose=target_pose,
                    duration_ms=move_ms,
                    hold_ms=hold_ms,
                    transient=False,
                    semantic_name=name,
                    motion_envelope=PRIMITIVE_MOTION_ENVELOPE,
                    kinetics_profile=kinetics_profile,
                )
            ],
            repeat_count=1,
            loop=False,
        )
    if name.startswith("double_blink_"):
        blink_frame = BodyKeyframe(
            keyframe_name="blink_one",
            pose=target_pose,
            duration_ms=move_ms,
            hold_ms=hold_ms,
            transient=True,
            semantic_name=name,
            motion_envelope=PRIMITIVE_MOTION_ENVELOPE,
            kinetics_profile=kinetics_profile,
        )
        recover_frame = BodyKeyframe(
            keyframe_name="recover_one",
            pose=neutral_pose.model_copy(deep=True),
            duration_ms=recover_ms,
            semantic_name=name,
            motion_envelope=PRIMITIVE_MOTION_ENVELOPE,
            kinetics_profile=kinetics_profile,
        )
        blink_two = blink_frame.model_copy(update={"keyframe_name": "blink_two"})
        recover_two = recover_frame.model_copy(update={"keyframe_name": "recover_two"})
        return AnimationTimeline(
            animation_name=name,
            keyframes=[blink_frame, recover_frame, blink_two, recover_two],
            repeat_count=1,
            loop=False,
        )
    return AnimationTimeline(
        animation_name=name,
        keyframes=[
            BodyKeyframe(
                keyframe_name="target",
                pose=target_pose,
                duration_ms=move_ms,
                hold_ms=hold_ms,
                transient=transient,
                semantic_name=name,
                motion_envelope=PRIMITIVE_MOTION_ENVELOPE,
                kinetics_profile=kinetics_profile,
            ),
            BodyKeyframe(
                keyframe_name="recover",
                pose=neutral_pose.model_copy(deep=True),
                duration_ms=recover_ms,
                semantic_name=name,
                motion_envelope=PRIMITIVE_MOTION_ENVELOPE,
                kinetics_profile=kinetics_profile,
            ),
        ],
        repeat_count=1,
        loop=False,
    )


def _primitive_target_pose(
    name: str,
    *,
    intensity: float,
    neutral_pose: BodyPose,
    operating_band: DerivedOperatingBand,
) -> BodyPose:
    if name.startswith("neutral_settle"):
        return neutral_pose.model_copy(deep=True)
    if name.startswith("head_turn_left"):
        return _apply_pose_overrides(
            neutral_pose,
            head_yaw=_signed_limit(
                float(operating_band.head_yaw.negative_limit),
                float(operating_band.head_yaw.positive_limit),
                direction="left",
                ratio=_HEAD_TURN_RATIO * intensity,
            ),
        )
    if name.startswith("head_turn_right"):
        return _apply_pose_overrides(
            neutral_pose,
            head_yaw=_signed_limit(
                float(operating_band.head_yaw.negative_limit),
                float(operating_band.head_yaw.positive_limit),
                direction="right",
                ratio=_HEAD_TURN_RATIO * intensity,
            ),
        )
    if name.startswith("head_pitch_up"):
        return _apply_pose_overrides(
            neutral_pose,
            head_pitch=_signed_limit(
                float(operating_band.head_pitch.negative_limit),
                float(operating_band.head_pitch.positive_limit),
                direction="up",
                ratio=_HEAD_PITCH_RATIO * intensity,
            ),
        )
    if name.startswith("head_pitch_down"):
        return _apply_pose_overrides(
            neutral_pose,
            head_pitch=_signed_limit(
                float(operating_band.head_pitch.negative_limit),
                float(operating_band.head_pitch.positive_limit),
                direction="down",
                ratio=_HEAD_PITCH_RATIO * intensity,
            ),
        )
    if name.startswith("head_tilt_left"):
        return _apply_pose_overrides(
            neutral_pose,
            head_roll=_signed_limit(
                float(operating_band.head_roll.negative_limit),
                float(operating_band.head_roll.positive_limit),
                direction="left",
                ratio=_HEAD_TILT_RATIO * intensity,
            ),
        )
    if name.startswith("head_tilt_right"):
        return _apply_pose_overrides(
            neutral_pose,
            head_roll=_signed_limit(
                float(operating_band.head_roll.negative_limit),
                float(operating_band.head_roll.positive_limit),
                direction="right",
                ratio=_HEAD_TILT_RATIO * intensity,
            ),
        )
    if name.startswith("eyes_left"):
        return _apply_pose_overrides(
            neutral_pose,
            eye_yaw=_signed_limit(
                float(operating_band.eye_yaw.negative_limit),
                float(operating_band.eye_yaw.positive_limit),
                direction="left",
                ratio=_EYE_SHIFT_RATIO * intensity,
            ),
        )
    if name.startswith("eyes_right"):
        return _apply_pose_overrides(
            neutral_pose,
            eye_yaw=_signed_limit(
                float(operating_band.eye_yaw.negative_limit),
                float(operating_band.eye_yaw.positive_limit),
                direction="right",
                ratio=_EYE_SHIFT_RATIO * intensity,
            ),
        )
    if name.startswith("eyes_up"):
        return _apply_pose_overrides(
            neutral_pose,
            eye_pitch=_signed_limit(
                float(operating_band.eye_pitch.negative_limit),
                float(operating_band.eye_pitch.positive_limit),
                direction="up",
                ratio=_EYE_SHIFT_RATIO * intensity,
            ),
        )
    if name.startswith("eyes_down"):
        return _apply_pose_overrides(
            neutral_pose,
            eye_pitch=_signed_limit(
                float(operating_band.eye_pitch.negative_limit),
                float(operating_band.eye_pitch.positive_limit),
                direction="down",
                ratio=_EYE_SHIFT_RATIO * intensity,
            ),
        )
    if name == "close_both_eyes_hold_slow":
        return _with_lid_closure(neutral_pose, operating_band, ratio=_HELD_CLOSE_EYES_RATIO * intensity)
    if name.startswith("close_both_eyes"):
        return _with_lid_closure(neutral_pose, operating_band, ratio=_CLOSE_EYES_RATIO * intensity)
    if name.startswith("blink_both") or name.startswith("double_blink_"):
        return _with_lid_closure(neutral_pose, operating_band, ratio=_BLINK_RATIO * intensity)
    if name.startswith("wink_left"):
        pose = _with_lid_closure(neutral_pose, operating_band, ratio=_WINK_RATIO * intensity, left=True, right=False)
        if name == "wink_left_emphasis_fast":
            pose = _support_brow(pose, neutral_pose, operating_band, side="left", ratio=_BROW_SINGLE_RATIO * _SUPPORT_FAMILY_RATIO * intensity)
        return pose
    if name.startswith("wink_right"):
        pose = _with_lid_closure(neutral_pose, operating_band, ratio=_WINK_RATIO * intensity, left=False, right=True)
        if name == "wink_right_emphasis_fast":
            pose = _support_brow(pose, neutral_pose, operating_band, side="right", ratio=_BROW_SINGLE_RATIO * _SUPPORT_FAMILY_RATIO * intensity)
        return pose
    if name.startswith("brows_raise_both"):
        return _with_brow_shift(neutral_pose, operating_band, direction="raise", ratio=_BROW_BOTH_RATIO * intensity, left=True, right=True)
    if name.startswith("brows_lower_both"):
        return _with_brow_shift(neutral_pose, operating_band, direction="lower", ratio=_BROW_BOTH_RATIO * intensity, left=True, right=True)
    if name == "brows_lower_hold_slow":
        return _with_brow_shift(
            neutral_pose,
            operating_band,
            direction="lower",
            ratio=_HELD_BROW_RATIO * intensity,
            left=True,
            right=True,
        )
    if name == "brows_neutral_slow":
        return neutral_pose.model_copy(deep=True)
    if name.startswith("brow_left_raise"):
        return _with_brow_shift(neutral_pose, operating_band, direction="raise", ratio=_BROW_SINGLE_RATIO * intensity, left=True, right=False)
    if name.startswith("brow_left_lower"):
        return _with_brow_shift(neutral_pose, operating_band, direction="lower", ratio=_BROW_SINGLE_RATIO * intensity, left=True, right=False)
    if name.startswith("brow_right_raise"):
        return _with_brow_shift(neutral_pose, operating_band, direction="raise", ratio=_BROW_SINGLE_RATIO * intensity, left=False, right=True)
    if name.startswith("brow_right_lower"):
        return _with_brow_shift(neutral_pose, operating_band, direction="lower", ratio=_BROW_SINGLE_RATIO * intensity, left=False, right=True)
    if name == "lids_neutral_slow":
        return neutral_pose.model_copy(deep=True)
    if name.startswith("tiny_nod"):
        return _apply_pose_overrides(neutral_pose, head_pitch=max(-1.0, -_TINY_NOD_DEPTH * intensity))
    if name.startswith("attend_left"):
        return _apply_pose_overrides(
            neutral_pose,
            head_yaw=_signed_limit(
                float(operating_band.head_yaw.negative_limit),
                float(operating_band.head_yaw.positive_limit),
                direction="left",
                ratio=_HEAD_TURN_RATIO * intensity,
            ),
            eye_yaw=_signed_limit(
                float(operating_band.eye_yaw.negative_limit),
                float(operating_band.eye_yaw.positive_limit),
                direction="left",
                ratio=_EYE_SHIFT_RATIO * _SUPPORT_FAMILY_RATIO * intensity,
            ),
        )
    if name.startswith("attend_right"):
        return _apply_pose_overrides(
            neutral_pose,
            head_yaw=_signed_limit(
                float(operating_band.head_yaw.negative_limit),
                float(operating_band.head_yaw.positive_limit),
                direction="right",
                ratio=_HEAD_TURN_RATIO * intensity,
            ),
            eye_yaw=_signed_limit(
                float(operating_band.eye_yaw.negative_limit),
                float(operating_band.eye_yaw.positive_limit),
                direction="right",
                ratio=_EYE_SHIFT_RATIO * _SUPPORT_FAMILY_RATIO * intensity,
            ),
        )
    if name.startswith("curious_left"):
        pose = _apply_pose_overrides(
            neutral_pose,
            head_yaw=_signed_limit(
                float(operating_band.head_yaw.negative_limit),
                float(operating_band.head_yaw.positive_limit),
                direction="left",
                ratio=_HEAD_TURN_RATIO * intensity,
            ),
        )
        return _support_brow(pose, neutral_pose, operating_band, side="left", ratio=_BROW_SINGLE_RATIO * _SUPPORT_FAMILY_RATIO * intensity)
    if name.startswith("curious_right"):
        pose = _apply_pose_overrides(
            neutral_pose,
            head_yaw=_signed_limit(
                float(operating_band.head_yaw.negative_limit),
                float(operating_band.head_yaw.positive_limit),
                direction="right",
                ratio=_HEAD_TURN_RATIO * intensity,
            ),
        )
        return _support_brow(pose, neutral_pose, operating_band, side="right", ratio=_BROW_SINGLE_RATIO * _SUPPORT_FAMILY_RATIO * intensity)
    if name.startswith("warm_blink"):
        pose = _with_lid_closure(neutral_pose, operating_band, ratio=_BLINK_RATIO * intensity)
        return _support_brows_both(pose, neutral_pose, operating_band, ratio=_BROW_BOTH_RATIO * _SUPPORT_FAMILY_RATIO * intensity)
    return neutral_pose.model_copy(deep=True)


def _support_brow(
    pose: BodyPose,
    neutral_pose: BodyPose,
    operating_band: DerivedOperatingBand,
    *,
    side: str,
    ratio: float,
) -> BodyPose:
    payload = pose.model_dump()
    negative = float(operating_band.brow.negative_limit)
    positive = float(operating_band.brow.positive_limit)
    field_name = "brow_raise_left" if side == "left" else "brow_raise_right"
    neutral_field = float(getattr(neutral_pose, field_name))
    payload[field_name] = _ratio_from_neutral(neutral_field, negative, positive, direction="raise", ratio=ratio)
    return BodyPose.model_validate(payload)


def _support_brows_both(
    pose: BodyPose,
    neutral_pose: BodyPose,
    operating_band: DerivedOperatingBand,
    *,
    ratio: float,
) -> BodyPose:
    payload = pose.model_dump()
    negative = float(operating_band.brow.negative_limit)
    positive = float(operating_band.brow.positive_limit)
    payload["brow_raise_left"] = _ratio_from_neutral(
        float(neutral_pose.brow_raise_left),
        negative,
        positive,
        direction="raise",
        ratio=ratio,
    )
    payload["brow_raise_right"] = _ratio_from_neutral(
        float(neutral_pose.brow_raise_right),
        negative,
        positive,
        direction="raise",
        ratio=ratio,
    )
    return BodyPose.model_validate(payload)
