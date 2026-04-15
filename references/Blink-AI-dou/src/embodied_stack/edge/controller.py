from __future__ import annotations

from embodied_stack.config import Settings, get_settings
from embodied_stack.edge.drivers import RobotDriver, build_robot_driver
from embodied_stack.edge.safety import validate_command
from embodied_stack.shared.models import (
    CommandAck,
    CommandAckStatus,
    CommandHistoryEntry,
    CommandHistoryResponse,
    HeartbeatStatus,
    RobotCommand,
    SimulatedSensorEventRequest,
    SimulatedSensorEventResult,
    TelemetryLogResponse,
    TelemetrySnapshot,
)


class SimulatedRobotController:
    def __init__(self, driver: RobotDriver | None = None, *, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.driver = driver or build_robot_driver(self.settings)
        self.command_history: list[CommandHistoryEntry] = []
        self.command_ack_cache: dict[str, CommandAck] = {}
        self.command_attempt_counts: dict[str, int] = {}

    @property
    def capabilities(self):
        return self.driver.capabilities

    def get_telemetry(self) -> TelemetrySnapshot:
        return self.driver.get_telemetry()

    def get_heartbeat(self) -> HeartbeatStatus:
        return self.driver.get_heartbeat()

    def get_telemetry_log(self) -> TelemetryLogResponse:
        return TelemetryLogResponse(items=self.driver.get_telemetry_log())

    def get_command_history(self) -> CommandHistoryResponse:
        return CommandHistoryResponse(items=[entry.model_copy(deep=True) for entry in self.command_history])

    def apply_command(self, command: RobotCommand) -> CommandAck:
        self.command_attempt_counts[command.command_id] = self.command_attempt_counts.get(command.command_id, 0) + 1
        if cached := self.command_ack_cache.get(command.command_id):
            return cached.model_copy(
                update={
                    "status": CommandAckStatus.DUPLICATE,
                    "attempt_count": self.command_attempt_counts[command.command_id],
                },
                deep=True,
            )

        heartbeat = self.driver.get_heartbeat()
        telemetry = self.driver.get_telemetry()
        accepted, reason, normalized_payload = validate_command(
            command,
            safe_idle_active=heartbeat.safe_idle_active,
            capabilities=self.driver.capabilities,
            telemetry=telemetry,
        )
        if not accepted:
            ack = CommandAck(
                command_id=command.command_id,
                accepted=False,
                status=CommandAckStatus.REJECTED,
                reason=reason,
                attempt_count=self.command_attempt_counts[command.command_id],
                applied_state=telemetry.model_dump(mode="json"),
            )
            self.command_ack_cache[command.command_id] = ack.model_copy(deep=True)
            self.command_history.append(CommandHistoryEntry(command=command, ack=ack))
            return ack

        applied_state = self.driver.execute_command(command, normalized_payload)
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
        return ack

    def simulate_event(self, request: SimulatedSensorEventRequest) -> SimulatedSensorEventResult:
        return self.driver.simulate_event(request, now=request.timestamp)

    def force_safe_idle(self, reason: str = "operator_override") -> HeartbeatStatus:
        return self.driver.force_safe_idle(reason)

    def reset(self) -> None:
        self.driver.reset()
        self.command_history = []
        self.command_ack_cache = {}
        self.command_attempt_counts = {}
