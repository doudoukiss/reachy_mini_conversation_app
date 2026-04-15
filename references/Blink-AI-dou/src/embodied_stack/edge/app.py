from __future__ import annotations

from fastapi import FastAPI

from embodied_stack.config import Settings, get_settings
from embodied_stack.edge.controller import SimulatedRobotController
from embodied_stack.shared.readiness import build_service_readiness_response
from embodied_stack.shared.models import (
    CommandAck,
    CommandHistoryResponse,
    EdgeAdapterKind,
    EdgeAdapterState,
    HeartbeatStatus,
    ReadinessCheck,
    ResetResult,
    RobotCommand,
    ServiceReadinessResponse,
    SimulatedSensorEventRequest,
    SimulatedSensorEventResult,
    TelemetryLogResponse,
    TelemetrySnapshot,
)


def create_app(
    *,
    settings: Settings | None = None,
    controller: SimulatedRobotController | None = None,
) -> FastAPI:
    runtime_settings = settings or get_settings()
    edge_controller = controller or SimulatedRobotController(settings=runtime_settings)

    app = FastAPI(title=f"{runtime_settings.project_name} Edge API")
    app.state.controller = edge_controller

    @app.get("/health")
    def health() -> dict:
        return {
            "ok": True,
            "service": "edge",
            "project_name": runtime_settings.project_name,
            "runtime_profile": edge_controller.capabilities.runtime_profile,
        }

    @app.get("/ready", response_model=ServiceReadinessResponse)
    def readiness() -> ServiceReadinessResponse:
        telemetry = edge_controller.get_telemetry()
        heartbeat = edge_controller.get_heartbeat()
        capabilities = edge_controller.capabilities
        ready_states = {EdgeAdapterState.ACTIVE, EdgeAdapterState.SIMULATED, EdgeAdapterState.DEGRADED}
        health_by_kind = {item.kind: item for item in telemetry.adapter_health}

        actuator_ready = all(
            health_by_kind.get(kind) is not None and health_by_kind[kind].state in ready_states
            for kind in (
                EdgeAdapterKind.SPEAKER_TRIGGER,
                EdgeAdapterKind.DISPLAY,
                EdgeAdapterKind.LED,
                EdgeAdapterKind.HEAD_POSE,
            )
        )
        simulated_event_ready = capabilities.supports_simulated_events
        watchdog_ready = capabilities.supports_heartbeat_monitor and heartbeat.transport_ok

        checks = [
            ReadinessCheck(
                name="driver_profile",
                ok=True,
                status="ready",
                detail=capabilities.runtime_profile,
                category="runtime",
                reason_code="driver_profile_loaded",
                required_for=["process", "usable"],
            ),
            ReadinessCheck(
                name="actuator_surface",
                ok=actuator_ready,
                status="ready" if actuator_ready else "degraded",
                detail="speaker/display/led/head_pose",
                category="actuator",
                reason_code="actuator_surface_ready" if actuator_ready else "actuator_surface_degraded",
                required_for=["usable", "best_experience"],
            ),
            ReadinessCheck(
                name="event_bridge",
                ok=simulated_event_ready,
                status="ready" if simulated_event_ready else "degraded",
                detail="simulated_events_enabled" if simulated_event_ready else "simulated_events_disabled",
                category="runtime",
                reason_code="simulated_events_enabled" if simulated_event_ready else "simulated_events_disabled",
                required_for=["usable"],
            ),
            ReadinessCheck(
                name="watchdog",
                ok=watchdog_ready,
                status="ready" if watchdog_ready else "blocked",
                detail=heartbeat.safe_idle_reason or "heartbeat_monitor_ok",
                category="runtime",
                reason_code="heartbeat_monitor_ok" if watchdog_ready else "heartbeat_monitor_blocked",
                required_for=["process", "usable"],
            ),
        ]
        return build_service_readiness_response(
            service="edge",
            runtime_profile=capabilities.runtime_profile,
            checks=checks,
        )

    @app.get("/api/capabilities")
    def capabilities() -> dict:
        return edge_controller.capabilities.model_dump(mode="json")

    @app.get("/api/telemetry", response_model=TelemetrySnapshot)
    def telemetry() -> TelemetrySnapshot:
        return edge_controller.get_telemetry()

    @app.get("/api/telemetry/log", response_model=TelemetryLogResponse)
    def telemetry_log() -> TelemetryLogResponse:
        return edge_controller.get_telemetry_log()

    @app.get("/api/heartbeat", response_model=HeartbeatStatus)
    def heartbeat() -> HeartbeatStatus:
        return edge_controller.get_heartbeat()

    @app.post("/api/commands", response_model=CommandAck)
    def apply_command(command: RobotCommand) -> CommandAck:
        return edge_controller.apply_command(command)

    @app.post("/api/sim/events", response_model=SimulatedSensorEventResult)
    def simulate_event(request: SimulatedSensorEventRequest) -> SimulatedSensorEventResult:
        return edge_controller.simulate_event(request)

    @app.post("/api/safe-idle", response_model=HeartbeatStatus)
    def safe_idle(reason: str = "operator_override") -> HeartbeatStatus:
        return edge_controller.force_safe_idle(reason)

    @app.post("/api/reset", response_model=ResetResult)
    def reset() -> ResetResult:
        edge_controller.reset()
        return ResetResult(ok=True, brain_reset=False, edge_reset=True, cleared_demo_runs=False)

    @app.get("/api/command-history", response_model=CommandHistoryResponse)
    def command_history() -> CommandHistoryResponse:
        return edge_controller.get_command_history()

    return app


settings = get_settings()
app = create_app(settings=settings)


def main() -> None:
    import uvicorn

    uvicorn.run("embodied_stack.edge.app:app", host=settings.edge_host, port=settings.edge_port, reload=False)


if __name__ == "__main__":
    main()
