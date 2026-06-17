"""Shared deterministic primitives for the lab entity model.

Every per-domain entity is a PURE function of its id (see the package docstring).
These helpers are the shared, stateless building blocks: a digest keyed only on
(kind, id) and deterministic pickers derived from it. No clock, no random, no
stored state -- the same inputs always yield the same output (I4).
"""

from __future__ import annotations

import hashlib


def _edigest(kind: str, entity_id: str) -> str:
    """64-hex digest keyed ONLY on (kind, id) -- the coherence anchor.

    Independent of action_type/payload so every action touching the same entity
    derives the identical view (I4)."""
    return hashlib.sha256(f"entity:{kind}:{entity_id}".encode()).hexdigest()


def _pick(dig: str, choices: tuple[str, ...], *, offset: int = 0) -> str:
    window = dig[offset : offset + 4] or dig[:4]
    return choices[int(window, 16) % len(choices)]


def _int(dig: str, lo: int, hi: int, *, offset: int = 0) -> int:
    window = dig[offset : offset + 8] or dig[:8]
    return lo + (int(window, 16) % (hi - lo))


def _money(cents: int) -> str:
    """Format an integer number of cents as a fixed 2-decimal string."""
    return f"{cents // 100}.{cents % 100:02d}"


def _masked_iban(dig: str) -> str:
    """A deterministic masked IBAN placeholder (never a real account)."""
    return f"DE**{'*' * 14}{dig[:4].upper()}"
