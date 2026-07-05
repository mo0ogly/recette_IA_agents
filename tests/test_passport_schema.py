"""Schema tests for the Contrat-3 signed agent passport artifact.

Two schemas are exercised here:

* ``agent-passport.schema.json`` -- the signed ``.inspect_ia_agents/passport.json``
  artifact (frozen attestation): a valid passport validates, and each of the
  frozen constraints (required signature, exact 128-hex signature, no extra
  fields, non-empty delegation) rejects a malformed passport.
* ``discovery-ground-truth.schema.json`` -- the additive ``attestation_status``
  axis (the SIGNED passport.json axis, distinct from the manifest-level
  ``passport_status`` axis).
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

import jsonschema

REPO = Path(__file__).resolve().parent.parent
SCHEMAS = REPO / "corpus" / "schemas"
PASSPORT_SCHEMA = SCHEMAS / "agent-passport.schema.json"
GROUND_TRUTH_SCHEMA = SCHEMAS / "discovery-ground-truth.schema.json"

# A realistic, fully-populated Contrat-3 passport. The signature is a
# real-shaped 64-byte Ed25519 value (exactly 128 lowercase hex chars); the
# delegation chain ends at a human principal; ``exp`` is RFC3339. Kept in sync
# with the Rust reference in discoveryprobe/agent-passport/src/lib.rs.
VALID_PASSPORT = {
    "id": "agent:invoice-reconciler-7",
    "tenant": "acme-finance",
    "delegation": [
        "agent:invoice-reconciler-7",
        "service:reconciliation-orchestrator",
        "human:cfo.jdupont@acme.example",
    ],
    "scope": ["read_ledger", "post_journal_entry", "open_pr"],
    "exp": "2026-12-31T23:59:59Z",
    "spiffe_id": "spiffe://acme.example/ns/finance/sa/invoice-reconciler",
    "signature": (
        "3d4f8a1c9b2e7f6058a1c4d2e9f0b8a7561d3c2b4e5f6a7089c1d2e3f4a5b6c7"
        "d8e9f0a1b2c3d4e5f60718293a4b5c6d7e8f90a1b2c3d4e5f6071829304a5b6c"
    ),
    "key_id": "ed25519:acme-issuer-2026-q3",
}


def _passport_schema() -> dict:
    return json.loads(PASSPORT_SCHEMA.read_text(encoding="utf-8"))


def _ground_truth_schema() -> dict:
    return json.loads(GROUND_TRUTH_SCHEMA.read_text(encoding="utf-8"))


class TestAgentPassportSchema(unittest.TestCase):
    def test_schema_is_itself_valid(self):
        jsonschema.Draft202012Validator.check_schema(_passport_schema())

    def test_valid_contrat3_passport_validates(self):
        self.assertEqual(len(VALID_PASSPORT["signature"]), 128)
        jsonschema.Draft202012Validator(_passport_schema()).validate(VALID_PASSPORT)

    def test_valid_passport_without_optional_spiffe_id_validates(self):
        doc = dict(VALID_PASSPORT)
        del doc["spiffe_id"]
        jsonschema.Draft202012Validator(_passport_schema()).validate(doc)

    def test_passport_missing_signature_is_invalid(self):
        doc = dict(VALID_PASSPORT)
        del doc["signature"]
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.Draft202012Validator(_passport_schema()).validate(doc)

    def test_passport_with_127_char_signature_is_invalid(self):
        doc = dict(VALID_PASSPORT)
        doc["signature"] = VALID_PASSPORT["signature"][:-1]  # 127 chars
        self.assertEqual(len(doc["signature"]), 127)
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.Draft202012Validator(_passport_schema()).validate(doc)

    def test_passport_with_129_char_signature_is_invalid(self):
        doc = dict(VALID_PASSPORT)
        doc["signature"] = VALID_PASSPORT["signature"] + "a"  # 129 chars
        self.assertEqual(len(doc["signature"]), 129)
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.Draft202012Validator(_passport_schema()).validate(doc)

    def test_passport_with_uppercase_hex_signature_is_invalid(self):
        doc = dict(VALID_PASSPORT)
        doc["signature"] = VALID_PASSPORT["signature"].upper()
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.Draft202012Validator(_passport_schema()).validate(doc)

    def test_passport_with_extra_field_is_invalid(self):
        doc = dict(VALID_PASSPORT)
        doc["elevated"] = True
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.Draft202012Validator(_passport_schema()).validate(doc)

    def test_passport_with_empty_delegation_is_invalid(self):
        doc = dict(VALID_PASSPORT)
        doc["delegation"] = []
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.Draft202012Validator(_passport_schema()).validate(doc)


class TestAttestationStatusGroundTruth(unittest.TestCase):
    def test_ground_truth_schema_is_still_valid(self):
        jsonschema.Draft202012Validator.check_schema(_ground_truth_schema())

    def test_ground_truth_with_attestation_status_untrusted_validates(self):
        doc = {
            "agent_repo": "gh-untrusted-passport",
            "target_system": "github",
            "detected": True,
            "attestation_status": "untrusted",
        }
        jsonschema.Draft202012Validator(_ground_truth_schema()).validate(doc)

    def test_ground_truth_accepts_every_attestation_status_value(self):
        for value in ("trusted", "untrusted", "unsigned", "malformed"):
            with self.subTest(attestation_status=value):
                doc = {
                    "agent_repo": "gh-attested",
                    "target_system": "github",
                    "detected": True,
                    "attestation_status": value,
                }
                jsonschema.Draft202012Validator(_ground_truth_schema()).validate(doc)

    def test_ground_truth_with_bogus_attestation_status_is_invalid(self):
        doc = {
            "agent_repo": "gh-bad",
            "target_system": "github",
            "detected": True,
            "attestation_status": "bogus",
        }
        with self.assertRaises(jsonschema.ValidationError):
            jsonschema.Draft202012Validator(_ground_truth_schema()).validate(doc)


if __name__ == "__main__":
    unittest.main()
