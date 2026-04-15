from __future__ import annotations

from datetime import date, datetime, time, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator, model_validator


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class RobotMode(str, Enum):
    DESKTOP_BODYLESS = "desktop_bodyless"
    DESKTOP_VIRTUAL_BODY = "desktop_virtual_body"
    DESKTOP_SERIAL_BODY = "desktop_serial_body"
    TETHERED_FUTURE = "tethered_future"
    SIMULATED = "simulated"
    TETHERED_DEMO = "tethered_demo"
    HARDWARE = "hardware"
    DEGRADED_SAFE_IDLE = "degraded_safe_idle"


class CommandType(str, Enum):
    SPEAK = "speak"
    DISPLAY_TEXT = "display_text"
    SET_LED = "set_led"
    SET_HEAD_POSE = "set_head_pose"
    SET_EXPRESSION = "set_expression"
    SET_GAZE = "set_gaze"
    PERFORM_GESTURE = "perform_gesture"
    PERFORM_ANIMATION = "perform_animation"
    SAFE_IDLE = "safe_idle"
    MOVE_BASE = "move_base"
    STOP = "stop"


class SessionStatus(str, Enum):
    ACTIVE = "active"
    ESCALATION_PENDING = "escalation_pending"
    CLOSED = "closed"


class SessionRoutingStatus(str, Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    HANDED_OFF = "handed_off"
    COMPLETE = "complete"


class ReminderStatus(str, Enum):
    OPEN = "open"
    DELIVERED = "delivered"
    DISMISSED = "dismissed"


class IncidentReasonCategory(str, Enum):
    ACCESSIBILITY = "accessibility"
    SAFETY = "safety"
    LOST_ITEM = "lost_item"
    STAFF_REQUEST = "staff_request"
    EVENT_SUPPORT = "event_support"
    GENERAL_ESCALATION = "general_escalation"
    UNKNOWN = "unknown"


class IncidentUrgency(str, Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


class IncidentStatus(str, Enum):
    PENDING = "pending"
    ACKNOWLEDGED = "acknowledged"
    ASSIGNED = "assigned"
    RESOLVED = "resolved"
    UNAVAILABLE = "unavailable"


class IncidentResolutionOutcome(str, Enum):
    STAFF_ASSISTED = "staff_assisted"
    REMOTE_GUIDANCE = "remote_guidance"
    NO_OPERATOR_AVAILABLE = "no_operator_available"
    VISITOR_CANCELLED = "visitor_cancelled"
    DUPLICATE = "duplicate"
    UNKNOWN = "unknown"


class IncidentTimelineEventType(str, Enum):
    CREATED = "created"
    ACKNOWLEDGED = "acknowledged"
    ASSIGNED = "assigned"
    NOTE_ADDED = "note_added"
    RESOLVED = "resolved"
    UNAVAILABLE = "unavailable"


class IncidentListScope(str, Enum):
    OPEN = "open"
    CLOSED = "closed"
    ALL = "all"


class VenueFallbackScenario(str, Enum):
    SAFE_IDLE = "safe_idle"
    TRANSPORT_OUTAGE = "transport_outage"
    OPERATOR_UNAVAILABLE = "operator_unavailable"
    AFTER_HOURS = "after_hours"


class ResponseMode(str, Enum):
    GUIDE = "guide"
    AMBASSADOR = "ambassador"
    DEBUG = "debug"


class TraceOutcome(str, Enum):
    OK = "ok"
    ERROR = "error"
    SAFE_FALLBACK = "safe_fallback"
    FALLBACK_REPLY = "fallback_reply"
    NOOP = "noop"


class DemoRunStatus(str, Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ShiftReportStatus(str, Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class EpisodeSourceType(str, Enum):
    DEMO_RUN = "demo_run"
    SESSION = "session"
    SHIFT_REPORT = "shift_report"


class EpisodeAssetKind(str, Enum):
    IMAGE_FRAME = "image_frame"
    VIDEO_CLIP = "video_clip"
    AUDIO_CLIP = "audio_clip"
    OTHER = "other"


class EpisodeAnnotationStatus(str, Enum):
    PENDING_REVIEW = "pending_review"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class MemoryLayer(str, Enum):
    WORKING = "working"
    PROFILE = "profile"
    EPISODIC = "episodic"
    RELATIONSHIP = "relationship"
    PROCEDURAL = "procedural"
    SEMANTIC = "semantic"
    WORLD = "world"


class MemoryActionType(str, Enum):
    WRITE = "write"
    PROMOTE = "promote"
    REVIEW = "review"
    CORRECT = "correct"
    DELETE = "delete"
    REJECT = "reject"


class MemoryWriteReasonCode(str, Enum):
    TURN_COMPACTION = "turn_compaction"
    CONVERSATION_TOPIC = "conversation_topic"
    VENUE_LOCATION = "venue_location"
    VENUE_EVENT = "venue_event"
    GROUNDED_REPLY = "grounded_reply"
    RELATIONSHIP_STYLE = "relationship_style"
    RELATIONSHIP_THREAD = "relationship_thread"
    RELATIONSHIP_PROMISE = "relationship_promise"
    PROCEDURAL_PREFERENCE = "procedural_preference"
    EXPLICIT_REMINDER_REQUEST = "explicit_reminder_request"
    EXPLICIT_NOTE_CAPTURE = "explicit_note_capture"
    SCHEDULED_COMPACTION = "scheduled_compaction"
    PROFILE_PREFERENCE = "profile_preference"
    PROFILE_FACT = "profile_fact"
    SESSION_CONTEXT = "session_context"
    AGENT_WRITE = "agent_write"
    AGENT_PROMOTION = "agent_promotion"
    OPERATOR_CORRECTION = "operator_correction"
    OPERATOR_DELETION = "operator_deletion"
    TEACHER_IMPORTANCE = "teacher_importance"


class MemoryReviewStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    CORRECTED = "corrected"
    TOMBSTONED = "tombstoned"
    REJECTED = "rejected"


class MemoryDecisionOutcome(str, Enum):
    WRITTEN = "written"
    PROMOTED = "promoted"
    MERGED = "merged"
    REVIEWED = "reviewed"
    CORRECTED = "corrected"
    TOMBSTONED = "tombstoned"
    REJECTED = "rejected"
    SKIPPED = "skipped"


class ReviewDebtState(str, Enum):
    CLEAR = "clear"
    PENDING = "pending"
    OVERDUE = "overdue"


class MemoryRetrievalBackend(str, Enum):
    PROFILE_SCAN = "profile_scan"
    EPISODIC_KEYWORD = "episodic_keyword"
    RELATIONSHIP_RUNTIME = "relationship_runtime"
    PROCEDURAL_MATCH = "procedural_match"
    SEMANTIC_VECTOR = "semantic_vector"
    WORLD_STATE = "world_state"
    PERCEPTION_CONTEXT = "perception_context"


class ExportRedactionProfile(str, Enum):
    LOCAL_FULL = "local_full"
    LOCAL_OPERATOR = "local_operator"
    RESEARCH_REDACTED = "research_redacted"


class RedactionState(str, Enum):
    RAW = "raw"
    REDACTED = "redacted"


class SensitiveContentFlag(str, Enum):
    OPERATOR_NOTE = "operator_note"
    SESSION_MEMORY = "session_memory"
    PROFILE_MEMORY = "profile_memory"
    RELATIONSHIP_MEMORY = "relationship_memory"
    PROCEDURAL_MEMORY = "procedural_memory"
    USER_IDENTIFIER = "user_identifier"
    TEACHER_FREEFORM = "teacher_freeform"
    TRANSCRIPT_TEXT = "transcript_text"
    LOCAL_PATH = "local_path"


class EpisodeLabelName(str, Enum):
    SUCCESSFUL_GROUNDING = "successful_grounding"
    FAILED_GROUNDING = "failed_grounding"
    GREETING_QUALITY = "greeting_quality"
    ESCALATION_CORRECTNESS = "escalation_correctness"
    SAFE_FALLBACK_CORRECTNESS = "safe_fallback_correctness"


class TeacherAnnotationScope(str, Enum):
    TRACE = "trace"
    MEMORY = "memory"
    EPISODE = "episode"
    RUN = "run"
    ACTION = "action"
    WORKFLOW_RUN = "workflow_run"


class TeacherPrimaryKind(str, Enum):
    GENERAL = "general"
    REPLY = "reply"
    MEMORY = "memory"
    SCENE = "scene"
    EMBODIMENT = "embodiment"
    OUTCOME = "outcome"
    ACTION = "action"


class ActionTeacherFeedbackLabel(str, Enum):
    WRONG_ACTION_CHOICE = "wrong_action_choice"
    WRONG_TIMING = "wrong_timing"
    WRONG_EXPLANATION = "wrong_explanation"
    SHOULD_HAVE_REQUIRED_APPROVAL = "should_have_required_approval"
    UNNECESSARY_ACTION = "unnecessary_action"
    MISSING_FOLLOW_UP = "missing_follow_up"


class TeacherMemoryFeedbackAction(str, Enum):
    PROMOTE = "promote"
    REJECT = "reject"
    MERGE_INTO = "merge_into"
    CORRECT_TO = "correct_to"
    NEEDS_REVIEW = "needs_review"


class BenchmarkFamily(str, Enum):
    APPLIANCE_BOOT_RECOVERY = "appliance_boot_recovery"
    CONVERSATION_CONTINUITY = "conversation_continuity"
    MEMORY_CORRECTNESS = "memory_correctness"
    SCENE_GROUNDING = "scene_grounding"
    HONEST_UNCERTAINTY = "honest_uncertainty"
    GRACEFUL_DEVICE_FAILURE = "graceful_device_failure"
    SOCIAL_TIMING = "social_timing"
    PROACTIVE_PROMPT_QUALITY = "proactive_prompt_quality"
    BODY_EXPRESSION_ALIGNMENT = "body_expression_alignment"
    SAFE_IDLE_BEHAVIOR = "safe_idle_behavior"
    OPERATOR_ESCALATION_QUALITY = "operator_escalation_quality"
    EPISODE_EXPORT_VALIDITY = "episode_export_validity"
    PLANNER_SWAP_COMPATIBILITY = "planner_swap_compatibility"
    REPLAY_DETERMINISM = "replay_determinism"
    ANNOTATION_COMPLETENESS = "annotation_completeness"
    DATASET_SPLIT_HYGIENE = "dataset_split_hygiene"
    LOCAL_APPLIANCE_RELIABILITY = "local_appliance_reliability"
    TOOL_PROTOCOL_INTEGRITY = "tool_protocol_integrity"
    PERCEPTION_WORLD_MODEL_FRESHNESS = "perception_world_model_freshness"
    SOCIAL_RUNTIME_QUALITY = "social_runtime_quality"
    MEMORY_RETRIEVAL_QUALITY = "memory_retrieval_quality"
    TEACHER_ANNOTATION_COMPLETENESS = "teacher_annotation_completeness"
    EMBODIMENT_ACTION_VALIDITY = "embodiment_action_validity"
    PLANNER_COMPARISON_QUALITY = "planner_comparison_quality"
    EXPORT_DATASET_HYGIENE = "export_dataset_hygiene"
    ACTION_APPROVAL_CORRECTNESS = "action_approval_correctness"
    ACTION_IDEMPOTENCY = "action_idempotency"
    WORKFLOW_RESUME_CORRECTNESS = "workflow_resume_correctness"
    BROWSER_ARTIFACT_COMPLETENESS = "browser_artifact_completeness"
    CONNECTOR_SAFETY_POLICY = "connector_safety_policy"
    PROACTIVE_ACTION_RESTRAINT = "proactive_action_restraint"
    ACTION_TRACE_COMPLETENESS = "action_trace_completeness"


class PlannerReplayMode(str, Enum):
    STRICT = "strict"
    OBSERVATIONAL = "observational"


class BenchmarkComparisonMode(str, Enum):
    EPISODE_ONLY = "episode_only"
    REPLAY_ONLY = "replay_only"
    EPISODE_VS_REPLAY = "episode_vs_replay"


class DatasetSplitName(str, Enum):
    TRAIN = "train"
    VALIDATION = "validation"
    TEST = "test"


class ResearchExportFormat(str, Enum):
    NATIVE = "native"
    LEROBOT_LIKE = "lerobot_like"
    OPENX_LIKE = "openx_like"


class EdgeTransportMode(str, Enum):
    IN_PROCESS = "in_process"
    HTTP = "http"


class TransportState(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"


class CommandAckStatus(str, Enum):
    APPLIED = "applied"
    REJECTED = "rejected"
    DUPLICATE = "duplicate"
    TRANSPORT_ERROR = "transport_error"


class EdgeAdapterDirection(str, Enum):
    ACTUATOR = "actuator"
    INPUT = "input"
    MONITOR = "monitor"


class EdgeAdapterState(str, Enum):
    ACTIVE = "active"
    UNAVAILABLE = "unavailable"
    DEGRADED = "degraded"
    SIMULATED = "simulated"
    DISABLED = "disabled"


class EdgeAdapterKind(str, Enum):
    SPEAKER_TRIGGER = "speaker_trigger"
    DISPLAY = "display"
    LED = "led"
    HEAD_POSE = "head_pose"
    TOUCH = "touch"
    BUTTON = "button"
    PRESENCE = "presence"
    NETWORK = "network"
    BATTERY = "battery"
    HEARTBEAT = "heartbeat"
    TRANSCRIPT_RELAY = "transcript_relay"


class DesktopDeviceKind(str, Enum):
    MICROPHONE = "microphone"
    SPEAKER = "speaker"
    CAMERA = "camera"


class RuntimeBackendKind(str, Enum):
    TEXT_REASONING = "text_reasoning"
    VISION_ANALYSIS = "vision_analysis"
    EMBEDDINGS = "embeddings"
    SPEECH_TO_TEXT = "speech_to_text"
    TEXT_TO_SPEECH = "text_to_speech"


class RuntimeBackendAvailability(str, Enum):
    CONFIGURED = "configured"
    WARM = "warm"
    UNAVAILABLE = "unavailable"
    DEGRADED = "degraded"
    FALLBACK_ACTIVE = "fallback_active"


class AgentHookName(str, Enum):
    BEFORE_SKILL_SELECTION = "before_skill_selection"
    AFTER_TRANSCRIPT = "after_transcript"
    AFTER_PERCEPTION = "after_perception"
    BEFORE_TOOL_CALL = "before_tool_call"
    AFTER_TOOL_RESULT = "after_tool_result"
    BEFORE_REPLY = "before_reply"
    BEFORE_REPLY_GENERATION = "before_reply_generation"
    BEFORE_SPEAK = "before_speak"
    BEFORE_MEMORY_WRITE = "before_memory_write"
    AFTER_TURN = "after_turn"
    ON_FAILURE = "on_failure"
    ON_SAFE_IDLE = "on_safe_idle"
    ON_PROVIDER_FAILURE = "on_provider_failure"
    ON_SESSION_CLOSE = "on_session_close"


class AgentValidationStatus(str, Enum):
    APPROVED = "approved"
    DOWNGRADED = "downgraded"
    BLOCKED = "blocked"
    OBSERVED = "observed"


class ToolPermissionClass(str, Enum):
    READ_ONLY = "read_only"
    EFFECTFUL = "effectful"
    OPERATOR_SENSITIVE = "operator_sensitive"


class ToolLatencyClass(str, Enum):
    FAST = "fast"
    LOCAL_IO = "local_io"
    NETWORK = "network"
    HUMAN_LOOP = "human_loop"


class ToolEffectClass(str, Enum):
    READ_ONLY = "read_only"
    STATE_MUTATION = "state_mutation"
    SPEECH_OUTPUT = "speech_output"
    EMBODIMENT_COMMAND = "embodiment_command"
    OPERATOR_HANDOFF = "operator_handoff"
    CONFIRMATION_GATE = "confirmation_gate"


class ToolResultStatus(str, Enum):
    OK = "ok"
    DEGRADED = "degraded"
    BLOCKED = "blocked"
    INVALID_INPUT = "invalid_input"
    INVALID_OUTPUT = "invalid_output"
    UNSUPPORTED = "unsupported"
    UNCONFIGURED = "unconfigured"
    ERROR = "error"


class ToolCapabilityState(str, Enum):
    AVAILABLE = "available"
    DEGRADED = "degraded"
    FALLBACK_ACTIVE = "fallback_active"
    BLOCKED = "blocked"
    UNSUPPORTED = "unsupported"
    UNCONFIGURED = "unconfigured"
    UNAVAILABLE = "unavailable"


class RunPhase(str, Enum):
    INSTRUCTION_LOAD = "instruction_load"
    SKILL_SELECTION = "skill_selection"
    SUBAGENT_SELECTION = "subagent_selection"
    TOOL_EXECUTION = "tool_execution"
    REPLY_PLANNING = "reply_planning"
    VALIDATION = "validation"
    COMMAND_EMISSION = "command_emission"
    COMPLETED = "completed"
    FAILED = "failed"


class RunStatus(str, Enum):
    RUNNING = "running"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    PAUSED = "paused"
    COMPLETED = "completed"
    ABORTED = "aborted"
    FAILED = "failed"


class CheckpointStatus(str, Enum):
    CREATED = "created"
    RESUMED = "resumed"
    REPLAYED = "replayed"
    FAILED = "failed"


class CheckpointKind(str, Enum):
    TURN_BOUNDARY = "turn_boundary"
    TOOL_BEFORE = "tool_before"
    TOOL_AFTER = "tool_after"
    PAUSE_BOUNDARY = "pause_boundary"
    ABORT_BOUNDARY = "abort_boundary"


class FallbackClassification(str, Enum):
    CAPABILITY_UNAVAILABLE = "capability_unavailable"
    POLICY_DOWNGRADE = "policy_downgrade"
    VALIDATION_DOWNGRADE = "validation_downgrade"
    PROVIDER_FAILURE = "provider_failure"


class BodyDriverMode(str, Enum):
    BODYLESS = "bodyless"
    VIRTUAL = "virtual"
    SERIAL = "serial"
    TETHERED = "tethered"


class CharacterProjectionProfile(str, Enum):
    NO_BODY = "no_body"
    AVATAR_ONLY = "avatar_only"
    ROBOT_HEAD_ONLY = "robot_head_only"
    AVATAR_AND_ROBOT_HEAD = "avatar_and_robot_head"


class CompanionAudioMode(str, Enum):
    PUSH_TO_TALK = "push_to_talk"
    OPEN_MIC = "open_mic"


class CompanionContextMode(str, Enum):
    PERSONAL_LOCAL = "personal_local"
    VENUE_DEMO = "venue_demo"


class CompanionBehaviorCategory(str, Enum):
    GENERAL_CONVERSATION = "general_conversation"
    GREETING_REENTRY = "greeting_reentry"
    UNRESOLVED_THREAD_FOLLOW_UP = "unresolved_thread_follow_up"
    DAY_PLANNING = "day_planning"
    OBSERVE_AND_COMMENT = "observe_and_comment"
    EMOTIONAL_TONE_BOUNDS = "emotional_tone_bounds"
    VENUE_CONCIERGE = "venue_concierge"
    INCIDENT_ESCALATION = "incident_escalation"
    SAFE_DEGRADED_RESPONSE = "safe_degraded_response"


class VoiceRuntimeMode(str, Enum):
    STUB_DEMO = "stub_demo"
    DESKTOP_NATIVE = "desktop_native"
    OPEN_MIC_LOCAL = "open_mic_local"
    MACOS_SAY = "macos_say"
    BROWSER_LIVE = "browser_live"
    BROWSER_LIVE_MACOS_SAY = "browser_live_macos_say"


class PerceptionProviderMode(str, Enum):
    STUB = "stub"
    MANUAL_ANNOTATIONS = "manual_annotations"
    OLLAMA_VISION = "ollama_vision"
    NATIVE_CAMERA_SNAPSHOT = "native_camera_snapshot"
    BROWSER_SNAPSHOT = "browser_snapshot"
    VIDEO_FILE_REPLAY = "video_file_replay"
    MULTIMODAL_LLM = "multimodal_llm"


class PerceptionSnapshotStatus(str, Enum):
    OK = "ok"
    DEGRADED = "degraded"
    FAILED = "failed"


class PerceptionTier(str, Enum):
    WATCHER = "watcher"
    SEMANTIC = "semantic"


class PerceptionObservationType(str, Enum):
    PERSON_VISIBILITY = "person_visibility"
    PEOPLE_COUNT = "people_count"
    ENGAGEMENT_ESTIMATE = "engagement_estimate"
    VISIBLE_TEXT = "visible_text"
    NAMED_OBJECT = "named_object"
    LOCATION_ANCHOR = "location_anchor"
    PARTICIPANT_ATTRIBUTE = "participant_attribute"
    SCENE_SUMMARY = "scene_summary"


class SceneClaimKind(str, Enum):
    WATCHER_HINT = "watcher_hint"
    SEMANTIC_OBSERVATION = "semantic_observation"
    OPERATOR_ANNOTATION = "operator_annotation"
    MEMORY_ASSUMPTION = "memory_assumption"


class SemanticQualityClass(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class WatcherPresenceState(str, Enum):
    UNKNOWN = "unknown"
    NO_PERSON = "no_person"
    PERSON_PRESENT = "person_present"


class WatcherMotionState(str, Enum):
    UNKNOWN = "unknown"
    STEADY = "steady"
    CHANGED = "changed"


class WatcherEngagementShift(str, Enum):
    UNKNOWN = "unknown"
    ENGAGING = "engaging"
    DISENGAGING = "disengaging"
    STABLE = "stable"


class PerceptionEventType(str, Enum):
    PERSON_VISIBLE = "person_visible"
    PERSON_LEFT = "person_left"
    PEOPLE_COUNT_CHANGED = "people_count_changed"
    ENGAGEMENT_ESTIMATE_CHANGED = "engagement_estimate_changed"
    VISIBLE_TEXT_DETECTED = "visible_text_detected"
    NAMED_OBJECT_DETECTED = "named_object_detected"
    LOCATION_ANCHOR_DETECTED = "location_anchor_detected"
    PARTICIPANT_ATTRIBUTE_DETECTED = "participant_attribute_detected"
    SCENE_SUMMARY_UPDATED = "scene_summary_updated"


class EngagementState(str, Enum):
    UNKNOWN = "unknown"
    NOTICING = "noticing"
    ENGAGED = "engaged"
    DISENGAGING = "disengaging"
    LOST = "lost"


class FactFreshness(str, Enum):
    UNKNOWN = "unknown"
    FRESH = "fresh"
    AGING = "aging"
    STALE = "stale"
    EXPIRED = "expired"


class EnvironmentState(str, Enum):
    UNKNOWN = "unknown"
    QUIET = "quiet"
    BUSY = "busy"


class AttentionTargetType(str, Enum):
    NONE = "none"
    PARTICIPANT = "participant"
    SIGN = "sign"
    ROOM_LABEL = "room_label"
    POSTER = "poster"
    DESK = "desk"
    SCREEN = "screen"
    OBJECT = "object"
    OPERATOR = "operator"


class VisualAnchorType(str, Enum):
    SIGN = "sign"
    ROOM_LABEL = "room_label"
    POSTER = "poster"
    DESK = "desk"
    SCREEN = "screen"
    OBJECT = "object"


class InteractionExecutiveState(str, Enum):
    IDLE = "idle"
    MONITORING = "monitoring"
    LISTENING = "listening"
    THINKING = "thinking"
    RESPONDING = "responding"
    INTERRUPTED = "interrupted"
    ESCALATING = "escalating"
    SAFE_IDLE = "safe_idle"
    DEGRADED = "degraded"


class SocialRuntimeMode(str, Enum):
    IDLE = "idle"
    MONITORING = "monitoring"
    GREETING = "greeting"
    LISTENING = "listening"
    THINKING = "thinking"
    SPEAKING = "speaking"
    FOLLOW_UP_WAITING = "follow_up_waiting"
    OPERATOR_HANDOFF = "operator_handoff"
    DEGRADED_AWARENESS = "degraded_awareness"
    SAFE_IDLE = "safe_idle"


class ShiftOperatingState(str, Enum):
    BOOTING = "booting"
    READY_IDLE = "ready_idle"
    ATTRACTING_ATTENTION = "attracting_attention"
    ASSISTING = "assisting"
    WAITING_FOR_FOLLOW_UP = "waiting_for_follow_up"
    OPERATOR_HANDOFF_PENDING = "operator_handoff_pending"
    DEGRADED = "degraded"
    SAFE_IDLE = "safe_idle"
    QUIET_HOURS = "quiet_hours"
    CLOSING = "closing"


class ExecutiveDecisionType(str, Enum):
    AUTO_GREET = "auto_greet"
    AUTO_GREET_SUPPRESSED = "auto_greet_suppressed"
    ASK_CLARIFYING_QUESTION = "ask_clarifying_question"
    KEEP_LISTENING = "keep_listening"
    SHORTEN_REPLY = "shorten_reply"
    ESCALATE_TO_HUMAN = "escalate_to_human"
    STOP_FOR_INTERRUPTION = "stop_for_interruption"
    FORCE_SAFE_IDLE = "force_safe_idle"
    DEFER_REPLY = "defer_reply"
    NORMAL_REPLY = "normal_reply"


class SpeechOutputStatus(str, Enum):
    IDLE = "idle"
    LISTENING = "listening"
    TRANSCRIBING = "transcribing"
    THINKING = "thinking"
    SIMULATED = "simulated"
    SPEAKING = "speaking"
    COMPLETED = "completed"
    INTERRUPTED = "interrupted"
    FAILED = "failed"
    SKIPPED = "skipped"


class CompanionVoiceLoopState(str, Enum):
    IDLE = "idle"
    ARMED = "armed"
    VAD_WAITING = "vad_waiting"
    CAPTURING = "capturing"
    ENDPOINTING = "endpointing"
    TRANSCRIBING = "transcribing"
    THINKING = "thinking"
    SPEAKING = "speaking"
    BARGE_IN = "barge_in"
    INTERRUPTED = "interrupted"
    COOLDOWN = "cooldown"
    DEGRADED_TYPED = "degraded_typed"


class CompanionPresenceState(str, Enum):
    IDLE = "idle"
    LISTENING = "listening"
    ACKNOWLEDGING = "acknowledging"
    THINKING_FAST = "thinking_fast"
    SPEAKING = "speaking"
    TOOL_WORKING = "tool_working"
    REENGAGING = "reengaging"
    DEGRADED = "degraded"


class CompanionTriggerDecision(str, Enum):
    SPEAK_NOW = "speak_now"
    WAIT = "wait"
    OBSERVE_ONLY = "observe_only"
    REFRESH_SCENE = "refresh_scene"
    ASK_FOLLOW_UP = "ask_follow_up"
    SAFE_IDLE = "safe_idle"


class InitiativeStage(str, Enum):
    MONITOR = "monitor"
    CANDIDATE = "candidate"
    INFER = "infer"
    SCORE = "score"
    DECIDE = "decide"
    COOLDOWN = "cooldown"


class InitiativeDecision(str, Enum):
    IGNORE = "ignore"
    SUGGEST = "suggest"
    ASK = "ask"
    ACT = "act"


class ShiftSimulationStepActionType(str, Enum):
    SENSOR_EVENT = "sensor_event"
    SPEECH_TURN = "speech_turn"
    SHIFT_TICK = "shift_tick"
    INCIDENT_ACKNOWLEDGE = "incident_acknowledge"
    INCIDENT_ASSIGN = "incident_assign"
    INCIDENT_NOTE = "incident_note"
    INCIDENT_RESOLVE = "incident_resolve"


class GroundingSourceType(str, Enum):
    TOOL = "tool"
    VENUE = "venue"
    PERCEPTION = "perception"
    PERCEPTION_FACT = "perception_fact"
    WORLD_MODEL = "world_model"
    OPERATOR_NOTE = "operator_note"
    USER_MEMORY = "user_memory"
    PROFILE_MEMORY = "profile_memory"
    EPISODIC_MEMORY = "episodic_memory"
    SEMANTIC_MEMORY = "semantic_memory"
    EXECUTIVE_POLICY = "executive_policy"
    SHIFT_POLICY = "shift_policy"
    LIMITED_AWARENESS = "limited_awareness"


VALID_WEEKDAYS = {
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
}


def _normalize_weekdays(value: Any) -> list[str]:
    if value is None:
        return []
    items = value if isinstance(value, list) else [value]
    normalized: list[str] = []
    for item in items:
        if item is None:
            continue
        text = str(item).strip().lower()
        if not text:
            continue
        if text == "weekdays":
            normalized.extend(["monday", "tuesday", "wednesday", "thursday", "friday"])
            continue
        if text == "weekends":
            normalized.extend(["saturday", "sunday"])
            continue
        normalized.append(text)
    deduped: list[str] = []
    for item in normalized:
        if item not in deduped:
            deduped.append(item)
    return deduped


def _coerce_string_list(value: Any) -> list[str]:
    if value is None:
        return []
    items = value if isinstance(value, list) else [value]
    normalized: list[str] = []
    for item in items:
        text = str(item).strip()
        if text:
            normalized.append(text)
    return normalized


__all__ = [
    "AliasChoices",
    "AgentHookName",
    "AgentValidationStatus",
    "Any",
    "ActionTeacherFeedbackLabel",
    "BaseModel",
    "BodyDriverMode",
    "BenchmarkFamily",
    "BenchmarkComparisonMode",
    "CheckpointKind",
    "CheckpointStatus",
    "CharacterProjectionProfile",
    "CommandAckStatus",
    "CommandType",
    "CompanionAudioMode",
    "CompanionBehaviorCategory",
    "CompanionPresenceState",
    "CompanionContextMode",
    "InitiativeDecision",
    "InitiativeStage",
    "CompanionTriggerDecision",
    "CompanionVoiceLoopState",
    "ConfigDict",
    "DesktopDeviceKind",
    "DemoRunStatus",
    "DatasetSplitName",
    "EdgeAdapterDirection",
    "EdgeAdapterKind",
    "EdgeAdapterState",
    "EdgeTransportMode",
    "EnvironmentState",
    "EngagementState",
    "EpisodeAnnotationStatus",
    "EpisodeAssetKind",
    "EpisodeLabelName",
    "EpisodeSourceType",
    "ExecutiveDecisionType",
    "FallbackClassification",
    "FactFreshness",
    "Field",
    "GroundingSourceType",
    "IncidentListScope",
    "IncidentReasonCategory",
    "IncidentResolutionOutcome",
    "IncidentStatus",
    "IncidentTimelineEventType",
    "IncidentUrgency",
    "InteractionExecutiveState",
    "MemoryActionType",
    "MemoryDecisionOutcome",
    "MemoryLayer",
    "MemoryRetrievalBackend",
    "MemoryReviewStatus",
    "MemoryWriteReasonCode",
    "PlannerReplayMode",
    "PerceptionEventType",
    "PerceptionObservationType",
    "PerceptionProviderMode",
    "PerceptionSnapshotStatus",
    "PerceptionTier",
    "ReminderStatus",
    "ResponseMode",
    "ResearchExportFormat",
    "ReviewDebtState",
    "RedactionState",
    "RobotMode",
    "RuntimeBackendAvailability",
    "RuntimeBackendKind",
    "RunPhase",
    "RunStatus",
    "SceneClaimKind",
    "SemanticQualityClass",
    "SessionRoutingStatus",
    "SessionStatus",
    "ShiftOperatingState",
    "ShiftReportStatus",
    "ShiftSimulationStepActionType",
    "SocialRuntimeMode",
    "SpeechOutputStatus",
    "SensitiveContentFlag",
    "TeacherAnnotationScope",
    "TeacherMemoryFeedbackAction",
    "TeacherPrimaryKind",
    "TraceOutcome",
    "TransportState",
    "ToolCapabilityState",
    "ToolEffectClass",
    "ToolLatencyClass",
    "ToolPermissionClass",
    "ToolResultStatus",
    "VALID_WEEKDAYS",
    "VenueFallbackScenario",
    "VisualAnchorType",
    "VoiceRuntimeMode",
    "WatcherEngagementShift",
    "WatcherMotionState",
    "WatcherPresenceState",
    "_coerce_string_list",
    "_normalize_weekdays",
    "date",
    "datetime",
    "ExportRedactionProfile",
    "field_validator",
    "model_validator",
    "time",
    "utc_now",
    "uuid4",
]
