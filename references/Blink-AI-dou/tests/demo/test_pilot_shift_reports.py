from pathlib import Path

from embodied_stack.demo.shift_reports import ShiftReportStore
from embodied_stack.demo.shift_simulator import PilotShiftSimulator, load_shift_definition


FIXTURE_PATH = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "embodied_stack"
    / "demo"
    / "pilot_days"
    / "community_center_pilot_day.json"
)


def test_pilot_shift_simulation_persists_report_and_metrics(brain_client, settings, orchestrator, demo_coordinator):
    simulator = PilotShiftSimulator(
        settings=settings,
        orchestrator=orchestrator,
        edge_gateway=demo_coordinator.edge_gateway,
        report_store=ShiftReportStore(settings.shift_report_dir),
    )
    report = simulator.run(load_shift_definition(FIXTURE_PATH))

    assert report.status == "completed"
    assert report.metrics.visitors_greeted >= 1
    assert report.metrics.conversations_started >= 3
    assert report.metrics.conversations_completed >= 2
    assert report.metrics.escalations_created >= 1
    assert report.metrics.escalations_resolved >= 1
    assert report.metrics.average_response_latency_ms >= 0.0
    assert report.metrics.time_spent_degraded_seconds >= 300.0
    assert report.metrics.safe_idle_incident_count >= 1
    assert report.score_summary.max_score >= 1.0
    assert Path(report.artifact_files["summary"]).exists()
    assert Path(report.artifact_files["report"]).exists()
    assert Path(report.artifact_files["shift_steps"]).exists()
    assert Path(report.artifact_files["simulation_definition"]).exists()
    assert Path(report.artifact_files["metrics_csv"]).exists()
    assert Path(report.artifact_files["sessions"]).exists()
    assert Path(report.artifact_files["traces"]).exists()
    assert report.final_world_state is not None
    assert report.final_shift_supervisor is not None
    assert report.final_incidents

    listing = brain_client.get("/api/shift-reports")
    assert listing.status_code == 200
    assert listing.json()["items"][0]["report_id"] == report.report_id

    detail = brain_client.get(f"/api/shift-reports/{report.report_id}")
    assert detail.status_code == 200
    assert detail.json()["metrics"]["visitors_greeted"] >= 1

    snapshot = brain_client.get("/api/operator/snapshot")
    assert snapshot.status_code == 200
    snapshot_body = snapshot.json()
    assert snapshot_body["shift_metrics"]["visitors_greeted"] >= 1
    assert snapshot_body["recent_shift_reports"]["items"][0]["report_id"] == report.report_id


def test_export_shift_report_episode_uses_pilot_report_bundle(brain_client, settings, orchestrator, demo_coordinator):
    simulator = PilotShiftSimulator(
        settings=settings,
        orchestrator=orchestrator,
        edge_gateway=demo_coordinator.edge_gateway,
        report_store=ShiftReportStore(settings.shift_report_dir),
    )
    report = simulator.run(load_shift_definition(FIXTURE_PATH))

    exported = brain_client.post(
        "/api/operator/episodes/export-shift-report",
        json={"report_id": report.report_id, "include_asset_refs": True},
    )
    assert exported.status_code == 200
    body = exported.json()

    assert body["source_type"] == "shift_report"
    assert body["source_id"] == report.report_id
    assert body["scenario_names"] == [report.simulation_name]
    assert body["sessions"]
    assert body["traces"]
    assert body["commands"]
    assert body["acknowledgements"]
    assert body["telemetry"]
    assert body["incidents"]
    assert body["incident_timeline"]
    assert Path(body["artifact_files"]["episode"]).exists()
    assert Path(body["artifact_files"]["telemetry"]).exists()
    assert Path(body["artifact_files"]["manifest"]).exists()
