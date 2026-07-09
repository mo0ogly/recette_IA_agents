"""Systematic multi-session tracking: fail-loud, hash-chained, cross-session (I1/I4)."""

from __future__ import annotations

import unittest

from recette.context_receipt import verify_chain
from recette.tracking import SessionTracker, TrackedExchange


def _ex(session_id: str, instance_id: str, seq: int, **kw) -> TrackedExchange:
    return TrackedExchange(
        session_id=session_id,
        instance_id=instance_id,
        peer_id=kw.get("peer_id", "server"),
        seq=seq,
        action_type=kw.get("action_type", "speak"),
        response=kw.get("response", {"content": f"line {seq}"}),
    )


class TestSessionTracker(unittest.TestCase):
    def test_missing_ids_fail_loud(self) -> None:
        t = SessionTracker()
        with self.assertRaises(ValueError):
            t.record(_ex("", "a", 1))
        with self.assertRaises(ValueError):
            t.record(_ex("s1", "", 1))

    def test_receipts_are_content_free(self) -> None:
        t = SessionTracker()
        r = t.record(_ex("s1", "a", 1, response={"content": "secret payload"}))
        # No raw body survives; only size + digest.
        self.assertNotIn("secret payload", str(r))
        self.assertIn("response_sha256", r)
        self.assertGreater(r["response_bytes"], 0)

    def test_chain_is_verifiable_per_session(self) -> None:
        t = SessionTracker()
        for i in range(1, 4):
            t.record(_ex("s1", "a", i))
        receipts = t.receipts("s1")
        self.assertEqual(len(receipts), 3)
        # Cross-verified by the SAME verifier used for proxy traces (format parity).
        self.assertTrue(verify_chain(receipts)["ok"])
        self.assertTrue(t.verify("s1")["ok"])

    def test_tamper_breaks_the_chain(self) -> None:
        t = SessionTracker()
        t.record(_ex("s1", "a", 1))
        t.record(_ex("s1", "b", 2))
        receipts = t.receipts("s1")
        receipts[0]["instance_id"] = "tampered"
        self.assertFalse(verify_chain(receipts)["ok"])

    def test_cross_session_index(self) -> None:
        t = SessionTracker()
        t.record(_ex("s1", "agent-x", 1))
        t.record(_ex("s2", "agent-x", 1))
        t.record(_ex("s2", "agent-y", 2))
        # An instance is tracked ACROSS the sessions it acted in.
        self.assertEqual(sorted(t.sessions_of("agent-x")), ["s1", "s2"])
        self.assertEqual(sorted(t.instances_of("s2")), ["agent-x", "agent-y"])
        # Each session's chain is independent and valid.
        self.assertTrue(t.verify("s1")["ok"])
        self.assertTrue(t.verify("s2")["ok"])


if __name__ == "__main__":
    unittest.main()
