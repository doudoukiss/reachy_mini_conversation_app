from __future__ import annotations

from dataclasses import dataclass

from embodied_stack.shared.contracts.action import (
    WorkflowDefinitionRecord,
    WorkflowStepKind,
    WorkflowTriggerKind,
)


@dataclass(frozen=True)
class WorkflowStepTemplate:
    step_key: str
    label: str
    kind: WorkflowStepKind
    tool_name: str | None = None
    retry_budget: int = 0


WORKFLOW_DEFINITIONS: dict[str, WorkflowDefinitionRecord] = {
    "capture_note_and_reminder": WorkflowDefinitionRecord(
        workflow_id="capture_note_and_reminder",
        label="Capture Note And Reminder",
        description="Create a local note and a local reminder from structured user input.",
        version="1.0",
        supported_triggers=[WorkflowTriggerKind.USER_REQUEST, WorkflowTriggerKind.OPERATOR_LAUNCH],
        proactive_capable=False,
        notes=["local_only", "no_browser"],
    ),
    "morning_briefing": WorkflowDefinitionRecord(
        workflow_id="morning_briefing",
        label="Morning Briefing",
        description="Gather reminders, memory context, calendar context, and an optional public page summary.",
        version="1.0",
        supported_triggers=[
            WorkflowTriggerKind.USER_REQUEST,
            WorkflowTriggerKind.OPERATOR_LAUNCH,
            WorkflowTriggerKind.DAILY_DIGEST,
            WorkflowTriggerKind.VENUE_SCHEDULED_PROMPT,
        ],
        proactive_capable=True,
        notes=["read_first", "optional_browser"],
    ),
    "event_lookup_and_open_page": WorkflowDefinitionRecord(
        workflow_id="event_lookup_and_open_page",
        label="Event Lookup And Open Page",
        description="Resolve an event page, open it in the bounded browser runtime, and capture a summary.",
        version="1.0",
        supported_triggers=[
            WorkflowTriggerKind.USER_REQUEST,
            WorkflowTriggerKind.OPERATOR_LAUNCH,
            WorkflowTriggerKind.EVENT_START_WINDOW,
            WorkflowTriggerKind.VENUE_SCHEDULED_PROMPT,
        ],
        proactive_capable=True,
        notes=["browser_runtime", "approval_aware"],
    ),
    "reminder_due_follow_up": WorkflowDefinitionRecord(
        workflow_id="reminder_due_follow_up",
        label="Reminder Due Follow Up",
        description="Build a bounded reminder follow-up summary when an open reminder becomes due.",
        version="1.0",
        supported_triggers=[
            WorkflowTriggerKind.USER_REQUEST,
            WorkflowTriggerKind.OPERATOR_LAUNCH,
            WorkflowTriggerKind.DUE_REMINDER,
        ],
        proactive_capable=True,
        notes=["read_first", "due_reminder"],
    ),
}


WORKFLOW_STEPS: dict[str, tuple[WorkflowStepTemplate, ...]] = {
    "capture_note_and_reminder": (
        WorkflowStepTemplate("validate_inputs", "Validate Inputs", WorkflowStepKind.DETERMINISTIC_CHECK),
        WorkflowStepTemplate(
            "create_note",
            "Create Note",
            WorkflowStepKind.CONNECTOR_ACTION,
            tool_name="create_note",
            retry_budget=0,
        ),
        WorkflowStepTemplate(
            "create_reminder",
            "Create Reminder",
            WorkflowStepKind.CONNECTOR_ACTION,
            tool_name="create_reminder",
            retry_budget=0,
        ),
        WorkflowStepTemplate("write_summary", "Write Summary", WorkflowStepKind.SUMMARY_ARTIFACT),
    ),
    "morning_briefing": (
        WorkflowStepTemplate("collect_context", "Collect Context", WorkflowStepKind.DETERMINISTIC_CHECK),
        WorkflowStepTemplate(
            "open_page",
            "Open Optional Page",
            WorkflowStepKind.CONNECTOR_ACTION,
            tool_name="browser_task",
            retry_budget=1,
        ),
        WorkflowStepTemplate(
            "capture_snapshot",
            "Capture Snapshot",
            WorkflowStepKind.CONNECTOR_ACTION,
            tool_name="browser_task",
            retry_budget=1,
        ),
        WorkflowStepTemplate("write_summary", "Write Summary", WorkflowStepKind.SUMMARY_ARTIFACT),
    ),
    "event_lookup_and_open_page": (
        WorkflowStepTemplate("resolve_event_page", "Resolve Event Page", WorkflowStepKind.DETERMINISTIC_CHECK),
        WorkflowStepTemplate(
            "open_page",
            "Open Page",
            WorkflowStepKind.CONNECTOR_ACTION,
            tool_name="browser_task",
            retry_budget=1,
        ),
        WorkflowStepTemplate(
            "capture_snapshot",
            "Capture Snapshot",
            WorkflowStepKind.CONNECTOR_ACTION,
            tool_name="browser_task",
            retry_budget=1,
        ),
        WorkflowStepTemplate(
            "follow_up_browser_action",
            "Optional Browser Follow Up",
            WorkflowStepKind.CONNECTOR_ACTION,
            tool_name="browser_task",
            retry_budget=0,
        ),
        WorkflowStepTemplate("write_summary", "Write Summary", WorkflowStepKind.SUMMARY_ARTIFACT),
    ),
    "reminder_due_follow_up": (
        WorkflowStepTemplate("resolve_due_reminder", "Resolve Due Reminder", WorkflowStepKind.DETERMINISTIC_CHECK),
        WorkflowStepTemplate("write_summary", "Write Summary", WorkflowStepKind.SUMMARY_ARTIFACT),
    ),
}


def list_workflow_definitions() -> list[WorkflowDefinitionRecord]:
    return [item.model_copy(deep=True) for item in WORKFLOW_DEFINITIONS.values()]


def get_workflow_definition(workflow_id: str) -> WorkflowDefinitionRecord | None:
    record = WORKFLOW_DEFINITIONS.get(workflow_id)
    return record.model_copy(deep=True) if record is not None else None


def get_workflow_steps(workflow_id: str) -> tuple[WorkflowStepTemplate, ...]:
    return WORKFLOW_STEPS.get(workflow_id, ())


__all__ = [
    "WorkflowStepTemplate",
    "WORKFLOW_DEFINITIONS",
    "WORKFLOW_STEPS",
    "get_workflow_definition",
    "get_workflow_steps",
    "list_workflow_definitions",
]
