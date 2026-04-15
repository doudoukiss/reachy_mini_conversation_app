from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

from embodied_stack.shared.contracts import BodyDriverMode, CompanionContextMode, RobotMode


class Settings(BaseSettings):
    project_name: str = "Blink-AI"
    community_name: str = "Future Community Space"
    pilot_site: str = "Demo Community Center"
    venue_content_dir: str = "pilot_site/demo_community_center"

    brain_host: str = "0.0.0.0"
    brain_port: int = 8000
    brain_store_path: str = "runtime/brain_store.json"
    brain_dialogue_backend: str = "rule_based"
    brain_voice_backend: str = "stub"
    brain_runtime_profile: str = "desktop_local_host"
    brain_deployment_target: str = "macbook_pro"
    brain_default_response_mode: str = "guide"
    brain_instruction_dir: str = "src/embodied_stack/brain/instructions"
    blink_runtime_mode: RobotMode = RobotMode.DESKTOP_VIRTUAL_BODY
    blink_model_profile: str = "companion_live"
    blink_backend_profile: str | None = None
    blink_voice_profile: str = "desktop_local"
    blink_audio_mode: str = "push_to_talk"
    blink_context_mode: CompanionContextMode = CompanionContextMode.PERSONAL_LOCAL
    blink_appliance_mode: bool = False
    blink_appliance_profile_file: str = "runtime/appliance_profile.json"
    blink_appliance_config_source: str = "repo_defaults"
    blink_text_backend: str | None = None
    blink_vision_backend: str | None = None
    blink_embedding_backend: str | None = None
    blink_stt_backend: str | None = None
    blink_tts_backend: str | None = None
    blink_camera_source: str = "default"
    blink_camera_device: str = "default"
    blink_mic_device: str = "default"
    blink_speaker_device: str = "system_default"
    blink_device_preset: str = "auto"
    blink_body_driver: BodyDriverMode = BodyDriverMode.VIRTUAL
    blink_planner_id: str = "agent_os_current"
    blink_planner_profile: str = "default"
    blink_serial_port: str | None = None
    blink_servo_baud: int = 1000000
    blink_servo_autoscan: bool = True
    blink_serial_transport: str = "dry_run"
    blink_serial_fixture: str | None = "src/embodied_stack/body/fixtures/robot_head_serial_fixture.json"
    blink_serial_timeout_seconds: float = 0.2
    blink_head_profile: str = "src/embodied_stack/body/profiles/robot_head_v1.json"
    blink_head_calibration: str = "src/embodied_stack/body/profiles/robot_head_v1.calibration_template.json"
    blink_action_plane_disabled_connectors: str = ""
    blink_action_plane_local_file_roots: str = "."
    blink_action_plane_draft_dir: str = "runtime/actions/drafts"
    blink_action_plane_stage_dir: str = "runtime/actions/staged"
    blink_action_plane_export_dir: str = "runtime/actions/exports"
    blink_action_plane_browser_backend: str = "disabled"
    blink_action_plane_browser_headless: bool = True
    blink_action_plane_browser_storage_dir: str = "runtime/actions/browser"
    blink_action_plane_browser_allowed_hosts: str = ""
    blink_workflow_morning_briefing_time: str = "09:00"
    blink_workflow_run_timeout_seconds: float = 900.0
    live_voice_default_mode: str = "stub_demo"
    blink_browser_live_turn_timeout_seconds: float = 20.0
    blink_browser_live_visual_turn_timeout_seconds: float = 35.0
    blink_live_turn_diagnostic_dir: str = "runtime/diagnostics/live_turn_failures"
    blink_native_capture_seconds: float = 6.0
    blink_native_transcription_locale: str = "en-US"
    blink_always_on_enabled: bool = False
    blink_local_model_prewarm: bool = False
    blink_observer_interval_seconds: float = 2.5
    blink_scene_change_threshold: float = 0.08
    blink_semantic_refresh_min_interval_seconds: float = 20.0
    blink_voice_arm_timeout_seconds: float = 12.0
    blink_fast_presence_enabled: bool = True
    blink_fast_presence_ack_delay_seconds: float = 0.35
    blink_fast_presence_tool_delay_seconds: float = 1.5
    blink_character_projection_profile: str = "auto"
    blink_character_projection_min_interval_seconds: float = 0.75
    blink_body_semantic_tuning_path: str | None = None
    blink_vad_silence_ms: int = 900
    blink_vad_min_speech_ms: int = 250
    blink_model_idle_unload_seconds: float = 120.0
    blink_memory_digest_interval_minutes: float = 10.0
    macos_tts_voice: str = "Samantha"
    macos_tts_rate: int = 185
    perception_default_provider: str = "stub"
    perception_frame_dir: str = "runtime/perception_frames"
    perception_fixture_dir: str = "src/embodied_stack/demo/data"
    perception_multimodal_api_key: str | None = None
    perception_multimodal_base_url: str = "https://api.openai.com"
    perception_multimodal_model: str = "gpt-4.1-mini"
    perception_multimodal_timeout_seconds: float = 8.0
    shift_background_tick_enabled: bool = True
    shift_autonomy_tick_interval_seconds: float = 5.0
    shift_timezone: str | None = None
    shift_hours_summary: str | None = None
    shift_closing_lead_minutes: int = 30
    shift_follow_up_window_seconds: float = 45.0
    shift_attract_prompt_delay_seconds: float = 12.0
    shift_outreach_cooldown_seconds: float = 90.0
    shift_low_battery_threshold_pct: float = 20.0
    participant_router_resume_window_seconds: float = 180.0
    participant_router_active_speaker_retention_seconds: float = 20.0
    participant_router_session_timeout_seconds: float = 240.0
    participant_router_wait_prompt_cooldown_seconds: float = 12.0
    operator_auth_enabled: bool = True
    operator_auth_token: str | None = None
    operator_auth_runtime_file: str = "runtime/operator_auth.json"

    edge_host: str = "0.0.0.0"
    edge_port: int = 8010
    edge_base_url: str = "http://127.0.0.1:8010"
    edge_driver_profile: str = "fake_robot_full"
    edge_heartbeat_timeout_seconds: float = 15.0
    edge_gateway_timeout_seconds: float = 3.0
    edge_gateway_max_retries: int = 1
    edge_gateway_retry_backoff_seconds: float = 0.15

    demo_report_dir: str = "runtime/demo_runs"
    performance_report_dir: str = "runtime/performance_runs"
    demo_check_dir: str = "runtime/demo_checks"
    acceptance_report_dir: str = "runtime/diagnostics/acceptance"
    local_companion_certification_dir: str = "runtime/diagnostics/local_companion_certification"
    local_companion_burn_in_dir: str = "runtime/diagnostics/local_companion_burn_in"
    shift_report_dir: str = "runtime/shift_reports"
    episode_export_dir: str = "runtime/episodes"
    replay_export_dir: str = "runtime/replays"
    pilot_shift_fixture_dir: str = "src/embodied_stack/demo/pilot_days"

    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen3.5:9b"
    ollama_text_model: str | None = None
    ollama_vision_model: str | None = None
    ollama_embedding_model: str = "embeddinggemma:300m"
    ollama_timeout_seconds: float = 4.0
    ollama_text_timeout_seconds: float = 12.0
    ollama_text_cold_start_timeout_seconds: float = 30.0
    ollama_vision_timeout_seconds: float = 30.0
    ollama_embed_timeout_seconds: float = 5.0
    ollama_keep_alive: str = "5m"

    whisper_cpp_binary: str | None = None
    whisper_cpp_model_path: str | None = None
    whisper_cpp_timeout_seconds: float = 15.0

    piper_binary: str | None = None
    piper_model_path: str | None = None
    piper_timeout_seconds: float = 20.0

    grsai_api_key: str | None = None
    grsai_base_url: str = "https://grsai.dakka.com.cn"
    grsai_text_base_url: str | None = None
    grsai_model: str = "gpt-4o-mini"
    grsai_timeout_seconds: float = 8.0

    openai_api_key: str | None = None
    openai_base_url: str = "https://api.openai.com/v1"
    openai_responses_model: str = "gpt-4.1-mini"
    openai_timeout_seconds: float = 8.0

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    @property
    def uses_desktop_runtime(self) -> bool:
        return self.blink_runtime_mode in {
            RobotMode.DESKTOP_BODYLESS,
            RobotMode.DESKTOP_VIRTUAL_BODY,
            RobotMode.DESKTOP_SERIAL_BODY,
        }

    @property
    def uses_tethered_runtime(self) -> bool:
        return self.blink_runtime_mode in {
            RobotMode.TETHERED_FUTURE,
            RobotMode.TETHERED_DEMO,
            RobotMode.HARDWARE,
        }

    @property
    def resolved_body_driver(self) -> BodyDriverMode:
        by_mode = {
            RobotMode.DESKTOP_BODYLESS: BodyDriverMode.BODYLESS,
            RobotMode.DESKTOP_VIRTUAL_BODY: BodyDriverMode.VIRTUAL,
            RobotMode.DESKTOP_SERIAL_BODY: BodyDriverMode.SERIAL,
            RobotMode.TETHERED_FUTURE: BodyDriverMode.TETHERED,
            RobotMode.TETHERED_DEMO: BodyDriverMode.TETHERED,
            RobotMode.HARDWARE: BodyDriverMode.TETHERED,
        }
        return by_mode.get(self.blink_runtime_mode, self.blink_body_driver)

    @property
    def action_plane_disabled_connectors(self) -> set[str]:
        return {
            item.strip()
            for item in self.blink_action_plane_disabled_connectors.split(",")
            if item.strip()
        }

    @property
    def action_plane_local_file_roots_list(self) -> list[str]:
        roots = [
            item.strip()
            for item in self.blink_action_plane_local_file_roots.split(",")
            if item.strip()
        ]
        return roots or ["."]

    @property
    def action_plane_browser_backend_mode(self) -> str:
        return self.blink_action_plane_browser_backend.strip().lower() or "disabled"

    @property
    def action_plane_browser_allowed_hosts_list(self) -> list[str]:
        return [
            item.strip().lower()
            for item in self.blink_action_plane_browser_allowed_hosts.split(",")
            if item.strip()
        ]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
