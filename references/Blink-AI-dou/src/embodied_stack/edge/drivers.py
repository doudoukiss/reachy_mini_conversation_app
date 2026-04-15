from __future__ import annotations

from datetime import datetime, timedelta
from typing import Protocol

from embodied_stack.config import Settings
from embodied_stack.edge.adapters import (
    ActuatorAdapterBase,
    BatteryMonitorInput,
    FakeDisplayActuator,
    FakeHeadPoseActuator,
    FakeLedActuator,
    FakeSpeakerActuator,
    HeartbeatMonitorInput,
    InputAdapterBase,
    NetworkMonitorInput,
    NotWiredActuator,
    NotWiredInput,
    SimpleSensorInput,
    TranscriptRelayInput,
)
from embodied_stack.shared.models import (
    CapabilityProfile,
    CommandType,
    EdgeAdapterKind,
    EdgeAdapterState,
    HeartbeatStatus,
    RobotCommand,
    RobotEvent,
    RobotMode,
    SimulatedSensorEventRequest,
    SimulatedSensorEventResult,
    TelemetryLogEntry,
    TelemetrySnapshot,
    utc_now,
)


COMMAND_TO_ADAPTER_KIND: dict[CommandType, EdgeAdapterKind] = {
    CommandType.SPEAK: EdgeAdapterKind.SPEAKER_TRIGGER,
    CommandType.DISPLAY_TEXT: EdgeAdapterKind.DISPLAY,
    CommandType.SET_LED: EdgeAdapterKind.LED,
    CommandType.SET_HEAD_POSE: EdgeAdapterKind.HEAD_POSE,
}

EVENT_TO_ADAPTER_KIND: dict[str, EdgeAdapterKind] = {
    "speech_transcript": EdgeAdapterKind.TRANSCRIPT_RELAY,
    "touch": EdgeAdapterKind.TOUCH,
    "button": EdgeAdapterKind.BUTTON,
    "person_detected": EdgeAdapterKind.PRESENCE,
    "network_state": EdgeAdapterKind.NETWORK,
    "low_battery": EdgeAdapterKind.BATTERY,
    "heartbeat": EdgeAdapterKind.HEARTBEAT,
}

NETWORK_SAFE_IDLE_REASONS = {"network_degraded", "heartbeat_timeout", "edge_transport_degraded"}


class RobotDriver(Protocol):
    capabilities: CapabilityProfile

    def get_telemetry(self, now: datetime | None = None) -> TelemetrySnapshot:
        ...

    def get_telemetry_log(self) -> list[TelemetryLogEntry]:
        ...

    def get_heartbeat(self, now: datetime | None = None) -> HeartbeatStatus:
        ...

    def execute_command(self, command: RobotCommand, payload: dict, now: datetime | None = None) -> dict:
        ...

    def simulate_event(self, request: SimulatedSensorEventRequest, now: datetime | None = None) -> SimulatedSensorEventResult:
        ...

    def force_safe_idle(self, reason: str, now: datetime | None = None) -> HeartbeatStatus:
        ...

    def reset(self) -> None:
        ...


class AdapterDrivenRobotDriver:
    def __init__(
        self,
        *,
        mode: RobotMode,
        runtime_profile: str,
        heartbeat_timeout_seconds: float,
        actuator_adapters: list[ActuatorAdapterBase],
        input_adapters: list[InputAdapterBase],
        supports_simulated_events: bool,
        battery_drain_enabled: bool,
    ) -> None:
        self.mode = mode
        self.runtime_profile = runtime_profile
        self.heartbeat_timeout_seconds = heartbeat_timeout_seconds
        self.actuator_adapters = actuator_adapters
        self.input_adapters = input_adapters
        self.supports_simulated_events = supports_simulated_events
        self.battery_drain_enabled = battery_drain_enabled
        self.capabilities = self._build_capabilities()
        self.reset()

    def reset(self) -> None:
        now = utc_now()
        for adapter in self._all_adapters():
            adapter.reset(now)
        self.telemetry = TelemetrySnapshot(
            mode=self.mode,
            runtime_profile=self.runtime_profile,
            last_updated=now,
        )
        self.telemetry_log: list[TelemetryLogEntry] = []
        self.heartbeat = HeartbeatStatus(
            connected=True,
            network_ok=True,
            safe_idle_active=False,
            last_contact_at=now,
            timeout_seconds=self.heartbeat_timeout_seconds,
        )
        self._refresh_adapter_health(now)
        self._record_telemetry("driver_reset", "edge_reset", now)

    def get_telemetry(self, now: datetime | None = None) -> TelemetrySnapshot:
        self._evaluate_heartbeat(now)
        self._refresh_adapter_health(now or utc_now())
        return self.telemetry.model_copy(deep=True)

    def get_telemetry_log(self) -> list[TelemetryLogEntry]:
        return [entry.model_copy(deep=True) for entry in self.telemetry_log]

    def get_heartbeat(self, now: datetime | None = None) -> HeartbeatStatus:
        self._evaluate_heartbeat(now)
        return self.heartbeat.model_copy(deep=True)

    def execute_command(self, command: RobotCommand, payload: dict, now: datetime | None = None) -> dict:
        current = self._touch_contact(now)
        self._drain_battery(command.command_type)

        if command.command_type == CommandType.STOP:
            self.force_safe_idle(str(payload.get("reason", "stop_command")), current)
            self._record_telemetry("stop", "command", current)
            return self.telemetry.model_dump(mode="json")

        adapter_kind = COMMAND_TO_ADAPTER_KIND.get(command.command_type)
        if adapter_kind is None:
            self._record_telemetry(f"unsupported_command:{command.command_type.value}", "command", current)
            return self.telemetry.model_dump(mode="json")

        adapter = self._actuator_by_kind(adapter_kind)
        note = adapter.apply(payload, self.telemetry, current) if adapter is not None else "command_ignored"
        self._refresh_adapter_health(current)
        self._record_telemetry(note, "command", current)

        if self.capabilities.supports_battery_monitor and self.telemetry.battery_pct <= 15.0:
            self.force_safe_idle("low_battery", current)

        return self.telemetry.model_dump(mode="json")

    def simulate_event(self, request: SimulatedSensorEventRequest, now: datetime | None = None) -> SimulatedSensorEventResult:
        current = self._touch_contact(now)
        event_type = request.event_type
        self._drain_battery(None if event_type == "heartbeat" else CommandType.SET_LED)

        adapter = self._input_by_kind(EVENT_TO_ADAPTER_KIND.get(event_type))
        if adapter is None:
            event = self._generic_event(request, current)
            self._record_telemetry(event_type, request.source, current)
            return SimulatedSensorEventResult(
                event=event,
                telemetry=self.get_telemetry(current),
                heartbeat=self.get_heartbeat(current),
            )

        result = adapter.handle_event(request, self.telemetry, self.heartbeat, current)
        if result.force_safe_idle_reason:
            self.force_safe_idle(result.force_safe_idle_reason, current)
        elif result.restore_connection:
            self._restore_connection(current)

        if result.event.event_type == "heartbeat":
            result.event.payload["network_ok"] = self.telemetry.network_ok
            result.event.payload["mode"] = self.telemetry.mode.value
            result.event.payload["safe_idle_reason"] = self.telemetry.safe_idle_reason

        self._refresh_adapter_health(current)
        self._record_telemetry(result.note, request.source, current)
        return SimulatedSensorEventResult(
            event=result.event,
            telemetry=self.get_telemetry(current),
            heartbeat=self.get_heartbeat(current),
        )

    def force_safe_idle(self, reason: str, now: datetime | None = None) -> HeartbeatStatus:
        current = now or utc_now()
        self.heartbeat.safe_idle_active = True
        self.heartbeat.safe_idle_reason = reason
        if reason in NETWORK_SAFE_IDLE_REASONS:
            self.heartbeat.connected = False
            self.heartbeat.network_ok = False
        self.telemetry.mode = RobotMode.DEGRADED_SAFE_IDLE
        self.telemetry.safe_idle_reason = reason
        self.telemetry.network_ok = self.heartbeat.network_ok
        self.telemetry.last_updated = current
        for adapter in self.actuator_adapters:
            if self._adapter_is_callable(adapter):
                adapter.on_safe_idle(reason, self.telemetry, current)
        self._refresh_adapter_health(current)
        return self.heartbeat.model_copy(deep=True)

    def _restore_connection(self, now: datetime) -> None:
        self.heartbeat.connected = True
        self.heartbeat.network_ok = True
        if self.heartbeat.safe_idle_reason in NETWORK_SAFE_IDLE_REASONS or not self.heartbeat.safe_idle_active:
            self.heartbeat.safe_idle_active = False
            self.heartbeat.safe_idle_reason = None
            self.telemetry.mode = self.mode
            self.telemetry.safe_idle_reason = None
        self.telemetry.network_ok = True
        self.telemetry.last_updated = now
        self._refresh_adapter_health(now)

    def _touch_contact(self, now: datetime | None = None) -> datetime:
        current = now or utc_now()
        self.heartbeat.last_contact_at = current
        self.telemetry.last_updated = current
        return current

    def _evaluate_heartbeat(self, now: datetime | None = None) -> None:
        current = now or utc_now()
        if current - self.heartbeat.last_contact_at > timedelta(seconds=self.heartbeat.timeout_seconds):
            self.force_safe_idle("heartbeat_timeout", current)

    def _record_telemetry(self, note: str, source: str, now: datetime) -> None:
        self.telemetry.last_updated = now
        self.telemetry_log.append(
            TelemetryLogEntry(
                timestamp=now,
                source=source,
                note=note,
                telemetry=self.telemetry.model_copy(deep=True),
            )
        )

    def _refresh_adapter_health(self, now: datetime) -> None:
        self.telemetry.adapter_health = [adapter.health(now) for adapter in self._all_adapters()]
        self.telemetry.runtime_profile = self.runtime_profile

    def _drain_battery(self, command_type: CommandType | None) -> None:
        if not self.battery_drain_enabled:
            return
        drain_map = {
            CommandType.SPEAK: 0.8,
            CommandType.DISPLAY_TEXT: 0.2,
            CommandType.SET_LED: 0.1,
            CommandType.SET_HEAD_POSE: 0.4,
            CommandType.STOP: 0.0,
            None: 0.2,
        }
        drain = drain_map.get(command_type, 0.2)
        self.telemetry.battery_pct = max(0.0, round(self.telemetry.battery_pct - drain, 2))

    def _generic_event(self, request: SimulatedSensorEventRequest, now: datetime) -> RobotEvent:
        self.telemetry.last_sensor_event_type = request.event_type
        self.telemetry.last_updated = now
        return RobotEvent(
            event_type=request.event_type,
            session_id=request.session_id,
            source=request.source,
            payload=dict(request.payload),
            timestamp=now,
        )

    def _build_capabilities(self) -> CapabilityProfile:
        adapters = [adapter.capability() for adapter in self._all_adapters()]
        enabled_kinds = {adapter.kind for adapter in adapters if adapter.enabled}
        return CapabilityProfile(
            mode=self.mode,
            runtime_profile=self.runtime_profile,
            supports_voice_output=EdgeAdapterKind.SPEAKER_TRIGGER in enabled_kinds,
            supports_led=EdgeAdapterKind.LED in enabled_kinds,
            supports_head_pose=EdgeAdapterKind.HEAD_POSE in enabled_kinds,
            supports_display=EdgeAdapterKind.DISPLAY in enabled_kinds,
            supports_base_motion=False,
            supports_touch_sensor=EdgeAdapterKind.TOUCH in enabled_kinds,
            supports_button_sensor=EdgeAdapterKind.BUTTON in enabled_kinds,
            supports_person_detection=EdgeAdapterKind.PRESENCE in enabled_kinds,
            supports_network_monitor=EdgeAdapterKind.NETWORK in enabled_kinds,
            supports_battery_monitor=EdgeAdapterKind.BATTERY in enabled_kinds,
            supports_heartbeat_monitor=EdgeAdapterKind.HEARTBEAT in enabled_kinds,
            supports_simulated_events=self.supports_simulated_events,
            adapters=adapters,
        )

    def _adapter_is_callable(self, adapter: ActuatorAdapterBase) -> bool:
        return adapter.enabled and adapter.health().state in {
            EdgeAdapterState.ACTIVE,
            EdgeAdapterState.SIMULATED,
            EdgeAdapterState.DEGRADED,
        }

    def _actuator_by_kind(self, kind: EdgeAdapterKind | None) -> ActuatorAdapterBase | None:
        if kind is None:
            return None
        return next((adapter for adapter in self.actuator_adapters if adapter.kind == kind), None)

    def _input_by_kind(self, kind: EdgeAdapterKind | None) -> InputAdapterBase | None:
        if kind is None:
            return None
        return next((adapter for adapter in self.input_adapters if adapter.kind == kind), None)

    def _all_adapters(self) -> list[ActuatorAdapterBase | InputAdapterBase]:
        return [*self.actuator_adapters, *self.input_adapters]


class FakeRobotDriver(AdapterDrivenRobotDriver):
    def __init__(self, heartbeat_timeout_seconds: float = 15.0) -> None:
        super().__init__(
            mode=RobotMode.SIMULATED,
            runtime_profile="fake_robot_full",
            heartbeat_timeout_seconds=heartbeat_timeout_seconds,
            actuator_adapters=[
                FakeSpeakerActuator(),
                FakeDisplayActuator(),
                FakeLedActuator(),
                FakeHeadPoseActuator(),
            ],
            input_adapters=[
                TranscriptRelayInput(),
                SimpleSensorInput(
                    adapter_id="touch_sensor",
                    kind=EdgeAdapterKind.TOUCH,
                    event_type="touch",
                    note="Simulated touch sensor input.",
                ),
                SimpleSensorInput(
                    adapter_id="button_input",
                    kind=EdgeAdapterKind.BUTTON,
                    event_type="button",
                    note="Simulated button input.",
                ),
                SimpleSensorInput(
                    adapter_id="presence_sensor",
                    kind=EdgeAdapterKind.PRESENCE,
                    event_type="person_detected",
                    note="Simulated presence detection input.",
                ),
                NetworkMonitorInput(),
                BatteryMonitorInput(),
                HeartbeatMonitorInput(),
            ],
            supports_simulated_events=True,
            battery_drain_enabled=True,
        )


class JetsonHardwareDriver(AdapterDrivenRobotDriver):
    def __init__(self, profile_name: str = "jetson_landing_zone", heartbeat_timeout_seconds: float = 15.0) -> None:
        mode, simulated_events, battery_drain_enabled, actuators, inputs = self._build_profile(profile_name)
        super().__init__(
            mode=mode,
            runtime_profile=profile_name,
            heartbeat_timeout_seconds=heartbeat_timeout_seconds,
            actuator_adapters=actuators,
            input_adapters=inputs,
            supports_simulated_events=simulated_events,
            battery_drain_enabled=battery_drain_enabled,
        )

    def _build_profile(
        self,
        profile_name: str,
    ) -> tuple[RobotMode, bool, bool, list[ActuatorAdapterBase], list[InputAdapterBase]]:
        if profile_name == "jetson_simulated_io":
            return (
                RobotMode.TETHERED_DEMO,
                True,
                True,
                [
                    FakeSpeakerActuator(adapter_id="jetson_speaker"),
                    FakeDisplayActuator(adapter_id="jetson_display"),
                    FakeLedActuator(adapter_id="jetson_led"),
                    FakeHeadPoseActuator(adapter_id="jetson_head_pose"),
                ],
                [
                    TranscriptRelayInput(adapter_id="jetson_transcript", simulated=True, enabled=True),
                    SimpleSensorInput(
                        adapter_id="jetson_touch",
                        kind=EdgeAdapterKind.TOUCH,
                        event_type="touch",
                        note="Simulated touch input under the Jetson hardware profile.",
                    ),
                    SimpleSensorInput(
                        adapter_id="jetson_button",
                        kind=EdgeAdapterKind.BUTTON,
                        event_type="button",
                        note="Simulated button input under the Jetson hardware profile.",
                    ),
                    SimpleSensorInput(
                        adapter_id="jetson_presence",
                        kind=EdgeAdapterKind.PRESENCE,
                        event_type="person_detected",
                        note="Simulated presence input under the Jetson hardware profile.",
                    ),
                    NetworkMonitorInput(adapter_id="jetson_network", simulated=True),
                    BatteryMonitorInput(adapter_id="jetson_battery", simulated=True),
                    HeartbeatMonitorInput(adapter_id="jetson_heartbeat", simulated=True),
                ],
            )

        if profile_name == "jetson_landing_zone":
            return (
                RobotMode.HARDWARE,
                False,
                False,
                [
                    NotWiredActuator(
                        adapter_id="jetson_speaker",
                        kind=EdgeAdapterKind.SPEAKER_TRIGGER,
                        supported_command=CommandType.SPEAK,
                        note="Speaker trigger adapter is declared, but robot audio output is not wired yet.",
                    ),
                    NotWiredActuator(
                        adapter_id="jetson_display",
                        kind=EdgeAdapterKind.DISPLAY,
                        supported_command=CommandType.DISPLAY_TEXT,
                        note="Display adapter is declared, but the physical display transport is not wired yet.",
                    ),
                    NotWiredActuator(
                        adapter_id="jetson_led",
                        kind=EdgeAdapterKind.LED,
                        supported_command=CommandType.SET_LED,
                        note="LED adapter is declared, but GPIO or driver wiring is not present yet.",
                    ),
                    NotWiredActuator(
                        adapter_id="jetson_head_pose",
                        kind=EdgeAdapterKind.HEAD_POSE,
                        supported_command=CommandType.SET_HEAD_POSE,
                        note="Head-pose adapter is declared, but the servo bridge is not wired yet.",
                    ),
                ],
                [
                    TranscriptRelayInput(adapter_id="jetson_transcript", simulated=False, enabled=False),
                    NotWiredInput(
                        adapter_id="jetson_touch",
                        kind=EdgeAdapterKind.TOUCH,
                        event_type="touch",
                        note="Touch input boundary exists, but the button or capacitive sensor is not wired yet.",
                    ),
                    NotWiredInput(
                        adapter_id="jetson_button",
                        kind=EdgeAdapterKind.BUTTON,
                        event_type="button",
                        note="Button input boundary exists, but no physical button adapter is wired yet.",
                    ),
                    NotWiredInput(
                        adapter_id="jetson_presence",
                        kind=EdgeAdapterKind.PRESENCE,
                        event_type="person_detected",
                        note="Presence input boundary exists, but no camera or proximity adapter is wired yet.",
                    ),
                    NetworkMonitorInput(
                        adapter_id="jetson_network",
                        simulated=False,
                        state=EdgeAdapterState.ACTIVE,
                        note="Network adapter boundary is active and ready for real tether watchdog data.",
                    ),
                    BatteryMonitorInput(
                        adapter_id="jetson_battery",
                        simulated=False,
                        state=EdgeAdapterState.UNAVAILABLE,
                        note="Battery monitor boundary exists, but a real battery sensor is not wired yet.",
                    ),
                    HeartbeatMonitorInput(
                        adapter_id="jetson_heartbeat",
                        simulated=False,
                        state=EdgeAdapterState.ACTIVE,
                        note="Heartbeat watchdog remains active even before final robot hardware arrives.",
                    ),
                ],
            )

        raise ValueError(f"unknown_edge_driver_profile:{profile_name}")


class JetsonDriverStub(JetsonHardwareDriver):
    def __init__(self, heartbeat_timeout_seconds: float = 15.0) -> None:
        super().__init__(profile_name="jetson_landing_zone", heartbeat_timeout_seconds=heartbeat_timeout_seconds)


def build_robot_driver(settings: Settings) -> RobotDriver:
    profile_name = settings.edge_driver_profile
    if profile_name == "fake_robot_full":
        return FakeRobotDriver(heartbeat_timeout_seconds=settings.edge_heartbeat_timeout_seconds)
    if profile_name.startswith("jetson_"):
        return JetsonHardwareDriver(
            profile_name=profile_name,
            heartbeat_timeout_seconds=settings.edge_heartbeat_timeout_seconds,
        )
    raise ValueError(f"unknown_edge_driver_profile:{profile_name}")
