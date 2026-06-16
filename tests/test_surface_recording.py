"""Section 12.4: a discoveryprobe broker capture recording feeds the SAME
detection scorecard as the in-bench projection.

The broker emits per-agent recordings (surfaces already projected). This proves
the judge is source-agnostic: a live eBPF capture and the in-bench projection
both land in one deterministic DetectionScorecard (I4). A ghost captured nowhere
is a false negative (the thesis failure), an unknown surface name is a loud
bridge mismatch, and a rejected capture has nothing to score.
"""

from __future__ import annotations

import json
import unittest
from dataclasses import asdict

from recette.surface.detect import ReferenceSurfaceDiscoveryAdapter
from recette.surface.recording import (
    CaptureRecording,
    detect_from_recording,
    score_recording,
)

# A broker BrokerResponse::Ok envelope: pr-bot seen on the wire, ghost nowhere.
_BROKER_OK = json.dumps(
    {
        "status": "ok",
        "recordings": [
            {
                "agent_id": "pr-bot-sdk",
                "surfaces": {"ebpf_wire": ["exec:pr-bot:42"]},
            },
            {"agent_id": "ghost-direct-db", "surfaces": {}},
        ],
        "recording_sha256": "0" * 64,
    }
)


class TestSurfaceRecording(unittest.TestCase):
    def test_visible_agent_is_detected_on_its_surface(self) -> None:
        recording = CaptureRecording.from_dict(
            {"agent_id": "pr-bot-sdk", "surfaces": {"ebpf_wire": ["exec:pr-bot:42"]}}
        )
        detection = detect_from_recording(recording, ReferenceSurfaceDiscoveryAdapter())
        self.assertTrue(detection.detected_anywhere)
        wire = next(d for d in detection.per_surface if d.surface.value == "ebpf_wire")
        self.assertTrue(wire.detected)

    def test_ghost_captured_nowhere_is_a_false_negative(self) -> None:
        scorecard = score_recording(_BROKER_OK)
        self.assertFalse(scorecard.ok)
        self.assertEqual(scorecard.false_negatives, ("ghost-direct-db",))
        self.assertEqual(scorecard.total_agents, 2)
        self.assertEqual(scorecard.detected_per_surface, {"ebpf_wire": 1})

    def test_accepts_a_bare_recordings_list(self) -> None:
        bare = json.dumps([{"agent_id": "pr-bot-sdk", "surfaces": {"ebpf_wire": ["x"]}}])
        scorecard = score_recording(bare)
        self.assertTrue(scorecard.ok)
        self.assertEqual(scorecard.false_negatives, ())

    def test_unknown_surface_name_raises_bridge_mismatch(self) -> None:
        with self.assertRaises(ValueError):
            CaptureRecording.from_dict({"agent_id": "x", "surfaces": {"kernel_uprobe": ["y"]}})

    def test_rejected_capture_has_nothing_to_score(self) -> None:
        rejected = json.dumps({"status": "rejected", "reason": "unknown agent: x"})
        with self.assertRaises(ValueError):
            score_recording(rejected)

    def test_scoring_is_byte_stable(self) -> None:
        first = json.dumps(asdict(score_recording(_BROKER_OK)), sort_keys=True)
        second = json.dumps(asdict(score_recording(_BROKER_OK)), sort_keys=True)
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
