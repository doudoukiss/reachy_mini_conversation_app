from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from embodied_stack.brain.app import create_app as create_brain_app
from embodied_stack.brain.orchestrator import BrainOrchestrator
from embodied_stack.config import Settings
from embodied_stack.demo.coordinator import DemoCoordinator
from embodied_stack.demo.smoke import run_smoke
from embodied_stack.desktop.runtime import build_inprocess_embodiment_gateway


FIXTURES_DIR = Path(__file__).resolve().parents[1] / "fixtures"


def test_seeded_single_turn_questions(brain_client):
    cases = json.loads((FIXTURES_DIR / "community_questions.json").read_text(encoding="utf-8"))
    for index, case in enumerate(cases, start=1):
        response = brain_client.post(
            "/api/events",
            json={
                "event_type": "speech_transcript",
                "session_id": f"qa-{index}",
                "payload": {"text": case["text"]},
            },
        )
        assert response.status_code == 200
        assert case["expected_contains"].lower() in response.json()["reply_text"].lower()


def test_seeded_multi_turn_flows(brain_client):
    flows = json.loads((FIXTURES_DIR / "multi_turn_flows.json").read_text(encoding="utf-8"))
    for flow in flows:
        session_id = f"flow-{flow['name']}"
        for step in flow["steps"]:
            response = brain_client.post(
                "/api/events",
                json={
                    "event_type": "speech_transcript",
                    "session_id": session_id,
                    "payload": {"text": step["text"]},
                },
            )
            assert response.status_code == 200
            assert step["expected_contains"].lower() in response.json()["reply_text"].lower()
        session = brain_client.get(f"/api/sessions/{session_id}")
        assert session.status_code == 200
        assert session.json()["conversation_summary"]


def test_disconnect_and_low_battery_paths_generate_safe_fallback_traces(brain_client, edge_client):
    network = edge_client.post(
        "/api/sim/events",
        json={"event_type": "network_state", "session_id": "fallback-session", "payload": {"network_ok": False}},
    )
    heartbeat_event = network.json()["event"]
    response = brain_client.post("/api/events", json=heartbeat_event)
    assert response.status_code == 200
    trace = brain_client.get(f"/api/traces/{response.json()['trace_id']}")
    assert trace.status_code == 200
    assert trace.json()["outcome"] == "safe_fallback"

    low_battery = brain_client.post(
        "/api/events",
        json={"event_type": "low_battery", "session_id": "fallback-session", "payload": {"battery_pct": 10.0}},
    )
    trace = brain_client.get(f"/api/traces/{low_battery.json()['trace_id']}")
    assert trace.json()["outcome"] == "safe_fallback"


def test_smoke_entrypoint_runs():
    run_smoke()


def test_provider_unavailable_voice_fallback_works(tmp_path):
    settings = Settings(
        brain_store_path=str(tmp_path / "brain_store.json"),
        demo_report_dir=str(tmp_path / "demo_runs"),
        brain_dialogue_backend="rule_based",
        brain_voice_backend="openai",
        openai_api_key=None,
    )
    orchestrator = BrainOrchestrator(settings=settings, store_path=settings.brain_store_path)
    coordinator = DemoCoordinator(
        orchestrator=orchestrator,
        edge_gateway=build_inprocess_embodiment_gateway(settings),
        report_dir=settings.demo_report_dir,
    )
    app = create_brain_app(settings=settings, orchestrator=orchestrator, demo_coordinator=coordinator)

    with TestClient(app) as client:
        response = client.post(
            "/api/voice/turn",
            json={"session_id": "voice-provider-fallback", "input_text": "Where is the quiet room?"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["used_fallback"] is True
        assert "Quiet Room" in body["response"]["reply_text"]
