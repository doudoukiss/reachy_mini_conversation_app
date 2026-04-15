from __future__ import annotations

from pathlib import Path

import yaml

from embodied_stack.body import DEFAULT_HEAD_PROFILE_PATH, default_head_profile, load_head_profile


def test_default_head_profile_matches_uploaded_robot_head() -> None:
    profile = load_head_profile(None)

    assert profile.profile_name == "robot_head_v1"
    assert profile.source_path == str(DEFAULT_HEAD_PROFILE_PATH)
    assert profile.source_format == "json"
    assert profile.baud_rate == 1000000
    assert profile.auto_scan_baud_rates == [1000000, 115200]
    assert len(profile.joints) == 11
    assert any(rule.name == "mirrored_eyelids" for rule in profile.coupling_rules)
    assert not any("baud rate" in note.lower() for note in profile.pending_bench_confirmations)


def test_head_profile_loader_supports_yaml(tmp_path: Path) -> None:
    payload = default_head_profile().model_dump(mode="json")
    profile_path = tmp_path / "robot_head.yaml"
    profile_path.write_text(yaml.safe_dump(payload, sort_keys=False), encoding="utf-8")

    profile = load_head_profile(profile_path)

    assert profile.source_path == str(profile_path)
    assert profile.source_format == "yaml"
    assert profile.joints[0].servo_ids == [1]
    assert profile.pending_bench_confirmations
