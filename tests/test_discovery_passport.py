"""Passport-status invariant: present / absent / invalid across the reference scan.

The discovery scanner must surface HOW an agent declares itself, not just that it
exists. A sanctioned repo carries a valid `.inspect_ia_agents/manifest.json`
(present); a shadow agent carries none (absent); a broken manifest that parses as
JSON but fails the manifest shape must be reported invalid, never silently trusted.
These tests pin that invariant through the ReferenceSourceScanAdapter and the
discovery harness.
"""

from __future__ import annotations

import unittest
from pathlib import Path

from recette.adapters import ReferenceSourceScanAdapter
from recette.discovery_harness import run_discovery_recette

_REPO_ROOT = Path(__file__).resolve().parents[1]
_REPOS = _REPO_ROOT / "corpus" / "repos"


def _scan(slug: str):
    adapter = ReferenceSourceScanAdapter()
    sid = adapter.register(str(_REPOS / slug / "repo"))
    adapter.await_run(adapter.scan(sid))
    return adapter.risks(sid)


class TestReferenceAdapterPassportStatus(unittest.TestCase):
    def test_reference_adapter_reports_present_for_manifest_repo(self):
        risks = _scan("gh-pr-bot")
        self.assertTrue(risks, "expected the pr-bot to be detected")
        self.assertTrue(
            all(r.passport_status == "present" for r in risks),
            [r.passport_status for r in risks],
        )

    def test_reference_adapter_reports_absent_for_shadow_agent(self):
        risks = _scan("gh-shadow-agent")
        self.assertTrue(risks, "expected the shadow agent to be detected via code fallback")
        self.assertTrue(
            all(r.passport_status == "absent" for r in risks),
            [r.passport_status for r in risks],
        )

    def test_reference_adapter_reports_invalid_for_broken_manifest(self):
        risks = _scan("gh-invalid-passport")
        self.assertTrue(risks, "expected broken-manifest agent detected via code fallback")
        self.assertTrue(
            all(r.passport_status == "invalid" for r in risks),
            [r.passport_status for r in risks],
        )


class TestHarnessPassportInvariant(unittest.TestCase):
    def test_harness_passport_invariant_scores_all_subjects(self):
        scorecard = run_discovery_recette(ReferenceSourceScanAdapter())
        # The three passport subjects must all pass, including the passport dimension.
        by_repo = {r.repo: r for r in scorecard.results}
        for slug, expected in (
            ("gh-pr-bot", None),
            ("gh-shadow-agent", "absent"),
            ("gh-invalid-passport", "invalid"),
        ):
            with self.subTest(slug=slug):
                result = by_repo.get(slug)
                self.assertIsNotNone(result, f"{slug} missing from scorecard")
                self.assertTrue(result.passed, "\n".join(result.detail) or result.repo)
                if expected is not None:
                    self.assertTrue(result.matches.get("passport"), result.detail)


if __name__ == "__main__":
    unittest.main()
