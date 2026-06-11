"""Tests for version_extract sanitization in match_runner.

Guards against the broken-regex class found 2026-05-31: a greedy version_extract
(^(.+)$ etc.) on target=body captured the whole HTML body as a "version".
Detection must still hold; the bogus version must be discarded.

Run: python3 .claude/skills/nightly-fingerprint-harvest/scripts/lib/test_match_runner_version.py
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

_MR = Path(__file__).with_name("match_runner.py")
_spec = importlib.util.spec_from_file_location("match_runner", _MR)
mr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mr)


def test_plausible_version_accepts_real_versions():
    for v in ("9.0.71", "1.24", "v3.2.1", "2.0-beta", "10.5.3+build1", "1"):
        assert mr._is_plausible_version(v), v


def test_plausible_version_rejects_garbage():
    for v in ("", "<!DOCTYPE html><html>x</html>", "a long sentence here xxxxx",
              "ok\nok", "abc", "nginx server"):
        assert not mr._is_plausible_version(v), v


def test_greedy_body_regex_detects_but_yields_no_version():
    rule = {"id": "x", "probes": [{"id": "p", "matchers": [
        {"target": "body", "match_type": "regex", "value": "Server",
         "version_extract": "^(.+)$", "confidence_delta": 0.5}]}]}
    r = mr.run_match(rule, b"Server: x\n<html>huge</html>", {}, None)
    assert r["any_probe_matched"] is True
    v = next((m.get("version_extract") for m in r["matched_matchers"]
              if m.get("version_extract")), None)
    assert v is None


def test_good_regex_still_extracts_version():
    rule = {"id": "y", "probes": [{"id": "p", "matchers": [
        {"target": "body", "match_type": "regex",
         "value": '"Version":"([0-9.]+)"',
         "version_extract": '"Version":"([0-9.]+)"', "confidence_delta": 0.6}]}]}
    r = mr.run_match(rule, b'{"Version":"9.0.71"}', {}, None)
    v = next((m.get("version_extract") for m in r["matched_matchers"]
              if m.get("version_extract")), None)
    assert v == "9.0.71"


if __name__ == "__main__":
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS {name}")
            except AssertionError as exc:
                print(f"FAIL {name}: {exc}")
                fails += 1
    raise SystemExit(1 if fails else 0)
