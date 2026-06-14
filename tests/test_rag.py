"""RAG backend tests. Offline -- the real backend is driven by a stub client."""

from __future__ import annotations

import os
import unittest

from recette.rag import (
    DeterministicRagBackend,
    Document,
    RealRagBackend,
    RetrievedDoc,
    build_rag,
)

CORPUS = [
    Document("d1", "cats and dogs"),
    Document("d2", "dogs run fast"),
    Document("d3", "quantum physics"),
]


class TestRetrievedDoc(unittest.TestCase):
    def test_is_frozen_record(self) -> None:
        d = RetrievedDoc(doc_id="d1", score=2, text="hello")
        self.assertEqual((d.doc_id, d.score, d.text), ("d1", 2, "hello"))


class TestDeterministicRagBackend(unittest.TestCase):
    def test_index_returns_count(self) -> None:
        rag = DeterministicRagBackend()
        self.assertEqual(rag.index(CORPUS), 3)

    def test_retrieve_ranks_by_token_overlap(self) -> None:
        rag = DeterministicRagBackend(CORPUS)
        top = rag.retrieve("dogs run", k=3)
        # d2 has both query tokens (score 2), d1 has one (score 1), d3 none.
        self.assertEqual([d.doc_id for d in top], ["d2", "d1"])
        self.assertEqual([d.score for d in top], [2, 1])

    def test_zero_overlap_docs_are_excluded(self) -> None:
        rag = DeterministicRagBackend(CORPUS)
        self.assertEqual(rag.retrieve("quantum", k=3), [RetrievedDoc("d3", 1, "quantum physics")])

    def test_tie_break_is_stable_by_doc_id(self) -> None:
        rag = DeterministicRagBackend(CORPUS)
        # "dogs" matches d1 and d2 with equal score 1; order must be by doc_id.
        self.assertEqual([d.doc_id for d in rag.retrieve("dogs", k=2)], ["d1", "d2"])

    def test_retrieve_is_deterministic_across_runs(self) -> None:
        rag = DeterministicRagBackend(CORPUS)
        self.assertEqual(rag.retrieve("dogs run", k=3), rag.retrieve("dogs run", k=3))

    def test_k_limits_results(self) -> None:
        rag = DeterministicRagBackend(CORPUS)
        self.assertEqual(len(rag.retrieve("dogs run fast", k=1)), 1)


class _StubResponse:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        pass

    def json(self) -> dict:
        return self._payload


class _StubEmbedClient:
    """Deterministic embeddings: a fixed vector per input text."""

    def __init__(self, table: dict[str, list[float]]) -> None:
        self._table = table

    def post(self, path: str, json: dict | None = None) -> _StubResponse:
        assert json is not None
        vec = self._table.get(json["input"], [0.0])
        return _StubResponse({"data": [{"embedding": vec}]})


class TestRealRagBackend(unittest.TestCase):
    def test_missing_key_raises_runtimeerror_naming_env_var(self) -> None:
        old = os.environ.pop("RAG_EMBEDDINGS_API_KEY", None)
        try:
            with self.assertRaises(RuntimeError) as ctx:
                RealRagBackend(model="text-embedding-3-small")
            self.assertIn("RAG_EMBEDDINGS_API_KEY", str(ctx.exception))
        finally:
            if old is not None:
                os.environ["RAG_EMBEDDINGS_API_KEY"] = old

    def test_api_key_skips_env_requirement(self) -> None:
        old = os.environ.pop("RAG_EMBEDDINGS_API_KEY", None)
        try:
            rag = RealRagBackend(model="m", api_key="sk-test")
            self.assertEqual(rag._client.headers["Authorization"], "Bearer sk-test")
        finally:
            if old is not None:
                os.environ["RAG_EMBEDDINGS_API_KEY"] = old

    def test_retrieve_ranks_by_cosine_via_stub(self) -> None:
        table = {
            "x": [1.0, 0.0],
            "y": [0.0, 1.0],
            "query": [1.0, 0.0],
        }
        rag = RealRagBackend(model="m", client=_StubEmbedClient(table))
        rag.index([Document("d1", "x"), Document("d2", "y")])
        top = rag.retrieve("query", k=2)
        self.assertEqual([d.doc_id for d in top], ["d1", "d2"])
        self.assertEqual(top[0].score, 1000)  # cosine 1.0 -> int 1000
        self.assertEqual(top[1].score, 0)

    def test_retrieve_is_deterministic_across_runs(self) -> None:
        table = {"x": [1.0, 0.0], "query": [0.7, 0.7]}
        rag = RealRagBackend(model="m", client=_StubEmbedClient(table))
        rag.index([Document("d1", "x")])
        self.assertEqual(rag.retrieve("query", k=1), rag.retrieve("query", k=1))


class TestBuildRag(unittest.TestCase):
    def test_build_deterministic(self) -> None:
        rag = build_rag("deterministic", corpus=CORPUS)
        self.assertIsInstance(rag, DeterministicRagBackend)
        self.assertEqual([d.doc_id for d in rag.retrieve("dogs", k=1)], ["d1"])

    def test_build_real_threads_client(self) -> None:
        rag = build_rag("real", model="m", client=_StubEmbedClient({}))
        self.assertIsInstance(rag, RealRagBackend)

    def test_build_real_without_model_or_client_raises(self) -> None:
        with self.assertRaises(ValueError):
            build_rag("real")

    def test_build_unknown_raises(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            build_rag("bogus")
        self.assertIn("deterministic", str(ctx.exception))
        self.assertIn("real", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
