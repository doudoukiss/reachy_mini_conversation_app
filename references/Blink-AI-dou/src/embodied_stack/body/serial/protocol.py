from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Iterable, Sequence

HEADER = bytes((0xFF, 0xFF))
BROADCAST_ID = 0xFE

ADDRESS_TORQUE_SWITCH = 0x28
ADDRESS_START_ACCELERATION = 0x29
ADDRESS_TARGET_POSITION = 0x2A
ADDRESS_RUNNING_SPEED = 0x2E
ADDRESS_PRESENT_POSITION = 0x38
ADDRESS_PRESENT_SPEED = 0x3A
ADDRESS_PRESENT_LOAD = 0x3C
ADDRESS_PRESENT_VOLTAGE = 0x3E
ADDRESS_PRESENT_TEMPERATURE = 0x3F
ADDRESS_PRESENT_ASYNC_FLAG = 0x40
ADDRESS_PRESENT_STATUS = 0x41
ADDRESS_PRESENT_MOVING = 0x42
ADDRESS_PRESENT_CURRENT = 0x45


class FeetechInstruction(IntEnum):
    PING = 0x01
    READ = 0x02
    WRITE = 0x03
    REG_WRITE = 0x04
    ACTION = 0x05
    RECOVERY = 0x06
    RESET = 0x0A
    SYNC_READ = 0x82
    SYNC_WRITE = 0x83


class FeetechProtocolError(ValueError):
    pass


@dataclass(frozen=True)
class FeetechPacket:
    servo_id: int
    length: int
    instruction: int
    parameters: bytes
    checksum: int
    raw_frame: bytes


@dataclass(frozen=True)
class FeetechStatusPacket:
    servo_id: int
    length: int
    error: int
    parameters: bytes
    checksum: int
    raw_frame: bytes


def normalize_servo_id(servo_id: int) -> int:
    if not 0 <= int(servo_id) <= 0xFE:
        raise FeetechProtocolError(f"invalid_servo_id:{servo_id}")
    return int(servo_id)


def checksum(payload: Iterable[int] | bytes) -> int:
    total = sum(int(value) & 0xFF for value in payload) & 0xFF
    return (~total) & 0xFF


def pack_u16_le(value: int) -> bytes:
    if not 0 <= int(value) <= 0xFFFF:
        raise FeetechProtocolError(f"u16_out_of_range:{value}")
    value = int(value)
    return bytes((value & 0xFF, (value >> 8) & 0xFF))


def pack_u8(value: int) -> bytes:
    if not 0 <= int(value) <= 0xFF:
        raise FeetechProtocolError(f"u8_out_of_range:{value}")
    return bytes((int(value) & 0xFF,))


def unpack_u16_le(payload: bytes) -> int:
    if len(payload) != 2:
        raise FeetechProtocolError(f"u16_requires_two_bytes:{len(payload)}")
    return payload[0] | (payload[1] << 8)


def encode_instruction_packet(servo_id: int, instruction: int | FeetechInstruction, parameters: bytes | Sequence[int] = b"") -> bytes:
    normalized_id = normalize_servo_id(servo_id)
    payload = bytes(parameters)
    length = len(payload) + 2
    body = bytes((normalized_id, length, int(instruction) & 0xFF)) + payload
    return HEADER + body + bytes((checksum(body),))


def encode_status_packet(servo_id: int, error: int = 0, parameters: bytes | Sequence[int] = b"") -> bytes:
    normalized_id = normalize_servo_id(servo_id)
    payload = bytes(parameters)
    length = len(payload) + 2
    body = bytes((normalized_id, length, int(error) & 0xFF)) + payload
    return HEADER + body + bytes((checksum(body),))


def decode_packet(frame: bytes) -> FeetechPacket:
    if len(frame) < 6:
        raise FeetechProtocolError(f"frame_too_short:{len(frame)}")
    if frame[:2] != HEADER:
        raise FeetechProtocolError("missing_header")
    servo_id = frame[2]
    length = frame[3]
    expected_size = length + 4
    if len(frame) != expected_size:
        raise FeetechProtocolError(f"invalid_frame_length:expected={expected_size}:actual={len(frame)}")
    expected_checksum = checksum(frame[2:-1])
    if frame[-1] != expected_checksum:
        raise FeetechProtocolError(
            f"checksum_mismatch:expected=0x{expected_checksum:02X}:actual=0x{frame[-1]:02X}"
        )
    instruction = frame[4]
    parameters = frame[5:-1]
    return FeetechPacket(
        servo_id=servo_id,
        length=length,
        instruction=instruction,
        parameters=parameters,
        checksum=frame[-1],
        raw_frame=bytes(frame),
    )


def decode_status_packet(frame: bytes) -> FeetechStatusPacket:
    packet = decode_packet(frame)
    return FeetechStatusPacket(
        servo_id=packet.servo_id,
        length=packet.length,
        error=packet.instruction,
        parameters=packet.parameters,
        checksum=packet.checksum,
        raw_frame=packet.raw_frame,
    )


def split_packet_stream(buffer: bytes) -> list[bytes]:
    frames: list[bytes] = []
    index = 0
    while index < len(buffer):
        if index + 4 > len(buffer):
            raise FeetechProtocolError("truncated_packet_stream")
        if buffer[index : index + 2] != HEADER:
            raise FeetechProtocolError(f"unexpected_stream_byte:0x{buffer[index]:02X}")
        length = buffer[index + 3]
        end = index + length + 4
        if end > len(buffer):
            raise FeetechProtocolError("truncated_packet_stream")
        frames.append(bytes(buffer[index:end]))
        index = end
    return frames


def format_frame_hex(frame: bytes) -> str:
    return " ".join(f"{byte:02X}" for byte in frame)


def ping_packet(servo_id: int) -> bytes:
    return encode_instruction_packet(servo_id, FeetechInstruction.PING)


def read_packet(servo_id: int, address: int, length: int) -> bytes:
    return encode_instruction_packet(servo_id, FeetechInstruction.READ, bytes((address & 0xFF, length & 0xFF)))


def write_packet(servo_id: int, address: int, payload: bytes | Sequence[int]) -> bytes:
    return encode_instruction_packet(servo_id, FeetechInstruction.WRITE, bytes((address & 0xFF,)) + bytes(payload))


def sync_write_packet(address: int, data_length: int, writes: Sequence[tuple[int, bytes]]) -> bytes:
    parameters = bytearray((address & 0xFF, data_length & 0xFF))
    for servo_id, payload in writes:
        if len(payload) != data_length:
            raise FeetechProtocolError(f"sync_write_payload_length_mismatch:id={servo_id}:expected={data_length}:actual={len(payload)}")
        parameters.append(normalize_servo_id(servo_id))
        parameters.extend(payload)
    return encode_instruction_packet(BROADCAST_ID, FeetechInstruction.SYNC_WRITE, parameters)


def sync_read_packet(address: int, data_length: int, servo_ids: Sequence[int]) -> bytes:
    parameters = bytearray((address & 0xFF, data_length & 0xFF))
    for servo_id in servo_ids:
        parameters.append(normalize_servo_id(servo_id))
    return encode_instruction_packet(BROADCAST_ID, FeetechInstruction.SYNC_READ, parameters)


def recovery_packet(servo_id: int) -> bytes:
    return encode_instruction_packet(servo_id, FeetechInstruction.RECOVERY)


def reset_packet(servo_id: int) -> bytes:
    return encode_instruction_packet(servo_id, FeetechInstruction.RESET)


def build_target_position_payload(position: int, duration_ms: int = 0, speed: int = 0) -> bytes:
    return pack_u16_le(position) + pack_u16_le(duration_ms) + pack_u16_le(speed)


__all__ = [
    "ADDRESS_PRESENT_ASYNC_FLAG",
    "ADDRESS_PRESENT_CURRENT",
    "ADDRESS_PRESENT_LOAD",
    "ADDRESS_PRESENT_MOVING",
    "ADDRESS_PRESENT_POSITION",
    "ADDRESS_PRESENT_SPEED",
    "ADDRESS_PRESENT_STATUS",
    "ADDRESS_PRESENT_TEMPERATURE",
    "ADDRESS_PRESENT_VOLTAGE",
    "ADDRESS_RUNNING_SPEED",
    "ADDRESS_START_ACCELERATION",
    "ADDRESS_TARGET_POSITION",
    "ADDRESS_TORQUE_SWITCH",
    "BROADCAST_ID",
    "FeetechInstruction",
    "FeetechPacket",
    "FeetechProtocolError",
    "FeetechStatusPacket",
    "build_target_position_payload",
    "checksum",
    "decode_packet",
    "decode_status_packet",
    "encode_instruction_packet",
    "encode_status_packet",
    "format_frame_hex",
    "normalize_servo_id",
    "pack_u8",
    "pack_u16_le",
    "ping_packet",
    "read_packet",
    "recovery_packet",
    "reset_packet",
    "split_packet_stream",
    "sync_read_packet",
    "sync_write_packet",
    "unpack_u16_le",
    "write_packet",
]
