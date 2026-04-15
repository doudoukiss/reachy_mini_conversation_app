from __future__ import annotations

from datetime import timedelta

from embodied_stack.desktop.always_on import CompanionTriggerEngine, SceneObservationEvent, SceneObserverEngine
from embodied_stack.shared.models import CompanionTriggerDecision, ShiftSupervisorSnapshot, utc_now


def _data_url(payload: bytes) -> str:
    import base64

    return "data:image/jpeg;base64," + base64.b64encode(payload).decode("ascii")


def test_scene_observer_recommends_refresh_only_on_meaningful_change():
    engine = SceneObserverEngine(change_threshold=0.1)

    first = engine.observe(image_data_url=_data_url(b"frame-a"))
    second = engine.observe(image_data_url=_data_url(b"frame-a"))
    third = engine.observe(image_data_url=_data_url(b"frame-b-significantly-different"))

    assert first.motion_changed is True
    assert first.semantic_refresh_recommended is True
    assert first.refresh_reason == "scene_changed"
    assert first.motion_state.value == "changed"
    assert first.presence_state.value == "unknown"
    assert first.engagement_shift_hint.value == "unknown"
    assert first.environment_state.value in {"unknown", "busy", "quiet"}
    assert second.motion_changed is False
    assert second.semantic_refresh_recommended is False
    assert third.motion_changed is True
    assert third.semantic_refresh_recommended is True
    assert third.refresh_reason == "scene_changed"


def test_trigger_engine_suppresses_under_outreach_cooldown():
    now = utc_now()
    engine = CompanionTriggerEngine(
        attract_prompt_delay_seconds=2.0,
        semantic_refresh_min_interval_seconds=10.0,
    )
    shift_snapshot = ShiftSupervisorSnapshot(
        person_present=True,
        presence_started_at=now - timedelta(seconds=10.0),
        outreach_cooldown_until=now + timedelta(seconds=30.0),
    )
    observer_event = SceneObservationEvent(
        observed_at=now,
        backend="frame_diff_fallback",
        change_score=0.8,
        motion_changed=True,
        person_present=True,
        person_transition="entered",
        attention_state="toward_device",
        semantic_refresh_recommended=False,
    )

    evaluation = engine.evaluate(
        observer_event=observer_event,
        shift_snapshot=shift_snapshot,
        fallback_active=False,
        semantic_provider_available=True,
        fresh_semantic_scene_available=True,
        last_semantic_refresh_at=now - timedelta(seconds=5.0),
        now=now,
    )

    assert evaluation.decision == CompanionTriggerDecision.OBSERVE_ONLY
    assert evaluation.proactive_eligible is False
    assert evaluation.suppressed_reason == "outreach_cooldown"


def test_trigger_engine_requests_refresh_when_scene_context_is_stale():
    now = utc_now()
    engine = CompanionTriggerEngine(
        attract_prompt_delay_seconds=2.0,
        semantic_refresh_min_interval_seconds=10.0,
    )
    shift_snapshot = ShiftSupervisorSnapshot(
        person_present=True,
        presence_started_at=now - timedelta(seconds=10.0),
    )
    observer_event = SceneObservationEvent(
        observed_at=now,
        backend="frame_diff_fallback",
        change_score=0.8,
        motion_changed=True,
        person_present=True,
        person_transition="entered",
        attention_state="toward_device",
        semantic_refresh_recommended=True,
    )

    evaluation = engine.evaluate(
        observer_event=observer_event,
        shift_snapshot=shift_snapshot,
        fallback_active=False,
        semantic_provider_available=True,
        fresh_semantic_scene_available=False,
        last_semantic_refresh_at=now - timedelta(seconds=60.0),
        now=now,
    )

    assert evaluation.decision == CompanionTriggerDecision.REFRESH_SCENE
    assert evaluation.reason == "person_entered_scene_refresh"
