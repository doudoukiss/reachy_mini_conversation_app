from __future__ import annotations

from dataclasses import dataclass, replace
import json
import logging
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Callable
from uuid import uuid4
from zoneinfo import ZoneInfo

from embodied_stack.action_plane.workflows.definitions import (
    WorkflowStepTemplate,
    get_workflow_definition,
    get_workflow_steps,
    list_workflow_definitions,
)
from embodied_stack.action_plane.workflows.store import WorkflowRunStore
from embodied_stack.config import Settings
from embodied_stack.observability import log_event
from embodied_stack.persistence import write_json_atomic
from embodied_stack.shared.contracts.action import (
    ActionApprovalResolutionRecord,
    ActionArtifactRecord,
    ActionExecutionStatus,
    ActionInvocationOrigin,
    BrowserRequestedAction,
    WorkflowCatalogResponse,
    WorkflowDefinitionRecord,
    WorkflowFailureClass,
    WorkflowPauseReason,
    WorkflowRunActionRequestRecord,
    WorkflowRunActionResponseRecord,
    WorkflowRunListResponse,
    WorkflowRunRecord,
    WorkflowRunStatus,
    WorkflowStartRequestRecord,
    WorkflowStepKind,
    WorkflowStepRecord,
    WorkflowStepStatus,
    WorkflowTriggerKind,
    WorkflowTriggerRecord,
)
from embodied_stack.shared.contracts._common import (
    CompanionContextMode,
    ReminderStatus,
    ToolResultStatus,
    datetime,
    utc_now,
)
from embodied_stack.shared.contracts.brain import ShiftSupervisorSnapshot

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class WorkflowTriggerProposal:
    workflow_id: str
    trigger: WorkflowTriggerRecord
    inputs: dict[str, Any]
    note: str | None = None
    suggested_only: bool = False


@dataclass(frozen=True)
class _StepOutcome:
    step_status: WorkflowStepStatus
    summary: str | None = None
    detail: str | None = None
    output_payload: dict[str, Any] | None = None
    state_updates: dict[str, Any] | None = None
    artifacts: list[ActionArtifactRecord] | None = None
    action_id: str | None = None
    blocking_action_id: str | None = None
    failure_class: WorkflowFailureClass | None = None
    pause_reason: WorkflowPauseReason | None = None


class WorkflowRuntime:
    def __init__(
        self,
        *,
        root_dir: str | Path,
        settings: Settings,
        tool_registry,
        action_gateway,
        body_feedback_callback: Callable[[str, WorkflowRunRecord], None] | None = None,
    ) -> None:
        self.root_dir = Path(root_dir)
        self.settings = settings
        self.tool_registry = tool_registry
        self.action_gateway = action_gateway
        self.store = WorkflowRunStore(self.root_dir)
        self.body_feedback_callback = body_feedback_callback

    def list_definitions(self) -> WorkflowCatalogResponse:
        return WorkflowCatalogResponse(items=list_workflow_definitions())

    def list_runs(self, *, session_id: str | None = None, limit: int = 50) -> WorkflowRunListResponse:
        return WorkflowRunListResponse(items=self.store.list_runs(session_id=session_id, limit=limit))

    def get_run(self, workflow_run_id: str) -> WorkflowRunRecord | None:
        return self.store.get_run(workflow_run_id)

    def summary_status(self) -> dict[str, Any]:
        runs = self.store.list_runs(limit=100)
        active = [item for item in runs if item.status in {
            WorkflowRunStatus.RUNNING,
            WorkflowRunStatus.PAUSED,
            WorkflowRunStatus.WAITING_FOR_APPROVAL,
            WorkflowRunStatus.SUGGESTED,
        }]
        waiting = [item for item in runs if item.status == WorkflowRunStatus.WAITING_FOR_APPROVAL]
        review_required = [
            item for item in runs if item.pause_reason == WorkflowPauseReason.RUNTIME_RESTART_REVIEW
        ]
        latest = runs[0] if runs else None
        return {
            "active_workflow_run_count": len(active),
            "waiting_workflow_count": len(waiting),
            "review_required_count": len(review_required),
            "last_workflow_run_id": latest.workflow_run_id if latest is not None else None,
            "last_workflow_status": latest.status if latest is not None else None,
        }

    def reconcile_restart_review(self) -> list[WorkflowRunRecord]:
        updated: list[WorkflowRunRecord] = []
        for run in self.store.list_runs(limit=None):
            if run.status in {
                WorkflowRunStatus.COMPLETED,
                WorkflowRunStatus.CANCELLED,
                WorkflowRunStatus.TIMED_OUT,
                WorkflowRunStatus.SUGGESTED,
            }:
                continue
            current = self._current_step(run)
            if current is None:
                continue
            linked_action_id = current.blocking_action_id or run.blocking_action_id or current.action_id
            linked_execution = (
                self.action_gateway.get_execution(linked_action_id) if linked_action_id is not None else None
            )
            if (
                run.status == WorkflowRunStatus.WAITING_FOR_APPROVAL
                and run.blocking_action_id
                and self.action_gateway.get_pending_approval(run.blocking_action_id) is not None
            ):
                continue
            if not (
                run.status == WorkflowRunStatus.RUNNING
                or current.status == WorkflowStepStatus.RUNNING
                or (
                    run.status == WorkflowRunStatus.WAITING_FOR_APPROVAL
                    and run.blocking_action_id
                    and (
                        linked_execution is None
                        or linked_execution.status != ActionExecutionStatus.PENDING_APPROVAL
                    )
                )
                or (
                    linked_execution is not None
                    and linked_execution.status == ActionExecutionStatus.UNCERTAIN_REVIEW_REQUIRED
                )
            ):
                continue
            current.status = WorkflowStepStatus.FAILED
            current.detail = "runtime_restart_review_required"
            current.blocking_action_id = linked_action_id
            current.finished_at = current.finished_at or utc_now()
            run.status = WorkflowRunStatus.PAUSED
            run.pause_reason = WorkflowPauseReason.RUNTIME_RESTART_REVIEW
            run.failure_class = WorkflowFailureClass.EXECUTION_ERROR
            run.blocking_action_id = linked_action_id
            run.current_step_id = current.step_id
            run.current_step_label = current.label
            run.detail = "runtime_restart_review_required"
            updated.append(self._save_run(run))
        return updated

    def start_workflow(
        self,
        *,
        request: WorkflowStartRequestRecord,
        tool_context,
        trigger: WorkflowTriggerRecord | None = None,
        suggested_only: bool = False,
    ) -> WorkflowRunActionResponseRecord:
        definition = self._require_definition(request.workflow_id)
        run = WorkflowRunRecord(
            workflow_run_id=f"wf_{uuid4().hex[:16]}",
            workflow_id=definition.workflow_id,
            label=definition.label,
            version=definition.version,
            status=WorkflowRunStatus.SUGGESTED if suggested_only else WorkflowRunStatus.RUNNING,
            trigger=trigger or self._default_trigger(request=request, tool_context=tool_context),
            session_id=tool_context.session.session_id,
            context_mode=tool_context.context_mode.value,
            started_by=tool_context.action_invocation_origin,
            proactive=tool_context.action_invocation_origin == ActionInvocationOrigin.PROACTIVE_RUNTIME,
            suggested_only=suggested_only,
            summary=request.note,
            inputs=dict(request.inputs),
            steps=self._instantiate_steps(definition.workflow_id),
            started_at=None if suggested_only else utc_now(),
        )
        self._save_run(run)
        if suggested_only:
            self._emit_body_feedback("safe_idle", run)
            return WorkflowRunActionResponseRecord(
                run=run,
                detail=request.note or "workflow_suggested",
            )
        return self._execute_run(run.workflow_run_id, tool_context=tool_context)

    def resume_workflow(
        self,
        *,
        workflow_run_id: str,
        request: WorkflowRunActionRequestRecord,
        tool_context,
    ) -> WorkflowRunActionResponseRecord:
        run = self._require_run(workflow_run_id)
        if run.status == WorkflowRunStatus.COMPLETED:
            return WorkflowRunActionResponseRecord(run=run, detail="workflow_already_completed")
        if run.pause_reason == WorkflowPauseReason.RUNTIME_RESTART_REVIEW:
            run = self._prepare_restart_review_resume(run, note=request.note)
        if run.status == WorkflowRunStatus.WAITING_FOR_APPROVAL and run.blocking_action_id:
            if self.action_gateway.get_pending_approval(run.blocking_action_id) is not None:
                return WorkflowRunActionResponseRecord(run=run, detail="workflow_waiting_for_approval")
        run.status = WorkflowRunStatus.RUNNING
        run.pause_reason = None
        run.failure_class = None
        run.detail = request.note or run.detail
        if run.started_at is None:
            run.started_at = utc_now()
        self._save_run(run)
        response = self._execute_run(workflow_run_id, tool_context=tool_context)
        return response.model_copy(update={"resumed": True})

    def retry_workflow_step(
        self,
        *,
        workflow_run_id: str,
        request: WorkflowRunActionRequestRecord,
        tool_context,
    ) -> WorkflowRunActionResponseRecord:
        run = self._require_run(workflow_run_id)
        step = self._current_step(run)
        if step is None:
            return WorkflowRunActionResponseRecord(run=run, detail="workflow_has_no_retryable_step")
        if step.status not in {WorkflowStepStatus.FAILED, WorkflowStepStatus.WAITING_FOR_APPROVAL}:
            return WorkflowRunActionResponseRecord(run=run, detail="workflow_step_not_retryable")
        if step.status == WorkflowStepStatus.WAITING_FOR_APPROVAL and run.blocking_action_id:
            if self.action_gateway.get_pending_approval(run.blocking_action_id) is not None:
                return WorkflowRunActionResponseRecord(run=run, detail="workflow_waiting_for_approval")
        step.status = WorkflowStepStatus.PENDING
        step.detail = request.note or "workflow_step_retry_requested"
        step.blocking_action_id = None
        run.blocking_action_id = None
        run.pause_reason = None
        run.failure_class = None
        run.status = WorkflowRunStatus.RUNNING
        self._save_run(run)
        response = self._execute_run(
            workflow_run_id,
            tool_context=tool_context,
            retry_namespace=f"workflow-retry:{workflow_run_id}:{step.step_id}:{uuid4().hex[:8]}",
        )
        return response.model_copy(update={"retried": True})

    def pause_workflow(
        self,
        *,
        workflow_run_id: str,
        request: WorkflowRunActionRequestRecord,
    ) -> WorkflowRunActionResponseRecord:
        run = self._require_run(workflow_run_id)
        run.status = WorkflowRunStatus.PAUSED
        run.pause_reason = WorkflowPauseReason.OPERATOR_PAUSED
        run.detail = request.note or "workflow_paused_by_operator"
        self._save_run(run)
        self._emit_body_feedback("safe_idle", run)
        return WorkflowRunActionResponseRecord(run=run, detail=run.detail, paused=True)

    def handle_action_resolution(
        self,
        *,
        resolution: ActionApprovalResolutionRecord,
        tool_context,
    ) -> WorkflowRunActionResponseRecord | None:
        execution = resolution.execution
        approval = resolution.approval
        workflow_run_id = execution.workflow_run_id if execution is not None else approval.workflow_run_id if approval is not None else None
        workflow_step_id = (
            execution.workflow_step_id
            if execution is not None
            else approval.workflow_step_id if approval is not None else None
        )
        if workflow_run_id is None:
            return None
        run = self.store.get_run(workflow_run_id)
        if run is None:
            return None
        step = self._step_by_id(run, workflow_step_id)
        if step is None:
            return None
        if resolution.approval_state.value == "rejected":
            step.status = WorkflowStepStatus.FAILED
            step.detail = resolution.detail or "approval_rejected"
            step.blocking_action_id = None
            run.status = WorkflowRunStatus.PAUSED
            run.pause_reason = WorkflowPauseReason.APPROVAL_REJECTED
            run.failure_class = WorkflowFailureClass.APPROVAL_REJECTED
            run.blocking_action_id = None
            run.detail = resolution.detail or "approval_rejected"
            self._save_run(run)
            self._emit_body_feedback("waiting_for_approval", run)
            return WorkflowRunActionResponseRecord(run=run, detail=run.detail)
        if execution.status not in {ActionExecutionStatus.EXECUTED, ActionExecutionStatus.REUSED}:
            step.status = WorkflowStepStatus.FAILED
            step.detail = execution.detail or execution.error_detail or execution.status.value
            run.status = WorkflowRunStatus.FAILED
            run.pause_reason = WorkflowPauseReason.FAILED_STEP
            run.failure_class = WorkflowFailureClass.ACTION_FAILED
            run.blocking_action_id = None
            self._save_run(run)
            self._emit_body_feedback("safe_idle", run)
            return WorkflowRunActionResponseRecord(run=run, detail=run.detail)
        step.status = WorkflowStepStatus.COMPLETED
        step.action_id = execution.action_id
        step.action_ids = [*step.action_ids, execution.action_id]
        step.output_payload = dict(execution.output_payload)
        step.summary = execution.detail or execution.status.value
        step.detail = execution.detail
        step.blocking_action_id = None
        step.finished_at = utc_now()
        run.blocking_action_id = None
        run.pause_reason = None
        run.failure_class = None
        run.status = WorkflowRunStatus.RUNNING
        self._update_run_for_completed_step(run, step=step, output_payload=step.output_payload)
        self._save_run(run)
        return self.resume_workflow(
            workflow_run_id=run.workflow_run_id,
            request=WorkflowRunActionRequestRecord(note="approval_resolved_resume"),
            tool_context=tool_context,
        )

    def evaluate_due_triggers(
        self,
        *,
        tool_context,
        shift_snapshot: ShiftSupervisorSnapshot,
        now: datetime | None = None,
    ) -> list[WorkflowRunActionResponseRecord]:
        active_session_id = tool_context.session.session_id
        if shift_snapshot.quiet_hours_active:
            log_event(
                logger,
                logging.INFO,
                "workflow_triggers_suppressed",
                session_id=active_session_id,
                reason="quiet_hours_active",
            )
            return []
        if self._has_active_proactive_run(active_session_id):
            return []
        proposals = self._build_trigger_proposals(
            tool_context=tool_context,
            shift_snapshot=shift_snapshot,
            now=now or utc_now(),
        )
        results: list[WorkflowRunActionResponseRecord] = []
        for proposal in proposals:
            if self.store.trigger_seen(proposal.trigger.trigger_key):
                continue
            request = WorkflowStartRequestRecord(
                workflow_id=proposal.workflow_id,
                session_id=tool_context.session.session_id,
                inputs=proposal.inputs,
                note=proposal.note,
            )
            response = self.start_workflow(
                request=request,
                tool_context=tool_context,
                trigger=proposal.trigger,
                suggested_only=proposal.suggested_only,
            )
            self.store.mark_trigger_seen(
                trigger_key=proposal.trigger.trigger_key,
                workflow_id=proposal.workflow_id,
                session_id=tool_context.session.session_id,
                run_id=response.run.workflow_run_id,
            )
            results.append(response)
        return results

    def _execute_run(
        self,
        workflow_run_id: str,
        *,
        tool_context,
        retry_namespace: str | None = None,
    ) -> WorkflowRunActionResponseRecord:
        run = self._require_run(workflow_run_id)
        self._emit_body_feedback("thinking", run)
        while True:
            if self._timed_out(run):
                run.status = WorkflowRunStatus.TIMED_OUT
                run.pause_reason = WorkflowPauseReason.TIMED_OUT
                run.failure_class = WorkflowFailureClass.TIMEOUT
                run.detail = "workflow_timed_out"
                run.finished_at = utc_now()
                self._save_run(run)
                self._emit_body_feedback("safe_idle", run)
                return WorkflowRunActionResponseRecord(run=run, detail=run.detail)
            step = self._current_step(run)
            if step is None:
                run.status = WorkflowRunStatus.COMPLETED
                run.pause_reason = None
                run.failure_class = None
                run.current_step_id = None
                run.current_step_label = None
                run.finished_at = utc_now()
                run.summary = run.summary or "workflow_completed"
                self._save_run(run)
                self._emit_body_feedback("acknowledging", run)
                self._emit_body_feedback("safe_idle", run)
                return WorkflowRunActionResponseRecord(run=run, detail=run.summary)
            if step.status == WorkflowStepStatus.WAITING_FOR_APPROVAL and run.blocking_action_id:
                if self.action_gateway.get_pending_approval(run.blocking_action_id) is not None:
                    run.status = WorkflowRunStatus.WAITING_FOR_APPROVAL
                    run.pause_reason = WorkflowPauseReason.WAITING_FOR_APPROVAL
                    run.current_step_id = step.step_id
                    run.current_step_label = step.label
                    self._save_run(run)
                    self._emit_body_feedback("waiting_for_approval", run)
                    return WorkflowRunActionResponseRecord(run=run, detail=step.detail or "approval_required")
                step.status = WorkflowStepStatus.PENDING
                step.blocking_action_id = None
                run.blocking_action_id = None
            if step.status == WorkflowStepStatus.FAILED:
                run.status = WorkflowRunStatus.FAILED
                run.pause_reason = WorkflowPauseReason.FAILED_STEP
                run.current_step_id = step.step_id
                run.current_step_label = step.label
                run.finished_at = utc_now()
                self._save_run(run)
                self._emit_body_feedback("safe_idle", run)
                return WorkflowRunActionResponseRecord(run=run, detail=step.detail or "workflow_failed")
            run.status = WorkflowRunStatus.RUNNING
            run.current_step_id = step.step_id
            run.current_step_label = step.label
            step.status = WorkflowStepStatus.RUNNING
            step.started_at = step.started_at or utc_now()
            step.attempt_count += 1
            self._save_run(run)
            outcome = self._execute_step(
                run=run,
                step=step,
                tool_context=tool_context,
                retry_namespace=retry_namespace,
            )
            step.summary = outcome.summary or step.summary
            step.detail = outcome.detail or step.detail
            if outcome.artifacts is not None:
                step.artifacts = outcome.artifacts
            if outcome.output_payload is not None:
                step.output_payload = outcome.output_payload
            if outcome.action_id is not None:
                step.action_id = outcome.action_id
                step.action_ids = [*step.action_ids, outcome.action_id]
            if outcome.step_status == WorkflowStepStatus.COMPLETED:
                step.status = WorkflowStepStatus.COMPLETED
                step.finished_at = utc_now()
                step.blocking_action_id = None
                run.blocking_action_id = None
                self._update_run_for_completed_step(
                    run,
                    step=step,
                    output_payload=outcome.output_payload or {},
                    state_updates=outcome.state_updates,
                )
                self._save_run(run)
                continue
            if outcome.step_status == WorkflowStepStatus.SKIPPED:
                step.status = WorkflowStepStatus.SKIPPED
                step.finished_at = utc_now()
                self._save_run(run)
                continue
            if outcome.step_status == WorkflowStepStatus.WAITING_FOR_APPROVAL:
                step.status = WorkflowStepStatus.WAITING_FOR_APPROVAL
                step.blocking_action_id = outcome.blocking_action_id
                run.status = WorkflowRunStatus.WAITING_FOR_APPROVAL
                run.pause_reason = outcome.pause_reason or WorkflowPauseReason.WAITING_FOR_APPROVAL
                run.blocking_action_id = outcome.blocking_action_id
                run.failure_class = None
                self._save_run(run)
                self._emit_body_feedback("waiting_for_approval", run)
                return WorkflowRunActionResponseRecord(run=run, detail=outcome.detail or "approval_required")
            if step.attempt_count <= step.retry_budget:
                step.status = WorkflowStepStatus.PENDING
                self._save_run(run)
                continue
            step.status = WorkflowStepStatus.FAILED
            step.finished_at = utc_now()
            run.status = WorkflowRunStatus.PAUSED if outcome.pause_reason else WorkflowRunStatus.FAILED
            run.pause_reason = outcome.pause_reason or WorkflowPauseReason.FAILED_STEP
            run.failure_class = outcome.failure_class or WorkflowFailureClass.ACTION_FAILED
            run.blocking_action_id = outcome.blocking_action_id
            run.detail = outcome.detail or step.detail
            self._save_run(run)
            self._emit_body_feedback("safe_idle", run)
            return WorkflowRunActionResponseRecord(run=run, detail=run.detail)

    def _execute_step(
        self,
        *,
        run: WorkflowRunRecord,
        step: WorkflowStepRecord,
        tool_context,
        retry_namespace: str | None,
    ) -> _StepOutcome:
        if step.kind == WorkflowStepKind.DETERMINISTIC_CHECK:
            return self._execute_check_step(run=run, step=step, tool_context=tool_context)
        if step.kind == WorkflowStepKind.SUMMARY_ARTIFACT:
            return self._execute_summary_step(run=run, step=step)
        return self._execute_connector_step(
            run=run,
            step=step,
            tool_context=tool_context,
            retry_namespace=retry_namespace,
        )

    def _execute_check_step(self, *, run: WorkflowRunRecord, step: WorkflowStepRecord, tool_context) -> _StepOutcome:
        if run.workflow_id == "capture_note_and_reminder":
            return self._capture_note_and_reminder_check(run=run)
        if run.workflow_id == "morning_briefing":
            return self._morning_briefing_check(run=run, tool_context=tool_context)
        if run.workflow_id == "event_lookup_and_open_page":
            return self._event_lookup_check(run=run, tool_context=tool_context)
        if run.workflow_id == "reminder_due_follow_up":
            return self._reminder_due_check(run=run, tool_context=tool_context)
        return _StepOutcome(
            step_status=WorkflowStepStatus.FAILED,
            detail=f"unsupported_workflow_check:{run.workflow_id}",
            failure_class=WorkflowFailureClass.EXECUTION_ERROR,
        )

    def _execute_summary_step(self, *, run: WorkflowRunRecord, step: WorkflowStepRecord) -> _StepOutcome:
        artifact_dir = self.store.run_artifact_dir(run.workflow_run_id)
        summary_payload = {
            "workflow_run_id": run.workflow_run_id,
            "workflow_id": run.workflow_id,
            "label": run.label,
            "status": run.status.value,
            "summary": self._workflow_summary_text(run),
            "detail": run.detail,
            "inputs": run.inputs,
            "state": run.state_payload,
            "steps": [item.model_dump(mode="json") for item in run.steps],
            "updated_at": utc_now().isoformat(),
        }
        summary_path = artifact_dir / "summary.json"
        write_json_atomic(summary_path, summary_payload, keep_backups=1)
        artifact = ActionArtifactRecord(
            kind="workflow_summary",
            label="Workflow Summary",
            path=str(summary_path),
            metadata={"workflow_id": run.workflow_id, "workflow_run_id": run.workflow_run_id},
        )
        return _StepOutcome(
            step_status=WorkflowStepStatus.COMPLETED,
            summary=summary_payload["summary"],
            detail="workflow_summary_written",
            output_payload={"summary_path": str(summary_path), "summary": summary_payload["summary"]},
            state_updates={"summary_path": str(summary_path), "summary_text": summary_payload["summary"]},
            artifacts=[artifact],
        )

    def _execute_connector_step(
        self,
        *,
        run: WorkflowRunRecord,
        step: WorkflowStepRecord,
        tool_context,
        retry_namespace: str | None,
    ) -> _StepOutcome:
        tool_name, payload, skip_reason = self._tool_request_for_step(run=run, step=step)
        if skip_reason is not None:
            return _StepOutcome(step_status=WorkflowStepStatus.SKIPPED, detail=skip_reason)
        child_context = replace(
            tool_context,
            run_id=tool_context.run_id or f"workflow:{run.workflow_run_id}",
            workflow_run_id=run.workflow_run_id,
            workflow_step_id=step.step_id,
            action_idempotency_namespace=retry_namespace,
        )
        record, output = self.tool_registry.invoke(tool_name, payload, context=child_context)
        output_payload = output.model_dump(mode="json") if output is not None else {}
        if record.action_status == ActionExecutionStatus.PENDING_APPROVAL:
            return _StepOutcome(
                step_status=WorkflowStepStatus.WAITING_FOR_APPROVAL,
                summary=record.summary,
                detail=record.error_detail or record.summary or "approval_required",
                output_payload=output_payload,
                action_id=record.action_id,
                blocking_action_id=record.action_id,
                pause_reason=WorkflowPauseReason.WAITING_FOR_APPROVAL,
            )
        if record.action_status == ActionExecutionStatus.PREVIEW_ONLY or record.result_status == ToolResultStatus.DEGRADED:
            return _StepOutcome(
                step_status=WorkflowStepStatus.FAILED,
                summary=record.summary,
                detail=record.error_detail or record.summary or "workflow_preview_only",
                output_payload=output_payload,
                action_id=record.action_id,
                failure_class=WorkflowFailureClass.POLICY_SUPPRESSED,
                pause_reason=WorkflowPauseReason.SUGGESTION_ONLY,
            )
        if not record.success:
            return _StepOutcome(
                step_status=WorkflowStepStatus.FAILED,
                summary=record.summary,
                detail=record.error_detail or record.error_code or record.summary or "workflow_action_failed",
                output_payload=output_payload,
                action_id=record.action_id,
                failure_class=WorkflowFailureClass.ACTION_FAILED,
            )
        return _StepOutcome(
            step_status=WorkflowStepStatus.COMPLETED,
            summary=record.summary,
            detail=record.summary,
            output_payload=output_payload,
            action_id=record.action_id,
        )

    def _capture_note_and_reminder_check(self, *, run: WorkflowRunRecord) -> _StepOutcome:
        note_content = str(run.inputs.get("note_content") or "").strip()
        reminder_text = str(run.inputs.get("reminder_text") or "").strip()
        if not note_content or not reminder_text:
            return _StepOutcome(
                step_status=WorkflowStepStatus.FAILED,
                detail="note_content_and_reminder_text_required",
                failure_class=WorkflowFailureClass.PRECONDITION_FAILED,
            )
        state_updates = {
            "note_title": str(run.inputs.get("note_title") or "Captured Note").strip() or "Captured Note",
            "note_content": note_content,
            "note_tags": list(run.inputs.get("note_tags") or []),
            "reminder_text": reminder_text,
            "reminder_due_at": run.inputs.get("due_at"),
        }
        return _StepOutcome(
            step_status=WorkflowStepStatus.COMPLETED,
            summary="validated_inputs",
            detail="workflow_inputs_validated",
            state_updates=state_updates,
            output_payload=state_updates,
        )

    def _morning_briefing_check(self, *, run: WorkflowRunRecord, tool_context) -> _StepOutcome:
        reminders = []
        latest_digest = None
        note_count = 0
        if tool_context.memory_store is not None:
            reminder_items = tool_context.memory_store.list_reminders(
                session_id=tool_context.session.session_id,
                user_id=tool_context.session.user_id,
                status=ReminderStatus.OPEN,
                limit=10,
            ).items
            reminders = [
                {
                    "reminder_id": item.reminder_id,
                    "reminder_text": item.reminder_text,
                    "due_at": item.due_at.isoformat() if item.due_at is not None else None,
                }
                for item in reminder_items
            ]
            digest_items = tool_context.memory_store.list_session_digests(
                session_id=tool_context.session.session_id,
                user_id=tool_context.session.user_id,
                limit=1,
            ).items
            if digest_items:
                latest_digest = {
                    "digest_id": digest_items[0].digest_id,
                    "summary": digest_items[0].summary,
                    "open_follow_ups": list(digest_items[0].open_follow_ups),
                }
            note_count = len(
                tool_context.memory_store.list_companion_notes(
                    session_id=tool_context.session.session_id,
                    user_id=tool_context.session.user_id,
                    limit=20,
                ).items
            )
        calendar_events = []
        venue_knowledge = getattr(tool_context.knowledge_tools, "venue_knowledge", None)
        if venue_knowledge is not None:
            for event in venue_knowledge.events[:5]:
                calendar_events.append(
                    {
                        "event_id": event.event_id,
                        "title": event.title,
                        "start_at": event.start_at.isoformat(),
                        "source_ref": event.source_ref,
                    }
                )
        target_url = run.inputs.get("target_url")
        state_updates = {
            "briefing": {
                "reminders": reminders,
                "latest_digest": latest_digest,
                "note_count": note_count,
                "calendar_events": calendar_events,
            },
            "resolved_target_url": target_url,
        }
        return _StepOutcome(
            step_status=WorkflowStepStatus.COMPLETED,
            summary="briefing_context_collected",
            detail="briefing_context_ready",
            state_updates=state_updates,
            output_payload=state_updates,
        )

    def _event_lookup_check(self, *, run: WorkflowRunRecord, tool_context) -> _StepOutcome:
        explicit_url = str(run.inputs.get("target_url") or "").strip()
        if explicit_url:
            resolved = {"current_url": explicit_url}
            if run.inputs.get("event_title"):
                resolved["event_title"] = str(run.inputs["event_title"])
            return _StepOutcome(
                step_status=WorkflowStepStatus.COMPLETED,
                summary="event_page_resolved",
                detail="event_page_from_explicit_target_url",
                state_updates=resolved,
                output_payload=resolved,
            )
        event_id = str(run.inputs.get("event_id") or "").strip()
        query = str(run.inputs.get("query") or "").strip().lower()
        venue_knowledge = getattr(tool_context.knowledge_tools, "venue_knowledge", None)
        if venue_knowledge is None:
            return _StepOutcome(
                step_status=WorkflowStepStatus.FAILED,
                detail="venue_knowledge_unavailable",
                failure_class=WorkflowFailureClass.PRECONDITION_FAILED,
            )
        matched = None
        for event in venue_knowledge.events:
            if event_id and event.event_id == event_id:
                matched = event
                break
            if query and (query in event.title.lower() or any(query in alias.lower() for alias in event.aliases)):
                matched = event
                break
        if matched is None and venue_knowledge.events:
            note = str(run.inputs.get("scheduled_prompt_note") or "")
            event_hint = note.split(":", 1)[1] if note.startswith("event_start_reminder_due:") else ""
            if event_hint:
                matched = next((item for item in venue_knowledge.events if item.event_id == event_hint), None)
        if matched is None or not str(matched.source_ref).startswith(("http://", "https://")):
            return _StepOutcome(
                step_status=WorkflowStepStatus.FAILED,
                detail="event_page_url_not_resolved",
                failure_class=WorkflowFailureClass.PRECONDITION_FAILED,
            )
        resolved = {
            "current_url": matched.source_ref,
            "event_id": matched.event_id,
            "event_title": matched.title,
            "event_summary": matched.summary,
            "event_start_at": matched.start_at.isoformat(),
        }
        return _StepOutcome(
            step_status=WorkflowStepStatus.COMPLETED,
            summary="event_page_resolved",
            detail="event_page_from_venue_knowledge",
            state_updates=resolved,
            output_payload=resolved,
        )

    def _reminder_due_check(self, *, run: WorkflowRunRecord, tool_context) -> _StepOutcome:
        if tool_context.memory_store is None:
            return _StepOutcome(
                step_status=WorkflowStepStatus.FAILED,
                detail="memory_store_unavailable",
                failure_class=WorkflowFailureClass.PRECONDITION_FAILED,
            )
        reminder_id = str(run.inputs.get("reminder_id") or "").strip()
        reminder = tool_context.memory_store.get_reminder(reminder_id) if reminder_id else None
        if reminder is None:
            now = utc_now()
            items = tool_context.memory_store.list_reminders(
                session_id=tool_context.session.session_id,
                user_id=tool_context.session.user_id,
                status=ReminderStatus.OPEN,
                limit=50,
            ).items
            reminder = next((item for item in items if item.due_at is not None and item.due_at <= now), None)
        if reminder is None:
            return _StepOutcome(
                step_status=WorkflowStepStatus.FAILED,
                detail="no_due_reminder_found",
                failure_class=WorkflowFailureClass.PRECONDITION_FAILED,
            )
        reminder_data = {
            "reminder_id": reminder.reminder_id,
            "reminder_text": reminder.reminder_text,
            "due_at": reminder.due_at.isoformat() if reminder.due_at is not None else None,
            "status": reminder.status.value,
        }
        return _StepOutcome(
            step_status=WorkflowStepStatus.COMPLETED,
            summary="due_reminder_resolved",
            detail="due_reminder_ready",
            state_updates={"due_reminder": reminder_data},
            output_payload=reminder_data,
        )

    def _tool_request_for_step(
        self,
        *,
        run: WorkflowRunRecord,
        step: WorkflowStepRecord,
    ) -> tuple[str, dict[str, Any], str | None]:
        state = run.state_payload
        if run.workflow_id == "capture_note_and_reminder":
            if step.step_key == "create_note":
                return (
                    "create_note",
                    {
                        "title": state.get("note_title") or "Captured Note",
                        "content": state.get("note_content") or "",
                        "tags": state.get("note_tags") or [],
                    },
                    None,
                )
            if step.step_key == "create_reminder":
                return (
                    "create_reminder",
                    {
                        "reminder_text": state.get("reminder_text") or "",
                        "due_at": state.get("reminder_due_at"),
                    },
                    None,
                )
        if run.workflow_id == "morning_briefing":
            if step.step_key == "open_page":
                target_url = state.get("resolved_target_url")
                if not target_url:
                    return "browser_task", {}, "no_target_url_for_open_page"
                return (
                    "browser_task",
                    {
                        "query": f"Open {target_url}",
                        "target_url": target_url,
                        "requested_action": BrowserRequestedAction.OPEN_URL.value,
                    },
                    None,
                )
            if step.step_key == "capture_snapshot":
                target_url = state.get("resolved_target_url")
                if not target_url:
                    return "browser_task", {}, "no_target_url_for_capture_snapshot"
                return (
                    "browser_task",
                    {
                        "query": "Capture morning briefing snapshot",
                        "requested_action": BrowserRequestedAction.CAPTURE_SNAPSHOT.value,
                    },
                    None,
                )
        if run.workflow_id == "event_lookup_and_open_page":
            if step.step_key == "open_page":
                target_url = state.get("current_url")
                if not target_url:
                    return "browser_task", {}, "no_resolved_event_page"
                return (
                    "browser_task",
                    {
                        "query": f"Open {target_url}",
                        "target_url": target_url,
                        "requested_action": BrowserRequestedAction.OPEN_URL.value,
                    },
                    None,
                )
            if step.step_key == "capture_snapshot":
                if not state.get("current_url"):
                    return "browser_task", {}, "no_resolved_event_page"
                return (
                    "browser_task",
                    {
                        "query": "Capture event page snapshot",
                        "requested_action": BrowserRequestedAction.CAPTURE_SNAPSHOT.value,
                    },
                    None,
                )
            if step.step_key == "follow_up_browser_action":
                requested_action = str(run.inputs.get("requested_action") or "").strip()
                if requested_action not in {
                    BrowserRequestedAction.CLICK_TARGET.value,
                    BrowserRequestedAction.TYPE_TEXT.value,
                    BrowserRequestedAction.SUBMIT_FORM.value,
                }:
                    return "browser_task", {}, "no_effectful_follow_up_requested"
                payload = {
                    "query": str(run.inputs.get("query") or run.label),
                    "requested_action": requested_action,
                    "target_hint": run.inputs.get("target_hint"),
                    "text_input": run.inputs.get("text_input"),
                }
                return ("browser_task", payload, None)
        return (step.tool_name or "", {}, f"unsupported_connector_step:{run.workflow_id}:{step.step_key}")

    def _update_run_for_completed_step(
        self,
        run: WorkflowRunRecord,
        *,
        step: WorkflowStepRecord,
        output_payload: dict[str, Any],
        state_updates: dict[str, Any] | None = None,
    ) -> None:
        if state_updates:
            run.state_payload = {**run.state_payload, **state_updates}
        if step.artifacts:
            existing = {(item.kind, item.path) for item in run.artifacts}
            for artifact in step.artifacts:
                key = (artifact.kind, artifact.path)
                if key not in existing:
                    run.artifacts.append(artifact)
                    existing.add(key)
        if step.step_key == "create_note" and output_payload.get("note_id"):
            run.state_payload["note_id"] = output_payload.get("note_id")
        if step.step_key == "create_reminder" and output_payload.get("reminder_id"):
            run.state_payload["reminder_id"] = output_payload.get("reminder_id")
        if step.step_key == "capture_snapshot":
            run.state_payload["latest_snapshot"] = output_payload.get("snapshot") or output_payload.get("result")
        if step.step_key == "follow_up_browser_action":
            run.state_payload["follow_up_result"] = output_payload.get("result") or output_payload
        if step.step_key == "write_summary":
            run.summary = output_payload.get("summary") or run.summary
        run.updated_at = utc_now()

    def _workflow_summary_text(self, run: WorkflowRunRecord) -> str:
        state = run.state_payload
        if run.workflow_id == "capture_note_and_reminder":
            return (
                f"Saved note '{state.get('note_title') or 'Captured Note'}' "
                f"and reminder '{state.get('reminder_text') or ''}'."
            ).strip()
        if run.workflow_id == "morning_briefing":
            briefing = state.get("briefing") or {}
            reminder_count = len(briefing.get("reminders") or [])
            event_count = len(briefing.get("calendar_events") or [])
            digest = briefing.get("latest_digest") or {}
            digest_summary = digest.get("summary") or "no recent digest"
            return f"Morning briefing ready with {reminder_count} reminders, {event_count} events, digest='{digest_summary}'."
        if run.workflow_id == "event_lookup_and_open_page":
            title = state.get("event_title") or "event page"
            url = state.get("current_url") or "-"
            return f"Event workflow captured '{title}' at {url}."
        if run.workflow_id == "reminder_due_follow_up":
            reminder = state.get("due_reminder") or {}
            return f"Reminder follow-up ready for '{reminder.get('reminder_text') or ''}'.".strip()
        return run.summary or f"{run.label} completed."

    def _instantiate_steps(self, workflow_id: str) -> list[WorkflowStepRecord]:
        items: list[WorkflowStepRecord] = []
        for index, template in enumerate(get_workflow_steps(workflow_id), start=1):
            items.append(
                WorkflowStepRecord(
                    step_id=f"{workflow_id}:{index}",
                    step_key=template.step_key,
                    label=template.label,
                    kind=template.kind,
                    tool_name=template.tool_name,
                    retry_budget=template.retry_budget,
                )
            )
        return items

    def _default_trigger(self, *, request: WorkflowStartRequestRecord, tool_context) -> WorkflowTriggerRecord:
        return WorkflowTriggerRecord(
            trigger_kind=(
                WorkflowTriggerKind.OPERATOR_LAUNCH
                if tool_context.action_invocation_origin == ActionInvocationOrigin.OPERATOR_CONSOLE
                else WorkflowTriggerKind.USER_REQUEST
            ),
            trigger_key=f"manual:{request.workflow_id}:{uuid4().hex[:8]}",
            source_session_id=tool_context.session.session_id,
            proactive=tool_context.action_invocation_origin == ActionInvocationOrigin.PROACTIVE_RUNTIME,
            note=request.note,
        )

    def _has_active_proactive_run(self, session_id: str | None) -> bool:
        return any(item.proactive for item in self.store.active_runs(session_id=session_id))

    def _build_trigger_proposals(
        self,
        *,
        tool_context,
        shift_snapshot: ShiftSupervisorSnapshot,
        now: datetime,
    ) -> list[WorkflowTriggerProposal]:
        proposals: list[WorkflowTriggerProposal] = []
        context_mode = tool_context.context_mode
        timezone_name = self.settings.shift_timezone or "Asia/Shanghai"
        local_now = now.astimezone(ZoneInfo(timezone_name))
        morning_hour, morning_minute = self._morning_briefing_time()
        morning_key = f"daily_digest:{tool_context.session.session_id}:{local_now.date().isoformat()}"
        if local_now.hour == morning_hour and local_now.minute >= morning_minute and not self.store.trigger_seen(morning_key):
            trigger = WorkflowTriggerRecord(
                trigger_kind=WorkflowTriggerKind.DAILY_DIGEST,
                trigger_key=morning_key,
                source_session_id=tool_context.session.session_id,
                proactive=True,
                scheduled_for=now,
                note="morning_briefing_due",
            )
            proposals.append(
                WorkflowTriggerProposal(
                    workflow_id="morning_briefing",
                    trigger=trigger,
                    inputs={},
                    note="daily_morning_briefing",
                    suggested_only=context_mode == CompanionContextMode.VENUE_DEMO,
                )
            )
        due_reminder = self._first_due_reminder(tool_context=tool_context, now=now)
        if due_reminder is not None:
            trigger = WorkflowTriggerRecord(
                trigger_kind=WorkflowTriggerKind.DUE_REMINDER,
                trigger_key=f"due_reminder:{tool_context.session.session_id}:{due_reminder['reminder_id']}",
                source_session_id=tool_context.session.session_id,
                proactive=True,
                scheduled_for=now,
                note="due_reminder_follow_up",
            )
            proposals.append(
                WorkflowTriggerProposal(
                    workflow_id="reminder_due_follow_up",
                    trigger=trigger,
                    inputs={"reminder_id": due_reminder["reminder_id"]},
                    note="due_reminder_follow_up",
                    suggested_only=context_mode == CompanionContextMode.VENUE_DEMO,
                )
            )
        prompt_type = shift_snapshot.next_scheduled_prompt_type
        prompt_note = shift_snapshot.next_scheduled_prompt_note
        prompt_at = shift_snapshot.next_scheduled_prompt_at
        if prompt_type and prompt_at is not None and prompt_at <= now:
            if prompt_type == "event_start_reminder":
                proposals.append(
                    WorkflowTriggerProposal(
                        workflow_id="event_lookup_and_open_page",
                        trigger=WorkflowTriggerRecord(
                            trigger_kind=WorkflowTriggerKind.EVENT_START_WINDOW,
                            trigger_key=f"event_window:{tool_context.session.session_id}:{prompt_note or prompt_type}",
                            source_session_id=tool_context.session.session_id,
                            proactive=True,
                            scheduled_for=prompt_at,
                            note=prompt_note,
                        ),
                        inputs={"scheduled_prompt_note": prompt_note},
                        note=prompt_note,
                        suggested_only=True,
                    )
                )
            else:
                proposals.append(
                    WorkflowTriggerProposal(
                        workflow_id="morning_briefing",
                        trigger=WorkflowTriggerRecord(
                            trigger_kind=WorkflowTriggerKind.VENUE_SCHEDULED_PROMPT,
                            trigger_key=f"scheduled_prompt:{tool_context.session.session_id}:{prompt_type}:{prompt_note or ''}",
                            source_session_id=tool_context.session.session_id,
                            proactive=True,
                            scheduled_for=prompt_at,
                            note=prompt_note,
                        ),
                        inputs={"scheduled_prompt_type": prompt_type, "scheduled_prompt_note": prompt_note},
                        note=prompt_note,
                        suggested_only=True,
                    )
                )
        return proposals

    def _first_due_reminder(self, *, tool_context, now: datetime) -> dict[str, Any] | None:
        if tool_context.memory_store is None:
            return None
        items = tool_context.memory_store.list_reminders(
            session_id=tool_context.session.session_id,
            user_id=tool_context.session.user_id,
            status=ReminderStatus.OPEN,
            limit=50,
        ).items
        due = next((item for item in items if item.due_at is not None and item.due_at <= now), None)
        if due is None:
            return None
        return {
            "reminder_id": due.reminder_id,
            "reminder_text": due.reminder_text,
            "due_at": due.due_at.isoformat() if due.due_at is not None else None,
        }

    def _morning_briefing_time(self) -> tuple[int, int]:
        raw = (self.settings.blink_workflow_morning_briefing_time or "09:00").strip()
        hour_text, minute_text = (raw.split(":", 1) + ["00"])[:2]
        try:
            return max(0, min(23, int(hour_text))), max(0, min(59, int(minute_text)))
        except ValueError:
            return 9, 0

    def _prepare_restart_review_resume(self, run: WorkflowRunRecord, *, note: str | None = None) -> WorkflowRunRecord:
        step = self._current_step(run)
        if step is None:
            return run
        linked_action_id = step.blocking_action_id or run.blocking_action_id or step.action_id
        execution = self.action_gateway.get_execution(linked_action_id) if linked_action_id is not None else None
        if execution is not None and execution.status in {
            ActionExecutionStatus.EXECUTED,
            ActionExecutionStatus.REUSED,
        }:
            step.status = WorkflowStepStatus.COMPLETED
            step.action_id = execution.action_id
            if execution.action_id not in step.action_ids:
                step.action_ids.append(execution.action_id)
            step.output_payload = dict(execution.output_payload)
            step.summary = execution.detail or execution.operator_summary or execution.status.value
            step.detail = execution.detail
            step.blocking_action_id = None
            step.finished_at = execution.finished_at or utc_now()
            run.blocking_action_id = None
            run.pause_reason = None
            run.failure_class = None
            self._update_run_for_completed_step(run, step=step, output_payload=step.output_payload)
            return self._save_run(run)
        if execution is not None and execution.status == ActionExecutionStatus.PENDING_APPROVAL:
            step.status = WorkflowStepStatus.WAITING_FOR_APPROVAL
            step.blocking_action_id = execution.action_id
            run.status = WorkflowRunStatus.WAITING_FOR_APPROVAL
            run.pause_reason = WorkflowPauseReason.WAITING_FOR_APPROVAL
            run.failure_class = None
            run.blocking_action_id = execution.action_id
            run.detail = execution.detail or "approval_required"
            return self._save_run(run)
        step.status = WorkflowStepStatus.PENDING
        step.detail = note or "runtime_restart_review_resumed"
        step.blocking_action_id = None
        step.finished_at = None
        run.blocking_action_id = None
        run.pause_reason = None
        run.failure_class = None
        run.detail = note or "runtime_restart_review_resumed"
        return self._save_run(run)

    def _timed_out(self, run: WorkflowRunRecord) -> bool:
        if run.started_at is None:
            return False
        return (utc_now() - run.started_at).total_seconds() > float(self.settings.blink_workflow_run_timeout_seconds)

    def _current_step(self, run: WorkflowRunRecord) -> WorkflowStepRecord | None:
        for step in run.steps:
            if step.status not in {WorkflowStepStatus.COMPLETED, WorkflowStepStatus.SKIPPED}:
                return step
        return None

    def _step_by_id(self, run: WorkflowRunRecord, step_id: str | None) -> WorkflowStepRecord | None:
        if step_id is None:
            return None
        return next((item for item in run.steps if item.step_id == step_id), None)

    def _require_definition(self, workflow_id: str) -> WorkflowDefinitionRecord:
        definition = get_workflow_definition(workflow_id)
        if definition is None:
            raise KeyError(f"workflow_not_found:{workflow_id}")
        return definition

    def _require_run(self, workflow_run_id: str) -> WorkflowRunRecord:
        run = self.store.get_run(workflow_run_id)
        if run is None:
            raise KeyError(f"workflow_run_not_found:{workflow_run_id}")
        return run

    def _save_run(self, run: WorkflowRunRecord) -> WorkflowRunRecord:
        saved = self.store.save_run(run)
        self.action_gateway.bundle_store.record_workflow_run(saved)
        return saved

    def _emit_body_feedback(self, state: str, run: WorkflowRunRecord) -> None:
        run.body_feedback_state = state
        self._save_run(run)
        if self.body_feedback_callback is None:
            return
        try:
            self.body_feedback_callback(state, run.model_copy(deep=True))
        except Exception:
            log_event(
                logger,
                logging.WARNING,
                "workflow_body_feedback_failed",
                workflow_run_id=run.workflow_run_id,
                workflow_id=run.workflow_id,
                body_feedback_state=state,
            )


__all__ = ["WorkflowRuntime", "WorkflowTriggerProposal"]
