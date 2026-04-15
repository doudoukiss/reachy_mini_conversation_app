from __future__ import annotations

from embodied_stack.brain.memory import MemoryStore
from embodied_stack.brain.world_model import WorldModelRuntime
from embodied_stack.shared.contracts import (
    CommandBatch,
    EnvironmentState,
    FactFreshness,
    PerceptionEventType,
    PerceptionTier,
    RobotEvent,
    SessionRecord,
    SocialRuntimeMode,
    utc_now,
)


def test_world_model_applies_watcher_context_to_social_runtime():
    runtime = WorldModelRuntime(MemoryStore())
    session = SessionRecord(session_id="world-model-watcher")
    now = utc_now()

    model = runtime.apply_event(
        RobotEvent(
            event_type=PerceptionEventType.PERSON_VISIBLE.value,
            session_id=session.session_id,
            timestamp=now,
            payload={
                "people_count": 1,
                "tier": PerceptionTier.WATCHER.value,
                "environment_state": EnvironmentState.QUIET.value,
                "device_awareness_constraints": ["person_attention_detection_unavailable"],
                "uncertainty_markers": ["watcher_only_scene_facts"],
            },
        ),
        session=session,
    )

    assert model.social_runtime_mode == SocialRuntimeMode.GREETING
    assert model.environment_state == EnvironmentState.QUIET
    assert model.scene_freshness == FactFreshness.FRESH
    assert "watcher_only_scene_facts" in model.uncertainty_markers
    assert model.device_awareness_constraints == ["person_attention_detection_unavailable"]
    assert model.attention_target is not None
    assert model.attention_target.rationale == "person_visible_event"


def test_world_model_tracks_semantic_refresh_reason_and_operator_handoff_mode():
    runtime = WorldModelRuntime(MemoryStore())
    session = SessionRecord(session_id="world-model-semantic")
    now = utc_now()

    model = runtime.apply_event(
        RobotEvent(
            event_type=PerceptionEventType.SCENE_SUMMARY_UPDATED.value,
            session_id=session.session_id,
            timestamp=now,
            payload={
                "scene_summary": "A front desk and check-in sign are visible.",
                "tier": PerceptionTier.SEMANTIC.value,
                "trigger_reason": "visual_query",
                "limited_awareness": False,
                "environment_state": EnvironmentState.BUSY.value,
            },
        ),
        session=session,
    )
    assert model.last_semantic_refresh_reason == "visual_query"
    assert model.last_semantic_refresh_at == now
    assert model.scene_freshness == FactFreshness.FRESH

    updated = runtime.apply_response(
        session=session,
        response=CommandBatch(session_id=session.session_id, reply_text="A human operator is joining shortly."),
        intent="operator_handoff",
        decisions=[],
    )

    assert updated.social_runtime_mode == SocialRuntimeMode.OPERATOR_HANDOFF
