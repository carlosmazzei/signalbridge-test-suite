def calculate_checksum(data):
    """Calculate checksum by XORing all bytes in the data"""
    checksum = 0
    for byte in data:
        checksum ^= byte
    return checksum
