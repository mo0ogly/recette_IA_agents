"""Content-free context receipts -- privacy-safe boundary-crossing audit.

A ``ProxyTrace`` records the full agent<->server exchange (request_payload +
response bodies). A *context receipt* is its content-FREE projection: it keeps
the INTENT metadata (who, target, action_type, resource, outcome) and replaces
the bodies with their byte-size + SHA-256 digest -- so an auditor can prove WHAT
crossed the boundary and that it is unchanged, without the platform ever logging
or exposing the raw content. (The pluribus "context receipt" idea, aligned with
this repo's legibility-first + audit posture for an RSSI/auditor audience.)

Pure and deterministic (I4): a function of one trace dict, SHA-256 over the
canonical JSON of each body (sort_keys, compact) -- no clock, no randomness.
"""

from __future__ import annotations

import hashlib
import json


def _digest(body: object) -> tuple[int, str]:
    """(byte length, sha256 hex) of a body's canonical JSON. ``({}, '')`` -> empty."""
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    raw = canonical.encode("utf-8")
    if not body:
        return 0, ""
    return len(raw), hashlib.sha256(raw).hexdigest()


def receipt(trace: dict) -> dict:
    """Content-free receipt of one ProxyTrace dict: intent metadata + body
    size/digest, never the body itself."""
    req_bytes, req_sha = _digest(trace.get("request_payload", {}))
    resp_bytes, resp_sha = _digest(trace.get("response", {}))
    return {
        "seq": trace.get("seq"),
        "event_id": trace.get("event_id"),
        "timestamp": trace.get("timestamp"),
        "agent_id": trace.get("agent_id"),
        "target_system": trace.get("target_system"),
        "target": trace.get("target"),
        "action_type": trace.get("action_type"),
        "resource": trace.get("resource"),
        "ok": trace.get("ok"),
        "status_code": trace.get("status_code"),
        "side_effect_hash": trace.get("side_effect_hash"),
        "run_id": trace.get("run_id"),
        "request_bytes": req_bytes,
        "request_sha256": req_sha,
        "response_bytes": resp_bytes,
        "response_sha256": resp_sha,
    }
