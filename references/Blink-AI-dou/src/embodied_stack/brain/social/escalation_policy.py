from __future__ import annotations

from dataclasses import dataclass

from embodied_stack.brain.venue_knowledge import VenueKnowledge
from embodied_stack.shared.models import IncidentReasonCategory


@dataclass(frozen=True)
class EscalationPolicyOutcome:
    policy_name: str = "escalation_policy"
    outcome: str = "idle"
    reason_category: str | None = None
    policy_note: str | None = None
    staff_contact_key: str | None = None
    urgency: str | None = None


def accessibility_request(lowered: str) -> bool:
    keywords = (
        "accessibility",
        "wheelchair",
        "hearing",
        "vision assistance",
        "accessible route",
        "mobility help",
        "sign language",
    )
    return any(keyword in lowered for keyword in keywords)


def escalation_for_text(lowered: str, *, venue_knowledge: VenueKnowledge | None) -> EscalationPolicyOutcome:
    if venue_knowledge is not None:
        rule = venue_knowledge.escalation_rule_for_text(lowered)
        if rule is not None:
            return EscalationPolicyOutcome(
                outcome="escalate",
                reason_category=rule["reason_category"],
                policy_note=rule.get("policy_note"),
                staff_contact_key=rule.get("staff_contact_key"),
                urgency=rule.get("urgency"),
            )
    if accessibility_request(lowered):
        return EscalationPolicyOutcome(
            outcome="escalate",
            reason_category=IncidentReasonCategory.ACCESSIBILITY.value,
            policy_note="accessibility request should go straight to a human operator path",
        )
    return EscalationPolicyOutcome()


__all__ = [
    "EscalationPolicyOutcome",
    "accessibility_request",
    "escalation_for_text",
]
