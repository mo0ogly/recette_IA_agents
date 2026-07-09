"""mitmproxy addon: stream intercepted flows to the inspect_ia_agents API wire buffer.

Loaded by the OPTIONAL mitmproxy Docker overlay (``mitmdump -s
scripts/mitm_wire_addon.py``). On each completed request/response it normalizes
the flow and POSTs it to ``{API_URL}/proxy/wire``, where the SQLite-backed
``SqliteWireRecorder`` buffers it for the console. The overlay is observability
only: it never alters the traffic and a POST failure is swallowed (fail-safe --
interception must never break the agent's call, failure-modes.md).

Beyond the HTTP application view (method/path/status/bodies), the addon also
decodes the LOWER network layers of each exchange -- what a "Wireshark for AI
agents" needs to be legible by layer, not just L7:

* L3/L4  -- real src/dst IP + ports from the sockets (client_conn / server_conn
  peername/sockname), transport, IP version.
* TLS    -- negotiated version, cipher, SNI, ALPN, the upstream certificate, and
  the client JA3 fingerprint (computed from the raw ClientHello) -- the exact
  signal a network agent-discovery probe fingerprints on.
* L7     -- full request/response headers (Authorization redacted), HTTP version,
  status reason.
* timing -- per-phase waterfall (TCP connect, TLS handshake, TTFB, total).

Every field is read via ``getattr`` with a safe default: a value that mitmproxy
does not expose for a given flow is emitted as ``null`` (honest absence), never
faked. The bodies stay the truncated L7 view; the new metadata rides in a nested
``layers`` object so the server model extends without breaking the flat contract.

Zero hard dependency beyond mitmproxy itself: the POST uses stdlib urllib, JA3 is
computed with hashlib, and ``build_ingest_payload`` is a pure function (no
mitmproxy import) so it is unit testable without a live proxy.

Config (R5, no hardcoded address):
- INSPECT_IA_AGENTS_API_URL    -- base URL of the governed API (default http://host.docker.internal:8090)
- INSPECT_IA_AGENTS_WIRE_RUN_HEADER -- request header carrying the originating run id
                              (default x-inspect-run-id); forwarded to the buffer.
"""

from __future__ import annotations

import hashlib
import json
import os
import struct
import urllib.request

DEFAULT_API_URL = "http://host.docker.internal:8090"
DEFAULT_RUN_HEADER = "x-inspect-run-id"
# Cap the body we forward; the server clamps again, but smaller POSTs keep the
# overlay light. A truncated body is enough to read the exchange.
MAX_BODY_CHARS = 16_384
# Header names whose value must never leave the wire in clear: the API key an
# agent presents to its LLM provider. Redacted at the source (defence in depth --
# the server also redacts secret shapes in the emitted view).
_SECRET_HEADERS = {"authorization", "x-api-key", "api-key", "proxy-authorization", "cookie"}
_REDACTED = "***"

# TLS GREASE values (RFC 8701): excluded from the JA3 string per the JA3 spec so
# the fingerprint is stable across a client's randomized GREASE injection.
_GREASE = {
    0x0A0A, 0x1A1A, 0x2A2A, 0x3A3A, 0x4A4A, 0x5A5A, 0x6A6A, 0x7A7A,
    0x8A8A, 0x9A9A, 0xAAAA, 0xBABA, 0xCACA, 0xDADA, 0xEAEA, 0xFAFA,
}


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
    layers: dict | None = None,
) -> dict:
    """Normalize a flow's fields into the ``POST /proxy/wire`` ingest payload.

    Pure and total: the caller (the mitmproxy hook) extracts these fields from
    the flow object; keeping the mapping here makes it testable without the
    mitmproxy runtime. The server re-validates and re-clamps, so this is a
    convenience shape, not a trust boundary. ``layers`` is the nested per-layer
    decode (L3/L4, TLS, HTTP, timing); ``None`` when nothing could be extracted.
    """
    payload = {
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
    if layers:
        payload["layers"] = layers
    return payload


def compute_ja3(raw_client_hello: bytes) -> tuple[str, str] | None:
    """Compute (ja3_string, ja3_md5) from a raw TLS ClientHello handshake body.

    ``raw_client_hello`` is the ClientHello starting at the 2-byte client
    version (mitmproxy's ``ClientHello.raw_bytes``). Follows the JA3 spec:
    ``SSLVersion,Ciphers,Extensions,EllipticCurves,ECPointFormats`` with GREASE
    values filtered. Returns ``None`` on any parse error (honest absence -- a
    wrong fingerprint would be worse than none).
    """
    try:
        buf = memoryview(raw_client_hello)
        # Some sources prefix the 4-byte handshake header (type=1 + 3-byte len).
        if len(buf) >= 6 and buf[0] == 0x01:
            buf = buf[4:]
        version = struct.unpack_from(">H", buf, 0)[0]
        off = 2 + 32  # version + 32-byte random
        sid_len = buf[off]
        off += 1 + sid_len
        cs_len = struct.unpack_from(">H", buf, off)[0]
        off += 2
        ciphers = []
        for i in range(off, off + cs_len, 2):
            c = struct.unpack_from(">H", buf, i)[0]
            if c not in _GREASE:
                ciphers.append(c)
        off += cs_len
        comp_len = buf[off]
        off += 1 + comp_len
        exts: list[int] = []
        curves: list[int] = []
        formats: list[int] = []
        if off + 2 <= len(buf):
            ext_total = struct.unpack_from(">H", buf, off)[0]
            off += 2
            end = off + ext_total
            while off + 4 <= end:
                etype = struct.unpack_from(">H", buf, off)[0]
                elen = struct.unpack_from(">H", buf, off + 2)[0]
                off += 4
                if etype not in _GREASE:
                    exts.append(etype)
                if etype == 0x000A and elen >= 2:  # supported_groups (curves)
                    glen = struct.unpack_from(">H", buf, off)[0]
                    for i in range(off + 2, off + 2 + glen, 2):
                        g = struct.unpack_from(">H", buf, i)[0]
                        if g not in _GREASE:
                            curves.append(g)
                elif etype == 0x000B and elen >= 1:  # ec_point_formats
                    flen = buf[off]
                    formats.extend(buf[off + 1 : off + 1 + flen])
                off += elen
        ja3_str = "{},{},{},{},{}".format(
            version,
            "-".join(str(c) for c in ciphers),
            "-".join(str(e) for e in exts),
            "-".join(str(c) for c in curves),
            "-".join(str(f) for f in formats),
        )
        return ja3_str, hashlib.md5(ja3_str.encode()).hexdigest()  # noqa: S324  # JA3 is defined on MD5
    except Exception:  # noqa: BLE001 - a malformed hello yields no fingerprint, never a crash
        return None


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


def _addr(peer: object) -> tuple[str | None, int | None]:
    """Split a mitmproxy (host, port[, ...]) address tuple into (ip, port)."""
    if isinstance(peer, (tuple, list)) and len(peer) >= 2:
        ip = str(peer[0]) if peer[0] is not None else None
        try:
            port = int(peer[1])
        except (TypeError, ValueError):
            port = None
        return ip, port
    return None, None


def _ip_version(ip: str | None) -> int | None:
    if not ip:
        return None
    return 6 if ":" in ip else 4


def _redact_headers(headers: object) -> dict:
    """Decoded header map with secret-bearing headers masked at the source."""
    out: dict[str, str] = {}
    try:
        for k, v in headers.items():  # type: ignore[attr-defined]  # mitmproxy Headers is a multidict
            key = str(k)
            out[key] = _REDACTED if key.lower() in _SECRET_HEADERS else str(v)
    except Exception:  # noqa: BLE001 - odd/undecodable headers must not crash the hook
        pass
    return out


def _decoded_alpn(conn: object) -> str | None:
    alpn = getattr(conn, "alpn", None)
    if isinstance(alpn, (bytes, bytearray)):
        try:
            return alpn.decode() or None
        except Exception:  # noqa: BLE001
            return None
    return str(alpn) if alpn else None


def _tls_layer(client_conn: object, server_conn: object, ja3: tuple[str, str] | None) -> dict:
    """Negotiated TLS parameters + upstream certificate + client JA3."""
    cipher = getattr(client_conn, "cipher", None) or getattr(client_conn, "cipher_name", None)
    layer = {
        "version": getattr(client_conn, "tls_version", None),
        "cipher": cipher,
        "sni": getattr(client_conn, "sni", None),
        "alpn": _decoded_alpn(client_conn),
        "upstream_version": getattr(server_conn, "tls_version", None),
        "upstream_cipher": getattr(server_conn, "cipher", None)
        or getattr(server_conn, "cipher_name", None),
        "ja3": ja3[1] if ja3 else None,
        "ja3_string": ja3[0] if ja3 else None,
    }
    # Upstream certificate (the real server the agent reached).
    certs = getattr(server_conn, "certificate_list", None) or []
    if certs:
        leaf = certs[0]
        layer["cert_subject"] = str(getattr(leaf, "cn", None) or getattr(leaf, "subject", None) or "") or None
        layer["cert_issuer"] = str(getattr(leaf, "issuer", None) or "") or None
        notafter = getattr(leaf, "notafter", None)
        layer["cert_not_after"] = str(notafter) if notafter else None
    return layer


def _timing_layer(req: object, resp: object, server_conn: object) -> dict:
    """Per-phase waterfall from mitmproxy timestamps (seconds -> ms). None-safe."""
    def ms(a: object, b: object) -> float | None:
        if isinstance(a, (int, float)) and isinstance(b, (int, float)) and b >= a:
            return round((b - a) * 1000, 3)
        return None

    t_conn_start = getattr(server_conn, "timestamp_start", None)
    t_tcp = getattr(server_conn, "timestamp_tcp_setup", None)
    t_tls = getattr(server_conn, "timestamp_tls_setup", None)
    t_req_start = getattr(req, "timestamp_start", None)
    t_resp_start = getattr(resp, "timestamp_start", None)
    t_resp_end = getattr(resp, "timestamp_end", None)
    return {
        "tcp_setup_ms": ms(t_conn_start, t_tcp),
        "tls_setup_ms": ms(t_tcp, t_tls),
        "ttfb_ms": ms(t_req_start, t_resp_start),
        "total_ms": ms(t_req_start, t_resp_end),
    }


class WireCapture:
    """mitmproxy addon: layered decode, one exchange per ``response`` hook.

    The client JA3 is computed once at the ClientHello (``tls_clienthello``) and
    cached by connection id, then attached to the completed flow -- the hello is
    not available anymore at ``response`` time.
    """

    def __init__(self) -> None:
        # id(client_connection) -> (ja3_string, ja3_md5). Bounded: entries are
        # popped when their flow completes; a dropped connection just leaks one
        # small tuple until process exit (the overlay is short-lived / debug).
        self._ja3: dict[int, tuple[str, str]] = {}

    def tls_clienthello(self, data: object) -> None:  # noqa: ANN001 - mitmproxy duck-types
        try:
            client = data.context.client  # type: ignore[attr-defined]
            hello = data.client_hello  # type: ignore[attr-defined]
            raw = getattr(hello, "raw_bytes", None)
            if raw is not None:
                ja3 = compute_ja3(bytes(raw))
                if ja3 is not None:
                    self._ja3[id(client)] = ja3
        except Exception:  # noqa: BLE001 - fingerprinting must never break the handshake
            pass

    def response(self, flow: object) -> None:  # noqa: ANN001 - mitmproxy duck-types the flow
        req = getattr(flow, "request", None)
        resp = getattr(flow, "response", None)
        if req is None or resp is None:
            return
        run_header = _run_header()
        run_id = None
        try:
            run_id = req.headers.get(run_header)
        except Exception:  # noqa: BLE001 - missing/odd headers must not crash the hook
            run_id = None
        start = getattr(req, "timestamp_start", None)
        end = getattr(resp, "timestamp_end", None)
        duration_ms = (
            round((end - start) * 1000, 3)
            if isinstance(start, (int, float)) and isinstance(end, (int, float))
            else None
        )
        layers = self._build_layers(flow, req, resp)
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
            layers=layers,
        )
        _post(payload)

    def _build_layers(self, flow: object, req: object, resp: object) -> dict:
        """Assemble the L3/L4 + TLS + HTTP + timing decode for one flow."""
        client_conn = getattr(flow, "client_conn", None)
        server_conn = getattr(flow, "server_conn", None)
        src_ip, src_port = _addr(getattr(client_conn, "peername", None))
        dst_ip, dst_port = _addr(getattr(server_conn, "peername", None))
        ja3 = self._ja3.pop(id(client_conn), None) if client_conn is not None else None
        return {
            "l3l4": {
                "src_ip": src_ip,
                "src_port": src_port,
                "dst_ip": dst_ip,
                "dst_port": dst_port,
                "transport": "TCP",
                "ip_version": _ip_version(dst_ip or src_ip),
            },
            "tls": _tls_layer(client_conn, server_conn, ja3)
            if getattr(req, "scheme", "") == "https"
            else None,
            "http": {
                "version": getattr(req, "http_version", None),
                "reason": getattr(resp, "reason", None),
                "request_headers": _redact_headers(getattr(req, "headers", {})),
                "response_headers": _redact_headers(getattr(resp, "headers", {})),
            },
            "timing": _timing_layer(req, resp, server_conn),
        }


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
