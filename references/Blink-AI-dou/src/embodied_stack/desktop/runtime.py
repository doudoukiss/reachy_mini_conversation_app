from __future__ import annotations

from dataclasses import dataclass
import logging

from embodied_stack.body import BodyCommandApplyError, SerialBodyDriver, ServoTransportError, build_body_driver
from embodied_stack.body.serial import list_serial_ports
from embodied_stack.config import Settings
from embodied_stack.observability import log_event
from embodied_stack.shared.models import (
    CharacterProjectionProfile,
    CharacterSemanticIntent,
    BodyDriverMode,
    CapabilityProfile,
    CommandAck,
    CommandAckStatus,
    CommandHistoryEntry,
    CommandHistoryResponse,
    CommandType,
    EdgeAdapterCapability,
    EdgeAdapterDirection,
    EdgeAdapterHealth,
    EdgeAdapterKind,
    EdgeAdapterState,
    EdgeTransportMode,
    HeartbeatStatus,
    RobotCommand,
    RobotEvent,
    RobotMode,
    SimulatedSensorEventRequest,
    SimulatedSensorEventResult,
    TelemetryLogEntry,
    TelemetryLogResponse,
    TelemetrySnapshot,
    TransportState,
    utc_now,
)

from .profiles import body_driver_mode_for_runtime

logger = logging.getLogger(__name__)

MAX_HEAD_YAW_DEG = 60.0
MAX_HEAD_PITCH_DEG = 25.0
SAFE_IDLE_STOP_REASONS = {
    "safe_idle",
    "operator_override",
    "transport_degraded",
    "low_battery",
    "edge_transport_degraded",
}
NETWORK_SAFE_IDLE_REASONS = {"network_degraded", "edge_transport_degraded", "heartbeat_timeout"}


class DesktopEmbodimentRuntime:
    def __init__(self, *, settings: Settings) -> None:
        self.settings = settings
        self.body_driver = build_body_driver(settings)
        self.telemetry_log: list[TelemetryLogEntry] = []
        self.reset()

    def reset(self) -> None:
        self.body_driver.reset()
        now = utc_now()
        self.heartbeat = HeartbeatStatus(
            connected=True,
            network_ok=True,
            safe_idle_active=False,
            transport_ok=True,
            timeout_seconds=self.settings.edge_heartbeat_timeout_seconds,
            last_contact_at=now,
        )
        self.telemetry = TelemetrySnapshot(
            mode=self.settings.blink_runtime_mode,
            runtime_profile=self.settings.brain_runtime_profile,
            body_driver_mode=body_driver_mode_for_runtime(self.settings),
            body_state=self.body_driver.state.model_copy(deep=True),
            body_capabilities=self.body_driver.capabilities.model_copy(deep=True),
            camera_source=self.settings.blink_camera_source,
            voice_profile=self.settings.blink_voice_profile,
            battery_pct=100.0,
            network_ok=True,
            transport_ok=True,
            adapter_health=self._adapter_health(now),
            last_updated=now,
        )
        self._sync_body_into_telemetry()
        self._record("desktop_runtime_reset", "desktop", now)

    @property
    def capabilities(self) -> CapabilityProfile:
        return CapabilityProfile(
            mode=self.settings.blink_runtime_mode,
            runtime_profile=self.settings.brain_runtime_profile,
            body_driver_mode=body_driver_mode_for_runtime(self.settings),
            body_capabilities=self.body_driver.capabilities.model_copy(deep=True),
            head_profile_path=self.settings.blink_head_profile,
            supports_voice_output=True,
            supports_led=True,
            supports_head_pose=True,
            supports_display=True,
            supports_semantic_body=True,
            supports_virtual_body_preview=self.body_driver.capabilities.supports_virtual_preview,
            supports_touch_sensor=True,
            supports_button_sensor=True,
            supports_person_detection=True,
            supports_network_monitor=True,
            supports_battery_monitor=True,
            supports_heartbeat_monitor=True,
            supports_simulated_events=True,
            adapters=[adapter.capability() for adapter in self._adapters()],
        )

    def get_telemetry(self) -> TelemetrySnapshot:
        self._sync_body_into_telemetry()
        self.telemetry.adapter_health = self._adapter_health()
        return self.telemetry.model_copy(deep=True)

    def get_telemetry_log(self) -> TelemetryLogResponse:
        return TelemetryLogResponse(items=[item.model_copy(deep=True) for item in self.telemetry_log])

    def get_heartbeat(self) -> HeartbeatStatus:
        return self.heartbeat.model_copy(deep=True)

    def get_body_status(self) -> dict[str, object]:
        return self._body_action_result(status="ok", payload={"available_ports": self._available_body_ports()}, refresh_body=False)

    def apply_character_projection(
        self,
        *,
        intent: CharacterSemanticIntent,
        profile: CharacterProjectionProfile | None = None,
    ):
        state = self.body_driver.apply_character_projection(intent=intent, profile=profile)
        self._sync_body_into_telemetry()
        return state.model_copy(deep=True)

    def connect_body(
        self,
        *,
        port: str | None = None,
        baud: int | None = None,
        timeout_seconds: float | None = None,
    ) -> dict[str, object]:
        driver = self._serial_body_driver()
        if driver is None:
            return self._body_action_result(status="unsupported", detail="serial_body_driver_not_active", refresh_body=False)
        try:
            payload = driver.connect(port=port, baud=baud, timeout_seconds=timeout_seconds)
        except (BodyCommandApplyError, ServoTransportError) as exc:
            detail = exc.detail if isinstance(exc, BodyCommandApplyError) else f"{exc.classification}:{exc.detail}"
            return self._body_action_result(status="error", detail=detail, refresh_body=False)
        return self._body_action_result(status=str(payload.get("status") or "ok"), detail=payload.get("detail"), payload=payload, refresh_body=False)

    def disconnect_body(self) -> dict[str, object]:
        driver = self._serial_body_driver()
        if driver is None:
            return self._body_action_result(status="unsupported", detail="serial_body_driver_not_active", refresh_body=False)
        payload = driver.disconnect()
        return self._body_action_result(status=str(payload.get("status") or "ok"), detail=payload.get("detail"), payload=payload, refresh_body=False)

    def scan_body(self, *, ids: list[int] | None = None) -> dict[str, object]:
        driver = self._serial_body_driver()
        if driver is None:
            return self._body_action_result(status="unsupported", detail="serial_body_driver_not_active", refresh_body=False)
        try:
            payload = driver.scan(ids=ids)
        except (BodyCommandApplyError, ServoTransportError) as exc:
            detail = exc.detail if isinstance(exc, BodyCommandApplyError) else f"{exc.classification}:{exc.detail}"
            return self._body_action_result(status="error", detail=detail, refresh_body=False)
        return self._body_action_result(
            status="ok",
            detail=payload.get("failure_summary", []),
            payload=payload,
            report_path=payload.get("report_path"),
            refresh_body=False,
        )

    def ping_body(self, *, ids: list[int] | None = None) -> dict[str, object]:
        driver = self._serial_body_driver()
        if driver is None:
            return self._body_action_result(status="unsupported", detail="serial_body_driver_not_active", refresh_body=False)
        try:
            payload = driver.ping(ids=ids)
        except (BodyCommandApplyError, ServoTransportError) as exc:
            detail = exc.detail if isinstance(exc, BodyCommandApplyError) else f"{exc.classification}:{exc.detail}"
            return self._body_action_result(status="error", detail=detail, refresh_body=False)
        return self._body_action_result(status="ok", detail=None, payload=payload, refresh_body=False)

    def read_body_health(self, *, ids: list[int] | None = None) -> dict[str, object]:
        driver = self._serial_body_driver()
        if driver is None:
            return self._body_action_result(status="unsupported", detail="serial_body_driver_not_active", refresh_body=False)
        try:
            payload = driver.read_health(ids=ids)
        except (BodyCommandApplyError, ServoTransportError) as exc:
            detail = exc.detail if isinstance(exc, BodyCommandApplyError) else f"{exc.classification}:{exc.detail}"
            return self._body_action_result(status="error", detail=detail, refresh_body=False)
        return self._body_action_result(status="ok", detail=None, payload=payload, refresh_body=False)

    def arm_body_motion(self, *, ttl_seconds: float = 60.0, author: str | None = None) -> dict[str, object]:
        driver = self._serial_body_driver()
        if driver is None:
            return self._body_action_result(status="unsupported", detail="serial_body_driver_not_active", refresh_body=False)
        try:
            payload = driver.arm_live_motion(
                ttl_seconds=ttl_seconds,
                author=author or "desktop_runtime.arm_body_motion",
            )
        except (BodyCommandApplyError, ServoTransportError) as exc:
            detail = exc.detail if isinstance(exc, BodyCommandApplyError) else f"{exc.classification}:{exc.detail}"
            return self._body_action_result(status="error", detail=detail, refresh_body=False)
        return self._body_action_result(status=str(payload.get("status") or "ok"), detail=payload.get("detail"), payload=payload, refresh_body=False)

    def disarm_body_motion(self) -> dict[str, object]:
        driver = self._serial_body_driver()
        if driver is None:
            return self._body_action_result(status="unsupported", detail="serial_body_driver_not_active", refresh_body=False)
        payload = driver.disarm_live_motion()
        return self._body_action_result(status=str(payload.get("status") or "ok"), detail=payload.get("detail"), payload=payload, refresh_body=False)

    def write_body_neutral(self, *, author: str | None = None) -> dict[str, object]:
        driver = self._serial_body_driver()
        if driver is None:
            return self._body_action_result(status="unsupported", detail="serial_body_driver_not_active", refresh_body=False)
        try:
            payload = driver.write_neutral(author=author)
        except (BodyCommandApplyError, ServoTransportError) as exc:
            detail = exc.detail if isinstance(exc, BodyCommandApplyError) else f"{exc.classification}:{exc.detail}"
            return self._body_action_result(status="error", detail=detail, refresh_body=False)
        return self._body_action_result(
            status="ok" if payload.get("success") else "degraded",
            detail=payload.get("failure_reason"),
            payload=payload,
            motion_report_path=payload.get("report_path"),
            refresh_body=False,
        )

    def run_body_power_preflight(self) -> dict[str, object]:
        driver = self._serial_body_driver()
        if driver is None:
            return self._body_action_result(status="unsupported", detail="serial_body_driver_not_active", refresh_body=False)
        try:
            payload = driver.run_power_preflight()
        except (BodyCommandApplyError, ServoTransportError) as exc:
            detail = exc.detail if isinstance(exc, BodyCommandApplyError) else f"{exc.classification}:{exc.detail}"
            return self._body_action_result(status="error", detail=detail, refresh_body=False)
        return self._body_action_result(
            status=str(payload.get("status") or "ok"),
            detail=payload.get("detail"),
            payload=payload.get("payload") or payload,
            refresh_body=False,
        )

    def get_body_servo_lab_catalog(self) -> dict[str, object]:
        driver = self._serial_body_driver()
        if driver is None:
            return self._body_action_result(status="unsupported", detail="serial_body_driver_not_active", refresh_body=False)
        try:
            payload = driver.servo_lab_catalog()
        except (BodyCommandApplyError, ServoTransportError) as exc:
            detail = exc.detail if isinstance(exc, BodyCommandApplyError) else f"{exc.classification}:{exc.detail}"
            return self._body_action_result(status="error", detail=detail, refresh_body=False)
        return self._body_action_result(
            status=str(payload.get("status") or "ok"),
            detail=payload.get("detail"),
            payload=payload.get("payload") or payload,
            refresh_body=False,
        )

    def read_body_servo_lab(
        self,
        *,
        joint_name: str | None = None,
        include_health: bool = True,
    ) -> dict[str, object]:
        driver = self._serial_body_driver()
        if driver is None:
            return self._body_action_result(status="unsupported", detail="serial_body_driver_not_active", refresh_body=False)
        try:
            payload = driver.servo_lab_readback(joint_name=joint_name, include_health=include_health)
        except (BodyCommandApplyError, ServoTransportError) as exc:
            detail = exc.detail if isinstance(exc, BodyCommandApplyError) else f"{exc.classification}:{exc.detail}"
            return self._body_action_result(status="error", detail=detail, refresh_body=False)
        return self._body_action_result(
            status=str(payload.get("status") or "ok"),
            detail=payload.get("detail"),
            payload=payload.get("payload") or payload,
            refresh_body=False,
        )

    def move_body_servo_lab(
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
        driver = self._serial_body_driver()
        if driver is None:
            return self._body_action_result(status="unsupported", detail="serial_body_driver_not_active", refresh_body=False)
        try:
            payload = driver.servo_lab_move(
                joint_name=joint_name,
                reference_mode=reference_mode,
                target_raw=target_raw,
                delta_counts=delta_counts,
                lab_min=lab_min,
                lab_max=lab_max,
                duration_ms=duration_ms,
                speed_override=speed_override,
                acceleration_override=acceleration_override,
                note=note,
            )
        except (BodyCommandApplyError, ServoTransportError, ValueError) as exc:
            if isinstance(exc, BodyCommandApplyError):
                detail = exc.detail
            elif isinstance(exc, ServoTransportError):
                detail = f"{exc.classification}:{exc.detail}"
            else:
                detail = str(exc)
            return self._body_action_result(status="error", detail=detail, refresh_body=False)
        success = bool(payload.get("success", False))
        return self._body_action_result(
            status="ok" if success else "degraded",
            detail=payload.get("failure_reason"),
            payload=payload,
            motion_report_path=payload.get("report_path"),
            refresh_body=False,
        )

    def sweep_body_servo_lab(
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
        driver = self._serial_body_driver()
        if driver is None:
            return self._body_action_result(status="unsupported", detail="serial_body_driver_not_active", refresh_body=False)
        try:
            payload = driver.servo_lab_sweep(
                joint_name=joint_name,
                lab_min=lab_min,
                lab_max=lab_max,
                cycles=cycles,
                duration_ms=duration_ms,
                dwell_ms=dwell_ms,
                speed_override=speed_override,
                acceleration_override=acceleration_override,
                return_to_neutral=return_to_neutral,
                note=note,
            )
        except (BodyCommandApplyError, ServoTransportError, ValueError) as exc:
            if isinstance(exc, BodyCommandApplyError):
                detail = exc.detail
            elif isinstance(exc, ServoTransportError):
                detail = f"{exc.classification}:{exc.detail}"
            else:
                detail = str(exc)
            return self._body_action_result(status="error", detail=detail, refresh_body=False)
        success = bool(payload.get("success", False))
        return self._body_action_result(
            status="ok" if success else "degraded",
            detail=payload.get("failure_reason"),
            payload=payload,
            motion_report_path=payload.get("report_path"),
            refresh_body=False,
        )

    def save_body_servo_lab_calibration(
        self,
        *,
        joint_name: str,
        save_current_as_neutral: bool = False,
        raw_min: int | None = None,
        raw_max: int | None = None,
        confirm_mirrored: bool | None = None,
        note: str | None = None,
    ) -> dict[str, object]:
        driver = self._serial_body_driver()
        if driver is None:
            return self._body_action_result(status="unsupported", detail="serial_body_driver_not_active", refresh_body=False)
        try:
            payload = driver.servo_lab_save_calibration(
                joint_name=joint_name,
                save_current_as_neutral=save_current_as_neutral,
                raw_min=raw_min,
                raw_max=raw_max,
                confirm_mirrored=confirm_mirrored,
                note=note,
            )
        except (BodyCommandApplyError, ServoTransportError, ValueError) as exc:
            if isinstance(exc, BodyCommandApplyError):
                detail = exc.detail
            elif isinstance(exc, ServoTransportError):
                detail = f"{exc.classification}:{exc.detail}"
            else:
                detail = str(exc)
            return self._body_action_result(status="error", detail=detail, refresh_body=False)
        return self._body_action_result(
            status=str(payload.get("status") or "ok"),
            detail=payload.get("detail"),
            payload=payload.get("payload") or payload,
            refresh_body=False,
        )

    def get_body_semantic_library(self, *, smoke_safe_only: bool = False) -> dict[str, object]:
        payload = self.body_driver.semantic_library(smoke_safe_only=smoke_safe_only)
        return self._body_action_result(status="ok", detail=None, payload=payload.get("payload") or payload, refresh_body=False)

    def get_body_expression_catalog(self) -> dict[str, object]:
        payload = self.body_driver.expression_catalog()
        return self._body_action_result(status="ok", detail=None, payload=payload.get("payload") or payload, refresh_body=False)

    def run_body_semantic_smoke(
        self,
        *,
        action: str = "look_left",
        intensity: float = 1.0,
        repeat_count: int = 1,
        note: str | None = None,
        allow_bench_actions: bool = False,
    ) -> dict[str, object]:
        try:
            payload = self.body_driver.run_semantic_smoke(
                action=action,
                intensity=intensity,
                repeat_count=repeat_count,
                note=note,
                allow_bench_actions=allow_bench_actions,
            )
        except (BodyCommandApplyError, ServoTransportError, ValueError) as exc:
            if isinstance(exc, BodyCommandApplyError):
                detail = exc.detail
            elif isinstance(exc, ServoTransportError):
                detail = f"{exc.classification}:{exc.detail}"
            else:
                detail = str(exc)
            return self._body_action_result(status="error", detail=detail, refresh_body=False)
        return self._body_action_result(status=str(payload.get("status") or "ok"), detail=payload.get("detail"), payload=payload, refresh_body=False)

    def run_body_primitive_sequence(
        self,
        *,
        steps: list[dict[str, object]],
        note: str | None = None,
        sequence_name: str = "body_primitive_sequence",
    ) -> dict[str, object]:
        try:
            payload = self.body_driver.run_primitive_sequence(
                steps=steps,
                note=note,
                sequence_name=sequence_name,
            )
        except (BodyCommandApplyError, ServoTransportError, ValueError) as exc:
            if isinstance(exc, BodyCommandApplyError):
                detail = exc.detail
            elif isinstance(exc, ServoTransportError):
                detail = f"{exc.classification}:{exc.detail}"
            else:
                detail = str(exc)
            return self._body_action_result(status="error", detail=detail, refresh_body=False)
        return self._body_action_result(
            status=str(payload.get("status") or "ok"),
            detail=payload.get("detail"),
            payload=payload,
            refresh_body=False,
        )

    def run_body_expressive_motif(
        self,
        *,
        motif: dict[str, object] | None = None,
        steps: list[dict[str, object]] | None = None,
        note: str | None = None,
        sequence_name: str = "body_expressive_motif",
    ) -> dict[str, object]:
        try:
            payload = self.body_driver.run_expressive_sequence(
                motif_name=str(motif.get("motif_name")) if isinstance(motif, dict) and motif.get("motif_name") is not None else None,
                steps=list(steps or []),
                note=note,
                sequence_name=sequence_name,
            )
        except (BodyCommandApplyError, ServoTransportError, ValueError) as exc:
            if isinstance(exc, BodyCommandApplyError):
                detail = exc.detail
            elif isinstance(exc, ServoTransportError):
                detail = f"{exc.classification}:{exc.detail}"
            else:
                detail = str(exc)
            return self._body_action_result(status="error", detail=detail, refresh_body=False)
        return self._body_action_result(
            status=str(payload.get("status") or "ok"),
            detail=payload.get("detail"),
            payload=payload,
            refresh_body=False,
        )

    def run_body_staged_sequence(
        self,
        *,
        stages: list[dict[str, object]],
        note: str | None = None,
        sequence_name: str = "body_staged_sequence",
    ) -> dict[str, object]:
        try:
            payload = self.body_driver.run_staged_sequence(
                stages=stages,
                note=note,
                sequence_name=sequence_name,
            )
        except (BodyCommandApplyError, ServoTransportError, ValueError) as exc:
            if isinstance(exc, BodyCommandApplyError):
                detail = exc.detail
            elif isinstance(exc, ServoTransportError):
                detail = f"{exc.classification}:{exc.detail}"
            else:
                detail = str(exc)
            return self._body_action_result(status="error", detail=detail, refresh_body=False)
        return self._body_action_result(
            status=str(payload.get("status") or "ok"),
            detail=payload.get("detail"),
            payload=payload,
            refresh_body=False,
        )

    def run_body_range_demo(
        self,
        *,
        sequence_name: str | None = None,
        preset_name: str | None = None,
        note: str | None = None,
    ) -> dict[str, object]:
        try:
            payload = self.body_driver.run_range_demo(
                sequence_name=sequence_name,
                preset_name=preset_name,
                note=note,
            )
        except (BodyCommandApplyError, ServoTransportError, ValueError, KeyError) as exc:
            if isinstance(exc, BodyCommandApplyError):
                detail = exc.detail
            elif isinstance(exc, ServoTransportError):
                detail = f"{exc.classification}:{exc.detail}"
            else:
                detail = str(exc)
            return self._body_action_result(status="error", detail=detail, refresh_body=False)
        return self._body_action_result(
            status=str(payload.get("status") or "ok"),
            detail=payload.get("detail"),
            payload=payload,
            refresh_body=False,
        )

    def record_body_teacher_review(
        self,
        *,
        action: str,
        review: str,
        note: str | None = None,
        proposed_tuning_delta: dict[str, object] | None = None,
        apply_tuning: bool = False,
    ) -> dict[str, object]:
        driver = self._serial_body_driver()
        if driver is None:
            return self._body_action_result(status="unsupported", detail="serial_body_driver_not_active", refresh_body=False)
        try:
            payload = driver.record_teacher_review(
                action=action,
                review=review,
                note=note,
                proposed_tuning_delta=proposed_tuning_delta,
                apply_tuning=apply_tuning,
            )
        except (BodyCommandApplyError, ServoTransportError, ValueError) as exc:
            detail = exc.detail if isinstance(exc, BodyCommandApplyError) else str(exc)
            return self._body_action_result(status="error", detail=detail, refresh_body=False)
        return self._body_action_result(status="ok", detail=None, payload=payload.get("payload") or payload, refresh_body=False)

    def validate_command(self, command: RobotCommand) -> tuple[bool, str, dict]:
        if command.command_type == CommandType.MOVE_BASE:
            return False, "base_motion_not_supported_for_current_head", {}

        if self.heartbeat.safe_idle_active and command.command_type in {
            CommandType.SET_HEAD_POSE,
            CommandType.SET_GAZE,
            CommandType.SET_EXPRESSION,
            CommandType.PERFORM_GESTURE,
            CommandType.PERFORM_ANIMATION,
        }:
            return False, "safe_idle_rejects_body_motion", {}

        if command.command_type == CommandType.SET_HEAD_POSE:
            yaw = max(-MAX_HEAD_YAW_DEG, min(MAX_HEAD_YAW_DEG, float(command.payload.get("head_yaw_deg", 0.0))))
            pitch = max(-MAX_HEAD_PITCH_DEG, min(MAX_HEAD_PITCH_DEG, float(command.payload.get("head_pitch_deg", 0.0))))
            return True, "ok", {"head_yaw_deg": yaw, "head_pitch_deg": pitch}
        if command.command_type == CommandType.SET_GAZE:
            payload = dict(command.payload)
            if "yaw" in payload:
                payload["yaw"] = max(-1.0, min(1.0, float(payload["yaw"])))
            if "pitch" in payload:
                payload["pitch"] = max(-1.0, min(1.0, float(payload["pitch"])))
            return True, "ok", payload
        return True, "ok", dict(command.payload)

    def execute_command(self, command: RobotCommand, payload: dict) -> dict:
        now = utc_now()
        self.heartbeat.last_contact_at = now
        log_event(
            logger,
            logging.INFO,
            "desktop_command_started",
            command_id=command.command_id,
            body_batch_id=command.command_id,
            command_type=command.command_type.value,
        )

        if command.command_type == CommandType.SPEAK:
            self.telemetry.last_spoken_text = str(payload.get("text", ""))
            self.telemetry.speaking = False
        elif command.command_type == CommandType.DISPLAY_TEXT:
            self.telemetry.display_text = str(payload.get("text", ""))
        elif command.command_type == CommandType.SET_LED:
            self.telemetry.led_color = str(payload.get("color", "off"))
        elif command.command_type in {
            CommandType.SET_HEAD_POSE,
            CommandType.SET_EXPRESSION,
            CommandType.SET_GAZE,
            CommandType.PERFORM_GESTURE,
            CommandType.PERFORM_ANIMATION,
            CommandType.SAFE_IDLE,
        }:
            self.body_driver.apply_command(command, payload)
        elif command.command_type == CommandType.STOP:
            reason = str(payload.get("reason", "stop_command"))
            if reason in SAFE_IDLE_STOP_REASONS:
                self.force_safe_idle(reason)
            else:
                self.telemetry.speaking = False
                self.telemetry.last_sensor_event_type = f"stop:{reason}"

        if command.command_type == CommandType.SAFE_IDLE:
            self.force_safe_idle(str(payload.get("reason", "safe_idle")))
        elif not self.heartbeat.safe_idle_active:
            self.telemetry.mode = self.settings.blink_runtime_mode

        self._sync_body_into_telemetry()
        note = f"command:{command.command_type.value}"
        self._record(note, "desktop_command", now)
        log_event(
            logger,
            logging.INFO,
            "desktop_command_completed",
            command_id=command.command_id,
            body_batch_id=command.command_id,
            command_type=command.command_type.value,
            safe_idle_active=self.heartbeat.safe_idle_active,
        )
        return self.telemetry.model_dump(mode="json")

    def simulate_event(self, request: SimulatedSensorEventRequest) -> SimulatedSensorEventResult:
        now = request.timestamp or utc_now()
        self.heartbeat.last_contact_at = now
        event = RobotEvent(
            event_type=request.event_type,
            session_id=request.session_id,
            source=request.source,
            payload=dict(request.payload),
            timestamp=now,
        )

        if request.event_type == "network_state":
            network_ok = bool(request.payload.get("network_ok", True))
            self.telemetry.network_ok = network_ok
            self.telemetry.network_latency_ms = request.payload.get("latency_ms")
            event = RobotEvent(
                event_type="heartbeat",
                session_id=request.session_id,
                source=request.source,
                payload={
                    "network_ok": network_ok,
                    "latency_ms": request.payload.get("latency_ms"),
                    "mode": self.telemetry.mode.value,
                },
                timestamp=now,
            )
            if not network_ok:
                self.force_safe_idle("network_degraded")
        elif request.event_type == "low_battery":
            self.telemetry.battery_pct = float(request.payload.get("battery_pct", 10.0))
            if self.telemetry.battery_pct <= self.settings.shift_low_battery_threshold_pct:
                self.force_safe_idle("low_battery")
        elif request.event_type == "heartbeat" and not bool(request.payload.get("network_ok", True)):
            self.force_safe_idle("network_degraded")

        self.telemetry.last_sensor_event_type = event.event_type
        self._sync_body_into_telemetry()
        self._record(f"event:{event.event_type}", request.source, now)
        log_event(
            logger,
            logging.INFO,
            "desktop_event_simulated",
            session_id=request.session_id,
            event_id=event.event_id,
            event_type=event.event_type,
            source=request.source,
        )
        return SimulatedSensorEventResult(
            event=event,
            telemetry=self.get_telemetry(),
            heartbeat=self.get_heartbeat(),
        )

    def force_safe_idle(self, reason: str) -> HeartbeatStatus:
        now = utc_now()
        self.heartbeat.safe_idle_active = True
        self.heartbeat.safe_idle_reason = reason
        if reason in NETWORK_SAFE_IDLE_REASONS:
            self.heartbeat.connected = False
            self.heartbeat.network_ok = False
            self.telemetry.network_ok = False
        self.telemetry.mode = RobotMode.DEGRADED_SAFE_IDLE
        self.telemetry.safe_idle_reason = reason
        self.telemetry.display_text = f"Safe idle: {reason}"
        self.body_driver.safe_idle(reason)
        self._sync_body_into_telemetry()
        self._record(f"safe_idle:{reason}", "desktop_runtime", now)
        log_event(
            logger,
            logging.WARNING,
            "desktop_safe_idle_forced",
            body_batch_id="safe_idle",
            reason=reason,
        )
        return self.get_heartbeat()

    def _sync_body_into_telemetry(self, *, refresh_body: bool = True) -> None:
        if refresh_body and isinstance(self.body_driver, SerialBodyDriver):
            self.body_driver.refresh_live_status(force=False)
        state = self.body_driver.state.model_copy(deep=True)
        self.telemetry.body_state = state
        self.telemetry.body_capabilities = self.body_driver.capabilities.model_copy(deep=True)
        self.telemetry.body_driver_mode = state.driver_mode
        self.telemetry.head_yaw_deg = round(state.pose.head_yaw * MAX_HEAD_YAW_DEG, 2)
        self.telemetry.head_pitch_deg = round(state.pose.head_pitch * MAX_HEAD_PITCH_DEG, 2)
        self.telemetry.active_expression = state.active_expression
        self.telemetry.attention_state = state.attention_state
        self.telemetry.gaze_target = state.gaze_target
        self.telemetry.last_gesture = state.last_gesture
        self.telemetry.last_animation = state.last_animation
        if state.driver_mode == BodyDriverMode.SERIAL and state.transport_mode == "live_serial":
            self.telemetry.transport_ok = bool(state.transport_healthy)
            self.telemetry.transport_error = state.transport_error
            self.heartbeat.transport_ok = bool(state.transport_healthy)
            self.heartbeat.transport_error = state.transport_error
        else:
            self.telemetry.transport_ok = True
            self.telemetry.transport_error = None
            self.heartbeat.transport_ok = True
            self.heartbeat.transport_error = None
        self.telemetry.last_updated = utc_now()

    def _record(self, note: str, source: str, now) -> None:
        self.telemetry_log.append(
            TelemetryLogEntry(
                timestamp=now,
                source=source,
                note=note,
                telemetry=self.telemetry.model_copy(deep=True),
            )
        )

    def _adapters(self) -> list["DesktopAdapter"]:
        body_state = EdgeAdapterState.SIMULATED
        if self.body_driver.capabilities.driver_mode == BodyDriverMode.SERIAL:
            body_state = EdgeAdapterState.ACTIVE if self.body_driver.capabilities.transport_healthy else EdgeAdapterState.DEGRADED
        return [
            DesktopAdapter("desktop_speaker", EdgeAdapterKind.SPEAKER_TRIGGER, EdgeAdapterDirection.ACTUATOR, EdgeAdapterState.ACTIVE, "Local speaker output."),
            DesktopAdapter("desktop_caption", EdgeAdapterKind.DISPLAY, EdgeAdapterDirection.ACTUATOR, EdgeAdapterState.ACTIVE, "Desktop captions and console text."),
            DesktopAdapter("desktop_indicator", EdgeAdapterKind.LED, EdgeAdapterDirection.ACTUATOR, EdgeAdapterState.SIMULATED, "Semantic desktop status indicator."),
            DesktopAdapter("desktop_body", EdgeAdapterKind.HEAD_POSE, EdgeAdapterDirection.ACTUATOR, body_state, "Semantic body adapter surface."),
            DesktopAdapter("desktop_transcript", EdgeAdapterKind.TRANSCRIPT_RELAY, EdgeAdapterDirection.INPUT, EdgeAdapterState.ACTIVE, "Typed and browser transcript input."),
            DesktopAdapter("desktop_presence", EdgeAdapterKind.PRESENCE, EdgeAdapterDirection.INPUT, EdgeAdapterState.SIMULATED, "Camera or fixture-backed presence input."),
            DesktopAdapter("desktop_network", EdgeAdapterKind.NETWORK, EdgeAdapterDirection.MONITOR, EdgeAdapterState.ACTIVE, "Local runtime network monitor."),
            DesktopAdapter("desktop_battery", EdgeAdapterKind.BATTERY, EdgeAdapterDirection.MONITOR, EdgeAdapterState.SIMULATED, "Battery is simulated in desktop mode."),
            DesktopAdapter("desktop_heartbeat", EdgeAdapterKind.HEARTBEAT, EdgeAdapterDirection.MONITOR, EdgeAdapterState.ACTIVE, "Desktop heartbeat watchdog."),
        ]

    def _adapter_health(self, now=None) -> list[EdgeAdapterHealth]:
        current = now or utc_now()
        return [adapter.health(current) for adapter in self._adapters()]

    def _serial_body_driver(self) -> SerialBodyDriver | None:
        return self.body_driver if isinstance(self.body_driver, SerialBodyDriver) else None

    def _available_body_ports(self) -> list[dict[str, object]]:
        return [item.to_dict() for item in list_serial_ports()]

    def _body_action_result(
        self,
        *,
        status: str,
        detail: object | None = None,
        payload: dict[str, object] | None = None,
        report_path: object | None = None,
        motion_report_path: object | None = None,
        refresh_body: bool = True,
    ) -> dict[str, object]:
        self._sync_body_into_telemetry(refresh_body=refresh_body)
        body_state = self.telemetry.body_state.model_dump(mode="json") if self.telemetry.body_state is not None else None
        transport_summary = (
            self._serial_body_driver().transport_summary()
            if self._serial_body_driver() is not None
            else {}
        )
        return {
            "ok": status not in {"error", "unsupported"},
            "status": status,
            "detail": detail,
            "body_state": body_state,
            "transport_summary": transport_summary,
            "report_path": str(report_path) if report_path else None,
            "motion_report_path": str(motion_report_path) if motion_report_path else None,
            "payload": payload or {},
        }


@dataclass
class DesktopAdapter:
    adapter_id: str
    kind: EdgeAdapterKind
    direction: EdgeAdapterDirection
    state: EdgeAdapterState
    note: str

    def capability(self) -> EdgeAdapterCapability:
        return EdgeAdapterCapability(
            adapter_id=self.adapter_id,
            kind=self.kind,
            direction=self.direction,
            enabled=self.state != EdgeAdapterState.DISABLED,
            simulated=self.state == EdgeAdapterState.SIMULATED,
            supported_commands=[],
            emitted_events=[],
            note=self.note,
        )

    def health(self, now) -> EdgeAdapterHealth:
        return EdgeAdapterHealth(
            adapter_id=self.adapter_id,
            kind=self.kind,
            direction=self.direction,
            state=self.state,
            note=self.note,
            last_updated=now,
        )


class DesktopRuntimeGateway:
    def __init__(self, *, settings: Settings) -> None:
        self.settings = settings
        self.runtime = DesktopEmbodimentRuntime(settings=settings)
        self.command_history: list[CommandHistoryEntry] = []
        self.command_ack_cache: dict[str, CommandAck] = {}
        self.command_attempt_counts: dict[str, int] = {}

    def reset(self) -> None:
        self.runtime.reset()
        self.command_history = []
        self.command_ack_cache = {}
        self.command_attempt_counts = {}

    def simulate_event(self, request: SimulatedSensorEventRequest) -> SimulatedSensorEventResult:
        return self.runtime.simulate_event(request)

    def apply_command(self, command: RobotCommand) -> CommandAck:
        self.command_attempt_counts[command.command_id] = self.command_attempt_counts.get(command.command_id, 0) + 1
        if cached := self.command_ack_cache.get(command.command_id):
            log_event(
                logger,
                logging.INFO,
                "desktop_command_duplicate",
                command_id=command.command_id,
                body_batch_id=command.command_id,
                attempt_count=self.command_attempt_counts[command.command_id],
            )
            return cached.model_copy(update={"status": CommandAckStatus.DUPLICATE, "attempt_count": self.command_attempt_counts[command.command_id]}, deep=True)

        accepted, reason, payload = self.runtime.validate_command(command)
        if not accepted:
            ack = CommandAck(
                command_id=command.command_id,
                accepted=False,
                status=CommandAckStatus.REJECTED,
                reason=reason,
                attempt_count=self.command_attempt_counts[command.command_id],
                applied_state=self.runtime.get_telemetry().model_dump(mode="json"),
            )
        else:
            try:
                applied_state = self.runtime.execute_command(command, payload)
            except BodyCommandApplyError as exc:
                ack = CommandAck(
                    command_id=command.command_id,
                    accepted=False,
                    status=CommandAckStatus.TRANSPORT_ERROR,
                    reason=f"{exc.classification}:{exc.detail}",
                    attempt_count=self.command_attempt_counts[command.command_id],
                    applied_state=self.runtime.get_telemetry().model_dump(mode="json"),
                )
            else:
                ack = CommandAck(
                    command_id=command.command_id,
                    accepted=True,
                    status=CommandAckStatus.APPLIED,
                    reason=reason,
                    attempt_count=self.command_attempt_counts[command.command_id],
                    applied_state=applied_state,
                )
        self.command_ack_cache[command.command_id] = ack.model_copy(deep=True)
        self.command_history.append(CommandHistoryEntry(command=command, ack=ack))
        log_event(
            logger,
            logging.INFO if ack.accepted else logging.WARNING,
            "desktop_command_ack",
            command_id=command.command_id,
            body_batch_id=command.command_id,
            command_type=command.command_type.value,
            accepted=ack.accepted,
            ack_status=ack.status.value,
            reason=ack.reason,
        )
        return ack

    def get_telemetry(self) -> TelemetrySnapshot:
        return self.runtime.get_telemetry()

    def get_telemetry_log(self) -> TelemetryLogResponse:
        return self.runtime.get_telemetry_log()

    def get_heartbeat(self) -> HeartbeatStatus:
        return self.runtime.get_heartbeat()

    def get_command_history(self) -> CommandHistoryResponse:
        return CommandHistoryResponse(items=[entry.model_copy(deep=True) for entry in self.command_history])

    def get_capabilities(self) -> CapabilityProfile:
        return self.runtime.capabilities

    def force_safe_idle(self, reason: str) -> HeartbeatStatus:
        return self.runtime.force_safe_idle(reason)

    def get_body_status(self) -> dict[str, object]:
        return self.runtime.get_body_status()

    def apply_character_projection(
        self,
        *,
        intent: CharacterSemanticIntent,
        profile: CharacterProjectionProfile | None = None,
    ):
        return self.runtime.apply_character_projection(intent=intent, profile=profile)

    def connect_body(
        self,
        *,
        port: str | None = None,
        baud: int | None = None,
        timeout_seconds: float | None = None,
    ) -> dict[str, object]:
        return self.runtime.connect_body(port=port, baud=baud, timeout_seconds=timeout_seconds)

    def disconnect_body(self) -> dict[str, object]:
        return self.runtime.disconnect_body()

    def scan_body(self, *, ids: list[int] | None = None) -> dict[str, object]:
        return self.runtime.scan_body(ids=ids)

    def ping_body(self, *, ids: list[int] | None = None) -> dict[str, object]:
        return self.runtime.ping_body(ids=ids)

    def read_body_health(self, *, ids: list[int] | None = None) -> dict[str, object]:
        return self.runtime.read_body_health(ids=ids)

    def arm_body_motion(self, *, ttl_seconds: float = 60.0, author: str | None = None) -> dict[str, object]:
        return self.runtime.arm_body_motion(ttl_seconds=ttl_seconds, author=author)

    def disarm_body_motion(self) -> dict[str, object]:
        return self.runtime.disarm_body_motion()

    def write_body_neutral(self, *, author: str | None = None) -> dict[str, object]:
        return self.runtime.write_body_neutral(author=author)

    def run_body_power_preflight(self) -> dict[str, object]:
        return self.runtime.run_body_power_preflight()

    def get_body_servo_lab_catalog(self) -> dict[str, object]:
        return self.runtime.get_body_servo_lab_catalog()

    def read_body_servo_lab(
        self,
        *,
        joint_name: str | None = None,
        include_health: bool = True,
    ) -> dict[str, object]:
        return self.runtime.read_body_servo_lab(joint_name=joint_name, include_health=include_health)

    def move_body_servo_lab(
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
        return self.runtime.move_body_servo_lab(
            joint_name=joint_name,
            reference_mode=reference_mode,
            target_raw=target_raw,
            delta_counts=delta_counts,
            lab_min=lab_min,
            lab_max=lab_max,
            duration_ms=duration_ms,
            speed_override=speed_override,
            acceleration_override=acceleration_override,
            note=note,
        )

    def sweep_body_servo_lab(
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
        return self.runtime.sweep_body_servo_lab(
            joint_name=joint_name,
            lab_min=lab_min,
            lab_max=lab_max,
            cycles=cycles,
            duration_ms=duration_ms,
            dwell_ms=dwell_ms,
            speed_override=speed_override,
            acceleration_override=acceleration_override,
            return_to_neutral=return_to_neutral,
            note=note,
        )

    def save_body_servo_lab_calibration(
        self,
        *,
        joint_name: str,
        save_current_as_neutral: bool = False,
        raw_min: int | None = None,
        raw_max: int | None = None,
        confirm_mirrored: bool | None = None,
        note: str | None = None,
    ) -> dict[str, object]:
        return self.runtime.save_body_servo_lab_calibration(
            joint_name=joint_name,
            save_current_as_neutral=save_current_as_neutral,
            raw_min=raw_min,
            raw_max=raw_max,
            confirm_mirrored=confirm_mirrored,
            note=note,
        )

    def get_body_semantic_library(self, *, smoke_safe_only: bool = False) -> dict[str, object]:
        return self.runtime.get_body_semantic_library(smoke_safe_only=smoke_safe_only)

    def get_body_expression_catalog(self) -> dict[str, object]:
        return self.runtime.get_body_expression_catalog()

    def run_body_semantic_smoke(
        self,
        *,
        action: str = "look_left",
        intensity: float = 1.0,
        repeat_count: int = 1,
        note: str | None = None,
        allow_bench_actions: bool = False,
    ) -> dict[str, object]:
        return self.runtime.run_body_semantic_smoke(
            action=action,
            intensity=intensity,
            repeat_count=repeat_count,
            note=note,
            allow_bench_actions=allow_bench_actions,
        )

    def run_body_primitive_sequence(
        self,
        *,
        steps: list[dict[str, object]],
        note: str | None = None,
        sequence_name: str = "body_primitive_sequence",
    ) -> dict[str, object]:
        return self.runtime.run_body_primitive_sequence(
            steps=steps,
            note=note,
            sequence_name=sequence_name,
        )

    def run_body_staged_sequence(
        self,
        *,
        stages: list[dict[str, object]],
        note: str | None = None,
        sequence_name: str = "body_staged_sequence",
    ) -> dict[str, object]:
        return self.runtime.run_body_staged_sequence(
            stages=stages,
            note=note,
            sequence_name=sequence_name,
        )

    def run_body_expressive_motif(
        self,
        *,
        motif: dict[str, object] | None = None,
        steps: list[dict[str, object]] | None = None,
        note: str | None = None,
        sequence_name: str = "body_expressive_motif",
    ) -> dict[str, object]:
        return self.runtime.run_body_expressive_motif(
            motif=motif,
            steps=steps,
            note=note,
            sequence_name=sequence_name,
        )

    def run_body_range_demo(
        self,
        *,
        sequence_name: str | None = None,
        preset_name: str | None = None,
        note: str | None = None,
    ) -> dict[str, object]:
        return self.runtime.run_body_range_demo(
            sequence_name=sequence_name,
            preset_name=preset_name,
            note=note,
        )

    def record_body_teacher_review(
        self,
        *,
        action: str,
        review: str,
        note: str | None = None,
        proposed_tuning_delta: dict[str, object] | None = None,
        apply_tuning: bool = False,
    ) -> dict[str, object]:
        return self.runtime.record_body_teacher_review(
            action=action,
            review=review,
            note=note,
            proposed_tuning_delta=proposed_tuning_delta,
            apply_tuning=apply_tuning,
        )

    def get_body_command_audits(self) -> list[dict[str, object]]:
        driver = self.runtime.body_driver
        if isinstance(driver, SerialBodyDriver):
            return [item.model_dump(mode="json") for item in driver.body_command_audits()]
        return []

    def get_body_motion_report_index(self) -> list[dict[str, object]]:
        driver = self.runtime.body_driver
        if isinstance(driver, SerialBodyDriver):
            return driver.motion_report_index()
        return []

    def get_body_semantic_tuning(self) -> dict[str, object]:
        driver = self.runtime.body_driver
        if isinstance(driver, SerialBodyDriver):
            return driver.semantic_tuning_snapshot()
        return {}

    def get_body_teacher_reviews(self) -> list[dict[str, object]]:
        driver = self.runtime.body_driver
        if isinstance(driver, SerialBodyDriver):
            return driver.teacher_reviews()
        return []

    def get_body_serial_failure_summary(self) -> dict[str, object]:
        driver = self.runtime.body_driver
        if isinstance(driver, SerialBodyDriver):
            return driver.serial_failure_summary()
        return {}

    def get_body_request_response_history(self) -> list[dict[str, object]]:
        driver = self.runtime.body_driver
        if isinstance(driver, SerialBodyDriver):
            return driver.request_response_history()
        return []

    def transport_mode(self) -> EdgeTransportMode:
        return EdgeTransportMode.IN_PROCESS

    def transport_state(self) -> TransportState:
        return TransportState.HEALTHY if self.runtime.heartbeat.transport_ok else TransportState.DEGRADED

    def last_transport_error(self) -> str | None:
        return self.runtime.heartbeat.transport_error or self.runtime.telemetry.transport_error


def build_default_embodiment_gateway(settings: Settings):
    if settings.uses_desktop_runtime:
        return DesktopRuntimeGateway(settings=settings)
    from embodied_stack.demo.coordinator import HttpEdgeGateway

    return HttpEdgeGateway(
        settings.edge_base_url,
        timeout_seconds=settings.edge_gateway_timeout_seconds,
        max_retries=settings.edge_gateway_max_retries,
        retry_backoff_seconds=settings.edge_gateway_retry_backoff_seconds,
    )


def build_inprocess_embodiment_gateway(settings: Settings):
    if settings.uses_desktop_runtime:
        return DesktopRuntimeGateway(settings=settings)
    from embodied_stack.demo.coordinator import InProcessEdgeGateway
    from embodied_stack.edge.controller import SimulatedRobotController

    return InProcessEdgeGateway(SimulatedRobotController(settings=settings))


__all__ = [
    "DesktopEmbodimentRuntime",
    "DesktopRuntimeGateway",
    "build_default_embodiment_gateway",
    "build_inprocess_embodiment_gateway",
]
