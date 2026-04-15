from __future__ import annotations

import array
import base64
import io
import json
import re
import shutil
import subprocess
import tempfile
import wave
from datetime import datetime
from dataclasses import dataclass
from pathlib import Path
from threading import RLock
from time import monotonic, perf_counter

from PIL import Image, ImageStat

from embodied_stack.backends.local_paths import resolve_whisper_cpp_binary_path, resolve_whisper_cpp_model_path
from embodied_stack.config import Settings
from embodied_stack.desktop.device_health import (
    DEVICE_REASON_FALLBACK_ACTIVE,
    DEVICE_REASON_OK,
    DEVICE_REASON_UNSUPPORTED_ROUTING,
    build_device_health,
    device_reason_code_for_error,
)
from embodied_stack.multimodal.camera import DesktopCameraSource, describe_camera_source
from embodied_stack.shared.models import (
    DesktopDeviceHealth,
    DesktopDeviceKind,
    EdgeAdapterState,
    PerceptionSourceFrame,
    SpeechOutputResult,
    SpeechOutputStatus,
    SpeechTranscriptRecord,
    VoiceRuntimeMode,
    utc_now,
)


_DEVICE_LINE_RE = re.compile(r"\[(\d+)\] (.+)$")
_FFMPEG_CAMERA_FORMAT_PRIORITY = ("bgr0", "0rgb", "nv12", "uyvy422", "yuyv422")
_FFMPEG_UNDEREXPOSED_MEAN_THRESHOLD = 12.0
_FFMPEG_WARMUP_SEEK_SECONDS = 0.8
_FFMPEG_WARMUP_TIMEOUT_SECONDS = 12.0


def _repo_root_from_source(source_path: Path) -> Path:
    return source_path.resolve().parents[4]


def _native_tools_runtime_dir(source_path: Path) -> Path:
    runtime_dir = _repo_root_from_source(source_path) / "runtime" / "native_tools"
    runtime_dir.mkdir(parents=True, exist_ok=True)
    return runtime_dir


class DesktopDeviceError(RuntimeError):
    def __init__(self, classification: str, detail: str | None = None) -> None:
        self.classification = classification
        self.detail = detail
        super().__init__(f"{classification}:{detail}" if detail else classification)


@dataclass(frozen=True)
class FFmpegAVFoundationDevice:
    index: int
    label: str
    kind: str


@dataclass(frozen=True)
class ResolvedAVFoundationSelection:
    selected: FFmpegAVFoundationDevice | None
    configured: str
    preset: str
    resolution_note: str
    fallback_used: bool = False


@dataclass(frozen=True)
class DesktopCameraCapture:
    image_data_url: str
    source_frame: PerceptionSourceFrame
    backend: str
    warmup_retry_used: bool = False


@dataclass(frozen=True)
class CapturedAudioChunk:
    audio_path: Path
    captured_at: datetime
    duration_seconds: float
    device_label: str


@dataclass(frozen=True)
class OpenMicCaptureResult:
    captured_at: datetime
    duration_seconds: float
    speech_detected: bool
    speech_ms: int = 0
    rms_level: float = 0.0
    transcript_text: str | None = None
    partial_transcript: str | None = None
    transcription_backend: str | None = None
    transcription_latency_ms: float | None = None
    degraded_reason: str | None = None


class AppleSpeechTranscriber:
    def __init__(self, *, source_path: Path) -> None:
        self.source_path = source_path
        self.swiftc_path = shutil.which("swiftc")
        self._lock = RLock()

    def available(self) -> bool:
        return bool(self.swiftc_path and self.source_path.exists())

    def transcribe(self, audio_path: Path, *, locale: str) -> dict[str, object]:
        binary_path = self._ensure_binary()
        try:
            completed = subprocess.run(
                [str(binary_path), str(audio_path), locale],
                check=False,
                capture_output=True,
                text=True,
                timeout=25.0,
            )
        except subprocess.TimeoutExpired as exc:
            raise DesktopDeviceError("apple_speech_timeout") from exc

        if completed.returncode != 0:
            detail = completed.stderr.strip() or completed.stdout.strip() or "speech_transcriber_failed"
            raise DesktopDeviceError("apple_speech_failed", detail)

        try:
            payload = json.loads(completed.stdout.strip() or "{}")
        except ValueError as exc:
            raise DesktopDeviceError("apple_speech_invalid_json", completed.stdout.strip()) from exc
        if not payload.get("ok"):
            raise DesktopDeviceError(
                str(payload.get("error_code") or "apple_speech_failed"),
                str(payload.get("message") or payload.get("detail") or "speech_transcriber_failed"),
            )
        return payload

    def _ensure_binary(self) -> Path:
        if not self.available():
            raise DesktopDeviceError("apple_speech_unavailable", str(self.source_path))

        runtime_dir = _native_tools_runtime_dir(self.source_path)
        binary_path = runtime_dir / "apple_speech_transcribe"

        with self._lock:
            needs_build = not binary_path.exists() or binary_path.stat().st_mtime < self.source_path.stat().st_mtime
            if not needs_build:
                return binary_path

            completed = subprocess.run(
                [str(self.swiftc_path), str(self.source_path), "-o", str(binary_path)],
                check=False,
                capture_output=True,
                text=True,
                timeout=30.0,
            )
            if completed.returncode != 0:
                detail = completed.stderr.strip() or completed.stdout.strip() or "swiftc_build_failed"
                raise DesktopDeviceError("apple_speech_compile_failed", detail)
        return binary_path


class WhisperCppTranscriber:
    def __init__(self, *, settings: Settings) -> None:
        self.settings = settings
        self.binary_path = resolve_whisper_cpp_binary_path(settings)

    def available(self) -> bool:
        model_path = self._model_path()
        return bool(self.binary_path and model_path and model_path.exists())

    def transcribe(self, audio_path: Path, *, locale: str) -> dict[str, object]:
        model_path = self._model_path()
        if not self.binary_path or model_path is None or not model_path.exists():
            raise DesktopDeviceError("whisper_cpp_unavailable", str(model_path or "model_missing"))

        language = (locale.split("-", 1)[0] or "en").lower()
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_prefix = Path(tmp_dir) / "whisper_chunk"
            command = [
                str(self.binary_path),
                "-m",
                str(model_path),
                "-f",
                str(audio_path),
                "-l",
                language,
                "-nt",
                "-otxt",
                "-of",
                str(output_prefix),
            ]
            try:
                completed = subprocess.run(
                    command,
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=self.settings.whisper_cpp_timeout_seconds,
                )
            except subprocess.TimeoutExpired as exc:
                raise DesktopDeviceError("whisper_cpp_timeout") from exc

            transcript_text = ""
            txt_path = output_prefix.with_suffix(".txt")
            if txt_path.exists():
                transcript_text = txt_path.read_text(encoding="utf-8").strip()
            if not transcript_text:
                transcript_text = _extract_whisper_stdout(completed.stdout, completed.stderr)
            if completed.returncode != 0:
                detail = completed.stderr.strip() or completed.stdout.strip() or "whisper_cpp_failed"
                raise DesktopDeviceError("whisper_cpp_failed", detail)
            if not transcript_text:
                raise DesktopDeviceError("whisper_cpp_empty_transcript")

        return {
            "ok": True,
            "transcript_text": transcript_text,
            "transcription_backend": "whisper_cpp_local",
        }

    def _model_path(self) -> Path | None:
        return resolve_whisper_cpp_model_path(self.settings)


class AppleCameraSnapshotHelper:
    def __init__(self, *, source_path: Path) -> None:
        self.source_path = source_path
        self.swiftc_path = shutil.which("swiftc")
        self.codesign_path = shutil.which("codesign")
        self._lock = RLock()

    def available(self) -> bool:
        return bool(self.swiftc_path and self.source_path.exists())

    def capture(self, output_path: Path, *, preferred_label: str | None = None) -> dict[str, object]:
        args = [str(output_path)]
        if preferred_label:
            args.append(preferred_label)
        return self._run_helper(args, timeout_seconds=20.0)

    def probe(self, *, preferred_label: str | None = None) -> dict[str, object]:
        args = ["--probe"]
        if preferred_label:
            args.append(preferred_label)
        return self._run_helper(args, timeout_seconds=10.0)

    def _run_helper(self, args: list[str], *, timeout_seconds: float) -> dict[str, object]:
        binary_path = self._ensure_binary()
        command = [str(binary_path), *args]
        try:
            completed = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
            )
        except subprocess.TimeoutExpired as exc:
            raise DesktopDeviceError("desktop_camera_capture_timeout") from exc

        stdout = completed.stdout.strip()
        stderr = completed.stderr.strip()
        try:
            payload = json.loads(stdout or "{}")
        except ValueError:
            payload = None
        if payload is not None:
            if payload.get("ok"):
                return payload
            raise DesktopDeviceError(
                str(payload.get("error_code") or "desktop_camera_capture_failed"),
                str(payload.get("message") or payload.get("detail") or stderr or stdout or "camera_snapshot_helper_failed"),
            )
        if completed.returncode != 0:
            detail = stderr or stdout or "camera_snapshot_helper_failed"
            raise DesktopDeviceError("desktop_camera_capture_failed", detail)
        try:
            payload = json.loads(stdout or "{}")
        except ValueError as exc:
            raise DesktopDeviceError("desktop_camera_capture_invalid_json", stdout) from exc
        if not payload.get("ok"):
            raise DesktopDeviceError(
                str(payload.get("error_code") or "desktop_camera_capture_failed"),
                str(payload.get("message") or payload.get("detail") or stderr or stdout or "camera_snapshot_helper_failed"),
            )
        return payload

    def _ensure_binary(self) -> Path:
        if not self.available():
            raise DesktopDeviceError("desktop_camera_helper_unavailable", str(self.source_path))

        runtime_dir = _native_tools_runtime_dir(self.source_path)
        bundle_dir = runtime_dir / "BlinkCameraHelper.app"
        contents_dir = bundle_dir / "Contents"
        macos_dir = contents_dir / "MacOS"
        info_plist = contents_dir / "Info.plist"
        binary_path = macos_dir / "BlinkCameraHelper"

        with self._lock:
            needs_build = (
                not binary_path.exists()
                or not info_plist.exists()
                or binary_path.stat().st_mtime < self.source_path.stat().st_mtime
            )
            if not needs_build:
                return binary_path

            macos_dir.mkdir(parents=True, exist_ok=True)
            info_plist.write_text(_camera_helper_info_plist(), encoding="utf-8")
            completed = subprocess.run(
                [str(self.swiftc_path), str(self.source_path), "-o", str(binary_path)],
                check=False,
                capture_output=True,
                text=True,
                timeout=30.0,
            )
            if completed.returncode != 0:
                detail = completed.stderr.strip() or completed.stdout.strip() or "swiftc_build_failed"
                raise DesktopDeviceError("desktop_camera_helper_compile_failed", detail)
            if self.codesign_path:
                subprocess.run(
                    [self.codesign_path, "--force", "--deep", "-s", "-", str(bundle_dir)],
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=20.0,
                )
        return binary_path


def _camera_helper_info_plist() -> str:
    return """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key>
  <string>BlinkCameraHelper</string>
  <key>CFBundleDisplayName</key>
  <string>BlinkCameraHelper</string>
  <key>CFBundleIdentifier</key>
  <string>com.blinkai.camerahelper</string>
  <key>CFBundleExecutable</key>
  <string>BlinkCameraHelper</string>
  <key>CFBundlePackageType</key>
  <string>APPL</string>
  <key>CFBundleVersion</key>
  <string>1</string>
  <key>CFBundleShortVersionString</key>
  <string>1.0</string>
  <key>NSCameraUsageDescription</key>
  <string>Blink-AI uses the camera for local scene understanding and operator-triggered snapshots.</string>
</dict>
</plist>
"""


class MacOSNativeMicrophoneInput:
    def __init__(
        self,
        *,
        settings: Settings,
        transcriber: AppleSpeechTranscriber,
        whisper_transcriber: WhisperCppTranscriber | None = None,
        default_source: str = "desktop_microphone",
    ) -> None:
        self.settings = settings
        self.transcriber = transcriber
        self.whisper_transcriber = whisper_transcriber
        self.default_source = default_source
        self.ffmpeg_path = shutil.which("ffmpeg")
        self._lock = RLock()
        self._active_process: subprocess.Popen[str] | None = None

    def health(self, *, required: bool = False) -> DesktopDeviceHealth:
        detail = self._base_detail()
        state = EdgeAdapterState.ACTIVE
        available = True
        selection_note = None
        selected_label = None
        configured_label = (self.settings.blink_mic_device or "default").strip() or "default"
        reason_code = DEVICE_REASON_OK
        fallback_active = False

        try:
            selection = self._select_audio_device()
            device = selection.selected if hasattr(selection, "selected") else selection
            resolution_note = selection.resolution_note if hasattr(selection, "resolution_note") else "legacy_selection"
            selected_label = device.label
            selection_note = resolution_note
            detail = f"{detail}; device={device.label}; selection={resolution_note}"
        except DesktopDeviceError as exc:
            available = False
            detail = exc.detail or detail
            state = EdgeAdapterState.UNAVAILABLE if required else EdgeAdapterState.DEGRADED
            fallback_active = not required
            reason_code = device_reason_code_for_error(exc.classification, fallback_active=fallback_active)

        if not self.ffmpeg_path:
            available = False
            state = EdgeAdapterState.UNAVAILABLE if required else EdgeAdapterState.DEGRADED
            detail = "ffmpeg_not_available_for_microphone_capture"
            fallback_active = not required
            reason_code = DEVICE_REASON_FALLBACK_ACTIVE if fallback_active else device_reason_code_for_error("ffmpeg_missing")
        elif not (self.transcriber.available() or (self.whisper_transcriber and self.whisper_transcriber.available())):
            available = False
            state = EdgeAdapterState.UNAVAILABLE if required else EdgeAdapterState.DEGRADED
            detail = "local_speech_transcriber_unavailable"
            fallback_active = not required
            reason_code = DEVICE_REASON_FALLBACK_ACTIVE if fallback_active else device_reason_code_for_error("transcriber_unavailable")

        return build_device_health(
            device_id="desktop_microphone",
            kind=DesktopDeviceKind.MICROPHONE,
            state=state,
            backend="ffmpeg_avfoundation+local_stt",
            available=available,
            required=required,
            detail=detail,
            configured_label=configured_label,
            selected_label=selected_label,
            reason_code=reason_code,
            selection_note=selection_note,
            fallback_active=fallback_active,
        )

    def capture(self, request, session_id: str) -> SpeechTranscriptRecord:
        chunk = self.capture_audio_chunk(duration_seconds=self.settings.blink_native_capture_seconds, session_id=session_id)
        try:
            transcription_started = perf_counter()
            transcript_payload = self._transcribe_with_fallback(
                chunk.audio_path,
                locale=self.settings.blink_native_transcription_locale,
            )
            transcription_latency_ms = round((perf_counter() - transcription_started) * 1000.0, 2)
            transcript_text = str(transcript_payload.get("transcript_text") or "").strip()
            if not transcript_text:
                raise ValueError("desktop_microphone_no_speech_detected")

            metadata = dict(request.input_metadata)
            metadata.update(
                {
                    "capture_mode": "desktop_microphone",
                    "audio_capture_backend": "ffmpeg_avfoundation",
                    "audio_device": chunk.device_label,
                    "transcription_backend": transcript_payload.get("transcription_backend", "apple_speech"),
                    "transcription_requested_backend": self.settings.blink_stt_backend or "apple_speech_local",
                    "stt_latency_ms": transcription_latency_ms,
                    "captured_audio_format": "wav_pcm_s16le_16khz_mono",
                }
            )
            confidence = transcript_payload.get("confidence")
            return SpeechTranscriptRecord(
                session_id=session_id,
                source=request.source or self.default_source,
                transcript_text=transcript_text,
                capture_mode="desktop_microphone",
                transcription_backend=str(transcript_payload.get("transcription_backend") or "apple_speech"),
                confidence=float(confidence) if isinstance(confidence, (int, float)) else None,
                metadata=metadata,
            )
        finally:
            chunk.audio_path.unlink(missing_ok=True)

    def capture_audio_chunk(self, *, duration_seconds: float, session_id: str | None = None) -> CapturedAudioChunk:
        del session_id
        if not self.ffmpeg_path:
            raise ValueError("desktop_microphone_ffmpeg_unavailable")

        selection = self._select_audio_device()
        device = selection.selected if hasattr(selection, "selected") else selection
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as handle:
            audio_path = Path(handle.name)

        command = [
            self.ffmpeg_path,
            "-loglevel",
            "error",
            "-f",
            "avfoundation",
            "-i",
            f":{device.index}",
            "-t",
            str(duration_seconds),
            "-ac",
            "1",
            "-ar",
            "16000",
            "-c:a",
            "pcm_s16le",
            "-y",
            str(audio_path),
        ]
        process: subprocess.Popen[str] | None = None
        try:
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            with self._lock:
                self._active_process = process
            stdout, stderr = process.communicate(timeout=duration_seconds + 8.0)
            if process.returncode != 0:
                detail = stderr.strip() or stdout.strip() or "microphone_capture_failed"
                raise ValueError(f"desktop_microphone_capture_failed:{detail}")
            if not audio_path.exists() or audio_path.stat().st_size == 0:
                raise ValueError("desktop_microphone_capture_empty")
            return CapturedAudioChunk(
                audio_path=audio_path,
                captured_at=utc_now(),
                duration_seconds=duration_seconds,
                device_label=device.label,
            )
        except subprocess.TimeoutExpired:
            self.cancel()
            raise ValueError("desktop_microphone_capture_timeout")
        finally:
            with self._lock:
                self._active_process = None

    def transcribe_audio_file(self, audio_path: Path, *, backend_id: str, locale: str) -> dict[str, object]:
        if backend_id == "apple_speech_local":
            return self.transcriber.transcribe(audio_path, locale=locale)
        if backend_id == "whisper_cpp_local":
            if self.whisper_transcriber is None:
                raise ValueError("unsupported_transcription_backend:whisper_cpp_local")
            return self.whisper_transcriber.transcribe(audio_path, locale=locale)
        raise ValueError(f"unsupported_transcription_backend:{backend_id}")

    def transcribe_local_audio_file(self, audio_path: Path, *, locale: str | None = None) -> dict[str, object]:
        return self._transcribe_with_fallback(
            audio_path,
            locale=locale or self.settings.blink_native_transcription_locale,
        )

    def cancel(self, session_id: str | None = None) -> None:
        del session_id
        with self._lock:
            process = self._active_process
            self._active_process = None
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=1.0)
            except subprocess.TimeoutExpired:
                process.kill()

    def _select_audio_device(self) -> ResolvedAVFoundationSelection:
        devices = list_avfoundation_devices(ffmpeg_path=self.ffmpeg_path)
        configured = (self.settings.blink_mic_device or "default").strip()
        preset = (self.settings.blink_device_preset or "auto").strip() or "auto"
        selection = resolve_avfoundation_device(
            configured=configured,
            devices=devices["audio"],
            prefixes=("microphone", "audio", "mic"),
            preset=preset,
        )
        if selection.selected is None:
            raise DesktopDeviceError("desktop_microphone_not_found", configured)
        return selection

    def selected_device_label(self) -> str | None:
        try:
            return self._select_audio_device().selected.label
        except DesktopDeviceError:
            return None

    def _base_detail(self) -> str:
        if not self.ffmpeg_path:
            return "ffmpeg_not_available_for_microphone_capture"
        apple_ready = self.transcriber.available()
        whisper_ready = bool(self.whisper_transcriber and self.whisper_transcriber.available())
        if apple_ready and whisper_ready:
            return "native_mac_microphone_ready:apple_speech+whisper_cpp"
        if apple_ready:
            return "native_mac_microphone_ready:apple_speech"
        if whisper_ready:
            return "native_mac_microphone_ready:whisper_cpp"
        return "local_speech_transcriber_unavailable"

    def _transcribe_with_fallback(self, audio_path: Path, *, locale: str) -> dict[str, object]:
        candidates: list[str] = []
        preferred_backend = (self.settings.blink_stt_backend or "").strip()
        if preferred_backend in {"apple_speech_local", "whisper_cpp_local"}:
            candidates.append(preferred_backend)
        if "apple_speech_local" not in candidates:
            candidates.append("apple_speech_local")
        if "whisper_cpp_local" not in candidates:
            candidates.append("whisper_cpp_local")

        last_error: Exception | None = None
        for backend_id in candidates:
            try:
                return self.transcribe_audio_file(audio_path, backend_id=backend_id, locale=locale)
            except (DesktopDeviceError, ValueError) as exc:
                last_error = exc
                continue
        if last_error is not None:
            raise last_error
        raise DesktopDeviceError("local_speech_transcriber_unavailable")


class StubSpeakerOutputDevice:
    def health(self, *, required: bool = False) -> DesktopDeviceHealth:
        fallback_active = not required
        return build_device_health(
            device_id="desktop_speaker",
            kind=DesktopDeviceKind.SPEAKER,
            state=EdgeAdapterState.SIMULATED if not required else EdgeAdapterState.DEGRADED,
            backend="stub_tts",
            available=not required,
            required=required,
            detail="stubbed_speaker_output",
            configured_label="system_default",
            selected_label="system_default",
            reason_code=DEVICE_REASON_FALLBACK_ACTIVE if fallback_active else device_reason_code_for_error("stub_speaker_unavailable"),
            selection_note="stubbed_output",
            fallback_active=fallback_active,
        )

    def speak(self, session_id: str, text: str | None, *, mode: VoiceRuntimeMode) -> SpeechOutputResult:
        if not text:
            return SpeechOutputResult(
                session_id=session_id,
                backend="stub_demo",
                output_backend="stub_tts",
                mode=mode,
                audio_available=False,
                status=SpeechOutputStatus.SKIPPED,
                message="no_reply_text",
            )
        return SpeechOutputResult(
            session_id=session_id,
            backend="stub_demo",
            output_backend="stub_tts",
            mode=mode,
            audio_available=False,
            status=SpeechOutputStatus.SIMULATED,
            spoken_text=text,
            message="stub_demo_no_audio",
        )

    def get_state(self, session_id: str | None = None, *, mode: VoiceRuntimeMode) -> SpeechOutputResult:
        return SpeechOutputResult(
            session_id=session_id,
            backend="stub_demo",
            output_backend="stub_tts",
            mode=mode,
            audio_available=False,
            status=SpeechOutputStatus.IDLE,
            message="stub_demo_idle",
        )

    def cancel(self, session_id: str | None = None, *, mode: VoiceRuntimeMode) -> SpeechOutputResult:
        return SpeechOutputResult(
            session_id=session_id,
            backend="stub_demo",
            output_backend="stub_tts",
            mode=mode,
            audio_available=False,
            status=SpeechOutputStatus.INTERRUPTED,
            message="stub_demo_cancelled",
        )


class MacOSSpeakerOutputDevice:
    def __init__(self, *, voice_name: str = "Samantha", rate: int = 185) -> None:
        self.voice_name = voice_name
        self.rate = rate
        self.say_path = shutil.which("say")
        self._lock = RLock()
        self._processes: dict[str, subprocess.Popen[str]] = {}
        self._states: dict[str, SpeechOutputResult] = {}

    def health(self, *, required: bool = False) -> DesktopDeviceHealth:
        available = bool(self.say_path)
        requested_output = getattr(self, "requested_output_device", "system_default")
        unsupported_routing = available and requested_output not in {"", "default", "system_default"}
        return build_device_health(
            device_id="desktop_speaker",
            kind=DesktopDeviceKind.SPEAKER,
            state=EdgeAdapterState.ACTIVE if available else (EdgeAdapterState.UNAVAILABLE if required else EdgeAdapterState.DEGRADED),
            backend="macos_say",
            available=available,
            required=required,
            detail=(
                f"voice={self.voice_name}; output=system_default; requested_output={requested_output}; selection_supported=false"
                if available
                else "say_command_unavailable"
            ),
            configured_label=requested_output if requested_output != "default" else "system_default",
            selected_label="system_default" if available else None,
            reason_code=(
                device_reason_code_for_error("speaker_routing_unsupported", unsupported_routing=True)
                if unsupported_routing
                else (DEVICE_REASON_OK if available else device_reason_code_for_error("say_command_unavailable"))
            ),
            selection_note="system_default_only",
            fallback_active=not available and not required,
        )

    def speak(self, session_id: str, text: str | None, *, mode: VoiceRuntimeMode) -> SpeechOutputResult:
        if not text:
            return SpeechOutputResult(
                session_id=session_id,
                backend="macos_say",
                output_backend="macos_say",
                mode=mode,
                audio_available=False,
                status=SpeechOutputStatus.SKIPPED,
                message="no_reply_text",
            )

        if not self.say_path:
            state = SpeechOutputResult(
                session_id=session_id,
                backend="macos_say",
                output_backend="macos_say",
                mode=mode,
                audio_available=False,
                status=SpeechOutputStatus.FAILED,
                spoken_text=text,
                message="say_command_unavailable",
                error_code="say_command_unavailable",
            )
            with self._lock:
                self._states[session_id] = state
            return state

        self.cancel(session_id, mode=mode)
        process = subprocess.Popen(
            [self.say_path, "-v", self.voice_name, "-r", str(self.rate), text],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        state = SpeechOutputResult(
            session_id=session_id,
            backend="macos_say",
            output_backend="macos_say",
            mode=mode,
            audio_available=True,
            status=SpeechOutputStatus.SPEAKING,
            spoken_text=text,
            message=f"speaking_with_{self.voice_name}",
        )
        with self._lock:
            self._processes[session_id] = process
            self._states[session_id] = state
        return state

    def get_state(self, session_id: str | None = None, *, mode: VoiceRuntimeMode) -> SpeechOutputResult:
        if session_id is None:
            return SpeechOutputResult(
                backend="macos_say",
                output_backend="macos_say",
                mode=mode,
                audio_available=bool(self.say_path),
                status=SpeechOutputStatus.IDLE,
                message="no_session_selected",
            )

        with self._lock:
            state = self._states.get(session_id)
            process = self._processes.get(session_id)

        if state is None:
            return SpeechOutputResult(
                session_id=session_id,
                backend="macos_say",
                output_backend="macos_say",
                mode=mode,
                audio_available=bool(self.say_path),
                status=SpeechOutputStatus.IDLE,
                message="idle",
            )

        if process is not None:
            if process.poll() is None:
                return state
            with self._lock:
                self._processes.pop(session_id, None)
                completed = state.model_copy(
                    update={
                        "status": SpeechOutputStatus.COMPLETED,
                        "message": "speech_completed",
                        "updated_at": utc_now(),
                    }
                )
                self._states[session_id] = completed
                return completed

        return state

    def cancel(self, session_id: str | None = None, *, mode: VoiceRuntimeMode) -> SpeechOutputResult:
        if session_id is None:
            return SpeechOutputResult(
                backend="macos_say",
                output_backend="macos_say",
                mode=mode,
                audio_available=bool(self.say_path),
                status=SpeechOutputStatus.IDLE,
                message="no_session_selected",
            )

        with self._lock:
            process = self._processes.pop(session_id, None)
            current = self._states.get(session_id)

        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=1.0)
            except subprocess.TimeoutExpired:
                process.kill()
            state = (current or SpeechOutputResult(session_id=session_id)).model_copy(
                update={
                    "backend": "macos_say",
                    "output_backend": "macos_say",
                    "mode": mode,
                    "audio_available": bool(self.say_path),
                    "status": SpeechOutputStatus.INTERRUPTED,
                    "message": "speech_cancelled",
                    "updated_at": utc_now(),
                }
            )
            with self._lock:
                self._states[session_id] = state
            return state

        return (current or SpeechOutputResult(session_id=session_id)).model_copy(
            update={
                "backend": "macos_say",
                "output_backend": "macos_say",
                "mode": mode,
                "audio_available": bool(self.say_path),
                "status": SpeechOutputStatus.IDLE,
                "message": "nothing_to_cancel",
                "updated_at": utc_now(),
            }
        )


class PiperSpeakerOutputDevice:
    def __init__(self, *, settings: Settings) -> None:
        self.settings = settings
        self.binary_path = settings.piper_binary or shutil.which("piper")
        self.afplay_path = shutil.which("afplay")
        self._lock = RLock()
        self._processes: dict[str, subprocess.Popen[str]] = {}
        self._states: dict[str, SpeechOutputResult] = {}
        self._files: dict[str, Path] = {}

    def health(self, *, required: bool = False) -> DesktopDeviceHealth:
        available = bool(self.binary_path and self.afplay_path and self.settings.piper_model_path)
        return build_device_health(
            device_id="desktop_speaker",
            kind=DesktopDeviceKind.SPEAKER,
            state=EdgeAdapterState.ACTIVE if available else (EdgeAdapterState.UNAVAILABLE if required else EdgeAdapterState.DEGRADED),
            backend="piper_local",
            available=available,
            required=required,
            detail=self.settings.piper_model_path if available else "piper_local_unavailable",
            configured_label="system_default",
            selected_label="system_default" if available else None,
            reason_code=DEVICE_REASON_OK if available else device_reason_code_for_error("piper_local_unavailable", fallback_active=not required),
            selection_note="system_default_only",
            fallback_active=not available and not required,
        )

    def speak(self, session_id: str, text: str | None, *, mode: VoiceRuntimeMode) -> SpeechOutputResult:
        if not text:
            return SpeechOutputResult(
                session_id=session_id,
                backend="piper_local",
                output_backend="piper_local",
                mode=mode,
                audio_available=False,
                status=SpeechOutputStatus.SKIPPED,
                message="no_reply_text",
            )
        if not (self.binary_path and self.afplay_path and self.settings.piper_model_path):
            state = SpeechOutputResult(
                session_id=session_id,
                backend="piper_local",
                output_backend="piper_local",
                mode=mode,
                audio_available=False,
                status=SpeechOutputStatus.FAILED,
                spoken_text=text,
                message="piper_local_unavailable",
                error_code="piper_local_unavailable",
            )
            with self._lock:
                self._states[session_id] = state
            return state

        self.cancel(session_id, mode=mode)
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as handle:
            output_path = Path(handle.name)
        try:
            completed = subprocess.run(
                [self.binary_path, "--model", self.settings.piper_model_path, "--output_file", str(output_path)],
                input=text,
                capture_output=True,
                text=True,
                check=False,
                timeout=self.settings.piper_timeout_seconds,
            )
        except subprocess.TimeoutExpired:
            output_path.unlink(missing_ok=True)
            state = SpeechOutputResult(
                session_id=session_id,
                backend="piper_local",
                output_backend="piper_local",
                mode=mode,
                audio_available=False,
                status=SpeechOutputStatus.FAILED,
                spoken_text=text,
                message="piper_timeout",
                error_code="piper_timeout",
            )
            with self._lock:
                self._states[session_id] = state
            return state

        if completed.returncode != 0 or not output_path.exists() or output_path.stat().st_size == 0:
            output_path.unlink(missing_ok=True)
            state = SpeechOutputResult(
                session_id=session_id,
                backend="piper_local",
                output_backend="piper_local",
                mode=mode,
                audio_available=False,
                status=SpeechOutputStatus.FAILED,
                spoken_text=text,
                message=completed.stderr.strip() or completed.stdout.strip() or "piper_failed",
                error_code="piper_failed",
            )
            with self._lock:
                self._states[session_id] = state
            return state

        process = subprocess.Popen(
            [self.afplay_path, str(output_path)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        state = SpeechOutputResult(
            session_id=session_id,
            backend="piper_local",
            output_backend="piper_local",
            mode=mode,
            audio_available=True,
            status=SpeechOutputStatus.SPEAKING,
            spoken_text=text,
            message="speaking_with_piper",
        )
        with self._lock:
            self._files[session_id] = output_path
            self._processes[session_id] = process
            self._states[session_id] = state
        return state

    def get_state(self, session_id: str | None = None, *, mode: VoiceRuntimeMode) -> SpeechOutputResult:
        if session_id is None:
            return SpeechOutputResult(
                backend="piper_local",
                output_backend="piper_local",
                mode=mode,
                audio_available=bool(self.binary_path and self.afplay_path),
                status=SpeechOutputStatus.IDLE,
                message="no_session_selected",
            )
        with self._lock:
            state = self._states.get(session_id)
            process = self._processes.get(session_id)
            output_path = self._files.get(session_id)
        if state is None:
            return SpeechOutputResult(
                session_id=session_id,
                backend="piper_local",
                output_backend="piper_local",
                mode=mode,
                audio_available=bool(self.binary_path and self.afplay_path),
                status=SpeechOutputStatus.IDLE,
                message="idle",
            )
        if process is not None:
            if process.poll() is None:
                return state
            with self._lock:
                self._processes.pop(session_id, None)
                self._files.pop(session_id, None)
                completed = state.model_copy(
                    update={
                        "status": SpeechOutputStatus.COMPLETED,
                        "message": "speech_completed",
                        "updated_at": utc_now(),
                    }
                )
                self._states[session_id] = completed
            if output_path is not None:
                output_path.unlink(missing_ok=True)
            return completed
        return state

    def cancel(self, session_id: str | None = None, *, mode: VoiceRuntimeMode) -> SpeechOutputResult:
        if session_id is None:
            return SpeechOutputResult(
                backend="piper_local",
                output_backend="piper_local",
                mode=mode,
                audio_available=bool(self.binary_path and self.afplay_path),
                status=SpeechOutputStatus.IDLE,
                message="no_session_selected",
            )
        with self._lock:
            process = self._processes.pop(session_id, None)
            current = self._states.get(session_id)
            output_path = self._files.pop(session_id, None)
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=1.0)
            except subprocess.TimeoutExpired:
                process.kill()
            if output_path is not None:
                output_path.unlink(missing_ok=True)
            state = (current or SpeechOutputResult(session_id=session_id)).model_copy(
                update={
                    "backend": "piper_local",
                    "output_backend": "piper_local",
                    "mode": mode,
                    "audio_available": bool(self.binary_path and self.afplay_path),
                    "status": SpeechOutputStatus.INTERRUPTED,
                    "message": "speech_cancelled",
                    "updated_at": utc_now(),
                }
            )
            with self._lock:
                self._states[session_id] = state
            return state
        if output_path is not None:
            output_path.unlink(missing_ok=True)
        return (current or SpeechOutputResult(session_id=session_id)).model_copy(
            update={
                "backend": "piper_local",
                "output_backend": "piper_local",
                "mode": mode,
                "audio_available": bool(self.binary_path and self.afplay_path),
                "status": SpeechOutputStatus.IDLE,
                "message": "nothing_to_cancel",
                "updated_at": utc_now(),
            }
        )


class MacOSNativeCamera:
    _PERMISSION_RETRY_INTERVAL_SECONDS = 4.0

    def __init__(self, *, settings: Settings, snapshot_helper: AppleCameraSnapshotHelper | None = None) -> None:
        self.settings = settings
        self.ffmpeg_path = shutil.which("ffmpeg")
        self.snapshot_helper = snapshot_helper
        self.source = describe_camera_source(settings)
        self._lock = RLock()
        self._last_capture_error: DesktopDeviceError | None = None
        self._last_capture_error_at: datetime | None = None
        self._permission_retry_not_before = 0.0

    def health(self, *, required: bool = False) -> DesktopDeviceHealth:
        configured_label = (self.settings.blink_camera_device or "default").strip() or "default"
        if self.source.mode == "disabled":
            return build_device_health(
                device_id="desktop_camera",
                kind=DesktopDeviceKind.CAMERA,
                state=EdgeAdapterState.DISABLED,
                backend="disabled",
                available=False,
                required=required,
                detail=self.source.note,
                configured_label=configured_label,
                reason_code=DEVICE_REASON_FALLBACK_ACTIVE if not required else device_reason_code_for_error("camera_disabled"),
                selection_note=self.source.mode,
                fallback_active=not required,
            )
        if self.source.mode == "fixture_replay":
            available = bool(self.source.fixture_path)
            return build_device_health(
                device_id="desktop_camera",
                kind=DesktopDeviceKind.CAMERA,
                state=EdgeAdapterState.SIMULATED,
                backend="fixture_replay",
                available=available,
                required=required,
                detail=self.source.note,
                configured_label=configured_label,
                selected_label=self.source.fixture_path,
                reason_code=DEVICE_REASON_OK if available else device_reason_code_for_error("fixture_replay_missing", fallback_active=not required),
                selection_note="fixture_replay",
                fallback_active=not available and not required,
            )
        if self.source.mode == "browser_snapshot":
            return build_device_health(
                device_id="desktop_camera",
                kind=DesktopDeviceKind.CAMERA,
                state=EdgeAdapterState.DISABLED if not required else EdgeAdapterState.DEGRADED,
                backend="browser_snapshot",
                available=False,
                required=required,
                detail=self.source.note or "browser_camera_compatibility_mode",
                configured_label=configured_label,
                reason_code=DEVICE_REASON_FALLBACK_ACTIVE if not required else device_reason_code_for_error("browser_snapshot_required"),
                selection_note="browser_snapshot",
                fallback_active=not required,
            )
        if self.source.mode != "webcam":
            return build_device_health(
                device_id="desktop_camera",
                kind=DesktopDeviceKind.CAMERA,
                state=EdgeAdapterState.UNAVAILABLE if required else EdgeAdapterState.DEGRADED,
                backend="unknown",
                available=False,
                required=required,
                detail=self.source.note,
                configured_label=configured_label,
                reason_code=device_reason_code_for_error("camera_mode_unavailable", fallback_active=not required),
                selection_note=self.source.mode,
                fallback_active=not required,
            )
        if self.snapshot_helper and self.snapshot_helper.available() and not self.ffmpeg_path:
            try:
                probe = self.snapshot_helper.probe(preferred_label=self.settings.blink_camera_device)
                detail = f"device={probe.get('device_label') or 'default'}; selection=native_probe"
                return build_device_health(
                    device_id="desktop_camera",
                    kind=DesktopDeviceKind.CAMERA,
                    state=EdgeAdapterState.ACTIVE,
                    backend="apple_avfoundation",
                    available=True,
                    required=required,
                    detail=detail,
                    configured_label=configured_label,
                    selected_label=str(probe.get("device_label") or "default"),
                    reason_code=DEVICE_REASON_OK,
                    selection_note="native_probe",
                )
            except DesktopDeviceError as exc:
                return build_device_health(
                    device_id="desktop_camera",
                    kind=DesktopDeviceKind.CAMERA,
                    state=EdgeAdapterState.UNAVAILABLE if required else EdgeAdapterState.DEGRADED,
                    backend="apple_avfoundation",
                    available=False,
                    required=required,
                    detail=exc.detail or exc.classification,
                    configured_label=configured_label,
                    reason_code=device_reason_code_for_error(exc.classification, fallback_active=not required),
                    selection_note="native_probe_failed",
                    fallback_active=not required,
                )
        cached_error = self._cached_capture_error()
        if cached_error is not None:
            return build_device_health(
                device_id="desktop_camera",
                kind=DesktopDeviceKind.CAMERA,
                state=EdgeAdapterState.UNAVAILABLE if required else EdgeAdapterState.DEGRADED,
                backend="ffmpeg_avfoundation",
                available=False,
                required=required,
                detail=cached_error.detail or cached_error.classification,
                configured_label=configured_label,
                reason_code=device_reason_code_for_error(cached_error.classification, fallback_active=not required),
                selection_note="cached_capture_error",
                fallback_active=not required,
            )
        try:
            selection = self._select_video_device()
            device = selection.selected if hasattr(selection, "selected") else selection
            resolution_note = selection.resolution_note if hasattr(selection, "resolution_note") else "legacy_selection"
        except DesktopDeviceError as exc:
            backend = "apple_avfoundation" if self.snapshot_helper and self.snapshot_helper.available() else "ffmpeg_avfoundation"
            return build_device_health(
                device_id="desktop_camera",
                kind=DesktopDeviceKind.CAMERA,
                state=EdgeAdapterState.UNAVAILABLE if required else EdgeAdapterState.DEGRADED,
                backend=backend,
                available=False,
                required=required,
                detail=exc.detail or self.source.note,
                configured_label=configured_label,
                reason_code=device_reason_code_for_error(exc.classification, fallback_active=not required),
                selection_note="selection_failed",
                fallback_active=not required,
            )

        backend = "apple_avfoundation" if self.snapshot_helper and self.snapshot_helper.available() else "ffmpeg_avfoundation"
        detail = f"device={device.label}; permission_checked_on_capture; selection={resolution_note}"
        return build_device_health(
            device_id="desktop_camera",
            kind=DesktopDeviceKind.CAMERA,
            state=EdgeAdapterState.ACTIVE,
            backend=backend,
            available=True,
            required=required,
            detail=detail,
            configured_label=configured_label,
            selected_label=device.label,
            reason_code=DEVICE_REASON_OK,
            selection_note=resolution_note,
        )

    def capture_snapshot(self, *, background: bool = False) -> DesktopCameraCapture:
        if self.source.mode != "webcam":
            raise DesktopDeviceError("desktop_camera_not_native", self.source.note)
        cached_error = self._cached_capture_error()
        if background and cached_error is not None and self._permission_retry_pending():
            raise cached_error
        selection = self._select_video_device()
        device = selection.selected if hasattr(selection, "selected") else selection
        try:
            if self.ffmpeg_path:
                try:
                    capture = self._capture_with_ffmpeg(device)
                    self._record_capture_success()
                    return capture
                except DesktopDeviceError as exc:
                    self._record_capture_failure(exc)
                    if exc.classification in {
                        "camera_authorization_required",
                        "desktop_camera_capture_timeout",
                    }:
                        raise exc
                    if not self.snapshot_helper or not self.snapshot_helper.available():
                        raise exc
            if self.snapshot_helper and self.snapshot_helper.available():
                capture = self._capture_with_native_helper(device.label)
                self._record_capture_success()
                return capture
            if not self.ffmpeg_path:
                raise DesktopDeviceError("desktop_camera_ffmpeg_unavailable")
            capture = self._capture_with_ffmpeg(device)
            self._record_capture_success()
            return capture
        except DesktopDeviceError as exc:
            self._record_capture_failure(exc)
            raise

    def _capture_with_native_helper(self, preferred_label: str | None) -> DesktopCameraCapture:
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as handle:
            output_path = Path(handle.name)
        try:
            payload = self.snapshot_helper.capture(output_path, preferred_label=preferred_label)
            image_bytes = output_path.read_bytes()
            if not image_bytes:
                raise DesktopDeviceError("desktop_camera_capture_empty")
            captured_at = utc_now()
            return DesktopCameraCapture(
                image_data_url="data:image/jpeg;base64," + base64.b64encode(image_bytes).decode("ascii"),
                source_frame=PerceptionSourceFrame(
                    source_kind="native_camera_snapshot",
                    source_label=str(payload.get("device_label") or preferred_label),
                    frame_id=f"camera-{captured_at.strftime('%Y%m%d%H%M%S')}",
                    mime_type="image/jpeg",
                    captured_at=captured_at,
                    file_name=output_path.name,
                    metadata={"camera_warmup_retry_used": False},
                ),
                backend="apple_avfoundation",
                warmup_retry_used=False,
            )
        finally:
            output_path.unlink(missing_ok=True)

    def _ffmpeg_health(self, *, required: bool) -> DesktopDeviceHealth:
        configured_label = (self.settings.blink_camera_device or "default").strip() or "default"
        if not self.ffmpeg_path:
            return build_device_health(
                device_id="desktop_camera",
                kind=DesktopDeviceKind.CAMERA,
                state=EdgeAdapterState.UNAVAILABLE if required else EdgeAdapterState.DEGRADED,
                backend="ffmpeg_avfoundation",
                available=False,
                required=required,
                detail="ffmpeg_not_available_for_camera_capture",
                configured_label=configured_label,
                reason_code=device_reason_code_for_error("ffmpeg_missing", fallback_active=not required),
                selection_note="ffmpeg_missing",
                fallback_active=not required,
            )
        try:
            selection = self._select_video_device()
            device = selection.selected if hasattr(selection, "selected") else selection
            resolution_note = selection.resolution_note if hasattr(selection, "resolution_note") else "legacy_selection"
        except DesktopDeviceError as exc:
            return build_device_health(
                device_id="desktop_camera",
                kind=DesktopDeviceKind.CAMERA,
                state=EdgeAdapterState.UNAVAILABLE if required else EdgeAdapterState.DEGRADED,
                backend="ffmpeg_avfoundation",
                available=False,
                required=required,
                detail=exc.detail or self.source.note,
                configured_label=configured_label,
                reason_code=device_reason_code_for_error(exc.classification, fallback_active=not required),
                selection_note="selection_failed",
                fallback_active=not required,
            )
        return build_device_health(
            device_id="desktop_camera",
            kind=DesktopDeviceKind.CAMERA,
            state=EdgeAdapterState.ACTIVE,
            backend="ffmpeg_avfoundation",
            available=True,
            required=required,
            detail=f"device={device.label}; selection={resolution_note}",
            configured_label=configured_label,
            selected_label=device.label,
            reason_code=DEVICE_REASON_OK,
            selection_note=resolution_note,
        )

    def _capture_with_ffmpeg(self, device: FFmpegAVFoundationDevice) -> DesktopCameraCapture:
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as handle:
            output_path = Path(handle.name)
        try:
            selected_pixel_format: str | None = None
            completed = self._run_ffmpeg_capture(device, output_path=output_path, pixel_format=None)
            if completed.returncode != 0:
                supported_formats = _extract_supported_ffmpeg_pixel_formats(
                    completed.stderr,
                    completed.stdout,
                )
                if supported_formats:
                    retry_format = _choose_ffmpeg_pixel_format(supported_formats)
                    selected_pixel_format = retry_format
                    completed = self._run_ffmpeg_capture(
                        device,
                        output_path=output_path,
                        pixel_format=retry_format,
                    )
                if completed.returncode != 0:
                    detail = completed.stderr.strip() or completed.stdout.strip() or "camera_capture_failed"
                    raise DesktopDeviceError("desktop_camera_capture_failed", detail)
            image_bytes = output_path.read_bytes()
            if not image_bytes:
                raise DesktopDeviceError("desktop_camera_capture_empty")
            warmup_retry_used = False
            if _is_underexposed_camera_frame(image_bytes):
                warmup_bytes = self._retry_ffmpeg_capture_after_warmup(
                    device,
                    pixel_format=selected_pixel_format,
                )
                if warmup_bytes is not None and _camera_frame_luma_mean(warmup_bytes) > _camera_frame_luma_mean(image_bytes):
                    image_bytes = warmup_bytes
                    warmup_retry_used = True
            image_data_url = "data:image/jpeg;base64," + base64.b64encode(image_bytes).decode("ascii")
            captured_at = utc_now()
            return DesktopCameraCapture(
                image_data_url=image_data_url,
                source_frame=PerceptionSourceFrame(
                    source_kind="native_camera_snapshot",
                    source_label=device.label,
                    frame_id=f"camera-{captured_at.strftime('%Y%m%d%H%M%S')}",
                    mime_type="image/jpeg",
                    captured_at=captured_at,
                    file_name=output_path.name,
                    metadata={"camera_warmup_retry_used": warmup_retry_used},
                ),
                backend="ffmpeg_avfoundation",
                warmup_retry_used=warmup_retry_used,
            )
        except subprocess.TimeoutExpired as exc:
            detail = "Camera capture timed out. Grant camera access to Terminal/iTerm and Homebrew ffmpeg, then retry."
            raise DesktopDeviceError("camera_authorization_required", detail) from exc
        finally:
            output_path.unlink(missing_ok=True)

    def _retry_ffmpeg_capture_after_warmup(
        self,
        device: FFmpegAVFoundationDevice,
        *,
        pixel_format: str | None,
    ) -> bytes | None:
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as handle:
            output_path = Path(handle.name)
        try:
            completed = self._run_ffmpeg_capture(
                device,
                output_path=output_path,
                pixel_format=pixel_format,
                seek_seconds=_FFMPEG_WARMUP_SEEK_SECONDS,
                timeout_seconds=_FFMPEG_WARMUP_TIMEOUT_SECONDS,
            )
            if completed.returncode != 0 or not output_path.exists():
                return None
            image_bytes = output_path.read_bytes()
            return image_bytes or None
        except (DesktopDeviceError, subprocess.TimeoutExpired):
            return None
        finally:
            output_path.unlink(missing_ok=True)

    def _cached_capture_error(self) -> DesktopDeviceError | None:
        with self._lock:
            error = self._last_capture_error
            if error is None:
                return None
            if error.classification not in {"camera_authorization_required", "camera_authorization_failed"}:
                return error
            return error

    def _permission_retry_pending(self) -> bool:
        with self._lock:
            return bool(self._last_capture_error) and monotonic() < self._permission_retry_not_before

    def _record_capture_failure(self, error: DesktopDeviceError) -> None:
        with self._lock:
            self._last_capture_error = error
            self._last_capture_error_at = utc_now()
            if error.classification in {"camera_authorization_required", "camera_authorization_failed"}:
                self._permission_retry_not_before = monotonic() + self._PERMISSION_RETRY_INTERVAL_SECONDS

    def _record_capture_success(self) -> None:
        with self._lock:
            self._last_capture_error = None
            self._last_capture_error_at = None
            self._permission_retry_not_before = 0.0

    def _run_ffmpeg_capture(
        self,
        device: FFmpegAVFoundationDevice,
        *,
        output_path: Path,
        pixel_format: str | None,
        seek_seconds: float = 0.0,
        timeout_seconds: float = 6.0,
    ) -> subprocess.CompletedProcess[str]:
        if not self.ffmpeg_path:
            raise DesktopDeviceError("desktop_camera_ffmpeg_unavailable")
        command = [
            self.ffmpeg_path,
            "-loglevel",
            "error",
            "-f",
            "avfoundation",
        ]
        if pixel_format:
            command.extend(["-pixel_format", pixel_format])
        command.extend(
            [
                "-framerate",
                "30",
                "-i",
                f"{device.index}:none",
            ]
        )
        if seek_seconds > 0:
            command.extend(
                [
                    "-ss",
                    f"{seek_seconds:.2f}",
                ]
            )
        command.extend(
            [
                "-frames:v",
                "1",
                "-q:v",
                "2",
                "-y",
                str(output_path),
            ]
        )
        return subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )

    def _select_video_device(self) -> ResolvedAVFoundationSelection:
        devices = list_avfoundation_devices(ffmpeg_path=self.ffmpeg_path)
        configured = (self.settings.blink_camera_device or "default").strip()
        preset = (self.settings.blink_device_preset or "auto").strip() or "auto"
        selection = resolve_avfoundation_device(
            configured=configured,
            devices=devices["video"],
            prefixes=("camera", "video"),
            preset=preset,
        )
        if selection.selected is None:
            raise DesktopDeviceError("desktop_camera_not_found", configured)
        return selection

    def selected_device_label(self) -> str | None:
        try:
            return self._select_video_device().selected.label
        except DesktopDeviceError:
            return None


class DesktopDeviceRegistry:
    def __init__(
        self,
        *,
        settings: Settings,
        microphone_input: MacOSNativeMicrophoneInput,
        whisper_transcriber: WhisperCppTranscriber,
        speaker_output: MacOSSpeakerOutputDevice,
        piper_speaker_output: PiperSpeakerOutputDevice,
        stub_speaker_output: StubSpeakerOutputDevice,
        camera_capture: MacOSNativeCamera,
    ) -> None:
        self.settings = settings
        self.microphone_input = microphone_input
        self.whisper_transcriber = whisper_transcriber
        self.speaker_output = speaker_output
        self.piper_speaker_output = piper_speaker_output
        self.stub_speaker_output = stub_speaker_output
        self.camera_capture = camera_capture

    def describe(self, *, default_voice_mode: VoiceRuntimeMode) -> list[DesktopDeviceHealth]:
        camera_required = (
            self.camera_capture.source.mode in {"webcam", "fixture_replay"}
            and self.settings.perception_default_provider != "stub"
        )
        return [
            self.microphone_input.health(required=default_voice_mode == VoiceRuntimeMode.DESKTOP_NATIVE),
            self._speaker_health(default_voice_mode=default_voice_mode),
            self.camera_capture.health(required=camera_required),
        ]

    def capture_camera_snapshot(self, *, background: bool = False) -> DesktopCameraCapture:
        return self.camera_capture.capture_snapshot(background=background)

    def selected_microphone_label(self) -> str | None:
        return self.microphone_input.selected_device_label()

    def selected_camera_label(self) -> str | None:
        return self.camera_capture.selected_device_label()

    def selected_speaker_label(self) -> str:
        requested = (self.settings.blink_speaker_device or "system_default").strip() or "system_default"
        return requested if requested != "default" else "system_default"

    def speaker_selection_supported(self) -> bool:
        return False

    def transcribe_local_audio_file(self, audio_path: Path, *, locale: str | None = None) -> dict[str, object]:
        return self.microphone_input.transcribe_local_audio_file(audio_path, locale=locale)

    def poll_open_mic(
        self,
        *,
        session_id: str,
        backend_candidates: tuple[str, ...],
        vad_silence_ms: int,
        vad_min_speech_ms: int,
    ) -> OpenMicCaptureResult:
        duration_seconds = max(0.8, min(2.0, (vad_silence_ms + vad_min_speech_ms) / 1000.0))
        chunk = self.microphone_input.capture_audio_chunk(duration_seconds=duration_seconds, session_id=session_id)
        try:
            speech_detected, speech_ms, rms_level = detect_voice_activity(
                chunk.audio_path,
                min_speech_ms=vad_min_speech_ms,
            )
            if not speech_detected:
                return OpenMicCaptureResult(
                    captured_at=chunk.captured_at,
                    duration_seconds=chunk.duration_seconds,
                    speech_detected=False,
                    speech_ms=speech_ms,
                    rms_level=rms_level,
                )

            last_error: str | None = None
            for backend_id in backend_candidates:
                try:
                    transcription_started = perf_counter()
                    if backend_id == "whisper_cpp_local":
                        if not self.whisper_transcriber.available():
                            last_error = "whisper_cpp_local_unavailable"
                            continue
                        payload = self.whisper_transcriber.transcribe(
                            chunk.audio_path,
                            locale=self.settings.blink_native_transcription_locale,
                        )
                    elif backend_id == "apple_speech_local":
                        payload = self.microphone_input.transcribe_audio_file(
                            chunk.audio_path,
                            backend_id="apple_speech_local",
                            locale=self.settings.blink_native_transcription_locale,
                        )
                    elif backend_id == "typed_input":
                        return OpenMicCaptureResult(
                            captured_at=chunk.captured_at,
                            duration_seconds=chunk.duration_seconds,
                            speech_detected=True,
                            speech_ms=speech_ms,
                            rms_level=rms_level,
                            transcription_backend="typed_input",
                            degraded_reason="typed_input_required",
                        )
                    else:
                        continue
                except (DesktopDeviceError, ValueError) as exc:
                    last_error = str(exc)
                    continue
                transcript_text = str(payload.get("transcript_text") or "").strip()
                if not transcript_text:
                    last_error = f"{backend_id}:empty_transcript"
                    continue
                transcription_latency_ms = round((perf_counter() - transcription_started) * 1000.0, 2)
                return OpenMicCaptureResult(
                    captured_at=chunk.captured_at,
                    duration_seconds=chunk.duration_seconds,
                    speech_detected=True,
                    speech_ms=speech_ms,
                    rms_level=rms_level,
                    transcript_text=transcript_text,
                    partial_transcript=transcript_text[:160],
                    transcription_backend=str(payload.get("transcription_backend") or backend_id),
                    transcription_latency_ms=transcription_latency_ms,
                )

            return OpenMicCaptureResult(
                captured_at=chunk.captured_at,
                duration_seconds=chunk.duration_seconds,
                speech_detected=True,
                speech_ms=speech_ms,
                rms_level=rms_level,
                transcription_backend="typed_input",
                degraded_reason=last_error or "typed_input_required",
            )
        finally:
            chunk.audio_path.unlink(missing_ok=True)

    def _speaker_health(self, *, default_voice_mode: VoiceRuntimeMode) -> DesktopDeviceHealth:
        requires_audio = default_voice_mode in {
            VoiceRuntimeMode.DESKTOP_NATIVE,
            VoiceRuntimeMode.OPEN_MIC_LOCAL,
            VoiceRuntimeMode.MACOS_SAY,
            VoiceRuntimeMode.BROWSER_LIVE_MACOS_SAY,
        }
        if (self.settings.blink_tts_backend or "").strip().lower() == "piper_local":
            return self.piper_speaker_output.health(required=requires_audio)
        return self.speaker_output.health(required=requires_audio)


def build_desktop_device_registry(settings: Settings) -> DesktopDeviceRegistry:
    helper_root = Path(__file__).resolve().parents[1]
    helper_source = helper_root / "native_helpers" / "apple_speech_transcribe.swift"
    camera_helper_source = helper_root / "native_helpers" / "apple_camera_snapshot.swift"
    speaker_output = MacOSSpeakerOutputDevice(
        voice_name=settings.macos_tts_voice,
        rate=settings.macos_tts_rate,
    )
    speaker_output.requested_output_device = settings.blink_speaker_device
    whisper_transcriber = WhisperCppTranscriber(settings=settings)
    return DesktopDeviceRegistry(
        settings=settings,
        microphone_input=MacOSNativeMicrophoneInput(
            settings=settings,
            transcriber=AppleSpeechTranscriber(source_path=helper_source),
            whisper_transcriber=whisper_transcriber,
        ),
        whisper_transcriber=whisper_transcriber,
        speaker_output=speaker_output,
        piper_speaker_output=PiperSpeakerOutputDevice(settings=settings),
        stub_speaker_output=StubSpeakerOutputDevice(),
        camera_capture=MacOSNativeCamera(
            settings=settings,
            snapshot_helper=AppleCameraSnapshotHelper(source_path=camera_helper_source),
        ),
    )


def list_avfoundation_devices(*, ffmpeg_path: str | None) -> dict[str, list[FFmpegAVFoundationDevice]]:
    devices = {"video": [], "audio": []}
    if not ffmpeg_path:
        return devices
    try:
        completed = subprocess.run(
            [ffmpeg_path, "-f", "avfoundation", "-list_devices", "true", "-i", ""],
            check=False,
            capture_output=True,
            text=True,
            timeout=5.0,
        )
    except subprocess.TimeoutExpired:
        return devices
    current_kind: str | None = None
    output = "\n".join(part for part in (completed.stdout, completed.stderr) if part)
    for line in output.splitlines():
        if "AVFoundation video devices:" in line:
            current_kind = "video"
            continue
        if "AVFoundation audio devices:" in line:
            current_kind = "audio"
            continue
        if current_kind is None:
            continue
        match = _DEVICE_LINE_RE.search(line)
        if not match:
            continue
        devices[current_kind].append(
            FFmpegAVFoundationDevice(
                index=int(match.group(1)),
                label=match.group(2).strip(),
                kind=current_kind,
            )
        )
    return devices


def _extract_supported_ffmpeg_pixel_formats(*parts: str | None) -> list[str]:
    formats: list[str] = []
    for part in parts:
        if not part:
            continue
        capture = False
        for raw_line in part.splitlines():
            line = raw_line.strip()
            if "Supported pixel formats:" in line:
                capture = True
                continue
            if not capture:
                continue
            if not line:
                continue
            token = line.split("]")[-1].strip()
            if not token or " " in token:
                continue
            formats.append(token)
    deduped: list[str] = []
    for token in formats:
        if token not in deduped:
            deduped.append(token)
    return deduped


def _choose_ffmpeg_pixel_format(formats: list[str]) -> str | None:
    available = {item.strip() for item in formats if item.strip()}
    for candidate in _FFMPEG_CAMERA_FORMAT_PRIORITY:
        if candidate in available:
            return candidate
    return formats[0].strip() if formats else None


def resolve_avfoundation_device(
    *,
    configured: str,
    devices: list[FFmpegAVFoundationDevice],
    prefixes: tuple[str, ...],
    preset: str = "auto",
) -> ResolvedAVFoundationSelection:
    if not devices:
        return ResolvedAVFoundationSelection(
            selected=None,
            configured=configured,
            preset=preset,
            resolution_note="no_devices_detected",
        )

    lowered = configured.lower()
    if lowered == "default":
        selected = sorted(devices, key=lambda item: (-_default_avfoundation_device_priority(item, preset=preset), item.index))[0]
        return ResolvedAVFoundationSelection(
            selected=selected,
            configured=configured,
            preset=preset,
            resolution_note=f"preset:{preset or 'auto'}",
        )

    token = configured
    for prefix in prefixes:
        marker = f"{prefix}:"
        if lowered.startswith(marker):
            token = configured.split(":", 1)[1]
            break

    token = token.strip()
    if token.isdigit():
        index = int(token)
        selected = next((item for item in devices if item.index == index), None)
        if selected is not None:
            return ResolvedAVFoundationSelection(
                selected=selected,
                configured=configured,
                preset=preset,
                resolution_note="configured_index_match",
            )
    else:
        lowered_token = token.lower()
        selected = next((item for item in devices if item.label.lower() == lowered_token), None)
        if selected is not None:
            return ResolvedAVFoundationSelection(
                selected=selected,
                configured=configured,
                preset=preset,
                resolution_note="configured_label_match",
            )

    fallback = sorted(devices, key=lambda item: (-_default_avfoundation_device_priority(item, preset=preset), item.index))[0]
    missing_kind = "index" if token.isdigit() else "label"
    return ResolvedAVFoundationSelection(
        selected=fallback,
        configured=configured,
        preset=preset,
        resolution_note=f"configured_{missing_kind}_missing_fallback_to:{fallback.label}",
        fallback_used=True,
    )


def select_avfoundation_device(
    *,
    configured: str,
    devices: list[FFmpegAVFoundationDevice],
    prefixes: tuple[str, ...],
    preset: str = "auto",
) -> FFmpegAVFoundationDevice | None:
    return resolve_avfoundation_device(
        configured=configured,
        devices=devices,
        prefixes=prefixes,
        preset=preset,
    ).selected


def _default_avfoundation_device_priority(device: FFmpegAVFoundationDevice, *, preset: str = "auto") -> int:
    label = device.label.lower()
    normalized_preset = (preset or "auto").strip().lower()
    score = 0
    if device.kind == "video":
        if normalized_preset == "internal_macbook":
            if "macbook" in label and "camera" in label:
                score += 220
            if "facetime" in label or "built-in" in label:
                score += 180
            if "ultrafine" in label and "camera" in label:
                score += 90
            elif "display" in label and "camera" in label and "screen" not in label:
                score += 70
        else:
            if "ultrafine" in label and "camera" in label:
                score += 200
            elif "display" in label and "camera" in label and "screen" not in label:
                score += 170
            if "macbook" in label and "camera" in label:
                score += 120
            if "facetime" in label or "built-in" in label:
                score += 100
        if "continuity" in label:
            score += 40
        if "desk view" in label:
            score -= 40
        if "capture screen" in label or "screen" in label:
            score -= 100
        if "display" in label:
            score -= 20
    if device.kind == "audio":
        if normalized_preset == "internal_macbook":
            if "macbook" in label and "microphone" in label:
                score += 220
            elif "microphone" in label or "built-in" in label:
                score += 170
            if "ultrafine" in label and "audio" in label:
                score += 90
            elif "display audio" in label:
                score += 70
        else:
            if "ultrafine" in label and "audio" in label:
                score += 200
            elif "display audio" in label:
                score += 170
            if "macbook" in label and "microphone" in label:
                score += 120
            elif "microphone" in label or "built-in" in label:
                score += 90
        if "speaker" in label:
            score -= 20
    return score


def detect_voice_activity(audio_path: Path, *, min_speech_ms: int, threshold: int = 550) -> tuple[bool, int, float]:
    try:
        with wave.open(str(audio_path), "rb") as handle:
            frame_rate = handle.getframerate() or 16000
            sample_width = handle.getsampwidth() or 2
            channel_count = handle.getnchannels() or 1
            frame_count = handle.getnframes()
            raw = handle.readframes(frame_count)
    except (wave.Error, OSError):
        return False, 0, 0.0
    if sample_width != 2 or not raw:
        return False, 0, 0.0
    samples = array.array("h")
    samples.frombytes(raw)
    if channel_count > 1:
        mono_samples = array.array("h")
        for index in range(0, len(samples), channel_count):
            mono_samples.append(samples[index])
        samples = mono_samples
    if not samples:
        return False, 0, 0.0
    window_ms = 30
    window_size = max(1, int(frame_rate * (window_ms / 1000.0)))
    voiced_windows = 0
    total_level = 0.0
    window_count = 0
    for start in range(0, len(samples), window_size):
        window = samples[start:start + window_size]
        if not window:
            continue
        level = sum(abs(sample) for sample in window) / len(window)
        total_level += level
        window_count += 1
        if level >= threshold:
            voiced_windows += 1
    speech_ms = voiced_windows * window_ms
    rms_level = round(total_level / max(window_count, 1), 2)
    return speech_ms >= min_speech_ms, speech_ms, rms_level


def _extract_whisper_stdout(stdout: str, stderr: str) -> str:
    lines = [line.strip() for line in (*stdout.splitlines(), *stderr.splitlines()) if line.strip()]
    candidates = [
        line
        for line in lines
        if not line.startswith("[")
        and "system_info" not in line
        and "whisper_" not in line
        and "main:" not in line
    ]
    return candidates[-1] if candidates else ""


def _camera_frame_luma_mean(image_bytes: bytes) -> float:
    try:
        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    except Exception:
        return 255.0
    stat = ImageStat.Stat(image)
    return sum(stat.mean) / 3.0


def _is_underexposed_camera_frame(image_bytes: bytes) -> bool:
    return _camera_frame_luma_mean(image_bytes) < _FFMPEG_UNDEREXPOSED_MEAN_THRESHOLD


__all__ = [
    "DesktopCameraCapture",
    "DesktopDeviceError",
    "DesktopDeviceRegistry",
    "OpenMicCaptureResult",
    "MacOSNativeCamera",
    "MacOSNativeMicrophoneInput",
    "MacOSSpeakerOutputDevice",
    "PiperSpeakerOutputDevice",
    "ResolvedAVFoundationSelection",
    "StubSpeakerOutputDevice",
    "WhisperCppTranscriber",
    "build_desktop_device_registry",
    "detect_voice_activity",
    "list_avfoundation_devices",
    "resolve_avfoundation_device",
    "select_avfoundation_device",
    "_camera_frame_luma_mean",
    "_is_underexposed_camera_frame",
]
