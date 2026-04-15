from __future__ import annotations

from .body import BodyCapabilityProfile, BodyState
from ._common import (
    Any,
    BaseModel,
    BodyDriverMode,
    CommandAckStatus,
    CommandType,
    EdgeAdapterDirection,
    EdgeAdapterKind,
    EdgeAdapterState,
    EdgeTransportMode,
    Field,
    RobotMode,
    SessionStatus,
    TransportState,
    datetime,
    model_validator,
    utc_now,
    uuid4,
)


class RobotEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: str(uuid4()))
    event_type: str
    source: str = "simulator"
    session_id: str | None = None
    timestamp: datetime = Field(default_factory=utc_now)
    payload: dict[str, Any] = Field(default_factory=dict)


class RobotCommand(BaseModel):
    command_id: str = Field(default_factory=lambda: str(uuid4()))
    command_type: CommandType
    timestamp: datetime = Field(default_factory=utc_now)
    priority: int = Field(default=5, ge=0, le=10)
    requires_ack: bool = True
    payload: dict[str, Any] = Field(default_factory=dict)


class CommandBatch(BaseModel):
    session_id: str = "default-session"
    reply_text: str | None = None
    commands: list[RobotCommand] = Field(default_factory=list)
    trace_id: str | None = None
    status: SessionStatus = SessionStatus.ACTIVE


class CommandAck(BaseModel):
    command_id: str
    accepted: bool
    status: CommandAckStatus = CommandAckStatus.APPLIED
    reason: str = "ok"
    transport_error: str | None = None
    attempt_count: int = 1
    timestamp: datetime = Field(default_factory=utc_now)
    applied_state: dict[str, Any] = Field(default_factory=dict)


class CommandHistoryEntry(BaseModel):
    command: RobotCommand
    ack: CommandAck


class CommandHistoryResponse(BaseModel):
    items: list[CommandHistoryEntry] = Field(default_factory=list)


class EdgeAdapterCapability(BaseModel):
    adapter_id: str
    kind: EdgeAdapterKind
    direction: EdgeAdapterDirection
    enabled: bool = True
    simulated: bool = False
    supported_commands: list[CommandType] = Field(default_factory=list)
    emitted_events: list[str] = Field(default_factory=list)
    note: str | None = None


class EdgeAdapterHealth(BaseModel):
    adapter_id: str
    kind: EdgeAdapterKind
    direction: EdgeAdapterDirection
    state: EdgeAdapterState = EdgeAdapterState.ACTIVE
    note: str | None = None
    last_updated: datetime = Field(default_factory=utc_now)


class ReadinessCheck(BaseModel):
    name: str
    ok: bool = True
    status: str = "ready"
    detail: str | None = None
    category: str = "runtime"
    reason_code: str | None = None
    required_for: list[str] = Field(default_factory=list)


class ServiceReadinessResponse(BaseModel):
    ok: bool = True
    service: str
    runtime_profile: str | None = None
    checks: list[ReadinessCheck] = Field(default_factory=list)
    process_ok: bool = True
    usable_ok: bool = True
    media_ok: bool = True
    best_experience_ok: bool = True
    status: str = "ready"

    @model_validator(mode="after")
    def _sync_readiness_aliases(self) -> "ServiceReadinessResponse":
        if self.ok != self.usable_ok:
            if self.usable_ok is True and self.ok is not True:
                self.usable_ok = self.ok
            else:
                self.ok = self.usable_ok
        else:
            self.ok = self.usable_ok
        if not self.status:
            if not self.process_ok or not self.usable_ok:
                self.status = "blocked"
            elif not self.media_ok:
                self.status = "media_degraded"
            elif not self.best_experience_ok:
                self.status = "best_experience_degraded"
            else:
                self.status = "ready"
        return self


class TelemetrySnapshot(BaseModel):
    mode: RobotMode = RobotMode.SIMULATED
    runtime_profile: str | None = None
    body_driver_mode: BodyDriverMode | None = None
    body_state: BodyState | None = None
    body_capabilities: BodyCapabilityProfile | None = None
    head_yaw_deg: float = 0.0
    head_pitch_deg: float = 0.0
    active_expression: str | None = None
    attention_state: str | None = None
    gaze_target: str | None = None
    last_gesture: str | None = None
    last_animation: str | None = None
    camera_source: str | None = None
    voice_profile: str | None = None
    led_color: str = "off"
    display_text: str | None = None
    speaking: bool = False
    battery_pct: float = 100.0
    network_ok: bool = True
    last_spoken_text: str | None = None
    last_sensor_event_type: str | None = None
    safe_idle_reason: str | None = None
    network_latency_ms: float | None = None
    transport_ok: bool = True
    transport_error: str | None = None
    adapter_health: list[EdgeAdapterHealth] = Field(default_factory=list)
    last_updated: datetime = Field(default_factory=utc_now)


class TelemetryLogEntry(BaseModel):
    entry_id: str = Field(default_factory=lambda: str(uuid4()))
    timestamp: datetime = Field(default_factory=utc_now)
    source: str = "edge"
    note: str | None = None
    telemetry: TelemetrySnapshot


class TelemetryLogResponse(BaseModel):
    items: list[TelemetryLogEntry] = Field(default_factory=list)


class HeartbeatStatus(BaseModel):
    connected: bool = True
    network_ok: bool = True
    safe_idle_active: bool = False
    safe_idle_reason: str | None = None
    transport_ok: bool = True
    transport_error: str | None = None
    last_contact_at: datetime = Field(default_factory=utc_now)
    timeout_seconds: float = 15.0


class CapabilityProfile(BaseModel):
    mode: RobotMode = RobotMode.SIMULATED
    runtime_profile: str = "fake_robot_full"
    body_driver_mode: BodyDriverMode | None = None
    body_capabilities: BodyCapabilityProfile | None = None
    head_profile_path: str | None = None
    supports_voice_output: bool = True
    supports_led: bool = True
    supports_head_pose: bool = True
    supports_display: bool = True
    supports_base_motion: bool = False
    supports_semantic_body: bool = False
    supports_virtual_body_preview: bool = False
    supports_touch_sensor: bool = True
    supports_button_sensor: bool = True
    supports_person_detection: bool = True
    supports_network_monitor: bool = True
    supports_battery_monitor: bool = True
    supports_heartbeat_monitor: bool = True
    supports_simulated_events: bool = True
    adapters: list[EdgeAdapterCapability] = Field(default_factory=list)


class SimulatedSensorEventRequest(BaseModel):
    event_type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    session_id: str | None = None
    source: str = "edge_simulator"
    timestamp: datetime | None = None


class SimulatedSensorEventResult(BaseModel):
    event: RobotEvent
    telemetry: TelemetrySnapshot
    heartbeat: HeartbeatStatus


__all__ = [
    "CapabilityProfile",
    "CommandAck",
    "CommandAckStatus",
    "CommandBatch",
    "CommandHistoryEntry",
    "CommandHistoryResponse",
    "CommandType",
    "EdgeAdapterCapability",
    "EdgeAdapterDirection",
    "EdgeAdapterHealth",
    "EdgeAdapterKind",
    "EdgeAdapterState",
    "EdgeTransportMode",
    "HeartbeatStatus",
    "ReadinessCheck",
    "RobotCommand",
    "RobotEvent",
    "RobotMode",
    "ServiceReadinessResponse",
    "SessionStatus",
    "SimulatedSensorEventRequest",
    "SimulatedSensorEventResult",
    "TelemetryLogEntry",
    "TelemetryLogResponse",
    "TelemetrySnapshot",
    "TransportState",
]
