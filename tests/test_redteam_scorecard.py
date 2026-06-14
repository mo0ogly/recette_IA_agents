import unittest

from recette.redteam_recette import ScenarioOutcome
from recette.redteam_scorecard import render, scorecard


class T(unittest.TestCase):
    def _o(self, sid, verdict, expected, vt, caught, tags=None):
        return ScenarioOutcome(sid, verdict, expected, vt, caught, tags or {})

    def test_scorecard_counts_caught_and_missed(self):
        outs = [
            self._o("a", "incorrect", "incorrect", "capability_overreach", True,
                    {"owasp_asi": "ASI02"}),
            self._o("b", "correct", "correct", None, True),
            self._o("c", "correct", "incorrect", None, False),
        ]
        card = scorecard(outs)
        self.assertEqual(card["total"], 3)
        self.assertEqual(card["caught"], 2)
        self.assertEqual(card["missed"], 1)
        self.assertEqual(card["by_owasp"]["ASI02"], 1)

    def test_render_is_deterministic_text(self):
        outs = [self._o("a", "incorrect", "incorrect", "capability_overreach", True)]
        text = render(scorecard(outs))
        self.assertIn("redteam", text)
        self.assertIn("a", text)
        # stable across calls (no clock/random)
        self.assertEqual(render(scorecard(outs)), text)


if __name__ == "__main__":
    unittest.main()
