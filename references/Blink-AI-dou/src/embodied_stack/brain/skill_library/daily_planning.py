from __future__ import annotations

from embodied_stack.shared.models import CompanionBehaviorCategory

from .types import SkillSpec


DAILY_PLANNING: tuple[SkillSpec, ...] = (
    SkillSpec(
        name="day_planning",
        playbook_name="daily_planning",
        route_variant="day_planning",
        behavior_category=CompanionBehaviorCategory.DAY_PLANNING,
        description="Summarize local day context, reminders, and recent digest state.",
        purpose="Offer a compact local planning summary from repo-local state.",
        required_tools=("today_context", "recent_session_digest", "personal_reminders", "memory_status"),
        allowed_tools=("today_context", "recent_session_digest", "personal_reminders", "query_local_files", "memory_status", "query_calendar"),
        forbidden_claims=("I know your whole day outside local context",),
        success_criteria=("summarize current local context", "avoid invented commitments"),
        entry_conditions=("The user asks what is next or requests a local planning summary.",),
        exit_conditions=("The planning summary stays within locally available context.",),
        body_style_hints=("brief",),
        memory_rules=("Do not invent external obligations.",),
        evaluation_rubric=("Bounded scope", "Usefulness", "No invented commitments"),
        aliases=("daily_planning",),
    ),
    SkillSpec(
        name="reminder_follow_up",
        playbook_name="daily_planning",
        route_variant="reminder_follow_up",
        behavior_category=CompanionBehaviorCategory.DAY_PLANNING,
        description="Handle bounded local reminders and follow-up prompts.",
        purpose="Manage reminders without implying external sync.",
        required_tools=("personal_reminders", "memory_status"),
        allowed_tools=("personal_reminders", "write_memory", "memory_status", "query_calendar"),
        forbidden_claims=("I synced that to your external calendar",),
        success_criteria=("keep reminders local", "state due status clearly"),
        entry_conditions=("The user asks for reminders or follow-up prompts.",),
        exit_conditions=("Reminder state and scope are explicit.",),
        body_style_hints=("brief", "listen_attentively"),
        memory_rules=("Local reminders stay local unless explicitly exported later.",),
        evaluation_rubric=("Reminder clarity", "No false sync"),
    ),
)
