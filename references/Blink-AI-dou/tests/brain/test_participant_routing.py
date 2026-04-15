from __future__ import annotations

from datetime import datetime, timedelta, timezone


def _timestamp(base: datetime, offset_seconds: int) -> str:
    return (base + timedelta(seconds=offset_seconds)).isoformat()


def _event(event_type: str, *, base: datetime, offset_seconds: int, payload: dict | None = None, session_id: str | None = None):
    event = {
        "event_type": event_type,
        "timestamp": _timestamp(base, offset_seconds),
        "payload": payload or {},
    }
    if session_id is not None:
        event["session_id"] = session_id
    return event


def test_returning_participant_resumes_recent_session(brain_client):
    base = datetime.now(timezone.utc).replace(microsecond=0)

    brain_client.post(
        "/api/events",
        json=_event(
            "person_visible",
            base=base,
            offset_seconds=0,
            payload={"participant_id": "likely_participant_1", "confidence": 0.95},
        ),
    )
    first = brain_client.post(
        "/api/events",
        json=_event(
            "speech_transcript",
            base=base,
            offset_seconds=5,
            payload={"participant_id": "likely_participant_1", "text": "Where is the workshop room?"},
        ),
    )
    assert first.status_code == 200
    first_session_id = first.json()["session_id"]

    brain_client.post(
        "/api/events",
        json=_event(
            "person_left",
            base=base,
            offset_seconds=20,
            payload={"participant_id": "likely_participant_1"},
        ),
    )
    brain_client.post(
        "/api/events",
        json=_event(
            "person_visible",
            base=base,
            offset_seconds=45,
            payload={"participant_id": "likely_participant_1", "confidence": 0.92},
        ),
    )
    follow_up = brain_client.post(
        "/api/events",
        json=_event(
            "speech_transcript",
            base=base,
            offset_seconds=50,
            payload={"participant_id": "likely_participant_1", "text": "Can you repeat how to get there?"},
        ),
    )
    assert follow_up.status_code == 200
    assert follow_up.json()["session_id"] == first_session_id
    assert "Workshop Room" in follow_up.json()["reply_text"]

    session = brain_client.get(f"/api/sessions/{first_session_id}")
    assert session.status_code == 200
    assert session.json()["participant_id"] == "likely_participant_1"


def test_second_speaker_interrupt_gets_wait_prompt_and_queue_entry(brain_client):
    base = datetime.now(timezone.utc).replace(microsecond=0)

    brain_client.post(
        "/api/events",
        json=_event(
            "person_visible",
            base=base,
            offset_seconds=0,
            payload={"participant_id": "likely_participant_1", "confidence": 0.94},
        ),
    )
    first = brain_client.post(
        "/api/events",
        json=_event(
            "speech_transcript",
            base=base,
            offset_seconds=1,
            payload={"participant_id": "likely_participant_1", "text": "Where is the front desk?"},
        ),
    )
    first_session_id = first.json()["session_id"]

    second = brain_client.post(
        "/api/events",
        json=_event(
            "speech_transcript",
            base=base,
            offset_seconds=2,
            payload={"participant_id": "likely_participant_2", "text": "Can you help me too?"},
        ),
    )
    assert second.status_code == 200
    body = second.json()
    assert "right with you" in (body["reply_text"] or "").lower()
    assert body["commands"][0]["command_type"] == "stop"

    snapshot = brain_client.get("/api/operator/snapshot")
    assert snapshot.status_code == 200
    router = snapshot.json()["participant_router"]
    assert router["active_participant_id"] == "likely_participant_1"
    assert router["queued_participants"][0]["participant_id"] == "likely_participant_2"

    first_session = brain_client.get(f"/api/sessions/{first_session_id}")
    queued_session = brain_client.get(f"/api/sessions/{body['session_id']}")
    assert first_session.json()["routing_status"] == "active"
    assert queued_session.json()["routing_status"] == "paused"


def test_secondary_visitor_repeat_wait_handling_stays_queued_without_spam(brain_client):
    base = datetime.now(timezone.utc).replace(microsecond=0)

    brain_client.post(
        "/api/events",
        json=_event(
            "person_visible",
            base=base,
            offset_seconds=0,
            payload={"participant_id": "likely_participant_1", "confidence": 0.94},
        ),
    )
    brain_client.post(
        "/api/events",
        json=_event(
            "speech_transcript",
            base=base,
            offset_seconds=1,
            payload={"participant_id": "likely_participant_1", "text": "What events are happening this week?"},
        ),
    )

    first_wait = brain_client.post(
        "/api/events",
        json=_event(
            "speech_transcript",
            base=base,
            offset_seconds=2,
            payload={"participant_id": "likely_participant_2", "text": "Can you help me next?"},
        ),
    )
    second_wait = brain_client.post(
        "/api/events",
        json=_event(
            "speech_transcript",
            base=base,
            offset_seconds=5,
            payload={"participant_id": "likely_participant_2", "text": "Hello?"},
        ),
    )

    assert first_wait.status_code == 200
    assert "right with you" in (first_wait.json()["reply_text"] or "").lower()
    assert second_wait.status_code == 200
    assert second_wait.json()["reply_text"] is None

    snapshot = brain_client.get("/api/operator/snapshot")
    router = snapshot.json()["participant_router"]
    assert len(router["queued_participants"]) == 1
    assert router["queued_participants"][0]["participant_id"] == "likely_participant_2"
    assert router["queued_participants"][0]["queue_position"] == 1


def test_accessibility_request_preempts_and_gains_priority(brain_client):
    base = datetime.now(timezone.utc).replace(microsecond=0)

    first = brain_client.post(
        "/api/events",
        json=_event(
            "speech_transcript",
            base=base,
            offset_seconds=0,
            payload={"participant_id": "likely_participant_1", "text": "Where is the front desk?"},
        ),
    )
    first_session_id = first.json()["session_id"]

    second = brain_client.post(
        "/api/events",
        json=_event(
            "speech_transcript",
            base=base,
            offset_seconds=2,
            payload={
                "participant_id": "likely_participant_2",
                "text": "I need accessibility help finding an accessible route.",
            },
        ),
    )
    assert second.status_code == 200
    assert "human operator" in second.json()["reply_text"].lower()

    snapshot = brain_client.get("/api/operator/snapshot")
    router = snapshot.json()["participant_router"]
    assert router["active_participant_id"] == "likely_participant_2"

    first_session = brain_client.get(f"/api/sessions/{first_session_id}")
    second_session = brain_client.get(f"/api/sessions/{second.json()['session_id']}")
    assert first_session.json()["routing_status"] == "paused"
    assert second_session.json()["routing_status"] == "handed_off"
    assert second_session.json()["status"] == "escalation_pending"


def test_expired_participant_session_is_closed_and_new_session_is_created(brain_client):
    base = datetime.now(timezone.utc).replace(microsecond=0)

    first = brain_client.post(
        "/api/events",
        json=_event(
            "speech_transcript",
            base=base,
            offset_seconds=0,
            payload={"participant_id": "likely_participant_1", "text": "Where is the workshop room?"},
        ),
    )
    assert first.status_code == 200
    original_session_id = first.json()["session_id"]

    brain_client.post(
        "/api/events",
        json=_event(
            "person_left",
            base=base,
            offset_seconds=5,
            payload={"participant_id": "likely_participant_1"},
        ),
    )
    brain_client.post(
        "/api/events",
        json=_event(
            "heartbeat",
            base=base,
            offset_seconds=400,
            payload={"network_ok": True},
        ),
    )

    expired_session = brain_client.get(f"/api/sessions/{original_session_id}")
    assert expired_session.status_code == 200
    assert expired_session.json()["routing_status"] == "complete"
    assert expired_session.json()["status"] == "closed"

    returning = brain_client.post(
        "/api/events",
        json=_event(
            "speech_transcript",
            base=base,
            offset_seconds=401,
            payload={"participant_id": "likely_participant_1", "text": "Can you repeat how to get there?"},
        ),
    )
    assert returning.status_code == 200
    assert returning.json()["session_id"] != original_session_id
