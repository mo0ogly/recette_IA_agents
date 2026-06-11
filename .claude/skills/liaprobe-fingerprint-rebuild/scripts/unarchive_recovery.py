#!/usr/bin/env python3
# unarchive_recovery.py
#
# Restore rules archived in error (per ONYPHE_ARCHIVE_RECOVERY report).
# For each recovery candidate:
#   1. Move file from patterns/<cat>/archive/ back to patterns/<cat>/
#   2. Remove _lia_independent_authoring.vendor_dead block
#   3. Set enabled=true
#   4. Add audit trail: _lia_independent_authoring.unarchived_by
#
# Usage:
#   python3 unarchive_recovery.py --dry-run
#   python3 unarchive_recovery.py --apply

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

LIAPROBE_DIR = Path("/opt/lia-sec/liaprobe")
PATTERNS_ROOT = LIAPROBE_DIR / "patterns"
DEV_DIR = Path("/opt/lia-sec/dev")
TRACKING_DIR = DEV_DIR / "_alire/tracking/liaprobe-fingerprint-rebuild"
RECOVERY_REPORT = TRACKING_DIR / "ONYPHE_ARCHIVE_RECOVERY_2026-05-12.json"

RUN_DATE = datetime.now(timezone.utc).strftime("%Y-%m-%d")
NOW_ISO = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
PASS_ID = "2026-05-12_apex_c7_unarchive"


def unarchive_one(archive_path: Path, gt_product: str, miss_count: int,
                  dry: bool) -> str:
    """Move file back to active dir, strip vendor_dead, enable. Return action str."""
    active_path = archive_path.parent.parent / archive_path.name
    if active_path.exists():
        return f"SKIP_ALREADY_ACTIVE  {archive_path.name}"
    try:
        rule = json.loads(archive_path.read_text())
    except (json.JSONDecodeError, OSError) as e:
        return f"ERROR_READ {archive_path.name}: {e}"

    rule["enabled"] = True
    auth = rule.setdefault("_lia_independent_authoring", {})
    auth.pop("vendor_dead", None)
    auth["unarchived"] = {
        "date": NOW_ISO,
        "reason": "onyphe_engine_match",
        "evidence": f"Onyphe wild traffic: gt_product={gt_product!r} miss_count={miss_count}",
        "marked_by": f"unarchive_recovery.py {PASS_ID}",
    }

    if dry:
        return f"DRY-RUN  {archive_path.name} -> {active_path.parent.name}/"

    active_path.write_text(json.dumps(rule, indent=2, ensure_ascii=False) + "\n")
    archive_path.unlink()
    return f"UNARCHIVED  {archive_path.name} -> {active_path.parent.name}/"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--apply", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()
    if not args.apply and not args.dry_run:
        p.error("Specify --apply or --dry-run")

    if not RECOVERY_REPORT.exists():
        print(f"[ERROR] {RECOVERY_REPORT} not found", file=sys.stderr)
        sys.exit(1)

    report = json.loads(RECOVERY_REPORT.read_text())
    candidates = report.get("recovery_candidates_miss", [])
    print(f"[INFO] {len(candidates)} recovery candidates loaded")

    actions = []
    for c in candidates:
        gt = c["gt_product"]
        miss = c["miss_count"]
        for ar in c["archived_rules"]:
            path = LIAPROBE_DIR / ar["path"]
            if not path.exists():
                actions.append(f"MISSING  {ar['path']}")
                continue
            actions.append(unarchive_one(path, gt, miss, args.dry_run))

    for a in actions:
        print(f"  {a}")
    print(f"\n[SUMMARY] {len([a for a in actions if a.startswith(('UNARCHIVED', 'DRY-RUN'))])} files processed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
