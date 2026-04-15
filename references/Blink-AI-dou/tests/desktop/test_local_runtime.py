from __future__ import annotations

import base64
import json
from pathlib import Path
import time

from fastapi.testclient import TestClient

from embodied_stack.brain import app as brain_app
from embodied_stack.config import Settings
from embodied_stack.desktop.app import build_desktop_runtime
from embodied_stack.multimodal.camera import DesktopCameraSource
from embodied_stack.shared.models import (
    DesktopDeviceHealth,
    DesktopDeviceKind,
    EdgeAdapterState,
    PerceptionSnapshotStatus,
    PerceptionSourceFrame,
    RobotMode,
    SpeechOutputResult,
    SpeechOutputStatus,
    SpeechTranscriptRecord,
    VoiceRuntimeMode,
    utc_now,
)


def build_settings(tmp_path: Path, **overrides) -> Settings:
    return Settings(
        _env_file=None,
        brain_store_path=str(tmp_path / "brain_store.json"),
        demo_report_dir=str(tmp_path / "demo_runs"),
        demo_check_dir=str(tmp_path / "demo_checks"),
        episode_export_dir=str(tmp_path / "episodes"),
        shift_report_dir=str(tmp_path / "shift_reports"),
        perception_frame_dir=str(tmp_path / "perception_frames"),
        operator_auth_token="desktop-test-token",
        operator_auth_runtime_file=str(tmp_path / "operator_auth.json"),
        **overrides,
    )


class FakeMicrophoneInput:
    ffmpeg_path = "/usr/bin/ffmpeg"

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
            confidence=0.9,
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


class FailingSpeakerOutput(FakeSpeakerOutput):
    def speak(self, session_id: str, text: str | None, *, mode: VoiceRuntimeMode) -> SpeechOutputResult:
        del session_id, text, mode
        raise RuntimeError("fixture_tts_failure")


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

    def transcribe_local_audio_file(self, audio_path: Path, *, locale: str | None = None):
        del audio_path, locale
        return {
            "transcript_text": "hello from browser audio",
            "transcription_backend": "whisper_cpp_local",
        }


def test_desktop_local_runtime_supports_typed_input_in_bodyless_mode(tmp_path: Path):
    settings = build_settings(
        tmp_path,
        blink_runtime_mode=RobotMode.DESKTOP_BODYLESS,
        blink_model_profile="offline_stub",
        blink_voice_profile="offline_stub",
    )

    with build_desktop_runtime(settings=settings) as runtime:
        interaction = runtime.submit_text(
            "Hello there",
            session_id="desktop-bodyless",
            voice_mode=VoiceRuntimeMode.STUB_DEMO,
            speak_reply=False,
        )

    assert interaction.success is True
    assert interaction.session_id == "desktop-bodyless"
    assert interaction.telemetry.mode == RobotMode.DESKTOP_BODYLESS
    assert interaction.response.reply_text
    assert interaction.voice_output is not None
    assert interaction.voice_output.mode == VoiceRuntimeMode.STUB_DEMO


def test_submit_text_uses_typed_runtime_even_when_live_voice_mode_is_desktop_native(tmp_path: Path):
    settings = build_settings(
        tmp_path,
        blink_runtime_mode=RobotMode.DESKTOP_BODYLESS,
        blink_model_profile="offline_stub",
        blink_voice_profile="desktop_local",
    )
    device_registry = FakeDeviceRegistry()

    with build_desktop_runtime(settings=settings, device_registry=device_registry) as runtime:
        interaction = runtime.submit_text(
            "Hello from typed desktop mode",
            session_id="desktop-typed-native",
            voice_mode=VoiceRuntimeMode.DESKTOP_NATIVE,
            speak_reply=False,
        )

    assert interaction.success is True
    assert interaction.event.payload["text"] == "Hello from typed desktop mode"
    assert interaction.voice_output is not None
    assert interaction.voice_output.transcript_text == "Hello from typed desktop mode"


def test_browser_audio_turn_uses_local_transcription_and_shared_operator_path(tmp_path: Path, monkeypatch):
    settings = build_settings(
        tmp_path,
        blink_runtime_mode=RobotMode.DESKTOP_BODYLESS,
        blink_model_profile="offline_stub",
        blink_voice_profile="desktop_local",
    )
    device_registry = FakeDeviceRegistry()
    audio_dir = tmp_path / "browser-audio"
    audio_dir.mkdir()
    normalized_audio = audio_dir / "capture.wav"
    normalized_audio.write_bytes(b"fake-audio")

    monkeypatch.setattr(
        brain_app,
        "_decode_browser_audio_data_url",
        lambda data_url, mime_type=None: ("audio/webm", b"fake-webm"),
    )
    monkeypatch.setattr(
        brain_app,
        "_normalize_browser_audio_for_transcription",
        lambda payload, mime_type, device_registry: normalized_audio,
    )

    runtime = build_desktop_runtime(settings=settings, device_registry=device_registry)
    with TestClient(runtime.app) as client:
        login = client.post("/api/operator/auth/login", json={"token": settings.operator_auth_token})
        assert login.status_code == 200
        response = client.post(
            "/api/operator/browser-audio-turn",
            json={
                "session_id": "browser-audio-session",
                "input_metadata": {
                    "browser_device_id": "mic-lg",
                    "browser_device_label": "LG UltraFine Display Audio",
                },
                "audio_data_url": "data:audio/webm;base64,ZmFrZQ==",
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["transcript_text"] == "hello from browser audio"
    assert body["transcription_backend"] == "whisper_cpp_local"
    assert body["browser_device_label"] == "LG UltraFine Display Audio"
    assert body["interaction"]["session_id"] == "browser-audio-session"
    assert body["interaction"]["event"]["payload"]["text"] == "hello from browser audio"


def test_browser_audio_turn_refreshes_browser_camera_for_visual_queries(tmp_path: Path, monkeypatch):
    settings = build_settings(
        tmp_path,
        blink_runtime_mode=RobotMode.DESKTOP_BODYLESS,
        blink_model_profile="offline_stub",
        blink_voice_profile="desktop_local",
    )
    device_registry = FakeDeviceRegistry()
    audio_dir = tmp_path / "browser-audio-visual"
    audio_dir.mkdir()
    normalized_audio = audio_dir / "capture.wav"
    normalized_audio.write_bytes(b"fake-audio")

    monkeypatch.setattr(
        brain_app,
        "_decode_browser_audio_data_url",
        lambda data_url, mime_type=None: ("audio/webm", b"fake-webm"),
    )
    monkeypatch.setattr(
        brain_app,
        "_normalize_browser_audio_for_transcription",
        lambda payload, mime_type, device_registry: normalized_audio,
    )
    monkeypatch.setattr(
        device_registry,
        "transcribe_local_audio_file",
        lambda audio_path, locale=None: {
            "transcript_text": "What can you see from the camera right now?",
            "transcription_backend": "whisper_cpp_local",
        },
    )

    runtime = build_desktop_runtime(settings=settings, device_registry=device_registry)
    captured_refreshes: list[tuple[str, str, bool]] = []

    def record_snapshot(request):
        captured_refreshes.append((request.provider_mode.value, request.source, request.publish_events))
        return None

    monkeypatch.setattr(runtime.operator_console, "submit_perception_snapshot", record_snapshot)

    with TestClient(runtime.app) as client:
        login = client.post("/api/operator/auth/login", json={"token": settings.operator_auth_token})
        assert login.status_code == 200
        response = client.post(
            "/api/operator/browser-audio-turn",
            json={
                "session_id": "browser-audio-visual",
                "audio_data_url": "data:audio/webm;base64,ZmFrZQ==",
                "camera_image_data_url": "data:image/jpeg;base64,ZmFrZQ==",
                "camera_provider_mode": "ollama_vision",
                "camera_source_frame": {
                    "source_kind": "browser_camera_snapshot",
                    "source_label": "operator_console_camera",
                    "frame_id": "camera-voice-test",
                    "mime_type": "image/jpeg",
                    "width_px": 640,
                    "height_px": 480,
                    "captured_at": utc_now().isoformat(),
                },
            },
        )

    assert response.status_code == 200
    assert captured_refreshes == [("ollama_vision", "browser_live_visual_refresh", False)]


def test_browser_speech_turn_refreshes_camera_once_and_records_live_diagnostics(tmp_path: Path, monkeypatch):
    settings = build_settings(
        tmp_path,
        blink_runtime_mode=RobotMode.DESKTOP_BODYLESS,
        blink_model_profile="offline_stub",
        blink_voice_profile="desktop_local",
    )
    device_registry = FakeDeviceRegistry()
    runtime = build_desktop_runtime(settings=settings, device_registry=device_registry)
    captured_refreshes: list[tuple[str, bool]] = []

    def record_snapshot(request):
        captured_refreshes.append((request.source, request.publish_events))
        return None

    monkeypatch.setattr(runtime.operator_console, "submit_perception_snapshot", record_snapshot)

    with TestClient(runtime.app) as client:
        login = client.post("/api/operator/auth/login", json={"token": settings.operator_auth_token})
        assert login.status_code == 200
        response = client.post(
            "/api/operator/text-turn",
            json={
                "session_id": "browser-speech-visual",
                "input_text": "What can you see from the cameras?",
                "voice_mode": "browser_live_macos_say",
                "speak_reply": True,
                "source": "browser_speech_recognition",
                "camera_image_data_url": "data:image/jpeg;base64,ZmFrZQ==",
                "camera_provider_mode": "ollama_vision",
                "camera_source_frame": {
                    "source_kind": "browser_camera_snapshot",
                    "source_label": "operator_console_camera",
                    "frame_id": "camera-turn-visual",
                    "mime_type": "image/jpeg",
                    "width_px": 640,
                    "height_px": 480,
                    "captured_at": utc_now().isoformat(),
                },
                "input_metadata": {
                    "capture_mode": "browser_microphone",
                    "transcription_backend": "browser_speech_recognition",
                    "browser_speech_recognition_ms": 111.5,
                    "client_submit_wall_time_ms": int(time.time() * 1000),
                },
            },
        )

    assert response.status_code == 200
    assert captured_refreshes == [("browser_live_visual_refresh", False)]
    body = response.json()
    diagnostics = body["live_turn_diagnostics"]
    assert diagnostics["source"] == "browser_speech_recognition"
    assert diagnostics["visual_query"] is True
    assert diagnostics["camera_frame_attached"] is True
    assert diagnostics["camera_refresh_skipped"] is True
    assert diagnostics["camera_refresh_ms"] is not None
    assert diagnostics["browser_speech_recognition_ms"] == 111.5
    assert diagnostics["persistence_writes"] >= 1
    assert body["voice_output"]["live_turn_diagnostics"]["camera_refresh_skipped"] is True
    trace = runtime.orchestrator.get_trace(body["response"]["trace_id"])
    assert trace is not None
    assert trace.reasoning.live_turn_diagnostics is not None
    assert trace.reasoning.live_turn_diagnostics.camera_refresh_skipped is True


def test_browser_live_timeout_returns_504_and_timeout_artifact(tmp_path: Path, monkeypatch):
    diagnostic_dir = tmp_path / "live-turn-failures"
    settings = build_settings(
        tmp_path,
        blink_runtime_mode=RobotMode.DESKTOP_BODYLESS,
        blink_model_profile="offline_stub",
        blink_voice_profile="desktop_local",
        blink_browser_live_turn_timeout_seconds=0.01,
        blink_live_turn_diagnostic_dir=str(diagnostic_dir),
    )
    runtime = build_desktop_runtime(settings=settings, device_registry=FakeDeviceRegistry())

    def slow_submit(request):
        del request
        time.sleep(0.05)
        raise RuntimeError("should_timeout_before_completion")

    monkeypatch.setattr(runtime.operator_console, "submit_text_turn", slow_submit)

    with TestClient(runtime.app) as client:
        login = client.post("/api/operator/auth/login", json={"token": settings.operator_auth_token})
        assert login.status_code == 200
        response = client.post(
            "/api/operator/text-turn",
            json={
                "session_id": "browser-live-timeout",
                "input_text": "Hello there",
                "voice_mode": "browser_live",
                "speak_reply": False,
                "source": "browser_speech_recognition",
            },
        )

    assert response.status_code == 504
    detail = response.json()["detail"]
    assert detail["code"] == "browser_live_turn_timeout"
    artifact_path = Path(detail["artifact_path"])
    assert artifact_path.exists()
    latest = json.loads((diagnostic_dir / "latest.json").read_text(encoding="utf-8"))
    assert latest["diagnostics"]["timeout_triggered"] is True
    assert latest["diagnostics"]["stall_classification"] == "server_handler_stall"


def test_browser_live_tts_failure_does_not_block_text_reply(tmp_path: Path):
    settings = build_settings(
        tmp_path,
        blink_runtime_mode=RobotMode.DESKTOP_BODYLESS,
        blink_model_profile="offline_stub",
        blink_voice_profile="desktop_local",
    )

    class _FailingSpeakerRegistry(FakeDeviceRegistry):
        def __init__(self) -> None:
            super().__init__()
            self.speaker_output = FailingSpeakerOutput()

    runtime = build_desktop_runtime(settings=settings, device_registry=_FailingSpeakerRegistry())
    runtime.voice_manager.get_runtime(VoiceRuntimeMode.BROWSER_LIVE_MACOS_SAY).text_to_speech = FailingSpeakerOutput()

    with TestClient(runtime.app) as client:
        login = client.post("/api/operator/auth/login", json={"token": settings.operator_auth_token})
        assert login.status_code == 200
        response = client.post(
            "/api/operator/text-turn",
            json={
                "session_id": "browser-live-tts-failure",
                "input_text": "Hello there",
                "voice_mode": "browser_live_macos_say",
                "speak_reply": True,
                "source": "browser_speech_recognition",
                "input_metadata": {
                    "capture_mode": "browser_microphone",
                    "transcription_backend": "browser_speech_recognition",
                },
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["response"]["reply_text"]
    assert body["voice_output"]["status"] == "failed"
    assert body["voice_output"]["message"] == "reply_audio_failed"
    assert "tts_failed" in body["live_turn_diagnostics"]["notes"]


def test_provider_unavailable_profile_falls_back_honestly(tmp_path: Path):
    settings = build_settings(
        tmp_path,
        blink_runtime_mode=RobotMode.DESKTOP_BODYLESS,
        blink_model_profile="cloud_demo",
        blink_voice_profile="offline_stub",
        grsai_api_key=None,
        openai_api_key=None,
    )

    with build_desktop_runtime(settings=settings) as runtime:
        interaction = runtime.submit_text(
            "Where is the front desk?",
            session_id="desktop-provider-fallback",
            voice_mode=VoiceRuntimeMode.STUB_DEMO,
            speak_reply=False,
        )
        trace = runtime.orchestrator.get_trace(interaction.response.trace_id)
        snapshot = runtime.snapshot(session_id="desktop-provider-fallback", voice_mode=VoiceRuntimeMode.STUB_DEMO)

    assert interaction.success is True
    assert trace is not None
    assert trace.reasoning.engine == "rule_based"
    assert snapshot.runtime.provider_status == "fallback_ready"
    assert "dialogue, voice, perception" in (snapshot.runtime.provider_detail or "")
    assert snapshot.runtime.resolved_backend_profile == "cloud_best"
    assert interaction.response.reply_text


def test_perception_unavailable_falls_back_without_crashing(tmp_path: Path):
    settings = build_settings(
        tmp_path,
        blink_runtime_mode=RobotMode.DESKTOP_BODYLESS,
        blink_model_profile="cloud_demo",
        blink_voice_profile="offline_stub",
        perception_multimodal_api_key=None,
    )

    with build_desktop_runtime(settings=settings) as runtime:
        result = runtime.submit_perception_probe(session_id="desktop-perception-fallback")

    assert result.success is False
    assert result.snapshot.status == PerceptionSnapshotStatus.FAILED
    assert result.snapshot.limited_awareness is True
    assert result.snapshot.scene_summary is not None


def test_snapshot_reports_composed_demo_profile_and_provider_fallback(tmp_path: Path):
    settings = build_settings(
        tmp_path,
        blink_runtime_mode=RobotMode.DESKTOP_BODYLESS,
        blink_model_profile="desktop_local",
        blink_voice_profile="desktop_local",
        perception_multimodal_api_key=None,
    )

    with build_desktop_runtime(settings=settings) as runtime:
        snapshot = runtime.snapshot()

    assert snapshot.runtime.profile_summary == "companion_live + bodyless"
    assert snapshot.runtime.embodiment_profile == "bodyless"
    assert snapshot.runtime.provider_status == "hybrid_local_fallback"
    assert snapshot.runtime.body_status == "bodyless:ready"


def test_serial_body_without_live_transport_keeps_conversation_honest(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("embodied_stack.body.driver.DEFAULT_ARM_LEASE_PATH", tmp_path / "runtime" / "serial" / "live_motion_arm.json")
    settings = build_settings(
        tmp_path,
        blink_runtime_mode=RobotMode.DESKTOP_SERIAL_BODY,
        blink_body_driver="serial",
        blink_model_profile="offline_stub",
        blink_voice_profile="offline_stub",
        blink_serial_transport="live_serial",
        blink_serial_port=None,
    )

    with build_desktop_runtime(settings=settings) as runtime:
        interaction = runtime.submit_text(
            "Where is the quiet room?",
            session_id="desktop-serial-fallback",
            voice_mode=VoiceRuntimeMode.STUB_DEMO,
            speak_reply=False,
        )
        snapshot = runtime.snapshot(session_id="desktop-serial-fallback")

    assert "Quiet Room" in (interaction.response.reply_text or "")
    assert any(ack.status.value == "transport_error" for ack in interaction.command_acks)
    assert snapshot.runtime.embodiment_profile == "serial_body"
    assert snapshot.runtime.body_status.startswith("serial:degraded")
    assert snapshot.telemetry.body_state is not None
    assert snapshot.telemetry.body_state.transport_error is not None


def test_native_live_turn_uses_fake_devices_and_updates_snapshot(tmp_path: Path):
    settings = build_settings(
        tmp_path,
        blink_runtime_mode=RobotMode.DESKTOP_BODYLESS,
        blink_model_profile="desktop_local",
        blink_voice_profile="desktop_local",
        perception_multimodal_api_key=None,
    )
    device_registry = FakeDeviceRegistry()

    with build_desktop_runtime(settings=settings, device_registry=device_registry) as runtime:
        result = runtime.submit_live_turn(
            session_id="desktop-native-live",
            voice_mode=VoiceRuntimeMode.DESKTOP_NATIVE,
            speak_reply=False,
        )
        snapshot = runtime.snapshot(session_id="desktop-native-live", voice_mode=VoiceRuntimeMode.DESKTOP_NATIVE)

    assert result.camera_error is None
    assert result.perception_result is not None
    assert result.interaction.success is True
    assert result.interaction.event.source == "desktop_native_runtime"
    assert result.interaction.voice_output is not None
    assert result.interaction.voice_output.transcript_text == "Where is the front desk?"
    assert "front desk" in (result.interaction.response.reply_text or "").lower()
    assert snapshot.runtime.default_live_voice_mode == VoiceRuntimeMode.DESKTOP_NATIVE
    assert [item.kind.value for item in snapshot.runtime.device_health] == ["microphone", "speaker", "camera"]
    assert snapshot.latest_perception is not None
    assert snapshot.latest_perception.source_frame.source_kind == "native_camera_snapshot"
    persisted_path = Path(snapshot.latest_perception.source_frame.fixture_path or "")
    assert persisted_path.exists()
    assert persisted_path.read_bytes() == b"fake-image"
    assert (Path(settings.perception_frame_dir) / "latest_camera_snapshot.png").exists()
