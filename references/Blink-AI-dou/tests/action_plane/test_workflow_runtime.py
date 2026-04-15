from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

from embodied_stack.action_plane import ActionPlaneGateway
from embodied_stack.action_plane.workflows import WorkflowRunStore, WorkflowRuntime
from embodied_stack.backends.router import BackendRouter
from embodied_stack.brain.agent_os import EmbodiedActionPolicy
from embodied_stack.brain.agent_os.tools import AgentToolRegistry, ToolRuntimeContext
from embodied_stack.brain.memory import MemoryStore
from embodied_stack.brain.tools import KnowledgeToolbox
from embodied_stack.config import Settings
from embodied_stack.shared.contracts import (
    ActionApprovalState,
    ActionExecutionRecord,
    ActionExecutionStatus,
    ActionInvocationOrigin,
    ActionPolicyDecision,
    ActionRequestRecord,
    ActionRiskClass,
    CompanionContextMode,
    EmbodiedWorldModel,
    ReminderRecord,
    SessionRecord,
    ShiftOperatingState,
    ShiftSupervisorSnapshot,
    WorkflowPauseReason,
    WorkflowRunActionRequestRecord,
    WorkflowRunActionResponseRecord,
    WorkflowRunRecord,
    WorkflowRunStatus,
    WorkflowStartRequestRecord,
    WorkflowStepKind,
    WorkflowStepRecord,
    WorkflowStepStatus,
    WorkflowTriggerKind,
    WorkflowTriggerRecord,
    WorldState,
)
from embodied_stack.shared.contracts._common import utc_now


def _build_workflow_harness(
    tmp_path: Path,
    *,
    browser_backend: str = "disabled",
    context_mode: CompanionContextMode = CompanionContextMode.PERSONAL_LOCAL,
    invocation_origin: ActionInvocationOrigin = ActionInvocationOrigin.USER_TURN,
):
    settings = Settings(
        _env_file=None,
        brain_store_path=str(tmp_path / "brain_store.json"),
        demo_report_dir=str(tmp_path / "demo_runs"),
        shift_report_dir=str(tmp_path / "shift_reports"),
        episode_export_dir=str(tmp_path / "episodes"),
        perception_frame_dir=str(tmp_path / "perception_frames"),
        brain_dialogue_backend="rule_based",
        brain_voice_backend="stub",
        blink_action_plane_browser_backend=browser_backend,
        blink_action_plane_browser_storage_dir=str(tmp_path / "browser"),
        blink_workflow_morning_briefing_time="09:00",
    )
    memory_store = MemoryStore(tmp_path / "brain_store.json")
    session = memory_store.ensure_session("workflow-session", user_id="visitor-1")
    router = BackendRouter(settings=settings)
    gateway = ActionPlaneGateway(root_dir=tmp_path / "actions", settings=settings)
    registry = AgentToolRegistry()
    workflow_runtime = WorkflowRuntime(
        root_dir=tmp_path / "actions",
        settings=settings,
        tool_registry=registry,
        action_gateway=gateway,
    )
    knowledge_tools = KnowledgeToolbox(settings=settings, memory_store=memory_store)
    context = ToolRuntimeContext(
        session=session,
        context_mode=context_mode,
        user_memory=None,
        world_state=WorldState(),
        world_model=EmbodiedWorldModel(),
        latest_perception=None,
        backend_status=router.runtime_statuses(),
        backend_profile=router.resolved_backend_profile(),
        body_driver_mode=settings.resolved_body_driver.value,
        body_transport_mode="preview_only",
        body_preview_status="preview_only",
        tool_invocations=[],
        action_policy=EmbodiedActionPolicy(settings=settings),
        run_id="workflow-test-run",
        action_invocation_origin=invocation_origin,
        action_gateway=gateway,
        workflow_runtime=workflow_runtime,
        knowledge_tools=knowledge_tools,
        memory_store=memory_store,
    )
    return SimpleNamespace(
        settings=settings,
        memory_store=memory_store,
        session=session,
        router=router,
        gateway=gateway,
        registry=registry,
        workflow_runtime=workflow_runtime,
        knowledge_tools=knowledge_tools,
        context=context,
    )


def test_workflow_contracts_round_trip():
    trigger = WorkflowTriggerRecord(
        trigger_kind=WorkflowTriggerKind.USER_REQUEST,
        trigger_key="manual:capture_note_and_reminder:test",
        source_session_id="workflow-session",
    )
    step = WorkflowStepRecord(
        step_id="capture_note_and_reminder:1",
        step_key="validate_inputs",
        label="Validate Inputs",
        kind=WorkflowStepKind.DETERMINISTIC_CHECK,
        status=WorkflowStepStatus.COMPLETED,
    )
    run = WorkflowRunRecord(
        workflow_run_id="wf_contract",
        workflow_id="capture_note_and_reminder",
        label="Capture Note And Reminder",
        status=WorkflowRunStatus.COMPLETED,
        trigger=trigger,
        session_id="workflow-session",
        steps=[step],
        summary="workflow_completed",
    )
    response = WorkflowRunActionResponseRecord(run=run, detail="workflow_completed")

    assert WorkflowTriggerRecord.model_validate_json(trigger.model_dump_json()) == trigger
    assert WorkflowStepRecord.model_validate_json(step.model_dump_json()) == step
    assert WorkflowRunRecord.model_validate_json(run.model_dump_json()) == run
    assert WorkflowRunActionResponseRecord.model_validate_json(response.model_dump_json()) == response


def test_workflow_store_persists_runs_trigger_state_and_artifacts(tmp_path: Path):
    store = WorkflowRunStore(tmp_path / "actions")
    trigger = WorkflowTriggerRecord(
        trigger_kind=WorkflowTriggerKind.USER_REQUEST,
        trigger_key="manual:test",
        source_session_id="workflow-session",
    )
    run = WorkflowRunRecord(
        workflow_run_id="wf_store",
        workflow_id="capture_note_and_reminder",
        label="Capture Note And Reminder",
        status=WorkflowRunStatus.RUNNING,
        trigger=trigger,
        session_id="workflow-session",
    )

    store.save_run(run)
    store.mark_trigger_seen(
        trigger_key="manual:test",
        workflow_id="capture_note_and_reminder",
        session_id="workflow-session",
        run_id=run.workflow_run_id,
    )
    artifact_dir = store.run_artifact_dir(run.workflow_run_id)

    reloaded = WorkflowRunStore(tmp_path / "actions")
    loaded = reloaded.get_run(run.workflow_run_id)

    assert loaded is not None
    assert loaded.workflow_id == "capture_note_and_reminder"
    assert reloaded.trigger_seen("manual:test") is True
    assert artifact_dir.is_dir()


def test_capture_note_and_reminder_workflow_completes_and_persists(tmp_path: Path):
    harness = _build_workflow_harness(tmp_path)

    record, output = harness.registry.invoke(
        "start_workflow",
        {
            "workflow_id": "capture_note_and_reminder",
            "inputs": {
                "note_title": "Bench Note",
                "note_content": "Remember the investor arrival window.",
                "note_tags": ["demo", "ops"],
                "reminder_text": "Prepare lobby greeting",
            },
        },
        context=harness.context,
    )

    assert record.success is True
    assert output is not None
    assert output.status == WorkflowRunStatus.COMPLETED
    assert output.summary == "Saved note 'Bench Note' and reminder 'Prepare lobby greeting'."
    run = harness.workflow_runtime.get_run(output.workflow_run_id)
    assert run is not None
    assert run.status == WorkflowRunStatus.COMPLETED
    assert run.state_payload["note_id"]
    assert run.state_payload["reminder_id"]
    assert run.state_payload["summary_path"]
    assert Path(run.state_payload["summary_path"]).exists()

    notes = harness.memory_store.list_companion_notes(session_id=harness.session.session_id, user_id=harness.session.user_id).items
    reminders = harness.memory_store.list_reminders(session_id=harness.session.session_id, user_id=harness.session.user_id, limit=10).items
    assert notes[0].title == "Bench Note"
    assert reminders[0].reminder_text == "Prepare lobby greeting"


def test_event_lookup_workflow_waits_for_approval_and_resumes_after_restart(tmp_path: Path):
    harness = _build_workflow_harness(tmp_path, browser_backend="stub")

    record, output = harness.registry.invoke(
        "start_workflow",
        {
            "workflow_id": "event_lookup_and_open_page",
            "inputs": {
                "target_url": "https://example.com",
                "requested_action": "type_text",
                "target_hint": {"label": "Search"},
                "text_input": "Blink concierge",
            },
        },
        context=harness.context,
    )

    assert record.success is True
    assert output is not None
    assert output.status == WorkflowRunStatus.WAITING_FOR_APPROVAL
    assert output.blocking_action_id is not None
    pending_action_id = output.blocking_action_id
    pending_execution = harness.gateway.get_execution(pending_action_id)
    assert pending_execution is not None
    assert pending_execution.workflow_run_id == output.workflow_run_id
    assert pending_execution.workflow_step_id is not None

    restarted_gateway = ActionPlaneGateway(root_dir=tmp_path / "actions", settings=harness.settings)
    restarted_registry = AgentToolRegistry()
    restarted_runtime = WorkflowRuntime(
        root_dir=tmp_path / "actions",
        settings=harness.settings,
        tool_registry=restarted_registry,
        action_gateway=restarted_gateway,
    )
    restarted_context = harness.context.__class__(
        **{
            **harness.context.__dict__,
            "action_gateway": restarted_gateway,
            "workflow_runtime": restarted_runtime,
        }
    )

    resolution = restarted_gateway.approve_action(
        action_id=pending_action_id,
        operator_note="approved in test",
        handler_context=restarted_context,
    )
    resumed = restarted_runtime.handle_action_resolution(resolution=resolution, tool_context=restarted_context)

    assert resolution.approval_state == ActionApprovalState.APPROVED
    assert resolution.execution is not None
    assert resolution.execution.status == ActionExecutionStatus.EXECUTED
    assert resumed is not None
    assert resumed.status == WorkflowRunStatus.COMPLETED
    run = restarted_runtime.get_run(output.workflow_run_id)
    assert run is not None
    assert run.status == WorkflowRunStatus.COMPLETED
    open_step = next(item for item in run.steps if item.step_key == "open_page")
    capture_step = next(item for item in run.steps if item.step_key == "capture_snapshot")
    follow_step = next(item for item in run.steps if item.step_key == "follow_up_browser_action")
    assert open_step.status == WorkflowStepStatus.COMPLETED
    assert capture_step.status == WorkflowStepStatus.COMPLETED
    assert open_step.attempt_count == 1
    assert capture_step.attempt_count == 1
    assert follow_step.status == WorkflowStepStatus.COMPLETED
    assert follow_step.action_ids[-1] == resolution.execution.action_id


def test_workflow_retry_replays_rejected_step_with_new_action_id(tmp_path: Path):
    harness = _build_workflow_harness(tmp_path, browser_backend="stub")

    record, output = harness.registry.invoke(
        "start_workflow",
        {
            "workflow_id": "event_lookup_and_open_page",
            "inputs": {
                "target_url": "https://example.com",
                "requested_action": "type_text",
                "target_hint": {"label": "Search"},
                "text_input": "Retry me",
            },
        },
        context=harness.context,
    )

    assert record.success is True
    assert output is not None
    first_action_id = output.blocking_action_id
    assert first_action_id is not None

    rejected = harness.gateway.reject_action(
        action_id=first_action_id,
        operator_note="not yet",
        handler_context=harness.context,
    )
    rejected_response = harness.workflow_runtime.handle_action_resolution(
        resolution=rejected,
        tool_context=harness.context,
    )

    assert rejected.approval_state == ActionApprovalState.REJECTED
    assert rejected_response is not None
    assert rejected_response.pause_reason == WorkflowPauseReason.APPROVAL_REJECTED

    operator_context = harness.context.__class__(
        **{
            **harness.context.__dict__,
            "action_invocation_origin": ActionInvocationOrigin.OPERATOR_CONSOLE,
        }
    )
    retried = harness.workflow_runtime.retry_workflow_step(
        workflow_run_id=output.workflow_run_id,
        request=WorkflowRunActionRequestRecord(note="retry as operator"),
        tool_context=operator_context,
    )

    assert retried.status == WorkflowRunStatus.COMPLETED
    run = harness.workflow_runtime.get_run(output.workflow_run_id)
    assert run is not None
    follow_step = next(item for item in run.steps if item.step_key == "follow_up_browser_action")
    assert len(follow_step.action_ids) == 2
    assert follow_step.action_ids[0] == first_action_id
    assert follow_step.action_ids[1] != first_action_id


def test_workflow_trigger_evaluation_respects_quiet_hours_and_context_mode(tmp_path: Path):
    morning_now = utc_now().astimezone(timezone.utc).replace(hour=1, minute=5, second=0, microsecond=0)
    personal = _build_workflow_harness(
        tmp_path / "personal",
        browser_backend="stub",
        context_mode=CompanionContextMode.PERSONAL_LOCAL,
        invocation_origin=ActionInvocationOrigin.PROACTIVE_RUNTIME,
    )
    personal.memory_store.upsert_reminder(
        ReminderRecord(
            session_id=personal.session.session_id,
            user_id=personal.session.user_id,
            reminder_text="Morning follow up",
            due_at=morning_now - timedelta(minutes=10),
        )
    )
    quiet_snapshot = ShiftSupervisorSnapshot(
        state=ShiftOperatingState.QUIET_HOURS,
        quiet_hours_active=True,
    )
    active_snapshot = ShiftSupervisorSnapshot(
        state=ShiftOperatingState.READY_IDLE,
        quiet_hours_active=False,
    )

    assert personal.workflow_runtime.evaluate_due_triggers(
        tool_context=personal.context,
        shift_snapshot=quiet_snapshot,
        now=morning_now,
    ) == []

    personal_results = personal.workflow_runtime.evaluate_due_triggers(
        tool_context=personal.context,
        shift_snapshot=active_snapshot,
        now=morning_now,
    )
    personal_ids = {item.workflow_id for item in personal_results}
    assert {"morning_briefing", "reminder_due_follow_up"} <= personal_ids
    assert all(item.status == WorkflowRunStatus.COMPLETED for item in personal_results)

    venue = _build_workflow_harness(
        tmp_path / "venue",
        browser_backend="stub",
        context_mode=CompanionContextMode.VENUE_DEMO,
        invocation_origin=ActionInvocationOrigin.PROACTIVE_RUNTIME,
    )
    venue.memory_store.upsert_reminder(
        ReminderRecord(
            session_id=venue.session.session_id,
            user_id=venue.session.user_id,
            reminder_text="Venue due reminder",
            due_at=morning_now - timedelta(minutes=10),
        )
    )
    venue_results = venue.workflow_runtime.evaluate_due_triggers(
        tool_context=venue.context,
        shift_snapshot=active_snapshot,
        now=morning_now,
    )
    assert venue_results
    assert all(item.status == WorkflowRunStatus.SUGGESTED for item in venue_results)


def test_restart_reconciliation_marks_uncertain_actions_and_pauses_workflows(tmp_path: Path):
    harness = _build_workflow_harness(tmp_path, browser_backend="stub")
    action_id = "act_uncertain"
    request = ActionRequestRecord(
        action_id=action_id,
        request_hash="request_hash",
        idempotency_key="idempotency_key",
        tool_name="browser_task",
        action_name="type_text",
        connector_id="browser_runtime",
        risk_class=ActionRiskClass.OPERATOR_SENSITIVE_WRITE,
        invocation_origin=ActionInvocationOrigin.USER_TURN,
        session_id=harness.session.session_id,
        run_id=harness.context.run_id,
        workflow_run_id="wf_restart_review",
        workflow_step_id="follow_up_browser_action",
        input_payload={"requested_action": "type_text", "text_input": "Blink concierge"},
    )
    harness.gateway.execution_store.upsert(
        ActionExecutionRecord(
            action_id=action_id,
            tool_name=request.tool_name,
            action_name=request.action_name,
            connector_id=request.connector_id,
            request_hash=request.request_hash,
            idempotency_key=request.idempotency_key,
            risk_class=request.risk_class,
            invocation_origin=request.invocation_origin,
            policy_decision=ActionPolicyDecision.ALLOW,
            approval_state=ActionApprovalState.APPROVED,
            status=ActionExecutionStatus.EXECUTING,
            session_id=request.session_id,
            run_id=request.run_id,
            workflow_run_id=request.workflow_run_id,
            workflow_step_id=request.workflow_step_id,
            input_payload=request.input_payload,
        )
    )
    trigger = WorkflowTriggerRecord(
        trigger_kind=WorkflowTriggerKind.USER_REQUEST,
        trigger_key="manual:restart-review",
        source_session_id=harness.session.session_id,
    )
    run = WorkflowRunRecord(
        workflow_run_id="wf_restart_review",
        workflow_id="event_lookup_and_open_page",
        label="Event Lookup And Open Page",
        status=WorkflowRunStatus.RUNNING,
        trigger=trigger,
        session_id=harness.session.session_id,
        current_step_id="follow_up_browser_action",
        current_step_label="Optional Browser Follow Up",
        blocking_action_id=action_id,
        steps=[
            WorkflowStepRecord(
                step_id="event_lookup_and_open_page:follow_up_browser_action",
                step_key="follow_up_browser_action",
                label="Optional Browser Follow Up",
                kind=WorkflowStepKind.CONNECTOR_ACTION,
                status=WorkflowStepStatus.RUNNING,
                action_ids=[action_id],
                attempt_count=1,
            )
        ],
    )
    harness.workflow_runtime.store.save_run(run)

    harness.gateway.reconcile_restart_review()
    reconciled = harness.gateway.get_execution(action_id)
    assert reconciled is not None
    assert reconciled.status == ActionExecutionStatus.UNCERTAIN_REVIEW_REQUIRED

    updated_runs = harness.workflow_runtime.reconcile_restart_review()
    assert updated_runs
    updated = harness.workflow_runtime.get_run("wf_restart_review")
    assert updated is not None
    assert updated.status == WorkflowRunStatus.PAUSED
    assert updated.pause_reason == WorkflowPauseReason.RUNTIME_RESTART_REVIEW
    assert updated.blocking_action_id == action_id
    assert updated.steps[0].status == WorkflowStepStatus.FAILED
