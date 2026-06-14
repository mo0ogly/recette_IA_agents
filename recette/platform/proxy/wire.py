"""Wire-level interception flows from the optional mitmproxy overlay.

The mitmproxy container (an OPTIONAL Docker overlay, off by default) intercepts
the real HTTP(S) traffic an agent emits towards target systems (the lab, or a
real forge). Its addon POSTs one normalized flow per request/response pair to
``POST /proxy/wire``; this module owns the server-side model and the bounded
buffer those flows land in.

Relationship to ``ProxyTrace`` (tracing.py): ``ProxyTrace`` is the APPLICATION
level view (the agent's intent at the ``ExternalSystemProxy`` boundary, I5).
``WireFlow`` is the NETWORK level view (the bytes actually on the wire). Both are
observability over the same side effect, at two altitudes -- the wire flow is the
"ce qu'il FAIT vraiment" level of legibility.

Determinism (I4): the wire overlay is OFF in every deterministic recette and
never sits in the decision/replay path. A ``WireFlow`` therefore carries no
wall-clock value; ordering comes from a monotone ``seq`` assigned by the
recorder, exactly like ``ProxyTrace``. The recorder + normalizer here are pure
and unit-testable without a live container.

Immutability (I1): the buffer is a bounded, jettable ring (the durable truth is
the append-only audit log). A ``clear`` discards the debug buffer, never the log.
"""

from __future__ import annotations

import os
import threading
from collections import deque
from dataclasses import asdict, dataclass

# The proxy URL an agent's HTTP client routes through when the wire overlay is
# active (R5: no hardcoded address). Unset/empty => wire OFF, the client talks to
# the target directly and the deterministic recette path is unchanged (I4).
WIRE_PROXY_ENV = "INSPECT_IA_AGENTS_WIRE_PROXY"

DEFAULT_RING_CAPACITY = 512
# Cap each captured body so a large response cannot blow up the in-memory ring.
# A wire flow is a debug view, not the audit truth: a truncated body is enough to
# read the exchange, and the marker makes the truncation explicit (never silent).
MAX_BODY_CHARS = 16_384
TRUNCATION_MARKER = "...[truncated]"


def wire_proxy_url_from_env() -> str | None:
    """The wire proxy URL from the environment, or None when the overlay is off."""
    raw = os.environ.get(WIRE_PROXY_ENV, "").strip()
    return raw or None


def _clamp_body(value: object) -> str:
    """Coerce a captured body to a bounded string. Non-string bodies are
    stringified (the addon already sends text); over-long bodies are truncated
    with an explicit marker so the console never shows a silently cut body."""
    text = value if isinstance(value, str) else "" if value is None else str(value)
    if len(text) > MAX_BODY_CHARS:
        return text[:MAX_BODY_CHARS] + TRUNCATION_MARKER
    return text


@dataclass(frozen=True)
class WireFlow:
    """One intercepted request/response pair at the network level.

    ``seq`` is assigned by the recorder (monotone, stable ordering). Everything
    else is normalized from the addon's ingest payload. ``ok`` is derived from
    the status code so the console can badge a flow without re-parsing it.
    """

    seq: int
    method: str
    scheme: str
    host: str
    port: int
    path: str
    status_code: int
    ok: bool
    content_type: str
    request_body: str
    response_body: str
    # Operational link to the originating run when the addon can attribute it
    # (forwarded by the client via a header). None when unattributed. Like
    # ProxyTrace.run_id this is run metadata on the view, never a canonical event
    # field and never on the audit log (I1).
    run_id: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def normalize_flow(payload: dict, seq: int) -> WireFlow:
    """Build a ``WireFlow`` from an addon ingest payload (pure, total).

    Defensive by construction: the payload crosses a process boundary (the
    mitmproxy container), so every field is coerced to its expected type with a
    safe default rather than trusted. ``seq`` is supplied by the recorder.

    Raises ``ValueError`` only on a non-dict payload (a malformed ingest body):
    the endpoint turns that into a 422, it never reaches the ring.
    """
    if not isinstance(payload, dict):
        raise ValueError("wire flow payload must be a JSON object")
    try:
        status_code = int(payload.get("status_code", 0))
    except (TypeError, ValueError):
        status_code = 0
    try:
        port = int(payload.get("port", 0))
    except (TypeError, ValueError):
        port = 0
    method = str(payload.get("method", "")).upper()
    run_id = payload.get("run_id")
    return WireFlow(
        seq=seq,
        method=method,
        scheme=str(payload.get("scheme", "")),
        host=str(payload.get("host", "")),
        port=port,
        path=str(payload.get("path", "")),
        status_code=status_code,
        # A flow with no response (status 0) or a >=400 status is a failure: the
        # badge must not show "ok" for an exchange that never completed.
        ok=0 < status_code < 400,
        content_type=str(payload.get("content_type", "")),
        request_body=_clamp_body(payload.get("request_body")),
        response_body=_clamp_body(payload.get("response_body")),
        run_id=str(run_id) if isinstance(run_id, str) and run_id else None,
    )


class WireFlowRecorder:
    """Bounded, thread-safe in-memory ring of the most recent wire flows.

    Mirrors ``RingTraceRecorder`` (tracing.py): ``capacity`` caps memory (oldest
    flows drop), ``seq`` is monotone across the recorder's life so ordering is
    stable even after the ring wraps. ``record`` never raises on a malformed
    payload it can normalize; ``normalize_flow`` only rejects a non-dict, which
    the endpoint screens first.
    """

    def __init__(self, capacity: int = DEFAULT_RING_CAPACITY) -> None:
        if capacity <= 0:
            raise ValueError("WireFlowRecorder capacity must be positive")
        self._ring: deque[WireFlow] = deque(maxlen=capacity)
        self._seq = 0
        self._lock = threading.Lock()

    def record(self, payload: dict) -> WireFlow:
        """Normalize and append one ingested flow; return the stored flow."""
        with self._lock:
            self._seq += 1
            flow = normalize_flow(payload, self._seq)
            self._ring.append(flow)
            return flow

    def snapshot(self) -> list[WireFlow]:
        with self._lock:
            return list(self._ring)

    def clear(self) -> None:
        with self._lock:
            self._ring.clear()
