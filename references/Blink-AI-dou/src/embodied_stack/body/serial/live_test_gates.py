from __future__ import annotations

import os


def _truthy(name: str) -> bool:
    return str(os.getenv(name, "")).strip().lower() in {"1", "true", "yes", "on"}


def live_serial_tests_enabled() -> bool:
    return _truthy("BLINK_RUN_LIVE_SERIAL_TESTS")


def live_serial_motion_tests_enabled() -> bool:
    return live_serial_tests_enabled() and _truthy("BLINK_RUN_LIVE_SERIAL_MOTION_TESTS")


__all__ = [
    "live_serial_motion_tests_enabled",
    "live_serial_tests_enabled",
]
