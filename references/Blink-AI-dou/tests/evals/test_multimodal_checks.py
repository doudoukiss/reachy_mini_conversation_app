from pathlib import Path

from embodied_stack.config import Settings
from embodied_stack.demo.multimodal_checks import run_multimodal_checks


def test_multimodal_check_suite_writes_scorecards_and_artifacts(tmp_path):
    settings = Settings(
        brain_store_path=str(tmp_path / "brain_store.json"),
        demo_report_dir=str(tmp_path / "demo_runs"),
        demo_check_dir=str(tmp_path / "demo_checks"),
        brain_dialogue_backend="rule_based",
        brain_voice_backend="stub",
        operator_auth_token="test-operator-token",
        operator_auth_runtime_file=str(tmp_path / "operator_auth.json"),
    )

    suite = run_multimodal_checks(settings=settings, output_dir=tmp_path / "demo_checks")

    assert suite.passed is True
    assert Path(suite.artifact_dir).is_dir()
    assert {item.check_name for item in suite.items} == {
        "approach_and_greet",
        "two_person_attention_handoff",
        "disengagement_shortening",
        "scene_grounded_comment",
        "uncertainty_admission",
        "stale_scene_suppression",
        "operator_correction_after_wrong_scene_interpretation",
    }
    assert all(item.scorecard and item.scorecard.passed for item in suite.items)
    assert all(Path(item.artifact_files["scorecard"]).exists() for item in suite.items)
    assert all(Path(item.artifact_files["perception_snapshots"]).exists() for item in suite.items)
