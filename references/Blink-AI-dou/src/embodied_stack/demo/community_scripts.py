from __future__ import annotations

import json
from datetime import date, time
from pathlib import Path

from embodied_stack.shared.models import CommunityEventRecord, LocationRecord, ScenarioDefinition, ScenarioEventStep


DATA_DIR = Path(__file__).resolve().parent / "data"


def _read_json(name: str):
    return json.loads((DATA_DIR / name).read_text(encoding="utf-8"))


COMMUNITY_FAQ = {entry["key"]: entry for entry in _read_json("faq.json")}
COMMUNITY_FAQ_LIST = list(COMMUNITY_FAQ.values())

COMMUNITY_LOCATIONS = {
    item["location_key"]: LocationRecord(**item) for item in _read_json("locations.json")
}

COMMUNITY_EVENTS = [
    CommunityEventRecord(
        event_id=item["event_id"],
        title=item["title"],
        event_date=date.fromisoformat(item["event_date"]),
        start_time=time.fromisoformat(item["start_time"]),
        location_key=item["location_key"],
        summary=item["summary"],
    )
    for item in _read_json("events.json")
]

FEEDBACK_PROMPTS = {item["key"]: item["prompt"] for item in _read_json("feedback_prompts.json")}
OPERATOR_ESCALATION = _read_json("escalation.json")


DEMO_SCENARIOS = {
    "welcome_and_wayfinding": ScenarioDefinition(
        name="welcome_and_wayfinding",
        description="Person detection followed by a wayfinding question for the workshop room.",
        steps=[
            ScenarioEventStep(event_type="person_detected", payload={"confidence": 0.94}),
            ScenarioEventStep(event_type="speech_transcript", payload={"text": "Hi there. Where is the workshop room?"}),
            ScenarioEventStep(event_type="speech_transcript", payload={"text": "Can you repeat how to get there?"}),
        ],
    ),
    "events_and_memory": ScenarioDefinition(
        name="events_and_memory",
        description="Community events questions with a follow-up that relies on session memory.",
        steps=[
            ScenarioEventStep(event_type="speech_transcript", payload={"text": "What events are happening this week?"}),
            ScenarioEventStep(event_type="speech_transcript", payload={"text": "What time does the robotics workshop start?"}),
            ScenarioEventStep(event_type="speech_transcript", payload={"text": "What can you do for visitors here?"}),
        ],
    ),
    "operator_escalation": ScenarioDefinition(
        name="operator_escalation",
        description="A visitor requests human help and the brain records an escalation path.",
        steps=[
            ScenarioEventStep(event_type="speech_transcript", payload={"text": "I need a human operator to help with a lost item."}),
            ScenarioEventStep(event_type="speech_transcript", payload={"text": "Can you show me where the front desk is?"}),
        ],
    ),
    "safe_fallback_demo": ScenarioDefinition(
        name="safe_fallback_demo",
        description="A simulated network degradation and low-battery path that forces visible safe idle behavior.",
        steps=[
            ScenarioEventStep(event_type="network_state", payload={"network_ok": False, "latency_ms": 850.0}),
            ScenarioEventStep(event_type="low_battery", payload={"battery_pct": 11.0}),
        ],
    ),
}
