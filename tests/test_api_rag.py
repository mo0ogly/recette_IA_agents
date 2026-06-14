"""GET /rag/scorecard: the RAG retrieval-quality recette endpoint."""

from __future__ import annotations

import unittest

try:
    from fastapi.testclient import TestClient

    from recette.api.app import create_app

    _HAS_FASTAPI = True
except ImportError:  # pragma: no cover
    _HAS_FASTAPI = False


@unittest.skipUnless(_HAS_FASTAPI, "requires the [api] extra (fastapi)")
class TestRagScorecard(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(create_app())

    def test_scorecard_shape_and_pass(self) -> None:
        body = self.client.get("/rag/scorecard").json()
        self.assertEqual(self.client.get("/rag/scorecard").status_code, 200)
        self.assertIn("total", body)
        self.assertIn("results", body)
        self.assertEqual(body["passed"], body["total"])
        self.assertTrue(body["all_passed"])
        for row in body["results"]:
            self.assertIn("query", row)
            self.assertIn("retrieved", row)
            self.assertTrue(row["passed"])

    def test_deterministic_across_calls(self) -> None:
        a = self.client.get("/rag/scorecard").json()
        b = self.client.get("/rag/scorecard").json()
        self.assertEqual(a, b)


if __name__ == "__main__":
    unittest.main()
