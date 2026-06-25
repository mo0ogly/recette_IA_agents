"""POST /behavior/wave -- the console runs a behavioral-analysis wave through the
API. The endpoint assembles the evidence bundle from the live registry + each
agent's declared plan, runs the deterministic engine, and returns the report
(+ metrics when ground-truth is supplied). Skipped without the [api] extra.
"""

from __future__ import annotations

import unittest

try:
    from fastapi.testclient import TestClient

    from recette.api.app import create_app
    from recette.api.config_store import ConfigStore

    _HAS_FASTAPI = True
except ImportError:  # pragma: no cover - only without the [api] extra
    _HAS_FASTAPI = False


_RECORDING = {
    "status": "ok",
    "recordings": [
        {
            "agent_id": "leak-bot",
            "surfaces": {
                "ebpf_wire": [
                    "open:/home/bot/.aws/credentials",
                    "connect:8.8.8.8:443",
                ]
            },
        }
    ],
}


@unittest.skipUnless(_HAS_FASTAPI, "requires the [api] extra (fastapi)")
class TestBehaviorWave(unittest.TestCase):
    def setUp(self) -> None:
        app = create_app(config_store=ConfigStore())
        self.client = TestClient(app)

    def test_profile_defaults_lists_lenses_and_threats(self) -> None:
        r = self.client.get("/behavior/profile/defaults")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertIn("credential", body["lenses"])
        self.assertIn("exfil", body["threats"])
        self.assertIn("ghost_host_tolerance", body["default_thresholds"])

    def test_wave_returns_report_with_findings(self) -> None:
        r = self.client.post(
            "/behavior/wave",
            json={"recording": _RECORDING, "profile": {"threat": "exfil"}},
        )
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertIsNone(body["metrics"])  # no ground_truth -> no metrics
        agents = body["report"]["agents"]
        leak = next(a for a in agents if a["agent_id"] == "leak-bot")
        fired = {f["lens"] for f in leak["findings"]}
        self.assertIn("credential", fired)
        self.assertIn("doh", fired)
        self.assertFalse(leak["coherent"])

    def test_wave_with_ground_truth_returns_metrics(self) -> None:
        r = self.client.post(
            "/behavior/wave",
            json={
                "recording": _RECORDING,
                "profile": {"threat": "exfil"},
                "ground_truth": {"leak-bot": {"expected_verdict": "incorrect"}},
            },
        )
        self.assertEqual(r.status_code, 200)
        metrics = r.json()["metrics"]
        self.assertIsNotNone(metrics)
        self.assertEqual(metrics["confusion"]["tp"], 1)

    def test_invalid_profile_is_400(self) -> None:
        r = self.client.post(
            "/behavior/wave",
            json={"recording": _RECORDING, "profile": {"threat": "bogus"}},
        )
        self.assertEqual(r.status_code, 400)

    def test_missing_recording_is_400(self) -> None:
        r = self.client.post("/behavior/wave", json={"profile": {}})
        self.assertEqual(r.status_code, 400)

    def test_correlate_returns_quadrants(self) -> None:
        body = {"recording": _RECORDING, "profile": {"threat": "exfil"}}
        resp = self.client.post("/behavior/correlate", json=body)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("quadrants", data["correlation"])
        self.assertIn("static_blind", data["correlation"]["quadrants"])

    def test_wave_with_discovery_cohort_flagged_echoes_cohort(self) -> None:
        body = {
            "recording": _RECORDING,
            "profile": {"threat": "exfil", "cohort": {"discovery": "flagged"}},
        }
        resp = self.client.post("/behavior/wave", json=body)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["cohort"]["mode"], "flagged")
        self.assertIn("admin-overreach", data["cohort"]["agents"])


if __name__ == "__main__":
    unittest.main()
