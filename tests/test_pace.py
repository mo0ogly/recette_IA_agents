"""Pace resolution + slicing are pure ops helpers (I4: never on the judged path)."""

import unittest

from recette.api.runners import MAX_PACE_MS, resolve_pace


class ResolvePaceTest(unittest.TestCase):
    def _server(self, sid, pace=None):
        s = {"id": sid, "system": "github", "mode": "mock_local", "port": 9101}
        if pace is not None:
            s["pace_ms"] = pace
        return s

    def test_agent_overrides_server(self):
        agent = {"server": "gh", "pace_ms": 2000}
        servers = [self._server("gh", 500)]
        self.assertEqual(resolve_pace(agent, servers), 2000)

    def test_inherits_server_when_agent_unset(self):
        agent = {"server": "gh"}
        servers = [self._server("gh", 500)]
        self.assertEqual(resolve_pace(agent, servers), 500)

    def test_defaults_zero_when_neither_set(self):
        agent = {"server": "gh"}
        servers = [self._server("gh")]
        self.assertEqual(resolve_pace(agent, servers), 0)

    def test_defaults_zero_when_server_missing(self):
        agent = {"server": "ghost"}
        self.assertEqual(resolve_pace(agent, []), 0)

    def test_clamped_to_max(self):
        agent = {"server": "gh", "pace_ms": 10**9}
        self.assertEqual(resolve_pace(agent, [self._server("gh")]), MAX_PACE_MS)

    def test_negative_clamped_to_zero(self):
        agent = {"server": "gh", "pace_ms": -5}
        self.assertEqual(resolve_pace(agent, [self._server("gh")]), 0)

    def test_non_int_falls_back_to_zero(self):
        agent = {"server": "gh", "pace_ms": "fast"}
        self.assertEqual(resolve_pace(agent, [self._server("gh")]), 0)


class PacedOnStepTest(unittest.TestCase):
    def test_calls_inner_then_sleeps_total_pace(self):
        slept = []
        calls = []
        from recette.api import runners

        original = runners.time.sleep
        runners.time.sleep = lambda s: slept.append(s)
        try:
            wrapped = runners._paced_on_step(
                lambda i, step: calls.append(i), pace_ms=250, should_stop=lambda: False
            )
            wrapped(0, object())
        finally:
            runners.time.sleep = original

        self.assertEqual(calls, [0])           # inner ran first
        self.assertAlmostEqual(sum(slept), 0.25, places=3)  # total slept == pace

    def test_stop_breaks_sleep_early(self):
        slept = []
        from recette.api import runners

        original = runners.time.sleep
        runners.time.sleep = lambda s: slept.append(s)
        try:
            wrapped = runners._paced_on_step(
                lambda i, step: None, pace_ms=5000, should_stop=lambda: True
            )
            wrapped(0, object())
        finally:
            runners.time.sleep = original

        self.assertLessEqual(sum(slept), 0.1)  # bailed within one slice

    def test_zero_pace_never_sleeps(self):
        from recette.api import runners

        original = runners.time.sleep

        def boom(_):
            raise AssertionError("should not sleep at pace 0")

        runners.time.sleep = boom
        try:
            wrapped = runners._paced_on_step(
                lambda i, step: None, pace_ms=0, should_stop=lambda: False
            )
            wrapped(0, object())  # must not raise
        finally:
            runners.time.sleep = original


if __name__ == "__main__":
    unittest.main()
