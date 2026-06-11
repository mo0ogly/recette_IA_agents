#!/usr/bin/env python3
"""Unit tests for plan_backfill_gen.py score/date extraction (c69 / A105).

Asserts the unified SCORE_RE / DATE_RE handle every legacy RETEX header
format observed in the liaprobe-fingerprint-rebuild scope, and that
extract_summary() returns the correct numerator + scale + date on two
real committed RETEX files (c2 = 91/100, c15 = 45/50)."""
import unittest
from pathlib import Path

import plan_backfill_gen as g


class TestScoreRegex(unittest.TestCase):
    def _score(self, line):
        m = g.SCORE_RE.search(line)
        return None if not m else (m.group(1), m.group(2))

    def test_agentique_legacy(self):
        # original c55 target format
        self.assertEqual(self._score("**Agentic score** : 48/50"), ("48", "50"))
        self.assertEqual(self._score("Score agentique : 46/50"), ("46", "50"))

    def test_bold_prefix_over_100(self):
        # c2,c3,c7,c8 -- no "agentique", /100, bold prefix, trailing text
        self.assertEqual(
            self._score("**Score :** 91/100 (objectif : 85)"), ("91", "100")
        )
        self.assertEqual(
            self._score("**Score :** 100/100 (objectif: maintain)"), ("100", "100")
        )

    def test_english_agentic_bold_outside_colon(self):
        # c15..c31 -- "Agentic score", ** outside the colon
        self.assertEqual(self._score("**Agentic score** : 45/50"), ("45", "50"))
        self.assertEqual(self._score("**Agentic score** : 43/50"), ("43", "50"))

    def test_bold_after_colon(self):
        # recent style -- ** AFTER the colon
        self.assertEqual(self._score("Score: **50/50**"), ("50", "50"))
        self.assertEqual(self._score("Score : **48/50** (+1 vs c67)"), ("48", "50"))

    def test_spaced_slash(self):
        self.assertEqual(self._score("Agentic score : 44 / 50"), ("44", "50"))


class TestDateRegex(unittest.TestCase):
    def _date(self, line):
        m = g.DATE_RE.search(line)
        return None if not m else m.group(1)

    def test_date_variants(self):
        self.assertEqual(self._date("**Date :** 2026-05-12"), "2026-05-12")
        self.assertEqual(self._date("**Date**  : 2026-05-13"), "2026-05-13")
        self.assertEqual(self._date("Date: 2026-05-14"), "2026-05-14")
        self.assertEqual(self._date("Date : 2026-05-15"), "2026-05-15")


class TestExtractSummaryRealRetex(unittest.TestCase):
    def _retex(self, cycle):
        path, reason = g.find_retex(cycle)
        self.assertIsNotNone(path, f"c{cycle} RETEX missing: {reason}")
        return path

    def test_c2_over_100(self):
        s = g.extract_summary(self._retex(2))
        self.assertEqual(s["score"], "91")
        self.assertEqual(s["score_scale"], "100")
        self.assertEqual(s["date"], "2026-05-12")

    def test_c15_agentic_50(self):
        s = g.extract_summary(self._retex(15))
        self.assertEqual(s["score"], "45")
        self.assertEqual(s["score_scale"], "50")
        self.assertEqual(s["date"], "2026-05-13")

    def test_score_text_render(self):
        s = g.extract_summary(self._retex(2))
        stub = g.generate_stub(2, "x.md", s)
        self.assertIn("Score: 91/100", stub)
        self.assertNotIn("(not extracted)", stub)


if __name__ == "__main__":
    unittest.main(verbosity=2)
