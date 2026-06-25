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

    def test_discovery_cohort_detected_and_flagged(self):
        from recette.behavior.correlate import discovery_cohort
        from recette.behavior.links import load_links

        links = load_links()
        detected = discovery_cohort(links, "detected")
        flagged = discovery_cohort(links, "flagged")
        # both sorted + deduped
        self.assertEqual(detected, sorted(set(detected)))
        self.assertEqual(flagged, sorted(set(flagged)))
        # flagged is a subset of detected
        self.assertTrue(set(flagged).issubset(set(detected)))
        # admin-overreach (gh + gl) are high-risk repos -> both in flagged
        # agent_ids are surface-qualified: admin-overreach-gh, admin-overreach-gl
        self.assertIn("admin-overreach-gh", flagged)
        self.assertIn("admin-overreach-gl", flagged)
        # replay-stable
        self.assertEqual(discovery_cohort(links, "flagged"), flagged)

    def test_discovery_cohort_bad_mode_raises(self):
        from recette.behavior.correlate import discovery_cohort
        from recette.behavior.links import load_links

        with self.assertRaises(ValueError):
            discovery_cohort(load_links(), "bogus")

    def test_resolve_cohort_into_profile(self):
        from recette.behavior import AnalysisProfile
        from recette.cli.behavior_cmds import resolve_discovery_cohort

        prof = AnalysisProfile.from_dict({"threat": "exfil"})
        resolved = resolve_discovery_cohort(prof, "flagged")
        # With the full 10-link corpus, admin-overreach subjects are surface-qualified.
        # Both gh and gl variants are high-risk -> both appear in the flagged cohort.
        agents = prof.cohort.get("agents", [])
        self.assertIn("admin-overreach-gh", agents)
        self.assertIn("admin-overreach-gl", agents)
        self.assertEqual(resolved["mode"], "flagged")
        self.assertEqual(sorted(resolved["agents"]), sorted(prof.cohort["agents"]))

    def test_build_discovery_facts_surface_aware(self):
        from recette.behavior.correlate import build_discovery_facts
        from recette.behavior.links import load_links

        facts = build_discovery_facts(load_links())
        # gitlab subject resolves (was invisible before surface-awareness)
        self.assertIn("gl-pr-bot", facts)
        self.assertTrue(facts["gl-pr-bot"]["detected"])
        # flagged split per verified levels: admin/supply flagged; pr-bot/readonly not
        self.assertTrue(facts["gh-admin-overreach"]["flagged"])
        self.assertTrue(facts["gh-supply-chain-compromise"]["flagged"])
        self.assertFalse(facts["gh-pr-bot"]["flagged"])
        self.assertFalse(facts["gh-readonly-reporter"]["flagged"])

    def test_cli_correlate_renders_static_blind(self):
        from recette.cli.behavior_cmds import correlate_summary

        rep = {
            "rows": [
                {
                    "agent_id": "pr-bot",
                    "static_flagged": False,
                    "runtime_dirty": True,
                    "behavioral_score": 80,
                    "quadrant": "static_blind",
                    "agreement": False,
                }
            ],
            "quadrants": {
                "agree_clean": 0,
                "agree_dirty": 0,
                "static_blind": ["pr-bot"],
                "static_overflag": [],
            },
            "unresolved": [],
            "coverage_gaps": [],
            "thresholds": {"runtime_dirty": 50},
            "tool_version": "behavior-engine/1",
        }
        text = correlate_summary(rep)
        self.assertIn("static_blind", text)
        self.assertIn("pr-bot", text)
