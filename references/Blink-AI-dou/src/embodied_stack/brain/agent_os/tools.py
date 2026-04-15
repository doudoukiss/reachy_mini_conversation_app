from __future__ import annotations

from dataclasses import dataclass
import logging
from pathlib import Path
import shutil
from time import perf_counter
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from pydantic import BaseModel, Field, ValidationError

from embodied_stack.action_plane.models import ActionInvocationContext, ActionInvocationResult
from embodied_stack.brain.memory_policy import MemoryPolicyService
from embodied_stack.brain.agent_os.aci import (
    capability_for_tool,
    default_confidence,
    default_provenance,
    normalize_capability_state,
    normalize_result_status,
    unsupported_browser_output,
)
from embodied_stack.body.semantics import (
    normalize_animation_name,
    normalize_expression_name,
    normalize_gaze_name,
    normalize_gesture_name,
)
from embodied_stack.brain.tool_protocol import ToolSpec
from embodied_stack.observability import log_event
from embodied_stack.persistence import write_json_atomic
from embodied_stack.config import Settings
from embodied_stack.shared.contracts import (
    ActionArtifactRecord,
    ActionInvocationOrigin,
    BrowserActionPreviewRecord,
    BrowserActionResultRecord,
    BrowserRequestedAction,
    BrowserSnapshotRecord,
    BrowserTargetCandidateRecord,
    BrowserTargetHintRecord,
    CompanionContextMode,
    EmbodiedWorldModel,
    EpisodicMemoryRecord,
    IncidentReasonCategory,
    IncidentStatus,
    IncidentTicketRecord,
    IncidentTimelineEventType,
    IncidentTimelineRecord,
    IncidentUrgency,
    PerceptionFactRecord,
    PerceptionObservationType,
    PerceptionSnapshotRecord,
    RobotCommand,
    RuntimeBackendStatus,
    ReminderRecord,
    ReminderStatus,
    SemanticMemoryRecord,
    SessionRecord,
    SessionStatus,
    ToolEffectClass,
    ToolLatencyClass,
    ToolPermissionClass,
    ToolSpecRecord,
    ToolValidationRecord,
    TypedToolCallRecord,
    ToolResultStatus,
    UserMemoryRecord,
    WorkflowRunActionResponseRecord,
    WorkflowStartRequestRecord,
    WorldState,
    MemoryRetrievalRecord,
    MemoryWriteReasonCode,
    utc_now,
)

from .action_policy import EmbodiedActionPolicy

if TYPE_CHECKING:
    from embodied_stack.action_plane import ActionPlaneGateway
    from embodied_stack.action_plane.workflows import WorkflowRuntime
    from embodied_stack.brain.memory import MemoryStore
    from embodied_stack.brain.tools import KnowledgeToolbox

logger = logging.getLogger(__name__)


class TextQueryToolInput(BaseModel):
    query: str


class SessionScopedToolInput(BaseModel):
    session_id: str | None = None


class VenueKnowledgeAnswer(BaseModel):
    tool_name: str
    answer_text: str
    source_refs: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class VenueKnowledgeToolOutput(BaseModel):
    matched: bool = False
    answers: list[VenueKnowledgeAnswer] = Field(default_factory=list)


class DeviceHealthItem(BaseModel):
    device_name: str
    status: str
    detail: str | None = None


class DeviceHealthSnapshotOutput(BaseModel):
    devices: list[DeviceHealthItem] = Field(default_factory=list)
    degraded_devices: list[str] = Field(default_factory=list)


class MemoryRetrievalHit(BaseModel):
    memory_id: str | None = None
    layer: str
    summary: str
    source_ref: str | None = None
    session_id: str | None = None
    confidence: float | None = None
    source_trace_ids: list[str] = Field(default_factory=list)
    ranking_reason: str | None = None
    ranking_score: float | None = None


class MemoryRetrievalToolOutput(BaseModel):
    session_summary: str | None = None
    working_summary: str | None = None
    profile_summary: str | None = None
    relationship_summary: str | None = None
    operator_notes: list[str] = Field(default_factory=list)
    remembered_facts: dict[str, str] = Field(default_factory=dict)
    remembered_preferences: dict[str, str] = Field(default_factory=dict)
    episodic_hits: list[MemoryRetrievalHit] = Field(default_factory=list)
    semantic_hits: list[MemoryRetrievalHit] = Field(default_factory=list)
    relationship_hits: list[MemoryRetrievalHit] = Field(default_factory=list)
    procedural_hits: list[MemoryRetrievalHit] = Field(default_factory=list)
    perception_facts: list[PerceptionFactRecord] = Field(default_factory=list)
    retrievals: list[MemoryRetrievalRecord] = Field(default_factory=list)


class MemoryStatusToolOutput(BaseModel):
    session_id: str
    user_id: str | None = None
    transcript_turn_count: int = 0
    conversation_summary: str | None = None
    session_memory_keys: list[str] = Field(default_factory=list)
    operator_note_count: int = 0
    episodic_memory_count: int = 0
    semantic_memory_count: int = 0
    profile_memory_available: bool = False
    open_reminder_count: int = 0
    note_count: int = 0
    session_digest_count: int = 0
    relationship_memory_available: bool = False
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
    procedural_memory_count: int = 0
    open_follow_ups: list[str] = Field(default_factory=list)


class SystemHealthToolOutput(BaseModel):
    runtime_mode: str
    body_driver_mode: str
    context_mode: str
    backend_profile: str
    text_backend: str | None = None
    vision_backend: str | None = None
    embedding_backend: str | None = None
    stt_backend: str | None = None
    tts_backend: str | None = None
    degraded_backends: list[str] = Field(default_factory=list)


class LocalNoteItem(BaseModel):
    note_id: str
    title: str
    content: str
    tags: list[str] = Field(default_factory=list)


class SessionDigestItem(BaseModel):
    digest_id: str
    summary: str
    open_follow_ups: list[str] = Field(default_factory=list)


class LocalFilesToolOutput(BaseModel):
    notes: list[LocalNoteItem] = Field(default_factory=list)
    digests: list[SessionDigestItem] = Field(default_factory=list)


class PersonalReminderItem(BaseModel):
    reminder_id: str
    reminder_text: str
    due_at: str | None = None
    due_state: str = "open"


class PersonalRemindersToolOutput(BaseModel):
    reminders: list[PersonalReminderItem] = Field(default_factory=list)
    due_count: int = 0


class TodayContextToolOutput(BaseModel):
    today_label: str
    open_reminder_count: int = 0
    note_count: int = 0
    latest_digest: str | None = None


class RecentSessionDigestToolOutput(BaseModel):
    summary: str | None = None
    open_follow_ups: list[str] = Field(default_factory=list)


class CaptureSceneToolOutput(BaseModel):
    scene_summary: str | None = None
    limited_awareness: bool = False
    provider_mode: str | None = None
    perception_tier: str | None = None
    freshness: str | None = None
    trigger_reason: str | None = None
    visible_text: list[str] = Field(default_factory=list)
    named_objects: list[str] = Field(default_factory=list)
    attention_target: str | None = None
    engagement_state: str | None = None
    uncertainty_markers: list[str] = Field(default_factory=list)
    device_awareness_constraints: list[str] = Field(default_factory=list)
    facts: list[PerceptionFactRecord] = Field(default_factory=list)


class WorldModelRuntimeToolOutput(BaseModel):
    social_runtime_mode: str
    scene_freshness: str
    engagement_state: str
    attention_target: str | None = None
    attention_rationale: str | None = None
    likely_speaker_participant_id: str | None = None
    environment_state: str
    uncertainty_markers: list[str] = Field(default_factory=list)
    device_awareness_constraints: list[str] = Field(default_factory=list)


class AudioTranscriptionToolInput(BaseModel):
    transcript_text: str | None = None
    source: str = "operator_console"


class AudioTranscriptionToolOutput(BaseModel):
    transcript_text: str | None = None
    transcription_backend: str = "pass_through"
    success: bool = True


class SpeechActionToolInput(BaseModel):
    text: str | None = None
    state: str | None = None


class SpeechActionToolOutput(BaseModel):
    success: bool = True
    state: str | None = None
    text: str | None = None


class MemoryWriteToolInput(BaseModel):
    key: str
    value: str
    scope: str = "session"
    reason_code: MemoryWriteReasonCode = MemoryWriteReasonCode.SESSION_CONTEXT


class MemoryWriteToolOutput(BaseModel):
    scope: str
    key: str
    value: str
    action_id: str | None = None
    memory_id: str | None = None
    persisted: bool = False


class MemoryPromotionToolInput(BaseModel):
    summary: str
    memory_kind: str = "fact"
    canonical_value: str | None = None
    scope: str = "semantic"
    reason_code: MemoryWriteReasonCode = MemoryWriteReasonCode.CONVERSATION_TOPIC


class MemoryPromotionToolOutput(BaseModel):
    scope: str
    memory_id: str | None = None
    action_id: str | None = None
    promoted: bool = False


class CreateReminderToolInput(BaseModel):
    reminder_text: str
    due_at: str | None = None
    reason_code: MemoryWriteReasonCode = MemoryWriteReasonCode.CONVERSATION_TOPIC


class CreateReminderToolOutput(BaseModel):
    created: bool = False
    reminder_id: str | None = None
    reminder_text: str
    due_at: str | None = None
    status: str | None = None


class ListRemindersToolInput(BaseModel):
    status: str = ReminderStatus.OPEN.value
    limit: int = 10


class MarkReminderDoneToolInput(BaseModel):
    reminder_id: str
    status: str = ReminderStatus.DISMISSED.value


class MarkReminderDoneToolOutput(BaseModel):
    updated: bool = False
    reminder_id: str
    status: str
    reminder_text: str | None = None


class CreateNoteToolInput(BaseModel):
    title: str = "Untitled Note"
    content: str
    tags: list[str] = Field(default_factory=list)


class CreateNoteToolOutput(BaseModel):
    created: bool = False
    note_id: str | None = None
    title: str
    content: str
    tags: list[str] = Field(default_factory=list)


class AppendNoteToolInput(BaseModel):
    note_id: str
    content_append: str


class AppendNoteToolOutput(BaseModel):
    updated: bool = False
    note_id: str
    title: str | None = None
    content: str | None = None
    tags: list[str] = Field(default_factory=list)


class SearchNotesToolInput(BaseModel):
    query: str
    limit: int = 10


class SearchNotesToolOutput(BaseModel):
    notes: list[LocalNoteItem] = Field(default_factory=list)
    query: str | None = None


class ReadLocalFileToolInput(BaseModel):
    path: str
    max_chars: int = 20000


class ReadLocalFileToolOutput(BaseModel):
    path: str
    content: str
    truncated: bool = False
    size_bytes: int = 0


class StageLocalFileToolInput(BaseModel):
    path: str


class StageLocalFileToolOutput(BaseModel):
    staged: bool = False
    source_path: str
    staged_path: str | None = None


class ExportLocalBundleToolInput(BaseModel):
    paths: list[str] = Field(default_factory=list)
    label: str | None = None


class ExportedBundleFile(BaseModel):
    source_path: str
    bundle_path: str


class ExportLocalBundleToolOutput(BaseModel):
    exported: bool = False
    bundle_dir: str | None = None
    manifest_path: str | None = None
    file_count: int = 0
    files: list[ExportedBundleFile] = Field(default_factory=list)


class DraftCalendarEventToolInput(BaseModel):
    title: str
    start_at: str | None = None
    end_at: str | None = None
    location: str | None = None
    description: str | None = None


class DraftCalendarEventToolOutput(BaseModel):
    drafted: bool = False
    draft_path: str | None = None
    title: str
    start_at: str | None = None
    end_at: str | None = None
    location: str | None = None
    status: str | None = None


class ActionPlanToolInput(BaseModel):
    intent: str
    reply_text: str | None = None


class EmbodiedActionPreview(BaseModel):
    command_type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    semantic_name: str | None = None
    source_name: str | None = None
    driver_mode: str | None = None
    transport_mode: str | None = None
    preview_status: str | None = None


class ActionPlanToolOutput(BaseModel):
    command_types: list[str] = Field(default_factory=list)
    previews: list[EmbodiedActionPreview] = Field(default_factory=list)
    semantic_only: bool = True


class IncidentRequestToolInput(BaseModel):
    participant_summary: str
    note: str | None = None


class IncidentToolOutput(BaseModel):
    requested: bool = False
    incident_ticket_id: str | None = None
    status: str | None = None


class ConfirmationToolInput(BaseModel):
    prompt: str


class ConfirmationToolOutput(BaseModel):
    confirmation_required: bool = True
    prompt: str


class BrowserTaskToolInput(BaseModel):
    query: str
    target_url: str | None = None
    requested_action: BrowserRequestedAction | None = None
    target_hint: BrowserTargetHintRecord | None = None
    text_input: str | None = None


class BrowserTaskToolOutput(BaseModel):
    task: str | None = None
    requested_action: BrowserRequestedAction | None = None
    supported: bool = False
    configured: bool = False
    status: str = "unsupported"
    detail: str | None = None
    browser_session_id: str | None = None
    current_url: str | None = None
    page_title: str | None = None
    summary: str | None = None
    visible_text: str | None = None
    candidate_targets: list[BrowserTargetCandidateRecord] = Field(default_factory=list)
    preview_required: bool = False
    snapshot: BrowserSnapshotRecord | None = None
    preview: BrowserActionPreviewRecord | None = None
    result: BrowserActionResultRecord | None = None
    artifacts: list[ActionArtifactRecord] = Field(default_factory=list)


@dataclass(frozen=True)
class ToolRuntimeContext:
    session: SessionRecord
    context_mode: CompanionContextMode
    user_memory: UserMemoryRecord | None
    world_state: WorldState
    world_model: EmbodiedWorldModel
    latest_perception: PerceptionSnapshotRecord | None
    backend_status: list[RuntimeBackendStatus]
    backend_profile: str
    body_driver_mode: str
    body_transport_mode: str | None
    body_preview_status: str | None
    tool_invocations: list[Any]
    action_policy: EmbodiedActionPolicy
    run_id: str | None = None
    action_invocation_origin: ActionInvocationOrigin = ActionInvocationOrigin.USER_TURN
    action_gateway: "ActionPlaneGateway | None" = None
    workflow_runtime: "WorkflowRuntime | None" = None
    knowledge_tools: "KnowledgeToolbox | None" = None
    memory_store: "MemoryStore | None" = None
    workflow_run_id: str | None = None
    workflow_step_id: str | None = None
    action_idempotency_namespace: str | None = None


class AgentToolRegistry:
    def __init__(self) -> None:
        self._canonical_specs: dict[str, ToolSpec] = {}
        self._aliases: dict[str, str] = {}
        for spec in (
            ToolSpec(
                name="device_health_snapshot",
                family="device",
                category="system",
                capability_name=capability_for_tool("device_health_snapshot"),
                input_model=SessionScopedToolInput,
                output_model=DeviceHealthSnapshotOutput,
                handler=self._device_health_snapshot,
                latency_class=ToolLatencyClass.FAST,
                failure_modes=("device_unavailable",),
            ),
            ToolSpec(
                name="memory_status",
                family="memory",
                category="memory",
                capability_name=capability_for_tool("memory_status"),
                input_model=SessionScopedToolInput,
                output_model=MemoryStatusToolOutput,
                handler=self._memory_status,
                latency_class=ToolLatencyClass.LOCAL_IO,
            ),
            ToolSpec(
                name="system_health",
                family="system",
                category="system",
                capability_name=capability_for_tool("system_health"),
                input_model=SessionScopedToolInput,
                output_model=SystemHealthToolOutput,
                handler=self._system_health,
                latency_class=ToolLatencyClass.FAST,
                aliases=("runtime_status",),
            ),
            ToolSpec(
                name="search_memory",
                family="memory",
                category="memory",
                capability_name=capability_for_tool("search_memory"),
                input_model=TextQueryToolInput,
                output_model=MemoryRetrievalToolOutput,
                handler=self._search_memory,
                latency_class=ToolLatencyClass.LOCAL_IO,
                aliases=("memory_retrieval",),
            ),
            ToolSpec(
                name="search_venue_knowledge",
                family="knowledge",
                category="knowledge",
                capability_name=capability_for_tool("search_venue_knowledge"),
                input_model=TextQueryToolInput,
                output_model=VenueKnowledgeToolOutput,
                handler=self._search_venue_knowledge,
                latency_class=ToolLatencyClass.LOCAL_IO,
                aliases=("venue_knowledge",),
            ),
            ToolSpec(
                name="query_calendar",
                family="calendar",
                category="knowledge",
                capability_name=capability_for_tool("query_calendar"),
                input_model=TextQueryToolInput,
                output_model=VenueKnowledgeToolOutput,
                handler=self._query_calendar,
                latency_class=ToolLatencyClass.LOCAL_IO,
            ),
            ToolSpec(
                name="draft_calendar_event",
                family="calendar",
                category="action",
                capability_name=capability_for_tool("draft_calendar_event"),
                input_model=DraftCalendarEventToolInput,
                output_model=DraftCalendarEventToolOutput,
                handler=self._draft_calendar_event,
                permission_class=ToolPermissionClass.EFFECTFUL,
                latency_class=ToolLatencyClass.LOCAL_IO,
                effect_class=ToolEffectClass.STATE_MUTATION,
                checkpoint_policy="before_and_after",
            ),
            ToolSpec(
                name="query_local_files",
                family="local_files",
                category="memory",
                capability_name=capability_for_tool("query_local_files"),
                input_model=TextQueryToolInput,
                output_model=LocalFilesToolOutput,
                handler=self._query_local_files,
                latency_class=ToolLatencyClass.LOCAL_IO,
            ),
            ToolSpec(
                name="body_preview",
                family="body",
                category="action",
                capability_name=capability_for_tool("body_preview"),
                input_model=ActionPlanToolInput,
                output_model=ActionPlanToolOutput,
                handler=self._body_preview,
                latency_class=ToolLatencyClass.FAST,
                aliases=("embodied_actions",),
            ),
            ToolSpec(
                name="capture_scene",
                family="perception",
                category="perception",
                capability_name=capability_for_tool("capture_scene"),
                input_model=SessionScopedToolInput,
                output_model=CaptureSceneToolOutput,
                handler=self._capture_scene,
                latency_class=ToolLatencyClass.LOCAL_IO,
                failure_modes=("limited_awareness",),
            ),
            ToolSpec(
                name="world_model_runtime",
                family="perception",
                category="perception",
                capability_name=capability_for_tool("world_model_runtime"),
                input_model=SessionScopedToolInput,
                output_model=WorldModelRuntimeToolOutput,
                handler=self._world_model_runtime,
                latency_class=ToolLatencyClass.FAST,
            ),
            ToolSpec(
                name="transcribe_audio",
                family="voice",
                category="voice",
                capability_name=capability_for_tool("transcribe_audio"),
                input_model=AudioTranscriptionToolInput,
                output_model=AudioTranscriptionToolOutput,
                handler=self._transcribe_audio,
                latency_class=ToolLatencyClass.LOCAL_IO,
                failure_modes=("no_audio_available",),
            ),
            ToolSpec(
                name="speak_text",
                family="voice",
                category="action",
                capability_name=capability_for_tool("speak_text"),
                input_model=SpeechActionToolInput,
                output_model=SpeechActionToolOutput,
                handler=self._speak_text,
                permission_class=ToolPermissionClass.EFFECTFUL,
                latency_class=ToolLatencyClass.HUMAN_LOOP,
                effect_class=ToolEffectClass.SPEECH_OUTPUT,
                failure_modes=("voice_output_unavailable",),
                confirmation_required=False,
                checkpoint_policy="before_and_after",
            ),
            ToolSpec(
                name="interrupt_speech",
                family="voice",
                category="action",
                capability_name=capability_for_tool("interrupt_speech"),
                input_model=SpeechActionToolInput,
                output_model=SpeechActionToolOutput,
                handler=self._interrupt_speech,
                permission_class=ToolPermissionClass.EFFECTFUL,
                latency_class=ToolLatencyClass.FAST,
                effect_class=ToolEffectClass.SPEECH_OUTPUT,
                checkpoint_policy="before_and_after",
            ),
            ToolSpec(
                name="set_listening_state",
                family="voice",
                category="action",
                capability_name=capability_for_tool("set_listening_state"),
                input_model=SpeechActionToolInput,
                output_model=SpeechActionToolOutput,
                handler=self._set_listening_state,
                permission_class=ToolPermissionClass.EFFECTFUL,
                latency_class=ToolLatencyClass.FAST,
                effect_class=ToolEffectClass.STATE_MUTATION,
                checkpoint_policy="before_and_after",
            ),
            ToolSpec(
                name="write_memory",
                family="memory",
                category="memory",
                capability_name=capability_for_tool("write_memory"),
                input_model=MemoryWriteToolInput,
                output_model=MemoryWriteToolOutput,
                handler=self._write_memory,
                permission_class=ToolPermissionClass.EFFECTFUL,
                latency_class=ToolLatencyClass.LOCAL_IO,
                effect_class=ToolEffectClass.STATE_MUTATION,
                checkpoint_policy="before_and_after",
            ),
            ToolSpec(
                name="create_reminder",
                family="reminders",
                category="action",
                capability_name=capability_for_tool("create_reminder"),
                input_model=CreateReminderToolInput,
                output_model=CreateReminderToolOutput,
                handler=self._create_reminder,
                permission_class=ToolPermissionClass.EFFECTFUL,
                latency_class=ToolLatencyClass.LOCAL_IO,
                effect_class=ToolEffectClass.STATE_MUTATION,
                checkpoint_policy="before_and_after",
            ),
            ToolSpec(
                name="list_reminders",
                family="reminders",
                category="memory",
                capability_name=capability_for_tool("list_reminders"),
                input_model=ListRemindersToolInput,
                output_model=PersonalRemindersToolOutput,
                handler=self._list_reminders,
                latency_class=ToolLatencyClass.LOCAL_IO,
            ),
            ToolSpec(
                name="mark_reminder_done",
                family="reminders",
                category="action",
                capability_name=capability_for_tool("mark_reminder_done"),
                input_model=MarkReminderDoneToolInput,
                output_model=MarkReminderDoneToolOutput,
                handler=self._mark_reminder_done,
                permission_class=ToolPermissionClass.EFFECTFUL,
                latency_class=ToolLatencyClass.LOCAL_IO,
                effect_class=ToolEffectClass.STATE_MUTATION,
                checkpoint_policy="before_and_after",
            ),
            ToolSpec(
                name="create_note",
                family="notes",
                category="action",
                capability_name=capability_for_tool("create_note"),
                input_model=CreateNoteToolInput,
                output_model=CreateNoteToolOutput,
                handler=self._create_note,
                permission_class=ToolPermissionClass.EFFECTFUL,
                latency_class=ToolLatencyClass.LOCAL_IO,
                effect_class=ToolEffectClass.STATE_MUTATION,
                checkpoint_policy="before_and_after",
            ),
            ToolSpec(
                name="append_note",
                family="notes",
                category="action",
                capability_name=capability_for_tool("append_note"),
                input_model=AppendNoteToolInput,
                output_model=AppendNoteToolOutput,
                handler=self._append_note,
                permission_class=ToolPermissionClass.EFFECTFUL,
                latency_class=ToolLatencyClass.LOCAL_IO,
                effect_class=ToolEffectClass.STATE_MUTATION,
                checkpoint_policy="before_and_after",
            ),
            ToolSpec(
                name="search_notes",
                family="notes",
                category="memory",
                capability_name=capability_for_tool("search_notes"),
                input_model=SearchNotesToolInput,
                output_model=SearchNotesToolOutput,
                handler=self._search_notes,
                latency_class=ToolLatencyClass.LOCAL_IO,
            ),
            ToolSpec(
                name="read_local_file",
                family="local_files",
                category="knowledge",
                capability_name=capability_for_tool("read_local_file"),
                input_model=ReadLocalFileToolInput,
                output_model=ReadLocalFileToolOutput,
                handler=self._read_local_file,
                latency_class=ToolLatencyClass.LOCAL_IO,
            ),
            ToolSpec(
                name="stage_local_file",
                family="local_files",
                category="action",
                capability_name=capability_for_tool("stage_local_file"),
                input_model=StageLocalFileToolInput,
                output_model=StageLocalFileToolOutput,
                handler=self._stage_local_file,
                permission_class=ToolPermissionClass.EFFECTFUL,
                latency_class=ToolLatencyClass.LOCAL_IO,
                effect_class=ToolEffectClass.STATE_MUTATION,
                checkpoint_policy="before_and_after",
            ),
            ToolSpec(
                name="export_local_bundle",
                family="local_files",
                category="action",
                capability_name=capability_for_tool("export_local_bundle"),
                input_model=ExportLocalBundleToolInput,
                output_model=ExportLocalBundleToolOutput,
                handler=self._export_local_bundle,
                permission_class=ToolPermissionClass.EFFECTFUL,
                latency_class=ToolLatencyClass.LOCAL_IO,
                effect_class=ToolEffectClass.STATE_MUTATION,
                checkpoint_policy="before_and_after",
            ),
            ToolSpec(
                name="promote_memory",
                family="memory",
                category="memory",
                capability_name=capability_for_tool("promote_memory"),
                input_model=MemoryPromotionToolInput,
                output_model=MemoryPromotionToolOutput,
                handler=self._promote_memory,
                permission_class=ToolPermissionClass.EFFECTFUL,
                latency_class=ToolLatencyClass.LOCAL_IO,
                effect_class=ToolEffectClass.STATE_MUTATION,
                checkpoint_policy="before_and_after",
            ),
            ToolSpec(
                name="start_workflow",
                family="workflow",
                category="action",
                capability_name=capability_for_tool("start_workflow"),
                input_model=WorkflowStartRequestRecord,
                output_model=WorkflowRunActionResponseRecord,
                handler=self._start_workflow,
                permission_class=ToolPermissionClass.EFFECTFUL,
                latency_class=ToolLatencyClass.LOCAL_IO,
                effect_class=ToolEffectClass.STATE_MUTATION,
                checkpoint_policy="before_and_after",
            ),
            ToolSpec(
                name="body_command",
                family="body",
                category="action",
                capability_name=capability_for_tool("body_command"),
                input_model=ActionPlanToolInput,
                output_model=ActionPlanToolOutput,
                handler=self._body_command,
                permission_class=ToolPermissionClass.EFFECTFUL,
                latency_class=ToolLatencyClass.FAST,
                effect_class=ToolEffectClass.EMBODIMENT_COMMAND,
                checkpoint_policy="before_and_after",
            ),
            ToolSpec(
                name="body_safe_idle",
                family="body",
                category="action",
                capability_name=capability_for_tool("body_safe_idle"),
                input_model=ActionPlanToolInput,
                output_model=ActionPlanToolOutput,
                handler=self._body_safe_idle,
                permission_class=ToolPermissionClass.EFFECTFUL,
                latency_class=ToolLatencyClass.FAST,
                effect_class=ToolEffectClass.EMBODIMENT_COMMAND,
                checkpoint_policy="before_and_after",
            ),
            ToolSpec(
                name="request_operator_help",
                family="handoff",
                category="action",
                capability_name=capability_for_tool("request_operator_help"),
                input_model=IncidentRequestToolInput,
                output_model=IncidentToolOutput,
                handler=self._request_operator_help,
                permission_class=ToolPermissionClass.OPERATOR_SENSITIVE,
                latency_class=ToolLatencyClass.HUMAN_LOOP,
                effect_class=ToolEffectClass.OPERATOR_HANDOFF,
                confirmation_required=True,
                checkpoint_policy="before_and_after",
            ),
            ToolSpec(
                name="log_incident",
                family="handoff",
                category="action",
                capability_name=capability_for_tool("log_incident"),
                input_model=IncidentRequestToolInput,
                output_model=IncidentToolOutput,
                handler=self._log_incident,
                permission_class=ToolPermissionClass.OPERATOR_SENSITIVE,
                latency_class=ToolLatencyClass.LOCAL_IO,
                effect_class=ToolEffectClass.OPERATOR_HANDOFF,
                checkpoint_policy="before_and_after",
            ),
            ToolSpec(
                name="require_confirmation",
                family="safety",
                category="system",
                capability_name=capability_for_tool("require_confirmation"),
                input_model=ConfirmationToolInput,
                output_model=ConfirmationToolOutput,
                handler=self._require_confirmation,
                permission_class=ToolPermissionClass.OPERATOR_SENSITIVE,
                latency_class=ToolLatencyClass.HUMAN_LOOP,
                effect_class=ToolEffectClass.CONFIRMATION_GATE,
                confirmation_required=True,
                checkpoint_policy="before_and_after",
            ),
            ToolSpec(
                name="local_notes",
                family="local_files",
                category="memory",
                capability_name=capability_for_tool("local_notes"),
                input_model=TextQueryToolInput,
                output_model=LocalFilesToolOutput,
                handler=self._query_local_files,
                latency_class=ToolLatencyClass.LOCAL_IO,
            ),
            ToolSpec(
                name="personal_reminders",
                family="memory",
                category="memory",
                capability_name=capability_for_tool("personal_reminders"),
                input_model=TextQueryToolInput,
                output_model=PersonalRemindersToolOutput,
                handler=self._personal_reminders,
                latency_class=ToolLatencyClass.LOCAL_IO,
            ),
            ToolSpec(
                name="today_context",
                family="system",
                category="system",
                capability_name=capability_for_tool("today_context"),
                input_model=SessionScopedToolInput,
                output_model=TodayContextToolOutput,
                handler=self._today_context,
                latency_class=ToolLatencyClass.LOCAL_IO,
            ),
            ToolSpec(
                name="recent_session_digest",
                family="memory",
                category="memory",
                capability_name=capability_for_tool("recent_session_digest"),
                input_model=SessionScopedToolInput,
                output_model=RecentSessionDigestToolOutput,
                handler=self._recent_session_digest,
                latency_class=ToolLatencyClass.LOCAL_IO,
            ),
            ToolSpec(
                name="browser_task",
                family="browser",
                category="action",
                capability_name=capability_for_tool("browser_task"),
                input_model=BrowserTaskToolInput,
                output_model=BrowserTaskToolOutput,
                handler=self._browser_task,
                permission_class=ToolPermissionClass.OPERATOR_SENSITIVE,
                latency_class=ToolLatencyClass.HUMAN_LOOP,
                effect_class=ToolEffectClass.READ_ONLY,
                failure_modes=("browser_task_not_configured", "browser_task_unsupported"),
            ),
        ):
            self._canonical_specs[spec.name] = spec
            for alias in spec.aliases:
                self._aliases[alias] = spec.name

    def list_tool_names(self) -> list[str]:
        return list(self._canonical_specs)

    def list_tool_specs(self) -> list[ToolSpecRecord]:
        return [spec.to_record() for spec in self._canonical_specs.values()]

    def resolve_spec(self, tool_name: str) -> ToolSpec:
        canonical = self._aliases.get(tool_name, tool_name)
        return self._canonical_specs[canonical]

    def invoke(
        self,
        tool_name: str,
        payload: dict[str, Any],
        *,
        context: ToolRuntimeContext,
        allowed_tools: set[str] | None = None,
        active_skill_name: str | None = None,
        active_subagent_name: str | None = None,
    ) -> tuple[TypedToolCallRecord, BaseModel | None]:
        spec = self.resolve_spec(tool_name)
        if allowed_tools is not None and spec.name not in allowed_tools:
            now = utc_now()
            log_event(
                logger,
                logging.WARNING,
                "tool_invocation_blocked",
                session_id=context.session.session_id,
                tool_name=spec.name,
                active_skill=active_skill_name,
                active_subagent=active_subagent_name,
            )
            return (
                TypedToolCallRecord(
                    tool_name=spec.name,
                    requested_tool_name=tool_name,
                    version=spec.version,
                    family=spec.family,
                    capability_name=spec.capability_name,
                    category=spec.category,
                    input_payload=payload,
                    success=False,
                    summary="tool_not_allowed",
                    result_status=normalize_result_status(success=False, blocked=True),
                    permission_class=spec.permission_class,
                    latency_class=spec.latency_class,
                    effect_class=spec.effect_class,
                    confirmation_required=spec.confirmation_required,
                    failure_mode="tool_not_allowed",
                    error_code="tool_not_allowed",
                    error_detail="tool_not_allowed_for_skill_or_subagent",
                    capability_state=normalize_capability_state(success=False, blocked=True),
                    checkpoint_policy=spec.checkpoint_policy,
                    observability_policy=list(spec.observability_policy),
                    started_at=now,
                    finished_at=now,
                    latency_ms=0.0,
                    duration_ms=0.0,
                    validation=ToolValidationRecord(
                        schema_valid=True,
                        output_valid=False,
                        detail="tool_not_allowed_for_skill_or_subagent",
                        errors=[
                            f"skill={active_skill_name or 'none'}",
                            f"subagent={active_subagent_name or 'none'}",
                        ],
                    ),
                ),
                None,
            )

        started_at = utc_now()
        started_clock = perf_counter()
        try:
            input_model = spec.input_model.model_validate(payload)
            schema_valid = True
            input_errors: list[str] = []
        except ValidationError as exc:
            input_model = None
            schema_valid = False
            input_errors = [item["msg"] for item in exc.errors()]

        if input_model is None:
            finished_at = utc_now()
            record = TypedToolCallRecord(
                tool_name=spec.name,
                requested_tool_name=tool_name,
                version=spec.version,
                family=spec.family,
                capability_name=spec.capability_name,
                category=spec.category,
                input_payload=payload,
                success=False,
                summary="input_validation_failed",
                result_status=normalize_result_status(success=False, failure_mode="tool_input_invalid"),
                permission_class=spec.permission_class,
                latency_class=spec.latency_class,
                effect_class=spec.effect_class,
                confirmation_required=spec.confirmation_required,
                failure_mode="tool_input_invalid",
                error_code="tool_input_invalid",
                error_detail="tool_input_invalid",
                capability_state=normalize_capability_state(success=False),
                checkpoint_policy=spec.checkpoint_policy,
                observability_policy=list(spec.observability_policy),
                started_at=started_at,
                finished_at=finished_at,
                latency_ms=round((perf_counter() - started_clock) * 1000.0, 2),
                duration_ms=round((perf_counter() - started_clock) * 1000.0, 2),
                validation=ToolValidationRecord(
                    schema_valid=False,
                    output_valid=False,
                    detail="tool_input_invalid",
                    errors=input_errors,
                ),
            )
            log_event(
                logger,
                logging.WARNING,
                "tool_input_invalid",
                session_id=context.session.session_id,
                tool_name=spec.name,
                duration_ms=record.duration_ms,
            )
            return record, None

        action_result: ActionInvocationResult | None = None
        try:
            if context.action_gateway is not None and context.action_gateway.is_routed_tool(spec.name):
                action_result = context.action_gateway.invoke(
                    tool_name=spec.name,
                    requested_tool_name=tool_name,
                    input_model=input_model,
                    handler_context=context,
                    invocation=ActionInvocationContext(
                        session_id=context.session.session_id,
                        run_id=context.run_id,
                        workflow_run_id=context.workflow_run_id,
                        workflow_step_id=context.workflow_step_id,
                        context_mode=context.context_mode.value,
                        body_mode=context.body_driver_mode,
                        invocation_origin=context.action_invocation_origin,
                    ),
                    replay_nonce=context.action_idempotency_namespace,
                )
                raw_output = action_result.output_model
            else:
                raw_output = spec.handler(input_model, context)
        except Exception as exc:
            logger.exception("tool_runtime_error")
            finished_at = utc_now()
            duration_ms = round((perf_counter() - started_clock) * 1000.0, 2)
            detail = f"{exc.__class__.__name__}:{exc}"
            record = TypedToolCallRecord(
                tool_name=spec.name,
                requested_tool_name=tool_name,
                version=spec.version,
                family=spec.family,
                capability_name=spec.capability_name,
                category=spec.category,
                input_payload=input_model.model_dump(mode="json"),
                success=False,
                summary="tool_runtime_error",
                result_status=normalize_result_status(success=False, failure_mode="tool_runtime_error"),
                permission_class=spec.permission_class,
                latency_class=spec.latency_class,
                effect_class=spec.effect_class,
                confirmation_required=spec.confirmation_required,
                failure_mode="tool_runtime_error",
                error_code="tool_runtime_error",
                error_detail=detail,
                capability_state=normalize_capability_state(success=False),
                checkpoint_policy=spec.checkpoint_policy,
                observability_policy=list(spec.observability_policy),
                started_at=started_at,
                finished_at=finished_at,
                latency_ms=duration_ms,
                duration_ms=duration_ms,
                validation=ToolValidationRecord(
                    schema_valid=True,
                    output_valid=False,
                    detail="tool_runtime_error",
                    errors=[detail],
                ),
                workflow_run_id=context.workflow_run_id,
                workflow_step_id=context.workflow_step_id,
            )
            log_event(
                logger,
                logging.ERROR,
                "tool_runtime_error",
                session_id=context.session.session_id,
                tool_name=spec.name,
                duration_ms=duration_ms,
            )
            return record, None
        output_valid = True
        output_errors: list[str] = []
        try:
            if isinstance(raw_output, BaseModel):
                output_model = spec.output_model.model_validate(raw_output.model_dump(mode="json"))
            else:
                output_model = spec.output_model.model_validate(raw_output)
        except ValidationError as exc:
            output_model = None
            output_valid = False
            output_errors = [item["msg"] for item in exc.errors()]

        finished_at = utc_now()
        duration_ms = round((perf_counter() - started_clock) * 1000.0, 2)
        if output_model is None:
            record = TypedToolCallRecord(
                tool_name=spec.name,
                requested_tool_name=tool_name,
                version=spec.version,
                family=spec.family,
                capability_name=spec.capability_name,
                category=spec.category,
                input_payload=input_model.model_dump(mode="json"),
                success=False,
                summary="output_validation_failed",
                result_status=normalize_result_status(success=False, failure_mode="tool_output_invalid"),
                permission_class=spec.permission_class,
                latency_class=spec.latency_class,
                effect_class=spec.effect_class,
                confirmation_required=spec.confirmation_required,
                failure_mode="tool_output_invalid",
                error_code="tool_output_invalid",
                error_detail="tool_output_invalid",
                capability_state=normalize_capability_state(success=False),
                checkpoint_policy=spec.checkpoint_policy,
                observability_policy=list(spec.observability_policy),
                started_at=started_at,
                finished_at=finished_at,
                latency_ms=duration_ms,
                duration_ms=duration_ms,
                validation=ToolValidationRecord(
                    schema_valid=True,
                    output_valid=False,
                    detail="tool_output_invalid",
                    errors=output_errors,
                ),
            )
            log_event(
                logger,
                logging.WARNING,
                "tool_output_invalid",
                session_id=context.session.session_id,
                tool_name=spec.name,
                duration_ms=duration_ms,
            )
            return record, None

        success = (
            action_result.success_override
            if action_result is not None and action_result.success_override is not None
            else self._tool_success_for_output(spec.name, output_model)
        )
        summary = (
            action_result.summary_override
            if action_result is not None and action_result.summary_override is not None
            else self._summary_for_output(spec.name, output_model)
        )
        output_error_code = self._error_code_for_output(spec.name, output_model)
        action_error_code = action_result.execution.error_code if action_result is not None else None
        error_code = output_error_code or action_error_code
        output_error_detail = self._error_detail_for_output(spec.name, output_model)
        action_error_detail = action_result.execution.error_detail if action_result is not None else None
        error_detail = output_error_detail or action_error_detail
        result_status = (
            action_result.result_status_override
            if action_result is not None and action_result.result_status_override is not None
            else normalize_result_status(
                success=success,
                unsupported=self._is_unsupported_output(spec.name, output_model),
                unconfigured=self._is_unconfigured_output(spec.name, output_model),
            )
        )
        capability_state = (
            action_result.capability_state_override
            if action_result is not None and action_result.capability_state_override is not None
            else self._capability_state_for_output(spec.name, output_model)
        )
        record = TypedToolCallRecord(
            tool_name=spec.name,
            requested_tool_name=tool_name,
            version=spec.version,
            family=spec.family,
            capability_name=spec.capability_name,
            category=spec.category,
            input_payload=input_model.model_dump(mode="json"),
            output_payload=output_model.model_dump(mode="json"),
            success=success,
            summary=summary,
            result_status=result_status,
            confidence=default_confidence(output_model),
            provenance=[
                *self._source_refs_for_output(spec.name, output_model),
                *default_provenance(output_model),
            ],
            fallback_used=self._fallback_used_for_output(spec.name, output_model),
            permission_class=spec.permission_class,
            latency_class=spec.latency_class,
            effect_class=spec.effect_class,
            confirmation_required=spec.confirmation_required,
            failure_mode=error_code if not success else None,
            error_code=error_code,
            error_detail=error_detail,
            capability_state=capability_state,
            checkpoint_policy=spec.checkpoint_policy,
            observability_policy=list(spec.observability_policy),
            started_at=started_at,
            finished_at=finished_at,
            latency_ms=duration_ms,
            duration_ms=duration_ms,
            validation=ToolValidationRecord(
                schema_valid=schema_valid,
                output_valid=output_valid,
                detail="tool_ok",
            ),
            source_refs=self._source_refs_for_output(spec.name, output_model),
            action_id=action_result.execution.action_id if action_result is not None else None,
            connector_id=action_result.execution.connector_id if action_result is not None else None,
            risk_class=action_result.execution.risk_class if action_result is not None else None,
            approval_state=action_result.execution.approval_state if action_result is not None else None,
            action_status=action_result.execution.status if action_result is not None else None,
            request_hash=action_result.execution.request_hash if action_result is not None else None,
            idempotency_key=action_result.execution.idempotency_key if action_result is not None else None,
            workflow_run_id=context.workflow_run_id,
            workflow_step_id=context.workflow_step_id,
            notes=self._action_notes(action_result),
        )
        log_event(
            logger,
            logging.INFO if record.success else logging.WARNING,
            "tool_invocation_completed",
            session_id=context.session.session_id,
            tool_name=spec.name,
            duration_ms=duration_ms,
            success=record.success,
            action_id=record.action_id,
        )
        return record, output_model

    def _device_health_snapshot(self, model: BaseModel, context: ToolRuntimeContext) -> BaseModel:
        del model
        backend_by_kind = {item.kind.value: item for item in context.backend_status}
        devices = [
            DeviceHealthItem(
                device_name="microphone",
                status=backend_by_kind.get("speech_to_text").status.value if backend_by_kind.get("speech_to_text") else "unavailable",
                detail=backend_by_kind.get("speech_to_text").detail if backend_by_kind.get("speech_to_text") else "speech_to_text_backend_missing",
            ),
            DeviceHealthItem(
                device_name="speaker",
                status=backend_by_kind.get("text_to_speech").status.value if backend_by_kind.get("text_to_speech") else "unavailable",
                detail=backend_by_kind.get("text_to_speech").detail if backend_by_kind.get("text_to_speech") else "text_to_speech_backend_missing",
            ),
            DeviceHealthItem(
                device_name="camera",
                status=backend_by_kind.get("vision_analysis").status.value if backend_by_kind.get("vision_analysis") else "unavailable",
                detail=(
                    backend_by_kind.get("vision_analysis").detail
                    if backend_by_kind.get("vision_analysis")
                    else "vision_backend_missing"
                ),
            ),
        ]
        degraded = [item.device_name for item in devices if item.status in {"degraded", "fallback_active", "unavailable"}]
        return DeviceHealthSnapshotOutput(devices=devices, degraded_devices=degraded)

    def _search_venue_knowledge(self, model: BaseModel, context: ToolRuntimeContext) -> BaseModel:
        del model
        answers: list[VenueKnowledgeAnswer] = []
        for item in context.tool_invocations:
            if not getattr(item, "answer_text", None):
                continue
            source_refs = []
            metadata = getattr(item, "metadata", {}) or {}
            if isinstance(metadata.get("source_refs"), list):
                source_refs = [str(value) for value in metadata["source_refs"]]
            answers.append(
                VenueKnowledgeAnswer(
                    tool_name=item.tool_name,
                    answer_text=item.answer_text,
                    source_refs=source_refs,
                    notes=list(item.notes),
                )
            )
        return VenueKnowledgeToolOutput(matched=bool(answers), answers=answers)

    def _query_calendar(self, model: BaseModel, context: ToolRuntimeContext) -> BaseModel:
        venue_knowledge = getattr(context.knowledge_tools, "venue_knowledge", None) if context.knowledge_tools is not None else None
        result = venue_knowledge.lookup_events(model.query) if venue_knowledge is not None else None
        if result is None:
            return VenueKnowledgeToolOutput(matched=False, answers=[])
        return VenueKnowledgeToolOutput(
            matched=True,
            answers=[
                VenueKnowledgeAnswer(
                    tool_name="query_calendar",
                    answer_text=result.answer_text,
                    source_refs=list(result.metadata.get("source_refs", [])),
                    notes=list(result.notes),
                )
            ],
        )

    def _search_memory(self, model: BaseModel, context: ToolRuntimeContext) -> BaseModel:
        memory_context = (
            context.knowledge_tools.build_memory_context(
                model.query,
                session=context.session,
                user_memory=context.user_memory,
                world_model=context.world_model,
                latest_perception=context.latest_perception,
            )
            if context.knowledge_tools is not None
            else None
        )
        episodic_hits = [
            MemoryRetrievalHit(
                memory_id=item.memory_id,
                layer="episodic",
                summary=item.summary,
                source_ref=(item.source_refs[0] if item.source_refs else None),
                session_id=item.session_id,
                source_trace_ids=list(item.source_trace_ids),
                ranking_reason="episodic_keyword_match",
                ranking_score=1.0,
            )
            for item in (memory_context.episodic_hits if memory_context is not None else [])
        ]
        semantic_hits = [
            MemoryRetrievalHit(
                memory_id=item.memory_id,
                layer="semantic",
                summary=item.summary,
                source_ref=(item.source_refs[0] if item.source_refs else None),
                session_id=item.session_id,
                confidence=item.confidence,
                source_trace_ids=list(item.source_trace_ids),
                ranking_reason="semantic_memory_match",
                ranking_score=item.confidence,
            )
            for item in (memory_context.semantic_hits if memory_context is not None else [])
        ]
        relationship_hits = [
            MemoryRetrievalHit(
                memory_id=item.memory_id,
                layer="relationship",
                summary=item.summary,
                source_ref=item.source_ref,
                ranking_reason=item.ranking_reason,
                ranking_score=item.ranking_score,
            )
            for item in (memory_context.relationship_hits if memory_context is not None else [])
        ]
        procedural_hits = [
            MemoryRetrievalHit(
                memory_id=item.procedure_id,
                layer="procedural",
                summary=item.summary,
                source_ref=(item.source_refs[0] if item.source_refs else None),
                session_id=item.session_id,
                confidence=item.confidence,
                source_trace_ids=list(item.source_trace_ids),
                ranking_reason="procedural_match",
                ranking_score=item.confidence or 1.0,
            )
            for item in (memory_context.procedural_hits if memory_context is not None else [])
        ]
        retrievals: list[MemoryRetrievalRecord] = []
        if context.user_memory is not None and memory_context is not None and memory_context.profile_summary:
            retrievals.append(
                MemoryRetrievalRecord(
                    query_text=model.query,
                    backend="profile_scan",
                    session_id=context.session.session_id,
                    user_id=context.user_memory.user_id,
                    selected_candidates=[],
                    used_in_reply=True,
                    notes=["search_memory_profile_scan"],
                )
            )
        retrievals.append(
            MemoryRetrievalRecord(
                query_text=model.query,
                backend="episodic_keyword",
                session_id=context.session.session_id,
                user_id=context.user_memory.user_id if context.user_memory is not None else None,
                selected_candidates=[
                    {
                        "memory_id": hit.memory_id,
                        "layer": "episodic",
                        "summary": hit.summary,
                        "reason": hit.ranking_reason,
                        "score": hit.ranking_score,
                        "source_refs": [hit.source_ref] if hit.source_ref else [],
                        "session_id": hit.session_id,
                    }
                    for hit in episodic_hits
                ],
                miss_reason=(None if episodic_hits else "no_episodic_match"),
                used_in_reply=bool(episodic_hits),
                notes=["search_memory_episodic_keyword"],
            )
        )
        retrievals.append(
            MemoryRetrievalRecord(
                query_text=model.query,
                backend="semantic_vector",
                session_id=context.session.session_id,
                user_id=context.user_memory.user_id if context.user_memory is not None else None,
                selected_candidates=[
                    {
                        "memory_id": hit.memory_id,
                        "layer": "semantic",
                        "summary": hit.summary,
                        "reason": hit.ranking_reason,
                        "score": hit.ranking_score,
                        "source_refs": [hit.source_ref] if hit.source_ref else [],
                        "session_id": hit.session_id,
                    }
                    for hit in semantic_hits
                ],
                miss_reason=(None if semantic_hits else "no_semantic_match"),
                used_in_reply=bool(semantic_hits),
                notes=["search_memory_semantic_vector"],
            )
        )
        if memory_context is not None and (memory_context.relationship_summary or relationship_hits):
            retrievals.append(
                MemoryRetrievalRecord(
                    query_text=model.query,
                    backend="relationship_runtime",
                    session_id=context.session.session_id,
                    user_id=context.user_memory.user_id if context.user_memory is not None else None,
                    selected_candidates=[
                        {
                            "memory_id": hit.memory_id,
                            "layer": "relationship",
                            "summary": hit.summary,
                            "reason": hit.ranking_reason,
                            "score": hit.ranking_score,
                            "source_refs": [hit.source_ref] if hit.source_ref else [],
                        }
                        for hit in relationship_hits
                    ],
                    miss_reason=(None if relationship_hits or memory_context.relationship_summary else "no_relationship_match"),
                    used_in_reply=bool(relationship_hits or memory_context.relationship_summary),
                    notes=["search_memory_relationship_runtime"],
                )
            )
        if procedural_hits:
            retrievals.append(
                MemoryRetrievalRecord(
                    query_text=model.query,
                    backend="procedural_match",
                    session_id=context.session.session_id,
                    user_id=context.user_memory.user_id if context.user_memory is not None else None,
                    selected_candidates=[
                        {
                            "memory_id": hit.memory_id,
                            "layer": "procedural",
                            "summary": hit.summary,
                            "reason": hit.ranking_reason,
                            "score": hit.ranking_score,
                            "source_refs": [hit.source_ref] if hit.source_ref else [],
                            "session_id": hit.session_id,
                        }
                        for hit in procedural_hits
                    ],
                    used_in_reply=True,
                    notes=["search_memory_procedural_match"],
                )
            )
        if memory_context is not None and memory_context.perception_facts:
            retrievals.append(
                MemoryRetrievalRecord(
                    query_text=model.query,
                    backend="perception_context",
                    session_id=context.session.session_id,
                    user_id=context.user_memory.user_id if context.user_memory is not None else None,
                    selected_candidates=[
                        {
                            "memory_id": item.fact_id,
                            "summary": item.label or item.detail or item.fact_type,
                            "reason": "perception_fact",
                            "score": item.confidence,
                            "source_refs": [item.source_ref] if item.source_ref else [],
                        }
                        for item in memory_context.perception_facts
                    ],
                    used_in_reply=True,
                    notes=["search_memory_perception_context"],
                )
            )
        return MemoryRetrievalToolOutput(
            session_summary=context.session.conversation_summary,
            working_summary=memory_context.working_memory.conversation_summary if memory_context is not None else None,
            profile_summary=memory_context.profile_summary if memory_context is not None else None,
            relationship_summary=memory_context.relationship_summary if memory_context is not None else None,
            operator_notes=[note.text for note in context.session.operator_notes[-3:]],
            remembered_facts=(
                dict(context.user_memory.facts)
                if context.user_memory is not None and memory_context is not None and memory_context.profile_summary is not None
                else {}
            ),
            remembered_preferences=(
                dict(context.user_memory.preferences)
                if context.user_memory is not None and memory_context is not None and memory_context.profile_summary is not None
                else {}
            ),
            episodic_hits=episodic_hits,
            semantic_hits=semantic_hits,
            relationship_hits=relationship_hits,
            procedural_hits=procedural_hits,
            perception_facts=list(memory_context.perception_facts) if memory_context is not None else [],
            retrievals=retrievals,
        )

    def _memory_status(self, model: BaseModel, context: ToolRuntimeContext) -> BaseModel:
        del model
        memory_store = context.memory_store
        relationship_memory = (
            memory_store.get_relationship_memory(context.user_memory.user_id)
            if memory_store is not None and context.user_memory is not None
            else None
        )
        relationship_profile = (
            context.user_memory.relationship_profile
            if context.user_memory is not None
            else (relationship_memory.preferred_style if relationship_memory is not None else None)
        )
        if memory_store is None:
            episodic_items = []
            semantic_items = []
            procedural_items = []
            reminders = []
            notes = []
            digests = []
            continuity_reminders = []
            continuity_digests = []
        else:
            episodic_items = memory_store.list_episodic_memory(session_id=context.session.session_id, limit=100).items
            semantic_items = memory_store.list_semantic_memory(session_id=context.session.session_id, limit=100).items
            procedural_items = memory_store.list_procedural_memory(user_id=context.session.user_id, limit=100).items
            reminders = memory_store.list_reminders(
                session_id=context.session.session_id,
                user_id=context.session.user_id,
                status=ReminderStatus.OPEN,
                limit=100,
            ).items
            notes = memory_store.list_companion_notes(session_id=context.session.session_id, user_id=context.session.user_id, limit=100).items
            digests = memory_store.list_session_digests(session_id=context.session.session_id, user_id=context.session.user_id, limit=100).items
            continuity_reminders = (
                memory_store.list_reminders(user_id=context.session.user_id, status=ReminderStatus.OPEN, limit=100).items
                if context.session.user_id
                else reminders
            )
            continuity_digests = (
                memory_store.list_session_digests(user_id=context.session.user_id, limit=100).items
                if context.session.user_id
                else digests
            )
        latest_digest = continuity_digests[0] if continuity_digests else None
        open_follow_ups: list[str] = []
        for item in list(latest_digest.open_follow_ups) if latest_digest is not None else []:
            if item not in open_follow_ups:
                open_follow_ups.append(item)
        for reminder in continuity_reminders:
            if reminder.reminder_text not in open_follow_ups:
                open_follow_ups.append(reminder.reminder_text)
        open_practical_threads = []
        open_emotional_threads = []
        promise_count = 0
        recurring_topics = []
        familiarity = None
        if relationship_memory is not None and not relationship_memory.tombstoned:
            familiarity = relationship_memory.familiarity
            recurring_topics = [item.topic for item in relationship_memory.recurring_topics[:6]]
            open_practical_threads = [
                item.summary
                for item in relationship_memory.open_threads
                if item.status.value == "open" and item.kind.value == "practical"
            ][:6]
            open_emotional_threads = [
                item.summary
                for item in relationship_memory.open_threads
                if item.status.value == "open" and item.kind.value == "emotional"
            ][:4]
            promise_count = len([item for item in relationship_memory.promises if item.status.value == "open"])
            for item in [*open_practical_threads, *open_emotional_threads]:
                if item not in open_follow_ups:
                    open_follow_ups.append(item)
        return MemoryStatusToolOutput(
            session_id=context.session.session_id,
            user_id=context.session.user_id,
            transcript_turn_count=len(context.session.transcript),
            conversation_summary=context.session.conversation_summary,
            session_memory_keys=sorted(context.session.session_memory),
            operator_note_count=len(context.session.operator_notes),
            episodic_memory_count=len(episodic_items),
            semantic_memory_count=len(semantic_items),
            profile_memory_available=context.user_memory is not None,
            open_reminder_count=len(reminders),
            note_count=len(notes),
            session_digest_count=len(digests),
            relationship_memory_available=relationship_memory is not None,
            familiarity=familiarity,
            recurring_topics=recurring_topics,
            greeting_preference=relationship_profile.greeting_preference if relationship_profile is not None else None,
            planning_style=relationship_profile.planning_style if relationship_profile is not None else None,
            tone_preferences=list(relationship_profile.tone_preferences) if relationship_profile is not None else [],
            interaction_boundaries=list(relationship_profile.interaction_boundaries) if relationship_profile is not None else [],
            continuity_preferences=list(relationship_profile.continuity_preferences) if relationship_profile is not None else [],
            open_practical_threads=open_practical_threads,
            open_emotional_threads=open_emotional_threads,
            promise_count=promise_count,
            procedural_memory_count=len(procedural_items),
            open_follow_ups=open_follow_ups,
        )

    def _system_health(self, model: BaseModel, context: ToolRuntimeContext) -> BaseModel:
        del model
        by_kind = {item.kind.value: item for item in context.backend_status}
        degraded = [
            f"{item.kind.value}:{item.status.value}"
            for item in context.backend_status
            if item.status.value in {"degraded", "fallback_active", "unavailable"}
        ]
        return SystemHealthToolOutput(
            runtime_mode=context.world_state.mode.value,
            body_driver_mode=context.body_driver_mode,
            context_mode=context.context_mode.value,
            backend_profile=context.backend_profile,
            text_backend=by_kind.get("text_reasoning").backend_id if by_kind.get("text_reasoning") else None,
            vision_backend=by_kind.get("vision_analysis").backend_id if by_kind.get("vision_analysis") else None,
            embedding_backend=by_kind.get("embeddings").backend_id if by_kind.get("embeddings") else None,
            stt_backend=by_kind.get("speech_to_text").backend_id if by_kind.get("speech_to_text") else None,
            tts_backend=by_kind.get("text_to_speech").backend_id if by_kind.get("text_to_speech") else None,
            degraded_backends=degraded,
        )

    def _query_local_files(self, model: BaseModel, context: ToolRuntimeContext) -> BaseModel:
        del model
        notes = context.knowledge_tools.list_recent_notes(session=context.session, user_memory=context.user_memory, limit=5) if context.knowledge_tools is not None else []
        digests = context.knowledge_tools.list_recent_session_digests(session=context.session, user_memory=context.user_memory, limit=3) if context.knowledge_tools is not None else []
        return LocalFilesToolOutput(
            notes=[
                LocalNoteItem(
                    note_id=item.note_id,
                    title=item.title,
                    content=item.content,
                    tags=list(item.tags),
                )
                for item in notes
            ],
            digests=[
                SessionDigestItem(
                    digest_id=item.digest_id,
                    summary=item.summary,
                    open_follow_ups=list(item.open_follow_ups),
                )
                for item in digests
            ],
        )

    def _personal_reminders(self, model: BaseModel, context: ToolRuntimeContext) -> BaseModel:
        del model
        reminders = context.knowledge_tools.list_open_reminders(session=context.session, user_memory=context.user_memory, limit=6) if context.knowledge_tools is not None else []
        now = context.world_state.updated_at
        return PersonalRemindersToolOutput(
            reminders=[
                PersonalReminderItem(
                    reminder_id=item.reminder_id,
                    reminder_text=item.reminder_text,
                    due_at=item.due_at.isoformat() if item.due_at is not None else None,
                    due_state="due" if item.due_at is not None and item.due_at <= now else item.status.value,
                )
                for item in reminders
            ],
            due_count=sum(1 for item in reminders if item.due_at is not None and item.due_at <= now),
        )

    def _today_context(self, model: BaseModel, context: ToolRuntimeContext) -> BaseModel:
        del model
        reminders = context.knowledge_tools.list_open_reminders(session=context.session, user_memory=context.user_memory, limit=10) if context.knowledge_tools is not None else []
        notes = context.knowledge_tools.list_recent_notes(session=context.session, user_memory=context.user_memory, limit=10) if context.knowledge_tools is not None else []
        digests = context.knowledge_tools.list_recent_session_digests(session=context.session, user_memory=context.user_memory, limit=1) if context.knowledge_tools is not None else []
        return TodayContextToolOutput(
            today_label=context.world_state.updated_at.strftime("%A, %B %-d"),
            open_reminder_count=len(reminders),
            note_count=len(notes),
            latest_digest=digests[0].summary if digests else None,
        )

    def _recent_session_digest(self, model: BaseModel, context: ToolRuntimeContext) -> BaseModel:
        del model
        digests = context.knowledge_tools.list_recent_session_digests(session=context.session, user_memory=context.user_memory, limit=1) if context.knowledge_tools is not None else []
        latest = digests[0] if digests else None
        return RecentSessionDigestToolOutput(
            summary=latest.summary if latest is not None else None,
            open_follow_ups=list(latest.open_follow_ups) if latest is not None else [],
        )

    def _capture_scene(self, model: BaseModel, context: ToolRuntimeContext) -> BaseModel:
        del model
        snapshot = context.latest_perception
        fresh_facts = (
            context.knowledge_tools.recent_perception_facts(
                query=None,
                world_model=context.world_model,
                latest_perception=context.latest_perception,
            )
            if context.knowledge_tools is not None
            else []
        )
        visible_text = [item.label for item in fresh_facts if item.fact_type == "visible_text"]
        named_objects = [item.label for item in fresh_facts if item.fact_type == "named_object"]
        if not fresh_facts and snapshot is not None:
            for observation in snapshot.observations:
                if observation.observation_type == PerceptionObservationType.VISIBLE_TEXT and observation.text_value:
                    visible_text.append(observation.text_value)
                if observation.observation_type == PerceptionObservationType.NAMED_OBJECT and observation.text_value:
                    named_objects.append(observation.text_value)
        return CaptureSceneToolOutput(
            scene_summary=snapshot.scene_summary if snapshot is not None else None,
            limited_awareness=bool(snapshot.limited_awareness) if snapshot is not None else bool(context.world_model.perception_limited_awareness),
            provider_mode=snapshot.provider_mode.value if snapshot is not None else None,
            perception_tier=snapshot.tier.value if snapshot is not None else None,
            freshness=context.world_model.scene_freshness.value,
            trigger_reason=snapshot.trigger_reason if snapshot is not None else context.world_model.last_semantic_refresh_reason,
            visible_text=list(dict.fromkeys(visible_text)),
            named_objects=list(dict.fromkeys(named_objects)),
            attention_target=context.world_model.attention_target.target_label if context.world_model.attention_target else None,
            engagement_state=context.world_model.engagement_state.value,
            uncertainty_markers=list(context.world_model.uncertainty_markers),
            device_awareness_constraints=list(context.world_model.device_awareness_constraints),
            facts=fresh_facts,
        )

    def _world_model_runtime(self, model: BaseModel, context: ToolRuntimeContext) -> BaseModel:
        del model
        return WorldModelRuntimeToolOutput(
            social_runtime_mode=context.world_model.social_runtime_mode.value,
            scene_freshness=context.world_model.scene_freshness.value,
            engagement_state=context.world_model.engagement_state.value,
            attention_target=context.world_model.attention_target.target_label if context.world_model.attention_target else None,
            attention_rationale=context.world_model.attention_target.rationale if context.world_model.attention_target else None,
            likely_speaker_participant_id=context.world_model.current_speaker_participant_id,
            environment_state=context.world_model.environment_state.value,
            uncertainty_markers=list(context.world_model.uncertainty_markers),
            device_awareness_constraints=list(context.world_model.device_awareness_constraints),
        )

    def _transcribe_audio(self, model: BaseModel, context: ToolRuntimeContext) -> BaseModel:
        del context
        return AudioTranscriptionToolOutput(
            transcript_text=(model.transcript_text or "").strip() or None,
            transcription_backend="pass_through",
            success=bool((model.transcript_text or "").strip()),
        )

    def _speak_text(self, model: BaseModel, context: ToolRuntimeContext) -> BaseModel:
        del context
        return SpeechActionToolOutput(success=True, state="speaking", text=model.text)

    def _interrupt_speech(self, model: BaseModel, context: ToolRuntimeContext) -> BaseModel:
        del model, context
        return SpeechActionToolOutput(success=True, state="interrupted")

    def _set_listening_state(self, model: BaseModel, context: ToolRuntimeContext) -> BaseModel:
        del context
        return SpeechActionToolOutput(success=True, state=model.state or "listening")

    def _write_memory(self, model: BaseModel, context: ToolRuntimeContext) -> BaseModel:
        if context.memory_store is None:
            if model.scope == "profile" and context.user_memory is not None:
                context.user_memory.facts[model.key] = model.value
            else:
                context.session.session_memory[model.key] = model.value
            return MemoryWriteToolOutput(scope=model.scope, key=model.key, value=model.value, persisted=False)

        policy = MemoryPolicyService(context.memory_store)
        resolved_scope = model.scope
        if model.scope == "profile" and context.user_memory is not None:
            _profile, action = policy.write_profile_fact(
                user_memory=context.user_memory,
                key=model.key,
                value=model.value,
                tool_name="write_memory",
                reason_code=model.reason_code,
                policy_basis="agent_tool_profile_write",
            )
        else:
            if model.scope == "profile":
                resolved_scope = "session"
            action = policy.write_session_memory(
                session=context.session,
                key=model.key,
                value=model.value,
                tool_name="write_memory",
                reason_code=model.reason_code,
                policy_basis=(
                    "agent_tool_session_write"
                    if resolved_scope == "session"
                    else "profile_write_fallback_to_session"
                ),
            )
        return MemoryWriteToolOutput(
            scope=resolved_scope,
            key=model.key,
            value=model.value,
            action_id=action.action_id,
            memory_id=action.memory_id,
            persisted=True,
        )

    def _create_reminder(self, model: BaseModel, context: ToolRuntimeContext) -> BaseModel:
        if context.memory_store is None:
            return CreateReminderToolOutput(
                created=False,
                reminder_text=model.reminder_text,
                due_at=model.due_at,
                status="memory_store_unavailable",
            )
        record = context.memory_store.upsert_reminder(
            ReminderRecord(
                session_id=context.session.session_id,
                user_id=context.session.user_id,
                reminder_text=model.reminder_text,
                due_at=model.due_at,
                status=ReminderStatus.OPEN,
                reason_code=model.reason_code,
                policy_basis="agent_tool_create_reminder",
            )
        )
        return CreateReminderToolOutput(
            created=True,
            reminder_id=record.reminder_id,
            reminder_text=record.reminder_text,
            due_at=record.due_at.isoformat() if record.due_at is not None else None,
            status=record.status.value,
        )

    def _list_reminders(self, model: BaseModel, context: ToolRuntimeContext) -> BaseModel:
        if context.memory_store is None:
            return PersonalRemindersToolOutput(reminders=[], due_count=0)
        status = ReminderStatus(model.status) if model.status else None
        items = context.memory_store.list_reminders(
            session_id=context.session.session_id,
            user_id=context.session.user_id,
            status=status,
            limit=model.limit,
        ).items
        now = context.world_state.updated_at
        return PersonalRemindersToolOutput(
            reminders=[
                PersonalReminderItem(
                    reminder_id=item.reminder_id,
                    reminder_text=item.reminder_text,
                    due_at=item.due_at.isoformat() if item.due_at is not None else None,
                    due_state="due" if item.due_at is not None and item.due_at <= now else item.status.value,
                )
                for item in items
            ],
            due_count=sum(1 for item in items if item.status == ReminderStatus.OPEN),
        )

    def _mark_reminder_done(self, model: BaseModel, context: ToolRuntimeContext) -> BaseModel:
        if context.memory_store is None:
            return MarkReminderDoneToolOutput(
                updated=False,
                reminder_id=model.reminder_id,
                status="memory_store_unavailable",
            )
        existing = context.memory_store.get_reminder(model.reminder_id)
        if existing is None:
            return MarkReminderDoneToolOutput(updated=False, reminder_id=model.reminder_id, status="reminder_not_found")
        existing.status = ReminderStatus(model.status)
        existing.updated_at = utc_now()
        updated = context.memory_store.upsert_reminder(existing)
        return MarkReminderDoneToolOutput(
            updated=True,
            reminder_id=updated.reminder_id,
            status=updated.status.value,
            reminder_text=updated.reminder_text,
        )

    def _create_note(self, model: BaseModel, context: ToolRuntimeContext) -> BaseModel:
        if context.memory_store is None:
            return CreateNoteToolOutput(
                created=False,
                title=model.title,
                content=model.content,
                tags=list(model.tags),
            )
        note = context.memory_store.upsert_companion_note(
            CompanionNoteRecord(
                session_id=context.session.session_id,
                user_id=context.session.user_id,
                title=model.title,
                content=model.content,
                tags=list(model.tags),
                reason_code=MemoryWriteReasonCode.CONVERSATION_TOPIC,
                policy_basis="agent_tool_create_note",
            )
        )
        return CreateNoteToolOutput(
            created=True,
            note_id=note.note_id,
            title=note.title,
            content=note.content,
            tags=list(note.tags),
        )

    def _append_note(self, model: BaseModel, context: ToolRuntimeContext) -> BaseModel:
        if context.memory_store is None:
            return AppendNoteToolOutput(updated=False, note_id=model.note_id)
        existing = context.memory_store.get_companion_note(model.note_id)
        if existing is None:
            return AppendNoteToolOutput(updated=False, note_id=model.note_id)
        existing.content = f"{existing.content.rstrip()}\n{model.content_append}".strip()
        existing.updated_at = utc_now()
        updated = context.memory_store.upsert_companion_note(existing)
        return AppendNoteToolOutput(
            updated=True,
            note_id=updated.note_id,
            title=updated.title,
            content=updated.content,
            tags=list(updated.tags),
        )

    def _search_notes(self, model: BaseModel, context: ToolRuntimeContext) -> BaseModel:
        if context.memory_store is None:
            return SearchNotesToolOutput(notes=[], query=model.query or None)
        items = context.memory_store.list_companion_notes(
            session_id=context.session.session_id,
            user_id=context.session.user_id,
            limit=model.limit,
        ).items
        lowered = model.query.lower().strip()
        filtered = [
            item
            for item in items
            if not lowered
            or all(token in " ".join([item.title, item.content, *item.tags]).lower() for token in lowered.split())
        ]
        return SearchNotesToolOutput(
            notes=[
                LocalNoteItem(
                    note_id=item.note_id,
                    title=item.title,
                    content=item.content,
                    tags=list(item.tags),
                )
                for item in filtered
            ],
            query=model.query or None,
        )

    def _read_local_file(self, model: BaseModel, context: ToolRuntimeContext) -> BaseModel:
        del context
        try:
            path = self._resolve_allowed_local_file(model.path)
            content = path.read_text(encoding="utf-8", errors="replace")
            truncated = len(content) > model.max_chars
            return ReadLocalFileToolOutput(
                path=str(path),
                content=content[: model.max_chars],
                truncated=truncated,
                size_bytes=path.stat().st_size,
            )
        except Exception:
            return ReadLocalFileToolOutput(path=model.path, content="", truncated=False, size_bytes=0)

    def _stage_local_file(self, model: BaseModel, context: ToolRuntimeContext) -> BaseModel:
        del context
        try:
            source = self._resolve_allowed_local_file(model.path)
            settings = Settings()
            stage_dir = Path(settings.blink_action_plane_stage_dir)
            stage_dir.mkdir(parents=True, exist_ok=True)
            staged_path = stage_dir / f"{utc_now().strftime('%Y%m%dT%H%M%S')}_{source.name}"
            shutil.copy2(source, staged_path)
            return StageLocalFileToolOutput(staged=True, source_path=str(source), staged_path=str(staged_path))
        except Exception:
            return StageLocalFileToolOutput(staged=False, source_path=model.path, staged_path=None)

    def _export_local_bundle(self, model: BaseModel, context: ToolRuntimeContext) -> BaseModel:
        del context
        try:
            settings = Settings()
            export_dir = Path(settings.blink_action_plane_export_dir)
            export_dir.mkdir(parents=True, exist_ok=True)
            label = self._slugify(model.label or "export-bundle")
            bundle_dir = export_dir / f"{utc_now().strftime('%Y%m%dT%H%M%S')}_{label}"
            bundle_dir.mkdir(parents=True, exist_ok=True)
            files: list[ExportedBundleFile] = []
            for raw_path in model.paths:
                source = self._resolve_allowed_local_file(raw_path)
                destination = bundle_dir / source.name
                shutil.copy2(source, destination)
                files.append(ExportedBundleFile(source_path=str(source), bundle_path=str(destination)))
            manifest_path = bundle_dir / "manifest.json"
            write_json_atomic(
                manifest_path,
                {"label": label, "files": [item.model_dump(mode="json") for item in files]},
                keep_backups=1,
            )
            return ExportLocalBundleToolOutput(
                exported=True,
                bundle_dir=str(bundle_dir),
                manifest_path=str(manifest_path),
                file_count=len(files),
                files=files,
            )
        except Exception:
            return ExportLocalBundleToolOutput(exported=False, file_count=0, files=[])

    def _promote_memory(self, model: BaseModel, context: ToolRuntimeContext) -> BaseModel:
        if context.memory_store is None:
            return MemoryPromotionToolOutput(scope=model.scope, promoted=False)

        policy = MemoryPolicyService(context.memory_store)
        if model.scope == "episodic":
            record = EpisodicMemoryRecord(
                memory_id=f"episodic-{uuid4().hex[:12]}",
                session_id=context.session.session_id,
                user_id=context.session.user_id,
                title=model.memory_kind,
                summary=model.summary,
                topics=[model.memory_kind],
                source_trace_ids=[turn.trace_id for turn in context.session.transcript if turn.trace_id][-3:],
            )
            action = policy.promote_episodic(
                record,
                tool_name="promote_memory",
                reason_code=model.reason_code,
                policy_basis="agent_tool_episodic_promotion",
            )
        else:
            record = SemanticMemoryRecord(
                memory_id=f"semantic-{uuid4().hex[:12]}",
                memory_kind=model.memory_kind,
                summary=model.summary,
                canonical_value=model.canonical_value,
                session_id=context.session.session_id,
                user_id=context.session.user_id,
                confidence=0.75,
                source_trace_ids=[turn.trace_id for turn in context.session.transcript if turn.trace_id][-3:],
            )
            action = policy.promote_semantic(
                record,
                tool_name="promote_memory",
                reason_code=model.reason_code,
                confidence=record.confidence,
                policy_basis="agent_tool_semantic_promotion",
            )
        return MemoryPromotionToolOutput(
            scope=model.scope,
            memory_id=action.memory_id,
            action_id=action.action_id,
            promoted=True,
        )

    def _draft_calendar_event(self, model: BaseModel, context: ToolRuntimeContext) -> BaseModel:
        del context
        settings = Settings()
        draft_dir = Path(settings.blink_action_plane_draft_dir)
        draft_dir.mkdir(parents=True, exist_ok=True)
        draft_path = draft_dir / f"{utc_now().strftime('%Y%m%dT%H%M%S')}_{self._slugify(model.title)}.json"
        write_json_atomic(
            draft_path,
            {
                "title": model.title,
                "start_at": model.start_at,
                "end_at": model.end_at,
                "location": model.location,
                "description": model.description,
                "created_at": utc_now().isoformat(),
                "status": "draft_only_local_artifact",
            },
            keep_backups=1,
        )
        return DraftCalendarEventToolOutput(
            drafted=True,
            draft_path=str(draft_path),
            title=model.title,
            start_at=model.start_at,
            end_at=model.end_at,
            location=model.location,
            status="drafted",
        )

    def _start_workflow(self, model: BaseModel, context: ToolRuntimeContext) -> BaseModel:
        if context.workflow_runtime is None:
            raise RuntimeError("workflow_runtime_unavailable")
        return context.workflow_runtime.start_workflow(request=model, tool_context=context)

    def _body_preview(self, model: BaseModel, context: ToolRuntimeContext) -> BaseModel:
        commands = context.action_policy.build_commands(model.intent, model.reply_text)
        return ActionPlanToolOutput(
            command_types=[command.command_type.value for command in commands],
            previews=[self._embodied_action_preview(command=command, context=context) for command in commands],
            semantic_only=all(command.command_type.value != "move_base" for command in commands),
        )

    def _body_command(self, model: BaseModel, context: ToolRuntimeContext) -> BaseModel:
        return self._body_preview(model, context)

    def _body_safe_idle(self, model: BaseModel, context: ToolRuntimeContext) -> BaseModel:
        safe_model = ActionPlanToolInput(intent="safe_idle", reply_text=model.reply_text)
        return self._body_preview(safe_model, context)

    def _request_operator_help(self, model: BaseModel, context: ToolRuntimeContext) -> BaseModel:
        context.session.status = SessionStatus.ESCALATION_PENDING
        context.session.session_memory["operator_escalation"] = "requested"
        context.session.current_topic = "operator_handoff"
        if context.memory_store is not None:
            context.memory_store.upsert_session(context.session)
        return IncidentToolOutput(requested=True, status="operator_requested")

    def _log_incident(self, model: BaseModel, context: ToolRuntimeContext) -> BaseModel:
        ticket_id = None
        if context.memory_store is not None:
            ticket = IncidentTicketRecord(
                session_id=context.session.session_id,
                participant_summary=model.participant_summary,
                reason_category=IncidentReasonCategory.GENERAL_ESCALATION,
                urgency=IncidentUrgency.NORMAL,
                current_status=IncidentStatus.PENDING,
            )
            context.memory_store.upsert_incident_ticket(ticket)
            context.memory_store.append_incident_timeline(
                [
                    IncidentTimelineRecord(
                        ticket_id=ticket.ticket_id,
                        session_id=context.session.session_id,
                        event_type=IncidentTimelineEventType.CREATED,
                        to_status=ticket.current_status,
                        note=model.note,
                    )
                ]
            )
            ticket_id = ticket.ticket_id
        context.session.active_incident_ticket_id = ticket_id
        context.session.current_topic = "operator_handoff"
        return IncidentToolOutput(requested=ticket_id is not None, incident_ticket_id=ticket_id, status="pending")

    def _require_confirmation(self, model: BaseModel, context: ToolRuntimeContext) -> BaseModel:
        del context
        return ConfirmationToolOutput(prompt=model.prompt)

    def _browser_task(self, model: BaseModel, context: ToolRuntimeContext) -> BaseModel:
        del context
        return BrowserTaskToolOutput.model_validate(
            unsupported_browser_output(
                query=model.query,
                requested_action=getattr(model, "requested_action", None),
            )
        )

    def _tool_success_for_output(self, tool_name: str, output_model: BaseModel) -> bool:
        if tool_name == "write_memory":
            return bool(getattr(output_model, "persisted", False))
        if tool_name == "promote_memory":
            return bool(getattr(output_model, "promoted", False))
        if tool_name in {"create_reminder", "create_note"}:
            return bool(getattr(output_model, "created", False))
        if tool_name in {"mark_reminder_done", "append_note"}:
            return bool(getattr(output_model, "updated", False))
        if tool_name == "stage_local_file":
            return bool(getattr(output_model, "staged", False))
        if tool_name == "export_local_bundle":
            return bool(getattr(output_model, "exported", False))
        if tool_name == "draft_calendar_event":
            return bool(getattr(output_model, "drafted", False))
        if tool_name in {"request_operator_help", "log_incident"}:
            return bool(getattr(output_model, "requested", False))
        if tool_name == "browser_task":
            return bool(getattr(output_model, "supported", False) and getattr(output_model, "configured", False))
        if hasattr(output_model, "success"):
            value = getattr(output_model, "success", None)
            if isinstance(value, bool):
                return value
        return True

    def _fallback_used_for_output(self, tool_name: str, output_model: BaseModel) -> bool:
        if tool_name == "capture_scene":
            return bool(getattr(output_model, "limited_awareness", False))
        if tool_name == "device_health_snapshot":
            return bool(getattr(output_model, "degraded_devices", []))
        if tool_name == "system_health":
            return bool(getattr(output_model, "degraded_backends", []))
        if tool_name == "browser_task":
            return not self._tool_success_for_output(tool_name, output_model)
        return False

    def _is_unsupported_output(self, tool_name: str, output_model: BaseModel) -> bool:
        return tool_name == "browser_task" and getattr(output_model, "status", None) == "unsupported"

    def _is_unconfigured_output(self, tool_name: str, output_model: BaseModel) -> bool:
        return tool_name == "browser_task" and getattr(output_model, "configured", True) is False

    def _capability_state_for_output(self, tool_name: str, output_model: BaseModel):
        unsupported = self._is_unsupported_output(tool_name, output_model)
        unconfigured = self._is_unconfigured_output(tool_name, output_model)
        unavailable = False
        if tool_name == "device_health_snapshot":
            unavailable = any(item.status == "unavailable" for item in getattr(output_model, "devices", []))
        if tool_name == "system_health":
            unavailable = any("unavailable" in item for item in getattr(output_model, "degraded_backends", []))
        return normalize_capability_state(
            success=self._tool_success_for_output(tool_name, output_model),
            fallback_used=self._fallback_used_for_output(tool_name, output_model),
            unsupported=unsupported,
            unconfigured=unconfigured,
            unavailable=unavailable,
        )

    def _error_code_for_output(self, tool_name: str, output_model: BaseModel) -> str | None:
        if tool_name == "browser_task":
            if getattr(output_model, "status", None) == "unsupported":
                return "browser_task_unsupported"
            if getattr(output_model, "configured", True) is False:
                return "browser_task_not_configured"
        return None

    def _error_detail_for_output(self, tool_name: str, output_model: BaseModel) -> str | None:
        if tool_name == "browser_task":
            return getattr(output_model, "detail", None)
        if tool_name == "capture_scene" and getattr(output_model, "limited_awareness", False):
            return "limited_awareness"
        if tool_name in {"stage_local_file", "export_local_bundle", "draft_calendar_event"} and not self._tool_success_for_output(tool_name, output_model):
            return self._summary_for_output(tool_name, output_model)
        return None

    def _summary_for_output(self, tool_name: str, output_model: BaseModel) -> str:
        if tool_name in {"search_venue_knowledge", "query_calendar"}:
            answers = getattr(output_model, "answers", [])
            return f"answers={len(answers)}"
        if tool_name == "list_reminders":
            return f"reminders={len(getattr(output_model, 'reminders', []))}"
        if tool_name == "search_notes":
            return f"notes={len(getattr(output_model, 'notes', []))}"
        if tool_name == "search_memory":
            episodic_hits = getattr(output_model, "episodic_hits", [])
            semantic_hits = getattr(output_model, "semantic_hits", [])
            return f"memory_hits={len(episodic_hits) + len(semantic_hits)}"
        if tool_name in {"body_preview", "body_command", "body_safe_idle"}:
            return ",".join(getattr(output_model, "command_types", [])[:4]) or "no_commands"
        if tool_name == "read_local_file":
            return getattr(output_model, "path", None) or "file_read"
        if tool_name == "stage_local_file":
            return "file_staged" if getattr(output_model, "staged", False) else "file_stage_failed"
        if tool_name == "export_local_bundle":
            return "bundle_exported" if getattr(output_model, "exported", False) else "bundle_export_failed"
        if tool_name == "draft_calendar_event":
            return "calendar_drafted" if getattr(output_model, "drafted", False) else "calendar_draft_failed"
        if tool_name in {"request_operator_help", "log_incident"}:
            return getattr(output_model, "status", None) or "handoff_pending"
        if tool_name == "require_confirmation":
            return "confirmation_required"
        if tool_name == "capture_scene":
            return getattr(output_model, "scene_summary", None) or "scene_captured"
        if tool_name == "system_health":
            return getattr(output_model, "runtime_mode", "system_health")
        if tool_name == "browser_task":
            return getattr(output_model, "status", None) or "browser_task"
        return tool_name

    def _source_refs_for_output(self, tool_name: str, output_model: BaseModel) -> list[str]:
        if tool_name in {"search_venue_knowledge", "query_calendar"}:
            return [
                source_ref
                for answer in getattr(output_model, "answers", [])
                for source_ref in answer.source_refs
                if source_ref
            ]
        if tool_name == "search_memory":
            refs: list[str] = []
            for bucket in (getattr(output_model, "episodic_hits", []), getattr(output_model, "semantic_hits", [])):
                refs.extend([item.source_ref for item in bucket if item.source_ref])
            return refs
        if tool_name == "browser_task":
            return [artifact.path for artifact in getattr(output_model, "artifacts", []) if artifact.path]
        if tool_name in {"read_local_file", "stage_local_file"}:
            path = getattr(output_model, "path", None) or getattr(output_model, "source_path", None)
            return [path] if path else []
        if tool_name == "export_local_bundle":
            manifest_path = getattr(output_model, "manifest_path", None)
            return [manifest_path] if manifest_path else []
        if tool_name == "draft_calendar_event":
            draft_path = getattr(output_model, "draft_path", None)
            return [draft_path] if draft_path else []
        return []

    def _resolve_allowed_local_file(self, raw_path: str) -> Path:
        settings = Settings()
        roots = [Path(item).expanduser().resolve() for item in settings.action_plane_local_file_roots_list]
        candidate = Path(raw_path).expanduser()
        if not candidate.is_absolute():
            candidate = Path.cwd() / candidate
        resolved = candidate.resolve()
        for root in roots:
            try:
                resolved.relative_to(root)
                return resolved
            except ValueError:
                continue
        raise ValueError(f"path_outside_allowed_roots:{resolved}")

    def _slugify(self, value: str) -> str:
        return "".join(ch.lower() if ch.isalnum() else "-" for ch in value).strip("-") or "artifact"

    def _embodied_action_preview(self, *, command: RobotCommand, context: ToolRuntimeContext) -> EmbodiedActionPreview:
        payload = dict(command.payload)
        semantic_name = None
        source_name = None
        if command.command_type.value == "set_expression":
            source_name = str(payload.get("expression") or "neutral")
            semantic_name = normalize_expression_name(source_name).canonical_name
        elif command.command_type.value == "set_gaze":
            source_name = str(payload.get("target") or "look_forward")
            semantic_name = normalize_gaze_name(source_name).canonical_name
        elif command.command_type.value == "perform_gesture":
            source_name = str(payload.get("gesture") or "blink")
            semantic_name = normalize_gesture_name(source_name).canonical_name
        elif command.command_type.value == "perform_animation":
            source_name = str(payload.get("animation") or "recover_neutral")
            semantic_name = normalize_animation_name(source_name).canonical_name
        elif command.command_type.value == "safe_idle":
            source_name = "safe_idle"
            semantic_name = "safe_idle"
        return EmbodiedActionPreview(
            command_type=command.command_type.value,
            payload=payload,
            semantic_name=semantic_name,
            source_name=source_name,
            driver_mode=context.body_driver_mode,
            transport_mode=context.body_transport_mode,
            preview_status=context.body_preview_status,
        )

    def _action_notes(self, action_result: ActionInvocationResult | None) -> list[str]:
        if action_result is None:
            return []
        notes = [
            f"action_policy:{action_result.proposal.policy_decision.value}",
            f"action_status:{action_result.execution.status.value}",
        ]
        if action_result.execution.detail:
            notes.append(f"action_detail:{action_result.execution.detail}")
        return notes
