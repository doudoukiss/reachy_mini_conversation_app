from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from embodied_stack.shared.models import AgentHookName, HookExecutionRecord

from .models import AgentTurnContext, AgentTurnPlan, ReplyCandidatePlan


@dataclass(frozen=True)
class HookRuntimeState:
    active_skill_name: str | None = None
    active_subagent_name: str | None = None
    tool_count: int = 0
    validation_count: int = 0
    memory_write_requested: bool = False
    provider_failure_active: bool = False
    safe_idle_active: bool = False
    reply_candidate: ReplyCandidatePlan | None = None
    final_plan: AgentTurnPlan | None = None
    run_id: str | None = None
    checkpoint_id: str | None = None


HookHandler = Callable[[AgentTurnContext, HookRuntimeState], HookExecutionRecord]


class HookRegistry:
    _CANONICAL_HOOKS: tuple[AgentHookName, ...] = (
        AgentHookName.BEFORE_SKILL_SELECTION,
        AgentHookName.AFTER_TRANSCRIPT,
        AgentHookName.AFTER_PERCEPTION,
        AgentHookName.BEFORE_TOOL_CALL,
        AgentHookName.AFTER_TOOL_RESULT,
        AgentHookName.BEFORE_REPLY,
        AgentHookName.BEFORE_SPEAK,
        AgentHookName.BEFORE_MEMORY_WRITE,
        AgentHookName.AFTER_TURN,
        AgentHookName.ON_FAILURE,
        AgentHookName.ON_SAFE_IDLE,
        AgentHookName.ON_SESSION_CLOSE,
    )

    _ALIASES: dict[AgentHookName, AgentHookName] = {
        AgentHookName.BEFORE_REPLY_GENERATION: AgentHookName.BEFORE_REPLY,
        AgentHookName.ON_PROVIDER_FAILURE: AgentHookName.ON_FAILURE,
    }

    def __init__(self) -> None:
        handler_map: dict[AgentHookName, list[tuple[str, HookHandler]]] = {
            AgentHookName.BEFORE_SKILL_SELECTION: [("skill_selection_audit", self._before_skill_selection)],
            AgentHookName.AFTER_TRANSCRIPT: [("transcript_audit", self._after_transcript)],
            AgentHookName.AFTER_PERCEPTION: [("perception_audit", self._after_perception)],
            AgentHookName.BEFORE_TOOL_CALL: [("tool_call_audit", self._before_tool_call)],
            AgentHookName.AFTER_TOOL_RESULT: [("tool_result_audit", self._after_tool_result)],
            AgentHookName.BEFORE_REPLY: [("reply_planning_audit", self._before_reply)],
            AgentHookName.BEFORE_SPEAK: [("speak_gate_audit", self._before_speak)],
            AgentHookName.BEFORE_MEMORY_WRITE: [("memory_write_gate", self._before_memory_write)],
            AgentHookName.AFTER_TURN: [("turn_completion_audit", self._after_turn)],
            AgentHookName.ON_FAILURE: [("failure_audit", self._on_failure)],
            AgentHookName.ON_SAFE_IDLE: [("safe_idle_audit", self._on_safe_idle)],
            AgentHookName.ON_SESSION_CLOSE: [("session_close_audit", self._on_session_close)],
        }
        self._handlers = {
            **handler_map,
            AgentHookName.BEFORE_REPLY_GENERATION: handler_map[AgentHookName.BEFORE_REPLY],
            AgentHookName.ON_PROVIDER_FAILURE: handler_map[AgentHookName.ON_FAILURE],
        }

    def list_hook_names(self) -> list[str]:
        return [item.value for item in [*self._CANONICAL_HOOKS, *self._ALIASES]]

    def run(
        self,
        hook_name: AgentHookName,
        *,
        context: AgentTurnContext,
        state: HookRuntimeState,
    ) -> list[HookExecutionRecord]:
        records: list[HookExecutionRecord] = []
        canonical = self._ALIASES.get(hook_name, hook_name)
        for handler_name, handler in self._handlers.get(hook_name, []):
            record = handler(context, state)
            records.append(
                record.model_copy(
                    update={
                        "hook_name": hook_name,
                        "canonical_phase": canonical,
                        "handler_name": handler_name,
                        "run_id": state.run_id,
                        "checkpoint_id": state.checkpoint_id,
                    }
                )
            )
        return records

    def _before_skill_selection(self, context: AgentTurnContext, state: HookRuntimeState) -> HookExecutionRecord:
        return HookExecutionRecord(
            hook_name=AgentHookName.BEFORE_SKILL_SELECTION,
            canonical_phase=AgentHookName.BEFORE_SKILL_SELECTION,
            handler_name="before_skill_selection",
            action_type="audit",
            detail=f"session={context.session.session_id}",
            notes=[f"provider_failure={state.provider_failure_active}"],
        )

    def _after_transcript(self, context: AgentTurnContext, state: HookRuntimeState) -> HookExecutionRecord:
        return HookExecutionRecord(
            hook_name=AgentHookName.AFTER_TRANSCRIPT,
            canonical_phase=AgentHookName.AFTER_TRANSCRIPT,
            handler_name="after_transcript",
            action_type="audit",
            detail=f"session={context.session.session_id} skill={state.active_skill_name or 'unresolved'}",
            notes=["transcript_captured", context.event.event_type],
        )

    def _after_perception(self, context: AgentTurnContext, state: HookRuntimeState) -> HookExecutionRecord:
        snapshot = context.latest_perception
        detail = "no_perception_snapshot"
        notes = ["perception_absent"]
        if snapshot is not None:
            detail = f"{snapshot.provider_mode.value}:{snapshot.status.value}"
            notes = [f"limited_awareness={snapshot.limited_awareness}"]
        return HookExecutionRecord(
            hook_name=AgentHookName.AFTER_PERCEPTION,
            canonical_phase=AgentHookName.AFTER_PERCEPTION,
            handler_name="after_perception",
            action_type="audit",
            detail=detail,
            notes=notes,
        )

    def _before_tool_call(self, context: AgentTurnContext, state: HookRuntimeState) -> HookExecutionRecord:
        del context
        return HookExecutionRecord(
            hook_name=AgentHookName.BEFORE_TOOL_CALL,
            canonical_phase=AgentHookName.BEFORE_TOOL_CALL,
            handler_name="before_tool_call",
            action_type="audit",
            detail=f"tools={state.tool_count}",
            notes=[f"subagent={state.active_subagent_name or 'none'}"],
        )

    def _after_tool_result(self, context: AgentTurnContext, state: HookRuntimeState) -> HookExecutionRecord:
        del context
        return HookExecutionRecord(
            hook_name=AgentHookName.AFTER_TOOL_RESULT,
            canonical_phase=AgentHookName.AFTER_TOOL_RESULT,
            handler_name="after_tool_result",
            action_type="audit",
            detail=f"tools={state.tool_count}",
            notes=[f"checkpoint={state.checkpoint_id or 'none'}"],
        )

    def _before_reply(self, context: AgentTurnContext, state: HookRuntimeState) -> HookExecutionRecord:
        del context
        return HookExecutionRecord(
            hook_name=AgentHookName.BEFORE_REPLY,
            canonical_phase=AgentHookName.BEFORE_REPLY,
            handler_name="before_reply",
            action_type="audit",
            detail=f"tools={state.tool_count}",
            notes=[f"skill={state.active_skill_name or 'none'}"],
        )

    def _before_speak(self, context: AgentTurnContext, state: HookRuntimeState) -> HookExecutionRecord:
        del context
        candidate = state.reply_candidate
        return HookExecutionRecord(
            hook_name=AgentHookName.BEFORE_SPEAK,
            canonical_phase=AgentHookName.BEFORE_SPEAK,
            handler_name="before_speak",
            action_type="gate",
            detail=f"intent={candidate.intent if candidate is not None else 'none'}",
            notes=[f"validation_count={state.validation_count}"],
        )

    def _before_memory_write(self, context: AgentTurnContext, state: HookRuntimeState) -> HookExecutionRecord:
        del context
        return HookExecutionRecord(
            hook_name=AgentHookName.BEFORE_MEMORY_WRITE,
            canonical_phase=AgentHookName.BEFORE_MEMORY_WRITE,
            handler_name="before_memory_write",
            action_type="gate",
            gated=state.memory_write_requested,
            detail=f"memory_write_requested={state.memory_write_requested}",
            notes=[f"skill={state.active_skill_name or 'none'}"],
        )

    def _after_turn(self, context: AgentTurnContext, state: HookRuntimeState) -> HookExecutionRecord:
        del context
        plan = state.final_plan
        return HookExecutionRecord(
            hook_name=AgentHookName.AFTER_TURN,
            canonical_phase=AgentHookName.AFTER_TURN,
            handler_name="after_turn",
            action_type="audit",
            detail=f"intent={plan.intent if plan is not None else 'none'}",
            notes=[f"provider_failure={state.provider_failure_active}"],
        )

    def _on_failure(self, context: AgentTurnContext, state: HookRuntimeState) -> HookExecutionRecord:
        return HookExecutionRecord(
            hook_name=AgentHookName.ON_FAILURE,
            canonical_phase=AgentHookName.ON_FAILURE,
            handler_name="on_failure",
            action_type="audit",
            detail=context.session.session_id,
            notes=["failure_visible"],
        )

    def _on_safe_idle(self, context: AgentTurnContext, state: HookRuntimeState) -> HookExecutionRecord:
        return HookExecutionRecord(
            hook_name=AgentHookName.ON_SAFE_IDLE,
            canonical_phase=AgentHookName.ON_SAFE_IDLE,
            handler_name="on_safe_idle",
            action_type="audit",
            detail=context.session.session_id,
            notes=["safe_idle_policy_surface"],
        )

    def _on_session_close(self, context: AgentTurnContext, state: HookRuntimeState) -> HookExecutionRecord:
        del state
        return HookExecutionRecord(
            hook_name=AgentHookName.ON_SESSION_CLOSE,
            canonical_phase=AgentHookName.ON_SESSION_CLOSE,
            handler_name="on_session_close",
            action_type="audit",
            detail=context.session.session_id,
            notes=["session_close_visible"],
        )
