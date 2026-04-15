from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from embodied_stack.brain.agent_os import AgentRuntime
from embodied_stack.brain.agent_os.models import AgentEventAudit, AgentTurnContext, AgentTurnPlan
from embodied_stack.brain.visual_query import looks_like_visual_query
from embodied_stack.shared.contracts import CompanionContextMode, PlannerDescriptor, SkillActivationRecord, ToolInvocationRecord


class PlannerAdapter(Protocol):
    planner_id: str
    planner_profile: str

    def descriptor(self) -> PlannerDescriptor: ...

    def plan_speech_turn(
        self,
        *,
        context: AgentTurnContext,
        tool_invocations: list[ToolInvocationRecord],
        memory_updates: dict[str, str],
    ) -> AgentTurnPlan: ...

    def audit_event(
        self,
        *,
        context: AgentTurnContext,
        safe_idle_active: bool = False,
        preferred_skill_name: str | None = None,
    ) -> AgentEventAudit: ...


@dataclass
class AgentOSPlannerAdapter:
    runtime: AgentRuntime
    planner_profile: str = "default"
    planner_id: str = "agent_os_current"

    def descriptor(self) -> PlannerDescriptor:
        return PlannerDescriptor(
            planner_id=self.planner_id,
            display_name="Agent OS Planner",
            description="The current run/checkpoint-aware Agent OS planner path.",
            deterministic=self.planner_profile != "cloud_enhanced",
            default_profile="default",
            available_profiles=["default", "local_only", "cloud_enhanced"],
            supports_strict_mode=self.planner_profile != "cloud_enhanced",
            strict_replay_policy_version="blink_strict_replay/v2",
            capability_tags=[
                "agent_os",
                "playbook_routing",
                "tool_selection",
                "memory_grounding",
                "embodiment_semantics",
            ],
            expected_input_surfaces=[
                "normalized_scene_facts",
                "selected_tool_chain",
                "retrieved_memory_candidates",
                "planner_input_envelope",
            ],
            comparison_labels=[
                "reply_text",
                "active_playbook",
                "active_subagent",
                "tool_chain",
                "fallback_classification",
            ],
            scoring_notes=[
                "strict replay treats paraphrase drift as review-required if the tool chain and embodiment outputs still match",
                "cloud_enhanced is intentionally excluded from strict mode because provider variance is expected",
            ],
            notes=["Uses the existing AgentRuntime path and operator-visible traces."],
        )

    def plan_speech_turn(
        self,
        *,
        context: AgentTurnContext,
        tool_invocations: list[ToolInvocationRecord],
        memory_updates: dict[str, str],
    ) -> AgentTurnPlan:
        plan = self.runtime.plan_speech_turn(
            context=context,
            tool_invocations=tool_invocations,
            memory_updates=memory_updates,
        )
        plan.notes.extend([f"planner_id:{self.planner_id}", f"planner_profile:{self.planner_profile}"])
        return plan

    def audit_event(
        self,
        *,
        context: AgentTurnContext,
        safe_idle_active: bool = False,
        preferred_skill_name: str | None = None,
    ) -> AgentEventAudit:
        audit = self.runtime.audit_event(
            context=context,
            safe_idle_active=safe_idle_active,
            preferred_skill_name=preferred_skill_name,
        )
        audit.notes.extend([f"planner_id:{self.planner_id}", f"planner_profile:{self.planner_profile}"])
        return audit


@dataclass
class DeterministicBaselinePlannerAdapter:
    runtime: AgentRuntime
    planner_profile: str = "default"
    planner_id: str = "deterministic_baseline"

    def descriptor(self) -> PlannerDescriptor:
        return PlannerDescriptor(
            planner_id=self.planner_id,
            display_name="Deterministic Baseline Planner",
            description="A deterministic comparison planner for replay, compatibility, and eval work.",
            deterministic=True,
            default_profile="default",
            available_profiles=["default", "local_only"],
            supports_strict_mode=True,
            strict_replay_policy_version="blink_strict_replay/v2",
            capability_tags=[
                "deterministic",
                "tool_selection",
                "fallback_baseline",
                "replay_eval",
            ],
            expected_input_surfaces=[
                "normalized_scene_facts",
                "selected_tool_chain",
                "retrieved_memory_candidates",
                "planner_input_envelope",
            ],
            comparison_labels=[
                "reply_text",
                "active_skill",
                "active_subagent",
                "tool_chain",
            ],
            scoring_notes=[
                "designed for reproducible replay and planner-comparison baselines rather than production dialogue quality",
            ],
            notes=["Provides a reproducible baseline without changing the appliance/runtime stack."],
        )

    def plan_speech_turn(
        self,
        *,
        context: AgentTurnContext,
        tool_invocations: list[ToolInvocationRecord],
        memory_updates: dict[str, str],
    ) -> AgentTurnPlan:
        active_skill = self._resolve_skill(context=context)
        selected_subagent = self.runtime.subagent_registry.resolve(active_skill)
        intent = self._intent_for_context(
            context=context,
            active_skill=active_skill,
            tool_invocations=tool_invocations,
        )
        reply_text = self._reply_text(
            context=context,
            active_skill=active_skill,
            tool_invocations=tool_invocations,
            memory_updates=memory_updates,
            intent=intent,
        )
        return AgentTurnPlan(
            reply_text=reply_text,
            intent=intent,
            engine_name=self.planner_id,
            fallback_used=not bool(tool_invocations),
            commands=[],
            active_skill=active_skill,
            active_subagent=selected_subagent.name,
            notes=[f"planner_id:{self.planner_id}", f"planner_profile:{self.planner_profile}"],
        )

    def audit_event(
        self,
        *,
        context: AgentTurnContext,
        safe_idle_active: bool = False,
        preferred_skill_name: str | None = None,
    ) -> AgentEventAudit:
        return self.runtime.audit_event(
            context=context,
            safe_idle_active=safe_idle_active,
            preferred_skill_name=preferred_skill_name,
        )

    def _resolve_skill(self, *, context: AgentTurnContext) -> SkillActivationRecord:
        provider_failure_active = self.runtime._provider_failure_active(context)
        return self.runtime.skill_registry.resolve(
            text=context.text,
            session=context.session,
            context_mode=context.context_mode,
            latest_perception=context.latest_perception,
            provider_failure_active=provider_failure_active,
        )

    def _intent_for_context(
        self,
        *,
        context: AgentTurnContext,
        active_skill: SkillActivationRecord,
        tool_invocations: list[ToolInvocationRecord],
    ) -> str:
        tool_names = {item.tool_name for item in tool_invocations if item.matched}
        lowered = context.text.lower().strip()
        if "operator_escalation" in tool_names or any(token in lowered for token in {"human", "operator", "staff", "help me"}):
            return "operator_handoff"
        if "wayfinding_lookup" in tool_names or any(token in lowered for token in {"where", "how do i get", "front desk", "workshop room", "quiet room"}):
            return "wayfinding"
        if "events_lookup" in tool_names or any(token in lowered for token in {"event", "workshop", "schedule", "start time"}):
            return "events"
        if active_skill.skill_name == "observe_and_comment" or looks_like_visual_query(lowered):
            return "perception_query"
        if any(token in lowered for token in {"hello", "hi", "good morning", "good afternoon"}):
            return "greeting"
        if active_skill.skill_name == "safe_degraded_response":
            return "clarify"
        return "capabilities"

    def _reply_text(
        self,
        *,
        context: AgentTurnContext,
        active_skill: SkillActivationRecord,
        tool_invocations: list[ToolInvocationRecord],
        memory_updates: dict[str, str],
        intent: str,
    ) -> str | None:
        for tool in tool_invocations:
            if tool.matched and tool.answer_text:
                return tool.answer_text
        if context.user_memory and context.user_memory.display_name and "remember" in context.text.lower():
            return f"I remember you as {context.user_memory.display_name}."
        if active_skill.skill_name == "observe_and_comment" and context.latest_perception and context.latest_perception.scene_summary:
            return context.latest_perception.scene_summary
        if active_skill.skill_name == "companion_greeting_reentry" and self._is_personal_local(context):
            if context.user_memory and context.user_memory.display_name:
                return f"Welcome back, {context.user_memory.display_name}. Want to pick up where we left off or plan the day?"
            return "Hi. I can help with notes, reminders, planning, workspace context, and grounded local questions."
        if memory_updates.get("remembered_name") and intent == "greeting":
            return f"Hello {memory_updates['remembered_name']}. How can I help?"
        if intent == "operator_handoff":
            if self._is_personal_local(context):
                return "I can help capture that clearly and flag it for follow-up."
            return "I can help get a human operator involved."
        if intent == "wayfinding":
            if self._is_personal_local(context):
                return "I can help with that if you tell me the place, sign, or destination you want to check."
            return "I can help with directions if you tell me the destination you need."
        if intent == "events":
            if self._is_personal_local(context):
                return "I can help with current plans, reminders, or venue timing if you ask about a specific item."
            return "I can help with events and schedules if you ask about a specific program or time."
        if intent == "perception_query":
            return "My current visual understanding is limited without a fresh semantic scene update."
        if active_skill.skill_name == "safe_degraded_response":
            return "I can still help, but my current awareness is limited so I may need you to repeat or clarify."
        if self._is_personal_local(context):
            return "I can help with local notes, reminders, workspace context, and grounded questions about what is happening right now."
        return "I can help with directions, events, visitor questions, and operator handoff."

    def _is_personal_local(self, context: AgentTurnContext) -> bool:
        return context.context_mode == CompanionContextMode.PERSONAL_LOCAL


@dataclass
class PlannerRegistry:
    runtime: AgentRuntime

    def list_descriptors(self) -> list[PlannerDescriptor]:
        return [
            AgentOSPlannerAdapter(runtime=self.runtime).descriptor(),
            DeterministicBaselinePlannerAdapter(runtime=self.runtime).descriptor(),
        ]

    def get(self, planner_id: str, *, planner_profile: str = "default") -> PlannerAdapter:
        resolved = (planner_id or "agent_os_current").strip().lower()
        if resolved == "agent_os_current":
            return AgentOSPlannerAdapter(runtime=self.runtime, planner_profile=planner_profile)
        if resolved == "deterministic_baseline":
            return DeterministicBaselinePlannerAdapter(runtime=self.runtime, planner_profile=planner_profile)
        raise KeyError(resolved)
