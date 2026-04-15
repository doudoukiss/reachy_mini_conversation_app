from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from embodied_stack.shared.models import (
    ExecutiveDecisionType,
    IncidentListScope,
    IncidentStatus,
    IncidentTicketRecord,
    ParticipantRouterSnapshot,
    PerceptionSnapshotRecord,
    ScorecardCriterion,
    SessionRecord,
    SessionRoutingStatus,
    SessionStatus,
    ShiftMetricsSnapshot,
    ShiftOperatingState,
    ShiftScoreSummary,
    ShiftSupervisorSnapshot,
    ShiftTransitionRecord,
    TraceOutcome,
    TraceRecord,
    utc_now,
)


OPEN_INCIDENT_STATUSES = {
    IncidentStatus.PENDING,
    IncidentStatus.ACKNOWLEDGED,
    IncidentStatus.ASSIGNED,
}

FALLBACK_OUTCOMES = {
    TraceOutcome.FALLBACK_REPLY,
    TraceOutcome.SAFE_FALLBACK,
}


@dataclass
class ShiftEvidenceBundle:
    sessions: list[SessionRecord]
    traces: list[TraceRecord]
    perception_snapshots: list[PerceptionSnapshotRecord]
    shift_transitions: list[ShiftTransitionRecord]
    incidents: list[IncidentTicketRecord]
    shift_snapshot: ShiftSupervisorSnapshot
    participant_router: ParticipantRouterSnapshot | None = None


def collect_shift_evidence(orchestrator, *, limit: int = 5000) -> ShiftEvidenceBundle:
    sessions = [
        session
        for summary in orchestrator.list_sessions().items
        if (session := orchestrator.get_session(summary.session_id)) is not None
    ]
    traces = list(orchestrator.list_traces(limit=limit).items)
    perception_snapshots = list(orchestrator.list_perception_history(limit=limit).items)
    shift_transitions = list(orchestrator.list_shift_transitions(limit=limit).items)
    incidents = list(orchestrator.list_incidents(scope=IncidentListScope.ALL, limit=limit).items)
    return ShiftEvidenceBundle(
        sessions=sessions,
        traces=traces,
        perception_snapshots=perception_snapshots,
        shift_transitions=shift_transitions,
        incidents=incidents,
        shift_snapshot=orchestrator.get_shift_supervisor(),
        participant_router=orchestrator.get_participant_router(),
    )


def calculate_shift_metrics(
    *,
    sessions: list[SessionRecord],
    traces: list[TraceRecord],
    perception_snapshots: list[PerceptionSnapshotRecord],
    shift_transitions: list[ShiftTransitionRecord],
    incidents: list[IncidentTicketRecord],
    shift_snapshot: ShiftSupervisorSnapshot,
    participant_router: ParticipantRouterSnapshot | None = None,
    as_of: datetime | None = None,
) -> ShiftMetricsSnapshot:
    current_time = as_of or _latest_timestamp(
        traces=traces,
        perception_snapshots=perception_snapshots,
        shift_transitions=shift_transitions,
        fallback=shift_snapshot.updated_at,
    )
    ordered_traces = sorted(traces, key=lambda item: item.event.timestamp)
    ordered_transitions = sorted(shift_transitions, key=lambda item: item.created_at)
    speech_traces = [trace for trace in ordered_traces if trace.event.event_type == "speech_transcript"]

    response_latencies = [trace.latency_ms for trace in ordered_traces if trace.latency_ms is not None]
    greeted = sum(
        1
        for trace in ordered_traces
        if any(decision.decision_type == ExecutiveDecisionType.AUTO_GREET for decision in trace.reasoning.executive_decisions)
    )
    unanswered_question_count = sum(
        1
        for trace in speech_traces
        if trace.outcome in FALLBACK_OUTCOMES or trace.reasoning.fallback_used
    )
    fallback_event_count = sum(
        1
        for trace in ordered_traces
        if trace.outcome in FALLBACK_OUTCOMES or trace.reasoning.fallback_used
    )
    limited_awareness_count = sum(1 for snapshot in perception_snapshots if snapshot.limited_awareness)
    active_sessions = [session for session in sessions if session.status != SessionStatus.CLOSED]
    open_incidents = [incident for incident in incidents if incident.current_status in OPEN_INCIDENT_STATUSES]

    shift_started_at = _earliest_timestamp(
        traces=ordered_traces,
        perception_snapshots=perception_snapshots,
        shift_transitions=ordered_transitions,
        sessions=sessions,
        fallback=shift_snapshot.last_transition_at,
    )
    degraded_seconds = _duration_in_state(
        ordered_transitions,
        target_state=ShiftOperatingState.DEGRADED,
        current_state=shift_snapshot.state,
        start_at=shift_started_at,
        end_at=current_time,
    )

    return ShiftMetricsSnapshot(
        shift_started_at=shift_started_at,
        shift_ended_at=current_time,
        current_state=shift_snapshot.state,
        active_session_count=len(active_sessions),
        queued_participant_count=len(participant_router.queued_participants) if participant_router is not None else 0,
        open_incident_count=len(open_incidents),
        visitors_greeted=greeted,
        conversations_started=sum(
            1
            for session in sessions
            if any(turn.user_text for turn in session.transcript)
        ),
        conversations_completed=sum(
            1
            for session in sessions
            if session.status == SessionStatus.CLOSED or session.routing_status == SessionRoutingStatus.COMPLETE
        ),
        escalations_created=len(incidents),
        escalations_resolved=sum(1 for incident in incidents if incident.current_status == IncidentStatus.RESOLVED),
        response_count=len(response_latencies),
        average_response_latency_ms=_average(response_latencies),
        time_spent_degraded_seconds=round(degraded_seconds, 2),
        safe_idle_incident_count=sum(
            1 for transition in ordered_transitions if transition.to_state == ShiftOperatingState.SAFE_IDLE
        ),
        unanswered_question_count=unanswered_question_count,
        fallback_event_count=fallback_event_count,
        fallback_frequency_rate=_rate(fallback_event_count, len(ordered_traces)),
        perception_snapshot_count=len(perception_snapshots),
        perception_limited_awareness_count=limited_awareness_count,
        perception_limited_awareness_rate=_rate(limited_awareness_count, len(perception_snapshots)),
        last_updated_at=current_time,
    )


def score_shift_metrics(
    metrics: ShiftMetricsSnapshot,
    *,
    incidents: list[IncidentTicketRecord],
) -> ShiftScoreSummary:
    conversation_completion_rate = _rate(metrics.conversations_completed, metrics.conversations_started)
    unresolved_incidents = [incident for incident in incidents if incident.current_status in OPEN_INCIDENT_STATUSES]
    criteria = [
        ScorecardCriterion(
            criterion="greeting_coverage",
            passed=(metrics.conversations_started == 0 and metrics.visitors_greeted == 0)
            or metrics.visitors_greeted > 0,
            expected="At least one visitor is greeted when the shift serves live traffic.",
            observed=f"greeted={metrics.visitors_greeted}, conversations_started={metrics.conversations_started}",
        ),
        ScorecardCriterion(
            criterion="conversation_completion_rate",
            passed=metrics.conversations_started == 0 or conversation_completion_rate >= 0.5,
            expected="At least half of started conversations should reach a closed or complete state in the replay.",
            observed=f"{metrics.conversations_completed}/{metrics.conversations_started}",
        ),
        ScorecardCriterion(
            criterion="escalation_followthrough",
            passed=metrics.escalations_created == 0 or not unresolved_incidents,
            expected="Escalations should end resolved or unavailable by the end of the simulated shift.",
            observed=f"created={metrics.escalations_created}, unresolved={len(unresolved_incidents)}",
        ),
        ScorecardCriterion(
            criterion="response_latency",
            passed=metrics.response_count == 0 or metrics.average_response_latency_ms <= 2000.0,
            expected="Average response latency should stay at or below 2000 ms in the pilot replay.",
            observed=f"{metrics.average_response_latency_ms} ms",
        ),
        ScorecardCriterion(
            criterion="perception_awareness_quality",
            passed=metrics.perception_snapshot_count == 0 or metrics.perception_limited_awareness_rate <= 0.5,
            expected="Limited-awareness snapshots should stay below 50 percent of perception observations.",
            observed=(
                f"{metrics.perception_limited_awareness_count}/{metrics.perception_snapshot_count}"
                if metrics.perception_snapshot_count
                else "no_perception_snapshots"
            ),
        ),
        ScorecardCriterion(
            criterion="degraded_recovery",
            passed=metrics.current_state not in {ShiftOperatingState.DEGRADED, ShiftOperatingState.SAFE_IDLE},
            expected="The shift should not end stuck in degraded or safe-idle mode.",
            observed=f"final_state={metrics.current_state.value if metrics.current_state else 'unknown'}",
        ),
    ]
    passed_count = sum(1 for item in criteria if item.passed)
    max_score = float(len(criteria))
    score = float(passed_count)
    ratio = (score / max_score) if max_score else 0.0
    if ratio >= 0.85:
        rating = "strong"
    elif ratio >= 0.6:
        rating = "watch"
    else:
        rating = "needs_attention"
    return ShiftScoreSummary(
        score=score,
        max_score=max_score,
        rating=rating,
        summary_text=f"{passed_count}/{int(max_score)} pilot-shift criteria passed.",
        criteria=criteria,
    )


def _average(values: list[float]) -> float:
    if not values:
        return 0.0
    return round(sum(values) / len(values), 2)


def _rate(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 4)


def _latest_timestamp(
    *,
    traces: list[TraceRecord],
    perception_snapshots: list[PerceptionSnapshotRecord],
    shift_transitions: list[ShiftTransitionRecord],
    fallback: datetime | None = None,
) -> datetime:
    timestamps: list[datetime] = [trace.event.timestamp for trace in traces]
    timestamps.extend(snapshot.created_at for snapshot in perception_snapshots)
    timestamps.extend(transition.created_at for transition in shift_transitions)
    if fallback is not None:
        timestamps.append(fallback)
    return max(timestamps) if timestamps else utc_now()


def _earliest_timestamp(
    *,
    traces: list[TraceRecord],
    perception_snapshots: list[PerceptionSnapshotRecord],
    shift_transitions: list[ShiftTransitionRecord],
    sessions: list[SessionRecord],
    fallback: datetime | None = None,
) -> datetime | None:
    timestamps: list[datetime] = [trace.event.timestamp for trace in traces]
    timestamps.extend(snapshot.created_at for snapshot in perception_snapshots)
    timestamps.extend(transition.created_at for transition in shift_transitions)
    if not timestamps:
        timestamps.extend(session.created_at for session in sessions)
    if fallback is not None:
        timestamps.append(fallback)
    return min(timestamps) if timestamps else None


def _duration_in_state(
    transitions: list[ShiftTransitionRecord],
    *,
    target_state: ShiftOperatingState,
    current_state: ShiftOperatingState,
    start_at: datetime | None,
    end_at: datetime,
) -> float:
    if not transitions:
        if current_state == target_state and start_at is not None:
            return max((end_at - start_at).total_seconds(), 0.0)
        return 0.0

    ordered = sorted(transitions, key=lambda item: item.created_at)
    cursor = start_at or ordered[0].created_at
    in_target_state = ordered[0].from_state == target_state
    total_seconds = 0.0

    for transition in ordered:
        if in_target_state and transition.created_at >= cursor:
            total_seconds += (transition.created_at - cursor).total_seconds()
        cursor = transition.created_at
        in_target_state = transition.to_state == target_state

    if in_target_state and end_at >= cursor:
        total_seconds += (end_at - cursor).total_seconds()
    return total_seconds
