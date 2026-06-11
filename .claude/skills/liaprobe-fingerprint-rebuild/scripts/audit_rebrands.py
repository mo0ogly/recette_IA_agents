#!/usr/bin/env python3
# audit_rebrands.py
#
# Detect taxonomy drift between rule.product field and the canonical
# product name in LIA-SEC postgres product table.
#
# Discovers rebrands like:
#   "Lotus Domino" -> "Domino"      (IBM rebrand post-v9)
#   "GHost"        -> "AkamaiGHost" (Akamai naming consolidation)
#   "Skype for Business" -> ...
#
# Strategy:
#   1. Scan active patterns/ rules (skip todo/ + archive/ + nested)
#   2. For each rule, extract product + vendor fields
#   3. Query postgres : is rule.product the canonical product_name OR an
#      alias? If alias-only, propose rename to canonical.
#   4. Optional postgres `vendor_alias` cross-reference for aliases on the
#      product term too (e.g. via product_name LIKE)
#   5. Output ONYPHE_REBRAND_PROPOSALS_<DATE>.json
#
# Usage:
#   python3 audit_rebrands.py
#   python3 audit_rebrands.py --apply       # rewrites rule.product
#   python3 audit_rebrands.py --apply --min-confidence 0.9

import argparse
import json
import os
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

LIAPROBE_DIR = Path("/opt/lia-sec/liaprobe")
PATTERNS_ROOT = LIAPROBE_DIR / "patterns"
DEV_DIR = Path("/opt/lia-sec/dev")
TRACKING_DIR = DEV_DIR / "_alire/tracking/liaprobe-fingerprint-rebuild"
BACKUP_DIR = DEV_DIR / "_alire/temp/apex/apex-20260513-c13/rebrand_backup"

RUN_DATE = datetime.now(timezone.utc).strftime("%Y-%m-%d")
NOW_ISO = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
PASS_ID = f"{RUN_DATE}_apex_c13_audit_rebrands"


def discover_database_url() -> str:
    """Read DATABASE_URL from systemd unit."""
    import subprocess
    try:
        out = subprocess.run(["systemctl", "cat", "lia-backend"],
                             capture_output=True, text=True, timeout=5).stdout
    except Exception:
        return ""
    for line in out.splitlines():
        if line.startswith("Environment=DATABASE_URL="):
            return line.split("=", 2)[2].strip()
        if line.startswith("Environment=") and "DATABASE_URL" in line:
            return line.split("DATABASE_URL=", 1)[1].strip()
    return ""


def normalize(s: str) -> str:
    if not s:
        return ""
    return re.sub(r"[^a-z0-9]", "", s.lower())


def scan_active_rules() -> list:
    """Walk patterns/<cat>/*.json (loader-discoverable only). Return list of
    dicts: {path, id, product, taxonomy_name, vendor, enabled}."""
    out = []
    for subdir in PATTERNS_ROOT.iterdir():
        if not subdir.is_dir():
            continue
        for path in subdir.glob("*.json"):
            try:
                rule = json.loads(path.read_text())
            except (json.JSONDecodeError, OSError):
                continue
            product = (rule.get("product") or "").strip()
            if not product:
                continue
            out.append({
                "path": str(path.relative_to(LIAPROBE_DIR)),
                "id": (rule.get("id") or "").lower(),
                "product": product,
                "taxonomy_name": (rule.get("taxonomy_name") or "").strip(),
                "vendor": (rule.get("vendor") or "").strip(),
                "enabled": rule.get("enabled", True),
            })
    return out


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--apply", action="store_true")
    p.add_argument("--dry-run", action="store_true", default=True)
    p.add_argument("--min-confidence", type=float, default=0.9,
                   help="Only propose rename if alias confidence >= threshold")
    p.add_argument("--include-disabled", action="store_true",
                   help="Audit disabled rules too (default skip)")
    args = p.parse_args()
    if args.apply:
        args.dry_run = False

    url = discover_database_url()
    if not url:
        print("[ERROR] no DATABASE_URL discovered", file=sys.stderr)
        sys.exit(2)

    try:
        import psycopg2
    except ImportError:
        print("[ERROR] psycopg2 not available", file=sys.stderr)
        sys.exit(3)

    conn = psycopg2.connect(url, connect_timeout=10)

    print("[INFO] Scanning active rules...")
    rules = scan_active_rules()
    if not args.include_disabled:
        rules = [r for r in rules if r["enabled"]]
    print(f"[INFO] {len(rules)} candidate rules")

    proposals = []
    no_match = 0
    aligned = 0

    with conn.cursor() as cur:
        for r in rules:
            product_norm = normalize(r["product"])
            if not product_norm:
                continue

            # 1. Check if rule.product matches a canonical product_name in DB
            cur.execute(
                """
                SELECT product_id, product_name, vendor_id
                FROM product
                WHERE lower(product_name) = %s
                ORDER BY product_id
                LIMIT 1
                """,
                (r["product"].lower(),),
            )
            row = cur.fetchone()
            if row:
                aligned += 1
                continue

            # 2. Rule.product is NOT a canonical product_name -- search for
            # close matches via pg_trgm + manual rebrand patterns
            # (substring + word permutations)
            cur.execute(
                """
                SELECT product_id, product_name, vendor_id,
                       similarity(product_name, %s) AS sim
                FROM product
                WHERE product_name %% %s
                ORDER BY sim DESC
                LIMIT 5
                """,
                (r["product"], r["product"]),
            )
            candidates = cur.fetchall()
            if not candidates:
                no_match += 1
                continue

            # Best candidate
            best = candidates[0]
            best_pid, best_name, best_vid, best_sim = best
            if best_sim is None or best_sim < args.min_confidence:
                no_match += 1
                continue

            # Filter out cosmetic-only differences (case, spacing, punctuation
            # like _ vs space, ! removed). Real rebrands have different
            # alpha-numeric content.
            current_letters = re.sub(r"[^a-z0-9]", "", r["product"].lower())
            proposed_letters = re.sub(r"[^a-z0-9]", "", best_name.lower())
            if current_letters == proposed_letters:
                aligned += 1  # cosmetic only -- treat as aligned
                continue

            # Filter out word-reorder / word-set equality (e.g.
            # "Access Remote PC" vs "Remote Pc Access"). Tokenize alpha-num
            # words, compare sets.
            current_tokens = set(re.findall(r"[a-z0-9]+", r["product"].lower()))
            proposed_tokens = set(re.findall(r"[a-z0-9]+", best_name.lower()))
            if current_tokens == proposed_tokens:
                aligned += 1  # same token set, different order -- skip
                continue

            # Strong rebrand candidate -- propose
            cur.execute(
                "SELECT vendor_name FROM vendor WHERE vendor_id = %s",
                (best_vid,),
            )
            vrow = cur.fetchone()
            best_vendor = vrow[0] if vrow else None

            proposals.append({
                "rule_file": r["path"],
                "rule_id": r["id"],
                "current_product": r["product"],
                "current_vendor": r["vendor"],
                "proposed_product": best_name,
                "proposed_vendor": best_vendor,
                "confidence": round(float(best_sim), 3),
                "product_id": int(best_pid),
                "vendor_id": int(best_vid),
                "all_candidates": [
                    {"name": c[1], "sim": round(float(c[3]), 3)}
                    for c in candidates[:3]
                ],
            })

    conn.close()

    print(f"\n[STATS]")
    print(f"  Aligned (rule.product == canonical) : {aligned}")
    print(f"  No DB match                         : {no_match}")
    print(f"  Rebrand proposals                   : {len(proposals)}")

    # Sort proposals by confidence DESC for review
    proposals.sort(key=lambda x: -x["confidence"])

    report = {
        "schema": "lia-rebrand-proposals-v1",
        "run_date": RUN_DATE,
        "min_confidence": args.min_confidence,
        "total_rules_scanned": len(rules),
        "aligned": aligned,
        "no_match": no_match,
        "proposals": proposals,
    }
    out_path = TRACKING_DIR / f"REBRAND_PROPOSALS_{RUN_DATE}.json"
    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False))
    print(f"  Report: {out_path}")

    print(f"\nTop 15 rebrand proposals:")
    for p in proposals[:15]:
        print(f"  {p['rule_file']:50s} "
              f"'{p['current_product'][:25]}' -> "
              f"'{p['proposed_product'][:25]}' (sim={p['confidence']})")

    if args.dry_run:
        return 0

    # Apply mode -- rewrite rule.product + add audit trail
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    applied = 0
    for p_ in proposals:
        path = LIAPROBE_DIR / p_["rule_file"]
        try:
            rule = json.loads(path.read_text())
        except Exception:
            continue
        shutil.copy2(path, BACKUP_DIR / path.name)
        old_product = rule.get("product")
        rule["product"] = p_["proposed_product"]
        if p_.get("proposed_vendor") and rule.get("vendor") != p_["proposed_vendor"]:
            rule["vendor"] = p_["proposed_vendor"]
        auth = rule.setdefault("_lia_independent_authoring", {})
        auth.setdefault("rebrand_history", []).append({
            "date": NOW_ISO,
            "from_product": old_product,
            "to_product": p_["proposed_product"],
            "vendor": p_["proposed_vendor"],
            "confidence": p_["confidence"],
            "marked_by": PASS_ID,
        })
        path.write_text(json.dumps(rule, indent=2, ensure_ascii=False) + "\n")
        applied += 1
    print(f"\n[APPLY] {applied} rules rebranded")
    return 0


if __name__ == "__main__":
    sys.exit(main())
