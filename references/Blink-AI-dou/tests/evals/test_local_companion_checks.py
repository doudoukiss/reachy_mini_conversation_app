from pathlib import Path

from embodied_stack.config import Settings
from embodied_stack.demo.local_companion_checks import run_local_companion_checks


def test_local_companion_check_suite_covers_polished_local_runtime_paths(tmp_path):
    settings = Settings(
        _env_file=None,
        brain_store_path=str(tmp_path / "brain_store.json"),
        demo_report_dir=str(tmp_path / "demo_runs"),
        demo_check_dir=str(tmp_path / "demo_checks"),
        episode_export_dir=str(tmp_path / "episodes"),
        shift_report_dir=str(tmp_path / "shift_reports"),
        brain_dialogue_backend="rule_based",
        brain_voice_backend="stub",
        operator_auth_token="test-operator-token",
        operator_auth_runtime_file=str(tmp_path / "operator_auth.json"),
    )

    suite = run_local_companion_checks(settings=settings, output_dir=tmp_path / "demo_checks")

    assert suite.passed is True
    assert Path(suite.artifact_dir).is_dir()
    assert Path(suite.artifact_files["summary"]).exists()
    assert {item.check_name for item in suite.items} == {
        "mic_speaker_loop",
        "webcam_grounded_reply",
        "browser_live_visual_turn",
        "profile_fallback",
        "memory_retrieval",
        "relationship_continuity",
        "uncertainty_honesty",
        "bodyless_virtual_body_continuity",
    }
    assert all(item.passed for item in suite.items)
    assert all(Path(item.artifact_files["summary"]).exists() for item in suite.items)

    mic = next(item for item in suite.items if item.check_name == "mic_speaker_loop")
    assert Path(mic.artifact_files["episode"]).exists()
    assert Path(mic.artifact_files["snapshot"]).exists()

    webcam = next(item for item in suite.items if item.check_name == "webcam_grounded_reply")
    assert Path(webcam.artifact_files["capture"]).exists()
    assert Path(webcam.artifact_files["episode"]).exists()

    fallback = next(item for item in suite.items if item.check_name == "profile_fallback")
    assert any(note for note in fallback.notes)
