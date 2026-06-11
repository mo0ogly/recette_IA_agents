#!/usr/bin/env python3
# revert_field_patches.py
#
# Revert c25 vendor / product field patches while preserving:
#   - git mv filename renames (already done, history preserved)
#   - source.file body field (now matches new basename)
#   - _lia_independent_authoring.filename_rename_c25 audit block
#     (entries removed: vendor + product; entry kept: source.file)
#
# Rationale: c25 ST3 broke 1658 onyphe verdicts (CORRECT -> WRONG) because
# the engine reports rule.product as the detected_product label. The Onyphe
# ground-truth still uses human-friendly product strings ("Apache HTTP
# Server"), but c25 had normalized them to PG canonical form ("Http_Server").
# The canonical values stay accessible via _meta_enrichment.canonical_vendor
# (their proper home), not on top-level vendor / product.
#
# Source of truth for revert = backup files in BACKUP_DIR (taken just
# before apply_renames.py touched them).
#
# Usage:
#   python3 revert_field_patches.py --dry-run
#   python3 revert_field_patches.py --apply

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

LIAPROBE_DIR = Path("/opt/lia-sec/liaprobe")
DEV_DIR = Path("/opt/lia-sec/dev")
BACKUP_DIR = DEV_DIR / "_alire/temp/apex/apex-20260513-c25/rename_backup"
CYCLE_AUDIT_KEY = "filename_rename_c25"


def _find_current_path(original_basename: str, renames_index: dict[str, str]) -> Path | None:
    new_basename = renames_index.get(original_basename, original_basename)
    candidate = LIAPROBE_DIR / "patterns" / "lia" / new_basename
    if candidate.exists():
        return candidate
    return None


def _build_renames_index() -> dict[str, str]:
    # Walk patterns/lia/*.json, find rules with c25 audit block, map
    # from_basename -> current basename on disk.
    idx: dict[str, str] = {}
    for p in (LIAPROBE_DIR / "patterns" / "lia").glob("*.json"):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        audit = (data.get("_lia_independent_authoring") or {}).get(CYCLE_AUDIT_KEY)
        if not audit:
            continue
        from_b = audit.get("from_basename")
        if from_b:
            idx[from_b] = p.name
    return idx


def revert_one(backup_path: Path, renames_index: dict[str, str], dry: bool) -> str:
    original_basename = backup_path.name
    current_path = _find_current_path(original_basename, renames_index)
    if current_path is None:
        return f"MISSING_CURRENT {original_basename}"

    try:
        current = json.loads(current_path.read_text(encoding="utf-8"))
        original = json.loads(backup_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return f"READ_FAIL {original_basename}: {exc}"

    changed: list[str] = []

    # Restore vendor / product to their pre-c25 values
    for field in ("vendor", "product"):
        orig_val = original.get(field)
        cur_val = current.get(field)
        if orig_val != cur_val:
            if orig_val is None:
                current.pop(field, None)
            else:
                current[field] = orig_val
            changed.append(field)

    # source.file MUST point to current filename (new basename)
    src_obj = current.setdefault("source", {})
    if src_obj.get("file") != current_path.name:
        src_obj["file"] = current_path.name
        changed.append("source.file_realign")

    # Trim audit block: drop vendor + product from field_updates_applied,
    # keep source.file. Add note about revert.
    auth = current.get("_lia_independent_authoring") or {}
    audit = auth.get(CYCLE_AUDIT_KEY)
    if audit and isinstance(audit, dict):
        applied = audit.get("field_updates_applied") or {}
        for field in ("vendor", "product"):
            if field in applied:
                applied.pop(field, None)
                changed.append(f"audit_drop_{field}")
        audit["field_updates_applied"] = applied
        audit["fields_reverted_note"] = (
            "vendor + product field patches reverted post-onyphe regression "
            "(c25 ST3 found 1658 verdict CORRECT->WRONG). Canonical values "
            "remain in _meta_enrichment.canonical_vendor. Filename rename "
            "preserved (git mv intact)."
        )

    if not changed:
        return f"NO_CHANGE {original_basename}"

    if dry:
        return f"DRY-REVERT {current_path.name} ({','.join(changed)})"

    current_path.write_text(json.dumps(current, indent=2, ensure_ascii=False) + "\n",
                            encoding="utf-8")
    return f"REVERTED {current_path.name} ({','.join(changed)})"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    if not args.apply and not args.dry_run:
        ap.error("Specify --apply or --dry-run")
    if not BACKUP_DIR.is_dir():
        print(f"FATAL: backup dir not found: {BACKUP_DIR}", file=sys.stderr)
        return 2

    renames_index = _build_renames_index()
    print(f"[INFO] backup files     : {sum(1 for _ in BACKUP_DIR.glob('*.json'))}")
    print(f"[INFO] renames in index : {len(renames_index)}")
    print(f"[INFO] mode             : {'DRY-RUN' if args.dry_run else 'APPLY'}")
    print()

    counts: dict[str, int] = {}
    for bk in sorted(BACKUP_DIR.glob("*.json")):
        result = revert_one(bk, renames_index, args.dry_run)
        key = result.split(" ", 1)[0]
        counts[key] = counts.get(key, 0) + 1

    print("\n[SUMMARY]")
    for k in sorted(counts.keys()):
        print(f"  {k:<24}: {counts[k]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
