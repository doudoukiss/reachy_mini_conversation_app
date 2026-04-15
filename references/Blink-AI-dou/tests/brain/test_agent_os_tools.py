from __future__ import annotations

from pathlib import Path

from embodied_stack.action_plane import ActionPlaneGateway
from embodied_stack.backends.router import BackendRouter
from embodied_stack.brain.agent_os import EmbodiedActionPolicy
from embodied_stack.brain.agent_os.tools import AgentToolRegistry, ToolRuntimeContext
from embodied_stack.brain.agent_os.subagents import SubagentRegistry
from embodied_stack.brain.agent_os.skills import SkillRegistry
from embodied_stack.brain.memory import MemoryStore
from embodied_stack.brain.tools import KnowledgeToolbox
from embodied_stack.shared.contracts import (
    ActionApprovalState,
    ActionExecutionStatus,
    ActionInvocationOrigin,
    CompanionContextMode,
    CompanionNoteRecord,
    EmbodiedWorldModel,
    EpisodicMemoryRecord,
    MemoryWriteReasonCode,
    ProceduralMemoryRecord,
    ReminderRecord,
    RelationshipMemoryRecord,
    RelationshipThreadKind,
    RelationshipThreadRecord,
    RelationshipTopicRecord,
    SessionDigestRecord,
    SessionRecord,
    ToolPermissionClass,
    ToolResultStatus,
    UserMemoryRecord,
    WorldState,
)


def _tool_context(
    settings,
    *,
    knowledge_tools: KnowledgeToolbox | None = None,
    user_memory: UserMemoryRecord | None = None,
    memory_store: MemoryStore | None = None,
    session: SessionRecord | None = None,
    action_gateway: ActionPlaneGateway | None = None,
    invocation_origin: ActionInvocationOrigin = ActionInvocationOrigin.USER_TURN,
    run_id: str | None = "test-run",
) -> ToolRuntimeContext:
    router = BackendRouter(settings=settings)
    return ToolRuntimeContext(
        session=session or SessionRecord(session_id="tool-session"),
        context_mode=CompanionContextMode.PERSONAL_LOCAL,
        user_memory=user_memory,
        world_state=WorldState(),
        world_model=EmbodiedWorldModel(),
        latest_perception=None,
        backend_status=router.runtime_statuses(),
        backend_profile=router.resolved_backend_profile(),
        body_driver_mode=settings.resolved_body_driver.value,
        body_transport_mode=(
            settings.blink_serial_transport
            if settings.resolved_body_driver.value == "serial"
            else ("virtual_preview" if settings.resolved_body_driver.value == "virtual" else "preview_only")
        ),
        body_preview_status=(
            "live"
            if settings.resolved_body_driver.value == "serial" and settings.blink_serial_transport == "live_serial"
            else (
                settings.blink_serial_transport
                if settings.resolved_body_driver.value == "serial"
                else ("virtual_preview" if settings.resolved_body_driver.value == "virtual" else "preview_only")
            )
        ),
        tool_invocations=[],
        action_policy=EmbodiedActionPolicy(settings=settings),
        run_id=run_id,
        action_invocation_origin=invocation_origin,
        action_gateway=action_gateway,
        knowledge_tools=knowledge_tools,
        memory_store=memory_store,
    )


def test_tool_registry_exposes_protocol_metadata():
    registry = AgentToolRegistry()
    specs = {item.name: item for item in registry.list_tool_specs()}

    assert specs["system_health"].permission_class == ToolPermissionClass.READ_ONLY
    assert specs["system_health"].capability_name == "system_health"
    assert specs["system_health"].family == "system"
    assert specs["body_command"].checkpoint_policy == "before_and_after"
    assert specs["request_operator_help"].permission_class == ToolPermissionClass.OPERATOR_SENSITIVE
    assert specs["browser_task"].capability_name == "browser_task"
    assert specs["start_workflow"].family == "workflow"


def test_subagent_registry_selects_primary_memory_surface():
    skills = SkillRegistry()
    subagents = SubagentRegistry()

    skill = skills.activate_named("memory_follow_up", reason="test")
    subagent = subagents.resolve(skill)

    assert subagent.name == "memory_curator"
    assert "write_memory" in subagent.allowed_tools


def test_tool_registry_rejects_invalid_memory_retrieval_payload(settings):
    registry = AgentToolRegistry()
    record, output = registry.invoke(
        "memory_retrieval",
        {},
        context=_tool_context(settings),
    )

    assert record.success is False
    assert record.validation.schema_valid is False
    assert output is None


def test_tool_registry_returns_runtime_status_with_valid_schema(settings):
    registry = AgentToolRegistry()
    record, output = registry.invoke(
        "runtime_status",
        {},
        context=_tool_context(settings),
    )

    assert record.success is True
    assert record.capability_name == "system_health"
    assert record.result_status.value == "ok"
    assert record.validation.schema_valid is True
    assert record.validation.output_valid is True
    assert output is not None
    assert output.backend_profile == "companion_live"
    assert output.text_backend == "rule_based"


def test_tool_registry_converts_handler_exception_into_failure_record(settings):
    registry = AgentToolRegistry()
    spec = registry.resolve_spec("runtime_status")
    original_handler = spec.handler
    object.__setattr__(spec, "handler", lambda model, context: (_ for _ in ()).throw(RuntimeError("fixture_tool_crash")))

    try:
        record, output = registry.invoke(
            "runtime_status",
            {},
            context=_tool_context(settings),
        )
    finally:
        object.__setattr__(spec, "handler", original_handler)

    assert record.success is False
    assert record.error_code == "tool_runtime_error"
    assert record.validation.output_valid is False
    assert record.validation.detail == "tool_runtime_error"
    assert "RuntimeError:fixture_tool_crash" in (record.error_detail or "")
    assert output is None


def test_browser_task_reports_honest_unsupported_state(settings):
    registry = AgentToolRegistry()
    record, output = registry.invoke(
        "browser_task",
        {"query": "Open the local calendar"},
        context=_tool_context(settings),
    )

    assert record.success is False
    assert record.capability_name == "browser_task"
    assert record.result_status.value == "unsupported"
    assert record.capability_state.value == "unsupported"
    assert record.error_code == "browser_task_unsupported"
    assert output is not None
    assert output.supported is False
    assert output.configured is False


def test_browser_task_stub_open_url_returns_snapshot_and_artifacts(settings, tmp_path: Path):
    browser_settings = settings.model_copy(
        update={
            "blink_action_plane_browser_backend": "stub",
            "blink_action_plane_browser_storage_dir": str(tmp_path / "browser"),
        }
    )
    registry = AgentToolRegistry()
    gateway = ActionPlaneGateway(root_dir=tmp_path / "actions", settings=browser_settings)

    record, output = registry.invoke(
        "browser_task",
        {
            "query": "Open example.com",
            "target_url": "https://example.com",
            "requested_action": "open_url",
        },
        context=_tool_context(browser_settings, action_gateway=gateway),
    )

    assert record.success is True
    assert record.result_status == ToolResultStatus.OK
    assert output is not None
    assert output.supported is True
    assert output.configured is True
    assert output.status == "ok"
    assert output.current_url == "https://example.com"
    assert output.snapshot is not None
    assert output.snapshot.screenshot_path is not None
    assert Path(output.snapshot.screenshot_path).exists()
    assert output.result is not None
    assert output.result.result_path is not None
    assert Path(output.result.result_path).exists()


def test_browser_task_effectful_action_requires_approval_for_user_turn(settings, tmp_path: Path):
    browser_settings = settings.model_copy(
        update={
            "blink_action_plane_browser_backend": "stub",
            "blink_action_plane_browser_storage_dir": str(tmp_path / "browser"),
        }
    )
    registry = AgentToolRegistry()
    gateway = ActionPlaneGateway(root_dir=tmp_path / "actions", settings=browser_settings)
    context = _tool_context(browser_settings, action_gateway=gateway)

    open_record, _open_output = registry.invoke(
        "browser_task",
        {
            "query": "Open example.com",
            "target_url": "https://example.com",
            "requested_action": "open_url",
        },
        context=context,
    )
    assert open_record.success is True

    preview_context = _tool_context(
        browser_settings,
        action_gateway=gateway,
        session=context.session,
        invocation_origin=ActionInvocationOrigin.USER_TURN,
    )
    record, output = registry.invoke(
        "browser_task",
        {
            "query": "Type into the search field",
            "requested_action": "type_text",
            "target_hint": {"label": "Search"},
            "text_input": "Blink concierge",
        },
        context=preview_context,
    )

    assert record.success is False
    assert record.result_status == ToolResultStatus.BLOCKED
    assert record.action_status == ActionExecutionStatus.PENDING_APPROVAL
    assert record.approval_state == ActionApprovalState.PENDING
    assert output is not None
    assert output.preview_required is True
    assert output.preview is not None
    assert output.preview.preview_path is not None
    assert Path(output.preview.preview_path).exists()
    assert output.preview.resolved_target is not None
    assert output.preview.resolved_target.label == "Search"


def test_memory_retrieval_tool_returns_layered_hits(settings, tmp_path):
    store = MemoryStore(tmp_path / "brain_store.json")
    user_memory = UserMemoryRecord(
        user_id="visitor-1",
        display_name="Alex",
        preferences={"route_preference": "quiet route"},
    )
    store.upsert_user_memory(user_memory)
    store.upsert_episodic_memory(
        EpisodicMemoryRecord(
            memory_id="session-1",
            session_id="session-1",
            user_id="visitor-1",
            title="wayfinding",
            summary="we discussed directions to the workshop room.",
            topics=["wayfinding", "workshop_room"],
        )
    )
    knowledge_tools = KnowledgeToolbox(settings=settings, memory_store=store)
    registry = AgentToolRegistry()

    record, output = registry.invoke(
        "memory_retrieval",
        {"query": "What did we talk about last time?"},
        context=_tool_context(settings, knowledge_tools=knowledge_tools, user_memory=user_memory),
    )

    assert record.success is True
    assert output is not None
    assert output.profile_summary is not None
    assert output.episodic_hits
    assert output.episodic_hits[0].memory_id == "session-1"
    assert output.episodic_hits[0].ranking_reason == "episodic_keyword_match"
    assert output.retrievals
    assert any(item.backend == "episodic_keyword" for item in output.retrievals)


def test_memory_retrieval_tool_surfaces_relationship_and_procedural_layers(settings, tmp_path):
    store = MemoryStore(tmp_path / "brain_store.json")
    user_memory = UserMemoryRecord(user_id="visitor-1", display_name="Alex")
    store.upsert_user_memory(user_memory)
    store.upsert_relationship_memory(
        RelationshipMemoryRecord(
            relationship_id="visitor-1",
            user_id="visitor-1",
            familiarity=0.7,
            recurring_topics=[RelationshipTopicRecord(topic="investor_demo", mention_count=2)],
            open_threads=[
                RelationshipThreadRecord(
                    kind=RelationshipThreadKind.PRACTICAL,
                    summary="Resume the investor demo rehearsal.",
                    follow_up_requested=True,
                )
            ],
        )
    )
    store.upsert_procedural_memory(
        ProceduralMemoryRecord(
            user_id="visitor-1",
            session_id="tool-session",
            name="planning routine",
            summary="For planning, give one step at a time.",
            trigger_phrases=["planning"],
            steps=["give one step at a time"],
        )
    )
    knowledge_tools = KnowledgeToolbox(settings=settings, memory_store=store)
    registry = AgentToolRegistry()

    record, output = registry.invoke(
        "memory_retrieval",
        {"query": "Can we pick up the investor demo and use the planning routine?"},
        context=_tool_context(settings, knowledge_tools=knowledge_tools, user_memory=user_memory),
    )

    assert record.success is True
    assert output is not None
    assert output.relationship_summary is not None
    assert output.relationship_hits
    assert output.relationship_hits[0].layer == "relationship"
    assert output.procedural_hits
    assert output.procedural_hits[0].layer == "procedural"
    assert any(item.backend == "relationship_runtime" for item in output.retrievals)
    assert any(item.backend == "procedural_match" for item in output.retrievals)


def test_daily_use_tools_return_local_notes_reminders_and_digest(settings, tmp_path):
    store = MemoryStore(tmp_path / "brain_store.json")
    user_memory = UserMemoryRecord(user_id="visitor-1", display_name="Alex")
    store.upsert_user_memory(user_memory)
    store.upsert_reminder(
        ReminderRecord(
            session_id="tool-session",
            user_id="visitor-1",
            reminder_text="bring the badge",
        )
    )
    store.upsert_companion_note(
        CompanionNoteRecord(
            session_id="tool-session",
            user_id="visitor-1",
            title="Investor demo",
            content="Finish the investor demo script.",
            tags=["workspace"],
        )
    )
    store.upsert_session_digest(
        SessionDigestRecord(
            session_id="tool-session",
            user_id="visitor-1",
            summary="We reviewed the investor demo flow and left one follow-up.",
            turn_count=8,
            open_follow_ups=["bring the badge"],
        )
    )
    knowledge_tools = KnowledgeToolbox(settings=settings, memory_store=store)
    registry = AgentToolRegistry()

    note_record, note_output = registry.invoke(
        "local_notes",
        {"query": "What notes do I have?"},
        context=_tool_context(settings, knowledge_tools=knowledge_tools, user_memory=user_memory),
    )
    reminder_record, reminder_output = registry.invoke(
        "personal_reminders",
        {"query": "What reminders do I have?"},
        context=_tool_context(settings, knowledge_tools=knowledge_tools, user_memory=user_memory),
    )
    digest_record, digest_output = registry.invoke(
        "recent_session_digest",
        {"session_id": "tool-session"},
        context=_tool_context(settings, knowledge_tools=knowledge_tools, user_memory=user_memory),
    )

    assert note_record.success is True
    assert note_output is not None
    assert note_output.notes[0].title == "Investor demo"
    assert reminder_record.success is True
    assert reminder_output is not None
    assert reminder_output.reminders[0].reminder_text == "bring the badge"
    assert digest_record.success is True
    assert digest_output is not None
    assert "investor demo flow" in (digest_output.summary or "")


def test_memory_tools_route_writes_through_policy_service(settings, tmp_path):
    store = MemoryStore(tmp_path / "brain_store.json")
    session = store.ensure_session("tool-session", user_id="visitor-1")
    user_memory = UserMemoryRecord(user_id="visitor-1", display_name="Alex")
    store.upsert_user_memory(user_memory)
    registry = AgentToolRegistry()

    write_record, write_output = registry.invoke(
        "write_memory",
        {
            "scope": "profile",
            "key": "preferred_route",
            "value": "quiet route",
            "reason_code": MemoryWriteReasonCode.PROFILE_PREFERENCE.value,
        },
        context=_tool_context(
            settings,
            user_memory=user_memory,
            memory_store=store,
            session=session,
        ),
    )
    promote_record, promote_output = registry.invoke(
        "promote_memory",
        {
            "scope": "semantic",
            "summary": "Alex prefers the quiet route.",
            "memory_kind": "route_preference",
            "canonical_value": "quiet route",
            "reason_code": MemoryWriteReasonCode.CONVERSATION_TOPIC.value,
        },
        context=_tool_context(
            settings,
            user_memory=user_memory,
            memory_store=store,
            session=session,
        ),
    )

    assert write_record.success is True
    assert write_output is not None
    assert write_output.persisted is True
    assert write_output.action_id is not None
    assert store.get_user_memory("visitor-1").facts["preferred_route"] == "quiet route"

    assert promote_record.success is True
    assert promote_output is not None
    assert promote_output.promoted is True
    assert promote_output.action_id is not None
    assert store.list_memory_actions(session_id="tool-session").items


def test_action_plane_allows_session_memory_write_and_deduplicates(settings, tmp_path):
    store = MemoryStore(tmp_path / "brain_store.json")
    session = store.ensure_session("tool-session", user_id="visitor-1")
    gateway = ActionPlaneGateway(root_dir=tmp_path / "actions")
    registry = AgentToolRegistry()

    context = _tool_context(
        settings,
        memory_store=store,
        session=session,
        action_gateway=gateway,
        run_id="run-dedupe",
    )
    first_record, first_output = registry.invoke(
        "write_memory",
        {"scope": "session", "key": "last_topic", "value": "robotics"},
        context=context,
    )
    second_record, second_output = registry.invoke(
        "write_memory",
        {"scope": "session", "key": "last_topic", "value": "robotics"},
        context=context,
    )

    assert first_record.success is True
    assert first_output is not None
    assert first_output.persisted is True
    assert first_record.action_status == ActionExecutionStatus.EXECUTED
    assert first_record.action_id is not None
    assert second_record.success is True
    assert second_record.action_status == ActionExecutionStatus.REUSED
    assert second_record.summary == "reused_result"
    assert second_record.idempotency_key == first_record.idempotency_key
    assert store.get_session("tool-session").session_memory["last_topic"] == "robotics"


def test_action_plane_profile_write_requires_approval_and_survives_restart(settings, tmp_path):
    store = MemoryStore(tmp_path / "brain_store.json")
    session = store.ensure_session("tool-session", user_id="visitor-1")
    user_memory = UserMemoryRecord(user_id="visitor-1", display_name="Alex")
    store.upsert_user_memory(user_memory)
    gateway = ActionPlaneGateway(root_dir=tmp_path / "actions")
    registry = AgentToolRegistry()

    record, output = registry.invoke(
        "write_memory",
        {
            "scope": "profile",
            "key": "preferred_route",
            "value": "quiet route",
            "reason_code": MemoryWriteReasonCode.PROFILE_PREFERENCE.value,
        },
        context=_tool_context(
            settings,
            user_memory=user_memory,
            memory_store=store,
            session=session,
            action_gateway=gateway,
            run_id="run-approval",
        ),
    )

    assert record.success is False
    assert record.result_status == ToolResultStatus.BLOCKED
    assert record.approval_state == ActionApprovalState.PENDING
    assert record.action_status == ActionExecutionStatus.PENDING_APPROVAL
    assert output is not None
    assert output.persisted is False
    assert store.get_user_memory("visitor-1").facts == {}

    restarted_gateway = ActionPlaneGateway(root_dir=tmp_path / "actions")
    status = restarted_gateway.status()
    assert status.pending_approval_count == 1
    assert status.pending_approvals[0].action_id == record.action_id


def test_action_plane_proactive_write_downgrades_to_preview_only(settings, tmp_path):
    store = MemoryStore(tmp_path / "brain_store.json")
    session = store.ensure_session("tool-session", user_id="visitor-1")
    gateway = ActionPlaneGateway(root_dir=tmp_path / "actions")
    registry = AgentToolRegistry()

    record, output = registry.invoke(
        "promote_memory",
        {"scope": "semantic", "summary": "Alex likes calm music.", "memory_kind": "music_preference"},
        context=_tool_context(
            settings,
            memory_store=store,
            session=session,
            action_gateway=gateway,
            invocation_origin=ActionInvocationOrigin.PROACTIVE_RUNTIME,
            run_id="run-preview",
        ),
    )

    assert record.success is False
    assert record.result_status == ToolResultStatus.DEGRADED
    assert record.action_status == ActionExecutionStatus.PREVIEW_ONLY
    assert output is not None
    assert output.promoted is False
    assert store.list_semantic_memory(session_id="tool-session").items == []


def test_action_plane_routes_incident_tools_and_adds_metadata(settings, tmp_path):
    store = MemoryStore(tmp_path / "brain_store.json")
    session = store.ensure_session("tool-session", user_id="visitor-1")
    gateway = ActionPlaneGateway(root_dir=tmp_path / "actions")
    registry = AgentToolRegistry()

    record, output = registry.invoke(
        "log_incident",
        {"participant_summary": "visitor needs assistance", "note": "skill=test"},
        context=_tool_context(
            settings,
            memory_store=store,
            session=session,
            action_gateway=gateway,
            invocation_origin=ActionInvocationOrigin.OPERATOR_CONSOLE,
            run_id="run-incident",
        ),
    )

    assert record.success is True
    assert record.connector_id == "incident_local"
    assert record.approval_state == ActionApprovalState.IMPLICIT_OPERATOR_APPROVAL
    assert record.action_status == ActionExecutionStatus.EXECUTED
    assert record.action_id is not None
    assert record.request_hash is not None
    assert record.idempotency_key is not None
    assert output is not None
    assert output.requested is True
    assert store.list_incident_tickets().items


def test_action_plane_browser_task_rejects_unconfigured_connector_honestly(settings, tmp_path):
    gateway = ActionPlaneGateway(root_dir=tmp_path / "actions")
    registry = AgentToolRegistry()

    record, output = registry.invoke(
        "browser_task",
        {"query": "Open the local calendar"},
        context=_tool_context(settings, action_gateway=gateway, run_id="run-browser"),
    )

    assert record.success is False
    assert record.action_status == ActionExecutionStatus.REJECTED
    assert record.connector_id == "browser_runtime"
    assert record.result_status == ToolResultStatus.UNSUPPORTED
    assert output is not None
    assert output.supported is False
    assert output.configured is False


def test_body_preview_reports_canonical_semantics_and_transport_mode(settings):
    registry = AgentToolRegistry()
    record, output = registry.invoke(
        "body_preview",
        {"intent": "greeting", "reply_text": None},
        context=_tool_context(settings),
    )

    assert record.success is True
    assert output is not None
    assert output.previews
    assert output.previews[0].driver_mode == settings.resolved_body_driver.value
    assert output.previews[0].preview_status is not None
    assert any(item.semantic_name == "friendly" for item in output.previews)
    assert any(item.semantic_name == "look_at_user" for item in output.previews)


def test_stage_b_connector_tools_execute_through_action_plane(settings, tmp_path):
    settings = settings.model_copy(
        update={
            "blink_action_plane_local_file_roots": str(tmp_path),
            "blink_action_plane_stage_dir": str(tmp_path / "staged"),
            "blink_action_plane_export_dir": str(tmp_path / "exports"),
            "blink_action_plane_draft_dir": str(tmp_path / "drafts"),
        }
    )
    store = MemoryStore(tmp_path / "brain_store.json")
    session = store.ensure_session("tool-session", user_id="visitor-1")
    user_memory = UserMemoryRecord(user_id="visitor-1", display_name="Alex")
    store.upsert_user_memory(user_memory)
    knowledge_tools = KnowledgeToolbox(settings=settings, memory_store=store)
    gateway = ActionPlaneGateway(root_dir=tmp_path / "actions", settings=settings)
    registry = AgentToolRegistry()
    context = _tool_context(
        settings,
        knowledge_tools=knowledge_tools,
        user_memory=user_memory,
        memory_store=store,
        session=session,
        action_gateway=gateway,
    )
    in_root = tmp_path / "sample.txt"
    in_root.write_text("connector runtime file", encoding="utf-8")
    outside_root = tmp_path.parent / "outside.txt"
    outside_root.write_text("should be blocked", encoding="utf-8")

    note_record, note_output = registry.invoke(
        "create_note",
        {"title": "Bench note", "content": "Validate connectors", "tags": ["bench"]},
        context=context,
    )
    reminder_record, reminder_output = registry.invoke(
        "create_reminder",
        {"reminder_text": "Bring badge"},
        context=context,
    )
    file_record, file_output = registry.invoke(
        "read_local_file",
        {"path": str(in_root)},
        context=context,
    )
    blocked_record, blocked_output = registry.invoke(
        "read_local_file",
        {"path": str(outside_root)},
        context=context,
    )
    calendar_record, calendar_output = registry.invoke(
        "draft_calendar_event",
        {"title": "Lobby coverage", "start_at": "2026-04-08T09:00:00Z"},
        context=context,
    )

    assert note_record.success is True
    assert note_record.connector_id == "notes_local"
    assert note_output is not None
    assert note_output.created is True
    assert reminder_record.success is True
    assert reminder_record.connector_id == "reminders_local"
    assert reminder_output is not None
    assert reminder_output.created is True
    assert file_record.success is True
    assert file_record.connector_id == "local_files"
    assert file_output is not None
    assert "connector runtime file" in file_output.content
    assert blocked_record.success is False
    assert blocked_record.action_status == ActionExecutionStatus.FAILED
    assert blocked_output is not None
    assert blocked_output.path == str(outside_root)
    assert calendar_record.success is True
    assert calendar_record.connector_id == "calendar_local"
    assert calendar_output is not None
    assert calendar_output.drafted is True
