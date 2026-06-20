"""Content-free context receipts: intent + size/digest, NEVER the body. Pure I4."""

from __future__ import annotations

import hashlib
import json
import unittest

from recette.context_receipt import receipt

_TRACE = {
    "seq": 3,
    "event_id": "evt-0003",
    "timestamp": "2026-01-01T00:00:00Z",
    "agent_id": "gh-pr-bot",
    "target_system": "github",
    "target": "api.github.com",
    "action_type": "open_pr",
    "resource": "acme/x",
    "request_payload": {"title": "secret PR title", "body": "confidential"},
    "ok": True,
    "status_code": 201,
    "side_effect_hash": "abc",
    "run_id": "run-1",
    "response": {"number": 42, "secret_token": "tok-xyz"},
}


class TestReceipt(unittest.TestCase):
    def test_keeps_intent_metadata(self) -> None:
        r = receipt(_TRACE)
        self.assertEqual(r["action_type"], "open_pr")
        self.assertEqual(r["target"], "api.github.com")
        self.assertEqual(r["status_code"], 201)
        self.assertEqual(r["run_id"], "run-1")

    def test_never_carries_the_bodies(self) -> None:
        r = receipt(_TRACE)
        blob = json.dumps(r)
        # No raw content leaks: neither request nor response values appear.
        self.assertNotIn("secret PR title", blob)
        self.assertNotIn("confidential", blob)
        self.assertNotIn("tok-xyz", blob)
        self.assertNotIn("request_payload", r)
        self.assertNotIn("response", r)

    def test_size_and_digest_are_verifiable(self) -> None:
        r = receipt(_TRACE)
        canonical = json.dumps(
            _TRACE["request_payload"], sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
        self.assertEqual(r["request_bytes"], len(canonical))
        self.assertEqual(r["request_sha256"], hashlib.sha256(canonical).hexdigest())

    def test_empty_body_is_zero_bytes_empty_digest(self) -> None:
        r = receipt({**_TRACE, "request_payload": {}, "response": {}})
        self.assertEqual(r["request_bytes"], 0)
        self.assertEqual(r["request_sha256"], "")
        self.assertEqual(r["response_bytes"], 0)

    def test_deterministic(self) -> None:
        self.assertEqual(receipt(_TRACE), receipt(_TRACE))


try:
    from fastapi.testclient import TestClient

    from recette.api.app import create_app

    _HAVE_FASTAPI = True
except ImportError:  # pragma: no cover
    _HAVE_FASTAPI = False


@unittest.skipUnless(_HAVE_FASTAPI, "fastapi not installed")
class TestReceiptsRoute(unittest.TestCase):
    def test_receipts_endpoint_shape(self) -> None:
        body = TestClient(create_app()).get("/proxy/receipts").json()
        self.assertIn("receipts", body)
        self.assertIsInstance(body["receipts"], list)


if __name__ == "__main__":
    unittest.main()
