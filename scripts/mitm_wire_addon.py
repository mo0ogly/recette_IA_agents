"""mitmproxy addon: stream intercepted flows to the inspect_ia_agents API wire ring.

Loaded by the OPTIONAL mitmproxy Docker overlay (``mitmdump -s
scripts/mitm_wire_addon.py``). On each completed request/response it normalizes
the flow and POSTs it to ``{API_URL}/proxy/wire``, where ``WireFlowRecorder``
buffers it for the console. The overlay is observability only: it never alters
the traffic and a POST failure is swallowed (fail-safe -- interception must never
break the agent's call, failure-modes.md).

Zero hard dependency beyond mitmproxy itself: the POST uses stdlib urllib, and
``build_ingest_payload`` is a pure function (no mitmproxy import) so it is unit
testable without a live proxy.

Config (R5, no hardcoded address):
- INSPECT_IA_AGENTS_API_URL    -- base URL of the governed API (default http://host.docker.internal:8090)
- INSPECT_IA_AGENTS_WIRE_RUN_HEADER -- request header carrying the originating run id
                              (default x-inspect-run-id); forwarded to the ring.
"""

from __future__ import annotations

import json
import os
import urllib.request

DEFAULT_API_URL = "http://host.docker.internal:8090"
DEFAULT_RUN_HEADER = "x-inspect-run-id"
# Cap the body we forward; the server clamps again, but smaller POSTs keep the
# overlay light. A truncated body is enough to read the exchange.
MAX_BODY_CHARS = 16_384


def _api_url() -> str:
    return os.environ.get("INSPECT_IA_AGENTS_API_URL", DEFAULT_API_URL).rstrip("/")


def _run_header() -> str:
    return os.environ.get("INSPECT_IA_AGENTS_WIRE_RUN_HEADER", DEFAULT_RUN_HEADER).lower()


def _clip(text: str) -> str:
    return text if len(text) <= MAX_BODY_CHARS else text[:MAX_BODY_CHARS]


def build_ingest_payload(
    *,
    method: str,
    scheme: str,
    host: str,
    port: int,
    path: str,
    status_code: int,
    content_type: str,
    request_body: str,
    response_body: str,
    run_id: str | None,
    duration_ms: float | None = None,
) -> dict:
    """Normalize a flow's fields into the ``POST /proxy/wire`` ingest payload.

    Pure and total: the caller (the mitmproxy hook) extracts these fields from
    the flow object; keeping the mapping here makes it testable without the
    mitmproxy runtime. The server re-validates and re-clamps, so this is a
    convenience shape, not a trust boundary.
    """
    return {
        "method": method,
        "scheme": scheme,
        "host": host,
        "port": port,
        "path": path,
        "status_code": status_code,
        "content_type": content_type,
        "request_body": _clip(request_body),
        "response_body": _clip(response_body),
        "run_id": run_id,
        "duration_ms": duration_ms,
    }


def _post(payload: dict) -> None:
    """POST one flow to the API ingest, swallowing any failure (fail-safe)."""
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{_api_url()}/proxy/wire",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        # Target is an operator-configured API base URL, not user input.
        urllib.request.urlopen(req, timeout=5).close()  # noqa: S310  # nosec B310
    except Exception:  # noqa: BLE001 - interception must never break on a sink failure
        pass


class WireCapture:
    """mitmproxy addon: one ``response`` hook per completed exchange."""

    def response(self, flow: object) -> None:  # noqa: ANN001 - mitmproxy duck-types the flow
        req = getattr(flow, "request", None)
        resp = getattr(flow, "response", None)
        if req is None or resp is None:
            return
        run_header = _run_header()
        run_id = None
        try:
            headers = req.headers
            run_id = headers.get(run_header)
        except Exception:  # noqa: BLE001 - missing/odd headers must not crash the hook
            run_id = None
        # Round-trip latency from the flow timestamps: wall-clock OPS metadata on
        # the wire view only; it is NEVER an input to a judge/decision/replay
        # path (I4). None when mitmproxy did not record both ends.
        start = getattr(req, "timestamp_start", None)
        end = getattr(resp, "timestamp_end", None)
        duration_ms = (
            round((end - start) * 1000, 3)
            if isinstance(start, (int, float)) and isinstance(end, (int, float))
            else None
        )
        payload = build_ingest_payload(
            method=getattr(req, "method", ""),
            scheme=getattr(req, "scheme", ""),
            host=getattr(req, "host", ""),
            port=int(getattr(req, "port", 0) or 0),
            path=getattr(req, "path", ""),
            status_code=int(getattr(resp, "status_code", 0) or 0),
            content_type=_safe_content_type(resp),
            request_body=_safe_text(req),
            response_body=_safe_text(resp),
            run_id=run_id,
            duration_ms=duration_ms,
        )
        _post(payload)


def _safe_text(message: object) -> str:
    """Best-effort decoded body of a mitmproxy message (empty on any failure)."""
    getter = getattr(message, "get_text", None)
    if getter is None:
        return ""
    try:
        return getter(strict=False) or ""
    except Exception:  # noqa: BLE001 - a binary/undecodable body is not fatal
        return ""


def _safe_content_type(resp: object) -> str:
    try:
        return resp.headers.get("content-type", "")  # type: ignore[attr-defined]  # mitmproxy duck-types the response
    except Exception:  # noqa: BLE001
        return ""


# mitmproxy discovers addons through this module-level list.
addons = [WireCapture()]
