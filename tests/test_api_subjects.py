"""The unified /subjects API exposes both families (git + MAF) and the aggregate
scorecard, so the console renders one corpus and one verdict after the fusion."""

from __future__ import annotations

import unittest

try:
    from fastapi.testclient import TestClient

    from recette.api.app import create_app

    _HAS_FASTAPI = True
except ImportError:  # pragma: no cover
    _HAS_FASTAPI = False


@unittest.skipUnless(_HAS_FASTAPI, "requires the [api] extra (fastapi)")
class TestSubjectsApi(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(create_app())

    def test_lists_both_families(self) -> None:
        body = self.client.get("/subjects").json()
        self.assertGreater(body["count"], 0)
        self.assertIn("git_agent", body["families"])
        self.assertIn("maf_agent", body["families"])
        self.assertIn("maf_orchestration", body["families"])
        families = {s["family"] for s in body["subjects"]}
        self.assertEqual(families, {"git_agent", "maf_agent", "maf_orchestration"})

    def test_maf_subject_carries_target_and_ground_truth(self) -> None:
        body = self.client.get("/subjects").json()
        maf = next(s for s in body["subjects"] if s["family"] == "maf_agent")
        self.assertTrue(maf["target_systems"])
        self.assertIn(maf["category"], ("correct", "incorrect"))

    def test_scorecard_aggregates_identification_and_maf(self) -> None:
        body = self.client.get("/subjects/scorecard").json()
        self.assertIn("identification", body)
        self.assertIn("maf", body)
        self.assertGreater(body["maf"]["agents"], 0)
        self.assertTrue(body["all_passed"])


if __name__ == "__main__":
    unittest.main()
