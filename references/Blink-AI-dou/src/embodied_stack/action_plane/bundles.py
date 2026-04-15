from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from typing import Any

from embodied_stack.persistence import load_json_model_or_quarantine, load_json_value_or_quarantine, write_json_atomic
from embodied_stack.shared.contracts.action import (
    ActionApprovalEventRecord,
    ActionApprovalRecord,
    ActionApprovalState,
    ActionBundleDetailRecord,
    ActionBundleListResponse,
    ActionBundleManifestV1,
    ActionBundleRootKind,
    ActionConnectorCallRecord,
    ActionExecutionRecord,
    ActionExecutionStatus,
    ActionPolicyDecision,
    ActionProposalRecord,
    ActionReplayRecord,
    ActionRetryRecord,
    ActionInvocationOrigin,
    WorkflowRunRecord,
)
from embodied_stack.shared.contracts.episode import TeacherAnnotationRecord
from embodied_stack.shared.contracts._common import utc_now


class ActionBundleStore:
    MANIFEST_FILE = "manifest.json"
    APPROVAL_EVENTS_FILE = "approval_events.json"
    EXECUTION_TRACE_FILE = "execution_trace.json"
    CONNECTOR_CALLS_FILE = "connector_calls.json"
    FEEDBACK_FILE = "feedback.json"
    TEACHER_ANNOTATIONS_FILE = "teacher_annotations.json"
    RESULT_FILE = "result.json"
    WORKFLOW_RUN_FILE = "workflow_run.json"

    def __init__(self, export_root: str | Path) -> None:
        self.export_root = Path(export_root)
        self.bundles_dir = self.export_root / "action_bundles"
        self.replays_dir = self.export_root / "action_replays"
        self.bundles_dir.mkdir(parents=True, exist_ok=True)
        self.replays_dir.mkdir(parents=True, exist_ok=True)

    def list_bundles(self, *, limit: int = 100, session_id: str | None = None) -> ActionBundleListResponse:
        items: list[ActionBundleManifestV1] = []
        for path in sorted(self.bundles_dir.glob(f"*/{self.MANIFEST_FILE}")):
            manifest = load_json_model_or_quarantine(path, ActionBundleManifestV1, quarantine_invalid=True)
            if manifest is None:
                continue
            if session_id is not None and manifest.session_id != session_id:
                continue
            items.append(manifest)
        items.sort(key=lambda item: item.updated_at, reverse=True)
        return ActionBundleListResponse(items=items[:limit])

    def get_bundle(self, bundle_id: str) -> ActionBundleManifestV1 | None:
        path = self._bundle_dir(bundle_id) / self.MANIFEST_FILE
        return load_json_model_or_quarantine(path, ActionBundleManifestV1, quarantine_invalid=True)

    def get_bundle_detail(self, bundle_id: str) -> ActionBundleDetailRecord | None:
        manifest = self.get_bundle(bundle_id)
        if manifest is None:
            return None
        feedback = load_json_value_or_quarantine(self._bundle_dir(bundle_id) / self.FEEDBACK_FILE) or {}
        result = load_json_value_or_quarantine(self._bundle_dir(bundle_id) / self.RESULT_FILE) or {}
        return ActionBundleDetailRecord(
            manifest=manifest,
            approval_events=self._load_approval_events(bundle_id),
            execution_trace=self._load_execution_trace(bundle_id),
            connector_calls=self._load_connector_calls(bundle_id),
            retries=self._load_retry_records(bundle_id),
            replays=self.list_replays(bundle_id=bundle_id, limit=100),
            teacher_annotations=[
                item.model_dump(mode="json") for item in self._load_teacher_annotations(bundle_id)
            ],
            feedback=feedback if isinstance(feedback, dict) else {},
            result=result if isinstance(result, dict) else {},
        )

    def save_replay(self, record: ActionReplayRecord, *, payloads: dict[str, Any]) -> ActionReplayRecord:
        replay_dir = self.replays_dir / record.replay_id
        replay_dir.mkdir(parents=True, exist_ok=True)
        record.artifact_dir = str(replay_dir)
        record.artifact_files = {
            "manifest": str(replay_dir / "manifest.json"),
            "source_bundle": str(replay_dir / "source_bundle.json"),
            "connector_calls": str(replay_dir / "connector_calls.json"),
            "results": str(replay_dir / "results.json"),
        }
        for name, payload in payloads.items():
            target = Path(record.artifact_files[name])
            write_json_atomic(target, payload)
        write_json_atomic(Path(record.artifact_files["manifest"]), record)
        return record.model_copy(deep=True)

    def get_replay(self, replay_id: str) -> ActionReplayRecord | None:
        path = self.replays_dir / replay_id / "manifest.json"
        return load_json_model_or_quarantine(path, ActionReplayRecord, quarantine_invalid=True)

    def list_replays(self, *, bundle_id: str | None = None, limit: int = 100) -> list[ActionReplayRecord]:
        items: list[ActionReplayRecord] = []
        for path in sorted(self.replays_dir.glob("*/manifest.json")):
            record = load_json_model_or_quarantine(path, ActionReplayRecord, quarantine_invalid=True)
            if record is None:
                continue
            if bundle_id is not None and record.bundle_id != bundle_id:
                continue
            items.append(record)
        items.sort(key=lambda item: item.started_at, reverse=True)
        return items[:limit]

    def record_request(
        self,
        proposal: ActionProposalRecord,
        *,
        replay_of_action_id: str | None = None,
    ) -> ActionBundleManifestV1:
        request = proposal.request
        manifest = self._load_or_create_manifest_for_request(proposal)
        manifest.requested_tool_name = manifest.requested_tool_name or request.tool_name
        manifest.requested_action_name = manifest.requested_action_name or request.action_name
        manifest.session_id = request.session_id or manifest.session_id
        manifest.run_id = request.run_id or manifest.run_id
        manifest.workflow_run_id = request.workflow_run_id or manifest.workflow_run_id
        if request.workflow_step_id and request.workflow_step_id not in manifest.workflow_step_ids:
            manifest.workflow_step_ids.append(request.workflow_step_id)
        manifest.invocation_origin = request.invocation_origin
        manifest.proactive = request.invocation_origin == ActionInvocationOrigin.PROACTIVE_RUNTIME
        manifest.policy_decision = proposal.policy_decision
        manifest.approval_state = proposal.approval_state
        manifest.updated_at = utc_now()
        if replay_of_action_id:
            retries = self._load_retry_records(manifest.bundle_id)
            retries.append(
                ActionRetryRecord(
                    action_id=request.action_id,
                    source_action_id=replay_of_action_id,
                    workflow_run_id=request.workflow_run_id,
                    workflow_step_id=request.workflow_step_id,
                    reason="replay_requested",
                )
            )
            self._write_json(self._bundle_dir(manifest.bundle_id) / "retries.json", retries)
            manifest.retry_count = len(retries)
        self._save_manifest(manifest)
        return manifest

    def record_approval(self, approval: ActionApprovalRecord) -> ActionBundleManifestV1:
        manifest = self._load_or_create_manifest_for_approval(approval)
        event = ActionApprovalEventRecord(
            action_id=approval.action_id,
            tool_name=approval.tool_name,
            action_name=approval.action_name or approval.tool_name,
            connector_id=approval.connector_id,
            approval_state=approval.approval_state,
            detail=approval.detail,
            operator_note=approval.operator_note,
            workflow_run_id=approval.workflow_run_id,
            workflow_step_id=approval.workflow_step_id,
            occurred_at=approval.updated_at,
        )
        events = self._load_approval_events(manifest.bundle_id)
        events.append(event)
        self._write_json(self._bundle_dir(manifest.bundle_id) / self.APPROVAL_EVENTS_FILE, events)
        manifest.requested_tool_name = manifest.requested_tool_name or approval.tool_name
        manifest.requested_action_name = manifest.requested_action_name or approval.action_name
        manifest.session_id = approval.request.session_id or manifest.session_id
        manifest.run_id = approval.request.run_id or manifest.run_id
        manifest.workflow_run_id = approval.workflow_run_id or manifest.workflow_run_id
        if approval.workflow_step_id and approval.workflow_step_id not in manifest.workflow_step_ids:
            manifest.workflow_step_ids.append(approval.workflow_step_id)
        manifest.invocation_origin = approval.request.invocation_origin
        manifest.proactive = approval.request.invocation_origin == ActionInvocationOrigin.PROACTIVE_RUNTIME
        manifest.approval_state = approval.approval_state
        manifest.approval_event_count = len(events)
        manifest.operator_feedback_count = sum(1 for item in events if item.operator_note)
        manifest.updated_at = utc_now()
        self._save_manifest(manifest)
        return manifest

    def record_execution(self, execution: ActionExecutionRecord) -> ActionBundleManifestV1:
        manifest = self._load_or_create_manifest_for_execution(execution)
        traces = self._load_execution_trace(manifest.bundle_id)
        replaced = False
        for index, item in enumerate(traces):
            if item.action_id == execution.action_id:
                traces[index] = execution
                replaced = True
                break
        if not replaced:
            traces.append(execution)
        self._write_json(self._bundle_dir(manifest.bundle_id) / self.EXECUTION_TRACE_FILE, traces)

        connector_call = ActionConnectorCallRecord(
            action_id=execution.action_id,
            tool_name=execution.tool_name,
            action_name=execution.action_name or execution.tool_name,
            connector_id=execution.connector_id,
            workflow_run_id=execution.workflow_run_id,
            workflow_step_id=execution.workflow_step_id,
            risk_class=execution.risk_class,
            approval_state=execution.approval_state,
            status=execution.status,
            input_payload=dict(execution.input_payload),
            output_payload=dict(execution.output_payload),
            error_code=execution.error_code,
            error_detail=execution.error_detail,
            artifacts=[item.model_copy(deep=True) for item in execution.artifacts],
            created_at=execution.created_at,
            started_at=execution.started_at,
            finished_at=execution.finished_at,
        )
        calls = self._load_connector_calls(manifest.bundle_id)
        replaced = False
        for index, item in enumerate(calls):
            if item.action_id == connector_call.action_id:
                calls[index] = connector_call
                replaced = True
                break
        if not replaced:
            calls.append(connector_call)
        self._write_json(self._bundle_dir(manifest.bundle_id) / self.CONNECTOR_CALLS_FILE, calls)

        manifest.requested_tool_name = manifest.requested_tool_name or execution.tool_name
        manifest.requested_action_name = manifest.requested_action_name or execution.action_name
        manifest.session_id = execution.session_id or manifest.session_id
        manifest.run_id = execution.run_id or manifest.run_id
        manifest.workflow_run_id = execution.workflow_run_id or manifest.workflow_run_id
        if execution.workflow_step_id and execution.workflow_step_id not in manifest.workflow_step_ids:
            manifest.workflow_step_ids.append(execution.workflow_step_id)
        manifest.invocation_origin = execution.invocation_origin
        manifest.proactive = execution.invocation_origin == ActionInvocationOrigin.PROACTIVE_RUNTIME
        manifest.final_status = execution.status
        manifest.outcome_summary = execution.detail or execution.error_detail or execution.status.value
        manifest.failure_classification = execution.error_code
        manifest.connector_call_count = len(calls)
        manifest.browser_artifact_count = sum(
            1
            for call in calls
            for artifact in call.artifacts
            if self._is_browser_artifact(artifact.kind, artifact.path)
        )
        manifest.updated_at = utc_now()
        if execution.status in {
            ActionExecutionStatus.EXECUTING,
            ActionExecutionStatus.EXECUTED,
            ActionExecutionStatus.REUSED,
            ActionExecutionStatus.REJECTED,
            ActionExecutionStatus.FAILED,
            ActionExecutionStatus.PREVIEW_ONLY,
            ActionExecutionStatus.PENDING_APPROVAL,
            ActionExecutionStatus.UNCERTAIN_REVIEW_REQUIRED,
        }:
            self._write_json(
                self._bundle_dir(manifest.bundle_id) / self.RESULT_FILE,
                {
                    "action_id": execution.action_id,
                    "status": execution.status.value,
                    "detail": execution.detail,
                    "operator_summary": execution.operator_summary,
                    "next_step_hint": execution.next_step_hint,
                    "error_code": execution.error_code,
                    "error_detail": execution.error_detail,
                    "output_payload": execution.output_payload,
                },
            )
        if execution.finished_at is not None and execution.status not in {
            ActionExecutionStatus.PENDING_APPROVAL,
            ActionExecutionStatus.PREVIEW_ONLY,
            ActionExecutionStatus.EXECUTING,
            ActionExecutionStatus.UNCERTAIN_REVIEW_REQUIRED,
        }:
            manifest.completed_at = execution.finished_at
        self._save_manifest(manifest)
        return manifest

    def record_workflow_run(self, run: WorkflowRunRecord) -> ActionBundleManifestV1:
        bundle_id = self.bundle_id_for_workflow_run(run.workflow_run_id)
        manifest = self.get_bundle(bundle_id)
        if manifest is None:
            manifest = ActionBundleManifestV1(
                bundle_id=bundle_id,
                root_kind=ActionBundleRootKind.WORKFLOW_RUN,
                root_workflow_run_id=run.workflow_run_id,
                requested_workflow_id=run.workflow_id,
                session_id=run.session_id,
                workflow_run_id=run.workflow_run_id,
                workflow_step_ids=[item.step_id for item in run.steps],
                created_at=run.created_at,
            )
        manifest.session_id = run.session_id
        manifest.run_id = manifest.run_id or None
        manifest.workflow_run_id = run.workflow_run_id
        manifest.root_workflow_run_id = run.workflow_run_id
        manifest.requested_workflow_id = run.workflow_id
        manifest.invocation_origin = run.started_by
        manifest.proactive = run.proactive
        manifest.workflow_step_ids = [item.step_id for item in run.steps]
        manifest.final_status = run.status
        manifest.outcome_summary = run.summary or run.detail
        manifest.failure_classification = run.failure_class.value if run.failure_class is not None else None
        manifest.updated_at = utc_now()
        if run.finished_at is not None:
            manifest.completed_at = run.finished_at
        self._ensure_bundle_layout(manifest)
        self._write_json(self._bundle_dir(bundle_id) / self.WORKFLOW_RUN_FILE, run)
        self._write_json(
            self._bundle_dir(bundle_id) / self.RESULT_FILE,
            {
                "workflow_run_id": run.workflow_run_id,
                "workflow_id": run.workflow_id,
                "status": run.status.value,
                "pause_reason": run.pause_reason.value if run.pause_reason is not None else None,
                "failure_class": run.failure_class.value if run.failure_class is not None else None,
                "summary": run.summary,
                "detail": run.detail,
            },
        )
        self._save_manifest(manifest)
        return manifest

    def record_teacher_annotation(self, annotation: TeacherAnnotationRecord) -> ActionBundleManifestV1 | None:
        manifest = None
        if annotation.scope.value == "action" and annotation.action_id:
            manifest = self.find_bundle_for_action(annotation.action_id)
        elif annotation.scope.value == "workflow_run" and annotation.workflow_run_id:
            manifest = self.get_bundle(self.bundle_id_for_workflow_run(annotation.workflow_run_id))
        if manifest is None:
            return None
        annotations = self._load_teacher_annotations(manifest.bundle_id)
        annotations.append(annotation)
        self._write_json(self._bundle_dir(manifest.bundle_id) / self.TEACHER_ANNOTATIONS_FILE, annotations)
        self._write_json(
            self._bundle_dir(manifest.bundle_id) / self.FEEDBACK_FILE,
            {
                "teacher_annotation_ids": [item.annotation_id for item in annotations],
                "labels": [item.label for item in annotations if item.label],
            },
        )
        manifest.teacher_annotation_count = len(annotations)
        manifest.updated_at = utc_now()
        self._save_manifest(manifest)
        return manifest

    def attach_episode_links(self, *, episode_id: str, bundle_ids: list[str]) -> None:
        for bundle_id in bundle_ids:
            manifest = self.get_bundle(bundle_id)
            if manifest is None:
                continue
            if episode_id not in manifest.linked_episode_ids:
                manifest.linked_episode_ids.append(episode_id)
                manifest.updated_at = utc_now()
                self._save_manifest(manifest)

    def find_bundle_for_action(self, action_id: str) -> ActionBundleManifestV1 | None:
        direct = self.get_bundle(self.bundle_id_for_action(action_id))
        if direct is not None:
            return direct
        for manifest in self.list_bundles(limit=1000).items:
            calls = self._load_connector_calls(manifest.bundle_id)
            if any(item.action_id == action_id for item in calls):
                return manifest
        return None

    def find_related_bundles(
        self,
        *,
        session_ids: list[str],
        run_ids: list[str],
        started_at,
        completed_at,
    ) -> list[ActionBundleManifestV1]:
        items: list[ActionBundleManifestV1] = []
        session_set = {item for item in session_ids if item}
        run_set = {item for item in run_ids if item}
        lower_bound = started_at - timedelta(minutes=5) if started_at is not None else None
        upper_bound = completed_at + timedelta(minutes=15) if completed_at is not None else None
        for manifest in self.list_bundles(limit=1000).items:
            if session_set and manifest.session_id not in session_set and manifest.run_id not in run_set:
                continue
            stamp = manifest.updated_at or manifest.created_at
            if lower_bound is not None and stamp < lower_bound:
                continue
            if upper_bound is not None and stamp > upper_bound:
                continue
            items.append(manifest)
        items.sort(key=lambda item: item.created_at)
        return items

    @staticmethod
    def bundle_id_for_action(action_id: str) -> str:
        return f"action_{action_id}"

    @staticmethod
    def bundle_id_for_workflow_run(workflow_run_id: str) -> str:
        return f"workflow_{workflow_run_id}"

    def _load_or_create_manifest_for_request(self, proposal: ActionProposalRecord) -> ActionBundleManifestV1:
        request = proposal.request
        if request.workflow_run_id:
            bundle_id = self.bundle_id_for_workflow_run(request.workflow_run_id)
            manifest = self.get_bundle(bundle_id)
            if manifest is not None:
                return manifest
            manifest = ActionBundleManifestV1(
                bundle_id=bundle_id,
                root_kind=ActionBundleRootKind.WORKFLOW_RUN,
                root_workflow_run_id=request.workflow_run_id,
                requested_workflow_id=None,
                invocation_origin=request.invocation_origin,
                proactive=request.invocation_origin == ActionInvocationOrigin.PROACTIVE_RUNTIME,
                session_id=request.session_id,
                run_id=request.run_id,
                workflow_run_id=request.workflow_run_id,
                workflow_step_ids=[request.workflow_step_id] if request.workflow_step_id else [],
                created_at=request.created_at,
            )
            self._ensure_bundle_layout(manifest)
            return manifest
        bundle_id = self.bundle_id_for_action(request.action_id)
        manifest = self.get_bundle(bundle_id)
        if manifest is not None:
            return manifest
        manifest = ActionBundleManifestV1(
            bundle_id=bundle_id,
            root_kind=ActionBundleRootKind.ACTION,
            root_action_id=request.action_id,
            requested_tool_name=request.tool_name,
            requested_action_name=request.action_name,
            invocation_origin=request.invocation_origin,
            proactive=request.invocation_origin == ActionInvocationOrigin.PROACTIVE_RUNTIME,
            session_id=request.session_id,
            run_id=request.run_id,
            workflow_run_id=request.workflow_run_id,
            workflow_step_ids=[request.workflow_step_id] if request.workflow_step_id else [],
            created_at=request.created_at,
        )
        self._ensure_bundle_layout(manifest)
        return manifest

    def _load_or_create_manifest_for_approval(self, approval: ActionApprovalRecord) -> ActionBundleManifestV1:
        bundle_id = (
            self.bundle_id_for_workflow_run(approval.workflow_run_id)
            if approval.workflow_run_id
            else self.bundle_id_for_action(approval.action_id)
        )
        manifest = self.get_bundle(bundle_id)
        if manifest is not None:
            return manifest
        manifest = ActionBundleManifestV1(
            bundle_id=bundle_id,
            root_kind=ActionBundleRootKind.WORKFLOW_RUN if approval.workflow_run_id else ActionBundleRootKind.ACTION,
            root_action_id=None if approval.workflow_run_id else approval.action_id,
            root_workflow_run_id=approval.workflow_run_id,
            requested_tool_name=approval.tool_name,
            requested_action_name=approval.action_name,
            invocation_origin=approval.request.invocation_origin,
            proactive=approval.request.invocation_origin == ActionInvocationOrigin.PROACTIVE_RUNTIME,
            session_id=approval.request.session_id,
            run_id=approval.request.run_id,
            workflow_run_id=approval.workflow_run_id,
            workflow_step_ids=[approval.workflow_step_id] if approval.workflow_step_id else [],
            created_at=approval.requested_at,
        )
        self._ensure_bundle_layout(manifest)
        return manifest

    def _load_or_create_manifest_for_execution(self, execution: ActionExecutionRecord) -> ActionBundleManifestV1:
        bundle_id = (
            self.bundle_id_for_workflow_run(execution.workflow_run_id)
            if execution.workflow_run_id
            else self.bundle_id_for_action(execution.action_id)
        )
        manifest = self.get_bundle(bundle_id)
        if manifest is not None:
            return manifest
        manifest = ActionBundleManifestV1(
            bundle_id=bundle_id,
            root_kind=ActionBundleRootKind.WORKFLOW_RUN if execution.workflow_run_id else ActionBundleRootKind.ACTION,
            root_action_id=None if execution.workflow_run_id else execution.action_id,
            root_workflow_run_id=execution.workflow_run_id,
            requested_tool_name=execution.tool_name,
            requested_action_name=execution.action_name,
            invocation_origin=execution.invocation_origin,
            proactive=execution.invocation_origin == ActionInvocationOrigin.PROACTIVE_RUNTIME,
            session_id=execution.session_id,
            run_id=execution.run_id,
            workflow_run_id=execution.workflow_run_id,
            workflow_step_ids=[execution.workflow_step_id] if execution.workflow_step_id else [],
            created_at=execution.created_at,
        )
        self._ensure_bundle_layout(manifest)
        return manifest

    def _bundle_dir(self, bundle_id: str) -> Path:
        return self.bundles_dir / bundle_id

    def _ensure_bundle_layout(self, manifest: ActionBundleManifestV1) -> None:
        bundle_dir = self._bundle_dir(manifest.bundle_id)
        bundle_dir.mkdir(parents=True, exist_ok=True)
        manifest.artifact_dir = str(bundle_dir)
        manifest.artifact_files = {
            "manifest": str(bundle_dir / self.MANIFEST_FILE),
            "approval_events": str(bundle_dir / self.APPROVAL_EVENTS_FILE),
            "execution_trace": str(bundle_dir / self.EXECUTION_TRACE_FILE),
            "connector_calls": str(bundle_dir / self.CONNECTOR_CALLS_FILE),
            "feedback": str(bundle_dir / self.FEEDBACK_FILE),
            "teacher_annotations": str(bundle_dir / self.TEACHER_ANNOTATIONS_FILE),
            "result": str(bundle_dir / self.RESULT_FILE),
        }
        if manifest.root_kind == ActionBundleRootKind.WORKFLOW_RUN:
            manifest.artifact_files["workflow_run"] = str(bundle_dir / self.WORKFLOW_RUN_FILE)

    def _save_manifest(self, manifest: ActionBundleManifestV1) -> None:
        self._ensure_bundle_layout(manifest)
        write_json_atomic(Path(manifest.artifact_files["manifest"]), manifest)

    def _load_approval_events(self, bundle_id: str) -> list[ActionApprovalEventRecord]:
        payload = load_json_value_or_quarantine(self._bundle_dir(bundle_id) / self.APPROVAL_EVENTS_FILE)
        if not isinstance(payload, list):
            return []
        items: list[ActionApprovalEventRecord] = []
        for item in payload:
            try:
                items.append(ActionApprovalEventRecord.model_validate(item))
            except Exception:
                continue
        return items

    def _load_execution_trace(self, bundle_id: str) -> list[ActionExecutionRecord]:
        payload = load_json_value_or_quarantine(self._bundle_dir(bundle_id) / self.EXECUTION_TRACE_FILE)
        if not isinstance(payload, list):
            return []
        items: list[ActionExecutionRecord] = []
        for item in payload:
            try:
                items.append(ActionExecutionRecord.model_validate(item))
            except Exception:
                continue
        return items

    def _load_connector_calls(self, bundle_id: str) -> list[ActionConnectorCallRecord]:
        payload = load_json_value_or_quarantine(self._bundle_dir(bundle_id) / self.CONNECTOR_CALLS_FILE)
        if not isinstance(payload, list):
            return []
        items: list[ActionConnectorCallRecord] = []
        for item in payload:
            try:
                items.append(ActionConnectorCallRecord.model_validate(item))
            except Exception:
                continue
        return items

    def _load_teacher_annotations(self, bundle_id: str) -> list[TeacherAnnotationRecord]:
        payload = load_json_value_or_quarantine(self._bundle_dir(bundle_id) / self.TEACHER_ANNOTATIONS_FILE)
        if not isinstance(payload, list):
            return []
        items: list[TeacherAnnotationRecord] = []
        for item in payload:
            try:
                items.append(TeacherAnnotationRecord.model_validate(item))
            except Exception:
                continue
        return items

    def _load_retry_records(self, bundle_id: str) -> list[ActionRetryRecord]:
        payload = load_json_value_or_quarantine(self._bundle_dir(bundle_id) / "retries.json")
        if not isinstance(payload, list):
            return []
        items: list[ActionRetryRecord] = []
        for item in payload:
            try:
                items.append(ActionRetryRecord.model_validate(item))
            except Exception:
                continue
        return items

    def _write_json(self, path: Path, payload: Any) -> None:
        if hasattr(payload, "model_dump"):
            data = payload.model_dump(mode="json")
        elif isinstance(payload, list):
            data = [item.model_dump(mode="json") if hasattr(item, "model_dump") else item for item in payload]
        else:
            data = payload
        write_json_atomic(path, data)

    @staticmethod
    def _is_browser_artifact(kind: str, path: str | None) -> bool:
        normalized = kind.lower()
        if "browser" in normalized or "screenshot" in normalized or "page_text" in normalized:
            return True
        return bool(path and "/browser/" in path.replace("\\", "/"))
