from __future__ import annotations

from embodied_stack.brain.skill_library import FIRST_PARTY_SKILLS, SkillSpec
from embodied_stack.brain.visual_query import looks_like_visual_query
from embodied_stack.shared.models import CompanionContextMode, PerceptionSnapshotRecord, SessionRecord, SkillActivationRecord


class SkillRegistry:
    def __init__(self) -> None:
        self._skills = {spec.name: spec for spec in FIRST_PARTY_SKILLS}
        self._aliases = {
            alias: spec.name
            for spec in FIRST_PARTY_SKILLS
            for alias in spec.aliases
        }
        self._playbook_aliases: dict[str, str] = {}
        for spec in FIRST_PARTY_SKILLS:
            self._playbook_aliases.setdefault(spec.playbook_name, spec.name)

    def list_skill_names(self) -> list[str]:
        return list(dict.fromkeys([*self._skills, *self._playbook_aliases]))

    def activate_named(self, skill_name: str, *, reason: str) -> SkillActivationRecord:
        canonical = self._aliases.get(skill_name) or self._playbook_aliases.get(skill_name) or skill_name
        skill = self._skills[canonical]
        return SkillActivationRecord(
            skill_name=skill.name,
            behavior_category=skill.behavior_category,
            playbook_name=skill.playbook_name,
            playbook_version=skill.playbook_version,
            route_reason=reason,
            route_variant=skill.route_variant or skill.name,
            description=skill.description,
            reason=reason,
            purpose=skill.purpose,
            entry_conditions=list(skill.entry_conditions),
            exit_conditions=list(skill.exit_conditions),
            required_tools=list(skill.required_tools),
            allowed_tools=list(skill.allowed_tools),
            banned_tools=list(skill.banned_tools),
            forbidden_claims=list(skill.forbidden_claims),
            success_criteria=list(skill.success_criteria),
            body_style_hints=list(skill.body_style_hints),
            memory_rules=list(skill.memory_rules),
            evaluation_rubric=list(skill.evaluation_rubric),
            version=skill.version,
        )

    def resolve(
        self,
        *,
        text: str,
        session: SessionRecord,
        context_mode: CompanionContextMode,
        latest_perception: PerceptionSnapshotRecord | None,
        provider_failure_active: bool,
    ) -> SkillActivationRecord:
        lowered = text.lower().strip()
        skill = self._select_skill(
            lowered=lowered,
            session=session,
            context_mode=context_mode,
            latest_perception=latest_perception,
            provider_failure_active=provider_failure_active,
        )
        return self.activate_named(
            skill.name,
            reason=self._reason_for_skill(
                skill_name=skill.name,
                lowered=lowered,
                session=session,
                latest_perception=latest_perception,
                provider_failure_active=provider_failure_active,
            ),
        )

    def _select_skill(
        self,
        *,
        lowered: str,
        session: SessionRecord,
        context_mode: CompanionContextMode,
        latest_perception: PerceptionSnapshotRecord | None,
        provider_failure_active: bool,
    ) -> SkillSpec:
        if session.scenario_name:
            return self._skills["investor_demo_mode"]
        if provider_failure_active or "safe idle" in lowered or session.current_topic == "safe_idle":
            return self._skills["safe_degraded_response"]
        if any(
            phrase in lowered
            for phrase in (
                "runtime issue",
                "diagnose",
                "doctor",
                "setup issue",
                "mic not working",
                "camera not working",
                "device missing",
            )
        ):
            return self._skills["self_diagnose_local_runtime"]
        if any(phrase in lowered for phrase in ("operator", "human help", "lost item", "accessibility")) or session.current_topic == "operator_handoff":
            return self._skills["incident_escalation"]
        if any(phrase in lowered for phrase in ("reminder", "remind me", "follow up with me later", "later today")):
            return self._skills["reminder_follow_up"]
        if any(phrase in lowered for phrase in ("note that", "write this down", "my note", "saved notes")):
            return self._skills["note_and_recall"]
        if any(phrase in lowered for phrase in ("plan my day", "what's next today", "today context", "today's plan")):
            return self._skills["day_planning"]
        if any(phrase in lowered for phrase in ("workspace", "what was i working on", "recent context", "recap our session")):
            return self._skills["workspace_context_help"]
        if any(
            phrase in lowered
            for phrase in (
                "what were we discussing",
                "pick up where we left off",
                "pick up where we were",
                "did i leave anything open",
                "what should we revisit",
                "unfinished thread",
                "open thread",
            )
        ):
            return self._skills["unresolved_thread_follow_up"]
        if any(phrase in lowered for phrase in ("remember", "my name", "repeat how to get there")):
            return self._skills["memory_follow_up"]
        if any(
            phrase in lowered
            for phrase in (
                "keep it brief",
                "be direct",
                "don't be chatty",
                "do not be chatty",
                "take it one step at a time",
                "step by step",
                "i'm overwhelmed",
                "i am overwhelmed",
            )
        ):
            return self._skills["emotional_tone_bounds"]
        if any(phrase in lowered for phrase in ("where is", "directions", "front desk", "workshop room", "quiet room")):
            return self._skills["wayfinding"]
        if any(phrase in lowered for phrase in ("event", "schedule", "calendar", "what time")):
            return self._skills["schedule_help"]
        if looks_like_visual_query(lowered):
            return self._skills["observe_and_comment"]
        if session.current_topic == "greeting" or any(phrase in lowered for phrase in ("hello", "hi", "hey there")):
            if context_mode == CompanionContextMode.PERSONAL_LOCAL:
                return self._skills["companion_greeting_reentry"]
            return self._skills["welcome_guest"]
        if latest_perception is not None and not latest_perception.limited_awareness and "look" in lowered:
            return self._skills["observe_and_comment"]
        return self._skills["general_conversation"]

    def _reason_for_skill(
        self,
        *,
        skill_name: str,
        lowered: str,
        session: SessionRecord,
        latest_perception: PerceptionSnapshotRecord | None,
        provider_failure_active: bool,
    ) -> str:
        if skill_name == "investor_demo_mode":
            return f"scenario_bound:{session.scenario_name}"
        if provider_failure_active and skill_name == "safe_degraded_response":
            return "provider_failure_active"
        if latest_perception is not None and skill_name == "observe_and_comment":
            return f"perception_available:{latest_perception.provider_mode.value}"
        if session.current_topic:
            return f"session_topic:{session.current_topic}"
        return f"query_match:{lowered[:48] or 'empty'}"
