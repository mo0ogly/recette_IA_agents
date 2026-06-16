"""Detection scorecard: per-surface detection rate + the false-negative gate
(any agent detected on no surface fails the recette)."""

from __future__ import annotations

import unittest

from recette.surface.detect import ReferenceSurfaceDiscoveryAdapter, detect_agent
from recette.surface.scorecard import score_detections
from recette.surface.surfaces import ObservationSurface

NORMAL = detect_agent(
    agent_id="pr-bot",
    proxy_traces=[{"action_type": "open_pr", "resource": "acme/web#42"}],
    wire_flows=[{"seq": 0, "method": "POST", "host": "api.github.com", "port": 443, "path": "/p"}],
    adapter=ReferenceSurfaceDiscoveryAdapter(),
)
GHOST = detect_agent(
    agent_id="ghost",
    proxy_traces=[],
    wire_flows=[{"seq": 0, "method": "POST", "host": "shadow-db", "port": 5432, "path": "/w"}],
    adapter=ReferenceSurfaceDiscoveryAdapter(),
)
VANISHED = detect_agent(
    agent_id="vanished",
    proxy_traces=[],
    wire_flows=[],
    adapter=ReferenceSurfaceDiscoveryAdapter(),
)


class TestScorecard(unittest.TestCase):
    def test_all_detected_anywhere_passes(self) -> None:
        card = score_detections([NORMAL, GHOST])
        self.assertTrue(card.ok)
        self.assertEqual(card.false_negatives, ())

    def test_a_vanished_agent_is_a_false_negative(self) -> None:
        card = score_detections([NORMAL, VANISHED])
        self.assertFalse(card.ok)
        self.assertEqual(card.false_negatives, ("vanished",))

    def test_per_surface_rate_exposes_the_hook_blind_spot(self) -> None:
        card = score_detections([NORMAL, GHOST])
        # 2 agents; hook sees only the normal one (1/2), wire sees both (2/2).
        self.assertEqual(card.detected_per_surface[ObservationSurface.HOOK_SDK.value], 1)
        self.assertEqual(card.detected_per_surface[ObservationSurface.EBPF_WIRE.value], 2)
        self.assertEqual(card.total_agents, 2)

    def test_scorecard_is_deterministic(self) -> None:
        self.assertEqual(score_detections([NORMAL, GHOST]), score_detections([NORMAL, GHOST]))


if __name__ == "__main__":
    unittest.main()
