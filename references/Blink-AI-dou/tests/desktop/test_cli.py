from __future__ import annotations

from argparse import Namespace
from types import SimpleNamespace

import pytest

from embodied_stack.desktop import cli
from embodied_stack.shared.models import (
    CompanionContextMode,
    DemoRunStatus,
    PerformanceActuatorCoverageSummary,
    PerformanceCue,
    PerformanceCueKind,
    PerformanceCueResult,
    PerformanceMotionMarginRecord,
    PerformanceMotionOutcome,
    PerformanceRunResult,
    PerformanceSegment,
    PerformanceSegmentResult,
    PerformanceShowCatalogResponse,
    PerformanceShowDefinition,
    VoiceRuntimeMode,
    WorkflowPauseReason,
    WorkflowRunStatus,
)


class _FakeStoryRuntime:
    def __init__(self) -> None:
        self.story_voice_mode = None

    def run_story(
        self,
        story_name: str,
        *,
        session_id: str | None,
        response_mode,
        voice_mode,
        speak_reply: bool,
        reset_first: bool,
    ):
        del story_name, session_id, response_mode, speak_reply, reset_first
        self.story_voice_mode = voice_mode
        return [
            SimpleNamespace(
                scene_name="natural_discussion",
                success=True,
                note="ok",
                final_action=SimpleNamespace(reply_text="Hello there"),
                session_id="story-session",
            )
        ]


class _FakeRuntimeContext:
    def __init__(self, runtime: _FakeStoryRuntime) -> None:
        self.runtime = runtime

    def __enter__(self) -> _FakeStoryRuntime:
        return self.runtime

    def __exit__(self, exc_type, exc, tb) -> None:
        del exc_type, exc, tb


class _FakeActionPlaneOperatorConsole:
    def get_action_plane_overview(self, session_id=None):
        del session_id
        return SimpleNamespace(
            status=SimpleNamespace(
                pending_approval_count=1,
                waiting_workflow_count=1,
                review_required_count=1,
                degraded_connector_count=1,
                last_action_id="act_pending",
                last_action_status="pending_approval",
                connector_health=[
                    SimpleNamespace(connector_id="notes_local", status="healthy"),
                ],
            ),
            attention_items=[
                SimpleNamespace(
                    kind="approval",
                    severity="medium",
                    title="Approval required",
                    summary="Review the pending operator help request.",
                    action_id="act_pending",
                    workflow_run_id="wf_pending",
                    bundle_id="workflow_wf_pending",
                    session_id="workflow-session",
                    next_step_hint="Approve or reject act_pending from the interactive loop.",
                    detail_ref="act_pending",
                )
            ],
            approvals=self.list_action_plane_approvals().items,
            recent_history=self.list_action_plane_history().items,
            connectors=self.list_action_plane_connectors().items,
            active_workflows=self.list_action_plane_workflow_runs().items,
        )

    def list_action_plane_connectors(self):
        return SimpleNamespace(
            items=[
                SimpleNamespace(
                    connector_id="notes_local",
                    supported=True,
                    configured=True,
                    dry_run_supported=True,
                    supported_actions=["create_note", "append_note", "search_notes"],
                )
            ]
        )

    def list_action_plane_approvals(self):
        return SimpleNamespace(
            items=[
                SimpleNamespace(
                    action_id="act_pending",
                    tool_name="request_operator_help",
                    action_name="request_operator_help",
                    connector_id="incident_local",
                    policy_decision=SimpleNamespace(value="require_approval"),
                    approval_state=SimpleNamespace(value="pending"),
                    request=SimpleNamespace(risk_class=SimpleNamespace(value="operator_sensitive_write")),
                    detail="Approval required for operator help request.",
                )
            ]
        )

    def approve_action_plane_action(self, request):
        return SimpleNamespace(
            action_id=request.action_id,
            approval_state=SimpleNamespace(value="approved"),
            tool_name="request_operator_help",
            action_name="request_operator_help",
            execution=SimpleNamespace(
                status=SimpleNamespace(value="executed"),
                operator_summary="The operator help request has been approved and executed.",
                next_step_hint="Watch for the workflow to finish or export the resulting episode.",
            ),
        )

    def reject_action_plane_action(self, request):
        return SimpleNamespace(
            action_id=request.action_id,
            approval_state=SimpleNamespace(value="rejected"),
            tool_name="request_operator_help",
            action_name="request_operator_help",
            execution=SimpleNamespace(
                status=SimpleNamespace(value="rejected"),
                operator_summary="The pending request was rejected and will remain blocked until an explicit retry.",
                next_step_hint="Retry the blocked workflow if you want to resubmit the action.",
            ),
        )

    def list_action_plane_history(self, limit=25):
        del limit
        return SimpleNamespace(
            items=[
                SimpleNamespace(
                    action_id="act_history",
                    tool_name="create_note",
                    action_name="create_note",
                    status=SimpleNamespace(value="executed"),
                    connector_id="notes_local",
                    operator_summary="Created the requested note locally.",
                    next_step_hint="Inspect the linked action bundle if you need the full trace.",
                )
            ]
        )

    def replay_action_plane_action(self, request):
        return SimpleNamespace(
            action_id=f"replay_{request.action_id}",
            tool_name="create_note",
            action_name="create_note",
            status=SimpleNamespace(value="executed"),
            connector_id="notes_local",
            operator_summary="The deterministic replay completed successfully.",
            next_step_hint="Inspect the replay manifest for artifact paths.",
        )

    def list_action_plane_bundles(self, *, session_id=None, limit=25):
        del session_id, limit
        return SimpleNamespace(
            items=[
                SimpleNamespace(
                    bundle_id="workflow_wf_pending",
                    root_kind=SimpleNamespace(value="workflow_run"),
                    final_status=SimpleNamespace(value="completed"),
                    requested_tool_name=None,
                    requested_workflow_id="capture_note_and_reminder",
                    teacher_annotation_count=1,
                    retry_count=0,
                )
            ]
        )

    def get_action_plane_bundle(self, bundle_id):
        return SimpleNamespace(
            manifest=SimpleNamespace(
                bundle_id=bundle_id,
                root_kind=SimpleNamespace(value="workflow_run"),
                final_status=SimpleNamespace(value="completed"),
                requested_tool_name=None,
                requested_workflow_id="capture_note_and_reminder",
                artifact_dir="/tmp/action_bundle",
            ),
            approval_events=[],
            connector_calls=[SimpleNamespace(action_id="act_history"), SimpleNamespace(action_id="act_pending")],
            retries=[],
            replays=[SimpleNamespace(replay_id="action-replay-1")],
            teacher_annotations=[{"annotation_id": "ann-1"}],
        )

    def add_action_plane_bundle_teacher_annotation(self, bundle_id, request):
        return SimpleNamespace(
            annotation_id=f"ann-{bundle_id}",
            scope=SimpleNamespace(value="workflow_run"),
            scope_id=bundle_id,
            primary_kind=SimpleNamespace(value="action"),
            review_value=request.review_value,
        )

    def replay_action_plane_bundle(self, request):
        return SimpleNamespace(
            replay_id="action-replay-1",
            bundle_id=request.bundle_id,
            status=SimpleNamespace(value="completed"),
            replayed_action_count=2,
            blocked_action_ids=[],
        )

    def list_action_plane_workflows(self):
        return SimpleNamespace(
            items=[
                SimpleNamespace(
                    workflow_id="capture_note_and_reminder",
                    label="Capture Note And Reminder",
                    version="1.0",
                    supported_triggers=[SimpleNamespace(value="user_request"), SimpleNamespace(value="operator_launch")],
                )
            ]
        )

    def list_action_plane_workflow_runs(self, *, session_id=None, limit=25):
        del session_id, limit
        return SimpleNamespace(
            items=[
                SimpleNamespace(
                    workflow_run_id="wf_pending",
                    workflow_id="event_lookup_and_open_page",
                    status=WorkflowRunStatus.WAITING_FOR_APPROVAL,
                    current_step_label="Optional Browser Follow Up",
                    trigger=SimpleNamespace(trigger_kind=SimpleNamespace(value="user_request")),
                    pause_reason=WorkflowPauseReason.RUNTIME_RESTART_REVIEW,
                    detail="Workflow is waiting on restart review before it can continue.",
                )
            ]
        )

    def start_action_plane_workflow(self, request):
        return SimpleNamespace(
            workflow_run_id="wf_started",
            workflow_id=request.workflow_id,
            status=WorkflowRunStatus.COMPLETED,
            current_step_label=None,
            blocking_action_id=None,
        )

    def resume_action_plane_workflow(self, workflow_run_id, request):
        del request
        return SimpleNamespace(
            workflow_run_id=workflow_run_id,
            status=WorkflowRunStatus.WAITING_FOR_APPROVAL,
            current_step_label="Optional Browser Follow Up",
            resumed=True,
        )

    def retry_action_plane_workflow(self, workflow_run_id, request):
        del request
        return SimpleNamespace(
            workflow_run_id=workflow_run_id,
            status=WorkflowRunStatus.COMPLETED,
            current_step_label=None,
            retried=True,
        )

    def pause_action_plane_workflow(self, workflow_run_id, request):
        del request
        return SimpleNamespace(
            workflow_run_id=workflow_run_id,
            status=WorkflowRunStatus.PAUSED,
            current_step_label="Optional Browser Follow Up",
            paused=True,
            pause_reason=WorkflowPauseReason.OPERATOR_PAUSED,
        )


class _FakeActionPlaneRuntime:
    def __init__(self) -> None:
        self.operator_console = _FakeActionPlaneOperatorConsole()


class _FakePerformanceOperatorConsole:
    def __init__(self) -> None:
        self.last_request = None
        self.last_benchmark_request = None
        self.catalog = PerformanceShowCatalogResponse(
            items=[
                PerformanceShowDefinition(
                    show_name="investor_expressive_motion_v8",
                    title="Blink-AI Investor Expressive Motif Proof V8",
                    session_id="investor-expressive-motion-v8",
                    segments=[
                        PerformanceSegment(
                            segment_id="guarded_close_right",
                            title="Guarded close right",
                            investor_claim="The eyes stay closed while the brows frown and release.",
                            target_duration_seconds=18,
                        )
                    ],
                )
            ],
            active_run_id=None,
            latest_run_id="performance-abc123",
        )
        self.result = PerformanceRunResult(
            run_id="performance-abc123",
            status=DemoRunStatus.COMPLETED,
            show_name="investor_expressive_motion_v8",
            session_id="investor-expressive-motion-v8",
            proof_backend_mode="deterministic_show",
            language="en",
            narration_voice_preset="english_cute_character",
            narration_voice_name="Samantha",
            narration_voice_rate=185,
            degraded=False,
            last_motion_outcome=PerformanceMotionOutcome.LIVE_APPLIED,
            last_motion_margin_record=PerformanceMotionMarginRecord(
                action="look_far_left",
                outcome=PerformanceMotionOutcome.LIVE_APPLIED,
                min_remaining_margin_percent=14.2,
                safety_gate_passed=True,
            ),
            actuator_coverage=PerformanceActuatorCoverageSummary(
                head_yaw=True,
                eye_yaw=True,
                brows=True,
            ),
            timing_breakdown_ms={"narration": 1200.0, "proof": 340.0},
            selected_show_tuning_path="runtime/body/semantic_tuning/robot_head_investor_show_v8.json",
            segment_results=[
                PerformanceSegmentResult(
                    segment_id="guarded_close_right",
                    title="Guarded close right",
                    investor_claim="The eyes stay closed while the brows frown and release.",
                    status="completed",
                    cue_results=[
                        PerformanceCueResult(
                            cue_id="guarded_close_right_run",
                            cue_kind=PerformanceCueKind.BODY_EXPRESSIVE_MOTIF,
                            label="Guarded close right motif",
                            status="completed",
                            proof_checks=[],
                        )
                    ],
                )
            ],
            artifact_dir="/tmp/performance-abc123",
            artifact_files={"run_summary": "/tmp/performance-abc123/run_summary.json"},
            episode_id="episode-abc123",
        )

    def list_performance_shows(self):
        return self.catalog

    def run_performance_show(self, show_name, request):
        self.last_request = request
        assert show_name == "investor_expressive_motion_v8"
        return self.result

    def benchmark_performance_show(self, show_name, request):
        self.last_benchmark_request = request
        assert show_name == "investor_expressive_motion_v8"
        return {
            "show_name": show_name,
            "version": "v8",
            "session_id": "investor-expressive-motion-v8",
            "language": request.language or "en",
            "voice_mode": request.narration_voice_mode.value if request.narration_voice_mode is not None else "macos_say",
            "voice_preset": request.narration_voice_preset or "english_cute_character",
            "voice_name": request.narration_voice_name or "Samantha",
            "voice_rate": request.narration_voice_rate or 185,
            "target_total_duration_seconds": 216,
            "target_narration_ms": 0,
            "actual_narration_ms": 0.0,
            "timing_drift_ms": -200.0,
            "cue_count": 1,
            "items": [
                {
                    "cue_id": "guarded_close_right_run",
                    "voice_status": "completed",
                    "target_duration_ms": 0,
                    "actual_duration_ms": 0.0,
                    "timing_drift_ms": -300.0,
                }
            ],
        }


class _FakePerformanceRuntime:
    def __init__(self) -> None:
        self.operator_console = _FakePerformanceOperatorConsole()


def test_run_story_command_defaults_to_stub_demo_voice_mode(monkeypatch, capsys):
    runtime = _FakeStoryRuntime()
    seen = {}

    def _build_runtime(settings=None):
        seen["settings"] = settings
        return _FakeRuntimeContext(runtime)

    monkeypatch.setattr(cli, "build_desktop_runtime", _build_runtime)

    exit_code = cli.run_story_command(
        Namespace(
            story_name="local_companion_story",
            session_id=None,
            response_mode="guide",
            voice_mode=None,
            no_speak=True,
            no_reset=False,
            no_export=True,
        )
    )

    assert exit_code == 0
    assert runtime.story_voice_mode == VoiceRuntimeMode.STUB_DEMO
    assert seen["settings"].blink_context_mode == CompanionContextMode.VENUE_DEMO
    assert "story=local_companion_story scenes=1" in capsys.readouterr().out


def test_companion_parser_accepts_audio_mode_open_mic():
    parser = cli.build_parser()
    args = parser.parse_args(["companion", "--audio-mode", "open_mic"])

    assert args.command == "companion"
    assert args.audio_mode == "open_mic"


def test_companion_parser_accepts_context_mode():
    parser = cli.build_parser()
    args = parser.parse_args(["companion", "--context-mode", "venue_demo"])

    assert args.command == "companion"
    assert args.context_mode == "venue_demo"


def test_companion_parser_accepts_console_frontend_flags():
    parser = cli.build_parser()
    args = parser.parse_args(["companion", "--terminal-ui", "off", "--console-port", "8765", "--open-console"])

    assert args.command == "companion"
    assert args.terminal_ui == "off"
    assert args.console_port == 8765
    assert args.open_console is True


def test_companion_parser_help_mentions_terminal_first_guidance(capsys):
    parser = cli.build_parser()

    with pytest.raises(SystemExit):
        parser.parse_args(["companion", "--help"])

    output = capsys.readouterr().out
    assert "daily-use terminal-first companion" in output
    assert "/listen" in output
    assert "/presence" in output
    assert "/console" in output


def test_run_doctor_command_prints_report_path(monkeypatch, capsys):
    monkeypatch.setattr(
        cli,
        "run_local_companion_doctor",
        lambda write_path: {
            "report_path": str(write_path),
            "issues": [],
            "doctor_status": "certified",
            "next_actions": ["Safe to demo."],
            "auth": {"enabled": True, "token_source": "persisted_runtime", "runtime_file": "runtime/operator_auth.json"},
            "devices": {
                "selected_microphone_label": "LG UltraFine Display Audio",
                "selected_camera_label": "LG UltraFine Display Camera",
                "speaker_note": "macos_say follows the current macOS default output device.",
            },
            "runtime": {
                "context_mode": "personal_local",
                "profile_summary": "companion_live + virtual_body",
                "text_backend": "ollama_text",
                "stt_backend": "whisper_cpp_local",
                "first_text_turn": {"ok": True, "detail": "outcome=ok"},
                "warm_text_turn": {"ok": True, "detail": "outcome=ok"},
                "product_behavior_probe": {"ok": True, "detail": "personal_local_behavior_ok"},
                "embedding_probe": {"ok": True, "detail": "vector_dim=384"},
                "visual_question": {"ok": True, "detail": "capture=ok"},
                "memory_follow_up": {"ok": True, "detail": "open_reminders=1"},
                "proactive_policy": {"ok": True, "detail": "decision=speak_now"},
            },
        },
    )

    exit_code = cli.run_doctor_command(Namespace(write="runtime/diagnostics/test_report.md"))

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "doctor report=runtime/diagnostics/test_report.md" in output
    assert "doctor_status=certified" in output
    assert "product_behavior_probe ok=True detail=personal_local_behavior_ok" in output
    assert "next_action=Safe to demo." in output
    assert "issues=0" in output


def test_run_token_command_prints_persistent_token(tmp_path, monkeypatch, capsys):
    settings = cli.get_settings().model_copy(
        update={
            "operator_auth_token": "stable-terminal-token",
            "operator_auth_runtime_file": str(tmp_path / "operator_auth.json"),
        }
    )
    monkeypatch.setattr(cli, "get_settings", lambda: settings)

    exit_code = cli.run_token_command(Namespace())

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "operator_auth_token=stable-terminal-token" in output
    assert "token_source=env" in output


def test_normalize_companion_input_treats_carriage_return_as_blank_listen():
    assert cli._normalize_companion_input("\r") == ""
    assert cli._normalize_companion_input("^M") == ""
    assert cli._normalize_companion_input("^M/status^M") == "/status"


def test_normalize_companion_input_preserves_typed_text():
    assert cli._normalize_companion_input("  /type hello there \r\n") == "/type hello there"
    assert cli._normalize_companion_input("^M/type hello^M") == "/type hello"


def test_normalize_companion_input_strips_arrow_escape_garbage():
    assert cli._normalize_companion_input("/type hello\x1b[A") == "/type hello"
    assert cli._normalize_companion_input("/^[[Acompanion> ") == ""


def test_resolve_terminal_frontend_state_auto_disables_when_not_a_tty(monkeypatch):
    monkeypatch.setattr(cli.sys, "stdin", SimpleNamespace(isatty=lambda: False))
    monkeypatch.setattr(cli.sys, "stdout", SimpleNamespace(isatty=lambda: False))

    enabled, state, detail = cli._resolve_terminal_frontend_state("auto")

    assert enabled is False
    assert state == "disabled"
    assert "stdin_not_tty" in detail


def test_should_start_console_host_only_when_requested_or_terminal_missing():
    assert cli._should_start_console_host(terminal_enabled=True, open_console=False) is False
    assert cli._should_start_console_host(terminal_enabled=True, open_console=True) is True
    assert cli._should_start_console_host(terminal_enabled=False, open_console=False) is True


def test_print_camera_result_includes_persisted_snapshot_path(capsys):
    result = SimpleNamespace(
        success=True,
        snapshot=SimpleNamespace(
            status=SimpleNamespace(value="degraded"),
            limited_awareness=True,
            scene_summary="dim scene",
            source_frame=SimpleNamespace(
                fixture_path="/tmp/latest_camera_snapshot.jpg",
                metadata={"camera_warmup_retry_used": True},
            ),
        ),
    )

    cli._print_camera_result(result)

    output = capsys.readouterr().out
    assert "camera success=True" in output
    assert "path=/tmp/latest_camera_snapshot.jpg" in output
    assert "camera_warmup_retry_used=true" in output


def test_print_companion_help_mentions_optional_console(capsys):
    cli._print_companion_help(console_started=False)

    output = capsys.readouterr().out
    assert "type naturally for a text turn" in output
    assert "/presence opens the optional lightweight character shell" in output
    assert "/console starts the optional browser operator surface" in output
    assert "restart local-companion with a new --session-id" in output


def test_describe_action_policy_reason_humanizes_operator_approval():
    text = cli._describe_action_policy_reason(
        detail="operator_approval_required",
        policy_decision="require_approval",
        risk_class="operator_sensitive_write",
        connector_id="incident_local",
        action_name="request_operator_help",
    )

    assert "operator-sensitive work" in text
    assert "require_approval" in text
    assert "operator_sensitive_write" in text


def test_build_presence_url_preserves_session_context():
    url = cli._build_presence_url("http://127.0.0.1:8765/console", session_id="local companion")

    assert url == "http://127.0.0.1:8765/presence?session_id=local%20companion"


def test_performance_dry_run_prints_show_plan(capsys):
    exit_code = cli.run_performance_dry_run_command(
        Namespace(
            show_name="investor_expressive_motion_v8",
            segment_ids=[],
            cue_ids=[],
            proof_backend_mode="deterministic_show",
            language="zh-CN",
            narration_voice_preset="chinese_cute_character",
            narration_voice_name=None,
            narration_voice_rate=None,
            narration_only=False,
            proof_only=False,
        )
    )

    assert exit_code == 0
    output = capsys.readouterr().out
    assert "show=investor_expressive_motion_v8" in output
    assert "segment=attentive_notice_right" in output
    assert "cue=attentive_notice_right_run kind=body_expressive_motif" in output
    assert "cue=guarded_close_right_run kind=body_expressive_motif" in output
    assert "proof_backend_mode=deterministic_show" in output
    assert "voice_preset=chinese_cute_character" in output


def test_performance_cli_commands_use_venue_demo_settings(monkeypatch, capsys):
    runtime = _FakePerformanceRuntime()
    seen = {}

    def _build_runtime(settings=None):
        seen["settings"] = settings
        return _FakeRuntimeContext(runtime)

    monkeypatch.setattr(cli, "build_desktop_runtime", _build_runtime)
    monkeypatch.setattr(
        cli,
        "benchmark_show_narration",
        lambda operator_console, definition, request: {
            "show_name": definition.show_name,
            "version": definition.version,
            "session_id": request.session_id or definition.session_id,
            "language": request.language or "zh-CN",
            "voice_mode": "stub_demo",
            "voice_preset": request.narration_voice_preset or "chinese_cute_character",
            "voice_name": request.narration_voice_name or "Tingting",
            "voice_rate": request.narration_voice_rate or 210,
            "target_total_duration_seconds": 216,
            "target_narration_ms": 0,
            "actual_narration_ms": 0.0,
            "timing_drift_ms": -200.0,
            "cue_count": 1,
            "items": [
                {
                    "cue_id": "guarded_close_right_run",
                    "voice_status": "completed",
                    "target_duration_ms": 0,
                    "actual_duration_ms": 0.0,
                    "timing_drift_ms": -300.0,
                }
            ],
        },
    )

    assert cli.run_performance_catalog_command(Namespace(json=False)) == 0
    catalog_output = capsys.readouterr().out
    assert "investor_expressive_motion_v8" in catalog_output
    assert "latest_run_id=performance-abc123" in catalog_output

    assert (
        cli.run_performance_show_command(
            Namespace(
                show_name="investor_expressive_motion_v8",
                session_id=None,
                segment_ids=["guarded_close_right"],
                cue_ids=[],
                response_mode=None,
                proof_backend_mode="deterministic_show",
                proof_voice_mode=None,
                narration_voice_mode=None,
                language="en",
                narration_voice_preset="english_cute_character",
                narration_voice_name=None,
                narration_voice_rate=185,
                no_narration=True,
                narration_only=False,
                proof_only=False,
                force_degraded_cue_ids=[],
                reset_runtime=False,
                background=False,
            )
        )
        == 0
    )
    output = capsys.readouterr().out
    assert "performance_show run_id=performance-abc123 status=completed" in output
    assert seen["settings"].blink_context_mode == CompanionContextMode.VENUE_DEMO
    assert seen["settings"].blink_body_semantic_tuning_path == str(cli.SHOW_TUNING_PATHS["investor_expressive_motion_v8"])
    assert runtime.operator_console.last_request.narration_enabled is False
    assert runtime.operator_console.last_request.segment_ids == ["guarded_close_right"]
    assert runtime.operator_console.last_request.proof_backend_mode.value == "deterministic_show"
    assert "motion_outcome=live_applied" in output
    assert "coverage=head_yaw,eye_yaw,brows" in output
    assert "motion_margin safety_gate_passed=True" in output
    assert "tuning_path=runtime/body/semantic_tuning/robot_head_investor_show_v8.json" in output

    assert (
        cli.run_performance_benchmark_command(
            Namespace(
                show_name="investor_expressive_motion_v8",
                segment_ids=["guarded_close_right"],
                cue_ids=[],
                language="zh-CN",
                narration_voice_mode="stub_demo",
                narration_voice_preset="chinese_cute_character",
                narration_voice_name=None,
                narration_voice_rate=260,
                json=False,
            )
        )
        == 0
    )
    benchmark_output = capsys.readouterr().out
    assert "performance_benchmark show=investor_expressive_motion_v8" in benchmark_output
    assert "voice_preset=chinese_cute_character" in benchmark_output
    assert "language=zh-CN" in benchmark_output


def test_performance_show_rejects_background_mode_in_one_shot_cli(capsys):
    exit_code = cli.run_performance_show_command(
        Namespace(
            show_name="investor_expressive_motion_v8",
            session_id=None,
            segment_ids=[],
            cue_ids=[],
            response_mode=None,
            proof_backend_mode="deterministic_show",
            proof_voice_mode=None,
            narration_voice_mode=None,
            language=None,
            narration_voice_preset=None,
            narration_voice_name=None,
            narration_voice_rate=None,
            no_narration=True,
            narration_only=False,
            proof_only=False,
            force_degraded_cue_ids=[],
            reset_runtime=False,
            background=True,
        )
    )

    assert exit_code == 1
    assert "background_mode_requires_long_running_blink_appliance" in capsys.readouterr().out


def test_local_companion_entrypoint_accepts_top_level_performance_commands(monkeypatch):
    called = {}

    monkeypatch.setattr(cli.sys, "argv", ["local-companion", "performance-benchmark", "investor_expressive_motion_v8"])


    def _run_benchmark(args):
        called["command"] = args.command
        return 0

    monkeypatch.setattr(cli, "run_performance_benchmark_command", _run_benchmark)

    with pytest.raises(SystemExit) as exc:
        cli.companion_main()

    assert exc.value.code == 0
    assert called["command"] == "performance-benchmark"


def test_action_plane_cli_commands(monkeypatch, capsys):
    runtime = _FakeActionPlaneRuntime()

    def _build_runtime(settings=None):
        del settings
        return _FakeRuntimeContext(runtime)

    monkeypatch.setattr(cli, "build_desktop_runtime", _build_runtime)

    assert cli.run_connector_status_command(Namespace(json=False)) == 0
    assert "notes_local supported=True" in capsys.readouterr().out

    assert cli.run_approval_list_command(Namespace(json=False)) == 0
    approval_output = capsys.readouterr().out
    assert "act_pending" in approval_output
    assert "policy=require_approval" in approval_output
    assert "why=" in approval_output

    assert cli.run_approval_resolve_command(Namespace(action_id="act_pending", note="ok"), approve=True) == 0
    resolved_output = capsys.readouterr().out
    assert "approval=approved" in resolved_output
    assert "operator_summary=The operator help request has been approved and executed." in resolved_output

    assert cli.run_action_history_command(Namespace(limit=10, json=False)) == 0
    history_output = capsys.readouterr().out
    assert "act_history" in history_output
    assert "operator_summary=Created the requested note locally." in history_output

    assert cli.run_replay_action_command(Namespace(action_id="act_history", note=None)) == 0
    replay_output = capsys.readouterr().out
    assert "replay_act_history" in replay_output
    assert "operator_summary=The deterministic replay completed successfully." in replay_output

    assert cli.run_action_bundle_list_command(Namespace(session_id=None, limit=10, json=False)) == 0
    assert "workflow_wf_pending" in capsys.readouterr().out

    assert cli.run_action_bundle_show_command(Namespace(bundle_id="workflow_wf_pending", json=False)) == 0
    assert "artifact_dir=/tmp/action_bundle" in capsys.readouterr().out

    assert cli.run_action_bundle_teacher_review_command(
        Namespace(
            bundle_id="workflow_wf_pending",
            review_value="good",
            label=None,
            note="solid",
            author="operator_console",
            action_feedback_labels="missing_follow_up",
            benchmark_tags="action_trace_completeness",
        )
    ) == 0
    assert "ann-workflow_wf_pending" in capsys.readouterr().out

    assert cli.run_replay_action_bundle_command(
        Namespace(bundle_id="workflow_wf_pending", note=None, approved_action_id=[], json=False)
    ) == 0
    assert "action-replay-1" in capsys.readouterr().out

    assert cli.run_workflow_list_command(Namespace(json=False)) == 0
    assert "capture_note_and_reminder" in capsys.readouterr().out

    assert cli.run_workflow_runs_command(Namespace(session_id=None, limit=10, json=False)) == 0
    workflow_output = capsys.readouterr().out
    assert "wf_pending" in workflow_output
    assert "pause_reason=runtime_restart_review" in workflow_output

    assert cli.run_workflow_start_command(
        Namespace(workflow_id="capture_note_and_reminder", session_id="tool-session", inputs="{}", note="cli")
    ) == 0
    assert "wf_started" in capsys.readouterr().out

    assert cli.run_workflow_resume_command(Namespace(workflow_run_id="wf_pending", note="resume")) == 0
    assert "resumed=True" in capsys.readouterr().out

    assert cli.run_workflow_retry_command(Namespace(workflow_run_id="wf_pending", note="retry")) == 0
    assert "retried=True" in capsys.readouterr().out

    assert cli.run_workflow_pause_command(Namespace(workflow_run_id="wf_pending", note="pause")) == 0
    assert "paused=True" in capsys.readouterr().out


def test_companion_actions_command_outputs_status_and_resolutions(capsys):
    runtime = _FakeActionPlaneRuntime()

    assert cli._handle_companion_actions_command(
        "/actions status",
        runtime=runtime,
        session_id="workflow-session",
    ) is True
    status_output = capsys.readouterr().out
    assert "pending=1" in status_output
    assert "review_required=1" in status_output
    assert "next_step=Approve or reject act_pending from the interactive loop." in status_output
    assert "approval_help use='/actions approvals'" in status_output

    assert cli._handle_companion_actions_command(
        "/actions approvals",
        runtime=runtime,
        session_id="workflow-session",
    ) is True
    approvals_output = capsys.readouterr().out
    assert "policy=require_approval" in approvals_output
    assert "risk=operator_sensitive_write" in approvals_output
    assert "why=Review the pending operator help request." in approvals_output

    assert cli._handle_companion_actions_command(
        "/actions approve act_pending looks good",
        runtime=runtime,
        session_id="workflow-session",
    ) is True
    approve_output = capsys.readouterr().out
    assert "approval=approved" in approve_output
    assert "operator_summary=The operator help request has been approved and executed." in approve_output

    assert cli._handle_companion_actions_command(
        "/actions bundle workflow_wf_pending",
        runtime=runtime,
        session_id="workflow-session",
    ) is True
    bundle_output = capsys.readouterr().out
    assert "artifact_dir=/tmp/action_bundle" in bundle_output
