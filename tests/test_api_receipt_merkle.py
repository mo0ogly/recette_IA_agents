"""Endpoint tests for the receipt Merkle root + inclusion proof.

GET /proxy/receipts/merkle returns the root committing to the current receipts;
GET /proxy/receipts/merkle/proof?seq=N returns an inclusion proof a verifier can
fold to the root WITHOUT the other receipts (selective disclosure). Both are pure
given the recorder snapshot (I4) and content-free.
"""

from __future__ import annotations

import unittest

from recette.platform.proxy.tracing import ProxyTrace
from recette.receipt_merkle import verify_inclusion

try:
    from fastapi.testclient import TestClient

    from recette.api.app import create_app

    _HAS_FASTAPI = True
except ImportError:  # pragma: no cover - depends on the [api] extra
    _HAS_FASTAPI = False


def _proxy_trace(seq: int) -> ProxyTrace:
    return ProxyTrace(
        seq=seq,
        event_id=f"evt-{seq:04d}",
        timestamp="2026-01-01T00:00:00Z",
        agent_id="gh-pr-bot",
        target_system="github",
        target="api.github.com",
        action_type="open_pr",
        resource=f"acme/repo{seq}",
        request_payload={"n": seq},
        ok=True,
        status_code=201,
        side_effect_hash=f"h{seq}",
        error=None,
        run_id="run-1",
        response={"ok": True},
    )


@unittest.skipUnless(_HAS_FASTAPI, "requires the [api] extra (fastapi)")
class ReceiptMerkleEndpointTest(unittest.TestCase):
    def setUp(self) -> None:
        self.app = create_app()
        self.client = TestClient(self.app)
        # Feed a few traces into the proxy recorder so receipts exist.
        recorder = self.app.state.proxy_trace_recorder
        for i in range(1, 4):
            recorder._ring.append(_proxy_trace(i))  # noqa: SLF001 -- test seam

    def test_empty_recorder_has_empty_root(self) -> None:
        client = TestClient(create_app())  # fresh app, no traces
        body = client.get("/proxy/receipts/merkle").json()
        self.assertEqual(body["root"], "")
        self.assertEqual(body["count"], 0)

    def test_root_and_count(self) -> None:
        body = self.client.get("/proxy/receipts/merkle").json()
        self.assertEqual(body["count"], 3)
        self.assertEqual(len(body["root"]), 64)

    def test_inclusion_proof_folds_to_root(self) -> None:
        receipts = self.client.get("/proxy/receipts").json()["receipts"]
        root = self.client.get("/proxy/receipts/merkle").json()["root"]
        for r in receipts:
            proof = self.client.get(f"/proxy/receipts/merkle/proof?seq={r['seq']}").json()
            self.assertEqual(proof["root"], root)
            self.assertTrue(verify_inclusion(proof["leaf"], proof["path"], root))

    def test_unknown_seq_is_404(self) -> None:
        resp = self.client.get("/proxy/receipts/merkle/proof?seq=9999")
        self.assertEqual(resp.status_code, 404)


if __name__ == "__main__":
    unittest.main()
