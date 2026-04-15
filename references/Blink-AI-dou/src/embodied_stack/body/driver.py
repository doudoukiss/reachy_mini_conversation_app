from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from threading import RLock

from embodied_stack.config import Settings
from embodied_stack.shared.contracts import (
    AnimationRequest,
    CharacterProjectionProfile,
    CharacterProjectionStatus,
    CharacterSemanticIntent,
    BodyCapabilityProfile,
    BodyCommandAuditRecord,
    BodyCommandOutcomeRecord,
    BodyDriverMode,
    BodyState,
    CompiledAnimation,
    CompiledBodyFrame,
    ExpressionRequest,
    GazeRequest,
    GestureRequest,
    RobotCommand,
    utc_now,
)

from .animations import animation_timeline, gesture_timeline
from .compiler import (
    SUPPORTED_ANIMATIONS,
    SUPPORTED_EXPRESSIONS,
    SUPPORTED_GAZE_TARGETS,
    SUPPORTED_GESTURES,
    SemanticBodyCompiler,
    StagedSequenceAccentSpec,
    StagedSequenceStageSpec,
)
from .grounded_catalog import grounded_catalog_export
from .expressive_motifs import (
    ExpressiveSequenceStepSpec,
    resolve_expressive_motif,
)
from .library import expression_pose
from .motion_tuning import extract_clamp_reasons, remaining_margin_percent_by_family
from .profile import load_head_profile
from .projection import projection_profile_supports_avatar, projection_profile_supports_robot_head, resolve_character_projection_profile
from .primitives import PrimitiveSequenceStepSpec
from .range_demo import available_range_demo_presets, available_range_demo_sequences, build_range_demo_plan
from .semantics import build_semantic_smoke_request
from .serial import FeetechBodyBridge, LIVE_SERIAL_MODE, ServoTransportError, build_servo_transport, list_serial_ports, read_bench_health_many
from .serial.bench import (
    DEFAULT_ARM_LEASE_PATH,
    DEFAULT_MOTION_REPORT_DIR,
    clear_arm_lease,
    confirm_live_transport,
    coupling_validation_ready,
    execute_bench_command,
    execute_servo_lab_sweep,
    conflicting_range_joints,
    neutral_targets,
    read_arm_lease,
    read_bench_snapshot,
    transport_summary as bench_transport_summary,
    validate_motion_arm,
    write_arm_lease,
)
from .serial.doctor import DEFAULT_BRINGUP_REPORT_PATH, parse_servo_ids, run_serial_doctor
from .serial.evidence import build_motion_report_index, build_serial_failure_summary, collect_request_response_history, load_motion_reports
from .servo_lab import (
    ServoLabError,
    build_servo_lab_catalog,
    motion_control_payload,
    readback_payload,
    resolve_servo_lab_move,
    resolve_servo_lab_sweep,
    save_servo_lab_calibration,
    servo_lab_capabilities,
)
from .tuning import (
    DEFAULT_SEMANTIC_TUNING_PATH,
    DEFAULT_TEACHER_REVIEW_PATH,
    load_semantic_tuning,
    record_teacher_review,
    semantic_library_payload,
    tuning_override_names,
)

BODYLESS_TRANSPORT_MODE = "bodyless"
VIRTUAL_PREVIEW_TRANSPORT_MODE = "virtual_preview"
SERIAL_REFRESH_INTERVAL_SECONDS = 1.0


class BodyCommandApplyError(RuntimeError):
    def __init__(self, classification: str, detail: str) -> None:
        self.classification = classification
        self.detail = detail
        super().__init__(detail)


def _parse_timestamp(value: object | None) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        return datetime.fromisoformat(value)
    return None


def _extract_clamped_joints(notes: list[str]) -> list[str]:
    joints: list[str] = []
    for note in notes:
        head, _, _ = str(note).partition(":")
        if head:
            joints.append(head)
    return sorted(dict.fromkeys(joints))


def _semantic_family_for_command_type(command_type: str) -> str | None:
    mapping = {
        "set_gaze": "gaze",
        "set_expression": "expression",
        "perform_gesture": "gesture",
        "perform_animation": "animation",
        "body_primitive_sequence": "animation",
        "body_staged_sequence": "animation",
        "body_expressive_motif": "animation",
        "body_range_demo": "range_demo",
        "body_power_preflight": "power_preflight",
        "character_projection": "projection",
        "safe_idle": "expression",
    }
    return mapping.get(command_type)


def _load_head_calibration(path: str, *, profile):
    # Import lazily so `python -m embodied_stack.body.calibration` does not pre-load
    # the target module through the package import path.
    from .calibration import load_head_calibration

    return load_head_calibration(path, profile=profile)


def _save_head_calibration(record, path: str) -> None:
    from .calibration import save_head_calibration

    save_head_calibration(record, path)


@dataclass
class BaseBodyDriver:
    settings: Settings

    def __post_init__(self) -> None:
        self.profile = load_head_profile(self.settings.blink_head_profile)
        self.calibration = _load_head_calibration(self.settings.blink_head_calibration, profile=self.profile)
        self._semantic_tuning_path = self.settings.blink_body_semantic_tuning_path or str(DEFAULT_SEMANTIC_TUNING_PATH)
        self._teacher_review_path = str(DEFAULT_TEACHER_REVIEW_PATH)
        self.semantic_tuning = load_semantic_tuning(
            profile_name=self.profile.profile_name,
            calibration_path=self.settings.blink_head_calibration,
            path=self._semantic_tuning_path,
        )
        self.compiler = SemanticBodyCompiler(
            profile=self.profile,
            calibration=self.calibration,
            tuning=self.semantic_tuning,
            tuning_path=self._semantic_tuning_path,
        )
        self._setup_driver()
        self.capabilities = self._build_capabilities()
        self.state = BodyState(
            driver_mode=self.capabilities.driver_mode,
            head_profile_name=self.profile.profile_name,
            head_profile_path=self.profile.source_path or self.settings.blink_head_profile,
            head_profile_version=self.profile.profile_version,
            connected=self.capabilities.connected,
            present=self.capabilities.present,
            transport_reason_code=self.capabilities.transport_reason_code,
            transport_confirmed_live=self.capabilities.transport_confirmed_live,
            transport_port=self.capabilities.transport_port,
            transport_baud_rate=self.capabilities.transport_baud_rate,
            calibration_path=self._calibration_path(),
            calibration_version=self._calibration_version(),
            calibration_status=self._calibration_status(),
            live_motion_enabled=self._live_motion_enabled(),
        )
        self.reset()

    def _setup_driver(self) -> None:
        return None

    def _reload_tuning(self) -> None:
        self.semantic_tuning = load_semantic_tuning(
            profile_name=self.profile.profile_name,
            calibration_path=self._calibration_path() or self.settings.blink_head_calibration,
            path=self._semantic_tuning_path,
        )
        self.compiler.set_tuning(self.semantic_tuning, tuning_path=self._semantic_tuning_path)

    def reset(self) -> None:
        neutral = self.compiler.compile_frame(self.compiler.neutral_pose(), frame_name="neutral", animation_name="neutral")
        projection_profile = resolve_character_projection_profile(self.settings)
        self.state = BodyState(
            driver_mode=self.capabilities.driver_mode,
            character_projection=CharacterProjectionStatus(
                profile=projection_profile,
                avatar_enabled=projection_profile_supports_avatar(projection_profile),
                robot_head_enabled=projection_profile_supports_robot_head(projection_profile),
                outcome="idle",
            ),
            head_profile_name=self.profile.profile_name,
            head_profile_path=self.profile.source_path or self.settings.blink_head_profile,
            head_profile_version=self.profile.profile_version,
            connected=self.capabilities.connected,
            present=self.capabilities.present,
            transport_mode=self.capabilities.transport_mode,
            transport_healthy=self.capabilities.transport_healthy,
            transport_error=self.capabilities.transport_error,
            transport_reason_code=self.capabilities.transport_reason_code,
            transport_confirmed_live=self.capabilities.transport_confirmed_live,
            transport_port=self.capabilities.transport_port,
            transport_baud_rate=self.capabilities.transport_baud_rate,
            calibration_path=self._calibration_path(),
            calibration_version=self._calibration_version(),
            calibration_status=self._calibration_status(),
            live_motion_enabled=self._live_motion_enabled(),
            pose=neutral.pose,
            active_expression="neutral",
            servo_targets=neutral.servo_targets,
            current_frame=neutral,
            compiled_animation=CompiledAnimation(
                animation_name="neutral",
                frames=[neutral],
                total_duration_ms=neutral.duration_ms + neutral.hold_ms,
            ),
            virtual_preview=neutral.preview,
            updated_at=utc_now(),
        )
        self._sync_transport_status()

    def transport_summary(self) -> dict[str, object]:
        return {
            "mode": self.state.transport_mode or self.capabilities.transport_mode,
            "port": self.state.transport_port,
            "baud_rate": self.state.transport_baud_rate,
            "timeout_seconds": None,
            "healthy": bool(self.state.transport_healthy),
            "confirmed_live": bool(self.state.transport_confirmed_live),
            "reason_code": self.state.transport_reason_code or self.capabilities.transport_reason_code,
            "last_error": self.state.transport_error,
            "last_operation": (
                self.state.last_command_outcome.command_type
                if self.state.last_command_outcome is not None
                else None
            ),
            "last_good_reply": None,
            "transaction_count": 0,
        }

    def semantic_library(self, *, smoke_safe_only: bool = False) -> dict[str, object]:
        self._reload_tuning()
        actions = [
            item.model_dump(mode="json")
            for item in semantic_library_payload(self.semantic_tuning, smoke_safe_only=smoke_safe_only)
        ]
        return {
            "status": "ok",
            "detail": None,
            "transport_summary": self.transport_summary(),
            "semantic_actions": actions,
            "payload": {
                "semantic_actions": actions,
                "tuning_path": self._semantic_tuning_path,
                "teacher_review_path": self._teacher_review_path,
            },
        }

    def expression_catalog(self) -> dict[str, object]:
        self._reload_tuning()
        export = grounded_catalog_export().model_dump(mode="json")
        return {
            "status": "ok",
            "detail": None,
            "transport_summary": self.transport_summary(),
            "payload": {
                "catalog": export,
                "tuning_path": self._semantic_tuning_path,
                "teacher_review_path": self._teacher_review_path,
            },
        }

    def run_semantic_smoke(
        self,
        *,
        action: str = "look_left",
        intensity: float = 1.0,
        repeat_count: int = 1,
        note: str | None = None,
        allow_bench_actions: bool = False,
    ) -> dict[str, object]:
        self._reload_tuning()
        descriptor, command_type, payload = build_semantic_smoke_request(
            action,
            intensity=intensity,
            repeat_count=repeat_count,
            note=note,
            tuning_overrides=tuning_override_names(self.semantic_tuning),
            allow_bench_actions=allow_bench_actions,
        )
        if command_type == "safe_idle":
            state = self.safe_idle(str(payload.get("reason") or "operator_semantic_smoke"))
        else:
            state = self.apply_command(RobotCommand(command_type=command_type, payload=dict(payload)), dict(payload))
        return {
            "status": "ok" if state.last_command_outcome is None or state.last_command_outcome.accepted else "degraded",
            "detail": state.last_command_outcome.detail if state.last_command_outcome is not None else None,
            "action": descriptor.canonical_name,
            "body_state": state.model_dump(mode="json"),
            "latest_command_audit": (
                state.latest_command_audit.model_dump(mode="json")
                if state.latest_command_audit is not None
                else None
            ),
            "transport_summary": self.transport_summary(),
            "payload": {
                "action": descriptor.canonical_name,
                "family": descriptor.family,
                "smoke_safe": descriptor.smoke_safe,
                "rollout_stage": descriptor.rollout_stage,
                "tuning_path": self._semantic_tuning_path,
            },
        }

    def run_primitive_sequence(
        self,
        *,
        steps: list[dict[str, object]],
        note: str | None = None,
        sequence_name: str = "body_primitive_sequence",
    ) -> dict[str, object]:
        self._reload_tuning()
        compiled = self._compile_primitive_sequence_animation(sequence_name=sequence_name, steps=steps)
        before_readback = dict(self.state.feedback_positions)
        self._apply_preview_primitive_sequence(compiled)
        peak_targets = self._peak_targets_from_animation(compiled)
        outcome = BodyCommandOutcomeRecord(
            command_type="body_primitive_sequence",
            requested_action_name=sequence_name,
            canonical_action_name=sequence_name,
            source_action_name=sequence_name,
            outcome_status="preview_planned",
            accepted=True,
            transport_mode=self.state.transport_mode,
            reason_code="ok",
            detail=note,
            outcome_notes=list(compiled.compiler_notes),
            executed_frame_count=len(compiled.frames),
            executed_frame_names=[frame.frame_name or f"frame_{index}" for index, frame in enumerate(compiled.frames)],
            per_frame_duration_ms=[int(frame.duration_ms) for frame in compiled.frames],
            per_frame_hold_ms=[int(frame.hold_ms) for frame in compiled.frames],
            elapsed_wall_clock_ms=float(compiled.total_duration_ms),
            final_frame_name=compiled.frames[-1].frame_name if compiled.frames else None,
            peak_compiled_targets=peak_targets,
            peak_normalized_pose=self._peak_pose_from_animation(compiled),
            tuning_lane=compiled.tuning_lane or self.compiler.tuning.tuning_lane,
            kinetics_profiles_used=list(compiled.kinetics_profiles_used),
            grounding=compiled.grounding,
            recipe_name=compiled.recipe_name,
            primitive_steps=list(compiled.primitive_steps),
            sequence_step_count=compiled.sequence_step_count,
            returned_to_neutral=bool(compiled.returns_to_neutral),
            remaining_margin_percent_by_family=remaining_margin_percent_by_family(
                compiled_targets=peak_targets,
                profile=self.profile,
                calibration=self.calibration,
            ),
            clamp_reasons=extract_clamp_reasons(*compiled.compiler_notes),
            generated_at=utc_now(),
        )
        self.state.last_command_outcome = outcome
        self.state.latest_command_audit = self._build_command_audit(
            command=None,
            command_type="body_primitive_sequence",
            requested_action_name=sequence_name,
            compiled_targets=peak_targets,
            before_readback=before_readback,
            fallback_used=False,
            report_path=None,
        )
        self.state.updated_at = utc_now()
        return {
            "status": "ok",
            "detail": note,
            "sequence_name": sequence_name,
            "body_state": self.state.model_dump(mode="json"),
            "latest_command_audit": self.state.latest_command_audit.model_dump(mode="json"),
            "transport_summary": self.transport_summary(),
            "payload": {
                "sequence_name": sequence_name,
                "primitive_steps": list(compiled.primitive_steps),
                "sequence_step_count": compiled.sequence_step_count,
                "returned_to_neutral": bool(compiled.returns_to_neutral),
                "preview_only": True,
                "live_requested": False,
                "tuning_path": self._semantic_tuning_path,
            },
        }

    def run_staged_sequence(
        self,
        *,
        stages: list[dict[str, object]],
        note: str | None = None,
        sequence_name: str = "body_staged_sequence",
    ) -> dict[str, object]:
        self._reload_tuning()
        compiled = self._compile_staged_sequence_animation(sequence_name=sequence_name, stages=stages)
        before_readback = dict(self.state.feedback_positions)
        self._apply_preview_primitive_sequence(compiled)
        peak_targets = self._peak_targets_from_animation(compiled)
        outcome = BodyCommandOutcomeRecord(
            command_type="body_staged_sequence",
            requested_action_name=sequence_name,
            canonical_action_name=sequence_name,
            source_action_name=sequence_name,
            outcome_status="preview_planned",
            accepted=True,
            transport_mode=self.state.transport_mode,
            reason_code="ok",
            detail=note,
            outcome_notes=list(compiled.compiler_notes),
            executed_frame_count=len(compiled.frames),
            executed_frame_names=[frame.frame_name or f"frame_{index}" for index, frame in enumerate(compiled.frames)],
            per_frame_duration_ms=[int(frame.duration_ms) for frame in compiled.frames],
            per_frame_hold_ms=[int(frame.hold_ms) for frame in compiled.frames],
            elapsed_wall_clock_ms=float(compiled.total_duration_ms),
            final_frame_name=compiled.frames[-1].frame_name if compiled.frames else None,
            peak_compiled_targets=peak_targets,
            peak_normalized_pose=self._peak_pose_from_animation(compiled),
            tuning_lane=compiled.tuning_lane or self.compiler.tuning.tuning_lane,
            kinetics_profiles_used=list(compiled.kinetics_profiles_used),
            grounding=compiled.grounding,
            recipe_name=compiled.recipe_name,
            primitive_steps=list(compiled.primitive_steps),
            sequence_step_count=compiled.sequence_step_count,
            structural_action=compiled.structural_action,
            expressive_accents=list(compiled.expressive_accents),
            stage_count=compiled.stage_count,
            returned_to_neutral=bool(compiled.returns_to_neutral),
            remaining_margin_percent_by_family=remaining_margin_percent_by_family(
                compiled_targets=peak_targets,
                profile=self.profile,
                calibration=self.calibration,
            ),
            clamp_reasons=extract_clamp_reasons(*compiled.compiler_notes),
            generated_at=utc_now(),
        )
        self.state.last_command_outcome = outcome
        self.state.latest_command_audit = self._build_command_audit(
            command=None,
            command_type="body_staged_sequence",
            requested_action_name=sequence_name,
            compiled_targets=peak_targets,
            before_readback=before_readback,
            fallback_used=False,
            report_path=None,
        )
        self.state.updated_at = utc_now()
        return {
            "status": "ok",
            "detail": note,
            "sequence_name": sequence_name,
            "body_state": self.state.model_dump(mode="json"),
            "latest_command_audit": self.state.latest_command_audit.model_dump(mode="json"),
            "transport_summary": self.transport_summary(),
            "payload": {
                "sequence_name": sequence_name,
                "structural_action": compiled.structural_action,
                "expressive_accents": list(compiled.expressive_accents),
                "stage_count": compiled.stage_count,
                "returned_to_neutral": bool(compiled.returns_to_neutral),
                "preview_only": True,
                "live_requested": False,
                "tuning_path": self._semantic_tuning_path,
            },
        }

    def run_expressive_sequence(
        self,
        *,
        motif_name: str | None = None,
        steps: list[dict[str, object]] | None = None,
        note: str | None = None,
        sequence_name: str = "body_expressive_motif",
    ) -> dict[str, object]:
        self._reload_tuning()
        resolved_steps = list(steps or [])
        if motif_name is not None:
            motif = resolve_expressive_motif(motif_name)
            if motif is None:
                raise ValueError(f"unknown_expressive_motif:{motif_name}")
            if resolved_steps:
                raise ValueError("body_expressive_motif_disallows_steps_when_motif_name_provided")
            resolved_steps = [
                {
                    "step_kind": step.step_kind,
                    "action": step.action_name,
                    "intensity": step.intensity,
                    "release_groups": list(step.release_groups),
                    "move_ms": step.move_ms,
                    "hold_ms": step.hold_ms,
                    "note": step.note,
                }
                for step in motif.steps
            ]
        compiled = self._compile_expressive_motif_animation(
            sequence_name=sequence_name,
            motif_name=motif_name,
            steps=resolved_steps,
        )
        before_readback = dict(self.state.feedback_positions)
        self._apply_preview_primitive_sequence(compiled)
        peak_targets = self._peak_targets_from_animation(compiled)
        outcome = BodyCommandOutcomeRecord(
            command_type="body_expressive_motif",
            requested_action_name=sequence_name,
            canonical_action_name=sequence_name,
            source_action_name=sequence_name,
            outcome_status="preview_planned",
            accepted=True,
            transport_mode=self.state.transport_mode,
            reason_code="ok",
            detail=note,
            outcome_notes=list(compiled.compiler_notes),
            executed_frame_count=len(compiled.frames),
            executed_frame_names=[frame.frame_name or f"frame_{index}" for index, frame in enumerate(compiled.frames)],
            per_frame_duration_ms=[int(frame.duration_ms) for frame in compiled.frames],
            per_frame_hold_ms=[int(frame.hold_ms) for frame in compiled.frames],
            elapsed_wall_clock_ms=float(compiled.total_duration_ms),
            final_frame_name=compiled.frames[-1].frame_name if compiled.frames else None,
            peak_compiled_targets=peak_targets,
            peak_normalized_pose=self._peak_pose_from_animation(compiled),
            tuning_lane=compiled.tuning_lane or self.compiler.tuning.tuning_lane,
            kinetics_profiles_used=list(compiled.kinetics_profiles_used),
            grounding=compiled.grounding,
            recipe_name=compiled.recipe_name,
            motif_name=compiled.motif_name,
            primitive_steps=list(compiled.primitive_steps),
            expressive_steps=list(compiled.expressive_steps),
            step_kinds=list(compiled.step_kinds),
            sequence_step_count=compiled.sequence_step_count,
            structural_action=compiled.structural_action,
            expressive_accents=list(compiled.expressive_accents),
            stage_count=compiled.stage_count,
            returned_to_neutral=bool(compiled.returns_to_neutral),
            remaining_margin_percent_by_family=remaining_margin_percent_by_family(
                compiled_targets=peak_targets,
                profile=self.profile,
                calibration=self.calibration,
            ),
            clamp_reasons=extract_clamp_reasons(*compiled.compiler_notes),
            generated_at=utc_now(),
        )
        self.state.last_command_outcome = outcome
        self.state.latest_command_audit = self._build_command_audit(
            command=None,
            command_type="body_expressive_motif",
            requested_action_name=sequence_name,
            compiled_targets=peak_targets,
            before_readback=before_readback,
            fallback_used=False,
            report_path=None,
        )
        self.state.updated_at = utc_now()
        return {
            "status": "ok",
            "detail": note,
            "sequence_name": sequence_name,
            "body_state": self.state.model_dump(mode="json"),
            "latest_command_audit": self.state.latest_command_audit.model_dump(mode="json"),
            "transport_summary": self.transport_summary(),
            "payload": {
                "sequence_name": sequence_name,
                "motif_name": compiled.motif_name,
                "structural_action": compiled.structural_action,
                "expressive_steps": list(compiled.expressive_steps),
                "step_kinds": list(compiled.step_kinds),
                "sequence_step_count": compiled.sequence_step_count,
                "returned_to_neutral": bool(compiled.returns_to_neutral),
                "preview_only": True,
                "live_requested": False,
                "tuning_path": self._semantic_tuning_path,
            },
        }

    def run_range_demo(
        self,
        *,
        sequence_name: str | None = None,
        preset_name: str | None = None,
        note: str | None = None,
    ) -> dict[str, object]:
        plan = self._build_range_demo_plan(preset_name=preset_name, sequence_name=sequence_name)
        before_readback = dict(self.state.feedback_positions)
        self._apply_preview_range_demo(plan)
        outcome = BodyCommandOutcomeRecord(
            command_type="body_range_demo",
            requested_action_name=plan.sequence_name,
            canonical_action_name="body_range_demo",
            source_action_name=plan.sequence_name,
            outcome_status="preview_planned",
            accepted=True,
            transport_mode=self.state.transport_mode,
            reason_code="ok",
            detail=note,
            outcome_notes=[
                f"range_demo_sequence:{plan.sequence_name}",
                f"range_demo_preset:{plan.preset_name}",
                *plan.animation.compiler_notes,
            ],
            executed_frame_count=len(plan.animation.frames),
            executed_frame_names=[frame.frame_name or f"frame_{index}" for index, frame in enumerate(plan.animation.frames)],
            per_frame_duration_ms=[int(frame.duration_ms) for frame in plan.animation.frames],
            per_frame_hold_ms=[int(frame.hold_ms) for frame in plan.animation.frames],
            elapsed_wall_clock_ms=float(plan.animation.total_duration_ms),
            final_frame_name=plan.animation.frames[-1].frame_name,
            peak_compiled_targets=self._peak_targets_from_animation(plan.animation),
            peak_normalized_pose=self._peak_pose_from_animation(plan.animation),
            tuning_lane=plan.animation.tuning_lane or self.compiler.tuning.tuning_lane,
            kinetics_profiles_used=list(plan.animation.kinetics_profiles_used),
            remaining_margin_percent_by_family=remaining_margin_percent_by_family(
                compiled_targets=self._peak_targets_from_animation(plan.animation),
                profile=self.profile,
                calibration=self.calibration,
            ),
            clamp_reasons=extract_clamp_reasons(*plan.animation.compiler_notes),
            usable_range_audit=plan.usable_range_audit,
            generated_at=utc_now(),
        )
        self.state.last_command_outcome = outcome
        self.state.latest_command_audit = self._build_command_audit(
            command=None,
            command_type="body_range_demo",
            requested_action_name=plan.sequence_name,
            compiled_targets=outcome.peak_compiled_targets,
            before_readback=before_readback,
            fallback_used=False,
            report_path=None,
        )
        self.state.updated_at = utc_now()
        return {
            "status": "ok",
            "detail": note,
            "sequence_name": plan.sequence_name,
            "preset_name": plan.preset_name,
            "body_state": self.state.model_dump(mode="json"),
            "latest_command_audit": self.state.latest_command_audit.model_dump(mode="json"),
            "transport_summary": self.transport_summary(),
            "payload": {
                "sequence_name": plan.sequence_name,
                "preset_name": plan.preset_name,
                "range_demo": plan.to_payload(),
                "preview_only": True,
                "tuning_path": self._semantic_tuning_path,
                "available_presets": list(available_range_demo_presets()),
                "available_sequences": list(available_range_demo_sequences()),
            },
        }

    def run_power_preflight(self) -> dict[str, object]:
        self.state.power_health_classification = "healthy"
        self.state.preflight_passed = True
        self.state.preflight_failure_reason = None
        self.state.idle_voltage_snapshot = {}
        self.state.updated_at = utc_now()
        return {
            "status": "ok",
            "detail": "power_preflight_not_required",
            "body_state": self.state.model_dump(mode="json"),
            "latest_command_audit": None,
            "transport_summary": self.transport_summary(),
            "payload": {
                "power_health_classification": "healthy",
                "preflight_passed": True,
                "preflight_failure_reason": None,
                "idle_voltage_snapshot": {},
                "sample_count": 0,
            },
        }

    def safe_idle(self, reason: str) -> BodyState:
        self.state.safe_idle_active = True
        self.state.notes = [f"safe_idle:{reason}"]
        self.state = self.compiler.apply_expression(
            self.state,
            ExpressionRequest(expression_name="safe_idle", note=f"safe_idle:{reason}"),
        )
        self._record_outcome(
            command_type="safe_idle",
            requested_action_name="safe_idle",
            accepted=True,
            outcome_status="preview_applied",
        )
        self.state.updated_at = utc_now()
        self._sync_transport_status()
        return self.state.model_copy(deep=True)

    def apply_character_projection(
        self,
        *,
        intent: CharacterSemanticIntent,
        profile: CharacterProjectionProfile | None = None,
    ) -> BodyState:
        resolved_profile = profile or resolve_character_projection_profile(self.settings)
        avatar_enabled = projection_profile_supports_avatar(resolved_profile)
        robot_head_enabled = projection_profile_supports_robot_head(resolved_profile)
        self.capabilities.character_projection_profile = resolved_profile
        if resolved_profile == CharacterProjectionProfile.NO_BODY:
            self.state.character_projection = CharacterProjectionStatus(
                profile=resolved_profile,
                avatar_enabled=False,
                robot_head_enabled=False,
                robot_head_allowed=False,
                robot_head_applied=False,
                outcome="observe_only",
                blocked_reason=None,
                semantic_summary=intent.semantic_summary,
                intent=intent.model_copy(deep=True),
                notes=["projection_profile:no_body"],
            )
            self.state.updated_at = utc_now()
            self._sync_transport_status()
            return self.state.model_copy(deep=True)

        compiled = self._compile_character_projection(intent)
        self._apply_character_projection_preview(intent=intent, compiled=compiled)
        blocked_reason = "physical_head_unavailable" if robot_head_enabled else None
        self.state.character_projection = CharacterProjectionStatus(
            profile=resolved_profile,
            avatar_enabled=avatar_enabled,
            robot_head_enabled=robot_head_enabled,
            robot_head_allowed=False,
            robot_head_applied=False,
            outcome="projection_preview_only",
            blocked_reason=blocked_reason,
            semantic_summary=intent.semantic_summary,
            intent=intent.model_copy(deep=True),
            notes=[f"driver_mode:{self.state.driver_mode.value}", f"motion_hint:{intent.motion_hint}"],
        )
        self.state.last_command_outcome = BodyCommandOutcomeRecord(
            command_type="character_projection",
            requested_action_name=intent.surface_state,
            canonical_action_name=intent.expression_name,
            source_action_name=intent.semantic_summary or intent.surface_state,
            outcome_status="projection_preview_only",
            accepted=True,
            transport_mode=self.state.transport_mode,
            reason_code=self.state.transport_reason_code,
            detail=blocked_reason,
            outcome_notes=[intent.motion_hint, *(intent.source_signals or [])],
            generated_at=utc_now(),
        )
        self.state.updated_at = utc_now()
        self._sync_transport_status()
        return self.state.model_copy(deep=True)

    def apply_command(self, command: RobotCommand, payload: dict) -> BodyState:
        if command.command_type == "set_expression":
            expression_name = str(payload.get("expression_name") or payload.get("expression") or "neutral")
            self.state = self.compiler.apply_expression(
                self.state,
                ExpressionRequest(
                    expression_name=expression_name,
                    intensity=float(payload.get("intensity", 1.0)),
                    note=payload.get("note"),
                ),
            )
            self._record_outcome(command_type="set_expression", requested_action_name=expression_name)
        elif command.command_type == "set_gaze":
            target_name = payload.get("target")
            self.state = self.compiler.apply_gaze(
                self.state,
                request=GazeRequest(
                    target=target_name,
                    yaw=payload.get("yaw"),
                    pitch=payload.get("pitch"),
                    intensity=float(payload.get("intensity", 1.0)),
                    note=payload.get("note"),
                ),
            )
            self._record_outcome(command_type="set_gaze", requested_action_name=str(target_name) if target_name is not None else "custom")
        elif command.command_type == "perform_gesture":
            gesture_name = str(payload.get("gesture_name") or payload.get("gesture") or "blink")
            self.state = self.compiler.apply_gesture(
                self.state,
                GestureRequest(
                    gesture_name=gesture_name,
                    intensity=float(payload.get("intensity", 1.0)),
                    repeat_count=int(payload.get("repeat_count", 1)),
                    note=payload.get("note"),
                ),
            )
            self._record_outcome(command_type="perform_gesture", requested_action_name=gesture_name)
        elif command.command_type == "perform_animation":
            animation_name = str(payload.get("animation_name") or payload.get("animation") or "recover_neutral")
            self.state = self.compiler.apply_animation(
                self.state,
                AnimationRequest(
                    animation_name=animation_name,
                    intensity=float(payload.get("intensity", 1.0)),
                    repeat_count=int(payload.get("repeat_count", 1)),
                    loop=bool(payload.get("loop", False)),
                    note=payload.get("note"),
                ),
            )
            self._record_outcome(command_type="perform_animation", requested_action_name=animation_name)
        elif command.command_type == "set_head_pose":
            self.state = self.compiler.apply_legacy_head_pose(
                self.state,
                head_yaw_deg=float(payload.get("head_yaw_deg", 0.0)),
                head_pitch_deg=float(payload.get("head_pitch_deg", 0.0)),
            )
            self._record_outcome(command_type="set_head_pose", requested_action_name="legacy_head_pose")
        elif command.command_type == "safe_idle":
            return self.safe_idle(str(payload.get("reason", "safe_idle")))
        self.state.safe_idle_active = False
        self.state.updated_at = utc_now()
        self._sync_transport_status()
        return self.state.model_copy(deep=True)

    def _compile_character_projection(self, intent: CharacterSemanticIntent) -> CompiledAnimation:
        compiler_notes = [f"surface_state:{intent.surface_state}", f"motion_hint:{intent.motion_hint}"]
        if intent.animation_name:
            timeline = animation_timeline(
                intent.animation_name,
                anchor_pose=intent.pose,
                intensity=max(0.6, intent.warmth, intent.curiosity),
            )
            compiled = self.compiler.compile_timeline(timeline)
            compiled.compiler_notes.extend(compiler_notes)
            return compiled
        if intent.gesture_name:
            timeline = gesture_timeline(
                intent.gesture_name,
                anchor_pose=intent.pose,
                intensity=max(0.55, intent.curiosity),
            )
            compiled = self.compiler.compile_timeline(timeline)
            compiled.compiler_notes.extend(compiler_notes)
            return compiled
        frame = self.compiler.compile_frame(
            intent.pose,
            frame_name=f"character_projection:{intent.surface_state}",
            duration_ms=int(self.profile.default_transition_ms or 160),
            animation_name=intent.animation_name,
            semantic_name=intent.expression_name,
            source_name=intent.semantic_summary,
            previous_pose=self.state.pose,
        )
        return CompiledAnimation(
            animation_name=f"character_projection:{intent.surface_state}",
            frames=[frame],
            total_duration_ms=frame.duration_ms + frame.hold_ms,
            compiler_notes=compiler_notes,
        )

    def _apply_character_projection_preview(
        self,
        *,
        intent: CharacterSemanticIntent,
        compiled: CompiledAnimation,
    ) -> None:
        final_frame = compiled.frames[-1] if compiled.frames else self.compiler.compile_frame(self.compiler.neutral_pose())
        self.state.pose = final_frame.pose
        self.state.servo_targets = dict(final_frame.servo_targets)
        self.state.current_frame = final_frame
        self.state.compiled_animation = compiled
        self.state.virtual_preview = final_frame.preview
        self.state.active_expression = intent.expression_name
        self.state.attention_state = intent.surface_state
        self.state.gaze_target = intent.gaze_target
        self.state.last_gesture = intent.gesture_name
        self.state.last_animation = intent.animation_name
        self.state.clamp_notes = list(final_frame.preview.clamp_notes) if final_frame.preview is not None else []
        self.state.notes = [f"character_projection:{intent.surface_state}"]

    def close(self) -> None:
        return None

    def _build_capabilities(self) -> BodyCapabilityProfile:
        raise NotImplementedError

    def _sync_transport_status(self) -> None:
        self.capabilities.transport_mode = self.capabilities.transport_mode
        self.capabilities.transport_healthy = self.capabilities.transport_healthy
        self.capabilities.transport_error = self.capabilities.transport_error
        self.capabilities.transport_boundary_version = self.profile.transport_boundary_version
        self.capabilities.calibration_path = self._calibration_path()
        self.capabilities.calibration_version = self._calibration_version()
        self.capabilities.calibration_status = self._calibration_status()
        self.capabilities.live_motion_enabled = self._live_motion_enabled()
        self.state.transport_mode = self.capabilities.transport_mode
        self.state.transport_healthy = self.capabilities.transport_healthy
        self.state.transport_error = self.capabilities.transport_error
        self.state.transport_reason_code = self.capabilities.transport_reason_code
        self.state.transport_confirmed_live = self.capabilities.transport_confirmed_live
        self.state.transport_port = self.capabilities.transport_port
        self.state.transport_baud_rate = self.capabilities.transport_baud_rate
        self.state.connected = self.capabilities.connected
        self.state.calibration_path = self._calibration_path()
        self.state.calibration_version = self._calibration_version()
        self.state.calibration_status = self._calibration_status()
        self.state.live_motion_enabled = self._live_motion_enabled()

    def _base_capabilities(
        self,
        *,
        driver_mode: BodyDriverMode,
        present: bool,
        connected: bool,
        transport_mode: str,
        transport_healthy: bool,
        transport_error: str | None,
        supports_virtual_preview: bool,
        supports_serial_transport: bool,
        supports_readback: bool,
        notes: list[str],
    ) -> BodyCapabilityProfile:
        return BodyCapabilityProfile(
            driver_mode=driver_mode,
            character_projection_profile=resolve_character_projection_profile(self.settings),
            head_profile_name=self.profile.profile_name,
            head_profile_path=self.profile.source_path or self.settings.blink_head_profile,
            servo_family=self.profile.servo_family,
            servo_count=len([joint for joint in self.profile.joints if joint.enabled]),
            present=present,
            connected=connected,
            transport_mode=transport_mode,
            transport_healthy=transport_healthy,
            transport_error=transport_error,
            transport_reason_code="ok" if transport_healthy else None,
            transport_confirmed_live=transport_mode != LIVE_SERIAL_MODE,
            transport_port=None,
            transport_baud_rate=self.profile.baud_rate,
            transport_boundary_version=self.profile.transport_boundary_version,
            supports_expression=True,
            supports_gaze=True,
            supports_gesture=True,
            supports_animation=True,
            supports_virtual_preview=supports_virtual_preview,
            supports_serial_transport=supports_serial_transport,
            supports_readback=supports_readback,
            safe_idle_supported=True,
            calibration_path=self._calibration_path(),
            calibration_version=self._calibration_version(),
            calibration_status=self._calibration_status(),
            live_motion_enabled=self._live_motion_enabled(),
            supported_gaze_targets=list(SUPPORTED_GAZE_TARGETS),
            supported_expressions=list(SUPPORTED_EXPRESSIONS),
            supported_gestures=list(SUPPORTED_GESTURES),
            supported_animations=list(SUPPORTED_ANIMATIONS),
            notes=notes,
        )

    def _record_outcome(
        self,
        *,
        command_type: str,
        requested_action_name: str | None,
        accepted: bool = True,
        outcome_status: str = "preview_applied",
        rejected: bool = False,
        detail: str | None = None,
    ) -> None:
        preview = self.state.virtual_preview
        compiled = self.state.compiled_animation
        peak_targets = self._peak_targets_from_animation(compiled) if compiled is not None else {}
        remaining_margins = remaining_margin_percent_by_family(
            compiled_targets=peak_targets,
            profile=self.profile,
            calibration=self.calibration,
        )
        preview_notes = list(preview.outcome_notes) if preview is not None else []
        self.state.last_command_outcome = BodyCommandOutcomeRecord(
            command_type=command_type,
            requested_action_name=requested_action_name,
            canonical_action_name=preview.semantic_name if preview is not None else None,
            source_action_name=preview.source_name if preview is not None else requested_action_name,
            outcome_status=outcome_status,
            accepted=accepted,
            rejected=rejected,
            clamped=bool(self.state.clamp_notes),
            transport_mode=self.state.transport_mode,
            reason_code="ok" if accepted else self.state.transport_reason_code,
            detail=detail,
            outcome_notes=preview_notes,
            peak_compiled_targets=peak_targets,
            peak_normalized_pose=self._peak_pose_from_animation(compiled) if compiled is not None else {},
            tuning_lane=self.compiler.tuning.tuning_lane,
            kinetics_profiles_used=list(compiled.kinetics_profiles_used) if compiled is not None else [],
            grounding=compiled.grounding if compiled is not None else None,
            recipe_name=compiled.recipe_name if compiled is not None else None,
            motif_name=compiled.motif_name if compiled is not None else None,
            primitive_steps=list(compiled.primitive_steps) if compiled is not None else [],
            expressive_steps=list(compiled.expressive_steps) if compiled is not None else [],
            step_kinds=list(compiled.step_kinds) if compiled is not None else [],
            sequence_step_count=compiled.sequence_step_count if compiled is not None else None,
            structural_action=compiled.structural_action if compiled is not None else None,
            expressive_accents=list(compiled.expressive_accents) if compiled is not None else [],
            stage_count=compiled.stage_count if compiled is not None else None,
            returned_to_neutral=bool(compiled.returns_to_neutral) if compiled is not None else False,
            remaining_margin_percent_by_family=remaining_margins,
            clamp_reasons=extract_clamp_reasons(*preview_notes),
            generated_at=utc_now(),
        )

    def _build_range_demo_plan(self, *, preset_name: str | None, sequence_name: str | None = None):
        default_kinetics_name = self.compiler.tuning.default_kinetics_profile or "social_shift"
        default_kinetics = self.compiler.kinetics_profiles().get(default_kinetics_name)
        friendly = self.compiler.compile_frame(
            expression_pose("friendly", intensity=0.58, neutral_pose=self.compiler.neutral_pose()),
            frame_name="friendly_settle",
            animation_name=f"body_range_demo:{sequence_name or preset_name}",
            semantic_name="friendly",
            duration_ms=620,
            hold_ms=320,
        )
        friendly.compiler_notes.extend(
            [
                f"range_demo_sequence:{sequence_name or preset_name}",
                f"range_demo_preset:{preset_name or 'auto'}",
                "range_demo_friendly_settle",
            ]
        )
        return build_range_demo_plan(
            profile=self.profile,
            calibration=self.calibration,
            preset_name=preset_name,
            sequence_name=sequence_name,
            neutral_pose=self.compiler.neutral_pose(),
            friendly_frame=friendly,
            calibration_source_path=self._calibration_path(),
            tuning_lane=self.compiler.tuning.tuning_lane,
            default_kinetics_profile=default_kinetics_name,
            requested_speed=default_kinetics.speed if default_kinetics is not None else None,
            requested_acceleration=default_kinetics.acceleration if default_kinetics is not None else None,
        )

    def _compile_primitive_sequence_animation(
        self,
        *,
        sequence_name: str,
        steps: list[dict[str, object]],
    ) -> CompiledAnimation:
        normalized_steps: list[PrimitiveSequenceStepSpec] = []
        for step in steps:
            action = str(step.get("action") or "").strip()
            if not action:
                raise ValueError("body_primitive_sequence_step_requires_action")
            normalized_steps.append(
                PrimitiveSequenceStepSpec(
                    primitive_name=action,
                    intensity=float(step.get("intensity", 1.0) or 1.0),
                    note=str(step.get("note")) if step.get("note") is not None else None,
                )
            )
        return self.compiler.compile_primitive_sequence(
            sequence_name=sequence_name,
            steps=normalized_steps,
        )

    def _compile_staged_sequence_animation(
        self,
        *,
        sequence_name: str,
        stages: list[dict[str, object]],
    ) -> CompiledAnimation:
        normalized_stages: list[StagedSequenceStageSpec] = []
        for stage in stages:
            normalized_accents = tuple(
                StagedSequenceAccentSpec(
                    action_name=str(item.get("action") or "").strip(),
                    intensity=float(item.get("intensity", 1.0) or 1.0),
                    note=str(item.get("note")) if item.get("note") is not None else None,
                )
                for item in list(stage.get("accents") or [])
            )
            normalized_stages.append(
                StagedSequenceStageSpec(
                    stage_kind=str(stage.get("stage_kind") or "").strip(),
                    action_name=(
                        str(stage.get("action")).strip()
                        if stage.get("action") is not None
                        else None
                    ),
                    intensity=float(stage.get("intensity", 1.0) or 1.0),
                    move_ms=int(stage["move_ms"]) if stage.get("move_ms") is not None else None,
                    hold_ms=int(stage["hold_ms"]) if stage.get("hold_ms") is not None else None,
                    settle_ms=int(stage["settle_ms"]) if stage.get("settle_ms") is not None else None,
                    accents=normalized_accents,
                    note=str(stage.get("note")) if stage.get("note") is not None else None,
                )
            )
        return self.compiler.compile_staged_sequence(
            sequence_name=sequence_name,
            stages=normalized_stages,
        )

    def _compile_expressive_motif_animation(
        self,
        *,
        sequence_name: str,
        motif_name: str | None,
        steps: list[dict[str, object]],
    ) -> CompiledAnimation:
        normalized_steps: list[ExpressiveSequenceStepSpec] = []
        for step in steps:
            normalized_steps.append(
                ExpressiveSequenceStepSpec(
                    step_kind=str(step.get("step_kind") or "").strip(),
                    action_name=(
                        str(step.get("action")).strip()
                        if step.get("action") is not None
                        else None
                    ),
                    intensity=float(step.get("intensity", 1.0) or 1.0),
                    release_groups=tuple(str(item).strip() for item in list(step.get("release_groups") or [])),
                    move_ms=int(step["move_ms"]) if step.get("move_ms") is not None else None,
                    hold_ms=int(step["hold_ms"]) if step.get("hold_ms") is not None else None,
                    note=str(step.get("note")) if step.get("note") is not None else None,
                )
            )
        return self.compiler.compile_expressive_sequence(
            sequence_name=sequence_name,
            motif_name=motif_name,
            steps=normalized_steps,
        )

    def _apply_preview_primitive_sequence(self, compiled: CompiledAnimation) -> None:
        if not compiled.frames:
            return
        final_frame = compiled.frames[-1].model_copy(deep=True)
        self.state.safe_idle_active = False
        self.state.active_expression = "neutral"
        self.state.last_animation = compiled.animation_name
        self.state.pose = final_frame.pose.model_copy(deep=True)
        self.state.servo_targets = dict(final_frame.servo_targets)
        self.state.feedback_positions = dict(final_frame.servo_targets)
        self.state.compiled_animation = compiled.model_copy(deep=True)
        self.state.current_frame = final_frame
        self.state.virtual_preview = final_frame.preview

    def _apply_preview_range_demo(self, plan) -> None:
        final_frame = plan.animation.frames[-1].model_copy(deep=True)
        self.state.safe_idle_active = False
        self.state.active_expression = "neutral" if str(final_frame.frame_name).startswith("neutral") else "friendly"
        self.state.last_animation = plan.animation.animation_name
        self.state.pose = final_frame.pose.model_copy(deep=True)
        self.state.servo_targets = dict(final_frame.servo_targets)
        self.state.feedback_positions = dict(final_frame.servo_targets)
        self.state.compiled_animation = plan.animation.model_copy(deep=True)
        self.state.current_frame = final_frame
        self.state.virtual_preview = final_frame.preview

    def _peak_targets_from_animation(self, animation: CompiledAnimation) -> dict[str, int]:
        peak_targets: dict[str, int] = {}
        peak_distance: dict[str, int] = {}
        joint_profiles = {joint.joint_name: joint for joint in self.profile.joints}
        for frame in animation.frames:
            for joint_name, target in frame.servo_targets.items():
                joint = joint_profiles.get(joint_name)
                if joint is None:
                    continue
                neutral = int(self.calibration_joint_neutral(joint_name) or joint.neutral)
                distance = abs(int(target) - neutral)
                if distance >= peak_distance.get(joint_name, -1):
                    peak_distance[joint_name] = distance
                    peak_targets[joint_name] = int(target)
        return peak_targets

    def _peak_pose_from_animation(self, animation: CompiledAnimation) -> dict[str, float]:
        peaks: dict[str, float] = {}
        for field_name in ("head_pitch", "head_yaw", "head_roll"):
            best_value = 0.0
            best_abs = -1.0
            for frame in animation.frames:
                value = float(getattr(frame.pose, field_name, 0.0))
                if abs(value) >= best_abs:
                    best_value = value
                    best_abs = abs(value)
            peaks[field_name] = round(best_value, 4)
        return peaks

    def calibration_joint_neutral(self, joint_name: str) -> int | None:
        if self.calibration is None:
            return None
        for record in self.calibration.joint_records:
            if record.joint_name == joint_name:
                return int(record.neutral)
        return None

    def _build_command_audit(
        self,
        *,
        command: RobotCommand | None,
        command_type: str,
        requested_action_name: str | None,
        compiled_targets: dict[str, int],
        before_readback: dict[str, int],
        fallback_used: bool,
        report_path: str | None = None,
    ) -> BodyCommandAuditRecord:
        outcome = self.state.last_command_outcome
        return BodyCommandAuditRecord(
            command_id=command.command_id if command is not None else None,
            command_type=command_type,
            semantic_family=_semantic_family_for_command_type(command_type),
            requested_action_name=requested_action_name,
            canonical_action_name=outcome.canonical_action_name if outcome is not None else None,
            source_action_name=outcome.source_action_name if outcome is not None else requested_action_name,
            alias_used=bool(self.state.virtual_preview.alias_used) if self.state.virtual_preview is not None else False,
            alias_source_name=self.state.virtual_preview.alias_source_name if self.state.virtual_preview is not None else None,
            compiled_targets=dict((outcome.peak_compiled_targets if outcome is not None and outcome.peak_compiled_targets else compiled_targets)),
            clamped_joints=_extract_clamped_joints(self.state.clamp_notes),
            before_readback=before_readback,
            after_readback=dict(self.state.feedback_positions),
            transport_status=self.transport_summary(),
            health_summary=self._health_summary() if hasattr(self, "_health_summary") else {},
            outcome_status=outcome.outcome_status if outcome is not None else "unknown",
            reason_code=outcome.reason_code if outcome is not None else self.state.transport_reason_code,
            detail=outcome.detail if outcome is not None else self.state.transport_error,
            fallback_used=fallback_used,
            report_path=report_path,
            tuning_path=self._semantic_tuning_path,
            executed_frame_count=outcome.executed_frame_count if outcome is not None else None,
            executed_frame_names=list(outcome.executed_frame_names) if outcome is not None else [],
            per_frame_duration_ms=list(outcome.per_frame_duration_ms) if outcome is not None else [],
            per_frame_hold_ms=list(outcome.per_frame_hold_ms) if outcome is not None else [],
            elapsed_wall_clock_ms=outcome.elapsed_wall_clock_ms if outcome is not None else None,
            final_frame_name=outcome.final_frame_name if outcome is not None else None,
            peak_compiled_targets=dict(outcome.peak_compiled_targets) if outcome is not None else {},
            peak_normalized_pose=dict(outcome.peak_normalized_pose) if outcome is not None else {},
            tuning_lane=outcome.tuning_lane if outcome is not None else self.compiler.tuning.tuning_lane,
            kinetics_profiles_used=list(outcome.kinetics_profiles_used) if outcome is not None else [],
            grounding=outcome.grounding if outcome is not None else None,
            recipe_name=outcome.recipe_name if outcome is not None else None,
            motif_name=outcome.motif_name if outcome is not None else None,
            primitive_steps=list(outcome.primitive_steps) if outcome is not None else [],
            expressive_steps=list(outcome.expressive_steps) if outcome is not None else [],
            step_kinds=list(outcome.step_kinds) if outcome is not None else [],
            sequence_step_count=outcome.sequence_step_count if outcome is not None else None,
            structural_action=outcome.structural_action if outcome is not None else None,
            expressive_accents=list(outcome.expressive_accents) if outcome is not None else [],
            stage_count=outcome.stage_count if outcome is not None else None,
            returned_to_neutral=bool(outcome.returned_to_neutral) if outcome is not None else False,
            remaining_margin_percent_by_family=dict(outcome.remaining_margin_percent_by_family) if outcome is not None else {},
            clamp_reasons=list(outcome.clamp_reasons) if outcome is not None else [],
            fault_classification=outcome.fault_classification if outcome is not None else None,
            power_health_classification=outcome.power_health_classification if outcome is not None else None,
            suspect_voltage_event=bool(outcome.suspect_voltage_event) if outcome is not None else False,
            readback_implausible=bool(outcome.readback_implausible) if outcome is not None else False,
            confirmation_read_performed=bool(outcome.confirmation_read_performed) if outcome is not None else False,
            confirmation_result=outcome.confirmation_result if outcome is not None else None,
            preflight_passed=outcome.preflight_passed if outcome is not None else None,
            preflight_failure_reason=outcome.preflight_failure_reason if outcome is not None else None,
            idle_voltage_snapshot=dict(outcome.idle_voltage_snapshot) if outcome is not None else {},
            motion_control=(
                outcome.motion_control.model_copy(deep=True)
                if outcome is not None and outcome.motion_control is not None
                else None
            ),
            usable_range_audit=(
                outcome.usable_range_audit.model_copy(deep=True)
                if outcome is not None and outcome.usable_range_audit is not None
                else None
            ),
            notes=list(outcome.outcome_notes) if outcome is not None else [],
            generated_at=outcome.generated_at if outcome is not None else utc_now(),
        )

    def _calibration_path(self) -> str | None:
        return self.settings.blink_head_calibration or self.calibration.profile_path

    def _calibration_version(self) -> str | None:
        return self.calibration.schema_version if self.calibration is not None else None

    def _calibration_status(self) -> str | None:
        if self.calibration is None:
            return "missing"
        if self.calibration.calibration_kind == "template":
            return "template"
        return "loaded"

    def _live_motion_enabled(self) -> bool:
        return False


class BodylessDriver(BaseBodyDriver):
    def _build_capabilities(self) -> BodyCapabilityProfile:
        return self._base_capabilities(
            driver_mode=BodyDriverMode.BODYLESS,
            present=False,
            connected=False,
            transport_mode=BODYLESS_TRANSPORT_MODE,
            transport_healthy=True,
            transport_error=None,
            supports_virtual_preview=False,
            supports_serial_transport=False,
            supports_readback=False,
            notes=["Desktop bodyless mode keeps semantic embodiment commands routable without claiming a physical head is present."],
        )


class VirtualBodyDriver(BaseBodyDriver):
    def _build_capabilities(self) -> BodyCapabilityProfile:
        return self._base_capabilities(
            driver_mode=BodyDriverMode.VIRTUAL,
            present=True,
            connected=True,
            transport_mode=VIRTUAL_PREVIEW_TRANSPORT_MODE,
            transport_healthy=True,
            transport_error=None,
            supports_virtual_preview=True,
            supports_serial_transport=False,
            supports_readback=False,
            notes=["Virtual body preview is the primary current development path for the expressive robot head."],
        )


class SerialBodyDriver(BaseBodyDriver):
    def _setup_driver(self) -> None:
        self._requested_profile_path = Path(self.settings.blink_head_profile)
        self._configured_profile_exists = self._requested_profile_path.exists()
        self._runtime_transport_port = self.settings.blink_serial_port
        self._runtime_servo_baud = int(self.settings.blink_servo_baud)
        self._runtime_timeout_seconds = float(self.settings.blink_serial_timeout_seconds)
        self._serial_lock = RLock()
        self._command_audits: list[BodyCommandAuditRecord] = []
        self._motion_report_paths: list[str] = []
        self.transport = None
        self.bridge = None
        self._transport_init_error: str | None = None
        self._hydrate_runtime_transport_from_arm_lease()
        self._connect_transport()

    def close(self) -> None:
        with self._serial_lock:
            if self.transport is not None:
                self.transport.close()
            self.transport = None
            self.bridge = None

    def reset(self) -> None:
        with self._serial_lock:
            super().reset()
            self._sync_arm_state()
            if self.transport is not None and self.bridge is not None and self.transport.status.mode != LIVE_SERIAL_MODE:
                self._refresh_feedback_positions()
            self.refresh_live_status(force=True)

    def run_primitive_sequence(
        self,
        *,
        steps: list[dict[str, object]],
        note: str | None = None,
        sequence_name: str = "body_primitive_sequence",
    ) -> dict[str, object]:
        with self._serial_lock:
            self._reload_tuning()
            compiled = self._compile_primitive_sequence_animation(sequence_name=sequence_name, steps=steps)
            before_readback = dict(self.state.feedback_positions)
            self._apply_preview_primitive_sequence(compiled)

            try:
                transport, bridge = self._require_transport_available("body_primitive_sequence")
            except ServoTransportError as exc:
                return self._blocked_primitive_sequence_result(
                    compiled=compiled,
                    sequence_name=sequence_name,
                    note=note,
                    before_readback=before_readback,
                    classification=exc.classification,
                    detail=exc.detail,
                )

            live_requested = transport.status.mode == LIVE_SERIAL_MODE
            if live_requested:
                try:
                    confirm_live_transport(transport, self.profile)
                    self._require_runtime_motion_ready("body_primitive_sequence")
                except ServoTransportError as exc:
                    return self._blocked_primitive_sequence_result(
                        compiled=compiled,
                        sequence_name=sequence_name,
                        note=note,
                        before_readback=before_readback,
                        classification=exc.classification,
                        detail=exc.detail,
                    )

            outcome, health = bridge.apply_compiled_animation(compiled)
            self.state.last_command_outcome = outcome
            self._apply_health(health)
            self._record_audit(
                command=None,
                command_type="body_primitive_sequence",
                requested_action_name=sequence_name,
                compiled_targets=outcome.peak_compiled_targets or self._peak_targets_from_animation(compiled),
                before_readback=before_readback,
                fallback_used=False,
            )
            self.state.updated_at = utc_now()
            return {
                "status": "ok" if outcome.accepted else "degraded",
                "detail": note,
                "sequence_name": sequence_name,
                "body_state": self.state.model_dump(mode="json"),
                "latest_command_audit": (
                    self.state.latest_command_audit.model_dump(mode="json")
                    if self.state.latest_command_audit is not None
                    else None
                ),
                "transport_summary": self.transport_summary(),
                "payload": {
                    "sequence_name": sequence_name,
                    "primitive_steps": list(compiled.primitive_steps),
                    "sequence_step_count": compiled.sequence_step_count,
                    "returned_to_neutral": bool(compiled.returns_to_neutral),
                    "preview_only": False,
                    "live_requested": live_requested,
                    "tuning_path": self._semantic_tuning_path,
                },
            }

    def run_staged_sequence(
        self,
        *,
        stages: list[dict[str, object]],
        note: str | None = None,
        sequence_name: str = "body_staged_sequence",
    ) -> dict[str, object]:
        with self._serial_lock:
            self._reload_tuning()
            compiled = self._compile_staged_sequence_animation(sequence_name=sequence_name, stages=stages)
            before_readback = dict(self.state.feedback_positions)
            self._apply_preview_primitive_sequence(compiled)

            try:
                transport, bridge = self._require_transport_available("body_staged_sequence")
            except ServoTransportError as exc:
                return self._blocked_staged_sequence_result(
                    compiled=compiled,
                    sequence_name=sequence_name,
                    note=note,
                    before_readback=before_readback,
                    classification=exc.classification,
                    detail=exc.detail,
                )

            live_requested = transport.status.mode == LIVE_SERIAL_MODE
            if live_requested:
                try:
                    confirm_live_transport(transport, self.profile)
                    self._require_runtime_motion_ready("body_staged_sequence")
                except ServoTransportError as exc:
                    return self._blocked_staged_sequence_result(
                        compiled=compiled,
                        sequence_name=sequence_name,
                        note=note,
                        before_readback=before_readback,
                        classification=exc.classification,
                        detail=exc.detail,
                    )

            outcome, health = bridge.apply_compiled_animation(compiled)
            self.state.last_command_outcome = outcome
            self._apply_health(health)
            self._record_audit(
                command=None,
                command_type="body_staged_sequence",
                requested_action_name=sequence_name,
                compiled_targets=outcome.peak_compiled_targets or self._peak_targets_from_animation(compiled),
                before_readback=before_readback,
                fallback_used=False,
            )
            self.state.updated_at = utc_now()
            return {
                "status": "ok" if outcome.accepted else "degraded",
                "detail": note,
                "sequence_name": sequence_name,
                "body_state": self.state.model_dump(mode="json"),
                "latest_command_audit": (
                    self.state.latest_command_audit.model_dump(mode="json")
                    if self.state.latest_command_audit is not None
                    else None
                ),
                "transport_summary": self.transport_summary(),
                "payload": {
                    "sequence_name": sequence_name,
                    "structural_action": compiled.structural_action,
                    "expressive_accents": list(compiled.expressive_accents),
                    "stage_count": compiled.stage_count,
                    "returned_to_neutral": bool(compiled.returns_to_neutral),
                    "preview_only": False,
                    "live_requested": live_requested,
                    "tuning_path": self._semantic_tuning_path,
                },
            }

    def run_expressive_sequence(
        self,
        *,
        motif_name: str | None = None,
        steps: list[dict[str, object]] | None = None,
        note: str | None = None,
        sequence_name: str = "body_expressive_motif",
    ) -> dict[str, object]:
        with self._serial_lock:
            self._reload_tuning()
            resolved_steps = list(steps or [])
            if motif_name is not None:
                motif = resolve_expressive_motif(motif_name)
                if motif is None:
                    raise ValueError(f"unknown_expressive_motif:{motif_name}")
                if resolved_steps:
                    raise ValueError("body_expressive_motif_disallows_steps_when_motif_name_provided")
                resolved_steps = [
                    {
                        "step_kind": step.step_kind,
                        "action": step.action_name,
                        "intensity": step.intensity,
                        "release_groups": list(step.release_groups),
                        "move_ms": step.move_ms,
                        "hold_ms": step.hold_ms,
                        "note": step.note,
                    }
                    for step in motif.steps
                ]
            compiled = self._compile_expressive_motif_animation(
                sequence_name=sequence_name,
                motif_name=motif_name,
                steps=resolved_steps,
            )
            before_readback = dict(self.state.feedback_positions)
            self._apply_preview_primitive_sequence(compiled)

            try:
                transport, bridge = self._require_transport_available("body_expressive_motif")
            except ServoTransportError as exc:
                return self._blocked_expressive_sequence_result(
                    compiled=compiled,
                    sequence_name=sequence_name,
                    note=note,
                    before_readback=before_readback,
                    classification=exc.classification,
                    detail=exc.detail,
                )

            live_requested = transport.status.mode == LIVE_SERIAL_MODE
            if live_requested:
                try:
                    confirm_live_transport(transport, self.profile)
                    self._require_runtime_motion_ready("body_expressive_motif")
                except ServoTransportError as exc:
                    return self._blocked_expressive_sequence_result(
                        compiled=compiled,
                        sequence_name=sequence_name,
                        note=note,
                        before_readback=before_readback,
                        classification=exc.classification,
                        detail=exc.detail,
                    )

            outcome, health = bridge.apply_compiled_animation(compiled)
            self.state.last_command_outcome = outcome
            self._apply_health(health)
            self._record_audit(
                command=None,
                command_type="body_expressive_motif",
                requested_action_name=sequence_name,
                compiled_targets=outcome.peak_compiled_targets or self._peak_targets_from_animation(compiled),
                before_readback=before_readback,
                fallback_used=False,
            )
            self.state.updated_at = utc_now()
            return {
                "status": "ok" if outcome.accepted else "degraded",
                "detail": note,
                "sequence_name": sequence_name,
                "body_state": self.state.model_dump(mode="json"),
                "latest_command_audit": (
                    self.state.latest_command_audit.model_dump(mode="json")
                    if self.state.latest_command_audit is not None
                    else None
                ),
                "transport_summary": self.transport_summary(),
                "payload": {
                    "sequence_name": sequence_name,
                    "motif_name": compiled.motif_name,
                    "structural_action": compiled.structural_action,
                    "expressive_steps": list(compiled.expressive_steps),
                    "step_kinds": list(compiled.step_kinds),
                    "sequence_step_count": compiled.sequence_step_count,
                    "returned_to_neutral": bool(compiled.returns_to_neutral),
                    "preview_only": False,
                    "live_requested": live_requested,
                    "tuning_path": self._semantic_tuning_path,
                },
            }

    def connect(
        self,
        *,
        port: str | None = None,
        baud: int | None = None,
        timeout_seconds: float | None = None,
    ) -> dict[str, object]:
        with self._serial_lock:
            self._reload_calibration()
            if port is not None:
                self._runtime_transport_port = port
            if baud is not None:
                self._runtime_servo_baud = int(baud)
            if timeout_seconds is not None:
                self._runtime_timeout_seconds = float(timeout_seconds)
            self.close()
            self._connect_transport()
            self.refresh_live_status(force=True)
            return {
                "status": "connected" if self.state.transport_healthy else "degraded",
                "detail": self.state.transport_error,
                "transport_summary": self.transport_summary(),
                "available_ports": [item.to_dict() for item in list_serial_ports()],
            }

    def disconnect(self) -> dict[str, object]:
        with self._serial_lock:
            self.close()
            self._transport_init_error = "operator_disconnect"
            self._sync_transport_status(force_error=self._transport_init_error)
            self._sync_arm_state()
            self.state.updated_at = utc_now()
            return {
                "status": "disconnected",
                "detail": self._transport_init_error,
                "transport_summary": self.transport_summary(),
            }

    def refresh_live_status(self, *, force: bool = False) -> BodyState:
        with self._serial_lock:
            now = utc_now()
            if (
                not force
                and self.state.last_transport_poll_at is not None
                and (now - self.state.last_transport_poll_at).total_seconds() < SERIAL_REFRESH_INTERVAL_SECONDS
            ):
                return self.state.model_copy(deep=True)
            self._reload_calibration()
            hydrated_from_lease = self._hydrate_runtime_transport_from_arm_lease()
            if (
                (self.transport is None or self.bridge is None)
                and self._configured_transport_mode() == LIVE_SERIAL_MODE
                and self._runtime_transport_port
                and (
                    hydrated_from_lease
                    or (self._transport_init_error or "").startswith("missing_port:")
                )
            ):
                self._connect_transport()
            self._sync_arm_state()
            if self.transport is None or self.bridge is None:
                self._sync_transport_status(force_error=self._transport_init_error)
                self.state.last_transport_poll_at = now
                self.state.updated_at = now
                return self.state.model_copy(deep=True)
            try:
                if self.transport.status.mode == LIVE_SERIAL_MODE:
                    confirm_live_transport(self.transport, self.profile)
                self._refresh_feedback_positions()
                self._sync_transport_status()
            except (BodyCommandApplyError, ServoTransportError) as exc:
                detail = exc.detail if isinstance(exc, BodyCommandApplyError) else f"{exc.classification}:{exc.detail}"
                self._sync_transport_status(force_error=detail)
            self.state.last_transport_poll_at = now
            self.state.updated_at = now
            return self.state.model_copy(deep=True)

    def arm_live_motion(self, *, ttl_seconds: float = 60.0, author: str | None = None) -> dict[str, object]:
        with self._serial_lock:
            transport, _bridge = self._require_live_transport("arm_live_motion")
            self._require_saved_calibration("arm_live_motion")
            snapshot = read_bench_snapshot(transport, self._servo_ids())
            if any("error" in payload for payload in snapshot["positions"].values()) or any(
                "error" in payload for payload in snapshot["health"].values()
            ):
                raise ServoTransportError("transport_unconfirmed", "arm_live_motion_requires_stable_readback")
            lease = write_arm_lease(
                port=transport.status.port,
                baud_rate=transport.status.baud_rate,
                calibration_path=self._calibration_path() or self.settings.blink_head_calibration,
                ttl_seconds=ttl_seconds,
                path=DEFAULT_ARM_LEASE_PATH,
                author=author,
            )
            self._sync_arm_state()
            return {
                "status": "armed",
                "detail": None,
                "transport_summary": self.transport_summary(),
                "arm_status": {"armed": True, "lease": lease},
            }

    def disarm_live_motion(self) -> dict[str, object]:
        with self._serial_lock:
            payload = clear_arm_lease(DEFAULT_ARM_LEASE_PATH)
            self._sync_arm_state()
            return {
                "status": "disarmed",
                "detail": None,
                "transport_summary": self.transport_summary(),
                "arm_status": {"armed": False, "lease": None},
                "clear_result": payload,
            }

    def scan(self, *, ids: list[int] | None = None) -> dict[str, object]:
        with self._serial_lock:
            report = run_serial_doctor(
                profile_path=self.profile.source_path or self.settings.blink_head_profile,
                calibration_path=self.settings.blink_head_calibration,
                transport_mode=self._configured_transport_mode(),
                port=self._runtime_transport_port,
                explicit_baud=self._runtime_servo_baud,
                timeout_seconds=self._runtime_timeout_seconds,
                fixture_path=self.settings.blink_serial_fixture,
                ids=",".join(str(item) for item in (ids or [])) or None,
                auto_scan_baud=bool(self.settings.blink_servo_autoscan),
                report_path=DEFAULT_BRINGUP_REPORT_PATH,
            )
            self.refresh_live_status(force=True)
            return report

    def ping(self, *, ids: list[int] | None = None) -> dict[str, object]:
        with self._serial_lock:
            transport, _bridge = self._require_transport_available("ping")
            requested_ids = ids or self._servo_ids()
            responsive_ids: list[int] = []
            ping_results: dict[int, dict[str, object]] = {}
            for servo_id in requested_ids:
                try:
                    transport.ping(servo_id)
                except ServoTransportError as exc:
                    ping_results[servo_id] = {"ok": False, "error": f"{exc.classification}:{exc.detail}"}
                else:
                    ping_results[servo_id] = {"ok": True}
                    responsive_ids.append(servo_id)
            self.refresh_live_status(force=True)
            return {
                "requested_ids": requested_ids,
                "responsive_ids": responsive_ids,
                "ping_results": ping_results,
                "transport_summary": self.transport_summary(),
                "request_response_history": transport.history_payload(),
            }

    def read_health(self, *, ids: list[int] | None = None) -> dict[str, object]:
        with self._serial_lock:
            transport, _bridge = self._require_transport_available("read_health")
            requested_ids = ids or self._servo_ids()
            bench_health = read_bench_health_many(transport, requested_ids)
            self.refresh_live_status(force=True)
            return {
                "requested_ids": requested_ids,
                "health_reads": bench_health,
                "servo_health": self._health_summary(),
                "transport_summary": self.transport_summary(),
                "request_response_history": transport.history_payload(),
            }

    def write_neutral(self, *, author: str | None = None) -> dict[str, object]:
        with self._serial_lock:
            transport, bridge = self._require_live_transport("write_neutral")
            self._require_runtime_motion_ready("write_neutral")
            resolved_targets = neutral_targets(self.calibration, self.profile)
            report = execute_bench_command(
                transport=transport,
                bridge=bridge,
                profile=self.profile,
                calibration=self.calibration,
                command_family="write_neutral",
                requested_targets=resolved_targets,
                resolved_targets=resolved_targets,
                duration_ms=max(int(self.profile.neutral_recovery_ms or 220), int(self.profile.minimum_transition_ms or 80)),
                report_dir=DEFAULT_MOTION_REPORT_DIR,
                author=author,
            )
            self._remember_motion_report(report.get("report_path"))
            self.refresh_live_status(force=True)
            self._record_manual_audit(command_type="write_neutral", requested_action_name="write_neutral", report=report)
            return report

    def servo_lab_catalog(self) -> dict[str, object]:
        with self._serial_lock:
            self._reload_calibration()
            transport = self.transport
            current_positions: dict[str, int] = {}
            readback_errors: dict[str, str] = {}
            if transport is not None:
                current_positions, readback_errors = self._servo_lab_read_positions(transport)
            else:
                readback_errors = {
                    joint.joint_name: "transport_unavailable"
                    for joint in self.profile.joints
                    if joint.enabled
                }
            catalog = build_servo_lab_catalog(
                profile=self.profile,
                calibration=self.calibration,
                current_positions=current_positions,
                readback_errors=readback_errors,
                transport=transport,
                calibration_path=self._calibration_path(),
            )
            return {
                "status": "degraded" if readback_errors else "ok",
                "detail": self.state.transport_error if transport is None else None,
                "transport_summary": self.transport_summary(),
                "payload": catalog.to_payload(),
            }

    def servo_lab_readback(
        self,
        *,
        joint_name: str | None = None,
        include_health: bool = True,
    ) -> dict[str, object]:
        with self._serial_lock:
            transport, _bridge = self._require_transport_available("servo_lab_readback")
            self._reload_calibration()
            current_positions, readback_errors = self._servo_lab_read_positions(transport, joint_name=joint_name)
            catalog = build_servo_lab_catalog(
                profile=self.profile,
                calibration=self.calibration,
                current_positions=current_positions,
                readback_errors=readback_errors,
                transport=transport,
                calibration_path=self._calibration_path(),
            )
            health_reads = self._servo_lab_health_reads(transport, joint_name=joint_name) if include_health else {}
            self.refresh_live_status(force=True)
            return {
                "status": "degraded" if readback_errors else "ok",
                "detail": next(iter(readback_errors.values()), None),
                "transport_summary": self.transport_summary(),
                "payload": readback_payload(
                    catalog=catalog,
                    selected_joint_name=joint_name,
                    include_health=include_health,
                    health_reads=health_reads,
                ),
            }

    def servo_lab_move(
        self,
        *,
        joint_name: str,
        reference_mode: str,
        target_raw: int | None = None,
        delta_counts: int | None = None,
        lab_min: int | None = None,
        lab_max: int | None = None,
        duration_ms: int = 600,
        speed_override: int | None = None,
        acceleration_override: int | None = None,
        note: str | None = None,
    ) -> dict[str, object]:
        with self._serial_lock:
            self._reload_calibration()
            transport, bridge = self._require_transport_available("servo_lab_move")
            if transport.status.mode == LIVE_SERIAL_MODE:
                confirm_live_transport(transport, self.profile)
                self._require_runtime_motion_ready("servo_lab_move")
            current_position = self._servo_lab_read_current_position(transport, joint_name)
            try:
                move_plan = resolve_servo_lab_move(
                    profile=self.profile,
                    calibration=self.calibration,
                    joint_name=joint_name,
                    reference_mode=reference_mode,
                    target_raw=target_raw,
                    delta_counts=delta_counts,
                    current_position=current_position,
                    lab_min=lab_min,
                    lab_max=lab_max,
                )
            except ServoLabError as exc:
                raise ServoTransportError(exc.code, exc.detail) from exc

            report = execute_bench_command(
                transport=transport,
                bridge=bridge,
                profile=self.profile,
                calibration=self.calibration,
                command_family="servo_lab_move",
                requested_targets={joint_name: move_plan.requested_target},
                resolved_targets={joint_name: move_plan.effective_target},
                duration_ms=int(duration_ms),
                speed_override=speed_override,
                acceleration_override=acceleration_override,
                report_dir=DEFAULT_MOTION_REPORT_DIR,
                author=note,
            )
            self._remember_motion_report(report.get("report_path"))
            self.refresh_live_status(force=True)
            self._record_manual_audit(command_type="servo_lab_move", requested_action_name=joint_name, report=report)
            outcome = BodyCommandOutcomeRecord.model_validate(report.get("outcome") or {})
            capabilities = servo_lab_capabilities(transport)
            report["operation"] = "servo_lab_move"
            report["servo_lab_move"] = move_plan.to_payload()
            report["motion_control_summary"] = motion_control_payload(
                outcome.motion_control,
                acceleration_supported=capabilities.acceleration_supported,
                acceleration_status=capabilities.acceleration_status,
            )
            report["capabilities"] = capabilities.to_payload()
            return report

    def servo_lab_sweep(
        self,
        *,
        joint_name: str,
        lab_min: int | None = None,
        lab_max: int | None = None,
        cycles: int = 1,
        duration_ms: int = 600,
        dwell_ms: int = 250,
        speed_override: int | None = None,
        acceleration_override: int | None = None,
        return_to_neutral: bool = True,
        note: str | None = None,
    ) -> dict[str, object]:
        with self._serial_lock:
            self._reload_calibration()
            transport, bridge = self._require_transport_available("servo_lab_sweep")
            if transport.status.mode == LIVE_SERIAL_MODE:
                confirm_live_transport(transport, self.profile)
                self._require_runtime_motion_ready("servo_lab_sweep")
            current_position = self._servo_lab_read_current_position(transport, joint_name)
            try:
                sweep_plan = resolve_servo_lab_sweep(
                    profile=self.profile,
                    calibration=self.calibration,
                    joint_name=joint_name,
                    current_position=current_position,
                    lab_min=lab_min,
                    lab_max=lab_max,
                    cycles=cycles,
                    duration_ms=duration_ms,
                    dwell_ms=dwell_ms,
                    return_to_neutral=return_to_neutral,
                )
            except ServoLabError as exc:
                raise ServoTransportError(exc.code, exc.detail) from exc

            report = execute_servo_lab_sweep(
                transport=transport,
                bridge=bridge,
                profile=self.profile,
                calibration=self.calibration,
                joint_name=joint_name,
                requested_targets={joint_name: current_position if current_position is not None else sweep_plan.bounds.neutral},
                sweep_plan=sweep_plan.to_payload(),
                speed_override=speed_override,
                acceleration_override=acceleration_override,
                report_dir=DEFAULT_MOTION_REPORT_DIR,
                author=note,
            )
            self._remember_motion_report(report.get("report_path"))
            self.refresh_live_status(force=True)
            self._record_manual_audit(command_type="servo_lab_sweep", requested_action_name=joint_name, report=report)
            outcome = BodyCommandOutcomeRecord.model_validate(report.get("outcome") or {})
            capabilities = servo_lab_capabilities(transport)
            report["operation"] = "servo_lab_sweep"
            report["servo_lab_sweep"] = sweep_plan.to_payload()
            report["motion_control_summary"] = motion_control_payload(
                outcome.motion_control,
                acceleration_supported=capabilities.acceleration_supported,
                acceleration_status=capabilities.acceleration_status,
            )
            report["capabilities"] = capabilities.to_payload()
            return report

    def servo_lab_save_calibration(
        self,
        *,
        joint_name: str,
        save_current_as_neutral: bool = False,
        raw_min: int | None = None,
        raw_max: int | None = None,
        confirm_mirrored: bool | None = None,
        note: str | None = None,
    ) -> dict[str, object]:
        with self._serial_lock:
            self._reload_calibration()
            if self.calibration.calibration_kind == "template":
                raise ServoTransportError("calibration_template", "servo_lab_save_calibration_requires_saved_calibration")
            current_position: int | None = None
            if save_current_as_neutral:
                transport, _bridge = self._require_transport_available("servo_lab_save_calibration")
                current_position = self._servo_lab_read_current_position(transport, joint_name)
            output_path = self._calibration_path() or self.settings.blink_head_calibration
            try:
                updated, update = save_servo_lab_calibration(
                    profile=self.profile,
                    calibration=self.calibration,
                    joint_name=joint_name,
                    output_path=output_path,
                    current_position=current_position,
                    save_current_as_neutral=save_current_as_neutral,
                    raw_min=raw_min,
                    raw_max=raw_max,
                    confirm_mirrored=confirm_mirrored,
                )
            except ServoLabError as exc:
                raise ServoTransportError(exc.code, exc.detail) from exc

            _save_head_calibration(updated, output_path)
            self.calibration = updated
            self._reload_tuning()
            self.refresh_live_status(force=True)
            self.state.last_command_outcome = BodyCommandOutcomeRecord(
                command_type="servo_lab_save_calibration",
                requested_action_name=joint_name,
                canonical_action_name="servo_lab_save_calibration",
                source_action_name=joint_name,
                outcome_status="calibration_updated",
                accepted=True,
                transport_mode=self.state.transport_mode,
                reason_code="ok",
                detail=note,
                outcome_notes=[f"servo_lab_save_calibration:{joint_name}"],
            )
            self.state.updated_at = utc_now()
            return {
                "status": "ok",
                "detail": note,
                "transport_summary": self.transport_summary(),
                "payload": {
                    "calibration_update": update.to_payload(),
                    "output_path": output_path,
                },
            }

    def semantic_library(self, *, smoke_safe_only: bool = False) -> dict[str, object]:
        self._reload_tuning()
        actions = [
            item.model_dump(mode="json")
            for item in semantic_library_payload(self.semantic_tuning, smoke_safe_only=smoke_safe_only)
        ]
        return {
            "status": "ok",
            "detail": None,
            "transport_summary": self.transport_summary(),
            "semantic_actions": actions,
            "payload": {
                "semantic_actions": actions,
                "tuning_path": self._semantic_tuning_path,
                "teacher_review_path": self._teacher_review_path,
            },
        }

    def expression_catalog(self) -> dict[str, object]:
        self._reload_tuning()
        export = grounded_catalog_export().model_dump(mode="json")
        return {
            "status": "ok",
            "detail": None,
            "transport_summary": self.transport_summary(),
            "payload": {
                "catalog": export,
                "tuning_path": self._semantic_tuning_path,
                "teacher_review_path": self._teacher_review_path,
            },
        }

    def run_semantic_smoke(
        self,
        *,
        action: str = "look_left",
        intensity: float = 1.0,
        repeat_count: int = 1,
        note: str | None = None,
        allow_bench_actions: bool = False,
    ) -> dict[str, object]:
        self._reload_tuning()
        try:
            descriptor, command_type, payload = build_semantic_smoke_request(
                action,
                intensity=intensity,
                repeat_count=repeat_count,
                note=note,
                tuning_overrides=tuning_override_names(self.semantic_tuning),
                allow_bench_actions=allow_bench_actions,
            )
        except ValueError as exc:
            raise ServoTransportError("out_of_range", str(exc)) from exc
        if command_type == "safe_idle":
            state = self.safe_idle(str(payload.get("reason") or "operator_semantic_smoke"))
        else:
            state = self.apply_command(RobotCommand(command_type=command_type, payload=dict(payload)), dict(payload))
        return {
            "status": "ok" if state.last_command_outcome is None or state.last_command_outcome.accepted else "degraded",
            "detail": state.last_command_outcome.detail if state.last_command_outcome is not None else None,
            "action": descriptor.canonical_name,
            "body_state": state.model_dump(mode="json"),
            "latest_command_audit": state.latest_command_audit.model_dump(mode="json") if state.latest_command_audit is not None else None,
            "transport_summary": self.transport_summary(),
            "payload": {
                "action": descriptor.canonical_name,
                "family": descriptor.family,
                "smoke_safe": descriptor.smoke_safe,
                "rollout_stage": descriptor.rollout_stage,
                "tuning_path": self._semantic_tuning_path,
            },
        }

    def run_range_demo(
        self,
        *,
        sequence_name: str | None = None,
        preset_name: str | None = None,
        note: str | None = None,
    ) -> dict[str, object]:
        with self._serial_lock:
            self._reload_tuning()
            plan = self._build_range_demo_plan(preset_name=preset_name, sequence_name=sequence_name)
            before_readback = dict(self.state.feedback_positions)
            self._apply_preview_range_demo(plan)

            try:
                transport, bridge = self._require_transport_available("body_range_demo")
            except ServoTransportError as exc:
                return self._blocked_range_demo_result(
                    sequence_name=plan.sequence_name,
                    preset_name=plan.preset_name,
                    note=note,
                    plan=plan,
                    before_readback=before_readback,
                    classification=exc.classification,
                    detail=exc.detail,
                )

            live_requested = transport.status.mode == LIVE_SERIAL_MODE
            if live_requested:
                try:
                    confirm_live_transport(transport, self.profile)
                    self._require_runtime_motion_ready("body_range_demo")
                except ServoTransportError as exc:
                    return self._blocked_range_demo_result(
                        sequence_name=plan.sequence_name,
                        preset_name=plan.preset_name,
                        note=note,
                        plan=plan,
                        before_readback=before_readback,
                        classification=exc.classification,
                        detail=exc.detail,
                    )

            outcome, health = bridge.apply_compiled_animation(plan.animation)
            self.state.last_command_outcome = outcome
            self._apply_health(health)
            self._record_audit(
                command=None,
                command_type="body_range_demo",
                requested_action_name=plan.sequence_name,
                compiled_targets=outcome.peak_compiled_targets or self._peak_targets_from_animation(plan.animation),
                before_readback=before_readback,
                fallback_used=False,
            )
            self.state.updated_at = utc_now()
            return {
                "status": "ok" if outcome.accepted else "degraded",
                "detail": note,
                "sequence_name": plan.sequence_name,
                "preset_name": plan.preset_name,
                "body_state": self.state.model_dump(mode="json"),
                "latest_command_audit": (
                    self.state.latest_command_audit.model_dump(mode="json")
                    if self.state.latest_command_audit is not None
                    else None
                ),
                "transport_summary": self.transport_summary(),
                "payload": {
                    "sequence_name": plan.sequence_name,
                    "preset_name": plan.preset_name,
                    "range_demo": plan.to_payload(),
                    "preview_only": transport.status.mode != LIVE_SERIAL_MODE,
                    "live_requested": live_requested,
                    "tuning_path": self._semantic_tuning_path,
                    "available_presets": list(available_range_demo_presets()),
                    "available_sequences": list(available_range_demo_sequences()),
                },
            }

    def run_power_preflight(self) -> dict[str, object]:
        with self._serial_lock:
            self._reload_calibration()
            try:
                transport, bridge = self._require_transport_available("body_power_preflight")
            except ServoTransportError as exc:
                return {
                    "status": "blocked",
                    "detail": exc.detail,
                    "body_state": self.state.model_dump(mode="json"),
                    "latest_command_audit": (
                        self.state.latest_command_audit.model_dump(mode="json")
                        if self.state.latest_command_audit is not None
                        else None
                    ),
                    "transport_summary": self.transport_summary(),
                    "payload": {
                        "power_health_classification": "suspect_power",
                        "preflight_passed": False,
                        "preflight_failure_reason": exc.detail,
                        "idle_voltage_snapshot": {},
                        "sample_count": 0,
                    },
                }

            try:
                outcome, health = bridge.run_live_power_preflight()
            except ServoTransportError as exc:
                detail = f"{exc.classification}:{exc.detail}"
                self._sync_transport_status(force_error=detail)
                self.state.power_health_classification = "suspect_power"
                self.state.preflight_passed = False
                self.state.preflight_failure_reason = detail
                self.state.idle_voltage_snapshot = {}
                self.state.updated_at = utc_now()
                return {
                    "status": "blocked",
                    "detail": detail,
                    "body_state": self.state.model_dump(mode="json"),
                    "latest_command_audit": (
                        self.state.latest_command_audit.model_dump(mode="json")
                        if self.state.latest_command_audit is not None
                        else None
                    ),
                    "transport_summary": self.transport_summary(),
                    "payload": {
                        "power_health_classification": "suspect_power",
                        "preflight_passed": False,
                        "preflight_failure_reason": detail,
                        "idle_voltage_snapshot": {},
                        "sample_count": 0,
                    },
                }

            before_readback = {
                joint_name: int(record.current_position)
                for joint_name, record in health.items()
                if record.current_position is not None
            }
            self.state.last_command_outcome = outcome
            self._apply_health(health)
            self.state.power_health_classification = outcome.power_health_classification
            self.state.preflight_passed = outcome.preflight_passed
            self.state.preflight_failure_reason = outcome.preflight_failure_reason
            self.state.idle_voltage_snapshot = dict(outcome.idle_voltage_snapshot)
            self._record_audit(
                command=None,
                command_type="body_power_preflight",
                requested_action_name="live_power_preflight",
                compiled_targets={},
                before_readback=before_readback,
                fallback_used=not bool(outcome.preflight_passed),
            )
            self.state.updated_at = utc_now()
            return {
                "status": "ok" if outcome.preflight_passed else "blocked",
                "detail": outcome.preflight_failure_reason,
                "body_state": self.state.model_dump(mode="json"),
                "latest_command_audit": (
                    self.state.latest_command_audit.model_dump(mode="json")
                    if self.state.latest_command_audit is not None
                    else None
                ),
                "transport_summary": self.transport_summary(),
                "payload": {
                    "power_health_classification": outcome.power_health_classification,
                    "preflight_passed": outcome.preflight_passed,
                    "preflight_failure_reason": outcome.preflight_failure_reason,
                    "idle_voltage_snapshot": dict(outcome.idle_voltage_snapshot),
                    "sample_count": 2,
                },
            }

    def record_teacher_review(
        self,
        *,
        action: str,
        review: str,
        note: str | None = None,
        proposed_tuning_delta: dict[str, object] | None = None,
        apply_tuning: bool = False,
    ) -> dict[str, object]:
        result = record_teacher_review(
            action=action,
            review=review,
            note=note,
            proposed_tuning_delta=proposed_tuning_delta,
            apply_tuning=apply_tuning,
            latest_command_audit=self.state.latest_command_audit,
            tuning_path=self._semantic_tuning_path,
            reviews_path=self._teacher_review_path,
            profile_name=self.profile.profile_name,
            calibration_path=self._calibration_path() or self.settings.blink_head_calibration,
        )
        self._reload_tuning()
        return {
            "status": "ok",
            "detail": None,
            "transport_summary": self.transport_summary(),
            "payload": {
                "review": result["review"].model_dump(mode="json"),
                "descriptor": result["descriptor"].model_dump(mode="json"),
                "tuning": result["tuning"].model_dump(mode="json"),
                "tuning_path": self._semantic_tuning_path,
                "teacher_review_path": self._teacher_review_path,
            },
        }

    def transport_summary(self) -> dict[str, object]:
        if self.transport is not None:
            return bench_transport_summary(self.transport)
        return {
            "mode": self._configured_transport_mode(),
            "port": self._runtime_transport_port,
            "baud_rate": self._runtime_servo_baud,
            "timeout_seconds": self._runtime_timeout_seconds,
            "healthy": False,
            "confirmed_live": False,
            "reason_code": "transport_unconfirmed",
            "last_error": self._transport_init_error,
            "last_operation": None,
            "last_good_reply": None,
            "transaction_count": 0,
        }

    def body_command_audits(self) -> list[BodyCommandAuditRecord]:
        return [item.model_copy(deep=True) for item in self._command_audits]

    def motion_report_index(self) -> list[dict[str, object]]:
        return build_motion_report_index(self._motion_report_paths)

    def request_response_history(self) -> list[dict[str, object]]:
        return collect_request_response_history(
            motion_reports=load_motion_reports(self._motion_report_paths),
            current_history=self.transport.history_payload() if self.transport is not None else None,
        )

    def serial_failure_summary(self) -> dict[str, object]:
        return build_serial_failure_summary(
            motion_reports=load_motion_reports(self._motion_report_paths),
            body_state=self.state,
        ).model_dump(mode="json")

    def semantic_tuning_snapshot(self) -> dict[str, object]:
        self._reload_tuning()
        return {
            **self.semantic_tuning.model_dump(mode="json"),
            "derived_operating_band": self.compiler.operating_band().model_dump(mode="json"),
            "resolved_kinetics_profiles": {
                name: profile.model_dump(mode="json")
                for name, profile in self.compiler.kinetics_profiles().items()
            },
        }

    def teacher_reviews(self) -> list[dict[str, object]]:
        path = Path(self._teacher_review_path)
        if not path.exists():
            return []
        items: list[dict[str, object]] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            items.append(json.loads(line))
        return items

    def safe_idle(self, reason: str) -> BodyState:
        with self._serial_lock:
            before_readback = dict(self.state.feedback_positions)
            super().safe_idle(reason)
            try:
                if self.transport is None or self.bridge is None:
                    raise BodyCommandApplyError("transport_unavailable", self._transport_init_error or "serial_transport_not_available")
                neutral_frame = self.compiler.compile_frame(
                    self.compiler.neutral_pose(),
                    frame_name="neutral_safe_idle",
                    duration_ms=600,
                    animation_name="recover_neutral",
                )
                outcome, health = self.bridge.safe_idle(
                    torque_off=bool(self.profile.safe_idle_torque_off),
                    neutral_frame=neutral_frame,
                )
                self.state.last_command_outcome = outcome
                self._apply_health(health)
            except (ServoTransportError, BodyCommandApplyError) as exc:
                detail = exc.detail if isinstance(exc, BodyCommandApplyError) else f"{exc.classification}:{exc.detail}"
                self.state.transport_error = detail
                self.state.notes.append(f"safe_idle_transport_warning:{detail}")
                self.state.last_command_outcome = BodyCommandOutcomeRecord(
                    command_type="safe_idle",
                    requested_action_name="safe_idle",
                    canonical_action_name="safe_idle",
                    source_action_name="safe_idle",
                    outcome_status="transport_warning",
                    accepted=False,
                    rejected=True,
                    transport_mode=self.state.transport_mode,
                    reason_code=self.state.transport_reason_code,
                    detail=detail,
                    outcome_notes=list(self.state.virtual_preview.outcome_notes) if self.state.virtual_preview is not None else [],
                    generated_at=utc_now(),
                )
            self._sync_transport_status(force_error=self.state.transport_error)
            self._sync_arm_state()
            self._record_audit(
                command=None,
                command_type="safe_idle",
                requested_action_name="safe_idle",
                compiled_targets=self.state.servo_targets,
                before_readback=before_readback,
                fallback_used=False,
            )
            self.state.updated_at = utc_now()
            return self.state.model_copy(deep=True)

    def apply_character_projection(
        self,
        *,
        intent: CharacterSemanticIntent,
        profile: CharacterProjectionProfile | None = None,
    ) -> BodyState:
        with self._serial_lock:
            resolved_profile = profile or resolve_character_projection_profile(self.settings)
            robot_head_enabled = projection_profile_supports_robot_head(resolved_profile)
            self.capabilities.character_projection_profile = resolved_profile
            blocked_reason = self._projection_block_reason() if robot_head_enabled else None

            if resolved_profile == CharacterProjectionProfile.NO_BODY:
                return super().apply_character_projection(intent=intent, profile=resolved_profile)

            if intent.safe_idle_requested and robot_head_enabled and blocked_reason is None:
                state = self.safe_idle(f"character_projection:{intent.surface_state}")
                self.state.last_command_outcome = BodyCommandOutcomeRecord(
                    command_type="character_projection",
                    requested_action_name=intent.surface_state,
                    canonical_action_name="safe_idle",
                    source_action_name=intent.semantic_summary or intent.surface_state,
                    outcome_status="safe_idle_projection_sent",
                    accepted=True,
                    transport_mode=self.state.transport_mode,
                    reason_code=self.state.transport_reason_code,
                    outcome_notes=[intent.motion_hint, *(intent.source_signals or [])],
                    generated_at=utc_now(),
                )
                self.state.character_projection = CharacterProjectionStatus(
                    profile=resolved_profile,
                    avatar_enabled=projection_profile_supports_avatar(resolved_profile),
                    robot_head_enabled=True,
                    robot_head_allowed=True,
                    robot_head_applied=True,
                    outcome="safe_idle_applied",
                    semantic_summary=intent.semantic_summary,
                    intent=intent.model_copy(deep=True),
                    notes=["projection_used_safe_idle"],
                )
                self.state.updated_at = utc_now()
                return self.state.model_copy(deep=True)

            if blocked_reason is not None or not robot_head_enabled:
                super().apply_character_projection(intent=intent, profile=resolved_profile)
                self.state.character_projection = CharacterProjectionStatus(
                    profile=resolved_profile,
                    avatar_enabled=projection_profile_supports_avatar(resolved_profile),
                    robot_head_enabled=robot_head_enabled,
                    robot_head_allowed=False,
                    robot_head_applied=False,
                    outcome="robot_head_blocked_preview_only" if blocked_reason is not None else "projection_preview_only",
                    blocked_reason=blocked_reason,
                    semantic_summary=intent.semantic_summary,
                    intent=intent.model_copy(deep=True),
                    notes=[f"driver_mode:{self.state.driver_mode.value}", f"motion_hint:{intent.motion_hint}"],
                )
                if self.state.last_command_outcome is not None:
                    self.state.last_command_outcome = self.state.last_command_outcome.model_copy(
                        update={
                            "detail": blocked_reason,
                            "outcome_status": self.state.character_projection.outcome,
                        },
                        deep=True,
                    )
                self.state.updated_at = utc_now()
                return self.state.model_copy(deep=True)

            before_readback = dict(self.state.feedback_positions)
            compiled = self._compile_character_projection(intent)
            self._apply_character_projection_preview(intent=intent, compiled=compiled)
            compiled_targets = dict(self.state.servo_targets)
            try:
                self._apply_compiled_animation()
            except BodyCommandApplyError as exc:
                detail = f"{exc.classification}:{exc.detail}"
                self._sync_transport_status(force_error=detail)
                self.state.last_command_outcome = BodyCommandOutcomeRecord(
                    command_type="character_projection",
                    requested_action_name=intent.surface_state,
                    canonical_action_name=intent.expression_name,
                    source_action_name=intent.semantic_summary or intent.surface_state,
                    outcome_status="robot_head_blocked_preview_only",
                    accepted=False,
                    rejected=True,
                    clamped=bool(self.state.clamp_notes),
                    transport_mode=self.state.transport_mode,
                    reason_code=self.state.transport_reason_code,
                    detail=detail,
                    outcome_notes=[intent.motion_hint, *(intent.source_signals or [])],
                    generated_at=utc_now(),
                )
                self.state.character_projection = CharacterProjectionStatus(
                    profile=resolved_profile,
                    avatar_enabled=projection_profile_supports_avatar(resolved_profile),
                    robot_head_enabled=True,
                    robot_head_allowed=False,
                    robot_head_applied=False,
                    outcome="robot_head_blocked_preview_only",
                    blocked_reason=detail,
                    semantic_summary=intent.semantic_summary,
                    intent=intent.model_copy(deep=True),
                    notes=["projection_fell_back_to_preview_only"],
                )
                self._record_audit(
                    command=None,
                    command_type="character_projection",
                    requested_action_name=intent.surface_state,
                    compiled_targets=compiled_targets,
                    before_readback=before_readback,
                    fallback_used=True,
                )
                self.state.updated_at = utc_now()
                return self.state.model_copy(deep=True)

            self.refresh_live_status(force=True)
            self.state.last_command_outcome = BodyCommandOutcomeRecord(
                command_type="character_projection",
                requested_action_name=intent.surface_state,
                canonical_action_name=intent.expression_name,
                source_action_name=intent.semantic_summary or intent.surface_state,
                outcome_status="projection_sent",
                accepted=True,
                clamped=bool(self.state.clamp_notes),
                transport_mode=self.state.transport_mode,
                reason_code=self.state.transport_reason_code,
                outcome_notes=[intent.motion_hint, *(intent.source_signals or [])],
                generated_at=utc_now(),
            )
            self.state.character_projection = CharacterProjectionStatus(
                profile=resolved_profile,
                avatar_enabled=projection_profile_supports_avatar(resolved_profile),
                robot_head_enabled=True,
                robot_head_allowed=True,
                robot_head_applied=True,
                outcome="robot_head_applied",
                semantic_summary=intent.semantic_summary,
                intent=intent.model_copy(deep=True),
                notes=["projection_dispatched_to_serial_head"],
            )
            self._record_audit(
                command=None,
                command_type="character_projection",
                requested_action_name=intent.surface_state,
                compiled_targets=compiled_targets,
                before_readback=before_readback,
                fallback_used=False,
            )
            self._sync_transport_status()
            self.state.updated_at = utc_now()
            return self.state.model_copy(deep=True)

    def apply_command(self, command: RobotCommand, payload: dict) -> BodyState:
        with self._serial_lock:
            if command.command_type == "safe_idle":
                return self.safe_idle(str(payload.get("reason", "safe_idle")))
            before_readback = dict(self.state.feedback_positions)
            super().apply_command(command, payload)
            compiled_targets = dict(self.state.servo_targets)
            try:
                self._apply_compiled_animation(command=command)
            except BodyCommandApplyError as exc:
                detail = f"{exc.classification}:{exc.detail}"
                self._sync_transport_status(force_error=detail)
                self.state.last_command_outcome = BodyCommandOutcomeRecord(
                    command_type=command.command_type.value,
                    requested_action_name=self.state.last_command_outcome.requested_action_name if self.state.last_command_outcome is not None else None,
                    canonical_action_name=self.state.virtual_preview.semantic_name if self.state.virtual_preview is not None else None,
                    source_action_name=self.state.virtual_preview.source_name if self.state.virtual_preview is not None else None,
                    outcome_status="rejected",
                    accepted=False,
                    rejected=True,
                    clamped=bool(self.state.clamp_notes),
                    transport_mode=self.state.transport_mode,
                    reason_code=self.state.transport_reason_code,
                    detail=detail,
                    outcome_notes=list(self.state.virtual_preview.outcome_notes) if self.state.virtual_preview is not None else [],
                    generated_at=utc_now(),
                )
                self._sync_arm_state()
                self._record_audit(
                    command=command,
                    command_type=command.command_type.value,
                    requested_action_name=self.state.last_command_outcome.requested_action_name if self.state.last_command_outcome is not None else None,
                    compiled_targets=compiled_targets,
                    before_readback=before_readback,
                    fallback_used=False,
                )
                raise
            self.refresh_live_status(force=True)
            self._record_audit(
                command=command,
                command_type=command.command_type.value,
                requested_action_name=self.state.last_command_outcome.requested_action_name if self.state.last_command_outcome is not None else None,
                compiled_targets=compiled_targets,
                before_readback=before_readback,
                fallback_used=False,
            )
            self._sync_transport_status()
            self.state.updated_at = utc_now()
            return self.state.model_copy(deep=True)

    def _projection_block_reason(self) -> str | None:
        try:
            self._require_transport_available("character_projection")
            if self.transport is not None and self.transport.status.mode == LIVE_SERIAL_MODE:
                if not self._configured_profile_exists:
                    raise ServoTransportError("missing_profile", "character_projection_requires_configured_head_profile")
                if not self.transport.status.confirmed_live or not self.transport.status.healthy:
                    detail = self.transport.status.last_error or "live_serial_transport_not_confirmed"
                    raise ServoTransportError("transport_unconfirmed", detail)
                self._require_runtime_motion_ready("character_projection")
        except ServoTransportError as exc:
            return f"{exc.classification}:{exc.detail}"
        return None

    def read_feedback(self) -> dict[str, int]:
        self._refresh_feedback_positions()
        return dict(self.state.feedback_positions)

    def _apply_compiled_animation(self, *, command: RobotCommand | None = None) -> None:
        try:
            if self.transport is None or self.bridge is None:
                raise ServoTransportError("transport_unavailable", self._transport_init_error or "serial_transport_not_available")
            if self.transport.status.mode == LIVE_SERIAL_MODE:
                if not self._configured_profile_exists:
                    raise ServoTransportError("missing_profile", "live_serial_refuses_motion_without_configured_head_profile")
                if not self.transport.status.confirmed_live or not self.transport.status.healthy:
                    detail = self.transport.status.last_error or "live_serial_transport_not_confirmed"
                    raise ServoTransportError("transport_unconfirmed", detail)
                self._require_runtime_motion_ready(command.command_type.value if command is not None else "semantic_motion")
            compiled = self.state.compiled_animation
            if compiled is None:
                return
            outcome, health = self.bridge.apply_compiled_animation(compiled)
            self.state.last_command_outcome = outcome
            self._apply_health(health)
        except ServoTransportError as exc:
            raise BodyCommandApplyError(exc.classification, exc.detail) from exc

    def _refresh_feedback_positions(self) -> None:
        if self.transport is None or self.bridge is None:
            return
        try:
            health = self.bridge.poll_health(
                target_positions=self.state.servo_targets,
                last_command_outcome=self.state.last_command_outcome,
            )
        except ServoTransportError as exc:
            self._sync_transport_status(force_error=f"{exc.classification}:{exc.detail}")
            return
        self._apply_health(health)

    def _apply_health(self, health: dict[str, object]) -> None:
        self.state.servo_health = {
            name: record.model_copy(deep=True)
            for name, record in health.items()
        }
        self.state.feedback_positions = {
            name: int(record.current_position)
            for name, record in self.state.servo_health.items()
            if record.current_position is not None
        }
        self.state.feedback_status = {
            name: len(record.error_bits)
            for name, record in self.state.servo_health.items()
        }

    def _sync_transport_status(self, force_error: str | None = None) -> None:
        if self.transport is None:
            self.capabilities.transport_mode = self._configured_transport_mode()
            self.capabilities.transport_healthy = False
            self.capabilities.transport_error = force_error or self._transport_init_error
            self.capabilities.transport_reason_code = "transport_unconfirmed"
            self.capabilities.transport_confirmed_live = False
            self.capabilities.transport_port = self._runtime_transport_port
            self.capabilities.transport_baud_rate = self._runtime_servo_baud
            self.capabilities.connected = False
        else:
            self.capabilities.transport_mode = self.transport.status.mode
            self.capabilities.transport_healthy = self.transport.status.healthy
            self.capabilities.transport_error = force_error or self.transport.status.last_error
            self.capabilities.transport_reason_code = self.transport.status.reason_code
            self.capabilities.transport_confirmed_live = self.transport.status.confirmed_live
            self.capabilities.transport_port = self.transport.status.port
            self.capabilities.transport_baud_rate = self.transport.status.baud_rate
            self.capabilities.connected = self.transport.status.mode != LIVE_SERIAL_MODE or self.transport.status.confirmed_live
        self.capabilities.transport_boundary_version = self.profile.transport_boundary_version
        self.capabilities.live_motion_enabled = self._live_motion_enabled()
        self.state.transport_mode = self.capabilities.transport_mode
        self.state.transport_healthy = self.capabilities.transport_healthy
        self.state.transport_error = self.capabilities.transport_error
        self.state.transport_reason_code = self.capabilities.transport_reason_code
        self.state.transport_confirmed_live = self.capabilities.transport_confirmed_live
        self.state.transport_port = self.capabilities.transport_port
        self.state.transport_baud_rate = self.capabilities.transport_baud_rate
        self.state.connected = self.capabilities.connected
        self.state.calibration_path = self._calibration_path()
        self.state.calibration_version = self._calibration_version()
        self.state.calibration_status = self._calibration_status()
        self.state.live_motion_enabled = self._live_motion_enabled()
        self.state.live_motion_armed = bool(self.state.live_motion_armed)

    def _servo_lab_read_positions(
        self,
        transport,
        *,
        joint_name: str | None = None,
    ) -> tuple[dict[str, int], dict[str, str]]:
        current_positions: dict[str, int] = {}
        readback_errors: dict[str, str] = {}
        joints = [joint for joint in self.profile.joints if joint.enabled]
        if joint_name is not None:
            joints = [joint for joint in joints if joint.joint_name == joint_name]
            if not joints:
                raise ServoTransportError("out_of_range", f"unknown_joint:{joint_name}")
        for joint in joints:
            servo_id = int(joint.servo_ids[0]) if joint.servo_ids else None
            if servo_id is None:
                readback_errors[joint.joint_name] = "servo_id_missing"
                continue
            try:
                current_positions[joint.joint_name] = int(transport.read_position(servo_id))
            except ServoTransportError as exc:
                readback_errors[joint.joint_name] = f"{exc.classification}:{exc.detail}"
        return current_positions, readback_errors

    def _servo_lab_read_current_position(self, transport, joint_name: str) -> int | None:
        current_positions, readback_errors = self._servo_lab_read_positions(transport, joint_name=joint_name)
        if joint_name in readback_errors:
            raise ServoTransportError("transport_unconfirmed", f"servo_lab_readback_failed:{joint_name}:{readback_errors[joint_name]}")
        return current_positions.get(joint_name)

    def _servo_lab_health_reads(
        self,
        transport,
        *,
        joint_name: str | None = None,
    ) -> dict[str, object]:
        joints = [joint for joint in self.profile.joints if joint.enabled]
        if joint_name is not None:
            joints = [joint for joint in joints if joint.joint_name == joint_name]
            if not joints:
                raise ServoTransportError("out_of_range", f"unknown_joint:{joint_name}")
        payload: dict[str, object] = {}
        for joint in joints:
            servo_ids = [int(servo_id) for servo_id in joint.servo_ids]
            payload[joint.joint_name] = {
                "servo_ids": servo_ids,
                "health": read_bench_health_many(transport, servo_ids),
            }
        return payload

    def _build_capabilities(self) -> BodyCapabilityProfile:
        transport_mode = self.transport.status.mode if self.transport is not None else self._configured_transport_mode()
        transport_healthy = self.transport.status.healthy if self.transport is not None else False
        transport_error = self.transport.status.last_error if self.transport is not None else self._transport_init_error
        transport_reason_code = self.transport.status.reason_code if self.transport is not None else "transport_unconfirmed"
        notes = [
            "Serial body mode keeps the same semantic compiler as virtual mode.",
            "Dry-run and fixture replay remain valid pre-power development paths for the Feetech/ST head.",
            f"transport_boundary:{self.profile.transport_boundary_version}",
            f"calibration_status:{self._calibration_status()}",
        ]
        if transport_mode == LIVE_SERIAL_MODE:
            notes.append("Live serial writes remain blocked until the transport confirms a healthy servo reply and a saved calibration is loaded.")
            notes.append("Future Jetson deployment stays thin: apply semantic commands, report health, acknowledge outcomes, and fall back to safe idle.")
        if transport_error:
            notes.append(f"transport_error:{transport_error}")
        return self._base_capabilities(
            driver_mode=BodyDriverMode.SERIAL,
            present=True,
            connected=transport_mode != LIVE_SERIAL_MODE or transport_healthy,
            transport_mode=transport_mode,
            transport_healthy=transport_healthy,
            transport_error=transport_error,
            supports_virtual_preview=True,
            supports_serial_transport=True,
            supports_readback=True,
            notes=notes,
        ).model_copy(
            update={
                "transport_reason_code": transport_reason_code,
                "transport_confirmed_live": self.transport.status.confirmed_live if self.transport is not None else False,
                "transport_port": self.transport.status.port if self.transport is not None else self._runtime_transport_port,
                "transport_baud_rate": self.transport.status.baud_rate if self.transport is not None else self._runtime_servo_baud,
            }
        )

    def _live_motion_enabled(self) -> bool:
        return bool(self.bridge.live_motion_enabled) if getattr(self, "bridge", None) is not None else False

    def _servo_ids(self) -> list[int]:
        ids: list[int] = []
        for joint in self.profile.joints:
            ids.extend(joint.servo_ids)
        return sorted({servo_id for servo_id in ids})

    def _configured_transport_mode(self) -> str:
        return (self.settings.blink_serial_transport or "unavailable").strip().lower()

    def _hydrate_runtime_transport_from_arm_lease(self) -> bool:
        if self._configured_transport_mode() != LIVE_SERIAL_MODE:
            return False
        if self._runtime_transport_port:
            return False
        lease = read_arm_lease(DEFAULT_ARM_LEASE_PATH)
        if lease is None:
            return False
        expires_at = _parse_timestamp(lease.get("expires_at"))
        if expires_at is None or utc_now() > expires_at:
            return False
        port = str(lease.get("port") or "").strip()
        if not port:
            return False
        self._runtime_transport_port = port
        baud_rate = lease.get("baud_rate")
        if baud_rate is not None:
            self._runtime_servo_baud = int(baud_rate)
        return True

    def _reload_calibration(self) -> None:
        self.calibration = _load_head_calibration(self.settings.blink_head_calibration, profile=self.profile)
        self._reload_tuning()
        if self.bridge is not None:
            self.bridge.calibration = self.calibration

    def _connect_transport(self) -> None:
        settings = self.settings.model_copy(
            update={
                "blink_serial_port": self._runtime_transport_port,
                "blink_servo_baud": self._runtime_servo_baud,
                "blink_serial_timeout_seconds": self._runtime_timeout_seconds,
            },
            deep=True,
        )
        try:
            self.transport = build_servo_transport(settings, self.profile)
        except ServoTransportError as exc:
            self.transport = None
            self.bridge = None
            self._transport_init_error = f"{exc.classification}:{exc.detail}"
            return
        self._transport_init_error = None
        self.bridge = FeetechBodyBridge(
            transport=self.transport,
            profile=self.profile,
            calibration=self.calibration,
        )
        if self.transport.status.mode == LIVE_SERIAL_MODE:
            self.transport.confirm_live(self._servo_ids()[:1])

    def _require_transport_available(self, operation: str) -> tuple[object, FeetechBodyBridge]:
        if self.transport is None or self.bridge is None:
            raise ServoTransportError("transport_unconfirmed", f"{operation}_requires_connected_transport")
        return self.transport, self.bridge

    def _require_live_transport(self, operation: str) -> tuple[object, FeetechBodyBridge]:
        transport, bridge = self._require_transport_available(operation)
        if transport.status.mode == LIVE_SERIAL_MODE:
            confirm_live_transport(transport, self.profile)
        return transport, bridge

    def _require_saved_calibration(self, operation: str) -> None:
        if self.calibration.calibration_kind == "template":
            raise ServoTransportError("calibration_template", f"{operation}_requires_saved_non_template_calibration")

    def _require_runtime_motion_ready(self, operation: str) -> None:
        self._require_saved_calibration(operation)
        conflicts = conflicting_range_joints(self.calibration)
        if conflicts:
            raise ServoTransportError("range_conflict_from_capture", f"{operation}_range_conflict:{','.join(sorted(conflicts))}")
        if not coupling_validation_ready(self.calibration):
            raise ServoTransportError("coupling_unvalidated", f"{operation}_requires_validate_coupling")
        validate_motion_arm(
            port=self._runtime_transport_port,
            baud_rate=self._runtime_servo_baud,
            calibration_path=self._calibration_path() or self.settings.blink_head_calibration,
            path=DEFAULT_ARM_LEASE_PATH,
        )

    def _sync_arm_state(self) -> None:
        lease = read_arm_lease(DEFAULT_ARM_LEASE_PATH)
        self.state.live_motion_armed = False
        self.state.arm_expires_at = None
        expires_at = _parse_timestamp(lease.get("expires_at")) if lease is not None else None
        self.state.arm_expires_at = expires_at
        if lease is None or expires_at is None or utc_now() > expires_at:
            return
        calibration_path = self._calibration_path() or self.settings.blink_head_calibration
        try:
            validate_motion_arm(
                port=self._runtime_transport_port,
                baud_rate=self._runtime_servo_baud,
                calibration_path=calibration_path,
                path=DEFAULT_ARM_LEASE_PATH,
            )
        except ServoTransportError:
            return
        self.state.live_motion_armed = True

    def _health_summary(self) -> dict[str, dict[str, object]]:
        return {
            name: record.model_dump(mode="json")
            for name, record in self.state.servo_health.items()
        }

    def _record_audit(
        self,
        *,
        command: RobotCommand | None,
        command_type: str,
        requested_action_name: str | None,
        compiled_targets: dict[str, int],
        before_readback: dict[str, int],
        fallback_used: bool,
        report_path: str | None = None,
    ) -> None:
        audit = self._build_command_audit(
            command=command,
            command_type=command_type,
            requested_action_name=requested_action_name,
            compiled_targets=compiled_targets,
            before_readback=before_readback,
            fallback_used=fallback_used,
            report_path=report_path,
        )
        self.state.latest_command_audit = audit
        self.state.body_fault_classification = audit.fault_classification
        self.state.body_fault_detail = audit.confirmation_result or audit.detail
        self.state.power_health_classification = audit.power_health_classification
        self.state.preflight_passed = audit.preflight_passed
        self.state.preflight_failure_reason = audit.preflight_failure_reason
        self.state.idle_voltage_snapshot = dict(audit.idle_voltage_snapshot)
        self._command_audits.append(audit)
        self._command_audits = self._command_audits[-200:]

    def _record_manual_audit(
        self,
        *,
        command_type: str,
        requested_action_name: str,
        report: dict[str, object],
    ) -> None:
        outcome_payload = report.get("outcome") or {}
        self.state.last_command_outcome = BodyCommandOutcomeRecord.model_validate(outcome_payload)
        self._record_audit(
            command=None,
            command_type=command_type,
            requested_action_name=requested_action_name,
            compiled_targets=dict(report.get("clamped_targets") or {}),
            before_readback={
                str(key): value["position"]
                for key, value in (report.get("before_position") or {}).items()
                if isinstance(value, dict) and value.get("position") is not None
            },
            fallback_used=bool(report.get("failure_reason")),
            report_path=str(report.get("report_path")) if report.get("report_path") else None,
        )

    def _blocked_range_demo_result(
        self,
        *,
        sequence_name: str,
        preset_name: str,
        note: str | None,
        plan,
        before_readback: dict[str, int],
        classification: str,
        detail: str,
    ) -> dict[str, object]:
        outcome = BodyCommandOutcomeRecord(
            command_type="body_range_demo",
            requested_action_name=sequence_name,
            canonical_action_name="body_range_demo",
            source_action_name=sequence_name,
            outcome_status="blocked",
            accepted=False,
            rejected=True,
            transport_mode=self.transport_summary().get("mode") if isinstance(self.transport_summary(), dict) else None,
            reason_code=classification,
            detail=detail,
            outcome_notes=[
                f"range_demo_sequence:{sequence_name}",
                f"range_demo_preset:{preset_name}",
                "range_demo_blocked",
                *plan.animation.compiler_notes,
            ],
            executed_frame_count=len(plan.animation.frames),
            executed_frame_names=[frame.frame_name or f"frame_{index}" for index, frame in enumerate(plan.animation.frames)],
            per_frame_duration_ms=[int(frame.duration_ms) for frame in plan.animation.frames],
            per_frame_hold_ms=[int(frame.hold_ms) for frame in plan.animation.frames],
            elapsed_wall_clock_ms=0.0,
            final_frame_name=plan.animation.frames[-1].frame_name,
            peak_compiled_targets=self._peak_targets_from_animation(plan.animation),
            peak_normalized_pose=self._peak_pose_from_animation(plan.animation),
            usable_range_audit=plan.usable_range_audit,
            generated_at=utc_now(),
        )
        self.state.last_command_outcome = outcome
        self.state.latest_command_audit = self._build_command_audit(
            command=None,
            command_type="body_range_demo",
            requested_action_name=sequence_name,
            compiled_targets=outcome.peak_compiled_targets,
            before_readback=before_readback,
            fallback_used=True,
            report_path=None,
        )
        self.state.updated_at = utc_now()
        return {
            "status": "blocked",
            "detail": detail,
            "sequence_name": sequence_name,
            "preset_name": preset_name,
            "body_state": self.state.model_dump(mode="json"),
            "latest_command_audit": (
                self.state.latest_command_audit.model_dump(mode="json")
                if self.state.latest_command_audit is not None
                else None
            ),
            "transport_summary": self.transport_summary(),
            "payload": {
                "sequence_name": sequence_name,
                "preset_name": preset_name,
                "range_demo": plan.to_payload(),
                "preview_only": False,
                "live_requested": True,
                "blocked_reason": f"{classification}:{detail}",
                "tuning_path": self._semantic_tuning_path,
                "available_presets": list(available_range_demo_presets()),
                "available_sequences": list(available_range_demo_sequences()),
            },
        }

    def _blocked_primitive_sequence_result(
        self,
        *,
        compiled: CompiledAnimation,
        sequence_name: str,
        note: str | None,
        before_readback: dict[str, int],
        classification: str,
        detail: str,
    ) -> dict[str, object]:
        peak_targets = self._peak_targets_from_animation(compiled)
        outcome = BodyCommandOutcomeRecord(
            command_type="body_primitive_sequence",
            requested_action_name=sequence_name,
            canonical_action_name=sequence_name,
            source_action_name=sequence_name,
            outcome_status="blocked",
            accepted=False,
            rejected=True,
            transport_mode=self.transport_summary().get("mode") if isinstance(self.transport_summary(), dict) else None,
            reason_code=classification,
            detail=detail,
            outcome_notes=list(compiled.compiler_notes),
            executed_frame_count=len(compiled.frames),
            executed_frame_names=[frame.frame_name or f"frame_{index}" for index, frame in enumerate(compiled.frames)],
            per_frame_duration_ms=[int(frame.duration_ms) for frame in compiled.frames],
            per_frame_hold_ms=[int(frame.hold_ms) for frame in compiled.frames],
            elapsed_wall_clock_ms=0.0,
            final_frame_name=compiled.frames[-1].frame_name if compiled.frames else None,
            peak_compiled_targets=peak_targets,
            peak_normalized_pose=self._peak_pose_from_animation(compiled),
            tuning_lane=compiled.tuning_lane or self.compiler.tuning.tuning_lane,
            kinetics_profiles_used=list(compiled.kinetics_profiles_used),
            grounding=compiled.grounding,
            recipe_name=compiled.recipe_name,
            primitive_steps=list(compiled.primitive_steps),
            sequence_step_count=compiled.sequence_step_count,
            returned_to_neutral=bool(compiled.returns_to_neutral),
            generated_at=utc_now(),
        )
        self.state.last_command_outcome = outcome
        self.state.latest_command_audit = self._build_command_audit(
            command=None,
            command_type="body_primitive_sequence",
            requested_action_name=sequence_name,
            compiled_targets=peak_targets,
            before_readback=before_readback,
            fallback_used=True,
            report_path=None,
        )
        self.state.updated_at = utc_now()
        return {
            "status": "blocked",
            "detail": detail,
            "sequence_name": sequence_name,
            "body_state": self.state.model_dump(mode="json"),
            "latest_command_audit": (
                self.state.latest_command_audit.model_dump(mode="json")
                if self.state.latest_command_audit is not None
                else None
            ),
            "transport_summary": self.transport_summary(),
            "payload": {
                "sequence_name": sequence_name,
                "primitive_steps": list(compiled.primitive_steps),
                "sequence_step_count": compiled.sequence_step_count,
                "returned_to_neutral": bool(compiled.returns_to_neutral),
                "preview_only": False,
                "live_requested": True,
                "blocked_reason": f"{classification}:{detail}",
                "tuning_path": self._semantic_tuning_path,
            },
        }

    def _blocked_staged_sequence_result(
        self,
        *,
        compiled: CompiledAnimation,
        sequence_name: str,
        note: str | None,
        before_readback: dict[str, int],
        classification: str,
        detail: str,
    ) -> dict[str, object]:
        peak_targets = self._peak_targets_from_animation(compiled)
        outcome = BodyCommandOutcomeRecord(
            command_type="body_staged_sequence",
            requested_action_name=sequence_name,
            canonical_action_name=sequence_name,
            source_action_name=sequence_name,
            outcome_status="blocked",
            accepted=False,
            rejected=True,
            transport_mode=self.transport_summary().get("mode") if isinstance(self.transport_summary(), dict) else None,
            reason_code=classification,
            detail=detail,
            outcome_notes=list(compiled.compiler_notes),
            executed_frame_count=len(compiled.frames),
            executed_frame_names=[frame.frame_name or f"frame_{index}" for index, frame in enumerate(compiled.frames)],
            per_frame_duration_ms=[int(frame.duration_ms) for frame in compiled.frames],
            per_frame_hold_ms=[int(frame.hold_ms) for frame in compiled.frames],
            elapsed_wall_clock_ms=0.0,
            final_frame_name=compiled.frames[-1].frame_name if compiled.frames else None,
            peak_compiled_targets=peak_targets,
            peak_normalized_pose=self._peak_pose_from_animation(compiled),
            tuning_lane=compiled.tuning_lane or self.compiler.tuning.tuning_lane,
            kinetics_profiles_used=list(compiled.kinetics_profiles_used),
            grounding=compiled.grounding,
            recipe_name=compiled.recipe_name,
            primitive_steps=list(compiled.primitive_steps),
            sequence_step_count=compiled.sequence_step_count,
            structural_action=compiled.structural_action,
            expressive_accents=list(compiled.expressive_accents),
            stage_count=compiled.stage_count,
            returned_to_neutral=bool(compiled.returns_to_neutral),
            generated_at=utc_now(),
        )
        self.state.last_command_outcome = outcome
        self.state.latest_command_audit = self._build_command_audit(
            command=None,
            command_type="body_staged_sequence",
            requested_action_name=sequence_name,
            compiled_targets=peak_targets,
            before_readback=before_readback,
            fallback_used=True,
            report_path=None,
        )
        self.state.updated_at = utc_now()
        return {
            "status": "blocked",
            "detail": detail,
            "sequence_name": sequence_name,
            "body_state": self.state.model_dump(mode="json"),
            "latest_command_audit": (
                self.state.latest_command_audit.model_dump(mode="json")
                if self.state.latest_command_audit is not None
                else None
            ),
            "transport_summary": self.transport_summary(),
            "payload": {
                "sequence_name": sequence_name,
                "structural_action": compiled.structural_action,
                "expressive_accents": list(compiled.expressive_accents),
                "stage_count": compiled.stage_count,
                "returned_to_neutral": bool(compiled.returns_to_neutral),
                "preview_only": False,
                "live_requested": True,
                "blocked_reason": f"{classification}:{detail}",
                "tuning_path": self._semantic_tuning_path,
            },
        }

    def _blocked_expressive_sequence_result(
        self,
        *,
        compiled: CompiledAnimation,
        sequence_name: str,
        note: str | None,
        before_readback: dict[str, int],
        classification: str,
        detail: str,
    ) -> dict[str, object]:
        peak_targets = self._peak_targets_from_animation(compiled)
        outcome = BodyCommandOutcomeRecord(
            command_type="body_expressive_motif",
            requested_action_name=sequence_name,
            canonical_action_name=sequence_name,
            source_action_name=sequence_name,
            outcome_status="blocked",
            accepted=False,
            rejected=True,
            transport_mode=self.transport_summary().get("mode") if isinstance(self.transport_summary(), dict) else None,
            reason_code=classification,
            detail=detail,
            outcome_notes=list(compiled.compiler_notes),
            executed_frame_count=len(compiled.frames),
            executed_frame_names=[frame.frame_name or f"frame_{index}" for index, frame in enumerate(compiled.frames)],
            per_frame_duration_ms=[int(frame.duration_ms) for frame in compiled.frames],
            per_frame_hold_ms=[int(frame.hold_ms) for frame in compiled.frames],
            elapsed_wall_clock_ms=0.0,
            final_frame_name=compiled.frames[-1].frame_name if compiled.frames else None,
            peak_compiled_targets=peak_targets,
            peak_normalized_pose=self._peak_pose_from_animation(compiled),
            tuning_lane=compiled.tuning_lane or self.compiler.tuning.tuning_lane,
            kinetics_profiles_used=list(compiled.kinetics_profiles_used),
            grounding=compiled.grounding,
            recipe_name=compiled.recipe_name,
            motif_name=compiled.motif_name,
            primitive_steps=list(compiled.primitive_steps),
            expressive_steps=list(compiled.expressive_steps),
            step_kinds=list(compiled.step_kinds),
            sequence_step_count=compiled.sequence_step_count,
            structural_action=compiled.structural_action,
            expressive_accents=list(compiled.expressive_accents),
            stage_count=compiled.stage_count,
            returned_to_neutral=bool(compiled.returns_to_neutral),
            generated_at=utc_now(),
        )
        self.state.last_command_outcome = outcome
        self.state.latest_command_audit = self._build_command_audit(
            command=None,
            command_type="body_expressive_motif",
            requested_action_name=sequence_name,
            compiled_targets=peak_targets,
            before_readback=before_readback,
            fallback_used=True,
            report_path=None,
        )
        self.state.updated_at = utc_now()
        return {
            "status": "blocked",
            "detail": detail,
            "sequence_name": sequence_name,
            "body_state": self.state.model_dump(mode="json"),
            "latest_command_audit": (
                self.state.latest_command_audit.model_dump(mode="json")
                if self.state.latest_command_audit is not None
                else None
            ),
            "transport_summary": self.transport_summary(),
            "payload": {
                "sequence_name": sequence_name,
                "motif_name": compiled.motif_name,
                "structural_action": compiled.structural_action,
                "expressive_steps": list(compiled.expressive_steps),
                "step_kinds": list(compiled.step_kinds),
                "sequence_step_count": compiled.sequence_step_count,
                "returned_to_neutral": bool(compiled.returns_to_neutral),
                "preview_only": False,
                "live_requested": True,
                "blocked_reason": f"{classification}:{detail}",
                "tuning_path": self._semantic_tuning_path,
            },
        }

    def _remember_motion_report(self, report_path: object | None) -> None:
        if not report_path:
            return
        path = str(report_path)
        if path not in self._motion_report_paths:
            self._motion_report_paths.append(path)


def build_body_driver(settings: Settings) -> BaseBodyDriver:
    mode = settings.resolved_body_driver
    if mode == BodyDriverMode.BODYLESS:
        return BodylessDriver(settings=settings)
    if mode == BodyDriverMode.SERIAL:
        return SerialBodyDriver(settings=settings)
    return VirtualBodyDriver(settings=settings)


__all__ = [
    "BaseBodyDriver",
    "BodyCommandApplyError",
    "BodylessDriver",
    "SerialBodyDriver",
    "VirtualBodyDriver",
    "build_body_driver",
]
