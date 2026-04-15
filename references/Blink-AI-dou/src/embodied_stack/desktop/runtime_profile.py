from __future__ import annotations

import json
import shutil
from pathlib import Path

from pydantic import BaseModel, Field

from embodied_stack.config import Settings
from embodied_stack.persistence import load_json_value_or_quarantine, write_json_atomic
from embodied_stack.shared.models import ApplianceStartupSummary, FallbackState, StartupDeviceSelection, utc_now


APPLIANCE_RUNTIME_DIR_FIELDS = (
    "brain_store_path",
    "demo_report_dir",
    "demo_check_dir",
    "shift_report_dir",
    "episode_export_dir",
    "perception_frame_dir",
)

APPLIANCE_PROFILE_SETTING_FIELDS = (
    "blink_model_profile",
    "blink_backend_profile",
    "blink_voice_profile",
    "blink_runtime_mode",
    "blink_audio_mode",
    "blink_context_mode",
    "blink_mic_device",
    "blink_camera_device",
    "blink_speaker_device",
    "blink_device_preset",
)


class ApplianceRuntimeProfile(BaseModel):
    version: int = 1
    saved_at: str = Field(default_factory=lambda: utc_now().isoformat())
    setup_complete: bool = True
    device_preset: str = "internal_macbook"
    microphone_device: str = "default"
    camera_device: str = "default"
    speaker_device: str = "system_default"
    model_profile: str = "companion_live"
    backend_profile: str | None = None
    voice_profile: str = "desktop_local"
    runtime_mode: str = "desktop_virtual_body"
    audio_mode: str = "push_to_talk"
    context_mode: str = "personal_local"

    def to_settings_overrides(self) -> dict[str, object]:
        return {
            "blink_model_profile": self.model_profile,
            "blink_backend_profile": self.backend_profile,
            "blink_voice_profile": self.voice_profile,
            "blink_runtime_mode": self.runtime_mode,
            "blink_audio_mode": self.audio_mode,
            "blink_context_mode": self.context_mode,
            "blink_mic_device": self.microphone_device,
            "blink_camera_device": self.camera_device,
            "blink_speaker_device": self.speaker_device,
            "blink_device_preset": self.device_preset,
        }


class ApplianceProfileStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def load(self) -> ApplianceRuntimeProfile | None:
        if not self.path.exists():
            return None
        payload = load_json_value_or_quarantine(self.path, quarantine_invalid=True)
        if not isinstance(payload, dict):
            return None
        try:
            return ApplianceRuntimeProfile.model_validate(payload)
        except Exception:
            return None

    def save(self, profile: ApplianceRuntimeProfile) -> ApplianceRuntimeProfile:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        write_json_atomic(self.path, profile, keep_backups=3)
        return profile

    def exists(self) -> bool:
        return self.path.exists()

    def clear(self) -> None:
        self.path.unlink(missing_ok=True)


def _validated_settings_update(settings: Settings, overrides: dict[str, object]) -> Settings:
    return Settings.model_validate({**settings.model_dump(), **overrides})


def apply_appliance_profile(settings: Settings) -> Settings:
    resolved = settings.model_copy(deep=True)
    explicit_fields = set(resolved.model_fields_set)
    relevant_explicit_fields = explicit_fields & set(APPLIANCE_PROFILE_SETTING_FIELDS)

    if not resolved.blink_appliance_mode:
        return resolved

    if "blink_device_preset" not in explicit_fields and (resolved.blink_device_preset or "auto").strip().lower() in {"", "auto", "default"}:
        resolved.blink_device_preset = "internal_macbook"

    if relevant_explicit_fields:
        resolved.blink_appliance_config_source = "explicit_settings"
    else:
        resolved.blink_appliance_config_source = "repo_defaults"

    store = ApplianceProfileStore(resolved.blink_appliance_profile_file)
    profile = store.load()
    if profile is None:
        return resolved

    overrides = {
        field_name: value
        for field_name, value in profile.to_settings_overrides().items()
        if field_name not in explicit_fields and value is not None
    }
    if not overrides:
        if resolved.blink_appliance_config_source == "repo_defaults":
            resolved.blink_appliance_config_source = "appliance_profile"
        return resolved

    updated = _validated_settings_update(resolved, overrides)
    if not relevant_explicit_fields:
        updated.blink_appliance_config_source = "appliance_profile"
    return updated


def default_appliance_profile(settings: Settings) -> ApplianceRuntimeProfile:
    return ApplianceRuntimeProfile(
        device_preset="internal_macbook",
        microphone_device=settings.blink_mic_device or "default",
        camera_device=settings.blink_camera_device or "default",
        speaker_device=settings.blink_speaker_device or "system_default",
        model_profile=settings.blink_model_profile,
        backend_profile=settings.blink_backend_profile,
        voice_profile=settings.blink_voice_profile,
        runtime_mode=settings.blink_runtime_mode.value,
        audio_mode=settings.blink_audio_mode,
        context_mode=settings.blink_context_mode.value,
    )


def configured_device_label(value: str | None, *, default_value: str) -> str:
    resolved = (value or default_value).strip() or default_value
    return resolved


def build_appliance_startup_summary(
    settings: Settings,
    *,
    config_source: str | None = None,
    selected_microphone_label: str | None = None,
    selected_camera_label: str | None = None,
    selected_speaker_label: str | None = None,
    microphone_selection_note: str | None = None,
    camera_selection_note: str | None = None,
    speaker_selection_note: str | None = None,
    microphone_fallback_active: bool = False,
    camera_fallback_active: bool = False,
    speaker_fallback_active: bool = False,
    provider_status: str | None = None,
    provider_detail: str | None = None,
    fallback_state: FallbackState | None = None,
) -> ApplianceStartupSummary:
    configured_microphone = configured_device_label(settings.blink_mic_device, default_value="default")
    configured_camera = configured_device_label(settings.blink_camera_device, default_value="default")
    configured_speaker = configured_device_label(settings.blink_speaker_device, default_value="system_default")
    return ApplianceStartupSummary(
        runtime_mode=settings.blink_runtime_mode,
        model_profile=settings.blink_model_profile,
        backend_profile=settings.blink_backend_profile,
        voice_profile=settings.blink_voice_profile,
        device_preset=settings.blink_device_preset,
        config_source=config_source or settings.blink_appliance_config_source,
        provider_status=provider_status,
        provider_detail=provider_detail,
        fallback_active=bool(fallback_state.active) if fallback_state is not None else False,
        fallback_notes=list(fallback_state.notes) if fallback_state is not None else [],
        microphone=StartupDeviceSelection(
            configured_label=configured_microphone,
            selected_label=selected_microphone_label,
            selection_note=microphone_selection_note,
            fallback_active=microphone_fallback_active,
        ),
        camera=StartupDeviceSelection(
            configured_label=configured_camera,
            selected_label=selected_camera_label,
            selection_note=camera_selection_note,
            fallback_active=camera_fallback_active,
        ),
        speaker=StartupDeviceSelection(
            configured_label=configured_speaker,
            selected_label=selected_speaker_label,
            selection_note=speaker_selection_note,
            fallback_active=speaker_fallback_active,
        ),
    )


def ensure_runtime_layout(settings: Settings) -> list[str]:
    repaired: list[str] = []
    for field_name in APPLIANCE_RUNTIME_DIR_FIELDS:
        path = Path(getattr(settings, field_name))
        directory = path if path.suffix == "" else path.parent
        if not directory.exists():
            repaired.append(str(directory))
        directory.mkdir(parents=True, exist_ok=True)
    return repaired


def reset_runtime_state(settings: Settings) -> list[str]:
    removed: list[str] = []
    for field_name in APPLIANCE_RUNTIME_DIR_FIELDS:
        path = Path(getattr(settings, field_name))
        if path.suffix:
            if path.exists():
                path.unlink()
                removed.append(str(path))
            continue
        if path.exists():
            shutil.rmtree(path)
            removed.append(str(path))
    profile_store = ApplianceProfileStore(settings.blink_appliance_profile_file)
    if profile_store.exists():
        profile_store.clear()
        removed.append(str(profile_store.path))
    auth_runtime_file = Path(settings.operator_auth_runtime_file)
    if auth_runtime_file.exists():
        auth_runtime_file.unlink()
        removed.append(str(auth_runtime_file))
    ensure_runtime_layout(settings)
    return removed


def apply_runtime_profile_to_live_settings(settings: Settings, profile: ApplianceRuntimeProfile) -> None:
    updated = _validated_settings_update(settings, profile.to_settings_overrides())
    updated.blink_appliance_config_source = "appliance_profile"
    for field_name, value in updated.model_dump().items():
        setattr(settings, field_name, value)


__all__ = [
    "APPLIANCE_PROFILE_SETTING_FIELDS",
    "APPLIANCE_RUNTIME_DIR_FIELDS",
    "ApplianceProfileStore",
    "ApplianceRuntimeProfile",
    "apply_appliance_profile",
    "apply_runtime_profile_to_live_settings",
    "build_appliance_startup_summary",
    "configured_device_label",
    "default_appliance_profile",
    "ensure_runtime_layout",
    "reset_runtime_state",
]
