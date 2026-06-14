"""RAG retrieval-quality recette tests. Deterministic, offline."""

from __future__ import annotations

import unittest

from recette.rag import DeterministicRagBackend, Document
from recette.rag_eval import (
    RagQueryTruth,
    ReferenceRagAdapter,
    judge_rag,
)

CORPUS = [
    Document("d1", "cats and dogs"),
    Document("d2", "dogs run fast"),
    Document("d3", "quantum physics"),
]


def _reference() -> ReferenceRagAdapter:
    return ReferenceRagAdapter(DeterministicRagBackend(CORPUS))


class _FixedAdapter:
    """An adapter returning a canned ranking, to drive FAIL paths."""

    def __init__(self, ranking: list[str]) -> None:
        self._ranking = ranking

    def retrieve(self, query: str, *, k: int) -> list[str]:
        return self._ranking[:k]


class TestReferenceRagAdapter(unittest.TestCase):
    def test_returns_ranked_doc_ids(self) -> None:
        adapter = _reference()
        self.assertEqual(adapter.retrieve("dogs run", k=3), ["d2", "d1"])


class TestJudgeRag(unittest.TestCase):
    def test_reference_passes_its_own_ground_truth(self) -> None:
        truths = [
            RagQueryTruth(query="dogs run", relevant_ids=("d1", "d2"), top_id="d2"),
            RagQueryTruth(query="quantum", relevant_ids=("d3",), top_id="d3"),
        ]
        card = judge_rag(_reference(), truths, k=3)
        self.assertTrue(card.all_passed)
        self.assertEqual(card.passed_count, 2)
        self.assertEqual(card.mean_recall, 1.0)

    def test_missing_relevant_doc_fails_on_recall(self) -> None:
        # Adapter never returns d2, but ground truth needs it.
        card = judge_rag(
            _FixedAdapter(["d1", "d3"]),
            [RagQueryTruth(query="dogs", relevant_ids=("d1", "d2"))],
            k=3,
        )
        self.assertFalse(card.all_passed)
        res = card.results[0]
        self.assertEqual(res.recall, 0.5)
        self.assertFalse(res.passed)

    def test_wrong_top_doc_fails_even_with_full_recall(self) -> None:
        # Both relevant docs present, but the required top doc is not first.
        card = judge_rag(
            _FixedAdapter(["d1", "d2"]),
            [RagQueryTruth(query="dogs run", relevant_ids=("d1", "d2"), top_id="d2")],
            k=3,
        )
        res = card.results[0]
        self.assertEqual(res.recall, 1.0)
        self.assertFalse(res.top_ok)
        self.assertFalse(res.passed)

    def test_top_id_none_does_not_judge_order(self) -> None:
        card = judge_rag(
            _FixedAdapter(["d1", "d2"]),
            [RagQueryTruth(query="dogs run", relevant_ids=("d1", "d2"))],
            k=3,
        )
        self.assertTrue(card.all_passed)

    def test_precision_reflects_noise(self) -> None:
        # One relevant (d1) out of two returned -> precision 0.5.
        card = judge_rag(
            _FixedAdapter(["d1", "d3"]),
            [RagQueryTruth(query="dogs", relevant_ids=("d1",))],
            k=3,
        )
        self.assertEqual(card.results[0].precision, 0.5)
        self.assertTrue(card.results[0].passed)  # full recall, no top constraint

    def test_render_lists_each_query_verdict(self) -> None:
        card = judge_rag(
            _reference(),
            [RagQueryTruth(query="quantum", relevant_ids=("d3",))],
            k=3,
        )
        text = card.render()
        self.assertIn("RAG retrieval recette", text)
        self.assertIn("PASS", text)
        self.assertIn("quantum", text)

    def test_is_deterministic_across_runs(self) -> None:
        truths = [RagQueryTruth(query="dogs run", relevant_ids=("d1", "d2"), top_id="d2")]
        a = judge_rag(_reference(), truths, k=3)
        b = judge_rag(_reference(), truths, k=3)
        self.assertEqual(a.results, b.results)


if __name__ == "__main__":
    unittest.main()
