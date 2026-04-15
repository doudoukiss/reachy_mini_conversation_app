from __future__ import annotations

from pathlib import Path

from embodied_stack.body import calibration as calibration_module
from embodied_stack.body.profile import default_head_profile
from embodied_stack.body.servo_lab import build_servo_lab_catalog, resolve_servo_lab_move, save_servo_lab_calibration


def _saved_calibration():
    profile = default_head_profile()
    calibration = calibration_module.calibration_from_profile(profile, calibration_kind="saved")
    for joint in calibration.joint_records:
        joint.mirrored_direction_confirmed = True
    calibration.coupling_validation = {
        "neck_pitch_roll": "ok",
        "mirrored_eyelids": "ok",
        "mirrored_brows": "ok",
        "eyes_follow_lids": "ok",
        "range_conflicts": "ok",
    }
    return profile, calibration


def test_servo_lab_catalog_contains_all_11_joints() -> None:
    profile, calibration = _saved_calibration()
    current_positions = {joint.joint_name: joint.neutral for joint in profile.joints if joint.enabled}

    catalog = build_servo_lab_catalog(
        profile=profile,
        calibration=calibration,
        current_positions=current_positions,
        readback_errors={},
        transport=None,
        calibration_path="runtime/calibration.json",
    )

    assert catalog.to_payload()["joint_count"] == 11
    assert {item.joint_name for item in catalog.joints} == {
        "head_yaw",
        "head_pitch_pair_a",
        "head_pitch_pair_b",
        "eye_yaw",
        "eye_pitch",
        "upper_lid_left",
        "upper_lid_right",
        "lower_lid_left",
        "lower_lid_right",
        "brow_left",
        "brow_right",
    }


def test_servo_lab_catalog_uses_captured_calibration_without_profile_fallback_warning() -> None:
    profile = default_head_profile()
    calibration = calibration_module.calibration_from_profile(profile, calibration_kind="captured")
    current_positions = {joint.joint_name: joint.neutral for joint in profile.joints if joint.enabled}

    catalog = build_servo_lab_catalog(
        profile=profile,
        calibration=calibration,
        current_positions=current_positions,
        readback_errors={},
        transport=None,
        calibration_path="runtime/calibration.json",
    )

    assert catalog.calibration_kind == "captured"
    assert all("using_profile_fallback" not in item.warnings for item in catalog.joints)


def test_servo_lab_current_relative_move_uses_current_position_not_neutral() -> None:
    profile, calibration = _saved_calibration()

    plan = resolve_servo_lab_move(
        profile=profile,
        calibration=calibration,
        joint_name="head_yaw",
        reference_mode="current_delta",
        target_raw=None,
        delta_counts=10,
        current_position=2100,
        lab_min=None,
        lab_max=None,
    )

    assert plan.current_position == 2100
    assert plan.bounds.neutral == 2047
    assert plan.requested_target == 2110
    assert plan.effective_target == 2110


def test_servo_lab_move_bypasses_stage_b_smoke_limit_but_respects_hard_limits() -> None:
    profile, calibration = _saved_calibration()

    visible_move = resolve_servo_lab_move(
        profile=profile,
        calibration=calibration,
        joint_name="head_yaw",
        reference_mode="current_delta",
        target_raw=None,
        delta_counts=150,
        current_position=2047,
        lab_min=None,
        lab_max=None,
    )
    clamped_move = resolve_servo_lab_move(
        profile=profile,
        calibration=calibration,
        joint_name="head_yaw",
        reference_mode="current_delta",
        target_raw=None,
        delta_counts=1000,
        current_position=2047,
        lab_min=None,
        lab_max=None,
    )

    assert visible_move.effective_target == 2197
    assert all("smoke_limit_clamp" not in note for note in visible_move.clamp_notes)
    assert clamped_move.effective_target == 2447
    assert any("lab_max_clamp:head_yaw" in note for note in clamped_move.clamp_notes)


def test_servo_lab_save_calibration_clamps_to_profile_limits(tmp_path: Path) -> None:
    profile, calibration = _saved_calibration()

    updated, update = save_servo_lab_calibration(
        profile=profile,
        calibration=calibration,
        joint_name="head_yaw",
        output_path=str(tmp_path / "updated.json"),
        current_position=2055,
        save_current_as_neutral=True,
        raw_min=1000,
        raw_max=3000,
        confirm_mirrored=True,
    )

    record = next(item for item in updated.joint_records if item.joint_name == "head_yaw")
    assert record.neutral == 2055
    assert record.raw_min == 1647
    assert record.raw_max == 2447
    assert record.mirrored_direction_confirmed is True
    assert any("profile_raw_min_clamp:head_yaw" in note for note in update.clamp_notes)
    assert any("profile_raw_max_clamp:head_yaw" in note for note in update.clamp_notes)
