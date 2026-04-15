from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from embodied_stack.shared.models import (
    CommandType,
    EdgeAdapterCapability,
    EdgeAdapterDirection,
    EdgeAdapterHealth,
    EdgeAdapterKind,
    EdgeAdapterState,
    HeartbeatStatus,
    RobotEvent,
    SimulatedSensorEventRequest,
    TelemetrySnapshot,
    utc_now,
)


@dataclass
class InputEventResult:
    event: RobotEvent
    note: str
    force_safe_idle_reason: str | None = None
    restore_connection: bool = False


class EdgeAdapterBase:
    def __init__(
        self,
        *,
        adapter_id: str,
        kind: EdgeAdapterKind,
        direction: EdgeAdapterDirection,
        enabled: bool = True,
        simulated: bool = False,
        state: EdgeAdapterState | None = None,
        note: str | None = None,
        supported_commands: tuple[CommandType, ...] = (),
        emitted_events: tuple[str, ...] = (),
    ) -> None:
        self.adapter_id = adapter_id
        self.kind = kind
        self.direction = direction
        self.enabled = enabled
        self.simulated = simulated
        self.supported_commands = supported_commands
        self.emitted_events = emitted_events
        if state is None:
            if not enabled:
                state = EdgeAdapterState.DISABLED
            elif simulated:
                state = EdgeAdapterState.SIMULATED
            else:
                state = EdgeAdapterState.ACTIVE
        self._state = state
        self._note = note
        self._last_updated = utc_now()

    def reset(self, now: datetime | None = None) -> None:
        self._last_updated = now or utc_now()

    def capability(self) -> EdgeAdapterCapability:
        return EdgeAdapterCapability(
            adapter_id=self.adapter_id,
            kind=self.kind,
            direction=self.direction,
            enabled=self.enabled,
            simulated=self.simulated,
            supported_commands=list(self.supported_commands),
            emitted_events=list(self.emitted_events),
            note=self._note,
        )

    def health(self, now: datetime | None = None) -> EdgeAdapterHealth:
        current = now or self._last_updated
        return EdgeAdapterHealth(
            adapter_id=self.adapter_id,
            kind=self.kind,
            direction=self.direction,
            state=self._state,
            note=self._note,
            last_updated=current,
        )

    def set_state(
        self,
        state: EdgeAdapterState,
        *,
        note: str | None = None,
        now: datetime | None = None,
    ) -> None:
        self._state = state
        if note is not None:
            self._note = note
        self._last_updated = now or utc_now()


class ActuatorAdapterBase(EdgeAdapterBase):
    def apply(self, payload: dict, telemetry: TelemetrySnapshot, now: datetime) -> str:
        raise NotImplementedError

    def on_safe_idle(self, reason: str, telemetry: TelemetrySnapshot, now: datetime) -> None:
        del reason, telemetry, now


class InputAdapterBase(EdgeAdapterBase):
    def handle_event(
        self,
        request: SimulatedSensorEventRequest,
        telemetry: TelemetrySnapshot,
        heartbeat: HeartbeatStatus,
        now: datetime,
    ) -> InputEventResult:
        raise NotImplementedError


class FakeSpeakerActuator(ActuatorAdapterBase):
    def __init__(self, *, adapter_id: str = "speaker") -> None:
        super().__init__(
            adapter_id=adapter_id,
            kind=EdgeAdapterKind.SPEAKER_TRIGGER,
            direction=EdgeAdapterDirection.ACTUATOR,
            simulated=True,
            supported_commands=(CommandType.SPEAK,),
            note="Simulated speaker trigger for pre-hardware demos.",
        )

    def apply(self, payload: dict, telemetry: TelemetrySnapshot, now: datetime) -> str:
        text = str(payload.get("text", ""))
        telemetry.speaking = True
        telemetry.last_spoken_text = text
        telemetry.speaking = False
        telemetry.last_sensor_event_type = "speech_output"
        telemetry.last_updated = now
        return f"speak:{text}"

    def on_safe_idle(self, reason: str, telemetry: TelemetrySnapshot, now: datetime) -> None:
        del reason
        telemetry.speaking = False
        telemetry.last_updated = now


class FakeDisplayActuator(ActuatorAdapterBase):
    def __init__(self, *, adapter_id: str = "display") -> None:
        super().__init__(
            adapter_id=adapter_id,
            kind=EdgeAdapterKind.DISPLAY,
            direction=EdgeAdapterDirection.ACTUATOR,
            simulated=True,
            supported_commands=(CommandType.DISPLAY_TEXT,),
            note="Simulated display output for the fake robot and tethered demos.",
        )

    def apply(self, payload: dict, telemetry: TelemetrySnapshot, now: datetime) -> str:
        telemetry.display_text = str(payload.get("text", ""))
        telemetry.last_updated = now
        return "display_text"

    def on_safe_idle(self, reason: str, telemetry: TelemetrySnapshot, now: datetime) -> None:
        telemetry.display_text = f"Safe idle: {reason}"
        telemetry.last_updated = now


class FakeLedActuator(ActuatorAdapterBase):
    def __init__(self, *, adapter_id: str = "led") -> None:
        super().__init__(
            adapter_id=adapter_id,
            kind=EdgeAdapterKind.LED,
            direction=EdgeAdapterDirection.ACTUATOR,
            simulated=True,
            supported_commands=(CommandType.SET_LED,),
            note="Simulated LED output.",
        )

    def apply(self, payload: dict, telemetry: TelemetrySnapshot, now: datetime) -> str:
        telemetry.led_color = str(payload.get("color", "off"))
        telemetry.last_updated = now
        return f"set_led:{telemetry.led_color}"

    def on_safe_idle(self, reason: str, telemetry: TelemetrySnapshot, now: datetime) -> None:
        del reason
        telemetry.led_color = "amber"
        telemetry.last_updated = now


class FakeHeadPoseActuator(ActuatorAdapterBase):
    def __init__(self, *, adapter_id: str = "head_pose") -> None:
        super().__init__(
            adapter_id=adapter_id,
            kind=EdgeAdapterKind.HEAD_POSE,
            direction=EdgeAdapterDirection.ACTUATOR,
            simulated=True,
            supported_commands=(CommandType.SET_HEAD_POSE,),
            note="Simulated head pose actuator.",
        )

    def apply(self, payload: dict, telemetry: TelemetrySnapshot, now: datetime) -> str:
        telemetry.head_yaw_deg = float(payload.get("head_yaw_deg", 0.0))
        telemetry.head_pitch_deg = float(payload.get("head_pitch_deg", 0.0))
        telemetry.last_updated = now
        return "set_head_pose"

    def on_safe_idle(self, reason: str, telemetry: TelemetrySnapshot, now: datetime) -> None:
        del reason
        telemetry.head_yaw_deg = 0.0
        telemetry.head_pitch_deg = 0.0
        telemetry.last_updated = now


class NotWiredActuator(ActuatorAdapterBase):
    def __init__(
        self,
        *,
        adapter_id: str,
        kind: EdgeAdapterKind,
        supported_command: CommandType,
        enabled: bool = True,
        note: str = "Adapter landing zone exists but the hardware path is not wired yet.",
    ) -> None:
        super().__init__(
            adapter_id=adapter_id,
            kind=kind,
            direction=EdgeAdapterDirection.ACTUATOR,
            enabled=enabled,
            simulated=False,
            state=EdgeAdapterState.UNAVAILABLE if enabled else EdgeAdapterState.DISABLED,
            supported_commands=(supported_command,),
            note=note,
        )

    def apply(self, payload: dict, telemetry: TelemetrySnapshot, now: datetime) -> str:
        del payload, telemetry, now
        return f"{self.kind.value}_unavailable"


class TranscriptRelayInput(InputAdapterBase):
    def __init__(
        self,
        *,
        adapter_id: str = "transcript_relay",
        simulated: bool = True,
        enabled: bool = True,
    ) -> None:
        super().__init__(
            adapter_id=adapter_id,
            kind=EdgeAdapterKind.TRANSCRIPT_RELAY,
            direction=EdgeAdapterDirection.INPUT,
            enabled=enabled,
            simulated=simulated,
            state=EdgeAdapterState.SIMULATED if enabled and simulated else EdgeAdapterState.DISABLED,
            emitted_events=("speech_transcript",),
            note="Speech transcript relay for typed, browser, or fixture-driven demo turns.",
        )

    def handle_event(
        self,
        request: SimulatedSensorEventRequest,
        telemetry: TelemetrySnapshot,
        heartbeat: HeartbeatStatus,
        now: datetime,
    ) -> InputEventResult:
        del heartbeat
        telemetry.last_sensor_event_type = "speech_transcript"
        telemetry.last_updated = now
        return InputEventResult(
            event=RobotEvent(
                event_type="speech_transcript",
                session_id=request.session_id,
                source=request.source,
                payload={"text": str(request.payload.get("text", ""))},
                timestamp=now,
            ),
            note="speech_input",
        )


class SimpleSensorInput(InputAdapterBase):
    def __init__(
        self,
        *,
        adapter_id: str,
        kind: EdgeAdapterKind,
        event_type: str,
        simulated: bool = True,
        enabled: bool = True,
        note: str,
    ) -> None:
        super().__init__(
            adapter_id=adapter_id,
            kind=kind,
            direction=EdgeAdapterDirection.INPUT,
            enabled=enabled,
            simulated=simulated,
            state=EdgeAdapterState.SIMULATED if enabled and simulated else EdgeAdapterState.DISABLED,
            emitted_events=(event_type,),
            note=note,
        )
        self.event_type = event_type

    def handle_event(
        self,
        request: SimulatedSensorEventRequest,
        telemetry: TelemetrySnapshot,
        heartbeat: HeartbeatStatus,
        now: datetime,
    ) -> InputEventResult:
        del heartbeat
        telemetry.last_sensor_event_type = self.event_type
        telemetry.last_updated = now
        return InputEventResult(
            event=RobotEvent(
                event_type=self.event_type,
                session_id=request.session_id,
                source=request.source,
                payload=dict(request.payload),
                timestamp=now,
            ),
            note=self.event_type,
        )


class NotWiredInput(InputAdapterBase):
    def __init__(
        self,
        *,
        adapter_id: str,
        kind: EdgeAdapterKind,
        event_type: str,
        direction: EdgeAdapterDirection = EdgeAdapterDirection.INPUT,
        enabled: bool = True,
        note: str = "Input adapter landing zone exists but hardware wiring is still pending.",
    ) -> None:
        super().__init__(
            adapter_id=adapter_id,
            kind=kind,
            direction=direction,
            enabled=enabled,
            simulated=False,
            state=EdgeAdapterState.UNAVAILABLE if enabled else EdgeAdapterState.DISABLED,
            emitted_events=(event_type,),
            note=note,
        )
        self.event_type = event_type

    def handle_event(
        self,
        request: SimulatedSensorEventRequest,
        telemetry: TelemetrySnapshot,
        heartbeat: HeartbeatStatus,
        now: datetime,
    ) -> InputEventResult:
        del request, telemetry, heartbeat, now
        raise RuntimeError(f"{self.kind.value}_adapter_unavailable")


class BatteryMonitorInput(InputAdapterBase):
    def __init__(
        self,
        *,
        adapter_id: str = "battery_monitor",
        simulated: bool = True,
        enabled: bool = True,
        state: EdgeAdapterState | None = None,
        note: str = "Battery monitoring adapter.",
    ) -> None:
        super().__init__(
            adapter_id=adapter_id,
            kind=EdgeAdapterKind.BATTERY,
            direction=EdgeAdapterDirection.MONITOR,
            enabled=enabled,
            simulated=simulated,
            state=state,
            emitted_events=("low_battery",),
            note=note,
        )

    def handle_event(
        self,
        request: SimulatedSensorEventRequest,
        telemetry: TelemetrySnapshot,
        heartbeat: HeartbeatStatus,
        now: datetime,
    ) -> InputEventResult:
        del heartbeat
        telemetry.last_sensor_event_type = "low_battery"
        telemetry.battery_pct = float(request.payload.get("battery_pct", min(telemetry.battery_pct, 12.0)))
        telemetry.last_updated = now
        return InputEventResult(
            event=RobotEvent(
                event_type="low_battery",
                session_id=request.session_id,
                source=request.source,
                payload={"battery_pct": telemetry.battery_pct},
                timestamp=now,
            ),
            note="low_battery",
            force_safe_idle_reason="low_battery",
        )


class NetworkMonitorInput(InputAdapterBase):
    def __init__(
        self,
        *,
        adapter_id: str = "network_monitor",
        simulated: bool = True,
        enabled: bool = True,
        state: EdgeAdapterState | None = None,
        note: str = "Network watchdog and link-state adapter.",
    ) -> None:
        super().__init__(
            adapter_id=adapter_id,
            kind=EdgeAdapterKind.NETWORK,
            direction=EdgeAdapterDirection.MONITOR,
            enabled=enabled,
            simulated=simulated,
            state=state,
            emitted_events=("network_state",),
            note=note,
        )

    def handle_event(
        self,
        request: SimulatedSensorEventRequest,
        telemetry: TelemetrySnapshot,
        heartbeat: HeartbeatStatus,
        now: datetime,
    ) -> InputEventResult:
        del heartbeat
        network_ok = bool(request.payload.get("network_ok", True))
        latency_ms = float(request.payload.get("latency_ms", 0.0))
        telemetry.last_sensor_event_type = "network_state"
        telemetry.network_ok = network_ok
        telemetry.network_latency_ms = latency_ms
        telemetry.last_updated = now
        return InputEventResult(
            event=RobotEvent(
                event_type="heartbeat",
                session_id=request.session_id,
                source=request.source,
                payload={
                    "network_ok": network_ok,
                    "mode": telemetry.mode.value,
                    "latency_ms": latency_ms,
                    "safe_idle_reason": telemetry.safe_idle_reason,
                },
                timestamp=now,
            ),
            note="network_state",
            force_safe_idle_reason="network_degraded" if not network_ok else None,
            restore_connection=network_ok,
        )


class HeartbeatMonitorInput(InputAdapterBase):
    def __init__(
        self,
        *,
        adapter_id: str = "heartbeat_monitor",
        simulated: bool = True,
        enabled: bool = True,
        state: EdgeAdapterState | None = None,
        note: str = "Heartbeat watchdog adapter.",
    ) -> None:
        super().__init__(
            adapter_id=adapter_id,
            kind=EdgeAdapterKind.HEARTBEAT,
            direction=EdgeAdapterDirection.MONITOR,
            enabled=enabled,
            simulated=simulated,
            state=state,
            emitted_events=("heartbeat",),
            note=note,
        )

    def handle_event(
        self,
        request: SimulatedSensorEventRequest,
        telemetry: TelemetrySnapshot,
        heartbeat: HeartbeatStatus,
        now: datetime,
    ) -> InputEventResult:
        del heartbeat
        network_ok = bool(request.payload.get("network_ok", telemetry.network_ok))
        latency_ms = float(request.payload.get("latency_ms", telemetry.network_latency_ms or 0.0))
        safe_idle_reason = str(request.payload.get("safe_idle_reason", "network_degraded"))
        telemetry.last_sensor_event_type = "heartbeat"
        telemetry.network_ok = network_ok
        telemetry.network_latency_ms = latency_ms
        telemetry.last_updated = now
        return InputEventResult(
            event=RobotEvent(
                event_type="heartbeat",
                session_id=request.session_id,
                source=request.source,
                payload={
                    "network_ok": network_ok,
                    "mode": telemetry.mode.value,
                    "latency_ms": latency_ms,
                    "safe_idle_reason": telemetry.safe_idle_reason,
                },
                timestamp=now,
            ),
            note="heartbeat",
            force_safe_idle_reason=safe_idle_reason if not network_ok else None,
            restore_connection=network_ok,
        )
