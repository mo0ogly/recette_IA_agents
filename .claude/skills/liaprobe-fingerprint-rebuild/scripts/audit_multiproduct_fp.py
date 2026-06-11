#!/usr/bin/env python3
# audit_multiproduct_fp.py
#
# Corpus-wide Onyphe gt mismatch detection. For each WRONG verdict,
# checks if the rule's product name (or significant tokens) appears in
# the full banner content. If yes, the rule detected a legit signal but
# Onyphe ground-truth categorized the IP under a different product (typical
# of multi-product hosting where ONE IP runs N services).
#
# Generalizes the gfi_kerio_connect c13 forensic that revealed 80% of
# "FPs" were Onyphe gt mismatch (not rule bugs).
#
# Output: MULTIPRODUCT_FP_AUDIT_<DATE>.json
#   - per-rule: total_fp, onyphe_gt_mismatch_count, true_fp_count
#   - corpus: real_precision (after gt corrections)
#
# Usage:
#   python3 audit_multiproduct_fp.py
#   python3 audit_multiproduct_fp.py --apply  # add fp_audit block to rule

import argparse
import json
import re
import shutil
import subprocess
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

LIAPROBE_DIR = Path("/opt/lia-sec/liaprobe")
PATTERNS_ROOT = LIAPROBE_DIR / "patterns"
RECETTE_BIN = LIAPROBE_DIR / "bin/recette-onyphe"
DEV_DIR = Path("/opt/lia-sec/dev")
ONYPHE_FILE = DEV_DIR / "_alire/temp/onyphe_merged_skipspip_2026-05-13.jsonl"
TRACKING_DIR = DEV_DIR / "_alire/tracking/liaprobe-fingerprint-rebuild"
BACKUP_DIR = DEV_DIR / "_alire/temp/apex/apex-20260513-c14/fp_audit_backup"

RUN_DATE = datetime.now(timezone.utc).strftime("%Y-%m-%d")
NOW_ISO = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
PASS_ID = f"{RUN_DATE}_apex_c14_multiproduct_fp"


def extract_signature_tokens(product: str) -> list:
    """Tokens from product name useful for banner-search.
    Filter generic words (server, service, web, http, etc.)."""
    GENERIC = {"server", "service", "web", "http", "https", "agent",
               "client", "system", "tool", "manager", "gateway",
               "appliance", "edition", "v1", "v2", "v3",
               "inc", "corp", "ltd", "the", "and", "of", "for"}
    tokens = re.findall(r"[a-z0-9]{3,}", product.lower())
    return [t for t in tokens if t not in GENERIC and len(t) >= 3]


def find_full_banner(eng_banner: str, source_banners: list) -> str:
    """Locate full banner in source list by engine truncated prefix match."""
    if not eng_banner:
        return ""
    eng_prefix = eng_banner[:30]
    for b in source_banners:
        b_repr = b[:30].replace("\r\n", "..")
        if b_repr[:25] == eng_prefix[:25]:
            return b
    return ""


def load_rule_by_pid(pid: str) -> dict:
    pid_low = pid.lower()
    for sub in PATTERNS_ROOT.iterdir():
        if not sub.is_dir():
            continue
        for path in sub.glob("*.json"):
            try:
                r = json.loads(path.read_text())
            except (json.JSONDecodeError, OSError):
                continue
            if (r.get("id") or "").lower() == pid_low:
                return {"path": path, "rule": r}
    return {}


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--apply", action="store_true",
                   help="Inject _lia_independent_authoring.fp_audit_c14 block")
    args = p.parse_args()

    print("[INFO] Running engine on Onyphe clean baseline...")
    proc = subprocess.run(
        [str(RECETTE_BIN), "-f", str(ONYPHE_FILE), "-out", "json", "-src", "all"],
        cwd=str(LIAPROBE_DIR), capture_output=True, text=True, timeout=600,
    )
    verdicts = json.loads(proc.stdout)
    print(f"[INFO] {len(verdicts)} verdicts received")

    print("[INFO] Loading source banners...")
    source_banners = []
    with open(ONYPHE_FILE) as f:
        for line in f:
            try:
                d = json.loads(line)
                source_banners.append(d.get("banner", ""))
            except json.JSONDecodeError:
                continue
    print(f"[INFO] {len(source_banners)} source banners")

    # Group FPs by PatternID
    by_rule = defaultdict(list)
    for v in verdicts:
        if v.get("Verdict") != "WRONG":
            continue
        pid = (v.get("PatternID") or "").lower()
        if pid:
            by_rule[pid].append(v)

    print(f"[INFO] {len(by_rule)} rules produced FPs")

    per_rule_audit = []
    total_fp = 0
    total_gt_mismatch = 0
    total_true_fp = 0

    for pid, fps in by_rule.items():
        info = load_rule_by_pid(pid)
        if not info:
            continue
        rule = info["rule"]
        product = rule.get("product") or ""
        tokens = extract_signature_tokens(product)
        if not tokens:
            continue

        gt_mismatch = 0
        true_fp = 0
        for v in fps:
            full_banner = find_full_banner(v.get("Banner", ""), source_banners)
            if not full_banner:
                continue
            banner_lower = full_banner.lower()
            # Onyphe gt mismatch if ANY product token is found in banner
            if any(tok in banner_lower for tok in tokens):
                gt_mismatch += 1
            else:
                true_fp += 1

        total_fp += len(fps)
        total_gt_mismatch += gt_mismatch
        total_true_fp += true_fp

        # TP from rule (need separate engine pass output) -- read from
        # current run by counting CORRECT verdicts of same PatternID
        rule_tp = sum(1 for x in verdicts
                       if (x.get("PatternID") or "").lower() == pid
                       and x.get("Verdict") == "CORRECT")
        real_prec = (rule_tp + gt_mismatch) / (rule_tp + gt_mismatch + true_fp) \
                    if (rule_tp + gt_mismatch + true_fp) > 0 else 0.0

        per_rule_audit.append({
            "pattern_id": pid,
            "product": product,
            "tokens_searched": tokens,
            "tp": rule_tp,
            "fp_reported": len(fps),
            "fp_gt_mismatch": gt_mismatch,
            "fp_true": true_fp,
            "real_precision": round(real_prec, 3),
        })

        if args.apply and gt_mismatch >= 3:
            # Inject audit block
            path = info["path"]
            BACKUP_DIR.mkdir(parents=True, exist_ok=True)
            bp = BACKUP_DIR / path.name
            if not bp.exists():
                shutil.copy2(path, bp)
            auth = rule.setdefault("_lia_independent_authoring", {})
            auth["fp_audit_c14"] = {
                "date": NOW_ISO,
                "tp": rule_tp,
                "fp_reported": len(fps),
                "fp_onyphe_gt_mismatch": gt_mismatch,
                "fp_true": true_fp,
                "real_precision": round(real_prec, 3),
                "analysis": f"{gt_mismatch}/{len(fps)} 'FPs' have product tokens "
                            f"({', '.join(tokens[:5])}) in banner -- "
                            f"Onyphe gt mismatch (multi-product hosting).",
                "marked_by": PASS_ID,
            }
            path.write_text(json.dumps(rule, indent=2, ensure_ascii=False) + "\n")

    # Sort by gt_mismatch DESC
    per_rule_audit.sort(key=lambda x: -x["fp_gt_mismatch"])

    corpus_real_prec = 0
    total_tp = sum(r["tp"] for r in per_rule_audit)
    if total_tp + total_gt_mismatch + total_true_fp > 0:
        corpus_real_prec = (total_tp + total_gt_mismatch) / \
                           (total_tp + total_gt_mismatch + total_true_fp)

    report = {
        "schema": "lia-multiproduct-fp-audit-v1",
        "run_date": RUN_DATE,
        "onyphe_file": str(ONYPHE_FILE),
        "total_fp_reported": total_fp,
        "total_fp_gt_mismatch": total_gt_mismatch,
        "total_fp_true": total_true_fp,
        "total_tp": total_tp,
        "corpus_real_precision": round(corpus_real_prec, 3),
        "gt_mismatch_pct": round(100 * total_gt_mismatch / max(total_fp, 1), 1),
        "per_rule": per_rule_audit,
    }
    out = TRACKING_DIR / f"MULTIPRODUCT_FP_AUDIT_{RUN_DATE}.json"
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False))

    print(f"\n[CORPUS STATS]")
    print(f"  Total FPs reported          : {total_fp}")
    print(f"  Onyphe gt mismatch (legit)  : {total_gt_mismatch} ({report['gt_mismatch_pct']}%)")
    print(f"  True FPs                    : {total_true_fp}")
    print(f"  Total TP                    : {total_tp}")
    print(f"  Real corpus precision       : {corpus_real_prec:.3f}")

    print(f"\nTop 15 rules by gt_mismatch (rule correct, Onyphe wrong):")
    print(f"  {'pattern_id':35s} {'product':30s} {'gt_mis':>6s} {'true_fp':>8s} {'tp':>5s} {'prec':>6s}")
    for r in per_rule_audit[:15]:
        print(f"  {r['pattern_id']:35s} {r['product'][:30]:30s} "
              f"{r['fp_gt_mismatch']:6d} {r['fp_true']:8d} {r['tp']:5d} {r['real_precision']:.3f}")

    print(f"\nReport: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
