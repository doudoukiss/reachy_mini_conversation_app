from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from embodied_stack.brain.memory import MemoryStore
from hypothesis import given
from hypothesis import strategies as st
from embodied_stack.shared.models import (
    CommandBatch,
    CompanionRelationshipProfile,
    EpisodicMemoryRecord,
    LiveTurnDiagnosticsRecord,
    ProceduralMemoryRecord,
    RelationshipMemoryRecord,
    RelationshipPromiseRecord,
    RelationshipThreadKind,
    RelationshipThreadRecord,
    RelationshipTopicRecord,
    ResponseMode,
    RobotEvent,
    TraceRecord,
    ReasoningTrace,
    SemanticMemoryRecord,
    SessionCreateRequest,
    UserMemoryRecord,
)


def test_memory_store_recovers_from_invalid_snapshot_file(tmp_path):
    store_path = tmp_path / "brain_store.json"
    store_path.write_text('{"sessions": "not-a-dict"', encoding="utf-8")

    store = MemoryStore(store_path)

    assert store.list_sessions().items == []
    backup_paths = list(tmp_path.glob("brain_store.json.corrupt-*"))
    assert len(backup_paths) == 1
    assert not store_path.exists()


def test_memory_store_links_user_memory_when_identity_arrives_after_session_creation(tmp_path):
    store = MemoryStore(tmp_path / "brain_store.json")
    store.create_session(SessionCreateRequest(session_id="anonymous-visitor"))

    session = store.ensure_session(
        "anonymous-visitor",
        user_id="visitor-123",
        response_mode=ResponseMode.AMBASSADOR,
    )

    user_memory = store.get_user_memory("visitor-123")

    assert session.user_id == "visitor-123"
    assert user_memory is not None
    assert user_memory.visit_count == 1
    assert user_memory.last_session_id == "anonymous-visitor"
    assert user_memory.preferred_response_mode == ResponseMode.AMBASSADOR


def test_memory_store_persists_layered_memory_records(tmp_path):
    store_path = tmp_path / "brain_store.json"
    store = MemoryStore(store_path)

    store.upsert_episodic_memory(
        EpisodicMemoryRecord(
            memory_id="session-1",
            session_id="session-1",
            user_id="visitor-1",
            title="wayfinding",
            summary="The visitor asked about the workshop room.",
            topics=["wayfinding", "workshop_room"],
            source_trace_ids=["trace-1"],
            source_refs=["venue_pack:rooms.txt"],
        )
    )
    store.upsert_semantic_memory(
        SemanticMemoryRecord(
            memory_id="semantic-location:session-1",
            memory_kind="venue_location",
            summary="The visitor asked about directions to Workshop Room.",
            canonical_value="workshop_room",
            session_id="session-1",
            user_id="visitor-1",
            tags=["wayfinding", "workshop_room"],
            source_trace_ids=["trace-1"],
            source_refs=["venue_pack:rooms.txt"],
        )
    )

    reloaded = MemoryStore(store_path)

    episodic = reloaded.list_episodic_memory(user_id="visitor-1").items
    semantic = reloaded.list_semantic_memory(session_id="session-1").items

    assert episodic[0].summary == "The visitor asked about the workshop room."
    assert episodic[0].source_trace_ids == ["trace-1"]
    assert semantic[0].memory_kind == "venue_location"
    assert semantic[0].canonical_value == "workshop_room"


def test_memory_store_persists_companion_relationship_profile(tmp_path):
    store_path = tmp_path / "brain_store.json"
    store = MemoryStore(store_path)
    store.upsert_user_memory(
        UserMemoryRecord(
            user_id="visitor-relationship",
            display_name="Alex",
            relationship_profile=CompanionRelationshipProfile(
                planning_style="one_step_at_a_time",
                tone_preferences=["brief", "direct"],
                interaction_boundaries=["avoid_chatty_small_talk"],
                continuity_preferences=["resume_open_threads"],
            ),
        )
    )

    reloaded = MemoryStore(store_path)
    user_memory = reloaded.get_user_memory("visitor-relationship")

    assert user_memory is not None
    assert user_memory.relationship_profile.planning_style == "one_step_at_a_time"
    assert user_memory.relationship_profile.tone_preferences == ["brief", "direct"]
    assert user_memory.relationship_profile.interaction_boundaries == ["avoid_chatty_small_talk"]
    assert user_memory.relationship_profile.continuity_preferences == ["resume_open_threads"]


def test_memory_store_persists_relationship_and_procedural_layers(tmp_path):
    store_path = tmp_path / "brain_store.json"
    store = MemoryStore(store_path)
    store.upsert_relationship_memory(
        RelationshipMemoryRecord(
            relationship_id="visitor-relationship",
            user_id="visitor-relationship",
            familiarity=0.64,
            recurring_topics=[RelationshipTopicRecord(topic="investor_demo", mention_count=2)],
            open_threads=[
                RelationshipThreadRecord(
                    kind=RelationshipThreadKind.PRACTICAL,
                    summary="Resume the investor demo rehearsal.",
                    follow_up_requested=True,
                )
            ],
            promises=[RelationshipPromiseRecord(summary="Follow up on: bring the badge")],
        )
    )
    store.upsert_procedural_memory(
        ProceduralMemoryRecord(
            user_id="visitor-relationship",
            session_id="session-1",
            name="planning routine",
            summary="When planning, give one step at a time.",
            trigger_phrases=["planning"],
            steps=["give one step at a time"],
        )
    )

    reloaded = MemoryStore(store_path)
    relationship = reloaded.get_relationship_memory("visitor-relationship")
    procedures = reloaded.list_procedural_memory(user_id="visitor-relationship").items

    assert relationship is not None
    assert relationship.familiarity == 0.64
    assert relationship.recurring_topics[0].topic == "investor_demo"
    assert relationship.open_threads[0].summary == "Resume the investor demo rehearsal."
    assert procedures[0].name == "planning routine"


def test_memory_store_batch_update_defers_full_store_flushes(tmp_path, monkeypatch):
    store_path = tmp_path / "brain_store.json"
    store = MemoryStore(store_path)
    writes: list[str] = []
    original = store._persist_now_locked

    def wrapped() -> None:
        writes.append("write")
        original()

    monkeypatch.setattr(store, "_persist_now_locked", wrapped)

    with store.batch_update():
        store.create_session(SessionCreateRequest(session_id="batched-session"))
        store.upsert_episodic_memory(
            EpisodicMemoryRecord(
                memory_id="batched-episodic",
                session_id="batched-session",
                user_id="visitor-1",
                title="batched",
                summary="Batched persistence keeps the store responsive.",
            )
        )
        store.upsert_semantic_memory(
            SemanticMemoryRecord(
                memory_id="batched-semantic",
                memory_kind="preference",
                summary="The visitor prefers faster live responses.",
                canonical_value="fast_live_responses",
                session_id="batched-session",
                user_id="visitor-1",
            )
        )
        assert writes == []

    assert writes == ["write"]

    reloaded = MemoryStore(store_path)
    assert reloaded.get_session("batched-session") is not None
    assert reloaded.get_episodic_memory("batched-episodic") is not None
    assert reloaded.get_semantic_memory("batched-semantic") is not None


@given(
    st.lists(
        st.text(
            alphabet=st.characters(
                min_codepoint=32,
                max_codepoint=126,
                blacklist_characters=["\n", "\r"],
            ),
            min_size=1,
            max_size=24,
        ),
        max_size=5,
    )
)
def test_memory_store_update_trace_roundtrips_live_turn_diagnostics(diagnostic_notes):
    with TemporaryDirectory() as temp_dir:
        store_path = Path(temp_dir) / "brain_store.json"
        store = MemoryStore(store_path)
        trace = TraceRecord(
            session_id="property-session",
            user_id="property-user",
            event=RobotEvent(event_type="speech_transcript", session_id="property-session", payload={"text": "hello"}),
            response=CommandBatch(session_id="property-session", reply_text="hi", commands=[]),
            reasoning=ReasoningTrace(engine="rule_based", intent="greeting"),
        )
        store.append_trace(trace)

        updated = trace.model_copy(deep=True)
        updated.reasoning.live_turn_diagnostics = LiveTurnDiagnosticsRecord(
            source="browser_speech_recognition",
            visual_query=False,
            notes=diagnostic_notes,
        )
        store.update_trace(updated)

        reloaded = MemoryStore(store_path)
        fetched = reloaded.get_trace(trace.trace_id)

        assert fetched is not None
        assert fetched.reasoning.live_turn_diagnostics is not None
        assert fetched.reasoning.live_turn_diagnostics.notes == diagnostic_notes
