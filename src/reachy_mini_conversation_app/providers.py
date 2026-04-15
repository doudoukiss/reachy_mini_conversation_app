"""Backend/provider capability helpers."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from functools import lru_cache
from typing import Literal

from huggingface_hub import snapshot_download
from huggingface_hub.errors import LocalEntryNotFoundError

from .config import AVAILABLE_VOICES, GEMINI_AVAILABLE_VOICES, config
from .local_audio import list_macos_say_voices


logger = logging.getLogger(__name__)

BackendProvider = Literal["openai", "gemini", "ollama"]
LOCAL_EMOTIONS_DATASET = "pollen-robotics/reachy-mini-emotions-library"
DEFAULT_LOCAL_TTS_VOICE = "Samantha"


@dataclass(frozen=True)
class BackendCapabilities:
    """Declarative properties for a backend provider."""

    provider: BackendProvider
    requires_api_key: bool
    api_key_env_name: str | None
    api_key_label: str | None
    default_voice: str
    fallback_voices: list[str]


def get_backend_provider() -> BackendProvider:
    """Return the configured backend provider."""
    provider = str(config.BACKEND_PROVIDER).strip().lower()
    if provider not in {"openai", "gemini", "ollama"}:
        raise RuntimeError(
            f"Unsupported BACKEND_PROVIDER={provider!r}. Expected one of: openai, gemini, ollama.",
        )
    return provider  # type: ignore[return-value]


@lru_cache(maxsize=1)
def get_macos_tts_voices() -> tuple[str, ...]:
    """Return the discovered macOS system voices."""
    return tuple(list_macos_say_voices())


def get_backend_capabilities(provider: BackendProvider | None = None) -> BackendCapabilities:
    """Return the capabilities for the active provider."""
    active_provider = provider or get_backend_provider()
    if active_provider == "gemini":
        return BackendCapabilities(
            provider="gemini",
            requires_api_key=True,
            api_key_env_name="GEMINI_API_KEY",
            api_key_label="Gemini API Key",
            default_voice="Kore",
            fallback_voices=list(GEMINI_AVAILABLE_VOICES),
        )

    if active_provider == "ollama":
        voices = list(get_macos_tts_voices())
        default_voice = str(config.LOCAL_TTS_VOICE or DEFAULT_LOCAL_TTS_VOICE).strip() or DEFAULT_LOCAL_TTS_VOICE
        if default_voice not in voices and voices:
            default_voice = voices[0]
        return BackendCapabilities(
            provider="ollama",
            requires_api_key=False,
            api_key_env_name=None,
            api_key_label=None,
            default_voice=default_voice,
            fallback_voices=voices or [DEFAULT_LOCAL_TTS_VOICE],
        )

    return BackendCapabilities(
        provider="openai",
        requires_api_key=True,
        api_key_env_name="OPENAI_API_KEY",
        api_key_label="OpenAI API Key",
        default_voice="cedar",
        fallback_voices=list(AVAILABLE_VOICES),
    )


def get_configured_api_key() -> str:
    """Return the configured API key for providers that require one."""
    provider = get_backend_provider()
    if provider == "gemini":
        return str(config.GEMINI_API_KEY or "")
    if provider == "openai":
        return str(config.OPENAI_API_KEY or "")
    return ""


def local_emotion_assets_available() -> bool:
    """Return whether emotion assets are already cached locally."""
    try:
        snapshot_download(
            LOCAL_EMOTIONS_DATASET,
            repo_type="dataset",
            local_files_only=True,
        )
        return True
    except LocalEntryNotFoundError:
        return False
    except Exception as exc:
        logger.debug("Could not verify local emotion cache: %s", exc)
        return False


def get_runtime_disabled_tools() -> set[str]:
    """Return tools that should be excluded from the current runtime."""
    if get_backend_provider() != "ollama":
        return set()
    if local_emotion_assets_available():
        return set()
    return {"play_emotion", "stop_emotion"}
