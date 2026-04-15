from __future__ import annotations

from embodied_stack.action_plane.approvals import ApprovalStore
from embodied_stack.action_plane.health import ConnectorHealthStore
from embodied_stack.action_plane.policy import ActionPolicyEngine
from embodied_stack.action_plane.registry import ActionRegistry
from embodied_stack.config import Settings
from embodied_stack.shared.contracts import (
    ActionApprovalRecord,
    ActionApprovalResolutionRecord,
    ActionApprovalResolutionRequest,
    ActionApprovalState,
    ActionBundleDetailRecord,
    ActionBundleManifestV1,
    ActionBundleRootKind,
    ActionCenterItemRecord,
    ActionCenterOverviewRecord,
    ActionExecutionRecord,
    ActionExecutionResultRecord,
    ActionExecutionStatus,
    ActionInvocationOrigin,
    ActionPlaneStatus,
    ActionPolicyDecision,
    ActionPreviewRecord,
    ActionReplayRequestRecord,
    ActionReplayRecord,
    ActionReplayStatus,
    ActionRequestRecord,
    ActionRiskClass,
    ConnectorDescriptorRecord,
    TeacherReviewRequest,
)


class _WriteMemoryInput:
    def __init__(self, *, scope: str) -> None:
        self.scope = scope


class _BrowserInput:
    def __init__(self, *, requested_action: str) -> None:
        self.requested_action = requested_action


def test_action_contracts_round_trip():
    request = ActionRequestRecord(
        action_id="act_123",
        request_hash="req_hash",
        idempotency_key="idem_key",
        tool_name="write_memory",
        connector_id="memory_local",
        risk_class=ActionRiskClass.LOW_RISK_LOCAL_WRITE,
        invocation_origin=ActionInvocationOrigin.USER_TURN,
        input_payload={"scope": "session", "key": "topic", "value": "robotics"},
    )
    preview = ActionPreviewRecord(
        action_id=request.action_id,
        tool_name=request.tool_name,
        action_name=request.action_name or request.tool_name,
        connector_id=request.connector_id,
        preview_payload={"persisted": False},
    )
    execution = ActionExecutionRecord(
        action_id=request.action_id,
        tool_name=request.tool_name,
        connector_id=request.connector_id,
        request_hash=request.request_hash,
        idempotency_key=request.idempotency_key,
        risk_class=request.risk_class,
        invocation_origin=request.invocation_origin,
        policy_decision=ActionPolicyDecision.ALLOW,
        approval_state=ActionApprovalState.NOT_REQUIRED,
        status=ActionExecutionStatus.EXECUTED,
        input_payload=request.input_payload,
        output_payload={"persisted": True},
    )
    result = ActionExecutionResultRecord(
        action_id=request.action_id,
        tool_name=request.tool_name,
        action_name=request.action_name or request.tool_name,
        connector_id=request.connector_id,
        status=execution.status,
        output_payload=execution.output_payload,
    )
    resolution_request = ActionApprovalResolutionRequest(action_id=request.action_id, operator_note="approved")
    resolution = ActionApprovalResolutionRecord(
        action_id=request.action_id,
        tool_name=request.tool_name,
        action_name=request.action_name or request.tool_name,
        connector_id=request.connector_id,
        approval_state=ActionApprovalState.APPROVED,
        operator_note=resolution_request.operator_note,
    )
    replay = ActionReplayRequestRecord(action_id=request.action_id)
    bundle_manifest = ActionBundleManifestV1(
        bundle_id="action_act_123",
        root_kind=ActionBundleRootKind.ACTION,
        root_action_id=request.action_id,
        requested_tool_name=request.tool_name,
        requested_action_name=request.tool_name,
        invocation_origin=request.invocation_origin,
        session_id="session-123",
    )
    replay_record = ActionReplayRecord(
        replay_id="action-replay-123",
        bundle_id=bundle_manifest.bundle_id,
        root_kind=bundle_manifest.root_kind,
        status=ActionReplayStatus.COMPLETED,
        replayed_action_count=1,
    )
    bundle_detail = ActionBundleDetailRecord(
        manifest=bundle_manifest,
        execution_trace=[execution],
        replays=[replay_record],
    )
    connector = ConnectorDescriptorRecord(
        connector_id="notes_local",
        label="Notes",
        category="local",
        transport_kind="filesystem",
        capability_tags=["notes"],
        supported_actions=["create_note"],
        action_risk={"create_note": ActionRiskClass.LOW_RISK_LOCAL_WRITE},
        dry_run_supported=True,
    )
    status = ActionPlaneStatus(
        enabled=True,
        pending_approval_count=0,
        last_action_id=execution.action_id,
        last_action_status=execution.status,
        review_required_count=1,
        degraded_connector_count=1,
        latest_failure_action_id="act_failure",
    )
    action_center_item = ActionCenterItemRecord(
        kind="approval",
        severity="medium",
        title="Approval required",
        summary="Review the pending write before continuing.",
        action_id=request.action_id,
        next_step_hint="Approve or reject the action from the Action Center.",
        detail_ref={"kind": "approval", "action_id": request.action_id},
    )
    action_center_overview = ActionCenterOverviewRecord(
        status=status,
        attention_items=[action_center_item],
        connectors=[connector],
        approvals=[],
        active_workflows=[],
        recent_history=[execution],
        recent_bundles=[bundle_manifest],
        browser_status=None,
        latest_replays=[replay_record],
        recent_failures=[],
    )
    teacher_review = TeacherReviewRequest(
        review_value="needs_revision",
        author="operator_console",
        action_feedback_labels=["missing_follow_up"],
    )

    assert ActionRequestRecord.model_validate_json(request.model_dump_json()) == request
    assert ActionPreviewRecord.model_validate_json(preview.model_dump_json()) == preview
    assert ActionExecutionRecord.model_validate_json(execution.model_dump_json()) == execution
    assert ActionExecutionResultRecord.model_validate_json(result.model_dump_json()) == result
    assert ActionApprovalResolutionRequest.model_validate_json(resolution_request.model_dump_json()) == resolution_request
    assert ActionApprovalResolutionRecord.model_validate_json(resolution.model_dump_json()) == resolution
    assert ActionReplayRequestRecord.model_validate_json(replay.model_dump_json()) == replay
    assert ActionBundleManifestV1.model_validate_json(bundle_manifest.model_dump_json()) == bundle_manifest
    assert ActionReplayRecord.model_validate_json(replay_record.model_dump_json()) == replay_record
    assert ActionBundleDetailRecord.model_validate_json(bundle_detail.model_dump_json()) == bundle_detail
    assert ConnectorDescriptorRecord.model_validate_json(connector.model_dump_json()) == connector
    assert ActionPlaneStatus.model_validate_json(status.model_dump_json()) == status
    assert ActionCenterItemRecord.model_validate_json(action_center_item.model_dump_json()) == action_center_item
    assert ActionCenterOverviewRecord.model_validate_json(action_center_overview.model_dump_json()) == action_center_overview
    assert TeacherReviewRequest.model_validate_json(teacher_review.model_dump_json()) == teacher_review


def test_action_policy_matrix(tmp_path):
    policy = ActionPolicyEngine()
    health_store = ConnectorHealthStore(tmp_path, registry=ActionRegistry())
    healthy_connector = health_store.get_record("memory_local")
    browser_connector = health_store.get_record("browser_runtime")

    assert healthy_connector is not None
    assert browser_connector is not None

    allow = policy.evaluate(
        tool_name="write_memory",
        connector_id="memory_local",
        invocation_origin=ActionInvocationOrigin.USER_TURN,
        connector_health=healthy_connector,
        input_model=_WriteMemoryInput(scope="session"),
    )
    assert allow.policy_decision == ActionPolicyDecision.ALLOW

    preview = policy.evaluate(
        tool_name="write_memory",
        connector_id="memory_local",
        invocation_origin=ActionInvocationOrigin.PROACTIVE_RUNTIME,
        connector_health=healthy_connector,
        input_model=_WriteMemoryInput(scope="session"),
    )
    assert preview.policy_decision == ActionPolicyDecision.PREVIEW_ONLY

    require = policy.evaluate(
        tool_name="write_memory",
        connector_id="memory_local",
        invocation_origin=ActionInvocationOrigin.USER_TURN,
        connector_health=healthy_connector,
        input_model=_WriteMemoryInput(scope="profile"),
    )
    assert require.policy_decision == ActionPolicyDecision.REQUIRE_APPROVAL
    assert require.approval_state == ActionApprovalState.PENDING

    implicit = policy.evaluate(
        tool_name="log_incident",
        connector_id="incident_local",
        invocation_origin=ActionInvocationOrigin.OPERATOR_CONSOLE,
        connector_health=health_store.get_record("incident_local"),
        input_model=_WriteMemoryInput(scope="session"),
    )
    assert implicit.policy_decision == ActionPolicyDecision.ALLOW
    assert implicit.approval_state == ActionApprovalState.IMPLICIT_OPERATOR_APPROVAL

    reject = policy.evaluate(
        tool_name="browser_task",
        connector_id="browser_runtime",
        invocation_origin=ActionInvocationOrigin.USER_TURN,
        connector_health=browser_connector,
        input_model=_BrowserInput(requested_action="open_url"),
    )
    assert reject.policy_decision == ActionPolicyDecision.REJECT

    stub_registry = ActionRegistry(
        settings=Settings(
            _env_file=None,
            blink_action_plane_browser_backend="stub",
            blink_action_plane_browser_storage_dir=str(tmp_path / "browser"),
        )
    )
    stub_health_store = ConnectorHealthStore(tmp_path / "stub", registry=stub_registry)
    browser_read = policy.evaluate(
        tool_name="browser_task",
        action_name="open_url",
        connector_id="browser_runtime",
        invocation_origin=ActionInvocationOrigin.USER_TURN,
        connector=stub_registry.get_connector("browser_runtime"),
        connector_health=stub_health_store.get_record("browser_runtime"),
        input_model=_BrowserInput(requested_action="open_url"),
    )
    browser_write = policy.evaluate(
        tool_name="browser_task",
        action_name="click_target",
        connector_id="browser_runtime",
        invocation_origin=ActionInvocationOrigin.USER_TURN,
        connector=stub_registry.get_connector("browser_runtime"),
        connector_health=stub_health_store.get_record("browser_runtime"),
        input_model=_BrowserInput(requested_action="click_target"),
    )
    assert browser_read.policy_decision == ActionPolicyDecision.ALLOW
    assert browser_write.policy_decision == ActionPolicyDecision.REQUIRE_APPROVAL


def test_approval_store_persists_and_reloads(tmp_path):
    store = ApprovalStore(tmp_path)
    request = ActionRequestRecord(
        action_id="act_approval",
        request_hash="req_hash",
        idempotency_key="idem_key",
        tool_name="write_memory",
        connector_id="memory_local",
        risk_class=ActionRiskClass.OPERATOR_SENSITIVE_WRITE,
        invocation_origin=ActionInvocationOrigin.USER_TURN,
        input_payload={"scope": "profile", "key": "route", "value": "quiet"},
    )
    approval = ActionApprovalRecord(
        action_id=request.action_id,
        tool_name=request.tool_name,
        connector_id=request.connector_id,
        request_hash=request.request_hash,
        idempotency_key=request.idempotency_key,
        policy_decision=ActionPolicyDecision.REQUIRE_APPROVAL,
        approval_state=ActionApprovalState.PENDING,
        detail="operator_approval_required",
        request=request,
    )
    store.upsert(approval)

    reloaded = ApprovalStore(tmp_path)
    assert reloaded.pending_count() == 1
    assert reloaded.get_by_idempotency_key("idem_key") is not None


def test_approval_store_approve_removes_pending_and_persists(tmp_path):
    store = ApprovalStore(tmp_path)
    request = ActionRequestRecord(
        action_id="act_approval_resolve",
        request_hash="req_hash",
        idempotency_key="idem_key",
        tool_name="request_operator_help",
        connector_id="incident_local",
        risk_class=ActionRiskClass.OPERATOR_SENSITIVE_WRITE,
        invocation_origin=ActionInvocationOrigin.USER_TURN,
        input_payload={"participant_summary": "needs help"},
    )
    approval = ActionApprovalRecord(
        action_id=request.action_id,
        tool_name=request.tool_name,
        connector_id=request.connector_id,
        request_hash=request.request_hash,
        idempotency_key=request.idempotency_key,
        policy_decision=ActionPolicyDecision.REQUIRE_APPROVAL,
        approval_state=ActionApprovalState.PENDING,
        detail="operator_approval_required",
        request=request,
    )
    store.upsert(approval)

    approved = store.approve(request.action_id, operator_note="approved in test")

    assert approved is not None
    assert approved.approval_state == ActionApprovalState.APPROVED
    assert approved.operator_note == "approved in test"
    reloaded = ApprovalStore(tmp_path)
    assert reloaded.pending_count() == 0
    assert reloaded.get_by_action_id(request.action_id) is None


def test_connector_health_store_persists_defaults(tmp_path):
    store = ConnectorHealthStore(tmp_path, registry=ActionRegistry())
    records = {item.connector_id: item for item in store.list_records()}

    assert records["memory_local"].supported is True
    assert records["incident_local"].configured is True
    assert records["browser_runtime"].supported is False
    assert records["browser_runtime"].configured is False

    reloaded = ConnectorHealthStore(tmp_path, registry=ActionRegistry())
    assert {item.connector_id for item in reloaded.list_records()} == set(records)
