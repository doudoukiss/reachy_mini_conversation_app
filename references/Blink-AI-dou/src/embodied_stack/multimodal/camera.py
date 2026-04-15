from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from embodied_stack.config import Settings


def default_camera_source(settings: Settings) -> str:
    return settings.blink_camera_source


@dataclass(frozen=True)
class DesktopCameraSource:
    configured_source: str
    mode: str
    available: bool
    fixture_path: str | None = None
    note: str | None = None


def describe_camera_source(settings: Settings) -> DesktopCameraSource:
    configured = settings.blink_camera_source.strip() or "default"
    lowered = configured.lower()

    if lowered in {"none", "disabled", "off", "unavailable"}:
        return DesktopCameraSource(
            configured_source=configured,
            mode="disabled",
            available=False,
            note="Camera input is explicitly disabled. Fixture replay and manual scene notes remain available.",
        )

    if lowered.startswith("fixture:"):
        fixture_path = configured.split(":", 1)[1]
        exists = Path(fixture_path).exists()
        return DesktopCameraSource(
            configured_source=configured,
            mode="fixture_replay",
            available=exists,
            fixture_path=fixture_path,
            note="Camera source is mapped to a local perception fixture." if exists else "Configured fixture path does not exist.",
        )

    if lowered.startswith("browser"):
        return DesktopCameraSource(
            configured_source=configured,
            mode="browser_snapshot",
            available=True,
            note="Webcam capture is expected to arrive from the browser console snapshot flow.",
        )

    if lowered == "default" or lowered.startswith("camera:"):
        return DesktopCameraSource(
            configured_source=configured,
            mode="webcam",
            available=True,
            note="Webcam capture is the preferred local visual input, with fixture replay and manual notes as honest fallback paths.",
        )

    return DesktopCameraSource(
        configured_source=configured,
        mode="unknown",
        available=False,
        note="Camera source is not recognized. Perception should fall back to fixture replay, browser snapshots, or manual annotations.",
    )


__all__ = ["DesktopCameraSource", "default_camera_source", "describe_camera_source"]
