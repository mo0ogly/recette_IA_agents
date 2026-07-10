"""Behavior-dimension anomaly signals: exact spam-repeat AND same-action spray.

Pure, deterministic unit tests of the shared behavior heuristic used by both the
git identification adapter and the MAF judge (adapters.behavior_is_anomalous).
The spray signal (same action across many DISTINCT targets) is the new signal:
the exact (action, target) repeat test misses a fan-out because no single pair
repeats.
"""

from __future__ import annotations

import unittest

from recette.adapters import (
    SPAM_THRESHOLD,
    SPRAY_THRESHOLD,
    behavior_is_anomalous,
    repeats_beyond_threshold,
    sprays_beyond_threshold,
)


class T(unittest.TestCase):
    def test_repeat_below_threshold_is_clean(self) -> None:
        keys = [("read_repo", "acme/widgets")] * (SPAM_THRESHOLD - 1)
        self.assertFalse(repeats_beyond_threshold(keys))
        self.assertFalse(behavior_is_anomalous(keys))

    def test_repeat_at_threshold_is_anomalous(self) -> None:
        keys = [("read_repo", "acme/widgets")] * SPAM_THRESHOLD
        self.assertTrue(repeats_beyond_threshold(keys))
        self.assertTrue(behavior_is_anomalous(keys))

    def test_spray_below_threshold_is_clean(self) -> None:
        # Same action across DISTINCT targets, one short of the spray threshold.
        keys = [("read_repo", f"acme/repo-{i}") for i in range(SPRAY_THRESHOLD - 1)]
        self.assertFalse(sprays_beyond_threshold(keys))
        self.assertFalse(behavior_is_anomalous(keys))

    def test_spray_at_threshold_is_anomalous_even_without_repeat(self) -> None:
        # No (action, target) pair repeats, yet the same action fans out across
        # SPRAY_THRESHOLD distinct targets -> anomaly. This is the gap the exact
        # repeat test misses.
        keys = [("read_repo", f"acme/repo-{i}") for i in range(SPRAY_THRESHOLD)]
        self.assertFalse(repeats_beyond_threshold(keys), "no pair repeats")
        self.assertTrue(sprays_beyond_threshold(keys))
        self.assertTrue(behavior_is_anomalous(keys))

    def test_spray_counts_per_action_not_across_actions(self) -> None:
        # Distinct targets spread across DIFFERENT actions must not trip spray:
        # each action sees only one target here.
        keys = [(f"action-{i}", f"acme/repo-{i}") for i in range(SPRAY_THRESHOLD + 2)]
        self.assertFalse(sprays_beyond_threshold(keys))
        self.assertFalse(behavior_is_anomalous(keys))

    def test_duplicate_targets_do_not_inflate_spray(self) -> None:
        # The same (action, target) many times is a REPEAT, not a spray: spray
        # counts DISTINCT targets, so a single repeated target stays at 1.
        keys = [("read_repo", "acme/widgets")] * (SPRAY_THRESHOLD + 3)
        self.assertFalse(sprays_beyond_threshold(keys))

    def test_functions_are_deterministic(self) -> None:
        keys = [("read_repo", f"acme/repo-{i}") for i in range(SPRAY_THRESHOLD)]
        self.assertEqual(behavior_is_anomalous(keys), behavior_is_anomalous(keys))


if __name__ == "__main__":
    unittest.main()
