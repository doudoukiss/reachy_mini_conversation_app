from __future__ import annotations

from embodied_stack.brain.live_voice import LiveVoiceRuntimeManager
from embodied_stack.brain.voice import VoicePipeline, VoicePipelineFactory
from embodied_stack.config import Settings
from embodied_stack.desktop.profiles import resolve_voice_profile
from embodied_stack.shared.models import VoiceRuntimeMode


def build_live_voice_manager(settings: Settings) -> LiveVoiceRuntimeManager:
    return LiveVoiceRuntimeManager(
        settings=settings,
        macos_voice_name=settings.macos_tts_voice,
        macos_rate=settings.macos_tts_rate,
    )


def resolve_live_voice_mode(settings: Settings) -> VoiceRuntimeMode:
    return resolve_voice_profile(settings).live_voice_mode

__all__ = [
    "VoicePipeline",
    "VoicePipelineFactory",
    "build_live_voice_manager",
    "resolve_live_voice_mode",
]
