from __future__ import annotations

import logging
from threading import Event, RLock, Thread
from time import monotonic, perf_counter
from typing import Any
from datetime import timedelta

from embodied_stack.backends.profiles import backend_candidates_for
from embodied_stack.brain.initiative import (
    CompanionInitiativeEngine,
    InitiativeContext,
    browser_context_from_status,
    terminal_activity_for_session,
)
from embodied_stack.brain.operator_console import OperatorConsoleService
from embodied_stack.brain.presence import FastPresenceSummary, PresenceRuntime
from embodied_stack.config import Settings
from embodied_stack.desktop.always_on import SceneObservationEvent, SceneObserverEngine
from embodied_stack.multimodal.events import build_scene_request
from embodied_stack.observability import log_event
from embodied_stack.shared.models import (
    CompanionAudioMode,
    InitiativeDecision,
    InitiativeStatus,
    CompanionPresenceState,
    CompanionPresenceStatus,
    CompanionSupervisorStatus,
    CompanionTriggerDecision,
    CompanionVoiceLoopState,
    CompanionVoiceLoopStatus,
    EnvironmentState,
    MemoryPromotionRecord,
    OperatorVoiceTurnRequest,
    PerceptionProviderMode,
    PerceptionSnapshotRecord,
    PerceptionSnapshotSubmitRequest,
    PerceptionTier,
    RuntimeBackendKind,
    ShiftOperatingState,
    SceneObserverStatus,
    SceneCacheRecord,
    SceneObserverEventListResponse,
    SceneObserverEventRecord,
    SpeechOutputStatus,
    ReminderStatus,
    ShiftAutonomyTickRequest,
    TriggerEngineStatus,
    VoiceCancelResult,
    VoiceRuntimeMode,
    WorkflowStartRequestRecord,
    utc_now,
)

logger = logging.getLogger(__name__)


class ShiftAutonomyRunner:
    def __init__(self, *, settings: Settings, operator_console: OperatorConsoleService) -> None:
        self.settings = settings
        self.operator_console = operator_console
        self._stop_event = Event()
        self._thread: Thread | None = None
        self._lock = RLock()
        self._observer = SceneObserverEngine(change_threshold=max(0.0, float(settings.blink_scene_change_threshold)))
        self._initiative = CompanionInitiativeEngine(
            attract_prompt_delay_seconds=float(settings.shift_attract_prompt_delay_seconds),
            semantic_refresh_min_interval_seconds=float(settings.blink_semantic_refresh_min_interval_seconds),
            cooldown_seconds=float(settings.shift_outreach_cooldown_seconds),
        )
        self._configured_voice_mode: VoiceRuntimeMode | None = None
        self._audio_mode = self._resolve_audio_mode(settings.blink_audio_mode)
        self._speak_enabled = True
        self._active_session_id: str | None = None
        self._last_shift_tick_at = 0.0
        self._last_observer_poll_at = 0.0
        self._last_semantic_refresh_at = None
        self._last_promoted_trace_id: str | None = None
        self._voice_history: list[dict[str, Any]] = []
        self._presence_history: list[dict[str, Any]] = []
        self._scene_history: list[dict[str, Any]] = []
        self._scene_event_buffer: list[SceneObserverEventRecord] = []
        self._initiative_history: list[dict[str, Any]] = []
        self._trigger_history: list[dict[str, Any]] = []
        self._partial_transcripts: list[dict[str, Any]] = []
        self._runtime_events: list[dict[str, Any]] = []
        self._memory_promotions: list[MemoryPromotionRecord] = []
        self._scene_cache: SceneCacheRecord | None = None
        self._last_character_projection_signature: str | None = None
        self._last_character_projection_at: float = 0.0
        self._supervisor = CompanionSupervisorStatus(
            enabled=settings.blink_always_on_enabled,
            state="idle" if settings.blink_always_on_enabled else "disabled",
            observer_interval_seconds=float(settings.blink_observer_interval_seconds),
        )
        self._presence_runtime = PresenceRuntime(
            settings=settings,
            transition_callback=self._record_presence_transition,
        )
        self._voice_loop = CompanionVoiceLoopStatus()
        self._scene_status = SceneObserverStatus(
            enabled=settings.blink_always_on_enabled,
            state="idle" if settings.blink_always_on_enabled else "disabled",
            backend=self._observer.backend_name,
            supports_mediapipe=self._observer.supports_mediapipe,
        )
        self._initiative_status = InitiativeStatus(enabled=settings.blink_always_on_enabled)
        self._trigger_status = TriggerEngineStatus(enabled=settings.blink_always_on_enabled)

    def start(self) -> None:
        if self.settings.blink_always_on_enabled:
            self.operator_console.backend_router.prewarm_local_models()
        elif not self.settings.shift_background_tick_enabled:
            return
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = Thread(target=self._run, name="blink-shift-autonomy", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=1.5)
            self._thread = None

    def configure_loop(
        self,
        *,
        session_id: str | None = None,
        voice_mode: VoiceRuntimeMode | None = None,
        speak_enabled: bool = True,
        audio_mode: CompanionAudioMode | str | None = None,
    ) -> None:
        with self._lock:
            if session_id:
                self._active_session_id = session_id
                self._supervisor.active_session_id = session_id
            if voice_mode is not None:
                self._configured_voice_mode = voice_mode
            if audio_mode is not None:
                self._audio_mode = self._resolve_audio_mode(audio_mode)
            self._speak_enabled = speak_enabled
            open_mic_active = (
                self._audio_mode == CompanionAudioMode.OPEN_MIC
                or self._configured_voice_mode == VoiceRuntimeMode.OPEN_MIC_LOCAL
            )
            if open_mic_active:
                self._voice_loop.state = CompanionVoiceLoopState.VAD_WAITING
                self._voice_loop.audio_backend = self._selected_open_mic_backend()
            else:
                self._voice_loop.state = CompanionVoiceLoopState.IDLE
                self._voice_loop.audio_backend = None
            self._voice_loop.last_transition_at = utc_now()

    def set_active_session(self, session_id: str | None) -> None:
        with self._lock:
            self._active_session_id = session_id
            self._supervisor.active_session_id = session_id

    def supervisor_status(self) -> CompanionSupervisorStatus:
        with self._lock:
            return self._supervisor.model_copy(deep=True)

    def voice_loop_status(self) -> CompanionVoiceLoopStatus:
        with self._lock:
            return self._voice_loop.model_copy(deep=True)

    def presence_runtime_status(self) -> CompanionPresenceStatus:
        return self._presence_runtime.status()

    def scene_observer_status(self) -> SceneObserverStatus:
        with self._lock:
            return self._scene_status.model_copy(deep=True)

    def initiative_engine_status(self) -> InitiativeStatus:
        with self._lock:
            return self._initiative_status.model_copy(deep=True)

    def trigger_engine_status(self) -> TriggerEngineStatus:
        with self._lock:
            return self._trigger_status.model_copy(deep=True)

    def scene_observer_events(self) -> SceneObserverEventListResponse:
        with self._lock:
            return SceneObserverEventListResponse(items=[item.model_copy(deep=True) for item in self._scene_event_buffer[-25:]])

    def audio_mode(self) -> CompanionAudioMode:
        with self._lock:
            return self._audio_mode

    def latest_scene_cache(self) -> SceneCacheRecord | None:
        with self._lock:
            return self._scene_cache.model_copy(deep=True) if self._scene_cache is not None else None

    def recent_memory_promotions(self) -> list[MemoryPromotionRecord]:
        with self._lock:
            return [item.model_copy(deep=True) for item in self._memory_promotions[-20:]]

    def set_audio_mode(self, mode: CompanionAudioMode | str) -> CompanionAudioMode:
        resolved = self._resolve_audio_mode(mode)
        with self._lock:
            self._audio_mode = resolved
            self._voice_loop.state = CompanionVoiceLoopState.VAD_WAITING if resolved == CompanionAudioMode.OPEN_MIC else CompanionVoiceLoopState.IDLE
            self._voice_loop.last_transition_at = utc_now()
            self._voice_loop.audio_backend = self._selected_open_mic_backend() if resolved == CompanionAudioMode.OPEN_MIC else None
        self._queue_runtime_event(
            event_type="audio_mode_changed",
            session_id=self._active_session_id,
            message=f"audio_mode={resolved.value}",
        )
        return resolved

    def silence_initiative(self, *, minutes: float = 15.0) -> InitiativeStatus:
        status = self._initiative.silence(minutes=minutes)
        with self._lock:
            self._initiative_status = status
        self._queue_runtime_event(
            event_type="initiative_state_changed",
            session_id=self._active_session_id,
            message=f"initiative_silenced_for_{round(max(0.0, minutes), 2)}m",
            state=status.last_decision.value,
        )
        return status

    def clear_initiative_silence(self) -> InitiativeStatus:
        status = self._initiative.clear_silence()
        with self._lock:
            self._initiative_status = status
        self._queue_runtime_event(
            event_type="initiative_state_changed",
            session_id=self._active_session_id,
            message="initiative_silence_cleared",
            state=status.last_decision.value,
        )
        return status

    def drain_runtime_events(self) -> list[dict[str, Any]]:
        with self._lock:
            events = list(self._runtime_events)
            self._runtime_events.clear()
            return events

    def export_artifacts(self) -> dict[str, object]:
        active_session_id = self._active_session_id
        voice_loop = {
            "status": self.voice_loop_status(),
            "history": list(self._voice_history[-100:]),
        }
        return {
            "presence_runtime": {
                "status": self.presence_runtime_status(),
                "history": list(self._presence_history[-100:]),
            },
            "initiative_engine": {
                "status": self.initiative_engine_status(),
                "history": list(self._initiative_history[-100:]),
            },
            "scene_observer": {
                "status": self.scene_observer_status(),
                "history": list(self._scene_history[-100:]),
                "events": [item.model_dump(mode="json") for item in self._scene_event_buffer[-100:]],
            },
            "trigger_history": {
                "status": self.trigger_engine_status(),
                "history": list(self._trigger_history[-100:]),
            },
            "voice_loop": voice_loop,
            "audio_loop": voice_loop,
            "partial_transcripts": list(self._partial_transcripts[-100:]),
            "scene_cache": self.latest_scene_cache(),
            "memory_promotions": [item.model_dump(mode="json") for item in self._memory_promotions[-100:]],
            "agent_runtime": self._agent_runtime_export(active_session_id),
            "model_residency": self.operator_console.backend_router.model_residency(),
            "ollama_runtime": self.operator_console.backend_router.runtime_statuses(),
        }

    def prepare_live_listen(self, *, session_id: str, voice_mode: VoiceRuntimeMode) -> None:
        self.configure_loop(session_id=session_id, voice_mode=voice_mode, speak_enabled=self._speak_enabled)
        self._transition_voice_state(
            CompanionVoiceLoopState.ARMED,
            session_id=session_id,
            message="push_to_talk_armed",
            armed_until=utc_now() + timedelta(seconds=float(self.settings.blink_voice_arm_timeout_seconds)),
        )
        self._transition_voice_state(
            CompanionVoiceLoopState.CAPTURING,
            session_id=session_id,
            message="capturing_one_utterance",
        )

    def prepare_typed_turn(self, *, session_id: str, voice_mode: VoiceRuntimeMode | None) -> None:
        self.configure_loop(session_id=session_id, voice_mode=voice_mode or self._configured_voice_mode, speak_enabled=self._speak_enabled)
        self._transition_voice_state(
            CompanionVoiceLoopState.DEGRADED_TYPED,
            session_id=session_id,
            message="typed_fallback_active",
            degraded_reason="typed_input",
        )

    def finalize_turn(
        self,
        *,
        session_id: str,
        transcript_text: str | None,
        interaction_latency_ms: float | None,
        spoken: bool,
    ) -> None:
        transcript_latency_ms = round(interaction_latency_ms or 0.0, 2) if transcript_text else None
        if transcript_text:
            self._transition_voice_state(
                CompanionVoiceLoopState.ENDPOINTING,
                session_id=session_id,
                message="utterance_endpointed",
            )
            self._transition_voice_state(
                CompanionVoiceLoopState.TRANSCRIBING,
                session_id=session_id,
                message="transcript_ready",
                transcript_latency_ms=transcript_latency_ms,
                partial_transcript_preview=transcript_text[:160],
            )
            self._transition_voice_state(
                CompanionVoiceLoopState.THINKING,
                session_id=session_id,
                message="reply_ready",
            )
        if spoken:
            self._transition_voice_state(
                CompanionVoiceLoopState.SPEAKING,
                session_id=session_id,
                message="reply_spoken",
                first_audio_latency_ms=round(interaction_latency_ms or 0.0, 2),
            )
        self._transition_voice_state(
            CompanionVoiceLoopState.COOLDOWN,
            session_id=session_id,
            message="turn_complete",
        )

    def interrupt(
        self,
        *,
        session_id: str | None = None,
        voice_mode: VoiceRuntimeMode | None = None,
        barge_in: bool = False,
    ) -> VoiceCancelResult:
        start = perf_counter()
        result = self.operator_console.cancel_voice(
            session_id=session_id,
            voice_mode=voice_mode or self._configured_voice_mode,
        )
        self._transition_voice_state(
            CompanionVoiceLoopState.INTERRUPTED,
            session_id=session_id or result.session_id,
            message=result.state.message or "interrupted",
            interruption_latency_ms=round((perf_counter() - start) * 1000.0, 2),
            interrupted=True,
        )
        self._presence_runtime.interrupt(
            session_id=session_id or result.session_id or self._resolve_session_id(),
            reason=result.state.message or "interrupted",
            barge_in=barge_in,
        )
        self._queue_runtime_event(
            event_type="voice_interrupted",
            session_id=session_id or result.session_id,
            message=result.state.message or "interrupted",
        )
        return result

    def begin_presence_turn(
        self,
        *,
        session_id: str,
        input_text: str | None,
        source: str | None,
        listening: bool,
    ) -> None:
        self._presence_runtime.begin_turn(
            session_id=session_id,
            input_text=input_text,
            source=source,
            listening=listening,
        )

    def note_presence_thinking_fast(self, *, session_id: str, input_text: str | None = None, message: str = "thinking_fast") -> None:
        self._presence_runtime.note_thinking_fast(
            session_id=session_id,
            input_text=input_text,
            message=message,
        )

    def prepare_presence_reply(self, *, session_id: str, reply_text: str | None, audible: bool) -> None:
        self._presence_runtime.begin_reply(
            session_id=session_id,
            reply_text=reply_text,
            audible=audible,
        )

    def complete_presence_turn(
        self,
        *,
        session_id: str,
        reply_text: str | None,
        spoken: bool,
        completed: bool = False,
    ) -> FastPresenceSummary:
        return self._presence_runtime.finish_turn(
            session_id=session_id,
            reply_text=reply_text,
            spoken=spoken,
            completed=completed,
        )

    def degrade_presence_turn(self, *, session_id: str, reason: str, message: str | None = None) -> FastPresenceSummary:
        return self._presence_runtime.degrade(
            session_id=session_id,
            reason=reason,
            message=message,
        )

    def run_once(self) -> None:
        if self.settings.blink_always_on_enabled:
            self._run_supervisor_tick()
        else:
            self._run_periodic_shift_tick()

    def _run(self) -> None:
        interval = 0.5 if self.settings.blink_always_on_enabled else max(1.0, float(self.settings.shift_autonomy_tick_interval_seconds))
        while not self._stop_event.wait(interval):
            try:
                if self.settings.blink_always_on_enabled:
                    self._run_supervisor_tick()
                else:
                    self._run_periodic_shift_tick()
            except Exception:
                log_event(
                    logger,
                    logging.ERROR,
                    "shift_runner_tick_failed",
                    session_id=self._active_session_id,
                    always_on_enabled=self.settings.blink_always_on_enabled,
                )
                logger.exception("Background shift autonomy tick failed.")

    def _run_periodic_shift_tick(self) -> None:
        now = monotonic()
        if now - self._last_shift_tick_at < max(1.0, float(self.settings.shift_autonomy_tick_interval_seconds)):
            return
        self._last_shift_tick_at = now
        interaction = self.operator_console.run_shift_tick(ShiftAutonomyTickRequest())
        try:
            shift_snapshot = self.operator_console.orchestrator.get_shift_supervisor()
            self.operator_console.evaluate_action_plane_workflow_triggers(
                session_id=self._active_session_id,
                shift_snapshot=shift_snapshot,
                now=utc_now(),
            )
        except RuntimeError:
            log_event(logger, logging.INFO, "workflow_trigger_evaluation_skipped", session_id=self._active_session_id)
        with self._lock:
            self._supervisor.last_tick_at = utc_now()
            self._supervisor.last_outcome = interaction.outcome

    def _run_supervisor_tick(self) -> None:
        session_id = self._resolve_session_id()
        now = utc_now()
        with self._lock:
            self._supervisor.enabled = True
            self._supervisor.state = "running"
            self._supervisor.active_session_id = session_id
            self._supervisor.last_tick_at = now

        observer_event = None
        if monotonic() - self._last_observer_poll_at >= max(0.5, float(self.settings.blink_observer_interval_seconds)):
            self._last_observer_poll_at = monotonic()
            observer_event = self._poll_scene_observer(session_id=session_id)
            if observer_event is not None and observer_event.motion_changed:
                self._invalidate_scene_cache("observer_motion_changed")

        if self._run_open_mic_tick(session_id=session_id):
            self._promote_memory_if_needed(session_id=session_id)
            self.operator_console.backend_router.apply_model_residency_policy()
            return

        initiative_context = self._build_initiative_context(
            session_id=session_id,
            now=now,
            observer_event=observer_event,
        )
        if initiative_context is None:
            self._promote_memory_if_needed(session_id=session_id)
            self.operator_console.backend_router.apply_model_residency_policy()
            return

        evaluation = self._initiative.evaluate(initiative_context)
        executed = False
        coarse_trigger_decision, proactive_eligible, trigger_suppression_reason = self._coarse_trigger_from_initiative(
            evaluation
        )
        log_event(
            logger,
            logging.INFO,
            "initiative_evaluated",
            session_id=session_id,
            decision=evaluation.decision.value,
            candidate_kind=evaluation.candidate_kind,
            candidate_count=evaluation.candidate_count,
            reason=evaluation.reason,
            suppressed_reason=evaluation.suppression_reason,
            score_total=evaluation.scorecard.total,
            trigger_decision=coarse_trigger_decision.value,
        )

        if evaluation.should_refresh_scene:
            self._refresh_semantic_scene(
                session_id=session_id,
                reason=evaluation.refresh_reason or evaluation.reason,
            )
        elif evaluation.decision in {InitiativeDecision.SUGGEST, InitiativeDecision.ASK}:
            executed = self._run_triggered_shift_tick(
                session_id=session_id,
                reason=evaluation.reason,
                initiative_payload=self._initiative_payload(evaluation),
            )
        elif evaluation.decision == InitiativeDecision.ACT:
            executed = self._run_initiative_action(session_id=session_id, evaluation=evaluation)

        initiative_status = self._initiative.commit(evaluation, acted=executed, now=now)
        self._record_initiative(
            evaluation,
            observed_at=now,
            executed=executed,
            status=initiative_status,
        )
        self._record_trigger_from_initiative(
            evaluation,
            observed_at=now,
            cooldown_until=initiative_status.cooldown_until,
            coarse_decision=coarse_trigger_decision,
            proactive_eligible=proactive_eligible,
            suppression_reason=trigger_suppression_reason,
            executed=executed,
        )
        self._sync_character_projection(session_id=session_id, reason="initiative_tick")

        if coarse_trigger_decision == CompanionTriggerDecision.SAFE_IDLE:
            with self._lock:
                self._supervisor.state = "safe_idle"
                self._supervisor.proactive_suppressed = True
                self._supervisor.proactive_suppression_reason = trigger_suppression_reason or evaluation.reason

        self._promote_memory_if_needed(session_id=session_id)
        self.operator_console.backend_router.apply_model_residency_policy()
        presence_state = self._presence_runtime.status()
        if presence_state.session_id == session_id and presence_state.state == CompanionPresenceState.SPEAKING:
            voice_mode = self._configured_voice_mode or self.operator_console.default_live_voice_mode()
            voice_state = self.operator_console.voice_manager.get_state(voice_mode, session_id)
            if voice_state.status not in {SpeechOutputStatus.SPEAKING, SpeechOutputStatus.THINKING, SpeechOutputStatus.TRANSCRIBING}:
                self._presence_runtime.reset_idle(session_id=session_id)
        with self._lock:
            if (
                self._voice_loop.state == CompanionVoiceLoopState.COOLDOWN
                and (now - self._voice_loop.last_transition_at).total_seconds() >= 2.0
            ):
                self._voice_loop.state = (
                    CompanionVoiceLoopState.VAD_WAITING
                    if self._audio_mode == CompanionAudioMode.OPEN_MIC
                    else CompanionVoiceLoopState.IDLE
                )
                self._voice_loop.last_transition_at = now
            elif self._audio_mode == CompanionAudioMode.OPEN_MIC and self._voice_loop.state == CompanionVoiceLoopState.IDLE:
                self._voice_loop.state = CompanionVoiceLoopState.VAD_WAITING
                self._voice_loop.last_transition_at = now

    def _poll_scene_observer(self, *, session_id: str) -> SceneObservationEvent | None:
        camera = self.operator_console.device_registry.camera_capture
        if camera.source.mode != "webcam":
            reason = camera.source.note or f"camera_source:{camera.source.mode}"
            previous_reason = None
            with self._lock:
                previous_reason = self._scene_status.degraded_reason
                self._scene_status.enabled = False
                self._scene_status.state = "degraded"
                self._scene_status.degraded_reason = reason
            if previous_reason != reason:
                log_event(
                    logger,
                    logging.WARNING,
                    "scene_observer_degraded",
                    session_id=session_id,
                    reason=reason,
                )
            return None
        try:
            capture = self.operator_console.device_registry.capture_camera_snapshot(background=True)
        except Exception as exc:
            previous_reason = None
            with self._lock:
                previous_reason = self._scene_status.degraded_reason
                self._scene_status.state = "degraded"
                self._scene_status.degraded_reason = str(exc)
            if previous_reason != str(exc):
                self._queue_runtime_event(
                    event_type="camera_status",
                    session_id=session_id,
                    message=str(exc),
                )
                log_event(
                    logger,
                    logging.WARNING,
                    "scene_observer_capture_failed",
                    session_id=session_id,
                    reason=str(exc),
                )
            return None
        previous_state = None
        previous_reason = None
        with self._lock:
            previous_state = self._scene_status.state
            previous_reason = self._scene_status.degraded_reason
        if previous_state == "degraded" and previous_reason:
            self._queue_runtime_event(
                event_type="camera_status",
                session_id=session_id,
                message="camera_capture_recovered",
            )
            log_event(
                logger,
                logging.INFO,
                "scene_observer_recovered",
                session_id=session_id,
                reason=previous_reason,
            )

        event = self._observer.observe(
            image_data_url=capture.image_data_url,
            source_kind=capture.source_frame.source_kind,
            observed_at=capture.source_frame.captured_at,
        )
        with self._lock:
            self._scene_status.enabled = True
            self._scene_status.state = "observing"
            self._scene_status.backend = event.backend
            self._scene_status.last_observed_at = event.observed_at
            self._scene_status.last_change_score = event.change_score
            self._scene_status.last_person_state = (
                "present" if event.person_present is True else "absent" if event.person_present is False else "unknown"
            )
            self._scene_status.last_people_count_estimate = event.people_count_estimate
            self._scene_status.last_attention_state = event.attention_state or "unknown"
            self._scene_status.last_attention_toward_device_score = event.attention_toward_device_score
            self._scene_status.last_environment_state = event.environment_state
            self._scene_status.last_refresh_reason = event.refresh_reason
            self._scene_status.buffer_size = len(self._scene_event_buffer) + 1
            self._scene_status.degraded_reason = None
        self._record_scene_observer_event(event)
        if event.person_present is not None or event.motion_changed:
            note = self._watcher_note_for_event(event)
            if event.attention_state == "toward_device":
                engagement = "engaged"
            elif event.attention_state == "away":
                engagement = "disengaging"
            elif event.person_present is False:
                engagement = "lost"
            else:
                engagement = None
            self.operator_console.submit_perception_snapshot(
                build_scene_request(
                    session_id=session_id,
                    source="scene_observer",
                    person_present=event.person_present,
                    people_count=event.people_count_estimate,
                    engagement=engagement,
                    scene_note=note,
                    provider_mode=PerceptionProviderMode.MANUAL_ANNOTATIONS,
                    trigger_reason=event.refresh_reason,
                    metadata={
                        "observer_backend": event.backend,
                        "presence_state": event.presence_state.value,
                        "motion_state": event.motion_state.value,
                        "new_entrant": event.new_entrant,
                        "attention_state": event.attention_state,
                        "attention_target_hint": event.attention_target_hint,
                        "attention_toward_device_score": event.attention_toward_device_score,
                        "engagement_shift_hint": event.engagement_shift_hint.value,
                        "signal_confidence": event.signal_confidence,
                        "environment_state": event.environment_state.value,
                        "scene_change_score": event.change_score,
                        "observer_capability_limits": list(event.capability_limits),
                        "device_awareness_constraints": list(event.capability_limits),
                        "watcher_refresh_recommended": event.semantic_refresh_recommended,
                    },
                    publish_events=True,
                )
            )
        return event

    def _run_open_mic_tick(self, *, session_id: str) -> bool:
        with self._lock:
            audio_mode = self._audio_mode
            configured_voice_mode = self._configured_voice_mode
        voice_mode = configured_voice_mode or self.operator_console.default_live_voice_mode()
        if audio_mode != CompanionAudioMode.OPEN_MIC and voice_mode != VoiceRuntimeMode.OPEN_MIC_LOCAL:
            return False
        voice_mode = VoiceRuntimeMode.OPEN_MIC_LOCAL
        if not hasattr(self.operator_console.device_registry, "poll_open_mic"):
            self._transition_voice_state(
                CompanionVoiceLoopState.DEGRADED_TYPED,
                session_id=session_id,
                message="open_mic_unavailable",
                degraded_reason="poll_open_mic_missing",
            )
            return False

        state = self.operator_console.voice_manager.get_state(voice_mode, session_id)
        if state.status in {SpeechOutputStatus.TRANSCRIBING, SpeechOutputStatus.THINKING}:
            return False

        result = self.operator_console.device_registry.poll_open_mic(
            session_id=session_id,
            backend_candidates=self._selected_open_mic_candidates(),
            vad_silence_ms=int(self.settings.blink_vad_silence_ms),
            vad_min_speech_ms=int(self.settings.blink_vad_min_speech_ms),
        )
        if not result.speech_detected:
            if state.status != SpeechOutputStatus.SPEAKING:
                self._transition_voice_state(
                    CompanionVoiceLoopState.VAD_WAITING,
                    session_id=session_id,
                    message="waiting_for_voice_activity",
                    audio_backend=result.transcription_backend or self._selected_open_mic_backend(),
                )
            return False

        if result.partial_transcript:
            self._partial_transcripts.append(
                {
                    "timestamp": result.captured_at.isoformat(),
                    "session_id": session_id,
                    "preview": result.partial_transcript,
                    "speech_ms": result.speech_ms,
                    "backend": result.transcription_backend,
                }
            )

        if state.status == SpeechOutputStatus.SPEAKING:
            self.interrupt(session_id=session_id, voice_mode=voice_mode, barge_in=True)
            self._transition_voice_state(
                CompanionVoiceLoopState.BARGE_IN,
                session_id=session_id,
                message="user_barge_in_detected",
                partial_transcript_preview=result.partial_transcript,
                audio_backend=result.transcription_backend,
            )

        if not result.transcript_text:
            self._transition_voice_state(
                CompanionVoiceLoopState.DEGRADED_TYPED,
                session_id=session_id,
                message="open_mic_requires_typed_fallback",
                degraded_reason=result.degraded_reason or "typed_input_required",
                partial_transcript_preview=result.partial_transcript,
                audio_backend=result.transcription_backend,
            )
            self._queue_runtime_event(
                event_type="open_mic_degraded",
                session_id=session_id,
                message=result.degraded_reason or "typed_input_required",
            )
            return False

        self._transition_voice_state(
            CompanionVoiceLoopState.CAPTURING,
            session_id=session_id,
            message="speech_detected",
            partial_transcript_preview=result.partial_transcript,
            audio_backend=result.transcription_backend,
        )
        self._transition_voice_state(
            CompanionVoiceLoopState.ENDPOINTING,
            session_id=session_id,
            message="voice_endpoint_detected",
            partial_transcript_preview=result.partial_transcript,
            audio_backend=result.transcription_backend,
        )
        interaction = self.operator_console.submit_text_turn(
            OperatorVoiceTurnRequest(
                session_id=session_id,
                user_id=(self.operator_console.orchestrator.get_session(session_id).user_id if self.operator_console.orchestrator.get_session(session_id) is not None else None),
                input_text=result.transcript_text,
                voice_mode=voice_mode,
                speak_reply=self._speak_enabled,
                source="open_mic_supervisor",
                input_metadata={
                    "capture_mode": "open_mic_supervisor",
                    "transcription_backend": result.transcription_backend or self._selected_open_mic_backend(),
                    "confidence": 0.8,
                    "speech_ms": result.speech_ms,
                    "rms_level": result.rms_level,
                    "stt_latency_ms": getattr(result, "transcription_latency_ms", None),
                    "partial_transcript_preview": result.partial_transcript,
                },
            )
        )
        self.finalize_turn(
            session_id=session_id,
            transcript_text=result.transcript_text,
            interaction_latency_ms=interaction.latency_ms,
            spoken=bool(
                interaction.voice_output
                and interaction.voice_output.status.value in {"speaking", "completed", "simulated"}
            ),
        )
        self._queue_runtime_event(
            event_type="open_mic_turn",
            session_id=session_id,
            message=result.transcript_text,
            reply_text=interaction.response.reply_text,
            trace_id=interaction.response.trace_id,
        )
        return True

    def _refresh_semantic_scene(self, *, session_id: str, reason: str) -> None:
        provider_mode = self._semantic_provider_mode()
        if provider_mode is None:
            return
        camera = self.operator_console.device_registry.camera_capture
        if camera.source.mode != "webcam":
            return
        try:
            capture = self.operator_console.device_registry.capture_camera_snapshot(background=True)
        except Exception as exc:
            log_event(
                logger,
                logging.WARNING,
                "semantic_scene_refresh_skipped",
                session_id=session_id,
                reason=reason,
                error=str(exc),
            )
            return
        result = self.operator_console.submit_perception_snapshot(
            PerceptionSnapshotSubmitRequest(
                session_id=session_id,
                provider_mode=provider_mode,
                tier=PerceptionTier.SEMANTIC,
                trigger_reason=reason,
                source="always_on_refresh",
                source_frame=capture.source_frame,
                image_data_url=capture.image_data_url,
                publish_events=True,
            )
        )
        snapshot = getattr(result, "snapshot", None)
        refresh_at = utc_now()
        self._last_semantic_refresh_at = refresh_at
        with self._lock:
            self._scene_status.last_semantic_refresh_at = refresh_at
            self._scene_status.last_refresh_reason = reason
            self._scene_status.semantic_refresh_count += 1
            self._supervisor.last_scene_refresh_reason = reason
        if isinstance(snapshot, PerceptionSnapshotRecord):
            self._note_scene_cache(snapshot, invalidated_because=None)
        self._queue_runtime_event(
            event_type="scene_refreshed",
            session_id=session_id,
            message=reason,
        )
        log_event(
            logger,
            logging.INFO,
            "semantic_scene_refreshed",
            session_id=session_id,
            reason=reason,
            provider_mode=provider_mode.value,
            snapshot_id=snapshot.snapshot_id if isinstance(snapshot, PerceptionSnapshotRecord) else None,
        )

    def _run_triggered_shift_tick(
        self,
        *,
        session_id: str,
        reason: str,
        initiative_payload: dict[str, object] | None = None,
    ) -> bool:
        interaction = self.operator_console.run_shift_tick(
            ShiftAutonomyTickRequest(
                session_id=session_id,
                source="always_on_supervisor",
                payload=initiative_payload or {},
            )
        )
        with self._lock:
            self._supervisor.last_outcome = interaction.outcome
            self._supervisor.state = "active"
            self._supervisor.proactive_suppressed = False
            self._supervisor.proactive_suppression_reason = None
        reply_text = interaction.response.reply_text
        executed = True
        if reply_text and self._speak_enabled:
            voice_mode = self._configured_voice_mode or self.operator_console.default_live_voice_mode()
            runtime = self.operator_console.voice_manager.get_runtime(voice_mode)
            self._transition_voice_state(
                CompanionVoiceLoopState.THINKING,
                session_id=session_id,
                message=reason,
            )
            start = perf_counter()
            speech_output = runtime.text_to_speech.speak(session_id, reply_text, mode=voice_mode)
            if speech_output.status.value in {"speaking", "completed", "simulated"}:
                self._transition_voice_state(
                    CompanionVoiceLoopState.SPEAKING,
                    session_id=session_id,
                    message="proactive_reply_spoken",
                    first_audio_latency_ms=round((perf_counter() - start) * 1000.0, 2),
                )
            self._transition_voice_state(
                CompanionVoiceLoopState.COOLDOWN,
                session_id=session_id,
                message="proactive_reply_complete",
            )
        if reply_text:
            self._queue_runtime_event(
                event_type="proactive_reply",
                session_id=session_id,
                message=reason,
                reply_text=reply_text,
                trace_id=interaction.response.trace_id,
                state=(initiative_payload or {}).get("initiative_action") if initiative_payload else None,
            )
        log_event(
            logger,
            logging.INFO,
            "shift_trigger_executed",
            session_id=session_id,
            trace_id=interaction.response.trace_id,
            reason=reason,
            outcome=interaction.outcome,
        )
        return executed

    def _promote_memory_if_needed(self, *, session_id: str) -> None:
        session = self.operator_console.orchestrator.get_session(session_id)
        if session is None or not session.transcript:
            return
        latest_trace = self.operator_console.orchestrator.list_traces(session_id=session_id, limit=1).items
        trace = latest_trace[0] if latest_trace else None
        if trace is None or trace.trace_id == self._last_promoted_trace_id:
            return
        self._last_promoted_trace_id = trace.trace_id
        user_memory = self.operator_console.orchestrator.memory.get_user_memory(session.user_id) if session.user_id else None
        promotions = self.operator_console.orchestrator.knowledge_tools.record_turn_memory(
            session=session,
            user_memory=user_memory,
            trace_id=trace.trace_id,
            reply_text=trace.response.reply_text,
            intent=trace.reasoning.intent,
            source_refs=[item.source_ref for item in trace.reasoning.grounding_sources if item.source_ref],
        )
        if promotions:
            with self._lock:
                self._memory_promotions.extend(promotions)

    def _build_initiative_context(
        self,
        *,
        session_id: str,
        now,
        observer_event: SceneObservationEvent | None,
    ) -> InitiativeContext | None:
        session = self.operator_console.orchestrator.get_session(session_id)
        if session is None:
            session = self.operator_console.orchestrator.create_session(
                self.operator_console.orchestrator.build_session_request(
                    session_id=session_id,
                    channel="speech",
                )
            )
        latest_trace_items = self.operator_console.orchestrator.list_traces(session_id=session_id, limit=1).items
        latest_trace = latest_trace_items[0] if latest_trace_items else None
        fallback_active = self.operator_console._build_fallback_state(
            backend_status=self.operator_console.backend_router.runtime_statuses(),
            latest_trace=latest_trace,
            heartbeat=self.operator_console.edge_gateway.get_heartbeat(),
        ).active
        latest_perception = self.operator_console.perception_service.get_latest_snapshot(session_id)
        if latest_perception is None:
            latest_perception = self.operator_console.perception_service.get_latest_snapshot()
        user_memory = (
            self.operator_console.orchestrator.memory.get_user_memory(session.user_id)
            if session.user_id
            else None
        )
        digests = tuple(
            self.operator_console.orchestrator.list_session_digests(
                session_id=session_id,
                user_id=session.user_id,
                limit=5,
            ).items
        )
        open_reminders = tuple(
            self.operator_console.orchestrator.list_reminders(
                session_id=session_id,
                user_id=session.user_id,
                status=ReminderStatus.OPEN,
                limit=10,
            ).items
        )
        browser_context = browser_context_from_status(None)
        try:
            browser_context = browser_context_from_status(
                self.operator_console.get_action_plane_browser_status(session_id=session_id)
            )
        except RuntimeError:
            browser_context = browser_context_from_status(None)
        observer_record = None
        if observer_event is not None:
            observer_record = self._scene_event_record_for(observer_event)
        elif self._scene_event_buffer:
            with self._lock:
                observer_record = self._scene_event_buffer[-1].model_copy(deep=True) if self._scene_event_buffer else None
        return InitiativeContext(
            now=now,
            session=session,
            shift_snapshot=self.operator_console.orchestrator.get_shift_supervisor(),
            presence_status=self.presence_runtime_status(),
            voice_status=self.voice_loop_status(),
            fallback_active=fallback_active,
            semantic_provider_available=self._semantic_provider_available(),
            fresh_semantic_scene_available=self._fresh_semantic_scene_available(session_id=session_id),
            last_semantic_refresh_at=self._last_semantic_refresh_at,
            observer_event=observer_record,
            latest_perception=latest_perception,
            user_memory=user_memory,
            digests=digests,
            open_reminders=open_reminders,
            browser_context=browser_context,
            terminal_activity=terminal_activity_for_session(session, now=now),
        )

    def _initiative_payload(self, evaluation) -> dict[str, object] | None:
        if evaluation.use_shift_prompt and not evaluation.reply_text:
            return None
        payload: dict[str, object] = {}
        if evaluation.reply_text:
            payload["initiative_reply_text"] = evaluation.reply_text
        if evaluation.intent:
            payload["initiative_intent"] = evaluation.intent
        if evaluation.proactive_action:
            payload["initiative_action"] = evaluation.proactive_action
        if evaluation.candidate_kind:
            payload["initiative_action_key"] = evaluation.candidate_kind
        if evaluation.reason:
            payload["initiative_reason"] = evaluation.reason
        return payload or None

    def _run_initiative_action(self, *, session_id: str, evaluation) -> bool:
        workflow_id = evaluation.workflow_id
        if workflow_id is None:
            return False
        reminder_id = str(evaluation.workflow_inputs.get("reminder_id") or "").strip() or None
        try:
            response = self.operator_console.start_proactive_action_plane_workflow(
                WorkflowStartRequestRecord(
                    workflow_id=workflow_id,
                    session_id=session_id,
                    inputs=dict(evaluation.workflow_inputs),
                    note=evaluation.reason,
                )
            )
        except Exception as exc:
            self._queue_runtime_event(
                event_type="initiative_action_failed",
                session_id=session_id,
                message=f"{workflow_id}:{exc}",
                state=InitiativeDecision.ACT.value,
            )
            log_event(
                logger,
                logging.WARNING,
                "initiative_action_failed",
                session_id=session_id,
                workflow_id=workflow_id,
                reason=evaluation.reason,
                error=str(exc),
            )
            return True

        if reminder_id:
            self._mark_reminder_triggered(reminder_id, triggered_at=utc_now())
        self._queue_runtime_event(
            event_type="initiative_action",
            session_id=session_id,
            message=f"{workflow_id}:{response.run.status.value}",
            state=InitiativeDecision.ACT.value,
        )
        log_event(
            logger,
            logging.INFO,
            "initiative_action_started",
            session_id=session_id,
            workflow_id=workflow_id,
            workflow_run_id=response.run.workflow_run_id,
            status=response.run.status.value,
            reason=evaluation.reason,
        )
        with self._lock:
            self._supervisor.last_outcome = response.run.status.value
        return True

    def _mark_reminder_triggered(self, reminder_id: str, *, triggered_at) -> None:
        reminder = self.operator_console.orchestrator.memory.get_reminder(reminder_id)
        if reminder is None:
            return
        reminder.last_triggered_at = triggered_at
        self.operator_console.orchestrator.upsert_reminder(reminder)

    @staticmethod
    def _coarse_trigger_from_initiative(evaluation) -> tuple[CompanionTriggerDecision, bool, str | None]:
        if evaluation.should_refresh_scene:
            return CompanionTriggerDecision.REFRESH_SCENE, False, None
        if evaluation.decision == InitiativeDecision.ASK:
            return CompanionTriggerDecision.ASK_FOLLOW_UP, True, None
        if evaluation.decision == InitiativeDecision.SUGGEST:
            return CompanionTriggerDecision.SPEAK_NOW, True, None
        if evaluation.decision == InitiativeDecision.ACT:
            return CompanionTriggerDecision.OBSERVE_ONLY, True, None
        suppression_reason = evaluation.suppression_reason
        if suppression_reason == "fallback_active" or (
            suppression_reason is not None and suppression_reason.startswith("shift_state:")
        ):
            return CompanionTriggerDecision.SAFE_IDLE, False, suppression_reason
        if evaluation.candidate_count > 0:
            return CompanionTriggerDecision.OBSERVE_ONLY, False, suppression_reason
        return CompanionTriggerDecision.WAIT, False, suppression_reason

    def _record_initiative(self, evaluation, *, observed_at, executed: bool, status: InitiativeStatus) -> None:
        with self._lock:
            self._initiative_status = status
        self._initiative_history.append(
            {
                "timestamp": observed_at.isoformat(),
                "stage_trace": [item.value for item in evaluation.stage_trace],
                "decision": evaluation.decision.value,
                "candidate_kind": evaluation.candidate_kind,
                "candidate_count": evaluation.candidate_count,
                "reason": evaluation.reason,
                "reason_codes": list(evaluation.reason_codes),
                "suppression_reason": evaluation.suppression_reason,
                "should_refresh_scene": evaluation.should_refresh_scene,
                "refresh_reason": evaluation.refresh_reason,
                "use_shift_prompt": evaluation.use_shift_prompt,
                "reply_text": evaluation.reply_text,
                "workflow_id": evaluation.workflow_id,
                "workflow_inputs": dict(evaluation.workflow_inputs),
                "scorecard": evaluation.scorecard.model_dump(mode="json"),
                "grounding": evaluation.grounding.model_dump(mode="json"),
                "executed": executed,
            }
        )

    def _record_trigger_from_initiative(
        self,
        evaluation,
        *,
        observed_at,
        cooldown_until,
        coarse_decision: CompanionTriggerDecision,
        proactive_eligible: bool,
        suppression_reason: str | None,
        executed: bool,
    ) -> None:
        with self._lock:
            self._trigger_status.enabled = True
            self._trigger_status.last_decision = coarse_decision
            self._trigger_status.last_reason = evaluation.reason
            self._trigger_status.last_evaluated_at = observed_at
            self._trigger_status.proactive_eligible = proactive_eligible
            self._trigger_status.suppressed_reason = suppression_reason
            self._trigger_status.fallback_active = suppression_reason == "fallback_active"
            self._trigger_status.cooldown_until = cooldown_until
            if coarse_decision in {
                CompanionTriggerDecision.SPEAK_NOW,
                CompanionTriggerDecision.ASK_FOLLOW_UP,
                CompanionTriggerDecision.REFRESH_SCENE,
            } or (evaluation.decision == InitiativeDecision.ACT and executed):
                self._trigger_status.trigger_count += 1
                self._trigger_status.last_action_at = observed_at
            if suppression_reason:
                self._trigger_status.suppression_count += 1
            self._supervisor.last_trigger_decision = coarse_decision
            self._supervisor.proactive_suppressed = bool(suppression_reason)
            self._supervisor.proactive_suppression_reason = suppression_reason
        self._trigger_history.append(
            {
                "timestamp": observed_at.isoformat(),
                "decision": coarse_decision.value,
                "reason": evaluation.reason,
                "initiative_decision": evaluation.decision.value,
                "proactive_eligible": proactive_eligible,
                "suppressed_reason": suppression_reason,
                "executed": executed,
            }
        )

    @staticmethod
    def _scene_event_record_for(event: SceneObservationEvent) -> SceneObserverEventRecord:
        return SceneObserverEventRecord(
            observed_at=event.observed_at,
            backend=event.backend,
            source_kind=event.source_kind,
            person_present=event.person_present,
            presence_state=event.presence_state,
            people_count_estimate=event.people_count_estimate,
            attention_state=event.attention_state,
            attention_target_hint=event.attention_target_hint,
            attention_toward_device_score=event.attention_toward_device_score,
            scene_change_score=event.change_score,
            motion_changed=event.motion_changed,
            motion_state=event.motion_state,
            new_entrant=event.new_entrant,
            engagement_shift_hint=event.engagement_shift_hint,
            signal_confidence=event.signal_confidence,
            environment_state=event.environment_state,
            refresh_recommended=event.semantic_refresh_recommended,
            refresh_reason=event.refresh_reason,
            capability_limits=list(event.capability_limits),
            limited_awareness=bool(event.capability_limits),
            provenance=[f"watcher:{event.backend}"],
        )

    def _agent_runtime_export(self, session_id: str | None) -> dict[str, object]:
        if not session_id:
            return {}
        traces = self.operator_console.orchestrator.list_traces(session_id=session_id, limit=1).items
        trace = traces[0] if traces else None
        if trace is None:
            return {}
        return {
            "active_playbook": trace.reasoning.active_playbook,
            "active_playbook_variant": trace.reasoning.active_playbook_variant,
            "active_subagent": trace.reasoning.active_subagent,
            "tool_chain": list(trace.reasoning.tool_chain),
            "fallback_reason": trace.reasoning.fallback_reason,
            "fallback_classification": (
                trace.reasoning.fallback_classification.value
                if trace.reasoning.fallback_classification is not None
                else None
            ),
            "unavailable_capabilities": list(trace.reasoning.unavailable_capabilities),
            "intentionally_skipped_capabilities": list(trace.reasoning.intentionally_skipped_capabilities),
        }

    def _record_scene_observer_event(self, event: SceneObservationEvent) -> None:
        record = SceneObserverEventRecord(
            observed_at=event.observed_at,
            backend=event.backend,
            source_kind=event.source_kind,
            person_present=event.person_present,
            presence_state=event.presence_state,
            people_count_estimate=event.people_count_estimate,
            attention_state=event.attention_state,
            attention_target_hint=event.attention_target_hint,
            attention_toward_device_score=event.attention_toward_device_score,
            scene_change_score=event.change_score,
            motion_changed=event.motion_changed,
            motion_state=event.motion_state,
            new_entrant=event.new_entrant,
            engagement_shift_hint=event.engagement_shift_hint,
            signal_confidence=event.signal_confidence,
            environment_state=event.environment_state,
            refresh_recommended=event.semantic_refresh_recommended,
            refresh_reason=event.refresh_reason,
            capability_limits=list(event.capability_limits),
            limited_awareness=bool(event.capability_limits),
            provenance=[f"watcher:{event.backend}"],
        )
        with self._lock:
            self._scene_event_buffer.append(record)
            self._scene_event_buffer = self._scene_event_buffer[-25:]
            self._scene_status.buffer_size = len(self._scene_event_buffer)
        self._scene_history.append(
            {
                "observed_at": event.observed_at.isoformat(),
                "backend": event.backend,
                "change_score": event.change_score,
                "motion_changed": event.motion_changed,
                "motion_state": event.motion_state.value,
                "person_present": event.person_present,
                "presence_state": event.presence_state.value,
                "people_count_estimate": event.people_count_estimate,
                "person_transition": event.person_transition,
                "new_entrant": event.new_entrant,
                "attention_state": event.attention_state,
                "attention_target_hint": event.attention_target_hint,
                "attention_toward_device_score": event.attention_toward_device_score,
                "engagement_shift_hint": event.engagement_shift_hint.value,
                "signal_confidence": event.signal_confidence,
                "environment_state": event.environment_state.value,
                "semantic_refresh_recommended": event.semantic_refresh_recommended,
                "refresh_reason": event.refresh_reason,
                "capability_limits": list(event.capability_limits),
            }
        )

    @staticmethod
    def _watcher_note_for_event(event: SceneObservationEvent) -> str | None:
        if event.refresh_reason == "new_arrival":
            return "Watcher noticed a new arrival near the device."
        if event.refresh_reason == "departure":
            return "Watcher noticed that the previously visible visitor left the scene."
        if event.refresh_reason == "attention_changed":
            return "Watcher noticed attention shifted relative to the device."
        if event.motion_changed:
            return "Watcher observed a meaningful scene change."
        if event.person_present is False:
            return "Watcher sees no one in view."
        return None

    def _transition_voice_state(
        self,
        state: CompanionVoiceLoopState,
        *,
        session_id: str | None,
        message: str | None,
        armed_until=None,
        degraded_reason: str | None = None,
        transcript_latency_ms: float | None = None,
        first_audio_latency_ms: float | None = None,
        interruption_latency_ms: float | None = None,
        partial_transcript_preview: str | None = None,
        audio_backend: str | None = None,
        interrupted: bool = False,
    ) -> None:
        now = utc_now()
        with self._lock:
            self._voice_loop.state = state
            self._voice_loop.session_id = session_id or self._voice_loop.session_id
            self._voice_loop.last_transition_at = now
            if armed_until is not None:
                self._voice_loop.armed_until = armed_until
            if transcript_latency_ms is not None:
                self._voice_loop.transcript_latency_ms = transcript_latency_ms
                self._voice_loop.last_transcript_at = now
            if first_audio_latency_ms is not None:
                self._voice_loop.first_audio_latency_ms = first_audio_latency_ms
                self._voice_loop.last_reply_at = now
            if interruption_latency_ms is not None:
                self._voice_loop.interruption_latency_ms = interruption_latency_ms
                self._voice_loop.last_interruption_at = now
            if degraded_reason is not None:
                self._voice_loop.degraded_reason = degraded_reason
            if partial_transcript_preview is not None:
                self._voice_loop.partial_transcript_preview = partial_transcript_preview
            if audio_backend is not None:
                self._voice_loop.audio_backend = audio_backend
            if interrupted:
                self._voice_loop.interruption_count += 1
            self._supervisor.state = state.value
        self._voice_history.append(
            {
                "timestamp": now.isoformat(),
                "state": state.value,
                "session_id": session_id,
                "message": message,
                "transcript_latency_ms": transcript_latency_ms,
                "first_audio_latency_ms": first_audio_latency_ms,
                "interruption_latency_ms": interruption_latency_ms,
                "degraded_reason": degraded_reason,
                "partial_transcript_preview": partial_transcript_preview,
                "audio_backend": audio_backend,
            }
        )
        log_event(
            logger,
            logging.INFO,
            "voice_loop_state_changed",
            session_id=session_id,
            voice_turn_id=session_id,
            state=state.value,
            state_message=message,
            degraded_reason=degraded_reason,
            audio_backend=audio_backend,
        )
        self._sync_character_projection(session_id=session_id, reason=f"voice:{state.value}")

    def _record_presence_transition(self, status: CompanionPresenceStatus, history_entry: dict[str, object]) -> None:
        with self._lock:
            self._presence_history.append(history_entry)
        self._queue_runtime_event(
            event_type="presence_state_changed",
            session_id=status.session_id,
            message=status.message,
            state=status.state.value,
        )
        log_event(
            logger,
            logging.INFO,
            "presence_state_changed",
            session_id=status.session_id,
            state=status.state.value,
            state_message=status.message,
            slow_path_active=status.slow_path_active,
            degraded_reason=status.degraded_reason,
        )
        self._sync_character_projection(session_id=status.session_id, reason=f"presence:{status.state.value}")

    def _sync_character_projection(self, *, session_id: str | None, reason: str) -> None:
        edge_gateway = self.operator_console.edge_gateway
        if not hasattr(edge_gateway, "apply_character_projection"):
            return
        target_session_id = session_id or self._resolve_session_id()
        try:
            surface = self.operator_console.get_character_presence_surface(session_id=target_session_id)
        except Exception:
            log_event(
                logger,
                logging.WARNING,
                "character_projection_surface_unavailable",
                session_id=target_session_id,
                projection_reason=reason,
            )
            return

        intent = surface.character_semantic_intent
        profile = surface.character_projection_profile
        signature = repr(
            (
                profile.value,
                intent.surface_state,
                intent.expression_name,
                intent.gaze_target,
                intent.gesture_name,
                intent.animation_name,
                intent.motion_hint,
                intent.safe_idle_requested,
                intent.pose.model_dump(mode="json"),
            )
        )
        now = monotonic()
        min_interval = max(0.1, float(self.settings.blink_character_projection_min_interval_seconds))
        if signature == self._last_character_projection_signature and now - self._last_character_projection_at < min_interval:
            return

        try:
            body_state = edge_gateway.apply_character_projection(intent=intent, profile=profile)
        except Exception:
            log_event(
                logger,
                logging.WARNING,
                "character_projection_dispatch_failed",
                session_id=target_session_id,
                projection_reason=reason,
                projection_profile=profile.value,
            )
            return

        projection = body_state.character_projection
        self._last_character_projection_signature = signature
        self._last_character_projection_at = now
        self._queue_runtime_event(
            event_type="character_projection_changed",
            session_id=target_session_id,
            message=(
                f"profile={profile.value} outcome={projection.outcome if projection is not None else 'unknown'}"
                if projection is not None
                else f"profile={profile.value}"
            ),
            state=intent.surface_state,
        )
        log_event(
            logger,
            logging.INFO,
            "character_projection_changed",
            session_id=target_session_id,
            projection_reason=reason,
            projection_profile=profile.value,
            surface_state=intent.surface_state,
            robot_head_applied=projection.robot_head_applied if projection is not None else False,
            blocked_reason=projection.blocked_reason if projection is not None else None,
        )

    def _resolve_session_id(self) -> str:
        with self._lock:
            if self._active_session_id:
                return self._active_session_id
        participant_router = self.operator_console.orchestrator.get_participant_router()
        if participant_router.active_session_id:
            return participant_router.active_session_id
        world_state = self.operator_console.orchestrator.get_world_state()
        return world_state.last_session_id or "local-companion-live"

    def _semantic_provider_mode(self) -> PerceptionProviderMode | None:
        return self.operator_console.backend_router.selected_semantic_perception_mode()

    def _semantic_provider_available(self) -> bool:
        return self._semantic_provider_mode() is not None

    def _fresh_semantic_scene_available(self, *, session_id: str) -> bool:
        latest = self.operator_console.perception_service.get_latest_snapshot(session_id)
        if latest is None:
            latest = self.operator_console.perception_service.get_latest_snapshot()
        if latest is None or latest.limited_awareness:
            return False
        if latest.tier != PerceptionTier.SEMANTIC:
            return False
        if latest.provider_mode not in {PerceptionProviderMode.OLLAMA_VISION, PerceptionProviderMode.MULTIMODAL_LLM}:
            return False
        captured_at = latest.source_frame.captured_at or latest.created_at
        age_seconds = (utc_now() - captured_at).total_seconds()
        return age_seconds <= 15.0

    def _resolve_audio_mode(self, value: CompanionAudioMode | str | None) -> CompanionAudioMode:
        raw = value.value if isinstance(value, CompanionAudioMode) else str(value or CompanionAudioMode.PUSH_TO_TALK.value)
        return CompanionAudioMode(raw.strip().lower())

    def _selected_open_mic_candidates(self) -> tuple[str, ...]:
        candidates = list(
            backend_candidates_for(
                self.settings,
                RuntimeBackendKind.SPEECH_TO_TEXT,
                include_legacy_overrides=False,
            )
        )
        if self.audio_mode() == CompanionAudioMode.OPEN_MIC and "whisper_cpp_local" in candidates:
            candidates = ["whisper_cpp_local", *[item for item in candidates if item != "whisper_cpp_local"]]
        return tuple(candidates)

    def _selected_open_mic_backend(self) -> str | None:
        candidates = self._selected_open_mic_candidates()
        return candidates[0] if candidates else None

    def _note_scene_cache(
        self,
        snapshot: PerceptionSnapshotRecord,
        *,
        invalidated_because: str | None,
    ) -> None:
        captured_at = snapshot.source_frame.captured_at or snapshot.created_at
        facts: list[str] = []
        for observation in snapshot.observations[:8]:
            if observation.text_value:
                facts.append(observation.text_value)
            elif observation.bool_value is not None:
                facts.append(f"{observation.observation_type.value}={observation.bool_value}")
        with self._lock:
            self._scene_cache = SceneCacheRecord(
                session_id=snapshot.session_id,
                captured_at=captured_at,
                stale_after=captured_at + timedelta(seconds=max(15.0, float(self.settings.blink_semantic_refresh_min_interval_seconds))),
                summary=snapshot.scene_summary,
                facts=facts,
                invalidated_because=invalidated_because,
            )

    def _invalidate_scene_cache(self, reason: str) -> None:
        with self._lock:
            if self._scene_cache is None:
                return
            self._scene_cache = self._scene_cache.model_copy(update={"invalidated_because": reason})

    def _queue_runtime_event(
        self,
        *,
        event_type: str,
        session_id: str | None,
        message: str | None,
        reply_text: str | None = None,
        trace_id: str | None = None,
        state: str | None = None,
    ) -> None:
        with self._lock:
            self._runtime_events.append(
                {
                    "timestamp": utc_now().isoformat(),
                    "event_type": event_type,
                    "session_id": session_id,
                    "message": message,
                    "reply_text": reply_text,
                    "trace_id": trace_id,
                    "state": state,
                }
            )


__all__ = ["ShiftAutonomyRunner"]
