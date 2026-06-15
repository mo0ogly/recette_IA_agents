"""Endpoint test for GET /proxy/reconcile (wire-vs-audit, allowlist slice).

Container-free: seed the wire recorder via POST /proxy/wire with one allowlisted
flow (the lab) and one honeypot flow (:9113), then assert /proxy/reconcile flags
the honeypot as a bypass. The deterministic recette never runs a real overlay.
"""

from __future__ import annotations

import json
import unittest

try:
    from fastapi.testclient import TestClient

    from recette.api.app import create_app
    from recette.platform.eventstore.memory_store import InMemoryEventStore

    _HAS_FASTAPI = True
except ImportError:  # pragma: no cover - depends on the [api] extra
    _HAS_FASTAPI = False


def _flow(**over: object) -> dict:
    base = {
        "method": "POST",
        "scheme": "http",
        "host": "127.0.0.1",
        "port": 8082,
        "path": "/github/execute",
        "status_code": 200,
        "request_body": "{}",
        "response_body": "{}",
        "run_id": "run-1",
    }
    base.update(over)
    return base


@unittest.skipUnless(_HAS_FASTAPI, "requires the [api] extra (fastapi)")
class ReconcileEndpointTest(unittest.TestCase):
    def setUp(self) -> None:
        # Inject a fresh in-memory store so the raise endpoint's idempotency is
        # tested against a clean log, not a persistent file shared across runs.
        self.client = TestClient(create_app(event_store=InMemoryEventStore()))

    def test_clean_run_reconciles_ok(self) -> None:
        # A single flow to the lab (:8082) -> mediated -> ok.
        self.client.post("/proxy/wire", json=_flow(port=8082))
        body = self.client.get("/proxy/reconcile", params={"run_id": "run-1"}).json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["bypass_flows"], [])

    def test_honeypot_flow_is_flagged_as_bypass(self) -> None:
        self.client.post("/proxy/wire", json=_flow(port=8082))  # lab, allowed
        self.client.post("/proxy/wire", json=_flow(port=9113, path="/write"))  # honeypot
        body = self.client.get("/proxy/reconcile", params={"run_id": "run-1"}).json()
        self.assertFalse(body["ok"])
        self.assertEqual([f["port"] for f in body["bypass_flows"]], [9113])

    def test_raise_records_one_compensatory_event_and_is_idempotent(self) -> None:
        self.client.post("/proxy/wire", json=_flow(port=8082))  # mediated
        self.client.post("/proxy/wire", json=_flow(port=9113, path="/write"))  # ghost
        first = self.client.post("/proxy/reconcile/raise", params={"run_id": "run-1"}).json()
        self.assertEqual(first["raised"], 1)
        self.assertEqual(len(first["event_ids"]), 1)
        # Re-raising the same bypass appends nothing (idempotent, no log spam).
        again = self.client.post("/proxy/reconcile/raise", params={"run_id": "run-1"}).json()
        self.assertEqual(again["raised"], 0)

    def test_raise_on_clean_run_records_nothing(self) -> None:
        self.client.post("/proxy/wire", json=_flow(port=8082))  # only the lab
        body = self.client.post("/proxy/reconcile/raise", params={"run_id": "run-1"}).json()
        self.assertEqual(body["raised"], 0)

    def test_configured_llm_backend_host_is_not_a_bypass(self) -> None:
        # Register a groq backend, then a wire flow to api.groq.com:443 must be
        # treated as mediated (real-mode LLM traffic), not an unmediated path.
        self.client.post(
            "/config/ai-backends",
            json={"id": "b-groq", "provider": "groq", "model": "llama"},
        )
        self.client.post(
            "/proxy/wire",
            json=_flow(host="api.groq.com", port=443, path="/openai/v1/chat/completions"),
        )
        body = self.client.get("/proxy/reconcile", params={"run_id": "run-1"}).json()
        self.assertTrue(body["ok"])
        self.assertEqual(body["bypass_flows"], [])

    def test_unconfigured_llm_host_still_flags(self) -> None:
        # No backend registered for this host -> still an unmediated path.
        self.client.post("/proxy/wire", json=_flow(host="api.evil.test", port=443, path="/x"))
        body = self.client.get("/proxy/reconcile", params={"run_id": "run-1"}).json()
        self.assertFalse(body["ok"])
        self.assertEqual([f["host"] for f in body["bypass_flows"]], ["api.evil.test"])

    def test_strict_flags_ghost_via_allowlisted_target(self) -> None:
        # A governed-shaped write to the lab (:8082, mediated) with NO ProxyTrace
        # behind it: phase 2 sees a mediated target and says ok; phase 3 (strict)
        # recomputes the side_effect_hash, finds no audit event, and flags it.
        ghost = _flow(
            port=8082,
            path="/github/execute",
            request_body=json.dumps(
                {"action_type": "open_pr", "resource": "acme/x", "payload": {}}
            ),
            response_body=json.dumps({"success": True, "data": {"number": 42}}),
        )
        self.client.post("/proxy/wire", json=ghost)
        lenient = self.client.get("/proxy/reconcile", params={"run_id": "run-1"}).json()
        self.assertTrue(lenient["ok"])  # phase 2 misses it
        strict = self.client.get(
            "/proxy/reconcile", params={"run_id": "run-1", "strict": "true"}
        ).json()
        self.assertFalse(strict["ok"])  # phase 3 catches it
        self.assertEqual([f["bypass_reason"] for f in strict["bypass_flows"]], ["no_audit_event"])


if __name__ == "__main__":
    unittest.main()
