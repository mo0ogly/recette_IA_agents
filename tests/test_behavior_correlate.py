import json
import unittest

from recette.behavior.correlate import correlate
from recette.behavior.links import Link


def _link(agent_id, disc, runtime, expected):
    return Link(
        agent_id=agent_id,
        discovery_subject=disc,
        runtime_subject=runtime,
        evidence_bundle=None,
        expected=expected,
    )


class TestCorrelate(unittest.TestCase):
    def setUp(self):
        # source clean (not flagged), runtime dirty (score 80 > 50) -> static_blind
        self.discovery_facts = {
            "gh-pr-bot": {"detected": True, "flagged": False},
            "gh-admin-overreach": {"detected": True, "flagged": True},
        }
        self.behavior_reports = {
            "pr-bot": {"agent_id": "pr-bot", "behavioral_score": 80, "coherent": False},
            "admin-overreach": {
                "agent_id": "admin-overreach",
                "behavioral_score": 90,
                "coherent": False,
            },
        }
        self.links = [
            _link("pr-bot", "gh-pr-bot", "x", {}),
            _link("admin-overreach", "gh-admin-overreach", "x", {}),
            _link("ghost", "gh-missing", "x", {}),  # discovery_facts has no gh-missing
        ]
        self.thresholds = {"runtime_dirty": 50}

    def test_static_blind_quadrant(self):
        rep = correlate(self.discovery_facts, self.behavior_reports, self.links, self.thresholds)
        row = next(r for r in rep["rows"] if r["agent_id"] == "pr-bot")
        self.assertFalse(row["static_flagged"])
        self.assertTrue(row["runtime_dirty"])
        self.assertEqual(row["quadrant"], "static_blind")
        self.assertIn("pr-bot", rep["quadrants"]["static_blind"])

    def test_agree_dirty_quadrant(self):
        rep = correlate(self.discovery_facts, self.behavior_reports, self.links, self.thresholds)
        row = next(r for r in rep["rows"] if r["agent_id"] == "admin-overreach")
        self.assertEqual(row["quadrant"], "agree_dirty")
        self.assertTrue(row["agreement"])

    def test_unresolved_link_is_loud_not_a_quadrant(self):
        rep = correlate(self.discovery_facts, self.behavior_reports, self.links, self.thresholds)
        reasons = {u["agent_id"]: u["reason"] for u in rep["unresolved"]}
        self.assertEqual(reasons.get("ghost"), "discovery_missing")
        # the ghost agent never appears in any quadrant
        all_quadrant_ids = sum((v for v in rep["quadrants"].values() if isinstance(v, list)), [])
        self.assertNotIn("ghost", all_quadrant_ids)

    def test_replay_byte_identical(self):
        a = correlate(self.discovery_facts, self.behavior_reports, self.links, self.thresholds)
        b = correlate(self.discovery_facts, self.behavior_reports, self.links, self.thresholds)
        self.assertEqual(json.dumps(a, sort_keys=True), json.dumps(b, sort_keys=True))

    def test_build_discovery_facts_over_corpus(self):
        from recette.behavior.correlate import build_discovery_facts
        from recette.behavior.links import load_links

        facts = build_discovery_facts(load_links())
        # gh-pr-bot is a detected agent repo in the corpus
        self.assertIn("gh-pr-bot", facts)
        self.assertTrue(facts["gh-pr-bot"]["detected"])
        # gh-admin-overreach is the high-risk overreach repo -> flagged
        self.assertTrue(facts["gh-admin-overreach"]["flagged"])
