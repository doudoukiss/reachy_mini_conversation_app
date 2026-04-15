from __future__ import annotations

from pathlib import Path

from embodied_stack.body.projection import build_character_semantic_intent, resolve_character_projection_profile
from embodied_stack.config import Settings
from embodied_stack.desktop.runtime import DesktopRuntimeGateway
from embodied_stack.shared.contracts import (
    CharacterProjectionProfile,
    CompanionPresenceState,
    CompanionPresenceStatus,
    CompanionVoiceLoopState,
    CompanionVoiceLoopStatus,
    FallbackState,
    InitiativeStatus,
    RelationshipContinuityStatus,
    RobotMode,
)


def build_settings(tmp_path: Path, **overrides) -> Settings:
    return Settings(
        _env_file=None,
        brain_store_path=str(tmp_path / "brain_store.json"),
        demo_report_dir=str(tmp_path / "demo_runs"),
        demo_check_dir=str(tmp_path / "demo_checks"),
        episode_export_dir=str(tmp_path / "episodes"),
        shift_report_dir=str(tmp_path / "shift_reports"),
        operator_auth_token="projection-test-token",
        operator_auth_runtime_file=str(tmp_path / "operator_auth.json"),
        **overrides,
    )


def test_character_semantic_intent_tracks_presence_semantics() -> None:
    intent = build_character_semantic_intent(
        presence_status=CompanionPresenceStatus(state=CompanionPresenceState.REENGAGING, slow_path_active=True),
        voice_status=CompanionVoiceLoopStatus(state=CompanionVoiceLoopState.INTERRUPTED),
        initiative_status=InitiativeStatus(),
        relationship_status=RelationshipContinuityStatus(known_user=True, returning_user=True),
        fallback_state=FallbackState(),
    )

    assert intent.surface_state == "interrupted"
    assert intent.expression_name == "listen_attentively"
    assert intent.gaze_target == "look_at_user"
    assert intent.gesture_name == "blink_soft"
    assert intent.animation_name is None
    assert intent.interruption_active is True
    assert intent.semantic_summary is not None


def test_character_projection_profile_defaults_follow_runtime_mode(tmp_path: Path) -> None:
    bodyless = build_settings(tmp_path / "bodyless", blink_runtime_mode=RobotMode.DESKTOP_BODYLESS)
    virtual = build_settings(tmp_path / "virtual", blink_runtime_mode=RobotMode.DESKTOP_VIRTUAL_BODY)
    serial = build_settings(tmp_path / "serial", blink_runtime_mode=RobotMode.DESKTOP_SERIAL_BODY)

    assert resolve_character_projection_profile(bodyless) == CharacterProjectionProfile.NO_BODY
    assert resolve_character_projection_profile(virtual) == CharacterProjectionProfile.AVATAR_ONLY
    assert resolve_character_projection_profile(serial) == CharacterProjectionProfile.AVATAR_AND_ROBOT_HEAD


def test_virtual_runtime_applies_character_projection_as_avatar_preview(tmp_path: Path) -> None:
    settings = build_settings(tmp_path, blink_runtime_mode=RobotMode.DESKTOP_VIRTUAL_BODY)
    gateway = DesktopRuntimeGateway(settings=settings)
    intent = build_character_semantic_intent(
        presence_status=CompanionPresenceStatus(state=CompanionPresenceState.ACKNOWLEDGING),
        voice_status=CompanionVoiceLoopStatus(state=CompanionVoiceLoopState.IDLE),
        initiative_status=InitiativeStatus(),
        relationship_status=RelationshipContinuityStatus(known_user=True),
        fallback_state=FallbackState(),
        body_state=gateway.get_telemetry().body_state,
    )

    state = gateway.apply_character_projection(intent=intent, profile=CharacterProjectionProfile.AVATAR_ONLY)

    assert state.character_projection is not None
    assert state.character_projection.profile == CharacterProjectionProfile.AVATAR_ONLY
    assert state.character_projection.robot_head_applied is False
    assert state.character_projection.outcome == "projection_preview_only"
    assert state.active_expression == "friendly"
    assert state.gaze_target == "look_at_user"
