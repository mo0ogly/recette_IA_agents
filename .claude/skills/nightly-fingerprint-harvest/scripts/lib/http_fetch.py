"""Live HTTP(S) fetch helper for hostname-only collectors.

Certificate-transparency sources (crt.sh) yield candidate hostnames but no
payload. The orchestrator calls fetch_host() to capture a real HTTP response
(status, headers, body) so the rule's probes can actually be scored. Without
this step a hostname-only source produces zero-value captures (empty body ->
match_score always 0).

stdlib only (urllib). Never raises -- returns a FetchResult with .error set on
failure so the nightly run never aborts on a single unreachable host.

TLS verification is intentionally relaxed: fingerprinted appliances and small
self-hosted products routinely present self-signed certificates. Verifying the
chain would drop exactly the targets this harvest exists to capture. This is a
read-only recon GET to a candidate host, not a trust decision.
"""

from __future__ import annotations

import gzip
import http.client
import socket
import ssl
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Optional

DEFAULT_TIMEOUT = 8
MAX_BODY_BYTES = 256 * 1024  # cap captured body at 256 KiB
USER_AGENT = "LIA-SEC liaprobe-harvest/1.0"


@dataclass
class FetchResult:
    url: str
    status: int = 0
    headers: dict = field(default_factory=dict)
    body: bytes = b""
    error: Optional[str] = None
    latency_ms: int = 0


def _maybe_gunzip(raw: bytes, headers: dict) -> bytes:
    enc = (headers.get("Content-Encoding") or "").lower()
    if "gzip" in enc:
        try:
            return gzip.decompress(raw)
        except Exception:
            return raw
    return raw


def _get(url: str, timeout: int, ctx: Optional[ssl.SSLContext]) -> FetchResult:
    started = time.monotonic()
    req = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept": "*/*",
        "Accept-Encoding": "gzip, identity",
        "Connection": "close",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            status = resp.status
            headers = {k: v for k, v in resp.headers.items()}
            raw = resp.read(MAX_BODY_BYTES + 1)
    except urllib.error.HTTPError as exc:
        # An HTTP error code still carries a real status + body = useful evidence.
        try:
            headers = {k: v for k, v in exc.headers.items()} if exc.headers else {}
            raw = exc.read(MAX_BODY_BYTES + 1)
        except Exception:
            headers, raw = {}, b""
        body = _maybe_gunzip(raw, headers)[:MAX_BODY_BYTES]
        return FetchResult(url=url, status=exc.code, headers=headers, body=body,
                           latency_ms=int((time.monotonic() - started) * 1000))
    except (urllib.error.URLError, ssl.SSLError, socket.timeout, OSError,
            ValueError, http.client.HTTPException) as exc:
        # http.client.HTTPException (incl. BadStatusLine) fires when the probed
        # port speaks a non-HTTP protocol -- e.g. an FTP host answering
        # "220 Welcome to ... FTP". Without it the exception escapes fetch_host
        # (which promises "Never raises") and kills the whole nightly harvest.
        # Incident 2026-06-01: a single Check Point FTP host aborted the run
        # (nightly_run exit=1) after 87 captures.
        return FetchResult(url=url, error=str(exc),
                           latency_ms=int((time.monotonic() - started) * 1000))
    body = _maybe_gunzip(raw, headers)[:MAX_BODY_BYTES]
    return FetchResult(url=url, status=status, headers=headers, body=body,
                       latency_ms=int((time.monotonic() - started) * 1000))


def _netloc(host: str, scheme: str, port: int) -> str:
    default = 443 if scheme == "https" else 80
    return host if port == default else f"{host}:{port}"


def fetch_host(host: str, port: int = 443, timeout: int = DEFAULT_TIMEOUT) -> FetchResult:
    """Fetch host over HTTPS first, fall back to HTTP. Returns the first
    response that carries a real status code. Never raises."""
    if not host:
        return FetchResult(url="", error="empty host")

    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    if port in (0, 443):
        attempts = [("https", 443), ("http", 80)]
    elif port == 80:
        attempts = [("http", 80), ("https", 443)]
    else:
        attempts = [("https", port), ("http", port), ("http", 80)]

    last = FetchResult(url=host, error="no scheme attempted")
    for scheme, p in attempts:
        url = f"{scheme}://{_netloc(host, scheme, p)}/"
        res = _get(url, timeout, ctx if scheme == "https" else None)
        if res.status:
            return res
        last = res
    return last
