"""Shared primitives for realistic, deterministic lab domain doubles.

Every value a domain handler returns must be a pure function of its inputs
(action_type, resource, payload): no clock, no random, no cross-call state, so
replays are byte-identical (I4). These helpers are the determinism anchor and
the common validation/derivation toolkit shared by the domain modules.

A handler returns a dict for a simulated side effect, ``None`` for an unknown
action (HTTP 404), or raises ``LabActionError`` for a known action with invalid
input (HTTP 4xx). Validation is lenient on OMITTED fields (a deterministic value
is derived) and strict only on values that are present and wrong, so scenarios
that omit fields still succeed.
"""

from __future__ import annotations

import hashlib
import json

from ..errors import LabActionError

__all__ = [
    "LabActionError",
    "digest",
    "ref",
    "pick",
    "derived_int",
    "coerce_positive_number",
    "valid_email",
    "envelope",
]


def digest(domain: str, action_type: str, resource: str, payload: dict) -> str:
    """64-hex stable digest of the full input -- the determinism anchor (I4)."""
    material = f"{domain}:{action_type}:{resource}:{json.dumps(payload, sort_keys=True)}"
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def ref(prefix: str, dig: str, *, length: int = 10) -> str:
    """A realistic stable identifier: prefix + a slice of the input digest."""
    return f"{prefix}{dig[:length]}"


def pick(dig: str, choices: tuple[str, ...], *, offset: int = 0) -> str:
    """A deterministic choice from a tuple (stable per input)."""
    window = dig[offset : offset + 4] or dig[:4]
    return choices[int(window, 16) % len(choices)]


def derived_int(dig: str, lo: int, hi: int, *, offset: int = 0) -> int:
    """A stable integer in [lo, hi) derived from the digest (no counter/clock)."""
    window = dig[offset : offset + 8] or dig[:8]
    return lo + (int(window, 16) % (hi - lo))


def coerce_positive_number(raw: object) -> float | None:
    """A positive number, accepting a numeric string ("42", "42.5") as LLMs emit.
    Returns None for anything that is not a positive number (bool, placeholder
    text, non-positive value)."""
    if isinstance(raw, bool):
        return None
    if isinstance(raw, (int, float)):
        return float(raw) if raw > 0 else None
    if isinstance(raw, str):
        try:
            value = float(raw.replace(",", "").strip())
        except ValueError:
            return None
        return value if value > 0 else None
    return None


def valid_email(value: str) -> bool:
    """A pragmatic email check: one ``@``, a non-empty local part, and a domain
    with a dot. Enough to reject placeholders ("user_email") without an RFC."""
    if value.count("@") != 1:
        return False
    local, _, domain = value.partition("@")
    return bool(local) and "." in domain and not domain.startswith(".") and not domain.endswith(".")


def envelope(action_type: str, resource: str, dig: str) -> dict:
    """The base response envelope shared by every action (stable result_id)."""
    return {"action": action_type, "resource": resource, "result_id": dig[:12]}
