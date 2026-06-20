"""Signed Merkle-root attestation -- selective disclosure end to end.

The root attestation signs only ``{chain_head, count, merkle_root}`` (NO
receipts), so a verifier can trust the root WITHOUT the batch. Combined with one
inclusion proof, an auditor attests that ONE side effect crossed the boundary
without ever seeing the others. Deterministic (I4), fail-safe unsigned with no
key.
"""

from __future__ import annotations

import os
import unittest

from recette.context_receipt import chain_receipts
from recette.receipt_export import (
    SIGNING_KEY_ENV,
    export_root_attestation,
    verify_root_attestation,
)
from recette.receipt_merkle import inclusion_proof, verify_inclusion

try:
    import cryptography.hazmat.primitives.asymmetric.ed25519  # noqa: F401

    _HAVE_CRYPTO = True
except ImportError:  # pragma: no cover
    _HAVE_CRYPTO = False

_SEED = "a12a12dbf6c6a9b89c9e3ef84707a4c2fc0d04a5fa0a78536df8930b4bf16a65"


def _trace(seq: int) -> dict:
    return {
        "seq": seq,
        "event_id": f"evt-{seq:04d}",
        "timestamp": "2026-01-01T00:00:00Z",
        "agent_id": "gh-pr-bot",
        "target_system": "github",
        "target": "api.github.com",
        "action_type": "open_pr",
        "resource": f"acme/repo{seq}",
        "request_payload": {"n": seq},
        "ok": True,
        "status_code": 201,
        "side_effect_hash": f"h{seq}",
        "run_id": "run-1",
        "response": {"ok": True},
    }


class TestRootAttestationUnsigned(unittest.TestCase):
    def setUp(self) -> None:
        self._saved = os.environ.pop(SIGNING_KEY_ENV, None)

    def tearDown(self) -> None:
        if self._saved is not None:
            os.environ[SIGNING_KEY_ENV] = self._saved

    def test_no_key_unsigned_failsafe(self) -> None:
        att = export_root_attestation(chain_receipts([_trace(1), _trace(2)]))
        self.assertFalse(att["signed"])
        self.assertNotIn("signature", att)
        # The root is still present (it is a public commitment, not a secret).
        self.assertEqual(len(att["merkle_root"]), 64)
        self.assertFalse(verify_root_attestation(att)["valid"])

    def test_carries_no_receipts(self) -> None:
        att = export_root_attestation(chain_receipts([_trace(1), _trace(2)]))
        self.assertNotIn("receipts", att)
        self.assertEqual(att["count"], 2)
        self.assertEqual(att["schema"], "inspect_ia_agents-receipt-root-v1")


@unittest.skipUnless(_HAVE_CRYPTO, "cryptography ([bundle] extra) not installed")
class TestRootAttestationSigned(unittest.TestCase):
    def setUp(self) -> None:
        self._saved = os.environ.get(SIGNING_KEY_ENV)
        os.environ[SIGNING_KEY_ENV] = _SEED

    def tearDown(self) -> None:
        if self._saved is None:
            os.environ.pop(SIGNING_KEY_ENV, None)
        else:
            os.environ[SIGNING_KEY_ENV] = self._saved

    def test_sign_verify_roundtrip(self) -> None:
        att = export_root_attestation(chain_receipts([_trace(i) for i in range(1, 6)]))
        self.assertTrue(att["signed"])
        self.assertTrue(verify_root_attestation(att)["valid"])

    def test_tampered_root_fails(self) -> None:
        att = export_root_attestation(chain_receipts([_trace(1), _trace(2)]))
        att["merkle_root"] = "00" * 32
        self.assertFalse(verify_root_attestation(att)["valid"])

    def test_key_pinning(self) -> None:
        att = export_root_attestation(chain_receipts([_trace(1)]))
        self.assertFalse(verify_root_attestation(att, expected_public_key="dead")["valid"])
        self.assertTrue(
            verify_root_attestation(att, expected_public_key=att["public_key"])["valid"]
        )

    def test_deterministic_signature(self) -> None:
        a = export_root_attestation(chain_receipts([_trace(1), _trace(2)]))
        b = export_root_attestation(chain_receipts([_trace(1), _trace(2)]))
        self.assertEqual(a["signature"], b["signature"])

    def test_selective_disclosure_end_to_end(self) -> None:
        # Issuer side: full batch -> signed root attestation + one inclusion proof.
        receipts = chain_receipts([_trace(i) for i in range(1, 8)])
        att = export_root_attestation(receipts)
        proof = inclusion_proof(receipts, 3)

        # Auditor side: holds ONLY the signed attestation + the single proof.
        # (1) the root is authentic (signature over {chain_head,count,merkle_root})
        self.assertTrue(verify_root_attestation(att)["valid"])
        # (2) the disclosed leaf is committed under that exact root
        self.assertTrue(verify_inclusion(proof["leaf"], proof["path"], att["merkle_root"]))
        # The auditor never received the other 6 receipts.
        self.assertNotIn("receipts", att)


if __name__ == "__main__":
    unittest.main()
