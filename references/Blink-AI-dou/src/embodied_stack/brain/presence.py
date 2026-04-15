from __future__ import annotations

from dataclasses import dataclass, field
from threading import Event, RLock, Thread
from typing import Callable

from embodied_stack.config import Settings
from embodied_stack.shared.models import (
    CompanionPresenceState,
    CompanionPresenceStatus,
    utc_now,
)


TransitionCallback = Callable[[CompanionPresenceStatus, dict[str, object]], None]


@dataclass
class FastPresencePlan:
    acknowledge_text: str
    working_text: str
    reason: str


@dataclass
class FastPresenceSummary:
    acknowledged: bool = False
    tool_working: bool = False
    acknowledgement_text: str | None = None
    working_text: str | None = None


@dataclass
class _ActiveWatch:
    done: Event = field(default_factory=Event)
    summary: FastPresenceSummary = field(default_factory=FastPresenceSummary)
    thread: Thread | None = None


class FastPresencePlanner:
    def plan(self, *, input_text: str | None, source: str | None) -> FastPresencePlan:
        text = (input_text or "").strip().lower()
        source_text = (source or "").strip().lower()
        if any(token in text for token in ("camera", "see", "look", "watch", "screen", "show me")):
            return FastPresencePlan(
                acknowledge_text="Checking that now.",
                working_text="Still checking the scene.",
                reason="visual_query",
            )
        if any(token in text for token in ("find", "search", "look up", "check", "open", "run", "debug", "fix", "write")):
            return FastPresencePlan(
                acknowledge_text="On it.",
                working_text="Still working through it.",
                reason="task_request",
            )
        if "open_mic" in source_text or "voice" in source_text or "listen" in source_text:
            return FastPresencePlan(
                acknowledge_text="Mm-hm.",
                working_text="Still with you.",
                reason="voice_turn",
            )
        return FastPresencePlan(
            acknowledge_text="Got it.",
            working_text="Still on it.",
            reason="default",
        )


class PresenceRuntime:
    def __init__(
        self,
        *,
        settings: Settings,
        transition_callback: TransitionCallback | None = None,
    ) -> None:
        self.settings = settings
        self._transition_callback = transition_callback
        self._planner = FastPresencePlanner()
        self._lock = RLock()
        self._status = CompanionPresenceStatus()
        self._watches: dict[str, _ActiveWatch] = {}

    def status(self) -> CompanionPresenceStatus:
        with self._lock:
            return self._status.model_copy(deep=True)

    def begin_turn(
        self,
        *,
        session_id: str,
        input_text: str | None,
        source: str | None,
        listening: bool,
    ) -> None:
        self._stop_watch(session_id)
        preview = self._preview(input_text)
        state = CompanionPresenceState.LISTENING if listening else CompanionPresenceState.THINKING_FAST
        message = "listening" if listening else "thinking_fast"
        self._transition(
            state,
            session_id=session_id,
            message=message,
            last_user_text_preview=preview,
            slow_path_active=not listening,
            slow_path_started=not listening,
        )
        if listening:
            return
        self._ensure_watch(session_id=session_id, source=source, input_text=input_text)

    def note_thinking_fast(self, *, session_id: str, input_text: str | None = None, message: str = "thinking_fast") -> None:
        self._ensure_watch(session_id=session_id, source=None, input_text=input_text)
        current = self.status()
        if current.session_id != session_id:
            return
        if current.state in {
            CompanionPresenceState.ACKNOWLEDGING,
            CompanionPresenceState.TOOL_WORKING,
            CompanionPresenceState.SPEAKING,
            CompanionPresenceState.DEGRADED,
        }:
            return
        if not self.settings.blink_fast_presence_enabled:
            return
        self._transition(
            CompanionPresenceState.THINKING_FAST,
            session_id=session_id,
            message=message,
            last_user_text_preview=self._preview(input_text) or current.last_user_text_preview,
            slow_path_active=True,
            slow_path_started=current.slow_path_started_at is None,
        )

    def begin_reply(self, *, session_id: str, reply_text: str | None, audible: bool) -> None:
        current = self.status()
        if current.session_id != session_id:
            return
        reply_preview = self._preview(reply_text)
        if current.state in {CompanionPresenceState.ACKNOWLEDGING, CompanionPresenceState.TOOL_WORKING}:
            self._transition(
                CompanionPresenceState.REENGAGING,
                session_id=session_id,
                message="reply_ready",
                last_reply_preview=reply_preview,
                slow_path_active=False,
            )
        if audible:
            self._transition(
                CompanionPresenceState.SPEAKING,
                session_id=session_id,
                message="speaking",
                last_reply_preview=reply_preview,
                last_reply=True,
                slow_path_active=False,
            )

    def finish_turn(
        self,
        *,
        session_id: str,
        reply_text: str | None,
        spoken: bool,
        completed: bool = False,
    ) -> FastPresenceSummary:
        summary = self._stop_watch(session_id)
        current = self.status()
        if current.session_id == session_id and (not spoken or completed):
            if current.state in {CompanionPresenceState.ACKNOWLEDGING, CompanionPresenceState.TOOL_WORKING}:
                self._transition(
                    CompanionPresenceState.REENGAGING,
                    session_id=session_id,
                    message="reply_ready",
                    last_reply_preview=self._preview(reply_text),
                    last_reply=bool(reply_text),
                    slow_path_active=False,
                )
            self._transition(
                CompanionPresenceState.IDLE,
                session_id=session_id,
                message="idle",
                last_reply_preview=self._preview(reply_text) or current.last_reply_preview,
                last_reply=bool(reply_text),
                slow_path_active=False,
            )
        return summary

    def _ensure_watch(self, *, session_id: str, source: str | None, input_text: str | None) -> None:
        if not self.settings.blink_fast_presence_enabled:
            return
        with self._lock:
            if session_id in self._watches:
                return
        watch = _ActiveWatch()
        watch.thread = Thread(
            target=self._run_watch,
            kwargs={
                "session_id": session_id,
                "source": source,
                "input_text": input_text,
                "watch": watch,
            },
            name=f"blink-fast-presence-{session_id[:16]}",
            daemon=True,
        )
        with self._lock:
            self._watches[session_id] = watch
        watch.thread.start()

    def interrupt(self, *, session_id: str, reason: str, barge_in: bool = False) -> None:
        self._stop_watch(session_id)
        current = self.status()
        self._transition(
            CompanionPresenceState.REENGAGING,
            session_id=session_id,
            message=reason,
            last_user_text_preview=current.last_user_text_preview,
            slow_path_active=False,
            interrupted=True,
            barged_in=barge_in,
        )

    def degrade(self, *, session_id: str, reason: str, message: str | None = None) -> FastPresenceSummary:
        summary = self._stop_watch(session_id)
        self._transition(
            CompanionPresenceState.DEGRADED,
            session_id=session_id,
            message=message or reason,
            degraded_reason=reason,
            slow_path_active=False,
        )
        return summary

    def reset_idle(self, *, session_id: str | None = None) -> None:
        self._transition(
            CompanionPresenceState.IDLE,
            session_id=session_id or self.status().session_id,
            message="idle",
            slow_path_active=False,
        )

    def _run_watch(
        self,
        *,
        session_id: str,
        source: str | None,
        input_text: str | None,
        watch: _ActiveWatch,
    ) -> None:
        plan = self._planner.plan(input_text=input_text, source=source)
        if watch.done.wait(max(0.0, float(self.settings.blink_fast_presence_ack_delay_seconds))):
            return
        watch.summary.acknowledged = True
        watch.summary.acknowledgement_text = plan.acknowledge_text
        self._transition(
            CompanionPresenceState.ACKNOWLEDGING,
            session_id=session_id,
            message=plan.acknowledge_text,
            last_acknowledgement_text=plan.acknowledge_text,
            slow_path_active=True,
            increment_acknowledgement=True,
        )
        remaining = max(
            0.0,
            float(self.settings.blink_fast_presence_tool_delay_seconds)
            - float(self.settings.blink_fast_presence_ack_delay_seconds),
        )
        if watch.done.wait(remaining):
            return
        watch.summary.tool_working = True
        watch.summary.working_text = plan.working_text
        self._transition(
            CompanionPresenceState.TOOL_WORKING,
            session_id=session_id,
            message=plan.working_text,
            slow_path_active=True,
        )

    def _stop_watch(self, session_id: str) -> FastPresenceSummary:
        with self._lock:
            watch = self._watches.pop(session_id, None)
        if watch is None:
            return FastPresenceSummary()
        watch.done.set()
        if watch.thread is not None and watch.thread.is_alive():
            watch.thread.join(timeout=0.05)
        return watch.summary

    def _transition(
        self,
        state: CompanionPresenceState,
        *,
        session_id: str | None,
        message: str | None,
        last_user_text_preview: str | None = None,
        last_reply_preview: str | None = None,
        last_acknowledgement_text: str | None = None,
        degraded_reason: str | None = None,
        slow_path_active: bool | None = None,
        slow_path_started: bool = False,
        last_reply: bool = False,
        increment_acknowledgement: bool = False,
        interrupted: bool = False,
        barged_in: bool = False,
    ) -> None:
        now = utc_now()
        with self._lock:
            status = self._status.model_copy(deep=True)
            status.state = state
            status.session_id = session_id or status.session_id
            status.message = message
            status.last_transition_at = now
            if last_user_text_preview is not None:
                status.last_user_text_preview = last_user_text_preview
            if last_reply_preview is not None:
                status.last_reply_preview = last_reply_preview
            if last_acknowledgement_text is not None:
                status.last_acknowledgement_text = last_acknowledgement_text
            if degraded_reason is not None:
                status.degraded_reason = degraded_reason
            elif state != CompanionPresenceState.DEGRADED:
                status.degraded_reason = None
            if slow_path_active is not None:
                status.slow_path_active = slow_path_active
            if slow_path_started:
                status.slow_path_started_at = now
            elif slow_path_active is False:
                status.slow_path_started_at = None
            if last_reply:
                status.last_reply_at = now
            if increment_acknowledgement:
                status.acknowledgement_count += 1
            if interrupted:
                status.interruption_count += 1
            if barged_in:
                status.barge_in_count += 1
            self._status = status
            snapshot = status.model_copy(deep=True)
        if self._transition_callback is not None:
            self._transition_callback(
                snapshot,
                {
                    "timestamp": now.isoformat(),
                    "state": state.value,
                    "session_id": session_id,
                    "message": message,
                    "last_user_text_preview": last_user_text_preview,
                    "last_reply_preview": last_reply_preview,
                    "degraded_reason": snapshot.degraded_reason,
                    "slow_path_active": snapshot.slow_path_active,
                },
            )

    @staticmethod
    def _preview(text: str | None, *, limit: int = 80) -> str | None:
        preview = (text or "").strip()
        if not preview:
            return None
        if len(preview) <= limit:
            return preview
        return preview[: limit - 3].rstrip() + "..."


__all__ = [
    "FastPresencePlan",
    "FastPresencePlanner",
    "FastPresenceSummary",
    "PresenceRuntime",
]
