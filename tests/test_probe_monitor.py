"""Passive eBPF monitor: a looped broker capture accumulates live sightings.

Stubs the broker relay (no socket): a watched agent seen on a surface shows up in
the snapshot in near-real-time; a broker error degrades (last_error) without
fabricating a sighting; stop() halts the loop.
"""

from __future__ import annotations

import time
import unittest
from unittest import mock

from recette.api import probe_monitor
from recette.api.probe_monitor import ProbeMonitor
from recette.api.probe_relay import ProbeUnavailable


def _wait(cond, tries=200):  # type: ignore[no-untyped-def]
    for _ in range(tries):
        if cond():
            return True
        time.sleep(0.02)
    return False


class ProbeMonitorTest(unittest.TestCase):
    def test_sees_a_watched_agent_in_near_real_time(self) -> None:
        recording = {
            "status": "ok",
            "recordings": [
                {"agent_id": "dx-live-bot", "surfaces": {"ebpf_wire": ["connect:127.0.0.1:9101"]}}
            ],
        }
        mon = ProbeMonitor()
        self.addCleanup(mon.stop)
        with mock.patch.object(probe_monitor, "relay_capture", return_value=recording):
            self.assertTrue(mon.start(socket_path="/x.sock", agents=["dx-live-bot"], window_ms=200))
            self.assertFalse(mon.start(socket_path="/x.sock", agents=["dx-live-bot"]))  # idempotent
            ok = _wait(
                lambda: any(s["agent_id"] == "dx-live-bot" for s in mon.snapshot()["sightings"])
            )
        self.assertTrue(ok, "watched agent never surfaced")
        snap = mon.snapshot()
        sighting = next(s for s in snap["sightings"] if s["agent_id"] == "dx-live-bot")
        self.assertEqual(sighting["surfaces"], ["ebpf_wire"])
        self.assertGreaterEqual(sighting["windows_seen"], 1)
        self.assertTrue(snap["running"])

    def test_broker_error_degrades_without_fabricating(self) -> None:
        mon = ProbeMonitor()
        self.addCleanup(mon.stop)
        with mock.patch.object(
            probe_monitor, "relay_capture", side_effect=ProbeUnavailable("broker down")
        ):
            mon.start(socket_path="/x.sock", agents=["a"], window_ms=200)
            ok = _wait(lambda: mon.snapshot()["last_error"] is not None)
        self.assertTrue(ok)
        self.assertEqual(mon.snapshot()["sightings"], [])  # never invents a sighting

    def test_rejected_capture_sets_error_no_sighting(self) -> None:
        rejected = {"status": "rejected", "reason": "unknown agent: x"}
        mon = ProbeMonitor()
        self.addCleanup(mon.stop)
        with mock.patch.object(probe_monitor, "relay_capture", return_value=rejected):
            mon.start(socket_path="/x.sock", agents=["x"], window_ms=200)
            ok = _wait(lambda: mon.snapshot()["last_error"] is not None)
        self.assertTrue(ok)
        self.assertEqual(mon.snapshot()["sightings"], [])

    def test_stop_halts(self) -> None:
        mon = ProbeMonitor()
        with mock.patch.object(probe_monitor, "relay_capture", return_value={"status": "ok"}):
            mon.start(socket_path="/x.sock", agents=["a"], window_ms=200)
            self.assertTrue(_wait(lambda: mon.snapshot()["windows"] >= 1))
            mon.stop()
        self.assertFalse(mon.snapshot()["running"])


if __name__ == "__main__":
    unittest.main()
