from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from embodied_stack.action_plane.models import ActionInvocationContext
from embodied_stack.body import calibration as calibration_module
from embodied_stack.brain.app import create_app as create_brain_app
from embodied_stack.brain.operator.service import OperatorConsoleService
from embodied_stack.brain.orchestrator import BrainOrchestrator
from embodied_stack.body.profile import default_head_profile
from embodied_stack.config import Settings
from embodied_stack.demo.local_companion_certification import LATEST_READINESS_FILE
from embodied_stack.demo.coordinator import DemoCoordinator
from embodied_stack.desktop.runtime import build_inprocess_embodiment_gateway
from embodied_stack.shared.contracts import (
    ActionInvocationOrigin,
    BodyDriverMode,
    BodyState,
    LocalCompanionCertificationVerdict,
    LocalCompanionReadinessRecord,
)


def _build_appliance_client(tmp_path: Path, **overrides) -> TestClient:
    settings = Settings(
        _env_file=None,
        brain_store_path=str(tmp_path / "brain_store.json"),
        demo_report_dir=str(tmp_path / "demo_runs"),
        demo_check_dir=str(tmp_path / "demo_checks"),
        shift_report_dir=str(tmp_path / "shift_reports"),
        episode_export_dir=str(tmp_path / "episodes"),
        performance_report_dir=str(tmp_path / "performance_runs"),
        perception_frame_dir=str(tmp_path / "perception_frames"),
        brain_dialogue_backend="rule_based",
        brain_voice_backend="stub",
        shift_background_tick_enabled=False,
        operator_auth_token=None,
        operator_auth_runtime_file=str(tmp_path / "operator_auth.json"),
        blink_appliance_mode=True,
        blink_appliance_profile_file=str(tmp_path / "appliance_profile.json"),
        ollama_base_url="http://127.0.0.1:9",
        ollama_timeout_seconds=0.1,
        **overrides,
    )
    orchestrator = BrainOrchestrator(settings=settings, store_path=settings.brain_store_path)
    coordinator = DemoCoordinator(
        orchestrator=orchestrator,
        edge_gateway=build_inprocess_embodiment_gateway(settings),
        report_dir=settings.demo_report_dir,
    )
    return TestClient(create_brain_app(settings=settings, orchestrator=orchestrator, demo_coordinator=coordinator))


def _bootstrap_appliance_session(client: TestClient):
    return client.get("/console")


def _saved_calibration(path: Path) -> None:
    profile = default_head_profile()
    calibration = calibration_module.calibration_from_profile(profile, calibration_kind="saved")
    for joint in calibration.joint_records:
        joint.mirrored_direction_confirmed = True
    calibration.coupling_validation = {
        "neck_pitch_roll": "ok",
        "mirrored_eyelids": "ok",
        "mirrored_brows": "ok",
        "eyes_follow_lids": "ok",
        "range_conflicts": "ok",
    }
    calibration_module.save_head_calibration(calibration, path)


def _write_local_companion_readiness(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = LocalCompanionReadinessRecord(
        verdict=LocalCompanionCertificationVerdict.DEGRADED_BUT_ACCEPTABLE,
        summary="The companion is demo-usable, but camera and local model readiness are still degraded.",
        machine_ready=False,
        product_ready=True,
        machine_blockers=[],
        repo_or_runtime_issues=[],
        degraded_warnings=["camera authorization missing", "ollama unavailable"],
        last_certified_at=None,
        next_actions=["Grant camera access.", "Start Ollama before the next certification run."],
    )
    path.write_text(payload.model_dump_json(indent=2), encoding="utf-8")


def test_console_requires_operator_login(unauthenticated_brain_client):
    response = unauthenticated_brain_client.get("/console")
    assert response.status_code == 200
    assert "Operator Login" in response.text


def test_body_gateway_call_reuses_body_state_from_gateway_result(tmp_path):
    class _Gateway:
        def __init__(self) -> None:
            self.telemetry_calls = 0

        def get_telemetry(self):
            self.telemetry_calls += 1
            raise AssertionError("body gateway call should not force telemetry when body_state is already provided")

        def get_body_semantic_library(self, *, smoke_safe_only: bool = False):
            return {
                "ok": True,
                "status": "ok",
                "body_state": BodyState(driver_mode=BodyDriverMode.SERIAL).model_dump(mode="json"),
                "payload": {"semantic_actions": [{"canonical_name": "look_left"}], "smoke_safe_only": smoke_safe_only},
            }

    settings = Settings(
        _env_file=None,
        brain_store_path=str(tmp_path / "brain_store.json"),
        demo_report_dir=str(tmp_path / "demo_runs"),
        demo_check_dir=str(tmp_path / "demo_checks"),
        shift_report_dir=str(tmp_path / "shift_reports"),
        episode_export_dir=str(tmp_path / "episodes"),
        operator_auth_runtime_file=str(tmp_path / "operator_auth.json"),
    )
    gateway = _Gateway()
    service = OperatorConsoleService(
        settings=settings,
        orchestrator=object(),
        edge_gateway=gateway,
        demo_coordinator=object(),
        shift_report_store=object(),
        voice_manager=object(),
        backend_router=object(),
        device_registry=object(),
        perception_service=object(),
        episode_exporter=object(),
    )

    result = service.get_body_semantic_library(smoke_safe_only=True)

    assert result.ok is True
    assert result.payload["semantic_actions"][0]["canonical_name"] == "look_left"
    assert gateway.telemetry_calls == 0


def test_visual_query_camera_refresh_does_not_publish_events_before_reply(tmp_path):
    settings = Settings(
        _env_file=None,
        brain_store_path=str(tmp_path / "brain_store.json"),
        demo_report_dir=str(tmp_path / "demo_runs"),
        demo_check_dir=str(tmp_path / "demo_checks"),
        shift_report_dir=str(tmp_path / "shift_reports"),
        episode_export_dir=str(tmp_path / "episodes"),
        operator_auth_runtime_file=str(tmp_path / "operator_auth.json"),
    )
    source_frame = {
        "source_kind": "browser_camera_snapshot",
        "source_label": "operator_console_camera",
        "frame_id": "camera-frame",
        "mime_type": "image/jpeg",
        "width_px": 640,
        "height_px": 480,
        "captured_at": "2026-04-08T12:00:00Z",
    }

    service = OperatorConsoleService(
        settings=settings,
        orchestrator=object(),
        edge_gateway=object(),
        demo_coordinator=object(),
        shift_report_store=object(),
        voice_manager=object(),
        backend_router=SimpleNamespace(selected_backend_id=lambda kind: "ollama_vision"),
        device_registry=SimpleNamespace(
            camera_capture=SimpleNamespace(source=SimpleNamespace(mode="webcam")),
            capture_camera_snapshot=lambda: SimpleNamespace(
                source_frame=source_frame,
                image_data_url="data:image/jpeg;base64,ZmFrZQ==",
            ),
        ),
        perception_service=SimpleNamespace(get_latest_snapshot=lambda session_id=None: None),
        episode_exporter=object(),
    )
    captured_requests = []

    def record_snapshot(request):
        captured_requests.append(request)
        return None

    service.submit_perception_snapshot = record_snapshot

    service._maybe_refresh_scene_for_visual_query(
        session_id="visual-query-session",
        user_id="user-1",
        text="What can you see from the camera?",
    )

    assert len(captured_requests) == 1
    assert captured_requests[0].source == "before_reply_generation"
    assert captured_requests[0].publish_events is False


def test_operator_endpoint_rejects_unauthenticated_requests(unauthenticated_brain_client):
    response = unauthenticated_brain_client.get("/api/operator/snapshot")
    assert response.status_code == 401
    assert response.json()["detail"] == "operator_auth_required"


def test_console_page_is_served(brain_client):
    response = brain_client.get("/console")
    assert response.status_code == 200
    assert "Blink-AI Operator Console" in response.text
    assert "Reset + Run Desktop Story" in response.text
    assert 'id="action-bundles"' in response.text


def test_companion_test_page_is_served(brain_client):
    response = brain_client.get("/companion-test")
    assert response.status_code == 200
    assert "Blink-AI Companion Test" in response.text
    assert 'id="companion-send-btn"' in response.text


def test_presence_page_is_served(brain_client):
    response = brain_client.get("/presence")
    assert response.status_code == 200
    assert "Blink-AI Character Presence" in response.text
    assert 'id="presence-shell-window"' in response.text


def test_performance_page_is_served(brain_client):
    response = brain_client.get("/performance")
    assert response.status_code == 200
    assert "Deterministic Investor Performance Mode" in response.text
    assert 'id="performance-proof-grid"' in response.text
    assert 'id="performance-config-summary"' in response.text


def test_operator_performance_show_endpoints_roundtrip(brain_client):
    catalog = brain_client.get("/api/operator/performance-shows")
    assert catalog.status_code == 200
    catalog_body = catalog.json()
    assert any(item["show_name"] == "investor_expressive_motion_v8" for item in catalog_body["items"])

    run = brain_client.post(
        "/api/operator/performance-shows/investor_expressive_motion_v8/run",
        json={"background": False, "narration_enabled": False, "proof_backend_mode": "deterministic_show"},
    )
    assert run.status_code == 200
    run_body = run.json()
    assert run_body["show_name"] == "investor_expressive_motion_v8"
    assert run_body["status"] == "completed"
    assert run_body["proof_backend_mode"] == "deterministic_show"
    assert run_body["artifact_files"]["run_summary"].endswith("run_summary.json")

    latest = brain_client.get(f"/api/operator/performance-shows/runs/{run_body['run_id']}")
    assert latest.status_code == 200
    latest_body = latest.json()
    assert latest_body["run_id"] == run_body["run_id"]
    assert latest_body["episode_id"] == run_body["episode_id"]


def test_operator_expression_catalog_endpoint_returns_grounded_capability_export(brain_client):
    response = brain_client.get("/api/operator/body/expression-catalog")

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    payload = body["payload"]
    assert payload["tuning_path"].endswith("robot_head_live_v1.json")
    catalog = payload["catalog"]
    assert catalog["schema_version"] == "blink_grounded_expression_catalog/v1"
    assert "friendly" in catalog["supported_persistent_states"]
    assert "guarded_close_right" in catalog["supported_motifs"]
    assert "head_turn_right_slow" in catalog["supported_structural_units"]
    assert "close_both_eyes_slow" in catalog["supported_expressive_units"]
    entry_names = {entry["canonical_name"] for entry in catalog["entries"]}
    assert "friendly" in entry_names
    assert "guarded_close_right" in entry_names


def test_appliance_console_is_tokenless_and_opens_setup_directly(tmp_path):
    with _build_appliance_client(tmp_path) as client:
        setup_page = _bootstrap_appliance_session(client)
        assert setup_page.status_code == 200
        assert "Local Appliance Setup" in setup_page.text

        status = client.get("/api/operator/auth/status")
        assert status.status_code == 200
        assert status.json()["authenticated"] is True
        assert status.json()["auth_mode"] == "appliance_localhost_trusted"

        companion_test = client.get("/companion-test")
        assert companion_test.status_code == 200
        assert "Blink-AI Companion Test" in companion_test.text


def test_appliance_status_and_profile_flow_surface_setup_state_and_snapshot_fields(tmp_path):
    profile_path = tmp_path / "appliance_profile.json"
    readiness_dir = tmp_path / "runtime" / "diagnostics" / "local_companion_certification"
    _write_local_companion_readiness(readiness_dir / LATEST_READINESS_FILE)
    with _build_appliance_client(tmp_path, local_companion_certification_dir=str(readiness_dir)) as client:
        _bootstrap_appliance_session(client)

        status = client.get("/api/appliance/status")
        assert status.status_code == 200
        body = status.json()
        assert body["setup_complete"] is False
        assert body["profile_exists"] is False
        assert body["auth_mode"] == "appliance_localhost_trusted"
        assert body["config_source"] == "repo_defaults"
        assert body["device_preset"] == "internal_macbook"
        assert body["selected_speaker_label"] == "system_default"
        assert body["speaker_selection_supported"] is False
        assert body["action_plane_ready"] is True
        assert body["browser_runtime_state"] in {"disabled", "degraded", "unsupported"}
        assert body["pending_action_count"] == 0
        assert body["waiting_workflow_count"] == 0
        assert body["review_required_count"] == 0
        assert body["local_companion_readiness"]["verdict"] == "degraded_but_acceptable"
        assert body["local_companion_readiness"]["degraded_warnings"] == ["camera authorization missing", "ollama unavailable"]
        assert any(item["category"] == "setup" for item in body["setup_issues"])

        devices = client.get("/api/appliance/devices")
        assert devices.status_code == 200
        assert devices.json()["speaker_selection_supported"] is False
        assert devices.json()["selected_speaker_label"] == "system_default"

        saved = client.post(
            "/api/appliance/profile",
            json={
                "setup_complete": True,
                "device_preset": "external_monitor",
                "microphone_device": "MacBook Pro Microphone",
                "camera_device": "MacBook Pro Camera",
                "speaker_device": "system_default",
            },
        )
        assert saved.status_code == 200
        saved_body = saved.json()
        assert saved_body["setup_complete"] is True
        assert saved_body["profile_exists"] is True
        assert saved_body["config_source"] == "appliance_profile"
        assert saved_body["device_preset"] == "external_monitor"
        assert profile_path.exists()

        persisted = json.loads(profile_path.read_text(encoding="utf-8"))
        assert persisted["setup_complete"] is True
        assert persisted["device_preset"] == "external_monitor"
        assert persisted["microphone_device"] == "MacBook Pro Microphone"
        assert persisted["camera_device"] == "MacBook Pro Camera"

        console = client.get("/console")
        assert console.status_code == 200
        assert "Blink-AI Operator Console" in console.text

        snapshot = client.get("/api/operator/snapshot")
        assert snapshot.status_code == 200
        runtime = snapshot.json()["runtime"]
        assert runtime["setup_complete"] is True
        assert runtime["auth_mode"] == "appliance_localhost_trusted"
        assert runtime["config_source"] == "appliance_profile"
        assert runtime["device_preset"] == "external_monitor"
        assert runtime["selected_speaker_label"] == "system_default"
        assert runtime["speaker_selection_supported"] is False
        assert runtime["local_companion_readiness"]["verdict"] == "degraded_but_acceptable"
        assert runtime["local_companion_readiness"]["next_actions"] == [
            "Grant camera access.",
            "Start Ollama before the next certification run.",
        ]


def test_console_page_includes_browser_device_picker_controls(brain_client):
    response = brain_client.get("/console")

    assert response.status_code == 200
    assert 'id="brain-status-panel"' in response.text
    assert 'id="brain-status-summary"' in response.text
    assert 'id="browser-microphone-input"' in response.text
    assert 'id="local-companion-readiness-pill"' in response.text
    assert 'id="action-center-panel"' in response.text
    assert 'id="action-center-attention"' in response.text
    assert 'id="action-center-inspector-summary"' in response.text
    assert 'id="browser-camera-input"' in response.text
    assert 'id="disable-camera-btn"' in response.text
    assert 'id="browser-speaker-input"' in response.text
    assert 'id="voice-howto-note"' in response.text
    assert 'id="frontend-status-chip"' in response.text
    assert 'id="open-presence-shell-link"' in response.text


def test_operator_presence_endpoint_exposes_character_shell(brain_client):
    response = brain_client.get("/api/operator/presence")

    assert response.status_code == 200
    body = response.json()
    assert "character_projection_profile" in body
    assert "character_semantic_intent" in body
    assert "character_presence_shell" in body
    assert body["character_presence_shell"]["surface_state"] in {
        "idle",
        "listening",
        "acknowledging",
        "thinking",
        "speaking",
        "tool_working",
        "reengaging",
        "interrupted",
        "degraded",
    }

    snapshot = brain_client.get("/api/operator/snapshot")
    assert snapshot.status_code == 200
    assert "character_projection_profile" in snapshot.json()["runtime"]
    assert "character_semantic_intent" in snapshot.json()["runtime"]
    assert "character_presence_shell" in snapshot.json()["runtime"]


def test_operator_console_exposes_serial_body_controls_and_exports_body_artifacts(monkeypatch, tmp_path: Path):
    calibration_path = tmp_path / "runtime" / "calibrations" / "robot_head_live_v1.json"
    _saved_calibration(calibration_path)
    monkeypatch.setattr("embodied_stack.body.driver.DEFAULT_ARM_LEASE_PATH", tmp_path / "runtime" / "serial" / "live_motion_arm.json")
    monkeypatch.setattr("embodied_stack.body.driver.DEFAULT_MOTION_REPORT_DIR", tmp_path / "runtime" / "serial" / "motion_reports")
    monkeypatch.setattr("embodied_stack.body.driver.DEFAULT_SEMANTIC_TUNING_PATH", tmp_path / "runtime" / "body" / "semantic_tuning" / "robot_head_live_v1.json")
    monkeypatch.setattr("embodied_stack.body.driver.DEFAULT_TEACHER_REVIEW_PATH", tmp_path / "runtime" / "body" / "semantic_tuning" / "teacher_reviews.jsonl")
    settings = Settings(
        _env_file=None,
        brain_store_path=str(tmp_path / "brain_store.json"),
        demo_report_dir=str(tmp_path / "demo_runs"),
        demo_check_dir=str(tmp_path / "demo_checks"),
        shift_report_dir=str(tmp_path / "shift_reports"),
        episode_export_dir=str(tmp_path / "episodes"),
        perception_frame_dir=str(tmp_path / "perception_frames"),
        brain_dialogue_backend="rule_based",
        brain_voice_backend="stub",
        shift_background_tick_enabled=False,
        operator_auth_token="serial-console-token",
        operator_auth_runtime_file=str(tmp_path / "operator_auth.json"),
        blink_runtime_mode="desktop_serial_body",
        blink_body_driver="serial",
        blink_serial_transport="dry_run",
        blink_servo_baud=1000000,
        blink_head_calibration=str(calibration_path),
    )
    orchestrator = BrainOrchestrator(settings=settings, store_path=settings.brain_store_path)
    coordinator = DemoCoordinator(
        orchestrator=orchestrator,
        edge_gateway=build_inprocess_embodiment_gateway(settings),
        report_dir=settings.demo_report_dir,
    )
    with TestClient(create_brain_app(settings=settings, orchestrator=orchestrator, demo_coordinator=coordinator)) as client:
        login = client.post("/api/operator/auth/login", json={"token": settings.operator_auth_token})
        assert login.status_code == 200

        console = client.get("/console")
        assert console.status_code == 200
        assert 'id="body-connect-btn"' in console.text
        assert 'id="body-semantic-smoke-btn"' in console.text
        assert 'id="servo-lab-joint-select"' in console.text
        assert 'id="servo-lab-move-btn"' in console.text
        assert 'id="servo-lab-sweep-btn"' in console.text

        status = client.get("/api/operator/body/status")
        assert status.status_code == 200
        assert status.json()["body_state"]["transport_baud_rate"] == 1000000

        servo_lab_catalog = client.get("/api/operator/body/servo-lab/catalog")
        assert servo_lab_catalog.status_code == 200
        assert servo_lab_catalog.json()["payload"]["joint_count"] == 11

        servo_lab_readback = client.post("/api/operator/body/servo-lab/readback", json={"joint_name": "head_yaw"})
        assert servo_lab_readback.status_code == 200
        assert servo_lab_readback.json()["payload"]["selected_joint"]["joint_name"] == "head_yaw"

        semantic_library = client.get("/api/operator/body/semantic-library?smoke_safe_only=true")
        assert semantic_library.status_code == 200
        assert any(item["canonical_name"] == "look_left" for item in semantic_library.json()["payload"]["semantic_actions"])

        arm = client.post("/api/operator/body/arm", json={"ttl_seconds": 60})
        assert arm.status_code == 200
        assert arm.json()["ok"] is True

        smoke = client.post(
            "/api/operator/body/semantic-smoke",
            json={"action": "look_left", "intensity": 0.8, "repeat_count": 1},
        )
        assert smoke.status_code == 200
        assert smoke.json()["ok"] is True
        assert smoke.json()["body_state"]["latest_command_audit"]["command_type"] == "set_gaze"
        assert smoke.json()["body_state"]["latest_command_audit"]["canonical_action_name"] == "look_left"

        review = client.post(
            "/api/operator/body/teacher-review",
            json={
                "action": "look_left",
                "review": "adjust",
                "note": "eyes should lead a bit more",
                "proposed_tuning_delta": {
                    "action_overrides": {
                        "look_left": {
                            "pose_offsets": {"eye_yaw": -0.05},
                            "notes": ["operator_review_adjustment"],
                        }
                    }
                },
                "apply_tuning": True,
            },
        )
        assert review.status_code == 200
        assert review.json()["ok"] is True

        servo_lab_move = client.post(
            "/api/operator/body/servo-lab/move",
            json={
                "joint_name": "head_yaw",
                "reference_mode": "current_delta",
                "delta_counts": 150,
                "speed_override": 240,
            },
        )
        assert servo_lab_move.status_code == 200
        assert servo_lab_move.json()["ok"] is True
        move_payload = servo_lab_move.json()["payload"]["servo_lab_move"]
        assert move_payload["effective_target"] == move_payload["current_position"] + 150

        servo_lab_sweep = client.post(
            "/api/operator/body/servo-lab/sweep",
            json={
                "joint_name": "head_yaw",
                "cycles": 1,
                "duration_ms": 300,
                "dwell_ms": 120,
            },
        )
        assert servo_lab_sweep.status_code == 200
        assert servo_lab_sweep.json()["ok"] is True
        assert len(servo_lab_sweep.json()["payload"]["servo_lab_sweep"]["steps"]) >= 2

        servo_lab_save = client.post(
            "/api/operator/body/servo-lab/save-calibration",
            json={
                "joint_name": "head_yaw",
                "raw_min": 1700,
                "raw_max": 2400,
            },
        )
        assert servo_lab_save.status_code == 200
        assert servo_lab_save.json()["ok"] is True

        neutral = client.post("/api/operator/body/write-neutral")
        assert neutral.status_code == 200
        assert neutral.json()["motion_report_path"] is not None

        interaction = client.post(
            "/api/operator/text-turn",
            json={
                "session_id": "serial-console-session",
                "input_text": "hello there",
                "voice_mode": "stub_demo",
                "speak_reply": False,
            },
        )
        assert interaction.status_code == 200

        export = client.post(
            "/api/operator/episodes/export-session",
            json={"session_id": "serial-console-session"},
        )
        assert export.status_code == 200
        artifact_files = export.json()["artifact_files"]
        assert "body_command_audits" in artifact_files
        assert "body_motion_report_index" in artifact_files
        assert "body_semantic_tuning" in artifact_files
        assert "body_teacher_reviews" in artifact_files
        assert "console_snapshot" in artifact_files
        assert "body_telemetry" in artifact_files
        assert "serial_failure_summary" in artifact_files
        assert "serial_request_response_history" in artifact_files
        assert Path(artifact_files["body_command_audits"]).exists()
        assert Path(artifact_files["body_motion_report_index"]).exists()
        assert Path(artifact_files["body_semantic_tuning"]).exists()
        assert Path(artifact_files["body_teacher_reviews"]).exists()
        assert Path(artifact_files["console_snapshot"]).exists()
        assert Path(artifact_files["body_telemetry"]).exists()
        assert Path(artifact_files["serial_failure_summary"]).exists()
        assert Path(artifact_files["serial_request_response_history"]).exists()


def test_operator_snapshot_includes_runtime_and_edge_state(brain_client):
    response = brain_client.get("/api/operator/snapshot")
    assert response.status_code == 200
    body = response.json()
    assert body["runtime"]["dialogue_backend"] == "rule_based"
    assert body["runtime"]["perception_provider_mode"] == "native_camera_snapshot"
    assert body["runtime"]["backend_profile"] == "companion_live"
    assert body["runtime"]["resolved_backend_profile"] == "companion_live"
    assert body["runtime"]["text_backend"] == "rule_based"
    assert body["runtime"]["vision_backend"] == "native_camera_snapshot"
    assert body["runtime"]["embedding_backend"] == "hash_embed"
    assert body["runtime"]["stt_backend"] == "typed_input"
    assert body["runtime"]["tts_backend"] == "stub_tts"
    assert {item["kind"]: item["status"] for item in body["runtime"]["backend_status"]} == {
        "text_reasoning": "warm",
        "vision_analysis": "degraded",
        "embeddings": "fallback_active",
        "speech_to_text": "degraded",
        "text_to_speech": "degraded",
    }
    assert body["runtime"]["edge_transport_mode"] == "in_process"
    assert body["runtime"]["edge_transport_state"] == "healthy"
    assert body["runtime"]["runtime_mode"] == "desktop_virtual_body"
    assert body["runtime"]["body_driver_mode"] == "virtual"
    assert body["runtime"]["embodiment_profile"] == "virtual_body"
    assert body["runtime"]["profile_summary"] == "companion_live + virtual_body"
    assert body["runtime"]["provider_status"] == "hybrid_local_fallback"
    assert [item["kind"] for item in body["runtime"]["device_health"]] == ["microphone", "speaker", "camera"]
    assert body["runtime"]["perception_freshness"]["status"] == "idle"
    assert body["runtime"]["perception_freshness"]["freshness"] == "unknown"
    assert body["runtime"]["perception_freshness"]["watcher"]["status"] == "idle"
    assert body["runtime"]["perception_freshness"]["semantic"]["status"] == "idle"
    assert body["runtime"]["memory_status"]["status"] == "idle"
    assert body["runtime"]["memory_status"]["relationship_continuity"]["known_user"] is False
    assert body["runtime"]["memory_status"]["relationship_continuity"]["open_follow_ups"] == []
    assert body["runtime"]["social_runtime_mode"] == "idle"
    assert body["runtime"]["grounded_scene_references"] == []
    assert body["runtime"]["watcher_buffer_count"] >= 0
    assert body["runtime"]["fallback_state"]["active"] is True
    assert "embeddings:hash_embed" in body["runtime"]["fallback_state"]["fallback_backends"]
    assert body["runtime"]["agent_runtime_enabled"] is True
    assert body["runtime"]["action_plane"]["enabled"] is True
    assert {item["connector_id"] for item in body["runtime"]["action_plane"]["connector_health"]} == {
        "memory_local",
        "incident_local",
        "browser_runtime",
        "reminders_local",
        "notes_local",
        "local_files",
        "calendar_local",
        "mcp_adapter",
    }
    assert "wayfinding" in body["runtime"]["registered_skills"]
    assert set(body["runtime"]["registered_hooks"]) >= {
        "before_skill_selection",
        "after_transcript",
        "after_perception",
        "before_tool_call",
        "after_tool_result",
        "before_reply",
        "before_reply_generation",
        "before_speak",
        "after_turn",
        "on_failure",
        "on_safe_idle",
        "on_provider_failure",
        "on_session_close",
    }
    assert set(body["runtime"]["registered_tools"]) >= {
        "device_health_snapshot",
        "memory_status",
        "system_health",
        "search_memory",
        "search_venue_knowledge",
        "query_calendar",
        "query_local_files",
        "body_preview",
        "capture_scene",
        "world_model_runtime",
        "request_operator_help",
        "require_confirmation",
        "local_notes",
        "personal_reminders",
        "today_context",
        "recent_session_digest",
    }
    assert "dialogue_planner" in body["runtime"]["specialist_roles"]
    assert "dialogue_planner" in body["runtime"]["registered_subagents"]
    assert body["telemetry"]["mode"] == "desktop_virtual_body"
    assert "command_history" in body
    assert "trace_summaries" in body
    assert "latest_perception" in body
    assert "perception_history" in body
    assert "scene_observer_events" in body
    assert "shift_supervisor" in body
    assert "shift_metrics" in body
    assert "shift_transitions" in body
    assert "venue_operations" in body
    assert "participant_router" in body
    assert "open_incidents" in body
    assert "closed_incidents" in body
    assert "recent_shift_reports" in body


def test_action_plane_operator_endpoints_roundtrip(brain_client):
    created = brain_client.post("/api/sessions", json={"session_id": "action-plane-console", "user_id": "visitor-1"})
    assert created.status_code == 200

    operator_console = brain_client.app.state.operator_console
    agent_runtime = operator_console.orchestrator.agent_runtime
    tool_context = operator_console._build_action_plane_tool_context()
    spec = agent_runtime.tool_registry.resolve_spec("request_operator_help")
    input_model = spec.input_model.model_validate(
        {"participant_summary": "visitor needs human help", "note": "operator endpoint test"}
    )
    pending = agent_runtime.action_gateway.invoke(
        tool_name="request_operator_help",
        requested_tool_name="request_operator_help",
        input_model=input_model,
        handler_context=tool_context,
        invocation=ActionInvocationContext(
            session_id=tool_context.session.session_id,
            run_id="operator-action-plane-test",
            context_mode=tool_context.context_mode.value,
            body_mode=tool_context.body_driver_mode,
            invocation_origin=ActionInvocationOrigin.USER_TURN,
        ),
    )
    action_id = pending.execution.action_id

    status = brain_client.get("/api/operator/action-plane/status")
    assert status.status_code == 200
    assert status.json()["enabled"] is True

    connectors = brain_client.get("/api/operator/action-plane/connectors")
    assert connectors.status_code == 200
    connector_ids = {item["connector_id"] for item in connectors.json()["items"]}
    assert "notes_local" in connector_ids
    assert "local_files" in connector_ids

    approvals = brain_client.get("/api/operator/action-plane/approvals")
    assert approvals.status_code == 200
    assert any(item["action_id"] == action_id for item in approvals.json()["items"])

    overview = brain_client.get(
        "/api/operator/action-plane/overview",
        params={"session_id": "action-plane-console"},
    )
    assert overview.status_code == 200
    overview_body = overview.json()
    assert overview_body["status"]["pending_approval_count"] >= 1
    assert overview_body["attention_items"]
    assert any(item["action_id"] == action_id for item in overview_body["approvals"])
    approval_attention = next(item for item in overview_body["attention_items"] if item["action_id"] == action_id)
    assert "operator-sensitive write" in approval_attention["summary"]
    assert "approve or reject" in approval_attention["next_step_hint"].lower()

    approved = brain_client.post(
        f"/api/operator/action-plane/approvals/{action_id}/approve",
        json={"action_id": action_id, "operator_note": "approved in test"},
    )
    assert approved.status_code == 200
    assert approved.json()["approval_state"] == "approved"
    assert approved.json()["execution"]["status"] == "executed"
    assert approved.json()["execution"]["operator_summary"]
    assert approved.json()["execution"]["next_step_hint"]

    history = brain_client.get("/api/operator/action-plane/history", params={"limit": 20})
    assert history.status_code == 200
    assert any(item["action_id"] == action_id for item in history.json()["items"])

    replay = brain_client.post("/api/operator/action-plane/replay", json={"action_id": action_id})
    assert replay.status_code == 200
    assert replay.json()["status"] == "executed"
    assert replay.json()["action_id"] != action_id


def test_action_plane_browser_operator_endpoints_with_stub_backend(tmp_path: Path):
    with _build_appliance_client(
        tmp_path,
        blink_action_plane_browser_backend="stub",
        blink_action_plane_browser_storage_dir=str(tmp_path / "runtime" / "actions" / "browser"),
    ) as client:
        _bootstrap_appliance_session(client)
        created = client.post("/api/sessions", json={"session_id": "browser-console", "user_id": "visitor-1"})
        assert created.status_code == 200

        task = client.post(
            "/api/operator/action-plane/browser/task",
            json={
                "session_id": "browser-console",
                "query": "Open example.com",
                "target_url": "https://example.com",
                "requested_action": "open_url",
            },
        )
        assert task.status_code == 200
        task_body = task.json()
        assert task_body["status"] == "ok"
        assert task_body["supported"] is True
        assert task_body["snapshot"]["screenshot_path"]

        type_text = client.post(
            "/api/operator/action-plane/browser/task",
            json={
                "session_id": "browser-console",
                "query": "Type into the search field",
                "requested_action": "type_text",
                "target_hint": {"label": "Search"},
                "text_input": "Blink concierge",
            },
        )
        assert type_text.status_code == 200
        assert type_text.json()["status"] == "ok"
        assert type_text.json()["result"]["resolved_target"]["label"] == "Search"

        status = client.get("/api/operator/action-plane/browser/status", params={"session_id": "browser-console"})
        assert status.status_code == 200
        status_body = status.json()
        assert status_body["supported"] is True
        assert status_body["configured"] is True
        assert status_body["active_session"]["current_url"] == "https://example.com"
        assert status_body["latest_snapshot"]["screenshot_data_url"].startswith("data:image/png;base64,")


def test_action_plane_workflow_operator_endpoints_roundtrip(tmp_path: Path):
    with _build_appliance_client(
        tmp_path,
        blink_action_plane_browser_backend="stub",
        blink_action_plane_browser_storage_dir=str(tmp_path / "runtime" / "actions" / "browser"),
    ) as client:
        _bootstrap_appliance_session(client)
        created = client.post("/api/sessions", json={"session_id": "workflow-console", "user_id": "visitor-1"})
        assert created.status_code == 200

        catalog = client.get("/api/operator/action-plane/workflows")
        assert catalog.status_code == 200
        workflow_ids = {item["workflow_id"] for item in catalog.json()["items"]}
        assert {
            "capture_note_and_reminder",
            "morning_briefing",
            "event_lookup_and_open_page",
            "reminder_due_follow_up",
        } <= workflow_ids

        started = client.post(
            "/api/operator/action-plane/workflows/start",
            json={
                "workflow_id": "capture_note_and_reminder",
                "session_id": "workflow-console",
                "inputs": {
                    "note_content": "remember the lobby flow",
                    "reminder_text": "prep concierge badge",
                },
            },
        )
        assert started.status_code == 200
        started_body = started.json()
        assert started_body["status"] == "completed"

        runs = client.get("/api/operator/action-plane/workflows/runs", params={"session_id": "workflow-console"})
        assert runs.status_code == 200
        assert any(item["workflow_run_id"] == started_body["workflow_run_id"] for item in runs.json()["items"])

        run_detail = client.get(f"/api/operator/action-plane/workflows/runs/{started_body['workflow_run_id']}")
        assert run_detail.status_code == 200
        assert run_detail.json()["status"] == "completed"

        operator_console = client.app.state.operator_console
        runtime = operator_console.orchestrator.agent_runtime
        user_context = operator_console._build_action_plane_tool_context(
            session_id="workflow-console",
            invocation_origin=ActionInvocationOrigin.USER_TURN,
        )
        pending = runtime.start_action_plane_workflow(
            request=runtime.tool_registry.resolve_spec("start_workflow").input_model.model_validate(
                {
                    "workflow_id": "event_lookup_and_open_page",
                    "session_id": "workflow-console",
                    "inputs": {
                        "target_url": "https://example.com",
                        "requested_action": "type_text",
                        "target_hint": {"label": "Search"},
                        "text_input": "workflow operator test",
                    },
                }
            ),
            tool_context=user_context,
        )
        assert pending.status.value == "waiting_for_approval"

        snapshot = client.get("/api/operator/snapshot", params={"session_id": "workflow-console"})
        assert snapshot.status_code == 200
        assert snapshot.json()["runtime"]["action_plane"]["waiting_workflow_count"] >= 1

        pause = client.post(
            f"/api/operator/action-plane/workflows/runs/{pending.workflow_run_id}/pause",
            json={"note": "pause in test"},
        )
        assert pause.status_code == 200
        assert pause.json()["status"] == "paused"
        assert pause.json()["paused"] is True


def test_operator_text_turn_updates_transcript_and_command_log(brain_client):
    response = brain_client.post(
        "/api/operator/text-turn",
        json={
            "session_id": "console-session",
            "input_text": "Where is the front desk?",
            "voice_mode": "stub_demo",
            "speak_reply": True,
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["interaction_type"] == "voice_turn"
    assert body["event"]["event_type"] == "speech_transcript"
    assert "Front Desk" in body["response"]["reply_text"]
    assert body["voice_output"]["status"] == "simulated"
    assert body["command_acks"]
    assert body["latency_ms"] >= 0.0
    assert body["live_turn_diagnostics"]["stt_ms"] is not None
    assert body["live_turn_diagnostics"]["reasoning_ms"] is not None
    assert body["live_turn_diagnostics"]["tts_start_ms"] is not None
    assert body["live_turn_diagnostics"]["end_to_end_turn_ms"] is not None

    session = brain_client.get("/api/sessions/console-session")
    assert session.status_code == 200
    assert session.json()["transcript"][0]["event_type"] == "speech_transcript"
    assert session.json()["transcript"][0]["source"] == "operator_console"


def test_operator_snapshot_surfaces_last_agent_skill_tool_calls_and_validations(brain_client):
    response = brain_client.post(
        "/api/operator/text-turn",
        json={
            "session_id": "console-agent-runtime",
            "input_text": "Where is the front desk?",
            "voice_mode": "stub_demo",
            "speak_reply": False,
        },
    )
    assert response.status_code == 200

    snapshot = brain_client.get("/api/operator/snapshot", params={"session_id": "console-agent-runtime"})
    assert snapshot.status_code == 200
    body = snapshot.json()
    assert body["runtime"]["last_active_skill"]["skill_name"] == "wayfinding"
    assert body["runtime"]["active_playbook"] == "community_concierge"
    assert body["runtime"]["active_playbook_variant"] == "wayfinding"
    assert {item["tool_name"] for item in body["runtime"]["last_tool_calls"]} >= {
        "search_venue_knowledge",
        "device_health_snapshot",
        "system_health",
        "body_preview",
    }
    assert any(item["validator_name"] == "reply_review_policy" for item in body["runtime"]["last_validation_outcomes"])
    assert any(item["role_name"] == "dialogue_planner" for item in body["runtime"]["last_role_decisions"])
    assert body["runtime"]["run_id"] is not None
    assert body["runtime"]["checkpoint_count"] >= 0


def test_operator_run_endpoints_support_replay_and_resume(brain_client):
    response = brain_client.post(
        "/api/operator/text-turn",
        json={
            "session_id": "operator-run-surface",
            "input_text": "Note that the front desk opens early tomorrow.",
            "voice_mode": "stub_demo",
            "speak_reply": False,
        },
    )
    assert response.status_code == 200

    runs = brain_client.get("/api/operator/runs", params={"session_id": "operator-run-surface"})
    assert runs.status_code == 200
    run = runs.json()["items"][0]
    assert run["active_skill"] == "note_and_recall"

    checkpoints = brain_client.get(f"/api/operator/runs/{run['run_id']}/checkpoints")
    assert checkpoints.status_code == 200
    assert checkpoints.json()["items"]
    checkpoint_id = checkpoints.json()["items"][0]["checkpoint_id"]

    export = brain_client.get(f"/api/operator/runs/{run['run_id']}/export")
    assert export.status_code == 200
    assert export.json()["artifact"]["run"]["run_id"] == run["run_id"]
    assert export.json()["artifact"]["artifact_path"]

    replay = brain_client.post(f"/api/operator/runs/{run['run_id']}/replay")
    assert replay.status_code == 200
    assert replay.json()["replayed_from_run_id"] == run["run_id"]

    resume = brain_client.post(f"/api/operator/checkpoints/{checkpoint_id}/resume")
    assert resume.status_code == 200
    assert resume.json()["resumed_from_checkpoint_id"] == checkpoint_id


def test_operator_snapshot_surfaces_companion_memory_and_perception_status(brain_client):
    scene = brain_client.post(
        "/api/operator/investor-scenes/natural_discussion/run",
        json={"session_id": "companion-console", "voice_mode": "stub_demo", "speak_reply": False},
    )
    assert scene.status_code == 200

    observe = brain_client.post(
        "/api/operator/investor-scenes/observe_and_comment/run",
        json={"session_id": "companion-console", "voice_mode": "stub_demo", "speak_reply": False},
    )
    assert observe.status_code == 200

    remember = brain_client.post(
        "/api/operator/investor-scenes/companion_memory_follow_up/run",
        json={"session_id": "companion-console", "voice_mode": "stub_demo", "speak_reply": False},
    )
    assert remember.status_code == 200

    snapshot = brain_client.get("/api/operator/snapshot", params={"session_id": "companion-console"})
    assert snapshot.status_code == 200
    body = snapshot.json()
    assert body["runtime"]["memory_status"]["status"] == "grounded"
    assert body["runtime"]["memory_status"]["profile_memory_available"] is True
    assert body["runtime"]["memory_status"]["profile_preference_count"] >= 1
    assert body["runtime"]["memory_status"]["relationship_continuity"]["known_user"] is True
    assert body["runtime"]["memory_status"]["relationship_continuity"]["display_name"] == "Alex"
    assert body["runtime"]["perception_freshness"]["status"] in {"fresh", "aging"}
    assert body["runtime"]["perception_freshness"]["tier"] in {"semantic", "watcher"}
    assert body["runtime"]["perception_freshness"]["source_kind"] in {
        "manual_annotations",
        "video_file_replay",
        "image_fixture",
    }
    assert body["runtime"]["social_runtime_mode"] in {
        "monitoring",
        "greeting",
        "listening",
        "thinking",
        "speaking",
        "follow_up_waiting",
        "degraded_awareness",
    }
    assert body["runtime"]["last_active_skill"]["skill_name"] in {"memory_follow_up", "general_conversation"}


def test_operator_snapshot_keeps_perception_session_scoped(brain_client):
    observe = brain_client.post(
        "/api/operator/investor-scenes/observe_and_comment/run",
        json={"session_id": "seeded-visual-session", "voice_mode": "stub_demo", "speak_reply": False},
    )
    assert observe.status_code == 200

    created = brain_client.post("/api/sessions", json={"session_id": "fresh-terminal-session"})
    assert created.status_code == 200

    snapshot = brain_client.get("/api/operator/snapshot", params={"session_id": "fresh-terminal-session"})
    assert snapshot.status_code == 200
    body = snapshot.json()
    assert body["latest_perception"] is None
    assert body["runtime"]["perception_freshness"]["status"] == "idle"
    assert body["runtime"]["perception_freshness"]["freshness"] == "unknown"
    assert body["runtime"]["perception_freshness"]["semantic"]["status"] == "idle"


def test_browser_live_state_update_is_visible_in_snapshot(brain_client):
    update = brain_client.post(
        "/api/operator/voice/state",
        json={
            "session_id": "browser-live-session",
            "voice_mode": "browser_live",
            "status": "listening",
            "message": "browser_microphone_active",
            "input_backend": "browser_microphone",
            "transcription_backend": "browser_speech_recognition",
            "output_backend": "stub_tts",
        },
    )
    assert update.status_code == 200
    assert update.json()["status"] == "listening"
    assert update.json()["can_listen"] is True

    snapshot = brain_client.get("/api/operator/snapshot?session_id=browser-live-session&voice_mode=browser_live")
    assert snapshot.status_code == 200
    body = snapshot.json()
    assert body["voice_state"]["status"] == "listening"
    assert body["voice_state"]["input_backend"] == "browser_microphone"


def test_browser_live_transcript_turn_uses_same_session_trace_path(brain_client):
    response = brain_client.post(
        "/api/operator/text-turn",
        json={
            "session_id": "browser-live-session",
            "input_text": "Where is the front desk?",
            "voice_mode": "browser_live",
            "speak_reply": False,
            "source": "browser_speech_recognition",
            "input_metadata": {
                "capture_mode": "browser_microphone",
                "transcription_backend": "browser_speech_recognition",
                "confidence": 0.88,
            },
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["interaction_type"] == "voice_turn"
    assert body["event"]["source"] == "browser_speech_recognition"
    assert body["event"]["payload"]["transcription_backend"] == "browser_speech_recognition"
    assert body["voice_output"]["status"] == "skipped"
    assert body["voice_output"]["transcript_text"] == "Where is the front desk?"
    assert body["live_turn_diagnostics"]["source"] == "browser_speech_recognition"
    assert body["live_turn_diagnostics"]["visual_query"] is False
    assert body["live_turn_diagnostics"]["stt_ms"] is not None
    assert body["live_turn_diagnostics"]["reasoning_ms"] is not None

    trace = brain_client.get(f"/api/traces/{body['response']['trace_id']}")
    assert trace.status_code == 200
    trace_body = trace.json()
    assert trace_body["event"]["payload"]["confidence"] == 0.88
    assert trace_body["reasoning"]["live_turn_diagnostics"]["source"] == "browser_speech_recognition"

    session = brain_client.get("/api/sessions/browser-live-session")
    assert session.status_code == 200
    assert session.json()["transcript"][0]["source"] == "browser_speech_recognition"

    snapshot = brain_client.get("/api/operator/snapshot?session_id=browser-live-session&voice_mode=browser_live")
    assert snapshot.status_code == 200
    assert snapshot.json()["runtime"]["latest_live_turn_diagnostics"]["source"] == "browser_speech_recognition"


def test_operator_can_force_safe_idle(brain_client):
    response = brain_client.post("/api/operator/safe-idle", params={"session_id": "console-safe"})
    assert response.status_code == 200
    body = response.json()
    assert body["outcome"] == "safe_fallback"
    assert body["heartbeat"]["safe_idle_active"] is True
    assert body["latency_ms"] >= 0.0


def test_operator_can_cancel_voice_stub_mode(brain_client):
    response = brain_client.post(
        "/api/operator/voice/cancel",
        params={"session_id": "console-session", "voice_mode": "stub_demo"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["state"]["status"] == "interrupted"


def test_investor_scene_catalog_and_memory_followup(brain_client):
    catalog = brain_client.get("/api/operator/investor-scenes")
    assert catalog.status_code == 200
    assert {item["scene_name"] for item in catalog.json()["items"]} >= {
        "greeting_presence",
        "attentive_listening",
        "wayfinding_usefulness",
        "venue_helpful_question",
        "natural_discussion",
        "observe_and_comment",
        "companion_memory_follow_up",
        "knowledge_grounded_help",
        "safe_degraded_behavior",
        "memory_followup",
        "operator_escalation",
        "safe_fallback_failure",
        "approach_and_greet",
        "read_visible_sign_and_answer",
        "remember_person_context_across_turns",
        "detect_disengagement_and_shorten_reply",
        "escalate_after_confusion_or_accessibility_request",
        "perception_unavailable_honest_fallback",
        "two_person_attention_handoff",
        "disengagement_shortening",
        "scene_grounded_comment",
        "uncertainty_admission",
        "stale_scene_suppression",
        "operator_correction_after_wrong_scene_interpretation",
    }

    first = brain_client.post(
        "/api/operator/investor-scenes/wayfinding_usefulness/run",
        json={"session_id": "investor-main", "voice_mode": "stub_demo"},
    )
    assert first.status_code == 200
    assert first.json()["success"] is True

    follow_up = brain_client.post(
        "/api/operator/investor-scenes/memory_followup/run",
        json={"session_id": "investor-main", "voice_mode": "stub_demo"},
    )
    assert follow_up.status_code == 200
    body = follow_up.json()
    assert body["success"] is True
    assert "Workshop Room" in body["items"][0]["response"]["reply_text"]


def test_local_companion_story_scenes_pass_with_stub_voice(brain_client):
    scene_names = [
        "natural_discussion",
        "observe_and_comment",
        "companion_memory_follow_up",
        "knowledge_grounded_help",
        "safe_degraded_behavior",
    ]

    for scene_name in scene_names:
        response = brain_client.post(
            f"/api/operator/investor-scenes/{scene_name}/run",
            json={"voice_mode": "stub_demo", "speak_reply": False},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["success"] is True
        assert body["scorecard"]["passed"] is True


def test_multimodal_scene_returns_scorecard_and_replay_evidence(brain_client):
    response = brain_client.post(
        "/api/operator/investor-scenes/read_visible_sign_and_answer/run",
        json={"session_id": "investor-multimodal", "voice_mode": "stub_demo", "speak_reply": False},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["perception_snapshots"]
    assert body["scorecard"]["passed"] is True
    assert body["scorecard"]["score"] >= 2.0
    assert body["final_action"]["reply_text"]
    assert "Workshop Room" in body["final_action"]["reply_text"]
    assert body["grounding_sources"]


def test_stage_c_multimodal_scenes_surface_policy_and_operator_override(brain_client):
    stale = brain_client.post(
        "/api/operator/investor-scenes/stale_scene_suppression/run",
        json={"session_id": "investor-stale-scene", "voice_mode": "stub_demo", "speak_reply": False},
    )
    assert stale.status_code == 200
    stale_body = stale.json()
    assert stale_body["success"] is True
    assert stale_body["scorecard"]["passed"] is True
    assert any(
        item["policy_outcome"] == "stale_scene_suppressed"
        for item in stale_body["executive_decisions"]
    )

    corrected = brain_client.post(
        "/api/operator/investor-scenes/operator_correction_after_wrong_scene_interpretation/run",
        json={"session_id": "investor-operator-correction", "voice_mode": "stub_demo", "speak_reply": False},
    )
    assert corrected.status_code == 200
    corrected_body = corrected.json()
    assert corrected_body["success"] is True
    assert corrected_body["scorecard"]["passed"] is True
    assert "Workshop Room" in (corrected_body["final_action"]["reply_text"] or "")
    assert any(
        source.get("claim_kind") == "operator_annotation"
        for source in corrected_body["grounding_sources"]
    )

def test_operator_teacher_memory_and_benchmark_endpoints_roundtrip(brain_client):
    scene = brain_client.post(
        "/api/operator/investor-scenes/natural_discussion/run",
        json={"session_id": "episode-teacher", "voice_mode": "stub_demo", "speak_reply": False},
    )
    assert scene.status_code == 200

    exported = brain_client.post(
        "/api/operator/episodes/export-session",
        json={"session_id": "episode-teacher", "include_asset_refs": True},
    )
    assert exported.status_code == 200
    episode = exported.json()
    assert episode["schema_version"] == "blink_episode/v2"

    episode_review = brain_client.post(
        f"/api/operator/episodes/{episode['episode_id']}/teacher",
        json={
            "review_value": "good",
            "label": "scene_grounding",
            "note": "Grounded answer looked solid.",
            "author": "operator_console",
            "outcome_label": "completed",
            "benchmark_tags": ["scene_grounding"],
        },
    )
    assert episode_review.status_code == 200
    assert episode_review.json()["scope"] == "episode"

    teacher_list = brain_client.get(f"/api/operator/episodes/{episode['episode_id']}/teacher")
    assert teacher_list.status_code == 200
    assert teacher_list.json()["items"][0]["scope"] == "episode"

    trace_id = episode["traces"][-1]["trace_id"]
    trace_review = brain_client.post(
        f"/api/operator/traces/{trace_id}/teacher/review",
        json={
            "review_value": "needs_revision",
            "note": "A shorter reply would be better here.",
            "author": "operator_console",
            "better_reply_text": "Shorter reply.",
        },
    )
    assert trace_review.status_code == 200
    assert trace_review.json()["scope"] == "trace"

    run_id = episode["run_ids"][0]
    run_review = brain_client.post(
        f"/api/operator/runs/{run_id}/teacher",
        json={
            "review_value": "good",
            "author": "operator_console",
            "label": "memory_followup",
            "memory_feedback": {"action": "needs_review"},
        },
    )
    assert run_review.status_code == 200
    assert run_review.json()["scope"] == "run"

    run_teacher_list = brain_client.get(f"/api/operator/runs/{run_id}/teacher")
    assert run_teacher_list.status_code == 200
    assert run_teacher_list.json()["items"][0]["run_id"] == run_id

    memory_action = next((item for item in episode["memory_actions"] if item["layer"] in {"episodic", "semantic"}), None)
    assert memory_action is not None
    review = brain_client.post(
        "/api/operator/memory/review",
        json={
            "memory_id": memory_action["memory_id"],
            "layer": memory_action["layer"],
            "note": "Keep this memory.",
            "author": "operator_console",
        },
    )
    assert review.status_code == 200
    assert review.json()["status"] == "approved"

    retrievals = brain_client.get("/api/operator/memory/retrievals", params={"session_id": "episode-teacher"})
    assert retrievals.status_code == 200
    assert "items" in retrievals.json()

    review_debt = brain_client.get("/api/operator/memory/review-debt")
    assert review_debt.status_code == 200
    assert "pending_count" in review_debt.json()

    benchmark_catalog = brain_client.get("/api/operator/benchmarks")
    assert benchmark_catalog.status_code == 200
    assert "perception_world_model_freshness" in benchmark_catalog.json()["families"]

    planners = brain_client.get("/api/operator/planners")
    assert planners.status_code == 200
    planner_ids = {item["planner_id"] for item in planners.json()["items"]}
    assert {"agent_os_current", "deterministic_baseline"} <= planner_ids

    research_export = brain_client.post(
        f"/api/operator/episodes/{episode['episode_id']}/export-research",
        json={"formats": ["native", "lerobot_like"]},
    )
    assert research_export.status_code == 200
    research_body = research_export.json()
    assert research_body["schema_version"] == "blink_research_bundle/v1"
    assert Path(research_body["artifact_files"]["manifest"]).exists()
    assert Path(research_body["adapter_exports"]["lerobot_like"]).exists()

    dataset_export = brain_client.post(
        "/api/operator/datasets/export",
        json={
            "name": "operator_stage_d_dataset",
            "episode_ids": [episode["episode_id"]],
        },
    )
    assert dataset_export.status_code == 200
    dataset_body = dataset_export.json()
    assert dataset_body["schema_version"] == "blink_dataset_manifest/v1"

    dataset_list = brain_client.get("/api/operator/datasets")
    assert dataset_list.status_code == 200
    assert dataset_list.json()["items"][0]["dataset_id"] == dataset_body["dataset_id"]

    dataset_detail = brain_client.get(f"/api/operator/datasets/{dataset_body['dataset_id']}")
    assert dataset_detail.status_code == 200
    assert dataset_detail.json()["dataset_id"] == dataset_body["dataset_id"]

    replay = brain_client.post(
        "/api/operator/replays/episode",
        json={
            "episode_id": episode["episode_id"],
            "planner_id": "deterministic_baseline",
            "planner_profile": "default",
            "replay_mode": "strict",
            "comparison_mode": "episode_vs_replay",
        },
    )
    assert replay.status_code == 200
    replay_body = replay.json()
    assert replay_body["planner_id"] == "deterministic_baseline"
    assert replay_body["step_count"] >= 1
    assert Path(replay_body["artifact_files"]["replay"]).exists()

    replay_detail = brain_client.get(f"/api/operator/replays/{replay_body['replay_id']}")
    assert replay_detail.status_code == 200
    assert replay_detail.json()["replay_id"] == replay_body["replay_id"]

    benchmark_run = brain_client.post(
        "/api/operator/benchmarks/run",
        json={
            "episode_id": episode["episode_id"],
            "planner_id": "deterministic_baseline",
            "planner_profile": "default",
            "comparison_planners": ["agent_os_current"],
            "comparison_mode": "episode_vs_replay",
            "replay_mode": "strict",
            "families": [
                "scene_grounding",
                "memory_correctness",
                "episode_export_validity",
                "planner_swap_compatibility",
                "replay_determinism",
            ],
        },
    )
    assert benchmark_run.status_code == 200
    benchmark_body = benchmark_run.json()
    assert benchmark_body["episode_id"] == episode["episode_id"]
    assert benchmark_body["artifact_files"]["run"]
    assert benchmark_body["planner_id"] == "deterministic_baseline"
    assert benchmark_body["replay_id"]
    assert benchmark_body["artifact_files"]["research_manifest"]
    assert benchmark_body["evidence_pack_manifest"]

    evidence_list = brain_client.get("/api/operator/benchmarks/evidence")
    assert evidence_list.status_code == 200
    assert any(item["pack_id"] == benchmark_body["evidence_pack_id"] for item in evidence_list.json()["items"])
