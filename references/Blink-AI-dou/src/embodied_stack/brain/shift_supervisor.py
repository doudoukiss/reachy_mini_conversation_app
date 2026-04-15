from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from embodied_stack.brain.memory import MemoryStore
from embodied_stack.brain.venue_knowledge import VenueKnowledge
from embodied_stack.config import Settings
from embodied_stack.shared.models import (
    CommandBatch,
    IncidentReasonCategory,
    RobotEvent,
    SessionRecord,
    SessionStatus,
    ShiftOperatingState,
    ShiftSupervisorSnapshot,
    ShiftTimerSnapshot,
    ShiftTransitionRecord,
    VenueFallbackScenario,
    VenueOperationsSnapshot,
    VenueScheduleWindow,
    WorldState,
    EmbodiedWorldModel,
    utc_now,
)


DAY_NAMES = {
    "monday": 0,
    "tuesday": 1,
    "wednesday": 2,
    "thursday": 3,
    "friday": 4,
    "saturday": 5,
    "sunday": 6,
}


@dataclass(frozen=True)
class ScheduleWindow:
    weekday: int
    opens_at: time
    closes_at: time


@dataclass(frozen=True)
class ScheduleStatus:
    is_open: bool
    quiet_hours_active: bool
    is_closing: bool
    next_open_at: datetime | None
    next_close_at: datetime | None
    timezone_name: str


@dataclass
class ShiftSupervisorPlan:
    snapshot: ShiftSupervisorSnapshot
    transitions: list[ShiftTransitionRecord] = field(default_factory=list)
    reason_codes: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    skip_interaction: bool = False
    reply_text: str | None = None
    intent: str | None = None
    proactive_action: str | None = None
    proactive_action_key: str | None = None


class VenueHoursSchedule:
    def __init__(
        self,
        *,
        timezone_name: str,
        windows: list[ScheduleWindow],
        quiet_windows: list[ScheduleWindow],
        closing_windows: list[ScheduleWindow],
        closing_lead_minutes: int,
    ) -> None:
        self.timezone_name = timezone_name
        self.windows = windows
        self.quiet_windows = quiet_windows
        self.closing_windows = closing_windows
        self.closing_lead_minutes = max(0, closing_lead_minutes)
        try:
            self.tz = ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError:
            self.tz = ZoneInfo("UTC")
            self.timezone_name = "UTC"

    @classmethod
    def from_venue(cls, *, settings: Settings, venue_knowledge: VenueKnowledge) -> VenueHoursSchedule:
        timezone_name = settings.shift_timezone or venue_knowledge.operations.timezone or venue_knowledge.timezone or "UTC"
        operations = venue_knowledge.operations
        windows = schedule_windows_from_operations(operations.opening_hours)
        if not windows:
            summary = settings.shift_hours_summary or venue_knowledge.hours_summary or ""
            windows = parse_hours_summary(summary)
        if not windows:
            windows = [
                ScheduleWindow(weekday=weekday, opens_at=time(hour=0, minute=0), closes_at=time(hour=23, minute=59))
                for weekday in range(7)
            ]
        quiet_windows = schedule_windows_from_operations(operations.quiet_hours)
        closing_windows = schedule_windows_from_operations(operations.closing_windows)
        if not closing_windows:
            closing_windows = derive_closing_windows(windows, settings.shift_closing_lead_minutes)
        return cls(
            timezone_name=timezone_name,
            windows=windows,
            quiet_windows=quiet_windows,
            closing_windows=closing_windows,
            closing_lead_minutes=settings.shift_closing_lead_minutes,
        )

    def status(self, now: datetime) -> ScheduleStatus:
        localized = ensure_utc(now).astimezone(self.tz)
        today_windows = [window for window in self.windows if window.weekday == localized.weekday()]
        current_window = next(
            (
                window
                for window in today_windows
                if window.opens_at <= localized.timetz().replace(tzinfo=None) < window.closes_at
            ),
            None,
        )

        next_open_at: datetime | None = None
        next_close_at: datetime | None = None

        for offset in range(0, 8):
            candidate_date = localized.date() + timedelta(days=offset)
            candidate_windows = [window for window in self.windows if window.weekday == candidate_date.weekday()]
            for window in sorted(candidate_windows, key=lambda item: (item.opens_at.hour, item.opens_at.minute)):
                open_at = datetime.combine(candidate_date, window.opens_at, tzinfo=self.tz)
                close_at = datetime.combine(candidate_date, window.closes_at, tzinfo=self.tz)
                if offset == 0 and close_at <= localized:
                    continue
                if current_window is not None and open_at <= localized < close_at:
                    next_close_at = close_at
                    break
                if open_at > localized and next_open_at is None:
                    next_open_at = open_at
            if next_close_at is not None:
                break
            if next_open_at is not None and offset > 0:
                break

        active_quiet_window = next(
            (
                window
                for window in self.quiet_windows
                if window.weekday == localized.weekday()
                and window.opens_at <= localized.timetz().replace(tzinfo=None) < window.closes_at
            ),
            None,
        )
        active_closing_window = next(
            (
                window
                for window in self.closing_windows
                if window.weekday == localized.weekday()
                and window.opens_at <= localized.timetz().replace(tzinfo=None) < window.closes_at
            ),
            None,
        )

        is_open = current_window is not None
        is_closing = active_closing_window is not None
        if is_open and not is_closing and next_close_at is not None:
            is_closing = (next_close_at - localized) <= timedelta(minutes=self.closing_lead_minutes)

        return ScheduleStatus(
            is_open=is_open,
            quiet_hours_active=active_quiet_window is not None,
            is_closing=is_closing,
            next_open_at=next_open_at.astimezone(timezone.utc) if next_open_at else None,
            next_close_at=next_close_at.astimezone(timezone.utc) if next_close_at else None,
            timezone_name=self.timezone_name,
        )


@dataclass
class ShiftSupervisor:
    memory: MemoryStore
    settings: Settings
    venue_knowledge: VenueKnowledge

    def __post_init__(self) -> None:
        self.schedule = VenueHoursSchedule.from_venue(settings=self.settings, venue_knowledge=self.venue_knowledge)

    def get_status(self) -> ShiftSupervisorSnapshot:
        return self.memory.get_shift_supervisor()

    def get_operations_snapshot(self) -> VenueOperationsSnapshot:
        snapshot = self.venue_knowledge.operations.model_copy(deep=True)
        shift = self.memory.get_shift_supervisor()
        snapshot.next_scheduled_prompt_at = shift.next_scheduled_prompt_at
        snapshot.next_scheduled_prompt_type = shift.next_scheduled_prompt_type
        snapshot.next_scheduled_prompt_note = shift.next_scheduled_prompt_note
        return snapshot

    def list_transitions(
        self,
        *,
        session_id: str | None = None,
        limit: int = 50,
    ):
        return self.memory.list_shift_transitions(session_id=session_id, limit=limit)

    def set_override(
        self,
        *,
        state: ShiftOperatingState | None,
        reason: str,
        clear: bool = False,
        session_id: str | None = None,
        now: datetime | None = None,
    ) -> ShiftSupervisorSnapshot:
        status = self.memory.get_shift_supervisor()
        current_time = ensure_utc(now or utc_now())
        transitions: list[ShiftTransitionRecord] = []

        status.override_active = not clear and state is not None
        status.override_state = None if clear else state
        status.override_reason = None if clear else reason
        if clear and not status.low_battery_active:
            status.safe_idle_active = False
        status.last_policy_note = "shift_override_cleared" if clear else f"shift_override:{state.value if state else 'none'}"
        target_state, reason_codes = self._target_state(
            status=status,
            now=current_time,
            session=None,
            world_model=self.memory.get_world_model(),
            world_state=self.memory.get_world_state(),
            event_type="shift_override",
        )
        transitions.extend(
            self._apply_state(
                status,
                target_state=target_state,
                reason_codes=reason_codes,
                trigger="shift_override",
                session_id=session_id,
                note=status.last_policy_note,
                now=current_time,
            )
        )
        status.timers = self._timers(status, now=current_time)
        persisted = self.memory.replace_shift_supervisor(status)
        if transitions:
            self.memory.append_shift_transitions(transitions)
        return persisted

    def evaluate_pre_event(
        self,
        *,
        event: RobotEvent,
        session: SessionRecord | None,
        world_model: EmbodiedWorldModel,
        world_state: WorldState,
    ) -> ShiftSupervisorPlan:
        now = ensure_utc(event.timestamp)
        status = self.memory.get_shift_supervisor()
        self._apply_signal_updates(status, event=event, world_model=world_model)

        target_state, reason_codes = self._target_state(
            status=status,
            now=now,
            session=session,
            world_model=world_model,
            world_state=world_state,
            event_type=event.event_type,
        )
        transitions = self._apply_state(
            status,
            target_state=target_state,
            reason_codes=reason_codes,
            trigger=event.event_type,
            session_id=session.session_id if session else event.session_id,
            note=None,
            now=now,
        )

        plan = ShiftSupervisorPlan(
            snapshot=status,
            transitions=transitions,
            reason_codes=reason_codes,
        )

        if event.event_type in {"person_detected", "person_visible"}:
            if self._suppress_presence_outreach(status=status, now=now):
                plan.skip_interaction = True
                plan.intent = "telemetry_update"
                plan.notes.append("shift_policy:presence_outreach_suppressed")
                plan.snapshot.last_policy_note = "presence_outreach_suppressed"
        elif event.event_type == "speech_transcript":
            if status.state == ShiftOperatingState.SAFE_IDLE:
                plan.skip_interaction = True
                plan.reply_text = self._fallback_reply(
                    scenario=VenueFallbackScenario.SAFE_IDLE,
                    default="I am holding safe idle right now while an operator checks the system.",
                )
                plan.intent = "safe_idle"
                plan.notes.append("shift_policy:safe_idle_reply_override")
                plan.snapshot.last_policy_note = "safe_idle_reply_override"
            elif status.state == ShiftOperatingState.DEGRADED:
                plan.skip_interaction = True
                plan.reply_text = self._fallback_reply(
                    scenario=VenueFallbackScenario.TRANSPORT_OUTAGE,
                    default="I am in a degraded mode right now while the venue link recovers.",
                )
                plan.intent = "safe_idle"
                plan.notes.append("shift_policy:degraded_reply_override")
                plan.snapshot.last_policy_note = "degraded_reply_override"
        elif event.event_type == "shift_autonomy_tick":
            plan.skip_interaction = True
            plan.intent = "telemetry_update"
            initiative_reply_text = str(event.payload.get("initiative_reply_text") or "").strip() or None
            initiative_intent = str(event.payload.get("initiative_intent") or "").strip() or None
            initiative_action = str(event.payload.get("initiative_action") or "").strip() or None
            initiative_action_key = str(event.payload.get("initiative_action_key") or "").strip() or None
            initiative_reason = str(event.payload.get("initiative_reason") or "").strip() or None
            if initiative_reply_text is not None:
                plan.reply_text = initiative_reply_text
                plan.intent = initiative_intent or "attract_prompt"
                plan.proactive_action = initiative_action or plan.intent
                plan.proactive_action_key = initiative_action_key or None
                plan.notes.append(f"shift_policy:{plan.proactive_action}")
                plan.snapshot.last_policy_note = initiative_reason or plan.proactive_action or "initiative_prompt"
            else:
                scheduled_prompt = self._scheduled_prompt(status=status, now=now)
                if scheduled_prompt is not None:
                    prompt_text, action, action_key, note = scheduled_prompt
                    plan.reply_text = prompt_text
                    plan.intent = "attract_prompt"
                    plan.proactive_action = action
                    plan.proactive_action_key = action_key
                    plan.notes.append(f"shift_policy:{action}")
                    plan.snapshot.last_policy_note = note
                else:
                    prompt = self._attract_prompt(status=status, now=now)
                    if prompt is not None:
                        plan.reply_text = prompt
                        plan.intent = "attract_prompt"
                        plan.proactive_action = "attract_prompt"
                        plan.notes.append("shift_policy:attract_prompt")
                        plan.snapshot.last_policy_note = "attract_prompt"
                    else:
                        plan.notes.append("shift_policy:tick_noop")
                        plan.snapshot.last_policy_note = "tick_noop"

        self._set_next_scheduled_prompt(status, now=now)
        status.timers = self._timers(status, now=now)
        persisted = self.memory.replace_shift_supervisor(status)
        plan.snapshot = persisted
        return plan

    def evaluate_post_response(
        self,
        *,
        event: RobotEvent,
        session: SessionRecord | None,
        response: CommandBatch,
        intent: str,
        proactive_action: str | None = None,
        proactive_action_key: str | None = None,
    ) -> ShiftSupervisorPlan:
        now = ensure_utc(event.timestamp)
        status = self.memory.get_shift_supervisor()
        world_model = self.memory.get_world_model()
        world_state = self.memory.get_world_state()

        if session is not None:
            status.active_session_id = session.session_id
            status.active_user_id = session.user_id

        if event.event_type == "speech_transcript":
            status.last_interaction_at = now
            status.follow_up_deadline_at = None
            if session is not None and session.status == SessionStatus.ESCALATION_PENDING:
                target_state = ShiftOperatingState.OPERATOR_HANDOFF_PENDING
                reason_codes = ["operator_handoff_pending"]
            elif response.reply_text:
                status.follow_up_deadline_at = now + timedelta(seconds=self.settings.shift_follow_up_window_seconds)
                target_state = ShiftOperatingState.WAITING_FOR_FOLLOW_UP
                reason_codes = ["waiting_for_follow_up_window_active"]
            else:
                target_state, reason_codes = self._target_state(
                    status=status,
                    now=now,
                    session=session,
                    world_model=world_model,
                    world_state=world_state,
                    event_type=event.event_type,
                )
        elif event.event_type in {"person_detected", "person_visible"} and response.reply_text:
            status.follow_up_deadline_at = now + timedelta(seconds=self.settings.shift_follow_up_window_seconds)
            status.last_greeting_at = now
            status.last_proactive_outreach_at = now
            status.outreach_cooldown_until = now + timedelta(seconds=self.settings.shift_outreach_cooldown_seconds)
            status.last_proactive_action = "auto_greet"
            target_state = ShiftOperatingState.WAITING_FOR_FOLLOW_UP
            reason_codes = ["auto_greet_waiting_for_follow_up"]
        elif event.event_type == "shift_autonomy_tick" and response.reply_text:
            status.last_proactive_outreach_at = now
            status.outreach_cooldown_until = now + timedelta(seconds=self.settings.shift_outreach_cooldown_seconds)
            status.last_proactive_action = proactive_action or "attract_prompt"
            if proactive_action_key:
                status.last_scheduled_prompt_at = now
                status.last_scheduled_prompt_type = proactive_action
                status.last_scheduled_prompt_key = proactive_action_key
                status.issued_scheduled_prompt_keys = [
                    *status.issued_scheduled_prompt_keys[-19:],
                    proactive_action_key,
                ]
                target_state, reason_codes = self._target_state(
                    status=status,
                    now=now,
                    session=session,
                    world_model=world_model,
                    world_state=world_state,
                    event_type=event.event_type,
                )
                reason_codes = [*reason_codes, f"{proactive_action or 'scheduled_prompt'}_issued"]
            else:
                status.last_attract_prompt_at = now
                target_state = ShiftOperatingState.ATTRACTING_ATTENTION
                reason_codes = ["attract_prompt_issued"]
        elif event.event_type == "low_battery":
            target_state = ShiftOperatingState.SAFE_IDLE
            reason_codes = ["low_battery_safe_idle"]
        elif event.event_type in {"person_left", "people_count_changed"} and not status.person_present:
            status.follow_up_deadline_at = None
            target_state, reason_codes = self._target_state(
                status=status,
                now=now,
                session=session,
                world_model=world_model,
                world_state=world_state,
                event_type=event.event_type,
            )
        else:
            target_state, reason_codes = self._target_state(
                status=status,
                now=now,
                session=session,
                world_model=world_model,
                world_state=world_state,
                event_type=event.event_type,
            )

        if status.follow_up_deadline_at and status.follow_up_deadline_at <= now:
            status.follow_up_deadline_at = None
            target_state, reason_codes = self._target_state(
                status=status,
                now=now,
                session=session,
                world_model=world_model,
                world_state=world_state,
                event_type="follow_up_timeout",
            )

        transitions = self._apply_state(
            status,
            target_state=target_state,
            reason_codes=reason_codes,
            trigger=f"{event.event_type}:post_response",
            session_id=session.session_id if session else event.session_id,
            note=status.last_policy_note,
            proactive_action=proactive_action,
            now=now,
        )
        self._set_next_scheduled_prompt(status, now=now)
        status.timers = self._timers(status, now=now)
        persisted = self.memory.replace_shift_supervisor(status)
        return ShiftSupervisorPlan(
            snapshot=persisted,
            transitions=transitions,
            reason_codes=reason_codes,
            proactive_action=proactive_action,
        )

    def _apply_signal_updates(
        self,
        status: ShiftSupervisorSnapshot,
        *,
        event: RobotEvent,
        world_model: EmbodiedWorldModel,
    ) -> None:
        now = ensure_utc(event.timestamp)
        people_count = len(world_model.active_participants_in_view)
        if event.event_type in {"person_detected", "person_visible"}:
            count = int(event.payload.get("people_count") or people_count or 1)
            if not status.person_present:
                status.presence_started_at = now
            status.person_present = True
            status.people_count = max(count, 1)
            status.last_presence_at = now
        elif event.event_type == "person_left":
            status.person_present = False
            status.people_count = 0
            status.presence_started_at = None
        elif event.event_type == "people_count_changed":
            count = int(event.payload.get("people_count") or 0)
            status.person_present = count > 0
            status.people_count = max(count, 0)
            if count > 0:
                status.last_presence_at = now
                status.presence_started_at = status.presence_started_at or now
            else:
                status.presence_started_at = None
        elif event.event_type == "shift_autonomy_tick":
            recent_presence = bool(
                status.last_presence_at
                and (now - status.last_presence_at) <= timedelta(seconds=max(15.0, self.settings.shift_attract_prompt_delay_seconds))
            )
            status.person_present = people_count > 0 or recent_presence
            status.people_count = people_count if people_count > 0 else (1 if recent_presence else 0)
            if status.person_present:
                status.last_presence_at = status.last_presence_at or now
                status.presence_started_at = status.presence_started_at or status.last_presence_at or now
            else:
                status.presence_started_at = None

        battery_pct = event.payload.get("battery_pct")
        if event.event_type == "low_battery" or (
            isinstance(battery_pct, (int, float)) and float(battery_pct) <= self.settings.shift_low_battery_threshold_pct
        ):
            status.low_battery_active = True
            status.safe_idle_active = True
        elif isinstance(battery_pct, (int, float)) and float(battery_pct) > self.settings.shift_low_battery_threshold_pct + 5.0:
            status.low_battery_active = False

        transport_degraded = False
        if event.event_type == "heartbeat" and not bool(event.payload.get("network_ok", True)):
            transport_degraded = True
        if event.payload.get("transport_ok") is False:
            transport_degraded = True
        if str(event.payload.get("edge_transport_state") or "").strip().lower() == "degraded":
            transport_degraded = True
        if str(event.payload.get("mode") or "").strip().lower() == "degraded_safe_idle":
            status.safe_idle_active = True
            transport_degraded = True
        if bool(event.payload.get("safe_idle_active", False)):
            status.safe_idle_active = True
        status.transport_degraded = transport_degraded or status.transport_degraded
        if event.payload.get("transport_ok") is True and event.payload.get("edge_transport_state") == "healthy":
            status.transport_degraded = False
            if not status.low_battery_active:
                status.safe_idle_active = False

    def _target_state(
        self,
        *,
        status: ShiftSupervisorSnapshot,
        now: datetime,
        session: SessionRecord | None,
        world_model: EmbodiedWorldModel,
        world_state: WorldState,
        event_type: str,
    ) -> tuple[ShiftOperatingState, list[str]]:
        del world_state

        schedule_status = self.schedule.status(now)
        status.next_open_at = schedule_status.next_open_at
        status.next_close_at = schedule_status.next_close_at
        status.venue_timezone = schedule_status.timezone_name
        status.quiet_hours_active = schedule_status.quiet_hours_active or not schedule_status.is_open
        status.closing_active = schedule_status.is_closing
        schedule_enforced = event_type == "shift_autonomy_tick" or status.state in {
            ShiftOperatingState.QUIET_HOURS,
            ShiftOperatingState.CLOSING,
        }

        if status.override_active and status.override_state is not None:
            reasons = ["operator_override_active"]
            if status.override_reason:
                reasons.append(status.override_reason)
            if status.override_state == ShiftOperatingState.SAFE_IDLE:
                status.safe_idle_active = True
            return status.override_state, reasons

        if status.low_battery_active or status.safe_idle_active:
            return ShiftOperatingState.SAFE_IDLE, ["low_battery_safe_idle" if status.low_battery_active else "safe_idle_active"]
        if status.transport_degraded:
            return ShiftOperatingState.DEGRADED, ["edge_transport_degraded"]
        if schedule_enforced and not schedule_status.is_open:
            return ShiftOperatingState.QUIET_HOURS, ["venue_closed"]
        if schedule_enforced and schedule_status.is_closing:
            return ShiftOperatingState.CLOSING, ["closing_window_active"]
        if schedule_enforced and schedule_status.quiet_hours_active:
            return ShiftOperatingState.QUIET_HOURS, ["quiet_hours_active"]
        if session is not None and session.status == SessionStatus.ESCALATION_PENDING:
            return ShiftOperatingState.OPERATOR_HANDOFF_PENDING, ["operator_handoff_pending"]
        if status.follow_up_deadline_at and status.follow_up_deadline_at > now:
            return ShiftOperatingState.WAITING_FOR_FOLLOW_UP, ["waiting_for_follow_up_window_active"]
        if event_type == "speech_transcript":
            return ShiftOperatingState.ASSISTING, ["active_conversation_turn"]
        if status.person_present or len(world_model.active_participants_in_view) > 0:
            return ShiftOperatingState.ATTRACTING_ATTENTION, ["visitor_present_idle"]
        return ShiftOperatingState.READY_IDLE, ["ready_for_shift_work"]

    def _apply_state(
        self,
        status: ShiftSupervisorSnapshot,
        *,
        target_state: ShiftOperatingState,
        reason_codes: list[str],
        trigger: str,
        session_id: str | None,
        note: str | None,
        now: datetime,
        proactive_action: str | None = None,
    ) -> list[ShiftTransitionRecord]:
        transitions: list[ShiftTransitionRecord] = []
        if status.state != target_state:
            transitions.append(
                ShiftTransitionRecord(
                    session_id=session_id,
                    trigger=trigger,
                    from_state=status.state,
                    to_state=target_state,
                    reason_codes=list(reason_codes),
                    proactive_action=proactive_action,
                    note=note,
                    created_at=now,
                )
            )
            status.last_transition_at = now
        status.state = target_state
        status.reason_codes = list(reason_codes)
        status.updated_at = now
        return transitions

    def _suppress_presence_outreach(self, *, status: ShiftSupervisorSnapshot, now: datetime) -> bool:
        schedule_status = self.schedule.status(now)
        if self.venue_knowledge.operations.proactive_greeting_policy.suppress_during_quiet_hours and schedule_status.quiet_hours_active:
            return True
        if status.state in {
            ShiftOperatingState.QUIET_HOURS,
            ShiftOperatingState.CLOSING,
            ShiftOperatingState.SAFE_IDLE,
            ShiftOperatingState.DEGRADED,
            ShiftOperatingState.OPERATOR_HANDOFF_PENDING,
        }:
            return True
        return False

    def _attract_prompt(self, *, status: ShiftSupervisorSnapshot, now: datetime) -> str | None:
        policy = self.venue_knowledge.operations.announcement_policy
        if not policy.enabled:
            return None
        if status.state not in {
            ShiftOperatingState.READY_IDLE,
            ShiftOperatingState.ATTRACTING_ATTENTION,
        }:
            return None
        if not status.person_present or status.presence_started_at is None:
            return None
        if status.follow_up_deadline_at and status.follow_up_deadline_at > now:
            return None
        if self._within_outreach_cooldown(status, now=now):
            return None
        if (now - status.presence_started_at) < timedelta(seconds=self.settings.shift_attract_prompt_delay_seconds):
            return None
        if policy.quiet_hours_suppressed and status.quiet_hours_active:
            return None
        suggestions = policy.proactive_suggestions
        if suggestions:
            index = min(len(suggestions) - 1, max(0, len(status.issued_scheduled_prompt_keys) % len(suggestions)))
            return suggestions[index]
        return "Hi there. I can help with directions, today's events, or a staff handoff."

    def _within_outreach_cooldown(self, status: ShiftSupervisorSnapshot, *, now: datetime) -> bool:
        return bool(status.outreach_cooldown_until and status.outreach_cooldown_until > now)

    def _timers(self, status: ShiftSupervisorSnapshot, *, now: datetime) -> list[ShiftTimerSnapshot]:
        timers: list[ShiftTimerSnapshot] = []
        timers.append(self._timer("follow_up_window", status.follow_up_deadline_at, now))
        timers.append(self._timer("outreach_cooldown", status.outreach_cooldown_until, now))
        presence_deadline = None
        if status.person_present and status.presence_started_at is not None:
            presence_deadline = status.presence_started_at + timedelta(seconds=self.settings.shift_attract_prompt_delay_seconds)
        timers.append(self._timer("presence_settle", presence_deadline, now))
        timers.append(self._timer("next_scheduled_prompt", status.next_scheduled_prompt_at, now))
        return timers

    @staticmethod
    def _timer(name: str, deadline_at: datetime | None, now: datetime) -> ShiftTimerSnapshot:
        if deadline_at is None:
            return ShiftTimerSnapshot(timer_name=name, active=False)
        remaining = max(0.0, round((deadline_at - now).total_seconds(), 2))
        return ShiftTimerSnapshot(
            timer_name=name,
            active=deadline_at > now,
            deadline_at=deadline_at,
            remaining_seconds=remaining,
        )

    def _scheduled_prompt(
        self,
        *,
        status: ShiftSupervisorSnapshot,
        now: datetime,
    ) -> tuple[str, str, str, str] | None:
        policy = self.venue_knowledge.operations.announcement_policy
        if not policy.enabled:
            return None
        if status.state in {
            ShiftOperatingState.SAFE_IDLE,
            ShiftOperatingState.DEGRADED,
            ShiftOperatingState.OPERATOR_HANDOFF_PENDING,
        }:
            return None
        if policy.quiet_hours_suppressed and status.quiet_hours_active:
            return None

        opening_prompt = self._opening_prompt(status=status, now=now)
        if opening_prompt is not None:
            return opening_prompt

        closing_prompt = self._closing_prompt(status=status, now=now)
        if closing_prompt is not None:
            return closing_prompt

        event_prompt = self._event_prompt(status=status, now=now)
        if event_prompt is not None:
            return event_prompt

        return None

    def _opening_prompt(
        self,
        *,
        status: ShiftSupervisorSnapshot,
        now: datetime,
    ) -> tuple[str, str, str, str] | None:
        policy = self.venue_knowledge.operations.announcement_policy
        if not policy.opening_prompt_text or status.state == ShiftOperatingState.QUIET_HOURS:
            return None
        local_now = ensure_utc(now).astimezone(self.schedule.tz)
        open_window = policy.opening_prompt_window_minutes
        if status.next_open_at is not None and status.next_open_at > now:
            return None
        prompt_key = f"opening_prompt:{local_now.date().isoformat()}"
        if prompt_key in status.issued_scheduled_prompt_keys:
            return None
        open_start = find_current_open_window_start(self.schedule.windows, localized=local_now)
        if open_start is None:
            return None
        open_start_utc = open_start.astimezone(timezone.utc)
        if status.last_proactive_outreach_at and status.last_proactive_outreach_at >= open_start_utc:
            return None
        if local_now > open_start + timedelta(minutes=open_window):
            return None
        return (
            policy.opening_prompt_text,
            "opening_prompt",
            prompt_key,
            "opening_prompt_due",
        )

    def _closing_prompt(
        self,
        *,
        status: ShiftSupervisorSnapshot,
        now: datetime,
    ) -> tuple[str, str, str, str] | None:
        policy = self.venue_knowledge.operations.announcement_policy
        if not policy.closing_prompt_text or not status.closing_active:
            return None
        local_now = ensure_utc(now).astimezone(self.schedule.tz)
        prompt_key = f"closing_prompt:{local_now.date().isoformat()}:{status.next_close_at.isoformat() if status.next_close_at else 'none'}"
        if prompt_key in status.issued_scheduled_prompt_keys:
            return None
        return (
            policy.closing_prompt_text,
            "closing_prompt",
            prompt_key,
            "closing_prompt_due",
        )

    def _event_prompt(
        self,
        *,
        status: ShiftSupervisorSnapshot,
        now: datetime,
    ) -> tuple[str, str, str, str] | None:
        policy = self.venue_knowledge.operations.announcement_policy
        if not policy.event_start_reminder_enabled:
            return None
        if not status.person_present:
            return None
        lead = timedelta(minutes=policy.event_start_reminder_lead_minutes)
        for event in self.venue_knowledge.events:
            if event.start_at <= now:
                continue
            reminder_at = event.start_at - lead
            if reminder_at > now:
                continue
            prompt_key = f"event_prompt:{event.event_id}:{event.start_at.isoformat()}"
            if prompt_key in status.issued_scheduled_prompt_keys:
                continue
            location = event.location_label or "the listed venue space"
            text = (
                policy.event_start_reminder_text.replace("{event_title}", event.title).replace("{location}", location)
                if policy.event_start_reminder_text
                else f"Upcoming reminder: {event.title} starts soon in {location}."
            )
            return (
                text,
                "event_start_reminder",
                prompt_key,
                f"event_start_reminder_due:{event.event_id}",
            )
        return None

    def _set_next_scheduled_prompt(self, status: ShiftSupervisorSnapshot, *, now: datetime) -> None:
        next_at: datetime | None = None
        next_type: str | None = None
        next_note: str | None = None
        policy = self.venue_knowledge.operations.announcement_policy
        if policy.enabled:
            local_now = ensure_utc(now).astimezone(self.schedule.tz)
            open_start = find_next_open_window_start(self.schedule.windows, localized=local_now)
            if (
                policy.opening_prompt_text
                and open_start is not None
                and f"opening_prompt:{open_start.date().isoformat()}" not in status.issued_scheduled_prompt_keys
            ):
                next_at = open_start.astimezone(timezone.utc)
                next_type = "opening_prompt"
                next_note = "opening_prompt_due"
            closing_start = find_next_window_start(self.schedule.closing_windows, localized=local_now)
            if policy.closing_prompt_text and closing_start is not None:
                closing_due = closing_start.astimezone(timezone.utc)
                if next_at is None or closing_due < next_at:
                    next_at = closing_due
                    next_type = "closing_prompt"
                    next_note = "closing_prompt_due"
            if policy.event_start_reminder_enabled:
                lead = timedelta(minutes=policy.event_start_reminder_lead_minutes)
                for event in self.venue_knowledge.events:
                    reminder_at = event.start_at - lead
                    key = f"event_prompt:{event.event_id}:{event.start_at.isoformat()}"
                    if reminder_at <= now or key in status.issued_scheduled_prompt_keys:
                        continue
                    if next_at is None or reminder_at < next_at:
                        next_at = reminder_at
                        next_type = "event_start_reminder"
                        next_note = f"event_start_reminder_due:{event.event_id}"
                    break
        status.next_scheduled_prompt_at = next_at
        status.next_scheduled_prompt_type = next_type
        status.next_scheduled_prompt_note = next_note

    def _fallback_reply(self, *, scenario: VenueFallbackScenario, default: str) -> str:
        instruction = self.venue_knowledge.fallback_instruction(scenario)
        if instruction is None:
            return default
        return instruction.visitor_message


def ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def schedule_windows_from_operations(windows: list[VenueScheduleWindow]) -> list[ScheduleWindow]:
    resolved: list[ScheduleWindow] = []
    for window in windows:
        for day_name in window.days:
            weekday = DAY_NAMES.get(day_name.lower())
            if weekday is None:
                continue
            resolved.append(
                ScheduleWindow(
                    weekday=weekday,
                    opens_at=window.start_local,
                    closes_at=window.end_local,
                )
            )
    return resolved


def derive_closing_windows(windows: list[ScheduleWindow], closing_lead_minutes: int) -> list[ScheduleWindow]:
    lead = max(0, closing_lead_minutes)
    derived: list[ScheduleWindow] = []
    reference_date = utc_now().date()
    for window in windows:
        close_at = datetime.combine(reference_date, window.closes_at)
        open_at = datetime.combine(reference_date, window.opens_at)
        start = max(open_at, close_at - timedelta(minutes=lead))
        if start.time() >= window.closes_at:
            continue
        derived.append(
            ScheduleWindow(
                weekday=window.weekday,
                opens_at=start.time(),
                closes_at=window.closes_at,
            )
        )
    return derived


def find_current_open_window_start(windows: list[ScheduleWindow], *, localized: datetime) -> datetime | None:
    return find_current_window_start(windows, localized=localized)


def find_next_open_window_start(windows: list[ScheduleWindow], *, localized: datetime) -> datetime | None:
    return find_next_window_start(windows, localized=localized)


def find_current_window_start(windows: list[ScheduleWindow], *, localized: datetime) -> datetime | None:
    today = localized.date()
    current_time = localized.timetz().replace(tzinfo=None)
    for window in sorted((item for item in windows if item.weekday == localized.weekday()), key=lambda item: item.opens_at):
        if window.opens_at <= current_time < window.closes_at:
            return datetime.combine(today, window.opens_at, tzinfo=localized.tzinfo)
    return None


def find_next_window_start(windows: list[ScheduleWindow], *, localized: datetime) -> datetime | None:
    for offset in range(0, 8):
        candidate_date = localized.date() + timedelta(days=offset)
        candidate_windows = sorted(
            (item for item in windows if item.weekday == candidate_date.weekday()),
            key=lambda item: item.opens_at,
        )
        for window in candidate_windows:
            candidate = datetime.combine(candidate_date, window.opens_at, tzinfo=localized.tzinfo)
            if candidate > localized:
                return candidate
    return None


def parse_hours_summary(summary: str) -> list[ScheduleWindow]:
    if not summary.strip():
        return []

    day_pattern = r"(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)"
    pattern = re.compile(
        rf"(?P<days>{day_pattern}(?:\s+(?:through|to)\s+{day_pattern})?(?:\s*,\s*{day_pattern})*(?:\s+and\s+{day_pattern})?)\s+from\s+(?P<start>\d{{1,2}}(?::\d{{2}})?\s*[ap]m)\s+to\s+(?P<end>\d{{1,2}}(?::\d{{2}})?\s*[ap]m)",
        re.IGNORECASE,
    )

    windows: list[ScheduleWindow] = []
    for match in pattern.finditer(summary):
        weekdays = expand_days(match.group("days"))
        opens_at = parse_clock_time(match.group("start"))
        closes_at = parse_clock_time(match.group("end"))
        if not weekdays:
            continue
        windows.extend(
            ScheduleWindow(weekday=weekday, opens_at=opens_at, closes_at=closes_at)
            for weekday in weekdays
        )
    return windows


def expand_days(days_text: str) -> list[int]:
    normalized = days_text.lower().replace(",", " and ")
    normalized = re.sub(r"\s+", " ", normalized).strip()
    if " through " in normalized:
        start_name, end_name = normalized.split(" through ", 1)
        return expand_day_range(start_name.strip(), end_name.strip())
    if " to " in normalized:
        start_name, end_name = normalized.split(" to ", 1)
        return expand_day_range(start_name.strip(), end_name.strip())
    parts = [item.strip() for item in normalized.split(" and ") if item.strip()]
    return [DAY_NAMES[item] for item in parts if item in DAY_NAMES]


def expand_day_range(start_name: str, end_name: str) -> list[int]:
    if start_name not in DAY_NAMES or end_name not in DAY_NAMES:
        return []
    start = DAY_NAMES[start_name]
    end = DAY_NAMES[end_name]
    days: list[int] = [start]
    while days[-1] != end:
        days.append((days[-1] + 1) % 7)
        if len(days) > 7:
            return []
    return days


def parse_clock_time(value: str) -> time:
    normalized = re.sub(r"\s+", " ", value.strip().upper())
    for fmt in ("%I:%M %p", "%I %p"):
        try:
            return datetime.strptime(normalized, fmt).time()
        except ValueError:
            continue
    raise ValueError(f"unsupported_clock_time:{value}")
