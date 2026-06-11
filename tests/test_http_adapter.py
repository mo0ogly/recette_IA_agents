"""Tests for HttpSourceScanAdapter using a stubbed transport (no real network)."""

from __future__ import annotations

import unittest

from recette.adapters import DiscoveryRisk, SourceScanAdapter
from recette.http_adapter import HttpSourceScanAdapter


class _Resp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _StubClient:
    """Canned :8081 responses; records calls."""

    def __init__(self):
        self.calls = []

    def post(self, path, json=None):
        self.calls.append(("POST", path, json))
        if path == "/v1/sources":
            return _Resp({"success": True, "data": {"source_id": "S1"}})
        if path.endswith("/scan"):
            return _Resp({"success": True, "data": {"run_id": "R1"}})
        raise AssertionError(f"unexpected POST {path}")

    def get(self, path):
        self.calls.append(("GET", path, None))
        if path.startswith("/v1/scan-runs/"):
            return _Resp({"success": True, "data": {"status": "completed"}})
        if path.endswith("/risks"):
            return _Resp(
                {
                    "success": True,
                    "data": [
                        {
                            "canonical_agent_id": "deadbeef",
                            "action_pattern": "open_pr",
                            "target_system": "github",
                            "estimated_risk": {"level": 2},
                            "generated_policy": "package agentrail",
                        }
                    ],
                }
            )
        raise AssertionError(f"unexpected GET {path}")


class TestHttpAdapter(unittest.TestCase):
    def setUp(self):
        self.stub = _StubClient()
        self.adapter = HttpSourceScanAdapter(
            base_url="http://x:8081", tenant="acme", token="t", client=self.stub
        )

    def test_satisfies_protocol(self):
        self.assertIsInstance(self.adapter, SourceScanAdapter)

    def test_full_round_trip_parses_into_discovery_risk(self):
        sid = self.adapter.register("https://github.com/acme/pr-bot")
        self.assertEqual(sid, "S1")
        run = self.adapter.scan(sid)
        self.assertEqual(run, "R1")
        self.assertEqual(self.adapter.await_run(run), "completed")
        risks = self.adapter.risks(sid)
        self.assertEqual(len(risks), 1)
        self.assertIsInstance(risks[0], DiscoveryRisk)
        self.assertEqual(risks[0].action_pattern, "open_pr")
        self.assertEqual(risks[0].estimated_risk, {"level": 2})

    def test_envelope_is_unwrapped(self):
        sid = self.adapter.register("loc")
        # If the {success,data} envelope were not unwrapped, source_id would not be "S1".
        self.assertEqual(sid, "S1")

    def test_register_sends_github_adapter_and_tenant(self):
        self.adapter.register("loc")
        post = next(c for c in self.stub.calls if c[0] == "POST" and c[1] == "/v1/sources")
        self.assertEqual(post[2]["adapter"], "github")
        self.assertEqual(post[2]["tenant_id"], "acme")


if __name__ == "__main__":
    unittest.main()
