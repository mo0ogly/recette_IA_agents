#!/usr/bin/env python3
# disable_low_precision_rules.py
#
# Disable rules whose precision is below threshold on Onyphe wild traffic.
# Reads WRONG_BY_RULE report, identifies rules with:
#   - precision < --max-precision (default 0.30)
#   - fp_count >= --min-fp (default 3)
# Sets rule.enabled = false + audit trail.
#
# Index of (PatternID -> rule file path) is built across all patterns/
# subdirs (web-signatures + banner-signatures + service-detectors +
# tcp-probes + lia). Backups saved to BACKUP_DIR.
#
# Usage:
#   python3 disable_low_precision_rules.py --dry-run
#   python3 disable_low_precision_rules.py --apply --max-precision 0.3 --min-fp 3

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
REPORT = TRACKING_DIR / "WRONG_BY_RULE_2026-05-13.json"
BACKUP_DIR = DEV_DIR / "_alire/temp/apex/apex-20260513-c8/disable_backup"

NOW_ISO = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
PASS_ID = "2026-05-13_apex_c8_disable"


def build_pattern_index() -> dict:
    """Map pattern_id -> LIST of (path, rule) tuples. Cluster-aware to avoid
    c13-style bug where disable touched only 1 of N files sharing same id.
    Loader-discoverable subdirs only (skip todo/ + archive/ + nested).
    """
    idx = {}
    for sub in ("web-signatures", "banner-signatures",
                "service-detectors", "tcp-probes", "lia"):
        d = PATTERNS_ROOT / sub
        if not d.exists():
            continue
        for path in d.glob("*.json"):
            try:
                rule = json.loads(path.read_text())
            except (json.JSONDecodeError, OSError):
                continue
            pid_seen = set()
            for pid in (rule.get("id"), rule.get("taxonomy_code"), path.stem):
                if pid and isinstance(pid, str) and pid.lower() not in pid_seen:
                    pid_seen.add(pid.lower())
                    idx.setdefault(pid.lower(), []).append((path, rule))
                    break
    return idx


def disable_rule(path: Path, rule: dict, rec: dict, dry: bool) -> str:
    if rule.get("enabled") is False:
        return f"SKIP_ALREADY_DISABLED {path.name}"
    if not dry:
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        bp = BACKUP_DIR / path.name
        if not bp.exists():
            shutil.copy2(path, bp)
    rule["enabled"] = False
    auth = rule.setdefault("_lia_independent_authoring", {})
    auth["disabled_low_precision"] = {
        "date": NOW_ISO,
        "fp": rec["fp"],
        "tp": rec["tp"],
        "precision": rec["precision"],
        "det_product": rec["det_product"],
        "gt_when_wrong": rec["gt_when_wrong"],
        "marked_by": f"disable_low_precision_rules.py {PASS_ID}",
    }
    if dry:
        return (f"DRY-RUN {path.name}: prec={rec['precision']} fp={rec['fp']} "
                f"tp={rec['tp']}")
    path.write_text(json.dumps(rule, indent=2, ensure_ascii=False) + "\n")
    return (f"DISABLED {path.name}: prec={rec['precision']} fp={rec['fp']} "
            f"tp={rec['tp']}")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--apply", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--max-precision", type=float, default=0.30)
    p.add_argument("--min-fp", type=int, default=3)
    args = p.parse_args()
    if not args.apply and not args.dry_run:
        p.error("Specify --apply or --dry-run")

    report = json.loads(REPORT.read_text())
    candidates = []
    for r in report["rules"]:
        prec = r["precision"] if r["precision"] is not None else 0
        if prec < args.max_precision and r["fp"] >= args.min_fp:
            candidates.append(r)
    print(f"[INFO] {len(candidates)} rules below threshold "
          f"(precision < {args.max_precision} AND fp >= {args.min_fp})")
    for c in candidates:
        print(f"  - {c['pattern_id']:35s} prec={c['precision']} fp={c['fp']} tp={c['tp']}")

    if not candidates:
        return 0

    idx = build_pattern_index()
    print(f"\n[INFO] Pattern index: {len(idx)} entries")

    actions = []
    cluster_summary = {}  # pid -> count of files affected
    for rec in candidates:
        pid = rec["pattern_id"].lower()
        entries = idx.get(pid)
        if not entries:
            actions.append(f"NOT_FOUND {pid}")
            continue
        # Cluster-aware: disable ALL files sharing this id (c13 lesson)
        cluster_summary[pid] = len(entries)
        for path, rule in entries:
            actions.append(disable_rule(path, rule, rec, args.dry_run))

    print()
    for a in actions:
        print(f"  {a}")
    print(f"\n[CLUSTER COVERAGE]")
    multi_file = [(pid, n) for pid, n in cluster_summary.items() if n > 1]
    if multi_file:
        print(f"  {len(multi_file)} pattern_ids resolved to multiple files "
              f"(cluster-aware disable):")
        for pid, n in multi_file:
            print(f"    {pid}: {n} files disabled together")
    else:
        print("  All candidate pattern_ids resolved to single files.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
