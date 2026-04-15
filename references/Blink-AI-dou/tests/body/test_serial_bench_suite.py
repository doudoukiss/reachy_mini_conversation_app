from __future__ import annotations

import json
from pathlib import Path

from embodied_stack.body import calibration as calibration_module
from embodied_stack.body.serial import bench_suite as bench_suite_module
from embodied_stack.body.serial.evidence import (
    SerialBenchStepRecord,
    build_motion_report_index,
    build_serial_failure_summary,
)
from embodied_stack.shared.contracts._common import utc_now


def _run_bench(args: list[str], capsys) -> tuple[int, dict]:
    exit_code = bench_suite_module.main(args)
    payload = json.loads(capsys.readouterr().out)
    return exit_code, payload


def test_serial_bench_dry_run_writes_stage_e_artifacts(monkeypatch, tmp_path: Path, capsys) -> None:
    motion_report_dir = tmp_path / "runtime" / "serial" / "motion_reports"
    monkeypatch.setattr(calibration_module, "DEFAULT_MOTION_REPORT_DIR", motion_report_dir)
    monkeypatch.setattr(
        bench_suite_module,
        "_collect_console_artifacts",
        lambda args, suite_dir: (
            {"runtime": {"runtime_mode": "desktop_serial_body"}, "suite_dir": str(suite_dir)},
            {"mode": "desktop_serial_body", "transport_ok": True, "args_transport": args.transport},
        ),
    )

    exit_code, payload = _run_bench(
        [
            "--transport",
            "dry_run",
            "--calibration",
            str(tmp_path / "runtime" / "calibrations" / "robot_head_live_v1.json"),
            "--report-root",
            str(tmp_path / "runtime" / "serial" / "bench_suites"),
        ],
        capsys,
    )

    assert exit_code == 0
    assert payload["failure_summary"]["status"] == "ok"
    assert payload["metrics"]["degraded_count"] == 0
    assert payload["metrics"]["request_count"] > 0
    assert Path(payload["artifact_files"]["suite.json"]).exists()
    assert Path(payload["artifact_files"]["doctor_report.json"]).exists()
    assert Path(payload["artifact_files"]["scan_report.json"]).exists()
    assert Path(payload["artifact_files"]["position_report.json"]).exists()
    assert Path(payload["artifact_files"]["health_report.json"]).exists()
    assert Path(payload["artifact_files"]["calibration_snapshot.json"]).exists()
    assert Path(payload["artifact_files"]["motion_reports_index.json"]).exists()
    assert Path(payload["artifact_files"]["console_snapshot.json"]).exists()
    assert Path(payload["artifact_files"]["body_telemetry.json"]).exists()
    assert Path(payload["artifact_files"]["failure_summary.json"]).exists()
    assert Path(payload["artifact_files"]["request_response_history.json"]).exists()

    motion_index = json.loads(Path(payload["artifact_files"]["motion_reports_index.json"]).read_text(encoding="utf-8"))
    assert len(motion_index) == 4
    assert {item["command_family"] for item in motion_index} == {
        "write_neutral",
        "move_joint",
        "semantic_smoke",
        "safe_idle",
    }

    history = json.loads(Path(payload["artifact_files"]["request_response_history.json"]).read_text(encoding="utf-8"))
    assert history
    assert all("source" in item for item in history)
    assert all("request_hex" in item for item in history)


def test_serial_bench_fixture_replay_writes_stage_e_suite(monkeypatch, tmp_path: Path, capsys) -> None:
    motion_report_dir = tmp_path / "runtime" / "serial" / "motion_reports"
    monkeypatch.setattr(calibration_module, "DEFAULT_MOTION_REPORT_DIR", motion_report_dir)
    monkeypatch.setattr(
        bench_suite_module,
        "_collect_console_artifacts",
        lambda args, suite_dir: ({"fixture": True, "suite_dir": str(suite_dir)}, {"mode": args.transport}),
    )

    exit_code, payload = _run_bench(
        [
            "--transport",
            "fixture_replay",
            "--fixture",
            "src/embodied_stack/body/fixtures/robot_head_serial_fixture.json",
            "--report-root",
            str(tmp_path / "runtime" / "serial" / "bench_suites"),
        ],
        capsys,
    )

    assert exit_code == 0
    assert payload["transport_mode"] == "fixture_replay"
    assert payload["failure_summary"]["status"] == "ok"
    assert Path(payload["artifact_files"]["suite.json"]).exists()


def test_serial_failure_summary_and_motion_index_aggregate_stage_e_evidence(tmp_path: Path) -> None:
    report_path = tmp_path / "runtime" / "serial" / "motion_reports" / "report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(
            {
                "generated_at": str(utc_now()),
                "command_family": "move_joint",
                "success": False,
                "failure_reason": "power_sag_suspected",
                "stop_notes": ["post_health_error:3:timeout"],
                "request_response_history": [{"operation": "sync_write", "request_hex": "01", "response_hex": [], "ok": False, "reason_code": "timeout", "error": "timeout"}],
            }
        ),
        encoding="utf-8",
    )

    summary = build_serial_failure_summary(
        steps=[
            SerialBenchStepRecord(
                step_name="read_health",
                status="ok",
                started_at=utc_now(),
                completed_at=utc_now(),
                success=True,
            ),
            SerialBenchStepRecord(
                step_name="move_joint",
                status="degraded",
                started_at=utc_now(),
                completed_at=utc_now(),
                success=False,
                reason_code="power_sag_suspected",
                detail="post_health_error:3:timeout",
                report_path=str(report_path),
            ),
        ],
        motion_reports=[json.loads(report_path.read_text(encoding="utf-8")) | {"report_path": str(report_path)}],
        stop_step="move_joint",
    )
    index = build_motion_report_index([report_path])

    assert summary.status == "degraded"
    assert summary.stop_step == "move_joint"
    assert "power_sag_suspected" in summary.reason_codes
    assert any(item.source == "motion_report" for item in summary.events)
    assert index[0]["command_family"] == "move_joint"
    assert index[0]["failure_reason"] == "power_sag_suspected"
