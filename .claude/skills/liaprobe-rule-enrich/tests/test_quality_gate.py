"""Tests for quality_gate.py -- 17 gates G1-G17."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock

SCRIPT_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import enrich_lib as el  # noqa: E402
from quality_gate import (  # noqa: E402
    GateEngine,
    GateResult,
    GateStatus,
    StopVerdict,
    _extract_regex_set,
    gate_g1_lock_acquired,
    gate_g2_rule_schema_valid,
    gate_g3_dependency_available,
    gate_g4_state_coherent,
    gate_g5_evidence_sha256,
    gate_g6_atomic_rule_write,
    gate_g7_regex_preserved,
    gate_g8_recette_replay,
    gate_g9_onyphe_regression,
    gate_g10_score_no_regression,
    gate_g11_decision_log_appended,
    gate_g12_state_updated,
    gate_g13_metrics_recorded,
    gate_g14_score_target,
    gate_g15_all_cycles_done,
    gate_g16_budget_exhausted,
    gate_g17_consecutive_failures,
)


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


class TestPreActGates(unittest.TestCase):
    def test_g1_lock_held(self):
        lock = MagicMock()
        lock._fd = 42
        r = gate_g1_lock_acquired(lock)
        self.assertEqual(r.status, GateStatus.PASS)

    def test_g1_lock_not_held(self):
        r = gate_g1_lock_acquired(None)
        self.assertEqual(r.status, GateStatus.FAIL)
        self.assertTrue(r.blocking)

    def test_g2_schema_valid(self):
        r = gate_g2_rule_schema_valid(_valid_rule())
        self.assertEqual(r.status, GateStatus.PASS)

    def test_g2_schema_invalid(self):
        bad = _valid_rule()
        del bad["taxonomy_code"]
        r = gate_g2_rule_schema_valid(bad)
        self.assertEqual(r.status, GateStatus.FAIL)

    def test_g3_no_check(self):
        r = gate_g3_dependency_available("cycle_x", None)
        self.assertEqual(r.status, GateStatus.SKIP)

    def test_g3_dep_ok(self):
        r = gate_g3_dependency_available("cycle_x", lambda: (True, "PG up"))
        self.assertEqual(r.status, GateStatus.PASS)

    def test_g3_dep_fail(self):
        r = gate_g3_dependency_available("cycle_x", lambda: (False, "PG down"))
        self.assertEqual(r.status, GateStatus.FAIL)

    def test_g3_dep_raises(self):
        def raise_it():
            raise RuntimeError("boom")
        r = gate_g3_dependency_available("cycle_x", raise_it)
        self.assertEqual(r.status, GateStatus.FAIL)

    def test_g4_first_enrich(self):
        with TemporaryDirectory() as tmp:
            rp = Path(tmp) / "rule.json"
            rp.write_text(json.dumps(_valid_rule()))
            r = gate_g4_state_coherent(rp, {})
            self.assertEqual(r.status, GateStatus.PASS)

    def test_g4_sha_match(self):
        with TemporaryDirectory() as tmp:
            rp = Path(tmp) / "rule.json"
            rp.write_text(json.dumps(_valid_rule()))
            sha = el.sha256_file(rp)
            state = {"rule": {"rule_sha256_current": sha}}
            r = gate_g4_state_coherent(rp, state)
            self.assertEqual(r.status, GateStatus.PASS)

    def test_g4_sha_mismatch(self):
        with TemporaryDirectory() as tmp:
            rp = Path(tmp) / "rule.json"
            rp.write_text(json.dumps(_valid_rule()))
            state = {"rule": {"rule_sha256_current": "0" * 64}}
            r = gate_g4_state_coherent(rp, state)
            self.assertEqual(r.status, GateStatus.FAIL)
            self.assertTrue(r.blocking)

    def test_g4_missing_file(self):
        r = gate_g4_state_coherent(Path("/nonexistent/rule.json"), {})
        self.assertEqual(r.status, GateStatus.FAIL)


class TestPostActGates(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.tmpdir = Path(self.tmp.name)
        self.ew = el.EvidenceWriter(
            enrichment_root=self.tmpdir / "enrich",
            fingerprints_root=self.tmpdir / "fp",
            patterns_root=self.tmpdir / "patterns",
        )
        # Setup rule
        self.rule_path = self.tmpdir / "patterns" / "TEST.json"
        self.rule_path.parent.mkdir(parents=True, exist_ok=True)
        self.rule_data = _valid_rule()
        self.rule_path.write_text(json.dumps(self.rule_data))

    def tearDown(self):
        self.tmp.cleanup()

    def test_g5_evidence_sha256_valid(self):
        ev_path, _ = self.ew.write(
            rule_path=self.rule_path,
            cycle_id="cycle_5_eol",
            rule_data=self.rule_data,
            rule_sha256_before="a" * 64,
            rule_sha256_after="pending",
            source_meta={"type": "http", "url": "x"},
            raw_data=[{"k": "v"}],
            applied_diff={"added_keys": []},
            summary={},
        )
        r = gate_g5_evidence_sha256(ev_path, self.ew)
        self.assertEqual(r.status, GateStatus.PASS)

    def test_g5_evidence_missing(self):
        r = gate_g5_evidence_sha256(self.tmpdir / "nope.json", self.ew)
        self.assertEqual(r.status, GateStatus.FAIL)

    def test_g6_atomic_write_clean(self):
        r = gate_g6_atomic_rule_write(self.rule_path)
        self.assertEqual(r.status, GateStatus.PASS)

    def test_g6_orphan_tmp(self):
        tmp = self.rule_path.with_suffix(self.rule_path.suffix + ".tmp")
        tmp.write_text("orphan")
        r = gate_g6_atomic_rule_write(self.rule_path)
        self.assertEqual(r.status, GateStatus.FAIL)
        tmp.unlink()

    def test_g6_corrupt_json(self):
        self.rule_path.write_text("{ corrupt")
        r = gate_g6_atomic_rule_write(self.rule_path)
        self.assertEqual(r.status, GateStatus.FAIL)

    def test_g7_regex_preserved(self):
        before = _valid_rule()
        after = _valid_rule()
        after["lifecycle"] = {"data_source": "endoflife.date"}  # added enrich
        r = gate_g7_regex_preserved(before, after)
        self.assertEqual(r.status, GateStatus.PASS)

    def test_g7_regex_removed(self):
        before = _valid_rule()
        after = _valid_rule()
        after["banner_matchers"] = []  # regex stripped
        r = gate_g7_regex_preserved(before, after)
        self.assertEqual(r.status, GateStatus.FAIL)
        self.assertTrue(r.blocking)

    def test_g7_regex_modified(self):
        before = _valid_rule()
        after = _valid_rule()
        after["banner_matchers"][0]["value"] = "^Server: Bar"
        r = gate_g7_regex_preserved(before, after)
        self.assertEqual(r.status, GateStatus.FAIL)

    def test_g8_no_replay_fn(self):
        r = gate_g8_recette_replay("cycle_5_eol", Path("/x"), None)
        self.assertEqual(r.status, GateStatus.SKIP)
        self.assertFalse(r.blocking)

    def test_g8_replay_pass(self):
        r = gate_g8_recette_replay(
            "cycle_5_eol", Path("/x"),
            lambda p: (True, "match"),
        )
        self.assertEqual(r.status, GateStatus.PASS)

    def test_g8_replay_fail(self):
        r = gate_g8_recette_replay(
            "cycle_5_eol", Path("/x"),
            lambda p: (False, "drift"),
        )
        self.assertEqual(r.status, GateStatus.FAIL)

    def test_g9_no_dataset(self):
        r = gate_g9_onyphe_regression(self.rule_path, None)
        self.assertEqual(r.status, GateStatus.SKIP)

    def test_g9_no_matcher_fn(self):
        # dataset path that exists but no matcher_fn
        ds = self.tmpdir / "onyphe.jsonl"
        ds.write_text("")
        r = gate_g9_onyphe_regression(self.rule_path, ds, matcher_fn=None)
        self.assertEqual(r.status, GateStatus.SKIP)

    def test_g9_match_above_threshold(self):
        ds = self.tmpdir / "onyphe.jsonl"
        lines = []
        for i in range(15):
            lines.append(json.dumps({
                "banner": f"banner-{i}",
                "ground_truth": {"product": "product"},
            }))
        ds.write_text("\n".join(lines))
        # matcher returns True for 8 out of 10 sampled
        calls = {"n": 0}

        def matcher(rule, banner):
            calls["n"] += 1
            return calls["n"] <= 8
        r = gate_g9_onyphe_regression(self.rule_path, ds, sample_size=10, matcher_fn=matcher)
        self.assertEqual(r.status, GateStatus.PASS)

    def test_g9_match_below_threshold(self):
        ds = self.tmpdir / "onyphe.jsonl"
        lines = []
        for i in range(15):
            lines.append(json.dumps({
                "banner": f"banner-{i}",
                "ground_truth": {"product": "product"},
            }))
        ds.write_text("\n".join(lines))
        # matcher returns False for everything
        r = gate_g9_onyphe_regression(self.rule_path, ds, sample_size=10, matcher_fn=lambda r, b: False)
        self.assertEqual(r.status, GateStatus.FAIL)
        self.assertTrue(r.blocking)

    def test_g10_first_run(self):
        r = gate_g10_score_no_regression(None, 25.0)
        self.assertEqual(r.status, GateStatus.PASS)

    def test_g10_improvement(self):
        r = gate_g10_score_no_regression(20.0, 35.0)
        self.assertEqual(r.status, GateStatus.PASS)

    def test_g10_equality(self):
        r = gate_g10_score_no_regression(20.0, 20.0)
        self.assertEqual(r.status, GateStatus.PASS)

    def test_g10_regression(self):
        r = gate_g10_score_no_regression(35.0, 20.0)
        self.assertEqual(r.status, GateStatus.FAIL)
        self.assertTrue(r.blocking)


class TestEndAndStopGates(unittest.TestCase):
    def test_g11_log_present(self):
        with TemporaryDirectory() as tmp:
            jp = Path(tmp) / "journal.jsonl"
            jp.write_text(json.dumps({"action": "CYCLE_OK", "cycle": "cycle_5_eol"}) + "\n")
            r = gate_g11_decision_log_appended(jp, "CYCLE_OK")
            self.assertEqual(r.status, GateStatus.PASS)

    def test_g11_log_missing(self):
        r = gate_g11_decision_log_appended(Path("/nonexistent.jsonl"), "X")
        self.assertEqual(r.status, GateStatus.FAIL)
        self.assertFalse(r.blocking)

    def test_g12_completed(self):
        s_after = {"cycles": {"cycle_5_eol": {"status": "completed"}}}
        r = gate_g12_state_updated({}, s_after, "cycle_5_eol")
        self.assertEqual(r.status, GateStatus.PASS)

    def test_g12_pending(self):
        r = gate_g12_state_updated({}, {"cycles": {}}, "cycle_5_eol")
        self.assertEqual(r.status, GateStatus.FAIL)
        self.assertFalse(r.blocking)

    def test_g13_history_empty(self):
        r = gate_g13_metrics_recorded({})
        self.assertEqual(r.status, GateStatus.SKIP)

    def test_g13_history_present(self):
        r = gate_g13_metrics_recorded({"transformative_score": {"history": [{"score": 25}]}})
        self.assertEqual(r.status, GateStatus.PASS)

    def test_g14_target_reached(self):
        r = gate_g14_score_target(75.0, 70.0)
        self.assertEqual(r.status, GateStatus.PASS)

    def test_g14_target_not_reached(self):
        r = gate_g14_score_target(50.0, 70.0)
        self.assertEqual(r.status, GateStatus.SKIP)

    def test_g14_no_score(self):
        r = gate_g14_score_target(None, 70.0)
        self.assertEqual(r.status, GateStatus.SKIP)

    def test_g15_all_done(self):
        cycles_dict = {c: {"status": "completed"} for c in el.CYCLES}
        r = gate_g15_all_cycles_done({"cycles": cycles_dict})
        self.assertEqual(r.status, GateStatus.PASS)

    def test_g15_one_pending(self):
        cycles_dict = {c: {"status": "completed"} for c in el.CYCLES}
        cycles_dict[el.CYCLES[0]] = {"status": "pending"}
        r = gate_g15_all_cycles_done({"cycles": cycles_dict})
        self.assertEqual(r.status, GateStatus.SKIP)

    def test_g16_exhausted(self):
        r = gate_g16_budget_exhausted(12, 12)
        self.assertEqual(r.status, GateStatus.PASS)

    def test_g16_within_budget(self):
        r = gate_g16_budget_exhausted(5, 12)
        self.assertEqual(r.status, GateStatus.SKIP)

    def test_g17_threshold_reached(self):
        r = gate_g17_consecutive_failures(2, threshold=2)
        self.assertEqual(r.status, GateStatus.PASS)

    def test_g17_below_threshold(self):
        r = gate_g17_consecutive_failures(1, threshold=2)
        self.assertEqual(r.status, GateStatus.SKIP)


class TestExtractRegexSet(unittest.TestCase):
    def test_extracts_from_banner_matchers(self):
        rule = {"banner_matchers": [{"target": "raw", "value": "^Server: Foo"}]}
        s = _extract_regex_set(rule)
        self.assertEqual(s, {"^Server: Foo"})

    def test_extracts_from_probes(self):
        rule = {
            "probes": [{
                "id": "p1",
                "matchers": [{"target": "body", "value": "Bar"}],
            }],
        }
        s = _extract_regex_set(rule)
        self.assertEqual(s, {"Bar"})

    def test_dedup_across_keys(self):
        rule = {
            "banner_matchers": [{"value": "X"}],
            "service_matchers": [{"value": "X"}],
        }
        s = _extract_regex_set(rule)
        self.assertEqual(s, {"X"})

    def test_skips_non_string(self):
        rule = {"banner_matchers": [{"value": 42}, {"value": None}]}
        s = _extract_regex_set(rule)
        self.assertEqual(s, set())


class TestGateEngineOrchestration(unittest.TestCase):
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
        self.engine = GateEngine(self.rule_path, self.sm, self.ew)

    def tearDown(self):
        self.tmp.cleanup()

    def test_run_pre_act_records_history(self):
        lock = MagicMock()
        lock._fd = 1
        rule = _valid_rule()
        results = self.engine.run_pre_act("cycle_5_eol", rule, lock)
        self.assertEqual(len(results), 4)
        self.assertEqual(len(self.engine.history), 4)

    def test_all_pass_helper(self):
        results = [GateResult("X", GateStatus.PASS, ""), GateResult("Y", GateStatus.SKIP, "")]
        self.assertTrue(GateEngine.all_pass(results))
        results.append(GateResult("Z", GateStatus.FAIL, "", blocking=True))
        self.assertFalse(GateEngine.all_pass(results))

    def test_any_blocking_fail(self):
        results = [GateResult("X", GateStatus.FAIL, "", blocking=False)]
        self.assertFalse(GateEngine.any_blocking_fail(results))
        results.append(GateResult("Y", GateStatus.FAIL, "", blocking=True))
        self.assertTrue(GateEngine.any_blocking_fail(results))

    def test_run_stop_target_reached(self):
        verdict, gates = self.engine.run_stop(
            score=80.0, target=70.0, iter_count=1, max_iter=10, consecutive_failures=0,
        )
        self.assertEqual(verdict, StopVerdict.STOP_SUCCESS)

    def test_run_stop_budget(self):
        verdict, _ = self.engine.run_stop(
            score=10.0, target=70.0, iter_count=12, max_iter=12, consecutive_failures=0,
        )
        self.assertEqual(verdict, StopVerdict.STOP_BUDGET)

    def test_run_stop_replan(self):
        verdict, _ = self.engine.run_stop(
            score=10.0, target=70.0, iter_count=1, max_iter=12, consecutive_failures=2,
        )
        self.assertEqual(verdict, StopVerdict.STOP_REPLAN)

    def test_run_stop_continue(self):
        verdict, _ = self.engine.run_stop(
            score=10.0, target=70.0, iter_count=1, max_iter=12, consecutive_failures=0,
        )
        self.assertEqual(verdict, StopVerdict.CONTINUE)


class TestGateEngineRunEnd(unittest.TestCase):
    """Tests for GateEngine.run_end() -- G11+G12+G13 wired (A1 fix)."""

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
        self.engine = GateEngine(self.rule_path, self.sm, self.ew)

    def tearDown(self):
        self.tmp.cleanup()

    def test_run_end_invokes_g11_g12_g13(self):
        journal_path = self.tmpdir / "journal.jsonl"
        journal_path.write_text(json.dumps({
            "action": "CYCLE_OK", "cycle": "cycle_5_eol",
        }) + "\n")
        state_before = {"cycles": {}}
        state_after = {
            "cycles": {"cycle_5_eol": {"status": "completed"}},
            "transformative_score": {"history": [{"score": 15}]},
        }
        results = self.engine.run_end(
            cycle_id="cycle_5_eol",
            state_before=state_before,
            state_after=state_after,
            journal_path=journal_path,
            action="CYCLE_OK",
        )
        self.assertEqual(len(results), 3)
        gate_ids = [r.gate_id for r in results]
        self.assertEqual(gate_ids, ["G11_decision_log", "G12_state_updated", "G13_metrics_recorded"])
        # All non-blocking
        self.assertTrue(all(not r.blocking for r in results))

    def test_run_end_no_journal_skips_g11(self):
        results = self.engine.run_end(
            cycle_id="cycle_5_eol",
            state_before={"cycles": {}},
            state_after={"cycles": {"cycle_5_eol": {"status": "completed"}}},
            journal_path=None,
        )
        self.assertEqual(len(results), 3)
        self.assertEqual(results[0].gate_id, "G11_decision_log")
        self.assertEqual(results[0].status, GateStatus.SKIP)

    def test_run_end_history_recorded(self):
        results = self.engine.run_end(
            cycle_id="cycle_5_eol",
            state_before={},
            state_after={"cycles": {"cycle_5_eol": {"status": "completed"}}},
        )
        # Should be recorded in self.history
        engine_history_after = len(self.engine.history)
        self.assertEqual(engine_history_after, 3)


if __name__ == "__main__":
    unittest.main(verbosity=2)
