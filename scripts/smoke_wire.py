#!/usr/bin/env python3
"""Live smoke for the OPTIONAL mitmproxy wire-interception overlay.

Proves the full network-level chain end to end:

    client --(HTTP proxy)--> [mitmproxy container] --> lab :8082
                                  | addon POSTs the flow
                                  v
                          API /proxy/wire  (flow shows up in the ring)

Re-runnable and self-skipping: needs Docker + a running governed API (start it
with ``./recette.sh platform up``). Without Docker, or with the API down, it
SKIPS with a clear reason instead of failing -- the deterministic regression
lives in the unittest suite (tests/test_wire_proxy.py, test_api_wire.py,
test_wire_routing.py, test_mitm_addon.py); this is the live wiring proof (R14).

Run it through the single entry point:  ./recette.sh wire up  then this script,
or let it bring the overlay up/down itself (default).
"""

from __future__ import annotations

import json
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
API_URL = "http://127.0.0.1:8090"
LAB_URL = "http://127.0.0.1:8082"
WIRE_PROXY = "http://127.0.0.1:8083"
WIRE_PORT = 8083


def _skip(reason: str) -> None:
    print(f"SKIP smoke_wire: {reason}")
    sys.exit(0)


def _fail(reason: str) -> None:
    print(f"FAIL smoke_wire: {reason}")
    sys.exit(1)


def _http_json(url: str, *, method: str = "GET", proxy: str | None = None) -> tuple[int, dict]:
    handlers: list[urllib.request.BaseHandler] = []
    if proxy:
        handlers.append(urllib.request.ProxyHandler({"http": proxy, "https": proxy}))
    opener = urllib.request.build_opener(*handlers)
    req = urllib.request.Request(url, method=method)
    try:
        with opener.open(req, timeout=10) as resp:  # noqa: S310  # nosec B310
            return resp.status, json.loads(resp.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as exc:
        return exc.code, {}


def _port_open(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(1.0)
        return s.connect_ex((host, port)) == 0


def _compose(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["docker", "compose", "--profile", "wire", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def main() -> None:
    if shutil.which("docker") is None:
        _skip("docker not installed")
    try:
        status, _ = _http_json(f"{API_URL}/health")
    except OSError:
        _skip("governed API not reachable on :8090 (run ./recette.sh platform up)")
        return
    if status != 200:
        _skip(f"API health returned {status}")

    print("smoke_wire: bringing the mitmproxy overlay up (may pull the image)...")
    up = _compose("up", "-d", "wire-proxy")
    if up.returncode != 0:
        _skip(f"could not start wire-proxy (docker): {up.stderr.strip()[:200]}")

    try:
        # Wait for mitmdump to bind the proxy port.
        for _ in range(60):
            if _port_open("127.0.0.1", WIRE_PORT):
                break
            time.sleep(1)
        else:
            _fail("wire-proxy did not bind :8083 in time")

        # Clear the ring so the assertion is unambiguous.
        _http_json(f"{API_URL}/proxy/wire", method="DELETE")

        # Drive a request THROUGH the proxy to the live lab. mitmproxy forwards
        # it and its addon POSTs the flow to the API ring.
        marker_path = "/okta/healthz"
        code, _ = _http_json(f"{LAB_URL}{marker_path}", proxy=WIRE_PROXY)
        print(f"smoke_wire: request through proxy -> lab {marker_path} returned {code}")

        # Poll the ring for the intercepted flow.
        for _ in range(20):
            _, body = _http_json(f"{API_URL}/proxy/wire")
            flows = body.get("flows", [])
            hit = next((f for f in flows if f.get("path") == marker_path), None)
            if hit is not None:
                print(f"smoke_wire: PASS -- flow captured: {json.dumps(hit)[:200]}")
                return
            time.sleep(0.5)
        _fail("no intercepted flow reached /proxy/wire (addon -> API ingest broken)")
    finally:
        print("smoke_wire: tearing the overlay down")
        _compose("rm", "-sf", "wire-proxy")


if __name__ == "__main__":
    main()
