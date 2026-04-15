from __future__ import annotations

from embodied_stack.shared.models import CompanionBehaviorCategory

from .types import SkillSpec


MEMORY_FOLLOWUP: tuple[SkillSpec, ...] = (
    SkillSpec(
        name="memory_follow_up",
        playbook_name="memory_followup",
        route_variant="memory_follow_up",
        behavior_category=CompanionBehaviorCategory.UNRESOLVED_THREAD_FOLLOW_UP,
        description="Use remembered context without fabricating durable memory.",
        purpose="Continue a prior thread using stored episodic, relationship, or profile memory without over-injecting context.",
        required_tools=("search_memory", "memory_status", "system_health"),
        allowed_tools=("search_memory", "memory_status", "system_health", "write_memory", "promote_memory"),
        forbidden_claims=("I remember things that are not in memory",),
        success_criteria=("use session or user memory", "make provenance inspectable"),
        entry_conditions=("The user asks to remember or continue a prior topic.",),
        exit_conditions=("The follow-up is grounded to actual stored context.",),
        body_style_hints=("friendly", "listen_attentively"),
        memory_rules=(
            "Only write or promote memory when the user states durable information.",
            "Prefer relationship-memory open threads and promises over vague profile recall.",
        ),
        evaluation_rubric=("Continuity", "Provenance", "No fabricated recall"),
        aliases=("remember_and_follow_up", "memory_followup"),
    ),
    SkillSpec(
        name="note_and_recall",
        playbook_name="memory_followup",
        route_variant="note_and_recall",
        behavior_category=CompanionBehaviorCategory.GENERAL_CONVERSATION,
        description="Capture and recall local notes or stable workspace context.",
        purpose="Keep a bounded local note workflow available without external systems.",
        required_tools=("query_local_files", "memory_status", "write_memory"),
        allowed_tools=("query_local_files", "write_memory", "search_memory", "memory_status"),
        forbidden_claims=("I wrote that somewhere else",),
        success_criteria=("surface saved notes", "stay local-first", "be explicit about what is stored"),
        entry_conditions=("The user asks for a local note or asks to save local context.",),
        exit_conditions=("The note path is visible and bounded.",),
        body_style_hints=("listen_attentively",),
        memory_rules=("State whether the note is session, relationship, or profile scoped.",),
        evaluation_rubric=("Local-first honesty", "Recall quality"),
    ),
)
