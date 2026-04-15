from __future__ import annotations

from dataclasses import dataclass

from embodied_stack.shared.models import SkillActivationRecord


@dataclass(frozen=True)
class SubagentSpec:
    name: str
    purpose: str
    allowed_tools: tuple[str, ...]
    banned_tools: tuple[str, ...] = ()
    version: str = "1.0"
    primary_surface: bool = True


class SubagentRegistry:
    def __init__(self) -> None:
        self._specs = {
            spec.name: spec
            for spec in (
                SubagentSpec(
                    name="perception_analyst",
                    purpose="Interpret the current scene and perception confidence.",
                    allowed_tools=("capture_scene", "world_model_runtime", "device_health_snapshot", "system_health", "body_preview"),
                ),
                SubagentSpec(
                    name="dialogue_planner",
                    purpose="Plan a grounded reply using venue and memory context.",
                    allowed_tools=(
                        "search_venue_knowledge",
                        "query_calendar",
                        "search_memory",
                        "memory_status",
                        "device_health_snapshot",
                        "world_model_runtime",
                        "query_local_files",
                        "local_notes",
                        "personal_reminders",
                        "today_context",
                        "recent_session_digest",
                        "browser_task",
                        "start_workflow",
                        "system_health",
                        "body_preview",
                    ),
                ),
                SubagentSpec(
                    name="memory_curator",
                    purpose="Handle memory retrieval, storage, and recap surfaces.",
                    allowed_tools=(
                        "search_memory",
                        "memory_status",
                        "system_health",
                        "write_memory",
                        "promote_memory",
                        "query_local_files",
                        "local_notes",
                        "personal_reminders",
                        "recent_session_digest",
                        "today_context",
                        "start_workflow",
                    ),
                ),
                SubagentSpec(
                    name="safety_reviewer",
                    purpose="Keep the turn safe, degraded honestly, and within supported scope.",
                    allowed_tools=("system_health", "device_health_snapshot", "body_safe_idle", "require_confirmation", "request_operator_help"),
                ),
                SubagentSpec(
                    name="tool_result_summarizer",
                    purpose="Summarize tool outcomes, skipped capabilities, and fallback markers for traces.",
                    allowed_tools=("search_memory", "query_local_files", "system_health"),
                ),
                SubagentSpec(
                    name="embodiment_planner",
                    purpose="Preview and constrain semantic body or speech actions.",
                    allowed_tools=("body_preview", "body_command", "body_safe_idle", "interrupt_speech", "speak_text", "set_listening_state"),
                    primary_surface=False,
                ),
                SubagentSpec(
                    name="operator_handoff_planner",
                    purpose="Prepare operator-visible escalation and handoff steps.",
                    allowed_tools=("request_operator_help", "log_incident", "require_confirmation", "search_memory", "system_health"),
                    primary_surface=False,
                ),
                SubagentSpec(
                    name="reflection",
                    purpose="Compatibility alias for tool result summarization.",
                    allowed_tools=(),
                    primary_surface=False,
                ),
            )
        }

    def list_subagent_names(self) -> list[str]:
        return [name for name, spec in self._specs.items() if spec.primary_surface]

    def list_role_names(self) -> list[str]:
        return list(self._specs)

    def get(self, name: str) -> SubagentSpec:
        return self._specs[name]

    def resolve(self, active_skill: SkillActivationRecord) -> SubagentSpec:
        playbook = active_skill.playbook_name or active_skill.skill_name
        if playbook == "observe_and_comment":
            return self._specs["perception_analyst"]
        if playbook in {"memory_followup", "daily_planning"}:
            return self._specs["memory_curator"]
        if playbook == "companion_relationship":
            if active_skill.skill_name in {"unresolved_thread_follow_up", "emotional_tone_bounds"}:
                return self._specs["memory_curator"]
            return self._specs["dialogue_planner"]
        if playbook == "incident_escalation":
            return self._specs["operator_handoff_planner"]
        if playbook == "safe_degraded_response":
            return self._specs["safety_reviewer"]
        if playbook in {"community_concierge", "general_companion_conversation"}:
            return self._specs["dialogue_planner"]
        return self._specs["dialogue_planner"]


__all__ = [
    "SubagentRegistry",
    "SubagentSpec",
]
