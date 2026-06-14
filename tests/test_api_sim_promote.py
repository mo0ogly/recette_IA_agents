"""POST /sim/scenarios/{id}/promote -- freeze a caught anomaly into a subject.

Requires fastapi (venv only): run with ``.venv/bin/python -m unittest
tests.test_api_sim_promote``. The success path monkeypatches the router's
``promote_scenario`` symbol to force a tmp ``out_root`` so the REAL corpus under
``corpus/agents/`` is never polluted. The error-mapping paths hit the real
function -- a true-negative scenario and a multi-axis run map to 422, an unknown
id to 404; all of these raise BEFORE any file write, so they never touch disk.
"""

from __future__ import annotations

import functools
import tempfile
import unittest
from pathlib import Path

try:
    from fastapi.testclient import TestClient

    import recette.api.routers.sim as sim_router
    from recette.api.app import create_app
    from recette.redteam_promote import promote_scenario as real_promote

    _HAVE_FASTAPI = True
except ImportError:
    _HAVE_FASTAPI = False


@unittest.skipUnless(_HAVE_FASTAPI, "fastapi not installed")
class PromoteEndpointTests(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(create_app())

    def test_promote_caught_maf_anomaly_returns_200(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            # Force out_root to a tmp dir so the real corpus is never written.
            forced = functools.partial(real_promote, out_root=tmp)

            def patched(scenario_id, *, overwrite=False):
                return forced(scenario_id, overwrite=overwrite)

            original = sim_router.promote_scenario
            sim_router.promote_scenario = patched
            try:
                r = self.client.post("/sim/scenarios/rt-diagnostic-overreach/promote")
            finally:
                sim_router.promote_scenario = original

            self.assertEqual(r.status_code, 200)
            body = r.json()
            self.assertEqual(body["slug"], "rt-diagnostic-overreach")
            self.assertEqual(body["verdict"], "incorrect")
            self.assertEqual(body["violation_type"], "capability_overreach")
            self.assertEqual(len(body["created"]), 3)
            for path in body["created"]:
                self.assertTrue(Path(path).is_file())
                self.assertTrue(str(path).startswith(tmp))

    def test_correct_scenario_maps_to_422(self) -> None:
        # A true-negative scenario raises ValueError("nothing to promote") BEFORE
        # any write -> 422. Hits the real promote_scenario (no monkeypatch needed,
        # it never touches disk on this path).
        r = self.client.post("/sim/scenarios/rt-diagnostic-resisted/promote")
        self.assertEqual(r.status_code, 422)
        self.assertIn("nothing to promote", r.json()["detail"])

    def test_multi_axis_git_scenario_maps_to_422(self) -> None:
        # The two-axis git overreach scenario cannot be frozen single-axis ->
        # ValueError raised before any write -> 422.
        r = self.client.post("/sim/scenarios/rt-prbot-overreach/promote")
        self.assertEqual(r.status_code, 422)
        self.assertIn("single-axis", r.json()["detail"])

    def test_unknown_scenario_maps_to_404(self) -> None:
        r = self.client.post("/sim/scenarios/does-not-exist/promote")
        self.assertEqual(r.status_code, 404)
        self.assertIn("unknown scenario id", r.json()["detail"])


if __name__ == "__main__":
    unittest.main()
