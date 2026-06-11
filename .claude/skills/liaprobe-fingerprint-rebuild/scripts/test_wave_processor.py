#!/usr/bin/env python3
# test_wave_processor.py -- Unit tests for wave_processor orchestration.
# Covers Bug 2 regression (auto-fix preservation) and Bug 3 regression
# (http-gate blocking for vendor_self_host pattern failures).
# Run: cd scripts/ && python3 -m unittest test_wave_processor -v

import unittest
from unittest import mock

import wave_processor as P
from wave_config import WaveConfig


# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

def _llm_rule(taxonomy_code: str = "DEMO", **overrides) -> dict:
    """Return a rule shape as the LLM would produce it, with key fields set."""
    rule = {
        "$schema": "lia-fingerprint-v2-independent",
        "id": taxonomy_code.lower(),
        "version": "2.0.0",
        "enabled": True,
        "taxonomy_code": taxonomy_code,
        "taxonomy_name": "Demo",
        "product": "Demo",
        "vendor": "Demo Inc",
        "vendor_website": "https://demo.example/",
        "default_ports": [443],
        "probes": [{
            "id": f"lia_{taxonomy_code.lower()}_http",
            "layer": "L7_HTTP",
            "method": "GET",
            "path": "/",
            "follow_redirects": True,
            "matchers": [{
                "target": "header", "field": "server",
                "match_type": "regex", "value": "(?i)demo",
                "confidence_delta": 0.75,
            }],
        }],
        "base_confidence": 0.0,
        "confidence_threshold": 0.65,
        "tags": ["demo"],
        "artifacts": {
            "html_sha256": "a" * 64,
            "favicon_sha256": None,
            "favicon_mmh3": None,
            "headers_sha256": None,
            "capture_url": "https://demo.example/",
            "observation_provenance": "vendor_self_host",
            "capture_date": "2026-05-12",
        },
        "_lia_independent_authoring": {
            "review_date": "2026-05-12",
            "operator": "test",
            "method": "direct_public_observation",
            "vendor_website": "https://demo.example/",
            "rationale": "Source: test",
            "false_positive_check": "Pattern tested -- NEGATIVE",
            "third_party_catalog_references_consulted": "NONE -- pattern authored from public observation",
            "supersedes_prior_rule": f"patterns/web-signatures/{taxonomy_code}.json",
        },
    }
    for k, v in overrides.items():
        rule[k] = v
    return rule


class RecordingCfg:
    """In-memory replacement for WaveConfig with recording callbacks."""

    def __init__(self, products: list, resolve_vendor_url: str = "heuristic"):
        # Ensure each product dict has the keys build_prompt expects.
        for p in products:
            p.setdefault("product", p["taxonomy_code"])
            p.setdefault("vendor", "")
            p.setdefault("vendor_website", "")
        self.products_to_serve = products
        self.authored: list = []
        self.deferred: list = []      # (code, reason)
        self.archived: list = []
        self.written_rules: list = []  # (rule, code, archived)
        self.git_commits: list = []   # (wave, authored_list, archived_list)
        self.log_lines: list = []
        self._build()
        self.resolve_vendor_url = resolve_vendor_url

    def _build(self):
        self.cfg = WaveConfig(
            n_waves=1,
            rules_per_wave=len(self.products_to_serve),
            model="haiku",
            escalate_model="sonnet",
            dry_run=False,
            run_date="2026-05-12",
            resolve_vendor_url="heuristic",
            claude_bin="/usr/bin/claude",
            get_products=lambda n: self.products_to_serve[:n],
            mark_authored=lambda code, date: self.authored.append(code),
            mark_deferred=lambda code, date, reason: self.deferred.append((code, reason)),
            mark_archived=lambda code, date: self.archived.append(code),
            write_rule=lambda rule, code, archived: self.written_rules.append((rule, code, archived)),
            git_commit=lambda w, a, ar: self.git_commits.append((w, a, ar)),
            log=lambda msg: self.log_lines.append(msg),
        )


# ---------------------------------------------------------------------------
# _auto_fix_rule -- Bug 2 regression
# ---------------------------------------------------------------------------

class AutoFixRuleTests(unittest.TestCase):

    def test_preserves_existing_observation_provenance(self):
        """Bug 2 fix: LLM-set provenance must survive _auto_fix_rule."""
        rule = {
            "artifacts": {"observation_provenance": "vendor_self_host"},
        }
        out = P._auto_fix_rule(rule, "DEMO", "2026-05-12")
        self.assertEqual(out["artifacts"]["observation_provenance"], "vendor_self_host",
                         "Bug 2 regression: _auto_fix_rule overrode existing provenance")

    def test_preserves_real_deployment_third_party(self):
        rule = {
            "artifacts": {"observation_provenance": "real_deployment_third_party"},
        }
        out = P._auto_fix_rule(rule, "DEMO", "2026-05-12")
        self.assertEqual(out["artifacts"]["observation_provenance"],
                         "real_deployment_third_party")

    def test_adds_default_when_provenance_missing(self):
        rule = {"artifacts": {}}
        out = P._auto_fix_rule(rule, "DEMO", "2026-05-12")
        self.assertEqual(out["artifacts"]["observation_provenance"],
                         "documented_default_behavior")

    def test_adds_schema_and_supersedes(self):
        rule = {}
        out = P._auto_fix_rule(rule, "DEMO_X", "2026-05-12")
        self.assertEqual(out["$schema"], "lia-fingerprint-v2-independent")
        self.assertEqual(
            out["_lia_independent_authoring"]["supersedes_prior_rule"],
            "patterns/web-signatures/DEMO_X.json",
        )


# ---------------------------------------------------------------------------
# process_wave -- Bug 3 regression (http-gate blocking) + ST2b auto-upgrade gate
# ---------------------------------------------------------------------------

class ProcessWaveHttpGateTests(unittest.TestCase):

    def _run_wave_with_rule(self, rule: dict, http_result: dict) -> RecordingCfg:
        """Run process_wave with a single fake rule and a fake http_verify_rule result."""
        rc = RecordingCfg(products=[{"taxonomy_code": rule["taxonomy_code"]}])
        fake_usage = {"input_tokens": 0, "output_tokens": 0}
        with mock.patch.object(P, "_call_claude_safe", return_value=([rule], fake_usage)), \
             mock.patch.object(P, "http_verify_rule", return_value=http_result):
            P.process_wave(1, rc.cfg)
        return rc

    def test_defers_vendor_self_host_on_pattern_failure(self):
        """Bug 3 fix: vendor_self_host + verified=False + 'no match' = DEFER."""
        rule = _llm_rule("DEMO_SH")
        rule["artifacts"]["observation_provenance"] = "vendor_self_host"
        http_result = {
            "verified": False, "tested": True, "status": 200,
            "note": "no match (HTTP 200, tested 1 pattern(s))",
            "verified_signal_class": None,
            "body_sha256": "b" * 64, "capture_url": "https://demo.example/",
        }
        rc = self._run_wave_with_rule(rule, http_result)
        self.assertIn(("DEMO_SH", "http_gate_no_match"), rc.deferred,
                      f"Bug 3 regression: vendor_self_host pattern failure not deferred. "
                      f"Deferred: {rc.deferred}, Authored: {rc.authored}")
        self.assertNotIn("DEMO_SH", rc.authored)

    def test_authors_vendor_self_host_on_infra_error(self):
        """Bug 3 fix: vendor_self_host + verified=False + 'fetch error' = AUTHOR (non-blocking)."""
        rule = _llm_rule("DEMO_INFRA")
        rule["artifacts"]["observation_provenance"] = "vendor_self_host"
        http_result = {
            "verified": False, "tested": True, "status": 0,
            "note": "fetch error: timeout",
            "verified_signal_class": None,
            "body_sha256": None, "capture_url": "https://demo.example/",
        }
        rc = self._run_wave_with_rule(rule, http_result)
        self.assertIn("DEMO_INFRA", rc.authored,
                      f"vendor_self_host with fetch error should still be authored. "
                      f"Authored: {rc.authored}, Deferred: {rc.deferred}")

    def test_authors_documented_default_without_upgrade_on_body_match(self):
        """ST2b: body match must NOT upgrade documented_default_behavior."""
        rule = _llm_rule("DEMO_BODY")
        rule["artifacts"]["observation_provenance"] = "documented_default_behavior"
        rule["artifacts"]["html_sha256"] = None  # documented_default allows null
        http_result = {
            "verified": True, "tested": True, "status": 200,
            "note": "matched: body:demo",
            "verified_signal_class": "body",
            "body_sha256": "c" * 64, "capture_url": "https://demo.example/",
        }
        rc = self._run_wave_with_rule(rule, http_result)
        self.assertIn("DEMO_BODY", rc.authored)
        # Find the written rule and check provenance was NOT upgraded
        written = [r for r, code, _ in rc.written_rules if code == "DEMO_BODY"]
        self.assertEqual(len(written), 1)
        self.assertEqual(
            written[0]["artifacts"]["observation_provenance"],
            "documented_default_behavior",
            "ST2b regression: body match wrongly upgraded provenance to vendor_self_host",
        )

    def test_authors_documented_default_with_upgrade_on_header_match(self):
        """ST2b: header match SHOULD upgrade documented_default_behavior -> vendor_self_host."""
        rule = _llm_rule("DEMO_HEADER")
        rule["artifacts"]["observation_provenance"] = "documented_default_behavior"
        rule["artifacts"]["html_sha256"] = None
        http_result = {
            "verified": True, "tested": True, "status": 200,
            "note": "matched: header:(?i)demo-server",
            "verified_signal_class": "header",
            "body_sha256": "d" * 64, "capture_url": "https://demo.example/",
        }
        rc = self._run_wave_with_rule(rule, http_result)
        self.assertIn("DEMO_HEADER", rc.authored)
        written = [r for r, code, _ in rc.written_rules if code == "DEMO_HEADER"]
        self.assertEqual(len(written), 1)
        self.assertEqual(
            written[0]["artifacts"]["observation_provenance"],
            "vendor_self_host",
            "ST2b: header match did not upgrade provenance as expected",
        )
        # Side benefit: html_sha256 was captured from http result
        self.assertEqual(written[0]["artifacts"]["html_sha256"], "d" * 64,
                         "Verified http-gate must populate html_sha256 with body_sha256")


# ---------------------------------------------------------------------------
# process_wave -- skip http-gate when resolve_vendor_url == "off"
# ---------------------------------------------------------------------------

class ProcessWaveSkipGateTests(unittest.TestCase):

    def test_skips_http_gate_when_resolve_vendor_url_off(self):
        rule = _llm_rule("DEMO_OFF")
        rc = RecordingCfg(products=[{"taxonomy_code": "DEMO_OFF"}])
        rc.cfg.resolve_vendor_url = "off"
        fake_usage = {"input_tokens": 0, "output_tokens": 0}
        with mock.patch.object(P, "_call_claude_safe", return_value=([rule], fake_usage)), \
             mock.patch.object(P, "http_verify_rule") as mock_verify:
            P.process_wave(1, rc.cfg)
            mock_verify.assert_not_called()
        self.assertIn("DEMO_OFF", rc.authored)


if __name__ == "__main__":
    unittest.main()
