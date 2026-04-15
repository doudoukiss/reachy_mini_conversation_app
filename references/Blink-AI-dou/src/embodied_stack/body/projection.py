from __future__ import annotations

from datetime import timedelta

from embodied_stack.config import Settings
from embodied_stack.shared.contracts import (
    BodyPose,
    BodyState,
    CharacterPresenceShellState,
    CharacterProjectionProfile,
    CharacterSemanticIntent,
    CompanionPresenceState,
    CompanionPresenceStatus,
    CompanionVoiceLoopState,
    CompanionVoiceLoopStatus,
    FallbackState,
    InitiativeDecision,
    InitiativeStage,
    InitiativeStatus,
    RelationshipContinuityStatus,
    RobotMode,
    utc_now,
)

from .grounded_catalog import (
    build_grounded_gaze_preview_pose,
    build_grounded_state_pose,
    grounded_preview_neutral_pose,
)
from .library import apply_pose_overrides

_RECENT_INTERRUPTION_WINDOW = timedelta(seconds=3)

_PROFILE_ALIASES = {
    "auto": "auto",
    "none": CharacterProjectionProfile.NO_BODY.value,
    "no_body": CharacterProjectionProfile.NO_BODY.value,
    "bodyless": CharacterProjectionProfile.NO_BODY.value,
    "avatar": CharacterProjectionProfile.AVATAR_ONLY.value,
    "avatar_only": CharacterProjectionProfile.AVATAR_ONLY.value,
    "head": CharacterProjectionProfile.ROBOT_HEAD_ONLY.value,
    "robot_head": CharacterProjectionProfile.ROBOT_HEAD_ONLY.value,
    "robot_head_only": CharacterProjectionProfile.ROBOT_HEAD_ONLY.value,
    "both": CharacterProjectionProfile.AVATAR_AND_ROBOT_HEAD.value,
    "avatar_and_robot_head": CharacterProjectionProfile.AVATAR_AND_ROBOT_HEAD.value,
}


def resolve_character_projection_profile(settings: Settings) -> CharacterProjectionProfile:
    configured = _PROFILE_ALIASES.get(
        settings.blink_character_projection_profile.strip().lower(),
        settings.blink_character_projection_profile.strip().lower(),
    )
    if configured != "auto":
        try:
            return CharacterProjectionProfile(configured)
        except ValueError:
            pass
    if settings.blink_runtime_mode == RobotMode.DESKTOP_VIRTUAL_BODY:
        return CharacterProjectionProfile.AVATAR_ONLY
    if settings.blink_runtime_mode == RobotMode.DESKTOP_SERIAL_BODY:
        return CharacterProjectionProfile.AVATAR_AND_ROBOT_HEAD
    if settings.blink_runtime_mode in {RobotMode.TETHERED_FUTURE, RobotMode.TETHERED_DEMO, RobotMode.HARDWARE}:
        return CharacterProjectionProfile.ROBOT_HEAD_ONLY
    return CharacterProjectionProfile.NO_BODY


def projection_profile_supports_avatar(profile: CharacterProjectionProfile) -> bool:
    return profile in {
        CharacterProjectionProfile.AVATAR_ONLY,
        CharacterProjectionProfile.AVATAR_AND_ROBOT_HEAD,
    }


def projection_profile_supports_robot_head(profile: CharacterProjectionProfile) -> bool:
    return profile in {
        CharacterProjectionProfile.ROBOT_HEAD_ONLY,
        CharacterProjectionProfile.AVATAR_AND_ROBOT_HEAD,
    }


def build_character_semantic_intent(
    *,
    presence_status: CompanionPresenceStatus,
    voice_status: CompanionVoiceLoopStatus,
    initiative_status: InitiativeStatus,
    relationship_status: RelationshipContinuityStatus,
    fallback_state: FallbackState,
    body_state: BodyState | None = None,
) -> CharacterSemanticIntent:
    now = utc_now()
    surface_state = _resolve_surface_state(
        presence_status=presence_status,
        voice_status=voice_status,
        fallback_state=fallback_state,
        now=now,
    )
    warmth = _clamp(
        _warmth(
            surface_state=surface_state,
            presence_status=presence_status,
            relationship_status=relationship_status,
            fallback_state=fallback_state,
        )
    )
    curiosity = _clamp(
        _curiosity(
            surface_state=surface_state,
            initiative_status=initiative_status,
            relationship_status=relationship_status,
            fallback_state=fallback_state,
        )
    )
    expression_name, gaze_target, gesture_name, animation_name, motion_hint = _semantic_mapping(
        surface_state=surface_state,
        curiosity=curiosity,
        warmth=warmth,
        initiative_status=initiative_status,
    )
    neutral_pose = grounded_preview_neutral_pose()
    expression_pose = build_grounded_state_pose(
        expression_name,
        intensity=max(0.6, warmth),
        neutral_pose=neutral_pose,
    ) or neutral_pose.model_copy(deep=True)
    gaze_pose = build_grounded_gaze_preview_pose(
        gaze_target,
        intensity=1.0,
        neutral_pose=neutral_pose,
    ) or neutral_pose.model_copy(deep=True)
    pose_payload = expression_pose.model_dump()
    gaze_payload = gaze_pose.model_dump()
    for field_name in ("head_yaw", "head_pitch", "head_roll", "eye_yaw", "eye_pitch"):
        pose_payload[field_name] = gaze_payload[field_name]
    pose = BodyPose.model_validate(pose_payload)
    pose = _apply_surface_pose_overrides(
        surface_state=surface_state,
        pose=pose,
        gesture_name=gesture_name,
        warmth=warmth,
        curiosity=curiosity,
    )
    semantic_summary = _semantic_summary(
        expression_name=expression_name,
        gaze_target=gaze_target,
        gesture_name=gesture_name,
        animation_name=animation_name,
    )
    source_signals = _source_signals(
        presence_status=presence_status,
        voice_status=voice_status,
        initiative_status=initiative_status,
        relationship_status=relationship_status,
        fallback_state=fallback_state,
        body_state=body_state,
    )
    return CharacterSemanticIntent(
        surface_state=surface_state,
        expression_name=expression_name,
        gaze_target=gaze_target,
        gesture_name=gesture_name,
        animation_name=animation_name,
        motion_hint=motion_hint,
        warmth=warmth,
        curiosity=curiosity,
        listening_active=surface_state in {"listening", "acknowledging", "reengaging"} or voice_status.state in {
            CompanionVoiceLoopState.ARMED,
            CompanionVoiceLoopState.VAD_WAITING,
            CompanionVoiceLoopState.CAPTURING,
            CompanionVoiceLoopState.ENDPOINTING,
            CompanionVoiceLoopState.TRANSCRIBING,
        },
        speaking_active=surface_state == "speaking" or voice_status.state == CompanionVoiceLoopState.SPEAKING,
        interruption_active=surface_state == "interrupted",
        slow_path_active=presence_status.slow_path_active,
        safe_idle_requested=bool(fallback_state.safe_idle_active or (body_state.safe_idle_active if body_state is not None else False)),
        detail=_detail_text(
            surface_state=surface_state,
            presence_status=presence_status,
            voice_status=voice_status,
            relationship_status=relationship_status,
        ),
        semantic_summary=semantic_summary,
        source_signals=source_signals,
        pose=pose,
    )


def build_character_presence_shell(
    *,
    presence_status: CompanionPresenceStatus,
    voice_status: CompanionVoiceLoopStatus,
    initiative_status: InitiativeStatus,
    relationship_status: RelationshipContinuityStatus,
    fallback_state: FallbackState,
    body_state: BodyState | None = None,
) -> CharacterPresenceShellState:
    intent = build_character_semantic_intent(
        presence_status=presence_status,
        voice_status=voice_status,
        initiative_status=initiative_status,
        relationship_status=relationship_status,
        fallback_state=fallback_state,
        body_state=body_state,
    )
    return CharacterPresenceShellState(
        surface_state=intent.surface_state,
        headline=_headline(intent.surface_state),
        expression_name=intent.expression_name,
        gaze_target=intent.gaze_target,
        gesture_name=intent.gesture_name,
        animation_name=intent.animation_name,
        motion_hint=intent.motion_hint,
        warmth=intent.warmth,
        curiosity=intent.curiosity,
        listening_active=intent.listening_active,
        speaking_active=intent.speaking_active,
        interruption_active=intent.interruption_active,
        slow_path_active=intent.slow_path_active,
        message=presence_status.message,
        detail=intent.detail,
        semantic_summary=intent.semantic_summary,
        source_signals=list(intent.source_signals),
        pose=intent.pose,
    )


def _resolve_surface_state(
    *,
    presence_status: CompanionPresenceStatus,
    voice_status: CompanionVoiceLoopStatus,
    fallback_state: FallbackState,
    now,
) -> str:
    if presence_status.state == CompanionPresenceState.DEGRADED or fallback_state.active or fallback_state.safe_idle_active:
        return "degraded"
    if voice_status.state in {CompanionVoiceLoopState.BARGE_IN, CompanionVoiceLoopState.INTERRUPTED}:
        return "interrupted"
    if voice_status.last_interruption_at is not None and now - voice_status.last_interruption_at <= _RECENT_INTERRUPTION_WINDOW:
        return "interrupted"
    if presence_status.state == CompanionPresenceState.LISTENING or voice_status.state in {
        CompanionVoiceLoopState.ARMED,
        CompanionVoiceLoopState.VAD_WAITING,
        CompanionVoiceLoopState.CAPTURING,
        CompanionVoiceLoopState.ENDPOINTING,
        CompanionVoiceLoopState.TRANSCRIBING,
    }:
        return "listening"
    if presence_status.state == CompanionPresenceState.ACKNOWLEDGING:
        return "acknowledging"
    if presence_status.state == CompanionPresenceState.SPEAKING or voice_status.state == CompanionVoiceLoopState.SPEAKING:
        return "speaking"
    if presence_status.state == CompanionPresenceState.TOOL_WORKING:
        return "tool_working"
    if presence_status.state == CompanionPresenceState.THINKING_FAST or voice_status.state == CompanionVoiceLoopState.THINKING:
        return "thinking"
    if presence_status.state == CompanionPresenceState.REENGAGING:
        return "reengaging"
    return "idle"


def _warmth(
    *,
    surface_state: str,
    presence_status: CompanionPresenceStatus,
    relationship_status: RelationshipContinuityStatus,
    fallback_state: FallbackState,
) -> float:
    score = 0.54
    if relationship_status.known_user:
        score += 0.08
    if relationship_status.returning_user:
        score += 0.1
    if surface_state in {"listening", "acknowledging", "speaking", "reengaging"}:
        score += 0.08
    if presence_status.last_acknowledgement_text:
        score += 0.03
    if fallback_state.active:
        score -= 0.2
    return score


def _curiosity(
    *,
    surface_state: str,
    initiative_status: InitiativeStatus,
    relationship_status: RelationshipContinuityStatus,
    fallback_state: FallbackState,
) -> float:
    score = 0.18
    if surface_state in {"thinking", "tool_working"}:
        score += 0.26
    if initiative_status.current_stage in {InitiativeStage.CANDIDATE, InitiativeStage.INFER, InitiativeStage.SCORE}:
        score += 0.22
    if initiative_status.last_decision in {InitiativeDecision.SUGGEST, InitiativeDecision.ASK}:
        score += 0.1
    if relationship_status.open_follow_ups:
        score += 0.08
    if fallback_state.active:
        score -= 0.08
    return score


def _headline(surface_state: str) -> str:
    return {
        "idle": "Settled",
        "listening": "Listening",
        "acknowledging": "Acknowledging",
        "thinking": "Thinking Quickly",
        "speaking": "Speaking",
        "tool_working": "Working",
        "reengaging": "Reengaging",
        "interrupted": "Interrupted",
        "degraded": "Degraded",
    }.get(surface_state, "Settled")


def _semantic_mapping(
    *,
    surface_state: str,
    curiosity: float,
    warmth: float,
    initiative_status: InitiativeStatus,
) -> tuple[str, str, str | None, str | None, str]:
    expression_name = "friendly" if warmth >= 0.56 else "neutral"
    gaze_target = "look_forward"
    gesture_name = None
    animation_name = None
    motion_hint = "settled"

    if surface_state == "listening":
        return "listen_attentively", "look_at_user", None, None, "attentive"
    if surface_state == "acknowledging":
        return "friendly", "look_at_user", "acknowledge_light", None, "acknowledge"
    if surface_state == "thinking":
        gesture_name = "tilt_curious" if curiosity >= 0.4 else None
        return "thinking", "look_down_briefly", gesture_name, None, "ponder"
    if surface_state == "tool_working":
        return "thinking", "look_down_briefly", None, None, "ponder"
    if surface_state == "speaking":
        return "friendly", "look_at_user", None, None, "speak"
    if surface_state == "reengaging":
        return "friendly", "look_at_user", "blink_soft", None, "reengage"
    if surface_state == "interrupted":
        return "listen_attentively", "look_at_user", "blink_soft", None, "interrupt"
    if surface_state == "degraded":
        return "safe_idle", "look_forward", None, "recover_neutral", "degraded"
    return expression_name, gaze_target, None, None, motion_hint


def _apply_surface_pose_overrides(
    *,
    surface_state: str,
    pose,
    gesture_name: str | None,
    warmth: float,
    curiosity: float,
):
    updated = pose
    if surface_state == "acknowledging":
        updated = apply_pose_overrides(updated, head_pitch=max(-1.0, updated.head_pitch - 0.08))
    if surface_state == "speaking":
        updated = apply_pose_overrides(
            updated,
            head_pitch=min(1.0, updated.head_pitch + 0.03),
            brow_raise_left=min(1.0, updated.brow_raise_left + 0.05 * warmth),
            brow_raise_right=min(1.0, updated.brow_raise_right + 0.05 * warmth),
        )
    if gesture_name == "tilt_curious":
        updated = apply_pose_overrides(
            updated,
            head_roll=max(-1.0, min(1.0, updated.head_roll + 0.05 + (0.05 * curiosity))),
        )
    if gesture_name == "blink_soft":
        updated = apply_pose_overrides(
            updated,
            upper_lid_left_open=0.28,
            upper_lid_right_open=0.28,
            lower_lid_left_open=0.4,
            lower_lid_right_open=0.4,
        )
    return updated


def _detail_text(
    *,
    surface_state: str,
    presence_status: CompanionPresenceStatus,
    voice_status: CompanionVoiceLoopStatus,
    relationship_status: RelationshipContinuityStatus,
) -> str | None:
    if surface_state == "degraded":
        return presence_status.degraded_reason or voice_status.degraded_reason or "Companion fallback is active."
    if surface_state == "thinking":
        return "Fast loop is holding presence while the slow loop works."
    if surface_state == "tool_working":
        return "Slow-loop work is active without dropping presence."
    if surface_state == "reengaging":
        return "Blink-AI is reentering the thread gently."
    if surface_state == "acknowledging":
        return presence_status.last_acknowledgement_text or "Low-latency acknowledgement is active."
    if surface_state == "interrupted":
        return "User interruption was detected and the companion yielded."
    if surface_state == "listening":
        if relationship_status.known_user:
            return "Blink-AI is tracking the user’s turn and listening for the next beat."
        return "Blink-AI is listening for the next turn."
    if surface_state == "speaking":
        return "Blink-AI is currently delivering the reply."
    return "Blink-AI is settled and available."


def _semantic_summary(
    *,
    expression_name: str,
    gaze_target: str,
    gesture_name: str | None,
    animation_name: str | None,
) -> str:
    parts = [f"expression:{expression_name}", f"gaze:{gaze_target}"]
    if gesture_name:
        parts.append(f"gesture:{gesture_name}")
    if animation_name:
        parts.append(f"animation:{animation_name}")
    return ", ".join(parts)


def _source_signals(
    *,
    presence_status: CompanionPresenceStatus,
    voice_status: CompanionVoiceLoopStatus,
    initiative_status: InitiativeStatus,
    relationship_status: RelationshipContinuityStatus,
    fallback_state: FallbackState,
    body_state: BodyState | None,
) -> list[str]:
    signals = [f"presence:{presence_status.state.value}", f"voice:{voice_status.state.value}"]
    if initiative_status.current_stage is not None:
        signals.append(f"initiative:{initiative_status.current_stage.value}")
    if relationship_status.known_user:
        signals.append("relationship:known_user")
    if relationship_status.returning_user:
        signals.append("relationship:returning_user")
    if relationship_status.open_follow_ups:
        signals.append("relationship:open_follow_ups")
    if fallback_state.active:
        signals.append("fallback:active")
    if fallback_state.safe_idle_active:
        signals.append("fallback:safe_idle")
    if body_state is not None and body_state.driver_mode is not None:
        signals.append(f"body_driver:{body_state.driver_mode.value}")
    return signals


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, round(float(value), 3)))


__all__ = [
    "build_character_presence_shell",
    "build_character_semantic_intent",
    "projection_profile_supports_avatar",
    "projection_profile_supports_robot_head",
    "resolve_character_projection_profile",
]
