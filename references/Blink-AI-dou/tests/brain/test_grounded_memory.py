from __future__ import annotations

from datetime import timedelta

from embodied_stack.brain.grounded_memory import GroundedMemoryService
from embodied_stack.brain.memory import MemoryStore
from embodied_stack.brain.orchestrator import BrainOrchestrator
from embodied_stack.brain.venue_knowledge import VenueKnowledge
from embodied_stack.shared.models import (
    EmbodiedWorldModel,
    EpisodicMemoryRecord,
    PerceptionConfidence,
    PerceptionObservation,
    PerceptionObservationType,
    PerceptionProviderMode,
    PerceptionSnapshotRecord,
    PerceptionSnapshotStatus,
    PerceptionSourceFrame,
    ProceduralMemoryRecord,
    RelationshipMemoryRecord,
    RelationshipPromiseRecord,
    RelationshipThreadKind,
    RelationshipThreadRecord,
    RelationshipTopicRecord,
    SemanticMemoryRecord,
    SessionRecord,
    UserMemoryRecord,
    VoiceTurnRequest,
    WorldModelObservation,
    utc_now,
)


def _grounded_memory_service(settings, tmp_path) -> tuple[GroundedMemoryService, MemoryStore]:
    store = MemoryStore(tmp_path / "brain_store.json")
    venue_knowledge = VenueKnowledge.from_directory(settings.venue_content_dir)
    return GroundedMemoryService(memory_store=store, venue_knowledge=venue_knowledge), store


def test_grounded_memory_retrieves_profile_and_prior_session(settings, tmp_path):
    service, store = _grounded_memory_service(settings, tmp_path)
    user_memory = UserMemoryRecord(
        user_id="visitor-1",
        display_name="Alex",
        preferences={"route_preference": "quiet route"},
    )
    store.upsert_user_memory(user_memory)
    store.upsert_episodic_memory(
        EpisodicMemoryRecord(
            memory_id="session-1",
            session_id="session-1",
            user_id="visitor-1",
            title="wayfinding",
            summary="we discussed directions to the workshop room.",
            topics=["wayfinding", "workshop_room"],
            source_trace_ids=["trace-1"],
            source_refs=["venue_pack:rooms.txt"],
        )
    )

    profile = service.lookup_profile_memory("What do you remember about me?", user_memory=user_memory)
    prior = service.lookup_prior_session(
        "What did we talk about last time?",
        session=SessionRecord(session_id="session-2", user_id="visitor-1"),
        user_memory=user_memory,
    )

    assert profile is not None
    assert "Alex" in (profile.answer_text or "")
    assert "quiet route" in (profile.answer_text or "")
    assert prior is not None
    assert "workshop room" in (prior.answer_text or "").lower()
    assert prior.metadata["knowledge_source"] == "episodic_memory"


def test_recent_perception_facts_rejects_stale_snapshot_and_expired_world_model(settings, tmp_path):
    service, _store = _grounded_memory_service(settings, tmp_path)
    stale_at = utc_now() - timedelta(minutes=2)
    world_model = EmbodiedWorldModel(
        recent_visible_text=[
            WorldModelObservation(
                label="Old Sign",
                confidence=PerceptionConfidence(score=0.92, label="high"),
                observed_at=stale_at,
                expires_at=utc_now() - timedelta(seconds=1),
                source_event_type="visible_text_detected",
            )
        ],
        last_perception_at=stale_at,
    )
    snapshot = PerceptionSnapshotRecord(
        provider_mode=PerceptionProviderMode.STUB,
        status=PerceptionSnapshotStatus.OK,
        scene_summary="Old lobby frame",
        source_frame=PerceptionSourceFrame(source_kind="image_fixture", captured_at=stale_at),
        observations=[
            PerceptionObservation(
                observation_type=PerceptionObservationType.VISIBLE_TEXT,
                text_value="Old Sign",
                confidence=PerceptionConfidence(score=0.95, label="high"),
                source_frame=PerceptionSourceFrame(source_kind="image_fixture", captured_at=stale_at),
            )
        ],
        created_at=stale_at,
    )

    facts = service.recent_perception_facts(
        world_model=world_model,
        latest_perception=snapshot,
        query="What sign do you see?",
    )
    lookup = service.lookup_recent_perception(
        "What sign do you see?",
        world_model=world_model,
        latest_perception=snapshot,
    )

    assert facts == []
    assert lookup is not None
    assert lookup.notes == ["stale_perception_rejected"]
    assert lookup.metadata["snapshot_stale"] is True


def test_recent_perception_lookup_avoids_world_model_scene_facts_when_latest_snapshot_has_limited_awareness(
    settings, tmp_path
):
    service, _store = _grounded_memory_service(settings, tmp_path)
    captured_at = utc_now()
    world_model = EmbodiedWorldModel(
        recent_visible_text=[
            WorldModelObservation(
                label="Workshop Room",
                confidence=PerceptionConfidence(score=0.92, label="high"),
                observed_at=captured_at - timedelta(seconds=10),
                expires_at=captured_at + timedelta(seconds=20),
                source_event_type="visible_text_detected",
            )
        ]
    )
    snapshot = PerceptionSnapshotRecord(
        provider_mode=PerceptionProviderMode.STUB,
        status=PerceptionSnapshotStatus.FAILED,
        limited_awareness=True,
        scene_summary="Perception is currently limited.",
        source_frame=PerceptionSourceFrame(source_kind="image_fixture", captured_at=captured_at),
    )

    facts = service.recent_perception_facts(
        world_model=world_model,
        latest_perception=snapshot,
        query="What sign can you see right now?",
    )
    lookup = service.lookup_recent_perception(
        "What sign can you see right now?",
        world_model=world_model,
        latest_perception=snapshot,
    )

    assert facts == []
    assert lookup is not None
    assert "limited right now" in (lookup.answer_text or "").lower()
    assert "Workshop Room" not in (lookup.answer_text or "")
    assert lookup.metadata["limited_awareness"] is True


def test_memory_context_assembly_surfaces_profile_episodic_semantic_and_perception(settings, tmp_path):
    service, store = _grounded_memory_service(settings, tmp_path)
    user_memory = UserMemoryRecord(
        user_id="visitor-1",
        display_name="Alex",
        preferences={"route_preference": "quiet route"},
    )
    store.upsert_user_memory(user_memory)
    store.upsert_episodic_memory(
        EpisodicMemoryRecord(
            memory_id="session-1",
            session_id="session-1",
            user_id="visitor-1",
            title="wayfinding",
            summary="we discussed the workshop room and the quiet route.",
            topics=["wayfinding", "workshop_room", "quiet_route"],
            source_trace_ids=["trace-1"],
            source_refs=["venue_pack:rooms.txt"],
        )
    )
    store.upsert_semantic_memory(
        SemanticMemoryRecord(
            memory_id="semantic-1",
            memory_kind="visitor_preference",
            summary="The visitor prefers the quiet route to the workshop room.",
            canonical_value="quiet_route",
            session_id="session-1",
            user_id="visitor-1",
            tags=["quiet_route", "workshop_room"],
            source_trace_ids=["trace-1"],
            source_refs=["profile:visitor-1"],
        )
    )
    world_model = EmbodiedWorldModel(
        recent_visible_text=[
            WorldModelObservation(
                label="Workshop Room",
                confidence=PerceptionConfidence(score=0.91, label="high"),
                observed_at=utc_now(),
                expires_at=utc_now() + timedelta(seconds=30),
                source_event_type="visible_text_detected",
            )
        ]
    )

    context = service.build_memory_context(
        "quiet route workshop room sign",
        session=SessionRecord(session_id="session-2", user_id="visitor-1"),
        user_memory=user_memory,
        world_model=world_model,
        latest_perception=None,
    )

    assert context.profile_summary is not None
    assert "quiet route" in context.profile_summary
    assert context.episodic_hits
    assert context.semantic_hits
    assert [item.label for item in context.perception_facts] == ["Workshop Room"]


def test_memory_context_adds_relationship_and_procedural_hits_without_always_injecting_profile(settings, tmp_path):
    service, store = _grounded_memory_service(settings, tmp_path)
    user_memory = UserMemoryRecord(
        user_id="visitor-1",
        display_name="Alex",
        preferences={"route_preference": "quiet route"},
    )
    store.upsert_user_memory(user_memory)
    store.upsert_relationship_memory(
        RelationshipMemoryRecord(
            relationship_id="visitor-1",
            user_id="visitor-1",
            familiarity=0.72,
            recurring_topics=[RelationshipTopicRecord(topic="investor_demo", mention_count=3)],
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
            user_id="visitor-1",
            session_id="session-1",
            name="planning routine",
            summary="When planning, give one step at a time.",
            trigger_phrases=["planning"],
            steps=["give one step at a time"],
        )
    )

    neutral = service.build_memory_context(
        "What sign do you see?",
        session=SessionRecord(session_id="session-2", user_id="visitor-1"),
        user_memory=user_memory,
        world_model=EmbodiedWorldModel(),
        latest_perception=None,
    )
    follow_up = service.build_memory_context(
        "Can we pick up where we left off on the investor demo?",
        session=SessionRecord(session_id="session-2", user_id="visitor-1"),
        user_memory=user_memory,
        world_model=EmbodiedWorldModel(),
        latest_perception=None,
    )

    assert neutral.profile_summary is None
    assert neutral.relationship_summary is None
    assert follow_up.relationship_summary is not None
    assert follow_up.relationship_hits
    assert follow_up.relationship_hits[0].summary == "Resume the investor demo rehearsal."
    assert follow_up.procedural_hits == []

    planning = service.build_memory_context(
        "Help me with planning today.",
        session=SessionRecord(session_id="session-2", user_id="visitor-1"),
        user_memory=user_memory,
        world_model=EmbodiedWorldModel(),
        latest_perception=None,
    )
    assert planning.procedural_hits
    assert planning.procedural_hits[0].name == "planning routine"


def test_recent_perception_lookup_keeps_people_count_and_low_light_context(settings, tmp_path):
    service, _store = _grounded_memory_service(settings, tmp_path)
    snapshot = PerceptionSnapshotRecord(
        provider_mode=PerceptionProviderMode.OLLAMA_VISION,
        status=PerceptionSnapshotStatus.DEGRADED,
        limited_awareness=True,
        scene_summary="Dark indoor setting with a person seated in the lower center of the frame; lighting is insufficient for detailed assessment.",
        source_frame=PerceptionSourceFrame(source_kind="native_camera_snapshot", captured_at=utc_now()),
        observations=[
            PerceptionObservation(
                observation_type=PerceptionObservationType.PEOPLE_COUNT,
                number_value=1,
                confidence=PerceptionConfidence(score=0.55, label="medium"),
                source_frame=PerceptionSourceFrame(source_kind="native_camera_snapshot", captured_at=utc_now()),
            ),
            PerceptionObservation(
                observation_type=PerceptionObservationType.ENGAGEMENT_ESTIMATE,
                text_value="focused on screen or task below view",
                confidence=PerceptionConfidence(score=0.55, label="medium"),
                source_frame=PerceptionSourceFrame(source_kind="native_camera_snapshot", captured_at=utc_now()),
            ),
        ],
    )

    lookup = service.lookup_recent_perception(
        "What can you see from the cameras now?",
        world_model=EmbodiedWorldModel(),
        latest_perception=snapshot,
    )

    assert lookup is not None
    assert "1 person" in (lookup.answer_text or "")
    assert "focused on screen or task below view" in (lookup.answer_text or "")
    assert "lighting is insufficient" in (lookup.answer_text or "")


def test_orchestrator_grounded_memory_smoke_reuses_profile_and_prior_session(settings):
    orchestrator = BrainOrchestrator(settings=settings, store_path=settings.brain_store_path)

    orchestrator.handle_voice_turn(
        VoiceTurnRequest(
            session_id="memory-session-1",
            user_id="visitor-1",
            input_text="My name is Alex and I prefer the quiet route.",
        )
    )
    remembered = orchestrator.handle_voice_turn(
        VoiceTurnRequest(
            session_id="memory-session-2",
            user_id="visitor-1",
            input_text="What do you remember about me?",
        )
    )
    prior = orchestrator.handle_voice_turn(
        VoiceTurnRequest(
            session_id="memory-session-3",
            user_id="visitor-1",
            input_text="What did we talk about last time?",
        )
    )

    assert "Alex" in (remembered.response.reply_text or "")
    assert "quiet route" in (remembered.response.reply_text or "").lower()
    assert "prior session" in (prior.response.reply_text or "").lower()
    assert "quiet route" in (prior.response.reply_text or "").lower()


def test_record_turn_memory_updates_relationship_runtime(settings, tmp_path):
    service, store = _grounded_memory_service(settings, tmp_path)
    session = store.ensure_session("relationship-session", user_id="visitor-1")
    user_memory = UserMemoryRecord(user_id="visitor-1", display_name="Alex", visit_count=2)
    user_memory.relationship_profile.tone_preferences.append("brief")
    store.upsert_user_memory(user_memory)
    session.current_topic = "investor_demo"
    session.last_user_text = "Remind me to bring the badge tomorrow and let's pick up the investor demo later."
    session.last_reply_text = "I will keep that ready."
    session.conversation_summary = "We left one open investor demo follow-up."
    store.upsert_session(session)

    promotions = service.record_turn(
        session=session,
        user_memory=user_memory,
        trace_id="trace-1",
        reply_text=session.last_reply_text,
        intent="remember_and_follow_up",
        source_refs=["session:relationship-session"],
    )

    relationship = store.get_relationship_memory("visitor-1")

    assert relationship is not None
    assert relationship.familiarity >= 0.4
    assert relationship.preferred_style.tone_preferences == ["brief"]
    assert any("bring the badge" in item.summary for item in relationship.open_threads)
    assert any(item.summary.startswith("Follow up on:") for item in relationship.promises)
    assert {item.promotion_type for item in promotions} >= {"relationship_memory", "personal_reminder"}
