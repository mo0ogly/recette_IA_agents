"""Tests the #6 behavioural-repetition metric in recette_govscore.

A repeat (same agent issuing the same action on the same resource > once) is not a
violation -- the side_effect_hash is correctly deterministic -- but a behavioural
signal (the LLM re-reading the same resource). The helper is pure (I4) and
unit-testable on synthetic traces.
"""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "_govscore",
    Path(__file__).resolve().parent.parent / "scripts" / "recette_govscore.py",
)
assert _SPEC and _SPEC.loader
_govscore = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_govscore)
_repetitions = _govscore._repetitions


def _trace(a: str, res: str) -> dict:
    return {"action_type": a, "resource": res}


class TestGovscoreRepetition(unittest.TestCase):
    def test_no_repeat_no_entry(self) -> None:
        traced = [{"ok": True, "agent_id": "x", "done_traces": [_trace("read", "a")]}]
        self.assertEqual(_repetitions(traced), [])

    def test_counts_repeat(self) -> None:
        traced = [
            {
                "ok": True,
                "agent_id": "bot",
                "done_traces": [_trace("read", "a"), _trace("read", "a"), _trace("read", "a")],
            }
        ]
        out = _repetitions(traced)
        self.assertEqual(len(out), 1)
        self.assertEqual(out[0]["agent_id"], "bot")
        self.assertEqual(out[0]["repeats"][0], {"action_type": "read", "resource": "a", "count": 3})

    def test_distinct_resources_not_a_repeat(self) -> None:
        traced = [
            {"ok": True, "agent_id": "b", "done_traces": [_trace("read", "a"), _trace("read", "b")]}
        ]
        self.assertEqual(_repetitions(traced), [])

    def test_skips_failed_runs(self) -> None:
        traced = [{"ok": False, "agent_id": "b", "done_traces": [_trace("read", "a")]}]
        self.assertEqual(_repetitions(traced), [])

    def test_deterministic_sorted(self) -> None:
        traced = [
            {"ok": True, "agent_id": "z", "done_traces": [_trace("r", "a"), _trace("r", "a")]},
            {"ok": True, "agent_id": "a", "done_traces": [_trace("r", "b"), _trace("r", "b")]},
        ]
        out = _repetitions(traced)
        self.assertEqual([x["agent_id"] for x in out], ["a", "z"])  # sorted by agent_id
        self.assertEqual(out, _repetitions(traced))  # stable


if __name__ == "__main__":
    unittest.main()
