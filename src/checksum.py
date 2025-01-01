"""Checksum calculation functions."""


def calculate_checksum(data: bytes) -> bytes:
    """Calculate checksum by XORing all bytes in the data."""
    checksum = 0
    for byte in data:
        checksum ^= byte
    return bytes([checksum])
