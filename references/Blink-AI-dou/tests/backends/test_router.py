from __future__ import annotations

from datetime import timedelta
from pathlib import Path

from embodied_stack.backends.embeddings import FallbackEmbeddingBackend, HashEmbeddingBackend, OllamaEmbeddingBackend, SemanticRetriever, RetrievalDocument
from embodied_stack.backends.local_paths import resolve_whisper_cpp_model_path
from embodied_stack.backends.profiles import backend_candidates_for, resolve_backend_profile_name
from embodied_stack.backends.router import BackendRouter, OllamaProbeSnapshot
from embodied_stack.config import Settings
from embodied_stack.shared.models import RuntimeBackendKind, utc_now


class StaticOllamaProbe:
    def __init__(self, snapshot: OllamaProbeSnapshot) -> None:
        self._snapshot = snapshot

    def snapshot(self) -> OllamaProbeSnapshot:
        return self._snapshot


def test_backend_profile_alias_maps_desktop_local_to_companion_live():
    settings = Settings(_env_file=None, blink_model_profile="desktop_local")

    assert resolve_backend_profile_name(settings) == "companion_live"
    assert backend_candidates_for(settings, RuntimeBackendKind.TEXT_REASONING) == ("rule_based", "grsai_chat", "ollama_text")


def test_backend_router_marks_fallback_when_requested_backend_is_unavailable():
    settings = Settings(
        _env_file=None,
        blink_backend_profile="local_balanced",
        brain_dialogue_backend="ollama",
        perception_default_provider="ollama_vision",
        ollama_text_model="qwen2.5:3b",
        ollama_vision_model="llava:7b",
        ollama_embedding_model="all-minilm",
    )
    router = BackendRouter(
        settings=settings,
        ollama_probe=StaticOllamaProbe(
            OllamaProbeSnapshot(
                reachable=False,
                installed_models=set(),
                running_models=set(),
                error="ollama_probe_timeout",
            )
        ),
    )

    decisions = {item.kind.value: item for item in router.route_decisions()}

    assert decisions["text_reasoning"].backend_id == "rule_based"
    assert decisions["text_reasoning"].status.value == "fallback_active"
    assert decisions["text_reasoning"].fallback_from == "ollama_text"
    assert decisions["vision_analysis"].backend_id == "native_camera_snapshot"
    assert decisions["vision_analysis"].status.value == "fallback_active"
    assert decisions["embeddings"].backend_id == "hash_embed"
    assert decisions["embeddings"].status.value == "fallback_active"


def test_backend_router_respects_explicit_backend_overrides():
    settings = Settings(
        _env_file=None,
        blink_backend_profile="cloud_best",
        blink_text_backend="rule_based",
        blink_vision_backend="stub_vision",
        blink_embedding_backend="hash_embed",
        blink_stt_backend="typed_input",
        blink_tts_backend="stub_tts",
    )
    router = BackendRouter(settings=settings)

    assert router.selected_backend_id(RuntimeBackendKind.TEXT_REASONING) == "rule_based"
    assert router.selected_backend_id(RuntimeBackendKind.VISION_ANALYSIS) == "stub_vision"
    assert router.selected_backend_id(RuntimeBackendKind.EMBEDDINGS) == "hash_embed"
    assert router.selected_backend_id(RuntimeBackendKind.SPEECH_TO_TEXT) == "typed_input"
    assert router.selected_backend_id(RuntimeBackendKind.TEXT_TO_SPEECH) == "stub_tts"


def test_explicit_backend_profile_beats_legacy_backend_settings():
    settings = Settings(
        _env_file=None,
        blink_backend_profile="offline_safe",
        brain_dialogue_backend="grsai",
        perception_default_provider="multimodal_llm",
        live_voice_default_mode="desktop_native",
    )
    router = BackendRouter(settings=settings)

    assert router.selected_backend_id(RuntimeBackendKind.TEXT_REASONING) == "rule_based"
    assert router.selected_backend_id(RuntimeBackendKind.VISION_ANALYSIS) == "stub_vision"
    assert router.selected_backend_id(RuntimeBackendKind.EMBEDDINGS) == "hash_embed"
    assert router.selected_backend_id(RuntimeBackendKind.SPEECH_TO_TEXT) == "typed_input"
    assert router.selected_backend_id(RuntimeBackendKind.TEXT_TO_SPEECH) == "stub_tts"


def test_embedding_fallback_reports_actual_backend_used():
    class FailingOllamaEmbed(OllamaEmbeddingBackend):
        def embed(self, inputs: list[str]) -> list[list[float]]:
            raise self._error()

        def _error(self):
            from embodied_stack.backends.types import EmbeddingBackendError

            return EmbeddingBackendError("ollama_embedding_timeout")

    backend = FallbackEmbeddingBackend(
        primary=FailingOllamaEmbed(
            base_url="http://127.0.0.1:11434",
            model="all-minilm",
            timeout_seconds=0.1,
        ),
        fallback=HashEmbeddingBackend(),
    )
    retriever = SemanticRetriever(
        embedding_backend=backend,
        static_documents=[
            RetrievalDocument(
                document_id="operator-note:1",
                tool_name="faq_lookup",
                text="Offer the April volunteer packet if asked.",
                answer_text="Offer the April volunteer packet if asked.",
            )
        ],
    )

    hit = retriever.search("Do you have the volunteer packet?", minimum_score=0.1)

    assert hit is not None
    assert hit.backend_id == "hash_embed"


def test_open_mic_audio_mode_prefers_whisper_cpp_candidate():
    settings = Settings(_env_file=None, blink_backend_profile="m4_pro_companion", blink_audio_mode="open_mic")

    assert backend_candidates_for(settings, RuntimeBackendKind.SPEECH_TO_TEXT, include_legacy_overrides=False)[0] == "whisper_cpp_local"


def test_whisper_model_discovery_prefers_explicit_override(tmp_path):
    explicit = tmp_path / "explicit.bin"
    cached_home = tmp_path / "home"
    cached_model = cached_home / ".cache" / "berserker" / "whisper-cpp" / "ggml-tiny.en.bin"
    cached_model.parent.mkdir(parents=True, exist_ok=True)
    cached_model.write_bytes(b"cached")
    settings = Settings(_env_file=None, whisper_cpp_model_path=str(explicit))

    discovered = resolve_whisper_cpp_model_path(settings, home_dir=cached_home, brew_prefix=tmp_path / "brew")

    assert discovered == explicit


def test_whisper_model_discovery_uses_berserker_cache_before_other_locations(tmp_path):
    home_dir = tmp_path / "home"
    berserker_dir = home_dir / ".cache" / "berserker" / "whisper-cpp"
    fallback_dir = home_dir / ".cache" / "whisper.cpp"
    berserker_dir.mkdir(parents=True, exist_ok=True)
    fallback_dir.mkdir(parents=True, exist_ok=True)
    preferred = berserker_dir / "ggml-tiny.en.bin"
    preferred.write_bytes(b"tiny")
    later_candidate = fallback_dir / "ggml-base.en.bin"
    later_candidate.write_bytes(b"base")
    settings = Settings(_env_file=None)

    discovered = resolve_whisper_cpp_model_path(settings, home_dir=home_dir, brew_prefix=tmp_path / "brew")

    assert discovered == preferred


def test_backend_router_marks_whisper_available_when_model_is_auto_discovered(monkeypatch, tmp_path):
    import embodied_stack.backends.router as router_module

    discovered_model = tmp_path / "ggml-tiny.en.bin"
    discovered_model.write_bytes(b"model")
    settings = Settings(_env_file=None, blink_backend_profile="m4_pro_companion", blink_audio_mode="open_mic")
    monkeypatch.setattr(router_module, "resolve_whisper_cpp_binary_path", lambda settings: "/opt/homebrew/bin/whisper-cli")
    monkeypatch.setattr(router_module, "resolve_whisper_cpp_model_path", lambda settings: discovered_model)
    monkeypatch.setattr(router_module.shutil, "which", lambda name: "/usr/bin/true")

    router = BackendRouter(settings=settings)
    decision = next(item for item in router.route_decisions() if item.kind == RuntimeBackendKind.SPEECH_TO_TEXT)

    assert decision.backend_id == "whisper_cpp_local"
    assert decision.status.value == "configured"
    assert decision.model == str(discovered_model)


def test_model_residency_unloads_idle_vision_model(monkeypatch):
    settings = Settings(
        _env_file=None,
        blink_backend_profile="m4_pro_companion",
        ollama_text_model="qwen3.5:9b",
        ollama_vision_model="qwen3.5:9b",
        ollama_embedding_model="embeddinggemma:300m",
        blink_model_idle_unload_seconds=1.0,
    )
    router = BackendRouter(
        settings=settings,
        ollama_probe=StaticOllamaProbe(
            OllamaProbeSnapshot(
                reachable=True,
                installed_models={"qwen3.5:9b", "embeddinggemma:300m"},
                running_models={"qwen3.5:9b"},
                latency_ms=24.0,
            )
        ),
    )
    router.report_ollama_success(kind=RuntimeBackendKind.VISION_ANALYSIS, model="qwen3.5:9b", latency_ms=18.0)
    router._model_residency[RuntimeBackendKind.VISION_ANALYSIS] = router._model_residency[RuntimeBackendKind.VISION_ANALYSIS].model_copy(
        update={"last_used_at": utc_now() - timedelta(seconds=5.0)}
    )
    monkeypatch.setattr(router, "_request_ollama_unload", lambda model: True)

    records = router.apply_model_residency_policy()
    vision = next(item for item in records if item.kind == RuntimeBackendKind.VISION_ANALYSIS)

    assert vision.resident is False
    assert vision.status == "unloaded"


def test_model_residency_keeps_shared_text_and_vision_model_resident(monkeypatch):
    settings = Settings(
        _env_file=None,
        blink_backend_profile="m4_pro_companion",
        ollama_text_model="qwen3.5:9b",
        ollama_vision_model="qwen3.5:9b",
        ollama_embedding_model="embeddinggemma:300m",
        blink_model_idle_unload_seconds=1.0,
    )
    router = BackendRouter(
        settings=settings,
        ollama_probe=StaticOllamaProbe(
            OllamaProbeSnapshot(
                reachable=True,
                installed_models={"qwen3.5:9b", "embeddinggemma:300m"},
                running_models={"qwen3.5:9b"},
                latency_ms=24.0,
            )
        ),
    )
    router.report_ollama_success(kind=RuntimeBackendKind.TEXT_REASONING, model="qwen3.5:9b", latency_ms=12.0)
    router.report_ollama_success(kind=RuntimeBackendKind.VISION_ANALYSIS, model="qwen3.5:9b", latency_ms=18.0)
    router._model_residency[RuntimeBackendKind.VISION_ANALYSIS] = router._model_residency[RuntimeBackendKind.VISION_ANALYSIS].model_copy(
        update={"last_used_at": utc_now() - timedelta(seconds=5.0)}
    )
    unload_calls: list[str | None] = []
    monkeypatch.setattr(router, "_request_ollama_unload", lambda model: unload_calls.append(model) or True)

    records = router.apply_model_residency_policy()
    vision = next(item for item in records if item.kind == RuntimeBackendKind.VISION_ANALYSIS)

    assert vision.resident is True
    assert vision.status == "shared_resident"
    assert unload_calls == []


def test_companion_live_keeps_default_perception_native_but_exposes_semantic_escalation():
    settings = Settings(
        _env_file=None,
        blink_backend_profile="companion_live",
        perception_multimodal_api_key="demo-key",
        perception_multimodal_base_url="https://example.invalid/v1",
        perception_multimodal_model="gpt-4.1-mini",
    )
    router = BackendRouter(settings=settings)

    assert router.selected_backend_id(RuntimeBackendKind.VISION_ANALYSIS) == "native_camera_snapshot"
    assert router.selected_perception_mode().value == "native_camera_snapshot"
    assert router.selected_semantic_vision_backend_id() == "multimodal_llm"
    assert router.selected_semantic_perception_mode().value == "multimodal_llm"


def test_backend_router_uses_per_kind_ollama_timeouts():
    settings = Settings(
        _env_file=None,
        blink_backend_profile="m4_pro_companion",
        ollama_text_timeout_seconds=12.0,
        ollama_text_cold_start_timeout_seconds=30.0,
        ollama_vision_timeout_seconds=30.0,
        ollama_embed_timeout_seconds=5.0,
    )
    router = BackendRouter(settings=settings)

    assert router._ollama_timeout_seconds_for(RuntimeBackendKind.TEXT_REASONING) == 12.0
    assert router._ollama_timeout_seconds_for(RuntimeBackendKind.TEXT_REASONING, cold_start=True) == 30.0
    assert router._ollama_timeout_seconds_for(RuntimeBackendKind.VISION_ANALYSIS) == 30.0
    assert router._ollama_timeout_seconds_for(RuntimeBackendKind.EMBEDDINGS) == 5.0


def test_backend_router_surfaces_last_failure_metadata_for_ollama_text():
    settings = Settings(
        _env_file=None,
        blink_backend_profile="m4_pro_companion",
        ollama_text_model="qwen3.5:9b",
    )
    router = BackendRouter(
        settings=settings,
        ollama_probe=StaticOllamaProbe(
            OllamaProbeSnapshot(
                reachable=True,
                installed_models={"qwen3.5:9b"},
                running_models=set(),
            )
        ),
    )
    router.report_ollama_failure(
        kind=RuntimeBackendKind.TEXT_REASONING,
        reason="ollama_timeout",
        timeout_seconds=12.0,
        retry_used=True,
    )

    decision = next(item for item in router.route_decisions() if item.kind == RuntimeBackendKind.TEXT_REASONING)

    assert decision.backend_id == "ollama_text"
    assert decision.last_failure_reason == "ollama_timeout"
    assert decision.last_timeout_seconds == 12.0
    assert decision.cold_start_retry_used is True
