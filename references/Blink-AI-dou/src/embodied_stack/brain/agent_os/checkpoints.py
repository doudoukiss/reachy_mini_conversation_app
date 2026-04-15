from __future__ import annotations

from dataclasses import dataclass, field
import logging

from embodied_stack.observability import log_event
from embodied_stack.shared.models import (
    CheckpointKind,
    CheckpointRecord,
    CheckpointStatus,
    CommandType,
    FallbackClassification,
    RobotEvent,
    RunPhase,
    RunRecord,
    RunStatus,
    utc_now,
)

from .lifecycle import assert_phase_transition, assert_status_transition
from .trace_store import AgentOSTraceStore

logger = logging.getLogger(__name__)


@dataclass
class ActiveRunState:
    run: RunRecord
    checkpoints: list[CheckpointRecord] = field(default_factory=list)

    @property
    def last_checkpoint_id(self) -> str | None:
        if not self.checkpoints:
            return None
        return self.checkpoints[-1].checkpoint_id


class RunTracker:
    def __init__(self, store: AgentOSTraceStore) -> None:
        self.store = store

    def start_run(
        self,
        *,
        session_id: str,
        event: RobotEvent,
        provider_failure_active: bool,
        replayed_from_run_id: str | None = None,
        resumed_from_checkpoint_id: str | None = None,
        notes: list[str] | None = None,
    ) -> ActiveRunState:
        record = RunRecord(
            session_id=session_id,
            event_type=event.event_type,
            provider_failure_active=provider_failure_active,
            replayed_from_run_id=replayed_from_run_id,
            resumed_from_checkpoint_id=resumed_from_checkpoint_id,
            source_event=event.model_dump(mode="json"),
            notes=list(notes or []),
        )
        self.store.save_run(record)
        log_event(
            logger,
            logging.INFO,
            "agent_run_started",
            run_id=record.run_id,
            session_id=session_id,
            event_type=event.event_type,
        )
        active = ActiveRunState(run=record)
        self.create_checkpoint(
            active,
            phase=record.phase,
            kind=CheckpointKind.TURN_BOUNDARY,
            label="turn_start",
            reason="run_started",
            payload={"event_type": event.event_type},
            notes=["turn_boundary"],
        )
        return active

    def advance(
        self,
        active: ActiveRunState,
        *,
        phase: RunPhase,
        active_skill: str | None = None,
        active_playbook: str | None = None,
        active_playbook_variant: str | None = None,
        active_subagent: str | None = None,
        intent: str | None = None,
        reply_text: str | None = None,
        fallback_reason: str | None = None,
        fallback_classification: FallbackClassification | None = None,
        unavailable_capabilities: list[str] | None = None,
        intentionally_skipped_capabilities: list[str] | None = None,
        failure_state: str | None = None,
        tool_name: str | None = None,
        note: str | None = None,
    ) -> ActiveRunState:
        assert_phase_transition(active.run.phase, phase)
        updated_notes = list(active.run.notes)
        if note:
            updated_notes.append(note)
        updated = active.run.model_copy(
            update={
                "phase": phase,
                "active_skill": active_skill if active_skill is not None else active.run.active_skill,
                "active_playbook": (
                    active_playbook if active_playbook is not None else active.run.active_playbook
                ),
                "active_playbook_variant": (
                    active_playbook_variant
                    if active_playbook_variant is not None
                    else active.run.active_playbook_variant
                ),
                "active_subagent": active_subagent if active_subagent is not None else active.run.active_subagent,
                "intent": intent if intent is not None else active.run.intent,
                "reply_text": reply_text if reply_text is not None else active.run.reply_text,
                "fallback_reason": fallback_reason if fallback_reason is not None else active.run.fallback_reason,
                "fallback_classification": (
                    fallback_classification
                    if fallback_classification is not None
                    else active.run.fallback_classification
                ),
                "unavailable_capabilities": (
                    list(unavailable_capabilities)
                    if unavailable_capabilities is not None
                    else list(active.run.unavailable_capabilities)
                ),
                "intentionally_skipped_capabilities": (
                    list(intentionally_skipped_capabilities)
                    if intentionally_skipped_capabilities is not None
                    else list(active.run.intentionally_skipped_capabilities)
                ),
                "failure_state": failure_state if failure_state is not None else active.run.failure_state,
                "tool_names": (
                    [*active.run.tool_names, tool_name]
                    if tool_name and tool_name not in active.run.tool_names
                    else list(active.run.tool_names)
                ),
                "tool_chain": (
                    [*active.run.tool_chain, tool_name]
                    if tool_name and tool_name not in active.run.tool_chain
                    else list(active.run.tool_chain)
                ),
                "notes": updated_notes,
                "updated_at": utc_now(),
            }
        )
        self.store.save_run(updated)
        active.run = updated
        return active

    def create_checkpoint(
        self,
        active: ActiveRunState,
        *,
        phase: RunPhase,
        kind: CheckpointKind = CheckpointKind.TURN_BOUNDARY,
        label: str,
        reason: str | None = None,
        tool_name: str | None = None,
        resumable: bool = False,
        payload: dict[str, object] | None = None,
        result_payload: dict[str, object] | None = None,
        resumable_payload: dict[str, object] | None = None,
        recovery_notes: list[str] | None = None,
        notes: list[str] | None = None,
    ) -> CheckpointRecord:
        checkpoint = CheckpointRecord(
            run_id=active.run.run_id,
            session_id=active.run.session_id,
            phase=phase,
            kind=kind,
            label=label,
            reason=reason,
            tool_name=tool_name,
            active_skill=active.run.active_skill,
            active_subagent=active.run.active_subagent,
            resumable=resumable,
            payload=dict(payload or {}),
            result_payload=dict(result_payload or {}),
            resumable_payload=dict(resumable_payload or {}),
            recovery_notes=list(recovery_notes or []),
            notes=list(notes or []),
        )
        self.store.save_checkpoint(checkpoint)
        active.checkpoints.append(checkpoint)
        active.run = active.run.model_copy(
            update={
                "checkpoint_ids": [*active.run.checkpoint_ids, checkpoint.checkpoint_id],
                "updated_at": utc_now(),
            }
        )
        self.store.save_run(active.run)
        log_event(
            logger,
            logging.INFO,
            "agent_checkpoint_created",
            run_id=active.run.run_id,
            checkpoint_id=checkpoint.checkpoint_id,
            session_id=active.run.session_id,
            phase=phase.value,
            checkpoint_kind=kind.value,
            tool_name=tool_name,
            label=label,
        )
        return checkpoint

    def attach_trace(self, active: ActiveRunState, trace_id: str) -> RunRecord:
        active.run = active.run.model_copy(update={"trace_id": trace_id, "updated_at": utc_now()})
        self.store.save_run(active.run)
        updated_checkpoints: list[CheckpointRecord] = []
        for checkpoint in active.checkpoints:
            attached = checkpoint.model_copy(update={"trace_id": trace_id, "updated_at": utc_now()})
            self.store.save_checkpoint(attached)
            updated_checkpoints.append(attached)
        active.checkpoints = updated_checkpoints
        log_event(
            logger,
            logging.INFO,
            "agent_run_trace_attached",
            run_id=active.run.run_id,
            session_id=active.run.session_id,
            trace_id=trace_id,
            checkpoint_id=active.last_checkpoint_id,
        )
        return active.run

    def complete(
        self,
        active: ActiveRunState,
        *,
        intent: str,
        reply_text: str | None,
        command_types: list[CommandType],
        fallback_reason: str | None = None,
        fallback_classification: FallbackClassification | None = None,
    ) -> RunRecord:
        assert_status_transition(active.run.status, RunStatus.COMPLETED)
        active.run = active.run.model_copy(
            update={
                "phase": RunPhase.COMPLETED,
                "status": RunStatus.COMPLETED,
                "intent": intent,
                "reply_text": reply_text,
                "command_types": list(command_types),
                "fallback_reason": fallback_reason if fallback_reason is not None else active.run.fallback_reason,
                "fallback_classification": (
                    fallback_classification
                    if fallback_classification is not None
                    else active.run.fallback_classification
                ),
                "updated_at": utc_now(),
                "completed_at": utc_now(),
            }
        )
        self.store.save_run(active.run)
        log_event(
            logger,
            logging.INFO,
            "agent_run_completed",
            run_id=active.run.run_id,
            session_id=active.run.session_id,
            trace_id=active.run.trace_id,
            checkpoint_id=active.last_checkpoint_id,
            intent=intent,
            command_count=len(command_types),
            fallback_reason=active.run.fallback_reason,
        )
        return active.run

    def fail(self, active: ActiveRunState, *, failure_state: str, note: str | None = None) -> RunRecord:
        assert_status_transition(active.run.status, RunStatus.FAILED)
        notes = list(active.run.notes)
        if note:
            notes.append(note)
        active.run = active.run.model_copy(
            update={
                "phase": RunPhase.FAILED,
                "status": RunStatus.FAILED,
                "failure_state": failure_state,
                "notes": notes,
                "updated_at": utc_now(),
                "completed_at": utc_now(),
            }
        )
        self.store.save_run(active.run)
        log_event(
            logger,
            logging.ERROR,
            "agent_run_failed",
            run_id=active.run.run_id,
            session_id=active.run.session_id,
            trace_id=active.run.trace_id,
            checkpoint_id=active.last_checkpoint_id,
            failure_state=failure_state,
        )
        return active.run

    def pause(
        self,
        active: ActiveRunState,
        *,
        reason: str,
        resumable_payload: dict[str, object] | None = None,
        recovery_notes: list[str] | None = None,
    ) -> RunRecord:
        assert_status_transition(active.run.status, RunStatus.PAUSED)
        checkpoint = self.create_checkpoint(
            active,
            phase=active.run.phase,
            kind=CheckpointKind.PAUSE_BOUNDARY,
            label="pause_boundary",
            reason=reason,
            resumable=True,
            resumable_payload=resumable_payload,
            recovery_notes=recovery_notes,
            notes=[reason],
        )
        active.run = active.run.model_copy(
            update={
                "status": RunStatus.PAUSED,
                "paused_from_checkpoint_id": checkpoint.checkpoint_id,
                "paused_at": utc_now(),
                "recovery_notes": [*active.run.recovery_notes, *(recovery_notes or [])],
                "updated_at": utc_now(),
            }
        )
        self.store.save_run(active.run)
        return active.run

    def await_confirmation(
        self,
        active: ActiveRunState,
        *,
        reason: str,
        resumable_payload: dict[str, object] | None = None,
    ) -> RunRecord:
        assert_status_transition(active.run.status, RunStatus.AWAITING_CONFIRMATION)
        checkpoint = self.create_checkpoint(
            active,
            phase=active.run.phase,
            kind=CheckpointKind.PAUSE_BOUNDARY,
            label="awaiting_confirmation",
            reason=reason,
            resumable=True,
            resumable_payload=resumable_payload,
            recovery_notes=[reason],
            notes=[reason],
        )
        active.run = active.run.model_copy(
            update={
                "status": RunStatus.AWAITING_CONFIRMATION,
                "paused_from_checkpoint_id": checkpoint.checkpoint_id,
                "updated_at": utc_now(),
            }
        )
        self.store.save_run(active.run)
        return active.run

    def resume(self, active: ActiveRunState, *, checkpoint_id: str | None = None, note: str | None = None) -> RunRecord:
        assert_status_transition(active.run.status, RunStatus.RUNNING)
        notes = list(active.run.recovery_notes)
        if note:
            notes.append(note)
        active.run = active.run.model_copy(
            update={
                "status": RunStatus.RUNNING,
                "paused_from_checkpoint_id": checkpoint_id or active.run.paused_from_checkpoint_id,
                "recovery_notes": notes,
                "updated_at": utc_now(),
            }
        )
        self.store.save_run(active.run)
        return active.run

    def abort(self, active: ActiveRunState, *, reason: str) -> RunRecord:
        assert_status_transition(active.run.status, RunStatus.ABORTED)
        self.create_checkpoint(
            active,
            phase=active.run.phase,
            kind=CheckpointKind.ABORT_BOUNDARY,
            label="abort_boundary",
            reason=reason,
            notes=[reason],
        )
        active.run = active.run.model_copy(
            update={
                "status": RunStatus.ABORTED,
                "aborted_at": utc_now(),
                "completed_at": utc_now(),
                "updated_at": utc_now(),
                "notes": [*active.run.notes, reason],
            }
        )
        self.store.save_run(active.run)
        return active.run

    def mark_checkpoint_resumed(self, checkpoint_id: str, resumed_to_run_id: str) -> CheckpointRecord | None:
        checkpoint = self.store.get_checkpoint(checkpoint_id)
        if checkpoint is None:
            return None
        updated = checkpoint.model_copy(
            update={
                "status": CheckpointStatus.RESUMED,
                "resumed_to_run_id": resumed_to_run_id,
                "updated_at": utc_now(),
            }
        )
        self.store.save_checkpoint(updated)
        return updated

    def mark_checkpoint_replayed(self, checkpoint_id: str, replayed_to_run_id: str) -> CheckpointRecord | None:
        checkpoint = self.store.get_checkpoint(checkpoint_id)
        if checkpoint is None:
            return None
        updated = checkpoint.model_copy(
            update={
                "status": CheckpointStatus.REPLAYED,
                "replayed_to_run_id": replayed_to_run_id,
                "updated_at": utc_now(),
            }
        )
        self.store.save_checkpoint(updated)
        return updated


__all__ = [
    "ActiveRunState",
    "RunTracker",
]
