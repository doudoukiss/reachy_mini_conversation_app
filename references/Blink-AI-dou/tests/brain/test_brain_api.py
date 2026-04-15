from __future__ import annotations

from fastapi.testclient import TestClient

from embodied_stack.brain.app import create_app as create_brain_app
from embodied_stack.brain.orchestrator import BrainOrchestrator
from embodied_stack.config import Settings
from embodied_stack.demo.coordinator import DemoCoordinator
from embodied_stack.desktop.runtime import build_inprocess_embodiment_gateway


def test_brain_health(brain_client):
    response = brain_client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["service"] == "brain"
    assert body["project_name"] == "Blink-AI"
    assert body["voice_backend"] == "stub"
    assert body["backend_profile"] == "companion_live"
    assert body["dialogue_backend"] == "rule_based"
    assert body["embedding_backend"] == "hash_embed"
    assert body["stt_backend"] == "typed_input"
    assert body["tts_backend"] == "stub_tts"
    assert body["operator_auth_enabled"] is True


def test_brain_readiness_reports_local_offline_defaults(brain_client):
    response = brain_client.get("/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    checks = {item["name"]: item for item in body["checks"]}
    assert checks["brain_store"]["ok"] is True
    assert checks["dialogue_backend"]["detail"] == "rule_based:warm:deterministic_local_reply_engine"
    assert checks["vision_backend"]["detail"].startswith("native_camera_snapshot:")
    assert checks["embedding_backend"]["detail"].startswith("hash_embed:fallback_active:")
    assert checks["stt_backend"]["detail"] == "typed_input:degraded:typed_input_only_no_audio_transcription"
    assert checks["tts_backend"]["detail"] == "stub_tts:degraded:simulated_speech_output_only"
    assert checks["default_voice_mode"]["ok"] is True
    assert "microphone_device" in checks
    assert "speaker_device" in checks
    assert "camera_device" in checks
    assert checks["operator_auth"]["detail"] in {"env", "generated_runtime", "persisted_runtime"}


def test_session_memory_and_followup_wayfinding(brain_client):
    brain_client.post(
        "/api/sessions",
        json={
            "session_id": "visitor-1",
            "user_id": "user-123",
            "operator_notes": ["Offer the April volunteer packet if asked."],
        },
    )

    intro = brain_client.post(
        "/api/events",
        json={
            "event_type": "speech_transcript",
            "session_id": "visitor-1",
            "payload": {"text": "My name is Alex."},
        },
    )
    assert intro.status_code == 200
    assert "Alex" in intro.json()["reply_text"]

    first = brain_client.post(
        "/api/events",
        json={
            "event_type": "speech_transcript",
            "session_id": "visitor-1",
            "payload": {"text": "Where is the workshop room?"},
        },
    )
    assert first.status_code == 200
    assert "Workshop Room" in first.json()["reply_text"]

    follow_up = brain_client.post(
        "/api/events",
        json={
            "event_type": "speech_transcript",
            "session_id": "visitor-1",
            "payload": {"text": "Can you repeat how to get there?"},
        },
    )
    assert follow_up.status_code == 200
    assert "Workshop Room" in follow_up.json()["reply_text"]

    session = brain_client.get("/api/sessions/visitor-1")
    assert session.status_code == 200
    body = session.json()
    assert body["session_memory"]["last_location"] == "workshop_room"
    assert body["session_memory"]["remembered_name"] == "Alex"
    assert body["operator_notes"][0]["text"] == "Offer the April volunteer packet if asked."
    assert "Current topic" in body["conversation_summary"]
    assert len(body["transcript"]) == 3


def test_user_memory_persists_across_sessions(brain_client):
    brain_client.post("/api/sessions", json={"session_id": "s1", "user_id": "repeat-user"})
    brain_client.post(
        "/api/events",
        json={
            "event_type": "speech_transcript",
            "session_id": "s1",
            "payload": {"text": "My name is Priya."},
        },
    )

    brain_client.post("/api/sessions", json={"session_id": "s2", "user_id": "repeat-user"})
    remembered = brain_client.post(
        "/api/events",
        json={
            "event_type": "speech_transcript",
            "session_id": "s2",
            "payload": {"text": "Do you remember me?"},
        },
    )
    assert remembered.status_code == 200
    assert "Priya" in remembered.json()["reply_text"]


def test_response_mode_endpoint_changes_future_replies(brain_client):
    brain_client.post("/api/sessions", json={"session_id": "mode-session"})
    update = brain_client.post(
        "/api/sessions/mode-session/response-mode",
        json={"response_mode": "debug"},
    )
    assert update.status_code == 200
    assert update.json()["response_mode"] == "debug"

    reply = brain_client.post(
        "/api/events",
        json={
            "event_type": "speech_transcript",
            "session_id": "mode-session",
            "payload": {"text": "What can you do?"},
        },
    )
    assert reply.status_code == 200
    assert "[debug mode]" in reply.json()["reply_text"]


def test_voice_turn_uses_same_session_trace_path(brain_client):
    response = brain_client.post(
        "/api/voice/turn",
        json={
            "session_id": "voice-session",
            "input_text": "Where is the quiet room?",
            "response_mode": "ambassador",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "stub_voice"
    assert body["response"]["trace_id"]
    assert "Happy to help." in body["response"]["reply_text"]

    session = brain_client.get("/api/sessions/voice-session").json()
    assert session["response_mode"] == "ambassador"
    assert session["transcript"][0]["event_type"] == "speech_transcript"


def test_openai_voice_backend_falls_back_to_stub(tmp_path):
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
            json={"session_id": "fallback-voice", "input_text": "Where is the front desk?"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["provider"] == "stub_voice"
        assert body["used_fallback"] is True
