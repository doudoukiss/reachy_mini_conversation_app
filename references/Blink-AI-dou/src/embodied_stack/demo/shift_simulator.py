from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from time import perf_counter

from embodied_stack.brain.orchestrator import BrainOrchestrator
from embodied_stack.config import Settings, get_settings
from embodied_stack.demo.coordinator import EdgeGateway
from embodied_stack.desktop.runtime import build_inprocess_embodiment_gateway
from embodied_stack.demo.shift_metrics import calculate_shift_metrics, collect_shift_evidence, score_shift_metrics
from embodied_stack.demo.shift_reports import ShiftReportStore
from embodied_stack.shared.models import (
    CommandAck,
    CommandAckStatus,
    CommandBatch,
    GroundingSourceRecord,
    IncidentAcknowledgeRequest,
    IncidentAssignRequest,
    IncidentListScope,
    IncidentNoteRequest,
    IncidentResolutionOutcome,
    IncidentResolveRequest,
    IncidentTicketRecord,
    RobotEvent,
    SimulatedSensorEventRequest,
    ShiftReportRecord,
    ShiftReportStatus,
    ShiftSimulationDefinition,
    ShiftSimulationStepActionType,
    ShiftSimulationStepDefinition,
    ShiftSimulationStepRecord,
    TraceOutcome,
    TraceRecord,
    utc_now,
)


DEFAULT_FIXTURE_NAME = "community_center_pilot_day.json"


@dataclass
class PilotShiftSimulator:
    settings: Settings
    orchestrator: BrainOrchestrator
    edge_gateway: EdgeGateway
    report_store: ShiftReportStore

    def run(
        self,
        definition: ShiftSimulationDefinition,
        *,
        reset_runtime_first: bool = True,
    ) -> ShiftReportRecord:
        if reset_runtime_first:
            self.orchestrator.reset_runtime(clear_user_memory=True)
            self.edge_gateway.reset()

        if definition.venue_content_dir and Path(definition.venue_content_dir).as_posix() != Path(self.settings.venue_content_dir).as_posix():
            raise ValueError(
                f"shift_simulation_venue_mismatch:{definition.venue_content_dir} != {self.settings.venue_content_dir}"
            )

        report = ShiftReportRecord(
            simulation_name=definition.simulation_name,
            description=definition.description,
            site_name=definition.site_name or self.settings.pilot_site,
            fixture_path=definition.fixture_path,
            status=ShiftReportStatus.RUNNING,
            simulation_definition=definition.model_copy(deep=True),
            configured_dialogue_backend=self.settings.brain_dialogue_backend,
            runtime_profile=self.settings.brain_runtime_profile,
            deployment_target=self.settings.brain_deployment_target,
        )

        for step in self._ordered_steps(definition):
            report.steps.append(self._run_step(definition=definition, step=step))

        evidence = collect_shift_evidence(self.orchestrator)
        report.session_ids = sorted({session.session_id for session in evidence.sessions})
        report.observed_dialogue_backends = sorted({trace.reasoning.engine for trace in evidence.traces if trace.reasoning.engine})
        report.metrics = calculate_shift_metrics(
            sessions=evidence.sessions,
            traces=evidence.traces,
            perception_snapshots=evidence.perception_snapshots,
            shift_transitions=evidence.shift_transitions,
            incidents=evidence.incidents,
            shift_snapshot=evidence.shift_snapshot,
            participant_router=evidence.participant_router,
        )
        report.score_summary = score_shift_metrics(report.metrics, incidents=evidence.incidents)
        report.completed_at = utc_now()
        report.status = ShiftReportStatus.COMPLETED
        report.final_world_state = self.orchestrator.get_world_state()
        report.final_shift_supervisor = evidence.shift_snapshot
        report.final_incidents = evidence.incidents

        grounding_sources = self._grounding_sources(evidence.traces)
        return self.report_store.save(
            report,
            sessions=evidence.sessions,
            traces=evidence.traces,
            telemetry_log=self.edge_gateway.get_telemetry_log(),
            command_history=self.edge_gateway.get_command_history(),
            perception_snapshots={"items": evidence.perception_snapshots},
            world_model_transitions=self.orchestrator.list_world_model_transitions(limit=5000),
            shift_transitions={"items": evidence.shift_transitions},
            incidents=evidence.incidents,
            incident_timeline=self.orchestrator.list_incident_timeline(limit=5000),
            executive_decisions=self.orchestrator.list_executive_decisions(limit=5000),
            grounding_sources=grounding_sources,
        )

    def _ordered_steps(
        self,
        definition: ShiftSimulationDefinition,
    ) -> list[ShiftSimulationStepDefinition]:
        def scheduled_at(step: ShiftSimulationStepDefinition):
            if step.at is not None:
                return step.at
            assert definition.start_at is not None
            return definition.start_at + timedelta(seconds=step.offset_seconds or 0.0)

        return sorted(definition.steps, key=scheduled_at)

    def _run_step(
        self,
        *,
        definition: ShiftSimulationDefinition,
        step: ShiftSimulationStepDefinition,
    ) -> ShiftSimulationStepRecord:
        scheduled_at = self._scheduled_at(definition, step)
        if step.action_type == ShiftSimulationStepActionType.SENSOR_EVENT:
            return self._run_sensor_event(step=step, scheduled_at=scheduled_at)
        if step.action_type == ShiftSimulationStepActionType.SPEECH_TURN:
            return self._run_speech_turn(step=step, scheduled_at=scheduled_at)
        if step.action_type == ShiftSimulationStepActionType.SHIFT_TICK:
            return self._run_shift_tick(step=step, scheduled_at=scheduled_at)
        return self._run_incident_action(step=step, scheduled_at=scheduled_at)

    def _run_sensor_event(
        self,
        *,
        step: ShiftSimulationStepDefinition,
        scheduled_at,
    ) -> ShiftSimulationStepRecord:
        start = perf_counter()
        payload = dict(step.payload)
        if step.participant_id and "participant_id" not in payload:
            payload["participant_id"] = step.participant_id
            payload.setdefault("participant_ids", [step.participant_id])
        sim_result = self.edge_gateway.simulate_event(
            SimulatedSensorEventRequest(
                event_type=step.event_type or "person_detected",
                payload=payload,
                session_id=step.session_id,
                source="pilot_shift_simulator",
                timestamp=scheduled_at,
            )
        )
        response = self.orchestrator.handle_event(sim_result.event)
        return self._interaction_record(
            step=step,
            scheduled_at=scheduled_at,
            response=response,
            event=sim_result.event,
            latency_ms=round((perf_counter() - start) * 1000.0, 2),
        )

    def _run_speech_turn(
        self,
        *,
        step: ShiftSimulationStepDefinition,
        scheduled_at,
    ) -> ShiftSimulationStepRecord:
        start = perf_counter()
        payload = {"text": step.input_text or "", **step.payload}
        if step.participant_id:
            payload.setdefault("participant_id", step.participant_id)
        event = RobotEvent(
            event_type="speech_transcript",
            session_id=step.session_id,
            source="pilot_shift_simulator",
            timestamp=scheduled_at,
            payload=payload,
        )
        response = self.orchestrator.handle_event(event)
        return self._interaction_record(
            step=step,
            scheduled_at=scheduled_at,
            response=response,
            event=event,
            latency_ms=round((perf_counter() - start) * 1000.0, 2),
        )

    def _run_shift_tick(
        self,
        *,
        step: ShiftSimulationStepDefinition,
        scheduled_at,
    ) -> ShiftSimulationStepRecord:
        start = perf_counter()
        telemetry = self.edge_gateway.get_telemetry()
        heartbeat = self.edge_gateway.get_heartbeat()
        event = self.orchestrator.build_shift_tick_event(
            session_id=step.session_id,
            timestamp=scheduled_at,
            source="pilot_shift_simulator",
            telemetry=telemetry,
            heartbeat=heartbeat,
            transport_state=self.edge_gateway.transport_state(),
            transport_error=self.edge_gateway.last_transport_error(),
        )
        event.payload.update(step.payload)
        response = self.orchestrator.handle_event(event)
        return self._interaction_record(
            step=step,
            scheduled_at=scheduled_at,
            response=response,
            event=event,
            latency_ms=round((perf_counter() - start) * 1000.0, 2),
        )

    def _run_incident_action(
        self,
        *,
        step: ShiftSimulationStepDefinition,
        scheduled_at,
    ) -> ShiftSimulationStepRecord:
        ticket = self._resolve_ticket(step.ticket_id)
        if step.action_type == ShiftSimulationStepActionType.INCIDENT_ACKNOWLEDGE:
            ticket = self.orchestrator.acknowledge_incident(
                ticket.ticket_id,
                IncidentAcknowledgeRequest(
                    operator_name=step.operator_name or "operator",
                    note=step.note,
                ),
            )
        elif step.action_type == ShiftSimulationStepActionType.INCIDENT_ASSIGN:
            ticket = self.orchestrator.assign_incident(
                ticket.ticket_id,
                IncidentAssignRequest(
                    assignee_name=step.assignee_name or "operator",
                    author=step.operator_name or "operator",
                    note=step.note,
                ),
            )
        elif step.action_type == ShiftSimulationStepActionType.INCIDENT_NOTE:
            ticket = self.orchestrator.add_incident_note(
                ticket.ticket_id,
                IncidentNoteRequest(
                    text=step.note or "operator_note_added",
                    author=step.operator_name or "operator",
                ),
            )
        elif step.action_type == ShiftSimulationStepActionType.INCIDENT_RESOLVE:
            outcome = str(step.payload.get("outcome") or IncidentResolutionOutcome.STAFF_ASSISTED.value)
            ticket = self.orchestrator.resolve_incident(
                ticket.ticket_id,
                IncidentResolveRequest(
                    outcome=IncidentResolutionOutcome(outcome),
                    author=step.operator_name or "operator",
                    note=step.note,
                ),
            )
        else:
            raise ValueError(f"unsupported_shift_step_action:{step.action_type.value}")
        return ShiftSimulationStepRecord(
            step_id=step.step_id,
            label=step.label,
            action_type=step.action_type,
            scheduled_at=scheduled_at,
            completed_at=scheduled_at,
            session_id=ticket.session_id,
            participant_id=ticket.participant_id,
            telemetry=self.edge_gateway.get_telemetry(),
            heartbeat=self.edge_gateway.get_heartbeat(),
            incident_ticket=ticket,
            success=True,
            outcome=ticket.current_status.value,
            latency_ms=0.0,
            shift_state=self.orchestrator.get_shift_supervisor().state,
            note=step.note,
        )

    def _interaction_record(
        self,
        *,
        step: ShiftSimulationStepDefinition,
        scheduled_at,
        response: CommandBatch,
        event: RobotEvent,
        latency_ms: float,
    ) -> ShiftSimulationStepRecord:
        trace = self.orchestrator.get_trace(response.trace_id) if response.trace_id else None
        command_acks = [self.edge_gateway.apply_command(command) for command in response.commands]
        telemetry = self.edge_gateway.get_telemetry()
        heartbeat = self.edge_gateway.get_heartbeat()
        return ShiftSimulationStepRecord(
            step_id=step.step_id,
            label=step.label,
            action_type=step.action_type,
            scheduled_at=scheduled_at,
            completed_at=scheduled_at,
            session_id=response.session_id,
            participant_id=str((trace.event.payload.get("participant_id") if trace is not None else event.payload.get("participant_id")) or "").strip() or None,
            event=trace.event if trace is not None else event,
            response=response,
            command_acks=command_acks,
            telemetry=telemetry,
            heartbeat=heartbeat,
            incident_ticket=trace.reasoning.incident_ticket if trace is not None else None,
            success=all(ack.accepted for ack in command_acks),
            outcome=self._derive_outcome(trace, command_acks, heartbeat).value,
            latency_ms=latency_ms,
            trace_id=trace.trace_id if trace is not None else response.trace_id,
            shift_state=(
                trace.reasoning.shift_supervisor.state
                if trace is not None and trace.reasoning.shift_supervisor is not None
                else self.orchestrator.get_shift_supervisor().state
            ),
            note=step.note,
        )

    def _resolve_ticket(self, ticket_id: str | None) -> IncidentTicketRecord:
        if ticket_id:
            ticket = self.orchestrator.get_incident(ticket_id)
            if ticket is None:
                raise KeyError(ticket_id)
            return ticket
        open_tickets = self.orchestrator.list_incidents(scope=IncidentListScope.OPEN, limit=10).items
        if not open_tickets:
            raise ValueError("shift_simulation_incident_step_requires_open_ticket")
        return open_tickets[0]

    def _scheduled_at(self, definition: ShiftSimulationDefinition, step: ShiftSimulationStepDefinition):
        if step.at is not None:
            return step.at
        assert definition.start_at is not None
        return definition.start_at + timedelta(seconds=step.offset_seconds or 0.0)

    def _grounding_sources(self, traces: list[TraceRecord]) -> list[GroundingSourceRecord]:
        results: list[GroundingSourceRecord] = []
        seen: set[tuple[str, str, str | None, str | None]] = set()
        for trace in traces:
            for source in trace.reasoning.grounding_sources:
                key = (source.source_type.value, source.label, source.source_ref, source.detail)
                if key in seen:
                    continue
                seen.add(key)
                results.append(source)
        return results

    def _derive_outcome(
        self,
        trace: TraceRecord | None,
        command_acks: list[CommandAck],
        heartbeat,
    ) -> TraceOutcome:
        if any(ack.status == CommandAckStatus.TRANSPORT_ERROR for ack in command_acks):
            return TraceOutcome.ERROR
        if heartbeat.safe_idle_active:
            return TraceOutcome.SAFE_FALLBACK
        if any(not ack.accepted for ack in command_acks):
            return TraceOutcome.ERROR
        if trace is not None:
            return trace.outcome
        return TraceOutcome.OK


def load_shift_definition(path: str | Path) -> ShiftSimulationDefinition:
    fixture_path = Path(path)
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    definition = ShiftSimulationDefinition.model_validate(payload)
    definition.fixture_path = str(fixture_path)
    return definition


def default_shift_fixture_path(settings: Settings | None = None) -> Path:
    resolved_settings = settings or get_settings()
    return Path(resolved_settings.pilot_shift_fixture_dir) / DEFAULT_FIXTURE_NAME


def build_inprocess_shift_simulator(
    *,
    settings: Settings | None = None,
) -> PilotShiftSimulator:
    runtime_settings = settings or get_settings()
    orchestrator = BrainOrchestrator(settings=runtime_settings, store_path=runtime_settings.brain_store_path)
    return PilotShiftSimulator(
        settings=runtime_settings,
        orchestrator=orchestrator,
        edge_gateway=build_inprocess_embodiment_gateway(runtime_settings),
        report_store=ShiftReportStore(runtime_settings.shift_report_dir),
    )


def run_shift_fixture(
    *,
    settings: Settings | None = None,
    fixture_path: str | Path | None = None,
    reset_runtime_first: bool = True,
) -> ShiftReportRecord:
    base_settings = settings or get_settings()
    definition = load_shift_definition(fixture_path or default_shift_fixture_path(base_settings))
    runtime_settings = (
        Settings(
            **{
                **base_settings.model_dump(),
                "venue_content_dir": definition.venue_content_dir or base_settings.venue_content_dir,
                "pilot_site": definition.site_name or base_settings.pilot_site,
            }
        )
        if definition.venue_content_dir
        else base_settings
    )
    simulator = build_inprocess_shift_simulator(settings=runtime_settings)
    return simulator.run(definition, reset_runtime_first=reset_runtime_first)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "fixture",
        nargs="?",
        help="Path to a pilot-day simulation JSON file. Defaults to the built-in community-center fixture.",
    )
    parser.add_argument("--no-reset", action="store_true", help="Do not reset brain and edge state before the run.")
    args = parser.parse_args()

    report = run_shift_fixture(
        fixture_path=args.fixture,
        reset_runtime_first=not args.no_reset,
    )
    print(
        json.dumps(
            {
                "report_id": report.report_id,
                "status": report.status,
                "simulation_name": report.simulation_name,
                "site_name": report.site_name,
                "artifact_dir": report.artifact_dir,
                "score": report.score_summary.score,
                "max_score": report.score_summary.max_score,
                "rating": report.score_summary.rating,
                "metrics": report.metrics.model_dump(mode="json"),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
