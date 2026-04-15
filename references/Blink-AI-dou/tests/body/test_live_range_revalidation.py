from __future__ import annotations

from pathlib import Path

from embodied_stack.body import calibration as calibration_module
from embodied_stack.body.live_range_revalidation import (
    available_revalidation_families,
    render_live_limits_markdown,
    resolve_revalidation_sequence,
)
from embodied_stack.body.profile import load_head_profile
import embodied_stack.body.live_range_revalidation as live_range_revalidation


def _saved_calibration():
    profile = load_head_profile("src/embodied_stack/body/profiles/robot_head_v1.json")
    calibration = calibration_module.calibration_from_profile(profile, calibration_kind="saved")
    calibration.coupling_validation = {
        "neck_pitch_roll": "ok",
        "mirrored_eyelids": "ok",
        "mirrored_brows": "ok",
        "eyes_follow_lids": "ok",
        "range_conflicts": "ok",
    }
    for joint in calibration.joint_records:
        joint.mirrored_direction_confirmed = True
    return profile, calibration


def test_revalidation_family_order_and_resume_sequence_are_deterministic() -> None:
    assert available_revalidation_families() == (
        "head_yaw",
        "neck_pitch",
        "neck_tilt",
        "eye_yaw",
        "eye_pitch",
        "upper_lids",
        "lower_lids",
        "brows",
    )
    assert resolve_revalidation_sequence(family=None, resume_from="eye_yaw") == [
        "eye_yaw",
        "eye_pitch",
        "upper_lids",
        "lower_lids",
        "brows",
    ]


def test_neck_probe_directions_match_pitch_and_tilt_coupling() -> None:
    pitch_probes = live_range_revalidation._PROBES_BY_FAMILY["neck_pitch"]
    tilt_probes = live_range_revalidation._PROBES_BY_FAMILY["neck_tilt"]

    assert pitch_probes[0].joint_signs == (("head_pitch_pair_a", -1), ("head_pitch_pair_b", 1))
    assert pitch_probes[1].joint_signs == (("head_pitch_pair_a", 1), ("head_pitch_pair_b", -1))
    assert tilt_probes[0].joint_signs == (("head_pitch_pair_b", -1),)
    assert tilt_probes[1].joint_signs == (("head_pitch_pair_a", 1),)


def test_head_yaw_probes_allow_wider_slower_live_revalidation() -> None:
    yaw_probes = live_range_revalidation._PROBES_BY_FAMILY["head_yaw"]

    assert yaw_probes[0].step_counts == 20
    assert yaw_probes[1].step_counts == 20
    assert yaw_probes[0].max_extension_counts >= 420
    assert yaw_probes[1].max_extension_counts >= 420
    assert yaw_probes[0].duration_ms >= 1600
    assert yaw_probes[1].duration_ms >= 1600
    assert yaw_probes[0].dwell_ms >= 2200
    assert yaw_probes[1].dwell_ms >= 2200


def test_health_mapping_uses_servo_ids_instead_of_missing_joint_names() -> None:
    profile, _calibration = _saved_calibration()
    snapshot = {
        "positions": {},
        "health": {
            1: {"servo_id": 1, "error_bits": []},
            9: {"servo_id": 9, "error_bits": []},
            10: {"servo_id": 10, "error_bits": []},
        },
    }

    result = live_range_revalidation._health_by_joint(
        profile=profile,
        snapshot=snapshot,
        requested_joints={"head_yaw", "eye_yaw"},
    )

    assert set(result) == {"head_yaw", "eye_yaw"}
    assert result["head_yaw"]["servo_id"] == 1
    assert result["eye_yaw"]["servo_id"] == 9


def test_probe_confirmation_uses_last_passing_live_readback_not_requested_target(monkeypatch, tmp_path: Path) -> None:
    profile, calibration = _saved_calibration()
    probe = live_range_revalidation._PROBES_BY_FAMILY["head_yaw"][0]
    requested_targets: list[dict[str, int]] = []
    snapshots = [
        {
            "positions": {1: {"position": 2047}},
            "health": {1: {"servo_id": 1, "error_bits": [], "load": 0}},
        },
        {
            "positions": {1: {"position": 2023}},
            "health": {1: {"servo_id": 1, "error_bits": [], "load": 40}},
        },
        {
            "positions": {1: {"position": 1995}},
            "health": {1: {"servo_id": 1, "error_bits": ["overload"], "load": 320}},
        },
        {
            "positions": {1: {"position": 2023}},
            "health": {1: {"servo_id": 1, "error_bits": [], "load": 35}},
        },
    ]

    def fake_execute_bench_command(**kwargs):
        requested_targets.append(dict(kwargs["requested_targets"] or {}))
        return {"success": True, "report_path": str(tmp_path / f"step-{len(requested_targets)}.json"), "stop_notes": []}

    def fake_read_bench_snapshot(_transport, _servo_ids):
        return snapshots.pop(0)

    class FakeTransport:
        def read_position(self, servo_id: int) -> int:
            assert servo_id == 1
            return 2047

    monkeypatch.setattr(live_range_revalidation, "execute_bench_command", fake_execute_bench_command)
    monkeypatch.setattr(live_range_revalidation, "read_bench_snapshot", fake_read_bench_snapshot)

    result = live_range_revalidation._run_probe(
        profile=profile,
        calibration=calibration,
        transport=FakeTransport(),
        bridge=object(),
        probe=probe,
        report_dir=tmp_path,
        allow_widen_beyond_profile=True,
    )

    assert result["chosen_last_passing_limit"]["head_yaw"] == 2023
    assert result["confirmed_targets"]["head_yaw"] == 2023
    assert requested_targets[0]["head_yaw"] == 2047
    assert requested_targets[1]["head_yaw"] == 2027
    assert requested_targets[3]["head_yaw"] == 2023


def test_probe_resets_to_family_neutral_before_search(monkeypatch, tmp_path: Path) -> None:
    profile, calibration = _saved_calibration()
    probe = live_range_revalidation._PROBES_BY_FAMILY["head_yaw"][1]
    requested_targets: list[dict[str, int]] = []
    snapshots = [
        {
            "positions": {1: {"position": 2047}},
            "health": {1: {"servo_id": 1, "error_bits": [], "load": 0}},
        },
        {
            "positions": {1: {"position": 2067}},
            "health": {1: {"servo_id": 1, "error_bits": [], "load": 0}},
        },
        {
            "positions": {1: {"position": 2087}},
            "health": {1: {"servo_id": 1, "error_bits": [], "load": 0}},
        },
        {
            "positions": {1: {"position": 2096}},
            "health": {1: {"servo_id": 1, "error_bits": [], "load": 0}},
        },
        {
            "positions": {1: {"position": 2087}},
            "health": {1: {"servo_id": 1, "error_bits": [], "load": 0}},
        },
        {
            "positions": {1: {"position": 2087}},
            "health": {1: {"servo_id": 1, "error_bits": [], "load": 0}},
        },
        {
            "positions": {1: {"position": 2087}},
            "health": {1: {"servo_id": 1, "error_bits": [], "load": 0}},
        },
        {
            "positions": {1: {"position": 2087}},
            "health": {1: {"servo_id": 1, "error_bits": [], "load": 0}},
        },
        {
            "positions": {1: {"position": 2087}},
            "health": {1: {"servo_id": 1, "error_bits": [], "load": 0}},
        },
    ]

    class FakeTransport:
        def read_position(self, servo_id: int) -> int:
            assert servo_id == 1
            return 2007

    def fake_execute_bench_command(**kwargs):
        requested_targets.append(dict(kwargs["requested_targets"] or {}))
        return {"success": True, "report_path": str(tmp_path / f"step-{len(requested_targets)}.json"), "stop_notes": []}

    def fake_read_bench_snapshot(_transport, _servo_ids):
        return snapshots.pop(0)

    monkeypatch.setattr(live_range_revalidation, "execute_bench_command", fake_execute_bench_command)
    monkeypatch.setattr(live_range_revalidation, "read_bench_snapshot", fake_read_bench_snapshot)

    result = live_range_revalidation._run_probe(
        profile=profile,
        calibration=calibration,
        transport=FakeTransport(),
        bridge=object(),
        probe=probe,
        report_dir=tmp_path,
        allow_widen_beyond_profile=True,
    )

    assert requested_targets[0] == {"head_yaw": 2047}
    assert requested_targets[1] == {"head_yaw": 2067}
    assert requested_targets[2] == {"head_yaw": 2087}
    assert requested_targets[4] == {"head_yaw": 2127}
    assert result["confirmed_targets"]["head_yaw"] == 2087


def test_checked_in_live_limits_doc_matches_renderer() -> None:
    profile = load_head_profile("src/embodied_stack/body/profiles/robot_head_v1.json")
    calibration = calibration_module.load_head_calibration(
        "runtime/calibrations/robot_head_live_v1.json",
        profile=profile,
    )
    actual = Path("docs/robot_head_live_limits.md").read_text(encoding="utf-8").strip()
    artifact_line = next(
        line for line in actual.splitlines() if line.startswith("Most recent live artifact directory:")
    )
    artifact_dir = artifact_line.split(":", 1)[1].strip()
    expected = render_live_limits_markdown(
        profile=profile,
        calibration=calibration,
        artifact_dir=artifact_dir,
    ).strip()

    assert actual == expected


def test_active_docs_no_longer_reference_deleted_info_txt() -> None:
    for path in Path("docs").rglob("*.md"):
        assert "info.txt" not in path.read_text(encoding="utf-8"), str(path)
