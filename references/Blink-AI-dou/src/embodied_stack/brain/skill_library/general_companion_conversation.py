from __future__ import annotations

from embodied_stack.shared.models import CompanionBehaviorCategory

from .types import SkillSpec


GENERAL_COMPANION_CONVERSATION: tuple[SkillSpec, ...] = (
    SkillSpec(
        name="general_conversation",
        playbook_name="general_companion_conversation",
        route_variant="general_conversation",
        behavior_category=CompanionBehaviorCategory.GENERAL_CONVERSATION,
        description="General companion conversation within confirmed product scope.",
        purpose="Answer ordinary questions while staying grounded to retrieved context and live system limits.",
        required_tools=("search_memory", "memory_status", "system_health"),
        allowed_tools=("search_memory", "memory_status", "system_health", "search_venue_knowledge", "body_preview"),
        forbidden_claims=("I know things that were not retrieved",),
        success_criteria=("stay concise", "stay within implemented scope"),
        entry_conditions=("No stronger specialist route matched.",),
        exit_conditions=("The user received a bounded, grounded reply.",),
        body_style_hints=("listen_attentively", "calm", "brief"),
        memory_rules=("Prefer recalled user context when it is explicitly present.",),
        evaluation_rubric=("Grounded", "Helpful", "Honest about limits"),
        aliases=("general_companion_conversation",),
    ),
    SkillSpec(
        name="investor_demo_mode",
        playbook_name="general_companion_conversation",
        route_variant="investor_demo_mode",
        behavior_category=CompanionBehaviorCategory.VENUE_CONCIERGE,
        description="Replayable demo-facing behavior that stays concrete and honest.",
        purpose="Keep investor-facing turns polished, deterministic, and inspectable.",
        required_tools=("search_venue_knowledge", "search_memory", "capture_scene", "system_health", "body_preview"),
        allowed_tools=("search_venue_knowledge", "search_memory", "capture_scene", "system_health", "body_preview", "request_operator_help"),
        forbidden_claims=("This is autonomous hardware behavior beyond the current runtime",),
        success_criteria=("stay polished", "stay deterministic", "avoid capability inflation"),
        entry_conditions=("A scenario-bound investor scene is running.",),
        exit_conditions=("The demo reply remains honest and replayable.",),
        body_style_hints=("polished", "deterministic"),
        memory_rules=("Do not fake unseen autonomy or external hardware control.",),
        evaluation_rubric=("Demo polish", "Honesty", "Replayability"),
    ),
)
