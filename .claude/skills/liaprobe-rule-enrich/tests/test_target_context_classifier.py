"""Tests for target_context_classifier (cycle 13 Phase 1)."""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

SCRIPT_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import target_context_classifier as tcc  # noqa: E402


MASTER_FIXTURE = {
    "$schema": "lia-cidr-context-master-v1",
    "bogon_ranges": [
        {
            "cidr": "10.0.0.0/8",
            "type": "private",
            "source_url": "https://www.rfc-editor.org/rfc/rfc1918.txt",
            "source_sha256": "abc",
        },
        {
            "cidr": "127.0.0.0/8",
            "type": "loopback",
            "source_url": "https://www.iana.org/...",
            "source_sha256": "def",
        },
        {
            "cidr": "100.64.0.0/10",
            "type": "cgnat",
            "source_url": "https://www.rfc-editor.org/rfc/rfc6598.txt",
            "source_sha256": "ghi",
        },
    ],
    "asn_type_map": {
        "source_url": "https://www.peeringdb.com/api/net",
        "asns": {
            "16509": {"organization": "AWS", "type": "cloud", "country": "US"},
            "13335": {"organization": "Cloudflare", "type": "cdn", "country": "US"},
            "16276": {"organization": "OVH", "type": "hosting", "country": "FR"},
        },
    },
    "cdn_server_header_map": {
        "values": {
            "cloudflare": "13335",
            "fastly": "54113",
        }
    },
}


def _master_path(tmpdir: Path) -> Path:
    p = tmpdir / "cidr_context_master.json"
    p.write_text(json.dumps(MASTER_FIXTURE))
    return p


class TestDetectBogon(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.master_path = _master_path(Path(self.tmp.name))
        self.master = MASTER_FIXTURE

    def tearDown(self):
        self.tmp.cleanup()

    def test_rfc1918_class_a(self):
        is_b, t, _ = tcc.detect_bogon("10.0.5.1", self.master)
        self.assertTrue(is_b)
        self.assertEqual(t, "private")

    def test_loopback(self):
        is_b, t, _ = tcc.detect_bogon("127.0.0.1", self.master)
        self.assertTrue(is_b)
        self.assertEqual(t, "loopback")

    def test_cgnat(self):
        is_b, t, _ = tcc.detect_bogon("100.64.5.1", self.master)
        self.assertTrue(is_b)
        self.assertEqual(t, "cgnat")

    def test_public_ip_not_bogon(self):
        is_b, t, _ = tcc.detect_bogon("8.8.8.8", self.master)
        self.assertFalse(is_b)
        self.assertIsNone(t)

    def test_invalid_ip_returns_false(self):
        is_b, t, _ = tcc.detect_bogon("not-an-ip", self.master)
        self.assertFalse(is_b)


class TestLookupAsnType(unittest.TestCase):
    def test_aws(self):
        org, t, c = tcc.lookup_asn_type(16509, MASTER_FIXTURE)
        self.assertEqual(org, "AWS")
        self.assertEqual(t, "cloud")
        self.assertEqual(c, "US")

    def test_cloudflare_cdn(self):
        org, t, c = tcc.lookup_asn_type(13335, MASTER_FIXTURE)
        self.assertEqual(t, "cdn")

    def test_unknown_asn(self):
        org, t, c = tcc.lookup_asn_type(999999, MASTER_FIXTURE)
        self.assertIsNone(org)
        self.assertIsNone(t)
        self.assertIsNone(c)

    def test_none_asn(self):
        org, t, c = tcc.lookup_asn_type(None, MASTER_FIXTURE)
        self.assertIsNone(org)


class TestDetectCdn(unittest.TestCase):
    def test_double_confirmed_cloudflare(self):
        is_cdn, name = tcc.detect_cdn("cloudflare", 13335, MASTER_FIXTURE)
        self.assertTrue(is_cdn)
        self.assertEqual(name, "cloudflare")

    def test_header_no_asn_hint_only(self):
        is_cdn, name = tcc.detect_cdn("cloudflare", None, MASTER_FIXTURE)
        self.assertFalse(is_cdn)
        self.assertEqual(name, "cloudflare")

    def test_header_asn_mismatch(self):
        is_cdn, name = tcc.detect_cdn("cloudflare", 16509, MASTER_FIXTURE)
        self.assertFalse(is_cdn)
        self.assertEqual(name, "cloudflare")

    def test_no_header(self):
        is_cdn, name = tcc.detect_cdn(None, 13335, MASTER_FIXTURE)
        self.assertFalse(is_cdn)
        self.assertIsNone(name)


class TestClassifyTarget(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.master_path = _master_path(Path(self.tmp.name))

    def tearDown(self):
        self.tmp.cleanup()

    def test_internal_target(self):
        ctx = tcc.classify_target("10.0.5.1", master_path=self.master_path)
        self.assertTrue(ctx["is_bogon"])
        self.assertEqual(ctx["bogon_type"], "private")
        self.assertFalse(ctx["is_cloud"])
        self.assertIsNone(ctx["asn"])
        self.assertEqual(len(ctx["source_provenance"]), 1)

    def test_aws_cloud_target(self):
        ctx = tcc.classify_target(
            "1.2.3.4",  # public IP
            asn=16509,
            master_path=self.master_path,
        )
        self.assertFalse(ctx["is_bogon"])
        self.assertTrue(ctx["is_cloud"])
        self.assertEqual(ctx["as_organization"], "AWS")
        self.assertEqual(ctx["country"], "US")

    def test_cloudflare_cdn_double_confirmed(self):
        ctx = tcc.classify_target(
            "1.2.3.4",
            asn=13335,
            server_header="cloudflare",
            master_path=self.master_path,
        )
        self.assertTrue(ctx["is_cdn"])
        self.assertEqual(ctx["cdn_provider"], "cloudflare")

    def test_cdn_header_spoofed_asn_mismatch(self):
        ctx = tcc.classify_target(
            "1.2.3.4",
            asn=16276,  # OVH, not Cloudflare
            server_header="cloudflare",
            master_path=self.master_path,
        )
        self.assertFalse(ctx["is_cdn"])
        self.assertEqual(ctx["cdn_provider"], "cloudflare")  # hint preserved
        self.assertTrue(ctx["is_hosting"])

    def test_unknown_public_ip(self):
        ctx = tcc.classify_target("8.8.8.8", master_path=self.master_path)
        self.assertFalse(ctx["is_bogon"])
        self.assertIsNone(ctx["asn"])
        self.assertIsNone(ctx["as_type"])
        self.assertFalse(ctx["is_cloud"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
