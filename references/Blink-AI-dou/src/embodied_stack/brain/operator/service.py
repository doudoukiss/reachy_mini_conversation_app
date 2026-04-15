from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
import json
import logging
import os
from pathlib import Path
from time import perf_counter, time
from uuid import uuid4

from embodied_stack.backends.router import BackendRouter
from embodied_stack.body.presence_shell import build_character_presence_shell, build_character_semantic_intent
from embodied_stack.body.projection import resolve_character_projection_profile
from embodied_stack.brain.agent_os.tools import BrowserTaskToolOutput
from embodied_stack.brain.freshness import DEFAULT_FRESHNESS_POLICY
from embodied_stack.brain.live_voice import LiveVoiceRuntimeManager
from embodied_stack.brain.perception import PerceptionService
from embodied_stack.brain.visual_query import looks_like_visual_query
from embodied_stack.config import Settings
from embodied_stack.desktop.devices import DesktopDeviceRegistry, list_avfoundation_devices
from embodied_stack.observability import log_event
from embodied_stack.desktop.profiles import summarize_desktop_profile
from embodied_stack.desktop.runtime_profile import (
    APPLIANCE_RUNTIME_DIR_FIELDS,
    ApplianceProfileStore,
    apply_runtime_profile_to_live_settings,
    build_appliance_startup_summary,
    configured_device_label,
    default_appliance_profile,
)
from embodied_stack.demo.coordinator import DemoCoordinator, EdgeGateway, EdgeGatewayError
from embodied_stack.demo.benchmarks import BenchmarkRunner
from embodied_stack.demo.episodes import BlinkEpisodeExporter
from embodied_stack.demo.performance_show import PerformanceShowManager
from embodied_stack.demo.replay_harness import EpisodeReplayHarness
from embodied_stack.demo.research import DatasetManifestBuilder, ResearchBundleExporter
from embodied_stack.demo.shift_metrics import calculate_shift_metrics, collect_shift_evidence
from embodied_stack.demo.shift_reports import ShiftReportStore
from embodied_stack.demo.investor_scenes import INVESTOR_SCENES, list_investor_scenes
from embodied_stack.persistence import write_json_atomic
from embodied_stack.shared.contracts import (
    ActionApprovalListResponse,
    ActionApprovalResolutionRecord,
    ActionApprovalResolutionRequest,
    ActionBundleDetailRecord,
    ActionBundleListResponse,
    ActionCenterItemRecord,
    ActionCenterOverviewRecord,
    ActionInvocationOrigin,
    ActionPlaneStatus,
    ActionExecutionListResponse,
    ActionReplayRecord,
    ActionReplayRequestRecord,
    CommandAck,
    CommandAckStatus,
    CommandBatch,
    ApplianceDeviceCatalog,
    ApplianceDeviceOption,
    ApplianceIssue,
    ApplianceProfileRequest,
    ApplianceStatus,
    BodyActionResult,
    BodyArmRequest,
    BodyConnectRequest,
    BodyExpressiveSequenceRequest,
    BodyIdsRequest,
    BodyPrimitiveSequenceRequest,
    BodyStagedSequenceRequest,
    BodyServoLabMoveRequest,
    BodyServoLabReadbackRequest,
    BodyServoLabSaveCalibrationRequest,
    BodyServoLabSweepRequest,
    BodySemanticSmokeRequest,
    BodyTeacherReviewRequest,
    BrowserActionTaskRequest,
    BrowserRuntimeStatusRecord,
    CheckpointListResponse,
    CharacterPresenceSurfaceSnapshot,
    CompanionPresenceStatus,
    CompanionSupervisorStatus,
    CompanionVoiceLoopStatus,
    CompanionContextMode,
    ConsoleRuntimeStatus,
    ConnectorCatalogResponse,
    DatasetExportRequest,
    DatasetManifestListResponse,
    DatasetManifestV1,
    DesktopDeviceKind,
    DemoSceneScorecard,
    EpisodeExportRunRequest,
    EpisodeExportSessionRequest,
    EpisodeExportShiftReportRequest,
    EpisodeListResponse,
    EpisodeRecord,
    ExportRedactionProfile,
    FallbackState,
    FactFreshness,
    FinalActionRecord,
    FreshnessWindowStatus,
    GroundingSourceRecord,
    IncidentAcknowledgeRequest,
    IncidentAssignRequest,
    IncidentListScope,
    IncidentNoteRequest,
    IncidentResolveRequest,
    IncidentTicketRecord,
    IncidentTimelineResponse,
    InitiativeStatus,
    InvestorSceneCatalogResponse,
    InvestorSceneDefinition,
    InvestorSceneRunRequest,
    InvestorSceneRunResult,
    LatencyBreakdownRecord,
    LiveTurnDiagnosticsRecord,
    LiveVoiceStateUpdateRequest,
    LogListResponse,
    MemoryStatus,
    MemoryRetrievalListResponse,
    MemoryReviewDebtSummary,
    OperatorConsoleSnapshot,
    OperatorInteractionResult,
    OperatorVoiceTurnRequest,
    PerceptionProviderMode,
    PerceptionFreshnessStatus,
    PerceptionTier,
    PerceptionReplayRequest,
    PerceptionReplayResult,
    PerceptionSnapshotRecord,
    PerceptionSnapshotSubmitRequest,
    PerceptionSourceFrame,
    PerceptionSubmissionResult,
    PerformanceShowCatalogResponse,
    PerformanceRunRequest,
    PerformanceRunResult,
    ResponseMode,
    RelationshipContinuityStatus,
    RobotEvent,
    RunListResponse,
    RunRecord,
    SemanticMemoryListResponse,
    ReminderStatus,
    SessionStatus,
    ShiftAutonomyTickRequest,
    ShiftOperatingState,
    WorkflowCatalogResponse,
    WorkflowRunActionRequestRecord,
    WorkflowRunActionResponseRecord,
    WorkflowRunListResponse,
    WorkflowRunRecord,
    WorkflowStartRequestRecord,
    ShiftOverrideRequest,
    SimulatedSensorEventRequest,
    SpeechOutputResult,
    SpeechOutputStatus,
    TraceOutcome,
    VoiceRuntimeMode,
    RuntimeBackendAvailability,
    RuntimeBackendKind,
    SceneObserverStatus,
    SceneObserverEventListResponse,
    PlannerCatalogResponse,
    PlannerReplayRecord,
    PlannerReplayRequest,
    BenchmarkEvidencePackListResponse,
    BenchmarkEvidencePackV1,
    ResearchBundleManifest,
    ResearchExportRequest,
    RunExportArtifact,
    RunExportResponse,
    TriggerEngineStatus,
    UserMemoryRecord,
    utc_now,
)
from embodied_stack.shared.contracts.demo import ScorecardCriterion
from embodied_stack.shared.contracts.brain import MemoryReviewRequest
from embodied_stack.shared.contracts.episode import (
    BenchmarkCatalogResponse,
    BenchmarkRunRecord,
    BenchmarkRunRequest,
    EpisodeListResponseV2,
    EpisodeRecordV2,
    TeacherAnnotationListResponse,
    TeacherAnnotationRecord,
    TeacherReviewRequest,
)

logger = logging.getLogger(__name__)


def _coerce_float(value: object) -> float | None:
    if value is None or value == "":
        return None
    try:
        return round(float(value), 2)
    except (TypeError, ValueError):
        return None


@dataclass
class OperatorConsoleService:
    _PERCEPTION_FRESH_MAX_AGE_SECONDS = 15.0
    _PERCEPTION_MAX_AGE_SECONDS = DEFAULT_FRESHNESS_POLICY.semantic_window.ttl_seconds

    settings: Settings
    orchestrator: object
    edge_gateway: EdgeGateway
    demo_coordinator: DemoCoordinator
    shift_report_store: ShiftReportStore
    voice_manager: LiveVoiceRuntimeManager
    backend_router: BackendRouter
    device_registry: DesktopDeviceRegistry
    perception_service: PerceptionService
    episode_exporter: BlinkEpisodeExporter
    shift_runner: object | None = None
    console_url: str | None = None
    console_launch_state: str | None = None
    terminal_frontend_state: str = "unknown"
    terminal_frontend_detail: str | None = None
    operator_auth_mode: str | None = None
    operator_auth_token_source: str | None = None
    operator_auth_runtime_file: str | None = None
    appliance_profile_store: ApplianceProfileStore | None = None
    performance_show_manager: PerformanceShowManager | None = None

    def _profile_store(self) -> ApplianceProfileStore:
        return self.appliance_profile_store or ApplianceProfileStore(self.settings.blink_appliance_profile_file)

    def _benchmark_runner(self) -> BenchmarkRunner:
        return BenchmarkRunner.from_settings(
            settings=self.settings,
            episode_exporter=self.episode_exporter,
        )

    def _replay_harness(self) -> EpisodeReplayHarness:
        return EpisodeReplayHarness.from_settings(
            settings=self.settings,
            episode_exporter=self.episode_exporter,
        )

    def _research_exporter(self) -> ResearchBundleExporter:
        return ResearchBundleExporter.from_settings(
            settings=self.settings,
            episode_exporter=self.episode_exporter,
        )

    def _dataset_builder(self) -> DatasetManifestBuilder:
        return DatasetManifestBuilder.from_settings(
            settings=self.settings,
            episode_exporter=self.episode_exporter,
        )

    def _required_ollama_models(self) -> list[str]:
        required: list[str] = []
        for kind in (
            RuntimeBackendKind.TEXT_REASONING,
            RuntimeBackendKind.VISION_ANALYSIS,
            RuntimeBackendKind.EMBEDDINGS,
        ):
            backend_id = self.backend_router.selected_backend_id(kind)
            if backend_id == "ollama_text":
                model = self.settings.ollama_text_model or self.settings.ollama_model
            elif backend_id == "ollama_vision":
                model = self.settings.ollama_vision_model or self.settings.ollama_model
            elif backend_id == "ollama_embed":
                model = self.settings.ollama_embedding_model
            else:
                model = None
            if model and model not in required:
                required.append(model)
        return required

    def _selected_microphone_label(self) -> str | None:
        getter = getattr(self.device_registry, "selected_microphone_label", None)
        if callable(getter):
            return getter()
        return None

    def _selected_camera_label(self) -> str | None:
        getter = getattr(self.device_registry, "selected_camera_label", None)
        if callable(getter):
            return getter()
        return None

    def _selected_speaker_label(self) -> str:
        getter = getattr(self.device_registry, "selected_speaker_label", None)
        if callable(getter):
            return getter()
        requested = (getattr(self.settings, "blink_speaker_device", "system_default") or "system_default").strip()
        return requested if requested != "default" else "system_default"

    def _speaker_selection_supported(self) -> bool:
        getter = getattr(self.device_registry, "speaker_selection_supported", None)
        if callable(getter):
            return bool(getter())
        return False

    def _configured_microphone_label(self) -> str:
        return configured_device_label(self.settings.blink_mic_device, default_value="default")

    def _configured_camera_label(self) -> str:
        return configured_device_label(self.settings.blink_camera_device, default_value="default")

    def _configured_speaker_label(self) -> str:
        return configured_device_label(self.settings.blink_speaker_device, default_value="system_default")

    def _directory_writable(self, path: Path) -> bool:
        try:
            path.mkdir(parents=True, exist_ok=True)
        except OSError:
            return False
        return path.is_dir() and os.access(path, os.W_OK)

    def _browser_runtime_state(self, browser_status: BrowserRuntimeStatusRecord | None) -> str:
        if browser_status is None:
            return "unknown"
        if browser_status.supported and browser_status.configured:
            return f"ready:{browser_status.backend_mode}"
        if browser_status.backend_mode == "disabled":
            return "disabled"
        return f"degraded:{browser_status.backend_mode}"

    def _next_action_plane_step(
        self,
        *,
        action_plane_ready: bool,
        pending_action_count: int,
        waiting_workflow_count: int,
        review_required_count: int,
        browser_runtime_state: str | None,
    ) -> str | None:
        if not action_plane_ready:
            return "Review Action Plane readiness issues before relying on Stage 6 actions."
        if review_required_count > 0:
            return "Open the Action Center and review restart-recovery items before resuming workflows."
        if pending_action_count > 0:
            return "Open the Action Center and resolve pending approvals."
        if waiting_workflow_count > 0:
            return "Open the Action Center and resume or retry blocked workflows."
        if browser_runtime_state and browser_runtime_state.startswith("degraded"):
            return "Browser actions are degraded; continue with non-browser connectors or install the browser runtime."
        return "Action Center ready."

    def _describe_action_plane_reason(
        self,
        *,
        detail: str | None,
        policy_decision: object | None = None,
        risk_class: object | None = None,
        connector_id: str | None = None,
        action_name: str | None = None,
    ) -> str:
        risk_value = getattr(risk_class, "value", risk_class) or "-"
        decision_value = getattr(policy_decision, "value", policy_decision) or "-"
        action_label = action_name or "action"
        connector_label = connector_id or "connector"
        match detail:
            case "operator_approval_required":
                return (
                    f"Blink paused before {action_label} because it is an operator-sensitive write. "
                    "Review it, then approve or reject it explicitly."
                )
            case "implicit_operator_approval":
                return (
                    f"{action_label} counts as operator-launched work, so Blink does not need a second approval."
                )
            case "local_write_allowed":
                return f"{action_label} is a low-risk local write, so Blink may execute it without extra approval."
            case "read_only_allowed":
                return f"{action_label} is read-only, so Blink may inspect it without extra approval."
            case "proactive_local_write_preview_only":
                return (
                    f"Blink only previewed {action_label}. Proactive local writes stay preview-only by default."
                )
            case "risk_class_rejected":
                return (
                    f"Blink blocked {action_label} because it falls into a high-risk or irreversible action class."
                )
            case "connector_missing":
                return f"Blink could not run {action_label} because {connector_label} is missing from this runtime."
            case "connector_unconfigured":
                return f"Blink could not run {action_label} because {connector_label} is not configured."
            case "connector_unsupported":
                return f"Blink could not run {action_label} because {connector_label} does not support it."
            case "policy_default_reject":
                return (
                    f"Blink blocked {action_label} because the policy layer did not find a safe allow path "
                    f"(decision={decision_value}, risk={risk_value})."
                )
        if detail:
            return detail.replace("_", " ")
        return f"Blink paused {action_label} for policy review (decision={decision_value}, risk={risk_value})."

    def _device_health_map(self, *, default_voice_mode: VoiceRuntimeMode) -> dict[str, object]:
        return {
            item.kind.value: item
            for item in self.device_registry.describe(default_voice_mode=default_voice_mode)
        }

    def _local_companion_readiness(self):
        try:
            from embodied_stack.demo.local_companion_certification import load_latest_local_companion_readiness
        except Exception:
            return None
        return load_latest_local_companion_readiness(self.settings)

    def _live_turn_diagnostic_root(self) -> Path:
        return Path(self.settings.blink_live_turn_diagnostic_dir)

    def _load_latest_live_turn_diagnostics(self) -> LiveTurnDiagnosticsRecord | None:
        path = self._live_turn_diagnostic_root() / "latest.json"
        if not path.exists():
            return None
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            diagnostics_payload = payload.get("diagnostics")
            if not isinstance(diagnostics_payload, dict):
                return None
            return LiveTurnDiagnosticsRecord.model_validate(diagnostics_payload)
        except Exception:
            logger.exception("latest_live_turn_diagnostics_load_failed", extra={"path": str(path)})
            return None

    def _build_live_turn_diagnostics(self, request: OperatorVoiceTurnRequest) -> LiveTurnDiagnosticsRecord:
        metadata = dict(request.input_metadata or {})
        client_submit_wall_time_ms = _coerce_float(metadata.get("client_submit_wall_time_ms"))
        server_ingress_ms = None
        if client_submit_wall_time_ms is not None:
            server_ingress_ms = round(max(0.0, (time() * 1000.0) - client_submit_wall_time_ms), 2)
        visual_query = self._looks_like_visual_query(request.input_text)
        return LiveTurnDiagnosticsRecord(
            source=request.source,
            visual_query=visual_query,
            camera_frame_attached=bool(request.camera_image_data_url),
            spoken_reply_requested=bool(request.speak_reply),
            stt_backend=str(metadata.get("transcription_backend")) if metadata.get("transcription_backend") is not None else None,
            browser_speech_recognition_ms=_coerce_float(metadata.get("browser_speech_recognition_ms")),
            browser_camera_capture_ms=_coerce_float(metadata.get("browser_camera_capture_ms")),
            server_ingress_ms=server_ingress_ms,
            stt_ms=_coerce_float(metadata.get("stt_latency_ms")),
        )

    def capture_live_turn_timeout_artifact(
        self,
        *,
        request: OperatorVoiceTurnRequest,
        timeout_seconds: float,
        stall_classification: str = "server_handler_stall",
    ) -> LiveTurnDiagnosticsRecord:
        diagnostics = self._build_live_turn_diagnostics(request)
        diagnostics.timeout_seconds = round(timeout_seconds, 2)
        diagnostics.timeout_triggered = True
        diagnostics.stall_classification = stall_classification
        diagnostics.notes.append("browser_live_turn_timeout")

        root = self._live_turn_diagnostic_root()
        root.mkdir(parents=True, exist_ok=True)
        artifact_id = f"live-turn-timeout-{utc_now().strftime('%Y%m%d%H%M%S')}-{uuid4().hex[:8]}"
        artifact_dir = root / artifact_id
        artifact_dir.mkdir(parents=True, exist_ok=True)
        artifact_path = artifact_dir / "timeout.json"
        diagnostics.timeout_artifact_path = str(artifact_path)
        payload = {
            "artifact_id": artifact_id,
            "created_at": utc_now().isoformat(),
            "request": request,
            "diagnostics": diagnostics,
            "latest_perception": self.perception_service.get_latest_snapshot(request.session_id)
            or self.perception_service.get_latest_snapshot(),
            "voice_state": self.voice_manager.get_state(
                request.voice_mode,
                request.session_id or self._resolve_session_id("console-live"),
            ),
            "backend_status": self.backend_router.runtime_statuses(),
            "action_plane_status": (
                self._action_plane_runtime().action_plane_status()
                if getattr(self.orchestrator, "agent_runtime", None) is not None
                else None
            ),
        }
        write_json_atomic(artifact_path, payload)
        write_json_atomic(root / "latest.json", payload)
        return diagnostics

    def get_appliance_status(self) -> ApplianceStatus:
        store = self._profile_store()
        profile = store.load()
        setup_complete = bool(profile and profile.setup_complete) if self.settings.blink_appliance_mode else True
        issues: list[ApplianceIssue] = []
        default_voice_mode = self.default_live_voice_mode()
        device_health = self._device_health_map(default_voice_mode=default_voice_mode)
        local_companion_readiness = self._local_companion_readiness()

        for field_name in APPLIANCE_RUNTIME_DIR_FIELDS:
            path = Path(getattr(self.settings, field_name))
            directory = path if path.suffix == "" else path.parent
            if not directory.exists():
                issues.append(
                    ApplianceIssue(
                        category="runtime",
                        severity="error",
                        message=f"Runtime directory is missing: {directory}",
                        blocking=True,
                    )
                )

        if self.settings.blink_appliance_mode and profile is None:
            issues.append(
                ApplianceIssue(
                    category="setup",
                    severity="warning",
                    message="Local appliance setup has not been saved yet. Review devices and confirm the profile.",
                    blocking=True,
                )
            )

        ollama_snapshot = self.backend_router.ollama_probe.snapshot()
        required_models = self._required_ollama_models()
        missing_models = [model for model in required_models if model not in ollama_snapshot.installed_models]
        if required_models and not ollama_snapshot.reachable:
            issues.append(
                ApplianceIssue(
                    category="ollama",
                    severity="warning",
                    message=f"Ollama is not reachable at {self.settings.ollama_base_url}. Typed and rule-based fallback remain available.",
                    blocking=False,
                )
            )
        elif missing_models:
            issues.append(
                ApplianceIssue(
                    category="ollama",
                    severity="warning",
                    message="Missing local Ollama models: " + ", ".join(missing_models),
                    blocking=False,
                )
            )

        for item in device_health.values():
            if item.available:
                continue
            issues.append(
                ApplianceIssue(
                    category=item.kind.value,
                    severity="warning" if not item.required else "error",
                    message=item.detail or f"{item.kind.value} is unavailable",
                    blocking=bool(item.required),
                )
            )

        startup_summary = build_appliance_startup_summary(
            self.settings,
            config_source=self.settings.blink_appliance_config_source,
            selected_microphone_label=self._selected_microphone_label(),
            selected_camera_label=self._selected_camera_label(),
            selected_speaker_label=self._selected_speaker_label(),
            microphone_selection_note=getattr(device_health.get("microphone"), "selection_note", None),
            camera_selection_note=getattr(device_health.get("camera"), "selection_note", None),
            speaker_selection_note=getattr(device_health.get("speaker"), "selection_note", None),
            microphone_fallback_active=bool(getattr(device_health.get("microphone"), "fallback_active", False)),
            camera_fallback_active=bool(getattr(device_health.get("camera"), "fallback_active", False)),
            speaker_fallback_active=bool(getattr(device_health.get("speaker"), "fallback_active", False)),
        )

        action_plane_ready = True
        action_plane_issues: list[str] = []
        pending_action_count = 0
        waiting_workflow_count = 0
        review_required_count = 0
        browser_runtime_state = "unknown"
        action_root = Path(self.settings.brain_store_path).resolve().parent / "actions"
        action_paths = {
            "action_state": action_root,
            "workflow_state": action_root / "workflows",
            "action_exports": Path(self.settings.blink_action_plane_export_dir),
        }
        for label, directory in action_paths.items():
            if self._directory_writable(directory):
                continue
            action_plane_ready = False
            issue = f"{label}_not_writable:{directory}"
            action_plane_issues.append(issue)
            issues.append(
                ApplianceIssue(
                    category="action_plane",
                    severity="error",
                    message=f"Action Plane directory is not writable: {directory}",
                    blocking=True,
                )
            )

        agent_runtime = getattr(self.orchestrator, "agent_runtime", None)
        if agent_runtime is None:
            action_plane_ready = False
            action_plane_issues.append("agent_runtime_unavailable")
        else:
            try:
                action_status = agent_runtime.action_plane_status()
                pending_action_count = action_status.pending_approval_count
                waiting_workflow_count = action_status.waiting_workflow_count
                review_required_count = action_status.review_required_count
            except Exception as exc:
                action_plane_ready = False
                action_plane_issues.append(f"action_plane_status_unavailable:{exc}")
            try:
                browser_status = agent_runtime.action_plane_browser_status()
                browser_runtime_state = self._browser_runtime_state(browser_status)
                if not browser_status.supported or not browser_status.configured:
                    message = (
                        "Browser runtime is unavailable. Stage 6 browser actions stay degraded, "
                        "but non-browser connectors remain usable."
                    )
                    issues.append(
                        ApplianceIssue(
                            category="action_plane_browser",
                            severity="warning",
                            message=message,
                            blocking=False,
                        )
                    )
                    action_plane_issues.append(f"browser_runtime_degraded:{browser_status.backend_mode}")
            except Exception as exc:
                browser_runtime_state = "degraded"
                action_plane_issues.append(f"browser_runtime_status_unavailable:{exc}")

        return ApplianceStatus(
            appliance_mode=bool(self.settings.blink_appliance_mode),
            setup_complete=setup_complete,
            setup_issues=issues,
            action_plane_ready=action_plane_ready,
            action_plane_issues=action_plane_issues,
            browser_runtime_state=browser_runtime_state,
            pending_action_count=pending_action_count,
            waiting_workflow_count=waiting_workflow_count,
            review_required_count=review_required_count,
            next_operator_step=self._next_action_plane_step(
                action_plane_ready=action_plane_ready,
                pending_action_count=pending_action_count,
                waiting_workflow_count=waiting_workflow_count,
                review_required_count=review_required_count,
                browser_runtime_state=browser_runtime_state,
            ),
            auth_mode=self.operator_auth_mode or ("disabled_dev" if not self.settings.operator_auth_enabled else "configured_static_token"),
            config_source=self.settings.blink_appliance_config_source,
            device_preset=self.settings.blink_device_preset,
            configured_microphone_label=self._configured_microphone_label(),
            selected_microphone_label=self._selected_microphone_label(),
            configured_camera_label=self._configured_camera_label(),
            selected_camera_label=self._selected_camera_label(),
            configured_speaker_label=self._configured_speaker_label(),
            selected_speaker_label=self._selected_speaker_label(),
            speaker_selection_supported=self._speaker_selection_supported(),
            profile_path=str(store.path),
            profile_exists=store.exists(),
            model_profile=self.settings.blink_model_profile,
            backend_profile=self.settings.blink_backend_profile or self.backend_router.resolved_backend_profile(),
            voice_profile=self.settings.blink_voice_profile,
            runtime_mode=self.settings.blink_runtime_mode,
            ollama_reachable=ollama_snapshot.reachable,
            required_models=required_models,
            missing_models=missing_models,
            export_available=True,
            export_dir=self.settings.episode_export_dir,
            startup_summary=startup_summary,
            local_companion_readiness=local_companion_readiness,
        )

    def get_appliance_devices(self) -> ApplianceDeviceCatalog:
        listed = list_avfoundation_devices(ffmpeg_path=self.device_registry.microphone_input.ffmpeg_path)
        selected_microphone = self._selected_microphone_label()
        selected_camera = self._selected_camera_label()
        return ApplianceDeviceCatalog(
            device_preset=self.settings.blink_device_preset,
            microphones=[
                ApplianceDeviceOption(
                    device_id=f"audio:{item.index}",
                    label=item.label,
                    kind=DesktopDeviceKind.MICROPHONE,
                    selected=item.label == selected_microphone,
                )
                for item in listed.get("audio", [])
            ],
            cameras=[
                ApplianceDeviceOption(
                    device_id=f"video:{item.index}",
                    label=item.label,
                    kind=DesktopDeviceKind.CAMERA,
                    selected=item.label == selected_camera,
                )
                for item in listed.get("video", [])
            ],
            selected_microphone_label=selected_microphone,
            selected_camera_label=selected_camera,
            selected_speaker_label=self._selected_speaker_label(),
            speaker_selection_supported=self._speaker_selection_supported(),
            speaker_note="macos_say follows the current macOS system default output device.",
        )

    def save_appliance_profile(self, request: ApplianceProfileRequest) -> ApplianceStatus:
        store = self._profile_store()
        profile = default_appliance_profile(self.settings).model_copy(
            update={
                "setup_complete": request.setup_complete,
                "device_preset": request.device_preset,
                "microphone_device": request.microphone_device,
                "camera_device": request.camera_device,
                "speaker_device": request.speaker_device,
                "saved_at": utc_now().isoformat(),
            }
        )
        store.save(profile)
        apply_runtime_profile_to_live_settings(self.settings, profile)
        self.device_registry.speaker_output.requested_output_device = self.settings.blink_speaker_device
        return self.get_appliance_status()

    def get_snapshot(
        self,
        *,
        session_id: str | None = None,
        voice_mode: VoiceRuntimeMode | None = None,
        trace_limit: int = 25,
    ) -> OperatorConsoleSnapshot:
        explicit_session_requested = session_id is not None
        sessions = self.orchestrator.list_sessions()
        world_state = self.orchestrator.get_world_state()
        participant_router = self.orchestrator.get_participant_router()
        active_session_id = (
            session_id
            or participant_router.active_session_id
            or world_state.last_session_id
            or (sessions.items[0].session_id if sessions.items else None)
        )
        selected_session = self.orchestrator.get_session(active_session_id) if active_session_id else None
        resolved_voice_mode = voice_mode or self.default_live_voice_mode()
        telemetry = self.edge_gateway.get_telemetry()
        heartbeat = self.edge_gateway.get_heartbeat()
        telemetry_log = self.edge_gateway.get_telemetry_log()
        command_history = self.edge_gateway.get_command_history()
        latest_perception = self.perception_service.get_latest_snapshot(active_session_id) if active_session_id else None
        if latest_perception is None and not explicit_session_requested:
            latest_perception = self.perception_service.get_latest_snapshot()
        selected_incident = (
            self.orchestrator.get_incident(selected_session.active_incident_ticket_id)
            if selected_session and selected_session.active_incident_ticket_id
            else None
        )
        appliance_status = self.get_appliance_status()
        local_companion_readiness = appliance_status.local_companion_readiness
        evidence = collect_shift_evidence(self.orchestrator)
        shift_metrics = calculate_shift_metrics(
            sessions=evidence.sessions,
            traces=evidence.traces,
            perception_snapshots=evidence.perception_snapshots,
            shift_transitions=evidence.shift_transitions,
            incidents=evidence.incidents,
            shift_snapshot=evidence.shift_snapshot,
            participant_router=evidence.participant_router,
        )
        if selected_incident is None:
            open_incidents = self.orchestrator.list_incidents(scope=IncidentListScope.OPEN, limit=25)
            selected_incident = open_incidents.items[0] if open_incidents.items else None
        else:
            open_incidents = self.orchestrator.list_incidents(scope=IncidentListScope.OPEN, limit=25)
        closed_incidents = self.orchestrator.list_incidents(scope=IncidentListScope.CLOSED, limit=25)
        profile_summary = summarize_desktop_profile(self.settings)
        backend_status = self.backend_router.runtime_statuses()
        backend_status_by_kind = {
            item.kind.value: item
            for item in backend_status
        }
        device_health = list(self._device_health_map(default_voice_mode=resolved_voice_mode).values())
        latest_trace = None
        world_model = self.orchestrator.get_world_model()
        scene_observer_events = (
            self.shift_runner.scene_observer_events()
            if self.shift_runner is not None and hasattr(self.shift_runner, "scene_observer_events")
            else SceneObserverEventListResponse()
        )
        latest_watcher_event = (
            next(
                (
                    item
                    for item in reversed(scene_observer_events.items)
                    if getattr(item, "session_id", None) in {None, active_session_id}
                ),
                None,
            )
            if explicit_session_requested and active_session_id is not None
            else (scene_observer_events.items[-1] if scene_observer_events.items else None)
        )
        if active_session_id:
            trace_items = self.orchestrator.list_traces(session_id=active_session_id, limit=1).items
            latest_trace = trace_items[0] if trace_items else None
        perception_freshness = self._build_perception_freshness(
            latest_perception=latest_perception,
            world_state=world_state,
            latest_watcher_event=latest_watcher_event,
            allow_world_fallback=not explicit_session_requested,
        )
        memory_status = self._build_memory_status(selected_session=selected_session)
        fallback_state = self._build_fallback_state(
            backend_status=backend_status,
            latest_trace=latest_trace,
            heartbeat=heartbeat,
        )
        startup_summary = build_appliance_startup_summary(
            self.settings,
            config_source=appliance_status.config_source,
            selected_microphone_label=appliance_status.selected_microphone_label,
            selected_camera_label=appliance_status.selected_camera_label,
            selected_speaker_label=appliance_status.selected_speaker_label,
            microphone_selection_note=next((item.selection_note for item in device_health if item.kind.value == "microphone"), None),
            camera_selection_note=next((item.selection_note for item in device_health if item.kind.value == "camera"), None),
            speaker_selection_note=next((item.selection_note for item in device_health if item.kind.value == "speaker"), None),
            microphone_fallback_active=any(item.kind.value == "microphone" and item.fallback_active for item in device_health),
            camera_fallback_active=any(item.kind.value == "camera" and item.fallback_active for item in device_health),
            speaker_fallback_active=any(item.kind.value == "speaker" and item.fallback_active for item in device_health),
            provider_status=profile_summary.provider_status,
            provider_detail=profile_summary.provider_detail,
            fallback_state=fallback_state,
        )

        body_state = telemetry.body_state
        if body_state is None:
            body_status = "unavailable"
        else:
            health = "ready" if body_state.transport_healthy else "degraded"
            body_status = f"{body_state.driver_mode.value}:{health}"
            if body_state.driver_mode.value == "serial":
                body_status = (
                    f"{body_status}:{body_state.transport_mode or 'unknown'}:"
                    f"{'armed' if body_state.live_motion_armed else 'disarmed'}"
                )
            if body_state.transport_error:
                body_status = f"{body_status} ({body_state.transport_error})"

        if latest_perception is None:
            perception_status = "idle"
        elif latest_perception.limited_awareness:
            perception_status = f"{latest_perception.status.value}:limited_awareness"
        else:
            perception_status = latest_perception.status.value

        agent_runtime = getattr(self.orchestrator, "agent_runtime", None)
        latest_reasoning = latest_trace.reasoning if latest_trace is not None else None
        latest_live_turn_diagnostics = (
            latest_reasoning.live_turn_diagnostics if latest_reasoning is not None else None
        ) or self._load_latest_live_turn_diagnostics()
        latest_decisions = latest_reasoning.executive_decisions if latest_reasoning is not None else []
        runs = agent_runtime.list_runs(session_id=active_session_id, limit=10) if agent_runtime is not None else RunListResponse()
        latest_run = runs.items[0] if runs.items else None
        checkpoints = (
            agent_runtime.list_checkpoints(run_id=latest_run.run_id, limit=25)
            if agent_runtime is not None and latest_run is not None
            else CheckpointListResponse()
        )
        voice_loop_status = (
            self.shift_runner.voice_loop_status()
            if self.shift_runner is not None and hasattr(self.shift_runner, "voice_loop_status")
            else CompanionVoiceLoopStatus()
        )
        latest_scene_cache = (
            self.shift_runner.latest_scene_cache()
            if self.shift_runner is not None and hasattr(self.shift_runner, "latest_scene_cache")
            else None
        )
        scene_cache_age_seconds = None
        if latest_scene_cache is not None:
            scene_cache_age_seconds = round(max(0.0, (utc_now() - latest_scene_cache.captured_at).total_seconds()), 2)
        greet_suppression_reason = next(
            (
                item.suppressed_reason
                for item in reversed(latest_decisions)
                if item.policy_name == "greeting_policy" and item.suppressed_reason
            ),
            None,
        )
        scene_reply_guardrail = None
        if latest_reasoning is not None:
            if latest_reasoning.stale_scene_suppressed:
                scene_reply_guardrail = "stale_scene_suppressed"
            elif latest_reasoning.uncertainty_admitted:
                scene_reply_guardrail = "uncertainty_admission"
        if scene_reply_guardrail is None:
            scene_reply_guardrail = next(
                (
                    item.policy_outcome
                    for item in reversed(latest_decisions)
                    if item.policy_outcome in {"uncertainty_admission", "stale_scene_suppressed"}
                ),
                None,
            )
        attention_target_source = None
        if world_model.attention_target is not None:
            attention_target_source = (
                world_model.attention_target.rationale
                or f"{world_model.attention_target.source_tier.value}:{world_model.attention_target.claim_kind.value}"
            )
        presence_runtime_status = (
            self.shift_runner.presence_runtime_status()
            if self.shift_runner is not None and hasattr(self.shift_runner, "presence_runtime_status")
            else CompanionPresenceStatus()
        )
        initiative_engine_status = (
            self.shift_runner.initiative_engine_status()
            if self.shift_runner is not None and hasattr(self.shift_runner, "initiative_engine_status")
            else InitiativeStatus()
        )
        character_projection_profile = resolve_character_projection_profile(self.settings)
        character_semantic_intent = build_character_semantic_intent(
            presence_status=presence_runtime_status,
            voice_status=voice_loop_status,
            initiative_status=initiative_engine_status,
            relationship_status=memory_status.relationship_continuity,
            fallback_state=fallback_state,
            body_state=body_state,
        )
        character_presence_shell = build_character_presence_shell(
            presence_status=presence_runtime_status,
            voice_status=voice_loop_status,
            initiative_status=initiative_engine_status,
            relationship_status=memory_status.relationship_continuity,
            fallback_state=fallback_state,
            body_state=body_state,
        )

        return OperatorConsoleSnapshot(
            runtime=ConsoleRuntimeStatus(
                project_name=self.settings.project_name,
                dialogue_backend=self.settings.brain_dialogue_backend,
                voice_backend=self.settings.brain_voice_backend,
                perception_provider_mode=self.perception_service.default_mode(),
                runtime_profile=self.settings.brain_runtime_profile,
                deployment_target=self.settings.brain_deployment_target,
                runtime_mode=self.settings.blink_runtime_mode,
                world_mode=world_state.mode,
                model_profile=self.settings.blink_model_profile,
                resolved_model_profile=profile_summary.model_profile,
                backend_profile=self.settings.blink_backend_profile or profile_summary.backend_profile,
                resolved_backend_profile=self.backend_router.resolved_backend_profile(),
                voice_profile=self.settings.blink_voice_profile,
                resolved_voice_profile=profile_summary.voice_profile,
                embodiment_profile=profile_summary.embodiment_profile,
                profile_summary=profile_summary.profile_label,
                provider_status=profile_summary.provider_status,
                provider_detail=profile_summary.provider_detail,
                perception_status=perception_status,
                body_status=body_status,
                camera_source=self.settings.blink_camera_source,
                configured_speaker_label=appliance_status.configured_speaker_label,
                selected_speaker_label=appliance_status.selected_speaker_label,
                speaker_selection_supported=appliance_status.speaker_selection_supported,
                device_preset=appliance_status.device_preset,
                configured_microphone_label=appliance_status.configured_microphone_label,
                selected_microphone_label=self.device_registry.selected_microphone_label(),
                configured_camera_label=appliance_status.configured_camera_label,
                selected_camera_label=self.device_registry.selected_camera_label(),
                body_driver_mode=self.settings.resolved_body_driver,
                head_profile_path=self.settings.blink_head_profile,
                operator_auth_enabled=self.settings.operator_auth_enabled,
                auth_mode=appliance_status.auth_mode,
                operator_auth_token_source=self.operator_auth_token_source,
                operator_auth_runtime_file=self.operator_auth_runtime_file,
                setup_complete=appliance_status.setup_complete,
                setup_issues=appliance_status.setup_issues,
                config_source=appliance_status.config_source,
                console_url=self.console_url,
                console_launch_state=self.console_launch_state,
                terminal_frontend_state=self.terminal_frontend_state,
                terminal_frontend_detail=self.terminal_frontend_detail,
                edge_transport_mode=self.edge_gateway.transport_mode(),
                edge_transport_state=self.edge_gateway.transport_state(),
                edge_transport_error=self.edge_gateway.last_transport_error(),
                default_live_voice_mode=resolved_voice_mode,
                audio_mode=(
                    self.shift_runner.audio_mode()
                    if self.shift_runner is not None and hasattr(self.shift_runner, "audio_mode")
                    else self.settings.blink_audio_mode
                ),
                context_mode=CompanionContextMode.VENUE_DEMO
                if selected_session is not None and selected_session.scenario_name
                else self.settings.blink_context_mode,
                text_backend=backend_status_by_kind.get("text_reasoning").backend_id if backend_status_by_kind.get("text_reasoning") else None,
                vision_backend=backend_status_by_kind.get("vision_analysis").backend_id if backend_status_by_kind.get("vision_analysis") else None,
                embedding_backend=backend_status_by_kind.get("embeddings").backend_id if backend_status_by_kind.get("embeddings") else None,
                stt_backend=backend_status_by_kind.get("speech_to_text").backend_id if backend_status_by_kind.get("speech_to_text") else None,
                tts_backend=backend_status_by_kind.get("text_to_speech").backend_id if backend_status_by_kind.get("text_to_speech") else None,
                backend_status=backend_status,
                device_health=device_health,
                perception_freshness=perception_freshness,
                social_runtime_mode=world_model.social_runtime_mode,
                last_semantic_refresh_reason=world_model.last_semantic_refresh_reason,
                active_speaker_hypothesis=world_model.current_speaker_participant_id,
                active_speaker_source=world_model.speaker_hypothesis_source,
                attention_target_source=attention_target_source,
                greet_suppression_reason=greet_suppression_reason,
                scene_reply_guardrail=scene_reply_guardrail,
                watcher_buffer_count=len(scene_observer_events.items) if hasattr(scene_observer_events, "items") else 0,
                memory_status=memory_status,
                fallback_state=fallback_state,
                always_on_enabled=bool(self.settings.blink_always_on_enabled),
                supervisor=(
                    self.shift_runner.supervisor_status()
                    if self.shift_runner is not None and hasattr(self.shift_runner, "supervisor_status")
                    else CompanionSupervisorStatus()
                ),
                presence_runtime=presence_runtime_status,
                character_projection_profile=character_projection_profile,
                character_semantic_intent=character_semantic_intent,
                character_presence_shell=character_presence_shell,
                voice_loop=voice_loop_status,
                audio_loop=voice_loop_status,
                scene_observer=(
                    self.shift_runner.scene_observer_status()
                    if self.shift_runner is not None and hasattr(self.shift_runner, "scene_observer_status")
                    else SceneObserverStatus()
                ),
                initiative_engine=initiative_engine_status,
                trigger_engine=(
                    self.shift_runner.trigger_engine_status()
                    if self.shift_runner is not None and hasattr(self.shift_runner, "trigger_engine_status")
                    else TriggerEngineStatus()
                ),
                partial_transcript_preview=voice_loop_status.partial_transcript_preview,
                latest_live_turn_diagnostics=latest_live_turn_diagnostics,
                scene_cache_age_seconds=scene_cache_age_seconds,
                open_reminder_count=memory_status.open_reminder_count,
                model_residency=self.backend_router.model_residency(),
                agent_runtime_enabled=agent_runtime is not None,
                registered_skills=agent_runtime.registered_skills() if agent_runtime is not None else [],
                registered_subagents=agent_runtime.registered_subagents() if agent_runtime is not None else [],
                registered_hooks=agent_runtime.registered_hooks() if agent_runtime is not None else [],
                registered_tools=agent_runtime.registered_tools() if agent_runtime is not None else [],
                specialist_roles=agent_runtime.specialist_roles() if agent_runtime is not None else [],
                run_id=latest_reasoning.run_id if latest_reasoning is not None else None,
                run_phase=latest_reasoning.run_phase if latest_reasoning is not None else None,
                run_status=latest_reasoning.run_status if latest_reasoning is not None else None,
                active_playbook=latest_reasoning.active_playbook if latest_reasoning is not None else None,
                active_playbook_variant=latest_reasoning.active_playbook_variant if latest_reasoning is not None else None,
                active_subagent=latest_reasoning.active_subagent if latest_reasoning is not None else None,
                tool_chain=latest_reasoning.tool_chain if latest_reasoning is not None else [],
                checkpoint_count=latest_reasoning.checkpoint_count if latest_reasoning is not None else 0,
                last_checkpoint_id=latest_reasoning.last_checkpoint_id if latest_reasoning is not None else None,
                failure_state=latest_reasoning.failure_state if latest_reasoning is not None else None,
                fallback_reason=latest_reasoning.fallback_reason if latest_reasoning is not None else None,
                fallback_classification=latest_reasoning.fallback_classification if latest_reasoning is not None else None,
                unavailable_capabilities=latest_reasoning.unavailable_capabilities if latest_reasoning is not None else [],
                intentionally_skipped_capabilities=(
                    latest_reasoning.intentionally_skipped_capabilities if latest_reasoning is not None else []
                ),
                recovery_status=latest_reasoning.recovery_status if latest_reasoning is not None else None,
                instruction_layers=latest_reasoning.instruction_layers if latest_reasoning is not None else [],
                last_active_skill=latest_reasoning.active_skill if latest_reasoning is not None else None,
                last_tool_calls=latest_reasoning.typed_tool_calls if latest_reasoning is not None else [],
                last_validation_outcomes=latest_reasoning.validation_outcomes if latest_reasoning is not None else [],
                last_hook_records=latest_reasoning.hook_records if latest_reasoning is not None else [],
                last_role_decisions=latest_reasoning.role_decisions if latest_reasoning is not None else [],
                grounded_scene_references=latest_reasoning.grounded_scene_references if latest_reasoning is not None else [],
                latest_scene_cache=latest_scene_cache,
                recent_memory_promotions=(
                    self.shift_runner.recent_memory_promotions()
                    if self.shift_runner is not None and hasattr(self.shift_runner, "recent_memory_promotions")
                    else []
                ),
                action_plane=agent_runtime.action_plane_status() if agent_runtime is not None else {},
                export_available=appliance_status.export_available,
                episode_export_dir=appliance_status.export_dir,
                startup_summary=startup_summary,
                local_companion_readiness=local_companion_readiness,
            ),
            active_session_id=active_session_id,
            sessions=sessions.items,
            selected_session=selected_session,
            world_state=world_state,
            shift_supervisor=self.orchestrator.get_shift_supervisor(),
            shift_metrics=shift_metrics,
            participant_router=participant_router,
            venue_operations=self.orchestrator.get_venue_operations(),
            world_model=world_model,
            telemetry=telemetry,
            heartbeat=heartbeat,
            telemetry_log=telemetry_log,
            command_history=command_history,
            trace_summaries=self.orchestrator.list_logs(session_id=active_session_id, limit=trace_limit)
            if active_session_id
            else LogListResponse(),
            executive_decisions=self.orchestrator.list_executive_decisions(session_id=active_session_id, limit=trace_limit)
            if active_session_id
            else self.orchestrator.list_executive_decisions(limit=trace_limit),
            recent_demo_runs=self.demo_coordinator.list_runs(),
            voice_state=self.voice_manager.get_state(resolved_voice_mode, active_session_id),
            latest_perception=latest_perception,
            perception_history=self.perception_service.list_history(session_id=active_session_id, limit=trace_limit),
            scene_observer_events=scene_observer_events,
            world_model_transitions=self.orchestrator.list_world_model_transitions(session_id=active_session_id, limit=trace_limit),
            shift_transitions=self.orchestrator.list_shift_transitions(session_id=active_session_id, limit=trace_limit),
            engagement_timeline=self.orchestrator.list_engagement_timeline(session_id=active_session_id, limit=trace_limit),
            selected_incident=selected_incident,
            selected_incident_timeline=(
                self.orchestrator.list_incident_timeline(ticket_id=selected_incident.ticket_id, limit=50)
                if selected_incident is not None
                else IncidentTimelineResponse()
            ),
            open_incidents=open_incidents,
            closed_incidents=closed_incidents,
            recent_shift_reports=self.shift_report_store.list(limit=10),
            runs=runs,
            checkpoints=checkpoints,
        )

    def get_character_presence_surface(self, *, session_id: str | None = None) -> CharacterPresenceSurfaceSnapshot:
        sessions = self.orchestrator.list_sessions()
        world_state = self.orchestrator.get_world_state()
        participant_router = self.orchestrator.get_participant_router()
        active_session_id = (
            session_id
            or participant_router.active_session_id
            or world_state.last_session_id
            or (sessions.items[0].session_id if sessions.items else None)
        )
        selected_session = self.orchestrator.get_session(active_session_id) if active_session_id else None
        telemetry = self.edge_gateway.get_telemetry()
        heartbeat = self.edge_gateway.get_heartbeat()
        latest_trace = None
        if active_session_id:
            trace_items = self.orchestrator.list_traces(session_id=active_session_id, limit=1).items
            latest_trace = trace_items[0] if trace_items else None
        fallback_state = self._build_fallback_state(
            backend_status=self.backend_router.runtime_statuses(),
            latest_trace=latest_trace,
            heartbeat=heartbeat,
        )
        memory_status = self._build_memory_status(selected_session=selected_session)
        presence_runtime_status = (
            self.shift_runner.presence_runtime_status()
            if self.shift_runner is not None and hasattr(self.shift_runner, "presence_runtime_status")
            else CompanionPresenceStatus()
        )
        voice_loop_status = (
            self.shift_runner.voice_loop_status()
            if self.shift_runner is not None and hasattr(self.shift_runner, "voice_loop_status")
            else CompanionVoiceLoopStatus()
        )
        initiative_engine_status = (
            self.shift_runner.initiative_engine_status()
            if self.shift_runner is not None and hasattr(self.shift_runner, "initiative_engine_status")
            else InitiativeStatus()
        )
        character_projection_profile = resolve_character_projection_profile(self.settings)
        character_semantic_intent = build_character_semantic_intent(
            presence_status=presence_runtime_status,
            voice_status=voice_loop_status,
            initiative_status=initiative_engine_status,
            relationship_status=memory_status.relationship_continuity,
            fallback_state=fallback_state,
            body_state=telemetry.body_state,
        )
        character_presence_shell = build_character_presence_shell(
            presence_status=presence_runtime_status,
            voice_status=voice_loop_status,
            initiative_status=initiative_engine_status,
            relationship_status=memory_status.relationship_continuity,
            fallback_state=fallback_state,
            body_state=telemetry.body_state,
        )
        return CharacterPresenceSurfaceSnapshot(
            active_session_id=active_session_id,
            character_projection_profile=character_projection_profile,
            character_semantic_intent=character_semantic_intent,
            character_presence_shell=character_presence_shell,
            presence_runtime=presence_runtime_status,
            voice_loop=voice_loop_status,
            initiative_engine=initiative_engine_status,
            relationship_continuity=memory_status.relationship_continuity,
            fallback_state=fallback_state,
            body_state=telemetry.body_state,
        )

    def list_runs(self, *, session_id: str | None = None, limit: int = 50) -> RunListResponse:
        agent_runtime = getattr(self.orchestrator, "agent_runtime", None)
        if agent_runtime is None:
            return RunListResponse()
        return agent_runtime.list_runs(session_id=session_id, limit=limit)

    def get_run(self, run_id: str) -> RunRecord | None:
        agent_runtime = getattr(self.orchestrator, "agent_runtime", None)
        if agent_runtime is None:
            return None
        return agent_runtime.get_run(run_id)

    def list_run_checkpoints(self, run_id: str, *, limit: int = 100) -> CheckpointListResponse:
        agent_runtime = getattr(self.orchestrator, "agent_runtime", None)
        if agent_runtime is None:
            return CheckpointListResponse()
        return agent_runtime.list_checkpoints(run_id=run_id, limit=limit)

    def replay_run(self, run_id: str) -> RunRecord:
        agent_runtime = getattr(self.orchestrator, "agent_runtime", None)
        if agent_runtime is None:
            raise KeyError(run_id)
        run = agent_runtime.get_run(run_id)
        if run is None:
            raise KeyError(run_id)
        event = RobotEvent.model_validate(
            {
                **run.source_event,
                "payload": {
                    **dict(run.source_event.get("payload", {})),
                    "agent_os_replayed_from_run_id": run_id,
                },
            }
        )
        response = self.orchestrator.handle_event(event)
        if not response.trace_id:
            raise RuntimeError("replay_missing_trace_id")
        replayed = agent_runtime.get_run_for_trace(response.trace_id)
        if replayed is None:
            raise RuntimeError("replay_run_not_recorded")
        return replayed

    def resume_checkpoint(self, checkpoint_id: str) -> RunRecord:
        agent_runtime = getattr(self.orchestrator, "agent_runtime", None)
        if agent_runtime is None:
            raise KeyError(checkpoint_id)
        checkpoint = agent_runtime.get_checkpoint(checkpoint_id)
        if checkpoint is None:
            raise KeyError(checkpoint_id)
        run = agent_runtime.get_run(checkpoint.run_id)
        if run is None:
            raise KeyError(checkpoint.run_id)
        event = RobotEvent.model_validate(
            {
                **run.source_event,
                "payload": {
                    **dict(run.source_event.get("payload", {})),
                    "agent_os_replayed_from_run_id": run.run_id,
                    "agent_os_resumed_from_checkpoint_id": checkpoint_id,
                },
            }
        )
        response = self.orchestrator.handle_event(event)
        if not response.trace_id:
            raise RuntimeError("resume_missing_trace_id")
        resumed = agent_runtime.get_run_for_trace(response.trace_id)
        if resumed is None:
            raise RuntimeError("resume_run_not_recorded")
        agent_runtime.run_tracker.mark_checkpoint_resumed(checkpoint_id, resumed.run_id)
        return resumed

    def pause_run(self, run_id: str, *, reason: str = "operator_pause") -> RunRecord:
        agent_runtime = getattr(self.orchestrator, "agent_runtime", None)
        if agent_runtime is None:
            raise KeyError(run_id)
        paused = agent_runtime.pause_run(run_id, reason=reason)
        if paused is None:
            raise KeyError(run_id)
        return paused

    def resume_run(self, run_id: str, *, note: str = "operator_resume") -> RunRecord:
        agent_runtime = getattr(self.orchestrator, "agent_runtime", None)
        if agent_runtime is None:
            raise KeyError(run_id)
        resumed = agent_runtime.resume_run(run_id, note=note)
        if resumed is None:
            raise KeyError(run_id)
        return resumed

    def abort_run(self, run_id: str, *, reason: str = "operator_abort") -> RunRecord:
        agent_runtime = getattr(self.orchestrator, "agent_runtime", None)
        if agent_runtime is None:
            raise KeyError(run_id)
        aborted = agent_runtime.abort_run(run_id, reason=reason)
        if aborted is None:
            raise KeyError(run_id)
        return aborted

    def export_run(self, run_id: str) -> RunExportResponse:
        agent_runtime = getattr(self.orchestrator, "agent_runtime", None)
        if agent_runtime is None:
            raise KeyError(run_id)
        run = agent_runtime.get_run(run_id)
        if run is None:
            raise KeyError(run_id)
        checkpoints = agent_runtime.list_checkpoints(run_id=run_id, limit=500).items[::-1]
        trace = self.orchestrator.get_trace(run.trace_id) if run.trace_id else None
        export_dir = Path(self.settings.episode_export_dir).resolve().parent / "agent_os_exports"
        export_dir.mkdir(parents=True, exist_ok=True)
        artifact_path = export_dir / f"run-{run_id}.json"
        artifact = RunExportArtifact(
            run=run,
            checkpoints=checkpoints,
            typed_tool_calls=list(trace.reasoning.typed_tool_calls) if trace is not None else [],
            hook_records=list(trace.reasoning.hook_records) if trace is not None else [],
            validation_outcomes=list(trace.reasoning.validation_outcomes) if trace is not None else [],
            role_decisions=list(trace.reasoning.role_decisions) if trace is not None else [],
            recovery_metadata={
                "paused_from_checkpoint_id": run.paused_from_checkpoint_id,
                "replayed_from_run_id": run.replayed_from_run_id,
                "resumed_from_checkpoint_id": run.resumed_from_checkpoint_id,
                "recovery_notes": list(run.recovery_notes),
                "trace_id": run.trace_id,
            },
            artifact_path=str(artifact_path),
        )
        write_json_atomic(artifact_path, artifact)
        return RunExportResponse(artifact=artifact)

    def _build_perception_freshness(
        self,
        *,
        latest_perception: PerceptionSnapshotRecord | None,
        world_state,
        latest_watcher_event=None,
        allow_world_fallback: bool = True,
    ) -> PerceptionFreshnessStatus:
        if latest_perception is None and (not allow_world_fallback or world_state.last_perception_at is None):
            freshness = PerceptionFreshnessStatus()
            if latest_watcher_event is not None:
                freshness.watcher = self._freshness_window(
                    observed_at=latest_watcher_event.observed_at,
                    max_age_seconds=DEFAULT_FRESHNESS_POLICY.watcher_hint_window.ttl_seconds,
                    limited_awareness=latest_watcher_event.limited_awareness,
                    source_kind=latest_watcher_event.source_kind,
                    summary=latest_watcher_event.refresh_reason,
                    tier=PerceptionTier.WATCHER,
                    trigger_reason=latest_watcher_event.refresh_reason,
                )
            return freshness

        observed_at = latest_perception.created_at if latest_perception is not None else world_state.last_perception_at
        captured_at = latest_perception.source_frame.captured_at if latest_perception is not None else None
        reference_at = captured_at or observed_at or world_state.last_perception_at
        semantic = self._freshness_window(
            observed_at=reference_at,
            max_age_seconds=self._PERCEPTION_MAX_AGE_SECONDS,
            limited_awareness=(
                latest_perception.limited_awareness
                if latest_perception is not None
                else bool(world_state.perception_limited_awareness)
            ),
            source_kind=latest_perception.source_frame.source_kind if latest_perception is not None else None,
            summary=(
                latest_perception.scene_summary
                if latest_perception is not None
                else world_state.latest_scene_summary
            ),
            tier=latest_perception.tier if latest_perception is not None else None,
            trigger_reason=latest_perception.trigger_reason if latest_perception is not None else None,
        )
        watcher = (
            self._freshness_window(
                observed_at=latest_watcher_event.observed_at,
                max_age_seconds=DEFAULT_FRESHNESS_POLICY.watcher_hint_window.ttl_seconds,
                limited_awareness=latest_watcher_event.limited_awareness,
                source_kind=latest_watcher_event.source_kind,
                summary=latest_watcher_event.refresh_reason,
                tier=PerceptionTier.WATCHER,
                trigger_reason=latest_watcher_event.refresh_reason,
            )
            if latest_watcher_event is not None
            else FreshnessWindowStatus()
        )

        return PerceptionFreshnessStatus(
            status=semantic.status,
            freshness=semantic.freshness,
            observed_at=observed_at or world_state.last_perception_at,
            captured_at=captured_at,
            age_seconds=semantic.age_seconds,
            max_age_seconds=self._PERCEPTION_MAX_AGE_SECONDS,
            expires_in_seconds=semantic.expires_in_seconds,
            limited_awareness=semantic.limited_awareness,
            source_kind=semantic.source_kind,
            summary=semantic.summary,
            tier=semantic.tier,
            trigger_reason=semantic.trigger_reason,
            uncertainty_markers=latest_perception.uncertainty_markers if latest_perception is not None else [],
            device_awareness_constraints=latest_perception.device_awareness_constraints if latest_perception is not None else [],
            watcher=watcher,
            semantic=semantic,
        )

    def _freshness_window(
        self,
        *,
        observed_at,
        max_age_seconds: float,
        limited_awareness: bool,
        source_kind: str | None,
        summary: str | None,
        tier,
        trigger_reason: str | None,
    ) -> FreshnessWindowStatus:
        if observed_at is None:
            return FreshnessWindowStatus()
        age_seconds = round(max(0.0, (utc_now() - observed_at).total_seconds()), 2)
        expires_in_seconds = round(max(0.0, max_age_seconds - age_seconds), 2)
        if age_seconds <= min(self._PERCEPTION_FRESH_MAX_AGE_SECONDS, max_age_seconds):
            status = "fresh"
            freshness = FactFreshness.FRESH
        elif age_seconds <= max_age_seconds:
            status = "aging"
            freshness = FactFreshness.AGING
        else:
            status = "stale"
            freshness = FactFreshness.STALE
        return FreshnessWindowStatus(
            status=status,
            freshness=freshness,
            observed_at=observed_at,
            age_seconds=age_seconds,
            max_age_seconds=max_age_seconds,
            expires_in_seconds=expires_in_seconds,
            limited_awareness=limited_awareness,
            source_kind=source_kind,
            summary=summary,
            tier=tier,
            trigger_reason=trigger_reason,
        )

    def _build_memory_status(self, *, selected_session) -> MemoryStatus:
        if selected_session is None:
            return MemoryStatus()

        review_debt_summary = self.orchestrator.memory_review_debt_summary()
        episodic_memory = self.orchestrator.list_episodic_memory(session_id=selected_session.session_id, limit=25).items
        semantic_memory = self.orchestrator.list_semantic_memory(session_id=selected_session.session_id, limit=25).items
        reminders = self.orchestrator.list_reminders(session_id=selected_session.session_id, status=ReminderStatus.OPEN, limit=50).items
        notes = self.orchestrator.list_companion_notes(session_id=selected_session.session_id, limit=50).items
        digests = self.orchestrator.list_session_digests(session_id=selected_session.session_id, limit=20).items
        continuity_reminders = (
            self.orchestrator.list_reminders(user_id=selected_session.user_id, status=ReminderStatus.OPEN, limit=50).items
            if selected_session.user_id
            else reminders
        )
        continuity_digests = (
            self.orchestrator.list_session_digests(user_id=selected_session.user_id, limit=20).items
            if selected_session.user_id
            else digests
        )
        profile_memory = (
            self.orchestrator.memory.get_user_memory(selected_session.user_id)
            if selected_session.user_id
            else None
        )
        relationship_memory = (
            self.orchestrator.memory.get_relationship_memory(selected_session.user_id)
            if selected_session.user_id
            else None
        )
        last_memory_at = max(
            [
                selected_session.updated_at,
                *(item.updated_at for item in episodic_memory),
                *(item.updated_at for item in semantic_memory),
                *(item.updated_at for item in reminders),
                *(item.updated_at for item in notes),
                *(item.updated_at for item in digests),
                *([profile_memory.updated_at] if profile_memory is not None else []),
                *([relationship_memory.updated_at] if relationship_memory is not None else []),
            ],
            default=selected_session.updated_at,
        )
        status = "empty"
        if selected_session.transcript or selected_session.session_memory or selected_session.operator_notes:
            status = "session_only"
        if episodic_memory or semantic_memory or reminders or notes or digests or profile_memory is not None:
            status = "grounded"
        latest_digest = continuity_digests[0] if continuity_digests else None
        relationship_profile = (
            profile_memory.relationship_profile
            if profile_memory is not None
            else (relationship_memory.preferred_style if relationship_memory is not None else None)
        )
        open_follow_ups: list[str] = []
        for item in list(latest_digest.open_follow_ups) if latest_digest is not None else []:
            if item not in open_follow_ups:
                open_follow_ups.append(item)
        for reminder in continuity_reminders:
            if reminder.reminder_text not in open_follow_ups:
                open_follow_ups.append(reminder.reminder_text)
        open_practical_threads: list[str] = []
        open_emotional_threads: list[str] = []
        promise_count = 0
        recurring_topics: list[str] = []
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
        known_user = bool(
            (profile_memory or relationship_memory)
            and (
                (profile_memory.display_name if profile_memory is not None else None)
                or (profile_memory.facts if profile_memory is not None else None)
                or (profile_memory.preferences if profile_memory is not None else None)
                or (profile_memory.interests if profile_memory is not None else None)
                or recurring_topics
                or open_practical_threads
                or open_emotional_threads
                or (relationship_profile and (
                    relationship_profile.greeting_preference
                    or relationship_profile.planning_style
                    or relationship_profile.tone_preferences
                    or relationship_profile.interaction_boundaries
                    or relationship_profile.continuity_preferences
                ))
            )
        )
        returning_user = bool(profile_memory and profile_memory.visit_count > 1)

        return MemoryStatus(
            status=status,
            session_id=selected_session.session_id,
            user_id=selected_session.user_id,
            transcript_turn_count=len(selected_session.transcript),
            conversation_summary=selected_session.conversation_summary,
            session_memory_keys=sorted(selected_session.session_memory),
            operator_note_count=len(selected_session.operator_notes),
            episodic_memory_count=len(episodic_memory),
            semantic_memory_count=len(semantic_memory),
            profile_memory_available=profile_memory is not None,
            profile_fact_count=len(profile_memory.facts) if profile_memory is not None else 0,
            profile_preference_count=len(profile_memory.preferences) if profile_memory is not None else 0,
            profile_interest_count=len(profile_memory.interests) if profile_memory is not None else 0,
            open_reminder_count=len(reminders),
            note_count=len(notes),
            session_digest_count=len(digests),
            relationship_continuity=RelationshipContinuityStatus(
                known_user=known_user,
                returning_user=returning_user,
                display_name=profile_memory.display_name if profile_memory is not None else None,
                familiarity=familiarity,
                recurring_topics=recurring_topics,
                greeting_preference=(
                    relationship_profile.greeting_preference if relationship_profile is not None else None
                ),
                planning_style=relationship_profile.planning_style if relationship_profile is not None else None,
                tone_preferences=list(relationship_profile.tone_preferences) if relationship_profile is not None else [],
                interaction_boundaries=(
                    list(relationship_profile.interaction_boundaries) if relationship_profile is not None else []
                ),
                continuity_preferences=(
                    list(relationship_profile.continuity_preferences) if relationship_profile is not None else []
                ),
                open_practical_threads=open_practical_threads,
                open_emotional_threads=open_emotional_threads,
                promise_count=promise_count,
                open_follow_ups=open_follow_ups,
            ),
            last_memory_at=last_memory_at,
            review_debt_summary=review_debt_summary,
        )

    def _build_fallback_state(
        self,
        *,
        backend_status,
        latest_trace,
        heartbeat,
    ) -> FallbackState:
        fallback_backends = [
            f"{item.kind.value}:{item.backend_id}"
            for item in backend_status
            if item.status == RuntimeBackendAvailability.FALLBACK_ACTIVE
        ]
        degraded_backends = [
            f"{item.kind.value}:{item.backend_id}:{item.status.value}"
            for item in backend_status
            if item.status in {RuntimeBackendAvailability.DEGRADED, RuntimeBackendAvailability.UNAVAILABLE}
        ]
        notes: list[str] = []
        if heartbeat.safe_idle_active:
            notes.append(f"safe_idle:{heartbeat.safe_idle_reason or 'unknown'}")
        for item in backend_status:
            if item.status == RuntimeBackendAvailability.FALLBACK_ACTIVE and item.fallback_from:
                notes.append(f"backend_fallback:{item.kind.value}:{item.fallback_from}->{item.backend_id}")
        if latest_trace is not None:
            if latest_trace.reasoning.fallback_used:
                notes.append("trace_fallback_used")
            notes.extend(latest_trace.reasoning.notes)
            if latest_trace.outcome in {TraceOutcome.SAFE_FALLBACK, TraceOutcome.FALLBACK_REPLY, TraceOutcome.ERROR}:
                notes.append(f"trace_outcome:{latest_trace.outcome.value}")

        active = bool(
            heartbeat.safe_idle_active
            or fallback_backends
            or (
                latest_trace is not None
                and (
                    latest_trace.reasoning.fallback_used
                    or latest_trace.outcome in {TraceOutcome.SAFE_FALLBACK, TraceOutcome.FALLBACK_REPLY, TraceOutcome.ERROR}
                )
            )
        )
        classification = None
        if latest_trace is not None:
            classification = latest_trace.reasoning.fallback_classification
        return FallbackState(
            active=active,
            safe_idle_active=heartbeat.safe_idle_active,
            latest_trace_outcome=latest_trace.outcome.value if latest_trace is not None else None,
            latest_trace_fallback_used=latest_trace.reasoning.fallback_used if latest_trace is not None else False,
            classification=classification,
            fallback_backends=fallback_backends,
            degraded_backends=degraded_backends,
            notes=notes[:12],
        )

    def submit_text_turn(self, request: OperatorVoiceTurnRequest) -> OperatorInteractionResult:
        start = perf_counter()
        mode = request.voice_mode or self.default_live_voice_mode()
        resolved_request = request.model_copy(
            update={
                "session_id": request.session_id or self._resolve_session_id("console-live"),
                "source": request.source if request.source and request.source != "voice_stub" else "operator_console",
            }
        )
        diagnostics = self._build_live_turn_diagnostics(resolved_request)
        use_fast_presence = bool(
            self.shift_runner is not None
            and getattr(self.settings, "blink_fast_presence_enabled", True)
            and hasattr(self.shift_runner, "begin_presence_turn")
        )
        if use_fast_presence:
            self.shift_runner.begin_presence_turn(
                session_id=resolved_request.session_id,
                input_text=resolved_request.input_text,
                source=resolved_request.source,
                listening=not bool(resolved_request.input_text.strip()),
            )

        def observe_voice_state(state: SpeechOutputResult) -> None:
            if not use_fast_presence:
                return
            if state.status in {SpeechOutputStatus.TRANSCRIBING, SpeechOutputStatus.THINKING}:
                self.shift_runner.note_presence_thinking_fast(
                    session_id=resolved_request.session_id,
                    input_text=state.transcript_text,
                    message=state.message or "thinking_fast",
                )

        def observe_reply_ready(reply_text: str | None, audible: bool) -> None:
            if use_fast_presence:
                self.shift_runner.prepare_presence_reply(
                    session_id=resolved_request.session_id,
                    reply_text=reply_text,
                    audible=audible,
                )

        fast_presence_summary = None
        with self.orchestrator.capture_persist_metrics() as persist_metrics:
            camera_refresh_ms, browser_camera_refresh_applied = self._maybe_refresh_scene_from_request_camera(resolved_request)
            runtime = self.voice_manager.get_runtime(mode)
            try:
                outcome = runtime.handle_turn(
                    resolved_request,
                    self._turn_handler_with_context_refresh,
                    state_observer=observe_voice_state,
                    reply_ready_observer=observe_reply_ready,
                )
            except Exception as exc:
                if use_fast_presence:
                    self.shift_runner.degrade_presence_turn(
                        session_id=resolved_request.session_id,
                        reason=exc.__class__.__name__,
                        message=str(exc),
                    )
                raise
        command_acks = self._apply_response_commands(outcome.voice_turn.response, source="submit_text_turn")
        telemetry = self.edge_gateway.get_telemetry()
        heartbeat = self.edge_gateway.get_heartbeat()
        live_turn_diagnostics = outcome.voice_turn.live_turn_diagnostics or diagnostics
        if use_fast_presence:
            fast_presence_summary = self.shift_runner.complete_presence_turn(
                session_id=resolved_request.session_id,
                reply_text=outcome.voice_turn.response.reply_text,
                spoken=bool(
                    outcome.speech_output
                    and outcome.speech_output.status.value in {"speaking", "completed", "simulated"}
                ),
                completed=bool(
                    outcome.speech_output
                    and outcome.speech_output.status.value in {"completed", "simulated", "skipped", "failed", "interrupted"}
                ),
            )
        live_turn_diagnostics = live_turn_diagnostics.model_copy(
            update={
                "source": resolved_request.source,
                "visual_query": diagnostics.visual_query,
                "camera_frame_attached": diagnostics.camera_frame_attached,
                "spoken_reply_requested": diagnostics.spoken_reply_requested,
                "browser_speech_recognition_ms": (
                    diagnostics.browser_speech_recognition_ms
                    if diagnostics.browser_speech_recognition_ms is not None
                    else live_turn_diagnostics.browser_speech_recognition_ms
                ),
                "browser_camera_capture_ms": (
                    diagnostics.browser_camera_capture_ms
                    if diagnostics.browser_camera_capture_ms is not None
                    else live_turn_diagnostics.browser_camera_capture_ms
                ),
                "server_ingress_ms": (
                    diagnostics.server_ingress_ms
                    if diagnostics.server_ingress_ms is not None
                    else live_turn_diagnostics.server_ingress_ms
                ),
                "camera_refresh_ms": camera_refresh_ms,
                "camera_refresh_skipped": browser_camera_refresh_applied,
                "persistence_ms": round(persist_metrics.total_ms, 2),
                "persistence_writes": persist_metrics.write_count,
                "total_ms": round((perf_counter() - start) * 1000.0, 2),
                "fast_presence_acknowledged": (
                    fast_presence_summary.acknowledged
                    if fast_presence_summary is not None
                    else live_turn_diagnostics.fast_presence_acknowledged
                ),
                "fast_presence_ack_text": (
                    fast_presence_summary.acknowledgement_text
                    if fast_presence_summary is not None
                    else live_turn_diagnostics.fast_presence_ack_text
                ),
                "fast_presence_tool_working": (
                    fast_presence_summary.tool_working
                    if fast_presence_summary is not None
                    else live_turn_diagnostics.fast_presence_tool_working
                ),
                "fast_presence_working_text": (
                    fast_presence_summary.working_text
                    if fast_presence_summary is not None
                    else live_turn_diagnostics.fast_presence_working_text
                ),
            }
        )
        trace = self.orchestrator.get_trace(outcome.voice_turn.response.trace_id) if outcome.voice_turn.response.trace_id else None
        backend_status_by_kind = {
            item.kind.value: item
            for item in self.backend_router.runtime_statuses()
        }
        residency_by_kind = {
            item.kind.value: item
            for item in self.backend_router.model_residency()
        }
        text_backend_status = backend_status_by_kind.get("text_reasoning")
        tts_backend_status = backend_status_by_kind.get("text_to_speech")
        text_residency = residency_by_kind.get("text_reasoning")
        live_turn_diagnostics = live_turn_diagnostics.model_copy(
            update={
                "reasoning_backend": text_backend_status.backend_id if text_backend_status is not None else None,
                "tts_backend": tts_backend_status.backend_id if tts_backend_status is not None else None,
                "reasoning_ms": (
                    trace.reasoning.latency_breakdown.dialogue_ms
                    if trace is not None
                    else live_turn_diagnostics.reasoning_ms
                ),
                "reasoning_backend_latency_ms": (
                    text_backend_status.last_success_latency_ms
                    if text_backend_status is not None
                    else live_turn_diagnostics.reasoning_backend_latency_ms
                ),
                "tts_start_ms": live_turn_diagnostics.tts_launch_ms,
                "end_to_end_turn_ms": live_turn_diagnostics.total_ms,
                "text_model_warm": (
                    text_residency.resident
                    if text_backend_status is not None and text_backend_status.provider == "ollama" and text_residency is not None
                    else None
                ),
                "text_cold_start_retry_used": (
                    text_backend_status.cold_start_retry_used
                    if text_backend_status is not None
                    else live_turn_diagnostics.text_cold_start_retry_used
                ),
            }
        )
        if outcome.voice_turn.response.trace_id:
            self._attach_live_turn_diagnostics(outcome.voice_turn.response.trace_id, live_turn_diagnostics)
        voice_output = (
            outcome.speech_output.model_copy(update={"live_turn_diagnostics": live_turn_diagnostics})
            if outcome.speech_output is not None
            else None
        )
        return self._enrich_interaction(
            OperatorInteractionResult(
            session_id=outcome.voice_turn.session_id,
            interaction_type="voice_turn",
            event=outcome.voice_turn.transcript_event,
            response=outcome.voice_turn.response,
            command_acks=command_acks,
            telemetry=telemetry,
            heartbeat=heartbeat,
            success=self._is_success(command_acks),
            outcome=self._derive_outcome(outcome.voice_turn.response.trace_id, command_acks, heartbeat),
            latency_ms=round((perf_counter() - start) * 1000.0, 2),
            voice_output=voice_output,
            live_turn_diagnostics=live_turn_diagnostics,
            )
        )

    def inject_event(self, request: SimulatedSensorEventRequest) -> OperatorInteractionResult:
        start = perf_counter()
        resolved_session_id = request.session_id or self._resolve_session_id("console-live")
        try:
            sim_result = self.edge_gateway.simulate_event(
                request.model_copy(update={"session_id": resolved_session_id})
            )
        except EdgeGatewayError as exc:
            event = RobotEvent(
                event_type=request.event_type,
                session_id=resolved_session_id,
                source=request.source,
                payload=request.payload,
            )
            return self._enrich_interaction(
                OperatorInteractionResult(
                session_id=resolved_session_id,
                interaction_type="simulated_event",
                event=event,
                response=CommandBatch(
                    session_id=resolved_session_id,
                    reply_text="Edge transport degraded. I am holding safe idle until the tether recovers.",
                    commands=[],
                ),
                command_acks=[],
                telemetry=self.edge_gateway.get_telemetry(),
                heartbeat=self.edge_gateway.get_heartbeat(),
                success=False,
                outcome=f"transport_error:{exc.classification}",
                latency_ms=round((perf_counter() - start) * 1000.0, 2),
                )
            )
        response = self.orchestrator.handle_event(sim_result.event)
        command_acks = self._apply_response_commands(response, source="inject_event")
        telemetry = self.edge_gateway.get_telemetry()
        heartbeat = self.edge_gateway.get_heartbeat()
        return self._enrich_interaction(
            OperatorInteractionResult(
            session_id=resolved_session_id,
            interaction_type="simulated_event",
            event=sim_result.event,
            response=response,
            command_acks=command_acks,
            telemetry=telemetry,
            heartbeat=heartbeat,
            success=self._is_success(command_acks),
            outcome=self._derive_outcome(response.trace_id, command_acks, heartbeat),
            latency_ms=round((perf_counter() - start) * 1000.0, 2),
            )
        )

    def force_safe_idle(self, *, session_id: str | None = None, reason: str = "operator_override") -> OperatorInteractionResult:
        start = perf_counter()
        resolved_session_id = session_id or self._resolve_session_id("console-safe-idle")
        self.orchestrator.shift_supervisor.set_override(
            state=ShiftOperatingState.SAFE_IDLE,
            reason=reason,
            clear=False,
            session_id=resolved_session_id,
        )
        heartbeat = self.edge_gateway.force_safe_idle(reason)
        telemetry = self.edge_gateway.get_telemetry()
        event = RobotEvent(
            event_type="heartbeat",
            session_id=resolved_session_id,
            source="operator_console",
            payload={
                "network_ok": heartbeat.network_ok,
                "mode": telemetry.mode.value,
                "latency_ms": telemetry.network_latency_ms,
                "safe_idle_reason": heartbeat.safe_idle_reason,
            },
        )
        response = self.orchestrator.handle_event(event)
        command_acks = self._apply_response_commands(response, source="force_safe_idle")
        return self._enrich_interaction(
            OperatorInteractionResult(
            session_id=resolved_session_id,
            interaction_type="force_safe_idle",
            event=event,
            response=response,
            command_acks=command_acks,
            telemetry=self.edge_gateway.get_telemetry(),
            heartbeat=self.edge_gateway.get_heartbeat(),
            success=True,
            outcome=self._derive_outcome(response.trace_id, command_acks, heartbeat),
            latency_ms=round((perf_counter() - start) * 1000.0, 2),
            )
        )

    def get_body_status(self) -> BodyActionResult:
        return self._body_gateway_call("get_body_status")

    def get_action_plane_status(self) -> ActionPlaneStatus:
        runtime = self._action_plane_runtime()
        return runtime.action_plane_status()

    def get_action_plane_overview(
        self,
        *,
        session_id: str | None = None,
        limit: int = 12,
    ) -> ActionCenterOverviewRecord:
        runtime = self._action_plane_runtime()
        status = runtime.action_plane_status()
        connectors = runtime.action_plane_connectors().items
        approvals = runtime.action_plane_approvals().items
        if session_id is not None:
            approvals = [item for item in approvals if item.request.session_id == session_id]
        history = runtime.action_plane_history(limit=200).items
        if session_id is not None:
            history = [item for item in history if item.session_id == session_id]
        recent_history = history[:limit]
        recent_failures = [
            item
            for item in history
            if item.status.value in {"failed", "rejected", "uncertain_review_required"}
        ][:limit]
        workflow_runs = runtime.action_plane_workflow_runs(session_id=session_id, limit=200).items
        active_workflows = [
            item
            for item in workflow_runs
            if item.status.value in {"running", "paused", "waiting_for_approval", "suggested"}
        ][:limit]
        recent_bundles = runtime.action_plane_bundles(session_id=session_id, limit=limit).items
        browser_status = runtime.action_plane_browser_status(session_id=session_id)
        latest_replays = runtime.action_plane_replays(session_id=session_id, limit=limit)
        attention_items = self._build_action_center_items(
            runtime=runtime,
            session_id=session_id,
            approvals=approvals,
            active_workflows=active_workflows,
            recent_failures=recent_failures,
            connector_health=status.connector_health,
            history=history,
        )
        status = status.model_copy(
            update={
                "pending_approval_count": len(approvals),
                "active_workflow_run_count": len(active_workflows),
                "waiting_workflow_count": sum(1 for item in active_workflows if item.status.value == "waiting_for_approval"),
                "review_required_count": (
                    sum(1 for item in recent_failures if item.status.value == "uncertain_review_required")
                    + sum(
                        1
                        for item in active_workflows
                        if item.pause_reason is not None and item.pause_reason.value == "runtime_restart_review"
                    )
                ),
                "last_action_id": recent_history[0].action_id if recent_history else status.last_action_id,
                "last_action_status": recent_history[0].status if recent_history else status.last_action_status,
                "latest_failure_action_id": (
                    recent_failures[0].action_id if recent_failures else status.latest_failure_action_id
                ),
            }
        )
        return ActionCenterOverviewRecord(
            status=status,
            attention_items=attention_items,
            connectors=connectors,
            approvals=approvals[:limit],
            active_workflows=active_workflows,
            recent_history=recent_history,
            recent_bundles=recent_bundles,
            browser_status=browser_status,
            latest_replays=latest_replays,
            recent_failures=recent_failures,
        )

    def _build_action_center_items(
        self,
        *,
        runtime,
        session_id: str | None,
        approvals,
        active_workflows,
        recent_failures,
        connector_health,
        history,
    ) -> list[ActionCenterItemRecord]:
        execution_by_action = {item.action_id: item for item in history}
        bundle_store = runtime.action_gateway.bundle_store
        items: list[ActionCenterItemRecord] = []
        seen: set[tuple[str, str | None, str | None]] = set()

        for approval in approvals:
            execution = execution_by_action.get(approval.action_id) or runtime.action_gateway.get_execution(approval.action_id)
            bundle = bundle_store.find_bundle_for_action(approval.action_id)
            key = ("approval", approval.action_id, bundle.bundle_id if bundle is not None else None)
            if key in seen:
                continue
            seen.add(key)
            approval_summary = self._describe_action_plane_reason(
                detail=approval.detail,
                policy_decision=approval.policy_decision,
                risk_class=getattr(approval.request, "risk_class", None),
                connector_id=approval.connector_id,
                action_name=approval.action_name or approval.tool_name,
            )
            if execution is not None and execution.operator_summary and execution.status.value != "pending_approval":
                approval_summary = execution.operator_summary
            items.append(
                ActionCenterItemRecord(
                    kind="approval",
                    severity="warning",
                    title=f"Approval required: {approval.action_name or approval.tool_name}",
                    summary=approval_summary,
                    action_id=approval.action_id,
                    bundle_id=bundle.bundle_id if bundle is not None else None,
                    session_id=approval.request.session_id,
                    next_step_hint=(
                        execution.next_step_hint
                        if execution is not None and execution.next_step_hint
                        else "Approve or reject this action in the Action Center."
                    ),
                    detail_ref={"kind": "approval", "action_id": approval.action_id},
                )
            )

        for run in active_workflows:
            if run.status.value not in {"paused", "waiting_for_approval", "failed"}:
                continue
            severity = "warning"
            if run.pause_reason and run.pause_reason.value == "runtime_restart_review":
                severity = "danger"
            elif run.status.value == "failed":
                severity = "danger"
            key = ("workflow", run.workflow_run_id, None)
            if key in seen:
                continue
            seen.add(key)
            items.append(
                ActionCenterItemRecord(
                    kind="workflow",
                    severity=severity,
                    title=f"Workflow: {run.label}",
                    summary=run.detail or run.summary or run.status.value,
                    workflow_run_id=run.workflow_run_id,
                    bundle_id=bundle_store.bundle_id_for_workflow_run(run.workflow_run_id),
                    session_id=run.session_id,
                    next_step_hint=(
                        "Review the linked action, then resume or retry this workflow."
                        if run.pause_reason and run.pause_reason.value == "runtime_restart_review"
                        else (
                            "Approve or reject the blocking action to continue."
                            if run.status.value == "waiting_for_approval"
                            else "Resume, retry, or pause this workflow from the Action Center."
                        )
                    ),
                    detail_ref={"kind": "workflow", "workflow_run_id": run.workflow_run_id},
                )
            )

        for execution in recent_failures:
            kind = (
                "review_required"
                if execution.status.value == "uncertain_review_required"
                else "action_failure"
            )
            bundle = bundle_store.find_bundle_for_action(execution.action_id)
            key = (kind, execution.action_id, bundle.bundle_id if bundle is not None else None)
            if key in seen:
                continue
            seen.add(key)
            items.append(
                ActionCenterItemRecord(
                    kind=kind,
                    severity="danger" if execution.status.value != "rejected" else "warning",
                    title=f"Action: {execution.action_name or execution.tool_name}",
                    summary=execution.operator_summary or execution.detail or execution.error_detail or execution.status.value,
                    action_id=execution.action_id,
                    workflow_run_id=execution.workflow_run_id,
                    bundle_id=bundle.bundle_id if bundle is not None else None,
                    session_id=execution.session_id,
                    next_step_hint=execution.next_step_hint,
                    detail_ref={"kind": kind, "action_id": execution.action_id},
                )
            )

        for record in connector_health:
            if record.status == "healthy" and record.supported and record.configured:
                continue
            key = ("connector_issue", record.connector_id, None)
            if key in seen:
                continue
            seen.add(key)
            items.append(
                ActionCenterItemRecord(
                    kind="connector_issue",
                    severity="warning",
                    title=f"Connector degraded: {record.connector_id}",
                    summary=record.detail or record.status,
                    session_id=session_id,
                    next_step_hint="Non-browser connectors remain usable; inspect connector health before retrying degraded actions.",
                    detail_ref={"kind": "connector", "connector_id": record.connector_id},
                )
            )

        severity_rank = {"danger": 0, "warning": 1, "info": 2}
        items.sort(key=lambda item: (severity_rank.get(item.severity, 3), item.title))
        return items

    def list_action_plane_connectors(self) -> ConnectorCatalogResponse:
        runtime = self._action_plane_runtime()
        return runtime.action_plane_connectors()

    def list_action_plane_approvals(self) -> ActionApprovalListResponse:
        runtime = self._action_plane_runtime()
        return runtime.action_plane_approvals()

    def list_action_plane_history(self, *, limit: int = 50) -> ActionExecutionListResponse:
        runtime = self._action_plane_runtime()
        return runtime.action_plane_history(limit=limit)

    def list_action_plane_bundles(
        self,
        *,
        session_id: str | None = None,
        limit: int = 50,
    ) -> ActionBundleListResponse:
        runtime = self._action_plane_runtime()
        return runtime.action_plane_bundles(session_id=session_id, limit=limit)

    def get_action_plane_bundle(self, bundle_id: str) -> ActionBundleDetailRecord | None:
        runtime = self._action_plane_runtime()
        return runtime.action_plane_bundle(bundle_id)

    def list_action_plane_workflows(self) -> WorkflowCatalogResponse:
        runtime = self._action_plane_runtime()
        return runtime.action_plane_workflows()

    def list_action_plane_workflow_runs(
        self,
        *,
        session_id: str | None = None,
        limit: int = 50,
    ) -> WorkflowRunListResponse:
        runtime = self._action_plane_runtime()
        return runtime.action_plane_workflow_runs(session_id=session_id, limit=limit)

    def get_action_plane_workflow_run(self, workflow_run_id: str) -> WorkflowRunRecord | None:
        runtime = self._action_plane_runtime()
        return runtime.action_plane_workflow_run(workflow_run_id)

    def start_action_plane_workflow(self, request: WorkflowStartRequestRecord) -> WorkflowRunActionResponseRecord:
        runtime = self._action_plane_runtime()
        tool_context = self._build_action_plane_tool_context(
            session_id=request.session_id,
            invocation_origin=ActionInvocationOrigin.OPERATOR_CONSOLE,
        )
        return runtime.start_action_plane_workflow(request=request, tool_context=tool_context)

    def start_proactive_action_plane_workflow(self, request: WorkflowStartRequestRecord) -> WorkflowRunActionResponseRecord:
        runtime = self._action_plane_runtime()
        tool_context = self._build_action_plane_tool_context(
            session_id=request.session_id,
            invocation_origin=ActionInvocationOrigin.PROACTIVE_RUNTIME,
        )
        return runtime.start_action_plane_workflow(request=request, tool_context=tool_context)

    def resume_action_plane_workflow(
        self,
        workflow_run_id: str,
        request: WorkflowRunActionRequestRecord,
    ) -> WorkflowRunActionResponseRecord:
        runtime = self._action_plane_runtime()
        run = runtime.action_plane_workflow_run(workflow_run_id)
        tool_context = self._build_action_plane_tool_context(
            session_id=run.session_id if run is not None else None,
            invocation_origin=ActionInvocationOrigin.OPERATOR_CONSOLE,
        )
        return runtime.resume_action_plane_workflow(
            workflow_run_id=workflow_run_id,
            request=request,
            tool_context=tool_context,
        )

    def retry_action_plane_workflow(
        self,
        workflow_run_id: str,
        request: WorkflowRunActionRequestRecord,
    ) -> WorkflowRunActionResponseRecord:
        runtime = self._action_plane_runtime()
        run = runtime.action_plane_workflow_run(workflow_run_id)
        tool_context = self._build_action_plane_tool_context(
            session_id=run.session_id if run is not None else None,
            invocation_origin=ActionInvocationOrigin.OPERATOR_CONSOLE,
        )
        return runtime.retry_action_plane_workflow(
            workflow_run_id=workflow_run_id,
            request=request,
            tool_context=tool_context,
        )

    def pause_action_plane_workflow(
        self,
        workflow_run_id: str,
        request: WorkflowRunActionRequestRecord,
    ) -> WorkflowRunActionResponseRecord:
        runtime = self._action_plane_runtime()
        return runtime.pause_action_plane_workflow(
            workflow_run_id=workflow_run_id,
            request=request,
        )

    def get_action_plane_browser_status(self, *, session_id: str | None = None) -> BrowserRuntimeStatusRecord:
        runtime = self._action_plane_runtime()
        return runtime.action_plane_browser_status(session_id=session_id)

    def run_action_plane_browser_task(self, request: BrowserActionTaskRequest) -> BrowserTaskToolOutput:
        runtime = self._action_plane_runtime()
        tool_context = self._build_action_plane_tool_context(
            session_id=request.session_id,
            invocation_origin=ActionInvocationOrigin.OPERATOR_CONSOLE,
        )
        record, output = runtime.tool_registry.invoke(
            "browser_task",
            {
                "query": request.query,
                "target_url": request.target_url,
                "requested_action": request.requested_action,
                "target_hint": (
                    request.target_hint.model_dump(mode="json")
                    if request.target_hint is not None
                    else None
                ),
                "text_input": request.text_input,
            },
            context=tool_context,
        )
        if output is None:
            raise RuntimeError(record.error_detail or record.error_code or "browser_task_failed")
        return output

    def approve_action_plane_action(self, request: ActionApprovalResolutionRequest) -> ActionApprovalResolutionRecord:
        runtime = self._action_plane_runtime()
        return runtime.resolve_action_plane_approval(
            action_id=request.action_id,
            approve=True,
            operator_note=request.operator_note,
            tool_context=self._build_action_plane_tool_context(),
        )

    def reject_action_plane_action(self, request: ActionApprovalResolutionRequest) -> ActionApprovalResolutionRecord:
        runtime = self._action_plane_runtime()
        return runtime.resolve_action_plane_approval(
            action_id=request.action_id,
            approve=False,
            operator_note=request.operator_note,
            tool_context=self._build_action_plane_tool_context(),
        )

    def replay_action_plane_action(self, request: ActionReplayRequestRecord):
        runtime = self._action_plane_runtime()
        return runtime.replay_action_plane_action(
            replay=request,
            tool_context=self._build_action_plane_tool_context(),
        ).execution

    def replay_action_plane_bundle(self, request: ActionReplayRequestRecord) -> ActionReplayRecord:
        runtime = self._action_plane_runtime()
        return runtime.replay_action_plane_bundle(replay=request)

    def add_action_plane_bundle_teacher_annotation(
        self,
        bundle_id: str,
        request: TeacherReviewRequest,
    ) -> TeacherAnnotationRecord:
        runtime = self._action_plane_runtime()
        detail = runtime.action_plane_bundle(bundle_id)
        if detail is None:
            raise KeyError(bundle_id)
        manifest = detail.manifest
        if manifest.root_kind.value == "workflow_run":
            scope = "workflow_run"
            scope_id = manifest.root_workflow_run_id or manifest.workflow_run_id
            action_id = None
            workflow_run_id = manifest.root_workflow_run_id or manifest.workflow_run_id
        else:
            scope = "action"
            scope_id = manifest.root_action_id
            action_id = manifest.root_action_id
            workflow_run_id = manifest.workflow_run_id
        if not scope_id:
            raise RuntimeError("bundle_missing_teacher_review_scope")
        record = self.orchestrator.add_teacher_annotation(
            scope=scope,
            scope_id=scope_id,
            request=request,
            session_id=manifest.session_id,
            run_id=manifest.run_id,
            action_id=action_id,
            workflow_run_id=workflow_run_id,
        )
        runtime.action_gateway.bundle_store.record_teacher_annotation(record)
        for episode_id in manifest.linked_episode_ids:
            episode = self.episode_exporter.get_episode(episode_id)
            if episode is None:
                continue
            annotations = self.episode_exporter._teacher_annotations_for_export(
                episode_id=episode_id,
                session_ids=episode.session_ids,
                traces=episode.traces,
                actions=episode.memory_actions,
                run_ids=episode.run_ids,
            )
            self.episode_exporter.episode_store.replace_teacher_annotations(
                episode_id,
                annotations,
                outcome_label=self._latest_outcome_label(annotations),
            )
        return record

    def evaluate_action_plane_workflow_triggers(
        self,
        *,
        session_id: str | None = None,
        shift_snapshot,
        now=None,
    ) -> list[WorkflowRunActionResponseRecord]:
        runtime = self._action_plane_runtime()
        tool_context = self._build_action_plane_tool_context(
            session_id=session_id or shift_snapshot.active_session_id,
            invocation_origin=ActionInvocationOrigin.PROACTIVE_RUNTIME,
        )
        return runtime.evaluate_action_plane_workflow_triggers(
            tool_context=tool_context,
            shift_snapshot=shift_snapshot,
            now=now,
        )

    def connect_body(self, request: BodyConnectRequest) -> BodyActionResult:
        return self._body_gateway_call(
            "connect_body",
            port=request.port,
            baud=request.baud,
            timeout_seconds=request.timeout_seconds,
        )

    def disconnect_body(self) -> BodyActionResult:
        return self._body_gateway_call("disconnect_body")

    def scan_body(self, request: BodyIdsRequest | None = None) -> BodyActionResult:
        return self._body_gateway_call("scan_body", ids=(request.ids if request is not None else None))

    def ping_body(self, request: BodyIdsRequest | None = None) -> BodyActionResult:
        return self._body_gateway_call("ping_body", ids=(request.ids if request is not None else None))

    def read_body_health(self, request: BodyIdsRequest | None = None) -> BodyActionResult:
        return self._body_gateway_call("read_body_health", ids=(request.ids if request is not None else None))

    def arm_body_motion(self, request: BodyArmRequest) -> BodyActionResult:
        return self._body_gateway_call("arm_body_motion", ttl_seconds=request.ttl_seconds, author=request.author)

    def disarm_body_motion(self) -> BodyActionResult:
        return self._body_gateway_call("disarm_body_motion")

    def write_body_neutral(self) -> BodyActionResult:
        return self._body_gateway_call("write_body_neutral")

    def run_body_power_preflight(self) -> BodyActionResult:
        return self._body_gateway_call("run_body_power_preflight")

    def get_body_servo_lab_catalog(self) -> BodyActionResult:
        return self._body_gateway_call("get_body_servo_lab_catalog")

    def read_body_servo_lab(self, request: BodyServoLabReadbackRequest) -> BodyActionResult:
        return self._body_gateway_call(
            "read_body_servo_lab",
            joint_name=request.joint_name,
            include_health=request.include_health,
        )

    def move_body_servo_lab(self, request: BodyServoLabMoveRequest) -> BodyActionResult:
        return self._body_gateway_call(
            "move_body_servo_lab",
            joint_name=request.joint_name,
            reference_mode=request.reference_mode.value,
            target_raw=request.target_raw,
            delta_counts=request.delta_counts,
            lab_min=request.lab_min,
            lab_max=request.lab_max,
            duration_ms=request.duration_ms,
            speed_override=request.speed_override,
            acceleration_override=request.acceleration_override,
            note=request.note,
        )

    def sweep_body_servo_lab(self, request: BodyServoLabSweepRequest) -> BodyActionResult:
        return self._body_gateway_call(
            "sweep_body_servo_lab",
            joint_name=request.joint_name,
            lab_min=request.lab_min,
            lab_max=request.lab_max,
            cycles=request.cycles,
            duration_ms=request.duration_ms,
            dwell_ms=request.dwell_ms,
            speed_override=request.speed_override,
            acceleration_override=request.acceleration_override,
            return_to_neutral=request.return_to_neutral,
            note=request.note,
        )

    def save_body_servo_lab_calibration(self, request: BodyServoLabSaveCalibrationRequest) -> BodyActionResult:
        return self._body_gateway_call(
            "save_body_servo_lab_calibration",
            joint_name=request.joint_name,
            save_current_as_neutral=request.save_current_as_neutral,
            raw_min=request.raw_min,
            raw_max=request.raw_max,
            confirm_mirrored=request.confirm_mirrored,
            note=request.note,
        )

    def get_body_semantic_library(self, *, smoke_safe_only: bool = False) -> BodyActionResult:
        return self._body_gateway_call("get_body_semantic_library", smoke_safe_only=smoke_safe_only)

    def get_body_expression_catalog(self) -> BodyActionResult:
        return self._body_gateway_call("get_body_expression_catalog")

    def run_body_semantic_smoke(self, request: BodySemanticSmokeRequest) -> BodyActionResult:
        return self._body_gateway_call(
            "run_body_semantic_smoke",
            action=request.action,
            intensity=request.intensity,
            repeat_count=request.repeat_count,
            note=request.note,
            allow_bench_actions=request.allow_bench_actions,
        )

    def run_body_primitive_sequence(self, request: BodyPrimitiveSequenceRequest) -> BodyActionResult:
        return self._body_gateway_call(
            "run_body_primitive_sequence",
            steps=[step.model_dump(mode="json", exclude_none=True) for step in request.steps],
            sequence_name=request.sequence_name,
            note=request.note,
        )

    def run_body_expressive_motif(self, request: BodyExpressiveSequenceRequest) -> BodyActionResult:
        return self._body_gateway_call(
            "run_body_expressive_motif",
            motif=request.motif.model_dump(mode="json", exclude_none=True) if request.motif is not None else None,
            steps=[step.model_dump(mode="json", exclude_none=True) for step in request.steps],
            sequence_name=request.sequence_name,
            note=request.note,
        )

    def run_body_staged_sequence(self, request: BodyStagedSequenceRequest) -> BodyActionResult:
        return self._body_gateway_call(
            "run_body_staged_sequence",
            stages=[stage.model_dump(mode="json", exclude_none=True) for stage in request.stages],
            sequence_name=request.sequence_name,
            note=request.note,
        )

    def run_body_range_demo(
        self,
        *,
        sequence_name: str | None = None,
        preset_name: str | None = None,
        note: str | None = None,
    ) -> BodyActionResult:
        return self._body_gateway_call(
            "run_body_range_demo",
            sequence_name=sequence_name,
            preset_name=preset_name,
            note=note,
        )

    def record_body_teacher_review(self, request: BodyTeacherReviewRequest) -> BodyActionResult:
        return self._body_gateway_call(
            "record_body_teacher_review",
            action=request.action,
            review=request.review,
            note=request.note,
            proposed_tuning_delta=request.proposed_tuning_delta,
            apply_tuning=request.apply_tuning,
        )

    def _body_gateway_call(self, method_name: str, **kwargs) -> BodyActionResult:
        handler = getattr(self.edge_gateway, method_name, None)
        if handler is None:
            return BodyActionResult(
                ok=False,
                status="unsupported",
                detail="serial_body_gateway_not_available",
                body_state=self.edge_gateway.get_telemetry().body_state,
            )
        result = handler(**kwargs)
        detail = result.get("detail")
        if isinstance(detail, list):
            detail = ", ".join(str(item) for item in detail)
        elif detail is not None:
            detail = str(detail)
        body_state = result.get("body_state")
        if body_state is None:
            body_state = self.edge_gateway.get_telemetry().body_state
        return BodyActionResult(
            ok=bool(result.get("ok", False)),
            status=str(result.get("status") or "unknown"),
            detail=detail,
            body_state=body_state,
            transport_summary=dict(result.get("transport_summary") or {}),
            report_path=str(result.get("report_path")) if result.get("report_path") else None,
            motion_report_path=str(result.get("motion_report_path")) if result.get("motion_report_path") else None,
            payload=dict(result.get("payload") or {}),
        )

    def _action_plane_runtime(self):
        agent_runtime = getattr(self.orchestrator, "agent_runtime", None)
        if agent_runtime is None:
            raise RuntimeError("agent_runtime_unavailable")
        return agent_runtime

    def _build_action_plane_tool_context(
        self,
        *,
        session_id: str | None = None,
        invocation_origin: ActionInvocationOrigin = ActionInvocationOrigin.OPERATOR_CONSOLE,
    ):
        runtime = self._action_plane_runtime()
        sessions = self.orchestrator.list_sessions().items
        world_state = self.orchestrator.get_world_state()
        participant_router = self.orchestrator.get_participant_router()
        active_session_id = (
            session_id
            or participant_router.active_session_id
            or world_state.last_session_id
            or (sessions[0].session_id if sessions else None)
        )
        if active_session_id is None:
            raise RuntimeError("no_active_session_for_action_plane")
        session = self.orchestrator.get_session(active_session_id)
        if session is None:
            raise RuntimeError("active_session_not_found_for_action_plane")
        user_memory = self.orchestrator.memory.get_user_memory(session.user_id) if session.user_id else None
        latest_perception = self.perception_service.get_latest_snapshot(active_session_id) or self.perception_service.get_latest_snapshot()
        context_mode = (
            CompanionContextMode.VENUE_DEMO
            if session.scenario_name
            else self.settings.blink_context_mode
        )
        return runtime.build_tool_runtime_context(
            session=session,
            context_mode=context_mode,
            user_memory=user_memory,
            world_state=world_state,
            world_model=self.orchestrator.get_world_model(),
            latest_perception=latest_perception,
            backend_status=self.backend_router.runtime_statuses(),
            tool_invocations=[],
            run_id=None,
            action_invocation_origin=invocation_origin,
        )

    def cancel_voice(self, *, session_id: str | None = None, voice_mode: VoiceRuntimeMode | None = None):
        return self.voice_manager.cancel(voice_mode or self.default_live_voice_mode(), session_id)

    def submit_perception_snapshot(self, request: PerceptionSnapshotSubmitRequest) -> PerceptionSubmissionResult:
        resolved_session_id = request.session_id or self._resolve_session_id("console-live")
        result = self.perception_service.submit_snapshot(request.model_copy(update={"session_id": resolved_session_id}))
        enriched_results = []
        for item in result.published_results:
            command_acks = self._apply_response_commands(item.response, source="submit_perception_snapshot")
            item.command_acks = command_acks
            item.success = self._is_success(command_acks)
            item.outcome = self._derive_outcome(item.response.trace_id, command_acks, self.edge_gateway.get_heartbeat())
            enriched_results.append(item)
        result.published_results = enriched_results
        result.success = result.success and all(item.success for item in enriched_results)
        return result

    def replay_perception_fixture(self, request: PerceptionReplayRequest) -> PerceptionReplayResult:
        resolved_session_id = request.session_id or self._resolve_session_id("console-live")
        result = self.perception_service.replay_fixture(request.model_copy(update={"session_id": resolved_session_id}))
        for snapshot_result in result.snapshots:
            for item in snapshot_result.published_results:
                command_acks = self._apply_response_commands(item.response, source="replay_perception_fixture")
                item.command_acks = command_acks
                item.success = self._is_success(command_acks)
                item.outcome = self._derive_outcome(item.response.trace_id, command_acks, self.edge_gateway.get_heartbeat())
            snapshot_result.success = snapshot_result.success and all(item.success for item in snapshot_result.published_results)
        result.success = result.success and all(item.success for item in result.snapshots)
        return result

    def run_shift_tick(self, request: ShiftAutonomyTickRequest | None = None) -> OperatorInteractionResult:
        start = perf_counter()
        tick_request = request or ShiftAutonomyTickRequest()
        telemetry = self.edge_gateway.get_telemetry()
        heartbeat = self.edge_gateway.get_heartbeat()
        event = self.orchestrator.build_shift_tick_event(
            session_id=tick_request.session_id or self._resolve_session_id("shift-supervisor"),
            timestamp=tick_request.timestamp,
            source=tick_request.source,
            telemetry=telemetry,
            heartbeat=heartbeat,
            transport_state=self.edge_gateway.transport_state(),
            transport_error=self.edge_gateway.last_transport_error(),
            extra_payload=tick_request.payload,
        )
        response = self.orchestrator.handle_event(event)
        command_acks = self._apply_response_commands(response, source="run_shift_tick")
        return self._enrich_interaction(
            OperatorInteractionResult(
                session_id=event.session_id or "shift-supervisor",
                interaction_type="shift_tick",
                event=event,
                response=response,
                command_acks=command_acks,
                telemetry=self.edge_gateway.get_telemetry(),
                heartbeat=self.edge_gateway.get_heartbeat(),
                success=self._is_success(command_acks),
                outcome=self._derive_outcome(response.trace_id, command_acks, heartbeat),
                latency_ms=round((perf_counter() - start) * 1000.0, 2),
            )
        )

    def set_shift_override(self, request: ShiftOverrideRequest, *, session_id: str | None = None):
        resolved_session_id = session_id or self._resolve_session_id("shift-supervisor")
        return self.orchestrator.shift_supervisor.set_override(
            state=request.state,
            reason=request.reason,
            clear=request.clear,
            session_id=resolved_session_id,
        )

    def update_live_voice_state(
        self,
        request: LiveVoiceStateUpdateRequest,
        *,
        session_id: str | None = None,
    ) -> SpeechOutputResult:
        resolved_session_id = session_id or request.session_id or self._resolve_session_id("console-live")
        return self.voice_manager.update_state(
            request.voice_mode,
            request.model_copy(update={"session_id": resolved_session_id}),
            resolved_session_id,
        )

    def list_investor_scenes(self) -> InvestorSceneCatalogResponse:
        return list_investor_scenes()

    def list_performance_shows(self) -> PerformanceShowCatalogResponse:
        if self.performance_show_manager is None:
            return PerformanceShowCatalogResponse()
        return self.performance_show_manager.catalog()

    def run_performance_show(
        self,
        show_name: str,
        request: PerformanceRunRequest | None = None,
    ) -> PerformanceRunResult:
        if self.performance_show_manager is None:
            raise RuntimeError("performance_show_manager_unavailable")
        return self.performance_show_manager.run_show(show_name, request)

    def get_performance_run(self, run_id: str) -> PerformanceRunResult | None:
        if self.performance_show_manager is None:
            return None
        return self.performance_show_manager.get_run(run_id)

    def cancel_performance_run(self, run_id: str) -> PerformanceRunResult:
        if self.performance_show_manager is None:
            raise RuntimeError("performance_show_manager_unavailable")
        return self.performance_show_manager.cancel_run(run_id)

    def get_profile_memory(self, user_id: str) -> UserMemoryRecord | None:
        return self.orchestrator.get_profile_memory(user_id)

    def list_episodic_memory(
        self,
        *,
        session_id: str | None = None,
        user_id: str | None = None,
        limit: int = 50,
    ):
        return self.orchestrator.list_episodic_memory(session_id=session_id, user_id=user_id, limit=limit)

    def list_semantic_memory(
        self,
        *,
        session_id: str | None = None,
        user_id: str | None = None,
        limit: int = 100,
    ) -> SemanticMemoryListResponse:
        return self.orchestrator.list_semantic_memory(session_id=session_id, user_id=user_id, limit=limit)

    def list_memory_retrievals(
        self,
        *,
        session_id: str | None = None,
        user_id: str | None = None,
        trace_id: str | None = None,
        run_id: str | None = None,
        limit: int = 100,
    ) -> MemoryRetrievalListResponse:
        return self.orchestrator.list_memory_retrievals(
            session_id=session_id,
            user_id=user_id,
            trace_id=trace_id,
            run_id=run_id,
            limit=limit,
        )

    def memory_review_debt_summary(self) -> MemoryReviewDebtSummary:
        return self.orchestrator.memory_review_debt_summary()

    def review_memory(self, request: MemoryReviewRequest):
        return self.orchestrator.review_memory(request)

    def correct_memory(self, request: MemoryReviewRequest):
        return self.orchestrator.correct_memory(request)

    def delete_memory(self, request: MemoryReviewRequest):
        return self.orchestrator.delete_memory(request)

    def get_episode_teacher_annotations(self, episode_id: str) -> TeacherAnnotationListResponse:
        episode = self.episode_exporter.get_episode(episode_id)
        if episode is None:
            raise KeyError(episode_id)
        return self.orchestrator.list_teacher_annotations(episode_id=episode_id, limit=500)

    def add_episode_teacher_annotation(self, episode_id: str, request: TeacherReviewRequest) -> TeacherAnnotationRecord:
        episode = self.episode_exporter.get_episode(episode_id)
        if episode is None:
            raise KeyError(episode_id)
        record = self.orchestrator.add_teacher_annotation(
            scope="episode",
            scope_id=episode_id,
            request=request,
            episode_id=episode_id,
            session_id=episode.session_ids[0] if episode.session_ids else None,
        )
        annotations = self.orchestrator.list_teacher_annotations(episode_id=episode_id, limit=500).items
        self.episode_exporter.episode_store.replace_teacher_annotations(
            episode_id,
            annotations,
            outcome_label=request.outcome_label,
        )
        return record

    def _latest_outcome_label(self, annotations: list[TeacherAnnotationRecord]) -> str | None:
        for annotation in reversed(annotations):
            if annotation.outcome_label:
                return annotation.outcome_label
        return None

    def add_trace_teacher_annotation(self, trace_id: str, request: TeacherReviewRequest) -> TeacherAnnotationRecord:
        trace = self.orchestrator.get_trace(trace_id)
        if trace is None:
            raise KeyError(trace_id)
        return self.orchestrator.add_teacher_annotation(
            scope="trace",
            scope_id=trace_id,
            request=request,
            session_id=trace.session_id,
            trace_id=trace_id,
        )

    def get_run_teacher_annotations(self, run_id: str) -> TeacherAnnotationListResponse:
        run = self.get_run(run_id)
        if run is None:
            raise KeyError(run_id)
        return self.orchestrator.list_teacher_annotations(run_id=run_id, limit=500)

    def add_run_teacher_annotation(self, run_id: str, request: TeacherReviewRequest) -> TeacherAnnotationRecord:
        run = self.get_run(run_id)
        if run is None:
            raise KeyError(run_id)
        return self.orchestrator.add_teacher_annotation(
            scope="run",
            scope_id=run_id,
            request=request,
            session_id=run.session_id,
            run_id=run_id,
            trace_id=run.trace_id,
        )

    def list_benchmarks(self) -> BenchmarkCatalogResponse:
        return self._benchmark_runner().catalog()

    def run_benchmarks(self, request: BenchmarkRunRequest) -> BenchmarkRunRecord:
        return self._benchmark_runner().run(request)

    def list_benchmark_evidence_packs(self) -> BenchmarkEvidencePackListResponse:
        return self._benchmark_runner().list_evidence_packs()

    def get_benchmark_evidence_pack(self, pack_id: str) -> BenchmarkEvidencePackV1 | None:
        return self._benchmark_runner().get_evidence_pack(pack_id)

    def list_planners(self) -> PlannerCatalogResponse:
        return self._replay_harness().list_planners()

    def replay_episode(self, request: PlannerReplayRequest) -> PlannerReplayRecord:
        return self._replay_harness().replay_episode(request)

    def get_replay(self, replay_id: str) -> PlannerReplayRecord | None:
        return self._replay_harness().get_replay(replay_id)

    def list_episodes(self) -> EpisodeListResponseV2:
        return self.episode_exporter.list_episodes()

    def get_episode(self, episode_id: str) -> EpisodeRecordV2 | None:
        return self.episode_exporter.get_episode(episode_id)

    def export_research_bundle(
        self,
        episode_id: str,
        request: ResearchExportRequest | None = None,
    ) -> ResearchBundleManifest:
        if self.episode_exporter.get_episode(episode_id) is None:
            raise KeyError(episode_id)
        return self._research_exporter().export_episode(
            episode_id,
            formats=(request.formats if request is not None else None),
            redaction_profile=(
                request.redaction_profile
                if request is not None
                else ExportRedactionProfile.RESEARCH_REDACTED
            ),
        )

    def export_dataset_manifest(self, request: DatasetExportRequest) -> DatasetManifestV1:
        return self._dataset_builder().export_dataset(request)

    def list_dataset_manifests(self) -> DatasetManifestListResponse:
        return self._dataset_builder().list_datasets()

    def get_dataset_manifest(self, dataset_id: str) -> DatasetManifestV1 | None:
        return self._dataset_builder().get_dataset(dataset_id)

    def export_session_episode(
        self,
        request: EpisodeExportSessionRequest,
        *,
        extra_artifacts: dict[str, object] | None = None,
    ) -> EpisodeRecordV2:
        snapshot = self.get_snapshot(session_id=request.session_id)
        body_telemetry = self.edge_gateway.get_telemetry()
        runtime_artifacts = (
            self.shift_runner.export_artifacts()
            if self.shift_runner is not None and hasattr(self.shift_runner, "export_artifacts")
            else {}
        )
        body_command_audits = self.edge_gateway.get_body_command_audits() if hasattr(self.edge_gateway, "get_body_command_audits") else []
        body_motion_report_index = (
            self.edge_gateway.get_body_motion_report_index()
            if hasattr(self.edge_gateway, "get_body_motion_report_index")
            else []
        )
        body_semantic_tuning = (
            self.edge_gateway.get_body_semantic_tuning()
            if hasattr(self.edge_gateway, "get_body_semantic_tuning")
            else {}
        )
        body_teacher_reviews = (
            self.edge_gateway.get_body_teacher_reviews()
            if hasattr(self.edge_gateway, "get_body_teacher_reviews")
            else []
        )
        serial_failure_summary = (
            self.edge_gateway.get_body_serial_failure_summary()
            if hasattr(self.edge_gateway, "get_body_serial_failure_summary")
            else {}
        )
        serial_request_response_history = (
            self.edge_gateway.get_body_request_response_history()
            if hasattr(self.edge_gateway, "get_body_request_response_history")
            else []
        )
        return self.episode_exporter.export_session(
            request,
            extra_artifacts={
                "runtime_snapshot": snapshot,
                "console_snapshot": snapshot,
                "body_telemetry": body_telemetry,
                "body_command_audits": body_command_audits,
                "body_motion_report_index": body_motion_report_index,
                "body_semantic_tuning": body_semantic_tuning,
                "body_teacher_reviews": body_teacher_reviews,
                "serial_failure_summary": serial_failure_summary,
                "serial_request_response_history": serial_request_response_history,
                **runtime_artifacts,
                **(extra_artifacts or {}),
            },
        )

    def export_demo_run_episode(self, request: EpisodeExportRunRequest) -> EpisodeRecordV2:
        return self.episode_exporter.export_run(request)

    def export_shift_report_episode(self, request: EpisodeExportShiftReportRequest) -> EpisodeRecordV2:
        return self.episode_exporter.export_shift_report(request)

    def list_incidents(
        self,
        *,
        scope: IncidentListScope = IncidentListScope.ALL,
        session_id: str | None = None,
        limit: int = 50,
    ):
        return self.orchestrator.list_incidents(scope=scope, session_id=session_id, limit=limit)

    def get_incident(self, ticket_id: str) -> IncidentTicketRecord | None:
        return self.orchestrator.get_incident(ticket_id)

    def acknowledge_incident(self, ticket_id: str, request: IncidentAcknowledgeRequest) -> IncidentTicketRecord:
        return self.orchestrator.acknowledge_incident(ticket_id, request)

    def assign_incident(self, ticket_id: str, request: IncidentAssignRequest) -> IncidentTicketRecord:
        return self.orchestrator.assign_incident(ticket_id, request)

    def add_incident_note(self, ticket_id: str, request: IncidentNoteRequest) -> IncidentTicketRecord:
        return self.orchestrator.add_incident_note(ticket_id, request)

    def resolve_incident(self, ticket_id: str, request: IncidentResolveRequest) -> IncidentTicketRecord:
        return self.orchestrator.resolve_incident(ticket_id, request)

    def run_investor_scene(self, scene_name: str, request: InvestorSceneRunRequest | None = None) -> InvestorSceneRunResult:
        definition = INVESTOR_SCENES.get(scene_name)
        if definition is None:
            raise KeyError(scene_name)

        run_request = request or InvestorSceneRunRequest()
        session_id = run_request.session_id or definition.session_id
        user_id = run_request.user_id or definition.user_id
        items: list[OperatorInteractionResult] = []
        perception_snapshots: list[PerceptionSnapshotRecord] = []
        success = True
        start = perf_counter()

        for step in definition.steps:
            if step.action_type == "voice_turn":
                item = self.submit_text_turn(
                    OperatorVoiceTurnRequest(
                        session_id=session_id,
                        user_id=user_id,
                        input_text=step.input_text or "",
                        response_mode=run_request.response_mode,
                        voice_mode=run_request.voice_mode,
                        speak_reply=run_request.speak_reply,
                        source="investor_scene",
                    )
                )
                item.step_label = step.label
                items.append(item)
                success = success and item.success
                continue

            if step.action_type == "inject_event":
                item = self.inject_event(
                    SimulatedSensorEventRequest(
                        event_type=step.event_type or "heartbeat",
                        payload=step.payload,
                        session_id=session_id,
                        source="investor_scene",
                    )
                )
                item.step_label = step.label
                items.append(item)
                success = success and item.success
                continue

            if step.action_type == "perception_fixture":
                replay = self.replay_perception_fixture(
                    PerceptionReplayRequest(
                        session_id=session_id,
                        fixture_path=step.fixture_path or "",
                        source="investor_scene",
                        publish_events=step.publish_events,
                    )
                )
                perception_snapshots.extend(snapshot_result.snapshot for snapshot_result in replay.snapshots)
                replay_items = self._interaction_results_from_replay(step.label, replay)
                items.extend(replay_items)
                success = success and replay.success and all(item.success for item in replay_items)
                continue

            if step.action_type == "perception_snapshot":
                source_frame = None
                payload_metadata = dict(step.payload)
                captured_at_offset_seconds = payload_metadata.pop("captured_at_offset_seconds", None)
                if isinstance(captured_at_offset_seconds, (int, float)):
                    source_frame = PerceptionSourceFrame(
                        source_kind="investor_scene",
                        source_label=step.label,
                        captured_at=utc_now() + timedelta(seconds=float(captured_at_offset_seconds)),
                    )
                submission = self.submit_perception_snapshot(
                    PerceptionSnapshotSubmitRequest(
                        session_id=session_id,
                        provider_mode=step.perception_mode or PerceptionProviderMode.MANUAL_ANNOTATIONS,
                        source="investor_scene",
                        source_frame=source_frame,
                        annotations=step.annotations,
                        metadata=payload_metadata,
                        publish_events=step.publish_events,
                    )
                )
                perception_snapshots.append(submission.snapshot)
                submission_items = self._interaction_results_from_submission(step.label, submission)
                items.extend(submission_items)
                success = success and submission.success and all(item.success for item in submission_items)
                continue

            raise KeyError(f"unsupported_scene_action:{step.action_type}")

        executive_decisions = self.orchestrator.list_executive_decisions(session_id=session_id, limit=50).items
        world_model_transitions = self.orchestrator.list_world_model_transitions(session_id=session_id, limit=50).items
        engagement_timeline = self.orchestrator.list_engagement_timeline(session_id=session_id, limit=50)
        final_action = self._scene_final_action(items)
        scorecard = self._scene_scorecard(
            definition=definition,
            session_id=session_id,
            items=items,
            perception_snapshots=perception_snapshots,
            executive_decisions=executive_decisions,
            final_action=final_action,
        )
        success = success and scorecard.passed

        return InvestorSceneRunResult(
            scene_name=definition.scene_name,
            title=definition.title,
            description=definition.description,
            session_id=session_id,
            items=items,
            success=success,
            note="Scene completed" if success else "One or more steps degraded or failed",
            perception_snapshots=perception_snapshots,
            executive_decisions=executive_decisions,
            world_model_transitions=world_model_transitions,
            engagement_timeline=engagement_timeline,
            grounding_sources=self._scene_grounding_sources(items),
            latency_breakdown=self._scene_latency_breakdown(items, total_ms=round((perf_counter() - start) * 1000.0, 2)),
            scorecard=scorecard,
            final_action=final_action,
        )

    def default_live_voice_mode(self) -> VoiceRuntimeMode:
        configured = self.settings.live_voice_default_mode
        if configured in VoiceRuntimeMode._value2member_map_:
            return VoiceRuntimeMode(configured)
        return VoiceRuntimeMode.STUB_DEMO

    def _resolve_session_id(self, fallback: str) -> str:
        world_state = self.orchestrator.get_world_state()
        return world_state.last_session_id or fallback

    def _attach_live_turn_diagnostics(self, trace_id: str, diagnostics: LiveTurnDiagnosticsRecord) -> None:
        trace = self.orchestrator.get_trace(trace_id)
        if trace is None:
            return
        trace.reasoning.live_turn_diagnostics = diagnostics
        try:
            self.orchestrator.update_trace(trace)
        except KeyError:
            logger.warning("live_turn_trace_update_missing", extra={"trace_id": trace_id})

    def _maybe_refresh_scene_from_request_camera(self, request: OperatorVoiceTurnRequest) -> tuple[float | None, bool]:
        if not request.camera_image_data_url or request.camera_source_frame is None:
            return None, False
        if not self._looks_like_visual_query(request.input_text):
            return None, False
        provider_mode = request.camera_provider_mode or self._semantic_provider_mode()
        if provider_mode is None:
            return None, False
        started = perf_counter()
        try:
            self.submit_perception_snapshot(
                PerceptionSnapshotSubmitRequest(
                    session_id=request.session_id,
                    provider_mode=provider_mode,
                    source="browser_live_visual_refresh",
                    source_frame=request.camera_source_frame,
                    image_data_url=request.camera_image_data_url,
                    metadata={"reason": "visual_query_refresh", "user_id": request.user_id},
                    # The reply path reads latest_perception directly, so avoid a second
                    # full event-processing pass before the actual answer.
                    publish_events=False,
                )
            )
            request.input_metadata["browser_camera_refresh_applied"] = True
            return round((perf_counter() - started) * 1000.0, 2), True
        except Exception:
            logger.exception("browser_live_visual_refresh_failed")
            return None, False

    def _turn_handler_with_context_refresh(self, request: VoiceTurnRequest) -> VoiceTurnResult:
        if not bool(request.input_metadata.get("browser_camera_refresh_applied")):
            self._maybe_refresh_scene_for_visual_query(
                session_id=request.session_id,
                user_id=request.user_id,
                text=request.input_text,
            )
        return self.orchestrator.handle_voice_turn(request)

    def _maybe_refresh_scene_for_visual_query(
        self,
        *,
        session_id: str,
        user_id: str | None,
        text: str,
    ) -> None:
        if not self._looks_like_visual_query(text):
            return
        provider_mode = self._semantic_provider_mode()
        if provider_mode is None:
            return
        latest = self.perception_service.get_latest_snapshot(session_id) or self.perception_service.get_latest_snapshot()
        if latest is not None:
            captured_at = latest.source_frame.captured_at or latest.created_at
            age_seconds = (utc_now() - captured_at).total_seconds()
            if (
                latest.provider_mode in {PerceptionProviderMode.OLLAMA_VISION, PerceptionProviderMode.MULTIMODAL_LLM}
                and not latest.limited_awareness
                and age_seconds <= max(15.0, float(self.settings.blink_semantic_refresh_min_interval_seconds))
            ):
                return
        camera_source = self.device_registry.camera_capture.source
        if camera_source.mode != "webcam":
            return
        try:
            capture = self.device_registry.capture_camera_snapshot()
        except Exception:
            return
        self.submit_perception_snapshot(
            PerceptionSnapshotSubmitRequest(
                session_id=session_id,
                provider_mode=provider_mode,
                source="before_reply_generation",
                source_frame=capture.source_frame,
                image_data_url=capture.image_data_url,
                metadata={"reason": "visual_query_refresh", "user_id": user_id},
                # The upcoming dialogue turn will consume the fresh semantic snapshot
                # directly, so publishing perception events here only adds latency.
                publish_events=False,
            )
        )

    def _semantic_provider_mode(self) -> PerceptionProviderMode | None:
        if hasattr(self.backend_router, "selected_semantic_perception_mode"):
            return self.backend_router.selected_semantic_perception_mode()
        backend_id = self.backend_router.selected_backend_id(RuntimeBackendKind.VISION_ANALYSIS)
        return {
            "ollama_vision": PerceptionProviderMode.OLLAMA_VISION,
            "multimodal_llm": PerceptionProviderMode.MULTIMODAL_LLM,
        }.get(backend_id)

    def _looks_like_visual_query(self, text: str) -> bool:
        return looks_like_visual_query(text)

    def _apply_response_commands(self, response: CommandBatch, *, source: str) -> list[CommandAck]:
        body_batch_id = response.trace_id or f"body-batch-{uuid4().hex[:8]}"
        log_event(
            logger,
            logging.INFO,
            "body_command_batch_started",
            body_batch_id=body_batch_id,
            source=source,
            session_id=response.session_id,
            trace_id=response.trace_id,
            command_count=len(response.commands),
        )
        command_acks = [self.edge_gateway.apply_command(command) for command in response.commands]
        log_event(
            logger,
            logging.INFO if self._is_success(command_acks) else logging.WARNING,
            "body_command_batch_completed",
            body_batch_id=body_batch_id,
            source=source,
            session_id=response.session_id,
            trace_id=response.trace_id,
            command_count=len(response.commands),
            accepted_count=sum(1 for ack in command_acks if ack.accepted),
        )
        return command_acks

    def _is_success(self, command_acks: list[CommandAck]) -> bool:
        return all(ack.accepted and ack.status != CommandAckStatus.TRANSPORT_ERROR for ack in command_acks)

    def _derive_outcome(self, trace_id: str | None, command_acks: list[CommandAck], heartbeat) -> str:
        if any(ack.status == CommandAckStatus.TRANSPORT_ERROR for ack in command_acks):
            return "transport_error"
        if heartbeat.safe_idle_active:
            return "safe_fallback"
        if any(not ack.accepted for ack in command_acks):
            return "error"
        if trace_id:
            trace = self.orchestrator.get_trace(trace_id)
            if trace:
                if trace.outcome == TraceOutcome.SAFE_FALLBACK:
                    return "safe_fallback"
                if trace.outcome == TraceOutcome.FALLBACK_REPLY:
                    return "fallback_reply"
                return trace.outcome.value
        return "ok"

    def _enrich_interaction(self, result: OperatorInteractionResult) -> OperatorInteractionResult:
        result.shift_supervisor = self.orchestrator.get_shift_supervisor()
        result.participant_router = self.orchestrator.get_participant_router()
        result.venue_operations = self.orchestrator.get_venue_operations()
        if not result.response.trace_id:
            return result
        trace = self.orchestrator.get_trace(result.response.trace_id)
        if trace is None:
            return result
        result.latency_breakdown = trace.reasoning.latency_breakdown
        result.grounding_sources = trace.reasoning.grounding_sources
        result.incident_ticket = trace.reasoning.incident_ticket
        result.incident_timeline = trace.reasoning.incident_timeline
        result.live_turn_diagnostics = trace.reasoning.live_turn_diagnostics or result.live_turn_diagnostics
        if result.voice_output is not None and result.live_turn_diagnostics is not None:
            result.voice_output = result.voice_output.model_copy(
                update={"live_turn_diagnostics": result.live_turn_diagnostics}
            )
        return result

    def _interaction_results_from_submission(
        self,
        step_label: str,
        submission: PerceptionSubmissionResult,
    ) -> list[OperatorInteractionResult]:
        interactions: list[OperatorInteractionResult] = []
        if submission.published_results:
            for item in submission.published_results:
                interactions.append(
                    self._enrich_interaction(
                        OperatorInteractionResult(
                            session_id=submission.session_id or item.event.session_id or "console-live",
                            interaction_type="perception_snapshot",
                            event=item.event,
                            response=item.response,
                            command_acks=item.command_acks,
                            telemetry=self.edge_gateway.get_telemetry(),
                            heartbeat=self.edge_gateway.get_heartbeat(),
                            success=item.success,
                            outcome=item.outcome,
                            latency_ms=submission.latency_breakdown.total_ms,
                            step_label=step_label,
                            latency_breakdown=submission.latency_breakdown,
                            perception_snapshot=submission.snapshot,
                        )
                    )
                )
            return interactions

        synthetic_event = RobotEvent(
            event_type="scene_summary_updated",
            session_id=submission.session_id,
            source="investor_scene",
            payload={
                "scene_summary": submission.snapshot.scene_summary,
                "limited_awareness": submission.snapshot.limited_awareness,
            },
        )
        return [
            OperatorInteractionResult(
                session_id=submission.session_id or "console-live",
                interaction_type="perception_snapshot",
                event=synthetic_event,
                response=CommandBatch(session_id=submission.session_id or "console-live", reply_text=None, commands=[]),
                command_acks=[],
                telemetry=self.edge_gateway.get_telemetry(),
                heartbeat=self.edge_gateway.get_heartbeat(),
                success=submission.success,
                outcome="ok" if submission.success else "error",
                latency_ms=submission.latency_breakdown.total_ms,
                step_label=step_label,
                latency_breakdown=submission.latency_breakdown,
                perception_snapshot=submission.snapshot,
            )
        ]

    def _interaction_results_from_replay(
        self,
        step_label: str,
        replay: PerceptionReplayResult,
    ) -> list[OperatorInteractionResult]:
        interactions: list[OperatorInteractionResult] = []
        for index, submission in enumerate(replay.snapshots, start=1):
            interactions.extend(self._interaction_results_from_submission(f"{step_label} frame {index}", submission))
        return interactions

    def _scene_grounding_sources(self, items: list[OperatorInteractionResult]) -> list[GroundingSourceRecord]:
        results: list[GroundingSourceRecord] = []
        seen: set[tuple[str, str, str | None, str | None]] = set()
        for item in items:
            for source in item.grounding_sources:
                key = (source.source_type.value, source.label, source.source_ref, source.detail)
                if key in seen:
                    continue
                seen.add(key)
                results.append(source)
        return results

    def _scene_latency_breakdown(
        self,
        items: list[OperatorInteractionResult],
        *,
        total_ms: float,
    ) -> LatencyBreakdownRecord:
        return LatencyBreakdownRecord(
            total_ms=total_ms,
            perception_ms=round(sum(item.latency_breakdown.perception_ms or 0.0 for item in items), 2),
            tool_ms=round(sum(item.latency_breakdown.tool_ms or 0.0 for item in items), 2),
            dialogue_ms=round(sum(item.latency_breakdown.dialogue_ms or 0.0 for item in items), 2),
            executive_ms=round(sum(item.latency_breakdown.executive_ms or 0.0 for item in items), 2),
            publish_ms=round(sum(item.latency_breakdown.publish_ms or 0.0 for item in items), 2),
        )

    def _scene_final_action(self, items: list[OperatorInteractionResult]) -> FinalActionRecord | None:
        for item in reversed(items):
            if item.response.reply_text or item.response.commands:
                trace = self.orchestrator.get_trace(item.response.trace_id or "") if item.response.trace_id else None
                reason_codes: list[str] = []
                executive_state = None
                intent = None
                if trace is not None:
                    reason_codes = [
                        code
                        for decision in trace.reasoning.executive_decisions
                        for code in decision.reason_codes
                    ]
                    executive_state = trace.reasoning.executive_state
                    intent = trace.reasoning.intent
                return FinalActionRecord(
                    intent=intent,
                    reply_text=item.response.reply_text,
                    command_types=[command.command_type for command in item.response.commands],
                    trace_id=item.response.trace_id,
                    executive_state=executive_state,
                    reason_codes=reason_codes,
                )
        return None

    def _scene_scorecard(
        self,
        *,
        definition: InvestorSceneDefinition,
        session_id: str,
        items: list[OperatorInteractionResult],
        perception_snapshots: list[PerceptionSnapshotRecord],
        executive_decisions,
        final_action: FinalActionRecord | None,
    ) -> DemoSceneScorecard:
        session = self.orchestrator.get_session(session_id)
        world_model = self.orchestrator.get_world_model()
        reply_texts = " ".join(item.response.reply_text or "" for item in items).lower()
        decision_types = {decision.decision_type.value for decision in executive_decisions}
        policy_outcomes = {decision.policy_outcome for decision in executive_decisions if decision.policy_outcome}
        criteria: list[ScorecardCriterion] = []

        if definition.scene_name == "approach_and_greet":
            criteria.extend(
                [
                    ScorecardCriterion(criterion="perception_detected_visitor", passed=bool(perception_snapshots), observed=str(len(perception_snapshots))),
                    ScorecardCriterion(criterion="auto_greet_triggered", passed="auto_greet" in decision_types, observed=",".join(sorted(decision_types))),
                    ScorecardCriterion(criterion="greeting_visible", passed="welcome" in reply_texts or "hello" in reply_texts or "hi." in reply_texts, observed=reply_texts),
                ]
            )
        elif definition.scene_name == "natural_discussion":
            user_memory = self.orchestrator.memory.get_user_memory(session.user_id) if session and session.user_id else None
            criteria.extend(
                [
                    ScorecardCriterion(
                        criterion="quiet_help_grounded",
                        passed="quiet room" in reply_texts,
                        observed=reply_texts,
                    ),
                    ScorecardCriterion(
                        criterion="name_captured",
                        passed=bool(user_memory and user_memory.display_name == "Alex"),
                        observed=user_memory.display_name if user_memory is not None else None,
                    ),
                    ScorecardCriterion(
                        criterion="preference_captured",
                        passed=bool(user_memory and user_memory.preferences.get("route_preference") == "quiet route"),
                        observed=user_memory.preferences.get("route_preference") if user_memory is not None else None,
                    ),
                ]
            )
        elif definition.scene_name == "attentive_listening":
            criteria.extend(
                [
                    ScorecardCriterion(
                        criterion="listening_policy_triggered",
                        passed="keep_listening" in decision_types,
                        observed=",".join(sorted(decision_types)),
                    ),
                    ScorecardCriterion(
                        criterion="did_not_over_reply",
                        passed=not reply_texts.strip(),
                        observed=reply_texts or "(no reply)",
                    ),
                ]
            )
        elif definition.scene_name in {"wayfinding_usefulness", "venue_helpful_question"}:
            criteria.extend(
                [
                    ScorecardCriterion(
                        criterion="venue_answer_grounded",
                        passed="workshop room" in reply_texts,
                        observed=reply_texts,
                    ),
                    ScorecardCriterion(
                        criterion="attentive_embodiment_emitted",
                        passed=bool(
                            final_action
                            and any(command.value in {"set_expression", "set_gaze"} for command in final_action.command_types)
                        ),
                        observed=",".join(command.value for command in final_action.command_types) if final_action else None,
                    ),
                ]
            )
        elif definition.scene_name == "knowledge_grounded_help":
            criteria.extend(
                [
                    ScorecardCriterion(
                        criterion="events_answer_grounded",
                        passed="robotics workshop" in reply_texts or "community coffee hour" in reply_texts,
                        observed=reply_texts,
                    ),
                    ScorecardCriterion(
                        criterion="tool_backed_help",
                        passed=bool(items and any(source.source_type.value in {"venue", "tool"} for source in items[-1].grounding_sources)),
                        observed=",".join(source.source_type.value for source in (items[-1].grounding_sources if items else [])),
                    ),
                ]
            )
        elif definition.scene_name == "read_visible_sign_and_answer":
            criteria.extend(
                [
                    ScorecardCriterion(
                        criterion="visible_text_extracted",
                        passed=any(
                            observation.observation_type.value == "visible_text"
                            for snapshot in perception_snapshots
                            for observation in snapshot.observations
                        ),
                        observed=perception_snapshots[-1].scene_summary if perception_snapshots else None,
                    ),
                    ScorecardCriterion(
                        criterion="sign_answer_grounded",
                        passed="workshop room" in reply_texts or "community events today" in reply_texts,
                        observed=reply_texts,
                    ),
                ]
            )
        elif definition.scene_name == "observe_and_comment":
            criteria.extend(
                [
                    ScorecardCriterion(
                        criterion="fresh_visible_text_extracted",
                        passed=any(
                            observation.observation_type.value == "visible_text"
                            for snapshot in perception_snapshots
                            for observation in snapshot.observations
                        ),
                        observed=perception_snapshots[-1].scene_summary if perception_snapshots else None,
                    ),
                    ScorecardCriterion(
                        criterion="reply_grounded_to_scene",
                        passed="workshop room" in reply_texts or "community events today" in reply_texts,
                        observed=reply_texts,
                    ),
                ]
            )
        elif definition.scene_name == "scene_grounded_comment":
            latest_grounding_sources = items[-1].grounding_sources if items else []
            criteria.extend(
                [
                    ScorecardCriterion(
                        criterion="scene_fact_grounding_visible",
                        passed=bool(
                            latest_grounding_sources
                            and any(source.source_type.value == "perception_fact" for source in latest_grounding_sources)
                        ),
                        observed=",".join(source.source_type.value for source in latest_grounding_sources),
                    ),
                    ScorecardCriterion(
                        criterion="scene_comment_mentions_grounded_fact",
                        passed=(
                            "workshop room" in reply_texts
                            or "community events today" in reply_texts
                            or "workshop corridor sign" in reply_texts
                        ),
                        observed=reply_texts,
                    ),
                ]
            )
        elif definition.scene_name == "remember_person_context_across_turns":
            remembered_name = session.session_memory.get("remembered_name") if session else None
            criteria.extend(
                [
                    ScorecardCriterion(criterion="remembered_name_stored", passed=bool(remembered_name), observed=remembered_name),
                    ScorecardCriterion(criterion="remembered_name_recalled", passed="maya" in reply_texts, observed=reply_texts),
                ]
            )
        elif definition.scene_name == "companion_memory_follow_up":
            memory_source_types = {
                source.source_type.value
                for source in (items[-1].grounding_sources if items else [])
            }
            criteria.extend(
                [
                    ScorecardCriterion(
                        criterion="profile_memory_recalled",
                        passed="alex" in reply_texts and "quiet route" in reply_texts,
                        observed=reply_texts,
                    ),
                    ScorecardCriterion(
                        criterion="memory_grounding_visible",
                        passed=bool(
                            memory_source_types.intersection(
                                {"profile_memory", "semantic_memory", "episodic_memory"}
                            )
                            or (session and session.current_topic == "user_memory")
                        ),
                        observed=",".join(sorted(memory_source_types)) or (session.current_topic if session else None),
                    ),
                ]
            )
        elif definition.scene_name == "detect_disengagement_and_shorten_reply":
            last_reply = next((item.response.reply_text or "" for item in reversed(items) if item.response.reply_text), "")
            criteria.extend(
                [
                    ScorecardCriterion(criterion="disengagement_detected", passed="shorten_reply" in decision_types, observed=",".join(sorted(decision_types))),
                    ScorecardCriterion(criterion="reply_shortened", passed=len(last_reply.split()) <= 20, observed=last_reply),
                ]
            )
        elif definition.scene_name == "disengagement_shortening":
            last_reply = next((item.response.reply_text or "" for item in reversed(items) if item.response.reply_text), "")
            criteria.extend(
                [
                    ScorecardCriterion(
                        criterion="disengagement_policy_fired",
                        passed="shorten_reply" in decision_types,
                        observed=",".join(sorted(decision_types)),
                    ),
                    ScorecardCriterion(
                        criterion="reply_shortened",
                        passed=len(last_reply.split()) <= 20,
                        observed=last_reply,
                    ),
                ]
            )
        elif definition.scene_name == "two_person_attention_handoff":
            criteria.extend(
                [
                    ScorecardCriterion(
                        criterion="two_participants_tracked",
                        passed=len(world_model.active_participants_in_view) >= 2,
                        observed=str(len(world_model.active_participants_in_view)),
                    ),
                    ScorecardCriterion(
                        criterion="attention_handed_to_recent_speaker",
                        passed=world_model.current_speaker_participant_id == "visitor_b",
                        observed=world_model.current_speaker_participant_id,
                    ),
                    ScorecardCriterion(
                        criterion="speaker_hypothesis_source_visible",
                        passed=world_model.speaker_hypothesis_source == "recent_speech_in_active_session",
                        observed=world_model.speaker_hypothesis_source,
                    ),
                ]
            )
        elif definition.scene_name == "escalate_after_confusion_or_accessibility_request":
            first_reply = items[0].response.reply_text.lower() if items and items[0].response.reply_text else ""
            criteria.extend(
                [
                    ScorecardCriterion(
                        criterion="confusion_handled_honestly",
                        passed="ask_clarifying_question" in decision_types or "do not have a confirmed venue entry" in first_reply,
                        observed=first_reply or ",".join(sorted(decision_types)),
                    ),
                    ScorecardCriterion(
                        criterion="human_escalation_requested",
                        passed=bool(session and session.status == SessionStatus.ESCALATION_PENDING),
                        observed=session.status.value if session else None,
                    ),
                ]
            )
        elif definition.scene_name in {"perception_unavailable_honest_fallback", "safe_degraded_behavior"}:
            criteria.extend(
                [
                    ScorecardCriterion(
                        criterion="limited_awareness_visible",
                        passed=bool(perception_snapshots and perception_snapshots[-1].limited_awareness),
                        observed=perception_snapshots[-1].scene_summary if perception_snapshots else None,
                    ),
                    ScorecardCriterion(
                        criterion="honest_fallback_language",
                        passed=(
                            "limited" in reply_texts
                            or "do not have a confident" in reply_texts
                            or "freshest visible text" in reply_texts
                            or "anchor i can ground" in reply_texts
                        ),
                        observed=reply_texts,
                    ),
                ]
            )
        elif definition.scene_name == "uncertainty_admission":
            criteria.extend(
                [
                    ScorecardCriterion(
                        criterion="uncertainty_policy_visible",
                        passed="uncertainty_admission" in policy_outcomes,
                        observed=",".join(sorted(item for item in policy_outcomes if item)),
                    ),
                    ScorecardCriterion(
                        criterion="reply_admits_limited_awareness",
                        passed="limited" in reply_texts or "cautiously report" in reply_texts,
                        observed=reply_texts,
                    ),
                ]
            )
        elif definition.scene_name == "stale_scene_suppression":
            criteria.extend(
                [
                    ScorecardCriterion(
                        criterion="stale_scene_policy_visible",
                        passed="stale_scene_suppressed" in policy_outcomes,
                        observed=",".join(sorted(item for item in policy_outcomes if item)),
                    ),
                    ScorecardCriterion(
                        criterion="reply_does_not_claim_stale_scene_as_current",
                        passed="limited" in reply_texts or "do not have fresh visual facts" in reply_texts,
                        observed=reply_texts,
                    ),
                ]
            )
        elif definition.scene_name == "operator_correction_after_wrong_scene_interpretation":
            latest_grounding_sources = items[-1].grounding_sources if items else []
            criteria.extend(
                [
                    ScorecardCriterion(
                        criterion="operator_annotation_visible_in_grounding",
                        passed=any(
                            source.claim_kind is not None and source.claim_kind.value == "operator_annotation"
                            for source in latest_grounding_sources
                        ),
                        observed=",".join(
                            source.claim_kind.value
                            for source in latest_grounding_sources
                            if source.claim_kind is not None
                        ),
                    ),
                    ScorecardCriterion(
                        criterion="corrected_scene_fact_used",
                        passed="workshop room" in reply_texts,
                        observed=reply_texts,
                    ),
                ]
            )

        if final_action is not None:
            criteria.append(
                ScorecardCriterion(
                    criterion="final_action_selected",
                    passed=bool(final_action.command_types or final_action.reply_text),
                    observed=",".join(command.value for command in final_action.command_types) or final_action.reply_text,
                )
            )

        return DemoSceneScorecard(
            scene_name=definition.scene_name,
            title=definition.title,
            passed=all(item.passed for item in criteria),
            score=float(sum(1 for item in criteria if item.passed)),
            max_score=float(len(criteria)),
            criteria=criteria,
        )
