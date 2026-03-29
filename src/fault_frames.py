"""
Deterministic malformed frame builders for fault-injection stress scenarios.

Each function returns a raw byte sequence that can be written directly to the
serial port (bypassing the normal COBS framing path).  The sequences are
designed to exercise specific error counters in the firmware validation
pipeline:

  Firmware validation pipeline order (stops at first failure):
  1. COBS decode fails              → cobs_decode_error
  2. decoded_size < 4               → msg_malformed_error
  3. decoded_size ≠ len_field + 4   → msg_malformed_error
  4. len_field > 20                 → buffer_overflow_error
  5. rxID ≠ 0x01                    → unknown_cmd_error
  6. XOR checksum mismatch          → checksum_error
  7. receive buffer accumulates 26+ non-zero bytes without 0x00
                                    → receive_buffer_overflow_error

Key firmware constants (from the C implementation):
  MAX_ENCODED_BUFFER_SIZE = 26  (overflow at index >= 25, i.e. 26th byte)
  HEADER_SIZE = 3               (rxID_high, rxID_low|cmd, len_field)
  CHECKSUM_SIZE = 1
  MIN_DECODED_SIZE = 4          (HEADER_SIZE + CHECKSUM_SIZE)
  MAX_PAYLOAD_LEN = 20          (len_field must be <= 20)
  VALID_RX_ID = 0x01            (upper 3 bits of byte[1])

Wire frame format:  COBS_ENCODE(body + XOR_checksum) + 0x00
Message body:       [rxID_high][rxID_low|cmd(5b)][len_field][payload...]
"""

from __future__ import annotations

import cobs.cobs as _cobs


def _cobs_frame(body: bytes) -> bytes:
    """COBS-encode body, append XOR checksum byte, and append 0x00 delimiter."""
    checksum = 0
    for b in body:
        checksum ^= b
    return _cobs.encode(body + bytes([checksum])) + b"\x00"


# ---------------------------------------------------------------------------
# Frame builders
# ---------------------------------------------------------------------------


def empty_frame() -> bytes:
    """Return a lone 0x00 delimiter — triggers cobs_decode_error (empty buffer)."""
    # COBS encoding of an empty byte string is b'\x01'; appending 0x00 gives
    # the canonical "empty COBS frame" that the firmware rejects at decode time.
    return _cobs.encode(b"") + b"\x00"


def too_short() -> bytes:
    """
    Return a 2-byte COBS payload — triggers msg_malformed_error.

    body = [0xAA, 0xBB] (2 bytes), checksum appended → 3 decoded bytes < 4
    (MIN_DECODED_SIZE).
    """
    return _cobs_frame(bytes([0xAA, 0xBB]))


def size_mismatch() -> bytes:
    """
    Return a frame where decoded_size ≠ len_field + 4 — triggers msg_malformed_error.

    len_field = 5 but only 3 payload bytes are present.
    decoded_size = HEADER(3) + payload(3) + checksum(1) = 7
    expected     = len_field + 4 = 5 + 4 = 9   →  7 ≠ 9.
    """
    header = bytes([0x00, 0x34, 5])  # rxID_high=0, byte1=0x34 (rxID=1,cmd=20), len=5
    payload = bytes([0xAA, 0xBB, 0xCC])  # only 3 bytes instead of 5
    return _cobs_frame(header + payload)


def unknown_id() -> bytes:
    """
    Return a structurally valid frame with rxID=2 — triggers unknown_cmd_error.

    byte[1] = 0x54 = 0b0101_0100 → top-3 bits = 0b010 = 2 (rxID),
                                     low-5 bits = 0b10100 = 20 (ECHO_COMMAND).
    len_field = 0, decoded_size = 4 = MIN_DECODED_SIZE, size-consistency ✓,
    len_field (0) ≤ 20 ✓, rxID (2) ≠ 1 → unknown_cmd_error.
    """
    return _cobs_frame(bytes([0x00, 0x54, 0x00]))


def bad_checksum() -> bytes:
    """
    Return a valid echo frame with the checksum byte bit-flipped.

    Triggers checksum_error.

    Passes COBS decode, minimum-size, size-consistency, payload-length, and
    rxID checks; fails the final XOR verification.
    """
    # Minimal valid echo header: rxID_high=0x00, byte1=0x34 (rxID=1,cmd=20), len=2
    # payload: two arbitrary bytes
    body = bytes([0x00, 0x34, 0x02, 0x11, 0x22])
    # Compute the correct checksum, then corrupt it
    correct_checksum = 0
    for b in body:
        correct_checksum ^= b
    bad_cs = correct_checksum ^ 0xFF  # flip all bits so XOR verify fails
    return _cobs.encode(body + bytes([bad_cs])) + b"\x00"


def payload_overflow() -> bytes:
    """Return a frame with len_field=21 — triggers buffer_overflow_error (len > 20)."""
    header = bytes([0x00, 0x34, 21])  # len_field = 21 > MAX_PAYLOAD_LEN(20)
    payload = bytes(21)  # 21 zero bytes (content irrelevant)
    return _cobs_frame(header + payload)


def single_overflow() -> bytes:
    """
    Return 26 non-zero bytes with no 0x00 — triggers receive_buffer_overflow_error once.

    The firmware accumulation buffer holds 25 useful bytes (index 0-24).
    The 26th non-zero byte triggers the overflow, resets the buffer, and
    increments receive_buffer_overflow_error.  No delimiter is included so
    no COBS decode is attempted.
    """
    return bytes([0x01] * 26)


def double_overflow_empty() -> bytes:
    """
    Return 52 non-zero bytes followed by 0x00.

    Triggers:
      receive_buffer_overflow_error += 2  (at byte 26 and byte 52)
      cobs_decode_error             += 1  (0x00 arrives on empty buffer)

    After the second overflow the buffer is empty.  The trailing 0x00
    delimiter triggers a COBS decode attempt on that empty buffer, which
    fails with cobs_decode_error.
    """
    return bytes([0x01] * 52) + b"\x00"


# ---------------------------------------------------------------------------
# Convenience mapping
# ---------------------------------------------------------------------------

ALL_RECIPES: dict[str, bytes] = {
    "empty_frame": empty_frame(),
    "too_short": too_short(),
    "size_mismatch": size_mismatch(),
    "unknown_id": unknown_id(),
    "bad_checksum": bad_checksum(),
    "payload_overflow": payload_overflow(),
    "single_overflow": single_overflow(),
    "double_overflow_empty": double_overflow_empty(),
}
