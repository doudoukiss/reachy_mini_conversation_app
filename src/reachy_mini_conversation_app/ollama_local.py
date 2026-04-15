"""Local Ollama-backed conversation handler for macOS."""

from __future__ import annotations

import json
import uuid
import base64
import time
import asyncio
import logging
import shutil
from datetime import datetime
from typing import Any, Optional

import gradio as gr
import numpy as np
from openai import AsyncOpenAI
from fastrtc import AdditionalOutputs, AsyncStreamHandler, wait_for_item, audio_to_int16
from numpy.typing import NDArray
from scipy.signal import resample

from reachy_mini_conversation_app.config import config
from reachy_mini_conversation_app.prompts import (
    augment_session_instructions,
    get_session_instructions,
    get_session_voice,
)
from reachy_mini_conversation_app.providers import get_backend_capabilities
from reachy_mini_conversation_app.local_audio import (
    LOCAL_TTS_SAMPLE_RATE,
    WHISPER_SAMPLE_RATE,
    EnergyTurnDetector,
    MacOSTTSSynthesizer,
    WhisperCppTranscriber,
    resolve_macos_say_voice,
    split_audio_chunks,
)
from reachy_mini_conversation_app.tools.background_tool_manager import (
    BackgroundToolManager,
    ToolCallRoutine,
    ToolNotification,
)
from reachy_mini_conversation_app.tools.core_tools import get_chat_tool_specs


logger = logging.getLogger(__name__)

LOCAL_OUTPUT_SAMPLE_RATE = LOCAL_TTS_SAMPLE_RATE
LOCAL_INPUT_SAMPLE_RATE = WHISPER_SAMPLE_RATE


def _content_to_text(content: Any) -> str:
    """Extract plain text from a chat completion content payload."""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                text = item.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return " ".join(parts).strip()
    return ""


def _parse_tool_args(args_json: str) -> dict[str, Any]:
    """Parse function arguments JSON safely."""
    try:
        parsed = json.loads(args_json or "{}")
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


class OllamaLocalHandler(AsyncStreamHandler):
    """Turn-based local conversation handler using Ollama + whisper.cpp + macOS say."""

    def __init__(self, deps: Any, gradio_mode: bool = False, instance_path: Optional[str] = None):
        """Initialize the local handler."""
        super().__init__(
            expected_layout="mono",
            output_sample_rate=LOCAL_OUTPUT_SAMPLE_RATE,
            input_sample_rate=LOCAL_INPUT_SAMPLE_RATE,
        )
        self.deps = deps
        self.gradio_mode = gradio_mode
        self.instance_path = instance_path
        self.output_queue: "asyncio.Queue[tuple[int, NDArray[np.int16]] | AdditionalOutputs]" = asyncio.Queue()
        self.last_activity_time = time.monotonic()
        self.start_time = time.monotonic()
        self._connected_event = asyncio.Event()
        self._conversation_lock = asyncio.Lock()
        self._turn_task: asyncio.Task[None] | None = None
        self._idle_task: asyncio.Task[None] | None = None
        self._playback_blocked_until = 0.0
        self._tool_notifications: asyncio.Queue[ToolNotification] = asyncio.Queue()
        self.tool_manager = BackgroundToolManager()
        self.turn_detector = EnergyTurnDetector()
        self.client: AsyncOpenAI | None = None

        capabilities = get_backend_capabilities()
        self.available_voices = list(capabilities.fallback_voices)
        self.default_voice = capabilities.default_voice
        self.transcriber = WhisperCppTranscriber(
            binary_path=config.WHISPER_CPP_BIN,
            model_path=config.WHISPER_CPP_MODEL,
        )
        self.tts = MacOSTTSSynthesizer(default_voice=self.default_voice)
        self._conversation_messages: list[dict[str, Any]] = []
        self._reset_conversation_history()

    def copy(self) -> "OllamaLocalHandler":
        """Create a copy of the handler."""
        return OllamaLocalHandler(self.deps, self.gradio_mode, self.instance_path)

    async def start_up(self) -> None:
        """Initialize the local backend and verify local dependencies."""
        self.client = AsyncOpenAI(
            base_url=config.OLLAMA_BASE_URL,
            api_key="ollama",
        )
        await self._run_preflight_checks()
        self.tool_manager.start_up(tool_callbacks=[self._queue_tool_notification])
        self._connected_event.set()
        logger.info(
            "Ollama local backend ready: model=%s base_url=%s whisper=%s",
            config.MODEL_NAME,
            config.OLLAMA_BASE_URL,
            config.WHISPER_CPP_BIN,
        )

    async def _run_preflight_checks(self) -> None:
        """Validate the Ollama, whisper.cpp, and TTS dependencies."""
        if self.client is None:
            raise RuntimeError("Ollama client not initialized")

        self.transcriber.validate()

        say_bin = shutil.which("say")
        if say_bin is None:
            raise RuntimeError("macOS 'say' command not found. Local TTS requires /usr/bin/say.")

        self.available_voices = await self.get_available_voices()
        if not self.available_voices:
            raise RuntimeError("No macOS voices are available from 'say -v ?'.")

        if config.LOCAL_TTS_VOICE and config.LOCAL_TTS_VOICE not in self.available_voices:
            raise RuntimeError(
                f"Configured LOCAL_TTS_VOICE '{config.LOCAL_TTS_VOICE}' is not installed on this Mac."
            )

        try:
            models = await self.client.models.list()
        except Exception as exc:
            raise RuntimeError(
                f"Failed to reach Ollama at {config.OLLAMA_BASE_URL}: {exc}"
            ) from exc

        available_model_ids = [getattr(model, "id", "") for model in getattr(models, "data", [])]
        if config.MODEL_NAME not in available_model_ids:
            raise RuntimeError(
                f"Ollama model '{config.MODEL_NAME}' is not installed. "
                "Run scripts/setup-local-mac.sh or 'ollama pull <model>'."
            )

    def _reset_conversation_history(self) -> None:
        """Reset the conversation to the current personality prompt."""
        self._conversation_messages = [
            {
                "role": "system",
                "content": augment_session_instructions(
                    get_session_instructions(),
                    robot_runtime=self.deps.robot_runtime,
                ),
            }
        ]

    async def apply_personality(self, profile: str | None) -> str:
        """Apply a new personality and reset local conversation history."""
        try:
            from reachy_mini_conversation_app.config import set_custom_profile

            set_custom_profile(profile)
            async with self._conversation_lock:
                self._reset_conversation_history()
            return "Applied personality and cleared local conversation history."
        except Exception as exc:
            logger.error("Error applying personality '%s': %s", profile, exc)
            return f"Failed to apply personality: {exc}"

    async def receive(self, frame: tuple[int, NDArray[np.int16]]) -> None:
        """Receive audio from the microphone and cut completed speech turns."""
        if self._turn_task is not None and not self._turn_task.done():
            return

        now = time.monotonic()
        if now < self._playback_blocked_until:
            self.turn_detector.reset()
            self.deps.movement_manager.set_listening(False)
            return

        input_sample_rate, audio_frame = frame
        audio_data = audio_frame
        if audio_data.ndim == 2:
            if audio_data.shape[1] > audio_data.shape[0]:
                audio_data = audio_data.T
            if audio_data.shape[1] > 1:
                audio_data = audio_data[:, 0]
            else:
                audio_data = audio_data[:, 0]

        if input_sample_rate != self.input_sample_rate:
            audio_data = resample(
                audio_data,
                int(len(audio_data) * self.input_sample_rate / input_sample_rate),
            )

        pcm = audio_to_int16(audio_data)
        speech_started, completed_turn = self.turn_detector.process_chunk(pcm)
        if speech_started:
            self.last_activity_time = now
            self.deps.movement_manager.set_listening(True)

        if completed_turn is not None:
            self.deps.movement_manager.set_listening(False)
            self.last_activity_time = time.monotonic()
            self._turn_task = asyncio.create_task(
                self._process_audio_turn(completed_turn),
                name="ollama-local-turn",
            )

    async def _process_audio_turn(self, audio_turn: NDArray[np.int16]) -> None:
        """Transcribe a completed turn, then run the model/tool loop."""
        try:
            transcript = await asyncio.to_thread(
                self.transcriber.transcribe,
                audio_turn,
                self.input_sample_rate,
            )
            transcript = transcript.strip()
            if not transcript:
                logger.debug("No transcript returned for completed local turn")
                return

            await self.output_queue.put(AdditionalOutputs({"role": "user", "content": transcript}))

            async with self._conversation_lock:
                self._conversation_messages.append({"role": "user", "content": transcript})
                await self._run_model_turn(idle_turn=False)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception("Local audio turn failed: %s", exc)
            await self.output_queue.put(
                AdditionalOutputs({"role": "assistant", "content": f"[error] {exc}"})
            )

    async def _queue_tool_notification(self, bg_tool: ToolNotification) -> None:
        """Fan completed tool notifications into a handler-local queue."""
        await self._tool_notifications.put(bg_tool)

    async def _run_tool_and_wait(
        self,
        *,
        tool_name: str,
        args_json: str,
        call_id: str,
        idle_turn: bool,
    ) -> ToolNotification:
        """Run a tool through the background tool manager and wait for completion."""
        bg_tool = await self.tool_manager.start_tool(
            call_id=call_id,
            tool_call_routine=ToolCallRoutine(
                tool_name=tool_name,
                args_json_str=args_json,
                deps=self.deps,
            ),
            is_idle_tool_call=idle_turn,
        )
        await self.output_queue.put(
            AdditionalOutputs(
                {
                    "role": "assistant",
                    "content": f"🛠️ Used tool {tool_name} with args {args_json}. Tool ID: {bg_tool.tool_id}",
                },
            ),
        )
        while True:
            notification = await self._tool_notifications.get()
            if notification.id == call_id:
                return notification

    async def _run_model_turn(self, *, idle_turn: bool, extra_tool_exclusions: list[str] | None = None) -> None:
        """Run the assistant/tool loop until the model returns final text."""
        if self.client is None:
            raise RuntimeError("Ollama client not initialized")

        tool_exclusions = list(extra_tool_exclusions or [])
        while True:
            turn_started_at = time.monotonic()
            response = await self.client.chat.completions.create(
                model=config.MODEL_NAME,
                messages=self._conversation_messages,
                tools=get_chat_tool_specs(exclusion_list=tool_exclusions),
                tool_choice="auto",
                reasoning_effort="none",
                temperature=0.2,
                max_tokens=256,
            )
            logger.debug("Ollama completion returned in %.2fs", time.monotonic() - turn_started_at)

            message = response.choices[0].message
            message_text = _content_to_text(message.content)
            tool_calls = list(message.tool_calls or [])

            if tool_calls:
                assistant_message = {
                    "role": "assistant",
                    "content": message_text,
                    "tool_calls": [
                        {
                            "id": tool_call.id or str(uuid.uuid4()),
                            "type": "function",
                            "function": {
                                "name": tool_call.function.name,
                                "arguments": (
                                    tool_call.function.arguments
                                    if isinstance(tool_call.function.arguments, str)
                                    else json.dumps(tool_call.function.arguments or {})
                                ),
                            },
                        }
                        for tool_call in tool_calls
                    ],
                }
                self._conversation_messages.append(assistant_message)

                image_follow_up: dict[str, Any] | None = None
                image_tool_name: str | None = None
                for tool_call in tool_calls:
                    tool_name = tool_call.function.name
                    if not isinstance(tool_name, str):
                        logger.warning("Skipping invalid tool call name=%r", tool_name)
                        continue
                    args_json = (
                        tool_call.function.arguments
                        if isinstance(tool_call.function.arguments, str)
                        else json.dumps(tool_call.function.arguments or {})
                    )
                    call_id = tool_call.id or str(uuid.uuid4())

                    notification = await self._run_tool_and_wait(
                        tool_name=tool_name,
                        args_json=args_json,
                        call_id=call_id,
                        idle_turn=idle_turn,
                    )
                    tool_result = self._notification_to_result(notification)
                    history_result = dict(tool_result)
                    if "b64_im" in history_result:
                        history_result["b64_im"] = "[image forwarded to the next multimodal user message]"
                    self._conversation_messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": call_id,
                            "name": tool_name,
                            "content": json.dumps(history_result),
                        },
                    )
                    await self.output_queue.put(
                        AdditionalOutputs(
                            {
                                "role": "assistant",
                                "content": json.dumps(tool_result),
                                "metadata": {
                                    "title": f"🛠️ Used tool {tool_name}",
                                    "status": "done",
                                },
                            },
                        ),
                    )

                    if "b64_im" in tool_result:
                        self._emit_camera_preview()
                        question = _parse_tool_args(args_json).get("question") or "What is shown in this image?"
                        image_follow_up = {
                            "role": "user",
                            "content": [
                                {
                                    "type": "text",
                                    "text": str(question),
                                },
                                {
                                    "type": "image_url",
                                    "image_url": f"data:image/jpeg;base64,{tool_result['b64_im']}",
                                },
                            ],
                        }
                        image_tool_name = tool_name

                if image_follow_up is not None:
                    self._conversation_messages.append(image_follow_up)
                    if image_tool_name is not None and image_tool_name not in tool_exclusions:
                        tool_exclusions.append(image_tool_name)
                continue

            final_text = message_text or "I don't have a response right now."
            self._conversation_messages.append({"role": "assistant", "content": final_text})
            if not idle_turn:
                await self.output_queue.put(AdditionalOutputs({"role": "assistant", "content": final_text}))
                await self._enqueue_tts(final_text)
            return

    def _notification_to_result(self, notification: ToolNotification) -> dict[str, Any]:
        """Normalize a tool notification into a tool result payload."""
        if notification.error is not None:
            return {"error": notification.error}
        if notification.result is not None:
            return notification.result
        return {"error": "No result returned from tool execution"}

    def _emit_camera_preview(self) -> None:
        """Show the latest camera frame in the UI when available."""
        if self.deps.camera_worker is None:
            return
        np_img = self.deps.camera_worker.get_latest_frame()
        if np_img is None:
            return
        rgb_frame = np.ascontiguousarray(np_img[..., ::-1])
        img = gr.Image(value=rgb_frame)
        self.output_queue.put_nowait(AdditionalOutputs({"role": "assistant", "content": img}))

    async def _enqueue_tts(self, text: str) -> None:
        """Synthesize assistant speech and enqueue it for playback."""
        voice = self._resolve_tts_voice()
        sample_rate, audio = await asyncio.to_thread(self.tts.synthesize, text, voice)
        chunks = split_audio_chunks(audio)
        total_duration_s = len(audio) / sample_rate if sample_rate > 0 else 0.0
        self._playback_blocked_until = time.monotonic() + total_duration_s + 0.25
        for chunk in chunks:
            if self.deps.head_wobbler is not None:
                self.deps.head_wobbler.feed(base64.b64encode(chunk.tobytes()).decode("utf-8"))
            await self.output_queue.put((sample_rate, chunk))

    def _resolve_tts_voice(self) -> str:
        """Resolve the effective voice for the current profile."""
        requested_voice = get_session_voice(default=self.default_voice)
        return resolve_macos_say_voice(requested_voice, self.available_voices, self.default_voice)

    async def emit(self) -> tuple[int, NDArray[np.int16]] | AdditionalOutputs | None:
        """Emit playback frames or chat outputs."""
        idle_duration = time.monotonic() - self.last_activity_time
        if (
            idle_duration > 15.0
            and self.deps.movement_manager.is_idle()
            and (self._turn_task is None or self._turn_task.done())
            and (self._idle_task is None or self._idle_task.done())
        ):
            self._idle_task = asyncio.create_task(
                self.send_idle_signal(idle_duration),
                name="ollama-local-idle",
            )
            self.last_activity_time = time.monotonic()

        return await wait_for_item(self.output_queue)  # type: ignore[no-any-return]

    async def shutdown(self) -> None:
        """Shutdown the handler."""
        if self._turn_task is not None and not self._turn_task.done():
            self._turn_task.cancel()
            try:
                await self._turn_task
            except asyncio.CancelledError:
                pass

        if self._idle_task is not None and not self._idle_task.done():
            self._idle_task.cancel()
            try:
                await self._idle_task
            except asyncio.CancelledError:
                pass

        await self.tool_manager.shutdown()

        while not self.output_queue.empty():
            try:
                self.output_queue.get_nowait()
            except asyncio.QueueEmpty:
                break

    async def send_idle_signal(self, idle_duration: float) -> None:
        """Send a local idle prompt to the model."""
        timestamp_msg = (
            f"[Idle time update: {self.format_timestamp()} - No activity for {idle_duration:.1f}s] "
            "You've been idle for a while. Feel free to get creative - dance, show an emotion, "
            "look around, do nothing, or just be yourself!"
        )
        async with self._conversation_lock:
            self._conversation_messages.append({"role": "user", "content": timestamp_msg})
            await self._run_model_turn(idle_turn=True)

    async def get_available_voices(self) -> list[str]:
        """Return the available local voices."""
        return list(self.available_voices)

    def format_timestamp(self) -> str:
        """Format current timestamp with date, time, and elapsed seconds."""
        loop_time = time.monotonic()
        elapsed_seconds = loop_time - self.start_time
        dt = datetime.now()
        return f"[{dt.strftime('%Y-%m-%d %H:%M:%S')} | +{elapsed_seconds:.1f}s]"
