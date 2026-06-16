"""GET /discovery/check runs the discovery recette and returns per-repo detail.

Proves the endpoint the console "Check discovery" button calls: discovery detects
each agent's SOURCE form (corpus/repos) and reports it in detail. Deterministic.
"""

from __future__ import annotations

import unittest

try:
    from fastapi.testclient import TestClient

    from recette.api.app import create_app

    _HAS_FASTAPI = True
except ImportError:  # pragma: no cover - only without the [api] extra
    _HAS_FASTAPI = False


@unittest.skipUnless(_HAS_FASTAPI, "requires the [api] extra (fastapi)")
class TestDiscoveryCheck(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(create_app())

    def test_check_reports_pr_bot_detected_in_detail(self) -> None:
        resp = self.client.get("/discovery/check")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIn("repos", body)
        by_repo = {r["repo"]: r for r in body["repos"]}
        self.assertIn("gh-pr-bot", by_repo)
        self.assertTrue(by_repo["gh-pr-bot"]["detected"])
        self.assertTrue(by_repo["gh-pr-bot"]["passed"])
        # the aggregate fields the UI shows are present
        for key in ("all_passed", "total", "passed", "ordering_ok"):
            self.assertIn(key, body)


if __name__ == "__main__":
    unittest.main()
