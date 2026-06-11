"""Contract tests for the SourceScanAdapter protocol + DiscoveryRisk dataclass."""

from __future__ import annotations

import unittest

from recette.adapters import DiscoveryRisk, SourceScanAdapter


class FakeAdapter:
    """Minimal in-memory adapter to exercise the protocol shape."""

    def __init__(self):
        self._sources = {}
        self._n = 0

    def register(self, location: str) -> str:
        self._n += 1
        sid = f"src-{self._n}"
        self._sources[sid] = location
        return sid

    def scan(self, source_id: str) -> str:
        return f"run-{source_id}"

    def await_run(self, run_id: str) -> str:
        return "completed"

    def risks(self, source_id: str):
        return [
            DiscoveryRisk(
                canonical_agent_id="abc123",
                action_pattern="open_pr",
                target_system="github",
                estimated_risk={"level": 2},
                generated_policy="package agentrail\nallow = true",
            )
        ]


class TestSourceScanAdapterContract(unittest.TestCase):
    def test_fake_satisfies_protocol(self):
        a = FakeAdapter()
        self.assertIsInstance(a, SourceScanAdapter)

    def test_round_trip(self):
        a = FakeAdapter()
        sid = a.register("/path/to/repo")
        run = a.scan(sid)
        self.assertEqual(a.await_run(run), "completed")
        risks = a.risks(sid)
        self.assertEqual(len(risks), 1)
        self.assertEqual(risks[0].action_pattern, "open_pr")
        self.assertEqual(risks[0].target_system, "github")

    def test_discovery_risk_is_frozen(self):
        import dataclasses

        r = DiscoveryRisk("id", "push", "github", {"level": 3}, None)
        with self.assertRaises(dataclasses.FrozenInstanceError):
            r.action_pattern = "merge_pr"  # type: ignore[misc]


if __name__ == "__main__":
    unittest.main()
