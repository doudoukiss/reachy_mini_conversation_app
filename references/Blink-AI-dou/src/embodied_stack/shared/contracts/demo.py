from __future__ import annotations

from enum import Enum

from ._common import (
    BaseModel,
    CommandType,
    DemoRunStatus,
    EpisodeAnnotationStatus,
    EpisodeAssetKind,
    EpisodeLabelName,
    EpisodeSourceType,
    ExportRedactionProfile,
    Field,
    IncidentStatus,
    ResponseMode,
    SessionStatus,
    ShiftReportStatus,
    ShiftSimulationStepActionType,
    TraceOutcome,
    date,
    datetime,
    model_validator,
    time,
    utc_now,
    uuid4,
)
from .brain import (
    ConversationTurn,
    EpisodicMemoryRecord,
    GroundingSourceRecord,
    IncidentTicketRecord,
    IncidentTimelineRecord,
    LatencyBreakdownRecord,
    OperatorNote,
    SemanticMemoryRecord,
    SessionRecord,
    ShiftMetricsSnapshot,
    ShiftOperatingState,
    ShiftSupervisorSnapshot,
    ToolInvocationRecord,
    UserMemoryRecord,
    WorldState,
)
from .edge import CommandAck, CommandBatch, HeartbeatStatus, RobotCommand, RobotEvent, TelemetrySnapshot
from .perception import (
    EmbodiedWorldModel,
    EngagementTimelinePoint,
    ExecutiveDecisionRecord,
    PerceptionSnapshotRecord,
    WorldModelTransitionRecord,
)


class DemoFallbackEvent(BaseModel):
    timestamp: datetime = Field(default_factory=utc_now)
    session_id: str
    event_type: str
    trace_id: str | None = None
    backend_used: str | None = None
    outcome: TraceOutcome = TraceOutcome.FALLBACK_REPLY
    note: str | None = None


class DemoRunMetrics(BaseModel):
    step_count: int = 0
    trace_count: int = 0
    command_count: int = 0
    acknowledged_count: int = 0
    rejected_count: int = 0
    ack_success_rate: float = 0.0
    fallback_event_count: int = 0
    safe_fallback_count: int = 0
    average_end_to_end_latency_ms: float = 0.0
    max_end_to_end_latency_ms: float = 0.0
    average_trace_latency_ms: float = 0.0
    max_trace_latency_ms: float = 0.0
    average_perception_latency_ms: float = 0.0
    max_perception_latency_ms: float = 0.0
    average_tool_latency_ms: float = 0.0
    average_dialogue_latency_ms: float = 0.0
    average_executive_latency_ms: float = 0.0


class DemoRunStepRecord(BaseModel):
    scenario_name: str
    step_index: int
    started_at: datetime = Field(default_factory=utc_now)
    completed_at: datetime | None = None
    event: RobotEvent
    response: CommandBatch
    command_acks: list[CommandAck] = Field(default_factory=list)
    telemetry: TelemetrySnapshot
    heartbeat: HeartbeatStatus
    success: bool = True
    latency_ms: float = 0.0
    trace_latency_ms: float | None = None
    backend_used: str | None = None
    fallback_used: bool = False
    outcome: TraceOutcome = TraceOutcome.OK
    latency_breakdown: LatencyBreakdownRecord = Field(default_factory=LatencyBreakdownRecord)
    grounding_sources: list[GroundingSourceRecord] = Field(default_factory=list)
    shift_supervisor: ShiftSupervisorSnapshot | None = None
    incident_ticket: IncidentTicketRecord | None = None
    incident_timeline: list[IncidentTimelineRecord] = Field(default_factory=list)


class DemoRunRequest(BaseModel):
    scenario_names: list[str] = Field(default_factory=list)
    user_id: str | None = None
    response_mode: ResponseMode | None = None
    reset_brain_first: bool = True
    reset_edge_first: bool = True
    stop_on_failure: bool = False


class DemoRunRecord(BaseModel):
    run_id: str = Field(default_factory=lambda: str(uuid4()))
    created_at: datetime = Field(default_factory=utc_now)
    completed_at: datetime | None = None
    scenario_names: list[str] = Field(default_factory=list)
    status: DemoRunStatus = DemoRunStatus.RUNNING
    steps: list[DemoRunStepRecord] = Field(default_factory=list)
    passed: bool = True
    total_latency_ms: float = 0.0
    fallback_count: int = 0
    configured_dialogue_backend: str | None = None
    observed_dialogue_backends: list[str] = Field(default_factory=list)
    runtime_profile: str | None = None
    deployment_target: str | None = None
    metrics: DemoRunMetrics = Field(default_factory=DemoRunMetrics)
    fallback_events: list[DemoFallbackEvent] = Field(default_factory=list)
    final_world_state: WorldState | None = None
    final_shift_supervisor: ShiftSupervisorSnapshot | None = None
    final_grounding_sources: list[GroundingSourceRecord] = Field(default_factory=list)
    final_incidents: list[IncidentTicketRecord] = Field(default_factory=list)
    artifact_dir: str | None = None
    artifact_files: dict[str, str] = Field(default_factory=dict)
    report_path: str | None = None
    notes: list[str] = Field(default_factory=list)


class ScorecardCriterion(BaseModel):
    criterion: str
    passed: bool = True
    expected: str | None = None
    observed: str | None = None
    note: str | None = None


class FinalActionRecord(BaseModel):
    intent: str | None = None
    reply_text: str | None = None
    command_types: list[CommandType] = Field(default_factory=list)
    trace_id: str | None = None
    executive_state: "InteractionExecutiveState | None" = None
    reason_codes: list[str] = Field(default_factory=list)


class DemoSceneScorecard(BaseModel):
    scene_name: str
    title: str
    passed: bool = True
    score: float = 0.0
    max_score: float = 0.0
    criteria: list[ScorecardCriterion] = Field(default_factory=list)


class DemoRunListResponse(BaseModel):
    items: list[DemoRunRecord] = Field(default_factory=list)


class ShiftScoreSummary(BaseModel):
    score: float = 0.0
    max_score: float = 0.0
    rating: str = "unscored"
    summary_text: str | None = None
    criteria: list[ScorecardCriterion] = Field(default_factory=list)


class ShiftSimulationStepDefinition(BaseModel):
    step_id: str = Field(default_factory=lambda: str(uuid4()))
    label: str
    action_type: ShiftSimulationStepActionType
    at: datetime | None = None
    offset_seconds: float | None = None
    session_id: str | None = None
    participant_id: str | None = None
    input_text: str | None = None
    event_type: str | None = None
    payload: dict[str, object] = Field(default_factory=dict)
    ticket_id: str | None = None
    operator_name: str | None = None
    assignee_name: str | None = None
    note: str | None = None

    @model_validator(mode="after")
    def validate_schedule_and_payload(self) -> "ShiftSimulationStepDefinition":
        if self.at is None and self.offset_seconds is None:
            raise ValueError("shift_simulation_step_requires_at_or_offset_seconds")
        if self.action_type == ShiftSimulationStepActionType.SPEECH_TURN and not self.input_text:
            raise ValueError("shift_simulation_speech_turn_requires_input_text")
        if self.action_type == ShiftSimulationStepActionType.SENSOR_EVENT and not self.event_type:
            raise ValueError("shift_simulation_sensor_event_requires_event_type")
        if self.action_type == ShiftSimulationStepActionType.INCIDENT_ASSIGN and not self.assignee_name:
            raise ValueError("shift_simulation_incident_assign_requires_assignee_name")
        return self


class ShiftSimulationDefinition(BaseModel):
    simulation_name: str
    description: str
    site_name: str | None = None
    venue_content_dir: str | None = None
    fixture_path: str | None = None
    start_at: datetime | None = None
    steps: list[ShiftSimulationStepDefinition] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_offsets(self) -> "ShiftSimulationDefinition":
        if any(step.offset_seconds is not None for step in self.steps) and self.start_at is None:
            raise ValueError("shift_simulation_requires_start_at_for_offset_steps")
        return self


class ShiftSimulationStepRecord(BaseModel):
    step_id: str
    label: str
    action_type: ShiftSimulationStepActionType
    scheduled_at: datetime
    completed_at: datetime | None = None
    session_id: str | None = None
    participant_id: str | None = None
    event: RobotEvent | None = None
    response: CommandBatch | None = None
    command_acks: list[CommandAck] = Field(default_factory=list)
    telemetry: TelemetrySnapshot | None = None
    heartbeat: HeartbeatStatus | None = None
    incident_ticket: IncidentTicketRecord | None = None
    success: bool = True
    outcome: str = "ok"
    latency_ms: float = 0.0
    trace_id: str | None = None
    shift_state: ShiftOperatingState | None = None
    note: str | None = None


class ShiftReportSummary(BaseModel):
    report_id: str = Field(default_factory=lambda: str(uuid4()))
    schema_version: str = "blink_shift_report/v1"
    simulation_name: str
    description: str
    site_name: str | None = None
    fixture_path: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    completed_at: datetime | None = None
    status: ShiftReportStatus = ShiftReportStatus.RUNNING
    configured_dialogue_backend: str | None = None
    observed_dialogue_backends: list[str] = Field(default_factory=list)
    runtime_profile: str | None = None
    deployment_target: str | None = None
    session_ids: list[str] = Field(default_factory=list)
    metrics: ShiftMetricsSnapshot = Field(default_factory=ShiftMetricsSnapshot)
    score_summary: ShiftScoreSummary = Field(default_factory=ShiftScoreSummary)
    artifact_dir: str | None = None
    artifact_files: dict[str, str] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)


class ShiftReportRecord(ShiftReportSummary):
    simulation_definition: ShiftSimulationDefinition | None = None
    steps: list[ShiftSimulationStepRecord] = Field(default_factory=list)
    final_world_state: WorldState | None = None
    final_shift_supervisor: ShiftSupervisorSnapshot | None = None
    final_incidents: list[IncidentTicketRecord] = Field(default_factory=list)


class ShiftReportListResponse(BaseModel):
    items: list[ShiftReportSummary] = Field(default_factory=list)


class EpisodeSessionMetadata(BaseModel):
    session_id: str
    user_id: str | None = None
    channel: str = "speech"
    scenario_name: str | None = None
    status: SessionStatus = SessionStatus.ACTIVE
    active_incident_ticket_id: str | None = None
    incident_status: IncidentStatus | None = None
    response_mode: ResponseMode = ResponseMode.GUIDE
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    current_topic: str | None = None
    conversation_summary: str | None = None
    session_memory: dict[str, str] = Field(default_factory=dict)
    operator_notes: list[OperatorNote] = Field(default_factory=list)


class EpisodeTranscriptEntry(BaseModel):
    session_id: str
    turn: ConversationTurn


class EpisodeToolCallRecord(BaseModel):
    session_id: str | None = None
    trace_id: str | None = None
    timestamp: datetime | None = None
    tool: ToolInvocationRecord


class EpisodeCommandRecord(BaseModel):
    session_id: str | None = None
    trace_id: str | None = None
    timestamp: datetime | None = None
    scenario_name: str | None = None
    step_index: int | None = None
    command: RobotCommand


class EpisodeAcknowledgementRecord(BaseModel):
    session_id: str | None = None
    trace_id: str | None = None
    timestamp: datetime | None = None
    scenario_name: str | None = None
    step_index: int | None = None
    ack: CommandAck


class EpisodeTelemetryRecord(BaseModel):
    session_id: str | None = None
    trace_id: str | None = None
    timestamp: datetime = Field(default_factory=utc_now)
    source: str = "episode_export"
    note: str | None = None
    telemetry: TelemetrySnapshot


class EpisodeAssetReference(BaseModel):
    asset_id: str = Field(default_factory=lambda: str(uuid4()))
    asset_kind: EpisodeAssetKind = EpisodeAssetKind.OTHER
    session_id: str | None = None
    trace_id: str | None = None
    snapshot_id: str | None = None
    source_kind: str = "unknown"
    path: str | None = None
    label: str | None = None
    mime_type: str | None = None
    captured_at: datetime | None = None
    received_at: datetime | None = None
    metadata: dict[str, object] = Field(default_factory=dict)


class EpisodeAnnotationLabel(BaseModel):
    label_name: EpisodeLabelName
    status: EpisodeAnnotationStatus = EpisodeAnnotationStatus.PENDING_REVIEW
    suggested_value: str = "not_applicable"
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    evidence_refs: list[str] = Field(default_factory=list)
    note: str | None = None


class EpisodeSummary(BaseModel):
    episode_id: str = Field(default_factory=lambda: str(uuid4()))
    schema_version: str = "blink_episode/v1"
    source_type: EpisodeSourceType
    source_id: str
    exported_at: datetime = Field(default_factory=utc_now)
    session_ids: list[str] = Field(default_factory=list)
    scenario_names: list[str] = Field(default_factory=list)
    configured_dialogue_backend: str | None = None
    observed_dialogue_backends: list[str] = Field(default_factory=list)
    runtime_profile: str | None = None
    deployment_target: str | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    transcript_turn_count: int = 0
    trace_count: int = 0
    tool_call_count: int = 0
    perception_snapshot_count: int = 0
    world_model_transition_count: int = 0
    executive_decision_count: int = 0
    incident_count: int = 0
    incident_timeline_count: int = 0
    command_count: int = 0
    acknowledgement_count: int = 0
    telemetry_count: int = 0
    episodic_memory_count: int = 0
    semantic_memory_count: int = 0
    profile_memory_count: int = 0
    asset_ref_count: int = 0
    annotation_count: int = 0
    redactions_applied: list[str] = Field(default_factory=list)
    artifact_dir: str | None = None
    artifact_files: dict[str, str] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)


class EpisodeRecord(EpisodeSummary):
    sessions: list[EpisodeSessionMetadata] = Field(default_factory=list)
    transcript: list[EpisodeTranscriptEntry] = Field(default_factory=list)
    traces: list["TraceRecord"] = Field(default_factory=list)
    tool_calls: list[EpisodeToolCallRecord] = Field(default_factory=list)
    perception_snapshots: list[PerceptionSnapshotRecord] = Field(default_factory=list)
    world_model_transitions: list[WorldModelTransitionRecord] = Field(default_factory=list)
    executive_decisions: list[ExecutiveDecisionRecord] = Field(default_factory=list)
    incidents: list[IncidentTicketRecord] = Field(default_factory=list)
    incident_timeline: list[IncidentTimelineRecord] = Field(default_factory=list)
    commands: list[EpisodeCommandRecord] = Field(default_factory=list)
    acknowledgements: list[EpisodeAcknowledgementRecord] = Field(default_factory=list)
    telemetry: list[EpisodeTelemetryRecord] = Field(default_factory=list)
    episodic_memory: list[EpisodicMemoryRecord] = Field(default_factory=list)
    semantic_memory: list[SemanticMemoryRecord] = Field(default_factory=list)
    profile_memory: list[UserMemoryRecord] = Field(default_factory=list)
    grounding_sources: list[GroundingSourceRecord] = Field(default_factory=list)
    final_world_state: WorldState | None = None
    final_world_model: EmbodiedWorldModel | None = None
    asset_refs: list[EpisodeAssetReference] = Field(default_factory=list)
    annotations: list[EpisodeAnnotationLabel] = Field(default_factory=list)


class EpisodeManifest(BaseModel):
    schema_version: str = "blink_episode/v1"
    episode_id: str
    source_type: EpisodeSourceType
    source_id: str
    exported_at: datetime = Field(default_factory=utc_now)
    session_ids: list[str] = Field(default_factory=list)
    scenario_names: list[str] = Field(default_factory=list)
    artifact_files: dict[str, str] = Field(default_factory=dict)
    redactions_applied: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class EpisodeListResponse(BaseModel):
    items: list[EpisodeSummary] = Field(default_factory=list)


class EpisodeExportSessionRequest(BaseModel):
    session_id: str
    redact_operator_notes: bool = False
    redact_session_memory: bool = False
    include_asset_refs: bool = True
    redaction_profile: ExportRedactionProfile = ExportRedactionProfile.LOCAL_FULL


class EpisodeExportRunRequest(BaseModel):
    run_id: str
    redact_operator_notes: bool = False
    redact_session_memory: bool = False
    include_asset_refs: bool = True
    redaction_profile: ExportRedactionProfile = ExportRedactionProfile.LOCAL_FULL


class EpisodeExportShiftReportRequest(BaseModel):
    report_id: str
    redact_operator_notes: bool = False
    redact_session_memory: bool = False
    include_asset_refs: bool = True
    redaction_profile: ExportRedactionProfile = ExportRedactionProfile.LOCAL_FULL


class DemoCheckResult(BaseModel):
    check_name: str
    description: str
    started_at: datetime = Field(default_factory=utc_now)
    completed_at: datetime | None = None
    passed: bool = True
    session_id: str | None = None
    scenario_names: list[str] = Field(default_factory=list)
    backend_used: str | None = None
    reply_text: str | None = None
    command_types: list[CommandType] = Field(default_factory=list)
    latency_ms: float | None = None
    fallback_events: list[DemoFallbackEvent] = Field(default_factory=list)
    final_world_state: WorldState | None = None
    latency_breakdown: LatencyBreakdownRecord = Field(default_factory=LatencyBreakdownRecord)
    grounding_sources: list[GroundingSourceRecord] = Field(default_factory=list)
    scorecard: DemoSceneScorecard | None = None
    notes: list[str] = Field(default_factory=list)
    artifact_files: dict[str, str] = Field(default_factory=dict)


class DemoCheckSuiteRecord(BaseModel):
    suite_id: str = Field(default_factory=lambda: str(uuid4()))
    created_at: datetime = Field(default_factory=utc_now)
    completed_at: datetime | None = None
    passed: bool = True
    configured_dialogue_backend: str | None = None
    runtime_profile: str | None = None
    deployment_target: str | None = None
    items: list[DemoCheckResult] = Field(default_factory=list)
    artifact_dir: str | None = None
    artifact_files: dict[str, str] = Field(default_factory=dict)


class LocalCompanionCertificationVerdict(str, Enum):
    MACHINE_BLOCKER = "machine_blocker"
    REPO_OR_RUNTIME_BUG = "repo_or_runtime_bug"
    DEGRADED_BUT_ACCEPTABLE = "degraded_but_acceptable"
    CERTIFIED = "certified"


class LocalCompanionCertificationIssueRecord(BaseModel):
    bucket: LocalCompanionCertificationVerdict
    category: str
    message: str
    blocking: bool = False


class LocalCompanionRubricScoreRecord(BaseModel):
    category: str
    score: float = 0.0
    max_score: float = 2.0
    passed: bool = False
    hard_blocker: bool = False
    minimum_pass_bar: str | None = None
    world_class_bar: str | None = None
    observed: str | None = None
    notes: list[str] = Field(default_factory=list)


class LocalCompanionReadinessRecord(BaseModel):
    verdict: LocalCompanionCertificationVerdict = LocalCompanionCertificationVerdict.DEGRADED_BUT_ACCEPTABLE
    summary: str | None = None
    machine_ready: bool = False
    product_ready: bool = False
    machine_blockers: list[str] = Field(default_factory=list)
    repo_or_runtime_issues: list[str] = Field(default_factory=list)
    degraded_warnings: list[str] = Field(default_factory=list)
    last_run_at: datetime | None = None
    last_certified_at: datetime | None = None
    artifact_dir: str | None = None
    doctor_report_path: str | None = None
    next_actions: list[str] = Field(default_factory=list)


class LocalCompanionCertificationRecord(BaseModel):
    cert_id: str = Field(default_factory=lambda: str(uuid4()))
    created_at: datetime = Field(default_factory=utc_now)
    completed_at: datetime | None = None
    verdict: LocalCompanionCertificationVerdict = LocalCompanionCertificationVerdict.DEGRADED_BUT_ACCEPTABLE
    machine_readiness_passed: bool = False
    repo_runtime_correctness_passed: bool = False
    companion_behavior_quality_passed: bool = False
    operator_ux_quality_passed: bool = False
    blocking_issues: list[str] = Field(default_factory=list)
    machine_readiness: LocalCompanionReadinessRecord = Field(default_factory=LocalCompanionReadinessRecord)
    rubric: list[LocalCompanionRubricScoreRecord] = Field(default_factory=list)
    issues: list[LocalCompanionCertificationIssueRecord] = Field(default_factory=list)
    artifact_dir: str | None = None
    artifact_files: dict[str, str] = Field(default_factory=dict)
    linked_episode_ids: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)


class CommunityEventRecord(BaseModel):
    event_id: str
    title: str
    event_date: date
    start_time: time
    location_key: str
    summary: str


class LocationRecord(BaseModel):
    location_key: str
    title: str
    floor: str
    directions: str


__all__ = [
    "CommandType",
    "CommunityEventRecord",
    "DemoCheckResult",
    "DemoCheckSuiteRecord",
    "DemoFallbackEvent",
    "DemoRunListResponse",
    "DemoRunMetrics",
    "DemoRunRecord",
    "DemoRunRequest",
    "DemoRunStatus",
    "DemoRunStepRecord",
    "DemoSceneScorecard",
    "EpisodeAcknowledgementRecord",
    "EpisodeAnnotationLabel",
    "EpisodeAnnotationStatus",
    "EpisodeAssetKind",
    "EpisodeAssetReference",
    "EpisodeCommandRecord",
    "EpisodeExportRunRequest",
    "EpisodeExportSessionRequest",
    "EpisodeExportShiftReportRequest",
    "EpisodeLabelName",
    "EpisodeListResponse",
    "EpisodeManifest",
    "EpisodeRecord",
    "EpisodeSessionMetadata",
    "EpisodeSourceType",
    "EpisodeSummary",
    "EpisodeTelemetryRecord",
    "EpisodeToolCallRecord",
    "EpisodeTranscriptEntry",
    "FinalActionRecord",
    "LocationRecord",
    "LocalCompanionCertificationIssueRecord",
    "LocalCompanionCertificationRecord",
    "LocalCompanionCertificationVerdict",
    "LocalCompanionReadinessRecord",
    "LocalCompanionRubricScoreRecord",
    "ShiftReportListResponse",
    "ShiftReportRecord",
    "ShiftReportStatus",
    "ShiftReportSummary",
    "ScorecardCriterion",
    "ShiftScoreSummary",
    "ShiftSimulationDefinition",
    "ShiftSimulationStepActionType",
    "ShiftSimulationStepDefinition",
    "ShiftSimulationStepRecord",
]
