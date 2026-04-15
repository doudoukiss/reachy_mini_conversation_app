from __future__ import annotations

import logging
from pathlib import Path
from time import perf_counter
from uuid import uuid4

from embodied_stack.backends.router import BackendRouter
from embodied_stack.brain.agent_os import AgentRuntime, EmbodiedActionPolicy
from embodied_stack.brain.executive import InteractionExecutive
from embodied_stack.brain.incident_workflow import IncidentWorkflow
from embodied_stack.brain.llm import DialogueEngine
from embodied_stack.brain.memory_layers import MemoryLayerService
from embodied_stack.brain.memory_policy import MemoryPolicyService
from embodied_stack.brain.memory import (
    MemoryStore,
    build_retrieval_records_from_tool_invocations,
    build_retrieval_records_from_typed_tool_calls,
)
from embodied_stack.brain.orchestration import GroundingSourceBuilder, InteractionHandler, StateProjectionHelper
from embodied_stack.brain.participant_router import ParticipantSessionRouter
from embodied_stack.brain.planner_interface import PlannerRegistry
from embodied_stack.brain.shift_supervisor import ShiftSupervisor
from embodied_stack.brain.tools import KnowledgeToolbox
from embodied_stack.brain.voice import VoicePipeline, VoicePipelineFactory
from embodied_stack.brain.world_model import WorldModelRuntime
from embodied_stack.config import Settings, get_settings
from embodied_stack.demo.community_scripts import DEMO_SCENARIOS
from embodied_stack.observability import log_event
from embodied_stack.shared.contracts import (
    CommandBatch,
    CompanionNoteListResponse,
    CompanionNoteRecord,
    EmbodiedWorldModel,
    EngagementTimelinePoint,
    EpisodicMemoryListResponse,
    ExecutiveDecisionListResponse,
    IncidentAcknowledgeRequest,
    IncidentAssignRequest,
    IncidentListResponse,
    IncidentListScope,
    IncidentNoteRequest,
    IncidentResolveRequest,
    IncidentTicketRecord,
    IncidentTimelineResponse,
    LogListResponse,
    MemoryLayer,
    OperatorNote,
    OperatorNoteRequest,
    PlannerCatalogResponse,
    ParticipantRouterSnapshot,
    PerceptionHistoryResponse,
    PerceptionSnapshotRecord,
    ReminderListResponse,
    ReminderRecord,
    ResponseMode,
    RobotEvent,
    SessionDigestListResponse,
    SessionDigestRecord,
    ShiftSupervisorSnapshot,
    ShiftTransitionListResponse,
    VenueOperationsSnapshot,
    ScenarioCatalogResponse,
    ScenarioReplayRequest,
    ScenarioReplayResult,
    ScenarioReplayStepResult,
    SessionCreateRequest,
    SessionListResponse,
    SessionRecord,
    SessionResponseModeRequest,
    SemanticMemoryListResponse,
    TraceListResponse,
    TraceRecord,
    UserMemoryRecord,
    VoiceTurnRequest,
    VoiceTurnResult,
    WorldState,
    WorldModelTransitionListResponse,
    WorldModelTransitionRecord,
    utc_now,
)
from embodied_stack.shared.contracts.brain import (
    MemoryActionListResponse,
    MemoryRetrievalListResponse,
    MemoryReviewDebtSummary,
    MemoryReviewListResponse,
    MemoryReviewRequest,
)
from embodied_stack.shared.contracts.episode import TeacherAnnotationListResponse, TeacherAnnotationRecord, TeacherReviewRequest

logger = logging.getLogger(__name__)


class BrainOrchestrator:
    def __init__(
        self,
        *,
        settings: Settings | None = None,
        store_path: str | Path | None = None,
        memory: MemoryStore | None = None,
        knowledge_tools: KnowledgeToolbox | None = None,
        dialogue_engine: DialogueEngine | None = None,
        voice_pipeline: VoicePipeline | None = None,
        backend_router: BackendRouter | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.backend_router = backend_router or BackendRouter(settings=self.settings)
        self.memory = memory or MemoryStore(store_path or self.settings.brain_store_path)
        self.memory_layers = MemoryLayerService(self.memory)
        self.memory_policy = MemoryPolicyService(self.memory)
        self.knowledge_tools = knowledge_tools or KnowledgeToolbox(
            settings=self.settings,
            embedding_backend=self.backend_router.build_embedding_backend(),
            memory_store=self.memory,
        )
        self.dialogue_engine = dialogue_engine or self.backend_router.build_dialogue_engine()
        self.action_policy = EmbodiedActionPolicy(settings=self.settings)
        self.voice_pipeline = voice_pipeline or VoicePipelineFactory(
            backend=self.settings.brain_voice_backend,
            openai_api_key=self.settings.openai_api_key,
            openai_base_url=self.settings.openai_base_url,
            openai_model=self.settings.openai_responses_model,
        ).build()
        self.world_model_runtime = WorldModelRuntime(self.memory)
        self.executive = InteractionExecutive(
            venue_knowledge=self.knowledge_tools.venue_knowledge,
            context_mode=self.settings.blink_context_mode,
        )
        self.participant_router = ParticipantSessionRouter(
            memory=self.memory,
            settings=self.settings,
        )
        self.incident_workflow = IncidentWorkflow(
            memory=self.memory,
            venue_knowledge=self.knowledge_tools.venue_knowledge,
        )
        self.shift_supervisor = ShiftSupervisor(
            memory=self.memory,
            settings=self.settings,
            venue_knowledge=self.knowledge_tools.venue_knowledge,
        )
        self.agent_runtime = AgentRuntime(
            settings=self.settings,
            backend_router=self.backend_router,
            knowledge_tools=self.knowledge_tools,
            dialogue_engine=self.dialogue_engine,
            action_policy=self.action_policy,
            memory_store=self.memory,
        )
        self.planner_registry = PlannerRegistry(runtime=self.agent_runtime)
        self.planner_adapter = self.planner_registry.get(
            self.settings.blink_planner_id,
            planner_profile=self.settings.blink_planner_profile,
        )
        self.grounding = GroundingSourceBuilder()
        self.state_projection = StateProjectionHelper(
            memory=self.memory,
            world_model_runtime=self.world_model_runtime,
            shift_supervisor=self.shift_supervisor,
            participant_router=self.participant_router,
            settings=self.settings,
        )
        self.interaction = InteractionHandler(
            settings=self.settings,
            memory=self.memory,
            knowledge_tools=self.knowledge_tools,
            dialogue_engine=self.dialogue_engine,
            action_policy=self.action_policy,
            agent_runtime=self.agent_runtime,
            planner_adapter=self.planner_adapter,
            executive=self.executive,
            incident_workflow=self.incident_workflow,
            grounding=self.grounding,
            ensure_user_memory=self._get_or_create_user_memory,
        )
        self._initialize_runtime_state()

    def list_planners(self) -> PlannerCatalogResponse:
        return PlannerCatalogResponse(items=self.planner_registry.list_descriptors())

    def build_session_request(
        self,
        *,
        session_id: str | None = None,
        user_id: str | None = None,
        channel: str = "speech",
        scenario_name: str | None = None,
        response_mode: ResponseMode | None = None,
        operator_notes: list[str] | None = None,
    ) -> SessionCreateRequest:
        return SessionCreateRequest(
            session_id=session_id,
            user_id=user_id,
            channel=channel,
            scenario_name=scenario_name,
            response_mode=response_mode or self._default_response_mode(),
            operator_notes=operator_notes or [],
        )

    def create_session(self, request: SessionCreateRequest) -> SessionRecord:
        session = self.memory.create_session(request)
        session.conversation_summary = session.conversation_summary or "Session created. No conversation turns yet."
        persisted = self.memory.upsert_session(session)
        self.state_projection.refresh_world_state(session=persisted)
        return persisted

    def list_sessions(self) -> SessionListResponse:
        return self.memory.list_sessions()

    def get_session(self, session_id: str) -> SessionRecord | None:
        return self.memory.get_session(session_id)

    def add_operator_note(self, session_id: str, request: OperatorNoteRequest) -> SessionRecord:
        session = self.memory.add_operator_note(
            session_id,
            OperatorNote(text=request.text, author=request.author),
        )
        session.conversation_summary = self.state_projection.build_session_summary(
            session,
            self._get_or_create_user_memory(session),
        )
        persisted = self.memory.upsert_session(session)
        self.state_projection.refresh_world_state(session=persisted)
        return persisted

    def _infer_memory_layer_for_id(self, memory_id: str):
        if self.memory.get_user_memory(memory_id) is not None:
            return MemoryLayer.PROFILE
        if self.memory.get_semantic_memory(memory_id) is not None:
            return MemoryLayer.SEMANTIC
        if (
            self.memory.get_episodic_memory(memory_id) is not None
            or self.memory.get_reminder(memory_id) is not None
            or self.memory.get_companion_note(memory_id) is not None
            or self.memory.get_session_digest(memory_id) is not None
        ):
            return MemoryLayer.EPISODIC
        return None

    def set_response_mode(self, session_id: str, request: SessionResponseModeRequest) -> SessionRecord:
        session = self.memory.get_session(session_id)
        if session is None:
            raise KeyError(session_id)
        session.response_mode = request.response_mode
        user_memory = self._get_or_create_user_memory(session)
        if user_memory:
            user_memory.preferred_response_mode = request.response_mode
            self.memory.upsert_user_memory(user_memory)
        session.conversation_summary = self.state_projection.build_session_summary(session, user_memory)
        persisted = self.memory.upsert_session(session)
        self.state_projection.refresh_world_state(session=persisted)
        return persisted

    def reset_runtime(self, *, clear_user_memory: bool = True) -> None:
        self.memory.reset(clear_user_memory=clear_user_memory)
        self._initialize_runtime_state()

    def get_world_state(self) -> WorldState:
        return self.memory.get_world_state()

    def get_world_model(self) -> EmbodiedWorldModel:
        return self.world_model_runtime.get_state()

    def get_shift_supervisor(self) -> ShiftSupervisorSnapshot:
        return self.shift_supervisor.get_status()

    def get_participant_router(self) -> ParticipantRouterSnapshot:
        return self.participant_router.get_status()

    def get_venue_operations(self) -> VenueOperationsSnapshot:
        return self.shift_supervisor.get_operations_snapshot()

    def list_incidents(
        self,
        *,
        scope: IncidentListScope = IncidentListScope.ALL,
        session_id: str | None = None,
        limit: int = 50,
    ) -> IncidentListResponse:
        return self.memory.list_incident_tickets(scope=scope, session_id=session_id, limit=limit)

    def get_incident(self, ticket_id: str) -> IncidentTicketRecord | None:
        return self.memory.get_incident_ticket(ticket_id)

    def list_incident_timeline(
        self,
        *,
        ticket_id: str | None = None,
        session_id: str | None = None,
        limit: int = 100,
    ) -> IncidentTimelineResponse:
        return self.memory.list_incident_timeline(ticket_id=ticket_id, session_id=session_id, limit=limit)

    def acknowledge_incident(
        self,
        ticket_id: str,
        request: IncidentAcknowledgeRequest,
    ) -> IncidentTicketRecord:
        ticket, _timeline = self.incident_workflow.acknowledge_ticket(ticket_id, request)
        self._refresh_world_state_for_incident(ticket)
        return ticket

    def assign_incident(
        self,
        ticket_id: str,
        request: IncidentAssignRequest,
    ) -> IncidentTicketRecord:
        ticket, _timeline = self.incident_workflow.assign_ticket(ticket_id, request)
        self._refresh_world_state_for_incident(ticket)
        return ticket

    def add_incident_note(
        self,
        ticket_id: str,
        request: IncidentNoteRequest,
    ) -> IncidentTicketRecord:
        ticket, _timeline = self.incident_workflow.add_note(ticket_id, request)
        self._refresh_world_state_for_incident(ticket)
        return ticket

    def resolve_incident(
        self,
        ticket_id: str,
        request: IncidentResolveRequest,
    ) -> IncidentTicketRecord:
        ticket, _timeline = self.incident_workflow.resolve_ticket(ticket_id, request)
        self._refresh_world_state_for_incident(ticket)
        return ticket

    def list_executive_decisions(
        self,
        session_id: str | None = None,
        limit: int = 25,
    ) -> ExecutiveDecisionListResponse:
        return self.memory.list_executive_decisions(session_id=session_id, limit=limit)

    def list_world_model_transitions(
        self,
        session_id: str | None = None,
        limit: int = 25,
    ) -> WorldModelTransitionListResponse:
        return self.memory.list_world_model_transitions(session_id=session_id, limit=limit)

    def list_shift_transitions(
        self,
        session_id: str | None = None,
        limit: int = 25,
    ) -> ShiftTransitionListResponse:
        return self.memory.list_shift_transitions(session_id=session_id, limit=limit)

    def list_engagement_timeline(
        self,
        session_id: str | None = None,
        limit: int = 25,
    ) -> list[EngagementTimelinePoint]:
        return self.memory.list_engagement_timeline(session_id=session_id, limit=limit)

    def get_memory_snapshot(self) -> dict:
        return self.memory.snapshot()

    def list_episodic_memory(
        self,
        *,
        session_id: str | None = None,
        user_id: str | None = None,
        limit: int = 50,
    ) -> EpisodicMemoryListResponse:
        return self.memory_layers.list_episodic(session_id=session_id, user_id=user_id, limit=limit)

    def list_semantic_memory(
        self,
        *,
        session_id: str | None = None,
        user_id: str | None = None,
        limit: int = 100,
    ) -> SemanticMemoryListResponse:
        return self.memory_layers.list_semantic(session_id=session_id, user_id=user_id, limit=limit)

    def get_profile_memory(self, user_id: str) -> UserMemoryRecord | None:
        return self.memory_layers.get_profile(user_id)

    def list_memory_actions(
        self,
        *,
        session_id: str | None = None,
        user_id: str | None = None,
        trace_id: str | None = None,
        memory_id: str | None = None,
        limit: int = 100,
    ) -> MemoryActionListResponse:
        return self.memory_layers.list_actions(
            session_id=session_id,
            user_id=user_id,
            trace_id=trace_id,
            memory_id=memory_id,
            limit=limit,
        )

    def list_memory_reviews(self, *, memory_id: str | None = None, limit: int = 100) -> MemoryReviewListResponse:
        return self.memory_layers.list_reviews(memory_id=memory_id, limit=limit)

    def list_memory_retrievals(
        self,
        *,
        session_id: str | None = None,
        user_id: str | None = None,
        trace_id: str | None = None,
        run_id: str | None = None,
        limit: int = 100,
    ) -> MemoryRetrievalListResponse:
        return self.memory_layers.list_retrievals(
            session_id=session_id,
            user_id=user_id,
            trace_id=trace_id,
            run_id=run_id,
            limit=limit,
        )

    def memory_review_debt_summary(self) -> MemoryReviewDebtSummary:
        return self.memory_layers.review_debt_summary()

    def review_memory(self, request: MemoryReviewRequest):
        return self.memory_policy.review_memory(request)

    def correct_memory(self, request: MemoryReviewRequest):
        return self.memory_policy.correct_memory(request)

    def delete_memory(self, request: MemoryReviewRequest):
        return self.memory_policy.delete_memory(request)

    def list_teacher_annotations(
        self,
        *,
        trace_id: str | None = None,
        run_id: str | None = None,
        action_id: str | None = None,
        workflow_run_id: str | None = None,
        memory_id: str | None = None,
        episode_id: str | None = None,
        limit: int = 100,
    ) -> TeacherAnnotationListResponse:
        return self.memory_layers.list_teacher_annotations(
            trace_id=trace_id,
            run_id=run_id,
            action_id=action_id,
            workflow_run_id=workflow_run_id,
            memory_id=memory_id,
            episode_id=episode_id,
            limit=limit,
        )

    def add_teacher_annotation(
        self,
        *,
        scope,
        scope_id: str,
        request: TeacherReviewRequest,
        session_id: str | None = None,
        trace_id: str | None = None,
        run_id: str | None = None,
        action_id: str | None = None,
        workflow_run_id: str | None = None,
        memory_id: str | None = None,
        episode_id: str | None = None,
    ) -> TeacherAnnotationRecord:
        record = TeacherAnnotationRecord(
            scope=scope,
            scope_id=scope_id,
            review_value=request.review_value,
            label=request.label,
            note=request.note,
            author=request.author,
            primary_kind=request.resolved_primary_kind,
            session_id=session_id,
            trace_id=trace_id,
            run_id=run_id,
            action_id=action_id,
            workflow_run_id=workflow_run_id,
            memory_id=memory_id,
            episode_id=episode_id,
            reply_feedback=request.normalized_reply_feedback(),
            memory_feedback=request.normalized_memory_feedback(),
            scene_feedback=request.normalized_scene_feedback(),
            embodiment_feedback=request.normalized_embodiment_feedback(),
            outcome_feedback=request.normalized_outcome_feedback(),
            action_feedback=request.normalized_action_feedback(),
            better_reply_text=request.better_reply_text,
            corrected_scene_summary=request.corrected_scene_summary,
            preferred_body_expression=request.preferred_body_expression,
            memory_importance=request.memory_importance,
            proactive_prompt_appropriate=request.proactive_prompt_appropriate,
            outcome_label=request.outcome_label,
            action_feedback_labels=list(request.action_feedback_labels),
            benchmark_tags=list(request.benchmark_tags),
        )
        persisted = self.memory.upsert_teacher_annotation(record)
        memory_feedback = persisted.memory_feedback
        if persisted.memory_id and memory_feedback is not None and memory_feedback.action.value in {
            "reject",
            "merge_into",
            "correct_to",
            "needs_review",
        }:
            inferred_layer = self._infer_memory_layer_for_id(persisted.memory_id)
            if inferred_layer is not None:
                self.memory_policy.mark_teacher_conflict(
                    layer=inferred_layer,
                    memory_id=persisted.memory_id,
                    note=persisted.note,
                )
        return persisted

    def list_reminders(
        self,
        *,
        session_id: str | None = None,
        user_id: str | None = None,
        status=None,
        limit: int = 100,
    ) -> ReminderListResponse:
        return self.memory.list_reminders(session_id=session_id, user_id=user_id, status=status, limit=limit)

    def upsert_reminder(self, record: ReminderRecord) -> ReminderRecord:
        return self.memory.upsert_reminder(record)

    def list_companion_notes(
        self,
        *,
        session_id: str | None = None,
        user_id: str | None = None,
        limit: int = 100,
    ) -> CompanionNoteListResponse:
        return self.memory.list_companion_notes(session_id=session_id, user_id=user_id, limit=limit)

    def upsert_companion_note(self, record: CompanionNoteRecord) -> CompanionNoteRecord:
        return self.memory.upsert_companion_note(record)

    def list_session_digests(
        self,
        *,
        session_id: str | None = None,
        user_id: str | None = None,
        limit: int = 50,
    ) -> SessionDigestListResponse:
        return self.memory.list_session_digests(session_id=session_id, user_id=user_id, limit=limit)

    def upsert_session_digest(self, record: SessionDigestRecord) -> SessionDigestRecord:
        return self.memory.upsert_session_digest(record)

    def get_latest_perception(self, session_id: str | None = None) -> PerceptionSnapshotRecord | None:
        return self.memory.get_latest_perception(session_id)

    def list_perception_history(self, session_id: str | None = None, limit: int = 20) -> PerceptionHistoryResponse:
        return self.memory.list_perception_history(session_id=session_id, limit=limit)

    def list_logs(self, session_id: str | None = None, limit: int = 50) -> LogListResponse:
        return self.memory.list_logs(session_id=session_id, limit=limit)

    def list_traces(self, session_id: str | None = None, limit: int = 50) -> TraceListResponse:
        return self.memory.list_traces(session_id=session_id, limit=limit)

    def get_trace(self, trace_id: str) -> TraceRecord | None:
        return self.memory.get_trace(trace_id)

    def update_trace(self, trace: TraceRecord) -> TraceRecord:
        return self.memory.update_trace(trace)

    def capture_persist_metrics(self):
        return self.memory.capture_persist_metrics()

    def list_scenarios(self) -> ScenarioCatalogResponse:
        return ScenarioCatalogResponse(items=list(DEMO_SCENARIOS.values()))

    def replay_scenario(self, scenario_name: str, request: ScenarioReplayRequest | None = None) -> ScenarioReplayResult:
        scenario = DEMO_SCENARIOS.get(scenario_name)
        if scenario is None:
            raise KeyError(scenario_name)

        replay_request = request or ScenarioReplayRequest()
        session_id = replay_request.session_id or f"scenario-{scenario_name}-{uuid4().hex[:8]}"
        self.create_session(
            self.build_session_request(
                session_id=session_id,
                user_id=replay_request.user_id,
                scenario_name=scenario_name,
                operator_notes=replay_request.operator_notes,
            )
        )

        results: list[ScenarioReplayStepResult] = []
        for step in scenario.steps:
            event = RobotEvent(
                event_type=step.event_type,
                payload=step.payload,
                session_id=session_id,
                source="scenario_replay",
            )
            response = self.handle_event(event)
            results.append(ScenarioReplayStepResult(event=event, response=response))

        return ScenarioReplayResult(
            scenario_name=scenario.name,
            description=scenario.description,
            session_id=session_id,
            steps=results,
            final_world_state=self.get_world_state(),
        )

    def handle_voice_turn(self, request: VoiceTurnRequest) -> VoiceTurnResult:
        voice_turn_id = f"voice-turn-{uuid4().hex[:8]}"
        session_id = request.session_id or f"voice-session-{uuid4().hex[:8]}"
        with self.memory.batch_update():
            session = self.memory.ensure_session(
                session_id,
                user_id=request.user_id,
                channel="voice",
                response_mode=request.response_mode or self._default_response_mode(),
            )
            if request.response_mode and session.response_mode != request.response_mode:
                session = self.set_response_mode(session_id, SessionResponseModeRequest(response_mode=request.response_mode))
            prepared = self.voice_pipeline.prepare_event(request, session_id)
            log_event(
                logger,
                logging.INFO,
                "voice_turn_started",
                voice_turn_id=voice_turn_id,
                session_id=session_id,
                event_id=prepared.event.event_id,
                source=prepared.event.source,
            )
            response = self.handle_event(prepared.event)
            log_event(
                logger,
                logging.INFO,
                "voice_turn_completed",
                voice_turn_id=voice_turn_id,
                session_id=session_id,
                event_id=prepared.event.event_id,
                trace_id=response.trace_id,
                command_count=len(response.commands),
            )
            return VoiceTurnResult(
                session_id=session_id,
                transcript_event=prepared.event,
                response=response,
                provider=prepared.provider,
                used_fallback=prepared.used_fallback,
                audio_available=prepared.audio_available,
            )

    def build_shift_tick_event(
        self,
        *,
        session_id: str | None = None,
        timestamp=None,
        source: str = "shift_supervisor",
        telemetry=None,
        heartbeat=None,
        transport_state=None,
        transport_error: str | None = None,
        extra_payload: dict[str, object] | None = None,
    ) -> RobotEvent:
        payload: dict[str, object] = {}
        if telemetry is not None:
            payload.update(
                {
                    "battery_pct": telemetry.battery_pct,
                    "mode": telemetry.mode.value,
                    "transport_ok": telemetry.transport_ok,
                }
            )
        if heartbeat is not None:
            payload.update(
                {
                    "network_ok": heartbeat.network_ok,
                    "safe_idle_active": heartbeat.safe_idle_active,
                    "safe_idle_reason": heartbeat.safe_idle_reason,
                    "transport_ok": payload.get("transport_ok", True) and heartbeat.transport_ok,
                }
            )
        if transport_state is not None:
            payload["edge_transport_state"] = transport_state.value
        if transport_error:
            payload["edge_transport_error"] = transport_error
        if extra_payload:
            payload.update(extra_payload)
        return RobotEvent(
            event_type="shift_autonomy_tick",
            session_id=session_id,
            source=source,
            timestamp=timestamp or utc_now(),
            payload=payload,
        )

    def handle_event(self, event: RobotEvent) -> CommandBatch:
        with self.memory.batch_update():
            start = perf_counter()
            log_event(
                logger,
                logging.INFO,
                "brain_event_started",
                session_id=event.session_id,
                event_id=event.event_id,
                event_type=event.event_type,
                source=event.source,
            )
            prior_world_model = self.world_model_runtime.get_state()
            route_plan = self.participant_router.route_event(
                event,
                prior_world_model=prior_world_model,
            )
            event = route_plan.event
            session = route_plan.session
            user_memory = self._get_or_create_user_memory(session)
            current_world_model = self.world_model_runtime.apply_event(event, session=session)
            current_world_model.participant_router = route_plan.snapshot
            current_world_model = self.memory.replace_world_model(current_world_model)
            shift_pre = self.shift_supervisor.evaluate_pre_event(
                event=event,
                session=session,
                world_model=current_world_model,
                world_state=self.memory.get_world_state(),
            )

            session.events.append(event)
            if event.event_type == "speech_transcript":
                text = str(event.payload.get("text", "")).strip()
                session.last_user_text = text
                response, reasoning, session, user_memory, decisions = self.interaction.handle_speech_event(
                    text=text,
                    event=event,
                    session=session,
                    user_memory=user_memory,
                    prior_world_model=prior_world_model,
                    world_model=current_world_model,
                    route_plan=route_plan,
                    shift_plan=shift_pre,
                )
            else:
                response, reasoning, session, decisions = self.interaction.handle_non_speech_event(
                    event=event,
                    session=session,
                    user_memory=user_memory,
                    prior_world_model=prior_world_model,
                    world_model=current_world_model,
                    route_plan=route_plan,
                    shift_plan=shift_pre,
                )

            route_snapshot = self.participant_router.finalize_event(
                event=event,
                session=session,
                prior_world_model=prior_world_model,
                response_text=response.reply_text,
                intent=reasoning.intent,
            )
            session = self.memory.get_session(session.session_id) or session

            shift_post = self.shift_supervisor.evaluate_post_response(
                event=event,
                session=session,
                response=response,
                intent=reasoning.intent,
                proactive_action=shift_pre.proactive_action,
                proactive_action_key=shift_pre.proactive_action_key,
            )
            shift_transitions = [*shift_pre.transitions, *shift_post.transitions]
            shift_snapshot = shift_post.snapshot

            trace_id = str(uuid4())
            decisions = self.interaction.annotate_decisions(
                decisions,
                session_id=session.session_id,
                commands=response.commands,
            )
            incident_sync = self.incident_workflow.sync_from_decisions(
                session=session,
                event=event,
                reasoning=reasoning,
                decisions=decisions,
                trace_id=trace_id,
            )
            if incident_sync.reply_text is not None:
                response = self.interaction.override_response_reply(
                    response=response,
                    intent=reasoning.intent,
                    reply_text=incident_sync.reply_text,
                )
            response.trace_id = trace_id
            response.status = session.status
            reasoning.executive_decisions = decisions
            reasoning.uncertainty_admitted = any(item.policy_outcome == "uncertainty_admission" for item in decisions)
            reasoning.stale_scene_suppressed = any(item.policy_outcome == "stale_scene_suppressed" for item in decisions)
            reasoning.executive_state = decisions[-1].executive_state if decisions else current_world_model.executive_state
            reasoning.shift_supervisor = shift_snapshot
            reasoning.participant_router = route_snapshot
            reasoning.venue_operations = self.shift_supervisor.get_operations_snapshot()
            reasoning.shift_transitions = [
                transition.model_copy(update={"trace_id": trace_id})
                for transition in shift_transitions
            ]
            reasoning.incident_ticket = incident_sync.ticket
            reasoning.incident_timeline = incident_sync.timeline
            reasoning.grounding_sources = self.grounding.merge(
                reasoning.grounding_sources,
                [
                    *self.grounding.executive_sources(decisions),
                    *self.grounding.shift_sources(shift_snapshot, reasoning.shift_transitions),
                ],
            )
            reasoning.grounded_scene_references = [
                item for item in reasoning.grounding_sources if item.fact_id is not None or item.claim_kind is not None
            ]
            reasoning.notes = [*reasoning.notes, *route_plan.notes, *shift_pre.notes, *incident_sync.notes]
            session.last_reply_text = response.reply_text
            session.updated_at = utc_now()
            session.conversation_summary = self.state_projection.build_session_summary(session, user_memory)
            session.transcript.append(
                self.interaction.build_turn(
                    event=event,
                    response=response,
                    intent=reasoning.intent,
                    trace_id=trace_id,
                    participant_id=route_plan.participant_id,
                    incident_ticket_id=session.active_incident_ticket_id,
                    executive_reason_codes=self.interaction.reason_codes(decisions),
                )
            )
            persisted_session = self.memory.upsert_session(session)

            if user_memory is not None and persisted_session.user_id:
                user_memory.last_session_id = persisted_session.session_id
                self.memory.upsert_user_memory(user_memory)

            latency_ms = round((perf_counter() - start) * 1000.0, 2)
            trace = TraceRecord(
                trace_id=trace_id,
                session_id=persisted_session.session_id,
                user_id=persisted_session.user_id,
                event=event,
                response=response,
                reasoning=reasoning,
                latency_ms=latency_ms,
                outcome=self.state_projection.derive_trace_outcome(
                    event=event,
                    response=response,
                    reasoning=reasoning,
                ),
            )
            trace.reasoning.latency_breakdown.total_ms = latency_ms
            self.memory.append_trace(trace)
            retrieval_records = [
                *build_retrieval_records_from_tool_invocations(
                    query_text=(str(event.payload.get("text")) if isinstance(event.payload, dict) and event.payload.get("text") else None),
                    session_id=persisted_session.session_id,
                    user_id=persisted_session.user_id,
                    trace_id=trace_id,
                    run_id=trace.reasoning.run_id,
                    tool_invocations=trace.reasoning.tool_invocations,
                ),
                *build_retrieval_records_from_typed_tool_calls(
                    session_id=persisted_session.session_id,
                    user_id=persisted_session.user_id,
                    trace_id=trace_id,
                    run_id=trace.reasoning.run_id,
                    typed_tool_calls=trace.reasoning.typed_tool_calls,
                ),
            ]
            if retrieval_records:
                self.memory.append_memory_retrievals(retrieval_records)
            if trace.reasoning.run_id is not None:
                self.agent_runtime.attach_trace(trace.reasoning.run_id, trace_id)
                self.memory.attach_trace_to_memory_retrievals(run_id=trace.reasoning.run_id, trace_id=trace_id)
            self.knowledge_tools.record_turn_memory(
                session=persisted_session,
                user_memory=user_memory,
                trace_id=trace_id,
                reply_text=response.reply_text,
                intent=reasoning.intent,
                source_refs=[item.source_ref for item in trace.reasoning.grounding_sources if item.source_ref],
            )
            if decisions:
                self.memory.append_executive_decisions(decisions)
            if reasoning.shift_transitions:
                self.memory.append_shift_transitions(reasoning.shift_transitions)
            updated_world_model = self.world_model_runtime.apply_response(
                session=persisted_session,
                response=response,
                intent=reasoning.intent,
                decisions=decisions,
                at_time=event.timestamp,
            )
            updated_world_model.participant_router = route_snapshot
            updated_world_model = self.memory.replace_world_model(updated_world_model)
            self.memory.append_world_model_transition(
                WorldModelTransitionRecord(
                    session_id=persisted_session.session_id,
                    trace_id=trace_id,
                    source_event_type=event.event_type,
                    intent=reasoning.intent,
                    changed_fields=self.state_projection.world_model_changed_fields(
                        prior_world_model,
                        updated_world_model,
                    ),
                    before=prior_world_model,
                    after=updated_world_model,
                    notes=reasoning.notes,
                )
            )
            self.state_projection.refresh_world_state(
                session=persisted_session,
                event=event,
                response=response,
                trace_id=trace_id,
                world_model=updated_world_model,
            )
            log_event(
                logger,
                logging.INFO,
                "brain_event_completed",
                session_id=persisted_session.session_id,
                event_id=event.event_id,
                event_type=event.event_type,
                trace_id=trace_id,
                run_id=trace.reasoning.run_id,
                command_count=len(response.commands),
                latency_ms=latency_ms,
                outcome=trace.outcome.value,
            )
            return response

    def _refresh_world_state_for_incident(self, ticket: IncidentTicketRecord) -> None:
        session = self.get_session(ticket.session_id)
        if session is None:
            return
        session.conversation_summary = self.state_projection.build_session_summary(
            session,
            self._get_or_create_user_memory(session),
        )
        persisted = self.memory.upsert_session(session)
        self.state_projection.refresh_world_state(session=persisted)

    def _get_or_create_user_memory(self, session: SessionRecord) -> UserMemoryRecord | None:
        if not session.user_id:
            return None
        user_memory = self.memory.get_user_memory(session.user_id)
        if user_memory is not None:
            return user_memory
        record = UserMemoryRecord(
            user_id=session.user_id,
            preferred_response_mode=session.response_mode,
        )
        self.memory.upsert_user_memory(record)
        return record

    def _default_response_mode(self) -> ResponseMode:
        configured = self.settings.brain_default_response_mode
        if configured in ResponseMode._value2member_map_:
            return ResponseMode(configured)
        return ResponseMode.GUIDE

    def _initialize_runtime_state(self) -> None:
        world_state = self.memory.get_world_state()
        world_state.mode = self.settings.blink_runtime_mode
        self.memory.replace_world_state(world_state)
