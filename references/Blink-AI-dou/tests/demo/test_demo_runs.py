from pathlib import Path


def test_demo_run_persists_report_and_lists(brain_client, settings):
    response = brain_client.post(
        "/api/demo-runs",
        json={"scenario_names": ["welcome_and_wayfinding", "safe_fallback_demo"]},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert body["passed"] is True
    assert len(body["steps"]) == 5
    assert Path(body["report_path"]).exists()
    assert Path(body["artifact_dir"]).is_dir()
    assert Path(body["artifact_files"]["summary"]).exists()
    assert Path(body["artifact_files"]["sessions"]).exists()
    assert Path(body["artifact_files"]["traces"]).exists()
    assert Path(body["artifact_files"]["telemetry_log"]).exists()
    assert Path(body["artifact_files"]["command_history"]).exists()
    assert Path(body["artifact_files"]["perception_snapshots"]).exists()
    assert Path(body["artifact_files"]["world_model_transitions"]).exists()
    assert Path(body["artifact_files"]["shift_transitions"]).exists()
    assert Path(body["artifact_files"]["incidents"]).exists()
    assert Path(body["artifact_files"]["incident_timeline"]).exists()
    assert Path(body["artifact_files"]["executive_decisions"]).exists()
    assert Path(body["artifact_files"]["grounding_sources"]).exists()
    assert Path(body["artifact_files"]["manifest"]).exists()
    assert body["fallback_count"] >= 1
    assert body["metrics"]["step_count"] == 5
    assert body["metrics"]["trace_count"] == 5
    assert body["metrics"]["command_count"] >= 1
    assert body["metrics"]["ack_success_rate"] == 1.0
    assert body["metrics"]["average_executive_latency_ms"] >= 0.0
    assert body["observed_dialogue_backends"]
    assert body["fallback_events"]
    assert body["final_shift_supervisor"]
    assert "final_incidents" in body
    assert body["steps"][0]["backend_used"]
    assert body["steps"][0]["started_at"]
    assert body["steps"][0]["completed_at"]
    assert "latency_breakdown" in body["steps"][0]
    assert "grounding_sources" in body["steps"][0]
    assert "shift_supervisor" in body["steps"][0]
    assert "incident_timeline" in body["steps"][0]

    listing = brain_client.get("/api/demo-runs")
    assert listing.status_code == 200
    assert listing.json()["items"][0]["run_id"] == body["run_id"]

    detail = brain_client.get(f"/api/demo-runs/{body['run_id']}")
    assert detail.status_code == 200
    assert detail.json()["final_world_state"]["last_trace_id"]


def test_reset_clears_runtime_state_and_optionally_reports(brain_client):
    response = brain_client.post("/api/demo-runs", json={"scenario_names": ["welcome_and_wayfinding"]})
    artifact_dir = Path(response.json()["artifact_dir"])
    assert brain_client.get("/api/demo-runs").json()["items"]
    assert artifact_dir.exists()

    reset = brain_client.post(
        "/api/reset",
        json={"reset_edge": True, "clear_user_memory": True, "clear_demo_runs": True},
    )
    assert reset.status_code == 200
    assert reset.json()["edge_reset"] is True
    assert reset.json()["cleared_demo_runs"] is True

    sessions = brain_client.get("/api/sessions")
    assert sessions.status_code == 200
    assert sessions.json()["items"] == []
    assert brain_client.get("/api/demo-runs").json()["items"] == []
    assert not artifact_dir.exists()
