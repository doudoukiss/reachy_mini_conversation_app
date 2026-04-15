from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from embodied_stack.action_plane.connectors import ConnectorActionError
from embodied_stack.action_plane.connectors.browser import (
    BrowserRuntimeConnector,
    build_browser_connector_descriptor,
)
from embodied_stack.config import Settings
from embodied_stack.shared.contracts import (
    ActionInvocationOrigin,
    ActionRequestRecord,
    ActionRiskClass,
    BrowserRequestedAction,
    SessionRecord,
)


def _request(*, action_name: str, payload: dict[str, object], session_id: str = "browser-unit") -> ActionRequestRecord:
    return ActionRequestRecord(
        action_id=f"act_{action_name}",
        request_hash=f"req_{action_name}",
        idempotency_key=f"idem_{action_name}",
        tool_name="browser_task",
        requested_tool_name="browser_task",
        action_name=action_name,
        requested_action_name=action_name,
        connector_id="browser_runtime",
        risk_class=ActionRiskClass.READ_ONLY,
        invocation_origin=ActionInvocationOrigin.USER_TURN,
        session_id=session_id,
        input_payload=payload,
    )


def test_browser_descriptor_reflects_backend_modes(tmp_path: Path):
    disabled = build_browser_connector_descriptor(
        Settings(_env_file=None, blink_action_plane_browser_backend="disabled")
    )
    stub = build_browser_connector_descriptor(
        Settings(_env_file=None, blink_action_plane_browser_backend="stub")
    )

    assert disabled.supported is False
    assert disabled.configured is False
    assert stub.supported is True
    assert stub.configured is True
    assert BrowserRequestedAction.OPEN_URL.value in stub.supported_actions


def test_browser_connector_stub_writes_preview_and_result_artifacts(tmp_path: Path):
    settings = Settings(
        _env_file=None,
        blink_action_plane_browser_backend="stub",
        blink_action_plane_browser_storage_dir=str(tmp_path / "browser"),
    )
    connector = BrowserRuntimeConnector(build_browser_connector_descriptor(settings), settings=settings)
    runtime_context = SimpleNamespace(session=SessionRecord(session_id="browser-unit"))

    open_result = connector.execute(
        action_name="open_url",
        request=_request(
            action_name="open_url",
            payload={
                "query": "Open example.com",
                "target_url": "https://example.com",
            },
        ),
        runtime_context=runtime_context,
    )
    assert open_result.output_payload["status"] == "ok"
    assert Path(open_result.output_payload["snapshot"]["screenshot_path"]).exists()

    preview = connector.preview(
        action_name="type_text",
        request=_request(
            action_name="type_text",
            payload={
                "query": "Type into the search field",
                "target_hint": {"label": "Search"},
                "text_input": "Blink concierge",
            },
        ),
        runtime_context=runtime_context,
        reason="approval_required",
    )
    assert preview.output_payload["preview_required"] is True
    assert preview.output_payload["preview"]["resolved_target"]["label"] == "Search"
    assert Path(preview.output_payload["preview"]["preview_path"]).exists()


def test_browser_connector_rejects_unsafe_local_url(tmp_path: Path):
    settings = Settings(
        _env_file=None,
        blink_action_plane_browser_backend="stub",
        blink_action_plane_browser_storage_dir=str(tmp_path / "browser"),
    )
    connector = BrowserRuntimeConnector(build_browser_connector_descriptor(settings), settings=settings)
    runtime_context = SimpleNamespace(session=SessionRecord(session_id="browser-unit"))

    with pytest.raises(ConnectorActionError) as excinfo:
        connector.execute(
            action_name="open_url",
            request=_request(
                action_name="open_url",
                payload={
                    "query": "Open localhost",
                    "target_url": "http://127.0.0.1:3000",
                },
            ),
            runtime_context=runtime_context,
        )

    assert excinfo.value.code == "unsafe_browser_host"
