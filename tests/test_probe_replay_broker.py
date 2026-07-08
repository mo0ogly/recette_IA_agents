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
import socket as _socket
import tempfile
import threading
import unittest

_HAS_AF_UNIX = hasattr(_socket, "AF_UNIX")

from recette.api.probe_relay import open_watch, relay_capture
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


@unittest.skipUnless(_HAS_AF_UNIX, "requires AF_UNIX (absent on Windows CPython)")
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


class TestEndToEndOverTcp(unittest.TestCase):
    """The tcp:HOST:PORT endpoint (Windows fallback, no AF_UNIX) carries the
    same wire form end-to-end: broker bind, relay connect, judge scoring.
    Runs on every platform (loopback TCP), so the e2e path stays covered where
    the unix-socket class above is skipped."""

    def setUp(self) -> None:
        # Port 0 -> the OS picks a free ephemeral port; the broker reports it.
        self.broker = ReplayBroker("tcp:127.0.0.1:0")
        self.thread = threading.Thread(target=self.broker.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.broker.close)

    def test_replay_capture_over_tcp_is_scored(self) -> None:
        self.assertTrue(self.broker.address.startswith("tcp:127.0.0.1:"))
        recording = relay_capture(
            socket_path=self.broker.address,
            agents=["pr-bot-sdk", "vanished"],
            duration_ms=1000,
        )
        self.assertEqual(recording["status"], "ok")
        self.assertEqual(recording["mode"], "replay")
        scorecard = score_recording(json.dumps(recording))
        self.assertFalse(scorecard.ok)
        self.assertEqual(tuple(scorecard.false_negatives), ("vanished",))

    def test_deterministic_sha_over_tcp(self) -> None:
        a = relay_capture(
            socket_path=self.broker.address, agents=["pr-bot-sdk"], duration_ms=1000
        )
        b = relay_capture(
            socket_path=self.broker.address, agents=["pr-bot-sdk"], duration_ms=1000
        )
        self.assertEqual(a["recording_sha256"], b["recording_sha256"])

    def test_watch_streams_deterministic_recordings(self) -> None:
        # The passive monitor path: ONE connection, one recording line per slice.
        sock = open_watch(
            socket_path=self.broker.address, agents=["pr-bot-sdk"], duration_ms=200
        )
        self.addCleanup(sock.close)
        sock.settimeout(5.0)
        buf = b""
        while buf.count(b"\n") < 2:
            data = sock.recv(65536)
            self.assertTrue(data, "watch stream closed before two slices arrived")
            buf += data
        first, second = buf.split(b"\n")[:2]
        rec_a = json.loads(first)
        rec_b = json.loads(second)
        self.assertEqual(rec_a["status"], "ok")
        self.assertEqual(rec_a["mode"], "replay")
        # Slices replay the same reference: byte-stable content (I4).
        self.assertEqual(rec_a["recording_sha256"], rec_b["recording_sha256"])

    def test_watch_does_not_block_concurrent_capture(self) -> None:
        # A long-lived watch stream must not starve a one-shot capture.
        sock = open_watch(
            socket_path=self.broker.address, agents=["pr-bot-sdk"], duration_ms=10_000
        )
        self.addCleanup(sock.close)
        recording = relay_capture(
            socket_path=self.broker.address, agents=["pr-bot-sdk"], duration_ms=1000
        )
        self.assertEqual(recording["status"], "ok")


if __name__ == "__main__":
    unittest.main()
