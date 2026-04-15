from __future__ import annotations

from embodied_stack.brain.agent_os.hooks import HookRegistry, HookRuntimeState
from embodied_stack.brain.agent_os.models import AgentTurnContext, ReplyCandidatePlan
from embodied_stack.shared.models import AgentHookName, CompanionContextMode, EmbodiedWorldModel, RobotEvent, SessionRecord, WorldState


def _build_context() -> AgentTurnContext:
    return AgentTurnContext(
        text="Hello there",
        event=RobotEvent(
            event_type="speech_transcript",
            session_id="hook-session",
            source="test",
            payload={"text": "Hello there"},
        ),
        session=SessionRecord(session_id="hook-session"),
        context_mode=CompanionContextMode.PERSONAL_LOCAL,
        user_memory=None,
        world_state=WorldState(),
        world_model=EmbodiedWorldModel(),
        latest_perception=None,
        backend_status=[],
    )


def test_hook_registry_reports_all_required_lifecycle_hooks():
    registry = HookRegistry()

    assert set(registry.list_hook_names()) == {
        "before_skill_selection",
        "after_transcript",
        "after_perception",
        "before_tool_call",
        "after_tool_result",
        "before_reply",
        "before_reply_generation",
        "before_speak",
        "before_memory_write",
        "after_turn",
        "on_failure",
        "on_safe_idle",
        "on_provider_failure",
        "on_session_close",
    }


def test_hook_registry_executes_provider_failure_and_before_speak_hooks():
    registry = HookRegistry()
    context = _build_context()

    provider_failure_records = registry.run(
        AgentHookName.ON_PROVIDER_FAILURE,
        context=context,
        state=HookRuntimeState(
            active_skill_name="safe_degraded_response",
            provider_failure_active=True,
        ),
    )
    before_speak_records = registry.run(
        AgentHookName.BEFORE_SPEAK,
        context=context,
        state=HookRuntimeState(
            active_skill_name="wayfinding",
            validation_count=2,
            reply_candidate=ReplyCandidatePlan(
                reply_text="The front desk is in the lobby.",
                intent="wayfinding",
                engine_name="rule_based",
            ),
        ),
    )
    before_memory_write_records = registry.run(
        AgentHookName.BEFORE_MEMORY_WRITE,
        context=context,
        state=HookRuntimeState(
            active_skill_name="memory_follow_up",
            memory_write_requested=True,
        ),
    )

    assert provider_failure_records[0].hook_name == AgentHookName.ON_PROVIDER_FAILURE
    assert provider_failure_records[0].canonical_phase == AgentHookName.ON_FAILURE
    assert provider_failure_records[0].notes == ["failure_visible"]
    assert before_speak_records[0].hook_name == AgentHookName.BEFORE_SPEAK
    assert before_speak_records[0].action_type == "gate"
    assert before_speak_records[0].detail == "intent=wayfinding"
    assert before_speak_records[0].notes == ["validation_count=2"]
    assert before_memory_write_records[0].hook_name == AgentHookName.BEFORE_MEMORY_WRITE
    assert before_memory_write_records[0].gated is True
