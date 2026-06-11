#!/usr/bin/env python3
# analyze_archive_recovery.py
#
# For each MISS verdict in the latest Onyphe engine audit, check if an
# archived rule (patterns/<category>/archive/) exists that targets the same
# product. If yes, the rule may have been archived in error and should be
# reconsidered for re-activation.
#
# Reads:  _alire/tracking/liaprobe-fingerprint-rebuild/ONYPHE_ENGINE_AUDIT_*.json
#         AND a fresh recette-onyphe run with -limit and -src all to identify
#         specific MISS GTProducts (audit JSON has aggregated summary only,
#         per-banner verdicts need re-run).
# Output: ONYPHE_ARCHIVE_RECOVERY_<DATE>.json
#
# Recovery candidates ordered by MISS count per GTProduct so the biggest
# coverage gaps surface first.

import argparse
import json
import re
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

LIAPROBE_DIR = Path("/opt/lia-sec/liaprobe")
PATTERNS_ROOT = LIAPROBE_DIR / "patterns"
RECETTE_BIN = LIAPROBE_DIR / "bin/recette-onyphe"
DEV_DIR = Path("/opt/lia-sec/dev")
DEFAULT_FILE = DEV_DIR / "_alire/temp/onyphe_recette_16641.jsonl"
TRACKING_DIR = DEV_DIR / "_alire/tracking/liaprobe-fingerprint-rebuild"

RUN_DATE = datetime.now(timezone.utc).strftime("%Y-%m-%d")


def normalize(s: str) -> str:
    if not s:
        return ""
    return re.sub(r"[^a-z0-9]", "", s.lower())


def index_archived_rules() -> dict:
    """Map normalized product name -> list of archived rule paths."""
    idx = {}
    for archive_dir in PATTERNS_ROOT.glob("*/archive"):
        for path in archive_dir.glob("*.json"):
            try:
                rule = json.loads(path.read_text())
            except (json.JSONDecodeError, OSError):
                continue
            for k in ("product", "taxonomy_name", "name", "id", "taxonomy_code"):
                v = rule.get(k)
                if isinstance(v, str) and v:
                    n = normalize(v)
                    if n:
                        idx.setdefault(n, []).append({
                            "path": str(path.relative_to(LIAPROBE_DIR)),
                            "product": v,
                            "key_source": k,
                            "enabled": rule.get("enabled", True),
                        })
                        break  # Only register once per archived file
    return idx


def run_engine(onyphe_file: Path, limit: int = 0) -> list:
    cmd = [str(RECETTE_BIN), "-f", str(onyphe_file), "-out", "json", "-src", "all"]
    if limit:
        cmd.extend(["-limit", str(limit)])
    proc = subprocess.run(cmd, cwd=str(LIAPROBE_DIR),
                          capture_output=True, text=True, timeout=600)
    if proc.returncode != 0:
        print(f"[ERROR] engine exit {proc.returncode}: {proc.stderr}", file=sys.stderr)
        sys.exit(2)
    return json.loads(proc.stdout)


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--file", type=str, default=str(DEFAULT_FILE))
    p.add_argument("--limit", type=int, default=0)
    args = p.parse_args()

    onyphe_file = Path(args.file)
    if not onyphe_file.exists():
        p.error(f"File not found: {onyphe_file}")

    print(f"[INFO] Running engine on {onyphe_file.name}...")
    verdicts = run_engine(onyphe_file, args.limit)
    print(f"[INFO] {len(verdicts)} verdicts received")

    # Count MISS by GTProduct (where engine had no detection)
    miss_by_product = Counter()
    wrong_by_product = Counter()
    for v in verdicts:
        if v.get("Verdict") == "MISS":
            miss_by_product[v.get("GTProduct", "")] += 1
        elif v.get("Verdict") == "WRONG":
            wrong_by_product[v.get("GTProduct", "")] += 1

    print(f"\n[INFO] MISS distinct products: {len(miss_by_product)}")
    print(f"[INFO] WRONG distinct products: {len(wrong_by_product)}")

    # Index archived rules
    print("[INFO] Indexing archived rules...")
    archive_idx = index_archived_rules()
    print(f"[INFO] Archive index: {len(archive_idx)} distinct product keys, "
          f"{sum(len(v) for v in archive_idx.values())} files")

    # Cross-reference: which MISS products have an archived rule?
    recovery_candidates = []
    for product, miss_count in miss_by_product.most_common():
        n = normalize(product)
        if n and n in archive_idx:
            recovery_candidates.append({
                "gt_product": product,
                "miss_count": miss_count,
                "wrong_count": wrong_by_product.get(product, 0),
                "archived_rules": archive_idx[n],
            })

    # Also: WRONG products where an archived rule might restore correct detection
    wrong_recoveries = []
    for product, wrong_count in wrong_by_product.most_common():
        n = normalize(product)
        if n and n in archive_idx:
            wrong_recoveries.append({
                "gt_product": product,
                "wrong_count": wrong_count,
                "miss_count": miss_by_product.get(product, 0),
                "archived_rules": archive_idx[n],
            })

    report = {
        "schema": "lia-onyphe-archive-recovery-v1",
        "run_date": RUN_DATE,
        "onyphe_file": str(onyphe_file),
        "total_verdicts": len(verdicts),
        "miss_with_archived_match": len(recovery_candidates),
        "wrong_with_archived_match": len(wrong_recoveries),
        "recovery_candidates_miss": recovery_candidates,
        "recovery_candidates_wrong": wrong_recoveries,
    }
    out = TRACKING_DIR / f"ONYPHE_ARCHIVE_RECOVERY_{RUN_DATE}.json"
    with open(out, "w") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print(f"\n[RECOVERY] {len(recovery_candidates)} MISS products have archived rule(s)")
    print(f"[RECOVERY] {len(wrong_recoveries)} WRONG products have archived rule(s)")
    if recovery_candidates[:10]:
        print("\nTop 10 MISS recovery candidates (most banners missed):")
        for r in recovery_candidates[:10]:
            files = ", ".join(a["path"].rsplit("/", 1)[-1] for a in r["archived_rules"][:3])
            print(f"  {r['gt_product']:30s} miss={r['miss_count']:4d}  "
                  f"archived={files}")
    print(f"\nReport: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
