from __future__ import annotations

import json
from pathlib import Path

from embodied_stack.config import Settings
from embodied_stack.desktop.runtime_profile import (
    ApplianceProfileStore,
    ApplianceRuntimeProfile,
    apply_appliance_profile,
    apply_runtime_profile_to_live_settings,
    ensure_runtime_layout,
    reset_runtime_state,
)
from embodied_stack.shared.models import CompanionContextMode, RobotMode


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
        **overrides,
    )


def test_apply_appliance_profile_uses_saved_profile_when_settings_are_not_explicit(tmp_path: Path):
    settings = build_settings(tmp_path)
    ApplianceProfileStore(settings.blink_appliance_profile_file).save(
        ApplianceRuntimeProfile(
            device_preset="external_monitor",
            microphone_device="LG UltraFine Display Audio",
            camera_device="LG UltraFine Display Camera",
            runtime_mode="desktop_virtual_body",
            context_mode="personal_local",
        )
    )

    resolved = apply_appliance_profile(settings)

    assert resolved.blink_appliance_config_source == "appliance_profile"
    assert resolved.blink_device_preset == "external_monitor"
    assert resolved.blink_mic_device == "LG UltraFine Display Audio"
    assert resolved.blink_camera_device == "LG UltraFine Display Camera"
    assert resolved.blink_runtime_mode == RobotMode.DESKTOP_VIRTUAL_BODY
    assert resolved.blink_context_mode == CompanionContextMode.PERSONAL_LOCAL


def test_apply_appliance_profile_keeps_explicit_settings_over_saved_profile(tmp_path: Path):
    settings = build_settings(
        tmp_path,
        blink_mic_device="Explicit USB Microphone",
        blink_device_preset="external_monitor",
    )
    ApplianceProfileStore(settings.blink_appliance_profile_file).save(
        ApplianceRuntimeProfile(
            device_preset="internal_macbook",
            microphone_device="MacBook Pro Microphone",
        )
    )

    resolved = apply_appliance_profile(settings)

    assert resolved.blink_appliance_config_source == "explicit_settings"
    assert resolved.blink_device_preset == "external_monitor"
    assert resolved.blink_mic_device == "Explicit USB Microphone"


def test_apply_appliance_profile_defaults_to_internal_macbook_in_appliance_mode(tmp_path: Path):
    settings = build_settings(tmp_path)

    resolved = apply_appliance_profile(settings)

    assert resolved.blink_device_preset == "internal_macbook"
    assert resolved.blink_appliance_config_source == "repo_defaults"


def test_apply_runtime_profile_to_live_settings_sets_appliance_profile_source_and_validates_types(tmp_path: Path):
    settings = build_settings(tmp_path, blink_device_preset="auto")
    profile = ApplianceRuntimeProfile(
        device_preset="external_monitor",
        microphone_device="LG UltraFine Display Audio",
        camera_device="LG UltraFine Display Camera",
        runtime_mode="desktop_virtual_body",
        context_mode="personal_local",
    )

    apply_runtime_profile_to_live_settings(settings, profile)

    assert settings.blink_appliance_config_source == "appliance_profile"
    assert settings.blink_device_preset == "external_monitor"
    assert settings.blink_runtime_mode == RobotMode.DESKTOP_VIRTUAL_BODY
    assert settings.blink_context_mode == CompanionContextMode.PERSONAL_LOCAL


def test_reset_runtime_state_removes_profile_and_auth_and_repairs_layout(tmp_path: Path):
    settings = build_settings(tmp_path)
    ensure_runtime_layout(settings)
    profile_path = Path(settings.blink_appliance_profile_file)
    auth_path = Path(settings.operator_auth_runtime_file)
    brain_store = Path(settings.brain_store_path)
    profile_path.write_text(
        json.dumps(ApplianceRuntimeProfile().model_dump(), indent=2),
        encoding="utf-8",
    )
    auth_path.write_text('{"token":"secret"}', encoding="utf-8")
    brain_store.write_text("{}", encoding="utf-8")

    removed = reset_runtime_state(settings)

    assert str(profile_path) in removed
    assert str(auth_path) in removed
    assert str(brain_store) in removed
    assert profile_path.exists() is False
    assert auth_path.exists() is False
    assert brain_store.exists() is False
    assert Path(settings.demo_report_dir).exists() is True
