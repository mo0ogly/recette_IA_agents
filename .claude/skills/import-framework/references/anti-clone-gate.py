#!/usr/bin/env python3
"""
Anti-clone Jaccard gate for clean-room AGPL framework imports.

RETEX 2026-05-26 (NIST Tier 1, 6 frameworks, 2350 questions).

Reads hand-authored questions from data/ai_rephrased/*.json + official extracted
statements from data/extracted/*.json (+ optionally legacy DB titles), computes
Jaccard similarity word-level, writes a verdict report.

Verdict thresholds (RETEX-tuned):
  sim_official < 0.80 AND sim_legacy < 0.80 -> PASS
  0.80 <= sim_official < 0.95               -> WARN_OFFICIAL
  0.80 <= sim_legacy   < 0.95               -> WARN_LEGACY
  sim_official >= 0.95                      -> FAIL_OFFICIAL (re-rephrase mandatory)
  sim_legacy   >= 0.95                      -> FAIL_LEGACY   (AGPL contamination)

Usage:
  python3 anti_clone_gate.py \
    --rephrased data/ai_rephrased \
    --official  data/extracted \
    --legacy    data/legacy_db_titles.json \
    --out       data/anti_clone_report.json

Exit codes:
  0 = PASS (0 FAIL, optional WARNs)
  1 = FAIL (>=1 FAIL_OFFICIAL or FAIL_LEGACY)
"""

import argparse
import json
import re
import sys
from pathlib import Path


WORD_RE = re.compile(r"[a-z0-9]+")


def tokens(s: str) -> set:
    return set(WORD_RE.findall((s or "").lower()))


def jaccard(a: str, b: str) -> float:
    ta, tb = tokens(a), tokens(b)
    if not ta and not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def verdict(sim_official: float, sim_legacy: float) -> str:
    if sim_official >= 0.95:
        return "FAIL_OFFICIAL"
    if sim_legacy >= 0.95:
        return "FAIL_LEGACY"
    if sim_official >= 0.80:
        return "WARN_OFFICIAL"
    if sim_legacy >= 0.80:
        return "WARN_LEGACY"
    return "PASS"


def load_rephrased(p: Path) -> list:
    """Returns list of {id, title, control_reference, official_statement}."""
    out = []
    for f in sorted(p.glob("*.json")):
        data = json.loads(f.read_text())
        items = data.get("questions") or data.get("items") or data
        if isinstance(items, dict):
            items = list(items.values())
        for q in items:
            out.append({
                "id": q.get("id"),
                "title": q.get("title", ""),
                "control_reference": q.get("control_reference", ""),
                "official_statement": q.get("source", {}).get("official_statement", ""),
                "_file": f.name,
            })
    return out


def load_legacy(p: Path) -> dict:
    """Optional: dict {control_reference: legacy_title}."""
    if not p or not p.exists():
        return {}
    return json.loads(p.read_text())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rephrased", required=True, type=Path)
    ap.add_argument("--official", type=Path, default=None,
                    help="Optional dir with official statements per family")
    ap.add_argument("--legacy", type=Path, default=None,
                    help="Optional JSON {control_ref: legacy_title}")
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args()

    rephrased = load_rephrased(args.rephrased)
    legacy = load_legacy(args.legacy) if args.legacy else {}

    rows = []
    counts = {"PASS": 0, "WARN_OFFICIAL": 0, "WARN_LEGACY": 0,
              "FAIL_OFFICIAL": 0, "FAIL_LEGACY": 0}

    for q in rephrased:
        sim_o = jaccard(q["title"], q.get("official_statement", ""))
        sim_l = jaccard(q["title"], legacy.get(q.get("control_reference", ""), ""))
        v = verdict(sim_o, sim_l)
        counts[v] += 1
        rows.append({
            "id": q["id"],
            "control_reference": q["control_reference"],
            "file": q["_file"],
            "sim_official": round(sim_o, 3),
            "sim_legacy": round(sim_l, 3),
            "verdict": v,
            "title_preview": q["title"][:120],
        })

    fails = counts["FAIL_OFFICIAL"] + counts["FAIL_LEGACY"]
    report = {
        "schema": "anti-clone-report-v1",
        "total": len(rephrased),
        "counts": counts,
        "verdict": "PASS" if fails == 0 else "FAIL",
        "rows": rows,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2))

    print(f"Total: {report['total']}, counts: {counts}")
    print(f"Verdict: {report['verdict']}")
    if fails:
        print("FAILs:")
        for r in rows:
            if r["verdict"].startswith("FAIL"):
                print(f"  {r['id']} {r['verdict']} sim_o={r['sim_official']} sim_l={r['sim_legacy']}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
