"""Bring the multidomain + macro-orchestration harnesses into the unittest suite.

`scripts/run_multidomain_scenarios.py` and `scripts/run_orchestrated_campaign.py`
are the deterministic recettes for the multi-agent campaigns and the macro
orchestration campaigns (campaign <-> MAF team link). They are runnable as CLI
scripts, but a CLI-only check never runs in `./recette.sh test`, so a verdict
regression in a committed campaign would pass CI silently. This module runs both
harnesses' main() in-process and asserts a clean (exit 0) result, turning them
into a guarded regression gate like every other recette.

Deterministic (I4): both harnesses use an in-memory gateway + stub proxy, no LLM,
no network. Skipped when the [api] extra (fastapi) is absent.
"""

from __future__ import annotations

import os
import unittest
from pathlib import Path

try:
    import fastapi  # noqa: F401

    HAVE_FASTAPI = True
except ImportError:
    HAVE_FASTAPI = False

REPO_ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(HAVE_FASTAPI, "requires the [api] extra (fastapi)")
class TestOrchestratedCampaignHarnesses(unittest.TestCase):
    """Run the deterministic harnesses from the repo root and assert exit 0."""

    def setUp(self) -> None:
        self._cwd = Path.cwd()
        os.chdir(REPO_ROOT)
        self.addCleanup(lambda: os.chdir(self._cwd))

    def test_multidomain_scenarios_all_pass(self) -> None:
        from scripts.run_multidomain_scenarios import main

        self.assertEqual(main([]), 0)

    def test_macro_orchestration_campaigns_all_pass(self) -> None:
        from scripts.run_orchestrated_campaign import discover_links, main

        # At least one macro orchestration campaign must exist (the link is data).
        self.assertGreaterEqual(len(discover_links()), 1)
        self.assertEqual(main([]), 0)


if __name__ == "__main__":
    unittest.main()
