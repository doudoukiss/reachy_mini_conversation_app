from __future__ import annotations

import json

from fastapi.testclient import TestClient

from embodied_stack.brain.app import create_app as create_brain_app
from embodied_stack.brain.orchestrator import BrainOrchestrator
from embodied_stack.config import Settings
from embodied_stack.demo.coordinator import DemoCoordinator
from embodied_stack.desktop.runtime import build_inprocess_embodiment_gateway


def run_smoke() -> None:
    settings = Settings(
        brain_store_path="runtime/smoke_brain_store.json",
        demo_report_dir="runtime/smoke_demo_runs",
        operator_auth_token="smoke-operator-token",
        operator_auth_runtime_file="runtime/smoke_operator_auth.json",
    )
    orchestrator = BrainOrchestrator(settings=settings, store_path=settings.brain_store_path)
    coordinator = DemoCoordinator(
        orchestrator=orchestrator,
        edge_gateway=build_inprocess_embodiment_gateway(settings),
        report_dir=settings.demo_report_dir,
    )
    app = create_brain_app(settings=settings, orchestrator=orchestrator, demo_coordinator=coordinator)

    with TestClient(app) as client:
        login = client.post("/api/operator/auth/login", json={"token": settings.operator_auth_token})
        login.raise_for_status()
        client.post(
            "/api/reset",
            json={"reset_edge": True, "clear_user_memory": True, "clear_demo_runs": True},
        ).raise_for_status()
        response = client.post("/api/demo-runs", json={})
        response.raise_for_status()
        body = response.json()
        summary = {
            "run_id": body["run_id"],
            "status": body["status"],
            "scenario_names": body["scenario_names"],
            "step_count": len(body["steps"]),
            "fallback_count": body["fallback_count"],
            "total_latency_ms": body["total_latency_ms"],
            "trace_count": body["final_world_state"]["trace_count"],
            "report_path": body["report_path"],
        }
        print(json.dumps(summary, indent=2))


def main() -> None:
    run_smoke()


if __name__ == "__main__":
    main()
