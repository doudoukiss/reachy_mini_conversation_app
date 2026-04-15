from __future__ import annotations

from embodied_stack.shared.contracts.body import BodyCommandOutcomeRecord, HeadProfile, ServoHealthRecord

from .protocol import (
    ADDRESS_PRESENT_ASYNC_FLAG,
    ADDRESS_PRESENT_CURRENT,
    ADDRESS_PRESENT_LOAD,
    ADDRESS_PRESENT_MOVING,
    ADDRESS_PRESENT_POSITION,
    ADDRESS_PRESENT_SPEED,
    ADDRESS_PRESENT_STATUS,
    ADDRESS_PRESENT_TEMPERATURE,
    ADDRESS_PRESENT_VOLTAGE,
    ADDRESS_TORQUE_SWITCH,
    unpack_u16_le,
)
from .transport import BaseServoTransport, ServoTransportError

ERROR_BIT_LABELS = {
    0: "input_voltage",
    1: "angle_limit",
    2: "overheat",
    3: "range",
    4: "checksum",
    5: "overload",
    6: "instruction",
    7: "timeout",
}
STATUS_BIT_LABELS = {
    0: "bit0",
    1: "bit1",
    2: "bit2",
    3: "bit3",
    4: "bit4",
    5: "bit5",
    6: "bit6",
    7: "bit7",
}
VOLTAGE_RAW_SCALE_VOLTS = 0.1
BENCH_HEALTH_START_ADDRESS = ADDRESS_PRESENT_POSITION
BENCH_HEALTH_LENGTH = ADDRESS_PRESENT_MOVING - ADDRESS_PRESENT_POSITION + 1


def decode_error_bits(error_code: int) -> list[str]:
    bits = int(error_code or 0)
    labels = [label for bit, label in ERROR_BIT_LABELS.items() if bits & (1 << bit)]
    return labels or ([] if bits == 0 else [f"unknown:0x{bits:02X}"])


def decode_status_bits(status_code: int) -> list[str]:
    bits = int(status_code or 0)
    labels = [label for bit, label in STATUS_BIT_LABELS.items() if bits & (1 << bit)]
    return labels or []


def decode_bench_health_payload(
    payload: bytes,
    *,
    current_payload: bytes | None = None,
    torque_enabled: bool | None = None,
    packet_error: int = 0,
) -> dict[str, object]:
    if len(payload) < BENCH_HEALTH_LENGTH:
        raise ServoTransportError(
            "invalid_reply",
            f"bench_health_payload_too_short:expected={BENCH_HEALTH_LENGTH}:actual={len(payload)}",
        )
    status_bits = int(payload[ADDRESS_PRESENT_STATUS - BENCH_HEALTH_START_ADDRESS])
    moving = bool(payload[ADDRESS_PRESENT_MOVING - BENCH_HEALTH_START_ADDRESS])
    voltage_raw = int(payload[ADDRESS_PRESENT_VOLTAGE - BENCH_HEALTH_START_ADDRESS])
    bench_health = {
        "position": unpack_u16_le(payload[ADDRESS_PRESENT_POSITION - BENCH_HEALTH_START_ADDRESS : ADDRESS_PRESENT_POSITION - BENCH_HEALTH_START_ADDRESS + 2]),
        "speed": unpack_u16_le(payload[ADDRESS_PRESENT_SPEED - BENCH_HEALTH_START_ADDRESS : ADDRESS_PRESENT_SPEED - BENCH_HEALTH_START_ADDRESS + 2]),
        "load": unpack_u16_le(payload[ADDRESS_PRESENT_LOAD - BENCH_HEALTH_START_ADDRESS : ADDRESS_PRESENT_LOAD - BENCH_HEALTH_START_ADDRESS + 2]),
        "voltage": voltage_raw,
        "voltage_raw": voltage_raw,
        "voltage_volts": round(voltage_raw * VOLTAGE_RAW_SCALE_VOLTS, 2),
        "temperature": int(payload[ADDRESS_PRESENT_TEMPERATURE - BENCH_HEALTH_START_ADDRESS]),
        "async_write_flag": bool(payload[ADDRESS_PRESENT_ASYNC_FLAG - BENCH_HEALTH_START_ADDRESS]),
        "status_bits": status_bits,
        "status_flags": decode_status_bits(status_bits),
        "moving": moving,
        "torque_enabled": torque_enabled,
        "error_bits": decode_error_bits(packet_error),
    }
    if current_payload is not None and len(current_payload) == 2:
        bench_health["current"] = unpack_u16_le(current_payload)
    else:
        bench_health["current"] = None
    bench_health["status_summary"] = (
        f"position={bench_health['position']};"
        f" speed={bench_health['speed']};"
        f" load={bench_health['load']};"
        f" voltage_raw={bench_health['voltage_raw']};"
        f" voltage_volts={bench_health['voltage_volts']};"
        f" temperature={bench_health['temperature']};"
        f" moving={'yes' if moving else 'no'};"
        f" torque={'on' if torque_enabled else 'off' if torque_enabled is not None else 'unknown'};"
        f" status=0x{status_bits:02X}"
    )
    return bench_health


def read_bench_health(transport: BaseServoTransport, servo_id: int) -> dict[str, object]:
    packet = transport.sync_read_status(BENCH_HEALTH_START_ADDRESS, BENCH_HEALTH_LENGTH, [servo_id]).get(servo_id)
    if packet is None:
        raise ServoTransportError("timeout", f"bench_health_missing_reply:id={servo_id}")

    torque_enabled = None
    try:
        torque_packet = transport.sync_read_status(ADDRESS_TORQUE_SWITCH, 1, [servo_id]).get(servo_id)
    except ServoTransportError:
        torque_packet = None
    if torque_packet is not None and torque_packet.parameters:
        torque_enabled = bool(torque_packet.parameters[0])

    current_payload = None
    current_error = None
    try:
        current_payload = transport.read(servo_id, ADDRESS_PRESENT_CURRENT, 2)
    except ServoTransportError as exc:
        current_error = f"{exc.classification}:{exc.detail}"

    result = decode_bench_health_payload(
        packet.parameters,
        current_payload=current_payload,
        torque_enabled=torque_enabled,
        packet_error=int(packet.error or 0),
    )
    result["servo_id"] = int(servo_id)
    if current_error is not None:
        result["current_error"] = current_error
    return result


def read_bench_health_many(transport: BaseServoTransport, servo_ids: list[int]) -> dict[int, dict[str, object]]:
    results: dict[int, dict[str, object]] = {}
    for servo_id in servo_ids:
        try:
            results[servo_id] = read_bench_health(transport, servo_id)
        except ServoTransportError as exc:
            results[servo_id] = {"servo_id": int(servo_id), "error": f"{exc.classification}:{exc.detail}"}
    return results


def servo_health_from_bench_reads(
    *,
    profile: HeadProfile,
    bench_health: dict[int, dict[str, object]],
    target_positions: dict[str, int] | None = None,
    last_command_outcome: BodyCommandOutcomeRecord | None = None,
    power_health_classification: str | None = None,
) -> dict[str, ServoHealthRecord]:
    records: dict[str, ServoHealthRecord] = {}
    for joint in profile.joints:
        if not joint.enabled or not joint.servo_ids:
            continue
        servo_id = int(joint.servo_ids[0])
        payload = bench_health.get(servo_id, {})
        payload_error = payload.get("error")
        error_bits = [str(item) for item in payload.get("error_bits") or []]
        current_position = int(payload["position"]) if payload.get("position") is not None else None
        voltage_raw = int(payload["voltage_raw"]) if payload.get("voltage_raw") is not None else (
            int(payload["voltage"]) if payload.get("voltage") is not None else None
        )
        records[joint.joint_name] = ServoHealthRecord(
            servo_id=servo_id,
            joint_name=joint.joint_name,
            current_position=current_position,
            target_position=(target_positions or {}).get(joint.joint_name),
            torque_enabled=bool(payload["torque_enabled"]) if payload.get("torque_enabled") is not None else None,
            voltage=voltage_raw,
            voltage_raw=voltage_raw,
            voltage_volts=(
                round(voltage_raw * VOLTAGE_RAW_SCALE_VOLTS, 2)
                if voltage_raw is not None
                else None
            ),
            load=int(payload["load"]) if payload.get("load") is not None else None,
            current=int(payload["current"]) if payload.get("current") is not None else None,
            temperature=int(payload["temperature"]) if payload.get("temperature") is not None else None,
            moving=bool(payload["moving"]) if payload.get("moving") is not None else None,
            power_health_classification=power_health_classification,
            error_bits=error_bits,
            last_poll_status="ok" if payload_error is None else "missing",
            reason_code=(
                "ok"
                if payload_error is None and not error_bits
                else ("servo_status_error" if payload_error is None else str(payload_error))
            ),
            status_summary=str(payload.get("status_summary") or payload_error or ""),
            last_command_outcome=(
                last_command_outcome.outcome_status
                if last_command_outcome is not None
                else None
            ),
        )
    return records


def collect_servo_health(
    *,
    profile: HeadProfile,
    transport: BaseServoTransport,
    target_positions: dict[str, int] | None = None,
    last_command_outcome: BodyCommandOutcomeRecord | None = None,
) -> dict[str, ServoHealthRecord]:
    servo_ids = sorted({servo_id for joint in profile.joints if joint.enabled for servo_id in joint.servo_ids})
    position_packets = transport.sync_read_status(ADDRESS_PRESENT_POSITION, 2, servo_ids)
    torque_packets: dict[int, object] = {}
    try:
        torque_packets = transport.sync_read_status(ADDRESS_TORQUE_SWITCH, 1, servo_ids)
    except ServoTransportError:
        torque_packets = {}

    records: dict[str, ServoHealthRecord] = {}
    for joint in profile.joints:
        if not joint.enabled or not joint.servo_ids:
            continue
        servo_id = joint.servo_ids[0]
        position_packet = position_packets.get(servo_id)
        torque_packet = torque_packets.get(servo_id)
        error_code = int((position_packet.error if position_packet is not None else 0) or 0)
        if torque_packet is not None:
            error_code |= int(torque_packet.error or 0)
        current_position = None
        if position_packet is not None and len(position_packet.parameters) >= 2:
            current_position = unpack_u16_le(position_packet.parameters[:2])
        torque_enabled = None
        if torque_packet is not None and torque_packet.parameters:
            torque_enabled = bool(torque_packet.parameters[0])
        reason_code = "ok"
        if position_packet is None:
            reason_code = transport.status.reason_code or "transport_unconfirmed"
        elif error_code:
            reason_code = "servo_status_error"
        records[joint.joint_name] = ServoHealthRecord(
            servo_id=servo_id,
            joint_name=joint.joint_name,
            current_position=current_position,
            target_position=(target_positions or {}).get(joint.joint_name),
            torque_enabled=torque_enabled,
            voltage=None,
            voltage_raw=None,
            voltage_volts=None,
            load=None,
            current=None,
            temperature=None,
            moving=None,
            power_health_classification=None,
            error_bits=decode_error_bits(error_code),
            last_poll_status="ok" if position_packet is not None else "missing",
            reason_code=reason_code,
            status_summary=(
                f"poll={'ok' if position_packet is not None else 'missing'};"
                f" torque={'on' if torque_enabled else 'off' if torque_enabled is not None else 'unknown'};"
                f" errors={','.join(decode_error_bits(error_code)) or '-'}"
            ),
            last_command_outcome=(
                last_command_outcome.outcome_status
                if last_command_outcome is not None
                else None
            ),
        )
    return records


__all__ = [
    "BENCH_HEALTH_LENGTH",
    "BENCH_HEALTH_START_ADDRESS",
    "collect_servo_health",
    "decode_bench_health_payload",
    "decode_error_bits",
    "decode_status_bits",
    "read_bench_health",
    "read_bench_health_many",
    "servo_health_from_bench_reads",
    "VOLTAGE_RAW_SCALE_VOLTS",
]
