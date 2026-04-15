from __future__ import annotations

from pathlib import Path

from embodied_stack.config import Settings
from embodied_stack.desktop import launcher


def build_settings(tmp_path: Path, **overrides) -> Settings:
    return Settings(
        _env_file=None,
        brain_store_path=str(tmp_path / "brain_store.json"),
        demo_report_dir=str(tmp_path / "demo_runs"),
        demo_check_dir=str(tmp_path / "demo_checks"),
        shift_report_dir=str(tmp_path / "shift_reports"),
        episode_export_dir=str(tmp_path / "episodes"),
        perception_frame_dir=str(tmp_path / "perception_frames"),
        operator_auth_runtime_file=str(tmp_path / "operator_auth.json"),
        blink_appliance_profile_file=str(tmp_path / "appliance_profile.json"),
        blink_appliance_mode=True,
        brain_host="127.0.0.1",
        brain_port=8765,
        **overrides,
    )


class _FakeProcess:
    def __init__(self, returncode: int = 0) -> None:
        self.returncode = returncode
        self.running = True
        self.terminated = False
        self.killed = False

    def wait(self, timeout: float | None = None) -> int:
        del timeout
        self.running = False
        return self.returncode

    def poll(self) -> int | None:
        return None if self.running else self.returncode

    def terminate(self) -> None:
        self.terminated = True
        self.running = False

    def kill(self) -> None:
        self.killed = True
        self.running = False


def test_build_service_env_sets_appliance_runtime_variables(tmp_path: Path):
    settings = build_settings(tmp_path)

    env = launcher.build_service_env(settings)

    assert env["BRAIN_HOST"] == "127.0.0.1"
    assert env["BRAIN_PORT"] == "8765"
    assert env["BLINK_APPLIANCE_MODE"] == "true"
    assert env["BLINK_APPLIANCE_PROFILE_FILE"] == settings.blink_appliance_profile_file


def test_run_appliance_waits_for_ready_and_opens_console_url(monkeypatch, tmp_path: Path, capsys):
    settings = build_settings(tmp_path)
    process = _FakeProcess(returncode=0)
    seen: dict[str, object] = {}

    monkeypatch.setattr(launcher, "ensure_runtime_layout", lambda runtime_settings: ["runtime"] if runtime_settings is settings else [])
    monkeypatch.setattr(launcher, "launch_service", lambda runtime_settings: process)
    monkeypatch.setattr(
        launcher,
        "wait_for_service_ready",
        lambda *, base_url, timeout_seconds=20.0: seen.setdefault("ready", (base_url, timeout_seconds)),
    )
    monkeypatch.setattr(
        launcher,
        "fetch_appliance_status",
        lambda *, base_url: seen.setdefault(
            "appliance_status",
            {
                "selected_microphone_label": "LG UltraFine Display Audio",
                "selected_camera_label": "LG UltraFine Display Camera",
                "selected_speaker_label": "system_default",
                "setup_issues": [{"category": "camera", "blocking": False}],
            },
        ),
    )
    monkeypatch.setattr(
        launcher,
        "fetch_service_health",
        lambda *, base_url: seen.setdefault("health", {"dialogue_backend": "ollama_text"}),
    )
    monkeypatch.setattr(
        launcher,
        "open_console_url",
        lambda url: seen.setdefault("opened", url) == url,
    )

    exit_code = launcher.run_appliance(settings=settings, open_console=True)

    assert exit_code == 0
    assert seen["ready"] == ("http://127.0.0.1:8765", 20.0)
    assert seen["opened"] == "http://127.0.0.1:8765/console"
    output = capsys.readouterr().out
    assert "blink_appliance url=http://127.0.0.1:8765/console" in output
    assert "blink_appliance browser=opened" in output
    assert "blink_appliance_ready console=http://127.0.0.1:8765/console text=ollama_text" in output


def test_main_reset_runtime_reports_removed_paths(monkeypatch, tmp_path: Path, capsys):
    settings = build_settings(tmp_path)
    seen: dict[str, object] = {}

    monkeypatch.setattr(launcher, "appliance_settings", lambda port=None: settings if port is None else settings)
    monkeypatch.setattr(
        launcher,
        "reset_runtime_state",
        lambda runtime_settings: seen.setdefault("removed", [str(Path(runtime_settings.demo_report_dir))]),
    )

    exit_code = launcher.main(["--reset-runtime"])

    assert exit_code == 0
    assert seen["removed"] == [str(Path(settings.demo_report_dir))]
    assert "blink_appliance_reset removed=1" in capsys.readouterr().out


def test_main_doctor_writes_appliance_report(monkeypatch, tmp_path: Path, capsys):
    settings = build_settings(tmp_path)
    seen: dict[str, object] = {}

    monkeypatch.setattr(launcher, "appliance_settings", lambda port=None: settings if port is None else settings)
    monkeypatch.setattr(
        launcher,
        "run_local_companion_doctor",
        lambda *, settings, write_path: seen.setdefault(
            "doctor",
            {"settings": settings, "report_path": str(write_path), "issues": ["missing_model"]},
        ),
    )

    exit_code = launcher.main(["--doctor"])

    assert exit_code == 0
    assert seen["doctor"]["settings"] is settings
    assert seen["doctor"]["report_path"] == "runtime/diagnostics/blink_appliance_report.md"
    assert "blink_appliance_doctor report=runtime/diagnostics/blink_appliance_report.md issues=1" in capsys.readouterr().out


def test_main_respects_no_open_console_flag(monkeypatch, tmp_path: Path):
    settings = build_settings(tmp_path)
    seen: dict[str, object] = {}

    monkeypatch.setattr(launcher, "appliance_settings", lambda port=None: settings if port is None else settings)
    def _run_appliance(*, settings, open_console):
        seen["run"] = (settings, open_console)
        return 0

    monkeypatch.setattr(launcher, "run_appliance", _run_appliance)

    exit_code = launcher.main(["--no-open-console"])

    assert exit_code == 0
    assert seen["run"] == (settings, False)
