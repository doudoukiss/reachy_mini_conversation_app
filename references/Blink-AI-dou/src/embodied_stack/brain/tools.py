from __future__ import annotations

from datetime import timedelta

from embodied_stack.backends.embeddings import RetrievalDocument, SemanticRetriever
from embodied_stack.backends.types import EmbeddingBackend
from embodied_stack.brain.grounded_memory import GroundedMemoryService, MemoryContextSnapshot
from embodied_stack.brain.memory import MemoryStore
from embodied_stack.brain.venue_knowledge import VenueKnowledge, VenueLookupResult
from embodied_stack.config import Settings, get_settings
from embodied_stack.demo.community_scripts import (
    COMMUNITY_EVENTS,
    COMMUNITY_FAQ_LIST,
    COMMUNITY_LOCATIONS,
    FEEDBACK_PROMPTS,
    OPERATOR_ESCALATION,
)
from embodied_stack.shared.contracts._common import CompanionContextMode, ReminderStatus
from embodied_stack.shared.contracts.brain import (
    MemoryPromotionRecord,
    SessionRecord,
    ToolInvocationRecord,
    UserMemoryRecord,
    WorldState,
    utc_now,
)
from embodied_stack.shared.contracts.perception import (
    EmbodiedWorldModel,
    PerceptionFactRecord,
    PerceptionObservationType,
    PerceptionSnapshotRecord,
)


class KnowledgeToolbox:
    """Venue-aware local tools for FAQ, events, wayfinding, feedback, and human escalation."""

    def __init__(
        self,
        *,
        settings: Settings | None = None,
        venue_knowledge: VenueKnowledge | None = None,
        embedding_backend: EmbeddingBackend | None = None,
        memory_store: MemoryStore | None = None,
    ) -> None:
        runtime_settings = settings or get_settings()
        self.settings = runtime_settings
        self.venue_knowledge = venue_knowledge or VenueKnowledge.from_directory(runtime_settings.venue_content_dir)
        self.memory_store = memory_store
        self.grounded_memory = (
            GroundedMemoryService(
                memory_store=memory_store,
                venue_knowledge=self.venue_knowledge,
                digest_interval_minutes=float(runtime_settings.blink_memory_digest_interval_minutes),
            )
            if memory_store is not None
            else None
        )
        self.semantic_retriever = (
            SemanticRetriever(
                embedding_backend=embedding_backend,
                static_documents=self._build_static_retrieval_documents(),
            )
            if embedding_backend is not None
            else None
        )

    def venue_overview(self) -> str:
        return self.venue_knowledge.overview()

    def resolved_context_mode(self, *, session: SessionRecord) -> CompanionContextMode:
        if session.scenario_name:
            return CompanionContextMode.VENUE_DEMO
        return self.settings.blink_context_mode

    def contextual_venue_overview(self, *, text: str, session: SessionRecord) -> str | None:
        if self.should_include_venue_context(text=text, session=session):
            return self.venue_knowledge.overview()
        return None

    def should_include_venue_context(self, *, text: str, session: SessionRecord) -> bool:
        context_mode = self.resolved_context_mode(session=session)
        if context_mode == CompanionContextMode.VENUE_DEMO:
            return True
        lowered = text.lower().strip()
        if session.current_topic in {"events", "wayfinding", "feedback"}:
            return True
        return self._query_is_explicitly_venue_scoped(lowered, session=session)

    def lookup(
        self,
        text: str,
        *,
        session: SessionRecord,
        user_memory: UserMemoryRecord | None,
        world_state: WorldState,
        world_model: EmbodiedWorldModel | None = None,
        latest_perception: PerceptionSnapshotRecord | None = None,
    ) -> list[ToolInvocationRecord]:
        lowered = text.lower().strip()
        results: list[ToolInvocationRecord] = []

        local_first = self._prefer_local_companion_memory(session=session)
        tool_order = (
            (
                self._lookup_personal_reminders,
                self._lookup_local_notes,
                self._lookup_recent_session_digest,
                self._lookup_today_context,
                self._lookup_profile_memory,
                self._lookup_prior_session,
                self._lookup_recent_perception,
                self._lookup_feedback,
                self._lookup_events,
                self._lookup_faq,
                self._lookup_location,
                self._lookup_venue_document,
                self._lookup_operator_escalation,
            )
            if local_first
            else (
                self._lookup_operator_escalation,
                self._lookup_profile_memory,
                self._lookup_prior_session,
                self._lookup_personal_reminders,
                self._lookup_local_notes,
                self._lookup_recent_session_digest,
                self._lookup_today_context,
                self._lookup_recent_perception,
                self._lookup_feedback,
                self._lookup_events,
                self._lookup_faq,
                self._lookup_location,
                self._lookup_venue_document,
            )
        )

        for tool in tool_order:
            result = tool(
                lowered,
                session=session,
                user_memory=user_memory,
                world_state=world_state,
                world_model=world_model,
                latest_perception=latest_perception,
            )
            if result is not None:
                results.append(result)

        if self.grounded_memory is not None and results:
            support_results = self._supporting_grounding_results(
                lowered,
                session=session,
                user_memory=user_memory,
                world_model=world_model,
                latest_perception=latest_perception,
            )
            for result in support_results:
                if all(
                    not (
                        existing.tool_name == result.tool_name
                        and existing.answer_text == result.answer_text
                    )
                    for existing in results
                ):
                    results.append(result)

        if not results:
            semantic_result = self._semantic_lookup(
                lowered,
                session=session,
                user_memory=user_memory,
            )
            if semantic_result is not None:
                results.append(semantic_result)

        return results

    def build_memory_context(
        self,
        query: str,
        *,
        session: SessionRecord,
        user_memory: UserMemoryRecord | None,
        world_model: EmbodiedWorldModel | None,
        latest_perception: PerceptionSnapshotRecord | None,
    ) -> MemoryContextSnapshot:
        if self.grounded_memory is None:
            return MemoryContextSnapshot()
        return self.grounded_memory.build_memory_context(
            query,
            session=session,
            user_memory=user_memory,
            world_model=world_model,
            latest_perception=latest_perception,
        )

    def recent_perception_facts(
        self,
        *,
        query: str | None,
        world_model: EmbodiedWorldModel | None,
        latest_perception: PerceptionSnapshotRecord | None,
    ) -> list[PerceptionFactRecord]:
        if self.grounded_memory is None:
            return []
        return self.grounded_memory.recent_perception_facts(
            world_model=world_model,
            latest_perception=latest_perception,
            query=query,
        )

    def record_turn_memory(
        self,
        *,
        session: SessionRecord,
        user_memory: UserMemoryRecord | None,
        trace_id: str,
        reply_text: str | None,
        intent: str | None,
        source_refs: list[str],
    ) -> list[MemoryPromotionRecord]:
        if self.grounded_memory is None:
            return []
        return self.grounded_memory.record_turn(
            session=session,
            user_memory=user_memory,
            trace_id=trace_id,
            reply_text=reply_text,
            intent=intent,
            source_refs=source_refs,
        )

    def list_open_reminders(
        self,
        *,
        session: SessionRecord,
        user_memory: UserMemoryRecord | None,
        limit: int = 20,
    ):
        if self.memory_store is None:
            return []
        user_id = user_memory.user_id if user_memory is not None else session.user_id
        if user_id:
            return self.memory_store.list_reminders(
                user_id=user_id,
                status=ReminderStatus.OPEN,
                limit=limit,
            ).items
        return self.memory_store.list_reminders(
            session_id=session.session_id,
            status=ReminderStatus.OPEN,
            limit=limit,
        ).items

    def list_recent_notes(
        self,
        *,
        session: SessionRecord,
        user_memory: UserMemoryRecord | None,
        limit: int = 20,
    ):
        if self.memory_store is None:
            return []
        user_id = user_memory.user_id if user_memory is not None else session.user_id
        return self.memory_store.list_companion_notes(session_id=session.session_id, user_id=user_id, limit=limit).items

    def list_recent_session_digests(
        self,
        *,
        session: SessionRecord,
        user_memory: UserMemoryRecord | None,
        limit: int = 10,
    ):
        if self.memory_store is None:
            return []
        user_id = user_memory.user_id if user_memory is not None else session.user_id
        if user_id:
            return self.memory_store.list_session_digests(user_id=user_id, limit=limit).items
        return self.memory_store.list_session_digests(session_id=session.session_id, limit=limit).items

    def _lookup_profile_memory(
        self,
        lowered: str,
        *,
        session: SessionRecord,
        user_memory: UserMemoryRecord | None,
        world_state: WorldState,
        world_model: EmbodiedWorldModel | None,
        latest_perception: PerceptionSnapshotRecord | None,
    ) -> ToolInvocationRecord | None:
        del session, world_state, world_model, latest_perception
        if self.grounded_memory is None:
            return None
        return self.grounded_memory.lookup_profile_memory(lowered, user_memory=user_memory)

    def _lookup_personal_reminders(
        self,
        lowered: str,
        *,
        session: SessionRecord,
        user_memory: UserMemoryRecord | None,
        world_state: WorldState,
        world_model: EmbodiedWorldModel | None,
        latest_perception: PerceptionSnapshotRecord | None,
    ) -> ToolInvocationRecord | None:
        del world_state, world_model, latest_perception
        if not any(
            phrase in lowered
            for phrase in (
                "reminder",
                "remind me",
                "what do i need to remember",
                "later today",
                "leave anything open",
                "what should we revisit",
                "follow up",
            )
        ):
            return None
        reminders = self.list_open_reminders(session=session, user_memory=user_memory, limit=4)
        if not reminders:
            return ToolInvocationRecord(
                tool_name="personal_reminders",
                answer_text="You do not have any open local reminders right now.",
                metadata={"knowledge_source": "personal_reminders", "source_refs": []},
                notes=["personal_reminders_empty"],
            )
        now = utc_now()
        lines = []
        for item in reminders:
            if item.due_at is not None and item.due_at <= now:
                lines.append(f"{item.reminder_text} (due now)")
            elif item.due_at is not None:
                delta = max(0, int((item.due_at - now).total_seconds() // 60))
                lines.append(f"{item.reminder_text} (due in about {delta} min)")
            else:
                lines.append(item.reminder_text)
        return ToolInvocationRecord(
            tool_name="personal_reminders",
            answer_text="Your open reminders are: " + "; ".join(lines) + ".",
            metadata={
                "knowledge_source": "personal_reminders",
                "source_refs": [f"reminder:{item.reminder_id}" for item in reminders],
            },
            notes=["personal_reminders_match"],
        )

    def _lookup_local_notes(
        self,
        lowered: str,
        *,
        session: SessionRecord,
        user_memory: UserMemoryRecord | None,
        world_state: WorldState,
        world_model: EmbodiedWorldModel | None,
        latest_perception: PerceptionSnapshotRecord | None,
    ) -> ToolInvocationRecord | None:
        del world_state, world_model, latest_perception
        if not any(phrase in lowered for phrase in ("my note", "notes", "workspace", "write down", "remember this note")):
            return None
        notes = self.list_recent_notes(session=session, user_memory=user_memory, limit=3)
        if not notes:
            return ToolInvocationRecord(
                tool_name="local_notes",
                answer_text="I do not have any saved local notes for this session yet.",
                metadata={"knowledge_source": "local_notes", "source_refs": []},
                notes=["local_notes_empty"],
            )
        return ToolInvocationRecord(
            tool_name="local_notes",
            answer_text="Saved notes: " + "; ".join(f"{item.title}: {item.content}" for item in notes) + ".",
            metadata={
                "knowledge_source": "local_notes",
                "source_refs": [f"note:{item.note_id}" for item in notes],
            },
            notes=["local_notes_match"],
        )

    def _lookup_recent_session_digest(
        self,
        lowered: str,
        *,
        session: SessionRecord,
        user_memory: UserMemoryRecord | None,
        world_state: WorldState,
        world_model: EmbodiedWorldModel | None,
        latest_perception: PerceptionSnapshotRecord | None,
    ) -> ToolInvocationRecord | None:
        del world_state, world_model, latest_perception
        if not any(
            phrase in lowered
            for phrase in (
                "summary",
                "summarize",
                "what were we discussing",
                "recap",
                "recent session",
                "what should we revisit",
                "pick up where we left off",
                "where we left off",
                "leave anything open",
            )
        ):
            return None
        digests = self.list_recent_session_digests(session=session, user_memory=user_memory, limit=1)
        if not digests:
            return None
        digest = digests[0]
        return ToolInvocationRecord(
            tool_name="recent_session_digest",
            answer_text=digest.summary,
            metadata={
                "knowledge_source": "session_digest",
                "source_refs": [f"digest:{digest.digest_id}"],
            },
            notes=["session_digest_match"],
        )

    def _lookup_today_context(
        self,
        lowered: str,
        *,
        session: SessionRecord,
        user_memory: UserMemoryRecord | None,
        world_state: WorldState,
        world_model: EmbodiedWorldModel | None,
        latest_perception: PerceptionSnapshotRecord | None,
    ) -> ToolInvocationRecord | None:
        del world_state, world_model, latest_perception
        if not any(phrase in lowered for phrase in ("today", "plan my day", "what's next", "day plan")):
            return None
        reminders = self.list_open_reminders(session=session, user_memory=user_memory, limit=4)
        digests = self.list_recent_session_digests(session=session, user_memory=user_memory, limit=1)
        notes = self.list_recent_notes(session=session, user_memory=user_memory, limit=2)
        parts = [f"Today is {utc_now().strftime('%A, %B %-d')}."]
        if reminders:
            parts.append("Open reminders: " + "; ".join(item.reminder_text for item in reminders) + ".")
        if digests:
            parts.append("Recent session summary: " + digests[0].summary)
        if notes:
            parts.append("Saved notes: " + "; ".join(item.title for item in notes) + ".")
        return ToolInvocationRecord(
            tool_name="today_context",
            answer_text=" ".join(parts),
            metadata={
                "knowledge_source": "today_context",
                "source_refs": [
                    *[f"reminder:{item.reminder_id}" for item in reminders],
                    *([f"digest:{digests[0].digest_id}"] if digests else []),
                    *[f"note:{item.note_id}" for item in notes],
                ],
            },
            notes=["today_context_match"],
        )

    def _lookup_prior_session(
        self,
        lowered: str,
        *,
        session: SessionRecord,
        user_memory: UserMemoryRecord | None,
        world_state: WorldState,
        world_model: EmbodiedWorldModel | None,
        latest_perception: PerceptionSnapshotRecord | None,
    ) -> ToolInvocationRecord | None:
        del world_state, world_model, latest_perception
        if self.grounded_memory is None:
            return None
        return self.grounded_memory.lookup_prior_session(
            lowered,
            session=session,
            user_memory=user_memory,
        )

    def _lookup_recent_perception(
        self,
        lowered: str,
        *,
        session: SessionRecord,
        user_memory: UserMemoryRecord | None,
        world_state: WorldState,
        world_model: EmbodiedWorldModel | None,
        latest_perception: PerceptionSnapshotRecord | None,
    ) -> ToolInvocationRecord | None:
        del session, user_memory, world_state
        if self.grounded_memory is None:
            return None
        return self.grounded_memory.lookup_recent_perception(
            lowered,
            world_model=world_model,
            latest_perception=latest_perception,
        )

    def _lookup_venue_document(
        self,
        lowered: str,
        *,
        session: SessionRecord,
        user_memory: UserMemoryRecord | None,
        world_state: WorldState,
        world_model: EmbodiedWorldModel | None,
        latest_perception: PerceptionSnapshotRecord | None,
    ) -> ToolInvocationRecord | None:
        del session, user_memory, world_state, world_model, latest_perception
        if self.grounded_memory is None:
            return None
        return self.grounded_memory.lookup_venue_document(lowered)

    def _supporting_grounding_results(
        self,
        lowered: str,
        *,
        session: SessionRecord,
        user_memory: UserMemoryRecord | None,
        world_model: EmbodiedWorldModel | None,
        latest_perception: PerceptionSnapshotRecord | None,
    ) -> list[ToolInvocationRecord]:
        if self.grounded_memory is None:
            return []
        results: list[ToolInvocationRecord] = []
        if profile := self.grounded_memory.lookup_profile_memory(lowered, user_memory=user_memory):
            results.append(profile)
        if prior := self.grounded_memory.lookup_prior_session(
            lowered,
            session=session,
            user_memory=user_memory,
        ):
            results.append(prior)
        if perception := self.grounded_memory.lookup_recent_perception(
            lowered,
            world_model=world_model,
            latest_perception=latest_perception,
        ):
            results.append(perception)
        return results

    def _lookup_faq(
        self,
        lowered: str,
        *,
        session: SessionRecord,
        user_memory: UserMemoryRecord | None,
        world_state: WorldState,
        world_model: EmbodiedWorldModel | None,
        latest_perception: PerceptionSnapshotRecord | None,
    ) -> ToolInvocationRecord | None:
        del user_memory, world_state

        if any(phrase in lowered for phrase in ("human help", "operator", "staff member", "help me right now", "staff")):
            return None

        venue_result = self.venue_knowledge.lookup_faq(lowered)
        if venue_result is not None:
            return self._from_venue_result("faq_lookup", venue_result)

        if self._should_prefer_location_answer(
            lowered,
            session=session,
            world_model=world_model,
            latest_perception=latest_perception,
        ):
            return None

        for entry in COMMUNITY_FAQ_LIST:
            if any(alias in lowered for alias in entry["aliases"]):
                return ToolInvocationRecord(
                    tool_name="faq_lookup",
                    answer_text=entry["answer"],
                    metadata={"faq_key": entry["key"], "knowledge_source": "seeded_demo_data"},
                    memory_updates={"last_topic": entry["key"]},
                    notes=[f"keyword_match:{entry['key']}"],
                )
        return None

    def _lookup_events(
        self,
        lowered: str,
        *,
        session: SessionRecord,
        user_memory: UserMemoryRecord | None,
        world_state: WorldState,
        world_model: EmbodiedWorldModel | None,
        latest_perception: PerceptionSnapshotRecord | None,
    ) -> ToolInvocationRecord | None:
        del user_memory, world_state, world_model, latest_perception

        venue_result = self.venue_knowledge.lookup_events(
            lowered,
            last_event_id=session.session_memory.get("last_event_id"),
        )
        if venue_result is not None:
            return self._from_venue_result("events_lookup", venue_result)

        if any(keyword in lowered for keyword in ("events", "schedule", "this week", "happening")):
            summary = ", ".join(
                f"{item.title} on {item.event_date.strftime('%A, %B %-d')} at {item.start_time.strftime('%-I:%M %p')}"
                for item in COMMUNITY_EVENTS
            )
            return ToolInvocationRecord(
                tool_name="events_lookup",
                answer_text=f"This week at the community center: {summary}.",
                metadata={"event_ids": [item.event_id for item in COMMUNITY_EVENTS], "knowledge_source": "seeded_demo_data"},
                memory_updates={"last_topic": "events", "last_event_id": COMMUNITY_EVENTS[0].event_id},
                notes=["keyword_match:events"],
            )

        for event in COMMUNITY_EVENTS:
            if event.title.lower() in lowered and any(keyword in lowered for keyword in ("time", "start", "when")):
                location = COMMUNITY_LOCATIONS[event.location_key]
                return ToolInvocationRecord(
                    tool_name="events_lookup",
                    answer_text=(
                        f"{event.title} starts on {event.event_date.strftime('%A, %B %-d')} at "
                        f"{event.start_time.strftime('%-I:%M %p')} in the {location.title}."
                    ),
                    metadata={"event_id": event.event_id, "location_key": event.location_key, "knowledge_source": "seeded_demo_data"},
                    memory_updates={"last_topic": "events", "last_event_id": event.event_id},
                    notes=[f"keyword_match:{event.event_id}_time"],
                )

        if session.session_memory.get("last_topic") == "events" and any(keyword in lowered for keyword in ("what time", "when does that start", "when is that")):
            event_id = session.session_memory.get("last_event_id", COMMUNITY_EVENTS[0].event_id)
            event = next(item for item in COMMUNITY_EVENTS if item.event_id == event_id)
            return ToolInvocationRecord(
                tool_name="events_lookup",
                answer_text=(
                    f"{event.title} starts on {event.event_date.strftime('%A, %B %-d')} at "
                    f"{event.start_time.strftime('%-I:%M %p')}."
                ),
                metadata={"event_id": event.event_id, "knowledge_source": "seeded_demo_data"},
                memory_updates={"last_topic": "events", "last_event_id": event.event_id},
                notes=["memory_followup:last_event_id"],
            )

        if any(keyword in lowered for keyword in ("feedback", "complaint", "suggestion")):
            return None

        if any(keyword in lowered for keyword in ("event", "events", "schedule", "calendar", "what time", "when is")):
            return ToolInvocationRecord(
                tool_name="events_lookup",
                answer_text=(
                    "I do not have a confirmed venue schedule entry for that yet. "
                    "I can answer from imported event data when it is available, or connect you to staff."
                ),
                metadata={"knowledge_source": "honest_insufficiency", "insufficient_reason": "venue_schedule_unknown"},
                memory_updates={"last_topic": "events"},
                notes=["venue_events_insufficient"],
            )

        return None

    def _lookup_location(
        self,
        lowered: str,
        *,
        session: SessionRecord,
        user_memory: UserMemoryRecord | None,
        world_state: WorldState,
        world_model: EmbodiedWorldModel | None,
        latest_perception: PerceptionSnapshotRecord | None,
    ) -> ToolInvocationRecord | None:
        del user_memory, world_state

        venue_result = self.venue_knowledge.lookup_location(
            lowered,
            last_location_key=session.session_memory.get("last_location"),
            visible_labels=self._visible_labels(world_model, latest_perception),
            attention_target=world_model.attention_target.target_label if world_model and world_model.attention_target else None,
        )
        if venue_result is not None:
            return self._from_venue_result("wayfinding_lookup", venue_result)

        for location_key, location in COMMUNITY_LOCATIONS.items():
            if location.title.lower() in lowered or location_key.replace("_", " ") in lowered:
                return self._seeded_location_result(location_key, note=f"keyword_match:{location_key}")

        if any(phrase in lowered for phrase in ("where is it", "how do i get there", "repeat that", "repeat how to get there")):
            last_location = session.session_memory.get("last_location")
            if last_location:
                return self._seeded_location_result(last_location, note="memory_followup:last_location")

        if any(
            phrase in lowered
            for phrase in ("where is", "how do i get to", "how do i get there", "directions", "find the", "find ")
        ):
            return ToolInvocationRecord(
                tool_name="wayfinding_lookup",
                answer_text=(
                    "I do not have a confirmed venue entry for that room or sign yet. "
                    "If you can show me visible signage I can ground from that, or I can hand off to staff."
                ),
                metadata={"knowledge_source": "honest_insufficiency", "insufficient_reason": "venue_location_unknown"},
                memory_updates={"last_topic": "wayfinding"},
                notes=["venue_location_insufficient"],
            )

        return None

    def _lookup_operator_escalation(
        self,
        lowered: str,
        *,
        session: SessionRecord,
        user_memory: UserMemoryRecord | None,
        world_state: WorldState,
        world_model: EmbodiedWorldModel | None,
        latest_perception: PerceptionSnapshotRecord | None,
    ) -> ToolInvocationRecord | None:
        del session, user_memory, world_state, world_model, latest_perception

        if not any(keyword in lowered for keyword in ("human", "staff", "operator", "lost item", "help me", "accessibility issue", "safety concern", "accessible route", "accessibility")):
            return None

        venue_contact = self.venue_knowledge.lookup_staff_contact(lowered)
        if venue_contact is not None:
            return ToolInvocationRecord(
                tool_name="operator_escalation",
                answer_text=f"{OPERATOR_ESCALATION['response_text']} {venue_contact.answer_text}",
                metadata={
                    "knowledge_source": "venue_pack",
                    "policy_note": OPERATOR_ESCALATION["policy_note"],
                    **venue_contact.metadata,
                },
                memory_updates=venue_contact.memory_updates,
                notes=["keyword_match:operator_escalation", *venue_contact.notes],
            )

        return ToolInvocationRecord(
            tool_name="operator_escalation",
            answer_text=(
                "I do not have a confirmed staff contact for that right now. "
                + OPERATOR_ESCALATION["response_text"]
            ),
            metadata={
                "contact_label": OPERATOR_ESCALATION["contact_label"],
                "policy_note": OPERATOR_ESCALATION["policy_note"],
                "knowledge_source": "seeded_demo_data",
            },
            memory_updates={"last_topic": "operator_handoff", "operator_escalation": "requested"},
            notes=["keyword_match:operator_escalation"],
        )

    def _lookup_feedback(
        self,
        lowered: str,
        *,
        session: SessionRecord,
        user_memory: UserMemoryRecord | None,
        world_state: WorldState,
        world_model: EmbodiedWorldModel | None,
        latest_perception: PerceptionSnapshotRecord | None,
    ) -> ToolInvocationRecord | None:
        del session, user_memory, world_state, world_model, latest_perception

        if any(keyword in lowered for keyword in ("feedback", "complaint", "suggestion")):
            prompt_key = "event_feedback" if "event" in lowered else "general_feedback"
            return ToolInvocationRecord(
                tool_name="feedback_lookup",
                answer_text=FEEDBACK_PROMPTS[prompt_key],
                metadata={"prompt_key": prompt_key, "knowledge_source": "seeded_demo_data"},
                memory_updates={"last_topic": "feedback"},
                notes=[f"keyword_match:{prompt_key}"],
            )
        return None

    def _lookup_user_memory(
        self,
        lowered: str,
        *,
        session: SessionRecord,
        user_memory: UserMemoryRecord | None,
        world_state: WorldState,
        world_model: EmbodiedWorldModel | None,
        latest_perception: PerceptionSnapshotRecord | None,
    ) -> ToolInvocationRecord | None:
        del session, world_state, world_model, latest_perception

        if user_memory and user_memory.display_name and "do you remember me" in lowered:
            return ToolInvocationRecord(
                tool_name="user_memory_lookup",
                answer_text=f"Yes. I remember you as {user_memory.display_name}.",
                metadata={"user_id": user_memory.user_id},
                memory_updates={"last_topic": "user_memory"},
                notes=["memory_match:user_display_name"],
            )
        return None

    def _seeded_location_result(self, location_key: str, *, note: str) -> ToolInvocationRecord:
        location = COMMUNITY_LOCATIONS[location_key]
        return ToolInvocationRecord(
            tool_name="wayfinding_lookup",
            answer_text=f"The {location.title} is on the {location.floor}. {location.directions}",
            metadata={"location_key": location_key, "knowledge_source": "seeded_demo_data"},
            memory_updates={"last_topic": "wayfinding", "last_location": location_key},
            notes=[note],
        )

    def _semantic_lookup(
        self,
        lowered: str,
        *,
        session: SessionRecord,
        user_memory: UserMemoryRecord | None,
    ) -> ToolInvocationRecord | None:
        if self.semantic_retriever is None:
            return None

        hit = self.semantic_retriever.search(
            lowered,
            extra_documents=self._build_dynamic_retrieval_documents(session=session, user_memory=user_memory),
            minimum_score=0.58,
        )
        if hit is None:
            return None

        return ToolInvocationRecord(
            tool_name=hit.document.tool_name,
            answer_text=hit.document.answer_text,
            metadata={
                **hit.document.metadata,
                "retrieval_backend": hit.backend_id,
                "retrieval_score": round(hit.score, 3),
            },
            notes=[*hit.document.notes, f"semantic_retrieval:{hit.document.document_id}"],
        )

    def _build_static_retrieval_documents(self) -> list[RetrievalDocument]:
        documents: list[RetrievalDocument] = []
        for item in self.venue_knowledge.faqs:
            documents.append(
                RetrievalDocument(
                    document_id=f"venue-faq:{item.entry_id}",
                    tool_name="faq_lookup",
                    text=" ".join(part for part in [item.question, item.answer, *item.aliases, *item.tags] if part),
                    answer_text=item.answer,
                    metadata={"faq_key": item.entry_id, "source_refs": [item.source_ref], "knowledge_source": "semantic_retrieval"},
                    notes=("venue_semantic_faq",),
                )
            )
        for item in self.venue_knowledge.locations.values():
            documents.append(
                RetrievalDocument(
                    document_id=f"venue-location:{item.location_key}",
                    tool_name="wayfinding_lookup",
                    text=" ".join(
                        part
                        for part in [item.title, item.directions, *item.aliases, *item.visible_signage, *item.nearby_landmarks]
                        if part
                    ),
                    answer_text=item.directions,
                    metadata={"location_key": item.location_key, "source_refs": [item.source_ref], "knowledge_source": "semantic_retrieval"},
                    notes=("venue_semantic_location",),
                )
            )
        for item in self.venue_knowledge.events:
            location_text = item.location_label or "the listed venue space"
            documents.append(
                RetrievalDocument(
                    document_id=f"venue-event:{item.event_id}",
                    tool_name="events_lookup",
                    text=" ".join(part for part in [item.title, item.summary, location_text, *item.aliases] if part),
                    answer_text=(
                        f"{item.title} starts on {item.start_at.strftime('%A, %B %-d')} at "
                        f"{item.start_at.strftime('%-I:%M %p')} in {location_text}."
                    ),
                    metadata={"event_id": item.event_id, "source_refs": [item.source_ref], "knowledge_source": "semantic_retrieval"},
                    notes=("venue_semantic_event",),
                )
            )
        for item in self.venue_knowledge.documents:
            documents.append(
                RetrievalDocument(
                    document_id=f"venue-doc:{item.doc_id}",
                    tool_name="venue_doc_lookup",
                    text=" ".join(part for part in [item.title, item.text] if part),
                    answer_text=" ".join(item.text.split())[:240].rstrip(),
                    metadata={"doc_id": item.doc_id, "source_refs": [item.source_ref], "knowledge_source": "venue_document"},
                    notes=("venue_semantic_document",),
                )
            )
        return documents

    def _build_dynamic_retrieval_documents(
        self,
        *,
        session: SessionRecord,
        user_memory: UserMemoryRecord | None,
    ) -> list[RetrievalDocument]:
        documents: list[RetrievalDocument] = []
        for index, note in enumerate(session.operator_notes[-3:]):
            documents.append(
                RetrievalDocument(
                    document_id=f"operator-note:{session.session_id}:{index}",
                    tool_name="faq_lookup",
                    text=note.text,
                    answer_text=note.text,
                    metadata={"session_id": session.session_id, "knowledge_source": "operator_note_memory"},
                    notes=("semantic_operator_note",),
                )
            )
        if self.grounded_memory is not None:
            documents.extend(
                self.grounded_memory.build_dynamic_retrieval_documents(
                    session=session,
                    user_memory=user_memory,
                )
            )
        if self.memory_store is not None:
            user_id = user_memory.user_id if user_memory is not None else session.user_id
            for item in self.memory_store.list_reminders(session_id=session.session_id, user_id=user_id, limit=8).items:
                documents.append(
                    RetrievalDocument(
                        document_id=f"reminder:{item.reminder_id}",
                        tool_name="personal_reminders",
                        text=item.reminder_text,
                        answer_text=item.reminder_text,
                        metadata={"source_refs": [f"reminder:{item.reminder_id}"], "knowledge_source": "personal_reminders"},
                        notes=("semantic_personal_reminder",),
                    )
                )
            for item in self.memory_store.list_companion_notes(session_id=session.session_id, user_id=user_id, limit=8).items:
                documents.append(
                    RetrievalDocument(
                        document_id=f"note:{item.note_id}",
                        tool_name="local_notes",
                        text=" ".join([item.title, item.content, *item.tags]),
                        answer_text=f"{item.title}: {item.content}",
                        metadata={"source_refs": [f"note:{item.note_id}"], "knowledge_source": "local_notes"},
                        notes=("semantic_local_note",),
                    )
                )
            for item in self.memory_store.list_session_digests(session_id=session.session_id, user_id=user_id, limit=4).items:
                documents.append(
                    RetrievalDocument(
                        document_id=f"digest:{item.digest_id}",
                        tool_name="recent_session_digest",
                        text=" ".join([item.summary, *item.open_follow_ups]),
                        answer_text=item.summary,
                        metadata={"source_refs": [f"digest:{item.digest_id}"], "knowledge_source": "session_digest"},
                        notes=("semantic_session_digest",),
                    )
                )
        elif user_memory is not None:
            fact_lines = [f"{key}: {value}" for key, value in sorted(user_memory.facts.items())]
            preference_lines = [f"{key}: {value}" for key, value in sorted(user_memory.preferences.items())]
            memory_text = " ".join(
                part
                for part in [
                    user_memory.display_name or "",
                    *fact_lines,
                    *preference_lines,
                    *user_memory.interests,
                ]
                if part
            )
            if memory_text:
                answer_text = (
                    f"I remember {user_memory.display_name}. {memory_text}."
                    if user_memory.display_name
                    else f"I remember: {memory_text}."
                )
                documents.append(
                    RetrievalDocument(
                        document_id=f"user-memory:{user_memory.user_id}",
                        tool_name="user_memory_lookup",
                        text=memory_text,
                        answer_text=answer_text,
                        metadata={"user_id": user_memory.user_id, "knowledge_source": "user_memory"},
                        notes=("semantic_user_memory",),
                    )
                )
        return documents

    def _from_venue_result(self, tool_name: str, result: VenueLookupResult) -> ToolInvocationRecord:
        metadata = {"knowledge_source": "venue_pack", **result.metadata}
        return ToolInvocationRecord(
            tool_name=tool_name,
            answer_text=result.answer_text,
            metadata=metadata,
            memory_updates=result.memory_updates,
            notes=result.notes,
        )

    def _visible_labels(
        self,
        world_model: EmbodiedWorldModel | None,
        latest_perception: PerceptionSnapshotRecord | None,
    ) -> list[str]:
        labels: list[str] = []
        if world_model is not None:
            labels.extend(item.label for item in world_model.recent_visible_text)
            labels.extend(item.label for item in world_model.visual_anchors)
            labels.extend(item.label for item in world_model.recent_named_objects)
        if latest_perception is not None:
            for observation in latest_perception.observations:
                if observation.confidence.score < 0.65:
                    continue
                if observation.observation_type in {
                    PerceptionObservationType.VISIBLE_TEXT,
                    PerceptionObservationType.LOCATION_ANCHOR,
                    PerceptionObservationType.NAMED_OBJECT,
                } and observation.text_value:
                    labels.append(observation.text_value)
        return list(dict.fromkeys(labels))

    def _should_prefer_location_answer(
        self,
        lowered: str,
        *,
        session: SessionRecord,
        world_model: EmbodiedWorldModel | None,
        latest_perception: PerceptionSnapshotRecord | None,
    ) -> bool:
        if not self._looks_like_location_query(lowered):
            return False

        venue_result = self.venue_knowledge.lookup_location(
            lowered,
            last_location_key=session.session_memory.get("last_location"),
            visible_labels=self._visible_labels(world_model, latest_perception),
            attention_target=world_model.attention_target.target_label if world_model and world_model.attention_target else None,
        )
        if venue_result is not None:
            return True

        if any(location.title.lower() in lowered or location_key.replace("_", " ") in lowered for location_key, location in COMMUNITY_LOCATIONS.items()):
            return True

        if any(phrase in lowered for phrase in ("where is it", "how do i get there", "repeat that", "repeat how to get there")):
            return bool(session.session_memory.get("last_location"))

        return False

    @staticmethod
    def _looks_like_location_query(lowered: str) -> bool:
        return any(
            phrase in lowered
            for phrase in ("where is", "where are", "how do i get", "directions", "find the", "find ", "way to")
        )

    def _prefer_local_companion_memory(self, *, session: SessionRecord) -> bool:
        if self.resolved_context_mode(session=session) == CompanionContextMode.VENUE_DEMO:
            return False
        return self.settings.blink_model_profile in {"companion_live", "local_companion", "m4_pro_companion", "desktop_local"} or self.settings.blink_always_on_enabled

    def _query_is_explicitly_venue_scoped(self, lowered: str, *, session: SessionRecord) -> bool:
        if self._looks_like_location_query(lowered):
            return True
        if any(
            phrase in lowered
            for phrase in (
                "front desk",
                "quiet room",
                "workshop room",
                "event",
                "schedule",
                "calendar",
                "hours",
                "community center",
                "venue",
                "pilot site",
                "feedback",
                "operator",
                "staff",
            )
        ):
            return True
        if any(phrase in lowered for phrase in ("where is it", "repeat that", "repeat how to get there")):
            return bool(session.session_memory.get("last_location"))
        return False
