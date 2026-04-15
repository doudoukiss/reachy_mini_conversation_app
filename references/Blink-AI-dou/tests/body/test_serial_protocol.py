from __future__ import annotations

from embodied_stack.body.serial import (
    FeetechInstruction,
    build_target_position_payload,
    decode_status_packet,
    ping_packet,
    read_packet,
    split_packet_stream,
    sync_read_packet,
    sync_write_packet,
)


def test_ping_and_read_packets_match_vendor_examples() -> None:
    assert ping_packet(1).hex(" ").upper() == "FF FF 01 02 01 FB"
    assert read_packet(1, 0x38, 0x02).hex(" ").upper() == "FF FF 01 04 02 38 02 BE"


def test_target_position_payload_is_low_byte_first() -> None:
    payload = build_target_position_payload(position=2048, duration_ms=0, speed=1000)
    assert payload.hex(" ").upper() == "00 08 00 00 E8 03"


def test_sync_write_encoding_matches_vendor_example() -> None:
    payload = build_target_position_payload(position=2048, duration_ms=0, speed=1000)
    packet = sync_write_packet(
        0x2A,
        0x06,
        [
            (1, payload),
            (2, payload),
            (3, payload),
            (4, payload),
        ],
    )
    assert (
        packet.hex(" ").upper()
        == "FF FF FE 20 83 2A 06 01 00 08 00 00 E8 03 02 00 08 00 00 E8 03 03 00 08 00 00 E8 03 04 00 08 00 00 E8 03 58"
    )


def test_sync_read_packet_and_reply_decoding() -> None:
    request = sync_read_packet(0x38, 0x08, [1, 2])
    assert request.hex(" ").upper() == "FF FF FE 06 82 38 08 01 02 36"

    stream = bytes.fromhex(
        "FF FF 01 0A 00 00 08 00 00 00 00 79 1E 55 "
        "FF FF 02 0A 00 FF 07 00 00 00 00 77 23 53"
    )
    frames = split_packet_stream(stream)
    decoded = [decode_status_packet(frame) for frame in frames]

    assert [packet.servo_id for packet in decoded] == [1, 2]
    assert decoded[0].error == 0
    assert decoded[0].parameters[:2].hex(" ").upper() == "00 08"
    assert decoded[1].parameters[:2].hex(" ").upper() == "FF 07"


def test_instruction_enum_values_are_stable() -> None:
    assert FeetechInstruction.PING == 0x01
    assert FeetechInstruction.READ == 0x02
    assert FeetechInstruction.WRITE == 0x03
    assert FeetechInstruction.SYNC_READ == 0x82
    assert FeetechInstruction.SYNC_WRITE == 0x83
