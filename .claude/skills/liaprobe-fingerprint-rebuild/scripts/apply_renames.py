#!/usr/bin/env python3
# apply_renames.py
#
# Apply selected rename proposals from RENAME_PROPOSALS_<DATE>.json
# (schema lia-rename-proposals-v1, produced by rename_proposals.py).
#
# For each safe proposal:
#   - git mv current basename -> proposed basename (preserves history)
#   - patch JSON: vendor, product, source.file per field_updates block
#   - inject _lia_independent_authoring.filename_rename_c{N} audit block
#   - backup original to BACKUP_DIR before any write
#
# Safe filter (default):
#   action in {rename, fields_only_update}
#   AND flags excludes:
#     - collision_with_other_rule   (human disambiguation needed)
#     - not_confident_resolution    (DOUBTFUL bucket = wrong canonical)
#     - canonical_marked_ambiguous
#     - parse_error
#
# Usage:
#   python3 apply_renames.py --dry-run
#   python3 apply_renames.py --apply
#   python3 apply_renames.py --apply --max 5         # limit for smoke
#   python3 apply_renames.py --apply --tier 1a       # Tier 1a only (default both)
#   python3 apply_renames.py --apply --include-collisions   # NOT recommended

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

LIAPROBE_DIR = Path("/opt/lia-sec/liaprobe")
DEV_DIR = Path("/opt/lia-sec/dev")
TRACKING_DIR = DEV_DIR / "_alire/tracking/liaprobe-fingerprint-rebuild"
PROPOSALS_DEFAULT = TRACKING_DIR / f"RENAME_PROPOSALS_{datetime.now(timezone.utc).strftime('%Y-%m-%d')}.json"

RUN_DATE = datetime.now(timezone.utc).strftime("%Y-%m-%d")
NOW_ISO = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
CYCLE = "c25"
PASS_ID = f"{RUN_DATE}_apex_{CYCLE}_apply_renames"
BACKUP_DIR = DEV_DIR / f"_alire/temp/apex/apex-{RUN_DATE.replace('-', '')}-{CYCLE}/rename_backup"

UNSAFE_FLAGS = {
    "collision_with_other_rule",
    "not_confident_resolution",
    "canonical_marked_ambiguous",
    "parse_error",
}


def _filter_safe(proposals: list[dict], tier_filter: str | None,
                 include_collisions: bool) -> list[dict]:
    safe: list[dict] = []
    for p in proposals:
        if p.get("action") not in ("rename", "fields_only_update"):
            continue
        if tier_filter and p.get("tier") != tier_filter:
            continue
        flag_names = {f.split(":", 1)[0] for f in p.get("flags", [])}
        unsafe = UNSAFE_FLAGS - ({"collision_with_other_rule"} if include_collisions else set())
        if flag_names & unsafe:
            continue
        safe.append(p)
    return safe


def _git_mv(repo_dir: Path, src: Path, dst: Path) -> tuple[bool, str]:
    if dst.exists():
        return False, f"DEST_EXISTS {dst.name}"
    cmd = ["git", "-C", str(repo_dir), "mv", str(src.relative_to(repo_dir)),
           str(dst.relative_to(repo_dir))]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=10)
    except subprocess.CalledProcessError as exc:
        return False, f"GIT_MV_FAIL {src.name}: {exc.stderr.strip()}"
    return True, ""


def _patch_rule(rule_path: Path, field_updates: dict[str, dict[str, Any]],
                proposal: dict, dry: bool) -> tuple[bool, str]:
    # NEVER patch top-level vendor or product -- engine uses them as the
    # detected_product label. Patching breaks Onyphe ground-truth match
    # (incident c25 ST3: 1658 CORRECT -> WRONG verdicts). Canonical values
    # live in _meta_enrichment.canonical_vendor (sole source of truth for
    # naming). Hard-coded guard below filters any incoming bad updates.
    FORBIDDEN_FIELD_UPDATES = {"vendor", "product"}
    field_updates = {k: v for k, v in field_updates.items()
                     if k not in FORBIDDEN_FIELD_UPDATES}

    try:
        rule = json.loads(rule_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return False, f"READ_FAIL {rule_path.name}: {exc}"

    auth = rule.setdefault("_lia_independent_authoring", {})

    previous_values: dict[str, Any] = {}
    for key, change in field_updates.items():
        if key == "source.file":
            src_obj = rule.setdefault("source", {})
            previous_values[key] = src_obj.get("file")
            src_obj["file"] = change["proposed"]
        else:
            previous_values[key] = rule.get(key)
            rule[key] = change["proposed"]

    auth[f"filename_rename_{CYCLE}"] = {
        "date": NOW_ISO,
        "from_basename": proposal["current_basename"],
        "to_basename": proposal["proposed_basename"],
        "tier": proposal.get("tier"),
        "vendor_id": proposal.get("evidence", {}).get("vendor_id"),
        "product_id": proposal.get("evidence", {}).get("product_id"),
        "alias_chain_hash": proposal.get("evidence", {}).get("alias_chain_hash"),
        "resolved_via": proposal.get("evidence", {}).get("resolved_via"),
        "field_updates_applied": {
            k: {"from": previous_values[k], "to": v["proposed"]}
            for k, v in field_updates.items()
        },
        "reason": "Canonical NVD CPE vendor+product name. Replaces legacy quadrigramme stem. See SKILL.md 'Canonical filename rule'.",
        "marked_by": PASS_ID,
    }

    if dry:
        return True, ""
    rule_path.write_text(json.dumps(rule, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return True, ""


def _backup(src: Path) -> None:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    backup_path = BACKUP_DIR / src.name
    if not backup_path.exists():
        shutil.copy2(src, backup_path)


def apply_one(proposal: dict, dry: bool) -> str:
    rule_path = Path(proposal["rule_file"])
    if not rule_path.exists():
        return f"MISSING {rule_path.name}"

    current_basename = proposal["current_basename"]
    proposed_basename = proposal["proposed_basename"]
    action = proposal["action"]
    field_updates = proposal.get("field_updates", {})

    final_path = rule_path

    if action == "rename":
        new_path = rule_path.parent / proposed_basename
        if not dry:
            _backup(rule_path)
            ok, err = _git_mv(LIAPROBE_DIR, rule_path, new_path)
            if not ok:
                return err
            final_path = new_path
        # In dry-run, keep reading the existing path (rename not done yet)
    elif action == "fields_only_update":
        if not dry:
            _backup(rule_path)

    if field_updates:
        ok, err = _patch_rule(final_path, field_updates, proposal, dry)
        if not ok:
            return err

    if dry:
        if action == "rename":
            return f"DRY-RENAME {current_basename} -> {proposed_basename}"
        return f"DRY-FIELDS-ONLY {current_basename} (vendor/product/source.file)"
    if action == "rename":
        return f"RENAMED {current_basename} -> {proposed_basename}"
    return f"FIELDS_PATCHED {current_basename}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--proposals", type=Path, default=PROPOSALS_DEFAULT,
                    help=f"Path to RENAME_PROPOSALS_*.json (default: {PROPOSALS_DEFAULT.name})")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--max", type=int, default=0,
                    help="Max proposals to apply (0 = all)")
    ap.add_argument("--tier", choices=["1a_canonical_vendor", "1b_bare_fields"],
                    help="Filter by tier (default: both)")
    ap.add_argument("--include-collisions", action="store_true",
                    help="Include proposals flagged with collision_with_other_rule (NOT recommended)")
    args = ap.parse_args()

    if not args.apply and not args.dry_run:
        ap.error("Specify --apply or --dry-run")
    if not args.proposals.exists():
        print(f"FATAL: proposals not found: {args.proposals}", file=sys.stderr)
        return 2

    report = json.loads(args.proposals.read_text(encoding="utf-8"))
    if report.get("schema") != "lia-rename-proposals-v1":
        print(f"FATAL: unexpected schema: {report.get('schema')}", file=sys.stderr)
        return 2

    proposals = report.get("proposals", [])
    safe = _filter_safe(proposals, args.tier, args.include_collisions)
    if args.max > 0:
        safe = safe[:args.max]

    print(f"[INFO] proposals in report : {len(proposals)}")
    print(f"[INFO] safe to apply       : {len(safe)}")
    print(f"[INFO] mode                : {'DRY-RUN' if args.dry_run else 'APPLY'}")
    if args.tier:
        print(f"[INFO] tier filter         : {args.tier}")
    if args.include_collisions:
        print(f"[WARN] include_collisions  : ON")
    print(f"[INFO] backup dir          : {BACKUP_DIR}")
    print()

    counts: dict[str, int] = {}
    for p in safe:
        result = apply_one(p, args.dry_run)
        key = result.split(" ", 1)[0]
        counts[key] = counts.get(key, 0) + 1
        if args.dry_run and len(counts) < 200:
            print(f"  {result}")
        elif not result.startswith(("DRY-", "RENAMED", "FIELDS_PATCHED")):
            print(f"  {result}")

    print("\n[SUMMARY]")
    for k in sorted(counts.keys()):
        print(f"  {k:<20}: {counts[k]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
