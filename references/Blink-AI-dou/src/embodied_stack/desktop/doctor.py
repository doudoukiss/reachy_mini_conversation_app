from __future__ import annotations

import platform
import shutil
import subprocess
import tempfile
from pathlib import Path
from time import perf_counter, sleep
from typing import Any

from embodied_stack.backends.local_paths import resolve_whisper_cpp_binary_path, resolve_whisper_cpp_model_path
from embodied_stack.brain.auth import OperatorAuthManager
from embodied_stack.config import Settings, get_settings
from embodied_stack.desktop.app import build_desktop_runtime
from embodied_stack.desktop.devices import list_avfoundation_devices
from embodied_stack.shared.models import (
    CompanionContextMode,
    LocalCompanionCertificationVerdict,
    ResponseMode,
    VoiceRuntimeMode,
    utc_now,
)


def run_local_companion_doctor(
    *,
    settings: Settings | None = None,
    write_path: str | Path | None = None,
) -> dict[str, Any]:
    runtime_settings = (settings or get_settings()).model_copy(deep=True)
    runtime_settings.blink_always_on_enabled = True
    runtime_settings.blink_context_mode = CompanionContextMode.PERSONAL_LOCAL
    report_path = Path(write_path or "runtime/diagnostics/local_mbp_config_report.md")
    report_path.parent.mkdir(parents=True, exist_ok=True)

    report: dict[str, Any] = {
        "generated_at": utc_now().isoformat(),
        "report_path": str(report_path),
        "issues": [],
        "doctor_status": LocalCompanionCertificationVerdict.DEGRADED_BUT_ACCEPTABLE.value,
        "next_actions": [],
    }
    report["hardware"] = _collect_hardware_summary()
    report["binaries"] = _collect_binary_summary(runtime_settings)
    report["ollama"] = _collect_ollama_summary(runtime_settings)
    report["whisper"] = _collect_whisper_summary(runtime_settings)
    report["auth"] = _collect_auth_summary(runtime_settings)
    report["devices"] = _collect_device_summary(runtime_settings)
    report["runtime"] = _collect_runtime_summary(runtime_settings)
    _classify_issues(report)

    markdown = render_local_companion_doctor_report(report)
    report_path.write_text(markdown, encoding="utf-8")
    report["report_path"] = str(report_path)
    return report


def render_local_companion_doctor_report(report: dict[str, Any]) -> str:
    hardware = report.get("hardware", {})
    binaries = report.get("binaries", {})
    ollama = report.get("ollama", {})
    whisper = report.get("whisper", {})
    auth = report.get("auth", {})
    devices = report.get("devices", {})
    runtime = report.get("runtime", {})
    issues = report.get("issues", [])
    doctor_status = report.get("doctor_status") or LocalCompanionCertificationVerdict.DEGRADED_BUT_ACCEPTABLE.value
    next_actions = report.get("next_actions") or []

    def _status_line(item: dict[str, Any]) -> str:
        status = "ok" if item.get("ok") else "issue"
        detail = item.get("detail") or "-"
        latency = item.get("latency_ms")
        latency_text = f" ({latency} ms)" if latency is not None else ""
        return f"- {item.get('label')}: {status}{latency_text} - {detail}"

    issue_groups = {
        LocalCompanionCertificationVerdict.MACHINE_BLOCKER.value: [],
        LocalCompanionCertificationVerdict.REPO_OR_RUNTIME_BUG.value: [],
        LocalCompanionCertificationVerdict.DEGRADED_BUT_ACCEPTABLE.value: [],
    }
    for issue in issues:
        issue_groups.setdefault(
            issue.get("bucket") or LocalCompanionCertificationVerdict.DEGRADED_BUT_ACCEPTABLE.value,
            [],
        ).append(issue["message"])

    lines = [
        "# Local MBP Config Report",
        "",
        f"Generated: {report.get('generated_at')}",
        "",
        "## Certification Verdict",
        f"- doctor_status: {doctor_status}",
        "- next_actions:" if next_actions else "- next_actions: none",
        *([f"  - {item}" for item in next_actions] if next_actions else []),
        "",
        "## Hardware",
        f"- machine: {hardware.get('machine') or '-'}",
        f"- macos_version: {hardware.get('macos_version') or '-'}",
        f"- cpu: {hardware.get('cpu') or '-'}",
        f"- memory_gb: {hardware.get('memory_gb') or '-'}",
        "",
        "## Local Binaries",
        f"- ollama: {binaries.get('ollama') or '-'}",
        f"- whisper_cli: {binaries.get('whisper_cli') or '-'}",
        f"- ffmpeg: {binaries.get('ffmpeg') or '-'}",
        f"- say: {binaries.get('say') or '-'}",
        "",
        "## Ollama",
        f"- reachable: {ollama.get('reachable')}",
        f"- base_url: {ollama.get('base_url') or '-'}",
        f"- installed_models: {', '.join(ollama.get('installed_models', [])) or '-'}",
        f"- running_models: {', '.join(ollama.get('running_models', [])) or '-'}",
        f"- probe_error: {ollama.get('probe_error') or '-'}",
        f"- probe_latency_ms: {ollama.get('probe_latency_ms') if ollama.get('probe_latency_ms') is not None else '-'}",
        "",
        "## Whisper",
        f"- binary: {whisper.get('binary') or '-'}",
        f"- model_path: {whisper.get('model_path') or '-'}",
        _status_line(whisper.get("smoke", {"label": "raw_whisper_smoke", "ok": False, "detail": "not_run"})),
        "",
        "## Auth",
        f"- enabled: {auth.get('enabled')}",
        f"- auth_mode: {auth.get('auth_mode') or '-'}",
        f"- token_source: {auth.get('token_source') or '-'}",
        f"- runtime_file: {auth.get('runtime_file') or '-'}",
        "",
        "## Devices",
        f"- device_preset: {devices.get('device_preset') or '-'}",
        f"- available_audio_devices: {', '.join(devices.get('available_audio_devices', [])) or '-'}",
        f"- available_video_devices: {', '.join(devices.get('available_video_devices', [])) or '-'}",
        f"- selected_microphone_label: {devices.get('selected_microphone_label') or '-'}",
        f"- selected_camera_label: {devices.get('selected_camera_label') or '-'}",
        f"- selected_speaker_label: {devices.get('selected_speaker_label') or '-'}",
        f"- speaker_selection_supported: {devices.get('speaker_selection_supported')}",
        f"- microphone_detail: {devices.get('microphone_detail') or '-'}",
        f"- camera_detail: {devices.get('camera_detail') or '-'}",
        f"- speaker_detail: {devices.get('speaker_detail') or '-'}",
        f"- speaker_note: {devices.get('speaker_note') or '-'}",
        "",
        "## Runtime",
        f"- context_mode: {runtime.get('context_mode') or '-'}",
        f"- profile_summary: {runtime.get('profile_summary') or '-'}",
        f"- resolved_backend_profile: {runtime.get('resolved_backend_profile') or '-'}",
        f"- text_backend: {runtime.get('text_backend') or '-'}",
        f"- stt_backend: {runtime.get('stt_backend') or '-'}",
        f"- tts_backend: {runtime.get('tts_backend') or '-'}",
        f"- auth_mode: {runtime.get('auth_mode') or '-'}",
        f"- setup_complete: {runtime.get('setup_complete')}",
        f"- config_source: {runtime.get('config_source') or '-'}",
        f"- device_preset: {runtime.get('device_preset') or '-'}",
        f"- auth_token_source: {runtime.get('operator_auth_token_source') or '-'}",
        f"- auth_runtime_file: {runtime.get('operator_auth_runtime_file') or '-'}",
        f"- selected_microphone_label: {runtime.get('selected_microphone_label') or '-'}",
        f"- selected_camera_label: {runtime.get('selected_camera_label') or '-'}",
        f"- selected_speaker_label: {runtime.get('selected_speaker_label') or '-'}",
        f"- terminal_frontend_state: {runtime.get('terminal_frontend_state') or '-'}",
        f"- terminal_frontend_detail: {runtime.get('terminal_frontend_detail') or '-'}",
        f"- console_url: {runtime.get('console_url') or '-'}",
        f"- console_launch_state: {runtime.get('console_launch_state') or '-'}",
        f"- fallback_active: {runtime.get('fallback_active')}",
        f"- missing_models: {', '.join(runtime.get('missing_models', [])) or '-'}",
        "",
        "## Runtime Smokes",
        _status_line(runtime.get("status_probe", {"label": "status_probe", "ok": False, "detail": "not_run"})),
        _status_line(runtime.get("first_text_turn", {"label": "first_text_turn", "ok": False, "detail": "not_run"})),
        _status_line(runtime.get("warm_text_turn", {"label": "warm_text_turn", "ok": False, "detail": "not_run"})),
        _status_line(runtime.get("product_behavior_probe", {"label": "product_behavior_probe", "ok": False, "detail": "not_run"})),
        _status_line(runtime.get("embedding_probe", {"label": "embedding_probe", "ok": False, "detail": "not_run"})),
        _status_line(runtime.get("visual_question", {"label": "visual_question", "ok": False, "detail": "not_run"})),
        _status_line(runtime.get("memory_follow_up", {"label": "memory_follow_up", "ok": False, "detail": "not_run"})),
        _status_line(runtime.get("proactive_policy", {"label": "proactive_policy", "ok": False, "detail": "not_run"})),
        "",
        "## Issue Buckets",
    ]
    for category, title in (
        (LocalCompanionCertificationVerdict.MACHINE_BLOCKER.value, "Machine blockers"),
        (LocalCompanionCertificationVerdict.REPO_OR_RUNTIME_BUG.value, "Repo or runtime bugs"),
        (LocalCompanionCertificationVerdict.DEGRADED_BUT_ACCEPTABLE.value, "Degraded but acceptable"),
    ):
        messages = issue_groups.get(category) or []
        if not messages:
            lines.append(f"- {title}: none")
            continue
        lines.append(f"- {title}:")
        lines.extend([f"  - {message}" for message in messages])
    return "\n".join(lines) + "\n"


def _collect_hardware_summary() -> dict[str, Any]:
    mem_bytes = _run_text_command(["sysctl", "-n", "hw.memsize"])
    cpu = _run_text_command(["sysctl", "-n", "machdep.cpu.brand_string"]) or _run_text_command(["sysctl", "-n", "hw.model"])
    memory_gb = None
    if mem_bytes and mem_bytes.isdigit():
        memory_gb = round(int(mem_bytes) / (1024**3), 2)
    return {
        "machine": platform.machine(),
        "macos_version": _run_text_command(["sw_vers", "-productVersion"]) or platform.mac_ver()[0] or platform.platform(),
        "cpu": cpu or platform.processor() or platform.machine(),
        "memory_gb": memory_gb,
    }


def _collect_binary_summary(settings: Settings) -> dict[str, Any]:
    return {
        "ollama": shutil.which("ollama"),
        "whisper_cli": resolve_whisper_cpp_binary_path(settings),
        "ffmpeg": shutil.which("ffmpeg"),
        "say": shutil.which("say"),
    }


def _collect_ollama_summary(settings: Settings) -> dict[str, Any]:
    from embodied_stack.backends.router import BackendRouter

    router = BackendRouter(settings=settings)
    snapshot = router.ollama_probe.snapshot()
    installed_models = _ollama_model_list()
    return {
        "base_url": settings.ollama_base_url,
        "reachable": snapshot.reachable,
        "probe_error": snapshot.error,
        "probe_latency_ms": snapshot.latency_ms,
        "installed_models": installed_models or sorted(snapshot.installed_models),
        "running_models": sorted(snapshot.running_models),
    }


def _collect_whisper_summary(settings: Settings) -> dict[str, Any]:
    binary = resolve_whisper_cpp_binary_path(settings)
    model_path = resolve_whisper_cpp_model_path(settings)
    smoke = _probe_whisper_smoke(binary=binary, model_path=model_path, timeout_seconds=float(settings.whisper_cpp_timeout_seconds))
    return {
        "binary": binary,
        "model_path": str(model_path) if model_path is not None else None,
        "smoke": smoke,
    }


def _collect_auth_summary(settings: Settings) -> dict[str, Any]:
    manager = OperatorAuthManager(settings)
    return {
        "enabled": manager.enabled,
        "auth_mode": manager.auth_mode,
        "token_source": manager.token_source,
        "runtime_file": str(manager.runtime_file) if manager.runtime_file.exists() else None,
    }


def _collect_device_summary(settings: Settings) -> dict[str, Any]:
    ffmpeg_path = shutil.which("ffmpeg")
    listed = list_avfoundation_devices(ffmpeg_path=ffmpeg_path)
    with build_desktop_runtime(settings=settings) as runtime:
        snapshot = runtime.snapshot()
        camera_detail = None
        camera_capture = runtime.device_registry.camera_capture
        if camera_capture.snapshot_helper and camera_capture.snapshot_helper.available():
            try:
                probe = camera_capture.snapshot_helper.probe(
                    preferred_label=snapshot.runtime.selected_camera_label,
                )
                camera_detail = f"ready:{probe.get('device_label') or snapshot.runtime.selected_camera_label or 'default'}"
            except Exception as exc:  # pragma: no cover - depends on local camera/permissions
                camera_detail = str(exc)
    microphone = next((item for item in snapshot.runtime.device_health if item.kind.value == "microphone"), None)
    camera = next((item for item in snapshot.runtime.device_health if item.kind.value == "camera"), None)
    speaker = next((item for item in snapshot.runtime.device_health if item.kind.value == "speaker"), None)
    return {
        "device_preset": settings.blink_device_preset,
        "available_audio_devices": [item.label for item in listed.get("audio", [])],
        "available_video_devices": [item.label for item in listed.get("video", [])],
        "selected_microphone_label": snapshot.runtime.selected_microphone_label,
        "selected_camera_label": snapshot.runtime.selected_camera_label,
        "selected_speaker_label": snapshot.runtime.selected_speaker_label,
        "speaker_selection_supported": snapshot.runtime.speaker_selection_supported,
        "microphone_detail": microphone.detail if microphone is not None else None,
        "camera_detail": camera_detail or (camera.detail if camera is not None else None),
        "speaker_detail": speaker.detail if speaker is not None else None,
        "speaker_note": "macos_say follows the current macOS default output device.",
    }


def _collect_runtime_summary(settings: Settings) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    with tempfile.TemporaryDirectory(prefix="blink-local-doctor-runtime-") as tmp_dir:
        tmp_root = Path(tmp_dir)
        runtime_settings = settings.model_copy(
            update={
                "blink_always_on_enabled": True,
                "blink_local_model_prewarm": True,
                "brain_store_path": str(tmp_root / "brain_store.json"),
                "demo_report_dir": str(tmp_root / "demo_runs"),
                "demo_check_dir": str(tmp_root / "demo_checks"),
                "episode_export_dir": str(tmp_root / "episodes"),
                "shift_report_dir": str(tmp_root / "shift_reports"),
                "operator_auth_runtime_file": str(tmp_root / "operator_auth.json"),
            }
        )

        with build_desktop_runtime(settings=runtime_settings) as runtime:
            session = runtime.ensure_session(
                session_id="local-companion-doctor",
                user_id="local-companion-doctor",
                response_mode=ResponseMode.GUIDE,
            )
            status_snapshot = runtime.snapshot(session_id=session.session_id)
            summary.update(
                {
                    "context_mode": status_snapshot.runtime.context_mode.value,
                    "profile_summary": status_snapshot.runtime.profile_summary,
                    "resolved_backend_profile": status_snapshot.runtime.resolved_backend_profile,
                    "text_backend": status_snapshot.runtime.text_backend,
                    "stt_backend": status_snapshot.runtime.stt_backend,
                    "tts_backend": status_snapshot.runtime.tts_backend,
                    "auth_mode": status_snapshot.runtime.auth_mode,
                    "setup_complete": status_snapshot.runtime.setup_complete,
                    "config_source": status_snapshot.runtime.config_source,
                    "device_preset": status_snapshot.runtime.device_preset,
                    "operator_auth_token_source": status_snapshot.runtime.operator_auth_token_source,
                    "operator_auth_runtime_file": status_snapshot.runtime.operator_auth_runtime_file,
                    "selected_microphone_label": status_snapshot.runtime.selected_microphone_label,
                    "selected_camera_label": status_snapshot.runtime.selected_camera_label,
                    "selected_speaker_label": status_snapshot.runtime.selected_speaker_label,
                    "terminal_frontend_state": status_snapshot.runtime.terminal_frontend_state,
                    "terminal_frontend_detail": status_snapshot.runtime.terminal_frontend_detail,
                    "console_url": status_snapshot.runtime.console_url,
                    "console_launch_state": status_snapshot.runtime.console_launch_state,
                    "fallback_active": status_snapshot.runtime.fallback_state.active,
                    "startup_summary": (
                        status_snapshot.runtime.startup_summary.model_dump(mode="json")
                        if status_snapshot.runtime.startup_summary is not None
                        else None
                    ),
                    "missing_models": [issue.message for issue in status_snapshot.runtime.setup_issues if issue.category == "ollama"],
                    "status_probe": {
                        "label": "status_probe",
                        "ok": True,
                        "detail": (
                            f"text={status_snapshot.runtime.text_backend} "
                            f"stt={status_snapshot.runtime.stt_backend} "
                            f"context={status_snapshot.runtime.context_mode.value}"
                        ),
                    },
                }
            )

            summary["first_text_turn"] = _runtime_text_turn_probe(
                runtime=runtime,
                session_id="local-companion-doctor-first",
                prompt="Reply with exactly: first local text turn works.",
                label="first_text_turn",
                retry_on_transient_fallback=True,
                retry_delay_seconds=0.25,
            )
            summary["warm_text_turn"] = _runtime_text_turn_probe(
                runtime=runtime,
                session_id="local-companion-doctor-warm",
                prompt="Reply with exactly: warm local text turn works.",
                label="warm_text_turn",
                retry_on_transient_fallback=True,
                retry_delay_seconds=0.25,
            )
            summary["product_behavior_probe"] = _runtime_product_behavior_probe(
                runtime=runtime,
                session_id="local-companion-doctor-product",
            )
            summary["embedding_probe"] = _runtime_embedding_probe(runtime)
            summary["visual_question"] = _runtime_visual_question_probe(runtime=runtime, session_id=session.session_id)
            summary["memory_follow_up"] = _runtime_memory_follow_up_probe(runtime=runtime, session_id=session.session_id)
            summary["proactive_policy"] = _runtime_proactive_probe(runtime=runtime, session_id=session.session_id)
    return summary


def _runtime_text_turn_probe(
    *,
    runtime,
    session_id: str,
    prompt: str,
    label: str,
    retry_on_transient_fallback: bool = False,
    retry_delay_seconds: float = 0.0,
) -> dict[str, Any]:
    last_result: dict[str, Any] | None = None
    max_attempts = 2 if retry_on_transient_fallback else 1
    total_started = perf_counter()

    for attempt in range(1, max_attempts + 1):
        started = perf_counter()
        try:
            interaction = runtime.submit_text(
                prompt,
                session_id=session_id,
                voice_mode=VoiceRuntimeMode.STUB_DEMO,
                speak_reply=False,
                source="local_companion_doctor",
            )
        except Exception as exc:
            return {
                "label": label,
                "ok": False,
                "detail": f"probe_error:{exc}",
                "attempt_count": attempt,
                "recovered_after_retry": False,
            }
        attempt_latency_ms = round((perf_counter() - started) * 1000.0, 2)
        trace = runtime.orchestrator.get_trace(interaction.response.trace_id or "")
        engine = trace.reasoning.engine if trace is not None else None
        fallback_used = trace.reasoning.fallback_used if trace is not None else None
        text_backend_status = _runtime_text_backend_status(runtime=runtime, session_id=session_id)
        backend_failure_reason = text_backend_status.get("last_failure_reason")
        backend_timeout_seconds = text_backend_status.get("last_timeout_seconds")
        backend_retry_used = text_backend_status.get("cold_start_retry_used")
        ok = bool(
            interaction.response.reply_text
            and engine
            and str(engine).startswith("ollama:")
            and fallback_used is False
        )
        last_result = {
            "label": label,
            "ok": ok,
            "detail": (
                f"outcome={interaction.outcome}; "
                f"reply={interaction.response.reply_text or '-'}; "
                f"engine={engine or '-'}; "
                f"fallback_used={fallback_used}; "
                f"attempt={attempt}/{max_attempts}; "
                f"backend_failure={backend_failure_reason or '-'}; "
                f"backend_timeout_seconds={backend_timeout_seconds if backend_timeout_seconds is not None else '-'}; "
                f"backend_cold_retry_used={backend_retry_used}"
            ),
            "latency_ms": round((perf_counter() - total_started) * 1000.0, 2),
            "attempt_latency_ms": attempt_latency_ms,
            "attempt_count": attempt,
            "recovered_after_retry": attempt > 1 and ok,
            "outcome": interaction.outcome,
            "reply_text": interaction.response.reply_text,
            "engine": engine,
            "fallback_used": fallback_used,
            "backend_failure_reason": backend_failure_reason,
            "backend_timeout_seconds": backend_timeout_seconds,
            "backend_cold_retry_used": backend_retry_used,
        }
        if ok:
            return last_result
        if not retry_on_transient_fallback or attempt >= max_attempts:
            break
        if not _should_retry_text_probe(
            outcome=interaction.outcome,
            engine=engine,
            fallback_used=fallback_used,
            backend_failure_reason=backend_failure_reason,
        ):
            break
        if retry_delay_seconds > 0:
            sleep(retry_delay_seconds)

    return last_result or {
        "label": label,
        "ok": False,
        "detail": "probe_error:unknown",
        "attempt_count": 0,
        "recovered_after_retry": False,
    }


def _runtime_text_backend_status(*, runtime, session_id: str) -> dict[str, Any]:
    try:
        snapshot = runtime.snapshot(session_id=session_id)
    except Exception:
        return {}
    item = next(
        (entry for entry in snapshot.runtime.backend_status if entry.kind.value == "text_reasoning"),
        None,
    )
    if item is None:
        return {}
    return {
        "backend_id": item.backend_id,
        "status": item.status.value,
        "last_failure_reason": item.last_failure_reason,
        "last_timeout_seconds": item.last_timeout_seconds,
        "cold_start_retry_used": item.cold_start_retry_used,
        "last_success_latency_ms": item.last_success_latency_ms,
    }


def _should_retry_text_probe(
    *,
    outcome: str | None,
    engine: str | None,
    fallback_used: bool | None,
    backend_failure_reason: str | None,
) -> bool:
    if outcome == "fallback_reply":
        return True
    if fallback_used is True:
        return True
    if not engine or not str(engine).startswith("ollama:"):
        return True
    return backend_failure_reason in {
        "ollama_timeout",
        "ollama_timeout_after_cold_start_retry",
    }


def _runtime_embedding_probe(runtime) -> dict[str, Any]:
    started = perf_counter()
    try:
        vectors = runtime.app.state.backend_router.build_embedding_backend().embed(["local companion doctor embedding probe"])
    except Exception as exc:
        return {
            "label": "embedding_probe",
            "ok": False,
            "detail": f"embedding_error:{exc}",
        }
    latency_ms = round((perf_counter() - started) * 1000.0, 2)
    return {
        "label": "embedding_probe",
        "ok": bool(vectors and vectors[0]),
        "detail": f"vector_dim={len(vectors[0]) if vectors else 0}",
        "latency_ms": latency_ms,
    }


def _runtime_product_behavior_probe(*, runtime, session_id: str) -> dict[str, Any]:
    try:
        interaction = runtime.submit_text(
            "I had a long day. Give me one calm personal suggestion for tonight in one sentence.",
            session_id=session_id,
            voice_mode=VoiceRuntimeMode.STUB_DEMO,
            speak_reply=False,
            source="local_companion_doctor_product_behavior",
        )
    except Exception as exc:
        return {
            "label": "product_behavior_probe",
            "ok": False,
            "detail": f"product_behavior_error:{exc}",
        }
    reply = (interaction.response.reply_text or "").strip()
    lowered = reply.lower()
    venue_markers = ("front desk", "workshop room", "community center", "visitor", "check-in", "concierge")
    return {
        "label": "product_behavior_probe",
        "ok": bool(reply) and not any(marker in lowered for marker in venue_markers),
        "detail": f"outcome={interaction.outcome}; reply={reply or '-'}",
    }


def _runtime_visual_question_probe(*, runtime, session_id: str) -> dict[str, Any]:
    try:
        capture_result = runtime.capture_camera_observation(session_id=session_id, user_id="local-companion-doctor")
    except Exception as exc:
        return {
            "label": "visual_question",
            "ok": False,
            "detail": f"camera_error:{exc}",
        }
    try:
        interaction = runtime.submit_text(
            "What can you see right now?",
            session_id=session_id,
            voice_mode=VoiceRuntimeMode.STUB_DEMO,
            speak_reply=False,
            source="local_companion_doctor_visual",
        )
    except Exception as exc:
        return {
            "label": "visual_question",
            "ok": False,
            "detail": f"visual_question_error:{exc}",
        }
    summary = "-"
    if hasattr(capture_result, "snapshot"):
        summary = capture_result.snapshot.scene_summary or capture_result.snapshot.status.value
    return {
        "label": "visual_question",
        "ok": bool(interaction.response.reply_text),
        "detail": f"capture={summary}; outcome={interaction.outcome}; reply={interaction.response.reply_text or '-'}",
    }


def _runtime_memory_follow_up_probe(*, runtime, session_id: str) -> dict[str, Any]:
    try:
        runtime.submit_text(
            "Remind me to review the investor demo notes later today.",
            session_id=session_id,
            voice_mode=VoiceRuntimeMode.STUB_DEMO,
            speak_reply=False,
            source="local_companion_doctor_memory",
        )
        interaction = runtime.submit_text(
            "What do I need to remember?",
            session_id=session_id,
            voice_mode=VoiceRuntimeMode.STUB_DEMO,
            speak_reply=False,
            source="local_companion_doctor_memory",
        )
    except Exception as exc:
        return {
            "label": "memory_follow_up",
            "ok": False,
            "detail": f"memory_probe_error:{exc}",
        }
    snapshot = runtime.snapshot(session_id=session_id)
    reminder_count = snapshot.runtime.memory_status.open_reminder_count
    return {
        "label": "memory_follow_up",
        "ok": reminder_count >= 1,
        "detail": f"open_reminders={reminder_count}; outcome={interaction.outcome}; reply={interaction.response.reply_text or '-'}",
    }


def _runtime_proactive_probe(*, runtime, session_id: str) -> dict[str, Any]:
    runtime.submit_scene_observation(
        session_id=session_id,
        user_id="local-companion-doctor",
        person_present=True,
        people_count=1,
        engagement="engaged",
        scene_note="Doctor proactive probe",
    )
    runtime.run_supervisor_once()
    snapshot = runtime.snapshot(session_id=session_id)
    return {
        "label": "proactive_policy",
        "ok": snapshot.runtime.trigger_engine.enabled,
        "detail": (
            f"decision={snapshot.runtime.trigger_engine.last_decision.value}; "
            f"suppressed={snapshot.runtime.trigger_engine.suppressed_reason or '-'}"
        ),
    }


def _probe_whisper_smoke(*, binary: str | None, model_path: Path | None, timeout_seconds: float) -> dict[str, Any]:
    if not binary:
        return {"label": "raw_whisper_smoke", "ok": False, "detail": "whisper_cli_missing"}
    if model_path is None:
        return {"label": "raw_whisper_smoke", "ok": False, "detail": "whisper_model_missing"}
    if shutil.which("say") is None:
        return {"label": "raw_whisper_smoke", "ok": False, "detail": "say_command_missing"}

    with tempfile.TemporaryDirectory(prefix="blink-whisper-doctor-") as tmp_dir:
        audio_path = Path(tmp_dir) / "doctor_whisper.aiff"
        say_result = subprocess.run(
            ["say", "-o", str(audio_path), "Local whisper smoke test."],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if say_result.returncode != 0:
            return {"label": "raw_whisper_smoke", "ok": False, "detail": say_result.stderr.strip() or "say_failed"}

        whisper_input_path = audio_path
        ffmpeg_binary = shutil.which("ffmpeg")
        if ffmpeg_binary is not None:
            wav_path = Path(tmp_dir) / "doctor_whisper.wav"
            ffmpeg_result = subprocess.run(
                [ffmpeg_binary, "-loglevel", "error", "-y", "-i", str(audio_path), str(wav_path)],
                capture_output=True,
                text=True,
                timeout=15,
            )
            if ffmpeg_result.returncode == 0:
                whisper_input_path = wav_path

        started = perf_counter()
        whisper_result = subprocess.run(
            [binary, "-m", str(model_path), "-f", str(whisper_input_path), "-l", "en", "-nt"],
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
        latency_ms = round((perf_counter() - started) * 1000.0, 2)
        transcript = _normalize_whisper_output(whisper_result.stdout, whisper_result.stderr)
        errors = _normalize_whisper_errors(whisper_result.stdout, whisper_result.stderr)
        return {
            "label": "raw_whisper_smoke",
            "ok": whisper_result.returncode == 0 and bool(transcript) and not errors,
            "detail": transcript or errors or (whisper_result.stderr.strip() or "empty_whisper_output"),
            "latency_ms": latency_ms,
        }


def _normalize_whisper_output(stdout: str, stderr: str) -> str:
    combined = "\n".join(part.strip() for part in (stdout, stderr) if part.strip())
    lines = [line.strip() for line in combined.splitlines() if line.strip()]
    cleaned = [
        line
        for line in lines
        if not line.startswith("whisper_init")
        and not line.startswith("system_info")
        and not line.startswith("main:")
    ]
    return " ".join(cleaned).strip()


def _normalize_whisper_errors(stdout: str, stderr: str) -> str:
    combined = "\n".join(part.strip() for part in (stdout, stderr) if part.strip())
    lines = [line.strip() for line in combined.splitlines() if line.strip()]
    errors = [line for line in lines if line.lower().startswith("error:")]
    return " ".join(errors).strip()


def _ollama_model_list() -> list[str]:
    if shutil.which("ollama") is None:
        return []
    try:
        result = subprocess.run(
            ["ollama", "list"],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except Exception:
        return []
    if result.returncode != 0:
        return []
    models: list[str] = []
    for line in result.stdout.splitlines()[1:]:
        parts = line.split()
        if parts:
            models.append(parts[0].strip())
    return models


def _classify_issues(report: dict[str, Any]) -> None:
    issues: list[dict[str, Any]] = []
    binaries = report.get("binaries", {})
    whisper = report.get("whisper", {})
    auth = report.get("auth", {})
    ollama = report.get("ollama", {})
    runtime = report.get("runtime", {})
    devices = report.get("devices", {})
    next_actions: list[str] = []

    def add_issue(
        *,
        bucket: LocalCompanionCertificationVerdict,
        category: str,
        message: str,
        blocking: bool,
    ) -> None:
        issues.append(
            {
                "bucket": bucket.value,
                "category": category,
                "message": message,
                "blocking": blocking,
            }
        )

    if not binaries.get("ollama"):
        add_issue(
            bucket=LocalCompanionCertificationVerdict.MACHINE_BLOCKER,
            category="machine_install",
            message="Ollama is not installed on this Mac.",
            blocking=True,
        )
    if not ollama.get("reachable"):
        add_issue(
            bucket=LocalCompanionCertificationVerdict.MACHINE_BLOCKER,
            category="machine_install",
            message=f"Ollama is not reachable at {ollama.get('base_url') or '-'}.",
            blocking=True,
        )
    if not binaries.get("whisper_cli"):
        add_issue(
            bucket=LocalCompanionCertificationVerdict.MACHINE_BLOCKER,
            category="machine_install",
            message="whisper-cli is not installed or not on PATH.",
            blocking=True,
        )
    if not whisper.get("model_path"):
        add_issue(
            bucket=LocalCompanionCertificationVerdict.MACHINE_BLOCKER,
            category="machine_install",
            message="No local whisper.cpp model was discovered.",
            blocking=True,
        )

    if runtime.get("stt_backend") == "typed_input" and binaries.get("whisper_cli") and whisper.get("model_path"):
        add_issue(
            bucket=LocalCompanionCertificationVerdict.REPO_OR_RUNTIME_BUG,
            category="repo_configuration",
            message="The runtime still selected typed_input even though whisper.cpp is available locally.",
            blocking=True,
        )
    if runtime.get("text_backend") != "ollama_text":
        add_issue(
            bucket=LocalCompanionCertificationVerdict.REPO_OR_RUNTIME_BUG,
            category="repo_configuration",
            message=f"The runtime resolved text backend {runtime.get('text_backend') or '-'} instead of ollama_text for local companion mode.",
            blocking=True,
        )
    if auth.get("enabled") and auth.get("auth_mode") not in {"appliance_local_session", "appliance_localhost_trusted"} and not auth.get("runtime_file"):
        add_issue(
            bucket=LocalCompanionCertificationVerdict.REPO_OR_RUNTIME_BUG,
            category="repo_configuration",
            message="Operator auth is enabled but the runtime auth file path is missing.",
            blocking=True,
        )
    if devices.get("selected_microphone_label") is None:
        add_issue(
            bucket=LocalCompanionCertificationVerdict.MACHINE_BLOCKER,
            category="machine_install",
            message="No native microphone device was selected for local companion mode.",
            blocking=True,
        )
    if runtime.get("missing_models"):
        add_issue(
            bucket=LocalCompanionCertificationVerdict.MACHINE_BLOCKER,
            category="machine_install",
            message="Local Ollama setup is incomplete: " + ", ".join(runtime.get("missing_models", [])),
            blocking=True,
        )

    first_turn = runtime.get("first_text_turn", {})
    if not first_turn.get("ok"):
        add_issue(
            bucket=LocalCompanionCertificationVerdict.DEGRADED_BUT_ACCEPTABLE,
            category="model_latency",
            message=f"First local text turn did not complete cleanly: {first_turn.get('detail') or '-'}",
            blocking=False,
        )
    warm_turn = runtime.get("warm_text_turn", {})
    if not warm_turn.get("ok"):
        add_issue(
            bucket=(
                LocalCompanionCertificationVerdict.MACHINE_BLOCKER
                if not ollama.get("reachable")
                else LocalCompanionCertificationVerdict.DEGRADED_BUT_ACCEPTABLE
            ),
            category="model_latency",
            message=f"Warm local text turn did not complete cleanly: {warm_turn.get('detail') or '-'}",
            blocking=not ollama.get("reachable"),
        )
    product_behavior = runtime.get("product_behavior_probe", {})
    if not product_behavior.get("ok"):
        add_issue(
            bucket=LocalCompanionCertificationVerdict.REPO_OR_RUNTIME_BUG,
            category="product_behavior",
            message=f"Personal-local behavior probe did not produce the expected style: {product_behavior.get('detail') or '-'}",
            blocking=True,
        )
    visual_question = runtime.get("visual_question", {})
    if not visual_question.get("ok"):
        add_issue(
            bucket=LocalCompanionCertificationVerdict.MACHINE_BLOCKER,
            category="camera",
            message=f"Camera probe did not complete cleanly: {visual_question.get('detail') or '-'}",
            blocking=True,
        )

    report["issues"] = issues
    if any(item["bucket"] == LocalCompanionCertificationVerdict.MACHINE_BLOCKER.value for item in issues):
        report["doctor_status"] = LocalCompanionCertificationVerdict.MACHINE_BLOCKER.value
        next_actions = [
            "Install or fix the local machine dependencies and permissions called out above.",
            "Rerun local-companion-doctor after Ollama, camera, and audio readiness are green.",
            "Rerun local-companion-certify once the machine blockers are cleared.",
        ]
    elif any(item["bucket"] == LocalCompanionCertificationVerdict.REPO_OR_RUNTIME_BUG.value for item in issues):
        report["doctor_status"] = LocalCompanionCertificationVerdict.REPO_OR_RUNTIME_BUG.value
        next_actions = [
            "Fix the local companion runtime or profile-resolution issue called out above.",
            "Rerun local-companion-doctor to confirm the intended local path is now selected.",
            "Rerun local-companion-certify after the repo/runtime issue is fixed.",
        ]
    elif issues:
        report["doctor_status"] = LocalCompanionCertificationVerdict.DEGRADED_BUT_ACCEPTABLE.value
        next_actions = [
            "The product remains usable, but this Mac did not prove the full world-class local path yet.",
            "Review the degraded warnings above and rerun local-companion-certify after tightening them.",
            "Demo use is acceptable only if you accept the degraded local path.",
        ]
    else:
        report["doctor_status"] = LocalCompanionCertificationVerdict.CERTIFIED.value
        next_actions = [
            "This Mac is ready to prove the intended local companion path.",
            "Rerun local-companion-certify to produce a fresh certification bundle.",
            "Safe to demo.",
        ]
    report["next_actions"] = next_actions


def _run_text_command(args: list[str]) -> str | None:
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=10)
    except Exception:
        return None
    if result.returncode != 0:
        return None
    text = result.stdout.strip()
    return text or None


__all__ = [
    "render_local_companion_doctor_report",
    "run_local_companion_doctor",
]
