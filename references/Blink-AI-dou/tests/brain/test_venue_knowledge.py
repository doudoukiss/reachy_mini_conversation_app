from __future__ import annotations

from pathlib import Path

from embodied_stack.backends.embeddings import HashEmbeddingBackend
from embodied_stack.brain.orchestrator import BrainOrchestrator
from embodied_stack.brain.tools import KnowledgeToolbox
from embodied_stack.brain.venue_knowledge import VenueKnowledge
from embodied_stack.config import Settings
from embodied_stack.shared.models import OperatorNote, ResponseMode, RobotEvent, SessionRecord, VoiceTurnRequest, WorldState


def test_venue_knowledge_ingests_mixed_content_formats(tmp_path: Path):
    pack_dir = tmp_path / "pilot_site"
    pack_dir.mkdir(parents=True)
    (pack_dir / "site.yaml").write_text(
        "site_name: Test Venue\nhours_summary: Monday to Friday 9 AM to 5 PM.\n",
        encoding="utf-8",
    )
    (pack_dir / "faqs.yaml").write_text(
        "- key: hours\n  question: What are your hours?\n  answer: We are open weekdays.\n  aliases: [hours, open]\n",
        encoding="utf-8",
    )
    (pack_dir / "events.csv").write_text(
        "event_id,title,start_at,location_label,summary\nopen_house,Open House,2026-04-01T10:00:00,Lobby,Meet the team.\n",
        encoding="utf-8",
    )
    (pack_dir / "rooms.txt").write_text(
        "front_desk|Front Desk|Lobby|Walk straight from the entrance.|front desk|Front Desk|main entrance\n",
        encoding="utf-8",
    )
    (pack_dir / "staff_contacts.txt").write_text(
        "front_desk|Jordan Lee|Front Desk Coordinator|555-0100|frontdesk@test.org|Lobby support|front desk, reception\n",
        encoding="utf-8",
    )
    (pack_dir / "operations.md").write_text(
        "# Operations\n\nThe front desk keeps printed maps.\n",
        encoding="utf-8",
    )
    (pack_dir / "calendar.ics").write_text(
        "BEGIN:VCALENDAR\nBEGIN:VEVENT\nUID:evening_tour\nDTSTART:20260402T180000\nSUMMARY:Evening Tour\nLOCATION:Lobby\nDESCRIPTION:Walkthrough.\nEND:VEVENT\nEND:VCALENDAR\n",
        encoding="utf-8",
    )

    knowledge = VenueKnowledge.from_directory(pack_dir)
    assert knowledge.site_name == "Test Venue"
    assert len(knowledge.faqs) == 1
    assert {item.title for item in knowledge.events} >= {"Open House", "Evening Tour"}
    assert "front_desk" in knowledge.locations
    assert knowledge.staff_contacts[0].role == "Front Desk Coordinator"
    assert knowledge.documents[0].title == "Operations"


def test_imported_venue_pack_answers_event_question(brain_client):
    response = brain_client.post(
        "/api/events",
        json={
            "event_type": "speech_transcript",
            "session_id": "venue-events",
            "payload": {"text": "What events are happening this week?"},
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert "Robotics Workshop" in body["reply_text"]

    trace = brain_client.get(f"/api/traces/{body['trace_id']}")
    assert trace.status_code == 200
    tool = trace.json()["reasoning"]["tool_invocations"][0]
    assert tool["tool_name"] == "events_lookup"
    assert tool["metadata"]["knowledge_source"] == "venue_pack"
    assert "events.csv" in tool["metadata"]["source_refs"]


def test_perception_grounded_direction_followup_uses_visible_signage(brain_client):
    first = brain_client.post(
        "/api/events",
        json={
            "event_type": "speech_transcript",
            "session_id": "venue-wayfinding",
            "payload": {"text": "Where is the workshop room?"},
        },
    )
    assert first.status_code == 200

    perception = brain_client.post(
        "/api/events",
        json={
            "event_type": "visible_text_detected",
            "session_id": "venue-wayfinding",
            "payload": {"text": "Workshop Room", "confidence": 0.92},
        },
    )
    assert perception.status_code == 200

    follow_up = brain_client.post(
        "/api/events",
        json={
            "event_type": "speech_transcript",
            "session_id": "venue-wayfinding",
            "payload": {"text": "Can you repeat how to get there?"},
        },
    )
    assert follow_up.status_code == 200
    body = follow_up.json()
    assert "I can currently ground" in body["reply_text"]
    assert "Workshop Room" in body["reply_text"]

    trace = brain_client.get(f"/api/traces/{body['trace_id']}")
    assert trace.status_code == 200
    notes = trace.json()["reasoning"]["tool_invocations"][0]["notes"]
    assert "perception_grounded_wayfinding" in notes


def test_conflicting_location_data_is_handled_honestly(tmp_path: Path):
    pack_dir = tmp_path / "conflict_site"
    pack_dir.mkdir(parents=True)
    (pack_dir / "rooms.txt").write_text(
        "\n".join(
            [
                "front_desk_a|Front Desk|Lobby|Turn left from the entrance.|front desk|Front Desk|main entrance",
                "front_desk_b|Front Desk|Lobby|Turn right from the entrance.|front desk|Front Desk|main entrance",
            ]
        ),
        encoding="utf-8",
    )
    settings = Settings(venue_content_dir=str(pack_dir))
    toolbox = KnowledgeToolbox(settings=settings)

    result = toolbox.lookup(
        "where is the front desk?",
        session=SessionRecord(session_id="conflict-session", response_mode=ResponseMode.GUIDE),
        user_memory=None,
        world_state=WorldState(),
    )
    assert result
    assert result[0].tool_name == "wayfinding_lookup"
    assert "conflicting venue directions" in (result[0].answer_text or "").lower()
    assert result[0].metadata["knowledge_source"] == "venue_pack"
    assert result[0].notes == ["venue_location_conflict"]


def test_provider_fallback_still_uses_venue_pack_without_credentials(tmp_path: Path):
    settings = Settings(
        brain_store_path=str(tmp_path / "brain_store.json"),
        demo_report_dir=str(tmp_path / "demo_runs"),
        brain_dialogue_backend="grsai",
        grsai_api_key=None,
    )
    orchestrator = BrainOrchestrator(settings=settings, store_path=settings.brain_store_path)
    result = orchestrator.handle_voice_turn(
        VoiceTurnRequest(session_id="venue-fallback", input_text="Where is the front desk?")
    )
    assert "front desk" in (result.response.reply_text or "").lower()

    trace = orchestrator.get_trace(result.response.trace_id)
    assert trace is not None
    assert trace.reasoning.fallback_used is True
    assert trace.reasoning.tool_invocations[0].metadata["knowledge_source"] == "venue_pack"


def test_local_hash_embeddings_support_semantic_memory_retrieval(tmp_path: Path):
    settings = Settings(
        _env_file=None,
        brain_store_path=str(tmp_path / "brain_store.json"),
        demo_report_dir=str(tmp_path / "demo_runs"),
    )
    toolbox = KnowledgeToolbox(settings=settings, embedding_backend=HashEmbeddingBackend())

    results = toolbox.lookup(
        "Can you use the sunrise badge handoff script?",
        session=SessionRecord(
            session_id="semantic-memory",
            response_mode=ResponseMode.GUIDE,
            operator_notes=[OperatorNote(text="Use the sunrise badge handoff script if asked.")],
        ),
        user_memory=None,
        world_state=WorldState(),
    )

    assert results
    assert results[0].answer_text == "Use the sunrise badge handoff script if asked."
    assert results[0].metadata["retrieval_backend"] == "hash_embed"
    assert "semantic_operator_note" in results[0].notes


def test_missing_venue_or_perception_data_is_honest(tmp_path: Path):
    pack_dir = tmp_path / "empty_site"
    pack_dir.mkdir(parents=True)
    settings = Settings(
        brain_store_path=str(tmp_path / "empty_store.json"),
        demo_report_dir=str(tmp_path / "demo_runs"),
        venue_content_dir=str(pack_dir),
    )
    orchestrator = BrainOrchestrator(settings=settings, store_path=settings.brain_store_path)
    response = orchestrator.handle_event(
        RobotEvent(
            event_type="speech_transcript",
            session_id="empty-venue",
            payload={"text": "Where is the atrium?"},
        )
    )
    assert "do not have a confirmed venue entry" in (response.reply_text or "").lower()

    trace = orchestrator.get_trace(response.trace_id)
    assert trace is not None
    assert trace.reasoning.tool_invocations[0].notes == ["venue_location_insufficient"]
