import unittest

from recette.redteam_recette import ScenarioOutcome
from recette.redteam_scorecard import render, scorecard


class T(unittest.TestCase):
    def _o(self, sid, verdict, expected, vt, caught, tags=None, expected_vt=...):
        # expected_vt defaults to the predicted vt (a caught row has predicted ==
        # expected); callers override it to model a wrong-dimension catch.
        evt = vt if expected_vt is ... else expected_vt
        return ScenarioOutcome(sid, verdict, expected, vt, evt, caught, tags or {})

    def test_scorecard_counts_caught_and_missed(self):
        outs = [
            self._o(
                "a", "incorrect", "incorrect", "capability_overreach", True, {"owasp_asi": "ASI02"}
            ),
            self._o("b", "correct", "correct", None, True),
            self._o("c", "correct", "incorrect", None, False),
        ]
        card = scorecard(outs)
        self.assertEqual(card["total"], 3)
        self.assertEqual(card["caught"], 2)
        self.assertEqual(card["missed"], 1)
        self.assertEqual(card["by_owasp"]["ASI02"], 1)

    def test_by_owasp_is_a_distribution_not_a_catch_rate(self):
        # Two outcomes share the SAME owasp tag, one caught and one missed.
        # by_owasp counts ALL outcomes carrying the tag (the distribution of
        # scenarios per OWASP category), NOT how many were caught -- the
        # caught/missed split lives in the top-level counters. This locks that
        # documented semantic so a future refactor cannot silently turn by_owasp
        # into a catch-rate.
        outs = [
            self._o(
                "a", "incorrect", "incorrect", "policy_violation", True, {"owasp_asi": "ASI05"}
            ),
            self._o("b", "correct", "incorrect", None, False, {"owasp_asi": "ASI05"}),
            self._o(
                "c", "incorrect", "incorrect", "capability_overreach", True, {"owasp_asi": "ASI02"}
            ),
        ]
        card = scorecard(outs)
        self.assertEqual(card["total"], 3)
        self.assertEqual(card["caught"], 2)
        self.assertEqual(card["missed"], 1)
        # ASI05 counts BOTH the caught (a) and the missed (b) -> 2, not 1.
        self.assertEqual(card["by_owasp"], {"ASI02": 1, "ASI05": 2})

    def test_render_marks_a_miss_row(self):
        # The MISS branch of render must label a missed scenario, distinct from
        # an OK row, so the operator can see which anomaly slipped through.
        outs = [
            self._o("caught", "incorrect", "incorrect", "policy_violation", True),
            self._o("slipped", "correct", "incorrect", None, False),
        ]
        text = render(scorecard(outs))
        self.assertIn("[MISS] slipped", text)
        self.assertIn("[OK] caught", text)

    def test_render_is_deterministic_text(self):
        outs = [self._o("a", "incorrect", "incorrect", "capability_overreach", True)]
        text = render(scorecard(outs))
        self.assertIn("redteam", text)
        self.assertIn("a", text)
        # stable across calls (no clock/random)
        self.assertEqual(render(scorecard(outs)), text)


if __name__ == "__main__":
    unittest.main()
