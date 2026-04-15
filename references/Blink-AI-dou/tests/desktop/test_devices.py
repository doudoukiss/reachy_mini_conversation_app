from __future__ import annotations

import base64
from pathlib import Path
from types import SimpleNamespace

from PIL import Image

from embodied_stack.config import Settings
from embodied_stack.desktop.devices import (
    CapturedAudioChunk,
    DesktopCameraCapture,
    DesktopDeviceError,
    FFmpegAVFoundationDevice,
    MacOSNativeCamera,
    MacOSNativeMicrophoneInput,
    _choose_ffmpeg_pixel_format,
    _camera_frame_luma_mean,
    _extract_supported_ffmpeg_pixel_formats,
    _is_underexposed_camera_frame,
    _native_tools_runtime_dir,
    select_avfoundation_device,
)
from embodied_stack.shared.models import PerceptionSourceFrame, utc_now


def build_settings(tmp_path: Path, **overrides) -> Settings:
    return Settings(
        _env_file=None,
        brain_store_path=str(tmp_path / "brain_store.json"),
        demo_report_dir=str(tmp_path / "demo_runs"),
        episode_export_dir=str(tmp_path / "episodes"),
        shift_report_dir=str(tmp_path / "shift_reports"),
        perception_frame_dir=str(tmp_path / "perception_frames"),
        operator_auth_token="desktop-test-token",
        operator_auth_runtime_file=str(tmp_path / "operator_auth.json"),
        blink_appliance_profile_file=str(tmp_path / "appliance_profile.json"),
        **overrides,
    )


def test_select_avfoundation_device_prefers_external_display_camera_for_default():
    selected = select_avfoundation_device(
        configured="default",
        devices=[
            FFmpegAVFoundationDevice(index=0, label="MacBook Pro Camera", kind="video"),
            FFmpegAVFoundationDevice(index=1, label="LG UltraFine Display Camera", kind="video"),
            FFmpegAVFoundationDevice(index=2, label="MacBook Pro Desk View Camera", kind="video"),
        ],
        prefixes=("camera", "video"),
    )

    assert selected is not None
    assert selected.label == "LG UltraFine Display Camera"


def test_select_avfoundation_device_prefers_external_display_microphone_for_default():
    selected = select_avfoundation_device(
        configured="default",
        devices=[
            FFmpegAVFoundationDevice(index=0, label="LG UltraFine Display Audio", kind="audio"),
            FFmpegAVFoundationDevice(index=1, label="MacBook Pro Microphone", kind="audio"),
        ],
        prefixes=("microphone", "audio", "mic"),
    )

    assert selected is not None
    assert selected.label == "LG UltraFine Display Audio"


def test_select_avfoundation_device_falls_back_to_built_in_camera_when_display_camera_missing():
    selected = select_avfoundation_device(
        configured="default",
        devices=[
            FFmpegAVFoundationDevice(index=0, label="MacBook Pro Camera", kind="video"),
            FFmpegAVFoundationDevice(index=1, label="MacBook Pro Desk View Camera", kind="video"),
        ],
        prefixes=("camera", "video"),
    )

    assert selected is not None
    assert selected.label == "MacBook Pro Camera"


def test_select_avfoundation_device_falls_back_to_built_in_microphone_when_display_audio_missing():
    selected = select_avfoundation_device(
        configured="default",
        devices=[
            FFmpegAVFoundationDevice(index=0, label="MacBook Pro Microphone", kind="audio"),
        ],
        prefixes=("microphone", "audio", "mic"),
    )

    assert selected is not None
    assert selected.label == "MacBook Pro Microphone"


def test_select_avfoundation_device_prefers_internal_macbook_when_internal_preset_requested():
    selected = select_avfoundation_device(
        configured="default",
        devices=[
            FFmpegAVFoundationDevice(index=0, label="LG UltraFine Display Audio", kind="audio"),
            FFmpegAVFoundationDevice(index=1, label="MacBook Pro Microphone", kind="audio"),
        ],
        prefixes=("microphone", "audio", "mic"),
        preset="internal_macbook",
    )

    assert selected is not None
    assert selected.label == "MacBook Pro Microphone"


def test_select_avfoundation_device_keeps_external_monitor_preference_when_requested():
    selected = select_avfoundation_device(
        configured="default",
        devices=[
            FFmpegAVFoundationDevice(index=0, label="MacBook Pro Camera", kind="video"),
            FFmpegAVFoundationDevice(index=1, label="LG UltraFine Display Camera", kind="video"),
        ],
        prefixes=("camera", "video"),
        preset="external_monitor",
    )

    assert selected is not None
    assert selected.label == "LG UltraFine Display Camera"


class _FailingAppleSpeech:
    def available(self) -> bool:
        return True

    def transcribe(self, audio_path: Path, *, locale: str) -> dict[str, object]:
        del audio_path, locale
        raise DesktopDeviceError("apple_speech_failed", "speech_transcriber_failed")


class _WorkingWhisper:
    def available(self) -> bool:
        return True

    def transcribe(self, audio_path: Path, *, locale: str) -> dict[str, object]:
        del audio_path, locale
        return {
            "ok": True,
            "transcript_text": "fallback transcript",
            "transcription_backend": "whisper_cpp_local",
        }


def test_microphone_capture_falls_back_to_whisper_when_apple_speech_fails(tmp_path: Path, monkeypatch):
    settings = build_settings(tmp_path)
    microphone = MacOSNativeMicrophoneInput(
        settings=settings,
        transcriber=_FailingAppleSpeech(),
        whisper_transcriber=_WorkingWhisper(),
    )
    microphone.ffmpeg_path = "ffmpeg"

    audio_path = tmp_path / "capture.wav"
    audio_path.write_bytes(b"fake-audio")

    monkeypatch.setattr(
        microphone,
        "capture_audio_chunk",
        lambda duration_seconds, session_id=None: CapturedAudioChunk(
            audio_path=audio_path,
            captured_at=utc_now(),
            duration_seconds=duration_seconds,
            device_label="MacBook Pro Microphone",
        ),
    )

    transcript = microphone.capture(
        SimpleNamespace(input_metadata={}, source=None),
        session_id="desktop-native-live",
    )

    assert transcript.transcript_text == "fallback transcript"
    assert transcript.transcription_backend == "whisper_cpp_local"


class _PermissionDeniedCameraHelper:
    def available(self) -> bool:
        return True

    def probe(self, *, preferred_label: str | None = None) -> dict[str, object]:
        del preferred_label
        raise DesktopDeviceError("camera_authorization_failed", "Camera permission was denied.")

    def capture(self, output_path: Path, *, preferred_label: str | None = None) -> dict[str, object]:
        del output_path, preferred_label
        raise DesktopDeviceError("camera_authorization_failed", "Camera permission was denied.")


class _UnexpectedCameraHelper:
    def available(self) -> bool:
        return True

    def probe(self, *, preferred_label: str | None = None) -> dict[str, object]:
        del preferred_label
        raise AssertionError("camera helper should not be used")

    def capture(self, output_path: Path, *, preferred_label: str | None = None) -> dict[str, object]:
        del output_path, preferred_label
        raise AssertionError("camera helper should not be used")


def test_camera_health_reports_permission_denied_honestly(tmp_path: Path):
    settings = build_settings(tmp_path)
    camera = MacOSNativeCamera(settings=settings, snapshot_helper=_PermissionDeniedCameraHelper())
    camera.ffmpeg_path = None
    camera.source = SimpleNamespace(mode="webcam", note="native_webcam", fixture_path=None)

    health = camera.health(required=True)

    assert health.backend == "apple_avfoundation"
    assert health.available is False
    assert health.state.value == "unavailable"
    assert "permission was denied" in (health.detail or "").lower()


def test_camera_capture_reports_helper_permission_denied_when_ffmpeg_unavailable(tmp_path: Path, monkeypatch):
    settings = build_settings(tmp_path)
    camera = MacOSNativeCamera(settings=settings, snapshot_helper=_PermissionDeniedCameraHelper())
    camera.ffmpeg_path = None
    camera.source = SimpleNamespace(mode="webcam", note="native_webcam", fixture_path=None)

    monkeypatch.setattr(
        camera,
        "_select_video_device",
        lambda: FFmpegAVFoundationDevice(index=1, label="MacBook Pro Camera", kind="video"),
    )

    try:
        camera.capture_snapshot()
    except DesktopDeviceError as exc:
        assert exc.classification == "camera_authorization_failed"
        assert "permission was denied" in (exc.detail or "").lower()
    else:
        raise AssertionError("camera capture should fail honestly when permission is denied")


def test_camera_capture_reports_ffmpeg_permission_requirement_without_helper_fallback(tmp_path: Path, monkeypatch):
    settings = build_settings(tmp_path)
    camera = MacOSNativeCamera(settings=settings, snapshot_helper=_UnexpectedCameraHelper())
    camera.ffmpeg_path = "ffmpeg"
    camera.source = SimpleNamespace(mode="webcam", note="native_webcam", fixture_path=None)

    monkeypatch.setattr(
        camera,
        "_select_video_device",
        lambda: FFmpegAVFoundationDevice(index=0, label="LG UltraFine Display Camera", kind="video"),
    )

    def _raise_ffmpeg_timeout(device):
        del device
        raise DesktopDeviceError(
            "camera_authorization_required",
            "Camera capture timed out. Grant camera access to Terminal/iTerm and Homebrew ffmpeg, then retry.",
        )

    monkeypatch.setattr(camera, "_capture_with_ffmpeg", _raise_ffmpeg_timeout)

    try:
        camera.capture_snapshot()
    except DesktopDeviceError as exc:
        assert exc.classification == "camera_authorization_required"
        assert "grant camera access" in (exc.detail or "").lower()
    else:
        raise AssertionError("camera capture should fail honestly when ffmpeg permission is pending")


def test_camera_background_retry_fast_fails_while_permission_retry_pending(tmp_path: Path, monkeypatch):
    settings = build_settings(tmp_path)
    camera = MacOSNativeCamera(settings=settings, snapshot_helper=_UnexpectedCameraHelper())
    camera.ffmpeg_path = "ffmpeg"
    camera.source = SimpleNamespace(mode="webcam", note="native_webcam", fixture_path=None)

    monkeypatch.setattr(
        camera,
        "_select_video_device",
        lambda: FFmpegAVFoundationDevice(index=0, label="LG UltraFine Display Camera", kind="video"),
    )

    calls = {"count": 0}

    def _permission_timeout(device):
        del device
        calls["count"] += 1
        raise DesktopDeviceError(
            "camera_authorization_required",
            "Camera capture timed out. Grant camera access to Terminal/iTerm and Homebrew ffmpeg, then retry.",
        )

    monkeypatch.setattr(camera, "_capture_with_ffmpeg", _permission_timeout)

    try:
        camera.capture_snapshot(background=False)
    except DesktopDeviceError:
        pass

    try:
        camera.capture_snapshot(background=True)
    except DesktopDeviceError as exc:
        assert exc.classification == "camera_authorization_required"
    else:
        raise AssertionError("background retry should use cached permission failure during retry window")

    assert calls["count"] == 1


def test_camera_manual_retry_recovers_after_permission_change(tmp_path: Path, monkeypatch):
    settings = build_settings(tmp_path)
    camera = MacOSNativeCamera(settings=settings, snapshot_helper=_UnexpectedCameraHelper())
    camera.ffmpeg_path = "ffmpeg"
    camera.source = SimpleNamespace(mode="webcam", note="native_webcam", fixture_path=None)

    monkeypatch.setattr(
        camera,
        "_select_video_device",
        lambda: FFmpegAVFoundationDevice(index=0, label="LG UltraFine Display Camera", kind="video"),
    )

    calls = {"count": 0}

    def _retryable_capture(device):
        calls["count"] += 1
        if calls["count"] == 1:
            raise DesktopDeviceError(
                "camera_authorization_required",
                "Camera capture timed out. Grant camera access to Terminal/iTerm and Homebrew ffmpeg, then retry.",
            )
        captured_at = utc_now()
        return DesktopCameraCapture(
            image_data_url="data:image/jpeg;base64,ZmFrZQ==",
            source_frame=PerceptionSourceFrame(
                source_kind="native_camera_snapshot",
                source_label=device.label,
                frame_id="frame-1",
                mime_type="image/jpeg",
                captured_at=captured_at,
                metadata={"camera_warmup_retry_used": False},
            ),
            backend="ffmpeg_avfoundation",
            warmup_retry_used=False,
        )

    monkeypatch.setattr(camera, "_capture_with_ffmpeg", _retryable_capture)

    try:
        camera.capture_snapshot(background=False)
    except DesktopDeviceError:
        pass

    capture = camera.capture_snapshot(background=False)

    assert capture.backend == "ffmpeg_avfoundation"
    assert calls["count"] == 2
    health = camera.health(required=True)
    assert health.available is True
    assert health.state.value == "active"


def test_extract_supported_ffmpeg_pixel_formats_parses_avfoundation_error():
    stderr = """
    [avfoundation @ 0x74ac18000] Selected pixel format (yuv420p) is not supported by the input device.
    [avfoundation @ 0x74ac18000] Supported pixel formats:
    [avfoundation @ 0x74ac18000]   uyvy422
    [avfoundation @ 0x74ac18000]   yuyv422
    [avfoundation @ 0x74ac18000]   nv12
    [avfoundation @ 0x74ac18000]   0rgb
    [avfoundation @ 0x74ac18000]   bgr0
    """

    assert _extract_supported_ffmpeg_pixel_formats(stderr) == ["uyvy422", "yuyv422", "nv12", "0rgb", "bgr0"]


def test_choose_ffmpeg_pixel_format_prefers_bgr0_then_nv12():
    assert _choose_ffmpeg_pixel_format(["uyvy422", "nv12", "bgr0"]) == "bgr0"
    assert _choose_ffmpeg_pixel_format(["uyvy422", "nv12"]) == "nv12"


def test_underexposed_camera_frame_detection_flags_nearly_black_image(tmp_path: Path):
    dark_image = Image.new("RGB", (4, 4), color=(5, 5, 5))
    bright_image = Image.new("RGB", (4, 4), color=(180, 180, 180))
    dark_path = tmp_path / "test_dark_frame.jpg"
    bright_path = tmp_path / "test_bright_frame.jpg"
    dark_image.save(dark_path, format="JPEG")
    bright_image.save(bright_path, format="JPEG")

    try:
        dark_bytes = dark_path.read_bytes()
        bright_bytes = bright_path.read_bytes()
        assert _camera_frame_luma_mean(dark_bytes) < 12.0
        assert _is_underexposed_camera_frame(dark_bytes) is True
        assert _is_underexposed_camera_frame(bright_bytes) is False
    finally:
        dark_path.unlink(missing_ok=True)
        bright_path.unlink(missing_ok=True)


def test_ffmpeg_capture_retries_after_warmup_when_initial_frame_is_underexposed(tmp_path: Path, monkeypatch):
    settings = build_settings(tmp_path)
    camera = MacOSNativeCamera(settings=settings, snapshot_helper=_UnexpectedCameraHelper())
    camera.ffmpeg_path = "ffmpeg"
    camera.source = SimpleNamespace(mode="webcam", note="native_webcam", fixture_path=None)

    monkeypatch.setattr(
        camera,
        "_select_video_device",
        lambda: FFmpegAVFoundationDevice(index=0, label="LG UltraFine Display Camera", kind="video"),
    )

    dark_bytes_path = tmp_path / "dark.jpg"
    bright_bytes_path = tmp_path / "bright.jpg"
    Image.new("RGB", (8, 8), color=(5, 5, 5)).save(dark_bytes_path, format="JPEG")
    Image.new("RGB", (8, 8), color=(180, 180, 180)).save(bright_bytes_path, format="JPEG")

    calls: list[tuple[float, float, str | None]] = []

    def _fake_run_ffmpeg_capture(device, *, output_path, pixel_format, seek_seconds=0.0, timeout_seconds=6.0):
        del device
        calls.append((seek_seconds, timeout_seconds, pixel_format))
        source = bright_bytes_path if seek_seconds > 0 else dark_bytes_path
        output_path.write_bytes(source.read_bytes())
        return SimpleNamespace(returncode=0, stderr="", stdout="")

    monkeypatch.setattr(camera, "_run_ffmpeg_capture", _fake_run_ffmpeg_capture)

    capture = camera.capture_snapshot(background=False)

    assert capture.backend == "ffmpeg_avfoundation"
    assert _camera_frame_luma_mean(base64.b64decode(capture.image_data_url.split(",", 1)[1])) > 100.0
    assert capture.warmup_retry_used is True
    assert capture.source_frame.metadata["camera_warmup_retry_used"] is True
    assert calls[0][0] == 0.0
    assert calls[1][0] > 0.0


def test_native_tools_runtime_dir_targets_repo_runtime_not_src_runtime():
    repo_root = Path(__file__).resolve().parents[2]
    source_path = repo_root / "src/embodied_stack/desktop/native_helpers/apple_camera_snapshot.swift"
    runtime_dir = _native_tools_runtime_dir(source_path)

    assert runtime_dir == repo_root / "runtime/native_tools"
