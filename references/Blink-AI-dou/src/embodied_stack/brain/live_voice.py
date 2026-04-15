from __future__ import annotations

from dataclasses import dataclass
import logging
from threading import RLock
from time import perf_counter
from typing import Callable, Protocol
from uuid import uuid4

from embodied_stack.backends.router import BackendRouter
from embodied_stack.desktop.devices import (
    DesktopDeviceRegistry,
    MacOSSpeakerOutputDevice,
    PiperSpeakerOutputDevice,
    StubSpeakerOutputDevice,
    build_desktop_device_registry,
)
from embodied_stack.config import Settings
from embodied_stack.observability import log_event
from embodied_stack.shared.models import (
    LiveTurnDiagnosticsRecord,
    LiveVoiceStateUpdateRequest,
    OperatorVoiceTurnRequest,
    RuntimeBackendKind,
    SpeechOutputResult,
    SpeechOutputStatus,
    SpeechTranscriptRecord,
    VoiceCancelResult,
    VoiceRuntimeMode,
    VoiceTurnRequest,
    VoiceTurnResult,
    utc_now,
)

logger = logging.getLogger(__name__)


class SpeechInputSource(Protocol):
    def capture(self, request: OperatorVoiceTurnRequest, session_id: str) -> SpeechTranscriptRecord:
        ...

    def cancel(self, session_id: str | None = None) -> None:
        ...


class SpeechToTextEngine(Protocol):
    def transcribe(self, transcript: SpeechTranscriptRecord) -> SpeechTranscriptRecord:
        ...


class TextToSpeechEngine(Protocol):
    def speak(self, session_id: str, text: str | None, *, mode: VoiceRuntimeMode) -> SpeechOutputResult:
        ...

    def get_state(self, session_id: str | None = None, *, mode: VoiceRuntimeMode) -> SpeechOutputResult:
        ...

    def cancel(self, session_id: str | None = None, *, mode: VoiceRuntimeMode) -> SpeechOutputResult:
        ...


class DirectTranscriptInputSource:
    def __init__(
        self,
        *,
        default_source: str,
        capture_mode: str,
        transcription_backend: str,
    ) -> None:
        self.default_source = default_source
        self.capture_mode = capture_mode
        self.transcription_backend = transcription_backend

    def capture(self, request: OperatorVoiceTurnRequest, session_id: str) -> SpeechTranscriptRecord:
        text = request.input_text.strip()
        if not text:
            raise ValueError("voice_input_text_required")

        metadata = dict(request.input_metadata)
        confidence = metadata.get("confidence")
        return SpeechTranscriptRecord(
            session_id=session_id,
            source=request.source or self.default_source,
            transcript_text=text,
            capture_mode=str(metadata.get("capture_mode", self.capture_mode)),
            transcription_backend=str(metadata.get("transcription_backend", self.transcription_backend)),
            confidence=float(confidence) if confidence is not None else None,
            metadata=metadata,
        )

    def cancel(self, session_id: str | None = None) -> None:
        del session_id


class PassThroughSpeechToTextEngine:
    def __init__(self, *, backend_name: str = "pass_through") -> None:
        self.backend_name = backend_name

    def transcribe(self, transcript: SpeechTranscriptRecord) -> SpeechTranscriptRecord:
        if not transcript.transcription_backend:
            transcript.transcription_backend = self.backend_name
        return transcript


StubTextToSpeechEngine = StubSpeakerOutputDevice
MacOSTextToSpeechEngine = MacOSSpeakerOutputDevice


@dataclass
class LiveVoiceTurnOutcome:
    transcript: SpeechTranscriptRecord
    voice_turn: VoiceTurnResult
    speech_output: SpeechOutputResult


class LiveVoiceRuntime:
    def __init__(
        self,
        *,
        mode: VoiceRuntimeMode,
        runtime_backend: str,
        input_backend: str,
        transcription_backend: str,
        output_backend: str,
        can_listen: bool | Callable[[], bool],
        input_source: SpeechInputSource,
        speech_to_text: SpeechToTextEngine,
        text_to_speech: TextToSpeechEngine,
        audio_available: bool | Callable[[], bool] | None = None,
    ) -> None:
        self.mode = mode
        self.runtime_backend = runtime_backend
        self.input_backend = input_backend
        self.transcription_backend = transcription_backend
        self.output_backend = output_backend
        self._can_listen = can_listen
        self.input_source = input_source
        self.speech_to_text = speech_to_text
        self.text_to_speech = text_to_speech
        self._audio_available = audio_available
        self._lock = RLock()
        self._states: dict[str, SpeechOutputResult] = {}

    def speak(self, session_id: str, text: str | None, *, mode: VoiceRuntimeMode | None = None) -> SpeechOutputResult:
        resolved_mode = self.mode if mode is None else mode
        try:
            tts_state = self.text_to_speech.speak(session_id, text, mode=resolved_mode)
        except Exception as exc:
            logger.exception("live_voice_direct_tts_failed")
            tts_state = SpeechOutputResult(
                session_id=session_id,
                backend=self.runtime_backend,
                output_backend=self.output_backend,
                mode=resolved_mode,
                audio_available=self._audio_output_available(),
                status=SpeechOutputStatus.FAILED,
                spoken_text=text,
                message="reply_audio_failed",
                error_code=str(exc),
            )
        current = self.get_state(session_id)
        merged = self._merge_state(current, tts_state, transcript_text=current.transcript_text)
        self._store_state(merged)
        return merged

    def handle_turn(
        self,
        request: OperatorVoiceTurnRequest,
        turn_handler: Callable[[VoiceTurnRequest], VoiceTurnResult],
        *,
        state_observer: Callable[[SpeechOutputResult], None] | None = None,
        reply_ready_observer: Callable[[str | None, bool], None] | None = None,
    ) -> LiveVoiceTurnOutcome:
        total_started = perf_counter()
        voice_turn_id = f"live-voice-{uuid4().hex[:8]}"
        session_id = request.session_id or "console-session"
        diagnostics = LiveTurnDiagnosticsRecord(
            source=request.source,
            visual_query=bool(request.input_metadata.get("visual_query")) if isinstance(request.input_metadata, dict) else False,
            camera_frame_attached=bool(getattr(request, "camera_image_data_url", None)),
            spoken_reply_requested=bool(request.speak_reply),
            browser_speech_recognition_ms=_coerce_float(request.input_metadata.get("browser_speech_recognition_ms")),
            browser_camera_capture_ms=_coerce_float(request.input_metadata.get("browser_camera_capture_ms")),
            server_ingress_ms=_coerce_float(request.input_metadata.get("server_ingress_ms")),
        )
        listening_supported = self._listening_supported()
        initial_status = (
            SpeechOutputStatus.LISTENING
            if listening_supported and not request.input_text.strip()
            else SpeechOutputStatus.TRANSCRIBING
        )
        initial_state = self._base_state(session_id).model_copy(
            update={
                "status": initial_status,
                "transcript_text": request.input_text.strip() or None,
                "message": "capturing_live_audio" if initial_status == SpeechOutputStatus.LISTENING else "processing_live_input",
                "updated_at": utc_now(),
            }
        )
        self._store_state(initial_state)
        if state_observer is not None:
            state_observer(initial_state)
        captured = self.input_source.capture(request, session_id)
        stt_started = perf_counter()
        transcript = self.speech_to_text.transcribe(captured)
        stt_runtime_ms = round((perf_counter() - stt_started) * 1000.0, 2)
        transcript_stt_ms = _coerce_float(transcript.metadata.get("stt_latency_ms")) if transcript.metadata else None
        diagnostics.stt_backend = transcript.transcription_backend
        diagnostics.stt_ms = (
            transcript_stt_ms
            if transcript_stt_ms is not None
            else diagnostics.browser_speech_recognition_ms
            if diagnostics.browser_speech_recognition_ms is not None
            else stt_runtime_ms
        )
        log_event(
            logger,
            logging.INFO,
            "live_voice_transcript_ready",
            voice_turn_id=voice_turn_id,
            session_id=session_id,
            capture_mode=transcript.capture_mode,
            transcription_backend=transcript.transcription_backend,
        )
        thinking_state = self._base_state(session_id).model_copy(
            update={
                "status": SpeechOutputStatus.THINKING,
                "transcript_text": transcript.transcript_text,
                "message": "thinking",
                "live_turn_diagnostics": diagnostics,
                "updated_at": utc_now(),
            }
        )
        self._store_state(thinking_state)
        if state_observer is not None:
            state_observer(thinking_state)
        turn_started = perf_counter()
        voice_turn = turn_handler(
            VoiceTurnRequest(
                session_id=session_id,
                user_id=request.user_id,
                input_text=transcript.transcript_text,
                response_mode=request.response_mode,
                source=transcript.source,
                input_metadata={
                    "capture_mode": transcript.capture_mode,
                    "transcription_backend": transcript.transcription_backend,
                    "confidence": transcript.confidence,
                    **transcript.metadata,
                },
            )
        )
        diagnostics.live_voice_runtime_ms = round((perf_counter() - turn_started) * 1000.0, 2)
        log_event(
            logger,
            logging.INFO,
            "live_voice_turn_completed",
            voice_turn_id=voice_turn_id,
            session_id=session_id,
            trace_id=voice_turn.response.trace_id,
            command_count=len(voice_turn.response.commands),
        )
        tts_started = perf_counter()
        if reply_ready_observer is not None:
            reply_ready_observer(voice_turn.response.reply_text, bool(request.speak_reply))
        if request.speak_reply:
            try:
                speech_output = self.text_to_speech.speak(
                    session_id,
                    voice_turn.response.reply_text,
                    mode=self.mode if request.voice_mode is None else request.voice_mode,
                )
            except Exception as exc:
                logger.exception("live_voice_tts_failed")
                speech_output = SpeechOutputResult(
                    session_id=session_id,
                    backend=self.runtime_backend,
                    output_backend=self.output_backend,
                    mode=self.mode,
                    audio_available=self._audio_output_available(),
                    status=SpeechOutputStatus.FAILED,
                    spoken_text=voice_turn.response.reply_text,
                    message="reply_audio_failed",
                    error_code=str(exc),
                )
                diagnostics.notes.append("tts_failed")
        else:
            speech_output = SpeechOutputResult(
                session_id=session_id,
                backend=self.runtime_backend,
                output_backend="disabled_tts",
                mode=self.mode,
                audio_available=False,
                status=SpeechOutputStatus.SKIPPED,
                spoken_text=voice_turn.response.reply_text,
                message="reply_audio_disabled",
            )
        diagnostics.tts_launch_ms = round((perf_counter() - tts_started) * 1000.0, 2)
        diagnostics.tts_start_ms = diagnostics.tts_launch_ms
        diagnostics.total_ms = round((perf_counter() - total_started) * 1000.0, 2)
        diagnostics.end_to_end_turn_ms = diagnostics.total_ms
        final_state = self._merge_state(
            self._base_state(session_id),
            speech_output,
            transcript_text=transcript.transcript_text,
        )
        final_state.live_turn_diagnostics = diagnostics
        self._store_state(final_state)
        if state_observer is not None:
            state_observer(final_state)
        log_event(
            logger,
            logging.INFO,
            "live_voice_output_ready",
            voice_turn_id=voice_turn_id,
            session_id=session_id,
            trace_id=voice_turn.response.trace_id,
            audio_available=final_state.audio_available,
            output_status=final_state.status.value,
        )
        return LiveVoiceTurnOutcome(
            transcript=transcript,
            voice_turn=voice_turn.model_copy(update={"live_turn_diagnostics": diagnostics}),
            speech_output=final_state,
        )

    def update_state(self, request: LiveVoiceStateUpdateRequest, session_id: str) -> SpeechOutputResult:
        current = self.get_state(session_id)
        updated = current.model_copy(
            update={
                "backend": self.runtime_backend,
                "mode": request.voice_mode,
                "status": request.status,
                "message": request.message,
                "transcript_text": request.transcript_text or current.transcript_text,
                "input_backend": request.input_backend or current.input_backend or self.input_backend,
                "transcription_backend": request.transcription_backend or current.transcription_backend or self.transcription_backend,
                "output_backend": request.output_backend or current.output_backend or self.output_backend,
                "error_code": request.metadata.get("error_code") if request.metadata else current.error_code,
                "updated_at": utc_now(),
            }
        )
        self._store_state(updated)
        return updated

    def cancel(self, session_id: str | None = None) -> VoiceCancelResult:
        self.input_source.cancel(session_id)
        tts_state = self.text_to_speech.cancel(session_id, mode=self.mode)
        if session_id is None:
            return VoiceCancelResult(ok=True, session_id=session_id, state=tts_state)

        current = self.get_state(session_id)
        if current.status in {SpeechOutputStatus.LISTENING, SpeechOutputStatus.TRANSCRIBING, SpeechOutputStatus.THINKING}:
            cancelled = current.model_copy(
                update={
                    "status": SpeechOutputStatus.INTERRUPTED,
                    "message": "live_input_cancelled",
                    "updated_at": utc_now(),
                }
            )
        else:
            cancelled = self._merge_state(current, tts_state, transcript_text=current.transcript_text)
        self._store_state(cancelled)
        return VoiceCancelResult(ok=True, session_id=session_id, state=cancelled)

    def get_state(self, session_id: str | None = None) -> SpeechOutputResult:
        if session_id is None:
            return self._base_state(None)

        with self._lock:
            current = self._states.get(session_id)
        if current is None:
            current = self._base_state(session_id)

        tts_state = self.text_to_speech.get_state(session_id, mode=self.mode)
        if tts_state.status in {
            SpeechOutputStatus.SPEAKING,
            SpeechOutputStatus.COMPLETED,
            SpeechOutputStatus.FAILED,
            SpeechOutputStatus.INTERRUPTED,
        }:
            merged = self._merge_state(current, tts_state, transcript_text=current.transcript_text)
            self._store_state(merged)
            return merged
        return current

    def _base_state(self, session_id: str | None) -> SpeechOutputResult:
        return SpeechOutputResult(
            session_id=session_id,
            backend=self.runtime_backend,
            mode=self.mode,
            audio_available=self._audio_output_available(),
            input_backend=self.input_backend,
            transcription_backend=self.transcription_backend,
            output_backend=self.output_backend,
            can_listen=self._listening_supported(),
            can_cancel=True,
            status=SpeechOutputStatus.IDLE,
            message="idle",
        )

    def _merge_state(
        self,
        base: SpeechOutputResult,
        update: SpeechOutputResult,
        *,
        transcript_text: str | None,
    ) -> SpeechOutputResult:
        return base.model_copy(
            update={
                "backend": self.runtime_backend,
                "mode": self.mode,
                "audio_available": update.audio_available,
                "input_backend": base.input_backend or self.input_backend,
                "transcription_backend": base.transcription_backend or self.transcription_backend,
                "output_backend": update.output_backend or base.output_backend or self.output_backend,
                "transcript_text": transcript_text,
                "status": update.status,
                "spoken_text": update.spoken_text,
                "message": update.message,
                "error_code": update.error_code,
                "updated_at": utc_now(),
                "can_listen": self._listening_supported(),
                "can_cancel": True,
            }
        )

    def _store_state(self, state: SpeechOutputResult) -> None:
        with self._lock:
            self._states[state.session_id or "default"] = state

    def _listening_supported(self) -> bool:
        return self._can_listen() if callable(self._can_listen) else bool(self._can_listen)

    def _audio_output_available(self) -> bool:
        if self._audio_available is None:
            return self.mode in {
                VoiceRuntimeMode.DESKTOP_NATIVE,
                VoiceRuntimeMode.OPEN_MIC_LOCAL,
                VoiceRuntimeMode.MACOS_SAY,
                VoiceRuntimeMode.BROWSER_LIVE_MACOS_SAY,
            }
        return self._audio_available() if callable(self._audio_available) else bool(self._audio_available)


def _coerce_float(value: object) -> float | None:
    if value is None or value == "":
        return None
    try:
        return round(float(value), 2)
    except (TypeError, ValueError):
        return None


class LiveVoiceRuntimeManager:
    def __init__(
        self,
        *,
        settings: Settings | None = None,
        device_registry: DesktopDeviceRegistry | None = None,
        backend_router: BackendRouter | None = None,
        macos_voice_name: str = "Samantha",
        macos_rate: int = 185,
    ) -> None:
        self.settings = settings or Settings(
            _env_file=None,
            macos_tts_voice=macos_voice_name,
            macos_tts_rate=macos_rate,
        )
        self.device_registry = device_registry or build_desktop_device_registry(self.settings)
        selected_stt_backend = (
            backend_router.selected_backend_id(RuntimeBackendKind.SPEECH_TO_TEXT)
            if backend_router is not None
            else ("whisper_cpp_local" if self.settings.blink_audio_mode == "open_mic" else "apple_speech_local")
        )
        selected_tts_backend = (
            backend_router.selected_backend_id(RuntimeBackendKind.TEXT_TO_SPEECH)
            if backend_router is not None
            else (self.settings.blink_tts_backend or "macos_say")
        )
        speaker_output = self._speaker_for_backend(selected_tts_backend)
        stub_speaker_output = self.device_registry.stub_speaker_output
        self._runtimes = {
            VoiceRuntimeMode.STUB_DEMO: LiveVoiceRuntime(
                mode=VoiceRuntimeMode.STUB_DEMO,
                runtime_backend="stub_demo",
                input_backend="typed_input",
                transcription_backend="pass_through",
                output_backend="stub_tts",
                can_listen=False,
                input_source=DirectTranscriptInputSource(
                    default_source="operator_console",
                    capture_mode="typed_input",
                    transcription_backend="pass_through",
                ),
                speech_to_text=PassThroughSpeechToTextEngine(backend_name="pass_through"),
                text_to_speech=stub_speaker_output,
                audio_available=False,
            ),
            VoiceRuntimeMode.DESKTOP_NATIVE: LiveVoiceRuntime(
                mode=VoiceRuntimeMode.DESKTOP_NATIVE,
                runtime_backend="desktop_native_live",
                input_backend="desktop_microphone",
                transcription_backend="apple_speech",
                output_backend=selected_tts_backend,
                can_listen=lambda: self.device_registry.microphone_input.health(required=True).available,
                input_source=self.device_registry.microphone_input,
                speech_to_text=PassThroughSpeechToTextEngine(backend_name="apple_speech"),
                text_to_speech=speaker_output,
                audio_available=lambda: self._speaker_for_backend(selected_tts_backend).health(required=True).available,
            ),
            VoiceRuntimeMode.OPEN_MIC_LOCAL: LiveVoiceRuntime(
                mode=VoiceRuntimeMode.OPEN_MIC_LOCAL,
                runtime_backend="open_mic_local",
                input_backend="open_mic_supervisor",
                transcription_backend=selected_stt_backend,
                output_backend=selected_tts_backend,
                can_listen=lambda: self.device_registry.microphone_input.health(required=True).available and selected_stt_backend != "typed_input",
                input_source=DirectTranscriptInputSource(
                    default_source="open_mic_supervisor",
                    capture_mode="open_mic_supervisor",
                    transcription_backend=selected_stt_backend,
                ),
                speech_to_text=PassThroughSpeechToTextEngine(backend_name=selected_stt_backend),
                text_to_speech=speaker_output,
                audio_available=lambda: self._speaker_for_backend(selected_tts_backend).health(required=True).available,
            ),
            VoiceRuntimeMode.MACOS_SAY: LiveVoiceRuntime(
                mode=VoiceRuntimeMode.MACOS_SAY,
                runtime_backend="macos_say_live",
                input_backend="typed_input",
                transcription_backend="pass_through",
                output_backend=selected_tts_backend,
                can_listen=False,
                input_source=DirectTranscriptInputSource(
                    default_source="operator_console",
                    capture_mode="typed_input",
                    transcription_backend="pass_through",
                ),
                speech_to_text=PassThroughSpeechToTextEngine(backend_name="pass_through"),
                text_to_speech=speaker_output,
                audio_available=lambda: self._speaker_for_backend(selected_tts_backend).health(required=True).available,
            ),
            VoiceRuntimeMode.BROWSER_LIVE: LiveVoiceRuntime(
                mode=VoiceRuntimeMode.BROWSER_LIVE,
                runtime_backend="browser_live",
                input_backend="browser_microphone",
                transcription_backend="browser_speech_recognition",
                output_backend="stub_tts",
                can_listen=True,
                input_source=DirectTranscriptInputSource(
                    default_source="browser_speech_recognition",
                    capture_mode="browser_microphone",
                    transcription_backend="browser_speech_recognition",
                ),
                speech_to_text=PassThroughSpeechToTextEngine(backend_name="browser_speech_recognition"),
                text_to_speech=stub_speaker_output,
                audio_available=False,
            ),
            VoiceRuntimeMode.BROWSER_LIVE_MACOS_SAY: LiveVoiceRuntime(
                mode=VoiceRuntimeMode.BROWSER_LIVE_MACOS_SAY,
                runtime_backend="browser_live_macos_say",
                input_backend="browser_microphone",
                transcription_backend="browser_speech_recognition",
                output_backend="macos_say",
                can_listen=True,
                input_source=DirectTranscriptInputSource(
                    default_source="browser_speech_recognition",
                    capture_mode="browser_microphone",
                    transcription_backend="browser_speech_recognition",
                ),
                speech_to_text=PassThroughSpeechToTextEngine(backend_name="browser_speech_recognition"),
                text_to_speech=speaker_output,
                audio_available=lambda: self.device_registry.speaker_output.health(required=True).available,
            ),
        }

    def get_runtime(
        self,
        mode: VoiceRuntimeMode,
        *,
        voice_name: str | None = None,
        rate: int | None = None,
    ) -> LiveVoiceRuntime:
        runtime = self._runtimes[mode]
        if voice_name is None and rate is None:
            return runtime
        if runtime.output_backend != "macos_say":
            return runtime
        speaker_output = MacOSSpeakerOutputDevice(
            voice_name=voice_name or self.settings.macos_tts_voice,
            rate=rate or self.settings.macos_tts_rate,
        )
        speaker_output.requested_output_device = self.settings.blink_speaker_device
        return LiveVoiceRuntime(
            mode=runtime.mode,
            runtime_backend=runtime.runtime_backend,
            input_backend=runtime.input_backend,
            transcription_backend=runtime.transcription_backend,
            output_backend="macos_say",
            can_listen=runtime._can_listen,
            input_source=runtime.input_source,
            speech_to_text=runtime.speech_to_text,
            text_to_speech=speaker_output,
            audio_available=runtime._audio_available,
        )

    def get_state(self, mode: VoiceRuntimeMode, session_id: str | None = None) -> SpeechOutputResult:
        return self.get_runtime(mode).get_state(session_id)

    def update_state(self, mode: VoiceRuntimeMode, request: LiveVoiceStateUpdateRequest, session_id: str) -> SpeechOutputResult:
        return self.get_runtime(mode).update_state(request, session_id)

    def cancel(self, mode: VoiceRuntimeMode, session_id: str | None = None) -> VoiceCancelResult:
        return self.get_runtime(mode).cancel(session_id)

    def _speaker_for_backend(self, backend_id: str):
        if backend_id == "piper_local":
            return self.device_registry.piper_speaker_output
        if backend_id == "macos_say":
            return self.device_registry.speaker_output
        return self.device_registry.stub_speaker_output
