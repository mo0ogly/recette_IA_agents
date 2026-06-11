"""Tests for enrich_cycle_4_cve / enrich_cycle_5_eol / enrich_cycle_7_mitre.

Mock psycopg2 PG and HTTP calls. Validates :
- cpe_pattern building from cpe23_template
- _row_to_cve_entry conversions (datetime, KEV, ransomware)
- slug resolution (master CSV, slugify product, slugify vendor)
- _parse_eol_value (boolean, ISO string, None)
- _build_lifecycle aggregation (LTS detection, latest cycle)
- skip paths : no_cpe, no_match, pg_down, no_slug, http_404, no_cves
"""
from __future__ import annotations

import json
import sys
import unittest
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

SCRIPT_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import enrich_lib as el  # noqa: E402
import enrich_cycle_4_cve as c4  # noqa: E402
import enrich_cycle_5_eol as c5  # noqa: E402
import enrich_cycle_7_mitre as c7  # noqa: E402
import enrich_cycle_8_default_creds as c8  # noqa: E402
import enrich_cycle_9_cert_patterns as c9  # noqa: E402
import enrich_cycle_10_http_behavior as c10b  # noqa: E402
import enrich_cycle_11_cluster_tls as c11  # noqa: E402
import enrich_cycle_12_honeypot as c12  # noqa: E402
import enrich_cycle_6_compliance as c6  # noqa: E402


def _valid_rule(extra: dict | None = None) -> dict:
    rule = {
        "$schema": "lia-fingerprint-v1",
        "id": "lia_jenkins",
        "vendor": "Jenkins",
        "product": "Jenkins",
        "category": "DevOps",
        "taxonomy_code": "DEVOPS.CI",
        "cpe23_template": "cpe:2.3:a:jenkins:jenkins:{version}:*:*:*:*:*:*:*",
        "banner_matchers": [
            {"target": "raw", "op": "regex", "value": "^X-Jenkins:"},
        ],
        "probes": [],
    }
    if extra:
        rule.update(extra)
    return rule


def _setup_state_evidence(tmpdir: Path) -> tuple[Path, el.StateManager, el.EvidenceWriter, MagicMock]:
    rule_path = tmpdir / "patterns" / "TEST.json"
    rule_path.parent.mkdir(parents=True, exist_ok=True)
    rule_path.write_text(json.dumps(_valid_rule()))
    sm = el.StateManager(tmpdir / "state")
    ew = el.EvidenceWriter(
        enrichment_root=tmpdir / "enrich",
        fingerprints_root=tmpdir / "fp",
        patterns_root=tmpdir / "patterns",
    )
    lock = MagicMock()
    lock._fd = 42
    return rule_path, sm, ew, lock


# ======================================================================
# Cycle 4 -- CVE
# ======================================================================

class TestCycle4CpePattern(unittest.TestCase):
    def test_build_cpe_pattern_from_template(self):
        rule = {"cpe23_template": "cpe:2.3:a:jenkins:jenkins:{version}:*:*:*:*:*:*:*"}
        self.assertEqual(c4._build_cpe_pattern(rule), "cpe:2.3:a:jenkins:jenkins:%")

    def test_build_cpe_pattern_no_template(self):
        self.assertIsNone(c4._build_cpe_pattern({}))

    def test_build_cpe_pattern_invalid(self):
        self.assertIsNone(c4._build_cpe_pattern({"cpe23_template": "not-a-cpe"}))


class TestCycle4RowToCveEntry(unittest.TestCase):
    def test_row_basic(self):
        row = {
            "cve_id": "CVE-2024-23897",
            "severity": "CRITICAL",
            "cvss_v3": 9.8,
            "published_date": datetime(2024, 1, 24, 18, 15),
            "cwe_ids": ["CWE-22"],
            "in_kev": False,
        }
        entry = c4._row_to_cve_entry(row)
        self.assertEqual(entry["cve_id"], "CVE-2024-23897")
        self.assertEqual(entry["severity"], "CRITICAL")
        self.assertEqual(entry["cvss_v3"], 9.8)
        self.assertIn("2024-01-24", entry["published"])
        self.assertEqual(entry["cwe_ids"], ["CWE-22"])
        self.assertNotIn("cisa_kev", entry)

    def test_row_kev_with_ransomware(self):
        row = {
            "cve_id": "CVE-2024-23897",
            "severity": "CRITICAL",
            "in_kev": True,
            "kev_date_added": "2024-08-19",
            "kev_ransomware": "Known",
        }
        entry = c4._row_to_cve_entry(row)
        self.assertTrue(entry["cisa_kev"])
        self.assertEqual(entry["kev_date_added"], "2024-08-19")
        self.assertTrue(entry["kev_ransomware_use"])

    def test_row_default_severity(self):
        entry = c4._row_to_cve_entry({"cve_id": "CVE-1"})
        self.assertEqual(entry["severity"], "UNKNOWN")


class TestCycle4Handle(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.tmpdir = Path(self.tmp.name)
        self.rule_path, self.sm, self.ew, self.lock = _setup_state_evidence(self.tmpdir)

    def tearDown(self):
        self.tmp.cleanup()

    def test_skip_no_cpe(self):
        rule = _valid_rule()
        del rule["cpe23_template"]
        self.rule_path.write_text(json.dumps(rule))
        success, _, summary = c4.handle(self.rule_path, rule, self.ew, self.sm, self.lock)
        self.assertFalse(success)
        self.assertTrue(summary.get("skipped"))
        self.assertEqual(summary["reason"], "no_cpe")

    def test_skip_pg_down(self):
        rule = _valid_rule()
        with patch.object(c4, "fetch_cves") as mock_fetch:
            mock_fetch.side_effect = el.DependencyMissingError("psycopg2 not installed")
            success, _, summary = c4.handle(self.rule_path, rule, self.ew, self.sm, self.lock)
        self.assertFalse(success)
        self.assertEqual(summary["reason"], "pg_down")

    def test_skip_no_match(self):
        rule = _valid_rule()
        with patch.object(c4, "fetch_cves") as mock_fetch:
            mock_fetch.return_value = []
            success, _, summary = c4.handle(self.rule_path, rule, self.ew, self.sm, self.lock)
        self.assertFalse(success)
        self.assertEqual(summary["reason"], "no_match")

    def test_success_with_cves(self):
        rule = _valid_rule()
        rows = [
            {
                "cve_id": "CVE-2024-23897", "severity": "CRITICAL", "cvss_v3": 9.8,
                "published_date": datetime(2024, 1, 24), "cwe_ids": ["CWE-22"],
                "in_kev": True, "kev_date_added": "2024-08-19", "kev_ransomware": False,
            },
            {
                "cve_id": "CVE-2025-1", "severity": "HIGH", "cvss_v3": 7.5,
                "published_date": datetime(2025, 1, 1), "cwe_ids": ["CWE-79"],
                "in_kev": False,
            },
        ]
        with patch.object(c4, "fetch_cves") as mock_fetch:
            mock_fetch.return_value = rows
            success, diff, summary = c4.handle(self.rule_path, rule, self.ew, self.sm, self.lock)
        self.assertTrue(success)
        self.assertEqual(summary["cve_count"], 2)
        self.assertEqual(summary["kev_count"], 1)
        self.assertEqual(summary["max_cvss"], 9.8)
        self.assertEqual(summary["critical_count"], 1)
        # rule.json should now have known_cves[]
        loaded = json.loads(self.rule_path.read_text())
        self.assertEqual(len(loaded["known_cves"]), 2)
        self.assertIn("cycle_4_cve", loaded.get("_meta_enrichment", {}))


# ======================================================================
# Cycle 5 -- EOL
# ======================================================================

class TestCycle5SlugResolve(unittest.TestCase):
    def test_resolve_slug_from_product(self):
        rule = _valid_rule()
        slug = c5._resolve_slug(rule, None)
        self.assertEqual(slug, "jenkins")

    def test_resolve_slug_from_master_csv(self):
        with TemporaryDirectory() as tmp:
            csv_path = Path(tmp) / "master.csv"
            csv_path.write_text("liaprobe_product_key,endoflife_slug\napache/http_server,httpd\n")
            rule = _valid_rule({
                "vendor": "Apache",
                "product": "Apache HTTP Server",
                "cpe23_template": "cpe:2.3:a:apache:http_server:{version}:*:*:*:*:*:*:*",
            })
            slug = c5._resolve_slug(rule, csv_path)
            self.assertEqual(slug, "httpd")

    def test_resolve_slug_no_product(self):
        rule = {"vendor": "Vendor"}
        slug = c5._resolve_slug(rule, None)
        self.assertEqual(slug, "vendor")

    def test_resolve_slug_empty(self):
        slug = c5._resolve_slug({}, None)
        self.assertIsNone(slug)


class TestCycle5ParseEolValue(unittest.TestCase):
    def test_parse_eol_none(self):
        self.assertEqual(c5._parse_eol_value(None), (None, False))

    def test_parse_eol_false(self):
        self.assertEqual(c5._parse_eol_value(False), (None, False))

    def test_parse_eol_true(self):
        self.assertEqual(c5._parse_eol_value(True), (None, True))

    def test_parse_eol_iso_past(self):
        date_str, is_past = c5._parse_eol_value("2020-01-01")
        self.assertEqual(date_str, "2020-01-01")
        self.assertTrue(is_past)

    def test_parse_eol_iso_future(self):
        date_str, is_past = c5._parse_eol_value("2099-01-01")
        self.assertEqual(date_str, "2099-01-01")
        self.assertFalse(is_past)

    def test_parse_eol_invalid(self):
        date_str, is_past = c5._parse_eol_value("not-a-date")
        self.assertIsNone(date_str)
        self.assertFalse(is_past)


class TestCycle5BuildLifecycle(unittest.TestCase):
    def test_build_lifecycle_with_lts(self):
        cycles = [
            {"cycle": "1.0", "releaseDate": "2020-01-01", "eol": "2022-01-01", "lts": False},
            {"cycle": "2.0", "releaseDate": "2024-01-01", "eol": "2099-01-01", "lts": True, "latest": "2.5"},
        ]
        result = c5._build_lifecycle(cycles)
        self.assertEqual(result["latest_cycle"], "2.0")
        self.assertEqual(result["lts_cycle"], "2.0")
        self.assertEqual(result["current_stable"], "2.5")
        self.assertFalse(result["is_eol_now"])

    def test_build_lifecycle_empty(self):
        self.assertIsNone(c5._build_lifecycle([]))


class TestCycle5Handle(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.tmpdir = Path(self.tmp.name)
        self.rule_path, self.sm, self.ew, self.lock = _setup_state_evidence(self.tmpdir)

    def tearDown(self):
        self.tmp.cleanup()

    def test_skip_no_slug(self):
        rule = {}  # no product/vendor/cpe
        self.rule_path.write_text(json.dumps(rule))
        success, _, summary = c5.handle(self.rule_path, rule, self.ew, self.sm, self.lock)
        self.assertFalse(success)
        self.assertEqual(summary["reason"], "no slug")

    def test_skip_http_404(self):
        rule = _valid_rule()
        mock_resp = MagicMock(status=404, body=b"", url="x", response_size_bytes=0,
                              fetched_at="2026-05-02T00:00:00Z", from_cache=False)
        with patch.object(c5, "fetch_eol") as mock_fetch:
            mock_fetch.return_value = (mock_resp, None)
            success, _, summary = c5.handle(self.rule_path, rule, self.ew, self.sm, self.lock)
        self.assertFalse(success)
        self.assertEqual(summary["reason"], "http_404")

    def test_success_with_lifecycle(self):
        rule = _valid_rule()
        cycles = [
            {"cycle": "2.541", "releaseDate": "2025-12-10",
             "eol": "2099-01-01", "lts": True, "latest": "2.541.3"},
        ]
        mock_resp = MagicMock(status=200, body=b"[]", url="x", response_size_bytes=10,
                              fetched_at="2026-05-02T00:00:00Z", from_cache=False)
        with patch.object(c5, "fetch_eol") as mock_fetch:
            mock_fetch.return_value = (mock_resp, cycles)
            success, diff, summary = c5.handle(self.rule_path, rule, self.ew, self.sm, self.lock)
        self.assertTrue(success)
        self.assertEqual(summary["slug_used"], "jenkins")
        self.assertEqual(summary["cycles_count"], 1)
        self.assertFalse(summary["is_eol_now"])
        self.assertTrue(summary["lts_present"])
        loaded = json.loads(self.rule_path.read_text())
        self.assertIn("lifecycle", loaded)
        self.assertEqual(loaded["lifecycle"]["latest_cycle"], "2.541")


# ======================================================================
# Cycle 7 -- MITRE
# ======================================================================

class TestCycle7Handle(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.tmpdir = Path(self.tmp.name)
        self.rule_path, self.sm, self.ew, self.lock = _setup_state_evidence(self.tmpdir)

    def tearDown(self):
        self.tmp.cleanup()

    def test_skip_no_cves(self):
        rule = _valid_rule()  # no known_cves
        success, _, summary = c7.handle(self.rule_path, rule, self.ew, self.sm, self.lock)
        self.assertFalse(success)
        self.assertEqual(summary["reason"], "no_cves")

    def test_skip_pg_down(self):
        rule = _valid_rule({"known_cves": [{"cve_id": "CVE-2024-1"}]})
        with patch.object(c7, "fetch_techniques") as mock_fetch:
            mock_fetch.side_effect = el.DependencyMissingError("psycopg2 not installed")
            success, _, summary = c7.handle(self.rule_path, rule, self.ew, self.sm, self.lock)
        self.assertFalse(success)
        self.assertEqual(summary["reason"], "pg_down")

    def test_skip_no_match(self):
        rule = _valid_rule({"known_cves": [{"cve_id": "CVE-2024-1"}]})
        with patch.object(c7, "fetch_techniques") as mock_fetch:
            mock_fetch.return_value = []
            success, _, summary = c7.handle(self.rule_path, rule, self.ew, self.sm, self.lock)
        self.assertFalse(success)
        self.assertEqual(summary["reason"], "no_match")

    def test_success_with_techniques(self):
        rule = _valid_rule({"known_cves": [{"cve_id": "CVE-2024-23897"}]})
        # Need to write rule with known_cves to disk too (handle reads sha)
        self.rule_path.write_text(json.dumps(rule))
        rows = [
            {
                "technique_id": "attack-pattern--xxx",
                "technique_short_id": "T1007",
                "technique_name": "System Service Discovery",
            },
            {
                "technique_id": "attack-pattern--yyy",
                "technique_short_id": "T1018",
                "technique_name": "Remote System Discovery",
            },
        ]
        with patch.object(c7, "fetch_techniques") as mock_fetch:
            mock_fetch.return_value = rows
            success, diff, summary = c7.handle(self.rule_path, rule, self.ew, self.sm, self.lock)
        self.assertTrue(success)
        self.assertEqual(summary["techniques_count"], 2)
        self.assertEqual(summary["cve_source_count"], 1)
        loaded = json.loads(self.rule_path.read_text())
        self.assertIn("attack_surface", loaded)
        self.assertEqual(len(loaded["attack_surface"]["techniques"]), 2)


# ======================================================================
# Cycle 8 -- Default credentials
# ======================================================================

class TestCycle8ProductKey(unittest.TestCase):
    def test_build_product_key_from_cpe(self):
        rule = {"cpe23_template": "cpe:2.3:a:jenkins:jenkins:{version}:*:*:*:*:*:*:*"}
        self.assertEqual(c8._build_product_key(rule), "jenkins/jenkins")

    def test_build_product_key_from_vendor_product(self):
        rule = {"vendor": "Apache", "product": "Tomcat"}
        self.assertEqual(c8._build_product_key(rule), "apache/tomcat")

    def test_build_product_key_none(self):
        self.assertIsNone(c8._build_product_key({}))


class TestCycle8Lookup(unittest.TestCase):
    def test_lookup_credentials_match(self):
        master = {
            "products": {
                "jenkins/jenkins": [
                    {"username": "admin", "password": "admin", "source_id": "x"},
                ],
            },
        }
        creds = c8.lookup_credentials("jenkins/jenkins", master)
        self.assertEqual(len(creds), 1)
        self.assertEqual(creds[0]["username"], "admin")

    def test_lookup_credentials_no_match(self):
        self.assertEqual(c8.lookup_credentials("unknown/x", {"products": {}}), [])

    def test_lookup_credentials_capped(self):
        master = {
            "products": {
                "x/y": [{"username": f"u{i}", "password": "p"} for i in range(100)],
            },
        }
        creds = c8.lookup_credentials("x/y", master)
        self.assertEqual(len(creds), c8.MAX_CREDENTIALS)


class TestCycle8Handle(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.tmpdir = Path(self.tmp.name)
        self.rule_path, self.sm, self.ew, self.lock = _setup_state_evidence(self.tmpdir)
        self.master_path = self.tmpdir / "master.json"
        self.master = {
            "$schema": "lia-default-creds-master-v2",
            "generated_at": "2026-05-02T00:00:00Z",
            "products": {
                "jenkins/jenkins": [
                    {
                        "username": "admin", "password": "admin",
                        "source_id": "defaultcreds_cheat_sheet",
                        "source_url": "https://example.com",
                        "source_sha256": "abc",
                        "source_line": 1,
                    },
                ],
            },
        }
        self.master_path.write_text(json.dumps(self.master))

    def tearDown(self):
        self.tmp.cleanup()

    def test_skip_no_product_key(self):
        rule = {}
        self.rule_path.write_text(json.dumps(rule))
        success, _, summary = c8.handle(
            self.rule_path, rule, self.ew, self.sm, self.lock,
            master_path=self.master_path,
        )
        self.assertFalse(success)
        self.assertEqual(summary["reason"], "no_product_key")

    def test_skip_master_missing(self):
        rule = _valid_rule()
        success, _, summary = c8.handle(
            self.rule_path, rule, self.ew, self.sm, self.lock,
            master_path=self.tmpdir / "nonexistent.json",
        )
        self.assertFalse(success)
        self.assertEqual(summary["reason"], "master_missing")

    def test_skip_no_match(self):
        rule = _valid_rule({
            "vendor": "Unknown",
            "product": "Niche",
            "cpe23_template": "cpe:2.3:a:unknown:niche:{version}:*:*:*:*:*:*:*",
        })
        success, _, summary = c8.handle(
            self.rule_path, rule, self.ew, self.sm, self.lock,
            master_path=self.master_path,
        )
        self.assertFalse(success)
        self.assertEqual(summary["reason"], "no_match")

    def test_success_inject_credentials(self):
        rule = _valid_rule()  # jenkins/jenkins
        success, diff, summary = c8.handle(
            self.rule_path, rule, self.ew, self.sm, self.lock,
            master_path=self.master_path,
        )
        self.assertTrue(success)
        self.assertEqual(summary["product_key"], "jenkins/jenkins")
        self.assertEqual(summary["credentials_count"], 1)
        loaded = json.loads(self.rule_path.read_text())
        self.assertIn("default_credentials", loaded)
        self.assertEqual(loaded["default_credentials"][0]["username"], "admin")
        self.assertIn("cycle_8_default_creds", loaded.get("_meta_enrichment", {}))


# ======================================================================
# Cycle 9 -- Certificate patterns
# ======================================================================

CERT_MASTER_FIXTURE = {
    "$schema": "lia-cert-patterns-master-v1",
    "generated_at": "2026-05-02T00:00:00Z",
    "pattern_definitions": {
        "openssl_default": {
            "name": "OpenSSL default",
            "severity": "info",
            "confidence": 0.4,
            "match": {"subject_dn_regex": "Internet Widgits"},
            "source_id": "vendor_docs_openssl",
            "source_url": "https://example.com/openssl",
            "source_sha256": "abc",
            "verified_at": "2026-05-02T00:00:00Z",
        },
        "synology_default": {
            "name": "Synology default",
            "severity": "high",
            "confidence": 0.7,
            "match": {"subject_cn_regex": "^synology$"},
            "source_id": "vendor_docs_synology",
            "source_url": "https://example.com/synology",
            "source_sha256": "def",
            "verified_at": "2026-05-02T00:00:00Z",
        },
        "k8s_san": {
            "name": "K8s SAN",
            "severity": "medium",
            "confidence": 0.85,
            "match": {"san_regex": "\\.cluster\\.local$"},
            "source_id": "vendor_docs_k8s",
            "source_url": "https://example.com/k8s",
            "source_sha256": "ghi",
            "verified_at": "2026-05-02T00:00:00Z",
        },
    },
    "products": {
        "synology/*": ["synology_default", "openssl_default"],
        "kubernetes/*": ["k8s_san"],
        "*/*": ["openssl_default"],
    },
}


class TestCycle9ProductKey(unittest.TestCase):
    def test_build_product_key_from_cpe(self):
        rule = {"cpe23_template": "cpe:2.3:a:synology:dsm:{version}:*:*:*:*:*:*:*"}
        self.assertEqual(c9._build_product_key(rule), "synology/dsm")

    def test_build_product_key_none(self):
        self.assertIsNone(c9._build_product_key({}))


class TestCycle9Lookup(unittest.TestCase):
    def test_lookup_exact_product(self):
        # synology/dsm should fall through to synology/* wildcard
        ids = c9.lookup_pattern_ids("synology/dsm", CERT_MASTER_FIXTURE)
        self.assertIn("synology_default", ids)
        self.assertIn("openssl_default", ids)

    def test_lookup_universal_only(self):
        ids = c9.lookup_pattern_ids("unknown/x", CERT_MASTER_FIXTURE)
        self.assertEqual(ids, ["openssl_default"])

    def test_lookup_dedup(self):
        # synology/* references openssl_default AND */* also has it -- one entry only
        ids = c9.lookup_pattern_ids("synology/dsm", CERT_MASTER_FIXTURE)
        self.assertEqual(ids.count("openssl_default"), 1)

    def test_lookup_capped(self):
        master = {
            "products": {
                "x/y": [f"p{i}" for i in range(50)],
            },
        }
        ids = c9.lookup_pattern_ids("x/y", master)
        self.assertEqual(len(ids), c9.MAX_PATTERNS)


class TestCycle9Resolve(unittest.TestCase):
    def test_resolve_patterns(self):
        patterns = c9.resolve_patterns(["synology_default", "k8s_san"], CERT_MASTER_FIXTURE)
        self.assertEqual(len(patterns), 2)
        self.assertEqual(patterns[0]["pattern_id"], "synology_default")
        self.assertEqual(patterns[0]["severity"], "high")
        self.assertEqual(patterns[1]["pattern_id"], "k8s_san")

    def test_resolve_skips_missing(self):
        patterns = c9.resolve_patterns(["nonexistent"], CERT_MASTER_FIXTURE)
        self.assertEqual(patterns, [])


class TestCycle9Handle(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.tmpdir = Path(self.tmp.name)
        self.rule_path, self.sm, self.ew, self.lock = _setup_state_evidence(self.tmpdir)
        self.master_path = self.tmpdir / "cert_master.json"
        self.master_path.write_text(json.dumps(CERT_MASTER_FIXTURE))

    def tearDown(self):
        self.tmp.cleanup()

    def test_skip_no_product_key(self):
        rule = {}
        self.rule_path.write_text(json.dumps(rule))
        success, _, summary = c9.handle(
            self.rule_path, rule, self.ew, self.sm, self.lock,
            master_path=self.master_path,
        )
        self.assertFalse(success)
        self.assertEqual(summary["reason"], "no_product_key")

    def test_skip_master_missing(self):
        rule = _valid_rule()
        success, _, summary = c9.handle(
            self.rule_path, rule, self.ew, self.sm, self.lock,
            master_path=self.tmpdir / "nonexistent.json",
        )
        self.assertFalse(success)
        self.assertEqual(summary["reason"], "master_missing")

    def test_success_inject_universal_pattern(self):
        rule = _valid_rule({
            "vendor": "Apache", "product": "Tomcat",
            "cpe23_template": "cpe:2.3:a:apache:tomcat:{version}:*:*:*:*:*:*:*",
        })
        success, diff, summary = c9.handle(
            self.rule_path, rule, self.ew, self.sm, self.lock,
            master_path=self.master_path,
        )
        self.assertTrue(success)
        self.assertEqual(summary["product_key"], "apache/tomcat")
        # Apache tomcat falls through to */* universal
        self.assertEqual(summary["patterns_count"], 1)
        loaded = json.loads(self.rule_path.read_text())
        self.assertIn("certificate_patterns", loaded)
        self.assertEqual(loaded["certificate_patterns"][0]["pattern_id"], "openssl_default")
        self.assertIn("cycle_9_cert_patterns", loaded.get("_meta_enrichment", {}))

    def test_success_inject_synology(self):
        rule = _valid_rule({
            "vendor": "Synology", "product": "DSM",
            "cpe23_template": "cpe:2.3:a:synology:dsm:{version}:*:*:*:*:*:*:*",
        })
        success, _, summary = c9.handle(
            self.rule_path, rule, self.ew, self.sm, self.lock,
            master_path=self.master_path,
        )
        self.assertTrue(success)
        self.assertEqual(summary["max_severity"], "high")
        self.assertEqual(summary["patterns_count"], 2)


# ======================================================================
# Cycle 10 -- HTTP behavior
# ======================================================================

BEHAVIOR_MASTER_FIXTURE = {
    "$schema": "lia-http-behavior-master-v1",
    "definitions": {
        "apache_httpd": {
            "name": "Apache",
            "signals": [
                {"signal_id": "apache_header_order", "type": "header_order"},
                {"signal_id": "apache_default_404", "type": "body_substring"},
            ],
            "source_url": "https://example.com/apache",
            "source_sha256": "abc",
            "verified_at": "2026-05-02T00:00:00Z",
        },
        "cookie_naming": {
            "name": "Cookie naming",
            "signals": [{"signal_id": "cookie_jsessionid", "type": "cookie_name"}],
            "source_url": "https://example.com/rfc",
            "source_sha256": "def",
            "verified_at": "2026-05-02T00:00:00Z",
        },
    },
    "products": {
        "apache/httpd": ["apache_httpd", "cookie_naming"],
        "*/*": ["cookie_naming"],
    },
}


class TestCycle10Lookup(unittest.TestCase):
    def test_exact_with_universal_dedup(self):
        ids = c10b.lookup_definition_ids("apache/httpd", BEHAVIOR_MASTER_FIXTURE)
        self.assertEqual(ids, ["apache_httpd", "cookie_naming"])

    def test_universal_only(self):
        ids = c10b.lookup_definition_ids("unknown/x", BEHAVIOR_MASTER_FIXTURE)
        self.assertEqual(ids, ["cookie_naming"])


class TestCycle10Handle(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.tmpdir = Path(self.tmp.name)
        self.rule_path, self.sm, self.ew, self.lock = _setup_state_evidence(self.tmpdir)
        self.master_path = self.tmpdir / "behavior_master.json"
        self.master_path.write_text(json.dumps(BEHAVIOR_MASTER_FIXTURE))

    def tearDown(self):
        self.tmp.cleanup()

    def test_inject_apache(self):
        rule = _valid_rule({
            "vendor": "Apache", "product": "HTTPD",
            "cpe23_template": "cpe:2.3:a:apache:httpd:{version}:*:*:*:*:*:*:*",
        })
        success, _, summary = c10b.handle(
            self.rule_path, rule, self.ew, self.sm, self.lock,
            master_path=self.master_path,
        )
        self.assertTrue(success)
        self.assertEqual(summary["definitions_count"], 2)
        self.assertEqual(summary["signals_count"], 3)
        loaded = json.loads(self.rule_path.read_text())
        self.assertIn("http_behavior", loaded)
        self.assertEqual(
            loaded["_meta_enrichment"]["cycle_10_behavior"]["go_schema_patch_status"],
            "deferred_phase_2",
        )


# ======================================================================
# Cycle 11 -- Cluster topology + JARM Phase 1
# ======================================================================

CLUSTER_MASTER_FIXTURE = {
    "$schema": "lia-cluster-topology-master-v1",
    "definitions": {
        "elasticsearch": {
            "name": "Elasticsearch cluster discovery",
            "discovery_endpoints": [
                {"method": "GET", "path": "/_cluster/health", "expected_keys": ["cluster_name"], "interpretation": "single GET"}
            ],
            "anomaly_indicators": ["single-node cluster on prod port"],
            "request_discipline": "single_request_only",
            "source_url": "https://www.elastic.co/...",
            "source_sha256": "abc",
            "verified_at": "2026-05-02T00:00:00Z",
        },
        "vault": {
            "name": "Vault sys/leader",
            "discovery_endpoints": [
                {"method": "GET", "path": "/v1/sys/leader", "expected_keys": ["ha_enabled"], "interpretation": "leader"},
                {"method": "GET", "path": "/v1/sys/health", "expected_keys": ["initialized"], "interpretation": "health"},
            ],
            "anomaly_indicators": [],
            "source_url": "https://example.com/vault",
            "source_sha256": "def",
            "verified_at": "2026-05-02T00:00:00Z",
        },
    },
    "products": {
        "elastic/elasticsearch": ["elasticsearch"],
        "hashicorp/vault": ["vault"],
    },
}


class TestCycle11Lookup(unittest.TestCase):
    def test_exact_product(self):
        ids = c11.lookup_definition_ids("elastic/elasticsearch", CLUSTER_MASTER_FIXTURE)
        self.assertEqual(ids, ["elasticsearch"])

    def test_no_match(self):
        ids = c11.lookup_definition_ids("unknown/x", CLUSTER_MASTER_FIXTURE)
        self.assertEqual(ids, [])


class TestCycle11Resolve(unittest.TestCase):
    def test_resolve(self):
        defs = c11.resolve_definitions(["elasticsearch", "vault"], CLUSTER_MASTER_FIXTURE)
        self.assertEqual(len(defs), 2)
        self.assertEqual(defs[0]["definition_id"], "elasticsearch")


class TestCycle11Handle(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.tmpdir = Path(self.tmp.name)
        self.rule_path, self.sm, self.ew, self.lock = _setup_state_evidence(self.tmpdir)
        self.master_path = self.tmpdir / "cluster_master.json"
        self.master_path.write_text(json.dumps(CLUSTER_MASTER_FIXTURE))

    def tearDown(self):
        self.tmp.cleanup()

    def test_skip_no_match(self):
        rule = _valid_rule({
            "vendor": "Apache", "product": "Tomcat",
            "cpe23_template": "cpe:2.3:a:apache:tomcat:{version}:*:*:*:*:*:*:*",
        })
        success, _, summary = c11.handle(
            self.rule_path, rule, self.ew, self.sm, self.lock,
            master_path=self.master_path,
        )
        self.assertFalse(success)
        self.assertEqual(summary["reason"], "no_match")

    def test_inject_elasticsearch(self):
        rule = _valid_rule({
            "vendor": "Elastic", "product": "Elasticsearch",
            "cpe23_template": "cpe:2.3:a:elastic:elasticsearch:{version}:*:*:*:*:*:*:*",
        })
        success, _, summary = c11.handle(
            self.rule_path, rule, self.ew, self.sm, self.lock,
            master_path=self.master_path,
        )
        self.assertTrue(success)
        self.assertEqual(summary["definitions_count"], 1)
        loaded = json.loads(self.rule_path.read_text())
        self.assertIn("cluster_topology", loaded)
        self.assertIn("jarm_signatures", loaded)
        self.assertEqual(loaded["jarm_signatures"]["status"], "placeholder")

    def test_endpoints_count_aggregate(self):
        rule = _valid_rule({
            "vendor": "HashiCorp", "product": "Vault",
            "cpe23_template": "cpe:2.3:a:hashicorp:vault:{version}:*:*:*:*:*:*:*",
        })
        success, _, summary = c11.handle(
            self.rule_path, rule, self.ew, self.sm, self.lock,
            master_path=self.master_path,
        )
        self.assertTrue(success)
        self.assertEqual(summary["endpoints_count"], 2)


# ======================================================================
# Cycle 12 -- Honeypot
# ======================================================================

HONEYPOT_MASTER_FIXTURE = {
    "$schema": "lia-honeypot-master-v1",
    "generated_at": "2026-05-02T00:00:00Z",
    "indicator_definitions": {
        "cowrie_default_banner": {
            "name": "Cowrie default SSH banner",
            "type": "banner_match",
            "match": {"ssh_banner_regex": "^SSH-2\\.0-OpenSSH_9\\.2p1"},
            "confidence": 0.55,
            "severity": "high",
            "source_id": "cowrie_repo",
            "source_url": "https://example.com/cowrie",
            "source_sha256": "abc",
            "verified_at": "2026-05-02T00:00:00Z",
        },
        "conpot_siemens_default": {
            "name": "Conpot Siemens default",
            "type": "string_match_any",
            "match": {"string_alternatives": ["Siemens, SIMATIC, S7-200"]},
            "confidence": 0.70,
            "severity": "critical",
            "source_id": "conpot_repo",
            "source_url": "https://example.com/conpot",
            "source_sha256": "def",
            "verified_at": "2026-05-02T00:00:00Z",
        },
        "tpot_port_constellation": {
            "name": "T-Pot port constellation",
            "type": "port_constellation",
            "match": {"min_ports_open": 5, "candidate_ports": [22, 80, 443]},
            "confidence": 0.70,
            "severity": "high",
            "source_id": "tpot_repo",
            "source_url": "https://example.com/tpot",
            "source_sha256": "ghi",
            "verified_at": "2026-05-02T00:00:00Z",
        },
    },
    "products": {
        "openbsd/openssh": ["cowrie_default_banner"],
        "siemens/*": ["conpot_siemens_default"],
        "*/*": ["tpot_port_constellation"],
    },
    "scoring_rule": "If 2+ indicators match -> is_likely_honeypot=true",
}


class TestCycle12Lookup(unittest.TestCase):
    def test_lookup_exact(self):
        ids = c12.lookup_indicator_ids("openbsd/openssh", HONEYPOT_MASTER_FIXTURE)
        self.assertIn("cowrie_default_banner", ids)
        self.assertIn("tpot_port_constellation", ids)

    def test_lookup_vendor_wildcard(self):
        ids = c12.lookup_indicator_ids("siemens/simatic_s7-200", HONEYPOT_MASTER_FIXTURE)
        self.assertIn("conpot_siemens_default", ids)
        self.assertIn("tpot_port_constellation", ids)

    def test_lookup_universal_only(self):
        ids = c12.lookup_indicator_ids("unknown/x", HONEYPOT_MASTER_FIXTURE)
        self.assertEqual(ids, ["tpot_port_constellation"])


class TestCycle12Resolve(unittest.TestCase):
    def test_resolve_with_max_severity(self):
        ids = ["cowrie_default_banner", "conpot_siemens_default"]
        ind = c12.resolve_indicators(ids, HONEYPOT_MASTER_FIXTURE)
        self.assertEqual(len(ind), 2)
        self.assertEqual(c12._max_severity(ind), "critical")


class TestCycle12Handle(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.tmpdir = Path(self.tmp.name)
        self.rule_path, self.sm, self.ew, self.lock = _setup_state_evidence(self.tmpdir)
        self.master_path = self.tmpdir / "honeypot_master.json"
        self.master_path.write_text(json.dumps(HONEYPOT_MASTER_FIXTURE))

    def tearDown(self):
        self.tmp.cleanup()

    def test_skip_no_product_key(self):
        rule = {}
        self.rule_path.write_text(json.dumps(rule))
        success, _, summary = c12.handle(
            self.rule_path, rule, self.ew, self.sm, self.lock,
            master_path=self.master_path,
        )
        self.assertFalse(success)
        self.assertEqual(summary["reason"], "no_product_key")

    def test_inject_universal(self):
        rule = _valid_rule({
            "vendor": "Apache", "product": "Tomcat",
            "cpe23_template": "cpe:2.3:a:apache:tomcat:{version}:*:*:*:*:*:*:*",
        })
        success, _, summary = c12.handle(
            self.rule_path, rule, self.ew, self.sm, self.lock,
            master_path=self.master_path,
        )
        self.assertTrue(success)
        self.assertEqual(summary["indicators_count"], 1)
        loaded = json.loads(self.rule_path.read_text())
        self.assertIn("honeypot_indicators", loaded)
        self.assertEqual(loaded["honeypot_indicators"][0]["indicator_id"], "tpot_port_constellation")
        self.assertIn("cycle_12_honeypot", loaded.get("_meta_enrichment", {}))

    def test_inject_siemens_critical(self):
        rule = _valid_rule({
            "vendor": "Siemens", "product": "SIMATIC S7-200",
            "cpe23_template": "cpe:2.3:o:siemens:simatic_s7-200:{version}:*:*:*:*:*:*:*",
        })
        success, _, summary = c12.handle(
            self.rule_path, rule, self.ew, self.sm, self.lock,
            master_path=self.master_path,
        )
        self.assertTrue(success)
        self.assertEqual(summary["max_severity"], "critical")


# ---------------------------------------------------------------------------
# Cycle 6 -- Compliance framework mapping
# ---------------------------------------------------------------------------

COMPLIANCE_MASTER_FIXTURE = {
    "$schema": "lia-compliance-master-v1",
    "generated_at": "2026-05-02T12:00:00Z",
    "description": "Test compliance master",
    "sources": {},
    "frameworks": {
        "anssi": {"description": "ANSSI Guide Hygiene Informatique v2"},
        "nis2": {"description": "NIS2 Directive (EU) 2022/2555"},
        "iso27001": {"description": "ISO/IEC 27001:2022 Annex A"},
        "ebios_rm": {"description": "EBIOS RM v1.5"},
    },
    "product_mappings": {
        "jenkins/jenkins": {
            "anssi": ["R5", "R14", "R17", "R38"],
            "nis2": ["art21.2.b", "art21.2.d", "art21.2.e"],
            "iso27001": ["A.8.8", "A.8.9", "A.8.19"],
            "ebios_rm": ["WS2", "WS4", "FE.CONF", "FE.INTEG"],
        },
        "apache/http_server": {
            "anssi": ["R5", "R38", "R39"],
            "nis2": ["art21.2.b", "art21.2.d"],
            "iso27001": ["A.8.8", "A.8.9"],
            "ebios_rm": ["WS2", "WS4"],
        },
    },
}


def _setup_compliance_master(tmpdir: Path) -> Path:
    master_path = tmpdir / "compliance_master.json"
    master_path.write_text(json.dumps(COMPLIANCE_MASTER_FIXTURE), encoding="utf-8")
    return master_path


class TestCycle6ProductKey(unittest.TestCase):
    """Unit tests for _build_product_key helper."""

    def test_build_product_key_from_cpe(self):
        rule = _valid_rule()
        # cpe:2.3:a:jenkins:jenkins:{version}:... -> "jenkins/jenkins"
        key = c6._build_product_key(rule)
        self.assertEqual(key, "jenkins/jenkins")

    def test_build_product_key_cpe_uppercase_lowercased(self):
        rule = _valid_rule({
            "cpe23_template": "cpe:2.3:a:Apache:HTTP_Server:{version}:*:*:*:*:*:*:*",
        })
        key = c6._build_product_key(rule)
        self.assertEqual(key, "apache/http_server")

    def test_build_product_key_fallback_vendor_product(self):
        rule = _valid_rule({
            "cpe23_template": "",
            "vendor": "Redis",
            "product": "Redis",
        })
        key = c6._build_product_key(rule)
        self.assertEqual(key, "redis/redis")

    def test_build_product_key_none_when_no_data(self):
        rule = {
            "$schema": "lia-fingerprint-v1",
            "id": "lia_unknown",
            "cpe23_template": "",
        }
        key = c6._build_product_key(rule)
        self.assertIsNone(key)


class TestCycle6Lookup(unittest.TestCase):
    """Unit tests for lookup_compliance_mappings."""

    def test_lookup_known_product(self):
        result = c6.lookup_compliance_mappings("jenkins/jenkins", COMPLIANCE_MASTER_FIXTURE)
        self.assertIsNotNone(result)
        self.assertIn("anssi", result)
        self.assertIn("nis2", result)
        self.assertIn("iso27001", result)
        self.assertIn("ebios_rm", result)
        self.assertIn("R5", result["anssi"])

    def test_lookup_unknown_product_returns_none(self):
        result = c6.lookup_compliance_mappings("unknown/vendor", COMPLIANCE_MASTER_FIXTURE)
        self.assertIsNone(result)

    def test_lookup_all_frameworks_present_even_if_empty(self):
        # A mapping entry with only some frameworks filled should still return all 4 keys.
        master = {
            "product_mappings": {
                "test/product": {
                    "anssi": ["R1"],
                    # nis2, iso27001, ebios_rm omitted
                },
            },
        }
        result = c6.lookup_compliance_mappings("test/product", master)
        self.assertIsNotNone(result)
        for fw in ("anssi", "nis2", "iso27001", "ebios_rm"):
            self.assertIn(fw, result)
        self.assertEqual(result["nis2"], [])
        self.assertEqual(result["iso27001"], [])


class TestCycle6Handle(unittest.TestCase):
    """Integration tests for handle() -- filesystem-based, no live DB."""

    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.tmpdir = Path(self.tmp.name)
        self.rule_path, self.sm, self.ew, self.lock = _setup_state_evidence(self.tmpdir)
        self.master_path = _setup_compliance_master(self.tmpdir)

    def tearDown(self):
        self.tmp.cleanup()

    def test_skip_no_product_key(self):
        rule = {
            "$schema": "lia-fingerprint-v1",
            "id": "lia_no_key",
            "cpe23_template": "",
        }
        self.rule_path.write_text(json.dumps(rule), encoding="utf-8")
        success, diff, summary = c6.handle(
            self.rule_path, rule, self.ew, self.sm, self.lock,
            master_path=self.master_path,
        )
        self.assertFalse(success)
        self.assertEqual(summary.get("reason"), "no_product_key")

    def test_skip_master_missing(self):
        rule = _valid_rule()
        missing_path = self.tmpdir / "nonexistent_master.json"
        success, diff, summary = c6.handle(
            self.rule_path, rule, self.ew, self.sm, self.lock,
            master_path=missing_path,
        )
        self.assertFalse(success)
        self.assertEqual(summary.get("reason"), "master_missing")

    def test_skip_no_match(self):
        rule = _valid_rule({
            "cpe23_template": "cpe:2.3:a:unknownvendor:unknownprod:{version}:*:*:*:*:*:*:*",
        })
        self.rule_path.write_text(json.dumps(rule), encoding="utf-8")
        success, diff, summary = c6.handle(
            self.rule_path, rule, self.ew, self.sm, self.lock,
            master_path=self.master_path,
        )
        self.assertFalse(success)
        self.assertEqual(summary.get("reason"), "no_match")

    def test_success_inject_mappings(self):
        rule = _valid_rule()
        self.rule_path.write_text(json.dumps(rule), encoding="utf-8")
        success, diff, summary = c6.handle(
            self.rule_path, rule, self.ew, self.sm, self.lock,
            master_path=self.master_path,
        )
        self.assertTrue(success)
        loaded = json.loads(self.rule_path.read_text(encoding="utf-8"))
        self.assertIn("compliance_mappings", loaded)
        self.assertIn("R5", loaded["compliance_mappings"]["anssi"])
        self.assertIn("_meta_enrichment", loaded)
        self.assertIn("cycle_6_compliance", loaded["_meta_enrichment"])

    def test_all_frameworks_present_in_output(self):
        rule = _valid_rule()
        self.rule_path.write_text(json.dumps(rule), encoding="utf-8")
        success, diff, summary = c6.handle(
            self.rule_path, rule, self.ew, self.sm, self.lock,
            master_path=self.master_path,
        )
        self.assertTrue(success)
        loaded = json.loads(self.rule_path.read_text(encoding="utf-8"))
        mappings = loaded["compliance_mappings"]
        for fw in ("anssi", "nis2", "iso27001", "ebios_rm"):
            self.assertIn(fw, mappings)

    def test_summary_controls_count(self):
        rule = _valid_rule()
        self.rule_path.write_text(json.dumps(rule), encoding="utf-8")
        success, diff, summary = c6.handle(
            self.rule_path, rule, self.ew, self.sm, self.lock,
            master_path=self.master_path,
        )
        self.assertTrue(success)
        # jenkins/jenkins has 4+3+3+4=14 controls total in the fixture
        self.assertEqual(summary["total_controls"], 14)
        self.assertIn("per_framework", summary)
        self.assertEqual(summary["per_framework"]["anssi"], 4)


if __name__ == "__main__":
    unittest.main(verbosity=2)
