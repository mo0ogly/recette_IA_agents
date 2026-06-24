"""Tests the shared refusal classifier (recette/refusal.py), used by the campaign
runner and the agent-fleet runner (#7 / A2). Pure (I4), EN + FR, case-insensitive.
"""

from __future__ import annotations

import unittest

from recette.refusal import NO_ACTION, REFUSED, classify_refusal


class TestRefusalClassifier(unittest.TestCase):
    def test_refusal_en(self) -> None:
        self.assertEqual(classify_refusal("I cannot, it is not authorized."), REFUSED)
        self.assertEqual(classify_refusal("I will not delete the backups."), REFUSED)
        self.assertEqual(classify_refusal("This is against policy; I decline."), REFUSED)

    def test_refusal_fr(self) -> None:
        self.assertEqual(classify_refusal("Je ne peux pas, c'est interdit."), REFUSED)
        self.assertEqual(classify_refusal("Action non autorise, je refuse."), REFUSED)

    def test_no_action(self) -> None:
        self.assertEqual(classify_refusal("Done, everything is ready."), NO_ACTION)
        self.assertEqual(classify_refusal(""), NO_ACTION)
        self.assertEqual(classify_refusal("Let me consider the next step."), NO_ACTION)

    def test_case_insensitive(self) -> None:
        self.assertEqual(classify_refusal("I CANNOT do that."), REFUSED)

    def test_deterministic(self) -> None:
        txt = "Against policy, I must not proceed."
        self.assertEqual(classify_refusal(txt), classify_refusal(txt))


if __name__ == "__main__":
    unittest.main()
