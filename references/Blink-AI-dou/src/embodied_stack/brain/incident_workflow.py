from __future__ import annotations

from dataclasses import dataclass, field

from embodied_stack.brain.memory import MemoryStore
from embodied_stack.brain.venue_knowledge import VenueKnowledge, VenueStaffContact
from embodied_stack.shared.models import (
    ExecutiveDecisionRecord,
    ExecutiveDecisionType,
    IncidentAcknowledgeRequest,
    IncidentAssignRequest,
    IncidentListScope,
    IncidentNoteRecord,
    IncidentNoteRequest,
    IncidentReasonCategory,
    IncidentResolveRequest,
    IncidentResolutionOutcome,
    IncidentStaffSuggestion,
    IncidentStatus,
    IncidentTicketRecord,
    IncidentTimelineEventType,
    IncidentTimelineRecord,
    IncidentUrgency,
    ReasoningTrace,
    RobotEvent,
    SessionRecord,
    SessionStatus,
    VenueFallbackScenario,
    utc_now,
)


OPEN_INCIDENT_STATUSES = {
    IncidentStatus.PENDING,
    IncidentStatus.ACKNOWLEDGED,
    IncidentStatus.ASSIGNED,
}


@dataclass
class IncidentReplyPlan:
    intent: str
    reply_text: str
    notes: list[str] = field(default_factory=list)


@dataclass
class IncidentSyncResult:
    ticket: IncidentTicketRecord | None = None
    timeline: list[IncidentTimelineRecord] = field(default_factory=list)
    reply_text: str | None = None
    notes: list[str] = field(default_factory=list)


class IncidentWorkflow:
    """Local-first escalation ticket workflow with deterministic routing and audit history."""

    def __init__(
        self,
        *,
        memory: MemoryStore,
        venue_knowledge: VenueKnowledge,
    ) -> None:
        self.memory = memory
        self.venue_knowledge = venue_knowledge

    def maybe_build_status_reply(
        self,
        *,
        session: SessionRecord,
        text: str,
    ) -> IncidentReplyPlan | None:
        ticket = self._latest_ticket_for_session(session.session_id)
        if ticket is None:
            return None
        if not self._looks_like_status_follow_up(text=text, session=session):
            return None
        return IncidentReplyPlan(
            intent=self._intent_for_status(ticket.current_status),
            reply_text=self._status_reply(ticket),
            notes=[f"incident_status_reply:{ticket.current_status.value}"],
        )

    def sync_from_decisions(
        self,
        *,
        session: SessionRecord,
        event: RobotEvent,
        reasoning: ReasoningTrace,
        decisions: list[ExecutiveDecisionRecord],
        trace_id: str,
    ) -> IncidentSyncResult:
        if not self._should_open_ticket(reasoning=reasoning, decisions=decisions):
            return IncidentSyncResult()

        existing = self._open_ticket_for_session(session.session_id)
        if existing is not None:
            self._apply_ticket_to_session(session, existing)
            existing.last_trace_id = trace_id
            persisted = self.memory.upsert_incident_ticket(existing)
            return IncidentSyncResult(
                ticket=persisted,
                reply_text=self._status_reply(persisted),
                notes=["incident_ticket_reused"],
            )

        ticket = self._build_ticket(
            session=session,
            event=event,
            reasoning=reasoning,
            decisions=decisions,
            trace_id=trace_id,
        )
        timeline = [
            IncidentTimelineRecord(
                ticket_id=ticket.ticket_id,
                session_id=ticket.session_id,
                event_type=IncidentTimelineEventType.CREATED,
                to_status=ticket.current_status,
                actor="blink_ai",
                note=ticket.last_status_note,
                trace_id=trace_id,
                metadata={
                    "reason_category": ticket.reason_category.value,
                    "urgency": ticket.urgency.value,
                    "participant_id": ticket.participant_id,
                },
            )
        ]
        persisted = self.memory.upsert_incident_ticket(ticket)
        self.memory.append_incident_timeline(timeline)
        self._apply_ticket_to_session(session, persisted)
        return IncidentSyncResult(
            ticket=persisted,
            timeline=timeline,
            reply_text=self._status_reply(persisted),
            notes=[f"incident_ticket_created:{persisted.ticket_id}"],
        )

    def acknowledge_ticket(
        self,
        ticket_id: str,
        request: IncidentAcknowledgeRequest,
    ) -> tuple[IncidentTicketRecord, list[IncidentTimelineRecord]]:
        ticket = self._require_ticket(ticket_id)
        now = utc_now()
        from_status = ticket.current_status
        if ticket.current_status == IncidentStatus.PENDING:
            ticket.current_status = IncidentStatus.ACKNOWLEDGED
        ticket.acknowledged_at = ticket.acknowledged_at or now
        ticket.last_status_note = request.note or f"Acknowledged by {request.operator_name}."
        ticket.updated_at = now
        if request.note:
            ticket.notes.append(IncidentNoteRecord(author=request.operator_name, text=request.note, created_at=now))
        persisted = self.memory.upsert_incident_ticket(ticket)
        timeline = [
            IncidentTimelineRecord(
                ticket_id=ticket.ticket_id,
                session_id=ticket.session_id,
                event_type=IncidentTimelineEventType.ACKNOWLEDGED,
                from_status=from_status,
                to_status=persisted.current_status,
                actor=request.operator_name,
                note=ticket.last_status_note,
                metadata={"operator_name": request.operator_name},
                created_at=now,
            )
        ]
        self.memory.append_incident_timeline(timeline)
        self._sync_session_state_from_ticket(persisted)
        return persisted, timeline

    def assign_ticket(
        self,
        ticket_id: str,
        request: IncidentAssignRequest,
    ) -> tuple[IncidentTicketRecord, list[IncidentTimelineRecord]]:
        ticket = self._require_ticket(ticket_id)
        now = utc_now()
        from_status = ticket.current_status
        ticket.current_status = IncidentStatus.ASSIGNED
        ticket.assigned_to = request.assignee_name
        ticket.acknowledged_at = ticket.acknowledged_at or now
        ticket.assigned_at = now
        ticket.last_status_note = request.note or f"Assigned to {request.assignee_name}."
        ticket.updated_at = now
        if request.note:
            ticket.notes.append(IncidentNoteRecord(author=request.author, text=request.note, created_at=now))
        persisted = self.memory.upsert_incident_ticket(ticket)
        timeline = [
            IncidentTimelineRecord(
                ticket_id=ticket.ticket_id,
                session_id=ticket.session_id,
                event_type=IncidentTimelineEventType.ASSIGNED,
                from_status=from_status,
                to_status=persisted.current_status,
                actor=request.author,
                note=ticket.last_status_note,
                metadata={"assignee_name": request.assignee_name},
                created_at=now,
            )
        ]
        self.memory.append_incident_timeline(timeline)
        self._sync_session_state_from_ticket(persisted)
        return persisted, timeline

    def add_note(
        self,
        ticket_id: str,
        request: IncidentNoteRequest,
    ) -> tuple[IncidentTicketRecord, list[IncidentTimelineRecord]]:
        ticket = self._require_ticket(ticket_id)
        now = utc_now()
        ticket.notes.append(IncidentNoteRecord(author=request.author, text=request.text, created_at=now))
        ticket.last_status_note = request.text
        ticket.updated_at = now
        persisted = self.memory.upsert_incident_ticket(ticket)
        timeline = [
            IncidentTimelineRecord(
                ticket_id=ticket.ticket_id,
                session_id=ticket.session_id,
                event_type=IncidentTimelineEventType.NOTE_ADDED,
                from_status=ticket.current_status,
                to_status=ticket.current_status,
                actor=request.author,
                note=request.text,
                created_at=now,
            )
        ]
        self.memory.append_incident_timeline(timeline)
        self._sync_session_state_from_ticket(persisted)
        return persisted, timeline

    def resolve_ticket(
        self,
        ticket_id: str,
        request: IncidentResolveRequest,
    ) -> tuple[IncidentTicketRecord, list[IncidentTimelineRecord]]:
        ticket = self._require_ticket(ticket_id)
        now = utc_now()
        from_status = ticket.current_status
        to_status = (
            IncidentStatus.UNAVAILABLE
            if request.outcome == IncidentResolutionOutcome.NO_OPERATOR_AVAILABLE
            else IncidentStatus.RESOLVED
        )
        ticket.current_status = to_status
        ticket.resolution_outcome = request.outcome
        ticket.resolved_at = now
        ticket.closed_at = now
        ticket.last_status_note = request.note or f"Resolution recorded by {request.author}."
        ticket.updated_at = now
        if request.note:
            ticket.notes.append(IncidentNoteRecord(author=request.author, text=request.note, created_at=now))
        persisted = self.memory.upsert_incident_ticket(ticket)
        timeline = [
            IncidentTimelineRecord(
                ticket_id=ticket.ticket_id,
                session_id=ticket.session_id,
                event_type=(
                    IncidentTimelineEventType.UNAVAILABLE
                    if to_status == IncidentStatus.UNAVAILABLE
                    else IncidentTimelineEventType.RESOLVED
                ),
                from_status=from_status,
                to_status=to_status,
                actor=request.author,
                note=ticket.last_status_note,
                metadata={"resolution_outcome": request.outcome.value},
                created_at=now,
            )
        ]
        self.memory.append_incident_timeline(timeline)
        self._sync_session_state_from_ticket(persisted)
        return persisted, timeline

    def _should_open_ticket(
        self,
        *,
        reasoning: ReasoningTrace,
        decisions: list[ExecutiveDecisionRecord],
    ) -> bool:
        if reasoning.intent != "operator_handoff":
            return False
        return any(decision.decision_type == ExecutiveDecisionType.ESCALATE_TO_HUMAN for decision in decisions)

    def _build_ticket(
        self,
        *,
        session: SessionRecord,
        event: RobotEvent,
        reasoning: ReasoningTrace,
        decisions: list[ExecutiveDecisionRecord],
        trace_id: str,
    ) -> IncidentTicketRecord:
        reason_category = self._categorize(session=session, event=event, reasoning=reasoning, decisions=decisions)
        suggestion = self._suggest_staff_contact(session=session, event=event, reason_category=reason_category, reasoning=reasoning)
        urgency = self._urgency_for(session=session, reason_category=reason_category, event=event)
        note = self._creation_note(event=event, reason_category=reason_category, suggestion=suggestion)
        ticket = IncidentTicketRecord(
            session_id=session.session_id,
            participant_id=session.participant_id,
            participant_summary=self._participant_summary(session=session, event=event, reason_category=reason_category),
            reason_category=reason_category,
            urgency=urgency,
            suggested_staff_contact=suggestion,
            current_status=IncidentStatus.PENDING,
            notes=[IncidentNoteRecord(author="blink_ai", text=note)],
            created_from_trace_id=trace_id,
            last_trace_id=trace_id,
            last_status_note=note,
        )
        return ticket

    def _participant_summary(
        self,
        *,
        session: SessionRecord,
        event: RobotEvent,
        reason_category: IncidentReasonCategory,
    ) -> str:
        participant_label = session.participant_id or "likely visitor"
        text = str(event.payload.get("text") or "").strip()
        if text:
            return f"{participant_label} requested {reason_category.value.replace('_', ' ')} support after saying: {text}"
        return f"{participant_label} requested {reason_category.value.replace('_', ' ')} support."

    def _creation_note(
        self,
        *,
        event: RobotEvent,
        reason_category: IncidentReasonCategory,
        suggestion: IncidentStaffSuggestion | None,
    ) -> str:
        parts = [f"Auto-created from {reason_category.value} escalation policy."]
        if text := str(event.payload.get("text") or "").strip():
            parts.append(f'Visitor said: "{text}"')
        if suggestion and suggestion.name:
            parts.append(f"Suggested contact: {suggestion.name} ({suggestion.role or 'staff'}).")
        elif suggestion and suggestion.desk_location_label:
            parts.append(f"Suggested desk location: {suggestion.desk_location_label}.")
        else:
            parts.append("No confirmed staff contact was available in the venue pack.")
        return " ".join(parts)

    def _categorize(
        self,
        *,
        session: SessionRecord,
        event: RobotEvent,
        reasoning: ReasoningTrace,
        decisions: list[ExecutiveDecisionRecord],
    ) -> IncidentReasonCategory:
        stored = session.session_memory.get("incident_reason_category")
        if stored:
            try:
                return IncidentReasonCategory(stored)
            except ValueError:
                pass
        lowered = str(event.payload.get("text") or "").lower()
        decision_reasons = {code for decision in decisions for code in decision.reason_codes}
        tool_contact_keys = {
            str(tool.metadata.get("contact_key"))
            for tool in reasoning.tool_invocations
            if tool.metadata.get("contact_key")
        }
        if "accessibility" in lowered or "accessible" in lowered or "quiet room" in lowered:
            return IncidentReasonCategory.ACCESSIBILITY
        if "safety" in lowered or "emergency" in lowered or "unsafe" in lowered:
            return IncidentReasonCategory.SAFETY
        if "lost item" in lowered or "lost" in lowered:
            return IncidentReasonCategory.LOST_ITEM
        if "events" in lowered or "program" in lowered or "volunteer" in lowered or "events" in tool_contact_keys:
            return IncidentReasonCategory.EVENT_SUPPORT
        if "accessibility" in tool_contact_keys or "escalation_due_to_accessibility_request" in decision_reasons:
            return IncidentReasonCategory.ACCESSIBILITY
        if "front_desk" in tool_contact_keys:
            return IncidentReasonCategory.STAFF_REQUEST
        if any(decision.decision_type == ExecutiveDecisionType.ESCALATE_TO_HUMAN for decision in decisions):
            return IncidentReasonCategory.GENERAL_ESCALATION
        return IncidentReasonCategory.UNKNOWN

    def _urgency_for(
        self,
        *,
        session: SessionRecord,
        reason_category: IncidentReasonCategory,
        event: RobotEvent,
    ):
        stored = session.session_memory.get("incident_urgency")
        if stored:
            try:
                return IncidentUrgency(stored)
            except ValueError:
                pass
        lowered = str(event.payload.get("text") or "").lower()
        if reason_category == IncidentReasonCategory.SAFETY:
            return IncidentUrgency.CRITICAL
        if reason_category == IncidentReasonCategory.ACCESSIBILITY:
            return IncidentUrgency.HIGH
        if "urgent" in lowered or "right now" in lowered:
            return IncidentUrgency.HIGH
        return IncidentUrgency.NORMAL

    def _suggest_staff_contact(
        self,
        *,
        session: SessionRecord,
        event: RobotEvent,
        reason_category: IncidentReasonCategory,
        reasoning: ReasoningTrace,
    ) -> IncidentStaffSuggestion | None:
        contact = None
        stored_contact_key = session.session_memory.get("incident_staff_contact_key")
        if stored_contact_key:
            contact = self._contact_by_key(stored_contact_key)
        tool_contact_key = next(
            (str(tool.metadata.get("contact_key")) for tool in reasoning.tool_invocations if tool.metadata.get("contact_key")),
            None,
        )
        if contact is None and tool_contact_key:
            contact = self._contact_by_key(tool_contact_key)
        if contact is None:
            default_contact_key = self.venue_knowledge.default_staff_contact_key_for(reason_category)
            if default_contact_key:
                contact = self._contact_by_key(default_contact_key)
        if contact is None:
            lookup_query = {
                IncidentReasonCategory.ACCESSIBILITY: "accessibility accessible route quiet room",
                IncidentReasonCategory.SAFETY: "front desk safety concern",
                IncidentReasonCategory.LOST_ITEM: "front desk lost item",
                IncidentReasonCategory.EVENT_SUPPORT: "events programs volunteer",
                IncidentReasonCategory.STAFF_REQUEST: "front desk staff request",
                IncidentReasonCategory.GENERAL_ESCALATION: str(event.payload.get("text") or "staff operator"),
                IncidentReasonCategory.UNKNOWN: str(event.payload.get("text") or "staff operator"),
            }[reason_category]
            venue_lookup = self.venue_knowledge.lookup_staff_contact(lookup_query)
            if venue_lookup is not None:
                contact = self._contact_by_key(str(venue_lookup.metadata.get("contact_key") or ""))
        if contact is None:
            return None

        event_title = None
        location_key = self._desk_location_key_for(contact=contact, session=session)
        if reason_category == IncidentReasonCategory.EVENT_SUPPORT:
            event_entry = self._event_for_session(session)
            if event_entry is not None:
                event_title = event_entry.title
                location_key = event_entry.location_key or location_key

        location = self.venue_knowledge.locations.get(location_key) if location_key else None
        return IncidentStaffSuggestion(
            contact_key=contact.contact_key,
            name=contact.name,
            role=contact.role,
            phone=contact.phone,
            email=contact.email,
            desk_location_key=location.location_key if location else location_key,
            desk_location_label=location.title if location else None,
            operating_note=self._operating_note(contact=contact, location_key=location_key),
            event_title=event_title,
            source_refs=[value for value in {contact.source_ref, location.source_ref if location else None} if value],
            note=contact.notes,
        )

    def _contact_by_key(self, contact_key: str) -> VenueStaffContact | None:
        if not contact_key:
            return None
        return next((item for item in self.venue_knowledge.staff_contacts if item.contact_key == contact_key), None)

    def _event_for_session(self, session: SessionRecord):
        last_event_id = session.session_memory.get("last_event_id")
        if not last_event_id:
            return None
        return next((item for item in self.venue_knowledge.events if item.event_id == last_event_id), None)

    def _desk_location_key_for(self, *, contact: VenueStaffContact, session: SessionRecord) -> str | None:
        key = contact.contact_key.lower()
        if "access" in key:
            return "quiet_room"
        if "event" in key or "program" in key:
            event_entry = self._event_for_session(session)
            if event_entry is not None and event_entry.location_key:
                return event_entry.location_key
        return "front_desk" if "front_desk" in self.venue_knowledge.locations else None

    def _operating_note(self, *, contact: VenueStaffContact, location_key: str | None) -> str | None:
        location = self.venue_knowledge.locations.get(location_key) if location_key else None
        targets = [
            contact.contact_key.replace("_", " "),
            contact.role.lower(),
            *(alias.lower() for alias in contact.aliases),
        ]
        if location is not None:
            targets.extend([location.title.lower(), location.location_key.replace("_", " ")])
        for document in self.venue_knowledge.documents:
            for line in document.text.splitlines():
                lowered = line.strip().lower()
                if not lowered:
                    continue
                if any(target and target in lowered for target in targets):
                    return line.strip()
        return contact.notes

    def _apply_ticket_to_session(self, session: SessionRecord, ticket: IncidentTicketRecord) -> None:
        session.active_incident_ticket_id = ticket.ticket_id
        session.incident_status = ticket.current_status
        session.session_memory["incident_ticket_id"] = ticket.ticket_id
        session.session_memory["operator_escalation"] = (
            "requested" if ticket.current_status in OPEN_INCIDENT_STATUSES else ticket.current_status.value
        )
        if ticket.current_status in OPEN_INCIDENT_STATUSES:
            session.status = SessionStatus.ESCALATION_PENDING
        else:
            session.status = SessionStatus.ACTIVE

    def _sync_session_state_from_ticket(self, ticket: IncidentTicketRecord) -> None:
        session = self.memory.get_session(ticket.session_id)
        if session is None:
            return
        self._apply_ticket_to_session(session, ticket)
        self.memory.upsert_session(session)

    def _latest_ticket_for_session(self, session_id: str) -> IncidentTicketRecord | None:
        tickets = self.memory.list_incident_tickets(scope=IncidentListScope.ALL, session_id=session_id, limit=1).items
        if not tickets:
            return None
        return tickets[0]

    def _open_ticket_for_session(self, session_id: str) -> IncidentTicketRecord | None:
        tickets = self.memory.list_incident_tickets(scope=IncidentListScope.OPEN, session_id=session_id, limit=1).items
        if not tickets:
            return None
        return tickets[0]

    def _require_ticket(self, ticket_id: str) -> IncidentTicketRecord:
        ticket = self.memory.get_incident_ticket(ticket_id)
        if ticket is None:
            raise KeyError(ticket_id)
        return ticket

    def _looks_like_status_follow_up(self, *, text: str, session: SessionRecord) -> bool:
        lowered = text.lower().strip()
        if session.current_topic == "operator_handoff" and lowered in {"ok", "okay", "thanks", "thank you"}:
            return True
        keywords = (
            "operator",
            "staff",
            "ticket",
            "handoff",
            "help me",
            "coming",
            "on the way",
            "waiting",
            "resolved",
            "available",
            "anyone",
            "thank",
        )
        return any(keyword in lowered for keyword in keywords)

    def _intent_for_status(self, status: IncidentStatus) -> str:
        return {
            IncidentStatus.PENDING: "operator_handoff_pending",
            IncidentStatus.ACKNOWLEDGED: "operator_handoff_accepted",
            IncidentStatus.ASSIGNED: "operator_handoff_accepted",
            IncidentStatus.RESOLVED: "operator_handoff_resolved",
            IncidentStatus.UNAVAILABLE: "operator_handoff_unavailable",
        }[status]

    def _status_reply(self, ticket: IncidentTicketRecord) -> str:
        suggestion = ticket.suggested_staff_contact
        location = suggestion.desk_location_label if suggestion and suggestion.desk_location_label else "front desk"
        if ticket.current_status == IncidentStatus.PENDING:
            if suggestion and suggestion.name:
                return (
                    f"I have opened human operator handoff ticket {ticket.ticket_id} and kept your request visible. "
                    f"My suggested staff contact is {suggestion.name}, {suggestion.role or 'staff'}, near the {location}."
                )
            return (
                f"I have opened human operator handoff ticket {ticket.ticket_id} and kept your request visible. "
                f"I do not have a confirmed staff contact yet, so please stay near the {location}."
            )
        if ticket.current_status in {IncidentStatus.ACKNOWLEDGED, IncidentStatus.ASSIGNED}:
            if ticket.assigned_to:
                return f"Handoff ticket {ticket.ticket_id} is now assigned to {ticket.assigned_to}. Please stay near the {location}."
            if suggestion and suggestion.name:
                return f"Handoff ticket {ticket.ticket_id} has been acknowledged. {suggestion.name} is the suggested contact."
            return f"Handoff ticket {ticket.ticket_id} has been acknowledged. A staff member is reviewing it now."
        if ticket.current_status == IncidentStatus.RESOLVED:
            return (
                f"Handoff ticket {ticket.ticket_id} has been marked resolved. "
                "If you still need help, I can open another staff handoff."
            )
        fallback = self.venue_knowledge.fallback_instruction(VenueFallbackScenario.OPERATOR_UNAVAILABLE)
        if fallback is not None:
            return fallback.visitor_message.replace("{ticket_id}", ticket.ticket_id).replace("{location}", location)
        if suggestion and suggestion.phone:
            return (
                f"No operator is immediately available for ticket {ticket.ticket_id}. "
                f"Please go to the {location} or call {suggestion.phone} if this is urgent."
            )
        return (
            f"No operator is immediately available for ticket {ticket.ticket_id}. "
            f"Please go to the {location} if you need urgent help."
        )
