from __future__ import annotations

import json
import time
from pathlib import Path
from threading import Thread
from typing import Any

import httpx

from embodied_stack.action_plane import ActionPlaneGateway
from embodied_stack.action_plane.connectors.base import ConnectorActionError
from embodied_stack.backends.router import BackendRouter, OllamaProbeSnapshot
from embodied_stack.body import BodyCommandApplyError, build_body_driver
from embodied_stack.body import calibration as calibration_module
from embodied_stack.body import driver as body_driver_module
from embodied_stack.body.profile import default_head_profile
from embodied_stack.body.serial.transport import DryRunServoTransport, LIVE_SERIAL_MODE
from embodied_stack.brain.agent_os import EmbodiedActionPolicy
from embodied_stack.brain.agent_os.tools import AgentToolRegistry, ToolRuntimeContext
from embodied_stack.brain.llm import DialogueContext, DialogueEngineError, OllamaDialogueEngine
from embodied_stack.brain.memory import MemoryStore
from embodied_stack.brain.memory_policy import MemoryPolicyService
from embodied_stack.brain.tools import KnowledgeToolbox
from embodied_stack.config import Settings, get_settings
from embodied_stack.desktop.app import build_desktop_runtime
from embodied_stack.desktop.devices import DesktopDeviceError
from embodied_stack.demo.local_companion_checks import (
    FakeCameraCapture,
    FakeDeviceRegistry,
    FakeMicrophoneInput,
    FakeSpeakerOutput,
)
from embodied_stack.persistence import write_json_atomic
from embodied_stack.shared.models import (
    ActionInvocationOrigin,
    ActionRequestRecord,
    ActionRiskClass,
    CompanionAudioMode,
    CompanionContextMode,
    DemoCheckResult,
    DemoCheckSuiteRecord,
    DesktopDeviceHealth,
    DesktopDeviceKind,
    EdgeAdapterState,
    EmbodiedWorldModel,
    MemoryLayer,
    MemoryReviewRequest,
    MemoryWriteReasonCode,
    ResponseMode,
    RobotCommand,
    RobotMode,
    SemanticMemoryRecord,
    SessionRecord,
    VoiceRuntimeMode,
    WorldState,
    utc_now,
)


class StaticOllamaProbe:
    def __init__(self, snapshot: OllamaProbeSnapshot) -> None:
        self._snapshot = snapshot

    def snapshot(self) -> OllamaProbeSnapshot:
        return self._snapshot


class UnavailableMicrophoneInput(FakeMicrophoneInput):
    def health(self, *, required: bool = False) -> DesktopDeviceHealth:
        return DesktopDeviceHealth(
            device_id="desktop_microphone",
            kind=DesktopDeviceKind.MICROPHONE,
            state=EdgeAdapterState.DEGRADED if required else EdgeAdapterState.SIMULATED,
            backend="fake_microphone",
            available=False,
            required=required,
            detail="microphone_permission_denied",
        )

    def capture(self, request, session_id: str):  # noqa: ANN001
        del request, session_id
        raise DesktopDeviceError(
            "microphone_permission_denied",
            "Grant microphone access to Terminal/iTerm and retry.",
        )


class UnavailableSpeakerOutput(FakeSpeakerOutput):
    def health(self, *, required: bool = False) -> DesktopDeviceHealth:
        return DesktopDeviceHealth(
            device_id="desktop_speaker",
            kind=DesktopDeviceKind.SPEAKER,
            state=EdgeAdapterState.DEGRADED if required else EdgeAdapterState.SIMULATED,
            backend="fake_speaker",
            available=False,
            required=required,
            detail="speaker_unavailable",
        )

    def speak(self, session_id: str, text: str | None, *, mode: VoiceRuntimeMode):
        del session_id, text, mode
        raise RuntimeError("speaker_unavailable")


class PermissionDeniedCameraCapture(FakeCameraCapture):
    def health(self, *, required: bool = False) -> DesktopDeviceHealth:
        return DesktopDeviceHealth(
            device_id="desktop_camera",
            kind=DesktopDeviceKind.CAMERA,
            state=EdgeAdapterState.DEGRADED if required else EdgeAdapterState.SIMULATED,
            backend="fake_camera",
            available=False,
            required=required,
            detail="camera_authorization_required",
        )

    def capture_snapshot(self):
        raise DesktopDeviceError(
            "camera_authorization_required",
            "Grant camera access to Terminal/iTerm and Homebrew ffmpeg, then retry.",
        )


class MicrophoneUnavailableRegistry(FakeDeviceRegistry):
    def __init__(self) -> None:
        super().__init__()
        self.microphone_input = UnavailableMicrophoneInput()


class SpeakerUnavailableRegistry(FakeDeviceRegistry):
    def __init__(self) -> None:
        super().__init__()
        self.speaker_output = UnavailableSpeakerOutput()


class CameraPermissionDeniedRegistry(FakeDeviceRegistry):
    def __init__(self) -> None:
        super().__init__()
        self.camera_capture = PermissionDeniedCameraCapture()


def _saved_calibration(path: Path) -> None:
    profile = default_head_profile()
    calibration = calibration_module.calibration_from_profile(profile, calibration_kind="saved")
    for joint in calibration.joint_records:
        joint.mirrored_direction_confirmed = True
    calibration.coupling_validation = {
        "neck_pitch_roll": "ok",
        "mirrored_eyelids": "ok",
        "mirrored_brows": "ok",
        "eyes_follow_lids": "ok",
        "range_conflicts": "ok",
    }
    calibration_module.save_head_calibration(calibration, path)


def _unconfirmed_live_transport():
    profile = default_head_profile()
    neutral_positions = {
        servo_id: joint.neutral
        for joint in profile.joints
        for servo_id in joint.servo_ids
    }
    transport = DryRunServoTransport(
        baud_rate=1000000,
        timeout_seconds=0.2,
        known_ids=sorted({servo_id for joint in profile.joints for servo_id in joint.servo_ids}),
        neutral_positions=neutral_positions,
    )
    transport.status.mode = LIVE_SERIAL_MODE
    transport.status.port = "/dev/tty.fake"
    transport.status.healthy = True
    transport.status.confirmed_live = False
    transport.status.reason_code = "transport_unconfirmed"
    return transport


def run_local_companion_failure_drills(
    *,
    settings: Settings | None = None,
    output_dir: str | Path | None = None,
) -> DemoCheckSuiteRecord:
    runner = LocalCompanionFailureDrillRunner(settings=settings, output_dir=output_dir)
    return runner.run()


class LocalCompanionFailureDrillRunner:
    def __init__(self, *, settings: Settings | None = None, output_dir: str | Path | None = None) -> None:
        self.settings = settings or get_settings()
        self.output_dir = Path(output_dir or Path(self.settings.demo_check_dir) / "local_companion_failure_drills")
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
            ("slow_model_response_presence", "Slow text turns keep the fast presence loop visibly alive instead of going dead.", self._check_slow_model_response_presence),
            ("local_model_unavailable", "When local or preferred models are unavailable, the companion falls back honestly instead of stalling.", self._check_local_model_unavailable),
            ("provider_timeout", "Provider timeout classification records both the initial timeout and the cold-start retry failure.", self._check_provider_timeout),
            ("malformed_tool_result", "Malformed tool output is rejected as a traced invalid result instead of being treated as valid.", self._check_malformed_tool_result),
            ("tool_exception", "Tool handler exceptions degrade into a typed failure record instead of escaping uncaught.", self._check_tool_exception),
            ("mic_unavailable", "Microphone unavailability is visible in the runtime health surface and easy to diagnose.", self._check_mic_unavailable),
            ("camera_permission_denied", "Camera permission denial stays explicit and inspectable instead of becoming a vague failure.", self._check_camera_permission_denied),
            ("speaker_unavailable", "Speaker failure does not block the text reply path and remains honestly visible.", self._check_speaker_unavailable),
            ("memory_conflict_resolution", "Conflicting remembered facts can be corrected and tombstoned without corrupting default reads.", self._check_memory_conflict_resolution),
            ("no_retrieval_result", "Empty retrieval results stay honest instead of inventing a memory hit.", self._check_no_retrieval_result),
            ("approval_denied", "Rejected approvals stay bounded and recorded instead of continuing silently.", self._check_approval_denied),
            ("unsupported_action_request", "Unsupported connector actions surface explicit unsupported errors instead of partial execution.", self._check_unsupported_action_request),
            ("serial_port_missing", "Missing serial port keeps the companion in degraded preview instead of attempting live motion.", self._check_serial_port_missing),
            ("serial_calibration_missing", "Live serial motion stays blocked when only template calibration is present.", self._check_serial_calibration_missing),
            ("serial_live_write_not_confirmed", "Unconfirmed live serial transport stays preview-only even with a saved calibration.", self._check_serial_live_write_not_confirmed),
        ]

        for check_name, description, handler in checks:
            check_dir = suite_dir / check_name
            check_dir.mkdir(parents=True, exist_ok=True)
            suite.items.append(handler(check_name=check_name, description=description, check_dir=check_dir))

        suite.completed_at = utc_now()
        suite.passed = all(item.passed for item in suite.items)
        suite.artifact_files["summary"] = str(suite_dir / "summary.json")
        suite.artifact_files["markdown"] = str(suite_dir / "summary.md")
        self._write_json(Path(suite.artifact_files["summary"]), suite)
        Path(suite.artifact_files["markdown"]).write_text(self._render_markdown_summary(suite), encoding="utf-8")
        return suite

    def _check_slow_model_response_presence(self, *, check_name: str, description: str, check_dir: Path) -> DemoCheckResult:
        settings = self._runtime_settings(
            check_dir,
            {
                "blink_fast_presence_ack_delay_seconds": 0.02,
                "blink_fast_presence_tool_delay_seconds": 0.2,
            },
        )
        with build_desktop_runtime(settings=settings, device_registry=FakeDeviceRegistry()) as runtime:
            session = runtime.ensure_session(session_id="failure-drill-slow-turn", user_id="failure-user", response_mode=ResponseMode.GUIDE)
            runtime.configure_companion_loop(session_id=session.session_id, voice_mode=VoiceRuntimeMode.STUB_DEMO)
            original = runtime.operator_console._turn_handler_with_context_refresh

            def slow_handler(turn_request):
                time.sleep(0.12)
                return original(turn_request)

            runtime.operator_console._turn_handler_with_context_refresh = slow_handler
            holder: dict[str, Any] = {}
            worker = Thread(
                target=lambda: holder.setdefault(
                    "interaction",
                    runtime.submit_text(
                        "Check the current local state.",
                        session_id=session.session_id,
                        voice_mode=VoiceRuntimeMode.STUB_DEMO,
                        speak_reply=False,
                        source="failure_drills",
                    ),
                ),
                daemon=True,
            )
            worker.start()
            time.sleep(0.05)
            mid_snapshot = runtime.snapshot(session_id=session.session_id, voice_mode=VoiceRuntimeMode.STUB_DEMO)
            worker.join(timeout=2.0)
            final_snapshot = runtime.snapshot(session_id=session.session_id, voice_mode=VoiceRuntimeMode.STUB_DEMO)
            runtime.operator_console._turn_handler_with_context_refresh = original
        interaction = holder.get("interaction")
        mid_state = mid_snapshot.runtime.presence_runtime.state.value
        passed = bool(
            interaction is not None
            and interaction.response.reply_text
            and mid_state in {"acknowledging", "thinking_fast"}
            and final_snapshot.runtime.presence_runtime.state.value in {"idle", "speaking", "reengaging"}
        )
        return self._finalize_result(
            check_dir=check_dir,
            result=DemoCheckResult(
                check_name=check_name,
                description=description,
                completed_at=utc_now(),
                passed=passed,
                session_id=session.session_id,
                reply_text=interaction.response.reply_text if interaction is not None else None,
                notes=[f"mid_state={mid_state}", f"final_state={final_snapshot.runtime.presence_runtime.state.value}"],
            ),
            payloads={"mid_snapshot": mid_snapshot, "final_snapshot": final_snapshot, "interaction": interaction},
        )

    def _check_local_model_unavailable(self, *, check_name: str, description: str, check_dir: Path) -> DemoCheckResult:
        settings = self._runtime_settings(
            check_dir,
            {
                "blink_backend_profile": "cloud_best",
                "blink_model_profile": "cloud_demo",
                "grsai_api_key": None,
                "openai_api_key": None,
                "perception_multimodal_api_key": None,
                "ollama_base_url": "http://127.0.0.1:9",
                "ollama_timeout_seconds": 0.05,
            },
        )
        with build_desktop_runtime(settings=settings) as runtime:
            interaction = runtime.submit_text(
                "Where is the front desk?",
                session_id="failure-drill-provider-unavailable",
                voice_mode=VoiceRuntimeMode.STUB_DEMO,
                speak_reply=False,
                source="failure_drills",
            )
            snapshot = runtime.snapshot(
                session_id="failure-drill-provider-unavailable",
                voice_mode=VoiceRuntimeMode.STUB_DEMO,
            )
        passed = bool(
            interaction.success
            and interaction.response.reply_text
            and snapshot.runtime.fallback_state.active
            and snapshot.runtime.provider_status == "fallback_ready"
            and any(note.startswith("primary_failed:") for note in snapshot.runtime.fallback_state.notes)
        )
        return self._finalize_result(
            check_dir=check_dir,
            result=DemoCheckResult(
                check_name=check_name,
                description=description,
                completed_at=utc_now(),
                passed=passed,
                session_id="failure-drill-provider-unavailable",
                reply_text=interaction.response.reply_text,
                notes=snapshot.runtime.fallback_state.notes,
            ),
            payloads={"interaction": interaction, "snapshot": snapshot},
        )

    def _check_provider_timeout(self, *, check_name: str, description: str, check_dir: Path) -> DemoCheckResult:
        attempts: list[float] = []
        failures: list[tuple[str, float | None, bool]] = []

        class TimeoutEngine(OllamaDialogueEngine):
            def _perform_chat(self, *, messages: list[dict[str, str]], timeout_seconds: float):
                del messages
                attempts.append(timeout_seconds)
                raise httpx.TimeoutException("fixture_timeout")

        engine = TimeoutEngine(
            base_url="http://127.0.0.1:11434",
            model="qwen3.5:9b",
            timeout_seconds=12.0,
            cold_start_timeout_seconds=30.0,
            warm_checker=lambda: False,
            failure_reporter=lambda reason, timeout_seconds, retry_used: failures.append((reason, timeout_seconds, retry_used)),
        )
        error = None
        try:
            engine.generate_reply(
                "Reply with a short confirmation.",
                DialogueContext(
                    session=SessionRecord(session_id="failure-drill-provider-timeout"),
                    world_state=WorldState(),
                    tool_invocations=[],
                    context_mode=CompanionContextMode.PERSONAL_LOCAL,
                ),
            )
        except DialogueEngineError as exc:
            error = str(exc)
        passed = attempts == [12.0, 30.0] and failures == [
            ("ollama_timeout", 12.0, True),
            ("ollama_timeout_after_cold_start_retry", 30.0, True),
        ] and error == "ollama_timeout_after_cold_start_retry"
        return self._finalize_result(
            check_dir=check_dir,
            result=DemoCheckResult(
                check_name=check_name,
                description=description,
                completed_at=utc_now(),
                passed=passed,
                notes=[f"error={error}"],
            ),
            payloads={"attempts": attempts, "failures": failures, "error": error},
        )

    def _check_malformed_tool_result(self, *, check_name: str, description: str, check_dir: Path) -> DemoCheckResult:
        settings = self._runtime_settings(check_dir)
        registry = AgentToolRegistry()
        spec = registry.resolve_spec("runtime_status")
        original_handler = spec.handler
        object.__setattr__(spec, "handler", lambda model, context: {"unexpected": "shape"})
        try:
            record, output = registry.invoke("runtime_status", {}, context=self._tool_context(settings=settings))
        finally:
            object.__setattr__(spec, "handler", original_handler)
        passed = bool(
            record.success is False
            and record.error_code == "tool_output_invalid"
            and record.validation.output_valid is False
            and output is None
        )
        return self._finalize_result(
            check_dir=check_dir,
            result=DemoCheckResult(
                check_name=check_name,
                description=description,
                completed_at=utc_now(),
                passed=passed,
                notes=[record.error_code or "-", record.validation.detail or "-"],
            ),
            payloads={"record": record, "output": output},
        )

    def _check_tool_exception(self, *, check_name: str, description: str, check_dir: Path) -> DemoCheckResult:
        settings = self._runtime_settings(check_dir)
        registry = AgentToolRegistry()
        spec = registry.resolve_spec("runtime_status")
        original_handler = spec.handler
        object.__setattr__(spec, "handler", lambda model, context: (_ for _ in ()).throw(RuntimeError("fixture_tool_crash")))
        try:
            record, output = registry.invoke("runtime_status", {}, context=self._tool_context(settings=settings))
        finally:
            object.__setattr__(spec, "handler", original_handler)
        passed = bool(
            record.success is False
            and record.error_code == "tool_runtime_error"
            and record.validation.detail == "tool_runtime_error"
            and "RuntimeError:fixture_tool_crash" in (record.error_detail or "")
            and output is None
        )
        return self._finalize_result(
            check_dir=check_dir,
            result=DemoCheckResult(
                check_name=check_name,
                description=description,
                completed_at=utc_now(),
                passed=passed,
                notes=[record.error_code or "-", record.error_detail or "-"],
            ),
            payloads={"record": record, "output": output},
        )

    def _check_mic_unavailable(self, *, check_name: str, description: str, check_dir: Path) -> DemoCheckResult:
        settings = self._runtime_settings(check_dir)
        with build_desktop_runtime(settings=settings, device_registry=MicrophoneUnavailableRegistry()) as runtime:
            session = runtime.ensure_session(session_id="failure-drill-mic", user_id="failure-user")
            runtime.configure_companion_loop(session_id=session.session_id, voice_mode=VoiceRuntimeMode.DESKTOP_NATIVE)
            snapshot = runtime.snapshot(session_id=session.session_id, voice_mode=VoiceRuntimeMode.DESKTOP_NATIVE)
        microphone = next(item for item in snapshot.runtime.device_health if item.kind.value == "microphone")
        passed = bool(
            microphone.available is False
            and microphone.detail == "microphone_permission_denied"
            and snapshot.runtime.default_live_voice_mode == VoiceRuntimeMode.DESKTOP_NATIVE
        )
        return self._finalize_result(
            check_dir=check_dir,
            result=DemoCheckResult(
                check_name=check_name,
                description=description,
                completed_at=utc_now(),
                passed=passed,
                session_id=session.session_id,
                notes=[microphone.detail or "-", microphone.state.value],
            ),
            payloads={"snapshot": snapshot, "microphone": microphone},
        )

    def _check_camera_permission_denied(self, *, check_name: str, description: str, check_dir: Path) -> DemoCheckResult:
        settings = self._runtime_settings(check_dir)
        error = None
        with build_desktop_runtime(settings=settings, device_registry=CameraPermissionDeniedRegistry()) as runtime:
            session = runtime.ensure_session(session_id="failure-drill-camera", user_id="failure-user")
            try:
                runtime.capture_camera_observation(session_id=session.session_id, user_id=session.user_id)
            except DesktopDeviceError as exc:
                error = f"{exc.classification}:{exc.detail}"
            snapshot = runtime.snapshot(session_id=session.session_id, voice_mode=VoiceRuntimeMode.STUB_DEMO)
        camera = next(item for item in snapshot.runtime.device_health if item.kind.value == "camera")
        passed = bool(
            error is not None
            and error.startswith("camera_authorization_required:")
            and camera.detail == "camera_authorization_required"
            and camera.available is False
        )
        return self._finalize_result(
            check_dir=check_dir,
            result=DemoCheckResult(
                check_name=check_name,
                description=description,
                completed_at=utc_now(),
                passed=passed,
                session_id=session.session_id,
                notes=[error or "-", camera.detail or "-"],
            ),
            payloads={"snapshot": snapshot, "error": error, "camera": camera},
        )

    def _check_speaker_unavailable(self, *, check_name: str, description: str, check_dir: Path) -> DemoCheckResult:
        settings = self._runtime_settings(check_dir)
        with build_desktop_runtime(settings=settings, device_registry=SpeakerUnavailableRegistry()) as runtime:
            runtime.voice_manager.get_runtime(VoiceRuntimeMode.MACOS_SAY).text_to_speech = UnavailableSpeakerOutput()
            interaction = runtime.submit_text(
                "Please read this back to me.",
                session_id="failure-drill-speaker",
                voice_mode=VoiceRuntimeMode.MACOS_SAY,
                speak_reply=True,
                source="failure_drills",
            )
            snapshot = runtime.snapshot(session_id="failure-drill-speaker", voice_mode=VoiceRuntimeMode.MACOS_SAY)
        speaker = next(item for item in snapshot.runtime.device_health if item.kind.value == "speaker")
        passed = bool(
            interaction.response.reply_text
            and interaction.voice_output is not None
            and interaction.voice_output.status.value == "failed"
            and interaction.voice_output.message == "reply_audio_failed"
            and speaker.detail == "speaker_unavailable"
        )
        return self._finalize_result(
            check_dir=check_dir,
            result=DemoCheckResult(
                check_name=check_name,
                description=description,
                completed_at=utc_now(),
                passed=passed,
                session_id="failure-drill-speaker",
                reply_text=interaction.response.reply_text,
                notes=[interaction.voice_output.message if interaction.voice_output is not None else "-", speaker.detail or "-"],
            ),
            payloads={"interaction": interaction, "snapshot": snapshot, "speaker": speaker},
        )

    def _check_memory_conflict_resolution(self, *, check_name: str, description: str, check_dir: Path) -> DemoCheckResult:
        store = MemoryStore(check_dir / "brain_store.json")
        policy = MemoryPolicyService(store)
        policy.promote_semantic(
            SemanticMemoryRecord(
                memory_id="semantic-quiet",
                memory_kind="route_preference",
                summary="Alex prefers the quiet route.",
                canonical_value="quiet route",
                session_id="failure-drill-memory",
                user_id="visitor-1",
            ),
            reason_code=MemoryWriteReasonCode.CONVERSATION_TOPIC,
            tool_name="promote_memory",
        )
        policy.promote_semantic(
            SemanticMemoryRecord(
                memory_id="semantic-accessible",
                memory_kind="route_preference",
                summary="Alex prefers the accessible route.",
                canonical_value="accessible route",
                session_id="failure-drill-memory",
                user_id="visitor-1",
            ),
            reason_code=MemoryWriteReasonCode.CONVERSATION_TOPIC,
            tool_name="promote_memory",
        )
        corrected = policy.correct_memory(
            MemoryReviewRequest(
                memory_id="semantic-quiet",
                layer=MemoryLayer.SEMANTIC,
                note="Operator resolved the conflict in favor of the accessible route.",
                author="failure_drills",
                updated_fields={"canonical_value": "accessible route"},
            )
        )
        deleted = policy.delete_memory(
            MemoryReviewRequest(
                memory_id="semantic-accessible",
                layer=MemoryLayer.SEMANTIC,
                note="Operator removed the duplicate after correction.",
                author="failure_drills",
            )
        )
        active = store.list_semantic_memory().items
        all_items = store.list_semantic_memory(include_tombstoned=True).items
        corrected_item = store.get_semantic_memory("semantic-quiet")
        deleted_item = next(item for item in all_items if item.memory_id == "semantic-accessible")
        passed = bool(
            corrected.status.value == "corrected"
            and deleted.status.value == "tombstoned"
            and corrected_item is not None
            and corrected_item.canonical_value == "accessible route"
            and len(active) == 1
            and deleted_item.tombstoned is True
        )
        return self._finalize_result(
            check_dir=check_dir,
            result=DemoCheckResult(
                check_name=check_name,
                description=description,
                completed_at=utc_now(),
                passed=passed,
                notes=[corrected.status.value, deleted.status.value, f"active={len(active)}"],
            ),
            payloads={
                "corrected": corrected,
                "deleted": deleted,
                "active": active,
                "all_items": all_items,
            },
        )

    def _check_no_retrieval_result(self, *, check_name: str, description: str, check_dir: Path) -> DemoCheckResult:
        settings = self._runtime_settings(check_dir)
        store = MemoryStore(check_dir / "brain_store.json")
        knowledge_tools = KnowledgeToolbox(settings=settings, memory_store=store)
        session = store.ensure_session("failure-drill-no-retrieval", user_id="visitor-1")
        record, output = AgentToolRegistry().invoke(
            "memory_retrieval",
            {"query": "What do you remember about my favorite route?"},
            context=self._tool_context(
                settings=settings,
                memory_store=store,
                knowledge_tools=knowledge_tools,
                session=session,
            ),
        )
        passed = bool(
            record.success
            and output is not None
            and not output.episodic_hits
            and not output.semantic_hits
            and not output.remembered_facts
            and not output.remembered_preferences
        )
        return self._finalize_result(
            check_dir=check_dir,
            result=DemoCheckResult(
                check_name=check_name,
                description=description,
                completed_at=utc_now(),
                passed=passed,
                session_id=session.session_id,
                notes=[record.summary, f"semantic_hits={len(output.semantic_hits) if output is not None else 0}"],
            ),
            payloads={"record": record, "output": output},
        )

    def _check_approval_denied(self, *, check_name: str, description: str, check_dir: Path) -> DemoCheckResult:
        settings = self._runtime_settings(
            check_dir,
            {
                "blink_action_plane_browser_backend": "stub",
                "blink_action_plane_browser_storage_dir": str(check_dir / "browser"),
            },
        )
        registry = AgentToolRegistry()
        gateway = ActionPlaneGateway(root_dir=check_dir / "actions", settings=settings)
        context = self._tool_context(settings=settings, action_gateway=gateway)

        open_record, _open_output = registry.invoke(
            "browser_task",
            {
                "query": "Open example.com",
                "target_url": "https://example.com",
                "requested_action": "open_url",
            },
            context=context,
        )
        preview_record, preview_output = registry.invoke(
            "browser_task",
            {
                "query": "Type into the search field",
                "requested_action": "type_text",
                "target_hint": {"label": "Search"},
                "text_input": "Blink companion",
            },
            context=context,
        )
        resolution = gateway.reject_action(
            action_id=preview_record.action_id or "",
            operator_note="not now",
            detail="operator_denied",
            handler_context=context,
        )
        passed = bool(
            open_record.success
            and preview_record.success is False
            and preview_output is not None
            and resolution.execution is not None
            and resolution.execution.status.value == "rejected"
            and resolution.detail == "operator_denied"
            and resolution.approval_state.value == "rejected"
        )
        return self._finalize_result(
            check_dir=check_dir,
            result=DemoCheckResult(
                check_name=check_name,
                description=description,
                completed_at=utc_now(),
                passed=passed,
                session_id=context.session.session_id,
                notes=[preview_record.result_status.value, resolution.detail or "-"],
            ),
            payloads={
                "open_record": open_record,
                "preview_record": preview_record,
                "preview_output": preview_output,
                "resolution": resolution,
            },
        )

    def _check_unsupported_action_request(self, *, check_name: str, description: str, check_dir: Path) -> DemoCheckResult:
        settings = self._runtime_settings(check_dir)
        gateway = ActionPlaneGateway(root_dir=check_dir / "actions", settings=settings)
        connector = gateway.registry.get_connector_runtime("notes_local")
        store = MemoryStore(check_dir / "brain_store.json")
        request = ActionRequestRecord(
            action_id="unsupported-note-action",
            request_hash="unsupported-note-action",
            idempotency_key="unsupported-note-action",
            tool_name="create_note",
            requested_tool_name="create_note",
            action_name="delete_note",
            connector_id="notes_local",
            risk_class=ActionRiskClass.LOW_RISK_LOCAL_WRITE,
            invocation_origin=ActionInvocationOrigin.USER_TURN,
            session_id="failure-drill-unsupported",
            input_payload={},
        )
        error = None
        try:
            assert connector is not None
            connector.execute(
                action_name="delete_note",
                request=request,
                runtime_context=self._tool_context(settings=settings, memory_store=store),
            )
        except ConnectorActionError as exc:
            error = {"code": exc.code, "detail": exc.detail}
        passed = error == {
            "code": "unsupported_action",
            "detail": "unsupported_note_action:delete_note",
        }
        return self._finalize_result(
            check_dir=check_dir,
            result=DemoCheckResult(
                check_name=check_name,
                description=description,
                completed_at=utc_now(),
                passed=passed,
                notes=[json.dumps(error, sort_keys=True)],
            ),
            payloads={"error": error, "request": request},
        )

    def _check_serial_port_missing(self, *, check_name: str, description: str, check_dir: Path) -> DemoCheckResult:
        settings = self._runtime_settings(
            check_dir,
            {
                "blink_runtime_mode": RobotMode.DESKTOP_SERIAL_BODY,
                "blink_body_driver": "serial",
                "blink_serial_transport": "live_serial",
                "blink_serial_port": None,
            },
        )
        with build_desktop_runtime(settings=settings) as runtime:
            interaction = runtime.submit_text(
                "Where is the quiet room?",
                session_id="failure-drill-serial-port-missing",
                voice_mode=VoiceRuntimeMode.STUB_DEMO,
                speak_reply=False,
                source="failure_drills",
            )
            snapshot = runtime.snapshot(session_id="failure-drill-serial-port-missing", voice_mode=VoiceRuntimeMode.STUB_DEMO)
        body_state = snapshot.telemetry.body_state
        honest_serial_fallback = bool(
            body_state is not None
            and (
                snapshot.runtime.body_status.startswith("serial:degraded")
                or (
                    body_state.transport_mode == "live_serial"
                    and body_state.live_motion_enabled is False
                    and (
                        body_state.calibration_status == "template"
                        or snapshot.runtime.body_status.endswith(":disarmed")
                        or body_state.transport_error is not None
                    )
                )
            )
        )
        passed = bool(
            interaction.response.reply_text
            and any(ack.status.value == "transport_error" for ack in interaction.command_acks)
            and honest_serial_fallback
        )
        return self._finalize_result(
            check_dir=check_dir,
            result=DemoCheckResult(
                check_name=check_name,
                description=description,
                completed_at=utc_now(),
                passed=passed,
                session_id="failure-drill-serial-port-missing",
                reply_text=interaction.response.reply_text,
                notes=[snapshot.runtime.body_status, snapshot.telemetry.body_state.transport_error or "-"],
            ),
            payloads={"interaction": interaction, "snapshot": snapshot},
        )

    def _check_serial_calibration_missing(self, *, check_name: str, description: str, check_dir: Path) -> DemoCheckResult:
        settings = self._runtime_settings(
            check_dir,
            {
                "blink_runtime_mode": RobotMode.DESKTOP_SERIAL_BODY,
                "blink_body_driver": "serial",
                "blink_serial_transport": "live_serial",
                "blink_serial_port": "/dev/tty.fake",
                "blink_head_calibration": "src/embodied_stack/body/profiles/robot_head_v1.calibration_template.json",
            },
        )
        driver = build_body_driver(settings)
        error = None
        try:
            driver.apply_command(
                RobotCommand(command_type="set_expression", payload={"expression": "friendly"}),
                {"expression": "friendly"},
            )
        except BodyCommandApplyError as exc:
            error = {"classification": exc.classification, "detail": exc.detail}
        passed = bool(error is not None and error["classification"] in {"transport_unconfirmed", "missing_profile", "transport_unavailable"})
        return self._finalize_result(
            check_dir=check_dir,
            result=DemoCheckResult(
                check_name=check_name,
                description=description,
                completed_at=utc_now(),
                passed=passed,
                notes=[json.dumps(error, sort_keys=True) if error is not None else "no_error"],
            ),
            payloads={"error": error, "body_state": driver.state},
        )

    def _check_serial_live_write_not_confirmed(self, *, check_name: str, description: str, check_dir: Path) -> DemoCheckResult:
        calibration_path = check_dir / "runtime" / "calibrations" / "robot_head_live_v1.json"
        calibration_path.parent.mkdir(parents=True, exist_ok=True)
        _saved_calibration(calibration_path)
        settings = self._runtime_settings(
            check_dir,
            {
                "blink_runtime_mode": RobotMode.DESKTOP_SERIAL_BODY,
                "blink_body_driver": "serial",
                "blink_serial_transport": "dry_run",
                "blink_serial_port": "/dev/tty.fake",
                "blink_servo_baud": 1000000,
                "blink_head_calibration": str(calibration_path),
            },
        )
        driver = build_body_driver(settings)
        assert driver.transport is not None
        driver.transport.status.mode = LIVE_SERIAL_MODE
        driver.transport.status.port = "/dev/tty.fake"
        driver.transport.status.healthy = True
        driver.transport.status.confirmed_live = False
        driver.transport.status.reason_code = "transport_unconfirmed"
        driver.transport.status.last_error = "live_serial_transport_not_confirmed"
        driver._sync_transport_status()  # keep the forced unconfirmed state without re-running live confirmation
        state = driver.state.model_copy(deep=True)
        passed = bool(
            state.transport_mode == "live_serial"
            and state.transport_confirmed_live is False
            and state.transport_reason_code == "transport_unconfirmed"
            and state.live_motion_enabled is False
        )
        return self._finalize_result(
            check_dir=check_dir,
            result=DemoCheckResult(
                check_name=check_name,
                description=description,
                completed_at=utc_now(),
                passed=passed,
                notes=[state.transport_reason_code or "-", f"confirmed={state.transport_confirmed_live}"],
            ),
            payloads={"body_state": state},
        )

    def _runtime_settings(self, check_dir: Path, overrides: dict[str, object] | None = None) -> Settings:
        return self.settings.model_copy(
            update={
                "blink_always_on_enabled": True,
                "blink_context_mode": CompanionContextMode.PERSONAL_LOCAL,
                "blink_model_profile": "offline_stub",
                "blink_backend_profile": "offline_safe",
                "brain_store_path": str(check_dir / "brain_store.json"),
                "demo_report_dir": str(check_dir / "demo_runs"),
                "demo_check_dir": str(check_dir / "demo_checks"),
                "episode_export_dir": str(check_dir / "episodes"),
                "shift_report_dir": str(check_dir / "shift_reports"),
                "operator_auth_runtime_file": str(check_dir / "operator_auth.json"),
                "blink_action_plane_draft_dir": str(check_dir / "actions" / "drafts"),
                "blink_action_plane_stage_dir": str(check_dir / "actions" / "staged"),
                "blink_action_plane_export_dir": str(check_dir / "actions" / "exports"),
                "blink_action_plane_browser_storage_dir": str(check_dir / "actions" / "browser"),
                **(overrides or {}),
            }
        )

    def _tool_context(
        self,
        *,
        settings: Settings,
        memory_store: MemoryStore | None = None,
        knowledge_tools: KnowledgeToolbox | None = None,
        action_gateway: ActionPlaneGateway | None = None,
        session: SessionRecord | None = None,
    ) -> ToolRuntimeContext:
        router = BackendRouter(settings=settings)
        resolved_body_driver = settings.resolved_body_driver.value
        if resolved_body_driver == "serial":
            body_transport_mode = settings.blink_serial_transport
            body_preview_status = settings.blink_serial_transport
        elif resolved_body_driver == "virtual":
            body_transport_mode = "virtual_preview"
            body_preview_status = "virtual_preview"
        else:
            body_transport_mode = "preview_only"
            body_preview_status = "preview_only"
        return ToolRuntimeContext(
            session=session or SessionRecord(session_id="failure-drill-tool-session", user_id="visitor-1"),
            context_mode=CompanionContextMode.PERSONAL_LOCAL,
            user_memory=None,
            world_state=WorldState(),
            world_model=EmbodiedWorldModel(),
            latest_perception=None,
            backend_status=router.runtime_statuses(),
            backend_profile=router.resolved_backend_profile(),
            body_driver_mode=resolved_body_driver,
            body_transport_mode=body_transport_mode,
            body_preview_status=body_preview_status,
            tool_invocations=[],
            action_policy=EmbodiedActionPolicy(settings=settings),
            run_id="failure-drill-run",
            action_invocation_origin=ActionInvocationOrigin.USER_TURN,
            action_gateway=action_gateway,
            knowledge_tools=knowledge_tools,
            memory_store=memory_store,
        )

    def _finalize_result(self, *, check_dir: Path, result: DemoCheckResult, payloads: dict[str, object]) -> DemoCheckResult:
        result.artifact_files["summary"] = str(check_dir / "summary.json")
        self._write_json(Path(result.artifact_files["summary"]), result)
        for name, payload in payloads.items():
            path = check_dir / f"{name}.json"
            result.artifact_files[name] = str(path)
            self._write_json(path, payload)
        self._write_json(Path(result.artifact_files["summary"]), result)
        return result

    def _render_markdown_summary(self, suite: DemoCheckSuiteRecord) -> str:
        lines = [
            "# Local Companion Failure Drills",
            "",
            f"- suite_id: {suite.suite_id}",
            f"- passed: {suite.passed}",
            f"- check_count: {len(suite.items)}",
            "",
            "| Check | Passed | Notes |",
            "| --- | --- | --- |",
        ]
        for item in suite.items:
            notes = "; ".join(item.notes) if item.notes else "-"
            lines.append(f"| {item.check_name} | {'yes' if item.passed else 'no'} | {notes} |")
        return "\n".join(lines) + "\n"

    def _write_json(self, path: Path, payload: object) -> None:
        write_json_atomic(path, self._normalize(payload))

    def _normalize(self, payload: object) -> object:
        if hasattr(payload, "model_dump"):
            return payload.model_dump(mode="json")
        if isinstance(payload, list):
            return [self._normalize(item) for item in payload]
        if isinstance(payload, dict):
            return {key: self._normalize(value) for key, value in payload.items()}
        return payload


def main() -> None:
    suite = run_local_companion_failure_drills()
    print(
        json.dumps(
            {
                "suite_id": suite.suite_id,
                "passed": suite.passed,
                "check_count": len(suite.items),
                "passed_count": sum(1 for item in suite.items if item.passed),
                "artifact_dir": suite.artifact_dir,
                "summary_path": suite.artifact_files.get("summary"),
            },
            indent=2,
        )
    )


__all__ = ["LocalCompanionFailureDrillRunner", "main", "run_local_companion_failure_drills"]
