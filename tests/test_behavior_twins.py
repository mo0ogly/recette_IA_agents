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
