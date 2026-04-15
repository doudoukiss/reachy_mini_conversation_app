from __future__ import annotations

import json
import secrets
from datetime import timedelta
from pathlib import Path
from typing import Any

from fastapi import Request, Response

from embodied_stack.config import Settings
from embodied_stack.persistence import load_json_value_or_quarantine, write_json_atomic
from embodied_stack.shared.models import OperatorAuthStatus, utc_now


class OperatorAuthError(PermissionError):
    pass


class OperatorAuthManager:
    cookie_name = "blink_operator_auth"
    header_name = "x-blink-operator-token"
    session_ttl_seconds = 60 * 60 * 12
    bootstrap_ttl_seconds = 120

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.enabled = settings.operator_auth_enabled
        self.runtime_file = Path(settings.operator_auth_runtime_file)
        self.appliance_mode = bool(settings.blink_appliance_mode)
        self.auth_mode = "configured_static_token"
        self._bootstrap_tokens: dict[str, dict[str, Any]] = {}
        if not self.enabled:
            self.token = ""
            self.token_source = "disabled"
            self.auth_mode = "disabled_dev"
            return

        if self.appliance_mode:
            self.token = ""
            self.token_source = "appliance_localhost"
            self.auth_mode = "appliance_localhost_trusted"
        elif settings.operator_auth_token:
            self.token = settings.operator_auth_token
            self.token_source = "env"
            self.auth_mode = "configured_static_token"
            self._write_runtime_file()
        else:
            persisted = self._load_runtime_token()
            if persisted:
                self.token = persisted
                self.token_source = "persisted_runtime"
            else:
                self.token = secrets.token_urlsafe(24)
                self.token_source = "generated_runtime"
            self.auth_mode = "configured_static_token"
            self._write_runtime_file()

    def requires_auth(self, path: str) -> bool:
        if not self.enabled:
            return False
        if self.appliance_mode:
            return False
        if path.startswith("/api/operator/auth"):
            return False
        if path.startswith("/api/appliance/bootstrap"):
            return False
        if path.startswith("/appliance/bootstrap/"):
            return False
        if path in {"/console", "/setup", "/companion-test"}:
            return True
        if path.startswith("/api/operator"):
            return True
        if path.startswith("/api/appliance"):
            return True
        if path in {"/api/reset", "/api/world-state", "/api/memory"}:
            return True
        if path.startswith("/api/shift"):
            return True
        if path.startswith("/api/sessions"):
            return True
        if path.startswith("/api/scenarios"):
            return True
        if path.startswith("/api/demo-runs"):
            return True
        if path.startswith("/api/logs"):
            return True
        if path.startswith("/api/traces"):
            return True
        return False

    def is_authenticated(self, request: Request) -> bool:
        if not self.enabled:
            return True
        if self.appliance_mode:
            return True
        candidate = request.cookies.get(self.cookie_name) or request.headers.get(self.header_name)
        return bool(candidate) and secrets.compare_digest(candidate, self.token)

    def ensure_authenticated(self, request: Request) -> None:
        if not self.is_authenticated(request):
            raise OperatorAuthError("operator_auth_required")

    def set_login_cookie(self, response: Response) -> None:
        if not self.enabled or self.appliance_mode:
            return
        response.set_cookie(
            key=self.cookie_name,
            value=self.token,
            httponly=True,
            samesite="lax",
            secure=False,
            path="/",
            max_age=self.session_ttl_seconds,
        )

    def clear_login_cookie(self, response: Response) -> None:
        if self.appliance_mode:
            return
        response.delete_cookie(self.cookie_name, path="/")

    def status(self, *, authenticated: bool) -> OperatorAuthStatus:
        warning = None
        runtime_file = None if self.appliance_mode else (str(self.runtime_file) if self.runtime_file.exists() else None)
        if self.enabled and self.token_source in {"generated_runtime", "persisted_runtime"}:
            warning = "Local runtime token is stored in the runtime auth file. Do not share or commit it."
        elif self.enabled and self.auth_mode == "appliance_localhost_trusted":
            warning = "Blink appliance mode trusts the local browser on localhost and does not require operator token entry."
        return OperatorAuthStatus(
            enabled=self.enabled,
            authenticated=authenticated,
            cookie_name=self.cookie_name,
            header_name=self.header_name,
            auth_mode=self.auth_mode,
            token_source=self.token_source,
            runtime_file=runtime_file,
            session_ttl_seconds=self.session_ttl_seconds if self.enabled and not self.appliance_mode else None,
            bootstrap_ttl_seconds=self.bootstrap_ttl_seconds if self.enabled and not self.appliance_mode else None,
            warning=warning,
        )

    def issue_bootstrap_token(self, *, host: str, port: int) -> tuple[str, object]:
        if self.appliance_mode:
            expires_at = utc_now().replace(microsecond=0) + timedelta(seconds=self.bootstrap_ttl_seconds)
            return f"http://{host}:{port}/console", expires_at
        token = secrets.token_urlsafe(18)
        expires_at = utc_now().replace(microsecond=0) + timedelta(seconds=self.bootstrap_ttl_seconds)
        self._bootstrap_tokens[token] = {
            "expires_at": expires_at,
            "host": host,
            "port": port,
        }
        return f"http://{host}:{port}/appliance/bootstrap/{token}", expires_at

    def consume_bootstrap_token(self, token: str) -> bool:
        if self.appliance_mode:
            return True
        payload = self._bootstrap_tokens.pop(token, None)
        if payload is None:
            return False
        expires_at = payload.get("expires_at")
        if expires_at is None or expires_at < utc_now():
            return False
        return True

    def _load_runtime_token(self) -> str | None:
        if not self.runtime_file.exists():
            return None
        payload = load_json_value_or_quarantine(self.runtime_file, quarantine_invalid=True)
        if not isinstance(payload, dict):
            return None
        token = payload.get("operator_auth_token")
        if not isinstance(token, str):
            return None
        token = token.strip()
        return token or None

    def _write_runtime_file(self) -> None:
        self.runtime_file.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "created_at": utc_now().isoformat(),
            "auth_mode": self.auth_mode,
            "token_source": self.token_source,
            "operator_auth_token": self.token,
            "warning": "Local operator auth state only. Do not commit this file or share live tokens.",
        }
        write_json_atomic(self.runtime_file, payload, keep_backups=3)
