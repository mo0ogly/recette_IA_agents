#!/usr/bin/env python3
# merge_onyphe_sources.py
#
# Aggregate all Onyphe data sources in _alire/temp into a single deduplicated
# recette JSONL, ready for `bin/recette-onyphe` engine audit.
#
# Inputs:
#   *_recette*.jsonl     -> already in recette format (port, protocol, banner, ground_truth)
#   *banners_samples*.jsonl -> raw Onyphe export (flat: ip, port, product, data) -> convert
#
# Dedup key: sha256(ip|port|protocol|product|banner)
#
# Output:
#   _alire/temp/onyphe_merged_unique_<DATE>.jsonl
#
# Usage:
#   python3 merge_onyphe_sources.py
#   python3 merge_onyphe_sources.py --out /custom/path.jsonl

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

DEV_DIR = Path("/opt/lia-sec/dev")
TEMP_DIR = DEV_DIR / "_alire/temp"
TRACKING_DIR = DEV_DIR / "_alire/tracking/liaprobe-fingerprint-rebuild"

RUN_DATE = datetime.now(timezone.utc).strftime("%Y-%m-%d")


def dedup_key(entry: dict) -> str:
    """Stable dedup key on (ip, port, protocol, product, banner)."""
    gt = entry.get("ground_truth", {}) or {}
    parts = [
        str(gt.get("ip", "")),
        str(entry.get("port") or gt.get("port", "")),
        str(entry.get("protocol", "")),
        str(gt.get("product", "")),
        (entry.get("banner") or "")[:512],  # cap banner for hash speed
    ]
    return hashlib.sha256("|".join(parts).encode("utf-8", errors="replace")).hexdigest()


def is_recette_entry(d: dict) -> bool:
    """True if entry already in recette format."""
    return "banner" in d and "ground_truth" in d


def convert_sample_entry(d: dict) -> dict | None:
    """Convert a banners_samples entry (flat) to recette format. Skip if missing data/product."""
    product = (d.get("product") or "").strip()
    banner = d.get("data")
    if not product or not banner:
        return None
    return {
        "port": d.get("port", 0),
        "protocol": d.get("protocol", ""),
        "banner": banner,
        "state": "open",
        "ground_truth": {
            "ip": d.get("ip", ""),
            "port": d.get("port", 0),
            "product": product,
            "version": d.get("productversion", ""),
            "os": d.get("os", ""),
            "device_class": d.get("device_class", ""),
            "cpe": d.get("cpe", []),
            "cve": d.get("cve", []),
            "country": d.get("country", ""),
            "asn": d.get("asn", 0),
            "hostname": d.get("hostname", []),
        },
    }


def discover_sources() -> list:
    """List all candidate Onyphe files in temp dir, ordered by name."""
    files = []
    for p in sorted(TEMP_DIR.glob("*onyphe*.jsonl")):
        files.append(p)
    for p in sorted(TEMP_DIR.glob("*onyphe*banners_samples*.jsonl")):
        # Already caught above if pattern matches; sorted/set later
        if p not in files:
            files.append(p)
    return files


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--out", type=str,
                   default=str(TEMP_DIR / f"onyphe_merged_unique_{RUN_DATE}.jsonl"))
    p.add_argument("--report", type=str,
                   default=str(TRACKING_DIR / f"ONYPHE_MERGE_REPORT_{RUN_DATE}.json"))
    p.add_argument("--skip-spip", action="store_true",
                   help="Filter out multi-port concat artifacts containing "
                        "'Composed-By: SPIP' marker (c12 finding)")
    p.add_argument("--max-banner-size", type=int, default=0,
                   help="Skip banners exceeding N bytes (0 = no limit)")
    args = p.parse_args()

    sources = discover_sources()
    print(f"[INFO] {len(sources)} Onyphe source files discovered:")
    for s in sources:
        print(f"  - {s.name}")

    seen = set()
    per_source = {}
    out_count = 0
    skipped_convert = 0
    skipped_spip = 0
    skipped_size = 0

    out_path = Path(args.out)
    with open(out_path, "w") as fout:
        for src in sources:
            src_name = src.name
            src_stats = {"read": 0, "kept": 0, "dup": 0, "skipped": 0}
            with open(src, encoding="utf-8") as fin:
                for line in fin:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        d = json.loads(line)
                    except json.JSONDecodeError:
                        src_stats["skipped"] += 1
                        continue
                    src_stats["read"] += 1
                    if is_recette_entry(d):
                        entry = d
                    else:
                        entry = convert_sample_entry(d)
                        if entry is None:
                            src_stats["skipped"] += 1
                            skipped_convert += 1
                            continue
                    banner = entry.get("banner") or ""
                    if args.skip_spip and "Composed-By: SPIP" in banner:
                        src_stats["skipped"] += 1
                        skipped_spip += 1
                        continue
                    if args.max_banner_size and len(banner) > args.max_banner_size:
                        src_stats["skipped"] += 1
                        skipped_size += 1
                        continue
                    k = dedup_key(entry)
                    if k in seen:
                        src_stats["dup"] += 1
                        continue
                    seen.add(k)
                    fout.write(json.dumps(entry, ensure_ascii=False) + "\n")
                    src_stats["kept"] += 1
                    out_count += 1
            per_source[src_name] = src_stats
            print(f"  {src_name}: read={src_stats['read']} kept={src_stats['kept']} "
                  f"dup={src_stats['dup']} skipped={src_stats['skipped']}")

    report = {
        "schema": "lia-onyphe-merge-v1",
        "run_date": RUN_DATE,
        "sources": [str(s) for s in sources],
        "per_source_stats": per_source,
        "total_unique_kept": out_count,
        "convert_skipped_no_product_or_banner": skipped_convert,
        "filter_skipped_spip_concat": skipped_spip,
        "filter_skipped_oversize": skipped_size,
        "filters_applied": {
            "skip_spip": args.skip_spip,
            "max_banner_size": args.max_banner_size,
        },
        "output_file": str(out_path),
    }
    Path(args.report).write_text(json.dumps(report, indent=2, ensure_ascii=False))

    print(f"\n[SUMMARY] Total unique entries: {out_count}")
    print(f"Output:  {out_path}")
    print(f"Report:  {args.report}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
