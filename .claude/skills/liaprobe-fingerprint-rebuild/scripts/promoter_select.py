#!/usr/bin/env python3
# promoter_select.py
#
# A135b-EXEC -- READ-ONLY selection + Tier partition for the staged
# data/ -> patterns/ web-signature promoter (SPEC_PROMOTER_A135b_2026-05-15.md).
#
# This script WRITES NOTHING to patterns/ or data/. It evaluates the spec
# selection predicate (P1..P4) per filename present in BOTH trees, partitions
# the auto-promotable set by promoted-rule target into:
#
#   tier_h  : every effective matcher target is banner-evaluable
#             (the onyphe corpus is banner-only, so the spec §5 PRIMARY
#              FP-ceiling gate is COMPUTABLE + MEANINGFUL for these)
#   tier_b  : >=1 effective matcher needs an HTTP body / JS / favicon
#             (PRIMARY gate is VACUOUS on a body-less banner corpus ->
#              BLOCKED pending a body corpus, spec §7/§8 deferred)
#
# plus manual_review (signal-loss / collision) and excluded (data not OK).
#
# Output: a PROMOTER_MANIFEST.json report under the tracking dir, and a
# summary table on stdout. Spec §6(b) dry-run is inherently read-only.
#
# Usage:
#   python3 promoter_select.py                 # report only (default)
#   python3 promoter_select.py --manifest PATH # custom manifest path

import argparse
import collections
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

LIAPROBE = Path("/opt/lia-sec/liaprobe")
PATTERNS_DIR = LIAPROBE / "patterns/web-signatures"
DATA_DIR = LIAPROBE / "data/fingerprints/web-signatures"
TRACKING_DIR = Path(
    "/opt/lia-sec/dev/_alire/tracking/liaprobe-fingerprint-rebuild"
)

# matcher.go switch vocabulary (R18, grep-confirmed 2026-05-15). Any target
# NOT in this set hits the default branch in matcher.go and never fires.
KNOWN_TARGETS = {
    "banner", "body", "header", "cookie", "status_code", "favicon_hash",
    "json_field", "title", "url", "attr", "script_src", "js_global",
}
# matcher.go short-circuits these targets to "no match" when field == ""
# (R18, grep-confirmed 2026-05-15).
FIELD_REQUIRED = {
    "header", "cookie", "json_field", "ssdp_header", "mdns_txt",
    "attr", "js_global",
}
# Targets that can be evaluated against a banner = HTTP response HEAD
# (status line + headers). The onyphe corpora carry only this, no body.
BANNER_EVALUABLE = {"banner", "header", "cookie", "status_code"}
SCHEMA_ALLOWLIST = {"lia-fingerprint-v1", "lia-fingerprint-v2-independent"}
# Content-bearing match types: a wrong rule CAN be falsified by the
# corpus (the FP-ceiling gate is meaningful). Includes the A128 synonyms.
CONTENT_MATCH = {"regex", "contains", "literal", "string",
                 "exact", "equals", "eq"}
# Presence-only: the banner corpus cannot falsify these (any host that
# carries the header/cookie matches) -> PRIMARY gate is VACUOUS for them
# (A135b-EXEC critique HIGH-a). Such Tier-H rules are behaviorally Tier B.
PRESENCE_MATCH = {"exists"}
# Conservative Go-RE2 incompatibility heuristic (NOT a true RE2 oracle --
# A135b-EXEC critique HIGH-b ; a real go-side regexp.Compile V3 gate must
# be built before any apply). Flags lookaround / backref / atomic group.
import re as _re  # noqa: E402
RE2_INCOMPAT = _re.compile(r"\(\?[=!]|\(\?<[=!]|\(\?>|\\[1-9]|\\k<")


def all_matchers(rule: dict) -> list:
    """Collect every matcher (banner + service + probe matchers)."""
    ms = list(rule.get("banner_matchers", []) or [])
    ms += list(rule.get("service_matchers", []) or [])
    for pr in rule.get("probes", []) or []:
        ms += list(pr.get("matchers", []) or [])
    return [m for m in ms if isinstance(m, dict)]


def is_effective(m: dict) -> bool:
    """A matcher fires only if its target is supported by matcher.go and,
    when the target is field-required, a non-empty `field` is present."""
    t = m.get("target", "")
    if t not in KNOWN_TARGETS:
        return False
    if t in FIELD_REQUIRED and not (m.get("field") or "").strip():
        return False
    return True


def effective_matchers(rule: dict) -> list:
    return [m for m in all_matchers(rule) if is_effective(m)]


def effective_targets(rule: dict) -> set:
    return {m.get("target", "") for m in effective_matchers(rule)}


def patterns_broken(rule: dict) -> bool:
    """P1: the patterns/ rule loads but no matcher can ever fire."""
    ms = all_matchers(rule)
    if not ms:
        return True
    return not any(is_effective(m) for m in ms)


def data_ok(rule: dict) -> tuple[bool, str]:
    """P2: the data/ rule is loader-valid AND every field-required-target
    matcher carries a non-empty field AND >=1 effective matcher."""
    if rule.get("$schema") not in SCHEMA_ALLOWLIST:
        return False, f"schema={rule.get('$schema')!r}"
    for k in ("id", "taxonomy_code", "taxonomy_name"):
        v = rule.get(k)
        if not isinstance(v, str) or not v.strip():
            return False, f"missing {k}"
    if rule.get("enabled") is not True:
        return False, "enabled!=true"
    ct = rule.get("confidence_threshold", 0)
    if not (isinstance(ct, (int, float)) and 0 < ct <= 1.0):
        return False, f"confidence_threshold={ct}"
    ms = all_matchers(rule)
    if not ms:
        return False, "no matchers"
    for i, m in enumerate(ms):
        if not (m.get("target") or "").strip():
            return False, f"matcher[{i}] empty target"
        if not (m.get("match_type") or "").strip():
            return False, f"matcher[{i}] empty match_type"
    # every field-required-target matcher must carry a field
    for i, m in enumerate(ms):
        if m.get("target") in FIELD_REQUIRED and \
                not (m.get("field") or "").strip():
            return False, f"matcher[{i}] {m.get('target')} missing field"
    if not any(is_effective(m) for m in ms):
        return False, "no effective matcher (all targets unsupported)"
    return True, "ok"


def load(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8")), None
    except (json.JSONDecodeError, OSError) as e:
        return None, str(e)


def build_collision_index() -> tuple[dict, dict]:
    """taxonomy_code -> {fn}, product -> {fn} over the WHOLE patterns tree
    (web-signatures). Conservative P4 proxy; per-file post-2026-05-02 git
    date refinement is a documented deferred residual (spec, R26)."""
    tax, prod = collections.defaultdict(set), collections.defaultdict(set)
    for p in PATTERNS_DIR.glob("*.json"):
        r, err = load(p)
        if err or not isinstance(r, dict):
            continue
        tc = (r.get("taxonomy_code") or "").strip().lower()
        pr = (r.get("product") or "").strip().lower()
        if tc:
            tax[tc].add(p.name)
        if pr:
            prod[pr].add(p.name)
    return tax, prod


def main() -> int:
    ap = argparse.ArgumentParser(description="A135b read-only promoter "
                                 "selection + Tier partition (no writes)")
    run_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    ap.add_argument("--manifest", default=str(
        TRACKING_DIR / f"PROMOTER_MANIFEST_{run_date}.json"))
    args = ap.parse_args()

    if not PATTERNS_DIR.is_dir() or not DATA_DIR.is_dir():
        print(f"FATAL: tree missing ({PATTERNS_DIR} / {DATA_DIR})",
              file=sys.stderr)
        return 2

    pat_names = {p.name for p in PATTERNS_DIR.glob("*.json")}
    data_names = {p.name for p in DATA_DIR.glob("*.json")}
    both = sorted(pat_names & data_names)

    tax_idx, prod_idx = build_collision_index()
    entries = {}
    counts = collections.Counter()

    for fn in both:
        P, perr = load(PATTERNS_DIR / fn)
        D, derr = load(DATA_DIR / fn)
        if perr or not isinstance(P, dict):
            entries[fn] = {"status": "excluded", "reason": f"patterns parse: {perr}"}
            counts["excluded"] += 1
            continue
        if derr or not isinstance(D, dict):
            entries[fn] = {"status": "excluded", "reason": f"data parse: {derr}"}
            counts["excluded"] += 1
            continue

        if not patterns_broken(P):
            entries[fn] = {"status": "excluded",
                           "reason": "P1 fail: patterns rule not broken "
                                     "(has >=1 effective matcher)"}
            counts["excluded_p1"] += 1
            continue

        ok, why = data_ok(D)
        if not ok:
            entries[fn] = {"status": "excluded",
                           "reason": f"P2 fail: data not OK ({why})"}
            counts["excluded_p2"] += 1
            continue

        # P3 superset: an effective target present in patterns but absent
        # in data = silent signal loss. (P1 guarantees patterns has 0
        # effective targets, so this is a defensive assertion; a non-empty
        # diff means P1 logic and P3 disagree -> route to manual review.)
        p_eff = effective_targets(P)
        d_eff = effective_targets(D)
        if p_eff - d_eff:
            entries[fn] = {"status": "manual_review",
                           "reason": f"P3 signal-loss: patterns effective "
                                     f"targets {sorted(p_eff - d_eff)} "
                                     f"absent in data",
                           "d_targets": sorted(d_eff)}
            counts["manual_review"] += 1
            continue

        # P4 collision proxy: data taxonomy_code/product shared by ANOTHER
        # patterns rule.
        tc = (D.get("taxonomy_code") or "").strip().lower()
        pr = (D.get("product") or "").strip().lower()
        coll = (tax_idx.get(tc, set()) | prod_idx.get(pr, set())) - {fn}
        if coll:
            entries[fn] = {"status": "manual_review",
                           "reason": f"P4 collision proxy: taxonomy/product "
                                     f"shared with {sorted(coll)[:3]}"
                                     f"{'...' if len(coll) > 3 else ''}",
                           "d_targets": sorted(d_eff)}
            counts["manual_review"] += 1
            continue

        d_ms = effective_matchers(D)

        # HIGH-b: conservative Go-RE2 incompat heuristic on any effective
        # matcher value -> manual_review (NOT a true RE2 oracle).
        re2_bad = [m.get("value", "") for m in d_ms
                   if RE2_INCOMPAT.search(m.get("value", "") or "")]
        if re2_bad:
            entries[fn] = {"status": "manual_review",
                           "reason": f"RE2-incompat heuristic hit "
                                     f"(needs real go regexp.Compile V3): "
                                     f"{re2_bad[0][:60]!r}",
                           "d_targets": sorted(d_eff)}
            counts["manual_review_re2"] += 1
            continue

        if not (d_eff <= BANNER_EVALUABLE):
            tier = "tier_b"
        else:
            # HIGH-a: Tier-H is gate-meaningful ONLY if >=1 effective
            # banner-evaluable matcher is content-bearing (corpus can
            # falsify it). All-presence Tier-H = vacuous gate =
            # behaviorally Tier B.
            be = [m for m in d_ms
                  if m.get("target") in BANNER_EVALUABLE]
            if any(m.get("match_type") in CONTENT_MATCH for m in be):
                tier = "tier_h_gateable"
            elif be and all(m.get("match_type") in PRESENCE_MATCH
                            for m in be):
                tier = "tier_h_exists"
            else:
                # unknown/other match types on banner targets: corpus
                # can still exercise them -> treat as gateable.
                tier = "tier_h_gateable"
        entries[fn] = {"status": tier,
                       "reason": "selected",
                       "d_targets": sorted(d_eff),
                       "match_types": sorted({m.get("match_type", "")
                                              for m in d_ms}),
                       "field_required_in_d": sorted(
                           d_eff & FIELD_REQUIRED)}
        counts[tier] += 1

    manifest = {
        "schema": "lia-promoter-manifest-v1",
        "run_date": run_date,
        "spec": "SPEC_PROMOTER_A135b_2026-05-15.md",
        "note": "READ-ONLY selection report; no patterns/ or data/ "
                "mutation. tier_h_gateable = banner-evaluable AND >=1 "
                "content-bearing matcher (spec §5 PRIMARY gate "
                "MEANINGFUL -> TRUE promotable). tier_h_exists = "
                "banner-evaluable but presence-only (gate VACUOUS, "
                "A135b-EXEC HIGH-a -> behaviorally Tier B). tier_b = "
                "body/JS (gate vacuous on banner corpus). "
                "manual_review_re2 = conservative RE2-incompat heuristic "
                "(needs real go regexp.Compile V3 before apply). All "
                "non-gateable buckets BLOCKED pending body corpus / "
                "live-probe (A137b-class).",
        "patterns_count": len(pat_names),
        "data_count": len(data_names),
        "common_filenames": len(both),
        "summary": dict(counts),
        "entries": entries,
    }
    Path(args.manifest).write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")

    print(f"patterns={len(pat_names)} data={len(data_names)} "
          f"common={len(both)}")
    print("--- selection summary ---")
    for k in ("tier_h_gateable", "tier_h_exists", "tier_b",
              "manual_review", "manual_review_re2",
              "excluded_p1", "excluded_p2", "excluded"):
        print(f"  {k:18s}: {counts.get(k, 0)}")
    th = [f for f, e in entries.items()
          if e["status"] == "tier_h_gateable"]
    print(f"\ntier_h_gateable (TRUE promotable -- content-bearing "
          f"banner-evaluable, spec §5 gate meaningful): {len(th)}")
    for f in th[:10]:
        print(f"  {f}  targets={entries[f]['d_targets']}")
    if len(th) > 10:
        print(f"  ... +{len(th) - 10} more")
    print(f"\nManifest: {args.manifest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
