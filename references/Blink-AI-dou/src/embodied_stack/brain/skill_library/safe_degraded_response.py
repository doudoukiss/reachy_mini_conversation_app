from __future__ import annotations

from embodied_stack.shared.models import CompanionBehaviorCategory

from .types import SkillSpec


SAFE_DEGRADED_RESPONSE: tuple[SkillSpec, ...] = (
    SkillSpec(
        name="safe_degraded_response",
        playbook_name="safe_degraded_response",
        route_variant="safe_degraded_response",
        behavior_category=CompanionBehaviorCategory.SAFE_DEGRADED_RESPONSE,
        description="Honest degraded-mode replies under uncertainty or provider failure.",
        purpose="Provide a safe, explicit fallback when the runtime or scene confidence is limited.",
        required_tools=("system_health", "device_health_snapshot", "require_confirmation"),
        allowed_tools=("system_health", "device_health_snapshot", "body_safe_idle", "require_confirmation", "request_operator_help"),
        forbidden_claims=("I am certain about the scene",),
        success_criteria=("surface limits", "offer a safe next step"),
        entry_conditions=("Provider failure, limited awareness, or unsafe action downgrade is active.",),
        exit_conditions=("The degraded reason and next step are obvious.",),
        body_style_hints=("calm", "minimal"),
        memory_rules=("Do not promote degraded guesses into memory.",),
        evaluation_rubric=("Degradation honesty", "Safety", "Practical next step"),
    ),
    SkillSpec(
        name="self_diagnose_local_runtime",
        playbook_name="safe_degraded_response",
        route_variant="self_diagnose_local_runtime",
        behavior_category=CompanionBehaviorCategory.SAFE_DEGRADED_RESPONSE,
        description="Local appliance and runtime diagnosis responses.",
        purpose="Help the operator understand device, backend, and setup issues from the local runtime.",
        required_tools=("system_health", "device_health_snapshot", "memory_status"),
        allowed_tools=("system_health", "device_health_snapshot", "memory_status", "query_local_files", "request_operator_help"),
        success_criteria=("state the degraded component", "suggest a concrete recovery step"),
        entry_conditions=("The user asks about setup, devices, models, or local runtime health.",),
        exit_conditions=("The issue and next step are inspectable.",),
        body_style_hints=("minimal", "technical"),
        memory_rules=("Do not store transient diagnostics as user memory.",),
        evaluation_rubric=("Specific diagnosis", "Recovery guidance", "No false repair claim"),
    ),
)
