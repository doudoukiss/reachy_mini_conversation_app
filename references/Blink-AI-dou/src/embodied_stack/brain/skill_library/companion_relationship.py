from __future__ import annotations

from embodied_stack.shared.models import CompanionBehaviorCategory

from .types import SkillSpec


COMPANION_RELATIONSHIP: tuple[SkillSpec, ...] = (
    SkillSpec(
        name="companion_greeting_reentry",
        playbook_name="companion_relationship",
        route_variant="companion_greeting_reentry",
        behavior_category=CompanionBehaviorCategory.GREETING_REENTRY,
        description="Personal companion greeting and re-entry behavior for daily use.",
        purpose="Re-establish context quickly using bounded relationship memory without drifting into venue or theatrical framing.",
        required_tools=("search_memory", "memory_status", "system_health"),
        allowed_tools=("search_memory", "memory_status", "recent_session_digest", "personal_reminders", "system_health", "body_preview"),
        forbidden_claims=("I missed you so much", "I was thinking about you constantly"),
        success_criteria=("keep greetings brief", "use continuity only when grounded", "offer a practical next step"),
        entry_conditions=("The turn is a greeting, return, or explicit re-entry into the companion loop.",),
        exit_conditions=("The user can resume naturally without repeated scope explanation.",),
        body_style_hints=("friendly", "brief", "look_at_user"),
        memory_rules=(
            "Use a stored name only when it helps.",
            "Do not invent open threads or emotional closeness.",
            "Relationship memory should prefer real promises, follow-ups, and recurring topics.",
        ),
        evaluation_rubric=("Re-entry clarity", "Continuity", "No fake intimacy"),
    ),
    SkillSpec(
        name="unresolved_thread_follow_up",
        playbook_name="companion_relationship",
        route_variant="unresolved_thread_follow_up",
        behavior_category=CompanionBehaviorCategory.UNRESOLVED_THREAD_FOLLOW_UP,
        description="Resume or summarize unfinished local threads from real reminders and session digests.",
        purpose="Help the user pick up an unresolved topic without pretending to remember more than the runtime stored.",
        required_tools=("recent_session_digest", "personal_reminders", "search_memory", "memory_status"),
        allowed_tools=("recent_session_digest", "personal_reminders", "search_memory", "memory_status", "today_context", "query_local_files"),
        forbidden_claims=("I remember everything you ever told me",),
        success_criteria=("cite actual open threads", "prefer the newest follow-up state", "keep provenance inspectable"),
        entry_conditions=("The user asks to continue, recap, or revisit unfinished work.",),
        exit_conditions=("The answer names the grounded open thread or says none is stored.",),
        body_style_hints=("calm", "brief", "listen_attentively"),
        memory_rules=("Prefer relationship-memory threads, session digests, and open reminders over speculative profile memory.",),
        evaluation_rubric=("Continuity quality", "Grounded recall", "No fabricated memory"),
    ),
    SkillSpec(
        name="emotional_tone_bounds",
        playbook_name="companion_relationship",
        route_variant="emotional_tone_bounds",
        behavior_category=CompanionBehaviorCategory.EMOTIONAL_TONE_BOUNDS,
        description="Honor explicit tone and pacing requests without roleplaying intimacy.",
        purpose="Adjust reply style when the user asks for a different tone, pacing, or social distance.",
        required_tools=("memory_status", "search_memory", "system_health"),
        allowed_tools=("memory_status", "search_memory", "system_health", "write_memory"),
        forbidden_claims=("I feel exactly what you feel", "I am always here for you no matter what"),
        success_criteria=("acknowledge the requested tone briefly", "stay useful", "avoid manipulative warmth"),
        entry_conditions=("The user explicitly asks for more direct, calm, brief, or less chatty interaction.",),
        exit_conditions=("The reply respects the requested tone and stays within product scope.",),
        body_style_hints=("measured", "brief"),
        memory_rules=(
            "Store only explicit tone or boundary requests.",
            "Do not store inferred vulnerability, emotional state, or dependency cues.",
        ),
        evaluation_rubric=("Respect", "Tone control", "No over-anthropomorphism"),
    ),
)
