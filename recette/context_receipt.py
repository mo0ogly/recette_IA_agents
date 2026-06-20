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


def _chain_hash(prev_hash: str, body: dict) -> str:
    """sha256(prev_hash || canonical(body)) -- the receipt's chained digest.
    ``body`` is the receipt WITHOUT its prev_hash/hash fields."""
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256((prev_hash + canonical).encode("utf-8")).hexdigest()


def chain_receipts(traces: list[dict]) -> list[dict]:
    """Content-free receipts linked in a hash chain (sequence-integrity proof,
    like the audit log I1). Each receipt carries ``prev_hash`` and ``hash`` so a
    verifier can prove the SEQUENCE was not reordered, dropped, or altered --
    still content-free (the chain hashes the receipt, not the bodies). Pure (I4):
    genesis prev_hash is the empty string; order follows the input list."""
    out: list[dict] = []
    prev = ""
    for trace in traces:
        r = receipt(trace)  # the body to hash (no prev_hash/hash yet)
        h = _chain_hash(prev, r)
        r["prev_hash"] = prev
        r["hash"] = h
        out.append(r)
        prev = h
    return out


def verify_chain(receipts: list[dict]) -> dict:
    """Recompute every chained hash from genesis; report the first break.

    ``ok`` is True when every receipt's ``hash`` matches the recomputation and
    its ``prev_hash`` matches the predecessor's ``hash``. Pure (I4)."""
    prev = ""
    for idx, r in enumerate(receipts):
        body = {k: v for k, v in r.items() if k not in ("prev_hash", "hash")}
        if r.get("prev_hash") != prev or r.get("hash") != _chain_hash(prev, body):
            return {"ok": False, "checked": idx, "first_break_seq": r.get("seq")}
        prev = r["hash"]
    return {"ok": True, "checked": len(receipts), "first_break_seq": None}


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
