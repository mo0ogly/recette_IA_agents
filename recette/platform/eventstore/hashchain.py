"""Canonical serialization and hash chain for the event log (I1 integrity)."""

from __future__ import annotations

import hashlib
import json

GENESIS_HASH = "0" * 64


def canonical_json(payload: dict) -> str:
    """Deterministic JSON: sorted keys, no whitespace, no NaN (I4)."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)


def chain_hash(prev_hash: str, payload: dict) -> str:
    """sha256 over prev_hash + canonical payload."""
    data = prev_hash + canonical_json(payload)
    return hashlib.sha256(data.encode("utf-8")).hexdigest()
