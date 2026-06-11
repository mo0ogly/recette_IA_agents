#!/usr/bin/env python3
# archive_vendor_dead.py
#
# Move rules carrying a vendor_dead block from patterns/web-signatures/
# to patterns/web-signatures/archive/. Rules in archive/ are not loaded
# by the liaprobe runtime, removing them from active scan rotation.
#
# Usage:
#   python3 archive_vendor_dead.py --dry-run       # list, no move
#   python3 archive_vendor_dead.py --apply         # mv to archive/
#
# Provenance: rules end up here when http_gate confirms vendor unreachable
# (DNS / SSL / timeout / 403) across 1-2 audit passes. They retain the
# vendor_dead block for future reconsideration (re-audit after N days).

import argparse
import json
import shutil
import sys
from pathlib import Path

LIAPROBE_DIR = Path("/opt/lia-sec/liaprobe")
PATTERNS_DIR = LIAPROBE_DIR / "patterns/web-signatures"
ARCHIVE_DIR = PATTERNS_DIR / "archive"


def scan_targets() -> list:
    targets = []
    for path in sorted(PATTERNS_DIR.glob("*.json")):
        try:
            rule = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        vd = rule.get("_lia_independent_authoring", {}).get("vendor_dead")
        if vd:
            targets.append((path, rule, vd))
    return targets


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--apply", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()
    if not args.apply and not args.dry_run:
        p.error("Specify --apply or --dry-run")

    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    targets = scan_targets()
    print(f"[INFO] Found {len(targets)} rules with vendor_dead block")

    by_reason = {}
    for _, _, vd in targets:
        by_reason[vd.get("reason", "?")] = by_reason.get(vd.get("reason", "?"), 0) + 1
    for k, v in by_reason.items():
        print(f"  reason={k}: {v}")

    if not targets:
        return 0

    moved = 0
    for path, rule, vd in targets:
        code = rule.get("taxonomy_code", path.stem)
        dest = ARCHIVE_DIR / path.name
        if args.dry_run:
            print(f"  DRY-RUN  {code} -> archive/ (since {vd.get('since', '?')[:10]})")
            continue
        # If a file with same name already in archive/, overwrite (latest state wins).
        if dest.exists():
            dest.unlink()
        shutil.move(str(path), str(dest))
        moved += 1

    if args.apply:
        print(f"[SUMMARY] moved {moved} rule files to archive/")
    else:
        print(f"[SUMMARY] would move {len(targets)} rule files to archive/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
