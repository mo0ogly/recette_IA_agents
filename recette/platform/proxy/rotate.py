"""Append-on-rotate sink for the bounded debug rings. A retained copy of the
entry the ring is about to evict, so a long run keeps its early packets. Debug
convenience only -- the append-only audit log remains the durable truth (I1).
"""

from __future__ import annotations

import json
import os
from pathlib import Path

ROTATE_DIR_ENV = "INSPECT_IA_AGENTS_PROXY_ROTATE_DIR"


def rotate_dir_from_env() -> Path | None:
    """The rotate directory from the environment, or None when unset (R5).

    Unset/empty => no rotate sink: the rings stay purely in-memory and an
    evicted entry is simply dropped (the previous behaviour).
    """
    raw = os.environ.get(ROTATE_DIR_ENV, "").strip()
    return Path(raw) if raw else None


def append_jsonl(path: Path, obj: dict) -> None:
    """Append one JSONL line, fail-safe (never raises -- persistence must not
    break the debug path)."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(obj) + "\n")
    except Exception:  # noqa: BLE001 - fail-safe
        pass
