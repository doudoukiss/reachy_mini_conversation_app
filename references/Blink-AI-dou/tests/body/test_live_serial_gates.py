from __future__ import annotations

from embodied_stack.body.serial.live_test_gates import live_serial_motion_tests_enabled, live_serial_tests_enabled


def test_live_serial_gate_defaults_disabled(monkeypatch) -> None:
    monkeypatch.delenv("BLINK_RUN_LIVE_SERIAL_TESTS", raising=False)
    monkeypatch.delenv("BLINK_RUN_LIVE_SERIAL_MOTION_TESTS", raising=False)

    assert live_serial_tests_enabled() is False
    assert live_serial_motion_tests_enabled() is False


def test_live_serial_motion_gate_requires_both_env_flags(monkeypatch) -> None:
    monkeypatch.setenv("BLINK_RUN_LIVE_SERIAL_TESTS", "1")
    monkeypatch.delenv("BLINK_RUN_LIVE_SERIAL_MOTION_TESTS", raising=False)
    assert live_serial_tests_enabled() is True
    assert live_serial_motion_tests_enabled() is False

    monkeypatch.setenv("BLINK_RUN_LIVE_SERIAL_MOTION_TESTS", "true")
    assert live_serial_motion_tests_enabled() is True
