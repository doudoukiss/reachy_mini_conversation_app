from __future__ import annotations

from embodied_stack.shared.models import RunPhase, RunStatus


_PHASE_TRANSITIONS: dict[RunPhase, set[RunPhase]] = {
    RunPhase.INSTRUCTION_LOAD: {RunPhase.SKILL_SELECTION, RunPhase.FAILED},
    RunPhase.SKILL_SELECTION: {RunPhase.SUBAGENT_SELECTION, RunPhase.FAILED},
    RunPhase.SUBAGENT_SELECTION: {RunPhase.TOOL_EXECUTION, RunPhase.REPLY_PLANNING, RunPhase.FAILED},
    RunPhase.TOOL_EXECUTION: {RunPhase.TOOL_EXECUTION, RunPhase.REPLY_PLANNING, RunPhase.VALIDATION, RunPhase.FAILED},
    RunPhase.REPLY_PLANNING: {RunPhase.TOOL_EXECUTION, RunPhase.VALIDATION, RunPhase.FAILED},
    RunPhase.VALIDATION: {RunPhase.COMMAND_EMISSION, RunPhase.FAILED},
    RunPhase.COMMAND_EMISSION: {RunPhase.COMPLETED, RunPhase.FAILED},
    RunPhase.COMPLETED: set(),
    RunPhase.FAILED: set(),
}

_STATUS_TRANSITIONS: dict[RunStatus, set[RunStatus]] = {
    RunStatus.RUNNING: {
        RunStatus.RUNNING,
        RunStatus.AWAITING_CONFIRMATION,
        RunStatus.PAUSED,
        RunStatus.COMPLETED,
        RunStatus.ABORTED,
        RunStatus.FAILED,
    },
    RunStatus.AWAITING_CONFIRMATION: {
        RunStatus.AWAITING_CONFIRMATION,
        RunStatus.PAUSED,
        RunStatus.RUNNING,
        RunStatus.ABORTED,
        RunStatus.FAILED,
    },
    RunStatus.PAUSED: {
        RunStatus.PAUSED,
        RunStatus.RUNNING,
        RunStatus.ABORTED,
        RunStatus.FAILED,
    },
    RunStatus.COMPLETED: set(),
    RunStatus.ABORTED: set(),
    RunStatus.FAILED: set(),
}


def assert_phase_transition(current: RunPhase, next_phase: RunPhase) -> None:
    if next_phase == current:
        return
    allowed = _PHASE_TRANSITIONS.get(current, set())
    if next_phase not in allowed:
        raise ValueError(f"invalid_run_phase_transition:{current.value}->{next_phase.value}")


def assert_status_transition(current: RunStatus, next_status: RunStatus) -> None:
    if next_status == current:
        return
    allowed = _STATUS_TRANSITIONS.get(current, set())
    if next_status not in allowed:
        raise ValueError(f"invalid_run_status_transition:{current.value}->{next_status.value}")


def recovery_status_for(status: RunStatus) -> str | None:
    if status == RunStatus.PAUSED:
        return "paused"
    if status == RunStatus.AWAITING_CONFIRMATION:
        return "awaiting_confirmation"
    if status == RunStatus.ABORTED:
        return "aborted"
    return None


__all__ = [
    "assert_phase_transition",
    "assert_status_transition",
    "recovery_status_for",
]
