"""The replay broker re-projects committed surface ground-truth onto the broker
wire form, and the source-agnostic judge scores it exactly like a live capture.

These tests prove the dev/CI probe path end-to-end WITHOUT CAP_BPF: the replay
broker on a Unix socket, the production relay (``recette.api.probe_relay``), and
the production judge (``recette.surface.recording.score_recording``). Determinism
(I4) is asserted (same request -> byte-stable sha256).
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
import unittest

from recette.api.probe_relay import relay_capture
from recette.platform.probe.replay_broker import (
    ReplayBroker,
    build_recording,
    handle_command,
    load_reference_surfaces,
)
from recette.surface.recording import score_recording


class TestReference(unittest.TestCase):
    def test_loads_known_corpus_subjects(self) -> None:
        ref = load_reference_surfaces()
        # the keystone subjects of the surface corpus
        self.assertIn("pr-bot-sdk", ref)
        self.assertIn("ghost-direct-db", ref)
        self.assertIn("vanished", ref)
        # pr-bot is visible everywhere; ghost only on the wire; vanished nowhere
        self.assertTrue(all(ref["pr-bot-sdk"].values()))
        self.assertTrue(ref["ghost-direct-db"]["ebpf_wire"])
        self.assertFalse(ref["ghost-direct-db"]["hook_sdk"])
        self.assertFalse(any(ref["vanished"].values()))


class TestBuildRecording(unittest.TestCase):
    def setUp(self) -> None:
        self.ref = load_reference_surfaces()

    def test_shapes_match_visibility(self) -> None:
        rec = build_recording(["pr-bot-sdk", "ghost-direct-db", "vanished"], self.ref)
        self.assertEqual(rec["status"], "ok")
        self.assertEqual(rec["mode"], "replay")
        by_id = {r["agent_id"]: r for r in rec["recordings"]}  # type: ignore[union-attr]
        self.assertEqual(
            set(by_id["pr-bot-sdk"]["surfaces"]),
            {"hook_subprocess", "hook_mcp", "hook_sdk", "ebpf_wire"},
        )
        self.assertEqual(set(by_id["ghost-direct-db"]["surfaces"]), {"ebpf_wire"})
        self.assertEqual(by_id["vanished"]["surfaces"], {})

    def test_unknown_agent_is_ghost(self) -> None:
        rec = build_recording(["totally-unknown-agent"], self.ref)
        self.assertEqual(rec["recordings"][0]["surfaces"], {})  # type: ignore[index]

    def test_deterministic_sha(self) -> None:
        a = build_recording(["pr-bot-sdk", "vanished"], self.ref)
        b = build_recording(["pr-bot-sdk", "vanished"], self.ref)
        self.assertEqual(a["recording_sha256"], b["recording_sha256"])


class TestHandleCommand(unittest.TestCase):
    def setUp(self) -> None:
        self.ref = load_reference_surfaces()

    def test_rejects_non_capture(self) -> None:
        out = handle_command(json.dumps({"command": "halt"}), self.ref)
        self.assertEqual(out["status"], "error")

    def test_rejects_empty_agents(self) -> None:
        out = handle_command(json.dumps({"command": "capture", "agents": []}), self.ref)
        self.assertEqual(out["status"], "error")

    def test_rejects_garbage(self) -> None:
        out = handle_command("not json", self.ref)
        self.assertEqual(out["status"], "error")


class TestEndToEndThroughRelayAndJudge(unittest.TestCase):
    def setUp(self) -> None:
        self.dir = tempfile.mkdtemp()
        self.path = os.path.join(self.dir, "replay.sock")
        self.broker = ReplayBroker(self.path)
        self.thread = threading.Thread(target=self.broker.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.broker.close)

    def test_replay_capture_is_scored_like_a_live_capture(self) -> None:
        recording = relay_capture(
            socket_path=self.path,
            agents=["pr-bot-sdk", "vanished"],
            duration_ms=1000,
        )
        self.assertEqual(recording["status"], "ok")
        self.assertEqual(recording["mode"], "replay")
        scorecard = score_recording(json.dumps(recording))
        # pr-bot is seen, vanished is the false negative the thesis must surface
        self.assertFalse(scorecard.ok)
        self.assertEqual(tuple(scorecard.false_negatives), ("vanished",))

    def test_all_seen_is_green(self) -> None:
        recording = relay_capture(
            socket_path=self.path,
            agents=["pr-bot-sdk", "ghost-direct-db"],
            duration_ms=1000,
        )
        scorecard = score_recording(json.dumps(recording))
        self.assertTrue(scorecard.ok)
        self.assertEqual(tuple(scorecard.false_negatives), ())


if __name__ == "__main__":
    unittest.main()
