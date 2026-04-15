from __future__ import annotations

from dataclasses import dataclass, field

from fastapi import FastAPI

from embodied_stack.backends.router import BackendRouter
from embodied_stack.brain.app import create_app as create_brain_app
from embodied_stack.config import Settings, get_settings
from embodied_stack.desktop.devices import DesktopDeviceError, DesktopDeviceRegistry
from embodied_stack.demo.investor_scenes import INVESTOR_SCENE_SEQUENCES
from embodied_stack.multimodal.events import build_scene_request
from embodied_stack.multimodal.perception import resolve_default_perception_mode
from embodied_stack.shared.models import (
    BrainResetRequest,
    CompanionAudioMode,
    InvestorSceneRunRequest,
    InvestorSceneRunResult,
    OperatorConsoleSnapshot,
    OperatorInteractionResult,
    OperatorVoiceTurnRequest,
    PerceptionFixtureDefinition,
    PerceptionProviderMode,
    PerceptionReplayRequest,
    PerceptionReplayResult,
    PerceptionSnapshotSubmitRequest,
    PerceptionSubmissionResult,
    ResponseMode,
    ResetResult,
    SessionRecord,
    VoiceRuntimeMode,
)

from .profiles import apply_desktop_profile, summarize_desktop_profile


def create_app(
    *,
    settings: Settings | None = None,
    device_registry: DesktopDeviceRegistry | None = None,
    backend_router: BackendRouter | None = None,
) -> FastAPI:
    resolved_settings = apply_desktop_profile(settings or get_settings())
    return create_brain_app(
        settings=resolved_settings,
        device_registry=device_registry,
        backend_router=backend_router,
    )


@dataclass
class DesktopLiveTurnResult:
    interaction: OperatorInteractionResult
    perception_result: PerceptionSubmissionResult | PerceptionReplayResult | None = None
    camera_error: str | None = None


@dataclass
class DesktopRuntimeManager:
    settings: Settings
    app: FastAPI
    _started: bool = field(default=False, init=False)

    @property
    def orchestrator(self):
        return self.app.state.orchestrator

    @property
    def operator_console(self):
        return self.app.state.operator_console

    @property
    def perception_service(self):
        return self.app.state.perception_service

    @property
    def device_registry(self) -> DesktopDeviceRegistry:
        return self.app.state.device_registry

    @property
    def voice_manager(self):
        return self.app.state.operator_console.voice_manager

    @property
    def shift_runner(self):
        return self.app.state.shift_runner

    @property
    def supervisor(self):
        return self.app.state.shift_runner

    @property
    def demo_coordinator(self):
        return self.app.state.demo_coordinator

    def start(self) -> None:
        if not self._started:
            self.shift_runner.start()
            self._started = True

    def stop(self) -> None:
        if self._started:
            self.shift_runner.stop()
            self._started = False

    def __enter__(self) -> "DesktopRuntimeManager":
        self.start()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.stop()

    def ensure_session(
        self,
        *,
        session_id: str | None = None,
        user_id: str | None = None,
        channel: str = "speech",
        response_mode: ResponseMode | None = None,
    ) -> SessionRecord:
        if session_id:
            existing = self.orchestrator.get_session(session_id)
            if existing is not None:
                self.shift_runner.set_active_session(existing.session_id)
                return existing
        request = self.orchestrator.build_session_request(
            session_id=session_id,
            user_id=user_id,
            channel=channel,
            response_mode=response_mode,
        )
        session = self.orchestrator.create_session(request)
        self.shift_runner.set_active_session(session.session_id)
        return session

    def submit_text(
        self,
        text: str,
        *,
        session_id: str | None = None,
        user_id: str | None = None,
        response_mode: ResponseMode | None = None,
        voice_mode: VoiceRuntimeMode | None = None,
        speak_reply: bool = True,
        source: str = "desktop_local_cli",
    ) -> OperatorInteractionResult:
        session = self.ensure_session(session_id=session_id, user_id=user_id, response_mode=response_mode)
        resolved_voice_mode = self._resolve_typed_voice_mode(
            voice_mode or self.default_voice_mode(),
            speak_reply=speak_reply,
        )
        if self.settings.blink_always_on_enabled:
            self.shift_runner.prepare_typed_turn(
                session_id=session.session_id,
                voice_mode=resolved_voice_mode,
            )
        interaction = self.operator_console.submit_text_turn(
            OperatorVoiceTurnRequest(
                session_id=session.session_id,
                user_id=user_id,
                input_text=text,
                response_mode=response_mode,
                voice_mode=resolved_voice_mode,
                speak_reply=speak_reply,
                source=source,
            )
        )
        if self.settings.blink_always_on_enabled:
            self.shift_runner.finalize_turn(
                session_id=session.session_id,
                transcript_text=text,
                interaction_latency_ms=interaction.latency_ms,
                spoken=bool(
                    interaction.voice_output
                    and interaction.voice_output.status.value in {"speaking", "completed", "simulated"}
                ),
            )
        return interaction

    def _resolve_typed_voice_mode(self, voice_mode: VoiceRuntimeMode, *, speak_reply: bool) -> VoiceRuntimeMode:
        if voice_mode == VoiceRuntimeMode.DESKTOP_NATIVE:
            return VoiceRuntimeMode.MACOS_SAY if speak_reply else VoiceRuntimeMode.STUB_DEMO
        if voice_mode == VoiceRuntimeMode.OPEN_MIC_LOCAL:
            return VoiceRuntimeMode.MACOS_SAY if speak_reply else VoiceRuntimeMode.STUB_DEMO
        if voice_mode == VoiceRuntimeMode.BROWSER_LIVE and speak_reply:
            return VoiceRuntimeMode.BROWSER_LIVE_MACOS_SAY
        return voice_mode

    def submit_live_turn(
        self,
        *,
        session_id: str | None = None,
        user_id: str | None = None,
        response_mode: ResponseMode | None = None,
        voice_mode: VoiceRuntimeMode | None = None,
        speak_reply: bool = True,
        capture_camera: bool = True,
        provider_mode: PerceptionProviderMode | None = None,
        source: str = "desktop_native_runtime",
    ) -> DesktopLiveTurnResult:
        session = self.ensure_session(session_id=session_id, user_id=user_id, response_mode=response_mode)
        resolved_voice_mode = voice_mode or self.default_voice_mode()
        if self.settings.blink_always_on_enabled:
            self.shift_runner.prepare_live_listen(
                session_id=session.session_id,
                voice_mode=resolved_voice_mode,
            )
        perception_result = None
        camera_error = None
        if capture_camera:
            try:
                perception_result = self.capture_camera_observation(
                    session_id=session.session_id,
                    user_id=user_id,
                    provider_mode=provider_mode,
                )
            except DesktopDeviceError as exc:
                camera_error = exc.classification if exc.detail is None else f"{exc.classification}:{exc.detail}"

        interaction = self.operator_console.submit_text_turn(
            OperatorVoiceTurnRequest(
                session_id=session.session_id,
                user_id=user_id,
                input_text="",
                response_mode=response_mode,
                voice_mode=resolved_voice_mode,
                speak_reply=speak_reply,
                source=source,
            )
        )
        if self.settings.blink_always_on_enabled:
            self.shift_runner.finalize_turn(
                session_id=session.session_id,
                transcript_text=interaction.voice_output.transcript_text if interaction.voice_output is not None else None,
                interaction_latency_ms=interaction.latency_ms,
                spoken=bool(
                    interaction.voice_output
                    and interaction.voice_output.status.value in {"speaking", "completed", "simulated"}
                ),
            )
        return DesktopLiveTurnResult(
            interaction=interaction,
            perception_result=perception_result,
            camera_error=camera_error,
        )

    def submit_scene_observation(
        self,
        *,
        session_id: str | None = None,
        user_id: str | None = None,
        person_present: bool | None = None,
        people_count: int | None = None,
        engagement: float | str | None = None,
        scene_note: str | None = None,
        source: str = "desktop_local_runtime",
    ) -> PerceptionSubmissionResult:
        session = self.ensure_session(session_id=session_id, user_id=user_id, channel="vision")
        return self.operator_console.submit_perception_snapshot(
            build_scene_request(
                session_id=session.session_id,
                source=source,
                person_present=person_present,
                people_count=people_count,
                engagement=engagement,
                scene_note=scene_note,
                provider_mode=PerceptionProviderMode.MANUAL_ANNOTATIONS,
            )
        )

    def capture_camera_observation(
        self,
        *,
        session_id: str | None = None,
        user_id: str | None = None,
        provider_mode: PerceptionProviderMode | None = None,
        source: str = "desktop_native_camera",
    ) -> PerceptionSubmissionResult | PerceptionReplayResult:
        session = self.ensure_session(session_id=session_id, user_id=user_id, channel="vision")
        camera_source = self.device_registry.camera_capture.source
        resolved_provider = provider_mode or resolve_default_perception_mode(self.settings)

        if camera_source.mode == "fixture_replay":
            if not camera_source.fixture_path:
                raise DesktopDeviceError("desktop_camera_fixture_missing")
            return self.replay_fixture(
                camera_source.fixture_path,
                session_id=session.session_id,
                user_id=user_id,
                source=source,
            )
        if camera_source.mode != "webcam":
            raise DesktopDeviceError("desktop_camera_not_native", camera_source.note)

        capture = self.device_registry.capture_camera_snapshot()
        return self.operator_console.submit_perception_snapshot(
            PerceptionSnapshotSubmitRequest(
                session_id=session.session_id,
                provider_mode=resolved_provider,
                source=source,
                source_frame=capture.source_frame,
                image_data_url=capture.image_data_url,
            )
        )

    def submit_perception_probe(
        self,
        *,
        session_id: str | None = None,
        user_id: str | None = None,
        provider_mode: PerceptionProviderMode | None = None,
        image_data_url: str | None = None,
        source: str = "desktop_local_runtime",
    ) -> PerceptionSubmissionResult:
        session = self.ensure_session(session_id=session_id, user_id=user_id, channel="vision")
        return self.operator_console.submit_perception_snapshot(
            PerceptionSnapshotSubmitRequest(
                session_id=session.session_id,
                provider_mode=provider_mode or resolve_default_perception_mode(self.settings),
                source=source,
                image_data_url=image_data_url,
            )
        )

    def replay_fixture(
        self,
        fixture: str,
        *,
        session_id: str | None = None,
        user_id: str | None = None,
        source: str = "desktop_local_runtime",
    ) -> PerceptionReplayResult:
        session = self.ensure_session(session_id=session_id, user_id=user_id, channel="vision")
        return self.operator_console.replay_perception_fixture(
            PerceptionReplayRequest(
                session_id=session.session_id,
                fixture_path=self._resolve_fixture_path(fixture),
                source=source,
            )
        )

    def snapshot(self, *, session_id: str | None = None, voice_mode: VoiceRuntimeMode | None = None) -> OperatorConsoleSnapshot:
        return self.operator_console.get_snapshot(session_id=session_id, voice_mode=voice_mode)

    def configure_companion_loop(
        self,
        *,
        session_id: str,
        voice_mode: VoiceRuntimeMode | None = None,
        speak_enabled: bool = True,
        audio_mode: CompanionAudioMode | str | None = None,
    ) -> None:
        self.shift_runner.configure_loop(
            session_id=session_id,
            voice_mode=voice_mode or self.default_voice_mode(),
            speak_enabled=speak_enabled,
            audio_mode=audio_mode,
        )

    def set_audio_mode(self, mode: CompanionAudioMode | str) -> CompanionAudioMode:
        return self.shift_runner.set_audio_mode(mode)

    def silence_initiative(self, *, minutes: float = 15.0):
        if hasattr(self.shift_runner, "silence_initiative"):
            return self.shift_runner.silence_initiative(minutes=minutes)
        return None

    def clear_initiative_silence(self):
        if hasattr(self.shift_runner, "clear_initiative_silence"):
            return self.shift_runner.clear_initiative_silence()
        return None

    def drain_runtime_events(self) -> list[dict[str, object]]:
        if hasattr(self.shift_runner, "drain_runtime_events"):
            return self.shift_runner.drain_runtime_events()
        return []

    def interrupt_voice(
        self,
        *,
        session_id: str | None = None,
        voice_mode: VoiceRuntimeMode | None = None,
    ):
        return self.shift_runner.interrupt(session_id=session_id, voice_mode=voice_mode or self.default_voice_mode())

    def run_supervisor_once(self) -> None:
        self.shift_runner.run_once()

    def export_session_episode(self, session_id: str) -> object:
        from embodied_stack.shared.models import EpisodeExportSessionRequest

        return self.operator_console.export_session_episode(
            EpisodeExportSessionRequest(
                session_id=session_id,
                include_asset_refs=True,
            )
        )

    def default_voice_mode(self) -> VoiceRuntimeMode:
        return self.operator_console.default_live_voice_mode()

    def fixture_catalog(self) -> list[PerceptionFixtureDefinition]:
        return self.perception_service.list_fixtures().items

    def reset_demo(
        self,
        *,
        reset_edge: bool = True,
        clear_user_memory: bool = True,
        clear_demo_runs: bool = True,
    ) -> ResetResult:
        return self.demo_coordinator.reset_system(
            BrainResetRequest(
                reset_edge=reset_edge,
                clear_user_memory=clear_user_memory,
                clear_demo_runs=clear_demo_runs,
            )
        )

    def run_scene(
        self,
        scene_name: str,
        *,
        session_id: str | None = None,
        response_mode: ResponseMode | None = None,
        voice_mode: VoiceRuntimeMode | None = None,
        speak_reply: bool = True,
    ) -> InvestorSceneRunResult:
        return self.operator_console.run_investor_scene(
            scene_name,
            InvestorSceneRunRequest(
                session_id=session_id,
                response_mode=response_mode,
                voice_mode=voice_mode or self.default_voice_mode(),
                speak_reply=speak_reply,
            ),
        )

    def run_story(
        self,
        story_name: str = "desktop_story",
        *,
        session_id: str | None = None,
        response_mode: ResponseMode | None = None,
        voice_mode: VoiceRuntimeMode | None = None,
        speak_reply: bool = True,
        reset_first: bool = True,
    ) -> list[InvestorSceneRunResult]:
        scenes = INVESTOR_SCENE_SEQUENCES.get(story_name)
        if scenes is None:
            raise KeyError(story_name)
        if reset_first:
            self.reset_demo()
        return [
            self.run_scene(
                scene_name,
                session_id=session_id,
                response_mode=response_mode,
                voice_mode=voice_mode,
                speak_reply=speak_reply,
            )
            for scene_name in scenes
        ]

    def profile_summary(self) -> dict[str, object]:
        profile = summarize_desktop_profile(self.settings)
        backend_status = {
            item.kind.value: item
            for item in self.app.state.backend_router.runtime_statuses()
        }
        return {
            "runtime_mode": self.settings.blink_runtime_mode.value,
            "model_profile": self.settings.blink_model_profile,
            "resolved_model_profile": profile.model_profile,
            "backend_profile": profile.backend_profile,
            "context_mode": self.settings.blink_context_mode.value,
            "dialogue_backend": backend_status["text_reasoning"].backend_id,
            "voice_backend": self.settings.brain_voice_backend,
            "vision_backend": backend_status["vision_analysis"].backend_id,
            "embedding_backend": backend_status["embeddings"].backend_id,
            "stt_backend": backend_status["speech_to_text"].backend_id,
            "tts_backend": backend_status["text_to_speech"].backend_id,
            "voice_profile": self.settings.blink_voice_profile,
            "resolved_voice_profile": profile.voice_profile,
            "embodiment_profile": profile.embodiment_profile,
            "profile_summary": profile.profile_label,
            "provider_status": profile.provider_status,
            "provider_detail": profile.provider_detail,
            "live_voice_mode": self.default_voice_mode().value,
            "perception_provider": self.settings.perception_default_provider,
            "camera_source": self.settings.blink_camera_source,
            "body_driver": self.settings.resolved_body_driver.value,
        }

    def _resolve_fixture_path(self, fixture: str) -> str:
        for item in self.fixture_catalog():
            if fixture in {item.fixture_name, item.title, item.fixture_path}:
                return item.fixture_path
        return fixture


def build_desktop_runtime(
    *,
    settings: Settings | None = None,
    device_registry: DesktopDeviceRegistry | None = None,
    backend_router: BackendRouter | None = None,
) -> DesktopLocalRuntime:
    resolved_settings = apply_desktop_profile(settings or get_settings())
    app = create_app(
        settings=resolved_settings,
        device_registry=device_registry,
        backend_router=backend_router,
    )
    return DesktopRuntimeManager(settings=resolved_settings, app=app)


DesktopLocalRuntime = DesktopRuntimeManager


settings = apply_desktop_profile(get_settings())
app = create_app(settings=settings)


def main() -> None:
    import uvicorn

    uvicorn.run("embodied_stack.desktop.app:app", host=settings.brain_host, port=settings.brain_port, reload=False)


if __name__ == "__main__":
    main()
