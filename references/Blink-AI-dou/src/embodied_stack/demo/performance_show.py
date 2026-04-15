from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass
from functools import lru_cache
import json
from pathlib import Path
import re
import shutil
import subprocess
from threading import Event, Lock
from time import perf_counter, sleep
from typing import TYPE_CHECKING, Any, Callable
from uuid import uuid4

from embodied_stack.body.profile import load_head_profile
from embodied_stack.body.primitives import (
    primitive_action_names,
    primitive_only_coverage,
)
from embodied_stack.body.range_demo import available_range_demo_presets, available_range_demo_sequences
from embodied_stack.body.expressive_motifs import resolve_expressive_motif
from embodied_stack.body.semantics import lookup_action_descriptor
from embodied_stack.body.serial.bench import DEFAULT_ARM_LEASE_PATH, read_arm_lease
from embodied_stack.persistence import load_json_model_or_quarantine, write_json_atomic
from embodied_stack.shared.contracts import (
    BodySemanticSmokeRequest,
    BodyExpressiveSequenceRequest,
    BodyPrimitiveSequenceRequest,
    BodyStagedSequenceRequest,
    DemoRunStatus,
    EpisodeExportSessionRequest,
    InvestorSceneRunRequest,
    OperatorInteractionResult,
    OperatorVoiceTurnRequest,
    PerceptionReplayRequest,
    PerceptionSnapshotSubmitRequest,
    PerformanceCue,
    PerformanceCueKind,
    PerformanceActuatorCoverageSummary,
    PerformanceMotionBeat,
    PerformanceMotionMarginRecord,
    PerformanceMotionOutcome,
    PerformanceProofBackendMode,
    PerformanceCueResult,
    PerformanceRunRequest,
    PerformanceRunResult,
    PerformanceSegment,
    PerformanceSegmentResult,
    PerformanceShowCatalogResponse,
    PerformanceShowDefinition,
    PrimitiveSequenceStep,
    ExpressiveMotifReference,
    StagedSequenceAccent,
    StagedSequenceStage,
    ResponseMode,
    ScorecardCriterion,
    IncidentReasonCategory,
    IncidentListScope,
    IncidentStatus,
    IncidentTicketRecord,
    IncidentTimelineEventType,
    IncidentTimelineRecord,
    IncidentUrgency,
    SessionStatus,
    UserMemoryRecord,
    SimulatedSensorEventRequest,
    VoiceRuntimeMode,
    utc_now,
)

if TYPE_CHECKING:
    from embodied_stack.brain.operator.service import OperatorConsoleService


DATA_DIR = Path(__file__).resolve().parent / "data"
REPO_ROOT = DATA_DIR.parents[3]
SHOW_DEFINITION_PATHS = {
    "investor_head_motion_v3": DATA_DIR / "performance_investor_head_motion_v3.json",
    "investor_eye_motion_v4": DATA_DIR / "performance_investor_eye_motion_v4.json",
    "investor_lid_motion_v5": DATA_DIR / "performance_investor_lid_motion_v5.json",
    "investor_brow_motion_v6": DATA_DIR / "performance_investor_brow_motion_v6.json",
    "investor_neck_motion_v7": DATA_DIR / "performance_investor_neck_motion_v7.json",
    "investor_expressive_motion_v8": DATA_DIR / "performance_investor_expressive_motion_v8.json",
    "robot_head_servo_range_showcase_v1": DATA_DIR / "performance_robot_head_servo_range_showcase_v1.json",
}
SHOW_TUNING_PATHS = {
    "investor_head_motion_v3": Path("runtime/body/semantic_tuning/robot_head_investor_show_v3.json"),
    "investor_eye_motion_v4": Path("runtime/body/semantic_tuning/robot_head_investor_show_v4.json"),
    "investor_lid_motion_v5": Path("runtime/body/semantic_tuning/robot_head_investor_show_v5.json"),
    "investor_brow_motion_v6": Path("runtime/body/semantic_tuning/robot_head_investor_show_v6.json"),
    "investor_neck_motion_v7": Path("runtime/body/semantic_tuning/robot_head_investor_show_v7.json"),
    "investor_expressive_motion_v8": Path("runtime/body/semantic_tuning/robot_head_investor_show_v8.json"),
}
RANGE_DEMO_DEFAULT_PRESET = "investor_show_joint_envelope_v1"
LIVE_SAFE_ACTIONS = {
    "friendly",
    "neutral",
    "thinking",
    "concerned",
    "confused",
    "listen_attentively",
    "safe_idle",
    "look_forward",
    "look_left",
    "look_right",
    "look_up",
    "look_down_briefly",
    "look_far_left",
    "look_far_right",
    "look_far_up",
    "look_far_down",
    "look_at_user",
    "curious_bright",
    "focused_soft",
    "playful",
    "bashful",
    "eyes_widen",
    "half_lid_focus",
    "brow_raise_soft",
    "brow_knit_soft",
    "blink_soft",
    "double_blink",
    "wink_left",
    "wink_right",
    "acknowledge_light",
    "playful_peek_left",
    "playful_peek_right",
    "tilt_curious",
    "recover_neutral",
    "youthful_greeting",
    "soft_reengage",
    "playful_react",
}
ACTION_INTENSITY_LIMITS = {
    "friendly": 0.9,
    "neutral": 0.85,
    "thinking": 0.9,
    "concerned": 0.88,
    "confused": 0.86,
    "listen_attentively": 0.92,
    "safe_idle": 0.82,
    "look_forward": 0.92,
    "look_left": 0.96,
    "look_right": 0.96,
    "look_up": 0.9,
    "look_down_briefly": 0.88,
    "look_far_left": 0.92,
    "look_far_right": 0.92,
    "look_far_up": 0.88,
    "look_far_down": 0.84,
    "look_at_user": 0.94,
    "curious_bright": 0.92,
    "focused_soft": 0.88,
    "playful": 0.82,
    "bashful": 0.82,
    "eyes_widen": 0.84,
    "half_lid_focus": 0.88,
    "brow_raise_soft": 0.9,
    "brow_knit_soft": 0.86,
    "blink_soft": 0.82,
    "double_blink": 0.8,
    "wink_left": 0.8,
    "wink_right": 0.8,
    "acknowledge_light": 0.86,
    "playful_peek_left": 0.82,
    "playful_peek_right": 0.82,
    "nod_small": 0.76,
    "nod_medium": 0.8,
    "tilt_curious": 0.74,
    "recover_neutral": 0.9,
    "youthful_greeting": 0.84,
    "soft_reengage": 0.84,
    "playful_react": 0.8,
}
LIVE_SAFE_ACTIONS.update(primitive_action_names())
ACTION_INTENSITY_LIMITS.update({name: 1.0 for name in primitive_action_names()})
DEFAULT_NARRATION_POLL_SECONDS = 0.05
BODY_SETTLE_SECONDS = 0.18
BODY_SAFE_IDLE_SETTLE_SECONDS = 0.35
DEFAULT_SHOW_NAME = "investor_expressive_motion_v8"
MACOS_SAY_VOICE_MODES = {
    VoiceRuntimeMode.MACOS_SAY,
    VoiceRuntimeMode.BROWSER_LIVE_MACOS_SAY,
}
VOICE_PRESETS: dict[str, dict[str, object]] = {
    "english_cute_character": {
        "language": "en",
        "voice_name": "Samantha",
        "rate": 185,
    },
    "chinese_cute_character": {
        "language": "zh-CN",
        "voice_name": "Tingting",
        "rate": 210,
    },
    "english_keynote": {
        "language": "en",
        "voice_name": "Samantha",
        "rate": 185,
    },
    "english_warm": {
        "language": "en",
        "voice_name": "Samantha",
        "rate": 192,
    },
    "english_young_character_v3": {
        "language": "en",
        "voice_name": "Samantha",
        "rate": 185,
    },
    "chinese_keynote": {
        "language": "zh-CN",
        "voice_name": "Tingting",
        "rate": 210,
    },
    "chinese_young_character_v3": {
        "language": "zh-CN",
        "voice_name": "Tingting",
        "rate": 210,
    },
    "english_cute_character_v4": {
        "language": "en",
        "voice_name": "Samantha",
        "rate": 185,
    },
    "chinese_cute_character_v4": {
        "language": "zh-CN",
        "voice_name": "Tingting",
        "rate": 210,
    },
}
DEFAULT_VOICE_PRESET_BY_LANGUAGE = {
    "en": "english_cute_character",
    "en-us": "english_cute_character",
    "zh": "chinese_cute_character",
    "zh-cn": "chinese_cute_character",
}
ACTUATOR_GROUPS = (
    "head_yaw",
    "head_pitch_pair",
    "eye_yaw",
    "eye_pitch",
    "upper_lids",
    "lower_lids",
    "brows",
)
JOINT_GROUPS = {
    "head_yaw": "head_yaw",
    "head_pitch_pair_a": "head_pitch_pair",
    "head_pitch_pair_b": "head_pitch_pair",
    "eye_yaw": "eye_yaw",
    "eye_pitch": "eye_pitch",
    "upper_lid_left": "upper_lids",
    "upper_lid_right": "upper_lids",
    "lower_lid_left": "lower_lids",
    "lower_lid_right": "lower_lids",
    "brow_left": "brows",
    "brow_right": "brows",
}
HEAD_AND_EYE_GROUPS = {"head_yaw", "head_pitch_pair", "eye_yaw", "eye_pitch"}
EXPLICIT_ACTION_COVERAGE = {
    "look_forward": {"head_yaw", "eye_yaw"},
    "look_at_user": {"head_yaw", "eye_yaw", "head_pitch_pair", "eye_pitch"},
    "look_left": {"head_yaw", "eye_yaw"},
    "look_right": {"head_yaw", "eye_yaw"},
    "look_up": {"head_pitch_pair", "eye_pitch"},
    "look_down_briefly": {"head_pitch_pair", "eye_pitch"},
    "look_far_left": {"head_yaw", "eye_yaw"},
    "look_far_right": {"head_yaw", "eye_yaw"},
    "look_far_up": {"head_pitch_pair", "eye_pitch"},
    "look_far_down": {"head_pitch_pair", "eye_pitch"},
    "friendly": {"head_pitch_pair", "upper_lids", "lower_lids", "brows"},
    "curious_bright": {"head_pitch_pair", "eye_yaw", "eye_pitch", "upper_lids", "lower_lids", "brows"},
    "focused_soft": {"head_pitch_pair", "eye_pitch", "upper_lids", "lower_lids", "brows"},
    "playful": {"head_yaw", "head_pitch_pair", "eye_yaw", "upper_lids", "lower_lids", "brows"},
    "bashful": {"head_yaw", "head_pitch_pair", "eye_yaw", "eye_pitch", "upper_lids", "lower_lids", "brows"},
    "thinking": {"head_pitch_pair", "eye_yaw", "eye_pitch", "upper_lids", "lower_lids", "brows"},
    "concerned": {"head_pitch_pair", "upper_lids", "lower_lids", "brows"},
    "confused": {"head_pitch_pair", "eye_yaw", "upper_lids", "lower_lids", "brows"},
    "listen_attentively": {"head_pitch_pair", "upper_lids", "lower_lids", "brows"},
    "safe_idle": {"upper_lids", "lower_lids"},
    "eyes_widen": {"upper_lids", "lower_lids", "brows"},
    "half_lid_focus": {"upper_lids", "lower_lids"},
    "brow_raise_soft": {"brows"},
    "brow_knit_soft": {"brows"},
    "blink_soft": {"upper_lids", "lower_lids"},
    "double_blink": {"upper_lids", "lower_lids", "brows"},
    "wink_left": {"upper_lids", "lower_lids", "brows"},
    "wink_right": {"upper_lids", "lower_lids", "brows"},
    "acknowledge_light": {"head_yaw", "eye_pitch", "brows"},
    "playful_peek_left": {"head_yaw", "eye_yaw", "brows"},
    "playful_peek_right": {"head_yaw", "eye_yaw", "brows"},
    "tilt_curious": {"head_pitch_pair", "brows"},
    "recover_neutral": {"head_yaw", "head_pitch_pair", "eye_yaw", "eye_pitch", "upper_lids", "lower_lids", "brows"},
    "youthful_greeting": {"head_yaw", "head_pitch_pair", "eye_yaw", "eye_pitch", "upper_lids", "lower_lids", "brows"},
    "soft_reengage": {"head_pitch_pair", "eye_pitch", "upper_lids", "lower_lids", "brows"},
    "playful_react": {"head_yaw", "head_pitch_pair", "eye_yaw", "upper_lids", "lower_lids", "brows"},
}
EXPLICIT_ACTION_COVERAGE.update(primitive_only_coverage())
DEFAULT_MIN_MARGIN_PERCENT = {
    "head_yaw": 10.0,
    "head_pitch_pair": 10.0,
    "eye_yaw": 8.0,
    "eye_pitch": 10.0,
    "upper_lids": 12.0,
    "lower_lids": 12.0,
    "brows": 12.0,
}
_VOICE_LINE_RE = re.compile(r"^(?P<name>.+?)\\s{2,}[a-z_#].*$", re.IGNORECASE)
_NOD_FAMILY_ACTIONS = {"nod_small", "nod_medium"}
_TRANSIENT_BLINK_ACTIONS = {"blink_soft", "double_blink", "wink_left", "wink_right"}
_AGGRESSIVE_LID_ACTIONS = {
    "eyes_widen",
    "half_lid_focus",
    "blink_soft",
    "double_blink",
    "wink_left",
    "wink_right",
}
_SUPPORTED_DETERMINISTIC_SCENE_TEMPLATES = {
    "grounded_sign",
    "memory_follow_up",
    "oversight_accessibility",
}
_SUPPORTED_DETERMINISTIC_TURN_TEMPLATES = {
    "memory_intro",
    "event_lookup",
}


@dataclass(frozen=True)
class ResolvedNarrationConfig:
    language: str
    voice_mode: VoiceRuntimeMode
    voice_preset: str | None
    voice_name: str | None
    voice_rate: int | None
    notes: tuple[str, ...] = ()


class PerformanceShowCancelled(RuntimeError):
    """Raised when a background performance run is explicitly cancelled."""


def _normalized_language(language: str | None) -> str:
    return (language or "en").strip().lower() or "en"


def _language_candidates(language: str | None) -> list[str]:
    normalized = _normalized_language(language)
    candidates = [normalized]
    if "-" in normalized:
        base = normalized.split("-", 1)[0]
        if base not in candidates:
            candidates.append(base)
    elif normalized == "zh":
        candidates.append("zh-cn")
    return candidates


def _localized_value(primary: str | None, localized: dict[str, str] | None, language: str | None) -> str | None:
    localized = localized or {}
    for candidate in _language_candidates(language):
        if candidate in localized:
            return localized[candidate]
    return primary


@lru_cache(maxsize=1)
def _macos_voice_names() -> tuple[str, ...]:
    say_path = shutil.which("say")
    if not say_path:
        return ()
    try:
        completed = subprocess.run(
            [say_path, "-v", "?"],
            check=False,
            capture_output=True,
            text=True,
            timeout=2.0,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ()
    if completed.returncode != 0:
        return ()
    names: list[str] = []
    for line in completed.stdout.splitlines():
        candidate = line.strip()
        if not candidate:
            continue
        match = _VOICE_LINE_RE.match(candidate)
        if match is not None:
            names.append(match.group("name").strip())
    return tuple(dict.fromkeys(names))


def _voice_preset_for_language(language: str | None) -> str:
    for candidate in _language_candidates(language):
        preset = DEFAULT_VOICE_PRESET_BY_LANGUAGE.get(candidate)
        if preset is not None:
            return preset
    return "english_cute_character"


def _resolve_payload_path(payload: dict[str, Any], path: str) -> object:
    current: object = payload
    for segment in path.split("."):
        if isinstance(current, dict):
            current = current.get(segment)
        elif isinstance(current, list):
            try:
                current = current[int(segment)]
            except (TypeError, ValueError, IndexError):
                return None
        else:
            return None
    return current


def _resolve_show_path(path: str) -> str:
    candidate = Path(path).expanduser()
    if candidate.is_absolute():
        return str(candidate)
    data_candidate = (DATA_DIR / candidate).resolve()
    if data_candidate.exists():
        return str(data_candidate)
    repo_candidate = (REPO_ROOT / candidate).resolve()
    return str(repo_candidate)


def _speech_unit_count(text: str, *, language: str) -> int:
    cleaned = " ".join((text or "").split())
    if not cleaned:
        return 0
    normalized = _normalized_language(language)
    if normalized.startswith("zh"):
        return len(cleaned.replace(" ", ""))
    return len([item for item in cleaned.split(" ") if item])


def _speech_timeout_seconds(*, text: str, language: str, voice_rate: int | None) -> float:
    units = max(1, _speech_unit_count(text, language=language))
    normalized = _normalized_language(language)
    if normalized.startswith("zh"):
        units_per_minute = max(120.0, float(voice_rate or 190) * 1.7)
    else:
        units_per_minute = max(120.0, float(voice_rate or 190))
    duration_seconds = (units / units_per_minute) * 60.0
    return max(2.0, min(24.0, round(duration_seconds * 2.4 + 1.5, 2)))


def _empty_coverage_summary() -> PerformanceActuatorCoverageSummary:
    return PerformanceActuatorCoverageSummary()


def _coverage_from_groups(groups: set[str]) -> PerformanceActuatorCoverageSummary:
    payload = {group: (group in groups) for group in ACTUATOR_GROUPS}
    return PerformanceActuatorCoverageSummary.model_validate(payload)


def _merge_coverage(
    base: PerformanceActuatorCoverageSummary,
    other: PerformanceActuatorCoverageSummary,
) -> PerformanceActuatorCoverageSummary:
    payload = {
        group: bool(getattr(base, group) or getattr(other, group))
        for group in ACTUATOR_GROUPS
    }
    return PerformanceActuatorCoverageSummary.model_validate(payload)


def _action_coverage_groups(action: str) -> set[str]:
    groups = set(EXPLICIT_ACTION_COVERAGE.get(action, set()))
    descriptor = lookup_action_descriptor(action)
    if descriptor is None:
        return groups
    if descriptor.primary_actuator_group in ACTUATOR_GROUPS:
        groups.add(str(descriptor.primary_actuator_group))
    groups.update(group for group in descriptor.support_actuator_groups if group in ACTUATOR_GROUPS)
    return groups


def _profile_joint_ranges(head_profile_path: str | None) -> dict[str, tuple[int, int, int]]:
    profile = load_head_profile(head_profile_path)
    return {
        joint.joint_name: (int(joint.raw_min), int(joint.raw_max), int(joint.neutral))
        for joint in profile.joints
        if joint.enabled
    }


def _normalized_motion_outcome(
    *,
    audit: dict[str, Any],
    body_state: dict[str, Any],
) -> PerformanceMotionOutcome:
    outcome_status = str(audit.get("outcome_status") or "").lower()
    reason_code = str(audit.get("reason_code") or "")
    transport_status = audit.get("transport_status") or {}
    transport_mode = str(
        body_state.get("transport_mode")
        or transport_status.get("mode")
        or audit.get("transport_mode")
        or ""
    )
    confirmed_live = bool(
        body_state.get("transport_confirmed_live")
        if body_state.get("transport_confirmed_live") is not None
        else transport_status.get("confirmed_live")
    )
    executed_live_write = bool(audit.get("executed_frame_count")) or bool(audit.get("compiled_targets"))
    accepted = outcome_status not in {"blocked", "rejected", "transport_warning"}
    if accepted and transport_mode == "live_serial" and (confirmed_live or executed_live_write):
        return PerformanceMotionOutcome.LIVE_APPLIED
    if accepted and (
        "preview" in outcome_status
        or transport_mode != "live_serial"
        or (not confirmed_live and not executed_live_write)
        or reason_code in {"transport_unconfirmed", "motion_not_armed", "transport_unavailable", "missing_profile"}
    ):
        return PerformanceMotionOutcome.PREVIEW_ONLY
    return PerformanceMotionOutcome.BLOCKED


def _health_flags(
    action: str,
    *,
    audit: dict[str, Any],
) -> tuple[list[str], list[str], list[str]]:
    health_summary = audit.get("health_summary") or {}
    fault_classification = str(audit.get("fault_classification") or "")
    error_joints: list[str] = []
    abnormal_load_joints: list[str] = []
    flags: list[str] = []
    for joint_name, payload in health_summary.items():
        if not isinstance(payload, dict):
            continue
        error_bits = [str(item) for item in payload.get("error_bits") or []]
        non_voltage_error_bits = [item for item in error_bits if item != "input_voltage"]
        reason_code = str(payload.get("reason_code") or "")
        status_summary = str(payload.get("status_summary") or "")
        load_value = payload.get("load")
        current_value = payload.get("current")
        if non_voltage_error_bits:
            error_joints.append(str(joint_name))
            flags.append(f"{joint_name}:error_bits={','.join(non_voltage_error_bits)}")
        elif "input_voltage" in error_bits:
            if fault_classification == "confirmed_power_fault":
                error_joints.append(str(joint_name))
                flags.append(f"{joint_name}:error_bits=input_voltage")
            else:
                flags.append(f"{joint_name}:suspect_voltage_event")
        combined = " ".join([reason_code, *error_bits]).lower()
        overloaded = any(token in combined for token in {"overload", "over-current", "overcurrent"})
        load_suspicious = isinstance(load_value, (int, float)) and abs(float(load_value)) >= 900.0
        current_suspicious = isinstance(current_value, (int, float)) and abs(float(current_value)) >= 900.0
        if overloaded or load_suspicious or current_suspicious:
            abnormal_load_joints.append(str(joint_name))
            if overloaded:
                detail = reason_code or ",".join(error_bits) or status_summary or "detected"
            elif load_suspicious:
                detail = f"load={load_value}"
            else:
                detail = f"current={current_value}"
            flags.append(f"{joint_name}:abnormal_load={detail}")
    if audit.get("fault_classification"):
        flags.append(f"{action}:fault_classification={audit['fault_classification']}")
    if audit.get("readback_implausible"):
        flags.append(f"{action}:readback_implausible")
    if audit.get("confirmation_result"):
        flags.append(f"{action}:confirmation_result={audit['confirmation_result']}")
    if str(audit.get("reason_code") or "") not in {"", "ok"}:
        flags.append(f"{action}:reason_code={audit.get('reason_code')}")
    if audit.get("detail"):
        flags.append(f"{action}:detail={audit.get('detail')}")
    return list(dict.fromkeys(flags)), sorted(set(error_joints)), sorted(set(abnormal_load_joints))


def _margin_thresholds_for_action(
    *,
    action: str,
    narration_linked: bool,
) -> dict[str, float]:
    if action == "body_range_demo:servo_range_showcase_v1":
        return {group: 0.0 for group in DEFAULT_MIN_MARGIN_PERCENT}
    thresholds = dict(DEFAULT_MIN_MARGIN_PERCENT)
    if action in _TRANSIENT_BLINK_ACTIONS and not narration_linked:
        thresholds["upper_lids"] = 8.0
        thresholds["lower_lids"] = 8.0
    return thresholds


def _motion_margin_record(
    *,
    action: str,
    coverage_tags: list[str],
    audit: dict[str, Any],
    body_state: dict[str, Any],
    narration_linked: bool = False,
) -> tuple[PerformanceMotionMarginRecord, PerformanceActuatorCoverageSummary]:
    threshold_percent_by_group = _margin_thresholds_for_action(
        action=action,
        narration_linked=narration_linked,
    )
    joint_ranges = _profile_joint_ranges(str(body_state.get("head_profile_path") or ""))
    compiled_targets = {
        str(joint_name): int(value)
        for joint_name, value in (audit.get("compiled_targets") or {}).items()
    }
    before_readback = {
        str(joint_name): int(value)
        for joint_name, value in (audit.get("before_readback") or {}).items()
        if value is not None
    }
    after_readback = {
        str(joint_name): int(value)
        for joint_name, value in (audit.get("after_readback") or {}).items()
        if value is not None
    }
    per_joint_margins: dict[str, float] = {}
    per_group_margins: dict[str, list[float]] = {}
    coverage_groups: set[str] = set()
    safety_gate_passed = True

    for joint_name, target in compiled_targets.items():
        if joint_name not in joint_ranges:
            continue
        raw_min, raw_max, neutral = joint_ranges[joint_name]
        span = max(1, raw_max - raw_min)
        remaining_margin = min(target - raw_min, raw_max - target)
        margin_percent = round((remaining_margin / span) * 100.0, 2)
        per_joint_margins[joint_name] = margin_percent
        group = JOINT_GROUPS.get(joint_name)
        if group is None:
            continue
        per_group_margins.setdefault(group, []).append(margin_percent)
        threshold = threshold_percent_by_group[group]
        if margin_percent < threshold:
            safety_gate_passed = False
        target_delta = abs(target - neutral)
        if (target_delta / span) >= 0.08:
            coverage_groups.add(group)

    live_readback_checked = bool(after_readback)
    if live_readback_checked:
        for joint_name, current in after_readback.items():
            group = JOINT_GROUPS.get(joint_name)
            if group is None or joint_name not in joint_ranges:
                continue
            raw_min, raw_max, _neutral = joint_ranges[joint_name]
            span = max(1, raw_max - raw_min)
            if joint_name in before_readback and abs(current - before_readback[joint_name]) / span >= 0.05:
                coverage_groups.add(group)

    flags, error_joints, abnormal_load_joints = _health_flags(action, audit=audit)
    fault_classification = str(audit.get("fault_classification") or "") or None
    power_health_classification = str(audit.get("power_health_classification") or "") or None
    suspect_voltage_event = bool(audit.get("suspect_voltage_event"))
    readback_implausible = bool(audit.get("readback_implausible"))
    confirmation_read_performed = bool(audit.get("confirmation_read_performed"))
    confirmation_result = str(audit.get("confirmation_result") or "") or None
    preflight_passed = audit.get("preflight_passed")
    preflight_failure_reason = str(audit.get("preflight_failure_reason") or "") or None
    if abnormal_load_joints or fault_classification == "confirmed_power_fault":
        safety_gate_passed = False
    elif error_joints:
        safety_gate_passed = False

    inferred_groups = _action_coverage_groups(action)
    inferred_groups.update(group for group in coverage_tags if group in ACTUATOR_GROUPS)
    coverage_groups.update(inferred_groups)
    outcome = _normalized_motion_outcome(audit=audit, body_state=body_state)
    if outcome == PerformanceMotionOutcome.BLOCKED:
        safety_gate_passed = False

    min_margin_percent = min(per_joint_margins.values()) if per_joint_margins else None
    min_margin_percent_by_group = {
        group: round(min(values), 2)
        for group, values in per_group_margins.items()
        if values
    }
    max_margin_percent_by_group = {
        group: round(max(values), 2)
        for group, values in per_group_margins.items()
        if values
    }
    worst_actuator_group = (
        min(min_margin_percent_by_group.items(), key=lambda item: item[1])[0]
        if min_margin_percent_by_group
        else None
    )
    record = PerformanceMotionMarginRecord(
        action=action,
        outcome=outcome,
        safety_gate_passed=safety_gate_passed,
        peak_calibrated_target=compiled_targets,
        latest_readback=after_readback,
        min_remaining_margin_percent_by_joint=per_joint_margins,
        min_remaining_margin_percent_by_group=min_margin_percent_by_group,
        max_remaining_margin_percent_by_group=max_margin_percent_by_group,
        threshold_percent_by_group=threshold_percent_by_group,
        min_remaining_margin_percent=round(float(min_margin_percent), 2) if min_margin_percent is not None else None,
        worst_actuator_group=worst_actuator_group,
        health_flags=flags,
        error_joints=error_joints,
        abnormal_load_joints=abnormal_load_joints,
        fault_classification=fault_classification,
        power_health_classification=power_health_classification,
        suspect_voltage_event=suspect_voltage_event,
        readback_implausible=readback_implausible,
        confirmation_read_performed=confirmation_read_performed,
        confirmation_result=confirmation_result,
        preflight_passed=preflight_passed,
        preflight_failure_reason=preflight_failure_reason,
        reason_code=str(audit.get("reason_code") or "") or None,
        detail=str(audit.get("detail") or "") or None,
        transport_mode=str(body_state.get("transport_mode") or audit.get("transport_mode") or "") or None,
        transport_confirmed_live=body_state.get("transport_confirmed_live"),
        live_readback_checked=live_readback_checked,
    )
    return record, _coverage_from_groups(coverage_groups)


def _projection_outcome_from_body_state(body_state: dict[str, Any]) -> PerformanceMotionOutcome | None:
    audit = body_state.get("latest_command_audit") or {}
    if isinstance(audit, dict) and audit:
        action = str(audit.get("canonical_action_name") or audit.get("requested_action_name") or "projection")
        record, _coverage = _motion_margin_record(
            action=action,
            coverage_tags=[],
            audit=audit,
            body_state=body_state,
            narration_linked=False,
        )
        return record.outcome
    character_projection = body_state.get("character_projection") or {}
    raw_outcome = str(character_projection.get("outcome") or "").lower()
    transport_mode = str(body_state.get("transport_mode") or "")
    confirmed_live = bool(body_state.get("transport_confirmed_live"))
    if raw_outcome in {"robot_head_applied", "safe_idle_applied"} and transport_mode == "live_serial" and confirmed_live:
        return PerformanceMotionOutcome.LIVE_APPLIED
    if "preview_only" in raw_outcome or raw_outcome in {"projection_preview_only", "robot_head_blocked_preview_only"}:
        return PerformanceMotionOutcome.PREVIEW_ONLY
    if raw_outcome:
        return PerformanceMotionOutcome.BLOCKED
    return None


def _aggregate_motion_results(results: list[dict[str, Any]]) -> dict[str, Any]:
    aggregate_coverage = _empty_coverage_summary()
    last_margin_record: PerformanceMotionMarginRecord | None = None
    saw_live = False
    saw_preview = False
    saw_blocked = False
    degraded = False
    for item in results:
        coverage_payload = item.get("actuator_coverage")
        if isinstance(coverage_payload, dict) and coverage_payload:
            aggregate_coverage = _merge_coverage(
                aggregate_coverage,
                PerformanceActuatorCoverageSummary.model_validate(coverage_payload),
            )
        margin_payload = item.get("motion_margin_record")
        if isinstance(margin_payload, dict) and margin_payload:
            last_margin_record = PerformanceMotionMarginRecord.model_validate(margin_payload)
            degraded = degraded or (not last_margin_record.safety_gate_passed)
        outcome = str(item.get("motion_outcome") or "")
        if outcome == PerformanceMotionOutcome.LIVE_APPLIED.value:
            saw_live = True
        elif outcome == PerformanceMotionOutcome.PREVIEW_ONLY.value:
            saw_preview = True
        elif outcome == PerformanceMotionOutcome.BLOCKED.value:
            saw_blocked = True
        degraded = degraded or bool(item.get("degraded"))
    if saw_blocked:
        aggregate_outcome = PerformanceMotionOutcome.BLOCKED
    elif saw_preview and not saw_live:
        aggregate_outcome = PerformanceMotionOutcome.PREVIEW_ONLY
    elif saw_live:
        aggregate_outcome = PerformanceMotionOutcome.LIVE_APPLIED
    else:
        aggregate_outcome = None
    return {
        "motion_outcome": aggregate_outcome.value if aggregate_outcome is not None else None,
        "body_projection_outcome": aggregate_outcome.value if aggregate_outcome is not None else None,
        "preview_only": aggregate_outcome == PerformanceMotionOutcome.PREVIEW_ONLY,
        "motion_margin_record": (
            last_margin_record.model_dump(mode="json") if last_margin_record is not None else None
        ),
        "actuator_coverage": aggregate_coverage.model_dump(mode="json"),
        "degraded": degraded,
    }


def _merge_min_margins(
    base: dict[str, float],
    other: dict[str, float],
) -> dict[str, float]:
    merged = dict(base)
    for group, value in other.items():
        if group not in merged:
            merged[group] = value
        else:
            merged[group] = min(float(merged[group]), float(value))
    return {group: round(float(value), 2) for group, value in merged.items()}


def _merge_max_margins(
    base: dict[str, float],
    other: dict[str, float],
) -> dict[str, float]:
    merged = dict(base)
    for group, value in other.items():
        if group not in merged:
            merged[group] = value
        else:
            merged[group] = max(float(merged[group]), float(value))
    return {group: round(float(value), 2) for group, value in merged.items()}


def _worst_actuator_group(min_margins: dict[str, float]) -> str | None:
    if not min_margins:
        return None
    return min(min_margins.items(), key=lambda item: float(item[1]))[0]


def _current_arm_lease_metadata() -> tuple[str | None, str | None]:
    lease = read_arm_lease(DEFAULT_ARM_LEASE_PATH)
    if not lease:
        return None, None
    author = lease.get("author")
    port = lease.get("port")
    return (
        str(author) if isinstance(author, str) and author else None,
        str(port) if isinstance(port, str) and port else None,
    )


def _flatten_cue_results(run: PerformanceRunResult) -> list[dict[str, object]]:
    flattened: list[dict[str, object]] = []
    for segment in run.segment_results:
        for cue in segment.cue_results:
            flattened.append(
                {
                    "segment_id": segment.segment_id,
                    "segment_title": segment.title,
                    "cue_result": cue.model_dump(mode="json"),
                }
            )
    return flattened


def _proof_results(run: PerformanceRunResult) -> list[dict[str, object]]:
    return [
        item
        for item in _flatten_cue_results(run)
        if item["cue_result"].get("proof_checks") or item["cue_result"].get("fallback_used")
    ]


def _narration_cues(definition: PerformanceShowDefinition) -> list[tuple[PerformanceSegment, PerformanceCue]]:
    return [
        (segment, cue)
        for segment in definition.segments
        for cue in segment.cues
        if cue.cue_kind == PerformanceCueKind.NARRATE
    ]


def _bool_status_label(value: bool) -> str:
    return "passed" if value else "failed"


def _total_duration_seconds(definition: PerformanceShowDefinition) -> int:
    return sum(segment.target_duration_seconds for segment in definition.segments)


def _include_cue_for_request(cue: PerformanceCue, request: PerformanceRunRequest) -> bool:
    if request.cue_ids and cue.cue_id not in request.cue_ids:
        return False
    if request.narration_only:
        return cue.cue_kind in {
            PerformanceCueKind.CAPTION,
            PerformanceCueKind.PROMPT,
            PerformanceCueKind.NARRATE,
            PerformanceCueKind.PAUSE,
        }
    if request.proof_only:
        return cue.cue_kind != PerformanceCueKind.NARRATE
    return True


def select_show_definition(
    definition: PerformanceShowDefinition,
    request: PerformanceRunRequest | None = None,
) -> PerformanceShowDefinition:
    request = request or PerformanceRunRequest()
    selected_segments: list[PerformanceSegment] = []
    for segment in definition.segments:
        if request.segment_ids and segment.segment_id not in request.segment_ids:
            continue
        cues = [cue.model_copy(deep=True) for cue in segment.cues if _include_cue_for_request(cue, request)]
        if not cues:
            continue
        selected_segments.append(segment.model_copy(update={"cues": cues}, deep=True))
    if not selected_segments:
        raise ValueError("performance_show_selection_empty")
    return definition.model_copy(update={"segments": selected_segments}, deep=True)


def list_packaged_performance_shows() -> list[PerformanceShowDefinition]:
    items: list[PerformanceShowDefinition] = []
    for show_name in SHOW_DEFINITION_PATHS:
        items.append(load_show_definition(show_name))
    return items


def load_show_definition(show_name: str) -> PerformanceShowDefinition:
    path = SHOW_DEFINITION_PATHS.get(show_name)
    if path is None:
        raise KeyError(show_name)
    payload = json.loads(path.read_text(encoding="utf-8"))
    definition = PerformanceShowDefinition.model_validate(payload)
    validate_show_definition(definition)
    return definition


def _validate_body_action(cue: PerformanceCue) -> list[str]:
    issues: list[str] = []
    beats = list(cue.motion_track)
    primitive_steps = list(cue.primitive_sequence)
    staged_actions: list[tuple[str, float | None]] = []
    motif_actions: list[tuple[str, float | None]] = []
    if cue.cue_kind == PerformanceCueKind.BODY_SEMANTIC_SMOKE:
        if not cue.action:
            return ["body_semantic_smoke_cue_requires_action"]
        beats.append(
            PerformanceMotionBeat(
                offset_ms=0,
                action=cue.action,
                intensity=cue.intensity,
                repeat_count=cue.repeat_count,
                note=cue.note,
            )
        )
    if cue.cue_kind == PerformanceCueKind.BODY_PRIMITIVE_SEQUENCE:
        if not primitive_steps:
            return ["body_primitive_sequence_cue_requires_steps"]
        for step in primitive_steps:
            descriptor = lookup_action_descriptor(step.action)
            if descriptor is None:
                issues.append(f"unsupported_body_action:{step.action}")
                continue
            if step.action not in LIVE_SAFE_ACTIONS:
                issues.append(f"body_action_not_in_public_live_safe_palette:{step.action}")
            if descriptor.grounding != "primitive":
                issues.append(f"body_primitive_sequence_requires_primitive:{cue.cue_id}:{step.action}")
            if not descriptor.smoke_safe:
                issues.append(f"body_action_not_smoke_safe:{step.action}")
            if step.intensity is not None:
                ceiling = ACTION_INTENSITY_LIMITS.get(step.action, 0.70)
                if step.intensity > ceiling:
                    issues.append(
                        f"body_action_intensity_exceeds_show_ceiling:{step.action}:{step.intensity}>{ceiling}"
                    )
    if cue.cue_kind == PerformanceCueKind.BODY_STAGED_SEQUENCE:
        if not cue.staged_sequence:
            return ["body_staged_sequence_cue_requires_stages"]
        for stage in cue.staged_sequence:
            if stage.action:
                staged_actions.append((stage.action, stage.intensity))
            for accent in stage.accents:
                staged_actions.append((accent.action, accent.intensity))
        for action_name, intensity in staged_actions:
            descriptor = lookup_action_descriptor(action_name)
            if descriptor is None:
                issues.append(f"unsupported_body_action:{action_name}")
                continue
            if action_name not in LIVE_SAFE_ACTIONS:
                issues.append(f"body_action_not_in_public_live_safe_palette:{action_name}")
            if not descriptor.smoke_safe:
                issues.append(f"body_action_not_smoke_safe:{action_name}")
            if intensity is not None:
                ceiling = ACTION_INTENSITY_LIMITS.get(action_name, 0.70)
                if intensity > ceiling:
                    issues.append(
                        f"body_action_intensity_exceeds_show_ceiling:{action_name}:{intensity}>{ceiling}"
                    )
    if cue.cue_kind == PerformanceCueKind.BODY_EXPRESSIVE_MOTIF and cue.expressive_motif is not None:
        motif = resolve_expressive_motif(cue.expressive_motif.motif_name)
        if motif is None:
            return [f"unknown_expressive_motif:{cue.expressive_motif.motif_name}"]
        for step in motif.steps:
            if step.action_name is not None:
                motif_actions.append((step.action_name, step.intensity))
        for action_name, intensity in motif_actions:
            descriptor = lookup_action_descriptor(action_name)
            if descriptor is None:
                issues.append(f"unsupported_body_action:{action_name}")
                continue
            if action_name not in LIVE_SAFE_ACTIONS:
                issues.append(f"body_action_not_in_public_live_safe_palette:{action_name}")
            if not descriptor.smoke_safe:
                issues.append(f"body_action_not_smoke_safe:{action_name}")
            if intensity is not None:
                ceiling = ACTION_INTENSITY_LIMITS.get(action_name, 0.70)
                if intensity > ceiling:
                    issues.append(
                        f"body_action_intensity_exceeds_show_ceiling:{action_name}:{intensity}>{ceiling}"
                    )
    for beat in beats:
        descriptor = lookup_action_descriptor(beat.action)
        if descriptor is None:
            issues.append(f"unsupported_body_action:{beat.action}")
            continue
        if beat.action not in LIVE_SAFE_ACTIONS:
            issues.append(f"body_action_not_in_public_live_safe_palette:{beat.action}")
        if not descriptor.smoke_safe:
            issues.append(f"body_action_not_smoke_safe:{beat.action}")
        if beat.intensity is not None:
            ceiling = ACTION_INTENSITY_LIMITS.get(beat.action, 0.70)
            if beat.intensity > ceiling:
                issues.append(
                    f"body_action_intensity_exceeds_show_ceiling:{beat.action}:{beat.intensity}>{ceiling}"
                )
    return issues


def _validate_body_range_demo(cue: PerformanceCue) -> list[str]:
    if cue.cue_kind != PerformanceCueKind.BODY_RANGE_DEMO:
        return []
    preset_name = str(cue.payload.get("preset_name") or RANGE_DEMO_DEFAULT_PRESET)
    sequence_name = str(cue.payload.get("sequence_name") or "").strip()
    issues: list[str] = []
    if preset_name not in available_range_demo_presets():
        issues.append(f"unsupported_body_range_demo_preset:{cue.cue_id}:{preset_name}")
    if sequence_name and sequence_name not in available_range_demo_sequences():
        issues.append(f"unsupported_body_range_demo_sequence:{cue.cue_id}:{sequence_name}")
    return issues


def _playful_actions_in_cue(cue: PerformanceCue) -> set[str]:
    playful_actions = {"playful", "playful_peek_left", "playful_peek_right", "playful_react"}
    names = {beat.action for beat in cue.motion_track if beat.action in playful_actions}
    names.update(step.action for step in cue.primitive_sequence if step.action in playful_actions)
    names.update(stage.action for stage in cue.staged_sequence if stage.action in playful_actions and stage.action is not None)
    for stage in cue.staged_sequence:
        names.update(accent.action for accent in stage.accents if accent.action in playful_actions)
    if cue.cue_kind == PerformanceCueKind.BODY_EXPRESSIVE_MOTIF and cue.expressive_motif is not None:
        motif = resolve_expressive_motif(cue.expressive_motif.motif_name)
        if motif is not None:
            names.update(
                step.action_name
                for step in motif.steps
                if step.action_name in playful_actions
            )
    if cue.action in playful_actions:
        names.add(cue.action)
    return names


def _declared_coverage_groups(cue: PerformanceCue) -> set[str]:
    groups: set[str] = set()
    if cue.cue_kind == PerformanceCueKind.BODY_RANGE_DEMO:
        return set(ACTUATOR_GROUPS)
    if cue.cue_kind == PerformanceCueKind.BODY_PRIMITIVE_SEQUENCE:
        for step in cue.primitive_sequence:
            groups.update(_action_coverage_groups(step.action))
        return groups
    if cue.cue_kind == PerformanceCueKind.BODY_STAGED_SEQUENCE:
        for stage in cue.staged_sequence:
            if stage.action is not None:
                groups.update(_action_coverage_groups(stage.action))
            for accent in stage.accents:
                groups.update(_action_coverage_groups(accent.action))
        return groups
    if cue.cue_kind == PerformanceCueKind.BODY_EXPRESSIVE_MOTIF and cue.expressive_motif is not None:
        motif = resolve_expressive_motif(cue.expressive_motif.motif_name)
        if motif is None:
            return groups
        for step in motif.steps:
            if step.action_name is not None:
                groups.update(_action_coverage_groups(step.action_name))
        return groups
    beats = list(cue.motion_track)
    if cue.cue_kind == PerformanceCueKind.BODY_SEMANTIC_SMOKE and cue.action:
        beats.append(
            PerformanceMotionBeat(
                offset_ms=0,
                action=cue.action,
                intensity=cue.intensity,
                repeat_count=cue.repeat_count,
                note=cue.note,
            )
        )
    for beat in beats:
        groups.update(_action_coverage_groups(beat.action))
        groups.update(group for group in beat.coverage_tags if group in ACTUATOR_GROUPS)
    return groups


def _validate_motion_track_policy(cue: PerformanceCue) -> list[str]:
    issues: list[str] = []
    if cue.cue_kind == PerformanceCueKind.NARRATE:
        for beat in cue.motion_track:
            if beat.action in _NOD_FAMILY_ACTIONS:
                issues.append(f"narration_motion_track_nod_not_allowed:{cue.cue_id}:{beat.action}")

    indexed_beats = list(enumerate(cue.motion_track))
    for index, beat in indexed_beats:
        if beat.action not in {"look_far_up", "look_far_down"}:
            continue
        for other_index, other in indexed_beats:
            if other_index == index:
                continue
            if other.action not in _AGGRESSIVE_LID_ACTIONS:
                continue
            if abs(other.offset_ms - beat.offset_ms) <= 450:
                issues.append(
                    f"look_far_lid_combo_not_allowed:{cue.cue_id}:{beat.action}+{other.action}"
                )
    return issues


def _validate_staged_sequence_policy(cue: PerformanceCue) -> list[str]:
    if cue.cue_kind != PerformanceCueKind.BODY_STAGED_SEQUENCE:
        return []
    issues: list[str] = []
    if cue.motion_track:
        issues.append(f"body_staged_sequence_motion_track_not_allowed:{cue.cue_id}")
    if cue.action:
        issues.append(f"body_staged_sequence_legacy_action_not_allowed:{cue.cue_id}:{cue.action}")
    if cue.primitive_sequence:
        issues.append(f"body_staged_sequence_primitive_sequence_not_allowed:{cue.cue_id}")
    if len(cue.staged_sequence) != 3:
        issues.append(f"body_staged_sequence_requires_three_stages:{cue.cue_id}")
        return issues
    stage_kinds = [stage.stage_kind for stage in cue.staged_sequence]
    if stage_kinds != ["structural", "expressive", "return"]:
        issues.append(f"body_staged_sequence_requires_structural_expressive_return:{cue.cue_id}")
        return issues
    structural_stage, expressive_stage, return_stage = cue.staged_sequence
    if structural_stage.action is None:
        issues.append(f"body_staged_sequence_structural_action_missing:{cue.cue_id}")
    else:
        coverage = _action_coverage_groups(structural_stage.action)
        if coverage.difference({"head_yaw", "head_pitch_pair"}):
            issues.append(f"body_staged_sequence_structural_action_not_structural:{cue.cue_id}:{structural_stage.action}")
    for accent in expressive_stage.accents:
        coverage = _action_coverage_groups(accent.action)
        if coverage.intersection({"head_yaw", "head_pitch_pair"}):
            issues.append(f"body_staged_sequence_expressive_action_not_eye_area:{cue.cue_id}:{accent.action}")
    if return_stage.action is not None:
        issues.append(f"body_staged_sequence_return_action_not_allowed:{cue.cue_id}:{return_stage.action}")
    return issues


def _validate_expressive_motif_policy(cue: PerformanceCue) -> list[str]:
    if cue.cue_kind != PerformanceCueKind.BODY_EXPRESSIVE_MOTIF:
        return []
    issues: list[str] = []
    if cue.motion_track:
        issues.append(f"body_expressive_motif_motion_track_not_allowed:{cue.cue_id}")
    if cue.action:
        issues.append(f"body_expressive_motif_legacy_action_not_allowed:{cue.cue_id}:{cue.action}")
    if cue.primitive_sequence:
        issues.append(f"body_expressive_motif_primitive_sequence_not_allowed:{cue.cue_id}")
    if cue.staged_sequence:
        issues.append(f"body_expressive_motif_staged_sequence_not_allowed:{cue.cue_id}")
    if cue.expressive_motif is None:
        issues.append(f"body_expressive_motif_requires_motif:{cue.cue_id}")
        return issues
    motif = resolve_expressive_motif(cue.expressive_motif.motif_name)
    if motif is None:
        issues.append(f"body_expressive_motif_unknown:{cue.cue_id}:{cue.expressive_motif.motif_name}")
        return issues
    if not motif.steps:
        issues.append(f"body_expressive_motif_requires_steps:{cue.cue_id}")
        return issues
    if motif.steps[0].step_kind != "structural_set":
        issues.append(f"body_expressive_motif_requires_structural_open:{cue.cue_id}")
    if motif.steps[-1].step_kind != "return_to_neutral":
        issues.append(f"body_expressive_motif_requires_return_close:{cue.cue_id}")
    seen_structural = False
    return_index: int | None = None
    active_expressive = False
    for index, step in enumerate(motif.steps):
        if step.step_kind == "structural_set":
            if seen_structural:
                issues.append(f"body_expressive_motif_multiple_structural_steps:{cue.cue_id}")
            seen_structural = True
            if step.action_name is None:
                issues.append(f"body_expressive_motif_structural_action_missing:{cue.cue_id}")
            else:
                coverage = _action_coverage_groups(step.action_name)
                if coverage.difference({"head_yaw", "head_pitch_pair"}):
                    issues.append(
                        f"body_expressive_motif_structural_action_not_structural:{cue.cue_id}:{step.action_name}"
                    )
            if active_expressive:
                issues.append(f"body_expressive_motif_structural_change_after_expression:{cue.cue_id}")
        elif step.step_kind == "expressive_set":
            if step.action_name is None:
                issues.append(f"body_expressive_motif_expressive_action_missing:{cue.cue_id}")
            elif _action_coverage_groups(step.action_name).intersection({"head_yaw", "head_pitch_pair"}):
                issues.append(
                    f"body_expressive_motif_expressive_action_not_eye_area:{cue.cue_id}:{step.action_name}"
                )
            active_expressive = True
        elif step.step_kind == "expressive_release":
            active_expressive = True
        elif step.step_kind == "return_to_neutral":
            return_index = index
            if active_expressive:
                active_expressive = False
    if return_index is None:
        issues.append(f"body_expressive_motif_missing_return:{cue.cue_id}")
    return issues

def _validate_deterministic_template_policy(cue: PerformanceCue) -> list[str]:
    if cue.cue_kind not in {PerformanceCueKind.RUN_SCENE, PerformanceCueKind.SUBMIT_TEXT_TURN}:
        return []
    template_name = str(cue.payload.get("proof_template") or "").strip()
    if not template_name:
        return [f"proof_cue_missing_deterministic_template:{cue.cue_id}"]
    if cue.cue_kind == PerformanceCueKind.RUN_SCENE and template_name not in _SUPPORTED_DETERMINISTIC_SCENE_TEMPLATES:
        return [f"unsupported_deterministic_scene_template:{cue.cue_id}:{template_name}"]
    if cue.cue_kind == PerformanceCueKind.SUBMIT_TEXT_TURN and template_name not in _SUPPORTED_DETERMINISTIC_TURN_TEMPLATES:
        return [f"unsupported_deterministic_turn_template:{cue.cue_id}:{template_name}"]
    return []


def validate_show_definition(definition: PerformanceShowDefinition) -> None:
    errors: list[str] = []
    seen_segment_ids: set[str] = set()
    seen_cue_ids: set[str] = set()
    total_duration_seconds = _total_duration_seconds(definition)
    tuning_path = SHOW_TUNING_PATHS.get(definition.show_name)
    if definition.defaults.proof_backend_mode != PerformanceProofBackendMode.DETERMINISTIC_SHOW:
        errors.append("performance_show_requires_deterministic_default")
    if tuning_path is not None and not tuning_path.exists():
        errors.append(f"missing_show_tuning_path:{tuning_path}")

    for segment in definition.segments:
        if segment.segment_id in seen_segment_ids:
            errors.append(f"duplicate_segment_id:{segment.segment_id}")
        seen_segment_ids.add(segment.segment_id)
        segment_groups: set[str] = set()
        segment_expression_present = False
        for cue in segment.cues:
            if cue.cue_id in seen_cue_ids:
                errors.append(f"duplicate_cue_id:{cue.cue_id}")
            seen_cue_ids.add(cue.cue_id)
            if cue.cue_kind == PerformanceCueKind.RUN_SCENE and cue.scene_name not in _scene_catalog():
                errors.append(f"unknown_scene_name:{cue.scene_name}")
            errors.extend(_validate_motion_track_policy(cue))
            errors.extend(_validate_deterministic_template_policy(cue))
            errors.extend(_validate_body_range_demo(cue))
            errors.extend(_validate_staged_sequence_policy(cue))
            errors.extend(_validate_expressive_motif_policy(cue))
            if cue.cue_kind in {
                PerformanceCueKind.BODY_SEMANTIC_SMOKE,
                PerformanceCueKind.BODY_PRIMITIVE_SEQUENCE,
                PerformanceCueKind.BODY_STAGED_SEQUENCE,
                PerformanceCueKind.BODY_EXPRESSIVE_MOTIF,
            } or cue.motion_track:
                errors.extend(_validate_body_action(cue))
                segment_groups.update(_declared_coverage_groups(cue))
            elif cue.cue_kind == PerformanceCueKind.BODY_RANGE_DEMO:
                segment_groups.update(_declared_coverage_groups(cue))
            if segment.segment_id in {"operator_oversight", "honest_fallback_and_safe_idle"}:
                for action_name in sorted(_playful_actions_in_cue(cue)):
                    errors.append(f"{segment.segment_id}:{cue.cue_id}:playful_action_not_allowed:{action_name}")
            if cue.action:
                descriptor = lookup_action_descriptor(cue.action)
                segment_expression_present = segment_expression_present or (
                    descriptor is not None and descriptor.family == "expression"
                )
            for beat in cue.motion_track:
                descriptor = lookup_action_descriptor(beat.action)
                segment_expression_present = segment_expression_present or (
                    descriptor is not None and descriptor.family == "expression"
                )
        if segment_groups and not segment_groups.intersection({"head_yaw", "head_pitch_pair"}):
            errors.append(f"segment_missing_head_motion:{segment.segment_id}")
        if segment_groups and not segment_groups.intersection({"eye_yaw", "eye_pitch", "upper_lids", "lower_lids"}):
            errors.append(f"segment_missing_eye_or_lid_motion:{segment.segment_id}")
        if segment_groups and not (segment_groups.intersection({"brows"}) or segment_expression_present):
            errors.append(f"segment_missing_brow_or_expression_shift:{segment.segment_id}")

    if definition.show_name == "investor_expressive_motion_v8":
        if total_duration_seconds != 216:
            errors.append(f"motif_v8_show_requires_exact_duration:{total_duration_seconds}")
        if len(definition.segments) != 12:
            errors.append(f"motif_v8_show_requires_twelve_segments:{len(definition.segments)}")
        for segment in definition.segments:
            for cue in segment.cues:
                allowed_kinds = {
                    PerformanceCueKind.CAPTION,
                    PerformanceCueKind.BODY_EXPRESSIVE_MOTIF,
                    PerformanceCueKind.PAUSE,
                }
                if cue.cue_kind not in allowed_kinds:
                    errors.append(f"motif_v8_disallowed_cue_kind:{cue.cue_id}:{cue.cue_kind.value}")
                if cue.cue_kind == PerformanceCueKind.BODY_EXPRESSIVE_MOTIF:
                    if cue.expressive_motif is None:
                        errors.append(f"motif_v8_missing_motif:{cue.cue_id}")
                    else:
                        motif = resolve_expressive_motif(cue.expressive_motif.motif_name)
                        if motif is None:
                            errors.append(f"motif_v8_unknown_motif:{cue.cue_id}:{cue.expressive_motif.motif_name}")
                        else:
                            for step in motif.steps:
                                if step.action_name is not None and step.action_name.endswith("_fast"):
                                    errors.append(
                                        f"motif_v8_fast_action_not_allowed:{cue.cue_id}:{step.action_name}"
                                    )
                if cue.action:
                    errors.append(f"motif_v8_legacy_action_not_allowed:{cue.cue_id}:{cue.action}")
                if cue.motion_track:
                    errors.append(f"motif_v8_motion_track_not_allowed:{cue.cue_id}")
                if cue.primitive_sequence:
                    errors.append(f"staged_v8_primitive_sequence_not_allowed:{cue.cue_id}")

    if errors:
        raise ValueError(";".join(errors))


def _validate_language_coverage(definition: PerformanceShowDefinition, language: str | None) -> None:
    normalized = _normalized_language(language)
    if not normalized.startswith("zh"):
        return
    if definition.show_name not in SHOW_DEFINITION_PATHS:
        return
    missing: list[str] = []
    for _segment, cue in _narration_cues(definition):
        localized = cue.localized_text or {}
        if not any(candidate in localized for candidate in _language_candidates(language)):
            missing.append(cue.cue_id)
    if missing:
        raise ValueError(f"performance_show_missing_language_coverage:{normalized}:{','.join(missing)}")


def _scene_catalog() -> set[str]:
    from embodied_stack.demo.investor_scenes import INVESTOR_SCENES

    return set(INVESTOR_SCENES)


class PerformanceReportStore:
    RUN_SUMMARY_FILE = "run_summary.json"
    DIAGNOSTICS_MARKDOWN_FILE = "rehearsal_log.md"

    def __init__(self, report_dir: str | Path) -> None:
        self.report_dir = Path(report_dir)

    def save(
        self,
        run: PerformanceRunResult,
        *,
        show_definition: PerformanceShowDefinition,
        session_export: Any | None = None,
    ) -> PerformanceRunResult:
        self.report_dir.mkdir(parents=True, exist_ok=True)
        run_dir = self.report_dir / run.run_id
        run_dir.mkdir(parents=True, exist_ok=True)

        artifact_files = {
            "run_summary": str(run_dir / self.RUN_SUMMARY_FILE),
            "cue_results": str(run_dir / "cue_results.json"),
            "proof_results": str(run_dir / "proof_results.json"),
            "manifest": str(run_dir / "manifest.json"),
            "show_definition": str(run_dir / "show_definition.json"),
            "rehearsal_log": str(run_dir / self.DIAGNOSTICS_MARKDOWN_FILE),
        }
        if session_export is not None:
            artifact_files["session_export"] = str(run_dir / "session_export.json")

        run.artifact_dir = str(run_dir)
        run.artifact_files = artifact_files

        write_json_atomic(Path(artifact_files["run_summary"]), run)
        write_json_atomic(Path(artifact_files["cue_results"]), _flatten_cue_results(run))
        write_json_atomic(Path(artifact_files["proof_results"]), _proof_results(run))
        write_json_atomic(Path(artifact_files["show_definition"]), show_definition)
        if session_export is not None:
            write_json_atomic(Path(artifact_files["session_export"]), session_export)
        write_json_atomic(
            Path(artifact_files["manifest"]),
            {
                "run_id": run.run_id,
                "show_name": run.show_name,
                "version": run.version,
                "status": run.status.value,
                "session_id": run.session_id,
                "proof_backend_mode": run.proof_backend_mode.value if run.proof_backend_mode is not None else None,
                "language": run.language,
                "narration_voice_preset": run.narration_voice_preset,
                "narration_voice_name": run.narration_voice_name,
                "narration_voice_rate": run.narration_voice_rate,
                "selected_show_tuning_path": run.selected_show_tuning_path,
                "live_motion_arm_author": run.live_motion_arm_author,
                "live_motion_arm_port": run.live_motion_arm_port,
                "selected_segment_ids": list(run.selected_segment_ids),
                "selected_cue_ids": list(run.selected_cue_ids),
                "narration_only": run.narration_only,
                "proof_only": run.proof_only,
                "elapsed_seconds": run.elapsed_seconds,
                "timing_drift_seconds": run.timing_drift_seconds,
                "timing_breakdown_ms": dict(run.timing_breakdown_ms),
                "proof_check_count": run.proof_check_count,
                "failed_proof_check_count": run.failed_proof_check_count,
                "preview_only": run.preview_only,
                "last_body_projection_outcome": run.last_body_projection_outcome,
                "last_motion_outcome": run.last_motion_outcome.value if run.last_motion_outcome is not None else None,
                "last_motion_margin_record": (
                    run.last_motion_margin_record.model_dump(mode="json")
                    if run.last_motion_margin_record is not None
                    else None
                ),
                "actuator_coverage": run.actuator_coverage.model_dump(mode="json"),
                "min_margin_percent_by_group": dict(run.min_margin_percent_by_group),
                "max_margin_percent_by_group": dict(run.max_margin_percent_by_group),
                "worst_actuator_group": run.worst_actuator_group,
                "degraded_due_to_margin_only_cues": list(run.degraded_due_to_margin_only_cues),
                "eye_pitch_exercised_live": run.eye_pitch_exercised_live,
                "power_health_classification": run.power_health_classification,
                "preflight_passed": run.preflight_passed,
                "preflight_failure_reason": run.preflight_failure_reason,
                "idle_voltage_snapshot": dict(run.idle_voltage_snapshot),
                "artifact_files": artifact_files,
                "degraded": run.degraded,
                "degraded_cues": list(run.degraded_cues),
                "stop_requested": run.stop_requested,
                "updated_at": utc_now(),
            },
        )
        Path(artifact_files["rehearsal_log"]).write_text(
            self._diagnostics_markdown(run),
            encoding="utf-8",
        )
        return run.model_copy(deep=True)

    def get(self, run_id: str) -> PerformanceRunResult | None:
        path = self.report_dir / run_id / self.RUN_SUMMARY_FILE
        if not path.exists():
            return None
        return load_json_model_or_quarantine(path, PerformanceRunResult, quarantine_invalid=True)

    def _diagnostics_markdown(self, run: PerformanceRunResult) -> str:
        min_margins = ", ".join(f"{group}={value:.2f}%" for group, value in sorted(run.min_margin_percent_by_group.items()))
        max_margins = ", ".join(f"{group}={value:.2f}%" for group, value in sorted(run.max_margin_percent_by_group.items()))
        lines = [
            f"# Investor Show Rehearsal Log: {run.show_name}",
            "",
            f"- Run ID: `{run.run_id}`",
            f"- Status: `{run.status.value}`",
            f"- Show version: `{run.version}`",
            f"- Session ID: `{run.session_id}`",
            f"- Proof backend: `{run.proof_backend_mode.value if run.proof_backend_mode is not None else '-'}`",
            f"- Voice preset: `{run.narration_voice_preset or '-'}`",
            f"- Voice: `{run.narration_voice_name or '-'} @ {run.narration_voice_rate or '-'}`",
            f"- Selected tuning file: `{run.selected_show_tuning_path or '-'}`",
            f"- Arm path used: `{run.live_motion_arm_author or '-'}`",
            f"- Live port recorded in lease: `{run.live_motion_arm_port or '-'}`",
            f"- Last motion outcome: `{run.last_motion_outcome.value if run.last_motion_outcome is not None else '-'}`",
            f"- Power health: `{run.power_health_classification or '-'}`",
            f"- Preflight passed: `{run.preflight_passed if run.preflight_passed is not None else '-'}`",
            f"- Preflight reason: `{run.preflight_failure_reason or '-'}`",
            f"- Worst actuator group: `{run.worst_actuator_group or '-'}`",
            f"- Eye pitch exercised live: `{run.eye_pitch_exercised_live}`",
            f"- Margin-only degraded cues: `{','.join(run.degraded_due_to_margin_only_cues) or '-'}`",
            f"- Min margin by group: {min_margins or '-'}",
            f"- Max margin by group: {max_margins or '-'}",
            f"- Go / no-go verdict: `{'go' if run.status == DemoRunStatus.COMPLETED and not run.degraded else 'no_go'}`",
            "",
            "## Notes",
            "",
        ]
        if run.notes:
            lines.extend([f"- {note}" for note in run.notes])
        else:
            lines.append("- none")
        lines.append("")
        return "\n".join(lines)


class PerformanceShowRunner:
    def __init__(
        self,
        *,
        operator_console: "OperatorConsoleService",
        report_store: PerformanceReportStore,
        status_callback: Callable[[PerformanceRunResult], None] | None = None,
        cancel_checker: Callable[[], bool] | None = None,
    ) -> None:
        self.operator_console = operator_console
        self.report_store = report_store
        self.status_callback = status_callback
        self.cancel_checker = cancel_checker

    def _resolved_language(
        self,
        *,
        definition: PerformanceShowDefinition,
        request: PerformanceRunRequest,
    ) -> str:
        return request.language or definition.defaults.language or "en"

    def _resolved_proof_backend_mode(
        self,
        *,
        definition: PerformanceShowDefinition,
        request: PerformanceRunRequest,
    ) -> PerformanceProofBackendMode:
        return request.proof_backend_mode or definition.defaults.proof_backend_mode

    def _resolved_narration_config(
        self,
        *,
        definition: PerformanceShowDefinition,
        request: PerformanceRunRequest,
        cue: PerformanceCue | None = None,
    ) -> ResolvedNarrationConfig:
        language = self._resolved_language(definition=definition, request=request)
        voice_mode = self._resolved_narration_voice_mode(definition=definition, request=request, cue=cue)
        preset_name = request.narration_voice_preset or definition.defaults.narration_voice_preset
        if not preset_name:
            preset_name = _voice_preset_for_language(language)
        preset = VOICE_PRESETS.get(preset_name, VOICE_PRESETS["english_cute_character"])
        voice_name = request.narration_voice_name or definition.defaults.narration_voice_name or str(preset["voice_name"])
        voice_rate = request.narration_voice_rate or definition.defaults.narration_voice_rate or int(preset["rate"])
        notes: list[str] = []
        if voice_mode in MACOS_SAY_VOICE_MODES:
            available_voices = set(_macos_voice_names())
            if available_voices and voice_name not in available_voices:
                fallback_voice = str(preset["voice_name"])
                if fallback_voice in available_voices:
                    notes.append(f"voice_fallback:{voice_name}->{fallback_voice}")
                    voice_name = fallback_voice
                else:
                    raise ValueError(f"performance_voice_unavailable:{voice_name}")
        return ResolvedNarrationConfig(
            language=language,
            voice_mode=voice_mode,
            voice_preset=preset_name,
            voice_name=voice_name,
            voice_rate=voice_rate,
            notes=tuple(notes),
        )

    def _cue_text(
        self,
        cue: PerformanceCue,
        *,
        definition: PerformanceShowDefinition,
        request: PerformanceRunRequest,
    ) -> str | None:
        return _localized_value(
            cue.text,
            cue.localized_text,
            self._resolved_language(definition=definition, request=request),
        )

    def _cue_fallback_text(
        self,
        cue: PerformanceCue,
        *,
        definition: PerformanceShowDefinition,
        request: PerformanceRunRequest,
    ) -> str | None:
        return _localized_value(
            cue.fallback_text,
            cue.localized_fallback_text,
            self._resolved_language(definition=definition, request=request),
        )

    def _timing_add(self, run: PerformanceRunResult, key: str, duration_ms: float | int | None) -> None:
        if duration_ms is None:
            return
        run.timing_breakdown_ms[key] = round(run.timing_breakdown_ms.get(key, 0.0) + float(duration_ms), 2)

    def run(
        self,
        definition: PerformanceShowDefinition,
        request: PerformanceRunRequest | None = None,
        *,
        run_id: str | None = None,
    ) -> PerformanceRunResult:
        request = request or PerformanceRunRequest()
        if request.narration_only and request.proof_only:
            raise ValueError("performance_run_request_conflicting_modes")
        resolved_definition = select_show_definition(definition, request)
        resolved_session_id = request.session_id or resolved_definition.session_id
        narration_config = self._resolved_narration_config(definition=resolved_definition, request=request)
        _validate_language_coverage(resolved_definition, narration_config.language)
        proof_backend_mode = self._resolved_proof_backend_mode(definition=resolved_definition, request=request)
        arm_author, arm_port = _current_arm_lease_metadata()
        run = PerformanceRunResult(
            run_id=run_id or f"performance-{uuid4().hex[:12]}",
            show_name=resolved_definition.show_name,
            version=resolved_definition.version,
            session_id=resolved_session_id,
            proof_backend_mode=proof_backend_mode,
            language=narration_config.language,
            narration_voice_preset=narration_config.voice_preset,
            narration_voice_name=narration_config.voice_name,
            narration_voice_rate=narration_config.voice_rate,
            selected_show_tuning_path=str(SHOW_TUNING_PATHS.get(resolved_definition.show_name) or ""),
            live_motion_arm_author=arm_author,
            live_motion_arm_port=arm_port,
            selected_segment_ids=[segment.segment_id for segment in resolved_definition.segments],
            selected_cue_ids=[cue.cue_id for segment in resolved_definition.segments for cue in segment.cues],
            narration_only=request.narration_only,
            proof_only=request.proof_only,
            target_total_duration_seconds=_total_duration_seconds(resolved_definition),
            segment_results=[
                PerformanceSegmentResult(
                    segment_id=segment.segment_id,
                    title=segment.title,
                    investor_claim=segment.investor_claim,
                    target_start_seconds=segment.target_start_seconds,
                    target_duration_seconds=segment.target_duration_seconds,
                )
                for segment in resolved_definition.segments
            ],
            timing_breakdown_ms={
                "narration": 0.0,
                "proof": 0.0,
                "motion_track": 0.0,
                "idle": 0.0,
                "body_motion": 0.0,
                "proof_backend_latency": 0.0,
            },
        )
        if not run.selected_show_tuning_path:
            run.selected_show_tuning_path = None
        if narration_config.notes:
            run.notes.extend(narration_config.notes)
        session_export: Any | None = None
        run_started = perf_counter()
        self._prepare_runtime(request=request)
        self._ensure_show_session(definition=resolved_definition, request=request, session_id=resolved_session_id)
        if self._requires_live_power_preflight(definition=resolved_definition, request=request):
            self._run_live_power_preflight(
                run=run,
                definition=resolved_definition,
                session_export=session_export,
            )
        if self._requires_preshow_body_neutral(request=request):
            self._run_preshow_body_neutral(
                run=run,
                definition=resolved_definition,
                session_export=session_export,
            )
        self._persist(run, definition=resolved_definition, session_export=session_export)
        try:
            for segment, segment_result in zip(resolved_definition.segments, run.segment_results, strict=True):
                self._check_cancelled()
                segment_started = perf_counter()
                self._start_segment(
                    run,
                    segment,
                    segment_result,
                    definition=resolved_definition,
                    session_export=session_export,
                )
                for cue in segment.cues:
                    self._check_cancelled()
                    cue_result = self._execute_cue(
                        run=run,
                        definition=resolved_definition,
                        request=request,
                        segment=segment,
                        cue=cue,
                    )
                    segment_result.cue_results.append(cue_result)
                    if cue_result.payload.get("session_export") is not None:
                        session_export = cue_result.payload["session_export"]
                    self._update_rollups(run, segment_result=segment_result)
                    self._persist(run, definition=resolved_definition, session_export=session_export)
                    if not cue_result.success and not self._continue_on_error(
                        cue=cue,
                        definition=resolved_definition,
                        request=request,
                    ):
                        raise RuntimeError(f"performance_cue_failed:{cue.cue_id}")
                segment_result.actual_duration_ms = round((perf_counter() - segment_started) * 1000.0, 2)
                segment_result.timing_drift_ms = round(
                    segment_result.actual_duration_ms - float(segment.target_duration_seconds * 1000),
                    2,
                )
                segment_result.status = "degraded" if segment_result.degraded else ("completed" if segment_result.success else "failed")
                segment_result.completed_at = utc_now()
                self._update_rollups(run, segment_result=segment_result)
                self._persist(run, definition=resolved_definition, session_export=session_export)
            run.status = DemoRunStatus.COMPLETED
            run.completed_at = utc_now()
            run.degraded = bool(run.degraded_cues)
            if session_export is not None:
                run.episode_id = getattr(session_export, "episode_id", None)
            self._finalize_run_timing(run, run_started=run_started)
            self._persist(run, definition=resolved_definition, session_export=session_export)
            return run
        except PerformanceShowCancelled as exc:
            run.status = DemoRunStatus.CANCELLED
            run.completed_at = utc_now()
            run.degraded = True
            run.stop_requested = True
            run.notes.append(str(exc))
            if session_export is not None:
                run.episode_id = getattr(session_export, "episode_id", None)
            self._finalize_run_timing(run, run_started=run_started)
            self._persist(run, definition=resolved_definition, session_export=session_export)
            return run
        except Exception as exc:
            run.status = DemoRunStatus.FAILED
            run.completed_at = utc_now()
            run.degraded = True
            run.notes.append(str(exc))
            if session_export is not None:
                run.episode_id = getattr(session_export, "episode_id", None)
            self._finalize_run_timing(run, run_started=run_started)
            self._persist(run, definition=resolved_definition, session_export=session_export)
            return run

    def _persist(
        self,
        run: PerformanceRunResult,
        *,
        definition: PerformanceShowDefinition,
        session_export: Any | None,
    ) -> None:
        saved = self.report_store.save(run, show_definition=definition, session_export=session_export)
        if self.status_callback is not None:
            self.status_callback(saved)

    def _prepare_runtime(self, *, request: PerformanceRunRequest) -> None:
        if request.reset_runtime:
            self.operator_console.orchestrator.reset_runtime(clear_user_memory=True)

    def _requires_live_power_preflight(
        self,
        *,
        definition: PerformanceShowDefinition,
        request: PerformanceRunRequest,
    ) -> bool:
        if definition.show_name not in SHOW_TUNING_PATHS:
            return False
        if request.narration_only:
            return False
        body_state = self._body_state_payload(force_refresh=True)
        transport_mode = str(body_state.get("transport_mode") or "")
        return transport_mode == "live_serial"

    def _run_live_power_preflight(
        self,
        *,
        run: PerformanceRunResult,
        definition: PerformanceShowDefinition,
        session_export: Any | None,
    ) -> None:
        result = self.operator_console.run_body_power_preflight()
        payload = result.payload if isinstance(result.payload, dict) else {}
        run.power_health_classification = str(payload.get("power_health_classification") or "") or None
        run.preflight_passed = bool(payload.get("preflight_passed")) if payload.get("preflight_passed") is not None else False
        run.preflight_failure_reason = str(payload.get("preflight_failure_reason") or result.detail or "") or None
        run.idle_voltage_snapshot = {
            str(joint_name): dict(snapshot)
            for joint_name, snapshot in (payload.get("idle_voltage_snapshot") or {}).items()
            if isinstance(snapshot, dict)
        }
        if run.preflight_passed is False:
            note = f"body_preflight_warning:{run.preflight_failure_reason or run.power_health_classification or 'unknown'}"
            if note not in run.notes:
                run.notes.append(note)
        self._persist(run, definition=definition, session_export=session_export)

    def _requires_preshow_body_neutral(
        self,
        *,
        request: PerformanceRunRequest,
    ) -> bool:
        if request.narration_only:
            return False
        body_state = self._body_state_payload(force_refresh=True)
        return str(body_state.get("transport_mode") or "") == "live_serial"

    def _run_preshow_body_neutral(
        self,
        *,
        run: PerformanceRunResult,
        definition: PerformanceShowDefinition,
        session_export: Any | None,
    ) -> None:
        started = perf_counter()
        result = self.operator_console.write_body_neutral()
        self._timing_add(run, "body_motion", (perf_counter() - started) * 1000.0)
        detail = str(result.detail or "") or None
        if result.ok and result.status == "ok":
            note = "body_preshow_neutral:ok"
            if note not in run.notes:
                run.notes.append(note)
            sleep(BODY_SETTLE_SECONDS)
            self._timing_add(run, "idle", BODY_SETTLE_SECONDS * 1000.0)
        else:
            note = f"body_preshow_neutral_warning:{result.status}:{detail or 'unknown'}"
            if note not in run.notes:
                run.notes.append(note)
        self._persist(run, definition=definition, session_export=session_export)

    def _ensure_show_session(
        self,
        *,
        definition: PerformanceShowDefinition,
        request: PerformanceRunRequest,
        session_id: str,
    ) -> None:
        orchestrator = self.operator_console.orchestrator
        session = orchestrator.get_session(session_id)
        resolved_response_mode = request.response_mode or definition.defaults.response_mode
        if session is None:
            orchestrator.create_session(
                orchestrator.build_session_request(
                    session_id=session_id,
                    channel="speech",
                    scenario_name=definition.show_name,
                    response_mode=resolved_response_mode,
                )
            )
            return
        if session.scenario_name != definition.show_name:
            session.scenario_name = definition.show_name
        if session.response_mode != resolved_response_mode:
            session.response_mode = resolved_response_mode
        persisted = orchestrator.memory.upsert_session(session)
        orchestrator.state_projection.refresh_world_state(session=persisted)

    def _check_cancelled(self) -> None:
        if self.cancel_checker is not None and self.cancel_checker():
            raise PerformanceShowCancelled("performance_show_cancelled")

    def _finalize_run_timing(self, run: PerformanceRunResult, *, run_started: float) -> None:
        run.elapsed_seconds = round(max(0.0, perf_counter() - run_started), 2)
        if run.target_total_duration_seconds:
            run.timing_drift_seconds = round(run.elapsed_seconds - float(run.target_total_duration_seconds), 2)

    def _update_rollups(
        self,
        run: PerformanceRunResult,
        *,
        segment_result: PerformanceSegmentResult | None = None,
    ) -> None:
        if segment_result is not None:
            segment_result.degraded = any(item.degraded for item in segment_result.cue_results)
            segment_result.success = all(item.success for item in segment_result.cue_results) if segment_result.cue_results else True
            segment_result.proof_check_count = sum(len(item.proof_checks) for item in segment_result.cue_results)
            segment_result.failed_proof_check_count = sum(
                1
                for item in segment_result.cue_results
                for criterion in item.proof_checks
                if not criterion.passed
            )
            for cue_result in segment_result.cue_results:
                if cue_result.degraded and cue_result.cue_id not in run.degraded_cues:
                    run.degraded_cues.append(cue_result.cue_id)
                projection_outcome = cue_result.payload.get("body_projection_outcome")
                if isinstance(projection_outcome, str) and projection_outcome:
                    run.last_body_projection_outcome = projection_outcome
                if cue_result.motion_outcome is not None:
                    run.last_motion_outcome = cue_result.motion_outcome
                    run.last_body_projection_outcome = cue_result.motion_outcome.value
                if cue_result.motion_margin_record is not None:
                    run.last_motion_margin_record = cue_result.motion_margin_record.model_copy(deep=True)
                    if cue_result.motion_margin_record.power_health_classification:
                        run.power_health_classification = cue_result.motion_margin_record.power_health_classification
                    run.min_margin_percent_by_group = _merge_min_margins(
                        run.min_margin_percent_by_group,
                        cue_result.motion_margin_record.min_remaining_margin_percent_by_group,
                    )
                    run.max_margin_percent_by_group = _merge_max_margins(
                        run.max_margin_percent_by_group,
                        cue_result.motion_margin_record.max_remaining_margin_percent_by_group,
                    )
                    run.worst_actuator_group = _worst_actuator_group(run.min_margin_percent_by_group)
                    if cue_result.motion_margin_record.fault_classification:
                        run.last_body_issue_classification = cue_result.motion_margin_record.fault_classification
                        run.last_body_issue_confirmation_result = cue_result.motion_margin_record.confirmation_result
                        if run.body_fault_trigger_cue_id is None:
                            run.body_fault_trigger_cue_id = cue_result.cue_id
                            run.body_fault_detail = (
                                cue_result.motion_margin_record.confirmation_result
                                or cue_result.motion_margin_record.detail
                            )
                segment_result.actuator_coverage = _merge_coverage(segment_result.actuator_coverage, cue_result.actuator_coverage)
                run.actuator_coverage = _merge_coverage(run.actuator_coverage, cue_result.actuator_coverage)
                if cue_result.actuator_coverage.eye_pitch and cue_result.motion_outcome == PerformanceMotionOutcome.LIVE_APPLIED:
                    run.eye_pitch_exercised_live = True
                if bool(cue_result.payload.get("preview_only")):
                    run.preview_only = True
                margin_only_degraded = (
                    cue_result.degraded
                    and cue_result.motion_margin_record is not None
                    and not cue_result.motion_margin_record.safety_gate_passed
                    and all(item.passed for item in cue_result.proof_checks)
                    and cue_result.note is None
                )
                if margin_only_degraded and cue_result.cue_id not in run.degraded_due_to_margin_only_cues:
                    run.degraded_due_to_margin_only_cues.append(cue_result.cue_id)

        run.proof_check_count = sum(
            len(cue_result.proof_checks)
            for segment in run.segment_results
            for cue_result in segment.cue_results
        )
        run.failed_proof_check_count = sum(
            1
            for segment in run.segment_results
            for cue_result in segment.cue_results
            for criterion in cue_result.proof_checks
            if not criterion.passed
        )
        run.completed_segment_count = sum(
            1 for segment in run.segment_results if segment.status in {"completed", "degraded", "failed"}
        )

    def _start_segment(
        self,
        run: PerformanceRunResult,
        segment: PerformanceSegment,
        segment_result: PerformanceSegmentResult,
        *,
        definition: PerformanceShowDefinition,
        session_export: Any | None,
    ) -> None:
        segment_result.status = "running"
        segment_result.started_at = utc_now()
        run.current_segment_id = segment.segment_id
        run.current_segment_title = segment.title
        run.current_investor_claim = segment.investor_claim
        run.current_cue_id = None
        run.current_prompt = None
        run.current_caption = None
        run.current_narration = None
        self._persist(run, definition=definition, session_export=session_export)

    def _execute_cue(
        self,
        *,
        run: PerformanceRunResult,
        definition: PerformanceShowDefinition,
        request: PerformanceRunRequest,
        segment: PerformanceSegment,
        cue: PerformanceCue,
    ) -> PerformanceCueResult:
        cue_started = perf_counter()
        cue_result = PerformanceCueResult(
            cue_id=cue.cue_id,
            cue_kind=cue.cue_kind,
            label=cue.label,
            status="running",
            target_duration_ms=cue.target_duration_ms,
            started_at=utc_now(),
        )
        run.current_cue_id = cue.cue_id
        try:
            payload = self._run_cue(
                run=run,
                definition=definition,
                request=request,
                segment=segment,
                cue=cue,
            )
            cue_result.payload = payload
            motion_outcome = payload.get("motion_outcome")
            if motion_outcome:
                cue_result.motion_outcome = PerformanceMotionOutcome(str(motion_outcome))
            motion_margin_record = payload.get("motion_margin_record")
            if isinstance(motion_margin_record, dict) and motion_margin_record:
                cue_result.motion_margin_record = PerformanceMotionMarginRecord.model_validate(motion_margin_record)
                if cue_result.motion_margin_record.power_health_classification:
                    run.power_health_classification = cue_result.motion_margin_record.power_health_classification
                if cue_result.motion_margin_record.fault_classification:
                    run.last_body_issue_classification = cue_result.motion_margin_record.fault_classification
                    run.last_body_issue_confirmation_result = cue_result.motion_margin_record.confirmation_result
                if cue_result.motion_margin_record.fault_classification and run.body_fault_trigger_cue_id is None:
                    run.body_fault_trigger_cue_id = cue.cue_id
                    run.body_fault_detail = (
                        cue_result.motion_margin_record.confirmation_result
                        or cue_result.motion_margin_record.detail
                    )
            actuator_coverage = payload.get("actuator_coverage")
            if isinstance(actuator_coverage, dict) and actuator_coverage:
                cue_result.actuator_coverage = PerformanceActuatorCoverageSummary.model_validate(actuator_coverage)
            cue_result.proof_checks = self._proof_checks(cue=cue, payload=payload)
            if cue.cue_id in request.force_degraded_cue_ids:
                cue_result.note = f"forced_degraded_rehearsal:{cue.cue_id}"
                cue_result.payload["degraded"] = True
                cue_result.payload["forced_degraded_rehearsal"] = True
            cue_result.degraded = (
                bool(payload.get("degraded"))
                or any(not item.passed for item in cue_result.proof_checks)
                or (
                    cue_result.motion_margin_record is not None
                    and not cue_result.motion_margin_record.safety_gate_passed
                )
            )
            cue_result.success = not cue_result.degraded or self._continue_on_error(cue=cue, definition=definition, request=request)
            cue_result.status = "degraded" if cue_result.degraded else "completed"
            fallback_text = self._cue_fallback_text(cue, definition=definition, request=request)
            if cue_result.degraded and fallback_text and self._continue_on_error(cue=cue, definition=definition, request=request):
                fallback_payload = self._perform_narration(
                    run=run,
                    text=fallback_text,
                    narration=self._resolved_narration_config(definition=definition, request=request),
                    motion_track=[],
                    target_duration_ms=cue.target_duration_ms,
                    enabled=request.narration_enabled,
                )
                cue_result.fallback_used = True
                cue_result.payload["fallback_narration"] = fallback_payload
                cue_result.note = fallback_text
            if self._should_schedule_body_settle(cue=cue, cue_result=cue_result):
                run.pending_body_settle_reason = cue.cue_kind.value
        except PerformanceShowCancelled:
            raise
        except Exception as exc:
            cue_result.success = self._continue_on_error(cue=cue, definition=definition, request=request)
            cue_result.degraded = True
            cue_result.status = "degraded" if cue_result.success else "failed"
            cue_result.note = str(exc)
        cue_result.completed_at = utc_now()
        cue_result.actual_duration_ms = round((perf_counter() - cue_started) * 1000.0, 2)
        if cue_result.target_duration_ms is not None:
            cue_result.timing_drift_ms = round(cue_result.actual_duration_ms - float(cue_result.target_duration_ms), 2)
        self._record_timing_breakdown(run, cue=cue, cue_result=cue_result)
        return cue_result

    def _body_state_payload(self, *, force_refresh: bool = False) -> dict[str, Any]:
        edge_gateway = getattr(self.operator_console, "edge_gateway", None)
        if edge_gateway is None:
            return {}
        body_state = None
        if force_refresh:
            runtime = getattr(edge_gateway, "runtime", None)
            body_driver = getattr(runtime, "body_driver", None)
            if body_driver is not None and hasattr(body_driver, "refresh_live_status"):
                try:
                    body_state = body_driver.refresh_live_status(force=True)
                except Exception:
                    body_state = None
        if body_state is None:
            telemetry = edge_gateway.get_telemetry()
            body_state = telemetry.body_state
        return body_state.model_dump(mode="json") if body_state is not None else {}

    def _synthetic_preview_motion_result(
        self,
        *,
        action: str,
        coverage_tags: list[str],
        detail: str,
        body_state: dict[str, Any] | None = None,
        fault_classification: str | None = None,
        power_health_classification: str | None = None,
        confirmation_result: str | None = None,
        preflight_passed: bool | None = None,
        preflight_failure_reason: str | None = None,
    ) -> dict[str, Any]:
        state_payload = body_state or self._body_state_payload(force_refresh=False)
        actuator_coverage = _coverage_from_groups(
            set(EXPLICIT_ACTION_COVERAGE.get(action, set())).union(
                {group for group in coverage_tags if group in ACTUATOR_GROUPS}
            )
        )
        margin_record = PerformanceMotionMarginRecord(
            action=action,
            outcome=PerformanceMotionOutcome.PREVIEW_ONLY,
            safety_gate_passed=False,
            peak_calibrated_target={},
            latest_readback={},
            min_remaining_margin_percent_by_joint={},
            min_remaining_margin_percent_by_group={},
            max_remaining_margin_percent_by_group={},
            threshold_percent_by_group=_margin_thresholds_for_action(action=action, narration_linked=True),
            health_flags=[detail],
            fault_classification=fault_classification,
            power_health_classification=power_health_classification,
            confirmation_result=confirmation_result,
            preflight_passed=preflight_passed,
            preflight_failure_reason=preflight_failure_reason,
            detail=detail,
            transport_mode=str(state_payload.get("transport_mode") or "") or None,
            transport_confirmed_live=state_payload.get("transport_confirmed_live"),
            live_readback_checked=False,
        )
        return {
            "action": action,
            "success": True,
            "status": "preview_only",
            "detail": detail,
            "preview_only": True,
            "body_projection_outcome": PerformanceMotionOutcome.PREVIEW_ONLY.value,
            "motion_outcome": PerformanceMotionOutcome.PREVIEW_ONLY.value,
            "motion_margin_record": margin_record.model_dump(mode="json"),
            "actuator_coverage": actuator_coverage.model_dump(mode="json"),
            "degraded": True,
            "raw_result": {
                "reason": detail,
                "fault_classification": fault_classification,
                "power_health_classification": power_health_classification,
                "confirmation_result": confirmation_result,
                "preflight_passed": preflight_passed,
                "preflight_failure_reason": preflight_failure_reason,
            },
        }

    def _should_schedule_body_settle(
        self,
        *,
        cue: PerformanceCue,
        cue_result: PerformanceCueResult,
    ) -> bool:
        if cue.cue_kind not in {
            PerformanceCueKind.BODY_SAFE_IDLE,
            PerformanceCueKind.BODY_SEMANTIC_SMOKE,
            PerformanceCueKind.BODY_STAGED_SEQUENCE,
            PerformanceCueKind.BODY_EXPRESSIVE_MOTIF,
            PerformanceCueKind.BODY_RANGE_DEMO,
        }:
            return False
        if cue_result.motion_outcome is not None:
            return cue_result.motion_outcome == PerformanceMotionOutcome.LIVE_APPLIED
        projection_outcome = str(cue_result.payload.get("body_projection_outcome") or "")
        return projection_outcome == PerformanceMotionOutcome.LIVE_APPLIED.value

    def _body_state_suspicious_for_settle(self, body_state: dict[str, Any]) -> str | None:
        audit = body_state.get("latest_command_audit") or {}
        if isinstance(audit, dict):
            classification = str(audit.get("fault_classification") or "")
            if classification == "confirmed_power_fault":
                return "settle_check_confirmed_power_fault"
            if classification in {"suspect_voltage_event", "readback_implausible"}:
                return f"settle_check_{classification}"
        servo_health = body_state.get("servo_health") or {}
        voltage_joints = []
        for joint_name, payload in servo_health.items():
            if not isinstance(payload, dict):
                continue
            error_bits = [str(item) for item in payload.get("error_bits") or []]
            if "input_voltage" in error_bits:
                voltage_joints.append(str(joint_name))
        if len(voltage_joints) >= 4:
            return "settle_check_suspect_voltage_event"
        return None

    def _run_cue(
        self,
        *,
        run: PerformanceRunResult,
        definition: PerformanceShowDefinition,
        request: PerformanceRunRequest,
        segment: PerformanceSegment,
        cue: PerformanceCue,
    ) -> dict[str, Any]:
        self._check_cancelled()
        resolved_session_id = cue.session_id or run.session_id
        resolved_response_mode = cue.response_mode or request.response_mode or definition.defaults.response_mode
        proof_voice_mode = cue.voice_mode or request.proof_voice_mode or definition.defaults.proof_voice_mode
        proof_backend_mode = self._resolved_proof_backend_mode(definition=definition, request=request)
        cue_text = self._cue_text(cue, definition=definition, request=request)

        match cue.cue_kind:
            case PerformanceCueKind.PROMPT:
                run.current_prompt = cue_text
                return {"prompt": cue_text, "segment_title": segment.title}
            case PerformanceCueKind.CAPTION:
                run.current_caption = cue_text
                return {"caption": cue_text, "segment_title": segment.title}
            case PerformanceCueKind.NARRATE:
                return self._perform_narration(
                    run=run,
                    text=cue_text or "",
                    narration=self._resolved_narration_config(definition=definition, request=request, cue=cue),
                    motion_track=cue.motion_track,
                    target_duration_ms=cue.target_duration_ms,
                    enabled=request.narration_enabled,
                )
            case PerformanceCueKind.RUN_SCENE:
                if proof_backend_mode == PerformanceProofBackendMode.DETERMINISTIC_SHOW:
                    template_name = str(cue.payload.get("proof_template") or "")
                    if template_name:
                        return self._run_deterministic_scene_proof(
                            run=run,
                            definition=definition,
                            request=request,
                            cue=cue,
                            session_id=resolved_session_id,
                            template_name=template_name,
                        )
                return self._run_live_scene_proof(
                    cue=cue,
                    session_id=resolved_session_id,
                    response_mode=resolved_response_mode,
                    voice_mode=proof_voice_mode,
                )
            case PerformanceCueKind.SUBMIT_TEXT_TURN:
                if proof_backend_mode == PerformanceProofBackendMode.DETERMINISTIC_SHOW:
                    template_name = str(cue.payload.get("proof_template") or "")
                    if template_name:
                        return self._run_deterministic_turn_proof(
                            run=run,
                            definition=definition,
                            request=request,
                            cue=cue,
                            session_id=resolved_session_id,
                            prompt_text=cue_text or "",
                            template_name=template_name,
                        )
                return self._run_live_text_turn_proof(
                    cue=cue,
                    session_id=resolved_session_id,
                    response_mode=resolved_response_mode,
                    voice_mode=proof_voice_mode,
                    input_text=cue_text or "",
                )
            case PerformanceCueKind.INJECT_EVENT:
                interaction = self.operator_console.inject_event(
                    SimulatedSensorEventRequest(
                        event_type=cue.event_type or "heartbeat",
                        payload=dict(cue.payload),
                        session_id=resolved_session_id,
                        source="performance_show",
                    )
                )
                payload = self._interaction_payload(interaction)
                payload["proof_backend_latency_ms"] = 0.0
                return payload
            case PerformanceCueKind.PERCEPTION_FIXTURE:
                fixture_path = _resolve_show_path(cue.fixture_path or "")
                replay = self.operator_console.replay_perception_fixture(
                    PerceptionReplayRequest(
                        session_id=resolved_session_id,
                        fixture_path=fixture_path,
                        source="performance_show",
                        publish_events=cue.publish_events,
                    )
                )
                return {
                    "fixture_path": replay.fixture_path,
                    "resolved_fixture_path": fixture_path,
                    "snapshot_count": len(replay.snapshots),
                    "success": replay.success,
                    "degraded": not replay.success,
                    "proof_backend_latency_ms": 0.0,
                    "raw_result": replay.model_dump(mode="json"),
                }
            case PerformanceCueKind.PERCEPTION_SNAPSHOT:
                result = self.operator_console.submit_perception_snapshot(
                    PerceptionSnapshotSubmitRequest(
                        session_id=resolved_session_id,
                        provider_mode=cue.perception_mode,
                        source="performance_show",
                        annotations=list(cue.annotations),
                        metadata=dict(cue.payload),
                        trigger_reason=cue.note,
                        publish_events=cue.publish_events,
                    )
                )
                return {
                    "provider_mode": result.snapshot.provider_mode.value,
                    "success": result.success,
                    "degraded": not result.success,
                    "proof_backend_latency_ms": 0.0,
                    "raw_result": result.model_dump(mode="json"),
                }
            case PerformanceCueKind.BODY_SEMANTIC_SMOKE:
                return self._run_body_motion_beat(
                    PerformanceMotionBeat(
                        offset_ms=0,
                        action=cue.action or "look_forward",
                        intensity=cue.intensity,
                        repeat_count=cue.repeat_count,
                        note=cue.note,
                    )
                )
            case PerformanceCueKind.BODY_PRIMITIVE_SEQUENCE:
                return self._run_body_primitive_sequence_cue(cue)
            case PerformanceCueKind.BODY_STAGED_SEQUENCE:
                return self._run_body_staged_sequence_cue(cue)
            case PerformanceCueKind.BODY_EXPRESSIVE_MOTIF:
                return self._run_body_expressive_motif_cue(cue)
            case PerformanceCueKind.BODY_RANGE_DEMO:
                return self._run_body_range_demo_cue(cue)
            case PerformanceCueKind.BODY_WRITE_NEUTRAL:
                result = self.operator_console.write_body_neutral()
                return {
                    "status": result.status,
                    "detail": result.detail,
                    "success": result.ok and result.status == "ok",
                    "degraded": result.status != "ok",
                    "raw_result": result.model_dump(mode="json"),
                }
            case PerformanceCueKind.BODY_SAFE_IDLE:
                interaction = self.operator_console.force_safe_idle(
                    session_id=resolved_session_id,
                    reason=cue.note or "performance_show_safe_idle",
                )
                return self._interaction_payload(interaction)
            case PerformanceCueKind.PAUSE:
                duration_seconds = max(0.0, float(cue.target_duration_ms or 0) / 1000.0)
                if duration_seconds > 0:
                    deadline = perf_counter() + duration_seconds
                    while perf_counter() < deadline:
                        self._check_cancelled()
                        sleep(min(DEFAULT_NARRATION_POLL_SECONDS, max(0.01, deadline - perf_counter())))
                return {"paused_seconds": duration_seconds}
            case PerformanceCueKind.EXPORT_SESSION_EPISODE:
                session_export = self.operator_console.export_session_episode(
                    EpisodeExportSessionRequest(session_id=resolved_session_id),
                    extra_artifacts={
                        "performance_run_summary": run.model_copy(deep=True),
                        "performance_cue_results": _flatten_cue_results(run),
                        "performance_show_definition": definition.model_copy(deep=True),
                    },
                )
                run.episode_id = session_export.episode_id
                return {
                    "session_export": session_export,
                    "episode_id": session_export.episode_id,
                    "artifact_dir": session_export.artifact_dir,
                    "artifact_files": session_export.artifact_files,
                }
        raise RuntimeError(f"unsupported_performance_cue:{cue.cue_kind.value}")

    def _run_live_scene_proof(
        self,
        *,
        cue: PerformanceCue,
        session_id: str,
        response_mode: ResponseMode,
        voice_mode: VoiceRuntimeMode,
    ) -> dict[str, Any]:
        started = perf_counter()
        result = self.operator_console.run_investor_scene(
            cue.scene_name or "",
            InvestorSceneRunRequest(
                session_id=session_id,
                user_id=cue.user_id,
                response_mode=response_mode,
                voice_mode=voice_mode,
                speak_reply=False,
            ),
        )
        return {
            "scene_name": result.scene_name,
            "success": result.success,
            "proof_backend_mode": PerformanceProofBackendMode.LIVE_COMPANION_PROOF.value,
            "reply_text": result.final_action.reply_text if result.final_action is not None else None,
            "grounding_sources": [item.model_dump(mode="json") for item in result.grounding_sources],
            "incident_present": any(item.incident_ticket is not None for item in result.items),
            "safe_idle_active": any(item.heartbeat.safe_idle_active for item in result.items),
            "body_projection_outcome": self._body_projection_outcome_from_items(result.items),
            "interaction_count": len(result.items),
            "scorecard_passed": result.scorecard.passed if result.scorecard is not None else None,
            "scorecard_score": result.scorecard.score if result.scorecard is not None else None,
            "proof_backend_latency_ms": round((perf_counter() - started) * 1000.0, 2),
            "degraded": not result.success,
            "raw_result": result.model_dump(mode="json"),
        }

    def _run_live_text_turn_proof(
        self,
        *,
        cue: PerformanceCue,
        session_id: str,
        response_mode: ResponseMode,
        voice_mode: VoiceRuntimeMode,
        input_text: str,
    ) -> dict[str, Any]:
        started = perf_counter()
        interaction = self.operator_console.submit_text_turn(
            OperatorVoiceTurnRequest(
                session_id=session_id,
                user_id=cue.user_id,
                input_text=input_text,
                response_mode=response_mode,
                voice_mode=voice_mode,
                speak_reply=False,
                source="performance_show",
            )
        )
        payload = self._interaction_payload(interaction)
        payload["proof_backend_latency_ms"] = round((perf_counter() - started) * 1000.0, 2)
        payload["proof_backend_mode"] = PerformanceProofBackendMode.LIVE_COMPANION_PROOF.value
        return payload

    def _run_deterministic_scene_proof(
        self,
        *,
        run: PerformanceRunResult,
        definition: PerformanceShowDefinition,
        request: PerformanceRunRequest,
        cue: PerformanceCue,
        session_id: str,
        template_name: str,
    ) -> dict[str, Any]:
        started = perf_counter()
        match template_name:
            case "grounded_sign":
                payload = self._deterministic_grounded_sign(session_id=session_id)
            case "memory_follow_up":
                payload = self._deterministic_memory_follow_up(cue=cue)
            case "oversight_accessibility":
                payload = self._deterministic_oversight_accessibility(session_id=session_id)
            case _:
                raise RuntimeError(f"unsupported_deterministic_scene_template:{template_name}")
        payload.setdefault("proof_backend_latency_ms", round((perf_counter() - started) * 1000.0, 2))
        payload["proof_backend_mode"] = PerformanceProofBackendMode.DETERMINISTIC_SHOW.value
        return payload

    def _run_deterministic_turn_proof(
        self,
        *,
        run: PerformanceRunResult,
        definition: PerformanceShowDefinition,
        request: PerformanceRunRequest,
        cue: PerformanceCue,
        session_id: str,
        prompt_text: str,
        template_name: str,
    ) -> dict[str, Any]:
        del run, definition, request
        started = perf_counter()
        match template_name:
            case "memory_intro":
                payload = self._deterministic_memory_intro(cue=cue, session_id=session_id)
            case "event_lookup":
                payload = self._deterministic_event_lookup(prompt_text=prompt_text)
            case _:
                raise RuntimeError(f"unsupported_deterministic_turn_template:{template_name}")
        payload.setdefault("proof_backend_latency_ms", round((perf_counter() - started) * 1000.0, 2))
        payload["proof_backend_mode"] = PerformanceProofBackendMode.DETERMINISTIC_SHOW.value
        return payload

    def _ensure_user_memory_record(
        self,
        *,
        user_id: str,
        session_id: str,
    ) -> UserMemoryRecord:
        orchestrator = self.operator_console.orchestrator
        existing = orchestrator.get_profile_memory(user_id)
        if existing is not None:
            return existing
        session = orchestrator.get_session(session_id)
        if session is not None and session.user_id != user_id:
            session.user_id = user_id
            orchestrator.memory.upsert_session(session)
        record = UserMemoryRecord(user_id=user_id)
        return orchestrator.memory.upsert_user_memory(record)

    def _deterministic_grounded_sign(self, *, session_id: str) -> dict[str, Any]:
        orchestrator = self.operator_console.orchestrator
        latest = orchestrator.get_latest_perception(session_id)
        world_model = orchestrator.memory.get_world_model()
        facts = orchestrator.knowledge_tools.recent_perception_facts(
            query="what sign can you see right now?",
            world_model=world_model,
            latest_perception=latest,
        )
        visible_text = [item.label for item in facts if getattr(item, "fact_type", "") == "visible_text" and item.label]
        source_refs = list(dict.fromkeys(item.source_ref for item in facts if item.source_ref))
        sign_text = next((item for item in visible_text if "workshop room" in item.lower()), visible_text[0] if visible_text else None)
        if sign_text is None:
            return {
                "success": False,
                "degraded": True,
                "reply_text": "I do not have fresh visual facts for that sign right now.",
                "grounding_sources": [],
                "raw_result": {
                    "scene_summary": latest.scene_summary if latest is not None else None,
                    "fact_count": len(facts),
                },
            }
        reply_text = f"The visible sign says {sign_text}, and it points toward the workshop room path."
        return {
            "success": True,
            "reply_text": reply_text,
            "grounding_sources": [{"source_ref": ref} for ref in source_refs] or (
                [{"source_ref": latest.source_frame.source_label}] if latest is not None else []
            ),
            "scene_summary": latest.scene_summary if latest is not None else None,
            "raw_result": {
                "visible_text": visible_text,
                "scene_summary": latest.scene_summary if latest is not None else None,
            },
        }

    def _deterministic_memory_intro(
        self,
        *,
        cue: PerformanceCue,
        session_id: str,
    ) -> dict[str, Any]:
        if cue.user_id is None:
            raise RuntimeError("deterministic_memory_intro_requires_user_id")
        orchestrator = self.operator_console.orchestrator
        memory = self._ensure_user_memory_record(user_id=cue.user_id, session_id=session_id)
        memory.display_name = "Alex"
        memory.preferences["route_preference"] = "quiet route"
        memory.last_session_id = session_id
        orchestrator.memory.upsert_user_memory(memory)
        venue_result = orchestrator.knowledge_tools.venue_knowledge.lookup_location(
            "Where is the quiet room?",
            last_location_key=None,
            visible_labels=[],
            attention_target=None,
        )
        session = orchestrator.get_session(session_id)
        if session is not None:
            session.user_id = cue.user_id
            session.current_topic = "wayfinding"
            session.session_memory["last_location"] = "quiet_room"
            orchestrator.memory.upsert_session(session)
            orchestrator.state_projection.refresh_world_state(session=session)
        reply_text = (
            f"Welcome, Alex. I can guide you by the quiet route. {venue_result.answer_text}"
            if venue_result is not None
            else "Welcome, Alex. I can guide you to the Quiet Room by the quiet route."
        )
        return {
            "success": True,
            "reply_text": reply_text,
            "grounding_sources": [
                {"source_ref": ref}
                for ref in (venue_result.metadata.get("source_refs") if venue_result is not None else [])
            ],
            "remembered_name": memory.display_name,
            "remembered_preferences": dict(memory.preferences),
            "raw_result": {
                "user_id": cue.user_id,
                "display_name": memory.display_name,
                "preferences": dict(memory.preferences),
            },
        }

    def _deterministic_memory_follow_up(self, *, cue: PerformanceCue) -> dict[str, Any]:
        if cue.user_id is None:
            raise RuntimeError("deterministic_memory_follow_up_requires_user_id")
        memory = self.operator_console.get_profile_memory(cue.user_id)
        if memory is None:
            return {
                "success": False,
                "degraded": True,
                "reply_text": "I do not have saved profile details for that visitor yet.",
                "grounding_sources": [],
                "raw_result": {"user_id": cue.user_id},
            }
        reply_text = (
            f"You introduced yourself as {memory.display_name or 'that visitor'}, "
            f"and you prefer the {memory.preferences.get('route_preference', 'default')}."
        )
        return {
            "success": True,
            "reply_text": reply_text,
            "grounding_sources": [{"source_ref": f"profile:{cue.user_id}"}],
            "remembered_name": memory.display_name,
            "remembered_preferences": dict(memory.preferences),
            "raw_result": {
                "user_id": cue.user_id,
                "display_name": memory.display_name,
                "preferences": dict(memory.preferences),
            },
        }

    def _deterministic_event_lookup(self, *, prompt_text: str) -> dict[str, Any]:
        venue_result = self.operator_console.orchestrator.knowledge_tools.venue_knowledge.lookup_events(prompt_text)
        if venue_result is None:
            return {
                "success": False,
                "degraded": True,
                "reply_text": "I do not have a verified event answer for that right now.",
                "grounding_sources": [],
                "raw_result": {"query": prompt_text},
            }
        return {
            "success": True,
            "reply_text": venue_result.answer_text,
            "grounding_sources": [{"source_ref": ref} for ref in venue_result.metadata.get("source_refs", [])],
            "raw_result": {
                "query": prompt_text,
                "metadata": dict(venue_result.metadata),
                "notes": list(venue_result.notes),
            },
        }

    def _deterministic_oversight_accessibility(self, *, session_id: str) -> dict[str, Any]:
        orchestrator = self.operator_console.orchestrator
        existing = orchestrator.memory.list_incident_tickets(
            scope=IncidentListScope.OPEN,
            session_id=session_id,
            limit=1,
        ).items
        if existing:
            ticket = existing[0]
            timeline = orchestrator.memory.list_incident_timeline(ticket_id=ticket.ticket_id, limit=1).items
        else:
            ticket = IncidentTicketRecord(
                session_id=session_id,
                participant_summary="Visitor requested the accessible route and a staff handoff for assistance.",
                reason_category=IncidentReasonCategory.ACCESSIBILITY,
                urgency=IncidentUrgency.HIGH,
                current_status=IncidentStatus.PENDING,
                last_status_note="Accessibility handoff created for the investor show proof lane.",
            )
            timeline_entry = IncidentTimelineRecord(
                ticket_id=ticket.ticket_id,
                session_id=session_id,
                event_type=IncidentTimelineEventType.CREATED,
                to_status=ticket.current_status,
                actor="blink_ai",
                note=ticket.last_status_note,
                metadata={
                    "reason_category": ticket.reason_category.value,
                    "urgency": ticket.urgency.value,
                },
            )
            ticket = orchestrator.memory.upsert_incident_ticket(ticket)
            orchestrator.memory.append_incident_timeline([timeline_entry])
            timeline = [timeline_entry]
            session = orchestrator.get_session(session_id)
            if session is not None:
                session.active_incident_ticket_id = ticket.ticket_id
                session.incident_status = ticket.current_status
                session.status = SessionStatus.ESCALATION_PENDING
                session.session_memory["incident_ticket_id"] = ticket.ticket_id
                session.session_memory["operator_escalation"] = "requested"
                orchestrator.memory.upsert_session(session)
                orchestrator.state_projection.refresh_world_state(session=session)
        reply_text = "I can take the accessible route, and I am opening a visible staff handoff now."
        return {
            "success": True,
            "reply_text": reply_text,
            "incident_present": True,
            "incident_status": ticket.current_status.value,
            "incident_reason_category": ticket.reason_category.value,
            "ticket_id": ticket.ticket_id,
            "grounding_sources": [{"source_ref": f"incident:{ticket.ticket_id}"}],
            "raw_result": {
                "ticket": ticket.model_dump(mode="json"),
                "timeline": [item.model_dump(mode="json") for item in timeline],
            },
        }

    def _run_body_motion_beat(
        self,
        beat: PerformanceMotionBeat,
        *,
        narration_linked: bool = False,
    ) -> dict[str, Any]:
        result = self.operator_console.run_body_semantic_smoke(
            BodySemanticSmokeRequest(
                action=beat.action,
                intensity=beat.intensity or 1.0,
                repeat_count=beat.repeat_count,
                note=beat.note,
                allow_bench_actions=False,
            )
        )
        body_state_payload = result.body_state.model_dump(mode="json") if result.body_state is not None else {}
        audit = (
            body_state_payload.get("latest_command_audit")
            or result.payload.get("latest_command_audit")
            or {}
        )
        margin_record, actuator_coverage = _motion_margin_record(
            action=beat.action,
            coverage_tags=list(beat.coverage_tags),
            audit=audit,
            body_state=body_state_payload,
            narration_linked=narration_linked,
        )
        preview_only = margin_record.outcome == PerformanceMotionOutcome.PREVIEW_ONLY
        degraded = (
            result.status != "ok"
            or margin_record.outcome == PerformanceMotionOutcome.BLOCKED
            or not margin_record.safety_gate_passed
        )
        return {
            "action": beat.action,
            "success": result.ok and result.status == "ok",
            "status": result.status,
            "detail": result.detail,
            "preview_only": preview_only,
            "body_projection_outcome": margin_record.outcome.value,
            "motion_outcome": margin_record.outcome.value,
            "motion_margin_record": margin_record.model_dump(mode="json"),
            "actuator_coverage": actuator_coverage.model_dump(mode="json"),
            "degraded": degraded,
            "raw_result": result.model_dump(mode="json"),
        }

    def _run_body_primitive_sequence_cue(
        self,
        cue: PerformanceCue,
    ) -> dict[str, Any]:
        steps = [
            PrimitiveSequenceStep(
                action=step.action,
                intensity=step.intensity,
                note=step.note,
            )
            for step in cue.primitive_sequence
        ]
        result = self.operator_console.run_body_primitive_sequence(
            BodyPrimitiveSequenceRequest(
                steps=steps,
                sequence_name=cue.cue_id,
                note=cue.note,
            )
        )
        body_state_payload = result.body_state.model_dump(mode="json") if result.body_state is not None else {}
        audit = (
            body_state_payload.get("latest_command_audit")
            or result.payload.get("latest_command_audit")
            or {}
        )
        driver_payload = result.payload.get("payload") if isinstance(result.payload, dict) else None
        body_payload = dict(driver_payload if isinstance(driver_payload, dict) else {})
        sequence_name = str(body_payload.get("sequence_name") or cue.cue_id)
        coverage_tags = sorted({
            group
            for step in cue.primitive_sequence
            for group in _action_coverage_groups(step.action)
        })
        resolved_motion_action = f"body_primitive_sequence:{sequence_name}"
        margin_record, actuator_coverage = _motion_margin_record(
            action=resolved_motion_action,
            coverage_tags=coverage_tags,
            audit=audit,
            body_state=body_state_payload,
            narration_linked=False,
        )
        degraded = result.status in {"blocked", "error"} or margin_record.outcome == PerformanceMotionOutcome.BLOCKED
        return {
            "success": result.ok and result.status == "ok",
            "status": result.status,
            "detail": result.detail,
            "degraded": degraded,
            "sequence_name": sequence_name,
            "primitive_steps": [step.action for step in cue.primitive_sequence],
            "sequence_step_count": len(cue.primitive_sequence),
            "returned_to_neutral": bool(body_payload.get("returned_to_neutral")),
            "preview_only": bool(body_payload.get("preview_only")),
            "live_requested": bool(body_payload.get("live_requested")),
            "body_projection_outcome": margin_record.outcome.value,
            "motion_outcome": margin_record.outcome.value,
            "motion_margin_record": margin_record.model_dump(mode="json"),
            "actuator_coverage": actuator_coverage.model_dump(mode="json"),
            "raw_result": result.model_dump(mode="json"),
        }

    def _run_body_staged_sequence_cue(
        self,
        cue: PerformanceCue,
    ) -> dict[str, Any]:
        stages = [
            StagedSequenceStage(
                stage_kind=stage.stage_kind,
                action=stage.action,
                intensity=stage.intensity,
                move_ms=stage.move_ms,
                hold_ms=stage.hold_ms,
                settle_ms=stage.settle_ms,
                accents=[
                    StagedSequenceAccent(
                        action=accent.action,
                        intensity=accent.intensity,
                        note=accent.note,
                    )
                    for accent in stage.accents
                ],
                note=stage.note,
            )
            for stage in cue.staged_sequence
        ]
        result = self.operator_console.run_body_staged_sequence(
            BodyStagedSequenceRequest(
                stages=stages,
                sequence_name=cue.cue_id,
                note=cue.note,
            )
        )
        body_state_payload = result.body_state.model_dump(mode="json") if result.body_state is not None else {}
        audit = (
            body_state_payload.get("latest_command_audit")
            or result.payload.get("latest_command_audit")
            or {}
        )
        driver_payload = result.payload.get("payload") if isinstance(result.payload, dict) else None
        body_payload = dict(driver_payload if isinstance(driver_payload, dict) else {})
        sequence_name = str(body_payload.get("sequence_name") or cue.cue_id)
        coverage_tags: list[str] = []
        for stage in cue.staged_sequence:
            if stage.action is not None:
                coverage_tags.extend(sorted(_action_coverage_groups(stage.action)))
            for accent in stage.accents:
                coverage_tags.extend(sorted(_action_coverage_groups(accent.action)))
        coverage_tags = sorted(set(coverage_tags))
        resolved_motion_action = f"body_staged_sequence:{sequence_name}"
        margin_record, actuator_coverage = _motion_margin_record(
            action=resolved_motion_action,
            coverage_tags=coverage_tags,
            audit=audit,
            body_state=body_state_payload,
            narration_linked=False,
        )
        degraded = result.status in {"blocked", "error"} or margin_record.outcome == PerformanceMotionOutcome.BLOCKED
        return {
            "success": result.ok and result.status == "ok",
            "status": result.status,
            "detail": result.detail,
            "degraded": degraded,
            "sequence_name": sequence_name,
            "structural_action": body_payload.get("structural_action"),
            "expressive_accents": list(body_payload.get("expressive_accents") or []),
            "stage_count": body_payload.get("stage_count"),
            "returned_to_neutral": bool(body_payload.get("returned_to_neutral")),
            "preview_only": bool(body_payload.get("preview_only")),
            "live_requested": bool(body_payload.get("live_requested")),
            "body_projection_outcome": margin_record.outcome.value,
            "motion_outcome": margin_record.outcome.value,
            "motion_margin_record": margin_record.model_dump(mode="json"),
            "actuator_coverage": actuator_coverage.model_dump(mode="json"),
            "raw_result": result.model_dump(mode="json"),
        }

    def _run_body_expressive_motif_cue(
        self,
        cue: PerformanceCue,
    ) -> dict[str, Any]:
        motif_ref = cue.expressive_motif
        if motif_ref is None:
            raise ValueError("body_expressive_motif_cue_requires_motif")
        motif = resolve_expressive_motif(motif_ref.motif_name)
        if motif is None:
            raise ValueError(f"unknown_expressive_motif:{motif_ref.motif_name}")
        result = self.operator_console.run_body_expressive_motif(
            BodyExpressiveSequenceRequest(
                motif=ExpressiveMotifReference(motif_name=motif_ref.motif_name),
                sequence_name=cue.cue_id,
                note=cue.note,
            )
        )
        body_state_payload = result.body_state.model_dump(mode="json") if result.body_state is not None else {}
        audit = (
            body_state_payload.get("latest_command_audit")
            or result.payload.get("latest_command_audit")
            or {}
        )
        driver_payload = result.payload.get("payload") if isinstance(result.payload, dict) else None
        body_payload = dict(driver_payload if isinstance(driver_payload, dict) else {})
        sequence_name = str(body_payload.get("sequence_name") or cue.cue_id)
        coverage_tags: list[str] = []
        for step in motif.steps:
            if step.action_name is not None:
                coverage_tags.extend(sorted(_action_coverage_groups(step.action_name)))
        coverage_tags = sorted(set(coverage_tags))
        resolved_motion_action = f"body_expressive_motif:{motif_ref.motif_name}"
        margin_record, actuator_coverage = _motion_margin_record(
            action=resolved_motion_action,
            coverage_tags=coverage_tags,
            audit=audit,
            body_state=body_state_payload,
            narration_linked=False,
        )
        degraded = result.status in {"blocked", "error"} or margin_record.outcome == PerformanceMotionOutcome.BLOCKED
        return {
            "success": result.ok and result.status == "ok",
            "status": result.status,
            "detail": result.detail,
            "degraded": degraded,
            "sequence_name": sequence_name,
            "motif_name": body_payload.get("motif_name") or motif_ref.motif_name,
            "structural_action": body_payload.get("structural_action"),
            "expressive_steps": list(body_payload.get("expressive_steps") or []),
            "step_kinds": list(body_payload.get("step_kinds") or []),
            "sequence_step_count": body_payload.get("sequence_step_count"),
            "returned_to_neutral": bool(body_payload.get("returned_to_neutral")),
            "preview_only": bool(body_payload.get("preview_only")),
            "live_requested": bool(body_payload.get("live_requested")),
            "body_projection_outcome": margin_record.outcome.value,
            "motion_outcome": margin_record.outcome.value,
            "motion_margin_record": margin_record.model_dump(mode="json"),
            "actuator_coverage": actuator_coverage.model_dump(mode="json"),
            "raw_result": result.model_dump(mode="json"),
        }

    def _run_body_range_demo_cue(
        self,
        cue: PerformanceCue,
    ) -> dict[str, Any]:
        preset_name = str(cue.payload.get("preset_name") or RANGE_DEMO_DEFAULT_PRESET)
        sequence_name = str(cue.payload.get("sequence_name") or "").strip() or None
        result = self.operator_console.run_body_range_demo(
            sequence_name=sequence_name,
            preset_name=preset_name,
            note=cue.note,
        )
        body_state_payload = result.body_state.model_dump(mode="json") if result.body_state is not None else {}
        audit = (
            body_state_payload.get("latest_command_audit")
            or result.payload.get("latest_command_audit")
            or {}
        )
        driver_payload = result.payload.get("payload") if isinstance(result.payload, dict) else None
        body_payload = dict(driver_payload if isinstance(driver_payload, dict) else {})
        resolved_motion_action = f"body_range_demo:{body_payload.get('sequence_name') or sequence_name or preset_name}"
        margin_record, actuator_coverage = _motion_margin_record(
            action=resolved_motion_action,
            coverage_tags=list(ACTUATOR_GROUPS),
            audit=audit,
            body_state=body_state_payload,
            narration_linked=False,
        )
        degraded = result.status in {"blocked", "error"} or margin_record.outcome == PerformanceMotionOutcome.BLOCKED
        return {
            "success": result.ok and result.status == "ok",
            "status": result.status,
            "detail": result.detail,
            "degraded": degraded,
            "sequence_name": sequence_name,
            "preview_only": bool(body_payload.get("preview_only")),
            "live_requested": bool(body_payload.get("live_requested")),
            "preset_name": preset_name,
            "range_demo": body_payload.get("range_demo"),
            "blocked_reason": body_payload.get("blocked_reason"),
            "body_projection_outcome": margin_record.outcome.value,
            "motion_outcome": margin_record.outcome.value,
            "motion_margin_record": margin_record.model_dump(mode="json"),
            "actuator_coverage": actuator_coverage.model_dump(mode="json"),
            "raw_result": result.model_dump(mode="json"),
        }

    def _interaction_payload(self, interaction: OperatorInteractionResult) -> dict[str, Any]:
        body_state_payload = (
            interaction.telemetry.body_state.model_dump(mode="json")
            if interaction.telemetry.body_state is not None
            else {}
        )
        projection_outcome = _projection_outcome_from_body_state(body_state_payload)
        return {
            "reply_text": interaction.response.reply_text,
            "grounding_sources": [item.model_dump(mode="json") for item in interaction.grounding_sources],
            "incident_present": interaction.incident_ticket is not None,
            "incident_status": (
                interaction.incident_ticket.current_status.value if interaction.incident_ticket is not None else None
            ),
            "incident_reason_category": (
                interaction.incident_ticket.reason_category.value if interaction.incident_ticket is not None else None
            ),
            "safe_idle_active": interaction.heartbeat.safe_idle_active,
            "body_projection_outcome": projection_outcome.value if projection_outcome is not None else None,
            "motion_outcome": projection_outcome.value if projection_outcome is not None else None,
            "preview_only": projection_outcome == PerformanceMotionOutcome.PREVIEW_ONLY,
            "success": interaction.success,
            "degraded": not interaction.success,
            "raw_result": interaction.model_dump(mode="json"),
        }

    def _body_projection_outcome_from_items(self, items: list[OperatorInteractionResult]) -> str | None:
        for item in reversed(items):
            if item.telemetry.body_state is not None:
                body_state = item.telemetry.body_state.model_dump(mode="json")
                outcome = _projection_outcome_from_body_state(body_state)
                if outcome is not None:
                    return outcome.value
        return None

    def _proof_checks(self, *, cue: PerformanceCue, payload: dict[str, Any]) -> list[ScorecardCriterion]:
        checks: list[ScorecardCriterion] = []
        reply_text = str(payload.get("reply_text") or "")
        for expected in cue.expect_reply_contains:
            checks.append(
                ScorecardCriterion(
                    criterion=f"reply_contains:{expected}",
                    passed=expected in reply_text,
                    expected=expected,
                    observed=reply_text or None,
                )
            )
        if cue.expect_grounding_sources is not None:
            grounding_count = len(payload.get("grounding_sources") or [])
            checks.append(
                ScorecardCriterion(
                    criterion="grounding_sources_present",
                    passed=bool(grounding_count) is cue.expect_grounding_sources,
                    expected=str(cue.expect_grounding_sources),
                    observed=str(bool(grounding_count)),
                )
            )
        if cue.expect_incident is not None:
            incident_present = bool(payload.get("incident_present"))
            checks.append(
                ScorecardCriterion(
                    criterion="incident_present",
                    passed=incident_present is cue.expect_incident,
                    expected=str(cue.expect_incident),
                    observed=str(incident_present),
                )
            )
        if cue.expect_incident_status is not None:
            observed_status = str(payload.get("incident_status") or "")
            checks.append(
                ScorecardCriterion(
                    criterion="incident_status",
                    passed=observed_status == cue.expect_incident_status,
                    expected=cue.expect_incident_status,
                    observed=observed_status or None,
                )
            )
        if cue.expect_incident_reason_category is not None:
            observed_reason = str(payload.get("incident_reason_category") or "")
            checks.append(
                ScorecardCriterion(
                    criterion="incident_reason_category",
                    passed=observed_reason == cue.expect_incident_reason_category,
                    expected=cue.expect_incident_reason_category,
                    observed=observed_reason or None,
                )
            )
        if cue.expect_safe_idle is not None:
            safe_idle_active = bool(payload.get("safe_idle_active"))
            checks.append(
                ScorecardCriterion(
                    criterion="safe_idle_active",
                    passed=safe_idle_active is cue.expect_safe_idle,
                    expected=str(cue.expect_safe_idle),
                    observed=str(safe_idle_active),
                )
            )
        if cue.expect_user_memory_facts or cue.expect_user_memory_preferences:
            profile = self.operator_console.get_profile_memory(cue.user_id) if cue.user_id else None
            facts = profile.facts if profile is not None else {}
            preferences = profile.preferences if profile is not None else {}
            for key, expected in cue.expect_user_memory_facts.items():
                observed = getattr(profile, key, None) if profile is not None and hasattr(profile, key) else facts.get(key)
                checks.append(
                    ScorecardCriterion(
                        criterion=f"user_memory_fact:{key}",
                        passed=observed == expected,
                        expected=expected,
                        observed=observed,
                    )
                )
            for key, expected in cue.expect_user_memory_preferences.items():
                observed = preferences.get(key)
                checks.append(
                    ScorecardCriterion(
                        criterion=f"user_memory_preference:{key}",
                        passed=observed == expected,
                        expected=expected,
                        observed=observed,
                    )
                )
        for expected in cue.expect_export_artifacts:
            artifact_files = payload.get("artifact_files") or {}
            observed = None
            passed = False
            if isinstance(artifact_files, dict):
                observed = artifact_files.get(expected)
                passed = bool(observed)
            checks.append(
                ScorecardCriterion(
                    criterion=f"export_artifact:{expected}",
                    passed=passed,
                    expected=expected,
                    observed=str(observed) if observed is not None else None,
                )
            )
        if cue.expect_body_projection_outcome is not None:
            observed_outcome = str(payload.get("body_projection_outcome") or "")
            checks.append(
                ScorecardCriterion(
                    criterion="body_projection_outcome",
                    passed=observed_outcome == cue.expect_body_projection_outcome,
                    expected=cue.expect_body_projection_outcome,
                    observed=observed_outcome or None,
                )
            )
        for expected in cue.expect_body_status_contains:
            observed_detail = json.dumps(payload.get("raw_result") or payload, sort_keys=True)
            checks.append(
                ScorecardCriterion(
                    criterion=f"body_status_contains:{expected}",
                    passed=expected in observed_detail,
                    expected=expected,
                    observed=observed_detail,
                )
            )
        for path, expected in cue.expect_payload_equals.items():
            observed = _resolve_payload_path(payload, path)
            checks.append(
                ScorecardCriterion(
                    criterion=f"payload_equals:{path}",
                    passed=observed == expected,
                    expected=str(expected),
                    observed=str(observed) if observed is not None else None,
                )
            )
        return checks

    def _continue_on_error(
        self,
        *,
        cue: PerformanceCue,
        definition: PerformanceShowDefinition,
        request: PerformanceRunRequest,
    ) -> bool:
        if cue.continue_on_error is not None:
            return cue.continue_on_error
        if request.continue_on_error is not None:
            return request.continue_on_error
        return definition.defaults.continue_on_error

    def _record_timing_breakdown(
        self,
        run: PerformanceRunResult,
        *,
        cue: PerformanceCue,
        cue_result: PerformanceCueResult,
    ) -> None:
        if cue.cue_kind == PerformanceCueKind.NARRATE:
            self._timing_add(run, "narration", cue_result.actual_duration_ms)
            self._timing_add(run, "motion_track", cue_result.payload.get("motion_track_ms"))
        elif cue.cue_kind in {PerformanceCueKind.RUN_SCENE, PerformanceCueKind.SUBMIT_TEXT_TURN, PerformanceCueKind.INJECT_EVENT}:
            self._timing_add(run, "proof", cue_result.actual_duration_ms)
            self._timing_add(run, "proof_backend_latency", cue_result.payload.get("proof_backend_latency_ms"))
        elif cue.cue_kind == PerformanceCueKind.PAUSE:
            self._timing_add(run, "idle", cue_result.actual_duration_ms)
        elif cue.cue_kind in {
            PerformanceCueKind.BODY_SEMANTIC_SMOKE,
            PerformanceCueKind.BODY_PRIMITIVE_SEQUENCE,
            PerformanceCueKind.BODY_STAGED_SEQUENCE,
            PerformanceCueKind.BODY_EXPRESSIVE_MOTIF,
            PerformanceCueKind.BODY_RANGE_DEMO,
        }:
            self._timing_add(run, "body_motion", cue_result.actual_duration_ms)

    def _resolved_narration_voice_mode(
        self,
        *,
        definition: PerformanceShowDefinition,
        request: PerformanceRunRequest,
        cue: PerformanceCue | None = None,
    ) -> VoiceRuntimeMode:
        return cue.voice_mode if cue is not None and cue.voice_mode is not None else (
            request.narration_voice_mode or definition.defaults.narration_voice_mode
        )

    def _perform_narration(
        self,
        *,
        run: PerformanceRunResult,
        text: str,
        narration: ResolvedNarrationConfig,
        motion_track: list[PerformanceMotionBeat],
        target_duration_ms: int | None,
        enabled: bool,
    ) -> dict[str, Any]:
        run.current_narration = text
        if not enabled:
            return {
                "spoken_text": text,
                "narration_enabled": False,
                "language": narration.language,
                "voice_preset": narration.voice_preset,
                "voice_name": narration.voice_name,
                "voice_rate": narration.voice_rate,
                "motion_track_ms": 0.0,
                "motion_results": [],
            }
        runtime = self.operator_console.voice_manager.get_runtime(
            narration.voice_mode,
            voice_name=narration.voice_name,
            rate=narration.voice_rate,
        )
        output = runtime.speak(run.session_id, text, mode=narration.voice_mode)
        motion_results, motion_track_ms = self._perform_motion_track(
            run=run,
            runtime=runtime,
            motion_track=motion_track,
        )
        self._wait_for_narration_completion(
            runtime=runtime,
            narration=narration,
            session_id=run.session_id,
            target_duration_ms=target_duration_ms,
            text=text,
        )
        aggregate_motion = _aggregate_motion_results(motion_results)
        return {
            "spoken_text": text,
            "voice_output": output.model_dump(mode="json"),
            "narration_enabled": True,
            "language": narration.language,
            "voice_preset": narration.voice_preset,
            "voice_name": narration.voice_name,
            "voice_rate": narration.voice_rate,
            "motion_results": motion_results,
            "motion_track_ms": motion_track_ms,
            **aggregate_motion,
        }

    def _perform_motion_track(
        self,
        *,
        run: PerformanceRunResult,
        runtime,
        motion_track: list[PerformanceMotionBeat],
    ) -> tuple[list[dict[str, Any]], float]:
        if not motion_track:
            return [], 0.0
        started = perf_counter()
        last_offset_seconds = 0.0
        results: list[dict[str, Any]] = []
        for beat in sorted(motion_track, key=lambda item: item.offset_ms):
            offset_seconds = max(0.0, beat.offset_ms / 1000.0)
            wait_seconds = max(0.0, offset_seconds - last_offset_seconds)
            if wait_seconds > 0:
                deadline = perf_counter() + wait_seconds
                while perf_counter() < deadline:
                    self._check_cancelled()
                    sleep(min(DEFAULT_NARRATION_POLL_SECONDS, max(0.01, deadline - perf_counter())))
            if run.pending_body_settle_reason:
                settle_seconds = (
                    BODY_SAFE_IDLE_SETTLE_SECONDS
                    if run.pending_body_settle_reason == PerformanceCueKind.BODY_SAFE_IDLE.value
                    else BODY_SETTLE_SECONDS
                )
                sleep(settle_seconds)
                refreshed_body_state = self._body_state_payload(force_refresh=True)
                run.pending_body_settle_reason = None
                suspicious_detail = self._body_state_suspicious_for_settle(refreshed_body_state)
                if suspicious_detail is not None:
                    classification = (
                        "suspect_voltage_event"
                        if "voltage" in suspicious_detail
                        else "readback_implausible"
                    )
                    run.last_body_issue_classification = classification
                    run.last_body_issue_confirmation_result = "settle_gate_continue"
                    if run.body_fault_trigger_cue_id is None:
                        run.body_fault_trigger_cue_id = beat.action
                        run.body_fault_detail = suspicious_detail
                    warning = f"body_settle_warning:{suspicious_detail}"
                    if warning not in run.notes:
                        run.notes.append(warning)
            state = runtime.get_state(run.session_id)
            if state.status.value not in {"speaking", "completed", "simulated"} and beat.offset_ms > 0:
                results.append(
                    {
                        "action": beat.action,
                        "status": "skipped",
                        "detail": "speech_completed_before_motion_beat",
                        "offset_ms": beat.offset_ms,
                    }
                )
                last_offset_seconds = offset_seconds
                continue
            beat_result = self._run_body_motion_beat(beat, narration_linked=True)
            results.append({"offset_ms": beat.offset_ms, **beat_result})
            if beat_result.get("body_projection_outcome"):
                run.last_body_projection_outcome = str(beat_result["body_projection_outcome"])
            if beat_result.get("preview_only"):
                run.preview_only = True
            margin_payload = beat_result.get("motion_margin_record")
            if isinstance(margin_payload, dict) and margin_payload:
                margin_record = PerformanceMotionMarginRecord.model_validate(margin_payload)
                if margin_record.fault_classification:
                    run.last_body_issue_classification = margin_record.fault_classification
                    run.last_body_issue_confirmation_result = margin_record.confirmation_result
                if margin_record.fault_classification and run.body_fault_trigger_cue_id is None:
                    run.body_fault_trigger_cue_id = beat.action
                    run.body_fault_detail = margin_record.confirmation_result or margin_record.detail
            last_offset_seconds = offset_seconds
        return results, round((perf_counter() - started) * 1000.0, 2)

    def _wait_for_narration_completion(
        self,
        *,
        runtime,
        narration: ResolvedNarrationConfig,
        session_id: str,
        target_duration_ms: int | None,
        text: str,
    ) -> None:
        wait_seconds = (
            float(target_duration_ms) / 1000.0
            if target_duration_ms is not None
            else _speech_timeout_seconds(
                text=text,
                language=narration.language,
                voice_rate=narration.voice_rate,
            )
        )
        if wait_seconds <= 0:
            return
        deadline = perf_counter() + wait_seconds
        while perf_counter() < deadline:
            if self.cancel_checker is not None and self.cancel_checker():
                runtime.cancel(session_id)
                raise PerformanceShowCancelled("performance_show_cancelled")
            state = runtime.get_state(session_id)
            if state.status.value != "speaking":
                return
            sleep(min(DEFAULT_NARRATION_POLL_SECONDS, max(0.01, deadline - perf_counter())))


class PerformanceShowManager:
    def __init__(
        self,
        *,
        operator_console: "OperatorConsoleService",
        report_dir: str | Path,
    ) -> None:
        self.operator_console = operator_console
        self.report_store = PerformanceReportStore(report_dir)
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="blink-performance-show")
        self._lock = Lock()
        self._runs: dict[str, PerformanceRunResult] = {}
        self._futures: dict[str, Future[PerformanceRunResult]] = {}
        self._cancellations: dict[str, Event] = {}
        self._definitions: dict[str, PerformanceShowDefinition] = {}
        self._active_run_id: str | None = None
        self._latest_run_id: str | None = None

    def catalog(self) -> PerformanceShowCatalogResponse:
        return PerformanceShowCatalogResponse(
            items=list_packaged_performance_shows(),
            active_run_id=self._active_run_id,
            latest_run_id=self._latest_run_id,
        )

    def get_run(self, run_id: str) -> PerformanceRunResult | None:
        with self._lock:
            run = self._runs.get(run_id)
        if run is not None:
            return run.model_copy(deep=True)
        return self.report_store.get(run_id)

    def run_show(self, show_name: str, request: PerformanceRunRequest | None = None) -> PerformanceRunResult:
        definition = load_show_definition(show_name)
        request = request or PerformanceRunRequest()
        if request.background:
            with self._lock:
                if self._active_run_id is not None:
                    active = self._futures.get(self._active_run_id)
                    if active is None or not active.done():
                        raise RuntimeError(f"performance_show_already_running:{self._active_run_id}")
            resolved_definition = select_show_definition(definition, request)
            runner = PerformanceShowRunner(
                operator_console=self.operator_console,
                report_store=self.report_store,
            )
            narration = runner._resolved_narration_config(definition=resolved_definition, request=request)
            proof_backend_mode = runner._resolved_proof_backend_mode(definition=resolved_definition, request=request)
            initial = PerformanceRunResult(
                run_id=f"performance-{uuid4().hex[:12]}",
                show_name=resolved_definition.show_name,
                version=resolved_definition.version,
                session_id=request.session_id or resolved_definition.session_id,
                proof_backend_mode=proof_backend_mode,
                language=narration.language,
                narration_voice_preset=narration.voice_preset,
                narration_voice_name=narration.voice_name,
                narration_voice_rate=narration.voice_rate,
                selected_segment_ids=[segment.segment_id for segment in resolved_definition.segments],
                selected_cue_ids=[cue.cue_id for segment in resolved_definition.segments for cue in segment.cues],
                narration_only=request.narration_only,
                proof_only=request.proof_only,
                target_total_duration_seconds=_total_duration_seconds(resolved_definition),
                timing_breakdown_ms={
                    "narration": 0.0,
                    "proof": 0.0,
                    "motion_track": 0.0,
                    "idle": 0.0,
                    "body_motion": 0.0,
                    "proof_backend_latency": 0.0,
                },
            )
            if narration.notes:
                initial.notes.extend(narration.notes)
            self._remember_run(initial)
            self.report_store.save(initial, show_definition=resolved_definition)
            cancel_event = Event()
            with self._lock:
                self._definitions[initial.run_id] = resolved_definition.model_copy(deep=True)
                self._cancellations[initial.run_id] = cancel_event
                self._active_run_id = initial.run_id
                self._latest_run_id = initial.run_id
            future = self._executor.submit(self._run_background, definition, request, initial.run_id)
            with self._lock:
                self._futures[initial.run_id] = future
            return initial
        runner = PerformanceShowRunner(
            operator_console=self.operator_console,
            report_store=self.report_store,
            status_callback=self._remember_run,
        )
        result = runner.run(definition, request.model_copy(update={"background": False}))
        self._remember_run(result)
        with self._lock:
            self._latest_run_id = result.run_id
            self._active_run_id = None
        return result

    def cancel_run(self, run_id: str) -> PerformanceRunResult:
        with self._lock:
            run = self._runs.get(run_id)
            if run is None:
                raise KeyError(run_id)
            future = self._futures.get(run_id)
            cancel_event = self._cancellations.get(run_id)
            if future is None or cancel_event is None or future.done():
                raise RuntimeError(f"performance_show_not_running:{run_id}")
            cancel_event.set()
            run.stop_requested = True
            self._runs[run_id] = run.model_copy(deep=True)
            return run.model_copy(deep=True)

    def _run_background(
        self,
        definition: PerformanceShowDefinition,
        request: PerformanceRunRequest,
        run_id: str,
    ) -> PerformanceRunResult:
        cancel_event = self._cancellations[run_id]
        runner = PerformanceShowRunner(
            operator_console=self.operator_console,
            report_store=self.report_store,
            status_callback=self._remember_run,
            cancel_checker=cancel_event.is_set,
        )
        result = runner.run(
            definition,
            request.model_copy(update={"background": False, "session_id": request.session_id or definition.session_id}),
            run_id=run_id,
        )
        self._remember_run(result)
        with self._lock:
            self._active_run_id = None
            self._latest_run_id = result.run_id
            self._futures.pop(run_id, None)
            self._cancellations.pop(run_id, None)
        return result

    def _remember_run(self, run: PerformanceRunResult) -> None:
        with self._lock:
            self._runs[run.run_id] = run.model_copy(deep=True)
            self._latest_run_id = run.run_id


def benchmark_show_narration(
    *,
    operator_console: "OperatorConsoleService",
    definition: PerformanceShowDefinition,
    request: PerformanceRunRequest | None = None,
) -> dict[str, Any]:
    request = request or PerformanceRunRequest()
    selected = select_show_definition(
        definition,
        request.model_copy(update={"background": False, "narration_only": True}),
    )
    runner = PerformanceShowRunner(
        operator_console=operator_console,
        report_store=PerformanceReportStore(operator_console.settings.performance_report_dir),
    )
    narration = runner._resolved_narration_config(definition=selected, request=request)
    _validate_language_coverage(selected, narration.language)
    session_id = request.session_id or selected.session_id
    runtime = operator_console.voice_manager.get_runtime(
        narration.voice_mode,
        voice_name=narration.voice_name,
        rate=narration.voice_rate,
    )
    items: list[dict[str, Any]] = []
    total_actual_ms = 0.0
    total_target_ms = 0
    for segment, cue in _narration_cues(selected):
        text = runner._cue_text(cue, definition=selected, request=request) or ""
        started = perf_counter()
        output = runtime.speak(session_id, text, mode=narration.voice_mode)
        timeout_seconds = _speech_timeout_seconds(
            text=text,
            language=narration.language,
            voice_rate=narration.voice_rate,
        )
        deadline = perf_counter() + timeout_seconds
        final_status = output.status.value
        if final_status == "speaking":
            while perf_counter() < deadline:
                state = runtime.get_state(session_id)
                final_status = state.status.value
                if final_status != "speaking":
                    break
                sleep(DEFAULT_NARRATION_POLL_SECONDS)
        actual_ms = round((perf_counter() - started) * 1000.0, 2)
        total_actual_ms += actual_ms
        total_target_ms += cue.target_duration_ms or 0
        items.append(
            {
                "segment_id": segment.segment_id,
                "cue_id": cue.cue_id,
                "label": cue.label,
                "target_duration_ms": cue.target_duration_ms,
                "actual_duration_ms": actual_ms,
                "timing_drift_ms": (
                    round(actual_ms - float(cue.target_duration_ms), 2)
                    if cue.target_duration_ms is not None
                    else None
                ),
                "voice_status": final_status,
                "word_or_char_units": _speech_unit_count(text, language=narration.language),
                "text_preview": text,
            }
        )
    runtime.cancel(session_id)
    return {
        "show_name": selected.show_name,
        "version": selected.version,
        "session_id": session_id,
        "language": narration.language,
        "voice_mode": narration.voice_mode.value,
        "voice_preset": narration.voice_preset,
        "voice_name": narration.voice_name,
        "voice_rate": narration.voice_rate,
        "segment_ids": [segment.segment_id for segment in selected.segments],
        "cue_ids": [cue.cue_id for segment in selected.segments for cue in segment.cues],
        "target_total_duration_seconds": _total_duration_seconds(selected),
        "target_narration_ms": total_target_ms,
        "actual_narration_ms": round(total_actual_ms, 2),
        "timing_drift_ms": round(total_actual_ms - float(total_target_ms), 2),
        "cue_count": len(items),
        "items": items,
    }


__all__ = [
    "PerformanceReportStore",
    "PerformanceShowManager",
    "PerformanceShowRunner",
    "SHOW_DEFINITION_PATHS",
    "benchmark_show_narration",
    "load_show_definition",
    "list_packaged_performance_shows",
    "select_show_definition",
    "validate_show_definition",
]
