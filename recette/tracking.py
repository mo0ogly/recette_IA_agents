"""Systematic multi-session tracking of autonomous-instance exchanges.

Every boundary crossing is recorded with BOTH a ``session_id`` (one conversation /
episode) and an ``instance_id`` (the acting autonomous instance, anchored on its
agent passport). :meth:`SessionTracker.record` FAILS LOUD if either is missing --
tracking is never optional ("a chaque fois"). Receipts are content-free (see
``context_receipt``) and hash-chained PER SESSION (sequence integrity, I1); a
cross-session index links one instance across the sessions it acted in.

Deterministic (I4): no clock, no randomness; the chain is a pure function of the
recorded exchanges in order. The chain format is byte-compatible with
``context_receipt.verify_chain`` (asserted by test), so an external auditor
verifies a session's receipts with the SAME verifier used for proxy traces.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field

from .context_receipt import receipt, verify_chain


def _chain_hash(prev_hash: str, body: dict) -> str:
    """sha256(prev_hash || canonical(body)) -- identical to context_receipt so the
    two chains are cross-verifiable. ``body`` is the receipt WITHOUT prev_hash/hash."""
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256((prev_hash + canonical).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class TrackedExchange:
    """One boundary crossing by an autonomous instance, to be recorded.

    ``request_payload``/``response`` are hashed to size+digest (content-free) by
    the receipt; the raw bodies are never persisted by the tracker (R8/privacy).
    """

    session_id: str
    instance_id: str
    peer_id: str
    seq: int
    target: str = ""
    action_type: str = ""
    resource: str = ""
    ok: bool = True
    status_code: int | None = None
    request_payload: dict = field(default_factory=dict)
    response: dict = field(default_factory=dict)

    def _trace(self) -> dict:
        # Shaped like a ProxyTrace dict so context_receipt.receipt digests it.
        return {
            "seq": self.seq,
            "agent_id": self.instance_id,
            "target": self.target,
            "target_system": self.peer_id,
            "action_type": self.action_type,
            "resource": self.resource,
            "ok": self.ok,
            "status_code": self.status_code,
            "run_id": self.session_id,
            "request_payload": self.request_payload,
            "response": self.response,
        }


class SessionTracker:
    """Append-only, per-session hash-chained receipts + a cross-session index.

    Not concurrency-safe by design (a run is single-threaded and deterministic);
    the API layer owns one tracker per process and serialises writes.
    """

    def __init__(self) -> None:
        self._receipts: dict[str, list[dict]] = {}
        self._prev: dict[str, str] = {}
        self._instance_sessions: dict[str, list[str]] = {}
        self._session_instances: dict[str, list[str]] = {}

    def record(self, exchange: TrackedExchange) -> dict:
        """Record an exchange; return its content-free, chained receipt.

        Raises ``ValueError`` if ``session_id`` or ``instance_id`` is missing --
        the systematic-tracking guarantee is enforced here, not left to callers.
        """
        if not exchange.session_id or not exchange.instance_id:
            raise ValueError(
                "tracking requires BOTH session_id and instance_id (systematic, fail-loud)"
            )
        sid = exchange.session_id
        body = receipt(exchange._trace())
        body["session_id"] = sid
        body["instance_id"] = exchange.instance_id
        body["peer_id"] = exchange.peer_id
        prev = self._prev.get(sid, "")
        h = _chain_hash(prev, body)
        body["prev_hash"] = prev
        body["hash"] = h
        self._prev[sid] = h
        self._receipts.setdefault(sid, []).append(body)
        self._index(exchange.instance_id, sid)
        return body

    def _index(self, instance_id: str, session_id: str) -> None:
        inst = self._instance_sessions.setdefault(instance_id, [])
        if session_id not in inst:
            inst.append(session_id)
        sess = self._session_instances.setdefault(session_id, [])
        if instance_id not in sess:
            sess.append(instance_id)

    def receipts(self, session_id: str) -> list[dict]:
        """The chained receipts recorded for ``session_id``, in order (a copy)."""
        return list(self._receipts.get(session_id, []))

    def verify(self, session_id: str) -> dict:
        """Recompute the session's hash chain from genesis; report the first break.

        Delegates to ``context_receipt.verify_chain`` -- the same verifier used for
        proxy-trace receipts -- proving format compatibility."""
        return verify_chain(self.receipts(session_id))

    def sessions_of(self, instance_id: str) -> list[str]:
        """Every session this instance acted in (multi-session view of an instance)."""
        return list(self._instance_sessions.get(instance_id, []))

    def instances_of(self, session_id: str) -> list[str]:
        """Every instance that acted in this session."""
        return list(self._session_instances.get(session_id, []))

    def sessions(self) -> list[str]:
        """All known session ids, in first-seen order."""
        return list(self._receipts.keys())
