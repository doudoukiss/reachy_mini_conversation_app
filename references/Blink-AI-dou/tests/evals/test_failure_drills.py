from __future__ import annotations

from pathlib import Path

from embodied_stack.config import Settings
from embodied_stack.demo.failure_drills import run_local_companion_failure_drills


def test_failure_drills_pass(tmp_path: Path) -> None:
    settings = Settings(
        _env_file=None,
        brain_store_path=str(tmp_path / "brain_store.json"),
        demo_report_dir=str(tmp_path / "demo_runs"),
        demo_check_dir=str(tmp_path / "demo_checks"),
        episode_export_dir=str(tmp_path / "episodes"),
        shift_report_dir=str(tmp_path / "shift_reports"),
        operator_auth_runtime_file=str(tmp_path / "operator_auth.json"),
        blink_always_on_enabled=True,
    )

    suite = run_local_companion_failure_drills(settings=settings, output_dir=tmp_path / "failure_drills")

    assert suite.passed is True
    assert {item.check_name for item in suite.items} == {
        "slow_model_response_presence",
        "local_model_unavailable",
        "provider_timeout",
        "malformed_tool_result",
        "tool_exception",
        "mic_unavailable",
        "camera_permission_denied",
        "speaker_unavailable",
        "memory_conflict_resolution",
        "no_retrieval_result",
        "approval_denied",
        "unsupported_action_request",
        "serial_port_missing",
        "serial_calibration_missing",
        "serial_live_write_not_confirmed",
    }
    assert Path(suite.artifact_files["summary"]).exists()
    assert Path(suite.artifact_files["markdown"]).exists()
