from __future__ import annotations

from embodied_stack.config import Settings
from embodied_stack.shared.models import RuntimeBackendKind

from .types import BackendProfileSpec


BACKEND_PROFILES: dict[str, BackendProfileSpec] = {
    "companion_live": BackendProfileSpec(
        name="companion_live",
        text_candidates=("grsai_chat", "ollama_text", "rule_based"),
        vision_candidates=("native_camera_snapshot", "multimodal_llm", "ollama_vision", "stub_vision"),
        embedding_candidates=("ollama_embed", "hash_embed"),
        stt_candidates=("apple_speech_local", "whisper_cpp_local", "typed_input"),
        tts_candidates=("macos_say", "piper_local", "stub_tts"),
        note="Daily-use hybrid companion profile: provider-backed dialogue for fluid conversation when available, local media and memory, and selective semantic vision escalation.",
        memory_pressure_note="Keep default camera grounding cheap; only escalate to multimodal or Ollama vision on explicit visual questions or supervised refreshes.",
    ),
    "cloud_best": BackendProfileSpec(
        name="cloud_best",
        text_candidates=("grsai_chat", "ollama_text", "rule_based"),
        vision_candidates=("multimodal_llm", "ollama_vision", "native_camera_snapshot", "stub_vision"),
        embedding_candidates=("ollama_embed", "hash_embed"),
        stt_candidates=("apple_speech_local", "whisper_cpp_local", "typed_input"),
        tts_candidates=("macos_say", "piper_local", "stub_tts"),
        note="Best-quality demo profile with cloud-first reasoning and vision, local media, and local retrieval fallback.",
        memory_pressure_note="Keep only one heavy remote or local reasoning path active at a time; embeddings stay small and local.",
    ),
    "m4_pro_companion": BackendProfileSpec(
        name="m4_pro_companion",
        text_candidates=("ollama_text", "rule_based"),
        vision_candidates=("ollama_vision", "native_camera_snapshot", "stub_vision"),
        embedding_candidates=("ollama_embed", "hash_embed"),
        stt_candidates=("apple_speech_local", "whisper_cpp_local", "typed_input"),
        tts_candidates=("macos_say", "piper_local", "stub_tts"),
        note="Canonical M4 Pro local companion profile using Ollama text and vision, local embeddings, Apple Speech STT, and macOS say TTS.",
        memory_pressure_note="Warm one medium local Ollama model path at a time; prefer on-demand semantic refresh instead of keeping multiple heavy models resident.",
    ),
    "local_balanced": BackendProfileSpec(
        name="local_balanced",
        text_candidates=("ollama_text", "rule_based"),
        vision_candidates=("ollama_vision", "native_camera_snapshot", "stub_vision"),
        embedding_candidates=("ollama_embed", "hash_embed"),
        stt_candidates=("apple_speech_local", "whisper_cpp_local", "typed_input"),
        tts_candidates=("macos_say", "piper_local", "stub_tts"),
        note="Primary M4 Pro local profile with local text, local embeddings, local STT/TTS, and local-first vision fallback.",
        memory_pressure_note="Prefer one Ollama reasoning or vision model warm at a time; embeddings should stay small enough to remain resident.",
    ),
    "local_fast": BackendProfileSpec(
        name="local_fast",
        text_candidates=("ollama_text", "rule_based"),
        vision_candidates=("native_camera_snapshot", "stub_vision"),
        embedding_candidates=("hash_embed",),
        stt_candidates=("apple_speech_local", "whisper_cpp_local", "typed_input"),
        tts_candidates=("macos_say", "piper_local", "stub_tts"),
        note="Latency-sensitive local profile that avoids a resident local vision model and uses cheap retrieval defaults.",
        memory_pressure_note="Avoid loading multiple medium models together; prefer one small text model plus native media services.",
    ),
    "offline_safe": BackendProfileSpec(
        name="offline_safe",
        text_candidates=("rule_based",),
        vision_candidates=("stub_vision", "native_camera_snapshot"),
        embedding_candidates=("hash_embed",),
        stt_candidates=("typed_input", "apple_speech_local", "whisper_cpp_local"),
        tts_candidates=("stub_tts", "macos_say", "piper_local"),
        note="Deterministic no-provider fallback profile for robustness testing and honest degraded operation.",
        memory_pressure_note="Do not assume any model server is available; keep the system usable with deterministic local fallbacks only.",
    ),
}

BACKEND_PROFILE_ALIASES: dict[str, str] = {
    "companion_live": "companion_live",
    "cloud_demo": "cloud_best",
    "desktop_local": "companion_live",
    "local_companion": "m4_pro_companion",
    "m4_pro_companion": "m4_pro_companion",
    "local_dev": "local_fast",
    "offline_stub": "offline_safe",
}

_OVERRIDE_FIELDS: dict[RuntimeBackendKind, str] = {
    RuntimeBackendKind.TEXT_REASONING: "blink_text_backend",
    RuntimeBackendKind.VISION_ANALYSIS: "blink_vision_backend",
    RuntimeBackendKind.EMBEDDINGS: "blink_embedding_backend",
    RuntimeBackendKind.SPEECH_TO_TEXT: "blink_stt_backend",
    RuntimeBackendKind.TEXT_TO_SPEECH: "blink_tts_backend",
}

_LEGACY_BACKEND_MAP: dict[RuntimeBackendKind, dict[str, str]] = {
    RuntimeBackendKind.TEXT_REASONING: {
        "rule_based": "rule_based",
        "grsai": "grsai_chat",
        "provider": "grsai_chat",
        "openai_compatible": "grsai_chat",
        "ollama": "ollama_text",
        "auto": "ollama_text",
    },
    RuntimeBackendKind.VISION_ANALYSIS: {
        "stub": "stub_vision",
        "browser_snapshot": "browser_snapshot",
        "native_camera_snapshot": "native_camera_snapshot",
        "multimodal_llm": "multimodal_llm",
        "ollama_vision": "ollama_vision",
    },
}


def backend_profile_names() -> tuple[str, ...]:
    return tuple(BACKEND_PROFILES)


def resolve_backend_profile_name(settings: Settings) -> str:
    configured = (settings.blink_backend_profile or "").strip().lower()
    if configured:
        return BACKEND_PROFILE_ALIASES.get(configured, configured)

    model_profile = settings.blink_model_profile.strip().lower()
    return BACKEND_PROFILE_ALIASES.get(model_profile, "local_balanced")


def resolve_backend_profile(settings: Settings) -> BackendProfileSpec:
    return BACKEND_PROFILES.get(resolve_backend_profile_name(settings), BACKEND_PROFILES["local_balanced"])


def backend_candidates_for(
    settings: Settings,
    kind: RuntimeBackendKind,
    *,
    include_legacy_overrides: bool = True,
) -> tuple[str, ...]:
    profile = resolve_backend_profile(settings)
    base_candidates = {
        RuntimeBackendKind.TEXT_REASONING: profile.text_candidates,
        RuntimeBackendKind.VISION_ANALYSIS: profile.vision_candidates,
        RuntimeBackendKind.EMBEDDINGS: profile.embedding_candidates,
        RuntimeBackendKind.SPEECH_TO_TEXT: profile.stt_candidates,
        RuntimeBackendKind.TEXT_TO_SPEECH: profile.tts_candidates,
    }[kind]
    override = (getattr(settings, _OVERRIDE_FIELDS[kind]) or "").strip().lower()
    if include_legacy_overrides and not override and not settings.blink_backend_profile:
        override = _legacy_override(settings, kind)
    if not override:
        resolved = base_candidates
    else:
        resolved = (override, *tuple(candidate for candidate in base_candidates if candidate != override))
    resolved = _cloud_demo_fallback_candidates(settings, kind, resolved)
    if kind == RuntimeBackendKind.SPEECH_TO_TEXT:
        return _reorder_stt_candidates(settings, resolved)
    return resolved


def _legacy_override(settings: Settings, kind: RuntimeBackendKind) -> str | None:
    if kind == RuntimeBackendKind.TEXT_REASONING:
        legacy = settings.brain_dialogue_backend.strip().lower()
        return _LEGACY_BACKEND_MAP[kind].get(legacy)
    if kind == RuntimeBackendKind.VISION_ANALYSIS:
        legacy = settings.perception_default_provider.strip().lower()
        return _LEGACY_BACKEND_MAP[kind].get(legacy)
    if kind in {RuntimeBackendKind.SPEECH_TO_TEXT, RuntimeBackendKind.TEXT_TO_SPEECH}:
        mode = settings.live_voice_default_mode.strip().lower()
        if kind == RuntimeBackendKind.SPEECH_TO_TEXT:
            return {
                "desktop_native": "apple_speech_local",
                "open_mic_local": "whisper_cpp_local",
                "browser_live": "typed_input",
                "browser_live_macos_say": "typed_input",
                "macos_say": "typed_input",
                "stub_demo": "typed_input",
            }.get(mode)
        return {
            "desktop_native": "macos_say",
            "open_mic_local": "macos_say",
            "browser_live_macos_say": "macos_say",
            "macos_say": "macos_say",
            "browser_live": "stub_tts",
            "stub_demo": "stub_tts",
        }.get(mode)
    return None


def _reorder_stt_candidates(settings: Settings, candidates: tuple[str, ...]) -> tuple[str, ...]:
    if settings.blink_audio_mode.strip().lower() != "open_mic":
        return candidates
    ordered = []
    for preferred in ("whisper_cpp_local", "apple_speech_local", "typed_input"):
        if preferred in candidates and preferred not in ordered:
            ordered.append(preferred)
    ordered.extend(candidate for candidate in candidates if candidate not in ordered)
    return tuple(ordered)


def _cloud_demo_fallback_candidates(
    settings: Settings,
    kind: RuntimeBackendKind,
    candidates: tuple[str, ...],
) -> tuple[str, ...]:
    if settings.blink_backend_profile:
        return candidates
    if settings.blink_model_profile.strip().lower() != "cloud_demo":
        return candidates

    if kind == RuntimeBackendKind.TEXT_REASONING and not settings.grsai_api_key:
        return ("rule_based", *tuple(candidate for candidate in candidates if candidate != "rule_based"))
    if kind == RuntimeBackendKind.VISION_ANALYSIS and not settings.perception_multimodal_api_key:
        preferred = ("native_camera_snapshot", "stub_vision")
        ordered = [candidate for candidate in preferred if candidate in candidates]
        ordered.extend(candidate for candidate in candidates if candidate not in ordered)
        return tuple(ordered)
    if kind == RuntimeBackendKind.TEXT_TO_SPEECH and settings.brain_voice_backend.strip().lower() == "openai" and not settings.openai_api_key:
        return ("stub_tts", *tuple(candidate for candidate in candidates if candidate != "stub_tts"))
    return candidates
