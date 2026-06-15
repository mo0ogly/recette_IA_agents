"""Ghost-agent probe: a REAL second egress that bypasses the governed proxy.

This is a red-team bench probe, NOT a production path. It models an unregistered
"ghost" agent that writes straight to a target (the shadow-db honeypot) WITHOUT
going through the ``ExternalSystemProxy`` -- the deliberate I2/I5 violation the
red-team bench must detect. When driven through the wire overlay, mitmproxy
records one ``WireFlow`` to the sink that no ``ProxyTrace`` explains, so
``reconcile_run`` flags it (the ghost-direct-db scenario, step 2 + 4).

The request is built (pure, testable) separately from being sent (real I/O):
``build_probe_request`` is asserted in the unittest suite; ``direct_write``
performs the live egress only in the smoke (R14).
"""

from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request

DEFAULT_RUN_HEADER = "x-inspect-run-id"


def build_probe_request(
    sink_url: str,
    payload: dict,
    *,
    run_id: str | None = None,
    run_header: str = DEFAULT_RUN_HEADER,
) -> urllib.request.Request:
    """Build the ghost's direct-write request (no proxy mediation).

    Carries ``run_id`` in the wire run header so the recorded ``WireFlow`` is
    attributable to the run; the body is a JSON write payload. Pure: no network,
    deterministic -- the unittest asserts the method, target and header.
    """
    # Fail-safe: the ghost egress targets an http(s) sink only. Reject file:/
    # custom schemes so a misconfigured sink_url cannot turn the probe into a
    # local-file or arbitrary-scheme write (clears S310: scheme is validated).
    scheme = urllib.parse.urlsplit(sink_url).scheme
    if scheme not in ("http", "https"):
        raise ValueError(f"ghost probe sink_url must be http(s), got scheme {scheme!r}")
    body = json.dumps(payload, sort_keys=True).encode("utf-8")
    req = urllib.request.Request(sink_url, data=body, method="POST")  # noqa: S310 (scheme validated above)
    req.add_header("Content-Type", "application/json")
    if run_id:
        req.add_header(run_header, run_id)
    return req


def direct_write(
    sink_url: str,
    payload: dict,
    *,
    proxy_url: str | None = None,
    run_id: str | None = None,
    run_header: str = DEFAULT_RUN_HEADER,
    timeout: float = 10.0,
) -> int:
    """Perform the live direct egress to ``sink_url`` and return the status code.

    When ``proxy_url`` is set, the egress goes through the wire overlay so the
    flow is intercepted and recorded -- this is how the bench observes the
    unmediated path. A connection/HTTP error returns its code (or 0) rather than
    raising: the probe must not crash the smoke, the DETECTION is the assertion.
    """
    handlers: list[urllib.request.BaseHandler] = []
    if proxy_url:
        handlers.append(urllib.request.ProxyHandler({"http": proxy_url, "https": proxy_url}))
    opener = urllib.request.build_opener(*handlers)
    req = build_probe_request(sink_url, payload, run_id=run_id, run_header=run_header)
    try:
        with opener.open(req, timeout=timeout) as resp:  # noqa: S310  # nosec B310 - bench probe
            return int(resp.status)
    except urllib.error.HTTPError as exc:
        return int(exc.code)
    except OSError:
        return 0
