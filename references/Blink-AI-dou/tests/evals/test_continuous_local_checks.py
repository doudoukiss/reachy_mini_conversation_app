from __future__ import annotations

from pathlib import Path

from embodied_stack.config import Settings
from embodied_stack.demo.continuous_local_checks import run_continuous_local_checks


def test_continuous_local_checks_pass(tmp_path: Path):
    settings = Settings(
        _env_file=None,
        brain_store_path=str(tmp_path / "brain_store.json"),
        demo_report_dir=str(tmp_path / "demo_runs"),
        demo_check_dir=str(tmp_path / "demo_checks"),
        episode_export_dir=str(tmp_path / "episodes"),
        shift_report_dir=str(tmp_path / "shift_reports"),
        operator_auth_token="desktop-test-token",
        operator_auth_runtime_file=str(tmp_path / "operator_auth.json"),
        blink_always_on_enabled=True,
    )

    suite = run_continuous_local_checks(settings=settings, output_dir=tmp_path / "continuous_local")

    assert suite.passed is True
    assert {item.check_name for item in suite.items} == {
        "cold_start_retry",
        "open_mic_turn",
        "barge_in_interrupt",
        "personal_context_mode",
        "venue_demo_context_mode",
        "daily_memory",
        "proactive_policy",
        "latency_visibility",
        "model_residency",
    }
