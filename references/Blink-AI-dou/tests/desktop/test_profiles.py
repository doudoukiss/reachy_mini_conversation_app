from __future__ import annotations

from embodied_stack.config import Settings
from embodied_stack.desktop.profiles import (
    apply_desktop_profile,
    resolve_embodiment_profile,
    resolve_model_profile,
    resolve_voice_profile,
    summarize_desktop_profile,
)
from embodied_stack.shared.models import RobotMode, VoiceRuntimeMode


def test_cloud_demo_profile_prefers_provider_backends():
    settings = Settings(
        _env_file=None,
        blink_model_profile="cloud_demo",
        blink_voice_profile="offline_stub",
        ollama_base_url="http://127.0.0.1:9",
        ollama_timeout_seconds=0.1,
    )

    resolved = apply_desktop_profile(settings)

    assert resolved.brain_dialogue_backend == "rule_based"
    assert resolved.brain_voice_backend == "openai"
    assert resolved.perception_default_provider == "native_camera_snapshot"
    assert resolved.live_voice_default_mode == "stub_demo"


def test_desktop_local_alias_maps_to_companion_live_profile():
    settings = Settings(
        _env_file=None,
        blink_model_profile="desktop_local",
        blink_voice_profile="desktop_local",
    )

    model_profile = resolve_model_profile(settings)
    voice_profile = resolve_voice_profile(settings, say_available=False, native_available=False)

    assert model_profile is not None
    assert model_profile.name == "companion_live"
    assert voice_profile.name == "desktop_local"
    assert voice_profile.live_voice_mode == VoiceRuntimeMode.STUB_DEMO


def test_desktop_local_voice_profile_prefers_native_mode_when_available():
    settings = Settings(
        _env_file=None,
        blink_voice_profile="desktop_local",
    )

    voice_profile = resolve_voice_profile(settings, say_available=True, native_available=True)

    assert voice_profile.name == "desktop_local"
    assert voice_profile.live_voice_mode == VoiceRuntimeMode.DESKTOP_NATIVE
    assert voice_profile.microphone_expected is True


def test_embodiment_profile_maps_runtime_mode_to_clear_demo_mode():
    settings = Settings(
        _env_file=None,
        blink_runtime_mode=RobotMode.DESKTOP_SERIAL_BODY,
        blink_model_profile="cloud_demo",
    )

    embodiment = resolve_embodiment_profile(settings)

    assert embodiment.name == "serial_body"
    assert embodiment.body_driver.value == "serial"
    assert embodiment.live_transport_expected is True


def test_desktop_profile_summary_exposes_composed_model_and_body_status():
    settings = Settings(
        _env_file=None,
        blink_runtime_mode=RobotMode.DESKTOP_BODYLESS,
        blink_model_profile="desktop_local",
        blink_voice_profile="desktop_local",
        perception_multimodal_api_key=None,
    )

    summary = summarize_desktop_profile(settings, say_available=True)

    assert summary.profile_label == "companion_live + bodyless"
    assert summary.embodiment_profile == "bodyless"
    assert summary.provider_status == "hybrid_local_fallback"
    assert summary.backend_profile == "companion_live"
