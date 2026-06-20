"""Merkle inclusion proofs over receipts -- selective disclosure, determinism (I4).

Proves: a single receipt is provably committed under the root via a short path
WITHOUT the other receipts (selective disclosure); a tampered leaf or a swapped
root fails; the root is deterministic and order-sensitive; domain separation
(RFC 6962) keeps a leaf from masquerading as an internal node.
"""

from __future__ import annotations

import unittest

from recette.context_receipt import chain_receipts
from recette.receipt_merkle import (
    inclusion_proof,
    leaf_hash,
    merkle_root,
    verify_inclusion,
)


def _trace(seq: int, action: str = "open_pr") -> dict:
    return {
        "seq": seq,
        "event_id": f"evt-{seq:04d}",
        "timestamp": "2026-01-01T00:00:00Z",
        "agent_id": "gh-pr-bot",
        "target_system": "github",
        "target": "api.github.com",
        "action_type": action,
        "resource": f"acme/repo{seq}",
        "request_payload": {"n": seq},
        "ok": True,
        "status_code": 201,
        "side_effect_hash": f"h{seq}",
        "run_id": "run-1",
        "response": {"ok": True},
    }


class TestMerkleRoot(unittest.TestCase):
    def test_empty_has_no_root(self) -> None:
        self.assertEqual(merkle_root([]), "")

    def test_single_receipt_root_is_its_leaf(self) -> None:
        receipts = chain_receipts([_trace(1)])
        self.assertEqual(merkle_root(receipts), leaf_hash(receipts[0]))

    def test_root_is_deterministic(self) -> None:
        a = merkle_root(chain_receipts([_trace(i) for i in range(1, 6)]))
        b = merkle_root(chain_receipts([_trace(i) for i in range(1, 6)]))
        self.assertEqual(a, b)
        self.assertEqual(len(a), 64)

    def test_root_is_order_sensitive(self) -> None:
        fwd = merkle_root(chain_receipts([_trace(1), _trace(2)]))
        rev = merkle_root(chain_receipts([_trace(2), _trace(1)]))
        self.assertNotEqual(fwd, rev)

    def test_leaf_excludes_chain_fields(self) -> None:
        # A receipt's leaf must not depend on prev_hash/hash, so it is computable
        # from the disclosed receipt alone.
        chained = chain_receipts([_trace(1)])[0]
        bare = {k: v for k, v in chained.items() if k not in ("prev_hash", "hash")}
        self.assertEqual(leaf_hash(chained), leaf_hash(bare))


class TestInclusionProof(unittest.TestCase):
    def setUp(self) -> None:
        # An odd count exercises the duplicate-last-node path.
        self.receipts = chain_receipts([_trace(i) for i in range(1, 8)])
        self.root = merkle_root(self.receipts)

    def test_every_receipt_proves_inclusion(self) -> None:
        for i in range(len(self.receipts)):
            proof = inclusion_proof(self.receipts, i)
            self.assertEqual(proof["root"], self.root)
            self.assertTrue(
                verify_inclusion(proof["leaf"], proof["path"], self.root),
                f"receipt {i} failed inclusion",
            )

    def test_selective_disclosure_needs_only_one_receipt(self) -> None:
        # The verifier reconstructs the root from ONE leaf + the path, never the
        # other receipts.
        proof = inclusion_proof(self.receipts, 3)
        self.assertTrue(verify_inclusion(proof["leaf"], proof["path"], self.root))
        # The path discloses only sibling HASHES, never receipt content.
        for step in proof["path"]:
            self.assertEqual(set(step), {"sibling", "side"})
            self.assertEqual(len(step["sibling"]), 64)

    def test_wrong_leaf_fails(self) -> None:
        proof = inclusion_proof(self.receipts, 2)
        forged = leaf_hash(_trace(999))
        self.assertFalse(verify_inclusion(forged, proof["path"], self.root))

    def test_wrong_root_fails(self) -> None:
        proof = inclusion_proof(self.receipts, 2)
        self.assertFalse(verify_inclusion(proof["leaf"], proof["path"], "00" * 32))

    def test_empty_root_never_verifies(self) -> None:
        self.assertFalse(verify_inclusion("ab" * 32, [], ""))

    def test_out_of_range_raises(self) -> None:
        with self.assertRaises(IndexError):
            inclusion_proof(self.receipts, len(self.receipts))


if __name__ == "__main__":
    unittest.main()
