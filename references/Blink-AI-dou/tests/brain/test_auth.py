from __future__ import annotations

import json

from embodied_stack.brain.auth import OperatorAuthManager
from embodied_stack.config import Settings
from embodied_stack.shared.models import utc_now


def test_operator_auth_manager_persists_generated_runtime_token(tmp_path):
    runtime_file = tmp_path / "operator_auth.json"
    settings = Settings(
        operator_auth_enabled=True,
        operator_auth_token=None,
        operator_auth_runtime_file=str(runtime_file),
    )

    first = OperatorAuthManager(settings)
    second = OperatorAuthManager(settings)

    assert first.token
    assert second.token == first.token
    assert first.token_source == "generated_runtime"
    assert second.token_source == "persisted_runtime"


def test_operator_auth_manager_writes_env_token_to_runtime_file(tmp_path):
    runtime_file = tmp_path / "operator_auth.json"
    settings = Settings(
        operator_auth_enabled=True,
        operator_auth_token="fixed-local-token",
        operator_auth_runtime_file=str(runtime_file),
    )

    manager = OperatorAuthManager(settings)
    payload = json.loads(runtime_file.read_text(encoding="utf-8"))

    assert manager.token == "fixed-local-token"
    assert manager.auth_mode == "configured_static_token"
    assert manager.token_source == "env"
    assert payload["operator_auth_token"] == "fixed-local-token"
    assert payload["auth_mode"] == "configured_static_token"
    assert payload["token_source"] == "env"


def test_operator_auth_manager_uses_tokenless_localhost_auth_in_appliance_mode(tmp_path):
    runtime_file = tmp_path / "operator_auth.json"
    settings = Settings(
        operator_auth_enabled=True,
        operator_auth_token=None,
        operator_auth_runtime_file=str(runtime_file),
        blink_appliance_mode=True,
        blink_appliance_profile_file=str(tmp_path / "appliance_profile.json"),
    )

    manager = OperatorAuthManager(settings)
    status = manager.status(authenticated=False)

    assert manager.auth_mode == "appliance_localhost_trusted"
    assert manager.token_source == "appliance_localhost"
    assert manager.token == ""
    assert runtime_file.exists() is False
    assert status.runtime_file is None
    assert status.bootstrap_ttl_seconds is None
    assert status.warning is not None


def test_operator_auth_manager_reports_disabled_dev_mode(tmp_path):
    settings = Settings(
        operator_auth_enabled=False,
        operator_auth_runtime_file=str(tmp_path / "operator_auth.json"),
    )

    manager = OperatorAuthManager(settings)
    status = manager.status(authenticated=False)

    assert status.auth_mode == "disabled_dev"
    assert status.enabled is False


def test_operator_auth_manager_returns_direct_console_url_for_appliance_mode(tmp_path):
    settings = Settings(
        operator_auth_enabled=True,
        operator_auth_token=None,
        operator_auth_runtime_file=str(tmp_path / "operator_auth.json"),
        blink_appliance_mode=True,
        blink_appliance_profile_file=str(tmp_path / "appliance_profile.json"),
    )

    manager = OperatorAuthManager(settings)
    bootstrap_url, expires_at = manager.issue_bootstrap_token(host="127.0.0.1", port=8765)

    assert bootstrap_url == "http://127.0.0.1:8765/console"
    assert expires_at > utc_now()
    assert manager.consume_bootstrap_token("stale-token") is True


def test_operator_auth_manager_leaves_bootstrap_endpoint_public(tmp_path):
    settings = Settings(
        operator_auth_enabled=True,
        operator_auth_token=None,
        operator_auth_runtime_file=str(tmp_path / "operator_auth.json"),
        blink_appliance_mode=True,
        blink_appliance_profile_file=str(tmp_path / "appliance_profile.json"),
    )

    manager = OperatorAuthManager(settings)

    assert manager.requires_auth("/api/appliance/bootstrap") is False
    assert manager.requires_auth("/appliance/bootstrap/token") is False
    assert manager.requires_auth("/api/appliance/status") is False
