from __future__ import annotations

import base64
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
import shutil
import subprocess
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path
from time import perf_counter

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from embodied_stack.backends.router import BackendRouter
from embodied_stack.brain.agent_os.tools import BrowserTaskToolOutput
from embodied_stack.brain.auth import OperatorAuthManager
from embodied_stack.brain.live_voice import LiveVoiceRuntimeManager
from embodied_stack.brain.operator_console import OperatorConsoleService
from embodied_stack.brain.orchestrator import BrainOrchestrator
from embodied_stack.brain.perception import PerceptionService
from embodied_stack.brain.visual_query import looks_like_visual_query
from embodied_stack.brain.shift_runner import ShiftAutonomyRunner
from embodied_stack.config import Settings, get_settings
from embodied_stack.demo.coordinator import DemoCoordinator
from embodied_stack.demo.episodes import EpisodeStore, build_exporter
from embodied_stack.demo.performance_show import PerformanceShowManager
from embodied_stack.demo.shift_reports import ShiftReportStore
from embodied_stack.desktop.devices import DesktopDeviceRegistry, build_desktop_device_registry
from embodied_stack.desktop.profiles import apply_desktop_profile
from embodied_stack.desktop.runtime_profile import ApplianceProfileStore
from embodied_stack.desktop.runtime import build_default_embodiment_gateway
from embodied_stack.shared.readiness import build_service_readiness_response
from embodied_stack.shared.contracts import (
    ActionApprovalListResponse,
    ActionApprovalResolutionRecord,
    ActionApprovalResolutionRequest,
    ActionBundleDetailRecord,
    ActionBundleListResponse,
    ActionCenterOverviewRecord,
    ActionExecutionListResponse,
    ActionExecutionRecord,
    ActionPlaneStatus,
    ActionReplayRecord,
    ActionReplayRequestRecord,
    ApplianceBootstrapResponse,
    ApplianceDeviceCatalog,
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
    BrainResetRequest,
    BrowserActionTaskRequest,
    BrowserRuntimeStatusRecord,
    CheckpointListResponse,
    BodyDriverMode,
    BrowserAudioTurnRequest,
    BrowserAudioTurnResult,
    BenchmarkEvidencePackListResponse,
    BenchmarkEvidencePackV1,
    CommandBatch,
    ConnectorCatalogResponse,
    WorkflowCatalogResponse,
    WorkflowRunActionRequestRecord,
    WorkflowRunActionResponseRecord,
    WorkflowRunListResponse,
    WorkflowRunRecord,
    WorkflowStartRequestRecord,
    DatasetExportRequest,
    DatasetManifestListResponse,
    DatasetManifestV1,
    DemoRunListResponse,
    DemoRunRecord,
    DemoRunRequest,
    EmbodiedWorldModel,
    EpisodicMemoryListResponse,
    EpisodeExportRunRequest,
    EpisodeExportSessionRequest,
    EpisodeExportShiftReportRequest,
    ExecutiveDecisionListResponse,
    IncidentAcknowledgeRequest,
    IncidentAssignRequest,
    IncidentListResponse,
    IncidentListScope,
    IncidentNoteRequest,
    IncidentResolveRequest,
    IncidentTicketRecord,
    InvestorSceneCatalogResponse,
    InvestorSceneRunRequest,
    InvestorSceneRunResult,
    LiveVoiceStateUpdateRequest,
    LogListResponse,
    OperatorNoteRequest,
    OperatorAuthLoginRequest,
    OperatorAuthStatus,
    OperatorConsoleSnapshot,
    CharacterPresenceSurfaceSnapshot,
    OperatorInteractionResult,
    OperatorVoiceTurnRequest,
    PerceptionFixtureCatalogResponse,
    PerceptionHistoryResponse,
    PerceptionReplayRequest,
    PerceptionReplayResult,
    PerceptionSnapshotRecord,
    PerceptionSnapshotSubmitRequest,
    PerceptionSubmissionResult,
    PerformanceShowCatalogResponse,
    PerformanceRunRequest,
    PerformanceRunResult,
    PlannerCatalogResponse,
    PlannerReplayRecord,
    PlannerReplayRequest,
    ReadinessCheck,
    ResearchBundleManifest,
    ResearchExportRequest,
    ResetResult,
    RobotEvent,
    RunExportResponse,
    RunListResponse,
    RunRecord,
    ScenarioCatalogResponse,
    ScenarioReplayRequest,
    ScenarioReplayResult,
    SemanticMemoryListResponse,
    SessionCreateRequest,
    SessionListResponse,
    SessionRecord,
    SessionResponseModeRequest,
    ServiceReadinessResponse,
    ShiftAutonomyTickRequest,
    ShiftOverrideRequest,
    ShiftReportListResponse,
    ShiftReportRecord,
    ShiftSupervisorSnapshot,
    ShiftTransitionListResponse,
    SimulatedSensorEventRequest,
    SpeechOutputResult,
    TraceListResponse,
    TraceRecord,
    VoiceCancelResult,
    VoiceRuntimeMode,
    VoiceTurnRequest,
    VoiceTurnResult,
    WorldState,
)
from embodied_stack.shared.contracts.brain import (
    MemoryRetrievalListResponse,
    MemoryReviewDebtSummary,
    MemoryReviewRecord,
    MemoryReviewRequest,
    UserMemoryRecord,
)
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


_BROWSER_AUDIO_SUFFIXES = {
    "audio/webm": ".webm",
    "audio/ogg": ".ogg",
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
    "audio/mpeg": ".mp3",
    "audio/mp4": ".m4a",
    "audio/aac": ".aac",
}
_BROWSER_LIVE_EXECUTOR = ThreadPoolExecutor(max_workers=4, thread_name_prefix="blink-browser-live")


def _decode_browser_audio_data_url(data_url: str, *, mime_type: str | None = None) -> tuple[str, bytes]:
    if not data_url.startswith("data:") or "," not in data_url:
        raise HTTPException(status_code=400, detail="browser_audio_data_url_invalid")
    header, encoded = data_url.split(",", 1)
    resolved_mime = mime_type or header[5:].split(";", 1)[0] or "application/octet-stream"
    if ";base64" not in header:
        raise HTTPException(status_code=400, detail="browser_audio_not_base64")
    try:
        payload = base64.b64decode(encoded, validate=True)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="browser_audio_base64_invalid") from exc
    return resolved_mime, payload


def _browser_live_turn_timeout_seconds(request: OperatorVoiceTurnRequest, settings: Settings) -> float | None:
    if request.source not in {"browser_speech_recognition", "browser_audio_capture"}:
        return None
    if request.camera_image_data_url and looks_like_visual_query(request.input_text):
        return float(settings.blink_browser_live_visual_turn_timeout_seconds)
    return float(settings.blink_browser_live_turn_timeout_seconds)


def _submit_operator_turn_with_timeout(
    *,
    operator_console: OperatorConsoleService,
    settings: Settings,
    request: OperatorVoiceTurnRequest,
) -> OperatorInteractionResult:
    timeout_seconds = _browser_live_turn_timeout_seconds(request, settings)
    if timeout_seconds is None:
        return operator_console.submit_text_turn(request)

    future = _BROWSER_LIVE_EXECUTOR.submit(operator_console.submit_text_turn, request)
    try:
        return future.result(timeout=timeout_seconds)
    except FuturesTimeoutError as exc:
        future.cancel()
        stall_classification = (
            "dialogue_or_visual_stall"
            if request.camera_image_data_url and looks_like_visual_query(request.input_text)
            else "server_handler_stall"
        )
        diagnostics = operator_console.capture_live_turn_timeout_artifact(
            request=request,
            timeout_seconds=timeout_seconds,
            stall_classification=stall_classification,
        )
        raise HTTPException(
            status_code=504,
            detail={
                "code": "browser_live_turn_timeout",
                "message": "Browser live turn timed out before the reply completed.",
                "timeout_seconds": timeout_seconds,
                "stall_classification": stall_classification,
                "artifact_path": diagnostics.timeout_artifact_path,
            },
        ) from exc


def _normalize_browser_audio_for_transcription(
    *,
    payload: bytes,
    mime_type: str,
    device_registry: DesktopDeviceRegistry,
) -> Path:
    ffmpeg_path = device_registry.microphone_input.ffmpeg_path
    if not ffmpeg_path:
        raise HTTPException(status_code=503, detail="browser_audio_ffmpeg_unavailable")

    input_suffix = _BROWSER_AUDIO_SUFFIXES.get(mime_type.lower(), ".webm")
    temp_dir = Path(tempfile.mkdtemp(prefix="blink-browser-audio-"))
    input_path = temp_dir / f"capture{input_suffix}"
    wav_path = temp_dir / "capture.wav"
    input_path.write_bytes(payload)

    completed = subprocess.run(
        [
            ffmpeg_path,
            "-loglevel",
            "error",
            "-i",
            str(input_path),
            "-ac",
            "1",
            "-ar",
            "16000",
            "-c:a",
            "pcm_s16le",
            "-y",
            str(wav_path),
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=20.0,
    )
    if completed.returncode != 0 or not wav_path.exists() or wav_path.stat().st_size == 0:
        detail = completed.stderr.strip() or completed.stdout.strip() or "browser_audio_transcode_failed"
        raise HTTPException(status_code=503, detail=detail)
    return wav_path


def create_app(
    *,
    settings: Settings | None = None,
    store_path: str | Path | None = None,
    orchestrator: BrainOrchestrator | None = None,
    demo_coordinator: DemoCoordinator | None = None,
    device_registry: DesktopDeviceRegistry | None = None,
    backend_router: BackendRouter | None = None,
) -> FastAPI:
    runtime_settings = apply_desktop_profile(settings or get_settings())
    resolved_backend_router = backend_router or BackendRouter(settings=runtime_settings)
    resolved_device_registry = device_registry or build_desktop_device_registry(runtime_settings)
    brain = orchestrator or BrainOrchestrator(
        settings=runtime_settings,
        store_path=store_path,
        backend_router=resolved_backend_router,
    )
    shift_report_store = ShiftReportStore(runtime_settings.shift_report_dir)
    coordinator = demo_coordinator or DemoCoordinator(
        orchestrator=brain,
        edge_gateway=build_default_embodiment_gateway(runtime_settings),
        report_dir=runtime_settings.demo_report_dir,
    )
    perception_service = PerceptionService(
        settings=runtime_settings,
        memory=brain.memory,
        event_handler=brain.handle_event,
        providers=resolved_backend_router.build_perception_providers(),
    )
    voice_manager = LiveVoiceRuntimeManager(
        settings=runtime_settings,
        device_registry=resolved_device_registry,
        backend_router=resolved_backend_router,
        macos_voice_name=runtime_settings.macos_tts_voice,
        macos_rate=runtime_settings.macos_tts_rate,
    )
    operator_console = OperatorConsoleService(
        settings=runtime_settings,
        orchestrator=brain,
        edge_gateway=coordinator.edge_gateway,
        demo_coordinator=coordinator,
        shift_report_store=shift_report_store,
        voice_manager=voice_manager,
        backend_router=resolved_backend_router,
        device_registry=resolved_device_registry,
        perception_service=perception_service,
        episode_exporter=build_exporter(
            settings=runtime_settings,
            orchestrator=brain,
            report_store=coordinator.report_store,
            episode_store=EpisodeStore(runtime_settings.episode_export_dir),
            edge_gateway=coordinator.edge_gateway,
        ),
    )
    auth_manager = OperatorAuthManager(runtime_settings)
    appliance_profile_store = ApplianceProfileStore(runtime_settings.blink_appliance_profile_file)
    operator_console.appliance_profile_store = appliance_profile_store
    operator_console.operator_auth_mode = auth_manager.auth_mode
    operator_console.operator_auth_token_source = auth_manager.token_source
    operator_console.operator_auth_runtime_file = str(auth_manager.runtime_file)
    performance_show_manager = PerformanceShowManager(
        operator_console=operator_console,
        report_dir=runtime_settings.performance_report_dir,
    )
    operator_console.performance_show_manager = performance_show_manager
    shift_runner = ShiftAutonomyRunner(settings=runtime_settings, operator_console=operator_console)
    operator_console.shift_runner = shift_runner

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        shift_runner.start()
        try:
            yield
        finally:
            shift_runner.stop()

    app = FastAPI(title=f"{runtime_settings.project_name} Brain API", lifespan=lifespan)
    app.state.orchestrator = brain
    app.state.demo_coordinator = coordinator
    app.state.perception_service = perception_service
    app.state.operator_console = operator_console
    app.state.operator_auth = auth_manager
    app.state.shift_runner = shift_runner
    app.state.shift_report_store = shift_report_store
    app.state.device_registry = resolved_device_registry
    app.state.backend_router = resolved_backend_router
    app.state.performance_show_manager = performance_show_manager

    static_dir = Path(__file__).resolve().parent / "static"
    login_page = static_dir / "login.html"
    setup_page = static_dir / "setup.html"
    companion_test_page = static_dir / "companion_test.html"
    presence_page = static_dir / "presence.html"
    performance_page = static_dir / "performance.html"
    app.mount("/console/static", StaticFiles(directory=static_dir), name="console-static")

    @app.middleware("http")
    async def operator_auth_middleware(request: Request, call_next):
        if auth_manager.requires_auth(request.url.path) and not auth_manager.is_authenticated(request):
            if request.url.path in {"/console", "/presence", "/performance", "/setup", "/companion-test"} and request.method.upper() == "GET":
                return FileResponse(login_page)
            return JSONResponse(status_code=401, content={"detail": "operator_auth_required"})
        return await call_next(request)

    @app.get("/", include_in_schema=False)
    def root() -> RedirectResponse:
        return RedirectResponse(url="/console")

    @app.get("/login", include_in_schema=False)
    def login() -> FileResponse:
        return FileResponse(login_page)

    @app.get("/console", include_in_schema=False)
    def console() -> FileResponse:
        if runtime_settings.blink_appliance_mode and not operator_console.get_appliance_status().setup_complete:
            return FileResponse(setup_page)
        return FileResponse(static_dir / "console.html")

    @app.get("/presence", include_in_schema=False)
    def presence() -> FileResponse:
        if runtime_settings.blink_appliance_mode and not operator_console.get_appliance_status().setup_complete:
            return FileResponse(setup_page)
        return FileResponse(presence_page)

    @app.get("/performance", include_in_schema=False)
    def performance() -> FileResponse:
        if runtime_settings.blink_appliance_mode and not operator_console.get_appliance_status().setup_complete:
            return FileResponse(setup_page)
        return FileResponse(performance_page)

    @app.get("/setup", include_in_schema=False)
    def setup() -> FileResponse:
        return FileResponse(setup_page)

    @app.get("/companion-test", include_in_schema=False)
    def companion_test() -> FileResponse:
        return FileResponse(companion_test_page)

    @app.get("/appliance/bootstrap/{token}", include_in_schema=False)
    def appliance_bootstrap_redirect(token: str) -> RedirectResponse:
        if runtime_settings.blink_appliance_mode:
            return RedirectResponse(url="/console")
        if not auth_manager.consume_bootstrap_token(token):
            raise HTTPException(status_code=401, detail="invalid_appliance_bootstrap_token")
        response = RedirectResponse(url="/console")
        auth_manager.set_login_cookie(response)
        return response

    @app.get("/health")
    def health() -> dict:
        backend_status = {
            item.kind.value: item
            for item in resolved_backend_router.runtime_statuses()
        }
        return {
            "ok": True,
            "service": "brain",
            "project_name": runtime_settings.project_name,
            "runtime_profile": runtime_settings.brain_runtime_profile,
            "deployment_target": runtime_settings.brain_deployment_target,
            "runtime_mode": runtime_settings.blink_runtime_mode,
            "model_profile": runtime_settings.blink_model_profile,
            "backend_profile": resolved_backend_router.resolved_backend_profile(),
            "voice_profile": runtime_settings.blink_voice_profile,
            "camera_source": runtime_settings.blink_camera_source,
            "microphone_device": runtime_settings.blink_mic_device,
            "body_driver_mode": runtime_settings.resolved_body_driver,
            "head_profile_path": runtime_settings.blink_head_profile,
            "dialogue_backend": backend_status["text_reasoning"].backend_id,
            "voice_backend": runtime_settings.brain_voice_backend,
            "perception_provider": backend_status["vision_analysis"].backend_id,
            "embedding_backend": backend_status["embeddings"].backend_id,
            "stt_backend": backend_status["speech_to_text"].backend_id,
            "tts_backend": backend_status["text_to_speech"].backend_id,
            "operator_auth_enabled": runtime_settings.operator_auth_enabled,
        }

    @app.get("/ready", response_model=ServiceReadinessResponse)
    def readiness() -> ServiceReadinessResponse:
        checks: list[ReadinessCheck] = []

        store_path = Path(runtime_settings.brain_store_path)
        store_ok = store_path.parent.exists()
        checks.append(
            ReadinessCheck(
                name="brain_store",
                ok=store_ok,
                status="ready" if store_ok else "blocked",
                detail=str(store_path),
                category="persistence",
                reason_code="brain_store_ready" if store_ok else "brain_store_unavailable",
                required_for=["process", "usable"],
            )
        )

        telemetry = coordinator.edge_gateway.get_telemetry()
        heartbeat = coordinator.edge_gateway.get_heartbeat()
        edge_ok = telemetry.transport_ok and heartbeat.transport_ok and coordinator.edge_gateway.transport_state().value == "healthy"
        checks.append(
            ReadinessCheck(
                name="edge_transport",
                ok=edge_ok,
                status="ready" if edge_ok else "degraded",
                detail=f"{coordinator.edge_gateway.transport_mode().value}:{coordinator.edge_gateway.transport_state().value}",
                category="edge",
                reason_code="edge_transport_ready" if edge_ok else "edge_transport_degraded",
                required_for=["best_experience"],
            )
        )
        body_state = telemetry.body_state
        body_driver_ready = True
        body_driver_detail = f"{runtime_settings.blink_runtime_mode.value}:{runtime_settings.resolved_body_driver.value}"
        if runtime_settings.resolved_body_driver == BodyDriverMode.SERIAL:
            if body_state is not None:
                body_driver_ready = bool(body_state.transport_healthy)
                body_driver_detail = (
                    f"{runtime_settings.blink_runtime_mode.value}:"
                    f"{runtime_settings.resolved_body_driver.value}:"
                    f"{body_state.transport_mode or 'unknown'}"
                )
                if body_state.transport_error:
                    body_driver_detail = f"{body_driver_detail}:{body_state.transport_error}"
            else:
                body_driver_ready = runtime_settings.blink_serial_transport != "live_serial"
        checks.append(
            ReadinessCheck(
                name="body_driver",
                ok=body_driver_ready,
                status="ready" if body_driver_ready else "degraded",
                detail=body_driver_detail,
                category="body",
                reason_code="body_driver_ready" if body_driver_ready else "body_driver_degraded",
                required_for=["best_experience"],
            )
        )

        route_decisions = {
            item.kind.value: item
            for item in resolved_backend_router.route_decisions()
        }
        for check_name, key in (
            ("dialogue_backend", "text_reasoning"),
            ("vision_backend", "vision_analysis"),
            ("embedding_backend", "embeddings"),
            ("stt_backend", "speech_to_text"),
            ("tts_backend", "text_to_speech"),
        ):
            decision = route_decisions[key]
            check_ok = decision.status.value != "unavailable"
            check_status = "ready" if decision.status.value in {"warm", "configured"} else ("degraded" if check_ok else "blocked")
            checks.append(
                ReadinessCheck(
                    name=check_name,
                    ok=check_ok,
                    status=check_status,
                    detail=f"{decision.backend_id}:{decision.status.value}:{decision.detail or '-'}",
                    category="backend",
                    reason_code=decision.status.value,
                    required_for=(
                        ["usable", "best_experience"]
                        if check_name == "dialogue_backend"
                        else ["best_experience"]
                    ),
                )
            )

        voice_mode = operator_console.default_live_voice_mode()
        voice_state = voice_manager.get_state(voice_mode)
        device_health = {
            item.kind.value: item
            for item in resolved_device_registry.describe(default_voice_mode=voice_mode)
        }
        microphone_device = device_health.get("microphone")
        speaker_device = device_health.get("speaker")
        voice_ok = True
        voice_status = "ready"
        voice_detail = voice_state.message or voice_state.status.value
        if voice_mode == VoiceRuntimeMode.DESKTOP_NATIVE:
            voice_ok = bool(
                microphone_device
                and microphone_device.available
                and speaker_device
                and speaker_device.available
            )
            voice_status = "ready" if voice_ok else "blocked"
            voice_detail = "desktop_native_ready" if voice_ok else "desktop_native_device_unavailable"
        elif voice_mode.value in {"macos_say", "browser_live_macos_say"} and not voice_state.audio_available:
            voice_ok = False
            voice_status = "blocked"
        elif voice_mode.value == "browser_live" or voice_mode.value == "browser_live_macos_say":
            voice_detail = "browser_permission_required"
        checks.append(
            ReadinessCheck(
                name="default_voice_mode",
                ok=voice_ok,
                status=voice_status,
                detail=f"{voice_mode.value}:{voice_detail}",
                category="voice",
                reason_code=voice_status,
                required_for=["usable"],
            )
        )

        for item in device_health.values():
            checks.append(
                ReadinessCheck(
                    name=f"{item.kind.value}_device",
                    ok=item.available or not item.required,
                    status="ready" if item.available else ("degraded" if not item.required else "blocked"),
                    detail=f"{item.backend}:{item.detail or item.state.value}",
                    category="device",
                    reason_code=item.reason_code,
                    required_for=["media"],
                )
            )

        checks.append(
            ReadinessCheck(
                name="operator_auth",
                ok=True,
                status="ready" if runtime_settings.operator_auth_enabled else "degraded",
                detail=auth_manager.token_source,
                category="auth",
                reason_code="operator_auth_enabled" if runtime_settings.operator_auth_enabled else "operator_auth_degraded",
                required_for=["best_experience"],
            )
        )

        return build_service_readiness_response(
            service="brain",
            runtime_profile=runtime_settings.brain_runtime_profile,
            checks=checks,
        )

    @app.get("/api/operator/auth/status", response_model=OperatorAuthStatus)
    def operator_auth_status(request: Request) -> OperatorAuthStatus:
        return auth_manager.status(authenticated=auth_manager.is_authenticated(request))

    @app.post("/api/operator/auth/login", response_model=OperatorAuthStatus)
    def operator_auth_login(request: OperatorAuthLoginRequest, response: Response) -> OperatorAuthStatus:
        if runtime_settings.blink_appliance_mode:
            return auth_manager.status(authenticated=True)
        if auth_manager.enabled and request.token != auth_manager.token:
            raise HTTPException(status_code=401, detail="invalid_operator_token")
        auth_manager.set_login_cookie(response)
        return auth_manager.status(authenticated=True)

    @app.post("/api/operator/auth/logout", response_model=OperatorAuthStatus)
    def operator_auth_logout(response: Response) -> OperatorAuthStatus:
        if runtime_settings.blink_appliance_mode:
            return auth_manager.status(authenticated=True)
        auth_manager.clear_login_cookie(response)
        return auth_manager.status(authenticated=False)

    @app.post("/api/appliance/bootstrap", response_model=ApplianceBootstrapResponse)
    def appliance_bootstrap() -> ApplianceBootstrapResponse:
        if not runtime_settings.blink_appliance_mode:
            raise HTTPException(status_code=404, detail="appliance_mode_disabled")
        host = runtime_settings.brain_host if runtime_settings.brain_host not in {"0.0.0.0", "::"} else "127.0.0.1"
        bootstrap_url, expires_at = auth_manager.issue_bootstrap_token(host=host, port=runtime_settings.brain_port)
        return ApplianceBootstrapResponse(bootstrap_url=bootstrap_url, expires_at=expires_at)

    @app.get("/api/appliance/status", response_model=ApplianceStatus)
    def appliance_status() -> ApplianceStatus:
        return operator_console.get_appliance_status()

    @app.get("/api/appliance/devices", response_model=ApplianceDeviceCatalog)
    def appliance_devices() -> ApplianceDeviceCatalog:
        return operator_console.get_appliance_devices()

    @app.post("/api/appliance/profile", response_model=ApplianceStatus)
    def appliance_profile(request: ApplianceProfileRequest) -> ApplianceStatus:
        return operator_console.save_appliance_profile(request)

    @app.post("/api/reset", response_model=ResetResult)
    def reset(request: BrainResetRequest | None = None) -> ResetResult:
        return coordinator.reset_system(request)

    @app.post("/api/sessions", response_model=SessionRecord)
    def create_session(request: SessionCreateRequest) -> SessionRecord:
        return brain.create_session(request)

    @app.get("/api/sessions", response_model=SessionListResponse)
    def list_sessions() -> SessionListResponse:
        return brain.list_sessions()

    @app.get("/api/sessions/{session_id}", response_model=SessionRecord)
    def get_session(session_id: str) -> SessionRecord:
        session = brain.get_session(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="session_not_found")
        return session

    @app.post("/api/sessions/{session_id}/operator-notes", response_model=SessionRecord)
    def add_operator_note(session_id: str, request: OperatorNoteRequest) -> SessionRecord:
        try:
            return brain.add_operator_note(session_id, request)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="session_not_found") from exc

    @app.post("/api/sessions/{session_id}/response-mode", response_model=SessionRecord)
    def set_response_mode(session_id: str, request: SessionResponseModeRequest) -> SessionRecord:
        try:
            return brain.set_response_mode(session_id, request)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="session_not_found") from exc

    @app.post("/api/events", response_model=CommandBatch)
    def ingest_event(event: RobotEvent) -> CommandBatch:
        return brain.handle_event(event)

    @app.post("/api/voice/turn", response_model=VoiceTurnResult)
    def voice_turn(request: VoiceTurnRequest) -> VoiceTurnResult:
        return brain.handle_voice_turn(request)

    @app.get("/api/world-state", response_model=WorldState)
    def world_state() -> WorldState:
        return brain.get_world_state()

    @app.get("/api/world-model", response_model=EmbodiedWorldModel)
    def world_model() -> EmbodiedWorldModel:
        return brain.get_world_model()

    @app.get("/api/shift-state", response_model=ShiftSupervisorSnapshot)
    def shift_state() -> ShiftSupervisorSnapshot:
        return brain.get_shift_supervisor()

    @app.get("/api/shift-transitions", response_model=ShiftTransitionListResponse)
    def shift_transitions(session_id: str | None = None, limit: int = 25) -> ShiftTransitionListResponse:
        return brain.list_shift_transitions(session_id=session_id, limit=limit)

    @app.get("/api/executive/decisions", response_model=ExecutiveDecisionListResponse)
    def list_executive_decisions(
        session_id: str | None = None,
        limit: int = 25,
    ) -> ExecutiveDecisionListResponse:
        return brain.list_executive_decisions(session_id=session_id, limit=limit)

    @app.get("/api/operator/snapshot", response_model=OperatorConsoleSnapshot)
    def operator_snapshot(
        session_id: str | None = None,
        voice_mode: VoiceRuntimeMode | None = None,
        trace_limit: int = 25,
    ) -> OperatorConsoleSnapshot:
        return operator_console.get_snapshot(session_id=session_id, voice_mode=voice_mode, trace_limit=trace_limit)

    @app.get("/api/operator/presence", response_model=CharacterPresenceSurfaceSnapshot)
    def operator_presence(session_id: str | None = None) -> CharacterPresenceSurfaceSnapshot:
        return operator_console.get_character_presence_surface(session_id=session_id)

    @app.get("/api/operator/performance-shows", response_model=PerformanceShowCatalogResponse)
    def operator_performance_show_catalog() -> PerformanceShowCatalogResponse:
        return operator_console.list_performance_shows()

    @app.post("/api/operator/performance-shows/{show_name}/run", response_model=PerformanceRunResult)
    def operator_run_performance_show(
        show_name: str,
        request: PerformanceRunRequest | None = None,
    ) -> PerformanceRunResult:
        try:
            return operator_console.run_performance_show(show_name, request)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="performance_show_not_found") from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.get("/api/operator/performance-shows/runs/{run_id}", response_model=PerformanceRunResult)
    def operator_get_performance_run(run_id: str) -> PerformanceRunResult:
        run = operator_console.get_performance_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="performance_run_not_found")
        return run

    @app.post("/api/operator/performance-shows/runs/{run_id}/cancel", response_model=PerformanceRunResult)
    def operator_cancel_performance_run(run_id: str) -> PerformanceRunResult:
        try:
            return operator_console.cancel_performance_run(run_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="performance_run_not_found") from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.get("/api/operator/runs", response_model=RunListResponse)
    def operator_list_runs(session_id: str | None = None, limit: int = 50) -> RunListResponse:
        return operator_console.list_runs(session_id=session_id, limit=limit)

    @app.get("/api/operator/runs/{run_id}", response_model=RunRecord)
    def operator_get_run(run_id: str) -> RunRecord:
        run = operator_console.get_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="run_not_found")
        return run

    @app.get("/api/operator/runs/{run_id}/checkpoints", response_model=CheckpointListResponse)
    def operator_get_run_checkpoints(run_id: str, limit: int = 100) -> CheckpointListResponse:
        return operator_console.list_run_checkpoints(run_id, limit=limit)

    @app.post("/api/operator/checkpoints/{checkpoint_id}/resume", response_model=RunRecord)
    def operator_resume_checkpoint(checkpoint_id: str) -> RunRecord:
        try:
            return operator_console.resume_checkpoint(checkpoint_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="checkpoint_not_found") from exc

    @app.post("/api/operator/runs/{run_id}/pause", response_model=RunRecord)
    def operator_pause_run(run_id: str, reason: str = "operator_pause") -> RunRecord:
        try:
            return operator_console.pause_run(run_id, reason=reason)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="run_not_found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/api/operator/runs/{run_id}/resume", response_model=RunRecord)
    def operator_resume_run(run_id: str, note: str = "operator_resume") -> RunRecord:
        try:
            return operator_console.resume_run(run_id, note=note)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="run_not_found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/api/operator/runs/{run_id}/abort", response_model=RunRecord)
    def operator_abort_run(run_id: str, reason: str = "operator_abort") -> RunRecord:
        try:
            return operator_console.abort_run(run_id, reason=reason)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="run_not_found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.get("/api/operator/runs/{run_id}/export", response_model=RunExportResponse)
    def operator_export_run(run_id: str) -> RunExportResponse:
        try:
            return operator_console.export_run(run_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="run_not_found") from exc

    @app.post("/api/operator/runs/{run_id}/replay", response_model=RunRecord)
    def operator_replay_run(run_id: str) -> RunRecord:
        try:
            return operator_console.replay_run(run_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="run_not_found") from exc

    @app.get("/api/operator/runs/{run_id}/teacher", response_model=TeacherAnnotationListResponse)
    def operator_get_run_teacher_annotations(run_id: str) -> TeacherAnnotationListResponse:
        try:
            return operator_console.get_run_teacher_annotations(run_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="run_not_found") from exc

    @app.post("/api/operator/runs/{run_id}/teacher", response_model=TeacherAnnotationRecord)
    def operator_add_run_teacher_annotation(
        run_id: str,
        request: TeacherReviewRequest,
    ) -> TeacherAnnotationRecord:
        try:
            return operator_console.add_run_teacher_annotation(run_id, request)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="run_not_found") from exc

    @app.post("/api/operator/text-turn", response_model=OperatorInteractionResult)
    def operator_text_turn(request: OperatorVoiceTurnRequest) -> OperatorInteractionResult:
        return _submit_operator_turn_with_timeout(
            operator_console=operator_console,
            settings=settings,
            request=request,
        )

    @app.post("/api/operator/browser-audio-turn", response_model=BrowserAudioTurnResult)
    def operator_browser_audio_turn(request: BrowserAudioTurnRequest) -> BrowserAudioTurnResult:
        resolved_mime, payload = _decode_browser_audio_data_url(
            request.audio_data_url,
            mime_type=request.mime_type,
        )
        wav_path = _normalize_browser_audio_for_transcription(
            payload=payload,
            mime_type=resolved_mime,
            device_registry=resolved_device_registry,
        )
        try:
            transcription_started = perf_counter()
            transcript = resolved_device_registry.transcribe_local_audio_file(wav_path)
            stt_latency_ms = round((perf_counter() - transcription_started) * 1000.0, 2)
        except Exception as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        finally:
            shutil.rmtree(wav_path.parent, ignore_errors=True)

        transcript_text = str(transcript.get("transcript_text") or "").strip()
        if not transcript_text:
            raise HTTPException(status_code=503, detail="browser_audio_empty_transcript")

        input_metadata = dict(request.input_metadata)
        input_metadata.update(
            {
                "capture_mode": "browser_microphone",
                "transcription_backend": transcript.get("transcription_backend") or "local_stt",
                "audio_mime_type": resolved_mime,
                "stt_latency_ms": stt_latency_ms,
            }
        )
        voice_turn_request = OperatorVoiceTurnRequest(
            session_id=request.session_id,
            user_id=request.user_id,
            input_text=transcript_text,
            response_mode=request.response_mode,
            voice_mode=request.voice_mode,
            speak_reply=request.speak_reply,
            source=request.source,
            input_metadata=input_metadata,
            camera_image_data_url=request.camera_image_data_url,
            camera_source_frame=request.camera_source_frame,
            camera_provider_mode=request.camera_provider_mode,
        )
        interaction = _submit_operator_turn_with_timeout(
            operator_console=operator_console,
            settings=settings,
            request=voice_turn_request,
        )
        return BrowserAudioTurnResult(
            interaction=interaction,
            transcript_text=transcript_text,
            transcription_backend=str(transcript.get("transcription_backend") or ""),
            browser_device_label=(
                str(input_metadata.get("browser_device_label"))
                if input_metadata.get("browser_device_label") is not None
                else None
            ),
            audio_mime_type=resolved_mime,
        )

    @app.post("/api/operator/inject-event", response_model=OperatorInteractionResult)
    def operator_inject_event(request: SimulatedSensorEventRequest) -> OperatorInteractionResult:
        return operator_console.inject_event(request)

    @app.post("/api/operator/safe-idle", response_model=OperatorInteractionResult)
    def operator_force_safe_idle(
        session_id: str | None = None,
        reason: str = "operator_override",
    ) -> OperatorInteractionResult:
        return operator_console.force_safe_idle(session_id=session_id, reason=reason)

    @app.get("/api/operator/action-plane/status", response_model=ActionPlaneStatus)
    def operator_action_plane_status() -> ActionPlaneStatus:
        try:
            return operator_console.get_action_plane_status()
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.get("/api/operator/action-plane/overview", response_model=ActionCenterOverviewRecord)
    def operator_action_plane_overview(session_id: str | None = None) -> ActionCenterOverviewRecord:
        try:
            return operator_console.get_action_plane_overview(session_id=session_id)
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.get("/api/operator/action-plane/connectors", response_model=ConnectorCatalogResponse)
    def operator_action_plane_connectors() -> ConnectorCatalogResponse:
        try:
            return operator_console.list_action_plane_connectors()
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.get("/api/operator/action-plane/browser/status", response_model=BrowserRuntimeStatusRecord)
    def operator_action_plane_browser_status(session_id: str | None = None) -> BrowserRuntimeStatusRecord:
        try:
            return operator_console.get_action_plane_browser_status(session_id=session_id)
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.post("/api/operator/action-plane/browser/task", response_model=BrowserTaskToolOutput)
    def operator_action_plane_browser_task(request: BrowserActionTaskRequest) -> BrowserTaskToolOutput:
        try:
            return operator_console.run_action_plane_browser_task(request)
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.get("/api/operator/action-plane/approvals", response_model=ActionApprovalListResponse)
    def operator_action_plane_approvals() -> ActionApprovalListResponse:
        try:
            return operator_console.list_action_plane_approvals()
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.post("/api/operator/action-plane/approvals/{action_id}/approve", response_model=ActionApprovalResolutionRecord)
    def operator_action_plane_approve(
        action_id: str,
        request: ActionApprovalResolutionRequest | None = None,
    ) -> ActionApprovalResolutionRecord:
        try:
            resolved = request or ActionApprovalResolutionRequest(action_id=action_id)
            if resolved.action_id != action_id:
                resolved = resolved.model_copy(update={"action_id": action_id})
            return operator_console.approve_action_plane_action(resolved)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.post("/api/operator/action-plane/approvals/{action_id}/reject", response_model=ActionApprovalResolutionRecord)
    def operator_action_plane_reject(
        action_id: str,
        request: ActionApprovalResolutionRequest | None = None,
    ) -> ActionApprovalResolutionRecord:
        try:
            resolved = request or ActionApprovalResolutionRequest(action_id=action_id)
            if resolved.action_id != action_id:
                resolved = resolved.model_copy(update={"action_id": action_id})
            return operator_console.reject_action_plane_action(resolved)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.get("/api/operator/action-plane/history", response_model=ActionExecutionListResponse)
    def operator_action_plane_history(limit: int = 50) -> ActionExecutionListResponse:
        try:
            return operator_console.list_action_plane_history(limit=limit)
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.get("/api/operator/action-plane/bundles", response_model=ActionBundleListResponse)
    def operator_action_plane_bundles(session_id: str | None = None, limit: int = 50) -> ActionBundleListResponse:
        try:
            return operator_console.list_action_plane_bundles(session_id=session_id, limit=limit)
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.get("/api/operator/action-plane/bundles/{bundle_id}", response_model=ActionBundleDetailRecord)
    def operator_action_plane_bundle(bundle_id: str) -> ActionBundleDetailRecord:
        try:
            bundle = operator_console.get_action_plane_bundle(bundle_id)
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        if bundle is None:
            raise HTTPException(status_code=404, detail="action_bundle_not_found")
        return bundle

    @app.get("/api/operator/action-plane/workflows", response_model=WorkflowCatalogResponse)
    def operator_action_plane_workflows() -> WorkflowCatalogResponse:
        try:
            return operator_console.list_action_plane_workflows()
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.get("/api/operator/action-plane/workflows/runs", response_model=WorkflowRunListResponse)
    def operator_action_plane_workflow_runs(session_id: str | None = None, limit: int = 50) -> WorkflowRunListResponse:
        try:
            return operator_console.list_action_plane_workflow_runs(session_id=session_id, limit=limit)
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.get("/api/operator/action-plane/workflows/runs/{workflow_run_id}", response_model=WorkflowRunRecord)
    def operator_action_plane_workflow_run(workflow_run_id: str) -> WorkflowRunRecord:
        try:
            run = operator_console.get_action_plane_workflow_run(workflow_run_id)
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        if run is None:
            raise HTTPException(status_code=404, detail="workflow_run_not_found")
        return run

    @app.post("/api/operator/action-plane/workflows/start", response_model=WorkflowRunActionResponseRecord)
    def operator_action_plane_start_workflow(request: WorkflowStartRequestRecord) -> WorkflowRunActionResponseRecord:
        try:
            return operator_console.start_action_plane_workflow(request)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.post("/api/operator/action-plane/workflows/runs/{workflow_run_id}/resume", response_model=WorkflowRunActionResponseRecord)
    def operator_action_plane_resume_workflow(
        workflow_run_id: str,
        request: WorkflowRunActionRequestRecord | None = None,
    ) -> WorkflowRunActionResponseRecord:
        try:
            return operator_console.resume_action_plane_workflow(
                workflow_run_id,
                request or WorkflowRunActionRequestRecord(),
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.post("/api/operator/action-plane/workflows/runs/{workflow_run_id}/retry", response_model=WorkflowRunActionResponseRecord)
    def operator_action_plane_retry_workflow(
        workflow_run_id: str,
        request: WorkflowRunActionRequestRecord | None = None,
    ) -> WorkflowRunActionResponseRecord:
        try:
            return operator_console.retry_action_plane_workflow(
                workflow_run_id,
                request or WorkflowRunActionRequestRecord(),
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.post("/api/operator/action-plane/workflows/runs/{workflow_run_id}/pause", response_model=WorkflowRunActionResponseRecord)
    def operator_action_plane_pause_workflow(
        workflow_run_id: str,
        request: WorkflowRunActionRequestRecord | None = None,
    ) -> WorkflowRunActionResponseRecord:
        try:
            return operator_console.pause_action_plane_workflow(
                workflow_run_id,
                request or WorkflowRunActionRequestRecord(),
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.post("/api/operator/action-plane/replay", response_model=ActionExecutionRecord)
    def operator_action_plane_replay(request: ActionReplayRequestRecord) -> ActionExecutionRecord:
        try:
            return operator_console.replay_action_plane_action(request)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.post("/api/operator/action-plane/replays", response_model=ActionReplayRecord)
    def operator_action_plane_bundle_replay(request: ActionReplayRequestRecord) -> ActionReplayRecord:
        try:
            return operator_console.replay_action_plane_bundle(request)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.post("/api/operator/action-plane/bundles/{bundle_id}/teacher-review", response_model=TeacherAnnotationRecord)
    def operator_action_plane_bundle_teacher_review(
        bundle_id: str,
        request: TeacherReviewRequest,
    ) -> TeacherAnnotationRecord:
        try:
            return operator_console.add_action_plane_bundle_teacher_annotation(bundle_id, request)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.get("/api/operator/body/status", response_model=BodyActionResult)
    def operator_body_status() -> BodyActionResult:
        return operator_console.get_body_status()

    @app.post("/api/operator/body/connect", response_model=BodyActionResult)
    def operator_body_connect(request: BodyConnectRequest) -> BodyActionResult:
        return operator_console.connect_body(request)

    @app.post("/api/operator/body/disconnect", response_model=BodyActionResult)
    def operator_body_disconnect() -> BodyActionResult:
        return operator_console.disconnect_body()

    @app.post("/api/operator/body/scan", response_model=BodyActionResult)
    def operator_body_scan(request: BodyIdsRequest | None = None) -> BodyActionResult:
        return operator_console.scan_body(request)

    @app.post("/api/operator/body/ping", response_model=BodyActionResult)
    def operator_body_ping(request: BodyIdsRequest | None = None) -> BodyActionResult:
        return operator_console.ping_body(request)

    @app.post("/api/operator/body/read-health", response_model=BodyActionResult)
    def operator_body_read_health(request: BodyIdsRequest | None = None) -> BodyActionResult:
        return operator_console.read_body_health(request)

    @app.post("/api/operator/body/arm", response_model=BodyActionResult)
    def operator_body_arm(request: BodyArmRequest | None = None) -> BodyActionResult:
        return operator_console.arm_body_motion(request or BodyArmRequest())

    @app.post("/api/operator/body/disarm", response_model=BodyActionResult)
    def operator_body_disarm() -> BodyActionResult:
        return operator_console.disarm_body_motion()

    @app.post("/api/operator/body/write-neutral", response_model=BodyActionResult)
    def operator_body_write_neutral() -> BodyActionResult:
        return operator_console.write_body_neutral()

    @app.get("/api/operator/body/servo-lab/catalog", response_model=BodyActionResult)
    def operator_body_servo_lab_catalog() -> BodyActionResult:
        return operator_console.get_body_servo_lab_catalog()

    @app.post("/api/operator/body/servo-lab/readback", response_model=BodyActionResult)
    def operator_body_servo_lab_readback(request: BodyServoLabReadbackRequest | None = None) -> BodyActionResult:
        return operator_console.read_body_servo_lab(request or BodyServoLabReadbackRequest())

    @app.post("/api/operator/body/servo-lab/move", response_model=BodyActionResult)
    def operator_body_servo_lab_move(request: BodyServoLabMoveRequest) -> BodyActionResult:
        return operator_console.move_body_servo_lab(request)

    @app.post("/api/operator/body/servo-lab/sweep", response_model=BodyActionResult)
    def operator_body_servo_lab_sweep(request: BodyServoLabSweepRequest) -> BodyActionResult:
        return operator_console.sweep_body_servo_lab(request)

    @app.post("/api/operator/body/servo-lab/save-calibration", response_model=BodyActionResult)
    def operator_body_servo_lab_save_calibration(request: BodyServoLabSaveCalibrationRequest) -> BodyActionResult:
        return operator_console.save_body_servo_lab_calibration(request)

    @app.get("/api/operator/body/semantic-library", response_model=BodyActionResult)
    def operator_body_semantic_library(smoke_safe_only: bool = False) -> BodyActionResult:
        return operator_console.get_body_semantic_library(smoke_safe_only=smoke_safe_only)

    @app.get("/api/operator/body/expression-catalog", response_model=BodyActionResult)
    def operator_body_expression_catalog() -> BodyActionResult:
        return operator_console.get_body_expression_catalog()

    @app.post("/api/operator/body/semantic-smoke", response_model=BodyActionResult)
    def operator_body_semantic_smoke(request: BodySemanticSmokeRequest | None = None) -> BodyActionResult:
        return operator_console.run_body_semantic_smoke(request or BodySemanticSmokeRequest())

    @app.post("/api/operator/body/primitive-sequence", response_model=BodyActionResult)
    def operator_body_primitive_sequence(request: BodyPrimitiveSequenceRequest) -> BodyActionResult:
        return operator_console.run_body_primitive_sequence(request)

    @app.post("/api/operator/body/expressive-motif", response_model=BodyActionResult)
    def operator_body_expressive_motif(request: BodyExpressiveSequenceRequest) -> BodyActionResult:
        return operator_console.run_body_expressive_motif(request)

    @app.post("/api/operator/body/staged-sequence", response_model=BodyActionResult)
    def operator_body_staged_sequence(request: BodyStagedSequenceRequest) -> BodyActionResult:
        return operator_console.run_body_staged_sequence(request)

    @app.post("/api/operator/body/teacher-review", response_model=BodyActionResult)
    def operator_body_teacher_review(request: BodyTeacherReviewRequest) -> BodyActionResult:
        return operator_console.record_body_teacher_review(request)

    @app.post("/api/operator/shift/tick", response_model=OperatorInteractionResult)
    def operator_shift_tick(request: ShiftAutonomyTickRequest | None = None) -> OperatorInteractionResult:
        return operator_console.run_shift_tick(request)

    @app.post("/api/operator/shift/override", response_model=ShiftSupervisorSnapshot)
    def operator_shift_override(
        request: ShiftOverrideRequest,
        session_id: str | None = None,
    ) -> ShiftSupervisorSnapshot:
        return operator_console.set_shift_override(request, session_id=session_id)

    @app.get("/api/operator/incidents", response_model=IncidentListResponse)
    def operator_list_incidents(
        scope: IncidentListScope = IncidentListScope.ALL,
        session_id: str | None = None,
        limit: int = 50,
    ) -> IncidentListResponse:
        return operator_console.list_incidents(scope=scope, session_id=session_id, limit=limit)

    @app.get("/api/operator/incidents/{ticket_id}", response_model=IncidentTicketRecord)
    def operator_get_incident(ticket_id: str) -> IncidentTicketRecord:
        ticket = operator_console.get_incident(ticket_id)
        if ticket is None:
            raise HTTPException(status_code=404, detail="incident_not_found")
        return ticket

    @app.post("/api/operator/incidents/{ticket_id}/acknowledge", response_model=IncidentTicketRecord)
    def operator_acknowledge_incident(ticket_id: str, request: IncidentAcknowledgeRequest) -> IncidentTicketRecord:
        try:
            return operator_console.acknowledge_incident(ticket_id, request)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="incident_not_found") from exc

    @app.post("/api/operator/incidents/{ticket_id}/assign", response_model=IncidentTicketRecord)
    def operator_assign_incident(ticket_id: str, request: IncidentAssignRequest) -> IncidentTicketRecord:
        try:
            return operator_console.assign_incident(ticket_id, request)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="incident_not_found") from exc

    @app.post("/api/operator/incidents/{ticket_id}/notes", response_model=IncidentTicketRecord)
    def operator_add_incident_note(ticket_id: str, request: IncidentNoteRequest) -> IncidentTicketRecord:
        try:
            return operator_console.add_incident_note(ticket_id, request)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="incident_not_found") from exc

    @app.post("/api/operator/incidents/{ticket_id}/resolve", response_model=IncidentTicketRecord)
    def operator_resolve_incident(ticket_id: str, request: IncidentResolveRequest) -> IncidentTicketRecord:
        try:
            return operator_console.resolve_incident(ticket_id, request)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="incident_not_found") from exc

    @app.post("/api/operator/perception/snapshots", response_model=PerceptionSubmissionResult)
    def operator_submit_perception_snapshot(request: PerceptionSnapshotSubmitRequest) -> PerceptionSubmissionResult:
        return operator_console.submit_perception_snapshot(request)

    @app.post("/api/operator/perception/replay", response_model=PerceptionReplayResult)
    def operator_replay_perception_fixture(request: PerceptionReplayRequest) -> PerceptionReplayResult:
        return operator_console.replay_perception_fixture(request)

    @app.get("/api/operator/perception/latest", response_model=PerceptionSnapshotRecord | None)
    def operator_get_latest_perception(session_id: str | None = None) -> PerceptionSnapshotRecord | None:
        return perception_service.get_latest_snapshot(session_id=session_id)

    @app.get("/api/operator/perception/history", response_model=PerceptionHistoryResponse)
    def operator_get_perception_history(session_id: str | None = None, limit: int = 20) -> PerceptionHistoryResponse:
        return perception_service.list_history(session_id=session_id, limit=limit)

    @app.get("/api/operator/perception/fixtures", response_model=PerceptionFixtureCatalogResponse)
    def operator_list_perception_fixtures() -> PerceptionFixtureCatalogResponse:
        return perception_service.list_fixtures()

    @app.post("/api/operator/voice/cancel", response_model=VoiceCancelResult)
    def operator_cancel_voice(
        session_id: str | None = None,
        voice_mode: VoiceRuntimeMode | None = None,
    ) -> VoiceCancelResult:
        return operator_console.cancel_voice(session_id=session_id, voice_mode=voice_mode)

    @app.post("/api/operator/voice/state", response_model=SpeechOutputResult)
    def operator_update_voice_state(request: LiveVoiceStateUpdateRequest) -> SpeechOutputResult:
        return operator_console.update_live_voice_state(request, session_id=request.session_id)

    @app.get("/api/operator/investor-scenes", response_model=InvestorSceneCatalogResponse)
    def operator_list_investor_scenes() -> InvestorSceneCatalogResponse:
        return operator_console.list_investor_scenes()

    @app.post("/api/operator/investor-scenes/{scene_name}/run", response_model=InvestorSceneRunResult)
    def operator_run_investor_scene(
        scene_name: str,
        request: InvestorSceneRunRequest | None = None,
    ) -> InvestorSceneRunResult:
        try:
            return operator_console.run_investor_scene(scene_name, request)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="scene_not_found") from exc

    @app.get("/api/operator/memory/profile/{user_id}", response_model=UserMemoryRecord | None)
    def operator_get_profile_memory(user_id: str) -> UserMemoryRecord | None:
        return operator_console.get_profile_memory(user_id)

    @app.get("/api/operator/memory/episodic", response_model=EpisodicMemoryListResponse)
    def operator_list_episodic_memory(
        session_id: str | None = None,
        user_id: str | None = None,
        limit: int = 50,
    ) -> EpisodicMemoryListResponse:
        return operator_console.list_episodic_memory(session_id=session_id, user_id=user_id, limit=limit)

    @app.get("/api/operator/memory/semantic", response_model=SemanticMemoryListResponse)
    def operator_list_semantic_memory(
        session_id: str | None = None,
        user_id: str | None = None,
        limit: int = 100,
    ) -> SemanticMemoryListResponse:
        return operator_console.list_semantic_memory(session_id=session_id, user_id=user_id, limit=limit)

    @app.get("/api/operator/memory/retrievals", response_model=MemoryRetrievalListResponse)
    def operator_list_memory_retrievals(
        session_id: str | None = None,
        user_id: str | None = None,
        trace_id: str | None = None,
        run_id: str | None = None,
        limit: int = 100,
    ) -> MemoryRetrievalListResponse:
        return operator_console.list_memory_retrievals(
            session_id=session_id,
            user_id=user_id,
            trace_id=trace_id,
            run_id=run_id,
            limit=limit,
        )

    @app.get("/api/operator/memory/review-debt", response_model=MemoryReviewDebtSummary)
    def operator_memory_review_debt() -> MemoryReviewDebtSummary:
        return operator_console.memory_review_debt_summary()

    @app.post("/api/operator/memory/review", response_model=MemoryReviewRecord)
    def operator_review_memory(request: MemoryReviewRequest) -> MemoryReviewRecord:
        return operator_console.review_memory(request)

    @app.post("/api/operator/memory/correct", response_model=MemoryReviewRecord)
    def operator_correct_memory(request: MemoryReviewRequest) -> MemoryReviewRecord:
        try:
            return operator_console.correct_memory(request)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="memory_not_found") from exc

    @app.post("/api/operator/memory/delete", response_model=MemoryReviewRecord)
    def operator_delete_memory(request: MemoryReviewRequest) -> MemoryReviewRecord:
        try:
            return operator_console.delete_memory(request)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="memory_not_found") from exc

    @app.get("/api/operator/episodes", response_model=EpisodeListResponseV2)
    def operator_list_episodes() -> EpisodeListResponseV2:
        return operator_console.list_episodes()

    @app.get("/api/operator/episodes/{episode_id}", response_model=EpisodeRecordV2)
    def operator_get_episode(episode_id: str) -> EpisodeRecordV2:
        episode = operator_console.get_episode(episode_id)
        if episode is None:
            raise HTTPException(status_code=404, detail="episode_not_found")
        return episode

    @app.get("/api/operator/episodes/{episode_id}/teacher", response_model=TeacherAnnotationListResponse)
    def operator_get_episode_teacher_annotations(episode_id: str) -> TeacherAnnotationListResponse:
        try:
            return operator_console.get_episode_teacher_annotations(episode_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="episode_not_found") from exc

    @app.post("/api/operator/episodes/{episode_id}/teacher", response_model=TeacherAnnotationRecord)
    def operator_add_episode_teacher_annotation(
        episode_id: str,
        request: TeacherReviewRequest,
    ) -> TeacherAnnotationRecord:
        try:
            return operator_console.add_episode_teacher_annotation(episode_id, request)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="episode_not_found") from exc

    @app.post("/api/operator/traces/{trace_id}/teacher/review", response_model=TeacherAnnotationRecord)
    def operator_add_trace_teacher_annotation(
        trace_id: str,
        request: TeacherReviewRequest,
    ) -> TeacherAnnotationRecord:
        try:
            return operator_console.add_trace_teacher_annotation(trace_id, request)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="trace_not_found") from exc

    @app.get("/api/operator/benchmarks", response_model=BenchmarkCatalogResponse)
    def operator_list_benchmarks() -> BenchmarkCatalogResponse:
        return operator_console.list_benchmarks()

    @app.post("/api/operator/benchmarks/run", response_model=BenchmarkRunRecord)
    def operator_run_benchmarks(request: BenchmarkRunRequest) -> BenchmarkRunRecord:
        try:
            return operator_console.run_benchmarks(request)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="episode_not_found") from exc

    @app.get("/api/operator/benchmarks/evidence", response_model=BenchmarkEvidencePackListResponse)
    def operator_list_benchmark_evidence_packs() -> BenchmarkEvidencePackListResponse:
        return operator_console.list_benchmark_evidence_packs()

    @app.get("/api/operator/benchmarks/evidence/{pack_id}", response_model=BenchmarkEvidencePackV1)
    def operator_get_benchmark_evidence_pack(pack_id: str) -> BenchmarkEvidencePackV1:
        pack = operator_console.get_benchmark_evidence_pack(pack_id)
        if pack is None:
            raise HTTPException(status_code=404, detail="benchmark_evidence_pack_not_found")
        return pack

    @app.get("/api/operator/planners", response_model=PlannerCatalogResponse)
    def operator_list_planners() -> PlannerCatalogResponse:
        return operator_console.list_planners()

    @app.post("/api/operator/replays/episode", response_model=PlannerReplayRecord)
    def operator_replay_episode(request: PlannerReplayRequest) -> PlannerReplayRecord:
        try:
            return operator_console.replay_episode(request)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="episode_or_planner_not_found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/operator/replays/{replay_id}", response_model=PlannerReplayRecord)
    def operator_get_replay(replay_id: str) -> PlannerReplayRecord:
        replay = operator_console.get_replay(replay_id)
        if replay is None:
            raise HTTPException(status_code=404, detail="replay_not_found")
        return replay

    @app.post("/api/operator/episodes/{episode_id}/export-research", response_model=ResearchBundleManifest)
    def operator_export_research_bundle(
        episode_id: str,
        request: ResearchExportRequest | None = None,
    ) -> ResearchBundleManifest:
        try:
            return operator_console.export_research_bundle(episode_id, request)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="episode_not_found") from exc

    @app.get("/api/operator/datasets", response_model=DatasetManifestListResponse)
    def operator_list_dataset_manifests() -> DatasetManifestListResponse:
        return operator_console.list_dataset_manifests()

    @app.get("/api/operator/datasets/{dataset_id}", response_model=DatasetManifestV1)
    def operator_get_dataset_manifest(dataset_id: str) -> DatasetManifestV1:
        dataset = operator_console.get_dataset_manifest(dataset_id)
        if dataset is None:
            raise HTTPException(status_code=404, detail="dataset_not_found")
        return dataset

    @app.post("/api/operator/datasets/export", response_model=DatasetManifestV1)
    def operator_export_dataset_manifest(request: DatasetExportRequest) -> DatasetManifestV1:
        try:
            return operator_console.export_dataset_manifest(request)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="episode_not_found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/api/operator/episodes/export-session", response_model=EpisodeRecordV2)
    def operator_export_session_episode(request: EpisodeExportSessionRequest) -> EpisodeRecordV2:
        try:
            return operator_console.export_session_episode(request)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="session_not_found") from exc

    @app.post("/api/operator/episodes/export-demo-run", response_model=EpisodeRecordV2)
    def operator_export_demo_run_episode(request: EpisodeExportRunRequest) -> EpisodeRecordV2:
        try:
            return operator_console.export_demo_run_episode(request)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="demo_run_not_found") from exc

    @app.post("/api/operator/episodes/export-shift-report", response_model=EpisodeRecordV2)
    def operator_export_shift_report_episode(request: EpisodeExportShiftReportRequest) -> EpisodeRecordV2:
        try:
            return operator_console.export_shift_report_episode(request)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="shift_report_not_found") from exc

    @app.get("/api/memory")
    def get_memory() -> dict:
        return brain.get_memory_snapshot()

    @app.get("/api/scenarios", response_model=ScenarioCatalogResponse)
    def list_scenarios() -> ScenarioCatalogResponse:
        return brain.list_scenarios()

    @app.post("/api/scenarios/{scenario_name}/replay", response_model=ScenarioReplayResult)
    def replay_scenario(scenario_name: str, request: ScenarioReplayRequest | None = None) -> ScenarioReplayResult:
        try:
            return brain.replay_scenario(scenario_name, request)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="scenario_not_found") from exc

    @app.post("/api/demo-runs", response_model=DemoRunRecord)
    def create_demo_run(request: DemoRunRequest) -> DemoRunRecord:
        return coordinator.run_demo(request)

    @app.get("/api/demo-runs", response_model=DemoRunListResponse)
    def list_demo_runs() -> DemoRunListResponse:
        return coordinator.list_runs()

    @app.get("/api/demo-runs/{run_id}", response_model=DemoRunRecord)
    def get_demo_run(run_id: str) -> DemoRunRecord:
        run = coordinator.get_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="demo_run_not_found")
        return run

    @app.get("/api/shift-reports", response_model=ShiftReportListResponse)
    def list_shift_reports(limit: int = 25) -> ShiftReportListResponse:
        return shift_report_store.list(limit=limit)

    @app.get("/api/shift-reports/{report_id}", response_model=ShiftReportRecord)
    def get_shift_report(report_id: str) -> ShiftReportRecord:
        report = shift_report_store.get(report_id)
        if report is None:
            raise HTTPException(status_code=404, detail="shift_report_not_found")
        return report

    @app.get("/api/logs", response_model=LogListResponse)
    def list_logs(session_id: str | None = None, limit: int = 50) -> LogListResponse:
        return brain.list_logs(session_id=session_id, limit=limit)

    @app.get("/api/traces", response_model=TraceListResponse)
    def list_traces(session_id: str | None = None, limit: int = 50) -> TraceListResponse:
        return brain.list_traces(session_id=session_id, limit=limit)

    @app.get("/api/traces/{trace_id}", response_model=TraceRecord)
    def get_trace(trace_id: str) -> TraceRecord:
        trace = brain.get_trace(trace_id)
        if trace is None:
            raise HTTPException(status_code=404, detail="trace_not_found")
        return trace

    return app


settings = get_settings()
app = create_app(settings=settings)


def main() -> None:
    import uvicorn

    uvicorn.run("embodied_stack.brain.app:app", host=settings.brain_host, port=settings.brain_port, reload=False)


if __name__ == "__main__":
    main()
