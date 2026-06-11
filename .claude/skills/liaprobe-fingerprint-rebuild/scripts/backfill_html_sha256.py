#!/usr/bin/env python3
# backfill_html_sha256.py
#
# Populate artifacts.html_sha256 on vendor_self_host rules currently missing
# the field. Captures body sha256 from live HTTP response ONLY when the
# matched signal is `header` or `cookie` (proof the vendor self-hosts its
# product on the captured URL). Body / title matches do NOT trigger hash
# capture because they could match marketing-site content (per user
# preference: the hash signs the SOLUTION, not the vendor marketing site).
#
# Scope: vendor_self_host + html_sha256 is None + enabled.
# Default batch limit: 100 rules per run (--limit to override).
# Sample-of-5 confirmation before mass run.
#
# Usage:
#   python3 backfill_html_sha256.py --sample 5
#   python3 backfill_html_sha256.py --apply --limit 100 --sleep 0.4
#   python3 backfill_html_sha256.py --apply --limit 1000   # full corpus

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from wave_validator import http_verify_rule

LIAPROBE_DIR = Path("/opt/lia-sec/liaprobe")
PATTERNS_DIR = LIAPROBE_DIR / "patterns/web-signatures"
DEV_DIR = Path("/opt/lia-sec/dev")
TRACKING_DIR = DEV_DIR / "_alire/tracking/liaprobe-fingerprint-rebuild"

RUN_DATE = datetime.now(timezone.utc).strftime("%Y-%m-%d")
PASS_ID = "2026-05-12_apex_c5_backfill_sha256"


def is_target(rule: dict) -> bool:
    if not rule.get("enabled", False):
        return False
    arts = rule.get("artifacts", {})
    if arts.get("observation_provenance") != "vendor_self_host":
        return False
    return arts.get("html_sha256") is None


def scan_targets(limit: int = 0) -> list:
    targets = []
    for path in sorted(PATTERNS_DIR.glob("*.json")):
        try:
            rule = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        if is_target(rule):
            targets.append((path, rule))
            if limit and len(targets) >= limit:
                break
    return targets


def classify_for_backfill(result: dict) -> str:
    """Outcome categories for the backfill pass."""
    if not result.get("verified"):
        if not result.get("tested"):
            return "NOT_TESTED"
        note = (result.get("note") or "").lower()
        if "fetch error" in note:
            return "INFRA_ERROR"
        if "no match" in note:
            return "PATTERN_FAILURE"
        return "UNKNOWN"
    sc = result.get("verified_signal_class")
    if sc in ("header", "cookie"):
        return "BACKFILL_OK"
    return "VERIFIED_BUT_BODY_ONLY"  # can't backfill -- body match != solution proof


def update_rule(path: Path, rule: dict, verdict: str, result: dict, dry: bool) -> str:
    auth = rule.setdefault("_lia_independent_authoring", {})
    gate = auth.setdefault("http_gate", {})
    gate["date"] = RUN_DATE
    gate["verified"] = result.get("verified", False)
    gate["http_status"] = result.get("status", 0)
    gate["note"] = result.get("note", "")
    gate["reverify_pass"] = PASS_ID

    changed = False
    if verdict == "BACKFILL_OK":
        arts = rule.setdefault("artifacts", {})
        arts["html_sha256"] = result["body_sha256"]
        gate["html_sha256_source"] = "live_capture_header_match"
        changed = True
    elif verdict == "PATTERN_FAILURE":
        rule["enabled"] = False
        gate["disabled_reason"] = "backfill_pattern_failure"
        changed = True
    elif verdict == "INFRA_ERROR":
        rule["enabled"] = False
        gate["disabled_reason"] = "backfill_infra_persistent"
        auth["vendor_dead"] = {
            "since": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "reason": "infra_persistent",
            "evidence": result.get("note", "")[:240],
            "marked_by": f"backfill_html_sha256.py {PASS_ID}",
        }
        changed = True
    # VERIFIED_BUT_BODY_ONLY: record gate metadata but do NOT capture hash

    if not changed:
        # Still record http_gate for audit even when no rule state change.
        if dry:
            return "dry-run"
        path.write_text(json.dumps(rule, indent=2, ensure_ascii=False) + "\n")
        return "audit-only"

    if dry:
        return "dry-run"
    path.write_text(json.dumps(rule, indent=2, ensure_ascii=False) + "\n")
    return "modified"


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--sample", type=int, default=5)
    p.add_argument("--apply", action="store_true")
    p.add_argument("--limit", type=int, default=100,
                   help="Max rules per run when --apply (default 100, 0 = no limit)")
    p.add_argument("--sleep", type=float, default=0.4)
    p.add_argument("--dry-run-writes", action="store_true")
    args = p.parse_args()

    targets_all = scan_targets(limit=0)
    print(f"[INFO] Total scope (vendor_self_host + html_sha256=null + enabled): {len(targets_all)}")

    if not args.apply:
        import random
        random.seed(42)
        sample = random.sample(targets_all, min(args.sample, len(targets_all)))
        print(f"[INFO] Sample mode: {len(sample)} rules (no writes)\n")
        vc = {}
        for i, (path, rule) in enumerate(sample, 1):
            code = rule.get("taxonomy_code", path.stem)
            vendor = rule.get("vendor_website") or rule.get(
                "_lia_independent_authoring", {}).get("vendor_website", "")
            print(f"[{i}/{len(sample)}] {code} ({vendor})")
            try:
                r = http_verify_rule(rule)
            except Exception as e:
                print(f"    EXCEPTION: {e}")
                continue
            v = classify_for_backfill(r)
            vc[v] = vc.get(v, 0) + 1
            sc = r.get("verified_signal_class")
            print(f"    -> {v} (signal: {sc}) :: {r.get('note', '')[:100]}")
            time.sleep(args.sleep)
        print("\n[SUMMARY]")
        for k, v in sorted(vc.items()):
            print(f"  {k}: {v}")
        print(f"\nRun with --apply to process up to --limit (default 100) rules.")
        return 0

    targets = targets_all[:args.limit] if args.limit else targets_all
    print(f"[INFO] Apply mode: processing {len(targets)} of {len(targets_all)} targets "
          f"(limit={args.limit if args.limit else 'none'})")
    if args.dry_run_writes:
        print("[INFO] --dry-run-writes: no files will be modified")

    report = {
        "schema": "lia-backfill-html-sha256-v1",
        "run_date": RUN_DATE,
        "pass_id": PASS_ID,
        "scope_total": len(targets_all),
        "processed": len(targets),
        "limit": args.limit,
        "results": [],
        "summary": {"BACKFILL_OK": 0, "VERIFIED_BUT_BODY_ONLY": 0,
                    "PATTERN_FAILURE": 0, "INFRA_ERROR": 0,
                    "NOT_TESTED": 0, "UNKNOWN": 0},
    }
    for i, (path, rule) in enumerate(targets, 1):
        code = rule.get("taxonomy_code", path.stem)
        if i % 25 == 0:
            print(f"  [{i}/{len(targets)}] {code}...")
        try:
            r = http_verify_rule(rule)
        except Exception as e:
            report["results"].append({"code": code, "verdict": "EXCEPTION", "note": str(e)})
            continue
        v = classify_for_backfill(r)
        report["summary"][v] = report["summary"].get(v, 0) + 1
        action = update_rule(path, rule, v, r, args.dry_run_writes)
        report["results"].append({
            "code": code, "verdict": v,
            "note": r.get("note", "")[:200],
            "http_status": r.get("status", 0),
            "signal_class": r.get("verified_signal_class"),
            "action": action,
        })
        time.sleep(args.sleep)

    report_path = TRACKING_DIR / f"BACKFILL_HTML_SHA256_{RUN_DATE}.json"
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print("\n[SUMMARY]")
    for k, v in sorted(report["summary"].items()):
        print(f"  {k}: {v}")
    print(f"\nReport: {report_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
