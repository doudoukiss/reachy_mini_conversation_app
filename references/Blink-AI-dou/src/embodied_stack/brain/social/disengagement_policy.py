from __future__ import annotations

from dataclasses import dataclass

from embodied_stack.shared.models import EngagementState


@dataclass(frozen=True)
class DisengagementPolicyOutcome:
    policy_name: str = "disengagement_policy"
    outcome: str = "idle"
    guardrail: str | None = None


def shorten_reply(reply_text: str) -> str:
    trimmed = reply_text.strip()
    if len(trimmed) <= 120:
        return trimmed
    if "." in trimmed:
        first_sentence = trimmed.split(".", 1)[0].strip()
        if first_sentence and len(first_sentence) <= 120:
            return f"{first_sentence}."
    if "," in trimmed:
        first_clause = trimmed.split(",", 1)[0].strip()
        if first_clause and len(first_clause) <= 120:
            return f"{first_clause}."
    words = trimmed.split()
    return " ".join(words[:18]).rstrip(" ,") + "..."


def reply_guardrail(
    *,
    prior_engagement_state: EngagementState,
    reply_text: str | None,
) -> DisengagementPolicyOutcome:
    if not reply_text:
        return DisengagementPolicyOutcome()
    if prior_engagement_state == EngagementState.DISENGAGING:
        return DisengagementPolicyOutcome(outcome="shorten_reply", guardrail="stale_or_disengaging_scene")
    if prior_engagement_state == EngagementState.LOST:
        return DisengagementPolicyOutcome(outcome="defer_reply", guardrail="disengaged_scene")
    return DisengagementPolicyOutcome()


__all__ = [
    "DisengagementPolicyOutcome",
    "reply_guardrail",
    "shorten_reply",
]
