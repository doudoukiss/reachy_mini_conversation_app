from __future__ import annotations

from pathlib import Path

import pytest

from embodied_stack.body.serial import (
    DryRunServoTransport,
    FixtureReplayServoTransport,
    LiveSerialServoTransport,
    ServoTransportError,
    build_target_position_payload,
)


class TimeoutSerialConnection:
    port = "/dev/null"
    baudrate = 115200
    timeout = 0.01

    def write(self, payload: bytes) -> int:
        return len(payload)

    def read(self, size: int) -> bytes:
        return b""

    def close(self) -> None:
        return None

    def reset_input_buffer(self) -> None:
        return None

    def reset_output_buffer(self) -> None:
        return None


class InvalidReplySerialConnection(TimeoutSerialConnection):
    def __init__(self) -> None:
        self._replies = [bytes.fromhex("FF FF 01 02 00 00")]

    def read(self, size: int) -> bytes:
        if not self._replies:
            return b""
        payload = self._replies[0][:size]
        self._replies[0] = self._replies[0][size:]
        if not self._replies[0]:
            self._replies.pop(0)
        return payload


def test_dry_run_transport_roundtrips_ping_sync_write_and_sync_read() -> None:
    transport = DryRunServoTransport(
        baud_rate=115200,
        timeout_seconds=0.2,
        known_ids=[1, 2],
        neutral_positions={1: 2047, 2: 2047},
    )

    assert transport.ping(1).servo_id == 1
    assert transport.read_position(1) == 2047

    payload = build_target_position_payload(position=2100, duration_ms=180, speed=120)
    transport.sync_write(0x2A, [(1, payload), (2, payload)], data_length=6)
    positions = transport.sync_read(0x38, 2, [1, 2])

    assert int.from_bytes(positions[1], "little") == 2100
    assert int.from_bytes(positions[2], "little") == 2100
    assert transport.status.healthy is True
    assert transport.status.reason_code == "ok"
    assert transport.status.last_good_reply is not None


def test_dry_run_transport_roundtrips_start_acceleration_register() -> None:
    transport = DryRunServoTransport(
        baud_rate=115200,
        timeout_seconds=0.2,
        known_ids=[1, 2],
        neutral_positions={1: 2047, 2: 2047},
    )

    transport.sync_write_start_acceleration([(1, 40), (2, 40)])

    assert transport.read_start_acceleration(1) == 40
    assert transport.sync_read_start_acceleration([1, 2]) == {1: 40, 2: 40}


def test_fixture_replay_transport_uses_recorded_transactions() -> None:
    fixture_path = Path("src/embodied_stack/body/fixtures/robot_head_serial_fixture.json")
    transport = FixtureReplayServoTransport(
        fixture_path=fixture_path,
        baud_rate=115200,
        timeout_seconds=0.2,
    )

    assert transport.ping(1).servo_id == 1
    assert transport.read_position(1) == 2047


def test_fixture_replay_transport_falls_back_to_dry_run_for_unmatched_requests() -> None:
    fixture_path = Path("src/embodied_stack/body/fixtures/robot_head_serial_fixture.json")
    transport = FixtureReplayServoTransport(
        fixture_path=fixture_path,
        baud_rate=115200,
        timeout_seconds=0.2,
        known_ids=[1, 2, 3],
        neutral_positions={1: 2047, 2: 2047, 3: 2047},
    )

    assert transport.ping(1).servo_id == 1
    assert transport.ping(2).servo_id == 2
    assert transport.read_position(1) == 2047


def test_dry_run_transport_reports_no_device() -> None:
    transport = DryRunServoTransport(
        baud_rate=115200,
        timeout_seconds=0.2,
        known_ids=[1],
        neutral_positions={1: 2047},
    )

    with pytest.raises(ServoTransportError) as exc_info:
        transport.ping(2)

    assert exc_info.value.classification == "no_device"


def test_live_transport_reports_timeout() -> None:
    transport = LiveSerialServoTransport(
        port="/dev/tty.fake",
        baud_rate=115200,
        timeout_seconds=0.01,
        connection_factory=TimeoutSerialConnection,
    )

    with pytest.raises(ServoTransportError) as exc_info:
        transport.ping(1)

    assert exc_info.value.classification == "timeout"


def test_live_transport_rejects_invalid_reply() -> None:
    transport = LiveSerialServoTransport(
        port="/dev/tty.fake",
        baud_rate=115200,
        timeout_seconds=0.01,
        connection_factory=InvalidReplySerialConnection,
    )

    with pytest.raises(ServoTransportError) as exc_info:
        transport.ping(1)

    assert exc_info.value.classification == "invalid_reply"
