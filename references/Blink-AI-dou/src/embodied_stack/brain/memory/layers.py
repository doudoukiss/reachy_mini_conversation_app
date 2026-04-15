from __future__ import annotations

from dataclasses import dataclass

from embodied_stack.shared.contracts.brain import (
    EpisodicMemoryListResponse,
    MemoryActionListResponse,
    MemoryRetrievalBackend,
    MemoryRetrievalListResponse,
    MemoryReviewDebtSummary,
    MemoryReviewListResponse,
    ProceduralMemoryListResponse,
    RelationshipMemoryListResponse,
    SemanticMemoryListResponse,
    RelationshipMemoryRecord,
    UserMemoryRecord,
)
from embodied_stack.shared.contracts.episode import TeacherAnnotationListResponse
from .store import MemoryStore


@dataclass
class MemoryLayerService:
    memory_store: MemoryStore

    def get_profile(self, user_id: str) -> UserMemoryRecord | None:
        return self.memory_store.get_user_memory(user_id)

    def get_relationship(self, user_id: str) -> RelationshipMemoryRecord | None:
        return self.memory_store.get_relationship_memory(user_id)

    def list_episodic(
        self,
        *,
        session_id: str | None = None,
        user_id: str | None = None,
        limit: int = 50,
        include_tombstoned: bool = False,
    ) -> EpisodicMemoryListResponse:
        return self.memory_store.list_episodic_memory(
            session_id=session_id,
            user_id=user_id,
            limit=limit,
            include_tombstoned=include_tombstoned,
        )

    def list_semantic(
        self,
        *,
        session_id: str | None = None,
        user_id: str | None = None,
        limit: int = 100,
        include_tombstoned: bool = False,
    ) -> SemanticMemoryListResponse:
        return self.memory_store.list_semantic_memory(
            session_id=session_id,
            user_id=user_id,
            limit=limit,
            include_tombstoned=include_tombstoned,
        )

    def list_relationship(
        self,
        *,
        user_id: str | None = None,
        limit: int = 50,
        include_tombstoned: bool = False,
    ) -> RelationshipMemoryListResponse:
        return self.memory_store.list_relationship_memory(
            user_id=user_id,
            limit=limit,
            include_tombstoned=include_tombstoned,
        )

    def list_procedural(
        self,
        *,
        session_id: str | None = None,
        user_id: str | None = None,
        limit: int = 100,
        include_tombstoned: bool = False,
    ) -> ProceduralMemoryListResponse:
        return self.memory_store.list_procedural_memory(
            session_id=session_id,
            user_id=user_id,
            limit=limit,
            include_tombstoned=include_tombstoned,
        )

    def list_actions(
        self,
        *,
        session_id: str | None = None,
        user_id: str | None = None,
        trace_id: str | None = None,
        memory_id: str | None = None,
        limit: int = 100,
    ) -> MemoryActionListResponse:
        return self.memory_store.list_memory_actions(
            session_id=session_id,
            user_id=user_id,
            trace_id=trace_id,
            memory_id=memory_id,
            limit=limit,
        )

    def list_reviews(
        self,
        *,
        memory_id: str | None = None,
        limit: int = 100,
    ) -> MemoryReviewListResponse:
        return self.memory_store.list_memory_reviews(memory_id=memory_id, limit=limit)

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
        return self.memory_store.list_teacher_annotations(
            trace_id=trace_id,
            run_id=run_id,
            action_id=action_id,
            workflow_run_id=workflow_run_id,
            memory_id=memory_id,
            episode_id=episode_id,
            limit=limit,
        )

    def list_retrievals(
        self,
        *,
        session_id: str | None = None,
        user_id: str | None = None,
        trace_id: str | None = None,
        run_id: str | None = None,
        backend: MemoryRetrievalBackend | None = None,
        limit: int = 100,
    ) -> MemoryRetrievalListResponse:
        return self.memory_store.list_memory_retrievals(
            session_id=session_id,
            user_id=user_id,
            trace_id=trace_id,
            run_id=run_id,
            backend=backend,
            limit=limit,
        )

    def review_debt_summary(self) -> MemoryReviewDebtSummary:
        return self.memory_store.memory_review_debt_summary()
