from __future__ import annotations

from embodied_stack.body.grounded_catalog import (
    EXPRESSIVE_UNITS,
    GROUNDED_MOTIFS,
    GROUNDED_PERSISTENT_STATES,
    STRUCTURAL_UNITS,
    grounded_catalog_export,
    lookup_grounded_catalog_entry,
    resolve_grounded_state_name,
)
from embodied_stack.body.semantics import build_semantic_smoke_request, lookup_action_descriptor, semantic_action_descriptors


def test_stage_d_semantic_library_marks_smoke_safe_and_bench_only_actions() -> None:
    descriptors = {item.canonical_name: item for item in semantic_action_descriptors()}

    assert descriptors["look_left"].family == "gaze"
    assert descriptors["look_left"].smoke_safe is True
    assert descriptors["friendly"].family == "expression"
    assert descriptors["friendly"].implementation_kind == "state"
    assert descriptors["friendly"].hold_supported is True
    assert descriptors["friendly"].evidence_source is not None


def test_stage_d_lookup_resolves_legacy_aliases_to_canonical_actions() -> None:
    descriptor = lookup_action_descriptor("left")

    assert descriptor is not None
    assert descriptor.canonical_name == "look_left"
    assert "left" in descriptor.aliases


def test_stage_d_semantic_smoke_builds_family_specific_requests() -> None:
    descriptor, command_type, payload = build_semantic_smoke_request("look_left", intensity=0.8, repeat_count=2)

    assert descriptor.canonical_name == "look_left"
    assert command_type == "set_gaze"
    assert payload["target"] == "look_left"
    assert payload["intensity"] == 0.8

    descriptor, command_type, payload = build_semantic_smoke_request("friendly", intensity=0.6)
    assert descriptor.canonical_name == "friendly"
    assert command_type == "set_expression"
    assert payload["expression_name"] == "friendly"
    assert payload["intensity"] == 0.6

    descriptor, command_type, payload = build_semantic_smoke_request("blink_soft", intensity=0.5, repeat_count=2)
    assert descriptor.canonical_name == "blink_soft"
    assert command_type == "perform_gesture"
    assert payload["gesture_name"] == "blink_soft"
    assert payload["repeat_count"] == 2

    descriptor, command_type, payload = build_semantic_smoke_request("recover_neutral", intensity=0.7, repeat_count=3)
    assert descriptor.canonical_name == "recover_neutral"
    assert command_type == "perform_animation"
    assert payload["animation_name"] == "recover_neutral"
    assert payload["repeat_count"] == 3


def test_stage_d_expressive_upgrade_actions_are_present_in_semantic_library() -> None:
    descriptors = {item.canonical_name: item for item in semantic_action_descriptors()}

    assert descriptors["focused_soft"].family == "expression"
    assert descriptors["concerned"].family == "expression"
    assert descriptors["confused"].family == "expression"
    assert descriptors["double_blink"].family == "gesture"
    assert descriptors["acknowledge_light"].family == "gesture"
    assert descriptors["playful_peek_left"].family == "gesture"
    assert descriptors["playful_peek_right"].family == "gesture"
    assert descriptors["youthful_greeting"].family == "animation"
    assert descriptors["soft_reengage"].family == "animation"
    assert descriptors["playful_react"].family == "animation"
    assert descriptors["youthful_greeting"].smoke_safe is True


def test_stage_d_curious_alias_now_resolves_to_curious_bright() -> None:
    descriptor = lookup_action_descriptor("curious")

    assert descriptor is not None
    assert descriptor.canonical_name == "focused_soft"
    assert descriptor.alias_source == "curious"


def test_grounded_expression_catalog_export_is_canonical_and_supported() -> None:
    export = grounded_catalog_export()

    assert export.schema_version == "blink_grounded_expression_catalog/v1"
    assert set(export.supported_structural_units) == set(STRUCTURAL_UNITS)
    assert set(export.supported_expressive_units) == set(EXPRESSIVE_UNITS)
    assert set(export.supported_persistent_states) >= {"neutral", "friendly", "thinking", "concerned"}
    assert set(export.supported_persistent_states) == set(GROUNDED_PERSISTENT_STATES)
    assert set(export.supported_motifs) == set(GROUNDED_MOTIFS)
    assert export.alias_mapping["warm_greeting"] == "friendly"
    assert export.alias_mapping["curious"] == "focused_soft"

    for entry in export.entries:
        assert entry.hardware_support_status == "supported"
        assert entry.evidence_source is not None
        assert entry.safe_tuning_lane is not None
        assert set(entry.structural_units_used).issubset(STRUCTURAL_UNITS)
        assert set(entry.expressive_units_used).issubset(EXPRESSIVE_UNITS)


def test_grounded_aliases_resolve_to_exact_catalog_entries() -> None:
    assert resolve_grounded_state_name("warm_greeting") == "friendly"
    assert resolve_grounded_state_name("curious") == "focused_soft"

    friendly = lookup_grounded_catalog_entry("warm_greeting")
    focused = lookup_grounded_catalog_entry("curious")

    assert friendly is not None
    assert friendly.canonical_name == "friendly"
    assert focused is not None
    assert focused.canonical_name == "focused_soft"
