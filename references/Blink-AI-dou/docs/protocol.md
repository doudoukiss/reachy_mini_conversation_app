# Protocol Notes

This repository uses shared Pydantic contracts under `src/embodied_stack/shared/contracts/` for both brain and edge boundaries.

The shared contract surface now also includes `action.py` for the Stage 6 Action Plane Stage A/B baseline plus Stage 6C browser runtime, Stage 6D workflow runtime, and Stage 6E action flywheel: risk classes, policy decisions, approval state, preview/result records, approval resolution and replay records, execution records, connector descriptors and health, workflow definition and run records, `ActionPlaneStatus`, browser-specific records for browser session status, snapshots, target candidates, previews, and results, and durable action-bundle plus action-replay records.
The demo/operator contract surface now also includes local-companion certification records that separate machine readiness from repo/runtime correctness and publish the latest readiness state into appliance and runtime snapshots.
`src/embodied_stack/shared/models.py` remains as a compatibility re-export shim for the existing public import surface.

## Core robot contracts

### Events
- `RobotEvent`
- common event types:
  - `person_detected`
  - `speech_transcript`
  - `touch`
  - `button`
  - `heartbeat`
  - `telemetry`
  - `low_battery`
  - `network_state` via edge simulation input, normalized to `heartbeat` for the brain path
  - `shift_autonomy_tick` for bounded supervisor evaluation between interaction turns
  - perception-scene events:
    - `person_visible`
    - `person_left`
    - `people_count_changed`
    - `engagement_estimate_changed`
    - `visible_text_detected`
    - `named_object_detected`
    - `location_anchor_detected`
    - `scene_summary_updated`

### Commands
- `RobotCommand`
- supported command types:
  - `speak`
  - `display_text`
  - `set_led`
  - `set_head_pose`
  - `set_expression`
  - `set_gaze`
  - `perform_gesture`
  - `perform_animation`
  - `safe_idle`
  - `stop`
- unsupported for now:
  - `move_base`

### Edge responses
- `CommandAck`
- `TelemetrySnapshot`
- `TelemetryLogEntry`
- `TelemetryLogResponse`
- `HeartbeatStatus`
- `CommandHistoryEntry`
- `CommandHistoryResponse`
- `CapabilityProfile`
- `BodyPose`
- `BodyState`
- `BodyCapabilityProfile`
- `CharacterSemanticIntent`
- `CharacterProjectionStatus`
- `SemanticActionDescriptor`
- `HeadProfile`
- `ExpressionRequest`
- `GazeRequest`
- `GestureRequest`
- `AnimationRequest`
- `BodyPrimitiveSequenceRequest`
- `BodyExpressiveSequenceRequest`
- `BodyStagedSequenceRequest`
- `PrimitiveSequenceStep`
- `ExpressiveSequenceStep`
- `ExpressiveMotifReference`
- `StagedSequenceStage`
- `StagedSequenceAccent`
- `GroundedExpressionCatalogEntry`
- `GroundedExpressionCatalogExport`
- `AnimationTimeline`
- `CompiledBodyFrame`
- `CompiledAnimation`
- `VirtualBodyPreview`
- `JointCalibrationRecord`
- `HeadCalibrationRecord`
- `ServoHealthRecord`
- `BodyCommandOutcomeRecord`
- `BodyMotionControlSettingRecord`
- `BodyMotionControlAuditRecord`
- `BodyCalibrationJointAuditRecord`
- `BodyUsableRangeAuditRecord`
- `EdgeAdapterCapability`
- `EdgeAdapterHealth`
- `SimulatedSensorEventRequest`
- `SimulatedSensorEventResult`

### Body model details
- `HeadProfile`
  - YAML or JSON body-profile file
  - per-servo IDs, neutral, raw min/max, positive semantic direction, safe speed/acceleration, safe speed ceiling, transition defaults, auto-scan baud defaults, transport-boundary version, and coupling-rule notes
- semantic registry
  - planner-facing canonical names remain expression, gaze, gesture, animation, and `safe_idle` semantics rather than raw-servo surfaces
  - public semantic names now resolve through the grounded expression catalog before the compiler decides whether the implementation is a held state, a unit-level action, or a motif
  - maintained public held expressions are `neutral`, `friendly`, `thinking`, `concerned`, `confused`, `listen_attentively`, `focused_soft`, and `safe_idle`
  - maintained dynamic expressive behavior is represented through named motifs such as `guarded_close_right`, `skeptical_tilt_right`, `playful_peek_right`, and `bright_reengage`
  - the body layer also registers primitive-only motion names for family-proof and low-level operator lanes, including neutral-settle, head-turn, head-tilt, eye-shift, blink, wink, brow, lid-hold, and tiny-nod variants
  - legacy names remain accepted only through explicit aliases into the grounded catalog; unsupported names reject instead of inventing a direct composite pose
- `BodyPose`
  - normalized semantic pose for neck yaw/pitch/roll, eye yaw/pitch, upper/lower lids, and brows
  - per-side lid fields are supported for wink and mirrored-mechanics compilation
- `BodyCapabilityProfile` and `BodyState`
  - now also surface serial transport mode, transport health, transport error detail, readback position snapshots, calibration metadata, last command outcome, servo health, clamp/rejection notes, and the latest character-projection status for the body layer
- `CharacterSemanticIntent`
  - canonical semantic output of the character runtime before any avatar or robot-specific sink logic runs
- `CharacterProjectionStatus`
  - operator-facing record of whether the current intent stayed observe-only, updated preview only, or actually reached the robot head
- `SemanticActionDescriptor`
  - typed action metadata for semantic and primitive actions
  - now also exposes implementation kind, hardware support status, evidence source, structural and expressive units used, hold support, release policy, sequencing rule, safe tuning lane, and alias source
- `ExpressionRequest`, `GazeRequest`, `GestureRequest`, `AnimationRequest`
  - typed semantic request models for the body layer
- `BodyPrimitiveSequenceRequest`
  - operator-facing atomic primitive playlist with explicit ordered `PrimitiveSequenceStep` entries
- `BodyExpressiveSequenceRequest`
  - operator-facing stateful motif request with ordered expressive-sequence steps
- `BodyStagedSequenceRequest`
  - compatibility-stage expressive request retained for older staged body cues only
- `PrimitiveSequenceStep`, `StagedSequenceStage`, `StagedSequenceAccent`, `ExpressiveSequenceStep`, `ExpressiveMotifReference`
  - typed demo/operator payloads for primitive operator lanes, staged compatibility lanes, and the maintained motif-driven V8 lane
- `ExpressiveMotifDefinition`
  - internal registry record for named expressive motifs such as guarded close, skeptical tilt, playful peek, and doubtful side glance
- `GroundedExpressionCatalogEntry` and `GroundedExpressionCatalogExport`
  - machine-readable source of truth for supported units, persistent states, motifs, alias mapping, evidence source, and safe tuning lanes
- `AnimationTimeline`, `CompiledBodyFrame`, `CompiledAnimation`
  - compiled time-ordered embodiment frames that can drive virtual preview now and serial transport later
  - each compiled frame now surfaces transition profile, compiler notes, safe-idle compatibility, originating semantic name, selected motion envelope, and selected kinetics profile
  - compiled animations now also preserve primitive, staged, and motif grounding metadata such as `grounding`, `recipe_name`, `primitive_steps`, `motif_name`, `expressive_steps`, `step_kinds`, `structural_action`, `expressive_accents`, `stage_count`, `returns_to_neutral`, and primary or support actuator groups
- `VirtualBodyPreview`
  - readable demo/debug view with canonical semantic name, alias source when normalization occurred, gaze direction, gaze summary, neck pose, lid state, brow state, current animation name, normalized preview values, transition profile, safe-idle compatibility, and clamp/coupling/compiler notes
- `HeadCalibrationRecord` and `JointCalibrationRecord`
  - persisted `blink_head_calibration/v2` records for saved/template calibration, neutral capture, min/max ranges, mirrored-direction confirmations, coupling validation, safe speed/acceleration, transport metadata, transport confirmation state, transport-boundary version, and capture provenance
- `SemanticTuningRecord`
  - persisted `blink_head_semantic_tuning/v1` records for hardware-specific expressive tuning such as lid coupling, brow correction, neck weighting, and per-action pose overrides
- `ServoHealthRecord`
  - per-joint health snapshot with current position, target position, torque state, optional voltage/load/current/temperature/moving telemetry, explicit `voltage_raw` plus derived `voltage_volts`, power-health classification, error bits, last poll status, stable reason code, operator-readable status summary, and last command outcome
- `BodyCommandOutcomeRecord`
  - semantic command result surface with requested name, canonical name, source alias, accepted or rejected state, clamp status, transport mode, stable reason code, compiler notes, detail, primitive or staged grounding fields such as `grounding`, `recipe_name`, `primitive_steps`, `structural_action`, `expressive_accents`, `stage_count`, and `returned_to_neutral`, corroborated live-fault classification fields such as `suspect_voltage_event`, `readback_implausible`, `confirmation_read_performed`, and `confirmation_result`, plus investor-show startup power-preflight fields such as `power_health_classification`, `preflight_passed`, `preflight_failure_reason`, and `idle_voltage_snapshot`
- `BodyMotionControlSettingRecord` and `BodyMotionControlAuditRecord`
  - operator-facing record of profile defaults, calibration overrides, explicit demo overrides, effective live values, and whether speed or acceleration were actually applied and verified on the active transport
- `BodyCalibrationJointAuditRecord` and `BodyUsableRangeAuditRecord`
  - calibration-health record for each joint that compares profile bounds, saved calibration bounds, neutral position, suspicious-neutral margin, and the planning source used by maximum-safe range demos
- `BodyCommandAuditRecord` and `SemanticTeacherReviewRecord`
  - operator-facing action audit and teacher-feedback surfaces that preserve semantic family, canonical action, raw targets, readback, tuning source, primitive recipe trace or staged expressive trace, effective motion-control settings, usable-range audit, executed-frame telemetry, compact peak-pose summaries, corroborated live-fault fields, and investor-show idle power-preflight truth without exposing raw-servo control to the planner

## Brain application contracts

### Public event response
`CommandBatch` is the robot-facing brain response and includes only:

- `session_id`
- `reply_text`
- `commands`
- `trace_id`
- `status`

Reasoning metadata is not included in this public response.

### Session and memory contracts
- `SessionCreateRequest`
- `SessionRecord`
- `SessionRoutingStatus`
- `SessionSummary`
- `SessionResponseModeRequest`
- `OperatorNote`
- `UserMemoryRecord`
- `CompanionRelationshipProfile`
- `EpisodicMemoryRecord`
- `EpisodicMemoryListResponse`
- `SemanticMemoryRecord`
- `SemanticMemoryListResponse`
- `WorldState`
- `IncidentStaffSuggestion`
- `IncidentNoteRecord`
- `IncidentTicketRecord`
- `IncidentTimelineRecord`
- `IncidentListResponse`
- `IncidentTimelineResponse`
- `IncidentAcknowledgeRequest`
- `IncidentAssignRequest`
- `IncidentNoteRequest`
- `IncidentResolveRequest`
- `VenueScheduleWindow`
- `VenueProactiveGreetingPolicy`
- `VenueAnnouncementPolicy`
- `VenueEscalationKeywordRule`
- `VenueEscalationPolicy`
- `VenueFallbackInstruction`
- `VenueOperationsSnapshot`

### Trace and replay contracts
- `ActionRequestRecord`
- `ActionProposalRecord`
- `ActionApprovalRecord`
- `ActionPreviewRecord`
- `ActionExecutionResultRecord`
- `ActionApprovalResolutionRequest`
- `ActionApprovalResolutionRecord`
- `ActionReplayRequestRecord`
- `ActionReplayRecord`
- `ActionExecutionRecord`
- `ActionArtifactRecord`
- `ActionBundleManifestV1`
- `ActionBundleListResponse`
- `ActionBundleDetailRecord`
- `ActionApprovalEventRecord`
- `ActionConnectorCallRecord`
- `ActionRetryRecord`
- `ConnectorCatalogResponse`
- `ActionApprovalListResponse`
- `ActionExecutionListResponse`
- `ConnectorDescriptorRecord`
- `ConnectorHealthRecord`
- `WorkflowDefinitionRecord`
- `WorkflowTriggerRecord`
- `WorkflowStartRequestRecord`
- `WorkflowRunActionRequestRecord`
- `WorkflowRunActionResponseRecord`
- `WorkflowCatalogResponse`
- `WorkflowRunListResponse`
- `WorkflowStepRecord`
- `WorkflowRunRecord`
- `ActionPlaneStatus`
- `ReasoningTrace`
- `LatencyBreakdownRecord`
- `LiveTurnDiagnosticsRecord`
- `GroundingSourceRecord`
- `GroundingSourceType`
- `ToolInvocationRecord`
- `InstructionLayerRecord`
- `ToolSpecRecord`
- `SkillActivationRecord`
- `RunRecord`
- `RunListResponse`
- `RunPhase`
- `RunStatus`
- `CheckpointRecord`
- `CheckpointListResponse`
- `CheckpointStatus`
- `ToolValidationRecord`
- `TypedToolCallRecord`
- `SpecialistRoleDecisionRecord`
- `ValidationOutcomeRecord`
- `HookExecutionRecord`
- `TraceRecord`
- `TraceSummary`
- `ShiftOperatingState`
- `ShiftTimerSnapshot`
- `ShiftSupervisorSnapshot`
- `ShiftMetricsSnapshot`
- `ShiftTransitionRecord`
- `ShiftTransitionListResponse`
- `ShiftScoreSummary`
- `ShiftSimulationDefinition`
- `ShiftSimulationStepDefinition`
- `ShiftSimulationStepRecord`
- `ShiftReportSummary`
- `ShiftReportRecord`
- `ShiftReportListResponse`
- `ParticipantSessionBinding`
- `QueuedParticipantRecord`
- `ParticipantRouterSnapshot`
- `ScenarioDefinition`
- `ScenarioReplayRequest`
- `ScenarioReplayResult`
- `VoiceTurnRequest`
- `VoiceTurnResult`
- `BrowserAudioTurnRequest`
- `BrowserAudioTurnResult`
- `EmbodiedWorldModel`
- `WorldModelParticipant`
- `WorldModelAnchor`
- `WorldModelObservation`
- `AttentionTargetRecord`
- `SceneObserverEventRecord`
- `SceneObserverEventListResponse`
- `ExecutiveDecisionRecord`
- `ExecutiveDecisionListResponse`
- `WorldModelTransitionRecord`
- `WorldModelTransitionListResponse`
- `EngagementTimelinePoint`
- `LiveVoiceStateUpdateRequest`
- `PerceptionSourceFrame`
- `PerceptionConfidence`
- `PerceptionObservation`
- `PerceptionEventRecord`
- `PerceptionSnapshotRecord`
- `PerceptionFactRecord`
- `PerceptionFactListResponse`
- `PerceptionSnapshotSubmitRequest`
- `PerceptionSubmissionResult`
- `PerceptionReplayRequest`
- `PerceptionReplayResult`
- `PerceptionHistoryResponse`
- `PerceptionFixtureDefinition`
- `PerceptionFixtureCatalogResponse`
- `BrainResetRequest`
- `ResetResult`
- `DemoRunRequest`
- `DemoRunMetrics`

`BrowserAudioTurnRequest` is the browser-to-operator bridge for recorded microphone uploads. It now also supports an optional browser camera frame (`camera_image_data_url`, `camera_source_frame`, `camera_provider_mode`) so visual voice turns can refresh semantic perception before the dialogue reply is generated.
- `DemoFallbackEvent`
- `DemoRunStepRecord`
- `DemoRunRecord`
- `DemoRunListResponse`
- `EpisodeExportSessionRequest`
- `EpisodeExportRunRequest`
- `EpisodeExportShiftReportRequest`
- `EpisodeSessionMetadata`
- `EpisodeTranscriptEntry`
- `EpisodeToolCallRecord`
- `EpisodeCommandRecord`
- `EpisodeAcknowledgementRecord`
- `EpisodeTelemetryRecord`
- `EpisodeAssetReference`
- `EpisodeAnnotationLabel`
- `MemoryPolicyScoreRecord`
- `MemoryActionRecord`
- `MemoryReviewRecord`
- `MemoryRetrievalCandidateRecord`
- `MemoryRetrievalRecord`
- `MemoryRetrievalListResponse`
- `MemoryReviewDebtSummary`
- `MemoryReviewRequest`
- `TeacherReplyFeedback`
- `TeacherMemoryFeedback`
- `TeacherSceneFeedback`
- `TeacherEmbodimentFeedback`
- `TeacherOutcomeFeedback`
- `TeacherSupervisionSummary`
- `TeacherReviewRequest`
- `TeacherAnnotationRecord`
- `TeacherAnnotationListResponse`
- `EpisodeDatasetMembership`
- `EpisodeSummaryV2`
- `EpisodeRecordV2`
- `EpisodeManifestV2`
- `EpisodeListResponseV2`
- `PlannerDescriptor`
- `PlannerCatalogResponse`
- `PlannerInputRecord`
- `PlannerOutputRecord`
- `PlannerDiffRecord`
- `PlannerReplayRequest`
- `PlannerReplayStepRecord`
- `PlannerReplayRecord`
- `DatasetQualityMetric`
- `DatasetEpisodeEntry`
- `DatasetSplitRecord`
- `DatasetExportRequest`
- `DatasetManifestV1`
- `DatasetManifestListResponse`
- `ResearchExportRequest`
- `ResearchBundleManifest`
- `BenchmarkCaseResult`
- `BenchmarkRunRequest`
- `BenchmarkRunRecord`
- `BenchmarkCatalogResponse`
- `DemoCheckResult`
- `DemoCheckSuiteRecord`
- `LocalCompanionCertificationVerdict`
- `LocalCompanionCertificationIssueRecord`
- `LocalCompanionRubricScoreRecord`
- `LocalCompanionReadinessRecord`
- `LocalCompanionCertificationRecord`
- `OperatorVoiceTurnRequest`
- `OperatorInteractionResult`
- `OperatorConsoleSnapshot`
- `ConsoleRuntimeStatus`
- `ApplianceIssue`
- `ApplianceDeviceOption`
- `ApplianceDeviceCatalog`
- `ApplianceStatus`
- `ApplianceProfileRequest`
- `ApplianceBootstrapResponse`
- `DesktopDeviceHealth`
- `ShiftAutonomyTickRequest`
- `InitiativeScorecardRecord`
- `InitiativeGroundingRecord`
- `InitiativeStatus`
- `ShiftOverrideRequest`
- `SpeechTranscriptRecord`
- `SpeechOutputResult`
- `VoiceCancelResult`

`ShiftAutonomyTickRequest` may now carry a bounded `payload` map so the fast loop can inject initiative reply text or proactive-intent metadata without pretending that the slow loop has already streamed a full answer.
- `InvestorSceneDefinition`
- `InvestorSceneCatalogResponse`
- `InvestorSceneRunRequest`
- `InvestorSceneRunResult`
- `DemoSceneScorecard`
- `FinalActionRecord`

### Stage 2-3 perception/runtime additions
- shared enums now include:
  - `PerceptionTier`
  - `FactFreshness`
  - `EnvironmentState`
  - `SocialRuntimeMode`
  - `SceneClaimKind`
  - `SemanticQualityClass`
  - `WatcherPresenceState`
  - `WatcherMotionState`
  - `WatcherEngagementShift`
- `PerceptionSnapshotRecord` and `PerceptionSnapshotSubmitRequest` now carry:
  - `tier`
  - `trigger_reason`
  - `dialogue_eligible`
  - `device_awareness_constraints`
  - `uncertainty_markers`
  - `provenance`
- `PerceptionObservation`, `PerceptionFactRecord`, `WorldModelParticipant`, `WorldModelObservation`, `WorldModelAnchor`, and `AttentionTargetRecord` now also carry:
  - `claim_kind`
  - `quality_class`
  - `justification` for operator/service-relevant participant or scene corrections
- `SceneObserverEventRecord` now carries explicit watcher-signal fields:
  - `presence_state`
  - `motion_state`
  - `new_entrant`
  - `attention_target_hint`
  - `engagement_shift_hint`
  - `signal_confidence`
  - `refresh_recommended`
  - `refresh_reason`
- `EmbodiedWorldModel` now also carries:
  - `social_runtime_mode`
  - `environment_state`
  - `scene_freshness`
  - `device_awareness_constraints`
  - `uncertainty_markers`
  - `last_semantic_refresh_at`
  - `last_semantic_refresh_reason`
  - `speaker_hypothesis_source`
  - `speaker_hypothesis_expires_at`
  - `recent_participant_attributes`
- `WorldModelParticipant`, `WorldModelObservation`, `WorldModelAnchor`, and `AttentionTargetRecord` now carry freshness plus provenance metadata
- `ReasoningTrace`, `TraceSummary`, and `GroundingSourceRecord` now also expose inspectable scene-grounding metadata:
  - `grounded_scene_references`
  - `uncertainty_admitted`
  - `stale_scene_suppressed`
  - `fact_id`
  - `claim_kind`
  - `freshness`
- `ConsoleRuntimeStatus` and `OperatorConsoleSnapshot` now also expose:
  - richer `perception_freshness`
    - separate `watcher` and `semantic` freshness windows
  - `social_runtime_mode`
  - `last_semantic_refresh_reason`
  - `active_speaker_hypothesis`
  - `active_speaker_source`
  - `attention_target_source`
  - `greet_suppression_reason`
  - `scene_reply_guardrail`
  - `grounded_scene_references`
  - `watcher_buffer_count`
  - `scene_observer_events`
  - `initiative_engine`
    - current stage
    - last decision
    - scorecard
    - grounding signals
    - cooldown and suppression status
  - `action_plane`
    - `enabled`
    - `pending_approval_count`
    - `last_action_id`
    - `last_action_status`
    - connector-health summary
    - pending approval records

### Stage 5 research bridge additions
- planner boundary
  - interaction orchestration now depends on an in-process `PlannerAdapter` contract instead of calling `AgentRuntime` directly
  - the maintained default adapter is `agent_os_current`
  - a deterministic comparison adapter is available as `deterministic_baseline`
  - planner descriptors now also expose `capability_tags`, `strict_replay_policy_version`, `expected_input_surfaces`, `comparison_labels`, and `scoring_notes`
- `PlannerInputRecord`
  - packages the bounded planner input for replay or research export: source trace id, session id, user id, input text, event, session snapshot, world model, latest perception, tool invocations, memory updates, normalized scene facts, selected tool chain, retrieved memory candidates, planner input envelope, replay mode, and creation time
- `PlannerOutputRecord`
  - packages the bounded planner output for replay or research export: planner id/profile, engine name, reply text, intent, chosen skill, active playbook, playbook variant, chosen subagent, typed tool calls, selected tool chain, normalized scene facts used, embodiment output envelope, semantic commands, fallback markers/classification, run id, and notes
- `PlannerDiffRecord`
  - now classifies replay drift with `reason_code`, `divergence_class`, `severity`, and `acceptable_in_strict`
- `PlannerReplayRecord`
  - packages one episode replay run with replay id, planner id/profile, replay mode, comparison mode, determinism flag, strict replay policy version, policy notes, acceptable metadata-drift fields, environment fingerprint, source episode refs, step count, divergence summary, artifact refs, and per-step diffs
- `ResearchBundleManifest`
  - packages one derived `blink_research_bundle/v1` export linked to a source `blink_episode/v2`, including exporter version, provenance, split metadata, native artifact files, optional adapter exports, adapter export status, evidence refs, and notes
- benchmark/eval surfaces
  - canonical benchmark families are now:
    - `local_appliance_reliability`
    - `tool_protocol_integrity`
    - `perception_world_model_freshness`
    - `social_runtime_quality`
    - `memory_retrieval_quality`
    - `teacher_annotation_completeness`
    - `embodiment_action_validity`
    - `replay_determinism`
    - `planner_comparison_quality`
    - `export_dataset_hygiene`
    - `action_approval_correctness`
    - `action_idempotency`
    - `workflow_resume_correctness`
    - `browser_artifact_completeness`
    - `connector_safety_policy`
    - `proactive_action_restraint`
    - `action_trace_completeness`
  - legacy benchmark-family values remain readable for one compatibility iteration but are normalized onto the canonical set at run time
- `BenchmarkEvidencePackV1`
  - packages one benchmark/eval evidence directory under `runtime/demo_checks/benchmarks/evidence/<pack_id>/` with run metadata, environment metadata, source episode refs, replay outputs, scorecards, divergence summaries, logs, and additive refs for linked action bundles and action replays when action-focused families are requested
- `DatasetSplitRecord`
  - records stable split assignment so related sessions and replays stay in the same train/validation/test grouping
- `EpisodeSummaryV2` and `EpisodeManifestV2`
  - now also carry `derived_artifact_files` so the canonical episode record can reference research-side artifacts without changing the role of `blink_episode/v2`
- `BenchmarkRunRequest` and `BenchmarkRunRecord`
  - now also carry optional `planner_id`, `planner_profile`, `replay_id`, `replay_mode`, `comparison_mode`, `research_formats`, and `determinism_status`

### Agent runtime inspection contracts
- `AgentHookName`
  - `before_skill_selection`
  - `after_transcript`
  - `after_perception`
  - `before_tool_call`
  - `after_tool_result`
  - `before_reply`
  - `before_reply_generation`
  - `before_speak`
  - `after_turn`
  - `on_failure`
  - `on_safe_idle`
  - `on_provider_failure`
  - `on_session_close`
- `AgentValidationStatus`
  - `approved`
  - `downgraded`
  - `blocked`
  - `observed`
- `ToolPermissionClass`
  - `read_only`
  - `effectful`
  - `operator_sensitive`
- `ToolLatencyClass`
  - `fast`
  - `local_io`
  - `network`
  - `human_loop`
- `ToolEffectClass`
  - `read_only`
  - `state_mutation`
  - `speech_output`
  - `embodiment_command`
  - `operator_handoff`
  - `confirmation_gate`
- `ToolResultStatus`
  - `ok`, `degraded`, `blocked`, `invalid_input`, `invalid_output`, `unsupported`, `unconfigured`, and `error`
- `ToolCapabilityState`
  - `available`, `degraded`, `fallback_active`, `blocked`, `unsupported`, `unconfigured`, and `unavailable`
- `CheckpointKind`
  - `turn_boundary`, `tool_before`, `tool_after`, `pause_boundary`, and `abort_boundary`
- `FallbackClassification`
  - `capability_unavailable`, `policy_downgrade`, `validation_downgrade`, and `provider_failure`
- `RunRecord`
  - persists one bounded agent-runtime cycle with `run_id`, `session_id`, `trace_id`, `phase`, `status`, active skill, active playbook, active subagent, tool chain, checkpoint ids, intent, fallback classification, unavailable/intentionally-skipped capabilities, recovery notes, and replay/resume lineage
- `CheckpointRecord`
  - persists one inspectable pause point around a turn boundary, tool boundary, pause, or abort with `checkpoint_id`, `run_id`, `phase`, `kind`, tool name, payload, result payload, resumable payload, recovery notes, and resume/replay linkage
- `ToolSpecRecord`
  - surfaces one internal tool definition including version, family, canonical capability, schemas, permission class, latency class, effect class, confirmation requirement, failure modes, checkpoint policy, and observability policy
- `TypedToolCallRecord`
  - now also carries additive Action Plane metadata:
    - `action_id`
    - `connector_id`
    - `risk_class`
    - `approval_state`
    - `action_status`
    - `request_hash`
    - `idempotency_key`
- `ReasoningTrace`
  - now carries `run_id`, `run_phase`, `run_status`, `instruction_layers`, `active_skill`, `active_playbook`, `active_subagent`, `tool_chain`, `typed_tool_calls`, `hook_records`, `checkpoint_count`, `last_checkpoint_id`, `role_decisions`, `validation_outcomes`, `failure_state`, `fallback_reason`, `fallback_classification`, unavailable/intentionally-skipped capabilities, recovery status, and replay/resume lineage
- `TraceSummary`
  - now carries `run_id`, `run_phase`, `run_status`, `active_skill`, `active_playbook`, `active_subagent`, `tool_names`, `validation_statuses`, `checkpoint_count`, `last_checkpoint_id`, `failure_state`, `fallback_reason`, `fallback_classification`, unavailable/intentionally-skipped capabilities, and recovery status

### Desktop-local runtime and operator contracts
- `RuntimeBackendKind`
  - `text_reasoning`
  - `vision_analysis`
  - `embeddings`
  - `speech_to_text`
  - `text_to_speech`
- `RuntimeBackendAvailability`
  - `configured` means the backend is configured but not necessarily warm in memory yet
  - `warm` means the backend is configured and immediately usable
  - `unavailable` means the requested backend cannot currently be used
  - `degraded` means the selected backend is usable but intentionally limited
  - `fallback_active` means the requested backend was unavailable and Blink-AI selected an honest fallback
- `RuntimeBackendStatus`
  - typed operator/runtime record for one backend kind
  - surfaces `kind`, `backend_id`, `status`, `provider`, `model`, `local`, `cloud`, `requested_backend_id`, `fallback_from`, `detail`, and `last_checked_at`
  - may also surface `requested_model`, `active_model`, `reachable`, `installed`, `warm`, `keep_alive`, and `last_success_latency_ms` so local backend health is honest about cold starts and fallback
- `CompanionVoiceLoopState`
  - `idle`, `arming`, `listening`, `transcribing`, `thinking`, `speaking`, `interrupted`, `cooldown`, and `degraded_typed`
- `CompanionPresenceState`
  - `idle`, `listening`, `acknowledging`, `thinking_fast`, `speaking`, `tool_working`, `reengaging`, and `degraded`
- `CharacterPresenceShellState`
  - the shared optional avatar-shell projection of the fast loop
  - surfaces `surface_state`, `headline`, canonical semantic targets such as `expression_name` and `gaze_target`, optional `gesture_name` and `animation_name`, `motion_hint`, `warmth`, `curiosity`, `source_signals`, and a projected `BodyPose`
  - is built from the same runtime presence state, voice-loop state, initiative state, relationship continuity, and fallback state that drive the terminal-first companion
- `CharacterSemanticIntent`
  - the canonical semantic output of the character runtime
  - carries the resolved semantic expression, gaze, optional gesture and animation, warmth, curiosity, source signals, projected `BodyPose`, and whether hardware-safe-idle was actually requested
- `CharacterProjectionProfile`
  - chooses downstream sinks for the same semantic intent
  - `no_body`, `avatar_only`, `robot_head_only`, and `avatar_and_robot_head`
- `CharacterProjectionStatus`
  - typed observability record for the downstream projection path
  - surfaces the active projection profile, whether avatar and robot-head sinks are enabled, whether robot motion was actually allowed and applied, any block reason, and the last semantic intent snapshot
- `CompanionTriggerDecision`
  - `speak_now`, `wait`, `observe_only`, `refresh_scene`, `ask_follow_up`, and `safe_idle`
- `VoiceRuntimeMode`
  - `desktop_native` is the preferred live local-Mac conversation mode when native microphone and speaker backends are available
  - `macos_say`, `browser_live`, `browser_live_macos_say`, and `stub_demo` remain compatibility and fallback modes
- `PerceptionProviderMode`
  - `native_camera_snapshot` captures a local webcam frame and records provenance without inventing semantic scene claims on its own
  - `ollama_vision` runs local multimodal frame analysis through Ollama when configured
  - `multimodal_llm` remains the path that can turn a captured source frame into structured scene understanding
- `DesktopDeviceHealth`
  - typed per-device status for local microphone, speaker, and camera boundaries
  - surfaces `device_id`, `kind`, `state`, `backend`, `available`, `required`, `detail`, `configured_label`, `selected_label`, `reason_code`, `selection_note`, `fallback_active`, and `last_checked_at`
- `OperatorAuthStatus`
  - now also surfaces `auth_mode`, `session_ttl_seconds`, and `bootstrap_ttl_seconds`
  - auth mode is explicit as `appliance_localhost_trusted`, `configured_static_token`, or `disabled_dev`
- `ApplianceStatus`
  - browser-first local appliance status contract for setup gating
  - surfaces `setup_complete`, `setup_issues`, `auth_mode`, `config_source`, `device_preset`, selected native device labels, speaker-routing support, and Ollama model availability
  - now also includes `local_companion_readiness` so the browser appliance can surface latest certification state, machine blockers, degraded warnings, and the next action without inventing a second status API
- `ApplianceDeviceCatalog`
  - typed native-device listing for microphone and camera plus honest speaker-routing capability status
- `ConsoleRuntimeStatus`
  - includes `backend_profile`, `resolved_backend_profile`, `text_backend`, `vision_backend`, `embedding_backend`, `stt_backend`, `tts_backend`, `backend_status`, `default_live_voice_mode`, and `device_health`
  - now also includes `perception_freshness`, `memory_status`, and `fallback_state` so the local companion path can surface freshness, grounded memory state, and active degradation honestly
  - now also includes `always_on_enabled`, `supervisor`, `presence_runtime`, `character_projection_profile`, `character_semantic_intent`, `character_presence_shell`, `voice_loop`, `scene_observer`, `initiative_engine`, and `trigger_engine` so the operator can inspect the fast loop, the optional avatar-shell projection, the shared semantic intent, and the always-on supervisor rather than inferring them from transcript output alone
  - now also includes `agent_runtime_enabled`, `registered_skills`, `registered_subagents`, `registered_hooks`, `registered_tools`, `specialist_roles`, `run_id`, `run_phase`, `run_status`, `active_playbook`, `active_playbook_variant`, `active_subagent`, `tool_chain`, `checkpoint_count`, `last_checkpoint_id`, `failure_state`, `fallback_reason`, `fallback_classification`, unavailable/intentionally-skipped capabilities, `recovery_status`, `instruction_layers`, `last_active_skill`, `last_tool_calls`, `last_validation_outcomes`, `last_hook_records`, and `last_role_decisions`
  - now also includes `action_plane` so the operator snapshot can surface pending approvals, latest action execution state, and connector health while detailed connector, approval, history, and replay views stay on dedicated `/api/operator/action-plane/*` endpoints
  - now also includes `setup_complete`, `setup_issues`, `auth_mode`, `config_source`, `device_preset`, `selected_speaker_label`, `speaker_selection_supported`, `export_available`, and `episode_export_dir`
  - now also includes `local_companion_readiness` so `/console` and `local-companion` startup can render the same latest certification summary, machine blockers, and degraded warnings
  - now also includes `latest_live_turn_diagnostics` so browser-live turns can surface their latest timing breakdown, timeout classification, and timeout artifact path through the normal snapshot path
  - the operator snapshot therefore exposes both the requested backend profile and the actually selected backend path for each media or model capability
- `LiveTurnDiagnosticsRecord`
  - typed timing and timeout record for live browser turns on the Mac-local companion path
  - surfaces browser speech-recognition time, browser camera-capture time, server ingress time, camera refresh time, runtime execution time, persistence time and write count, TTS launch time, total time, timeout ceiling, timeout artifact path, timeout flag, stall classification, and whether the fast presence loop had to emit acknowledgement or slow-work feedback
- `OperatorInteractionResult`
  - now also includes `live_turn_diagnostics` so `/console`, local-companion checks, and certification lanes can inspect one turn’s end-to-end browser-live timing without a second diagnostics API
- `OperatorConsoleSnapshot`
  - now also includes `runs` and `checkpoints` so the browser console can inspect the latest persisted Agent OS state without leaving the snapshot payload
  - run export responses package the persisted run, checkpoints, tool calls, hook records, validation outcomes, role decisions, and recovery metadata into one local artifact
- `CharacterPresenceSurfaceSnapshot`
  - lightweight fast-loop surface contract for the optional `/presence` shell
  - includes `character_projection_profile`, `character_semantic_intent`, `character_presence_shell`, `presence_runtime`, `voice_loop`, `initiative_engine`, `relationship_continuity`, `fallback_state`, and optional `body_state`
- `InvestorSceneDefinition` and `InvestorSceneRunRequest`
  - may now carry `user_id` so maintained local companion stories can share durable profile memory across scenes instead of acting like isolated single turns
- `PerformanceCueKind`
- deterministic investor-show cue kinds now include `prompt`, `caption`, `narrate`, `run_scene`, `submit_text_turn`, `inject_event`, `perception_fixture`, `perception_snapshot`, `body_semantic_smoke`, `body_primitive_sequence`, `body_expressive_motif`, `body_staged_sequence`, `body_write_neutral`, `body_safe_idle`, `pause`, and `export_session_episode`
- `PerformanceCue`, `PerformanceSegment`, and `PerformanceShowDefinition`
  - source-controlled deterministic performance asset contracts for the investor-show lane
  - cue-level proof assertions may now target reply substrings, grounding presence, incident and safe-idle state, profile-memory facts and preferences, body-projection outcome, exported artifact presence, and arbitrary payload paths through `expect_payload_equals`
  - narration cues may now carry `localized_text`, `localized_fallback_text`, and a semantic `motion_track` made of `PerformanceMotionBeat` items so the same prewritten line can drive English or Chinese narration plus synchronized body motion
  - `body_primitive_sequence` carries an ordered list of primitive names and compiles them into one atomic animation with an explicit final neutral-confirm frame
  - `body_expressive_motif` carries a named motif reference and compiles it into one atomic animation with explicit held expressive state, staged release, and final neutral confirm
  - the maintained investor surface is now the V3-V7 family ladder plus the motif-driven V8 lane, not the older V1/V2 show pair
  - `PerformanceMotionBeat` may also declare `coverage_tags` so actuator coverage can be verified explicitly instead of inferred only from action names
- `PerformanceRunRequest`
  - supports filtered rehearsals through `segment_ids` and `cue_ids`
  - supports `deterministic_show` versus `live_companion_proof`, explicit `language`, narration voice preset, narration voice name, narration voice rate, `narration_only`, `proof_only`, forced degraded rehearsals through `force_degraded_cue_ids`, and clean-start runs through `reset_runtime`
- `PerformanceMotionOutcome`, `PerformanceMotionMarginRecord`, and `PerformanceActuatorCoverageSummary`
  - normalize public-show motion reporting across CLI, projector page, artifacts, and exports
  - motion outcomes are now always one of `live_applied`, `preview_only`, or `blocked`
  - margin records capture peak targets, live readback, minimum remaining raw-range margin by joint and by actuator group, safety thresholds by group, health flags, and whether the public-show safety gate passed
  - actuator coverage reports whether a run visibly exercised `head_yaw`, `head_pitch_pair`, `eye_yaw`, `eye_pitch`, `upper_lids`, `lower_lids`, and `brows`
- `PerformanceCueResult` and `PerformanceSegmentResult`
  - now surface per-cue and per-segment timing, drift, proof-check counts, degraded or fallback state, normalized motion outcome, motion margin records, and actuator coverage
- `PerformanceRunResult`
  - one typed result model for both in-progress and completed deterministic performance runs
- surfaces current segment title and investor claim, current prompt, caption, narration, proof backend mode, narration language and voice selection, selected segments and cues, total target duration, elapsed time, timing drift, timing breakdown buckets, proof-check counts, body-projection outcome, normalized last motion outcome, last motion margin record, actuator coverage, preview-only state, stop-requested state, degraded cues, artifact locations, selected tuning path, live arm lease author and port, per-group margin rollups, worst actuator group, margin-only degraded cues, whether eye pitch was exercised live, and the latest body-fault classification / confirmation result when a live serial cue becomes suspicious
- `PerformanceShowCatalogResponse`
  - surfaces the packaged deterministic shows plus `active_run_id` and `latest_run_id` for the projector page and operator polling path

## API surface

### Brain endpoints
- `GET /health`
- `GET /ready`
- `POST /api/reset`
- `POST /api/sessions`
- `GET /api/sessions`
- `GET /api/sessions/{session_id}`
- `POST /api/sessions/{session_id}/operator-notes`
- `POST /api/sessions/{session_id}/response-mode`
- `POST /api/events`
- `POST /api/voice/turn`
- `GET /api/world-state`
- `GET /api/world-model`
- `GET /api/shift-state`
- `GET /api/shift-transitions`
- `GET /api/executive/decisions`
- `GET /api/scenarios`
- `POST /api/scenarios/{scenario_name}/replay`
- `POST /api/demo-runs`
- `GET /api/demo-runs`
- `GET /api/demo-runs/{run_id}`
- `GET /api/shift-reports`
- `GET /api/shift-reports/{report_id}`
- `GET /api/operator/snapshot`
- `GET /api/operator/presence`
- `GET /api/operator/action-plane/status`
- `GET /api/operator/action-plane/connectors`
- `GET /api/operator/action-plane/approvals`
- `POST /api/operator/action-plane/approvals/{action_id}/approve`
- `POST /api/operator/action-plane/approvals/{action_id}/reject`
- `GET /api/operator/action-plane/history`
- `POST /api/operator/action-plane/replay`
- `GET /api/operator/action-plane/bundles`
- `GET /api/operator/action-plane/bundles/{bundle_id}`
- `POST /api/operator/action-plane/bundles/{bundle_id}/teacher-review`
- `POST /api/operator/action-plane/replays`
- `GET /api/operator/runs`
- `GET /api/operator/runs/{run_id}`
- `GET /api/operator/runs/{run_id}/checkpoints`
- `POST /api/operator/checkpoints/{checkpoint_id}/resume`
- `POST /api/operator/runs/{run_id}/pause`
- `POST /api/operator/runs/{run_id}/resume`
- `POST /api/operator/runs/{run_id}/abort`
- `GET /api/operator/runs/{run_id}/export`
- `POST /api/operator/runs/{run_id}/replay`
- `GET /api/operator/incidents`
- `GET /api/operator/incidents/{ticket_id}`
- `POST /api/operator/incidents/{ticket_id}/acknowledge`
- `POST /api/operator/incidents/{ticket_id}/assign`
- `POST /api/operator/incidents/{ticket_id}/notes`
- `POST /api/operator/incidents/{ticket_id}/resolve`
- `GET /api/operator/auth/status`
- `POST /api/operator/auth/login`
- `POST /api/operator/auth/logout`
- `POST /api/appliance/bootstrap`
- `GET /appliance/bootstrap/{token}`
- `GET /api/appliance/status`
- `GET /api/appliance/devices`
- `POST /api/appliance/profile`
- `POST /api/operator/text-turn`
- `POST /api/operator/inject-event`
- `POST /api/operator/safe-idle`
- `POST /api/operator/shift/tick`
- `POST /api/operator/shift/override`
- `POST /api/operator/voice/cancel`
- `GET /api/operator/body/semantic-library`
- `GET /api/operator/body/expression-catalog`
- `POST /api/operator/body/semantic-smoke`
- `POST /api/operator/body/primitive-sequence`
- `POST /api/operator/body/expressive-motif`
- `POST /api/operator/body/staged-sequence`
- `POST /api/operator/body/teacher-review`
- `POST /api/operator/perception/snapshots`
- `POST /api/operator/perception/replay`
- `GET /api/operator/perception/latest`
- `GET /api/operator/perception/history`
- `GET /api/operator/perception/fixtures`
- Stage 2 keeps those same endpoints and layers the watcher buffer into `OperatorConsoleSnapshot` instead of splitting a separate perception UI surface
- `GET /performance`
- `GET /api/operator/performance-shows`
- `POST /api/operator/performance-shows/{show_name}/run`
- `GET /api/operator/performance-shows/runs/{run_id}`
- `POST /api/operator/performance-shows/runs/{run_id}/cancel`
- `GET /api/operator/investor-scenes`
- `POST /api/operator/investor-scenes/{scene_name}/run`
- `GET /api/operator/planners`
- `POST /api/operator/replays/episode`
- `GET /api/operator/replays/{replay_id}`
- `GET /api/operator/episodes`
- `GET /api/operator/episodes/{episode_id}`
- `POST /api/operator/episodes/{episode_id}/export-research`
- `POST /api/operator/episodes/export-session`
- `POST /api/operator/episodes/export-demo-run`
- `POST /api/operator/episodes/export-shift-report`
- `GET /api/logs`
- `GET /api/traces`
- `GET /api/traces/{trace_id}`

### Edge endpoints
- `GET /health`
- `GET /ready`
- `POST /api/commands`
- `GET /api/telemetry`
- `GET /api/telemetry/log`
- `GET /api/heartbeat`
- `POST /api/sim/events`
- `POST /api/safe-idle`
- `GET /api/capabilities`
- `POST /api/reset`

## Rules

1. All shared request and response models live in `src/embodied_stack/shared/`.
2. Every command must have a `command_id`.
3. Unsafe or unsupported commands must return a rejected acknowledgement.
4. The brain may keep session and user memory, but the edge should remain deterministic.
5. The brain may emit semantic body commands, but raw servo IDs and transport details must stay behind the body or edge interfaces.
Feetech/ST protocol correctness, checksum validation, and low-byte-first packing belong to the body serial layer, not the brain.

## Runtime modes

Blink-AI now treats these modes as first-class:

- `desktop_bodyless`
- `desktop_virtual_body`
- `desktop_serial_body`
- `tethered_future`
- `degraded_safe_idle`

Legacy `simulated`, `tethered_demo`, and `hardware` values remain in the contract surface for compatibility with the existing edge package.
6. Trace reasoning is for logs and operator inspection, not for the edge-facing contract.
7. Voice turns must resolve into the same session and trace machinery used by text events.
8. Safe idle can be triggered by explicit stop, low battery, network degradation, or heartbeat timeout.
9. Demo run records must persist timestamps, end-to-end latency, trace latency, observed backend, command acknowledgements, fallback events, telemetry snapshots, and final world state.
10. The operator console must drive the same brain and edge paths used by the scripted demo flows, not a separate mock UI path.
11. Demo report storage should write local evidence bundles, not rely on an external observability platform.
12. Operator interaction results should expose end-to-end latency so demo-day behavior is measurable without external tooling.
13. `CommandAck.status` distinguishes applied, rejected, duplicate, and transport-error outcomes.
14. `command_id` is the edge idempotency key for duplicate-safe HTTP retries.
15. Telemetry and heartbeat snapshots may surface transport degradation with `transport_ok=false` and a degraded safe-idle reason when the brain cannot currently reach the edge.
16. Browser-live voice input is logged as a normal `speech_transcript` event with explicit source and input metadata rather than a separate hidden path.
17. Live voice state updates are operator-facing runtime state only; they do not bypass the normal session/trace path for final transcript turns.
18. Edge capability declaration and runtime adapter health are separate: `CapabilityProfile.adapters` declares enabled boundaries, while `TelemetrySnapshot.adapter_health` reports whether those boundaries are active, simulated, unavailable, degraded, or disabled.
19. `runtime_profile` on edge capabilities and telemetry identifies whether the edge is running the fake robot path, a Jetson-shaped simulated profile, or the unwired Jetson landing zone.
20. Adapter-aware command rejection must happen at the edge before command application when an actuator boundary is disabled or unavailable.
21. The browser console and operator/demo control APIs require local operator authentication unless auth is explicitly disabled in config.
22. Operator auth should use env vars or ignored runtime-local files, never tracked plaintext key files.
23. `/ready` is the operational readiness contract for both services; `/health` only means the process is up.
24. Perception runs on the Mac brain. The Jetson edge may emit simple sensor events, but it does not own scene understanding.
25. The default local runtime path is `embodied_stack.desktop.app`, which keeps the brain and embodiment runtime in one process for desktop modes.
26. Every perception result must include explicit confidence and source/provenance metadata before it is treated as a structured scene event.
27. Pilot-site `operations` data is part of the Mac-brain behavior contract: opening hours, quiet hours, closing windows, proactive greeting policy, announcement policy, escalation overrides, accessibility notes, and fallback instructions must stay data-driven and inspectable.
28. If perception fails or is unavailable, Blink-AI must surface limited awareness instead of turning uncertainty into facts.
29. Browser snapshots, fixture replay, and manual annotations should all normalize into the same perception snapshot and event contracts so replay and inspection stay consistent.
30. The embodied world model must keep confidence and expiry semantics for ephemeral scene state such as participants, attention, anchors, and recent visible text.
31. The watcher path and the semantic path must be distinguishable in the protocol through explicit tier metadata; watcher-only facts may shape social policy but must not masquerade as strong semantic grounding.
32. Every fresh scene fact must carry freshness and provenance semantics before it is used for grounded replies or operator inspection.
33. `SocialRuntimeMode` is now an explicit contract surface and should be propagated to world model, traces, and operator snapshot rather than inferred from `InteractionExecutiveState` alone.
31. Layered memory is explicit: `UserMemoryRecord` remains the profile-memory surface, while `EpisodicMemoryRecord` and `SemanticMemoryRecord` carry compact durable summaries and reusable grounded facts instead of relying only on raw turn logs.
32. `CompanionRelationshipProfile` under `UserMemoryRecord` should store only explicit continuity preferences such as greeting style, planning style, tone bounds, and interaction boundaries. It should not store inferred vulnerability or fake-intimacy cues.
33. `SkillActivationRecord.behavior_category` and operator-facing `MemoryStatus.relationship_continuity` are part of the inspectability contract for companion behavior and should remain stable enough for traces, `/status`, and operator snapshot consumers.
34. Social-interaction control policy must be inspectable through explicit executive decision records instead of hiding behavior only inside prompts.
35. A `stop` command with reason `user_interrupt` is turn-taking behavior, not a safe-idle fallback.
36. `ReasoningTrace` may now include structured phase latencies and explicit grounding sources for demo evidence and diagnostics.
37. Grounding sources may now distinguish profile memory, episodic memory, semantic memory, and fresh perception facts so replay can show what evidence actually supported a turn.
38. Demo bundles should preserve perception snapshots, world-model transitions, executive decisions, and grounding sources as local artifacts.
39. `InvestorSceneStep.action_type` may represent voice turns, injected events, perception fixture replay, or structured perception snapshots.
40. Episode exports must remain append-only local artifacts with a schema version, manifest, and explicit artifact file map.
41. The maintained export schema is now `blink_episode/v2`, while local read compatibility for older `blink_episode/v1` artifacts remains supported during transition.
42. Episode exports should package transcript, tool calls, perception, world-model transitions, executive decisions, commands, acknowledgements, telemetry, layered memory artifacts, scene facts, run lineage, teacher annotations, and annotation-ready labels in a deterministic JSON shape.
43. Durable memory writes should flow through policy-tracked actions and reviews so operator corrections, deletions, and teacher signals remain inspectable after the live session ends.
44. Layered durable memory records, `MemoryActionRecord`, and `MemoryReviewRecord` now carry shared scorecard fields, decision outcome, merge or supersede lineage, and review-debt state so promotion policy is inspectable after export.
45. `MemoryRetrievalRecord` is the first-class retrieval audit surface; runs and traces should preserve query text, backend, selected and rejected candidates, misses, latency, and whether the retrieval actually fed the reply.
46. Session episode exports may also include extra local-runtime artifacts such as `runtime_snapshot.json` so later replay and evaluation can inspect the model profile, active skill, memory status, perception freshness, fallback state, device health, and body mode that grounded the exported session.
47. Session episode exports may also include always-on local-runtime artifacts such as `presence_runtime.json`, `initiative_engine.json`, `voice_loop.json`, `scene_observer.json`, `trigger_history.json`, and `ollama_runtime.json` so fast-loop state, initiative scoring and suppression, supervisor decisions, scene refreshes, and warm or cold model behavior remain inspectable.
48. Streaming local companion exports may additionally include `audio_loop.json`, `partial_transcripts.json`, `scene_cache.json`, `memory_promotions.json`, and `model_residency.json` so open-mic activity, scene freshness, salience-based memory promotion, and local-model warm/cold behavior remain auditable after a session.
49. Redaction choices applied during episode export must be recorded explicitly in the episode summary and manifest.
50. Shift-level autonomy remains a Mac-brain concern; the Jetson edge still executes only simple deterministic commands and safety fallbacks.
51. The shift supervisor must expose explicit state, timers, and reason codes through shared models rather than hiding long-horizon behavior inside prompt text.
52. `shift_autonomy_tick` decisions must stay bounded, reviewable, and traceable through `ShiftTransitionRecord` artifacts and trace/report snapshots.
47. The always-on local supervisor must expose explicit voice-loop, observer, trigger, scene-cache, and audio-mode state rather than hiding continuous behavior inside an unstructured background thread.
48. Cheap camera observation may guide refresh decisions, but proactive scene-grounded speech must only rely on fresh semantic facts from a true semantic provider, not `native_camera_snapshot` alone.
49. Multi-visitor routing must remain deterministic and inspectable; the brain may track `likely_participant_*` handles, but it must not claim real identity or face recognition.
50. Session routing should expose active, paused, handed-off, and complete state through shared models so operators can see why a visitor is being served or queued.
51. Human handoff must become a first-class local incident ticket with explicit reason category, urgency, staff suggestion, current status, notes, and timestamps.
52. Incident state transitions must be auditable through shared timeline records and visible in reports, exports, and operator-facing APIs.
51. Day-in-the-life simulation inputs must stay file-driven and replayable so shift evidence can be regenerated without hardware or cloud dependencies.
52. Pilot-shift bundles must carry enough sessions, traces, commands, acknowledgements, telemetry, transitions, and incident artifacts to export into the existing episode path later.
53. Robot-side handoff wording must be driven by explicit incident status, not hidden prompt logic, so pending, acknowledged, resolved, and unavailable states remain reviewable.
54. Pilot-shift reports must remain deterministic, local-first artifacts with explicit JSON contracts and simple CSV metrics exports rather than hidden dashboard-only state.
55. The serial body landing zone must support dry-run and fixture replay without powered hardware, and live serial writes must be rejected when transport health is unconfirmed.
56. The first-class local interaction path is the desktop-local runtime on the Mac, with explicit microphone, speaker, and webcam device boundaries rather than a browser-only live loop.
57. `desktop_native` voice mode must report honest availability based on local device checks; it must not imply that a browser relay or serial body is active.
58. `OperatorConsoleSnapshot.runtime.device_health` is the operator-facing contract for microphone, speaker, and camera readiness, and `/ready` on the brain should surface device-level readiness detail for desktop-local modes.
59. `native_camera_snapshot` may capture source frames for local grounding, but if semantic analysis is unavailable Blink-AI must remain in limited-awareness mode instead of fabricating scene structure.
60. Backend routing is a first-class runtime contract on the Mac brain; text reasoning, vision, embeddings, STT, and TTS must each resolve through an explicit backend profile or per-kind override.
61. `/health`, `/ready`, and `OperatorConsoleSnapshot.runtime.backend_status` must report whether a backend is `configured`, `warm`, `unavailable`, `degraded`, or `fallback_active` rather than implying that all requested providers are live.
62. `fallback_active` means Blink-AI selected a different backend than requested. The fallback source should remain visible through `requested_backend_id` and `fallback_from`.
63. Local retrieval should remain usable without cloud dependencies through a deterministic local embedding fallback path, even when Ollama embeddings are unavailable.
64. `OperatorConsoleSnapshot.runtime.context_mode` must distinguish personal local operation from explicit venue/demo flows so the Mac-local product path does not silently default back to concierge behavior.
65. Ollama-backed runtime status must expose the last failure reason, the last failure time, the timeout applied to the last request, and whether a cold-start retry was consumed whenever Blink-AI falls back or degrades.
66. Machine-specific validation may write a runtime-generated local report under `runtime/diagnostics/`, but that report must describe actual binary or model discovery and local latency findings rather than committed aspirational configuration.
67. `desktop_serial_body` may now expose operator-facing body-control endpoints for connect, disconnect, scan, ping, read-health, arm, disarm, write-neutral, semantic-library lookup, semantic smoke, and teacher review, but those endpoints must call the same serial body driver and body helper code used elsewhere rather than shelling out to CLI subprocesses.
68. `BodyState` is the operator-facing live-serial truth surface; it must carry arm state, last poll time, last command audit, targets, readback, servo health, and the latest semantic action outcome so `/console`, runtime snapshots, and exports stay consistent.
69. Session exports may include `body_command_audits.json`, `body_motion_report_index.json`, `body_semantic_tuning.json`, `body_teacher_reviews.json`, `console_snapshot.json`, `body_telemetry.json`, `serial_failure_summary.json`, and `serial_request_response_history.json` when serial body actions occurred so live-head behavior, tuning, feedback, and failure evidence remain inspectable after export.
70. The maintained Stage E Mac hardware workflow may also write a `blink_serial_bench_suite/v1` artifact directory under `runtime/serial/bench_suites/`; it must wrap the existing doctor, readback, motion-report, telemetry, and console evidence instead of inventing a second serial truth surface.
71. Stage 6D workflow runs persist under `runtime/actions/workflows/` and must keep definitions in repo code, not in runtime-authored JSON.
72. `ActionRequestRecord`, `ActionApprovalRecord`, and `ActionExecutionRecord` may carry `workflow_run_id` and `workflow_step_id` so approval, replay, and execution history can link back to workflow runs.
73. `ActionPlaneStatus` now also summarizes workflow activity through additive fields such as active workflow count, waiting workflow count, and last workflow status.
74. Stage 6E writes live `blink_action_bundle/v1` sidecar artifacts under `runtime/actions/exports/action_bundles/`; bundle creation must happen during Action Plane and workflow lifecycle updates rather than waiting for later episode export.
75. Deterministic Action Plane replays write under `runtime/actions/exports/action_replays/` and must use stub or dry-run backends only; they must not launch live browser sessions or effectful live connector writes.
76. Stage 6F adds `GET /api/operator/action-plane/overview` as the decision-ready aggregation surface for the browser Action Center; it must summarize status, attention items, approvals, workflows, recent history, recent bundles, browser state, recent replays, and recent failures without replacing the existing detail endpoints.
77. `ActionExecutionStatus` may now carry `uncertain_review_required`, and `WorkflowPauseReason` may now carry `runtime_restart_review`, so restart reconciliation can surface uncertain nonterminal side effects honestly instead of assuming success.
78. Runtime restart reconciliation must never auto-approve, auto-replay, or silently auto-resume effectful browser or connector steps. Uncertain work must remain operator-visible until an explicit approve, retry, resume, or abandon decision is made.
79. `ApplianceStatus`, `ActionPreviewRecord`, and `ActionExecutionRecord` may now carry operator-facing Stage 6 guidance such as Action Plane readiness, browser degradation state, pending-review counts, `operator_summary`, and `next_step_hint` so `/console`, `blink-appliance`, and `local-companion` can render the same next-step guidance.
80. `uv run blink-appliance` is the browser-first localhost entrypoint for Stage 0 appliance operation; it must wrap the existing one-process runtime rather than creating a second independent runtime.
81. Appliance mode is a trusted localhost browser path: `/console` must open directly with no token prompt, while non-appliance service modes continue to use local operator-token auth.
82. Browser-live voice turns now carry bounded deadlines on the Mac-local companion path. A timed-out turn must fail loudly with a persisted timeout artifact under `runtime/diagnostics/live_turn_failures/` instead of hanging silently for minutes.
83. Browser-supplied camera frames are the freshest visual source for a browser-live turn. Once a fresh request camera frame has been applied, the generic visual-query refresh path must skip duplicate semantic refresh work for that same turn.
84. The stabilization entrypoints `make stabilize-fast`, `make stabilize-full`, and `make stabilize-live-local` are the maintained regression gates for the current local-companion hardening sprint.
82. Appliance setup state, config source, native device preset, selected speaker label, and speaker-routing support must remain visible through `ApplianceStatus` and `OperatorConsoleSnapshot.runtime`.
83. `blink_episode/v2` remains the canonical local artifact; derived research exports and linked action-bundle indexes must attach through `derived_artifact_files` rather than replacing the episode contract.
84. `TeacherAnnotationRecord` may now target `run`, `trace`, `episode`, `memory`, `action`, or `workflow_run`, and typed feedback should remain immutable supervision metadata rather than silently rewriting historical artifacts.
85. Planner swapping is an in-process, explicitly registered adapter boundary. Stage 5 does not introduce dynamic plugin discovery or a second runtime tree.
86. Episode replay artifacts must be written under `runtime/replays/` and must not mutate the source episode bundle they were derived from.
87. Replay must remain hardware-optional. Semantic body actions may replay through bodyless, virtual-body, or serial dry-run paths only unless a later explicitly gated live path is requested.
88. `blink_episode/v2` exports may now include `input_events`, `memory_retrievals`, `teacher_supervision_summary`, `benchmark_labels`, `dataset_memberships`, `redaction_profile`, and `sensitive_content_flags` so later research and operator review reuse the same canonical episode bundle.
89. `blink_research_bundle/v1` is a derived, neutral export that decomposes observations, raw inputs, world-model deltas, planner inputs/outputs, playbook runtime, tool traces, memory retrievals, memory actions, teacher feedback, labels, split metadata, linked action-bundle refs, linked action-replay refs, and action-quality metrics into separate JSON artifacts.
90. Research and dataset exports should default to `research_redacted`, write redacted copies only, and preserve the source episode bundle unchanged.
91. Dataset manifests are derived `blink_dataset_manifest/v1` artifacts built from exported episodes and research bundles. Split assignment must be stable and use a leakage-group key that keeps related sessions, replay lineage, teacher-linked corrections, root action bundle IDs, and workflow lineage in the same split.
92. Research adapters such as `lerobot_like` and `openx_like` are one-way convenience exports built from the native research bundle; they are not the canonical storage format.
93. Benchmark runs may score a source episode, a replayed planner run, a source-vs-replay comparison, or action-focused families through the same `BenchmarkRunRequest` contract instead of a second benchmark API family.
94. The no-robot local companion certification lane persists aggregate artifacts under `runtime/diagnostics/local_companion_certification/<cert_id>/` and publishes the latest readiness summary through `latest.json` and `latest_readiness.json`.
95. `LocalCompanionReadinessRecord` and `LocalCompanionCertificationRecord` must keep machine-readiness, repo/runtime correctness, companion behavior quality, operator UX quality, blocking issues, rubric scores, and next-action guidance separate so a degraded Mac does not masquerade as a product regression, and a product regression does not get mislabeled as a machine problem.
94. If a saved native device is missing, Blink-AI must fall back predictably and surface the exact fallback reason in operator-facing device health or setup status rather than silently choosing a different device.

## Versioning guidance

If you materially change event, session, trace, or command payloads:

- update shared models
- update tests
- update the scenario runner
- update this file
