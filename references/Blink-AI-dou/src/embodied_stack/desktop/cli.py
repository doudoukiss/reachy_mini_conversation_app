from __future__ import annotations

import argparse
from contextlib import nullcontext
import json
import re
import sys
import threading
import time
from urllib.parse import quote
import webbrowser
from dataclasses import dataclass
from pathlib import Path

try:
    from prompt_toolkit import PromptSession
    from prompt_toolkit.history import FileHistory
    from prompt_toolkit.patch_stdout import patch_stdout
except ImportError:  # pragma: no cover - dependency/runtime guard
    PromptSession = None
    FileHistory = None
    patch_stdout = None

from embodied_stack.brain.auth import OperatorAuthManager
from embodied_stack.config import get_settings
from embodied_stack.desktop.doctor import run_local_companion_doctor
from embodied_stack.demo.performance_show import (
    SHOW_TUNING_PATHS,
    benchmark_show_narration,
    load_show_definition,
    select_show_definition,
)
from embodied_stack.demo.investor_scenes import INVESTOR_SCENES, INVESTOR_SCENE_SEQUENCES
from embodied_stack.shared.models import (
    TeacherReviewRequest,
    ActionApprovalResolutionRequest,
    ActionReplayRequestRecord,
    CompanionAudioMode,
    CompanionContextMode,
    PerformanceRunRequest,
    ResponseMode,
    VoiceRuntimeMode,
    WorkflowRunActionRequestRecord,
    WorkflowStartRequestRecord,
)

from .app import build_desktop_runtime, main as serve_main


_ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")
_VISIBLE_ESCAPE_RE = re.compile(r"\^\[\[[0-9;?]*[A-Za-z~]")
_DISCARD_NOISE_SENTINEL = "__discard_terminal_noise__"
_PERFORMANCE_DEFAULT_SHOW_NAME = "investor_expressive_motion_v8"


def _normalize_companion_input(raw: str) -> str:
    normalized = raw.replace("\r", "").replace("\x00", "").replace("^M", "")
    normalized = _ANSI_ESCAPE_RE.sub("", normalized)
    normalized = _VISIBLE_ESCAPE_RE.sub("", normalized)
    normalized = normalized.replace("companion>", " ").strip()
    if normalized in {"", "/", "companion"}:
        return ""
    if normalized == "":
        return ""
    return normalized


def _input_contains_terminal_noise(raw: str) -> bool:
    return bool(_ANSI_ESCAPE_RE.search(raw) or _VISIBLE_ESCAPE_RE.search(raw) or "companion>" in raw)


@dataclass
class _CompanionConsoleHost:
    app: object
    port: int
    host: str = "127.0.0.1"
    server: object | None = None
    thread: threading.Thread | None = None
    error: BaseException | None = None

    @property
    def console_url(self) -> str:
        return f"http://{self.host}:{self.port}/console"

    def presence_url_for(self, *, session_id: str | None = None) -> str:
        return _build_presence_url(self.console_url, session_id=session_id)

    def start(self) -> None:
        import uvicorn

        config = uvicorn.Config(
            self.app,
            host=self.host,
            port=self.port,
            log_level="warning",
            access_log=False,
            lifespan="off",
        )
        server = uvicorn.Server(config)
        self.server = server

        def _run() -> None:
            try:
                server.run()
            except BaseException as exc:  # pragma: no cover - defensive
                self.error = exc

        self.thread = threading.Thread(target=_run, name="blink-companion-console", daemon=True)
        self.thread.start()

        deadline = time.monotonic() + 8.0
        while time.monotonic() < deadline:
            if self.error is not None:
                raise RuntimeError(f"companion_console_start_failed:{self.error}") from self.error
            if getattr(server, "started", False):
                return
            if self.thread is not None and not self.thread.is_alive():
                break
            time.sleep(0.05)
        raise RuntimeError(f"companion_console_start_timeout:{self.port}")

    def stop(self) -> None:
        server = self.server
        if server is None:
            return
        server.should_exit = True
        if self.thread is not None:
            self.thread.join(timeout=5.0)


def _resolve_terminal_frontend_state(mode: str) -> tuple[bool, str, str]:
    if mode == "off":
        return False, "disabled", "terminal_ui_disabled_by_flag"
    if PromptSession is None:
        return False, "disabled", "prompt_toolkit_not_available"

    stdin_tty = bool(getattr(sys.stdin, "isatty", lambda: False)())
    stdout_tty = bool(getattr(sys.stdout, "isatty", lambda: False)())
    if stdin_tty and stdout_tty:
        return True, "enabled", "prompt_toolkit_main_thread"

    detail_parts: list[str] = []
    if not stdin_tty:
        detail_parts.append("stdin_not_tty")
    if not stdout_tty:
        detail_parts.append("stdout_not_tty")
    detail = ",".join(detail_parts) or "terminal_frontend_unavailable"
    return False, ("degraded" if mode == "on" else "disabled"), detail


def _launch_console(console_url: str, *, open_console: bool) -> str:
    if not open_console:
        return "available"
    try:
        opened = webbrowser.open(console_url, new=2)
    except Exception:
        return "open_failed"
    return "opened" if opened else "available"


def _build_presence_url(console_url: str, *, session_id: str | None = None) -> str:
    base = console_url.removesuffix("/console")
    url = f"{base}/presence"
    if session_id:
        url = f"{url}?session_id={quote(session_id, safe='')}"
    return url


def _build_prompt_session() -> PromptSession | None:
    if PromptSession is None:
        return None
    history = None
    if FileHistory is not None:
        history_path = Path("runtime/companion_history.txt")
        history_path.parent.mkdir(parents=True, exist_ok=True)
        history = FileHistory(str(history_path))
    return PromptSession(history=history)


def _prompt_terminal_command(session: object, *, prompt: str = "companion> ") -> str:
    context = patch_stdout() if patch_stdout is not None else nullcontext()
    with context:
        raw = session.prompt(prompt)
    normalized = _normalize_companion_input(raw)
    if normalized == "" and _input_contains_terminal_noise(raw):
        return _DISCARD_NOISE_SENTINEL
    return normalized


def _should_start_console_host(*, terminal_enabled: bool, open_console: bool) -> bool:
    return open_console or not terminal_enabled


def _format_device_health(snapshot, kind: str) -> str:
    item = next((entry for entry in snapshot.runtime.device_health if entry.kind.value == kind), None)
    if item is None:
        return f"{kind}=unknown"
    detail = item.detail or item.backend or item.state.value
    return f"{kind}={item.state.value}:{detail}"


def _format_text_backend(snapshot) -> str:
    item = next((entry for entry in snapshot.runtime.backend_status if entry.kind.value == "text_reasoning"), None)
    if item is None:
        return f"text={snapshot.runtime.text_backend or '-'}"
    model = item.active_model or item.requested_model or item.model or "-"
    warmth = "warm" if item.warm else "cold"
    return f"text={item.backend_id}:{item.status.value}:{model}:{warmth}"


def _format_latency_ms(value: float | None) -> str:
    return "-" if value is None else f"{round(value, 2)}ms"


def _format_body_line(snapshot) -> str | None:
    body_state = snapshot.telemetry.body_state
    if body_state is None or body_state.driver_mode.value != "serial":
        return None
    return (
        "body "
        f"transport={body_state.transport_mode or '-'} "
        f"port={body_state.transport_port or '-'} "
        f"baud={body_state.transport_baud_rate or '-'} "
        f"healthy={body_state.transport_healthy} "
        f"confirmed_live={body_state.transport_confirmed_live} "
        f"calibration={body_state.calibration_status or '-'} "
        f"armed={body_state.live_motion_armed} "
        f"live_motion={body_state.live_motion_enabled} "
        f"last={body_state.last_command_outcome.outcome_status if body_state.last_command_outcome is not None else '-'}"
    )


def _print_companion_startup_summary(snapshot, *, console_opt_in: bool) -> None:
    runtime = snapshot.runtime
    auth_mode = "enabled" if runtime.operator_auth_enabled else "disabled"
    print("start_here text=plain_text voice=/listen presence=/presence help=/help status=/status silence=/silence")
    print("power_user camera=/camera actions=/actions status export=/export quit=/quit")
    print(
        "readiness "
        f"terminal={runtime.terminal_frontend_state}:{runtime.terminal_frontend_detail or '-'} "
        f"{_format_text_backend(snapshot)} "
        f"{_format_device_health(snapshot, 'microphone')} "
        f"{_format_device_health(snapshot, 'camera')} "
        f"{_format_device_health(snapshot, 'speaker')} "
        f"auth={auth_mode}:{runtime.operator_auth_token_source or '-'}"
    )
    print(
        "native_devices "
        f"microphone={runtime.selected_microphone_label or '-'} "
        f"camera={runtime.selected_camera_label or '-'}"
    )
    print("speaker_note=macos_say follows the current macOS default output device.")
    initiative_mode = "silenced" if runtime.initiative_engine.suppression_reason else runtime.initiative_engine.last_decision.value
    print(
        "mode "
        "surface=terminal_primary "
        f"context={runtime.context_mode.value} "
        f"audio={runtime.audio_mode.value} "
        f"presence={runtime.presence_runtime.state.value} "
        f"initiative={initiative_mode} "
        f"body={runtime.body_status or runtime.body_driver_mode.value}"
    )
    print("controls stop_voice=/interrupt stop_initiative=/silence stop_runtime=/quit reset_session='restart with --session-id <new>'")
    if runtime.operator_auth_enabled:
        print(
            "auth "
            f"token_source={runtime.operator_auth_token_source or '-'} "
            f"runtime_file={runtime.operator_auth_runtime_file or '-'}"
        )
    body_line = _format_body_line(snapshot)
    if body_line is not None:
        print(body_line)
    print(
        "actions "
        f"pending={runtime.action_plane.pending_approval_count} "
        f"waiting_workflows={runtime.action_plane.waiting_workflow_count} "
        f"review_required={runtime.action_plane.review_required_count} "
        f"degraded_connectors={runtime.action_plane.degraded_connector_count}"
    )
    readiness = runtime.local_companion_readiness
    if readiness is not None:
        print(
            "certification "
            f"status={readiness.verdict.value} "
            f"machine_ready={readiness.machine_ready} "
            f"product_ready={readiness.product_ready} "
            f"last_certified={readiness.last_certified_at or '-'} "
            f"blockers={len(readiness.machine_blockers)} "
            f"degraded={len(readiness.degraded_warnings)}"
        )
    else:
        print("certification status=unknown machine_ready=False product_ready=False last_certified=- blockers=0 degraded=0")
    if runtime.console_url:
        print(
            "console "
            f"url={runtime.console_url} "
            f"launch={runtime.console_launch_state or '-'} "
            "role=secondary_operator_surface"
        )
        print(
            "presence "
            f"url={_build_presence_url(runtime.console_url, session_id=snapshot.active_session_id)} "
            "role=optional_character_surface"
        )
    elif console_opt_in:
        print("console unavailable; terminal mode remains active. use=/console to retry.")
    else:
        print("console optional use=/console or start_with=--open-console")
        print("presence optional use=/presence")


def _print_action_center_follow_up(runtime, *, session_id: str) -> None:
    overview = runtime.operator_console.get_action_plane_overview(session_id=session_id)
    if not overview.attention_items:
        return
    focus = next(
        (
            item
            for item in overview.attention_items
            if item.action_id is not None and item.action_id == overview.status.last_action_id
        ),
        overview.attention_items[0],
    )
    print(f"action_center {focus.kind} severity={focus.severity} title={focus.title}")
    print(f"operator_summary={focus.summary}")
    if focus.next_step_hint:
        print(f"next_step={focus.next_step_hint}")
    if focus.kind == "approval" and focus.action_id:
        print(f"approval_help use='/actions approvals' then '/actions approve {focus.action_id}' or '/actions reject {focus.action_id}'")


def _describe_action_policy_reason(
    *,
    detail: object | None,
    policy_decision: object | None = None,
    risk_class: object | None = None,
    connector_id: object | None = None,
    action_name: object | None = None,
) -> str:
    detail_value = getattr(detail, "value", detail)
    decision_value = getattr(policy_decision, "value", policy_decision) or "-"
    risk_value = getattr(risk_class, "value", risk_class) or "-"
    connector_value = getattr(connector_id, "value", connector_id) or "connector"
    action_value = getattr(action_name, "value", action_name) or "action"
    reason_map = {
        "operator_approval_required": (
            f"Blink paused before {action_value} because it is operator-sensitive work."
        ),
        "implicit_operator_approval": (
            f"{action_value} counts as operator-launched work, so no second approval is needed."
        ),
        "local_write_allowed": f"{action_value} is a low-risk local write.",
        "read_only_allowed": f"{action_value} is read-only.",
        "proactive_local_write_preview_only": (
            f"Blink only previewed {action_value}; proactive writes stay preview-only by default."
        ),
        "risk_class_rejected": (
            f"Blink blocked {action_value} because it is high-risk or irreversible."
        ),
        "connector_missing": f"Blink could not run {action_value} because {connector_value} is missing.",
        "connector_unconfigured": f"Blink could not run {action_value} because {connector_value} is not configured.",
        "connector_unsupported": f"Blink could not run {action_value} because {connector_value} does not support it.",
        "policy_default_reject": (
            f"Blink blocked {action_value} because the policy layer did not find a safe allow path."
        ),
    }
    if detail_value in reason_map:
        return f"{reason_map[detail_value]} (decision={decision_value}, risk={risk_value})"
    if isinstance(detail_value, str) and detail_value:
        return detail_value.replace("_", " ")
    return f"Blink paused {action_value} for policy review. (decision={decision_value}, risk={risk_value})"


def _print_companion_help(*, console_started: bool) -> None:
    print("Daily use: type naturally for a text turn or use /listen for one push-to-talk voice turn.")
    print("/help shows this guide again.")
    print("/status prints runtime state, device health, latency, model residency, and the latest action follow-up.")
    print("/silence pauses proactive initiative for 15 minutes by default. /silence off re-enables it immediately.")
    print("/open-mic on switches to hands-free listening. /open-mic off returns to push-to-talk mode.")
    print("/presence opens the optional lightweight character shell for the same runtime.")
    print("/camera captures one explicit visual snapshot without starting a voice turn.")
    print("/interrupt stops the current speech output.")
    if console_started:
        print("/console reopens the optional browser operator surface or prints its URL.")
    else:
        print("/console starts the optional browser operator surface from this runtime and prints its URL.")
    print("/actions status shows pending approvals, workflows, and degraded connectors.")
    print("/actions approvals explains why Blink paused and what approval will unblock.")
    print("/export writes the current session bundle. /quit exits and also exports unless --no-export was passed.")
    print("To start fresh, restart local-companion with a new --session-id. Use uv run blink-appliance --reset-runtime only when the browser runtime itself is stuck.")


def _print_companion_status_follow_up(*, console_started: bool) -> None:
    console_hint = "/console" if console_started else "/console(optional)"
    presence_hint = "/presence"
    print(
        "next "
        f"text=plain_text voice=/listen presence={presence_hint} help=/help silence=/silence camera=/camera actions='/actions status' console={console_hint}"
    )
    print("stop_reset stop_voice=/interrupt stop_runtime=/quit reset_session='restart with --session-id <new>'")


def _ensure_companion_console_host(*, runtime, console_host: _CompanionConsoleHost | None, port: int) -> _CompanionConsoleHost:
    if console_host is not None:
        if runtime.operator_console.console_url is None:
            runtime.operator_console.console_url = console_host.console_url
        if runtime.operator_console.console_launch_state in {None, "opt_in", "failed"}:
            runtime.operator_console.console_launch_state = "available"
        return console_host

    host = _CompanionConsoleHost(runtime.app, port=port)
    host.start()
    runtime.operator_console.console_url = host.console_url
    runtime.operator_console.console_launch_state = "available"
    return host


def _handle_companion_actions_command(raw: str, *, runtime, session_id: str) -> bool:
    if not raw.startswith("/actions"):
        return False
    parts = raw.split()
    command = parts[1] if len(parts) > 1 else "status"
    overview = runtime.operator_console.get_action_plane_overview(session_id=session_id)
    health_by_connector = {
        item.connector_id: item
        for item in overview.status.connector_health
    }
    attention_by_action = {
        item.action_id: item
        for item in overview.attention_items
        if getattr(item, "action_id", None)
    }

    if command == "status":
        print(
            "actions "
            f"pending={overview.status.pending_approval_count} "
            f"waiting_workflows={overview.status.waiting_workflow_count} "
            f"review_required={overview.status.review_required_count} "
            f"degraded_connectors={overview.status.degraded_connector_count}"
        )
        for item in overview.attention_items[:5]:
            print(
                f"{item.kind} severity={item.severity} title={item.title} "
                f"summary={item.summary}"
            )
            if item.next_step_hint:
                print(f"next_step={item.next_step_hint}")
        if overview.status.pending_approval_count:
            print("approval_help use='/actions approvals' for the policy reason and the exact next approval command.")
        return True

    if command == "approvals":
        if not overview.approvals:
            print("approvals none")
            return True
        execution_by_action = {item.action_id: item for item in overview.recent_history}
        for item in overview.approvals:
            execution = execution_by_action.get(item.action_id)
            attention = attention_by_action.get(item.action_id)
            risk = getattr(getattr(item, "request", None), "risk_class", None)
            risk_value = getattr(risk, "value", risk) or "-"
            print(
                f"{item.action_id} tool={item.tool_name} action={item.action_name} "
                f"connector={item.connector_id} state={item.approval_state.value} "
                f"policy={getattr(item.policy_decision, 'value', item.policy_decision)} "
                f"risk={risk_value}"
            )
            why = (
                attention.summary
                if attention is not None and attention.summary
                else execution.operator_summary
                if execution is not None and execution.operator_summary
                else _describe_action_policy_reason(
                    detail=getattr(item, "detail", None),
                    policy_decision=getattr(item, "policy_decision", None),
                    risk_class=risk,
                    connector_id=getattr(item, "connector_id", None),
                    action_name=getattr(item, "action_name", None) or getattr(item, "tool_name", None),
                )
            )
            print(f"why={why}")
            next_step = (
                attention.next_step_hint
                if attention is not None and attention.next_step_hint
                else execution.next_step_hint
                if execution is not None and execution.next_step_hint
                else f"Use /actions approve {item.action_id} or /actions reject {item.action_id}."
            )
            print(f"next_step={next_step}")
        return True

    if command in {"approve", "reject"}:
        if len(parts) < 3:
            print(f"usage=/actions {command} <action_id> [note]")
            return True
        action_id = parts[2]
        note = raw.split(None, 3)[3].strip() if len(parts) > 3 else None
        request = ActionApprovalResolutionRequest(action_id=action_id, operator_note=note)
        response = (
            runtime.operator_console.approve_action_plane_action(request)
            if command == "approve"
            else runtime.operator_console.reject_action_plane_action(request)
        )
        print(
            f"{response.action_id} approval={response.approval_state.value} "
            f"execution={(response.execution.status.value if response.execution is not None else '-')}"
        )
        if response.execution is not None and response.execution.operator_summary:
            print(f"operator_summary={response.execution.operator_summary}")
        if response.execution is not None and response.execution.next_step_hint:
            print(f"next_step={response.execution.next_step_hint}")
        return True

    if command == "history":
        try:
            limit = int(parts[2]) if len(parts) > 2 else 10
        except ValueError:
            print("usage=/actions history [limit]")
            return True
        for item in overview.recent_history[:limit]:
            print(
                f"{item.action_id} status={item.status.value} tool={item.tool_name} "
                f"action={item.action_name} connector={item.connector_id}"
            )
            if item.operator_summary:
                print(f"operator_summary={item.operator_summary}")
        return True

    if command == "connectors":
        for item in overview.connectors:
            health = health_by_connector.get(item.connector_id)
            print(
                f"{item.connector_id} supported={item.supported} configured={item.configured} "
                f"status={(health.status if health is not None else '-')}"
            )
        return True

    if command == "workflows":
        if not overview.active_workflows:
            print("workflows none")
            return True
        for item in overview.active_workflows:
            print(
                f"{item.workflow_run_id} workflow={item.workflow_id} status={item.status.value} "
                f"step={item.current_step_label or '-'} pause={(item.pause_reason.value if item.pause_reason else '-')}"
            )
            if item.detail:
                print(f"detail={item.detail}")
        return True

    if command == "bundle":
        if len(parts) < 3:
            print("usage=/actions bundle <bundle_id>")
            return True
        detail = runtime.operator_console.get_action_plane_bundle(parts[2])
        if detail is None:
            print(f"bundle_not_found={parts[2]}")
            return True
        manifest = detail.manifest
        print(
            f"{manifest.bundle_id} root={manifest.root_kind.value} "
            f"status={(manifest.final_status.value if hasattr(manifest.final_status, 'value') else manifest.final_status) or '-'}"
        )
        print(
            f"approvals={len(detail.approval_events)} connector_calls={len(detail.connector_calls)} "
            f"replays={len(detail.replays)} teacher_annotations={len(detail.teacher_annotations)}"
        )
        if manifest.artifact_dir:
            print(f"artifact_dir={manifest.artifact_dir}")
        return True

    print("usage=/actions status|approvals|approve <action_id> [note]|reject <action_id> [note]|history [limit]|connectors|workflows|bundle <bundle_id>")
    return True


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Blink-AI local companion and desktop runtime tools")
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("serve", help="Run the FastAPI desktop runtime server")

    shell = subparsers.add_parser("shell", help="Run a local typed-input desktop shell")
    shell.add_argument("--session-id", default="desktop-local")
    shell.add_argument("--user-id", default=None)
    shell.add_argument("--response-mode", default="guide")
    shell.add_argument("--voice-mode", choices=[item.value for item in VoiceRuntimeMode], default=None)
    shell.add_argument("--no-speak", action="store_true")
    shell.add_argument("--no-export", action="store_true")

    local_loop = subparsers.add_parser("local-loop", help="Run the native desktop-local conversation loop")
    local_loop.add_argument("--session-id", default="desktop-local-live")
    local_loop.add_argument("--user-id", default=None)
    local_loop.add_argument("--response-mode", default="guide")
    local_loop.add_argument("--voice-mode", choices=[item.value for item in VoiceRuntimeMode], default=None)
    local_loop.add_argument("--no-speak", action="store_true")
    local_loop.add_argument("--no-camera", action="store_true")
    local_loop.add_argument("--no-export", action="store_true")

    companion = subparsers.add_parser(
        "companion",
        help="Run the terminal-first daily companion loop",
        description=(
            "Run Blink-AI as the daily-use terminal-first companion.\n"
            "Plain text sends a turn, /listen captures one push-to-talk voice turn,\n"
            "/presence opens the optional lightweight character shell,\n"
            "and /console opens the optional browser operator surface."
        ),
        epilog=(
            "Examples:\n"
            "  uv run local-companion\n"
            "  uv run local-companion --audio-mode open_mic\n"
            "  uv run local-companion --open-console\n\n"
            "Inside the loop:\n"
            "  plain text        send a typed turn\n"
            "  /listen           capture one voice turn\n"
            "  /presence         open the optional character shell\n"
            "  /silence 15       pause proactive initiative for 15 minutes\n"
            "  /status           inspect health, latency, and residency\n"
            "  /actions status   inspect pending approvals and workflows\n"
            "  /console          open the optional browser operator view\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    companion.prog = "local-companion"
    companion.add_argument("--session-id", default="local-companion-live", help="Session id to resume or create")
    companion.add_argument("--user-id", default=None, help="Optional user id for memory continuity")
    companion.add_argument("--response-mode", default="guide", help="Reply style for the interaction loop")
    companion.add_argument(
        "--voice-mode",
        choices=[item.value for item in VoiceRuntimeMode],
        default=None,
        help="Force a specific voice runtime mode instead of the profile default",
    )
    companion.add_argument(
        "--audio-mode",
        choices=[item.value for item in CompanionAudioMode],
        default=None,
        help="Choose push-to-talk or open-mic behavior for the terminal loop",
    )
    companion.add_argument(
        "--context-mode",
        choices=[item.value for item in CompanionContextMode],
        default=None,
        help="Override the context mode; defaults to personal_local for daily use",
    )
    companion.add_argument(
        "--terminal-ui",
        choices=["auto", "on", "off"],
        default="auto",
        help="Force terminal UI on or off instead of auto-detecting TTY support",
    )
    companion.add_argument("--console-port", type=int, default=None, help="Port for the optional browser console host")
    console_flags = companion.add_mutually_exclusive_group()
    console_flags.add_argument("--open-console", action="store_true", help="Open the optional browser console at startup")
    console_flags.add_argument("--no-open-console", action="store_true", help="Keep startup terminal-only")
    companion.add_argument("--no-speak", action="store_true", help="Disable spoken replies and keep output text-only")
    companion.add_argument("--no-camera", action="store_true", help="Disable background or manual camera capture")
    companion.add_argument("--no-export", action="store_true", help="Skip session bundle export on exit")

    doctor = subparsers.add_parser("doctor", help="Probe the local companion stack and write a machine report")
    doctor.add_argument("--write", default="runtime/diagnostics/local_mbp_config_report.md")

    connector_status = subparsers.add_parser("connector-status", help="Show Action Plane connector status")
    connector_status.add_argument("--json", action="store_true")

    approval_list = subparsers.add_parser("approval-list", help="List pending Action Plane approvals")
    approval_list.add_argument("--json", action="store_true")

    approval_approve = subparsers.add_parser("approval-approve", help="Approve a pending Action Plane action")
    approval_approve.add_argument("action_id")
    approval_approve.add_argument("--note", default=None)

    approval_reject = subparsers.add_parser("approval-reject", help="Reject a pending Action Plane action")
    approval_reject.add_argument("action_id")
    approval_reject.add_argument("--note", default=None)

    action_history = subparsers.add_parser("action-history", help="Show recent Action Plane execution history")
    action_history.add_argument("--limit", type=int, default=25)
    action_history.add_argument("--json", action="store_true")

    replay_action = subparsers.add_parser("replay-action", help="Replay a prior Action Plane action")
    replay_action.add_argument("action_id")
    replay_action.add_argument("--note", default=None)

    bundle_list = subparsers.add_parser("action-bundle-list", help="List recent Action Plane flywheel bundles")
    bundle_list.add_argument("--session-id", default=None)
    bundle_list.add_argument("--limit", type=int, default=25)
    bundle_list.add_argument("--json", action="store_true")

    bundle_show = subparsers.add_parser("action-bundle-show", help="Show a single Action Plane flywheel bundle")
    bundle_show.add_argument("bundle_id")
    bundle_show.add_argument("--json", action="store_true")

    bundle_teacher = subparsers.add_parser(
        "action-bundle-teacher-review",
        help="Attach teacher feedback to an Action Plane bundle",
    )
    bundle_teacher.add_argument("bundle_id")
    bundle_teacher.add_argument("--review-value", default="needs_revision")
    bundle_teacher.add_argument("--label", default=None)
    bundle_teacher.add_argument("--note", default=None)
    bundle_teacher.add_argument("--author", default="operator_console")
    bundle_teacher.add_argument("--action-feedback-labels", default="")
    bundle_teacher.add_argument("--benchmark-tags", default="")

    replay_bundle = subparsers.add_parser(
        "replay-action-bundle",
        help="Replay a stored Action Plane bundle with deterministic backends",
    )
    replay_bundle.add_argument("bundle_id")
    replay_bundle.add_argument("--note", default=None)
    replay_bundle.add_argument("--approved-action-id", action="append", default=[])
    replay_bundle.add_argument("--json", action="store_true")

    workflow_list = subparsers.add_parser("workflow-list", help="List available Action Plane workflows")
    workflow_list.add_argument("--json", action="store_true")

    workflow_runs = subparsers.add_parser("workflow-runs", help="List Action Plane workflow runs")
    workflow_runs.add_argument("--session-id", default=None)
    workflow_runs.add_argument("--limit", type=int, default=25)
    workflow_runs.add_argument("--json", action="store_true")

    workflow_start = subparsers.add_parser("workflow-start", help="Start an Action Plane workflow")
    workflow_start.add_argument("workflow_id")
    workflow_start.add_argument("--session-id", default=None)
    workflow_start.add_argument("--inputs", default="{}")
    workflow_start.add_argument("--note", default=None)

    workflow_resume = subparsers.add_parser("workflow-resume", help="Resume an Action Plane workflow")
    workflow_resume.add_argument("workflow_run_id")
    workflow_resume.add_argument("--note", default=None)

    workflow_retry = subparsers.add_parser("workflow-retry", help="Retry the current failed Action Plane workflow step")
    workflow_retry.add_argument("workflow_run_id")
    workflow_retry.add_argument("--note", default=None)

    workflow_pause = subparsers.add_parser("workflow-pause", help="Pause an Action Plane workflow")
    workflow_pause.add_argument("workflow_run_id")
    workflow_pause.add_argument("--note", default=None)

    subparsers.add_parser("token", help="Print the active persistent local console token")

    reset = subparsers.add_parser("reset", help="Reset the desktop demo runtime to a known state")
    reset.add_argument("--keep-demo-runs", action="store_true")
    reset.add_argument("--keep-memory", action="store_true")
    reset.add_argument("--no-edge-reset", action="store_true")

    scene = subparsers.add_parser("scene", help="Run one investor scene")
    scene.add_argument("scene_name", choices=sorted(INVESTOR_SCENES))
    scene.add_argument("--session-id", default=None)
    scene.add_argument("--response-mode", default="guide")
    scene.add_argument("--voice-mode", choices=[item.value for item in VoiceRuntimeMode], default=None)
    scene.add_argument("--no-speak", action="store_true")
    scene.add_argument("--reset-first", action="store_true")

    story = subparsers.add_parser("story", help="Reset and run a curated investor story sequence")
    story.add_argument("--story-name", choices=sorted(INVESTOR_SCENE_SEQUENCES), default="desktop_story")
    story.add_argument("--session-id", default=None)
    story.add_argument("--response-mode", default="guide")
    story.add_argument("--voice-mode", choices=[item.value for item in VoiceRuntimeMode], default=None)
    story.add_argument("--no-speak", action="store_true")
    story.add_argument("--no-reset", action="store_true")
    story.add_argument("--no-export", action="store_true")

    companion_story = subparsers.add_parser("companion-story", help="Reset and run the maintained local companion story")
    companion_story.add_argument("--story-name", choices=sorted(INVESTOR_SCENE_SEQUENCES), default="local_companion_story")
    companion_story.add_argument("--session-id", default=None)
    companion_story.add_argument("--response-mode", default="guide")
    companion_story.add_argument("--voice-mode", choices=[item.value for item in VoiceRuntimeMode], default=None)
    companion_story.add_argument("--no-speak", action="store_true")
    companion_story.add_argument("--no-reset", action="store_true")
    companion_story.add_argument("--no-export", action="store_true")

    performance_catalog = subparsers.add_parser(
        "performance-catalog",
        help="List deterministic investor performance shows and active run status",
    )
    performance_catalog.add_argument("--json", action="store_true")

    performance_dry_run = subparsers.add_parser(
        "performance-dry-run",
        help="Validate and print the ordered cue plan for a deterministic investor performance show",
    )
    performance_dry_run.add_argument("show_name")
    performance_dry_run.add_argument("--segment", dest="segment_ids", action="append", default=[])
    performance_dry_run.add_argument("--cue", dest="cue_ids", action="append", default=[])
    performance_dry_run.add_argument("--narration-only", action="store_true")
    performance_dry_run.add_argument("--proof-only", action="store_true")
    performance_dry_run.add_argument("--proof-backend-mode", choices=["deterministic_show", "live_companion_proof"], default=None)
    performance_dry_run.add_argument("--language", default=None)
    performance_dry_run.add_argument("--narration-voice-preset", default=None)
    performance_dry_run.add_argument("--narration-voice-name", default=None)
    performance_dry_run.add_argument("--narration-voice-rate", type=int, default=None)

    performance_show = subparsers.add_parser(
        "performance-show",
        help="Run a deterministic investor performance show against the current local runtime",
    )
    performance_show.add_argument("show_name")
    performance_show.add_argument("--session-id", default=None)
    performance_show.add_argument("--segment", dest="segment_ids", action="append", default=[])
    performance_show.add_argument("--cue", dest="cue_ids", action="append", default=[])
    performance_show.add_argument("--response-mode", default=None)
    performance_show.add_argument("--proof-backend-mode", choices=["deterministic_show", "live_companion_proof"], default=None)
    performance_show.add_argument("--proof-voice-mode", choices=[item.value for item in VoiceRuntimeMode], default=None)
    performance_show.add_argument("--narration-voice-mode", choices=[item.value for item in VoiceRuntimeMode], default=None)
    performance_show.add_argument("--language", default=None)
    performance_show.add_argument("--narration-voice-preset", default=None)
    performance_show.add_argument("--narration-voice-name", default=None)
    performance_show.add_argument("--narration-voice-rate", type=int, default=None)
    performance_show.add_argument("--no-narration", action="store_true")
    performance_show.add_argument("--narration-only", action="store_true")
    performance_show.add_argument("--proof-only", action="store_true")
    performance_show.add_argument("--force-degraded-cue", dest="force_degraded_cue_ids", action="append", default=[])
    performance_show.add_argument("--reset-runtime", action="store_true")
    performance_show.add_argument("--background", action="store_true")

    performance_benchmark = subparsers.add_parser(
        "performance-benchmark",
        help="Benchmark narration timing for a performance show with the selected voice and language",
    )
    performance_benchmark.add_argument("show_name")
    performance_benchmark.add_argument("--segment", dest="segment_ids", action="append", default=[])
    performance_benchmark.add_argument("--cue", dest="cue_ids", action="append", default=[])
    performance_benchmark.add_argument("--language", default=None)
    performance_benchmark.add_argument("--narration-voice-mode", choices=[item.value for item in VoiceRuntimeMode], default=None)
    performance_benchmark.add_argument("--narration-voice-preset", default=None)
    performance_benchmark.add_argument("--narration-voice-name", default=None)
    performance_benchmark.add_argument("--narration-voice-rate", type=int, default=None)
    performance_benchmark.add_argument("--json", action="store_true")

    return parser


def _print_snapshot_status(snapshot) -> None:
    runtime = snapshot.runtime
    active_skill = runtime.last_active_skill.skill_name if runtime.last_active_skill is not None else "-"
    perception_age = (
        f"{runtime.perception_freshness.age_seconds}s"
        if runtime.perception_freshness.age_seconds is not None
        else "-"
    )
    print(
        "status "
        f"profile={runtime.profile_summary or '-'} "
        f"model={runtime.resolved_model_profile or runtime.model_profile or '-'} "
        f"backend={runtime.resolved_backend_profile or runtime.backend_profile or '-'} "
        f"context={runtime.context_mode.value} "
        f"skill={active_skill} "
        f"perception={runtime.perception_status or runtime.perception_provider_mode.value} "
        f"freshness={runtime.perception_freshness.status}:{perception_age} "
        f"memory={runtime.memory_status.status}:{runtime.memory_status.transcript_turn_count}t "
        f"body={runtime.body_status or runtime.body_driver_mode.value} "
        f"fallback={'active' if runtime.fallback_state.active else 'clear'} "
        f"audio_mode={runtime.audio_mode.value} "
        f"voice={snapshot.voice_state.status.value} "
        f"presence={runtime.presence_runtime.state.value} "
        f"loop={runtime.audio_loop.state.value} "
        f"observer={runtime.scene_observer.state} "
        f"trigger={runtime.trigger_engine.last_decision.value} "
        f"initiative={runtime.initiative_engine.last_decision.value}"
    )
    print(
        "devices "
        + " ".join(
            f"{item.kind.value}={item.state.value}"
            for item in runtime.device_health
        )
    )
    print(
        "frontends "
        f"terminal={runtime.terminal_frontend_state}:{runtime.terminal_frontend_detail or '-'} "
        f"console={runtime.console_launch_state or '-'}:{runtime.console_url or '-'} "
        f"native_mic={runtime.selected_microphone_label or '-'} "
        f"native_camera={runtime.selected_camera_label or '-'}"
    )
    body_line = _format_body_line(snapshot)
    if body_line is not None:
        print(body_line)
    ollama_status = [
        item
        for item in runtime.backend_status
        if item.provider == "ollama"
    ]
    if ollama_status:
        print(
            "ollama "
            + " ".join(
                f"{item.kind.value}={item.status.value}:{item.requested_model or item.model or '-'}"
                f":{'warm' if item.warm else 'cold'}"
                for item in ollama_status
            )
        )
    ollama_failures = [item for item in ollama_status if item.last_failure_reason]
    if ollama_failures:
        print(
            "ollama_failures "
            + " ".join(
                f"{item.kind.value}={item.last_failure_reason}:timeout={item.last_timeout_seconds or '-'}"
                f":retry={'yes' if item.cold_start_retry_used else 'no'}"
                for item in ollama_failures
            )
        )
    print(
        "always_on "
        f"enabled={runtime.always_on_enabled} "
        f"supervisor={runtime.supervisor.state} "
        f"presence_message={runtime.presence_runtime.message or '-'} "
        f"observer_refresh={runtime.scene_observer.last_refresh_reason or '-'} "
        f"cooldown_until={runtime.trigger_engine.cooldown_until or '-'} "
        f"initiative_stage={runtime.initiative_engine.current_stage.value} "
        f"initiative_candidate={runtime.initiative_engine.last_candidate_kind or '-'} "
        f"initiative_suppressed={runtime.initiative_engine.suppression_reason or '-'} "
        f"initiative_cooldown={runtime.initiative_engine.cooldown_until or '-'} "
        f"scene_cache_age={runtime.scene_cache_age_seconds if runtime.scene_cache_age_seconds is not None else '-'} "
        f"open_reminders={runtime.open_reminder_count}"
    )
    relationship = runtime.memory_status.relationship_continuity
    if (
        relationship.known_user
        or relationship.open_follow_ups
        or relationship.tone_preferences
        or relationship.interaction_boundaries
    ):
        print(
            "relationship "
            f"user={relationship.display_name or runtime.memory_status.user_id or '-'} "
            f"returning={relationship.returning_user} "
            f"planning={relationship.planning_style or '-'} "
            f"tones={','.join(relationship.tone_preferences) or '-'} "
            f"bounds={','.join(relationship.interaction_boundaries) or '-'} "
            f"open_threads={len(relationship.open_follow_ups)}"
        )
    if runtime.partial_transcript_preview:
        print(f"partial={runtime.partial_transcript_preview}")
    if runtime.latest_live_turn_diagnostics is not None:
        diagnostics = runtime.latest_live_turn_diagnostics
        text_model_state = (
            "warm"
            if diagnostics.text_model_warm is True
            else "cold"
            if diagnostics.text_model_warm is False
            else "-"
        )
        print(
            "latency "
            f"stt={_format_latency_ms(diagnostics.stt_ms)} "
            f"reasoning={_format_latency_ms(diagnostics.reasoning_ms)} "
            f"tts_start={_format_latency_ms(diagnostics.tts_start_ms or diagnostics.tts_launch_ms)} "
            f"end_to_end={_format_latency_ms(diagnostics.end_to_end_turn_ms or diagnostics.total_ms)} "
            f"stt_backend={diagnostics.stt_backend or '-'} "
            f"reasoning_backend={diagnostics.reasoning_backend or '-'} "
            f"text_model={text_model_state} "
            f"cold_start_retry={'yes' if diagnostics.text_cold_start_retry_used else 'no'}"
        )
    if runtime.model_residency:
        print(
            "residency "
            + " ".join(
                f"{item.kind.value}={item.status}:{item.model or '-'}:{'resident' if item.resident else 'cold'}"
                for item in runtime.model_residency
            )
        )
    if runtime.fallback_state.notes:
        print(f"fallback_notes={'; '.join(runtime.fallback_state.notes[:4])}")
    if snapshot.latest_perception is not None:
        print(
            "latest_perception "
            f"status={snapshot.latest_perception.status.value} "
            f"limited_awareness={snapshot.latest_perception.limited_awareness} "
            f"summary={snapshot.latest_perception.scene_summary or '(none)'}"
        )


def _export_session_bundle(runtime, session_id: str) -> None:
    episode = runtime.export_session_episode(session_id)
    print(
        "episode_exported "
        f"session={session_id} "
        f"episode_id={episode.episode_id} "
        f"summary={episode.artifact_files.get('summary', episode.artifact_dir or '-')}"
    )


def _print_camera_result(perception_result) -> None:
    if hasattr(perception_result, "snapshot"):
        snapshot_result = perception_result.snapshot
        warmup_retry_used = False
        if snapshot_result.source_frame and snapshot_result.source_frame.metadata:
            warmup_retry_used = bool(snapshot_result.source_frame.metadata.get("camera_warmup_retry_used"))
        line = (
            f"camera success={perception_result.success} status={snapshot_result.status.value} "
            f"limited_awareness={snapshot_result.limited_awareness} "
            f"camera_warmup_retry_used={'true' if warmup_retry_used else 'false'} "
            f"summary={snapshot_result.scene_summary or '-'}"
        )
        snapshot_path = snapshot_result.source_frame.fixture_path if snapshot_result.source_frame else None
        if snapshot_path:
            line += f" path={snapshot_path}"
        print(line)
        return
    print(f"camera success={perception_result.success} frames={len(perception_result.snapshots)}")


def _drain_runtime_events(runtime) -> None:
    for item in runtime.drain_runtime_events():
        event_type = item.get("event_type") or "runtime_event"
        message = item.get("message") or "-"
        reply_text = item.get("reply_text")
        trace_id = item.get("trace_id") or "-"
        state = item.get("state")
        state_suffix = f" state={state}" if state else ""
        if reply_text:
            print(f"[event] {event_type}{state_suffix} message={message} reply={reply_text} trace_id={trace_id}")
        else:
            print(f"[event] {event_type}{state_suffix} message={message}")


def _run_with_runtime_feedback(runtime, func):
    result: dict[str, object] = {}
    error: dict[str, BaseException] = {}
    done = threading.Event()

    def runner() -> None:
        try:
            result["value"] = func()
        except BaseException as exc:  # pragma: no cover - exercised via caller behavior
            error["value"] = exc
        finally:
            done.set()

    thread = threading.Thread(target=runner, name="blink-cli-presence", daemon=True)
    thread.start()
    while not done.wait(0.08):
        _drain_runtime_events(runtime)
    thread.join(timeout=0.1)
    _drain_runtime_events(runtime)
    if "value" in error:
        raise error["value"]
    return result.get("value")


def run_shell(args: argparse.Namespace) -> int:
    response_mode = ResponseMode(args.response_mode)
    voice_mode = VoiceRuntimeMode(args.voice_mode) if args.voice_mode else None

    with build_desktop_runtime() as runtime:
        session = runtime.ensure_session(
            session_id=args.session_id,
            user_id=args.user_id,
            response_mode=response_mode,
        )
        summary = runtime.profile_summary()
        print("Blink-AI desktop-local shell")
        print(f"session={session.session_id} runtime_mode={summary['runtime_mode']} body_driver={summary['body_driver']}")
        print(
            "profile="
            f"{summary['profile_summary']} dialogue={summary['dialogue_backend']} "
            f"voice_profile={summary['voice_profile']} live_voice_mode={summary['live_voice_mode']} "
            f"perception={summary['perception_provider']}"
        )
        print(f"provider_status={summary['provider_status']} detail={summary['provider_detail']}")
        print("Commands: /help /status /export /fixture <name|path> /presence on|off [count] [engagement] /scene <note> /voice cancel /safe-idle [reason] /quit")

        try:
            while True:
                try:
                    raw = input(f"[{session.session_id}]> ").strip()
                except EOFError:
                    print()
                    break
                except KeyboardInterrupt:
                    print()
                    break

                if not raw:
                    continue
                if raw in {"/quit", "/exit"}:
                    break
                if raw == "/help":
                    print("Plain text sends a typed conversation turn.")
                    print("/status shows the current runtime and perception summary.")
                    print("/export writes a local episode bundle for this session.")
                    print("/fixture replays a perception fixture by name or path.")
                    print("/presence on|off [count] [engagement] publishes a manual presence snapshot.")
                    print("/scene <note> publishes a manual scene note.")
                    print("/voice cancel interrupts the current speech output path.")
                    print("/safe-idle [reason] forces the runtime into safe idle.")
                    continue
                if raw == "/status":
                    _print_snapshot_status(runtime.snapshot(session_id=session.session_id, voice_mode=voice_mode))
                    continue
                if raw == "/export":
                    _export_session_bundle(runtime, session.session_id)
                    continue
                if raw.startswith("/fixture "):
                    fixture = raw.split(" ", 1)[1].strip()
                    result = runtime.replay_fixture(fixture, session_id=session.session_id, user_id=args.user_id)
                    print(f"fixture success={result.success} message={result.message} frames={len(result.snapshots)}")
                    continue
                if raw.startswith("/presence "):
                    parts = raw.split()
                    state = parts[1].lower()
                    person_present = state in {"on", "true", "1", "yes"}
                    people_count = int(parts[2]) if len(parts) > 2 else (1 if person_present else 0)
                    engagement = parts[3] if len(parts) > 3 else None
                    result = runtime.submit_scene_observation(
                        session_id=session.session_id,
                        user_id=args.user_id,
                        person_present=person_present,
                        people_count=people_count,
                        engagement=engagement,
                        scene_note="Manual desktop presence cue.",
                    )
                    print(
                        f"presence success={result.success} status={result.snapshot.status.value} "
                        f"limited_awareness={result.snapshot.limited_awareness}"
                    )
                    continue
                if raw.startswith("/scene "):
                    note = raw.split(" ", 1)[1].strip()
                    result = runtime.submit_scene_observation(
                        session_id=session.session_id,
                        user_id=args.user_id,
                        scene_note=note,
                    )
                    print(
                        f"scene success={result.success} status={result.snapshot.status.value} "
                        f"summary={result.snapshot.scene_summary or note}"
                    )
                    continue
                if raw == "/voice cancel":
                    result = runtime.operator_console.cancel_voice(session_id=session.session_id, voice_mode=voice_mode)
                    print(f"voice_cancel status={result.state.status.value} message={result.state.message}")
                    continue
                if raw.startswith("/safe-idle"):
                    reason = raw.split(" ", 1)[1].strip() if " " in raw else "operator_override"
                    result = runtime.operator_console.force_safe_idle(session_id=session.session_id, reason=reason)
                    print(f"safe_idle outcome={result.outcome} reason={result.heartbeat.safe_idle_reason}")
                    continue

                interaction = runtime.submit_text(
                    raw,
                    session_id=session.session_id,
                    user_id=args.user_id,
                    response_mode=response_mode,
                    voice_mode=voice_mode,
                    speak_reply=not args.no_speak,
                )
                print(f"reply: {interaction.response.reply_text}")
                if interaction.response.commands:
                    print("commands:", ", ".join(command.command_type.value for command in interaction.response.commands))
                print(f"outcome={interaction.outcome} trace_id={interaction.response.trace_id}")
        finally:
            if not args.no_export:
                _export_session_bundle(runtime, session.session_id)
    return 0


def run_local_loop(args: argparse.Namespace) -> int:
    response_mode = ResponseMode(args.response_mode)
    voice_mode = VoiceRuntimeMode(args.voice_mode) if args.voice_mode else None

    with build_desktop_runtime() as runtime:
        session = runtime.ensure_session(
            session_id=args.session_id,
            user_id=args.user_id,
            response_mode=response_mode,
        )
        summary = runtime.profile_summary()
        snapshot = runtime.snapshot(session_id=session.session_id, voice_mode=voice_mode)
        print("Blink-AI native desktop-local loop")
        print(
            "profile="
            f"{summary['profile_summary']} runtime_mode={summary['runtime_mode']} "
            f"voice_profile={summary['voice_profile']} live_voice_mode={summary['live_voice_mode']} "
            f"perception={summary['perception_provider']} body_driver={summary['body_driver']}"
        )
        print(f"provider_status={summary['provider_status']} detail={summary['provider_detail']}")
        print(
            "devices "
            + " ".join(
                f"{item.kind.value}={item.state.value}"
                for item in snapshot.runtime.device_health
            )
        )
        print("Commands: Enter or /listen captures a native turn. /type <text> uses typed fallback. /camera captures only. /status /export /voice cancel /safe-idle [reason] /quit")

        try:
            while True:
                try:
                    raw = input(f"[{session.session_id}] native> ").strip()
                except EOFError:
                    print()
                    break
                except KeyboardInterrupt:
                    print()
                    break

                if raw in {"/quit", "/exit"}:
                    break
                if raw == _DISCARD_NOISE_SENTINEL:
                    print("ignored_terminal_control_sequence")
                    continue
                if raw == "/status":
                    _print_snapshot_status(runtime.snapshot(session_id=session.session_id, voice_mode=voice_mode))
                    continue
                if raw == "/export":
                    _export_session_bundle(runtime, session.session_id)
                    continue
                if raw.startswith("/type "):
                    interaction = runtime.submit_text(
                        raw.split(" ", 1)[1].strip(),
                        session_id=session.session_id,
                        user_id=args.user_id,
                        response_mode=response_mode,
                        voice_mode=voice_mode,
                        speak_reply=not args.no_speak,
                        source="desktop_local_cli",
                    )
                    print(f"reply: {interaction.response.reply_text}")
                    if interaction.response.commands:
                        print("commands:", ", ".join(command.command_type.value for command in interaction.response.commands))
                    print(f"outcome={interaction.outcome} trace_id={interaction.response.trace_id}")
                    continue
                if raw == "/camera":
                    try:
                        perception_result = runtime.capture_camera_observation(
                            session_id=session.session_id,
                            user_id=args.user_id,
                        )
                    except Exception as exc:
                        print(f"camera_error={exc}")
                        continue
                    _print_camera_result(perception_result)
                    continue
                if raw == "/voice cancel":
                    result = runtime.operator_console.cancel_voice(session_id=session.session_id, voice_mode=voice_mode)
                    print(f"voice_cancel status={result.state.status.value} message={result.state.message}")
                    continue
                if raw.startswith("/safe-idle"):
                    reason = raw.split(" ", 1)[1].strip() if " " in raw else "operator_override"
                    result = runtime.operator_console.force_safe_idle(session_id=session.session_id, reason=reason)
                    print(f"safe_idle outcome={result.outcome} reason={result.heartbeat.safe_idle_reason}")
                    continue
                if raw and raw != "/listen":
                    print("Unknown command. Use /listen for native capture, /type <text> for typed fallback, or /quit.")
                    continue

                try:
                    result = runtime.submit_live_turn(
                        session_id=session.session_id,
                        user_id=args.user_id,
                        response_mode=response_mode,
                        voice_mode=voice_mode,
                        speak_reply=not args.no_speak,
                        capture_camera=not args.no_camera,
                    )
                except Exception as exc:
                    print(f"voice_error={exc}")
                    continue
                if result.perception_result is not None:
                    _print_camera_result(result.perception_result)
                if result.camera_error:
                    print(f"camera_error={result.camera_error}")
                print(f"heard: {result.interaction.voice_output.transcript_text or '(none)'}")
                print(f"reply: {result.interaction.response.reply_text}")
                if result.interaction.response.commands:
                    print("commands:", ", ".join(command.command_type.value for command in result.interaction.response.commands))
                print(f"outcome={result.interaction.outcome} trace_id={result.interaction.response.trace_id}")
        finally:
            if not args.no_export:
                _export_session_bundle(runtime, session.session_id)
    return 0


def run_companion(args: argparse.Namespace) -> int:
    response_mode = ResponseMode(args.response_mode)
    requested_voice_mode = VoiceRuntimeMode(args.voice_mode) if args.voice_mode else None
    settings = get_settings().model_copy(deep=True)
    settings.blink_always_on_enabled = True
    if args.audio_mode:
        settings.blink_audio_mode = args.audio_mode
    if args.context_mode:
        settings.blink_context_mode = CompanionContextMode(args.context_mode)
    if args.no_camera:
        settings.blink_camera_source = "disabled"

    with build_desktop_runtime(settings=settings) as runtime:
        if args.session_id:
            runtime.shift_runner.set_active_session(args.session_id)
        terminal_enabled, terminal_state, terminal_detail = _resolve_terminal_frontend_state(args.terminal_ui)
        runtime.operator_console.terminal_frontend_state = terminal_state
        runtime.operator_console.terminal_frontend_detail = terminal_detail

        session = runtime.ensure_session(
            session_id=args.session_id,
            user_id=args.user_id,
            response_mode=response_mode,
        )
        voice_mode = requested_voice_mode or runtime.default_voice_mode()
        if settings.blink_audio_mode == CompanionAudioMode.OPEN_MIC.value and requested_voice_mode is None:
            voice_mode = VoiceRuntimeMode.OPEN_MIC_LOCAL
        runtime.configure_companion_loop(
            session_id=session.session_id,
            voice_mode=voice_mode,
            speak_enabled=not args.no_speak,
            audio_mode=settings.blink_audio_mode,
        )

        prompt_session = _build_prompt_session() if terminal_enabled else None
        open_console = bool(args.open_console)
        console_host = None
        runtime.operator_console.console_launch_state = "opt_in"
        runtime.operator_console.console_url = None
        console_port = args.console_port or runtime.settings.brain_port
        if _should_start_console_host(terminal_enabled=terminal_enabled, open_console=open_console):
            try:
                console_host = _CompanionConsoleHost(runtime.app, port=console_port)
                console_host.start()
                runtime.operator_console.console_url = console_host.console_url
                runtime.operator_console.console_launch_state = _launch_console(
                    console_host.console_url,
                    open_console=open_console,
                )
            except Exception as exc:
                runtime.operator_console.console_launch_state = "failed"
                runtime.operator_console.console_url = None
                print(f"console_error={exc}")
                if not terminal_enabled:
                    return 1

        summary = runtime.profile_summary()
        snapshot = runtime.snapshot(session_id=session.session_id, voice_mode=voice_mode)
        print("Blink-AI local companion")
        print(
            "profile="
            f"{summary['profile_summary']} runtime_mode={summary['runtime_mode']} "
            f"voice_profile={summary['voice_profile']} live_voice_mode={voice_mode.value} "
            f"perception={summary['perception_provider']} body_driver={summary['body_driver']} "
            f"context={settings.blink_context_mode.value}"
        )
        print(f"provider_status={summary['provider_status']} detail={summary['provider_detail']}")
        _print_companion_startup_summary(snapshot, console_opt_in=open_console)
        _print_action_center_follow_up(runtime, session_id=session.session_id)
        if terminal_enabled:
            print(
                "Commands: plain text sends a turn. /listen captures one push-to-talk voice turn. "
                "/help /silence [minutes|off] /open-mic on|off /presence /camera /interrupt /status /console /actions ... /export /quit"
            )
        else:
            print(
                "Terminal frontend unavailable. "
                f"Use the browser console at {snapshot.runtime.console_url or 'the printed /console URL'} "
                f"or the character shell at {(_build_presence_url(snapshot.runtime.console_url, session_id=session.session_id) if snapshot.runtime.console_url else 'use /presence after the host starts')} "
                "and press Ctrl-C here to stop the host."
            )

        try:
            while True:
                _drain_runtime_events(runtime)

                if not terminal_enabled:
                    time.sleep(0.35)
                    continue

                try:
                    raw = _prompt_terminal_command(prompt_session)
                except KeyboardInterrupt:
                    print()
                    break
                except EOFError:
                    terminal_enabled = False
                    runtime.operator_console.terminal_frontend_state = "disabled"
                    runtime.operator_console.terminal_frontend_detail = "stdin_eof"
                    print(
                        "terminal_frontend_disabled "
                        f"use_browser_console={runtime.operator_console.console_url or '-'} "
                        "press_ctrl_c_to_stop"
                    )
                    if runtime.operator_console.console_url is None:
                        break
                    continue

                if raw in {"/quit", "/exit"}:
                    break
                if raw == "/help":
                    _print_companion_help(console_started=console_host is not None)
                    continue
                if _handle_companion_actions_command(
                    raw,
                    runtime=runtime,
                    session_id=session.session_id,
                ):
                    continue
                if raw in {"/presence", "/presence open", "/presence url"}:
                    try:
                        console_host = _ensure_companion_console_host(
                            runtime=runtime,
                            console_host=console_host,
                            port=console_port,
                        )
                        presence_url = console_host.presence_url_for(session_id=session.session_id)
                        launch_state = "available"
                        if raw != "/presence url":
                            launch_state = _launch_console(presence_url, open_console=True)
                        print(
                            "presence "
                            f"url={presence_url} "
                            f"launch={launch_state} "
                            "role=optional_character_surface"
                        )
                    except Exception as exc:
                        print(f"presence_error={exc}")
                    continue
                if raw in {"/console", "/console open", "/console url"}:
                    try:
                        console_host = _ensure_companion_console_host(
                            runtime=runtime,
                            console_host=console_host,
                            port=console_port,
                        )
                        launch_state = runtime.operator_console.console_launch_state or "available"
                        if raw != "/console url":
                            launch_state = _launch_console(console_host.console_url, open_console=True)
                            runtime.operator_console.console_launch_state = launch_state
                        print(
                            "console "
                            f"url={console_host.console_url} "
                            f"launch={launch_state} "
                            "role=secondary_operator_surface"
                        )
                    except Exception as exc:
                        runtime.operator_console.console_launch_state = "failed"
                        runtime.operator_console.console_url = None
                        print(f"console_error={exc}")
                    continue
                if raw == "/status":
                    _print_snapshot_status(runtime.snapshot(session_id=session.session_id, voice_mode=voice_mode))
                    _print_action_center_follow_up(runtime, session_id=session.session_id)
                    _print_companion_status_follow_up(console_started=console_host is not None)
                    continue
                if raw == "/silence":
                    status = runtime.silence_initiative(minutes=15.0)
                    if status is None:
                        print("initiative_silence_unavailable")
                    else:
                        print(f"initiative silence=on until={status.cooldown_until or '-'} reason={status.suppression_reason or '-'}")
                    continue
                if raw.startswith("/silence "):
                    value = raw.split(" ", 1)[1].strip().lower()
                    if value in {"off", "clear"}:
                        status = runtime.clear_initiative_silence()
                        if status is None:
                            print("initiative_silence_unavailable")
                        else:
                            print("initiative silence=off")
                        continue
                    try:
                        minutes = float(value)
                    except ValueError:
                        print("usage=/silence [minutes|off]")
                        continue
                    status = runtime.silence_initiative(minutes=max(0.0, minutes))
                    if status is None:
                        print("initiative_silence_unavailable")
                    else:
                        print(f"initiative silence=on until={status.cooldown_until or '-'} reason={status.suppression_reason or '-'}")
                    continue
                if raw == "/export":
                    _export_session_bundle(runtime, session.session_id)
                    continue
                if raw == "/camera":
                    try:
                        perception_result = runtime.capture_camera_observation(
                            session_id=session.session_id,
                            user_id=args.user_id,
                        )
                    except Exception as exc:
                        print(f"camera_error={exc}")
                        continue
                    _print_camera_result(perception_result)
                    continue
                if raw == "/interrupt":
                    result = runtime.interrupt_voice(session_id=session.session_id, voice_mode=voice_mode)
                    print(f"interrupt status={result.state.status.value} message={result.state.message}")
                    continue
                if raw == "/open-mic on":
                    voice_mode = VoiceRuntimeMode.OPEN_MIC_LOCAL
                    runtime.configure_companion_loop(
                        session_id=session.session_id,
                        voice_mode=voice_mode,
                        speak_enabled=not args.no_speak,
                        audio_mode=CompanionAudioMode.OPEN_MIC,
                    )
                    print("open_mic enabled")
                    continue
                if raw == "/open-mic off":
                    voice_mode = requested_voice_mode or VoiceRuntimeMode.DESKTOP_NATIVE
                    runtime.configure_companion_loop(
                        session_id=session.session_id,
                        voice_mode=voice_mode,
                        speak_enabled=not args.no_speak,
                        audio_mode=CompanionAudioMode.PUSH_TO_TALK,
                    )
                    print("open_mic disabled")
                    continue

                if raw.startswith("/type "):
                    text = raw.split(" ", 1)[1].strip()
                elif raw not in {"", "/listen"}:
                    text = raw
                else:
                    text = None

                if text is not None:
                    interaction = _run_with_runtime_feedback(
                        runtime,
                        lambda: runtime.submit_text(
                            text,
                            session_id=session.session_id,
                            user_id=args.user_id,
                            response_mode=response_mode,
                            voice_mode=voice_mode,
                            speak_reply=not args.no_speak,
                            source="local_companion_typed",
                        ),
                    )
                    print(f"reply: {interaction.response.reply_text}")
                    if interaction.response.commands:
                        print("commands:", ", ".join(command.command_type.value for command in interaction.response.commands))
                    print(f"outcome={interaction.outcome} trace_id={interaction.response.trace_id}")
                    _print_action_center_follow_up(runtime, session_id=session.session_id)
                    continue

                if raw == "":
                    continue

                if voice_mode == VoiceRuntimeMode.OPEN_MIC_LOCAL:
                    print("open_mic active; speak naturally or type /type <text>. Use /open-mic off for push-to-talk capture.")
                    continue

                try:
                    print("listening...")
                    result = _run_with_runtime_feedback(
                        runtime,
                        lambda: runtime.submit_live_turn(
                            session_id=session.session_id,
                            user_id=args.user_id,
                            response_mode=response_mode,
                            voice_mode=voice_mode,
                            speak_reply=not args.no_speak,
                            capture_camera=False,
                            source="local_companion_listen",
                        ),
                    )
                except Exception as exc:
                    print(f"voice_error={exc}")
                    continue
                print(f"heard: {result.interaction.voice_output.transcript_text or '(none)'}")
                print(f"reply: {result.interaction.response.reply_text}")
                if result.interaction.response.commands:
                    print("commands:", ", ".join(command.command_type.value for command in result.interaction.response.commands))
                print(f"outcome={result.interaction.outcome} trace_id={result.interaction.response.trace_id}")
                _print_action_center_follow_up(runtime, session_id=session.session_id)
        except KeyboardInterrupt:
            print()
        finally:
            if console_host is not None:
                console_host.stop()
            if not args.no_export:
                _export_session_bundle(runtime, session.session_id)
    return 0


def run_reset(args: argparse.Namespace) -> int:
    with build_desktop_runtime() as runtime:
        result = runtime.reset_demo(
            reset_edge=not args.no_edge_reset,
            clear_user_memory=not args.keep_memory,
            clear_demo_runs=not args.keep_demo_runs,
        )
    print(
        "reset "
        f"brain={result.brain_reset} edge={result.edge_reset} "
        f"cleared_demo_runs={result.cleared_demo_runs} notes={','.join(result.notes) or '-'}"
    )
    return 0


def run_scene_command(args: argparse.Namespace) -> int:
    response_mode = ResponseMode(args.response_mode)
    voice_mode = VoiceRuntimeMode(args.voice_mode) if args.voice_mode else VoiceRuntimeMode.STUB_DEMO

    settings = get_settings().model_copy(deep=True)
    settings.blink_context_mode = CompanionContextMode.VENUE_DEMO
    with build_desktop_runtime(settings=settings) as runtime:
        if args.reset_first:
            runtime.reset_demo()
        result = runtime.run_scene(
            args.scene_name,
            session_id=args.session_id,
            response_mode=response_mode,
            voice_mode=voice_mode,
            speak_reply=not args.no_speak,
        )

    print(f"scene={result.scene_name} success={result.success} session={result.session_id}")
    print(f"title={result.title}")
    print(f"note={result.note or '-'}")
    if result.final_action is not None:
        print(f"reply={result.final_action.reply_text or '-'}")
        print(f"commands={','.join(command.value for command in result.final_action.command_types) or '-'}")
    return 0


def run_story_command(args: argparse.Namespace) -> int:
    response_mode = ResponseMode(args.response_mode)
    voice_mode = VoiceRuntimeMode(args.voice_mode) if args.voice_mode else VoiceRuntimeMode.STUB_DEMO

    settings = get_settings().model_copy(deep=True)
    settings.blink_context_mode = CompanionContextMode.VENUE_DEMO
    with build_desktop_runtime(settings=settings) as runtime:
        results = runtime.run_story(
            args.story_name,
            session_id=args.session_id,
            response_mode=response_mode,
            voice_mode=voice_mode,
            speak_reply=not args.no_speak,
            reset_first=not args.no_reset,
        )

    for item in results:
        print(
            f"{item.scene_name} success={item.success} "
            f"note={item.note or '-'} "
            f"reply={(item.final_action.reply_text if item.final_action else '-') or '-'}"
        )
    if not args.no_export:
        exported_sessions: list[str] = []
        seen: set[str] = set()
        with build_desktop_runtime(settings=settings) as runtime:
            for item in results:
                if item.session_id in seen:
                    continue
                seen.add(item.session_id)
                exported_sessions.append(item.session_id)
                _export_session_bundle(runtime, item.session_id)
    print(f"story={args.story_name} scenes={len(results)}")
    return 0


def _performance_settings(*, show_name: str | None = None):
    settings = get_settings().model_copy(deep=True)
    settings.blink_context_mode = CompanionContextMode.VENUE_DEMO
    tuning_path = SHOW_TUNING_PATHS.get(show_name or _PERFORMANCE_DEFAULT_SHOW_NAME)
    if tuning_path is not None and tuning_path.exists():
        settings.blink_body_semantic_tuning_path = str(tuning_path)
    return settings


def _performance_total_duration_seconds(definition) -> int:
    return sum(segment.target_duration_seconds for segment in definition.segments)


def _performance_localized_text(cue, language: str | None) -> str | None:
    normalized = (language or "").strip().lower()
    if normalized and cue.localized_text:
        if normalized in cue.localized_text:
            return cue.localized_text[normalized]
        if "-" in normalized:
            base = normalized.split("-", 1)[0]
            if base in cue.localized_text:
                return cue.localized_text[base]
        elif normalized == "zh" and "zh-cn" in cue.localized_text:
            return cue.localized_text["zh-cn"]
    return cue.text


def _performance_coverage_summary(coverage) -> str:
    if coverage is None:
        return "-"
    active = [
        name
        for name in (
            "head_yaw",
            "head_pitch_pair",
            "eye_yaw",
            "eye_pitch",
            "upper_lids",
            "lower_lids",
            "brows",
        )
        if bool(getattr(coverage, name, False))
    ]
    return ",".join(active) if active else "-"


def run_performance_catalog_command(args: argparse.Namespace) -> int:
    with build_desktop_runtime(settings=_performance_settings()) as runtime:
        response = runtime.operator_console.list_performance_shows()
    if args.json:
        print(json.dumps(response.model_dump(mode="json"), indent=2, default=_json_default))
        return 0
    for item in response.items:
        print(
            f"{item.show_name} version={item.version} session={item.session_id} "
            f"segments={len(item.segments)} duration_seconds={_performance_total_duration_seconds(item)}"
        )
        print(f"title={item.title}")
    print(f"active_run_id={response.active_run_id or '-'}")
    print(f"latest_run_id={response.latest_run_id or '-'}")
    return 0


def run_performance_dry_run_command(args: argparse.Namespace) -> int:
    try:
        definition = load_show_definition(args.show_name)
        request = PerformanceRunRequest(
            segment_ids=list(args.segment_ids),
            cue_ids=list(args.cue_ids),
            proof_backend_mode=args.proof_backend_mode,
            language=args.language,
            narration_voice_preset=args.narration_voice_preset,
            narration_voice_name=args.narration_voice_name,
            narration_voice_rate=args.narration_voice_rate,
            narration_only=bool(args.narration_only),
            proof_only=bool(args.proof_only),
            background=False,
        )
        definition = select_show_definition(definition, request)
    except KeyError:
        print(f"performance_show_not_found={args.show_name}")
        return 1
    except (RuntimeError, ValueError) as exc:
        print(f"performance_show_error={exc}")
        return 1

    print(
        f"show={definition.show_name} version={definition.version} session={definition.session_id} "
        f"segments={len(definition.segments)} total_duration_seconds={_performance_total_duration_seconds(definition)}"
    )
    print(
        f"defaults response_mode={definition.defaults.response_mode.value} "
        f"proof_backend_mode={(request.proof_backend_mode or definition.defaults.proof_backend_mode).value if hasattr((request.proof_backend_mode or definition.defaults.proof_backend_mode), 'value') else (request.proof_backend_mode or definition.defaults.proof_backend_mode)} "
        f"proof_voice_mode={definition.defaults.proof_voice_mode.value} "
        f"narration_voice_mode={definition.defaults.narration_voice_mode.value} "
        f"language={request.language or definition.defaults.language} "
        f"voice_preset={request.narration_voice_preset or definition.defaults.narration_voice_preset or '-'} "
        f"voice_name={request.narration_voice_name or definition.defaults.narration_voice_name or '-'} "
        f"voice_rate={request.narration_voice_rate or definition.defaults.narration_voice_rate or '-'} "
        f"continue_on_error={definition.defaults.continue_on_error}"
    )
    print(
        f"selection segments={','.join(args.segment_ids) or '-'} "
        f"cues={','.join(args.cue_ids) or '-'} "
        f"narration_only={bool(args.narration_only)} proof_only={bool(args.proof_only)}"
    )
    for segment in definition.segments:
        print(
            f"segment={segment.segment_id} start={segment.target_start_seconds}s duration={segment.target_duration_seconds}s "
            f"title={segment.title} claim={segment.investor_claim}"
        )
        for cue in segment.cues:
            cue_parts = [
                f"cue={cue.cue_id}",
                f"kind={cue.cue_kind.value}",
                f"label={cue.label or '-'}",
            ]
            if cue.scene_name:
                cue_parts.append(f"scene={cue.scene_name}")
            text = _performance_localized_text(cue, request.language)
            if text:
                cue_parts.append(f"text={text}")
            if cue.action:
                cue_parts.append(f"action={cue.action}")
            if cue.event_type:
                cue_parts.append(f"event={cue.event_type}")
            if cue.fixture_path:
                cue_parts.append(f"fixture={cue.fixture_path}")
            if cue.motion_track:
                cue_parts.append(
                    "motion_track="
                    + ",".join(
                        f"{item.offset_ms}:{item.action}:{item.intensity if item.intensity is not None else '-'}"
                        for item in cue.motion_track
                    )
                )
            if cue.expect_reply_contains:
                cue_parts.append(f"expect_reply_contains={','.join(cue.expect_reply_contains)}")
            if cue.expect_user_memory_facts:
                cue_parts.append(
                    "expect_user_memory_facts="
                    + ",".join(f"{key}:{value}" for key, value in cue.expect_user_memory_facts.items())
                )
            if cue.expect_user_memory_preferences:
                cue_parts.append(
                    "expect_user_memory_preferences="
                    + ",".join(f"{key}:{value}" for key, value in cue.expect_user_memory_preferences.items())
                )
            print("  " + " ".join(cue_parts))
    return 0


def run_performance_show_command(args: argparse.Namespace) -> int:
    if args.background:
        print("performance_show_error=background_mode_requires_long_running_blink_appliance")
        return 1

    request = PerformanceRunRequest(
        session_id=args.session_id,
        segment_ids=list(args.segment_ids),
        cue_ids=list(args.cue_ids),
        response_mode=ResponseMode(args.response_mode) if args.response_mode else None,
        proof_backend_mode=args.proof_backend_mode,
        proof_voice_mode=VoiceRuntimeMode(args.proof_voice_mode) if args.proof_voice_mode else None,
        narration_voice_mode=(
            VoiceRuntimeMode(args.narration_voice_mode)
            if args.narration_voice_mode
            else None
        ),
        language=args.language,
        narration_voice_preset=args.narration_voice_preset,
        narration_voice_name=args.narration_voice_name,
        narration_voice_rate=args.narration_voice_rate,
        background=False,
        narration_enabled=not args.no_narration,
        narration_only=bool(args.narration_only),
        proof_only=bool(args.proof_only),
        force_degraded_cue_ids=list(args.force_degraded_cue_ids),
        reset_runtime=bool(args.reset_runtime),
    )

    try:
        with build_desktop_runtime(settings=_performance_settings(show_name=args.show_name)) as runtime:
            result = runtime.operator_console.run_performance_show(args.show_name, request)
    except KeyError:
        print(f"performance_show_not_found={args.show_name}")
        return 1
    except RuntimeError as exc:
        print(f"performance_show_error={exc}")
        return 1

    print(
        f"performance_show run_id={result.run_id} status={result.status.value} show={result.show_name} "
        f"session={result.session_id} degraded={result.degraded}"
    )
    print(
        f"proof_backend_mode={result.proof_backend_mode.value if result.proof_backend_mode is not None else '-'} "
        f"language={result.language} "
        f"voice_preset={result.narration_voice_preset or '-'} "
        f"voice_name={result.narration_voice_name or '-'} "
        f"voice_rate={result.narration_voice_rate or '-'} "
        f"tuning_path={result.selected_show_tuning_path or '-'}"
    )
    print(
        f"selection segments={','.join(result.selected_segment_ids) or '-'} "
        f"cues={','.join(result.selected_cue_ids) or '-'} "
        f"narration_only={result.narration_only} proof_only={result.proof_only}"
    )
    print(
        f"proof_checks={result.proof_check_count} "
        f"failed_checks={result.failed_proof_check_count} "
        f"degraded_cues={len(result.degraded_cues)} "
        f"elapsed_seconds={result.elapsed_seconds} "
        f"timing_drift_seconds={result.timing_drift_seconds if result.timing_drift_seconds is not None else '-'}"
    )
    if result.timing_breakdown_ms:
        print(
            "timing_breakdown_ms="
            + ",".join(f"{key}:{value}" for key, value in sorted(result.timing_breakdown_ms.items()))
        )
    print(
        f"motion_outcome={result.last_motion_outcome.value if result.last_motion_outcome is not None else '-'} "
        f"coverage={_performance_coverage_summary(result.actuator_coverage)} "
        f"worst_actuator_group={result.worst_actuator_group or '-'} "
        f"eye_pitch_exercised_live={result.eye_pitch_exercised_live}"
    )
    if result.last_motion_margin_record is not None:
        print(
            f"motion_margin safety_gate_passed={result.last_motion_margin_record.safety_gate_passed} "
            f"min_margin_percent={result.last_motion_margin_record.min_remaining_margin_percent if result.last_motion_margin_record.min_remaining_margin_percent is not None else '-'} "
            f"reason_code={result.last_motion_margin_record.reason_code or '-'} "
            f"health_flags={','.join(result.last_motion_margin_record.health_flags) or '-'}"
        )
    if result.min_margin_percent_by_group:
        print(
            "motion_margin_by_group "
            f"min={','.join(f'{key}:{value}' for key, value in sorted(result.min_margin_percent_by_group.items()))} "
            f"max={','.join(f'{key}:{value}' for key, value in sorted(result.max_margin_percent_by_group.items())) or '-'}"
        )
    if result.degraded_due_to_margin_only_cues:
        print(f"margin_only_degraded_cues={','.join(result.degraded_due_to_margin_only_cues)}")
    if result.live_motion_arm_author or result.live_motion_arm_port:
        print(
            f"live_motion_arm author={result.live_motion_arm_author or '-'} "
            f"port={result.live_motion_arm_port or '-'}"
        )
    for segment in result.segment_results:
        print(
            f"{segment.segment_id} status={segment.status} degraded={segment.degraded} "
            f"cues={len(segment.cue_results)} "
            f"proof_checks={segment.proof_check_count} "
            f"failed_checks={segment.failed_proof_check_count} "
            f"timing_drift_ms={segment.timing_drift_ms if segment.timing_drift_ms is not None else '-'}"
        )
        for cue in segment.cue_results:
            if cue.degraded or cue.cue_kind.value in {"prompt", "narrate"}:
                print(
                    f"  cue={cue.cue_id} kind={cue.cue_kind.value} status={cue.status} "
                    f"timing_drift_ms={cue.timing_drift_ms if cue.timing_drift_ms is not None else '-'} "
                    f"motion_outcome={(cue.motion_outcome.value if cue.motion_outcome is not None else '-')} "
                    f"coverage={_performance_coverage_summary(cue.actuator_coverage)} "
                    f"note={cue.note or '-'}"
                )
    if result.current_prompt:
        print(f"current_prompt={result.current_prompt}")
    if result.last_body_projection_outcome:
        print(f"body_projection_outcome={result.last_body_projection_outcome}")
    print(f"preview_only={result.preview_only}")
    if result.episode_id:
        print(f"episode_id={result.episode_id}")
    if result.artifact_dir:
        print(f"artifact_dir={result.artifact_dir}")
    return 0 if result.status.value == "completed" else 1


def run_performance_benchmark_command(args: argparse.Namespace) -> int:
    request = PerformanceRunRequest(
        session_id=f"{args.show_name}-benchmark",
        segment_ids=list(args.segment_ids),
        cue_ids=list(args.cue_ids),
        narration_voice_mode=(
            VoiceRuntimeMode(args.narration_voice_mode)
            if args.narration_voice_mode
            else None
        ),
        language=args.language,
        narration_voice_preset=args.narration_voice_preset,
        narration_voice_name=args.narration_voice_name,
        narration_voice_rate=args.narration_voice_rate,
        background=False,
        narration_only=True,
    )
    try:
        definition = load_show_definition(args.show_name)
        with build_desktop_runtime(settings=_performance_settings(show_name=args.show_name)) as runtime:
            result = benchmark_show_narration(
                operator_console=runtime.operator_console,
                definition=definition,
                request=request,
            )
    except KeyError:
        print(f"performance_show_not_found={args.show_name}")
        return 1
    except ValueError as exc:
        print(f"performance_show_error={exc}")
        return 1

    if args.json:
        print(json.dumps(result, indent=2, default=_json_default))
        return 0

    print(
        f"performance_benchmark show={result['show_name']} version={result['version']} session={result['session_id']}"
    )
    print(
        f"language={result['language']} voice_mode={result['voice_mode']} "
        f"voice_preset={result['voice_preset'] or '-'} voice_name={result['voice_name'] or '-'} "
        f"voice_rate={result['voice_rate'] or '-'}"
    )
    print(
        f"narration_target_ms={result['target_narration_ms']} "
        f"narration_actual_ms={result['actual_narration_ms']} "
        f"timing_drift_ms={result['timing_drift_ms']} "
        f"target_total_duration_seconds={result['target_total_duration_seconds']}"
    )
    for item in result["items"]:
        print(
            f"{item['cue_id']} status={item['voice_status']} "
            f"target_ms={item['target_duration_ms'] if item['target_duration_ms'] is not None else '-'} "
            f"actual_ms={item['actual_duration_ms']} "
            f"timing_drift_ms={item['timing_drift_ms'] if item['timing_drift_ms'] is not None else '-'}"
        )
    return 0


def run_doctor_command(args: argparse.Namespace) -> int:
    report = run_local_companion_doctor(write_path=args.write)
    print(f"doctor report={report['report_path']}")
    print(f"doctor_status={report.get('doctor_status') or '-'}")
    runtime = report.get("runtime", {})
    auth = report.get("auth", {})
    devices = report.get("devices", {})
    print(
        "runtime "
        f"context={runtime.get('context_mode') or '-'} "
        f"profile={runtime.get('profile_summary') or '-'} "
        f"text_backend={runtime.get('text_backend') or '-'} "
        f"stt_backend={runtime.get('stt_backend') or '-'}"
    )
    print(
        "auth "
        f"enabled={auth.get('enabled')} "
        f"source={auth.get('token_source') or '-'} "
        f"runtime_file={auth.get('runtime_file') or '-'}"
    )
    print(
        "devices "
        f"selected_mic={devices.get('selected_microphone_label') or '-'} "
        f"selected_camera={devices.get('selected_camera_label') or '-'} "
        f"speaker_note={devices.get('speaker_note') or '-'}"
    )
    for key in (
        "first_text_turn",
        "warm_text_turn",
        "product_behavior_probe",
        "embedding_probe",
        "visual_question",
        "memory_follow_up",
        "proactive_policy",
    ):
        item = runtime.get(key, {})
        print(f"{key} ok={item.get('ok')} detail={item.get('detail') or '-'}")
    issue_count = len(report.get("issues", []))
    print(f"issues={issue_count}")
    for action in report.get("next_actions", []):
        print(f"next_action={action}")
    return 0


def _json_default(value):
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _split_csv(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [item.strip() for item in raw.split(",") if item.strip()]


def run_connector_status_command(args: argparse.Namespace) -> int:
    with build_desktop_runtime() as runtime:
        response = runtime.operator_console.list_action_plane_connectors()
    if args.json:
        print(json.dumps(response.model_dump(mode="json"), indent=2, default=_json_default))
        return 0
    for item in response.items:
        print(
            f"{item.connector_id} supported={item.supported} configured={item.configured} "
            f"dry_run={item.dry_run_supported} actions={','.join(item.supported_actions) or '-'}"
        )
    return 0


def run_approval_list_command(args: argparse.Namespace) -> int:
    with build_desktop_runtime() as runtime:
        response = runtime.operator_console.list_action_plane_approvals()
    if args.json:
        print(json.dumps(response.model_dump(mode="json"), indent=2, default=_json_default))
        return 0
    for item in response.items:
        risk = getattr(getattr(item, "request", None), "risk_class", None)
        risk_value = getattr(risk, "value", risk) or "-"
        print(
            f"{item.action_id} tool={item.tool_name} action={item.action_name} "
            f"connector={item.connector_id} state={item.approval_state.value} "
            f"policy={getattr(item.policy_decision, 'value', item.policy_decision)} "
            f"risk={risk_value}"
        )
        if getattr(item, "detail", None):
            print(
                "why="
                + _describe_action_policy_reason(
                    detail=item.detail,
                    policy_decision=getattr(item, "policy_decision", None),
                    risk_class=risk,
                    connector_id=getattr(item, "connector_id", None),
                    action_name=getattr(item, "action_name", None) or getattr(item, "tool_name", None),
                )
            )
    return 0


def run_approval_resolve_command(args: argparse.Namespace, *, approve: bool) -> int:
    request = ActionApprovalResolutionRequest(action_id=args.action_id, operator_note=args.note)
    with build_desktop_runtime() as runtime:
        response = (
            runtime.operator_console.approve_action_plane_action(request)
            if approve
            else runtime.operator_console.reject_action_plane_action(request)
        )
    print(
        f"{response.action_id} approval={response.approval_state.value} "
        f"tool={response.tool_name} action={response.action_name} "
        f"execution={(response.execution.status.value if response.execution is not None else '-')}"
    )
    if response.execution is not None and getattr(response.execution, "operator_summary", None):
        print(f"operator_summary={response.execution.operator_summary}")
    if response.execution is not None and getattr(response.execution, "next_step_hint", None):
        print(f"next_step={response.execution.next_step_hint}")
    return 0


def run_action_history_command(args: argparse.Namespace) -> int:
    with build_desktop_runtime() as runtime:
        response = runtime.operator_console.list_action_plane_history(limit=args.limit)
    if args.json:
        print(json.dumps(response.model_dump(mode="json"), indent=2, default=_json_default))
        return 0
    for item in response.items:
        print(
            f"{item.action_id} tool={item.tool_name} action={item.action_name} "
            f"status={item.status.value} connector={item.connector_id}"
        )
        if getattr(item, "operator_summary", None):
            print(f"operator_summary={item.operator_summary}")
        if getattr(item, "next_step_hint", None):
            print(f"next_step={item.next_step_hint}")
    return 0


def run_replay_action_command(args: argparse.Namespace) -> int:
    request = ActionReplayRequestRecord(action_id=args.action_id, operator_note=args.note)
    with build_desktop_runtime() as runtime:
        execution = runtime.operator_console.replay_action_plane_action(request)
    print(
        f"{execution.action_id} tool={execution.tool_name} action={execution.action_name} "
        f"status={execution.status.value} connector={execution.connector_id}"
    )
    if getattr(execution, "operator_summary", None):
        print(f"operator_summary={execution.operator_summary}")
    if getattr(execution, "next_step_hint", None):
        print(f"next_step={execution.next_step_hint}")
    return 0


def run_action_bundle_list_command(args: argparse.Namespace) -> int:
    with build_desktop_runtime() as runtime:
        response = runtime.operator_console.list_action_plane_bundles(
            session_id=args.session_id,
            limit=args.limit,
        )
    if args.json:
        print(json.dumps(response.model_dump(mode="json"), indent=2, default=_json_default))
        return 0
    for item in response.items:
        print(
            f"{item.bundle_id} root={item.root_kind.value} "
            f"status={(item.final_status.value if hasattr(item.final_status, 'value') else item.final_status) or '-'} "
            f"tool={item.requested_tool_name or '-'} workflow={item.requested_workflow_id or '-'} "
            f"teacher={item.teacher_annotation_count} retries={item.retry_count}"
        )
    return 0


def run_action_bundle_show_command(args: argparse.Namespace) -> int:
    with build_desktop_runtime() as runtime:
        detail = runtime.operator_console.get_action_plane_bundle(args.bundle_id)
    if detail is None:
        print(f"bundle_not_found={args.bundle_id}")
        return 1
    if args.json:
        print(json.dumps(detail.model_dump(mode="json"), indent=2, default=_json_default))
        return 0
    manifest = detail.manifest
    print(
        f"{manifest.bundle_id} root={manifest.root_kind.value} "
        f"status={(manifest.final_status.value if hasattr(manifest.final_status, 'value') else manifest.final_status) or '-'} "
        f"tool={manifest.requested_tool_name or '-'} workflow={manifest.requested_workflow_id or '-'}"
    )
    print(
        f"approvals={len(detail.approval_events)} connector_calls={len(detail.connector_calls)} "
        f"retries={len(detail.retries)} teacher_annotations={len(detail.teacher_annotations)}"
    )
    if manifest.artifact_dir:
        print(f"artifact_dir={manifest.artifact_dir}")
    return 0


def run_action_bundle_teacher_review_command(args: argparse.Namespace) -> int:
    request = TeacherReviewRequest(
        review_value=args.review_value,
        label=args.label,
        note=args.note,
        author=args.author,
        action_feedback_labels=_split_csv(args.action_feedback_labels),
        benchmark_tags=_split_csv(args.benchmark_tags),
    )
    with build_desktop_runtime() as runtime:
        record = runtime.operator_console.add_action_plane_bundle_teacher_annotation(args.bundle_id, request)
    print(
        f"{record.annotation_id} scope={record.scope.value} scope_id={record.scope_id} "
        f"primary_kind={record.primary_kind.value}"
    )
    return 0


def run_replay_action_bundle_command(args: argparse.Namespace) -> int:
    request = ActionReplayRequestRecord(
        bundle_id=args.bundle_id,
        operator_note=args.note,
        approved_action_ids=list(args.approved_action_id or []),
    )
    with build_desktop_runtime() as runtime:
        record = runtime.operator_console.replay_action_plane_bundle(request)
    if args.json:
        print(json.dumps(record.model_dump(mode="json"), indent=2, default=_json_default))
        return 0
    print(
        f"{record.replay_id} bundle={record.bundle_id} status={record.status.value} "
        f"replayed={record.replayed_action_count} blocked={len(record.blocked_action_ids)}"
    )
    return 0


def run_workflow_list_command(args: argparse.Namespace) -> int:
    with build_desktop_runtime() as runtime:
        response = runtime.operator_console.list_action_plane_workflows()
    if args.json:
        print(json.dumps(response.model_dump(mode="json"), indent=2, default=_json_default))
        return 0
    for item in response.items:
        print(
            f"{item.workflow_id} label={item.label} version={item.version} "
            f"triggers={','.join(trigger.value for trigger in item.supported_triggers) or '-'}"
        )
    return 0


def run_workflow_runs_command(args: argparse.Namespace) -> int:
    with build_desktop_runtime() as runtime:
        response = runtime.operator_console.list_action_plane_workflow_runs(
            session_id=args.session_id,
            limit=args.limit,
        )
    if args.json:
        print(json.dumps(response.model_dump(mode="json"), indent=2, default=_json_default))
        return 0
    for item in response.items:
        print(
            f"{item.workflow_run_id} workflow={item.workflow_id} status={item.status.value} "
            f"step={item.current_step_label or '-'} trigger={item.trigger.trigger_kind.value}"
        )
        if getattr(item, "pause_reason", None) is not None:
            print(f"pause_reason={item.pause_reason.value}")
        if getattr(item, "detail", None):
            print(f"detail={item.detail}")
    return 0


def run_workflow_start_command(args: argparse.Namespace) -> int:
    request = WorkflowStartRequestRecord(
        workflow_id=args.workflow_id,
        session_id=args.session_id,
        inputs=json.loads(args.inputs or "{}"),
        note=args.note,
    )
    with build_desktop_runtime() as runtime:
        response = runtime.operator_console.start_action_plane_workflow(request)
    print(
        f"{response.workflow_run_id} workflow={response.workflow_id} status={response.status.value if response.status else '-'} "
        f"step={response.current_step_label or '-'} blocking_action={response.blocking_action_id or '-'}"
    )
    if getattr(response, "summary", None):
        print(f"summary={response.summary}")
    if getattr(response, "detail", None):
        print(f"detail={response.detail}")
    return 0


def run_workflow_resume_command(args: argparse.Namespace) -> int:
    request = WorkflowRunActionRequestRecord(note=args.note)
    with build_desktop_runtime() as runtime:
        response = runtime.operator_console.resume_action_plane_workflow(args.workflow_run_id, request)
    print(
        f"{response.workflow_run_id} status={response.status.value if response.status else '-'} "
        f"step={response.current_step_label or '-'} resumed={response.resumed}"
    )
    if getattr(response, "detail", None):
        print(f"detail={response.detail}")
    return 0


def run_workflow_retry_command(args: argparse.Namespace) -> int:
    request = WorkflowRunActionRequestRecord(note=args.note)
    with build_desktop_runtime() as runtime:
        response = runtime.operator_console.retry_action_plane_workflow(args.workflow_run_id, request)
    print(
        f"{response.workflow_run_id} status={response.status.value if response.status else '-'} "
        f"step={response.current_step_label or '-'} retried={response.retried}"
    )
    if getattr(response, "detail", None):
        print(f"detail={response.detail}")
    return 0


def run_workflow_pause_command(args: argparse.Namespace) -> int:
    request = WorkflowRunActionRequestRecord(note=args.note)
    with build_desktop_runtime() as runtime:
        response = runtime.operator_console.pause_action_plane_workflow(args.workflow_run_id, request)
    print(
        f"{response.workflow_run_id} status={response.status.value if response.status else '-'} "
        f"step={response.current_step_label or '-'} paused={response.paused}"
    )
    if getattr(response, "detail", None):
        print(f"detail={response.detail}")
    return 0


def run_token_command(_: argparse.Namespace) -> int:
    settings = get_settings()
    manager = OperatorAuthManager(settings)
    if not manager.enabled:
        print("operator_auth disabled")
        return 0
    print(f"operator_auth_token={manager.token}")
    print(f"token_source={manager.token_source}")
    print(f"runtime_file={manager.runtime_file}")
    return 0


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    command = args.command or "serve"

    if command == "serve":
        serve_main()
        return
    if command == "shell":
        raise SystemExit(run_shell(args))
    if command == "local-loop":
        raise SystemExit(run_local_loop(args))
    if command == "companion":
        raise SystemExit(run_companion(args))
    if command == "doctor":
        raise SystemExit(run_doctor_command(args))
    if command == "connector-status":
        raise SystemExit(run_connector_status_command(args))
    if command == "approval-list":
        raise SystemExit(run_approval_list_command(args))
    if command == "approval-approve":
        raise SystemExit(run_approval_resolve_command(args, approve=True))
    if command == "approval-reject":
        raise SystemExit(run_approval_resolve_command(args, approve=False))
    if command == "action-history":
        raise SystemExit(run_action_history_command(args))
    if command == "replay-action":
        raise SystemExit(run_replay_action_command(args))
    if command == "action-bundle-list":
        raise SystemExit(run_action_bundle_list_command(args))
    if command == "action-bundle-show":
        raise SystemExit(run_action_bundle_show_command(args))
    if command == "action-bundle-teacher-review":
        raise SystemExit(run_action_bundle_teacher_review_command(args))
    if command == "replay-action-bundle":
        raise SystemExit(run_replay_action_bundle_command(args))
    if command == "workflow-list":
        raise SystemExit(run_workflow_list_command(args))
    if command == "workflow-runs":
        raise SystemExit(run_workflow_runs_command(args))
    if command == "workflow-start":
        raise SystemExit(run_workflow_start_command(args))
    if command == "workflow-resume":
        raise SystemExit(run_workflow_resume_command(args))
    if command == "workflow-retry":
        raise SystemExit(run_workflow_retry_command(args))
    if command == "workflow-pause":
        raise SystemExit(run_workflow_pause_command(args))
    if command == "token":
        raise SystemExit(run_token_command(args))
    if command == "reset":
        raise SystemExit(run_reset(args))
    if command == "performance-catalog":
        raise SystemExit(run_performance_catalog_command(args))
    if command == "performance-dry-run":
        raise SystemExit(run_performance_dry_run_command(args))
    if command == "performance-show":
        raise SystemExit(run_performance_show_command(args))
    if command == "performance-benchmark":
        raise SystemExit(run_performance_benchmark_command(args))
    if command == "scene":
        raise SystemExit(run_scene_command(args))
    if command in {"story", "companion-story"}:
        raise SystemExit(run_story_command(args))
    parser.error(f"unknown_command:{command}")


def local_loop_main() -> None:
    parser = build_parser()
    args = parser.parse_args(["local-loop", *sys.argv[1:]])
    raise SystemExit(run_local_loop(args))


def companion_main() -> None:
    parser = build_parser()
    top_level_commands = {
        "serve",
        "shell",
        "local-loop",
        "companion",
        "doctor",
        "connector-status",
        "approval-list",
        "approval-approve",
        "approval-reject",
        "action-history",
        "replay-action",
        "action-bundle-list",
        "action-bundle-show",
        "action-bundle-teacher-review",
        "replay-action-bundle",
        "workflow-list",
        "workflow-runs",
        "workflow-start",
        "workflow-resume",
        "workflow-retry",
        "workflow-pause",
        "token",
        "reset",
        "scene",
        "story",
        "companion-story",
        "performance-catalog",
        "performance-dry-run",
        "performance-show",
        "performance-benchmark",
    }
    argv = list(sys.argv[1:])
    args = parser.parse_args(argv if argv and argv[0] in top_level_commands else ["companion", *argv])
    command = args.command or "companion"
    if command == "companion":
        raise SystemExit(run_companion(args))
    if command == "performance-catalog":
        raise SystemExit(run_performance_catalog_command(args))
    if command == "performance-dry-run":
        raise SystemExit(run_performance_dry_run_command(args))
    if command == "performance-show":
        raise SystemExit(run_performance_show_command(args))
    if command == "performance-benchmark":
        raise SystemExit(run_performance_benchmark_command(args))
    if command == "scene":
        raise SystemExit(run_scene_command(args))
    if command in {"story", "companion-story"}:
        raise SystemExit(run_story_command(args))
    if command == "doctor":
        raise SystemExit(run_doctor_command(args))
    if command == "token":
        raise SystemExit(run_token_command(args))
    main()


def companion_story_main() -> None:
    parser = build_parser()
    args = parser.parse_args(["companion-story", *sys.argv[1:]])
    raise SystemExit(run_story_command(args))


def doctor_main() -> None:
    parser = build_parser()
    args = parser.parse_args(["doctor", *sys.argv[1:]])
    raise SystemExit(run_doctor_command(args))


def token_main() -> None:
    parser = build_parser()
    args = parser.parse_args(["token", *sys.argv[1:]])
    raise SystemExit(run_token_command(args))


__all__ = [
    "build_parser",
    "companion_main",
    "companion_story_main",
    "doctor_main",
    "local_loop_main",
    "main",
    "run_performance_catalog_command",
    "run_performance_benchmark_command",
    "run_performance_dry_run_command",
    "run_performance_show_command",
    "run_companion",
    "run_doctor_command",
    "run_local_loop",
    "run_reset",
    "run_scene_command",
    "run_shell",
    "run_story_command",
    "run_token_command",
    "token_main",
]
