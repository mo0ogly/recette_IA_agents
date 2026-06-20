"""Signed receipt export: Ed25519 sign/verify roundtrip, tamper, unsigned fail-safe."""

from __future__ import annotations

import os
import unittest

from recette.context_receipt import chain_receipts
from recette.receipt_export import SIGNING_KEY_ENV, export_receipts, verify_export

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
# A fixed 32-byte Ed25519 seed (test-only, not a real secret).
_SEED = "a12a12dbf6c6a9b89c9e3ef84707a4c2fc0d04a5fa0a78536df8930b4bf16a65"


class TestUnsigned(unittest.TestCase):
    def setUp(self) -> None:
        self._saved = os.environ.pop(SIGNING_KEY_ENV, None)

    def tearDown(self) -> None:
        if self._saved is not None:
            os.environ[SIGNING_KEY_ENV] = self._saved

    def test_no_key_yields_unsigned_envelope_failsafe(self) -> None:
        env = export_receipts(chain_receipts([_TRACE]))
        self.assertFalse(env["signed"])
        self.assertNotIn("signature", env)
        self.assertEqual(env["chain_head"], chain_receipts([_TRACE])[-1]["hash"])
        # verify of an unsigned envelope is explicitly invalid.
        self.assertFalse(verify_export(env)["valid"])


@unittest.skipUnless(_HAVE_CRYPTO, "cryptography ([bundle] extra) not installed")
class TestSigned(unittest.TestCase):
    def setUp(self) -> None:
        self._saved = os.environ.get(SIGNING_KEY_ENV)
        os.environ[SIGNING_KEY_ENV] = _SEED

    def tearDown(self) -> None:
        if self._saved is None:
            os.environ.pop(SIGNING_KEY_ENV, None)
        else:
            os.environ[SIGNING_KEY_ENV] = self._saved

    def test_sign_then_verify_roundtrip(self) -> None:
        env = export_receipts(chain_receipts([_TRACE]))
        self.assertTrue(env["signed"])
        self.assertIn("public_key", env)
        self.assertTrue(verify_export(env)["valid"])

    def test_tampered_receipt_fails_verification(self) -> None:
        env = export_receipts(chain_receipts([_TRACE]))
        env["receipts"][0]["action_type"] = "TAMPERED"
        self.assertFalse(verify_export(env)["valid"])

    def test_key_pinning(self) -> None:
        env = export_receipts(chain_receipts([_TRACE]))
        self.assertFalse(verify_export(env, expected_public_key="deadbeef")["valid"])
        self.assertTrue(verify_export(env, expected_public_key=env["public_key"])["valid"])

    def test_deterministic_payload(self) -> None:
        # Same key + same receipts -> identical signature (Ed25519 is deterministic).
        a = export_receipts(chain_receipts([_TRACE]))
        b = export_receipts(chain_receipts([_TRACE]))
        self.assertEqual(a["signature"], b["signature"])


if __name__ == "__main__":
    unittest.main()
