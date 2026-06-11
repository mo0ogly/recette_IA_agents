#!/usr/bin/env python3
# unarchive_merge_losers.py
#
# c27 ST2: revert MERGE -> SPLIT for specific losers whose unique
# detection coverage was NOT recovered by matcher absorption in c26.
#
# audit_merge_coverage.py identified 4 losers with non-recoverable
# detection (16 banners lost):
#   - TWISTEDWEB.json   -> Twistedmatrix_Twisted_Banner.json (+10 recovered)
#   - CITRXGW.json      -> Citrix_Gateway_Variant.json       (+3 recovered)
#   - LOTDOM.json       -> IBM_Lotus_Domino_Variant.json     (+2 recovered)
#   - PVEWEB.json       -> Proxmox_Virtual_Environment_Web.json (+1 recovered)
#
# Action: git mv from patterns/lia/_archive_c26/<loser>.json back to
# patterns/lia/<unique_name>.json + update source.file + audit block.

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

LIAPROBE_DIR = Path("/opt/lia-sec/liaprobe")
DEV_DIR = Path("/opt/lia-sec/dev")
BACKUP_DIR = DEV_DIR / "_alire/temp/apex/apex-20260513-c27/unarchive_backup"
ARCHIVE_SUBDIR = "_archive_c26"
NOW_ISO = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
RUN_DATE = datetime.now(timezone.utc).strftime("%Y-%m-%d")
PASS_ID = f"{RUN_DATE}_apex_c27_unarchive_merge_losers"

# Hardcoded list per c26 coverage audit results
UNARCHIVES: list[dict] = [
    {
        "archived_basename": "TWISTEDWEB.json",
        "target_basename": "Twistedmatrix_Twisted_Banner.json",
        "rationale": "Banner-matcher-only variant. Pre-c26 detected 10 unique TwistedWeb banners on non-standard ports (8085, 8889) that the probe-path winner does not catch. Co-exists with Twistedmatrix_Twisted.json (probe-driven variant).",
        "recovered_count": 10,
        "sub_product_label": "Twisted Web (header-banner)",
    },
    {
        "archived_basename": "CITRXGW.json",
        "target_basename": "Citrix_Gateway_Variant.json",
        "rationale": "Pre-c26 detected 3 unique Citrix Gateway banners on non-standard ports (81, 888, 8888) with 'Server: Citrix-3.2.x.x' header that the merged winner does not catch. Co-exists with Citrix_Gateway.json.",
        "recovered_count": 3,
        "sub_product_label": "Citrix Gateway (non-standard ports)",
    },
    {
        "archived_basename": "LOTDOM.json",
        "target_basename": "IBM_Lotus_Domino_Variant.json",
        "rationale": "Originally archived as duplicate of LDOMINO, but coverage audit found 2 unique detections on ports 113 + 8085 that the merged winner does not catch. Co-exists with IBM_Lotus_Domino.json.",
        "recovered_count": 2,
        "sub_product_label": "IBM Lotus Domino (alt ports)",
    },
    {
        "archived_basename": "PVEWEB.json",
        "target_basename": "Proxmox_Virtual_Environment_Web.json",
        "rationale": "Pre-c26 detected 1 unique Proxmox VE banner on port 3128 (proxy port) that the merged winner does not catch. Co-exists with Proxmox_Virtual_Environment.json.",
        "recovered_count": 1,
        "sub_product_label": "Proxmox VE (web UI)",
    },
]


def _backup(p: Path) -> None:
    if not p.exists():
        return
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    target = BACKUP_DIR / p.name
    if not target.exists():
        shutil.copy2(p, target)


def _git_mv(src: Path, dst: Path) -> tuple[bool, str]:
    if dst.exists():
        return False, f"DEST_EXISTS {dst.name}"
    cmd = ["git", "-C", str(LIAPROBE_DIR), "mv",
           str(src.relative_to(LIAPROBE_DIR)), str(dst.relative_to(LIAPROBE_DIR))]
    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True, timeout=10)
    except subprocess.CalledProcessError as exc:
        return False, f"GIT_MV_FAIL {src.name}: {exc.stderr.strip()}"
    return True, ""


def unarchive_one(decision: dict, dry: bool) -> str:
    archive_src = LIAPROBE_DIR / "patterns/lia" / ARCHIVE_SUBDIR / decision["archived_basename"]
    target = LIAPROBE_DIR / "patterns/lia" / decision["target_basename"]

    if not archive_src.exists():
        return f"MISSING_SOURCE {archive_src}"
    if target.exists():
        return f"TARGET_EXISTS {target.name}"

    if dry:
        return f"DRY-UNARCHIVE {decision['archived_basename']} -> {decision['target_basename']} (+{decision['recovered_count']})"

    _backup(archive_src)
    ok, err = _git_mv(archive_src, target)
    if not ok:
        return err

    try:
        rule = json.loads(target.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        return f"READ_FAIL_AFTER_MV {target.name}: {exc}"

    # Update source.file to new basename
    src_obj = rule.setdefault("source", {})
    src_obj["file"] = decision["target_basename"]

    # Audit block
    auth = rule.setdefault("_lia_independent_authoring", {})
    auth["collision_unarchive_c27"] = {
        "date": NOW_ISO,
        "action": "MERGE_REVERT_TO_SPLIT",
        "from_archive": f"{ARCHIVE_SUBDIR}/{decision['archived_basename']}",
        "to_basename": decision["target_basename"],
        "sub_product_label": decision["sub_product_label"],
        "rationale": decision["rationale"],
        "recovered_count_from_audit": decision["recovered_count"],
        "audit_source": "MERGE_COVERAGE_AUDIT_2026-05-13.json (c27 ST1)",
        "marked_by": PASS_ID,
    }

    # If the original c26 archive audit said "loser_archived", upgrade it
    # to reflect the revert (history preserved, not deleted).
    triage = auth.get("collision_triage_c26")
    if triage and triage.get("role") == "loser_archived":
        triage["revert_note_c27"] = (
            "Initially archived c26 as MERGE loser. Coverage audit c27 "
            "found unique detection (see collision_unarchive_c27)."
        )

    target.write_text(json.dumps(rule, indent=2, ensure_ascii=False) + "\n",
                      encoding="utf-8")
    return f"UNARCHIVED {decision['archived_basename']} -> {decision['target_basename']}"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    if not args.apply and not args.dry_run:
        ap.error("Specify --apply or --dry-run")

    print(f"[INFO] unarchive entries  : {len(UNARCHIVES)}")
    print(f"[INFO] mode               : {'DRY-RUN' if args.dry_run else 'APPLY'}")
    print(f"[INFO] backup dir         : {BACKUP_DIR}")
    print()

    for d in UNARCHIVES:
        result = unarchive_one(d, args.dry_run)
        print(f"  {result}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
