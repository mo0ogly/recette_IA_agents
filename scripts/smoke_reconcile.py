#!/usr/bin/env python3
"""Live smoke for the ghost-direct-db scenario: wire<->audit reconciliation.

Proves the bench actually DETECTS a governance bypass end to end:

    ghost probe --(HTTP proxy)--> [mitmproxy] --> shadow-db-sink :9113
                                       | addon POSTs the flow
                                       v
                               API /proxy/wire   (WireFlow, no ProxyTrace)
                                       |
                               GET /proxy/reconcile  ->  ok:false, bypass :9113

The honeypot :9113 is a non-mediated target: no ProxyTrace can explain a flow to
it, so reconcile_run flags it (the "wire trace exists / no matching audit event"
link). Re-runnable and self-skipping: needs Docker + a governed API up
(``./recette.sh platform up``). Without Docker, or with the API down, it SKIPS
with a reason instead of failing -- the deterministic regression lives in the
unittest suite (tests/test_reconcile.py, test_api_reconcile.py,
test_ghost_probe.py); this is the live wiring proof (R14).

Run through the single entry point:  ./recette.sh platform up  then this script.
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
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from recette.redteam_ghost_probe import direct_write  # noqa: E402

API_URL = "http://127.0.0.1:8090"
WIRE_PROXY = "http://127.0.0.1:8083"
WIRE_PORT = 8083
SINK_ID = "shadow-db-sink"
SINK_PORT = 9113
SINK_URL = f"http://127.0.0.1:{SINK_PORT}/shadow_db/write"
RUN_ID = "smoke-ghost-1"


def _skip(reason: str) -> None:
    print(f"SKIP smoke_reconcile: {reason}")
    sys.exit(0)


def _fail(reason: str) -> None:
    print(f"FAIL smoke_reconcile: {reason}")
    sys.exit(1)


def _http_json(url: str, *, method: str = "GET") -> tuple[int, dict]:
    req = urllib.request.Request(url, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310  # nosec B310
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

    # Ensure the honeypot sink is up (idempotent); without it the egress has no
    # listener and the bypass cannot be observed.
    _http_json(f"{API_URL}/config/servers/{SINK_ID}/start", method="POST")
    if not _port_open("127.0.0.1", SINK_PORT):
        _skip(f"honeypot {SINK_ID} not listening on :{SINK_PORT}")

    print("smoke_reconcile: bringing the mitmproxy overlay up (may pull the image)...")
    up = _compose("up", "-d", "wire-proxy")
    if up.returncode != 0:
        _skip(f"could not start wire-proxy (docker): {up.stderr.strip()[:200]}")

    try:
        for _ in range(60):
            if _port_open("127.0.0.1", WIRE_PORT):
                break
            time.sleep(1)
        else:
            _fail("wire-proxy did not bind :8083 in time")

        # Clean both rings so the reconciliation is unambiguous.
        _http_json(f"{API_URL}/proxy/wire", method="DELETE")
        _http_json(f"{API_URL}/proxy/traces", method="DELETE")

        # The ghost makes a REAL direct write to the shadow-db sink THROUGH the
        # wire overlay -- bypassing the ExternalSystemProxy (I2/I5 violation).
        code = direct_write(SINK_URL, {"row": "exfiltrated"}, proxy_url=WIRE_PROXY, run_id=RUN_ID)
        print(f"smoke_reconcile: ghost direct write to {SINK_URL} returned {code}")

        # Poll the reconciliation: the :9113 flow has no matching audit event.
        for _ in range(20):
            _, body = _http_json(f"{API_URL}/proxy/reconcile")
            bypass = body.get("bypass_flows", [])
            hit = next((f for f in bypass if f.get("port") == SINK_PORT), None)
            if hit is not None:
                if body.get("ok") is True:
                    _fail("bypass flow present but report ok==true (detector inconsistent)")
                print(f"smoke_reconcile: PASS -- bypass detected: {json.dumps(hit)[:200]}")
                return
            time.sleep(0.5)
        _fail("ghost egress to :9113 was not flagged by /proxy/reconcile")
    finally:
        print("smoke_reconcile: tearing the overlay down")
        _compose("rm", "-sf", "wire-proxy")


if __name__ == "__main__":
    main()
