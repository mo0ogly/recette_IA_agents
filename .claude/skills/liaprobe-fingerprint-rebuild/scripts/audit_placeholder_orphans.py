#!/usr/bin/env python3
"""c37 A41: review 191 placeholder-only aliases for potential reassignment.

For each alias row on a placeholder vendor (lia-declined / lia-meta /
Unknown-O) whose alias_name does NOT match any real vendor, query PG via
pg_trgm similarity() to surface a real vendor that could be the
canonical target. Reports candidates with vscore >= 0.6 for c38+
manual reassignment review.

Output: PLACEHOLDER_ORPHANS_CANDIDATES_<DATE>.json
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEV = Path("/opt/lia-sec/dev")
TRACKING = DEV / "_alire/tracking/liaprobe-fingerprint-rebuild"
NOW = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
RUN_DATE = datetime.now(timezone.utc).strftime("%Y-%m-%d")
DEFAULT_OUT = TRACKING / f"PLACEHOLDER_ORPHANS_CANDIDATES_{RUN_DATE}.json"

PLACEHOLDER_VENDORS = ("lia-declined", "lia-meta", "Unknown-O")


def _systemd_dburl() -> str:
    try:
        out = subprocess.run(
            ["systemctl", "cat", "lia-backend"],
            capture_output=True, text=True, timeout=5,
        ).stdout
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return ""
    for line in out.splitlines():
        if line.startswith("Environment=DATABASE_URL="):
            return line.split("=", 1)[1].split("=", 1)[1]
    return ""


def _query(dburl: str, sql: str, params: dict[str, str] | None = None) -> list[list[str]]:
    if params:
        formatted = sql
        for k, v in params.items():
            safe = v.replace("'", "''")
            formatted = formatted.replace(f":{k}", f"'{safe}'")
        sql = formatted
    res = subprocess.run(
        ["psql", dburl, "-t", "-A", "-F", "\t", "-c", sql],
        capture_output=True, text=True, timeout=15,
    )
    if res.returncode != 0:
        raise RuntimeError(f"psql failed: {res.stderr.strip()}")
    return [line.split("\t") for line in res.stdout.splitlines() if line.strip()]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--threshold", type=float, default=0.6,
                    help="pg_trgm similarity threshold (default 0.6)")
    ap.add_argument("--limit", type=int, default=0,
                    help="limit number of orphans processed (0 = all)")
    args = ap.parse_args()

    dburl = _systemd_dburl()
    if not dburl:
        print("FATAL: no DATABASE_URL", file=sys.stderr)
        return 2

    # Get placeholder IDs
    p_rows = _query(dburl,
        f"SELECT vendor_id, vendor_name FROM vendor "
        f"WHERE vendor_name IN ({','.join(repr(p) for p in PLACEHOLDER_VENDORS)})")
    placeholder_ids = {int(r[0]): r[1] for r in p_rows}
    if not placeholder_ids:
        print("[OK] no placeholder vendors, exit")
        return 0

    ids_csv = ",".join(str(i) for i in placeholder_ids)

    # Get all orphan aliases (alias_name has NO real vendor match)
    orphan_rows = _query(dburl, f"""
SELECT va.id, va.alias_name, va.vendor_id, va.source
FROM vendor_alias va
WHERE va.vendor_id IN ({ids_csv})
  AND NOT EXISTS (
      SELECT 1 FROM vendor real_v
      WHERE LOWER(real_v.vendor_name) = LOWER(va.alias_name)
        AND real_v.vendor_id NOT IN ({ids_csv})
  )
ORDER BY va.alias_name
""")
    print(f"[INFO] orphan placeholder aliases: {len(orphan_rows)}")

    if args.limit > 0:
        orphan_rows = orphan_rows[:args.limit]
        print(f"[INFO] limited to first {args.limit}")

    # For each orphan, run a fuzzy similarity lookup on vendor.vendor_name (excluding placeholders)
    results: list[dict[str, Any]] = []
    candidates_found = 0
    for row in orphan_rows:
        alias_id, alias_name, placeholder_vid, placeholder_src = row
        try:
            fuzzy_rows = _query(dburl, f"""
SELECT vendor_id, vendor_name, similarity(LOWER(vendor_name), LOWER(:alias)) AS score
FROM vendor
WHERE similarity(LOWER(vendor_name), LOWER(:alias)) >= {args.threshold}
  AND vendor_id NOT IN ({ids_csv})
ORDER BY score DESC
LIMIT 3
""", params={"alias": alias_name})
        except RuntimeError as exc:
            results.append({
                "alias_id": int(alias_id),
                "alias_name": alias_name,
                "placeholder_vendor": placeholder_ids.get(int(placeholder_vid)),
                "status": "QUERY_FAIL",
                "error": str(exc),
            })
            continue

        if not fuzzy_rows:
            results.append({
                "alias_id": int(alias_id),
                "alias_name": alias_name,
                "placeholder_vendor": placeholder_ids.get(int(placeholder_vid)),
                "status": "NO_CANDIDATE",
            })
            continue

        candidates = [{"vendor_id": int(r[0]), "vendor_name": r[1], "vscore": round(float(r[2]), 3)} for r in fuzzy_rows]
        results.append({
            "alias_id": int(alias_id),
            "alias_name": alias_name,
            "placeholder_vendor": placeholder_ids.get(int(placeholder_vid)),
            "status": "CANDIDATES",
            "candidates": candidates,
            "top_score": candidates[0]["vscore"],
        })
        candidates_found += 1

    artifact = {
        "schema": "lia-placeholder-orphan-candidates-v1",
        "generated_at": NOW,
        "threshold": args.threshold,
        "placeholder_vendors": placeholder_ids,
        "summary": {
            "total_orphans_scanned": len(results),
            "with_candidates": candidates_found,
            "no_candidate": sum(1 for r in results if r["status"] == "NO_CANDIDATE"),
            "query_fail": sum(1 for r in results if r["status"] == "QUERY_FAIL"),
        },
        "results": results,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(artifact, indent=2, ensure_ascii=False), encoding="utf-8")

    print()
    print(f"[SUMMARY] orphans={len(results)} with_candidates={candidates_found} no_candidate={artifact['summary']['no_candidate']}")
    if candidates_found > 0:
        print()
        print("[TOP CANDIDATES] (vscore >= threshold)")
        sorted_results = sorted(
            [r for r in results if r["status"] == "CANDIDATES"],
            key=lambda r: -r["top_score"],
        )
        for r in sorted_results[:30]:
            top = r["candidates"][0]
            print(f"  alias={r['alias_name']!r:35} -> {top['vendor_name']!r:30} vscore={top['vscore']}")
    print(f"\noutput: {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
