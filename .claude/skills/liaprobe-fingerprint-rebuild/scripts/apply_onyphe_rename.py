#!/usr/bin/env python3
# apply_onyphe_rename.py
#
# Apply rename proposals from ONYPHE_RENAME_PROPOSALS report: align
# rule.product (and taxonomy_name when present) to the Onyphe canonical
# product name as observed in wild ground-truth.
#
# Original product stored in _lia_independent_authoring.previous_product_*
# for auditability. Backup of original file written to BACKUP_DIR.
#
# Usage:
#   python3 apply_onyphe_rename.py --dry-run
#   python3 apply_onyphe_rename.py --apply
#   python3 apply_onyphe_rename.py --apply --min-tp 5  # only rename rules with >= 5 TP

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

LIAPROBE_DIR = Path("/opt/lia-sec/liaprobe")
DEV_DIR = Path("/opt/lia-sec/dev")
TRACKING_DIR = DEV_DIR / "_alire/tracking/liaprobe-fingerprint-rebuild"
PROPOSALS = TRACKING_DIR / "ONYPHE_RENAME_PROPOSALS_2026-05-12.json"
BACKUP_DIR = DEV_DIR / "_alire/temp/apex/apex-20260512-c7/rename_backup"

RUN_DATE = datetime.now(timezone.utc).strftime("%Y-%m-%d")
NOW_ISO = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
PASS_ID = "2026-05-12_apex_c7_rename"


def apply_one(proposal: dict, dry: bool) -> str:
    rule_path = LIAPROBE_DIR / proposal["rule_file"]
    if not rule_path.exists():
        return f"MISSING {proposal['rule_file']}"
    try:
        rule = json.loads(rule_path.read_text())
    except (json.JSONDecodeError, OSError) as e:
        return f"ERROR_READ {rule_path.name}: {e}"

    current = proposal["current_product"]
    proposed = proposal["proposed_product"]

    if rule.get("product") == proposed:
        return f"SKIP_ALREADY_RENAMED {rule_path.name}"

    auth = rule.setdefault("_lia_independent_authoring", {})
    # Backup original
    if not dry:
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        backup_path = BACKUP_DIR / rule_path.name
        if not backup_path.exists():
            shutil.copy2(rule_path, backup_path)

    # Track previous values
    if "product" in rule:
        auth.setdefault("previous_product", rule["product"])
        rule["product"] = proposed
    if "taxonomy_name" in rule:
        auth.setdefault("previous_taxonomy_name", rule["taxonomy_name"])
        rule["taxonomy_name"] = proposed

    auth["onyphe_canonical_rename"] = {
        "date": NOW_ISO,
        "from": current,
        "to": proposed,
        "tp_supporting": proposal["tp_count_supporting"],
        "gt_distribution": proposal["gt_distribution"],
        "marked_by": f"apply_onyphe_rename.py {PASS_ID}",
    }

    if dry:
        return (f"DRY-RUN {rule_path.name}: '{current}' -> '{proposed}' "
                f"(tp={proposal['tp_count_supporting']})")

    rule_path.write_text(json.dumps(rule, indent=2, ensure_ascii=False) + "\n")
    return (f"RENAMED {rule_path.name}: '{current}' -> '{proposed}' "
            f"(tp={proposal['tp_count_supporting']})")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--apply", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--min-tp", type=int, default=1,
                   help="Only apply if tp_count_supporting >= min-tp (default 1)")
    args = p.parse_args()
    if not args.apply and not args.dry_run:
        p.error("Specify --apply or --dry-run")

    if not PROPOSALS.exists():
        print(f"[ERROR] {PROPOSALS} not found", file=sys.stderr)
        sys.exit(1)

    report = json.loads(PROPOSALS.read_text())
    props = [p for p in report.get("proposals", [])
             if p.get("tp_count_supporting", 0) >= args.min_tp]
    print(f"[INFO] {len(props)} proposals (tp >= {args.min_tp}) of "
          f"{len(report.get('proposals', []))} total")

    counts = {"RENAMED": 0, "DRY-RUN": 0, "SKIP_ALREADY_RENAMED": 0,
              "MISSING": 0, "ERROR_READ": 0}
    for p in sorted(props, key=lambda x: -x["tp_count_supporting"]):
        result = apply_one(p, args.dry_run)
        # tally
        key = result.split()[0]
        counts[key] = counts.get(key, 0) + 1
        if args.dry_run or "RENAMED" in result:
            print(f"  {result}")
    print(f"\n[SUMMARY]")
    for k, v in counts.items():
        if v:
            print(f"  {k}: {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
