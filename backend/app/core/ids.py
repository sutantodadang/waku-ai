"""ID generation helpers."""
from __future__ import annotations

import os
import time
from uuid import UUID


def uuid7() -> str:
    """Generate a UUIDv7 (time-ordered) as a string. Stdlib only."""
    ms = int(time.time() * 1000)
    rand = os.urandom(10)
    b = bytearray(16)
    b[0] = (ms >> 40) & 0xFF
    b[1] = (ms >> 32) & 0xFF
    b[2] = (ms >> 24) & 0xFF
    b[3] = (ms >> 16) & 0xFF
    b[4] = (ms >> 8) & 0xFF
    b[5] = ms & 0xFF
    b[6] = 0x70 | (rand[0] & 0x0F)   # version 7
    b[7] = rand[1]
    b[8] = 0x80 | (rand[2] & 0x3F)   # variant (RFC 4122)
    b[9:16] = rand[3:10]
    return str(UUID(bytes=bytes(b)))
