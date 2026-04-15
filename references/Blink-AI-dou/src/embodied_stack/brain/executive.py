from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from embodied_stack.demo.community_scripts import OPERATOR_ESCALATION
from embodied_stack.brain.social.disengagement_policy import reply_guardrail, shorten_reply
from embodied_stack.brain.social.escalation_policy import accessibility_request, escalation_for_text
from embodied_stack.brain.social.greeting_policy import greeting_suppression_reason
from embodied_stack.brain.social.interruption_policy import is_recent_interrupt, should_keep_listening
from embodied_stack.brain.venue_knowledge import VenueKnowledge
from embodied_stack.brain.visual_query import looks_like_visual_query
from embodied_stack.shared.models import (
    CompanionContextMode,
    EmbodiedWorldModel,
    EngagementState,
    ExecutiveDecisionRecord,
    ExecutiveDecisionType,
    FactFreshness,
    IncidentReasonCategory,
    InteractionExecutiveState,
    PerceptionSnapshotRecord,
    ResponseMode,
    RobotEvent,
    SessionRecord,
    SessionStatus,
    UserMemoryRecord,
    utc_now,
)


@dataclass
class ExecutivePlan:
    decisions: list[ExecutiveDecisionRecord] = field(default_factory=list)
    reply_text: str | None = None
    intent: str | None = None
    notes: list[str] = field(default_factory=list)
    skip_dialogue: bool = False
    prepend_stop: bool = False


@dataclass
class InteractionExecutive:
    auto_greet_cooldown_seconds: float = 45.0
    interruption_window_seconds: float = 6.0
    venue_knowledge: VenueKnowledge | None = None
    context_mode: CompanionContextMode = CompanionContextMode.PERSONAL_LOCAL

    def evaluate_non_speech(
        self,
        *,
        event: RobotEvent,
        session: SessionRecord,
        prior_world_model: EmbodiedWorldModel,
        world_model: EmbodiedWorldModel,
        user_memory: UserMemoryRecord | None,
    ) -> ExecutivePlan:
        del prior_world_model

        if event.event_type in {"person_detected", "person_visible"}:
            policy = self._greeting_policy(session=session)
            greeting_outcome = greeting_suppression_reason(
                world_model=world_model,
                policy_enabled=bool(policy.enabled) if policy is not None else True,
                max_people_for_auto_greet=policy.max_people_for_auto_greet if policy is not None else None,
                last_greet_at=self._last_greet_at(session),
                now=event.timestamp,
                cooldown_seconds=self._greeting_cooldown_seconds(session=session),
            )
            if greeting_outcome.suppressed_reason is not None:
                return ExecutivePlan(
                    decisions=[
                        self._decision(
                            session_id=session.session_id,
                            decision_type=ExecutiveDecisionType.AUTO_GREET_SUPPRESSED,
                            policy_name=greeting_outcome.policy_name,
                            policy_outcome=greeting_outcome.outcome,
                            suppressed_reason=greeting_outcome.suppressed_reason,
                            executive_state=InteractionExecutiveState.MONITORING,
                            event=event,
                            reason_codes=[greeting_outcome.suppressed_reason],
                            note="site policy suppressed automatic greeting for the current scene",
                            applied=False,
                        )
                    ],
                    skip_dialogue=True,
                )

            greeting = self._build_greeting(session=session, user_memory=user_memory)
            session.current_topic = "greeting"
            session.session_memory["last_auto_greet_at"] = event.timestamp.isoformat()
            return ExecutivePlan(
                decisions=[
                    self._decision(
                        session_id=session.session_id,
                        decision_type=ExecutiveDecisionType.AUTO_GREET,
                        policy_name="greeting_policy",
                        policy_outcome="greeted",
                        executive_state=InteractionExecutiveState.RESPONDING,
                        event=event,
                        reason_codes=["auto_greet_on_approach"],
                        note="presence cue triggered a proactive greeting",
                    )
                ],
                reply_text=greeting,
                intent="greeting",
                skip_dialogue=True,
            )

        if event.event_type in {"touch", "button"}:
            session.current_topic = "attention"
            return ExecutivePlan(
                decisions=[
                    self._decision(
                        session_id=session.session_id,
                        decision_type=ExecutiveDecisionType.NORMAL_REPLY,
                        policy_name="greeting_policy",
                        policy_outcome="reengaged",
                        executive_state=InteractionExecutiveState.MONITORING,
                        event=event,
                        reason_codes=["interaction_prompt_from_touch"],
                        note="manual interaction cue requested attention",
                    )
                ],
                reply_text=self._attention_reply(session=session),
                intent="attention",
                skip_dialogue=True,
            )

        if event.event_type == "low_battery":
            session.current_topic = "safe_idle"
            return ExecutivePlan(
                decisions=[
                    self._decision(
                        session_id=session.session_id,
                        decision_type=ExecutiveDecisionType.FORCE_SAFE_IDLE,
                        policy_name="attract_mode_policy",
                        policy_outcome="safe_idle",
                        executive_state=InteractionExecutiveState.SAFE_IDLE,
                        event=event,
                        reason_codes=["low_battery_safe_idle"],
                        note="low battery forced safe idle behavior",
                    )
                ],
                reply_text="Battery is low. I am switching into a safe idle mode and reducing activity.",
                intent="safe_idle",
                skip_dialogue=True,
            )

        if event.event_type == "heartbeat" and not event.payload.get("network_ok", True):
            return ExecutivePlan(
                decisions=[
                    self._decision(
                        session_id=session.session_id,
                        decision_type=ExecutiveDecisionType.FORCE_SAFE_IDLE,
                        policy_name="attract_mode_policy",
                        policy_outcome="safe_idle",
                        executive_state=InteractionExecutiveState.SAFE_IDLE,
                        event=event,
                        reason_codes=["transport_safe_idle_active"],
                        note="edge heartbeat reported degraded network state",
                    )
                ],
                intent="telemetry_update",
                skip_dialogue=True,
            )

        if event.event_type == "telemetry" and str(event.payload.get("mode", "")).strip() == "degraded_safe_idle":
            return ExecutivePlan(
                decisions=[
                    self._decision(
                        session_id=session.session_id,
                        decision_type=ExecutiveDecisionType.FORCE_SAFE_IDLE,
                        policy_name="attract_mode_policy",
                        policy_outcome="safe_idle",
                        executive_state=InteractionExecutiveState.SAFE_IDLE,
                        event=event,
                        reason_codes=["edge_safe_idle_active"],
                        note="edge telemetry already indicates safe idle",
                        applied=False,
                    )
                ],
                intent="telemetry_update",
                skip_dialogue=True,
            )

        if event.event_type == "scene_summary_updated" and world_model.perception_limited_awareness:
            return ExecutivePlan(
                decisions=[
                    self._decision(
                        session_id=session.session_id,
                        decision_type=ExecutiveDecisionType.DEFER_REPLY,
                        policy_name="disengagement_policy",
                        policy_outcome="uncertainty_admission",
                        executive_state=InteractionExecutiveState.DEGRADED,
                        event=event,
                        reason_codes=["perception_limited_world_model"],
                        note="world model recorded limited awareness from the latest perception update",
                        applied=False,
                    )
                ],
                intent="telemetry_update",
                skip_dialogue=True,
            )

        return ExecutivePlan()

    def evaluate_speech_pre(
        self,
        *,
        text: str,
        event: RobotEvent,
        session: SessionRecord,
        prior_world_model: EmbodiedWorldModel,
        world_model: EmbodiedWorldModel,
        user_memory: UserMemoryRecord | None,
        latest_perception: PerceptionSnapshotRecord | None,
    ) -> ExecutivePlan:
        del user_memory, latest_perception

        lowered = text.lower().strip()
        plan = ExecutivePlan()

        if is_recent_interrupt(prior_world_model, now=event.timestamp, interruption_window_seconds=self.interruption_window_seconds):
            plan.prepend_stop = True
            plan.decisions.append(
                self._decision(
                    session_id=session.session_id,
                    decision_type=ExecutiveDecisionType.STOP_FOR_INTERRUPTION,
                    policy_name="interruption_policy",
                    policy_outcome="interrupted",
                    executive_state=InteractionExecutiveState.INTERRUPTED,
                    event=event,
                    reason_codes=["user_interrupt_detected"],
                    note="incoming speech arrived while the robot was still responding",
                )
            )

        escalation_outcome = escalation_for_text(lowered, venue_knowledge=self.venue_knowledge)
        if escalation_outcome.outcome == "escalate":
            session.current_topic = "operator_handoff"
            session.session_memory["operator_escalation"] = "requested"
            session.session_memory["incident_reason_category"] = (
                escalation_outcome.reason_category or IncidentReasonCategory.ACCESSIBILITY.value
            )
            if escalation_outcome.urgency:
                session.session_memory["incident_urgency"] = escalation_outcome.urgency
            if escalation_outcome.staff_contact_key:
                session.session_memory["incident_staff_contact_key"] = escalation_outcome.staff_contact_key
            if escalation_outcome.policy_note:
                session.session_memory["incident_policy_note"] = escalation_outcome.policy_note
            session.status = SessionStatus.ESCALATION_PENDING
            reason_codes = (
                [f"escalation_due_to_site_rule:{escalation_outcome.reason_category}"]
                if escalation_outcome.reason_category and not accessibility_request(lowered)
                else ["escalation_due_to_accessibility_request"]
            )
            note = escalation_outcome.policy_note or "site escalation policy requested human handoff"
            plan.decisions.append(
                self._decision(
                    session_id=session.session_id,
                    decision_type=ExecutiveDecisionType.ESCALATE_TO_HUMAN,
                    policy_name=escalation_outcome.policy_name,
                    policy_outcome="escalated",
                    executive_state=InteractionExecutiveState.ESCALATING,
                    event=event,
                    reason_codes=reason_codes,
                    note=note,
                )
            )
            plan.reply_text = OPERATOR_ESCALATION["response_text"]
            plan.intent = "operator_handoff"
            plan.skip_dialogue = True
            return plan

        if should_keep_listening(lowered):
            session.current_topic = "listening"
            plan.decisions.append(
                self._decision(
                    session_id=session.session_id,
                    decision_type=ExecutiveDecisionType.KEEP_LISTENING,
                    policy_name="interruption_policy",
                    policy_outcome="keep_listening",
                    executive_state=InteractionExecutiveState.LISTENING,
                    event=event,
                    reason_codes=["keep_listening_brief_backchannel"],
                    note="brief backchannel or pause request should not trigger a full spoken answer",
                )
            )
            plan.intent = "listening"
            plan.skip_dialogue = True
            return plan

        if self._needs_clarification(lowered, session=session, world_model=world_model):
            session.current_topic = "clarify"
            plan.decisions.append(
                self._decision(
                    session_id=session.session_id,
                    decision_type=ExecutiveDecisionType.ASK_CLARIFYING_QUESTION,
                    policy_name="disengagement_policy",
                    policy_outcome="clarify",
                    executive_state=InteractionExecutiveState.THINKING,
                    event=event,
                    reason_codes=["clarify_missing_referent"],
                    note="visitor referred to an unclear room, event, or visual anchor",
                )
            )
            plan.reply_text = self._clarifying_reply(world_model)
            plan.intent = "clarify"
            plan.skip_dialogue = True
            return plan

        return plan

    def evaluate_speech_post(
        self,
        *,
        text: str,
        event: RobotEvent,
        session: SessionRecord,
        prior_world_model: EmbodiedWorldModel,
        world_model: EmbodiedWorldModel,
        latest_perception: PerceptionSnapshotRecord | None,
        reply_text: str | None,
        intent: str,
    ) -> ExecutivePlan:
        del session

        lowered = text.lower().strip()
        plan = ExecutivePlan()

        if intent == "operator_handoff" and not any(
            "escalation" in reason
            for reason in self._reason_codes(plan.decisions)
        ):
            plan.decisions.append(
                self._decision(
                    session_id=world_model.likely_user_session_id,
                    decision_type=ExecutiveDecisionType.ESCALATE_TO_HUMAN,
                    policy_name="escalation_policy",
                    policy_outcome="escalated",
                    executive_state=InteractionExecutiveState.ESCALATING,
                    event=event,
                    reason_codes=["operator_escalation_requested"],
                    note="tool or policy selected the human handoff path",
                )
            )

        if self._is_visual_query(lowered):
            if world_model.scene_freshness in {FactFreshness.STALE, FactFreshness.EXPIRED}:
                plan.decisions.append(
                    self._decision(
                        session_id=world_model.likely_user_session_id,
                        decision_type=ExecutiveDecisionType.DEFER_REPLY,
                        policy_name="disengagement_policy",
                        policy_outcome="stale_scene_suppressed",
                        executive_state=InteractionExecutiveState.DEGRADED,
                        event=event,
                        reason_codes=["stale_scene_visual_query"],
                        note="visual answer was constrained by stale scene context",
                        applied=False,
                    )
                )
            elif latest_perception is None or latest_perception.limited_awareness or latest_perception.status.value != "ok":
                plan.decisions.append(
                    self._decision(
                        session_id=world_model.likely_user_session_id,
                        decision_type=ExecutiveDecisionType.DEFER_REPLY,
                        policy_name="disengagement_policy",
                        policy_outcome="uncertainty_admission",
                        executive_state=InteractionExecutiveState.DEGRADED,
                        event=event,
                        reason_codes=["limited_visual_awareness_response"],
                        note="visual answer was constrained by limited situational awareness",
                        applied=False,
                    )
                )

        guardrail = reply_guardrail(
            prior_engagement_state=prior_world_model.engagement_state,
            reply_text=reply_text,
        )

        if reply_text and guardrail.outcome == "shorten_reply":
            shortened = shorten_reply(reply_text)
            if shortened != reply_text:
                plan.reply_text = shortened
                plan.decisions.append(
                    self._decision(
                        session_id=world_model.likely_user_session_id,
                        decision_type=ExecutiveDecisionType.SHORTEN_REPLY,
                        policy_name=guardrail.policy_name,
                        policy_outcome=guardrail.outcome,
                        executive_state=InteractionExecutiveState.RESPONDING,
                        event=event,
                        reason_codes=["engagement_low_short_reply"],
                        note="visitor looks like they are disengaging, so the reply was shortened",
                    )
                )

        if prior_world_model.engagement_state == EngagementState.LOST and should_keep_listening(lowered):
            plan.reply_text = None
            plan.decisions.append(
                self._decision(
                    session_id=world_model.likely_user_session_id,
                    decision_type=ExecutiveDecisionType.DEFER_REPLY,
                    policy_name=guardrail.policy_name,
                    policy_outcome="stale_scene_suppressed",
                    executive_state=InteractionExecutiveState.MONITORING,
                    event=event,
                    reason_codes=["engagement_lost_defer_reply"],
                    note="interaction looked lost and the utterance was too brief to answer confidently",
                )
            )

        return plan

    def _last_greet_at(self, session: SessionRecord) -> datetime | None:
        stored = session.session_memory.get("last_auto_greet_at")
        if not stored:
            return None
        try:
            return datetime.fromisoformat(stored)
        except ValueError:
            return None

    def _build_greeting(self, *, session: SessionRecord, user_memory: UserMemoryRecord | None) -> str:
        if self._context_mode_for_session(session) == CompanionContextMode.PERSONAL_LOCAL:
            if user_memory and user_memory.display_name:
                greeting = f"Welcome back, {user_memory.display_name}. Want to pick up where we left off or plan the day?"
            else:
                greeting = (
                    "Hi. I'm Blink-AI. I can help with notes, reminders, planning, workspace context, "
                    "and grounded local questions."
                )
            if session.response_mode == ResponseMode.AMBASSADOR:
                greeting = f"Good to see you. {greeting}"
            elif session.response_mode == ResponseMode.DEBUG:
                greeting = f"[debug mode] presence_detected; greeting={greeting}"
            return greeting

        site_name = self.venue_knowledge.site_name if self.venue_knowledge else "Blink-AI"
        policy = self._greeting_policy(session=session)
        greeting = policy.greeting_text if policy and policy.greeting_text else f"Hello! Welcome to {site_name}."
        if user_memory and user_memory.display_name:
            returning_text = (
                policy.returning_greeting_text
                if policy and policy.returning_greeting_text
                else f"Welcome back, {user_memory.display_name}. How can I help today?"
            )
            greeting = returning_text.replace("{name}", user_memory.display_name)
        if session.response_mode == ResponseMode.AMBASSADOR:
            greeting = f"Good to see you. {greeting}"
        elif session.response_mode == ResponseMode.DEBUG:
            greeting = f"[debug mode] presence_detected; greeting={greeting}"
        return greeting

    def _needs_clarification(
        self,
        lowered: str,
        *,
        session: SessionRecord,
        world_model: EmbodiedWorldModel,
    ) -> bool:
        ambiguous_phrases = {
            "where is that",
            "where is it",
            "which one",
            "what about that",
            "can you show me that",
            "what room is that",
        }
        if lowered not in ambiguous_phrases:
            return False
        if session.session_memory.get("last_location") or session.session_memory.get("last_event_id"):
            return False
        return world_model.attention_target is None

    def _clarifying_reply(self, world_model: EmbodiedWorldModel) -> str:
        if world_model.attention_target and world_model.attention_target.target_label:
            return (
                f"Do you mean {world_model.attention_target.target_label}, or should I help with a room or event name?"
            )
        return "Which room, event, or sign do you mean?"

    def _greeting_policy(self, *, session: SessionRecord | None = None):
        context_mode = self._context_mode_for_session(session) if session is not None else self.context_mode
        if context_mode == CompanionContextMode.PERSONAL_LOCAL:
            return None
        if self.venue_knowledge is None:
            return None
        return self.venue_knowledge.operations.proactive_greeting_policy

    def _context_mode_for_session(self, session: SessionRecord | None) -> CompanionContextMode:
        if session is not None and session.scenario_name:
            return CompanionContextMode.VENUE_DEMO
        return self.context_mode

    def _attention_reply(self, *, session: SessionRecord | None = None) -> str:
        if self._context_mode_for_session(session) == CompanionContextMode.PERSONAL_LOCAL:
            return "I am ready. I can help with notes, reminders, planning, or current local context."
        return "I am ready to help with directions, events, feedback, or staff handoff."

    def _greeting_cooldown_seconds(self, *, session: SessionRecord | None = None) -> float:
        policy = self._greeting_policy(session=session)
        return policy.cooldown_seconds if policy is not None else self.auto_greet_cooldown_seconds

    def _is_visual_query(self, lowered: str) -> bool:
        return looks_like_visual_query(lowered) or "read the text" in lowered

    def _decision(
        self,
        *,
        session_id: str | None,
        decision_type: ExecutiveDecisionType,
        policy_name: str | None,
        policy_outcome: str | None,
        suppressed_reason: str | None = None,
        executive_state: InteractionExecutiveState,
        event: RobotEvent,
        reason_codes: list[str],
        note: str,
        applied: bool = True,
    ) -> ExecutiveDecisionRecord:
        return ExecutiveDecisionRecord(
            session_id=session_id,
            decision_type=decision_type,
            policy_name=policy_name,
            policy_outcome=policy_outcome,
            suppressed_reason=suppressed_reason,
            executive_state=executive_state,
            trigger_event_type=event.event_type,
            applied=applied,
            reason_codes=reason_codes,
            note=note,
            created_at=utc_now(),
        )

    def _reason_codes(self, decisions: list[ExecutiveDecisionRecord]) -> list[str]:
        return [reason for decision in decisions for reason in decision.reason_codes]
