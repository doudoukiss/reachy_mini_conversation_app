from __future__ import annotations

from datetime import timedelta

from embodied_stack.brain.initiative import (
    BrowserContextSignal,
    CompanionInitiativeEngine,
    InitiativeContext,
    TerminalActivitySignal,
)
from embodied_stack.shared.models import (
    CompanionPresenceStatus,
    CompanionRelationshipProfile,
    CompanionVoiceLoopStatus,
    InitiativeDecision,
    ReminderRecord,
    SessionDigestRecord,
    SessionRecord,
    ShiftOperatingState,
    ShiftSupervisorSnapshot,
    UserMemoryRecord,
    utc_now,
)


def _engine() -> CompanionInitiativeEngine:
    return CompanionInitiativeEngine(
        attract_prompt_delay_seconds=30.0,
        semantic_refresh_min_interval_seconds=15.0,
        cooldown_seconds=60.0,
    )


def _context(
    *,
    now=None,
    shift_snapshot: ShiftSupervisorSnapshot | None = None,
    user_memory: UserMemoryRecord | None = None,
    digests: tuple[SessionDigestRecord, ...] = (),
    reminders: tuple[ReminderRecord, ...] = (),
    terminal_idle_seconds: float | None = 120.0,
    browser_available: bool = False,
) -> InitiativeContext:
    current = now or utc_now()
    session = SessionRecord(
        session_id="initiative-session",
        user_id="initiative-user",
        last_user_text="Help me keep moving on this plan.",
        updated_at=current - timedelta(seconds=30),
    )
    return InitiativeContext(
        now=current,
        session=session,
        shift_snapshot=shift_snapshot
        or ShiftSupervisorSnapshot(
            state=ShiftOperatingState.READY_IDLE,
            active_session_id=session.session_id,
        ),
        presence_status=CompanionPresenceStatus(session_id=session.session_id),
        voice_status=CompanionVoiceLoopStatus(session_id=session.session_id),
        fallback_active=False,
        semantic_provider_available=True,
        fresh_semantic_scene_available=True,
        last_semantic_refresh_at=current - timedelta(seconds=5),
        observer_event=None,
        latest_perception=None,
        user_memory=user_memory,
        digests=digests,
        open_reminders=reminders,
        browser_context=BrowserContextSignal(
            available=browser_available,
            current_url="https://example.com/tasks" if browser_available else None,
            page_title="Tasks" if browser_available else None,
            summary="Task board" if browser_available else None,
        ),
        terminal_activity=TerminalActivitySignal(
            source="local_companion_typed",
            idle_seconds=terminal_idle_seconds,
            last_user_text=session.last_user_text,
        ),
    )


def test_initiative_engine_asks_for_due_follow_up_when_idle() -> None:
    now = utc_now()
    context = _context(
        now=now,
        shift_snapshot=ShiftSupervisorSnapshot(
            state=ShiftOperatingState.WAITING_FOR_FOLLOW_UP,
            active_session_id="initiative-session",
            follow_up_deadline_at=now - timedelta(seconds=5),
        ),
        digests=(
            SessionDigestRecord(
                session_id="initiative-session",
                user_id="initiative-user",
                summary="Open planning thread.",
                open_follow_ups=["booking the train"],
            ),
        ),
        browser_available=True,
    )

    evaluation = _engine().evaluate(context)

    assert evaluation.decision == InitiativeDecision.ASK
    assert evaluation.candidate_kind == "follow_up_due"
    assert evaluation.workflow_id is None
    assert evaluation.scorecard.relevance >= 0.85
    assert evaluation.grounding.follow_up_count == 1


def test_initiative_engine_ignores_recent_terminal_activity() -> None:
    now = utc_now()
    context = _context(
        now=now,
        shift_snapshot=ShiftSupervisorSnapshot(
            state=ShiftOperatingState.WAITING_FOR_FOLLOW_UP,
            active_session_id="initiative-session",
            follow_up_deadline_at=now - timedelta(seconds=5),
        ),
        terminal_idle_seconds=3.0,
    )

    evaluation = _engine().evaluate(context)

    assert evaluation.decision == InitiativeDecision.IGNORE
    assert evaluation.suppression_reason == "recent_terminal_activity"
    assert evaluation.candidate_kind == "follow_up_due"


def test_initiative_engine_blocks_when_relationship_boundary_requests_silence() -> None:
    now = utc_now()
    context = _context(
        now=now,
        shift_snapshot=ShiftSupervisorSnapshot(
            state=ShiftOperatingState.WAITING_FOR_FOLLOW_UP,
            active_session_id="initiative-session",
            follow_up_deadline_at=now - timedelta(seconds=5),
        ),
        user_memory=UserMemoryRecord(
            user_id="initiative-user",
            relationship_profile=CompanionRelationshipProfile(
                interaction_boundaries=["only when asked"],
            ),
        ),
    )

    evaluation = _engine().evaluate(context)

    assert evaluation.decision == InitiativeDecision.IGNORE
    assert evaluation.suppression_reason == "relationship_boundary_active"


def test_initiative_engine_allows_due_reminder_auto_action_when_idle() -> None:
    now = utc_now()
    context = _context(
        now=now,
        reminders=(
            ReminderRecord(
                session_id="initiative-session",
                user_id="initiative-user",
                reminder_text="Pay the electric bill.",
                due_at=now - timedelta(minutes=8),
            ),
        ),
        terminal_idle_seconds=180.0,
    )

    evaluation = _engine().evaluate(context)

    assert evaluation.decision == InitiativeDecision.ACT
    assert evaluation.candidate_kind == "due_reminder_follow_up"
    assert evaluation.workflow_id == "reminder_due_follow_up"
    assert evaluation.workflow_inputs["reminder_id"]
    assert evaluation.scorecard.risk <= 0.22
