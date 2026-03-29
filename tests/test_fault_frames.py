"""
Unit tests for fault_frames module.

All tests are pure (no serial hardware, no mocks needed).
"""

from __future__ import annotations

import cobs.cobs as cobs_lib
import pytest

import fault_frames as ff

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _decode(frame: bytes) -> bytes:
    """COBS-decode a frame (strip trailing 0x00 delimiter first)."""
    assert frame[-1] == 0x00, "frame must end with 0x00 delimiter"
    return cobs_lib.decode(frame[:-1])


def _xor(data: bytes) -> int:
    result = 0
    for b in data:
        result ^= b
    return result


# ---------------------------------------------------------------------------
# TestCobsFrameHelper (internal _cobs_frame behaviour via public functions)
# ---------------------------------------------------------------------------


class TestCobsFrameHelper:
    def test_valid_cobs_frame_has_no_zero_before_delimiter(self) -> None:
        frame = ff.too_short()  # any frame built with _cobs_frame
        assert b"\x00" not in frame[:-1]

    def test_valid_cobs_frame_ends_with_zero(self) -> None:
        frame = ff.too_short()
        assert frame[-1] == 0x00

    def test_cobs_frame_decodes_correctly(self) -> None:
        # The decoded payload of too_short() should be [0xAA, 0xBB, checksum]
        decoded = _decode(ff.too_short())
        body = bytes([0xAA, 0xBB])
        expected_checksum = _xor(body)
        assert decoded == body + bytes([expected_checksum])


# ---------------------------------------------------------------------------
# TestEmptyFrame
# ---------------------------------------------------------------------------


class TestEmptyFrame:
    def test_returns_bytes(self) -> None:
        assert isinstance(ff.empty_frame(), bytes)

    def test_is_canonical_cobs_empty(self) -> None:
        # COBS encoding of empty bytes is b'\x01'; plus delimiter = b'\x01\x00'
        assert ff.empty_frame() == b"\x01\x00"

    def test_cobs_decode_gives_empty(self) -> None:
        assert cobs_lib.decode(ff.empty_frame()[:-1]) == b""

    def test_ends_with_delimiter(self) -> None:
        assert ff.empty_frame()[-1] == 0x00


# ---------------------------------------------------------------------------
# TestTooShort
# ---------------------------------------------------------------------------


class TestTooShort:
    def test_ends_with_delimiter(self) -> None:
        assert ff.too_short()[-1] == 0x00

    def test_decoded_size_less_than_4(self) -> None:
        decoded = _decode(ff.too_short())
        # body(2) + checksum(1) = 3 bytes, which is < MIN_DECODED_SIZE(4)
        assert len(decoded) < 4

    def test_no_zero_bytes_before_delimiter(self) -> None:
        frame = ff.too_short()
        assert b"\x00" not in frame[:-1]


# ---------------------------------------------------------------------------
# TestSizeMismatch
# ---------------------------------------------------------------------------


class TestSizeMismatch:
    def test_ends_with_delimiter(self) -> None:
        assert ff.size_mismatch()[-1] == 0x00

    def test_decoded_size_at_least_4(self) -> None:
        # Must pass the minimum-size check to reach the size-consistency check
        decoded = _decode(ff.size_mismatch())
        assert len(decoded) >= 4

    def test_decoded_size_ne_len_field_plus_4(self) -> None:
        decoded = _decode(ff.size_mismatch())
        len_field = decoded[2]
        # decoded_size ≠ len_field + HEADER_SIZE(3) + CHECKSUM_SIZE(1)
        assert len(decoded) != len_field + 4

    def test_rxid_passes(self) -> None:
        # rxID must be 1 so the frame reaches the size-consistency check
        decoded = _decode(ff.size_mismatch())
        assert (decoded[1] >> 5) == 1


# ---------------------------------------------------------------------------
# TestUnknownId
# ---------------------------------------------------------------------------


class TestUnknownId:
    def test_ends_with_delimiter(self) -> None:
        assert ff.unknown_id()[-1] == 0x00

    def test_decoded_size_is_4(self) -> None:
        decoded = _decode(ff.unknown_id())
        assert len(decoded) == 4  # header(3) + checksum(1)

    def test_size_consistency_passes(self) -> None:
        decoded = _decode(ff.unknown_id())
        len_field = decoded[2]
        assert len(decoded) == len_field + 4

    def test_len_field_le_20(self) -> None:
        decoded = _decode(ff.unknown_id())
        assert decoded[2] <= 20

    def test_rxid_is_not_1(self) -> None:
        decoded = _decode(ff.unknown_id())
        assert (decoded[1] >> 5) != 1


# ---------------------------------------------------------------------------
# TestBadChecksum
# ---------------------------------------------------------------------------


class TestBadChecksum:
    def test_ends_with_delimiter(self) -> None:
        assert ff.bad_checksum()[-1] == 0x00

    def test_decoded_size_at_least_4(self) -> None:
        decoded = _decode(ff.bad_checksum())
        assert len(decoded) >= 4

    def test_xor_of_all_decoded_bytes_nonzero(self) -> None:
        # A valid frame has XOR of all decoded bytes == 0.
        # A corrupted checksum makes the XOR non-zero.
        decoded = _decode(ff.bad_checksum())
        assert _xor(decoded) != 0

    def test_rxid_is_1(self) -> None:
        decoded = _decode(ff.bad_checksum())
        assert (decoded[1] >> 5) == 1


# ---------------------------------------------------------------------------
# TestPayloadOverflow
# ---------------------------------------------------------------------------


class TestPayloadOverflow:
    def test_ends_with_delimiter(self) -> None:
        assert ff.payload_overflow()[-1] == 0x00

    def test_len_field_greater_than_20(self) -> None:
        decoded = _decode(ff.payload_overflow())
        len_field = decoded[2]
        assert len_field > 20

    def test_decoded_size_at_least_4(self) -> None:
        decoded = _decode(ff.payload_overflow())
        assert len(decoded) >= 4


# ---------------------------------------------------------------------------
# TestSingleOverflow
# ---------------------------------------------------------------------------


class TestSingleOverflow:
    def test_len_is_26(self) -> None:
        assert len(ff.single_overflow()) == 26

    def test_no_zero_bytes(self) -> None:
        assert b"\x00" not in ff.single_overflow()

    def test_all_bytes_nonzero(self) -> None:
        assert all(b != 0 for b in ff.single_overflow())


# ---------------------------------------------------------------------------
# TestDoubleOverflowEmpty
# ---------------------------------------------------------------------------


class TestDoubleOverflowEmpty:
    def test_len_is_53(self) -> None:
        assert len(ff.double_overflow_empty()) == 53

    def test_ends_with_zero_delimiter(self) -> None:
        assert ff.double_overflow_empty()[-1] == 0x00

    def test_first_52_bytes_nonzero(self) -> None:
        assert all(b != 0 for b in ff.double_overflow_empty()[:52])


# ---------------------------------------------------------------------------
# TestAllRecipes
# ---------------------------------------------------------------------------

_EXPECTED_NAMES = {
    "empty_frame",
    "too_short",
    "size_mismatch",
    "unknown_id",
    "bad_checksum",
    "payload_overflow",
    "single_overflow",
    "double_overflow_empty",
}


class TestAllRecipes:
    def test_dict_has_8_entries(self) -> None:
        assert len(ff.ALL_RECIPES) == 8

    def test_all_values_are_bytes(self) -> None:
        for name, frame in ff.ALL_RECIPES.items():
            assert isinstance(frame, bytes), f"{name!r} is not bytes"

    def test_all_expected_names_present(self) -> None:
        assert set(ff.ALL_RECIPES.keys()) == _EXPECTED_NAMES

    @pytest.mark.parametrize("name", sorted(_EXPECTED_NAMES))
    def test_each_recipe_matches_function(self, name: str) -> None:
        fn = getattr(ff, name)
        assert ff.ALL_RECIPES[name] == fn()
