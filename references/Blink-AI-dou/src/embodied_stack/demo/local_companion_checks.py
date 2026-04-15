from __future__ import annotations

import base64
import json
from pathlib import Path

from fastapi.testclient import TestClient

from embodied_stack.config import Settings, get_settings
from embodied_stack.desktop.app import build_desktop_runtime
from embodied_stack.persistence import write_json_atomic
from embodied_stack.multimodal.camera import DesktopCameraSource
from embodied_stack.shared.models import (
    DemoCheckResult,
    DemoCheckSuiteRecord,
    DesktopDeviceHealth,
    DesktopDeviceKind,
    EdgeAdapterState,
    EpisodeExportSessionRequest,
    PerceptionProviderMode,
    PerceptionSourceFrame,
    ResponseMode,
    RobotMode,
    SpeechOutputResult,
    SpeechOutputStatus,
    SpeechTranscriptRecord,
    VoiceRuntimeMode,
    utc_now,
)


class FakeMicrophoneInput:
    def health(self, *, required: bool = False) -> DesktopDeviceHealth:
        return DesktopDeviceHealth(
            device_id="desktop_microphone",
            kind=DesktopDeviceKind.MICROPHONE,
            state=EdgeAdapterState.ACTIVE,
            backend="fake_microphone",
            available=True,
            required=required,
            detail="fixture_microphone_ready",
        )

    def capture(self, request, session_id: str) -> SpeechTranscriptRecord:
        return SpeechTranscriptRecord(
            session_id=session_id,
            source=request.source or "desktop_microphone",
            transcript_text="Where is the front desk?",
            capture_mode="desktop_microphone",
            transcription_backend="fake_apple_speech",
            confidence=0.92,
        )

    def cancel(self, session_id: str | None = None) -> None:
        del session_id


class FakeSpeakerOutput:
    def health(self, *, required: bool = False) -> DesktopDeviceHealth:
        return DesktopDeviceHealth(
            device_id="desktop_speaker",
            kind=DesktopDeviceKind.SPEAKER,
            state=EdgeAdapterState.ACTIVE,
            backend="fake_speaker",
            available=True,
            required=required,
            detail="fixture_speaker_ready",
        )

    def speak(self, session_id: str, text: str | None, *, mode: VoiceRuntimeMode) -> SpeechOutputResult:
        return SpeechOutputResult(
            session_id=session_id,
            backend="fake_speaker",
            output_backend="fake_speaker",
            mode=mode,
            audio_available=True,
            status=SpeechOutputStatus.COMPLETED,
            spoken_text=text,
            message="fixture_speech_completed",
        )

    def get_state(self, session_id: str | None = None, *, mode: VoiceRuntimeMode) -> SpeechOutputResult:
        return SpeechOutputResult(
            session_id=session_id,
            backend="fake_speaker",
            output_backend="fake_speaker",
            mode=mode,
            audio_available=True,
            status=SpeechOutputStatus.IDLE,
            message="fixture_speaker_idle",
        )

    def cancel(self, session_id: str | None = None, *, mode: VoiceRuntimeMode) -> SpeechOutputResult:
        return SpeechOutputResult(
            session_id=session_id,
            backend="fake_speaker",
            output_backend="fake_speaker",
            mode=mode,
            audio_available=True,
            status=SpeechOutputStatus.INTERRUPTED,
            message="fixture_speaker_cancelled",
        )


class FakeStubSpeakerOutput(FakeSpeakerOutput):
    def health(self, *, required: bool = False) -> DesktopDeviceHealth:
        return DesktopDeviceHealth(
            device_id="desktop_speaker",
            kind=DesktopDeviceKind.SPEAKER,
            state=EdgeAdapterState.SIMULATED if not required else EdgeAdapterState.DEGRADED,
            backend="stub_tts",
            available=not required,
            required=required,
            detail="fixture_stub_speaker",
        )


class FakePiperSpeakerOutput(FakeSpeakerOutput):
    pass


class FakeCameraCapture:
    source = DesktopCameraSource(
        configured_source="default",
        mode="webcam",
        available=True,
        note="fixture_camera_ready",
    )

    def health(self, *, required: bool = False) -> DesktopDeviceHealth:
        return DesktopDeviceHealth(
            device_id="desktop_camera",
            kind=DesktopDeviceKind.CAMERA,
            state=EdgeAdapterState.ACTIVE,
            backend="fake_camera",
            available=True,
            required=required,
            detail="fixture_camera_ready",
        )

    def capture_snapshot(self):
        captured_at = utc_now()
        return type(
            "CameraCapture",
            (),
            {
                "image_data_url": "data:image/png;base64," + base64.b64encode(b"fake-image").decode("ascii"),
                "source_frame": PerceptionSourceFrame(
                    source_kind="native_camera_snapshot",
                    source_label="fixture_camera",
                    frame_id=f"fixture-{captured_at.strftime('%Y%m%d%H%M%S')}",
                    mime_type="image/png",
                    captured_at=captured_at,
                ),
                "backend": "fake_camera",
            },
        )()


class FakeDeviceRegistry:
    def __init__(self) -> None:
        self.microphone_input = FakeMicrophoneInput()
        self.speaker_output = FakeSpeakerOutput()
        self.piper_speaker_output = FakePiperSpeakerOutput()
        self.stub_speaker_output = FakeStubSpeakerOutput()
        self.camera_capture = FakeCameraCapture()

    def describe(self, *, default_voice_mode: VoiceRuntimeMode):
        return [
            self.microphone_input.health(required=default_voice_mode == VoiceRuntimeMode.DESKTOP_NATIVE),
            self.speaker_output.health(
                required=default_voice_mode
                in {
                    VoiceRuntimeMode.DESKTOP_NATIVE,
                    VoiceRuntimeMode.MACOS_SAY,
                    VoiceRuntimeMode.BROWSER_LIVE_MACOS_SAY,
                }
            ),
            self.camera_capture.health(required=True),
        ]

    def capture_camera_snapshot(self, *, background: bool = False):
        del background
        return self.camera_capture.capture_snapshot()

    def selected_microphone_label(self) -> str:
        return "LG UltraFine Display Audio"

    def selected_camera_label(self) -> str:
        return "LG UltraFine Display Camera"

    def transcribe_local_audio_file(self, audio_path, *, locale: str | None = None):
        del audio_path, locale
        return {
            "transcript_text": "fixture browser transcript",
            "transcription_backend": "whisper_cpp_local",
        }

    def poll_open_mic(
        self,
        *,
        session_id: str,
        backend_candidates: tuple[str, ...],
        vad_silence_ms: int,
        vad_min_speech_ms: int,
    ):
        del session_id, backend_candidates, vad_silence_ms, vad_min_speech_ms
        captured_at = utc_now()
        return type(
            "OpenMicCaptureResult",
            (),
            {
                "captured_at": captured_at,
                "duration_seconds": 1.0,
                "speech_detected": False,
                "speech_ms": 0,
                "rms_level": 0.0,
                "transcript_text": None,
                "partial_transcript": None,
                "transcription_backend": "typed_input",
                "degraded_reason": None,
            },
        )()


def run_local_companion_checks(
    *,
    settings: Settings | None = None,
    output_dir: str | Path | None = None,
) -> DemoCheckSuiteRecord:
    runner = LocalCompanionCheckRunner(settings=settings, output_dir=output_dir)
    return runner.run()


class LocalCompanionCheckRunner:
    def __init__(self, *, settings: Settings | None = None, output_dir: str | Path | None = None) -> None:
        self.settings = settings or get_settings()
        self.output_dir = Path(output_dir or Path(self.settings.demo_check_dir) / "local_companion")
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
            ("mic_speaker_loop", "Native mic capture and local speaker playback complete a desktop turn.", self._check_mic_speaker_loop),
            ("webcam_grounded_reply", "The camera boundary can feed a grounded visual reply through the local runtime.", self._check_webcam_grounded_reply),
            ("browser_live_visual_turn", "Browser live speech plus camera returns a bounded grounded reply instead of stalling.", self._check_browser_live_visual_turn),
            ("profile_fallback", "Requested higher-tier backends degrade honestly into local fallback paths.", self._check_profile_fallback),
            ("memory_retrieval", "Local companion memory recalls prior user details and preferences.", self._check_memory_retrieval),
            ("relationship_continuity", "Companion continuity stays useful, bounded, and inspectable across sessions.", self._check_relationship_continuity),
            ("uncertainty_honesty", "Visual uncertainty stays explicit instead of turning into invented claims.", self._check_uncertainty_honesty),
            ("bodyless_virtual_body_continuity", "Bodyless and virtual-body modes preserve the same conversation path.", self._check_bodyless_virtual_body_continuity),
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

    def _check_mic_speaker_loop(self, *, check_name: str, description: str, check_dir: Path) -> DemoCheckResult:
        settings = self._runtime_settings(check_dir, {"blink_runtime_mode": RobotMode.DESKTOP_BODYLESS})
        with build_desktop_runtime(settings=settings, device_registry=FakeDeviceRegistry()) as runtime:
            result = runtime.submit_live_turn(
                session_id="local-companion-mic",
                user_id="local-companion-user",
                response_mode=ResponseMode.GUIDE,
                voice_mode=VoiceRuntimeMode.DESKTOP_NATIVE,
                speak_reply=True,
                capture_camera=False,
            )
            snapshot = runtime.snapshot(session_id="local-companion-mic", voice_mode=VoiceRuntimeMode.DESKTOP_NATIVE)
            episode = runtime.operator_console.export_session_episode(
                EpisodeExportSessionRequest(session_id="local-companion-mic", include_asset_refs=True)
            )
        passed = bool(
            result.interaction.success
            and result.interaction.voice_output is not None
            and result.interaction.voice_output.status == SpeechOutputStatus.COMPLETED
            and result.interaction.voice_output.transcript_text == "Where is the front desk?"
            and "front desk" in (result.interaction.response.reply_text or "").lower()
        )
        return self._finalize_result(
            check_dir=check_dir,
            result=DemoCheckResult(
                check_name=check_name,
                description=description,
                completed_at=utc_now(),
                passed=passed,
                session_id="local-companion-mic",
                backend_used=result.interaction.response.trace_id,
                reply_text=result.interaction.response.reply_text,
                latency_ms=result.interaction.latency_ms,
                notes=["voice_mode:desktop_native", "camera:false"],
            ),
            payloads={"interaction": result.interaction, "snapshot": snapshot, "episode": episode},
        )

    def _check_webcam_grounded_reply(self, *, check_name: str, description: str, check_dir: Path) -> DemoCheckResult:
        fixture_path = Path("src/embodied_stack/demo/data/perception_visible_sign_image.json").resolve()
        settings = self._runtime_settings(
            check_dir,
            {
                "blink_runtime_mode": RobotMode.DESKTOP_VIRTUAL_BODY,
                "blink_camera_source": f"fixture:{fixture_path}",
            },
        )
        with build_desktop_runtime(settings=settings) as runtime:
            capture = runtime.capture_camera_observation(
                session_id="local-companion-camera",
                user_id="local-companion-user",
            )
            interaction = runtime.submit_text(
                "What sign can you see right now?",
                session_id="local-companion-camera",
                user_id="local-companion-user",
                response_mode=ResponseMode.GUIDE,
                voice_mode=VoiceRuntimeMode.STUB_DEMO,
                speak_reply=False,
            )
            trace = runtime.orchestrator.get_trace(interaction.response.trace_id or "")
            snapshot = runtime.snapshot(session_id="local-companion-camera", voice_mode=VoiceRuntimeMode.STUB_DEMO)
            episode = runtime.operator_console.export_session_episode(
                EpisodeExportSessionRequest(session_id="local-companion-camera", include_asset_refs=True)
            )
        grounded_labels = {item.source_type.value for item in (trace.reasoning.grounding_sources if trace is not None else [])}
        passed = bool(
            interaction.success
            and ("workshop room" in (interaction.response.reply_text or "").lower() or "community events today" in (interaction.response.reply_text or "").lower())
            and grounded_labels.intersection({"perception", "perception_fact"})
            and snapshot.runtime.perception_freshness.status in {"fresh", "aging"}
        )
        return self._finalize_result(
            check_dir=check_dir,
            result=DemoCheckResult(
                check_name=check_name,
                description=description,
                completed_at=utc_now(),
                passed=passed,
                session_id="local-companion-camera",
                backend_used=trace.reasoning.engine if trace is not None else None,
                reply_text=interaction.response.reply_text,
                latency_ms=interaction.latency_ms,
                grounding_sources=trace.reasoning.grounding_sources if trace is not None else [],
                notes=[f"camera_source:{settings.blink_camera_source}"],
            ),
            payloads={"capture": capture, "interaction": interaction, "snapshot": snapshot, "episode": episode},
        )

    def _check_browser_live_visual_turn(self, *, check_name: str, description: str, check_dir: Path) -> DemoCheckResult:
        settings = self._runtime_settings(
            check_dir,
            {
                "blink_runtime_mode": RobotMode.DESKTOP_BODYLESS,
                "blink_browser_live_turn_timeout_seconds": 5.0,
                "blink_browser_live_visual_turn_timeout_seconds": 8.0,
                "blink_live_turn_diagnostic_dir": str(check_dir / "live_turn_failures"),
            },
        )
        with build_desktop_runtime(settings=settings, device_registry=FakeDeviceRegistry()) as runtime:
            with TestClient(runtime.app) as client:
                auth_status = client.get("/api/operator/auth/status")
                assert auth_status.status_code == 200
                auth_payload = auth_status.json()
                if auth_payload.get("enabled") and auth_payload.get("auth_mode") != "appliance_localhost_trusted":
                    login = client.post(
                        "/api/operator/auth/login",
                        json={"token": runtime.app.state.operator_auth.token},
                    )
                    assert login.status_code == 200
                response = client.post(
                    "/api/operator/text-turn",
                    json={
                        "session_id": "local-companion-browser-live",
                        "user_id": "local-companion-user",
                        "input_text": "What can you see from the cameras?",
                        "response_mode": "guide",
                        "voice_mode": "browser_live_macos_say",
                        "speak_reply": True,
                        "source": "browser_speech_recognition",
                        "camera_image_data_url": "data:image/jpeg;base64,ZmFrZQ==",
                        "camera_provider_mode": "ollama_vision",
                        "camera_source_frame": {
                            "source_kind": "browser_camera_snapshot",
                            "source_label": "operator_console_camera",
                            "frame_id": "browser-live-visual-check",
                            "mime_type": "image/jpeg",
                            "width_px": 640,
                            "height_px": 480,
                            "captured_at": utc_now().isoformat(),
                        },
                        "input_metadata": {
                            "capture_mode": "browser_microphone",
                            "transcription_backend": "browser_speech_recognition",
                            "browser_speech_recognition_ms": 120.0,
                            "client_submit_wall_time_ms": int(utc_now().timestamp() * 1000),
                        },
                    },
                )
                snapshot_response = client.get(
                    "/api/operator/snapshot",
                    params={"session_id": "local-companion-browser-live", "voice_mode": "browser_live_macos_say"},
                )
        payload = response.json()
        snapshot = snapshot_response.json()
        diagnostics = payload.get("live_turn_diagnostics") or {}
        passed = bool(
            response.status_code == 200
            and payload.get("response", {}).get("reply_text")
            and diagnostics.get("camera_refresh_skipped") is True
            and diagnostics.get("timeout_triggered") is False
            and diagnostics.get("total_ms") is not None
            and snapshot.get("runtime", {}).get("latest_live_turn_diagnostics", {}).get("source") == "browser_speech_recognition"
        )
        return self._finalize_result(
            check_dir=check_dir,
            result=DemoCheckResult(
                check_name=check_name,
                description=description,
                completed_at=utc_now(),
                passed=passed,
                session_id="local-companion-browser-live",
                backend_used=payload.get("response", {}).get("trace_id"),
                reply_text=payload.get("response", {}).get("reply_text"),
                latency_ms=payload.get("latency_ms"),
                notes=[
                    f"timeout_triggered={diagnostics.get('timeout_triggered')}",
                    f"camera_refresh_skipped={diagnostics.get('camera_refresh_skipped')}",
                ],
            ),
            payloads={"interaction": payload, "snapshot": snapshot},
        )

    def _check_profile_fallback(self, *, check_name: str, description: str, check_dir: Path) -> DemoCheckResult:
        settings = self._runtime_settings(
            check_dir,
            {
                "blink_runtime_mode": RobotMode.DESKTOP_BODYLESS,
                "blink_backend_profile": "cloud_best",
                "grsai_api_key": None,
                "openai_api_key": None,
                "perception_multimodal_api_key": None,
                "ollama_base_url": "http://127.0.0.1:9",
                "ollama_timeout_seconds": 0.1,
            },
        )
        with build_desktop_runtime(settings=settings) as runtime:
            interaction = runtime.submit_text(
                "Where is the front desk?",
                session_id="local-companion-fallback",
                user_id="local-companion-user",
                response_mode=ResponseMode.GUIDE,
                voice_mode=VoiceRuntimeMode.STUB_DEMO,
                speak_reply=False,
            )
            trace = runtime.orchestrator.get_trace(interaction.response.trace_id or "")
            snapshot = runtime.snapshot(session_id="local-companion-fallback", voice_mode=VoiceRuntimeMode.STUB_DEMO)
        passed = bool(
            interaction.success
            and trace is not None
            and snapshot.runtime.fallback_state.active
            and snapshot.runtime.fallback_state.fallback_backends
            and any(note.startswith("primary_failed:") for note in snapshot.runtime.fallback_state.notes)
        )
        return self._finalize_result(
            check_dir=check_dir,
            result=DemoCheckResult(
                check_name=check_name,
                description=description,
                completed_at=utc_now(),
                passed=passed,
                session_id="local-companion-fallback",
                backend_used=trace.reasoning.engine if trace is not None else None,
                reply_text=interaction.response.reply_text,
                latency_ms=interaction.latency_ms,
                notes=snapshot.runtime.fallback_state.notes,
            ),
            payloads={"interaction": interaction, "trace": trace, "snapshot": snapshot},
        )

    def _check_memory_retrieval(self, *, check_name: str, description: str, check_dir: Path) -> DemoCheckResult:
        settings = self._runtime_settings(check_dir, {"blink_runtime_mode": RobotMode.DESKTOP_BODYLESS})
        with build_desktop_runtime(settings=settings) as runtime:
            runtime.submit_text(
                "My name is Alex and I prefer the quiet route.",
                session_id="local-companion-memory",
                user_id="local-companion-user",
                response_mode=ResponseMode.GUIDE,
                voice_mode=VoiceRuntimeMode.STUB_DEMO,
                speak_reply=False,
            )
            remembered = runtime.submit_text(
                "What do you remember about me?",
                session_id="local-companion-memory",
                user_id="local-companion-user",
                response_mode=ResponseMode.GUIDE,
                voice_mode=VoiceRuntimeMode.STUB_DEMO,
                speak_reply=False,
            )
            snapshot = runtime.snapshot(session_id="local-companion-memory", voice_mode=VoiceRuntimeMode.STUB_DEMO)
            episode = runtime.operator_console.export_session_episode(
                EpisodeExportSessionRequest(session_id="local-companion-memory", include_asset_refs=True)
            )
        passed = bool(
            remembered.success
            and "alex" in (remembered.response.reply_text or "").lower()
            and "quiet route" in (remembered.response.reply_text or "").lower()
            and snapshot.runtime.memory_status.status == "grounded"
            and snapshot.runtime.memory_status.profile_memory_available
            and (
                snapshot.runtime.memory_status.semantic_memory_count >= 1
                or snapshot.runtime.memory_status.relationship_continuity.known_user
                or snapshot.runtime.memory_status.episodic_memory_count >= 1
            )
        )
        return self._finalize_result(
            check_dir=check_dir,
            result=DemoCheckResult(
                check_name=check_name,
                description=description,
                completed_at=utc_now(),
                passed=passed,
                session_id="local-companion-memory",
                backend_used=remembered.response.trace_id,
                reply_text=remembered.response.reply_text,
                latency_ms=remembered.latency_ms,
                notes=[f"memory_status:{snapshot.runtime.memory_status.status}"],
            ),
            payloads={"remembered": remembered, "snapshot": snapshot, "episode": episode},
        )

    def _check_relationship_continuity(self, *, check_name: str, description: str, check_dir: Path) -> DemoCheckResult:
        settings = self._runtime_settings(check_dir, {"blink_runtime_mode": RobotMode.DESKTOP_BODYLESS})
        with build_desktop_runtime(settings=settings) as runtime:
            runtime.submit_text(
                "My name is Alex. Keep it brief, use direct answers, and take it one step at a time.",
                session_id="local-companion-relationship-a",
                user_id="local-companion-user",
                response_mode=ResponseMode.GUIDE,
                voice_mode=VoiceRuntimeMode.STUB_DEMO,
                speak_reply=False,
            )
            runtime.submit_text(
                "Remind me to bring the badge tomorrow.",
                session_id="local-companion-relationship-a",
                user_id="local-companion-user",
                response_mode=ResponseMode.GUIDE,
                voice_mode=VoiceRuntimeMode.STUB_DEMO,
                speak_reply=False,
            )
            follow_up = runtime.submit_text(
                "What should we revisit?",
                session_id="local-companion-relationship-b",
                user_id="local-companion-user",
                response_mode=ResponseMode.GUIDE,
                voice_mode=VoiceRuntimeMode.STUB_DEMO,
                speak_reply=False,
            )
            snapshot = runtime.snapshot(session_id="local-companion-relationship-b", voice_mode=VoiceRuntimeMode.STUB_DEMO)
        reply = (follow_up.response.reply_text or "").lower()
        relationship = snapshot.runtime.memory_status.relationship_continuity
        passed = bool(
            follow_up.success
            and "badge" in reply
            and relationship.known_user
            and relationship.returning_user
            and relationship.planning_style == "one_step_at_a_time"
            and {"brief", "direct"}.issubset(set(relationship.tone_preferences))
            and "bring the badge" in relationship.open_follow_ups
            and "missed you" not in reply
            and "love" not in reply
        )
        return self._finalize_result(
            check_dir=check_dir,
            result=DemoCheckResult(
                check_name=check_name,
                description=description,
                completed_at=utc_now(),
                passed=passed,
                session_id="local-companion-relationship-b",
                backend_used=follow_up.response.trace_id,
                reply_text=follow_up.response.reply_text,
                latency_ms=follow_up.latency_ms,
                notes=[
                    f"relationship_known={relationship.known_user}",
                    f"open_follow_ups={len(relationship.open_follow_ups)}",
                ],
            ),
            payloads={"follow_up": follow_up, "snapshot": snapshot},
        )

    def _check_uncertainty_honesty(self, *, check_name: str, description: str, check_dir: Path) -> DemoCheckResult:
        settings = self._runtime_settings(check_dir, {"blink_runtime_mode": RobotMode.DESKTOP_BODYLESS})
        with build_desktop_runtime(settings=settings) as runtime:
            perception = runtime.submit_perception_probe(
                session_id="local-companion-uncertain",
                user_id="local-companion-user",
                provider_mode=PerceptionProviderMode.STUB,
            )
            interaction = runtime.submit_text(
                "What sign can you see right now?",
                session_id="local-companion-uncertain",
                user_id="local-companion-user",
                response_mode=ResponseMode.GUIDE,
                voice_mode=VoiceRuntimeMode.STUB_DEMO,
                speak_reply=False,
            )
            snapshot = runtime.snapshot(session_id="local-companion-uncertain", voice_mode=VoiceRuntimeMode.STUB_DEMO)
        reply = (interaction.response.reply_text or "").lower()
        passed = bool(
            perception.success
            and ("limited" in reply or "do not have" in reply or "cannot make confident" in reply)
            and snapshot.runtime.perception_freshness.limited_awareness
            and snapshot.runtime.perception_freshness.status in {"fresh", "aging"}
        )
        return self._finalize_result(
            check_dir=check_dir,
            result=DemoCheckResult(
                check_name=check_name,
                description=description,
                completed_at=utc_now(),
                passed=passed,
                session_id="local-companion-uncertain",
                backend_used=interaction.response.trace_id,
                reply_text=interaction.response.reply_text,
                latency_ms=interaction.latency_ms,
                notes=[f"perception_status:{snapshot.runtime.perception_status}"],
            ),
            payloads={"perception": perception, "interaction": interaction, "snapshot": snapshot},
        )

    def _check_bodyless_virtual_body_continuity(self, *, check_name: str, description: str, check_dir: Path) -> DemoCheckResult:
        settings_bodyless = self._runtime_settings(check_dir / "bodyless", {"blink_runtime_mode": RobotMode.DESKTOP_BODYLESS})
        settings_virtual = self._runtime_settings(check_dir / "virtual", {"blink_runtime_mode": RobotMode.DESKTOP_VIRTUAL_BODY})

        with build_desktop_runtime(settings=settings_bodyless) as runtime:
            bodyless = runtime.submit_text(
                "Where is the front desk?",
                session_id="local-companion-bodyless",
                user_id="local-companion-user",
                response_mode=ResponseMode.GUIDE,
                voice_mode=VoiceRuntimeMode.STUB_DEMO,
                speak_reply=False,
            )
            snapshot_bodyless = runtime.snapshot(session_id="local-companion-bodyless", voice_mode=VoiceRuntimeMode.STUB_DEMO)

        with build_desktop_runtime(settings=settings_virtual) as runtime:
            virtual = runtime.submit_text(
                "Where is the front desk?",
                session_id="local-companion-virtual",
                user_id="local-companion-user",
                response_mode=ResponseMode.GUIDE,
                voice_mode=VoiceRuntimeMode.STUB_DEMO,
                speak_reply=False,
            )
            snapshot_virtual = runtime.snapshot(session_id="local-companion-virtual", voice_mode=VoiceRuntimeMode.STUB_DEMO)

        passed = bool(
            bodyless.success
            and virtual.success
            and "front desk" in (bodyless.response.reply_text or "").lower()
            and "front desk" in (virtual.response.reply_text or "").lower()
            and snapshot_bodyless.runtime.embodiment_profile == "bodyless"
            and snapshot_virtual.runtime.embodiment_profile == "virtual_body"
        )
        return self._finalize_result(
            check_dir=check_dir,
            result=DemoCheckResult(
                check_name=check_name,
                description=description,
                completed_at=utc_now(),
                passed=passed,
                scenario_names=["bodyless", "virtual_body"],
                reply_text=virtual.response.reply_text,
                latency_ms=max(bodyless.latency_ms or 0.0, virtual.latency_ms or 0.0),
                notes=[
                    f"bodyless={snapshot_bodyless.runtime.body_status}",
                    f"virtual={snapshot_virtual.runtime.body_status}",
                ],
            ),
            payloads={
                "bodyless_interaction": bodyless,
                "bodyless_snapshot": snapshot_bodyless,
                "virtual_interaction": virtual,
                "virtual_snapshot": snapshot_virtual,
            },
        )

    def _runtime_settings(self, check_dir: Path, overrides: dict[str, object] | None = None) -> Settings:
        settings_data = self.settings.model_dump()
        settings_data.update(
            {
                "brain_store_path": str(check_dir / "brain_store.json"),
                "demo_report_dir": str(check_dir / "demo_runs"),
                "demo_check_dir": str(self.output_dir),
                "episode_export_dir": str(check_dir / "episodes"),
                "shift_report_dir": str(check_dir / "shift_reports"),
                "operator_auth_runtime_file": str(check_dir / "operator_auth.json"),
                "brain_voice_backend": "stub",
                "live_voice_default_mode": "stub_demo",
                "blink_model_profile": "desktop_local",
                "blink_voice_profile": "desktop_local",
                "blink_backend_profile": "offline_safe" if self.settings.brain_dialogue_backend == "rule_based" else settings_data.get("blink_backend_profile"),
            }
        )
        if overrides:
            settings_data.update(overrides)
        return Settings(_env_file=None, **settings_data)

    def _finalize_result(
        self,
        *,
        check_dir: Path,
        result: DemoCheckResult,
        payloads: dict[str, object],
    ) -> DemoCheckResult:
        artifact_files: dict[str, str] = {}
        for name, payload in payloads.items():
            if payload is None:
                continue
            path = check_dir / f"{name}.json"
            self._write_json(path, payload)
            artifact_files[name] = str(path)
        summary_path = check_dir / "summary.json"
        result.artifact_files = artifact_files
        self._write_json(summary_path, result)
        result.artifact_files["summary"] = str(summary_path)
        self._write_json(summary_path, result)
        return result

    def _write_json(self, path: Path, payload: object) -> None:
        write_json_atomic(path, self._normalize(payload))

    def _normalize(self, payload: object):
        if hasattr(payload, "model_dump"):
            return payload.model_dump(mode="json")
        if isinstance(payload, list):
            return [self._normalize(item) for item in payload]
        if isinstance(payload, dict):
            return {key: self._normalize(value) for key, value in payload.items()}
        return payload


def main() -> None:
    suite = run_local_companion_checks()
    print(
        json.dumps(
            {
                "suite_id": suite.suite_id,
                "passed": suite.passed,
                "check_count": len(suite.items),
                "passed_count": sum(1 for item in suite.items if item.passed),
                "artifact_dir": suite.artifact_dir,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
