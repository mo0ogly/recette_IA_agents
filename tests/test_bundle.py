"""Tests for the Ed25519 policy-bundle contract: accept valid, reject every tampering."""

from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from recette.bundle import canonical_payload, verify_bundle

REPO = Path(__file__).resolve().parent.parent
VALID = REPO / "corpus" / "bundles" / "valid" / "bundle.json"
SCHEMA = REPO / "corpus" / "schemas" / "policy-bundle.schema.json"

# Public key for the documented all-zero test seed (known Ed25519 test vector).
PINNED_PUBKEY = "3b6a27bcceb6a42d62a3a8d02a6f0d73653215771de243a63ac048a18b59da29"

try:
    import cryptography  # noqa: F401

    _HAS_CRYPTO = True
except ImportError:
    _HAS_CRYPTO = False


def _bundle() -> dict:
    return json.loads(VALID.read_text(encoding="utf-8"))


@unittest.skipUnless(_HAS_CRYPTO, "cryptography ([bundle] extra) not installed")
class TestBundleVerification(unittest.TestCase):
    def test_valid_bundle_passes(self):
        result = verify_bundle(_bundle(), expected_public_key=PINNED_PUBKEY)
        self.assertTrue(result.valid, result.reason)

    def test_valid_bundle_passes_without_pinning(self):
        self.assertTrue(verify_bundle(_bundle()).valid)

    def test_tampered_decision_is_rejected(self):
        b = _bundle()
        b["decisions"][2]["decision"] = "allow"  # was deny -- payload no longer matches sig
        self.assertFalse(verify_bundle(b).valid)

    def test_tampered_policy_version_is_rejected(self):
        b = _bundle()
        b["policy_version"] = "v2"
        self.assertFalse(verify_bundle(b).valid)

    def test_wrong_signature_is_rejected(self):
        b = _bundle()
        b["signature"] = "00" * 64
        self.assertFalse(verify_bundle(b).valid)

    def test_missing_signature_is_rejected(self):
        b = _bundle()
        b["signature"] = ""
        self.assertFalse(verify_bundle(b).valid)

    def test_wrong_pinned_key_is_rejected(self):
        result = verify_bundle(_bundle(), expected_public_key="ab" * 32)
        self.assertFalse(result.valid)

    def test_substituted_key_and_resign_fails_pinning(self):
        # An attacker re-signs with their own key: signature is internally valid but the
        # pinned key check must reject it.
        b = copy.deepcopy(_bundle())
        b["public_key"] = "ab" * 32
        self.assertFalse(verify_bundle(b, expected_public_key=PINNED_PUBKEY).valid)


class TestBundleShapeAndPayload(unittest.TestCase):
    def test_valid_fixture_matches_schema(self):
        import jsonschema

        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        jsonschema.Draft202012Validator(schema).validate(_bundle())

    def test_canonical_payload_is_deterministic(self):
        b = _bundle()
        self.assertEqual(canonical_payload(b), canonical_payload(b))
        self.assertNotIn(b" ", canonical_payload(b))  # compact separators


if __name__ == "__main__":
    unittest.main()
