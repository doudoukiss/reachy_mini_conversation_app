from __future__ import annotations

from ._common import (
    ActionTeacherFeedbackLabel,
    Any,
    BaseModel,
    BenchmarkFamily,
    BenchmarkComparisonMode,
    CommandType,
    EpisodeSourceType,
    ExportRedactionProfile,
    Field,
    PlannerReplayMode,
    RedactionState,
    ResearchExportFormat,
    SensitiveContentFlag,
    TeacherAnnotationScope,
    TeacherMemoryFeedbackAction,
    TeacherPrimaryKind,
    datetime,
    utc_now,
    uuid4,
)
from .brain import (
    GroundingSourceRecord,
    MemoryActionRecord,
    MemoryRetrievalRecord,
    MemoryReviewRecord,
    WorldState,
)
from .demo import (
    EpisodeAcknowledgementRecord,
    EpisodeAnnotationLabel,
    EpisodeAssetReference,
    EpisodeCommandRecord,
    EpisodeExportRunRequest,
    EpisodeExportSessionRequest,
    EpisodeExportShiftReportRequest,
    EpisodeSessionMetadata,
    EpisodeTelemetryRecord,
    EpisodeToolCallRecord,
    EpisodeTranscriptEntry,
)
from .perception import (
    EmbodiedWorldModel,
    ExecutiveDecisionRecord,
    PerceptionFactRecord,
    PerceptionSnapshotRecord,
    WorldModelTransitionRecord,
)
from .brain import (
    EpisodicMemoryRecord,
    IncidentTicketRecord,
    IncidentTimelineRecord,
    ProceduralMemoryRecord,
    RelationshipMemoryRecord,
    SemanticMemoryRecord,
    SessionRecord,
    TraceRecord,
    UserMemoryRecord,
)
from .edge import RobotEvent


class TeacherReplyFeedback(BaseModel):
    better_reply_text: str | None = None
    note: str | None = None


class TeacherMemoryFeedback(BaseModel):
    action: TeacherMemoryFeedbackAction = TeacherMemoryFeedbackAction.NEEDS_REVIEW
    memory_id: str | None = None
    merge_into_memory_id: str | None = None
    corrected_value: str | None = None
    importance_label: str | None = None
    note: str | None = None


class TeacherSceneFeedback(BaseModel):
    corrected_scene_summary: str | None = None
    target_fact_ids: list[str] = Field(default_factory=list)
    note: str | None = None


class TeacherEmbodimentFeedback(BaseModel):
    preferred_body_expression: str | None = None
    preferred_command_types: list[CommandType] = Field(default_factory=list)
    note: str | None = None


class TeacherOutcomeFeedback(BaseModel):
    outcome_label: str | None = None
    proactive_prompt_appropriate: bool | None = None
    success_label: str | None = None
    note: str | None = None


class TeacherActionFeedback(BaseModel):
    labels: list[ActionTeacherFeedbackLabel] = Field(default_factory=list)
    note: str | None = None


class TeacherSupervisionSummary(BaseModel):
    annotation_count: int = 0
    authors: list[str] = Field(default_factory=list)
    primary_kinds: list[TeacherPrimaryKind] = Field(default_factory=list)
    benchmark_tags: list[str] = Field(default_factory=list)
    outcome_labels: list[str] = Field(default_factory=list)


class EpisodeDatasetMembership(BaseModel):
    dataset_id: str
    split_name: str | None = None
    entry_id: str | None = None


class TeacherReviewRequest(BaseModel):
    review_value: str = "needs_revision"
    label: str | None = None
    note: str | None = None
    author: str = "operator"
    primary_kind: TeacherPrimaryKind | None = None
    reply_feedback: TeacherReplyFeedback | None = None
    memory_feedback: TeacherMemoryFeedback | None = None
    scene_feedback: TeacherSceneFeedback | None = None
    embodiment_feedback: TeacherEmbodimentFeedback | None = None
    outcome_feedback: TeacherOutcomeFeedback | None = None
    action_feedback: TeacherActionFeedback | None = None
    better_reply_text: str | None = None
    corrected_scene_summary: str | None = None
    preferred_body_expression: str | None = None
    memory_importance: str | None = None
    proactive_prompt_appropriate: bool | None = None
    outcome_label: str | None = None
    action_feedback_labels: list[ActionTeacherFeedbackLabel] = Field(default_factory=list)
    benchmark_tags: list[str] = Field(default_factory=list)

    @property
    def resolved_primary_kind(self) -> TeacherPrimaryKind:
        if self.primary_kind is not None:
            return self.primary_kind
        if self.reply_feedback is not None or self.better_reply_text:
            return TeacherPrimaryKind.REPLY
        if self.memory_feedback is not None or self.memory_importance:
            return TeacherPrimaryKind.MEMORY
        if self.scene_feedback is not None or self.corrected_scene_summary:
            return TeacherPrimaryKind.SCENE
        if self.embodiment_feedback is not None or self.preferred_body_expression:
            return TeacherPrimaryKind.EMBODIMENT
        if self.outcome_feedback is not None or self.outcome_label is not None:
            return TeacherPrimaryKind.OUTCOME
        if self.action_feedback is not None or self.action_feedback_labels:
            return TeacherPrimaryKind.ACTION
        return TeacherPrimaryKind.GENERAL

    def normalized_reply_feedback(self) -> TeacherReplyFeedback | None:
        if self.reply_feedback is not None:
            return self.reply_feedback
        if self.better_reply_text:
            return TeacherReplyFeedback(better_reply_text=self.better_reply_text, note=self.note)
        return None

    def normalized_memory_feedback(self) -> TeacherMemoryFeedback | None:
        if self.memory_feedback is not None:
            return self.memory_feedback
        if self.memory_importance:
            return TeacherMemoryFeedback(
                action=TeacherMemoryFeedbackAction.NEEDS_REVIEW,
                importance_label=self.memory_importance,
                note=self.note,
            )
        return None

    def normalized_scene_feedback(self) -> TeacherSceneFeedback | None:
        if self.scene_feedback is not None:
            return self.scene_feedback
        if self.corrected_scene_summary:
            return TeacherSceneFeedback(corrected_scene_summary=self.corrected_scene_summary, note=self.note)
        return None

    def normalized_embodiment_feedback(self) -> TeacherEmbodimentFeedback | None:
        if self.embodiment_feedback is not None:
            return self.embodiment_feedback
        if self.preferred_body_expression:
            return TeacherEmbodimentFeedback(preferred_body_expression=self.preferred_body_expression, note=self.note)
        return None

    def normalized_outcome_feedback(self) -> TeacherOutcomeFeedback | None:
        if self.outcome_feedback is not None:
            return self.outcome_feedback
        if self.outcome_label is not None or self.proactive_prompt_appropriate is not None:
            return TeacherOutcomeFeedback(
                outcome_label=self.outcome_label,
                proactive_prompt_appropriate=self.proactive_prompt_appropriate,
                success_label=self.review_value,
                note=self.note,
            )
        return None

    def normalized_action_feedback(self) -> TeacherActionFeedback | None:
        if self.action_feedback is not None:
            return self.action_feedback
        if self.action_feedback_labels:
            return TeacherActionFeedback(labels=list(self.action_feedback_labels), note=self.note)
        return None


class TeacherAnnotationRecord(BaseModel):
    annotation_id: str = Field(default_factory=lambda: str(uuid4()))
    scope: TeacherAnnotationScope
    scope_id: str
    review_value: str = "needs_revision"
    label: str | None = None
    note: str | None = None
    author: str = "operator"
    primary_kind: TeacherPrimaryKind = TeacherPrimaryKind.GENERAL
    session_id: str | None = None
    trace_id: str | None = None
    run_id: str | None = None
    action_id: str | None = None
    workflow_run_id: str | None = None
    memory_id: str | None = None
    episode_id: str | None = None
    reply_feedback: TeacherReplyFeedback | None = None
    memory_feedback: TeacherMemoryFeedback | None = None
    scene_feedback: TeacherSceneFeedback | None = None
    embodiment_feedback: TeacherEmbodimentFeedback | None = None
    outcome_feedback: TeacherOutcomeFeedback | None = None
    action_feedback: TeacherActionFeedback | None = None
    better_reply_text: str | None = None
    corrected_scene_summary: str | None = None
    preferred_body_expression: str | None = None
    memory_importance: str | None = None
    proactive_prompt_appropriate: bool | None = None
    outcome_label: str | None = None
    action_feedback_labels: list[ActionTeacherFeedbackLabel] = Field(default_factory=list)
    benchmark_tags: list[str] = Field(default_factory=list)
    sensitive_content_flags: list[SensitiveContentFlag] = Field(default_factory=list)
    redaction_state: RedactionState = RedactionState.RAW
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class TeacherAnnotationListResponse(BaseModel):
    items: list[TeacherAnnotationRecord] = Field(default_factory=list)


class EpisodeSummaryV2(BaseModel):
    episode_id: str = Field(default_factory=lambda: str(uuid4()))
    schema_version: str = "blink_episode/v2"
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
    relationship_memory_count: int = 0
    procedural_memory_count: int = 0
    asset_ref_count: int = 0
    annotation_count: int = 0
    scene_fact_count: int = 0
    memory_action_count: int = 0
    memory_review_count: int = 0
    memory_retrieval_count: int = 0
    teacher_annotation_count: int = 0
    input_event_count: int = 0
    benchmark_label_count: int = 0
    dataset_membership_count: int = 0
    run_count: int = 0
    redaction_profile: ExportRedactionProfile = ExportRedactionProfile.LOCAL_FULL
    sensitive_content_flags: list[SensitiveContentFlag] = Field(default_factory=list)
    redactions_applied: list[str] = Field(default_factory=list)
    artifact_dir: str | None = None
    artifact_files: dict[str, str] = Field(default_factory=dict)
    derived_artifact_files: dict[str, str] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)
    final_reply_text: str | None = None
    outcome_label: str | None = None


class EpisodeRecordV2(EpisodeSummaryV2):
    sessions: list[EpisodeSessionMetadata] = Field(default_factory=list)
    input_events: list[RobotEvent] = Field(default_factory=list)
    transcript: list[EpisodeTranscriptEntry] = Field(default_factory=list)
    traces: list[TraceRecord] = Field(default_factory=list)
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
    relationship_memory: list[RelationshipMemoryRecord] = Field(default_factory=list)
    procedural_memory: list[ProceduralMemoryRecord] = Field(default_factory=list)
    grounding_sources: list[GroundingSourceRecord] = Field(default_factory=list)
    final_world_state: WorldState | None = None
    final_world_model: EmbodiedWorldModel | None = None
    asset_refs: list[EpisodeAssetReference] = Field(default_factory=list)
    annotations: list[EpisodeAnnotationLabel] = Field(default_factory=list)
    scene_facts: list[PerceptionFactRecord] = Field(default_factory=list)
    chosen_skills: list[str] = Field(default_factory=list)
    chosen_subagents: list[str] = Field(default_factory=list)
    run_ids: list[str] = Field(default_factory=list)
    memory_actions: list[MemoryActionRecord] = Field(default_factory=list)
    memory_reviews: list[MemoryReviewRecord] = Field(default_factory=list)
    memory_retrievals: list[MemoryRetrievalRecord] = Field(default_factory=list)
    teacher_annotations: list[TeacherAnnotationRecord] = Field(default_factory=list)
    teacher_supervision_summary: TeacherSupervisionSummary = Field(default_factory=TeacherSupervisionSummary)
    benchmark_labels: list[str] = Field(default_factory=list)
    dataset_memberships: list[EpisodeDatasetMembership] = Field(default_factory=list)
    body_action_types: list[CommandType] = Field(default_factory=list)
    fallback_reasons: list[str] = Field(default_factory=list)
    user_reaction_summary: str | None = None


class EpisodeManifestV2(BaseModel):
    schema_version: str = "blink_episode/v2"
    episode_id: str
    source_type: EpisodeSourceType
    source_id: str
    exported_at: datetime = Field(default_factory=utc_now)
    session_ids: list[str] = Field(default_factory=list)
    scenario_names: list[str] = Field(default_factory=list)
    artifact_files: dict[str, str] = Field(default_factory=dict)
    derived_artifact_files: dict[str, str] = Field(default_factory=dict)
    redaction_profile: ExportRedactionProfile = ExportRedactionProfile.LOCAL_FULL
    sensitive_content_flags: list[SensitiveContentFlag] = Field(default_factory=list)
    redactions_applied: list[str] = Field(default_factory=list)
    dataset_memberships: list[EpisodeDatasetMembership] = Field(default_factory=list)
    benchmark_labels: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    outcome_label: str | None = None
    teacher_annotation_count: int = 0
    memory_retrieval_count: int = 0


class EpisodeListResponseV2(BaseModel):
    items: list[EpisodeSummaryV2] = Field(default_factory=list)


class BenchmarkCaseResult(BaseModel):
    case_id: str = Field(default_factory=lambda: str(uuid4()))
    family: BenchmarkFamily
    canonical_family: BenchmarkFamily | None = None
    title: str
    passed: bool = True
    score: float = 0.0
    max_score: float = 1.0
    latency_ms: float | None = None
    fallback_count: int = 0
    memory_quality_signal: float | None = None
    body_action_valid: bool = True
    reason_code: str | None = None
    divergence_summary: dict[str, int] = Field(default_factory=dict)
    artifact_refs: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class BenchmarkRunRequest(BaseModel):
    episode_id: str
    families: list[BenchmarkFamily] = Field(default_factory=list)
    planner_id: str | None = None
    planner_profile: str = "default"
    comparison_planners: list[str] = Field(default_factory=list)
    comparison_profiles: dict[str, str] = Field(default_factory=dict)
    replay_id: str | None = None
    replay_mode: PlannerReplayMode = PlannerReplayMode.STRICT
    comparison_mode: BenchmarkComparisonMode = BenchmarkComparisonMode.EPISODE_ONLY
    research_formats: list[ResearchExportFormat] = Field(default_factory=lambda: [ResearchExportFormat.NATIVE])


class BenchmarkRunRecord(BaseModel):
    run_id: str = Field(default_factory=lambda: str(uuid4()))
    episode_id: str
    families: list[BenchmarkFamily] = Field(default_factory=list)
    started_at: datetime = Field(default_factory=utc_now)
    completed_at: datetime | None = None
    passed: bool = True
    score: float = 0.0
    max_score: float = 0.0
    fallback_count: int = 0
    planner_id: str | None = None
    planner_profile: str = "default"
    replay_id: str | None = None
    replay_mode: PlannerReplayMode | None = None
    comparison_mode: BenchmarkComparisonMode = BenchmarkComparisonMode.EPISODE_ONLY
    determinism_status: str | None = None
    planner_comparison_summary: list[dict[str, Any]] = Field(default_factory=list)
    suite_summary: dict[str, Any] = Field(default_factory=dict)
    evidence_pack_id: str | None = None
    evidence_pack_manifest: str | None = None
    results: list[BenchmarkCaseResult] = Field(default_factory=list)
    artifact_dir: str | None = None
    artifact_files: dict[str, str] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)


class BenchmarkRunListResponse(BaseModel):
    items: list[BenchmarkRunRecord] = Field(default_factory=list)


class BenchmarkCatalogResponse(BaseModel):
    families: list[BenchmarkFamily] = Field(default_factory=list)
    runs: list[BenchmarkRunRecord] = Field(default_factory=list)


__all__ = [
    "BenchmarkCatalogResponse",
    "BenchmarkCaseResult",
    "BenchmarkRunListResponse",
    "BenchmarkRunRecord",
    "BenchmarkRunRequest",
    "EpisodeExportRunRequest",
    "EpisodeExportSessionRequest",
    "EpisodeExportShiftReportRequest",
    "EpisodeDatasetMembership",
    "EpisodeListResponseV2",
    "EpisodeManifestV2",
    "EpisodeRecordV2",
    "EpisodeSummaryV2",
    "TeacherActionFeedback",
    "TeacherEmbodimentFeedback",
    "TeacherAnnotationListResponse",
    "TeacherAnnotationRecord",
    "TeacherMemoryFeedback",
    "TeacherOutcomeFeedback",
    "TeacherReplyFeedback",
    "TeacherReviewRequest",
    "TeacherSceneFeedback",
    "TeacherSupervisionSummary",
]
