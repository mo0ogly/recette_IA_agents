#!/usr/bin/env python3
"""audit_rule -- consolidated quality audit for a LiaProbe fingerprint rule.

Consolidates seven dimensions that were previously scattered across
lia-rule-validate (schema), the enrich skill (CPE/enrichment) and the
fingerprint-rebuild skill (provenance/legal, matcher signal preference):

  D1 SCHEMA          required fields, parse, schema tag
  D2 ID_COLLISION    generic / corpus-colliding id (engine picks one winner)
  D3 CPE_VALIDITY    no_cpe / :o: host / $1|* placeholder / 2.2 / ok :a:|:h:
  D4 ENRICH_COVERAGE known_cves / lifecycle / attack_surface / _meta presence
  D5 PROVENANCE_LEGAL clean-room block, third-party refs, capture_url, provenance
  D6 MATCHER_SANITY  >=1 matcher, primary-signal class (header/cookie/path > body)
  D7 LIFECYCLE_STATE enabled flag, disabled-low-precision audit markers

Output: a per-rule findings list (severity CRITICAL/HIGH/MEDIUM/LOW/INFO) plus
a 0-100 score and a letter grade. Read-only -- never mutates the rule.

Usage:
  audit_rule.py <rule.json> [--corpus-root /opt/lia-sec/liaprobe/patterns] [--json]
  audit_rule.py --tier /opt/lia-sec/liaprobe/patterns/tcp-probes [--json]   (aggregate)

Severity weights (subtracted from 100): CRITICAL 40, HIGH 20, MEDIUM 8, LOW 3,
INFO 0. Grade: A>=90 B>=75 C>=60 D>=40 F<40.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
from functools import lru_cache

SEVERITY_WEIGHT = {"CRITICAL": 40, "HIGH": 20, "MEDIUM": 8, "LOW": 3, "INFO": 0}
GENERIC_IDS = {
    "unknown", "cisco", "microsoft", "hp", "python", "dlink", "ibm", "sun",
    "apple", "google", "amazon", "oracle", "linux", "apache", "nginx",
}
# Matcher targets that prove self-host (strong) vs marketing-content (weak).
STRONG_TARGETS = {"banner", "response", "header", "headers", "cookie", "cookies", "server"}


def _finding(dim, severity, code, message):
    return {"dimension": dim, "severity": severity, "code": code, "message": message}


def _cpe_part(cpe: str):
    if not cpe:
        return None
    if cpe.startswith("cpe:2.3:"):
        p = cpe.split(":")
        return p[2] if len(p) >= 3 and p[2] in ("a", "o", "h") else None
    if cpe.startswith("cpe:/"):
        tail = cpe[len("cpe:/"):]
        if tail[:2] in ("o:", "a:", "h:"):
            return tail[0]
    return None


def _cpe_product(cpe: str):
    if cpe.startswith("cpe:2.3:"):
        p = cpe.split(":")
        return p[4] if len(p) >= 5 else ""
    return ""


@lru_cache(maxsize=4)
def _build_id_index(corpus_root: str) -> dict:
    """Map lowercase id -> list of files, scanning the corpus once (cached)."""
    idx: dict[str, list[str]] = {}
    if not corpus_root or not os.path.isdir(corpus_root):
        return idx
    for p in glob.glob(os.path.join(corpus_root, "**", "*.json"), recursive=True):
        if "/archive/" in p or "/captures/" in p or "/todo/" in p:
            continue
        try:
            with open(p) as fh:
                rid = (json.load(fh).get("id") or "").lower()
        except (OSError, json.JSONDecodeError):
            continue
        if rid:
            idx.setdefault(rid, []).append(p)
    return idx


def audit_rule(rule_path: str, corpus_root: str | None = None) -> dict:
    findings: list[dict] = []
    out = {"rule": rule_path, "id": None, "product": None,
           "findings": findings, "score": 100, "grade": "A"}

    # D1 SCHEMA -- parse + required fields
    try:
        with open(rule_path) as fh:
            r = json.load(fh)
    except OSError as e:
        findings.append(_finding("D1_SCHEMA", "CRITICAL", "unreadable", f"cannot read: {e}"))
        return _finalize(out)
    except json.JSONDecodeError as e:
        findings.append(_finding("D1_SCHEMA", "CRITICAL", "invalid_json", f"JSON parse failed: {e}"))
        return _finalize(out)

    out["id"] = r.get("id")
    out["product"] = r.get("product") or r.get("taxonomy_name")
    schema = r.get("$schema", "")
    if not schema.startswith("lia-fingerprint"):
        findings.append(_finding("D1_SCHEMA", "MEDIUM", "schema_tag",
                                 f"$schema is {schema!r}, expected lia-fingerprint*"))
    if not r.get("id"):
        findings.append(_finding("D1_SCHEMA", "CRITICAL", "missing_id",
                                 "required field 'id' absent or empty"))
    # product identity: top-level `product` OR the service-detector `taxonomy_name`.
    # service-detectors legitimately carry taxonomy_name instead of product.
    if not (r.get("product") or r.get("taxonomy_name")):
        findings.append(_finding("D1_SCHEMA", "CRITICAL", "missing_product",
                                 "no 'product' nor 'taxonomy_name' -> rule has no product identity"))

    # D2 ID_COLLISION
    rid = (r.get("id") or "").lower()
    if rid in GENERIC_IDS:
        findings.append(_finding("D2_ID_COLLISION", "HIGH", "generic_id",
                                 f"id {rid!r} is vendor-only/generic -> always collides, TP=0 risk"))
    if corpus_root and rid:
        idx = _build_id_index(corpus_root)
        siblings = [p for p in idx.get(rid, []) if os.path.abspath(p) != os.path.abspath(rule_path)]
        if siblings:
            findings.append(_finding("D2_ID_COLLISION", "HIGH", "id_collision",
                                     f"id {rid!r} shared by {len(siblings)} other rule(s) -> "
                                     f"engine picks one winner, this may score TP=0"))

    # D3 CPE_VALIDITY
    cpe = r.get("cpe23_template") or ""
    if not cpe:
        findings.append(_finding("D3_CPE_VALIDITY", "MEDIUM", "no_cpe",
                                 "no cpe23_template -> no CVE enrichment possible"))
    else:
        part = _cpe_part(cpe)
        prod = _cpe_product(cpe)
        if part == "o":
            findings.append(_finding("D3_CPE_VALIDITY", "HIGH", "cpe_part_os",
                                     f"CPE part :o: (OS host) {cpe!r} -> product misattribution, "
                                     "no product-level CVE; needs correction"))
        elif part is None:
            findings.append(_finding("D3_CPE_VALIDITY", "MEDIUM", "cpe_unparseable",
                                     f"CPE {cpe!r} not a recognizable a/o/h part"))
        elif "$" in prod or prod in ("*", "-", ""):
            findings.append(_finding("D3_CPE_VALIDITY", "HIGH", "cpe_placeholder",
                                     f"CPE product slot {prod!r} is a backref/wildcard; engine "
                                     "substitutes {version} only, so CPE never resolves for CVE"))

    # D4 ENRICH_COVERAGE
    has_cve = bool(r.get("known_cves"))
    meta = r.get("_meta_enrichment") or {}
    has_life = bool(r.get("lifecycle"))
    has_attack = bool(r.get("attack_surface"))
    if not has_cve and not meta and not has_life and not has_attack:
        findings.append(_finding("D4_ENRICH_COVERAGE", "LOW", "no_enrichment",
                                 "no known_cves / lifecycle / attack_surface / _meta_enrichment"))
    elif _cpe_part(cpe) in ("a", "h") and not has_cve and "cycle_4_cve" not in meta:
        findings.append(_finding("D4_ENRICH_COVERAGE", "LOW", "cve_not_attempted",
                                 "usable :a:/:h: CPE but cycle_4 CVE enrichment never ran"))

    # D5 PROVENANCE_LEGAL (clean-room derivative-risk)
    lia = r.get("_lia_independent_authoring")
    if lia is None:
        findings.append(_finding("D5_PROVENANCE_LEGAL", "MEDIUM", "no_authoring_block",
                                 "no _lia_independent_authoring block -> derivative-risk unproven"))
    else:
        refs = lia.get("third_party_catalog_references_consulted")
        if refs not in (None, "NONE"):
            findings.append(_finding("D5_PROVENANCE_LEGAL", "HIGH", "third_party_refs",
                                     f"third_party_catalog_references_consulted={refs!r} (must be NONE)"))
    art = r.get("artifacts") or {}
    if art.get("html_sha256") and not art.get("capture_url"):
        findings.append(_finding("D5_PROVENANCE_LEGAL", "MEDIUM", "no_capture_url",
                                 "html_sha256 present but capture_url missing -> unverifiable provenance"))
    if art.get("observation_provenance") == "vendor_marketing_site":
        findings.append(_finding("D5_PROVENANCE_LEGAL", "HIGH", "marketing_site_provenance",
                                 "observation_provenance=vendor_marketing_site -> volatile signal, forbidden"))

    # D6 MATCHER_SANITY
    matcher_blocks = []
    for key in ("banner_matchers", "service_matchers", "matchers"):
        v = r.get(key)
        if isinstance(v, list):
            matcher_blocks.extend(v)
    for probe in (r.get("probes") or []):
        if isinstance(probe, dict):
            matcher_blocks.extend(probe.get("matchers") or [])
    if not matcher_blocks:
        findings.append(_finding("D6_MATCHER_SANITY", "CRITICAL", "no_matchers",
                                 "rule has zero matchers -> detects nothing"))
    else:
        targets = {str(m.get("target", "")).lower() for m in matcher_blocks if isinstance(m, dict)}
        if targets and not (targets & STRONG_TARGETS):
            findings.append(_finding("D6_MATCHER_SANITY", "LOW", "weak_signal_only",
                                     f"matchers target only {sorted(targets)} (body/marketing); "
                                     "prefer header/cookie/banner for self-host proof"))

    # D7 LIFECYCLE_STATE
    if r.get("enabled") is False:
        reason = ""
        for blk in (meta, lia or {}):
            for k, v in (blk.items() if isinstance(blk, dict) else []):
                if "disable" in k.lower():
                    reason = k
        findings.append(_finding("D7_LIFECYCLE_STATE", "INFO", "disabled",
                                 f"rule disabled{(' (' + reason + ')') if reason else ''}"))

    return _finalize(out)


def _finalize(out: dict) -> dict:
    score = 100
    for f in out["findings"]:
        score -= SEVERITY_WEIGHT.get(f["severity"], 0)
    score = max(0, score)
    out["score"] = score
    out["grade"] = ("A" if score >= 90 else "B" if score >= 75 else
                    "C" if score >= 60 else "D" if score >= 40 else "F")
    return out


def audit_tier(tier_dir: str) -> dict:
    files = sorted(p for p in glob.glob(os.path.join(tier_dir, "*.json")) if os.path.isfile(p))
    results = [audit_rule(f, corpus_root=os.path.dirname(tier_dir)) for f in files]
    from collections import Counter
    sev = Counter()
    grade = Counter()
    for res in results:
        grade[res["grade"]] += 1
        for fnd in res["findings"]:
            sev[fnd["severity"]] += 1
    return {
        "tier": tier_dir, "rules": len(results),
        "avg_score": round(sum(r["score"] for r in results) / len(results), 1) if results else 0,
        "by_grade": dict(grade), "by_severity": dict(sev),
        "worst": sorted(results, key=lambda r: r["score"])[:15],
    }


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="audit_rule",
                                description="Consolidated quality audit of a LiaProbe fingerprint rule.")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("rule", nargs="?", help="Path to a single rule.json")
    g.add_argument("--tier", help="Audit all *.json in a tier dir (aggregate report)")
    p.add_argument("--corpus-root", default=None,
                   help="patterns/ root for id-collision check (single-rule mode)")
    p.add_argument("--json", action="store_true", help="Emit JSON")
    args = p.parse_args(argv)

    if args.tier:
        res = audit_tier(args.tier)
        if args.json:
            print(json.dumps(res, indent=2))
        else:
            print(f"tier {res['tier']}  rules={res['rules']}  avg_score={res['avg_score']}")
            print("  grades:", res["by_grade"])
            print("  severities:", res["by_severity"])
            print("  worst:")
            for w in res["worst"]:
                print(f"    {w['score']:3} {w['grade']} {os.path.basename(w['rule'])} "
                      f"({len(w['findings'])} findings)")
        return 0

    res = audit_rule(args.rule, corpus_root=args.corpus_root)
    if args.json:
        print(json.dumps(res, indent=2))
    else:
        print(f"{res['rule']}  score={res['score']} grade={res['grade']}")
        for f in res["findings"]:
            print(f"  [{f['severity']:8}] {f['dimension']:18} {f['code']}: {f['message']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
