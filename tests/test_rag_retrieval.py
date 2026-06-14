"""Retrieval-infra (P3) tests. Deterministic, offline."""

from __future__ import annotations

import unittest

from recette.rag import DeterministicRagBackend, Document
from recette.rag_retrieval import retrieve_context

CORPUS = [
    Document("d1", "cats and dogs"),
    Document("d2", "dogs run fast"),
    Document("d3", "quantum physics"),
]


class TestRetrieveContext(unittest.TestCase):
    def _backend(self) -> DeterministicRagBackend:
        return DeterministicRagBackend(CORPUS)

    def test_block_lists_ranked_docs(self) -> None:
        ctx = retrieve_context(self._backend(), "dogs run", k=3)
        self.assertEqual([d.doc_id for d in ctx.docs], ["d2", "d1"])
        self.assertIn("retrieved 2 document(s) for: dogs run", ctx.text)
        self.assertIn("(d2) dogs run fast", ctx.text)
        self.assertIn("(d1) cats and dogs", ctx.text)

    def test_empty_retrieval_is_explicit(self) -> None:
        ctx = retrieve_context(self._backend(), "unrelated terms", k=3)
        self.assertEqual(ctx.docs, ())
        self.assertEqual(ctx.text, "[retrieved 0 documents for: unrelated terms]")

    def test_hash_is_stable_across_runs(self) -> None:
        a = retrieve_context(self._backend(), "dogs run", k=3)
        b = retrieve_context(self._backend(), "dogs run", k=3)
        self.assertEqual(a.context_hash, b.context_hash)
        self.assertEqual(len(a.context_hash), 16)

    def test_hash_changes_with_content(self) -> None:
        a = retrieve_context(self._backend(), "dogs", k=3)
        b = retrieve_context(self._backend(), "quantum", k=3)
        self.assertNotEqual(a.context_hash, b.context_hash)

    def test_k_limits_block(self) -> None:
        ctx = retrieve_context(self._backend(), "dogs run fast", k=1)
        self.assertEqual(len(ctx.docs), 1)


if __name__ == "__main__":
    unittest.main()
