from __future__ import annotations

from .companion_relationship import COMPANION_RELATIONSHIP
from .community_concierge import COMMUNITY_CONCIERGE
from .daily_planning import DAILY_PLANNING
from .general_companion_conversation import GENERAL_COMPANION_CONVERSATION
from .incident_escalation import INCIDENT_ESCALATION
from .memory_followup import MEMORY_FOLLOWUP
from .observe_and_comment import OBSERVE_AND_COMMENT
from .safe_degraded_response import SAFE_DEGRADED_RESPONSE
from .types import SkillSpec


FIRST_PARTY_SKILLS: tuple[SkillSpec, ...] = (
    *GENERAL_COMPANION_CONVERSATION,
    *COMPANION_RELATIONSHIP,
    *OBSERVE_AND_COMMENT,
    *MEMORY_FOLLOWUP,
    *DAILY_PLANNING,
    *COMMUNITY_CONCIERGE,
    *INCIDENT_ESCALATION,
    *SAFE_DEGRADED_RESPONSE,
)


__all__ = [
    "FIRST_PARTY_SKILLS",
    "SkillSpec",
]
