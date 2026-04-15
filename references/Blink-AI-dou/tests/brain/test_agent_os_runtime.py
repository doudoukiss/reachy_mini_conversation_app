from __future__ import annotations

from embodied_stack.backends.router import BackendRouter
from embodied_stack.brain.agent_os import AgentRuntime, EmbodiedActionPolicy
from embodied_stack.brain.agent_os.models import AgentTurnContext
from embodied_stack.brain.llm import DialogueResult
from embodied_stack.brain.memory import MemoryStore
from embodied_stack.brain.tools import KnowledgeToolbox
from embodied_stack.shared.contracts import (
    AgentValidationStatus,
    CompanionContextMode,
    EmbodiedWorldModel,
    PerceptionProviderMode,
    PerceptionSnapshotRecord,
    PerceptionSourceFrame,
    RobotEvent,
    RunStatus,
    SessionRecord,
    WorldState,
)


class _VisualOverclaimDialogueEngine:
    def generate_reply(self, text, context):
        del text, context
        return DialogueResult(
            reply_text="I can see a visitor near the sign.",
            intent="perception_query",
            debug_notes=["test_visual_overclaim"],
            engine_name="test_dialogue_engine",
        )


def test_agent_runtime_downgrades_visual_overclaim_under_limited_awareness(settings):
    router = BackendRouter(settings=settings)
    runtime = AgentRuntime(
        settings=settings,
        backend_router=router,
        knowledge_tools=KnowledgeToolbox(
            settings=settings,
            embedding_backend=router.build_embedding_backend(),
        ),
        dialogue_engine=_VisualOverclaimDialogueEngine(),
        action_policy=EmbodiedActionPolicy(settings=settings),
    )
    context = AgentTurnContext(
        text="What can you see?",
        event=RobotEvent(
            event_type="speech_transcript",
            session_id="runtime-session",
            payload={"text": "What can you see?"},
            source="test",
        ),
        session=SessionRecord(session_id="runtime-session"),
        context_mode=CompanionContextMode.PERSONAL_LOCAL,
        user_memory=None,
        world_state=WorldState(),
        world_model=EmbodiedWorldModel(),
        latest_perception=PerceptionSnapshotRecord(
            session_id="runtime-session",
            provider_mode=PerceptionProviderMode.STUB,
            limited_awareness=True,
            source_frame=PerceptionSourceFrame(source_kind="test_frame"),
        ),
        backend_status=router.runtime_statuses(),
    )

    plan = runtime.plan_speech_turn(
        context=context,
        tool_invocations=[],
        memory_updates={},
    )

    assert plan.reply_text is not None
    assert plan.reply_text.startswith("My current visual awareness is limited")
    assert any(
        outcome.validator_name == "perception_honesty_policy"
        and outcome.status == AgentValidationStatus.DOWNGRADED
        for outcome in plan.validation_outcomes
    )
    assert any(record.hook_name == "before_speak" for record in plan.hook_records)


def test_agent_runtime_persists_runs_and_checkpoints_for_effectful_tools(settings, tmp_path):
    router = BackendRouter(settings=settings)
    memory = MemoryStore(tmp_path / "brain_store.json")
    runtime = AgentRuntime(
        settings=settings,
        backend_router=router,
        knowledge_tools=KnowledgeToolbox(
            settings=settings,
            embedding_backend=router.build_embedding_backend(),
            memory_store=memory,
        ),
        dialogue_engine=router.build_dialogue_engine(),
        action_policy=EmbodiedActionPolicy(settings=settings),
        memory_store=memory,
    )
    context = AgentTurnContext(
        text="I need human help with accessibility support.",
        event=RobotEvent(
            event_type="speech_transcript",
            session_id="runtime-incident",
            payload={"text": "I need human help with accessibility support."},
            source="test",
        ),
        session=SessionRecord(session_id="runtime-incident"),
        context_mode=CompanionContextMode.PERSONAL_LOCAL,
        user_memory=None,
        world_state=WorldState(),
        world_model=EmbodiedWorldModel(),
        latest_perception=None,
        backend_status=router.runtime_statuses(),
    )

    plan = runtime.plan_speech_turn(context=context, tool_invocations=[], memory_updates={})

    assert plan.run_record is not None
    assert plan.run_record.status == RunStatus.COMPLETED
    assert plan.active_subagent == "operator_handoff_planner"
    assert plan.checkpoints
    request_help_calls = [item for item in plan.typed_tool_calls if item.tool_name == "request_operator_help"]
    assert request_help_calls
    assert any(item.before_checkpoint_id for item in request_help_calls)
    assert request_help_calls[0].action_id is not None
    assert request_help_calls[0].connector_id == "incident_local"
    assert runtime.list_runs(session_id="runtime-incident").items[0].run_id == plan.run_record.run_id
    checkpoints = runtime.list_checkpoints(run_id=plan.run_record.run_id).items
    assert checkpoints
    tool_before = next(item for item in checkpoints if item.kind == "tool_before" and item.tool_name == "request_operator_help")
    tool_after = next(item for item in checkpoints if item.kind == "tool_after" and item.tool_name == "request_operator_help")
    assert tool_before.payload["_action_plane"]["routed"] is True
    assert tool_after.result_payload["_action_plane"]["action_id"] == request_help_calls[0].action_id
