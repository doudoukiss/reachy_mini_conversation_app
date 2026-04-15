from __future__ import annotations

import logging

from embodied_stack.brain.memory import MemoryStore
from embodied_stack.brain.participant_router import ParticipantSessionRouter
from embodied_stack.brain.shift_supervisor import ShiftSupervisor
from embodied_stack.brain.world_model import WorldModelRuntime
from embodied_stack.config import Settings
from embodied_stack.demo.community_scripts import COMMUNITY_EVENTS, COMMUNITY_LOCATIONS
from embodied_stack.shared.models import (
    CommandBatch,
    CommandType,
    EmbodiedWorldModel,
    IncidentListScope,
    PerceptionEventType,
    ReasoningTrace,
    RobotCommand,
    RobotEvent,
    RobotMode,
    SessionRecord,
    SessionStatus,
    TraceOutcome,
    UserMemoryRecord,
    utc_now,
)

logger = logging.getLogger(__name__)


class StateProjectionHelper:
    def __init__(
        self,
        *,
        memory: MemoryStore,
        world_model_runtime: WorldModelRuntime,
        shift_supervisor: ShiftSupervisor,
        participant_router: ParticipantSessionRouter,
        settings: Settings,
    ) -> None:
        self.memory = memory
        self.world_model_runtime = world_model_runtime
        self.shift_supervisor = shift_supervisor
        self.participant_router = participant_router
        self.settings = settings

    def world_model_changed_fields(
        self,
        before: EmbodiedWorldModel,
        after: EmbodiedWorldModel,
    ) -> list[str]:
        changed: list[str] = []
        if len(before.active_participants_in_view) != len(after.active_participants_in_view):
            changed.append("active_participants_in_view")
        if before.current_speaker_participant_id != after.current_speaker_participant_id:
            changed.append("current_speaker_participant_id")
        if before.likely_user_session_id != after.likely_user_session_id:
            changed.append("likely_user_session_id")
        if before.engagement_state != after.engagement_state:
            changed.append("engagement_state")
        if before.executive_state != after.executive_state:
            changed.append("executive_state")
        if before.turn_state != after.turn_state:
            changed.append("turn_state")
        if before.social_runtime_mode != after.social_runtime_mode:
            changed.append("social_runtime_mode")
        if before.environment_state != after.environment_state:
            changed.append("environment_state")
        if before.scene_freshness != after.scene_freshness:
            changed.append("scene_freshness")
        if (before.attention_target.target_label if before.attention_target else None) != (
            after.attention_target.target_label if after.attention_target else None
        ):
            changed.append("attention_target")
        if [item.label for item in before.visual_anchors] != [item.label for item in after.visual_anchors]:
            changed.append("visual_anchors")
        if [item.label for item in before.recent_visible_text] != [item.label for item in after.recent_visible_text]:
            changed.append("recent_visible_text")
        if [item.label for item in before.recent_named_objects] != [item.label for item in after.recent_named_objects]:
            changed.append("recent_named_objects")
        if before.perception_limited_awareness != after.perception_limited_awareness:
            changed.append("perception_limited_awareness")
        if before.device_awareness_constraints != after.device_awareness_constraints:
            changed.append("device_awareness_constraints")
        if before.uncertainty_markers != after.uncertainty_markers:
            changed.append("uncertainty_markers")
        return changed

    def derive_trace_outcome(
        self,
        *,
        event: RobotEvent,
        response: CommandBatch,
        reasoning: ReasoningTrace,
    ) -> TraceOutcome:
        if event.event_type == "heartbeat" and not event.payload.get("network_ok", True):
            return TraceOutcome.SAFE_FALLBACK
        if any(self.is_safe_idle_command(command) for command in response.commands):
            return TraceOutcome.SAFE_FALLBACK
        if reasoning.fallback_used or reasoning.intent == "fallback":
            return TraceOutcome.FALLBACK_REPLY
        if not response.reply_text and not response.commands:
            return TraceOutcome.NOOP
        return TraceOutcome.OK

    def build_session_summary(self, session: SessionRecord, user_memory: UserMemoryRecord | None) -> str:
        parts: list[str] = []
        if user_memory and user_memory.display_name:
            parts.append(f"Visitor name: {user_memory.display_name}.")
        if session.participant_id:
            parts.append(f"Likely participant: {session.participant_id}.")
        if session.active_incident_ticket_id and session.incident_status is not None:
            parts.append(
                f"Incident {session.active_incident_ticket_id} is {session.incident_status.value}."
            )
        if session.routing_status.value != "active":
            parts.append(f"Routing status: {session.routing_status.value}.")
        if session.current_topic:
            parts.append(f"Current topic: {session.current_topic}.")
        if last_location := session.session_memory.get("last_location"):
            location = COMMUNITY_LOCATIONS.get(last_location)
            if location:
                parts.append(f"Last location discussed: {location.title}.")
        if last_event_id := session.session_memory.get("last_event_id"):
            event = next((item for item in COMMUNITY_EVENTS if item.event_id == last_event_id), None)
            if event:
                parts.append(f"Last event discussed: {event.title}.")
        if session.status == SessionStatus.ESCALATION_PENDING:
            parts.append("Operator escalation is pending.")
        if session.response_mode:
            parts.append(f"Response mode: {session.response_mode.value}.")
        if not parts:
            return "Session created. No conversation turns yet."
        return " ".join(parts)

    def refresh_world_state(
        self,
        *,
        session: SessionRecord,
        event: RobotEvent | None = None,
        response: CommandBatch | None = None,
        trace_id: str | None = None,
        world_model: EmbodiedWorldModel | None = None,
    ) -> None:
        try:
            world_state = self.memory.get_world_state()
            sessions = self.memory.list_sessions().items
            active_world_model = world_model or self.world_model_runtime.get_state()
            if world_state.mode != RobotMode.DEGRADED_SAFE_IDLE:
                world_state.mode = self.settings.blink_runtime_mode
            world_state.active_session_ids = [
                item.session_id for item in sessions if item.status != SessionStatus.CLOSED
            ]
            world_state.active_user_ids = [item.user_id for item in sessions if item.user_id]
            world_state.pending_operator_session_ids = [
                item.session_id for item in sessions if item.status == SessionStatus.ESCALATION_PENDING
            ]
            open_incidents = self.memory.list_incident_tickets(scope=IncidentListScope.OPEN, limit=100).items
            world_state.open_incident_ticket_ids = [item.ticket_id for item in open_incidents]
            world_state.last_session_id = session.session_id
            world_state.last_incident_ticket_id = session.active_incident_ticket_id
            world_state.current_focus = session.current_topic
            world_state.person_detected = bool(active_world_model.active_participants_in_view)
            world_state.people_count = len(active_world_model.active_participants_in_view)
            world_state.engagement_state = active_world_model.engagement_state
            world_state.engagement_estimate = active_world_model.engagement_state.value
            world_state.attention_target = (
                active_world_model.attention_target.target_label if active_world_model.attention_target else None
            )
            world_state.executive_state = active_world_model.executive_state
            world_state.social_runtime_mode = active_world_model.social_runtime_mode
            world_state.perception_limited_awareness = active_world_model.perception_limited_awareness
            world_state.last_perception_at = active_world_model.last_perception_at
            world_state.shift_supervisor = self.shift_supervisor.get_status()
            world_state.participant_router = self.participant_router.get_status()
            world_state.venue_operations = self.shift_supervisor.get_operations_snapshot()
            world_state.updated_at = utc_now()

            if event is not None:
                world_state.last_event_type = event.event_type
                world_state.last_event_at = event.timestamp
                if event.event_type == "speech_transcript":
                    world_state.last_user_text = str(event.payload.get("text", "")).strip()
                if event.event_type == "low_battery":
                    world_state.mode = RobotMode.DEGRADED_SAFE_IDLE
                if event.event_type in {"heartbeat", "telemetry"}:
                    mode = event.payload.get("mode")
                    if mode in RobotMode._value2member_map_:
                        world_state.mode = RobotMode(mode)
                if event.event_type in {item.value for item in PerceptionEventType}:
                    world_state.last_perception_event_type = event.event_type
                    world_state.last_perception_at = event.timestamp
                    world_state.perception_limited_awareness = bool(event.payload.get("limited_awareness", False))
                if event.event_type == PerceptionEventType.PEOPLE_COUNT_CHANGED.value:
                    people_count = event.payload.get("people_count")
                    if isinstance(people_count, (int, float)):
                        world_state.people_count = int(people_count)
                if event.event_type == PerceptionEventType.ENGAGEMENT_ESTIMATE_CHANGED.value:
                    engagement = event.payload.get("engagement_estimate")
                    if isinstance(engagement, str):
                        world_state.engagement_estimate = engagement
                if event.event_type == PerceptionEventType.SCENE_SUMMARY_UPDATED.value:
                    summary = event.payload.get("scene_summary")
                    if isinstance(summary, str):
                        world_state.latest_scene_summary = summary
                if event.event_type in {item.value for item in PerceptionEventType}:
                    tier = event.payload.get("tier")
                    if tier == "semantic":
                        world_state.social_runtime_mode = active_world_model.social_runtime_mode

            if response is not None:
                world_state.last_reply_text = response.reply_text
                world_state.last_commands = response.commands
                if any(self.is_safe_idle_command(command) for command in response.commands):
                    world_state.mode = RobotMode.DEGRADED_SAFE_IDLE

            if trace_id is not None:
                world_state.trace_count += 1
                world_state.last_trace_id = trace_id
            decisions = self.memory.list_executive_decisions(session_id=session.session_id, limit=1).items
            world_state.last_executive_decision_type = decisions[0].decision_type if decisions else None

            self.memory.replace_world_state(world_state)
        except Exception:
            logger.exception("Failed to refresh world state for session %s", session.session_id)
            raise

    def is_safe_idle_command(self, command: RobotCommand) -> bool:
        if command.command_type == CommandType.SAFE_IDLE:
            return True
        if command.command_type != CommandType.STOP:
            return False
        reason = str(command.payload.get("reason", "")).strip().lower()
        return reason in {
            "safe_idle",
            "operator_override",
            "transport_degraded",
            "low_battery",
            "edge_transport_degraded",
        }
