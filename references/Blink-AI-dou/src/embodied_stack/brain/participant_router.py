from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from uuid import uuid4

from embodied_stack.brain.memory import MemoryStore
from embodied_stack.config import Settings
from embodied_stack.shared.models import (
    EmbodiedWorldModel,
    InteractionExecutiveState,
    ParticipantRouterSnapshot,
    ParticipantSessionBinding,
    QueuedParticipantRecord,
    ResponseMode,
    RobotEvent,
    SessionCreateRequest,
    SessionRecord,
    SessionRoutingStatus,
    SessionStatus,
)


VISIBILITY_EVENT_TYPES = {"person_detected", "person_visible", "people_count_changed", "person_left"}


@dataclass
class ParticipantRoutePlan:
    event: RobotEvent
    session: SessionRecord
    snapshot: ParticipantRouterSnapshot
    participant_id: str | None = None
    notes: list[str] = field(default_factory=list)
    skip_interaction: bool = False
    reply_text: str | None = None
    intent: str | None = None
    prepend_stop: bool = False


@dataclass
class ParticipantSessionRouter:
    memory: MemoryStore
    settings: Settings

    def get_status(self) -> ParticipantRouterSnapshot:
        return self.memory.get_participant_router()

    def route_event(
        self,
        event: RobotEvent,
        *,
        prior_world_model: EmbodiedWorldModel,
    ) -> ParticipantRoutePlan:
        now = event.timestamp
        snapshot = self._prune(self.memory.get_participant_router(), now=now)
        payload = dict(event.payload)
        notes: list[str] = []

        explicit_participant_id = self._explicit_participant_id(event)
        participant_id: str | None = explicit_participant_id
        session: SessionRecord | None = None

        if event.event_type in VISIBILITY_EVENT_TYPES:
            visible_ids = self._apply_visibility(snapshot, event=event, explicit_participant_id=explicit_participant_id, now=now)
            if visible_ids:
                payload["participant_ids"] = visible_ids
                participant_id = participant_id or visible_ids[0]
                payload["participant_id"] = participant_id
            notes.append(f"router_visibility:{len(visible_ids)}")

        if event.event_type == "speech_transcript":
            text = str(payload.get("text") or "").strip()
            participant_id = self._resolve_speaker(snapshot, prior_world_model=prior_world_model, explicit_participant_id=participant_id, now=now)
            if participant_id is None:
                participant_id = self._active_or_first_visible(snapshot)
            if participant_id is None:
                participant_id = self._next_participant_id(snapshot)
                self._ensure_binding(snapshot, participant_id, now=now)
                notes.append("router_new_unseen_participant")

            payload["participant_id"] = participant_id
            payload["crowd_mode"] = snapshot.crowd_mode

            session = self._ensure_session_for_participant(
                snapshot,
                participant_id=participant_id,
                session_hint=event.session_id,
                now=now,
            )

            if bool(payload.get("multiple_speakers")):
                self._activate(snapshot, participant_id=participant_id, session=session, now=now, reason="multiple_speakers_reorientation")
                routed_event = event.model_copy(
                    update={
                        "session_id": session.session_id,
                        "payload": {
                            **payload,
                            "routing_reason": "multiple_speakers_reorientation",
                        },
                    }
                )
                persisted = self.memory.replace_participant_router(snapshot)
                return ParticipantRoutePlan(
                    event=routed_event,
                    session=session,
                    snapshot=persisted,
                    participant_id=participant_id,
                    notes=["participant_router:multiple_speakers_reorientation"],
                    skip_interaction=True,
                    reply_text="I can help one person at a time. Please go one at a time and I will keep helping the current visitor first.",
                    intent="crowd_reorientation",
                    prepend_stop=self._should_stop_for_reorientation(prior_world_model, now=now),
                )

            active_participant_id = snapshot.active_participant_id
            priority_reason = self._priority_reason(text=text, session=session)
            binding = self._binding(snapshot, participant_id)
            if binding is not None and priority_reason and not binding.priority_reason:
                binding.priority_reason = priority_reason

            if (
                active_participant_id
                and active_participant_id != participant_id
                and self._retains_active_speaker(snapshot, now=now)
                and not priority_reason
            ):
                queue_entry = self._enqueue(snapshot, participant_id=participant_id, session=session, now=now)
                should_prompt = self._should_issue_wait_prompt(queue_entry, now=now)
                self._set_session_routing(
                    session,
                    participant_id=participant_id,
                    routing_status=SessionRoutingStatus.PAUSED,
                    now=now,
                    note="queued_behind_active_participant",
                )
                payload["routing_reason"] = "secondary_visitor_wait"
                routed_event = event.model_copy(update={"session_id": session.session_id, "payload": payload})
                persisted = self.memory.replace_participant_router(snapshot)
                return ParticipantRoutePlan(
                    event=routed_event,
                    session=session,
                    snapshot=persisted,
                    participant_id=participant_id,
                    notes=["participant_router:secondary_visitor_wait"],
                    skip_interaction=True,
                    reply_text="I will be right with you. I am finishing with another visitor first." if should_prompt else None,
                    intent="queue_wait",
                    prepend_stop=self._should_stop_for_reorientation(prior_world_model, now=now),
                )

            if active_participant_id and active_participant_id != participant_id:
                self._pause_active_participant(snapshot, now=now, note="focus_switched_to_another_participant")
            self._activate(
                snapshot,
                participant_id=participant_id,
                session=session,
                now=now,
                reason=priority_reason or ("speaker_retained" if active_participant_id == participant_id else "speaker_claimed_focus"),
            )
            notes.append(f"participant_router:active_participant={participant_id}")

        elif event.event_type in VISIBILITY_EVENT_TYPES:
            participant_id = participant_id or snapshot.active_participant_id or self._active_or_first_visible(snapshot)
            if participant_id is not None:
                session = self._ensure_session_for_participant(
                    snapshot,
                    participant_id=participant_id,
                    session_hint=event.session_id,
                    now=now,
                )
                if snapshot.active_participant_id is None:
                    self._activate(snapshot, participant_id=participant_id, session=session, now=now, reason="first_visible_wins")
            else:
                session = self._ensure_fallback_session(event.session_id)

        else:
            participant_id = explicit_participant_id or snapshot.active_participant_id or self._active_or_first_visible(snapshot)
            if participant_id is not None:
                session = self._ensure_session_for_participant(
                    snapshot,
                    participant_id=participant_id,
                    session_hint=event.session_id,
                    now=now,
                )
                payload["participant_id"] = participant_id
            else:
                session = self._ensure_fallback_session(event.session_id)

        routed_event = event.model_copy(
            update={
                "session_id": session.session_id,
                "payload": payload,
            }
        )
        persisted = self.memory.replace_participant_router(snapshot)
        return ParticipantRoutePlan(
            event=routed_event,
            session=session,
            snapshot=persisted,
            participant_id=participant_id,
            notes=notes,
        )

    def finalize_event(
        self,
        *,
        event: RobotEvent,
        session: SessionRecord,
        prior_world_model: EmbodiedWorldModel,
        response_text: str | None,
        intent: str,
    ) -> ParticipantRouterSnapshot:
        now = event.timestamp
        snapshot = self._prune(self.memory.get_participant_router(), now=now)
        participant_id = str(event.payload.get("participant_id") or session.participant_id or "").strip() or None
        routing_reason = str(event.payload.get("routing_reason") or "").strip()

        if participant_id is not None:
            binding = self._ensure_binding(snapshot, participant_id, now=now)
            binding.session_id = session.session_id
            if event.event_type in VISIBILITY_EVENT_TYPES:
                binding.last_seen_at = now
                binding.in_view = event.event_type != "person_left"
                session.last_participant_seen_at = now
                session.resume_until_at = now + timedelta(seconds=self.settings.participant_router_resume_window_seconds)
            if event.event_type == "speech_transcript":
                binding.last_heard_at = now
                binding.last_seen_at = binding.last_seen_at or now
                binding.resume_until_at = now + timedelta(seconds=self.settings.participant_router_resume_window_seconds)
                session.last_participant_heard_at = now
                session.last_participant_seen_at = binding.last_seen_at or now
                session.resume_until_at = binding.resume_until_at
                if intent == "queue_wait" or routing_reason == "secondary_visitor_wait":
                    self._set_session_routing(
                        session,
                        participant_id=participant_id,
                        routing_status=SessionRoutingStatus.PAUSED,
                        now=now,
                        note="queued_behind_active_participant",
                    )
                    self.memory.upsert_session(session)
                    return self.memory.replace_participant_router(snapshot)
                if session.status == SessionStatus.ESCALATION_PENDING:
                    binding.priority_reason = binding.priority_reason or "escalation"
                    self._set_session_routing(
                        session,
                        participant_id=participant_id,
                        routing_status=SessionRoutingStatus.HANDED_OFF,
                        now=now,
                        note="operator_handoff_priority",
                    )
                    snapshot.last_routing_reason = "escalated_participant_priority"
                elif session.routing_status != SessionRoutingStatus.COMPLETE:
                    self._set_session_routing(
                        session,
                        participant_id=participant_id,
                        routing_status=SessionRoutingStatus.ACTIVE,
                        now=now,
                        note="active_participant_served",
                    )
                if response_text or prior_world_model.turn_state == InteractionExecutiveState.RESPONDING:
                    snapshot.active_speaker_retention_until = now + timedelta(
                        seconds=self.settings.participant_router_active_speaker_retention_seconds
                    )
                self._activate(snapshot, participant_id=participant_id, session=session, now=now, reason=snapshot.last_routing_reason or "speech_turn_served")

            if event.event_type == "person_left" and snapshot.active_participant_id == participant_id:
                self._pause_active_participant(snapshot, now=now, note="active_participant_left_view")
                self._promote_next_active(snapshot, now=now)

        if session.routing_status == SessionRoutingStatus.COMPLETE and session.status != SessionStatus.CLOSED:
            session.status = SessionStatus.CLOSED
        self.memory.upsert_session(session)
        persisted = self.memory.replace_participant_router(snapshot)
        return persisted

    def _apply_visibility(
        self,
        snapshot: ParticipantRouterSnapshot,
        *,
        event: RobotEvent,
        explicit_participant_id: str | None,
        now: datetime,
    ) -> list[str]:
        payload = event.payload
        explicit_ids = [item for item in payload.get("participant_ids", []) or [] if isinstance(item, str) and item.strip()]
        if explicit_participant_id and explicit_participant_id not in explicit_ids:
            explicit_ids.insert(0, explicit_participant_id)

        if event.event_type == "person_left":
            if explicit_ids:
                for participant_id in explicit_ids:
                    binding = self._binding(snapshot, participant_id)
                    if binding is not None:
                        binding.in_view = False
                        binding.last_seen_at = now
                        binding.resume_until_at = now + timedelta(seconds=self.settings.participant_router_resume_window_seconds)
                self._rebuild_queue(snapshot)
                return [binding.participant_id for binding in self._visible_bindings(snapshot)]
            self._mark_all_not_in_view(snapshot, now=now)
            return []

        desired_count = int(payload.get("people_count") or len(explicit_ids) or 1)
        current_visible_ids = [binding.participant_id for binding in self._visible_bindings(snapshot)]

        visible_ids: list[str] = []
        for participant_id in explicit_ids:
            binding = self._ensure_binding(snapshot, participant_id, now=now)
            binding.in_view = True
            binding.last_seen_at = now
            binding.resume_until_at = now + timedelta(seconds=self.settings.participant_router_resume_window_seconds)
            visible_ids.append(participant_id)

        for participant_id in current_visible_ids:
            if len(visible_ids) >= desired_count:
                break
            if participant_id not in visible_ids:
                binding = self._ensure_binding(snapshot, participant_id, now=now)
                binding.in_view = True
                binding.last_seen_at = now
                visible_ids.append(participant_id)

        while len(visible_ids) < desired_count:
            participant_id = self._next_participant_id(snapshot)
            binding = self._ensure_binding(snapshot, participant_id, now=now)
            binding.in_view = True
            binding.last_seen_at = now
            binding.resume_until_at = now + timedelta(seconds=self.settings.participant_router_resume_window_seconds)
            visible_ids.append(participant_id)

        for binding in snapshot.participant_sessions:
            if binding.participant_id in visible_ids:
                binding.in_view = True
                binding.last_seen_at = now
                binding.resume_until_at = now + timedelta(seconds=self.settings.participant_router_resume_window_seconds)
            elif event.event_type == "people_count_changed" and binding.in_view:
                binding.in_view = False

        if visible_ids and snapshot.active_participant_id is None:
            snapshot.active_participant_id = visible_ids[0]
            active_binding = self._binding(snapshot, visible_ids[0])
            snapshot.active_session_id = active_binding.session_id if active_binding else None
            snapshot.last_routing_reason = "first_visible_wins"

        if snapshot.active_participant_id and snapshot.active_participant_id not in visible_ids and visible_ids:
            snapshot.active_participant_id = visible_ids[0]
            active_binding = self._binding(snapshot, visible_ids[0])
            snapshot.active_session_id = active_binding.session_id if active_binding else None
            snapshot.last_routing_reason = "active_participant_no_longer_visible"

        snapshot.crowd_mode = len(visible_ids) > 1 or bool(snapshot.queued_participants)
        self._rebuild_queue(snapshot)
        return visible_ids

    def _resolve_speaker(
        self,
        snapshot: ParticipantRouterSnapshot,
        *,
        prior_world_model: EmbodiedWorldModel,
        explicit_participant_id: str | None,
        now: datetime,
    ) -> str | None:
        del prior_world_model
        if explicit_participant_id:
            return explicit_participant_id
        if self._retains_active_speaker(snapshot, now=now) and snapshot.active_participant_id:
            return snapshot.active_participant_id
        visible = self._visible_bindings(snapshot)
        if len(visible) == 1:
            return visible[0].participant_id
        if snapshot.active_participant_id:
            return snapshot.active_participant_id
        if visible:
            return visible[0].participant_id
        return None

    def _ensure_session_for_participant(
        self,
        snapshot: ParticipantRouterSnapshot,
        *,
        participant_id: str,
        session_hint: str | None,
        now: datetime,
    ) -> SessionRecord:
        binding = self._ensure_binding(snapshot, participant_id, now=now)
        if session_hint:
            session = self.memory.ensure_session(session_hint)
        elif binding.session_id:
            existing = self.memory.get_session(binding.session_id)
            if existing is not None and existing.routing_status != SessionRoutingStatus.COMPLETE and existing.status != SessionStatus.CLOSED:
                session = existing
            else:
                session = self.memory.create_session(
                    SessionCreateRequest(
                        session_id=f"router-{participant_id}-{uuid4().hex[:6]}",
                        response_mode=ResponseMode.GUIDE,
                    )
                )
        else:
            session = self.memory.create_session(
                SessionCreateRequest(
                    session_id=f"router-{participant_id}-{uuid4().hex[:6]}",
                    response_mode=ResponseMode.GUIDE,
                )
            )

        binding.session_id = session.session_id
        if binding.last_seen_at:
            session.last_participant_seen_at = binding.last_seen_at
        if binding.last_heard_at:
            session.last_participant_heard_at = binding.last_heard_at
        self._set_session_routing(
            session,
            participant_id=participant_id,
            routing_status=session.routing_status if session.routing_status != SessionRoutingStatus.COMPLETE else SessionRoutingStatus.ACTIVE,
            now=now,
            note=session.routing_note or "participant_session_routed",
        )
        return self.memory.upsert_session(session)

    def _ensure_fallback_session(self, session_hint: str | None) -> SessionRecord:
        session_id = session_hint or "default-session"
        return self.memory.ensure_session(session_id)

    def _ensure_binding(
        self,
        snapshot: ParticipantRouterSnapshot,
        participant_id: str,
        *,
        now: datetime,
    ) -> ParticipantSessionBinding:
        binding = self._binding(snapshot, participant_id)
        if binding is not None:
            return binding
        binding = ParticipantSessionBinding(
            participant_id=participant_id,
            first_seen_at=now,
            last_seen_at=now,
            resume_until_at=now + timedelta(seconds=self.settings.participant_router_resume_window_seconds),
        )
        snapshot.participant_sessions.append(binding)
        return binding

    def _binding(self, snapshot: ParticipantRouterSnapshot, participant_id: str | None) -> ParticipantSessionBinding | None:
        if participant_id is None:
            return None
        return next((item for item in snapshot.participant_sessions if item.participant_id == participant_id), None)

    def _visible_bindings(self, snapshot: ParticipantRouterSnapshot) -> list[ParticipantSessionBinding]:
        return sorted(
            [item for item in snapshot.participant_sessions if item.in_view],
            key=lambda item: (item.first_seen_at, item.participant_id),
        )

    def _active_or_first_visible(self, snapshot: ParticipantRouterSnapshot) -> str | None:
        if snapshot.active_participant_id:
            return snapshot.active_participant_id
        visible = self._visible_bindings(snapshot)
        return visible[0].participant_id if visible else None

    def _activate(
        self,
        snapshot: ParticipantRouterSnapshot,
        *,
        participant_id: str,
        session: SessionRecord,
        now: datetime,
        reason: str,
    ) -> None:
        snapshot.active_participant_id = participant_id
        snapshot.active_session_id = session.session_id
        snapshot.active_speaker_retention_until = now + timedelta(
            seconds=self.settings.participant_router_active_speaker_retention_seconds
        )
        snapshot.last_routing_reason = reason
        self._dequeue(snapshot, participant_id)
        self._set_session_routing(
            session,
            participant_id=participant_id,
            routing_status=SessionRoutingStatus.ACTIVE if session.status != SessionStatus.ESCALATION_PENDING else SessionRoutingStatus.HANDED_OFF,
            now=now,
            note=reason,
        )

    def _pause_active_participant(self, snapshot: ParticipantRouterSnapshot, *, now: datetime, note: str) -> None:
        participant_id = snapshot.active_participant_id
        binding = self._binding(snapshot, participant_id)
        if binding is None:
            snapshot.active_participant_id = None
            snapshot.active_session_id = None
            return
        binding.resume_until_at = now + timedelta(seconds=self.settings.participant_router_resume_window_seconds)
        session = self.memory.get_session(binding.session_id)
        if session is not None and session.routing_status not in {SessionRoutingStatus.HANDED_OFF, SessionRoutingStatus.COMPLETE}:
            self._set_session_routing(
                session,
                participant_id=participant_id,
                routing_status=SessionRoutingStatus.PAUSED,
                now=now,
                note=note,
            )
            self.memory.upsert_session(session)
        snapshot.active_participant_id = None
        snapshot.active_session_id = None

    def _enqueue(
        self,
        snapshot: ParticipantRouterSnapshot,
        *,
        participant_id: str,
        session: SessionRecord,
        now: datetime,
    ) -> QueuedParticipantRecord:
        entry = self._queue_entry(snapshot, participant_id)
        binding = self._binding(snapshot, participant_id)
        priority_reason = binding.priority_reason if binding is not None else None
        if entry is None:
            entry = QueuedParticipantRecord(
                participant_id=participant_id,
                session_id=session.session_id,
                queue_position=len(snapshot.queued_participants) + 1,
                wait_started_at=now,
                last_prompted_at=None,
                last_seen_at=binding.last_seen_at if binding else now,
                priority_reason=priority_reason,
                note="waiting_for_active_participant",
            )
            snapshot.queued_participants.append(entry)
        else:
            entry.session_id = session.session_id
            entry.last_seen_at = binding.last_seen_at if binding else entry.last_seen_at
            entry.priority_reason = priority_reason or entry.priority_reason
            entry.note = "waiting_for_active_participant"
        self._rebuild_queue(snapshot)
        return entry

    def _dequeue(self, snapshot: ParticipantRouterSnapshot, participant_id: str) -> None:
        snapshot.queued_participants = [
            item for item in snapshot.queued_participants if item.participant_id != participant_id
        ]
        self._rebuild_queue(snapshot)

    def _queue_entry(self, snapshot: ParticipantRouterSnapshot, participant_id: str) -> QueuedParticipantRecord | None:
        return next((item for item in snapshot.queued_participants if item.participant_id == participant_id), None)

    def _rebuild_queue(self, snapshot: ParticipantRouterSnapshot) -> None:
        priority_entries = [
            item
            for item in snapshot.queued_participants
            if item.priority_reason
        ]
        regular_entries = [
            item
            for item in snapshot.queued_participants
            if not item.priority_reason
        ]
        ordered = sorted(priority_entries, key=lambda item: (item.wait_started_at, item.participant_id)) + sorted(
            regular_entries,
            key=lambda item: (item.wait_started_at, item.participant_id),
        )
        for index, item in enumerate(ordered, start=1):
            item.queue_position = index
        snapshot.queued_participants = ordered
        snapshot.crowd_mode = len(self._visible_bindings(snapshot)) > 1 or bool(snapshot.queued_participants)

    def _promote_next_active(self, snapshot: ParticipantRouterSnapshot, *, now: datetime) -> None:
        if snapshot.active_participant_id:
            return
        candidate = None
        if snapshot.queued_participants:
            candidate = snapshot.queued_participants[0]
        elif self._visible_bindings(snapshot):
            candidate_binding = self._visible_bindings(snapshot)[0]
            candidate = QueuedParticipantRecord(
                participant_id=candidate_binding.participant_id,
                session_id=candidate_binding.session_id,
                queue_position=1,
                wait_started_at=now,
            )
        if candidate is None:
            snapshot.active_session_id = None
            return
        binding = self._binding(snapshot, candidate.participant_id)
        session = self.memory.get_session(candidate.session_id) if candidate.session_id else None
        if binding is None or session is None:
            return
        self._activate(snapshot, participant_id=binding.participant_id, session=session, now=now, reason="next_participant_promoted")

    def _should_issue_wait_prompt(self, queue_entry: QueuedParticipantRecord, *, now: datetime) -> bool:
        if queue_entry.last_prompted_at is None:
            queue_entry.last_prompted_at = now
            return True
        if (now - queue_entry.last_prompted_at).total_seconds() >= self.settings.participant_router_wait_prompt_cooldown_seconds:
            queue_entry.last_prompted_at = now
            return True
        return False

    def _set_session_routing(
        self,
        session: SessionRecord,
        *,
        participant_id: str,
        routing_status: SessionRoutingStatus,
        now: datetime,
        note: str,
    ) -> None:
        session.participant_id = participant_id
        session.routing_status = routing_status
        session.routing_note = note
        session.resume_until_at = now + timedelta(seconds=self.settings.participant_router_resume_window_seconds)
        session.updated_at = now
        if routing_status == SessionRoutingStatus.COMPLETE:
            session.status = SessionStatus.CLOSED

    def _retains_active_speaker(self, snapshot: ParticipantRouterSnapshot, *, now: datetime) -> bool:
        return bool(
            snapshot.active_participant_id
            and snapshot.active_speaker_retention_until
            and snapshot.active_speaker_retention_until > now
        )

    def _priority_reason(self, *, text: str, session: SessionRecord) -> str | None:
        lowered = text.lower().strip()
        if session.status == SessionStatus.ESCALATION_PENDING:
            return "escalation"
        accessibility_terms = ("accessible", "accessibility", "wheelchair", "ada", "hearing", "visual impairment")
        if any(term in lowered for term in accessibility_terms):
            return "accessibility"
        if "human operator" in lowered or "staff" in lowered or "help" in lowered and "lost item" in lowered:
            return "escalation"
        return None

    def _should_stop_for_reorientation(self, prior_world_model: EmbodiedWorldModel, *, now: datetime) -> bool:
        return bool(
            prior_world_model.turn_state == InteractionExecutiveState.RESPONDING
            and prior_world_model.last_robot_speech_at
            and (now - prior_world_model.last_robot_speech_at).total_seconds() <= self.settings.participant_router_active_speaker_retention_seconds
        )

    def _mark_all_not_in_view(self, snapshot: ParticipantRouterSnapshot, *, now: datetime) -> None:
        for binding in snapshot.participant_sessions:
            if binding.in_view:
                binding.in_view = False
                binding.last_seen_at = now
                binding.resume_until_at = now + timedelta(seconds=self.settings.participant_router_resume_window_seconds)
        snapshot.crowd_mode = bool(snapshot.queued_participants)
        if snapshot.active_participant_id and self._binding(snapshot, snapshot.active_participant_id) is None:
            snapshot.active_participant_id = None
            snapshot.active_session_id = None

    def _prune(self, snapshot: ParticipantRouterSnapshot, *, now: datetime) -> ParticipantRouterSnapshot:
        remaining_bindings: list[ParticipantSessionBinding] = []
        for binding in snapshot.participant_sessions:
            reference_at = binding.last_heard_at or binding.last_seen_at or binding.first_seen_at
            if reference_at and (now - reference_at).total_seconds() > self.settings.participant_router_session_timeout_seconds:
                session = self.memory.get_session(binding.session_id)
                if session is not None:
                    self._set_session_routing(
                        session,
                        participant_id=binding.participant_id,
                        routing_status=SessionRoutingStatus.COMPLETE,
                        now=now,
                        note="participant_session_expired",
                    )
                    self.memory.upsert_session(session)
                continue
            remaining_bindings.append(binding)
        snapshot.participant_sessions = remaining_bindings
        snapshot.queued_participants = [
            item for item in snapshot.queued_participants if self._binding(snapshot, item.participant_id) is not None
        ]
        if snapshot.active_participant_id and self._binding(snapshot, snapshot.active_participant_id) is None:
            snapshot.active_participant_id = None
            snapshot.active_session_id = None
        if snapshot.active_speaker_retention_until and snapshot.active_speaker_retention_until <= now:
            snapshot.active_speaker_retention_until = None
        self._rebuild_queue(snapshot)
        if snapshot.active_participant_id is None:
            self._promote_next_active(snapshot, now=now)
        return snapshot

    @staticmethod
    def _explicit_participant_id(event: RobotEvent) -> str | None:
        for key in ("speaker_participant_id", "participant_id"):
            value = str(event.payload.get(key) or "").strip()
            if value:
                return value
        return None

    @staticmethod
    def _next_participant_id(snapshot: ParticipantRouterSnapshot) -> str:
        indices = []
        for binding in snapshot.participant_sessions:
            if binding.participant_id.startswith("likely_participant_"):
                suffix = binding.participant_id.removeprefix("likely_participant_")
                if suffix.isdigit():
                    indices.append(int(suffix))
        next_index = max(indices, default=0) + 1
        return f"likely_participant_{next_index}"
