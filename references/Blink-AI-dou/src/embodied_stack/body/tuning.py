from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

from embodied_stack.shared.contracts.body import (
    BodyCommandAuditRecord,
    MotionKineticsProfile,
    MotionEnvelope,
    OperatingBandPolicy,
    SemanticActionDescriptor,
    SemanticActionTuningOverride,
    SemanticTeacherReviewRecord,
    SemanticTuningRecord,
    utc_now,
)

from .serial.bench import normalize_path
from .semantics import lookup_action_descriptor, semantic_action_descriptors

DEFAULT_SEMANTIC_TUNING_PATH = Path("runtime/body/semantic_tuning/robot_head_live_v1.json")
DEFAULT_TEACHER_REVIEW_PATH = Path("runtime/body/semantic_tuning/teacher_reviews.jsonl")


def default_semantic_tuning(
    *,
    profile_name: str,
    calibration_path: str | None = None,
) -> SemanticTuningRecord:
    return SemanticTuningRecord(
        profile_name=profile_name,
        calibration_path=normalize_path(calibration_path) if calibration_path else None,
        notes=["stage_d_default_semantic_tuning"],
    )


def load_semantic_tuning(
    *,
    profile_name: str,
    calibration_path: str | None = None,
    path: str | Path = DEFAULT_SEMANTIC_TUNING_PATH,
) -> SemanticTuningRecord:
    tuning_path = Path(path)
    if not tuning_path.exists():
        return default_semantic_tuning(profile_name=profile_name, calibration_path=calibration_path)
    payload = json.loads(tuning_path.read_text(encoding="utf-8"))
    record = SemanticTuningRecord.model_validate(payload)
    if calibration_path and not record.calibration_path:
        record.calibration_path = normalize_path(calibration_path)
    return record


def save_semantic_tuning(
    record: SemanticTuningRecord,
    path: str | Path = DEFAULT_SEMANTIC_TUNING_PATH,
) -> SemanticTuningRecord:
    record.updated_at = utc_now()
    tuning_path = Path(path)
    tuning_path.parent.mkdir(parents=True, exist_ok=True)
    tuning_path.write_text(json.dumps(record.model_dump(mode="json"), indent=2) + "\n", encoding="utf-8")
    return record


def tuning_override_names(record: SemanticTuningRecord) -> set[str]:
    return {name for name, override in record.action_overrides.items() if override is not None}


def semantic_library_payload(
    record: SemanticTuningRecord,
    *,
    smoke_safe_only: bool = False,
) -> list[SemanticActionDescriptor]:
    return list(
        semantic_action_descriptors(
            tuning_overrides=tuning_override_names(record),
            smoke_safe_only=smoke_safe_only,
        )
    )


def merge_semantic_tuning_delta(
    record: SemanticTuningRecord,
    delta: dict[str, object],
) -> SemanticTuningRecord:
    for field_name in (
        "tuning_lane",
        "eye_lid_coupling_coefficient",
        "eye_lid_coupling_threshold",
        "brow_asymmetry_correction",
        "neck_pitch_weight",
        "neck_roll_weight",
        "default_motion_envelope",
        "default_kinetics_profile",
    ):
        if field_name in delta:
            setattr(record, field_name, delta[field_name])

    operating_band_policy = delta.get("operating_band_policy")
    if isinstance(operating_band_policy, dict):
        merged_policy = record.operating_band_policy.model_dump(mode="json")
        merged_policy.update(dict(operating_band_policy))
        record.operating_band_policy = OperatingBandPolicy.model_validate(merged_policy)

    motion_envelopes_payload = delta.get("motion_envelopes")
    if isinstance(motion_envelopes_payload, dict):
        for envelope_name, envelope_payload in motion_envelopes_payload.items():
            if not isinstance(envelope_payload, dict):
                continue
            previous = record.motion_envelopes.get(str(envelope_name))
            merged = previous.model_dump(mode="json") if previous is not None else {}
            merged.update(dict(envelope_payload))
            record.motion_envelopes[str(envelope_name)] = MotionEnvelope.model_validate(merged)

    kinetics_payload = delta.get("motion_kinetics_profiles")
    if isinstance(kinetics_payload, dict):
        for profile_name, profile_payload in kinetics_payload.items():
            if not isinstance(profile_payload, dict):
                continue
            previous = record.motion_kinetics_profiles.get(str(profile_name))
            merged = previous.model_dump(mode="json") if previous is not None else {}
            merged.update(dict(profile_payload))
            record.motion_kinetics_profiles[str(profile_name)] = MotionKineticsProfile.model_validate(merged)

    notes = delta.get("notes")
    if isinstance(notes, list):
        record.notes = list(dict.fromkeys([*record.notes, *(str(item) for item in notes)]))

    overrides_payload = delta.get("action_overrides")
    if isinstance(overrides_payload, dict):
        for action_name, override_payload in overrides_payload.items():
            if not isinstance(override_payload, dict):
                continue
            previous = record.action_overrides.get(action_name, SemanticActionTuningOverride())
            merged = previous.model_dump(mode="json")
            if "pose_offsets" in override_payload and isinstance(override_payload["pose_offsets"], dict):
                merged["pose_offsets"] = {
                    **dict(previous.pose_offsets),
                    **{
                        str(key): float(value)
                        for key, value in dict(override_payload["pose_offsets"]).items()
                    },
                }
            if "notes" in override_payload and isinstance(override_payload["notes"], list):
                merged["notes"] = list(dict.fromkeys([*previous.notes, *(str(item) for item in override_payload["notes"])]))
            for key in (
                "intensity_multiplier",
                "upper_lid_coupling_scale",
                "brow_asymmetry_correction",
                "neck_pitch_weight",
                "neck_roll_weight",
                "motion_envelope",
                "kinetics_profile",
            ):
                if key in override_payload:
                    merged[key] = override_payload[key]
            record.action_overrides[str(action_name)] = SemanticActionTuningOverride.model_validate(merged)

    record.updated_at = utc_now()
    return record


def record_teacher_review(
    *,
    action: str,
    review: str,
    note: str | None = None,
    proposed_tuning_delta: dict[str, object] | None = None,
    apply_tuning: bool = False,
    latest_command_audit: BodyCommandAuditRecord | None = None,
    tuning_path: str | Path = DEFAULT_SEMANTIC_TUNING_PATH,
    reviews_path: str | Path = DEFAULT_TEACHER_REVIEW_PATH,
    profile_name: str,
    calibration_path: str | None = None,
) -> dict[str, object]:
    descriptor = lookup_action_descriptor(action)
    if descriptor is None:
        raise ValueError(f"unsupported_semantic_action:{action}")
    tuning = load_semantic_tuning(
        profile_name=profile_name,
        calibration_path=calibration_path,
        path=tuning_path,
    )
    applied = False
    if apply_tuning and proposed_tuning_delta:
        merge_semantic_tuning_delta(tuning, proposed_tuning_delta)
        save_semantic_tuning(tuning, tuning_path)
        applied = True

    review_record = SemanticTeacherReviewRecord(
        review_id=f"body-review-{uuid4().hex}",
        action=descriptor.canonical_name,
        family=descriptor.family,
        review=review,
        note=note,
        proposed_tuning_delta=proposed_tuning_delta or {},
        applied_tuning=applied,
        tuning_path=str(Path(tuning_path)),
        latest_command_audit=latest_command_audit.model_copy(deep=True) if latest_command_audit is not None else None,
    )
    review_file = Path(reviews_path)
    review_file.parent.mkdir(parents=True, exist_ok=True)
    with review_file.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(review_record.model_dump(mode="json")) + "\n")
    return {
        "review": review_record,
        "tuning": tuning,
        "descriptor": descriptor,
    }


__all__ = [
    "DEFAULT_SEMANTIC_TUNING_PATH",
    "DEFAULT_TEACHER_REVIEW_PATH",
    "default_semantic_tuning",
    "load_semantic_tuning",
    "merge_semantic_tuning_delta",
    "record_teacher_review",
    "save_semantic_tuning",
    "semantic_library_payload",
    "tuning_override_names",
]
