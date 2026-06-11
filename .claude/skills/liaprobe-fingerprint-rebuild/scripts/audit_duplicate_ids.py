#!/usr/bin/env python3
# audit_duplicate_ids.py
#
# Scan all rule files in patterns/ (active dirs, not archive/), group by
# rule.id field. Report clusters where 2+ rules share the same id.
#
# For each duplicate cluster, optionally cross-reference Onyphe engine
# audit (ONYPHE_RULE_EVIDENCE_ENGINE) to identify the "winning" rule.
#
# Output:
#   ID_DUPLICATES_<DATE>.json : full report
#   Optionally proposes id renames: --propose-renames
#
# Usage:
#   python3 audit_duplicate_ids.py
#   python3 audit_duplicate_ids.py --propose-renames
#   python3 audit_duplicate_ids.py --min-cluster 3   # only id used in 3+ files

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

LIAPROBE_DIR = Path("/opt/lia-sec/liaprobe")
PATTERNS_ROOT = LIAPROBE_DIR / "patterns"
DEV_DIR = Path("/opt/lia-sec/dev")
TRACKING_DIR = DEV_DIR / "_alire/tracking/liaprobe-fingerprint-rebuild"
EVIDENCE_REPORT = TRACKING_DIR / "ONYPHE_RULE_EVIDENCE_ENGINE_2026-05-12.json"

RUN_DATE = datetime.now(timezone.utc).strftime("%Y-%m-%d")


def load_evidence_map() -> dict:
    """Map pattern_id -> tp_count from Onyphe evidence report."""
    if not EVIDENCE_REPORT.exists():
        return {}
    r = json.loads(EVIDENCE_REPORT.read_text())
    evid = r.get("evidence", {})
    return {pid.lower(): e.get("tp_count", 0) for pid, e in evid.items()}


def scan_corpus() -> dict:
    """Group rule files by id (lowercase). Skip archive/ + todo/ + nested
    subdirs (loader only loads .json directly under each patterns/<cat>/, not
    sub-subdirectories per pkg/fingerprint/loader.go:99-101)."""
    by_id = defaultdict(list)
    for subdir in PATTERNS_ROOT.iterdir():
        if not subdir.is_dir():
            continue
        # Only direct children of patterns/<cat>/ are loaded by engine
        for path in subdir.glob("*.json"):
            try:
                rule = json.loads(path.read_text())
            except (json.JSONDecodeError, OSError):
                continue
            pid = (rule.get("id") or "").lower()
            if not pid:
                continue
            by_id[pid].append({
                "path": str(path.relative_to(LIAPROBE_DIR)),
                "stem": path.stem,
                "product": rule.get("product", ""),
                "taxonomy_name": rule.get("taxonomy_name", ""),
                "vendor": rule.get("vendor", ""),
                "enabled": rule.get("enabled", True),
            })
    return dict(by_id)


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--min-cluster", type=int, default=2,
                   help="Only report clusters with N+ files sharing same id (default 2)")
    p.add_argument("--propose-renames", action="store_true",
                   help="For each cluster, identify the winning rule (highest TP) "
                        "and propose rename for the losers")
    p.add_argument("--top", type=int, default=20,
                   help="Print top N clusters to stdout (default 20)")
    args = p.parse_args()

    print("[INFO] Scanning patterns/ corpus (excluding archive/)...")
    by_id = scan_corpus()
    print(f"[INFO] {len(by_id)} unique ids across all files")

    evidence = load_evidence_map() if args.propose_renames else {}
    if evidence:
        print(f"[INFO] Loaded {len(evidence)} pattern_id TP counts from Onyphe evidence")

    clusters = [(pid, files) for pid, files in by_id.items()
                if len(files) >= args.min_cluster]
    clusters.sort(key=lambda c: -len(c[1]))

    rename_proposals = []
    if args.propose_renames:
        for pid, files in clusters:
            tp = evidence.get(pid, 0)
            # Winner = file in cluster with most-likely highest TP (heuristic: enabled + most specific name)
            # Real winner determined by engine confidence_delta priority -- we approximate
            winner = max(files, key=lambda f: (
                f["enabled"],
                len(f["product"] or ""),  # more specific product = likely intended target
                -len(f["stem"]),  # shorter stem = older/canonical
            ))
            for f in files:
                if f["path"] == winner["path"]:
                    continue
                # Suggest suffix based on filename stem or vendor
                vendor_part = (f["vendor"] or "lia").lower().replace(" ", "_")
                new_id = f"{pid}_{vendor_part}_{f['stem'].lower()}"[:64]
                rename_proposals.append({
                    "cluster_id": pid,
                    "winner_path": winner["path"],
                    "winner_product": winner["product"],
                    "rename_path": f["path"],
                    "from_id": pid,
                    "to_id": new_id,
                    "rename_product": f["product"],
                    "onyphe_tp_for_cluster": tp,
                })

    report = {
        "schema": "lia-id-duplicates-v1",
        "run_date": RUN_DATE,
        "total_unique_ids": len(by_id),
        "duplicate_clusters_count": len(clusters),
        "clusters": [
            {
                "id": pid,
                "file_count": len(files),
                "onyphe_tp": evidence.get(pid, 0),
                "files": files,
            }
            for pid, files in clusters
        ],
        "rename_proposals": rename_proposals,
    }
    out = TRACKING_DIR / f"ID_DUPLICATES_{RUN_DATE}.json"
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False))

    print(f"\n[STATS]")
    print(f"  Duplicate clusters (>= {args.min_cluster} files) : {len(clusters)}")
    print(f"  Total files in duplicate clusters : {sum(len(c[1]) for c in clusters)}")

    print(f"\nTOP {args.top} clusters by size :")
    print(f"  {'id':35s} {'count':>6s}  {'tp':>5s}  sample files")
    for pid, files in clusters[:args.top]:
        tp = evidence.get(pid, 0)
        sample = ", ".join(f["stem"] for f in files[:3])
        print(f"  {pid:35s} {len(files):>6d}  {tp:>5d}  {sample[:60]}")

    if args.propose_renames:
        print(f"\n[RENAMES] {len(rename_proposals)} proposals generated")

    print(f"\nReport: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
