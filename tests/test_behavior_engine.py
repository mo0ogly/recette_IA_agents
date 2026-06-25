"""P1 of the behavioral-analysis engine: evidence bundle hashing, profile knobs,
the lens registry (including the two behavioral lenses sequence & baseline), the
wave runner, and the replay (byte-equality) proof. Pure (I4): zero install beyond
the suite. Design: docs/plans/2026-06-25-behavioral-analysis-engine-design.md
"""

from __future__ import annotations

import json
import unittest

from recette.behavior import AnalysisProfile, EvidenceBundle
from recette.behavior.engine import replay, run_wave


def _bundle(**over: object) -> EvidenceBundle:
    base = {
        "recording": {
            "recordings": [
                {
                    "agent_id": "exfil-bot",
                    "surfaces": {
                        "ebpf_wire": [
                            "connect:127.0.0.1:9101",
                            "open:/home/bot/.aws/credentials",
                            "connect:8.8.8.8:443",
                            "connect:13.37.13.37:443",
                        ]
                    },
                },
                {"agent_id": "good-bot", "surfaces": {"ebpf_wire": ["connect:127.0.0.1:9101"]}},
            ]
        },
        "servers": [{"id": "gh-mock", "mode": "mock_local", "port": 9101}],
        "declared": {
            "exfil-bot": {
                "scope": ["read_repo"],
                "systems": ["gh-mock"],
                "decided": ["read_repo", "push"],
            },
            "good-bot": {"scope": ["read_repo"], "systems": ["gh-mock"], "decided": ["read_repo"]},
        },
        "baselines": {},
    }
    base.update(over)  # type: ignore[arg-type]
    return EvidenceBundle.from_dict(base)


class TestEvidenceBundle(unittest.TestCase):
    def test_hash_is_stable_and_content_addressed(self) -> None:
        a, b = _bundle(), _bundle()
        self.assertEqual(a.evidence_hash(), b.evidence_hash())
        self.assertTrue(a.evidence_hash().startswith("sha256:"))
        # a different recording -> a different hash
        c = _bundle(recording={"recordings": []})
        self.assertNotEqual(a.evidence_hash(), c.evidence_hash())

    def test_wire_tokens_preserve_order(self) -> None:
        tokens = _bundle().wire_tokens("exfil-bot")
        self.assertEqual(tokens[0], "connect:127.0.0.1:9101")
        self.assertEqual(tokens[1], "open:/home/bot/.aws/credentials")


class TestProfile(unittest.TestCase):
    def test_unknown_lens_rejected(self) -> None:
        with self.assertRaises(ValueError):
            AnalysisProfile.from_dict({"lenses": ["egress", "bogus"]})

    def test_unknown_threat_rejected(self) -> None:
        with self.assertRaises(ValueError):
            AnalysisProfile.from_dict({"threat": "nope"})

    def test_threat_reweights_score(self) -> None:
        bundle = _bundle()
        exfil = run_wave(bundle, AnalysisProfile.from_dict({"threat": "exfil"}))
        neutral = run_wave(bundle, AnalysisProfile.from_dict({"threat": "neutral"}))
        exfil_score = next(a for a in exfil.agents if a.agent_id == "exfil-bot").behavioral_score
        neutral_score = next(
            a for a in neutral.agents if a.agent_id == "exfil-bot"
        ).behavioral_score
        # exfil weighting penalizes the exfil lenses harder -> not a higher score
        self.assertLessEqual(exfil_score, neutral_score)


class TestWave(unittest.TestCase):
    def test_exfil_bot_divergent_good_bot_clean(self) -> None:
        d = run_wave(_bundle(), AnalysisProfile.from_dict({"threat": "exfil"})).to_dict()
        by_id = {a["agent_id"]: a for a in d["agents"]}
        self.assertFalse(by_id["exfil-bot"]["coherent"])
        self.assertEqual(by_id["exfil-bot"]["behavioral_score"], 0)
        self.assertTrue(by_id["good-bot"]["coherent"])
        self.assertEqual(by_id["good-bot"]["behavioral_score"], 100)

    def test_sequence_lens_detects_exfil_chain(self) -> None:
        d = run_wave(_bundle(), AnalysisProfile.from_dict({"threat": "exfil"})).to_dict()
        seq = [f for a in d["agents"] for f in a["findings"] if f["lens"] == "sequence"]
        self.assertEqual(len(seq), 1)
        self.assertIn("exfil chain", seq[0]["log"])
        self.assertEqual(seq[0]["mitre_atlas"], "AML.T0086")

    def test_credential_and_doh_lenses_tagged(self) -> None:
        d = run_wave(_bundle(), AnalysisProfile.from_dict({"threat": "exfil"})).to_dict()
        lenses = {f["lens"]: f for a in d["agents"] for f in a["findings"]}
        self.assertEqual(lenses["credential"]["owasp_asi"], "ASI03")
        self.assertEqual(lenses["doh"]["owasp_asi"], "ASI02")

    def test_baseline_lens_flags_novel_server(self) -> None:
        bundle = _bundle(
            recording={
                "recordings": [
                    {
                        "agent_id": "good-bot",
                        "surfaces": {"ebpf_wire": ["connect:127.0.0.1:9101"]},
                    }
                ]
            },
            baselines={"good-bot": {"servers": ["other-mock"], "max_connects": 5}},
        )
        d = run_wave(bundle, AnalysisProfile.from_dict({"lenses": ["baseline"]})).to_dict()
        good = next(a for a in d["agents"] if a["agent_id"] == "good-bot")
        self.assertTrue(any("new server gh-mock" in f["log"] for f in good["findings"]))

    def test_baseline_lens_noop_without_baseline(self) -> None:
        # no baseline provided -> the lens emits nothing (not a false positive)
        d = run_wave(_bundle(), AnalysisProfile.from_dict({"lenses": ["baseline"]})).to_dict()
        self.assertTrue(all(not a["findings"] for a in d["agents"]))

    def test_ghost_host_tolerance_suppresses_egress(self) -> None:
        prof = AnalysisProfile.from_dict(
            {"lenses": ["egress"], "thresholds": {"ghost_host_tolerance": 5}}
        )
        d = run_wave(_bundle(), prof).to_dict()
        self.assertTrue(all(not a["findings"] for a in d["agents"]))

    def test_muted_lens_via_off_threshold(self) -> None:
        prof = AnalysisProfile.from_dict({"thresholds": {"credential": "off"}})
        d = run_wave(_bundle(), prof).to_dict()
        self.assertFalse(any(f["lens"] == "credential" for a in d["agents"] for f in a["findings"]))

    def test_cohort_restricts_agents(self) -> None:
        prof = AnalysisProfile.from_dict({"cohort": {"agents": ["good-bot"]}})
        d = run_wave(_bundle(), prof).to_dict()
        self.assertEqual([a["agent_id"] for a in d["agents"]], ["good-bot"])

    def test_said_scope_lax_vs_strict(self) -> None:
        # exfil-bot dialed only its declared server -> lax suppresses the said_scope finding
        strict = run_wave(
            _bundle(), AnalysisProfile.from_dict({"lenses": ["said_scope"]})
        ).to_dict()
        lax = run_wave(
            _bundle(),
            AnalysisProfile.from_dict({"lenses": ["said_scope"], "thresholds": {"scope": "lax"}}),
        ).to_dict()
        strict_n = sum(len(a["findings"]) for a in strict["agents"])
        lax_n = sum(len(a["findings"]) for a in lax["agents"])
        self.assertGreater(strict_n, lax_n)


class TestReplay(unittest.TestCase):
    def test_replay_is_byte_identical(self) -> None:
        bundle = _bundle()
        prof = AnalysisProfile.from_dict({"threat": "exfil"})
        a = run_wave(bundle, prof).to_dict()
        b = run_wave(bundle, prof).to_dict()
        self.assertEqual(json.dumps(a, sort_keys=True), json.dumps(b, sort_keys=True))
        self.assertTrue(replay(bundle, prof, a))

    def test_experiment_id_pins_evidence_profile_version(self) -> None:
        rep = run_wave(_bundle(), AnalysisProfile.from_dict({"threat": "exfil"}))
        eid = rep.to_dict()["experiment_id"]
        self.assertIn(rep.evidence_hash, eid)
        self.assertIn(rep.profile_hash, eid)
        self.assertIn(rep.tool_version, eid)


if __name__ == "__main__":
    unittest.main()
