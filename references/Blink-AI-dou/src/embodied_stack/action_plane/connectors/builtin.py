from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any
from uuid import uuid4

from embodied_stack.action_plane.connectors.browser import build_browser_connector_descriptor
from embodied_stack.action_plane.connectors.base import (
    BaseConnector,
    ConnectorActionError,
    ConnectorExecutionResult,
    ConnectorPreviewResult,
    artifact_for_path,
)
from embodied_stack.brain.memory_policy import MemoryPolicyService
from embodied_stack.persistence import write_json_atomic
from embodied_stack.shared.contracts.action import (
    ActionRequestRecord,
    ActionRiskClass,
    ConnectorDescriptorRecord,
)
from embodied_stack.shared.contracts._common import (
    IncidentTimelineEventType,
    MemoryWriteReasonCode,
    ReminderStatus,
    utc_now,
)
from embodied_stack.shared.contracts.brain import (
    CompanionNoteRecord,
    EpisodicMemoryRecord,
    IncidentReasonCategory,
    IncidentStatus,
    IncidentTicketRecord,
    IncidentTimelineRecord,
    IncidentUrgency,
    ReminderRecord,
    SemanticMemoryRecord,
)


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    return slug or "artifact"


def _require_session(runtime_context: Any):
    session = getattr(runtime_context, "session", None)
    if session is None:
        raise ConnectorActionError("session_required", "session_required_for_connector_action")
    return session


def _memory_store(runtime_context: Any):
    store = getattr(runtime_context, "memory_store", None)
    if store is None:
        raise ConnectorActionError("memory_store_unavailable", "memory_store_unavailable")
    return store


def _reason_code(value: Any, default: MemoryWriteReasonCode) -> MemoryWriteReasonCode:
    if isinstance(value, MemoryWriteReasonCode):
        return value
    if isinstance(value, str) and value:
        try:
            return MemoryWriteReasonCode(value)
        except ValueError:
            return default
    return default


def _text_contains(haystack: str, needle: str) -> bool:
    lowered_haystack = haystack.lower()
    return all(token in lowered_haystack for token in needle.lower().split() if token)


class MemoryLocalConnector(BaseConnector):
    def execute(
        self,
        *,
        action_name: str,
        request: ActionRequestRecord,
        runtime_context: Any,
    ) -> ConnectorExecutionResult:
        store = getattr(runtime_context, "memory_store", None)
        session = _require_session(runtime_context)
        user_memory = getattr(runtime_context, "user_memory", None)
        payload = request.input_payload

        if action_name == "write_memory":
            scope = str(payload.get("scope") or "session")
            key = str(payload.get("key") or "")
            value = str(payload.get("value") or "")
            if store is None:
                if scope == "profile" and user_memory is not None:
                    user_memory.facts[key] = value
                else:
                    session.session_memory[key] = value
                return ConnectorExecutionResult(
                    summary="write_memory",
                    detail="memory_store_unavailable_session_fallback",
                    output_payload={
                        "scope": scope,
                        "key": key,
                        "value": value,
                        "persisted": False,
                    },
                )

            policy = MemoryPolicyService(store)
            if scope == "profile" and user_memory is not None:
                _profile, action = policy.write_profile_fact(
                    user_memory=user_memory,
                    key=key,
                    value=value,
                    tool_name=request.tool_name,
                    reason_code=_reason_code(payload.get("reason_code"), MemoryWriteReasonCode.PROFILE_PREFERENCE),
                    policy_basis="action_plane_memory_local_write_profile",
                )
                resolved_scope = "profile"
            else:
                resolved_scope = "session" if scope == "profile" else scope
                action = policy.write_session_memory(
                    session=session,
                    key=key,
                    value=value,
                    tool_name=request.tool_name,
                    reason_code=_reason_code(payload.get("reason_code"), MemoryWriteReasonCode.SESSION_CONTEXT),
                    policy_basis="action_plane_memory_local_write_session",
                )
            return ConnectorExecutionResult(
                summary="write_memory",
                output_payload={
                    "scope": resolved_scope,
                    "key": key,
                    "value": value,
                    "action_id": action.action_id,
                    "memory_id": action.memory_id,
                    "persisted": True,
                },
            )

        if action_name == "promote_memory":
            if store is None:
                return ConnectorExecutionResult(
                    summary="promote_memory",
                    detail="memory_store_unavailable",
                    output_payload={
                        "scope": str(payload.get("scope") or "semantic"),
                        "promoted": False,
                    },
                )
            policy = MemoryPolicyService(store)
            scope = str(payload.get("scope") or "semantic")
            if scope == "episodic":
                record = EpisodicMemoryRecord(
                    memory_id=f"episodic-{uuid4().hex[:12]}",
                    session_id=session.session_id,
                    user_id=session.user_id,
                    title=str(payload.get("memory_kind") or "fact"),
                    summary=str(payload.get("summary") or ""),
                    topics=[str(payload.get("memory_kind") or "fact")],
                    source_trace_ids=[turn.trace_id for turn in session.transcript if getattr(turn, "trace_id", None)][-3:],
                )
                action = policy.promote_episodic(
                    record,
                    tool_name=request.tool_name,
                    reason_code=_reason_code(payload.get("reason_code"), MemoryWriteReasonCode.CONVERSATION_TOPIC),
                    policy_basis="action_plane_memory_local_promote_episodic",
                )
            else:
                record = SemanticMemoryRecord(
                    memory_id=f"semantic-{uuid4().hex[:12]}",
                    memory_kind=str(payload.get("memory_kind") or "fact"),
                    summary=str(payload.get("summary") or ""),
                    canonical_value=str(payload.get("canonical_value")) if payload.get("canonical_value") is not None else None,
                    session_id=session.session_id,
                    user_id=session.user_id,
                    confidence=0.75,
                    source_trace_ids=[turn.trace_id for turn in session.transcript if getattr(turn, "trace_id", None)][-3:],
                )
                action = policy.promote_semantic(
                    record,
                    tool_name=request.tool_name,
                    reason_code=_reason_code(payload.get("reason_code"), MemoryWriteReasonCode.CONVERSATION_TOPIC),
                    confidence=record.confidence,
                    policy_basis="action_plane_memory_local_promote_semantic",
                )
            return ConnectorExecutionResult(
                summary="promote_memory",
                output_payload={
                    "scope": scope,
                    "memory_id": action.memory_id,
                    "action_id": action.action_id,
                    "promoted": True,
                },
            )

        raise ConnectorActionError("unsupported_action", f"unsupported_memory_action:{action_name}")

    def preview(
        self,
        *,
        action_name: str,
        request: ActionRequestRecord,
        runtime_context: Any,
        reason: str,
    ) -> ConnectorPreviewResult:
        del runtime_context
        payload = request.input_payload
        if action_name == "write_memory":
            return ConnectorPreviewResult(
                summary=reason,
                detail=reason,
                output_payload={
                    "scope": str(payload.get("scope") or "session"),
                    "key": str(payload.get("key") or ""),
                    "value": str(payload.get("value") or ""),
                    "persisted": False,
                },
            )
        if action_name == "promote_memory":
            return ConnectorPreviewResult(
                summary=reason,
                detail=reason,
                output_payload={
                    "scope": str(payload.get("scope") or "semantic"),
                    "promoted": False,
                },
            )
        return super().preview(action_name=action_name, request=request, runtime_context=runtime_context, reason=reason)


class IncidentLocalConnector(BaseConnector):
    def execute(
        self,
        *,
        action_name: str,
        request: ActionRequestRecord,
        runtime_context: Any,
    ) -> ConnectorExecutionResult:
        session = _require_session(runtime_context)
        payload = request.input_payload
        if action_name == "request_operator_help":
            session.status = "escalation_pending"
            session.session_memory["operator_escalation"] = "requested"
            session.current_topic = "operator_handoff"
            store = getattr(runtime_context, "memory_store", None)
            if store is not None:
                store.upsert_session(session)
            return ConnectorExecutionResult(
                summary="operator_requested",
                output_payload={"requested": True, "incident_ticket_id": None, "status": "operator_requested"},
            )

        if action_name == "log_incident":
            store = getattr(runtime_context, "memory_store", None)
            ticket_id = None
            if store is not None:
                ticket = IncidentTicketRecord(
                    session_id=session.session_id,
                    participant_summary=str(payload.get("participant_summary") or ""),
                    reason_category=IncidentReasonCategory.GENERAL_ESCALATION,
                    urgency=IncidentUrgency.NORMAL,
                    current_status=IncidentStatus.PENDING,
                )
                store.upsert_incident_ticket(ticket)
                store.append_incident_timeline(
                    [
                        IncidentTimelineRecord(
                            ticket_id=ticket.ticket_id,
                            session_id=session.session_id,
                            event_type=IncidentTimelineEventType.CREATED,
                            to_status=ticket.current_status,
                            note=str(payload.get("note")) if payload.get("note") else None,
                        )
                    ]
                )
                ticket_id = ticket.ticket_id
            session.active_incident_ticket_id = ticket_id
            session.current_topic = "operator_handoff"
            return ConnectorExecutionResult(
                summary="incident_logged",
                output_payload={"requested": ticket_id is not None, "incident_ticket_id": ticket_id, "status": "pending"},
            )

        raise ConnectorActionError("unsupported_action", f"unsupported_incident_action:{action_name}")

    def preview(
        self,
        *,
        action_name: str,
        request: ActionRequestRecord,
        runtime_context: Any,
        reason: str,
    ) -> ConnectorPreviewResult:
        del runtime_context
        if action_name == "request_operator_help":
            return ConnectorPreviewResult(
                summary=reason,
                detail=reason,
                output_payload={"requested": False, "incident_ticket_id": None, "status": reason},
            )
        if action_name == "log_incident":
            return ConnectorPreviewResult(
                summary=reason,
                detail=reason,
                output_payload={"requested": False, "incident_ticket_id": None, "status": reason},
            )
        return super().preview(action_name=action_name, request=request, runtime_context=runtime_context, reason=reason)


class RemindersLocalConnector(BaseConnector):
    def execute(
        self,
        *,
        action_name: str,
        request: ActionRequestRecord,
        runtime_context: Any,
    ) -> ConnectorExecutionResult:
        store = _memory_store(runtime_context)
        session = _require_session(runtime_context)
        payload = request.input_payload
        if action_name == "create_reminder":
            record = store.upsert_reminder(
                ReminderRecord(
                    session_id=session.session_id,
                    user_id=session.user_id,
                    reminder_text=str(payload.get("reminder_text") or ""),
                    due_at=payload.get("due_at"),
                    status=ReminderStatus.OPEN,
                    reason_code=_reason_code(payload.get("reason_code"), MemoryWriteReasonCode.CONVERSATION_TOPIC),
                    policy_basis="action_plane_reminders_create",
                )
            )
            return ConnectorExecutionResult(
                summary="reminder_created",
                output_payload={
                    "created": True,
                    "reminder_id": record.reminder_id,
                    "reminder_text": record.reminder_text,
                    "due_at": record.due_at.isoformat() if record.due_at is not None else None,
                    "status": record.status.value,
                },
            )

        if action_name == "list_reminders":
            status = str(payload.get("status") or ReminderStatus.OPEN.value)
            items = store.list_reminders(
                session_id=session.session_id,
                user_id=session.user_id,
                status=ReminderStatus(status) if status else None,
                limit=int(payload.get("limit") or 10),
            ).items
            return ConnectorExecutionResult(
                summary=f"reminders={len(items)}",
                output_payload={
                    "reminders": [
                        {
                            "reminder_id": item.reminder_id,
                            "reminder_text": item.reminder_text,
                            "due_at": item.due_at.isoformat() if item.due_at is not None else None,
                            "due_state": item.status.value,
                        }
                        for item in items
                    ],
                    "due_count": sum(1 for item in items if item.status == ReminderStatus.OPEN),
                },
            )

        if action_name == "mark_reminder_done":
            reminder_id = str(payload.get("reminder_id") or "")
            record = store.get_reminder(reminder_id)
            if record is None:
                raise ConnectorActionError("reminder_not_found", "reminder_not_found")
            record.status = ReminderStatus(str(payload.get("status") or ReminderStatus.DISMISSED.value))
            record.updated_at = utc_now()
            saved = store.upsert_reminder(record)
            return ConnectorExecutionResult(
                summary="reminder_updated",
                output_payload={
                    "updated": True,
                    "reminder_id": saved.reminder_id,
                    "status": saved.status.value,
                    "reminder_text": saved.reminder_text,
                },
            )

        raise ConnectorActionError("unsupported_action", f"unsupported_reminder_action:{action_name}")

    def preview(
        self,
        *,
        action_name: str,
        request: ActionRequestRecord,
        runtime_context: Any,
        reason: str,
    ) -> ConnectorPreviewResult:
        del runtime_context
        payload = request.input_payload
        if action_name == "create_reminder":
            return ConnectorPreviewResult(
                summary=reason,
                detail=reason,
                output_payload={
                    "created": False,
                    "reminder_id": None,
                    "reminder_text": str(payload.get("reminder_text") or ""),
                    "due_at": payload.get("due_at"),
                    "status": reason,
                },
            )
        if action_name == "list_reminders":
            return ConnectorPreviewResult(
                summary=reason,
                detail=reason,
                output_payload={"reminders": [], "due_count": 0},
            )
        if action_name == "mark_reminder_done":
            return ConnectorPreviewResult(
                summary=reason,
                detail=reason,
                output_payload={
                    "updated": False,
                    "reminder_id": str(payload.get("reminder_id") or ""),
                    "status": reason,
                    "reminder_text": None,
                },
            )
        return super().preview(action_name=action_name, request=request, runtime_context=runtime_context, reason=reason)


class NotesLocalConnector(BaseConnector):
    def execute(
        self,
        *,
        action_name: str,
        request: ActionRequestRecord,
        runtime_context: Any,
    ) -> ConnectorExecutionResult:
        store = _memory_store(runtime_context)
        session = _require_session(runtime_context)
        payload = request.input_payload

        if action_name == "create_note":
            note = store.upsert_companion_note(
                CompanionNoteRecord(
                    session_id=session.session_id,
                    user_id=session.user_id,
                    title=str(payload.get("title") or "Untitled Note"),
                    content=str(payload.get("content") or ""),
                    tags=[str(item) for item in payload.get("tags", [])],
                    reason_code=_reason_code(payload.get("reason_code"), MemoryWriteReasonCode.CONVERSATION_TOPIC),
                    policy_basis="action_plane_notes_create",
                )
            )
            return ConnectorExecutionResult(
                summary="note_created",
                output_payload={
                    "created": True,
                    "note_id": note.note_id,
                    "title": note.title,
                    "content": note.content,
                    "tags": list(note.tags),
                },
            )

        if action_name == "append_note":
            note_id = str(payload.get("note_id") or "")
            existing = store.get_companion_note(note_id)
            if existing is None:
                raise ConnectorActionError("note_not_found", "note_not_found")
            append_text = str(payload.get("content_append") or "")
            existing.content = f"{existing.content.rstrip()}\n{append_text}".strip()
            existing.updated_at = utc_now()
            updated = store.upsert_companion_note(existing)
            return ConnectorExecutionResult(
                summary="note_updated",
                output_payload={
                    "updated": True,
                    "note_id": updated.note_id,
                    "title": updated.title,
                    "content": updated.content,
                    "tags": list(updated.tags),
                },
            )

        if action_name == "search_notes":
            query = str(payload.get("query") or "").strip()
            items = store.list_companion_notes(
                session_id=session.session_id,
                user_id=session.user_id,
                limit=int(payload.get("limit") or 10),
            ).items
            if query:
                items = [
                    item
                    for item in items
                    if _text_contains(" ".join([item.title, item.content, *item.tags]), query)
                ]
            return ConnectorExecutionResult(
                summary=f"notes={len(items)}",
                output_payload={
                    "notes": [
                        {
                            "note_id": item.note_id,
                            "title": item.title,
                            "content": item.content,
                            "tags": list(item.tags),
                        }
                        for item in items
                    ],
                    "query": query or None,
                },
            )

        raise ConnectorActionError("unsupported_action", f"unsupported_note_action:{action_name}")

    def preview(
        self,
        *,
        action_name: str,
        request: ActionRequestRecord,
        runtime_context: Any,
        reason: str,
    ) -> ConnectorPreviewResult:
        del runtime_context
        payload = request.input_payload
        if action_name == "create_note":
            return ConnectorPreviewResult(
                summary=reason,
                detail=reason,
                output_payload={
                    "created": False,
                    "note_id": None,
                    "title": str(payload.get("title") or "Untitled Note"),
                    "content": str(payload.get("content") or ""),
                    "tags": [str(item) for item in payload.get("tags", [])],
                },
            )
        if action_name == "append_note":
            return ConnectorPreviewResult(
                summary=reason,
                detail=reason,
                output_payload={
                    "updated": False,
                    "note_id": str(payload.get("note_id") or ""),
                    "title": None,
                    "content": None,
                    "tags": [],
                },
            )
        if action_name == "search_notes":
            return ConnectorPreviewResult(
                summary=reason,
                detail=reason,
                output_payload={"notes": [], "query": str(payload.get("query") or "") or None},
            )
        return super().preview(action_name=action_name, request=request, runtime_context=runtime_context, reason=reason)


class LocalFilesConnector(BaseConnector):
    def __init__(
        self,
        descriptor: ConnectorDescriptorRecord,
        *,
        allowed_roots: list[Path],
        stage_dir: Path,
        export_dir: Path,
    ) -> None:
        super().__init__(descriptor)
        self._allowed_roots = [item.resolve() for item in allowed_roots]
        self._stage_dir = stage_dir
        self._export_dir = export_dir

    def _resolve_allowed_file(self, raw_path: str) -> Path:
        candidate = Path(raw_path).expanduser()
        if not candidate.is_absolute():
            candidate = Path.cwd() / candidate
        resolved = candidate.resolve()
        for root in self._allowed_roots:
            try:
                resolved.relative_to(root)
                return resolved
            except ValueError:
                continue
        raise ConnectorActionError("path_outside_allowed_roots", f"path_outside_allowed_roots:{resolved}")

    def execute(
        self,
        *,
        action_name: str,
        request: ActionRequestRecord,
        runtime_context: Any,
    ) -> ConnectorExecutionResult:
        del runtime_context
        payload = request.input_payload

        if action_name == "read_local_file":
            path = self._resolve_allowed_file(str(payload.get("path") or ""))
            content = path.read_text(encoding="utf-8", errors="replace")
            max_chars = int(payload.get("max_chars") or 20000)
            truncated = len(content) > max_chars
            rendered = content[:max_chars]
            return ConnectorExecutionResult(
                summary="file_read",
                output_payload={
                    "path": str(path),
                    "content": rendered,
                    "truncated": truncated,
                    "size_bytes": path.stat().st_size,
                },
                artifacts=[artifact_for_path(kind="source_file", label=path.name, path=path)],
            )

        if action_name == "stage_local_file":
            source = self._resolve_allowed_file(str(payload.get("path") or ""))
            self._stage_dir.mkdir(parents=True, exist_ok=True)
            staged_path = self._stage_dir / f"{utc_now().strftime('%Y%m%dT%H%M%S')}_{source.name}"
            shutil.copy2(source, staged_path)
            return ConnectorExecutionResult(
                summary="file_staged",
                output_payload={
                    "staged": True,
                    "source_path": str(source),
                    "staged_path": str(staged_path),
                },
                artifacts=[artifact_for_path(kind="staged_file", label=staged_path.name, path=staged_path)],
            )

        if action_name == "export_local_bundle":
            raw_paths = payload.get("paths") or []
            if not isinstance(raw_paths, list) or not raw_paths:
                raise ConnectorActionError("bundle_paths_required", "bundle_paths_required")
            label = _slugify(str(payload.get("label") or "export-bundle"))
            bundle_dir = self._export_dir / f"{utc_now().strftime('%Y%m%dT%H%M%S')}_{label}"
            bundle_dir.mkdir(parents=True, exist_ok=True)
            copied: list[dict[str, str]] = []
            for raw_path in raw_paths:
                source = self._resolve_allowed_file(str(raw_path))
                destination = bundle_dir / source.name
                shutil.copy2(source, destination)
                copied.append({"source_path": str(source), "bundle_path": str(destination)})
            manifest_path = bundle_dir / "manifest.json"
            write_json_atomic(manifest_path, {"label": label, "files": copied}, keep_backups=1)
            artifacts = [
                artifact_for_path(kind="bundle_manifest", label="manifest.json", path=manifest_path),
                *[
                    artifact_for_path(kind="bundle_file", label=Path(item["bundle_path"]).name, path=Path(item["bundle_path"]))
                    for item in copied
                ],
            ]
            return ConnectorExecutionResult(
                summary="bundle_exported",
                output_payload={
                    "exported": True,
                    "bundle_dir": str(bundle_dir),
                    "manifest_path": str(manifest_path),
                    "file_count": len(copied),
                    "files": copied,
                },
                artifacts=artifacts,
            )

        raise ConnectorActionError("unsupported_action", f"unsupported_local_file_action:{action_name}")

    def preview(
        self,
        *,
        action_name: str,
        request: ActionRequestRecord,
        runtime_context: Any,
        reason: str,
    ) -> ConnectorPreviewResult:
        del runtime_context
        payload = request.input_payload
        if action_name == "read_local_file":
            return ConnectorPreviewResult(
                summary=reason,
                detail=reason,
                output_payload={
                    "path": str(payload.get("path") or ""),
                    "content": "",
                    "truncated": False,
                    "size_bytes": 0,
                },
            )
        if action_name == "stage_local_file":
            return ConnectorPreviewResult(
                summary=reason,
                detail=reason,
                output_payload={
                    "staged": False,
                    "source_path": str(payload.get("path") or ""),
                    "staged_path": None,
                },
            )
        if action_name == "export_local_bundle":
            return ConnectorPreviewResult(
                summary=reason,
                detail=reason,
                output_payload={
                    "exported": False,
                    "bundle_dir": None,
                    "manifest_path": None,
                    "file_count": 0,
                    "files": [],
                },
            )
        return super().preview(action_name=action_name, request=request, runtime_context=runtime_context, reason=reason)


class CalendarLocalConnector(BaseConnector):
    def __init__(self, descriptor: ConnectorDescriptorRecord, *, draft_dir: Path) -> None:
        super().__init__(descriptor)
        self._draft_dir = draft_dir

    def execute(
        self,
        *,
        action_name: str,
        request: ActionRequestRecord,
        runtime_context: Any,
    ) -> ConnectorExecutionResult:
        payload = request.input_payload
        if action_name == "query_calendar":
            knowledge_tools = getattr(runtime_context, "knowledge_tools", None)
            venue_knowledge = getattr(knowledge_tools, "venue_knowledge", None)
            query = str(payload.get("query") or "")
            result = venue_knowledge.lookup_events(query) if venue_knowledge is not None else None
            if result is None:
                return ConnectorExecutionResult(
                    summary="calendar_no_match",
                    output_payload={"matched": False, "answers": []},
                )
            return ConnectorExecutionResult(
                summary="calendar_match",
                output_payload={
                    "matched": True,
                    "answers": [
                        {
                            "tool_name": request.tool_name,
                            "answer_text": result.answer_text,
                            "source_refs": list(result.metadata.get("source_refs", [])),
                            "notes": list(result.notes),
                        }
                    ],
                },
            )

        if action_name == "draft_calendar_event":
            self._draft_dir.mkdir(parents=True, exist_ok=True)
            title = str(payload.get("title") or "Untitled event")
            draft_path = self._draft_dir / f"{utc_now().strftime('%Y%m%dT%H%M%S')}_{_slugify(title)}.json"
            draft = {
                "title": title,
                "start_at": payload.get("start_at"),
                "end_at": payload.get("end_at"),
                "location": payload.get("location"),
                "description": payload.get("description"),
                "created_at": utc_now().isoformat(),
                "status": "draft_only_local_artifact",
            }
            write_json_atomic(draft_path, draft, keep_backups=1)
            return ConnectorExecutionResult(
                summary="calendar_draft_created",
                output_payload={
                    "drafted": True,
                    "draft_path": str(draft_path),
                    "title": title,
                    "start_at": payload.get("start_at"),
                    "end_at": payload.get("end_at"),
                    "location": payload.get("location"),
                    "status": "drafted",
                },
                artifacts=[artifact_for_path(kind="calendar_draft", label=draft_path.name, path=draft_path)],
            )

        raise ConnectorActionError("unsupported_action", f"unsupported_calendar_action:{action_name}")

    def preview(
        self,
        *,
        action_name: str,
        request: ActionRequestRecord,
        runtime_context: Any,
        reason: str,
    ) -> ConnectorPreviewResult:
        del runtime_context
        payload = request.input_payload
        if action_name == "query_calendar":
            return ConnectorPreviewResult(
                summary=reason,
                detail=reason,
                output_payload={"matched": False, "answers": []},
            )
        if action_name == "draft_calendar_event":
            return ConnectorPreviewResult(
                summary=reason,
                detail=reason,
                output_payload={
                    "drafted": False,
                    "draft_path": None,
                    "title": str(payload.get("title") or "Untitled event"),
                    "start_at": payload.get("start_at"),
                    "end_at": payload.get("end_at"),
                    "location": payload.get("location"),
                    "status": reason,
                },
            )
        return super().preview(action_name=action_name, request=request, runtime_context=runtime_context, reason=reason)


class MCPAdapterConnector(BaseConnector):
    def execute(
        self,
        *,
        action_name: str,
        request: ActionRequestRecord,
        runtime_context: Any,
    ) -> ConnectorExecutionResult:
        del action_name, request, runtime_context
        raise ConnectorActionError("connector_unavailable", "mcp_adapter_not_enabled")


def build_default_connector_descriptors(*, settings=None) -> list[ConnectorDescriptorRecord]:
    return [
        ConnectorDescriptorRecord(
            connector_id="memory_local",
            label="Local Memory Store",
            category="local_state",
            transport_kind="in_process",
            supported=True,
            configured=True,
            capability_tags=["memory", "local"],
            supported_actions=["write_memory", "promote_memory"],
            action_risk={
                "write_memory": ActionRiskClass.LOW_RISK_LOCAL_WRITE,
                "promote_memory": ActionRiskClass.LOW_RISK_LOCAL_WRITE,
            },
            dry_run_supported=True,
            notes=["session_and_profile_memory"],
        ),
        ConnectorDescriptorRecord(
            connector_id="incident_local",
            label="Local Incident Store",
            category="operator_handoff",
            transport_kind="in_process",
            supported=True,
            configured=True,
            capability_tags=["incident", "operator"],
            supported_actions=["request_operator_help", "log_incident"],
            action_risk={
                "request_operator_help": ActionRiskClass.OPERATOR_SENSITIVE_WRITE,
                "log_incident": ActionRiskClass.OPERATOR_SENSITIVE_WRITE,
            },
            dry_run_supported=True,
            notes=["incident_ticket_local_state"],
        ),
        build_browser_connector_descriptor(settings),
        ConnectorDescriptorRecord(
            connector_id="reminders_local",
            label="Local Reminders",
            category="memory",
            transport_kind="in_process",
            supported=True,
            configured=True,
            capability_tags=["reminders", "local"],
            supported_actions=["create_reminder", "list_reminders", "mark_reminder_done"],
            action_risk={
                "create_reminder": ActionRiskClass.LOW_RISK_LOCAL_WRITE,
                "list_reminders": ActionRiskClass.READ_ONLY,
                "mark_reminder_done": ActionRiskClass.LOW_RISK_LOCAL_WRITE,
            },
            dry_run_supported=True,
        ),
        ConnectorDescriptorRecord(
            connector_id="notes_local",
            label="Local Notes",
            category="memory",
            transport_kind="in_process",
            supported=True,
            configured=True,
            capability_tags=["notes", "local"],
            supported_actions=["create_note", "append_note", "search_notes"],
            action_risk={
                "create_note": ActionRiskClass.LOW_RISK_LOCAL_WRITE,
                "append_note": ActionRiskClass.LOW_RISK_LOCAL_WRITE,
                "search_notes": ActionRiskClass.READ_ONLY,
            },
            dry_run_supported=True,
        ),
        ConnectorDescriptorRecord(
            connector_id="local_files",
            label="Local Files",
            category="filesystem",
            transport_kind="local_fs",
            supported=True,
            configured=True,
            capability_tags=["files", "local"],
            supported_actions=["read_local_file", "stage_local_file", "export_local_bundle"],
            action_risk={
                "read_local_file": ActionRiskClass.READ_ONLY,
                "stage_local_file": ActionRiskClass.LOW_RISK_LOCAL_WRITE,
                "export_local_bundle": ActionRiskClass.LOW_RISK_LOCAL_WRITE,
            },
            dry_run_supported=True,
        ),
        ConnectorDescriptorRecord(
            connector_id="calendar_local",
            label="Local Calendar Drafts",
            category="calendar",
            transport_kind="in_process",
            supported=True,
            configured=True,
            capability_tags=["calendar", "venue"],
            supported_actions=["query_calendar", "draft_calendar_event"],
            action_risk={
                "query_calendar": ActionRiskClass.READ_ONLY,
                "draft_calendar_event": ActionRiskClass.LOW_RISK_LOCAL_WRITE,
            },
            dry_run_supported=True,
        ),
        ConnectorDescriptorRecord(
            connector_id="mcp_adapter",
            label="MCP Adapter",
            category="adapter",
            transport_kind="disabled",
            supported=False,
            configured=False,
            capability_tags=["mcp", "disabled"],
            supported_actions=[],
            action_risk={},
            dry_run_supported=False,
            dry_run_only=True,
            notes=["stage_b_interface_only"],
        ),
    ]


__all__ = [
    "BrowserRuntimeConnector",
    "CalendarLocalConnector",
    "IncidentLocalConnector",
    "LocalFilesConnector",
    "MCPAdapterConnector",
    "MemoryLocalConnector",
    "NotesLocalConnector",
    "RemindersLocalConnector",
    "build_default_connector_descriptors",
]
