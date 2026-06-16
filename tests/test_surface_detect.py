"""Per-surface detection: the SurfaceDiscoveryAdapter seam + reference oracle.
The ghost agent is the keystone: invisible on hook, detected on wire."""

from __future__ import annotations

import unittest

from recette.surface.detect import ReferenceSurfaceDiscoveryAdapter, detect_agent
from recette.surface.surfaces import ObservationSurface, SurfaceObservation

NORMAL_TRACES = [{"action_type": "open_pr", "resource": "acme/web#42"}]
NORMAL_FLOWS = [{"seq": 0, "method": "POST", "host": "api.github.com", "port": 443, "path": "/p"}]
GHOST_FLOWS = [
    {"seq": 0, "method": "POST", "host": "shadow-db.acme.internal", "port": 5432, "path": "/w"}
]


class TestReferenceAdapter(unittest.TestCase):
    def test_detects_when_something_is_visible(self) -> None:
        adapter = ReferenceSurfaceDiscoveryAdapter()
        obs = SurfaceObservation(ObservationSurface.HOOK_SDK, ("open_pr:acme/web#42",))
        self.assertTrue(adapter.detect_on(obs).detected)

    def test_blind_when_nothing_visible(self) -> None:
        adapter = ReferenceSurfaceDiscoveryAdapter()
        obs = SurfaceObservation(ObservationSurface.HOOK_SDK, ())
        self.assertFalse(adapter.detect_on(obs).detected)


class TestDetectAgent(unittest.TestCase):
    def test_normal_agent_detected_on_every_surface(self) -> None:
        result = detect_agent(
            agent_id="pr-bot",
            proxy_traces=NORMAL_TRACES,
            wire_flows=NORMAL_FLOWS,
            adapter=ReferenceSurfaceDiscoveryAdapter(),
        )
        self.assertTrue(result.detected_anywhere)
        self.assertTrue(all(d.detected for d in result.per_surface))

    def test_ghost_blind_on_hook_detected_on_wire(self) -> None:
        result = detect_agent(
            agent_id="ghost",
            proxy_traces=[],
            wire_flows=GHOST_FLOWS,
            adapter=ReferenceSurfaceDiscoveryAdapter(),
        )
        self.assertTrue(result.detected_anywhere)  # wire saved us
        by_surface = {d.surface: d.detected for d in result.per_surface}
        self.assertFalse(by_surface[ObservationSurface.HOOK_SDK])
        self.assertTrue(by_surface[ObservationSurface.EBPF_WIRE])

    def test_fully_invisible_agent_is_a_failure(self) -> None:
        result = detect_agent(
            agent_id="vanished",
            proxy_traces=[],
            wire_flows=[],
            adapter=ReferenceSurfaceDiscoveryAdapter(),
        )
        self.assertFalse(result.detected_anywhere)  # the thesis failure


if __name__ == "__main__":
    unittest.main()
