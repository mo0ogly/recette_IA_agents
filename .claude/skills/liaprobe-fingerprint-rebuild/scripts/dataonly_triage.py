#!/usr/bin/env python3
# dataonly_triage.py
#
# A136 -- READ-ONLY triage of data/fingerprints/web-signatures/ rules
# that have NO patterns/web-signatures/ counterpart (the loader serves
# patterns/ only, so these corrected rules are NEVER loaded). Writes
# nothing to patterns/ or data/. Classifies each into a disposition
# bucket and records provenance (capture_url / source) so the
# canonical-source policy can be applied per class.
#
# Buckets:
#   bannereval_gateable : loader-valid, banner-evaluable, content-bearing
#                         -- the post-A137b first-promotion candidates
#   bannereval_exists   : loader-valid, banner-evaluable, presence-only
#                         -- A137b-corpus required (vacuous on banners)
#   body_js             : loader-valid, body/script_src/js target
#                         -- A137b-corpus required (structural)
#   data_not_ok         : data/ rule itself loader-invalid
#                         -- re-authoring needed (hand-off, not promote)
#   parse_err           : unreadable JSON
#
# Usage: python3 dataonly_triage.py [--manifest PATH]

import argparse
import collections
import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path

LIAPROBE = Path("/opt/lia-sec/liaprobe")
PATTERNS = LIAPROBE / "patterns/web-signatures"
DATA = LIAPROBE / "data/fingerprints/web-signatures"
TRACK = Path("/opt/lia-sec/dev/_alire/tracking/liaprobe-fingerprint-rebuild")

_s = importlib.util.spec_from_file_location(
    "ps", Path(__file__).parent / "promoter_select.py")
ps = importlib.util.module_from_spec(_s)
_s.loader.exec_module(ps)


def provenance_class(rule: dict) -> str:
    """STRONG = a fetched-evidence anchor (capture_url + html_sha) ->
    promotion-ready once corpus P exists. WEAK = a vendor `website` /
    `source.file` origin pointer -> needs a LIVE capture to upgrade to
    STRONG. NONE = nothing. (A136 critique CRITICAL: the prior
    has_provenance missed `website` which is present on 100% of the
    2384, falsely reporting all as no-provenance.)"""
    def nz(v):
        return v.strip() if isinstance(v, str) else bool(v)
    if nz(rule.get("capture_url")) or nz(rule.get("html_sha256")):
        return "strong"
    src = rule.get("source")
    if isinstance(src, dict) and (nz(src.get("url"))
                                  or nz(src.get("origin"))):
        return "strong"
    if nz(rule.get("source_url")):
        return "strong"
    if nz(rule.get("website")):
        return "weak"
    if isinstance(src, dict) and (nz(src.get("file"))
                                  or nz(src.get("original_name"))):
        return "weak"
    if isinstance(rule.get("research"), list) and rule["research"]:
        return "weak"
    return "none"


def classify(rule: dict) -> str:
    ok, _ = ps.data_ok(rule)
    if not ok:
        return "data_not_ok"
    d_eff = ps.effective_targets(rule)
    be = [m for m in ps.effective_matchers(rule)
          if m.get("target") in ps.BANNER_EVALUABLE]
    be_content = any(m.get("match_type") in ps.CONTENT_MATCH for m in be)
    if not (d_eff <= ps.BANNER_EVALUABLE):
        # critique HIGH: a rule mixing a banner-evaluable matcher AND a
        # body/js one is split-gateable on its banner dimension -- not
        # the same as a pure body_js rule.
        if be:
            return ("mixed_partial_gateable" if be_content
                    else "mixed_partial_exists")
        return "body_js"
    return "bannereval_gateable" if be_content else "bannereval_exists"


def main() -> int:
    ap = argparse.ArgumentParser()
    run_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    ap.add_argument("--manifest",
                    default=str(TRACK / f"DATAONLY_TRIAGE_{run_date}.json"))
    a = ap.parse_args()

    pat = {p.name for p in PATTERNS.glob("*.json")}
    dat = {p.name for p in DATA.glob("*.json")}
    only = sorted(dat - pat)

    counts = collections.Counter()
    prov = collections.Counter()
    entries = {}
    for fn in only:
        r, e = ps.load(DATA / fn)
        if e or not isinstance(r, dict):
            counts["parse_err"] += 1
            entries[fn] = {"bucket": "parse_err", "provenance": False}
            continue
        b = classify(r)
        pc = provenance_class(r)
        counts[b] += 1
        prov[f"{b}:{pc}"] += 1
        entries[fn] = {"bucket": b, "provenance": pc,
                       "targets": sorted(ps.effective_targets(r))}

    manifest = {
        "schema": "lia-dataonly-triage-v1",
        "run_date": run_date,
        "policy": "DATAONLY_CANONICAL_SOURCE_POLICY_2026-05-15.md",
        "note": "READ-ONLY. data/ has corrected web-sig rules with NO "
                "patterns/ counterpart -> never loaded. Promotion of "
                "ANY bucket is gated-to-zero until A137b delivers a "
                "per-rule live/body corpus (A135b-EXEC-RUN proved the "
                "banner corpus does not exercise web-sig recovery, "
                "incl. bannereval_gateable). data_not_ok = re-author "
                "hand-off, never auto-promote.",
        "patterns_count": len(pat),
        "data_count": len(dat),
        "data_only": len(only),
        "summary": dict(counts),
        "provenance_split": dict(prov),
        "entries": entries,
    }
    Path(a.manifest).write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    print(f"data_only={len(only)}")
    for k, v in counts.most_common():
        print(f"  {v:5d} {k}")
    print("provenance split:")
    for k, v in sorted(prov.items()):
        print(f"  {v:5d} {k}")
    print(f"manifest: {a.manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
