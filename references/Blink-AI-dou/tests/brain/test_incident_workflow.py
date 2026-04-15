from __future__ import annotations

from fastapi.testclient import TestClient

from embodied_stack.brain.app import create_app as create_brain_app
from embodied_stack.brain.orchestrator import BrainOrchestrator
from embodied_stack.config import Settings
from embodied_stack.demo.coordinator import DemoCoordinator
from embodied_stack.desktop.runtime import build_inprocess_embodiment_gateway


def test_automatic_escalation_creates_incident_ticket(brain_client):
    response = brain_client.post(
        "/api/events",
        json={
            "event_type": "speech_transcript",
            "session_id": "incident-auto",
            "payload": {"text": "I need accessibility help finding an accessible route."},
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert "human operator handoff ticket" in body["reply_text"].lower()

    incidents = brain_client.get("/api/operator/incidents", params={"scope": "open"})
    assert incidents.status_code == 200
    ticket = incidents.json()["items"][0]
    assert ticket["session_id"] == "incident-auto"
    assert ticket["reason_category"] == "accessibility"
    assert ticket["urgency"] == "high"
    assert ticket["suggested_staff_contact"]["contact_key"] == "accessibility"
    assert ticket["current_status"] == "pending"

    trace = brain_client.get(f"/api/traces/{body['trace_id']}")
    assert trace.status_code == 200
    trace_body = trace.json()
    assert trace_body["reasoning"]["incident_ticket"]["ticket_id"] == ticket["ticket_id"]
    assert trace_body["reasoning"]["incident_timeline"][0]["event_type"] == "created"

    snapshot = brain_client.get("/api/operator/snapshot", params={"session_id": "incident-auto"})
    assert snapshot.status_code == 200
    snapshot_body = snapshot.json()
    assert snapshot_body["selected_incident"]["ticket_id"] == ticket["ticket_id"]
    assert snapshot_body["open_incidents"]["items"][0]["ticket_id"] == ticket["ticket_id"]


def test_operator_acknowledgment_flow_updates_follow_up_reply(brain_client):
    create = brain_client.post(
        "/api/events",
        json={
            "event_type": "speech_transcript",
            "session_id": "incident-ack",
            "payload": {"text": "I need accessibility help at the quiet room."},
        },
    )
    ticket_id = brain_client.get("/api/operator/incidents", params={"scope": "open"}).json()["items"][0]["ticket_id"]

    ack = brain_client.post(
        f"/api/operator/incidents/{ticket_id}/acknowledge",
        json={"operator_name": "Alex Operator", "note": "Acknowledged and reviewing the request now."},
    )
    assert ack.status_code == 200
    assert ack.json()["current_status"] == "acknowledged"

    follow_up = brain_client.post(
        "/api/events",
        json={
            "event_type": "speech_transcript",
            "session_id": "incident-ack",
            "payload": {"text": "Is someone coming to help me?"},
        },
    )
    assert follow_up.status_code == 200
    assert "acknowledged" in follow_up.json()["reply_text"].lower()

    session = brain_client.get("/api/sessions/incident-ack")
    assert session.status_code == 200
    assert session.json()["status"] == "escalation_pending"
    assert session.json()["incident_status"] == "acknowledged"
    assert session.json()["active_incident_ticket_id"] == ticket_id


def test_missing_staff_contact_fallback_stays_honest(tmp_path):
    empty_venue_dir = tmp_path / "empty_venue"
    empty_venue_dir.mkdir()
    settings = Settings(
        brain_store_path=str(tmp_path / "brain_store.json"),
        demo_report_dir=str(tmp_path / "demo_runs"),
        episode_export_dir=str(tmp_path / "episodes"),
        brain_dialogue_backend="rule_based",
        brain_voice_backend="stub",
        shift_background_tick_enabled=False,
        operator_auth_token="test-operator-token",
        operator_auth_runtime_file=str(tmp_path / "operator_auth.json"),
        venue_content_dir=str(empty_venue_dir),
    )
    orchestrator = BrainOrchestrator(settings=settings, store_path=settings.brain_store_path)
    demo_coordinator = DemoCoordinator(
        orchestrator=orchestrator,
        edge_gateway=build_inprocess_embodiment_gateway(settings),
        report_dir=settings.demo_report_dir,
    )
    app = create_brain_app(settings=settings, orchestrator=orchestrator, demo_coordinator=demo_coordinator)

    with TestClient(app) as client:
        login = client.post("/api/operator/auth/login", json={"token": settings.operator_auth_token})
        assert login.status_code == 200
        response = client.post(
            "/api/events",
            json={
                "event_type": "speech_transcript",
                "session_id": "incident-no-contact",
                "payload": {"text": "I need a staff member to help me right now."},
            },
        )
        assert response.status_code == 200
        assert "do not have a confirmed staff contact" in response.json()["reply_text"].lower()

        ticket = client.get("/api/operator/incidents", params={"scope": "open"}).json()["items"][0]
        assert ticket["suggested_staff_contact"] is None
        assert ticket["current_status"] == "pending"


def test_resolved_and_unresolved_incidents_are_exported_distinctly(brain_client):
    unresolved = brain_client.post(
        "/api/events",
        json={
            "event_type": "speech_transcript",
            "session_id": "incident-unresolved",
            "payload": {"text": "I need accessibility help with the elevator."},
        },
    )
    assert unresolved.status_code == 200

    resolved = brain_client.post(
        "/api/events",
        json={
            "event_type": "speech_transcript",
            "session_id": "incident-resolved",
            "payload": {"text": "Can a staff member help me with a lost item?"},
        },
    )
    assert resolved.status_code == 200
    resolved_ticket_id = brain_client.get("/api/operator/incidents", params={"session_id": "incident-resolved"}).json()["items"][0]["ticket_id"]

    close = brain_client.post(
        f"/api/operator/incidents/{resolved_ticket_id}/resolve",
        json={"outcome": "staff_assisted", "author": "Jordan Lee", "note": "Front desk staff completed the handoff."},
    )
    assert close.status_code == 200
    assert close.json()["current_status"] == "resolved"

    unresolved_episode = brain_client.post(
        "/api/operator/episodes/export-session",
        json={"session_id": "incident-unresolved", "include_asset_refs": False},
    )
    assert unresolved_episode.status_code == 200
    unresolved_body = unresolved_episode.json()
    assert unresolved_body["incidents"][0]["current_status"] == "pending"
    assert unresolved_body["incident_timeline"][0]["event_type"] == "created"

    resolved_episode = brain_client.post(
        "/api/operator/episodes/export-session",
        json={"session_id": "incident-resolved", "include_asset_refs": False},
    )
    assert resolved_episode.status_code == 200
    resolved_body = resolved_episode.json()
    assert resolved_body["incidents"][0]["current_status"] == "resolved"
    assert any(item["event_type"] == "resolved" for item in resolved_body["incident_timeline"])


def test_no_operator_available_path_is_safe_and_explicit(brain_client):
    create = brain_client.post(
        "/api/events",
        json={
            "event_type": "speech_transcript",
            "session_id": "incident-unavailable",
            "payload": {"text": "I need a staff member for accessibility support."},
        },
    )
    assert create.status_code == 200
    ticket_id = brain_client.get("/api/operator/incidents", params={"session_id": "incident-unavailable"}).json()["items"][0]["ticket_id"]

    close = brain_client.post(
        f"/api/operator/incidents/{ticket_id}/resolve",
        json={"outcome": "no_operator_available", "author": "operator_console", "note": "No operator is available on site."},
    )
    assert close.status_code == 200
    assert close.json()["current_status"] == "unavailable"

    follow_up = brain_client.post(
        "/api/events",
        json={
            "event_type": "speech_transcript",
            "session_id": "incident-unavailable",
            "payload": {"text": "Can anyone help me now?"},
        },
    )
    assert follow_up.status_code == 200
    assert "no operator is immediately available" in follow_up.json()["reply_text"].lower()

    session = brain_client.get("/api/sessions/incident-unavailable")
    assert session.status_code == 200
    assert session.json()["status"] == "active"
    assert session.json()["incident_status"] == "unavailable"
