from __future__ import annotations

from enum import Enum

from ._common import (
    BaseModel,
    BodyDriverMode,
    CharacterProjectionProfile,
    CompanionAudioMode,
    CompanionContextMode,
    CompanionPresenceState,
    CompanionTriggerDecision,
    CompanionVoiceLoopState,
    DesktopDeviceKind,
    DemoRunStatus,
    EdgeAdapterState,
    EdgeTransportMode,
    EnvironmentState,
    FallbackClassification,
    FactFreshness,
    Field,
    InitiativeDecision,
    InitiativeStage,
    model_validator,
    PerceptionProviderMode,
    PerceptionTier,
    ResponseMode,
    RobotMode,
    RuntimeBackendAvailability,
    RuntimeBackendKind,
    SocialRuntimeMode,
    TransportState,
    VoiceRuntimeMode,
    datetime,
    utc_now,
)
from .action import (
    ActionPlaneStatus,
    BrowserRequestedAction,
    BrowserRuntimeStatusRecord,
    BrowserTargetHintRecord,
)
from .body import BodyState, CharacterPresenceShellState, CharacterSemanticIntent
from .brain import (
    CheckpointListResponse,
    GroundingSourceRecord,
    HookExecutionRecord,
    IncidentListResponse,
    IncidentTicketRecord,
    IncidentTimelineRecord,
    IncidentTimelineResponse,
    InstructionLayerRecord,
    LatencyBreakdownRecord,
    MemoryPromotionRecord,
    MemoryRetrievalListResponse,
    MemoryReviewDebtSummary,
    LiveTurnDiagnosticsRecord,
    LogListResponse,
    OperatorNoteRequest,
    ParticipantRouterSnapshot,
    RunExportArtifact,
    RunListResponse,
    RunPhase,
    RunRecord,
    RunStatus,
    SessionRecord,
    SceneCacheRecord,
    SessionSummary,
    SkillActivationRecord,
    SpecialistRoleDecisionRecord,
    ShiftMetricsSnapshot,
    ShiftOperatingState,
    ShiftSupervisorSnapshot,
    ShiftTransitionListResponse,
    SpeechOutputResult,
    SpeechOutputStatus,
    TypedToolCallRecord,
    ValidationOutcomeRecord,
    VenueOperationsSnapshot,
    VoiceTurnRequest,
    WorldState,
)
from .demo import (
    DemoRunListResponse,
    DemoSceneScorecard,
    FinalActionRecord,
    LocalCompanionReadinessRecord,
    ScorecardCriterion,
    ShiftReportListResponse,
)
from .edge import (
    CommandAck,
    CommandBatch,
    CommandHistoryResponse,
    HeartbeatStatus,
    RobotEvent,
    TelemetryLogResponse,
    TelemetrySnapshot,
)
from .perception import (
    EmbodiedWorldModel,
    EngagementTimelinePoint,
    ExecutiveDecisionListResponse,
    ExecutiveDecisionRecord,
    PerceptionAnnotationInput,
    PerceptionFixtureCatalogResponse,
    PerceptionHistoryResponse,
    PerceptionPublishedResult,
    PerceptionReplayRequest,
    PerceptionReplayResult,
    PerceptionSnapshotRecord,
    PerceptionSnapshotSubmitRequest,
    PerceptionSubmissionResult,
    PerceptionSourceFrame,
    SceneObserverEventListResponse,
    WorldModelTransitionListResponse,
    WorldModelTransitionRecord,
)


class OperatorAuthLoginRequest(BaseModel):
    token: str


class OperatorAuthStatus(BaseModel):
    enabled: bool = True
    authenticated: bool = False
    cookie_name: str = "blink_operator_auth"
    header_name: str = "x-blink-operator-token"
    auth_mode: str = "configured_static_token"
    token_source: str | None = None
    runtime_file: str | None = None
    session_ttl_seconds: int | None = None
    bootstrap_ttl_seconds: int | None = None
    warning: str | None = None


class ApplianceIssue(BaseModel):
    category: str
    severity: str = "warning"
    message: str
    blocking: bool = False


class ApplianceDeviceOption(BaseModel):
    device_id: str
    label: str
    kind: DesktopDeviceKind
    selected: bool = False
    detail: str | None = None


class ApplianceDeviceCatalog(BaseModel):
    device_preset: str = "internal_macbook"
    microphones: list[ApplianceDeviceOption] = Field(default_factory=list)
    cameras: list[ApplianceDeviceOption] = Field(default_factory=list)
    selected_microphone_label: str | None = None
    selected_camera_label: str | None = None
    selected_speaker_label: str | None = "system_default"
    speaker_selection_supported: bool = False
    speaker_note: str | None = None


class StartupDeviceSelection(BaseModel):
    configured_label: str | None = None
    selected_label: str | None = None
    selection_note: str | None = None
    fallback_active: bool = False


class ApplianceStartupSummary(BaseModel):
    runtime_mode: RobotMode | None = None
    model_profile: str | None = None
    backend_profile: str | None = None
    voice_profile: str | None = None
    device_preset: str = "auto"
    config_source: str = "repo_defaults"
    provider_status: str | None = None
    provider_detail: str | None = None
    fallback_active: bool = False
    fallback_notes: list[str] = Field(default_factory=list)
    microphone: StartupDeviceSelection = Field(default_factory=StartupDeviceSelection)
    camera: StartupDeviceSelection = Field(default_factory=StartupDeviceSelection)
    speaker: StartupDeviceSelection = Field(default_factory=StartupDeviceSelection)


class ApplianceStatus(BaseModel):
    appliance_mode: bool = False
    setup_complete: bool = False
    setup_issues: list[ApplianceIssue] = Field(default_factory=list)
    action_plane_ready: bool = True
    action_plane_issues: list[str] = Field(default_factory=list)
    browser_runtime_state: str | None = None
    pending_action_count: int = 0
    waiting_workflow_count: int = 0
    review_required_count: int = 0
    next_operator_step: str | None = None
    auth_mode: str = "configured_static_token"
    config_source: str = "repo_defaults"
    device_preset: str = "auto"
    configured_microphone_label: str | None = None
    selected_microphone_label: str | None = None
    configured_camera_label: str | None = None
    selected_camera_label: str | None = None
    configured_speaker_label: str | None = "system_default"
    selected_speaker_label: str | None = "system_default"
    speaker_selection_supported: bool = False
    profile_path: str | None = None
    profile_exists: bool = False
    model_profile: str | None = None
    backend_profile: str | None = None
    voice_profile: str | None = None
    runtime_mode: RobotMode | None = None
    ollama_reachable: bool | None = None
    required_models: list[str] = Field(default_factory=list)
    missing_models: list[str] = Field(default_factory=list)
    export_available: bool = True
    export_dir: str | None = None
    startup_summary: ApplianceStartupSummary | None = None
    local_companion_readiness: LocalCompanionReadinessRecord | None = None


class ApplianceProfileRequest(BaseModel):
    setup_complete: bool = True
    device_preset: str = "internal_macbook"
    microphone_device: str = "default"
    camera_device: str = "default"
    speaker_device: str = "system_default"


class ApplianceBootstrapResponse(BaseModel):
    ok: bool = True
    bootstrap_url: str
    expires_at: datetime


class OperatorVoiceTurnRequest(VoiceTurnRequest):
    voice_mode: VoiceRuntimeMode = VoiceRuntimeMode.STUB_DEMO
    speak_reply: bool = True
    camera_image_data_url: str | None = None
    camera_source_frame: PerceptionSourceFrame | None = None
    camera_provider_mode: PerceptionProviderMode | None = None


class BrowserAudioTurnRequest(BaseModel):
    session_id: str | None = None
    user_id: str | None = None
    response_mode: ResponseMode | None = None
    voice_mode: VoiceRuntimeMode = VoiceRuntimeMode.BROWSER_LIVE_MACOS_SAY
    speak_reply: bool = True
    source: str = "browser_audio_capture"
    audio_data_url: str
    mime_type: str | None = None
    camera_image_data_url: str | None = None
    camera_source_frame: PerceptionSourceFrame | None = None
    camera_provider_mode: PerceptionProviderMode | None = None
    input_metadata: dict[str, object] = Field(default_factory=dict)


class BrowserAudioTurnResult(BaseModel):
    interaction: OperatorInteractionResult
    transcript_text: str | None = None
    transcription_backend: str | None = None
    browser_device_label: str | None = None
    audio_mime_type: str | None = None


class BrowserActionTaskRequest(BaseModel):
    session_id: str | None = None
    query: str = ""
    target_url: str | None = None
    requested_action: BrowserRequestedAction | None = None
    target_hint: BrowserTargetHintRecord | None = None
    text_input: str | None = None


class LiveVoiceStateUpdateRequest(BaseModel):
    session_id: str | None = None
    voice_mode: VoiceRuntimeMode = VoiceRuntimeMode.STUB_DEMO
    status: SpeechOutputStatus
    message: str | None = None
    transcript_text: str | None = None
    source: str = "operator_console"
    input_backend: str | None = None
    transcription_backend: str | None = None
    output_backend: str | None = None
    confidence: float | None = None
    metadata: dict[str, object] = Field(default_factory=dict)


class VoiceCancelResult(BaseModel):
    ok: bool = True
    session_id: str | None = None
    state: SpeechOutputResult


class BodyConnectRequest(BaseModel):
    port: str | None = None
    baud: int | None = None
    timeout_seconds: float | None = None


class BodyIdsRequest(BaseModel):
    ids: list[int] = Field(default_factory=list)


class BodyArmRequest(BaseModel):
    ttl_seconds: float = 60.0
    author: str | None = None


class BodySemanticSmokeRequest(BaseModel):
    action: str = "look_left"
    intensity: float = 1.0
    repeat_count: int = 1
    note: str | None = None
    allow_bench_actions: bool = False


class PrimitiveSequenceStep(BaseModel):
    action: str
    intensity: float | None = None
    note: str | None = None

    @model_validator(mode="after")
    def validate_shape(self) -> "PrimitiveSequenceStep":
        if self.intensity is not None and self.intensity < 0:
            raise ValueError("primitive_sequence_step_intensity_must_be_non_negative")
        return self


_STRUCTURAL_STAGE_PREFIXES = (
    "head_turn_",
    "head_tilt_",
    "head_pitch_up_",
    "head_pitch_down_",
)
_EXPRESSIVE_STAGE_PREFIXES = (
    "eyes_",
    "blink_both_",
    "close_both_eyes_",
    "lids_",
    "wink_",
    "brows_",
    "brow_",
)
_EXPRESSIVE_STAGE_EXACT = {
    "double_blink_slow",
    "double_blink_fast",
}
_EXPRESSIVE_MOTIF_RELEASE_GROUPS = {"eye_yaw", "eye_pitch", "lids", "brows"}


def _is_structural_stage_action(action: str | None) -> bool:
    normalized = str(action or "").strip()
    return any(normalized.startswith(prefix) for prefix in _STRUCTURAL_STAGE_PREFIXES)


def _is_expressive_stage_action(action: str | None) -> bool:
    normalized = str(action or "").strip()
    return normalized in _EXPRESSIVE_STAGE_EXACT or any(
        normalized.startswith(prefix) for prefix in _EXPRESSIVE_STAGE_PREFIXES
    )


def _is_expressive_motif_action(action: str | None) -> bool:
    return _is_expressive_stage_action(action)


class StagedSequenceAccent(BaseModel):
    action: str
    intensity: float | None = None
    note: str | None = None

    @model_validator(mode="after")
    def validate_shape(self) -> "StagedSequenceAccent":
        if self.intensity is not None and self.intensity < 0:
            raise ValueError("staged_sequence_accent_intensity_must_be_non_negative")
        if not _is_expressive_stage_action(self.action):
            raise ValueError(f"staged_sequence_expressive_action_not_allowed:{self.action}")
        return self


class StagedSequenceStage(BaseModel):
    stage_kind: str
    action: str | None = None
    intensity: float | None = None
    move_ms: int | None = None
    hold_ms: int | None = None
    settle_ms: int | None = None
    accents: list[StagedSequenceAccent] = Field(default_factory=list)
    note: str | None = None

    @model_validator(mode="after")
    def validate_shape(self) -> "StagedSequenceStage":
        if self.intensity is not None and self.intensity < 0:
            raise ValueError("staged_sequence_stage_intensity_must_be_non_negative")
        for field_name in ("move_ms", "hold_ms", "settle_ms"):
            value = getattr(self, field_name)
            if value is not None and value < 0:
                raise ValueError(f"staged_sequence_stage_{field_name}_must_be_non_negative")
        normalized_kind = str(self.stage_kind or "").strip()
        if normalized_kind not in {"structural", "expressive", "return"}:
            raise ValueError(f"staged_sequence_stage_kind_not_supported:{self.stage_kind}")
        if normalized_kind == "structural":
            if not self.action:
                raise ValueError("staged_sequence_structural_stage_requires_action")
            if self.accents:
                raise ValueError("staged_sequence_structural_stage_disallows_accents")
            if not _is_structural_stage_action(self.action):
                raise ValueError(f"staged_sequence_structural_action_not_allowed:{self.action}")
        elif normalized_kind == "expressive":
            if self.action is not None:
                raise ValueError("staged_sequence_expressive_stage_disallows_action")
            if not self.accents:
                raise ValueError("staged_sequence_expressive_stage_requires_accents")
            if len(self.accents) > 5:
                raise ValueError("staged_sequence_expressive_stage_too_many_accents")
        else:
            if self.action is not None:
                raise ValueError("staged_sequence_return_stage_disallows_action")
            if self.accents:
                raise ValueError("staged_sequence_return_stage_disallows_accents")
        return self


class BodyPrimitiveSequenceRequest(BaseModel):
    steps: list[PrimitiveSequenceStep] = Field(default_factory=list)
    sequence_name: str | None = None
    note: str | None = None

    @model_validator(mode="after")
    def validate_shape(self) -> "BodyPrimitiveSequenceRequest":
        if not self.steps:
            raise ValueError("body_primitive_sequence_requires_steps")
        return self


class BodyStagedSequenceRequest(BaseModel):
    stages: list[StagedSequenceStage] = Field(default_factory=list)
    sequence_name: str | None = None
    note: str | None = None

    @model_validator(mode="after")
    def validate_shape(self) -> "BodyStagedSequenceRequest":
        if len(self.stages) != 3:
            raise ValueError("body_staged_sequence_requires_three_stages")
        stage_kinds = [stage.stage_kind for stage in self.stages]
        if stage_kinds != ["structural", "expressive", "return"]:
            raise ValueError("body_staged_sequence_requires_structural_expressive_return")
        return self


class ExpressiveSequenceStep(BaseModel):
    step_kind: str
    action: str | None = None
    intensity: float | None = None
    release_groups: list[str] = Field(default_factory=list)
    move_ms: int | None = None
    hold_ms: int | None = None
    note: str | None = None

    @model_validator(mode="after")
    def validate_shape(self) -> "ExpressiveSequenceStep":
        if self.intensity is not None and self.intensity < 0:
            raise ValueError("expressive_sequence_step_intensity_must_be_non_negative")
        for field_name in ("move_ms", "hold_ms"):
            value = getattr(self, field_name)
            if value is not None and value < 0:
                raise ValueError(f"expressive_sequence_step_{field_name}_must_be_non_negative")
        normalized_kind = str(self.step_kind or "").strip()
        if normalized_kind not in {
            "structural_set",
            "expressive_set",
            "expressive_release",
            "hold",
            "return_to_neutral",
        }:
            raise ValueError(f"expressive_sequence_step_kind_not_supported:{self.step_kind}")
        if normalized_kind == "structural_set":
            if not self.action:
                raise ValueError("expressive_sequence_structural_step_requires_action")
            if not _is_structural_stage_action(self.action):
                raise ValueError(f"expressive_sequence_structural_action_not_allowed:{self.action}")
            if self.release_groups:
                raise ValueError("expressive_sequence_structural_step_disallows_release_groups")
        elif normalized_kind == "expressive_set":
            if not self.action:
                raise ValueError("expressive_sequence_expressive_step_requires_action")
            if not _is_expressive_motif_action(self.action):
                raise ValueError(f"expressive_sequence_expressive_action_not_allowed:{self.action}")
            if self.release_groups:
                raise ValueError("expressive_sequence_expressive_step_disallows_release_groups")
        elif normalized_kind == "expressive_release":
            if self.action is not None:
                raise ValueError("expressive_sequence_release_step_disallows_action")
            if not self.release_groups:
                raise ValueError("expressive_sequence_release_step_requires_groups")
            invalid_groups = [
                item
                for item in self.release_groups
                if item not in _EXPRESSIVE_MOTIF_RELEASE_GROUPS
            ]
            if invalid_groups:
                raise ValueError(
                    f"expressive_sequence_release_group_not_allowed:{','.join(invalid_groups)}"
                )
        elif normalized_kind == "hold":
            if self.action is not None:
                raise ValueError("expressive_sequence_hold_step_disallows_action")
            if self.release_groups:
                raise ValueError("expressive_sequence_hold_step_disallows_release_groups")
            if self.hold_ms is None:
                raise ValueError("expressive_sequence_hold_step_requires_hold_ms")
        else:
            if self.action is not None:
                raise ValueError("expressive_sequence_return_step_disallows_action")
            if self.release_groups:
                raise ValueError("expressive_sequence_return_step_disallows_release_groups")
        return self


class ExpressiveMotifReference(BaseModel):
    motif_name: str

    @model_validator(mode="after")
    def validate_shape(self) -> "ExpressiveMotifReference":
        if not self.motif_name.strip():
            raise ValueError("expressive_motif_reference_requires_name")
        self.motif_name = self.motif_name.strip()
        return self


class BodyExpressiveSequenceRequest(BaseModel):
    motif: ExpressiveMotifReference | None = None
    steps: list[ExpressiveSequenceStep] = Field(default_factory=list)
    sequence_name: str | None = None
    note: str | None = None

    @model_validator(mode="after")
    def validate_shape(self) -> "BodyExpressiveSequenceRequest":
        if self.motif is None and not self.steps:
            raise ValueError("body_expressive_motif_requires_motif_or_steps")
        if self.motif is not None and self.steps:
            raise ValueError("body_expressive_motif_disallows_motif_and_steps_together")
        if self.steps:
            if self.steps[0].step_kind != "structural_set":
                raise ValueError("body_expressive_motif_requires_structural_open")
            if self.steps[-1].step_kind != "return_to_neutral":
                raise ValueError("body_expressive_motif_requires_return_close")
        return self


class BodyServoLabReferenceMode(str, Enum):
    ABSOLUTE_RAW = "absolute_raw"
    NEUTRAL_DELTA = "neutral_delta"
    CURRENT_DELTA = "current_delta"


class BodyServoLabReadbackRequest(BaseModel):
    joint_name: str | None = None
    include_health: bool = True


class BodyServoLabMoveRequest(BaseModel):
    joint_name: str
    reference_mode: BodyServoLabReferenceMode = BodyServoLabReferenceMode.CURRENT_DELTA
    target_raw: int | None = None
    delta_counts: int | None = None
    lab_min: int | None = None
    lab_max: int | None = None
    duration_ms: int = Field(default=600, ge=0, le=10_000)
    speed_override: int | None = Field(default=None, ge=0, le=65_535)
    acceleration_override: int | None = Field(default=None, ge=0, le=150)
    note: str | None = None


class BodyServoLabSweepRequest(BaseModel):
    joint_name: str
    lab_min: int | None = None
    lab_max: int | None = None
    cycles: int = Field(default=1, ge=1, le=16)
    duration_ms: int = Field(default=600, ge=0, le=10_000)
    dwell_ms: int = Field(default=250, ge=0, le=10_000)
    speed_override: int | None = Field(default=None, ge=0, le=65_535)
    acceleration_override: int | None = Field(default=None, ge=0, le=150)
    return_to_neutral: bool = True
    note: str | None = None


class BodyServoLabSaveCalibrationRequest(BaseModel):
    joint_name: str
    save_current_as_neutral: bool = False
    raw_min: int | None = None
    raw_max: int | None = None
    confirm_mirrored: bool | None = None
    note: str | None = None


class BodyTeacherReviewRequest(BaseModel):
    action: str
    review: str
    note: str | None = None
    proposed_tuning_delta: dict[str, object] = Field(default_factory=dict)
    apply_tuning: bool = False


class BodyActionResult(BaseModel):
    ok: bool = True
    status: str = "ok"
    detail: str | None = None
    body_state: BodyState | None = None
    transport_summary: dict[str, object] = Field(default_factory=dict)
    report_path: str | None = None
    motion_report_path: str | None = None
    payload: dict[str, object] = Field(default_factory=dict)


class ShiftAutonomyTickRequest(BaseModel):
    session_id: str | None = None
    timestamp: "datetime | None" = None
    source: str = "shift_supervisor"
    payload: dict[str, object] = Field(default_factory=dict)


class ShiftOverrideRequest(BaseModel):
    state: ShiftOperatingState | None = None
    reason: str = "operator_override"
    clear: bool = False


class OperatorInteractionResult(BaseModel):
    session_id: str
    interaction_type: str
    event: RobotEvent
    response: CommandBatch
    command_acks: list[CommandAck] = Field(default_factory=list)
    telemetry: TelemetrySnapshot
    heartbeat: HeartbeatStatus
    success: bool = True
    outcome: str = "ok"
    latency_ms: float | None = None
    voice_output: SpeechOutputResult | None = None
    live_turn_diagnostics: LiveTurnDiagnosticsRecord | None = None
    step_label: str | None = None
    latency_breakdown: LatencyBreakdownRecord = Field(default_factory=LatencyBreakdownRecord)
    grounding_sources: list[GroundingSourceRecord] = Field(default_factory=list)
    perception_snapshot: PerceptionSnapshotRecord | None = None
    shift_supervisor: ShiftSupervisorSnapshot | None = None
    participant_router: "ParticipantRouterSnapshot | None" = None
    venue_operations: VenueOperationsSnapshot | None = None
    incident_ticket: IncidentTicketRecord | None = None
    incident_timeline: list[IncidentTimelineRecord] = Field(default_factory=list)


class DesktopDeviceHealth(BaseModel):
    device_id: str
    kind: DesktopDeviceKind
    state: EdgeAdapterState = EdgeAdapterState.UNAVAILABLE
    backend: str
    available: bool = False
    required: bool = False
    detail: str | None = None
    configured_label: str | None = None
    selected_label: str | None = None
    reason_code: str = "ok"
    selection_note: str | None = None
    fallback_active: bool = False
    last_checked_at: datetime = Field(default_factory=utc_now)


class RuntimeBackendStatus(BaseModel):
    kind: RuntimeBackendKind
    backend_id: str
    status: RuntimeBackendAvailability = RuntimeBackendAvailability.UNAVAILABLE
    provider: str
    model: str | None = None
    local: bool = False
    cloud: bool = False
    requested_backend_id: str | None = None
    fallback_from: str | None = None
    detail: str | None = None
    requested_model: str | None = None
    active_model: str | None = None
    reachable: bool | None = None
    installed: bool | None = None
    warm: bool | None = None
    keep_alive: str | None = None
    last_success_latency_ms: float | None = None
    last_failure_reason: str | None = None
    last_failure_at: datetime | None = None
    last_timeout_seconds: float | None = None
    cold_start_retry_used: bool = False
    last_checked_at: datetime = Field(default_factory=utc_now)


class FreshnessWindowStatus(BaseModel):
    status: str = "idle"
    freshness: FactFreshness = FactFreshness.UNKNOWN
    observed_at: datetime | None = None
    age_seconds: float | None = None
    max_age_seconds: float | None = None
    expires_in_seconds: float | None = None
    limited_awareness: bool = False
    source_kind: str | None = None
    summary: str | None = None
    tier: PerceptionTier | None = None
    trigger_reason: str | None = None


class PerceptionFreshnessStatus(BaseModel):
    status: str = "idle"
    freshness: FactFreshness = FactFreshness.UNKNOWN
    observed_at: datetime | None = None
    captured_at: datetime | None = None
    age_seconds: float | None = None
    max_age_seconds: float | None = None
    expires_in_seconds: float | None = None
    limited_awareness: bool = False
    source_kind: str | None = None
    summary: str | None = None
    tier: PerceptionTier | None = None
    trigger_reason: str | None = None
    uncertainty_markers: list[str] = Field(default_factory=list)
    device_awareness_constraints: list[str] = Field(default_factory=list)
    watcher: FreshnessWindowStatus = Field(default_factory=FreshnessWindowStatus)
    semantic: FreshnessWindowStatus = Field(default_factory=FreshnessWindowStatus)


class RelationshipContinuityStatus(BaseModel):
    known_user: bool = False
    returning_user: bool = False
    display_name: str | None = None
    familiarity: float | None = None
    recurring_topics: list[str] = Field(default_factory=list)
    greeting_preference: str | None = None
    planning_style: str | None = None
    tone_preferences: list[str] = Field(default_factory=list)
    interaction_boundaries: list[str] = Field(default_factory=list)
    continuity_preferences: list[str] = Field(default_factory=list)
    open_practical_threads: list[str] = Field(default_factory=list)
    open_emotional_threads: list[str] = Field(default_factory=list)
    promise_count: int = 0
    open_follow_ups: list[str] = Field(default_factory=list)


class MemoryStatus(BaseModel):
    status: str = "idle"
    session_id: str | None = None
    user_id: str | None = None
    transcript_turn_count: int = 0
    conversation_summary: str | None = None
    session_memory_keys: list[str] = Field(default_factory=list)
    operator_note_count: int = 0
    episodic_memory_count: int = 0
    semantic_memory_count: int = 0
    profile_memory_available: bool = False
    profile_fact_count: int = 0
    profile_preference_count: int = 0
    profile_interest_count: int = 0
    open_reminder_count: int = 0
    note_count: int = 0
    session_digest_count: int = 0
    relationship_continuity: RelationshipContinuityStatus = Field(default_factory=RelationshipContinuityStatus)
    last_memory_at: datetime | None = None
    review_debt_summary: MemoryReviewDebtSummary = Field(default_factory=MemoryReviewDebtSummary)


class FallbackState(BaseModel):
    active: bool = False
    safe_idle_active: bool = False
    latest_trace_outcome: str | None = None
    latest_trace_fallback_used: bool = False
    classification: FallbackClassification | None = None
    fallback_backends: list[str] = Field(default_factory=list)
    degraded_backends: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class CompanionVoiceLoopStatus(BaseModel):
    state: CompanionVoiceLoopState = CompanionVoiceLoopState.IDLE
    session_id: str | None = None
    armed_until: datetime | None = None
    last_transition_at: datetime = Field(default_factory=utc_now)
    last_transcript_at: datetime | None = None
    last_reply_at: datetime | None = None
    last_interruption_at: datetime | None = None
    degraded_reason: str | None = None
    transcript_latency_ms: float | None = None
    first_audio_latency_ms: float | None = None
    interruption_latency_ms: float | None = None
    interruption_count: int = 0
    partial_transcript_preview: str | None = None
    audio_backend: str | None = None


class CompanionPresenceStatus(BaseModel):
    state: CompanionPresenceState = CompanionPresenceState.IDLE
    session_id: str | None = None
    message: str | None = None
    last_transition_at: datetime = Field(default_factory=utc_now)
    last_user_text_preview: str | None = None
    last_reply_preview: str | None = None
    last_acknowledgement_text: str | None = None
    slow_path_active: bool = False
    slow_path_started_at: datetime | None = None
    last_reply_at: datetime | None = None
    acknowledgement_count: int = 0
    interruption_count: int = 0
    barge_in_count: int = 0
    degraded_reason: str | None = None


class LocalModelResidencyRecord(BaseModel):
    kind: RuntimeBackendKind
    backend_id: str
    model: str | None = None
    keep_warm: bool = False
    resident: bool = False
    status: str = "inactive"
    last_used_at: datetime | None = None
    idle_timeout_seconds: float | None = None
    unload_requested_at: datetime | None = None
    detail: str | None = None


class SceneObserverStatus(BaseModel):
    enabled: bool = False
    state: str = "disabled"
    backend: str = "frame_diff_fallback"
    supports_mediapipe: bool = False
    last_observed_at: datetime | None = None
    last_change_score: float | None = None
    last_person_state: str | None = None
    last_people_count_estimate: int | None = None
    last_attention_state: str | None = None
    last_attention_toward_device_score: float | None = None
    last_environment_state: EnvironmentState = EnvironmentState.UNKNOWN
    last_refresh_reason: str | None = None
    last_semantic_refresh_at: datetime | None = None
    semantic_refresh_count: int = 0
    buffer_size: int = 0
    degraded_reason: str | None = None


class TriggerEngineStatus(BaseModel):
    enabled: bool = False
    last_decision: CompanionTriggerDecision = CompanionTriggerDecision.WAIT
    last_reason: str | None = None
    last_evaluated_at: datetime | None = None
    last_action_at: datetime | None = None
    proactive_eligible: bool = False
    suppressed_reason: str | None = None
    cooldown_until: datetime | None = None
    trigger_count: int = 0
    suppression_count: int = 0
    fallback_active: bool = False


class InitiativeScorecardRecord(BaseModel):
    relevance: float = Field(default=0.0, ge=0.0, le=1.0)
    interruption_cost: float = Field(default=0.0, ge=0.0, le=1.0)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    risk: float = Field(default=0.0, ge=0.0, le=1.0)
    recency: float = Field(default=0.0, ge=0.0, le=1.0)
    relationship_appropriateness: float = Field(default=0.0, ge=0.0, le=1.0)
    total: float = Field(default=0.0, ge=0.0, le=1.0)


class InitiativeGroundingRecord(BaseModel):
    terminal_source: str | None = None
    terminal_idle_seconds: float | None = None
    person_present: bool = False
    semantic_scene_fresh: bool = False
    browser_context_available: bool = False
    browser_current_url: str | None = None
    due_reminder_count: int = 0
    follow_up_count: int = 0
    relationship_boundary_active: bool = False


class InitiativeStatus(BaseModel):
    enabled: bool = False
    current_stage: InitiativeStage = InitiativeStage.MONITOR
    last_decision: InitiativeDecision = InitiativeDecision.IGNORE
    last_candidate_kind: str | None = None
    last_reason: str | None = None
    last_reason_codes: list[str] = Field(default_factory=list)
    last_evaluated_at: datetime | None = None
    last_action_at: datetime | None = None
    cooldown_until: datetime | None = None
    suppressed: bool = False
    suppression_reason: str | None = None
    candidate_count: int = 0
    decision_count: int = 0
    suggest_count: int = 0
    ask_count: int = 0
    act_count: int = 0
    ignore_count: int = 0
    last_scorecard: InitiativeScorecardRecord = Field(default_factory=InitiativeScorecardRecord)
    last_grounding: InitiativeGroundingRecord = Field(default_factory=InitiativeGroundingRecord)


class CompanionSupervisorStatus(BaseModel):
    enabled: bool = False
    state: str = "disabled"
    active_session_id: str | None = None
    observer_interval_seconds: float | None = None
    last_tick_at: datetime | None = None
    last_scene_refresh_reason: str | None = None
    last_trigger_decision: CompanionTriggerDecision | None = None
    proactive_suppressed: bool = False
    proactive_suppression_reason: str | None = None
    last_outcome: str | None = None


class ConsoleRuntimeStatus(BaseModel):
    project_name: str
    dialogue_backend: str
    voice_backend: str
    perception_provider_mode: PerceptionProviderMode = PerceptionProviderMode.STUB
    runtime_profile: str
    deployment_target: str
    runtime_mode: RobotMode
    world_mode: RobotMode
    model_profile: str = "companion_live"
    resolved_model_profile: str | None = None
    backend_profile: str = "companion_live"
    resolved_backend_profile: str = "companion_live"
    voice_profile: str = "desktop_local"
    resolved_voice_profile: str = "desktop_local"
    embodiment_profile: str = "virtual_body"
    profile_summary: str | None = None
    provider_status: str | None = None
    provider_detail: str | None = None
    perception_status: str | None = None
    body_status: str | None = None
    camera_source: str = "default"
    configured_speaker_label: str | None = "system_default"
    selected_speaker_label: str | None = "system_default"
    speaker_selection_supported: bool = False
    device_preset: str = "auto"
    configured_microphone_label: str | None = None
    selected_microphone_label: str | None = None
    configured_camera_label: str | None = None
    selected_camera_label: str | None = None
    body_driver_mode: BodyDriverMode = BodyDriverMode.VIRTUAL
    head_profile_path: str | None = None
    operator_auth_enabled: bool = True
    auth_mode: str = "configured_static_token"
    operator_auth_token_source: str | None = None
    operator_auth_runtime_file: str | None = None
    setup_complete: bool = False
    setup_issues: list[ApplianceIssue] = Field(default_factory=list)
    config_source: str = "repo_defaults"
    console_url: str | None = None
    console_launch_state: str | None = None
    terminal_frontend_state: str = "unknown"
    terminal_frontend_detail: str | None = None
    edge_transport_mode: EdgeTransportMode = EdgeTransportMode.IN_PROCESS
    edge_transport_state: TransportState = TransportState.HEALTHY
    edge_transport_error: str | None = None
    default_live_voice_mode: VoiceRuntimeMode = VoiceRuntimeMode.STUB_DEMO
    audio_mode: CompanionAudioMode = CompanionAudioMode.PUSH_TO_TALK
    context_mode: CompanionContextMode = CompanionContextMode.PERSONAL_LOCAL
    text_backend: str | None = None
    vision_backend: str | None = None
    embedding_backend: str | None = None
    stt_backend: str | None = None
    tts_backend: str | None = None
    backend_status: list[RuntimeBackendStatus] = Field(default_factory=list)
    device_health: list[DesktopDeviceHealth] = Field(default_factory=list)
    perception_freshness: PerceptionFreshnessStatus = Field(default_factory=PerceptionFreshnessStatus)
    social_runtime_mode: SocialRuntimeMode = SocialRuntimeMode.IDLE
    last_semantic_refresh_reason: str | None = None
    active_speaker_hypothesis: str | None = None
    active_speaker_source: str | None = None
    attention_target_source: str | None = None
    greet_suppression_reason: str | None = None
    scene_reply_guardrail: str | None = None
    watcher_buffer_count: int = 0
    memory_status: MemoryStatus = Field(default_factory=MemoryStatus)
    fallback_state: FallbackState = Field(default_factory=FallbackState)
    always_on_enabled: bool = False
    supervisor: CompanionSupervisorStatus = Field(default_factory=CompanionSupervisorStatus)
    presence_runtime: CompanionPresenceStatus = Field(default_factory=CompanionPresenceStatus)
    character_projection_profile: CharacterProjectionProfile = CharacterProjectionProfile.NO_BODY
    character_semantic_intent: CharacterSemanticIntent = Field(default_factory=CharacterSemanticIntent)
    character_presence_shell: CharacterPresenceShellState = Field(default_factory=CharacterPresenceShellState)
    voice_loop: CompanionVoiceLoopStatus = Field(default_factory=CompanionVoiceLoopStatus)
    audio_loop: CompanionVoiceLoopStatus = Field(default_factory=CompanionVoiceLoopStatus)
    scene_observer: SceneObserverStatus = Field(default_factory=SceneObserverStatus)
    initiative_engine: InitiativeStatus = Field(default_factory=InitiativeStatus)
    trigger_engine: TriggerEngineStatus = Field(default_factory=TriggerEngineStatus)
    partial_transcript_preview: str | None = None
    latest_live_turn_diagnostics: LiveTurnDiagnosticsRecord | None = None
    scene_cache_age_seconds: float | None = None
    open_reminder_count: int = 0
    model_residency: list[LocalModelResidencyRecord] = Field(default_factory=list)
    agent_runtime_enabled: bool = True
    registered_skills: list[str] = Field(default_factory=list)
    registered_subagents: list[str] = Field(default_factory=list)
    registered_hooks: list[str] = Field(default_factory=list)
    registered_tools: list[str] = Field(default_factory=list)
    specialist_roles: list[str] = Field(default_factory=list)
    run_id: str | None = None
    run_phase: RunPhase | None = None
    run_status: RunStatus | None = None
    active_playbook: str | None = None
    active_playbook_variant: str | None = None
    active_subagent: str | None = None
    tool_chain: list[str] = Field(default_factory=list)
    checkpoint_count: int = 0
    last_checkpoint_id: str | None = None
    failure_state: str | None = None
    fallback_reason: str | None = None
    fallback_classification: FallbackClassification | None = None
    unavailable_capabilities: list[str] = Field(default_factory=list)
    intentionally_skipped_capabilities: list[str] = Field(default_factory=list)
    recovery_status: str | None = None
    instruction_layers: list[InstructionLayerRecord] = Field(default_factory=list)
    last_active_skill: SkillActivationRecord | None = None
    last_tool_calls: list[TypedToolCallRecord] = Field(default_factory=list)
    last_validation_outcomes: list[ValidationOutcomeRecord] = Field(default_factory=list)
    last_hook_records: list[HookExecutionRecord] = Field(default_factory=list)
    last_role_decisions: list[SpecialistRoleDecisionRecord] = Field(default_factory=list)
    grounded_scene_references: list[GroundingSourceRecord] = Field(default_factory=list)
    latest_scene_cache: SceneCacheRecord | None = None
    recent_memory_promotions: list[MemoryPromotionRecord] = Field(default_factory=list)
    action_plane: ActionPlaneStatus = Field(default_factory=ActionPlaneStatus)
    export_available: bool = True
    episode_export_dir: str | None = None
    startup_summary: ApplianceStartupSummary | None = None
    local_companion_readiness: LocalCompanionReadinessRecord | None = None


class OperatorConsoleSnapshot(BaseModel):
    runtime: ConsoleRuntimeStatus
    active_session_id: str | None = None
    sessions: list[SessionSummary] = Field(default_factory=list)
    selected_session: SessionRecord | None = None
    world_state: WorldState
    shift_supervisor: ShiftSupervisorSnapshot = Field(default_factory=ShiftSupervisorSnapshot)
    shift_metrics: ShiftMetricsSnapshot = Field(default_factory=ShiftMetricsSnapshot)
    participant_router: ParticipantRouterSnapshot = Field(default_factory=ParticipantRouterSnapshot)
    venue_operations: VenueOperationsSnapshot = Field(default_factory=VenueOperationsSnapshot)
    world_model: EmbodiedWorldModel = Field(default_factory=EmbodiedWorldModel)
    telemetry: TelemetrySnapshot
    heartbeat: HeartbeatStatus
    telemetry_log: TelemetryLogResponse = Field(default_factory=TelemetryLogResponse)
    command_history: CommandHistoryResponse = Field(default_factory=CommandHistoryResponse)
    trace_summaries: LogListResponse = Field(default_factory=LogListResponse)
    recent_demo_runs: DemoRunListResponse = Field(default_factory=DemoRunListResponse)
    voice_state: SpeechOutputResult = Field(default_factory=SpeechOutputResult)
    latest_perception: PerceptionSnapshotRecord | None = None
    perception_history: PerceptionHistoryResponse = Field(default_factory=PerceptionHistoryResponse)
    scene_observer_events: SceneObserverEventListResponse = Field(default_factory=SceneObserverEventListResponse)
    executive_decisions: ExecutiveDecisionListResponse = Field(default_factory=ExecutiveDecisionListResponse)
    shift_transitions: ShiftTransitionListResponse = Field(default_factory=ShiftTransitionListResponse)
    world_model_transitions: WorldModelTransitionListResponse = Field(default_factory=WorldModelTransitionListResponse)
    engagement_timeline: list[EngagementTimelinePoint] = Field(default_factory=list)
    selected_incident: IncidentTicketRecord | None = None
    selected_incident_timeline: IncidentTimelineResponse = Field(default_factory=IncidentTimelineResponse)
    open_incidents: IncidentListResponse = Field(default_factory=IncidentListResponse)
    closed_incidents: IncidentListResponse = Field(default_factory=IncidentListResponse)
    recent_shift_reports: ShiftReportListResponse = Field(default_factory=ShiftReportListResponse)
    runs: RunListResponse = Field(default_factory=RunListResponse)
    checkpoints: CheckpointListResponse = Field(default_factory=CheckpointListResponse)


class CharacterPresenceSurfaceSnapshot(BaseModel):
    generated_at: datetime = Field(default_factory=utc_now)
    active_session_id: str | None = None
    character_projection_profile: CharacterProjectionProfile = CharacterProjectionProfile.NO_BODY
    character_semantic_intent: CharacterSemanticIntent = Field(default_factory=CharacterSemanticIntent)
    character_presence_shell: CharacterPresenceShellState = Field(default_factory=CharacterPresenceShellState)
    presence_runtime: CompanionPresenceStatus = Field(default_factory=CompanionPresenceStatus)
    voice_loop: CompanionVoiceLoopStatus = Field(default_factory=CompanionVoiceLoopStatus)
    initiative_engine: InitiativeStatus = Field(default_factory=InitiativeStatus)
    relationship_continuity: RelationshipContinuityStatus = Field(default_factory=RelationshipContinuityStatus)
    fallback_state: FallbackState = Field(default_factory=FallbackState)
    body_state: BodyState | None = None


class RunExportResponse(BaseModel):
    artifact: RunExportArtifact


class InvestorSceneStep(BaseModel):
    action_type: str
    label: str
    input_text: str | None = None
    event_type: str | None = None
    payload: dict[str, object] = Field(default_factory=dict)
    fixture_path: str | None = None
    perception_mode: PerceptionProviderMode | None = None
    annotations: list[PerceptionAnnotationInput] = Field(default_factory=list)
    publish_events: bool = True


class InvestorSceneDefinition(BaseModel):
    scene_name: str
    title: str
    description: str
    session_id: str
    user_id: str | None = None
    steps: list[InvestorSceneStep] = Field(default_factory=list)


class InvestorSceneCatalogResponse(BaseModel):
    items: list[InvestorSceneDefinition] = Field(default_factory=list)


class InvestorSceneRunRequest(BaseModel):
    session_id: str | None = None
    user_id: str | None = None
    response_mode: ResponseMode | None = None
    voice_mode: VoiceRuntimeMode = VoiceRuntimeMode.STUB_DEMO
    speak_reply: bool = True


class InvestorSceneRunResult(BaseModel):
    scene_name: str
    title: str
    description: str
    session_id: str
    items: list[OperatorInteractionResult] = Field(default_factory=list)
    success: bool = True
    note: str | None = None
    perception_snapshots: list[PerceptionSnapshotRecord] = Field(default_factory=list)
    executive_decisions: list[ExecutiveDecisionRecord] = Field(default_factory=list)
    world_model_transitions: list[WorldModelTransitionRecord] = Field(default_factory=list)
    engagement_timeline: list[EngagementTimelinePoint] = Field(default_factory=list)
    grounding_sources: list[GroundingSourceRecord] = Field(default_factory=list)
    latency_breakdown: LatencyBreakdownRecord = Field(default_factory=LatencyBreakdownRecord)
    scorecard: DemoSceneScorecard | None = None
    final_action: FinalActionRecord | None = None


class PerformanceCueKind(str, Enum):
    PROMPT = "prompt"
    NARRATE = "narrate"
    CAPTION = "caption"
    RUN_SCENE = "run_scene"
    SUBMIT_TEXT_TURN = "submit_text_turn"
    INJECT_EVENT = "inject_event"
    PERCEPTION_FIXTURE = "perception_fixture"
    PERCEPTION_SNAPSHOT = "perception_snapshot"
    BODY_SEMANTIC_SMOKE = "body_semantic_smoke"
    BODY_PRIMITIVE_SEQUENCE = "body_primitive_sequence"
    BODY_STAGED_SEQUENCE = "body_staged_sequence"
    BODY_EXPRESSIVE_MOTIF = "body_expressive_motif"
    BODY_RANGE_DEMO = "body_range_demo"
    BODY_WRITE_NEUTRAL = "body_write_neutral"
    BODY_SAFE_IDLE = "body_safe_idle"
    PAUSE = "pause"
    EXPORT_SESSION_EPISODE = "export_session_episode"


class PerformanceProofBackendMode(str, Enum):
    DETERMINISTIC_SHOW = "deterministic_show"
    LIVE_COMPANION_PROOF = "live_companion_proof"


class PerformanceMotionOutcome(str, Enum):
    LIVE_APPLIED = "live_applied"
    PREVIEW_ONLY = "preview_only"
    BLOCKED = "blocked"


class PerformanceMotionMarginRecord(BaseModel):
    action: str
    outcome: PerformanceMotionOutcome = PerformanceMotionOutcome.BLOCKED
    safety_gate_passed: bool = True
    peak_calibrated_target: dict[str, int] = Field(default_factory=dict)
    latest_readback: dict[str, int] = Field(default_factory=dict)
    min_remaining_margin_percent_by_joint: dict[str, float] = Field(default_factory=dict)
    min_remaining_margin_percent_by_group: dict[str, float] = Field(default_factory=dict)
    max_remaining_margin_percent_by_group: dict[str, float] = Field(default_factory=dict)
    threshold_percent_by_group: dict[str, float] = Field(default_factory=dict)
    min_remaining_margin_percent: float | None = None
    worst_actuator_group: str | None = None
    health_flags: list[str] = Field(default_factory=list)
    error_joints: list[str] = Field(default_factory=list)
    abnormal_load_joints: list[str] = Field(default_factory=list)
    fault_classification: str | None = None
    power_health_classification: str | None = None
    suspect_voltage_event: bool = False
    readback_implausible: bool = False
    confirmation_read_performed: bool = False
    confirmation_result: str | None = None
    preflight_passed: bool | None = None
    preflight_failure_reason: str | None = None
    reason_code: str | None = None
    detail: str | None = None
    transport_mode: str | None = None
    transport_confirmed_live: bool | None = None
    live_readback_checked: bool = False


class PerformanceActuatorCoverageSummary(BaseModel):
    head_yaw: bool = False
    head_pitch_pair: bool = False
    eye_yaw: bool = False
    eye_pitch: bool = False
    upper_lids: bool = False
    lower_lids: bool = False
    brows: bool = False


class PerformanceMotionBeat(BaseModel):
    offset_ms: int = 0
    action: str
    intensity: float | None = None
    repeat_count: int = 1
    note: str | None = None
    coverage_tags: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_shape(self) -> "PerformanceMotionBeat":
        if self.offset_ms < 0:
            raise ValueError("performance_motion_beat_offset_ms_must_be_non_negative")
        if self.repeat_count < 1:
            raise ValueError("performance_motion_beat_repeat_count_must_be_positive")
        if self.intensity is not None and self.intensity < 0:
            raise ValueError("performance_motion_beat_intensity_must_be_non_negative")
        return self


class PerformanceShowDefaults(BaseModel):
    response_mode: ResponseMode = ResponseMode.AMBASSADOR
    proof_backend_mode: PerformanceProofBackendMode = PerformanceProofBackendMode.LIVE_COMPANION_PROOF
    proof_voice_mode: VoiceRuntimeMode = VoiceRuntimeMode.STUB_DEMO
    proof_speak_reply: bool = False
    narration_voice_mode: VoiceRuntimeMode = VoiceRuntimeMode.MACOS_SAY
    language: str = "en"
    narration_voice_preset: str | None = None
    narration_voice_name: str | None = None
    narration_voice_rate: int | None = None
    continue_on_error: bool = True


class PerformanceCue(BaseModel):
    cue_id: str
    cue_kind: PerformanceCueKind
    label: str | None = None
    text: str | None = None
    localized_text: dict[str, str] = Field(default_factory=dict)
    scene_name: str | None = None
    session_id: str | None = None
    user_id: str | None = None
    response_mode: ResponseMode | None = None
    voice_mode: VoiceRuntimeMode | None = None
    speak_reply: bool | None = None
    event_type: str | None = None
    payload: dict[str, object] = Field(default_factory=dict)
    perception_mode: PerceptionProviderMode | None = None
    fixture_path: str | None = None
    annotations: list[PerceptionAnnotationInput] = Field(default_factory=list)
    publish_events: bool = True
    action: str | None = None
    intensity: float | None = None
    repeat_count: int = 1
    note: str | None = None
    primitive_sequence: list[PrimitiveSequenceStep] = Field(default_factory=list)
    staged_sequence: list[StagedSequenceStage] = Field(default_factory=list)
    expressive_motif: ExpressiveMotifReference | None = None
    motion_track: list[PerformanceMotionBeat] = Field(default_factory=list)
    expect_reply_contains: list[str] = Field(default_factory=list)
    expect_grounding_sources: bool | None = None
    expect_incident: bool | None = None
    expect_incident_status: str | None = None
    expect_incident_reason_category: str | None = None
    expect_safe_idle: bool | None = None
    expect_user_memory_facts: dict[str, str] = Field(default_factory=dict)
    expect_user_memory_preferences: dict[str, str] = Field(default_factory=dict)
    expect_body_projection_outcome: str | None = None
    expect_body_status_contains: list[str] = Field(default_factory=list)
    expect_payload_equals: dict[str, object] = Field(default_factory=dict)
    expect_export_artifacts: list[str] = Field(default_factory=list)
    fallback_text: str | None = None
    localized_fallback_text: dict[str, str] = Field(default_factory=dict)
    continue_on_error: bool | None = None
    target_duration_ms: int | None = None

    @model_validator(mode="after")
    def validate_shape(self) -> "PerformanceCue":
        match self.cue_kind:
            case (
                PerformanceCueKind.PROMPT
                | PerformanceCueKind.NARRATE
                | PerformanceCueKind.CAPTION
                | PerformanceCueKind.SUBMIT_TEXT_TURN
            ):
                if not self.text:
                    raise ValueError(f"{self.cue_kind.value}_cue_requires_text")
            case PerformanceCueKind.RUN_SCENE:
                if not self.scene_name:
                    raise ValueError("run_scene_cue_requires_scene_name")
            case PerformanceCueKind.INJECT_EVENT:
                if not self.event_type:
                    raise ValueError("inject_event_cue_requires_event_type")
            case PerformanceCueKind.PERCEPTION_FIXTURE:
                if not self.fixture_path:
                    raise ValueError("perception_fixture_cue_requires_fixture_path")
            case PerformanceCueKind.PERCEPTION_SNAPSHOT:
                if self.perception_mode is None:
                    raise ValueError("perception_snapshot_cue_requires_perception_mode")
            case PerformanceCueKind.BODY_SEMANTIC_SMOKE:
                if not self.action:
                    raise ValueError("body_semantic_smoke_cue_requires_action")
            case PerformanceCueKind.BODY_PRIMITIVE_SEQUENCE:
                if not self.primitive_sequence:
                    raise ValueError("body_primitive_sequence_cue_requires_steps")
            case PerformanceCueKind.BODY_STAGED_SEQUENCE:
                if not self.staged_sequence:
                    raise ValueError("body_staged_sequence_cue_requires_stages")
            case PerformanceCueKind.BODY_EXPRESSIVE_MOTIF:
                if self.expressive_motif is None:
                    raise ValueError("body_expressive_motif_cue_requires_motif")
            case PerformanceCueKind.PAUSE:
                if self.target_duration_ms is None:
                    raise ValueError("pause_cue_requires_target_duration_ms")
            case _:
                pass
        if self.repeat_count < 1:
            raise ValueError("performance_cue_repeat_count_must_be_positive")
        if self.target_duration_ms is not None and self.target_duration_ms < 0:
            raise ValueError("performance_cue_target_duration_ms_must_be_non_negative")
        if self.intensity is not None and self.intensity < 0:
            raise ValueError("performance_cue_intensity_must_be_non_negative")
        return self


class PerformanceSegment(BaseModel):
    segment_id: str
    title: str
    investor_claim: str
    target_start_seconds: int = 0
    target_duration_seconds: int = 0
    cues: list[PerformanceCue] = Field(default_factory=list)


class PerformanceShowDefinition(BaseModel):
    show_name: str
    title: str
    version: str = "v1"
    session_id: str
    defaults: PerformanceShowDefaults = Field(default_factory=PerformanceShowDefaults)
    segments: list[PerformanceSegment] = Field(default_factory=list)


class PerformanceCueResult(BaseModel):
    cue_id: str
    cue_kind: PerformanceCueKind
    label: str | None = None
    status: str = "pending"
    success: bool = True
    degraded: bool = False
    fallback_used: bool = False
    note: str | None = None
    target_duration_ms: int | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    actual_duration_ms: float | None = None
    timing_drift_ms: float | None = None
    motion_outcome: PerformanceMotionOutcome | None = None
    motion_margin_record: PerformanceMotionMarginRecord | None = None
    actuator_coverage: PerformanceActuatorCoverageSummary = Field(default_factory=PerformanceActuatorCoverageSummary)
    proof_checks: list[ScorecardCriterion] = Field(default_factory=list)
    payload: dict[str, object] = Field(default_factory=dict)


class PerformanceSegmentResult(BaseModel):
    segment_id: str
    title: str
    investor_claim: str
    target_start_seconds: int = 0
    target_duration_seconds: int = 0
    status: str = "pending"
    success: bool = True
    degraded: bool = False
    started_at: datetime | None = None
    completed_at: datetime | None = None
    actual_duration_ms: float | None = None
    timing_drift_ms: float | None = None
    proof_check_count: int = 0
    failed_proof_check_count: int = 0
    actuator_coverage: PerformanceActuatorCoverageSummary = Field(default_factory=PerformanceActuatorCoverageSummary)
    cue_results: list[PerformanceCueResult] = Field(default_factory=list)


class PerformanceRunRequest(BaseModel):
    session_id: str | None = None
    response_mode: ResponseMode | None = None
    proof_backend_mode: PerformanceProofBackendMode | None = None
    narration_voice_mode: VoiceRuntimeMode | None = None
    proof_voice_mode: VoiceRuntimeMode | None = None
    language: str | None = None
    narration_voice_preset: str | None = None
    narration_voice_name: str | None = None
    narration_voice_rate: int | None = None
    continue_on_error: bool | None = None
    background: bool = True
    narration_enabled: bool = True
    narration_only: bool = False
    proof_only: bool = False
    segment_ids: list[str] = Field(default_factory=list)
    cue_ids: list[str] = Field(default_factory=list)
    force_degraded_cue_ids: list[str] = Field(default_factory=list)
    reset_runtime: bool = False


class PerformanceRunResult(BaseModel):
    run_id: str
    status: DemoRunStatus = DemoRunStatus.RUNNING
    show_name: str
    version: str = "v1"
    session_id: str
    proof_backend_mode: PerformanceProofBackendMode | None = None
    language: str = "en"
    narration_voice_preset: str | None = None
    narration_voice_name: str | None = None
    narration_voice_rate: int | None = None
    selected_show_tuning_path: str | None = None
    live_motion_arm_author: str | None = None
    live_motion_arm_port: str | None = None
    started_at: datetime = Field(default_factory=utc_now)
    completed_at: datetime | None = None
    current_segment_id: str | None = None
    current_segment_title: str | None = None
    current_investor_claim: str | None = None
    current_cue_id: str | None = None
    current_prompt: str | None = None
    current_caption: str | None = None
    current_narration: str | None = None
    selected_segment_ids: list[str] = Field(default_factory=list)
    selected_cue_ids: list[str] = Field(default_factory=list)
    narration_only: bool = False
    proof_only: bool = False
    target_total_duration_seconds: int = 0
    elapsed_seconds: float = 0.0
    timing_drift_seconds: float | None = None
    completed_segment_count: int = 0
    proof_check_count: int = 0
    failed_proof_check_count: int = 0
    last_body_projection_outcome: str | None = None
    last_motion_outcome: PerformanceMotionOutcome | None = None
    last_motion_margin_record: PerformanceMotionMarginRecord | None = None
    actuator_coverage: PerformanceActuatorCoverageSummary = Field(default_factory=PerformanceActuatorCoverageSummary)
    min_margin_percent_by_group: dict[str, float] = Field(default_factory=dict)
    max_margin_percent_by_group: dict[str, float] = Field(default_factory=dict)
    worst_actuator_group: str | None = None
    degraded_due_to_margin_only_cues: list[str] = Field(default_factory=list)
    eye_pitch_exercised_live: bool = False
    last_body_issue_classification: str | None = None
    last_body_issue_confirmation_result: str | None = None
    power_health_classification: str | None = None
    preflight_passed: bool | None = None
    preflight_failure_reason: str | None = None
    idle_voltage_snapshot: dict[str, dict[str, object]] = Field(default_factory=dict)
    body_fault_latched_preview_only: bool = False
    body_fault_trigger_cue_id: str | None = None
    body_fault_detail: str | None = None
    pending_body_settle_reason: str | None = None
    preview_only: bool = False
    stop_requested: bool = False
    degraded: bool = False
    degraded_cues: list[str] = Field(default_factory=list)
    segment_results: list[PerformanceSegmentResult] = Field(default_factory=list)
    timing_breakdown_ms: dict[str, float] = Field(default_factory=dict)
    artifact_dir: str | None = None
    artifact_files: dict[str, str] = Field(default_factory=dict)
    episode_id: str | None = None
    notes: list[str] = Field(default_factory=list)


class PerformanceShowCatalogResponse(BaseModel):
    items: list[PerformanceShowDefinition] = Field(default_factory=list)
    active_run_id: str | None = None
    latest_run_id: str | None = None


class BrainResetRequest(BaseModel):
    reset_edge: bool = False
    clear_user_memory: bool = True
    clear_demo_runs: bool = False


class ResetResult(BaseModel):
    ok: bool = True
    brain_reset: bool = True
    edge_reset: bool = False
    cleared_demo_runs: bool = False
    notes: list[str] = Field(default_factory=list)

__all__ = [
    "ApplianceStartupSummary",
    "ApplianceBootstrapResponse",
    "ApplianceDeviceCatalog",
    "ApplianceDeviceOption",
    "ApplianceIssue",
    "ApplianceProfileRequest",
    "ApplianceStatus",
    "BodyActionResult",
    "BodyArmRequest",
    "BodyConnectRequest",
    "BodyExpressiveSequenceRequest",
    "BodyIdsRequest",
    "BodyPrimitiveSequenceRequest",
    "BodyStagedSequenceRequest",
    "BodySemanticSmokeRequest",
    "ExpressiveMotifReference",
    "ExpressiveSequenceStep",
    "PrimitiveSequenceStep",
    "StagedSequenceAccent",
    "StagedSequenceStage",
    "BodyServoLabReferenceMode",
    "BodyServoLabReadbackRequest",
    "BodyServoLabMoveRequest",
    "BodyServoLabSweepRequest",
    "BodyServoLabSaveCalibrationRequest",
    "BodyTeacherReviewRequest",
    "BrowserActionTaskRequest",
    "BrowserAudioTurnRequest",
    "BrowserAudioTurnResult",
    "BrainResetRequest",
    "CompanionPresenceStatus",
    "CharacterPresenceSurfaceSnapshot",
    "CompanionSupervisorStatus",
    "CompanionVoiceLoopStatus",
    "ConsoleRuntimeStatus",
    "DesktopDeviceHealth",
    "DesktopDeviceKind",
    "FallbackState",
    "FreshnessWindowStatus",
    "InvestorSceneCatalogResponse",
    "InvestorSceneDefinition",
    "InvestorSceneRunRequest",
    "InvestorSceneRunResult",
    "InvestorSceneStep",
    "InitiativeGroundingRecord",
    "InitiativeScorecardRecord",
    "InitiativeStatus",
    "LocalModelResidencyRecord",
    "LiveVoiceStateUpdateRequest",
    "MemoryStatus",
    "RelationshipContinuityStatus",
    "OperatorAuthLoginRequest",
    "OperatorAuthStatus",
    "OperatorConsoleSnapshot",
    "OperatorInteractionResult",
    "OperatorNoteRequest",
    "OperatorVoiceTurnRequest",
    "PerceptionAnnotationInput",
    "PerceptionFixtureCatalogResponse",
    "PerceptionFreshnessStatus",
    "PerceptionPublishedResult",
    "PerceptionReplayRequest",
    "PerceptionReplayResult",
    "PerceptionSnapshotSubmitRequest",
    "PerceptionSubmissionResult",
    "PerformanceCue",
    "PerformanceCueKind",
    "PerformanceMotionBeat",
    "PerformanceMotionOutcome",
    "PerformanceMotionMarginRecord",
    "PerformanceActuatorCoverageSummary",
    "PerformanceProofBackendMode",
    "PerformanceCueResult",
    "PerformanceRunRequest",
    "PerformanceRunResult",
    "PerformanceSegment",
    "PerformanceSegmentResult",
    "PerformanceShowCatalogResponse",
    "PerformanceShowDefaults",
    "PerformanceShowDefinition",
    "ResetResult",
    "RunExportResponse",
    "RuntimeBackendStatus",
    "BrowserRuntimeStatusRecord",
    "SceneObserverStatus",
    "StartupDeviceSelection",
    "ShiftAutonomyTickRequest",
    "ShiftOverrideRequest",
    "TriggerEngineStatus",
    "VoiceCancelResult",
]
