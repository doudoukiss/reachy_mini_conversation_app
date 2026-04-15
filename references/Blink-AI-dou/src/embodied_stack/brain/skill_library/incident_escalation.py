from __future__ import annotations

from embodied_stack.shared.models import CompanionBehaviorCategory

from .types import SkillSpec


INCIDENT_ESCALATION: tuple[SkillSpec, ...] = (
    SkillSpec(
        name="incident_escalation",
        playbook_name="incident_escalation",
        route_variant="incident_escalation",
        behavior_category=CompanionBehaviorCategory.INCIDENT_ESCALATION,
        description="Human handoff and escalation replies.",
        purpose="Keep the user informed while moving the interaction into explicit operator help.",
        required_tools=("system_health", "request_operator_help", "require_confirmation"),
        allowed_tools=("system_health", "request_operator_help", "log_incident", "require_confirmation", "search_memory"),
        forbidden_claims=("The operator is already here",),
        success_criteria=("state handoff status clearly", "stay calm and explicit"),
        entry_conditions=("The user asks for help beyond the supported autonomous scope.",),
        exit_conditions=("Handoff state and next step are visible and explicit.",),
        body_style_hints=("calm", "supportive"),
        memory_rules=("Include relevant session context in the handoff request.",),
        evaluation_rubric=("Escalation clarity", "Calm tone", "No false operator presence"),
    ),
)
