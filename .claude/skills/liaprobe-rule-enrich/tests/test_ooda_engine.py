"""Tests for ooda_engine.py -- decision, scoring, OODA orchestration."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

SCRIPT_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import enrich_lib as el  # noqa: E402
from ooda_engine import (  # noqa: E402
    CYCLE_PRIORITIES,
    SECTION_WEIGHTS,
    Decision,
    OODAEngine,
    OODAResult,
    compute_transformative_score,
    decide_next_action,
)
from quality_gate import StopVerdict  # noqa: E402


def _valid_rule() -> dict:
    return {
        "$schema": "lia-fingerprint-v1",
        "id": "lia_test",
        "vendor": "Vendor",
        "product": "Product",
        "category": "Web",
        "taxonomy_code": "WEB.HTTP_SERVER",
        "banner_matchers": [
            {"target": "raw", "op": "regex", "value": "^Server: Foo"},
        ],
        "probes": [],
    }


class TestComputeScore(unittest.TestCase):
    def test_empty_rule(self):
        self.assertEqual(compute_transformative_score({}), 0.0)

    def test_only_known_cves(self):
        rule = {"known_cves": [{"cve_id": "CVE-2025-1"}]}
        # 25 weight
        self.assertEqual(compute_transformative_score(rule), 25.0)

    def test_lifecycle_only(self):
        rule = {"lifecycle": {"latest_cycle": "1.0"}}
        self.assertEqual(compute_transformative_score(rule), 15.0)

    def test_combined_top3(self):
        rule = {
            "known_cves": [{"cve_id": "X"}],     # 25
            "attack_surface": {"techniques": [{"id": "T1"}]},  # 20
            "lifecycle": {"latest_cycle": "1.0"},  # 15
        }
        self.assertEqual(compute_transformative_score(rule), 60.0)

    def test_empty_list_excluded(self):
        rule = {"known_cves": []}  # empty list -> not counted
        self.assertEqual(compute_transformative_score(rule), 0.0)

    def test_empty_dict_excluded(self):
        rule = {"lifecycle": {}}
        self.assertEqual(compute_transformative_score(rule), 0.0)

    def test_all_sections_max(self):
        rule = {k: [{"id": "x"}] for k in SECTION_WEIGHTS}
        # All sections present -> sum of weights
        self.assertEqual(compute_transformative_score(rule), float(sum(SECTION_WEIGHTS.values())))


class TestDecideNextAction(unittest.TestCase):
    def test_target_reached_stops(self):
        d = decide_next_action({"cycles": {}}, score=80.0, target=70.0)
        self.assertEqual(d.action, "STOP")

    def test_pending_cycle_4_first(self):
        d = decide_next_action({"cycles": {}}, score=0.0, target=70.0)
        self.assertEqual(d.action, "RUN_CYCLE")
        self.assertEqual(d.cycle_id, "cycle_4_cve")  # priority 60 = highest

    def test_cycle_7_blocked_until_4_done(self):
        state = {"cycles": {"cycle_4_cve": {"status": "pending"}}}
        d = decide_next_action(state, score=0.0, target=70.0)
        # 4 should run before 7
        self.assertEqual(d.cycle_id, "cycle_4_cve")

    def test_cycle_7_unlocked_when_4_completed(self):
        state = {"cycles": {
            "cycle_4_cve": {"status": "completed"},
            "cycle_5_eol": {"status": "completed"},
        }}
        d = decide_next_action(state, score=40.0, target=70.0)
        self.assertEqual(d.action, "RUN_CYCLE")
        # cycle_7 has priority 50, next highest pending
        self.assertEqual(d.cycle_id, "cycle_7_mitre")

    def test_all_done_stops(self):
        state = {"cycles": {c: {"status": "completed"} for c in CYCLE_PRIORITIES}}
        d = decide_next_action(state, score=40.0, target=70.0)
        self.assertEqual(d.action, "STOP")
        self.assertIn("all cycles done", d.reason)

    def test_skipped_cycles_count_as_done(self):
        state = {"cycles": {c: {"status": "skipped"} for c in CYCLE_PRIORITIES}}
        d = decide_next_action(state, score=10.0, target=70.0)
        self.assertEqual(d.action, "STOP")

    def test_priority_order(self):
        # Verify CYCLE_PRIORITIES dict values
        self.assertEqual(CYCLE_PRIORITIES["cycle_4_cve"], 60)
        self.assertEqual(CYCLE_PRIORITIES["cycle_7_mitre"], 50)
        self.assertEqual(CYCLE_PRIORITIES["cycle_5_eol"], 40)


class TestOODAEngineRunBudget(unittest.TestCase):
    """Test STOP_BUDGET path: handler always fails, max_iter exhausted."""

    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.tmpdir = Path(self.tmp.name)
        self.rule_path = self.tmpdir / "patterns" / "TEST.json"
        self.rule_path.parent.mkdir(parents=True, exist_ok=True)
        self.rule_path.write_text(json.dumps(_valid_rule()))
        self.sm = el.StateManager(self.tmpdir / "state")
        self.ew = el.EvidenceWriter(
            enrichment_root=self.tmpdir / "enrich",
            fingerprints_root=self.tmpdir / "fp",
            patterns_root=self.tmpdir / "patterns",
        )

    def tearDown(self):
        self.tmp.cleanup()

    def test_stop_complete_no_handlers(self):
        # All cycles handlers missing -> all skipped -> STOP_COMPLETE path
        engine = OODAEngine(
            rule_path=self.rule_path,
            state_manager=self.sm,
            evidence_writer=self.ew,
            cycle_handlers={},  # nothing registered
            target_score=70.0,
            max_iter=15,
        )
        result = engine.run()
        self.assertIsInstance(result, OODAResult)
        # all cycles should be skipped
        self.assertEqual(len(result.cycles_skipped), len(CYCLE_PRIORITIES))
        self.assertEqual(result.verdict, StopVerdict.STOP_COMPLETE)


class TestOODAEngineRunSuccess(unittest.TestCase):
    """Test STOP_SUCCESS path: handler boosts score above target."""

    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.tmpdir = Path(self.tmp.name)
        self.rule_path = self.tmpdir / "patterns" / "TEST.json"
        self.rule_path.parent.mkdir(parents=True, exist_ok=True)
        self.rule_path.write_text(json.dumps(_valid_rule()))
        self.sm = el.StateManager(self.tmpdir / "state")
        self.ew = el.EvidenceWriter(
            enrichment_root=self.tmpdir / "enrich",
            fingerprints_root=self.tmpdir / "fp",
            patterns_root=self.tmpdir / "patterns",
        )

    def tearDown(self):
        self.tmp.cleanup()

    def test_stop_success_when_score_boost(self):
        from enrich_lib import AtomicJSONWriter, sha256_file, utc_now_iso

        def fake_handler(rule_path, rule_data, ew, sm, lock):
            """Add known_cves (25) + lifecycle (15) + attack_surface (20) = 60 >> 50."""
            rule_after = dict(rule_data)
            rule_after["known_cves"] = [{"cve_id": "CVE-2025-1", "severity": "HIGH"}]
            rule_after["lifecycle"] = {"data_source": "endoflife.date", "latest_cycle": "2.0"}
            rule_after["attack_surface"] = {"techniques": [{"id": "T1"}]}
            sha_before = sha256_file(rule_path)
            ev_path, ev_sha = ew.write(
                rule_path=rule_path,
                cycle_id="cycle_4_cve",
                rule_data=rule_data,
                rule_sha256_before=sha_before,
                rule_sha256_after="pending",
                source_meta={"type": "postgresql"},
                raw_data=[{"cve_id": "CVE-2025-1"}],
                applied_diff={"added_keys": ["known_cves"]},
                summary={"cve_count": 1},
            )
            AtomicJSONWriter.write(rule_path, rule_after)
            sm.mark_cycle_done(rule_path, "cycle_4_cve", ev_path, ev_sha,
                               summary={"cve_count": 1})
            return True, {"added_keys": ["known_cves"]}, {"cve_count": 1}

        engine = OODAEngine(
            rule_path=self.rule_path,
            state_manager=self.sm,
            evidence_writer=self.ew,
            cycle_handlers={"cycle_4_cve": fake_handler},
            target_score=50.0,
            max_iter=5,
        )
        result = engine.run()
        self.assertEqual(result.verdict, StopVerdict.STOP_SUCCESS)
        self.assertGreaterEqual(result.final_score, 50.0)
        self.assertIn("cycle_4_cve", result.cycles_completed)


class TestOODAEngineReplan(unittest.TestCase):
    """Test STOP_REPLAN: 2 consecutive failures."""

    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.tmpdir = Path(self.tmp.name)
        self.rule_path = self.tmpdir / "patterns" / "TEST.json"
        self.rule_path.parent.mkdir(parents=True, exist_ok=True)
        self.rule_path.write_text(json.dumps(_valid_rule()))
        self.sm = el.StateManager(self.tmpdir / "state")
        self.ew = el.EvidenceWriter(
            enrichment_root=self.tmpdir / "enrich",
            fingerprints_root=self.tmpdir / "fp",
            patterns_root=self.tmpdir / "patterns",
        )

    def tearDown(self):
        self.tmp.cleanup()

    def test_handler_raises_triggers_failure(self):
        """Handler that raises -> rolled back, marked failed."""

        def raising_handler(rule_path, rule_data, ew, sm, lock):
            raise RuntimeError("boom")

        # Register handlers that always raise -> 2 failures = STOP_REPLAN
        engine = OODAEngine(
            rule_path=self.rule_path,
            state_manager=self.sm,
            evidence_writer=self.ew,
            cycle_handlers={
                "cycle_4_cve": raising_handler,
                "cycle_5_eol": raising_handler,
            },
            target_score=99.0,
            max_iter=10,
        )
        result = engine.run()
        # After 2 raises, consecutive_failures=2 triggers STOP_REPLAN
        self.assertEqual(result.verdict, StopVerdict.STOP_REPLAN)
        self.assertGreaterEqual(len(result.cycles_failed), 2)
        # rule.json must be valid (rolled back)
        loaded = json.loads(self.rule_path.read_text())
        self.assertEqual(loaded["id"], "lia_test")
        # No .bak orphan
        self.assertFalse(self.rule_path.with_suffix(".json.bak").exists())


class TestRollback(unittest.TestCase):
    def test_rollback_restores_original_content(self):
        with TemporaryDirectory() as tmp:
            tmpdir = Path(tmp)
            rp = tmpdir / "patterns" / "TEST.json"
            rp.parent.mkdir(parents=True, exist_ok=True)
            original = json.dumps(_valid_rule())
            rp.write_text(original)
            sm = el.StateManager(tmpdir / "state")
            ew = el.EvidenceWriter(
                enrichment_root=tmpdir / "enrich",
                fingerprints_root=tmpdir / "fp",
                patterns_root=tmpdir / "patterns",
            )
            engine = OODAEngine(rp, sm, ew, {})
            # Simulate corrupted rule + .bak holds correct
            bak = rp.with_suffix(rp.suffix + ".bak")
            bak.write_text(original)
            rp.write_text("{ corrupt")
            engine._rollback(bak)
            restored = rp.read_text()
            self.assertEqual(restored, original)
            self.assertFalse(bak.exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
