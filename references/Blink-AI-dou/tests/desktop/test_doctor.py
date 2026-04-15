from __future__ import annotations

from types import SimpleNamespace

from embodied_stack.desktop.doctor import _runtime_text_turn_probe, render_local_companion_doctor_report


def test_render_local_companion_doctor_report_includes_issue_sections():
    markdown = render_local_companion_doctor_report(
        {
            "generated_at": "2026-04-06T12:00:00Z",
            "hardware": {"machine": "arm64", "macos_version": "26.2", "cpu": "Apple M4 Pro", "memory_gb": 24},
            "binaries": {"ollama": "/opt/homebrew/bin/ollama", "whisper_cli": "/opt/homebrew/bin/whisper-cli", "ffmpeg": "/opt/homebrew/bin/ffmpeg", "say": "/usr/bin/say"},
            "ollama": {"reachable": True, "base_url": "http://127.0.0.1:11434", "installed_models": ["qwen3.5:9b"], "running_models": [], "probe_error": None, "probe_latency_ms": 21.0},
            "whisper": {"binary": "/opt/homebrew/bin/whisper-cli", "model_path": "/tmp/ggml-tiny.en.bin", "smoke": {"label": "raw_whisper_smoke", "ok": True, "detail": "Local whisper smoke test.", "latency_ms": 842.0}},
            "auth": {
                "enabled": True,
                "auth_mode": "configured_static_token",
                "token_source": "persisted_runtime",
                "runtime_file": "runtime/operator_auth.json",
            },
            "devices": {
                "device_preset": "external_monitor",
                "available_audio_devices": ["LG UltraFine Display Audio"],
                "available_video_devices": ["LG UltraFine Display Camera"],
                "selected_microphone_label": "LG UltraFine Display Audio",
                "selected_camera_label": "LG UltraFine Display Camera",
                "selected_speaker_label": "system_default",
                "speaker_selection_supported": False,
                "microphone_detail": "device=LG UltraFine Display Audio",
                "camera_detail": "Camera permission was denied.",
                "speaker_detail": "voice=Samantha; output=system_default; requested_output=system_default; selection_supported=false",
                "speaker_note": "macos_say follows the current macOS default output device.",
            },
            "runtime": {
                "context_mode": "personal_local",
                "profile_summary": "companion_live + virtual_body",
                "resolved_backend_profile": "companion_live",
                "text_backend": "ollama_text",
                "stt_backend": "whisper_cpp_local",
                "tts_backend": "macos_say",
                "auth_mode": "configured_static_token",
                "setup_complete": False,
                "config_source": "repo_defaults",
                "device_preset": "internal_macbook",
                "operator_auth_token_source": "persisted_runtime",
                "operator_auth_runtime_file": "runtime/operator_auth.json",
                "selected_microphone_label": "LG UltraFine Display Audio",
                "selected_camera_label": "LG UltraFine Display Camera",
                "selected_speaker_label": "system_default",
                "fallback_active": False,
                "missing_models": ["qwen3.5:9b"],
                "status_probe": {"label": "status_probe", "ok": True, "detail": "ok"},
                "first_text_turn": {"label": "first_text_turn", "ok": False, "detail": "fallback"},
                "warm_text_turn": {"label": "warm_text_turn", "ok": True, "detail": "ok"},
                "embedding_probe": {"label": "embedding_probe", "ok": True, "detail": "vector_dim=384"},
                "visual_question": {"label": "visual_question", "ok": True, "detail": "capture=ok"},
                "memory_follow_up": {"label": "memory_follow_up", "ok": True, "detail": "open_reminders=1"},
                "proactive_policy": {"label": "proactive_policy", "ok": True, "detail": "decision=speak_now"},
            },
            "issues": [
                {
                    "bucket": "machine_blocker",
                    "category": "machine_install",
                    "message": "whisper-cli missing",
                },
                {
                    "bucket": "repo_or_runtime_bug",
                    "category": "repo_configuration",
                    "message": "typed_input selected unexpectedly",
                },
                {
                    "bucket": "degraded_but_acceptable",
                    "category": "model_latency",
                    "message": "first local text turn fell back",
                },
            ],
            "doctor_status": "repo_or_runtime_bug",
            "next_actions": [
                "Fix the repo/runtime issue.",
                "Rerun local-companion-certify.",
            ],
        }
    )

    assert "# Local MBP Config Report" in markdown
    assert "## Certification Verdict" in markdown
    assert "- doctor_status: repo_or_runtime_bug" in markdown
    assert "Fix the repo/runtime issue." in markdown
    assert "## Auth" in markdown
    assert "## Devices" in markdown
    assert "- auth_mode: configured_static_token" in markdown
    assert "- device_preset: external_monitor" in markdown
    assert "- setup_complete: False" in markdown
    assert "- config_source: repo_defaults" in markdown
    assert "product_behavior_probe" in markdown
    assert "## Issue Buckets" in markdown
    assert "Machine blockers" in markdown
    assert "Repo or runtime bugs" in markdown
    assert "Degraded but acceptable" in markdown


def test_runtime_text_turn_probe_retries_transient_fallback():
    class FakeRuntime:
        def __init__(self) -> None:
            self._submit_calls = 0
            self._snapshot_calls = 0
            self.orchestrator = SimpleNamespace(get_trace=self.get_trace)

        def submit_text(self, *_args, **_kwargs):
            self._submit_calls += 1
            if self._submit_calls == 1:
                return SimpleNamespace(
                    outcome="fallback_reply",
                    response=SimpleNamespace(trace_id="trace-1", reply_text="fallback"),
                )
            return SimpleNamespace(
                outcome="ok",
                response=SimpleNamespace(trace_id="trace-2", reply_text="warm local text turn works."),
            )

        def get_trace(self, trace_id: str):
            if trace_id == "trace-1":
                return SimpleNamespace(reasoning=SimpleNamespace(engine="rule_based", fallback_used=True))
            return SimpleNamespace(reasoning=SimpleNamespace(engine="ollama:qwen3.5:9b", fallback_used=False))

        def snapshot(self, *_args, **_kwargs):
            self._snapshot_calls += 1
            if self._snapshot_calls == 1:
                status = SimpleNamespace(
                    kind=SimpleNamespace(value="text_reasoning"),
                    backend_id="ollama_text",
                    status=SimpleNamespace(value="fallback_active"),
                    last_failure_reason="ollama_timeout",
                    last_timeout_seconds=12.0,
                    cold_start_retry_used=False,
                    last_success_latency_ms=None,
                )
            else:
                status = SimpleNamespace(
                    kind=SimpleNamespace(value="text_reasoning"),
                    backend_id="ollama_text",
                    status=SimpleNamespace(value="warm"),
                    last_failure_reason=None,
                    last_timeout_seconds=None,
                    cold_start_retry_used=False,
                    last_success_latency_ms=842.0,
                )
            return SimpleNamespace(runtime=SimpleNamespace(backend_status=[status]))

    result = _runtime_text_turn_probe(
        runtime=FakeRuntime(),
        session_id="doctor-test",
        prompt="Reply with exactly: warm local text turn works.",
        label="warm_text_turn",
        retry_on_transient_fallback=True,
    )

    assert result["ok"] is True
    assert result["attempt_count"] == 2
    assert result["recovered_after_retry"] is True
    assert result["engine"] == "ollama:qwen3.5:9b"
    assert "attempt=2/2" in result["detail"]
