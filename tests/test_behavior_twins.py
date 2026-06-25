"""Acceptance tests for the frozen twin evidence bundles.

Each twin is a frozen EvidenceBundle at corpus/evidence/<subject>/bundle.json.
The wave must place the agent on the correct side of the runtime_dirty threshold (50).
"""

import json
import unittest
from pathlib import Path

from recette.behavior import AnalysisProfile, EvidenceBundle
from recette.behavior.engine import run_wave


def _wave_agent_score(bundle_dir: str, agent_id: str) -> int:
    data = json.loads((Path(bundle_dir) / "bundle.json").read_text())
    rep = run_wave(
        EvidenceBundle.from_dict(data), AnalysisProfile.from_dict({"threat": "exfil"})
    ).to_dict()
    a = next(x for x in rep["agents"] if x["agent_id"] == agent_id)
    return a["behavioral_score"]


class TestTwins(unittest.TestCase):
    def test_pr_bot_gh_is_runtime_dirty(self):
        # static_blind: pr-bot is NOT flagged by discovery but behaves dirty at runtime
        score = _wave_agent_score("corpus/evidence/gh-pr-bot", "pr-bot-gh")
        self.assertLess(
            score, 50, "pr-bot twin must be runtime-dirty (score below the dirty threshold)"
        )

    # --- Task 3: the remaining 7 twins ---

    def test_admin_overreach_gh_is_runtime_dirty(self):
        # agree_dirty: flagged by discovery AND dirty at runtime
        score = _wave_agent_score("corpus/evidence/gh-admin-overreach", "admin-overreach-gh")
        self.assertLess(
            score,
            50,
            "admin-overreach-gh must be runtime-dirty (credential + undeclared egress)",
        )

    def test_admin_overreach_gl_is_runtime_dirty(self):
        # agree_dirty: flagged by discovery AND dirty at runtime
        score = _wave_agent_score("corpus/evidence/gl-admin-overreach", "admin-overreach-gl")
        self.assertLess(
            score,
            50,
            "admin-overreach-gl must be runtime-dirty (credential + undeclared egress)",
        )

    def test_pr_bot_gl_is_runtime_dirty(self):
        # static_blind: pr-bot gl NOT flagged by discovery but behaves dirty at runtime
        score = _wave_agent_score("corpus/evidence/gl-pr-bot", "pr-bot-gl")
        self.assertLess(
            score,
            50,
            "pr-bot-gl twin must be runtime-dirty (score below the dirty threshold)",
        )

    def test_readonly_reporter_gh_is_runtime_clean(self):
        # agree_clean: NOT flagged by discovery, clean wire at runtime
        score = _wave_agent_score("corpus/evidence/gh-readonly-reporter", "readonly-reporter-gh")
        self.assertGreaterEqual(
            score,
            50,
            "readonly-reporter-gh must be runtime-clean (no credential, no undeclared egress)",
        )

    def test_readonly_reporter_gl_is_runtime_clean(self):
        # agree_clean: NOT flagged by discovery, clean wire at runtime
        score = _wave_agent_score("corpus/evidence/gl-readonly-reporter", "readonly-reporter-gl")
        self.assertGreaterEqual(
            score,
            50,
            "readonly-reporter-gl must be runtime-clean (no credential, no undeclared egress)",
        )

    def test_supply_chain_gh_is_runtime_clean(self):
        # static_overflag: flagged by discovery (CI/source compromise), runtime wire clean
        score = _wave_agent_score("corpus/evidence/gh-supply-chain-compromise", "supply-chain-gh")
        self.assertGreaterEqual(
            score,
            50,
            "supply-chain-gh must be runtime-clean (compromise is in CI/source, not wire)",
        )

    def test_supply_chain_gl_is_runtime_clean(self):
        # static_overflag: flagged by discovery (CI/source compromise), runtime wire clean
        score = _wave_agent_score("corpus/evidence/gl-supply-chain-compromise", "supply-chain-gl")
        self.assertGreaterEqual(
            score,
            50,
            "supply-chain-gl must be runtime-clean (compromise is in CI/source, not wire)",
        )
