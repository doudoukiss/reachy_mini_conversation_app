from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from embodied_stack.backends.router import BackendRouter
from embodied_stack.brain.live_voice import LiveVoiceRuntimeManager
from embodied_stack.brain.operator_console import OperatorConsoleService
from embodied_stack.brain.orchestrator import BrainOrchestrator
from embodied_stack.brain.perception import PerceptionService
from embodied_stack.config import Settings, get_settings
from embodied_stack.demo.checks import InProcessDemoRuntime
from embodied_stack.demo.coordinator import DemoCoordinator
from embodied_stack.demo.episodes import EpisodeStore, build_exporter
from embodied_stack.demo.shift_reports import ShiftReportStore
from embodied_stack.desktop.runtime import build_inprocess_embodiment_gateway
from embodied_stack.desktop.devices import build_desktop_device_registry
from embodied_stack.persistence import write_json_atomic
from embodied_stack.shared.models import (
    BrainResetRequest,
    DemoCheckResult,
    DemoCheckSuiteRecord,
    InvestorSceneRunRequest,
    ResponseMode,
    VoiceRuntimeMode,
    utc_now,
)


def run_multimodal_checks(
    *,
    settings: Settings | None = None,
    output_dir: str | Path | None = None,
) -> DemoCheckSuiteRecord:
    runner = MultimodalCheckRunner(settings=settings, output_dir=output_dir)
    return runner.run()


@dataclass
class MultimodalCheckRunner:
    settings: Settings | None = None
    output_dir: str | Path | None = None

    def __post_init__(self) -> None:
        self.settings = self.settings or get_settings()
        self.output_dir = Path(self.output_dir or Path(self.settings.demo_check_dir) / "multimodal")
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def run(self) -> DemoCheckSuiteRecord:
        suite = DemoCheckSuiteRecord(
            configured_dialogue_backend=self.settings.brain_dialogue_backend,
            runtime_profile=self.settings.brain_runtime_profile,
            deployment_target=self.settings.brain_deployment_target,
        )
        suite_dir = Path(self.output_dir) / suite.suite_id
        suite_dir.mkdir(parents=True, exist_ok=True)
        suite.artifact_dir = str(suite_dir)

        scenes = [
            ("approach_and_greet", "Perception-grounded approach cue becomes an automatic greeting."),
            ("two_person_attention_handoff", "Attention follows the active speaker when two people are in view."),
            ("disengagement_shortening", "Disengagement causes a visibly shorter response."),
            ("scene_grounded_comment", "A scene comment is grounded in normalized semantic facts rather than raw prompt context."),
            ("uncertainty_admission", "Limited awareness leads to an explicit uncertainty admission."),
            ("stale_scene_suppression", "Stale semantic context is not treated as current scene truth."),
            (
                "operator_correction_after_wrong_scene_interpretation",
                "Operator annotations override an earlier scene interpretation and become the grounded answer.",
            ),
        ]

        for scene_name, description in scenes:
            check_dir = suite_dir / scene_name
            check_dir.mkdir(parents=True, exist_ok=True)
            suite.items.append(
                self._run_scene_check(
                    scene_name=scene_name,
                    description=description,
                    check_dir=check_dir,
                )
            )

        suite.completed_at = utc_now()
        suite.passed = all(item.passed for item in suite.items)
        suite.artifact_files["summary"] = str(suite_dir / "summary.json")
        self._write_json(Path(suite.artifact_files["summary"]), suite)
        return suite

    def _run_scene_check(
        self,
        *,
        scene_name: str,
        description: str,
        check_dir: Path,
    ) -> DemoCheckResult:
        runtime = self._build_runtime(check_dir)
        started_at = utc_now()
        scene = runtime.operator_console.run_investor_scene(
            scene_name,
            InvestorSceneRunRequest(
                session_id=f"multimodal-{scene_name}",
                response_mode=ResponseMode.GUIDE,
                voice_mode=VoiceRuntimeMode.STUB_DEMO,
                speak_reply=False,
            ),
        )

        result = DemoCheckResult(
            check_name=scene_name,
            description=description,
            started_at=started_at,
            completed_at=utc_now(),
            passed=scene.success and bool(scene.scorecard and scene.scorecard.passed),
            session_id=scene.session_id,
            scenario_names=[scene_name],
            backend_used=scene.items[-1].response.trace_id and runtime.orchestrator.get_trace(scene.items[-1].response.trace_id).reasoning.engine
            if scene.items and scene.items[-1].response.trace_id and runtime.orchestrator.get_trace(scene.items[-1].response.trace_id)
            else None,
            reply_text=scene.final_action.reply_text if scene.final_action else None,
            command_types=scene.final_action.command_types if scene.final_action else [],
            latency_ms=scene.latency_breakdown.total_ms,
            fallback_events=[],
            final_world_state=runtime.orchestrator.get_world_state(),
            latency_breakdown=scene.latency_breakdown,
            grounding_sources=scene.grounding_sources,
            scorecard=scene.scorecard,
            notes=[scene.note or "scene_completed"],
        )

        artifact_files = {
            "scene_result": check_dir / "scene_result.json",
            "scorecard": check_dir / "scorecard.json",
            "perception_snapshots": check_dir / "perception_snapshots.json",
            "world_model_transitions": check_dir / "world_model_transitions.json",
            "engagement_timeline": check_dir / "engagement_timeline.json",
            "executive_decisions": check_dir / "executive_decisions.json",
            "grounding_sources": check_dir / "grounding_sources.json",
            "summary": check_dir / "summary.json",
        }
        self._write_json(artifact_files["scene_result"], scene)
        self._write_json(artifact_files["scorecard"], scene.scorecard)
        self._write_json(artifact_files["perception_snapshots"], scene.perception_snapshots)
        self._write_json(artifact_files["world_model_transitions"], scene.world_model_transitions)
        self._write_json(artifact_files["engagement_timeline"], scene.engagement_timeline)
        self._write_json(artifact_files["executive_decisions"], scene.executive_decisions)
        self._write_json(artifact_files["grounding_sources"], scene.grounding_sources)
        result.artifact_files = {name: str(path) for name, path in artifact_files.items()}
        self._write_json(artifact_files["summary"], result)
        return result

    def _build_runtime(self, check_dir: Path) -> InProcessDemoRuntime:
        runtime_settings = Settings(
            **{
                **self.settings.model_dump(),
                "brain_store_path": str(check_dir / "brain_store.json"),
                "demo_report_dir": str(check_dir / "demo_runs"),
                "demo_check_dir": str(self.output_dir),
                "episode_export_dir": str(check_dir / "episodes"),
                "brain_voice_backend": "stub",
                "live_voice_default_mode": "stub_demo",
            }
        )
        backend_router = BackendRouter(settings=runtime_settings)
        edge_gateway = build_inprocess_embodiment_gateway(runtime_settings)
        orchestrator = BrainOrchestrator(
            settings=runtime_settings,
            store_path=runtime_settings.brain_store_path,
            backend_router=backend_router,
        )
        coordinator = DemoCoordinator(
            orchestrator=orchestrator,
            edge_gateway=edge_gateway,
            report_dir=runtime_settings.demo_report_dir,
        )
        device_registry = build_desktop_device_registry(runtime_settings)
        voice_manager = LiveVoiceRuntimeManager(
            settings=runtime_settings,
            device_registry=device_registry,
            macos_voice_name=runtime_settings.macos_tts_voice,
            macos_rate=runtime_settings.macos_tts_rate,
        )
        perception_service = PerceptionService(
            settings=runtime_settings,
            memory=orchestrator.memory,
            event_handler=orchestrator.handle_event,
            providers=backend_router.build_perception_providers(),
        )
        operator_console = OperatorConsoleService(
            settings=runtime_settings,
            orchestrator=orchestrator,
            edge_gateway=coordinator.edge_gateway,
            demo_coordinator=coordinator,
            shift_report_store=ShiftReportStore(runtime_settings.shift_report_dir),
            voice_manager=voice_manager,
            backend_router=backend_router,
            device_registry=device_registry,
            perception_service=perception_service,
            episode_exporter=build_exporter(
                settings=runtime_settings,
                orchestrator=orchestrator,
                report_store=coordinator.report_store,
                episode_store=EpisodeStore(runtime_settings.episode_export_dir),
                edge_gateway=coordinator.edge_gateway,
            ),
        )
        coordinator.reset_system(
            BrainResetRequest(
                reset_edge=True,
                clear_user_memory=True,
                clear_demo_runs=True,
            )
        )
        return InProcessDemoRuntime(
            settings=runtime_settings,
            edge_gateway=edge_gateway,
            orchestrator=orchestrator,
            coordinator=coordinator,
            operator_console=operator_console,
        )

    def _write_json(self, path: Path, payload: object) -> None:
        write_json_atomic(path, self._normalize_payload(payload))

    def _normalize_payload(self, payload: object):
        if payload is None:
            return None
        if hasattr(payload, "model_dump"):
            return payload.model_dump(mode="json")
        if isinstance(payload, list):
            return [self._normalize_payload(item) for item in payload]
        if isinstance(payload, dict):
            return {key: self._normalize_payload(value) for key, value in payload.items()}
        return payload


def main() -> None:
    suite = run_multimodal_checks()
    summary = {
        "suite_id": suite.suite_id,
        "passed": suite.passed,
        "check_count": len(suite.items),
        "passed_count": sum(1 for item in suite.items if item.passed),
        "artifact_dir": suite.artifact_dir,
    }
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
