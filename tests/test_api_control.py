"""S1: /control/summary is a pure, deterministic governance digest (I1/I4)."""

from __future__ import annotations

import unittest

from recette.api.routers.control import summarize
from recette.platform.eventstore.protocol import StoredEvent


def _event(seq: int, kind: str, verdict: str | None, approval: str) -> StoredEvent:
    payload: dict = {"approval_state": approval}
    if verdict is not None:
        payload["policy_decision"] = {"verdict": verdict, "version": "v1", "rule_id": "r"}
    return StoredEvent(
        seq=seq,
        event_id=f"evt-{seq:04d}",
        schema_version="2.0",
        kind=kind,
        payload=payload,
        prev_hash="",
        hash="",
    )


_LOG = [
    _event(1, "action_executed", "allow", "none"),
    _event(2, "action_denied", "deny", "none"),
    _event(3, "action_requested", "escalate", "pending"),
    _event(4, "approval_resolved", None, "approved"),
    _event(5, "action_executed", "allow", "approved"),
]


class TestSummarize(unittest.TestCase):
    def test_counts_verdicts_approvals_execution(self) -> None:
        s = summarize(_LOG)
        self.assertEqual(s["verdicts"], {"allow": 2, "deny": 1, "escalate": 1})
        self.assertEqual(s["total"], 4)  # 4 events carry a verdict
        self.assertEqual(s["approvals"]["pending"], 1)
        self.assertEqual(s["approvals"]["approved"], 2)
        self.assertEqual(s["executed"], 2)
        self.assertEqual(s["denied_execution"], 1)
        self.assertTrue(s["deny_by_default"])

    def test_is_deterministic(self) -> None:
        self.assertEqual(summarize(_LOG), summarize(_LOG))

    def test_empty_log(self) -> None:
        s = summarize([])
        self.assertEqual(s["total"], 0)
        self.assertEqual(s["verdicts"], {"allow": 0, "deny": 0, "escalate": 0})


try:
    from fastapi.testclient import TestClient

    from recette.api.app import create_app

    _HAVE_FASTAPI = True
except ImportError:  # pragma: no cover
    _HAVE_FASTAPI = False


@unittest.skipUnless(_HAVE_FASTAPI, "fastapi not installed")
class TestControlRoute(unittest.TestCase):
    def test_summary_endpoint_shape(self) -> None:
        client = TestClient(create_app())
        body = client.get("/control/summary").json()
        self.assertIn("verdicts", body)
        self.assertIn("approvals", body)
        self.assertTrue(body["deny_by_default"])
        self.assertEqual(set(body["verdicts"]), {"allow", "deny", "escalate"})


if __name__ == "__main__":
    unittest.main()
