#!/usr/bin/env python3
# audit_merge_coverage.py
#
# Compare engine verdicts pre/post a MERGE operation per-cluster.
# Identifies which losers had unique detection coverage that the winner
# does NOT recover, so the operator can decide to revert MERGE -> SPLIT.
#
# Inputs:
#   --pre   : JSON output of bin/recette-onyphe BEFORE merge (each
#             verdict has PatternID, Verdict, GTProduct)
#   --post  : JSON output AFTER merge
#   --out   : audit JSON (default: _alire/tracking/.../MERGE_COVERAGE_AUDIT_<DATE>.json)
#
# Strategy: for each PatternID in pre that was CORRECT but no longer
# appears in post (or its banners are now MISS), the loser was carrying
# unique detection.

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

DEV_DIR = Path("/opt/lia-sec/dev")
TRACKING_DIR = DEV_DIR / "_alire/tracking/liaprobe-fingerprint-rebuild"
DEFAULT_OUT = TRACKING_DIR / f"MERGE_COVERAGE_AUDIT_{datetime.now(timezone.utc).strftime('%Y-%m-%d')}.json"


def _banner_key(v: dict) -> str:
    # Stable per-banner identifier: port + protocol + first 80 chars of banner
    b = (v.get("Banner") or "")[:80]
    return f"{v.get('Port')}|{v.get('Protocol')}|{b}"


def _load_verdicts(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        data = data.get("verdicts") or data.get("results") or []
    return data


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pre", type=Path, required=True)
    ap.add_argument("--post", type=Path, required=True)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args()

    pre = _load_verdicts(args.pre)
    post = _load_verdicts(args.post)

    # Index by banner key
    pre_by_banner: dict[str, dict] = {}
    for v in pre:
        pre_by_banner[_banner_key(v)] = v
    post_by_banner: dict[str, dict] = {}
    for v in post:
        post_by_banner[_banner_key(v)] = v

    # Find: pre=CORRECT, post=MISS (lost detection)
    lost: list[dict] = []
    for key, pv in pre_by_banner.items():
        if pv.get("Verdict") != "CORRECT":
            continue
        post_v = post_by_banner.get(key)
        if post_v is None:
            lost.append({"banner_key": key, "pre": pv, "post": None,
                         "reason": "banner_missing_in_post"})
            continue
        if post_v.get("Verdict") == "MISS":
            lost.append({"banner_key": key, "pre": pv, "post": post_v,
                         "reason": "verdict_changed_to_miss"})

    # Aggregate: per PatternID (pre) -> count of lost banners
    by_pattern: Counter = Counter()
    by_gtproduct: Counter = Counter()
    samples_by_pattern: dict[str, list[dict]] = defaultdict(list)
    for entry in lost:
        pid = entry["pre"].get("PatternID", "")
        gt = entry["pre"].get("GTProduct", "")
        by_pattern[pid] += 1
        by_gtproduct[gt] += 1
        if len(samples_by_pattern[pid]) < 3:
            samples_by_pattern[pid].append({
                "banner": (entry["pre"].get("Banner") or "")[:120],
                "port": entry["pre"].get("Port"),
                "gt_product": gt,
            })

    # Recovery: pre=MISS, post=CORRECT (engine actually improved)
    recovered: list[dict] = []
    for key, pv in pre_by_banner.items():
        if pv.get("Verdict") not in ("MISS", "WRONG"):
            continue
        post_v = post_by_banner.get(key)
        if post_v is not None and post_v.get("Verdict") == "CORRECT":
            recovered.append({"banner_key": key, "pre_verdict": pv["Verdict"],
                              "post_pattern": post_v.get("PatternID"),
                              "gt_product": pv.get("GTProduct")})

    # Stats summary
    pre_counts = Counter(v.get("Verdict") for v in pre)
    post_counts = Counter(v.get("Verdict") for v in post)

    artifact = {
        "schema": "lia-merge-coverage-audit-v1",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "pre": str(args.pre),
        "post": str(args.post),
        "summary": {
            "pre_verdict_counts": dict(pre_counts),
            "post_verdict_counts": dict(post_counts),
            "lost_correct_banners": len(lost),
            "recovered_banners": len(recovered),
            "net_delta_correct": post_counts["CORRECT"] - pre_counts["CORRECT"],
        },
        "lost_by_pattern_id": dict(sorted(by_pattern.items(), key=lambda x: -x[1])),
        "lost_by_gt_product": dict(sorted(by_gtproduct.items(), key=lambda x: -x[1])),
        "samples_by_pattern": dict(samples_by_pattern),
        "recovered_sample": recovered[:20],
    }

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(artifact, indent=2, ensure_ascii=False), encoding="utf-8")

    print(f"lost CORRECT banners      : {len(lost)}")
    print(f"recovered (MISS/WRONG->CORRECT) : {len(recovered)}")
    print(f"net delta CORRECT         : {artifact['summary']['net_delta_correct']}")
    print(f"\ntop lost pattern_ids:")
    for pid, n in list(by_pattern.most_common(10)):
        print(f"  {n:>4}  {pid}")
    print(f"\noutput: {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
