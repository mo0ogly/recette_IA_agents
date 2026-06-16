"""I4: running the full surface recette twice over the corpus yields a byte-
identical scorecard JSON. Guards against any non-determinism creeping in."""

from __future__ import annotations

import json
import unittest
from dataclasses import asdict

from recette.surface.corpus import load_surface_subjects
from recette.surface.detect import ReferenceSurfaceDiscoveryAdapter, detect_agent
from recette.surface.scorecard import score_detections


def _run_once() -> str:
    adapter = ReferenceSurfaceDiscoveryAdapter()
    detections = [
        detect_agent(
            agent_id=s["agent_id"],
            proxy_traces=s["run"]["proxy_traces"],
            wire_flows=s["run"]["wire_flows"],
            adapter=adapter,
        )
        for s in load_surface_subjects()
    ]
    return json.dumps(asdict(score_detections(detections)), sort_keys=True)


class TestSurfaceReplay(unittest.TestCase):
    def test_scorecard_is_byte_stable(self) -> None:
        self.assertEqual(_run_once(), _run_once())

    def test_corpus_has_no_false_negative(self) -> None:
        card = json.loads(_run_once())
        self.assertTrue(card["ok"])
        self.assertEqual(card["false_negatives"], [])


if __name__ == "__main__":
    unittest.main()
