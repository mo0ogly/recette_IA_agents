"""WS-D: bounded-memory window for the Lane B loop is pure and deterministic."""

from __future__ import annotations

import unittest

from recette.lane_b import _windowed
from recette.llm import Message


def _hist(n: int) -> list[Message]:
    return [Message("user", "goal"), *[Message("assistant", f"m{i}") for i in range(1, n)]]


class TestWindowedMemory(unittest.TestCase):
    def test_none_keeps_full_history(self) -> None:
        h = _hist(5)
        self.assertEqual(_windowed(h, None), h)

    def test_window_larger_than_history_is_noop(self) -> None:
        h = _hist(3)
        self.assertEqual(_windowed(h, 10), h)

    def test_window_keeps_goal_plus_recent(self) -> None:
        h = _hist(6)  # goal + m1..m5
        w = _windowed(h, 3)
        # goal message is retained, plus the last window-1 (=2) messages.
        self.assertEqual(len(w), 3)
        self.assertEqual(w[0].content, "goal")
        self.assertEqual(w[-1].content, "m5")
        self.assertEqual(w[1].content, "m4")

    def test_window_one_keeps_only_goal(self) -> None:
        self.assertEqual(_windowed(_hist(4), 1), _hist(4)[:1])

    def test_is_pure(self) -> None:
        h = _hist(8)
        self.assertEqual(_windowed(h, 4), _windowed(h, 4))


class TestMemoryWindowResolve(unittest.TestCase):
    def test_resolves_agent_config_to_window(self) -> None:
        from recette.api.runners import _memory_window

        self.assertIsNone(_memory_window({}))
        self.assertIsNone(_memory_window({"memory": {"enabled": False, "window": 5}}))
        self.assertIsNone(_memory_window({"memory": {"enabled": True}}))
        self.assertEqual(_memory_window({"memory": {"enabled": True, "window": 5}}), 5)
        # A non-positive / non-int window degrades to unbounded (fail-safe).
        self.assertIsNone(_memory_window({"memory": {"enabled": True, "window": 0}}))


if __name__ == "__main__":
    unittest.main()
