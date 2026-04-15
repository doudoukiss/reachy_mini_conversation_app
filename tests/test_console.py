"""Tests for the headless console stream."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from reachy_mini.media.media_manager import MediaBackend
from reachy_mini_conversation_app.console import LocalStream


def test_clear_audio_queue_prefers_clear_player_when_available() -> None:
    """Local GStreamer audio should use the lower-level player flush when available."""
    handler = MagicMock()
    audio = SimpleNamespace(
        clear_player=MagicMock(),
        clear_output_buffer=MagicMock(),
    )
    robot = SimpleNamespace(media=SimpleNamespace(audio=audio, backend=MediaBackend.LOCAL))
    stream = LocalStream(handler, robot)

    stream.clear_audio_queue()

    audio.clear_player.assert_called_once()
    audio.clear_output_buffer.assert_not_called()
    assert isinstance(handler.output_queue, asyncio.Queue)
    assert handler.output_queue.empty()


def test_clear_audio_queue_uses_output_buffer_for_webrtc() -> None:
    """WebRTC audio should flush queued playback via the output buffer API."""
    handler = MagicMock()
    audio = SimpleNamespace(
        clear_player=MagicMock(),
        clear_output_buffer=MagicMock(),
    )
    robot = SimpleNamespace(media=SimpleNamespace(audio=audio, backend=MediaBackend.WEBRTC))
    stream = LocalStream(handler, robot)

    stream.clear_audio_queue()

    audio.clear_output_buffer.assert_called_once()
    audio.clear_player.assert_not_called()
    assert isinstance(handler.output_queue, asyncio.Queue)
    assert handler.output_queue.empty()


def test_clear_audio_queue_falls_back_when_backend_is_unknown() -> None:
    """Unknown backends should still best-effort flush pending playback."""
    handler = MagicMock()
    audio = SimpleNamespace(clear_output_buffer=MagicMock())
    robot = SimpleNamespace(media=SimpleNamespace(audio=audio, backend=None))
    stream = LocalStream(handler, robot)

    stream.clear_audio_queue()

    audio.clear_output_buffer.assert_called_once()
    assert isinstance(handler.output_queue, asyncio.Queue)
    assert handler.output_queue.empty()


def test_launch_skips_api_key_wait_for_ollama(monkeypatch: MagicMock) -> None:
    """Local Ollama mode should not block on credential setup before starting media."""
    handler = MagicMock()
    handler.start_up = AsyncMock()
    handler.shutdown = AsyncMock()
    robot = SimpleNamespace(
        media=SimpleNamespace(
            start_recording=MagicMock(),
            start_playing=MagicMock(),
            stop_recording=MagicMock(),
            stop_playing=MagicMock(),
        )
    )
    stream = LocalStream(handler, robot)

    async def _done() -> None:
        return None

    monkeypatch.setattr("reachy_mini_conversation_app.console.get_backend_provider", lambda: "ollama")
    monkeypatch.setattr(
        "reachy_mini_conversation_app.console.get_backend_capabilities",
        lambda: SimpleNamespace(requires_api_key=False, api_key_env_name=None),
    )
    monkeypatch.setattr("reachy_mini_conversation_app.console.time.sleep", lambda _seconds: None)
    monkeypatch.setattr(stream, "_init_settings_ui_if_needed", MagicMock())
    monkeypatch.setattr(stream, "record_loop", _done)
    monkeypatch.setattr(stream, "play_loop", _done)

    stream.launch()

    robot.media.start_recording.assert_called_once()
    robot.media.start_playing.assert_called_once()
    handler.start_up.assert_awaited_once()
    handler.shutdown.assert_awaited_once()
