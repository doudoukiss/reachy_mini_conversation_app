from __future__ import annotations

from dataclasses import dataclass

from embodied_stack.shared.contracts.body import (
    BodyPose,
    GroundedExpressionCatalogEntry,
    GroundedExpressionCatalogExport,
)


EVIDENCE_V3 = "v3_head_yaw_proof:performance-ae00f17a1a41"
EVIDENCE_V4 = "v4_eye_proof:performance-cb00a731feb4"
EVIDENCE_V5 = "v5_lid_proof:performance-565508ad7b31"
EVIDENCE_V6 = "v6_brow_proof:performance-b0b5d0fb439a"
EVIDENCE_V7 = "v7_neck_proof:performance-1f5472ad5a3f"
EVIDENCE_V8 = "v8_expressive_motif_proof:performance-671025f99a17"
EVIDENCE_V8_GUARDED_RIGHT = "v8_guarded_close_right:performance-ff4b6d13bde8"
EVIDENCE_V8_GUARDED_LEFT = "v8_guarded_close_left:performance-d92191a96cd3"

STRUCTURAL_UNITS = (
    "head_turn_left_slow",
    "head_turn_right_slow",
    "head_pitch_up_slow",
    "head_pitch_down_slow",
    "head_tilt_left_slow",
    "head_tilt_right_slow",
)
EXPRESSIVE_UNITS = (
    "eyes_left_slow",
    "eyes_right_slow",
    "eyes_up_slow",
    "eyes_down_slow",
    "close_both_eyes_slow",
    "blink_both_slow",
    "double_blink_slow",
    "wink_left_slow",
    "wink_right_slow",
    "brows_raise_both_slow",
    "brows_lower_both_slow",
    "brow_left_raise_slow",
    "brow_left_lower_slow",
    "brow_right_raise_slow",
    "brow_right_lower_slow",
)

DEFAULT_PREVIEW_NEUTRAL_POSE = BodyPose(
    upper_lid_left_open=0.7142857,
    upper_lid_right_open=0.7142857,
    lower_lid_left_open=0.75,
    lower_lid_right_open=0.75,
    brow_raise_left=0.5,
    brow_raise_right=0.5,
)

GROUNDED_PERSISTENT_STATES = (
    "neutral",
    "friendly",
    "listen_attentively",
    "thinking",
    "focused_soft",
    "concerned",
    "confused",
    "safe_idle",
)

GROUNDED_STATE_ALIASES = {
    "warm_greeting": "friendly",
    "listening": "listen_attentively",
    "attentive": "listen_attentively",
    "attentive_ready": "listen_attentively",
    "listen_soft": "listen_attentively",
    "processing": "thinking",
    "curious": "focused_soft",
    "ready": "listen_attentively",
    "deep_thinking": "thinking",
    "thinking_deep": "thinking",
    "listening_soft": "listen_attentively",
    "curious_bright": "friendly",
    "playful": "friendly",
    "bashful": "focused_soft",
    "eyes_widen": "friendly",
    "half_lid_focus": "focused_soft",
    "brow_raise_soft": "friendly",
    "brow_knit_soft": "concerned",
    "brows_soft_raise": "friendly",
    "eyelids_soft_focus": "focused_soft",
    "surprised": "friendly",
    "sleepy": "safe_idle",
}

GROUNDED_MOTIFS = (
    "attentive_notice_right",
    "attentive_notice_left",
    "guarded_close_right",
    "guarded_close_left",
    "curious_lift",
    "reflective_lower",
    "skeptical_tilt_right",
    "skeptical_tilt_left",
    "empathetic_tilt_left",
    "empathetic_tilt_right",
    "playful_peek_right",
    "playful_peek_left",
    "bright_reengage",
    "doubtful_side_glance",
)


@dataclass(frozen=True)
class GroundedPersistentStateSpec:
    canonical_name: str
    description: str
    evidence_source: str
    expressive_units_used: tuple[str, ...]
    pose_deltas: dict[str, float]
    aliases: tuple[str, ...] = ()
    sequencing_rule: str = "held_eye_area_only"
    release_policy: str = "held_until_replaced"
    safe_tuning_lane: str = "default_live"


@dataclass(frozen=True)
class GroundedGazePreviewSpec:
    canonical_name: str
    description: str
    structural_units_used: tuple[str, ...]
    expressive_units_used: tuple[str, ...]
    pose_deltas: dict[str, float]


_STATE_SPECS = {
    "neutral": GroundedPersistentStateSpec(
        canonical_name="neutral",
        description="Full neutral held state with all expressive groups at calibrated neutral.",
        evidence_source=EVIDENCE_V3,
        expressive_units_used=(),
        pose_deltas={},
    ),
    "friendly": GroundedPersistentStateSpec(
        canonical_name="friendly",
        description="Soft friendly held eye-area state with slightly lifted brows and softer lids.",
        evidence_source=EVIDENCE_V6,
        expressive_units_used=("brows_raise_both_slow",),
        pose_deltas={
            "upper_lid_left_open": -0.04,
            "upper_lid_right_open": -0.04,
            "lower_lid_left_open": -0.02,
            "lower_lid_right_open": -0.02,
            "brow_raise_left": 0.12,
            "brow_raise_right": 0.12,
        },
        aliases=("warm_greeting",),
    ),
    "listen_attentively": GroundedPersistentStateSpec(
        canonical_name="listen_attentively",
        description="Stable attentive listening state using only held eye-area configuration.",
        evidence_source=EVIDENCE_V6,
        expressive_units_used=("brows_raise_both_slow",),
        pose_deltas={
            "upper_lid_left_open": -0.05,
            "upper_lid_right_open": -0.05,
            "lower_lid_left_open": -0.03,
            "lower_lid_right_open": -0.03,
            "brow_raise_left": 0.10,
            "brow_raise_right": 0.10,
        },
        aliases=("listening", "attentive", "ready", "listening_soft"),
    ),
    "thinking": GroundedPersistentStateSpec(
        canonical_name="thinking",
        description="Held thinking state grounded in eyes-down plus one-brow lift, without structural motion.",
        evidence_source=EVIDENCE_V4,
        expressive_units_used=("eyes_down_slow", "brow_left_raise_slow"),
        pose_deltas={
            "eye_pitch": -0.12,
            "upper_lid_left_open": -0.08,
            "upper_lid_right_open": -0.08,
            "lower_lid_left_open": -0.03,
            "lower_lid_right_open": -0.03,
            "brow_raise_left": 0.08,
            "brow_raise_right": 0.02,
        },
        aliases=("processing", "deep_thinking"),
    ),
    "focused_soft": GroundedPersistentStateSpec(
        canonical_name="focused_soft",
        description="Held focused state using downward eye bias and half-lidded concentration.",
        evidence_source=EVIDENCE_V4,
        expressive_units_used=("eyes_down_slow",),
        pose_deltas={
            "eye_pitch": -0.08,
            "upper_lid_left_open": -0.12,
            "upper_lid_right_open": -0.12,
            "lower_lid_left_open": -0.04,
            "lower_lid_right_open": -0.04,
            "brow_raise_left": 0.04,
            "brow_raise_right": 0.04,
        },
        aliases=("curious", "bashful", "half_lid_focus"),
    ),
    "concerned": GroundedPersistentStateSpec(
        canonical_name="concerned",
        description="Held concerned state grounded in slightly tightened lids and lowered brows.",
        evidence_source=EVIDENCE_V6,
        expressive_units_used=("brows_lower_both_slow",),
        pose_deltas={
            "upper_lid_left_open": -0.10,
            "upper_lid_right_open": -0.10,
            "lower_lid_left_open": -0.03,
            "lower_lid_right_open": -0.03,
            "brow_raise_left": -0.08,
            "brow_raise_right": -0.08,
        },
        aliases=("brow_knit_soft",),
    ),
    "confused": GroundedPersistentStateSpec(
        canonical_name="confused",
        description="Held confused state grounded in one-brow asymmetry and a slight eye-side bias.",
        evidence_source=EVIDENCE_V6,
        expressive_units_used=("brow_left_raise_slow", "eyes_right_slow"),
        pose_deltas={
            "eye_yaw": 0.05,
            "upper_lid_left_open": -0.04,
            "upper_lid_right_open": -0.04,
            "brow_raise_left": 0.14,
            "brow_raise_right": -0.04,
        },
    ),
    "safe_idle": GroundedPersistentStateSpec(
        canonical_name="safe_idle",
        description="Held low-strain idle state for degraded operation and recovery.",
        evidence_source=EVIDENCE_V5,
        expressive_units_used=(),
        pose_deltas={
            "upper_lid_left_open": -0.06,
            "upper_lid_right_open": -0.06,
            "lower_lid_left_open": -0.04,
            "lower_lid_right_open": -0.04,
            "brow_raise_left": 0.02,
            "brow_raise_right": 0.02,
        },
    ),
}

_GAZE_PREVIEW_SPECS = {
    "look_forward": GroundedGazePreviewSpec(
        canonical_name="look_forward",
        description="Neutral forward gaze.",
        structural_units_used=(),
        expressive_units_used=(),
        pose_deltas={},
    ),
    "look_at_user": GroundedGazePreviewSpec(
        canonical_name="look_at_user",
        description="Near-forward social gaze for user-facing interaction.",
        structural_units_used=(),
        expressive_units_used=(),
        pose_deltas={},
    ),
    "look_left": GroundedGazePreviewSpec(
        canonical_name="look_left",
        description="Moderate coordinated leftward gaze preview.",
        structural_units_used=("head_turn_left_slow",),
        expressive_units_used=("eyes_left_slow",),
        pose_deltas={"head_yaw": -0.18, "eye_yaw": -0.26},
    ),
    "look_right": GroundedGazePreviewSpec(
        canonical_name="look_right",
        description="Moderate coordinated rightward gaze preview.",
        structural_units_used=("head_turn_right_slow",),
        expressive_units_used=("eyes_right_slow",),
        pose_deltas={"head_yaw": 0.18, "eye_yaw": 0.26},
    ),
    "look_up": GroundedGazePreviewSpec(
        canonical_name="look_up",
        description="Upward gaze preview using eye pitch only.",
        structural_units_used=(),
        expressive_units_used=("eyes_up_slow",),
        pose_deltas={"eye_pitch": 0.22},
    ),
    "look_down_briefly": GroundedGazePreviewSpec(
        canonical_name="look_down_briefly",
        description="Downward glance preview using eye pitch only.",
        structural_units_used=(),
        expressive_units_used=("eyes_down_slow",),
        pose_deltas={"eye_pitch": -0.18},
    ),
    "look_far_left": GroundedGazePreviewSpec(
        canonical_name="look_far_left",
        description="Wider leftward gaze preview near the verified V3/V4 evidence range.",
        structural_units_used=("head_turn_left_slow",),
        expressive_units_used=("eyes_left_slow",),
        pose_deltas={"head_yaw": -0.28, "eye_yaw": -0.34},
    ),
    "look_far_right": GroundedGazePreviewSpec(
        canonical_name="look_far_right",
        description="Wider rightward gaze preview near the verified V3/V4 evidence range.",
        structural_units_used=("head_turn_right_slow",),
        expressive_units_used=("eyes_right_slow",),
        pose_deltas={"head_yaw": 0.28, "eye_yaw": 0.34},
    ),
    "look_far_up": GroundedGazePreviewSpec(
        canonical_name="look_far_up",
        description="Wider upward gaze preview near the verified V4 evidence range.",
        structural_units_used=(),
        expressive_units_used=("eyes_up_slow",),
        pose_deltas={"eye_pitch": 0.30},
    ),
    "look_far_down": GroundedGazePreviewSpec(
        canonical_name="look_far_down",
        description="Wider downward gaze preview near the verified V4 evidence range.",
        structural_units_used=(),
        expressive_units_used=("eyes_down_slow",),
        pose_deltas={"eye_pitch": -0.24},
    ),
}

_MOTIF_ENTRY_DATA = {
    "attentive_notice_right": {
        "description": "Structural right turn followed by delayed eye and brow response.",
        "evidence_source": EVIDENCE_V8,
        "structural_units_used": ["head_turn_right_slow"],
        "expressive_units_used": ["eyes_right_slow", "brows_raise_both_slow", "blink_both_slow"],
    },
    "attentive_notice_left": {
        "description": "Structural left turn followed by delayed eye and brow response.",
        "evidence_source": EVIDENCE_V8,
        "structural_units_used": ["head_turn_left_slow"],
        "expressive_units_used": ["eyes_left_slow", "brows_raise_both_slow", "blink_both_slow"],
    },
    "guarded_close_right": {
        "description": "Head right, lids close and hold, brows lower and release, lids release, then structural return.",
        "evidence_source": EVIDENCE_V8_GUARDED_RIGHT,
        "structural_units_used": ["head_turn_right_slow"],
        "expressive_units_used": ["close_both_eyes_slow", "brows_lower_both_slow"],
    },
    "guarded_close_left": {
        "description": "Head left, lids close and hold, brows lower and release, lids release, then structural return.",
        "evidence_source": EVIDENCE_V8_GUARDED_LEFT,
        "structural_units_used": ["head_turn_left_slow"],
        "expressive_units_used": ["close_both_eyes_slow", "brows_lower_both_slow"],
    },
    "curious_lift": {
        "description": "Conservative pitch-up followed by delayed upward eye-area response.",
        "evidence_source": EVIDENCE_V8,
        "structural_units_used": ["head_pitch_up_slow"],
        "expressive_units_used": ["eyes_up_slow", "brows_raise_both_slow", "blink_both_slow"],
    },
    "reflective_lower": {
        "description": "Conservative pitch-down followed by delayed downward eye-area response.",
        "evidence_source": EVIDENCE_V8,
        "structural_units_used": ["head_pitch_down_slow"],
        "expressive_units_used": ["eyes_down_slow", "brows_lower_both_slow", "blink_both_slow"],
    },
    "skeptical_tilt_right": {
        "description": "Right tilt held while eyes and one brow add skepticism in sequence.",
        "evidence_source": EVIDENCE_V8,
        "structural_units_used": ["head_tilt_right_slow"],
        "expressive_units_used": ["eyes_right_slow", "brow_left_raise_slow"],
    },
    "skeptical_tilt_left": {
        "description": "Left tilt held while eyes and one brow add skepticism in sequence.",
        "evidence_source": EVIDENCE_V8,
        "structural_units_used": ["head_tilt_left_slow"],
        "expressive_units_used": ["eyes_left_slow", "brow_right_raise_slow"],
    },
    "empathetic_tilt_left": {
        "description": "Left tilt held while brows soften and lids respond in sequence.",
        "evidence_source": EVIDENCE_V8,
        "structural_units_used": ["head_tilt_left_slow"],
        "expressive_units_used": ["brows_raise_both_slow", "blink_both_slow"],
    },
    "empathetic_tilt_right": {
        "description": "Right tilt held while brows soften and lids respond in sequence.",
        "evidence_source": EVIDENCE_V8,
        "structural_units_used": ["head_tilt_right_slow"],
        "expressive_units_used": ["brows_raise_both_slow", "blink_both_slow"],
    },
    "playful_peek_right": {
        "description": "Right turn held while eyes push farther right, then wink and brow lift release in order.",
        "evidence_source": EVIDENCE_V8,
        "structural_units_used": ["head_turn_right_slow"],
        "expressive_units_used": ["eyes_right_slow", "wink_right_slow", "brow_right_raise_slow"],
    },
    "playful_peek_left": {
        "description": "Left turn held while eyes push farther left, then wink and brow lift release in order.",
        "evidence_source": EVIDENCE_V8,
        "structural_units_used": ["head_turn_left_slow"],
        "expressive_units_used": ["eyes_left_slow", "wink_left_slow", "brow_left_raise_slow"],
    },
    "bright_reengage": {
        "description": "Moderate structural turn with delayed eye follow, double blink, and brow lift.",
        "evidence_source": EVIDENCE_V8,
        "structural_units_used": ["head_turn_left_slow"],
        "expressive_units_used": ["eyes_left_slow", "double_blink_slow", "brows_raise_both_slow"],
    },
    "doubtful_side_glance": {
        "description": "Restrained side turn with delayed doubtful eye-line and one-brow lift.",
        "evidence_source": EVIDENCE_V8,
        "structural_units_used": ["head_turn_left_slow"],
        "expressive_units_used": ["eyes_left_slow", "brow_right_raise_slow"],
    },
}


def grounded_state_names() -> tuple[str, ...]:
    return GROUNDED_PERSISTENT_STATES


def grounded_state_aliases() -> dict[str, str]:
    return dict(GROUNDED_STATE_ALIASES)


def grounded_motif_names() -> tuple[str, ...]:
    return GROUNDED_MOTIFS


def grounded_structural_unit_names() -> tuple[str, ...]:
    return STRUCTURAL_UNITS


def grounded_expressive_unit_names() -> tuple[str, ...]:
    return EXPRESSIVE_UNITS


def resolve_grounded_state_name(name: str | None) -> str | None:
    normalized = str(name or "").strip().lower()
    if not normalized:
        return None
    return GROUNDED_STATE_ALIASES.get(normalized, normalized if normalized in _STATE_SPECS else None)


def build_grounded_state_pose(
    name: str | None,
    *,
    intensity: float,
    neutral_pose: BodyPose,
) -> BodyPose | None:
    canonical_name = resolve_grounded_state_name(name)
    if canonical_name is None:
        return None
    spec = _STATE_SPECS[canonical_name]
    normalized_intensity = max(0.0, min(1.0, float(intensity)))
    payload = neutral_pose.model_dump()
    for field_name, delta in spec.pose_deltas.items():
        neutral_value = float(payload[field_name])
        if field_name in {"head_yaw", "head_pitch", "head_roll", "eye_yaw", "eye_pitch"}:
            payload[field_name] = max(-1.0, min(1.0, neutral_value + (float(delta) * normalized_intensity)))
        else:
            payload[field_name] = max(0.0, min(1.0, neutral_value + (float(delta) * normalized_intensity)))
    return BodyPose.model_validate(payload)


def build_grounded_gaze_preview_pose(
    name: str | None,
    *,
    intensity: float,
    neutral_pose: BodyPose,
) -> BodyPose | None:
    normalized = str(name or "").strip().lower()
    spec = _GAZE_PREVIEW_SPECS.get(normalized)
    if spec is None:
        return None
    normalized_intensity = max(0.0, min(1.0, float(intensity)))
    payload = neutral_pose.model_dump()
    for field_name, delta in spec.pose_deltas.items():
        neutral_value = float(payload[field_name])
        payload[field_name] = max(-1.0, min(1.0, neutral_value + (float(delta) * normalized_intensity)))
    return BodyPose.model_validate(payload)


def grounded_catalog_entries() -> tuple[GroundedExpressionCatalogEntry, ...]:
    entries: list[GroundedExpressionCatalogEntry] = []
    for name in STRUCTURAL_UNITS:
        evidence_source = EVIDENCE_V3 if "turn" in name else EVIDENCE_V7
        entries.append(
            GroundedExpressionCatalogEntry(
                canonical_name=name,
                family="unit",
                implementation_kind="unit",
                evidence_source=evidence_source,
                description=f"Validated structural unit {name}.",
                sequencing_rule="one_structural_family_at_a_time",
                hold_supported=False,
                release_policy="returns_to_neutral_in_primitive_lane",
                safe_tuning_lane="investor_show_joint_envelope_v1",
                structural_units_used=[name],
                constraints=["structural_only", "no_concurrent_eye_area_change"],
            )
        )
    for name in EXPRESSIVE_UNITS:
        evidence_source = EVIDENCE_V4
        if "eye" not in name:
            evidence_source = EVIDENCE_V5 if "wink" in name or "close_both_eyes" in name else EVIDENCE_V6
        entries.append(
            GroundedExpressionCatalogEntry(
                canonical_name=name,
                family="unit",
                implementation_kind="unit",
                evidence_source=evidence_source,
                description=f"Validated expressive unit {name}.",
                sequencing_rule="one_expressive_unit_change_at_a_time",
                hold_supported=not name.startswith("blink") and not name.startswith("double_blink"),
                release_policy="hold_until_explicit_release_or_recover",
                safe_tuning_lane="investor_expressive_sequence_joint_envelope_v1",
                expressive_units_used=[name],
                constraints=["eye_area_only", "structural_must_be_still"],
            )
        )
    for spec in _STATE_SPECS.values():
        entries.append(
            GroundedExpressionCatalogEntry(
                canonical_name=spec.canonical_name,
                family="expression",
                implementation_kind="state",
                evidence_source=spec.evidence_source,
                description=spec.description,
                sequencing_rule=spec.sequencing_rule,
                hold_supported=True,
                release_policy=spec.release_policy,
                safe_tuning_lane=spec.safe_tuning_lane,
                expressive_units_used=list(spec.expressive_units_used),
                aliases=list(spec.aliases),
                constraints=["no_structural_dependency", "held_eye_area_configuration_only"],
            )
        )
    for name, data in _MOTIF_ENTRY_DATA.items():
        entries.append(
            GroundedExpressionCatalogEntry(
                canonical_name=name,
                family="animation",
                implementation_kind="motif",
                evidence_source=str(data["evidence_source"]),
                description=str(data["description"]),
                sequencing_rule="structural_set_then_expressive_sequence_then_release_then_return",
                hold_supported=True,
                release_policy="expressive_groups_release_before_structural_return",
                safe_tuning_lane="investor_expressive_sequence_joint_envelope_v1",
                structural_units_used=list(data["structural_units_used"]),
                expressive_units_used=list(data["expressive_units_used"]),
                constraints=[
                    "one_structural_family_at_a_time",
                    "one_expressive_unit_change_at_a_time",
                    "final_full_neutral_confirm_required",
                ],
            )
        )
    return tuple(entries)


def grounded_catalog_export() -> GroundedExpressionCatalogExport:
    return GroundedExpressionCatalogExport(
        supported_structural_units=list(STRUCTURAL_UNITS),
        supported_expressive_units=list(EXPRESSIVE_UNITS),
        supported_persistent_states=list(GROUNDED_PERSISTENT_STATES),
        supported_motifs=list(GROUNDED_MOTIFS),
        alias_mapping=dict(GROUNDED_STATE_ALIASES),
        entries=list(grounded_catalog_entries()),
        notes=[
            "Structural motion and eye-area motion must be sequenced, not concurrent, in maintained expressive behavior.",
            "Public persistent states are held eye-area configurations only; structural motion belongs in motifs.",
            "V3-V7 provide the family evidence ladder; V8 provides the expressive motif proof lane.",
        ],
    )


def lookup_grounded_catalog_entry(name: str | None) -> GroundedExpressionCatalogEntry | None:
    normalized = str(name or "").strip().lower()
    if not normalized:
        return None
    canonical = GROUNDED_STATE_ALIASES.get(normalized, normalized)
    for entry in grounded_catalog_entries():
        if entry.canonical_name == canonical:
            return entry
        if normalized in entry.aliases:
            return entry
    return None


def grounded_preview_neutral_pose() -> BodyPose:
    return DEFAULT_PREVIEW_NEUTRAL_POSE.model_copy(deep=True)


__all__ = [
    "EVIDENCE_V3",
    "EVIDENCE_V4",
    "EVIDENCE_V5",
    "EVIDENCE_V6",
    "EVIDENCE_V7",
    "EVIDENCE_V8",
    "GROUNDED_MOTIFS",
    "GROUNDED_PERSISTENT_STATES",
    "GROUNDED_STATE_ALIASES",
    "EXPRESSIVE_UNITS",
    "STRUCTURAL_UNITS",
    "build_grounded_gaze_preview_pose",
    "build_grounded_state_pose",
    "grounded_preview_neutral_pose",
    "grounded_catalog_entries",
    "grounded_catalog_export",
    "grounded_expressive_unit_names",
    "grounded_motif_names",
    "grounded_state_aliases",
    "grounded_state_names",
    "grounded_structural_unit_names",
    "lookup_grounded_catalog_entry",
    "resolve_grounded_state_name",
]
