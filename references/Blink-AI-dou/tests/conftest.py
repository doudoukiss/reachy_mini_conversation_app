from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from embodied_stack.body.serial.live_test_gates import live_serial_motion_tests_enabled, live_serial_tests_enabled
from embodied_stack.brain.app import create_app as create_brain_app
from embodied_stack.brain.orchestrator import BrainOrchestrator
from embodied_stack.config import Settings
from embodied_stack.demo.coordinator import DemoCoordinator
from embodied_stack.desktop.runtime import build_inprocess_embodiment_gateway
from embodied_stack.edge.app import create_app as create_edge_app
from embodied_stack.edge.controller import SimulatedRobotController


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        brain_store_path=str(tmp_path / "brain_store.json"),
        demo_report_dir=str(tmp_path / "demo_runs"),
        shift_report_dir=str(tmp_path / "shift_reports"),
        episode_export_dir=str(tmp_path / "episodes"),
        performance_report_dir=str(tmp_path / "performance_runs"),
        perception_frame_dir=str(tmp_path / "perception_frames"),
        brain_dialogue_backend="rule_based",
        brain_voice_backend="stub",
        edge_heartbeat_timeout_seconds=5.0,
        shift_background_tick_enabled=False,
        operator_auth_token="test-operator-token",
        operator_auth_runtime_file=str(tmp_path / "operator_auth.json"),
        blink_appliance_profile_file=str(tmp_path / "appliance_profile.json"),
        blink_stt_backend="typed_input",
        blink_tts_backend="stub_tts",
        ollama_base_url="http://127.0.0.1:9",
        ollama_timeout_seconds=0.1,
    )


@pytest.fixture
def edge_controller(settings: Settings) -> SimulatedRobotController:
    return SimulatedRobotController(settings=settings)


@pytest.fixture
def edge_client(settings: Settings, edge_controller: SimulatedRobotController):
    app = create_edge_app(settings=settings, controller=edge_controller)
    with TestClient(app) as client:
        yield client


@pytest.fixture
def orchestrator(settings: Settings) -> BrainOrchestrator:
    return BrainOrchestrator(settings=settings, store_path=settings.brain_store_path)


@pytest.fixture
def demo_coordinator(settings: Settings, orchestrator: BrainOrchestrator, edge_controller: SimulatedRobotController) -> DemoCoordinator:
    return DemoCoordinator(
        orchestrator=orchestrator,
        edge_gateway=build_inprocess_embodiment_gateway(settings),
        report_dir=settings.demo_report_dir,
    )


@pytest.fixture
def brain_client(settings: Settings, orchestrator: BrainOrchestrator, demo_coordinator: DemoCoordinator):
    app = create_brain_app(settings=settings, orchestrator=orchestrator, demo_coordinator=demo_coordinator)
    with TestClient(app) as client:
        login = client.post("/api/operator/auth/login", json={"token": settings.operator_auth_token})
        assert login.status_code == 200
        yield client


@pytest.fixture
def unauthenticated_brain_client(settings: Settings, orchestrator: BrainOrchestrator, demo_coordinator: DemoCoordinator):
    app = create_brain_app(settings=settings, orchestrator=orchestrator, demo_coordinator=demo_coordinator)
    with TestClient(app) as client:
        yield client


def pytest_collection_modifyitems(config, items):
    del config
    skip_live = pytest.mark.skip(reason="Set BLINK_RUN_LIVE_SERIAL_TESTS=1 to run live serial hardware tests.")
    skip_motion = pytest.mark.skip(
        reason="Set BLINK_RUN_LIVE_SERIAL_TESTS=1 and BLINK_RUN_LIVE_SERIAL_MOTION_TESTS=1 to run live serial motion tests."
    )
    allow_live = live_serial_tests_enabled()
    allow_motion = live_serial_motion_tests_enabled()
    for item in items:
        if "live_serial_motion" in item.keywords and not allow_motion:
            item.add_marker(skip_motion)
        elif "live_serial" in item.keywords and not allow_live:
            item.add_marker(skip_live)
