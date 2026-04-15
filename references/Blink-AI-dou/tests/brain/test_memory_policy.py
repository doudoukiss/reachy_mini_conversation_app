from __future__ import annotations

from embodied_stack.brain.memory import MemoryStore
from embodied_stack.brain.memory_layers import MemoryLayerService
from embodied_stack.brain.memory_policy import MemoryPolicyService
from embodied_stack.shared.contracts import (
    EpisodicMemoryRecord,
    MemoryRetrievalBackend,
    MemoryLayer,
    MemoryReviewStatus,
    MemoryWriteReasonCode,
    ProceduralMemoryRecord,
    RelationshipMemoryRecord,
    RelationshipThreadKind,
    RelationshipThreadRecord,
    ReviewDebtState,
    SemanticMemoryRecord,
    SessionRecord,
    UserMemoryRecord,
)
from embodied_stack.shared.contracts.brain import MemoryRetrievalRecord, MemoryReviewRequest
from embodied_stack.shared.contracts.episode import TeacherAnnotationRecord, TeacherReviewRequest


def test_memory_policy_records_layered_actions_and_retrieval(tmp_path):
    store = MemoryStore(tmp_path / "brain_store.json")
    layers = MemoryLayerService(store)
    policy = MemoryPolicyService(store)
    session = store.ensure_session("memory-policy", user_id="visitor-1")
    user_memory = UserMemoryRecord(user_id="visitor-1", display_name="Alex")
    store.upsert_user_memory(user_memory)

    world_action = policy.write_session_memory(
        session=session,
        key="current_topic",
        value="wayfinding",
        reason_code=MemoryWriteReasonCode.SESSION_CONTEXT,
        tool_name="write_memory",
    )
    profile_record, profile_action = policy.write_profile_fact(
        user_memory=user_memory,
        key="preferred_route",
        value="quiet route",
        reason_code=MemoryWriteReasonCode.PROFILE_PREFERENCE,
        tool_name="write_memory",
    )
    episodic_action = policy.promote_episodic(
        EpisodicMemoryRecord(
            memory_id="episodic-1",
            session_id=session.session_id,
            user_id=session.user_id,
            title="wayfinding",
            summary="Alex asked for the quiet route to the workshop room.",
            topics=["wayfinding"],
        ),
        reason_code=MemoryWriteReasonCode.CONVERSATION_TOPIC,
        tool_name="promote_memory",
    )
    semantic_action = policy.promote_semantic(
        SemanticMemoryRecord(
            memory_id="semantic-1",
            memory_kind="route_preference",
            summary="Alex prefers the quiet route.",
            canonical_value="quiet route",
            session_id=session.session_id,
            user_id=session.user_id,
        ),
        reason_code=MemoryWriteReasonCode.CONVERSATION_TOPIC,
        tool_name="promote_memory",
    )

    actions = layers.list_actions(user_id="visitor-1", limit=20).items
    assert {item.action_id for item in actions} >= {
        world_action.action_id,
        profile_action.action_id,
        episodic_action.action_id,
        semantic_action.action_id,
    }
    assert layers.get_profile("visitor-1").facts["preferred_route"] == "quiet route"
    assert layers.list_episodic(session_id=session.session_id).items[0].memory_layer == MemoryLayer.EPISODIC
    assert layers.list_semantic(session_id=session.session_id).items[0].memory_layer == MemoryLayer.SEMANTIC
    assert world_action.layer == MemoryLayer.WORLD
    assert profile_record.memory_layer == MemoryLayer.PROFILE
    assert profile_record.policy_scorecard is not None
    assert profile_record.policy_scorecard.promotion_score >= 0.70
    assert episodic_action.policy_scorecard is not None
    assert semantic_action.policy_scorecard is not None
    assert profile_action.decision_outcome is not None

    store.append_memory_retrievals(
        [
            MemoryRetrievalRecord(
                query_text="quiet route",
                backend=MemoryRetrievalBackend.PROFILE_SCAN,
                session_id=session.session_id,
                user_id=session.user_id,
                selected_candidates=[],
                used_in_reply=True,
            )
        ]
    )
    retrievals = layers.list_retrievals(session_id=session.session_id, limit=10).items
    assert retrievals[0].backend == MemoryRetrievalBackend.PROFILE_SCAN


def test_memory_policy_corrections_and_tombstones_change_default_reads(tmp_path):
    store = MemoryStore(tmp_path / "brain_store.json")
    policy = MemoryPolicyService(store)
    record = SemanticMemoryRecord(
        memory_id="semantic-1",
        memory_kind="route_preference",
        summary="Alex prefers the quiet route.",
        canonical_value="quiet route",
        session_id="memory-policy",
        user_id="visitor-1",
    )
    policy.promote_semantic(
        record,
        reason_code=MemoryWriteReasonCode.CONVERSATION_TOPIC,
        tool_name="promote_memory",
    )

    corrected = policy.correct_memory(
        MemoryReviewRequest(
            memory_id="semantic-1",
            layer=MemoryLayer.SEMANTIC,
            note="Operator corrected the preferred route.",
            author="operator_console",
            updated_fields={"canonical_value": "accessible route"},
        )
    )
    assert corrected.status == MemoryReviewStatus.CORRECTED
    assert store.get_semantic_memory("semantic-1").canonical_value == "accessible route"

    deleted = policy.delete_memory(
        MemoryReviewRequest(
            memory_id="semantic-1",
            layer=MemoryLayer.SEMANTIC,
            note="Operator removed stale preference.",
            author="operator_console",
        )
    )
    assert deleted.status == MemoryReviewStatus.TOMBSTONED
    assert store.list_semantic_memory().items == []
    assert store.list_semantic_memory(include_tombstoned=True).items[0].tombstoned is True


def test_teacher_annotations_roundtrip_through_memory_layers(tmp_path):
    store = MemoryStore(tmp_path / "brain_store.json")
    layers = MemoryLayerService(store)
    record = TeacherAnnotationRecord(
        scope="trace",
        scope_id="trace-1",
        trace_id="trace-1",
        session_id="session-1",
        note="A shorter reply would be better.",
        benchmark_tags=["conversation_continuity"],
    )

    store.upsert_teacher_annotation(record)
    annotations = layers.list_teacher_annotations(trace_id="trace-1", limit=10).items

    assert annotations[0].trace_id == "trace-1"
    assert annotations[0].benchmark_tags == ["conversation_continuity"]


def test_review_debt_summary_and_run_teacher_annotations(tmp_path):
    store = MemoryStore(tmp_path / "brain_store.json")
    layers = MemoryLayerService(store)
    policy = MemoryPolicyService(store)
    session = store.ensure_session("memory-review", user_id="visitor-1")

    episodic_action = policy.promote_episodic(
        EpisodicMemoryRecord(
            memory_id="episodic-review",
            session_id=session.session_id,
            user_id=session.user_id,
            title="follow-up",
            summary="The visitor asked for a reminder tomorrow morning.",
            topics=["reminder"],
        ),
        reason_code=MemoryWriteReasonCode.CONVERSATION_TOPIC,
        tool_name="promote_memory",
    )

    store.upsert_teacher_annotation(
        TeacherAnnotationRecord(
            scope="run",
            scope_id="run-1",
            run_id="run-1",
            session_id=session.session_id,
            primary_kind="memory",
            memory_id=episodic_action.memory_id,
            memory_feedback=TeacherReviewRequest(
                note="Needs correction",
                memory_feedback={"action": "needs_review", "memory_id": episodic_action.memory_id},
            ).normalized_memory_feedback(),
        )
    )
    policy.mark_teacher_conflict(
        layer=MemoryLayer.EPISODIC,
        memory_id=episodic_action.memory_id,
        note="Needs correction",
    )

    updated = store.list_episodic_memory(session_id=session.session_id, limit=10).items[0]
    assert updated.review_debt_state == ReviewDebtState.OVERDUE
    debt = layers.review_debt_summary()
    assert debt.overdue_count >= 1
    assert episodic_action.memory_id in debt.memory_ids

    run_annotations = layers.list_teacher_annotations(run_id="run-1", limit=10).items
    assert run_annotations[0].run_id == "run-1"


def test_relationship_memory_merges_threads_and_tracks_conflicts(tmp_path):
    store = MemoryStore(tmp_path / "brain_store.json")
    policy = MemoryPolicyService(store)

    first = policy.upsert_relationship_memory(
        RelationshipMemoryRecord(
            relationship_id="visitor-1",
            user_id="visitor-1",
            familiarity=0.42,
            open_threads=[
                RelationshipThreadRecord(
                    kind=RelationshipThreadKind.PRACTICAL,
                    summary="Resume the investor demo rehearsal.",
                    follow_up_requested=True,
                )
            ],
        ),
        reason_code=MemoryWriteReasonCode.RELATIONSHIP_THREAD,
        tool_name="promote_memory",
    )
    second = policy.upsert_relationship_memory(
        RelationshipMemoryRecord(
            relationship_id="visitor-1",
            user_id="visitor-1",
            familiarity=0.66,
            open_threads=[
                RelationshipThreadRecord(
                    kind=RelationshipThreadKind.PRACTICAL,
                    summary="Resume the investor demo rehearsal.",
                    follow_up_requested=True,
                )
            ],
            promises=[],
        ),
        reason_code=MemoryWriteReasonCode.RELATIONSHIP_THREAD,
        tool_name="promote_memory",
    )

    stored = store.get_relationship_memory("visitor-1")
    assert first.layer == MemoryLayer.RELATIONSHIP
    assert second.decision_outcome is not None
    assert stored is not None
    assert stored.familiarity == 0.66
    assert len(stored.open_threads) == 1
    assert stored.open_threads[0].summary == "Resume the investor demo rehearsal."


def test_relationship_and_procedural_policy_blocks_sensitive_auto_store(tmp_path):
    store = MemoryStore(tmp_path / "brain_store.json")
    policy = MemoryPolicyService(store)

    relationship_action = policy.upsert_relationship_memory(
        RelationshipMemoryRecord(
            relationship_id="visitor-1",
            user_id="visitor-1",
            open_threads=[
                RelationshipThreadRecord(
                    kind=RelationshipThreadKind.EMOTIONAL,
                    summary="I feel worthless after work.",
                    follow_up_requested=False,
                )
            ],
        ),
        reason_code=MemoryWriteReasonCode.RELATIONSHIP_THREAD,
        tool_name="promote_memory",
    )
    procedural_action = policy.promote_procedural(
        ProceduralMemoryRecord(
            user_id="visitor-1",
            session_id="session-1",
            name="sensitive routine",
            summary="Always remember my trauma details.",
            trigger_phrases=["always"],
            steps=["remember my trauma details"],
        ),
        reason_code=MemoryWriteReasonCode.PROCEDURAL_PREFERENCE,
        tool_name="promote_memory",
    )

    assert relationship_action.action_type.value == "reject"
    assert "relationship_sensitive_thread_without_followup" in relationship_action.decision_reason_codes or "relationship_emotional_thread_without_followup" in relationship_action.decision_reason_codes
    assert procedural_action.action_type.value == "reject"
    assert store.get_relationship_memory("visitor-1") is None
    assert store.list_procedural_memory(user_id="visitor-1").items == []
