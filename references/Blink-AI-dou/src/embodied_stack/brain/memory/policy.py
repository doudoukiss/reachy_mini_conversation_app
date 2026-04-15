from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from difflib import SequenceMatcher
import re
from typing import Any

from embodied_stack.shared.contracts._common import (
    MemoryActionType,
    MemoryDecisionOutcome,
    MemoryLayer,
    MemoryReviewStatus,
    MemoryWriteReasonCode,
    ReviewDebtState,
    SensitiveContentFlag,
)
from embodied_stack.shared.contracts.brain import (
    CompanionNoteRecord,
    EpisodicMemoryRecord,
    MemoryActionRecord,
    MemoryPolicyScoreRecord,
    MemoryPromotionRecord,
    ProceduralMemoryRecord,
    MemoryReviewRecord,
    MemoryReviewRequest,
    ReminderRecord,
    RelationshipMemoryRecord,
    RelationshipPromiseRecord,
    RelationshipThreadRecord,
    RelationshipThreadStatus,
    RelationshipTopicRecord,
    SemanticMemoryRecord,
    SessionDigestRecord,
    SessionRecord,
    UserMemoryRecord,
    utc_now,
)
from .store import MemoryStore


_SENSITIVE_AUTO_STORE_RE = re.compile(
    r"\b(suicid|self harm|abuse|trauma|panic attack|depress|diagnos|ptsd|lonely|worthless|ashamed)\b",
    re.IGNORECASE,
)


@dataclass
class MemoryPolicyService:
    memory_store: MemoryStore
    review_debt_overdue_after = timedelta(hours=72)
    profile_threshold: float = 0.70
    episodic_threshold: float = 0.55
    relationship_threshold: float = 0.60
    procedural_threshold: float = 0.80
    semantic_threshold: float = 0.75
    semantic_merge_threshold: float = 0.65
    semantic_similarity_threshold: float = 0.85
    thread_stale_after = timedelta(days=14)
    emotional_thread_stale_after = timedelta(days=5)

    def write_session_memory(
        self,
        *,
        session: SessionRecord,
        key: str,
        value: str,
        trace_id: str | None = None,
        run_id: str | None = None,
        tool_name: str | None = None,
        reason_code: MemoryWriteReasonCode = MemoryWriteReasonCode.SESSION_CONTEXT,
        confidence: float | None = None,
        policy_basis: str | None = None,
    ) -> MemoryActionRecord:
        scorecard = self._score_for_world(key=key, value=value, confidence=confidence)
        session.session_memory[key] = value
        self.memory_store.upsert_session(session)
        action = self._build_action(
            memory_id=f"{session.session_id}:{key}",
            layer=MemoryLayer.WORLD,
            action_type=MemoryActionType.WRITE,
            session_id=session.session_id,
            user_id=session.user_id,
            trace_id=trace_id,
            run_id=run_id,
            tool_name=tool_name,
            summary=f"{key}={value}",
            reason_code=reason_code,
            confidence=confidence,
            policy_basis=policy_basis or "session_world_memory",
            review_status=MemoryReviewStatus.APPROVED,
            scorecard=scorecard,
            decision_outcome=MemoryDecisionOutcome.WRITTEN,
            decision_reason_codes=["world_session_context"],
            review_debt_state=ReviewDebtState.CLEAR,
            sensitive_content_flags=[SensitiveContentFlag.SESSION_MEMORY],
        )
        self.memory_store.append_memory_actions([action])
        return action

    def write_profile_fact(
        self,
        *,
        user_memory: UserMemoryRecord,
        key: str,
        value: str,
        trace_id: str | None = None,
        run_id: str | None = None,
        tool_name: str | None = None,
        reason_code: MemoryWriteReasonCode = MemoryWriteReasonCode.PROFILE_FACT,
        confidence: float | None = None,
        policy_basis: str | None = None,
    ) -> tuple[UserMemoryRecord, MemoryActionRecord]:
        scorecard = self._score_for_profile(key=key, value=value, confidence=confidence, explicit_write=True)
        previous_value = user_memory.facts.get(key)
        user_memory.facts[key] = value
        user_memory.reason_code = reason_code
        user_memory.policy_basis = policy_basis or "profile_fact_write"
        user_memory.review_status = MemoryReviewStatus.APPROVED
        user_memory.policy_scorecard = scorecard
        user_memory.decision_outcome = MemoryDecisionOutcome.WRITTEN
        user_memory.decision_reason_codes = ["profile_explicit_write"]
        if previous_value and previous_value != value:
            user_memory.decision_reason_codes.append("profile_conflict_latest_explicit")
        user_memory.review_debt_state = self._review_debt_state(scorecard)
        user_memory.sensitive_content_flags = self._merge_sensitive_flags(
            user_memory.sensitive_content_flags,
            [SensitiveContentFlag.PROFILE_MEMORY, SensitiveContentFlag.USER_IDENTIFIER],
        )
        user_memory.updated_at = utc_now()
        persisted = self.memory_store.upsert_user_memory(user_memory)
        action = self._build_action(
            memory_id=persisted.user_id,
            layer=MemoryLayer.PROFILE,
            action_type=MemoryActionType.WRITE,
            user_id=persisted.user_id,
            trace_id=trace_id,
            run_id=run_id,
            tool_name=tool_name,
            summary=f"{key}={value}",
            reason_code=reason_code,
            confidence=confidence,
            policy_basis=persisted.policy_basis,
            review_status=persisted.review_status,
            provenance_refs=[*persisted.provenance_refs, f"profile:{persisted.user_id}"],
            scorecard=scorecard,
            decision_outcome=MemoryDecisionOutcome.WRITTEN,
            decision_reason_codes=list(persisted.decision_reason_codes),
            review_debt_state=persisted.review_debt_state,
            sensitive_content_flags=list(persisted.sensitive_content_flags),
        )
        self.memory_store.append_memory_actions([action])
        return persisted, action

    def promote_episodic(
        self,
        record: EpisodicMemoryRecord | ReminderRecord | CompanionNoteRecord | SessionDigestRecord,
        *,
        trace_id: str | None = None,
        run_id: str | None = None,
        tool_name: str | None = None,
        reason_code: MemoryWriteReasonCode,
        confidence: float | None = None,
        policy_basis: str | None = None,
    ) -> MemoryActionRecord:
        summary = self._summary_for_record(record)
        scorecard = self._score_for_episodic(summary=summary, reason_code=reason_code, confidence=confidence)
        record.reason_code = reason_code
        record.policy_basis = policy_basis or "episodic_promotion"
        record.review_status = MemoryReviewStatus.APPROVED
        record.policy_scorecard = scorecard
        record.review_debt_state = self._review_debt_state(scorecard)
        record.sensitive_content_flags = self._merge_sensitive_flags(
            record.sensitive_content_flags,
            [SensitiveContentFlag.SESSION_MEMORY],
        )
        record.updated_at = utc_now()
        if scorecard.promotion_score < self.episodic_threshold:
            action = self._build_action(
                memory_id=getattr(record, "memory_id", None) or getattr(record, "reminder_id", None) or getattr(record, "note_id", None) or getattr(record, "digest_id", None),
                layer=MemoryLayer.EPISODIC,
                action_type=MemoryActionType.REJECT,
                session_id=getattr(record, "session_id", None),
                user_id=getattr(record, "user_id", None),
                trace_id=trace_id,
                run_id=run_id,
                tool_name=tool_name,
                summary=summary,
                reason_code=reason_code,
                confidence=confidence,
                policy_basis=record.policy_basis,
                review_status=MemoryReviewStatus.PENDING,
                scorecard=scorecard,
                decision_outcome=MemoryDecisionOutcome.REJECTED,
                decision_reason_codes=["episodic_threshold_not_met"],
                review_debt_state=self._review_debt_state(scorecard),
                sensitive_content_flags=list(record.sensitive_content_flags),
            )
            self.memory_store.append_memory_actions([action])
            return action
        if isinstance(record, EpisodicMemoryRecord):
            self.memory_store.upsert_episodic_memory(record)
            memory_id = record.memory_id
            session_id = record.session_id
            user_id = record.user_id
        elif isinstance(record, ReminderRecord):
            self.memory_store.upsert_reminder(record)
            memory_id = record.reminder_id
            session_id = record.session_id
            user_id = record.user_id
        elif isinstance(record, CompanionNoteRecord):
            self.memory_store.upsert_companion_note(record)
            memory_id = record.note_id
            session_id = record.session_id
            user_id = record.user_id
        else:
            self.memory_store.upsert_session_digest(record)
            memory_id = record.digest_id
            session_id = record.session_id
            user_id = record.user_id
        action = self._build_action(
            memory_id=memory_id,
            layer=MemoryLayer.EPISODIC,
            action_type=MemoryActionType.PROMOTE,
            session_id=session_id,
            user_id=user_id,
            trace_id=trace_id,
            run_id=run_id,
            tool_name=tool_name,
            summary=summary,
            reason_code=reason_code,
            confidence=confidence,
            policy_basis=record.policy_basis,
            review_status=record.review_status,
            provenance_refs=list(getattr(record, "provenance_refs", [])),
            scorecard=scorecard,
            decision_outcome=MemoryDecisionOutcome.PROMOTED,
            decision_reason_codes=["episodic_threshold_met"],
            review_debt_state=record.review_debt_state,
            sensitive_content_flags=list(record.sensitive_content_flags),
        )
        self.memory_store.append_memory_actions([action])
        return action

    def promote_semantic(
        self,
        record: SemanticMemoryRecord,
        *,
        trace_id: str | None = None,
        run_id: str | None = None,
        tool_name: str | None = None,
        reason_code: MemoryWriteReasonCode,
        confidence: float | None = None,
        policy_basis: str | None = None,
    ) -> MemoryActionRecord:
        scorecard = self._score_for_semantic(record=record, confidence=confidence)
        record.reason_code = reason_code
        record.policy_basis = policy_basis or "semantic_promotion"
        record.review_status = MemoryReviewStatus.APPROVED
        record.policy_scorecard = scorecard
        record.review_debt_state = self._review_debt_state(scorecard)
        record.sensitive_content_flags = self._merge_sensitive_flags(
            record.sensitive_content_flags,
            [SensitiveContentFlag.PROFILE_MEMORY] if record.user_id else [],
        )
        record.updated_at = utc_now()
        if self._contains_sensitive_auto_store_text(record.summary):
            action = self._build_action(
                memory_id=record.memory_id,
                layer=MemoryLayer.SEMANTIC,
                action_type=MemoryActionType.REJECT,
                session_id=record.session_id,
                user_id=record.user_id,
                trace_id=trace_id,
                run_id=run_id,
                tool_name=tool_name,
                summary=record.summary,
                reason_code=reason_code,
                confidence=confidence or record.confidence,
                policy_basis=record.policy_basis,
                review_status=MemoryReviewStatus.PENDING,
                provenance_refs=[*record.provenance_refs, *record.source_refs],
                scorecard=scorecard,
                decision_outcome=MemoryDecisionOutcome.REJECTED,
                decision_reason_codes=["semantic_sensitive_auto_store_blocked"],
                review_debt_state=self._review_debt_state(scorecard),
                sensitive_content_flags=list(
                    self._merge_sensitive_flags(record.sensitive_content_flags, [SensitiveContentFlag.PROFILE_MEMORY])
                ),
            )
            self.memory_store.append_memory_actions([action])
            return action
        if scorecard.promotion_score < self.semantic_threshold:
            action = self._build_action(
                memory_id=record.memory_id,
                layer=MemoryLayer.SEMANTIC,
                action_type=MemoryActionType.REJECT,
                session_id=record.session_id,
                user_id=record.user_id,
                trace_id=trace_id,
                run_id=run_id,
                tool_name=tool_name,
                summary=record.summary,
                reason_code=reason_code,
                confidence=confidence or record.confidence,
                policy_basis=record.policy_basis,
                review_status=MemoryReviewStatus.PENDING,
                provenance_refs=[*record.provenance_refs, *record.source_refs],
                scorecard=scorecard,
                decision_outcome=MemoryDecisionOutcome.REJECTED,
                decision_reason_codes=["semantic_threshold_not_met"],
                review_debt_state=self._review_debt_state(scorecard),
                sensitive_content_flags=list(record.sensitive_content_flags),
            )
            self.memory_store.append_memory_actions([action])
            return action

        merged_into = self._merge_target_for_semantic(record, scorecard=scorecard)
        if merged_into is not None:
            merged_into.source_trace_ids = list(dict.fromkeys([*merged_into.source_trace_ids, *record.source_trace_ids]))
            merged_into.source_refs = list(dict.fromkeys([*merged_into.source_refs, *record.source_refs]))
            merged_into.provenance_refs = list(dict.fromkeys([*merged_into.provenance_refs, *record.provenance_refs]))
            merged_into.policy_scorecard = scorecard
            merged_into.decision_outcome = MemoryDecisionOutcome.MERGED
            merged_into.decision_reason_codes = ["semantic_similarity_merge"]
            merged_into.supersedes_memory_ids = list(dict.fromkeys([*merged_into.supersedes_memory_ids, record.memory_id]))
            merged_into.review_debt_state = self._review_debt_state(scorecard)
            self.memory_store.upsert_semantic_memory(merged_into)
            action = self._build_action(
                memory_id=record.memory_id,
                layer=MemoryLayer.SEMANTIC,
                action_type=MemoryActionType.PROMOTE,
                session_id=record.session_id,
                user_id=record.user_id,
                trace_id=trace_id,
                run_id=run_id,
                tool_name=tool_name,
                summary=record.summary,
                reason_code=reason_code,
                confidence=confidence or record.confidence,
                policy_basis=record.policy_basis,
                review_status=merged_into.review_status,
                provenance_refs=[*record.provenance_refs, *record.source_refs],
                scorecard=scorecard,
                decision_outcome=MemoryDecisionOutcome.MERGED,
                decision_reason_codes=["semantic_similarity_merge"],
                merged_into_memory_id=merged_into.memory_id,
                supersedes_memory_ids=[record.memory_id],
                review_debt_state=merged_into.review_debt_state,
                sensitive_content_flags=list(merged_into.sensitive_content_flags),
            )
            self.memory_store.append_memory_actions([action])
            return action

        self.memory_store.upsert_semantic_memory(record)
        action = self._build_action(
            memory_id=record.memory_id,
            layer=MemoryLayer.SEMANTIC,
            action_type=MemoryActionType.PROMOTE,
            session_id=record.session_id,
            user_id=record.user_id,
            trace_id=trace_id,
            run_id=run_id,
            tool_name=tool_name,
            summary=record.summary,
            reason_code=reason_code,
            confidence=confidence or record.confidence,
            policy_basis=record.policy_basis,
            review_status=record.review_status,
            provenance_refs=[*record.provenance_refs, *record.source_refs],
            scorecard=scorecard,
            decision_outcome=MemoryDecisionOutcome.PROMOTED,
            decision_reason_codes=["semantic_threshold_met"],
            review_debt_state=record.review_debt_state,
            sensitive_content_flags=list(record.sensitive_content_flags),
        )
        self.memory_store.append_memory_actions([action])
        return action

    def upsert_relationship_memory(
        self,
        record: RelationshipMemoryRecord,
        *,
        trace_id: str | None = None,
        run_id: str | None = None,
        tool_name: str | None = None,
        reason_code: MemoryWriteReasonCode,
        confidence: float | None = None,
        policy_basis: str | None = None,
    ) -> MemoryActionRecord:
        record.open_threads = self._normalized_relationship_threads(record.open_threads)
        record.promises = self._normalized_relationship_promises(record.promises)
        record.reason_code = reason_code
        record.policy_basis = policy_basis or "relationship_runtime"
        scorecard = self._score_for_relationship(record=record, confidence=confidence)
        record.policy_scorecard = scorecard
        record.review_status = MemoryReviewStatus.APPROVED
        record.review_debt_state = self._review_debt_state(scorecard)
        record.sensitive_content_flags = self._merge_sensitive_flags(
            record.sensitive_content_flags,
            [SensitiveContentFlag.RELATIONSHIP_MEMORY],
        )
        record.updated_at = utc_now()
        block_reason = self._relationship_block_reason(record)
        if block_reason is not None or scorecard.promotion_score < self.relationship_threshold:
            action = self._build_action(
                memory_id=record.relationship_id,
                layer=MemoryLayer.RELATIONSHIP,
                action_type=MemoryActionType.REJECT,
                session_id=record.last_session_id,
                user_id=record.user_id,
                trace_id=trace_id,
                run_id=run_id,
                tool_name=tool_name,
                summary=self._summary_for_record(record),
                reason_code=reason_code,
                confidence=confidence,
                policy_basis=record.policy_basis,
                review_status=MemoryReviewStatus.PENDING,
                provenance_refs=list(record.provenance_refs),
                scorecard=scorecard,
                decision_outcome=MemoryDecisionOutcome.REJECTED,
                decision_reason_codes=[block_reason or "relationship_threshold_not_met"],
                review_debt_state=self._review_debt_state(scorecard),
                sensitive_content_flags=list(record.sensitive_content_flags),
            )
            self.memory_store.append_memory_actions([action])
            return action

        existing = self.memory_store.get_relationship_memory(record.relationship_id)
        decision_outcome = MemoryDecisionOutcome.PROMOTED
        decision_reason_codes = ["relationship_runtime_update"]
        persisted = record
        if existing is not None:
            persisted = self._merge_relationship_memory(existing, record, scorecard=scorecard)
            decision_outcome = MemoryDecisionOutcome.MERGED
            decision_reason_codes = ["relationship_runtime_merge"]
        persisted.decision_outcome = decision_outcome
        persisted.decision_reason_codes = decision_reason_codes
        persisted.updated_at = utc_now()
        self.memory_store.upsert_relationship_memory(persisted)
        action = self._build_action(
            memory_id=persisted.relationship_id,
            layer=MemoryLayer.RELATIONSHIP,
            action_type=MemoryActionType.PROMOTE,
            session_id=persisted.last_session_id,
            user_id=persisted.user_id,
            trace_id=trace_id,
            run_id=run_id,
            tool_name=tool_name,
            summary=self._summary_for_record(persisted),
            reason_code=reason_code,
            confidence=confidence,
            policy_basis=persisted.policy_basis,
            review_status=persisted.review_status,
            provenance_refs=list(persisted.provenance_refs),
            scorecard=scorecard,
            decision_outcome=decision_outcome,
            decision_reason_codes=decision_reason_codes,
            review_debt_state=persisted.review_debt_state,
            sensitive_content_flags=list(persisted.sensitive_content_flags),
        )
        self.memory_store.append_memory_actions([action])
        return action

    def promote_procedural(
        self,
        record: ProceduralMemoryRecord,
        *,
        trace_id: str | None = None,
        run_id: str | None = None,
        tool_name: str | None = None,
        reason_code: MemoryWriteReasonCode,
        confidence: float | None = None,
        policy_basis: str | None = None,
    ) -> MemoryActionRecord:
        record.reason_code = reason_code
        record.policy_basis = policy_basis or "procedural_memory"
        scorecard = self._score_for_procedural(record=record, confidence=confidence)
        record.policy_scorecard = scorecard
        record.review_status = MemoryReviewStatus.APPROVED
        record.review_debt_state = self._review_debt_state(scorecard)
        record.sensitive_content_flags = self._merge_sensitive_flags(
            record.sensitive_content_flags,
            [SensitiveContentFlag.PROCEDURAL_MEMORY] if record.user_id else [],
        )
        record.updated_at = utc_now()
        if self._contains_sensitive_auto_store_text(record.summary) or scorecard.promotion_score < self.procedural_threshold:
            action = self._build_action(
                memory_id=record.procedure_id,
                layer=MemoryLayer.PROCEDURAL,
                action_type=MemoryActionType.REJECT,
                session_id=record.session_id,
                user_id=record.user_id,
                trace_id=trace_id,
                run_id=run_id,
                tool_name=tool_name,
                summary=record.summary,
                reason_code=reason_code,
                confidence=confidence or record.confidence,
                policy_basis=record.policy_basis,
                review_status=MemoryReviewStatus.PENDING,
                provenance_refs=[*record.provenance_refs, *record.source_refs],
                scorecard=scorecard,
                decision_outcome=MemoryDecisionOutcome.REJECTED,
                decision_reason_codes=[
                    "procedural_sensitive_auto_store_blocked"
                    if self._contains_sensitive_auto_store_text(record.summary)
                    else "procedural_threshold_not_met"
                ],
                review_debt_state=self._review_debt_state(scorecard),
                sensitive_content_flags=list(record.sensitive_content_flags),
            )
            self.memory_store.append_memory_actions([action])
            return action

        existing = self._merge_target_for_procedural(record)
        decision_outcome = MemoryDecisionOutcome.PROMOTED
        decision_reason_codes = ["procedural_threshold_met"]
        persisted = record
        if existing is not None:
            existing.summary = record.summary
            existing.name = record.name
            existing.trigger_phrases = list(dict.fromkeys([*existing.trigger_phrases, *record.trigger_phrases]))
            existing.steps = list(dict.fromkeys([*existing.steps, *record.steps]))
            existing.source_trace_ids = list(dict.fromkeys([*existing.source_trace_ids, *record.source_trace_ids]))
            existing.source_refs = list(dict.fromkeys([*existing.source_refs, *record.source_refs]))
            existing.provenance_refs = list(dict.fromkeys([*existing.provenance_refs, *record.provenance_refs]))
            existing.policy_scorecard = scorecard
            existing.review_debt_state = self._review_debt_state(scorecard)
            existing.sensitive_content_flags = self._merge_sensitive_flags(
                existing.sensitive_content_flags,
                list(record.sensitive_content_flags),
            )
            existing.updated_at = utc_now()
            persisted = existing
            decision_outcome = MemoryDecisionOutcome.MERGED
            decision_reason_codes = ["procedural_merge"]

        persisted.decision_outcome = decision_outcome
        persisted.decision_reason_codes = decision_reason_codes
        self.memory_store.upsert_procedural_memory(persisted)
        action = self._build_action(
            memory_id=persisted.procedure_id,
            layer=MemoryLayer.PROCEDURAL,
            action_type=MemoryActionType.PROMOTE,
            session_id=persisted.session_id,
            user_id=persisted.user_id,
            trace_id=trace_id,
            run_id=run_id,
            tool_name=tool_name,
            summary=persisted.summary,
            reason_code=reason_code,
            confidence=confidence or persisted.confidence,
            policy_basis=persisted.policy_basis,
            review_status=persisted.review_status,
            provenance_refs=[*persisted.provenance_refs, *persisted.source_refs],
            scorecard=scorecard,
            decision_outcome=decision_outcome,
            decision_reason_codes=decision_reason_codes,
            review_debt_state=persisted.review_debt_state,
            sensitive_content_flags=list(persisted.sensitive_content_flags),
        )
        self.memory_store.append_memory_actions([action])
        return action

    def review_memory(self, request: MemoryReviewRequest) -> MemoryReviewRecord:
        target = self._load_target(request.layer, request.memory_id)
        scorecard = (
            target.policy_scorecard
            if target is not None
            else MemoryPolicyScoreRecord(review_priority=0.8, promotion_score=0.5)
        )
        review = MemoryReviewRecord(
            memory_id=request.memory_id,
            layer=request.layer,
            action_type=MemoryActionType.REVIEW,
            status=MemoryReviewStatus.APPROVED,
            author=request.author,
            note=request.note,
            updated_fields=dict(request.updated_fields),
            provenance_refs=[f"memory:{request.memory_id}"],
            policy_scorecard=scorecard,
            decision_outcome=MemoryDecisionOutcome.REVIEWED,
            decision_reason_codes=["operator_review"],
            review_debt_state=ReviewDebtState.CLEAR,
            sensitive_content_flags=list(target.sensitive_content_flags) if target is not None else [],
        )
        if target is not None:
            target.review_status = MemoryReviewStatus.APPROVED
            target.review_debt_state = ReviewDebtState.CLEAR
            target.decision_outcome = MemoryDecisionOutcome.REVIEWED
            target.decision_reason_codes = ["operator_review"]
            self._persist_target(request.layer, target)
        self.memory_store.append_memory_reviews([review])
        self.memory_store.append_memory_actions(
            [
                self._build_action(
                    memory_id=request.memory_id,
                    layer=request.layer,
                    action_type=MemoryActionType.REVIEW,
                    summary=request.note or "memory_review",
                    reason_code=MemoryWriteReasonCode.TEACHER_IMPORTANCE,
                    policy_basis="operator_review",
                    review_status=review.status,
                    provenance_refs=review.provenance_refs,
                    scorecard=scorecard,
                    decision_outcome=MemoryDecisionOutcome.REVIEWED,
                    decision_reason_codes=["operator_review"],
                    review_debt_state=ReviewDebtState.CLEAR,
                    sensitive_content_flags=list(review.sensitive_content_flags),
                )
            ]
        )
        return review

    def correct_memory(self, request: MemoryReviewRequest) -> MemoryReviewRecord:
        target = self._load_target(request.layer, request.memory_id)
        if target is None:
            raise KeyError(request.memory_id)
        self._apply_updates(target, request.updated_fields)
        if hasattr(target, "reason_code"):
            target.reason_code = MemoryWriteReasonCode.OPERATOR_CORRECTION
        if hasattr(target, "policy_basis"):
            target.policy_basis = request.note or "operator_correction"
        target.review_status = MemoryReviewStatus.CORRECTED
        target.decision_outcome = MemoryDecisionOutcome.CORRECTED
        target.decision_reason_codes = ["operator_correction"]
        target.tombstoned = False
        if hasattr(target, "deleted_at"):
            target.deleted_at = None
        target.review_debt_state = ReviewDebtState.CLEAR
        self._persist_target(request.layer, target)
        review = MemoryReviewRecord(
            memory_id=request.memory_id,
            layer=request.layer,
            action_type=MemoryActionType.CORRECT,
            status=MemoryReviewStatus.CORRECTED,
            author=request.author,
            note=request.note,
            updated_fields=dict(request.updated_fields),
            provenance_refs=[f"memory:{request.memory_id}"],
            policy_scorecard=target.policy_scorecard,
            decision_outcome=MemoryDecisionOutcome.CORRECTED,
            decision_reason_codes=["operator_correction"],
            review_debt_state=ReviewDebtState.CLEAR,
            sensitive_content_flags=list(target.sensitive_content_flags),
        )
        self.memory_store.append_memory_reviews([review])
        self.memory_store.append_memory_actions(
            [
                self._build_action(
                    memory_id=request.memory_id,
                    layer=request.layer,
                    action_type=MemoryActionType.CORRECT,
                    session_id=getattr(target, "session_id", None),
                    user_id=getattr(target, "user_id", getattr(target, "user_id", None)),
                    summary=self._summary_for_record(target),
                    reason_code=MemoryWriteReasonCode.OPERATOR_CORRECTION,
                    policy_basis=request.note or "operator_correction",
                    review_status=review.status,
                    provenance_refs=review.provenance_refs,
                    scorecard=target.policy_scorecard,
                    decision_outcome=MemoryDecisionOutcome.CORRECTED,
                    decision_reason_codes=["operator_correction"],
                    review_debt_state=ReviewDebtState.CLEAR,
                    sensitive_content_flags=list(target.sensitive_content_flags),
                )
            ]
        )
        return review

    def delete_memory(self, request: MemoryReviewRequest) -> MemoryReviewRecord:
        target = self._load_target(request.layer, request.memory_id)
        if target is None:
            raise KeyError(request.memory_id)
        target.tombstoned = True
        if hasattr(target, "deleted_at"):
            target.deleted_at = utc_now()
        if hasattr(target, "reason_code"):
            target.reason_code = MemoryWriteReasonCode.OPERATOR_DELETION
        if hasattr(target, "policy_basis"):
            target.policy_basis = request.note or "operator_deletion"
        target.review_status = MemoryReviewStatus.TOMBSTONED
        target.decision_outcome = MemoryDecisionOutcome.TOMBSTONED
        target.decision_reason_codes = ["operator_deletion"]
        target.review_debt_state = ReviewDebtState.CLEAR
        self._persist_target(request.layer, target)
        review = MemoryReviewRecord(
            memory_id=request.memory_id,
            layer=request.layer,
            action_type=MemoryActionType.DELETE,
            status=MemoryReviewStatus.TOMBSTONED,
            author=request.author,
            note=request.note,
            updated_fields=dict(request.updated_fields),
            provenance_refs=[f"memory:{request.memory_id}"],
            policy_scorecard=target.policy_scorecard,
            decision_outcome=MemoryDecisionOutcome.TOMBSTONED,
            decision_reason_codes=["operator_deletion"],
            review_debt_state=ReviewDebtState.CLEAR,
            sensitive_content_flags=list(target.sensitive_content_flags),
        )
        self.memory_store.append_memory_reviews([review])
        self.memory_store.append_memory_actions(
            [
                self._build_action(
                    memory_id=request.memory_id,
                    layer=request.layer,
                    action_type=MemoryActionType.DELETE,
                    session_id=getattr(target, "session_id", None),
                    user_id=getattr(target, "user_id", getattr(target, "user_id", None)),
                    summary=self._summary_for_record(target),
                    reason_code=MemoryWriteReasonCode.OPERATOR_DELETION,
                    policy_basis=request.note or "operator_deletion",
                    review_status=review.status,
                    tombstoned=True,
                    provenance_refs=review.provenance_refs,
                    scorecard=target.policy_scorecard,
                    decision_outcome=MemoryDecisionOutcome.TOMBSTONED,
                    decision_reason_codes=["operator_deletion"],
                    review_debt_state=ReviewDebtState.CLEAR,
                    sensitive_content_flags=list(target.sensitive_content_flags),
                )
            ]
        )
        return review

    def promotion_from_action(self, action: MemoryActionRecord) -> MemoryPromotionRecord:
        promotion_type = action.layer.value
        if action.layer == MemoryLayer.EPISODIC:
            if self.memory_store.get_reminder(action.memory_id) is not None:
                promotion_type = "personal_reminder"
            elif self.memory_store.get_companion_note(action.memory_id) is not None:
                promotion_type = "local_note"
            elif self.memory_store.get_session_digest(action.memory_id) is not None:
                promotion_type = "session_digest"
            else:
                promotion_type = "episodic_memory"
        elif action.layer == MemoryLayer.RELATIONSHIP:
            promotion_type = "relationship_memory"
        elif action.layer == MemoryLayer.PROCEDURAL:
            promotion_type = "procedural_memory"
        elif action.layer == MemoryLayer.SEMANTIC:
            promotion_type = "semantic_memory"
        elif action.layer == MemoryLayer.PROFILE:
            promotion_type = "profile_memory"
        elif action.layer == MemoryLayer.WORLD:
            promotion_type = "world_memory"
        return MemoryPromotionRecord(
            promotion_type=promotion_type,
            summary=action.summary,
            trace_id=action.trace_id,
            target_id=action.memory_id,
            reason=action.reason_code.value,
        )

    def _build_action(
        self,
        *,
        memory_id: str,
        layer: MemoryLayer,
        action_type: MemoryActionType,
        summary: str,
        reason_code: MemoryWriteReasonCode,
        session_id: str | None = None,
        user_id: str | None = None,
        trace_id: str | None = None,
        run_id: str | None = None,
        tool_name: str | None = None,
        confidence: float | None = None,
        policy_basis: str | None = None,
        review_status: MemoryReviewStatus = MemoryReviewStatus.PENDING,
        tombstoned: bool = False,
        provenance_refs: list[str] | None = None,
        scorecard: MemoryPolicyScoreRecord | None = None,
        decision_outcome: MemoryDecisionOutcome | None = None,
        decision_reason_codes: list[str] | None = None,
        merged_into_memory_id: str | None = None,
        supersedes_memory_ids: list[str] | None = None,
        review_debt_state: ReviewDebtState = ReviewDebtState.CLEAR,
        sensitive_content_flags: list[SensitiveContentFlag] | None = None,
    ) -> MemoryActionRecord:
        return MemoryActionRecord(
            memory_id=memory_id,
            layer=layer,
            action_type=action_type,
            session_id=session_id,
            user_id=user_id,
            trace_id=trace_id,
            run_id=run_id,
            tool_name=tool_name,
            summary=summary,
            reason_code=reason_code,
            provenance_refs=list(provenance_refs or []),
            confidence=confidence,
            policy_basis=policy_basis,
            review_status=review_status,
            tombstoned=tombstoned,
            policy_scorecard=scorecard or MemoryPolicyScoreRecord(),
            decision_outcome=decision_outcome,
            decision_reason_codes=list(decision_reason_codes or []),
            merged_into_memory_id=merged_into_memory_id,
            supersedes_memory_ids=list(supersedes_memory_ids or []),
            review_debt_state=review_debt_state,
            sensitive_content_flags=list(sensitive_content_flags or []),
        )

    def _load_target(self, layer: MemoryLayer, memory_id: str):
        if layer == MemoryLayer.PROFILE:
            return self.memory_store.get_user_memory(memory_id)
        if layer == MemoryLayer.RELATIONSHIP:
            return self.memory_store.get_relationship_memory(memory_id)
        if layer == MemoryLayer.SEMANTIC:
            return self.memory_store.get_semantic_memory(memory_id)
        if layer == MemoryLayer.PROCEDURAL:
            return self.memory_store.get_procedural_memory(memory_id)
        if layer == MemoryLayer.EPISODIC:
            return (
                self.memory_store.get_episodic_memory(memory_id)
                or self.memory_store.get_reminder(memory_id)
                or self.memory_store.get_companion_note(memory_id)
                or self.memory_store.get_session_digest(memory_id)
            )
        return None

    def _persist_target(self, layer: MemoryLayer, target) -> None:
        if layer == MemoryLayer.PROFILE:
            self.memory_store.upsert_user_memory(target)
            return
        if layer == MemoryLayer.RELATIONSHIP:
            self.memory_store.upsert_relationship_memory(target)
            return
        if layer == MemoryLayer.SEMANTIC:
            self.memory_store.upsert_semantic_memory(target)
            return
        if layer == MemoryLayer.PROCEDURAL:
            self.memory_store.upsert_procedural_memory(target)
            return
        if isinstance(target, EpisodicMemoryRecord):
            self.memory_store.upsert_episodic_memory(target)
        elif isinstance(target, ReminderRecord):
            self.memory_store.upsert_reminder(target)
        elif isinstance(target, CompanionNoteRecord):
            self.memory_store.upsert_companion_note(target)
        elif isinstance(target, SessionDigestRecord):
            self.memory_store.upsert_session_digest(target)

    def _apply_updates(self, target, updated_fields: dict[str, Any]) -> None:
        for key, value in updated_fields.items():
            if key in {"facts", "preferences"} and isinstance(value, dict):
                current = dict(getattr(target, key, {}))
                current.update(value)
                setattr(target, key, current)
                continue
            if key in {"relationship_profile", "preferred_style"} and isinstance(value, dict):
                current = getattr(target, key, None)
                if current is not None:
                    updated = current.model_copy(update=value)
                    setattr(target, key, updated)
                    continue
            if key == "interests" and isinstance(value, list):
                setattr(target, key, list(value))
                continue
            if key in {"recurring_topics", "open_threads", "promises", "trigger_phrases", "steps"} and isinstance(value, list):
                setattr(target, key, list(value))
                continue
            if hasattr(target, key):
                setattr(target, key, value)

    def _summary_for_record(self, record) -> str:
        if isinstance(record, EpisodicMemoryRecord):
            return record.summary
        if isinstance(record, RelationshipMemoryRecord):
            return self._relationship_summary(record)
        if isinstance(record, SemanticMemoryRecord):
            return record.summary
        if isinstance(record, ProceduralMemoryRecord):
            return record.summary
        if isinstance(record, ReminderRecord):
            return record.reminder_text
        if isinstance(record, CompanionNoteRecord):
            return f"{record.title}: {record.content}"
        if isinstance(record, SessionDigestRecord):
            return record.summary
        if isinstance(record, UserMemoryRecord):
            return record.display_name or f"profile:{record.user_id}"
        return str(record)

    def _score_for_world(self, *, key: str, value: str, confidence: float | None) -> MemoryPolicyScoreRecord:
        return MemoryPolicyScoreRecord(
            evidence_score=1.0,
            utility_score=0.55 if value else 0.2,
            durability_score=0.15,
            privacy_risk_score=0.35 if key else 0.2,
            promotion_score=0.0,
            review_priority=0.1,
        )

    def _score_for_profile(
        self,
        *,
        key: str,
        value: str,
        confidence: float | None,
        explicit_write: bool,
    ) -> MemoryPolicyScoreRecord:
        evidence = 1.0 if explicit_write else (confidence or 0.7)
        utility = 0.8 if value else 0.3
        durability = 0.9
        privacy = 0.65
        promotion = self._clamp((evidence * 0.4) + (utility * 0.3) + (durability * 0.3) - (privacy * 0.05))
        review = self._clamp((privacy * 0.45) + ((1.0 - promotion) * 0.35) + (0.2 if not explicit_write else 0.0))
        return MemoryPolicyScoreRecord(
            evidence_score=evidence,
            utility_score=utility,
            durability_score=durability,
            privacy_risk_score=privacy,
            promotion_score=promotion,
            review_priority=review,
        )

    def _score_for_relationship(
        self,
        *,
        record: RelationshipMemoryRecord,
        confidence: float | None,
    ) -> MemoryPolicyScoreRecord:
        explicit_style = bool(
            record.preferred_style.greeting_preference
            or record.preferred_style.planning_style
            or record.preferred_style.tone_preferences
            or record.preferred_style.interaction_boundaries
            or record.preferred_style.continuity_preferences
        )
        emotional_threads = sum(1 for item in record.open_threads if item.kind.value == "emotional")
        evidence = confidence or (0.9 if explicit_style or record.promises else 0.72)
        utility = 0.9 if record.open_threads or record.promises else (0.78 if explicit_style else 0.55)
        durability = 0.82 if explicit_style or record.recurring_topics else 0.58
        privacy = 0.62 if emotional_threads else 0.38
        promotion = self._clamp((evidence * 0.4) + (utility * 0.35) + (durability * 0.25) - (privacy * 0.08))
        review = self._clamp((privacy * 0.45) + ((1.0 - promotion) * 0.3))
        return MemoryPolicyScoreRecord(
            evidence_score=evidence,
            utility_score=utility,
            durability_score=durability,
            privacy_risk_score=privacy,
            promotion_score=promotion,
            review_priority=review,
        )

    def _score_for_procedural(
        self,
        *,
        record: ProceduralMemoryRecord,
        confidence: float | None,
    ) -> MemoryPolicyScoreRecord:
        evidence = confidence or record.confidence or 0.88
        utility = 0.92 if record.trigger_phrases or record.steps else 0.55
        durability = 0.94
        privacy = 0.3 if record.user_id else 0.18
        promotion = self._clamp((evidence * 0.42) + (utility * 0.33) + (durability * 0.25) - (privacy * 0.05))
        review = self._clamp((privacy * 0.28) + ((1.0 - promotion) * 0.32))
        return MemoryPolicyScoreRecord(
            evidence_score=evidence,
            utility_score=utility,
            durability_score=durability,
            privacy_risk_score=privacy,
            promotion_score=promotion,
            review_priority=review,
        )

    def _score_for_episodic(
        self,
        *,
        summary: str,
        reason_code: MemoryWriteReasonCode,
        confidence: float | None,
    ) -> MemoryPolicyScoreRecord:
        evidence = 1.0 if reason_code in {
            MemoryWriteReasonCode.EXPLICIT_REMINDER_REQUEST,
            MemoryWriteReasonCode.EXPLICIT_NOTE_CAPTURE,
        } else (confidence or 0.72)
        utility = 0.85 if summary else 0.2
        durability = 0.6
        privacy = 0.45
        promotion = self._clamp((evidence * 0.4) + (utility * 0.35) + (durability * 0.25) - (privacy * 0.05))
        review = self._clamp((privacy * 0.35) + ((1.0 - promotion) * 0.4))
        return MemoryPolicyScoreRecord(
            evidence_score=evidence,
            utility_score=utility,
            durability_score=durability,
            privacy_risk_score=privacy,
            promotion_score=promotion,
            review_priority=review,
        )

    def _score_for_semantic(
        self,
        *,
        record: SemanticMemoryRecord,
        confidence: float | None,
    ) -> MemoryPolicyScoreRecord:
        evidence = confidence or record.confidence or 0.76
        utility = 0.9 if record.canonical_value or record.summary else 0.25
        durability = 0.88
        privacy = 0.35 if record.user_id is None else 0.55
        promotion = self._clamp((evidence * 0.45) + (utility * 0.3) + (durability * 0.25) - (privacy * 0.05))
        review = self._clamp((privacy * 0.3) + ((1.0 - promotion) * 0.35))
        return MemoryPolicyScoreRecord(
            evidence_score=evidence,
            utility_score=utility,
            durability_score=durability,
            privacy_risk_score=privacy,
            promotion_score=promotion,
            review_priority=review,
        )

    def _review_debt_state(
        self,
        scorecard: MemoryPolicyScoreRecord,
        *,
        updated_at=None,
        teacher_conflict: bool = False,
    ) -> ReviewDebtState:
        if teacher_conflict:
            return ReviewDebtState.OVERDUE
        if scorecard.review_priority < 0.60:
            return ReviewDebtState.CLEAR
        if updated_at is not None and updated_at <= utc_now() - self.review_debt_overdue_after:
            return ReviewDebtState.OVERDUE
        return ReviewDebtState.PENDING

    def mark_teacher_conflict(
        self,
        *,
        layer: MemoryLayer,
        memory_id: str,
        note: str | None = None,
    ) -> None:
        target = self._load_target(layer, memory_id)
        if target is None:
            return
        target.review_debt_state = ReviewDebtState.OVERDUE
        target.decision_reason_codes = list(dict.fromkeys([*target.decision_reason_codes, "teacher_conflict"]))
        if note:
            target.policy_basis = note
        self._persist_target(layer, target)

    def _merge_target_for_semantic(
        self,
        record: SemanticMemoryRecord,
        *,
        scorecard: MemoryPolicyScoreRecord,
    ) -> SemanticMemoryRecord | None:
        if scorecard.promotion_score < self.semantic_merge_threshold:
            return None
        candidates = self.memory_store.list_semantic_memory(user_id=record.user_id, limit=100, include_tombstoned=False).items
        best_match: tuple[float, SemanticMemoryRecord] | None = None
        for candidate in candidates:
            if candidate.memory_id == record.memory_id or candidate.memory_kind != record.memory_kind:
                continue
            similarity = self._semantic_similarity(candidate, record)
            if similarity < self.semantic_similarity_threshold:
                continue
            if best_match is None or similarity > best_match[0]:
                best_match = (similarity, candidate)
        return best_match[1] if best_match is not None else None

    def _merge_target_for_procedural(self, record: ProceduralMemoryRecord) -> ProceduralMemoryRecord | None:
        candidates = self.memory_store.list_procedural_memory(
            user_id=record.user_id,
            session_id=record.session_id,
            limit=100,
            include_tombstoned=False,
        ).items
        for candidate in candidates:
            if candidate.procedure_id == record.procedure_id:
                continue
            trigger_overlap = set(candidate.trigger_phrases) & set(record.trigger_phrases)
            if candidate.name.strip().lower() == record.name.strip().lower() or trigger_overlap:
                return candidate
        return None

    def _semantic_similarity(self, left: SemanticMemoryRecord, right: SemanticMemoryRecord) -> float:
        left_text = (left.canonical_value or left.summary or "").strip().lower()
        right_text = (right.canonical_value or right.summary or "").strip().lower()
        if not left_text or not right_text:
            return 0.0
        if left_text == right_text:
            return 1.0
        return SequenceMatcher(None, left_text, right_text).ratio()

    def _merge_relationship_memory(
        self,
        existing: RelationshipMemoryRecord,
        incoming: RelationshipMemoryRecord,
        *,
        scorecard: MemoryPolicyScoreRecord,
    ) -> RelationshipMemoryRecord:
        merged = existing.model_copy(deep=True)
        merged.familiarity = self._clamp(max(existing.familiarity, incoming.familiarity))
        merged.last_session_id = incoming.last_session_id or existing.last_session_id
        merged.preferred_style = self._merge_relationship_style(existing.preferred_style, incoming.preferred_style)
        merged.recurring_topics = self._merge_relationship_topics(existing.recurring_topics, incoming.recurring_topics)
        merged.open_threads = self._merge_relationship_threads(existing.open_threads, incoming.open_threads)
        merged.promises = self._merge_relationship_promises(existing.promises, incoming.promises)
        merged.provenance_refs = list(dict.fromkeys([*existing.provenance_refs, *incoming.provenance_refs]))
        merged.policy_basis = incoming.policy_basis or existing.policy_basis
        merged.policy_scorecard = scorecard
        merged.review_status = MemoryReviewStatus.APPROVED
        merged.review_debt_state = self._review_debt_state(scorecard)
        merged.sensitive_content_flags = self._merge_sensitive_flags(
            existing.sensitive_content_flags,
            list(incoming.sensitive_content_flags),
        )
        return merged

    def _merge_relationship_style(
        self,
        existing: Any,
        incoming: Any,
    ):
        merged = existing.model_copy(deep=True)
        if incoming.greeting_preference is not None:
            merged.greeting_preference = incoming.greeting_preference
        if incoming.planning_style is not None:
            merged.planning_style = incoming.planning_style
        merged.tone_preferences = list(dict.fromkeys([*existing.tone_preferences, *incoming.tone_preferences]))
        merged.interaction_boundaries = list(
            dict.fromkeys([*existing.interaction_boundaries, *incoming.interaction_boundaries])
        )
        merged.continuity_preferences = list(
            dict.fromkeys([*existing.continuity_preferences, *incoming.continuity_preferences])
        )
        return merged

    def _merge_relationship_topics(
        self,
        existing: list[RelationshipTopicRecord],
        incoming: list[RelationshipTopicRecord],
    ) -> list[RelationshipTopicRecord]:
        merged: dict[str, RelationshipTopicRecord] = {item.topic: item.model_copy(deep=True) for item in existing}
        for item in incoming:
            current = merged.get(item.topic)
            if current is None:
                merged[item.topic] = item.model_copy(deep=True)
                continue
            current.mention_count += item.mention_count
            current.first_seen_at = min(current.first_seen_at, item.first_seen_at)
            current.last_seen_at = max(current.last_seen_at, item.last_seen_at)
            current.source_refs = list(dict.fromkeys([*current.source_refs, *item.source_refs]))
        return sorted(merged.values(), key=lambda entry: (entry.mention_count, entry.last_seen_at), reverse=True)

    def _merge_relationship_threads(
        self,
        existing: list[RelationshipThreadRecord],
        incoming: list[RelationshipThreadRecord],
    ) -> list[RelationshipThreadRecord]:
        merged: list[RelationshipThreadRecord] = [item.model_copy(deep=True) for item in existing]
        for item in incoming:
            match = next(
                (
                    candidate
                    for candidate in merged
                    if self._normalized_text(candidate.summary) == self._normalized_text(item.summary)
                    or (
                        candidate.topic
                        and item.topic
                        and self._normalized_text(candidate.topic) == self._normalized_text(item.topic)
                    )
                ),
                None,
            )
            if match is None:
                merged.append(item.model_copy(deep=True))
                continue
            match.summary = item.summary
            match.kind = item.kind
            match.status = item.status
            match.follow_up_requested = match.follow_up_requested or item.follow_up_requested
            match.last_session_id = item.last_session_id or match.last_session_id
            match.updated_at = max(match.updated_at, item.updated_at)
            match.source_trace_ids = list(dict.fromkeys([*match.source_trace_ids, *item.source_trace_ids]))
            match.source_refs = list(dict.fromkeys([*match.source_refs, *item.source_refs]))
        self._expire_stale_threads(merged)
        return sorted(merged, key=lambda entry: entry.updated_at, reverse=True)

    def _merge_relationship_promises(
        self,
        existing: list[RelationshipPromiseRecord],
        incoming: list[RelationshipPromiseRecord],
    ) -> list[RelationshipPromiseRecord]:
        merged: list[RelationshipPromiseRecord] = [item.model_copy(deep=True) for item in existing]
        for item in incoming:
            match = next(
                (
                    candidate
                    for candidate in merged
                    if self._normalized_text(candidate.summary) == self._normalized_text(item.summary)
                ),
                None,
            )
            if match is None:
                merged.append(item.model_copy(deep=True))
                continue
            match.status = item.status
            match.due_at = item.due_at or match.due_at
            match.updated_at = max(match.updated_at, item.updated_at)
            match.source_trace_ids = list(dict.fromkeys([*match.source_trace_ids, *item.source_trace_ids]))
            match.source_refs = list(dict.fromkeys([*match.source_refs, *item.source_refs]))
        return sorted(merged, key=lambda entry: entry.updated_at, reverse=True)

    def _normalized_relationship_threads(
        self,
        threads: list[RelationshipThreadRecord],
    ) -> list[RelationshipThreadRecord]:
        normalized = [item.model_copy(deep=True) for item in threads if item.summary.strip()]
        self._expire_stale_threads(normalized)
        return normalized

    def _expire_stale_threads(self, threads: list[RelationshipThreadRecord]) -> None:
        now = utc_now()
        for item in threads:
            stale_after = (
                self.emotional_thread_stale_after
                if item.kind.value == "emotional"
                else self.thread_stale_after
            )
            if item.status == RelationshipThreadStatus.RESOLVED:
                continue
            if item.updated_at <= now - stale_after:
                item.status = RelationshipThreadStatus.STALE

    def _normalized_relationship_promises(
        self,
        promises: list[RelationshipPromiseRecord],
    ) -> list[RelationshipPromiseRecord]:
        return [item.model_copy(deep=True) for item in promises if item.summary.strip()]

    def _relationship_block_reason(self, record: RelationshipMemoryRecord) -> str | None:
        if not (
            record.preferred_style.greeting_preference
            or record.preferred_style.planning_style
            or record.preferred_style.tone_preferences
            or record.preferred_style.interaction_boundaries
            or record.preferred_style.continuity_preferences
            or record.recurring_topics
            or record.open_threads
            or record.promises
        ):
            return "relationship_empty"
        for thread in record.open_threads:
            if self._contains_sensitive_auto_store_text(thread.summary) and not thread.follow_up_requested:
                return "relationship_sensitive_thread_without_followup"
            if thread.kind.value == "emotional" and not thread.follow_up_requested:
                return "relationship_emotional_thread_without_followup"
        return None

    def _relationship_summary(self, record: RelationshipMemoryRecord) -> str:
        open_threads = [item.summary for item in record.open_threads if item.status.value == "open"][:2]
        promises = [item.summary for item in record.promises if item.status.value == "open"][:2]
        topic_text = ", ".join(item.topic for item in record.recurring_topics[:3]) or "none"
        style_tokens = list(
            dict.fromkeys(
                [
                    *(record.preferred_style.tone_preferences or []),
                    *(record.preferred_style.interaction_boundaries or []),
                    *(record.preferred_style.continuity_preferences or []),
                ]
            )
        )
        style_text = ", ".join(style_tokens[:4]) or "none"
        return (
            f"familiarity={record.familiarity:.2f}; "
            f"topics={topic_text}; "
            f"open_threads={'; '.join(open_threads) or 'none'}; "
            f"promises={'; '.join(promises) or 'none'}; "
            f"style={style_text}"
        )

    def _contains_sensitive_auto_store_text(self, text: str | None) -> bool:
        if not text:
            return False
        return bool(_SENSITIVE_AUTO_STORE_RE.search(text))

    def _normalized_text(self, value: str | None) -> str:
        if not value:
            return ""
        return " ".join(value.strip().lower().split())

    def _merge_sensitive_flags(
        self,
        existing: list[SensitiveContentFlag],
        incoming: list[SensitiveContentFlag],
    ) -> list[SensitiveContentFlag]:
        merged = list(existing)
        for flag in incoming:
            if flag not in merged:
                merged.append(flag)
        return merged

    def _clamp(self, value: float) -> float:
        return max(0.0, min(1.0, round(value, 3)))
