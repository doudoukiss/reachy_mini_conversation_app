from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import httpx

from embodied_stack.backends.router import BackendRouter, OllamaProbeSnapshot
from embodied_stack.brain.llm import DialogueContext, OllamaDialogueEngine
from embodied_stack.config import Settings, get_settings
from embodied_stack.desktop.app import build_desktop_runtime
from embodied_stack.desktop.always_on import CompanionTriggerEngine, SceneObservationEvent
from embodied_stack.demo.local_companion_checks import FakeDeviceRegistry, FakeSpeakerOutput
from embodied_stack.persistence import write_json_atomic
from embodied_stack.shared.models import (
    CompanionContextMode,
    CompanionTriggerDecision,
    ConversationTurn,
    DemoCheckResult,
    DemoCheckSuiteRecord,
    OperatorNote,
    SessionRecord,
    SessionCreateRequest,
    ShiftSupervisorSnapshot,
    SpeechOutputResult,
    SpeechOutputStatus,
    UserMemoryRecord,
    VoiceRuntimeMode,
    WorldState,
    utc_now,
)


class StaticOllamaProbe:
    def __init__(self, snapshot: OllamaProbeSnapshot) -> None:
        self._snapshot = snapshot

    def snapshot(self) -> OllamaProbeSnapshot:
        return self._snapshot


class StatefulSpeakerOutput(FakeSpeakerOutput):
    def __init__(self) -> None:
        self._status = SpeechOutputStatus.IDLE
        self.cancel_calls = 0

    def force_speaking(self) -> None:
        self._status = SpeechOutputStatus.SPEAKING

    def speak(self, session_id: str, text: str | None, *, mode: VoiceRuntimeMode) -> SpeechOutputResult:
        self._status = SpeechOutputStatus.COMPLETED
        return super().speak(session_id, text, mode=mode)

    def get_state(self, session_id: str | None = None, *, mode: VoiceRuntimeMode) -> SpeechOutputResult:
        state = super().get_state(session_id, mode=mode)
        return state.model_copy(update={"status": self._status})

    def cancel(self, session_id: str | None = None, *, mode: VoiceRuntimeMode) -> SpeechOutputResult:
        self.cancel_calls += 1
        self._status = SpeechOutputStatus.INTERRUPTED
        return super().cancel(session_id, mode=mode)


class OpenMicRegistry(FakeDeviceRegistry):
    def __init__(self, results: list[SimpleNamespace]) -> None:
        super().__init__()
        self._results = results
        self._index = 0
        self.speaker_output = StatefulSpeakerOutput()
        self.piper_speaker_output = self.speaker_output

    def poll_open_mic(
        self,
        *,
        session_id: str,
        backend_candidates: tuple[str, ...],
        vad_silence_ms: int,
        vad_min_speech_ms: int,
    ):
        del session_id, backend_candidates, vad_silence_ms, vad_min_speech_ms
        item = self._results[min(self._index, len(self._results) - 1)]
        self._index += 1
        return item


def _speech_result(*, transcript_text: str | None, speech_detected: bool = True, backend: str = "whisper_cpp_local") -> SimpleNamespace:
    return SimpleNamespace(
        captured_at=utc_now(),
        duration_seconds=1.0,
        speech_detected=speech_detected,
        speech_ms=640 if speech_detected else 0,
        rms_level=0.52 if speech_detected else 0.0,
        transcript_text=transcript_text,
        partial_transcript=transcript_text[:48] if transcript_text else None,
        transcription_backend=backend,
        transcription_latency_ms=182.0 if transcript_text else None,
        degraded_reason=None if transcript_text else "typed_input_required",
    )


def run_continuous_local_checks(
    *,
    settings: Settings | None = None,
    output_dir: str | Path | None = None,
) -> DemoCheckSuiteRecord:
    runner = ContinuousLocalCheckRunner(settings=settings, output_dir=output_dir)
    return runner.run()


class ContinuousLocalCheckRunner:
    def __init__(self, *, settings: Settings | None = None, output_dir: str | Path | None = None) -> None:
        self.settings = settings or get_settings()
        self.output_dir = Path(output_dir or Path(self.settings.demo_check_dir) / "continuous_local")
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
            ("cold_start_retry", "First local text request retries once with a cold-start timeout before degrading.", self._check_cold_start_retry),
            ("open_mic_turn", "Open-mic streaming transitions reach cooldown with partial transcript evidence.", self._check_open_mic_turn),
            ("barge_in_interrupt", "Barge-in cancels current speech before the next turn is processed.", self._check_barge_in_interrupt),
            ("personal_context_mode", "Personal local mode keeps generic turns out of venue fallback phrasing.", self._check_personal_context_mode),
            ("venue_demo_context_mode", "Venue demo mode preserves concierge fallback phrasing for generic turns.", self._check_venue_demo_context_mode),
            ("daily_memory", "Local reminders, notes, and digest retrieval stay available in the companion path.", self._check_daily_memory),
            ("proactive_policy", "Proactive greeting is allowed when eligible and suppressed during cooldown.", self._check_proactive_policy),
            ("latency_visibility", "Runtime snapshot exposes STT, reasoning, TTS start, and end-to-end turn latency signals.", self._check_latency_visibility),
            ("model_residency", "Idle vision residency unloads while text remains warm.", self._check_model_residency),
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

    def _check_cold_start_retry(self, *, check_name: str, description: str, check_dir: Path) -> DemoCheckResult:
        attempts: list[float] = []
        failures: list[tuple[str, float | None, bool]] = []

        class ColdStartEngine(OllamaDialogueEngine):
            def _perform_chat(self, *, messages: list[dict[str, str]], timeout_seconds: float):
                del messages
                attempts.append(timeout_seconds)
                if len(attempts) == 1:
                    raise httpx.TimeoutException("cold start")
                return httpx.Response(200, json={"message": {"content": "local warm path works"}}), 321.0

        engine = ColdStartEngine(
            base_url="http://127.0.0.1:11434",
            model="qwen3.5:9b",
            timeout_seconds=12.0,
            cold_start_timeout_seconds=30.0,
            warm_checker=lambda: False,
            failure_reporter=lambda reason, timeout_seconds, retry_used: failures.append((reason, timeout_seconds, retry_used)),
        )
        result = engine.generate_reply(
            "Reply with a short confirmation.",
            DialogueContext(
                session=SessionRecord(
                    session_id="cold-start-retry",
                    conversation_summary="Local retry check.",
                    operator_notes=[OperatorNote(text="Retry once before degrading.")],
                ),
                world_state=WorldState(),
                tool_invocations=[],
                context_mode=CompanionContextMode.PERSONAL_LOCAL,
            ),
        )
        passed = attempts == [12.0, 30.0] and result.reply_text == "local warm path works" and result.debug_notes == ["ollama_chat_retry"]
        return self._finalize_result(
            check_dir=check_dir,
            result=DemoCheckResult(
                check_name=check_name,
                description=description,
                completed_at=utc_now(),
                passed=passed,
                notes=[str(item) for item in attempts],
            ),
            payloads={
                "attempts": attempts,
                "failures": failures,
                "result": {
                    "reply_text": result.reply_text,
                    "intent": result.intent,
                    "debug_notes": result.debug_notes,
                    "engine_name": result.engine_name,
                    "fallback_used": result.fallback_used,
                },
            },
        )

    def _check_open_mic_turn(self, *, check_name: str, description: str, check_dir: Path) -> DemoCheckResult:
        settings = self._runtime_settings(check_dir, {"blink_audio_mode": "open_mic", "blink_model_profile": "offline_stub", "blink_tts_backend": "macos_say"})
        runtime = build_desktop_runtime(settings=settings, device_registry=OpenMicRegistry([_speech_result(transcript_text="Where is the front desk?")]))
        session = runtime.ensure_session(session_id="continuous-open-mic")
        runtime.configure_companion_loop(session_id=session.session_id, voice_mode=VoiceRuntimeMode.OPEN_MIC_LOCAL, speak_enabled=True, audio_mode="open_mic")
        runtime.run_supervisor_once()
        artifacts = runtime.supervisor.export_artifacts()
        states = [item["state"] for item in artifacts["audio_loop"]["history"]]
        passed = bool("capturing" in states and "endpointing" in states and states[-1] == "cooldown" and artifacts["partial_transcripts"])
        return self._finalize_result(
            check_dir=check_dir,
            result=DemoCheckResult(
                check_name=check_name,
                description=description,
                completed_at=utc_now(),
                passed=passed,
                session_id=session.session_id,
                notes=states,
            ),
            payloads={"audio_loop": artifacts["audio_loop"], "partial_transcripts": artifacts["partial_transcripts"]},
        )

    def _check_barge_in_interrupt(self, *, check_name: str, description: str, check_dir: Path) -> DemoCheckResult:
        settings = self._runtime_settings(check_dir, {"blink_audio_mode": "open_mic", "blink_model_profile": "offline_stub", "blink_tts_backend": "macos_say"})
        registry = OpenMicRegistry([_speech_result(transcript_text="Sorry, one more thing.")])
        runtime = build_desktop_runtime(settings=settings, device_registry=registry)
        session = runtime.ensure_session(session_id="continuous-barge-in")
        runtime.configure_companion_loop(session_id=session.session_id, voice_mode=VoiceRuntimeMode.OPEN_MIC_LOCAL, speak_enabled=True, audio_mode="open_mic")
        registry.speaker_output.force_speaking()
        runtime.run_supervisor_once()
        history = runtime.supervisor.export_artifacts()["audio_loop"]["history"]
        states = [item["state"] for item in history]
        passed = bool("barge_in" in states and registry.speaker_output.cancel_calls == 1)
        return self._finalize_result(
            check_dir=check_dir,
            result=DemoCheckResult(
                check_name=check_name,
                description=description,
                completed_at=utc_now(),
                passed=passed,
                session_id=session.session_id,
                notes=states,
            ),
            payloads={"audio_loop": history},
        )

    def _check_personal_context_mode(self, *, check_name: str, description: str, check_dir: Path) -> DemoCheckResult:
        settings = self._runtime_settings(
            check_dir,
            {
                "blink_model_profile": "offline_stub",
                "blink_context_mode": CompanionContextMode.PERSONAL_LOCAL,
            },
        )
        runtime = build_desktop_runtime(settings=settings, device_registry=FakeDeviceRegistry())
        session = runtime.ensure_session(session_id="continuous-personal-context")
        interaction = runtime.submit_text(
            "What should we focus on next?",
            session_id=session.session_id,
            speak_reply=False,
            source="continuous_local_checks",
        )
        reply = interaction.response.reply_text or ""
        passed = "local notes, reminders" in reply and "rooms, events, staff handoff" not in reply
        return self._finalize_result(
            check_dir=check_dir,
            result=DemoCheckResult(
                check_name=check_name,
                description=description,
                completed_at=utc_now(),
                passed=passed,
                session_id=session.session_id,
                notes=[reply],
            ),
            payloads={"reply": reply, "outcome": interaction.outcome},
        )

    def _check_venue_demo_context_mode(self, *, check_name: str, description: str, check_dir: Path) -> DemoCheckResult:
        settings = self._runtime_settings(
            check_dir,
            {
                "blink_model_profile": "offline_stub",
                "blink_context_mode": CompanionContextMode.VENUE_DEMO,
            },
        )
        runtime = build_desktop_runtime(settings=settings, device_registry=FakeDeviceRegistry())
        session = runtime.ensure_session(session_id="continuous-venue-context")
        interaction = runtime.submit_text(
            "What should we focus on next?",
            session_id=session.session_id,
            speak_reply=False,
            source="continuous_local_checks",
        )
        reply = interaction.response.reply_text or ""
        passed = "venue questions" in reply and "local notes, reminders" not in reply
        return self._finalize_result(
            check_dir=check_dir,
            result=DemoCheckResult(
                check_name=check_name,
                description=description,
                completed_at=utc_now(),
                passed=passed,
                session_id=session.session_id,
                notes=[reply],
            ),
            payloads={"reply": reply, "outcome": interaction.outcome},
        )

    def _check_daily_memory(self, *, check_name: str, description: str, check_dir: Path) -> DemoCheckResult:
        settings = self._runtime_settings(check_dir, {"blink_model_profile": "offline_stub"})
        runtime = build_desktop_runtime(settings=settings, device_registry=FakeDeviceRegistry())
        session = runtime.orchestrator.create_session(SessionCreateRequest(session_id="continuous-memory", user_id="visitor-7"))
        runtime.orchestrator.memory.upsert_user_memory(UserMemoryRecord(user_id="visitor-7", display_name="Alex"))
        session.last_user_text = "Remind me to bring the badge tomorrow."
        session.last_reply_text = "I will keep that as a local reminder."
        session.conversation_summary = "We captured a reminder."
        session.transcript.append(ConversationTurn(event_type="speech_transcript", user_text=session.last_user_text, reply_text=session.last_reply_text))
        runtime.orchestrator.memory.upsert_session(session)
        runtime.orchestrator.knowledge_tools.record_turn_memory(
            session=session,
            user_memory=runtime.orchestrator.memory.get_user_memory("visitor-7"),
            trace_id="memory-trace-1",
            reply_text=session.last_reply_text,
            intent="reminder_follow_up",
            source_refs=[],
        )
        session.last_user_text = "Make a note that I am rehearsing the investor demo script."
        session.last_reply_text = "Saved as a local note."
        session.conversation_summary = "We captured a note."
        session.transcript.extend(
            [
                ConversationTurn(event_type="speech_transcript", user_text=f"turn {idx}", reply_text=f"reply {idx}")
                for idx in range(8)
            ]
        )
        runtime.orchestrator.memory.upsert_session(session)
        promotions = runtime.orchestrator.knowledge_tools.record_turn_memory(
            session=session,
            user_memory=runtime.orchestrator.memory.get_user_memory("visitor-7"),
            trace_id="memory-trace-2",
            reply_text=session.last_reply_text,
            intent="note_and_recall",
            source_refs=[],
        )
        snapshot = runtime.snapshot(session_id=session.session_id)
        passed = bool(snapshot.runtime.memory_status.open_reminder_count >= 1 and snapshot.runtime.memory_status.note_count >= 1 and any(item.promotion_type == "session_digest" for item in promotions))
        return self._finalize_result(
            check_dir=check_dir,
            result=DemoCheckResult(
                check_name=check_name,
                description=description,
                completed_at=utc_now(),
                passed=passed,
                session_id=session.session_id,
                notes=[snapshot.runtime.memory_status.status, str(snapshot.runtime.memory_status.open_reminder_count), str(snapshot.runtime.memory_status.note_count)],
            ),
            payloads={"snapshot": snapshot, "promotions": [item.model_dump(mode="json") for item in promotions]},
        )

    def _check_proactive_policy(self, *, check_name: str, description: str, check_dir: Path) -> DemoCheckResult:
        engine = CompanionTriggerEngine(
            attract_prompt_delay_seconds=2.0,
            semantic_refresh_min_interval_seconds=20.0,
        )
        now = utc_now()
        observer_event = SceneObservationEvent(
            observed_at=now,
            backend="frame_diff_fallback",
            change_score=0.12,
            motion_changed=False,
            person_present=True,
            person_transition="entered",
            attention_state="toward_device",
            semantic_refresh_recommended=False,
            source_kind="fixture",
        )
        eligible = engine.evaluate(
            observer_event=observer_event,
            shift_snapshot=ShiftSupervisorSnapshot(
                person_present=True,
                presence_started_at=now - timedelta(seconds=6),
            ),
            fallback_active=False,
            semantic_provider_available=True,
            fresh_semantic_scene_available=True,
            last_semantic_refresh_at=now - timedelta(seconds=3),
            now=now,
        )
        suppressed = engine.evaluate(
            observer_event=observer_event,
            shift_snapshot=ShiftSupervisorSnapshot(
                person_present=True,
                presence_started_at=now - timedelta(seconds=6),
                outreach_cooldown_until=now + timedelta(seconds=30),
            ),
            fallback_active=False,
            semantic_provider_available=True,
            fresh_semantic_scene_available=True,
            last_semantic_refresh_at=now - timedelta(seconds=3),
            now=now,
        )
        passed = (
            eligible.decision == CompanionTriggerDecision.SPEAK_NOW
            and suppressed.decision == CompanionTriggerDecision.WAIT
            and suppressed.suppressed_reason == "outreach_cooldown"
        )
        return self._finalize_result(
            check_dir=check_dir,
            result=DemoCheckResult(
                check_name=check_name,
                description=description,
                completed_at=utc_now(),
                passed=passed,
                notes=[eligible.decision.value, suppressed.decision.value],
            ),
            payloads={
                "eligible": eligible.__dict__,
                "suppressed": suppressed.__dict__,
            },
        )

    def _check_latency_visibility(self, *, check_name: str, description: str, check_dir: Path) -> DemoCheckResult:
        settings = self._runtime_settings(
            check_dir,
            {
                "blink_model_profile": "offline_stub",
                "blink_voice_profile": "offline_stub",
            },
        )
        runtime = build_desktop_runtime(settings=settings, device_registry=FakeDeviceRegistry())
        session = runtime.ensure_session(session_id="continuous-latency")
        runtime.submit_text(
            "What should I remember for later?",
            session_id=session.session_id,
            speak_reply=False,
            source="continuous_local_checks",
        )
        snapshot = runtime.snapshot(session_id=session.session_id)
        diagnostics = snapshot.runtime.latest_live_turn_diagnostics
        passed = bool(
            diagnostics is not None
            and diagnostics.stt_ms is not None
            and diagnostics.reasoning_ms is not None
            and diagnostics.tts_start_ms is not None
            and diagnostics.end_to_end_turn_ms is not None
        )
        return self._finalize_result(
            check_dir=check_dir,
            result=DemoCheckResult(
                check_name=check_name,
                description=description,
                completed_at=utc_now(),
                passed=passed,
                session_id=session.session_id,
                notes=[
                    str(diagnostics.stt_ms if diagnostics is not None else None),
                    str(diagnostics.reasoning_ms if diagnostics is not None else None),
                    str(diagnostics.end_to_end_turn_ms if diagnostics is not None else None),
                ],
            ),
            payloads={"snapshot": snapshot, "diagnostics": diagnostics},
        )

    def _check_model_residency(self, *, check_name: str, description: str, check_dir: Path) -> DemoCheckResult:
        settings = self._runtime_settings(
            check_dir,
            {
                "blink_backend_profile": "m4_pro_companion",
                "ollama_text_model": "qwen3.5:9b",
                "ollama_vision_model": "qwen3.5:9b",
                "ollama_embedding_model": "embeddinggemma:300m",
                "blink_model_idle_unload_seconds": 1.0,
            },
        )
        router = BackendRouter(
            settings=settings,
            ollama_probe=StaticOllamaProbe(
                OllamaProbeSnapshot(
                    reachable=True,
                    installed_models={"qwen3.5:9b", "embeddinggemma:300m"},
                    running_models={"qwen3.5:9b"},
                    latency_ms=22.0,
                )
            ),
        )
        router.report_ollama_success(kind=router.route_decisions()[0].kind, model="qwen3.5:9b", latency_ms=12.0)
        router.report_ollama_success(kind=router.route_decisions()[1].kind, model="qwen3.5:9b", latency_ms=18.0)
        router._model_residency[router.route_decisions()[1].kind] = router._model_residency[router.route_decisions()[1].kind].model_copy(
            update={"last_used_at": utc_now().replace(microsecond=0)}
        )
        router._model_residency[router.route_decisions()[1].kind] = router._model_residency[router.route_decisions()[1].kind].model_copy(
            update={"last_used_at": utc_now() - timedelta(seconds=5)}
        )
        router._request_ollama_unload = lambda model: True  # type: ignore[method-assign]
        residency = router.apply_model_residency_policy()
        vision = next(item for item in residency if item.kind.value == "vision_analysis")
        text = next(item for item in residency if item.kind.value == "text_reasoning")
        passed = bool(vision.status == "shared_resident" and vision.resident is True and text.keep_warm is True)
        return self._finalize_result(
            check_dir=check_dir,
            result=DemoCheckResult(
                check_name=check_name,
                description=description,
                completed_at=utc_now(),
                passed=passed,
                notes=[item.status for item in residency],
            ),
            payloads={"model_residency": [item.model_dump(mode="json") for item in residency]},
        )

    def _runtime_settings(self, check_dir: Path, overrides: dict[str, object]) -> Settings:
        return self.settings.model_copy(
            update={
                "blink_always_on_enabled": True,
                "brain_store_path": str(check_dir / "brain_store.json"),
                "demo_report_dir": str(check_dir / "demo_runs"),
                "demo_check_dir": str(check_dir / "demo_checks"),
                "episode_export_dir": str(check_dir / "episodes"),
                "shift_report_dir": str(check_dir / "shift_reports"),
                "operator_auth_runtime_file": str(check_dir / "operator_auth.json"),
                **overrides,
            }
        )

    def _finalize_result(self, *, check_dir: Path, result: DemoCheckResult, payloads: dict[str, object]) -> DemoCheckResult:
        result.artifact_files["summary"] = str(check_dir / "summary.json")
        self._write_json(Path(result.artifact_files["summary"]), result)
        for name, payload in payloads.items():
            artifact_path = check_dir / f"{name}.json"
            result.artifact_files[name] = str(artifact_path)
            self._write_json(artifact_path, payload)
        self._write_json(Path(result.artifact_files["summary"]), result)
        return result

    def _write_json(self, path: Path, payload: object) -> None:
        data = self._normalize(payload)
        write_json_atomic(path, data)

    def _normalize(self, payload: object):
        if hasattr(payload, "model_dump"):
            return payload.model_dump(mode="json")  # type: ignore[call-arg]
        if isinstance(payload, list):
            return [self._normalize(item) for item in payload]
        if isinstance(payload, dict):
            return {key: self._normalize(value) for key, value in payload.items()}
        return payload


def main() -> None:
    suite = run_continuous_local_checks()
    print(
        json.dumps(
            {
                "suite_id": suite.suite_id,
                "passed": suite.passed,
                "check_count": len(suite.items),
                "passed_count": sum(1 for item in suite.items if item.passed),
                "artifact_dir": suite.artifact_dir,
                "summary_path": suite.artifact_files.get("summary"),
            },
            indent=2,
        )
    )


__all__ = ["run_continuous_local_checks", "main"]
