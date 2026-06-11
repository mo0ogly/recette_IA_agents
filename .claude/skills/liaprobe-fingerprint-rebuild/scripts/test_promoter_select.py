#!/usr/bin/env python3
# test_promoter_select.py -- unit tests for the A135b read-only selection
# predicate core (no filesystem, no patterns/ access).

import importlib.util
import sys
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "promoter_select",
    Path(__file__).parent / "promoter_select.py")
ps = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ps)


def ok_data(**kw):
    base = {
        "$schema": "lia-fingerprint-v2-independent",
        "id": "x", "taxonomy_code": "X", "taxonomy_name": "X",
        "enabled": True, "confidence_threshold": 0.5,
        "banner_matchers": [{"target": "header", "field": "Server",
                             "match_type": "regex", "value": "nginx"}],
    }
    base.update(kw)
    return base


def run():
    f = 0

    # patterns_broken: header matcher missing field -> broken
    if not ps.patterns_broken({"banner_matchers": [
            {"target": "header", "match_type": "regex", "value": "x"}]}):
        print("FAIL: header-no-field must be broken"); f += 1
    # patterns_broken: zero matchers -> broken
    if not ps.patterns_broken({}):
        print("FAIL: zero matchers must be broken"); f += 1
    # patterns_broken: body matcher (no field needed) -> NOT broken
    if ps.patterns_broken({"banner_matchers": [
            {"target": "body", "match_type": "regex", "value": "x"}]}):
        print("FAIL: valid body matcher must not be broken"); f += 1
    # patterns_broken: only unsupported 'meta' target -> broken
    if not ps.patterns_broken({"banner_matchers": [
            {"target": "meta", "match_type": "regex", "value": "x"}]}):
        print("FAIL: meta-only must be broken (unsupported target)"); f += 1

    # data_ok: well-formed header+field -> ok
    good, why = ps.data_ok(ok_data())
    if not good:
        print(f"FAIL: ok_data rejected ({why})"); f += 1
    # data_ok: header matcher missing field -> not ok
    bad, _ = ps.data_ok(ok_data(banner_matchers=[
        {"target": "header", "match_type": "regex", "value": "x"}]))
    if bad:
        print("FAIL: data header-no-field must be rejected"); f += 1
    # data_ok: bad schema -> not ok
    bad, _ = ps.data_ok(ok_data(**{"$schema": "other"}))
    if bad:
        print("FAIL: bad schema must be rejected"); f += 1
    # data_ok: enabled false -> not ok
    bad, _ = ps.data_ok(ok_data(enabled=False))
    if bad:
        print("FAIL: enabled=false must be rejected"); f += 1
    # data_ok: only unsupported target -> not ok (no effective matcher)
    bad, _ = ps.data_ok(ok_data(banner_matchers=[
        {"target": "meta", "match_type": "regex", "value": "x"}]))
    if bad:
        print("FAIL: meta-only data must be rejected"); f += 1

    # effective_targets / Tier classification
    eff = ps.effective_targets(ok_data())
    if eff != {"header"}:
        print(f"FAIL: effective_targets {eff} != {{header}}"); f += 1
    if not (eff <= ps.BANNER_EVALUABLE):
        print("FAIL: header must be banner-evaluable (Tier H)"); f += 1
    sc = ps.effective_targets(ok_data(banner_matchers=[
        {"target": "script_src", "match_type": "regex", "value": "x"}]))
    if sc <= ps.BANNER_EVALUABLE:
        print("FAIL: script_src must NOT be banner-evaluable (Tier B)")
        f += 1

    # HIGH-a: presence-only vs content-bearing classification
    if "exists" not in ps.PRESENCE_MATCH:
        print("FAIL: exists must be PRESENCE_MATCH"); f += 1
    if "regex" not in ps.CONTENT_MATCH:
        print("FAIL: regex must be CONTENT_MATCH"); f += 1
    # HIGH-b: RE2-incompat heuristic catches lookaround / backref
    for bad in (r"(?=foo)", r"(?!foo)", r"(?<=x)", r"(?>x)", r"a\1b",
                r"\k<n>"):
        if not ps.RE2_INCOMPAT.search(bad):
            print(f"FAIL: RE2_INCOMPAT missed {bad!r}"); f += 1
    for good in (r"^nginx/[0-9.]+$", r"(?:abc)+", r"Server: .*"):
        if ps.RE2_INCOMPAT.search(good):
            print(f"FAIL: RE2_INCOMPAT false-positive {good!r}"); f += 1

    print(f"\n{'OK' if f == 0 else 'FAIL'}: {f} failures")
    return 1 if f else 0


if __name__ == "__main__":
    sys.exit(run())
