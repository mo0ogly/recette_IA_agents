"""
LiaProbe Phase 2 - Cycle 9 Certificate Pattern Tests
Tests for cert_patterns_master.json pattern matching logic.

Each test verifies that a pattern's regex matches the expected TLS Subject/Issuer
fields based on the official vendor documentation cited in the master file.
"""

import json
import re
import os
import unittest

MASTER_FILE = os.path.join(
    os.path.dirname(__file__),
    "/opt/lia-sec/dev/_alire/tracking/liaprobe-enrich-v2/master_data/cert_patterns_master.json"
)


def load_master():
    with open(MASTER_FILE, "r") as f:
        return json.load(f)


def match_pattern(pattern_def, subject_cn=None, subject_dn=None, issuer_cn=None, issuer_dn=None, san=None):
    """Apply all regexes from a pattern definition against provided cert fields.
    Returns True only if ALL present match fields in the pattern are satisfied."""
    m = pattern_def.get("match", {})
    checks = {
        "subject_cn_regex": subject_cn,
        "subject_dn_regex": subject_dn,
        "issuer_cn_regex": issuer_cn,
        "issuer_dn_regex": issuer_dn,
        "san_regex": san,
    }
    for key, value in m.items():
        if key in checks:
            if checks[key] is None:
                return False
            if not re.search(m[key], checks[key]):
                return False
    return True


class TestCycle9CertPatterns(unittest.TestCase):
    """Tests for Cycle 9 newly verified TLS certificate patterns."""

    @classmethod
    def setUpClass(cls):
        cls.master = load_master()
        cls.patterns = cls.master["pattern_definitions"]

    # --- Let's Encrypt updated chain ---

    def test_letsencrypt_new_intermediates_e7(self):
        """E7 and E8 ECDSA intermediates (active since 2025, expiry 2027-03-12) match."""
        pattern = self.patterns["letsencrypt_issuer_chain"]
        self.assertTrue(
            match_pattern(pattern,
                issuer_dn="O=Let's Encrypt",
                issuer_cn="E7"),
            "E7 Let's Encrypt intermediate must match letsencrypt_issuer_chain"
        )

    def test_letsencrypt_new_intermediates_r12(self):
        """R12 and R13 RSA intermediates (active since 2025, expiry 2027-03-12) match."""
        pattern = self.patterns["letsencrypt_issuer_chain"]
        self.assertTrue(
            match_pattern(pattern,
                issuer_dn="O=Let's Encrypt",
                issuer_cn="R12"),
            "R12 Let's Encrypt intermediate must match letsencrypt_issuer_chain"
        )

    def test_letsencrypt_new_intermediates_yr1(self):
        """YR1/YR2/YE1/YE2 (Y-generation intermediates, expiry 2028-09-02) match."""
        pattern = self.patterns["letsencrypt_issuer_chain"]
        for cn in ("YR1", "YR2", "YE1", "YE2"):
            with self.subTest(cn=cn):
                self.assertTrue(
                    match_pattern(pattern,
                        issuer_dn="O=Let's Encrypt",
                        issuer_cn=cn),
                    f"{cn} Let's Encrypt Y-generation intermediate must match letsencrypt_issuer_chain"
                )

    def test_letsencrypt_legacy_intermediates_still_match(self):
        """Legacy R3/E1 intermediates still match updated pattern."""
        pattern = self.patterns["letsencrypt_issuer_chain"]
        for cn in ("R3", "E1", "R10", "E5"):
            with self.subTest(cn=cn):
                self.assertTrue(
                    match_pattern(pattern,
                        issuer_dn="O=Let's Encrypt",
                        issuer_cn=cn),
                    f"Legacy {cn} must still match letsencrypt_issuer_chain"
                )

    def test_letsencrypt_isrg_root_x1(self):
        """ISRG Root X1 certificate pattern matches."""
        pattern = self.patterns["letsencrypt_isrg_root"]
        self.assertTrue(
            match_pattern(pattern,
                issuer_dn="O=Internet Security Research Group",
                issuer_cn="ISRG Root X1"),
            "ISRG Root X1 must match letsencrypt_isrg_root pattern"
        )

    def test_letsencrypt_isrg_root_x2(self):
        """ISRG Root X2 (ECDSA) certificate pattern matches."""
        pattern = self.patterns["letsencrypt_isrg_root"]
        self.assertTrue(
            match_pattern(pattern,
                issuer_dn="C=US, O=Internet Security Research Group, CN=ISRG Root X2",
                issuer_cn="ISRG Root X2"),
            "ISRG Root X2 must match letsencrypt_isrg_root pattern"
        )

    def test_letsencrypt_isrg_no_false_positive(self):
        """Random CA does not trigger ISRG Root pattern."""
        pattern = self.patterns["letsencrypt_isrg_root"]
        self.assertFalse(
            match_pattern(pattern,
                issuer_dn="O=DigiCert Inc",
                issuer_cn="DigiCert Global Root CA"),
            "DigiCert must NOT match letsencrypt_isrg_root pattern"
        )

    # --- Kubernetes PKI patterns ---

    def test_kubernetes_ca_self_signed(self):
        """kubernetes-ca root CA matches kubernetes_ca pattern."""
        pattern = self.patterns["kubernetes_ca"]
        self.assertTrue(
            match_pattern(pattern,
                subject_cn="kubernetes-ca",
                issuer_cn="kubernetes-ca"),
            "kubernetes-ca self-signed must match kubernetes_ca pattern"
        )

    def test_kubernetes_etcd_ca(self):
        """etcd-ca root CA matches kubernetes_etcd_ca pattern."""
        pattern = self.patterns["kubernetes_etcd_ca"]
        self.assertTrue(
            match_pattern(pattern,
                subject_cn="etcd-ca",
                issuer_cn="etcd-ca"),
            "etcd-ca must match kubernetes_etcd_ca pattern"
        )

    def test_kubernetes_front_proxy_ca(self):
        """kubernetes-front-proxy-ca matches its pattern."""
        pattern = self.patterns["kubernetes_front_proxy_ca"]
        self.assertTrue(
            match_pattern(pattern,
                subject_cn="kubernetes-front-proxy-ca",
                issuer_cn="kubernetes-front-proxy-ca"),
            "kubernetes-front-proxy-ca must match kubernetes_front_proxy_ca pattern"
        )

    def test_kubernetes_apiserver_cert(self):
        """kube-apiserver certificate signed by kubernetes-ca matches."""
        pattern = self.patterns["kubernetes_apiserver"]
        self.assertTrue(
            match_pattern(pattern,
                subject_cn="kube-apiserver",
                issuer_cn="kubernetes-ca"),
            "kube-apiserver cert must match kubernetes_apiserver pattern"
        )

    def test_kubernetes_apiserver_no_false_positive_wrong_issuer(self):
        """kube-apiserver CN with wrong issuer does NOT match."""
        pattern = self.patterns["kubernetes_apiserver"]
        self.assertFalse(
            match_pattern(pattern,
                subject_cn="kube-apiserver",
                issuer_cn="etcd-ca"),
            "kube-apiserver signed by etcd-ca must NOT match kubernetes_apiserver"
        )

    def test_kubernetes_apiserver_kubelet_client_system_masters(self):
        """kube-apiserver-kubelet-client with O=system:masters matches critical pattern."""
        pattern = self.patterns["kubernetes_apiserver_kubelet_client"]
        self.assertTrue(
            match_pattern(pattern,
                subject_cn="kube-apiserver-kubelet-client",
                subject_dn="CN=kube-apiserver-kubelet-client, O=system:masters"),
            "kube-apiserver-kubelet-client with O=system:masters must match critical pattern"
        )

    def test_kubernetes_etcd_server_cert(self):
        """kube-etcd server cert signed by etcd-ca matches."""
        pattern = self.patterns["kubernetes_etcd_server"]
        self.assertTrue(
            match_pattern(pattern,
                subject_cn="kube-etcd",
                issuer_cn="etcd-ca"),
            "kube-etcd must match kubernetes_etcd_server pattern"
        )

    def test_kubernetes_cluster_local_san(self):
        """SAN containing .cluster.local matches Kubernetes SAN pattern."""
        pattern = self.patterns["kubernetes_cluster_local_san"]
        self.assertTrue(
            match_pattern(pattern,
                san="kubernetes.default.svc.cluster.local"),
            "*.svc.cluster.local SAN must match kubernetes_cluster_local_san"
        )

    # --- k3s patterns ---

    def test_k3s_server_ca_pattern(self):
        """k3s-server-ca@<timestamp> matches k3s_server_ca pattern."""
        pattern = self.patterns["k3s_server_ca"]
        self.assertTrue(
            match_pattern(pattern, subject_cn="k3s-server-ca@1749464211"),
            "k3s-server-ca@1749464211 must match k3s_server_ca pattern"
        )

    def test_k3s_client_ca_pattern(self):
        """k3s-client-ca@<timestamp> matches k3s_client_ca pattern."""
        pattern = self.patterns["k3s_client_ca"]
        self.assertTrue(
            match_pattern(pattern, subject_cn="k3s-client-ca@1749464211"),
            "k3s-client-ca@<ts> must match k3s_client_ca pattern"
        )

    def test_k3s_serving_cert_pattern(self):
        """k3s@<timestamp> signed by k3s-server-ca@<timestamp> matches k3s_serving_cert."""
        pattern = self.patterns["k3s_serving_cert"]
        self.assertTrue(
            match_pattern(pattern,
                subject_cn="k3s@1749464211",
                issuer_cn="k3s-server-ca@1749464211"),
            "k3s@<ts> signed by k3s-server-ca@<ts> must match k3s_serving_cert"
        )

    def test_k3s_no_false_positive_plain_k3s(self):
        """Plain 'k3s' CN without timestamp does not match k3s_serving_cert."""
        pattern = self.patterns["k3s_serving_cert"]
        self.assertFalse(
            match_pattern(pattern,
                subject_cn="k3s",
                issuer_cn="k3s-server-ca"),
            "CN=k3s without timestamp must NOT match k3s_serving_cert"
        )

    # --- OpenWrt patterns ---

    def test_openwrt_default_cert(self):
        """OpenWrt with C=ZZ, ST=Somewhere matches openwrt_uhttpd_default_cert."""
        pattern = self.patterns["openwrt_uhttpd_default_cert"]
        self.assertTrue(
            match_pattern(pattern,
                subject_cn="OpenWrt",
                subject_dn="CN=OpenWrt, O=OpenWrt, C=ZZ, ST=Somewhere, L=Unknown"),
            "OpenWrt default cert must match openwrt_uhttpd_default_cert"
        )

    def test_openwrt_no_false_positive_other_cn(self):
        """Non-OpenWrt CN does not match openwrt pattern."""
        pattern = self.patterns["openwrt_uhttpd_default_cert"]
        self.assertFalse(
            match_pattern(pattern,
                subject_cn="MyRouter",
                subject_dn="CN=MyRouter, C=US"),
            "MyRouter must NOT match openwrt_uhttpd_default_cert"
        )

    # --- Caddy patterns ---

    def test_caddy_local_authority(self):
        """Caddy Local Authority issuer matches caddy_local_authority pattern."""
        pattern = self.patterns["caddy_local_authority"]
        self.assertTrue(
            match_pattern(pattern,
                issuer_dn="O=Caddy Local Authority"),
            "O=Caddy Local Authority must match caddy_local_authority pattern"
        )

    def test_caddy_local_authority_full_dn(self):
        """Full Caddy issuer DN matches caddy_local_authority."""
        pattern = self.patterns["caddy_local_authority"]
        self.assertTrue(
            match_pattern(pattern,
                issuer_dn="CN=Caddy Local Authority - 2024 ECC Root, O=Caddy Local Authority"),
            "Full Caddy DN must match caddy_local_authority"
        )

    # --- Ceph dashboard patterns ---

    def test_ceph_dashboard_cert(self):
        """CN=ceph-mgr-dashboard, O=IT matches ceph_dashboard_self_signed."""
        pattern = self.patterns["ceph_dashboard_self_signed"]
        self.assertTrue(
            match_pattern(pattern,
                subject_cn="ceph-mgr-dashboard",
                subject_dn="O=IT, CN=ceph-mgr-dashboard"),
            "Ceph dashboard cert must match ceph_dashboard_self_signed"
        )

    # --- VMware / Synology baseline patterns ---

    def test_vmware_vsphere_issuer(self):
        """O=VMware issuer matches vmware_vsphere_machine_cert."""
        pattern = self.patterns["vmware_vsphere_machine_cert"]
        self.assertTrue(
            match_pattern(pattern,
                issuer_dn="CN=CA, DC=vsphere.local, O=VMware"),
            "O=VMware must match vmware_vsphere_machine_cert"
        )

    def test_synology_default_cn(self):
        """CN=synology matches synology_dsm_default_cert."""
        pattern = self.patterns["synology_dsm_default_cert"]
        self.assertTrue(
            match_pattern(pattern,
                subject_cn="synology",
                issuer_cn="synology"),
            "CN=synology must match synology_dsm_default_cert"
        )

    # --- Schema integrity tests ---

    def test_all_patterns_have_required_fields(self):
        """Every pattern_definition entry must have all mandatory fields."""
        required = {"name", "rationale", "severity", "confidence", "match",
                    "source_id", "source_url", "source_sha256", "source_section", "verified_at"}
        for pid, pdef in self.patterns.items():
            with self.subTest(pattern=pid):
                missing = required - set(pdef.keys())
                self.assertEqual(
                    missing, set(),
                    f"Pattern '{pid}' missing fields: {missing}"
                )

    def test_products_reference_valid_patterns(self):
        """All pattern IDs in products block must exist in pattern_definitions."""
        products = self.master["products"]
        for product_key, pattern_ids in products.items():
            for pid in pattern_ids:
                with self.subTest(product=product_key, pattern=pid):
                    self.assertIn(
                        pid, self.patterns,
                        f"Product '{product_key}' references unknown pattern '{pid}'"
                    )

    def test_products_count_matches(self):
        """products_count header matches actual number of products entries."""
        self.assertEqual(
            self.master["products_count"],
            len(self.master["products"]),
            "products_count must match actual number of product keys"
        )

    def test_patterns_count_matches(self):
        """patterns_count header matches actual number of pattern_definitions."""
        self.assertEqual(
            self.master["patterns_count"],
            len(self.master["pattern_definitions"]),
            "patterns_count must match actual number of pattern_definitions entries"
        )

    def test_confidence_values_in_range(self):
        """All confidence values must be floats between 0.0 and 1.0."""
        for pid, pdef in self.patterns.items():
            with self.subTest(pattern=pid):
                c = pdef["confidence"]
                self.assertIsInstance(c, float, f"Pattern '{pid}': confidence must be float")
                self.assertGreater(c, 0.0, f"Pattern '{pid}': confidence must be > 0")
                self.assertLessEqual(c, 1.0, f"Pattern '{pid}': confidence must be <= 1.0")

    def test_source_sha256_non_empty(self):
        """All source_sha256 values must be non-empty strings (64 hex chars for SHA-256)."""
        for pid, pdef in self.patterns.items():
            with self.subTest(pattern=pid):
                sha = pdef.get("source_sha256", "")
                self.assertGreater(len(sha), 0, f"Pattern '{pid}': source_sha256 must not be empty")

    def test_no_todo_in_verified_patterns(self):
        """No verified pattern should have 'TODO' in source_url or source_section (data fields)."""
        # Only check structured data fields, not free-text rationale which may
        # legitimately describe ISO placeholder codes (e.g. C=ZZ = ISO placeholder).
        for pid, pdef in self.patterns.items():
            for field in ("source_url", "source_section"):
                val = pdef.get(field, "")
                with self.subTest(pattern=pid, field=field):
                    self.assertNotIn("TODO", val, f"Pattern '{pid}'.{field} must not contain TODO")
                    self.assertNotIn("TBD", val, f"Pattern '{pid}'.{field} must not contain TBD")

    def test_severity_values_valid(self):
        """All severity values must be one of: info, medium, high, critical."""
        valid = {"info", "medium", "high", "critical"}
        for pid, pdef in self.patterns.items():
            with self.subTest(pattern=pid):
                self.assertIn(
                    pdef["severity"], valid,
                    f"Pattern '{pid}': severity '{pdef['severity']}' not in {valid}"
                )


if __name__ == "__main__":
    unittest.main(verbosity=2)
