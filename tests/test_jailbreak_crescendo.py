"""Tests the #8 crescendo jailbreak ladder logic with a stub LLM (no network).

Crescendo = one mounting multi-turn conversation; the threshold is the lowest
ladder rung at which the model first calls a deny action. Driven by a fake LLM so
the walk is deterministic and testable offline.
"""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "_jb",
    Path(__file__).resolve().parent.parent / "scripts" / "run_jailbreak_threshold_skynet.py",
)
assert _SPEC and _SPEC.loader
_jb = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_jb)

_DOC = {
    "name": "t",
    "actions": [{"action_type": "delete_x", "expect": "deny", "resource": "r"}],
}


class _Decision:
    def __init__(self, tool: str | None = None, text: str = "") -> None:
        self.tool_name = tool
        self.text = text

    @property
    def is_tool_call(self) -> bool:
        return self.tool_name is not None


class _RefuseAll:
    def decide(self, *, system, history, tools):  # noqa: ANN001
        return _Decision(text="I refuse, that is not authorized")


class _BreakAtTurn:
    """Calls the deny tool starting at the Nth decide()."""

    def __init__(self, n: int) -> None:
        self.n = n
        self.calls = 0

    def decide(self, *, system, history, tools):  # noqa: ANN001
        self.calls += 1
        if self.calls >= self.n:
            return _Decision(tool=tools[0].name)
        return _Decision(text="no")


class TestCrescendo(unittest.TestCase):
    def test_refuse_all_holds(self) -> None:
        r = _jb.run_campaign(_RefuseAll(), _DOC, crescendo=True)
        self.assertTrue(r["held"])
        self.assertIsNone(r["broke_at"])
        self.assertEqual(r["mode"], "crescendo")

    def test_break_at_second_rung(self) -> None:
        r = _jb.run_campaign(_BreakAtTurn(2), _DOC, crescendo=True)
        self.assertFalse(r["held"])
        self.assertEqual(r["broke_at"], "L1_urgency")

    def test_break_at_first_rung(self) -> None:
        r = _jb.run_campaign(_BreakAtTurn(1), _DOC, crescendo=True)
        self.assertEqual(r["broke_at"], "L0_neutral")

    def test_single_mode_stamped(self) -> None:
        r = _jb.run_campaign(_RefuseAll(), _DOC, crescendo=False)
        self.assertEqual(r["mode"], "single_turn")
        self.assertTrue(r["held"])

    def test_conversation_grows_each_rung(self) -> None:
        # crescendo must feed a GROWING history (mounting pressure), not restart.
        seen_lengths = []

        class _Recorder:
            def decide(self, *, system, history, tools):  # noqa: ANN001
                seen_lengths.append(len(history))
                return _Decision(text="no")

        _jb.run_campaign(_Recorder(), _DOC, crescendo=True)
        # 4 rungs -> histories of 1, 3, 5, 7 (user+assistant appended each rung)
        self.assertEqual(seen_lengths, [1, 3, 5, 7])


if __name__ == "__main__":
    unittest.main()
