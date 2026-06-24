"""Persist a real per-PID LIVE eBPF capture (the VU surface) as ANSSI evidence.

The governed API's POST /probe/process-capture spawns a mock agent as its own
process and the CAP_BPF broker attributes kernel events to that exact PID -- a
REAL eBPF-wire surface (connect / openat / dns), not the deterministic corpus
projection in surface.json. The broker returns the recording over the socket and
appends a tamper-evident line to .run/probe.audit.jsonl (seq + recording_sha256);
the full recording itself is not written to disk. This script drives the capture,
saves the full recording, and snapshots the broker audit chain so both become
bundle artifacts a researcher can read and re-fold.

LIVE / recorded, not replayed (R14): kernel events vary slightly run to run (the
openat set depends on the interpreter's import cache), so the recording_sha256 is
a fingerprint of THIS capture, not a replay-stable hash. The audit chain proves
the capture happened under the live broker; the recording shows what it saw.

process-capture is mock-only by design (a live provider key never crosses the
spawned subprocess -- S4); the syscalls captured are real regardless of the
agent's brain. Run after `./recette.sh platform up` with caps granted.

Run: python3 scripts/run_ebpf_live_capture_skynet.py [--duration-ms 4000]
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import urllib.error
import urllib.request
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
_RUN = _ROOT / ".run"
_DIR = _ROOT / "docs" / "tracking" / "recette"
_OUT = _DIR / "ebpf_live_skynet.json"
_AUDIT_SNAPSHOT = _DIR / "probe_audit_skynet.jsonl"


def _api_base() -> str:
    """Canonical governed API, read from .run/api.port (R19/R5 -- never hardcode)."""
    port = (_RUN / "api.port").read_text(encoding="utf-8").strip()
    return f"http://127.0.0.1:{port}"


def _get(path: str) -> object:
    with urllib.request.urlopen(_api_base() + path, timeout=15) as resp:  # noqa: S310  # nosec B310 (loopback http to .run/api.port)
        return json.loads(resp.read())


def _post(path: str, body: dict) -> dict:
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        _api_base() + path, data=data, headers={"content-type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310  # nosec B310 (loopback http to .run/api.port)
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        return {"status": "error", "http_status": exc.code, "detail": exc.read().decode()[:300]}


def _mock_agents() -> list[str]:
    """Mock-scenario agents (process-capture is mock-only). Tolerates list or
    {data:[...]} / {agents:[...]} envelope shapes."""
    raw = _get("/config/agents")
    if isinstance(raw, dict):
        raw = raw.get("data", raw)
        if isinstance(raw, dict):
            raw = raw.get("agents", [])
    agents = raw if isinstance(raw, list) else []
    # The /config/agents listing keys the agent by `id` (the POST body field is
    # `agent_id`); read `id`, fall back to `agent_id` for either shape.
    out = []
    for a in agents:
        if not isinstance(a, dict):
            continue
        aid = a.get("id") or a.get("agent_id")
        if aid and a.get("ai_mode") != "real" and a.get("scenario"):
            out.append(aid)
    return out


def _summarize(rec: dict) -> dict:
    """Condense one capture for the human eye without dropping the raw surface."""
    out = []
    for r in rec.get("recordings", []):
        wire = r.get("surfaces", {}).get("ebpf_wire", [])
        out.append(
            {
                "agent_id": r.get("agent_id"),
                "connects": [w for w in wire if w.startswith("connect:")],
                "dns": [w for w in wire if w.startswith("dns:")],
                "n_open": sum(1 for w in wire if w.startswith("open:")),
                "n_events": len(wire),
                "ebpf_wire": wire,
            }
        )
    return {
        "status": rec.get("status"),
        "recording_sha256": rec.get("recording_sha256"),
        "agents": out,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Persist a live per-PID eBPF capture for the bundle.")
    ap.add_argument("--duration-ms", type=int, default=4000)
    args = ap.parse_args()

    status = _get("/probe/status")
    if not (isinstance(status, dict) and status.get("mode") == "live"):
        print(f"probe not live (status={status}); run ./recette.sh platform up with caps granted")
        return 1

    agents = _mock_agents()
    if not agents:
        print("no mock-scenario agent available for process-capture (mock-only)")
        return 1

    captures = []
    for agent_id in agents:
        rec = _post(
            "/probe/process-capture", {"agent_id": agent_id, "duration_ms": args.duration_ms}
        )
        body = rec.get("recording", rec)
        captures.append(_summarize(body))
        n = captures[-1]["agents"][0]["n_events"] if captures[-1].get("agents") else 0
        print(f"[capture] {agent_id}: status={captures[-1]['status']} events={n}")

    _DIR.mkdir(parents=True, exist_ok=True)
    _OUT.write_text(
        json.dumps(
            {
                "probe_mode": "live",
                "note": "LIVE per-PID eBPF capture (recorded, not replay-stable); "
                "kernel events vary run to run. The audit chain proves the capture "
                "ran under the CAP_BPF broker.",
                "captures": captures,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    # Snapshot the tamper-evident broker audit chain (seq + recording_sha256).
    audit = _RUN / "probe.audit.jsonl"
    if audit.exists():
        shutil.copyfile(audit, _AUDIT_SNAPSHOT)
    print(f"wrote {_OUT.relative_to(_ROOT)} + {_AUDIT_SNAPSHOT.relative_to(_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
