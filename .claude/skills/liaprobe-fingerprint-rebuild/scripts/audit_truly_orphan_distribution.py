#!/usr/bin/env python3
"""c38 A43: distribution audit of truly-orphan placeholder aliases.

For aliases on placeholder vendors (lia-declined / lia-meta / Unknown-O)
that have NO real-vendor match and NO fuzzy candidate at threshold 0.6:
- Group by placeholder vendor (source distribution)
- Group by alias_source (lia_internal vs manual vs nvd_cpe)
- Group by alias_name length (short = abbreviations, long = full names)
- Identify high-value patterns (CPE-like, known-vendor-look-alike)

Output: TRULY_ORPHAN_DISTRIBUTION_<DATE>.json + summary report for c38+
manual research targeting.

Decision: KEEP all 105 by default. Document why in SKILL.md.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEV = Path("/opt/lia-sec/dev")
TRACKING = DEV / "_alire/tracking/liaprobe-fingerprint-rebuild"
NOW = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
RUN_DATE = datetime.now(timezone.utc).strftime("%Y-%m-%d")
DEFAULT_OUT = TRACKING / f"TRULY_ORPHAN_DISTRIBUTION_{RUN_DATE}.json"

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
        capture_output=True, text=True, timeout=15,
    )
    if res.returncode != 0:
        raise RuntimeError(f"psql failed: {res.stderr.strip()}")
    return [line.split("\t") for line in res.stdout.splitlines() if line.strip()]


def categorize_alias(name: str) -> str:
    """Heuristic categorization of alias name format."""
    n = name.strip()
    if len(n) <= 5 and n.isupper():
        return "short_uppercase_abbreviation"
    if re.match(r"^[a-z][a-z0-9-]*[a-z0-9]$", n):
        return "lowercase_dns_friendly"
    if re.match(r"^[A-Z][a-z]+(\s[A-Z][a-z]+)*\s+(Inc|Corp|Ltd|GmbH|Llc)\.?$", n):
        return "corporate_with_suffix"
    if " " in n and any(t in n.lower() for t in ("software", "technology", "system", "group")):
        return "company_with_industry_keyword"
    if "." in n or "/" in n or "!" in n:
        return "punctuation_includes"
    if any(c.isspace() for c in n):
        return "multi_word_personal_or_company"
    return "single_token"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--candidates-source", type=Path,
                    default=TRACKING / "PLACEHOLDER_ORPHANS_CANDIDATES_2026-05-13.json",
                    help="JSON output of audit_placeholder_orphans.py at threshold 0.6")
    args = ap.parse_args()

    dburl = _systemd_dburl()
    if not dburl:
        print("FATAL: no DATABASE_URL", file=sys.stderr)
        return 2

    if not args.candidates_source.exists():
        print(f"FATAL: candidates source missing: {args.candidates_source}", file=sys.stderr)
        return 2

    artifact_in = json.loads(args.candidates_source.read_text())
    truly_orphan = [r for r in artifact_in["results"] if r.get("status") == "NO_CANDIDATE"]
    print(f"[INFO] truly-orphan placeholder aliases: {len(truly_orphan)}")

    # Enrich with PG row data
    ids = ",".join(str(r["alias_id"]) for r in truly_orphan)
    if not ids:
        print("[OK] nothing to audit, exit")
        return 0
    rows = _query(dburl, f"""
SELECT va.id, va.alias_name, va.source, va.added_at, v.vendor_name AS placeholder_name
FROM vendor_alias va
JOIN vendor v ON v.vendor_id = va.vendor_id
WHERE va.id IN ({ids})
""")
    pg_by_id = {int(r[0]): {"alias": r[1], "source": r[2], "added_at": r[3], "placeholder": r[4]} for r in rows}

    # Aggregate
    by_placeholder: Counter[str] = Counter()
    by_source: Counter[str] = Counter()
    by_category: Counter[str] = Counter()
    by_length_bucket: Counter[str] = Counter()
    enriched: list[dict[str, Any]] = []

    for r in truly_orphan:
        meta = pg_by_id.get(r["alias_id"], {})
        alias = meta.get("alias", r["alias_name"])
        src = meta.get("source", "?")
        placeholder = meta.get("placeholder", "?")
        cat = categorize_alias(alias)
        n = len(alias)
        bucket = "1-5" if n <= 5 else "6-10" if n <= 10 else "11-20" if n <= 20 else "21+"

        by_placeholder[placeholder] += 1
        by_source[src] += 1
        by_category[cat] += 1
        by_length_bucket[bucket] += 1

        enriched.append({
            "alias_id": r["alias_id"],
            "alias_name": alias,
            "source": src,
            "placeholder": placeholder,
            "category": cat,
            "length_bucket": bucket,
            "added_at": meta.get("added_at"),
        })

    summary = {
        "total_truly_orphan": len(enriched),
        "by_placeholder": dict(by_placeholder),
        "by_source": dict(by_source),
        "by_category": dict(by_category.most_common()),
        "by_length_bucket": dict(by_length_bucket.most_common()),
    }

    # Decision rationale (output policy)
    policy = {
        "decision": "KEEP_AS_IS",
        "rationale": [
            "105 placeholder orphan aliases have no real-vendor match AND no fuzzy candidate at threshold 0.6.",
            "C38 S2 spot-check of 10 highest-score (0.5-0.55) candidates returned 0 validated.",
            "DELETE = irreversible audit-trail loss. The placeholder vendor 'lia-declined' is the LIA-Scan curated catch-all for unresolved vendor names from rule.vendor fields.",
            "Future enrichment value: web research per orphan can produce a canonical vendor (e.g. 'serome technology, inc.' -> Serome Technology Inc., Korean). Manual one-by-one workflow appropriate.",
            "DELETE would force re-discovery if an orphan later proves resolvable, breaking the cumulative knowledge of c1-c38.",
        ],
        "next_steps_optional": [
            "c39+: manual research of 5-10 highest-value orphans per cycle (target vendors with active CVEs first).",
            "Build /enrich-placeholder-orphan slash command that walks per-orphan WebFetch -> PG lookup -> manual confirmation.",
            "Hard policy: never DELETE from vendor_alias without explicit user authorization.",
        ],
    }

    out = {
        "schema": "lia-truly-orphan-distribution-v1",
        "generated_at": NOW,
        "summary": summary,
        "policy": policy,
        "entries": enriched,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")

    print()
    print("[DISTRIBUTION]")
    print(f"  total           : {summary['total_truly_orphan']}")
    print(f"  by placeholder  :")
    for k, v in by_placeholder.most_common():
        print(f"      {k:<20} : {v}")
    print(f"  by alias source :")
    for k, v in by_source.most_common():
        print(f"      {k:<20} : {v}")
    print(f"  by category     :")
    for k, v in by_category.most_common():
        print(f"      {k:<35} : {v}")
    print(f"  by length bucket:")
    for k, v in by_length_bucket.most_common():
        print(f"      {k:<10} : {v}")
    print()
    print(f"[POLICY] {policy['decision']}")
    print(f"\noutput: {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
