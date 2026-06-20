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
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException

from ...surface.recording import score_recording
from ..probe_relay import ProbeUnavailable, relay_capture

router = APIRouter(prefix="/probe", tags=["probe"])

_SOCKET_ENV = "INSPECT_IA_AGENTS_PROBE_SOCKET"
_MODE_ENV = "INSPECT_IA_AGENTS_PROBE_MODE"
_MAX_DURATION_ENV = "INSPECT_IA_AGENTS_PROBE_MAX_DURATION_MS"
_DEFAULT_MAX_DURATION_MS = 30_000


def _canonical_socket() -> Path:
    """The launcher's canonical broker socket: ``<repo_root>/.run/probe.sock``.

    Mirrors ``PROBE_SOCKET_PATH`` in ``cicd/lib/common.sh`` (``${RUN_DIR}/probe.sock``).
    repo_root is this file's grandparent's-parent: recette/api/routers/probe.py.
    """
    return Path(__file__).resolve().parent.parent.parent.parent / ".run" / "probe.sock"


def _canonical_mode(default: str) -> str:
    """Mode of the launcher's canonical broker, read from ``.run/probe.mode``.

    The launcher writes ``live`` there when it started the privileged CAP_BPF
    broker on the canonical socket, ``replay`` for the non-privileged one. Read
    it so ``/probe/status`` tells the truth (R13/R14: never claim live for a
    replay broker, never hide a real live one). Falls back to ``default`` when
    the file is absent/unreadable (a hand-started broker without the marker)."""
    mode_file = _canonical_socket().with_name("probe.mode")
    try:
        value = mode_file.read_text(encoding="utf-8").strip()
    except OSError:
        return default
    return value if value in ("live", "replay") else default


def _resolve_socket() -> tuple[str | None, str]:
    """Resolve the broker socket and its mode (config-first, R5/R18).

    1. ``INSPECT_IA_AGENTS_PROBE_SOCKET`` env wins (mode from ``..._PROBE_MODE``,
       default ``live`` -- an operator-set socket targets the privileged broker).
    2. Fallback: the launcher's canonical ``.run/probe.sock`` IF it exists as a
       socket. This closes the friction where a standalone ``api restart`` (e.g.
       from a concurrent session) drops the env while the auto-started broker is
       still up -- the probe stays usable instead of going dark. Its mode comes
       from ``.run/probe.mode`` (the launcher records live vs replay there), so a
       launcher-started LIVE broker on the canonical socket reports ``live`` while
       the default replay broker reports ``replay`` (R13/R14).
    3. Otherwise: no socket -> ``(None, "off")``.
    """
    env_socket = os.environ.get(_SOCKET_ENV)
    if env_socket:
        return env_socket, os.environ.get(_MODE_ENV, "live")
    canonical = _canonical_socket()
    if canonical.is_socket():
        return str(canonical), _canonical_mode(os.environ.get(_MODE_ENV, "replay"))
    return None, "off"


def _max_duration_ms() -> int:
    """The API-side friendly cap (the broker manifest is the real bound). Config
    first (R5): overridable via env, never a magic literal in the request path."""
    raw = os.environ.get(_MAX_DURATION_ENV)
    if raw is None:
        return _DEFAULT_MAX_DURATION_MS
    try:
        value = int(raw)
    except ValueError:
        return _DEFAULT_MAX_DURATION_MS
    return value if value > 0 else _DEFAULT_MAX_DURATION_MS


@router.get("/status")
def status() -> dict:
    """Whether the probe broker socket is configured (for the console to enable
    the capture button). Does not connect -- reachability is proven by a capture.

    ``mode`` is ``replay`` when a non-privileged replay broker is wired (dev/CI,
    deterministic replay of corpus surface ground-truth) and ``live`` when the
    privileged eBPF broker is expected (CAP_BPF). It is surfaced so the console
    never presents a replay as a live capture (R13/R14). Config-first (R5).

    Resolves the env socket first, then the launcher's canonical ``.run/probe.sock``
    fallback, so a probe stays usable when a standalone ``api restart`` dropped the
    env but the auto-started broker is still up."""
    socket_path, mode = _resolve_socket()
    return {
        "configured": socket_path is not None,
        "socket_env": _SOCKET_ENV,
        "mode": mode,
    }


@router.post("/capture")
def capture(body: dict[str, Any]) -> dict:
    """Relay one bounded capture to the broker and score the recording.

    Body: ``{"agents": [ids], "duration_ms": <int>}``. Validation here mirrors
    the broker (deny-by-default lives in the broker; this is the friendly 400):
    a non-empty agent list of strings, a positive bounded duration.
    """
    socket_path, _ = _resolve_socket()
    if not socket_path:
        raise HTTPException(
            status_code=503,
            detail=f"{_SOCKET_ENV} not set and no broker socket at .run/probe.sock",
        )

    agents = body.get("agents")
    if not isinstance(agents, list) or not agents or not all(isinstance(a, str) for a in agents):
        raise HTTPException(status_code=400, detail="agents must be a non-empty list of ids")
    duration_ms = body.get("duration_ms", 3000)
    if not isinstance(duration_ms, int) or isinstance(duration_ms, bool) or duration_ms <= 0:
        raise HTTPException(status_code=400, detail="duration_ms must be a positive integer")
    ceiling = _max_duration_ms()
    if duration_ms > ceiling:
        raise HTTPException(
            status_code=400,
            detail=f"duration_ms exceeds the API ceiling {ceiling}",
        )

    try:
        recording = relay_capture(socket_path=socket_path, agents=agents, duration_ms=duration_ms)
    except ProbeUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    out: dict = {"recording": recording}
    if recording.get("status") == "ok":
        out["scorecard"] = asdict(score_recording(json.dumps(recording)))
    return out
