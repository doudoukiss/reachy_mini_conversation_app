from __future__ import annotations

import json
from pathlib import Path

import yaml

from embodied_stack.shared.contracts.body import HeadCouplingRule, HeadJointProfile, HeadProfile

DEFAULT_HEAD_PROFILE_PATH = Path(__file__).resolve().parent / "profiles" / "robot_head_v1.json"


def default_head_profile() -> HeadProfile:
    return HeadProfile(
        profile_name="robot_head_v1",
        profile_version="blink_head_profile/v1",
        transport_boundary_version="semantic_body_transport/v1",
        servo_family="feetech_sts3032",
        baud_rate=1000000,
        auto_scan_baud_rates=[1000000, 115200],
        neutral_pose_label="looking_forward_normal_expression",
        default_transition_ms=160,
        minimum_transition_ms=80,
        neutral_recovery_ms=220,
        joints=[
            HeadJointProfile(joint_name="head_yaw", servo_ids=[1], neutral=2047, raw_min=1647, raw_max=2447, positive_direction="look_right"),
            HeadJointProfile(joint_name="head_pitch_pair_a", servo_ids=[2], neutral=2047, raw_min=1447, raw_max=2647, positive_direction="head_up_raw_plus"),
            HeadJointProfile(joint_name="head_pitch_pair_b", servo_ids=[3], neutral=2047, raw_min=1447, raw_max=2647, positive_direction="head_up_raw_minus"),
            HeadJointProfile(joint_name="lower_lid_left", servo_ids=[4], neutral=2047, raw_min=1947, raw_max=2347, positive_direction="close"),
            HeadJointProfile(joint_name="upper_lid_left", servo_ids=[5], neutral=2047, raw_min=1547, raw_max=2247, positive_direction="open"),
            HeadJointProfile(joint_name="lower_lid_right", servo_ids=[6], neutral=2047, raw_min=1747, raw_max=2147, positive_direction="open"),
            HeadJointProfile(joint_name="upper_lid_right", servo_ids=[7], neutral=2047, raw_min=1847, raw_max=2547, positive_direction="close"),
            HeadJointProfile(joint_name="eye_pitch", servo_ids=[8], neutral=2047, raw_min=1447, raw_max=2447, positive_direction="look_up"),
            HeadJointProfile(joint_name="eye_yaw", servo_ids=[9], neutral=2047, raw_min=1747, raw_max=2347, positive_direction="look_right"),
            HeadJointProfile(joint_name="brow_left", servo_ids=[10], neutral=2047, raw_min=1897, raw_max=2197, positive_direction="raise_brow"),
            HeadJointProfile(joint_name="brow_right", servo_ids=[11], neutral=2047, raw_min=1897, raw_max=2197, positive_direction="raise_brow_raw_minus"),
        ],
        coupling_rules=[
            HeadCouplingRule(
                name="neck_pitch_roll",
                description="Servos 2 and 3 share pitch, with asymmetric roll handled by moving only one side for tilt.",
                affected_joints=["head_pitch_pair_a", "head_pitch_pair_b"],
                notes=[
                    "Increasing servo 2 and decreasing servo 3 together means head up.",
                    "Positive roll is treated as tilt right by moving only servo 2 upward.",
                    "Negative roll is treated as tilt left by moving only servo 3 downward.",
                ],
            ),
            HeadCouplingRule(
                name="mirrored_eyelids",
                description="Left and right lid raw directions differ, so semantic open/close must be compiled per joint.",
                affected_joints=["lower_lid_left", "upper_lid_left", "lower_lid_right", "upper_lid_right"],
                notes=["Semantic lid openness must be expanded into per-side raw commands because left/right mechanics are mirrored."],
            ),
            HeadCouplingRule(
                name="eyes_follow_lids",
                description="Strong eye pitch should pull the upper lids slightly in the same semantic direction.",
                affected_joints=["eye_pitch", "upper_lid_left", "upper_lid_right"],
                notes=["Looking upward opens the upper lids slightly; looking downward reduces upper-lid openness."],
            ),
            HeadCouplingRule(
                name="mirrored_brows",
                description="Brows are symmetric semantically but use opposite raw directions on the right side.",
                affected_joints=["brow_left", "brow_right"],
            ),
        ],
        safe_speed=120,
        safe_speed_ceiling=120,
        safe_acceleration=40,
        safe_idle_torque_off=True,
        source_path=str(DEFAULT_HEAD_PROFILE_PATH),
        source_format="json",
        notes=[
            "Uploaded hardware is modeled as an expressive social bust/head rather than a mobile base.",
            "The body layer exposes normalized semantic joints only; servo IDs stay inside the profile and compiler.",
            "Lane 1 keeps virtual preview authoritative and reserves live writes for explicit operator-gated calibration flows.",
        ],
        pending_bench_confirmations=[
            "Confirm servo IDs 1..11 on the live shared bus before enabling powered transport.",
            "Confirm neutral alignment at raw 2047 for yaw, pitch pair, lids, eyes, and brows.",
            "Confirm mirrored eyelid and brow directions on the assembled head under power.",
            "Confirm safe speed and acceleration values once the head is powered.",
        ],
    )


def _load_profile_payload(profile_path: Path) -> tuple[dict, str]:
    suffix = profile_path.suffix.lower()
    raw = profile_path.read_text(encoding="utf-8")
    if suffix == ".json":
        return json.loads(raw), "json"
    if suffix in {".yaml", ".yml"}:
        return yaml.safe_load(raw), "yaml"

    try:
        return json.loads(raw), "json"
    except json.JSONDecodeError:
        return yaml.safe_load(raw), "yaml"


def load_head_profile(path: str | Path | None) -> HeadProfile:
    profile_path = Path(path) if path else DEFAULT_HEAD_PROFILE_PATH
    if profile_path is None:
        return default_head_profile()
    if not profile_path.exists():
        profile = default_head_profile()
        profile.source_path = str(profile_path)
        profile.source_format = profile_path.suffix.lstrip(".") or "json"
        profile.notes.append("Configured head profile path was missing; loaded the embedded default profile instead.")
        return profile
    payload, source_format = _load_profile_payload(profile_path)
    profile = HeadProfile.model_validate(payload)
    profile.source_path = str(profile_path)
    profile.source_format = source_format
    return profile


__all__ = ["DEFAULT_HEAD_PROFILE_PATH", "default_head_profile", "load_head_profile"]
