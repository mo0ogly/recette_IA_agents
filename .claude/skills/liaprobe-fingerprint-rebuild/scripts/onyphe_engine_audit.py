#!/usr/bin/env python3
# onyphe_engine_audit.py
#
# Audit liaprobe rules against Onyphe ground-truth using the REAL liaprobe Go
# engine (bin/recette-onyphe), not a Python re-implementation. The Go engine
# loads all 10000+ patterns (web-signatures + banner-signatures + service-
# detectors + tcp-probes) and produces authoritative verdicts.
#
# This is the canonical source-of-truth audit. Python evaluator in
# onyphe_audit_web.py is retained for fast iteration but recette-onyphe is
# the reference for "rule proven by real-traffic detection".
#
# Outputs:
#   ONYPHE_ENGINE_AUDIT_<DATE>.json     -- full verdict report
#   ONYPHE_RULE_EVIDENCE_ENGINE_<DATE>.json -- per-rule proof of TP detection
#   ONYPHE_RENAME_PROPOSALS_<DATE>.json -- candidates where rule.product
#                                          differs from GTProduct (canonical
#                                          name from Onyphe)
#
# Usage:
#   python3 onyphe_engine_audit.py --sample 100
#   python3 onyphe_engine_audit.py --apply         # full corpus

import argparse
import glob
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

LIAPROBE_DIR = Path("/opt/lia-sec/liaprobe")
RECETTE_BIN = LIAPROBE_DIR / "bin/recette-onyphe"
PATTERNS_ROOT = LIAPROBE_DIR / "patterns"

DEV_DIR = Path("/opt/lia-sec/dev")
ONYPHE_FILE_DEFAULT = DEV_DIR / "_alire/temp/onyphe_recette_full_6265.jsonl"
ONYPHE_FILE = ONYPHE_FILE_DEFAULT  # may be overridden via --file CLI
TRACKING_DIR = DEV_DIR / "_alire/tracking/liaprobe-fingerprint-rebuild"

RUN_DATE = datetime.now(timezone.utc).strftime("%Y-%m-%d")


def run_engine(limit: int = 0) -> list:
    """Invoke recette-onyphe and return parsed JSON output (list of dicts)."""
    cmd = [
        str(RECETTE_BIN),
        "-f", str(ONYPHE_FILE),
        "-out", "json",
        "-src", "all",
    ]
    if limit:
        cmd.extend(["-limit", str(limit)])
    print(f"[INFO] Running: {' '.join(cmd)}  (cwd={LIAPROBE_DIR})")
    # recette-onyphe loads patterns relative to cwd
    proc = subprocess.run(
        cmd, cwd=str(LIAPROBE_DIR),
        capture_output=True, text=True, timeout=600,
    )
    if proc.returncode != 0:
        print(f"[ERROR] recette-onyphe exit {proc.returncode}:", file=sys.stderr)
        print(proc.stderr, file=sys.stderr)
        sys.exit(2)
    # Stderr contains "[recette-onyphe] X patterns charges" -- echo
    for ln in proc.stderr.splitlines():
        if ln.strip():
            print(f"  {ln}")
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        print(f"[ERROR] JSON parse: {e}", file=sys.stderr)
        sys.exit(3)


def build_pattern_index() -> dict:
    """Map PatternID (lowercase) -> rule file path + rule dict."""
    index = {}
    for root_subdir in ("web-signatures", "banner-signatures",
                        "service-detectors", "tcp-probes", "lia"):
        d = PATTERNS_ROOT / root_subdir
        if not d.exists():
            continue
        for path in d.glob("*.json"):
            try:
                rule = json.loads(path.read_text())
            except (json.JSONDecodeError, OSError):
                continue
            pid_candidates = []
            # v2-independent uses id (lowercase)
            if isinstance(rule.get("id"), str):
                pid_candidates.append(rule["id"])
            # v1-legacy uses taxonomy_code lowercased
            if isinstance(rule.get("taxonomy_code"), str):
                pid_candidates.append(rule["taxonomy_code"].lower())
            # filename stem
            pid_candidates.append(path.stem.lower())
            for pid in pid_candidates:
                if pid and pid.lower() not in index:
                    index[pid.lower()] = {"path": path, "rule": rule}
    return index


def extract_product(rule: dict, fallback: str) -> str:
    for k in ("product", "taxonomy_name", "name"):
        v = rule.get(k)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return fallback


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--sample", type=int, default=0,
                   help="Limit to first N banners (default 0 = full corpus)")
    p.add_argument("--apply", action="store_true",
                   help="Run on full corpus and write all 3 reports")
    p.add_argument("--file", type=str, default=None,
                   help=f"Onyphe jsonl file (default: {ONYPHE_FILE_DEFAULT})")
    args = p.parse_args()
    global ONYPHE_FILE
    if args.file:
        ONYPHE_FILE = Path(args.file)
        if not ONYPHE_FILE.exists():
            p.error(f"File not found: {ONYPHE_FILE}")
    if args.sample <= 0 and not args.apply:
        p.error("Specify --sample N or --apply")

    if not RECETTE_BIN.exists():
        print(f"[ERROR] {RECETTE_BIN} not found", file=sys.stderr)
        sys.exit(1)

    limit = args.sample if args.sample > 0 else 0
    verdicts = run_engine(limit=limit)
    print(f"[INFO] Engine returned {len(verdicts)} verdicts")

    # Aggregate by verdict
    counts = {}
    for v in verdicts:
        counts[v["Verdict"]] = counts.get(v["Verdict"], 0) + 1
    print("\nVERDICT SUMMARY:")
    for k, c in sorted(counts.items(), key=lambda x: -x[1]):
        pct = 100 * c / len(verdicts) if verdicts else 0
        print(f"  {k:12s}: {c:5d} ({pct:5.1f}%)")

    # Build pattern index for rename mapping
    print("\n[INFO] Indexing rule files...")
    pidx = build_pattern_index()
    print(f"[INFO] Pattern index: {len(pidx)} entries")

    # Per-PatternID evidence (TP only)
    evidence = {}
    rename_proposals = []
    for v in verdicts:
        pid = (v.get("PatternID") or "").lower()
        verdict = v.get("Verdict")
        if not pid or verdict != "CORRECT":
            continue
        gt_product = v.get("GTProduct", "")
        det_product = v.get("DetProduct", "")
        e = evidence.setdefault(pid, {
            "pattern_id": pid,
            "det_product": det_product,
            "gt_products_seen": {},
            "tp_count": 0,
            "samples": [],
        })
        e["tp_count"] += 1
        e["gt_products_seen"][gt_product] = e["gt_products_seen"].get(gt_product, 0) + 1
        if len(e["samples"]) < 10:
            e["samples"].append({
                "gt_product": gt_product,
                "gt_version": v.get("GTVersion", ""),
                "port": v.get("Port"),
                "protocol": v.get("Protocol"),
                "det_conf": v.get("DetConf"),
                "banner_snippet": (v.get("Banner") or "")[:120],
            })

    # Enrich evidence with rule file path + propose rename if product differs
    for pid, e in evidence.items():
        idx_entry = pidx.get(pid)
        if idx_entry:
            rule_path = str(idx_entry["path"].relative_to(LIAPROBE_DIR))
            current_product = extract_product(idx_entry["rule"], pid)
            e["rule_file"] = rule_path
            e["current_product"] = current_product
            # Dominant GT product (most common in TP samples)
            top_gt = max(e["gt_products_seen"].items(), key=lambda x: x[1])[0]
            e["canonical_onyphe_product"] = top_gt
            if current_product.lower() != top_gt.lower():
                rename_proposals.append({
                    "pattern_id": pid,
                    "rule_file": rule_path,
                    "current_product": current_product,
                    "proposed_product": top_gt,
                    "tp_count_supporting": e["tp_count"],
                    "gt_distribution": e["gt_products_seen"],
                })
        else:
            e["rule_file"] = None
            e["current_product"] = None
            e["canonical_onyphe_product"] = None

    # Reports
    main_report = {
        "schema": "lia-onyphe-engine-audit-v1",
        "run_date": RUN_DATE,
        "engine": str(RECETTE_BIN),
        "total_verdicts": len(verdicts),
        "verdict_summary": counts,
        "limit": limit,
    }
    evidence_report = {
        "schema": "lia-onyphe-rule-evidence-engine-v1",
        "run_date": RUN_DATE,
        "total_proven_rules": len(evidence),
        "evidence": evidence,
    }
    rename_report = {
        "schema": "lia-onyphe-rename-proposals-v1",
        "run_date": RUN_DATE,
        "total_proposals": len(rename_proposals),
        "proposals": rename_proposals,
    }

    if args.sample > 0 and not args.apply:
        # Sample mode -- just print summary, no write
        print(f"\n[SAMPLE] {len(evidence)} proven rules (TP > 0)")
        print(f"[SAMPLE] {len(rename_proposals)} rename proposals "
              f"(rule.product != Onyphe.GTProduct)")
        if rename_proposals[:5]:
            print("\nFirst 5 rename proposals:")
            for r in rename_proposals[:5]:
                print(f"  {r['pattern_id']:25s} "
                      f"'{r['current_product']}' -> '{r['proposed_product']}' "
                      f"(tp={r['tp_count_supporting']})")
        return 0

    main_path = TRACKING_DIR / f"ONYPHE_ENGINE_AUDIT_{RUN_DATE}.json"
    with open(main_path, "w") as f:
        json.dump(main_report, f, indent=2, ensure_ascii=False)
    evidence_path = TRACKING_DIR / f"ONYPHE_RULE_EVIDENCE_ENGINE_{RUN_DATE}.json"
    with open(evidence_path, "w") as f:
        json.dump(evidence_report, f, indent=2, ensure_ascii=False)
    rename_path = TRACKING_DIR / f"ONYPHE_RENAME_PROPOSALS_{RUN_DATE}.json"
    with open(rename_path, "w") as f:
        json.dump(rename_report, f, indent=2, ensure_ascii=False)

    # Per-rule trace files: alongside each matched rule file, write
    # <pattern_id>_trace.txt containing Onyphe execution proof.
    traces_written = 0
    for pid, e in evidence.items():
        rule_file = e.get("rule_file")
        if not rule_file:
            continue
        rule_path = LIAPROBE_DIR / rule_file
        if not rule_path.exists():
            continue
        trace_path = rule_path.parent / f"{rule_path.stem}_trace.txt"
        lines = []
        lines.append(f"# ONYPHE GROUND-TRUTH EXECUTION TRACE")
        lines.append(f"# Rule file        : {rule_file}")
        lines.append(f"# Pattern ID       : {pid}")
        lines.append(f"# Current product  : {e.get('current_product', '?')}")
        lines.append(f"# Onyphe canonical : {e.get('canonical_onyphe_product', '?')}")
        lines.append(f"# Run date         : {RUN_DATE}")
        lines.append(f"# Engine binary    : {RECETTE_BIN}")
        lines.append(f"# TP matches       : {e['tp_count']}")
        lines.append(f"# GT distribution  : {json.dumps(e['gt_products_seen'], ensure_ascii=False)}")
        lines.append("")
        lines.append("=" * 78)
        lines.append("  PROOF SAMPLES (up to 10 banners that triggered this rule via real engine)")
        lines.append("=" * 78)
        for i, s in enumerate(e["samples"], 1):
            lines.append(f"")
            lines.append(f"--- sample {i}/{len(e['samples'])} ---")
            lines.append(f"GTProduct  : {s['gt_product']}")
            lines.append(f"GTVersion  : {s['gt_version']}")
            lines.append(f"Port       : {s['port']}")
            lines.append(f"Protocol   : {s['protocol']}")
            lines.append(f"DetConf    : {s['det_conf']}")
            lines.append(f"Banner     : {s['banner_snippet']!r}")
        lines.append("")
        lines.append("=" * 78)
        lines.append("  REPRODUCTION COMMAND")
        lines.append("=" * 78)
        lines.append("")
        lines.append("cd /opt/lia-sec/liaprobe")
        lines.append("bin/recette-onyphe \\")
        lines.append("    -f /opt/lia-sec/dev/_alire/temp/onyphe_recette_full_6265.jsonl \\")
        lines.append("    -out json -src all \\")
        lines.append(f"  | jq '.[] | select(.PatternID == \"{pid}\" and .Verdict == \"CORRECT\")'")
        lines.append("")
        trace_path.write_text("\n".join(lines) + "\n")
        traces_written += 1

    print(f"\n[EVIDENCE] {len(evidence)} rules proven by Onyphe (TP > 0)")
    print(f"[TRACES]   {traces_written} *_trace.txt files written alongside rule .json")
    print(f"[RENAME]   {len(rename_proposals)} canonical-rename proposals")
    print(f"\nReports:")
    print(f"  {main_path}")
    print(f"  {evidence_path}")
    print(f"  {rename_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
