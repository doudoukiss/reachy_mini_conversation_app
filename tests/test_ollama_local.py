"""Tests for the local Ollama handler."""

from __future__ import annotations

import asyncio
import copy
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest
from fastrtc import AdditionalOutputs

from reachy_mini_conversation_app.ollama_local import OllamaLocalHandler
from reachy_mini_conversation_app.tools.background_tool_manager import ToolNotification
from reachy_mini_conversation_app.tools.tool_constants import ToolState
from reachy_mini_conversation_app.tools.core_tools import ToolDependencies


class FakeCompletions:
    """Captures chat completion calls and replays canned responses."""

    def __init__(self, responses: list[object]) -> None:
        self._responses = list(responses)
        self.calls: list[dict] = []

    async def create(self, **kwargs: object) -> object:
        self.calls.append(copy.deepcopy(dict(kwargs)))
        return self._responses.pop(0)


class FakeChat:
    """Namespace matching the OpenAI client shape."""

    def __init__(self, responses: list[object]) -> None:
        self.completions = FakeCompletions(responses)


class FakeClient:
    """Minimal OpenAI-compatible async client stub."""

    def __init__(self, responses: list[object]) -> None:
        self.chat = FakeChat(responses)


def _build_handler() -> OllamaLocalHandler:
    deps = ToolDependencies(
        reachy_mini=MagicMock(),
        movement_manager=MagicMock(),
        camera_worker=MagicMock(),
    )
    with patch("reachy_mini_conversation_app.ollama_local.get_session_instructions", return_value="test system"):
        handler = OllamaLocalHandler(deps)
    handler.available_voices = ["Ava"]
    handler.default_voice = "Ava"
    return handler


def _text_response(text: str) -> object:
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content=text,
                    tool_calls=[],
                )
            )
        ]
    )


def _tool_response(tool_name: str, arguments: str, call_id: str) -> object:
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(
                    content="",
                    tool_calls=[
                        SimpleNamespace(
                            id=call_id,
                            function=SimpleNamespace(name=tool_name, arguments=arguments),
                        )
                    ],
                )
            )
        ]
    )


@pytest.mark.asyncio
async def test_run_model_turn_executes_tool_then_speaks() -> None:
    """The local handler should loop through a tool call before producing speech."""
    handler = _build_handler()
    handler.client = FakeClient(
        [
            _tool_response("move_head", '{"direction":"left"}', "call_move_1"),
            _text_response("Looking left now."),
        ]
    )
    handler._run_tool_and_wait = AsyncMock(  # type: ignore[method-assign]
        return_value=ToolNotification(
            id="call_move_1",
            tool_name="move_head",
            is_idle_tool_call=False,
            status=ToolState.COMPLETED,
            result={"status": "queued", "direction": "left"},
        )
    )
    handler._enqueue_tts = AsyncMock()  # type: ignore[method-assign]

    handler._conversation_messages.append({"role": "user", "content": "look left"})
    await handler._run_model_turn(idle_turn=False)

    fake_client = handler.client
    assert isinstance(fake_client, FakeClient)
    assert len(fake_client.chat.completions.calls) == 2
    assert fake_client.chat.completions.calls[0]["reasoning_effort"] == "none"
    assert fake_client.chat.completions.calls[0]["max_tokens"] == 256
    assert handler._conversation_messages[-1]["content"] == "Looking left now."
    handler._enqueue_tts.assert_awaited_once_with("Looking left now.")


@pytest.mark.asyncio
async def test_run_model_turn_replays_camera_image_without_reoffering_camera_tool() -> None:
    """Camera follow-up requests should attach the image and remove the camera tool on retry."""
    handler = _build_handler()
    handler.client = FakeClient(
        [
            _tool_response("camera", '{"question":"What do you see?"}', "call_cam_1"),
            _text_response("I can see the camera image."),
        ]
    )
    handler._run_tool_and_wait = AsyncMock(  # type: ignore[method-assign]
        return_value=ToolNotification(
            id="call_cam_1",
            tool_name="camera",
            is_idle_tool_call=False,
            status=ToolState.COMPLETED,
            result={"b64_im": "YWJj"},
        )
    )
    handler._enqueue_tts = AsyncMock()  # type: ignore[method-assign]
    handler._emit_camera_preview = MagicMock()  # type: ignore[method-assign]

    handler._conversation_messages.append({"role": "user", "content": "show me the camera"})
    await handler._run_model_turn(idle_turn=False)

    fake_client = handler.client
    assert isinstance(fake_client, FakeClient)
    assert len(fake_client.chat.completions.calls) == 2

    retry_call = fake_client.chat.completions.calls[1]
    tool_names = [tool["function"]["name"] for tool in retry_call["tools"]]
    assert "camera" not in tool_names

    retry_messages = retry_call["messages"]
    image_message = retry_messages[-1]
    assert image_message["role"] == "user"
    assert image_message["content"][0]["text"] == "What do you see?"
    assert image_message["content"][1]["image_url"].startswith("data:image/jpeg;base64,")


@pytest.mark.asyncio
async def test_process_audio_turn_emits_user_transcript_before_model_call() -> None:
    """Completed local turns should be transcribed and emitted to the UI."""
    handler = _build_handler()
    handler.transcriber.transcribe = MagicMock(return_value="hello there")  # type: ignore[method-assign]
    handler._run_model_turn = AsyncMock()  # type: ignore[method-assign]

    await handler._process_audio_turn(np.array([1, 2, 3, 4], dtype=np.int16))

    output = await handler.output_queue.get()
    assert isinstance(output, AdditionalOutputs)
    message = output.args[0]
    assert message["role"] == "user"
    assert message["content"] == "hello there"
    assert handler._conversation_messages[-1] == {"role": "user", "content": "hello there"}
    handler._run_model_turn.assert_awaited_once_with(idle_turn=False)


def test_resolve_tts_voice_falls_back_to_installed_local_voice() -> None:
    """Profile voices from cloud backends should gracefully fall back locally."""
    handler = _build_handler()
    handler.available_voices = ["Ava"]
    handler.default_voice = "Ava"

    with patch("reachy_mini_conversation_app.ollama_local.get_session_voice", return_value="cedar"):
        assert handler._resolve_tts_voice() == "Ava"
