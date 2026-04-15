from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from embodied_stack.config import Settings
from embodied_stack.desktop.app import build_desktop_runtime
from embodied_stack.demo.local_companion_checks import FakeDeviceRegistry, FakeSpeakerOutput
from embodied_stack.shared.models import SpeechOutputResult, SpeechOutputStatus, VoiceRuntimeMode, utc_now


def build_settings(tmp_path: Path, **overrides) -> Settings:
    return Settings(
        _env_file=None,
        brain_store_path=str(tmp_path / "brain_store.json"),
        demo_report_dir=str(tmp_path / "demo_runs"),
        demo_check_dir=str(tmp_path / "demo_checks"),
        episode_export_dir=str(tmp_path / "episodes"),
        shift_report_dir=str(tmp_path / "shift_reports"),
        operator_auth_token="desktop-test-token",
        operator_auth_runtime_file=str(tmp_path / "operator_auth.json"),
        blink_always_on_enabled=True,
        blink_audio_mode="open_mic",
        blink_tts_backend="macos_say",
        **overrides,
    )


class StatefulSpeakerOutput(FakeSpeakerOutput):
    def __init__(self) -> None:
        self._status = SpeechOutputStatus.IDLE
        self.cancel_calls = 0

    def force_speaking(self) -> None:
        self._status = SpeechOutputStatus.SPEAKING

    def speak(self, session_id: str, text: str | None, *, mode: VoiceRuntimeMode) -> SpeechOutputResult:
        self._status = SpeechOutputStatus.COMPLETED
        return super().speak(session_id, text, mode=mode)

    def get_state(self, session_id: str | None = None, *, mode: VoiceRuntimeMode) -> SpeechOutputResult:
        result = super().get_state(session_id, mode=mode)
        return result.model_copy(update={"status": self._status})

    def cancel(self, session_id: str | None = None, *, mode: VoiceRuntimeMode) -> SpeechOutputResult:
        self.cancel_calls += 1
        self._status = SpeechOutputStatus.INTERRUPTED
        return super().cancel(session_id, mode=mode)


class SequenceOpenMicRegistry(FakeDeviceRegistry):
    def __init__(self, results: list[SimpleNamespace]) -> None:
        super().__init__()
        self._results = results
        self._index = 0
        self.speaker_output = StatefulSpeakerOutput()
        self.piper_speaker_output = self.speaker_output

    def poll_open_mic(
        self,
        *,
        session_id: str,
        backend_candidates: tuple[str, ...],
        vad_silence_ms: int,
        vad_min_speech_ms: int,
    ):
        del session_id, backend_candidates, vad_silence_ms, vad_min_speech_ms
        item = self._results[min(self._index, len(self._results) - 1)]
        self._index += 1
        return item


def _speech_result(*, transcript_text: str | None, speech_detected: bool = True, backend: str = "whisper_cpp_local"):
    return SimpleNamespace(
        captured_at=utc_now(),
        duration_seconds=1.0,
        speech_detected=speech_detected,
        speech_ms=640 if speech_detected else 0,
        rms_level=0.55 if speech_detected else 0.0,
        transcript_text=transcript_text,
        partial_transcript=transcript_text[:40] if transcript_text else None,
        transcription_backend=backend,
        degraded_reason=None if transcript_text else "typed_input_required",
    )


def test_open_mic_supervisor_records_streaming_turn_states(tmp_path: Path):
    settings = build_settings(tmp_path, blink_model_profile="offline_stub")
    registry = SequenceOpenMicRegistry([_speech_result(transcript_text="Where is the front desk?")])
    runtime = build_desktop_runtime(settings=settings, device_registry=registry)
    session = runtime.ensure_session(session_id="open-mic-session")
    runtime.configure_companion_loop(
        session_id=session.session_id,
        voice_mode=VoiceRuntimeMode.OPEN_MIC_LOCAL,
        speak_enabled=True,
        audio_mode="open_mic",
    )

    runtime.run_supervisor_once()
    artifacts = runtime.supervisor.export_artifacts()
    states = [item["state"] for item in artifacts["audio_loop"]["history"]]
    snapshot = runtime.snapshot(session_id=session.session_id, voice_mode=VoiceRuntimeMode.OPEN_MIC_LOCAL)

    assert "capturing" in states
    assert "endpointing" in states
    assert "transcribing" in states
    assert states[-1] == "cooldown"
    assert snapshot.runtime.audio_mode.value == "open_mic"
    assert artifacts["partial_transcripts"]


def test_open_mic_barge_in_interrupts_current_speech(tmp_path: Path):
    settings = build_settings(tmp_path, blink_model_profile="offline_stub")
    registry = SequenceOpenMicRegistry([_speech_result(transcript_text="Sorry, one more thing.")])
    runtime = build_desktop_runtime(settings=settings, device_registry=registry)
    session = runtime.ensure_session(session_id="barge-in-session")
    runtime.configure_companion_loop(
        session_id=session.session_id,
        voice_mode=VoiceRuntimeMode.OPEN_MIC_LOCAL,
        speak_enabled=True,
        audio_mode="open_mic",
    )
    registry.speaker_output.force_speaking()

    runtime.run_supervisor_once()
    history = runtime.supervisor.export_artifacts()["audio_loop"]["history"]
    states = [item["state"] for item in history]
    presence_states = [item["state"] for item in runtime.supervisor.export_artifacts()["presence_runtime"]["history"]]

    assert "barge_in" in states
    assert "reengaging" in presence_states
    assert registry.speaker_output.cancel_calls == 1
