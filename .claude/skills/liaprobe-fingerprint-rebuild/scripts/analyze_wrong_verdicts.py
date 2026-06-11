#!/usr/bin/env python3
# analyze_wrong_verdicts.py
#
# Group WRONG verdicts by responsible rule (PatternID). For each rule:
#   - fp_count    : number of WRONG matches
#   - tp_count    : number of CORRECT matches (from same engine run)
#   - precision   : tp / (tp + fp)
#   - det_product : what the rule claims to detect
#   - gt_seen     : Counter of actual GT products on banners that triggered the rule
#
# Output: WRONG_BY_RULE_<DATE>.json + plain-text summary on stdout.
#
# Inputs:
#   --verdicts <PATH>  (default: ../../temp/apex/apex-20260513-c8/full_verdicts.json)
#   --top N            (default: 20)
#
# Usage:
#   python3 analyze_wrong_verdicts.py
#   python3 analyze_wrong_verdicts.py --top 50

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

DEV_DIR = Path("/opt/lia-sec/dev")
TRACKING_DIR = DEV_DIR / "_alire/tracking/liaprobe-fingerprint-rebuild"
DEFAULT_VERDICTS = DEV_DIR / "_alire/temp/apex/apex-20260513-c8/full_verdicts.json"

RUN_DATE = datetime.now(timezone.utc).strftime("%Y-%m-%d")


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--verdicts", type=str, default=str(DEFAULT_VERDICTS))
    p.add_argument("--top", type=int, default=20)
    p.add_argument("--min-fp", type=int, default=1,
                   help="Only report rules with fp_count >= min-fp (default 1)")
    args = p.parse_args()

    verdicts = json.loads(Path(args.verdicts).read_text())
    print(f"[INFO] Loaded {len(verdicts)} verdicts from {args.verdicts}")

    per_rule = {}
    wrong_total = 0
    correct_total = 0
    for v in verdicts:
        pid = v.get("PatternID") or ""
        if not pid:
            continue
        verdict = v.get("Verdict")
        rec = per_rule.setdefault(pid, {
            "pattern_id": pid,
            "det_product": v.get("DetProduct", ""),
            "tp": 0,
            "fp": 0,
            "gt_when_wrong": Counter(),
            "gt_when_correct": Counter(),
            "samples_wrong": [],
        })
        if verdict == "CORRECT":
            rec["tp"] += 1
            correct_total += 1
            rec["gt_when_correct"][v.get("GTProduct", "")] += 1
        elif verdict == "WRONG":
            rec["fp"] += 1
            wrong_total += 1
            rec["gt_when_wrong"][v.get("GTProduct", "")] += 1
            if len(rec["samples_wrong"]) < 5:
                rec["samples_wrong"].append({
                    "gt_product": v.get("GTProduct"),
                    "port": v.get("Port"),
                    "protocol": v.get("Protocol"),
                    "det_conf": v.get("DetConf"),
                    "banner_snippet": (v.get("Banner") or "")[:120],
                })

    # Convert Counters to dict for JSON
    for rec in per_rule.values():
        denom = rec["tp"] + rec["fp"]
        rec["precision"] = round(rec["tp"] / denom, 3) if denom else None
        rec["total_matches"] = denom
        rec["gt_when_wrong"] = dict(rec["gt_when_wrong"].most_common())
        rec["gt_when_correct"] = dict(rec["gt_when_correct"].most_common())

    bad_rules = [r for r in per_rule.values() if r["fp"] >= args.min_fp]
    bad_rules.sort(key=lambda r: (-r["fp"], r["precision"] or 0))

    report = {
        "schema": "lia-wrong-by-rule-v1",
        "run_date": RUN_DATE,
        "total_verdicts": len(verdicts),
        "total_correct": correct_total,
        "total_wrong": wrong_total,
        "rules_with_fp": len(bad_rules),
        "rules_total_triggered": len(per_rule),
        "rules": bad_rules,
    }

    out = TRACKING_DIR / f"WRONG_BY_RULE_{RUN_DATE}.json"
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False))

    print(f"\n[STATS]")
    print(f"  Rules triggered any match : {len(per_rule)}")
    print(f"  Rules with fp >= {args.min_fp}     : {len(bad_rules)}")
    print(f"  Total CORRECT             : {correct_total}")
    print(f"  Total WRONG               : {wrong_total}")
    print()
    print(f"TOP {args.top} OFFENDERS (sorted by fp DESC):")
    print(f"  {'pattern_id':35s} {'det_product':25s} {'fp':>5s} {'tp':>5s} {'prec':>6s}  gt_when_wrong[:3]")
    for r in bad_rules[:args.top]:
        gt_top = list(r["gt_when_wrong"].items())[:3]
        gt_str = ", ".join(f"{p}={c}" for p, c in gt_top)
        prec = f"{r['precision']:.2f}" if r["precision"] is not None else "n/a"
        print(f"  {r['pattern_id']:35s} {r['det_product'][:25]:25s} "
              f"{r['fp']:5d} {r['tp']:5d} {prec:>6s}  {gt_str[:60]}")

    print(f"\nReport: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
