"""Property-based tests for protocol framing and checksum behavior."""

from __future__ import annotations

import queue
from unittest.mock import Mock

import pytest
from cobs import cobs
from hypothesis import given
from hypothesis import strategies as st

from checksum import calculate_checksum
from serial_interface import SerialInterface


@given(st.binary())
def test_checksum_matches_bitwise_xor_property(data: bytes) -> None:
    """Checksum must equal XOR reduction of all bytes."""
    expected = 0
    for byte in data:
        expected ^= byte

    assert calculate_checksum(data) == bytes([expected])


@given(st.binary(), st.binary())
def test_checksum_xor_composition_property(left: bytes, right: bytes) -> None:
    """checksum(A + B) equals checksum(A) XOR checksum(B)."""
    chk_left = calculate_checksum(left)[0]
    chk_right = calculate_checksum(right)[0]
    chk_concat = calculate_checksum(left + right)[0]

    assert chk_concat == (chk_left ^ chk_right)


@given(st.binary(min_size=2, max_size=512))
def test_write_frame_roundtrip_property(payload: bytes) -> None:
    """write() must emit COBS(message+checksum)+delimiter for valid payloads."""
    si = SerialInterface("COM1", 115200, 0.1)
    si.ser = Mock()
    si.ser.write.return_value = 0

    si.write(payload)

    si.ser.write.assert_called_once()
    (framed,), _ = si.ser.write.call_args

    assert framed.endswith(b"\x00")
    decoded = cobs.decode(framed[:-1])
    assert decoded == payload + calculate_checksum(payload)


@given(st.binary(min_size=1, max_size=256))
def test_handle_received_data_reassembles_split_frames_property(decoded: bytes) -> None:
    """Split serial reads must reconstruct queued COBS frames correctly."""
    si = SerialInterface("COM1", 115200, 0.1)
    si.ser = Mock()

    encoded = cobs.encode(decoded)
    wire_data = encoded + b"\x00"

    # Feed one byte at a time to model worst-case UART fragmentation.
    for byte in wire_data:
        si._handle_received_data(bytes([byte]), max_message_size=1024)

    queued = si.message_queue.get(timeout=0.5)
    assert queued == encoded


@given(st.binary(max_size=128), st.binary(max_size=128))
def test_handle_received_data_ignores_empty_frames_property(
    first_decoded: bytes,
    second_decoded: bytes,
) -> None:
    """Consecutive delimiters should not queue empty packets."""
    si = SerialInterface("COM1", 115200, 0.1)
    si.ser = Mock()

    first = cobs.encode(first_decoded)
    second = cobs.encode(second_decoded)

    si._handle_received_data(
        first + b"\x00\x00" + second + b"\x00",
        max_message_size=1024,
    )

    assert si.message_queue.get(timeout=0.5) == first
    assert si.message_queue.get(timeout=0.5) == second
    with pytest.raises(queue.Empty):
        # Queue should now be empty: the extra delimiter must not create a packet.
        si.message_queue.get(timeout=0.01)
