from __future__ import annotations

from dataclasses import dataclass

from embodied_stack.shared.contracts.body import SemanticActionDescriptor

from .grounded_catalog import (
    GROUNDED_STATE_ALIASES,
    grounded_state_names,
    lookup_grounded_catalog_entry,
)
from .primitives import action_descriptor_metadata, primitive_action_names


CANONICAL_GAZE_TARGETS = (
    "look_at_user",
    "look_forward",
    "look_left",
    "look_right",
    "look_up",
    "look_down_briefly",
    "look_far_left",
    "look_far_right",
    "look_far_up",
    "look_far_down",
)
CANONICAL_EXPRESSIONS = grounded_state_names()
CANONICAL_GESTURES = (
    "blink_soft",
    "double_blink",
    "wink_left",
    "wink_right",
    "acknowledge_light",
    "playful_peek_left",
    "playful_peek_right",
    "nod_small",
    "nod_medium",
    "tilt_curious",
)
CANONICAL_ANIMATIONS = (
    "recover_neutral",
    "youthful_greeting",
    "soft_reengage",
    "playful_react",
)

LEGACY_GAZE_TARGETS = ("forward", "left", "right", "up", "down", "micro_reorient_left", "micro_reorient_right")
LEGACY_EXPRESSIONS = tuple(sorted(GROUNDED_STATE_ALIASES))
LEGACY_GESTURES = ("blink", "double_blink_emphasis", "micro_nod", "affirm_nod", "soft_nod", "tilt_left", "tilt_right")
LEGACY_ANIMATIONS = (
    "listening",
    "attentive",
    "thinking",
    "friendly",
    "safe_idle",
    "forward",
    "left",
    "right",
    "up",
    "down",
    "look_forward",
    "look_left",
    "look_right",
    "look_up",
    "look_down",
    "blink",
    "micro_nod",
    "affirm_nod",
    "tilt_left",
    "tilt_right",
    "listen_pose",
    "thinking_pose",
    "settle_attention",
    "settle_thinking",
    "micro_blink_loop",
    "scan_softly",
    "speak_listen_transition",
)

GAZE_ALIASES = {
    "forward": "look_forward",
    "look_forward": "look_forward",
    "left": "look_left",
    "look_left": "look_left",
    "micro_reorient_left": "look_left",
    "right": "look_right",
    "look_right": "look_right",
    "micro_reorient_right": "look_right",
    "up": "look_up",
    "look_up": "look_up",
    "down": "look_down_briefly",
    "look_down": "look_down_briefly",
    "far_left": "look_far_left",
    "far_right": "look_far_right",
    "far_up": "look_far_up",
    "far_down": "look_far_down",
}
EXPRESSION_ALIASES = dict(GROUNDED_STATE_ALIASES)
GESTURE_ALIASES = {
    "blink": "blink_soft",
    "double_blink_emphasis": "double_blink",
    "micro_nod": "acknowledge_light",
    "affirm_nod": "acknowledge_light",
    "soft_nod": "nod_medium",
    "tilt_left": "tilt_curious",
    "tilt_right": "tilt_curious",
}
ANIMATION_ALIASES = {
    "listen_pose": "listen_attentively",
    "thinking_pose": "thinking",
    "forward": "look_forward",
    "left": "look_left",
    "right": "look_right",
    "up": "look_up",
    "down": "look_down_briefly",
    "look_forward": "look_forward",
    "look_left": "look_left",
    "look_right": "look_right",
    "look_up": "look_up",
    "look_down": "look_down_briefly",
    "blink": "blink_soft",
    "micro_nod": "acknowledge_light",
    "affirm_nod": "acknowledge_light",
    "tilt_left": "tilt_curious",
    "tilt_right": "tilt_curious",
    "settle_attention": "soft_reengage",
    "settle_thinking": "recover_neutral",
    "micro_blink_loop": "blink_soft",
    "scan_softly": "recover_neutral",
    "speak_listen_transition": "soft_reengage",
    "listening": "listen_attentively",
    "attentive": "listen_attentively",
    "thinking": "thinking",
    "friendly": "friendly",
    "safe_idle": "safe_idle",
}

_SEMANTIC_ACTION_LIBRARY = {
    "look_forward": {
        "family": "gaze",
        "smoke_safe": True,
        "rollout_stage": "d6",
        "description": "Center the gaze into a calm forward hold.",
    },
    "look_at_user": {
        "family": "gaze",
        "smoke_safe": True,
        "rollout_stage": "d6",
        "description": "Bias the gaze toward a nearby user without adding extra structural motion.",
    },
    "look_left": {
        "family": "gaze",
        "smoke_safe": True,
        "rollout_stage": "d6",
        "description": "Perform a grounded leftward gaze unit.",
    },
    "look_right": {
        "family": "gaze",
        "smoke_safe": True,
        "rollout_stage": "d6",
        "description": "Perform a grounded rightward gaze unit.",
    },
    "look_up": {
        "family": "gaze",
        "smoke_safe": True,
        "rollout_stage": "d6",
        "description": "Perform a grounded upward gaze unit.",
    },
    "look_down_briefly": {
        "family": "gaze",
        "smoke_safe": True,
        "rollout_stage": "d6",
        "description": "Perform a grounded brief downward glance.",
    },
    "look_far_left": {
        "family": "gaze",
        "smoke_safe": True,
        "rollout_stage": "d6",
        "description": "Use the wider validated leftward gaze range.",
    },
    "look_far_right": {
        "family": "gaze",
        "smoke_safe": True,
        "rollout_stage": "d6",
        "description": "Use the wider validated rightward gaze range.",
    },
    "look_far_up": {
        "family": "gaze",
        "smoke_safe": True,
        "rollout_stage": "d6",
        "description": "Use the wider validated upward gaze range.",
    },
    "look_far_down": {
        "family": "gaze",
        "smoke_safe": True,
        "rollout_stage": "d6",
        "description": "Use the wider validated downward gaze range.",
    },
    "neutral": {
        "family": "expression",
        "smoke_safe": True,
        "rollout_stage": "d6",
        "description": "Grounded neutral held state.",
    },
    "friendly": {
        "family": "expression",
        "smoke_safe": True,
        "rollout_stage": "d6",
        "description": "Grounded friendly held state built from sustainable eye-area configuration.",
    },
    "listen_attentively": {
        "family": "expression",
        "smoke_safe": True,
        "rollout_stage": "d6",
        "description": "Grounded attentive listening held state.",
    },
    "thinking": {
        "family": "expression",
        "smoke_safe": True,
        "rollout_stage": "d6",
        "description": "Grounded thinking held state.",
    },
    "focused_soft": {
        "family": "expression",
        "smoke_safe": True,
        "rollout_stage": "d6",
        "description": "Grounded focused-soft held state.",
    },
    "concerned": {
        "family": "expression",
        "smoke_safe": True,
        "rollout_stage": "d6",
        "description": "Grounded concerned held state.",
    },
    "confused": {
        "family": "expression",
        "smoke_safe": True,
        "rollout_stage": "d6",
        "description": "Grounded confused held state.",
    },
    "safe_idle": {
        "family": "expression",
        "smoke_safe": True,
        "rollout_stage": "d6",
        "description": "Grounded safe-idle held state.",
    },
    "blink_soft": {
        "family": "gesture",
        "smoke_safe": True,
        "rollout_stage": "d6",
        "description": "Grounded soft blink gesture.",
    },
    "double_blink": {
        "family": "gesture",
        "smoke_safe": True,
        "rollout_stage": "d6",
        "description": "Grounded double blink gesture.",
    },
    "wink_left": {
        "family": "gesture",
        "smoke_safe": True,
        "rollout_stage": "d6",
        "description": "Grounded left wink gesture.",
    },
    "wink_right": {
        "family": "gesture",
        "smoke_safe": True,
        "rollout_stage": "d6",
        "description": "Grounded right wink gesture.",
    },
    "acknowledge_light": {
        "family": "gesture",
        "smoke_safe": True,
        "rollout_stage": "d6",
        "description": "Grounded light acknowledgement gesture.",
    },
    "playful_peek_left": {
        "family": "gesture",
        "smoke_safe": True,
        "rollout_stage": "d6",
        "description": "Grounded playful left peek gesture.",
    },
    "playful_peek_right": {
        "family": "gesture",
        "smoke_safe": True,
        "rollout_stage": "d6",
        "description": "Grounded playful right peek gesture.",
    },
    "nod_small": {
        "family": "gesture",
        "smoke_safe": True,
        "rollout_stage": "d5",
        "description": "Small acknowledgement nod backed by the tiny-nod grounded unit.",
    },
    "nod_medium": {
        "family": "gesture",
        "smoke_safe": True,
        "rollout_stage": "d5",
        "description": "Medium acknowledgement nod for bench-safe motion validation.",
    },
    "tilt_curious": {
        "family": "gesture",
        "smoke_safe": True,
        "rollout_stage": "d5",
        "description": "Curious tilt gesture built from the conservative neck tilt unit.",
    },
    "recover_neutral": {
        "family": "animation",
        "smoke_safe": True,
        "rollout_stage": "d6",
        "description": "Recover the head and eye area back to neutral.",
    },
    "youthful_greeting": {
        "family": "animation",
        "smoke_safe": True,
        "rollout_stage": "d6",
        "description": "Grounded greeting animation based on validated primitive recipes.",
    },
    "soft_reengage": {
        "family": "animation",
        "smoke_safe": True,
        "rollout_stage": "d6",
        "description": "Grounded soft reengagement animation.",
    },
    "playful_react": {
        "family": "animation",
        "smoke_safe": True,
        "rollout_stage": "d6",
        "description": "Grounded playful reaction animation.",
    },
}

for _primitive_name in primitive_action_names():
    _SEMANTIC_ACTION_LIBRARY.setdefault(
        _primitive_name,
        {
            "family": "animation",
            "smoke_safe": True,
            "rollout_stage": "d6",
            "description": f"Grounded primitive body action {_primitive_name.replace('_', ' ')}.",
        },
    )


@dataclass(frozen=True)
class SemanticActionName:
    family: str
    canonical_name: str
    source_name: str
    alias_used: bool = False


def normalize_action_name(name: str | None) -> str:
    return (name or "").strip().lower() or "neutral"


def normalize_gaze_name(name: str | None) -> SemanticActionName:
    source_name = normalize_action_name(name or "look_forward")
    canonical_name = GAZE_ALIASES.get(source_name, source_name)
    return SemanticActionName(
        family="gaze",
        canonical_name=canonical_name,
        source_name=source_name,
        alias_used=canonical_name != source_name,
    )


def normalize_expression_name(name: str | None) -> SemanticActionName:
    source_name = normalize_action_name(name)
    canonical_name = EXPRESSION_ALIASES.get(source_name, source_name)
    return SemanticActionName(
        family="expression",
        canonical_name=canonical_name,
        source_name=source_name,
        alias_used=canonical_name != source_name,
    )


def normalize_gesture_name(name: str | None) -> SemanticActionName:
    source_name = normalize_action_name(name)
    canonical_name = GESTURE_ALIASES.get(source_name, source_name)
    return SemanticActionName(
        family="gesture",
        canonical_name=canonical_name,
        source_name=source_name,
        alias_used=canonical_name != source_name,
    )


def normalize_animation_name(name: str | None) -> SemanticActionName:
    source_name = normalize_action_name(name)
    canonical_name = ANIMATION_ALIASES.get(source_name, source_name)
    return SemanticActionName(
        family="animation",
        canonical_name=canonical_name,
        source_name=source_name,
        alias_used=canonical_name != source_name,
    )


def accepted_expression_names() -> tuple[str, ...]:
    return (*CANONICAL_EXPRESSIONS, *LEGACY_EXPRESSIONS)


def accepted_gaze_names() -> tuple[str, ...]:
    return (*CANONICAL_GAZE_TARGETS, *LEGACY_GAZE_TARGETS)


def accepted_gesture_names() -> tuple[str, ...]:
    return (*CANONICAL_GESTURES, *LEGACY_GESTURES)


def accepted_animation_names() -> tuple[str, ...]:
    return (*CANONICAL_ANIMATIONS, *LEGACY_ANIMATIONS, *primitive_action_names())


def resolve_semantic_action(name: str | None) -> SemanticActionName:
    source_name = normalize_action_name(name)
    candidates = (
        (normalize_gaze_name, set(accepted_gaze_names())),
        (normalize_expression_name, set(accepted_expression_names())),
        (normalize_gesture_name, set(accepted_gesture_names())),
        (normalize_animation_name, set(accepted_animation_names())),
    )
    for resolver, accepted_names in candidates:
        normalized = resolver(source_name)
        if source_name in accepted_names or normalized.canonical_name in accepted_names:
            return normalized
    raise ValueError(f"unsupported_semantic_action:{source_name}")


def _aliases_for_action(canonical_name: str) -> list[str]:
    aliases: set[str] = set()
    for alias_map in (GAZE_ALIASES, EXPRESSION_ALIASES, GESTURE_ALIASES, ANIMATION_ALIASES):
        for source_name, target_name in alias_map.items():
            if target_name == canonical_name and source_name != canonical_name:
                aliases.add(source_name)
    grounded = lookup_grounded_catalog_entry(canonical_name)
    if grounded is not None:
        aliases.update(grounded.aliases)
    return sorted(aliases)


def _descriptor_metadata_from_catalog(canonical_name: str) -> dict[str, object]:
    entry = lookup_grounded_catalog_entry(canonical_name)
    primitive_metadata = action_descriptor_metadata(canonical_name)
    implementation_kind: str | None = None
    if entry is not None:
        implementation_kind = entry.implementation_kind
    elif primitive_metadata["grounding"] in {"primitive", "recipe"}:
        implementation_kind = "unit"
    support_status = entry.hardware_support_status if entry is not None else "supported"
    evidence_source = entry.evidence_source if entry is not None else None
    structural_units_used = list(entry.structural_units_used) if entry is not None else []
    expressive_units_used = list(entry.expressive_units_used) if entry is not None else []
    hold_supported = bool(entry.hold_supported) if entry is not None else primitive_metadata["grounding"] == "state"
    release_policy = entry.release_policy if entry is not None else ("returns_to_neutral" if primitive_metadata["returns_to_neutral"] else None)
    sequencing_rule = entry.sequencing_rule if entry is not None else None
    safe_tuning_lane = entry.safe_tuning_lane if entry is not None else None
    grounding = primitive_metadata["grounding"]
    if entry is not None and entry.implementation_kind == "state":
        grounding = "state"
    if entry is not None and entry.implementation_kind == "motif":
        grounding = "motif"
    return {
        "grounding": grounding,
        "implementation_kind": implementation_kind,
        "hardware_support_status": support_status,
        "evidence_source": evidence_source,
        "structural_units_used": structural_units_used,
        "expressive_units_used": expressive_units_used,
        "hold_supported": hold_supported,
        "release_policy": release_policy,
        "sequencing_rule": sequencing_rule,
        "safe_tuning_lane": safe_tuning_lane,
        "primary_actuator_group": primitive_metadata["primary_actuator_group"],
        "support_actuator_groups": primitive_metadata["support_actuator_groups"],
        "returns_to_neutral": primitive_metadata["returns_to_neutral"],
        "max_active_families": primitive_metadata["max_active_families"],
        "tempo_variant": primitive_metadata["tempo_variant"],
    }


def _build_descriptor(
    canonical_name: str,
    *,
    source_name: str | None = None,
    alias_used: bool = False,
    tuning_overrides: set[str] | None = None,
) -> SemanticActionDescriptor:
    metadata = _SEMANTIC_ACTION_LIBRARY[canonical_name]
    grounded_metadata = _descriptor_metadata_from_catalog(canonical_name)
    return SemanticActionDescriptor(
        family=str(metadata["family"]),
        canonical_name=canonical_name,
        aliases=_aliases_for_action(canonical_name),
        smoke_safe=bool(metadata["smoke_safe"]),
        rollout_stage=str(metadata["rollout_stage"]),
        description=str(metadata["description"]),
        tuning_override_active=canonical_name in (tuning_overrides or set()),
        grounding=str(grounded_metadata["grounding"]) if grounded_metadata["grounding"] is not None else None,
        primary_actuator_group=(
            str(grounded_metadata["primary_actuator_group"])
            if grounded_metadata["primary_actuator_group"] is not None
            else None
        ),
        support_actuator_groups=list(grounded_metadata["support_actuator_groups"]),
        returns_to_neutral=bool(grounded_metadata["returns_to_neutral"]),
        max_active_families=(
            int(grounded_metadata["max_active_families"])
            if grounded_metadata["max_active_families"] is not None
            else None
        ),
        tempo_variant=(
            str(grounded_metadata["tempo_variant"])
            if grounded_metadata["tempo_variant"] is not None
            else None
        ),
        implementation_kind=(
            str(grounded_metadata["implementation_kind"])
            if grounded_metadata["implementation_kind"] is not None
            else None
        ),
        hardware_support_status=str(grounded_metadata["hardware_support_status"]),
        evidence_source=(
            str(grounded_metadata["evidence_source"])
            if grounded_metadata["evidence_source"] is not None
            else None
        ),
        structural_units_used=list(grounded_metadata["structural_units_used"]),
        expressive_units_used=list(grounded_metadata["expressive_units_used"]),
        hold_supported=bool(grounded_metadata["hold_supported"]),
        release_policy=(
            str(grounded_metadata["release_policy"])
            if grounded_metadata["release_policy"] is not None
            else None
        ),
        sequencing_rule=(
            str(grounded_metadata["sequencing_rule"])
            if grounded_metadata["sequencing_rule"] is not None
            else None
        ),
        safe_tuning_lane=(
            str(grounded_metadata["safe_tuning_lane"])
            if grounded_metadata["safe_tuning_lane"] is not None
            else None
        ),
        alias_source=source_name if alias_used else None,
    )


def semantic_action_descriptors(
    *,
    tuning_overrides: set[str] | None = None,
    smoke_safe_only: bool = False,
) -> tuple[SemanticActionDescriptor, ...]:
    items: list[SemanticActionDescriptor] = []
    for canonical_name, metadata in _SEMANTIC_ACTION_LIBRARY.items():
        if smoke_safe_only and not bool(metadata["smoke_safe"]):
            continue
        items.append(_build_descriptor(canonical_name, tuning_overrides=tuning_overrides))
    return tuple(items)


def lookup_action_descriptor(
    name: str | None,
    *,
    tuning_overrides: set[str] | None = None,
) -> SemanticActionDescriptor | None:
    try:
        resolved = resolve_semantic_action(name)
    except ValueError:
        return None
    if resolved.canonical_name not in _SEMANTIC_ACTION_LIBRARY:
        return None
    return _build_descriptor(
        resolved.canonical_name,
        source_name=resolved.source_name,
        alias_used=resolved.alias_used,
        tuning_overrides=tuning_overrides,
    )


def build_semantic_smoke_request(
    action: str,
    *,
    intensity: float = 1.0,
    repeat_count: int = 1,
    note: str | None = None,
    tuning_overrides: set[str] | None = None,
    allow_bench_actions: bool = False,
) -> tuple[SemanticActionDescriptor, str, dict[str, object]]:
    descriptor = lookup_action_descriptor(action, tuning_overrides=tuning_overrides)
    if descriptor is None:
        raise ValueError(f"unsupported_semantic_action:{normalize_action_name(action)}")
    if not allow_bench_actions and not descriptor.smoke_safe:
        raise ValueError(f"semantic_smoke_requires_allow_bench_actions:{descriptor.canonical_name}")
    if descriptor.canonical_name == "safe_idle":
        return descriptor, "safe_idle", {"reason": note or "semantic_smoke"}
    payload: dict[str, object] = {"intensity": float(intensity)}
    if note:
        payload["note"] = note
    if descriptor.family == "gaze":
        payload["target"] = descriptor.canonical_name
        return descriptor, "set_gaze", payload
    if descriptor.family == "expression":
        payload["expression_name"] = descriptor.canonical_name
        return descriptor, "set_expression", payload
    if descriptor.family == "gesture":
        payload["gesture_name"] = descriptor.canonical_name
        payload["repeat_count"] = max(1, int(repeat_count))
        return descriptor, "perform_gesture", payload
    payload["animation_name"] = descriptor.canonical_name
    payload["repeat_count"] = max(1, int(repeat_count))
    return descriptor, "perform_animation", payload


__all__ = [
    "ANIMATION_ALIASES",
    "CANONICAL_ANIMATIONS",
    "CANONICAL_EXPRESSIONS",
    "CANONICAL_GAZE_TARGETS",
    "CANONICAL_GESTURES",
    "EXPRESSION_ALIASES",
    "GAZE_ALIASES",
    "GESTURE_ALIASES",
    "LEGACY_ANIMATIONS",
    "LEGACY_EXPRESSIONS",
    "LEGACY_GAZE_TARGETS",
    "LEGACY_GESTURES",
    "SemanticActionName",
    "accepted_animation_names",
    "accepted_expression_names",
    "accepted_gaze_names",
    "accepted_gesture_names",
    "build_semantic_smoke_request",
    "lookup_action_descriptor",
    "normalize_action_name",
    "normalize_animation_name",
    "normalize_expression_name",
    "normalize_gaze_name",
    "normalize_gesture_name",
    "resolve_semantic_action",
    "semantic_action_descriptors",
]
