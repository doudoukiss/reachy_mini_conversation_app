from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from embodied_stack.shared.models import RobotEvent, VoiceTurnRequest


class VoicePipelineError(RuntimeError):
    pass


@dataclass
class PreparedVoiceEvent:
    event: RobotEvent
    provider: str
    used_fallback: bool = False
    audio_available: bool = False


class VoicePipeline(Protocol):
    def prepare_event(self, request: VoiceTurnRequest, session_id: str) -> PreparedVoiceEvent:
        ...


class StubVoicePipeline:
    def prepare_event(self, request: VoiceTurnRequest, session_id: str) -> PreparedVoiceEvent:
        text = request.input_text.strip()
        if not text:
            raise VoicePipelineError("voice_input_text_required")
        payload = {"text": text, **request.input_metadata}
        event_kwargs = {
            "event_type": "speech_transcript",
            "session_id": session_id,
            "source": request.source,
            "payload": payload,
        }
        if request.timestamp is not None:
            event_kwargs["timestamp"] = request.timestamp

        return PreparedVoiceEvent(
            event=RobotEvent(**event_kwargs),
            provider="stub_voice",
            audio_available=False,
        )


class OpenAIVoicePipeline:
    """Scaffold for a future OpenAI-backed voice path without requiring live credentials."""

    def __init__(self, *, api_key: str | None, base_url: str, model: str) -> None:
        self.api_key = api_key
        self.base_url = base_url
        self.model = model

    def prepare_event(self, request: VoiceTurnRequest, session_id: str) -> PreparedVoiceEvent:
        if not self.api_key:
            raise VoicePipelineError("openai_api_key_missing")
        text = request.input_text.strip()
        if not text:
            raise VoicePipelineError("voice_input_text_required")
        payload = {
            "text": text,
            "provider_model": self.model,
            "provider_base_url": self.base_url,
            **request.input_metadata,
        }
        event_kwargs = {
            "event_type": "speech_transcript",
            "session_id": session_id,
            "source": "openai_voice_scaffold",
            "payload": payload,
        }
        if request.timestamp is not None:
            event_kwargs["timestamp"] = request.timestamp

        return PreparedVoiceEvent(
            event=RobotEvent(**event_kwargs),
            provider="openai_scaffold",
            audio_available=False,
        )


class FallbackVoicePipeline:
    def __init__(self, primary: VoicePipeline | None, fallback: VoicePipeline) -> None:
        self.primary = primary
        self.fallback = fallback

    def prepare_event(self, request: VoiceTurnRequest, session_id: str) -> PreparedVoiceEvent:
        if self.primary is None:
            return self.fallback.prepare_event(request, session_id)
        try:
            return self.primary.prepare_event(request, session_id)
        except VoicePipelineError:
            prepared = self.fallback.prepare_event(request, session_id)
            prepared.used_fallback = True
            return prepared


class VoicePipelineFactory:
    def __init__(self, *, backend: str, openai_api_key: str | None, openai_base_url: str, openai_model: str) -> None:
        self.backend = backend
        self.openai_api_key = openai_api_key
        self.openai_base_url = openai_base_url
        self.openai_model = openai_model

    def build(self) -> VoicePipeline:
        normalized = self.backend.lower().strip()
        fallback = StubVoicePipeline()
        if normalized == "openai":
            return FallbackVoicePipeline(
                primary=OpenAIVoicePipeline(
                    api_key=self.openai_api_key,
                    base_url=self.openai_base_url,
                    model=self.openai_model,
                ),
                fallback=fallback,
            )
        if normalized == "auto":
            return FallbackVoicePipeline(
                primary=OpenAIVoicePipeline(
                    api_key=self.openai_api_key,
                    base_url=self.openai_base_url,
                    model=self.openai_model,
                ),
                fallback=fallback,
            )
        return fallback
