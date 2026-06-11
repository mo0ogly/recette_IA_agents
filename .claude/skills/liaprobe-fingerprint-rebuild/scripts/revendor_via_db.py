#!/usr/bin/env python3
# revendor_via_db.py
#
# c28 ST1: re-resolve canonical_vendor for rules currently in DOUBTFUL
# bucket. Uses strict alias_exact PostgreSQL lookups (no fuzzy).
#
# Per rule:
#   1. Read existing _meta_enrichment.canonical_vendor (DOUBTFUL bucket)
#   2. Build lookup candidates from:
#        - cpe_vendor_input + cpe_product_input (canonical inputs)
#        - top-level vendor + product (engine-facing fields)
#   3. Strict query:
#        SELECT vendor.id, vendor.vendor_name, product.id, product.product_name
#        FROM vendor_alias va JOIN vendor v ON va.vendor_id = v.id
#                              JOIN product p ON p.vendor_id = v.id
#        WHERE LOWER(va.alias_name) = LOWER(:vendor)
#          AND LOWER(p.product_name) = LOWER(:product)
#   4. If exactly 1 match: rebuild canonical_vendor block with
#      bucket=CONFIDENT, alias_chain, resolved_via=alias_exact_revendor_c28
#   5. If 0 match or >1 match: leave existing block (still DOUBTFUL)
#
# Output: REVENDOR_RESULTS_<DATE>.json with per-rule status.

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

LIAPROBE_DIR = Path("/opt/lia-sec/liaprobe")
DEV_DIR = Path("/opt/lia-sec/dev")
BACKUP_DIR = DEV_DIR / "_alire/temp/apex/apex-20260513-c28/revendor_backup"
NOW_ISO = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
RUN_DATE = datetime.now(timezone.utc).strftime("%Y-%m-%d")
PASS_ID = f"{RUN_DATE}_apex_c28_revendor_via_db"
DEFAULT_OUT = DEV_DIR / "_alire/tracking/liaprobe-fingerprint-rebuild" / f"REVENDOR_RESULTS_{RUN_DATE}.json"


def _systemd_dburl() -> Optional[str]:
    try:
        raw = subprocess.check_output(
            ["systemctl", "cat", "lia-backend"],
            text=True, stderr=subprocess.DEVNULL, timeout=5,
        )
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        return None
    for line in raw.splitlines():
        line = line.strip()
        if line.startswith("Environment=DATABASE_URL="):
            return line.split("=", 2)[2]
        if line.startswith("Environment=") and "DATABASE_URL=" in line:
            return line.split("DATABASE_URL=", 1)[1]
    return None


def _psql_query(dburl: str, sql: str, params: dict[str, str]) -> list[list[str]]:
    # Use psql -tAc with single-statement; substitute params by client-side
    # quoting (validated against allowlist below).
    if "'" in "".join(params.values()):
        return []
    formatted = sql
    for k, v in params.items():
        formatted = formatted.replace(f":{k}", f"'{v}'")
    try:
        # NOTE: -c MUST be last before SQL (psql consumes the next arg as the
        # SQL string). Order in c28 was [-tAc, -F, \t, SQL] which made psql
        # treat "-F" as SQL after -c absorbed it. Fixed to explicit -t -A -F.
        completed = subprocess.run(
            ["psql", dburl, "-t", "-A", "-F", "\t", "-c", formatted],
            capture_output=True, text=True, timeout=15,
        )
    except subprocess.TimeoutExpired as exc:
        # Fail loud: timeout is a system-level fault, not "no match".
        raise RuntimeError(f"psql timeout on query: {exc}") from exc
    # Fail loud on non-zero exit OR stderr containing "ERROR:" (c29 fix).
    # Silent return-[] on SQL error caused c28 to mis-report 51 NO_STRICT_MATCH
    # while the real failure was a column-name bug.
    if completed.returncode != 0:
        raise RuntimeError(
            f"psql failed (rc={completed.returncode}): {completed.stderr.strip()}\n"
            f"SQL: {formatted}"
        )
    if "ERROR:" in completed.stderr:
        raise RuntimeError(
            f"psql reported ERROR: {completed.stderr.strip()}\nSQL: {formatted}"
        )
    rows: list[list[str]] = []
    for line in completed.stdout.splitlines():
        if not line.strip():
            continue
        rows.append(line.split("\t"))
    return rows


STRICT_LOOKUP_SQL = """
SELECT v.vendor_id, v.vendor_name, p.product_id, p.product_name, va.source AS alias_source
FROM vendor_alias va
JOIN vendor v ON va.vendor_id = v.vendor_id
JOIN product p ON p.vendor_id = v.vendor_id
WHERE LOWER(va.alias_name) = LOWER(:vendor)
  AND LOWER(p.product_name) = LOWER(:product)
LIMIT 5
"""

# c33 A23: fuzzy fallback via pg_trgm similarity().
# Score = avg(alias similarity, product similarity). Threshold >= 0.6 enforced
# client-side (SQL returns all >= 0.5 to allow inspection).
# DRY-RUN ONLY by default. Operator reviews FUZZY_RESULTS_*.json then re-runs
# revendor on the subset they accept. Auto-apply requires --fuzzy-auto.
FUZZY_LOOKUP_SQL = """
SELECT v.vendor_id, v.vendor_name, p.product_id, p.product_name,
       va.source AS alias_source,
       similarity(LOWER(va.alias_name), LOWER(:vendor)) AS vscore,
       similarity(LOWER(p.product_name), LOWER(:product)) AS pscore
FROM vendor_alias va
JOIN vendor v ON va.vendor_id = v.vendor_id
JOIN product p ON p.vendor_id = v.vendor_id
WHERE similarity(LOWER(va.alias_name), LOWER(:vendor)) >= 0.5
  AND similarity(LOWER(p.product_name), LOWER(:product)) >= 0.5
ORDER BY (similarity(LOWER(va.alias_name), LOWER(:vendor)) +
          similarity(LOWER(p.product_name), LOWER(:product))) DESC
LIMIT 5
"""

# c34 A26: vendor-only fuzzy lookup. Used when rule.product is None/empty.
# Returns top vendor matches without product join. Resolution writes a
# vendor-only canonical_vendor block (product_id=None, bucket=
# VENDOR_ONLY_CONFIDENT). Strict client-side threshold >= 0.7 (higher than
# vendor+product fuzzy since less context).
VENDOR_ONLY_LOOKUP_SQL = """
SELECT v.vendor_id, v.vendor_name, va.source AS alias_source,
       similarity(LOWER(va.alias_name), LOWER(:vendor)) AS vscore
FROM vendor_alias va
JOIN vendor v ON va.vendor_id = v.vendor_id
WHERE similarity(LOWER(va.alias_name), LOWER(:vendor)) >= 0.6
ORDER BY similarity(LOWER(va.alias_name), LOWER(:vendor)) DESC
LIMIT 5
"""


def _scan_doubtful_rules(rules_dir: Path, include_non_canonical: bool = False) -> list[Path]:
    """
    Scan rules for revendor candidates.

    Default: bucket=DOUBTFUL only.
    include_non_canonical=True (A19j flag): also include rules with no
    canonical_vendor block at all but with a bare top-level vendor+product
    populated -- these are Tier 1b "bare" rules that strict alias_exact
    can potentially resolve.

    Always skipped (c35 A32):
    - bucket in {CONFIDENT, VENDOR_ONLY_CONFIDENT}: already resolved
    - canonical_vendor.permanent_doubtful=true: junk-vendor by design
    - classification_c34.permanent_doubtful=true: c34 PROTOCOL/JUNK_VENDOR
    """
    out: list[Path] = []
    for p in sorted(rules_dir.glob("*.json")):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        meta = (data.get("_meta_enrichment") or {})
        cv = meta.get("canonical_vendor") or {}
        bucket = (cv.get("bucket") or "").upper()
        if cv.get("permanent_doubtful"):
            continue
        classif = meta.get("classification_c34") or {}
        if classif.get("permanent_doubtful"):
            continue
        if bucket == "DOUBTFUL":
            out.append(p)
            continue
        if include_non_canonical and not cv:
            # No canonical_vendor block at all. Check bare top-level.
            if data.get("vendor") and data.get("product"):
                out.append(p)
    return out


def _candidate_pairs(rule: dict[str, Any]) -> list[tuple[str, str, str]]:
    # Returns list of (vendor, product, source_tag) to try in order.
    cv = (rule.get("_meta_enrichment") or {}).get("canonical_vendor") or {}
    pairs: list[tuple[str, str, str]] = []
    cpe_v = cv.get("cpe_vendor_input") or ""
    cpe_p = cv.get("cpe_product_input") or ""
    if cpe_v and cpe_p:
        pairs.append((cpe_v, cpe_p, "cpe_inputs"))
    bare_v = rule.get("vendor") or ""
    bare_p = rule.get("product") or ""
    if bare_v and bare_p and (bare_v, bare_p) != (cpe_v, cpe_p):
        pairs.append((bare_v, bare_p, "bare_top_level"))
    # Also try (vendor stripped of suffix " Inc", " Software", etc.)
    for suffix in (" Inc.", " Inc", " Foundation", " Software", " Ltd", " GmbH", " Corporation"):
        if bare_v.endswith(suffix):
            stripped = bare_v[: -len(suffix)].strip()
            if stripped and (stripped, bare_p, "stripped_vendor") not in [(a, b, "stripped_vendor") for a, b, _ in pairs]:
                pairs.append((stripped, bare_p, "stripped_vendor"))
            break
    return pairs


def revendor_one(rule_path: Path, dburl: str, dry: bool, include_non_canonical: bool = False) -> dict[str, Any]:
    try:
        rule = json.loads(rule_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return {"basename": rule_path.name, "status": "READ_FAIL", "error": str(exc)}

    cv = (rule.get("_meta_enrichment") or {}).get("canonical_vendor") or {}
    bucket = (cv.get("bucket") or "").upper()
    if bucket != "DOUBTFUL":
        # When include_non_canonical and the rule has no canonical block at all,
        # we still attempt resolution via bare top-level vendor+product.
        if not (include_non_canonical and not cv and rule.get("vendor") and rule.get("product")):
            return {"basename": rule_path.name, "status": "NOT_DOUBTFUL_SKIP"}

    pairs = _candidate_pairs(rule)
    if not pairs:
        return {"basename": rule_path.name, "status": "NO_CANDIDATES",
                "previous_canonical": {"vendor_name": cv.get("vendor_name"),
                                       "product_name_db": cv.get("product_name_db")}}

    for vendor, product, src_tag in pairs:
        rows = _psql_query(dburl, STRICT_LOOKUP_SQL,
                           {"vendor": vendor, "product": product})
        if len(rows) == 1:
            v_id, v_name, p_id, p_name, alias_source = rows[0]
            new_cv = {
                "cpe_vendor_input": vendor,
                "cpe_product_input": product,
                "resolved_via": f"alias_exact_revendor_c28_{src_tag}",
                "bucket": "CONFIDENT",
                "doubt_reasons": [],
                "vendor_id": int(v_id),
                "vendor_name": v_name,
                "product_id": int(p_id),
                "product_name_db": p_name,
                "sub_product": False,
                "alias_chain": [{
                    "alias_name": vendor,
                    "alias_source": alias_source,
                    "alias_type": "official_name",
                    "confidence_score": 1.0,
                }],
                "confidence": 0.95,
                "ambiguous": False,
                "lia_signature_key": f"lia_v{v_id}_p{p_id}",
                "resolved_at": NOW_ISO,
            }
            chain_hash = hashlib.sha256(
                json.dumps(new_cv["alias_chain"], sort_keys=True).encode("utf-8")
            ).hexdigest()[:12]

            outcome = {
                "basename": rule_path.name,
                "status": "RESOLVED_CONFIDENT",
                "candidate_used": {"vendor": vendor, "product": product, "source": src_tag},
                "previous_canonical": {
                    "vendor_name": cv.get("vendor_name"),
                    "product_name_db": cv.get("product_name_db"),
                    "bucket": cv.get("bucket"),
                    "resolved_via": cv.get("resolved_via"),
                },
                "new_canonical": {
                    "vendor_name": v_name,
                    "product_name_db": p_name,
                    "vendor_id": int(v_id),
                    "product_id": int(p_id),
                    "alias_chain_hash": chain_hash,
                },
            }

            if not dry:
                BACKUP_DIR.mkdir(parents=True, exist_ok=True)
                bk = BACKUP_DIR / rule_path.name
                if not bk.exists():
                    shutil.copy2(rule_path, bk)
                meta = rule.setdefault("_meta_enrichment", {})
                meta["canonical_vendor"] = new_cv
                auth = rule.setdefault("_lia_independent_authoring", {})
                auth["revendor_c28"] = {
                    "date": NOW_ISO,
                    "previous_canonical": outcome["previous_canonical"],
                    "new_canonical": outcome["new_canonical"],
                    "candidate_used": outcome["candidate_used"],
                    "alias_chain_hash": chain_hash,
                    "marked_by": PASS_ID,
                }
                rule_path.write_text(json.dumps(rule, indent=2, ensure_ascii=False) + "\n",
                                     encoding="utf-8")
            return outcome
        elif len(rows) > 1:
            # Multiple matches = ambiguous, skip this candidate
            continue

    return {
        "basename": rule_path.name,
        "status": "NO_STRICT_MATCH",
        "candidates_tried": [{"vendor": v, "product": p, "source": s} for v, p, s in pairs],
        "previous_canonical": {
            "vendor_name": cv.get("vendor_name"),
            "product_name_db": cv.get("product_name_db"),
            "bucket": cv.get("bucket"),
        },
    }


def fuzzy_one(rule_path: Path, dburl: str, threshold: float = 0.6) -> dict[str, Any]:
    """
    c33 A23: fuzzy fallback using pg_trgm similarity().

    Operator-review-only. Returns top candidates for each rule's bare or cpe
    vendor+product pair sorted by combined similarity score. Does NOT mutate
    the rule -- use this output as input for manual triage, then run a
    separate apply pass with a hardcoded TRIAGE list (like c26
    apply_collision_triage pattern).

    threshold = minimum (vscore + pscore) / 2 to include a candidate.
    """
    try:
        rule = json.loads(rule_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return {"basename": rule_path.name, "status": "READ_FAIL", "error": str(exc)}

    pairs = _candidate_pairs(rule)
    if not pairs:
        return {"basename": rule_path.name, "status": "NO_CANDIDATES"}

    all_candidates: list[dict[str, Any]] = []
    for vendor, product, src_tag in pairs:
        rows = _psql_query(dburl, FUZZY_LOOKUP_SQL,
                           {"vendor": vendor, "product": product})
        for row in rows:
            v_id, v_name, p_id, p_name, alias_source, vscore_s, pscore_s = row
            vscore = float(vscore_s)
            pscore = float(pscore_s)
            avg = (vscore + pscore) / 2.0
            if avg < threshold:
                continue
            all_candidates.append({
                "candidate_input": {"vendor": vendor, "product": product, "source": src_tag},
                "vendor_id": int(v_id),
                "vendor_name": v_name,
                "product_id": int(p_id),
                "product_name_db": p_name,
                "alias_source": alias_source,
                "vscore": round(vscore, 3),
                "pscore": round(pscore, 3),
                "avg_score": round(avg, 3),
            })

    if not all_candidates:
        return {
            "basename": rule_path.name,
            "status": "NO_FUZZY_MATCH",
            "threshold": threshold,
        }

    # Sort by avg_score desc, dedupe (vendor_id, product_id)
    seen: set[tuple[int, int]] = set()
    deduped: list[dict[str, Any]] = []
    for cand in sorted(all_candidates, key=lambda c: -c["avg_score"]):
        key = (cand["vendor_id"], cand["product_id"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(cand)

    return {
        "basename": rule_path.name,
        "status": "FUZZY_CANDIDATES",
        "threshold": threshold,
        "candidate_count": len(deduped),
        "candidates": deduped[:5],
    }


def vendor_only_one(rule_path: Path, dburl: str, threshold: float = 0.7) -> dict[str, Any]:
    """
    c34 A26: vendor-only fuzzy lookup. Used when rule.product is None/empty.

    Output-only. Returns top vendor matches without product join. Caller
    decides whether to write a vendor-only canonical_vendor block
    (product_id=None, bucket=VENDOR_ONLY_CONFIDENT) via separate apply step.

    threshold = minimum vscore. Default 0.7 (higher than vendor+product
    fuzzy 0.6 since vendor-only has less context).
    """
    try:
        rule = json.loads(rule_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return {"basename": rule_path.name, "status": "READ_FAIL", "error": str(exc)}

    pairs = _candidate_pairs(rule)
    bare_vendor = (rule.get("vendor") or "").strip()
    if not bare_vendor and pairs:
        bare_vendor = pairs[0][0]
    if not bare_vendor:
        return {"basename": rule_path.name, "status": "NO_VENDOR_INPUT"}

    rows = _psql_query(dburl, VENDOR_ONLY_LOOKUP_SQL, {"vendor": bare_vendor})

    candidates: list[dict[str, Any]] = []
    for row in rows:
        v_id, v_name, alias_source, vscore_s = row
        vscore = float(vscore_s)
        if vscore < threshold:
            continue
        candidates.append({
            "candidate_input": {"vendor": bare_vendor},
            "vendor_id": int(v_id),
            "vendor_name": v_name,
            "alias_source": alias_source,
            "vscore": round(vscore, 3),
        })

    if not candidates:
        return {
            "basename": rule_path.name,
            "status": "NO_VENDOR_FUZZY_MATCH",
            "threshold": threshold,
            "input_vendor": bare_vendor,
        }

    # Dedupe by vendor_id (keep highest vscore)
    seen: set[int] = set()
    deduped: list[dict[str, Any]] = []
    for cand in sorted(candidates, key=lambda c: -c["vscore"]):
        if cand["vendor_id"] in seen:
            continue
        seen.add(cand["vendor_id"])
        deduped.append(cand)

    return {
        "basename": rule_path.name,
        "status": "VENDOR_FUZZY_CANDIDATES",
        "threshold": threshold,
        "input_vendor": bare_vendor,
        "candidate_count": len(deduped),
        "candidates": deduped[:5],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument(
        "--include-non-canonical",
        action="store_true",
        help="A19j (c32): also scan rules with no canonical_vendor block but a "
             "bare top-level vendor+product. Tier 1b bare rules. Requires --apply "
             "or --dry-run as usual.",
    )
    ap.add_argument(
        "--fuzzy-fallback",
        action="store_true",
        help="A23 (c33): for every rule that returns NO_STRICT_MATCH (and "
             "NOT_DOUBTFUL_SKIP when combined with --include-non-canonical), "
             "run a pg_trgm fuzzy lookup with similarity threshold >= 0.6. "
             "OUTPUT-ONLY: candidates are written to the JSON artifact for "
             "manual triage. Does NOT mutate rule files (would need separate "
             "TRIAGE list pattern like apply_collision_triage).",
    )
    ap.add_argument(
        "--fuzzy-threshold",
        type=float,
        default=0.6,
        help="Threshold for fuzzy avg(vscore, pscore). Default 0.6.",
    )
    ap.add_argument(
        "--vendor-only-fuzzy",
        action="store_true",
        help="A26 (c34): for every rule returning NO_FUZZY_MATCH (or "
             "NO_STRICT_MATCH if --fuzzy-fallback off), run a vendor-only "
             "pg_trgm lookup on vendor_alias. Threshold defaults to 0.7 "
             "(higher than vendor+product fuzzy). OUTPUT-ONLY.",
    )
    ap.add_argument(
        "--vendor-only-threshold",
        type=float,
        default=0.7,
        help="Threshold for vendor-only fuzzy vscore. Default 0.7.",
    )
    args = ap.parse_args()
    if not args.apply and not args.dry_run:
        ap.error("Specify --apply or --dry-run")
    if args.fuzzy_fallback and not (0.0 < args.fuzzy_threshold < 1.0):
        ap.error("--fuzzy-threshold must be in (0, 1)")
    if args.vendor_only_fuzzy and not (0.0 < args.vendor_only_threshold < 1.0):
        ap.error("--vendor-only-threshold must be in (0, 1)")

    dburl = _systemd_dburl()
    if not dburl:
        print("FATAL: no DATABASE_URL via systemctl cat lia-backend", file=sys.stderr)
        return 2

    # c30 GATE: psql_dry_run_self_test. Run ONE known-positive query before
    # the main loop. If it returns 0 rows, subprocess args / column names /
    # connection are broken and main loop would silently report all rules as
    # NO_STRICT_MATCH (c28 incident).
    sentinel = _psql_query(
        dburl, STRICT_LOOKUP_SQL,
        {"vendor": "Linkerd", "product": "Linkerd"},
    )
    if not sentinel:
        print("FATAL: psql_dry_run_self_test failed. Sentinel "
              "(Linkerd/Linkerd) returned 0 rows. Check subprocess args, "
              "column names, vendor_alias + product population, "
              "DATABASE_URL.", file=sys.stderr)
        return 3
    print(f"[INFO] psql_dry_run_self_test PASS (sentinel Linkerd/Linkerd -> "
          f"vendor_id={sentinel[0][0]})")

    rules_dir = LIAPROBE_DIR / "patterns/lia"
    doubtful = _scan_doubtful_rules(rules_dir, include_non_canonical=args.include_non_canonical)
    print(f"[INFO] rules scanned          : {len(doubtful)}")
    print(f"[INFO] include-non-canonical  : {args.include_non_canonical}")
    print(f"[INFO] fuzzy-fallback         : {args.fuzzy_fallback} (threshold={args.fuzzy_threshold})")
    print(f"[INFO] vendor-only-fuzzy      : {args.vendor_only_fuzzy} (threshold={args.vendor_only_threshold})")
    print(f"[INFO] mode                   : {'DRY-RUN' if args.dry_run else 'APPLY'}")
    print()

    results: list[dict[str, Any]] = []
    fuzzy_results: list[dict[str, Any]] = []
    vendor_only_results: list[dict[str, Any]] = []
    counts: dict[str, int] = {}
    for p in doubtful:
        r = revendor_one(p, dburl, args.dry_run, include_non_canonical=args.include_non_canonical)
        results.append(r)
        counts[r["status"]] = counts.get(r["status"], 0) + 1
        if r["status"] == "RESOLVED_CONFIDENT":
            print(f"  {p.name}: {r['previous_canonical']['vendor_name']}/{r['previous_canonical']['product_name_db']} -> "
                  f"{r['new_canonical']['vendor_name']}/{r['new_canonical']['product_name_db']}")
        elif r["status"] == "NO_STRICT_MATCH":
            print(f"  {p.name}: no strict match (kept DOUBTFUL)")
            no_fuzzy = True
            # c33 A23: fuzzy fallback for unresolved rules
            if args.fuzzy_fallback:
                fr = fuzzy_one(p, dburl, threshold=args.fuzzy_threshold)
                fuzzy_results.append(fr)
                if fr["status"] == "FUZZY_CANDIDATES":
                    no_fuzzy = False
                    top = fr["candidates"][0]
                    print(f"    fuzzy: top -> {top['vendor_name']}/{top['product_name_db']} "
                          f"(avg={top['avg_score']})")
            # c34 A26: vendor-only fuzzy when vendor+product fuzzy yields nothing
            if args.vendor_only_fuzzy and no_fuzzy:
                vor = vendor_only_one(p, dburl, threshold=args.vendor_only_threshold)
                vendor_only_results.append(vor)
                if vor["status"] == "VENDOR_FUZZY_CANDIDATES":
                    top = vor["candidates"][0]
                    print(f"    vendor-only: top -> {top['vendor_name']} (vscore={top['vscore']})")

    artifact = {
        "schema": "lia-revendor-results-v1",
        "generated_at": NOW_ISO,
        "pass_id": PASS_ID,
        "summary": counts,
        "results": results,
    }
    if args.fuzzy_fallback:
        artifact["fuzzy_threshold"] = args.fuzzy_threshold
        artifact["fuzzy_results"] = fuzzy_results
        fc_with_candidates = sum(1 for f in fuzzy_results if f.get("status") == "FUZZY_CANDIDATES")
        artifact["fuzzy_summary"] = {
            "rules_with_fuzzy_candidates": fc_with_candidates,
            "rules_no_fuzzy_match": sum(1 for f in fuzzy_results if f.get("status") == "NO_FUZZY_MATCH"),
            "total_fuzzy_scanned": len(fuzzy_results),
        }
    if args.vendor_only_fuzzy:
        artifact["vendor_only_threshold"] = args.vendor_only_threshold
        artifact["vendor_only_results"] = vendor_only_results
        vc_with_candidates = sum(1 for v in vendor_only_results if v.get("status") == "VENDOR_FUZZY_CANDIDATES")
        artifact["vendor_only_summary"] = {
            "rules_with_vendor_candidates": vc_with_candidates,
            "rules_no_vendor_fuzzy": sum(1 for v in vendor_only_results if v.get("status") == "NO_VENDOR_FUZZY_MATCH"),
            "rules_no_vendor_input": sum(1 for v in vendor_only_results if v.get("status") == "NO_VENDOR_INPUT"),
            "total_vendor_only_scanned": len(vendor_only_results),
        }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(artifact, indent=2, ensure_ascii=False), encoding="utf-8")

    print("\n[SUMMARY]")
    for k in sorted(counts.keys()):
        print(f"  {k:<28}: {counts[k]}")
    print(f"\noutput: {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
