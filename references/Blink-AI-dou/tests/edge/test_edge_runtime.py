from __future__ import annotations

from datetime import timedelta

from fastapi.testclient import TestClient

from embodied_stack.config import Settings
from embodied_stack.edge.app import create_app as create_edge_app
from embodied_stack.edge.controller import SimulatedRobotController
from embodied_stack.edge.drivers import FakeRobotDriver, JetsonDriverStub, JetsonHardwareDriver
from embodied_stack.shared.models import CommandType, RobotCommand, SimulatedSensorEventRequest


def test_edge_health(edge_client):
    response = edge_client.get("/health")
    assert response.status_code == 200
    assert response.json()["service"] == "edge"


def test_edge_readiness_reports_fake_profile_ready(edge_client):
    response = edge_client.get("/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["runtime_profile"] == "fake_robot_full"


def test_simulated_sensor_event_and_telemetry_log(edge_client):
    response = edge_client.post(
        "/api/sim/events",
        json={
            "event_type": "speech_transcript",
            "session_id": "edge-session",
            "payload": {"text": "Hello from the edge"},
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["event"]["event_type"] == "speech_transcript"
    assert body["telemetry"]["last_sensor_event_type"] == "speech_transcript"

    log = edge_client.get("/api/telemetry/log")
    assert log.status_code == 200
    assert len(log.json()["items"]) >= 2


def test_network_state_forces_safe_idle(edge_client):
    response = edge_client.post(
        "/api/sim/events",
        json={
            "event_type": "network_state",
            "session_id": "edge-session",
            "payload": {"network_ok": False, "latency_ms": 900.0},
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["event"]["event_type"] == "heartbeat"
    assert body["heartbeat"]["safe_idle_active"] is True

    telemetry = edge_client.get("/api/telemetry").json()
    assert telemetry["mode"] == "degraded_safe_idle"
    assert telemetry["safe_idle_reason"] == "network_degraded"


def test_low_battery_and_safe_idle_head_pose_rejection(edge_client):
    edge_client.post(
        "/api/sim/events",
        json={"event_type": "low_battery", "payload": {"battery_pct": 10.0}},
    )
    response = edge_client.post(
        "/api/commands",
        json={"command_type": "set_head_pose", "payload": {"head_yaw_deg": 10.0, "head_pitch_deg": 0.0}},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["accepted"] is False
    assert body["reason"] == "safe_idle_rejects_head_pose"


def test_driver_timeout_and_stub_landing_zone():
    driver = FakeRobotDriver(heartbeat_timeout_seconds=5.0)
    future = driver.heartbeat.last_contact_at + timedelta(seconds=10)
    heartbeat = driver.get_heartbeat(now=future)
    assert heartbeat.safe_idle_active is True
    assert heartbeat.safe_idle_reason == "heartbeat_timeout"

    stub = JetsonDriverStub()
    assert stub.get_telemetry().mode == "hardware"


def test_fake_driver_reports_adapter_boundaries():
    driver = FakeRobotDriver()
    telemetry = driver.get_telemetry()
    capabilities = driver.capabilities

    assert capabilities.runtime_profile == "fake_robot_full"
    assert capabilities.supports_button_sensor is True
    assert capabilities.supports_battery_monitor is True
    assert any(adapter.kind == "speaker_trigger" for adapter in capabilities.adapters)
    assert any(adapter.state == "simulated" for adapter in telemetry.adapter_health)


def test_hardware_landing_zone_reports_unwired_adapters_and_rejects_commands(settings):
    driver = JetsonHardwareDriver(profile_name="jetson_landing_zone", heartbeat_timeout_seconds=settings.edge_heartbeat_timeout_seconds)
    controller = SimulatedRobotController(driver=driver, settings=settings)

    capabilities = controller.capabilities
    telemetry = controller.get_telemetry()
    assert capabilities.runtime_profile == "jetson_landing_zone"
    assert capabilities.supports_simulated_events is False
    assert any(adapter.kind == "display" for adapter in capabilities.adapters)
    assert any(adapter.state == "unavailable" for adapter in telemetry.adapter_health)

    command_ack = controller.apply_command(
        RobotCommand(command_type=CommandType.DISPLAY_TEXT, payload={"text": "hello landing zone"})
    )
    assert command_ack.accepted is False
    assert command_ack.reason == "adapter_unavailable:display"


def test_hardware_landing_zone_safe_idle_is_adapter_aware(settings):
    driver = JetsonHardwareDriver(profile_name="jetson_landing_zone", heartbeat_timeout_seconds=settings.edge_heartbeat_timeout_seconds)
    controller = SimulatedRobotController(driver=driver, settings=settings)

    heartbeat = controller.force_safe_idle("operator_override")
    telemetry = controller.get_telemetry()
    assert heartbeat.safe_idle_active is True
    assert telemetry.safe_idle_reason == "operator_override"
    assert telemetry.display_text is None
    assert telemetry.led_color == "off"


def test_hardware_landing_zone_readiness_is_degraded(tmp_path):
    settings = Settings(
        brain_store_path=str(tmp_path / "brain_store.json"),
        demo_report_dir=str(tmp_path / "demo_runs"),
        edge_driver_profile="jetson_landing_zone",
        operator_auth_token="test-operator-token",
    )
    app = create_edge_app(settings=settings)
    with TestClient(app) as client:
        response = client.get("/ready")
        assert response.status_code == 200
        body = response.json()
        assert body["ok"] is False
        checks = {item["name"]: item for item in body["checks"]}
        assert checks["actuator_surface"]["ok"] is False
        assert checks["event_bridge"]["ok"] is False


def test_hardware_simulated_profile_still_supports_brain_contract(settings, orchestrator):
    driver = JetsonHardwareDriver(profile_name="jetson_simulated_io", heartbeat_timeout_seconds=settings.edge_heartbeat_timeout_seconds)
    controller = SimulatedRobotController(driver=driver, settings=settings)

    sim_result = controller.simulate_event(
        SimulatedSensorEventRequest(
            event_type="speech_transcript",
            session_id="jetson-session",
            payload={"text": "Where is the workshop today?"},
        )
    )
    response = orchestrator.handle_event(sim_result.event)
    acks = [controller.apply_command(command) for command in response.commands]

    assert response.reply_text
    assert response.trace_id
    assert acks
    assert all(ack.accepted is True for ack in acks)
    assert controller.get_telemetry().runtime_profile == "jetson_simulated_io"


def test_command_history_is_recorded(edge_client):
    edge_client.post(
        "/api/commands",
        json={"command_type": "display_text", "payload": {"text": "hello"}},
    )
    history = edge_client.get("/api/command-history")
    assert history.status_code == 200
    assert history.json()["items"][0]["command"]["command_type"] == "display_text"


def test_duplicate_command_id_is_not_reapplied(edge_client):
    payload = {"command_id": "dedupe-1", "command_type": "display_text", "payload": {"text": "hello"}}
    first = edge_client.post("/api/commands", json=payload)
    duplicate = edge_client.post("/api/commands", json=payload)

    assert first.status_code == 200
    assert first.json()["status"] == "applied"
    assert duplicate.status_code == 200
    assert duplicate.json()["status"] == "duplicate"
    assert duplicate.json()["attempt_count"] == 2

    history = edge_client.get("/api/command-history")
    assert history.status_code == 200
    assert len(history.json()["items"]) == 1
