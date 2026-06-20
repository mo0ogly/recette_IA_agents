"""Endpoint test for cross-verifying a third-party receipt export.

POST /proxy/receipts/verify-import re-checks ANY ``inspect_ia_agents-receipt-export-v1``
envelope (the Ed25519 signature over its canonical payload + the receipt hash
chain) without trusting it. Stateless and pure (I4): nothing is read from the
recorders or the audit log, so the verdict is a function of the posted envelope
alone. This proves the off-platform exchange: sign here, verify there.
"""

from __future__ import annotations

import os
import unittest

from recette.context_receipt import chain_receipts
from recette.receipt_export import SIGNING_KEY_ENV, export_receipts

try:
    from fastapi.testclient import TestClient

    from recette.api.app import create_app

    _HAS_FASTAPI = True
except ImportError:  # pragma: no cover - depends on the [api] extra
    _HAS_FASTAPI = False

try:
    import cryptography.hazmat.primitives.asymmetric.ed25519  # noqa: F401

    _HAVE_CRYPTO = True
except ImportError:  # pragma: no cover
    _HAVE_CRYPTO = False

_TRACE = {
    "seq": 1,
    "event_id": "evt-0001",
    "timestamp": "2026-01-01T00:00:00Z",
    "agent_id": "gh-pr-bot",
    "target_system": "github",
    "target": "api.github.com",
    "action_type": "open_pr",
    "resource": "acme/x",
    "request_payload": {"a": 1},
    "ok": True,
    "status_code": 201,
    "side_effect_hash": "h",
    "run_id": "run-1",
    "response": {"n": 42},
}
_SEED = "a12a12dbf6c6a9b89c9e3ef84707a4c2fc0d04a5fa0a78536df8930b4bf16a65"


@unittest.skipUnless(_HAS_FASTAPI, "requires the [api] extra (fastapi)")
class VerifyImportEndpointTest(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(create_app())

    def test_unsigned_envelope_is_invalid_chain_ok(self) -> None:
        saved = os.environ.pop(SIGNING_KEY_ENV, None)
        try:
            env = export_receipts(chain_receipts([_TRACE]))
        finally:
            if saved is not None:
                os.environ[SIGNING_KEY_ENV] = saved
        body = self.client.post("/proxy/receipts/verify-import", json=env).json()
        self.assertFalse(body["signature"]["valid"])
        # The chain itself is intact even though the export is unsigned.
        self.assertTrue(body["chain"]["ok"])

    def test_non_object_is_422(self) -> None:
        # A JSON array is not an export envelope object.
        r = self.client.post("/proxy/receipts/verify-import", json=[1, 2])
        self.assertEqual(r.status_code, 422)

    @unittest.skipUnless(_HAVE_CRYPTO, "cryptography ([bundle] extra) not installed")
    def test_signed_roundtrip_then_tamper(self) -> None:
        saved = os.environ.get(SIGNING_KEY_ENV)
        os.environ[SIGNING_KEY_ENV] = _SEED
        try:
            env = export_receipts(chain_receipts([_TRACE]))
        finally:
            if saved is None:
                os.environ.pop(SIGNING_KEY_ENV, None)
            else:
                os.environ[SIGNING_KEY_ENV] = saved

        good = self.client.post("/proxy/receipts/verify-import", json=env).json()
        self.assertTrue(good["signature"]["valid"])
        self.assertTrue(good["chain"]["ok"])

        # Key pinning: a wrong expected key fails the signature.
        pinned = self.client.post(
            "/proxy/receipts/verify-import?expected_public_key=deadbeef", json=env
        ).json()
        self.assertFalse(pinned["signature"]["valid"])

        # Tamper a receipt -> both the signature and the chain break.
        env["receipts"][0]["action_type"] = "TAMPERED"
        bad = self.client.post("/proxy/receipts/verify-import", json=env).json()
        self.assertFalse(bad["signature"]["valid"])
        self.assertFalse(bad["chain"]["ok"])


if __name__ == "__main__":
    unittest.main()
