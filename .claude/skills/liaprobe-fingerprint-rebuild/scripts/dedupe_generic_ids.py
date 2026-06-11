#!/usr/bin/env python3
# dedupe_generic_ids.py
#
# For each duplicate id cluster in active corpus, rename the `id` field of
# each rule to be unique: new_id = "<old_id>_<filename_stem.lower>".
# Preserves audit trail in _lia_independent_authoring.dedupe_rename block.
#
# Targets : duplicate clusters from audit_duplicate_ids.py report.
# Excludes : rules already enriched with /liaprobe-rule-enrich
#            _meta_enrichment.canonical_vendor (they get product-specific id
#            from canonical resolution, separate workflow).
#
# Usage:
#   python3 dedupe_generic_ids.py --dry-run --min-cluster 10
#   python3 dedupe_generic_ids.py --apply --min-cluster 10

import argparse
import json
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

LIAPROBE_DIR = Path("/opt/lia-sec/liaprobe")
DEV_DIR = Path("/opt/lia-sec/dev")
TRACKING_DIR = DEV_DIR / "_alire/tracking/liaprobe-fingerprint-rebuild"
REPORT = TRACKING_DIR / "ID_DUPLICATES_2026-05-13.json"
BACKUP_DIR = DEV_DIR / "_alire/temp/apex/apex-20260513-c10/dedupe_backup"

NOW_ISO = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
PASS_ID = "2026-05-13_apex_c11_dedupe"

# Generic vendor-only ids OR known multi-file clusters with silent winner
# masking (c13 finding: net_snmp had 241 FP because 1 of 3 was disabled).
GENERIC_PATTERNS = {
    # Pure vendor-only
    "unknown", "cisco", "microsoft", "hp", "hpe", "python", "dlink",
    "ibm", "sun", "zyxel", "netgear", "kyocera", "canon", "nortel",
    "siemens", "samsung", "lg", "lenovo", "asus", "dell", "oracle",
    "google", "amazon", "apple", "intel", "broadcom", "qualcomm",
    "vmware", "redhat", "suse", "ubuntu", "debian", "3com", "huawei",
    "lexmark", "xerox", "linksys", "konicaminolta",
    # Multi-file vendor-product clusters (silent winner detected)
    "net_snmp", "apache_http_server", "microsoft_sql_server",
    "microsoft_exchange_server", "microsoft_iis",
    "microsoft_internet_information_services",
    "ibm_lotus_domino", "cmu_cyrus_imap_server", "checkpoint_firewall_1",
    "php", "hp_integrated_lights_out", "mailenable",
}


def make_unique_id(old_id: str, stem: str) -> str:
    """new_id = <old_id>_<stem.lower>, sanitized + capped at 80 chars."""
    suffix = re.sub(r"[^a-z0-9_]", "_", stem.lower())
    new_id = f"{old_id}_{suffix}"[:80]
    return new_id.rstrip("_")


def rename_one(file_info: dict, cluster_id: str, dry: bool) -> str:
    path = LIAPROBE_DIR / file_info["path"]
    try:
        rule = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError) as e:
        return f"ERROR_READ {path.name}: {e}"

    current_id = (rule.get("id") or "").lower()
    if current_id != cluster_id:
        return f"SKIP_DIVERGENT {path.name}: id={current_id!r} != cluster {cluster_id!r}"

    new_id = make_unique_id(cluster_id, path.stem)
    if new_id == current_id:
        return f"SKIP_NO_CHANGE {path.name}"

    # Backup
    if not dry:
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        bp = BACKUP_DIR / path.name
        if not bp.exists():
            shutil.copy2(path, bp)

    rule["id"] = new_id
    auth = rule.setdefault("_lia_independent_authoring", {})
    auth["dedupe_rename"] = {
        "date": NOW_ISO,
        "from_id": current_id,
        "to_id": new_id,
        "cluster_size": file_info.get("cluster_size", "?"),
        "marked_by": f"dedupe_generic_ids.py {PASS_ID}",
    }

    if dry:
        return f"DRY-RUN {path.name}: id {current_id!r} -> {new_id!r}"
    path.write_text(json.dumps(rule, indent=2, ensure_ascii=False) + "\n")
    return f"RENAMED {path.name}: id -> {new_id!r}"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--apply", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--min-cluster", type=int, default=10,
                   help="Only process clusters with N+ files (default 10)")
    p.add_argument("--generic-only", action="store_true", default=True,
                   help="Only dedupe vendor-only generic ids (default True)")
    p.add_argument("--all-duplicates", action="store_true",
                   help="Process every cluster with file_count>=min_cluster regardless of GENERIC_PATTERNS. C15 finding: cross-subdir duplicates (e.g. gfi_kerio_connect in lia/ + banner-signatures/) slipped through generic-only gate.")
    args = p.parse_args()
    if not args.apply and not args.dry_run:
        p.error("Specify --apply or --dry-run")
    # --all-duplicates overrides --generic-only
    if args.all_duplicates:
        args.generic_only = False

    report = json.loads(REPORT.read_text())
    candidates = []
    for c in report["clusters"]:
        if c["file_count"] < args.min_cluster:
            continue
        if args.generic_only and c["id"] not in GENERIC_PATTERNS:
            continue
        candidates.append(c)

    print(f"[INFO] {len(candidates)} clusters match (min-cluster={args.min_cluster}, "
          f"generic-only={args.generic_only})")
    total_files = sum(c["file_count"] for c in candidates)
    print(f"[INFO] {total_files} files to rename")

    if not candidates:
        return 0

    for c in candidates:
        print(f"  cluster '{c['id']}' x{c['file_count']}")

    if args.dry_run:
        print("\n[DRY-RUN] Sample renames (first 3 per cluster):")

    actions_summary = {"RENAMED": 0, "DRY-RUN": 0, "SKIP": 0, "ERROR": 0}
    for c in candidates:
        files_to_show = 3 if args.dry_run else len(c["files"])
        for i, f in enumerate(c["files"]):
            f["cluster_size"] = c["file_count"]
            result = rename_one(f, c["id"], args.dry_run)
            key = result.split()[0].split("_")[0]
            actions_summary[key] = actions_summary.get(key, 0) + 1
            if args.dry_run and i < files_to_show:
                print(f"  {result}")

    print(f"\n[SUMMARY]")
    for k, v in actions_summary.items():
        if v:
            print(f"  {k}: {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
