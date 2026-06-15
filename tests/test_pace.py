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


if __name__ == "__main__":
    unittest.main()
