from __future__ import annotations


def test_greet_on_approach_updates_world_model(brain_client):
    response = brain_client.post(
        "/api/events",
        json={"event_type": "person_visible", "session_id": "social-greet", "payload": {"confidence": 0.92}},
    )
    assert response.status_code == 200
    body = response.json()
    reply = body["reply_text"].lower()
    assert "welcome" in reply or "hi." in reply or "hello" in reply

    trace = brain_client.get(f"/api/traces/{body['trace_id']}")
    assert trace.status_code == 200
    trace_body = trace.json()
    assert trace_body["reasoning"]["executive_decisions"][0]["decision_type"] == "auto_greet"
    assert trace_body["reasoning"]["executive_decisions"][0]["reason_codes"] == ["auto_greet_on_approach"]

    world_model = brain_client.get("/api/world-model")
    assert world_model.status_code == 200
    world_body = world_model.json()
    assert len(world_body["active_participants_in_view"]) == 1
    assert world_body["engagement_state"] == "noticing"
    assert world_body["attention_target"]["target_type"] == "participant"


def test_auto_greet_is_suppressed_if_recently_greeted(brain_client):
    first = brain_client.post(
        "/api/events",
        json={"event_type": "person_visible", "session_id": "social-repeat", "payload": {"confidence": 0.9}},
    )
    assert first.status_code == 200

    second = brain_client.post(
        "/api/events",
        json={"event_type": "person_visible", "session_id": "social-repeat", "payload": {"confidence": 0.9}},
    )
    assert second.status_code == 200
    body = second.json()
    assert body["reply_text"] is None
    assert body["commands"] == []

    trace = brain_client.get(f"/api/traces/{body['trace_id']}")
    assert trace.status_code == 200
    decision = trace.json()["reasoning"]["executive_decisions"][0]
    assert decision["decision_type"] == "auto_greet_suppressed"
    assert "auto_greet_suppressed_recently" in decision["reason_codes"]


def test_user_speaking_over_reply_triggers_visible_interruption(brain_client):
    greeting = brain_client.post(
        "/api/events",
        json={"event_type": "person_visible", "session_id": "social-interrupt", "payload": {"confidence": 0.9}},
    )
    assert greeting.status_code == 200

    response = brain_client.post(
        "/api/events",
        json={
            "event_type": "speech_transcript",
            "session_id": "social-interrupt",
            "payload": {"text": "Where is the front desk?"},
        },
    )
    assert response.status_code == 200
    body = response.json()
    command_types = [item["command_type"] for item in body["commands"]]
    assert command_types[0] == "stop"
    assert body["commands"][0]["payload"]["reason"] == "user_interrupt"
    assert "Front Desk" in body["reply_text"]

    trace = brain_client.get(f"/api/traces/{body['trace_id']}")
    assert trace.status_code == 200
    trace_body = trace.json()
    assert trace_body["outcome"] == "ok"
    assert trace_body["reasoning"]["executive_decisions"][0]["decision_type"] == "stop_for_interruption"
    assert trace_body["reasoning"]["executive_decisions"][0]["reason_codes"] == ["user_interrupt_detected"]


def test_disengagement_shortens_reply(brain_client):
    event = brain_client.post(
        "/api/events",
        json={
            "event_type": "engagement_estimate_changed",
            "session_id": "social-disengaging",
            "payload": {"engagement_estimate": "disengaging", "confidence": 0.81},
        },
    )
    assert event.status_code == 200

    response = brain_client.post(
        "/api/events",
        json={
            "event_type": "speech_transcript",
            "session_id": "social-disengaging",
            "payload": {"text": "What events are happening this week?"},
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert len(body["reply_text"]) < 120

    trace = brain_client.get(f"/api/traces/{body['trace_id']}")
    assert trace.status_code == 200
    reasons = trace.json()["reasoning"]["executive_decisions"][0]["reason_codes"]
    assert "engagement_low_short_reply" in reasons


def test_accessibility_request_escalates_to_human(brain_client):
    response = brain_client.post(
        "/api/events",
        json={
            "event_type": "speech_transcript",
            "session_id": "social-escalation",
            "payload": {"text": "I need accessibility help finding an accessible route."},
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert "human operator" in body["reply_text"].lower()

    trace = brain_client.get(f"/api/traces/{body['trace_id']}")
    assert trace.status_code == 200
    trace_body = trace.json()
    assert trace_body["reasoning"]["intent"] == "operator_handoff"
    assert trace_body["reasoning"]["executive_decisions"][0]["decision_type"] == "escalate_to_human"
    assert trace_body["reasoning"]["executive_decisions"][0]["reason_codes"] == [
        "escalation_due_to_accessibility_request"
    ]
    assert trace_body["reasoning"]["incident_ticket"]["reason_category"] == "accessibility"

    session = brain_client.get("/api/sessions/social-escalation")
    assert session.status_code == 200
    assert session.json()["status"] == "escalation_pending"
    assert session.json()["incident_status"] == "pending"


def test_missing_perception_falls_back_honestly(brain_client):
    response = brain_client.post(
        "/api/events",
        json={
            "event_type": "speech_transcript",
            "session_id": "social-vision",
            "payload": {"text": "What do you see right now?"},
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert "visual situational awareness is limited" in body["reply_text"].lower()

    trace = brain_client.get(f"/api/traces/{body['trace_id']}")
    assert trace.status_code == 200
    trace_body = trace.json()
    assert trace_body["reasoning"]["intent"] == "perception_query"
    assert trace_body["reasoning"]["executive_decisions"][0]["reason_codes"] == [
        "limited_visual_awareness_response"
    ]


def test_operator_snapshot_shows_world_model_and_executive_decisions(brain_client):
    response = brain_client.post(
        "/api/events",
        json={"event_type": "person_visible", "session_id": "social-snapshot", "payload": {"confidence": 0.92}},
    )
    assert response.status_code == 200

    snapshot = brain_client.get("/api/operator/snapshot?session_id=social-snapshot")
    assert snapshot.status_code == 200
    body = snapshot.json()
    assert body["world_model"]["engagement_state"] == "noticing"
    assert body["world_model"]["attention_target"]["target_label"] == "active_visitor"
    assert body["executive_decisions"]["items"][0]["decision_type"] == "auto_greet"
