"""Tests the #10 independent SEEN-vs-DONE cross: eBPF kernel connect (mapped to a
server's target_system) vs proxy target_system. Two independent channels, so the
analyzer is pure (I4) and testable on synthetic logs.
"""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "_svd",
    Path(__file__).resolve().parent.parent / "scripts" / "recette_seen_vs_done_skynet.py",
)
assert _SPEC and _SPEC.loader
_svd = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_svd)

SERVERS = [
    {"id": "gh-mock", "system": "github", "mode": "mock_local", "port": 9101},
    {"id": "okta-mock", "system": "okta", "mode": "mock_local", "port": 9102},
]


def _ebpf(agent: str, connects: list[str]) -> dict:
    return {"captures": [{"agents": [{"agent_id": agent, "connects": connects}]}]}


def _proxy(agent: str, systems: list[str]) -> list[dict]:
    return [{"agent_id": agent, "target_system": s} for s in systems]


class TestSeenVsDone(unittest.TestCase):
    def test_coherent_when_seen_subset_of_done(self) -> None:
        out = _svd.analyze(
            _ebpf("bot", ["connect:127.0.0.1:9101"]), _proxy("bot", ["github"]), SERVERS
        )
        self.assertEqual(out["overlap_agents"], 1)
        self.assertEqual(out["coherence_rate"], 1.0)
        self.assertTrue(out["per_agent"][0]["coherent"])

    def test_covert_channel_when_seen_not_mediated(self) -> None:
        # dialed okta (kernel) but proxy only mediated github -> covert egress signal
        out = _svd.analyze(
            _ebpf("bot", ["connect:127.0.0.1:9101", "connect:127.0.0.1:9102"]),
            _proxy("bot", ["github"]),
            SERVERS,
        )
        a = out["per_agent"][0]
        self.assertFalse(a["coherent"])
        self.assertEqual(a["seen_not_mediated"], ["okta"])

    def test_undeclared_egress_endpoint_flagged(self) -> None:
        out = _svd.analyze(
            _ebpf("bot", ["connect:8.8.8.8:443"]), _proxy("bot", ["github"]), SERVERS
        )
        self.assertEqual(out["undeclared_egress_endpoints"], ["8.8.8.8:443"])
        # 8.8.8.8 maps to no server -> bot has no SEEN system -> no overlap row
        self.assertEqual(out["overlap_agents"], 0)

    def test_no_overlap_no_rows(self) -> None:
        out = _svd.analyze(_ebpf("a", ["connect:127.0.0.1:9101"]), _proxy("b", ["okta"]), SERVERS)
        self.assertEqual(out["overlap_agents"], 0)

    def test_deterministic(self) -> None:
        args = (_ebpf("bot", ["connect:127.0.0.1:9101"]), _proxy("bot", ["github"]), SERVERS)
        self.assertEqual(_svd.analyze(*args), _svd.analyze(*args))

    def test_kernel_reachable_full_coverage(self) -> None:
        # The deterministic layer: every traced agent whose DONE target maps to a
        # registered server is kernel-reachable, across the whole fleet.
        out = _svd.analyze(
            {"captures": []},
            _proxy("a", ["github"]) + _proxy("b", ["okta"]),
            SERVERS,
        )
        self.assertEqual(out["traced_agents"], 2)
        self.assertEqual(out["kernel_reachable_agents"], 2)
        self.assertEqual(out["kernel_reachable_rate"], 1.0)
        self.assertEqual(out["ghost_target_agents"], [])

    def test_ghost_target_flagged(self) -> None:
        # An agent whose DONE target has NO registered server is a ghost-target:
        # it claims to act on a system the kernel could never witness.
        out = _svd.analyze({"captures": []}, _proxy("rogue", ["unknown_system"]), SERVERS)
        self.assertEqual(out["kernel_reachable_agents"], 0)
        self.assertEqual(len(out["ghost_target_agents"]), 1)
        self.assertEqual(out["ghost_target_agents"][0]["ghost_targets"], ["unknown_system"])


if __name__ == "__main__":
    unittest.main()
