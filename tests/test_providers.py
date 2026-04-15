"""Tests for backend capability helpers."""

from unittest.mock import patch

from reachy_mini_conversation_app.config import config
from reachy_mini_conversation_app.providers import (
    DEFAULT_LOCAL_TTS_VOICE,
    get_backend_capabilities,
    get_runtime_disabled_tools,
    get_macos_tts_voices,
)


def test_get_backend_capabilities_for_openai() -> None:
    """OpenAI remains the default cloud provider shape."""
    with patch.object(config, "BACKEND_PROVIDER", "openai"):
        capabilities = get_backend_capabilities()

    assert capabilities.provider == "openai"
    assert capabilities.requires_api_key is True
    assert capabilities.api_key_env_name == "OPENAI_API_KEY"
    assert capabilities.default_voice == "cedar"


def test_get_backend_capabilities_for_ollama_uses_local_voice_list() -> None:
    """Ollama should expose macOS system voices and no API key requirement."""
    get_macos_tts_voices.cache_clear()
    with patch.object(config, "BACKEND_PROVIDER", "ollama"), patch.object(
        config,
        "LOCAL_TTS_VOICE",
        "Ava",
    ), patch(
        "reachy_mini_conversation_app.providers.list_macos_say_voices",
        return_value=["Ava", "Samantha"],
    ):
        get_macos_tts_voices.cache_clear()
        capabilities = get_backend_capabilities()

    assert capabilities.provider == "ollama"
    assert capabilities.requires_api_key is False
    assert capabilities.api_key_env_name is None
    assert capabilities.default_voice == "Ava"
    assert capabilities.fallback_voices == ["Ava", "Samantha"]


def test_get_backend_capabilities_for_ollama_falls_back_when_voice_missing() -> None:
    """An unavailable LOCAL_TTS_VOICE should fall back to an installed voice for UI defaults."""
    get_macos_tts_voices.cache_clear()
    with patch.object(config, "BACKEND_PROVIDER", "ollama"), patch.object(
        config,
        "LOCAL_TTS_VOICE",
        DEFAULT_LOCAL_TTS_VOICE,
    ), patch(
        "reachy_mini_conversation_app.providers.list_macos_say_voices",
        return_value=["Allison"],
    ):
        get_macos_tts_voices.cache_clear()
        capabilities = get_backend_capabilities()

    assert capabilities.default_voice == "Allison"


def test_get_runtime_disabled_tools_disables_emotions_for_uncached_ollama_runtime() -> None:
    """Local Ollama mode should skip network-backed emotion tools when assets are not cached."""
    with patch.object(config, "BACKEND_PROVIDER", "ollama"), patch(
        "reachy_mini_conversation_app.providers.local_emotion_assets_available",
        return_value=False,
    ):
        disabled = get_runtime_disabled_tools()

    assert disabled == {"play_emotion", "stop_emotion"}
