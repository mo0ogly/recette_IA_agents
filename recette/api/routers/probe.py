"""POST /probe/capture -- relay a bounded eBPF capture to the broker, score it.

NON-privileged (design sec. 7). The route relays a `capture` command to the
discoveryprobe broker over its local Unix socket
(``INSPECT_IA_AGENTS_PROBE_SOCKET``), returns the broker recording, and -- when
the capture succeeded -- the ``DetectionScorecard`` from the same source-agnostic
judge (``recette/surface``). The console Probe view consumes this. The API holds
no privilege; the broker holds CAP_BPF.

Fail-safe: no socket configured or broker unreachable -> 503, never a fabricated
capture.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict
from typing import Any

from fastapi import APIRouter, HTTPException

from ...surface.recording import score_recording
from ..probe_relay import ProbeUnavailable, relay_capture

router = APIRouter(prefix="/probe", tags=["probe"])

_SOCKET_ENV = "INSPECT_IA_AGENTS_PROBE_SOCKET"
_MAX_DURATION_MS = 30_000


@router.get("/status")
def status() -> dict:
    """Whether the probe broker socket is configured (for the console to enable
    the capture button). Does not connect -- reachability is proven by a capture."""
    return {
        "configured": bool(os.environ.get(_SOCKET_ENV)),
        "socket_env": _SOCKET_ENV,
    }


@router.post("/capture")
def capture(body: dict[str, Any]) -> dict:
    """Relay one bounded capture to the broker and score the recording.

    Body: ``{"agents": [ids], "duration_ms": <int>}``. Validation here mirrors
    the broker (deny-by-default lives in the broker; this is the friendly 400):
    a non-empty agent list of strings, a positive bounded duration.
    """
    socket_path = os.environ.get(_SOCKET_ENV)
    if not socket_path:
        raise HTTPException(
            status_code=503,
            detail=f"{_SOCKET_ENV} not set (probe broker not launched)",
        )

    agents = body.get("agents")
    if not isinstance(agents, list) or not agents or not all(isinstance(a, str) for a in agents):
        raise HTTPException(status_code=400, detail="agents must be a non-empty list of ids")
    duration_ms = body.get("duration_ms", 3000)
    if not isinstance(duration_ms, int) or isinstance(duration_ms, bool) or duration_ms <= 0:
        raise HTTPException(status_code=400, detail="duration_ms must be a positive integer")
    if duration_ms > _MAX_DURATION_MS:
        raise HTTPException(
            status_code=400,
            detail=f"duration_ms exceeds the API ceiling {_MAX_DURATION_MS}",
        )

    try:
        recording = relay_capture(socket_path=socket_path, agents=agents, duration_ms=duration_ms)
    except ProbeUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    out: dict = {"recording": recording}
    if recording.get("status") == "ok":
        out["scorecard"] = asdict(score_recording(json.dumps(recording)))
    return out
