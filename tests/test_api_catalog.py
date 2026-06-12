"""U1: GET /agents catalog reuses the harness corpus discovery."""

from __future__ import annotations

import unittest

try:
    from fastapi.testclient import TestClient

    from recette.api.app import create_app

    _HAS_FASTAPI = True
except ImportError:  # pragma: no cover
    _HAS_FASTAPI = False


@unittest.skipUnless(_HAS_FASTAPI, "requires the [api] extra (fastapi)")
class TestCatalog(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(create_app())

    def test_catalog_lists_corpus(self) -> None:
        body = self.client.get("/agents").json()
        ident_ids = {a["agent_id"] for a in body["identification"]}
        # known Lane A golden from corpus/agents/correct
        self.assertIn("gh-issue-triager", ident_ids)
        # discovery surfaces include github with the readonly-reporter repo slug
        self.assertIn("github", body["discovery"])
        self.assertIn("gh-readonly-reporter", body["discovery"]["github"])
        self.assertIn("lane_b", body)
