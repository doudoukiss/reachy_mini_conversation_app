from __future__ import annotations

from ._common import (
    Any,
    BaseModel,
    BenchmarkComparisonMode,
    DatasetSplitName,
    ExportRedactionProfile,
    Field,
    PlannerReplayMode,
    RedactionState,
    ResearchExportFormat,
    SensitiveContentFlag,
    datetime,
    utc_now,
    uuid4,
)
from .brain import SessionRecord, ToolInvocationRecord, TypedToolCallRecord
from .demo import EpisodeSessionMetadata
from .edge import CommandBatch, RobotCommand, RobotEvent
from .episode import EpisodeDatasetMembership, EpisodeRecordV2
from .perception import EmbodiedWorldModel, PerceptionSnapshotRecord


class PlannerDescriptor(BaseModel):
    planner_id: str
    display_name: str
    description: str | None = None
    deterministic: bool = False
    default_profile: str = "default"
    available_profiles: list[str] = Field(default_factory=lambda: ["default"])
    supports_strict_mode: bool = True
    strict_replay_policy_version: str = "blink_strict_replay/v2"
    capability_tags: list[str] = Field(default_factory=list)
    expected_input_surfaces: list[str] = Field(default_factory=list)
    comparison_labels: list[str] = Field(default_factory=list)
    scoring_notes: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class PlannerCatalogResponse(BaseModel):
    items: list[PlannerDescriptor] = Field(default_factory=list)


class PlannerInputRecord(BaseModel):
    source_trace_id: str | None = None
    session_id: str
    user_id: str | None = None
    input_text: str | None = None
    event: RobotEvent
    session_snapshot: SessionRecord | EpisodeSessionMetadata | None = None
    world_model: EmbodiedWorldModel | None = None
    latest_perception: PerceptionSnapshotRecord | None = None
    tool_invocations: list[ToolInvocationRecord] = Field(default_factory=list)
    memory_updates: dict[str, str] = Field(default_factory=dict)
    strict_replay_policy_version: str = "blink_strict_replay/v2"
    normalized_scene_facts: list[dict[str, Any]] = Field(default_factory=list)
    selected_tool_chain: list[str] = Field(default_factory=list)
    retrieved_memory_candidates: list[dict[str, Any]] = Field(default_factory=list)
    planner_input_envelope: dict[str, Any] = Field(default_factory=dict)
    replay_mode: PlannerReplayMode | None = None
    created_at: datetime = Field(default_factory=utc_now)


class PlannerOutputRecord(BaseModel):
    planner_id: str
    planner_profile: str = "default"
    engine_name: str
    reply_text: str | None = None
    intent: str
    active_skill: str | None = None
    active_playbook: str | None = None
    active_playbook_variant: str | None = None
    active_subagent: str | None = None
    fallback_used: bool = False
    fallback_reason: str | None = None
    fallback_classification: str | None = None
    strict_replay_policy_version: str = "blink_strict_replay/v2"
    typed_tool_calls: list[TypedToolCallRecord] = Field(default_factory=list)
    selected_tool_chain: list[str] = Field(default_factory=list)
    retrieved_memory_candidates: list[dict[str, Any]] = Field(default_factory=list)
    normalized_scene_facts_used: list[dict[str, Any]] = Field(default_factory=list)
    planner_output_envelope: dict[str, Any] = Field(default_factory=dict)
    embodiment_output_envelope: dict[str, Any] = Field(default_factory=dict)
    commands: list[RobotCommand] = Field(default_factory=list)
    run_id: str | None = None
    notes: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)


class PlannerDiffRecord(BaseModel):
    field_name: str
    matched: bool = True
    source_value: object | None = None
    replay_value: object | None = None
    reason_code: str | None = None
    divergence_class: str = "acceptable"
    severity: int = 0
    acceptable_in_strict: bool = True
    note: str | None = None


class PlannerReplayRequest(BaseModel):
    episode_id: str
    planner_id: str = "agent_os_current"
    planner_profile: str = "default"
    replay_mode: PlannerReplayMode = PlannerReplayMode.STRICT
    comparison_mode: BenchmarkComparisonMode = BenchmarkComparisonMode.EPISODE_VS_REPLAY


class PlannerReplayStepRecord(BaseModel):
    step_index: int
    source_trace_id: str | None = None
    session_id: str
    event: RobotEvent
    source_response: CommandBatch | None = None
    planner_input: PlannerInputRecord
    planner_output: PlannerOutputRecord
    replay_response: CommandBatch
    diffs: list[PlannerDiffRecord] = Field(default_factory=list)
    matched: bool = True
    match_score: float = 1.0
    divergence_summary: dict[str, int] = Field(default_factory=dict)
    normalized_envelope_refs: dict[str, str] = Field(default_factory=dict)
    note: str | None = None


class PlannerReplayRecord(BaseModel):
    replay_id: str = Field(default_factory=lambda: str(uuid4()))
    schema_version: str = "blink_planner_replay/v1"
    episode_id: str
    planner_id: str
    planner_profile: str = "default"
    replay_mode: PlannerReplayMode = PlannerReplayMode.STRICT
    comparison_mode: BenchmarkComparisonMode = BenchmarkComparisonMode.EPISODE_VS_REPLAY
    deterministic: bool = False
    strict_replay_policy_version: str = "blink_strict_replay/v2"
    replay_policy_notes: list[str] = Field(default_factory=list)
    acceptable_divergence_fields: list[str] = Field(default_factory=list)
    environment_fingerprint: dict[str, Any] = Field(default_factory=dict)
    source_episode_ref: str | None = None
    source_episode_artifact_dir: str | None = None
    started_at: datetime = Field(default_factory=utc_now)
    completed_at: datetime | None = None
    step_count: int = 0
    matched_step_count: int = 0
    match_ratio: float = 0.0
    divergence_summary: dict[str, int] = Field(default_factory=dict)
    normalized_envelope_refs: dict[str, str] = Field(default_factory=dict)
    artifact_dir: str | None = None
    artifact_files: dict[str, str] = Field(default_factory=dict)
    steps: list[PlannerReplayStepRecord] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class DatasetSplitRecord(BaseModel):
    split_name: DatasetSplitName
    group_key: str
    leakage_group_key: str | None = None
    split_seed: str = "blink_stage5_v1"
    source_episode_id: str
    source_ref: str
    note: str | None = None


class ResearchExportRequest(BaseModel):
    formats: list[ResearchExportFormat] = Field(default_factory=lambda: [ResearchExportFormat.NATIVE])
    redaction_profile: ExportRedactionProfile = ExportRedactionProfile.RESEARCH_REDACTED


class DatasetQualityMetric(BaseModel):
    name: str
    value: float = 0.0
    note: str | None = None


class DatasetEpisodeEntry(BaseModel):
    entry_id: str = Field(default_factory=lambda: str(uuid4()))
    episode_id: str
    source_ref: str
    split: DatasetSplitRecord
    research_bundle_manifest: str | None = None
    redaction_profile: ExportRedactionProfile = ExportRedactionProfile.RESEARCH_REDACTED
    dataset_membership: EpisodeDatasetMembership | None = None
    benchmark_labels: list[str] = Field(default_factory=list)
    sensitive_content_flags: list[SensitiveContentFlag] = Field(default_factory=list)
    quality_metrics: list[DatasetQualityMetric] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class DatasetManifestV1(BaseModel):
    dataset_id: str = Field(default_factory=lambda: str(uuid4()))
    schema_version: str = "blink_dataset_manifest/v1"
    name: str
    exported_at: datetime = Field(default_factory=utc_now)
    redaction_profile: ExportRedactionProfile = ExportRedactionProfile.RESEARCH_REDACTED
    artifact_dir: str | None = None
    artifact_files: dict[str, str] = Field(default_factory=dict)
    episode_count: int = 0
    split_counts: dict[str, int] = Field(default_factory=dict)
    entries: list[DatasetEpisodeEntry] = Field(default_factory=list)
    quality_metrics: list[DatasetQualityMetric] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class DatasetManifestListResponse(BaseModel):
    items: list[DatasetManifestV1] = Field(default_factory=list)


class DatasetExportRequest(BaseModel):
    name: str = "blink_dataset"
    episode_ids: list[str] = Field(default_factory=list)
    redaction_profile: ExportRedactionProfile = ExportRedactionProfile.RESEARCH_REDACTED
    notes: list[str] = Field(default_factory=list)


class ResearchBundleManifest(BaseModel):
    bundle_id: str = Field(default_factory=lambda: str(uuid4()))
    schema_version: str = "blink_research_bundle/v1"
    episode_id: str
    source_episode_schema_version: str = "blink_episode/v2"
    exporter_version: str = "blink_research_bridge/v2"
    exported_at: datetime = Field(default_factory=utc_now)
    split: DatasetSplitRecord
    redaction_profile: ExportRedactionProfile = ExportRedactionProfile.RESEARCH_REDACTED
    redaction_state: RedactionState = RedactionState.REDACTED
    sensitive_content_flags: list[SensitiveContentFlag] = Field(default_factory=list)
    dataset_memberships: list[EpisodeDatasetMembership] = Field(default_factory=list)
    artifact_dir: str | None = None
    artifact_files: dict[str, str] = Field(default_factory=dict)
    adapter_exports: dict[str, str] = Field(default_factory=dict)
    adapter_export_status: dict[str, dict[str, Any]] = Field(default_factory=dict)
    linked_action_bundles: list[str] = Field(default_factory=list)
    linked_action_replays: list[str] = Field(default_factory=list)
    provenance: dict[str, Any] = Field(default_factory=dict)
    evidence_refs: list[str] = Field(default_factory=list)
    quality_metrics: list[DatasetQualityMetric] = Field(default_factory=list)
    action_quality_metrics: list[DatasetQualityMetric] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class BenchmarkEvidencePackV1(BaseModel):
    pack_id: str = Field(default_factory=lambda: str(uuid4()))
    schema_version: str = "blink_benchmark_evidence_pack/v1"
    benchmark_run_id: str
    episode_ids: list[str] = Field(default_factory=list)
    replay_ids: list[str] = Field(default_factory=list)
    planner_targets: list[dict[str, str]] = Field(default_factory=list)
    benchmark_families: list[str] = Field(default_factory=list)
    redaction_profile: ExportRedactionProfile = ExportRedactionProfile.RESEARCH_REDACTED
    environment_fingerprint: dict[str, Any] = Field(default_factory=dict)
    artifact_dir: str | None = None
    artifact_files: dict[str, str] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)


class BenchmarkEvidencePackListResponse(BaseModel):
    items: list[BenchmarkEvidencePackV1] = Field(default_factory=list)


class EpisodeResearchExportRecord(BaseModel):
    episode: EpisodeRecordV2
    manifest: ResearchBundleManifest


__all__ = [
    "BenchmarkEvidencePackListResponse",
    "BenchmarkEvidencePackV1",
    "DatasetEpisodeEntry",
    "DatasetExportRequest",
    "DatasetManifestListResponse",
    "DatasetManifestV1",
    "DatasetQualityMetric",
    "DatasetSplitRecord",
    "EpisodeResearchExportRecord",
    "PlannerCatalogResponse",
    "PlannerDescriptor",
    "PlannerDiffRecord",
    "PlannerInputRecord",
    "PlannerOutputRecord",
    "PlannerReplayRecord",
    "PlannerReplayRequest",
    "PlannerReplayStepRecord",
    "ResearchBundleManifest",
    "ResearchExportRequest",
]
