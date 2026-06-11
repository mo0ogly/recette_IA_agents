#!/usr/bin/env python3
# test_nightly_skip.py -- Unit tests for nightly batch dead-vendor skip.
# Run: PYTHONPATH=. python3 -m unittest test_nightly_skip -v

import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock


def _load_nightly_module():
    """Load nightly_fingerprint_batch.sh as a Python module (it is .sh by name but .py by content)."""
    path = Path(__file__).resolve().parent / "nightly_fingerprint_batch.sh"
    spec = importlib.util.spec_from_loader(
        "_nightly_batch_under_test",
        importlib.machinery.SourceFileLoader("_nightly_batch_under_test", str(path)),
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_rule(patterns_dir: Path, code: str, vendor_dead: bool = False, **extra) -> Path:
    rule = {
        "taxonomy_code": code,
        "product": code.replace("_", " ").title(),
        "vendor": "TestVendor",
        "vendor_website": f"https://{code.lower()}.example",
        "enabled": False if vendor_dead else True,
        "_lia_independent_authoring": {
            "operator": "test",
        },
    }
    if vendor_dead:
        rule["_lia_independent_authoring"]["vendor_dead"] = {
            "since": "2026-05-12T00:00:00Z",
            "reason": "infra_persistent",
            "evidence": "DNS not found",
            "marked_by": "test",
        }
    rule.update(extra)
    path = patterns_dir / f"{code}.json"
    path.write_text(json.dumps(rule, indent=2))
    return path


class GetNextProductsSkipTests(unittest.TestCase):

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmp.name)
        self.patterns_dir = self.tmp_path / "patterns/web-signatures"
        self.patterns_dir.mkdir(parents=True)
        self.master_todo = self.tmp_path / "MASTER_TODO_LIST.md"
        self.master_todo.write_text(
            "| [.] FILE_ONLY | ALIVE_VENDOR_A | - | - |\n"
            "| [.] FILE_ONLY | DEAD_VENDOR_B | - | - |\n"
            "| [.] FILE_ONLY | ALIVE_VENDOR_C | - | - |\n"
            "| [.] FILE_ONLY | DEAD_VENDOR_D | - | - |\n"
            "| [.] FILE_ONLY | NO_DISK_FILE_E | - | - |\n"
        )
        _write_rule(self.patterns_dir, "ALIVE_VENDOR_A", vendor_dead=False)
        _write_rule(self.patterns_dir, "DEAD_VENDOR_B", vendor_dead=True)
        _write_rule(self.patterns_dir, "ALIVE_VENDOR_C", vendor_dead=False)
        _write_rule(self.patterns_dir, "DEAD_VENDOR_D", vendor_dead=True)
        # NO_DISK_FILE_E has no .json on disk -- should still be returned

        # Load module under test
        self.module = _load_nightly_module()
        self.module.MASTER_TODO = self.master_todo
        self.module.PATTERNS_DIR = self.patterns_dir
        # Suppress vendor-url HTTP resolution to keep tests offline.
        self.module.RESOLVE_VENDOR_URL = "off"
        # Capture log
        self.log_lines = []
        self.module.log = lambda msg: self.log_lines.append(msg)

    def tearDown(self):
        self.tmp.cleanup()

    def test_skips_dead_vendor_rules(self):
        products = self.module.get_next_products(10)
        codes = [p["taxonomy_code"] for p in products]
        self.assertIn("ALIVE_VENDOR_A", codes)
        self.assertIn("ALIVE_VENDOR_C", codes)
        self.assertIn("NO_DISK_FILE_E", codes,
                      "Rule without disk file must still be processable (new authoring)")
        self.assertNotIn("DEAD_VENDOR_B", codes)
        self.assertNotIn("DEAD_VENDOR_D", codes)

    def test_skip_count_logged(self):
        self.module.get_next_products(10)
        # Expect log message about skipped dead vendors
        matches = [ln for ln in self.log_lines if "skipped" in ln and "dead-vendor" in ln]
        self.assertTrue(matches, f"Expected log line about skipped dead vendors. Got: {self.log_lines}")
        self.assertIn("2", matches[0],
                      f"Should report 2 skipped (B and D). Got: {matches[0]}")

    def test_n_limit_respects_skip(self):
        """If n=1, we must return 1 alive product, not 1 skipped + 0 alive."""
        products = self.module.get_next_products(1)
        self.assertEqual(len(products), 1)
        self.assertEqual(products[0]["taxonomy_code"], "ALIVE_VENDOR_A")

    def test_n_limit_2(self):
        products = self.module.get_next_products(2)
        self.assertEqual(len(products), 2)
        self.assertEqual([p["taxonomy_code"] for p in products],
                         ["ALIVE_VENDOR_A", "ALIVE_VENDOR_C"])


if __name__ == "__main__":
    unittest.main()
