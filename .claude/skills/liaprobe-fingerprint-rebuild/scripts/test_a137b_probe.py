#!/usr/bin/env python3
# Offline tests for a137b_probe -- proves the R14 host-allowlist gate
# INCLUDING the redirect / meta-refresh per-hop recheck (the CRITICAL
# path the A137b-HARNESS critique found had ZERO coverage). Injected
# opener/fetcher; zero real HTTP.

import importlib.util
import unittest
from pathlib import Path

_s = importlib.util.spec_from_file_location(
    "ap", Path(__file__).parent / "a137b_probe.py")
ap = importlib.util.module_from_spec(_s)
_s.loader.exec_module(ap)

MANIFEST = {"entries": {
    "data:A.json": {"website": "https://allowed.com/", "host": "allowed.com",
                    "discriminator": {"match_type": "regex",
                                      "value": r"allowed\.com"}},
    "data:B.json": {"website": "https://blocked.io/", "host": "blocked.io",
                    "discriminator": {"match_type": "exists", "value": ""}},
}}


class FakeFetcher:
    def __init__(self):
        self.calls = []

    def __call__(self, url, allow):
        self.calls.append(url)
        return {"ok": True, "status": 200,
                "body": "<html>allowed.com widget</html>",
                "headers": {"server": "x"}, "final_url": url}


class FakeResp:
    def __init__(self, status, headers, body=b""):
        self.status = status
        self._h = headers
        self._b = body

    @property
    def headers(self):
        class H:
            def __init__(s, d):
                s.d = d

            def items(s):
                return s.d.items()
        return H(self._h)

    def read(self, _n=0):
        return self._b

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def make_open(script):
    """script: dict url -> FakeResp. Records opened URLs; raises if a
    URL not in script is opened (proves no unexpected socket)."""
    opened = []

    def _open(req, timeout):
        u = req.full_url
        opened.append(u)
        if u not in script:
            raise AssertionError(f"OPENED UNSCRIPTED (gate bypass?): {u}")
        return script[u]
    _open.opened = opened
    return _open


class TestGate(unittest.TestCase):
    def test_unauthorized_manifest_host_never_fetched(self):
        f = FakeFetcher()
        r = ap.run(MANIFEST, {"allowed.com"}, live=True, rate=0, fetcher=f)
        self.assertEqual(f.calls, ["https://allowed.com/"])
        self.assertEqual(r["skipped_host"], 1)
        self.assertEqual(r["reachable"], 1)

    def test_plan_mode_zero_network(self):
        f = FakeFetcher()
        r = ap.run(MANIFEST, {"allowed.com", "blocked.io"}, live=False,
                   rate=0, fetcher=f)
        self.assertEqual(f.calls, [])
        self.assertEqual(r["plan_only"], 2)

    def test_cli_live_without_allowlist_refuses(self):
        import subprocess
        import sys
        p = subprocess.run(
            [sys.executable, str(Path(__file__).parent / "a137b_probe.py"),
             "--manifest", "/dev/null", "--live"],
            capture_output=True, text=True)
        self.assertEqual(p.returncode, 2)
        self.assertIn("REFUSED", p.stderr)


class TestRedirectRecheck(unittest.TestCase):
    def test_3xx_to_offlist_host_REFUSED_before_socket(self):
        # allowed.com 302 -> evil.com : evil.com must NEVER be opened.
        op = make_open({"https://allowed.com/": FakeResp(
            302, {"location": "https://evil.com/x"})})
        r = ap.real_fetch("https://allowed.com/", {"allowed.com"},
                          _open=op)
        self.assertFalse(r["ok"])
        self.assertTrue(r["error"].startswith("refused_offlist_host:evil.com"))
        self.assertNotIn("https://evil.com/x", op.opened)

    def test_meta_refresh_to_offlist_host_REFUSED(self):
        op = make_open({"https://allowed.com/": FakeResp(
            200, {}, b'<meta http-equiv=refresh content="0;url=https://evil.com/">')})
        r = ap.real_fetch("https://allowed.com/", {"allowed.com"},
                          _open=op)
        self.assertFalse(r["ok"])
        self.assertTrue(r["error"].startswith("refused_offlist_host:evil.com"))
        self.assertNotIn("https://evil.com/", op.opened)

    def test_3xx_same_allowed_host_is_followed(self):
        op = make_open({
            "https://allowed.com/": FakeResp(
                301, {"location": "https://allowed.com/final"}),
            "https://allowed.com/final": FakeResp(
                200, {"server": "n"}, b"<html>ok allowed.com</html>")})
        r = ap.real_fetch("https://allowed.com/", {"allowed.com"},
                          _open=op)
        self.assertTrue(r["ok"])
        self.assertEqual(r["final_url"], "https://allowed.com/final")

    def test_bare_relative_redirect_stays_on_host_a127(self):
        op = make_open({
            "https://allowed.com/dir/p": FakeResp(
                302, {"location": "next.html"}),
            "https://allowed.com/dir/next.html": FakeResp(
                200, {}, b"ok")})
        r = ap.real_fetch("https://allowed.com/dir/p", {"allowed.com"},
                          _open=op)
        self.assertTrue(r["ok"])
        self.assertEqual(r["final_url"], "https://allowed.com/dir/next.html")


class TestNormalizationAndHeuristic(unittest.TestCase):
    def test_www_normalized_both_sides(self):
        self.assertEqual(ap.norm_host("WWW.Vendor.com."), "vendor.com")
        al = ap.load_allowlist("vendor.com")
        self.assertIn(ap.norm_host("www.vendor.com"), al)

    def test_regex_error_does_not_crash(self):
        self.assertFalse(ap.discriminator_present(
            {"match_type": "regex", "value": "("},
            {"ok": True, "body": "x", "headers": {}}))


if __name__ == "__main__":
    unittest.main()
