from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter

from embodied_stack.backends.router import BackendRouter
from embodied_stack.brain.live_voice import LiveVoiceRuntimeManager
from embodied_stack.brain.operator_console import OperatorConsoleService
from embodied_stack.brain.orchestrator import BrainOrchestrator
from embodied_stack.brain.perception import PerceptionService
from embodied_stack.config import Settings, get_settings
from embodied_stack.demo.coordinator import DemoCoordinator
from embodied_stack.demo.episodes import EpisodeStore, build_exporter
from embodied_stack.demo.shift_reports import ShiftReportStore
from embodied_stack.desktop.runtime import build_inprocess_embodiment_gateway
from embodied_stack.desktop.devices import build_desktop_device_registry
from embodied_stack.persistence import write_json_atomic
from embodied_stack.shared.models import (
    BrainResetRequest,
    CommandType,
    DemoCheckResult,
    DemoCheckSuiteRecord,
    DemoFallbackEvent,
    InvestorSceneRunRequest,
    OperatorInteractionResult,
    OperatorVoiceTurnRequest,
    PerceptionProviderMode,
    PerceptionSnapshotSubmitRequest,
    ResponseMode,
    SessionStatus,
    SimulatedSensorEventRequest,
    TraceOutcome,
    TraceRecord,
    VoiceRuntimeMode,
    WorldState,
    RobotMode,
    utc_now,
)


@dataclass
class InProcessDemoRuntime:
    settings: Settings
    edge_gateway: object
    orchestrator: BrainOrchestrator
    coordinator: DemoCoordinator
    operator_console: OperatorConsoleService


def run_demo_checks(
    *,
    settings: Settings | None = None,
    output_dir: str | Path | None = None,
) -> DemoCheckSuiteRecord:
    runner = DemoCheckRunner(settings=settings, output_dir=output_dir)
    return runner.run()


class DemoCheckRunner:
    def __init__(self, *, settings: Settings | None = None, output_dir: str | Path | None = None) -> None:
        self.settings = settings or get_settings()
        self.output_dir = Path(output_dir or self.settings.demo_check_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def run(self) -> DemoCheckSuiteRecord:
        suite = DemoCheckSuiteRecord(
            configured_dialogue_backend=self.settings.brain_dialogue_backend,
            runtime_profile=self.settings.brain_runtime_profile,
            deployment_target=self.settings.brain_deployment_target,
        )
        suite_dir = self.output_dir / suite.suite_id
        suite_dir.mkdir(parents=True, exist_ok=True)
        suite.artifact_dir = str(suite_dir)

        checks = [
            ("greeting", "Presence detection becomes a visible greeting.", self._check_greeting),
            ("attentive_listening", "A brief backchannel keeps Blink-AI visibly attentive instead of over-talking.", self._check_attentive_listening),
            ("wayfinding", "Wayfinding question returns grounded directions and safe commands.", self._check_wayfinding),
            ("events_lookup", "Events query returns imported venue schedule data.", self._check_events_lookup),
            ("memory_followup", "The brain remembers a recent location and can repeat it.", self._check_memory_followup),
            ("operator_escalation", "A human-handoff request becomes explicit operator escalation.", self._check_operator_escalation),
            ("safe_idle_behavior", "Failure paths enter safe idle instead of pretending to continue.", self._check_safe_idle_behavior),
            ("virtual_body_behavior", "The virtual body remains a useful demo surface with visible embodiment state.", self._check_virtual_body_behavior),
            ("camera_unavailable_fallback", "Camera/perception gaps stay honest and degrade without crashing the desktop loop.", self._check_camera_unavailable_fallback),
            ("bodyless_conversation", "Bodyless mode still supports practical conversation with transcript, memory, and world state.", self._check_bodyless_conversation),
            ("serial_transport_fallback", "Serial-body mode reports degraded transport honestly while conversation continues.", self._check_serial_transport_fallback),
            ("provider_failure_fallback", "A provider-backed path degrades honestly to the deterministic fallback.", self._check_provider_failure_fallback),
        ]

        for check_name, description, handler in checks:
            check_dir = suite_dir / check_name
            check_dir.mkdir(parents=True, exist_ok=True)
            suite.items.append(handler(check_name=check_name, description=description, check_dir=check_dir))

        suite.completed_at = utc_now()
        suite.passed = all(item.passed for item in suite.items)
        suite.artifact_files["summary"] = str(suite_dir / "summary.json")
        self._write_json(Path(suite.artifact_files["summary"]), suite)
        return suite

    def _check_greeting(self, *, check_name: str, description: str, check_dir: Path) -> DemoCheckResult:
        runtime = self._build_runtime(check_dir)
        started_at = utc_now()
        timer = perf_counter()
        scene = runtime.operator_console.run_investor_scene(
            "greeting_presence",
            InvestorSceneRunRequest(session_id="check-greeting", voice_mode=VoiceRuntimeMode.STUB_DEMO, speak_reply=False),
        )
        latency_ms = round((perf_counter() - timer) * 1000.0, 2)
        item = scene.items[0]
        command_types = [command.command_type for command in item.response.commands]
        passed = (
            scene.success
            and any(token in (item.response.reply_text or "").lower() for token in ("welcome", "hello", "hi."))
            and CommandType.SET_LED in command_types
            and CommandType.SPEAK in command_types
        )
        return self._finalize_check_result(
            check_dir=check_dir,
            result=DemoCheckResult(
                check_name=check_name,
                description=description,
                started_at=started_at,
                completed_at=utc_now(),
                passed=passed,
                session_id=scene.session_id,
                backend_used=self._trace_engine(runtime, item.response.trace_id),
                reply_text=item.response.reply_text,
                command_types=command_types,
                latency_ms=latency_ms,
                fallback_events=self._collect_fallback_events(runtime, scene.session_id),
                final_world_state=runtime.orchestrator.get_world_state(),
                notes=["scene:greeting_presence"],
            ),
            payloads={"scene_result": scene},
            runtime=runtime,
        )

    def _check_attentive_listening(self, *, check_name: str, description: str, check_dir: Path) -> DemoCheckResult:
        runtime = self._build_runtime(check_dir)
        started_at = utc_now()
        timer = perf_counter()
        scene = runtime.operator_console.run_investor_scene(
            "attentive_listening",
            InvestorSceneRunRequest(session_id="check-listening", voice_mode=VoiceRuntimeMode.STUB_DEMO, speak_reply=False),
        )
        latency_ms = round((perf_counter() - timer) * 1000.0, 2)
        item = scene.items[0]
        telemetry = runtime.edge_gateway.get_telemetry()
        command_types = [command.command_type for command in item.response.commands]
        passed = (
            scene.success
            and any(command_type == CommandType.SET_EXPRESSION for command_type in command_types)
            and telemetry.body_state is not None
            and telemetry.body_state.active_expression in {"listening", "listen_attentively"}
        )
        return self._finalize_check_result(
            check_dir=check_dir,
            result=DemoCheckResult(
                check_name=check_name,
                description=description,
                started_at=started_at,
                completed_at=utc_now(),
                passed=passed,
                session_id=scene.session_id,
                backend_used=self._trace_engine(runtime, item.response.trace_id),
                reply_text=item.response.reply_text,
                command_types=command_types,
                latency_ms=latency_ms,
                fallback_events=self._collect_fallback_events(runtime, scene.session_id),
                final_world_state=runtime.orchestrator.get_world_state(),
                notes=["scene:attentive_listening"],
            ),
            payloads={"scene_result": scene},
            runtime=runtime,
        )

    def _check_wayfinding(self, *, check_name: str, description: str, check_dir: Path) -> DemoCheckResult:
        runtime = self._build_runtime(check_dir)
        started_at = utc_now()
        timer = perf_counter()
        scene = runtime.operator_console.run_investor_scene(
            "venue_helpful_question",
            InvestorSceneRunRequest(session_id="check-wayfinding", voice_mode=VoiceRuntimeMode.STUB_DEMO, speak_reply=False),
        )
        latency_ms = round((perf_counter() - timer) * 1000.0, 2)
        item = scene.items[0]
        passed = scene.success and "Workshop Room" in (item.response.reply_text or "")
        return self._finalize_check_result(
            check_dir=check_dir,
            result=DemoCheckResult(
                check_name=check_name,
                description=description,
                started_at=started_at,
                completed_at=utc_now(),
                passed=passed,
                session_id=scene.session_id,
                backend_used=self._trace_engine(runtime, item.response.trace_id),
                reply_text=item.response.reply_text,
                command_types=[command.command_type for command in item.response.commands],
                latency_ms=latency_ms,
                fallback_events=self._collect_fallback_events(runtime, scene.session_id),
                final_world_state=runtime.orchestrator.get_world_state(),
                notes=["scene:venue_helpful_question"],
            ),
            payloads={"scene_result": scene},
            runtime=runtime,
        )

    def _check_events_lookup(self, *, check_name: str, description: str, check_dir: Path) -> DemoCheckResult:
        runtime = self._build_runtime(check_dir)
        started_at = utc_now()
        timer = perf_counter()
        interaction = runtime.operator_console.submit_text_turn(
            OperatorVoiceTurnRequest(
                session_id="check-events",
                input_text="What events are happening this week?",
                response_mode=ResponseMode.GUIDE,
                voice_mode=VoiceRuntimeMode.STUB_DEMO,
                speak_reply=False,
                source="demo_checks",
            )
        )
        latency_ms = round((perf_counter() - timer) * 1000.0, 2)
        passed = "Robotics Workshop" in (interaction.response.reply_text or "")
        return self._finalize_check_result(
            check_dir=check_dir,
            result=self._result_from_interaction(
                check_name=check_name,
                description=description,
                started_at=started_at,
                latency_ms=latency_ms,
                interaction=interaction,
                runtime=runtime,
                passed=passed,
                notes=["typed_input:events_lookup"],
            ),
            payloads={"interaction_result": interaction},
            runtime=runtime,
        )

    def _check_memory_followup(self, *, check_name: str, description: str, check_dir: Path) -> DemoCheckResult:
        runtime = self._build_runtime(check_dir)
        started_at = utc_now()
        session_id = "check-memory"
        runtime.operator_console.run_investor_scene(
            "wayfinding_usefulness",
            InvestorSceneRunRequest(session_id=session_id, voice_mode=VoiceRuntimeMode.STUB_DEMO, speak_reply=False),
        )
        timer = perf_counter()
        scene = runtime.operator_console.run_investor_scene(
            "memory_followup",
            InvestorSceneRunRequest(session_id=session_id, voice_mode=VoiceRuntimeMode.STUB_DEMO, speak_reply=False),
        )
        latency_ms = round((perf_counter() - timer) * 1000.0, 2)
        item = scene.items[0]
        session = runtime.orchestrator.get_session(session_id)
        passed = (
            scene.success
            and "Workshop Room" in (item.response.reply_text or "")
            and session is not None
            and session.session_memory.get("last_location") == "workshop_room"
        )
        notes = ["scene:memory_followup"]
        if session is not None:
            notes.append(f"summary:{session.conversation_summary}")
        return self._finalize_check_result(
            check_dir=check_dir,
            result=DemoCheckResult(
                check_name=check_name,
                description=description,
                started_at=started_at,
                completed_at=utc_now(),
                passed=passed,
                session_id=scene.session_id,
                backend_used=self._trace_engine(runtime, item.response.trace_id),
                reply_text=item.response.reply_text,
                command_types=[command.command_type for command in item.response.commands],
                latency_ms=latency_ms,
                fallback_events=self._collect_fallback_events(runtime, scene.session_id),
                final_world_state=runtime.orchestrator.get_world_state(),
                notes=notes,
            ),
            payloads={"scene_result": scene, "session": session},
            runtime=runtime,
        )

    def _check_operator_escalation(self, *, check_name: str, description: str, check_dir: Path) -> DemoCheckResult:
        runtime = self._build_runtime(check_dir)
        started_at = utc_now()
        timer = perf_counter()
        scene = runtime.operator_console.run_investor_scene(
            "operator_escalation",
            InvestorSceneRunRequest(session_id="check-escalation", voice_mode=VoiceRuntimeMode.STUB_DEMO, speak_reply=False),
        )
        latency_ms = round((perf_counter() - timer) * 1000.0, 2)
        session = runtime.orchestrator.get_session(scene.session_id)
        world_state = runtime.orchestrator.get_world_state()
        incidents = runtime.orchestrator.list_incidents(session_id=scene.session_id).items
        item = scene.items[0]
        passed = (
            scene.success
            and session is not None
            and session.status == SessionStatus.ESCALATION_PENDING
            and scene.session_id in world_state.pending_operator_session_ids
            and bool(incidents)
            and incidents[0].current_status.value == "pending"
        )
        return self._finalize_check_result(
            check_dir=check_dir,
            result=DemoCheckResult(
                check_name=check_name,
                description=description,
                started_at=started_at,
                completed_at=utc_now(),
                passed=passed,
                session_id=scene.session_id,
                backend_used=self._trace_engine(runtime, item.response.trace_id),
                reply_text=item.response.reply_text,
                command_types=[command.command_type for command in item.response.commands],
                latency_ms=latency_ms,
                fallback_events=self._collect_fallback_events(runtime, scene.session_id),
                final_world_state=world_state,
                notes=["scene:operator_escalation", f"incident_count:{len(incidents)}"],
            ),
            payloads={"scene_result": scene, "session": session, "incidents": incidents},
            runtime=runtime,
        )

    def _check_safe_idle_behavior(self, *, check_name: str, description: str, check_dir: Path) -> DemoCheckResult:
        runtime = self._build_runtime(check_dir)
        started_at = utc_now()
        timer = perf_counter()
        scene = runtime.operator_console.run_investor_scene(
            "safe_fallback_failure",
            InvestorSceneRunRequest(session_id="check-safe-idle", voice_mode=VoiceRuntimeMode.STUB_DEMO, speak_reply=False),
        )
        latency_ms = round((perf_counter() - timer) * 1000.0, 2)
        snapshot = runtime.operator_console.get_snapshot(session_id=scene.session_id)
        fallback_events = self._collect_fallback_events(runtime, scene.session_id)
        passed = (
            scene.success
            and snapshot.heartbeat.safe_idle_active
            and snapshot.world_state.mode.value == "degraded_safe_idle"
            and all(item.outcome == "safe_fallback" for item in scene.items)
        )
        return self._finalize_check_result(
            check_dir=check_dir,
            result=DemoCheckResult(
                check_name=check_name,
                description=description,
                started_at=started_at,
                completed_at=utc_now(),
                passed=passed,
                session_id=scene.session_id,
                backend_used=self._trace_engine(runtime, scene.items[-1].response.trace_id),
                reply_text=scene.items[-1].response.reply_text,
                command_types=[command.command_type for command in scene.items[-1].response.commands],
                latency_ms=latency_ms,
                fallback_events=fallback_events,
                final_world_state=snapshot.world_state,
                notes=["scene:safe_fallback_failure"],
            ),
            payloads={"scene_result": scene, "snapshot": snapshot},
            runtime=runtime,
        )

    def _check_virtual_body_behavior(self, *, check_name: str, description: str, check_dir: Path) -> DemoCheckResult:
        runtime = self._build_runtime(
            check_dir,
            settings_overrides={"blink_runtime_mode": RobotMode.DESKTOP_VIRTUAL_BODY},
        )
        started_at = utc_now()
        timer = perf_counter()
        interaction = runtime.operator_console.submit_text_turn(
            OperatorVoiceTurnRequest(
                session_id="check-virtual-body",
                input_text="Where is the front desk?",
                response_mode=ResponseMode.GUIDE,
                voice_mode=VoiceRuntimeMode.STUB_DEMO,
                speak_reply=False,
                source="demo_checks",
            )
        )
        latency_ms = round((perf_counter() - timer) * 1000.0, 2)
        telemetry = runtime.edge_gateway.get_telemetry()
        passed = (
            interaction.success
            and telemetry.body_state is not None
            and telemetry.body_state.virtual_preview is not None
            and telemetry.body_driver_mode.value == "virtual"
        )
        return self._finalize_check_result(
            check_dir=check_dir,
            result=self._result_from_interaction(
                check_name=check_name,
                description=description,
                started_at=started_at,
                latency_ms=latency_ms,
                interaction=interaction,
                runtime=runtime,
                passed=passed,
                notes=[
                    "virtual_preview:true",
                    f"active_expression:{telemetry.body_state.active_expression if telemetry.body_state else '-'}",
                ],
            ),
            payloads={"interaction_result": interaction, "telemetry": telemetry},
            runtime=runtime,
        )

    def _check_camera_unavailable_fallback(self, *, check_name: str, description: str, check_dir: Path) -> DemoCheckResult:
        runtime = self._build_runtime(
            check_dir,
            settings_overrides={
                "blink_model_profile": "local_dev",
                "perception_default_provider": "browser_snapshot",
                "blink_camera_source": "unavailable",
            },
        )
        started_at = utc_now()
        timer = perf_counter()
        submission = runtime.operator_console.submit_perception_snapshot(
            PerceptionSnapshotSubmitRequest(
                session_id="check-camera-fallback",
                provider_mode=PerceptionProviderMode.BROWSER_SNAPSHOT,
                source="demo_checks",
            )
        )
        latency_ms = round((perf_counter() - timer) * 1000.0, 2)
        passed = (
            submission.success is False
            and submission.snapshot.status.value == "failed"
            and submission.snapshot.limited_awareness is True
            and submission.snapshot.message == "browser_snapshot_missing_image"
        )
        return self._finalize_check_result(
            check_dir=check_dir,
            result=DemoCheckResult(
                check_name=check_name,
                description=description,
                started_at=started_at,
                completed_at=utc_now(),
                passed=passed,
                session_id=submission.session_id or "check-camera-fallback",
                backend_used=None,
                reply_text=submission.snapshot.scene_summary,
                command_types=[],
                latency_ms=latency_ms,
                fallback_events=[],
                final_world_state=runtime.orchestrator.get_world_state(),
                notes=["perception:browser_snapshot", "camera_source:unavailable"],
            ),
            payloads={"submission": submission},
            runtime=runtime,
        )

    def _check_bodyless_conversation(self, *, check_name: str, description: str, check_dir: Path) -> DemoCheckResult:
        runtime = self._build_runtime(
            check_dir,
            settings_overrides={
                "blink_runtime_mode": RobotMode.DESKTOP_BODYLESS,
                "blink_model_profile": "offline_stub",
                "blink_voice_profile": "offline_stub",
            },
        )
        started_at = utc_now()
        timer = perf_counter()
        interaction = runtime.operator_console.submit_text_turn(
            OperatorVoiceTurnRequest(
                session_id="check-bodyless",
                input_text="What events are happening this week?",
                response_mode=ResponseMode.GUIDE,
                voice_mode=VoiceRuntimeMode.STUB_DEMO,
                speak_reply=False,
                source="demo_checks",
            )
        )
        latency_ms = round((perf_counter() - timer) * 1000.0, 2)
        telemetry = runtime.edge_gateway.get_telemetry()
        passed = (
            interaction.success
            and "Robotics Workshop" in (interaction.response.reply_text or "")
            and telemetry.body_driver_mode.value == "bodyless"
        )
        return self._finalize_check_result(
            check_dir=check_dir,
            result=self._result_from_interaction(
                check_name=check_name,
                description=description,
                started_at=started_at,
                latency_ms=latency_ms,
                interaction=interaction,
                runtime=runtime,
                passed=passed,
                notes=["runtime_mode:desktop_bodyless"],
            ),
            payloads={"interaction_result": interaction, "telemetry": telemetry},
            runtime=runtime,
        )

    def _check_serial_transport_fallback(self, *, check_name: str, description: str, check_dir: Path) -> DemoCheckResult:
        runtime = self._build_runtime(
            check_dir,
            settings_overrides={
                "blink_runtime_mode": RobotMode.DESKTOP_SERIAL_BODY,
                "blink_body_driver": "serial",
                "blink_serial_transport": "live_serial",
                "blink_serial_port": None,
            },
        )
        started_at = utc_now()
        timer = perf_counter()
        interaction = runtime.operator_console.submit_text_turn(
            OperatorVoiceTurnRequest(
                session_id="check-serial-fallback",
                input_text="Where is the quiet room?",
                response_mode=ResponseMode.GUIDE,
                voice_mode=VoiceRuntimeMode.STUB_DEMO,
                speak_reply=False,
                source="demo_checks",
            )
        )
        latency_ms = round((perf_counter() - timer) * 1000.0, 2)
        telemetry = runtime.edge_gateway.get_telemetry()
        body_state = telemetry.body_state
        honest_serial_fallback = bool(
            body_state is not None
            and (
                (
                    body_state.transport_healthy is False
                    and body_state.transport_error is not None
                )
                or (
                    body_state.transport_mode == "live_serial"
                    and body_state.live_motion_enabled is False
                    and (
                        body_state.calibration_status == "template"
                        or body_state.transport_error is not None
                    )
                )
            )
        )
        passed = (
            "Quiet Room" in (interaction.response.reply_text or "")
            and any(ack.status.value == "transport_error" for ack in interaction.command_acks)
            and honest_serial_fallback
        )
        return self._finalize_check_result(
            check_dir=check_dir,
            result=self._result_from_interaction(
                check_name=check_name,
                description=description,
                started_at=started_at,
                latency_ms=latency_ms,
                interaction=interaction,
                runtime=runtime,
                passed=passed,
                notes=["runtime_mode:desktop_serial_body", "expected_serial_fallback:true"],
            ),
            payloads={"interaction_result": interaction, "telemetry": telemetry},
            runtime=runtime,
        )

    def _check_provider_failure_fallback(
        self,
        *,
        check_name: str,
        description: str,
        check_dir: Path,
    ) -> DemoCheckResult:
        runtime = self._build_runtime(
            check_dir,
            settings_overrides={
                "brain_dialogue_backend": "grsai",
                "grsai_api_key": None,
            },
        )
        started_at = utc_now()
        timer = perf_counter()
        interaction = runtime.operator_console.submit_text_turn(
            OperatorVoiceTurnRequest(
                session_id="check-provider-fallback",
                input_text="Where is the quiet room?",
                response_mode=ResponseMode.GUIDE,
                voice_mode=VoiceRuntimeMode.STUB_DEMO,
                speak_reply=False,
                source="demo_checks",
            )
        )
        latency_ms = round((perf_counter() - timer) * 1000.0, 2)
        trace = runtime.orchestrator.get_trace(interaction.response.trace_id or "")
        passed = (
            trace is not None
            and trace.reasoning.fallback_used is True
            and bool(trace.reasoning.engine)
            and "quiet room" in (interaction.response.reply_text or "").lower()
            and any(note.startswith("primary_failed:") for note in trace.reasoning.notes)
        )
        notes = ["provider_configured:grsai", "expected_fallback:honest_visible"]
        if trace is not None:
            notes.extend(trace.reasoning.notes)
        return self._finalize_check_result(
            check_dir=check_dir,
            result=self._result_from_interaction(
                check_name=check_name,
                description=description,
                started_at=started_at,
                latency_ms=latency_ms,
                interaction=interaction,
                runtime=runtime,
                passed=passed,
                notes=notes,
            ),
            payloads={"interaction_result": interaction, "trace": trace},
            runtime=runtime,
        )

    def _build_runtime(
        self,
        check_dir: Path,
        settings_overrides: dict | None = None,
    ) -> InProcessDemoRuntime:
        settings_data = self.settings.model_dump()
        settings_data.update(
            {
                "brain_store_path": str(check_dir / "brain_store.json"),
                "demo_report_dir": str(check_dir / "demo_runs"),
                "demo_check_dir": str(self.output_dir),
                "episode_export_dir": str(check_dir / "episodes"),
                "brain_voice_backend": "stub",
                "live_voice_default_mode": "stub_demo",
            }
        )
        if settings_overrides:
            settings_data.update(settings_overrides)
        runtime_settings = Settings(**settings_data)
        backend_router = BackendRouter(settings=runtime_settings)
        edge_gateway = build_inprocess_embodiment_gateway(runtime_settings)
        orchestrator = BrainOrchestrator(
            settings=runtime_settings,
            store_path=runtime_settings.brain_store_path,
            backend_router=backend_router,
        )
        coordinator = DemoCoordinator(
            orchestrator=orchestrator,
            edge_gateway=edge_gateway,
            report_dir=runtime_settings.demo_report_dir,
        )
        device_registry = build_desktop_device_registry(runtime_settings)
        voice_manager = LiveVoiceRuntimeManager(
            settings=runtime_settings,
            device_registry=device_registry,
            macos_voice_name=runtime_settings.macos_tts_voice,
            macos_rate=runtime_settings.macos_tts_rate,
        )
        perception_service = PerceptionService(
            settings=runtime_settings,
            memory=orchestrator.memory,
            event_handler=orchestrator.handle_event,
            providers=backend_router.build_perception_providers(),
        )
        operator_console = OperatorConsoleService(
            settings=runtime_settings,
            orchestrator=orchestrator,
            edge_gateway=coordinator.edge_gateway,
            demo_coordinator=coordinator,
            shift_report_store=ShiftReportStore(runtime_settings.shift_report_dir),
            voice_manager=voice_manager,
            backend_router=backend_router,
            device_registry=device_registry,
            perception_service=perception_service,
            episode_exporter=build_exporter(
                settings=runtime_settings,
                orchestrator=orchestrator,
                report_store=coordinator.report_store,
                episode_store=EpisodeStore(runtime_settings.episode_export_dir),
                edge_gateway=coordinator.edge_gateway,
            ),
        )
        coordinator.reset_system(
            BrainResetRequest(
                reset_edge=True,
                clear_user_memory=True,
                clear_demo_runs=True,
            )
        )
        return InProcessDemoRuntime(
            settings=runtime_settings,
            edge_gateway=edge_gateway,
            orchestrator=orchestrator,
            coordinator=coordinator,
            operator_console=operator_console,
        )

    def _result_from_interaction(
        self,
        *,
        check_name: str,
        description: str,
        started_at,
        latency_ms: float,
        interaction: OperatorInteractionResult,
        runtime: InProcessDemoRuntime,
        passed: bool,
        notes: list[str],
    ) -> DemoCheckResult:
        return DemoCheckResult(
            check_name=check_name,
            description=description,
            started_at=started_at,
            completed_at=utc_now(),
            passed=passed,
            session_id=interaction.session_id,
            backend_used=self._trace_engine(runtime, interaction.response.trace_id),
            reply_text=interaction.response.reply_text,
            command_types=[command.command_type for command in interaction.response.commands],
            latency_ms=latency_ms,
            fallback_events=self._collect_fallback_events(runtime, interaction.session_id),
            final_world_state=runtime.orchestrator.get_world_state(),
            notes=notes,
        )

    def _collect_fallback_events(self, runtime: InProcessDemoRuntime, session_id: str) -> list[DemoFallbackEvent]:
        traces = runtime.orchestrator.list_traces(session_id=session_id, limit=25).items
        events: list[DemoFallbackEvent] = []
        for trace in reversed(traces):
            if trace.outcome not in {TraceOutcome.SAFE_FALLBACK, TraceOutcome.FALLBACK_REPLY, TraceOutcome.ERROR}:
                continue
            note = ", ".join(trace.reasoning.notes) if trace.reasoning.notes else None
            events.append(
                DemoFallbackEvent(
                    timestamp=trace.timestamp,
                    session_id=trace.session_id,
                    event_type=trace.event.event_type,
                    trace_id=trace.trace_id,
                    backend_used=trace.reasoning.engine,
                    outcome=trace.outcome,
                    note=note,
                )
            )
        return events

    def _trace_engine(self, runtime: InProcessDemoRuntime, trace_id: str | None) -> str | None:
        if not trace_id:
            return None
        trace = runtime.orchestrator.get_trace(trace_id)
        return trace.reasoning.engine if trace else None

    def _finalize_check_result(
        self,
        *,
        check_dir: Path,
        result: DemoCheckResult,
        payloads: dict[str, object],
        runtime: InProcessDemoRuntime,
    ) -> DemoCheckResult:
        artifact_files: dict[str, str] = {}
        for name, payload in payloads.items():
            if payload is None:
                continue
            path = check_dir / f"{name}.json"
            self._write_json(path, payload)
            artifact_files[name] = str(path)
        trace_list_path = check_dir / "traces.json"
        self._write_json(trace_list_path, runtime.orchestrator.list_traces(session_id=result.session_id, limit=25))
        artifact_files["traces"] = str(trace_list_path)
        world_state_path = check_dir / "world_state.json"
        self._write_json(world_state_path, runtime.orchestrator.get_world_state())
        artifact_files["world_state"] = str(world_state_path)
        telemetry_path = check_dir / "telemetry_snapshot.json"
        self._write_json(telemetry_path, runtime.edge_gateway.get_telemetry())
        artifact_files["telemetry_snapshot"] = str(telemetry_path)
        heartbeat_path = check_dir / "heartbeat.json"
        self._write_json(heartbeat_path, runtime.edge_gateway.get_heartbeat())
        artifact_files["heartbeat"] = str(heartbeat_path)
        summary_path = check_dir / "summary.json"
        result.artifact_files = artifact_files
        self._write_json(summary_path, result)
        result.artifact_files["summary"] = str(summary_path)
        self._write_json(summary_path, result)
        return result

    def _write_json(self, path: Path, payload: object) -> None:
        normalized = self._normalize_payload(payload)
        write_json_atomic(path, normalized)

    def _normalize_payload(self, payload: object):
        if hasattr(payload, "model_dump"):
            return payload.model_dump(mode="json")
        if isinstance(payload, list):
            return [self._normalize_payload(item) for item in payload]
        if isinstance(payload, dict):
            return {key: self._normalize_payload(value) for key, value in payload.items()}
        return payload


def main() -> None:
    suite = run_demo_checks()
    summary = {
        "suite_id": suite.suite_id,
        "passed": suite.passed,
        "check_count": len(suite.items),
        "passed_count": sum(1 for item in suite.items if item.passed),
        "artifact_dir": suite.artifact_dir,
    }
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
