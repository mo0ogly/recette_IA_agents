import json
import unittest
from pathlib import Path

try:
    from fastapi.testclient import TestClient

    from recette.api.app import create_app

    _HAVE_FASTAPI = True
except ImportError:
    _HAVE_FASTAPI = False

_SIM_DIR = Path(__file__).resolve().parents[1] / "corpus" / "sim"


@unittest.skipUnless(_HAVE_FASTAPI, "fastapi not installed")
class T(unittest.TestCase):
    def setUp(self):
        self.c = TestClient(create_app())

    def test_scenarios_list_has_verdict_and_caught(self):
        r = self.c.get("/sim/scenarios")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertIn("scenarios", body)
        self.assertIn("count", body)
        self.assertTrue(body["scenarios"], "expected at least one scenario")
        item = body["scenarios"][0]
        for k in (
            "scenario_id",
            "name",
            "verdict",
            "expected_verdict",
            "anomaly_caught",
            "violation_type",
            "tags",
        ):
            self.assertIn(k, item)

    def test_single_scenario_has_transcript(self):
        sid = self.c.get("/sim/scenarios").json()["scenarios"][0]["scenario_id"]
        r = self.c.get(f"/sim/scenarios/{sid}")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["scenario_id"], sid)
        self.assertIn("transcript", body)
        self.assertIn("anomaly_caught", body)

    def test_unknown_scenario_404(self):
        r = self.c.get("/sim/scenarios/does-not-exist")
        self.assertEqual(r.status_code, 404)

    def test_maf_scenarios_carry_family_marker(self):
        body = self.c.get("/sim/scenarios").json()
        self.assertTrue(body["scenarios"])
        for item in body["scenarios"]:
            self.assertEqual(item.get("family"), "maf")

    def test_git_scenarios_list_has_family_and_fields(self):
        r = self.c.get("/sim/git-scenarios")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertIn("scenarios", body)
        self.assertIn("count", body)
        self.assertTrue(body["scenarios"], "expected at least one git scenario")
        item = body["scenarios"][0]
        for k in (
            "scenario_id",
            "name",
            "verdict",
            "expected_verdict",
            "anomaly_caught",
            "violation_type",
            "tags",
            "family",
        ):
            self.assertIn(k, item)
        self.assertEqual(item["family"], "git")

    def test_single_git_scenario_has_transcript_dimensions_action_log(self):
        sid = self.c.get("/sim/git-scenarios").json()["scenarios"][0]["scenario_id"]
        r = self.c.get(f"/sim/git-scenarios/{sid}")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["scenario_id"], sid)
        self.assertIn("dimensions", body)
        for k in ("identity", "capabilities", "policy", "behavior"):
            self.assertIn(k, body["dimensions"])
        self.assertIn("action_log", body)
        self.assertIn("anomaly_caught", body)

    def test_unknown_git_scenario_404(self):
        r = self.c.get("/sim/git-scenarios/does-not-exist")
        self.assertEqual(r.status_code, 404)

    def test_malformed_scenario_file_returns_422_with_detail(self):
        # A scenario file that is valid JSON but fails the schema (no ``expected``)
        # must surface as an explicit 422, not a bare 500 (legibility-first).
        sid = "zzz-temp-invalid-422"
        path = _SIM_DIR / f"{sid}.scenario.json"
        # Guaranteed cleanup, even on an assertion failure below.
        self.addCleanup(path.unlink, missing_ok=True)
        malformed = {
            "scenario_id": sid,
            "name": "temp malformed scenario (missing expected)",
            "strategy": "crescendo",
            "target_spec": {
                "kind": "maf_agent",
                "agent_id": sid,
                "name": "Temp",
                "description": "temp",
                "capability_scope": [],
                "version": "0.1.0",
            },
            "attack": {"user_turns": ["hi"]},
            "subject_program": [{"kind": "final", "text": "ok"}],
            "approver": "deny_all",
            # NOTE: no "expected" -> schema invalid -> run_scenario_view raises ValueError.
        }
        path.write_text(json.dumps(malformed), encoding="utf-8")

        r = self.c.get(f"/sim/scenarios/{sid}")
        self.assertEqual(r.status_code, 422)
        self.assertIn("detail", r.json())
        self.assertIn("expected", r.json()["detail"])


if __name__ == "__main__":
    unittest.main()
