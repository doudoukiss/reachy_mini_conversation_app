from __future__ import annotations

import base64
import json
from pathlib import Path

from embodied_stack.backends.router import BackendRouter, OllamaProbeSnapshot
from embodied_stack.brain.perception import confidence_from_score
from embodied_stack.config import Settings, get_settings
from embodied_stack.desktop.app import build_desktop_runtime
from embodied_stack.demo.local_companion_checks import (
    FakeCameraCapture,
    FakeDeviceRegistry,
)
from embodied_stack.persistence import write_json_atomic
from embodied_stack.shared.models import (
    DemoCheckResult,
    DemoCheckSuiteRecord,
    EpisodeExportSessionRequest,
    PerceptionObservation,
    PerceptionObservationType,
    PerceptionProviderMode,
    PerceptionSnapshotRecord,
    PerceptionSnapshotStatus,
    RobotMode,
    ShiftSupervisorSnapshot,
    VoiceRuntimeMode,
    utc_now,
)


class StaticOllamaProbe:
    def __init__(self, snapshot: OllamaProbeSnapshot) -> None:
        self._snapshot = snapshot

    def snapshot(self) -> OllamaProbeSnapshot:
        return self._snapshot


class FakeSemanticVisionProvider:
    mode = PerceptionProviderMode.OLLAMA_VISION

    def analyze_snapshot(self, request):
        source_frame = request.source_frame.model_copy(deep=True)
        return PerceptionSnapshotRecord(
            session_id=request.session_id,
            provider_mode=self.mode,
            source=request.source,
            status=PerceptionSnapshotStatus.OK,
            limited_awareness=False,
            message="semantic_fixture_ready",
            scene_summary="A visitor is standing near the front desk sign.",
            source_frame=source_frame,
            observations=[
                PerceptionObservation(
                    observation_type=PerceptionObservationType.PERSON_VISIBILITY,
                    bool_value=True,
                    confidence=confidence_from_score(0.91),
                    source_frame=source_frame,
                ),
                PerceptionObservation(
                    observation_type=PerceptionObservationType.LOCATION_ANCHOR,
                    text_value="Front Desk",
                    confidence=confidence_from_score(0.88),
                    source_frame=source_frame,
                ),
                PerceptionObservation(
                    observation_type=PerceptionObservationType.SCENE_SUMMARY,
                    text_value="A visitor is standing near the front desk sign.",
                    confidence=confidence_from_score(0.9),
                    source_frame=source_frame,
                ),
            ],
        )


class SequenceCameraCapture(FakeCameraCapture):
    def __init__(self, frames: list[bytes]) -> None:
        self._frames = frames or [b"steady-frame"]
        self._index = 0

    def capture_snapshot(self):
        captured_at = utc_now()
        payload = self._frames[min(self._index, len(self._frames) - 1)]
        self._index += 1
        return type(
            "CameraCapture",
            (),
            {
                "image_data_url": "data:image/png;base64," + base64.b64encode(payload).decode("ascii"),
                "source_frame": self.source_frame_for(captured_at),
                "backend": "sequence_camera",
            },
        )()

    def source_frame_for(self, captured_at):
        from embodied_stack.shared.models import PerceptionSourceFrame

        return PerceptionSourceFrame(
            source_kind="native_camera_snapshot",
            source_label="sequence_camera",
            frame_id=f"sequence-{captured_at.strftime('%Y%m%d%H%M%S')}",
            mime_type="image/png",
            captured_at=captured_at,
        )


class SequenceDeviceRegistry(FakeDeviceRegistry):
    def __init__(self, frames: list[bytes]) -> None:
        super().__init__()
        self.camera_capture = SequenceCameraCapture(frames)


def run_always_on_local_checks(
    *,
    settings: Settings | None = None,
    output_dir: str | Path | None = None,
) -> DemoCheckSuiteRecord:
    runner = AlwaysOnLocalCheckRunner(settings=settings, output_dir=output_dir)
    return runner.run()


class AlwaysOnLocalCheckRunner:
    def __init__(self, *, settings: Settings | None = None, output_dir: str | Path | None = None) -> None:
        self.settings = settings or get_settings()
        self.output_dir = Path(output_dir or Path(self.settings.demo_check_dir) / "always_on_local")
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
            ("canonical_ollama_profile", "Local companion resolves to the canonical M4 Pro Ollama preset.", self._check_canonical_profile),
            ("ollama_status_fallback", "Unavailable Ollama routes degrade honestly into fallback backends.", self._check_fallback_status),
            ("voice_loop_transitions", "Push-to-talk transitions are recorded through cooldown.", self._check_voice_loop_transitions),
            ("interrupt_cancel", "Interrupt requests immediately mark the always-on voice loop as interrupted.", self._check_interrupt_cancel),
            ("scene_observer_refresh", "Cheap scene observation triggers refresh only on meaningful changes.", self._check_scene_observer_refresh),
            ("visual_query_refresh", "A visual question triggers semantic refresh before reply generation.", self._check_visual_query_refresh),
            ("memory_body_continuity", "Always-on memory recall remains available in both bodyless and virtual-body modes.", self._check_memory_body_continuity),
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

    def _check_canonical_profile(self, *, check_name: str, description: str, check_dir: Path) -> DemoCheckResult:
        settings = self._runtime_settings(check_dir, {"blink_model_profile": "desktop_local"})
        runtime = build_desktop_runtime(settings=settings, device_registry=FakeDeviceRegistry())
        snapshot = runtime.snapshot()
        passed = bool(
            snapshot.runtime.resolved_backend_profile == "companion_live"
            and runtime.settings.ollama_model == "qwen3.5:9b"
            and runtime.settings.ollama_embedding_model == "embeddinggemma:300m"
        )
        return self._finalize_result(
            check_dir=check_dir,
            result=DemoCheckResult(
                check_name=check_name,
                description=description,
                completed_at=utc_now(),
                passed=passed,
                notes=[snapshot.runtime.resolved_backend_profile or "-", runtime.settings.ollama_model, runtime.settings.ollama_embedding_model],
            ),
            payloads={"snapshot": snapshot},
        )

    def _check_fallback_status(self, *, check_name: str, description: str, check_dir: Path) -> DemoCheckResult:
        settings = self._runtime_settings(check_dir, {"blink_model_profile": "desktop_local"})
        router = BackendRouter(
            settings=settings,
            ollama_probe=StaticOllamaProbe(
                OllamaProbeSnapshot(
                    reachable=False,
                    installed_models=set(),
                    running_models=set(),
                    error="ollama_unreachable",
                )
            ),
        )
        runtime = build_desktop_runtime(settings=settings, device_registry=FakeDeviceRegistry(), backend_router=router)
        snapshot = runtime.snapshot()
        passed = bool(
            snapshot.runtime.text_backend == "rule_based"
            and snapshot.runtime.embedding_backend == "hash_embed"
            and any(item.status.value == "fallback_active" for item in snapshot.runtime.backend_status)
        )
        return self._finalize_result(
            check_dir=check_dir,
            result=DemoCheckResult(
                check_name=check_name,
                description=description,
                completed_at=utc_now(),
                passed=passed,
                notes=[item.status.value for item in snapshot.runtime.backend_status],
            ),
            payloads={"snapshot": snapshot},
        )

    def _check_voice_loop_transitions(self, *, check_name: str, description: str, check_dir: Path) -> DemoCheckResult:
        settings = self._runtime_settings(check_dir, {"blink_runtime_mode": RobotMode.DESKTOP_BODYLESS})
        runtime = build_desktop_runtime(settings=settings, device_registry=FakeDeviceRegistry())
        session = runtime.ensure_session(session_id="always-on-voice")
        runtime.configure_companion_loop(session_id=session.session_id, voice_mode=VoiceRuntimeMode.DESKTOP_NATIVE, speak_enabled=True)
        interaction = runtime.submit_live_turn(
            session_id=session.session_id,
            voice_mode=VoiceRuntimeMode.DESKTOP_NATIVE,
            speak_reply=True,
            capture_camera=False,
        )
        artifacts = runtime.supervisor.export_artifacts()
        states = [item["state"] for item in artifacts["voice_loop"]["history"]]
        passed = states[:2] == ["armed", "capturing"] and "speaking" in states and states[-1] == "cooldown"
        return self._finalize_result(
            check_dir=check_dir,
            result=DemoCheckResult(
                check_name=check_name,
                description=description,
                completed_at=utc_now(),
                passed=passed,
                session_id=session.session_id,
                reply_text=interaction.interaction.response.reply_text,
                latency_ms=interaction.interaction.latency_ms,
                notes=states,
            ),
            payloads={"interaction": interaction, "voice_loop": artifacts["voice_loop"]},
        )

    def _check_interrupt_cancel(self, *, check_name: str, description: str, check_dir: Path) -> DemoCheckResult:
        settings = self._runtime_settings(check_dir, {"blink_runtime_mode": RobotMode.DESKTOP_BODYLESS})
        runtime = build_desktop_runtime(settings=settings, device_registry=FakeDeviceRegistry())
        session = runtime.ensure_session(session_id="always-on-interrupt")
        runtime.configure_companion_loop(session_id=session.session_id, voice_mode=VoiceRuntimeMode.DESKTOP_NATIVE, speak_enabled=True)
        runtime.supervisor.prepare_live_listen(session_id=session.session_id, voice_mode=VoiceRuntimeMode.DESKTOP_NATIVE)
        result = runtime.interrupt_voice(session_id=session.session_id, voice_mode=VoiceRuntimeMode.DESKTOP_NATIVE)
        snapshot = runtime.snapshot(session_id=session.session_id, voice_mode=VoiceRuntimeMode.DESKTOP_NATIVE)
        passed = bool(result.state.status.value == "interrupted" and snapshot.runtime.voice_loop.state.value == "interrupted")
        return self._finalize_result(
            check_dir=check_dir,
            result=DemoCheckResult(
                check_name=check_name,
                description=description,
                completed_at=utc_now(),
                passed=passed,
                session_id=session.session_id,
                notes=[snapshot.runtime.voice_loop.state.value],
            ),
            payloads={"cancel_result": result, "snapshot": snapshot},
        )

    def _check_scene_observer_refresh(self, *, check_name: str, description: str, check_dir: Path) -> DemoCheckResult:
        settings = self._runtime_settings(
            check_dir,
            {
                "blink_runtime_mode": RobotMode.DESKTOP_BODYLESS,
                "blink_backend_profile": "m4_pro_companion",
                "ollama_text_model": "qwen3.5:9b",
                "ollama_vision_model": "qwen3.5:9b",
                "ollama_embedding_model": "embeddinggemma:300m",
            },
        )
        router = BackendRouter(
            settings=settings,
            ollama_probe=StaticOllamaProbe(
                OllamaProbeSnapshot(
                    reachable=True,
                    installed_models={"qwen3.5:9b", "embeddinggemma:300m"},
                    running_models={"qwen3.5:9b"},
                    latency_ms=38.0,
                )
            ),
        )
        runtime = build_desktop_runtime(
            settings=settings,
            device_registry=SequenceDeviceRegistry([b"steady-frame", b"steady-frame", b"changed-frame"]),
            backend_router=router,
        )
        session = runtime.ensure_session(session_id="always-on-observer")
        runtime.configure_companion_loop(session_id=session.session_id, voice_mode=VoiceRuntimeMode.STUB_DEMO, speak_enabled=False)
        runtime.run_supervisor_once()
        runtime.supervisor._last_observer_poll_at = 0.0
        runtime.run_supervisor_once()
        runtime.supervisor._last_observer_poll_at = 0.0
        runtime.run_supervisor_once()
        artifacts = runtime.supervisor.export_artifacts()
        history = artifacts["scene_observer"]["history"]
        refresh_decisions = [item for item in artifacts["trigger_history"]["history"] if item["decision"] == "refresh_scene"]
        passed = bool(len(history) >= 2 and len(refresh_decisions) >= 1)
        return self._finalize_result(
            check_dir=check_dir,
            result=DemoCheckResult(
                check_name=check_name,
                description=description,
                completed_at=utc_now(),
                passed=passed,
                session_id=session.session_id,
                notes=[item["decision"] for item in artifacts["trigger_history"]["history"]],
            ),
            payloads={"scene_observer": artifacts["scene_observer"], "trigger_history": artifacts["trigger_history"]},
        )

    def _check_visual_query_refresh(self, *, check_name: str, description: str, check_dir: Path) -> DemoCheckResult:
        settings = self._runtime_settings(
            check_dir,
            {
                "blink_runtime_mode": RobotMode.DESKTOP_BODYLESS,
                "blink_backend_profile": "m4_pro_companion",
                "ollama_text_model": "qwen3.5:9b",
                "ollama_vision_model": "qwen3.5:9b",
                "ollama_embedding_model": "embeddinggemma:300m",
            },
        )
        router = BackendRouter(
            settings=settings,
            ollama_probe=StaticOllamaProbe(
                OllamaProbeSnapshot(
                    reachable=True,
                    installed_models={"qwen3.5:9b", "embeddinggemma:300m"},
                    running_models={"qwen3.5:9b"},
                    latency_ms=42.0,
                )
            ),
        )
        runtime = build_desktop_runtime(settings=settings, device_registry=FakeDeviceRegistry(), backend_router=router)
        runtime.operator_console.perception_service.providers[PerceptionProviderMode.OLLAMA_VISION] = FakeSemanticVisionProvider()
        session = runtime.ensure_session(session_id="always-on-visual")
        runtime.configure_companion_loop(session_id=session.session_id, voice_mode=VoiceRuntimeMode.STUB_DEMO, speak_enabled=False)
        interaction = runtime.submit_text(
            "What do you see right now?",
            session_id=session.session_id,
            voice_mode=VoiceRuntimeMode.STUB_DEMO,
            speak_reply=False,
            source="always_on_suite",
        )
        latest = runtime.perception_service.get_latest_snapshot(session.session_id)
        episode = runtime.operator_console.export_session_episode(
            EpisodeExportSessionRequest(session_id=session.session_id, include_asset_refs=True)
        )
        passed = bool(
            latest is not None
            and latest.provider_mode == PerceptionProviderMode.OLLAMA_VISION
            and latest.limited_awareness is False
            and all(name in episode.artifact_files for name in ("scene_observer", "trigger_history", "voice_loop", "ollama_runtime"))
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
            ),
            payloads={"latest_perception": latest, "episode": episode, "interaction": interaction},
        )

    def _check_memory_body_continuity(self, *, check_name: str, description: str, check_dir: Path) -> DemoCheckResult:
        bodyless_settings = self._runtime_settings(check_dir / "bodyless", {"blink_runtime_mode": RobotMode.DESKTOP_BODYLESS})
        virtual_settings = self._runtime_settings(check_dir / "virtual", {"blink_runtime_mode": RobotMode.DESKTOP_VIRTUAL_BODY})

        bodyless_runtime = build_desktop_runtime(settings=bodyless_settings, device_registry=FakeDeviceRegistry())
        virtual_runtime = build_desktop_runtime(settings=virtual_settings, device_registry=FakeDeviceRegistry())

        for runtime, session_id in ((bodyless_runtime, "always-on-memory-bodyless"), (virtual_runtime, "always-on-memory-virtual")):
            runtime.configure_companion_loop(session_id=session_id, voice_mode=VoiceRuntimeMode.STUB_DEMO, speak_enabled=False)
            runtime.submit_text(
                "My name is Alex and I prefer the quiet route.",
                session_id=session_id,
                user_id="alex-user",
                voice_mode=VoiceRuntimeMode.STUB_DEMO,
                speak_reply=False,
            )
            runtime.submit_text(
                "Do you remember me?",
                session_id=session_id,
                user_id="alex-user",
                voice_mode=VoiceRuntimeMode.STUB_DEMO,
                speak_reply=False,
            )

        bodyless_snapshot = bodyless_runtime.snapshot(session_id="always-on-memory-bodyless", voice_mode=VoiceRuntimeMode.STUB_DEMO)
        virtual_snapshot = virtual_runtime.snapshot(session_id="always-on-memory-virtual", voice_mode=VoiceRuntimeMode.STUB_DEMO)
        passed = bool(
            bodyless_snapshot.runtime.memory_status.profile_memory_available
            and virtual_snapshot.runtime.memory_status.profile_memory_available
            and bodyless_snapshot.runtime.body_driver_mode.value == "bodyless"
            and virtual_snapshot.runtime.body_driver_mode.value == "virtual"
        )
        return self._finalize_result(
            check_dir=check_dir,
            result=DemoCheckResult(
                check_name=check_name,
                description=description,
                completed_at=utc_now(),
                passed=passed,
                notes=[
                    bodyless_snapshot.runtime.memory_status.status,
                    virtual_snapshot.runtime.memory_status.status,
                ],
            ),
            payloads={"bodyless_snapshot": bodyless_snapshot, "virtual_snapshot": virtual_snapshot},
        )

    def _runtime_settings(self, check_dir: Path, overrides: dict[str, object] | None = None) -> Settings:
        settings_data = self.settings.model_dump()
        settings_data.update(
            {
                "brain_store_path": str(check_dir / "brain_store.json"),
                "demo_report_dir": str(check_dir / "demo_runs"),
                "demo_check_dir": str(self.output_dir),
                "episode_export_dir": str(check_dir / "episodes"),
                "shift_report_dir": str(check_dir / "shift_reports"),
                "operator_auth_runtime_file": str(check_dir / "operator_auth.json"),
                "brain_voice_backend": "stub",
                "live_voice_default_mode": "stub_demo",
                "blink_model_profile": "desktop_local",
                "blink_voice_profile": "desktop_local",
                "blink_always_on_enabled": True,
            }
        )
        if overrides:
            settings_data.update(overrides)
        return Settings(_env_file=None, **settings_data)

    def _finalize_result(
        self,
        *,
        check_dir: Path,
        result: DemoCheckResult,
        payloads: dict[str, object],
    ) -> DemoCheckResult:
        artifact_files: dict[str, str] = {}
        for name, payload in payloads.items():
            if payload is None:
                continue
            path = check_dir / f"{name}.json"
            self._write_json(path, payload)
            artifact_files[name] = str(path)
        summary_path = check_dir / "summary.json"
        result.artifact_files = artifact_files
        self._write_json(summary_path, result)
        result.artifact_files["summary"] = str(summary_path)
        self._write_json(summary_path, result)
        return result

    def _write_json(self, path: Path, payload: object) -> None:
        write_json_atomic(path, self._normalize(payload))

    def _normalize(self, payload: object):
        if hasattr(payload, "model_dump"):
            return payload.model_dump(mode="json")
        if hasattr(payload, "__dict__"):
            return {
                key: self._normalize(value)
                for key, value in vars(payload).items()
                if not key.startswith("_")
            }
        if isinstance(payload, list):
            return [self._normalize(item) for item in payload]
        if isinstance(payload, dict):
            return {key: self._normalize(value) for key, value in payload.items()}
        return payload


def main() -> None:
    suite = run_always_on_local_checks()
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


if __name__ == "__main__":
    main()
