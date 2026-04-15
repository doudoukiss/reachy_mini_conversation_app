from __future__ import annotations

from ._common import (
    Any,
    BaseModel,
    AttentionTargetType,
    CommandType,
    EnvironmentState,
    EngagementState,
    ExecutiveDecisionType,
    FactFreshness,
    Field,
    InteractionExecutiveState,
    PerceptionEventType,
    PerceptionObservationType,
    PerceptionProviderMode,
    PerceptionSnapshotStatus,
    PerceptionTier,
    SceneClaimKind,
    SemanticQualityClass,
    SocialRuntimeMode,
    VisualAnchorType,
    WatcherEngagementShift,
    WatcherMotionState,
    WatcherPresenceState,
    datetime,
    utc_now,
    uuid4,
)
from .brain import LatencyBreakdownRecord, ParticipantRouterSnapshot
from .edge import CommandAck, CommandBatch, RobotEvent


class PerceptionConfidence(BaseModel):
    score: float = Field(default=0.0, ge=0.0, le=1.0)
    label: str = "low"


class PerceptionSourceFrame(BaseModel):
    source_kind: str = "unknown"
    source_label: str | None = None
    frame_id: str = Field(default_factory=lambda: str(uuid4()))
    mime_type: str | None = None
    width_px: int | None = None
    height_px: int | None = None
    captured_at: datetime | None = None
    received_at: datetime = Field(default_factory=utc_now)
    fixture_path: str | None = None
    file_name: str | None = None
    clip_offset_ms: float | None = None
    clip_duration_ms: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class PerceptionObservation(BaseModel):
    observation_id: str = Field(default_factory=lambda: str(uuid4()))
    observation_type: PerceptionObservationType
    text_value: str | None = None
    number_value: float | None = None
    bool_value: bool | None = None
    confidence: PerceptionConfidence = Field(default_factory=PerceptionConfidence)
    claim_kind: SceneClaimKind = SceneClaimKind.SEMANTIC_OBSERVATION
    quality_class: SemanticQualityClass | None = None
    justification: str | None = None
    source_frame: PerceptionSourceFrame
    metadata: dict[str, Any] = Field(default_factory=dict)


class WorldModelParticipant(BaseModel):
    participant_id: str
    label: str = "likely visitor"
    confidence: PerceptionConfidence = Field(default_factory=PerceptionConfidence)
    claim_kind: SceneClaimKind = SceneClaimKind.WATCHER_HINT
    quality_class: SemanticQualityClass | None = None
    in_view: bool = True
    observed_at: datetime = Field(default_factory=utc_now)
    last_seen_at: datetime | None = None
    last_heard_at: datetime | None = None
    likely_session_id: str | None = None
    expires_at: datetime | None = None
    source_event_type: str | None = None
    freshness: FactFreshness = FactFreshness.UNKNOWN
    provenance: list[str] = Field(default_factory=list)
    uncertainty_marker: str | None = None
    source_tier: PerceptionTier = PerceptionTier.WATCHER


class AttentionTargetRecord(BaseModel):
    target_type: AttentionTargetType = AttentionTargetType.NONE
    target_label: str | None = None
    confidence: PerceptionConfidence = Field(default_factory=PerceptionConfidence)
    claim_kind: SceneClaimKind = SceneClaimKind.WATCHER_HINT
    quality_class: SemanticQualityClass | None = None
    observed_at: datetime = Field(default_factory=utc_now)
    expires_at: datetime | None = None
    freshness: FactFreshness = FactFreshness.UNKNOWN
    provenance: list[str] = Field(default_factory=list)
    uncertainty_marker: str | None = None
    rationale: str | None = None
    source_tier: PerceptionTier = PerceptionTier.WATCHER


class WorldModelAnchor(BaseModel):
    anchor_id: str = Field(default_factory=lambda: str(uuid4()))
    anchor_type: VisualAnchorType = VisualAnchorType.OBJECT
    label: str
    confidence: PerceptionConfidence = Field(default_factory=PerceptionConfidence)
    claim_kind: SceneClaimKind = SceneClaimKind.SEMANTIC_OBSERVATION
    quality_class: SemanticQualityClass | None = None
    justification: str | None = None
    observed_at: datetime = Field(default_factory=utc_now)
    expires_at: datetime | None = None
    source_event_type: str | None = None
    freshness: FactFreshness = FactFreshness.UNKNOWN
    provenance: list[str] = Field(default_factory=list)
    uncertainty_marker: str | None = None
    source_tier: PerceptionTier = PerceptionTier.SEMANTIC


class WorldModelObservation(BaseModel):
    observation_id: str = Field(default_factory=lambda: str(uuid4()))
    label: str
    confidence: PerceptionConfidence = Field(default_factory=PerceptionConfidence)
    claim_kind: SceneClaimKind = SceneClaimKind.SEMANTIC_OBSERVATION
    quality_class: SemanticQualityClass | None = None
    justification: str | None = None
    observed_at: datetime = Field(default_factory=utc_now)
    expires_at: datetime | None = None
    source_event_type: str | None = None
    freshness: FactFreshness = FactFreshness.UNKNOWN
    provenance: list[str] = Field(default_factory=list)
    uncertainty_marker: str | None = None
    source_tier: PerceptionTier = PerceptionTier.SEMANTIC


class ExecutiveDecisionRecord(BaseModel):
    decision_id: str = Field(default_factory=lambda: str(uuid4()))
    session_id: str | None = None
    decision_type: ExecutiveDecisionType
    policy_name: str | None = None
    policy_outcome: str | None = None
    suppressed_reason: str | None = None
    executive_state: InteractionExecutiveState = InteractionExecutiveState.IDLE
    trigger_event_type: str
    applied: bool = True
    reason_codes: list[str] = Field(default_factory=list)
    note: str | None = None
    command_types: list[CommandType] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)


class ExecutiveDecisionListResponse(BaseModel):
    items: list[ExecutiveDecisionRecord] = Field(default_factory=list)


class EmbodiedWorldModel(BaseModel):
    active_participants_in_view: list[WorldModelParticipant] = Field(default_factory=list)
    current_speaker_participant_id: str | None = None
    current_speaker_session_id: str | None = None
    speaker_hypothesis_source: str | None = None
    speaker_hypothesis_expires_at: datetime | None = None
    likely_user_session_id: str | None = None
    participant_router: ParticipantRouterSnapshot = Field(default_factory=ParticipantRouterSnapshot)
    engagement_state: EngagementState = EngagementState.UNKNOWN
    engagement_confidence: PerceptionConfidence = Field(default_factory=PerceptionConfidence)
    engagement_observed_at: datetime | None = None
    engagement_expires_at: datetime | None = None
    visual_anchors: list[WorldModelAnchor] = Field(default_factory=list)
    recent_visible_text: list[WorldModelObservation] = Field(default_factory=list)
    recent_named_objects: list[WorldModelObservation] = Field(default_factory=list)
    recent_participant_attributes: list[WorldModelObservation] = Field(default_factory=list)
    attention_target: AttentionTargetRecord | None = None
    executive_state: InteractionExecutiveState = InteractionExecutiveState.IDLE
    turn_state: InteractionExecutiveState = InteractionExecutiveState.IDLE
    social_runtime_mode: SocialRuntimeMode = SocialRuntimeMode.IDLE
    environment_state: EnvironmentState = EnvironmentState.UNKNOWN
    environment_confidence: PerceptionConfidence = Field(default_factory=PerceptionConfidence)
    environment_observed_at: datetime | None = None
    environment_expires_at: datetime | None = None
    scene_freshness: FactFreshness = FactFreshness.UNKNOWN
    perception_limited_awareness: bool = False
    device_awareness_constraints: list[str] = Field(default_factory=list)
    uncertainty_markers: list[str] = Field(default_factory=list)
    last_perception_at: datetime | None = None
    last_semantic_refresh_at: datetime | None = None
    last_semantic_refresh_reason: str | None = None
    latest_observer_event_at: datetime | None = None
    last_user_speech_at: datetime | None = None
    last_robot_speech_at: datetime | None = None
    last_interruption_at: datetime | None = None
    last_updated: datetime = Field(default_factory=utc_now)


class WorldModelTransitionRecord(BaseModel):
    transition_id: str = Field(default_factory=lambda: str(uuid4()))
    session_id: str | None = None
    trace_id: str | None = None
    source_event_type: str
    intent: str | None = None
    changed_fields: list[str] = Field(default_factory=list)
    before: EmbodiedWorldModel
    after: EmbodiedWorldModel
    created_at: datetime = Field(default_factory=utc_now)
    notes: list[str] = Field(default_factory=list)


class WorldModelTransitionListResponse(BaseModel):
    items: list[WorldModelTransitionRecord] = Field(default_factory=list)


class EngagementTimelinePoint(BaseModel):
    timestamp: datetime = Field(default_factory=utc_now)
    session_id: str | None = None
    engagement_state: EngagementState = EngagementState.UNKNOWN
    attention_target: str | None = None
    confidence: PerceptionConfidence = Field(default_factory=PerceptionConfidence)
    source_event_type: str | None = None


class SceneObserverEventRecord(BaseModel):
    observer_event_id: str = Field(default_factory=lambda: str(uuid4()))
    observed_at: datetime = Field(default_factory=utc_now)
    backend: str = "frame_diff_fallback"
    source_kind: str | None = None
    person_present: bool | None = None
    presence_state: WatcherPresenceState = WatcherPresenceState.UNKNOWN
    people_count_estimate: int | None = None
    attention_state: str | None = None
    attention_target_hint: str | None = None
    attention_toward_device_score: float | None = Field(default=None, ge=0.0, le=1.0)
    scene_change_score: float = Field(default=0.0, ge=0.0, le=1.0)
    motion_changed: bool = False
    motion_state: WatcherMotionState = WatcherMotionState.UNKNOWN
    new_entrant: bool = False
    engagement_shift_hint: WatcherEngagementShift = WatcherEngagementShift.UNKNOWN
    signal_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    environment_state: EnvironmentState = EnvironmentState.UNKNOWN
    refresh_recommended: bool = False
    refresh_reason: str | None = None
    capability_limits: list[str] = Field(default_factory=list)
    limited_awareness: bool = False
    freshness: FactFreshness = FactFreshness.FRESH
    provenance: list[str] = Field(default_factory=list)


class SceneObserverEventListResponse(BaseModel):
    items: list[SceneObserverEventRecord] = Field(default_factory=list)


class PerceptionEventRecord(BaseModel):
    perception_event_id: str = Field(default_factory=lambda: str(uuid4()))
    event_type: PerceptionEventType
    session_id: str | None = None
    source: str = "perception_bus"
    provider_mode: PerceptionProviderMode
    confidence: PerceptionConfidence = Field(default_factory=PerceptionConfidence)
    source_frame: PerceptionSourceFrame
    timestamp: datetime = Field(default_factory=utc_now)
    payload: dict[str, Any] = Field(default_factory=dict)
    robot_event_id: str | None = None
    trace_id: str | None = None


class PerceptionSnapshotRecord(BaseModel):
    snapshot_id: str = Field(default_factory=lambda: str(uuid4()))
    session_id: str | None = None
    provider_mode: PerceptionProviderMode = PerceptionProviderMode.STUB
    tier: PerceptionTier = PerceptionTier.SEMANTIC
    trigger_reason: str | None = None
    source: str = "operator_console"
    status: PerceptionSnapshotStatus = PerceptionSnapshotStatus.OK
    limited_awareness: bool = False
    dialogue_eligible: bool = False
    message: str | None = None
    scene_summary: str | None = None
    source_frame: PerceptionSourceFrame
    observations: list[PerceptionObservation] = Field(default_factory=list)
    events: list[PerceptionEventRecord] = Field(default_factory=list)
    device_awareness_constraints: list[str] = Field(default_factory=list)
    uncertainty_markers: list[str] = Field(default_factory=list)
    provenance: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)


class PerceptionFactRecord(BaseModel):
    fact_id: str = Field(default_factory=lambda: str(uuid4()))
    fact_type: str
    label: str
    detail: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    claim_kind: SceneClaimKind = SceneClaimKind.SEMANTIC_OBSERVATION
    quality_class: SemanticQualityClass | None = None
    justification: str | None = None
    observed_at: datetime | None = None
    expires_at: datetime | None = None
    source_ref: str | None = None
    limited_awareness: bool = False
    freshness: FactFreshness = FactFreshness.UNKNOWN
    source_tier: PerceptionTier = PerceptionTier.SEMANTIC
    uncertain: bool = False
    provenance: list[str] = Field(default_factory=list)
    grounding_eligible: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


class PerceptionAnnotationInput(BaseModel):
    observation_type: PerceptionObservationType
    text_value: str | None = None
    number_value: float | None = None
    bool_value: bool | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class PerceptionSnapshotSubmitRequest(BaseModel):
    session_id: str | None = None
    provider_mode: PerceptionProviderMode = PerceptionProviderMode.STUB
    tier: PerceptionTier = PerceptionTier.SEMANTIC
    trigger_reason: str | None = None
    source: str = "operator_console"
    image_data_url: str | None = None
    source_frame: PerceptionSourceFrame | None = None
    annotations: list[PerceptionAnnotationInput] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    publish_events: bool = True


class PerceptionPublishedResult(BaseModel):
    event: RobotEvent
    response: CommandBatch
    command_acks: list[CommandAck] = Field(default_factory=list)
    success: bool = True
    outcome: str = "ok"


class PerceptionSubmissionResult(BaseModel):
    session_id: str | None = None
    snapshot: PerceptionSnapshotRecord
    published_results: list[PerceptionPublishedResult] = Field(default_factory=list)
    success: bool = True
    message: str | None = None
    latency_breakdown: LatencyBreakdownRecord = Field(default_factory=LatencyBreakdownRecord)


class PerceptionReplayRequest(BaseModel):
    session_id: str | None = None
    fixture_path: str
    source: str = "operator_console"
    publish_events: bool = True


class PerceptionReplayResult(BaseModel):
    session_id: str | None = None
    fixture_path: str
    snapshots: list[PerceptionSubmissionResult] = Field(default_factory=list)
    success: bool = True
    message: str | None = None
    latency_breakdown: LatencyBreakdownRecord = Field(default_factory=LatencyBreakdownRecord)


class PerceptionHistoryResponse(BaseModel):
    items: list[PerceptionSnapshotRecord] = Field(default_factory=list)


class PerceptionFactListResponse(BaseModel):
    items: list[PerceptionFactRecord] = Field(default_factory=list)


class PerceptionFixtureDefinition(BaseModel):
    fixture_name: str
    title: str
    description: str
    fixture_path: str
    source_kind: str = "video_file_replay"


class PerceptionFixtureCatalogResponse(BaseModel):
    items: list[PerceptionFixtureDefinition] = Field(default_factory=list)


__all__ = [
    "AttentionTargetRecord",
    "AttentionTargetType",
    "EmbodiedWorldModel",
    "EngagementState",
    "EngagementTimelinePoint",
    "ExecutiveDecisionListResponse",
    "ExecutiveDecisionRecord",
    "FactFreshness",
    "ExecutiveDecisionType",
    "InteractionExecutiveState",
    "EnvironmentState",
    "PerceptionAnnotationInput",
    "PerceptionConfidence",
    "PerceptionEventRecord",
    "PerceptionEventType",
    "PerceptionFactListResponse",
    "PerceptionFactRecord",
    "PerceptionFixtureCatalogResponse",
    "PerceptionFixtureDefinition",
    "PerceptionHistoryResponse",
    "PerceptionObservation",
    "PerceptionObservationType",
    "PerceptionProviderMode",
    "PerceptionPublishedResult",
    "PerceptionReplayRequest",
    "PerceptionReplayResult",
    "PerceptionSnapshotRecord",
    "PerceptionSnapshotStatus",
    "PerceptionSnapshotSubmitRequest",
    "PerceptionSourceFrame",
    "PerceptionSubmissionResult",
    "PerceptionTier",
    "SceneObserverEventListResponse",
    "SceneObserverEventRecord",
    "SocialRuntimeMode",
    "VisualAnchorType",
    "WorldModelAnchor",
    "WorldModelObservation",
    "WorldModelParticipant",
    "WorldModelTransitionListResponse",
    "WorldModelTransitionRecord",
]
