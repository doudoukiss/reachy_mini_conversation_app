from __future__ import annotations

import httpx

from embodied_stack.demo.coordinator import HttpEdgeGateway
from embodied_stack.shared.models import CommandAckStatus, RobotCommand


def test_http_edge_gateway_retries_safe_command_requests():
    attempts = {"count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise httpx.ConnectError("edge unavailable", request=request)
        return httpx.Response(
            200,
            json={
                "command_id": "command-1",
                "accepted": True,
                "status": "applied",
                "reason": "ok",
                "attempt_count": 1,
                "applied_state": {"display_text": "hello"},
            },
        )

    gateway = HttpEdgeGateway(
        "http://edge.test",
        timeout_seconds=0.1,
        max_retries=1,
        retry_backoff_seconds=0.0,
        transport=httpx.MockTransport(handler),
    )

    ack = gateway.apply_command(
        RobotCommand(command_id="command-1", command_type="display_text", payload={"text": "hello"})
    )

    assert attempts["count"] == 2
    assert ack.accepted is True
    assert ack.status == CommandAckStatus.APPLIED
    assert gateway.transport_state().value == "healthy"


def test_http_edge_gateway_returns_transport_error_ack_and_degraded_snapshot():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("edge unavailable", request=request)

    gateway = HttpEdgeGateway(
        "http://edge.test",
        timeout_seconds=0.1,
        max_retries=0,
        retry_backoff_seconds=0.0,
        transport=httpx.MockTransport(handler),
    )

    ack = gateway.apply_command(
        RobotCommand(command_id="command-2", command_type="display_text", payload={"text": "hello"})
    )
    telemetry = gateway.get_telemetry()
    heartbeat = gateway.get_heartbeat()

    assert ack.accepted is False
    assert ack.status == CommandAckStatus.TRANSPORT_ERROR
    assert gateway.transport_state().value == "degraded"
    assert telemetry.transport_ok is False
    assert telemetry.safe_idle_reason == "edge_transport_degraded"
    assert heartbeat.transport_ok is False
    assert heartbeat.safe_idle_active is True


def test_http_edge_gateway_classifies_invalid_response_as_transport_degradation():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"bad": "payload"})

    gateway = HttpEdgeGateway(
        "http://edge.test",
        timeout_seconds=0.1,
        max_retries=0,
        retry_backoff_seconds=0.0,
        transport=httpx.MockTransport(handler),
    )

    telemetry = gateway.get_telemetry()

    assert telemetry.transport_ok is False
    assert telemetry.transport_error
    assert gateway.last_transport_error() == "get_telemetry:invalid_response"


def test_http_edge_gateway_force_safe_idle_preserves_transport_error_detail():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("edge unavailable", request=request)

    gateway = HttpEdgeGateway(
        "http://edge.test",
        timeout_seconds=0.1,
        max_retries=0,
        retry_backoff_seconds=0.0,
        transport=httpx.MockTransport(handler),
    )

    heartbeat = gateway.force_safe_idle("operator_override")

    assert heartbeat.safe_idle_active is True
    assert heartbeat.safe_idle_reason == "edge_transport_degraded"
    assert heartbeat.transport_ok is False
    assert "edge unavailable" in (heartbeat.transport_error or "")
