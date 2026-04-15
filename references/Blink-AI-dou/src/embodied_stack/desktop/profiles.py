from __future__ import annotations

import shutil
from dataclasses import dataclass

from embodied_stack.backends.profiles import backend_candidates_for, resolve_backend_profile_name
from embodied_stack.backends.router import BackendRouter
from embodied_stack.config import Settings
from embodied_stack.desktop.runtime_profile import apply_appliance_profile
from embodied_stack.shared.models import (
    BodyDriverMode,
    PerceptionProviderMode,
    RobotMode,
    RuntimeBackendKind,
    VoiceRuntimeMode,
)


RUNTIME_TO_BODY_DRIVER: dict[RobotMode, BodyDriverMode] = {
    RobotMode.DESKTOP_BODYLESS: BodyDriverMode.BODYLESS,
    RobotMode.DESKTOP_VIRTUAL_BODY: BodyDriverMode.VIRTUAL,
    RobotMode.DESKTOP_SERIAL_BODY: BodyDriverMode.SERIAL,
    RobotMode.TETHERED_FUTURE: BodyDriverMode.TETHERED,
}


@dataclass(frozen=True)
class ModelProfileSpec:
    name: str
    dialogue_backend: str
    voice_backend: str
    perception_provider: PerceptionProviderMode
    note: str
    fallback_perception_provider: PerceptionProviderMode | None = None
    provider_backed: bool = False


@dataclass(frozen=True)
class VoiceProfileSpec:
    name: str
    live_voice_mode: VoiceRuntimeMode
    note: str
    microphone_expected: bool = False
    audio_output_expected: bool = False


@dataclass(frozen=True)
class EmbodimentProfileSpec:
    name: str
    runtime_mode: RobotMode
    body_driver: BodyDriverMode
    note: str
    physical_body_expected: bool = False
    live_transport_expected: bool = False


@dataclass(frozen=True)
class ProviderStatusSummary:
    status: str
    detail: str


@dataclass(frozen=True)
class DesktopProfileSummary:
    profile_label: str
    model_profile: str | None
    backend_profile: str
    voice_profile: str
    embodiment_profile: str
    provider_status: str
    provider_detail: str


MODEL_PROFILES: dict[str, ModelProfileSpec] = {
    "companion_live": ModelProfileSpec(
        name="companion_live",
        dialogue_backend="grsai",
        voice_backend="stub",
        perception_provider=PerceptionProviderMode.NATIVE_CAMERA_SNAPSHOT,
        note="Default hybrid companion profile for daily conversation: local memory and media stay on-device, dialogue prefers the low-latency provider path, and heavy vision is used selectively.",
        provider_backed=True,
    ),
    "m4_pro_companion": ModelProfileSpec(
        name="m4_pro_companion",
        dialogue_backend="ollama",
        voice_backend="stub",
        perception_provider=PerceptionProviderMode.OLLAMA_VISION,
        fallback_perception_provider=PerceptionProviderMode.NATIVE_CAMERA_SNAPSHOT,
        note="Canonical M4 Pro local companion preset using qwen3.5:9b for text and vision plus embeddinggemma:300m for retrieval.",
        provider_backed=False,
    ),
    "cloud_demo": ModelProfileSpec(
        name="cloud_demo",
        dialogue_backend="grsai",
        voice_backend="openai",
        perception_provider=PerceptionProviderMode.MULTIMODAL_LLM,
        note="Provider-backed dialogue, voice scaffold, and multimodal perception with honest fallback when credentials are missing.",
        provider_backed=True,
    ),
    "local_dev": ModelProfileSpec(
        name="local_dev",
        dialogue_backend="ollama",
        voice_backend="stub",
        perception_provider=PerceptionProviderMode.BROWSER_SNAPSHOT,
        note="Local-first development profile using Ollama when available, typed fallback, and browser/fixture perception paths.",
        provider_backed=False,
    ),
    "offline_stub": ModelProfileSpec(
        name="offline_stub",
        dialogue_backend="rule_based",
        voice_backend="stub",
        perception_provider=PerceptionProviderMode.STUB,
        note="Fully local deterministic fallback profile with no provider dependency.",
        provider_backed=False,
    ),
}

MODEL_PROFILE_ALIASES: dict[str, str] = {
    "companion_live": "companion_live",
    "desktop_local": "companion_live",
    "local_companion": "m4_pro_companion",
    "desktop_stub": "offline_stub",
}

VOICE_PROFILE_ALIASES: dict[str, str] = {
    "stub_only": "offline_stub",
    "browser": "browser_live",
}

EMBODIMENT_PROFILES: dict[str, EmbodimentProfileSpec] = {
    "bodyless": EmbodimentProfileSpec(
        name="bodyless",
        runtime_mode=RobotMode.DESKTOP_BODYLESS,
        body_driver=BodyDriverMode.BODYLESS,
        note="No physical body required. Speech, transcript, memory, perception, and world state remain active.",
        physical_body_expected=False,
        live_transport_expected=False,
    ),
    "virtual_body": EmbodimentProfileSpec(
        name="virtual_body",
        runtime_mode=RobotMode.DESKTOP_VIRTUAL_BODY,
        body_driver=BodyDriverMode.VIRTUAL,
        note="Primary current demo path. Semantic embodiment renders through the virtual head preview on the desktop.",
        physical_body_expected=False,
        live_transport_expected=False,
    ),
    "serial_body": EmbodimentProfileSpec(
        name="serial_body",
        runtime_mode=RobotMode.DESKTOP_SERIAL_BODY,
        body_driver=BodyDriverMode.SERIAL,
        note="Future live-head bring-up path. The rest of Blink-AI still runs when serial transport is unavailable.",
        physical_body_expected=True,
        live_transport_expected=True,
    ),
}

EMBODIMENT_PROFILE_BY_RUNTIME: dict[RobotMode, EmbodimentProfileSpec] = {
    spec.runtime_mode: spec for spec in EMBODIMENT_PROFILES.values()
}


def body_driver_mode_for_runtime(settings: Settings) -> BodyDriverMode:
    return RUNTIME_TO_BODY_DRIVER.get(settings.blink_runtime_mode, settings.resolved_body_driver)


def resolve_model_profile(settings: Settings) -> ModelProfileSpec | None:
    configured = settings.blink_model_profile.strip().lower()
    resolved = MODEL_PROFILE_ALIASES.get(configured, configured)
    return MODEL_PROFILES.get(resolved)


def resolve_voice_profile(
    settings: Settings,
    *,
    say_available: bool | None = None,
    native_available: bool | None = None,
) -> VoiceProfileSpec:
    configured = settings.blink_voice_profile.strip().lower()
    resolved = VOICE_PROFILE_ALIASES.get(configured, configured)
    audio_ready = bool(shutil.which("say")) if say_available is None else say_available
    native_ready = bool(shutil.which("ffmpeg") and shutil.which("swiftc")) if native_available is None else native_available
    stt_candidates = backend_candidates_for(
        settings,
        RuntimeBackendKind.SPEECH_TO_TEXT,
        include_legacy_overrides=False,
    )
    tts_candidates = backend_candidates_for(
        settings,
        RuntimeBackendKind.TEXT_TO_SPEECH,
        include_legacy_overrides=False,
    )
    preferred_stt = stt_candidates[0] if stt_candidates else "typed_input"
    preferred_tts = tts_candidates[0] if tts_candidates else "stub_tts"

    if resolved == "browser_live":
        if audio_ready:
            return VoiceProfileSpec(
                name="browser_live",
                live_voice_mode=VoiceRuntimeMode.BROWSER_LIVE_MACOS_SAY,
                note="Browser microphone input with local macOS speech output.",
                microphone_expected=True,
                audio_output_expected=True,
            )
        return VoiceProfileSpec(
            name="browser_live",
            live_voice_mode=VoiceRuntimeMode.BROWSER_LIVE,
            note="Browser microphone input with stubbed local speech output.",
            microphone_expected=True,
            audio_output_expected=False,
        )

    if resolved == "offline_stub":
        return VoiceProfileSpec(
            name="offline_stub",
            live_voice_mode=VoiceRuntimeMode.STUB_DEMO,
            note="Typed-input fallback with stubbed speech output.",
            microphone_expected=False,
            audio_output_expected=False,
        )

    if settings.blink_audio_mode.strip().lower() == "open_mic":
        if preferred_tts == "macos_say" and native_ready and audio_ready and preferred_stt in {"whisper_cpp_local", "apple_speech_local"}:
            return VoiceProfileSpec(
                name="desktop_local",
                live_voice_mode=VoiceRuntimeMode.OPEN_MIC_LOCAL,
                note="Open-mic local companion with continuous microphone polling, local speech output, and honest typed fallback.",
                microphone_expected=True,
                audio_output_expected=True,
            )
        if preferred_tts == "macos_say" and audio_ready:
            return VoiceProfileSpec(
                name="desktop_local",
                live_voice_mode=VoiceRuntimeMode.MACOS_SAY,
                note="Open-mic was requested but live local transcription is unavailable, so the companion is using typed fallback with macOS speech output.",
                microphone_expected=False,
                audio_output_expected=True,
            )

    if preferred_stt == "apple_speech_local" and preferred_tts == "macos_say" and native_ready and audio_ready:
        return VoiceProfileSpec(
            name="desktop_local",
            live_voice_mode=VoiceRuntimeMode.DESKTOP_NATIVE,
            note="Native Mac microphone input with local speaker output and webcam-grounded desktop interaction.",
            microphone_expected=True,
            audio_output_expected=True,
        )

    if preferred_tts == "macos_say" and audio_ready:
        return VoiceProfileSpec(
            name="desktop_local",
            live_voice_mode=VoiceRuntimeMode.MACOS_SAY,
            note="Typed-input local loop with macOS speech output because native microphone capture is unavailable.",
            microphone_expected=False,
            audio_output_expected=True,
        )

    return VoiceProfileSpec(
        name="desktop_local",
        live_voice_mode=VoiceRuntimeMode.STUB_DEMO,
        note="Typed-input local loop with stubbed speech output because native desktop audio is unavailable.",
        microphone_expected=False,
        audio_output_expected=False,
    )


def resolve_embodiment_profile(settings: Settings) -> EmbodimentProfileSpec:
    return EMBODIMENT_PROFILE_BY_RUNTIME.get(
        settings.blink_runtime_mode,
        EmbodimentProfileSpec(
            name=settings.resolved_body_driver.value,
            runtime_mode=settings.blink_runtime_mode,
            body_driver=settings.resolved_body_driver,
            note="Runtime mode is using a non-default embodiment mapping.",
            physical_body_expected=settings.resolved_body_driver == BodyDriverMode.SERIAL,
            live_transport_expected=settings.resolved_body_driver in {BodyDriverMode.SERIAL, BodyDriverMode.TETHERED},
        ),
    )


def summarize_provider_status(
    settings: Settings,
    *,
    model_profile: ModelProfileSpec | None = None,
) -> ProviderStatusSummary:
    resolved_model = model_profile or resolve_model_profile(settings)
    if resolved_model is None:
        return ProviderStatusSummary(
            status="custom_backend",
            detail=f"Custom backend selection: dialogue={settings.brain_dialogue_backend}, voice={settings.brain_voice_backend}.",
        )

    if resolved_model.name == "cloud_demo":
        missing: list[str] = []
        if not settings.grsai_api_key:
            missing.append("dialogue")
        if settings.brain_voice_backend.lower() == "openai" and not settings.openai_api_key:
            missing.append("voice")
        if resolved_model.perception_provider == PerceptionProviderMode.MULTIMODAL_LLM and not settings.perception_multimodal_api_key:
            missing.append("perception")
        if missing:
            return ProviderStatusSummary(
                status="fallback_ready",
                detail="Missing provider credentials for "
                + ", ".join(missing)
                + ". Blink-AI remains usable through typed/local fallback paths.",
            )
        return ProviderStatusSummary(
            status="provider_backed",
            detail="Provider-backed cloud demo profile is configured for dialogue, voice, and multimodal perception.",
        )

    if resolved_model.name == "companion_live":
        if settings.grsai_api_key and settings.grsai_base_url and settings.grsai_model:
            return ProviderStatusSummary(
                status="hybrid_companion_live",
                detail="Hybrid companion-live profile keeps memory, orchestration, and local media on-device while preferring provider dialogue for faster day-to-day conversation.",
            )
        if settings.ollama_base_url:
            return ProviderStatusSummary(
                status="hybrid_local_fallback",
                detail="Companion-live is missing provider dialogue credentials, so it will fall back to local Ollama or deterministic local replies while keeping local memory and media active.",
            )
        return ProviderStatusSummary(
            status="typed_local_fallback",
            detail="Companion-live is running without provider dialogue or Ollama, so the terminal loop stays usable through deterministic local fallback and typed-safe media paths.",
        )

    if resolved_model.name == "local_dev":
        return ProviderStatusSummary(
            status="local_optional",
            detail="Local development prefers Ollama and browser/fixture perception, with deterministic fallback still available.",
        )

    if resolved_model.name == "m4_pro_companion":
        if settings.perception_multimodal_api_key:
            return ProviderStatusSummary(
                status="native_camera_grounded",
                detail="Native local companion profile will use webcam snapshots with multimodal grounding when available.",
            )
        if settings.ollama_base_url:
            return ProviderStatusSummary(
                status="local_ollama_companion",
                detail="Local companion mode prefers Ollama text and vision on the Mac, with Apple Speech, macOS say, and honest limited-awareness fallback when semantic vision is unavailable.",
            )
        return ProviderStatusSummary(
            status="native_camera_limited",
            detail="Native local companion profile uses the Mac mic, speaker, and webcam. Scene understanding stays honest and limited until a semantic local or cloud perception provider is configured.",
        )

    return ProviderStatusSummary(
        status="offline_only",
        detail="Offline stub profile is fully local and does not require cloud credentials.",
    )


def summarize_desktop_profile(
    settings: Settings,
    *,
    say_available: bool | None = None,
) -> DesktopProfileSummary:
    model_profile = resolve_model_profile(settings)
    voice_profile = resolve_voice_profile(settings, say_available=say_available)
    embodiment_profile = resolve_embodiment_profile(settings)
    provider_status = summarize_provider_status(settings, model_profile=model_profile)
    model_name = model_profile.name if model_profile is not None else settings.blink_model_profile
    return DesktopProfileSummary(
        profile_label=f"{model_name} + {embodiment_profile.name}",
        model_profile=model_name,
        backend_profile=resolve_backend_profile_name(settings),
        voice_profile=voice_profile.name,
        embodiment_profile=embodiment_profile.name,
        provider_status=provider_status.status,
        provider_detail=provider_status.detail,
    )


def apply_desktop_profile(settings: Settings) -> Settings:
    resolved = apply_appliance_profile(settings)
    if resolve_backend_profile_name(resolved) == "m4_pro_companion":
        resolved.ollama_model = "qwen3.5:9b"
        resolved.ollama_text_model = resolved.ollama_text_model or "qwen3.5:9b"
        resolved.ollama_vision_model = resolved.ollama_vision_model or "qwen3.5:9b"
        resolved.ollama_embedding_model = resolved.ollama_embedding_model or "embeddinggemma:300m"
    model_profile = resolve_model_profile(resolved)
    if model_profile is not None:
        resolved.brain_dialogue_backend = model_profile.dialogue_backend
        resolved.brain_voice_backend = model_profile.voice_backend
        resolved.perception_default_provider = _profile_perception_provider(
            resolved,
            model_profile=model_profile,
        ).value

    backend_router = BackendRouter(settings=resolved)
    resolved.brain_dialogue_backend = backend_router.legacy_dialogue_backend()
    resolved.perception_default_provider = backend_router.selected_perception_mode().value
    voice_profile = resolve_voice_profile(resolved)
    resolved.live_voice_default_mode = voice_profile.live_voice_mode.value
    return resolved


def _profile_perception_provider(
    settings: Settings,
    *,
    model_profile: ModelProfileSpec,
) -> PerceptionProviderMode:
    if (
        model_profile.perception_provider == PerceptionProviderMode.MULTIMODAL_LLM
        and not settings.perception_multimodal_api_key
        and model_profile.fallback_perception_provider is not None
    ):
        return model_profile.fallback_perception_provider
    return model_profile.perception_provider


def model_profile_names() -> tuple[str, ...]:
    return tuple(MODEL_PROFILES)


def voice_profile_names() -> tuple[str, ...]:
    return ("desktop_local", "browser_live", "offline_stub")


def embodiment_profile_names() -> tuple[str, ...]:
    return tuple(EMBODIMENT_PROFILES)


__all__ = [
    "DesktopProfileSummary",
    "EMBODIMENT_PROFILES",
    "MODEL_PROFILES",
    "ProviderStatusSummary",
    "RUNTIME_TO_BODY_DRIVER",
    "VOICE_PROFILE_ALIASES",
    "EmbodimentProfileSpec",
    "ModelProfileSpec",
    "VoiceProfileSpec",
    "apply_desktop_profile",
    "body_driver_mode_for_runtime",
    "embodiment_profile_names",
    "model_profile_names",
    "resolve_embodiment_profile",
    "resolve_model_profile",
    "resolve_voice_profile",
    "summarize_desktop_profile",
    "summarize_provider_status",
    "voice_profile_names",
]
