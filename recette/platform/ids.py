"""Deterministic event-id generation (I4).

Event ids must be unique and ordered but never derived from wall clock or
random inside the decision path. The lab generator derives ULID-shaped ids
from a monotonic sequence so a replayed stream produces identical ids.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

# Crockford base32 alphabet used by ULID.
_B32 = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def _b32(value: int, width: int) -> str:
    out = []
    for _ in range(width):
        out.append(_B32[value & 0x1F])
        value >>= 5
    return "".join(reversed(out))


@runtime_checkable
class EventIdGenerator(Protocol):
    def next_id(self) -> str: ...


class SequenceIdGenerator:
    """ULID-shaped ids from a counter: 26 chars, lexicographically ordered.

    The 48-bit "timestamp" part is a fixed epoch plus the sequence, the 80-bit
    "random" part is the sequence again -- fully deterministic, replay-stable.
    """

    def __init__(self, *, epoch_ms: int = 1_700_000_000_000) -> None:
        self._epoch_ms = epoch_ms
        self._seq = 0

    def next_id(self) -> str:
        self._seq += 1
        time_part = _b32(self._epoch_ms + self._seq, 10)  # 48 bits -> 10 chars
        rand_part = _b32(self._seq, 16)  # 80 bits -> 16 chars
        return time_part + rand_part
