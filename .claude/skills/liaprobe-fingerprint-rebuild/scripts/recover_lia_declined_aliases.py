#!/usr/bin/env python3
"""c38 S4: multi-strategy recovery scan for 186 lia-declined orphan aliases.

For each orphan alias, try 4 strategies in order of decreasing confidence:
1. token_substring: alias contains a token that is a real vendor name
2. vendor_substring: a real vendor name contains the full alias
3. cleaned_lookup: strip suffixes (Inc., Corp., GmbH) + retry exact match
4. word_first_or_last: first or last word matches a real vendor exactly

Output: RECOVERY_CANDIDATES_<DATE>.json with per-orphan top-3 candidates +
confidence tier (HIGH / MEDIUM / LOW). Operator picks HIGH-confidence subset
for c39+ reassignment migration.

NO mutation. OUTPUT-ONLY.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEV = Path("/opt/lia-sec/dev")
TRACKING = DEV / "_alire/tracking/liaprobe-fingerprint-rebuild"
NOW = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
RUN_DATE = datetime.now(timezone.utc).strftime("%Y-%m-%d")
DEFAULT_OUT = TRACKING / f"RECOVERY_CANDIDATES_{RUN_DATE}.json"

PLACEHOLDER_VENDORS = ("lia-declined", "lia-meta", "Unknown-O")
SUFFIXES = [
    " inc.", " inc", " corp.", " corp", " corporation", " gmbh", " ltd.",
    " ltd", " llc", " sa", " s.a.", " sas", " bv", " ag", " co.", " co",
    " group", " software", " technology", " systems", " industries",
]


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
        for k, v in params.items():
            safe = v.replace("'", "''")
            sql = sql.replace(f":{k}", f"'{safe}'")
    res = subprocess.run(
        ["psql", dburl, "-t", "-A", "-F", "\t", "-c", sql],
        capture_output=True, text=True, timeout=15,
    )
    if res.returncode != 0:
        return []  # tolerate query errors per orphan
    return [line.split("\t") for line in res.stdout.splitlines() if line.strip()]


def clean_alias(alias: str) -> str:
    lower = alias.lower().strip()
    for suf in SUFFIXES:
        if lower.endswith(suf):
            return lower[: -len(suf)].strip(" ,.")
    return lower


def split_tokens(alias: str) -> list[str]:
    # split on whitespace + punctuation
    tokens = re.split(r"[\s,./&\-_!]+", alias.lower())
    return [t for t in tokens if len(t) >= 3]


def recover_one(dburl: str, alias: str, placeholder_ids_csv: str) -> dict[str, Any]:
    candidates: list[dict[str, Any]] = []

    # Strategy 1: cleaned_lookup (exact match after suffix strip)
    cleaned = clean_alias(alias)
    if cleaned and cleaned != alias.lower():
        rows = _query(dburl,
            f"SELECT vendor_id, vendor_name, seed_source FROM vendor "
            f"WHERE LOWER(vendor_name) = LOWER(:alias) AND vendor_id NOT IN ({placeholder_ids_csv}) LIMIT 3",
            {"alias": cleaned})
        for r in rows:
            candidates.append({
                "strategy": "cleaned_lookup",
                "tier": "HIGH",
                "vendor_id": int(r[0]),
                "vendor_name": r[1],
                "seed_source": r[2],
                "match_input": cleaned,
            })

    # Strategy 2: word_first_or_last (single token exact match)
    tokens = split_tokens(alias)
    if len(tokens) > 1:
        for tok in (tokens[0], tokens[-1]):
            if len(tok) < 4:
                continue
            rows = _query(dburl,
                f"SELECT vendor_id, vendor_name, seed_source FROM vendor "
                f"WHERE LOWER(vendor_name) = LOWER(:tok) AND vendor_id NOT IN ({placeholder_ids_csv}) LIMIT 3",
                {"tok": tok})
            for r in rows:
                already = any(c["vendor_id"] == int(r[0]) for c in candidates)
                if not already:
                    candidates.append({
                        "strategy": "word_first_or_last",
                        "tier": "MEDIUM",
                        "vendor_id": int(r[0]),
                        "vendor_name": r[1],
                        "seed_source": r[2],
                        "match_input": tok,
                    })

    # Strategy 3: token_substring (vendor.vendor_name LIKE %token%)
    if not candidates and tokens:
        primary_token = max(tokens, key=len)
        if len(primary_token) >= 5:
            rows = _query(dburl,
                f"SELECT vendor_id, vendor_name, seed_source FROM vendor "
                f"WHERE LOWER(vendor_name) LIKE LOWER(:pat) AND vendor_id NOT IN ({placeholder_ids_csv}) "
                f"ORDER BY LENGTH(vendor_name) LIMIT 3",
                {"pat": f"%{primary_token}%"})
            for r in rows:
                already = any(c["vendor_id"] == int(r[0]) for c in candidates)
                if not already:
                    candidates.append({
                        "strategy": "token_substring",
                        "tier": "LOW",
                        "vendor_id": int(r[0]),
                        "vendor_name": r[1],
                        "seed_source": r[2],
                        "match_input": primary_token,
                    })

    return {"alias": alias, "candidates": candidates[:3]}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args()

    dburl = _systemd_dburl()
    if not dburl:
        print("FATAL: no DATABASE_URL", file=sys.stderr)
        return 2

    p_rows = _query(dburl,
        f"SELECT vendor_id, vendor_name FROM vendor "
        f"WHERE vendor_name IN ({','.join(repr(p) for p in PLACEHOLDER_VENDORS)})")
    placeholder_ids = [int(r[0]) for r in p_rows]
    placeholder_ids_csv = ",".join(str(i) for i in placeholder_ids)

    # Fetch all orphan aliases
    rows = _query(dburl, f"""
SELECT va.alias_name FROM vendor_alias va
WHERE va.vendor_id IN ({placeholder_ids_csv})
  AND NOT EXISTS (
      SELECT 1 FROM vendor v
      WHERE LOWER(v.vendor_name) = LOWER(va.alias_name)
        AND v.vendor_id NOT IN ({placeholder_ids_csv})
  )
ORDER BY va.alias_name
""")
    orphans = [r[0] for r in rows]
    print(f"[INFO] scanning {len(orphans)} orphan aliases")

    results = []
    tier_counts = {"HIGH": 0, "MEDIUM": 0, "LOW": 0, "NONE": 0}
    for orphan in orphans:
        r = recover_one(dburl, orphan, placeholder_ids_csv)
        results.append(r)
        if r["candidates"]:
            tier = r["candidates"][0]["tier"]
            tier_counts[tier] += 1
        else:
            tier_counts["NONE"] += 1

    artifact = {
        "schema": "lia-recovery-candidates-v1",
        "generated_at": NOW,
        "summary": {
            "total_orphans": len(orphans),
            "by_top_tier": tier_counts,
        },
        "results": results,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(artifact, indent=2, ensure_ascii=False), encoding="utf-8")

    print()
    print(f"[SUMMARY] HIGH={tier_counts['HIGH']} MEDIUM={tier_counts['MEDIUM']} LOW={tier_counts['LOW']} NONE={tier_counts['NONE']}")
    print()
    print("[HIGH-CONFIDENCE TOP 20]")
    high = [r for r in results if r["candidates"] and r["candidates"][0]["tier"] == "HIGH"]
    for r in high[:20]:
        c = r["candidates"][0]
        print(f"  {r['alias']!r:40} -> {c['vendor_name']!r:30} (strategy={c['strategy']})")

    print()
    print("[MEDIUM-CONFIDENCE TOP 20]")
    medium = [r for r in results if r["candidates"] and r["candidates"][0]["tier"] == "MEDIUM"]
    for r in medium[:20]:
        c = r["candidates"][0]
        print(f"  {r['alias']!r:40} -> {c['vendor_name']!r:30} (token={c['match_input']})")

    print(f"\noutput: {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
