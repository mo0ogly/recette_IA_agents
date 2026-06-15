"""Compensatory bypass_detected events (scenario step 5) + replay (step 6).

A wire flow with no matching audit event becomes a canonical PlatformActionEvent
(action_type=bypass_detected, deny). Pure/deterministic: replay reproduces the
same events byte for byte (I4). Idempotent: the same bypass is not re-emitted.
"""

from __future__ import annotations

import unittest

from recette.platform.events import PolicyVerdict
from recette.platform.proxy.bypass_event import (
    UNREGISTERED_AGENT,
    build_bypass_event,
    raise_bypass_events,
)
from recette.platform.proxy.reconcile import ReconcileReport


def _flow(seq: int, port: int, path: str = "/shadow_db/write") -> dict:
    return {
        "seq": seq,
        "host": "127.0.0.1",
        "port": port,
        "path": path,
        "response_body": "{}",
        "run_id": "R",
    }


class _Ids:
    """Deterministic id source for the test (sequence-derived, replay-stable)."""

    def __init__(self) -> None:
        self._n = 0

    def next_id(self) -> str:
        self._n += 1
        return f"evt-{self._n:04d}"


class BuildBypassEventTest(unittest.TestCase):
    def test_event_is_a_deny_against_the_unmediated_target(self) -> None:
        ev = build_bypass_event(_flow(1, 9113), event_id="evt-1", timestamp="2026-06-15T00:00:00Z")
        self.assertEqual(ev.action_type, "bypass_detected")
        self.assertEqual(ev.agent_id, UNREGISTERED_AGENT)
        self.assertEqual(ev.capability_scope, ())  # ghost has no bound capability (I3)
        self.assertEqual(ev.target_system, "127.0.0.1:9113")
        self.assertIsNotNone(ev.policy_decision)
        assert ev.policy_decision is not None
        self.assertEqual(ev.policy_decision.verdict, PolicyVerdict.DENY)
        self.assertIsNotNone(ev.side_effect_hash)

    def test_build_is_byte_stable(self) -> None:
        a = build_bypass_event(_flow(1, 9113), event_id="e", timestamp="T").to_dict()
        b = build_bypass_event(_flow(1, 9113), event_id="e", timestamp="T").to_dict()
        self.assertEqual(a, b)


class RaiseBypassEventsTest(unittest.TestCase):
    def test_one_event_per_distinct_bypass_in_seq_order(self) -> None:
        report = ReconcileReport(
            ok=False, bypass_flows=[_flow(1, 9113), _flow(2, 9114, "/disk/write")]
        )
        events = raise_bypass_events(report, next_event_id=_Ids().next_id, timestamp="T")
        self.assertEqual([e.event_id for e in events], ["evt-0001", "evt-0002"])
        self.assertEqual([e.target_system for e in events], ["127.0.0.1:9113", "127.0.0.1:9114"])

    def test_already_raised_hash_is_skipped_idempotent(self) -> None:
        report = ReconcileReport(ok=False, bypass_flows=[_flow(1, 9113)])
        first = raise_bypass_events(report, next_event_id=_Ids().next_id, timestamp="T")
        # Re-running with the first event's hash known emits nothing (no dup spam).
        again = raise_bypass_events(
            report,
            next_event_id=_Ids().next_id,
            timestamp="T",
            already_raised=[first[0].side_effect_hash or ""],
        )
        self.assertEqual(again, [])

    def test_replay_is_deterministic(self) -> None:
        report = ReconcileReport(ok=False, bypass_flows=[_flow(2, 9114), _flow(1, 9113)])
        run_a = [
            e.to_dict()
            for e in raise_bypass_events(report, next_event_id=_Ids().next_id, timestamp="T")
        ]
        run_b = [
            e.to_dict()
            for e in raise_bypass_events(report, next_event_id=_Ids().next_id, timestamp="T")
        ]
        self.assertEqual(run_a, run_b)


if __name__ == "__main__":
    unittest.main()
