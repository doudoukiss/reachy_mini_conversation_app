from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from embodied_stack.brain.orchestrator import BrainOrchestrator
from embodied_stack.brain.venue_knowledge import VenueKnowledge
from embodied_stack.config import Settings
from embodied_stack.shared.models import RobotEvent


REPO_ROOT = Path(__file__).resolve().parents[2]


def _make_orchestrator(tmp_path: Path, pack_name: str) -> BrainOrchestrator:
    settings = Settings(
        brain_store_path=str(tmp_path / f"{pack_name}_store.json"),
        demo_report_dir=str(tmp_path / "demo_runs"),
        episode_export_dir=str(tmp_path / "episodes"),
        shift_background_tick_enabled=False,
        venue_content_dir=str(REPO_ROOT / "pilot_site" / pack_name),
    )
    return BrainOrchestrator(settings=settings, store_path=settings.brain_store_path)


def test_real_site_packs_load_distinct_operations_profiles():
    community = VenueKnowledge.from_directory(REPO_ROOT / "pilot_site" / "demo_community_center")
    library = VenueKnowledge.from_directory(REPO_ROOT / "pilot_site" / "demo_library_branch")

    assert community.operations.announcement_policy.opening_prompt_text
    assert library.operations.announcement_policy.opening_prompt_text is None
    assert community.operations.proactive_greeting_policy.max_people_for_auto_greet == 3
    assert library.operations.proactive_greeting_policy.max_people_for_auto_greet == 1
    assert community.operations.escalation_policy_overrides.default_staff_contact_key == "front_desk"
    assert library.operations.quiet_hours[0].label == "study_quiet_window"


def test_invalid_site_operations_pack_fails_fast(tmp_path: Path):
    pack_dir = tmp_path / "invalid_site"
    pack_dir.mkdir(parents=True)
    (pack_dir / "site.yaml").write_text(
        "\n".join(
            [
                "site_name: Invalid Site",
                "timezone: America/Los_Angeles",
                "operations:",
                "  opening_hours:",
                "    - days: [monday]",
                '      start: "09:00"',
                '      end: "17:00"',
                "  escalation_policy_overrides:",
                "    default_staff_contact_key: missing_contact",
            ]
        ),
        encoding="utf-8",
    )
    (pack_dir / "staff_contacts.txt").write_text(
        "front_desk|Jordan Lee|Front Desk Coordinator|555-0100|frontdesk@test.org|Lobby support|front desk\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="invalid_operations_staff_contact:missing_contact"):
        VenueKnowledge.from_directory(pack_dir)


def test_community_center_opening_tick_issues_opening_prompt(tmp_path: Path):
    orchestrator = _make_orchestrator(tmp_path, "demo_community_center")
    tick = orchestrator.handle_event(
        orchestrator.build_shift_tick_event(
            session_id="ops-opening",
            timestamp=datetime(2026, 3, 30, 16, 5, tzinfo=timezone.utc),
        )
    )

    assert "community center shift" in (tick.reply_text or "").lower()
    shift = orchestrator.get_shift_supervisor()
    assert shift.state.value == "ready_idle"
    assert shift.last_scheduled_prompt_type == "opening_prompt"
    assert "opening_prompt_issued" in shift.reason_codes


def test_library_quiet_hours_suppress_auto_greeting(tmp_path: Path):
    orchestrator = _make_orchestrator(tmp_path, "demo_library_branch")
    response = orchestrator.handle_event(
        RobotEvent(
            event_type="person_visible",
            session_id="library-quiet",
            timestamp=datetime(2026, 3, 30, 19, 30, tzinfo=timezone.utc),
            payload={"confidence": 0.91},
        )
    )

    assert response.reply_text is None
    trace = orchestrator.get_trace(response.trace_id)
    assert trace is not None
    assert "shift_policy:presence_outreach_suppressed" in trace.reasoning.notes


def test_event_start_reminder_comes_from_site_pack_schedule(tmp_path: Path):
    orchestrator = _make_orchestrator(tmp_path, "demo_community_center")
    orchestrator.handle_event(
        RobotEvent(
            event_type="person_visible",
            session_id="ops-event",
            timestamp=datetime(2026, 4, 1, 0, 49, 55, tzinfo=timezone.utc),
            payload={"confidence": 0.93},
        )
    )

    reminder = orchestrator.handle_event(
        orchestrator.build_shift_tick_event(
            session_id="ops-event",
            timestamp=datetime(2026, 4, 1, 0, 50, tzinfo=timezone.utc),
        )
    )

    assert "Robotics Workshop" in (reminder.reply_text or "")
    shift = orchestrator.get_shift_supervisor()
    assert shift.last_scheduled_prompt_type == "event_start_reminder"
