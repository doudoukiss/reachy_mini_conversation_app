from __future__ import annotations

from datetime import timedelta
from pathlib import Path
import threading
import time

from embodied_stack.backends.router import BackendRouter, OllamaProbeSnapshot
from embodied_stack.brain.perception import confidence_from_score
from embodied_stack.config import Settings
from embodied_stack.desktop.app import build_desktop_runtime
from embodied_stack.demo.local_companion_checks import FakeDeviceRegistry
from embodied_stack.multimodal.camera import DesktopCameraSource
from embodied_stack.shared.models import (
    EpisodeExportSessionRequest,
    InitiativeDecision,
    PerceptionObservation,
    PerceptionObservationType,
    PerceptionProviderMode,
    PerceptionSnapshotRecord,
    PerceptionSnapshotStatus,
    ReminderRecord,
    RobotMode,
    ShiftOperatingState,
    ShiftSupervisorSnapshot,
    VoiceRuntimeMode,
    utc_now,
)


def build_settings(tmp_path: Path, **overrides) -> Settings:
    return Settings(
        _env_file=None,
        brain_store_path=str(tmp_path / "brain_store.json"),
        demo_report_dir=str(tmp_path / "demo_runs"),
        demo_check_dir=str(tmp_path / "demo_checks"),
        episode_export_dir=str(tmp_path / "episodes"),
        shift_report_dir=str(tmp_path / "shift_reports"),
        operator_auth_token="desktop-test-token",
        operator_auth_runtime_file=str(tmp_path / "operator_auth.json"),
        blink_always_on_enabled=True,
        **overrides,
    )


class StaticOllamaProbe:
    def __init__(self, snapshot: OllamaProbeSnapshot) -> None:
        self._snapshot = snapshot

    def snapshot(self) -> OllamaProbeSnapshot:
        return self._snapshot


class FakeSemanticVisionProvider:
    mode = PerceptionProviderMode.OLLAMA_VISION

    def analyze_snapshot(self, request):
        source_frame = request.source_frame.model_copy(deep=True)
        return PerceptionSnapshotRecord(
            session_id=request.session_id,
            provider_mode=self.mode,
            source=request.source,
            status=PerceptionSnapshotStatus.OK,
            limited_awareness=False,
            message="semantic_fixture_ready",
            scene_summary="A visitor is standing near the front desk sign.",
            source_frame=source_frame,
            observations=[
                PerceptionObservation(
                    observation_type=PerceptionObservationType.PERSON_VISIBILITY,
                    bool_value=True,
                    confidence=confidence_from_score(0.91),
                    source_frame=source_frame,
                ),
                PerceptionObservation(
                    observation_type=PerceptionObservationType.LOCATION_ANCHOR,
                    text_value="Front Desk",
                    confidence=confidence_from_score(0.88),
                    source_frame=source_frame,
                ),
                PerceptionObservation(
                    observation_type=PerceptionObservationType.SCENE_SUMMARY,
                    text_value="A visitor is standing near the front desk sign.",
                    confidence=confidence_from_score(0.9),
                    source_frame=source_frame,
                ),
            ],
        )


def test_always_on_snapshot_includes_supervisor_status(tmp_path: Path):
    settings = build_settings(
        tmp_path,
        blink_runtime_mode=RobotMode.DESKTOP_BODYLESS,
        blink_model_profile="desktop_local",
    )

    runtime = build_desktop_runtime(settings=settings, device_registry=FakeDeviceRegistry())
    session = runtime.ensure_session(session_id="always-on-status")
    runtime.configure_companion_loop(session_id=session.session_id, voice_mode=VoiceRuntimeMode.DESKTOP_NATIVE)
    snapshot = runtime.snapshot(session_id=session.session_id, voice_mode=VoiceRuntimeMode.DESKTOP_NATIVE)

    assert snapshot.runtime.always_on_enabled is True
    assert snapshot.runtime.supervisor.enabled is True
    assert snapshot.runtime.presence_runtime.state.value == "idle"
    assert snapshot.runtime.voice_loop.state.value == "idle"
    assert snapshot.runtime.scene_observer.backend in {"frame_diff_fallback", "opencv_frame_diff", "opencv_frame_diff+mediapipe"}
    assert snapshot.runtime.initiative_engine.last_decision.value == "ignore"
    assert snapshot.runtime.trigger_engine.last_decision.value == "wait"


def test_always_on_live_turn_records_voice_loop_history(tmp_path: Path):
    settings = build_settings(
        tmp_path,
        blink_runtime_mode=RobotMode.DESKTOP_BODYLESS,
        blink_model_profile="offline_stub",
    )

    runtime = build_desktop_runtime(settings=settings, device_registry=FakeDeviceRegistry())
    session = runtime.ensure_session(session_id="always-on-voice")
    runtime.configure_companion_loop(session_id=session.session_id, voice_mode=VoiceRuntimeMode.DESKTOP_NATIVE)
    runtime.submit_live_turn(
        session_id=session.session_id,
        voice_mode=VoiceRuntimeMode.DESKTOP_NATIVE,
        speak_reply=True,
        capture_camera=False,
    )
    artifacts = runtime.supervisor.export_artifacts()
    states = [item["state"] for item in artifacts["voice_loop"]["history"]]

    assert states[:2] == ["armed", "capturing"]
    assert "transcribing" in states
    assert "thinking" in states
    assert "speaking" in states
    assert states[-1] == "cooldown"


def test_mode_switching_clears_stale_open_mic_voice_loop_state(tmp_path: Path):
    settings = build_settings(
        tmp_path,
        blink_runtime_mode=RobotMode.DESKTOP_BODYLESS,
        blink_model_profile="offline_stub",
    )

    runtime = build_desktop_runtime(settings=settings, device_registry=FakeDeviceRegistry())
    session = runtime.ensure_session(session_id="always-on-mode-switch")

    runtime.configure_companion_loop(
        session_id=session.session_id,
        voice_mode=VoiceRuntimeMode.OPEN_MIC_LOCAL,
        audio_mode="open_mic",
    )
    open_mic_snapshot = runtime.snapshot(session_id=session.session_id, voice_mode=VoiceRuntimeMode.OPEN_MIC_LOCAL)

    runtime.configure_companion_loop(
        session_id=session.session_id,
        voice_mode=VoiceRuntimeMode.MACOS_SAY,
        audio_mode="push_to_talk",
    )
    push_to_talk_snapshot = runtime.snapshot(session_id=session.session_id, voice_mode=VoiceRuntimeMode.MACOS_SAY)

    assert open_mic_snapshot.runtime.voice_loop.state.value == "vad_waiting"
    assert open_mic_snapshot.runtime.voice_loop.audio_backend == "whisper_cpp_local"
    assert push_to_talk_snapshot.runtime.voice_loop.state.value == "idle"
    assert push_to_talk_snapshot.runtime.voice_loop.audio_backend is None


def test_visual_query_refreshes_semantic_scene_and_exports_always_on_artifacts(tmp_path: Path):
    settings = build_settings(
        tmp_path,
        blink_runtime_mode=RobotMode.DESKTOP_BODYLESS,
        blink_model_profile="desktop_local",
        blink_backend_profile="m4_pro_companion",
        ollama_text_model="qwen3.5:9b",
        ollama_vision_model="qwen3.5:9b",
        ollama_embedding_model="embeddinggemma:300m",
    )
    router = BackendRouter(
        settings=settings,
        ollama_probe=StaticOllamaProbe(
            OllamaProbeSnapshot(
                reachable=True,
                installed_models={"qwen3.5:9b", "embeddinggemma:300m"},
                running_models={"qwen3.5:9b"},
                latency_ms=42.0,
            )
        ),
    )
    runtime = build_desktop_runtime(
        settings=settings,
        device_registry=FakeDeviceRegistry(),
        backend_router=router,
    )
    runtime.operator_console.perception_service.providers[PerceptionProviderMode.OLLAMA_VISION] = FakeSemanticVisionProvider()
    session = runtime.ensure_session(session_id="always-on-visual")
    runtime.configure_companion_loop(session_id=session.session_id, voice_mode=VoiceRuntimeMode.STUB_DEMO, speak_enabled=False)

    runtime.submit_text(
        "What do you see right now?",
        session_id=session.session_id,
        voice_mode=VoiceRuntimeMode.STUB_DEMO,
        speak_reply=False,
        source="always_on_test",
    )
    latest = runtime.perception_service.get_latest_snapshot(session.session_id)
    episode = runtime.operator_console.export_session_episode(
        EpisodeExportSessionRequest(session_id=session.session_id, include_asset_refs=True)
    )

    assert latest is not None
    assert latest.provider_mode == PerceptionProviderMode.OLLAMA_VISION
    assert latest.limited_awareness is False
    assert "scene_observer" in episode.artifact_files
    assert "presence_runtime" in episode.artifact_files
    assert "trigger_history" in episode.artifact_files
    assert "voice_loop" in episode.artifact_files
    assert "ollama_runtime" in episode.artifact_files


def test_slow_typed_turn_keeps_presence_alive(tmp_path: Path):
    settings = build_settings(
        tmp_path,
        blink_runtime_mode=RobotMode.DESKTOP_BODYLESS,
        blink_model_profile="offline_stub",
        blink_fast_presence_ack_delay_seconds=0.02,
        blink_fast_presence_tool_delay_seconds=0.2,
    )

    runtime = build_desktop_runtime(settings=settings, device_registry=FakeDeviceRegistry())
    session = runtime.ensure_session(session_id="presence-slow-turn")
    runtime.configure_companion_loop(session_id=session.session_id, voice_mode=VoiceRuntimeMode.STUB_DEMO)
    original = runtime.operator_console._turn_handler_with_context_refresh

    def slow_handler(turn_request):
        time.sleep(0.12)
        return original(turn_request)

    runtime.operator_console._turn_handler_with_context_refresh = slow_handler
    result: dict[str, object] = {}
    worker = threading.Thread(
        target=lambda: result.setdefault(
            "interaction",
            runtime.submit_text(
                "Check the current front desk state.",
                session_id=session.session_id,
                voice_mode=VoiceRuntimeMode.STUB_DEMO,
                speak_reply=False,
                source="presence_test",
            ),
        ),
        daemon=True,
    )

    worker.start()
    time.sleep(0.06)
    snapshot = runtime.snapshot(session_id=session.session_id, voice_mode=VoiceRuntimeMode.STUB_DEMO)
    events = runtime.drain_runtime_events()
    worker.join(timeout=1.0)

    interaction = result["interaction"]

    assert snapshot.runtime.presence_runtime.state.value in {"acknowledging", "thinking_fast"}
    assert any(
        item.get("event_type") == "presence_state_changed" and item.get("state") == "acknowledging"
        for item in events
    )
    assert interaction.live_turn_diagnostics.fast_presence_acknowledged is True


def test_initiative_follow_up_reply_is_visible_without_spoken_output(tmp_path: Path):
    settings = build_settings(
        tmp_path,
        blink_runtime_mode=RobotMode.DESKTOP_BODYLESS,
        blink_model_profile="offline_stub",
    )

    runtime = build_desktop_runtime(settings=settings, device_registry=FakeDeviceRegistry())
    runtime.device_registry.camera_capture.source = DesktopCameraSource(
        configured_source="disabled",
        mode="disabled",
        available=False,
        note="test_disable_observer_for_follow_up",
    )
    session = runtime.ensure_session(session_id="initiative-follow-up", user_id="initiative-user")
    runtime.configure_companion_loop(
        session_id=session.session_id,
        voice_mode=VoiceRuntimeMode.STUB_DEMO,
        speak_enabled=False,
    )
    runtime.orchestrator.memory.replace_shift_supervisor(
        ShiftSupervisorSnapshot(
            state=ShiftOperatingState.WAITING_FOR_FOLLOW_UP,
            active_session_id=session.session_id,
            active_user_id=session.user_id,
            override_active=True,
            override_state=ShiftOperatingState.READY_IDLE,
            override_reason="test_force_ready_idle",
            follow_up_deadline_at=utc_now() - timedelta(seconds=5),
            last_interaction_at=utc_now() - timedelta(minutes=2),
        )
    )

    runtime.run_supervisor_once()

    snapshot = runtime.snapshot(session_id=session.session_id, voice_mode=VoiceRuntimeMode.STUB_DEMO)
    events = runtime.drain_runtime_events()

    proactive_event = next(item for item in events if item.get("event_type") == "proactive_reply")
    assert snapshot.runtime.initiative_engine.last_decision == InitiativeDecision.ASK
    assert proactive_event["reply_text"] is not None
    assert "Do you want to keep going" in proactive_event["reply_text"]


def test_initiative_due_reminder_starts_bounded_workflow(tmp_path: Path):
    settings = build_settings(
        tmp_path,
        blink_runtime_mode=RobotMode.DESKTOP_BODYLESS,
        blink_model_profile="offline_stub",
    )

    runtime = build_desktop_runtime(settings=settings, device_registry=FakeDeviceRegistry())
    session = runtime.ensure_session(session_id="initiative-reminder", user_id="initiative-user")
    runtime.configure_companion_loop(
        session_id=session.session_id,
        voice_mode=VoiceRuntimeMode.STUB_DEMO,
        speak_enabled=False,
    )
    reminder = runtime.orchestrator.upsert_reminder(
        ReminderRecord(
            session_id=session.session_id,
            user_id=session.user_id,
            reminder_text="Pay the electric bill.",
            due_at=utc_now() - timedelta(minutes=10),
        )
    )

    runtime.run_supervisor_once()

    snapshot = runtime.snapshot(session_id=session.session_id, voice_mode=VoiceRuntimeMode.STUB_DEMO)
    events = runtime.drain_runtime_events()
    updated = runtime.orchestrator.memory.get_reminder(reminder.reminder_id)
    workflow_runs = runtime.operator_console.list_action_plane_workflow_runs(session_id=session.session_id).items

    assert snapshot.runtime.initiative_engine.last_decision == InitiativeDecision.ACT
    assert any(item.get("event_type") == "initiative_action" for item in events)
    assert updated is not None and updated.last_triggered_at is not None
    assert any(item.workflow_id == "reminder_due_follow_up" for item in workflow_runs)


def test_initiative_silence_suppresses_due_reminder_workflow(tmp_path: Path):
    settings = build_settings(
        tmp_path,
        blink_runtime_mode=RobotMode.DESKTOP_BODYLESS,
        blink_model_profile="offline_stub",
    )

    runtime = build_desktop_runtime(settings=settings, device_registry=FakeDeviceRegistry())
    session = runtime.ensure_session(session_id="initiative-silenced", user_id="initiative-user")
    runtime.configure_companion_loop(
        session_id=session.session_id,
        voice_mode=VoiceRuntimeMode.STUB_DEMO,
        speak_enabled=False,
    )
    reminder = runtime.orchestrator.upsert_reminder(
        ReminderRecord(
            session_id=session.session_id,
            user_id=session.user_id,
            reminder_text="Submit the report.",
            due_at=utc_now() - timedelta(minutes=10),
        )
    )
    runtime.silence_initiative(minutes=30.0)

    runtime.run_supervisor_once()

    snapshot = runtime.snapshot(session_id=session.session_id, voice_mode=VoiceRuntimeMode.STUB_DEMO)
    events = runtime.drain_runtime_events()
    updated = runtime.orchestrator.memory.get_reminder(reminder.reminder_id)

    assert snapshot.runtime.initiative_engine.last_decision == InitiativeDecision.IGNORE
    assert snapshot.runtime.initiative_engine.suppression_reason == "manual_silence"
    assert not any(item.get("event_type") == "initiative_action" for item in events)
    assert updated is not None and updated.last_triggered_at is None
