from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from embodied_stack.config import Settings, get_settings
from embodied_stack.desktop.app import build_desktop_runtime
from embodied_stack.desktop.doctor import run_local_companion_doctor
from embodied_stack.demo.always_on_local_checks import run_always_on_local_checks
from embodied_stack.demo.continuous_local_checks import (
    OpenMicRegistry,
    StatefulSpeakerOutput,
    _speech_result,
    run_continuous_local_checks,
)
from embodied_stack.demo.investor_scenes import INVESTOR_SCENE_SEQUENCES
from embodied_stack.demo.local_companion_checks import FakeDeviceRegistry, run_local_companion_checks
from embodied_stack.persistence import load_json_model_or_quarantine, write_json_atomic
from embodied_stack.shared.models import (
    CompanionAudioMode,
    CompanionContextMode,
    DemoCheckResult,
    DemoCheckSuiteRecord,
    LocalCompanionCertificationIssueRecord,
    LocalCompanionCertificationRecord,
    LocalCompanionCertificationVerdict,
    LocalCompanionReadinessRecord,
    LocalCompanionRubricScoreRecord,
    ResponseMode,
    VoiceRuntimeMode,
    WorkflowStartRequestRecord,
    utc_now,
)


LATEST_CERTIFICATION_FILE = "latest.json"
LATEST_READINESS_FILE = "latest_readiness.json"
CERTIFICATION_SUMMARY_FILE = "certification.json"
RUNBOOK_DECISION_HINTS = {
    LocalCompanionCertificationVerdict.MACHINE_BLOCKER: "not_ready",
    LocalCompanionCertificationVerdict.REPO_OR_RUNTIME_BUG: "not_ready",
    LocalCompanionCertificationVerdict.DEGRADED_BUT_ACCEPTABLE: "demo_only",
    LocalCompanionCertificationVerdict.CERTIFIED: "ship",
}


def certification_root(settings: Settings | None = None) -> Path:
    return Path((settings or get_settings()).local_companion_certification_dir)


def burn_in_root(settings: Settings | None = None) -> Path:
    return Path((settings or get_settings()).local_companion_burn_in_dir)


def load_latest_local_companion_certification(
    settings: Settings | None = None,
) -> LocalCompanionCertificationRecord | None:
    root = certification_root(settings)
    return load_json_model_or_quarantine(
        root / LATEST_CERTIFICATION_FILE,
        LocalCompanionCertificationRecord,
        quarantine_invalid=True,
    )


def load_latest_local_companion_readiness(
    settings: Settings | None = None,
) -> LocalCompanionReadinessRecord | None:
    root = certification_root(settings)
    readiness = load_json_model_or_quarantine(
        root / LATEST_READINESS_FILE,
        LocalCompanionReadinessRecord,
        quarantine_invalid=True,
    )
    if readiness is not None:
        return readiness
    record = load_latest_local_companion_certification(settings)
    if record is None:
        return None
    return record.machine_readiness


def run_local_companion_certification(
    *,
    settings: Settings | None = None,
    output_dir: str | Path | None = None,
) -> LocalCompanionCertificationRecord:
    runner = LocalCompanionCertificationRunner(settings=settings, output_dir=output_dir)
    return runner.run()


def run_local_companion_burn_in(
    *,
    settings: Settings | None = None,
    output_dir: str | Path | None = None,
) -> DemoCheckSuiteRecord:
    runner = LocalCompanionBurnInRunner(settings=settings, output_dir=output_dir)
    return runner.run()


class LocalCompanionCertificationRunner:
    def __init__(self, *, settings: Settings | None = None, output_dir: str | Path | None = None) -> None:
        self.settings = settings or get_settings()
        self.output_dir = Path(output_dir or certification_root(self.settings))
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def run(self) -> LocalCompanionCertificationRecord:
        record = LocalCompanionCertificationRecord()
        cert_dir = self.output_dir / record.cert_id
        cert_dir.mkdir(parents=True, exist_ok=True)
        record.artifact_dir = str(cert_dir)

        doctor_path = cert_dir / "doctor" / "local_mbp_config_report.md"
        doctor_report = run_local_companion_doctor(
            settings=self.settings,
            write_path=doctor_path,
        )
        local_checks = run_local_companion_checks(settings=self.settings, output_dir=cert_dir / "local_companion_checks")
        always_on_checks = run_always_on_local_checks(settings=self.settings, output_dir=cert_dir / "always_on_local_checks")
        continuous_checks = run_continuous_local_checks(settings=self.settings, output_dir=cert_dir / "continuous_local_checks")
        local_story = self._run_story(
            cert_dir=cert_dir,
            story_name="local_companion_story",
            context_mode=CompanionContextMode.PERSONAL_LOCAL,
            session_id="local-companion-certification-live",
        )
        desktop_story = self._run_story(
            cert_dir=cert_dir,
            story_name="desktop_story",
            context_mode=CompanionContextMode.VENUE_DEMO,
            session_id="desktop-story-certification-live",
        )
        action_validation = self._run_action_plane_validation(cert_dir=cert_dir)

        issues = [self._normalize_issue(item) for item in doctor_report.get("issues", [])]
        if not local_checks.passed:
            issues.append(
                LocalCompanionCertificationIssueRecord(
                    bucket=LocalCompanionCertificationVerdict.REPO_OR_RUNTIME_BUG,
                    category="local_companion_checks",
                    message="Deterministic local companion checks did not pass cleanly.",
                    blocking=True,
                )
            )
        if not always_on_checks.passed:
            issues.append(
                LocalCompanionCertificationIssueRecord(
                    bucket=LocalCompanionCertificationVerdict.REPO_OR_RUNTIME_BUG,
                    category="always_on_local_checks",
                    message="Always-on local checks did not pass cleanly.",
                    blocking=True,
                )
            )
        if not continuous_checks.passed:
            issues.append(
                LocalCompanionCertificationIssueRecord(
                    bucket=LocalCompanionCertificationVerdict.REPO_OR_RUNTIME_BUG,
                    category="continuous_local_checks",
                    message="Continuous local checks did not pass cleanly.",
                    blocking=True,
                )
            )
        if not local_story["passed"]:
            issues.append(
                LocalCompanionCertificationIssueRecord(
                    bucket=LocalCompanionCertificationVerdict.REPO_OR_RUNTIME_BUG,
                    category="local_companion_story",
                    message="The maintained local companion story did not pass every scene.",
                    blocking=True,
                )
            )
        if not desktop_story["passed"]:
            issues.append(
                LocalCompanionCertificationIssueRecord(
                    bucket=LocalCompanionCertificationVerdict.REPO_OR_RUNTIME_BUG,
                    category="desktop_story",
                    message="The maintained desktop story regression lane did not pass every scene.",
                    blocking=True,
                )
            )
        if not action_validation["passed"]:
            issues.append(
                LocalCompanionCertificationIssueRecord(
                    bucket=LocalCompanionCertificationVerdict.REPO_OR_RUNTIME_BUG,
                    category="action_plane_linkage",
                    message="Local companion certification could not prove Action Plane bundle and episode linkage.",
                    blocking=True,
                )
            )

        record.machine_readiness = self._build_readiness(
            doctor_report=doctor_report,
            cert_dir=cert_dir,
        )
        record.machine_readiness_passed = (
            record.machine_readiness.verdict == LocalCompanionCertificationVerdict.CERTIFIED
        )
        record.repo_runtime_correctness_passed = all(
            suite.passed for suite in (local_checks, always_on_checks, continuous_checks)
        )
        record.companion_behavior_quality_passed = bool(local_story["passed"] and desktop_story["passed"])
        record.operator_ux_quality_passed = bool(action_validation["passed"])
        record.issues = issues
        record.rubric = self._build_rubric(
            doctor_report=doctor_report,
            local_checks=local_checks,
            always_on_checks=always_on_checks,
            continuous_checks=continuous_checks,
            local_story=local_story,
            desktop_story=desktop_story,
            action_validation=action_validation,
        )
        record.blocking_issues = [item.message for item in issues if item.blocking]
        record.verdict = self._final_verdict(
            doctor_verdict=record.machine_readiness.verdict,
            repo_runtime_correctness_passed=record.repo_runtime_correctness_passed,
            companion_behavior_quality_passed=record.companion_behavior_quality_passed,
            operator_ux_quality_passed=record.operator_ux_quality_passed,
        )
        record.next_actions = self._final_next_actions(record)
        record.machine_readiness = record.machine_readiness.model_copy(
            update={
                "summary": self._final_summary(record),
                "machine_ready": record.machine_readiness.verdict == LocalCompanionCertificationVerdict.CERTIFIED,
                "product_ready": (
                    record.repo_runtime_correctness_passed
                    and record.companion_behavior_quality_passed
                    and record.operator_ux_quality_passed
                ),
                "last_run_at": utc_now(),
                "last_certified_at": utc_now() if record.verdict == LocalCompanionCertificationVerdict.CERTIFIED else None,
                "next_actions": list(record.next_actions),
                "artifact_dir": str(cert_dir),
                "doctor_report_path": str(doctor_path),
            }
        )
        record.completed_at = utc_now()

        record.artifact_files = {
            "doctor_report": str(doctor_path),
            "local_companion_checks": local_checks.artifact_files.get("summary", ""),
            "always_on_local_checks": always_on_checks.artifact_files.get("summary", ""),
            "continuous_local_checks": continuous_checks.artifact_files.get("summary", ""),
            "local_companion_story": str(cert_dir / "local_companion_story.json"),
            "desktop_story": str(cert_dir / "desktop_story.json"),
            "action_plane_validation": str(cert_dir / "action_plane_validation.json"),
            "certification": str(cert_dir / CERTIFICATION_SUMMARY_FILE),
        }
        record.linked_episode_ids = sorted(
            {
                *local_story["episode_ids"],
                *desktop_story["episode_ids"],
                *action_validation["episode_ids"],
            }
        )

        self._write_json(Path(record.artifact_files["local_companion_story"]), local_story)
        self._write_json(Path(record.artifact_files["desktop_story"]), desktop_story)
        self._write_json(Path(record.artifact_files["action_plane_validation"]), action_validation)
        self._write_json(cert_dir / CERTIFICATION_SUMMARY_FILE, record)
        self._write_json(self.output_dir / LATEST_CERTIFICATION_FILE, record)
        self._write_json(self.output_dir / LATEST_READINESS_FILE, record.machine_readiness)
        return record

    def _run_story(
        self,
        *,
        cert_dir: Path,
        story_name: str,
        context_mode: CompanionContextMode,
        session_id: str,
    ) -> dict[str, Any]:
        runtime_settings = self._runtime_settings(cert_dir=cert_dir, context_mode=context_mode)
        with build_desktop_runtime(settings=runtime_settings) as runtime:
            results = runtime.run_story(
                story_name,
                session_id=session_id,
                response_mode=ResponseMode.GUIDE,
                voice_mode=VoiceRuntimeMode.STUB_DEMO,
                speak_reply=False,
                reset_first=True,
            )
            exported = []
            seen: set[str] = set()
            for item in results:
                if item.session_id in seen:
                    continue
                seen.add(item.session_id)
                exported.append(runtime.export_session_episode(item.session_id).model_dump(mode="json"))
        return {
            "story_name": story_name,
            "scene_names": list(INVESTOR_SCENE_SEQUENCES.get(story_name, ())),
            "passed": all(item.success and (item.scorecard.passed if item.scorecard is not None else True) for item in results),
            "items": [item.model_dump(mode="json") for item in results],
            "episode_ids": [item["episode_id"] for item in exported],
            "exports": exported,
        }

    def _run_action_plane_validation(self, *, cert_dir: Path) -> dict[str, Any]:
        runtime_settings = self._runtime_settings(
            cert_dir=cert_dir,
            context_mode=CompanionContextMode.PERSONAL_LOCAL,
        )
        with build_desktop_runtime(settings=runtime_settings) as runtime:
            session = runtime.ensure_session(
                session_id="local-companion-certification-actions",
                user_id="local-companion-certification",
                response_mode=ResponseMode.GUIDE,
            )
            interaction = runtime.submit_text(
                "I am checking the local companion certification path.",
                session_id=session.session_id,
                user_id=session.user_id,
                response_mode=ResponseMode.GUIDE,
                voice_mode=VoiceRuntimeMode.STUB_DEMO,
                speak_reply=False,
                source="local_companion_certification",
            )
            workflow = runtime.operator_console.start_action_plane_workflow(
                WorkflowStartRequestRecord(
                    workflow_id="capture_note_and_reminder",
                    session_id=session.session_id,
                    inputs={
                        "note_title": "Certification Note",
                        "note_content": "Verify that the local companion certification export links Action Plane artifacts.",
                        "note_tags": ["certification", "local_companion"],
                        "reminder_text": "Review the local companion certification bundle.",
                    },
                    note="local_companion_certification",
                )
            )
            overview = runtime.operator_console.get_action_plane_overview(session_id=session.session_id)
            episode = runtime.export_session_episode(session.session_id)
        action_bundle_index = episode.derived_artifact_files.get("action_bundle_index")
        linked = bool(action_bundle_index and Path(action_bundle_index).exists() and overview.recent_bundles)
        return {
            "passed": bool(
                interaction.response.reply_text
                and workflow.status is not None
                and workflow.status.value == "completed"
                and linked
            ),
            "session_id": session.session_id,
            "interaction": interaction.model_dump(mode="json"),
            "workflow": workflow.model_dump(mode="json"),
            "overview": overview.model_dump(mode="json"),
            "episode": episode.model_dump(mode="json"),
            "episode_ids": [episode.episode_id],
        }

    def _build_readiness(
        self,
        *,
        doctor_report: dict[str, Any],
        cert_dir: Path,
    ) -> LocalCompanionReadinessRecord:
        verdict = LocalCompanionCertificationVerdict(doctor_report.get("doctor_status") or "degraded_but_acceptable")
        machine_blockers = [
            item["message"]
            for item in doctor_report.get("issues", [])
            if item.get("bucket") == LocalCompanionCertificationVerdict.MACHINE_BLOCKER.value
        ]
        repo_issues = [
            item["message"]
            for item in doctor_report.get("issues", [])
            if item.get("bucket") == LocalCompanionCertificationVerdict.REPO_OR_RUNTIME_BUG.value
        ]
        degraded = [
            item["message"]
            for item in doctor_report.get("issues", [])
            if item.get("bucket") == LocalCompanionCertificationVerdict.DEGRADED_BUT_ACCEPTABLE.value
        ]
        return LocalCompanionReadinessRecord(
            verdict=verdict,
            summary=self._doctor_summary(verdict),
            machine_ready=verdict == LocalCompanionCertificationVerdict.CERTIFIED,
            product_ready=False,
            machine_blockers=machine_blockers,
            repo_or_runtime_issues=repo_issues,
            degraded_warnings=degraded,
            artifact_dir=str(cert_dir),
            doctor_report_path=str(doctor_report.get("report_path") or ""),
            next_actions=list(doctor_report.get("next_actions") or []),
        )

    def _build_rubric(
        self,
        *,
        doctor_report: dict[str, Any],
        local_checks: DemoCheckSuiteRecord,
        always_on_checks: DemoCheckSuiteRecord,
        continuous_checks: DemoCheckSuiteRecord,
        local_story: dict[str, Any],
        desktop_story: dict[str, Any],
        action_validation: dict[str, Any],
    ) -> list[LocalCompanionRubricScoreRecord]:
        local_items = {item.check_name: item for item in local_checks.items}
        always_items = {item.check_name: item for item in always_on_checks.items}
        continuous_items = {item.check_name: item for item in continuous_checks.items}
        local_scenes = {item["scene_name"]: item for item in local_story["items"]}
        desktop_scenes = {item["scene_name"]: item for item in desktop_story["items"]}

        def passed_item(item: DemoCheckResult | None) -> bool:
            return bool(item is not None and item.passed)

        def passed_scene(name: str, source: dict[str, Any]) -> bool:
            item = source.get(name)
            if item is None:
                return False
            scorecard = item.get("scorecard") or {}
            return bool(item.get("success") and scorecard.get("passed", True))

        warm_ok = bool((doctor_report.get("runtime", {}).get("warm_text_turn") or {}).get("ok"))
        cold_ok = bool((doctor_report.get("runtime", {}).get("first_text_turn") or {}).get("ok"))
        product_ok = bool((doctor_report.get("runtime", {}).get("product_behavior_probe") or {}).get("ok"))

        return [
            self._rubric_record(
                category="usefulness",
                passed=passed_scene("natural_discussion", local_scenes)
                and passed_scene("knowledge_grounded_help", local_scenes)
                and action_validation["passed"],
                observed="Local personal conversation, knowledge help, and deterministic note/reminder workflow completed.",
                notes=["Hard blocker: maintained local companion story or note/reminder workflow fails."],
            ),
            self._rubric_record(
                category="honesty",
                passed=passed_item(local_items.get("uncertainty_honesty"))
                and passed_scene("safe_degraded_behavior", local_scenes)
                and product_ok,
                observed="Fallback and uncertainty stay explicit, and personal-local behavior remains distinct from venue phrasing.",
                notes=["Hard blocker: visual uncertainty turns into a confident invented claim."],
            ),
            self._rubric_record(
                category="grounding",
                passed=passed_item(local_items.get("webcam_grounded_reply"))
                and passed_scene("observe_and_comment", local_scenes),
                observed="Grounded camera and scene fixtures drive visible-text-aware answers.",
                notes=["Hard blocker: grounded sign-reading path regresses into a generic response."],
            ),
            self._rubric_record(
                category="memory_continuity",
                passed=passed_item(local_items.get("memory_retrieval"))
                and passed_scene("companion_memory_follow_up", local_scenes)
                and action_validation["passed"],
                observed="Reminder/note continuity and memory follow-up remain available across the local companion lane.",
                notes=["Hard blocker: the companion loses the current visitor or reminder continuity."],
            ),
            self._rubric_record(
                category="interruption_and_recovery",
                passed=passed_item(continuous_items.get("open_mic_turn"))
                and passed_item(continuous_items.get("barge_in_interrupt")),
                observed="Open-mic and barge-in interruption paths complete with deterministic recovery.",
                notes=["Hard blocker: voice loop or interruption flow becomes stuck."],
            ),
            self._rubric_record(
                category="latency_and_responsiveness",
                passed=warm_ok and cold_ok,
                observed="Both cold and warm local text turn probes completed on the doctor lane.",
                notes=["Hard blocker: warm local text turn does not complete cleanly."],
            ),
            self._rubric_record(
                category="proactive_restraint",
                passed=passed_item(always_items.get("scene_observer_refresh"))
                and passed_item(continuous_items.get("proactive_policy"))
                and bool((doctor_report.get("runtime", {}).get("proactive_policy") or {}).get("ok")),
                observed="Proactive eligibility, suppression, and refresh discipline stay bounded.",
                notes=["Hard blocker: proactive policy triggers repeatedly without cooldown or justification."],
            ),
            self._rubric_record(
                category="operator_clarity",
                passed=action_validation["passed"]
                and passed_scene("safe_fallback_failure", desktop_scenes),
                observed="The Stage 6 workflow and export surfaces produce actionable bundle-linked evidence.",
                notes=["Hard blocker: the operator cannot find the next step from the action-linked local path."],
            ),
            self._rubric_record(
                category="artifact_completeness",
                passed=bool(
                    local_story["episode_ids"]
                    and desktop_story["episode_ids"]
                    and action_validation["episode"].get("derived_artifact_files", {}).get("action_bundle_index")
                ),
                observed="Episode exports and action-bundle linkage were written for the certification run.",
                notes=["Hard blocker: certification produces missing or unlinkable evidence artifacts."],
            ),
        ]

    def _rubric_record(
        self,
        *,
        category: str,
        passed: bool,
        observed: str,
        notes: list[str],
    ) -> LocalCompanionRubricScoreRecord:
        return LocalCompanionRubricScoreRecord(
            category=category,
            score=2.0 if passed else 0.0,
            max_score=2.0,
            passed=passed,
            hard_blocker=not passed,
            minimum_pass_bar="All required lane checks are green and the result is understandable to an operator.",
            world_class_bar="The lane is green, explicit, replayable, and demo-ready with linked artifacts.",
            observed=observed,
            notes=notes,
        )

    def _runtime_settings(
        self,
        *,
        cert_dir: Path,
        context_mode: CompanionContextMode,
    ) -> Settings:
        return self.settings.model_copy(
            update={
                "blink_always_on_enabled": True,
                "blink_context_mode": context_mode,
                "brain_store_path": str(cert_dir / "brain_store.json"),
                "demo_report_dir": str(cert_dir / "demo_runs"),
                "demo_check_dir": str(cert_dir / "demo_checks"),
                "episode_export_dir": str(cert_dir / "episodes"),
                "shift_report_dir": str(cert_dir / "shift_reports"),
                "operator_auth_runtime_file": str(cert_dir / "operator_auth.json"),
                "blink_action_plane_draft_dir": str(cert_dir / "actions" / "drafts"),
                "blink_action_plane_stage_dir": str(cert_dir / "actions" / "staged"),
                "blink_action_plane_export_dir": str(cert_dir / "actions" / "exports"),
                "blink_action_plane_browser_storage_dir": str(cert_dir / "actions" / "browser"),
                "blink_appliance_profile_file": str(cert_dir / "appliance_profile.json"),
            }
        )

    def _normalize_issue(self, payload: dict[str, Any]) -> LocalCompanionCertificationIssueRecord:
        return LocalCompanionCertificationIssueRecord(
            bucket=LocalCompanionCertificationVerdict(
                payload.get("bucket") or LocalCompanionCertificationVerdict.DEGRADED_BUT_ACCEPTABLE.value
            ),
            category=str(payload.get("category") or "doctor"),
            message=str(payload.get("message") or ""),
            blocking=bool(payload.get("blocking")),
        )

    def _doctor_summary(self, verdict: LocalCompanionCertificationVerdict) -> str:
        if verdict == LocalCompanionCertificationVerdict.MACHINE_BLOCKER:
            return "This Mac is not yet ready to prove the intended local companion path."
        if verdict == LocalCompanionCertificationVerdict.REPO_OR_RUNTIME_BUG:
            return "The repo/runtime path is inconsistent with the intended local companion configuration."
        if verdict == LocalCompanionCertificationVerdict.DEGRADED_BUT_ACCEPTABLE:
            return "The product remains usable, but the full intended local path is still degraded."
        return "This Mac is ready to prove the intended world-class local companion path."

    def _final_verdict(
        self,
        *,
        doctor_verdict: LocalCompanionCertificationVerdict,
        repo_runtime_correctness_passed: bool,
        companion_behavior_quality_passed: bool,
        operator_ux_quality_passed: bool,
    ) -> LocalCompanionCertificationVerdict:
        if doctor_verdict == LocalCompanionCertificationVerdict.MACHINE_BLOCKER:
            return LocalCompanionCertificationVerdict.MACHINE_BLOCKER
        if (
            doctor_verdict == LocalCompanionCertificationVerdict.REPO_OR_RUNTIME_BUG
            or not repo_runtime_correctness_passed
            or not companion_behavior_quality_passed
            or not operator_ux_quality_passed
        ):
            return LocalCompanionCertificationVerdict.REPO_OR_RUNTIME_BUG
        if doctor_verdict == LocalCompanionCertificationVerdict.DEGRADED_BUT_ACCEPTABLE:
            return LocalCompanionCertificationVerdict.DEGRADED_BUT_ACCEPTABLE
        return LocalCompanionCertificationVerdict.CERTIFIED

    def _final_next_actions(self, record: LocalCompanionCertificationRecord) -> list[str]:
        if record.verdict == LocalCompanionCertificationVerdict.MACHINE_BLOCKER:
            return [
                "Fix the machine blockers from local-companion-doctor before using this Mac as a proof surface.",
                "Keep deterministic suites as the floor, but do not present the Mac as fully ready.",
                "Rerun local-companion-certify after the machine path is green.",
            ]
        if record.verdict == LocalCompanionCertificationVerdict.REPO_OR_RUNTIME_BUG:
            return [
                "Fix the failing local companion or operator-surface regression before shipping or demoing this lane.",
                "Review the failed certification sections and linked artifacts in the certification bundle.",
                "Rerun local-companion-certify once the regression is fixed.",
            ]
        if record.verdict == LocalCompanionCertificationVerdict.DEGRADED_BUT_ACCEPTABLE:
            return [
                "The companion is demo-usable, but still below the intended world-class local bar.",
                "Use the certification bundle and doctor report to close the remaining degraded warnings.",
                "Rerun local-companion-certify before presenting this as the primary Mac path.",
            ]
        return [
            "Safe to demo.",
            "Use the latest certification bundle as the operator evidence pack for this Mac.",
            f"Decision={RUNBOOK_DECISION_HINTS[record.verdict]}.",
        ]

    def _final_summary(self, record: LocalCompanionCertificationRecord) -> str:
        return (
            f"verdict={record.verdict.value} "
            f"machine_ready={record.machine_readiness_passed} "
            f"product_ready={record.repo_runtime_correctness_passed and record.companion_behavior_quality_passed and record.operator_ux_quality_passed} "
            f"blocked={len(record.blocking_issues)}"
        )

    def _write_json(self, path: Path, payload: object) -> None:
        write_json_atomic(path, self._normalize(payload))

    def _normalize(self, payload: object) -> object:
        if hasattr(payload, "model_dump"):
            return payload.model_dump(mode="json")
        if isinstance(payload, list):
            return [self._normalize(item) for item in payload]
        if isinstance(payload, dict):
            return {key: self._normalize(value) for key, value in payload.items()}
        return payload


class LocalCompanionBurnInRunner:
    def __init__(self, *, settings: Settings | None = None, output_dir: str | Path | None = None) -> None:
        self.settings = settings or get_settings()
        self.output_dir = Path(output_dir or burn_in_root(self.settings))
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def run(self) -> DemoCheckSuiteRecord:
        suite = DemoCheckSuiteRecord(
            configured_dialogue_backend=self.settings.brain_dialogue_backend,
            runtime_profile=self.settings.brain_runtime_profile,
            deployment_target=self.settings.brain_deployment_target,
        )
        suite_dir = self.output_dir / suite.suite_id
        suite_dir.mkdir(parents=True, exist_ok=True)
        suite.artifact_dir = str(suite_dir)

        checks = [
            (
                "periodic_text_turns",
                "Bounded repeated local text turns remain stable and exportable.",
                self._check_periodic_text_turns,
            ),
            (
                "reminder_workflow_continuity",
                "Note and reminder workflow artifacts survive runtime reopen.",
                self._check_reminder_workflow_continuity,
            ),
            (
                "interrupt_recovery",
                "Interrupted voice output recovers cleanly into the next turn.",
                self._check_interrupt_recovery,
            ),
            (
                "trigger_stability",
                "Always-on supervisor ticks stay bounded instead of repeating false triggers.",
                self._check_trigger_stability,
            ),
            (
                "startup_shutdown_cycles",
                "Repeated runtime start and stop cycles preserve usable terminal-first behavior.",
                self._check_startup_shutdown_cycles,
            ),
            (
                "mode_switching",
                "Repeated push-to-talk and open-mic mode switching does not leave stale voice-loop state behind.",
                self._check_mode_switching,
            ),
            (
                "artifact_linkage",
                "Episode export still links Action Plane bundle artifacts after repeated activity.",
                self._check_artifact_linkage,
            ),
        ]

        for check_name, description, handler in checks:
            check_dir = suite_dir / check_name
            check_dir.mkdir(parents=True, exist_ok=True)
            suite.items.append(handler(check_name=check_name, description=description, check_dir=check_dir))

        suite.completed_at = utc_now()
        suite.passed = all(item.passed for item in suite.items)
        suite.artifact_files["summary"] = str(suite_dir / "summary.json")
        self._write_json(Path(suite.artifact_files["summary"]), suite)
        return suite

    def _check_periodic_text_turns(self, *, check_name: str, description: str, check_dir: Path) -> DemoCheckResult:
        settings = self._runtime_settings(check_dir)
        with build_desktop_runtime(settings=settings, device_registry=FakeDeviceRegistry()) as runtime:
            session = runtime.ensure_session(session_id="local-companion-burn-in", user_id="burn-in-user", response_mode=ResponseMode.GUIDE)
            prompts = (
                "Hello there.",
                "Please remind me to review the burn-in notes later today.",
                "What do you remember that I need to do?",
                "Add a local note that this run should stay inspectable.",
                "What open follow-ups are still pending?",
                "Summarize what I should revisit next.",
            )
            replies: list[str] = []
            for prompt in prompts:
                interaction = runtime.submit_text(
                    prompt,
                    session_id=session.session_id,
                    user_id=session.user_id,
                    response_mode=ResponseMode.GUIDE,
                    voice_mode=VoiceRuntimeMode.STUB_DEMO,
                    speak_reply=False,
                    source="local_companion_burn_in",
                )
                replies.append(interaction.response.reply_text or "")
            snapshot = runtime.snapshot(session_id=session.session_id, voice_mode=VoiceRuntimeMode.STUB_DEMO)
            episode = runtime.export_session_episode(session.session_id)
        passed = len([item for item in replies if item]) == len(prompts) and snapshot.runtime.memory_status.transcript_turn_count >= len(prompts)
        return self._finalize_result(
            check_dir=check_dir,
            result=DemoCheckResult(
                check_name=check_name,
                description=description,
                completed_at=utc_now(),
                passed=passed,
                session_id=session.session_id,
                reply_text=replies[-1] if replies else None,
                notes=[f"turns={snapshot.runtime.memory_status.transcript_turn_count}", f"prompts={len(prompts)}"],
            ),
            payloads={
                "prompts": {"items": list(prompts)},
                "replies": {"items": replies},
                "snapshot": snapshot,
                "episode": episode,
            },
        )

    def _check_reminder_workflow_continuity(self, *, check_name: str, description: str, check_dir: Path) -> DemoCheckResult:
        settings = self._runtime_settings(check_dir)
        with build_desktop_runtime(settings=settings, device_registry=FakeDeviceRegistry()) as runtime:
            session = runtime.ensure_session(session_id="burn-in-workflow", user_id="burn-in-user", response_mode=ResponseMode.GUIDE)
            response = runtime.operator_console.start_action_plane_workflow(
                WorkflowStartRequestRecord(
                    workflow_id="capture_note_and_reminder",
                    session_id=session.session_id,
                    inputs={
                        "note_title": "Burn In Note",
                        "note_content": "Verify restart continuity for reminder workflow artifacts.",
                        "reminder_text": "Check the burn-in continuity results.",
                    },
                    note="burn_in",
                )
            )
            history_before = runtime.operator_console.list_action_plane_history(limit=10)
        with build_desktop_runtime(settings=settings, device_registry=FakeDeviceRegistry()) as runtime:
            history_after = runtime.operator_console.list_action_plane_history(limit=10)
            workflow_runs = runtime.operator_console.list_action_plane_workflow_runs(session_id=session.session_id, limit=10)
        passed = (
            response.status is not None
            and response.status.value == "completed"
            and len(history_after.items) >= len(history_before.items)
            and bool(workflow_runs.items)
        )
        return self._finalize_result(
            check_dir=check_dir,
            result=DemoCheckResult(
                check_name=check_name,
                description=description,
                completed_at=utc_now(),
                passed=passed,
                session_id=session.session_id,
                notes=[response.workflow_run_id or "-", f"history={len(history_after.items)}"],
            ),
            payloads={
                "workflow_start": response,
                "history_before": history_before,
                "history_after": history_after,
                "workflow_runs": workflow_runs,
            },
        )

    def _check_interrupt_recovery(self, *, check_name: str, description: str, check_dir: Path) -> DemoCheckResult:
        settings = self._runtime_settings(check_dir)
        registry = OpenMicRegistry([_speech_result(transcript_text="Please continue after the interruption.")])
        with build_desktop_runtime(settings=settings, device_registry=registry) as runtime:
            session = runtime.ensure_session(session_id="burn-in-interrupt", user_id="burn-in-user", response_mode=ResponseMode.GUIDE)
            runtime.configure_companion_loop(
                session_id=session.session_id,
                voice_mode=VoiceRuntimeMode.OPEN_MIC_LOCAL,
                speak_enabled=True,
                audio_mode=CompanionAudioMode.OPEN_MIC,
            )
            registry.speaker_output.force_speaking()
            interrupted = runtime.interrupt_voice(session_id=session.session_id, voice_mode=VoiceRuntimeMode.OPEN_MIC_LOCAL)
            interaction = runtime.submit_text(
                "Thanks, continue now.",
                session_id=session.session_id,
                user_id=session.user_id,
                response_mode=ResponseMode.GUIDE,
                voice_mode=VoiceRuntimeMode.STUB_DEMO,
                speak_reply=False,
                source="local_companion_burn_in_interrupt",
            )
            snapshot = runtime.snapshot(session_id=session.session_id, voice_mode=VoiceRuntimeMode.STUB_DEMO)
        passed = bool(
            interrupted.state.status.value == "interrupted"
            and interaction.response.reply_text
            and snapshot.runtime.voice_loop.interruption_count >= 1
        )
        return self._finalize_result(
            check_dir=check_dir,
            result=DemoCheckResult(
                check_name=check_name,
                description=description,
                completed_at=utc_now(),
                passed=passed,
                session_id=session.session_id,
                reply_text=interaction.response.reply_text,
                notes=[snapshot.runtime.voice_loop.state.value],
            ),
            payloads={
                "interrupt": interrupted,
                "interaction": interaction,
                "snapshot": snapshot,
            },
        )

    def _check_trigger_stability(self, *, check_name: str, description: str, check_dir: Path) -> DemoCheckResult:
        settings = self._runtime_settings(check_dir)
        with build_desktop_runtime(settings=settings, device_registry=FakeDeviceRegistry()) as runtime:
            session = runtime.ensure_session(session_id="burn-in-trigger", user_id="burn-in-user", response_mode=ResponseMode.GUIDE)
            runtime.submit_scene_observation(
                session_id=session.session_id,
                user_id=session.user_id,
                person_present=True,
                people_count=1,
                engagement="engaged",
                scene_note="burn_in_trigger_probe",
            )
            for _ in range(3):
                runtime.run_supervisor_once()
            snapshot = runtime.snapshot(session_id=session.session_id, voice_mode=VoiceRuntimeMode.STUB_DEMO)
            events = runtime.drain_runtime_events()
        trigger = snapshot.runtime.trigger_engine
        passed = trigger.trigger_count <= 1 and trigger.suppression_count >= 0
        return self._finalize_result(
            check_dir=check_dir,
            result=DemoCheckResult(
                check_name=check_name,
                description=description,
                completed_at=utc_now(),
                passed=passed,
                session_id=session.session_id,
                notes=[f"trigger_count={trigger.trigger_count}", f"suppression_count={trigger.suppression_count}"],
            ),
            payloads={"snapshot": snapshot, "events": events},
        )

    def _check_startup_shutdown_cycles(self, *, check_name: str, description: str, check_dir: Path) -> DemoCheckResult:
        settings = self._runtime_settings(check_dir)
        cycles: list[dict[str, object]] = []
        for index in range(3):
            with build_desktop_runtime(settings=settings, device_registry=FakeDeviceRegistry()) as runtime:
                session = runtime.ensure_session(
                    session_id=f"burn-in-restart-{index}",
                    user_id="burn-in-user",
                    response_mode=ResponseMode.GUIDE,
                )
                interaction = runtime.submit_text(
                    f"Restart cycle {index}: what should I keep in mind?",
                    session_id=session.session_id,
                    user_id=session.user_id,
                    response_mode=ResponseMode.GUIDE,
                    voice_mode=VoiceRuntimeMode.STUB_DEMO,
                    speak_reply=False,
                    source="local_companion_burn_in_restart",
                )
                snapshot = runtime.snapshot(session_id=session.session_id, voice_mode=VoiceRuntimeMode.STUB_DEMO)
                cycles.append(
                    {
                        "session_id": session.session_id,
                        "reply_text": interaction.response.reply_text,
                        "transcript_turn_count": snapshot.runtime.memory_status.transcript_turn_count,
                        "presence_state": snapshot.runtime.presence_runtime.state.value,
                        "voice_state": snapshot.runtime.voice_loop.state.value,
                    }
                )
        passed = all(
            item["reply_text"] and int(item["transcript_turn_count"]) >= 1 and item["voice_state"] in {"idle", "cooldown"}
            for item in cycles
        )
        return self._finalize_result(
            check_dir=check_dir,
            result=DemoCheckResult(
                check_name=check_name,
                description=description,
                completed_at=utc_now(),
                passed=passed,
                session_id=str(cycles[-1]["session_id"]) if cycles else None,
                reply_text=str(cycles[-1]["reply_text"]) if cycles else None,
                notes=[f"cycles={len(cycles)}"],
            ),
            payloads={"cycles": cycles},
        )

    def _check_mode_switching(self, *, check_name: str, description: str, check_dir: Path) -> DemoCheckResult:
        settings = self._runtime_settings(check_dir)
        step_definitions = [
            (VoiceRuntimeMode.STUB_DEMO, CompanionAudioMode.PUSH_TO_TALK, "idle", None),
            (VoiceRuntimeMode.OPEN_MIC_LOCAL, CompanionAudioMode.OPEN_MIC, "vad_waiting", "whisper_cpp_local"),
            (VoiceRuntimeMode.MACOS_SAY, CompanionAudioMode.PUSH_TO_TALK, "idle", None),
            (VoiceRuntimeMode.OPEN_MIC_LOCAL, CompanionAudioMode.OPEN_MIC, "vad_waiting", "whisper_cpp_local"),
            (VoiceRuntimeMode.DESKTOP_NATIVE, CompanionAudioMode.PUSH_TO_TALK, "idle", None),
        ]
        steps: list[dict[str, object]] = []
        with build_desktop_runtime(settings=settings, device_registry=FakeDeviceRegistry()) as runtime:
            session = runtime.ensure_session(session_id="burn-in-mode-switch", user_id="burn-in-user", response_mode=ResponseMode.GUIDE)
            for voice_mode, audio_mode, expected_state, expected_backend in step_definitions:
                runtime.configure_companion_loop(
                    session_id=session.session_id,
                    voice_mode=voice_mode,
                    speak_enabled=voice_mode != VoiceRuntimeMode.STUB_DEMO,
                    audio_mode=audio_mode,
                )
                snapshot = runtime.snapshot(session_id=session.session_id, voice_mode=voice_mode)
                steps.append(
                    {
                        "voice_mode": voice_mode.value,
                        "audio_mode": audio_mode.value,
                        "expected_state": expected_state,
                        "expected_backend": expected_backend,
                        "actual_state": snapshot.runtime.voice_loop.state.value,
                        "actual_backend": snapshot.runtime.voice_loop.audio_backend,
                    }
                )
        passed = all(
            item["actual_state"] == item["expected_state"] and item["actual_backend"] == item["expected_backend"]
            for item in steps
        )
        return self._finalize_result(
            check_dir=check_dir,
            result=DemoCheckResult(
                check_name=check_name,
                description=description,
                completed_at=utc_now(),
                passed=passed,
                session_id="burn-in-mode-switch",
                notes=[f"{item['voice_mode']}->{item['actual_state']}" for item in steps],
            ),
            payloads={"steps": steps},
        )

    def _check_artifact_linkage(self, *, check_name: str, description: str, check_dir: Path) -> DemoCheckResult:
        settings = self._runtime_settings(check_dir)
        with build_desktop_runtime(settings=settings, device_registry=FakeDeviceRegistry()) as runtime:
            session = runtime.ensure_session(session_id="burn-in-export", user_id="burn-in-user", response_mode=ResponseMode.GUIDE)
            runtime.submit_text(
                "Please capture a note and reminder for tomorrow's local demo review.",
                session_id=session.session_id,
                user_id=session.user_id,
                response_mode=ResponseMode.GUIDE,
                voice_mode=VoiceRuntimeMode.STUB_DEMO,
                speak_reply=False,
                source="local_companion_burn_in_export",
            )
            runtime.operator_console.start_action_plane_workflow(
                WorkflowStartRequestRecord(
                    workflow_id="capture_note_and_reminder",
                    session_id=session.session_id,
                    inputs={
                        "note_content": "Check action bundle linkage after burn-in export.",
                        "reminder_text": "Inspect the burn-in export artifacts.",
                    },
                    note="burn_in_export",
                )
            )
            episode = runtime.export_session_episode(session.session_id)
            bundles = runtime.operator_console.list_action_plane_bundles(session_id=session.session_id, limit=10)
        action_bundle_index = episode.derived_artifact_files.get("action_bundle_index")
        passed = bool(action_bundle_index and Path(action_bundle_index).exists() and bundles.items)
        return self._finalize_result(
            check_dir=check_dir,
            result=DemoCheckResult(
                check_name=check_name,
                description=description,
                completed_at=utc_now(),
                passed=passed,
                session_id=session.session_id,
                notes=[episode.episode_id, f"bundles={len(bundles.items)}"],
            ),
            payloads={"episode": episode, "bundles": bundles},
        )

    def _runtime_settings(self, check_dir: Path) -> Settings:
        return self.settings.model_copy(
            update={
                "blink_always_on_enabled": True,
                "blink_context_mode": CompanionContextMode.PERSONAL_LOCAL,
                "blink_model_profile": "offline_stub",
                "blink_backend_profile": "offline_safe",
                "brain_store_path": str(check_dir / "brain_store.json"),
                "demo_report_dir": str(check_dir / "demo_runs"),
                "demo_check_dir": str(check_dir / "demo_checks"),
                "episode_export_dir": str(check_dir / "episodes"),
                "shift_report_dir": str(check_dir / "shift_reports"),
                "operator_auth_runtime_file": str(check_dir / "operator_auth.json"),
                "blink_action_plane_draft_dir": str(check_dir / "actions" / "drafts"),
                "blink_action_plane_stage_dir": str(check_dir / "actions" / "staged"),
                "blink_action_plane_export_dir": str(check_dir / "actions" / "exports"),
                "blink_action_plane_browser_storage_dir": str(check_dir / "actions" / "browser"),
            }
        )

    def _finalize_result(self, *, check_dir: Path, result: DemoCheckResult, payloads: dict[str, object]) -> DemoCheckResult:
        result.artifact_files["summary"] = str(check_dir / "summary.json")
        self._write_json(Path(result.artifact_files["summary"]), result)
        for name, payload in payloads.items():
            path = check_dir / f"{name}.json"
            result.artifact_files[name] = str(path)
            self._write_json(path, payload)
        self._write_json(Path(result.artifact_files["summary"]), result)
        return result

    def _write_json(self, path: Path, payload: object) -> None:
        write_json_atomic(path, self._normalize(payload))

    def _normalize(self, payload: object) -> object:
        if hasattr(payload, "model_dump"):
            return payload.model_dump(mode="json")
        if isinstance(payload, list):
            return [self._normalize(item) for item in payload]
        if isinstance(payload, dict):
            return {key: self._normalize(value) for key, value in payload.items()}
        return payload


def main() -> None:
    record = run_local_companion_certification()
    print(
        json.dumps(
            {
                "cert_id": record.cert_id,
                "verdict": record.verdict.value,
                "machine_readiness_passed": record.machine_readiness_passed,
                "repo_runtime_correctness_passed": record.repo_runtime_correctness_passed,
                "companion_behavior_quality_passed": record.companion_behavior_quality_passed,
                "operator_ux_quality_passed": record.operator_ux_quality_passed,
                "artifact_dir": record.artifact_dir,
                "blocking_issues": record.blocking_issues,
            },
            indent=2,
        )
    )


def burn_in_main() -> None:
    suite = run_local_companion_burn_in()
    print(
        json.dumps(
            {
                "suite_id": suite.suite_id,
                "passed": suite.passed,
                "check_count": len(suite.items),
                "passed_count": sum(1 for item in suite.items if item.passed),
                "artifact_dir": suite.artifact_dir,
            },
            indent=2,
        )
    )


__all__ = [
    "LocalCompanionBurnInRunner",
    "LocalCompanionCertificationRunner",
    "burn_in_main",
    "certification_root",
    "load_latest_local_companion_certification",
    "load_latest_local_companion_readiness",
    "main",
    "run_local_companion_burn_in",
    "run_local_companion_certification",
]
