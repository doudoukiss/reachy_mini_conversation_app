from __future__ import annotations


OPEN_TICK = "2026-03-30T16:05:00Z"


def test_shift_tick_moves_booting_to_ready_and_snapshot_exposes_state(brain_client):
    response = brain_client.post(
        "/api/operator/shift/tick",
        json={"session_id": "shift-opening", "timestamp": OPEN_TICK, "source": "test_shift_supervisor"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["interaction_type"] == "shift_tick"
    assert body["shift_supervisor"]["state"] == "ready_idle"
    assert "ready_for_shift_work" in body["shift_supervisor"]["reason_codes"]
    assert "opening_prompt_issued" in body["shift_supervisor"]["reason_codes"]
    assert "community center shift" in (body["response"]["reply_text"] or "").lower()

    shift_state = brain_client.get("/api/shift-state")
    assert shift_state.status_code == 200
    assert shift_state.json()["state"] == "ready_idle"

    snapshot = brain_client.get("/api/operator/snapshot", params={"session_id": "shift-opening"})
    assert snapshot.status_code == 200
    assert snapshot.json()["shift_supervisor"]["state"] == "ready_idle"
    assert "shift_transitions" in snapshot.json()


def test_repeated_presence_does_not_trigger_tick_time_outreach_spam(brain_client):
    first = brain_client.post(
        "/api/events",
        json={
            "event_type": "person_visible",
            "session_id": "shift-presence",
            "timestamp": OPEN_TICK,
            "payload": {"confidence": 0.92},
        },
    )
    assert first.status_code == 200
    assert first.json()["reply_text"]

    keep_present = brain_client.post(
        "/api/events",
        json={
            "event_type": "people_count_changed",
            "session_id": "shift-presence",
            "timestamp": "2026-03-30T16:05:49Z",
            "payload": {"people_count": 1, "confidence": 0.9},
        },
    )
    assert keep_present.status_code == 200
    assert keep_present.json()["reply_text"] is None

    tick = brain_client.post(
        "/api/operator/shift/tick",
        json={"session_id": "shift-presence", "timestamp": "2026-03-30T16:05:50Z"},
    )
    assert tick.status_code == 200
    body = tick.json()
    assert body["response"]["reply_text"] is None
    assert body["shift_supervisor"]["state"] == "attracting_attention"
    assert body["shift_supervisor"]["timers"][1]["timer_name"] == "outreach_cooldown"
    assert body["shift_supervisor"]["timers"][1]["active"] is True


def test_follow_up_window_expires_back_to_ready_idle(brain_client):
    reply = brain_client.post(
        "/api/events",
        json={
            "event_type": "speech_transcript",
            "session_id": "shift-followup",
            "timestamp": OPEN_TICK,
            "payload": {"text": "Where is the front desk?"},
        },
    )
    assert reply.status_code == 200
    assert "Front Desk" in reply.json()["reply_text"]

    during_window = brain_client.post(
        "/api/operator/shift/tick",
        json={"session_id": "shift-followup", "timestamp": "2026-03-30T16:05:20Z"},
    )
    assert during_window.status_code == 200
    assert during_window.json()["shift_supervisor"]["state"] == "waiting_for_follow_up"

    after_window = brain_client.post(
        "/api/operator/shift/tick",
        json={"session_id": "shift-followup", "timestamp": "2026-03-30T16:05:50Z"},
    )
    assert after_window.status_code == 200
    assert after_window.json()["shift_supervisor"]["state"] == "ready_idle"
    assert after_window.json()["shift_supervisor"]["reason_codes"] == ["ready_for_shift_work"]


def test_degraded_transport_enters_degraded_shift_state(brain_client):
    response = brain_client.post(
        "/api/events",
        json={
            "event_type": "heartbeat",
            "session_id": "shift-degraded",
            "timestamp": OPEN_TICK,
            "payload": {"network_ok": False, "transport_ok": False},
        },
    )
    assert response.status_code == 200

    shift_state = brain_client.get("/api/shift-state")
    assert shift_state.status_code == 200
    body = shift_state.json()
    assert body["state"] == "degraded"
    assert body["reason_codes"] == ["edge_transport_degraded"]


def test_closing_time_tick_sets_closing_state(brain_client):
    response = brain_client.post(
        "/api/operator/shift/tick",
        json={"session_id": "shift-closing", "timestamp": "2026-03-31T02:45:00Z"},
    )
    assert response.status_code == 200
    body = response.json()
    assert "closing soon" in (body["response"]["reply_text"] or "").lower()
    assert body["shift_supervisor"]["state"] == "closing"
    assert "closing_window_active" in body["shift_supervisor"]["reason_codes"]
    assert "closing_prompt_issued" in body["shift_supervisor"]["reason_codes"]


def test_operator_can_force_and_clear_shift_override(brain_client):
    forced = brain_client.post(
        "/api/operator/shift/override",
        params={"session_id": "shift-override"},
        json={"state": "safe_idle", "reason": "operator_demo_hold"},
    )
    assert forced.status_code == 200
    body = forced.json()
    assert body["state"] == "safe_idle"
    assert body["override_active"] is True
    assert body["override_state"] == "safe_idle"

    tick = brain_client.post(
        "/api/operator/shift/tick",
        json={"session_id": "shift-override", "timestamp": OPEN_TICK},
    )
    assert tick.status_code == 200
    assert tick.json()["shift_supervisor"]["state"] == "safe_idle"
    assert "operator_override_active" in tick.json()["shift_supervisor"]["reason_codes"]

    cleared = brain_client.post(
        "/api/operator/shift/override",
        params={"session_id": "shift-override"},
        json={"clear": True, "reason": "resume_service"},
    )
    assert cleared.status_code == 200
    assert cleared.json()["override_active"] is False
    assert cleared.json()["state"] == "ready_idle"
