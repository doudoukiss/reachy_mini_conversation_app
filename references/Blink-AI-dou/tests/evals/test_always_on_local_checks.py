from __future__ import annotations

from embodied_stack.config import Settings
from embodied_stack.demo.always_on_local_checks import run_always_on_local_checks


def test_run_always_on_local_checks(tmp_path):
    settings = Settings(
        _env_file=None,
        brain_store_path=str(tmp_path / "brain_store.json"),
        demo_report_dir=str(tmp_path / "demo_runs"),
        demo_check_dir=str(tmp_path / "demo_checks"),
        episode_export_dir=str(tmp_path / "episodes"),
        shift_report_dir=str(tmp_path / "shift_reports"),
        operator_auth_runtime_file=str(tmp_path / "operator_auth.json"),
        operator_auth_token="always-on-check-token",
    )

    suite = run_always_on_local_checks(settings=settings, output_dir=tmp_path / "demo_checks")

    assert suite.passed is True
    assert len(suite.items) >= 6
