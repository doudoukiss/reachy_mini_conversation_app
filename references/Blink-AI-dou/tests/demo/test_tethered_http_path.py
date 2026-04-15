from __future__ import annotations

from pathlib import Path

import httpx

from embodied_stack.demo.tethered import TetheredDemoStack, run_tethered_smoke


def test_tethered_smoke_runs_demo_over_real_http_path(tmp_path):
    summary = run_tethered_smoke(runtime_dir=tmp_path / "tethered-smoke")

    assert summary["edge_transport_mode"] == "http"
    assert summary["edge_transport_state"] == "healthy"
    assert summary["status"] == "completed"
    assert summary["passed"] is True
    assert Path(summary["report_path"]).exists()


def test_operator_snapshot_degrades_cleanly_when_edge_process_stops(tmp_path):
    with TetheredDemoStack(runtime_dir=tmp_path / "tethered-drop") as stack, httpx.Client(timeout=10.0) as client:
        reset = client.post(
            f"{stack.brain_url}/api/reset",
            json={"reset_edge": True, "clear_user_memory": True, "clear_demo_runs": True},
            headers=stack.operator_headers(),
        )
        reset.raise_for_status()

        assert stack.edge is not None
        stack.edge.stop()

        snapshot = client.get(f"{stack.brain_url}/api/operator/snapshot", headers=stack.operator_headers())
        snapshot.raise_for_status()
        body = snapshot.json()

        assert body["runtime"]["edge_transport_mode"] == "http"
        assert body["runtime"]["edge_transport_state"] == "degraded"
        assert body["heartbeat"]["transport_ok"] is False
        assert body["heartbeat"]["safe_idle_active"] is True
        assert body["telemetry"]["transport_ok"] is False
        assert body["telemetry"]["safe_idle_reason"] == "edge_transport_degraded"
