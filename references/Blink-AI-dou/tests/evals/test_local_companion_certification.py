from __future__ import annotations

from pathlib import Path

from embodied_stack.config import Settings
from embodied_stack.demo import local_companion_certification as certification
from embodied_stack.shared.contracts import (
    DemoCheckResult,
    DemoCheckSuiteRecord,
    LocalCompanionCertificationRecord,
    LocalCompanionCertificationVerdict,
    LocalCompanionReadinessRecord,
    utc_now,
)


def _settings(tmp_path: Path) -> Settings:
    return Settings(
        _env_file=None,
        brain_store_path=str(tmp_path / "brain_store.json"),
        demo_report_dir=str(tmp_path / "demo_runs"),
        demo_check_dir=str(tmp_path / "demo_checks"),
        episode_export_dir=str(tmp_path / "episodes"),
        shift_report_dir=str(tmp_path / "shift_reports"),
        operator_auth_runtime_file=str(tmp_path / "operator_auth.json"),
        local_companion_certification_dir=str(tmp_path / "certification"),
        local_companion_burn_in_dir=str(tmp_path / "burn_in"),
    )


def _suite(*, names: list[str], passed: bool = True) -> DemoCheckSuiteRecord:
    return DemoCheckSuiteRecord(
        passed=passed,
        items=[
            DemoCheckResult(
                check_name=name,
                description=name.replace("_", " "),
                completed_at=utc_now(),
                passed=passed,
            )
            for name in names
        ],
        artifact_files={"summary": f"/tmp/{names[0] if names else 'suite'}.json"},
    )


def test_local_companion_certification_writes_latest_readiness_and_bundle(monkeypatch, tmp_path: Path) -> None:
    settings = _settings(tmp_path)

    monkeypatch.setattr(
        certification,
        "run_local_companion_doctor",
        lambda **_kwargs: {
            "report_path": str(tmp_path / "doctor.md"),
            "issues": [],
            "doctor_status": "certified",
            "next_actions": ["Safe to demo."],
            "runtime": {
                "first_text_turn": {"ok": True},
                "warm_text_turn": {"ok": True},
                "product_behavior_probe": {"ok": True},
                "proactive_policy": {"ok": True},
            },
        },
    )
    monkeypatch.setattr(
        certification,
        "run_local_companion_checks",
        lambda **_kwargs: _suite(
            names=[
                "webcam_grounded_reply",
                "memory_retrieval",
                "uncertainty_honesty",
            ]
        ),
    )
    monkeypatch.setattr(
        certification,
        "run_always_on_local_checks",
        lambda **_kwargs: _suite(names=["scene_observer_refresh"]),
    )
    monkeypatch.setattr(
        certification,
        "run_continuous_local_checks",
        lambda **_kwargs: _suite(
            names=[
                "open_mic_turn",
                "barge_in_interrupt",
                "proactive_policy",
            ]
        ),
    )

    def _story(self, *, cert_dir: Path, story_name: str, context_mode, session_id: str):  # noqa: ANN001
        del self, cert_dir, context_mode, session_id
        if story_name == "local_companion_story":
            scene_name = "natural_discussion"
        else:
            scene_name = "safe_fallback_failure"
        return {
            "story_name": story_name,
            "scene_names": [scene_name],
            "passed": True,
            "items": [{"scene_name": scene_name, "success": True, "scorecard": {"passed": True}}],
            "episode_ids": [f"{story_name}-episode"],
            "exports": [],
        }

    def _action_validation(self, *, cert_dir: Path):  # noqa: ANN001
        del self
        action_bundle_index = cert_dir / "episodes" / "linked_action_bundles.json"
        action_bundle_index.parent.mkdir(parents=True, exist_ok=True)
        action_bundle_index.write_text("{}", encoding="utf-8")
        return {
            "passed": True,
            "session_id": "cert-session",
            "interaction": {"response": {"reply_text": "ok"}},
            "workflow": {"status": "completed"},
            "overview": {"recent_bundles": [{"bundle_id": "bundle-1"}]},
            "episode": {
                "episode_id": "episode-1",
                "derived_artifact_files": {"action_bundle_index": str(action_bundle_index)},
            },
            "episode_ids": ["episode-1"],
        }

    monkeypatch.setattr(certification.LocalCompanionCertificationRunner, "_run_story", _story)
    monkeypatch.setattr(certification.LocalCompanionCertificationRunner, "_run_action_plane_validation", _action_validation)

    record = certification.run_local_companion_certification(settings=settings)

    assert record.verdict == LocalCompanionCertificationVerdict.CERTIFIED
    assert record.machine_readiness.verdict == LocalCompanionCertificationVerdict.CERTIFIED
    assert Path(record.artifact_files["certification"]).exists()
    assert Path(settings.local_companion_certification_dir, certification.LATEST_CERTIFICATION_FILE).exists()
    assert Path(settings.local_companion_certification_dir, certification.LATEST_READINESS_FILE).exists()

    latest = certification.load_latest_local_companion_certification(settings)
    readiness = certification.load_latest_local_companion_readiness(settings)
    assert latest is not None
    assert readiness is not None
    assert latest.cert_id == record.cert_id
    assert readiness.verdict == LocalCompanionCertificationVerdict.CERTIFIED


def test_load_latest_local_companion_readiness_falls_back_to_latest_certification(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    root = certification.certification_root(settings)
    root.mkdir(parents=True, exist_ok=True)
    record = LocalCompanionCertificationRecord(
        verdict=LocalCompanionCertificationVerdict.DEGRADED_BUT_ACCEPTABLE,
        machine_readiness=LocalCompanionReadinessRecord(
            verdict=LocalCompanionCertificationVerdict.DEGRADED_BUT_ACCEPTABLE,
            summary="Degraded but usable.",
            machine_ready=False,
            product_ready=True,
            degraded_warnings=["camera unavailable"],
        ),
    )
    (root / certification.LATEST_CERTIFICATION_FILE).write_text(record.model_dump_json(indent=2), encoding="utf-8")

    readiness = certification.load_latest_local_companion_readiness(settings)

    assert readiness is not None
    assert readiness.verdict == LocalCompanionCertificationVerdict.DEGRADED_BUT_ACCEPTABLE
    assert readiness.degraded_warnings == ["camera unavailable"]


def test_local_companion_burn_in_runner_writes_summary(monkeypatch, tmp_path: Path) -> None:
    settings = _settings(tmp_path)

    def _passing_check(self, *, check_name: str, description: str, check_dir: Path):  # noqa: ANN001
        del self, check_dir
        return DemoCheckResult(
            check_name=check_name,
            description=description,
            completed_at=utc_now(),
            passed=True,
        )

    monkeypatch.setattr(certification.LocalCompanionBurnInRunner, "_check_periodic_text_turns", _passing_check)
    monkeypatch.setattr(certification.LocalCompanionBurnInRunner, "_check_reminder_workflow_continuity", _passing_check)
    monkeypatch.setattr(certification.LocalCompanionBurnInRunner, "_check_interrupt_recovery", _passing_check)
    monkeypatch.setattr(certification.LocalCompanionBurnInRunner, "_check_trigger_stability", _passing_check)
    monkeypatch.setattr(certification.LocalCompanionBurnInRunner, "_check_startup_shutdown_cycles", _passing_check)
    monkeypatch.setattr(certification.LocalCompanionBurnInRunner, "_check_mode_switching", _passing_check)
    monkeypatch.setattr(certification.LocalCompanionBurnInRunner, "_check_artifact_linkage", _passing_check)

    suite = certification.run_local_companion_burn_in(settings=settings)

    assert suite.passed is True
    assert len(suite.items) == 7
    assert Path(suite.artifact_files["summary"]).exists()
