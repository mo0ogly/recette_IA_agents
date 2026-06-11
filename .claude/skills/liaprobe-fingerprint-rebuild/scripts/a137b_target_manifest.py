#!/usr/bin/env python3
# a137b_target_manifest.py
#
# A137b (safe portion) -- READ-ONLY. Builds the per-rule live-probe
# TARGET manifest for the web-sig recovery surface, from the `website`
# field already present in every data/ rule (R18: 5164/5164). Writes
# NOTHING to patterns/ or data/. The manifest feeds a137b_probe.py
# (which is itself host-allowlist gated); this generator never touches
# the network.
#
# Candidate set = the recovery surface needing live validation:
#   - data-only rules (A136 triage: every bucket EXCEPT data_not_ok)
#   - patterns-broken / data-OK pairs (A135b promoter_select)
# Each entry: rule_file, host, website_url, source_tree, tier,
#             discriminator {target, match_type, value}.
#
# Usage: python3 a137b_target_manifest.py [--manifest PATH]

import argparse
import collections
import importlib.util
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

LIAPROBE = Path("/opt/lia-sec/liaprobe")
PAT = LIAPROBE / "patterns/web-signatures"
DAT = LIAPROBE / "data/fingerprints/web-signatures"
TRACK = Path("/opt/lia-sec/dev/_alire/tracking/liaprobe-fingerprint-rebuild")
_HERE = Path(__file__).parent


def _load_mod(name):
    s = importlib.util.spec_from_file_location(name, _HERE / f"{name}.py")
    m = importlib.util.module_from_spec(s)
    s.loader.exec_module(m)
    return m


ps = _load_mod("promoter_select")
dt = _load_mod("dataonly_triage")


def discriminator(rule: dict) -> dict:
    for m in ps.effective_matchers(rule):
        return {"target": m.get("target", ""),
                "match_type": m.get("match_type", ""),
                "value": (m.get("value", "") or "")[:200],
                "field": m.get("field", "")}
    return {"target": "", "match_type": "", "value": "", "field": ""}


def host_of(url: str) -> str:
    try:
        h = urlparse(url if "://" in url else "http://" + url).hostname
        return (h or "").lower()
    except ValueError:
        return ""


def main() -> int:
    ap = argparse.ArgumentParser()
    run_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    ap.add_argument("--manifest",
                    default=str(TRACK / f"A137B_TARGET_MANIFEST_{run_date}.json"))
    a = ap.parse_args()

    pat = {p.name for p in PAT.glob("*.json")}
    dat = {p.name for p in DAT.glob("*.json")}
    entries = {}
    hosts = collections.Counter()
    buckets = collections.Counter()

    # 1. data-only recovery candidates (A136 buckets minus data_not_ok)
    for fn in sorted(dat - pat):
        r, e = ps.load(DAT / fn)
        if e or not isinstance(r, dict):
            continue
        b = dt.classify(r)
        if b in ("data_not_ok",):
            continue
        site = (r.get("website") or "").strip()
        h = host_of(site)
        if not site or not h:
            buckets["dataonly_no_website"] += 1
            continue
        entries[f"data:{fn}"] = {
            "rule_file": f"data/fingerprints/web-signatures/{fn}",
            "source_tree": "data_only", "tier": b,
            "website": site, "host": h,
            "discriminator": discriminator(r)}
        hosts[h] += 1
        buckets[f"dataonly:{b}"] += 1

    # 2. patterns-broken / data-OK promoter pairs (A135b surface)
    for fn in sorted(pat & dat):
        P, pe = ps.load(PAT / fn)
        D, de = ps.load(DAT / fn)
        if pe or de or not isinstance(P, dict) or not isinstance(D, dict):
            continue
        if not ps.patterns_broken(P):
            continue
        ok, _ = ps.data_ok(D)
        if not ok:
            continue
        site = (D.get("website") or "").strip()
        h = host_of(site)
        if not site or not h:
            buckets["pair_no_website"] += 1
            continue
        d_eff = ps.effective_targets(D)
        tier = ("tier_h" if d_eff <= ps.BANNER_EVALUABLE else "tier_b")
        entries[f"pair:{fn}"] = {
            "rule_file": f"patterns/web-signatures/{fn}",
            "data_file": f"data/fingerprints/web-signatures/{fn}",
            "source_tree": "broken_pair", "tier": tier,
            "website": site, "host": h,
            "discriminator": discriminator(D)}
        hosts[h] += 1
        buckets[f"pair:{tier}"] += 1

    manifest = {
        "schema": "lia-a137b-target-manifest-v1",
        "run_date": run_date,
        "note": "READ-ONLY. Live validation targets from existing "
                "rule `website` fields. Consumed by a137b_probe.py "
                "(host-allowlist gated). `website` proves LIVENESS "
                "(WEAK->STRONG provenance); rule-firing only "
                "opportunistically (vendor homepage may not self-embed "
                "-- documented recall residual, A136 section 7). The "
                "live run is a SEPARATE explicitly-authorized "
                "--live --allow-hosts step (R14).",
        "total_targets": len(entries),
        "distinct_hosts": len(hosts),
        "buckets": dict(buckets),
        "top_hosts": dict(hosts.most_common(20)),
        "entries": entries,
    }
    Path(a.manifest).write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    print(f"targets={len(entries)} distinct_hosts={len(hosts)}")
    for k, v in sorted(buckets.items()):
        print(f"  {v:5d} {k}")
    print(f"manifest: {a.manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
