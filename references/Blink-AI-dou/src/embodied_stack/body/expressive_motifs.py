from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ExpressiveUnitSpec:
    action_name: str
    groups: tuple[str, ...]
    transient: bool = False


@dataclass(frozen=True)
class ExpressiveSequenceStepSpec:
    step_kind: str
    action_name: str | None = None
    intensity: float = 1.0
    release_groups: tuple[str, ...] = ()
    move_ms: int | None = None
    hold_ms: int | None = None
    note: str | None = None


@dataclass(frozen=True)
class ExpressiveMotifDefinition:
    motif_name: str
    title: str
    description: str
    steps: tuple[ExpressiveSequenceStepSpec, ...]


_ALLOWED_RELEASE_GROUPS = ("eye_yaw", "eye_pitch", "lids", "brows")

_STRUCTURAL_ACTIONS = {
    "head_turn_left_slow",
    "head_turn_right_slow",
    "head_pitch_up_slow",
    "head_pitch_down_slow",
    "head_tilt_left_slow",
    "head_tilt_right_slow",
}

_EXPRESSIVE_UNITS = {
    "eyes_left_slow": ExpressiveUnitSpec("eyes_left_slow", ("eye_yaw",)),
    "eyes_right_slow": ExpressiveUnitSpec("eyes_right_slow", ("eye_yaw",)),
    "eyes_up_slow": ExpressiveUnitSpec("eyes_up_slow", ("eye_pitch",)),
    "eyes_down_slow": ExpressiveUnitSpec("eyes_down_slow", ("eye_pitch",)),
    "close_both_eyes_slow": ExpressiveUnitSpec("close_both_eyes_slow", ("lids",)),
    "blink_both_slow": ExpressiveUnitSpec("blink_both_slow", ("lids",), transient=True),
    "double_blink_slow": ExpressiveUnitSpec("double_blink_slow", ("lids",), transient=True),
    "wink_left_slow": ExpressiveUnitSpec("wink_left_slow", ("lids",)),
    "wink_right_slow": ExpressiveUnitSpec("wink_right_slow", ("lids",)),
    "brows_raise_both_slow": ExpressiveUnitSpec("brows_raise_both_slow", ("brows",)),
    "brows_lower_both_slow": ExpressiveUnitSpec("brows_lower_both_slow", ("brows",)),
    "brow_left_raise_slow": ExpressiveUnitSpec("brow_left_raise_slow", ("brows",)),
    "brow_left_lower_slow": ExpressiveUnitSpec("brow_left_lower_slow", ("brows",)),
    "brow_right_raise_slow": ExpressiveUnitSpec("brow_right_raise_slow", ("brows",)),
    "brow_right_lower_slow": ExpressiveUnitSpec("brow_right_lower_slow", ("brows",)),
}


def structural_set(
    action_name: str,
    *,
    intensity: float = 1.0,
    move_ms: int | None = None,
    hold_ms: int | None = None,
    note: str | None = None,
) -> ExpressiveSequenceStepSpec:
    return ExpressiveSequenceStepSpec(
        step_kind="structural_set",
        action_name=action_name,
        intensity=intensity,
        move_ms=move_ms,
        hold_ms=hold_ms,
        note=note,
    )


def expressive_set(
    action_name: str,
    *,
    intensity: float = 1.0,
    move_ms: int | None = None,
    hold_ms: int | None = None,
    note: str | None = None,
) -> ExpressiveSequenceStepSpec:
    return ExpressiveSequenceStepSpec(
        step_kind="expressive_set",
        action_name=action_name,
        intensity=intensity,
        move_ms=move_ms,
        hold_ms=hold_ms,
        note=note,
    )


def expressive_release(
    *groups: str,
    move_ms: int | None = None,
    hold_ms: int | None = None,
    note: str | None = None,
) -> ExpressiveSequenceStepSpec:
    return ExpressiveSequenceStepSpec(
        step_kind="expressive_release",
        release_groups=tuple(groups),
        move_ms=move_ms,
        hold_ms=hold_ms,
        note=note,
    )


def hold(*, hold_ms: int, note: str | None = None) -> ExpressiveSequenceStepSpec:
    return ExpressiveSequenceStepSpec(
        step_kind="hold",
        hold_ms=hold_ms,
        note=note,
    )


def return_to_neutral(
    *,
    move_ms: int | None = None,
    hold_ms: int | None = None,
    note: str | None = None,
) -> ExpressiveSequenceStepSpec:
    return ExpressiveSequenceStepSpec(
        step_kind="return_to_neutral",
        move_ms=move_ms,
        hold_ms=hold_ms,
        note=note,
    )


def available_expressive_release_groups() -> tuple[str, ...]:
    return _ALLOWED_RELEASE_GROUPS


def expressive_motif_structural_actions() -> tuple[str, ...]:
    return tuple(sorted(_STRUCTURAL_ACTIONS))


def expressive_motif_action_names() -> tuple[str, ...]:
    return tuple(sorted(_EXPRESSIVE_UNITS))


def expressive_motif_unit(action_name: str) -> ExpressiveUnitSpec | None:
    return _EXPRESSIVE_UNITS.get(action_name)


def is_expressive_motif_structural_action(action_name: str | None) -> bool:
    return str(action_name or "").strip() in _STRUCTURAL_ACTIONS


def is_expressive_motif_action(action_name: str | None) -> bool:
    return str(action_name or "").strip() in _EXPRESSIVE_UNITS


_MOTIFS = {
    "attentive_notice_right": ExpressiveMotifDefinition(
        motif_name="attentive_notice_right",
        title="Attentive notice right",
        description="Head turns right, the eyes follow, the brows lift, then the expression releases before the head returns.",
        steps=(
            structural_set("head_turn_right_slow", intensity=0.9, move_ms=2400, hold_ms=900, note="turn_right"),
            expressive_set("eyes_right_slow", intensity=1.0, move_ms=900, hold_ms=700, note="eyes_follow"),
            expressive_set("brows_raise_both_slow", intensity=1.0, move_ms=900, hold_ms=700, note="brows_lift"),
            expressive_set("blink_both_slow", intensity=1.0, move_ms=900, hold_ms=0, note="soft_blink"),
            hold(hold_ms=500, note="read_expression"),
            expressive_release("brows", move_ms=850, hold_ms=350, note="brows_release"),
            expressive_release("eye_yaw", move_ms=900, hold_ms=350, note="eyes_center"),
            return_to_neutral(move_ms=2200, hold_ms=0, note="head_return"),
        ),
    ),
    "attentive_notice_left": ExpressiveMotifDefinition(
        motif_name="attentive_notice_left",
        title="Attentive notice left",
        description="Symmetric attentive notice to the left with the same structural-first ordering.",
        steps=(
            structural_set("head_turn_left_slow", intensity=0.9, move_ms=2400, hold_ms=900, note="turn_left"),
            expressive_set("eyes_left_slow", intensity=1.0, move_ms=900, hold_ms=700, note="eyes_follow"),
            expressive_set("brows_raise_both_slow", intensity=1.0, move_ms=900, hold_ms=700, note="brows_lift"),
            expressive_set("blink_both_slow", intensity=1.0, move_ms=900, hold_ms=0, note="soft_blink"),
            hold(hold_ms=500, note="read_expression"),
            expressive_release("brows", move_ms=850, hold_ms=350, note="brows_release"),
            expressive_release("eye_yaw", move_ms=900, hold_ms=350, note="eyes_center"),
            return_to_neutral(move_ms=2200, hold_ms=0, note="head_return"),
        ),
    ),
    "guarded_close_right": ExpressiveMotifDefinition(
        motif_name="guarded_close_right",
        title="Guarded close right",
        description="Head right, then eyes close and hold, then the brows lower, then each group releases in sequence before the head returns.",
        steps=(
            structural_set("head_turn_right_slow", intensity=1.0, move_ms=2600, hold_ms=1200, note="turn_right"),
            expressive_set("close_both_eyes_slow", intensity=1.0, move_ms=950, hold_ms=800, note="eyes_close_and_hold"),
            expressive_set("brows_lower_both_slow", intensity=1.0, move_ms=900, hold_ms=800, note="brows_frown_and_hold"),
            expressive_release("brows", move_ms=850, hold_ms=500, note="brows_release_while_eyes_stay_closed"),
            expressive_release("lids", move_ms=900, hold_ms=500, note="eyes_reopen"),
            return_to_neutral(move_ms=2200, hold_ms=0, note="head_return"),
        ),
    ),
    "guarded_close_left": ExpressiveMotifDefinition(
        motif_name="guarded_close_left",
        title="Guarded close left",
        description="Symmetric guarded close to the left with the same held-eye then brow-release ordering.",
        steps=(
            structural_set("head_turn_left_slow", intensity=1.0, move_ms=2600, hold_ms=1200, note="turn_left"),
            expressive_set("close_both_eyes_slow", intensity=1.0, move_ms=950, hold_ms=800, note="eyes_close_and_hold"),
            expressive_set("brows_lower_both_slow", intensity=1.0, move_ms=900, hold_ms=800, note="brows_frown_and_hold"),
            expressive_release("brows", move_ms=850, hold_ms=500, note="brows_release_while_eyes_stay_closed"),
            expressive_release("lids", move_ms=900, hold_ms=500, note="eyes_reopen"),
            return_to_neutral(move_ms=2200, hold_ms=0, note="head_return"),
        ),
    ),
    "curious_lift": ExpressiveMotifDefinition(
        motif_name="curious_lift",
        title="Curious lift",
        description="A conservative pitch-up settles first, then the eyes and brows respond upward, then release before the head returns.",
        steps=(
            structural_set("head_pitch_up_slow", intensity=0.85, move_ms=3000, hold_ms=1100, note="pitch_up"),
            expressive_set("eyes_up_slow", intensity=1.0, move_ms=900, hold_ms=700, note="eyes_up"),
            expressive_set("brows_raise_both_slow", intensity=1.0, move_ms=900, hold_ms=700, note="brows_lift"),
            expressive_set("blink_both_slow", intensity=0.9, move_ms=900, hold_ms=0, note="brief_blink"),
            expressive_release("brows", move_ms=850, hold_ms=350, note="brows_release"),
            expressive_release("eye_pitch", move_ms=900, hold_ms=350, note="eyes_center"),
            return_to_neutral(move_ms=2400, hold_ms=0, note="head_return"),
        ),
    ),
    "reflective_lower": ExpressiveMotifDefinition(
        motif_name="reflective_lower",
        title="Reflective lower",
        description="A downward pitch settles first, then the eyes lower, the brows knit, and the expression releases in sequence.",
        steps=(
            structural_set("head_pitch_down_slow", intensity=0.85, move_ms=3000, hold_ms=1100, note="pitch_down"),
            expressive_set("eyes_down_slow", intensity=1.0, move_ms=900, hold_ms=700, note="eyes_down"),
            expressive_set("brows_lower_both_slow", intensity=0.95, move_ms=900, hold_ms=700, note="brows_knit"),
            expressive_set("blink_both_slow", intensity=0.95, move_ms=900, hold_ms=0, note="slow_blink"),
            expressive_release("brows", move_ms=850, hold_ms=350, note="brows_release"),
            expressive_release("eye_pitch", move_ms=900, hold_ms=350, note="eyes_center"),
            return_to_neutral(move_ms=2400, hold_ms=0, note="head_return"),
        ),
    ),
    "skeptical_tilt_right": ExpressiveMotifDefinition(
        motif_name="skeptical_tilt_right",
        title="Skeptical tilt right",
        description="The neck tilts right, then the eyes follow, then one brow rises for skepticism before each group releases.",
        steps=(
            structural_set("head_tilt_right_slow", intensity=0.82, move_ms=3000, hold_ms=1100, note="tilt_right"),
            expressive_set("eyes_right_slow", intensity=0.8, move_ms=900, hold_ms=700, note="eyes_follow"),
            expressive_set("brow_left_raise_slow", intensity=0.85, move_ms=900, hold_ms=800, note="left_brow_raise"),
            expressive_release("brows", move_ms=850, hold_ms=350, note="brow_release"),
            expressive_release("eye_yaw", move_ms=900, hold_ms=350, note="eyes_center"),
            return_to_neutral(move_ms=2400, hold_ms=0, note="head_return"),
        ),
    ),
    "skeptical_tilt_left": ExpressiveMotifDefinition(
        motif_name="skeptical_tilt_left",
        title="Skeptical tilt left",
        description="The neck tilts left, then the eyes follow, then one brow rises for skepticism before each group releases.",
        steps=(
            structural_set("head_tilt_left_slow", intensity=0.82, move_ms=3000, hold_ms=1100, note="tilt_left"),
            expressive_set("eyes_left_slow", intensity=0.8, move_ms=900, hold_ms=700, note="eyes_follow"),
            expressive_set("brow_right_raise_slow", intensity=0.85, move_ms=900, hold_ms=800, note="right_brow_raise"),
            expressive_release("brows", move_ms=850, hold_ms=350, note="brow_release"),
            expressive_release("eye_yaw", move_ms=900, hold_ms=350, note="eyes_center"),
            return_to_neutral(move_ms=2400, hold_ms=0, note="head_return"),
        ),
    ),
    "empathetic_tilt_left": ExpressiveMotifDefinition(
        motif_name="empathetic_tilt_left",
        title="Empathetic tilt left",
        description="A left tilt settles first, then the brows soften upward and the lids blink before the expression releases.",
        steps=(
            structural_set("head_tilt_left_slow", intensity=0.82, move_ms=3000, hold_ms=1100, note="tilt_left"),
            expressive_set("brows_raise_both_slow", intensity=0.9, move_ms=900, hold_ms=700, note="soften_brows"),
            expressive_set("blink_both_slow", intensity=0.95, move_ms=900, hold_ms=0, note="empathetic_blink"),
            hold(hold_ms=500, note="read_empathy"),
            expressive_release("brows", move_ms=850, hold_ms=350, note="brows_release"),
            return_to_neutral(move_ms=2400, hold_ms=0, note="head_return"),
        ),
    ),
    "empathetic_tilt_right": ExpressiveMotifDefinition(
        motif_name="empathetic_tilt_right",
        title="Empathetic tilt right",
        description="A right tilt settles first, then the brows soften upward and the lids blink before the expression releases.",
        steps=(
            structural_set("head_tilt_right_slow", intensity=0.82, move_ms=3000, hold_ms=1100, note="tilt_right"),
            expressive_set("brows_raise_both_slow", intensity=0.9, move_ms=900, hold_ms=700, note="soften_brows"),
            expressive_set("blink_both_slow", intensity=0.95, move_ms=900, hold_ms=0, note="empathetic_blink"),
            hold(hold_ms=500, note="read_empathy"),
            expressive_release("brows", move_ms=850, hold_ms=350, note="brows_release"),
            return_to_neutral(move_ms=2400, hold_ms=0, note="head_return"),
        ),
    ),
    "playful_peek_right": ExpressiveMotifDefinition(
        motif_name="playful_peek_right",
        title="Playful peek right",
        description="The head turns right first, then the eyes push farther right, then a wink and brow lift stack playfully before releasing.",
        steps=(
            structural_set("head_turn_right_slow", intensity=0.72, move_ms=2400, hold_ms=900, note="turn_right"),
            expressive_set("eyes_right_slow", intensity=0.85, move_ms=900, hold_ms=700, note="eyes_push_right"),
            expressive_set("wink_right_slow", intensity=0.9, move_ms=900, hold_ms=700, note="wink_hold"),
            expressive_set("brow_right_raise_slow", intensity=0.85, move_ms=900, hold_ms=800, note="right_brow_raise"),
            expressive_release("brows", move_ms=850, hold_ms=350, note="brow_release"),
            expressive_release("lids", move_ms=900, hold_ms=350, note="wink_release"),
            expressive_release("eye_yaw", move_ms=900, hold_ms=350, note="eyes_center"),
            return_to_neutral(move_ms=2200, hold_ms=0, note="head_return"),
        ),
    ),
    "playful_peek_left": ExpressiveMotifDefinition(
        motif_name="playful_peek_left",
        title="Playful peek left",
        description="A mirrored playful side peek to the left.",
        steps=(
            structural_set("head_turn_left_slow", intensity=0.72, move_ms=2400, hold_ms=900, note="turn_left"),
            expressive_set("eyes_left_slow", intensity=0.85, move_ms=900, hold_ms=700, note="eyes_push_left"),
            expressive_set("wink_left_slow", intensity=0.9, move_ms=900, hold_ms=700, note="wink_hold"),
            expressive_set("brow_left_raise_slow", intensity=0.85, move_ms=900, hold_ms=800, note="left_brow_raise"),
            expressive_release("brows", move_ms=850, hold_ms=350, note="brow_release"),
            expressive_release("lids", move_ms=900, hold_ms=350, note="wink_release"),
            expressive_release("eye_yaw", move_ms=900, hold_ms=350, note="eyes_center"),
            return_to_neutral(move_ms=2200, hold_ms=0, note="head_return"),
        ),
    ),
    "bright_reengage": ExpressiveMotifDefinition(
        motif_name="bright_reengage",
        title="Bright reengage",
        description="A moderate turn sets the structure, then the eyes follow, the lids double blink, and the brows lift before returning.",
        steps=(
            structural_set("head_turn_left_slow", intensity=0.82, move_ms=2400, hold_ms=900, note="turn_left"),
            expressive_set("eyes_left_slow", intensity=0.95, move_ms=900, hold_ms=700, note="eyes_follow"),
            expressive_set("double_blink_slow", intensity=0.95, move_ms=900, hold_ms=0, note="double_blink"),
            expressive_set("brows_raise_both_slow", intensity=1.0, move_ms=900, hold_ms=800, note="brows_lift"),
            expressive_release("brows", move_ms=850, hold_ms=350, note="brows_release"),
            expressive_release("eye_yaw", move_ms=900, hold_ms=350, note="eyes_center"),
            return_to_neutral(move_ms=2200, hold_ms=0, note="head_return"),
        ),
    ),
    "doubtful_side_glance": ExpressiveMotifDefinition(
        motif_name="doubtful_side_glance",
        title="Doubtful side glance",
        description="A restrained side turn leads into a doubtful eye-line and one-brow lift before the expression releases.",
        steps=(
            structural_set("head_turn_left_slow", intensity=0.68, move_ms=2400, hold_ms=900, note="turn_left"),
            expressive_set("eyes_left_slow", intensity=0.82, move_ms=900, hold_ms=700, note="eyes_hold_left"),
            expressive_set("brow_right_raise_slow", intensity=0.95, move_ms=900, hold_ms=800, note="right_brow_raise"),
            hold(hold_ms=500, note="read_doubt"),
            expressive_release("brows", move_ms=850, hold_ms=350, note="brow_release"),
            expressive_release("eye_yaw", move_ms=900, hold_ms=350, note="eyes_center"),
            return_to_neutral(move_ms=2200, hold_ms=0, note="head_return"),
        ),
    ),
}


def expressive_motif_names() -> tuple[str, ...]:
    return tuple(sorted(_MOTIFS))


def resolve_expressive_motif(name: str) -> ExpressiveMotifDefinition | None:
    return _MOTIFS.get(name)
