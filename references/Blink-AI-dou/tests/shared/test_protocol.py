from embodied_stack.shared.models import (
    BodyCapabilityProfile,
    BodyDriverMode,
    BodyPose,
    BodyState,
    CommandBatch,
    CommandType,
    DemoRunRequest,
    EdgeAdapterCapability,
    EdgeAdapterDirection,
    EdgeAdapterHealth,
    EdgeAdapterKind,
    EdgeAdapterState,
    EpisodicMemoryRecord,
    EpisodeExportSessionRequest,
    EpisodeExportShiftReportRequest,
    EpisodeSourceType,
    EpisodeSummary,
    IncidentAcknowledgeRequest,
    IncidentAssignRequest,
    IncidentReasonCategory,
    IncidentResolveRequest,
    IncidentResolutionOutcome,
    IncidentStaffSuggestion,
    IncidentStatus,
    IncidentTicketRecord,
    IncidentTimelineEventType,
    IncidentTimelineRecord,
    ParticipantRouterSnapshot,
    ParticipantSessionBinding,
    PerceptionAnnotationInput,
    PerceptionFactRecord,
    PerceptionObservationType,
    PerceptionProviderMode,
    PerceptionSnapshotSubmitRequest,
    ProceduralMemoryRecord,
    QueuedParticipantRecord,
    RelationshipMemoryRecord,
    ResponseMode,
    RobotCommand,
    RobotEvent,
    ScenarioDefinition,
    ScenarioEventStep,
    SemanticMemoryRecord,
    SessionCreateRequest,
    SessionRoutingStatus,
    SessionStatus,
    ShiftAutonomyTickRequest,
    ShiftMetricsSnapshot,
    ShiftOperatingState,
    ShiftOverrideRequest,
    ShiftReportSummary,
    ShiftSimulationDefinition,
    ShiftSimulationStepActionType,
    ShiftSimulationStepDefinition,
    SimulatedSensorEventRequest,
    VoiceTurnRequest,
    VenueFallbackScenario,
    VenueOperationsSnapshot,
    VenueScheduleWindow,
)


def test_robot_event_defaults():
    event = RobotEvent(event_type="speech_transcript", payload={"text": "hello"})
    assert event.event_type == "speech_transcript"
    assert event.event_id
    assert event.payload["text"] == "hello"


def test_command_batch_roundtrip():
    batch = CommandBatch(
        session_id="session-1",
        reply_text="hello",
        commands=[RobotCommand(command_type=CommandType.SPEAK, payload={"text": "hello"})],
        status=SessionStatus.ACTIVE,
    )
    dumped = batch.model_dump()
    assert dumped["reply_text"] == "hello"
    assert dumped["commands"][0]["command_type"] == "speak"
    assert dumped["status"] == "active"


def test_session_and_voice_request_defaults():
    request = SessionCreateRequest()
    assert request.channel == "speech"
    assert request.response_mode == ResponseMode.GUIDE

    voice = VoiceTurnRequest(input_text="hello")
    assert voice.source == "voice_stub"
    assert voice.input_metadata == {}


def test_scenario_and_demo_request_contracts():
    scenario = ScenarioDefinition(
        name="demo",
        description="demo scenario",
        steps=[ScenarioEventStep(event_type="speech_transcript", payload={"text": "hello"})],
    )
    assert scenario.steps[0].event_type == "speech_transcript"

    demo_request = DemoRunRequest()
    assert demo_request.scenario_names == []


def test_simulated_sensor_event_contract():
    request = SimulatedSensorEventRequest(event_type="person_detected")
    assert request.source == "edge_simulator"


def test_edge_adapter_contracts():
    capability = EdgeAdapterCapability(
        adapter_id="jetson_led",
        kind=EdgeAdapterKind.LED,
        direction=EdgeAdapterDirection.ACTUATOR,
        simulated=True,
        supported_commands=[CommandType.SET_LED],
    )
    health = EdgeAdapterHealth(
        adapter_id="jetson_led",
        kind=EdgeAdapterKind.LED,
        direction=EdgeAdapterDirection.ACTUATOR,
        state=EdgeAdapterState.SIMULATED,
    )
    assert capability.supported_commands[0] == CommandType.SET_LED
    assert health.state == EdgeAdapterState.SIMULATED


def test_body_contracts():
    capabilities = BodyCapabilityProfile(driver_mode=BodyDriverMode.VIRTUAL, supports_virtual_preview=True)
    state = BodyState(driver_mode=BodyDriverMode.VIRTUAL, pose=BodyPose(head_yaw=0.2), active_expression="listening")
    assert capabilities.driver_mode == BodyDriverMode.VIRTUAL
    assert capabilities.supports_virtual_preview is True
    assert state.pose.head_yaw == 0.2
    assert state.active_expression == "listening"


def test_perception_contracts():
    request = PerceptionSnapshotSubmitRequest(
        session_id="perception-1",
        provider_mode=PerceptionProviderMode.MANUAL_ANNOTATIONS,
        annotations=[
            PerceptionAnnotationInput(
                observation_type=PerceptionObservationType.PEOPLE_COUNT,
                number_value=1,
                confidence=0.9,
            )
        ],
    )
    assert request.provider_mode == PerceptionProviderMode.MANUAL_ANNOTATIONS
    assert request.annotations[0].observation_type == PerceptionObservationType.PEOPLE_COUNT


def test_episode_export_contracts():
    request = EpisodeExportSessionRequest(session_id="episode-1", redact_operator_notes=True)
    shift_request = EpisodeExportShiftReportRequest(report_id="shift-report-1")
    summary = EpisodeSummary(source_type=EpisodeSourceType.SESSION, source_id="episode-1")
    assert request.session_id == "episode-1"
    assert shift_request.report_id == "shift-report-1"
    assert request.redact_operator_notes is True
    assert summary.schema_version == "blink_episode/v1"


def test_layered_memory_and_perception_fact_contracts():
    episodic = EpisodicMemoryRecord(
        memory_id="session-1",
        session_id="session-1",
        title="wayfinding",
        summary="Visitor asked about the workshop room.",
    )
    semantic = SemanticMemoryRecord(
        memory_id="semantic-1",
        memory_kind="venue_location",
        summary="Workshop room directions were discussed.",
    )
    relationship = RelationshipMemoryRecord(
        relationship_id="visitor-1",
        user_id="visitor-1",
    )
    procedural = ProceduralMemoryRecord(
        user_id="visitor-1",
        name="planning routine",
        summary="Give one step at a time.",
    )
    fact = PerceptionFactRecord(fact_type="visible_text", label="Workshop Room")

    assert episodic.memory_id == "session-1"
    assert semantic.memory_kind == "venue_location"
    assert relationship.memory_layer.value == "relationship"
    assert procedural.memory_layer.value == "procedural"
    assert fact.fact_type == "visible_text"


def test_shift_supervisor_contracts():
    tick = ShiftAutonomyTickRequest(session_id="shift-1")
    override = ShiftOverrideRequest(state=ShiftOperatingState.SAFE_IDLE, reason="operator_override")
    assert tick.source == "shift_supervisor"
    assert override.state == ShiftOperatingState.SAFE_IDLE


def test_participant_router_contracts():
    binding = ParticipantSessionBinding(
        participant_id="likely_participant_1",
        session_id="router-likely_participant_1",
        routing_status=SessionRoutingStatus.ACTIVE,
    )
    queue_item = QueuedParticipantRecord(
        participant_id="likely_participant_2",
        session_id="router-likely_participant_2",
        queue_position=1,
    )
    router = ParticipantRouterSnapshot(
        active_participant_id="likely_participant_1",
        active_session_id="router-likely_participant_1",
        queued_participants=[queue_item],
        participant_sessions=[binding],
    )
    assert router.active_participant_id == "likely_participant_1"
    assert router.queued_participants[0].queue_position == 1


def test_incident_contracts():
    suggestion = IncidentStaffSuggestion(
        contact_key="front_desk",
        name="Jordan Lee",
        role="Front Desk Coordinator",
        desk_location_key="front_desk",
        desk_location_label="Front Desk",
    )
    ticket = IncidentTicketRecord(
        session_id="incident-1",
        participant_summary="likely visitor requested staff support",
        reason_category=IncidentReasonCategory.STAFF_REQUEST,
        suggested_staff_contact=suggestion,
        current_status=IncidentStatus.PENDING,
    )
    timeline = IncidentTimelineRecord(
        ticket_id=ticket.ticket_id,
        session_id="incident-1",
        event_type=IncidentTimelineEventType.CREATED,
        to_status=IncidentStatus.PENDING,
        actor="blink_ai",
    )
    acknowledge = IncidentAcknowledgeRequest(operator_name="Alex")
    assign = IncidentAssignRequest(assignee_name="Jordan Lee")
    resolve = IncidentResolveRequest(outcome=IncidentResolutionOutcome.STAFF_ASSISTED)
    assert ticket.suggested_staff_contact.name == "Jordan Lee"
    assert timeline.event_type == IncidentTimelineEventType.CREATED
    assert acknowledge.operator_name == "Alex"
    assert assign.assignee_name == "Jordan Lee"
    assert resolve.outcome == IncidentResolutionOutcome.STAFF_ASSISTED


def test_venue_operations_contracts():
    snapshot = VenueOperationsSnapshot(
        site_name="Test Venue",
        timezone="America/Los_Angeles",
        opening_hours=[
            VenueScheduleWindow(days=["monday"], start="09:00", end="17:00", label="weekday_shift")
        ],
        fallback_instructions=[
            {"scenario": VenueFallbackScenario.SAFE_IDLE, "visitor_message": "Paused for safety."}
        ],
    )
    assert snapshot.opening_hours[0].label == "weekday_shift"
    assert snapshot.fallback_instructions[0].scenario == VenueFallbackScenario.SAFE_IDLE


def test_shift_report_contracts():
    step = ShiftSimulationStepDefinition(
        label="opening_tick",
        action_type=ShiftSimulationStepActionType.SHIFT_TICK,
        offset_seconds=0,
    )
    definition = ShiftSimulationDefinition(
        simulation_name="pilot_day",
        description="Deterministic pilot shift replay.",
        start_at="2026-04-02T09:00:00Z",
        steps=[step],
    )
    metrics = ShiftMetricsSnapshot(visitors_greeted=1, conversations_started=2)
    summary = ShiftReportSummary(
        simulation_name="pilot_day",
        description="Deterministic pilot shift replay.",
        metrics=metrics,
    )
    assert definition.steps[0].action_type == ShiftSimulationStepActionType.SHIFT_TICK
    assert summary.metrics.visitors_greeted == 1
