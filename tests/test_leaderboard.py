"""Tests the LLM governance leaderboard aggregator (A9). Pure ranking (I4)."""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

_SPEC = importlib.util.spec_from_file_location(
    "_lb", Path(__file__).resolve().parent.parent / "scripts" / "recette_leaderboard.py"
)
assert _SPEC and _SPEC.loader
_lb = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_lb)


def _card(llm: str, total: float, stars: int) -> dict:
    return {
        "llm": llm,
        "stars": stars,
        "total": total,
        "levels": {
            "L1_governance_hygiene": 40.0,
            "L2_behaviour_coherence": 25.0,
            "L3_adversarial_resistance": 20.0,
        },
        "metrics": {"engaged": 30, "resisted": 12, "adversarial": 14},
    }


class TestLeaderboard(unittest.TestCase):
    def test_ranks_by_total_desc(self) -> None:
        rows = _lb.rank([_card("a", 80.0, 4), _card("b", 95.0, 5), _card("c", 60.0, 3)])
        self.assertEqual([r["llm"] for r in rows], ["b", "a", "c"])

    def test_name_tiebreak_stable(self) -> None:
        rows = _lb.rank([_card("z", 90.0, 5), _card("a", 90.0, 5)])
        self.assertEqual([r["llm"] for r in rows], ["a", "z"])

    def test_carries_levels(self) -> None:
        rows = _lb.rank([_card("a", 80.0, 4)])
        self.assertEqual((rows[0]["L1"], rows[0]["L2"], rows[0]["L3"]), (40.0, 25.0, 20.0))

    def test_markdown_has_a_row(self) -> None:
        md = _lb.to_markdown(_lb.rank([_card("a", 80.0, 4)]))
        self.assertIn("| a |", md)
        self.assertIn("leaderboard", md)

    def test_deterministic(self) -> None:
        cards = [_card("a", 80.0, 4), _card("b", 95.0, 5)]
        self.assertEqual(_lb.rank(cards), _lb.rank(cards))


if __name__ == "__main__":
    unittest.main()
