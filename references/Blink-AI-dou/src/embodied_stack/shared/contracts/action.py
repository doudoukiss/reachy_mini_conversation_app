from __future__ import annotations

from enum import Enum

from ._common import Any, BaseModel, ConfigDict, Field, datetime, model_validator, utc_now


class ActionRiskClass(str, Enum):
    READ_ONLY = "read_only"
    LOW_RISK_LOCAL_WRITE = "low_risk_local_write"
    OPERATOR_SENSITIVE_WRITE = "operator_sensitive_write"
    EXTERNAL_SIDE_EFFECT = "external_side_effect"
    IRREVERSIBLE_OR_HIGH_RISK = "irreversible_or_high_risk"


class ActionPolicyDecision(str, Enum):
    ALLOW = "allow"
    PREVIEW_ONLY = "preview_only"
    REQUIRE_APPROVAL = "require_approval"
    REJECT = "reject"


class ActionApprovalState(str, Enum):
    NOT_REQUIRED = "not_required"
    IMPLICIT_OPERATOR_APPROVAL = "implicit_operator_approval"
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class ActionExecutionStatus(str, Enum):
    EXECUTING = "executing"
    EXECUTED = "executed"
    REUSED = "reused"
    PREVIEW_ONLY = "preview_only"
    PENDING_APPROVAL = "pending_approval"
    REJECTED = "rejected"
    FAILED = "failed"
    UNCERTAIN_REVIEW_REQUIRED = "uncertain_review_required"


class ActionInvocationOrigin(str, Enum):
    USER_TURN = "user_turn"
    OPERATOR_CONSOLE = "operator_console"
    PROACTIVE_RUNTIME = "proactive_runtime"


class BrowserRequestedAction(str, Enum):
    OPEN_URL = "open_url"
    CAPTURE_SNAPSHOT = "capture_snapshot"
    EXTRACT_VISIBLE_TEXT = "extract_visible_text"
    SUMMARIZE_PAGE = "summarize_page"
    FIND_CLICK_TARGETS = "find_click_targets"
    CLICK_TARGET = "click_target"
    TYPE_TEXT = "type_text"
    SUBMIT_FORM = "submit_form"


class BrowserTargetHintRecord(BaseModel):
    label: str | None = None
    role: str | None = None
    text: str | None = None
    placeholder: str | None = None
    field_name: str | None = None


class BrowserTargetCandidateRecord(BaseModel):
    target_id: str
    label: str | None = None
    text: str | None = None
    role: str | None = None
    input_type: str | None = None
    selector: str | None = None
    selector_kind: str | None = None
    placeholder: str | None = None
    field_name: str | None = None
    action_hints: list[str] = Field(default_factory=list)
    visible: bool = True
    disabled: bool = False


class BrowserSessionStatusRecord(BaseModel):
    blink_session_id: str | None = None
    browser_session_id: str | None = None
    backend_mode: str = "disabled"
    supported: bool = False
    configured: bool = False
    status: str = "inactive"
    current_url: str | None = None
    page_title: str | None = None
    last_action_id: str | None = None
    last_requested_action: BrowserRequestedAction | None = None
    last_screenshot_path: str | None = None
    updated_at: datetime = Field(default_factory=utc_now)


class BrowserSnapshotRecord(BaseModel):
    current_url: str | None = None
    page_title: str | None = None
    visible_text: str | None = None
    summary: str | None = None
    screenshot_path: str | None = None
    screenshot_data_url: str | None = None
    snapshot_path: str | None = None
    page_text_path: str | None = None
    captured_at: datetime = Field(default_factory=utc_now)


class BrowserActionPreviewRecord(BaseModel):
    action_id: str
    requested_action: BrowserRequestedAction
    current_url: str | None = None
    page_title: str | None = None
    summary: str | None = None
    visible_text: str | None = None
    screenshot_path: str | None = None
    screenshot_data_url: str | None = None
    target_hint: BrowserTargetHintRecord | None = None
    resolved_target: BrowserTargetCandidateRecord | None = None
    candidate_targets: list[BrowserTargetCandidateRecord] = Field(default_factory=list)
    text_input: str | None = None
    preview_path: str | None = None
    detail: str | None = None
    created_at: datetime = Field(default_factory=utc_now)


class BrowserActionResultRecord(BaseModel):
    action_id: str
    requested_action: BrowserRequestedAction
    status: str
    current_url: str | None = None
    page_title: str | None = None
    summary: str | None = None
    visible_text: str | None = None
    screenshot_path: str | None = None
    screenshot_data_url: str | None = None
    snapshot_path: str | None = None
    page_text_path: str | None = None
    result_path: str | None = None
    resolved_target: BrowserTargetCandidateRecord | None = None
    candidate_targets: list[BrowserTargetCandidateRecord] = Field(default_factory=list)
    text_input: str | None = None
    executed_at: datetime = Field(default_factory=utc_now)


class BrowserRuntimeStatusRecord(BaseModel):
    connector_id: str = "browser_runtime"
    backend_mode: str = "disabled"
    supported: bool = False
    configured: bool = False
    headless: bool = True
    active_session: BrowserSessionStatusRecord | None = None
    latest_snapshot: BrowserSnapshotRecord | None = None
    pending_preview: BrowserActionPreviewRecord | None = None
    last_result: BrowserActionResultRecord | None = None
    updated_at: datetime = Field(default_factory=utc_now)


class ActionArtifactRecord(BaseModel):
    kind: str
    label: str
    path: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)


class ActionRequestRecord(BaseModel):
    action_id: str
    request_hash: str
    idempotency_key: str
    tool_name: str
    requested_tool_name: str | None = None
    action_name: str | None = None
    requested_action_name: str | None = None
    connector_id: str
    risk_class: ActionRiskClass
    invocation_origin: ActionInvocationOrigin = ActionInvocationOrigin.USER_TURN
    session_id: str | None = None
    run_id: str | None = None
    workflow_run_id: str | None = None
    workflow_step_id: str | None = None
    context_mode: str | None = None
    body_mode: str | None = None
    input_payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def _default_action_names(self):
        if not self.action_name:
            self.action_name = self.tool_name
        if self.requested_action_name is None:
            self.requested_action_name = self.requested_tool_name or self.action_name
        return self


class ActionProposalRecord(BaseModel):
    action_id: str
    tool_name: str
    action_name: str
    connector_id: str
    risk_class: ActionRiskClass
    policy_decision: ActionPolicyDecision
    approval_state: ActionApprovalState
    detail: str | None = None
    request: ActionRequestRecord
    created_at: datetime = Field(default_factory=utc_now)


class ActionApprovalRecord(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    action_id: str
    tool_name: str
    action_name: str | None = None
    connector_id: str
    request_hash: str
    idempotency_key: str
    policy_decision: ActionPolicyDecision
    approval_state: ActionApprovalState
    detail: str | None = None
    operator_note: str | None = None
    workflow_run_id: str | None = None
    workflow_step_id: str | None = None
    request: ActionRequestRecord
    requested_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def _default_action_name(self):
        if not self.action_name:
            self.action_name = self.request.action_name or self.tool_name
        return self


class ActionExecutionRecord(BaseModel):
    action_id: str
    tool_name: str
    action_name: str | None = None
    connector_id: str
    request_hash: str
    idempotency_key: str
    risk_class: ActionRiskClass
    invocation_origin: ActionInvocationOrigin
    policy_decision: ActionPolicyDecision
    approval_state: ActionApprovalState
    status: ActionExecutionStatus
    session_id: str | None = None
    run_id: str | None = None
    workflow_run_id: str | None = None
    workflow_step_id: str | None = None
    input_payload: dict[str, Any] = Field(default_factory=dict)
    output_payload: dict[str, Any] = Field(default_factory=dict)
    error_code: str | None = None
    error_detail: str | None = None
    detail: str | None = None
    operator_summary: str | None = None
    next_step_hint: str | None = None
    reused_result: bool = False
    artifacts: list[ActionArtifactRecord] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)
    started_at: datetime = Field(default_factory=utc_now)
    finished_at: datetime | None = None

    @model_validator(mode="after")
    def _default_action_name(self):
        if not self.action_name:
            self.action_name = self.tool_name
        return self


class ActionPreviewRecord(BaseModel):
    action_id: str
    tool_name: str
    action_name: str
    connector_id: str
    summary: str | None = None
    detail: str | None = None
    operator_summary: str | None = None
    next_step_hint: str | None = None
    preview_payload: dict[str, Any] = Field(default_factory=dict)
    artifacts: list[ActionArtifactRecord] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)


class ActionExecutionResultRecord(BaseModel):
    action_id: str
    tool_name: str
    action_name: str
    connector_id: str
    status: ActionExecutionStatus
    summary: str | None = None
    detail: str | None = None
    operator_summary: str | None = None
    next_step_hint: str | None = None
    output_payload: dict[str, Any] = Field(default_factory=dict)
    error_code: str | None = None
    error_detail: str | None = None
    artifacts: list[ActionArtifactRecord] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)


class ActionApprovalResolutionRequest(BaseModel):
    action_id: str
    operator_note: str | None = None


class ActionApprovalResolutionRecord(BaseModel):
    action_id: str
    tool_name: str
    action_name: str
    connector_id: str
    approval_state: ActionApprovalState
    operator_note: str | None = None
    detail: str | None = None
    approval: ActionApprovalRecord | None = None
    execution: ActionExecutionRecord | None = None
    updated_at: datetime = Field(default_factory=utc_now)


class ActionReplayRequestRecord(BaseModel):
    action_id: str | None = None
    bundle_id: str | None = None
    operator_note: str | None = None
    invocation_origin: ActionInvocationOrigin = ActionInvocationOrigin.OPERATOR_CONSOLE
    approved_action_ids: list[str] = Field(default_factory=list)
    requested_at: datetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def _validate_target(self):
        if not self.action_id and not self.bundle_id:
            raise ValueError("action_replay_requires_action_id_or_bundle_id")
        return self


class ActionBundleRootKind(str, Enum):
    ACTION = "action"
    WORKFLOW_RUN = "workflow_run"


class ActionReplayStatus(str, Enum):
    COMPLETED = "completed"
    BLOCKED = "blocked"
    FAILED = "failed"


class ActionApprovalEventRecord(BaseModel):
    action_id: str
    tool_name: str
    action_name: str
    connector_id: str
    approval_state: ActionApprovalState
    detail: str | None = None
    operator_note: str | None = None
    workflow_run_id: str | None = None
    workflow_step_id: str | None = None
    occurred_at: datetime = Field(default_factory=utc_now)


class ActionConnectorCallRecord(BaseModel):
    action_id: str
    tool_name: str
    action_name: str
    connector_id: str
    workflow_run_id: str | None = None
    workflow_step_id: str | None = None
    risk_class: ActionRiskClass | None = None
    approval_state: ActionApprovalState | None = None
    status: ActionExecutionStatus
    input_payload: dict[str, Any] = Field(default_factory=dict)
    output_payload: dict[str, Any] = Field(default_factory=dict)
    error_code: str | None = None
    error_detail: str | None = None
    artifacts: list[ActionArtifactRecord] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)
    started_at: datetime | None = None
    finished_at: datetime | None = None


class ActionRetryRecord(BaseModel):
    action_id: str
    source_action_id: str | None = None
    workflow_run_id: str | None = None
    workflow_step_id: str | None = None
    reason: str | None = None
    created_at: datetime = Field(default_factory=utc_now)


class ActionBundleManifestV1(BaseModel):
    bundle_id: str
    schema_version: str = "blink_action_bundle/v1"
    root_kind: ActionBundleRootKind
    root_action_id: str | None = None
    root_workflow_run_id: str | None = None
    requested_tool_name: str | None = None
    requested_action_name: str | None = None
    requested_workflow_id: str | None = None
    invocation_origin: ActionInvocationOrigin | None = None
    proactive: bool = False
    session_id: str | None = None
    run_id: str | None = None
    workflow_run_id: str | None = None
    workflow_step_ids: list[str] = Field(default_factory=list)
    policy_decision: ActionPolicyDecision | None = None
    approval_state: ActionApprovalState | None = None
    final_status: ActionExecutionStatus | WorkflowRunStatus | None = None
    outcome_summary: str | None = None
    failure_classification: str | None = None
    linked_episode_ids: list[str] = Field(default_factory=list)
    approval_event_count: int = 0
    connector_call_count: int = 0
    retry_count: int = 0
    browser_artifact_count: int = 0
    operator_feedback_count: int = 0
    teacher_annotation_count: int = 0
    artifact_dir: str | None = None
    artifact_files: dict[str, str] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    completed_at: datetime | None = None


class ActionBundleListResponse(BaseModel):
    items: list[ActionBundleManifestV1] = Field(default_factory=list)


class ActionBundleDetailRecord(BaseModel):
    manifest: ActionBundleManifestV1
    approval_events: list[ActionApprovalEventRecord] = Field(default_factory=list)
    execution_trace: list[ActionExecutionRecord] = Field(default_factory=list)
    connector_calls: list[ActionConnectorCallRecord] = Field(default_factory=list)
    retries: list[ActionRetryRecord] = Field(default_factory=list)
    replays: list[ActionReplayRecord] = Field(default_factory=list)
    teacher_annotations: list[dict[str, Any]] = Field(default_factory=list)
    feedback: dict[str, Any] = Field(default_factory=dict)
    result: dict[str, Any] = Field(default_factory=dict)


class ActionReplayRecord(BaseModel):
    replay_id: str
    schema_version: str = "blink_action_replay/v1"
    bundle_id: str
    source_bundle_schema_version: str = "blink_action_bundle/v1"
    root_kind: ActionBundleRootKind
    status: ActionReplayStatus
    replayed_action_count: int = 0
    blocked_action_ids: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    artifact_dir: str | None = None
    artifact_files: dict[str, str] = Field(default_factory=dict)
    started_at: datetime = Field(default_factory=utc_now)
    completed_at: datetime | None = None


class ConnectorDescriptorRecord(BaseModel):
    connector_id: str
    label: str
    category: str
    transport_kind: str
    supported: bool = True
    configured: bool = True
    capability_tags: list[str] = Field(default_factory=list)
    supported_actions: list[str] = Field(default_factory=list)
    action_risk: dict[str, ActionRiskClass] = Field(default_factory=dict)
    dry_run_supported: bool = False
    dry_run_only: bool = False
    notes: list[str] = Field(default_factory=list)


class ConnectorHealthRecord(BaseModel):
    connector_id: str
    supported: bool = True
    configured: bool = True
    status: str = "healthy"
    detail: str | None = None
    updated_at: datetime = Field(default_factory=utc_now)


class WorkflowTriggerKind(str, Enum):
    USER_REQUEST = "user_request"
    OPERATOR_LAUNCH = "operator_launch"
    DUE_REMINDER = "due_reminder"
    DAILY_DIGEST = "daily_digest"
    EVENT_START_WINDOW = "event_start_window"
    VENUE_SCHEDULED_PROMPT = "venue_scheduled_prompt"


class WorkflowRunStatus(str, Enum):
    SUGGESTED = "suggested"
    RUNNING = "running"
    PAUSED = "paused"
    WAITING_FOR_APPROVAL = "waiting_for_approval"
    FAILED = "failed"
    COMPLETED = "completed"
    TIMED_OUT = "timed_out"
    CANCELLED = "cancelled"


class WorkflowStepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    WAITING_FOR_APPROVAL = "waiting_for_approval"
    FAILED = "failed"
    COMPLETED = "completed"
    SKIPPED = "skipped"


class WorkflowPauseReason(str, Enum):
    WAITING_FOR_APPROVAL = "waiting_for_approval"
    OPERATOR_PAUSED = "operator_paused"
    FAILED_STEP = "failed_step"
    APPROVAL_REJECTED = "approval_rejected"
    RUNTIME_RESTART_REVIEW = "runtime_restart_review"
    QUIET_HOURS_SUPPRESSED = "quiet_hours_suppressed"
    SUGGESTION_ONLY = "suggestion_only"
    TIMED_OUT = "timed_out"


class WorkflowFailureClass(str, Enum):
    PRECONDITION_FAILED = "precondition_failed"
    ACTION_FAILED = "action_failed"
    APPROVAL_REJECTED = "approval_rejected"
    TIMEOUT = "timeout"
    POLICY_SUPPRESSED = "policy_suppressed"
    EXECUTION_ERROR = "execution_error"


class WorkflowStepKind(str, Enum):
    CONNECTOR_ACTION = "connector_action"
    DETERMINISTIC_CHECK = "deterministic_check"
    SUMMARY_ARTIFACT = "summary_artifact"


class WorkflowTriggerRecord(BaseModel):
    trigger_kind: WorkflowTriggerKind
    trigger_key: str
    source_session_id: str | None = None
    proactive: bool = False
    scheduled_for: datetime | None = None
    note: str | None = None
    created_at: datetime = Field(default_factory=utc_now)


class WorkflowDefinitionRecord(BaseModel):
    workflow_id: str
    label: str
    description: str | None = None
    version: str = "1.0"
    supported_triggers: list[WorkflowTriggerKind] = Field(default_factory=list)
    proactive_capable: bool = False
    operator_launch_supported: bool = True
    user_tool_supported: bool = True
    notes: list[str] = Field(default_factory=list)


class WorkflowStepRecord(BaseModel):
    step_id: str
    step_key: str
    label: str
    kind: WorkflowStepKind = WorkflowStepKind.DETERMINISTIC_CHECK
    status: WorkflowStepStatus = WorkflowStepStatus.PENDING
    tool_name: str | None = None
    action_id: str | None = None
    action_ids: list[str] = Field(default_factory=list)
    blocking_action_id: str | None = None
    input_payload: dict[str, Any] = Field(default_factory=dict)
    output_payload: dict[str, Any] = Field(default_factory=dict)
    summary: str | None = None
    detail: str | None = None
    retry_budget: int = 0
    attempt_count: int = 0
    artifacts: list[ActionArtifactRecord] = Field(default_factory=list)
    started_at: datetime | None = None
    finished_at: datetime | None = None


class WorkflowRunRecord(BaseModel):
    workflow_run_id: str
    workflow_id: str
    label: str
    version: str = "1.0"
    status: WorkflowRunStatus = WorkflowRunStatus.PAUSED
    trigger: WorkflowTriggerRecord
    session_id: str | None = None
    context_mode: str | None = None
    started_by: ActionInvocationOrigin = ActionInvocationOrigin.USER_TURN
    proactive: bool = False
    suggested_only: bool = False
    blocking_action_id: str | None = None
    current_step_id: str | None = None
    current_step_label: str | None = None
    pause_reason: WorkflowPauseReason | None = None
    failure_class: WorkflowFailureClass | None = None
    summary: str | None = None
    detail: str | None = None
    body_feedback_state: str | None = None
    inputs: dict[str, Any] = Field(default_factory=dict)
    state_payload: dict[str, Any] = Field(default_factory=dict)
    steps: list[WorkflowStepRecord] = Field(default_factory=list)
    artifacts: list[ActionArtifactRecord] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    updated_at: datetime = Field(default_factory=utc_now)


class WorkflowStartRequestRecord(BaseModel):
    workflow_id: str
    session_id: str | None = None
    inputs: dict[str, Any] = Field(default_factory=dict)
    note: str | None = None


class WorkflowRunActionRequestRecord(BaseModel):
    note: str | None = None


class WorkflowRunActionResponseRecord(BaseModel):
    run: WorkflowRunRecord
    workflow_run_id: str | None = None
    workflow_id: str | None = None
    status: WorkflowRunStatus | None = None
    current_step_id: str | None = None
    current_step_label: str | None = None
    blocking_action_id: str | None = None
    pause_reason: WorkflowPauseReason | None = None
    summary: str | None = None
    detail: str | None = None
    resumed: bool = False
    retried: bool = False
    paused: bool = False

    @model_validator(mode="after")
    def _default_fields_from_run(self):
        if self.workflow_run_id is None:
            self.workflow_run_id = self.run.workflow_run_id
        if self.workflow_id is None:
            self.workflow_id = self.run.workflow_id
        if self.status is None:
            self.status = self.run.status
        if self.current_step_id is None:
            self.current_step_id = self.run.current_step_id
        if self.current_step_label is None:
            self.current_step_label = self.run.current_step_label
        if self.blocking_action_id is None:
            self.blocking_action_id = self.run.blocking_action_id
        if self.pause_reason is None:
            self.pause_reason = self.run.pause_reason
        if self.summary is None:
            self.summary = self.run.summary
        return self


class WorkflowCatalogResponse(BaseModel):
    items: list[WorkflowDefinitionRecord] = Field(default_factory=list)


class WorkflowRunListResponse(BaseModel):
    items: list[WorkflowRunRecord] = Field(default_factory=list)


class ConnectorCatalogResponse(BaseModel):
    items: list[ConnectorDescriptorRecord] = Field(default_factory=list)


class ActionApprovalListResponse(BaseModel):
    items: list[ActionApprovalRecord] = Field(default_factory=list)


class ActionExecutionListResponse(BaseModel):
    items: list[ActionExecutionRecord] = Field(default_factory=list)


class ActionPlaneStatus(BaseModel):
    enabled: bool = True
    pending_approval_count: int = 0
    review_required_count: int = 0
    degraded_connector_count: int = 0
    last_action_id: str | None = None
    last_action_status: ActionExecutionStatus | None = None
    latest_failure_action_id: str | None = None
    active_workflow_run_count: int = 0
    waiting_workflow_count: int = 0
    last_workflow_run_id: str | None = None
    last_workflow_status: WorkflowRunStatus | None = None
    connector_health: list[ConnectorHealthRecord] = Field(default_factory=list)
    pending_approvals: list[ActionApprovalRecord] = Field(default_factory=list)


class ActionCenterItemRecord(BaseModel):
    kind: str
    severity: str = "info"
    title: str
    summary: str
    action_id: str | None = None
    workflow_run_id: str | None = None
    bundle_id: str | None = None
    session_id: str | None = None
    next_step_hint: str | None = None
    detail_ref: dict[str, Any] = Field(default_factory=dict)


class ActionCenterOverviewRecord(BaseModel):
    status: ActionPlaneStatus = Field(default_factory=ActionPlaneStatus)
    attention_items: list[ActionCenterItemRecord] = Field(default_factory=list)
    connectors: list[ConnectorDescriptorRecord] = Field(default_factory=list)
    approvals: list[ActionApprovalRecord] = Field(default_factory=list)
    active_workflows: list[WorkflowRunRecord] = Field(default_factory=list)
    recent_history: list[ActionExecutionRecord] = Field(default_factory=list)
    recent_bundles: list[ActionBundleManifestV1] = Field(default_factory=list)
    browser_status: BrowserRuntimeStatusRecord | None = None
    latest_replays: list[ActionReplayRecord] = Field(default_factory=list)
    recent_failures: list[ActionExecutionRecord] = Field(default_factory=list)


__all__ = [
    "ActionApprovalRecord",
    "ActionApprovalListResponse",
    "ActionApprovalResolutionRecord",
    "ActionApprovalResolutionRequest",
    "ActionApprovalState",
    "ActionApprovalEventRecord",
    "ActionArtifactRecord",
    "ActionBundleListResponse",
    "ActionBundleDetailRecord",
    "ActionBundleManifestV1",
    "ActionBundleRootKind",
    "ActionCenterItemRecord",
    "ActionCenterOverviewRecord",
    "ActionConnectorCallRecord",
    "ActionExecutionListResponse",
    "ActionExecutionRecord",
    "ActionExecutionResultRecord",
    "ActionExecutionStatus",
    "ActionInvocationOrigin",
    "ActionPlaneStatus",
    "ActionPolicyDecision",
    "ActionPreviewRecord",
    "ActionProposalRecord",
    "ActionReplayRecord",
    "ActionReplayRequestRecord",
    "ActionReplayStatus",
    "ActionRequestRecord",
    "ActionRetryRecord",
    "ActionRiskClass",
    "BrowserActionPreviewRecord",
    "BrowserActionResultRecord",
    "BrowserRequestedAction",
    "BrowserRuntimeStatusRecord",
    "BrowserSessionStatusRecord",
    "BrowserSnapshotRecord",
    "BrowserTargetCandidateRecord",
    "BrowserTargetHintRecord",
    "ConnectorCatalogResponse",
    "ConnectorDescriptorRecord",
    "ConnectorHealthRecord",
    "WorkflowCatalogResponse",
    "WorkflowDefinitionRecord",
    "WorkflowFailureClass",
    "WorkflowPauseReason",
    "WorkflowRunActionRequestRecord",
    "WorkflowRunActionResponseRecord",
    "WorkflowRunListResponse",
    "WorkflowRunRecord",
    "WorkflowRunStatus",
    "WorkflowStepRecord",
    "WorkflowStepKind",
    "WorkflowStepStatus",
    "WorkflowStartRequestRecord",
    "WorkflowTriggerKind",
    "WorkflowTriggerRecord",
]
