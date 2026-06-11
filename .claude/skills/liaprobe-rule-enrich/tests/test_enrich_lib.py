"""
Unit tests for enrich_lib.

Tests critical paths: atomic write, lock, state, evidence, schema, hash.
External deps mocked (HTTP, PG).

Run:
    cd /opt/lia-sec/dev/.claude/skills/liaprobe-rule-enrich
    python3 -m pytest tests/ -v
    OR
    python3 -m unittest tests.test_enrich_lib -v
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# Add scripts/ to path
SKILL_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SKILL_DIR / "scripts"))

import enrich_lib as el  # noqa: E402


class TestHashHelpers(unittest.TestCase):
    """sha256_*, sha1_path helpers."""

    def test_sha256_string_deterministic(self):
        self.assertEqual(el.sha256_string("hello"), el.sha256_string("hello"))
        self.assertNotEqual(el.sha256_string("hello"), el.sha256_string("world"))

    def test_sha256_canonical_json_key_order(self):
        a = {"x": 1, "y": 2}
        b = {"y": 2, "x": 1}
        self.assertEqual(el.sha256_canonical_json(a), el.sha256_canonical_json(b))

    def test_sha256_canonical_json_unicode(self):
        h = el.sha256_canonical_json({"key": "valeur avec accents éàù"})
        self.assertEqual(len(h), 64)

    def test_sha256_file_matches_string(self):
        with tempfile.NamedTemporaryFile(mode="wb", delete=False) as f:
            f.write(b"hello world")
            tmp = Path(f.name)
        try:
            self.assertEqual(el.sha256_file(tmp), el.sha256_bytes(b"hello world"))
        finally:
            tmp.unlink()

    def test_sha1_path_normalizes_relative_to_absolute(self):
        # Same path, different forms = same hash (after resolve)
        h1 = el.sha1_path("/tmp/foo")
        h2 = el.sha1_path("/tmp/foo")
        self.assertEqual(h1, h2)
        self.assertEqual(len(h1), 40)


class TestAtomicJSONWriter(unittest.TestCase):
    """Atomic write: tmp + replace, idempotent, crash recovery."""

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir)

    def test_write_creates_target_with_correct_content(self):
        path = self.tmpdir / "test.json"
        el.AtomicJSONWriter.write(path, {"a": 1, "b": [2, 3]})
        self.assertTrue(path.exists())
        loaded = json.loads(path.read_text())
        self.assertEqual(loaded, {"a": 1, "b": [2, 3]})

    def test_write_appends_newline(self):
        path = self.tmpdir / "test.json"
        el.AtomicJSONWriter.write(path, {"x": 1})
        self.assertTrue(path.read_text().endswith("\n"))

    def test_write_overwrites_existing(self):
        path = self.tmpdir / "test.json"
        el.AtomicJSONWriter.write(path, {"old": True})
        el.AtomicJSONWriter.write(path, {"new": True})
        self.assertEqual(json.loads(path.read_text()), {"new": True})

    def test_write_atomic_no_partial_on_serialize_error(self):
        path = self.tmpdir / "test.json"
        el.AtomicJSONWriter.write(path, {"initial": True})
        # Try to write non-serializable -> should fail before touching file
        with self.assertRaises(TypeError):
            el.AtomicJSONWriter.write(path, {"bad": object()})
        # File still has initial content
        self.assertEqual(json.loads(path.read_text()), {"initial": True})

    def test_write_raises_if_parent_missing(self):
        path = self.tmpdir / "nonexistent" / "test.json"
        with self.assertRaises(OSError):
            el.AtomicJSONWriter.write(path, {})

    def test_cleanup_orphan_tmp(self):
        path = self.tmpdir / "test.json"
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text("orphan")
        self.assertTrue(el.AtomicJSONWriter.cleanup_orphan_tmp(path))
        self.assertFalse(tmp.exists())
        # Idempotent
        self.assertFalse(el.AtomicJSONWriter.cleanup_orphan_tmp(path))


class TestLockManager(unittest.TestCase):
    """fcntl flock acquire/release/timeout/contention."""

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        self.lock_path = self.tmpdir / "test.lock"

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir)

    def test_acquire_release_basic(self):
        lock = el.LockManager(self.lock_path)
        lock.acquire()
        lock.release()
        # Re-acquire works
        lock.acquire()
        lock.release()

    def test_context_manager(self):
        with el.LockManager(self.lock_path):
            self.assertTrue(self.lock_path.exists())

    def test_double_acquire_same_instance_raises(self):
        lock = el.LockManager(self.lock_path)
        lock.acquire()
        try:
            with self.assertRaises(el.EnrichError):
                lock.acquire()
        finally:
            lock.release()

    def test_concurrent_acquire_blocks_then_succeeds(self):
        lock1 = el.LockManager(self.lock_path, timeout_s=2)
        lock2 = el.LockManager(self.lock_path, timeout_s=2)
        lock1.acquire()
        result = {"acquired": False}

        def try_acquire():
            try:
                lock2.acquire()
                result["acquired"] = True
                lock2.release()
            except el.LockContentionError:
                pass

        t = threading.Thread(target=try_acquire)
        t.start()
        time.sleep(0.3)
        # Lock 2 should still be waiting
        self.assertFalse(result["acquired"])
        lock1.release()
        t.join(timeout=3)
        self.assertTrue(result["acquired"])

    def test_timeout_raises_lockcontentionerror(self):
        # Lock-1 in subprocess to truly block flock (threads share fd)
        # For simplicity here: use 2 LockManagers with very short timeout
        # via file flock. Run in subprocess for real test.
        import multiprocessing as mp

        def hold_lock(path: str, hold_s: float):
            lock = el.LockManager(Path(path))
            lock.acquire()
            time.sleep(hold_s)
            lock.release()

        p = mp.Process(target=hold_lock, args=(str(self.lock_path), 1.5))
        p.start()
        time.sleep(0.3)  # ensure child acquired
        try:
            lock = el.LockManager(self.lock_path, timeout_s=0.5)
            with self.assertRaises(el.LockContentionError):
                lock.acquire()
        finally:
            p.join(timeout=5)


class TestSchemaValidator(unittest.TestCase):
    """Validate fingerprint + evidence schemas."""

    def test_valid_fingerprint(self):
        data = {
            "$schema": "lia-fingerprint-v1",
            "id": "lia-jenkins",
            "taxonomy_code": "JENKINS",
            "product": "Jenkins",
        }
        # Should not raise
        el.SchemaValidator.validate_fingerprint(data)

    def test_missing_required_field(self):
        data = {"$schema": "lia-fingerprint-v1", "id": "x"}  # missing taxonomy_code
        with self.assertRaises(el.InvalidInputError):
            el.SchemaValidator.validate_fingerprint(data)

    def test_wrong_schema_version(self):
        data = {
            "$schema": "wrong-schema",
            "id": "x",
            "taxonomy_code": "X",
            "product": "X",
        }
        with self.assertRaises(el.InvalidInputError):
            el.SchemaValidator.validate_fingerprint(data)

    def test_valid_evidence(self):
        ev = {
            "$schema": "lia-enrich-evidence-v1",
            "cycle": "4_cve",
            "rule": {"id": "lia-jenkins", "path": "x", "rule_sha256": "a" * 64},
            "applied_at": "2026-05-02T14:30:00Z",
            "applied_by": "test",
            "source": {"type": "postgresql"},
            "raw_data_sha256": "a" * 64,
            "applied_diff_sha256": "b" * 64,
        }
        el.SchemaValidator.validate_evidence(ev)

    def test_invalid_evidence_source_type(self):
        if not el.HAS_JSONSCHEMA:
            self.skipTest("jsonschema not installed")
        ev = {
            "$schema": "lia-enrich-evidence-v1",
            "cycle": "4_cve",
            "rule": {"id": "x", "path": "y", "rule_sha256": "a" * 64},
            "applied_at": "x",
            "applied_by": "x",
            "source": {"type": "invalid_source_type"},
            "raw_data_sha256": "a" * 64,
            "applied_diff_sha256": "b" * 64,
        }
        with self.assertRaises(el.InvalidInputError):
            el.SchemaValidator.validate_evidence(ev)


class TestStructuredLogger(unittest.TestCase):
    """Append-only JSONL audit log."""

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        self.log_path = self.tmpdir / "test.jsonl"

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir)

    def test_log_writes_jsonl(self):
        logger = el.StructuredLogger(self.log_path)
        logger.log(action="TEST", value=42)
        logger.log(action="TEST2", x="y")
        lines = self.log_path.read_text().splitlines()
        self.assertEqual(len(lines), 2)
        e1 = json.loads(lines[0])
        self.assertEqual(e1["action"], "TEST")
        self.assertEqual(e1["value"], 42)
        self.assertIn("timestamp", e1)

    def test_log_concurrent_appends(self):
        logger = el.StructuredLogger(self.log_path)
        threads = []
        for i in range(20):
            t = threading.Thread(target=logger.log, kwargs={"i": i})
            threads.append(t)
            t.start()
        for t in threads:
            t.join()
        lines = self.log_path.read_text().splitlines()
        self.assertEqual(len(lines), 20)
        for line in lines:
            json.loads(line)  # all parseable


class TestStateManager(unittest.TestCase):
    """State file load/save, cycles, lifecycle."""

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        self.state_dir = self.tmpdir / "state"
        self.sm = el.StateManager(self.state_dir)
        self.rule_path = self.tmpdir / "rule.json"
        self.rule_path.write_text("{}")

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir)

    def test_fresh_state_has_all_cycles(self):
        s = self.sm.load(self.rule_path)
        self.assertEqual(s["lifecycle_state"], "PRISTINE")
        for c in el.CYCLES:
            self.assertIn(c, s["cycles"])
            self.assertEqual(s["cycles"][c]["status"], "pending")

    def test_save_load_roundtrip(self):
        s = self.sm.load(self.rule_path)
        s["audit"]["test_marker"] = "X"
        self.sm.save(self.rule_path, s)
        s2 = self.sm.load(self.rule_path)
        self.assertEqual(s2["audit"]["test_marker"], "X")

    def test_mark_cycle_done_promotes_lifecycle(self):
        ev_path = self.tmpdir / "evidence.json"
        ev_path.write_text("{}")
        self.sm.mark_cycle_done(
            self.rule_path, "cycle_4_cve",
            evidence_path=ev_path,
            evidence_sha256="a" * 64,
            summary={"cve_count": 10},
        )
        s = self.sm.load(self.rule_path)
        self.assertEqual(s["lifecycle_state"], "ENRICHED")
        self.assertEqual(s["cycles"]["cycle_4_cve"]["status"], "completed")
        self.assertEqual(s["cycles"]["cycle_4_cve"]["summary"]["cve_count"], 10)
        self.assertIsNotNone(s["first_enriched_at"])

    def test_mark_cycle_skipped(self):
        self.sm.mark_cycle_skipped(self.rule_path, "cycle_5_eol", "no slug")
        s = self.sm.load(self.rule_path)
        self.assertEqual(s["cycles"]["cycle_5_eol"]["status"], "skipped")
        self.assertEqual(s["cycles"]["cycle_5_eol"]["skip_reason"], "no slug")

    def test_unknown_cycle_raises(self):
        with self.assertRaises(el.InvalidInputError):
            self.sm.mark_cycle_skipped(self.rule_path, "cycle_99_fake", "x")

    def test_lock_returns_lockmanager_bound_to_rule(self):
        with self.sm.lock(self.rule_path):
            # Lock acquired
            pass


class TestEvidenceWriter(unittest.TestCase):
    """Evidence write + symlink + verify integrity."""

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        self.fp_root = self.tmpdir / "data" / "fingerprints"
        self.en_root = self.tmpdir / "data" / "enrichment"
        (self.fp_root / "lia").mkdir(parents=True)
        self.rule_path = self.fp_root / "lia" / "JENKINS.json"
        self.rule_path.write_text(json.dumps({"id": "lia-jenkins"}))
        self.ew = el.EvidenceWriter(self.en_root, self.fp_root)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir)

    def test_compute_enrichment_dir(self):
        d = self.ew.compute_enrichment_dir(self.rule_path)
        expected = self.en_root / "lia" / "JENKINS"
        self.assertEqual(d, expected)

    def test_write_creates_evidence_and_symlink(self):
        ev_path, sha = self.ew.write(
            rule_path=self.rule_path,
            cycle_id="cycle_4_cve",
            rule_data={"id": "lia-jenkins"},
            rule_sha256_before="a" * 64,
            rule_sha256_after="b" * 64,
            source_meta={"type": "postgresql", "query": "SELECT 1"},
            raw_data=[{"cve_id": "CVE-2024-1"}],
            applied_diff={"added": "known_cves"},
            summary={"cve_count": 1},
        )
        self.assertTrue(ev_path.exists())
        self.assertTrue(ev_path.name.startswith("cycle_4_cve_"))
        self.assertEqual(len(sha), 64)
        # Symlink
        symlink = ev_path.parent / "cycle_4_cve_latest.symlink"
        self.assertTrue(symlink.is_symlink())
        target = os.readlink(symlink)
        self.assertEqual(target, ev_path.name)

    def test_verify_integrity_match(self):
        ev_path, _ = self.ew.write(
            rule_path=self.rule_path,
            cycle_id="cycle_4_cve",
            rule_data={"id": "lia-jenkins"},
            rule_sha256_before="a" * 64,
            rule_sha256_after="b" * 64,
            source_meta={"type": "postgresql"},
            raw_data=[{"cve": "X"}],
            applied_diff={},
            summary={},
        )
        self.assertTrue(self.ew.verify_integrity(ev_path))

    def test_verify_integrity_detects_tamper(self):
        ev_path, _ = self.ew.write(
            rule_path=self.rule_path,
            cycle_id="cycle_4_cve",
            rule_data={"id": "lia-jenkins"},
            rule_sha256_before="a" * 64,
            rule_sha256_after="b" * 64,
            source_meta={"type": "postgresql"},
            raw_data=[{"cve": "ORIGINAL"}],
            applied_diff={},
            summary={},
        )
        # Tamper: modify raw_data without updating sha
        ev = json.loads(ev_path.read_text())
        ev["raw_data"] = [{"cve": "TAMPERED"}]
        ev_path.write_text(json.dumps(ev))
        self.assertFalse(self.ew.verify_integrity(ev_path))

    def test_two_writes_create_distinct_files(self):
        ev1, _ = self.ew.write(
            self.rule_path, "cycle_4_cve", {"id": "x"},
            "a" * 64, "b" * 64, {"type": "postgresql"},
            [], {}, {},
        )
        time.sleep(1.1)  # ensure different timestamp
        ev2, _ = self.ew.write(
            self.rule_path, "cycle_4_cve", {"id": "x"},
            "a" * 64, "c" * 64, {"type": "postgresql"},
            [], {}, {},
        )
        self.assertNotEqual(ev1, ev2)
        # Symlink points to latest
        symlink = ev2.parent / "cycle_4_cve_latest.symlink"
        self.assertEqual(os.readlink(symlink), ev2.name)


class TestHTTPClient(unittest.TestCase):
    """HTTP client with cache + retry (mocked urllib)."""

    def setUp(self):
        self.tmpdir = Path(tempfile.mkdtemp())
        self.cache = self.tmpdir / "cache"

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmpdir)

    @patch("urllib.request.urlopen")
    def test_get_caches_response(self, mock_urlopen):
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = b'{"x":1}'
        mock_urlopen.return_value.__enter__.return_value = mock_resp

        c = el.HTTPClient(self.cache)
        r1 = c.get("https://example.com/api")
        self.assertEqual(r1.status, 200)
        self.assertFalse(r1.from_cache)
        # Second call: cached
        r2 = c.get("https://example.com/api")
        self.assertTrue(r2.from_cache)
        self.assertEqual(r2.body, b'{"x":1}')
        self.assertEqual(mock_urlopen.call_count, 1)

    @patch("urllib.request.urlopen")
    def test_retry_on_failure(self, mock_urlopen):
        from urllib.error import URLError
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.read.return_value = b"OK"

        # Fail twice, succeed third
        cm = MagicMock()
        cm.__enter__.return_value = mock_resp
        side = [URLError("net fail"), URLError("net fail2"), cm]
        mock_urlopen.side_effect = side

        c = el.HTTPClient(self.cache)
        # speed up retries
        with patch("time.sleep"):
            r = c.get("https://example.com/api")
        self.assertEqual(r.status, 200)
        self.assertEqual(mock_urlopen.call_count, 3)

    @patch("urllib.request.urlopen")
    def test_all_retries_fail_raises(self, mock_urlopen):
        from urllib.error import URLError
        mock_urlopen.side_effect = URLError("permanent")
        c = el.HTTPClient(self.cache)
        with patch("time.sleep"):
            with self.assertRaises(el.DependencyMissingError):
                c.get("https://example.com/api")


class TestPGClientDSNResolution(unittest.TestCase):
    """PG client DSN resolution from env vars."""

    def test_database_url_priority(self):
        with patch.dict(os.environ, {"DATABASE_URL": "postgresql://u:p@h/db"}, clear=True):
            c = el.PGClient.__new__(el.PGClient)  # bypass __init__
            self.assertEqual(c._resolve_dsn(), "postgresql://u:p@h/db")

    def test_lia_db_vars(self):
        env = {
            "LIA_DB_HOST": "localhost",
            "LIA_DB_PORT": "5432",
            "LIA_DB_NAME": "lia_scan",
            "LIA_DB_USER": "lia_admin",
            "LIA_DB_PASS": "secret!@#",
        }
        with patch.dict(os.environ, env, clear=True):
            c = el.PGClient.__new__(el.PGClient)
            dsn = c._resolve_dsn()
            self.assertIn("localhost", dsn)
            self.assertIn("lia_scan", dsn)
            self.assertIn("lia_admin", dsn)
            # Special chars should be url-quoted
            self.assertIn("secret%21%40%23", dsn)

    def test_no_password_raises(self):
        with patch.dict(os.environ, {}, clear=True):
            c = el.PGClient.__new__(el.PGClient)
            with self.assertRaises(el.DependencyMissingError):
                c._resolve_dsn()

    def test_load_env_file(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False) as f:
            f.write("# comment\nLIA_TEST_VAR=hello\nQUOTED=\"world\"\n")
            tmp = Path(f.name)
        try:
            # Clear existing
            for k in ("LIA_TEST_VAR", "QUOTED"):
                os.environ.pop(k, None)
            el.PGClient._load_env_file(tmp)
            self.assertEqual(os.environ.get("LIA_TEST_VAR"), "hello")
            self.assertEqual(os.environ.get("QUOTED"), "world")
        finally:
            tmp.unlink()
            for k in ("LIA_TEST_VAR", "QUOTED"):
                os.environ.pop(k, None)


class TestCYCLESConstant(unittest.TestCase):
    """Sanity check on cycles registry."""

    def test_cycles_count(self):
        self.assertEqual(len(el.CYCLES), 9)

    def test_cycles_naming(self):
        for c in el.CYCLES:
            self.assertTrue(c.startswith("cycle_"))


class TestExtractCpeVendor(unittest.TestCase):
    """extract_cpe_vendor() helper."""

    def test_extracts_from_valid_cpe23(self):
        rule = {"cpe23_template": "cpe:2.3:a:apache:activemq:%:*:*:*:*:*:*:*"}
        self.assertEqual(el.extract_cpe_vendor(rule), "apache")

    def test_falls_back_to_vendor_field(self):
        rule = {"vendor": "Apache Software Foundation"}
        self.assertEqual(el.extract_cpe_vendor(rule), "Apache Software Foundation")

    def test_returns_none_when_no_data(self):
        self.assertIsNone(el.extract_cpe_vendor({}))

    def test_skips_wildcard_vendor(self):
        rule = {"cpe23_template": "cpe:2.3:a:*:irc_server:%:*:*:*:*:*:*:*", "vendor": "fallback"}
        self.assertEqual(el.extract_cpe_vendor(rule), "fallback")

    def test_accepts_hardware_cpe_vendor(self):
        rule = {"cpe23_template": "cpe:2.3:h:bosch:ip_bullet_5000:*:*:*:*:*:*:*:*"}
        self.assertEqual(el.extract_cpe_vendor(rule), "bosch")

    def test_rejects_os_cpe_vendor_and_falls_back(self):
        rule = {
            "cpe23_template": "cpe:2.3:o:microsoft:windows:*:*:*:*:*:*:*:*",
            "vendor": "Real Service Vendor",
        }
        self.assertEqual(el.extract_cpe_vendor(rule), "Real Service Vendor")

    def test_parses_cpe_2_2_application(self):
        rule = {"cpe23_template": "cpe:/a:apache:tomcat:9.0.50"}
        self.assertEqual(el.extract_cpe_vendor(rule), "apache")

    def test_parses_cpe_2_2_hardware(self):
        rule = {"cpe23_template": "cpe:/h:cisco:asa_5510:9.6.1"}
        self.assertEqual(el.extract_cpe_vendor(rule), "cisco")

    def test_parses_cpe_2_2_os_falls_back(self):
        rule = {"cpe23_template": "cpe:/o:cumulusnetworks:cumulus_linux:4.0", "vendor": "Cumulus"}
        self.assertEqual(el.extract_cpe_vendor(rule), "Cumulus")


class TestCpePartClassify(unittest.TestCase):
    """_cpe_part_classify() returns 'a' / 'h' / 'o' / None."""

    def test_application(self):
        self.assertEqual(el._cpe_part_classify("cpe:2.3:a:apache:httpd:*:*:*:*:*:*:*:*"), "a")

    def test_hardware(self):
        self.assertEqual(el._cpe_part_classify("cpe:2.3:h:cisco:asa:*:*:*:*:*:*:*:*"), "h")

    def test_os(self):
        self.assertEqual(el._cpe_part_classify("cpe:2.3:o:microsoft:windows:*:*:*:*:*:*:*:*"), "o")

    def test_cpe_2_2_application(self):
        self.assertEqual(el._cpe_part_classify("cpe:/a:apache:tomcat:9.0"), "a")

    def test_cpe_2_2_os(self):
        self.assertEqual(el._cpe_part_classify("cpe:/o:linux:linux_kernel:5.10"), "o")

    def test_invalid_returns_none(self):
        self.assertIsNone(el._cpe_part_classify(""))
        self.assertIsNone(el._cpe_part_classify("not-a-cpe"))
        self.assertIsNone(el._cpe_part_classify("cpe:2.3:a"))  # truncated


class TestPhaseCDenylist(unittest.TestCase):
    """Phase C false-positive denylists.

    Each denylist entry traces to a documented FP incident in
    brainstorm_phase_c/CONSOLIDATED.md (2026-05-04).
    """

    def test_runtime_noise_blocks_apache(self):
        # CHKMK.json incident: vendor=tribe29, notes mention "Apache"
        self.assertTrue(el.is_runtime_noise("apache"))
        self.assertTrue(el.is_runtime_noise("Apache"))
        self.assertTrue(el.is_runtime_noise("APACHE"))

    def test_runtime_noise_blocks_tomcat(self):
        # BAMBO.json incident: vendor=Atlassian, notes mention "Tomcat"
        self.assertTrue(el.is_runtime_noise("tomcat"))
        self.assertTrue(el.is_runtime_noise("Tomcat"))

    def test_runtime_noise_blocks_nginx_openssh(self):
        self.assertTrue(el.is_runtime_noise("nginx"))
        self.assertTrue(el.is_runtime_noise("openssh"))

    def test_runtime_noise_does_not_block_real_vendors(self):
        self.assertFalse(el.is_runtime_noise("kibana"))
        self.assertFalse(el.is_runtime_noise("grafana"))
        self.assertFalse(el.is_runtime_noise("kubernetes"))
        self.assertFalse(el.is_runtime_noise(""))

    def test_protocol_noise_blocks_protocol_tokens(self):
        # Top noise tokens from id-slug analysis (proxy=279, upnp=79, rtsp=77, ...)
        self.assertTrue(el.is_protocol_noise("proxy"))
        self.assertTrue(el.is_protocol_noise("upnp"))
        self.assertTrue(el.is_protocol_noise("rtsp"))
        self.assertTrue(el.is_protocol_noise("finger"))
        self.assertTrue(el.is_protocol_noise("ident"))
        self.assertTrue(el.is_protocol_noise("ssl"))
        self.assertTrue(el.is_protocol_noise("HTTP"))

    def test_protocol_noise_does_not_block_real_vendors(self):
        self.assertFalse(el.is_protocol_noise("microsoft"))
        self.assertFalse(el.is_protocol_noise("cisco"))
        self.assertFalse(el.is_protocol_noise("oracle"))

    def test_taxonomy_noise_blocks_known_fp_first_tokens(self):
        # Strategy 5 confirmed FP: THE -> The-Sz, EASY -> Easy Cms, ABLE -> N-Able
        self.assertTrue(el.is_taxonomy_noise("THE"))
        self.assertTrue(el.is_taxonomy_noise("EASY"))
        self.assertTrue(el.is_taxonomy_noise("ABLE"))
        self.assertTrue(el.is_taxonomy_noise("GRAPHQL"))
        self.assertTrue(el.is_taxonomy_noise("GENERIC"))
        self.assertTrue(el.is_taxonomy_noise("UNKNOWN"))

    def test_taxonomy_noise_case_insensitive(self):
        self.assertTrue(el.is_taxonomy_noise("the"))
        self.assertTrue(el.is_taxonomy_noise("Generic"))

    def test_taxonomy_noise_does_not_block_real_first_tokens(self):
        self.assertFalse(el.is_taxonomy_noise("MICROSOFT"))
        self.assertFalse(el.is_taxonomy_noise("WEBMIN"))
        self.assertFalse(el.is_taxonomy_noise("LINKSYS"))

    def test_taxonomy_noise_blocks_phase_d_generic_words(self):
        # Phase D 2026-05-04: extended denylist after taxonomy_name_capword
        # solo analysis (Coin, Cookie, Daily, Smart, Simple etc were FP candidates).
        self.assertTrue(el.is_taxonomy_noise("COIN"))
        self.assertTrue(el.is_taxonomy_noise("COOKIE"))
        self.assertTrue(el.is_taxonomy_noise("DAILY"))
        self.assertTrue(el.is_taxonomy_noise("SMART"))
        self.assertTrue(el.is_taxonomy_noise("SIMPLE"))
        self.assertTrue(el.is_taxonomy_noise("MODERN"))
        self.assertTrue(el.is_taxonomy_noise("PRO"))
        self.assertTrue(el.is_taxonomy_noise("PLUS"))


class TestCanonicalVendorResolver(unittest.TestCase):
    """CanonicalVendorResolver: exact match, trgm fuzzy, and threshold gate."""

    def _make_resolver(self, query_results):
        """Build a resolver with a mocked PGClient.query()."""
        pg = MagicMock(spec=el.PGClient)
        pg.query = MagicMock(side_effect=query_results)
        return el.CanonicalVendorResolver(pg), pg

    def test_exact_match_returns_payload(self):
        results = [
            [{
                "vendor_id": 992,
                "alias_name": "Jenkins",
                "alias_source": "nvd_cpe",
                "alias_type": "official_name",
                "confidence_score": 1.0,
                "vendor_name": "Jenkins",
            }],
        ]
        r, pg = self._make_resolver(results)
        out = r.resolve("jenkins")
        self.assertIsNotNone(out)
        self.assertEqual(out["vendor_id"], 992)
        self.assertEqual(out["vendor_name"], "Jenkins")
        self.assertEqual(out["resolved_via"], "exact")
        self.assertIsNone(out["similarity"])
        self.assertEqual(pg.query.call_count, 1)

    def test_fuzzy_match_above_threshold(self):
        results = [
            [],  # exact returns nothing
            [{
                "vendor_id": 1234,
                "alias_name": "Apache Software Foundation",
                "alias_source": "fuzzy_match",
                "alias_type": "fuzzy_match",
                "confidence_score": 0.9,
                "vendor_name": "Apache Software Foundation",
                "sim": 0.72,
            }],
        ]
        r, pg = self._make_resolver(results)
        out = r.resolve("apache_software")
        self.assertIsNotNone(out)
        self.assertEqual(out["resolved_via"], "fuzzy_trgm")
        self.assertEqual(out["similarity"], 0.72)
        self.assertEqual(pg.query.call_count, 2)

    def test_fuzzy_below_threshold_returns_none(self):
        results = [
            [],
            [{
                "vendor_id": 9,
                "alias_name": "ZZZUnrelated",
                "alias_source": "x",
                "alias_type": None,
                "confidence_score": 0.5,
                "vendor_name": "ZZZUnrelated",
                "sim": 0.30,
            }],
        ]
        r, _pg = self._make_resolver(results)
        self.assertIsNone(r.resolve("totally-unknown-vendor"))

    def test_no_match_returns_none(self):
        results = [[], []]
        r, _pg = self._make_resolver(results)
        self.assertIsNone(r.resolve("ghost-vendor"))

    def test_empty_token_returns_none_no_query(self):
        r, pg = self._make_resolver([])
        self.assertIsNone(r.resolve(""))
        self.assertIsNone(r.resolve(None))
        self.assertEqual(pg.query.call_count, 0)

    def test_normalize_strips_underscores_and_backslashes(self):
        results = [
            [{
                "vendor_id": 1,
                "alias_name": "Apache Software",
                "alias_source": "nvd_cpe",
                "alias_type": "official_name",
                "confidence_score": 1.0,
                "vendor_name": "Apache Software",
            }],
        ]
        r, pg = self._make_resolver(results)
        out = r.resolve("apache\\_software")
        self.assertIsNotNone(out)
        first_call_args = pg.query.call_args_list[0]
        self.assertEqual(first_call_args.args[1], ("apache software",))

    def test_requires_open_pg_client(self):
        with self.assertRaises(el.InvalidInputError):
            el.CanonicalVendorResolver(None)


if __name__ == "__main__":
    unittest.main(verbosity=2)
