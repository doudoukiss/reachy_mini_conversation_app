from __future__ import annotations

from embodied_stack.shared.models import (
    CapabilityProfile,
    CommandType,
    EdgeAdapterKind,
    EdgeAdapterState,
    RobotCommand,
    TelemetrySnapshot,
)


MAX_HEAD_YAW_DEG = 60.0
MIN_HEAD_YAW_DEG = -60.0
MAX_HEAD_PITCH_DEG = 25.0
MIN_HEAD_PITCH_DEG = -25.0

COMMAND_CAPABILITY_FIELDS: dict[CommandType, str] = {
    CommandType.SPEAK: "supports_voice_output",
    CommandType.DISPLAY_TEXT: "supports_display",
    CommandType.SET_LED: "supports_led",
    CommandType.SET_HEAD_POSE: "supports_head_pose",
}

COMMAND_ADAPTER_KINDS: dict[CommandType, EdgeAdapterKind] = {
    CommandType.SPEAK: EdgeAdapterKind.SPEAKER_TRIGGER,
    CommandType.DISPLAY_TEXT: EdgeAdapterKind.DISPLAY,
    CommandType.SET_LED: EdgeAdapterKind.LED,
    CommandType.SET_HEAD_POSE: EdgeAdapterKind.HEAD_POSE,
}


def validate_command(
    command: RobotCommand,
    *,
    safe_idle_active: bool = False,
    capabilities: CapabilityProfile | None = None,
    telemetry: TelemetrySnapshot | None = None,
) -> tuple[bool, str, dict]:
    if command.command_type == CommandType.MOVE_BASE:
        return False, "base_motion_not_supported_in_starter", {}

    supported, reason = _capability_status_for_command(command, capabilities=capabilities, telemetry=telemetry)
    if not supported:
        return False, reason, {}

    if safe_idle_active and command.command_type == CommandType.SET_HEAD_POSE:
        return False, "safe_idle_rejects_head_pose", {}

    if command.command_type == CommandType.SET_HEAD_POSE:
        yaw = float(command.payload.get("head_yaw_deg", 0.0))
        pitch = float(command.payload.get("head_pitch_deg", 0.0))
        clamped = {
            "head_yaw_deg": max(MIN_HEAD_YAW_DEG, min(MAX_HEAD_YAW_DEG, yaw)),
            "head_pitch_deg": max(MIN_HEAD_PITCH_DEG, min(MAX_HEAD_PITCH_DEG, pitch)),
        }
        return True, "ok", clamped

    return True, "ok", dict(command.payload)


def _capability_status_for_command(
    command: RobotCommand,
    *,
    capabilities: CapabilityProfile | None,
    telemetry: TelemetrySnapshot | None,
) -> tuple[bool, str]:
    if capabilities is None:
        return True, "ok"

    capability_field = COMMAND_CAPABILITY_FIELDS.get(command.command_type)
    if capability_field and not getattr(capabilities, capability_field):
        return False, f"capability_disabled:{command.command_type.value}"

    adapter_kind = COMMAND_ADAPTER_KINDS.get(command.command_type)
    if telemetry is None or adapter_kind is None:
        return True, "ok"

    for adapter_health in telemetry.adapter_health:
        if adapter_health.kind != adapter_kind:
            continue
        if adapter_health.state == EdgeAdapterState.UNAVAILABLE:
            return False, f"adapter_unavailable:{adapter_kind.value}"
        if adapter_health.state == EdgeAdapterState.DISABLED:
            return False, f"adapter_disabled:{adapter_kind.value}"
        break

    return True, "ok"
