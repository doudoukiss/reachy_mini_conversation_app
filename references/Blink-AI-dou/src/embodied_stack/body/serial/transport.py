from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Protocol, Sequence

from embodied_stack.config import Settings
from embodied_stack.shared.contracts.body import HeadProfile

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
    ADDRESS_RUNNING_SPEED,
    ADDRESS_TARGET_POSITION,
    ADDRESS_START_ACCELERATION,
    ADDRESS_TORQUE_SWITCH,
    BROADCAST_ID,
    FeetechInstruction,
    FeetechProtocolError,
    FeetechStatusPacket,
    build_target_position_payload,
    decode_packet,
    decode_status_packet,
    format_frame_hex,
    pack_u8,
    pack_u16_le,
    ping_packet,
    read_packet,
    recovery_packet,
    reset_packet,
    split_packet_stream,
    sync_read_packet,
    sync_write_packet,
    unpack_u16_le,
    write_packet,
)

DEFAULT_TRANSPORT_MODE = "dry_run"
FIXTURE_REPLAY_MODE = "fixture_replay"
LIVE_SERIAL_MODE = "live_serial"
STANDARD_TRANSPORT_REASON_CODES = {
    "missing_port",
    "port_busy",
    "baud_mismatch",
    "id_conflict",
    "timeout",
    "servo_status_error",
    "invalid_reply",
    "transport_unconfirmed",
    "serial_unavailable",
}
DEFAULT_FIXTURE_REPLAY_PATH = str(
    Path(__file__).resolve().parent.parent / "fixtures" / "robot_head_serial_fixture.json"
)


class SerialConnectionProtocol(Protocol):
    port: str
    baudrate: int
    timeout: float

    def write(self, payload: bytes) -> int: ...

    def read(self, size: int) -> bytes: ...

    def close(self) -> None: ...

    def reset_input_buffer(self) -> None: ...

    def reset_output_buffer(self) -> None: ...


class ServoTransportError(RuntimeError):
    def __init__(self, classification: str, detail: str) -> None:
        self.classification = classification
        self.detail = detail
        super().__init__(detail)


@dataclass
class ServoTransportStatus:
    mode: str
    port: str | None = None
    baud_rate: int = 1000000
    timeout_seconds: float = 0.2
    healthy: bool = False
    confirmed_live: bool = False
    reason_code: str = "transport_unconfirmed"
    last_error: str | None = None
    last_operation: str | None = None
    last_good_reply: str | None = None
    transaction_count: int = 0


@dataclass
class ServoTransactionRecord:
    operation: str
    request_hex: str
    response_hex: list[str] = field(default_factory=list)
    ok: bool = True
    reason_code: str | None = None
    error: str | None = None


@dataclass
class SerialPortRecord:
    device: str
    name: str | None = None
    description: str | None = None
    manufacturer: str | None = None
    serial_number: str | None = None
    location: str | None = None
    vid: int | None = None
    pid: int | None = None
    hwid: str | None = None
    recommended: bool = False
    kind: str = "other"

    def to_dict(self) -> dict[str, object]:
        return {
            "device": self.device,
            "name": self.name,
            "description": self.description,
            "manufacturer": self.manufacturer,
            "serial_number": self.serial_number,
            "location": self.location,
            "vid": self.vid,
            "pid": self.pid,
            "hwid": self.hwid,
            "recommended": self.recommended,
            "kind": self.kind,
        }


@dataclass
class FixtureTransaction:
    request_hex: str
    response_hex: list[str] = field(default_factory=list)
    note: str | None = None


def normalize_transport_reason_code(classification: str | None, detail: str | None = None) -> str:
    normalized = (classification or "").strip().lower()
    detail_text = (detail or "").strip().lower()
    if normalized in STANDARD_TRANSPORT_REASON_CODES:
        return normalized
    if "reply_id_mismatch" in detail_text:
        return "id_conflict"
    if "baud" in detail_text:
        return "baud_mismatch"
    if "busy" in detail_text or "in use" in detail_text or "permission denied" in detail_text:
        return "port_busy"
    if "no such file" in detail_text or "not found" in detail_text:
        return "missing_port"
    if normalized in {"no_device", "transport_unhealthy", "transport_unavailable", "open_failed", "fixture_missing"}:
        return "transport_unconfirmed"
    if normalized in {"write_failed", "read_failed"}:
        return "serial_unavailable"
    return "invalid_reply" if normalized else "transport_unconfirmed"


def serialize_transaction_history(records: Sequence[ServoTransactionRecord]) -> list[dict[str, object]]:
    return [
        {
            "operation": record.operation,
            "request_hex": record.request_hex,
            "response_hex": list(record.response_hex),
            "ok": record.ok,
            "reason_code": record.reason_code,
            "error": record.error,
        }
        for record in records
    ]


def list_serial_ports() -> list[SerialPortRecord]:
    try:
        from serial.tools import list_ports  # type: ignore
    except ModuleNotFoundError:
        return []

    ports: list[SerialPortRecord] = []
    for port in list_ports.comports():
        device = str(getattr(port, "device", "") or "")
        looks_like_system_port = (
            device.endswith("Bluetooth-Incoming-Port")
            or "debug-console" in device
            or (device.startswith("/dev/cu.") and getattr(port, "vid", None) is None and getattr(port, "pid", None) is None and str(getattr(port, "hwid", "") or "").lower() == "n/a")
        )
        recommended = device.startswith("/dev/cu.") and not looks_like_system_port
        if recommended:
            kind = "recommended"
        elif device.startswith("/dev/cu."):
            kind = "system"
        elif device.startswith("/dev/tty."):
            kind = "alternate"
        else:
            kind = "other"
        ports.append(
            SerialPortRecord(
                device=device,
                name=getattr(port, "name", None),
                description=getattr(port, "description", None),
                manufacturer=getattr(port, "manufacturer", None),
                serial_number=getattr(port, "serial_number", None),
                location=getattr(port, "location", None),
                vid=getattr(port, "vid", None),
                pid=getattr(port, "pid", None),
                hwid=getattr(port, "hwid", None),
                recommended=recommended,
                kind=kind,
            )
        )
    return sorted(ports, key=lambda item: (not item.recommended, item.device))


def classify_open_failure(exc: Exception) -> tuple[str, str]:
    detail = str(exc)
    detail_text = detail.lower()
    if isinstance(exc, FileNotFoundError) or "no such file" in detail_text or "not found" in detail_text:
        return "missing_port", detail
    if "busy" in detail_text or "resource busy" in detail_text or "permission denied" in detail_text or "in use" in detail_text:
        return "port_busy", detail
    return "serial_unavailable", detail


class BaseServoTransport:
    def __init__(
        self,
        *,
        mode: str,
        baud_rate: int,
        timeout_seconds: float,
        port: str | None = None,
    ) -> None:
        self.status = ServoTransportStatus(
            mode=mode,
            port=port,
            baud_rate=baud_rate,
            timeout_seconds=timeout_seconds,
            healthy=mode != LIVE_SERIAL_MODE,
            confirmed_live=mode != LIVE_SERIAL_MODE,
            reason_code="ok" if mode != LIVE_SERIAL_MODE else "transport_unconfirmed",
        )
        self.history: list[ServoTransactionRecord] = []

    def close(self) -> None:
        return None

    def history_payload(self) -> list[dict[str, object]]:
        return serialize_transaction_history(self.history)

    def ping(self, servo_id: int) -> FeetechStatusPacket:
        return self._single_reply("ping", ping_packet(servo_id), expected_response_ids=[servo_id])

    def read(self, servo_id: int, address: int, length: int) -> bytes:
        reply = self._single_reply("read", read_packet(servo_id, address, length), expected_response_ids=[servo_id])
        if len(reply.parameters) != length:
            raise ServoTransportError(
                "invalid_reply",
                f"read_length_mismatch:id={servo_id}:expected={length}:actual={len(reply.parameters)}",
            )
        return reply.parameters

    def write(self, servo_id: int, address: int, payload: bytes, *, expect_reply: bool = True) -> FeetechStatusPacket | None:
        responses = self._exchange(
            "write",
            write_packet(servo_id, address, payload),
            expected_response_ids=[servo_id] if expect_reply and servo_id != BROADCAST_ID else [],
        )
        return responses[0] if responses else None

    def sync_write(self, address: int, writes: Sequence[tuple[int, bytes]], *, data_length: int) -> None:
        self._exchange(
            "sync_write",
            sync_write_packet(address, data_length, writes),
            expected_response_ids=[],
        )

    def sync_read(self, address: int, length: int, servo_ids: Sequence[int]) -> dict[int, bytes]:
        packets = self.sync_read_status(address, length, servo_ids)
        return {servo_id: packet.parameters for servo_id, packet in packets.items()}

    def sync_read_status(self, address: int, length: int, servo_ids: Sequence[int]) -> dict[int, FeetechStatusPacket]:
        responses = self._exchange(
            "sync_read",
            sync_read_packet(address, length, servo_ids),
            expected_response_ids=list(servo_ids),
        )
        return {packet.servo_id: packet for packet in responses}

    def recovery(self, servo_id: int) -> FeetechStatusPacket | None:
        responses = self._exchange("recovery", recovery_packet(servo_id), expected_response_ids=[servo_id] if servo_id != BROADCAST_ID else [])
        return responses[0] if responses else None

    def reset_state(self, servo_id: int) -> FeetechStatusPacket | None:
        responses = self._exchange("reset_state", reset_packet(servo_id), expected_response_ids=[servo_id] if servo_id != BROADCAST_ID else [])
        return responses[0] if responses else None

    def set_torque(self, servo_ids: Sequence[int], *, enabled: bool) -> None:
        payloads = [(servo_id, bytes((1 if enabled else 0,))) for servo_id in servo_ids]
        self.sync_write(ADDRESS_TORQUE_SWITCH, payloads, data_length=1)

    def read_position(self, servo_id: int) -> int:
        return unpack_u16_le(self.read(servo_id, ADDRESS_PRESENT_POSITION, 2))

    def read_start_acceleration(self, servo_id: int) -> int:
        return self.read(servo_id, ADDRESS_START_ACCELERATION, 1)[0]

    def read_running_speed_register(self, servo_id: int) -> int:
        return unpack_u16_le(self.read(servo_id, ADDRESS_RUNNING_SPEED, 2))

    def write_target_position(
        self,
        servo_id: int,
        *,
        position: int,
        duration_ms: int,
        speed: int,
        expect_reply: bool = True,
    ) -> FeetechStatusPacket | None:
        return self.write(
            servo_id,
            ADDRESS_TARGET_POSITION,
            build_target_position_payload(position, duration_ms=duration_ms, speed=speed),
            expect_reply=expect_reply,
        )

    def write_start_acceleration(
        self,
        servo_id: int,
        *,
        acceleration: int,
        expect_reply: bool = True,
    ) -> FeetechStatusPacket | None:
        return self.write(
            servo_id,
            ADDRESS_START_ACCELERATION,
            pack_u8(acceleration),
            expect_reply=expect_reply,
        )

    def sync_write_start_acceleration(self, payloads: Sequence[tuple[int, int]]) -> None:
        writes = [(servo_id, pack_u8(acceleration)) for servo_id, acceleration in payloads]
        self.sync_write(ADDRESS_START_ACCELERATION, writes, data_length=1)

    def sync_read_start_acceleration(self, servo_ids: Sequence[int]) -> dict[int, int]:
        payload = self.sync_read(ADDRESS_START_ACCELERATION, 1, servo_ids)
        return {servo_id: values[0] for servo_id, values in payload.items()}

    def sync_read_running_speed_register(self, servo_ids: Sequence[int]) -> dict[int, int]:
        payload = self.sync_read(ADDRESS_RUNNING_SPEED, 2, servo_ids)
        return {servo_id: unpack_u16_le(values) for servo_id, values in payload.items()}

    def confirm_live(self, servo_ids: Sequence[int]) -> list[int]:
        found: list[int] = []
        for servo_id in servo_ids:
            try:
                self.ping(servo_id)
            except ServoTransportError:
                continue
            found.append(servo_id)
            if self.status.mode == LIVE_SERIAL_MODE:
                self.status.confirmed_live = True
                self.status.healthy = True
                self.status.reason_code = "ok"
                self.status.last_error = None
            break
        if self.status.mode == LIVE_SERIAL_MODE and not found:
            self.status.confirmed_live = False
            self.status.healthy = False
            self.status.reason_code = "transport_unconfirmed"
            if self.status.last_error is None:
                self.status.last_error = "transport_unconfirmed:no_device_reply"
        return found

    def _single_reply(self, operation: str, request_frame: bytes, *, expected_response_ids: Sequence[int]) -> FeetechStatusPacket:
        responses = self._exchange(operation, request_frame, expected_response_ids=expected_response_ids)
        return responses[0]

    def _exchange(self, operation: str, request_frame: bytes, *, expected_response_ids: Sequence[int]) -> list[FeetechStatusPacket]:
        record = ServoTransactionRecord(operation=operation, request_hex=format_frame_hex(request_frame))
        try:
            response_frames = self._exchange_frames(request_frame, expected_response_ids=expected_response_ids)
            responses = [decode_status_packet(frame) for frame in response_frames]
            if expected_response_ids:
                actual_ids = [packet.servo_id for packet in responses]
                if actual_ids != list(expected_response_ids):
                    raise ServoTransportError(
                        "invalid_reply",
                        f"reply_id_mismatch:expected={list(expected_response_ids)}:actual={actual_ids}",
                    )
            record.response_hex = [format_frame_hex(frame) for frame in response_frames]
            record.reason_code = "ok"
            self._mark_success()
            self.status.last_operation = operation
            self.status.last_good_reply = record.response_hex[-1] if record.response_hex else None
            return responses
        except (FeetechProtocolError, ServoTransportError) as exc:
            detail = exc.detail if isinstance(exc, ServoTransportError) else str(exc)
            classification = exc.classification if isinstance(exc, ServoTransportError) else "invalid_reply"
            record.ok = False
            record.reason_code = normalize_transport_reason_code(classification, detail)
            record.error = detail
            self._mark_failure(classification, detail)
            self.status.last_operation = operation
            raise exc if isinstance(exc, ServoTransportError) else ServoTransportError(classification, detail)
        finally:
            self.status.transaction_count += 1
            self.history.append(record)

    def _mark_failure(self, classification: str, detail: str) -> None:
        self.status.healthy = False
        if self.status.mode == LIVE_SERIAL_MODE:
            self.status.confirmed_live = False
        self.status.reason_code = normalize_transport_reason_code(classification, detail)
        self.status.last_error = f"{classification}:{detail}"

    def _mark_success(self) -> None:
        self.status.healthy = True
        if self.status.mode != LIVE_SERIAL_MODE:
            self.status.confirmed_live = True
        self.status.reason_code = "ok"
        self.status.last_error = None

    def _exchange_frames(self, request_frame: bytes, *, expected_response_ids: Sequence[int]) -> list[bytes]:
        raise NotImplementedError


class DryRunServoTransport(BaseServoTransport):
    def __init__(
        self,
        *,
        baud_rate: int,
        timeout_seconds: float,
        known_ids: Sequence[int],
        neutral_positions: dict[int, int],
    ) -> None:
        super().__init__(mode=DEFAULT_TRANSPORT_MODE, baud_rate=baud_rate, timeout_seconds=timeout_seconds)
        self._registers: dict[int, bytearray] = {}
        self._known_ids = set(int(value) for value in known_ids)
        for servo_id in self._known_ids:
            self._registers[servo_id] = bytearray(256)
            neutral = int(neutral_positions.get(servo_id, 2047))
            self._write_registers(servo_id, ADDRESS_START_ACCELERATION, bytes((0,)))
            self._write_registers(servo_id, ADDRESS_TARGET_POSITION, build_target_position_payload(neutral, duration_ms=0, speed=0))
            self._write_registers(servo_id, ADDRESS_PRESENT_POSITION, pack_u16_le(neutral))
            self._write_registers(servo_id, ADDRESS_PRESENT_SPEED, pack_u16_le(0))
            self._write_registers(servo_id, ADDRESS_PRESENT_LOAD, pack_u16_le(0))
            self._write_registers(servo_id, ADDRESS_PRESENT_VOLTAGE, bytes((120,)))
            self._write_registers(servo_id, ADDRESS_PRESENT_TEMPERATURE, bytes((25,)))
            self._write_registers(servo_id, ADDRESS_PRESENT_ASYNC_FLAG, bytes((0,)))
            self._write_registers(servo_id, ADDRESS_PRESENT_STATUS, bytes((0,)))
            self._write_registers(servo_id, ADDRESS_PRESENT_MOVING, bytes((0,)))
            self._write_registers(servo_id, ADDRESS_PRESENT_CURRENT, pack_u16_le(0))
            self._write_registers(servo_id, ADDRESS_TORQUE_SWITCH, bytes((1,)))

    def _exchange_frames(self, request_frame: bytes, *, expected_response_ids: Sequence[int]) -> list[bytes]:
        packet = decode_packet(request_frame)
        if packet.instruction == FeetechInstruction.PING:
            servo_ids = self._resolve_target_ids(packet.servo_id, expected_response_ids)
            return [self._status_frame(servo_id) for servo_id in servo_ids]
        if packet.instruction == FeetechInstruction.READ:
            self._require_known_id(packet.servo_id)
            if len(packet.parameters) != 2:
                raise ServoTransportError("invalid_request", f"read_requires_two_parameters:{len(packet.parameters)}")
            address, length = packet.parameters
            payload = bytes(self._registers[packet.servo_id][address : address + length])
            return [self._status_frame(packet.servo_id, payload)]
        if packet.instruction == FeetechInstruction.WRITE:
            self._apply_write(packet.servo_id, packet.parameters)
            return [] if packet.servo_id == BROADCAST_ID else [self._status_frame(packet.servo_id)]
        if packet.instruction == FeetechInstruction.SYNC_WRITE:
            self._apply_sync_write(packet.parameters)
            return []
        if packet.instruction == FeetechInstruction.SYNC_READ:
            address = packet.parameters[0]
            length = packet.parameters[1]
            servo_ids = list(packet.parameters[2:])
            return [self._status_frame(servo_id, bytes(self._registers[servo_id][address : address + length])) for servo_id in servo_ids]
        if packet.instruction in {FeetechInstruction.RECOVERY, FeetechInstruction.RESET}:
            self._require_known_id(packet.servo_id)
            return [self._status_frame(packet.servo_id)]
        raise ServoTransportError("unsupported_instruction", f"unsupported_instruction:0x{packet.instruction:02X}")

    def _resolve_target_ids(self, servo_id: int, expected_response_ids: Sequence[int]) -> list[int]:
        if servo_id == BROADCAST_ID:
            resolved = list(expected_response_ids or sorted(self._known_ids))
        else:
            self._require_known_id(servo_id)
            resolved = [servo_id]
        for target_id in resolved:
            self._require_known_id(target_id)
        return resolved

    def _apply_write(self, servo_id: int, parameters: bytes) -> None:
        if not parameters:
            raise ServoTransportError("invalid_request", "write_requires_address")
        address = parameters[0]
        payload = bytes(parameters[1:])
        targets = sorted(self._known_ids) if servo_id == BROADCAST_ID else [servo_id]
        for target_id in targets:
            self._require_known_id(target_id)
            self._write_registers(target_id, address, payload)

    def _apply_sync_write(self, parameters: bytes) -> None:
        if len(parameters) < 2:
            raise ServoTransportError("invalid_request", "sync_write_requires_address_and_length")
        address = parameters[0]
        data_length = parameters[1]
        cursor = 2
        while cursor < len(parameters):
            servo_id = parameters[cursor]
            payload = bytes(parameters[cursor + 1 : cursor + 1 + data_length])
            if len(payload) != data_length:
                raise ServoTransportError("invalid_request", "sync_write_truncated_payload")
            self._require_known_id(servo_id)
            self._write_registers(servo_id, address, payload)
            cursor += data_length + 1

    def _write_registers(self, servo_id: int, address: int, payload: bytes) -> None:
        self._registers[servo_id][address : address + len(payload)] = payload
        if address == ADDRESS_TARGET_POSITION and len(payload) >= 2:
            self._registers[servo_id][ADDRESS_PRESENT_POSITION : ADDRESS_PRESENT_POSITION + 2] = payload[:2]

    def _require_known_id(self, servo_id: int) -> None:
        if servo_id not in self._known_ids:
            raise ServoTransportError("no_device", f"no_device:id={servo_id}")

    @staticmethod
    def _status_frame(servo_id: int, payload: bytes = b"") -> bytes:
        from .protocol import encode_status_packet

        return encode_status_packet(servo_id, error=0, parameters=payload)


class FixtureReplayServoTransport(BaseServoTransport):
    def __init__(
        self,
        *,
        fixture_path: str | Path,
        baud_rate: int,
        timeout_seconds: float,
        known_ids: Sequence[int] | None = None,
        neutral_positions: dict[int, int] | None = None,
    ) -> None:
        super().__init__(mode=FIXTURE_REPLAY_MODE, baud_rate=baud_rate, timeout_seconds=timeout_seconds, port=str(fixture_path))
        self.fixture_path = Path(fixture_path)
        if not self.fixture_path.exists():
            raise ServoTransportError("fixture_missing", f"fixture_missing:{self.fixture_path}")
        payload = json.loads(self.fixture_path.read_text(encoding="utf-8"))
        self._transactions = [
            FixtureTransaction(
                request_hex=item["request_hex"],
                response_hex=list(item.get("response_hex", [])),
                note=item.get("note"),
            )
            for item in payload.get("transactions", [])
        ]
        self._cursor = 0
        fallback_ids = list(known_ids or self._infer_known_ids())
        self._fallback_transport = DryRunServoTransport(
            baud_rate=baud_rate,
            timeout_seconds=timeout_seconds,
            known_ids=fallback_ids,
            neutral_positions=neutral_positions or {servo_id: 2047 for servo_id in fallback_ids},
        )

    def _exchange_frames(self, request_frame: bytes, *, expected_response_ids: Sequence[int]) -> list[bytes]:
        actual_request = format_frame_hex(request_frame)
        if self._cursor < len(self._transactions):
            transaction = self._transactions[self._cursor]
            expected_request = transaction.request_hex.strip().upper()
            if actual_request == expected_request:
                self._cursor += 1
                # Keep the deterministic fallback transport in sync for later replay gaps.
                self._fallback_transport._exchange_frames(request_frame, expected_response_ids=expected_response_ids)
                return [bytes.fromhex(item) for item in transaction.response_hex]
        return self._fallback_transport._exchange_frames(request_frame, expected_response_ids=expected_response_ids)

    def _infer_known_ids(self) -> list[int]:
        known_ids: set[int] = set()
        for transaction in self._transactions:
            request = bytes.fromhex(transaction.request_hex)
            try:
                packet = decode_packet(request)
            except FeetechProtocolError:
                continue
            if packet.servo_id != BROADCAST_ID:
                known_ids.add(packet.servo_id)
            if packet.instruction == FeetechInstruction.SYNC_READ and len(packet.parameters) >= 2:
                known_ids.update(int(servo_id) for servo_id in packet.parameters[2:])
            if packet.instruction == FeetechInstruction.SYNC_WRITE and len(packet.parameters) >= 2:
                data_length = packet.parameters[1]
                cursor = 2
                while cursor < len(packet.parameters):
                    known_ids.add(int(packet.parameters[cursor]))
                    cursor += data_length + 1
        return sorted(known_ids or {1})


class LiveSerialServoTransport(BaseServoTransport):
    def __init__(
        self,
        *,
        port: str,
        baud_rate: int,
        timeout_seconds: float,
        connection_factory: Callable[[], SerialConnectionProtocol] | None = None,
    ) -> None:
        super().__init__(mode=LIVE_SERIAL_MODE, port=port, baud_rate=baud_rate, timeout_seconds=timeout_seconds)
        self._connection_factory = connection_factory or self._default_connection_factory(port, baud_rate, timeout_seconds)
        self._connection: SerialConnectionProtocol | None = None

    def close(self) -> None:
        if self._connection is not None:
            self._connection.close()
            self._connection = None

    def _default_connection_factory(
        self,
        port: str,
        baud_rate: int,
        timeout_seconds: float,
    ) -> Callable[[], SerialConnectionProtocol]:
        try:
            import serial  # type: ignore
        except ModuleNotFoundError as exc:
            raise ServoTransportError("serial_unavailable", "pyserial_not_installed") from exc

        def factory() -> SerialConnectionProtocol:
            try:
                return serial.Serial(
                    port=port,
                    baudrate=baud_rate,
                    timeout=timeout_seconds,
                    write_timeout=timeout_seconds,
                )
            except Exception as exc:
                classification, detail = classify_open_failure(exc)
                raise ServoTransportError(classification, detail) from exc

        return factory

    def _exchange_frames(self, request_frame: bytes, *, expected_response_ids: Sequence[int]) -> list[bytes]:
        connection = self._ensure_connection()
        try:
            connection.reset_input_buffer()
            connection.reset_output_buffer()
        except Exception:
            pass
        try:
            connection.write(request_frame)
        except Exception as exc:
            raise ServoTransportError("write_failed", str(exc)) from exc
        if not expected_response_ids:
            self.status.confirmed_live = True
            return []
        frames: list[bytes] = []
        for _ in expected_response_ids:
            frames.append(self._read_frame(connection))
        self.status.confirmed_live = True
        return frames

    def _ensure_connection(self) -> SerialConnectionProtocol:
        if self._connection is None:
            self._connection = self._connection_factory()
        return self._connection

    def _read_frame(self, connection: SerialConnectionProtocol) -> bytes:
        prefix = self._read_exact(connection, 2)
        while prefix != b"\xFF\xFF":
            prefix = prefix[1:] + self._read_exact(connection, 1)
        header_tail = self._read_exact(connection, 2)
        servo_id = header_tail[0]
        length = header_tail[1]
        remainder = self._read_exact(connection, length)
        frame = b"\xFF\xFF" + bytes((servo_id, length)) + remainder
        decode_status_packet(frame)
        return frame

    def _read_exact(self, connection: SerialConnectionProtocol, size: int) -> bytes:
        chunks = bytearray()
        while len(chunks) < size:
            chunk = connection.read(size - len(chunks))
            if not chunk:
                raise ServoTransportError("timeout", f"serial_timeout:expected={size}:received={len(chunks)}")
            chunks.extend(chunk)
        return bytes(chunks)


def _profile_servo_ids(profile: HeadProfile) -> list[int]:
    ids: list[int] = []
    for joint in profile.joints:
        ids.extend(joint.servo_ids)
    return sorted({servo_id for servo_id in ids})


def _profile_neutral_positions(profile: HeadProfile) -> dict[int, int]:
    positions: dict[int, int] = {}
    for joint in profile.joints:
        for servo_id in joint.servo_ids:
            positions[servo_id] = joint.neutral
    return positions


def build_servo_transport(
    settings: Settings,
    profile: HeadProfile,
    *,
    connection_factory: Callable[[], SerialConnectionProtocol] | None = None,
) -> BaseServoTransport:
    mode = (settings.blink_serial_transport or DEFAULT_TRANSPORT_MODE).strip().lower()
    if mode == FIXTURE_REPLAY_MODE:
        fixture_path = settings.blink_serial_fixture or DEFAULT_FIXTURE_REPLAY_PATH
        if not fixture_path:
            raise ServoTransportError("fixture_missing", "fixture_replay_requires_BLINK_SERIAL_FIXTURE")
        return FixtureReplayServoTransport(
            fixture_path=fixture_path,
            baud_rate=settings.blink_servo_baud,
            timeout_seconds=settings.blink_serial_timeout_seconds,
            known_ids=_profile_servo_ids(profile),
            neutral_positions=_profile_neutral_positions(profile),
        )
    if mode == LIVE_SERIAL_MODE:
        if not settings.blink_serial_port:
            raise ServoTransportError("missing_port", "live_serial_requires_BLINK_SERIAL_PORT")
        return LiveSerialServoTransport(
            port=settings.blink_serial_port,
            baud_rate=settings.blink_servo_baud,
            timeout_seconds=settings.blink_serial_timeout_seconds,
            connection_factory=connection_factory,
        )
    return DryRunServoTransport(
        baud_rate=settings.blink_servo_baud,
        timeout_seconds=settings.blink_serial_timeout_seconds,
        known_ids=_profile_servo_ids(profile),
        neutral_positions=_profile_neutral_positions(profile),
    )


__all__ = [
    "DEFAULT_TRANSPORT_MODE",
    "DEFAULT_FIXTURE_REPLAY_PATH",
    "FIXTURE_REPLAY_MODE",
    "LIVE_SERIAL_MODE",
    "DryRunServoTransport",
    "FixtureReplayServoTransport",
    "LiveSerialServoTransport",
    "SerialPortRecord",
    "classify_open_failure",
    "list_serial_ports",
    "normalize_transport_reason_code",
    "serialize_transaction_history",
    "ServoTransactionRecord",
    "ServoTransportError",
    "ServoTransportStatus",
    "build_servo_transport",
]
