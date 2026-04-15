from embodied_stack.config import Settings


def macos_voice_name(settings: Settings) -> str:
    return settings.macos_tts_voice


__all__ = ["macos_voice_name"]
