#!/usr/bin/env python3
"""c36 A35: global vendor_alias collision audit.

Scans lia_scan vendor_alias table for shadow aliases: rows whose
LOWER(alias_name) equals a real vendor's LOWER(vendor_name) but whose
vendor_id points to a placeholder (lia-declined, etc.). These shadows
silently break alias_exact resolution by hijacking the alias_name UNIQUE
slot.

Output: AUDIT_ALIAS_COLLISIONS_<DATE>.json with per-shadow record + summary.

Exit code 1 if any shadow found, 0 if clean.
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
DEFAULT_OUT = TRACKING / f"AUDIT_ALIAS_COLLISIONS_{RUN_DATE}.json"

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


def _query(dburl: str, sql: str) -> list[list[str]]:
    res = subprocess.run(
        ["psql", dburl, "-t", "-A", "-F", "\t", "-c", sql],
        capture_output=True, text=True, timeout=60,
    )
    if res.returncode != 0:
        raise RuntimeError(f"psql failed: {res.stderr.strip()}")
    return [line.split("\t") for line in res.stdout.splitlines() if line.strip()]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args()

    dburl = _systemd_dburl()
    if not dburl:
        print("FATAL: no DATABASE_URL", file=sys.stderr)
        return 2

    # Get placeholder vendor IDs
    placeholders_sql = (
        "SELECT vendor_id, vendor_name FROM vendor "
        f"WHERE vendor_name IN ({','.join(repr(p) for p in PLACEHOLDER_VENDORS)})"
    )
    rows = _query(dburl, placeholders_sql)
    placeholder_ids = {int(r[0]): r[1] for r in rows}
    print(f"[INFO] placeholder vendors: {placeholder_ids}")

    if not placeholder_ids:
        print("[OK] no placeholder vendors in DB, no shadows possible")
        return 0

    # Find aliases on placeholders whose LOWER(alias_name) matches a real vendor's LOWER(vendor_name)
    ids_csv = ",".join(str(i) for i in placeholder_ids)
    shadow_sql = f"""
SELECT va.id AS alias_id, va.alias_name, va.vendor_id AS placeholder_vid,
       va.source AS placeholder_source,
       real_v.vendor_id AS real_vid, real_v.vendor_name AS real_vendor_name,
       real_v.seed_source AS real_seed_source
FROM vendor_alias va
JOIN vendor real_v ON LOWER(real_v.vendor_name) = LOWER(va.alias_name)
WHERE va.vendor_id IN ({ids_csv})
  AND real_v.vendor_id NOT IN ({ids_csv})
ORDER BY real_v.vendor_name
"""
    shadow_rows = _query(dburl, shadow_sql)
    print(f"[INFO] shadow aliases found: {len(shadow_rows)}")

    shadows: list[dict[str, Any]] = []
    for r in shadow_rows:
        shadows.append({
            "alias_id": int(r[0]),
            "alias_name": r[1],
            "placeholder_vendor_id": int(r[2]),
            "placeholder_vendor_name": placeholder_ids.get(int(r[2]), "?"),
            "placeholder_alias_source": r[3],
            "real_vendor_id": int(r[4]),
            "real_vendor_name": r[5],
            "real_vendor_seed_source": r[6],
        })

    # Also find aliases on placeholders whose alias_name has no real vendor match
    # (still on placeholder by design -- not shadow but orphan-on-placeholder).
    orphan_sql = f"""
SELECT va.id, va.alias_name, va.vendor_id, va.source
FROM vendor_alias va
WHERE va.vendor_id IN ({ids_csv})
  AND NOT EXISTS (
      SELECT 1 FROM vendor real_v
      WHERE LOWER(real_v.vendor_name) = LOWER(va.alias_name)
        AND real_v.vendor_id NOT IN ({ids_csv})
  )
"""
    orphan_rows = _query(dburl, orphan_sql)
    print(f"[INFO] placeholder aliases with no real vendor match: {len(orphan_rows)} (expected, by design)")

    artifact = {
        "schema": "lia-audit-alias-collisions-v1",
        "generated_at": NOW,
        "placeholder_vendors": placeholder_ids,
        "summary": {
            "shadow_aliases": len(shadows),
            "placeholder_aliases_orphan": len(orphan_rows),
        },
        "shadows": shadows,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(artifact, indent=2, ensure_ascii=False), encoding="utf-8")

    print()
    print(f"[SUMMARY] shadow_aliases={len(shadows)} placeholder_orphans={len(orphan_rows)}")
    if shadows:
        print()
        print("[SHADOWS] (LOWER(alias_name) matches a real vendor but row points to placeholder):")
        for s in shadows[:20]:
            print(f"  alias={s['alias_name']!r:30} placeholder={s['placeholder_vendor_name']} (vid={s['placeholder_vendor_id']}) shadows real={s['real_vendor_name']} (vid={s['real_vendor_id']})")
        print()
        print("Action: build a REASSIGN migration similar to migrations 161+162 c35.")
    else:
        print("[OK] no shadow aliases. DB is clean.")
    print(f"\noutput: {args.out}")
    return 1 if shadows else 0


if __name__ == "__main__":
    sys.exit(main())
