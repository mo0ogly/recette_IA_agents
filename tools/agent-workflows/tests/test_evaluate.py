"""Behavioral contract tests; all evidence is confined to temporary fixtures."""

import copy
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from evaluate import compare, evaluate


class GateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / "subject.txt").write_text("subject")
        (self.root / "evidence.txt").write_text("synthetic test fixture")
        self.doc = {
            "method_version": "2",
            "scope_id": "fixture",
            "artifacts": {
                "subject.txt": hashlib.sha256(b"subject").hexdigest(),
                "evidence.txt": hashlib.sha256(b"synthetic test fixture").hexdigest(),
            },
            "domains": {"quality": 90, "security": 10},
            "checks": [
                {
                    "id": "q",
                    "domain": "quality",
                    "mandatory": False,
                    "gate": "validation",
                    "penalty": 10,
                    "max_penalty": 100,
                    "severity": "minor",
                },
                {
                    "id": "s",
                    "domain": "security",
                    "mandatory": True,
                    "gate": "validation",
                    "penalty": 60,
                    "max_penalty": 100,
                    "severity": "major",
                },
            ],
            "results": [
                {"id": name, "status": "PASS", "count": 0, "evidence": ["evidence.txt"]}
                for name in ("q", "s")
            ],
        }

    def run_gate(self, phase="delivery"):
        return evaluate(self.doc, self.root, phase)

    def test_complete(self):
        result = self.run_gate()
        self.assertTrue(result["allowed"])
        self.assertEqual(result["quality"], 100)
        self.assertEqual(result["progress"]["percent"], 100)

    def test_high_average_cannot_hide_major_and_domain_floor(self):
        self.doc["results"][1].update(status="FAIL", count=1)
        result = self.run_gate()
        self.assertEqual(result["quality"], 94)
        self.assertFalse(result["allowed"])
        self.assertEqual(result["max_severity"], "major")

    def test_missing_partial_and_untested_block(self):
        for status in ("PARTIEL", "NON TESTÉ"):
            with self.subTest(status=status):
                self.doc["results"][1]["status"] = status
                result = self.run_gate()
                self.assertFalse(result["allowed"])
                self.assertTrue(result["provisional"])
                self.assertEqual(result["progress"]["percent"], 50)
        self.doc["results"].pop()
        self.assertFalse(self.run_gate()["allowed"])

    def test_na_requires_reason_and_normalizes_weights(self):
        self.doc["results"][1]["status"] = "NON APPLICABLE"
        with self.assertRaises(ValueError):
            self.run_gate()
        self.doc["results"][1]["reason"] = "No security surface in this fixture"
        self.assertEqual(self.run_gate()["quality"], 100)
        self.assertEqual(self.run_gate()["progress"]["applicable"], 1)

    def test_all_na_not_success(self):
        for row in self.doc["results"]:
            row.update(status="NON APPLICABLE", reason="fixture")
        self.assertFalse(self.run_gate()["allowed"])
        self.assertIsNone(self.run_gate()["quality"])

    def test_evidence_required_and_current(self):
        self.doc["results"][0]["evidence"] = ["absent.txt"]
        with self.assertRaises(ValueError):
            self.run_gate()
        self.doc["results"][0]["evidence"] = ["evidence.txt"]
        (self.root / "subject.txt").write_text("changed")
        with self.assertRaises(ValueError):
            self.run_gate()

    def test_evidence_fingerprint_is_mandatory(self):
        del self.doc["artifacts"]["evidence.txt"]
        with self.assertRaises(ValueError):
            self.run_gate()

    def test_modified_evidence_invalidates_gate(self):
        (self.root / "evidence.txt").write_text("different conclusion")
        with self.assertRaises(ValueError):
            self.run_gate()

    def test_audit_can_finish_with_bad_quality(self):
        for row in self.doc["results"]:
            row.update(status="FAIL", count=10)
        self.assertTrue(self.run_gate("audit")["allowed"])
        self.assertFalse(self.run_gate()["allowed"])
        self.assertEqual(self.run_gate("audit")["progress"]["percent"], 0)

    def test_audit_missing_evidence_is_incomplete(self):
        self.doc["results"].pop()
        self.assertFalse(self.run_gate("audit")["allowed"])

    def test_gate_activity_failure_also_blocks_audit(self):
        self.doc["checks"][0]["domain"] = None
        self.doc["checks"][0]["mandatory"] = True
        self.doc["results"][0].update(status="FAIL", count=1)
        self.assertFalse(self.run_gate("audit")["allowed"])

    def test_entry_does_not_wait_for_future_tests(self):
        self.doc["checks"][0].update(domain=None, mandatory=True, gate="entry")
        self.doc["results"].pop()
        self.assertTrue(self.run_gate("entry")["allowed"])
        self.assertFalse(self.run_gate("validation")["allowed"])

    def test_invalid_inputs(self):
        for mutate in (
            lambda d: d["domains"].update(quality=float("nan")),
            lambda d: d["checks"][0].update(mandatory="false"),
            lambda d: d["checks"][0].update(penalty=-1),
            lambda d: d["results"][1].update(mandatory=False),
            lambda d: d["results"][0].update(count=True),
            lambda d: d["results"][0].update(status="FAIL", count=0),
            lambda d: d["results"].append(copy.deepcopy(d["results"][0])),
            lambda d: d.update(checks=[]),
            lambda d: d.update(artifacts={}),
            lambda d: d["results"][0].update(evidence=["../outside"]),
        ):
            with self.subTest(mutate=mutate):
                original = copy.deepcopy(self.doc)
                mutate(self.doc)
                with self.assertRaises(ValueError):
                    self.run_gate()
                self.doc = original

    def test_correction_reopens_gate_with_new_evidence(self):
        self.doc["results"][1].update(status="FAIL", count=1)
        self.assertFalse(self.run_gate()["allowed"])
        (self.root / "retest.txt").write_text("synthetic retest")
        self.doc["artifacts"]["retest.txt"] = hashlib.sha256(b"synthetic retest").hexdigest()
        self.doc["results"][1].update(status="PASS", count=0, evidence=["retest.txt"])
        self.assertTrue(self.run_gate()["allowed"])

    def test_comparison_only_same_method_scope_and_applicability(self):
        before = self.run_gate()
        self.doc["results"][0].update(status="FAIL", count=1)
        after = self.run_gate()
        self.assertEqual(compare(before, after), -9)
        for key in ("method_version", "config_digest", "scope_id", "applicability_digest"):
            changed = dict(before, **{key: "different"})
            self.assertIsNone(compare(changed, after))
        self.assertIsNone(compare({}, after))

    def test_cli_verdict_and_exit_codes(self):
        path = self.root / "report.json"
        command = [
            sys.executable,
            str(Path(__file__).resolve().parents[1] / "evaluate.py"),
            str(path),
            "--root",
            str(self.root),
        ]
        for failed, expected in ((False, 0), (True, 1)):
            if failed:
                self.doc["results"][1].update(status="FAIL", count=1)
            path.write_text(json.dumps(self.doc))
            process = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(process.returncode, expected, process.stderr)
            result = json.loads(process.stdout)
            self.assertEqual(result["ship_allowed"], not failed)
        path.write_text("{}")
        self.assertEqual(subprocess.run(command, capture_output=True).returncode, 2)


if __name__ == "__main__":
    unittest.main()
