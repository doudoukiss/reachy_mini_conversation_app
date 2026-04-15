from __future__ import annotations

import base64
import ipaddress
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

from pydantic import BaseModel, Field

from embodied_stack.action_plane.connectors.base import (
    BaseConnector,
    ConnectorActionError,
    ConnectorExecutionResult,
    ConnectorPreviewResult,
    artifact_for_path,
)
from embodied_stack.config import Settings
from embodied_stack.persistence import load_json_model_or_quarantine, write_json_atomic
from embodied_stack.shared.contracts.action import (
    ActionArtifactRecord,
    ActionRequestRecord,
    ActionRiskClass,
    BrowserActionPreviewRecord,
    BrowserActionResultRecord,
    BrowserRequestedAction,
    BrowserRuntimeStatusRecord,
    BrowserSessionStatusRecord,
    BrowserSnapshotRecord,
    BrowserTargetCandidateRecord,
    BrowserTargetHintRecord,
    ConnectorDescriptorRecord,
    ConnectorHealthRecord,
)
from embodied_stack.shared.contracts._common import utc_now

_STUB_PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9oN0S0YAAAAASUVORK5CYII="
)
_UNSAFE_SCHEMES = {"file", "chrome", "about"}
_TARGET_ACTIONS = {
    BrowserRequestedAction.FIND_CLICK_TARGETS,
    BrowserRequestedAction.CLICK_TARGET,
    BrowserRequestedAction.TYPE_TEXT,
    BrowserRequestedAction.SUBMIT_FORM,
}
_WRITE_ACTIONS = {
    BrowserRequestedAction.CLICK_TARGET,
    BrowserRequestedAction.TYPE_TEXT,
    BrowserRequestedAction.SUBMIT_FORM,
}
_INPUT_ACTIONS = {
    BrowserRequestedAction.TYPE_TEXT,
    BrowserRequestedAction.SUBMIT_FORM,
}
_BROWSER_ACTION_RISK = {
    BrowserRequestedAction.OPEN_URL.value: ActionRiskClass.READ_ONLY,
    BrowserRequestedAction.CAPTURE_SNAPSHOT.value: ActionRiskClass.READ_ONLY,
    BrowserRequestedAction.EXTRACT_VISIBLE_TEXT.value: ActionRiskClass.READ_ONLY,
    BrowserRequestedAction.SUMMARIZE_PAGE.value: ActionRiskClass.READ_ONLY,
    BrowserRequestedAction.FIND_CLICK_TARGETS.value: ActionRiskClass.READ_ONLY,
    BrowserRequestedAction.CLICK_TARGET.value: ActionRiskClass.OPERATOR_SENSITIVE_WRITE,
    BrowserRequestedAction.TYPE_TEXT.value: ActionRiskClass.OPERATOR_SENSITIVE_WRITE,
    BrowserRequestedAction.SUBMIT_FORM.value: ActionRiskClass.OPERATOR_SENSITIVE_WRITE,
}


class _PersistedBrowserSession(BaseModel):
    blink_session_id: str
    browser_session_id: str
    backend_mode: str
    current_url: str | None = None
    page_title: str | None = None
    visible_text: str | None = None
    summary: str | None = None
    candidate_targets: list[BrowserTargetCandidateRecord] = Field(default_factory=list)
    last_action_id: str | None = None
    last_requested_action: BrowserRequestedAction | None = None
    last_screenshot_path: str | None = None
    last_snapshot_path: str | None = None
    last_page_text_path: str | None = None
    updated_at: Any = Field(default_factory=utc_now)


@dataclass
class _ResolvedTarget:
    candidate: BrowserTargetCandidateRecord
    selector_kind: str
    selector_value: str


class _StubPageState(BaseModel):
    current_url: str
    page_title: str
    visible_text: str
    summary: str
    candidate_targets: list[BrowserTargetCandidateRecord] = Field(default_factory=list)
    typed_text: str | None = None


def _normalize_browser_action(value: Any) -> BrowserRequestedAction:
    if isinstance(value, BrowserRequestedAction):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return BrowserRequestedAction(value.strip())
        except ValueError as exc:
            raise ConnectorActionError("unsupported_browser_action", f"unsupported_browser_action:{value}") from exc
    raise ConnectorActionError("browser_action_required", "browser_action_required")


def _normalize_target_hint(value: Any) -> BrowserTargetHintRecord | None:
    if value is None:
        return None
    if isinstance(value, BrowserTargetHintRecord):
        return value
    if isinstance(value, dict):
        return BrowserTargetHintRecord.model_validate(value)
    raise ConnectorActionError("invalid_browser_target_hint", "invalid_browser_target_hint")


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    return slug or "browser"


def _display_label(candidate: BrowserTargetCandidateRecord) -> str:
    return (
        candidate.label
        or candidate.text
        or candidate.placeholder
        or candidate.field_name
        or candidate.selector
        or candidate.target_id
    )


def _browser_session_id(blink_session_id: str) -> str:
    return f"browser-{_slugify(blink_session_id)}"


def _screenshot_data_url(path: str | None) -> str | None:
    if not path:
        return None
    candidate = Path(path)
    if not candidate.exists():
        return None
    return f"data:image/png;base64,{base64.b64encode(candidate.read_bytes()).decode('ascii')}"


def _text_summary(visible_text: str | None, *, fallback: str) -> str:
    text = (visible_text or "").strip()
    if not text:
        return fallback
    clipped = text[:240].strip()
    return clipped if len(text) <= 240 else f"{clipped}..."


def _safe_host(hostname: str | None, allowlist: set[str]) -> bool:
    if not hostname:
        return False
    host = hostname.strip().lower().rstrip(".")
    if host in allowlist:
        return True
    if host in {"localhost", "127.0.0.1", "::1"}:
        return False
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        if host.endswith(".local"):
            return False
        return True
    return not (ip.is_loopback or ip.is_private or ip.is_link_local or ip.is_reserved or ip.is_multicast)


def build_browser_connector_descriptor(settings: Settings | None = None) -> ConnectorDescriptorRecord:
    settings = settings or Settings()
    backend = settings.action_plane_browser_backend_mode
    supported = False
    configured = backend != "disabled"
    notes: list[str] = []
    if backend == "disabled":
        notes.append("browser_backend_disabled")
    elif backend == "stub":
        supported = True
        notes.append("deterministic_stub_backend")
    elif backend == "playwright":
        try:
            import playwright.sync_api  # noqa: F401

            supported = True
        except Exception:
            notes.append("playwright_python_package_missing")
    else:
        notes.append("unknown_browser_backend")
    return ConnectorDescriptorRecord(
        connector_id="browser_runtime",
        label="Browser Runtime",
        category="browser",
        transport_kind="local_runtime",
        supported=supported,
        configured=configured,
        capability_tags=["browser", backend],
        supported_actions=[item.value for item in BrowserRequestedAction],
        action_risk=dict(_BROWSER_ACTION_RISK),
        dry_run_supported=backend == "stub",
        dry_run_only=backend in {"disabled", "stub"},
        notes=notes,
    )


class BrowserRuntimeConnector(BaseConnector):
    def __init__(self, descriptor: ConnectorDescriptorRecord, *, settings: Settings) -> None:
        super().__init__(descriptor)
        self._settings = settings
        self._backend_mode = settings.action_plane_browser_backend_mode
        self._storage_dir = Path(settings.blink_action_plane_browser_storage_dir)
        self._sessions_dir = self._storage_dir / "sessions"
        self._sessions_dir.mkdir(parents=True, exist_ok=True)
        self._allowlist = set(settings.action_plane_browser_allowed_hosts_list)
        self._launch_error_detail: str | None = None
        self._playwright_runtime: dict[str, tuple[Any, Any, Any, Any]] = {}
        self._stub_pages: dict[str, _StubPageState] = {}

    def health(self) -> ConnectorHealthRecord:
        if self._backend_mode == "disabled":
            return ConnectorHealthRecord(
                connector_id=self.descriptor.connector_id,
                supported=False,
                configured=False,
                status="unsupported",
                detail="browser_backend_disabled",
            )
        if self._backend_mode == "stub":
            return ConnectorHealthRecord(
                connector_id=self.descriptor.connector_id,
                supported=True,
                configured=True,
                status="healthy",
                detail="browser_stub_ready",
            )
        if self._backend_mode != "playwright":
            return ConnectorHealthRecord(
                connector_id=self.descriptor.connector_id,
                supported=False,
                configured=False,
                status="unsupported",
                detail="unknown_browser_backend",
            )
        try:
            import playwright.sync_api  # noqa: F401
        except Exception:
            return ConnectorHealthRecord(
                connector_id=self.descriptor.connector_id,
                supported=False,
                configured=True,
                status="unsupported",
                detail="playwright_python_package_missing",
            )
        if self._launch_error_detail:
            return ConnectorHealthRecord(
                connector_id=self.descriptor.connector_id,
                supported=False,
                configured=True,
                status="unsupported",
                detail=self._launch_error_detail,
            )
        return ConnectorHealthRecord(
            connector_id=self.descriptor.connector_id,
            supported=True,
            configured=True,
            status="healthy",
            detail="playwright_ready",
        )

    def status(self, *, session_id: str | None = None) -> BrowserRuntimeStatusRecord:
        active = self._load_session(session_id) if session_id else self._latest_session()
        snapshot: BrowserSnapshotRecord | None = None
        if active is not None:
            snapshot = BrowserSnapshotRecord(
                current_url=active.current_url,
                page_title=active.page_title,
                visible_text=active.visible_text,
                summary=active.summary,
                screenshot_path=active.last_screenshot_path,
                screenshot_data_url=_screenshot_data_url(active.last_screenshot_path),
                snapshot_path=active.last_snapshot_path,
                page_text_path=active.last_page_text_path,
                captured_at=active.updated_at,
            )
        return BrowserRuntimeStatusRecord(
            backend_mode=self._backend_mode,
            supported=self.health().supported,
            configured=self.health().configured,
            headless=self._settings.blink_action_plane_browser_headless,
            active_session=self._session_status(active),
            latest_snapshot=snapshot,
        )

    def preview(
        self,
        *,
        action_name: str,
        request: ActionRequestRecord,
        runtime_context: Any,
        reason: str,
    ) -> ConnectorPreviewResult:
        action = _normalize_browser_action(action_name)
        blink_session_id = self._blink_session_id(runtime_context, request)
        if reason in {"connector_unsupported", "connector_unconfigured"}:
            return ConnectorPreviewResult(
                summary=reason,
                detail=reason,
                output_payload=self._unsupported_output(
                    request=request,
                    requested_action=action,
                    detail=reason,
                ),
            )
        preview = self._build_preview(
            action=action,
            request=request,
            blink_session_id=blink_session_id,
            reason=reason,
        )
        output = self._output_payload(
            request=request,
            session_id=blink_session_id,
            action=action,
            status="approval_required" if reason == "approval_required" else reason,
            detail=preview.detail,
            snapshot=self._snapshot_for_session(blink_session_id),
            preview=preview,
            result=None,
            preview_required=action in _WRITE_ACTIONS,
        )
        return ConnectorPreviewResult(
            summary=reason,
            detail=preview.detail,
            output_payload=output,
            artifacts=self._preview_artifacts(preview),
        )

    def execute(
        self,
        *,
        action_name: str,
        request: ActionRequestRecord,
        runtime_context: Any,
    ) -> ConnectorExecutionResult:
        action = _normalize_browser_action(action_name)
        blink_session_id = self._blink_session_id(runtime_context, request)
        target_url = self._resolved_target_url(request)
        if target_url is not None:
            self._assert_safe_url(target_url)
        if action in _INPUT_ACTIONS:
            self._assert_safe_text_input(request.input_payload.get("text_input"))

        if self._backend_mode == "disabled":
            return ConnectorExecutionResult(
                summary="unsupported",
                detail="browser_backend_disabled",
                output_payload=self._unsupported_output(
                    request=request,
                    requested_action=action,
                    detail="browser_backend_disabled",
                ),
            )
        if self._backend_mode == "stub":
            result = self._execute_stub(action=action, request=request, blink_session_id=blink_session_id, target_url=target_url)
        elif self._backend_mode == "playwright":
            result = self._execute_playwright(action=action, request=request, blink_session_id=blink_session_id, target_url=target_url)
        else:
            raise ConnectorActionError("unknown_browser_backend", "unknown_browser_backend")

        self._persist_session(result["session"])
        action_result = result["result"]
        output = self._output_payload(
            request=request,
            session_id=blink_session_id,
            action=action,
            status=action_result.status,
            detail=action_result.summary or action_result.status,
            snapshot=result["snapshot"],
            preview=None,
            result=action_result,
            preview_required=False,
        )
        return ConnectorExecutionResult(
            summary=action_result.status,
            detail=action_result.summary or action_result.status,
            output_payload=output,
            artifacts=result["artifacts"],
        )

    def _output_payload(
        self,
        *,
        request: ActionRequestRecord,
        session_id: str,
        action: BrowserRequestedAction,
        status: str,
        detail: str | None,
        snapshot: BrowserSnapshotRecord | None,
        preview: BrowserActionPreviewRecord | None,
        result: BrowserActionResultRecord | None,
        preview_required: bool,
    ) -> dict[str, Any]:
        artifacts: list[ActionArtifactRecord] = []
        if snapshot is not None:
            if snapshot.snapshot_path:
                artifacts.append(ActionArtifactRecord(kind="browser_snapshot", label="snapshot.json", path=snapshot.snapshot_path))
            if snapshot.page_text_path:
                artifacts.append(ActionArtifactRecord(kind="browser_visible_text", label="page_text.txt", path=snapshot.page_text_path))
            if snapshot.screenshot_path:
                artifacts.append(ActionArtifactRecord(kind="browser_screenshot", label="screenshot.png", path=snapshot.screenshot_path))
        if preview is not None and preview.preview_path:
            artifacts.append(ActionArtifactRecord(kind="browser_preview", label="preview.json", path=preview.preview_path))
        if result is not None and result.result_path:
            artifacts.append(ActionArtifactRecord(kind="browser_result", label="result.json", path=result.result_path))
        candidate_targets = []
        if result is not None and result.candidate_targets:
            candidate_targets = result.candidate_targets
        elif preview is not None and preview.candidate_targets:
            candidate_targets = preview.candidate_targets
        return {
            "task": str(request.input_payload.get("query") or request.input_payload.get("target_url") or action.value),
            "requested_action": action,
            "supported": self.health().supported,
            "configured": self.health().configured,
            "status": status,
            "detail": detail,
            "browser_session_id": _browser_session_id(session_id),
            "current_url": (result.current_url if result is not None else None) or (preview.current_url if preview is not None else None) or (snapshot.current_url if snapshot is not None else None),
            "page_title": (result.page_title if result is not None else None) or (preview.page_title if preview is not None else None) or (snapshot.page_title if snapshot is not None else None),
            "summary": (result.summary if result is not None else None) or (preview.summary if preview is not None else None) or (snapshot.summary if snapshot is not None else None),
            "visible_text": (result.visible_text if result is not None else None) or (preview.visible_text if preview is not None else None) or (snapshot.visible_text if snapshot is not None else None),
            "candidate_targets": [item.model_dump(mode="json") for item in candidate_targets],
            "preview_required": preview_required,
            "snapshot": snapshot.model_dump(mode="json") if snapshot is not None else None,
            "preview": preview.model_dump(mode="json") if preview is not None else None,
            "result": result.model_dump(mode="json") if result is not None else None,
            "artifacts": [item.model_dump(mode="json") for item in artifacts],
        }

    def _unsupported_output(
        self,
        *,
        request: ActionRequestRecord,
        requested_action: BrowserRequestedAction,
        detail: str,
    ) -> dict[str, Any]:
        health = self.health()
        return {
            "task": str(request.input_payload.get("query") or request.input_payload.get("target_url") or ""),
            "requested_action": requested_action,
            "supported": health.supported,
            "configured": health.configured,
            "status": "unsupported" if not health.supported else "unconfigured",
            "detail": detail,
            "browser_session_id": None,
            "current_url": None,
            "page_title": None,
            "summary": None,
            "visible_text": None,
            "candidate_targets": [],
            "preview_required": False,
            "snapshot": None,
            "preview": None,
            "result": None,
            "artifacts": [],
        }

    def _build_preview(
        self,
        *,
        action: BrowserRequestedAction,
        request: ActionRequestRecord,
        blink_session_id: str,
        reason: str,
    ) -> BrowserActionPreviewRecord:
        target_url = self._resolved_target_url(request)
        persisted = self._load_or_seed_session(blink_session_id, target_url=target_url)
        playwright_page = None
        if self._backend_mode == "playwright":
            try:
                playwright_page = self._playwright_page(blink_session_id)
                if target_url:
                    playwright_page.goto(target_url, wait_until="domcontentloaded")
                persisted.current_url = playwright_page.url
                persisted.page_title = playwright_page.title()
                persisted.visible_text = self._playwright_visible_text(playwright_page)
                persisted.summary = _text_summary(
                    persisted.visible_text,
                    fallback="No visible text on the current page.",
                )
                persisted.candidate_targets = self._playwright_candidates(playwright_page)
            except ConnectorActionError:
                raise
            except Exception as exc:
                raise ConnectorActionError("browser_preview_unavailable", "browser_preview_unavailable") from exc
        self._persist_session(persisted)
        self._assert_effect_action_safe(action=action, persisted=persisted)
        target_hint = _normalize_target_hint(request.input_payload.get("target_hint"))
        resolved_target = self._resolve_target(blink_session_id=blink_session_id, target_hint=target_hint, allow_missing=action not in _TARGET_ACTIONS)
        snapshot = self._materialize_snapshot(
            blink_session_id=blink_session_id,
            persisted=persisted,
            action_id=request.action_id,
            playwright_page=playwright_page,
        )
        preview_path = self._action_dir(request.action_id) / "preview.json"
        preview = BrowserActionPreviewRecord(
            action_id=request.action_id,
            requested_action=action,
            current_url=snapshot.current_url,
            page_title=snapshot.page_title,
            summary=snapshot.summary,
            visible_text=snapshot.visible_text,
            screenshot_path=snapshot.screenshot_path,
            screenshot_data_url=_screenshot_data_url(snapshot.screenshot_path),
            target_hint=target_hint,
            resolved_target=(resolved_target.candidate if resolved_target is not None else None),
            candidate_targets=self._candidate_targets(blink_session_id),
            text_input=str(request.input_payload.get("text_input")) if request.input_payload.get("text_input") is not None else None,
            preview_path=str(preview_path),
            detail=reason,
        )
        write_json_atomic(preview_path, preview, keep_backups=1)
        return preview

    def _preview_artifacts(self, preview: BrowserActionPreviewRecord) -> list[ActionArtifactRecord]:
        artifacts: list[ActionArtifactRecord] = []
        if preview.screenshot_path:
            artifacts.append(ActionArtifactRecord(kind="browser_screenshot", label="screenshot.png", path=preview.screenshot_path))
        if preview.preview_path:
            artifacts.append(ActionArtifactRecord(kind="browser_preview", label="preview.json", path=preview.preview_path))
        return artifacts

    def _execute_stub(
        self,
        *,
        action: BrowserRequestedAction,
        request: ActionRequestRecord,
        blink_session_id: str,
        target_url: str | None,
    ) -> dict[str, Any]:
        persisted = self._load_or_seed_session(blink_session_id, target_url=target_url)
        page = self._stub_pages.setdefault(blink_session_id, self._default_stub_page(target_url or persisted.current_url or "https://example.com/"))
        if action == BrowserRequestedAction.OPEN_URL and target_url:
            page = self._default_stub_page(target_url)
        elif action == BrowserRequestedAction.CLICK_TARGET:
            resolved = self._resolve_target(blink_session_id=blink_session_id, target_hint=_normalize_target_hint(request.input_payload.get("target_hint")), allow_missing=False)
            if resolved is None:
                raise ConnectorActionError("browser_target_not_found", "browser_target_not_found")
            page.summary = f"Clicked {_display_label(resolved.candidate)}."
            if "continue" in _display_label(resolved.candidate).lower():
                page.current_url = f"{page.current_url.rstrip('/')}/continued"
                page.page_title = f"{page.page_title} Continued"
        elif action == BrowserRequestedAction.TYPE_TEXT:
            resolved = self._resolve_target(blink_session_id=blink_session_id, target_hint=_normalize_target_hint(request.input_payload.get("target_hint")), allow_missing=False)
            if resolved is None:
                raise ConnectorActionError("browser_target_not_found", "browser_target_not_found")
            page.typed_text = str(request.input_payload.get("text_input") or "")
            page.summary = f"Typed text into {_display_label(resolved.candidate)}."
            page.visible_text = f"{page.visible_text}\nTyped: {page.typed_text}".strip()
        elif action == BrowserRequestedAction.SUBMIT_FORM:
            resolved = self._resolve_target(blink_session_id=blink_session_id, target_hint=_normalize_target_hint(request.input_payload.get("target_hint")), allow_missing=False)
            if resolved is None:
                raise ConnectorActionError("browser_target_not_found", "browser_target_not_found")
            page.summary = f"Submitted form via {_display_label(resolved.candidate)}."
            page.visible_text = f"{page.visible_text}\nSubmission recorded.".strip()
        elif action == BrowserRequestedAction.FIND_CLICK_TARGETS:
            page.summary = "Resolved clickable targets on the current page."
        elif action == BrowserRequestedAction.EXTRACT_VISIBLE_TEXT:
            page.summary = _text_summary(page.visible_text, fallback="No visible text on the current page.")
        elif action == BrowserRequestedAction.SUMMARIZE_PAGE:
            page.summary = _text_summary(page.visible_text, fallback="No current page loaded.")
        page.candidate_targets = self._stub_candidates(page.current_url)
        self._stub_pages[blink_session_id] = page
        persisted.current_url = page.current_url
        persisted.page_title = page.page_title
        persisted.visible_text = page.visible_text
        persisted.summary = page.summary
        persisted.candidate_targets = page.candidate_targets
        persisted.last_action_id = request.action_id
        persisted.last_requested_action = action
        snapshot = self._materialize_snapshot(blink_session_id=blink_session_id, persisted=persisted, action_id=request.action_id)
        result_path = self._action_dir(request.action_id) / "result.json"
        resolved_target = None
        if action in _TARGET_ACTIONS:
            resolved = self._resolve_target(
                blink_session_id=blink_session_id,
                target_hint=_normalize_target_hint(request.input_payload.get("target_hint")),
                allow_missing=action == BrowserRequestedAction.FIND_CLICK_TARGETS,
            )
            resolved_target = resolved.candidate if resolved is not None else None
        result = BrowserActionResultRecord(
            action_id=request.action_id,
            requested_action=action,
            status="ok",
            current_url=snapshot.current_url,
            page_title=snapshot.page_title,
            summary=snapshot.summary,
            visible_text=snapshot.visible_text,
            screenshot_path=snapshot.screenshot_path,
            screenshot_data_url=_screenshot_data_url(snapshot.screenshot_path),
            snapshot_path=snapshot.snapshot_path,
            page_text_path=snapshot.page_text_path,
            result_path=str(result_path),
            resolved_target=resolved_target,
            candidate_targets=page.candidate_targets,
            text_input=str(request.input_payload.get("text_input")) if request.input_payload.get("text_input") is not None else None,
        )
        write_json_atomic(result_path, result, keep_backups=1)
        persisted.last_screenshot_path = snapshot.screenshot_path
        persisted.last_snapshot_path = snapshot.snapshot_path
        persisted.last_page_text_path = snapshot.page_text_path
        return {
            "session": persisted,
            "snapshot": snapshot,
            "result": result,
            "artifacts": self._execution_artifacts(snapshot=snapshot, result=result),
        }

    def _execute_playwright(
        self,
        *,
        action: BrowserRequestedAction,
        request: ActionRequestRecord,
        blink_session_id: str,
        target_url: str | None,
    ) -> dict[str, Any]:
        persisted = self._load_or_seed_session(blink_session_id, target_url=target_url)
        page = self._playwright_page(blink_session_id)
        if action == BrowserRequestedAction.OPEN_URL:
            if not target_url:
                raise ConnectorActionError("browser_target_url_required", "browser_target_url_required")
            page.goto(target_url, wait_until="domcontentloaded")
        elif target_url and not persisted.current_url:
            page.goto(target_url, wait_until="domcontentloaded")
        if action == BrowserRequestedAction.CLICK_TARGET:
            resolved = self._resolve_playwright_target(page=page, target_hint=_normalize_target_hint(request.input_payload.get("target_hint")), require_editable=False)
            locator = self._locator_for_candidate(page, resolved)
            locator.click()
        elif action == BrowserRequestedAction.TYPE_TEXT:
            resolved = self._resolve_playwright_target(page=page, target_hint=_normalize_target_hint(request.input_payload.get("target_hint")), require_editable=True)
            if resolved.candidate.input_type in {"password", "file"}:
                raise ConnectorActionError("unsafe_browser_target", "unsafe_browser_target")
            locator = self._locator_for_candidate(page, resolved)
            locator.fill(str(request.input_payload.get("text_input") or ""))
        elif action == BrowserRequestedAction.SUBMIT_FORM:
            resolved = self._resolve_playwright_target(page=page, target_hint=_normalize_target_hint(request.input_payload.get("target_hint")), require_editable=False)
            locator = self._locator_for_candidate(page, resolved)
            locator.click()
        page.wait_for_load_state("domcontentloaded")
        candidates = self._playwright_candidates(page)
        visible_text = self._playwright_visible_text(page)
        summary = _text_summary(visible_text, fallback="No visible text on the current page.")
        persisted.current_url = page.url
        persisted.page_title = page.title()
        persisted.visible_text = visible_text
        persisted.summary = summary
        persisted.candidate_targets = candidates
        persisted.last_action_id = request.action_id
        persisted.last_requested_action = action
        snapshot = self._materialize_snapshot(blink_session_id=blink_session_id, persisted=persisted, action_id=request.action_id, playwright_page=page)
        resolved_target = None
        if action in _TARGET_ACTIONS:
            resolved = self._resolve_playwright_target(
                page=page,
                target_hint=_normalize_target_hint(request.input_payload.get("target_hint")),
                require_editable=action == BrowserRequestedAction.TYPE_TEXT,
                allow_missing=action == BrowserRequestedAction.FIND_CLICK_TARGETS,
            )
            resolved_target = resolved.candidate if resolved is not None else None
        result_path = self._action_dir(request.action_id) / "result.json"
        result = BrowserActionResultRecord(
            action_id=request.action_id,
            requested_action=action,
            status="ok",
            current_url=snapshot.current_url,
            page_title=snapshot.page_title,
            summary=snapshot.summary,
            visible_text=snapshot.visible_text,
            screenshot_path=snapshot.screenshot_path,
            screenshot_data_url=_screenshot_data_url(snapshot.screenshot_path),
            snapshot_path=snapshot.snapshot_path,
            page_text_path=snapshot.page_text_path,
            result_path=str(result_path),
            resolved_target=resolved_target,
            candidate_targets=candidates,
            text_input=str(request.input_payload.get("text_input")) if request.input_payload.get("text_input") is not None else None,
        )
        write_json_atomic(result_path, result, keep_backups=1)
        persisted.last_screenshot_path = snapshot.screenshot_path
        persisted.last_snapshot_path = snapshot.snapshot_path
        persisted.last_page_text_path = snapshot.page_text_path
        return {
            "session": persisted,
            "snapshot": snapshot,
            "result": result,
            "artifacts": self._execution_artifacts(snapshot=snapshot, result=result),
        }

    def _execution_artifacts(self, *, snapshot: BrowserSnapshotRecord, result: BrowserActionResultRecord) -> list[ActionArtifactRecord]:
        artifacts: list[ActionArtifactRecord] = []
        if snapshot.snapshot_path:
            artifacts.append(artifact_for_path(kind="browser_snapshot", label="snapshot.json", path=Path(snapshot.snapshot_path)))
        if snapshot.page_text_path:
            artifacts.append(artifact_for_path(kind="browser_visible_text", label="page_text.txt", path=Path(snapshot.page_text_path)))
        if snapshot.screenshot_path:
            artifacts.append(artifact_for_path(kind="browser_screenshot", label="screenshot.png", path=Path(snapshot.screenshot_path)))
        if result.result_path:
            artifacts.append(artifact_for_path(kind="browser_result", label="result.json", path=Path(result.result_path)))
        return artifacts

    def _blink_session_id(self, runtime_context: Any, request: ActionRequestRecord) -> str:
        session = getattr(runtime_context, "session", None)
        if session is not None and getattr(session, "session_id", None):
            return str(session.session_id)
        if request.session_id:
            return request.session_id
        return "console-live"

    def _resolved_target_url(self, request: ActionRequestRecord) -> str | None:
        target_url = request.input_payload.get("target_url")
        if target_url:
            return str(target_url).strip()
        query = str(request.input_payload.get("query") or "").strip()
        if query.startswith("http://") or query.startswith("https://"):
            return query
        return None

    def _assert_safe_url(self, raw_url: str) -> None:
        parsed = urlparse(raw_url)
        if parsed.scheme.lower() in _UNSAFE_SCHEMES:
            raise ConnectorActionError("unsafe_browser_url", "unsafe_browser_url")
        if parsed.scheme.lower() not in {"http", "https"}:
            raise ConnectorActionError("unsupported_browser_url_scheme", "unsupported_browser_url_scheme")
        if not _safe_host(parsed.hostname, self._allowlist):
            raise ConnectorActionError("unsafe_browser_host", "unsafe_browser_host")

    def _assert_safe_text_input(self, value: Any) -> None:
        if value is None:
            raise ConnectorActionError("browser_text_input_required", "browser_text_input_required")
        if not str(value).strip():
            raise ConnectorActionError("browser_text_input_required", "browser_text_input_required")

    def _assert_effect_action_safe(self, *, action: BrowserRequestedAction, persisted: _PersistedBrowserSession) -> None:
        if action not in _WRITE_ACTIONS:
            return
        if not persisted.current_url:
            raise ConnectorActionError("browser_no_page_loaded", "browser_no_page_loaded")
        self._assert_safe_url(persisted.current_url)

    def _session_status(self, persisted: _PersistedBrowserSession | None) -> BrowserSessionStatusRecord | None:
        if persisted is None:
            return None
        return BrowserSessionStatusRecord(
            blink_session_id=persisted.blink_session_id,
            browser_session_id=persisted.browser_session_id,
            backend_mode=persisted.backend_mode,
            supported=self.health().supported,
            configured=self.health().configured,
            status="active" if persisted.current_url else "inactive",
            current_url=persisted.current_url,
            page_title=persisted.page_title,
            last_action_id=persisted.last_action_id,
            last_requested_action=persisted.last_requested_action,
            last_screenshot_path=persisted.last_screenshot_path,
            updated_at=persisted.updated_at,
        )

    def _latest_session(self) -> _PersistedBrowserSession | None:
        candidates = sorted(self._sessions_dir.glob("*.json"))
        if not candidates:
            return None
        latest = max(candidates, key=lambda item: item.stat().st_mtime)
        return load_json_model_or_quarantine(latest, _PersistedBrowserSession, quarantine_invalid=True)

    def _load_session(self, blink_session_id: str | None) -> _PersistedBrowserSession | None:
        if not blink_session_id:
            return None
        return load_json_model_or_quarantine(self._session_path(blink_session_id), _PersistedBrowserSession, quarantine_invalid=True)

    def _load_or_seed_session(self, blink_session_id: str, *, target_url: str | None = None) -> _PersistedBrowserSession:
        existing = self._load_session(blink_session_id)
        if existing is not None:
            return existing
        current_url = target_url or ("https://example.com/" if self._backend_mode == "stub" else None)
        page = self._default_stub_page(current_url or "https://example.com/") if self._backend_mode == "stub" else None
        persisted = _PersistedBrowserSession(
            blink_session_id=blink_session_id,
            browser_session_id=_browser_session_id(blink_session_id),
            backend_mode=self._backend_mode,
            current_url=(page.current_url if page is not None else current_url),
            page_title=(page.page_title if page is not None else None),
            visible_text=(page.visible_text if page is not None else None),
            summary=(page.summary if page is not None else None),
            candidate_targets=(page.candidate_targets if page is not None else []),
        )
        if page is not None:
            self._stub_pages[blink_session_id] = page
        self._persist_session(persisted)
        return persisted

    def _persist_session(self, persisted: _PersistedBrowserSession) -> None:
        persisted.updated_at = utc_now()
        write_json_atomic(self._session_path(persisted.blink_session_id), persisted, keep_backups=1)

    def _session_path(self, blink_session_id: str) -> Path:
        return self._sessions_dir / f"{_slugify(blink_session_id)}.json"

    def _action_dir(self, action_id: str) -> Path:
        directory = self._storage_dir / action_id
        directory.mkdir(parents=True, exist_ok=True)
        return directory

    def _snapshot_for_session(self, blink_session_id: str) -> BrowserSnapshotRecord | None:
        persisted = self._load_session(blink_session_id)
        if persisted is None:
            return None
        return BrowserSnapshotRecord(
            current_url=persisted.current_url,
            page_title=persisted.page_title,
            visible_text=persisted.visible_text,
            summary=persisted.summary,
            screenshot_path=persisted.last_screenshot_path,
            screenshot_data_url=_screenshot_data_url(persisted.last_screenshot_path),
            snapshot_path=persisted.last_snapshot_path,
            page_text_path=persisted.last_page_text_path,
            captured_at=persisted.updated_at,
        )

    def _materialize_snapshot(
        self,
        *,
        blink_session_id: str,
        persisted: _PersistedBrowserSession,
        action_id: str,
        playwright_page: Any | None = None,
    ) -> BrowserSnapshotRecord:
        action_dir = self._action_dir(action_id)
        screenshot_path = action_dir / "screenshot.png"
        page_text_path = action_dir / "page_text.txt"
        snapshot_path = action_dir / "snapshot.json"
        visible_text = persisted.visible_text or ""
        page_text_path.write_text(visible_text, encoding="utf-8")
        if playwright_page is not None:
            playwright_page.screenshot(path=str(screenshot_path), full_page=True)
            current_url = playwright_page.url
            page_title = playwright_page.title()
        else:
            screenshot_path.write_bytes(_STUB_PNG_BYTES)
            current_url = persisted.current_url
            page_title = persisted.page_title
        snapshot = BrowserSnapshotRecord(
            current_url=current_url,
            page_title=page_title,
            visible_text=visible_text,
            summary=persisted.summary,
            screenshot_path=str(screenshot_path),
            screenshot_data_url=_screenshot_data_url(str(screenshot_path)),
            snapshot_path=str(snapshot_path),
            page_text_path=str(page_text_path),
        )
        write_json_atomic(snapshot_path, snapshot, keep_backups=1)
        persisted.last_screenshot_path = str(screenshot_path)
        persisted.last_snapshot_path = str(snapshot_path)
        persisted.last_page_text_path = str(page_text_path)
        return snapshot

    def _candidate_targets(self, blink_session_id: str) -> list[BrowserTargetCandidateRecord]:
        persisted = self._load_session(blink_session_id)
        return list(persisted.candidate_targets) if persisted is not None else []

    def _resolve_target(
        self,
        *,
        blink_session_id: str,
        target_hint: BrowserTargetHintRecord | None,
        allow_missing: bool,
    ) -> _ResolvedTarget | None:
        candidates = self._candidate_targets(blink_session_id)
        if target_hint is None:
            if allow_missing:
                return None
            raise ConnectorActionError("browser_target_required", "browser_target_required")
        matches = [candidate for candidate in candidates if self._candidate_matches(candidate, target_hint)]
        if not matches:
            if allow_missing:
                return None
            raise ConnectorActionError("browser_target_not_found", "browser_target_not_found")
        candidate = matches[0]
        if candidate.input_type in {"password", "file"}:
            raise ConnectorActionError("unsafe_browser_target", "unsafe_browser_target")
        return _ResolvedTarget(candidate=candidate, selector_kind=candidate.selector_kind or "selector", selector_value=candidate.selector or candidate.target_id)

    def _candidate_matches(self, candidate: BrowserTargetCandidateRecord, hint: BrowserTargetHintRecord) -> bool:
        if hint.role and (candidate.role or "").lower() != hint.role.lower():
            return False
        checks = [
            (hint.label, candidate.label),
            (hint.text, candidate.text),
            (hint.placeholder, candidate.placeholder),
            (hint.field_name, candidate.field_name),
        ]
        for needle, haystack in checks:
            if needle and needle.lower() not in (haystack or "").lower():
                return False
        return any(value for value in [hint.label, hint.role, hint.text, hint.placeholder, hint.field_name])

    def _default_stub_page(self, target_url: str) -> _StubPageState:
        host = urlparse(target_url).netloc or "example.com"
        visible_text = f"Stub page for {host}. This page supports safe browsing previews."
        return _StubPageState(
            current_url=target_url,
            page_title=f"Stub Browser - {host}",
            visible_text=visible_text,
            summary=_text_summary(visible_text, fallback="Stub browser page."),
            candidate_targets=self._stub_candidates(target_url),
        )

    def _stub_candidates(self, target_url: str) -> list[BrowserTargetCandidateRecord]:
        slug = _slugify(target_url)
        return [
            BrowserTargetCandidateRecord(
                target_id=f"{slug}-search-input",
                label="Search",
                role="textbox",
                input_type="text",
                selector="[name='q']",
                selector_kind="css",
                placeholder="Search",
                field_name="q",
                action_hints=["type_text", "submit_form"],
            ),
            BrowserTargetCandidateRecord(
                target_id=f"{slug}-search-button",
                label="Search",
                role="button",
                selector="button[type='submit']",
                selector_kind="css",
                action_hints=["click_target", "submit_form"],
            ),
            BrowserTargetCandidateRecord(
                target_id=f"{slug}-continue-button",
                label="Continue",
                role="button",
                selector="button[data-role='continue']",
                selector_kind="css",
                action_hints=["click_target"],
            ),
        ]

    def _playwright_page(self, blink_session_id: str):
        runtime = self._playwright_runtime.get(blink_session_id)
        if runtime is not None:
            return runtime[3]
        try:
            from playwright.sync_api import sync_playwright
        except Exception as exc:
            self._launch_error_detail = "playwright_python_package_missing"
            raise ConnectorActionError("playwright_python_package_missing", "playwright_python_package_missing") from exc
        try:
            playwright = sync_playwright().start()
            browser = playwright.chromium.launch(headless=self._settings.blink_action_plane_browser_headless)
            context = browser.new_context()
            page = context.new_page()
        except Exception as exc:
            self._launch_error_detail = "playwright_launch_failed"
            raise ConnectorActionError("playwright_launch_failed", "playwright_launch_failed") from exc
        self._playwright_runtime[blink_session_id] = (playwright, browser, context, page)
        return page

    def _playwright_visible_text(self, page) -> str:
        try:
            return page.locator("body").inner_text(timeout=2000).strip()
        except Exception:
            return ""

    def _playwright_candidates(self, page) -> list[BrowserTargetCandidateRecord]:
        try:
            raw = page.evaluate(
                """() => Array.from(document.querySelectorAll('a,button,input,textarea,select,[role="button"],[role="textbox"]'))
                    .slice(0, 24)
                    .map((el, index) => ({
                      target_id: `target-${index}`,
                      label: (el.getAttribute('aria-label') || el.innerText || el.value || '').trim() || null,
                      role: (el.getAttribute('role') || el.tagName || '').toLowerCase(),
                      input_type: el.getAttribute('type') || null,
                      selector: el.id ? `#${el.id}` : (el.name ? `${el.tagName.toLowerCase()}[name="${el.name}"]` : null),
                      selector_kind: el.id ? 'css' : (el.name ? 'css' : null),
                      placeholder: el.getAttribute('placeholder') || null,
                      field_name: el.getAttribute('name') || null,
                      action_hints: [],
                      visible: !(el.offsetParent === null),
                      disabled: !!el.disabled,
                    }))"""
            )
        except Exception:
            return []
        candidates: list[BrowserTargetCandidateRecord] = []
        for item in raw or []:
            try:
                candidate = BrowserTargetCandidateRecord.model_validate(item)
            except Exception:
                continue
            if candidate.input_type in {"password", "file"}:
                continue
            candidates.append(candidate)
        return candidates

    def _resolve_playwright_target(
        self,
        *,
        page,
        target_hint: BrowserTargetHintRecord | None,
        require_editable: bool,
        allow_missing: bool = False,
    ) -> _ResolvedTarget | None:
        candidates = self._playwright_candidates(page)
        if target_hint is None:
            if allow_missing:
                return None
            raise ConnectorActionError("browser_target_required", "browser_target_required")
        matches = [candidate for candidate in candidates if self._candidate_matches(candidate, target_hint)]
        if require_editable:
            matches = [candidate for candidate in matches if candidate.role in {"input", "textarea", "textbox", "select"} or candidate.input_type]
        if not matches:
            if allow_missing:
                return None
            raise ConnectorActionError("browser_target_not_found", "browser_target_not_found")
        candidate = matches[0]
        if candidate.input_type in {"password", "file"}:
            raise ConnectorActionError("unsafe_browser_target", "unsafe_browser_target")
        selector = candidate.selector or ""
        selector_kind = candidate.selector_kind or "fallback"
        if not selector:
            if candidate.role in {"button", "a"} and candidate.label:
                selector = candidate.label
                selector_kind = "role_name"
            elif candidate.placeholder:
                selector = candidate.placeholder
                selector_kind = "placeholder"
            elif candidate.field_name:
                selector = candidate.field_name
                selector_kind = "field_name"
            else:
                selector = candidate.target_id
        candidate.selector = selector
        candidate.selector_kind = selector_kind
        return _ResolvedTarget(candidate=candidate, selector_kind=selector_kind, selector_value=selector)

    def _locator_for_candidate(self, page, resolved: _ResolvedTarget):
        candidate = resolved.candidate
        selector = resolved.selector_value
        if resolved.selector_kind == "css":
            return page.locator(selector).first
        if resolved.selector_kind == "role_name":
            role = "button" if candidate.role in {"button", "a"} else "textbox"
            return page.get_by_role(role, name=selector).first
        if resolved.selector_kind == "placeholder":
            return page.get_by_placeholder(selector).first
        if resolved.selector_kind == "field_name":
            return page.locator(f"[name='{selector}']").first
        return page.locator(selector).first


__all__ = [
    "BrowserRuntimeConnector",
    "build_browser_connector_descriptor",
]
