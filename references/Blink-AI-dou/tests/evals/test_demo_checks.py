from pathlib import Path

from embodied_stack.config import Settings
from embodied_stack.demo.checks import run_demo_checks


def test_demo_check_suite_covers_investor_paths_and_writes_artifacts(tmp_path):
    settings = Settings(
        brain_store_path=str(tmp_path / "brain_store.json"),
        demo_report_dir=str(tmp_path / "demo_runs"),
        demo_check_dir=str(tmp_path / "demo_checks"),
        brain_dialogue_backend="rule_based",
        brain_voice_backend="stub",
    )

    suite = run_demo_checks(settings=settings, output_dir=tmp_path / "demo_checks")

    assert suite.passed is True
    assert Path(suite.artifact_dir).is_dir()
    assert Path(suite.artifact_files["summary"]).exists()
    assert {item.check_name for item in suite.items} == {
        "greeting",
        "attentive_listening",
        "wayfinding",
        "events_lookup",
        "memory_followup",
        "operator_escalation",
        "safe_idle_behavior",
        "virtual_body_behavior",
        "camera_unavailable_fallback",
        "bodyless_conversation",
        "serial_transport_fallback",
        "provider_failure_fallback",
    }
    assert all(item.passed for item in suite.items)
    assert all(Path(item.artifact_files["summary"]).exists() for item in suite.items)
    safe_idle = next(item for item in suite.items if item.check_name == "safe_idle_behavior")
    assert safe_idle.fallback_events
