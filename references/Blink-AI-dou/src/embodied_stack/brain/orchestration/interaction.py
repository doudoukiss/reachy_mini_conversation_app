from __future__ import annotations

import logging
import re
from time import perf_counter
from typing import Callable

from embodied_stack.brain.agent_os import AgentRuntime, EmbodiedActionPolicy
from embodied_stack.brain.agent_os.models import AgentTurnContext
from embodied_stack.brain.executive import InteractionExecutive
from embodied_stack.brain.incident_workflow import IncidentWorkflow
from embodied_stack.brain.llm import DialogueEngine
from embodied_stack.brain.memory import MemoryStore
from embodied_stack.brain.orchestration.grounding import GroundingSourceBuilder
from embodied_stack.brain.participant_router import ParticipantRoutePlan
from embodied_stack.brain.planner_interface import PlannerAdapter
from embodied_stack.brain.shift_supervisor import ShiftSupervisorPlan
from embodied_stack.brain.tools import KnowledgeToolbox
from embodied_stack.brain.visual_query import looks_like_visual_query
from embodied_stack.config import Settings
from embodied_stack.shared.contracts import (
    CommandBatch,
    CommandType,
    CompanionContextMode,
    ConversationTurn,
    EmbodiedWorldModel,
    ExecutiveDecisionRecord,
    ExecutiveDecisionType,
    LatencyBreakdownRecord,
    PerceptionEventType,
    PerceptionObservationType,
    PerceptionProviderMode,
    PerceptionSnapshotRecord,
    ReasoningTrace,
    RobotCommand,
    RobotEvent,
    SessionRecord,
    SessionStatus,
    UserMemoryRecord,
)

logger = logging.getLogger(__name__)


class InteractionHandler:
    def __init__(
        self,
        *,
        settings: Settings,
        memory: MemoryStore,
        knowledge_tools: KnowledgeToolbox,
        dialogue_engine: DialogueEngine,
        action_policy: EmbodiedActionPolicy,
        agent_runtime: AgentRuntime,
        planner_adapter: PlannerAdapter,
        executive: InteractionExecutive,
        incident_workflow: IncidentWorkflow,
        grounding: GroundingSourceBuilder,
        ensure_user_memory: Callable[[SessionRecord], UserMemoryRecord | None],
    ) -> None:
        self.settings = settings
        self.memory = memory
        self.knowledge_tools = knowledge_tools
        self.dialogue_engine = dialogue_engine
        self.action_policy = action_policy
        self.agent_runtime = agent_runtime
        self.planner_adapter = planner_adapter
        self.executive = executive
        self.incident_workflow = incident_workflow
        self.grounding = grounding
        self.ensure_user_memory = ensure_user_memory

    def handle_speech_event(
        self,
        *,
        text: str,
        event: RobotEvent,
        session: SessionRecord,
        user_memory: UserMemoryRecord | None,
        prior_world_model: EmbodiedWorldModel,
        world_model: EmbodiedWorldModel,
        route_plan: ParticipantRoutePlan | None = None,
        shift_plan: ShiftSupervisorPlan | None = None,
    ) -> tuple[CommandBatch, ReasoningTrace, SessionRecord, UserMemoryRecord | None, list[ExecutiveDecisionRecord]]:
        try:
            latest_perception = self._latest_perception(session.session_id, text=text)
            agent_context = self.build_agent_context(
                text=text,
                event=event,
                session=session,
                user_memory=user_memory,
                world_model=world_model,
                latest_perception=latest_perception,
            )

            if route_plan is not None and route_plan.skip_interaction and route_plan.intent is not None:
                audit = self.planner_adapter.audit_event(
                    context=agent_context,
                    safe_idle_active=route_plan.intent == "safe_idle",
                    preferred_skill_name=self._preferred_skill_for_intent(route_plan.intent, session=session),
                )
                commands = self.build_commands(route_plan.intent, route_plan.reply_text)
                if route_plan.prepend_stop:
                    commands = self.prepend_stop_command(commands, reason="participant_reorientation")
                response = CommandBatch(
                    session_id=session.session_id,
                    reply_text=route_plan.reply_text,
                    commands=commands,
                    status=session.status,
                )
                reasoning = self._build_reasoning_trace(
                    engine="system",
                    intent=route_plan.intent,
                    session=session,
                    user_memory=user_memory,
                    latest_perception=latest_perception,
                    world_model=world_model,
                    latency=LatencyBreakdownRecord(),
                    audit=audit,
                    notes=list(route_plan.notes),
                )
                return response, reasoning, session, user_memory, []

            if shift_plan is not None and shift_plan.skip_interaction and shift_plan.intent is not None:
                audit = self.planner_adapter.audit_event(
                    context=agent_context,
                    safe_idle_active=shift_plan.intent == "safe_idle",
                    preferred_skill_name=self._preferred_skill_for_intent(shift_plan.intent, session=session),
                )
                response = CommandBatch(
                    session_id=session.session_id,
                    reply_text=shift_plan.reply_text,
                    commands=self.build_commands(shift_plan.intent, shift_plan.reply_text),
                    status=session.status,
                )
                reasoning = self._build_reasoning_trace(
                    engine="system",
                    intent=shift_plan.intent,
                    session=session,
                    user_memory=user_memory,
                    latest_perception=latest_perception,
                    world_model=world_model,
                    latency=LatencyBreakdownRecord(),
                    audit=audit,
                    notes=list(shift_plan.notes),
                )
                return response, reasoning, session, user_memory, []

            executive_pre_start = perf_counter()
            pre_plan = self.executive.evaluate_speech_pre(
                text=text,
                event=event,
                session=session,
                prior_world_model=prior_world_model,
                world_model=world_model,
                user_memory=user_memory,
                latest_perception=latest_perception,
            )
            executive_pre_ms = round((perf_counter() - executive_pre_start) * 1000.0, 2)

            if pre_plan.skip_dialogue and pre_plan.intent is not None:
                audit = self.planner_adapter.audit_event(
                    context=agent_context,
                    safe_idle_active=pre_plan.intent == "safe_idle",
                    preferred_skill_name=self._preferred_skill_for_intent(pre_plan.intent, session=session),
                )
                commands = self.build_commands(pre_plan.intent, pre_plan.reply_text)
                if pre_plan.prepend_stop:
                    commands = self.prepend_stop_command(commands, reason="user_interrupt")
                response = CommandBatch(
                    session_id=session.session_id,
                    reply_text=pre_plan.reply_text,
                    commands=commands,
                    status=session.status,
                )
                reasoning = self._build_reasoning_trace(
                    engine="system",
                    intent=pre_plan.intent,
                    session=session,
                    user_memory=user_memory,
                    latest_perception=latest_perception,
                    world_model=world_model,
                    latency=LatencyBreakdownRecord(
                        executive_pre_ms=executive_pre_ms,
                        executive_ms=executive_pre_ms,
                    ),
                    audit=audit,
                    notes=list(pre_plan.notes),
                )
                return response, reasoning, session, user_memory, pre_plan.decisions

            incident_reply = self.incident_workflow.maybe_build_status_reply(session=session, text=text)
            if incident_reply is not None:
                session.current_topic = "operator_handoff"
                audit = self.planner_adapter.audit_event(
                    context=agent_context,
                    preferred_skill_name=self._preferred_skill_for_intent(incident_reply.intent, session=session),
                )
                commands = self.build_commands(incident_reply.intent, incident_reply.reply_text)
                if pre_plan.prepend_stop:
                    commands = self.prepend_stop_command(commands, reason="user_interrupt")
                response = CommandBatch(
                    session_id=session.session_id,
                    reply_text=incident_reply.reply_text,
                    commands=commands,
                    status=session.status,
                )
                reasoning = self._build_reasoning_trace(
                    engine="system",
                    intent=incident_reply.intent,
                    session=session,
                    user_memory=user_memory,
                    latest_perception=latest_perception,
                    world_model=world_model,
                    latency=LatencyBreakdownRecord(
                        executive_pre_ms=executive_pre_ms,
                        executive_ms=executive_pre_ms,
                    ),
                    audit=audit,
                    notes=list(incident_reply.notes),
                )
                return response, reasoning, session, user_memory, pre_plan.decisions

            extracted_memory = self.extract_memory_updates(text=text)
            profile_updates = self.extract_profile_updates(text=text)
            user_memory = user_memory or self.ensure_user_memory(session)
            tool_start = perf_counter()
            tool_invocations = self.knowledge_tools.lookup(
                text,
                session=session,
                user_memory=user_memory,
                world_state=self.memory.get_world_state(),
                world_model=world_model,
                latest_perception=latest_perception,
            )
            tool_ms = round((perf_counter() - tool_start) * 1000.0, 2)
            memory_updates = {**extracted_memory}
            for tool in tool_invocations:
                memory_updates.update(tool.memory_updates)

            if user_memory:
                if "remembered_name" in memory_updates:
                    user_memory.display_name = memory_updates["remembered_name"]
                if session.response_mode:
                    user_memory.preferred_response_mode = session.response_mode
                for key, value in profile_updates["facts"].items():
                    user_memory.facts[key] = value
                for key, value in profile_updates["preferences"].items():
                    user_memory.preferences[key] = value
                for interest in profile_updates["interests"]:
                    if interest not in user_memory.interests:
                        user_memory.interests.append(interest)
                relationship_profile = user_memory.relationship_profile
                relationship_updates = profile_updates["relationship_profile"]
                if relationship_updates["greeting_preference"] is not None:
                    relationship_profile.greeting_preference = relationship_updates["greeting_preference"]
                if relationship_updates["planning_style"] is not None:
                    relationship_profile.planning_style = relationship_updates["planning_style"]
                for tone in relationship_updates["tone_preferences"]:
                    if tone not in relationship_profile.tone_preferences:
                        relationship_profile.tone_preferences.append(tone)
                for boundary in relationship_updates["interaction_boundaries"]:
                    if boundary not in relationship_profile.interaction_boundaries:
                        relationship_profile.interaction_boundaries.append(boundary)
                for preference in relationship_updates["continuity_preferences"]:
                    if preference not in relationship_profile.continuity_preferences:
                        relationship_profile.continuity_preferences.append(preference)

            session.session_memory.update(memory_updates)
            if current_topic := memory_updates.get("last_topic"):
                session.current_topic = current_topic
            if session.session_memory.get("operator_escalation") == "requested":
                session.status = SessionStatus.ESCALATION_PENDING

            dialogue_start = perf_counter()
            agent_plan = self.planner_adapter.plan_speech_turn(
                context=self.build_agent_context(
                    text=text,
                    event=event,
                    session=session,
                    user_memory=user_memory,
                    world_model=world_model,
                    latest_perception=latest_perception,
                ),
                tool_invocations=tool_invocations,
                memory_updates=memory_updates,
            )
            dialogue_ms = round((perf_counter() - dialogue_start) * 1000.0, 2)

            executive_post_start = perf_counter()
            post_plan = self.executive.evaluate_speech_post(
                text=text,
                event=event,
                session=session,
                prior_world_model=prior_world_model,
                world_model=world_model,
                latest_perception=latest_perception,
                reply_text=agent_plan.reply_text,
                intent=agent_plan.intent,
            )
            executive_post_ms = round((perf_counter() - executive_post_start) * 1000.0, 2)
            reply_text = self.apply_reply_override(
                original_reply=agent_plan.reply_text,
                decisions=post_plan.decisions,
                override=post_plan.reply_text,
            )
            intent = post_plan.intent or agent_plan.intent
            commands = self.build_commands(intent, reply_text)
            if pre_plan.prepend_stop:
                commands = self.prepend_stop_command(commands, reason="user_interrupt")
            response = CommandBatch(
                session_id=session.session_id,
                reply_text=reply_text,
                commands=commands,
                status=session.status,
            )
            reasoning = ReasoningTrace(
                engine=agent_plan.engine_name,
                intent=intent,
                fallback_used=agent_plan.fallback_used,
                run_id=agent_plan.run_record.run_id if agent_plan.run_record is not None else None,
                run_phase=agent_plan.run_record.phase if agent_plan.run_record is not None else None,
                run_status=agent_plan.run_record.status if agent_plan.run_record is not None else None,
                instruction_layers=agent_plan.instruction_layers,
                active_skill=agent_plan.active_skill,
                active_playbook=agent_plan.active_skill.playbook_name if agent_plan.active_skill is not None else None,
                active_playbook_variant=agent_plan.active_skill.route_variant if agent_plan.active_skill is not None else None,
                active_subagent=agent_plan.active_subagent,
                tool_invocations=tool_invocations,
                typed_tool_calls=agent_plan.typed_tool_calls,
                tool_chain=[item.tool_name for item in agent_plan.typed_tool_calls],
                memory_updates=memory_updates,
                grounding_sources=self.grounding.collect(
                    session=session,
                    user_memory=user_memory,
                    tool_invocations=tool_invocations,
                    latest_perception=latest_perception,
                    world_model=world_model,
                ),
                latency_breakdown=LatencyBreakdownRecord(
                    executive_pre_ms=executive_pre_ms,
                    tool_ms=tool_ms,
                    dialogue_ms=dialogue_ms,
                    executive_post_ms=executive_post_ms,
                    executive_ms=round(executive_pre_ms + executive_post_ms, 2),
                ),
                hook_records=agent_plan.hook_records,
                role_decisions=agent_plan.role_decisions,
                validation_outcomes=agent_plan.validation_outcomes,
                checkpoint_count=len(agent_plan.checkpoints),
                last_checkpoint_id=(agent_plan.checkpoints[-1].checkpoint_id if agent_plan.checkpoints else None),
                failure_state=agent_plan.run_record.failure_state if agent_plan.run_record is not None else None,
                fallback_reason=agent_plan.run_record.fallback_reason if agent_plan.run_record is not None else None,
                fallback_classification=(
                    agent_plan.run_record.fallback_classification
                    if agent_plan.run_record is not None
                    else None
                ),
                unavailable_capabilities=(
                    list(agent_plan.run_record.unavailable_capabilities)
                    if agent_plan.run_record is not None
                    else []
                ),
                intentionally_skipped_capabilities=(
                    list(agent_plan.run_record.intentionally_skipped_capabilities)
                    if agent_plan.run_record is not None
                    else []
                ),
                recovery_status=(
                    agent_plan.run_record.status.value
                    if agent_plan.run_record is not None
                    and agent_plan.run_record.status.value in {"paused", "awaiting_confirmation", "aborted"}
                    else None
                ),
                replayed_from_run_id=agent_plan.run_record.replayed_from_run_id if agent_plan.run_record is not None else None,
                resumed_from_checkpoint_id=agent_plan.run_record.resumed_from_checkpoint_id if agent_plan.run_record is not None else None,
                executive_state=world_model.executive_state,
                social_runtime_mode=world_model.social_runtime_mode,
                notes=agent_plan.notes,
            )
            return response, reasoning, session, user_memory, [*pre_plan.decisions, *post_plan.decisions]
        except Exception:
            logger.exception("Speech interaction helper failed for session %s", session.session_id)
            raise

    def handle_non_speech_event(
        self,
        *,
        event: RobotEvent,
        session: SessionRecord,
        user_memory: UserMemoryRecord | None,
        prior_world_model: EmbodiedWorldModel,
        world_model: EmbodiedWorldModel,
        route_plan: ParticipantRoutePlan | None = None,
        shift_plan: ShiftSupervisorPlan | None = None,
    ) -> tuple[CommandBatch, ReasoningTrace, SessionRecord, list[ExecutiveDecisionRecord]]:
        del route_plan
        try:
            latest_perception = self._latest_perception(session.session_id, text="")
            agent_context = self.build_agent_context(
                text="",
                event=event,
                session=session,
                user_memory=user_memory,
                world_model=world_model,
                latest_perception=latest_perception,
            )
            if shift_plan is not None and shift_plan.skip_interaction and shift_plan.intent is not None:
                audit = self.planner_adapter.audit_event(
                    context=agent_context,
                    safe_idle_active=shift_plan.intent == "safe_idle",
                    preferred_skill_name=self._preferred_skill_for_intent(shift_plan.intent, session=session),
                )
                response = CommandBatch(
                    session_id=session.session_id,
                    reply_text=shift_plan.reply_text,
                    commands=self.build_commands(shift_plan.intent, shift_plan.reply_text),
                    status=session.status,
                )
                return (
                    response,
                    self._build_reasoning_trace(
                        engine="system",
                        intent=shift_plan.intent,
                        session=session,
                        user_memory=user_memory,
                        latest_perception=latest_perception,
                        world_model=world_model,
                        latency=LatencyBreakdownRecord(),
                        audit=audit,
                        notes=list(shift_plan.notes),
                    ),
                    session,
                    [],
                )
            executive_start = perf_counter()
            plan = self.executive.evaluate_non_speech(
                event=event,
                session=session,
                prior_world_model=prior_world_model,
                world_model=world_model,
                user_memory=user_memory,
            )
            executive_ms = round((perf_counter() - executive_start) * 1000.0, 2)
            if plan.skip_dialogue and plan.intent is not None:
                audit = self.planner_adapter.audit_event(
                    context=agent_context,
                    safe_idle_active=plan.intent == "safe_idle",
                    preferred_skill_name=self._preferred_skill_for_intent(plan.intent, session=session),
                )
                response = CommandBatch(
                    session_id=session.session_id,
                    reply_text=plan.reply_text,
                    commands=self.build_commands(plan.intent, plan.reply_text),
                    status=session.status,
                )
                return (
                    response,
                    self._build_reasoning_trace(
                        engine="system",
                        intent=plan.intent,
                        session=session,
                        user_memory=user_memory,
                        latest_perception=latest_perception,
                        world_model=world_model,
                        latency=LatencyBreakdownRecord(
                            executive_ms=executive_ms,
                        ),
                        audit=audit,
                        notes=[f"event_match:{event.event_type}", *plan.notes],
                    ),
                    session,
                    plan.decisions,
                )

            if event.event_type in {
                "heartbeat",
                "telemetry",
                PerceptionEventType.PERSON_LEFT.value,
                PerceptionEventType.PEOPLE_COUNT_CHANGED.value,
                PerceptionEventType.ENGAGEMENT_ESTIMATE_CHANGED.value,
                PerceptionEventType.VISIBLE_TEXT_DETECTED.value,
                PerceptionEventType.NAMED_OBJECT_DETECTED.value,
                PerceptionEventType.LOCATION_ANCHOR_DETECTED.value,
                PerceptionEventType.SCENE_SUMMARY_UPDATED.value,
            }:
                audit = self.planner_adapter.audit_event(
                    context=agent_context,
                    safe_idle_active=session.current_topic == "safe_idle",
                    preferred_skill_name="observe_and_comment",
                )
                response = CommandBatch(
                    session_id=session.session_id,
                    reply_text=None,
                    commands=[],
                    status=session.status,
                )
                return (
                    response,
                    self._build_reasoning_trace(
                        engine="system",
                        intent="telemetry_update",
                        session=session,
                        user_memory=user_memory,
                        latest_perception=latest_perception,
                        world_model=world_model,
                        latency=LatencyBreakdownRecord(executive_ms=executive_ms),
                        audit=audit,
                        notes=[f"event_match:{event.event_type}", *plan.notes],
                    ),
                    session,
                    plan.decisions,
                )

            audit = self.planner_adapter.audit_event(
                context=agent_context,
                safe_idle_active=session.current_topic == "safe_idle",
            )
            response = CommandBatch(
                session_id=session.session_id,
                reply_text=None,
                commands=[],
                status=session.status,
            )
            return (
                response,
                self._build_reasoning_trace(
                    engine="system",
                    intent="noop",
                    session=session,
                    user_memory=user_memory,
                    latest_perception=latest_perception,
                    world_model=world_model,
                    latency=LatencyBreakdownRecord(executive_ms=executive_ms),
                    audit=audit,
                    notes=["event_match:noop", *plan.notes],
                ),
                session,
                plan.decisions,
            )
        except Exception:
            logger.exception(
                "Non-speech interaction helper failed for session %s on event %s",
                session.session_id,
                event.event_type,
            )
            raise

    def extract_memory_updates(self, *, text: str) -> dict[str, str]:
        lowered = text.lower().strip()
        updates: dict[str, str] = {}
        if match := re.search(r"(?:my name is|i am|i'm)\s+([a-z][a-z\-']+)", lowered):
            updates["remembered_name"] = match.group(1).strip(" .,!?:;").title()
            updates["last_topic"] = "introduction"
        return updates

    def extract_profile_updates(self, *, text: str) -> dict[str, object]:
        lowered = text.lower().strip()
        facts: dict[str, str] = {}
        preferences: dict[str, str] = {}
        interests: list[str] = []
        relationship_profile = {
            "greeting_preference": None,
            "planning_style": None,
            "tone_preferences": [],
            "interaction_boundaries": [],
            "continuity_preferences": [],
        }

        if match := re.search(r"(?:my name is|i am|i'm)\s+([a-z][a-z\-']+)", lowered):
            facts["remembered_name"] = match.group(1).strip(" .,!?:;").title()

        if "quiet route" in lowered:
            preferences["route_preference"] = "quiet route"
        elif "accessible route" in lowered or "wheelchair" in lowered:
            preferences["route_preference"] = "accessible route"
        elif match := re.search(r"i prefer\s+([^.!?]+)", lowered):
            stated_preference = match.group(1).strip(" .,!?:;")
            preferences["stated_preference"] = stated_preference
            self._apply_relationship_phrase(
                stated_preference.lower(),
                relationship_profile=relationship_profile,
            )

        if match := re.search(r"i like\s+([^.!?]+)", lowered):
            interest = match.group(1).strip(" .,!?:;")
            if interest:
                interests.append(interest)

        self._apply_relationship_phrase(lowered, relationship_profile=relationship_profile)

        return {
            "facts": facts,
            "preferences": preferences,
            "interests": interests,
            "relationship_profile": relationship_profile,
        }

    def _apply_relationship_phrase(
        self,
        text: str,
        *,
        relationship_profile: dict[str, object],
    ) -> None:
        lowered = text.lower().strip()
        if not lowered:
            return
        if any(phrase in lowered for phrase in ("keep greetings brief", "brief greeting")):
            relationship_profile["greeting_preference"] = "brief"
        if any(phrase in lowered for phrase in ("one step at a time", "step by step")):
            relationship_profile["planning_style"] = "one_step_at_a_time"
        if any(phrase in lowered for phrase in ("keep it brief", "be brief", "keep replies brief", "keep it concise", "brief and direct")):
            self._append_relationship_value(relationship_profile["tone_preferences"], "brief")
        if any(phrase in lowered for phrase in ("be direct", "keep it direct", "direct answers", "direct replies", "brief and direct")):
            self._append_relationship_value(relationship_profile["tone_preferences"], "direct")
        if any(phrase in lowered for phrase in ("be calm", "keep it calm", "keep it steady")):
            self._append_relationship_value(relationship_profile["tone_preferences"], "calm")
        if any(phrase in lowered for phrase in ("don't be chatty", "do not be chatty")):
            self._append_relationship_value(relationship_profile["interaction_boundaries"], "avoid_chatty_small_talk")
        if any(
            phrase in lowered
            for phrase in ("don't use my name every time", "do not use my name every time", "don't repeat my name")
        ):
            self._append_relationship_value(relationship_profile["interaction_boundaries"], "avoid_repeating_name")
        if any(
            phrase in lowered
            for phrase in (
                "pick up where we left off",
                "remind me where we left off",
                "where we left off",
                "keep track of open threads",
                "follow up on unfinished things",
            )
        ):
            self._append_relationship_value(relationship_profile["continuity_preferences"], "resume_open_threads")

    def _append_relationship_value(self, target: object, value: str) -> None:
        if not isinstance(target, list):
            return
        if value not in target:
            target.append(value)

    def build_commands(self, intent: str, reply_text: str | None) -> list[RobotCommand]:
        return self.action_policy.build_commands(intent, reply_text)

    def _build_legacy_commands(self, intent: str, reply_text: str | None) -> list[RobotCommand]:
        commands: list[RobotCommand] = []

        if intent == "greeting":
            commands.append(RobotCommand(command_type=CommandType.SET_LED, payload={"color": "blue"}))
            commands.append(
                RobotCommand(
                    command_type=CommandType.SET_HEAD_POSE,
                    payload={"head_yaw_deg": 8.0, "head_pitch_deg": 0.0},
                )
            )
        elif intent in {"wayfinding", "events", "faq", "capabilities", "feedback", "perception_query"}:
            commands.append(RobotCommand(command_type=CommandType.SET_LED, payload={"color": "green"}))
        elif intent in {"operator_handoff", "operator_handoff_pending", "operator_handoff_unavailable"}:
            commands.append(RobotCommand(command_type=CommandType.SET_LED, payload={"color": "amber"}))
        elif intent == "operator_handoff_accepted":
            commands.append(RobotCommand(command_type=CommandType.SET_LED, payload={"color": "blue"}))
        elif intent == "operator_handoff_resolved":
            commands.append(RobotCommand(command_type=CommandType.SET_LED, payload={"color": "green"}))
        elif intent == "safe_idle":
            commands.append(RobotCommand(command_type=CommandType.SET_LED, payload={"color": "amber"}))
            commands.append(RobotCommand(command_type=CommandType.STOP, payload={"reason": "safe_idle"}))
        elif intent in {"attention", "clarify", "listening", "attract_prompt", "queue_wait", "crowd_reorientation"}:
            commands.append(RobotCommand(command_type=CommandType.SET_LED, payload={"color": "white"}))

        if reply_text:
            commands.append(RobotCommand(command_type=CommandType.DISPLAY_TEXT, payload={"text": reply_text}))
            commands.append(RobotCommand(command_type=CommandType.SPEAK, payload={"text": reply_text}))

        return commands

    def _build_desktop_commands(self, intent: str, reply_text: str | None) -> list[RobotCommand]:
        commands: list[RobotCommand] = []

        if intent == "greeting":
            commands.append(RobotCommand(command_type=CommandType.SET_LED, payload={"color": "blue"}))
            commands.append(RobotCommand(command_type=CommandType.SET_EXPRESSION, payload={"expression": "friendly"}))
            commands.append(RobotCommand(command_type=CommandType.SET_GAZE, payload={"target": "look_at_user"}))
            commands.append(RobotCommand(command_type=CommandType.PERFORM_GESTURE, payload={"gesture": "nod_small"}))
        elif intent in {"wayfinding", "events", "faq", "capabilities", "feedback", "perception_query"}:
            commands.append(RobotCommand(command_type=CommandType.SET_LED, payload={"color": "green"}))
            commands.append(RobotCommand(command_type=CommandType.SET_EXPRESSION, payload={"expression": "listen_attentively"}))
            commands.append(RobotCommand(command_type=CommandType.SET_GAZE, payload={"target": "look_forward"}))
        elif intent in {"operator_handoff", "operator_handoff_pending", "operator_handoff_unavailable"}:
            commands.append(RobotCommand(command_type=CommandType.SET_LED, payload={"color": "amber"}))
            commands.append(RobotCommand(command_type=CommandType.SET_EXPRESSION, payload={"expression": "thinking"}))
        elif intent == "operator_handoff_accepted":
            commands.append(RobotCommand(command_type=CommandType.SET_LED, payload={"color": "blue"}))
            commands.append(RobotCommand(command_type=CommandType.SET_EXPRESSION, payload={"expression": "listen_attentively"}))
        elif intent == "operator_handoff_resolved":
            commands.append(RobotCommand(command_type=CommandType.SET_LED, payload={"color": "green"}))
            commands.append(RobotCommand(command_type=CommandType.SET_EXPRESSION, payload={"expression": "friendly"}))
        elif intent == "safe_idle":
            commands.append(RobotCommand(command_type=CommandType.SET_LED, payload={"color": "amber"}))
            commands.append(RobotCommand(command_type=CommandType.SAFE_IDLE, payload={"reason": "safe_idle"}))
        elif intent in {"attention", "clarify", "listening", "attract_prompt", "queue_wait", "crowd_reorientation"}:
            commands.append(RobotCommand(command_type=CommandType.SET_LED, payload={"color": "white"}))
            commands.append(RobotCommand(command_type=CommandType.SET_EXPRESSION, payload={"expression": "listen_attentively"}))
            commands.append(RobotCommand(command_type=CommandType.SET_GAZE, payload={"target": "look_forward"}))

        if reply_text:
            commands.append(RobotCommand(command_type=CommandType.DISPLAY_TEXT, payload={"text": reply_text}))
            commands.append(RobotCommand(command_type=CommandType.SPEAK, payload={"text": reply_text}))

        return commands

    def build_turn(
        self,
        *,
        event: RobotEvent,
        response: CommandBatch,
        intent: str,
        trace_id: str,
        participant_id: str | None,
        incident_ticket_id: str | None,
        executive_reason_codes: list[str],
    ) -> ConversationTurn:
        user_text = None
        if event.event_type == "speech_transcript":
            user_text = str(event.payload.get("text", "")).strip()
        return ConversationTurn(
            event_type=event.event_type,
            source=event.source,
            participant_id=participant_id,
            incident_ticket_id=incident_ticket_id,
            user_text=user_text,
            reply_text=response.reply_text,
            intent=intent,
            trace_id=trace_id,
            command_types=[command.command_type for command in response.commands],
            executive_reason_codes=executive_reason_codes,
        )

    def override_response_reply(
        self,
        *,
        response: CommandBatch,
        intent: str,
        reply_text: str,
    ) -> CommandBatch:
        stop_commands = [
            command.model_copy(deep=True) for command in response.commands if command.command_type == CommandType.STOP
        ]
        rebuilt = self.build_commands(intent, reply_text)
        response.reply_text = reply_text
        response.commands = [*stop_commands, *rebuilt]
        return response

    def apply_reply_override(
        self,
        *,
        original_reply: str | None,
        decisions: list[ExecutiveDecisionRecord],
        override: str | None,
    ) -> str | None:
        if override is not None:
            return override
        if any(
            decision.decision_type == ExecutiveDecisionType.DEFER_REPLY and decision.applied
            for decision in decisions
        ):
            return None
        return original_reply

    def prepend_stop_command(self, commands: list[RobotCommand], *, reason: str) -> list[RobotCommand]:
        return self.action_policy.prepend_stop_command(commands, reason=reason)

    def annotate_decisions(
        self,
        decisions: list[ExecutiveDecisionRecord],
        *,
        session_id: str,
        commands: list[RobotCommand],
    ) -> list[ExecutiveDecisionRecord]:
        command_types = [command.command_type for command in commands]
        return [
            decision.model_copy(update={"session_id": decision.session_id or session_id, "command_types": command_types})
            for decision in decisions
        ]

    def reason_codes(self, decisions: list[ExecutiveDecisionRecord]) -> list[str]:
        return [reason for decision in decisions for reason in decision.reason_codes]

    def _latest_perception(self, session_id: str, *, text: str) -> PerceptionSnapshotRecord | None:
        session_history = self.memory.list_perception_history(session_id=session_id, limit=10).items
        global_history = self.memory.list_perception_history(limit=10).items if not session_history else []
        return select_dialogue_perception_snapshot(
            session_history or global_history,
            visual_query=looks_like_visual_query(text),
        )

    def build_agent_context(
        self,
        *,
        text: str,
        event: RobotEvent,
        session: SessionRecord,
        user_memory: UserMemoryRecord | None,
        world_model: EmbodiedWorldModel,
        latest_perception: PerceptionSnapshotRecord | None,
    ) -> AgentTurnContext:
        return AgentTurnContext(
            text=text,
            event=event,
            session=session,
            context_mode=self.knowledge_tools.resolved_context_mode(session=session),
            user_memory=user_memory,
            world_state=self.memory.get_world_state(),
            world_model=world_model,
            latest_perception=latest_perception,
            backend_status=self.agent_runtime.backend_router.runtime_statuses(),
            replayed_from_run_id=(
                str(event.payload.get("agent_os_replayed_from_run_id"))
                if isinstance(event.payload, dict) and event.payload.get("agent_os_replayed_from_run_id") is not None
                else None
            ),
            resumed_from_checkpoint_id=(
                str(event.payload.get("agent_os_resumed_from_checkpoint_id"))
                if isinstance(event.payload, dict) and event.payload.get("agent_os_resumed_from_checkpoint_id") is not None
                else None
            ),
        )

    def _build_reasoning_trace(
        self,
        *,
        engine: str,
        intent: str,
        session: SessionRecord,
        user_memory: UserMemoryRecord | None,
        latest_perception: PerceptionSnapshotRecord | None,
        world_model: EmbodiedWorldModel,
        latency: LatencyBreakdownRecord,
        audit,
        notes: list[str],
    ) -> ReasoningTrace:
        grounding_sources = self.grounding.collect(
            session=session,
            user_memory=user_memory,
            tool_invocations=[],
            latest_perception=latest_perception,
            world_model=world_model,
        )
        grounded_scene_references = [
            item
            for item in grounding_sources
            if item.fact_id is not None or item.claim_kind is not None
        ]
        return ReasoningTrace(
            engine=engine,
            intent=intent,
            run_id=audit.run_record.run_id if audit.run_record is not None else None,
            run_phase=audit.run_record.phase if audit.run_record is not None else None,
            run_status=audit.run_record.status if audit.run_record is not None else None,
            instruction_layers=audit.instruction_layers,
            active_skill=audit.active_skill,
            active_playbook=audit.active_skill.playbook_name if audit.active_skill is not None else None,
            active_playbook_variant=audit.active_skill.route_variant if audit.active_skill is not None else None,
            active_subagent=audit.active_subagent,
            typed_tool_calls=audit.typed_tool_calls,
            tool_chain=[item.tool_name for item in audit.typed_tool_calls],
            grounding_sources=grounding_sources,
            latency_breakdown=latency,
            hook_records=audit.hook_records,
            role_decisions=audit.role_decisions,
            validation_outcomes=audit.validation_outcomes,
            checkpoint_count=len(audit.checkpoints),
            last_checkpoint_id=(audit.checkpoints[-1].checkpoint_id if audit.checkpoints else None),
            failure_state=audit.run_record.failure_state if audit.run_record is not None else None,
            fallback_reason=audit.run_record.fallback_reason if audit.run_record is not None else None,
            fallback_classification=audit.run_record.fallback_classification if audit.run_record is not None else None,
            unavailable_capabilities=(
                list(audit.run_record.unavailable_capabilities) if audit.run_record is not None else []
            ),
            intentionally_skipped_capabilities=(
                list(audit.run_record.intentionally_skipped_capabilities) if audit.run_record is not None else []
            ),
            recovery_status=(
                audit.run_record.status.value
                if audit.run_record is not None
                and audit.run_record.status.value in {"paused", "awaiting_confirmation", "aborted"}
                else None
            ),
            replayed_from_run_id=audit.run_record.replayed_from_run_id if audit.run_record is not None else None,
            resumed_from_checkpoint_id=audit.run_record.resumed_from_checkpoint_id if audit.run_record is not None else None,
            executive_state=world_model.executive_state,
            social_runtime_mode=world_model.social_runtime_mode,
            grounded_scene_references=grounded_scene_references,
            uncertainty_admitted=False,
            stale_scene_suppressed=False,
            notes=[*notes, *audit.notes],
        )

    def _preferred_skill_for_intent(self, intent: str, *, session: SessionRecord | None = None) -> str | None:
        context_mode = (
            self.knowledge_tools.resolved_context_mode(session=session)
            if session is not None
            else self.settings.blink_context_mode
        )
        return {
            "attention": "companion_greeting_reentry"
            if context_mode == CompanionContextMode.PERSONAL_LOCAL
            else "welcome_guest",
            "events": "schedule_help",
            "greeting": "companion_greeting_reentry"
            if context_mode == CompanionContextMode.PERSONAL_LOCAL
            else "welcome_guest",
            "operator_handoff": "incident_escalation",
            "operator_handoff_pending": "incident_escalation",
            "operator_handoff_unavailable": "incident_escalation",
            "perception_query": "observe_and_comment",
            "safe_idle": "safe_degraded_response",
            "wayfinding": "wayfinding",
        }.get(intent)


_SEMANTIC_PERCEPTION_PROVIDERS = {
    PerceptionProviderMode.OLLAMA_VISION,
    PerceptionProviderMode.MULTIMODAL_LLM,
}


def select_dialogue_perception_snapshot(
    snapshots: list[PerceptionSnapshotRecord],
    *,
    visual_query: bool,
) -> PerceptionSnapshotRecord | None:
    if not snapshots:
        return None
    if visual_query:
        latest = max(snapshots, key=_perception_timestamp)
        if latest.limited_awareness and latest.status.value != "ok":
            older_grounded = [
                item
                for item in snapshots
                if item is not latest and not item.limited_awareness
            ]
            if not older_grounded:
                return latest
            freshest_grounded = max(older_grounded, key=_perception_timestamp)
            if _perception_timestamp(latest) - _perception_timestamp(freshest_grounded) >= 10.0:
                return latest
    return max(snapshots, key=lambda item: _dialogue_perception_priority(item, visual_query=visual_query))


def _dialogue_perception_priority(
    snapshot: PerceptionSnapshotRecord,
    *,
    visual_query: bool,
) -> tuple[int, int, int, int, float]:
    captured_at = snapshot.source_frame.captured_at or snapshot.created_at
    is_scene_observer_note = snapshot.tier.value == "watcher" or snapshot.source == "scene_observer"
    is_semantic = (snapshot.tier.value == "semantic" and not is_scene_observer_note) or snapshot.provider_mode in _SEMANTIC_PERCEPTION_PROVIDERS
    has_structured_observations = any(
        item.observation_type != PerceptionObservationType.SCENE_SUMMARY for item in snapshot.observations
    )
    status_score = {"ok": 2, "degraded": 1, "failed": 0}.get(snapshot.status.value, 0)
    if is_semantic and snapshot.status.value == "ok" and not snapshot.limited_awareness:
        quality_score = 4 if visual_query else 3
    elif is_semantic and snapshot.status.value != "failed":
        quality_score = 3 if visual_query else 2
    elif snapshot.status.value != "failed" and not is_scene_observer_note:
        quality_score = 2
    elif snapshot.status.value != "failed":
        quality_score = 1
    else:
        quality_score = 0
    richness_score = 2 if has_structured_observations else 0
    limitation_score = 0 if snapshot.limited_awareness else 1
    return (
        quality_score,
        status_score,
        limitation_score,
        richness_score,
        captured_at.timestamp(),
    )


def _perception_timestamp(snapshot: PerceptionSnapshotRecord) -> float:
    captured_at = snapshot.source_frame.captured_at or snapshot.created_at
    return captured_at.timestamp()
