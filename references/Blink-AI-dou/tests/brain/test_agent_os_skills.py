from __future__ import annotations

from embodied_stack.brain.agent_os.skills import SkillRegistry
from embodied_stack.shared.contracts import CompanionContextMode, SessionRecord


def test_skill_registry_routes_wayfinding_queries_to_wayfinding():
    registry = SkillRegistry()
    result = registry.resolve(
        text="Where is the front desk?",
        session=SessionRecord(session_id="skill-wayfinding"),
        context_mode=CompanionContextMode.PERSONAL_LOCAL,
        latest_perception=None,
        provider_failure_active=False,
    )

    assert result.skill_name == "wayfinding"
    assert result.playbook_name == "community_concierge"
    assert result.route_variant == "wayfinding"
    assert "search_venue_knowledge" in result.required_tools
    assert "system_health" in result.required_tools
    assert result.reason.startswith("query_match:")


def test_skill_registry_prefers_safe_degraded_response_when_provider_failure_is_active():
    registry = SkillRegistry()
    result = registry.resolve(
        text="What can you see right now?",
        session=SessionRecord(session_id="skill-degraded"),
        context_mode=CompanionContextMode.PERSONAL_LOCAL,
        latest_perception=None,
        provider_failure_active=True,
    )

    assert result.skill_name == "safe_degraded_response"
    assert result.playbook_name == "safe_degraded_response"
    assert "system_health" in result.required_tools
    assert result.reason == "provider_failure_active"


def test_skill_registry_routes_camera_phrasing_to_observe_and_comment():
    registry = SkillRegistry()
    result = registry.resolve(
        text="What can you see from the cameras now?",
        session=SessionRecord(session_id="skill-visual"),
        context_mode=CompanionContextMode.PERSONAL_LOCAL,
        latest_perception=None,
        provider_failure_active=False,
    )

    assert result.skill_name == "observe_and_comment"
    assert result.behavior_category == "observe_and_comment"


def test_skill_registry_routes_personal_greeting_to_companion_reentry():
    registry = SkillRegistry()
    result = registry.resolve(
        text="Hey there",
        session=SessionRecord(session_id="skill-greeting", current_topic="greeting"),
        context_mode=CompanionContextMode.PERSONAL_LOCAL,
        latest_perception=None,
        provider_failure_active=False,
    )

    assert result.skill_name == "companion_greeting_reentry"
    assert result.playbook_name == "companion_relationship"
    assert result.behavior_category == "greeting_reentry"


def test_skill_registry_keeps_venue_greeting_in_concierge_mode():
    registry = SkillRegistry()
    result = registry.resolve(
        text="Hello",
        session=SessionRecord(session_id="skill-venue-greeting", current_topic="greeting"),
        context_mode=CompanionContextMode.VENUE_DEMO,
        latest_perception=None,
        provider_failure_active=False,
    )

    assert result.skill_name == "welcome_guest"
    assert result.behavior_category == "venue_concierge"


def test_skill_registry_routes_unresolved_follow_up_to_companion_thread_skill():
    registry = SkillRegistry()
    result = registry.resolve(
        text="Can we pick up where we left off?",
        session=SessionRecord(session_id="skill-follow-up"),
        context_mode=CompanionContextMode.PERSONAL_LOCAL,
        latest_perception=None,
        provider_failure_active=False,
    )

    assert result.skill_name == "unresolved_thread_follow_up"
    assert result.behavior_category == "unresolved_thread_follow_up"


def test_skill_registry_routes_explicit_tone_request_to_emotional_tone_bounds():
    registry = SkillRegistry()
    result = registry.resolve(
        text="Keep it brief and do not be chatty.",
        session=SessionRecord(session_id="skill-tone"),
        context_mode=CompanionContextMode.PERSONAL_LOCAL,
        latest_perception=None,
        provider_failure_active=False,
    )

    assert result.skill_name == "emotional_tone_bounds"
    assert result.behavior_category == "emotional_tone_bounds"
