from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from embodied_stack.shared.contracts import BrowserRequestedAction
from embodied_stack.shared.models import ToolCapabilityState, ToolResultStatus


@dataclass(frozen=True)
class ACICapability:
    name: str
    description: str


ACI_CAPABILITIES: dict[str, ACICapability] = {
    "camera_capture": ACICapability("camera_capture", "Capture or summarize the current scene."),
    "microphone_input": ACICapability("microphone_input", "Accept or transcribe local audio input."),
    "speech_output": ACICapability("speech_output", "Emit or control spoken output."),
    "memory_read": ACICapability("memory_read", "Read user, session, reminder, or digest memory."),
    "memory_write": ACICapability("memory_write", "Write or promote local memory state."),
    "local_files": ACICapability("local_files", "Inspect local notes, digests, reminders, and file-backed context."),
    "browser_task": ACICapability("browser_task", "Run an optional local browser task when configured."),
    "workflow_runtime": ACICapability("workflow_runtime", "Run bounded, resumable local workflows through the Action Plane."),
    "operator_status": ACICapability("operator_status", "Surface handoff, confirmation, and operator-visible state."),
    "system_health": ACICapability("system_health", "Inspect runtime, backend, and device health."),
    "body_preview": ACICapability("body_preview", "Preview semantic body actions without executing them."),
    "body_command": ACICapability("body_command", "Issue bounded semantic body commands."),
}


TOOL_CAPABILITY_MAP: dict[str, str] = {
    "device_health_snapshot": "system_health",
    "memory_status": "memory_read",
    "system_health": "system_health",
    "search_memory": "memory_read",
    "search_venue_knowledge": "local_files",
    "query_calendar": "local_files",
    "query_local_files": "local_files",
    "local_notes": "local_files",
    "personal_reminders": "memory_read",
    "today_context": "memory_read",
    "recent_session_digest": "memory_read",
    "body_preview": "body_preview",
    "capture_scene": "camera_capture",
    "world_model_runtime": "system_health",
    "transcribe_audio": "microphone_input",
    "speak_text": "speech_output",
    "interrupt_speech": "speech_output",
    "set_listening_state": "microphone_input",
    "write_memory": "memory_write",
    "promote_memory": "memory_write",
    "body_command": "body_command",
    "body_safe_idle": "body_command",
    "request_operator_help": "operator_status",
    "log_incident": "operator_status",
    "require_confirmation": "operator_status",
    "browser_task": "browser_task",
    "start_workflow": "workflow_runtime",
}


def capability_for_tool(tool_name: str) -> str:
    return TOOL_CAPABILITY_MAP.get(tool_name, "system_health")


def normalize_result_status(
    *,
    success: bool,
    failure_mode: str | None = None,
    unsupported: bool = False,
    unconfigured: bool = False,
    blocked: bool = False,
) -> ToolResultStatus:
    if blocked:
        return ToolResultStatus.BLOCKED
    if unsupported:
        return ToolResultStatus.UNSUPPORTED
    if unconfigured:
        return ToolResultStatus.UNCONFIGURED
    if success:
        return ToolResultStatus.OK
    if failure_mode == "tool_input_invalid":
        return ToolResultStatus.INVALID_INPUT
    if failure_mode == "tool_output_invalid":
        return ToolResultStatus.INVALID_OUTPUT
    return ToolResultStatus.ERROR


def normalize_capability_state(
    *,
    success: bool,
    fallback_used: bool = False,
    unsupported: bool = False,
    unconfigured: bool = False,
    blocked: bool = False,
    unavailable: bool = False,
) -> ToolCapabilityState:
    if blocked:
        return ToolCapabilityState.BLOCKED
    if unsupported:
        return ToolCapabilityState.UNSUPPORTED
    if unconfigured:
        return ToolCapabilityState.UNCONFIGURED
    if fallback_used:
        return ToolCapabilityState.FALLBACK_ACTIVE
    if unavailable:
        return ToolCapabilityState.UNAVAILABLE
    if success:
        return ToolCapabilityState.AVAILABLE
    return ToolCapabilityState.DEGRADED


def default_confidence(output_model: BaseModel | None) -> float | None:
    if output_model is None:
        return None
    for field_name in ("confidence", "confidence_score"):
        value = getattr(output_model, field_name, None)
        if isinstance(value, (int, float)):
            return float(value)
    return None


def default_provenance(output_model: BaseModel | None) -> list[str]:
    if output_model is None:
        return []
    provenance: list[str] = []
    if hasattr(output_model, "source_refs"):
        refs = getattr(output_model, "source_refs", None)
        if isinstance(refs, list):
            provenance.extend(str(item) for item in refs if item)
    if hasattr(output_model, "notes"):
        notes = getattr(output_model, "notes", None)
        if isinstance(notes, list):
            provenance.extend(f"note:{item}" for item in notes if item)
    return provenance[:12]


def unsupported_browser_output(
    query: str | None = None,
    requested_action: BrowserRequestedAction | str | None = None,
) -> dict[str, Any]:
    return {
        "task": query,
        "requested_action": requested_action,
        "supported": False,
        "configured": False,
        "status": "unsupported",
        "detail": "browser_task_not_configured",
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


__all__ = [
    "ACI_CAPABILITIES",
    "ACICapability",
    "TOOL_CAPABILITY_MAP",
    "capability_for_tool",
    "default_confidence",
    "default_provenance",
    "normalize_capability_state",
    "normalize_result_status",
    "unsupported_browser_output",
]
