from __future__ import annotations

from datetime import datetime, timedelta

from embodied_stack.shared.models import ShiftSupervisorSnapshot


def proactive_eligible(
    *,
    shift_snapshot: ShiftSupervisorSnapshot,
    now: datetime,
    attract_prompt_delay_seconds: float,
) -> bool:
    if shift_snapshot.safe_idle_active or shift_snapshot.transport_degraded or shift_snapshot.quiet_hours_active:
        return False
    if shift_snapshot.outreach_cooldown_until and shift_snapshot.outreach_cooldown_until > now:
        return False
    if shift_snapshot.person_present and shift_snapshot.presence_started_at is not None:
        settle_at = shift_snapshot.presence_started_at + timedelta(seconds=attract_prompt_delay_seconds)
        if settle_at > now:
            return False
    return True


def suppressed_reason(
    *,
    shift_snapshot: ShiftSupervisorSnapshot,
    now: datetime,
    attract_prompt_delay_seconds: float,
) -> str:
    if shift_snapshot.safe_idle_active:
        return "safe_idle_active"
    if shift_snapshot.transport_degraded:
        return "transport_degraded"
    if shift_snapshot.quiet_hours_active:
        return "quiet_hours_active"
    if shift_snapshot.outreach_cooldown_until and shift_snapshot.outreach_cooldown_until > now:
        return "outreach_cooldown"
    if shift_snapshot.person_present and shift_snapshot.presence_started_at is not None:
        settle_at = shift_snapshot.presence_started_at + timedelta(seconds=attract_prompt_delay_seconds)
        if settle_at > now:
            return "presence_settling"
    return "not_eligible"


__all__ = [
    "proactive_eligible",
    "suppressed_reason",
]
