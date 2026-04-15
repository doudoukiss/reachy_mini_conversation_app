from __future__ import annotations

import time

from embodied_stack.shared.contracts.body import (
    BodyCommandOutcomeRecord,
    BodyMotionControlAuditRecord,
    CompiledAnimation,
    CompiledBodyFrame,
    HeadCalibrationRecord,
    HeadProfile,
    ServoHealthRecord,
    utc_now,
)

from ..motion_audit import build_motion_control_audit
from ..motion_tuning import outcome_margin_payload
from .health import collect_servo_health, read_bench_health_many, servo_health_from_bench_reads
from .protocol import ADDRESS_TARGET_POSITION, build_target_position_payload
from .transport import BaseServoTransport, LIVE_SERIAL_MODE, ServoTransportError

SUSPECT_CONFIRMATION_DELAY_SECONDS = 0.04
IDLE_POWER_PREFLIGHT_DELAY_SECONDS = 0.05
LOW_VOLTAGE_THRESHOLD = 90
SUSPECT_VOLTAGE_FRACTION = 0.75
MIN_SUSPECT_VOLTAGE_JOINTS = 4
IMPLAUSIBLE_DIVERGENCE_RATIO = 0.2
MIN_IMPLAUSIBLE_JOINTS = 3
MIN_IMPLAUSIBLE_FAMILIES = 3


def _joint_fault_family(joint_name: str) -> str:
    if joint_name == "head_yaw":
        return "head_yaw"
    if joint_name.startswith("head_pitch_pair"):
        return "neck_pair"
    if joint_name.startswith("eye_"):
        return "eyes"
    if "lid" in joint_name:
        return "lids"
    if joint_name.startswith("brow_"):
        return "brows"
    return joint_name


def _suspicious_voltage_joints(health: dict[str, ServoHealthRecord]) -> list[str]:
    total = len(health)
    if total <= 0:
        return []
    voltage_joints = [
        joint_name
        for joint_name, record in health.items()
        if "input_voltage" in record.error_bits
    ]
    threshold = max(MIN_SUSPECT_VOLTAGE_JOINTS, int(total * SUSPECT_VOLTAGE_FRACTION))
    if len(voltage_joints) >= threshold:
        return sorted(voltage_joints)
    return []


def _low_voltage_joints(health: dict[str, ServoHealthRecord]) -> list[str]:
    total = len(health)
    if total <= 0:
        return []
    low_voltage = [
        joint_name
        for joint_name, record in health.items()
        if record.voltage_raw is not None and int(record.voltage_raw) <= LOW_VOLTAGE_THRESHOLD
    ]
    threshold = max(MIN_SUSPECT_VOLTAGE_JOINTS, int(total * SUSPECT_VOLTAGE_FRACTION))
    if len(low_voltage) >= threshold:
        return sorted(low_voltage)
    return []


def _power_health_snapshot(
    health: dict[str, ServoHealthRecord],
    *,
    idle_preflight: bool,
) -> tuple[str, str | None]:
    suspect_voltage = _suspicious_voltage_joints(health)
    low_voltage = _low_voltage_joints(health)
    if idle_preflight:
        if low_voltage:
            return "unhealthy_idle", f"unhealthy_idle_low_voltage:{','.join(low_voltage)}"
        if suspect_voltage:
            return "suspect_power", f"suspect_idle_input_voltage:{','.join(suspect_voltage)}"
        return "healthy", None
    if low_voltage:
        return "confirmed_power_fault", f"confirmed_low_voltage:{','.join(low_voltage)}"
    if suspect_voltage:
        return "suspect_power", f"suspect_input_voltage:{','.join(suspect_voltage)}"
    return "healthy", None


def _implausible_readback_joints(
    *,
    health: dict[str, ServoHealthRecord],
    bridge: "FeetechBodyBridge",
) -> list[str]:
    divergent: list[str] = []
    families: set[str] = set()
    for joint_name, record in health.items():
        target = record.target_position
        current = record.current_position
        if target is None or current is None:
            continue
        joint = next((item for item in bridge.profile.joints if item.joint_name == joint_name), None)
        if joint is None:
            continue
        raw_min, raw_max = bridge._limits_for_joint(  # noqa: SLF001
            joint_name,
            default_min=int(joint.raw_min),
            default_max=int(joint.raw_max),
        )
        span = max(1, int(raw_max) - int(raw_min))
        if abs(int(current) - int(target)) / span >= IMPLAUSIBLE_DIVERGENCE_RATIO:
            divergent.append(joint_name)
            families.add(_joint_fault_family(joint_name))
    if len(divergent) >= MIN_IMPLAUSIBLE_JOINTS and len(families) >= MIN_IMPLAUSIBLE_FAMILIES:
        return sorted(divergent)
    return []


class FeetechBodyBridge:
    def __init__(
        self,
        *,
        transport: BaseServoTransport,
        profile: HeadProfile,
        calibration: HeadCalibrationRecord | None = None,
    ) -> None:
        self.transport = transport
        self.profile = profile
        self.calibration = calibration

    @property
    def calibration_status(self) -> str:
        if self.calibration is None:
            return "missing"
        if self.calibration.calibration_kind == "template":
            return "template"
        return "loaded"

    @property
    def live_motion_enabled(self) -> bool:
        if self.transport.status.mode != LIVE_SERIAL_MODE:
            return True
        return (
            self.transport.status.confirmed_live
            and self.transport.status.healthy
            and self.calibration is not None
            and self.calibration.schema_version == "blink_head_calibration/v2"
            and self.calibration.calibration_kind != "template"
        )

    def apply_compiled_animation(self, compiled: CompiledAnimation) -> tuple[BodyCommandOutcomeRecord, dict[str, ServoHealthRecord]]:
        if self.transport.status.mode == LIVE_SERIAL_MODE and not self.live_motion_enabled:
            raise ServoTransportError("transport_unconfirmed", "live_serial_requires_confirmed_transport_and_saved_calibration")
        if not compiled.frames:
            outcome = BodyCommandOutcomeRecord(
                command_type="perform_animation",
                canonical_action_name=compiled.animation_name,
                source_action_name=compiled.animation_name,
                outcome_status="no_frames",
                accepted=False,
                rejected=True,
                transport_mode=self.transport.status.mode,
                reason_code="invalid_reply",
                detail="compiled_animation_has_no_frames",
                outcome_notes=[],
            )
            return outcome, {}
        servo_ids = self._servo_ids_for_animation(compiled)
        requested_speed = compiled.requested_speed
        requested_acceleration = compiled.requested_acceleration
        motion_control = self._prepare_motion_control(
            servo_ids,
            speed_override=requested_speed,
            acceleration_override=requested_acceleration,
        )
        started = time.perf_counter()
        for frame in compiled.frames:
            self._send_frame(
                frame,
                speed=motion_control.speed.effective_value,
            )
            self._wait_for_frame_dwell(frame)
        elapsed_wall_clock_ms = round((time.perf_counter() - started) * 1000.0, 2)
        motion_control = self._finalize_motion_control(
            servo_ids=servo_ids,
            base=motion_control,
            speed_verified=True,
        )
        outcome = BodyCommandOutcomeRecord(
            command_type="perform_animation",
            requested_action_name=compiled.animation_name,
            canonical_action_name=compiled.animation_name,
            source_action_name=compiled.animation_name,
            outcome_status="sent",
            accepted=True,
            transport_mode=self.transport.status.mode,
            reason_code=self.transport.status.reason_code,
            outcome_notes=list(compiled.compiler_notes),
            executed_frame_count=len(compiled.frames),
            executed_frame_names=[frame.frame_name or f"frame_{index}" for index, frame in enumerate(compiled.frames)],
            per_frame_duration_ms=[self._resolved_duration_ms(frame) for frame in compiled.frames],
            per_frame_hold_ms=[max(0, int(frame.hold_ms or 0)) for frame in compiled.frames],
            elapsed_wall_clock_ms=elapsed_wall_clock_ms,
            final_frame_name=compiled.frames[-1].frame_name,
            peak_compiled_targets=self._peak_compiled_targets(compiled),
            peak_normalized_pose=self._peak_normalized_pose(compiled),
            tuning_lane=compiled.tuning_lane,
            kinetics_profiles_used=list(compiled.kinetics_profiles_used),
            grounding=compiled.grounding,
            recipe_name=compiled.recipe_name,
            primitive_steps=list(compiled.primitive_steps),
            sequence_step_count=compiled.sequence_step_count,
            structural_action=compiled.structural_action,
            expressive_accents=list(compiled.expressive_accents),
            stage_count=compiled.stage_count,
            returned_to_neutral=bool(compiled.returns_to_neutral),
            motion_control=motion_control,
            generated_at=utc_now(),
        )
        outcome = outcome_margin_payload(outcome, profile=self.profile, calibration=self.calibration)
        health, outcome = self._poll_health_with_confirmation(
            target_positions=compiled.frames[-1].servo_targets,
            last_command_outcome=outcome,
            servo_ids=servo_ids,
        )
        return outcome, health

    def run_live_power_preflight(self) -> tuple[BodyCommandOutcomeRecord, dict[str, ServoHealthRecord]]:
        servo_ids = self._servo_ids()
        if self.transport.status.mode == LIVE_SERIAL_MODE and not self.live_motion_enabled:
            raise ServoTransportError("transport_unconfirmed", "live_serial_requires_confirmed_transport_and_saved_calibration")
        first_payload = read_bench_health_many(self.transport, servo_ids)
        first_health = servo_health_from_bench_reads(
            profile=self.profile,
            bench_health=first_payload,
            power_health_classification=None,
        )
        first_classification, first_reason = _power_health_snapshot(first_health, idle_preflight=True)
        time.sleep(IDLE_POWER_PREFLIGHT_DELAY_SECONDS)
        second_payload = read_bench_health_many(self.transport, servo_ids)
        second_health = servo_health_from_bench_reads(
            profile=self.profile,
            bench_health=second_payload,
            power_health_classification=None,
        )
        second_classification, second_reason = _power_health_snapshot(second_health, idle_preflight=True)
        final_classification = "healthy"
        failure_reason: str | None = None
        if "unhealthy_idle" in {first_classification, second_classification}:
            final_classification = "unhealthy_idle"
            failure_reason = second_reason or first_reason
        elif "suspect_power" in {first_classification, second_classification}:
            final_classification = "suspect_power"
            failure_reason = second_reason or first_reason
        snapshot = self._merge_extended_health(
            second_health,
            extended=second_payload,
            power_health_classification=final_classification,
        )
        idle_voltage_snapshot = {
            joint_name: record.model_dump(mode="json")
            for joint_name, record in snapshot.items()
        }
        outcome = BodyCommandOutcomeRecord(
            command_type="body_power_preflight",
            requested_action_name="live_power_preflight",
            canonical_action_name="live_power_preflight",
            source_action_name="live_power_preflight",
            outcome_status="preflight_passed" if final_classification == "healthy" else "preflight_blocked",
            accepted=final_classification == "healthy",
            rejected=final_classification != "healthy",
            transport_mode=self.transport.status.mode,
            reason_code="ok" if final_classification == "healthy" else final_classification,
            detail=failure_reason,
            outcome_notes=[
                f"power_preflight_sample_1:{first_classification}",
                f"power_preflight_sample_2:{second_classification}",
            ],
            power_health_classification=final_classification,
            preflight_passed=final_classification == "healthy",
            preflight_failure_reason=failure_reason,
            idle_voltage_snapshot=idle_voltage_snapshot,
            generated_at=utc_now(),
        )
        return outcome, snapshot

    def execute_joint_targets(
        self,
        *,
        servo_targets: dict[str, int],
        duration_ms: int | None = None,
        command_type: str = "bench_move",
        requested_action_name: str | None = None,
        outcome_notes: list[str] | None = None,
        speed_override: int | None = None,
        acceleration_override: int | None = None,
        limit_overrides: dict[str, tuple[int, int]] | None = None,
    ) -> tuple[BodyCommandOutcomeRecord, dict[str, ServoHealthRecord]]:
        if self.transport.status.mode == LIVE_SERIAL_MODE and not self.live_motion_enabled:
            raise ServoTransportError("transport_unconfirmed", "live_serial_requires_confirmed_transport_and_saved_calibration")
        if not servo_targets:
            raise ServoTransportError("out_of_range", "bench_move_requires_targets")
        servo_ids = self._servo_ids_for_joint_targets(servo_targets)
        motion_control = self._prepare_motion_control(
            servo_ids,
            speed_override=speed_override,
            acceleration_override=acceleration_override,
        )
        frame = CompiledBodyFrame(
            frame_name=requested_action_name or command_type,
            servo_targets=dict(servo_targets),
            duration_ms=max(int(self.profile.minimum_transition_ms or 80), int(duration_ms or self.profile.default_transition_ms or 120)),
            compiler_notes=list(outcome_notes or []),
        )
        self._send_frame(
            frame,
            speed=motion_control.speed.effective_value,
            limit_overrides=limit_overrides,
        )
        motion_control = self._finalize_motion_control(
            servo_ids=servo_ids,
            base=motion_control,
            speed_verified=True,
        )
        outcome = BodyCommandOutcomeRecord(
            command_type=command_type,
            requested_action_name=requested_action_name or command_type,
            canonical_action_name=requested_action_name or command_type,
            source_action_name=requested_action_name or command_type,
            outcome_status="sent",
            accepted=True,
            transport_mode=self.transport.status.mode,
            reason_code=self.transport.status.reason_code,
            outcome_notes=list(frame.compiler_notes),
            motion_control=motion_control,
            generated_at=utc_now(),
        )
        health, outcome = self._poll_health_with_confirmation(
            target_positions=frame.servo_targets,
            last_command_outcome=outcome,
            servo_ids=servo_ids,
        )
        return outcome, health

    def safe_idle(
        self,
        *,
        torque_off: bool,
        neutral_frame: CompiledBodyFrame,
    ) -> tuple[BodyCommandOutcomeRecord, dict[str, ServoHealthRecord]]:
        if torque_off:
            self._send_frame(neutral_frame)
            time.sleep(self._neutral_settle_seconds(neutral_frame))
            self.transport.set_torque(self._servo_ids(), enabled=False)
            outcome = BodyCommandOutcomeRecord(
                command_type="safe_idle",
                requested_action_name="safe_idle",
                canonical_action_name="safe_idle",
                source_action_name="safe_idle",
                outcome_status="neutral_recovered_torque_disabled",
                accepted=True,
                transport_mode=self.transport.status.mode,
                reason_code=self.transport.status.reason_code,
                outcome_notes=list(neutral_frame.compiler_notes),
                generated_at=utc_now(),
            )
            health, outcome = self._poll_health_with_confirmation(
                target_positions=neutral_frame.servo_targets,
                last_command_outcome=outcome,
                servo_ids=self._servo_ids_for_joint_targets(neutral_frame.servo_targets),
            )
            return outcome, health
        self._send_frame(neutral_frame)
        outcome = BodyCommandOutcomeRecord(
            command_type="safe_idle",
            requested_action_name="safe_idle",
            canonical_action_name="safe_idle",
            source_action_name="safe_idle",
            outcome_status="neutral_recovered",
            accepted=True,
            transport_mode=self.transport.status.mode,
            reason_code=self.transport.status.reason_code,
            outcome_notes=list(neutral_frame.compiler_notes),
            generated_at=utc_now(),
        )
        health, outcome = self._poll_health_with_confirmation(
            target_positions=neutral_frame.servo_targets,
            last_command_outcome=outcome,
            servo_ids=self._servo_ids_for_joint_targets(neutral_frame.servo_targets),
        )
        return outcome, health

    def poll_health(
        self,
        *,
        target_positions: dict[str, int] | None = None,
        last_command_outcome: BodyCommandOutcomeRecord | None = None,
    ) -> dict[str, ServoHealthRecord]:
        return collect_servo_health(
            profile=self.profile,
            transport=self.transport,
            target_positions=target_positions,
            last_command_outcome=last_command_outcome,
        )

    def _poll_health_with_confirmation(
        self,
        *,
        target_positions: dict[str, int] | None,
        last_command_outcome: BodyCommandOutcomeRecord,
        servo_ids: list[int],
    ) -> tuple[dict[str, ServoHealthRecord], BodyCommandOutcomeRecord]:
        try:
            health = self.poll_health(
                target_positions=target_positions,
                last_command_outcome=last_command_outcome,
            )
        except ServoTransportError as exc:
            return self._recover_from_health_poll_failure(
                target_positions=target_positions,
                last_command_outcome=last_command_outcome,
                servo_ids=servo_ids,
                error=exc,
                confirmation_attempted=False,
            )
        if self.transport.status.mode != LIVE_SERIAL_MODE:
            return health, last_command_outcome

        suspect_voltage = _suspicious_voltage_joints(health)
        implausible = _implausible_readback_joints(health=health, bridge=self)
        if not suspect_voltage and not implausible:
            return health, last_command_outcome

        confirmation_result = "pending_confirmation"
        time.sleep(SUSPECT_CONFIRMATION_DELAY_SECONDS)
        try:
            retry_health = self.poll_health(
                target_positions=target_positions,
                last_command_outcome=last_command_outcome,
            )
        except ServoTransportError as exc:
            return self._recover_from_health_poll_failure(
                target_positions=target_positions,
                last_command_outcome=last_command_outcome,
                servo_ids=servo_ids,
                error=exc,
                confirmation_attempted=True,
                prior_health=health,
                suspect_voltage=suspect_voltage,
                implausible=implausible,
            )
        retry_voltage = _suspicious_voltage_joints(retry_health)
        retry_implausible = _implausible_readback_joints(health=retry_health, bridge=self)
        confirmed = False
        classification: str | None = None

        if retry_voltage or retry_implausible:
            extended = read_bench_health_many(self.transport, servo_ids)
            retry_health = self._merge_extended_health(
                retry_health,
                extended=extended,
            )
            low_voltage_joints = [
                record.joint_name
                for record in retry_health.values()
                if record.voltage is not None and int(record.voltage) <= LOW_VOLTAGE_THRESHOLD
            ]
            if low_voltage_joints:
                confirmed = True
                classification = "confirmed_power_fault"
                confirmation_result = f"confirmed_low_voltage:{','.join(sorted(low_voltage_joints))}"
            elif retry_voltage and retry_implausible:
                confirmed = True
                classification = "confirmed_power_fault"
                confirmation_result = "confirmed_repeated_voltage_and_divergence"
            else:
                classification = "suspect_voltage_event" if (suspect_voltage or retry_voltage) else "readback_implausible"
                confirmation_result = "suspect_after_extended_health"
        else:
            classification = "suspect_voltage_event" if suspect_voltage else "readback_implausible"
            confirmation_result = "cleared_on_retry"

        power_health_classification, _power_reason = _power_health_snapshot(
            retry_health,
            idle_preflight=False,
        )
        if confirmed:
            power_health_classification = "confirmed_power_fault"

        updated_outcome = last_command_outcome.model_copy(
            update={
                "fault_classification": classification,
                "power_health_classification": power_health_classification,
                "suspect_voltage_event": bool(suspect_voltage or retry_voltage),
                "readback_implausible": bool(implausible or retry_implausible),
                "confirmation_read_performed": True,
                "confirmation_result": confirmation_result,
            },
            deep=True,
        )
        if confirmed:
            updated_outcome.detail = confirmation_result
        return retry_health, updated_outcome

    def _recover_from_health_poll_failure(
        self,
        *,
        target_positions: dict[str, int] | None,
        last_command_outcome: BodyCommandOutcomeRecord,
        servo_ids: list[int],
        error: ServoTransportError,
        confirmation_attempted: bool,
        prior_health: dict[str, ServoHealthRecord] | None = None,
        suspect_voltage: list[str] | None = None,
        implausible: list[str] | None = None,
    ) -> tuple[dict[str, ServoHealthRecord], BodyCommandOutcomeRecord]:
        bench_health = read_bench_health_many(self.transport, servo_ids)
        recovered_health = servo_health_from_bench_reads(
            profile=self.profile,
            bench_health=bench_health,
            target_positions=target_positions,
            last_command_outcome=last_command_outcome,
        )
        if prior_health:
            for joint_name, record in prior_health.items():
                recovered_health.setdefault(joint_name, record)
        recovered_voltage = _suspicious_voltage_joints(recovered_health)
        recovered_implausible = _implausible_readback_joints(health=recovered_health, bridge=self)
        power_health_classification, power_reason = _power_health_snapshot(
            recovered_health,
            idle_preflight=False,
        )
        confirmation_result = f"health_poll_error:{error.classification}:{error.detail}"
        fault_classification = "readback_degraded"
        if power_health_classification == "confirmed_power_fault":
            fault_classification = "confirmed_power_fault"
            confirmation_result = power_reason or confirmation_result
        elif recovered_voltage or suspect_voltage:
            fault_classification = "suspect_voltage_event"
        elif recovered_implausible or implausible:
            fault_classification = "readback_implausible"
        updated_outcome = last_command_outcome.model_copy(
            update={
                "outcome_status": "sent_with_readback_warning",
                "accepted": True,
                "rejected": False,
                "reason_code": error.classification,
                "detail": confirmation_result,
                "fault_classification": fault_classification,
                "power_health_classification": power_health_classification,
                "suspect_voltage_event": bool(recovered_voltage or suspect_voltage),
                "readback_implausible": bool(recovered_implausible or implausible),
                "confirmation_read_performed": confirmation_attempted,
                "confirmation_result": confirmation_result,
                "outcome_notes": [
                    *list(last_command_outcome.outcome_notes),
                    f"health_poll_warning:{error.classification}:{error.detail}",
                ],
            },
            deep=True,
        )
        return recovered_health, updated_outcome

    def _merge_extended_health(
        self,
        health: dict[str, ServoHealthRecord],
        *,
        extended: dict[int, dict[str, object]],
        power_health_classification: str | None = None,
    ) -> dict[str, ServoHealthRecord]:
        enriched: dict[str, ServoHealthRecord] = {}
        for joint_name, record in health.items():
            payload = extended.get(int(record.servo_id), {})
            status_summary = str(payload.get("status_summary") or record.status_summary or "")
            if payload.get("error") is not None:
                status_summary = f"{status_summary}; extended_error={payload['error']}" if status_summary else str(payload["error"])
            enriched[joint_name] = record.model_copy(
                update={
                    "voltage": int(payload["voltage"]) if payload.get("voltage") is not None else record.voltage,
                    "voltage_raw": int(payload["voltage_raw"]) if payload.get("voltage_raw") is not None else (
                        int(payload["voltage"]) if payload.get("voltage") is not None else record.voltage_raw
                    ),
                    "voltage_volts": (
                        float(payload["voltage_volts"])
                        if payload.get("voltage_volts") is not None
                        else record.voltage_volts
                    ),
                    "load": int(payload["load"]) if payload.get("load") is not None else record.load,
                    "current": int(payload["current"]) if payload.get("current") is not None else record.current,
                    "temperature": int(payload["temperature"]) if payload.get("temperature") is not None else record.temperature,
                    "moving": bool(payload["moving"]) if payload.get("moving") is not None else record.moving,
                    "power_health_classification": power_health_classification or record.power_health_classification,
                    "status_summary": status_summary or record.status_summary,
                },
                deep=True,
            )
        return enriched

    def inspect_motion_control_settings(
        self,
        *,
        servo_ids: list[int] | None = None,
        speed_override: int | None = None,
        acceleration_override: int | None = None,
        apply_acceleration: bool = False,
    ) -> BodyMotionControlAuditRecord:
        target_servo_ids = sorted({int(servo_id) for servo_id in (servo_ids or self._servo_ids())})
        acceleration_applied = False
        if apply_acceleration and target_servo_ids:
            effective_acceleration = self._safe_acceleration(acceleration_override)
            if effective_acceleration is not None:
                self.transport.sync_write_start_acceleration(
                    [(servo_id, effective_acceleration) for servo_id in target_servo_ids]
                )
                acceleration_applied = True
        return self._build_motion_control_audit(
            servo_ids=target_servo_ids,
            speed_override=speed_override,
            acceleration_override=acceleration_override,
            verify_speed=False,
            verify_acceleration=bool(target_servo_ids),
            acceleration_applied=acceleration_applied,
        )

    def _send_frame(
        self,
        frame: CompiledBodyFrame,
        *,
        speed: int | None = None,
        limit_overrides: dict[str, tuple[int, int]] | None = None,
    ) -> None:
        writes: list[tuple[int, bytes]] = []
        duration_ms = self._resolved_duration_ms(frame)
        resolved_speed = max(0, min(0xFFFF, int(speed if speed is not None else self._safe_speed())))
        for joint in self.profile.joints:
            if not joint.enabled:
                continue
            target = frame.servo_targets.get(joint.joint_name)
            if target is None:
                continue
            raw_min, raw_max = self._limits_for_joint(
                joint.joint_name,
                default_min=joint.raw_min,
                default_max=joint.raw_max,
                limit_overrides=limit_overrides,
            )
            if not raw_min <= target <= raw_max:
                raise ServoTransportError(
                    "out_of_range",
                    f"joint_target_out_of_range:{joint.joint_name}:{target}:{raw_min}-{raw_max}",
                )
            payload = build_target_position_payload(position=target, duration_ms=duration_ms, speed=resolved_speed)
            for servo_id in joint.servo_ids:
                writes.append((servo_id, payload))
        self.transport.sync_write(ADDRESS_TARGET_POSITION, writes, data_length=6)

    def _wait_for_frame_dwell(self, frame: CompiledBodyFrame) -> None:
        if self.transport.status.mode != LIVE_SERIAL_MODE:
            return
        remaining = self._frame_dwell_seconds(frame)
        while remaining > 0:
            sleep_seconds = min(0.02, remaining)
            time.sleep(sleep_seconds)
            remaining -= sleep_seconds

    def _resolved_duration_ms(self, frame: CompiledBodyFrame) -> int:
        duration_floor = int(self.profile.minimum_transition_ms or 120)
        return max(duration_floor, min(0xFFFF, int(frame.duration_ms or self.profile.default_transition_ms or 120)))

    def _frame_dwell_seconds(self, frame: CompiledBodyFrame) -> float:
        hold_ms = max(0, int(frame.hold_ms or 0))
        return max(0.0, float(self._resolved_duration_ms(frame) + hold_ms) / 1000.0)

    def _joint_neutral(self, joint_name: str, *, default_neutral: int) -> int:
        if self.calibration is not None:
            for record in self.calibration.joint_records:
                if record.joint_name == joint_name:
                    return int(record.neutral)
        return default_neutral

    def _peak_compiled_targets(self, compiled: CompiledAnimation) -> dict[str, int]:
        peak_targets: dict[str, int] = {}
        peak_distance: dict[str, int] = {}
        joint_profiles = {joint.joint_name: joint for joint in self.profile.joints}
        for frame in compiled.frames:
            for joint_name, target in frame.servo_targets.items():
                joint = joint_profiles.get(joint_name)
                if joint is None:
                    continue
                neutral = self._joint_neutral(joint_name, default_neutral=int(joint.neutral))
                distance = abs(int(target) - neutral)
                if distance >= peak_distance.get(joint_name, -1):
                    peak_targets[joint_name] = int(target)
                    peak_distance[joint_name] = distance
        return peak_targets

    def _peak_normalized_pose(self, compiled: CompiledAnimation) -> dict[str, float]:
        peak_fields = ("head_pitch", "head_yaw", "head_roll")
        peaks: dict[str, float] = {}
        for field_name in peak_fields:
            best_value = 0.0
            best_abs = -1.0
            for frame in compiled.frames:
                value = float(getattr(frame.pose, field_name, 0.0))
                if abs(value) >= best_abs:
                    best_value = value
                    best_abs = abs(value)
            peaks[field_name] = round(best_value, 4)
        return peaks

    def _limits_for_joint(
        self,
        joint_name: str,
        *,
        default_min: int,
        default_max: int,
        limit_overrides: dict[str, tuple[int, int]] | None = None,
    ) -> tuple[int, int]:
        if limit_overrides is not None and joint_name in limit_overrides:
            low, high = limit_overrides[joint_name]
            return int(low), int(high)
        if self.calibration is None:
            return default_min, default_max
        for record in self.calibration.joint_records:
            if record.joint_name == joint_name:
                return record.raw_min, record.raw_max
        return default_min, default_max

    def _safe_speed(self) -> int:
        if self.calibration is not None and self.calibration.safe_speed is not None:
            resolved = int(self.calibration.safe_speed)
        else:
            resolved = int(self.profile.safe_speed or 120)
        if self.profile.safe_speed_ceiling is not None:
            resolved = min(resolved, int(self.profile.safe_speed_ceiling))
        return resolved

    def _safe_acceleration(self, override: int | None = None) -> int | None:
        if override is not None:
            resolved = int(override)
        elif self.calibration is not None and self.calibration.safe_acceleration is not None:
            resolved = int(self.calibration.safe_acceleration)
        elif self.profile.safe_acceleration is not None:
            resolved = int(self.profile.safe_acceleration)
        else:
            return None
        return max(0, min(150, resolved))

    def _neutral_settle_seconds(self, frame: CompiledBodyFrame) -> float:
        transition_ms = max(
            int(self.profile.minimum_transition_ms or 80),
            int(frame.duration_ms or self.profile.neutral_recovery_ms or self.profile.default_transition_ms or 120),
        )
        hold_ms = max(0, int(frame.hold_ms or 0))
        settle_ms = min(max(transition_ms + hold_ms, 150), 2000)
        return settle_ms / 1000.0

    def _servo_ids(self) -> list[int]:
        ids: list[int] = []
        for joint in self.profile.joints:
            ids.extend(joint.servo_ids)
        return sorted({servo_id for servo_id in ids})

    def _servo_ids_for_animation(self, compiled: CompiledAnimation) -> list[int]:
        servo_ids: set[int] = set()
        joint_ids = {
            joint.joint_name: [int(servo_id) for servo_id in joint.servo_ids]
            for joint in self.profile.joints
            if joint.enabled
        }
        for frame in compiled.frames:
            for joint_name in frame.servo_targets:
                servo_ids.update(joint_ids.get(joint_name, []))
        return sorted(servo_ids)

    def _servo_ids_for_joint_targets(self, servo_targets: dict[str, int]) -> list[int]:
        servo_ids: set[int] = set()
        for joint in self.profile.joints:
            if not joint.enabled:
                continue
            if joint.joint_name in servo_targets:
                servo_ids.update(int(servo_id) for servo_id in joint.servo_ids)
        return sorted(servo_ids)

    def _prepare_motion_control(
        self,
        servo_ids: list[int],
        *,
        speed_override: int | None = None,
        acceleration_override: int | None = None,
    ) -> BodyMotionControlAuditRecord:
        effective_acceleration = self._safe_acceleration(acceleration_override)
        acceleration_applied = False
        if servo_ids and effective_acceleration is not None:
            self.transport.sync_write_start_acceleration(
                [(servo_id, effective_acceleration) for servo_id in servo_ids]
            )
            acceleration_applied = True
        return self._build_motion_control_audit(
            servo_ids=servo_ids,
            speed_override=speed_override,
            acceleration_override=acceleration_override,
            verify_speed=False,
            verify_acceleration=bool(servo_ids),
            acceleration_applied=acceleration_applied,
        )

    def _finalize_motion_control(
        self,
        *,
        servo_ids: list[int],
        base: BodyMotionControlAuditRecord,
        speed_verified: bool,
    ) -> BodyMotionControlAuditRecord:
        speed_override = base.speed.configured_value if base.speed.source == "override" else None
        acceleration_override = (
            base.acceleration.configured_value if base.acceleration.source == "override" else None
        )
        return self._build_motion_control_audit(
            servo_ids=servo_ids,
            speed_override=speed_override,
            acceleration_override=acceleration_override,
            verify_speed=speed_verified,
            verify_acceleration=base.acceleration.applied,
            acceleration_applied=base.acceleration.applied,
        )

    def _build_motion_control_audit(
        self,
        *,
        servo_ids: list[int],
        speed_override: int | None,
        acceleration_override: int | None,
        verify_speed: bool,
        verify_acceleration: bool,
        acceleration_applied: bool,
    ) -> BodyMotionControlAuditRecord:
        speed_readback: dict[int, int] | None = None
        acceleration_readback: dict[int, int] | None = None
        notes: list[str] = []
        if servo_ids and verify_speed:
            try:
                speed_readback = self.transport.sync_read_running_speed_register(servo_ids)
            except ServoTransportError as exc:
                notes.append(f"speed_readback_error:{exc.classification}:{exc.detail}")
        if servo_ids and verify_acceleration:
            try:
                acceleration_readback = self.transport.sync_read_start_acceleration(servo_ids)
            except ServoTransportError as exc:
                notes.append(f"acceleration_readback_error:{exc.classification}:{exc.detail}")
        audit = build_motion_control_audit(
            profile=self.profile,
            calibration=self.calibration,
            transport_mode=self.transport.status.mode,
            transport_confirmed_live=self.transport.status.confirmed_live,
            addressed_servo_ids=servo_ids,
            speed_override=speed_override,
            acceleration_override=acceleration_override,
            speed_readback=speed_readback,
            acceleration_readback=acceleration_readback,
            acceleration_applied=acceleration_applied,
        )
        if notes:
            audit.notes.extend(notes)
        return audit


__all__ = ["FeetechBodyBridge"]
