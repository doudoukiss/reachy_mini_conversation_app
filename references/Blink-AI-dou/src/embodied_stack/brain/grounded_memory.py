from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import timedelta
from uuid import uuid4

from embodied_stack.backends.embeddings import RetrievalDocument
from embodied_stack.brain.freshness import DEFAULT_FRESHNESS_POLICY, FreshnessPolicy
from embodied_stack.brain.memory import MemoryStore
from embodied_stack.brain.memory_policy import MemoryPolicyService
from embodied_stack.brain.venue_knowledge import VenueDocument, VenueKnowledge
from embodied_stack.brain.visual_query import looks_like_visual_query
from embodied_stack.demo.community_scripts import COMMUNITY_EVENTS, COMMUNITY_LOCATIONS
from embodied_stack.shared.contracts._common import MemoryWriteReasonCode
from embodied_stack.shared.contracts.brain import (
    CompanionNoteRecord,
    EpisodicMemoryRecord,
    MemoryPromotionRecord,
    ProceduralMemoryRecord,
    ReminderRecord,
    RelationshipMemoryRecord,
    RelationshipPromiseRecord,
    RelationshipThreadKind,
    RelationshipThreadRecord,
    RelationshipThreadStatus,
    RelationshipTopicRecord,
    SemanticMemoryRecord,
    SessionRecord,
    SessionDigestRecord,
    ToolInvocationRecord,
    UserMemoryRecord,
    utc_now,
)
from embodied_stack.shared.contracts.perception import (
    EmbodiedWorldModel,
    FactFreshness,
    PerceptionFactRecord,
    PerceptionObservationType,
    PerceptionSnapshotRecord,
    PerceptionTier,
    SceneClaimKind,
)


_TOKEN_RE = re.compile(r"[a-z0-9][a-z0-9_\-']+")
_STOPWORDS = {
    "a",
    "an",
    "and",
    "are",
    "at",
    "before",
    "can",
    "do",
    "for",
    "from",
    "i",
    "is",
    "it",
    "last",
    "me",
    "my",
    "of",
    "previous",
    "remember",
    "the",
    "time",
    "to",
    "we",
    "what",
    "where",
    "you",
}


@dataclass(frozen=True)
class WorkingMemorySnapshot:
    conversation_summary: str | None = None
    current_topic: str | None = None
    last_user_text: str | None = None
    session_memory: dict[str, str] = field(default_factory=dict)
    operator_notes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class RelationshipMemoryHit:
    memory_id: str
    layer: str
    summary: str
    ranking_reason: str
    ranking_score: float | None = None
    source_ref: str | None = None


@dataclass(frozen=True)
class MemoryContextSnapshot:
    working_memory: WorkingMemorySnapshot = field(default_factory=WorkingMemorySnapshot)
    profile_summary: str | None = None
    episodic_hits: list[EpisodicMemoryRecord] = field(default_factory=list)
    semantic_hits: list[SemanticMemoryRecord] = field(default_factory=list)
    relationship_summary: str | None = None
    relationship_hits: list[RelationshipMemoryHit] = field(default_factory=list)
    procedural_hits: list[ProceduralMemoryRecord] = field(default_factory=list)
    perception_facts: list[PerceptionFactRecord] = field(default_factory=list)


class GroundedMemoryService:
    """Compact, layered memory and fresh scene retrieval for grounded dialogue."""

    perception_snapshot_max_age_seconds: float = DEFAULT_FRESHNESS_POLICY.semantic_window.ttl_seconds
    minimum_fact_confidence: float = 0.6
    minimum_scene_presence_confidence: float = 0.5

    def __init__(
        self,
        *,
        memory_store: MemoryStore,
        venue_knowledge: VenueKnowledge,
        digest_interval_minutes: float = 10.0,
    ) -> None:
        self.memory_store = memory_store
        self.venue_knowledge = venue_knowledge
        self.digest_interval_minutes = digest_interval_minutes
        self.memory_policy = MemoryPolicyService(memory_store)
        self.freshness_policy: FreshnessPolicy = DEFAULT_FRESHNESS_POLICY

    def record_turn(
        self,
        *,
        session: SessionRecord,
        user_memory: UserMemoryRecord | None,
        trace_id: str,
        reply_text: str | None,
        intent: str | None,
        source_refs: list[str],
    ) -> list[MemoryPromotionRecord]:
        promotions: list[MemoryPromotionRecord] = []
        reminder = self._extract_reminder(
            session=session,
            user_memory=user_memory,
            trace_id=trace_id,
        )
        note = self._extract_note(
            session=session,
            user_memory=user_memory,
            trace_id=trace_id,
        )
        digest = self._maybe_write_session_digest(
            session=session,
            user_memory=user_memory,
            trace_id=trace_id,
        )

        if self._should_write_episodic_compaction(
            session=session,
            reply_text=reply_text,
            intent=intent,
            reminder=reminder,
            note=note,
            digest=digest,
        ):
            episodic = self._build_episodic_record(
                session=session,
                user_memory=user_memory,
                trace_id=trace_id,
                reply_text=reply_text,
                intent=intent,
                source_refs=source_refs,
            )
            promotions.append(
                self.memory_policy.promotion_from_action(
                    self.memory_policy.promote_episodic(
                        episodic,
                        trace_id=trace_id,
                        reason_code=MemoryWriteReasonCode.TURN_COMPACTION,
                        policy_basis="meaningful_turn_summary",
                    )
                )
            )

        for record in self._build_semantic_records(
            session=session,
            user_memory=user_memory,
            trace_id=trace_id,
            reply_text=reply_text,
            intent=intent,
            source_refs=source_refs,
        ):
            reason_code = {
                "conversation_topic": MemoryWriteReasonCode.CONVERSATION_TOPIC,
                "venue_location": MemoryWriteReasonCode.VENUE_LOCATION,
                "venue_event": MemoryWriteReasonCode.VENUE_EVENT,
            }.get(record.memory_kind, MemoryWriteReasonCode.AGENT_PROMOTION)
            promotions.append(
                self.memory_policy.promotion_from_action(
                    self.memory_policy.promote_semantic(
                        record,
                        trace_id=trace_id,
                        reason_code=reason_code,
                        policy_basis=f"semantic:{record.memory_kind}",
                    )
                )
            )
        if reminder is not None:
            promotions.append(
                self.memory_policy.promotion_from_action(
                    self.memory_policy.promote_episodic(
                        reminder,
                        trace_id=trace_id,
                        reason_code=MemoryWriteReasonCode.EXPLICIT_REMINDER_REQUEST,
                        policy_basis="explicit_reminder_request",
                    )
                )
            )

        if note is not None:
            promotions.append(
                self.memory_policy.promotion_from_action(
                    self.memory_policy.promote_episodic(
                        note,
                        trace_id=trace_id,
                        reason_code=MemoryWriteReasonCode.EXPLICIT_NOTE_CAPTURE,
                        policy_basis="explicit_note_capture",
                    )
                )
            )

        if digest is not None:
            promotions.append(
                self.memory_policy.promotion_from_action(
                    self.memory_policy.promote_episodic(
                        digest,
                        trace_id=trace_id,
                        reason_code=MemoryWriteReasonCode.SCHEDULED_COMPACTION,
                        policy_basis="scheduled_digest_compaction",
                    )
                )
            )
        relationship = self._build_relationship_memory(
            session=session,
            user_memory=user_memory,
            trace_id=trace_id,
            reminder=reminder,
            note=note,
            source_refs=source_refs,
        )
        if relationship is not None:
            promotions.append(
                self.memory_policy.promotion_from_action(
                    self.memory_policy.upsert_relationship_memory(
                        relationship,
                        trace_id=trace_id,
                        reason_code=(
                            MemoryWriteReasonCode.RELATIONSHIP_PROMISE
                            if relationship.promises
                            else MemoryWriteReasonCode.RELATIONSHIP_THREAD
                        ),
                        policy_basis="relationship_runtime",
                    )
                )
            )

        procedural = self._extract_procedural_memory(
            session=session,
            user_memory=user_memory,
            trace_id=trace_id,
            source_refs=source_refs,
        )
        if procedural is not None:
            promotions.append(
                self.memory_policy.promotion_from_action(
                    self.memory_policy.promote_procedural(
                        procedural,
                        trace_id=trace_id,
                        reason_code=MemoryWriteReasonCode.PROCEDURAL_PREFERENCE,
                        policy_basis="explicit_working_routine",
                    )
                )
            )
        return promotions

    def lookup_profile_memory(
        self,
        query: str,
        *,
        user_memory: UserMemoryRecord | None,
    ) -> ToolInvocationRecord | None:
        if user_memory is None or user_memory.tombstoned:
            return None
        lowered = query.lower().strip()
        if not self._looks_like_profile_query(lowered):
            return None

        summary = self._profile_summary(user_memory)
        if summary is None:
            return ToolInvocationRecord(
                tool_name="profile_memory_lookup",
                answer_text="I do not have any saved profile notes for you yet.",
                metadata={
                    "knowledge_source": "profile_memory",
                    "retrieval_backend": "profile_scan",
                    "source_refs": [f"profile:{user_memory.user_id}"],
                    "user_id": user_memory.user_id,
                    "review_status": user_memory.review_status.value,
                    "empty_profile": True,
                    "memory_layer": "profile",
                    "miss_reason": "no_profile_memory",
                },
                notes=["profile_memory_empty"],
            )
        return ToolInvocationRecord(
            tool_name="profile_memory_lookup",
            answer_text=summary,
            metadata={
                "knowledge_source": "profile_memory",
                "retrieval_backend": "profile_scan",
                "source_refs": [f"profile:{user_memory.user_id}"],
                "user_id": user_memory.user_id,
                "review_status": user_memory.review_status.value,
                "memory_layer": "profile",
                "memory_id": user_memory.user_id,
                "matched_summary": summary,
                "retrieval_reason": "profile_summary_present",
            },
            notes=["profile_memory_match"],
        )

    def lookup_prior_session(
        self,
        query: str,
        *,
        session: SessionRecord,
        user_memory: UserMemoryRecord | None,
    ) -> ToolInvocationRecord | None:
        if user_memory is None:
            return None
        lowered = query.lower().strip()
        if not self._looks_like_prior_session_query(lowered):
            return None

        candidates = [
            item
            for item in self.memory_store.list_episodic_memory(user_id=user_memory.user_id, limit=20).items
            if item.session_id != session.session_id
        ]
        ranked = self._rank_episodic_hits(lowered, candidates)
        if not ranked and candidates:
            ranked = sorted(candidates, key=lambda item: item.updated_at, reverse=True)
        if not ranked:
            return ToolInvocationRecord(
                tool_name="prior_session_lookup",
                answer_text="I do not have a prior session summary for that yet.",
                metadata={
                    "knowledge_source": "episodic_memory",
                    "retrieval_backend": "episodic_keyword",
                    "user_id": user_memory.user_id,
                    "source_refs": [],
                    "missing_prior_session": True,
                    "memory_layer": "episodic",
                    "miss_reason": "no_prior_session_match",
                },
                notes=["episodic_memory_missing"],
            )

        hit = ranked[0]
        return ToolInvocationRecord(
            tool_name="prior_session_lookup",
            answer_text=f"From a prior session, I remember {hit.summary}",
            metadata={
                "knowledge_source": "episodic_memory",
                "retrieval_backend": "episodic_keyword",
                "user_id": user_memory.user_id,
                "session_id": hit.session_id,
                "memory_id": hit.memory_id,
                "source_refs": hit.source_refs or [f"episodic:{hit.memory_id}"],
                "source_trace_ids": hit.source_trace_ids,
                "memory_layer": "episodic",
                "matched_summary": hit.summary,
                "retrieval_reason": "episodic_keyword_match",
            },
            notes=["episodic_memory_match"],
        )

    def lookup_recent_perception(
        self,
        query: str,
        *,
        world_model: EmbodiedWorldModel | None,
        latest_perception: PerceptionSnapshotRecord | None,
    ) -> ToolInvocationRecord | None:
        lowered = query.lower().strip()
        if not self._looks_like_scene_query(lowered):
            return None

        facts = self.recent_perception_facts(
            world_model=world_model,
            latest_perception=latest_perception,
            query=query,
        )
        if facts:
            source_refs = list(dict.fromkeys(item.source_ref for item in facts if item.source_ref))
            return ToolInvocationRecord(
                tool_name="perception_fact_lookup",
                answer_text=self._perception_answer(lowered, facts),
                metadata={
                    "knowledge_source": "perception_facts",
                    "retrieval_backend": "perception_context",
                    "source_refs": source_refs,
                    "fact_count": len(facts),
                    "limited_awareness": any(item.limited_awareness for item in facts),
                    "confidence": round(
                        sum(item.confidence for item in facts if item.confidence is not None)
                        / max(1, len([item for item in facts if item.confidence is not None])),
                        2,
                    )
                    if any(item.confidence is not None for item in facts)
                    else None,
                    "selected_candidates": [
                            {
                                "memory_id": item.fact_id,
                                "summary": item.label or item.detail or item.fact_type,
                                "reason": "perception_fact",
                                "score": item.confidence,
                                "source_refs": [item.source_ref] if item.source_ref else [],
                            }
                        for item in facts
                    ],
                },
                notes=["recent_perception_facts"],
            )
        if latest_perception is not None and latest_perception.limited_awareness and not self._snapshot_is_stale(latest_perception):
            cautious_facts = [
                item
                for item in self._snapshot_facts(latest_perception)
                if item.fact_type in {"people_count", "person_visibility", "engagement_estimate", "scene_summary"}
                and item.freshness not in {FactFreshness.STALE, FactFreshness.EXPIRED, FactFreshness.UNKNOWN}
                and item.claim_kind != SceneClaimKind.WATCHER_HINT
            ]
            if cautious_facts:
                cautious_answer = self._perception_answer(lowered, cautious_facts)
                return ToolInvocationRecord(
                    tool_name="perception_fact_lookup",
                    answer_text=(
                        "My visual situational awareness is limited right now, but I can cautiously report: "
                        f"{cautious_answer}"
                    ),
                    metadata={
                        "knowledge_source": "perception_facts",
                        "retrieval_backend": "perception_context",
                        "source_refs": list(dict.fromkeys(item.source_ref for item in cautious_facts if item.source_ref)),
                        "fact_count": len(cautious_facts),
                        "fresh": True,
                        "limited_awareness": True,
                        "snapshot_stale": False,
                        "selected_candidates": [
                            {
                                "memory_id": item.fact_id,
                                "summary": item.label or item.detail or item.fact_type,
                                "reason": "limited_awareness_fact",
                                "score": item.confidence,
                                "source_refs": [item.source_ref] if item.source_ref else [],
                            }
                            for item in cautious_facts
                        ],
                    },
                    notes=["limited_awareness_cautious_perception"],
                )

        return ToolInvocationRecord(
            tool_name="perception_fact_lookup",
            answer_text="My visual situational awareness is limited right now, so I do not have fresh visual facts for that.",
            metadata={
                "knowledge_source": "perception_facts",
                "retrieval_backend": "perception_context",
                "source_refs": [],
                "fresh": False,
                "limited_awareness": bool(latest_perception.limited_awareness) if latest_perception else False,
                "snapshot_stale": self._snapshot_is_stale(latest_perception) if latest_perception else False,
                "miss_reason": (
                    "stale_perception_context"
                    if latest_perception is not None and self._snapshot_is_stale(latest_perception)
                    else "perception_facts_missing"
                ),
            },
            notes=[
                "stale_perception_rejected"
                if latest_perception is not None and self._snapshot_is_stale(latest_perception)
                else "perception_facts_missing"
            ],
        )

    def lookup_venue_document(self, query: str) -> ToolInvocationRecord | None:
        best = self._best_document_hit(query)
        if best is None:
            return None
        return ToolInvocationRecord(
            tool_name="venue_doc_lookup",
            answer_text=self._document_snippet(best),
            metadata={
                "knowledge_source": "venue_document",
                "doc_id": best.doc_id,
                "source_refs": [best.source_ref],
            },
            notes=[f"venue_document_match:{best.doc_id}"],
        )

    def build_dynamic_retrieval_documents(
        self,
        *,
        session: SessionRecord,
        user_memory: UserMemoryRecord | None,
    ) -> list[RetrievalDocument]:
        documents: list[RetrievalDocument] = []
        if user_memory is not None:
            profile_summary = self._profile_summary(user_memory)
            if profile_summary:
                documents.append(
                    RetrievalDocument(
                        document_id=f"profile:{user_memory.user_id}",
                        tool_name="profile_memory_lookup",
                        text=profile_summary,
                        answer_text=profile_summary,
                        metadata={
                            "knowledge_source": "profile_memory",
                            "user_id": user_memory.user_id,
                            "source_refs": [f"profile:{user_memory.user_id}"],
                        },
                        notes=("semantic_profile_memory",),
                    )
                )
            prior_sessions = [
                item
                for item in self.memory_store.list_episodic_memory(user_id=user_memory.user_id, limit=12).items
                if item.session_id != session.session_id
            ]
            for record in prior_sessions[:6]:
                documents.append(
                    RetrievalDocument(
                        document_id=f"episodic:{record.memory_id}",
                        tool_name="prior_session_lookup",
                        text=" ".join(
                            part for part in [record.title, record.summary, *record.topics, record.last_user_text or ""] if part
                        ),
                        answer_text=f"From a prior session, I remember {record.summary}",
                        metadata={
                            "knowledge_source": "episodic_memory",
                            "session_id": record.session_id,
                            "memory_id": record.memory_id,
                            "source_refs": record.source_refs or [f"episodic:{record.memory_id}"],
                        },
                        notes=("semantic_prior_session",),
                    )
                )
            for record in self.memory_store.list_semantic_memory(user_id=user_memory.user_id, limit=12).items[:8]:
                documents.append(
                    RetrievalDocument(
                        document_id=f"semantic:{record.memory_id}",
                        tool_name="semantic_memory_lookup",
                        text=" ".join(part for part in [record.summary, record.canonical_value or "", *record.tags] if part),
                        answer_text=record.summary,
                        metadata={
                            "knowledge_source": "semantic_memory",
                            "memory_id": record.memory_id,
                            "source_refs": record.source_refs or [f"semantic:{record.memory_id}"],
                            "memory_kind": record.memory_kind,
                        },
                        notes=("semantic_memory_hit",),
                    )
                )
            relationship_memory = self.memory_store.get_relationship_memory(user_memory.user_id)
            if relationship_memory is not None and not relationship_memory.tombstoned:
                documents.append(
                    RetrievalDocument(
                        document_id=f"relationship:{relationship_memory.relationship_id}",
                        tool_name="search_memory",
                        text=self._relationship_summary(relationship_memory),
                        answer_text=self._relationship_summary(relationship_memory),
                        metadata={
                            "knowledge_source": "relationship_memory",
                            "memory_id": relationship_memory.relationship_id,
                            "source_refs": [f"relationship:{relationship_memory.relationship_id}"],
                        },
                        notes=("relationship_runtime",),
                    )
                )
            for record in self.memory_store.list_procedural_memory(user_id=user_memory.user_id, limit=10).items[:5]:
                documents.append(
                    RetrievalDocument(
                        document_id=f"procedural:{record.procedure_id}",
                        tool_name="search_memory",
                        text=" ".join(part for part in [record.name, record.summary, *record.trigger_phrases, *record.steps] if part),
                        answer_text=record.summary,
                        metadata={
                            "knowledge_source": "procedural_memory",
                            "memory_id": record.procedure_id,
                            "source_refs": record.source_refs or [f"procedural:{record.procedure_id}"],
                        },
                        notes=("procedural_memory",),
                    )
                )
        return documents

    def build_memory_context(
        self,
        query: str,
        *,
        session: SessionRecord,
        user_memory: UserMemoryRecord | None,
        world_model: EmbodiedWorldModel | None,
        latest_perception: PerceptionSnapshotRecord | None,
    ) -> MemoryContextSnapshot:
        lowered = query.lower().strip()
        working_memory = self._working_memory_snapshot(session)
        profile_summary = self._profile_summary_for_query(lowered, user_memory) if user_memory is not None else None
        episodic_hits: list[EpisodicMemoryRecord] = []
        semantic_hits: list[SemanticMemoryRecord] = []
        relationship_summary: str | None = None
        relationship_hits: list[RelationshipMemoryHit] = []
        procedural_hits: list[ProceduralMemoryRecord] = []
        if user_memory is not None:
            episodes = [
                item
                for item in self.memory_store.list_episodic_memory(user_id=user_memory.user_id, limit=12).items
                if item.session_id != session.session_id
            ]
            episodic_hits = self._rank_episodic_hits(lowered, episodes)[:3]
            if not episodic_hits and self._looks_like_prior_session_query(lowered):
                episodic_hits = sorted(episodes, key=lambda item: item.updated_at, reverse=True)[:3]
            semantics = self.memory_store.list_semantic_memory(user_id=user_memory.user_id, limit=20).items
            semantic_hits = self._rank_semantic_hits(lowered, semantics)[:4]
            relationship_memory = self.memory_store.get_relationship_memory(user_memory.user_id)
            if relationship_memory is not None and not relationship_memory.tombstoned:
                relationship_hits = self._rank_relationship_hits(lowered, relationship_memory)[:4]
                if self._relationship_context_needed(lowered) or relationship_hits:
                    relationship_summary = self._relationship_summary(relationship_memory)
            procedural_hits = self._rank_procedural_hits(
                lowered,
                self.memory_store.list_procedural_memory(user_id=user_memory.user_id, limit=20).items,
            )[:4]

        return MemoryContextSnapshot(
            working_memory=working_memory,
            profile_summary=profile_summary,
            episodic_hits=episodic_hits,
            semantic_hits=semantic_hits,
            relationship_summary=relationship_summary,
            relationship_hits=relationship_hits,
            procedural_hits=procedural_hits,
            perception_facts=self.recent_perception_facts(
                world_model=world_model,
                latest_perception=latest_perception,
                query=query,
            ),
        )

    def profile_memory_for_user_ids(self, user_ids: list[str]) -> list[UserMemoryRecord]:
        results: list[UserMemoryRecord] = []
        seen: set[str] = set()
        for user_id in user_ids:
            if not user_id or user_id in seen:
                continue
            seen.add(user_id)
            item = self.memory_store.get_user_memory(user_id)
            if item is not None:
                results.append(item)
        results.sort(key=lambda item: item.updated_at, reverse=True)
        return results

    def recent_perception_facts(
        self,
        *,
        world_model: EmbodiedWorldModel | None,
        latest_perception: PerceptionSnapshotRecord | None,
        query: str | None = None,
    ) -> list[PerceptionFactRecord]:
        facts: list[PerceptionFactRecord] = []
        lowered = (query or "").lower().strip()
        snapshot_is_fresh = latest_perception is not None and not self._snapshot_is_stale(latest_perception)
        fresh_limited_snapshot = snapshot_is_fresh and latest_perception is not None and latest_perception.limited_awareness
        if snapshot_is_fresh and latest_perception is not None:
            facts.extend(self._snapshot_facts(latest_perception))
        if world_model is not None and not fresh_limited_snapshot:
            facts.extend(self._world_model_facts(world_model))
        facts = self._dedupe_facts(facts)
        if not lowered:
            return facts[:6]
        return self._filter_facts_for_query(lowered, facts)

    def _build_episodic_record(
        self,
        *,
        session: SessionRecord,
        user_memory: UserMemoryRecord | None,
        trace_id: str,
        reply_text: str | None,
        intent: str | None,
        source_refs: list[str],
    ) -> EpisodicMemoryRecord:
        existing = self.memory_store.get_episodic_memory(session.session_id)
        trace_ids = self._merge_unique(existing.source_trace_ids if existing else [], [trace_id])
        refs = self._merge_unique(existing.source_refs if existing else [], source_refs)
        summary_parts = [session.conversation_summary or ""]
        if session.last_user_text:
            summary_parts.append(f"Latest visitor request: {session.last_user_text}.")
        if reply_text:
            summary_parts.append(f"Latest grounded reply: {reply_text}.")
        return EpisodicMemoryRecord(
            memory_id=session.session_id,
            session_id=session.session_id,
            user_id=user_memory.user_id if user_memory is not None else session.user_id,
            title=session.current_topic or intent or "conversation",
            summary=" ".join(part.strip() for part in summary_parts if part).strip() or "Grounded conversation recorded.",
            topics=self._session_topics(session, intent=intent),
            last_user_text=session.last_user_text,
            last_reply_text=reply_text or session.last_reply_text,
            source_trace_ids=trace_ids,
            source_refs=refs,
        )

    def _build_semantic_records(
        self,
        *,
        session: SessionRecord,
        user_memory: UserMemoryRecord | None,
        trace_id: str,
        reply_text: str | None,
        intent: str | None,
        source_refs: list[str],
    ) -> list[SemanticMemoryRecord]:
        results: list[SemanticMemoryRecord] = []
        refs = list(source_refs)
        if session.current_topic and session.current_topic not in {"conversation", "greeting", "introduction"}:
            existing = self.memory_store.get_semantic_memory(f"semantic-topic:{session.session_id}")
            results.append(
                SemanticMemoryRecord(
                    memory_id=f"semantic-topic:{session.session_id}",
                    memory_kind="conversation_topic",
                    summary=f"The conversation focused on {session.current_topic}.",
                    canonical_value=session.current_topic,
                    session_id=session.session_id,
                    user_id=user_memory.user_id if user_memory is not None else session.user_id,
                    tags=[session.current_topic, intent or session.current_topic],
                    source_trace_ids=self._merge_unique(existing.source_trace_ids if existing else [], [trace_id]),
                    source_refs=self._merge_unique(existing.source_refs if existing else [], refs),
                )
            )
        if last_location := session.session_memory.get("last_location"):
            location = COMMUNITY_LOCATIONS.get(last_location)
            label = location.title if location is not None else last_location.replace("_", " ")
            existing = self.memory_store.get_semantic_memory(f"semantic-location:{session.session_id}")
            results.append(
                SemanticMemoryRecord(
                    memory_id=f"semantic-location:{session.session_id}",
                    memory_kind="venue_location",
                    summary=f"The visitor asked about directions to {label}.",
                    canonical_value=last_location,
                    session_id=session.session_id,
                    user_id=user_memory.user_id if user_memory is not None else session.user_id,
                    tags=["wayfinding", last_location],
                    source_trace_ids=self._merge_unique(existing.source_trace_ids if existing else [], [trace_id]),
                    source_refs=self._merge_unique(existing.source_refs if existing else [], refs),
                )
            )
        if last_event_id := session.session_memory.get("last_event_id"):
            event = next((item for item in COMMUNITY_EVENTS if item.event_id == last_event_id), None)
            label = event.title if event is not None else last_event_id.replace("_", " ")
            existing = self.memory_store.get_semantic_memory(f"semantic-event:{session.session_id}")
            results.append(
                SemanticMemoryRecord(
                    memory_id=f"semantic-event:{session.session_id}",
                    memory_kind="venue_event",
                    summary=f"The visitor asked about {label}.",
                    canonical_value=last_event_id,
                    session_id=session.session_id,
                    user_id=user_memory.user_id if user_memory is not None else session.user_id,
                    tags=["events", last_event_id],
                    source_trace_ids=self._merge_unique(existing.source_trace_ids if existing else [], [trace_id]),
                    source_refs=self._merge_unique(existing.source_refs if existing else [], refs),
                )
            )
        return results

    def _profile_summary(self, user_memory: UserMemoryRecord | None) -> str | None:
        if user_memory is None or user_memory.tombstoned:
            return None
        parts: list[str] = []
        if user_memory.display_name:
            parts.append(f"I remember you as {user_memory.display_name}.")
        if user_memory.preferences:
            preference_text = ", ".join(f"{key.replace('_', ' ')}: {value}" for key, value in sorted(user_memory.preferences.items()))
            parts.append(f"Your saved preferences are {preference_text}.")
        remembered_facts = {
            key: value for key, value in user_memory.facts.items() if key != "remembered_name"
        }
        if remembered_facts:
            fact_text = ", ".join(f"{key.replace('_', ' ')}: {value}" for key, value in sorted(remembered_facts.items()))
            parts.append(f"Known facts are {fact_text}.")
        if user_memory.interests:
            parts.append(f"Your interests include {', '.join(user_memory.interests)}.")
        return " ".join(parts).strip() or None

    def _profile_summary_for_query(self, query: str, user_memory: UserMemoryRecord | None) -> str | None:
        summary = self._profile_summary(user_memory)
        if summary is None or user_memory is None:
            return None
        if self._looks_like_profile_query(query) or self._looks_like_prior_session_query(query):
            return summary
        query_tokens = {item for item in _TOKEN_RE.findall(query.lower()) if item not in _STOPWORDS and len(item) >= 4}
        if query_tokens and any(token in summary.lower() for token in query_tokens):
            return summary
        if self._looks_like_style_query(query):
            return summary
        return None

    def _working_memory_snapshot(self, session: SessionRecord) -> WorkingMemorySnapshot:
        return WorkingMemorySnapshot(
            conversation_summary=session.conversation_summary,
            current_topic=session.current_topic,
            last_user_text=session.last_user_text,
            session_memory=dict(session.session_memory),
            operator_notes=[note.text for note in session.operator_notes[-3:]],
        )

    def _should_write_episodic_compaction(
        self,
        *,
        session: SessionRecord,
        reply_text: str | None,
        intent: str | None,
        reminder: ReminderRecord | None,
        note: CompanionNoteRecord | None,
        digest: SessionDigestRecord | None,
    ) -> bool:
        if reminder is not None or note is not None or digest is not None:
            return True
        lowered = (session.last_user_text or "").strip().lower()
        if not lowered:
            return False
        if intent in {"greeting", "small_talk"} and len(lowered) < 40:
            return False
        if lowered in {"thanks", "thank you", "ok", "okay", "hello", "hi"}:
            return False
        return bool(session.conversation_summary or session.current_topic or reply_text)

    def _build_relationship_memory(
        self,
        *,
        session: SessionRecord,
        user_memory: UserMemoryRecord | None,
        trace_id: str,
        reminder: ReminderRecord | None,
        note: CompanionNoteRecord | None,
        source_refs: list[str],
    ) -> RelationshipMemoryRecord | None:
        if user_memory is None:
            return None
        existing = self.memory_store.get_relationship_memory(user_memory.user_id)
        now = utc_now()
        recurring_topics = self._relationship_topics_for_session(session=session, source_refs=source_refs)
        open_threads = self._relationship_threads_for_turn(
            session=session,
            trace_id=trace_id,
            reminder=reminder,
            note=note,
            source_refs=source_refs,
        )
        promises = self._relationship_promises_for_turn(
            session=session,
            trace_id=trace_id,
            reminder=reminder,
            source_refs=source_refs,
        )
        preferred_style = user_memory.relationship_profile.model_copy(deep=True)
        has_style = bool(
            preferred_style.greeting_preference
            or preferred_style.planning_style
            or preferred_style.tone_preferences
            or preferred_style.interaction_boundaries
            or preferred_style.continuity_preferences
        )
        familiarity = self._familiarity_for_user(user_memory=user_memory, existing=existing)
        if not (recurring_topics or open_threads or promises or has_style or familiarity > 0.0):
            return None
        return RelationshipMemoryRecord(
            relationship_id=user_memory.user_id,
            user_id=user_memory.user_id,
            familiarity=familiarity,
            preferred_style=preferred_style,
            recurring_topics=recurring_topics,
            open_threads=open_threads,
            promises=promises,
            last_session_id=session.session_id,
            provenance_refs=list(dict.fromkeys([*source_refs, f"profile:{user_memory.user_id}"])),
            created_at=existing.created_at if existing is not None else now,
            updated_at=now,
        )

    def _relationship_topics_for_session(
        self,
        *,
        session: SessionRecord,
        source_refs: list[str],
    ) -> list[RelationshipTopicRecord]:
        topics: list[str] = []
        if session.current_topic and session.current_topic not in {"conversation", "greeting"}:
            topics.append(session.current_topic)
        for item in self._session_topics(session, intent=None):
            if item not in topics:
                topics.append(item)
        return [
            RelationshipTopicRecord(topic=topic, mention_count=1, source_refs=list(source_refs))
            for topic in topics[:4]
        ]

    def _relationship_threads_for_turn(
        self,
        *,
        session: SessionRecord,
        trace_id: str,
        reminder: ReminderRecord | None,
        note: CompanionNoteRecord | None,
        source_refs: list[str],
    ) -> list[RelationshipThreadRecord]:
        results: list[RelationshipThreadRecord] = []
        if reminder is not None:
            results.append(
                RelationshipThreadRecord(
                    kind=RelationshipThreadKind.PRACTICAL,
                    summary=self._clean_follow_up_summary(reminder.reminder_text),
                    topic=session.current_topic,
                    follow_up_requested=True,
                    source_trace_ids=[trace_id],
                    source_refs=list(source_refs),
                    last_session_id=session.session_id,
                )
            )
        lowered = (session.last_user_text or "").lower().strip()
        if lowered and self._looks_like_follow_up_request(lowered):
            summary = self._relationship_thread_summary(session.last_user_text or "", fallback=session.conversation_summary)
            if summary:
                results.append(
                    RelationshipThreadRecord(
                        kind=(
                            RelationshipThreadKind.EMOTIONAL
                            if self._looks_like_emotional_thread(lowered)
                            else RelationshipThreadKind.PRACTICAL
                        ),
                        summary=summary,
                        topic=session.current_topic,
                        follow_up_requested=True,
                        source_trace_ids=[trace_id],
                        source_refs=list(source_refs),
                        last_session_id=session.session_id,
                    )
                )
        elif note is not None and self._looks_like_emotional_thread(note.content.lower()):
            results.append(
                RelationshipThreadRecord(
                    kind=RelationshipThreadKind.EMOTIONAL,
                    summary=note.content,
                    topic=session.current_topic,
                    follow_up_requested=False,
                    source_trace_ids=[trace_id],
                    source_refs=list(source_refs),
                    last_session_id=session.session_id,
                )
            )
        return results

    def _relationship_promises_for_turn(
        self,
        *,
        session: SessionRecord,
        trace_id: str,
        reminder: ReminderRecord | None,
        source_refs: list[str],
    ) -> list[RelationshipPromiseRecord]:
        if reminder is None:
            return []
        return [
            RelationshipPromiseRecord(
                summary=f"Follow up on: {self._clean_follow_up_summary(reminder.reminder_text)}",
                due_at=reminder.due_at,
                source_trace_ids=[trace_id],
                source_refs=list(source_refs),
            )
        ]

    def _relationship_thread_summary(self, text: str, *, fallback: str | None) -> str | None:
        cleaned = text.strip(" .,!?:;")
        if len(cleaned) < 12:
            return fallback
        return cleaned[:180]

    def _clean_follow_up_summary(self, text: str) -> str:
        cleaned = text.strip(" .,!?:;")
        for marker in (" and let's ", " and let us ", " and then ", " then "):
            if marker in cleaned.lower():
                index = cleaned.lower().find(marker)
                if index > 0:
                    cleaned = cleaned[:index]
                    break
        return cleaned.strip(" .,!?:;")

    def _familiarity_for_user(
        self,
        *,
        user_memory: UserMemoryRecord,
        existing: RelationshipMemoryRecord | None,
    ) -> float:
        visits = max(user_memory.visit_count, 1)
        baseline = min(0.85, 0.18 + (visits * 0.12))
        if existing is None:
            return round(baseline, 3)
        return round(min(1.0, max(existing.familiarity, baseline)), 3)

    def _relationship_summary(self, record: RelationshipMemoryRecord) -> str:
        open_threads = [item.summary for item in record.open_threads if item.status == RelationshipThreadStatus.OPEN][:2]
        promises = [item.summary for item in record.promises if item.status.value == "open"][:2]
        recurring_topics = ", ".join(item.topic for item in record.recurring_topics[:3]) or "none"
        style_bits = list(
            dict.fromkeys(
                [
                    *(record.preferred_style.tone_preferences or []),
                    *(record.preferred_style.interaction_boundaries or []),
                    *(record.preferred_style.continuity_preferences or []),
                ]
            )
        )
        style = ", ".join(style_bits[:4]) or "none"
        return (
            f"familiarity={record.familiarity:.2f}; "
            f"topics={recurring_topics}; "
            f"open_threads={'; '.join(open_threads) or 'none'}; "
            f"promises={'; '.join(promises) or 'none'}; "
            f"style={style}"
        )

    def _rank_relationship_hits(
        self,
        query: str,
        record: RelationshipMemoryRecord,
    ) -> list[RelationshipMemoryHit]:
        hits: list[RelationshipMemoryHit] = []
        for thread in record.open_threads:
            if thread.status != RelationshipThreadStatus.OPEN and not self._looks_like_follow_up_request(query):
                continue
            score = self._score_text(query, " ".join(part for part in [thread.summary, thread.topic or ""] if part))
            score *= self._freshness_weight(thread.updated_at, half_life_days=5.0 if thread.kind.value == "emotional" else 14.0)
            if score <= 0 and not self._relationship_context_needed(query):
                continue
            hits.append(
                RelationshipMemoryHit(
                    memory_id=thread.thread_id,
                    layer="relationship",
                    summary=thread.summary,
                    ranking_reason="relationship_open_thread",
                    ranking_score=round(min(1.0, score or 0.5), 3),
                    source_ref=(thread.source_refs[0] if thread.source_refs else None),
                )
            )
        for promise in record.promises:
            if promise.status.value != "open":
                continue
            score = self._score_text(query, promise.summary) * self._freshness_weight(promise.updated_at, half_life_days=14.0)
            if score <= 0 and not self._looks_like_follow_up_request(query):
                continue
            hits.append(
                RelationshipMemoryHit(
                    memory_id=promise.promise_id,
                    layer="relationship",
                    summary=promise.summary,
                    ranking_reason="relationship_promise",
                    ranking_score=round(min(1.0, score or 0.45), 3),
                    source_ref=(promise.source_refs[0] if promise.source_refs else None),
                )
            )
        for topic in record.recurring_topics:
            score = self._score_text(query, topic.topic) * max(0.4, min(1.0, topic.mention_count / 3))
            if score <= 0:
                continue
            hits.append(
                RelationshipMemoryHit(
                    memory_id=f"{record.relationship_id}:{topic.topic}",
                    layer="relationship",
                    summary=f"Recurring topic: {topic.topic}",
                    ranking_reason="relationship_recurring_topic",
                    ranking_score=round(min(1.0, score), 3),
                    source_ref=(topic.source_refs[0] if topic.source_refs else None),
                )
            )
        hits.sort(key=lambda item: item.ranking_score or 0.0, reverse=True)
        return hits

    def _rank_procedural_hits(
        self,
        query: str,
        records: list[ProceduralMemoryRecord],
    ) -> list[ProceduralMemoryRecord]:
        ranked = [
            (
                self._score_text(query, " ".join(part for part in [record.name, record.summary, *record.trigger_phrases, *record.steps] if part))
                * self._freshness_weight(record.updated_at, half_life_days=60.0),
                record,
            )
            for record in records
            if record.enabled and not record.tombstoned
        ]
        filtered = [record for score, record in ranked if score > 0.0 or self._looks_like_style_query(query)]
        filtered.sort(key=lambda item: item.updated_at, reverse=True)
        if filtered:
            filtered.sort(
                key=lambda item: self._score_text(query, f"{item.name} {item.summary} {' '.join(item.trigger_phrases)}")
                * self._freshness_weight(item.updated_at, half_life_days=60.0),
                reverse=True,
            )
        return filtered

    def _extract_procedural_memory(
        self,
        *,
        session: SessionRecord,
        user_memory: UserMemoryRecord | None,
        trace_id: str,
        source_refs: list[str],
    ) -> ProceduralMemoryRecord | None:
        text = (session.last_user_text or "").strip()
        lowered = text.lower()
        if not lowered:
            return None
        trigger: str | None = None
        instruction: str | None = None
        if match := re.search(r"(?:when i ask(?: you)? to|if i ask(?: you)? to)\s+(.+?),\s*(.+)", lowered):
            trigger = match.group(1).strip(" .,!?:;")
            instruction = match.group(2).strip(" .,!?:;")
        elif match := re.search(r"(?:always|please always)\s+(.+)", lowered):
            trigger = session.current_topic or "general"
            instruction = match.group(1).strip(" .,!?:;")
        elif match := re.search(r"(?:for planning|when we plan)\s*,?\s*(.+)", lowered):
            trigger = "planning"
            instruction = match.group(1).strip(" .,!?:;")
        if not trigger or not instruction:
            return None
        return ProceduralMemoryRecord(
            user_id=user_memory.user_id if user_memory is not None else session.user_id,
            session_id=session.session_id,
            name=f"{trigger} routine",
            summary=instruction,
            trigger_phrases=[trigger],
            steps=[instruction],
            source_trace_ids=[trace_id],
            source_refs=list(source_refs),
        )

    def _relationship_context_needed(self, query: str) -> bool:
        return (
            self._looks_like_follow_up_request(query)
            or self._looks_like_prior_session_query(query)
            or self._looks_like_style_query(query)
            or any(phrase in query for phrase in ("resume", "pick up", "left off", "unfinished", "open thread"))
        )

    def _looks_like_style_query(self, lowered: str) -> bool:
        return any(
            phrase in lowered
            for phrase in (
                "be brief",
                "be direct",
                "tone",
                "style",
                "how should we work",
                "one step at a time",
            )
        )

    def _looks_like_follow_up_request(self, lowered: str) -> bool:
        return any(
            phrase in lowered
            for phrase in (
                "follow up",
                "come back to",
                "resume",
                "pick up where we left off",
                "unfinished",
                "later",
                "tomorrow",
                "check back",
                "remind me",
            )
        )

    def _looks_like_emotional_thread(self, lowered: str) -> bool:
        return any(
            phrase in lowered
            for phrase in (
                "i feel",
                "i'm feeling",
                "i am feeling",
                "i'm worried",
                "i am worried",
                "stressed",
                "anxious",
                "upset",
            )
        )

    def _freshness_weight(self, updated_at, *, half_life_days: float) -> float:
        age = max(0.0, (utc_now() - updated_at).total_seconds())
        half_life_seconds = max(1.0, half_life_days * 86400.0)
        return max(0.15, 1.0 / (1.0 + (age / half_life_seconds)))

    def _rank_episodic_hits(self, query: str, records: list[EpisodicMemoryRecord]) -> list[EpisodicMemoryRecord]:
        ranked = [
            (
                self._score_text(
                    query,
                    " ".join(
                        part for part in [record.title, record.summary, *record.topics, record.last_user_text or "", record.last_reply_text or ""] if part
                    ),
                )
                * self._freshness_weight(record.updated_at, half_life_days=7.0),
                record,
            )
            for record in records
        ]
        filtered = [item for score, item in ranked if score > 0.0]
        filtered.sort(key=lambda item: item.updated_at, reverse=True)
        if filtered:
            filtered.sort(
                key=lambda item: self._score_text(query, f"{item.title} {item.summary}")
                * self._freshness_weight(item.updated_at, half_life_days=7.0),
                reverse=True,
            )
        return filtered

    def _rank_semantic_hits(self, query: str, records: list[SemanticMemoryRecord]) -> list[SemanticMemoryRecord]:
        ranked = [
            (
                self._score_text(query, " ".join(part for part in [record.summary, record.canonical_value or "", *record.tags] if part))
                * self._freshness_weight(record.updated_at, half_life_days=30.0),
                record,
            )
            for record in records
        ]
        filtered = [item for score, item in ranked if score > 0.0]
        filtered.sort(key=lambda item: item.updated_at, reverse=True)
        if filtered:
            filtered.sort(
                key=lambda item: self._score_text(query, f"{item.summary} {item.canonical_value or ''} {' '.join(item.tags)}")
                * self._freshness_weight(item.updated_at, half_life_days=30.0),
                reverse=True,
            )
        return filtered

    def _snapshot_facts(self, snapshot: PerceptionSnapshotRecord) -> list[PerceptionFactRecord]:
        facts: list[PerceptionFactRecord] = []
        source_ref = snapshot.source_frame.fixture_path or snapshot.source_frame.file_name
        observed_at = snapshot.source_frame.captured_at or snapshot.created_at
        snapshot_claim_kind = self._claim_kind_for_snapshot(snapshot)
        freshness = self._freshness_for(
            observed_at=observed_at,
            expires_at=None,
            claim_kind=snapshot_claim_kind,
        )
        grounding_eligible = self._grounding_eligible(
            claim_kind=snapshot_claim_kind,
            freshness=freshness,
            limited_awareness=snapshot.limited_awareness,
            source_tier=snapshot.tier,
        )
        if snapshot.scene_summary:
            facts.append(
                PerceptionFactRecord(
                    fact_type="scene_summary",
                    label="scene_summary",
                    detail=snapshot.scene_summary,
                    claim_kind=snapshot_claim_kind,
                    quality_class=self._quality_class(snapshot_claim_kind, snapshot),
                    observed_at=observed_at,
                    source_ref=source_ref,
                    limited_awareness=snapshot.limited_awareness,
                    freshness=freshness,
                    source_tier=snapshot.tier,
                    uncertain=snapshot.limited_awareness,
                    provenance=[source_ref] if source_ref else [],
                    grounding_eligible=grounding_eligible,
                )
            )
        for observation in snapshot.observations:
            confidence = observation.confidence.score
            claim_kind = observation.claim_kind or snapshot_claim_kind
            if observation.observation_type == PerceptionObservationType.PEOPLE_COUNT and observation.number_value is not None:
                if confidence < self.minimum_scene_presence_confidence:
                    continue
                facts.append(
                    PerceptionFactRecord(
                        fact_type="people_count",
                        label="people_in_view",
                        detail=str(int(observation.number_value)),
                        confidence=confidence,
                        claim_kind=claim_kind,
                        quality_class=observation.quality_class,
                        observed_at=observed_at,
                        source_ref=source_ref,
                        limited_awareness=snapshot.limited_awareness,
                        freshness=freshness,
                        source_tier=snapshot.tier,
                        uncertain=snapshot.limited_awareness,
                        provenance=[source_ref] if source_ref else [],
                        grounding_eligible=self._grounding_eligible(
                            claim_kind=claim_kind,
                            freshness=freshness,
                            limited_awareness=snapshot.limited_awareness,
                            source_tier=snapshot.tier,
                            allow_watcher_presence=True,
                        ),
                    )
                )
                continue
            if observation.observation_type == PerceptionObservationType.PERSON_VISIBILITY and observation.bool_value is not None:
                if confidence < self.minimum_scene_presence_confidence:
                    continue
                facts.append(
                    PerceptionFactRecord(
                        fact_type="person_visibility",
                        label="person_visible" if observation.bool_value else "person_not_visible",
                        detail="true" if observation.bool_value else "false",
                        confidence=confidence,
                        claim_kind=claim_kind,
                        quality_class=observation.quality_class,
                        observed_at=observed_at,
                        source_ref=source_ref,
                        limited_awareness=snapshot.limited_awareness,
                        freshness=freshness,
                        source_tier=snapshot.tier,
                        uncertain=snapshot.limited_awareness,
                        provenance=[source_ref] if source_ref else [],
                        grounding_eligible=self._grounding_eligible(
                            claim_kind=claim_kind,
                            freshness=freshness,
                            limited_awareness=snapshot.limited_awareness,
                            source_tier=snapshot.tier,
                            allow_watcher_presence=True,
                        ),
                    )
                )
                continue
            if observation.observation_type == PerceptionObservationType.ENGAGEMENT_ESTIMATE and observation.text_value:
                if confidence < self.minimum_scene_presence_confidence:
                    continue
                facts.append(
                    PerceptionFactRecord(
                        fact_type="engagement_estimate",
                        label=observation.text_value,
                        confidence=confidence,
                        claim_kind=claim_kind,
                        quality_class=observation.quality_class,
                        observed_at=observed_at,
                        source_ref=source_ref,
                        limited_awareness=snapshot.limited_awareness,
                        freshness=freshness,
                        source_tier=snapshot.tier,
                        uncertain=snapshot.limited_awareness,
                        provenance=[source_ref] if source_ref else [],
                        grounding_eligible=self._grounding_eligible(
                            claim_kind=claim_kind,
                            freshness=freshness,
                            limited_awareness=snapshot.limited_awareness,
                            source_tier=snapshot.tier,
                            allow_watcher_presence=True,
                        ),
                    )
                )
                continue
            if confidence < self.minimum_fact_confidence:
                continue
            if observation.observation_type == PerceptionObservationType.VISIBLE_TEXT and observation.text_value:
                fact_freshness = self._freshness_for(
                    observed_at=observation.source_frame.captured_at or observed_at,
                    expires_at=None,
                    claim_kind=claim_kind,
                )
                facts.append(
                    PerceptionFactRecord(
                        fact_type="visible_text",
                        label=observation.text_value,
                        confidence=confidence,
                        claim_kind=claim_kind,
                        quality_class=observation.quality_class,
                        observed_at=observation.source_frame.captured_at or observed_at,
                        source_ref=source_ref,
                        limited_awareness=snapshot.limited_awareness,
                        freshness=fact_freshness,
                        source_tier=snapshot.tier,
                        uncertain=snapshot.limited_awareness,
                        provenance=[source_ref] if source_ref else [],
                        grounding_eligible=self._grounding_eligible(
                            claim_kind=claim_kind,
                            freshness=fact_freshness,
                            limited_awareness=snapshot.limited_awareness,
                            source_tier=snapshot.tier,
                        ),
                    )
                )
            elif observation.observation_type == PerceptionObservationType.LOCATION_ANCHOR and observation.text_value:
                fact_freshness = self._freshness_for(
                    observed_at=observation.source_frame.captured_at or observed_at,
                    expires_at=None,
                    claim_kind=claim_kind,
                )
                facts.append(
                    PerceptionFactRecord(
                        fact_type="location_anchor",
                        label=observation.text_value,
                        confidence=confidence,
                        claim_kind=claim_kind,
                        quality_class=observation.quality_class,
                        observed_at=observation.source_frame.captured_at or observed_at,
                        source_ref=source_ref,
                        limited_awareness=snapshot.limited_awareness,
                        freshness=fact_freshness,
                        source_tier=snapshot.tier,
                        uncertain=snapshot.limited_awareness,
                        provenance=[source_ref] if source_ref else [],
                        grounding_eligible=self._grounding_eligible(
                            claim_kind=claim_kind,
                            freshness=fact_freshness,
                            limited_awareness=snapshot.limited_awareness,
                            source_tier=snapshot.tier,
                        ),
                    )
                )
            elif observation.observation_type == PerceptionObservationType.NAMED_OBJECT and observation.text_value:
                fact_freshness = self._freshness_for(
                    observed_at=observation.source_frame.captured_at or observed_at,
                    expires_at=None,
                    claim_kind=claim_kind,
                )
                facts.append(
                    PerceptionFactRecord(
                        fact_type="named_object",
                        label=observation.text_value,
                        confidence=confidence,
                        claim_kind=claim_kind,
                        quality_class=observation.quality_class,
                        observed_at=observation.source_frame.captured_at or observed_at,
                        source_ref=source_ref,
                        limited_awareness=snapshot.limited_awareness,
                        freshness=fact_freshness,
                        source_tier=snapshot.tier,
                        uncertain=snapshot.limited_awareness,
                        provenance=[source_ref] if source_ref else [],
                        grounding_eligible=self._grounding_eligible(
                            claim_kind=claim_kind,
                            freshness=fact_freshness,
                            limited_awareness=snapshot.limited_awareness,
                            source_tier=snapshot.tier,
                        ),
                    )
                )
            elif observation.observation_type == PerceptionObservationType.PARTICIPANT_ATTRIBUTE and observation.text_value:
                if not observation.justification:
                    continue
                fact_freshness = self._freshness_for(
                    observed_at=observation.source_frame.captured_at or observed_at,
                    expires_at=None,
                    claim_kind=claim_kind,
                )
                facts.append(
                    PerceptionFactRecord(
                        fact_type="participant_attribute",
                        label=observation.text_value,
                        confidence=confidence,
                        claim_kind=claim_kind,
                        quality_class=observation.quality_class,
                        justification=observation.justification,
                        observed_at=observation.source_frame.captured_at or observed_at,
                        source_ref=source_ref,
                        limited_awareness=snapshot.limited_awareness,
                        freshness=fact_freshness,
                        source_tier=snapshot.tier,
                        uncertain=snapshot.limited_awareness,
                        provenance=[source_ref] if source_ref else [],
                        grounding_eligible=self._grounding_eligible(
                            claim_kind=claim_kind,
                            freshness=fact_freshness,
                            limited_awareness=snapshot.limited_awareness,
                            source_tier=snapshot.tier,
                        ),
                    )
                )
        return facts

    def _world_model_facts(self, world_model: EmbodiedWorldModel) -> list[PerceptionFactRecord]:
        facts: list[PerceptionFactRecord] = []
        now = utc_now()
        if world_model.active_participants_in_view:
            facts.append(
                PerceptionFactRecord(
                    fact_type="people_count",
                    label="people_in_view",
                    detail=str(len(world_model.active_participants_in_view)),
                    confidence=world_model.engagement_confidence.score,
                    claim_kind=SceneClaimKind.WATCHER_HINT,
                    observed_at=world_model.last_perception_at,
                    limited_awareness=world_model.perception_limited_awareness,
                    freshness=world_model.scene_freshness,
                    source_tier=PerceptionTier.WATCHER,
                    uncertain=world_model.perception_limited_awareness,
                    provenance=["world_model:active_participants"],
                    grounding_eligible=self._grounding_eligible(
                        claim_kind=SceneClaimKind.WATCHER_HINT,
                        freshness=world_model.scene_freshness,
                        limited_awareness=world_model.perception_limited_awareness,
                        source_tier=PerceptionTier.WATCHER,
                        allow_watcher_presence=True,
                    ),
                )
            )
        if (
            world_model.engagement_state.value != "unknown"
            and world_model.engagement_observed_at is not None
            and (world_model.engagement_expires_at is None or world_model.engagement_expires_at >= now)
        ):
            facts.append(
                PerceptionFactRecord(
                    fact_type="engagement_state",
                    label=world_model.engagement_state.value,
                    confidence=world_model.engagement_confidence.score,
                    claim_kind=SceneClaimKind.WATCHER_HINT,
                    observed_at=world_model.engagement_observed_at,
                    expires_at=world_model.engagement_expires_at,
                    limited_awareness=world_model.perception_limited_awareness,
                    freshness=self._freshness_for(
                        observed_at=world_model.engagement_observed_at,
                        expires_at=world_model.engagement_expires_at,
                        claim_kind=SceneClaimKind.WATCHER_HINT,
                    ),
                    source_tier=PerceptionTier.WATCHER,
                    uncertain=world_model.perception_limited_awareness,
                    provenance=["world_model:engagement"],
                    grounding_eligible=self._grounding_eligible(
                        claim_kind=SceneClaimKind.WATCHER_HINT,
                        freshness=self._freshness_for(
                            observed_at=world_model.engagement_observed_at,
                            expires_at=world_model.engagement_expires_at,
                            claim_kind=SceneClaimKind.WATCHER_HINT,
                        ),
                        limited_awareness=world_model.perception_limited_awareness,
                        source_tier=PerceptionTier.WATCHER,
                        allow_watcher_presence=True,
                    ),
                )
            )
        if (
            world_model.attention_target is not None
            and (world_model.attention_target.expires_at is None or world_model.attention_target.expires_at >= now)
        ):
            facts.append(
                PerceptionFactRecord(
                    fact_type="attention_target",
                    label=world_model.attention_target.target_label or "attention_target",
                    confidence=world_model.attention_target.confidence.score,
                    claim_kind=world_model.attention_target.claim_kind,
                    quality_class=world_model.attention_target.quality_class,
                    observed_at=world_model.attention_target.observed_at,
                    expires_at=world_model.attention_target.expires_at,
                    limited_awareness=world_model.perception_limited_awareness,
                    freshness=world_model.attention_target.freshness,
                    source_tier=world_model.attention_target.source_tier,
                    uncertain=world_model.perception_limited_awareness,
                    provenance=list(world_model.attention_target.provenance),
                    grounding_eligible=self._grounding_eligible(
                        claim_kind=world_model.attention_target.claim_kind,
                        freshness=world_model.attention_target.freshness,
                        limited_awareness=world_model.perception_limited_awareness,
                        source_tier=world_model.attention_target.source_tier,
                        allow_watcher_presence=True,
                    ),
                )
            )
        for item in world_model.recent_visible_text:
            if item.expires_at is not None and item.expires_at < now:
                continue
            if item.confidence.score < self.minimum_fact_confidence:
                continue
            freshness = self._normalize_world_model_freshness(item)
            facts.append(
                PerceptionFactRecord(
                    fact_type="visible_text",
                    label=item.label,
                    confidence=item.confidence.score,
                    claim_kind=item.claim_kind,
                    quality_class=item.quality_class,
                    observed_at=item.observed_at,
                    expires_at=item.expires_at,
                    limited_awareness=world_model.perception_limited_awareness,
                    freshness=freshness,
                    source_tier=item.source_tier,
                    uncertain=world_model.perception_limited_awareness or item.uncertainty_marker is not None,
                    provenance=list(item.provenance),
                    grounding_eligible=self._grounding_eligible(
                        claim_kind=item.claim_kind,
                        freshness=freshness,
                        limited_awareness=world_model.perception_limited_awareness,
                        source_tier=item.source_tier,
                    ),
                )
            )
        for item in world_model.visual_anchors:
            if item.expires_at is not None and item.expires_at < now:
                continue
            if item.confidence.score < self.minimum_fact_confidence:
                continue
            freshness = self._normalize_world_model_freshness(item)
            facts.append(
                PerceptionFactRecord(
                    fact_type="location_anchor",
                    label=item.label,
                    confidence=item.confidence.score,
                    claim_kind=item.claim_kind,
                    quality_class=item.quality_class,
                    justification=item.justification,
                    observed_at=item.observed_at,
                    expires_at=item.expires_at,
                    limited_awareness=world_model.perception_limited_awareness,
                    freshness=freshness,
                    source_tier=item.source_tier,
                    uncertain=world_model.perception_limited_awareness or item.uncertainty_marker is not None,
                    provenance=list(item.provenance),
                    grounding_eligible=self._grounding_eligible(
                        claim_kind=item.claim_kind,
                        freshness=freshness,
                        limited_awareness=world_model.perception_limited_awareness,
                        source_tier=item.source_tier,
                    ),
                )
            )
        for item in world_model.recent_named_objects:
            if item.expires_at is not None and item.expires_at < now:
                continue
            if item.confidence.score < self.minimum_fact_confidence:
                continue
            freshness = self._normalize_world_model_freshness(item)
            facts.append(
                PerceptionFactRecord(
                    fact_type="named_object",
                    label=item.label,
                    confidence=item.confidence.score,
                    claim_kind=item.claim_kind,
                    quality_class=item.quality_class,
                    observed_at=item.observed_at,
                    expires_at=item.expires_at,
                    limited_awareness=world_model.perception_limited_awareness,
                    freshness=freshness,
                    source_tier=item.source_tier,
                    uncertain=world_model.perception_limited_awareness or item.uncertainty_marker is not None,
                    provenance=list(item.provenance),
                    grounding_eligible=self._grounding_eligible(
                        claim_kind=item.claim_kind,
                        freshness=freshness,
                        limited_awareness=world_model.perception_limited_awareness,
                        source_tier=item.source_tier,
                    ),
                )
            )
        for item in world_model.recent_participant_attributes:
            if item.expires_at is not None and item.expires_at < now:
                continue
            if item.confidence.score < self.minimum_fact_confidence or not item.justification:
                continue
            freshness = self._normalize_world_model_freshness(item)
            facts.append(
                PerceptionFactRecord(
                    fact_type="participant_attribute",
                    label=item.label,
                    confidence=item.confidence.score,
                    claim_kind=item.claim_kind,
                    quality_class=item.quality_class,
                    justification=item.justification,
                    observed_at=item.observed_at,
                    expires_at=item.expires_at,
                    limited_awareness=world_model.perception_limited_awareness,
                    freshness=freshness,
                    source_tier=item.source_tier,
                    uncertain=world_model.perception_limited_awareness or item.uncertainty_marker is not None,
                    provenance=list(item.provenance),
                    grounding_eligible=self._grounding_eligible(
                        claim_kind=item.claim_kind,
                        freshness=freshness,
                        limited_awareness=world_model.perception_limited_awareness,
                        source_tier=item.source_tier,
                    ),
                )
            )
        return facts

    def _freshness_for(self, *, observed_at, expires_at, claim_kind: SceneClaimKind) -> FactFreshness:
        return self.freshness_policy.assessment(
            observed_at=observed_at,
            expires_at=expires_at,
            claim_kind=claim_kind,
        ).freshness

    def _dedupe_facts(self, facts: list[PerceptionFactRecord]) -> list[PerceptionFactRecord]:
        deduped: dict[tuple[str, str], PerceptionFactRecord] = {}
        for fact in facts:
            key = (fact.fact_type, fact.label)
            existing = deduped.get(key)
            if existing is None or self._fact_priority(fact) > self._fact_priority(existing):
                deduped[key] = fact
        return list(deduped.values())

    def _filter_facts_for_query(self, query: str, facts: list[PerceptionFactRecord]) -> list[PerceptionFactRecord]:
        facts = [item for item in facts if self._fact_eligible_for_query(item, query)]
        if any(keyword in query for keyword in ("how many", "anyone", "people")):
            return [item for item in facts if item.fact_type in {"people_count", "person_visibility", "engagement_state", "engagement_estimate", "attention_target"}][:5]
        if any(keyword in query for keyword in ("text", "sign")):
            return [item for item in facts if item.fact_type in {"visible_text", "location_anchor"}][:4]
        if any(keyword in query for keyword in ("where", "anchor", "location")):
            return [item for item in facts if item.fact_type in {"location_anchor"}][:4]
        if any(keyword in query for keyword in ("object", "see", "front")):
            return [item for item in facts if item.fact_type in {"named_object", "location_anchor", "scene_summary", "participant_attribute"}][:6]
        return facts[:6]

    def _fact_eligible_for_query(self, fact: PerceptionFactRecord, query: str) -> bool:
        visual_scene_query = any(keyword in query for keyword in ("text", "sign", "where", "anchor", "location", "object", "see", "front"))
        if visual_scene_query:
            return fact.grounding_eligible and fact.fact_type in {
                "scene_summary",
                "visible_text",
                "location_anchor",
                "named_object",
                "participant_attribute",
            }
        if fact.fact_type in {"people_count", "person_visibility", "engagement_state", "engagement_estimate", "attention_target"}:
            return fact.freshness not in {FactFreshness.STALE, FactFreshness.EXPIRED, FactFreshness.UNKNOWN}
        return fact.grounding_eligible

    @staticmethod
    def _fact_priority(fact: PerceptionFactRecord) -> tuple[int, int, float]:
        claim_rank = {
            SceneClaimKind.OPERATOR_ANNOTATION: 4,
            SceneClaimKind.SEMANTIC_OBSERVATION: 3,
            SceneClaimKind.WATCHER_HINT: 2,
            SceneClaimKind.MEMORY_ASSUMPTION: 1,
        }.get(fact.claim_kind, 0)
        freshness_rank = {
            FactFreshness.FRESH: 4,
            FactFreshness.AGING: 3,
            FactFreshness.STALE: 2,
            FactFreshness.UNKNOWN: 1,
            FactFreshness.EXPIRED: 0,
        }.get(fact.freshness, 0)
        return (claim_rank, freshness_rank, fact.confidence or 0.0)

    @staticmethod
    def _claim_kind_for_snapshot(snapshot: PerceptionSnapshotRecord) -> SceneClaimKind:
        if snapshot.tier == PerceptionTier.WATCHER:
            return SceneClaimKind.WATCHER_HINT
        for observation in snapshot.observations:
            if observation.claim_kind == SceneClaimKind.OPERATOR_ANNOTATION:
                return SceneClaimKind.OPERATOR_ANNOTATION
        if snapshot.provider_mode.value == "manual_annotations" and snapshot.source.startswith("operator"):
            return SceneClaimKind.OPERATOR_ANNOTATION
        return SceneClaimKind.SEMANTIC_OBSERVATION

    def _quality_class(self, claim_kind: SceneClaimKind, snapshot: PerceptionSnapshotRecord):
        if claim_kind == SceneClaimKind.WATCHER_HINT:
            return None
        labels = [item.confidence.label for item in snapshot.observations if item.confidence.label]
        label = labels[0] if labels else None
        quality_map = {
            "low": "low",
            "medium": "medium",
            "high": "high",
        }
        return quality_map.get(label)

    def _grounding_eligible(
        self,
        *,
        claim_kind: SceneClaimKind,
        freshness: FactFreshness,
        limited_awareness: bool,
        source_tier: PerceptionTier,
        allow_watcher_presence: bool = False,
    ) -> bool:
        if allow_watcher_presence and claim_kind == SceneClaimKind.WATCHER_HINT:
            return freshness not in {FactFreshness.STALE, FactFreshness.EXPIRED, FactFreshness.UNKNOWN}
        return self.freshness_policy.dialogue_grounding_eligible(
            claim_kind=claim_kind,
            freshness=freshness,
            limited_awareness=limited_awareness,
            source_tier=source_tier,
        )

    def _normalize_world_model_freshness(self, item) -> FactFreshness:
        freshness = getattr(item, "freshness", FactFreshness.UNKNOWN)
        if freshness != FactFreshness.UNKNOWN:
            return freshness
        claim_kind = getattr(item, "claim_kind", SceneClaimKind.SEMANTIC_OBSERVATION)
        return self._freshness_for(
            observed_at=getattr(item, "observed_at", None),
            expires_at=getattr(item, "expires_at", None),
            claim_kind=claim_kind,
        )

    def _perception_answer(self, query: str, facts: list[PerceptionFactRecord]) -> str:
        if any(keyword in query for keyword in ("how many", "anyone", "people")):
            people_count = next((item.detail for item in facts if item.fact_type == "people_count"), None)
            if people_count is not None:
                noun = "person" if people_count == "1" else "people"
                engagement = self._format_engagement_phrase(
                    next((item.label for item in facts if item.fact_type == "engagement_estimate"), None)
                )
                if engagement:
                    return f"I currently estimate {people_count} {noun} in view, and {engagement}."
                return f"I currently have a fresh estimate of {people_count} {noun} in view."
        if any(keyword in query for keyword in ("text", "sign")):
            labels = [item.label for item in facts if item.fact_type in {"visible_text", "location_anchor"}]
            if labels:
                return f"The freshest visible text or anchor I can ground is: {', '.join(labels)}."
        if any(keyword in query for keyword in ("where", "anchor", "location")):
            labels = [item.label for item in facts if item.fact_type in {"location_anchor", "attention_target"}]
            if labels:
                return f"I can currently ground these location cues: {', '.join(labels)}."
        labels = [item.label for item in facts if item.fact_type in {"named_object", "location_anchor"}]
        if labels:
            return f"From the current scene state, I can ground these facts: {', '.join(labels)}."
        people_count = next((item.detail for item in facts if item.fact_type == "people_count"), None)
        engagement = self._format_engagement_phrase(
            next((item.label for item in facts if item.fact_type == "engagement_estimate"), None)
        )
        summary = next((item.detail for item in facts if item.fact_type == "scene_summary" and item.detail), None)
        if summary and people_count is not None:
            noun = "person" if people_count == "1" else "people"
            if engagement:
                return f"I can currently make out {people_count} {noun} in view. {engagement.capitalize()}. {summary}"
            return f"I can currently make out {people_count} {noun} in view. {summary}"
        return summary or "I do not have a fresh scene fact for that."

    def _format_engagement_phrase(self, value: str | None) -> str | None:
        if value is None:
            return None
        lowered = value.strip().lower()
        if not lowered:
            return None
        if lowered in {"low", "medium", "high"}:
            return f"the scene suggests {lowered} engagement"
        if lowered.startswith(("focused", "looking", "seated", "standing", "leaning")):
            return f"the person appears {lowered}"
        return lowered

    def _best_document_hit(self, query: str) -> VenueDocument | None:
        lowered = query.lower().strip()
        best_score = 0
        best: VenueDocument | None = None
        for item in self.venue_knowledge.documents:
            score = self._score_text(lowered, f"{item.title} {item.text}")
            if score > best_score:
                best_score = score
                best = item
        if best_score < 2:
            return None
        return best

    def _document_snippet(self, document: VenueDocument) -> str:
        text = " ".join(document.text.split())
        if len(text) <= 240:
            return text
        return text[:237].rstrip() + "..."

    def _session_topics(self, session: SessionRecord, *, intent: str | None) -> list[str]:
        topics = [session.current_topic or "", intent or ""]
        if last_location := session.session_memory.get("last_location"):
            topics.append(last_location)
        if last_event := session.session_memory.get("last_event_id"):
            topics.append(last_event)
        return [item for item in dict.fromkeys(topic.strip() for topic in topics if topic and topic.strip())]

    def _merge_unique(self, current: list[str], incoming: list[str]) -> list[str]:
        merged = list(current)
        for item in incoming:
            if item and item not in merged:
                merged.append(item)
        return merged

    def _snapshot_is_stale(self, snapshot: PerceptionSnapshotRecord) -> bool:
        captured_at = snapshot.source_frame.captured_at or snapshot.created_at
        freshness = self.freshness_policy.assessment(
            observed_at=captured_at,
            claim_kind=self._claim_kind_for_snapshot(snapshot),
        ).freshness
        return freshness in {FactFreshness.STALE, FactFreshness.EXPIRED}

    def _looks_like_profile_query(self, lowered: str) -> bool:
        return any(
            phrase in lowered
            for phrase in (
                "do you remember me",
                "what do you remember about me",
                "what do you know about me",
                "my preferences",
                "my preference",
                "remember my",
            )
        )

    def _looks_like_prior_session_query(self, lowered: str) -> bool:
        return any(
            phrase in lowered
            for phrase in (
                "last time",
                "previous session",
                "previous visit",
                "before",
                "earlier we talked",
                "what did we talk about",
            )
        )

    def _looks_like_scene_query(self, lowered: str) -> bool:
        return looks_like_visual_query(lowered)

    def _score_text(self, query: str, text: str) -> int:
        query_tokens = {item for item in _TOKEN_RE.findall(query.lower()) if item not in _STOPWORDS}
        text_tokens = set(_TOKEN_RE.findall(text.lower()))
        overlap = len(query_tokens & text_tokens)
        phrase_bonus = 2 if query.strip() and query.strip() in text.lower() else 0
        return overlap + phrase_bonus

    def _extract_reminder(
        self,
        *,
        session: SessionRecord,
        user_memory: UserMemoryRecord | None,
        trace_id: str,
    ) -> ReminderRecord | None:
        lowered = (session.last_user_text or "").lower().strip()
        if not lowered:
            return None
        match = re.search(
            r"(?:remind me to|set a reminder to|please remind me to)\s+(.+?)(?:\s+(tomorrow|later today)|\s+in\s+(\d+)\s+(minute|minutes|hour|hours))?[.?!]?$",
            lowered,
        )
        if match is None:
            return None
        reminder_text = match.group(1).strip(" .,!?:;")
        if not reminder_text:
            return None
        due_at = None
        relative_day = match.group(2)
        relative_amount = match.group(3)
        relative_unit = match.group(4)
        now = utc_now()
        if relative_day == "tomorrow":
            due_at = now + timedelta(days=1)
        elif relative_day == "later today":
            due_at = now + timedelta(hours=3)
        elif relative_amount and relative_unit:
            amount = int(relative_amount)
            due_at = now + (timedelta(hours=amount) if relative_unit.startswith("hour") else timedelta(minutes=amount))
        return ReminderRecord(
            session_id=session.session_id,
            user_id=user_memory.user_id if user_memory is not None else session.user_id,
            reminder_text=reminder_text,
            due_at=due_at,
            source_trace_ids=[trace_id],
        )

    def _extract_note(
        self,
        *,
        session: SessionRecord,
        user_memory: UserMemoryRecord | None,
        trace_id: str,
    ) -> CompanionNoteRecord | None:
        lowered = (session.last_user_text or "").lower().strip()
        if not lowered:
            return None
        match = re.search(
            r"(?:note that|make a note that|write this down|remember this note)[: ]+(.+?)[.?!]?$",
            lowered,
        )
        if match is None:
            return None
        content = match.group(1).strip(" .,!?:;")
        if not content:
            return None
        title_words = content.split()
        title = " ".join(title_words[:6]).strip() or "local note"
        return CompanionNoteRecord(
            session_id=session.session_id,
            user_id=user_memory.user_id if user_memory is not None else session.user_id,
            title=title,
            content=content,
            tags=self._session_topics(session, intent=None)[:4],
            source_trace_ids=[trace_id],
        )

    def _maybe_write_session_digest(
        self,
        *,
        session: SessionRecord,
        user_memory: UserMemoryRecord | None,
        trace_id: str,
    ) -> SessionDigestRecord | None:
        if not session.transcript:
            return None
        existing = self.memory_store.list_session_digests(session_id=session.session_id, limit=1).items
        latest = existing[0] if existing else None
        turn_count = len(session.transcript)
        enough_new_turns = latest is None or turn_count - latest.turn_count >= 8
        enough_time = latest is None or (
            utc_now() - latest.updated_at
        ).total_seconds() >= max(60.0, self.digest_interval_minutes * 60.0)
        if not (enough_new_turns or enough_time):
            return None
        recent_turns = session.transcript[-4:]
        highlights: list[str] = []
        for turn in recent_turns:
            if turn.user_text:
                highlights.append(f"user: {turn.user_text}")
            if turn.reply_text:
                highlights.append(f"blink: {turn.reply_text}")
        open_follow_ups = [
            item.reminder_text
            for item in self.memory_store.list_reminders(session_id=session.session_id, user_id=session.user_id, limit=20).items
            if item.status.value == "open"
        ][:4]
        record = SessionDigestRecord(
            digest_id=latest.digest_id if latest is not None else str(uuid4()),
            session_id=session.session_id,
            user_id=user_memory.user_id if user_memory is not None else session.user_id,
            summary=" | ".join(highlights)[:600] or (session.conversation_summary or "Session digest ready."),
            turn_count=turn_count,
            open_follow_ups=open_follow_ups,
            source_trace_ids=self._merge_unique(latest.source_trace_ids if latest is not None else [], [trace_id]),
        )
        return self.memory_store.upsert_session_digest(record)
