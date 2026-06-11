#!/usr/bin/env python3
# test_wave_validator.py -- Unit tests for wave_validator.
# Run: python3 -m unittest test_wave_validator -v
# Coverage: provenance acceptance, html_sha256 enforcement, http_verify_rule branches.

import unittest
from unittest import mock

import wave_validator as V


def _base_rule(**overrides) -> dict:
    """Return a minimally valid rule dict that passes validate_rule by default."""
    rule = {
        "$schema": "lia-fingerprint-v2-independent",
        "id": "demo",
        "version": "2.0.0",
        "enabled": True,
        "taxonomy_code": "DEMO",
        "taxonomy_name": "Demo Product",
        "product": "Demo",
        "vendor": "Demo Inc",
        "vendor_website": "https://demo.example/",
        "default_ports": [443],
        "probes": [{
            "id": "lia_demo_http",
            "layer": "L7_HTTP",
            "method": "GET",
            "path": "/",
            "follow_redirects": True,
            "matchers": [{
                "target": "header",
                "field": "server",
                "match_type": "regex",
                "value": "(?i)demo",
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
            "observation_provenance": "documented_default_behavior",
            "capture_date": "2026-05-12",
        },
        "_lia_independent_authoring": {
            "review_date": "2026-05-12",
            "operator": "nightly-batch-test",
            "method": "direct_public_observation",
            "vendor_website": "https://demo.example/",
            "rationale": "Source: docs -- Server header verified",
            "false_positive_check": "Pattern tested against nginx -- NEGATIVE",
            "third_party_catalog_references_consulted": "NONE -- pattern authored from public observation",
            "supersedes_prior_rule": "patterns/web-signatures/DEMO.json",
        },
    }
    # Apply nested overrides via dict.update on top-level for simplicity.
    for k, v in overrides.items():
        rule[k] = v
    return rule


class ValidateRuleProvenanceTests(unittest.TestCase):
    """Bug 1 regression: all 4 valid provenances must be accepted."""

    def test_accepts_documented_default_behavior(self):
        rule = _base_rule()
        rule["artifacts"]["observation_provenance"] = "documented_default_behavior"
        rule["artifacts"]["html_sha256"] = None
        self.assertEqual(V.validate_rule(rule), [])

    def test_accepts_real_deployment_third_party(self):
        rule = _base_rule()
        rule["artifacts"]["observation_provenance"] = "real_deployment_third_party"
        rule["artifacts"]["html_sha256"] = "b" * 64
        self.assertEqual(V.validate_rule(rule), [])

    def test_accepts_vendor_self_host_with_html_sha256(self):
        rule = _base_rule()
        rule["artifacts"]["observation_provenance"] = "vendor_self_host"
        rule["artifacts"]["html_sha256"] = "c" * 64
        self.assertEqual(V.validate_rule(rule), [])

    def test_accepts_NONE(self):
        rule = _base_rule()
        rule["artifacts"]["observation_provenance"] = "NONE"
        self.assertEqual(V.validate_rule(rule), [])

    def test_rejects_invalid_provenance(self):
        rule = _base_rule()
        rule["artifacts"]["observation_provenance"] = "vendor_marketing_site"
        errors = V.validate_rule(rule)
        joined = " ".join(errors)
        self.assertIn("observation_provenance must be one of", joined)
        self.assertIn("vendor_marketing_site", joined)


class ValidateRuleEvidenceTests(unittest.TestCase):
    """ST2: html_sha256 enforcement on strong provenances."""

    def test_vendor_self_host_requires_html_sha256_or_favicon(self):
        rule = _base_rule()
        rule["artifacts"]["observation_provenance"] = "vendor_self_host"
        rule["artifacts"]["html_sha256"] = None
        rule["artifacts"]["favicon_sha256"] = None
        errors = V.validate_rule(rule)
        self.assertTrue(
            any("vendor_self_host requires html_sha256" in e for e in errors),
            f"Expected sha256 enforcement, got: {errors}",
        )

    def test_vendor_self_host_accepts_favicon_only(self):
        rule = _base_rule()
        rule["artifacts"]["observation_provenance"] = "vendor_self_host"
        rule["artifacts"]["html_sha256"] = None
        rule["artifacts"]["favicon_sha256"] = "d" * 64
        self.assertEqual(V.validate_rule(rule), [])

    def test_real_deployment_third_party_requires_html_sha256(self):
        """ST2a: extend enforcement to real_deployment_third_party."""
        rule = _base_rule()
        rule["artifacts"]["observation_provenance"] = "real_deployment_third_party"
        rule["artifacts"]["html_sha256"] = None
        rule["artifacts"]["favicon_sha256"] = None
        errors = V.validate_rule(rule)
        self.assertTrue(
            any("real_deployment_third_party requires html_sha256" in e for e in errors),
            f"Expected sha256 enforcement on real_deployment_third_party, got: {errors}",
        )


class ValidateRuleSchemaTests(unittest.TestCase):
    """Basic schema enforcement."""

    def test_rejects_wrong_schema_string(self):
        rule = _base_rule()
        rule["$schema"] = "lia-fingerprint-v1"
        errors = V.validate_rule(rule)
        self.assertIn("$schema must be 'lia-fingerprint-v2-independent'", errors)

    def test_rejects_missing_NONE_in_authoring(self):
        rule = _base_rule()
        rule["_lia_independent_authoring"]["third_party_catalog_references_consulted"] = \
            "consulted catalog X"
        errors = V.validate_rule(rule)
        self.assertIn(
            "third_party_catalog_references_consulted must contain 'NONE'",
            errors,
        )


class IsObsoleteTests(unittest.TestCase):
    """Obsolete signal detection."""

    def test_obsolete_signal_in_rationale(self):
        rule = _base_rule()
        rule["enabled"] = False
        rule["_lia_independent_authoring"]["rationale"] = "Project abandoned in 2018"
        self.assertTrue(V.is_obsolete(rule))

    def test_not_obsolete_when_enabled(self):
        rule = _base_rule()
        rule["enabled"] = True
        rule["_lia_independent_authoring"]["rationale"] = "Project abandoned"
        self.assertFalse(V.is_obsolete(rule))


class HttpVerifyRuleTests(unittest.TestCase):
    """Bug 3 regression: http_verify_rule branches."""

    def test_no_vendor_website_returns_not_tested(self):
        rule = _base_rule()
        rule["vendor_website"] = ""
        rule["_lia_independent_authoring"]["vendor_website"] = ""
        result = V.http_verify_rule(rule)
        self.assertFalse(result["verified"])
        self.assertFalse(result["tested"])
        self.assertEqual(result["note"], "no vendor_website")

    def test_no_matchers_returns_not_tested(self):
        rule = _base_rule()
        rule["probes"] = [{"id": "x", "layer": "L7_HTTP", "method": "GET", "path": "/", "matchers": []}]
        result = V.http_verify_rule(rule)
        self.assertFalse(result["verified"])
        self.assertFalse(result["tested"])
        self.assertEqual(result["note"], "no regex matchers")
        self.assertIn("body_sha256", result)
        self.assertIn("capture_url", result)

    @mock.patch("wave_validator.urllib.request.urlopen")
    def test_fetch_error_returns_infra_error(self, mock_urlopen):
        mock_urlopen.side_effect = OSError("DNS failure")
        rule = _base_rule()
        result = V.http_verify_rule(rule)
        self.assertFalse(result["verified"])
        self.assertTrue(result["tested"])
        self.assertIn("fetch error", result["note"])
        self.assertIsNone(result["body_sha256"])

    @mock.patch("wave_validator.urllib.request.urlopen")
    def test_header_match_returns_verified_with_signal_class(self, mock_urlopen):
        fake_resp = mock.MagicMock()
        fake_resp.status = 200
        fake_resp.read.return_value = b"<html>not matching body</html>"
        fake_resp.headers.items.return_value = [("Server", "nginx demo-server")]
        fake_resp.__enter__ = lambda self: self
        fake_resp.__exit__ = lambda self, *a: None
        mock_urlopen.return_value = fake_resp
        rule = _base_rule()
        # Force header matcher
        rule["probes"][0]["matchers"] = [{
            "target": "header", "field": "server",
            "match_type": "regex", "value": "(?i)demo-server",
            "confidence_delta": 0.9,
        }]
        result = V.http_verify_rule(rule)
        self.assertTrue(result["verified"])
        self.assertEqual(result["status"], 200)
        self.assertEqual(result["verified_signal_class"], "header",
                         f"Expected signal_class=header, got: {result.get('verified_signal_class')}")
        self.assertEqual(len(result["body_sha256"]), 64)

    @mock.patch("wave_validator.urllib.request.urlopen")
    def test_body_match_signal_class_is_body(self, mock_urlopen):
        fake_resp = mock.MagicMock()
        fake_resp.status = 200
        fake_resp.read.return_value = b"<html><h1>demo product page</h1></html>"
        fake_resp.headers.items.return_value = [("Server", "nginx")]
        fake_resp.__enter__ = lambda self: self
        fake_resp.__exit__ = lambda self, *a: None
        mock_urlopen.return_value = fake_resp
        rule = _base_rule()
        rule["probes"][0]["matchers"] = [{
            "target": "body", "field": "html",
            "match_type": "regex", "value": "(?i)demo product",
            "confidence_delta": 0.5,
        }]
        result = V.http_verify_rule(rule)
        self.assertTrue(result["verified"])
        self.assertEqual(result["verified_signal_class"], "body",
                         f"Expected signal_class=body, got: {result.get('verified_signal_class')}")

    @mock.patch("wave_validator.urllib.request.urlopen")
    def test_no_match_records_body_sha256(self, mock_urlopen):
        fake_resp = mock.MagicMock()
        fake_resp.status = 200
        fake_resp.read.return_value = b"<html>unrelated</html>"
        fake_resp.headers.items.return_value = [("Server", "nginx")]
        fake_resp.__enter__ = lambda self: self
        fake_resp.__exit__ = lambda self, *a: None
        mock_urlopen.return_value = fake_resp
        rule = _base_rule()
        result = V.http_verify_rule(rule)
        self.assertFalse(result["verified"])
        self.assertTrue(result["tested"])
        self.assertIn("no match", result["note"])
        self.assertEqual(len(result["body_sha256"]), 64,
                         "body_sha256 must be captured even on no-match for audit trail")


if __name__ == "__main__":
    unittest.main()
