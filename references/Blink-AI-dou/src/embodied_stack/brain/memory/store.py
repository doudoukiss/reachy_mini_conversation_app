from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import logging
from pathlib import Path
from threading import RLock, local
from time import perf_counter

from pydantic import BaseModel, Field, ValidationError

from embodied_stack.persistence import load_json_model_or_quarantine, quarantine_invalid_file, write_json_atomic
from embodied_stack.shared.contracts.brain import (
    CompanionNoteListResponse,
    CompanionNoteRecord,
    EpisodicMemoryListResponse,
    EpisodicMemoryRecord,
    IncidentListResponse,
    IncidentListScope,
    IncidentTicketRecord,
    IncidentTimelineRecord,
    IncidentTimelineResponse,
    LogListResponse,
    MemoryActionListResponse,
    MemoryActionRecord,
    MemoryRetrievalListResponse,
    MemoryRetrievalRecord,
    MemoryReviewListResponse,
    MemoryReviewDebtSummary,
    MemoryReviewRecord,
    OperatorNote,
    ParticipantRouterSnapshot,
    ProceduralMemoryListResponse,
    ProceduralMemoryRecord,
    RelationshipMemoryListResponse,
    RelationshipMemoryRecord,
    ReminderListResponse,
    ReminderRecord,
    ReminderStatus,
    SessionCreateRequest,
    SessionDigestListResponse,
    SessionDigestRecord,
    SessionListResponse,
    SessionRecord,
    SessionSummary,
    SemanticMemoryListResponse,
    SemanticMemoryRecord,
    ShiftSupervisorSnapshot,
    ShiftTransitionListResponse,
    ShiftTransitionRecord,
    TraceListResponse,
    TraceRecord,
    TraceSummary,
    UserMemoryRecord,
    WorldState,
    utc_now,
)
from embodied_stack.shared.contracts.episode import TeacherAnnotationListResponse, TeacherAnnotationRecord
from embodied_stack.shared.contracts.perception import (
    EmbodiedWorldModel,
    EngagementTimelinePoint,
    ExecutiveDecisionListResponse,
    ExecutiveDecisionRecord,
    PerceptionHistoryResponse,
    PerceptionSnapshotRecord,
    WorldModelTransitionListResponse,
    WorldModelTransitionRecord,
)

logger = logging.getLogger(__name__)


@dataclass
class PersistMetricsSnapshot:
    write_count: int = 0
    total_ms: float = 0.0


class BrainStoreSnapshot(BaseModel):
    sessions: dict[str, SessionRecord] = Field(default_factory=dict)
    user_memory: dict[str, UserMemoryRecord] = Field(default_factory=dict)
    relationship_memory: dict[str, RelationshipMemoryRecord] = Field(default_factory=dict)
    episodic_memory: dict[str, EpisodicMemoryRecord] = Field(default_factory=dict)
    semantic_memory: dict[str, SemanticMemoryRecord] = Field(default_factory=dict)
    procedural_memory: dict[str, ProceduralMemoryRecord] = Field(default_factory=dict)
    reminders: dict[str, ReminderRecord] = Field(default_factory=dict)
    companion_notes: dict[str, CompanionNoteRecord] = Field(default_factory=dict)
    session_digests: dict[str, SessionDigestRecord] = Field(default_factory=dict)
    memory_actions: list[MemoryActionRecord] = Field(default_factory=list)
    memory_reviews: list[MemoryReviewRecord] = Field(default_factory=list)
    memory_retrievals: list[MemoryRetrievalRecord] = Field(default_factory=list)
    teacher_annotations: list[TeacherAnnotationRecord] = Field(default_factory=list)
    traces: list[TraceRecord] = Field(default_factory=list)
    executive_decisions: list[ExecutiveDecisionRecord] = Field(default_factory=list)
    incidents: dict[str, IncidentTicketRecord] = Field(default_factory=dict)
    incident_timeline: list[IncidentTimelineRecord] = Field(default_factory=list)
    perception_snapshots: list[PerceptionSnapshotRecord] = Field(default_factory=list)
    world_model_transitions: list[WorldModelTransitionRecord] = Field(default_factory=list)
    shift_transitions: list[ShiftTransitionRecord] = Field(default_factory=list)
    world_model: EmbodiedWorldModel = Field(default_factory=EmbodiedWorldModel)
    shift_supervisor: ShiftSupervisorSnapshot = Field(default_factory=ShiftSupervisorSnapshot)
    participant_router: ParticipantRouterSnapshot = Field(default_factory=ParticipantRouterSnapshot)
    world_state: WorldState = Field(default_factory=WorldState)


class MemoryStore:
    """Small JSON-backed store for local session, user, and trace state."""

    def __init__(self, store_path: str | Path | None = None) -> None:
        self._path = Path(store_path) if store_path else None
        self._lock = RLock()
        self._persist_suspend_depth = 0
        self._persist_dirty = False
        self._persist_metrics_local = local()
        self._snapshot = self._load()

    def _load(self) -> BrainStoreSnapshot:
        if self._path is None or not self._path.exists():
            return BrainStoreSnapshot()
        try:
            loaded = load_json_model_or_quarantine(self._path, BrainStoreSnapshot, quarantine_invalid=True)
            if loaded is not None:
                return loaded
            backup_path = self._backup_invalid_store()
            if backup_path is not None:
                logger.warning(
                    "Recovered from invalid brain store at %s and moved it to %s.",
                    self._path,
                    backup_path,
                )
            else:
                logger.warning(
                    "Recovered from invalid brain store at %s by starting with an empty snapshot.",
                    self._path,
                )
        except Exception:
            logger.exception("Recovered from invalid brain store at %s by starting with an empty snapshot.", self._path)
        return BrainStoreSnapshot()

    def _persist_now_locked(self) -> None:
        if self._path is None:
            return
        self._path.parent.mkdir(parents=True, exist_ok=True)
        started = perf_counter()
        write_json_atomic(self._path, self._snapshot, keep_backups=3)
        duration_ms = round((perf_counter() - started) * 1000.0, 2)
        metrics = getattr(self._persist_metrics_local, "active", None)
        if metrics is not None:
            metrics.write_count += 1
            metrics.total_ms = round(metrics.total_ms + duration_ms, 2)

    def _persist(self) -> None:
        with self._lock:
            if self._persist_suspend_depth > 0:
                self._persist_dirty = True
                return
            self._persist_now_locked()

    @contextmanager
    def batch_update(self):
        with self._lock:
            self._persist_suspend_depth += 1
        try:
            yield self
        finally:
            with self._lock:
                self._persist_suspend_depth = max(0, self._persist_suspend_depth - 1)
                should_flush = self._persist_suspend_depth == 0 and self._persist_dirty
                if should_flush:
                    self._persist_dirty = False
                    self._persist_now_locked()

    @contextmanager
    def capture_persist_metrics(self):
        previous = getattr(self._persist_metrics_local, "active", None)
        metrics = PersistMetricsSnapshot()
        self._persist_metrics_local.active = metrics
        try:
            yield metrics
        finally:
            if previous is None:
                try:
                    del self._persist_metrics_local.active
                except AttributeError:
                    pass
            else:
                self._persist_metrics_local.active = previous

    def snapshot(self) -> dict:
        with self._lock:
            return self._snapshot.model_dump(mode="json")

    def reset(self, *, clear_user_memory: bool = True) -> None:
        with self._lock:
            user_memory = {} if clear_user_memory else self._snapshot.user_memory
            relationship_memory = {} if clear_user_memory else self._snapshot.relationship_memory
            procedural_memory = {} if clear_user_memory else self._snapshot.procedural_memory
            self._snapshot = BrainStoreSnapshot(
                user_memory=user_memory,
                relationship_memory=relationship_memory,
                procedural_memory=procedural_memory,
            )
            self._persist()

    def create_session(self, request: SessionCreateRequest) -> SessionRecord:
        with self._lock:
            session_id = request.session_id or f"session-{utc_now().strftime('%Y%m%d%H%M%S%f')}"
            existing = self._snapshot.sessions.get(session_id)
            if existing is not None:
                return existing.model_copy(deep=True)

            session = SessionRecord(
                session_id=session_id,
                user_id=request.user_id,
                channel=request.channel,
                scenario_name=request.scenario_name,
                response_mode=request.response_mode,
                operator_notes=[OperatorNote(text=note) for note in request.operator_notes],
            )
            self._snapshot.sessions[session_id] = session
            if request.user_id:
                self._sync_user_memory_locked(
                    user_id=request.user_id,
                    session_id=session_id,
                    response_mode=request.response_mode,
                    increment_visit=True,
                )
            self._persist()
            return session.model_copy(deep=True)

    def ensure_session(
        self,
        session_id: str,
        *,
        user_id: str | None = None,
        channel: str = "speech",
        scenario_name: str | None = None,
        response_mode=None,
    ) -> SessionRecord:
        with self._lock:
            existing = self._snapshot.sessions.get(session_id)
            if existing is not None:
                session = existing.model_copy(deep=True)
                changed = False
                linked_new_user = False
                if user_id and session.user_id is None:
                    session.user_id = user_id
                    changed = True
                    linked_new_user = True
                if scenario_name and session.scenario_name is None:
                    session.scenario_name = scenario_name
                    changed = True
                if response_mode and session.response_mode != response_mode:
                    session.response_mode = response_mode
                    changed = True
                if changed:
                    session.updated_at = utc_now()
                    self._snapshot.sessions[session_id] = session
                    if session.user_id:
                        self._sync_user_memory_locked(
                            user_id=session.user_id,
                            session_id=session_id,
                            response_mode=session.response_mode,
                            increment_visit=linked_new_user,
                        )
                    self._persist()
                return session.model_copy(deep=True)

        return self.create_session(
            SessionCreateRequest(
                session_id=session_id,
                user_id=user_id,
                channel=channel,
                scenario_name=scenario_name,
                response_mode=response_mode or SessionCreateRequest().response_mode,
            )
        )

    def upsert_session(self, session: SessionRecord) -> SessionRecord:
        with self._lock:
            session.updated_at = utc_now()
            self._snapshot.sessions[session.session_id] = session
            self._persist()
            return session.model_copy(deep=True)

    def get_session(self, session_id: str) -> SessionRecord | None:
        with self._lock:
            session = self._snapshot.sessions.get(session_id)
            if session is None:
                return None
            return session.model_copy(deep=True)

    def list_sessions(self) -> SessionListResponse:
        with self._lock:
            items = [
                SessionSummary(
                    session_id=session.session_id,
                    user_id=session.user_id,
                    scenario_name=session.scenario_name,
                    status=session.status,
                    routing_status=session.routing_status,
                    participant_id=session.participant_id,
                    active_incident_ticket_id=session.active_incident_ticket_id,
                    incident_status=session.incident_status,
                    response_mode=session.response_mode,
                    current_topic=session.current_topic,
                    conversation_summary=session.conversation_summary,
                    last_reply_text=session.last_reply_text,
                    turn_count=len(session.transcript),
                    updated_at=session.updated_at,
                )
                for session in sorted(
                    self._snapshot.sessions.values(),
                    key=lambda item: item.updated_at,
                    reverse=True,
                )
            ]
            return SessionListResponse(items=items)

    def upsert_user_memory(self, record: UserMemoryRecord) -> UserMemoryRecord:
        with self._lock:
            record.updated_at = utc_now()
            self._snapshot.user_memory[record.user_id] = record
            self._persist()
            return record.model_copy(deep=True)

    def get_user_memory(self, user_id: str) -> UserMemoryRecord | None:
        with self._lock:
            record = self._snapshot.user_memory.get(user_id)
            if record is None:
                return None
            return record.model_copy(deep=True)

    def upsert_relationship_memory(self, record: RelationshipMemoryRecord) -> RelationshipMemoryRecord:
        with self._lock:
            record.updated_at = utc_now()
            self._snapshot.relationship_memory[record.relationship_id] = record
            self._persist()
            return record.model_copy(deep=True)

    def get_relationship_memory(self, relationship_id: str) -> RelationshipMemoryRecord | None:
        with self._lock:
            record = self._snapshot.relationship_memory.get(relationship_id)
            if record is None:
                return None
            return record.model_copy(deep=True)

    def list_relationship_memory(
        self,
        *,
        user_id: str | None = None,
        limit: int = 50,
        include_tombstoned: bool = False,
    ) -> RelationshipMemoryListResponse:
        with self._lock:
            items = list(self._snapshot.relationship_memory.values())
            if user_id:
                items = [item for item in items if item.user_id == user_id]
            if not include_tombstoned:
                items = [item for item in items if not item.tombstoned]
            items.sort(key=lambda item: item.updated_at, reverse=True)
            return RelationshipMemoryListResponse(items=[item.model_copy(deep=True) for item in items[:limit]])

    def get_episodic_memory(self, memory_id: str) -> EpisodicMemoryRecord | None:
        with self._lock:
            record = self._snapshot.episodic_memory.get(memory_id)
            if record is None:
                return None
            return record.model_copy(deep=True)

    def upsert_episodic_memory(self, record: EpisodicMemoryRecord) -> EpisodicMemoryRecord:
        with self._lock:
            record.updated_at = utc_now()
            self._snapshot.episodic_memory[record.memory_id] = record
            self._persist()
            return record.model_copy(deep=True)

    def list_episodic_memory(
        self,
        *,
        session_id: str | None = None,
        user_id: str | None = None,
        limit: int = 50,
        include_tombstoned: bool = False,
    ) -> EpisodicMemoryListResponse:
        with self._lock:
            items = list(self._snapshot.episodic_memory.values())
            if session_id:
                items = [item for item in items if item.session_id == session_id]
            if user_id:
                items = [item for item in items if item.user_id == user_id]
            if not include_tombstoned:
                items = [item for item in items if not item.tombstoned]
            items.sort(key=lambda item: item.updated_at, reverse=True)
            return EpisodicMemoryListResponse(items=[item.model_copy(deep=True) for item in items[:limit]])

    def get_semantic_memory(self, memory_id: str) -> SemanticMemoryRecord | None:
        with self._lock:
            record = self._snapshot.semantic_memory.get(memory_id)
            if record is None:
                return None
            return record.model_copy(deep=True)

    def upsert_semantic_memory(self, record: SemanticMemoryRecord) -> SemanticMemoryRecord:
        with self._lock:
            record.updated_at = utc_now()
            self._snapshot.semantic_memory[record.memory_id] = record
            self._persist()
            return record.model_copy(deep=True)

    def list_semantic_memory(
        self,
        *,
        session_id: str | None = None,
        user_id: str | None = None,
        limit: int = 100,
        include_tombstoned: bool = False,
    ) -> SemanticMemoryListResponse:
        with self._lock:
            items = list(self._snapshot.semantic_memory.values())
            if session_id:
                items = [item for item in items if item.session_id == session_id]
            if user_id:
                items = [item for item in items if item.user_id == user_id]
            if not include_tombstoned:
                items = [item for item in items if not item.tombstoned]
            items.sort(key=lambda item: item.updated_at, reverse=True)
            return SemanticMemoryListResponse(items=[item.model_copy(deep=True) for item in items[:limit]])

    def upsert_procedural_memory(self, record: ProceduralMemoryRecord) -> ProceduralMemoryRecord:
        with self._lock:
            record.updated_at = utc_now()
            self._snapshot.procedural_memory[record.procedure_id] = record
            self._persist()
            return record.model_copy(deep=True)

    def get_procedural_memory(self, procedure_id: str) -> ProceduralMemoryRecord | None:
        with self._lock:
            record = self._snapshot.procedural_memory.get(procedure_id)
            if record is None:
                return None
            return record.model_copy(deep=True)

    def list_procedural_memory(
        self,
        *,
        session_id: str | None = None,
        user_id: str | None = None,
        limit: int = 100,
        include_tombstoned: bool = False,
    ) -> ProceduralMemoryListResponse:
        with self._lock:
            items = list(self._snapshot.procedural_memory.values())
            if session_id:
                items = [item for item in items if item.session_id == session_id]
            if user_id:
                items = [item for item in items if item.user_id == user_id]
            if not include_tombstoned:
                items = [item for item in items if not item.tombstoned]
            items.sort(key=lambda item: item.updated_at, reverse=True)
            return ProceduralMemoryListResponse(items=[item.model_copy(deep=True) for item in items[:limit]])

    def upsert_reminder(self, record: ReminderRecord) -> ReminderRecord:
        with self._lock:
            record.updated_at = utc_now()
            self._snapshot.reminders[record.reminder_id] = record
            self._persist()
            return record.model_copy(deep=True)

    def get_reminder(self, reminder_id: str) -> ReminderRecord | None:
        with self._lock:
            record = self._snapshot.reminders.get(reminder_id)
            if record is None:
                return None
            return record.model_copy(deep=True)

    def list_reminders(
        self,
        *,
        session_id: str | None = None,
        user_id: str | None = None,
        status: ReminderStatus | None = None,
        limit: int = 100,
        include_tombstoned: bool = False,
    ) -> ReminderListResponse:
        with self._lock:
            items = list(self._snapshot.reminders.values())
            if session_id:
                items = [item for item in items if item.session_id == session_id]
            if user_id:
                items = [item for item in items if item.user_id == user_id]
            if status is not None:
                items = [item for item in items if item.status == status]
            if not include_tombstoned:
                items = [item for item in items if not item.tombstoned]
            items.sort(
                key=lambda item: (
                    item.due_at or item.updated_at,
                    item.updated_at,
                ),
                reverse=True,
            )
            return ReminderListResponse(items=[item.model_copy(deep=True) for item in items[:limit]])

    def upsert_companion_note(self, record: CompanionNoteRecord) -> CompanionNoteRecord:
        with self._lock:
            record.updated_at = utc_now()
            self._snapshot.companion_notes[record.note_id] = record
            self._persist()
            return record.model_copy(deep=True)

    def get_companion_note(self, note_id: str) -> CompanionNoteRecord | None:
        with self._lock:
            record = self._snapshot.companion_notes.get(note_id)
            if record is None:
                return None
            return record.model_copy(deep=True)

    def list_companion_notes(
        self,
        *,
        session_id: str | None = None,
        user_id: str | None = None,
        limit: int = 100,
        include_tombstoned: bool = False,
    ) -> CompanionNoteListResponse:
        with self._lock:
            items = list(self._snapshot.companion_notes.values())
            if session_id:
                items = [item for item in items if item.session_id == session_id]
            if user_id:
                items = [item for item in items if item.user_id == user_id]
            if not include_tombstoned:
                items = [item for item in items if not item.tombstoned]
            items.sort(key=lambda item: item.updated_at, reverse=True)
            return CompanionNoteListResponse(items=[item.model_copy(deep=True) for item in items[:limit]])

    def upsert_session_digest(self, record: SessionDigestRecord) -> SessionDigestRecord:
        with self._lock:
            record.updated_at = utc_now()
            self._snapshot.session_digests[record.digest_id] = record
            self._persist()
            return record.model_copy(deep=True)

    def get_session_digest(self, digest_id: str) -> SessionDigestRecord | None:
        with self._lock:
            record = self._snapshot.session_digests.get(digest_id)
            if record is None:
                return None
            return record.model_copy(deep=True)

    def list_session_digests(
        self,
        *,
        session_id: str | None = None,
        user_id: str | None = None,
        limit: int = 50,
        include_tombstoned: bool = False,
    ) -> SessionDigestListResponse:
        with self._lock:
            items = list(self._snapshot.session_digests.values())
            if session_id:
                items = [item for item in items if item.session_id == session_id]
            if user_id:
                items = [item for item in items if item.user_id == user_id]
            if not include_tombstoned:
                items = [item for item in items if not item.tombstoned]
            items.sort(key=lambda item: item.updated_at, reverse=True)
            return SessionDigestListResponse(items=[item.model_copy(deep=True) for item in items[:limit]])

    def append_memory_actions(self, records: list[MemoryActionRecord]) -> MemoryActionListResponse:
        with self._lock:
            self._snapshot.memory_actions.extend(records)
            self._persist()
            return MemoryActionListResponse(items=[item.model_copy(deep=True) for item in records])

    def list_memory_actions(
        self,
        *,
        session_id: str | None = None,
        user_id: str | None = None,
        trace_id: str | None = None,
        memory_id: str | None = None,
        limit: int = 100,
    ) -> MemoryActionListResponse:
        with self._lock:
            items = list(reversed(self._snapshot.memory_actions))
            if session_id:
                items = [item for item in items if item.session_id == session_id]
            if user_id:
                items = [item for item in items if item.user_id == user_id]
            if trace_id:
                items = [item for item in items if item.trace_id == trace_id]
            if memory_id:
                items = [item for item in items if item.memory_id == memory_id]
            return MemoryActionListResponse(items=[item.model_copy(deep=True) for item in items[:limit]])

    def append_memory_reviews(self, records: list[MemoryReviewRecord]) -> MemoryReviewListResponse:
        with self._lock:
            self._snapshot.memory_reviews.extend(records)
            self._persist()
            return MemoryReviewListResponse(items=[item.model_copy(deep=True) for item in records])

    def list_memory_reviews(
        self,
        *,
        memory_id: str | None = None,
        limit: int = 100,
    ) -> MemoryReviewListResponse:
        with self._lock:
            items = list(reversed(self._snapshot.memory_reviews))
            if memory_id:
                items = [item for item in items if item.memory_id == memory_id]
            return MemoryReviewListResponse(items=[item.model_copy(deep=True) for item in items[:limit]])

    def append_memory_retrievals(self, records: list[MemoryRetrievalRecord]) -> MemoryRetrievalListResponse:
        with self._lock:
            self._snapshot.memory_retrievals.extend(records)
            self._persist()
            return MemoryRetrievalListResponse(items=[item.model_copy(deep=True) for item in records])

    def list_memory_retrievals(
        self,
        *,
        session_id: str | None = None,
        user_id: str | None = None,
        trace_id: str | None = None,
        run_id: str | None = None,
        backend=None,
        limit: int = 100,
    ) -> MemoryRetrievalListResponse:
        with self._lock:
            items = list(reversed(self._snapshot.memory_retrievals))
            if session_id:
                items = [item for item in items if item.session_id == session_id]
            if user_id:
                items = [item for item in items if item.user_id == user_id]
            if trace_id:
                items = [item for item in items if item.trace_id == trace_id]
            if run_id:
                items = [item for item in items if item.run_id == run_id]
            if backend is not None:
                items = [item for item in items if item.backend == backend]
            return MemoryRetrievalListResponse(items=[item.model_copy(deep=True) for item in items[:limit]])

    def attach_trace_to_memory_retrievals(self, *, run_id: str, trace_id: str) -> None:
        with self._lock:
            changed = False
            for index, existing in enumerate(self._snapshot.memory_retrievals):
                if existing.run_id == run_id and existing.trace_id is None:
                    updated = existing.model_copy(deep=True)
                    updated.trace_id = trace_id
                    updated.updated_at = utc_now()
                    self._snapshot.memory_retrievals[index] = updated
                    changed = True
            if changed:
                self._persist()

    def memory_review_debt_summary(self) -> MemoryReviewDebtSummary:
        debt_items: list[tuple[str, float, object, str]] = []
        for collection in (
            self._snapshot.user_memory.values(),
            self._snapshot.relationship_memory.values(),
            self._snapshot.episodic_memory.values(),
            self._snapshot.semantic_memory.values(),
            self._snapshot.procedural_memory.values(),
            self._snapshot.reminders.values(),
            self._snapshot.companion_notes.values(),
            self._snapshot.session_digests.values(),
        ):
            for item in collection:
                if item.review_debt_state.value == "clear":
                    continue
                memory_id = (
                    getattr(item, "memory_id", None)
                    or getattr(item, "relationship_id", None)
                    or getattr(item, "procedure_id", None)
                    or getattr(item, "user_id", None)
                    or getattr(item, "reminder_id", None)
                    or getattr(item, "note_id", None)
                    or getattr(item, "digest_id", None)
                )
                if memory_id is None:
                    continue
                debt_items.append(
                    (
                        memory_id,
                        item.policy_scorecard.review_priority,
                        item.updated_at,
                        item.review_debt_state.value,
                    )
                )
        pending = [item for item in debt_items if item[1] >= 0.0]
        overdue = [item for item in debt_items if item[3] == "overdue"]
        pending.sort(key=lambda item: item[2])  # oldest first for debt visibility
        return MemoryReviewDebtSummary(
            pending_count=len(pending),
            overdue_count=len(overdue),
            highest_priority=max((item[1] for item in pending), default=0.0),
            oldest_pending_at=(pending[0][2] if pending else None),
            memory_ids=[item[0] for item in pending[:20]],
        )

    def upsert_teacher_annotation(self, record: TeacherAnnotationRecord) -> TeacherAnnotationRecord:
        with self._lock:
            for index, existing in enumerate(self._snapshot.teacher_annotations):
                if existing.annotation_id == record.annotation_id:
                    record.updated_at = utc_now()
                    self._snapshot.teacher_annotations[index] = record
                    self._persist()
                    return record.model_copy(deep=True)
            record.updated_at = utc_now()
            self._snapshot.teacher_annotations.append(record)
            self._persist()
            return record.model_copy(deep=True)

    def list_teacher_annotations(
        self,
        *,
        trace_id: str | None = None,
        run_id: str | None = None,
        action_id: str | None = None,
        workflow_run_id: str | None = None,
        memory_id: str | None = None,
        episode_id: str | None = None,
        limit: int = 100,
    ) -> TeacherAnnotationListResponse:
        with self._lock:
            items = list(reversed(self._snapshot.teacher_annotations))
            if trace_id:
                items = [item for item in items if item.trace_id == trace_id]
            if run_id:
                items = [item for item in items if item.run_id == run_id]
            if action_id:
                items = [item for item in items if item.action_id == action_id]
            if workflow_run_id:
                items = [item for item in items if item.workflow_run_id == workflow_run_id]
            if memory_id:
                items = [item for item in items if item.memory_id == memory_id]
            if episode_id:
                items = [item for item in items if item.episode_id == episode_id]
            return TeacherAnnotationListResponse(items=[item.model_copy(deep=True) for item in items[:limit]])

    def replace_world_state(self, world_state: WorldState) -> WorldState:
        with self._lock:
            world_state.updated_at = utc_now()
            self._snapshot.world_state = world_state
            self._persist()
            return world_state.model_copy(deep=True)

    def get_world_state(self) -> WorldState:
        with self._lock:
            return self._snapshot.world_state.model_copy(deep=True)

    def replace_world_model(self, world_model: EmbodiedWorldModel) -> EmbodiedWorldModel:
        with self._lock:
            world_model.last_updated = utc_now()
            self._snapshot.world_model = world_model
            self._persist()
            return world_model.model_copy(deep=True)

    def get_world_model(self) -> EmbodiedWorldModel:
        with self._lock:
            return self._snapshot.world_model.model_copy(deep=True)

    def replace_shift_supervisor(self, snapshot: ShiftSupervisorSnapshot) -> ShiftSupervisorSnapshot:
        with self._lock:
            snapshot.updated_at = utc_now()
            self._snapshot.shift_supervisor = snapshot
            self._persist()
            return snapshot.model_copy(deep=True)

    def get_shift_supervisor(self) -> ShiftSupervisorSnapshot:
        with self._lock:
            return self._snapshot.shift_supervisor.model_copy(deep=True)

    def replace_participant_router(self, snapshot: ParticipantRouterSnapshot) -> ParticipantRouterSnapshot:
        with self._lock:
            snapshot.updated_at = utc_now()
            self._snapshot.participant_router = snapshot
            self._persist()
            return snapshot.model_copy(deep=True)

    def get_participant_router(self) -> ParticipantRouterSnapshot:
        with self._lock:
            return self._snapshot.participant_router.model_copy(deep=True)

    def append_trace(self, trace: TraceRecord) -> TraceRecord:
        with self._lock:
            self._snapshot.traces.append(trace)
            self._persist()
            return trace.model_copy(deep=True)

    def update_trace(self, trace: TraceRecord) -> TraceRecord:
        with self._lock:
            for index, existing in enumerate(self._snapshot.traces):
                if existing.trace_id == trace.trace_id:
                    self._snapshot.traces[index] = trace
                    self._persist()
                    return trace.model_copy(deep=True)
            raise KeyError(trace.trace_id)

    def append_executive_decisions(self, decisions: list[ExecutiveDecisionRecord]) -> ExecutiveDecisionListResponse:
        with self._lock:
            self._snapshot.executive_decisions.extend(decisions)
            self._persist()
            return ExecutiveDecisionListResponse(items=[item.model_copy(deep=True) for item in decisions])

    def upsert_incident_ticket(self, ticket: IncidentTicketRecord) -> IncidentTicketRecord:
        with self._lock:
            ticket.updated_at = utc_now()
            self._snapshot.incidents[ticket.ticket_id] = ticket
            self._persist()
            return ticket.model_copy(deep=True)

    def get_incident_ticket(self, ticket_id: str) -> IncidentTicketRecord | None:
        with self._lock:
            ticket = self._snapshot.incidents.get(ticket_id)
            if ticket is None:
                return None
            return ticket.model_copy(deep=True)

    def list_incident_tickets(
        self,
        *,
        scope: IncidentListScope = IncidentListScope.ALL,
        session_id: str | None = None,
        limit: int = 50,
    ) -> IncidentListResponse:
        with self._lock:
            return IncidentListResponse(items=self._filter_incidents(scope=scope, session_id=session_id, limit=limit))

    def append_incident_timeline(
        self,
        records: list[IncidentTimelineRecord],
    ) -> IncidentTimelineResponse:
        with self._lock:
            self._snapshot.incident_timeline.extend(records)
            self._persist()
            return IncidentTimelineResponse(items=[item.model_copy(deep=True) for item in records])

    def list_incident_timeline(
        self,
        *,
        ticket_id: str | None = None,
        session_id: str | None = None,
        limit: int = 100,
    ) -> IncidentTimelineResponse:
        with self._lock:
            items = list(reversed(self._snapshot.incident_timeline))
            if ticket_id:
                items = [item for item in items if item.ticket_id == ticket_id]
            if session_id:
                items = [item for item in items if item.session_id == session_id]
            return IncidentTimelineResponse(items=[item.model_copy(deep=True) for item in items[:limit]])

    def list_executive_decisions(self, session_id: str | None = None, limit: int = 25) -> ExecutiveDecisionListResponse:
        with self._lock:
            items = list(reversed(self._snapshot.executive_decisions))
            if session_id:
                items = [item for item in items if item.session_id == session_id]
            return ExecutiveDecisionListResponse(items=[item.model_copy(deep=True) for item in items[:limit]])

    def append_shift_transitions(self, transitions: list[ShiftTransitionRecord]) -> ShiftTransitionListResponse:
        with self._lock:
            self._snapshot.shift_transitions.extend(transitions)
            self._persist()
            return ShiftTransitionListResponse(items=[item.model_copy(deep=True) for item in transitions])

    def list_shift_transitions(
        self,
        session_id: str | None = None,
        limit: int = 50,
    ) -> ShiftTransitionListResponse:
        with self._lock:
            items = list(reversed(self._snapshot.shift_transitions))
            if session_id:
                items = [item for item in items if item.session_id == session_id]
            return ShiftTransitionListResponse(items=[item.model_copy(deep=True) for item in items[:limit]])

    def append_perception_snapshot(self, snapshot: PerceptionSnapshotRecord) -> PerceptionSnapshotRecord:
        with self._lock:
            self._snapshot.perception_snapshots.append(snapshot)
            self._persist()
            return snapshot.model_copy(deep=True)

    def upsert_perception_snapshot(self, snapshot: PerceptionSnapshotRecord) -> PerceptionSnapshotRecord:
        with self._lock:
            for index, existing in enumerate(self._snapshot.perception_snapshots):
                if existing.snapshot_id == snapshot.snapshot_id:
                    self._snapshot.perception_snapshots[index] = snapshot
                    self._persist()
                    return snapshot.model_copy(deep=True)
            self._snapshot.perception_snapshots.append(snapshot)
            self._persist()
            return snapshot.model_copy(deep=True)

    def get_latest_perception(self, session_id: str | None = None) -> PerceptionSnapshotRecord | None:
        with self._lock:
            snapshots = self._filter_perception(session_id=session_id, limit=1)
            if not snapshots:
                return None
            return snapshots[0]

    def list_perception_history(self, session_id: str | None = None, limit: int = 20) -> PerceptionHistoryResponse:
        with self._lock:
            return PerceptionHistoryResponse(items=self._filter_perception(session_id=session_id, limit=limit))

    def append_world_model_transition(self, transition: WorldModelTransitionRecord) -> WorldModelTransitionRecord:
        with self._lock:
            self._snapshot.world_model_transitions.append(transition)
            self._persist()
            return transition.model_copy(deep=True)

    def list_world_model_transitions(
        self,
        session_id: str | None = None,
        limit: int = 50,
    ) -> WorldModelTransitionListResponse:
        with self._lock:
            items = list(reversed(self._snapshot.world_model_transitions))
            if session_id:
                items = [item for item in items if item.session_id == session_id]
            return WorldModelTransitionListResponse(items=[item.model_copy(deep=True) for item in items[:limit]])

    def list_engagement_timeline(
        self,
        session_id: str | None = None,
        limit: int = 50,
    ) -> list[EngagementTimelinePoint]:
        transitions = self.list_world_model_transitions(session_id=session_id, limit=limit).items
        timeline: list[EngagementTimelinePoint] = []
        last_signature: tuple | None = None
        for transition in reversed(transitions):
            after = transition.after
            signature = (
                after.engagement_state,
                after.attention_target.target_label if after.attention_target else None,
                after.engagement_confidence.score,
            )
            if signature == last_signature:
                continue
            last_signature = signature
            timeline.append(
                EngagementTimelinePoint(
                    timestamp=transition.created_at,
                    session_id=transition.session_id,
                    engagement_state=after.engagement_state,
                    attention_target=after.attention_target.target_label if after.attention_target else None,
                    confidence=after.engagement_confidence,
                    source_event_type=transition.source_event_type,
                )
            )
        return timeline[-limit:]

    def list_logs(self, session_id: str | None = None, limit: int = 50) -> LogListResponse:
        with self._lock:
            traces = self._filter_traces(session_id=session_id, limit=limit)
            return LogListResponse(
                items=[
                    TraceSummary(
                        trace_id=trace.trace_id,
                        session_id=trace.session_id,
                        timestamp=trace.timestamp,
                        event_type=trace.event.event_type,
                        intent=trace.reasoning.intent,
                        engine=trace.reasoning.engine,
                        fallback_used=trace.reasoning.fallback_used,
                        run_id=trace.reasoning.run_id,
                        run_phase=trace.reasoning.run_phase,
                        run_status=trace.reasoning.run_status,
                        active_skill=(
                            trace.reasoning.active_skill.skill_name
                            if trace.reasoning.active_skill is not None
                            else None
                        ),
                        active_playbook=trace.reasoning.active_playbook,
                        active_playbook_variant=trace.reasoning.active_playbook_variant,
                        active_subagent=trace.reasoning.active_subagent,
                        reply_text=trace.response.reply_text,
                        command_types=[command.command_type for command in trace.response.commands],
                        tool_names=[tool.tool_name for tool in trace.reasoning.typed_tool_calls],
                        validation_statuses=[item.status for item in trace.reasoning.validation_outcomes],
                        checkpoint_count=trace.reasoning.checkpoint_count,
                        last_checkpoint_id=trace.reasoning.last_checkpoint_id,
                        failure_state=trace.reasoning.failure_state,
                        fallback_reason=trace.reasoning.fallback_reason,
                        fallback_classification=trace.reasoning.fallback_classification,
                        unavailable_capabilities=list(trace.reasoning.unavailable_capabilities),
                        intentionally_skipped_capabilities=list(trace.reasoning.intentionally_skipped_capabilities),
                        recovery_status=trace.reasoning.recovery_status,
                        executive_state=trace.reasoning.executive_state,
                        social_runtime_mode=trace.reasoning.social_runtime_mode,
                        grounded_reference_labels=[item.label for item in trace.reasoning.grounded_scene_references[:6]],
                        uncertainty_admitted=trace.reasoning.uncertainty_admitted,
                        stale_scene_suppressed=trace.reasoning.stale_scene_suppressed,
                        executive_reason_codes=[
                            reason
                            for decision in trace.reasoning.executive_decisions
                            for reason in decision.reason_codes
                        ],
                        shift_state=trace.reasoning.shift_supervisor.state if trace.reasoning.shift_supervisor else None,
                        shift_reason_codes=trace.reasoning.shift_supervisor.reason_codes if trace.reasoning.shift_supervisor else [],
                        incident_ticket_id=trace.reasoning.incident_ticket.ticket_id if trace.reasoning.incident_ticket else None,
                        incident_status=trace.reasoning.incident_ticket.current_status if trace.reasoning.incident_ticket else None,
                        latency_ms=trace.latency_ms,
                        outcome=trace.outcome,
                    )
                    for trace in traces
                ]
            )

    def list_traces(self, session_id: str | None = None, limit: int = 50) -> TraceListResponse:
        with self._lock:
            return TraceListResponse(items=self._filter_traces(session_id=session_id, limit=limit))

    def get_trace(self, trace_id: str) -> TraceRecord | None:
        with self._lock:
            for trace in reversed(self._snapshot.traces):
                if trace.trace_id == trace_id:
                    return trace.model_copy(deep=True)
            return None

    def add_operator_note(self, session_id: str, note: OperatorNote) -> SessionRecord:
        session = self.get_session(session_id)
        if session is None:
            raise KeyError(session_id)
        session.operator_notes.append(note)
        return self.upsert_session(session)

    def _filter_traces(self, session_id: str | None, limit: int) -> list[TraceRecord]:
        traces = list(reversed(self._snapshot.traces))
        if session_id:
            traces = [trace for trace in traces if trace.session_id == session_id]
        return [trace.model_copy(deep=True) for trace in traces[:limit]]

    def _filter_incidents(
        self,
        *,
        scope: IncidentListScope,
        session_id: str | None,
        limit: int,
    ) -> list[IncidentTicketRecord]:
        items = list(self._snapshot.incidents.values())
        if session_id:
            items = [item for item in items if item.session_id == session_id]
        open_statuses = {"pending", "acknowledged", "assigned"}
        if scope == IncidentListScope.OPEN:
            items = [item for item in items if item.current_status.value in open_statuses]
        elif scope == IncidentListScope.CLOSED:
            items = [item for item in items if item.current_status.value not in open_statuses]
        items.sort(key=lambda item: item.updated_at, reverse=True)
        return [item.model_copy(deep=True) for item in items[:limit]]

    def _filter_perception(self, session_id: str | None, limit: int) -> list[PerceptionSnapshotRecord]:
        items = list(reversed(self._snapshot.perception_snapshots))
        if session_id:
            items = [item for item in items if item.session_id == session_id]
        return [item.model_copy(deep=True) for item in items[:limit]]

    def _sync_user_memory_locked(
        self,
        *,
        user_id: str,
        session_id: str,
        response_mode,
        increment_visit: bool,
    ) -> None:
        user_memory = self._snapshot.user_memory.get(user_id) or UserMemoryRecord(user_id=user_id)
        if increment_visit:
            user_memory.visit_count += 1
        user_memory.last_session_id = session_id
        if response_mode is not None:
            user_memory.preferred_response_mode = response_mode
        user_memory.updated_at = utc_now()
        self._snapshot.user_memory[user_id] = user_memory

    def _backup_invalid_store(self) -> Path | None:
        if self._path is None or not self._path.exists():
            return None
        try:
            return quarantine_invalid_file(self._path)
        except OSError:
            logger.exception("Failed to move invalid brain store at %s out of the active path.", self._path)
            return None
