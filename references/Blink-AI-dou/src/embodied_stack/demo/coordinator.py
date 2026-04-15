from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from time import perf_counter, sleep
from typing import Protocol

import httpx
from pydantic import ValidationError

from embodied_stack.demo.community_scripts import DEMO_SCENARIOS
from embodied_stack.demo.report_store import DemoReportStore
from embodied_stack.shared.models import (
    BrainResetRequest,
    CapabilityProfile,
    CommandAck,
    CommandAckStatus,
    CommandHistoryResponse,
    DemoFallbackEvent,
    DemoRunMetrics,
    DemoRunRecord,
    DemoRunRequest,
    DemoRunStatus,
    DemoRunStepRecord,
    IncidentListScope,
    EdgeTransportMode,
    HeartbeatStatus,
    LatencyBreakdownRecord,
    ResetResult,
    RobotCommand,
    RobotMode,
    SimulatedSensorEventRequest,
    SimulatedSensorEventResult,
    TelemetryLogResponse,
    TelemetrySnapshot,
    TraceOutcome,
    TraceRecord,
    TransportState,
    utc_now,
)


class EdgeGateway(Protocol):
    def reset(self) -> None:
        ...

    def simulate_event(self, request: SimulatedSensorEventRequest) -> SimulatedSensorEventResult:
        ...

    def apply_command(self, command: RobotCommand) -> CommandAck:
        ...

    def get_telemetry(self) -> TelemetrySnapshot:
        ...

    def get_telemetry_log(self) -> TelemetryLogResponse:
        ...

    def get_heartbeat(self) -> HeartbeatStatus:
        ...

    def get_command_history(self) -> CommandHistoryResponse:
        ...

    def get_capabilities(self) -> CapabilityProfile:
        ...

    def force_safe_idle(self, reason: str) -> HeartbeatStatus:
        ...

    def transport_mode(self) -> EdgeTransportMode:
        ...

    def transport_state(self) -> TransportState:
        ...

    def last_transport_error(self) -> str | None:
        ...


class EdgeGatewayError(RuntimeError):
    def __init__(
        self,
        *,
        operation: str,
        classification: str,
        detail: str,
        retryable: bool,
        attempt_count: int,
    ) -> None:
        super().__init__(f"{operation}:{classification}:{detail}")
        self.operation = operation
        self.classification = classification
        self.detail = detail
        self.retryable = retryable
        self.attempt_count = attempt_count


class HttpEdgeGateway:
    def __init__(
        self,
        base_url: str,
        timeout_seconds: float = 3.0,
        max_retries: int = 1,
        retry_backoff_seconds: float = 0.15,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.max_retries = max(0, max_retries)
        self.retry_backoff_seconds = max(0.0, retry_backoff_seconds)
        self.transport = transport
        self._last_transport_state = TransportState.HEALTHY
        self._last_transport_error: str | None = None
        self._last_telemetry = TelemetrySnapshot(mode=RobotMode.TETHERED_DEMO)
        self._last_heartbeat = HeartbeatStatus(
            connected=False,
            network_ok=False,
            safe_idle_active=True,
            safe_idle_reason="edge_unreachable",
            transport_ok=False,
            transport_error="edge_unreachable",
        )
        self._last_telemetry_log = TelemetryLogResponse()
        self._last_command_history = CommandHistoryResponse()
        self._last_capabilities = CapabilityProfile(mode=RobotMode.TETHERED_DEMO)

    def reset(self) -> None:
        self._request_model(
            operation="reset",
            method="POST",
            path="/api/reset",
            model=ResetResult,
            expected_fields=("ok",),
            safe_to_retry=True,
        )

    def simulate_event(self, request: SimulatedSensorEventRequest) -> SimulatedSensorEventResult:
        return self._request_model(
            operation="simulate_event",
            method="POST",
            path="/api/sim/events",
            model=SimulatedSensorEventResult,
            json_payload=request.model_dump(mode="json"),
            expected_fields=("event", "telemetry", "heartbeat"),
            safe_to_retry=False,
        )

    def apply_command(self, command: RobotCommand) -> CommandAck:
        try:
            return self._request_model(
                operation="apply_command",
                method="POST",
                path="/api/commands",
                model=CommandAck,
                json_payload=command.model_dump(mode="json"),
                expected_fields=("command_id", "accepted", "status"),
                safe_to_retry=True,
            )
        except EdgeGatewayError as exc:
            self._mark_transport_degraded(exc)
            return CommandAck(
                command_id=command.command_id,
                accepted=False,
                status=CommandAckStatus.TRANSPORT_ERROR,
                reason=exc.classification,
                transport_error=exc.detail,
                attempt_count=exc.attempt_count,
                applied_state=self._degraded_telemetry(exc.detail).model_dump(mode="json"),
            )

    def get_telemetry(self) -> TelemetrySnapshot:
        try:
            telemetry = self._request_model(
                operation="get_telemetry",
                method="GET",
                path="/api/telemetry",
                model=TelemetrySnapshot,
                expected_fields=("mode", "battery_pct"),
                safe_to_retry=True,
            )
            self._last_telemetry = telemetry.model_copy(deep=True)
            return telemetry
        except EdgeGatewayError as exc:
            self._mark_transport_degraded(exc)
            return self._degraded_telemetry(exc.detail)

    def get_telemetry_log(self) -> TelemetryLogResponse:
        try:
            log = self._request_model(
                operation="get_telemetry_log",
                method="GET",
                path="/api/telemetry/log",
                model=TelemetryLogResponse,
                expected_fields=("items",),
                safe_to_retry=True,
            )
            self._last_telemetry_log = log.model_copy(deep=True)
            return log
        except EdgeGatewayError as exc:
            self._mark_transport_degraded(exc)
            return self._last_telemetry_log.model_copy(deep=True)

    def get_heartbeat(self) -> HeartbeatStatus:
        try:
            heartbeat = self._request_model(
                operation="get_heartbeat",
                method="GET",
                path="/api/heartbeat",
                model=HeartbeatStatus,
                expected_fields=("connected", "network_ok"),
                safe_to_retry=True,
            )
            self._last_heartbeat = heartbeat.model_copy(deep=True)
            return heartbeat
        except EdgeGatewayError as exc:
            self._mark_transport_degraded(exc)
            return self._degraded_heartbeat(exc.detail)

    def get_command_history(self) -> CommandHistoryResponse:
        try:
            history = self._request_model(
                operation="get_command_history",
                method="GET",
                path="/api/command-history",
                model=CommandHistoryResponse,
                expected_fields=("items",),
                safe_to_retry=True,
            )
            self._last_command_history = history.model_copy(deep=True)
            return history
        except EdgeGatewayError as exc:
            self._mark_transport_degraded(exc)
            return self._last_command_history.model_copy(deep=True)

    def get_capabilities(self) -> CapabilityProfile:
        try:
            capabilities = self._request_model(
                operation="get_capabilities",
                method="GET",
                path="/api/capabilities",
                model=CapabilityProfile,
                expected_fields=("mode",),
                safe_to_retry=True,
            )
            self._last_capabilities = capabilities.model_copy(deep=True)
            return capabilities
        except EdgeGatewayError as exc:
            self._mark_transport_degraded(exc)
            return self._last_capabilities.model_copy(deep=True)

    def force_safe_idle(self, reason: str) -> HeartbeatStatus:
        try:
            heartbeat = self._request_model(
                operation="force_safe_idle",
                method="POST",
                path="/api/safe-idle",
                model=HeartbeatStatus,
                params={"reason": reason},
                expected_fields=("connected", "network_ok"),
                safe_to_retry=True,
            )
            self._last_heartbeat = heartbeat.model_copy(deep=True)
            return heartbeat
        except EdgeGatewayError as exc:
            self._mark_transport_degraded(exc)
            return self._degraded_heartbeat(exc.detail)

    def transport_mode(self) -> EdgeTransportMode:
        return EdgeTransportMode.HTTP

    def transport_state(self) -> TransportState:
        return self._last_transport_state

    def last_transport_error(self) -> str | None:
        return self._last_transport_error

    def _request_model(
        self,
        *,
        operation: str,
        method: str,
        path: str,
        model,
        safe_to_retry: bool,
        json_payload: dict | None = None,
        params: dict | None = None,
        expected_fields: tuple[str, ...] = (),
    ):
        last_error: EdgeGatewayError | None = None
        total_attempts = 1 + self.max_retries
        for attempt in range(1, total_attempts + 1):
            try:
                with httpx.Client(timeout=self.timeout_seconds, transport=self.transport) as client:
                    response = client.request(
                        method,
                        f"{self.base_url}{path}",
                        json=json_payload,
                        params=params,
                    )
                    response.raise_for_status()
                    body = response.json()
                if expected_fields and (
                    not isinstance(body, dict) or any(field not in body for field in expected_fields)
                ):
                    raise ValueError(f"missing_expected_fields:{','.join(expected_fields)}")
                value = model.model_validate(body)
                self._clear_transport_error()
                return value
            except httpx.TimeoutException as exc:
                last_error = EdgeGatewayError(
                    operation=operation,
                    classification="timeout",
                    detail=str(exc),
                    retryable=True,
                    attempt_count=attempt,
                )
            except httpx.ConnectError as exc:
                last_error = EdgeGatewayError(
                    operation=operation,
                    classification="unreachable",
                    detail=str(exc),
                    retryable=True,
                    attempt_count=attempt,
                )
            except httpx.HTTPStatusError as exc:
                retryable = exc.response.status_code >= 500
                last_error = EdgeGatewayError(
                    operation=operation,
                    classification=f"http_{exc.response.status_code}",
                    detail=exc.response.text[:200],
                    retryable=retryable,
                    attempt_count=attempt,
                )
            except (ValueError, ValidationError) as exc:
                last_error = EdgeGatewayError(
                    operation=operation,
                    classification="invalid_response",
                    detail=str(exc),
                    retryable=False,
                    attempt_count=attempt,
                )
            except httpx.HTTPError as exc:
                last_error = EdgeGatewayError(
                    operation=operation,
                    classification="transport_error",
                    detail=str(exc),
                    retryable=True,
                    attempt_count=attempt,
                )

            if last_error is None:
                continue
            if not (safe_to_retry and last_error.retryable and attempt < total_attempts):
                self._mark_transport_degraded(last_error)
                raise last_error
            sleep(self.retry_backoff_seconds)

        assert last_error is not None
        self._mark_transport_degraded(last_error)
        raise last_error

    def _clear_transport_error(self) -> None:
        self._last_transport_state = TransportState.HEALTHY
        self._last_transport_error = None

    def _mark_transport_degraded(self, error: EdgeGatewayError) -> None:
        self._last_transport_state = TransportState.DEGRADED
        self._last_transport_error = f"{error.operation}:{error.classification}"

    def _degraded_telemetry(self, reason: str) -> TelemetrySnapshot:
        telemetry = self._last_telemetry.model_copy(deep=True)
        telemetry.mode = RobotMode.DEGRADED_SAFE_IDLE
        telemetry.network_ok = False
        telemetry.safe_idle_reason = "edge_transport_degraded"
        telemetry.transport_ok = False
        telemetry.transport_error = reason
        telemetry.last_updated = utc_now()
        self._last_telemetry = telemetry.model_copy(deep=True)
        return telemetry

    def _degraded_heartbeat(self, reason: str) -> HeartbeatStatus:
        heartbeat = self._last_heartbeat.model_copy(deep=True)
        heartbeat.connected = False
        heartbeat.network_ok = False
        heartbeat.safe_idle_active = True
        heartbeat.safe_idle_reason = "edge_transport_degraded"
        heartbeat.transport_ok = False
        heartbeat.transport_error = reason
        heartbeat.last_contact_at = utc_now()
        self._last_heartbeat = heartbeat.model_copy(deep=True)
        return heartbeat


@dataclass
class InProcessEdgeGateway:
    controller: object

    def reset(self) -> None:
        self.controller.reset()

    def simulate_event(self, request: SimulatedSensorEventRequest) -> SimulatedSensorEventResult:
        return self.controller.simulate_event(request)

    def apply_command(self, command: RobotCommand) -> CommandAck:
        return self.controller.apply_command(command)

    def get_telemetry(self) -> TelemetrySnapshot:
        return self.controller.get_telemetry()

    def get_telemetry_log(self) -> TelemetryLogResponse:
        return self.controller.get_telemetry_log()

    def get_heartbeat(self) -> HeartbeatStatus:
        return self.controller.get_heartbeat()

    def get_command_history(self) -> CommandHistoryResponse:
        return self.controller.get_command_history()

    def get_capabilities(self) -> CapabilityProfile:
        return self.controller.capabilities

    def force_safe_idle(self, reason: str) -> HeartbeatStatus:
        return self.controller.force_safe_idle(reason)

    def transport_mode(self) -> EdgeTransportMode:
        return EdgeTransportMode.IN_PROCESS

    def transport_state(self) -> TransportState:
        return TransportState.HEALTHY

    def last_transport_error(self) -> str | None:
        return None


class DemoCoordinator:
    def __init__(self, *, orchestrator, edge_gateway: EdgeGateway, report_dir: str | Path) -> None:
        self.orchestrator = orchestrator
        self.edge_gateway = edge_gateway
        self.report_store = DemoReportStore(report_dir)

    def reset_system(self, request: BrainResetRequest | None = None) -> ResetResult:
        reset_request = request or BrainResetRequest()
        self.orchestrator.reset_runtime(clear_user_memory=reset_request.clear_user_memory)
        edge_reset = False
        notes: list[str] = []
        if reset_request.reset_edge:
            try:
                self.edge_gateway.reset()
                edge_reset = True
            except EdgeGatewayError as exc:
                notes.append(f"edge_reset_failed:{exc.classification}")
        if reset_request.clear_demo_runs:
            self.report_store.clear()
        return ResetResult(
            ok=edge_reset if reset_request.reset_edge else True,
            brain_reset=True,
            edge_reset=edge_reset,
            cleared_demo_runs=reset_request.clear_demo_runs,
            notes=notes,
        )

    def run_demo(self, request: DemoRunRequest) -> DemoRunRecord:
        scenario_names = request.scenario_names or list(DEMO_SCENARIOS.keys())
        run = DemoRunRecord(
            scenario_names=scenario_names,
            status=DemoRunStatus.RUNNING,
            configured_dialogue_backend=self._setting("brain_dialogue_backend"),
            runtime_profile=self._setting("brain_runtime_profile"),
            deployment_target=self._setting("brain_deployment_target"),
        )
        traces: list[TraceRecord] = []

        if request.reset_brain_first:
            self.orchestrator.reset_runtime(clear_user_memory=True)
            run.notes.append("brain_reset_before_run")
        if request.reset_edge_first:
            self.edge_gateway.reset()
            run.notes.append("edge_reset_before_run")

        for scenario_name in scenario_names:
            scenario = DEMO_SCENARIOS.get(scenario_name)
            if scenario is None:
                run.status = DemoRunStatus.FAILED
                run.passed = False
                run.notes.append(f"unknown_scenario:{scenario_name}")
                continue

            session_id = f"{run.run_id}-{scenario_name}"
            self.orchestrator.create_session(
                self.orchestrator.build_session_request(
                    session_id=session_id,
                    user_id=request.user_id,
                    scenario_name=scenario_name,
                    response_mode=request.response_mode,
                )
            )

            for index, step in enumerate(scenario.steps, start=1):
                started_at = utc_now()
                start = perf_counter()
                try:
                    sim_result = self.edge_gateway.simulate_event(
                        SimulatedSensorEventRequest(
                            event_type=step.event_type,
                            payload=step.payload,
                            session_id=session_id,
                        )
                    )
                except EdgeGatewayError as exc:
                    run.status = DemoRunStatus.FAILED
                    run.passed = False
                    run.notes.append(f"simulate_event_failed:{scenario_name}:{index}:{exc.classification}")
                    break
                response = self.orchestrator.handle_event(sim_result.event)
                trace = self.orchestrator.get_trace(response.trace_id) if response.trace_id else None
                if trace is not None:
                    traces.append(trace)
                command_acks = [self.edge_gateway.apply_command(command) for command in response.commands]
                telemetry = self.edge_gateway.get_telemetry()
                heartbeat = self.edge_gateway.get_heartbeat()
                latency_ms = round((perf_counter() - start) * 1000.0, 2)
                completed_at = utc_now()
                outcome = self._derive_outcome(trace, command_acks, heartbeat)
                success = all(ack.accepted for ack in command_acks)
                if outcome in {TraceOutcome.SAFE_FALLBACK, TraceOutcome.FALLBACK_REPLY}:
                    run.fallback_count += 1
                    run.fallback_events.append(self._build_fallback_event(trace, sim_result.event, outcome))
                if not success:
                    run.status = DemoRunStatus.FAILED
                    run.passed = False

                run.steps.append(
                    DemoRunStepRecord(
                        scenario_name=scenario_name,
                        step_index=index,
                        started_at=started_at,
                        completed_at=completed_at,
                        event=sim_result.event,
                        response=response,
                        command_acks=command_acks,
                        telemetry=telemetry,
                        heartbeat=heartbeat,
                        success=success,
                        latency_ms=latency_ms,
                        trace_latency_ms=trace.latency_ms if trace else None,
                        backend_used=trace.reasoning.engine if trace else "system",
                        fallback_used=trace.reasoning.fallback_used if trace else False,
                        outcome=outcome,
                        latency_breakdown=trace.reasoning.latency_breakdown if trace else LatencyBreakdownRecord(),
                        grounding_sources=trace.reasoning.grounding_sources if trace else [],
                        shift_supervisor=trace.reasoning.shift_supervisor if trace else self.orchestrator.get_shift_supervisor(),
                        incident_ticket=trace.reasoning.incident_ticket if trace else None,
                        incident_timeline=trace.reasoning.incident_timeline if trace else [],
                    )
                )
                if request.stop_on_failure and not success:
                    break

            if request.stop_on_failure and run.status == DemoRunStatus.FAILED:
                break

        if run.status == DemoRunStatus.RUNNING:
            run.status = DemoRunStatus.COMPLETED
        run.passed = run.status == DemoRunStatus.COMPLETED and all(step.success for step in run.steps)
        run.total_latency_ms = round(sum(step.latency_ms for step in run.steps), 2)
        run.observed_dialogue_backends = sorted(
            {step.backend_used for step in run.steps if step.backend_used}
        )
        run.metrics = self._build_metrics(run, traces)
        run.completed_at = utc_now()
        run.final_world_state = self.orchestrator.get_world_state()
        run.final_shift_supervisor = self.orchestrator.get_shift_supervisor()
        run.final_grounding_sources = traces[-1].reasoning.grounding_sources if traces else []
        session_ids = list({step.event.session_id for step in run.steps if step.event.session_id})
        run.final_incidents = (
            self.orchestrator.list_incidents(scope=IncidentListScope.ALL, limit=200).items
            if not session_ids
            else [
                item
                for session_id in session_ids
                for item in self.orchestrator.list_incidents(scope=IncidentListScope.ALL, session_id=session_id, limit=200).items
            ]
        )
        sessions = [
            session
            for session_id in session_ids
            if (session := self.orchestrator.get_session(session_id)) is not None
        ]
        return self.report_store.save(
            run,
            sessions=sessions,
            traces=traces,
            telemetry_log=self.edge_gateway.get_telemetry_log(),
            command_history=self.edge_gateway.get_command_history(),
            perception_snapshots=self.orchestrator.list_perception_history(limit=100) if not session_ids else {
                "items": [
                    item
                    for session_id in session_ids
                    for item in self.orchestrator.list_perception_history(session_id=session_id, limit=100).items
                ]
            },
            world_model_transitions=self.orchestrator.list_world_model_transitions(limit=200) if not session_ids else {
                "items": [
                    item
                    for session_id in session_ids
                    for item in self.orchestrator.list_world_model_transitions(session_id=session_id, limit=200).items
                ]
            },
            shift_transitions=self.orchestrator.list_shift_transitions(limit=200) if not session_ids else {
                "items": [
                    item
                    for session_id in session_ids
                    for item in self.orchestrator.list_shift_transitions(session_id=session_id, limit=200).items
                ]
            },
            incidents=run.final_incidents,
            incident_timeline=self.orchestrator.list_incident_timeline(limit=400) if not session_ids else {
                "items": [
                    item
                    for session_id in session_ids
                    for item in self.orchestrator.list_incident_timeline(session_id=session_id, limit=400).items
                ]
            },
            executive_decisions=self.orchestrator.list_executive_decisions(limit=200) if not session_ids else {
                "items": [
                    item
                    for session_id in session_ids
                    for item in self.orchestrator.list_executive_decisions(session_id=session_id, limit=200).items
                ]
            },
            grounding_sources=run.final_grounding_sources,
        )

    def list_runs(self):
        return self.report_store.list()

    def get_run(self, run_id: str) -> DemoRunRecord | None:
        return self.report_store.get(run_id)

    def clear_runs(self) -> None:
        self.report_store.clear()

    def _derive_outcome(
        self,
        trace: TraceRecord | None,
        command_acks: list[CommandAck],
        heartbeat: HeartbeatStatus,
    ) -> TraceOutcome:
        if any(ack.status == CommandAckStatus.TRANSPORT_ERROR for ack in command_acks):
            return TraceOutcome.ERROR
        if heartbeat.safe_idle_active:
            return TraceOutcome.SAFE_FALLBACK
        if any(not ack.accepted for ack in command_acks):
            return TraceOutcome.ERROR
        if trace:
            return trace.outcome
        return TraceOutcome.OK

    def _build_fallback_event(
        self,
        trace: TraceRecord | None,
        event,
        outcome: TraceOutcome,
    ) -> DemoFallbackEvent:
        note = None
        backend_used = None
        trace_id = None
        timestamp = event.timestamp
        if trace is not None:
            note = ", ".join(trace.reasoning.notes) if trace.reasoning.notes else None
            backend_used = trace.reasoning.engine
            trace_id = trace.trace_id
            timestamp = trace.timestamp
        return DemoFallbackEvent(
            timestamp=timestamp,
            session_id=event.session_id or "default-session",
            event_type=event.event_type,
            trace_id=trace_id,
            backend_used=backend_used,
            outcome=outcome,
            note=note,
        )

    def _build_metrics(self, run: DemoRunRecord, traces: list[TraceRecord]) -> DemoRunMetrics:
        command_count = sum(len(step.response.commands) for step in run.steps)
        acknowledged_count = sum(sum(1 for ack in step.command_acks if ack.accepted) for step in run.steps)
        rejected_count = sum(sum(1 for ack in step.command_acks if not ack.accepted) for step in run.steps)
        end_to_end_latencies = [step.latency_ms for step in run.steps]
        trace_latencies = [trace.latency_ms for trace in traces if trace.latency_ms is not None]
        perception_latencies = [trace.reasoning.latency_breakdown.perception_ms for trace in traces if trace.reasoning.latency_breakdown.perception_ms is not None]
        tool_latencies = [trace.reasoning.latency_breakdown.tool_ms for trace in traces if trace.reasoning.latency_breakdown.tool_ms is not None]
        dialogue_latencies = [trace.reasoning.latency_breakdown.dialogue_ms for trace in traces if trace.reasoning.latency_breakdown.dialogue_ms is not None]
        executive_latencies = [trace.reasoning.latency_breakdown.executive_ms for trace in traces if trace.reasoning.latency_breakdown.executive_ms is not None]
        ack_total = acknowledged_count + rejected_count
        return DemoRunMetrics(
            step_count=len(run.steps),
            trace_count=len(traces),
            command_count=command_count,
            acknowledged_count=acknowledged_count,
            rejected_count=rejected_count,
            ack_success_rate=round((acknowledged_count / ack_total) if ack_total else 1.0, 4),
            fallback_event_count=len(run.fallback_events),
            safe_fallback_count=sum(1 for step in run.steps if step.outcome == TraceOutcome.SAFE_FALLBACK),
            average_end_to_end_latency_ms=round(sum(end_to_end_latencies) / len(end_to_end_latencies), 2)
            if end_to_end_latencies
            else 0.0,
            max_end_to_end_latency_ms=round(max(end_to_end_latencies), 2) if end_to_end_latencies else 0.0,
            average_trace_latency_ms=round(sum(trace_latencies) / len(trace_latencies), 2) if trace_latencies else 0.0,
            max_trace_latency_ms=round(max(trace_latencies), 2) if trace_latencies else 0.0,
            average_perception_latency_ms=round(sum(perception_latencies) / len(perception_latencies), 2) if perception_latencies else 0.0,
            max_perception_latency_ms=round(max(perception_latencies), 2) if perception_latencies else 0.0,
            average_tool_latency_ms=round(sum(tool_latencies) / len(tool_latencies), 2) if tool_latencies else 0.0,
            average_dialogue_latency_ms=round(sum(dialogue_latencies) / len(dialogue_latencies), 2) if dialogue_latencies else 0.0,
            average_executive_latency_ms=round(sum(executive_latencies) / len(executive_latencies), 2) if executive_latencies else 0.0,
        )

    def _setting(self, name: str) -> str | None:
        settings = getattr(self.orchestrator, "settings", None)
        if settings is None:
            return None
        value = getattr(settings, name, None)
        return str(value) if value is not None else None
