"""CLI: python -m recette receipts-attest --attestation A --proof P.

Selective-disclosure verifier: a signed root attestation + ONE inclusion proof
attest that a single side effect crossed the boundary, WITHOUT the other
receipts. Exit 0 only when the root signature is valid, the proof folds to a
root, and that root equals the attested merkle_root. Pure (I4), offline.
"""

from __future__ import annotations

import json
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from recette.__main__ import main
from recette.context_receipt import chain_receipts
from recette.receipt_export import SIGNING_KEY_ENV, export_root_attestation
from recette.receipt_merkle import inclusion_proof

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


@unittest.skipUnless(_HAVE_CRYPTO, "cryptography ([bundle] extra) not installed")
class TestReceiptsAttestCli(unittest.TestCase):
    def setUp(self) -> None:
        self._saved = os.environ.get(SIGNING_KEY_ENV)
        os.environ[SIGNING_KEY_ENV] = _SEED
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name)
        receipts = chain_receipts([_trace(i) for i in range(1, 8)])
        self.att_path = self.dir / "att.json"
        self.proof_path = self.dir / "proof.json"
        self.att_path.write_text(json.dumps(export_root_attestation(receipts)), encoding="utf-8")
        self.proof_path.write_text(json.dumps(inclusion_proof(receipts, 3)), encoding="utf-8")

    def tearDown(self) -> None:
        if self._saved is None:
            os.environ.pop(SIGNING_KEY_ENV, None)
        else:
            os.environ[SIGNING_KEY_ENV] = self._saved

    def _run(self, *extra: str) -> int:
        return main(
            [
                "receipts-attest",
                "--attestation",
                str(self.att_path),
                "--proof",
                str(self.proof_path),
            ]
            + list(extra)
        )

    def test_valid_attestation_exit_0(self) -> None:
        self.assertEqual(self._run(), 0)

    def test_json_verdict(self) -> None:
        import contextlib
        import io

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            code = self._run("--json")
        out = json.loads(buf.getvalue())
        self.assertEqual(code, 0)
        self.assertTrue(out["ok"])
        self.assertTrue(out["signature"]["valid"])
        self.assertTrue(out["roots_match"])
        self.assertTrue(out["included"])

    def test_wrong_pubkey_exit_1(self) -> None:
        self.assertEqual(self._run("--pubkey", "deadbeef"), 1)

    def test_tampered_attested_root_exit_1(self) -> None:
        att = json.loads(self.att_path.read_text(encoding="utf-8"))
        att["merkle_root"] = "00" * 32  # breaks both the signature and the root match
        self.att_path.write_text(json.dumps(att), encoding="utf-8")
        self.assertEqual(self._run(), 1)

    def test_proof_for_other_root_exit_1(self) -> None:
        # A valid proof, but against a DIFFERENT root than the attestation commits
        # to -> roots_match false, verdict invalid (proof proves nothing here).
        other = chain_receipts([_trace(i) for i in range(20, 24)])
        self.proof_path.write_text(json.dumps(inclusion_proof(other, 1)), encoding="utf-8")
        self.assertEqual(self._run(), 1)


class TestReceiptsAttestUnsigned(unittest.TestCase):
    def setUp(self) -> None:
        self._saved = os.environ.pop(SIGNING_KEY_ENV, None)

    def tearDown(self) -> None:
        if self._saved is not None:
            os.environ[SIGNING_KEY_ENV] = self._saved

    def test_unsigned_attestation_exit_1(self) -> None:
        tmp = TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        d = Path(tmp.name)
        receipts = chain_receipts([_trace(1), _trace(2)])
        att = d / "att.json"
        proof = d / "proof.json"
        att.write_text(json.dumps(export_root_attestation(receipts)), encoding="utf-8")
        proof.write_text(json.dumps(inclusion_proof(receipts, 0)), encoding="utf-8")
        self.assertEqual(
            main(["receipts-attest", "--attestation", str(att), "--proof", str(proof)]), 1
        )


if __name__ == "__main__":
    unittest.main()
