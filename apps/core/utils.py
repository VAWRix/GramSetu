"""
Core utility functions for GramSetu platform.
"""

import os
import time
import uuid


def generate_uuid7() -> uuid.UUID:
    """
    Generate an RFC 9562-compliant UUIDv7 in pure Python 3.11 without external dependencies.
    
    Structure (128 bits):
    - 48 bits: Unix timestamp in milliseconds
    - 4 bits: Version 7 (0b0111)
    - 12 bits: Cryptographic pseudo-random bits
    - 2 bits: Variant 10 (0b10)
    - 62 bits: Cryptographic pseudo-random bits
    """
    timestamp_ms = time.time_ns() // 1_000_000
    rand_bytes = os.urandom(10)

    time_bytes = timestamp_ms.to_bytes(6, byteorder='big')
    b6 = 0x70 | (rand_bytes[0] & 0x0F)
    b7 = rand_bytes[1]
    b8 = 0x80 | (rand_bytes[2] & 0x3F)
    b9_15 = rand_bytes[3:]

    raw_bytes = time_bytes + bytes([b6, b7, b8]) + b9_15
    return uuid.UUID(bytes=raw_bytes)
