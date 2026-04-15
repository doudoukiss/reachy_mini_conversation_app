from __future__ import annotations

import base64
import hashlib
import json
import logging
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import BaseModel

from embodied_stack.action_plane.approvals import ApprovalStore
from embodied_stack.action_plane.bundles import ActionBundleStore
from embodied_stack.action_plane.connectors import ConnectorActionError
from embodied_stack.action_plane.execution_store import ExecutionStore
from embodied_stack.action_plane.health import ConnectorHealthStore
from embodied_stack.action_plane.models import (
    ActionInvocationContext,
    ActionInvocationResult,
    ActionPlaneSnapshot,
    ActionPolicyOutcome,
)
from embodied_stack.action_plane.policy import ActionPolicyEngine
from embodied_stack.action_plane.registry import ActionRegistry
from embodied_stack.config import Settings
from embodied_stack.observability import log_event
from embodied_stack.shared.contracts.action import (
    ActionApprovalListResponse,
    ActionApprovalRecord,
    ActionApprovalResolutionRecord,
    ActionApprovalState,
    ActionBundleDetailRecord,
    ActionBundleListResponse,
    BrowserActionPreviewRecord,
    BrowserActionResultRecord,
    BrowserRequestedAction,
    BrowserRuntimeStatusRecord,
    BrowserSnapshotRecord,
    ActionExecutionListResponse,
    ActionExecutionRecord,
    ActionExecutionStatus,
    ActionPlaneStatus,
    ActionPolicyDecision,
    ActionProposalRecord,
    ActionReplayRequestRecord,
    ActionRequestRecord,
    ConnectorCatalogResponse,
)
from embodied_stack.shared.contracts._common import ToolCapabilityState, ToolResultStatus, utc_now

logger = logging.getLogger(__name__)


class ActionPlaneGateway:
    def __init__(
        self,
        *,
        root_dir: str | Path,
        settings: Settings | None = None,
        registry: ActionRegistry | None = None,
        policy: ActionPolicyEngine | None = None,
        approval_store: ApprovalStore | None = None,
        execution_store: ExecutionStore | None = None,
        health_store: ConnectorHealthStore | None = None,
    ) -> None:
        self.root_dir = Path(root_dir)
        self.root_dir.mkdir(parents=True, exist_ok=True)
        self.settings = settings or Settings()
        self.registry = registry or ActionRegistry(settings=self.settings)
        self.policy = policy or ActionPolicyEngine()
        self.approval_store = approval_store or ApprovalStore(self.root_dir)
        self.execution_store = execution_store or ExecutionStore(self.root_dir)
        self.health_store = health_store or ConnectorHealthStore(self.root_dir, registry=self.registry)
        self.bundle_store = ActionBundleStore(self.settings.blink_action_plane_export_dir)

    def routed_tool_names(self) -> set[str]:
        return self.registry.routed_tool_names()

    def is_routed_tool(self, tool_name: str) -> bool:
        return tool_name in self.registry.routed_tool_names()

    def status(self) -> ActionPlaneStatus:
        self.health_store.refresh()
        last_record = self.execution_store.last_record()
        connector_health = self.health_store.list_records()
        executions = self.execution_store.list_records(limit=None)
        latest_failure = next(
            (
                item.action_id
                for item in executions
                if item.status in {
                    ActionExecutionStatus.FAILED,
                    ActionExecutionStatus.REJECTED,
                    ActionExecutionStatus.UNCERTAIN_REVIEW_REQUIRED,
                }
            ),
            None,
        )
        return ActionPlaneStatus(
            enabled=True,
            pending_approval_count=self.approval_store.pending_count(),
            review_required_count=sum(
                1 for item in executions if item.status == ActionExecutionStatus.UNCERTAIN_REVIEW_REQUIRED
            ),
            degraded_connector_count=sum(
                1
                for item in connector_health
                if item.status != "healthy" or not item.supported or not item.configured
            ),
            last_action_id=last_record.action_id if last_record is not None else None,
            last_action_status=last_record.status if last_record is not None else None,
            latest_failure_action_id=latest_failure,
            connector_health=connector_health,
            pending_approvals=self.approval_store.list_pending(),
        )

    def snapshot(self) -> ActionPlaneSnapshot:
        return ActionPlaneSnapshot(
            status=self.status(),
            connector_health=self.health_store.list_records(),
            pending_approvals=self.approval_store.list_pending(),
            execution_log=self.execution_store.list_records(),
        )

    def list_connectors(self) -> ConnectorCatalogResponse:
        self.health_store.refresh()
        return ConnectorCatalogResponse(items=self.registry.list_connectors())

    def list_action_bundles(self, *, limit: int = 100, session_id: str | None = None) -> ActionBundleListResponse:
        return self.bundle_store.list_bundles(limit=limit, session_id=session_id)

    def get_action_bundle(self, bundle_id: str) -> ActionBundleDetailRecord | None:
        return self.bundle_store.get_bundle_detail(bundle_id)

    def browser_status(self, *, session_id: str | None = None) -> BrowserRuntimeStatusRecord:
        self.health_store.refresh()
        connector_runtime = self.registry.get_connector_runtime("browser_runtime")
        if connector_runtime is not None and hasattr(connector_runtime, "status"):
            status = connector_runtime.status(session_id=session_id)
        else:
            status = BrowserRuntimeStatusRecord()
        pending_preview = None
        for approval in self.approval_store.list_pending():
            if approval.connector_id != "browser_runtime":
                continue
            if session_id is not None and approval.request.session_id != session_id:
                continue
            execution = self.execution_store.get_by_action_id(approval.action_id)
            pending_preview = self._browser_preview_from_payload(execution.output_payload if execution is not None else {})
            if pending_preview is not None:
                break
        last_result = None
        latest_snapshot = status.latest_snapshot
        for execution in self.execution_store.list_records(limit=100):
            if execution.connector_id != "browser_runtime":
                continue
            if session_id is not None and execution.session_id != session_id:
                continue
            if last_result is None:
                last_result = self._browser_result_from_payload(execution.output_payload)
            if latest_snapshot is None:
                latest_snapshot = self._browser_snapshot_from_payload(execution.output_payload)
            if last_result is not None and latest_snapshot is not None:
                break
        return status.model_copy(
            update={
                "pending_preview": pending_preview,
                "last_result": last_result,
                "latest_snapshot": latest_snapshot,
                "updated_at": utc_now(),
            }
        )

    def list_pending_approvals(self) -> ActionApprovalListResponse:
        return ActionApprovalListResponse(items=self.approval_store.list_pending())

    def list_execution_history(self, *, limit: int | None = 50) -> ActionExecutionListResponse:
        return ActionExecutionListResponse(items=self.execution_store.list_records(limit=limit))

    def get_execution(self, action_id: str) -> ActionExecutionRecord | None:
        return self.execution_store.get_by_action_id(action_id)

    def get_pending_approval(self, action_id: str) -> ActionApprovalRecord | None:
        return self.approval_store.get_by_action_id(action_id)

    def list_action_replays(self, *, limit: int = 25, session_id: str | None = None) -> list[ActionReplayRecord]:
        records = self.bundle_store.list_replays(limit=limit * 4 if session_id is not None else limit)
        if session_id is None:
            return records[:limit]
        matched: list[ActionReplayRecord] = []
        for item in records:
            bundle = self.bundle_store.get_bundle(item.bundle_id)
            if bundle is None or bundle.session_id != session_id:
                continue
            matched.append(item)
            if len(matched) >= limit:
                break
        return matched

    def reconcile_restart_review(self) -> list[ActionExecutionRecord]:
        updated: list[ActionExecutionRecord] = []
        for item in self.execution_store.list_records(limit=None):
            if item.status != ActionExecutionStatus.EXECUTING:
                continue
            review = item.model_copy(
                update={
                    "status": ActionExecutionStatus.UNCERTAIN_REVIEW_REQUIRED,
                    "error_code": "runtime_restart_review",
                    "error_detail": item.error_detail or "runtime_restarted_before_action_outcome_confirmed",
                    "detail": "runtime_restart_review_required",
                    "operator_summary": (
                        "Blink restarted before this action reached a confirmed terminal outcome."
                    ),
                    "next_step_hint": (
                        "Review this action in the Action Center before replaying it or resuming any blocked workflow."
                    ),
                    "finished_at": utc_now(),
                }
            )
            self.execution_store.upsert(review)
            self.bundle_store.record_execution(review)
            updated.append(review)
        return updated

    def invoke(
        self,
        *,
        tool_name: str,
        requested_tool_name: str,
        input_model: BaseModel,
        handler_context: Any,
        invocation: ActionInvocationContext,
        replay_of_action_id: str | None = None,
        replay_nonce: str | None = None,
    ) -> ActionInvocationResult:
        route = self.registry.route_for_tool(tool_name)
        if route is None:
            raise KeyError(f"tool {tool_name} is not routed through the action plane")
        action_name = self._resolved_action_name(tool_name=tool_name, route_action_name=route.action_name, input_model=input_model)
        connector = self.registry.get_connector(route.connector_id)
        connector_runtime = self.registry.get_connector_runtime(route.connector_id)
        self.health_store.refresh()
        connector_health = self.health_store.get_record(route.connector_id)
        policy = self.policy.evaluate(
            tool_name=tool_name,
            action_name=action_name,
            connector_id=route.connector_id,
            invocation_origin=invocation.invocation_origin,
            connector=connector,
            connector_health=connector_health,
            input_model=input_model,
        )
        request = self._build_request_record(
            tool_name=tool_name,
            requested_tool_name=requested_tool_name,
            action_name=action_name,
            requested_action_name=action_name,
            connector_id=route.connector_id,
            input_model=input_model,
            invocation=invocation,
            policy=policy,
            idempotency_namespace=replay_nonce,
        )
        proposal = ActionProposalRecord(
            action_id=request.action_id,
            tool_name=tool_name,
            action_name=action_name,
            connector_id=route.connector_id,
            risk_class=policy.risk_class,
            policy_decision=policy.policy_decision,
            approval_state=policy.approval_state,
            detail=policy.detail,
            request=request,
        )
        self.bundle_store.record_request(proposal, replay_of_action_id=replay_of_action_id)
        log_event(
            logger,
            logging.INFO,
            "action_plane_policy_decision",
            action_id=request.action_id,
            tool_name=tool_name,
            action_name=action_name,
            connector_id=route.connector_id,
            policy_decision=policy.policy_decision.value,
            approval_state=policy.approval_state.value,
            risk_class=policy.risk_class.value,
            replay_of_action_id=replay_of_action_id,
        )
        existing_execution = self.execution_store.get_by_idempotency_key(request.idempotency_key)
        if existing_execution is not None:
            return self._reuse_existing_execution(
                proposal=proposal,
                execution=existing_execution,
                connector_runtime=connector_runtime,
                handler_context=handler_context,
            )
        return self._execute_proposal(
            proposal=proposal,
            connector_runtime=connector_runtime,
            handler_context=handler_context,
        )

    def approve_action(
        self,
        *,
        action_id: str,
        operator_note: str | None = None,
        handler_context: Any,
    ) -> ActionApprovalResolutionRecord:
        approval = self.approval_store.get_by_action_id(action_id)
        if approval is None:
            raise KeyError(f"pending approval not found for action {action_id}")
        connector_runtime = self.registry.get_connector_runtime(approval.connector_id)
        approved = self.approval_store.approve(action_id, operator_note=operator_note)
        if approved is None:
            raise KeyError(f"unable to approve action {action_id}")
        self.bundle_store.record_approval(approved)
        execution = self._execute_approved_request(
            approval=approved,
            connector_runtime=connector_runtime,
            handler_context=handler_context,
        )
        return ActionApprovalResolutionRecord(
            action_id=approved.action_id,
            tool_name=approved.tool_name,
            action_name=approved.action_name,
            connector_id=approved.connector_id,
            approval_state=approved.approval_state,
            operator_note=approved.operator_note,
            detail=execution.detail or approved.detail,
            approval=approved,
            execution=execution,
        )

    def reject_action(
        self,
        *,
        action_id: str,
        operator_note: str | None = None,
        detail: str | None = None,
        handler_context: Any,
    ) -> ActionApprovalResolutionRecord:
        approval = self.approval_store.get_by_action_id(action_id)
        if approval is None:
            raise KeyError(f"pending approval not found for action {action_id}")
        rejected = self.approval_store.reject(
            action_id,
            operator_note=operator_note,
            detail=detail or "approval_rejected",
        )
        if rejected is None:
            raise KeyError(f"unable to reject action {action_id}")
        self.bundle_store.record_approval(rejected)
        connector_runtime = self.registry.get_connector_runtime(rejected.connector_id)
        preview = self._preview_result(
            connector_runtime=connector_runtime,
            action_name=rejected.action_name,
            request=rejected.request,
            handler_context=handler_context,
            reason=detail or "approval_rejected",
        )
        execution = self.execution_store.upsert(
            ActionExecutionRecord(
                action_id=rejected.action_id,
                tool_name=rejected.tool_name,
                action_name=rejected.action_name,
                connector_id=rejected.connector_id,
                request_hash=rejected.request_hash,
                idempotency_key=rejected.idempotency_key,
                risk_class=rejected.request.risk_class,
                invocation_origin=rejected.request.invocation_origin,
                policy_decision=rejected.policy_decision,
                approval_state=ActionApprovalState.REJECTED,
                status=ActionExecutionStatus.REJECTED,
                session_id=rejected.request.session_id,
                run_id=rejected.request.run_id,
                workflow_run_id=rejected.workflow_run_id,
                workflow_step_id=rejected.workflow_step_id,
                input_payload=rejected.request.input_payload,
                output_payload=preview.output_payload,
                error_code="approval_rejected",
                error_detail=detail or "approval_rejected",
                detail=detail or "approval_rejected",
                operator_summary=self._operator_summary_for(
                    status=ActionExecutionStatus.REJECTED,
                    detail=detail or "approval_rejected",
                ),
                next_step_hint=self._next_step_hint_for(status=ActionExecutionStatus.REJECTED),
                artifacts=preview.artifacts,
                finished_at=utc_now(),
            )
        )
        self.bundle_store.record_execution(execution)
        return ActionApprovalResolutionRecord(
            action_id=rejected.action_id,
            tool_name=rejected.tool_name,
            action_name=rejected.action_name,
            connector_id=rejected.connector_id,
            approval_state=rejected.approval_state,
            operator_note=rejected.operator_note,
            detail=execution.detail,
            approval=rejected,
            execution=execution,
        )

    def replay_action(
        self,
        *,
        replay: ActionReplayRequestRecord,
        tool_name: str,
        requested_tool_name: str,
        input_model: BaseModel,
        handler_context: Any,
        invocation: ActionInvocationContext,
    ) -> ActionInvocationResult:
        previous = self.execution_store.get_by_action_id(replay.action_id)
        if previous is None:
            raise KeyError(f"action not found for replay: {replay.action_id}")
        return self.invoke(
            tool_name=tool_name,
            requested_tool_name=requested_tool_name,
            input_model=input_model,
            handler_context=handler_context,
            invocation=invocation,
            replay_of_action_id=replay.action_id,
            replay_nonce=f"replay:{replay.action_id}:{uuid4().hex[:12]}",
        )

    def _reuse_existing_execution(
        self,
        *,
        proposal: ActionProposalRecord,
        execution: ActionExecutionRecord,
        connector_runtime,
        handler_context: Any,
    ) -> ActionInvocationResult:
        if execution.status in {ActionExecutionStatus.EXECUTED, ActionExecutionStatus.REUSED}:
            reused = execution.model_copy(
                update={
                    "status": ActionExecutionStatus.REUSED,
                    "reused_result": True,
                    "operator_summary": self._operator_summary_for(status=ActionExecutionStatus.REUSED),
                    "next_step_hint": self._next_step_hint_for(status=ActionExecutionStatus.REUSED),
                    "finished_at": utc_now(),
                }
            )
            self.execution_store.upsert(reused)
            self.bundle_store.record_execution(reused)
            log_event(
                logger,
                logging.INFO,
                "action_plane_execution_reused",
                action_id=reused.action_id,
                tool_name=reused.tool_name,
                action_name=reused.action_name,
                connector_id=reused.connector_id,
            )
            return ActionInvocationResult(
                output_model=reused.output_payload,
                proposal=proposal,
                execution=reused,
                success_override=True,
                summary_override="reused_result",
            )
        approval = self.approval_store.get_by_idempotency_key(execution.idempotency_key)
        preview = self._preview_result(
            connector_runtime=connector_runtime,
            action_name=proposal.action_name,
            request=proposal.request,
            handler_context=handler_context,
            reason=execution.detail or execution.error_code or execution.status.value,
        )
        if execution.status == ActionExecutionStatus.PENDING_APPROVAL:
            return ActionInvocationResult(
                output_model=execution.output_payload or preview.output_payload,
                proposal=proposal,
                execution=execution,
                approval=approval,
                success_override=False,
                result_status_override=ToolResultStatus.BLOCKED,
                capability_state_override=ToolCapabilityState.BLOCKED,
                summary_override="approval_required",
            )
        if execution.status in {
            ActionExecutionStatus.EXECUTING,
            ActionExecutionStatus.UNCERTAIN_REVIEW_REQUIRED,
        }:
            return ActionInvocationResult(
                output_model=execution.output_payload or preview.output_payload,
                proposal=proposal,
                execution=execution,
                approval=approval,
                success_override=False,
                result_status_override=ToolResultStatus.BLOCKED,
                capability_state_override=ToolCapabilityState.BLOCKED,
                summary_override=execution.detail or execution.status.value,
            )
        if execution.status == ActionExecutionStatus.PREVIEW_ONLY:
            return ActionInvocationResult(
                output_model=execution.output_payload or preview.output_payload,
                proposal=proposal,
                execution=execution,
                success_override=False,
                result_status_override=ToolResultStatus.DEGRADED,
                capability_state_override=ToolCapabilityState.FALLBACK_ACTIVE,
                summary_override=execution.detail or "preview_only",
            )
        return ActionInvocationResult(
            output_model=execution.output_payload or preview.output_payload,
            proposal=proposal,
            execution=execution,
            approval=approval,
            success_override=False,
            result_status_override=ToolResultStatus.ERROR,
            capability_state_override=ToolCapabilityState.DEGRADED,
            summary_override=execution.detail or execution.status.value,
        )

    def _execute_proposal(
        self,
        *,
        proposal: ActionProposalRecord,
        connector_runtime,
        handler_context: Any,
    ) -> ActionInvocationResult:
        request = proposal.request
        policy = proposal.policy_decision
        approval_state = proposal.approval_state
        if policy == ActionPolicyDecision.REQUIRE_APPROVAL:
            preview = self._preview_result(
                connector_runtime=connector_runtime,
                action_name=proposal.action_name,
                request=request,
                handler_context=handler_context,
                reason="approval_required",
            )
            approval = self.approval_store.upsert(
                ActionApprovalRecord(
                    action_id=request.action_id,
                    tool_name=request.tool_name,
                    action_name=request.action_name,
                    connector_id=request.connector_id,
                    request_hash=request.request_hash,
                    idempotency_key=request.idempotency_key,
                    policy_decision=policy,
                    approval_state=approval_state,
                    detail=proposal.detail,
                    workflow_run_id=request.workflow_run_id,
                    workflow_step_id=request.workflow_step_id,
                    request=request,
                )
            )
            self.bundle_store.record_approval(approval)
            execution = self.execution_store.upsert(
                ActionExecutionRecord(
                    action_id=request.action_id,
                    tool_name=request.tool_name,
                    action_name=request.action_name,
                    connector_id=request.connector_id,
                    request_hash=request.request_hash,
                    idempotency_key=request.idempotency_key,
                    risk_class=proposal.risk_class,
                    invocation_origin=request.invocation_origin,
                    policy_decision=policy,
                    approval_state=approval_state,
                    status=ActionExecutionStatus.PENDING_APPROVAL,
                    session_id=request.session_id,
                    run_id=request.run_id,
                    workflow_run_id=request.workflow_run_id,
                    workflow_step_id=request.workflow_step_id,
                    input_payload=request.input_payload,
                    output_payload=preview.output_payload,
                    error_code="approval_required",
                    error_detail=proposal.detail,
                    detail="approval_required",
                    operator_summary=self._operator_summary_for(status=ActionExecutionStatus.PENDING_APPROVAL),
                    next_step_hint=self._next_step_hint_for(status=ActionExecutionStatus.PENDING_APPROVAL),
                    artifacts=preview.artifacts,
                    finished_at=utc_now(),
                )
            )
            self.bundle_store.record_execution(execution)
            log_event(
                logger,
                logging.INFO,
                "action_plane_approval_pending",
                action_id=request.action_id,
                tool_name=request.tool_name,
                action_name=request.action_name,
                connector_id=request.connector_id,
            )
            return ActionInvocationResult(
                output_model=preview.output_payload,
                proposal=proposal,
                execution=execution,
                approval=approval,
                success_override=False,
                result_status_override=ToolResultStatus.BLOCKED,
                capability_state_override=ToolCapabilityState.BLOCKED,
                summary_override="approval_required",
            )
        if policy == ActionPolicyDecision.PREVIEW_ONLY:
            preview = self._preview_result(
                connector_runtime=connector_runtime,
                action_name=proposal.action_name,
                request=request,
                handler_context=handler_context,
                reason="preview_only",
            )
            execution = self.execution_store.upsert(
                ActionExecutionRecord(
                    action_id=request.action_id,
                    tool_name=request.tool_name,
                    action_name=request.action_name,
                    connector_id=request.connector_id,
                    request_hash=request.request_hash,
                    idempotency_key=request.idempotency_key,
                    risk_class=proposal.risk_class,
                    invocation_origin=request.invocation_origin,
                    policy_decision=policy,
                    approval_state=approval_state,
                    status=ActionExecutionStatus.PREVIEW_ONLY,
                    session_id=request.session_id,
                    run_id=request.run_id,
                    workflow_run_id=request.workflow_run_id,
                    workflow_step_id=request.workflow_step_id,
                    input_payload=request.input_payload,
                    output_payload=preview.output_payload,
                    detail="preview_only",
                    operator_summary=self._operator_summary_for(status=ActionExecutionStatus.PREVIEW_ONLY),
                    next_step_hint=self._next_step_hint_for(status=ActionExecutionStatus.PREVIEW_ONLY),
                    artifacts=preview.artifacts,
                    finished_at=utc_now(),
                )
            )
            self.bundle_store.record_execution(execution)
            return ActionInvocationResult(
                output_model=preview.output_payload,
                proposal=proposal,
                execution=execution,
                success_override=False,
                result_status_override=ToolResultStatus.DEGRADED,
                capability_state_override=ToolCapabilityState.FALLBACK_ACTIVE,
                summary_override="preview_only",
            )
        if policy == ActionPolicyDecision.REJECT:
            preview = self._preview_result(
                connector_runtime=connector_runtime,
                action_name=proposal.action_name,
                request=request,
                handler_context=handler_context,
                reason=proposal.detail or "rejected",
            )
            execution = self.execution_store.upsert(
                ActionExecutionRecord(
                    action_id=request.action_id,
                    tool_name=request.tool_name,
                    action_name=request.action_name,
                    connector_id=request.connector_id,
                    request_hash=request.request_hash,
                    idempotency_key=request.idempotency_key,
                    risk_class=proposal.risk_class,
                    invocation_origin=request.invocation_origin,
                    policy_decision=policy,
                    approval_state=approval_state,
                    status=ActionExecutionStatus.REJECTED,
                    session_id=request.session_id,
                    run_id=request.run_id,
                    workflow_run_id=request.workflow_run_id,
                    workflow_step_id=request.workflow_step_id,
                    input_payload=request.input_payload,
                    output_payload=preview.output_payload,
                    error_code=proposal.detail,
                    error_detail=proposal.detail,
                    detail=proposal.detail,
                    operator_summary=self._operator_summary_for(
                        status=ActionExecutionStatus.REJECTED,
                        detail=proposal.detail,
                    ),
                    next_step_hint=self._next_step_hint_for(status=ActionExecutionStatus.REJECTED),
                    artifacts=preview.artifacts,
                    finished_at=utc_now(),
                )
            )
            self.bundle_store.record_execution(execution)
            return ActionInvocationResult(
                output_model=preview.output_payload,
                proposal=proposal,
                execution=execution,
                success_override=False,
                summary_override=proposal.detail or "rejected",
            )
        return self._execute_request(
            request=request,
            risk_class=proposal.risk_class,
            policy_decision=policy,
            approval_state=approval_state,
            connector_runtime=connector_runtime,
            handler_context=handler_context,
        )

    def _execute_approved_request(
        self,
        *,
        approval: ActionApprovalRecord,
        connector_runtime,
        handler_context: Any,
    ) -> ActionExecutionRecord:
        request = approval.request.model_copy(update={"risk_class": approval.request.risk_class})
        return self._execute_request_record(
            request=request,
            risk_class=request.risk_class,
            policy_decision=approval.policy_decision,
            approval_state=ActionApprovalState.APPROVED,
            connector_runtime=connector_runtime,
            handler_context=handler_context,
        )

    def _execute_request(
        self,
        *,
        request: ActionRequestRecord,
        risk_class,
        policy_decision: ActionPolicyDecision,
        approval_state: ActionApprovalState,
        connector_runtime,
        handler_context: Any,
    ) -> ActionInvocationResult:
        execution = self._execute_request_record(
            request=request,
            risk_class=risk_class,
            policy_decision=policy_decision,
            approval_state=approval_state,
            connector_runtime=connector_runtime,
            handler_context=handler_context,
        )
        proposal = ActionProposalRecord(
            action_id=request.action_id,
            tool_name=request.tool_name,
            action_name=request.action_name,
            connector_id=request.connector_id,
            risk_class=risk_class,
            policy_decision=policy_decision,
            approval_state=approval_state,
            detail=execution.detail,
            request=request,
        )
        if execution.status == ActionExecutionStatus.EXECUTED:
            return ActionInvocationResult(output_model=execution.output_payload, proposal=proposal, execution=execution)
        return ActionInvocationResult(
            output_model=execution.output_payload,
            proposal=proposal,
            execution=execution,
            success_override=False,
            result_status_override=ToolResultStatus.ERROR,
            capability_state_override=ToolCapabilityState.DEGRADED,
            summary_override=execution.detail or execution.error_code or execution.status.value,
        )

    def _execute_request_record(
        self,
        *,
        request: ActionRequestRecord,
        risk_class,
        policy_decision: ActionPolicyDecision,
        approval_state: ActionApprovalState,
        connector_runtime,
        handler_context: Any,
    ) -> ActionExecutionRecord:
        started_at = utc_now()
        if connector_runtime is None:
            preview = self._preview_result(
                connector_runtime=None,
                action_name=request.action_name,
                request=request,
                handler_context=handler_context,
                reason="connector_missing",
            )
            execution = self.execution_store.upsert(
                ActionExecutionRecord(
                    action_id=request.action_id,
                    tool_name=request.tool_name,
                    action_name=request.action_name,
                    connector_id=request.connector_id,
                    request_hash=request.request_hash,
                    idempotency_key=request.idempotency_key,
                    risk_class=risk_class,
                    invocation_origin=request.invocation_origin,
                    policy_decision=policy_decision,
                    approval_state=approval_state,
                    status=ActionExecutionStatus.FAILED,
                    session_id=request.session_id,
                    run_id=request.run_id,
                    workflow_run_id=request.workflow_run_id,
                    workflow_step_id=request.workflow_step_id,
                    input_payload=request.input_payload,
                    output_payload=preview.output_payload,
                    error_code="connector_missing",
                    error_detail="connector_missing",
                    detail="connector_missing",
                    operator_summary=self._operator_summary_for(
                        status=ActionExecutionStatus.FAILED,
                        detail="connector_missing",
                    ),
                    next_step_hint=self._next_step_hint_for(status=ActionExecutionStatus.FAILED),
                    artifacts=preview.artifacts,
                    started_at=started_at,
                    finished_at=utc_now(),
                )
            )
            self.bundle_store.record_execution(execution)
            return execution
        executing = self.execution_store.upsert(
            ActionExecutionRecord(
                action_id=request.action_id,
                tool_name=request.tool_name,
                action_name=request.action_name,
                connector_id=request.connector_id,
                request_hash=request.request_hash,
                idempotency_key=request.idempotency_key,
                risk_class=risk_class,
                invocation_origin=request.invocation_origin,
                policy_decision=policy_decision,
                approval_state=approval_state,
                status=ActionExecutionStatus.EXECUTING,
                session_id=request.session_id,
                run_id=request.run_id,
                workflow_run_id=request.workflow_run_id,
                workflow_step_id=request.workflow_step_id,
                input_payload=request.input_payload,
                output_payload={},
                detail="executing",
                operator_summary=self._operator_summary_for(status=ActionExecutionStatus.EXECUTING),
                next_step_hint=self._next_step_hint_for(status=ActionExecutionStatus.EXECUTING),
                started_at=started_at,
            )
        )
        self.bundle_store.record_execution(executing)
        try:
            result = connector_runtime.execute(
                action_name=request.action_name,
                request=request,
                runtime_context=handler_context,
            )
            execution = self.execution_store.upsert(
                ActionExecutionRecord(
                    action_id=request.action_id,
                    tool_name=request.tool_name,
                    action_name=request.action_name,
                    connector_id=request.connector_id,
                    request_hash=request.request_hash,
                    idempotency_key=request.idempotency_key,
                    risk_class=risk_class,
                    invocation_origin=request.invocation_origin,
                    policy_decision=policy_decision,
                    approval_state=approval_state,
                    status=ActionExecutionStatus.EXECUTED,
                    session_id=request.session_id,
                    run_id=request.run_id,
                    workflow_run_id=request.workflow_run_id,
                    workflow_step_id=request.workflow_step_id,
                    input_payload=request.input_payload,
                    output_payload=result.output_payload,
                    detail=result.detail or result.summary or "executed",
                    operator_summary=self._operator_summary_for(
                        status=ActionExecutionStatus.EXECUTED,
                        detail=result.detail or result.summary or "executed",
                    ),
                    next_step_hint=self._next_step_hint_for(status=ActionExecutionStatus.EXECUTED),
                    artifacts=result.artifacts,
                    started_at=started_at,
                    finished_at=utc_now(),
                )
            )
            self.bundle_store.record_execution(execution)
            log_event(
                logger,
                logging.INFO,
                "action_plane_execution_recorded",
                action_id=request.action_id,
                tool_name=request.tool_name,
                action_name=request.action_name,
                connector_id=request.connector_id,
                status=execution.status.value,
            )
            return execution
        except ConnectorActionError as exc:
            preview = self._preview_result(
                connector_runtime=connector_runtime,
                action_name=request.action_name,
                request=request,
                handler_context=handler_context,
                reason=exc.detail,
            )
            execution = self.execution_store.upsert(
                ActionExecutionRecord(
                    action_id=request.action_id,
                    tool_name=request.tool_name,
                    action_name=request.action_name,
                    connector_id=request.connector_id,
                    request_hash=request.request_hash,
                    idempotency_key=request.idempotency_key,
                    risk_class=risk_class,
                    invocation_origin=request.invocation_origin,
                    policy_decision=policy_decision,
                    approval_state=approval_state,
                    status=ActionExecutionStatus.FAILED,
                    session_id=request.session_id,
                    run_id=request.run_id,
                    workflow_run_id=request.workflow_run_id,
                    workflow_step_id=request.workflow_step_id,
                    input_payload=request.input_payload,
                    output_payload=preview.output_payload,
                    error_code=exc.code,
                    error_detail=exc.detail,
                    detail=exc.detail,
                    operator_summary=self._operator_summary_for(
                        status=ActionExecutionStatus.FAILED,
                        detail=exc.detail,
                    ),
                    next_step_hint=self._next_step_hint_for(status=ActionExecutionStatus.FAILED),
                    artifacts=preview.artifacts,
                    started_at=started_at,
                    finished_at=utc_now(),
                )
            )
            self.bundle_store.record_execution(execution)
            log_event(
                logger,
                logging.WARNING,
                "action_plane_execution_failed",
                action_id=request.action_id,
                tool_name=request.tool_name,
                action_name=request.action_name,
                connector_id=request.connector_id,
                error_code=exc.code,
            )
            return execution
        except Exception as exc:
            preview = self._preview_result(
                connector_runtime=connector_runtime,
                action_name=request.action_name,
                request=request,
                handler_context=handler_context,
                reason="execution_failed",
            )
            execution = self.execution_store.upsert(
                ActionExecutionRecord(
                    action_id=request.action_id,
                    tool_name=request.tool_name,
                    action_name=request.action_name,
                    connector_id=request.connector_id,
                    request_hash=request.request_hash,
                    idempotency_key=request.idempotency_key,
                    risk_class=risk_class,
                    invocation_origin=request.invocation_origin,
                    policy_decision=policy_decision,
                    approval_state=approval_state,
                    status=ActionExecutionStatus.FAILED,
                    session_id=request.session_id,
                    run_id=request.run_id,
                    workflow_run_id=request.workflow_run_id,
                    workflow_step_id=request.workflow_step_id,
                    input_payload=request.input_payload,
                    output_payload=preview.output_payload,
                    error_code=exc.__class__.__name__,
                    error_detail=str(exc),
                    detail="execution_failed",
                    operator_summary=self._operator_summary_for(
                        status=ActionExecutionStatus.FAILED,
                        detail="execution_failed",
                    ),
                    next_step_hint=self._next_step_hint_for(status=ActionExecutionStatus.FAILED),
                    artifacts=preview.artifacts,
                    started_at=started_at,
                    finished_at=utc_now(),
                )
            )
            self.bundle_store.record_execution(execution)
            log_event(
                logger,
                logging.ERROR,
                "action_plane_execution_failed",
                action_id=request.action_id,
                tool_name=request.tool_name,
                action_name=request.action_name,
                connector_id=request.connector_id,
                error_code=exc.__class__.__name__,
            )
            return execution

    def _preview_result(
        self,
        *,
        connector_runtime,
        action_name: str,
        request: ActionRequestRecord,
        handler_context: Any,
        reason: str,
    ):
        if connector_runtime is None:
            from embodied_stack.action_plane.connectors import ConnectorPreviewResult

            return ConnectorPreviewResult(summary=reason, detail=reason, output_payload={})
        try:
            return connector_runtime.preview(
                action_name=action_name,
                request=request,
                runtime_context=handler_context,
                reason=reason,
            )
        except Exception:
            from embodied_stack.action_plane.connectors import ConnectorPreviewResult

            return ConnectorPreviewResult(summary=reason, detail=reason, output_payload={})

    def _operator_summary_for(
        self,
        *,
        status: ActionExecutionStatus,
        detail: str | None = None,
    ) -> str | None:
        if status == ActionExecutionStatus.PENDING_APPROVAL:
            return "Approval is required before this action can execute."
        if status == ActionExecutionStatus.PREVIEW_ONLY:
            return "The action was previewed but did not execute."
        if status == ActionExecutionStatus.REJECTED:
            return "The action was rejected and no side effect was performed."
        if status == ActionExecutionStatus.FAILED:
            return "The action failed before a confirmed successful outcome was recorded."
        if status == ActionExecutionStatus.EXECUTING:
            return "The action has started and is waiting for a confirmed terminal outcome."
        if status == ActionExecutionStatus.UNCERTAIN_REVIEW_REQUIRED:
            return "Blink restarted before the action outcome was confirmed."
        if status == ActionExecutionStatus.REUSED:
            return "A prior successful result was reused instead of executing the action again."
        if status == ActionExecutionStatus.EXECUTED:
            return detail or "The action executed successfully."
        return detail

    def _next_step_hint_for(self, *, status: ActionExecutionStatus) -> str | None:
        if status == ActionExecutionStatus.PENDING_APPROVAL:
            return "Continue in the Action Center to approve or reject this action."
        if status == ActionExecutionStatus.PREVIEW_ONLY:
            return "Review the preview and rerun it from the operator surface if you still want to proceed."
        if status == ActionExecutionStatus.REJECTED:
            return "Adjust the request or explicitly replay it if you want to try again."
        if status == ActionExecutionStatus.FAILED:
            return "Inspect the failure details and replay it explicitly only if the side effect is still safe."
        if status == ActionExecutionStatus.EXECUTING:
            return "If Blink restarts before this finishes, review it in the Action Center before retrying."
        if status == ActionExecutionStatus.UNCERTAIN_REVIEW_REQUIRED:
            return "Review this action in the Action Center before replaying it or resuming any blocked workflow."
        if status in {ActionExecutionStatus.EXECUTED, ActionExecutionStatus.REUSED}:
            return "Inspect the linked history or bundle in the Action Center if you need details."
        return None

    def _build_request_record(
        self,
        *,
        tool_name: str,
        requested_tool_name: str,
        action_name: str,
        requested_action_name: str,
        connector_id: str,
        input_model: BaseModel,
        invocation: ActionInvocationContext,
        policy: ActionPolicyOutcome,
        idempotency_namespace: str | None = None,
    ) -> ActionRequestRecord:
        input_payload = input_model.model_dump(mode="json")
        request_hash = hashlib.sha256(self._canonical_json(input_payload).encode("utf-8")).hexdigest()
        run_component = invocation.run_id or f"session:{invocation.session_id or 'unknown'}"
        namespace = f":{idempotency_namespace}" if idempotency_namespace else ""
        idempotency_key = hashlib.sha256(
            f"{run_component}:{tool_name}:{request_hash}{namespace}".encode("utf-8")
        ).hexdigest()
        action_id = f"act_{idempotency_key[:16]}"
        return ActionRequestRecord(
            action_id=action_id,
            request_hash=request_hash,
            idempotency_key=idempotency_key,
            tool_name=tool_name,
            requested_tool_name=requested_tool_name,
            action_name=action_name,
            requested_action_name=requested_action_name,
            connector_id=connector_id,
            risk_class=policy.risk_class,
            invocation_origin=invocation.invocation_origin,
            session_id=invocation.session_id,
            run_id=invocation.run_id,
            workflow_run_id=invocation.workflow_run_id,
            workflow_step_id=invocation.workflow_step_id,
            context_mode=invocation.context_mode,
            body_mode=invocation.body_mode,
            input_payload=input_payload,
        )

    def _canonical_json(self, payload: dict[str, Any]) -> str:
        return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)

    def _resolved_action_name(self, *, tool_name: str, route_action_name: str, input_model: BaseModel) -> str:
        if tool_name != "browser_task":
            return route_action_name
        requested = getattr(input_model, "requested_action", None)
        if isinstance(requested, BrowserRequestedAction):
            return requested.value
        if isinstance(requested, str) and requested.strip():
            try:
                return BrowserRequestedAction(requested.strip()).value
            except ValueError:
                return route_action_name
        target_url = getattr(input_model, "target_url", None)
        query = getattr(input_model, "query", None)
        if target_url or (isinstance(query, str) and query.strip().startswith(("http://", "https://"))):
            return BrowserRequestedAction.OPEN_URL.value
        return BrowserRequestedAction.CAPTURE_SNAPSHOT.value

    def _browser_snapshot_from_payload(self, payload: dict[str, Any]) -> BrowserSnapshotRecord | None:
        snapshot = payload.get("snapshot") if isinstance(payload, dict) else None
        if not isinstance(snapshot, dict):
            return None
        try:
            record = BrowserSnapshotRecord.model_validate(snapshot)
        except Exception:
            return None
        return record.model_copy(update={"screenshot_data_url": self._screenshot_data_url(record.screenshot_path)})

    def _browser_preview_from_payload(self, payload: dict[str, Any]) -> BrowserActionPreviewRecord | None:
        preview = payload.get("preview") if isinstance(payload, dict) else None
        if not isinstance(preview, dict):
            return None
        try:
            record = BrowserActionPreviewRecord.model_validate(preview)
        except Exception:
            return None
        return record.model_copy(update={"screenshot_data_url": self._screenshot_data_url(record.screenshot_path)})

    def _browser_result_from_payload(self, payload: dict[str, Any]) -> BrowserActionResultRecord | None:
        result = payload.get("result") if isinstance(payload, dict) else None
        if not isinstance(result, dict):
            return None
        try:
            record = BrowserActionResultRecord.model_validate(result)
        except Exception:
            return None
        return record.model_copy(update={"screenshot_data_url": self._screenshot_data_url(record.screenshot_path)})

    def _screenshot_data_url(self, path: str | None) -> str | None:
        if not path:
            return None
        candidate = Path(path)
        if not candidate.exists():
            return None
        return f"data:image/png;base64,{base64.b64encode(candidate.read_bytes()).decode('ascii')}"


__all__ = ["ActionPlaneGateway"]
