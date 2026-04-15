from __future__ import annotations

from embodied_stack.config import Settings
from embodied_stack.shared.models import BodyDriverMode, RobotMode


def test_desktop_first_settings_parse_from_environment(monkeypatch):
    monkeypatch.setenv("BLINK_RUNTIME_MODE", "desktop_serial_body")
    monkeypatch.setenv("BLINK_MODEL_PROFILE", "cloud_demo")
    monkeypatch.setenv("BLINK_BACKEND_PROFILE", "local_fast")
    monkeypatch.setenv("BLINK_VOICE_PROFILE", "desktop_local")
    monkeypatch.setenv("BLINK_TEXT_BACKEND", "ollama_text")
    monkeypatch.setenv("BLINK_EMBEDDING_BACKEND", "hash_embed")
    monkeypatch.setenv("BLINK_CAMERA_SOURCE", "camera:0")
    monkeypatch.setenv("BLINK_BODY_DRIVER", "serial")
    monkeypatch.setenv("BLINK_SERIAL_PORT", "/dev/tty.usbserial-demo")
    monkeypatch.setenv("BLINK_SERVO_BAUD", "1000000")
    monkeypatch.setenv("BLINK_SERVO_AUTOSCAN", "0")
    monkeypatch.setenv("BLINK_SERIAL_TRANSPORT", "fixture_replay")
    monkeypatch.setenv("BLINK_SERIAL_FIXTURE", "fixtures/robot_head_fixture.json")
    monkeypatch.setenv("BLINK_SERIAL_TIMEOUT_SECONDS", "0.35")
    monkeypatch.setenv("BLINK_HEAD_PROFILE", "profiles/robot_head_v1.json")

    settings = Settings(_env_file=None)

    assert settings.blink_runtime_mode == RobotMode.DESKTOP_SERIAL_BODY
    assert settings.blink_model_profile == "cloud_demo"
    assert settings.blink_backend_profile == "local_fast"
    assert settings.blink_voice_profile == "desktop_local"
    assert settings.blink_text_backend == "ollama_text"
    assert settings.blink_embedding_backend == "hash_embed"
    assert settings.blink_camera_source == "camera:0"
    assert settings.blink_body_driver == BodyDriverMode.SERIAL
    assert settings.blink_serial_port == "/dev/tty.usbserial-demo"
    assert settings.blink_servo_baud == 1000000
    assert settings.blink_servo_autoscan is False
    assert settings.blink_serial_transport == "fixture_replay"
    assert settings.blink_serial_fixture == "fixtures/robot_head_fixture.json"
    assert settings.blink_serial_timeout_seconds == 0.35
    assert settings.blink_head_profile == "profiles/robot_head_v1.json"
    assert settings.resolved_body_driver == BodyDriverMode.SERIAL
