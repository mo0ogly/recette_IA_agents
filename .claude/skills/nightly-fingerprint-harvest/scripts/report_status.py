#!/usr/bin/env python3
"""Global status report on the LiaProbe fingerprint corpus.

Reads:
  - All JSON rules across the 4 target directories
  - <session_root>/nightly/.state/rules_status.json

Produces (idempotent):
  - <session_root>/nightly/.state/global_status.md   -- human report
  - <session_root>/nightly/.state/global_status.csv  -- per-rule CSV

Usage:
  python3 scripts/report_status.py [--session-root PATH]

Counts (every rule slot in one of these buckets):
  - promotion_ready  : best_score >= threshold AND no drift -> ready to apply patch
  - drift_detected   : a fresh capture conflicts with the existing
                       artifacts.html_sha256 -> needs manual review
  - captured_no_match: at least one capture but score < threshold
  - queried_no_capture: queried at least once but every source returned 0 hosts
  - never_queried    : never been visited by the nightly harvest
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent
if str(THIS_DIR) not in sys.path:
    sys.path.insert(0, str(THIS_DIR))

from lib.rule_loader import iter_rules  # noqa: E402
from lib.rule_tracker import load_status, state_dir  # noqa: E402

DEFAULT_SESSION_ROOT = Path(
    "/opt/lia-sec/dev/_alire/tracking/liaprobe-fingerprint-rebuild"
)


def _bucket(rule_data: dict, entry: dict | None) -> str:
    if entry is None:
        return "never_queried"
    if entry.get("drift_detected"):
        return "drift_detected"
    if entry.get("promotion_ready"):
        return "promotion_ready"
    if entry.get("total_captures", 0) > 0:
        return "captured_no_match"
    return "queried_no_capture"


def build_overview(session_root: Path) -> tuple[dict, list[dict]]:
    status = load_status(session_root)
    rows: list[dict] = []
    counts = {
        "promotion_ready": 0,
        "drift_detected": 0,
        "captured_no_match": 0,
        "queried_no_capture": 0,
        "never_queried": 0,
    }

    for rule in iter_rules():
        entry = status.get(rule.rule_id)
        bucket = _bucket(rule.data, entry)
        counts[bucket] += 1
        rows.append({
            "rule_id": rule.rule_id,
            "path": str(rule.path),
            "vendor": rule.vendor,
            "product": rule.product,
            "taxonomy_code": rule.taxonomy_code,
            "bucket": bucket,
            "total_visits": (entry or {}).get("total_visits", 0),
            "total_captures": (entry or {}).get("total_captures", 0),
            "best_score": (entry or {}).get("best_score", 0.0),
            "sources_succeeded": ",".join((entry or {}).get("sources_succeeded", [])),
            "outcome_latest": (entry or {}).get("outcome_latest", "n/a"),
            "first_queried_at": (entry or {}).get("first_queried_at"),
            "last_queried_at": (entry or {}).get("last_queried_at"),
            "queried_dates": ",".join((entry or {}).get("queried_dates", [])),
            "confidence_threshold": rule.data.get("confidence_threshold"),
        })

    counts["total"] = len(rows)
    counts["queried"] = counts["total"] - counts["never_queried"]
    counts["pct_queried"] = round(100.0 * counts["queried"] / counts["total"], 2) if counts["total"] else 0.0
    counts["pct_promotion_ready"] = round(100.0 * counts["promotion_ready"] / counts["total"], 2) if counts["total"] else 0.0
    return counts, rows


def write_csv(rows: list[dict], path: Path) -> None:
    fields = [
        "rule_id", "path", "vendor", "product", "taxonomy_code", "bucket",
        "total_visits", "total_captures", "best_score", "sources_succeeded",
        "outcome_latest", "first_queried_at", "last_queried_at",
        "queried_dates", "confidence_threshold",
    ]
    with path.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        for r in rows:
            w.writerow(r)


def write_markdown(counts: dict, rows: list[dict], path: Path) -> None:
    drifts = [r for r in rows if r["bucket"] == "drift_detected"][:20]
    ready = [r for r in rows if r["bucket"] == "promotion_ready"][:20]
    never = [r for r in rows if r["bucket"] == "never_queried"][:20]

    lines = [
        "# LiaProbe fingerprint corpus -- nightly status",
        "",
        f"_Generated {datetime.now(timezone.utc).isoformat()}_",
        "",
        "## Counts",
        "",
        f"- Total rules         : **{counts['total']}**",
        f"- Queried at least once: **{counts['queried']}** ({counts['pct_queried']} %)",
        f"- Never queried       : **{counts['never_queried']}**",
        "",
        "## Buckets",
        "",
        "| Bucket | Count |",
        "|--------|------:|",
        f"| promotion_ready    | {counts['promotion_ready']} |",
        f"| drift_detected     | {counts['drift_detected']} |",
        f"| captured_no_match  | {counts['captured_no_match']} |",
        f"| queried_no_capture | {counts['queried_no_capture']} |",
        f"| never_queried      | {counts['never_queried']} |",
        "",
        f"Promotion-ready coverage: **{counts['pct_promotion_ready']} %**",
        "",
        "## Promotion-ready (top 20)",
        "",
        "| Rule | Vendor | Product | Score | Sources |",
        "|------|--------|---------|------:|---------|",
    ]
    for r in ready:
        lines.append(f"| {r['rule_id']} | {r['vendor']} | {r['product']} | {r['best_score']:.2f} | {r['sources_succeeded']} |")
    lines += [
        "",
        "## Drift detected (top 20) -- manual review needed",
        "",
        "| Rule | Vendor | Product | Best score |",
        "|------|--------|---------|------:|",
    ]
    for r in drifts:
        lines.append(f"| {r['rule_id']} | {r['vendor']} | {r['product']} | {r['best_score']:.2f} |")
    lines += [
        "",
        "## Never queried (sample of 20)",
        "",
        "| Rule | Vendor | Product | Threshold |",
        "|------|--------|---------|----------:|",
    ]
    for r in never:
        lines.append(f"| {r['rule_id']} | {r['vendor']} | {r['product']} | {r['confidence_threshold']} |")

    lines += [
        "",
        "## CSV companion",
        "",
        "See `global_status.csv` for the full per-rule breakdown (importable in Excel/Pandas).",
    ]
    path.write_text("\n".join(lines))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session-root", default=str(DEFAULT_SESSION_ROOT))
    args = parser.parse_args()

    session_root = Path(args.session_root)
    if not session_root.exists():
        print(f"session root not found: {session_root}", file=sys.stderr)
        return 2

    counts, rows = build_overview(session_root)
    out_dir = state_dir(session_root)
    write_csv(rows, out_dir / "global_status.csv")
    write_markdown(counts, rows, out_dir / "global_status.md")
    print(f"OK total={counts['total']} queried={counts['queried']} promotion_ready={counts['promotion_ready']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
