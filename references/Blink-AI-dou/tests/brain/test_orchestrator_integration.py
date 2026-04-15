from __future__ import annotations

from datetime import datetime, timezone

from embodied_stack.shared.contracts import IncidentListScope, PerceptionEventType, RobotEvent, ShiftOperatingState


def test_orchestrator_maintains_trace_world_and_shift_state_across_mixed_events(orchestrator):
    speech = orchestrator.handle_event(
        RobotEvent(
            event_type="speech_transcript",
            session_id="orch-mixed",
            payload={"text": "Where is the quiet room?"},
        )
    )
    telemetry = orchestrator.handle_event(
        RobotEvent(
            event_type="telemetry",
            session_id="orch-mixed",
            payload={"mode": "simulated", "battery_pct": 88.0, "transport_ok": True},
        )
    )
    shift = orchestrator.handle_event(
        orchestrator.build_shift_tick_event(
            session_id="orch-mixed",
            timestamp=datetime(2026, 3, 30, 16, 5, tzinfo=timezone.utc),
        )
    )

    speech_trace = orchestrator.get_trace(speech.trace_id)
    telemetry_trace = orchestrator.get_trace(telemetry.trace_id)
    shift_trace = orchestrator.get_trace(shift.trace_id)
    assert speech_trace is not None
    assert telemetry_trace is not None
    assert shift_trace is not None
    assert speech_trace.event.event_type == "speech_transcript"
    assert telemetry_trace.reasoning.intent == "telemetry_update"
    assert shift_trace.reasoning.shift_supervisor is not None
    assert shift_trace.reasoning.shift_supervisor.state in {
        ShiftOperatingState.READY_IDLE,
        ShiftOperatingState.WAITING_FOR_FOLLOW_UP,
    }

    world_state = orchestrator.get_world_state()
    assert world_state.last_event_type == "shift_autonomy_tick"
    assert world_state.last_trace_id == shift.trace_id
    assert orchestrator.get_shift_supervisor().state == shift_trace.reasoning.shift_supervisor.state


def test_orchestrator_keeps_perception_and_escalation_paths_visible_end_to_end(orchestrator):
    perception = orchestrator.handle_event(
        RobotEvent(
            event_type=PerceptionEventType.SCENE_SUMMARY_UPDATED.value,
            session_id="orch-perception",
            payload={"scene_summary": "One visitor is visible near the front desk.", "limited_awareness": False},
        )
    )
    incident = orchestrator.handle_event(
        RobotEvent(
            event_type="speech_transcript",
            session_id="orch-perception",
            payload={"text": "I need accessibility help finding an accessible route."},
        )
    )

    perception_trace = orchestrator.get_trace(perception.trace_id)
    incident_trace = orchestrator.get_trace(incident.trace_id)
    assert perception_trace is not None
    assert incident_trace is not None
    assert perception_trace.reasoning.intent == "telemetry_update"
    assert incident_trace.reasoning.incident_ticket is not None
    assert incident_trace.reasoning.incident_timeline

    incidents = orchestrator.list_incidents(scope=IncidentListScope.OPEN, session_id="orch-perception").items
    assert len(incidents) == 1
    assert incidents[0].ticket_id == incident_trace.reasoning.incident_ticket.ticket_id

    world_state = orchestrator.get_world_state()
    assert world_state.last_perception_event_type == PerceptionEventType.SCENE_SUMMARY_UPDATED.value
    assert world_state.latest_scene_summary == "One visitor is visible near the front desk."
