from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from embodied_stack.brain.perception.semantic_refresh import SemanticRefreshPolicy
from embodied_stack.brain.social.attract_mode_policy import proactive_eligible, suppressed_reason
from embodied_stack.shared.models import (
    BrowserRuntimeStatusRecord,
    CompanionPresenceState,
    CompanionPresenceStatus,
    CompanionVoiceLoopState,
    CompanionVoiceLoopStatus,
    InitiativeDecision,
    InitiativeGroundingRecord,
    InitiativeScorecardRecord,
    InitiativeStage,
    InitiativeStatus,
    PerceptionSnapshotRecord,
    ReminderRecord,
    SceneObserverEventRecord,
    SessionDigestRecord,
    SessionRecord,
    ShiftOperatingState,
    ShiftSupervisorSnapshot,
    UserMemoryRecord,
    utc_now,
)


_BUSY_PRESENCE_STATES = {
    CompanionPresenceState.LISTENING,
    CompanionPresenceState.ACKNOWLEDGING,
    CompanionPresenceState.THINKING_FAST,
    CompanionPresenceState.SPEAKING,
    CompanionPresenceState.TOOL_WORKING,
}
_BUSY_VOICE_STATES = {
    CompanionVoiceLoopState.ARMED,
    CompanionVoiceLoopState.CAPTURING,
    CompanionVoiceLoopState.ENDPOINTING,
    CompanionVoiceLoopState.TRANSCRIBING,
    CompanionVoiceLoopState.THINKING,
    CompanionVoiceLoopState.SPEAKING,
    CompanionVoiceLoopState.BARGE_IN,
}


@dataclass(frozen=True)
class BrowserContextSignal:
    available: bool
    current_url: str | None = None
    page_title: str | None = None
    summary: str | None = None


@dataclass(frozen=True)
class TerminalActivitySignal:
    source: str | None
    idle_seconds: float | None
    last_user_text: str | None


@dataclass(frozen=True)
class InitiativeContext:
    now: datetime
    session: SessionRecord
    shift_snapshot: ShiftSupervisorSnapshot
    presence_status: CompanionPresenceStatus
    voice_status: CompanionVoiceLoopStatus
    fallback_active: bool
    semantic_provider_available: bool
    fresh_semantic_scene_available: bool
    last_semantic_refresh_at: datetime | None
    observer_event: SceneObserverEventRecord | None
    latest_perception: PerceptionSnapshotRecord | None
    user_memory: UserMemoryRecord | None
    digests: tuple[SessionDigestRecord, ...] = ()
    open_reminders: tuple[ReminderRecord, ...] = ()
    browser_context: BrowserContextSignal = field(default_factory=lambda: BrowserContextSignal(False))
    terminal_activity: TerminalActivitySignal = field(default_factory=lambda: TerminalActivitySignal(None, None, None))


@dataclass(frozen=True)
class InitiativeCandidate:
    kind: str
    desired_decision: InitiativeDecision
    reason: str
    reason_codes: tuple[str, ...]
    reference_at: datetime | None = None
    use_shift_prompt: bool = False
    reply_text: str | None = None
    intent: str | None = None
    proactive_action: str | None = None
    workflow_id: str | None = None
    workflow_inputs: dict[str, object] = field(default_factory=dict)
    requires_fresh_semantic_scene: bool = False


@dataclass(frozen=True)
class InitiativeEvaluation:
    stage_trace: tuple[InitiativeStage, ...]
    decision: InitiativeDecision
    candidate_kind: str | None
    candidate_count: int
    reason: str
    reason_codes: tuple[str, ...]
    scorecard: InitiativeScorecardRecord
    grounding: InitiativeGroundingRecord
    suppression_reason: str | None = None
    should_refresh_scene: bool = False
    refresh_reason: str | None = None
    use_shift_prompt: bool = False
    reply_text: str | None = None
    intent: str | None = None
    proactive_action: str | None = None
    workflow_id: str | None = None
    workflow_inputs: dict[str, object] = field(default_factory=dict)


class CompanionInitiativeEngine:
    def __init__(
        self,
        *,
        attract_prompt_delay_seconds: float,
        semantic_refresh_min_interval_seconds: float,
        cooldown_seconds: float,
        reminder_retrigger_seconds: float | None = None,
    ) -> None:
        self.attract_prompt_delay_seconds = attract_prompt_delay_seconds
        self.cooldown_seconds = max(15.0, float(cooldown_seconds))
        self.reminder_retrigger_seconds = max(
            self.cooldown_seconds,
            float(reminder_retrigger_seconds if reminder_retrigger_seconds is not None else self.cooldown_seconds * 2.0),
        )
        self.semantic_refresh_policy = SemanticRefreshPolicy(
            min_interval_seconds=semantic_refresh_min_interval_seconds,
        )
        self._status = InitiativeStatus(enabled=True)
        self._manual_silence_until: datetime | None = None

    def status(self) -> InitiativeStatus:
        return self._status.model_copy(deep=True)

    def silence(self, *, minutes: float, now: datetime | None = None) -> InitiativeStatus:
        current = now or utc_now()
        until = current + timedelta(minutes=max(0.0, minutes))
        self._manual_silence_until = until
        self._status = self._status.model_copy(
            update={
                "enabled": True,
                "current_stage": InitiativeStage.COOLDOWN,
                "last_decision": InitiativeDecision.IGNORE,
                "last_reason": "manual_silence",
                "last_reason_codes": ["manual_silence"],
                "last_evaluated_at": current,
                "cooldown_until": until,
                "suppressed": True,
                "suppression_reason": "manual_silence",
            }
        )
        return self.status()

    def clear_silence(self) -> InitiativeStatus:
        self._manual_silence_until = None
        self._status = self._status.model_copy(
            update={
                "suppressed": False,
                "suppression_reason": None,
            }
        )
        return self.status()

    def evaluate(self, context: InitiativeContext) -> InitiativeEvaluation:
        now = context.now
        stage_trace: list[InitiativeStage] = [InitiativeStage.MONITOR]
        grounding = self._grounding(context)

        hard_block = self._hard_block_reason(context, now=now)
        if hard_block is not None:
            return InitiativeEvaluation(
                stage_trace=tuple([*stage_trace, InitiativeStage.DECIDE]),
                decision=InitiativeDecision.IGNORE,
                candidate_kind=None,
                candidate_count=0,
                reason=hard_block,
                reason_codes=(hard_block,),
                scorecard=InitiativeScorecardRecord(),
                grounding=grounding,
                suppression_reason=hard_block,
            )

        candidates = self._build_candidates(context)
        stage_trace.append(InitiativeStage.CANDIDATE)
        if not candidates:
            return InitiativeEvaluation(
                stage_trace=tuple([*stage_trace, InitiativeStage.DECIDE]),
                decision=InitiativeDecision.IGNORE,
                candidate_kind=None,
                candidate_count=0,
                reason="no_candidate",
                reason_codes=("no_candidate",),
                scorecard=InitiativeScorecardRecord(),
                grounding=grounding,
            )

        stage_trace.append(InitiativeStage.INFER)
        scored = [
            (candidate, self._score_candidate(candidate, context, grounding))
            for candidate in candidates
        ]
        stage_trace.append(InitiativeStage.SCORE)
        candidate, scorecard = max(scored, key=lambda item: item[1].total)

        refresh_reason = None
        should_refresh_scene = False
        if candidate.requires_fresh_semantic_scene and context.observer_event is not None:
            refresh = self.semantic_refresh_policy.should_refresh(
                refresh_recommended=context.observer_event.refresh_recommended,
                refresh_reason=context.observer_event.refresh_reason,
                fresh_semantic_scene_available=context.fresh_semantic_scene_available,
                last_semantic_refresh_at=context.last_semantic_refresh_at,
                now=now,
            )
            should_refresh_scene = refresh.should_refresh and context.semantic_provider_available
            refresh_reason = refresh.reason

        decision, reason_codes, suppression_reason = self._decide(
            candidate=candidate,
            scorecard=scorecard,
            context=context,
            should_refresh_scene=should_refresh_scene,
        )
        stage_trace.append(InitiativeStage.DECIDE)
        if decision != InitiativeDecision.IGNORE:
            stage_trace.append(InitiativeStage.COOLDOWN)
        return InitiativeEvaluation(
            stage_trace=tuple(stage_trace),
            decision=decision,
            candidate_kind=candidate.kind,
            candidate_count=len(candidates),
            reason=candidate.reason if decision != InitiativeDecision.IGNORE else suppression_reason or "initiative_ignored",
            reason_codes=reason_codes,
            scorecard=scorecard,
            grounding=grounding,
            suppression_reason=suppression_reason,
            should_refresh_scene=should_refresh_scene,
            refresh_reason=refresh_reason,
            use_shift_prompt=candidate.use_shift_prompt,
            reply_text=candidate.reply_text,
            intent=candidate.intent,
            proactive_action=candidate.proactive_action,
            workflow_id=candidate.workflow_id if decision == InitiativeDecision.ACT else None,
            workflow_inputs=dict(candidate.workflow_inputs) if decision == InitiativeDecision.ACT else {},
        )

    def commit(
        self,
        evaluation: InitiativeEvaluation,
        *,
        acted: bool,
        now: datetime | None = None,
    ) -> InitiativeStatus:
        current = now or utc_now()
        status = self._status.model_copy(deep=True)
        status.enabled = True
        status.current_stage = InitiativeStage.COOLDOWN if acted and evaluation.decision != InitiativeDecision.IGNORE else InitiativeStage.DECIDE
        status.last_decision = evaluation.decision
        status.last_candidate_kind = evaluation.candidate_kind
        status.last_reason = evaluation.reason
        status.last_reason_codes = list(evaluation.reason_codes)
        status.last_evaluated_at = current
        status.suppressed = evaluation.decision == InitiativeDecision.IGNORE
        status.suppression_reason = evaluation.suppression_reason
        status.candidate_count = evaluation.candidate_count
        status.decision_count += 1
        status.last_scorecard = evaluation.scorecard
        status.last_grounding = evaluation.grounding
        if evaluation.decision == InitiativeDecision.IGNORE:
            status.ignore_count += 1
        elif acted:
            status.last_action_at = current
            if evaluation.decision == InitiativeDecision.SUGGEST:
                status.suggest_count += 1
            elif evaluation.decision == InitiativeDecision.ASK:
                status.ask_count += 1
            elif evaluation.decision == InitiativeDecision.ACT:
                status.act_count += 1
            status.cooldown_until = current + timedelta(seconds=self._cooldown_for(evaluation))
        self._status = status
        return self.status()

    def _hard_block_reason(self, context: InitiativeContext, *, now: datetime) -> str | None:
        if self._manual_silence_until is not None and self._manual_silence_until > now:
            return "manual_silence"
        if context.fallback_active:
            return "fallback_active"
        if context.shift_snapshot.state in {
            ShiftOperatingState.SAFE_IDLE,
            ShiftOperatingState.DEGRADED,
            ShiftOperatingState.OPERATOR_HANDOFF_PENDING,
            ShiftOperatingState.QUIET_HOURS,
        }:
            return f"shift_state:{context.shift_snapshot.state.value}"
        if context.presence_status.state in _BUSY_PRESENCE_STATES:
            return f"presence_busy:{context.presence_status.state.value}"
        if context.voice_status.state in _BUSY_VOICE_STATES:
            return f"voice_busy:{context.voice_status.state.value}"
        if self._status.cooldown_until is not None and self._status.cooldown_until > now:
            return "initiative_cooldown"
        return None

    def _build_candidates(self, context: InitiativeContext) -> list[InitiativeCandidate]:
        candidates: list[InitiativeCandidate] = []
        shift = context.shift_snapshot
        now = context.now
        follow_up_due = bool(shift.follow_up_deadline_at and shift.follow_up_deadline_at <= now)
        scheduled_prompt_due = bool(shift.next_scheduled_prompt_at and shift.next_scheduled_prompt_at <= now)
        due_reminder = self._first_due_reminder(context, now=now)

        if context.observer_event is not None and context.observer_event.refresh_recommended:
            candidates.append(
                InitiativeCandidate(
                    kind="scene_refresh_due",
                    desired_decision=InitiativeDecision.IGNORE,
                    reason="scene_refresh_due",
                    reason_codes=(
                        "scene_refresh_due",
                        context.observer_event.refresh_reason or "scene_changed",
                    ),
                    reference_at=context.observer_event.observed_at,
                    proactive_action="semantic_refresh",
                    requires_fresh_semantic_scene=True,
                )
            )
        if follow_up_due:
            candidates.append(
                InitiativeCandidate(
                    kind="follow_up_due",
                    desired_decision=InitiativeDecision.ASK,
                    reason="follow_up_due",
                    reason_codes=("follow_up_due",),
                    reference_at=shift.follow_up_deadline_at,
                    reply_text=self._follow_up_prompt(context),
                    intent="listening",
                    proactive_action="follow_up_prompt",
                )
            )
        if scheduled_prompt_due:
            candidates.append(
                InitiativeCandidate(
                    kind="scheduled_prompt_due",
                    desired_decision=InitiativeDecision.SUGGEST,
                    reason="scheduled_prompt_due",
                    reason_codes=("scheduled_prompt_due", shift.next_scheduled_prompt_type or "scheduled_prompt"),
                    reference_at=shift.next_scheduled_prompt_at,
                    use_shift_prompt=True,
                    proactive_action=shift.next_scheduled_prompt_type or "scheduled_prompt",
                    requires_fresh_semantic_scene=False,
                )
            )
        proactive_ready = proactive_eligible(
            shift_snapshot=shift,
            now=now,
            attract_prompt_delay_seconds=self.attract_prompt_delay_seconds,
        )
        if proactive_ready and shift.person_present and not follow_up_due and not scheduled_prompt_due:
            candidates.append(
                InitiativeCandidate(
                    kind="presence_reengagement",
                    desired_decision=InitiativeDecision.SUGGEST,
                    reason="person_present_idle",
                    reason_codes=("person_present_idle",),
                    reference_at=shift.presence_started_at or shift.last_presence_at,
                    use_shift_prompt=True,
                    proactive_action="attract_prompt",
                    requires_fresh_semantic_scene=True,
                )
            )
        if due_reminder is not None:
            candidates.append(
                InitiativeCandidate(
                    kind="due_reminder_follow_up",
                    desired_decision=InitiativeDecision.ACT,
                    reason="due_reminder_follow_up",
                    reason_codes=("due_reminder_follow_up",),
                    reference_at=due_reminder.due_at,
                    proactive_action="reminder_due_follow_up",
                    workflow_id="reminder_due_follow_up",
                    workflow_inputs={"reminder_id": due_reminder.reminder_id},
                )
            )
        return candidates

    def _grounding(self, context: InitiativeContext) -> InitiativeGroundingRecord:
        boundaries = self._relationship_boundary_active(context.user_memory)
        due_count = sum(
            1
            for item in context.open_reminders
            if item.due_at is not None and item.due_at <= context.now
        )
        follow_up_count = sum(len(item.open_follow_ups) for item in context.digests[:1])
        return InitiativeGroundingRecord(
            terminal_source=context.terminal_activity.source,
            terminal_idle_seconds=(
                round(context.terminal_activity.idle_seconds, 2)
                if context.terminal_activity.idle_seconds is not None
                else None
            ),
            person_present=bool(context.shift_snapshot.person_present),
            semantic_scene_fresh=context.fresh_semantic_scene_available,
            browser_context_available=context.browser_context.available,
            browser_current_url=context.browser_context.current_url,
            due_reminder_count=due_count,
            follow_up_count=follow_up_count,
            relationship_boundary_active=boundaries,
        )

    def _score_candidate(
        self,
        candidate: InitiativeCandidate,
        context: InitiativeContext,
        grounding: InitiativeGroundingRecord,
    ) -> InitiativeScorecardRecord:
        relevance = self._relevance(candidate, context)
        interruption_cost = self._interruption_cost(candidate, context)
        confidence = self._confidence(candidate, context)
        risk = self._risk(candidate)
        recency = self._recency(candidate, context)
        relationship = self._relationship_appropriateness(candidate, context)
        total = (
            (0.30 * relevance)
            + (0.20 * confidence)
            + (0.16 * recency)
            + (0.16 * relationship)
            + 0.24
            - (0.24 * interruption_cost)
            - (0.18 * risk)
        )
        if grounding.browser_context_available and candidate.kind == "follow_up_due":
            total += 0.04
        return InitiativeScorecardRecord(
            relevance=round(_clamp(relevance), 3),
            interruption_cost=round(_clamp(interruption_cost), 3),
            confidence=round(_clamp(confidence), 3),
            risk=round(_clamp(risk), 3),
            recency=round(_clamp(recency), 3),
            relationship_appropriateness=round(_clamp(relationship), 3),
            total=round(_clamp(total), 3),
        )

    def _decide(
        self,
        *,
        candidate: InitiativeCandidate,
        scorecard: InitiativeScorecardRecord,
        context: InitiativeContext,
        should_refresh_scene: bool,
    ) -> tuple[InitiativeDecision, tuple[str, ...], str | None]:
        reason_codes = list(candidate.reason_codes)
        if should_refresh_scene:
            reason_codes.append("semantic_refresh_before_reengagement")
            return InitiativeDecision.IGNORE, tuple(reason_codes), "semantic_refresh_required"
        if self._relationship_boundary_active(context.user_memory):
            reason_codes.append("relationship_boundary_active")
            return InitiativeDecision.IGNORE, tuple(reason_codes), "relationship_boundary_active"
        if context.terminal_activity.idle_seconds is not None and context.terminal_activity.idle_seconds < 10.0:
            reason_codes.append("recent_terminal_activity")
            return InitiativeDecision.IGNORE, tuple(reason_codes), "recent_terminal_activity"
        if candidate.desired_decision == InitiativeDecision.ACT:
            if scorecard.total >= 0.62 and scorecard.risk <= 0.28 and scorecard.interruption_cost <= 0.35 and scorecard.confidence >= 0.78:
                return InitiativeDecision.ACT, tuple(reason_codes), None
            return InitiativeDecision.IGNORE, tuple([*reason_codes, "act_threshold_not_met"]), "act_threshold_not_met"
        if candidate.desired_decision == InitiativeDecision.ASK:
            if scorecard.total >= 0.55 and scorecard.confidence >= 0.65 and scorecard.interruption_cost <= 0.62:
                return InitiativeDecision.ASK, tuple(reason_codes), None
            return InitiativeDecision.IGNORE, tuple([*reason_codes, "ask_threshold_not_met"]), "ask_threshold_not_met"
        if scorecard.total >= 0.5 and scorecard.confidence >= 0.58 and scorecard.interruption_cost <= 0.7:
            return InitiativeDecision.SUGGEST, tuple(reason_codes), None
        return InitiativeDecision.IGNORE, tuple([*reason_codes, "suggest_threshold_not_met"]), "suggest_threshold_not_met"

    def _relevance(self, candidate: InitiativeCandidate, context: InitiativeContext) -> float:
        if candidate.kind == "scene_refresh_due":
            relevance = 0.62
            if context.observer_event is not None and context.observer_event.person_present:
                relevance += 0.12
            return relevance
        if candidate.kind == "follow_up_due":
            return 0.88 if any(item.open_follow_ups for item in context.digests[:1]) else 0.74
        if candidate.kind == "scheduled_prompt_due":
            return 0.7
        if candidate.kind == "presence_reengagement":
            relevance = 0.58
            if context.observer_event is not None and (context.observer_event.attention_toward_device_score or 0.0) >= 0.65:
                relevance += 0.16
            if context.browser_context.available:
                relevance += 0.06
            return relevance
        if candidate.kind == "due_reminder_follow_up":
            overdue_bonus = 0.12 if any(
                item.due_at is not None and (context.now - item.due_at).total_seconds() >= 300
                for item in context.open_reminders
            ) else 0.0
            return 0.8 + overdue_bonus
        return 0.4

    def _interruption_cost(self, candidate: InitiativeCandidate, context: InitiativeContext) -> float:
        idle = context.terminal_activity.idle_seconds
        if idle is None:
            cost = 0.42
        elif idle < 10:
            cost = 0.96
        elif idle < 30:
            cost = 0.78
        elif idle < 60:
            cost = 0.56
        elif idle < 120:
            cost = 0.36
        else:
            cost = 0.18
        if context.shift_snapshot.person_present and context.observer_event is not None:
            score = context.observer_event.attention_toward_device_score or 0.0
            if score >= 0.65 and candidate.desired_decision != InitiativeDecision.ACT:
                cost -= 0.18
        if candidate.desired_decision == InitiativeDecision.ACT and not context.shift_snapshot.person_present:
            cost -= 0.1
        return _clamp(cost)

    def _confidence(self, candidate: InitiativeCandidate, context: InitiativeContext) -> float:
        if candidate.kind == "scene_refresh_due":
            confidence = 0.64
            if context.observer_event is not None and context.observer_event.signal_confidence is not None:
                confidence += max(0.0, min(0.18, context.observer_event.signal_confidence * 0.24))
            return confidence
        if candidate.kind == "follow_up_due":
            return 0.86 if any(item.open_follow_ups for item in context.digests[:1]) else 0.72
        if candidate.kind == "scheduled_prompt_due":
            return 0.78
        if candidate.kind == "presence_reengagement":
            confidence = 0.54
            if context.fresh_semantic_scene_available:
                confidence += 0.22
            elif context.observer_event is not None and context.observer_event.signal_confidence is not None:
                confidence += max(0.0, min(0.16, context.observer_event.signal_confidence * 0.2))
            return confidence
        if candidate.kind == "due_reminder_follow_up":
            return 0.92
        return 0.45

    @staticmethod
    def _risk(candidate: InitiativeCandidate) -> float:
        if candidate.desired_decision == InitiativeDecision.ACT:
            return 0.22
        if candidate.desired_decision == InitiativeDecision.ASK:
            return 0.12
        return 0.16

    def _recency(self, candidate: InitiativeCandidate, context: InitiativeContext) -> float:
        reference = candidate.reference_at or context.session.updated_at
        age_seconds = max(0.0, (context.now - reference).total_seconds()) if reference is not None else 60.0
        if age_seconds <= 15.0:
            return 0.92
        if age_seconds <= 60.0:
            return 0.76
        if age_seconds <= 300.0:
            return 0.58
        return 0.34

    def _relationship_appropriateness(self, candidate: InitiativeCandidate, context: InitiativeContext) -> float:
        user_memory = context.user_memory
        if user_memory is None:
            return 0.5
        profile = user_memory.relationship_profile
        if self._relationship_boundary_active(user_memory):
            return 0.12
        score = 0.58
        if profile.greeting_preference:
            score += 0.06
        if profile.planning_style:
            score += 0.08
        if candidate.kind in {"follow_up_due", "due_reminder_follow_up"} and any(
            "follow" in item.lower() or "plan" in item.lower() or "reminder" in item.lower()
            for item in profile.continuity_preferences
        ):
            score += 0.16
        return _clamp(score)

    def _cooldown_for(self, evaluation: InitiativeEvaluation) -> float:
        if evaluation.decision == InitiativeDecision.ACT:
            return max(self.cooldown_seconds, self.reminder_retrigger_seconds)
        if evaluation.decision == InitiativeDecision.ASK:
            return self.cooldown_seconds
        return max(30.0, self.cooldown_seconds * 0.75)

    def _first_due_reminder(self, context: InitiativeContext, *, now: datetime) -> ReminderRecord | None:
        for item in context.open_reminders:
            if item.due_at is None or item.due_at > now:
                continue
            if item.last_triggered_at is not None and (now - item.last_triggered_at).total_seconds() < self.reminder_retrigger_seconds:
                continue
            return item
        return None

    def _follow_up_prompt(self, context: InitiativeContext) -> str:
        browser_title = context.browser_context.page_title or context.browser_context.summary
        if browser_title and self._turn_looks_browser_scoped(context.session.last_user_text):
            return f"Do you want to keep going with {browser_title}, or should I hold here?"
        latest_digest = context.digests[0] if context.digests else None
        if latest_digest is not None and latest_digest.open_follow_ups:
            item = latest_digest.open_follow_ups[0].strip().rstrip(".")
            if item:
                return f"Do you want to keep going on {item}, or should I stay quiet for now?"
        if context.session.current_topic:
            return f"Do you want to keep going on {context.session.current_topic.replace('_', ' ')}, or should I hold here?"
        return "Do you want to keep going, or should I stay quiet for now?"

    @staticmethod
    def _turn_looks_browser_scoped(text: str | None) -> bool:
        lowered = (text or "").strip().lower()
        return any(term in lowered for term in ("browser", "page", "site", "tab", "screen", "url", "link"))

    @staticmethod
    def _relationship_boundary_active(user_memory: UserMemoryRecord | None) -> bool:
        if user_memory is None:
            return False
        boundary_text = " ".join(user_memory.relationship_profile.interaction_boundaries).lower()
        return any(
            term in boundary_text
            for term in (
                "no proactive",
                "don't interrupt",
                "do not interrupt",
                "only when i ask",
                "only when asked",
                "stay quiet",
            )
        )


def terminal_activity_for_session(session: SessionRecord, *, now: datetime | None = None) -> TerminalActivitySignal:
    current = now or utc_now()
    latest_user_turn = next(
        (
            item
            for item in reversed(session.transcript)
            if item.user_text
        ),
        None,
    )
    if latest_user_turn is None:
        return TerminalActivitySignal(
            source=None,
            idle_seconds=None,
            last_user_text=session.last_user_text,
        )
    idle_seconds = max(0.0, round((current - latest_user_turn.timestamp).total_seconds(), 2))
    return TerminalActivitySignal(
        source=latest_user_turn.source,
        idle_seconds=idle_seconds,
        last_user_text=latest_user_turn.user_text,
    )


def browser_context_from_status(status: BrowserRuntimeStatusRecord | None) -> BrowserContextSignal:
    if status is None:
        return BrowserContextSignal(False)
    current_url = None
    page_title = None
    summary = None
    if status.latest_snapshot is not None:
        current_url = status.latest_snapshot.current_url
        page_title = status.latest_snapshot.page_title
        summary = status.latest_snapshot.summary
    if status.active_session is not None:
        current_url = current_url or status.active_session.current_url
        page_title = page_title or status.active_session.page_title
    available = bool(current_url or page_title or summary)
    return BrowserContextSignal(
        available=available,
        current_url=current_url,
        page_title=page_title,
        summary=summary,
    )


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


__all__ = [
    "BrowserContextSignal",
    "CompanionInitiativeEngine",
    "InitiativeCandidate",
    "InitiativeContext",
    "InitiativeEvaluation",
    "TerminalActivitySignal",
    "browser_context_from_status",
    "terminal_activity_for_session",
]
