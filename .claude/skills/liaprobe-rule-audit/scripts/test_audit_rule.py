#!/usr/bin/env python3
"""Unit tests for audit_rule -- TDD red-green per fingerprint-rebuild Gate 4."""
import json
import os
import tempfile
import unittest

import audit_rule as A


def _write(d, name, obj):
    p = os.path.join(d, name)
    with open(p, "w") as f:
        json.dump(obj, f)
    return p


CLEAN = {
    "$schema": "lia-fingerprint-v1",
    "id": "acme_widgetserver",
    "product": "WidgetServer",
    "vendor": "Acme",
    "cpe23_template": "cpe:2.3:a:acme:widgetserver:{version}:*:*:*:*:*:*:*",
    "known_cves": [{"cve_id": "CVE-2020-0001"}],
    "_lia_independent_authoring": {"third_party_catalog_references_consulted": "NONE"},
    "banner_matchers": [{"target": "banner", "match_type": "regex", "value": "^Acme WidgetServer"}],
}


def codes(res):
    return {f["code"] for f in res["findings"]}


class TestAuditRule(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def test_clean_rule_grade_a(self):
        p = _write(self.tmp, "clean.json", CLEAN)
        res = A.audit_rule(p)
        self.assertEqual(res["grade"], "A", res["findings"])
        self.assertEqual(res["score"], 100)
        self.assertEqual(res["findings"], [])

    def test_invalid_json_critical(self):
        p = os.path.join(self.tmp, "bad.json")
        with open(p, "w") as f:
            f.write("{not json")
        res = A.audit_rule(p)
        self.assertIn("invalid_json", codes(res))
        self.assertTrue(any(f["severity"] == "CRITICAL" for f in res["findings"]))

    def test_missing_required_fields_critical(self):
        p = _write(self.tmp, "noid.json", {"$schema": "lia-fingerprint-v1",
                                            "banner_matchers": [{"target": "banner", "value": "x"}]})
        res = A.audit_rule(p)
        self.assertIn("missing_id", codes(res))
        self.assertIn("missing_product", codes(res))

    def test_cpe_os_host_high(self):
        r = dict(CLEAN, cpe23_template="cpe:/o:apple:mac_os_x:10.3")
        p = _write(self.tmp, "os.json", r)
        res = A.audit_rule(p)
        self.assertIn("cpe_part_os", codes(res))

    def test_cpe_placeholder_high(self):
        r = dict(CLEAN, cpe23_template="cpe:2.3:h:ecosys:$1:*:*:*:*:*:*:*:*")
        p = _write(self.tmp, "ph.json", r)
        res = A.audit_rule(p)
        self.assertIn("cpe_placeholder", codes(res))

    def test_no_cpe_medium(self):
        r = dict(CLEAN)
        r.pop("cpe23_template")
        r.pop("known_cves")
        p = _write(self.tmp, "nocpe.json", r)
        res = A.audit_rule(p)
        self.assertIn("no_cpe", codes(res))

    def test_no_matchers_critical(self):
        r = dict(CLEAN)
        r.pop("banner_matchers")
        p = _write(self.tmp, "nomatch.json", r)
        res = A.audit_rule(p)
        self.assertIn("no_matchers", codes(res))
        # single CRITICAL = 100-40 = 60 = grade C; assert the CRITICAL is present
        self.assertTrue(any(f["severity"] == "CRITICAL" for f in res["findings"]))

    def test_generic_id_high(self):
        r = dict(CLEAN, id="nginx")
        p = _write(self.tmp, "gen.json", r)
        res = A.audit_rule(p)
        self.assertIn("generic_id", codes(res))

    def test_third_party_refs_high(self):
        r = dict(CLEAN, _lia_independent_authoring={"third_party_catalog_references_consulted": "SomeCatalog"})
        p = _write(self.tmp, "ref.json", r)
        res = A.audit_rule(p)
        self.assertIn("third_party_refs", codes(res))

    def test_marketing_provenance_high(self):
        r = dict(CLEAN, artifacts={"html_sha256": "ab" * 32, "capture_url": "http://x",
                                   "observation_provenance": "vendor_marketing_site"})
        p = _write(self.tmp, "mkt.json", r)
        res = A.audit_rule(p)
        self.assertIn("marketing_site_provenance", codes(res))

    def test_capture_url_missing_medium(self):
        r = dict(CLEAN, artifacts={"html_sha256": "ab" * 32})
        p = _write(self.tmp, "nourl.json", r)
        res = A.audit_rule(p)
        self.assertIn("no_capture_url", codes(res))

    def test_weak_signal_only_low(self):
        r = dict(CLEAN)
        r.pop("banner_matchers")
        r["matchers"] = [{"target": "body", "match_type": "regex", "value": "welcome"}]
        p = _write(self.tmp, "weak.json", r)
        res = A.audit_rule(p)
        self.assertIn("weak_signal_only", codes(res))

    def test_disabled_info(self):
        r = dict(CLEAN, enabled=False)
        p = _write(self.tmp, "off.json", r)
        res = A.audit_rule(p)
        self.assertIn("disabled", codes(res))

    def test_id_collision_with_corpus(self):
        a = _write(self.tmp, "a.json", dict(CLEAN, id="shared_id"))
        _write(self.tmp, "b.json", dict(CLEAN, id="shared_id"))
        res = A.audit_rule(a, corpus_root=self.tmp)
        self.assertIn("id_collision", codes(res))

    def test_grade_thresholds(self):
        self.assertEqual(A._finalize({"findings": []})["grade"], "A")
        self.assertEqual(A._finalize({"findings": [{"severity": "HIGH"}]})["grade"], "B")  # 80
        self.assertEqual(A._finalize({"findings": [{"severity": "CRITICAL"}]})["grade"], "C")  # 60


if __name__ == "__main__":
    unittest.main()
