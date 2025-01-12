"""Tests for the checksum module."""

from src.checksum import calculate_checksum


def test_empty_data() -> None:
    """Test that the checksum of an empty byte string is 0."""
    assert calculate_checksum(b"") == b"\x00"


def test_single_byte() -> None:
    """Test that the checksum of a single byte is the byte itself."""
    assert calculate_checksum(b"\x01") == b"\x01"


def test_multiple_bytes() -> None:
    """Test that the checksum is calculated correctly for multiple bytes."""
    assert calculate_checksum(b"\x01\x02\x03") == b"\x00"


def test_zero_bytes() -> None:
    """Test that the checksum is calculated correctly for zero bytes."""
    assert calculate_checksum(b"\x00\x00\x00") == b"\x00"


def test_all_ones() -> None:
    """Test that the checksum is calculated correctly for all ones."""
    assert calculate_checksum(b"\xff\xff\xff") == b"\xff"


def test_alternating_bits() -> None:
    """Test that the checksum is calculated correctly for alternating bits."""
    assert calculate_checksum(b"\xaa\x55") == b"\xff"


def test_typical_message() -> None:
    """Test that the checksum is calculated correctly for a typical message."""
    assert calculate_checksum(b"Hello World") == b"\x20"


def test_binary_data() -> None:
    """Test that the checksum is calculated correctly for binary data."""
    assert calculate_checksum(bytes([0x12, 0x34, 0x56, 0x78])) == b"\x08"
