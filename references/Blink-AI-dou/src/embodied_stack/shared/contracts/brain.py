from __future__ import annotations

from enum import Enum

from ._common import (
    AliasChoices,
    Any,
    AgentHookName,
    AgentValidationStatus,
    BaseModel,
    CheckpointKind,
    CheckpointStatus,
    CompanionBehaviorCategory,
    ConfigDict,
    EngagementState,
    ExecutiveDecisionType,
    FallbackClassification,
    FactFreshness,
    Field,
    GroundingSourceType,
    IncidentListScope,
    IncidentReasonCategory,
    IncidentResolutionOutcome,
    IncidentStatus,
    IncidentTimelineEventType,
    IncidentUrgency,
    InteractionExecutiveState,
    MemoryActionType,
    MemoryDecisionOutcome,
    MemoryLayer,
    MemoryRetrievalBackend,
    MemoryReviewStatus,
    MemoryWriteReasonCode,
    RedactionState,
    ReminderStatus,
    ReviewDebtState,
    ResponseMode,
    RobotMode,
    RunPhase,
    RunStatus,
    SceneClaimKind,
    SessionRoutingStatus,
    SessionStatus,
    ShiftOperatingState,
    SocialRuntimeMode,
    SensitiveContentFlag,
    SpeechOutputStatus,
    TraceOutcome,
    ToolEffectClass,
    ToolCapabilityState,
    ToolLatencyClass,
    ToolPermissionClass,
    ToolResultStatus,
    VenueFallbackScenario,
    VoiceRuntimeMode,
    _coerce_string_list,
    _normalize_weekdays,
    date,
    datetime,
    field_validator,
    model_validator,
    time,
    utc_now,
    uuid4,
)
from .action import ActionApprovalState, ActionExecutionStatus, ActionRiskClass
from .edge import CommandBatch, CommandType, HeartbeatStatus, RobotCommand, RobotEvent, TelemetrySnapshot


class VenueScheduleWindow(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    days: list[str] = Field(default_factory=list)
    start_local: time = Field(validation_alias=AliasChoices("start_local", "start"))
    end_local: time = Field(validation_alias=AliasChoices("end_local", "end"))
    label: str | None = None

    @field_validator("days", mode="before")
    @classmethod
    def _validate_days(cls, value: Any) -> list[str]:
        normalized = _normalize_weekdays(value)
        invalid = [item for item in normalized if item not in {
            "monday",
            "tuesday",
            "wednesday",
            "thursday",
            "friday",
            "saturday",
            "sunday",
        }]
        if invalid:
            raise ValueError(f"invalid weekdays: {', '.join(invalid)}")
        return normalized

    @model_validator(mode="after")
    def _validate_window(self) -> "VenueScheduleWindow":
        if not self.days:
            raise ValueError("schedule window requires at least one day")
        if self.start_local >= self.end_local:
            raise ValueError("schedule window start must be earlier than end")
        return self


class VenueProactiveGreetingPolicy(BaseModel):
    enabled: bool = True
    greeting_text: str | None = None
    returning_greeting_text: str | None = None
    cooldown_seconds: float = Field(default=45.0, ge=0.0)
    max_people_for_auto_greet: int = Field(default=2, ge=1)
    suppress_during_quiet_hours: bool = True


class VenueAnnouncementPolicy(BaseModel):
    enabled: bool = True
    opening_prompt_text: str | None = None
    opening_prompt_window_minutes: int = Field(default=20, ge=0, le=180)
    closing_prompt_text: str | None = None
    event_start_reminder_enabled: bool = True
    event_start_reminder_lead_minutes: int = Field(default=10, ge=1, le=180)
    event_start_reminder_text: str | None = None
    proactive_suggestions: list[str] = Field(default_factory=list)
    quiet_hours_suppressed: bool = True

    @field_validator("proactive_suggestions", mode="before")
    @classmethod
    def _validate_suggestions(cls, value: Any) -> list[str]:
        return _coerce_string_list(value)


class VenueEscalationKeywordRule(BaseModel):
    match_any: list[str] = Field(default_factory=list)
    reason_category: IncidentReasonCategory = IncidentReasonCategory.GENERAL_ESCALATION
    urgency: IncidentUrgency = IncidentUrgency.NORMAL
    staff_contact_key: str | None = None
    note: str | None = None

    @field_validator("match_any", mode="before")
    @classmethod
    def _validate_keywords(cls, value: Any) -> list[str]:
        normalized = [item.lower() for item in _coerce_string_list(value)]
        if not normalized:
            raise ValueError("escalation keyword rule requires at least one phrase")
        return normalized


class VenueEscalationPolicy(BaseModel):
    default_staff_contact_key: str | None = None
    accessibility_staff_contact_key: str | None = None
    keyword_rules: list[VenueEscalationKeywordRule] = Field(default_factory=list)


class VenueFallbackInstruction(BaseModel):
    scenario: VenueFallbackScenario
    visitor_message: str
    operator_note: str | None = None


class VenueOperationsSnapshot(BaseModel):
    source_ref: str | None = None
    site_name: str = "Unknown Site"
    timezone: str | None = None
    opening_hours: list[VenueScheduleWindow] = Field(default_factory=list)
    quiet_hours: list[VenueScheduleWindow] = Field(default_factory=list)
    closing_windows: list[VenueScheduleWindow] = Field(default_factory=list)
    proactive_greeting_policy: VenueProactiveGreetingPolicy = Field(default_factory=VenueProactiveGreetingPolicy)
    announcement_policy: VenueAnnouncementPolicy = Field(default_factory=VenueAnnouncementPolicy)
    escalation_policy_overrides: VenueEscalationPolicy = Field(default_factory=VenueEscalationPolicy)
    accessibility_notes: list[str] = Field(default_factory=list)
    fallback_instructions: list[VenueFallbackInstruction] = Field(default_factory=list)
    next_scheduled_prompt_at: datetime | None = None
    next_scheduled_prompt_type: str | None = None
    next_scheduled_prompt_note: str | None = None

    @field_validator("accessibility_notes", mode="before")
    @classmethod
    def _validate_accessibility_notes(cls, value: Any) -> list[str]:
        return _coerce_string_list(value)


class OperatorNote(BaseModel):
    note_id: str = Field(default_factory=lambda: str(uuid4()))
    text: str
    author: str = "operator"
    created_at: datetime = Field(default_factory=utc_now)


class IncidentStaffSuggestion(BaseModel):
    contact_key: str | None = None
    name: str | None = None
    role: str | None = None
    phone: str | None = None
    email: str | None = None
    desk_location_key: str | None = None
    desk_location_label: str | None = None
    operating_note: str | None = None
    event_title: str | None = None
    source_refs: list[str] = Field(default_factory=list)
    note: str | None = None


class IncidentNoteRecord(BaseModel):
    note_id: str = Field(default_factory=lambda: str(uuid4()))
    author: str = "operator"
    text: str
    created_at: datetime = Field(default_factory=utc_now)


class IncidentTimelineRecord(BaseModel):
    timeline_id: str = Field(default_factory=lambda: str(uuid4()))
    ticket_id: str
    session_id: str
    event_type: IncidentTimelineEventType
    from_status: IncidentStatus | None = None
    to_status: IncidentStatus
    actor: str | None = None
    note: str | None = None
    trace_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)


class IncidentTicketRecord(BaseModel):
    ticket_id: str = Field(default_factory=lambda: f"inc-{utc_now().strftime('%Y%m%d%H%M%S')}-{uuid4().hex[:6]}")
    session_id: str
    participant_id: str | None = None
    participant_summary: str
    reason_category: IncidentReasonCategory = IncidentReasonCategory.UNKNOWN
    urgency: IncidentUrgency = IncidentUrgency.NORMAL
    suggested_staff_contact: IncidentStaffSuggestion | None = None
    current_status: IncidentStatus = IncidentStatus.PENDING
    assigned_to: str | None = None
    resolution_outcome: IncidentResolutionOutcome | None = None
    notes: list[IncidentNoteRecord] = Field(default_factory=list)
    created_from_trace_id: str | None = None
    last_trace_id: str | None = None
    last_status_note: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    acknowledged_at: datetime | None = None
    assigned_at: datetime | None = None
    resolved_at: datetime | None = None
    closed_at: datetime | None = None
    updated_at: datetime = Field(default_factory=utc_now)


class MemoryPolicyScoreRecord(BaseModel):
    evidence_score: float = Field(default=0.0, ge=0.0, le=1.0)
    utility_score: float = Field(default=0.0, ge=0.0, le=1.0)
    durability_score: float = Field(default=0.0, ge=0.0, le=1.0)
    privacy_risk_score: float = Field(default=0.0, ge=0.0, le=1.0)
    promotion_score: float = Field(default=0.0, ge=0.0, le=1.0)
    review_priority: float = Field(default=0.0, ge=0.0, le=1.0)


class MemoryDecisionTrackedModel(BaseModel):
    policy_scorecard: MemoryPolicyScoreRecord = Field(default_factory=MemoryPolicyScoreRecord)
    decision_outcome: MemoryDecisionOutcome | None = None
    decision_reason_codes: list[str] = Field(default_factory=list)
    merged_into_memory_id: str | None = None
    supersedes_memory_ids: list[str] = Field(default_factory=list)
    review_debt_state: ReviewDebtState = ReviewDebtState.CLEAR
    sensitive_content_flags: list[SensitiveContentFlag] = Field(default_factory=list)
    redaction_state: RedactionState = RedactionState.RAW


class CompanionRelationshipProfile(BaseModel):
    greeting_preference: str | None = None
    planning_style: str | None = None
    tone_preferences: list[str] = Field(default_factory=list)
    interaction_boundaries: list[str] = Field(default_factory=list)
    continuity_preferences: list[str] = Field(default_factory=list)


class RelationshipThreadKind(str, Enum):
    PRACTICAL = "practical"
    EMOTIONAL = "emotional"


class RelationshipThreadStatus(str, Enum):
    OPEN = "open"
    RESOLVED = "resolved"
    STALE = "stale"


class RelationshipPromiseStatus(str, Enum):
    OPEN = "open"
    RESOLVED = "resolved"


class RelationshipTopicRecord(BaseModel):
    topic: str
    mention_count: int = 0
    first_seen_at: datetime = Field(default_factory=utc_now)
    last_seen_at: datetime = Field(default_factory=utc_now)
    source_refs: list[str] = Field(default_factory=list)


class RelationshipThreadRecord(BaseModel):
    thread_id: str = Field(default_factory=lambda: str(uuid4()))
    kind: RelationshipThreadKind = RelationshipThreadKind.PRACTICAL
    status: RelationshipThreadStatus = RelationshipThreadStatus.OPEN
    summary: str
    topic: str | None = None
    follow_up_requested: bool = False
    source_trace_ids: list[str] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)
    last_session_id: str | None = None
    opened_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class RelationshipPromiseRecord(BaseModel):
    promise_id: str = Field(default_factory=lambda: str(uuid4()))
    summary: str
    status: RelationshipPromiseStatus = RelationshipPromiseStatus.OPEN
    due_at: datetime | None = None
    source_trace_ids: list[str] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)
    opened_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class UserMemoryRecord(MemoryDecisionTrackedModel):
    user_id: str
    memory_layer: MemoryLayer = MemoryLayer.PROFILE
    display_name: str | None = None
    facts: dict[str, str] = Field(default_factory=dict)
    preferences: dict[str, str] = Field(default_factory=dict)
    relationship_profile: CompanionRelationshipProfile = Field(default_factory=CompanionRelationshipProfile)
    preferred_response_mode: ResponseMode | None = None
    interests: list[str] = Field(default_factory=list)
    visit_count: int = 0
    last_session_id: str | None = None
    reason_code: MemoryWriteReasonCode | None = None
    provenance_refs: list[str] = Field(default_factory=list)
    policy_basis: str | None = None
    review_status: MemoryReviewStatus = MemoryReviewStatus.APPROVED
    tombstoned: bool = False
    deleted_at: datetime | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class RelationshipMemoryRecord(MemoryDecisionTrackedModel):
    relationship_id: str
    memory_layer: MemoryLayer = MemoryLayer.RELATIONSHIP
    user_id: str
    familiarity: float = Field(default=0.0, ge=0.0, le=1.0)
    preferred_style: CompanionRelationshipProfile = Field(default_factory=CompanionRelationshipProfile)
    recurring_topics: list[RelationshipTopicRecord] = Field(default_factory=list)
    open_threads: list[RelationshipThreadRecord] = Field(default_factory=list)
    promises: list[RelationshipPromiseRecord] = Field(default_factory=list)
    last_session_id: str | None = None
    reason_code: MemoryWriteReasonCode | None = None
    provenance_refs: list[str] = Field(default_factory=list)
    policy_basis: str | None = None
    review_status: MemoryReviewStatus = MemoryReviewStatus.APPROVED
    tombstoned: bool = False
    deleted_at: datetime | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class RelationshipMemoryListResponse(BaseModel):
    items: list[RelationshipMemoryRecord] = Field(default_factory=list)


class EpisodicMemoryRecord(MemoryDecisionTrackedModel):
    memory_id: str
    memory_layer: MemoryLayer = MemoryLayer.EPISODIC
    session_id: str
    user_id: str | None = None
    title: str
    summary: str
    topics: list[str] = Field(default_factory=list)
    last_user_text: str | None = None
    last_reply_text: str | None = None
    source_trace_ids: list[str] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)
    reason_code: MemoryWriteReasonCode | None = None
    provenance_refs: list[str] = Field(default_factory=list)
    policy_basis: str | None = None
    review_status: MemoryReviewStatus = MemoryReviewStatus.APPROVED
    tombstoned: bool = False
    deleted_at: datetime | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class EpisodicMemoryListResponse(BaseModel):
    items: list[EpisodicMemoryRecord] = Field(default_factory=list)


class SemanticMemoryRecord(MemoryDecisionTrackedModel):
    memory_id: str
    memory_layer: MemoryLayer = MemoryLayer.SEMANTIC
    memory_kind: str
    summary: str
    canonical_value: str | None = None
    session_id: str | None = None
    user_id: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    tags: list[str] = Field(default_factory=list)
    source_trace_ids: list[str] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    reason_code: MemoryWriteReasonCode | None = None
    provenance_refs: list[str] = Field(default_factory=list)
    policy_basis: str | None = None
    review_status: MemoryReviewStatus = MemoryReviewStatus.APPROVED
    tombstoned: bool = False
    deleted_at: datetime | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class SemanticMemoryListResponse(BaseModel):
    items: list[SemanticMemoryRecord] = Field(default_factory=list)


class ProceduralMemoryRecord(MemoryDecisionTrackedModel):
    procedure_id: str = Field(default_factory=lambda: str(uuid4()))
    memory_layer: MemoryLayer = MemoryLayer.PROCEDURAL
    user_id: str | None = None
    session_id: str | None = None
    name: str
    summary: str
    trigger_phrases: list[str] = Field(default_factory=list)
    steps: list[str] = Field(default_factory=list)
    source_trace_ids: list[str] = Field(default_factory=list)
    source_refs: list[str] = Field(default_factory=list)
    enabled: bool = True
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    reason_code: MemoryWriteReasonCode | None = None
    provenance_refs: list[str] = Field(default_factory=list)
    policy_basis: str | None = None
    review_status: MemoryReviewStatus = MemoryReviewStatus.APPROVED
    tombstoned: bool = False
    deleted_at: datetime | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class ProceduralMemoryListResponse(BaseModel):
    items: list[ProceduralMemoryRecord] = Field(default_factory=list)


class ReminderRecord(MemoryDecisionTrackedModel):
    reminder_id: str = Field(default_factory=lambda: str(uuid4()))
    memory_layer: MemoryLayer = MemoryLayer.EPISODIC
    session_id: str
    user_id: str | None = None
    reminder_text: str
    due_at: datetime | None = None
    status: ReminderStatus = ReminderStatus.OPEN
    source_trace_ids: list[str] = Field(default_factory=list)
    last_triggered_at: datetime | None = None
    reason_code: MemoryWriteReasonCode | None = None
    provenance_refs: list[str] = Field(default_factory=list)
    policy_basis: str | None = None
    review_status: MemoryReviewStatus = MemoryReviewStatus.APPROVED
    tombstoned: bool = False
    deleted_at: datetime | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class ReminderListResponse(BaseModel):
    items: list[ReminderRecord] = Field(default_factory=list)


class CompanionNoteRecord(MemoryDecisionTrackedModel):
    note_id: str = Field(default_factory=lambda: str(uuid4()))
    memory_layer: MemoryLayer = MemoryLayer.EPISODIC
    session_id: str
    user_id: str | None = None
    title: str
    content: str
    tags: list[str] = Field(default_factory=list)
    source_trace_ids: list[str] = Field(default_factory=list)
    reason_code: MemoryWriteReasonCode | None = None
    provenance_refs: list[str] = Field(default_factory=list)
    policy_basis: str | None = None
    review_status: MemoryReviewStatus = MemoryReviewStatus.APPROVED
    tombstoned: bool = False
    deleted_at: datetime | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class CompanionNoteListResponse(BaseModel):
    items: list[CompanionNoteRecord] = Field(default_factory=list)


class SessionDigestRecord(MemoryDecisionTrackedModel):
    digest_id: str = Field(default_factory=lambda: str(uuid4()))
    memory_layer: MemoryLayer = MemoryLayer.EPISODIC
    session_id: str
    user_id: str | None = None
    summary: str
    turn_count: int = 0
    open_follow_ups: list[str] = Field(default_factory=list)
    source_trace_ids: list[str] = Field(default_factory=list)
    reason_code: MemoryWriteReasonCode | None = None
    provenance_refs: list[str] = Field(default_factory=list)
    policy_basis: str | None = None
    review_status: MemoryReviewStatus = MemoryReviewStatus.APPROVED
    tombstoned: bool = False
    deleted_at: datetime | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class SessionDigestListResponse(BaseModel):
    items: list[SessionDigestRecord] = Field(default_factory=list)


class SceneCacheRecord(BaseModel):
    session_id: str | None = None
    captured_at: datetime
    stale_after: datetime
    summary: str | None = None
    facts: list[str] = Field(default_factory=list)
    invalidated_because: str | None = None


class MemoryRetrievalCandidateRecord(BaseModel):
    memory_id: str | None = None
    layer: MemoryLayer | None = None
    summary: str
    reason: str | None = None
    score: float | None = Field(default=None, ge=0.0, le=1.0)
    source_refs: list[str] = Field(default_factory=list)
    session_id: str | None = None
    trace_id: str | None = None


class MemoryRetrievalRecord(BaseModel):
    retrieval_id: str = Field(default_factory=lambda: str(uuid4()))
    query_text: str
    backend: MemoryRetrievalBackend
    backend_detail: str | None = None
    session_id: str | None = None
    user_id: str | None = None
    trace_id: str | None = None
    run_id: str | None = None
    selected_candidates: list[MemoryRetrievalCandidateRecord] = Field(default_factory=list)
    rejected_candidates: list[MemoryRetrievalCandidateRecord] = Field(default_factory=list)
    miss_reason: str | None = None
    used_in_reply: bool = False
    latency_ms: float | None = None
    notes: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class MemoryRetrievalListResponse(BaseModel):
    items: list[MemoryRetrievalRecord] = Field(default_factory=list)


class MemoryReviewDebtSummary(BaseModel):
    pending_count: int = 0
    overdue_count: int = 0
    highest_priority: float = Field(default=0.0, ge=0.0, le=1.0)
    oldest_pending_at: datetime | None = None
    memory_ids: list[str] = Field(default_factory=list)


class MemoryPromotionRecord(BaseModel):
    promotion_id: str = Field(default_factory=lambda: str(uuid4()))
    promotion_type: str
    summary: str
    trace_id: str | None = None
    target_id: str | None = None
    reason: str | None = None
    updated_at: datetime = Field(default_factory=utc_now)


class MemoryActionRecord(MemoryDecisionTrackedModel):
    action_id: str = Field(default_factory=lambda: str(uuid4()))
    memory_id: str
    layer: MemoryLayer
    action_type: MemoryActionType = MemoryActionType.WRITE
    session_id: str | None = None
    user_id: str | None = None
    trace_id: str | None = None
    run_id: str | None = None
    tool_name: str | None = None
    episode_id: str | None = None
    summary: str
    reason_code: MemoryWriteReasonCode = MemoryWriteReasonCode.SESSION_CONTEXT
    provenance_refs: list[str] = Field(default_factory=list)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    policy_basis: str | None = None
    review_status: MemoryReviewStatus = MemoryReviewStatus.PENDING
    tombstoned: bool = False
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class MemoryActionListResponse(BaseModel):
    items: list[MemoryActionRecord] = Field(default_factory=list)


class MemoryReviewRecord(MemoryDecisionTrackedModel):
    review_id: str = Field(default_factory=lambda: str(uuid4()))
    memory_id: str
    layer: MemoryLayer
    action_type: MemoryActionType = MemoryActionType.REVIEW
    status: MemoryReviewStatus = MemoryReviewStatus.PENDING
    author: str = "operator"
    note: str | None = None
    updated_fields: dict[str, Any] = Field(default_factory=dict)
    provenance_refs: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class MemoryReviewListResponse(BaseModel):
    items: list[MemoryReviewRecord] = Field(default_factory=list)


class MemoryReviewRequest(BaseModel):
    memory_id: str
    layer: MemoryLayer
    note: str | None = None
    author: str = "operator"
    updated_fields: dict[str, Any] = Field(default_factory=dict)


class ConversationTurn(BaseModel):
    turn_id: str = Field(default_factory=lambda: str(uuid4()))
    timestamp: datetime = Field(default_factory=utc_now)
    event_type: str
    source: str | None = None
    participant_id: str | None = None
    incident_ticket_id: str | None = None
    user_text: str | None = None
    reply_text: str | None = None
    intent: str | None = None
    trace_id: str | None = None
    command_types: list[CommandType] = Field(default_factory=list)
    executive_reason_codes: list[str] = Field(default_factory=list)


class ParticipantSessionBinding(BaseModel):
    participant_id: str
    session_id: str | None = None
    likely: bool = True
    routing_status: SessionRoutingStatus = SessionRoutingStatus.ACTIVE
    in_view: bool = False
    first_seen_at: datetime = Field(default_factory=utc_now)
    last_seen_at: datetime | None = None
    last_heard_at: datetime | None = None
    wait_started_at: datetime | None = None
    resume_until_at: datetime | None = None
    priority_reason: str | None = None
    note: str | None = None


class QueuedParticipantRecord(BaseModel):
    participant_id: str
    session_id: str | None = None
    likely: bool = True
    queue_position: int = 0
    wait_started_at: datetime = Field(default_factory=utc_now)
    last_prompted_at: datetime | None = None
    last_seen_at: datetime | None = None
    priority_reason: str | None = None
    note: str | None = None


class ParticipantRouterSnapshot(BaseModel):
    active_participant_id: str | None = None
    active_session_id: str | None = None
    crowd_mode: bool = False
    active_speaker_retention_until: datetime | None = None
    queued_participants: list[QueuedParticipantRecord] = Field(default_factory=list)
    participant_sessions: list[ParticipantSessionBinding] = Field(default_factory=list)
    last_routing_reason: str | None = None
    updated_at: datetime = Field(default_factory=utc_now)


class SessionRecord(BaseModel):
    session_id: str
    user_id: str | None = None
    channel: str = "speech"
    scenario_name: str | None = None
    status: SessionStatus = SessionStatus.ACTIVE
    routing_status: SessionRoutingStatus = SessionRoutingStatus.ACTIVE
    participant_id: str | None = None
    active_incident_ticket_id: str | None = None
    incident_status: IncidentStatus | None = None
    response_mode: ResponseMode = ResponseMode.GUIDE
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    current_topic: str | None = None
    conversation_summary: str | None = None
    last_user_text: str | None = None
    last_reply_text: str | None = None
    last_participant_seen_at: datetime | None = None
    last_participant_heard_at: datetime | None = None
    resume_until_at: datetime | None = None
    routing_note: str | None = None
    events: list[RobotEvent] = Field(default_factory=list)
    transcript: list[ConversationTurn] = Field(default_factory=list)
    session_memory: dict[str, str] = Field(default_factory=dict)
    operator_notes: list[OperatorNote] = Field(default_factory=list)


class SessionSummary(BaseModel):
    session_id: str
    user_id: str | None = None
    scenario_name: str | None = None
    status: SessionStatus = SessionStatus.ACTIVE
    routing_status: SessionRoutingStatus = SessionRoutingStatus.ACTIVE
    participant_id: str | None = None
    active_incident_ticket_id: str | None = None
    incident_status: IncidentStatus | None = None
    response_mode: ResponseMode = ResponseMode.GUIDE
    current_topic: str | None = None
    conversation_summary: str | None = None
    last_reply_text: str | None = None
    turn_count: int = 0
    updated_at: datetime


class SessionCreateRequest(BaseModel):
    session_id: str | None = None
    user_id: str | None = None
    channel: str = "speech"
    scenario_name: str | None = None
    response_mode: ResponseMode = ResponseMode.GUIDE
    operator_notes: list[str] = Field(default_factory=list)


class OperatorNoteRequest(BaseModel):
    text: str
    author: str = "operator"


class IncidentAcknowledgeRequest(BaseModel):
    operator_name: str = "operator"
    note: str | None = None


class IncidentAssignRequest(BaseModel):
    assignee_name: str
    author: str = "operator"
    note: str | None = None


class IncidentNoteRequest(BaseModel):
    text: str
    author: str = "operator"


class IncidentResolveRequest(BaseModel):
    outcome: IncidentResolutionOutcome
    author: str = "operator"
    note: str | None = None


class SessionResponseModeRequest(BaseModel):
    response_mode: ResponseMode


class SessionListResponse(BaseModel):
    items: list[SessionSummary] = Field(default_factory=list)


class IncidentListResponse(BaseModel):
    items: list[IncidentTicketRecord] = Field(default_factory=list)


class IncidentTimelineResponse(BaseModel):
    items: list[IncidentTimelineRecord] = Field(default_factory=list)


class ShiftTimerSnapshot(BaseModel):
    timer_name: str
    active: bool = False
    deadline_at: datetime | None = None
    remaining_seconds: float | None = None


class ShiftSupervisorSnapshot(BaseModel):
    state: ShiftOperatingState = ShiftOperatingState.BOOTING
    reason_codes: list[str] = Field(default_factory=lambda: ["booting"])
    active_session_id: str | None = None
    active_user_id: str | None = None
    override_state: ShiftOperatingState | None = None
    override_reason: str | None = None
    override_active: bool = False
    last_transition_at: datetime = Field(default_factory=utc_now)
    last_presence_at: datetime | None = None
    presence_started_at: datetime | None = None
    last_interaction_at: datetime | None = None
    last_greeting_at: datetime | None = None
    last_attract_prompt_at: datetime | None = None
    last_proactive_outreach_at: datetime | None = None
    follow_up_deadline_at: datetime | None = None
    outreach_cooldown_until: datetime | None = None
    next_open_at: datetime | None = None
    next_close_at: datetime | None = None
    venue_timezone: str | None = None
    quiet_hours_active: bool = False
    closing_active: bool = False
    person_present: bool = False
    people_count: int = 0
    low_battery_active: bool = False
    transport_degraded: bool = False
    safe_idle_active: bool = False
    last_policy_note: str | None = None
    last_proactive_action: str | None = None
    last_scheduled_prompt_at: datetime | None = None
    last_scheduled_prompt_type: str | None = None
    last_scheduled_prompt_key: str | None = None
    issued_scheduled_prompt_keys: list[str] = Field(default_factory=list)
    next_scheduled_prompt_at: datetime | None = None
    next_scheduled_prompt_type: str | None = None
    next_scheduled_prompt_note: str | None = None
    timers: list[ShiftTimerSnapshot] = Field(default_factory=list)
    updated_at: datetime = Field(default_factory=utc_now)


class WorldState(BaseModel):
    mode: RobotMode = RobotMode.SIMULATED
    active_session_ids: list[str] = Field(default_factory=list)
    active_user_ids: list[str] = Field(default_factory=list)
    last_session_id: str | None = None
    last_event_type: str | None = None
    last_event_at: datetime | None = None
    person_detected: bool = False
    current_focus: str | None = None
    last_user_text: str | None = None
    last_reply_text: str | None = None
    pending_operator_session_ids: list[str] = Field(default_factory=list)
    open_incident_ticket_ids: list[str] = Field(default_factory=list)
    last_incident_ticket_id: str | None = None
    last_commands: list[RobotCommand] = Field(default_factory=list)
    last_perception_event_type: str | None = None
    last_perception_at: datetime | None = None
    latest_scene_summary: str | None = None
    people_count: int | None = None
    engagement_estimate: str | None = None
    perception_limited_awareness: bool = False
    engagement_state: EngagementState = EngagementState.UNKNOWN
    attention_target: str | None = None
    executive_state: InteractionExecutiveState = InteractionExecutiveState.IDLE
    social_runtime_mode: SocialRuntimeMode = SocialRuntimeMode.IDLE
    last_executive_decision_type: ExecutiveDecisionType | None = None
    shift_supervisor: ShiftSupervisorSnapshot = Field(default_factory=ShiftSupervisorSnapshot)
    participant_router: ParticipantRouterSnapshot = Field(default_factory=ParticipantRouterSnapshot)
    venue_operations: VenueOperationsSnapshot = Field(default_factory=VenueOperationsSnapshot)
    trace_count: int = 0
    last_trace_id: str | None = None
    updated_at: datetime = Field(default_factory=utc_now)


class ToolInvocationRecord(BaseModel):
    tool_name: str
    matched: bool = True
    answer_text: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    memory_updates: dict[str, str] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)


class LatencyBreakdownRecord(BaseModel):
    total_ms: float | None = None
    perception_ms: float | None = None
    executive_pre_ms: float | None = None
    tool_ms: float | None = None
    dialogue_ms: float | None = None
    executive_post_ms: float | None = None
    executive_ms: float | None = None
    publish_ms: float | None = None


class LiveTurnDiagnosticsRecord(BaseModel):
    source: str | None = None
    visual_query: bool = False
    camera_frame_attached: bool = False
    camera_refresh_skipped: bool = False
    spoken_reply_requested: bool = False
    stt_backend: str | None = None
    reasoning_backend: str | None = None
    tts_backend: str | None = None
    browser_speech_recognition_ms: float | None = None
    browser_camera_capture_ms: float | None = None
    server_ingress_ms: float | None = None
    stt_ms: float | None = None
    camera_refresh_ms: float | None = None
    live_voice_runtime_ms: float | None = None
    persistence_ms: float | None = None
    persistence_writes: int = 0
    reasoning_ms: float | None = None
    reasoning_backend_latency_ms: float | None = None
    tts_launch_ms: float | None = None
    tts_start_ms: float | None = None
    total_ms: float | None = None
    end_to_end_turn_ms: float | None = None
    fast_presence_acknowledged: bool = False
    fast_presence_ack_text: str | None = None
    fast_presence_tool_working: bool = False
    fast_presence_working_text: str | None = None
    text_model_warm: bool | None = None
    text_cold_start_retry_used: bool = False
    timeout_seconds: float | None = None
    timeout_triggered: bool = False
    stall_classification: str | None = None
    timeout_artifact_path: str | None = None
    notes: list[str] = Field(default_factory=list)


class GroundingSourceRecord(BaseModel):
    source_type: GroundingSourceType
    label: str
    source_ref: str | None = None
    fact_id: str | None = None
    claim_kind: SceneClaimKind | None = None
    freshness: FactFreshness | None = None
    confidence: float | None = None
    detail: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class InstructionLayerRecord(BaseModel):
    name: str
    source_ref: str
    dynamic: bool = False
    summary: str | None = None


class ToolSpecRecord(BaseModel):
    name: str
    version: str = "1.0"
    family: str
    capability_name: str = "system_health"
    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)
    permission_class: ToolPermissionClass = ToolPermissionClass.READ_ONLY
    latency_class: ToolLatencyClass = ToolLatencyClass.FAST
    effect_class: ToolEffectClass = ToolEffectClass.READ_ONLY
    confirmation_required: bool = False
    failure_modes: list[str] = Field(default_factory=list)
    checkpoint_policy: str = "none"
    observability_policy: list[str] = Field(default_factory=lambda: ["trace"])


class SkillActivationRecord(BaseModel):
    skill_name: str
    behavior_category: CompanionBehaviorCategory | None = None
    playbook_name: str | None = None
    playbook_version: str = "1.0"
    route_reason: str | None = None
    route_variant: str | None = None
    description: str | None = None
    reason: str
    purpose: str | None = None
    entry_conditions: list[str] = Field(default_factory=list)
    exit_conditions: list[str] = Field(default_factory=list)
    required_tools: list[str] = Field(default_factory=list)
    allowed_tools: list[str] = Field(default_factory=list)
    banned_tools: list[str] = Field(default_factory=list)
    forbidden_claims: list[str] = Field(default_factory=list)
    success_criteria: list[str] = Field(default_factory=list)
    body_style_hints: list[str] = Field(default_factory=list)
    memory_rules: list[str] = Field(default_factory=list)
    evaluation_rubric: list[str] = Field(default_factory=list)
    version: str = "1.0"


class ToolValidationRecord(BaseModel):
    schema_valid: bool = True
    output_valid: bool = True
    detail: str | None = None
    errors: list[str] = Field(default_factory=list)


class TypedToolCallRecord(BaseModel):
    tool_name: str
    requested_tool_name: str | None = None
    version: str = "1.0"
    family: str = "general"
    capability_name: str = "system_health"
    category: str
    input_payload: dict[str, Any] = Field(default_factory=dict)
    output_payload: dict[str, Any] = Field(default_factory=dict)
    summary: str | None = None
    success: bool = True
    result_status: ToolResultStatus = ToolResultStatus.OK
    confidence: float | None = None
    provenance: list[str] = Field(default_factory=list)
    fallback_used: bool = False
    permission_class: ToolPermissionClass = ToolPermissionClass.READ_ONLY
    latency_class: ToolLatencyClass = ToolLatencyClass.FAST
    effect_class: ToolEffectClass = ToolEffectClass.READ_ONLY
    confirmation_required: bool = False
    failure_mode: str | None = None
    error_code: str | None = None
    error_detail: str | None = None
    capability_state: ToolCapabilityState = ToolCapabilityState.AVAILABLE
    intentionally_skipped: bool = False
    skipped_reason: str | None = None
    checkpoint_policy: str = "none"
    observability_policy: list[str] = Field(default_factory=lambda: ["trace"])
    started_at: datetime = Field(default_factory=utc_now)
    finished_at: datetime | None = None
    latency_ms: float | None = None
    duration_ms: float | None = None
    validation: ToolValidationRecord = Field(default_factory=ToolValidationRecord)
    source_refs: list[str] = Field(default_factory=list)
    before_checkpoint_id: str | None = None
    after_checkpoint_id: str | None = None
    action_id: str | None = None
    connector_id: str | None = None
    risk_class: ActionRiskClass | None = None
    approval_state: ActionApprovalState | None = None
    action_status: ActionExecutionStatus | None = None
    request_hash: str | None = None
    idempotency_key: str | None = None
    workflow_run_id: str | None = None
    workflow_step_id: str | None = None
    notes: list[str] = Field(default_factory=list)


class SpecialistRoleDecisionRecord(BaseModel):
    role_name: str
    backend: str = "deterministic"
    summary: str
    notes: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ValidationOutcomeRecord(BaseModel):
    validator_name: str
    status: AgentValidationStatus = AgentValidationStatus.APPROVED
    detail: str | None = None
    downgraded: bool = False
    notes: list[str] = Field(default_factory=list)


class HookExecutionRecord(BaseModel):
    hook_name: AgentHookName
    canonical_phase: AgentHookName | None = None
    handler_name: str
    applied: bool = True
    action_type: str = "audit"
    gated: bool = False
    downgraded: bool = False
    run_id: str | None = None
    checkpoint_id: str | None = None
    detail: str | None = None
    notes: list[str] = Field(default_factory=list)


class CheckpointRecord(BaseModel):
    checkpoint_id: str = Field(default_factory=lambda: str(uuid4()))
    run_id: str
    session_id: str
    trace_id: str | None = None
    phase: RunPhase
    kind: CheckpointKind = CheckpointKind.TURN_BOUNDARY
    status: CheckpointStatus = CheckpointStatus.CREATED
    label: str
    reason: str | None = None
    tool_name: str | None = None
    active_skill: str | None = None
    active_subagent: str | None = None
    resumable: bool = False
    payload: dict[str, Any] = Field(default_factory=dict)
    result_payload: dict[str, Any] = Field(default_factory=dict)
    resumable_payload: dict[str, Any] = Field(default_factory=dict)
    recovery_notes: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    resumed_to_run_id: str | None = None
    replayed_to_run_id: str | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class CheckpointListResponse(BaseModel):
    items: list[CheckpointRecord] = Field(default_factory=list)


class RunRecord(BaseModel):
    run_id: str = Field(default_factory=lambda: str(uuid4()))
    session_id: str
    trace_id: str | None = None
    event_type: str
    status: RunStatus = RunStatus.RUNNING
    phase: RunPhase = RunPhase.INSTRUCTION_LOAD
    active_skill: str | None = None
    active_playbook: str | None = None
    active_playbook_variant: str | None = None
    active_subagent: str | None = None
    instruction_layer_names: list[str] = Field(default_factory=list)
    tool_names: list[str] = Field(default_factory=list)
    tool_chain: list[str] = Field(default_factory=list)
    checkpoint_ids: list[str] = Field(default_factory=list)
    intent: str | None = None
    reply_text: str | None = None
    command_types: list[CommandType] = Field(default_factory=list)
    fallback_reason: str | None = None
    fallback_classification: FallbackClassification | None = None
    unavailable_capabilities: list[str] = Field(default_factory=list)
    intentionally_skipped_capabilities: list[str] = Field(default_factory=list)
    failure_state: str | None = None
    provider_failure_active: bool = False
    replayed_from_run_id: str | None = None
    resumed_from_checkpoint_id: str | None = None
    paused_from_checkpoint_id: str | None = None
    source_event: dict[str, Any] = Field(default_factory=dict)
    recovery_notes: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    paused_at: datetime | None = None
    aborted_at: datetime | None = None
    completed_at: datetime | None = None


class RunListResponse(BaseModel):
    items: list[RunRecord] = Field(default_factory=list)


class RunExportArtifact(BaseModel):
    run: RunRecord
    checkpoints: list[CheckpointRecord] = Field(default_factory=list)
    typed_tool_calls: list[TypedToolCallRecord] = Field(default_factory=list)
    hook_records: list[HookExecutionRecord] = Field(default_factory=list)
    validation_outcomes: list[ValidationOutcomeRecord] = Field(default_factory=list)
    role_decisions: list[SpecialistRoleDecisionRecord] = Field(default_factory=list)
    recovery_metadata: dict[str, Any] = Field(default_factory=dict)
    exported_at: datetime = Field(default_factory=utc_now)
    artifact_path: str | None = None


class ShiftTransitionRecord(BaseModel):
    transition_id: str = Field(default_factory=lambda: str(uuid4()))
    session_id: str | None = None
    trace_id: str | None = None
    trigger: str
    from_state: ShiftOperatingState
    to_state: ShiftOperatingState
    reason_codes: list[str] = Field(default_factory=list)
    proactive_action: str | None = None
    note: str | None = None
    created_at: datetime = Field(default_factory=utc_now)


class ShiftTransitionListResponse(BaseModel):
    items: list[ShiftTransitionRecord] = Field(default_factory=list)


class ShiftMetricsSnapshot(BaseModel):
    shift_started_at: datetime | None = None
    shift_ended_at: datetime | None = None
    current_state: ShiftOperatingState | None = None
    active_session_count: int = 0
    queued_participant_count: int = 0
    open_incident_count: int = 0
    visitors_greeted: int = 0
    conversations_started: int = 0
    conversations_completed: int = 0
    escalations_created: int = 0
    escalations_resolved: int = 0
    response_count: int = 0
    average_response_latency_ms: float = 0.0
    time_spent_degraded_seconds: float = 0.0
    safe_idle_incident_count: int = 0
    unanswered_question_count: int = 0
    fallback_event_count: int = 0
    fallback_frequency_rate: float = 0.0
    perception_snapshot_count: int = 0
    perception_limited_awareness_count: int = 0
    perception_limited_awareness_rate: float = 0.0
    last_updated_at: datetime = Field(default_factory=utc_now)


class ReasoningTrace(BaseModel):
    engine: str
    intent: str
    fallback_used: bool = False
    run_id: str | None = None
    run_phase: RunPhase | None = None
    run_status: RunStatus | None = None
    instruction_layers: list[InstructionLayerRecord] = Field(default_factory=list)
    active_skill: SkillActivationRecord | None = None
    active_playbook: str | None = None
    active_playbook_variant: str | None = None
    active_subagent: str | None = None
    tool_invocations: list[ToolInvocationRecord] = Field(default_factory=list)
    typed_tool_calls: list[TypedToolCallRecord] = Field(default_factory=list)
    tool_chain: list[str] = Field(default_factory=list)
    memory_updates: dict[str, str] = Field(default_factory=dict)
    grounding_sources: list[GroundingSourceRecord] = Field(default_factory=list)
    latency_breakdown: LatencyBreakdownRecord = Field(default_factory=LatencyBreakdownRecord)
    hook_records: list[HookExecutionRecord] = Field(default_factory=list)
    role_decisions: list[SpecialistRoleDecisionRecord] = Field(default_factory=list)
    validation_outcomes: list[ValidationOutcomeRecord] = Field(default_factory=list)
    checkpoint_count: int = 0
    last_checkpoint_id: str | None = None
    failure_state: str | None = None
    fallback_reason: str | None = None
    fallback_classification: FallbackClassification | None = None
    unavailable_capabilities: list[str] = Field(default_factory=list)
    intentionally_skipped_capabilities: list[str] = Field(default_factory=list)
    recovery_status: str | None = None
    replayed_from_run_id: str | None = None
    resumed_from_checkpoint_id: str | None = None
    executive_state: InteractionExecutiveState | None = None
    social_runtime_mode: SocialRuntimeMode | None = None
    grounded_scene_references: list[GroundingSourceRecord] = Field(default_factory=list)
    uncertainty_admitted: bool = False
    stale_scene_suppressed: bool = False
    live_turn_diagnostics: LiveTurnDiagnosticsRecord | None = None
    executive_decisions: list["ExecutiveDecisionRecord"] = Field(default_factory=list)
    shift_supervisor: ShiftSupervisorSnapshot | None = None
    participant_router: ParticipantRouterSnapshot | None = None
    venue_operations: VenueOperationsSnapshot | None = None
    shift_transitions: list[ShiftTransitionRecord] = Field(default_factory=list)
    incident_ticket: IncidentTicketRecord | None = None
    incident_timeline: list[IncidentTimelineRecord] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class TraceRecord(BaseModel):
    trace_id: str = Field(default_factory=lambda: str(uuid4()))
    timestamp: datetime = Field(default_factory=utc_now)
    session_id: str
    user_id: str | None = None
    event: RobotEvent
    response: CommandBatch
    reasoning: ReasoningTrace
    latency_ms: float | None = None
    outcome: TraceOutcome = TraceOutcome.OK


class TraceSummary(BaseModel):
    trace_id: str
    session_id: str
    timestamp: datetime
    event_type: str
    intent: str
    engine: str
    fallback_used: bool = False
    run_id: str | None = None
    run_phase: RunPhase | None = None
    run_status: RunStatus | None = None
    active_skill: str | None = None
    active_playbook: str | None = None
    active_playbook_variant: str | None = None
    active_subagent: str | None = None
    reply_text: str | None = None
    command_types: list[CommandType] = Field(default_factory=list)
    tool_names: list[str] = Field(default_factory=list)
    validation_statuses: list[AgentValidationStatus] = Field(default_factory=list)
    checkpoint_count: int = 0
    last_checkpoint_id: str | None = None
    failure_state: str | None = None
    fallback_reason: str | None = None
    fallback_classification: FallbackClassification | None = None
    unavailable_capabilities: list[str] = Field(default_factory=list)
    intentionally_skipped_capabilities: list[str] = Field(default_factory=list)
    recovery_status: str | None = None
    executive_state: InteractionExecutiveState | None = None
    social_runtime_mode: SocialRuntimeMode | None = None
    grounded_reference_labels: list[str] = Field(default_factory=list)
    uncertainty_admitted: bool = False
    stale_scene_suppressed: bool = False
    executive_reason_codes: list[str] = Field(default_factory=list)
    shift_state: ShiftOperatingState | None = None
    shift_reason_codes: list[str] = Field(default_factory=list)
    incident_ticket_id: str | None = None
    incident_status: IncidentStatus | None = None
    latency_ms: float | None = None
    outcome: TraceOutcome = TraceOutcome.OK


class LogListResponse(BaseModel):
    items: list[TraceSummary] = Field(default_factory=list)


class TraceListResponse(BaseModel):
    items: list[TraceRecord] = Field(default_factory=list)


class ScenarioEventStep(BaseModel):
    event_type: str
    payload: dict[str, Any] = Field(default_factory=dict)


class ScenarioDefinition(BaseModel):
    name: str
    description: str
    steps: list[ScenarioEventStep] = Field(default_factory=list)


class ScenarioCatalogResponse(BaseModel):
    items: list[ScenarioDefinition] = Field(default_factory=list)


class ScenarioReplayRequest(BaseModel):
    session_id: str | None = None
    user_id: str | None = None
    operator_notes: list[str] = Field(default_factory=list)


class ScenarioReplayStepResult(BaseModel):
    event: RobotEvent
    response: CommandBatch


class ScenarioReplayResult(BaseModel):
    scenario_name: str
    description: str
    session_id: str
    steps: list[ScenarioReplayStepResult] = Field(default_factory=list)
    final_world_state: WorldState


class VoiceTurnRequest(BaseModel):
    session_id: str | None = None
    user_id: str | None = None
    input_text: str
    response_mode: ResponseMode | None = None
    source: str = "voice_stub"
    input_metadata: dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime | None = None


class VoiceTurnResult(BaseModel):
    session_id: str
    transcript_event: RobotEvent
    response: CommandBatch
    provider: str
    used_fallback: bool = False
    audio_available: bool = False
    live_turn_diagnostics: LiveTurnDiagnosticsRecord | None = None


class SpeechTranscriptRecord(BaseModel):
    session_id: str
    source: str = "typed_input"
    transcript_text: str
    event_type: str = "speech_transcript"
    capture_mode: str = "typed_input"
    transcription_backend: str = "pass_through"
    confidence: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)


class SpeechOutputResult(BaseModel):
    session_id: str | None = None
    backend: str = "stub"
    mode: VoiceRuntimeMode = VoiceRuntimeMode.STUB_DEMO
    audio_available: bool = False
    input_backend: str | None = None
    transcription_backend: str | None = None
    output_backend: str | None = None
    transcript_text: str | None = None
    can_listen: bool = False
    can_cancel: bool = True
    error_code: str | None = None
    status: SpeechOutputStatus = SpeechOutputStatus.IDLE
    spoken_text: str | None = None
    message: str | None = None
    live_turn_diagnostics: LiveTurnDiagnosticsRecord | None = None
    updated_at: datetime = Field(default_factory=utc_now)


__all__ = [
    "AgentHookName",
    "AgentValidationStatus",
    "CheckpointKind",
    "CheckpointListResponse",
    "CheckpointRecord",
    "CheckpointStatus",
    "CompanionNoteListResponse",
    "CompanionNoteRecord",
    "CompanionRelationshipProfile",
    "ConversationTurn",
    "EpisodicMemoryListResponse",
    "EpisodicMemoryRecord",
    "FallbackClassification",
    "GroundingSourceRecord",
    "GroundingSourceType",
    "HookExecutionRecord",
    "IncidentAcknowledgeRequest",
    "IncidentAssignRequest",
    "IncidentListResponse",
    "IncidentListScope",
    "IncidentNoteRecord",
    "IncidentNoteRequest",
    "IncidentReasonCategory",
    "IncidentResolveRequest",
    "IncidentResolutionOutcome",
    "IncidentStaffSuggestion",
    "IncidentStatus",
    "IncidentTicketRecord",
    "IncidentTimelineEventType",
    "IncidentTimelineRecord",
    "IncidentTimelineResponse",
    "IncidentUrgency",
    "InstructionLayerRecord",
    "LatencyBreakdownRecord",
    "LiveTurnDiagnosticsRecord",
    "LogListResponse",
    "MemoryPromotionRecord",
    "MemoryActionListResponse",
    "MemoryActionRecord",
    "MemoryDecisionOutcome",
    "MemoryPolicyScoreRecord",
    "MemoryRetrievalCandidateRecord",
    "MemoryRetrievalListResponse",
    "MemoryRetrievalRecord",
    "MemoryReviewListResponse",
    "MemoryReviewDebtSummary",
    "MemoryReviewRecord",
    "MemoryReviewRequest",
    "OperatorNote",
    "OperatorNoteRequest",
    "ParticipantRouterSnapshot",
    "ParticipantSessionBinding",
    "QueuedParticipantRecord",
    "ReasoningTrace",
    "ReminderListResponse",
    "ReminderRecord",
    "ReminderStatus",
    "RelationshipMemoryListResponse",
    "RelationshipMemoryRecord",
    "RelationshipPromiseRecord",
    "RelationshipPromiseStatus",
    "RelationshipThreadKind",
    "RelationshipThreadRecord",
    "RelationshipThreadStatus",
    "RelationshipTopicRecord",
    "ReviewDebtState",
    "ResponseMode",
    "RunExportArtifact",
    "RunListResponse",
    "RunPhase",
    "RunRecord",
    "RunStatus",
    "ScenarioCatalogResponse",
    "ScenarioDefinition",
    "ScenarioEventStep",
    "ScenarioReplayRequest",
    "ScenarioReplayResult",
    "ScenarioReplayStepResult",
    "SceneCacheRecord",
    "ProceduralMemoryListResponse",
    "ProceduralMemoryRecord",
    "SemanticMemoryListResponse",
    "SemanticMemoryRecord",
    "SessionCreateRequest",
    "SessionDigestListResponse",
    "SessionDigestRecord",
    "SessionListResponse",
    "SessionRecord",
    "SessionResponseModeRequest",
    "SessionRoutingStatus",
    "SessionStatus",
    "SessionSummary",
    "ShiftMetricsSnapshot",
    "ShiftOperatingState",
    "ShiftSupervisorSnapshot",
    "ShiftTimerSnapshot",
    "ShiftTransitionListResponse",
    "ShiftTransitionRecord",
    "SkillActivationRecord",
    "SpecialistRoleDecisionRecord",
    "SpeechOutputResult",
    "SpeechOutputStatus",
    "SpeechTranscriptRecord",
    "ToolEffectClass",
    "ToolCapabilityState",
    "ToolLatencyClass",
    "ToolPermissionClass",
    "ToolResultStatus",
    "ToolSpecRecord",
    "ToolValidationRecord",
    "ToolInvocationRecord",
    "TypedToolCallRecord",
    "TraceListResponse",
    "TraceOutcome",
    "TraceRecord",
    "TraceSummary",
    "UserMemoryRecord",
    "ValidationOutcomeRecord",
    "VenueAnnouncementPolicy",
    "VenueEscalationKeywordRule",
    "VenueEscalationPolicy",
    "VenueFallbackInstruction",
    "VenueFallbackScenario",
    "VenueOperationsSnapshot",
    "VenueProactiveGreetingPolicy",
    "VenueScheduleWindow",
    "VoiceRuntimeMode",
    "VoiceTurnRequest",
    "VoiceTurnResult",
    "WorldState",
]
