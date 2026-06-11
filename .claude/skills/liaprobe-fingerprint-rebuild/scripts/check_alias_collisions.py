#!/usr/bin/env python3
"""c36 A37: pre-migration alias collision gate.

Parses a vendor_alias migration SQL file, extracts alias_name candidates,
and queries lia_scan vendor_alias for pre-existing entries that would
cause ON CONFLICT silent drops.

Usage:
    python3 check_alias_collisions.py path/to/migration.sql

Exit codes:
    0 = no collisions found, safe to apply
    1 = collisions found (report printed)
    2 = SQL parse failure or DB error
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path


ALIAS_PATTERN = re.compile(
    r"INSERT\s+INTO\s+vendor_alias\s*\([^)]*alias_name[^)]*\)\s*"
    r"SELECT\s+[^,]+,\s*(?:E)?\'([^']+)\'",
    re.IGNORECASE,
)


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
        capture_output=True, text=True, timeout=15,
    )
    if res.returncode != 0:
        raise RuntimeError(f"psql failed: {res.stderr.strip()}")
    return [line.split("\t") for line in res.stdout.splitlines() if line.strip()]


def extract_aliases(sql_text: str) -> list[str]:
    """Extract alias_name string literals from INSERT INTO vendor_alias statements."""
    matches = ALIAS_PATTERN.findall(sql_text)
    return list(dict.fromkeys(matches))  # dedupe preserving order


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("migration", type=Path, help="SQL migration file")
    args = ap.parse_args()

    if not args.migration.exists():
        print(f"FATAL: migration not found: {args.migration}", file=sys.stderr)
        return 2

    sql = args.migration.read_text(encoding="utf-8")
    aliases = extract_aliases(sql)
    print(f"[INFO] {len(aliases)} alias_name candidates extracted from {args.migration.name}")

    if not aliases:
        print("[OK] no alias INSERTs detected, nothing to check")
        return 0

    dburl = _systemd_dburl()
    if not dburl:
        print("FATAL: no DATABASE_URL", file=sys.stderr)
        return 2

    collisions: list[dict] = []
    for alias in aliases:
        rows = _query(dburl,
            f"SELECT va.vendor_id, v.vendor_name, v.seed_source, va.source "
            f"FROM vendor_alias va JOIN vendor v ON v.vendor_id=va.vendor_id "
            f"WHERE LOWER(va.alias_name) = LOWER('{alias}')")
        if rows:
            v_id, v_name, seed, src = rows[0]
            placeholder = v_name == "lia-declined" or seed == "lia_internal"
            collisions.append({
                "alias": alias,
                "existing_vendor_id": v_id,
                "existing_vendor_name": v_name,
                "existing_source": src,
                "placeholder": placeholder,
            })

    if not collisions:
        print(f"[OK] all {len(aliases)} aliases free of collisions, safe to apply")
        return 0

    placeholder_collisions = [c for c in collisions if c["placeholder"]]
    real_collisions = [c for c in collisions if not c["placeholder"]]

    print(f"\n[COLLISIONS] {len(collisions)} aliases already exist:")
    print(f"  - {len(placeholder_collisions)} on placeholders (lia-declined / lia_internal) -> migration ON CONFLICT will silent-drop; REASSIGN migration needed POST-apply")
    print(f"  - {len(real_collisions)} on real vendors -> review manually")

    if placeholder_collisions:
        print("\n[PLACEHOLDER COLLISIONS]")
        for c in placeholder_collisions[:15]:
            print(f"  alias={c['alias']!r:30} -> {c['existing_vendor_name']} (vid={c['existing_vendor_id']}, src={c['existing_source']})")

    if real_collisions:
        print("\n[REAL VENDOR COLLISIONS]")
        for c in real_collisions[:15]:
            print(f"  alias={c['alias']!r:30} -> {c['existing_vendor_name']} (vid={c['existing_vendor_id']}, src={c['existing_source']})")

    print(f"\nTotal: {len(collisions)} collisions detected.")
    print("Action: review and add REASSIGN UPDATE statements after this migration.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
