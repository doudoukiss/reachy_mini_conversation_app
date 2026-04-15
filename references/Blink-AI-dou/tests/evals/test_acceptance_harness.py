from __future__ import annotations

import json
import subprocess
from pathlib import Path

from embodied_stack.config import Settings
from embodied_stack.demo.acceptance import AcceptanceStatus, build_test_inventory, run_acceptance


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        acceptance_report_dir=str(tmp_path / "acceptance"),
    )


def _completed(command: list[str], *, returncode: int = 0, payload: dict | None = None) -> subprocess.CompletedProcess[str]:
    stdout = json.dumps(payload, indent=2) if payload is not None else ""
    return subprocess.CompletedProcess(command, returncode, stdout=stdout, stderr="")


def test_build_test_inventory_covers_requested_categories() -> None:
    inventory = build_test_inventory()
    labels = {item.label for item in inventory}

    assert labels == {
        "repo health",
        "desktop/runtime",
        "Agent OS",
        "memory/relationship",
        "action plane",
        "embodiment/serial",
        "demos/evals",
    }

    action_plane = next(item for item in inventory if item.key == "action_plane")
    embodiment = next(item for item in inventory if item.key == "embodiment_serial")
    assert "tests/action_plane/test_stage_a.py" in action_plane.test_files
    assert "tests/body/test_serial_driver.py" in embodiment.test_files


def test_acceptance_plan_writes_machine_and_human_reports(tmp_path: Path) -> None:
    record = run_acceptance("quick", settings=_settings(tmp_path), execute=False)

    assert record.status == AcceptanceStatus.PLANNED
    assert Path(record.artifact_files["json"]).exists()
    assert Path(record.artifact_files["markdown"]).exists()
    assert all(item.status == AcceptanceStatus.PLANNED for item in record.commands)


def test_full_acceptance_records_degraded_certification_without_failing(monkeypatch, tmp_path: Path) -> None:
    def _run(command, **kwargs):  # noqa: ANN001
        del kwargs
        text = " ".join(command)
        if "local-companion-certify" in text:
            return _completed(
                command,
                payload={
                    "verdict": "degraded_but_acceptable",
                    "machine_readiness_passed": False,
                    "repo_runtime_correctness_passed": True,
                },
            )
        if "local-companion-burn-in" in text:
            return _completed(command, payload={"passed": True})
        if "demo-checks" in text:
            return _completed(command, payload={"passed": True})
        return _completed(command)

    monkeypatch.setattr(subprocess, "run", _run)

    record = run_acceptance("full", settings=_settings(tmp_path), execute=True)

    assert record.status == AcceptanceStatus.DEGRADED
    assert Path(record.artifact_files["json"]).exists()
    assert Path(record.artifact_files["markdown"]).exists()
    certification = next(item for item in record.commands if item.key == "local_companion_certify")
    assert certification.status == AcceptanceStatus.DEGRADED


def test_release_candidate_acceptance_requires_certified_verdict(monkeypatch, tmp_path: Path) -> None:
    def _run(command, **kwargs):  # noqa: ANN001
        del kwargs
        text = " ".join(command)
        if "local-companion-certify" in text:
            return _completed(
                command,
                payload={
                    "verdict": "degraded_but_acceptable",
                    "machine_readiness_passed": False,
                    "repo_runtime_correctness_passed": True,
                },
            )
        if "local-companion-burn-in" in text or "demo-checks" in text or "multimodal-demo-checks" in text:
            return _completed(command, payload={"passed": True})
        if "smoke-runner" in text:
            return _completed(command, payload={"status": "completed"})
        return _completed(command)

    monkeypatch.setattr(subprocess, "run", _run)

    record = run_acceptance("rc", settings=_settings(tmp_path), execute=True)

    assert record.status == AcceptanceStatus.FAILED
    certification = next(item for item in record.commands if item.key == "local_companion_certify")
    assert certification.status == AcceptanceStatus.FAILED
