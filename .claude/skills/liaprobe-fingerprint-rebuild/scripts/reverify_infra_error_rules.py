#!/usr/bin/env python3
# reverify_infra_error_rules.py
#
# Re-attempt HTTP verification on vendor_self_host rules whose http_gate
# previously failed with an infra error (DNS / SSL / timeout / non-200).
# These are rules currently AUTHORED + enabled but with verified=false
# and a "fetch error" note. Their regex was never confirmed against a real
# response -- they represent unverifiable patterns.
#
# Strategy:
#   1. Scan patterns/web-signatures/*.json, select target rules
#   2. Sample mode (default): re-verify N (default 5) rules, print verdict
#   3. Apply mode (--apply): re-verify ALL, update rules:
#        - persistent fetch error -> disable + mark deferred
#        - pattern failure (no match) -> disable + mark deferred
#        - pattern match -> keep enabled, update http_gate to verified=true
#
# Usage:
#   python3 reverify_infra_error_rules.py                  # sample 5, no write
#   python3 reverify_infra_error_rules.py --sample 10      # sample 10
#   python3 reverify_infra_error_rules.py --apply          # full run + writes
#   python3 reverify_infra_error_rules.py --apply --dry-run-writes  # full run, NO writes
#
# Output:
#   _alire/tracking/liaprobe-fingerprint-rebuild/REVERIFY_INFRA_ERROR_<DATE>.json

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Local skill imports
sys.path.insert(0, str(Path(__file__).resolve().parent))
from wave_validator import http_verify_rule

DEV_DIR = Path("/opt/lia-sec/dev")
LIAPROBE_DIR = Path("/opt/lia-sec/liaprobe")
PATTERNS_DIR = LIAPROBE_DIR / "patterns/web-signatures"
TRACKING_DIR = DEV_DIR / "_alire/tracking/liaprobe-fingerprint-rebuild"
MASTER_TODO = TRACKING_DIR / "MASTER_TODO_LIST.md"

RUN_DATE = datetime.now(timezone.utc).strftime("%Y-%m-%d")


def is_target_rule(rule: dict) -> bool:
    """A target rule is enabled, vendor_self_host, with http_gate fetch error."""
    if not rule.get("enabled", False):
        return False
    arts = rule.get("artifacts", {})
    if arts.get("observation_provenance") != "vendor_self_host":
        return False
    gate = rule.get("_lia_independent_authoring", {}).get("http_gate", {})
    if gate.get("verified", False):
        return False
    note = (gate.get("note") or "").lower()
    return "fetch error" in note


def scan_target_rules() -> list:
    """Return list of (path, rule) tuples for all target rules."""
    targets = []
    for path in sorted(PATTERNS_DIR.glob("*.json")):
        try:
            with open(path) as f:
                rule = json.load(f)
        except (json.JSONDecodeError, OSError):
            continue
        if is_target_rule(rule):
            targets.append((path, rule))
    return targets


def classify_result(result: dict) -> str:
    """Map http_verify_rule result to one of: VERIFIED, PATTERN_FAILURE, INFRA_ERROR_PERSISTENT."""
    if result.get("verified"):
        return "VERIFIED"
    if not result.get("tested"):
        return "NOT_TESTABLE"  # no vendor_website or no matchers
    note = (result.get("note") or "").lower()
    if "fetch error" in note:
        return "INFRA_ERROR_PERSISTENT"
    if "no match" in note:
        return "PATTERN_FAILURE"
    return "UNKNOWN"


def update_rule_on_disk(path: Path, rule: dict, verdict: str, result: dict,
                       dry_run: bool) -> str:
    """Apply rule update based on verdict. Return 'modified' | 'unchanged' | 'dry-run'."""
    gate = rule.setdefault("_lia_independent_authoring", {}).setdefault("http_gate", {})
    gate["date"] = RUN_DATE
    gate["verified"] = result.get("verified", False)
    gate["http_status"] = result.get("status", 0)
    gate["note"] = result.get("note", "")
    gate["reverify_pass"] = "2026-05-12_apex_c4"

    if verdict == "VERIFIED":
        # Pattern works, keep enabled, propagate body_sha256
        arts = rule.setdefault("artifacts", {})
        if result.get("body_sha256") and not arts.get("html_sha256"):
            arts["html_sha256"] = result["body_sha256"]

    elif verdict in ("PATTERN_FAILURE", "INFRA_ERROR_PERSISTENT"):
        rule["enabled"] = False
        gate["disabled_reason"] = (
            "reverify_pass_pattern_failure" if verdict == "PATTERN_FAILURE"
            else "reverify_pass_infra_persistent"
        )
    else:
        return "unchanged"

    if dry_run:
        return "dry-run"

    with open(path, "w") as f:
        json.dump(rule, f, indent=2, ensure_ascii=False)
    return "modified"


def mark_deferred_in_master_todo(taxonomy_code: str, reason: str) -> None:
    """Set MASTER_TODO line for code from AUTHORED back to FILE_ONLY."""
    txt = MASTER_TODO.read_text()
    old = f"| [x] AUTHORED | {taxonomy_code} |"
    if old not in txt:
        return
    # Convert AUTHORED line to FILE_ONLY w/ reverify reason in comment column
    import re
    pat = re.compile(rf"\| \[x\] AUTHORED \| {re.escape(taxonomy_code)} \| [^|]+ \| [^|]+ \|")
    new_line = f"| [.] FILE_ONLY | {taxonomy_code} | reverify_{RUN_DATE} | {reason} |"
    new_txt = pat.sub(new_line, txt)
    if new_txt != txt:
        MASTER_TODO.write_text(new_txt)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--sample", type=int, default=5,
                        help="Sample size when not in --apply mode (default: 5)")
    parser.add_argument("--apply", action="store_true",
                        help="Run on ALL targets and write changes to disk")
    parser.add_argument("--dry-run-writes", action="store_true",
                        help="With --apply: do not write files, only show plan")
    parser.add_argument("--sleep", type=float, default=1.0,
                        help="Sleep between HTTP calls to be polite (default: 1.0s)")
    args = parser.parse_args()

    targets = scan_target_rules()
    total = len(targets)
    print(f"[INFO] Found {total} target rules (vendor_self_host + enabled + http_gate infra error)")

    if not args.apply:
        # Sample mode: print verdicts only, no writes
        import random
        random.seed(42)
        sample = random.sample(targets, min(args.sample, total))
        print(f"[INFO] Sample mode: verifying {len(sample)} rules (no writes)\n")
        verdict_counts = {}
        for i, (path, rule) in enumerate(sample, 1):
            code = rule.get("taxonomy_code", path.stem)
            vendor = rule.get("vendor_website") or rule.get(
                "_lia_independent_authoring", {}).get("vendor_website", "")
            print(f"[{i}/{len(sample)}] {code} ({vendor})")
            try:
                result = http_verify_rule(rule)
            except Exception as e:
                print(f"    EXCEPTION: {e}")
                continue
            verdict = classify_result(result)
            verdict_counts[verdict] = verdict_counts.get(verdict, 0) + 1
            print(f"    -> {verdict} :: {result.get('note', '')[:120]}")
            time.sleep(args.sleep)

        print("\n[SUMMARY]")
        for k, v in sorted(verdict_counts.items()):
            print(f"  {k}: {v}")
        print(f"\nRun with --apply to process all {total} targets and write changes.")
        return 0

    # Apply mode: full run + writes
    print(f"[INFO] Apply mode: processing all {total} targets")
    if args.dry_run_writes:
        print("[INFO] --dry-run-writes: no files will be modified")

    report = {
        "schema": "lia-reverify-infra-error-v1",
        "run_date": RUN_DATE,
        "total_targets": total,
        "results": [],
        "summary": {"VERIFIED": 0, "PATTERN_FAILURE": 0,
                    "INFRA_ERROR_PERSISTENT": 0, "NOT_TESTABLE": 0, "UNKNOWN": 0},
    }
    for i, (path, rule) in enumerate(targets, 1):
        code = rule.get("taxonomy_code", path.stem)
        if i % 25 == 0:
            print(f"  [{i}/{total}] processing {code}...")
        try:
            result = http_verify_rule(rule)
        except Exception as e:
            report["results"].append({"code": code, "verdict": "EXCEPTION",
                                      "note": str(e)})
            continue
        verdict = classify_result(result)
        report["summary"][verdict] = report["summary"].get(verdict, 0) + 1

        action = update_rule_on_disk(path, rule, verdict, result, args.dry_run_writes)
        report["results"].append({
            "code": code,
            "verdict": verdict,
            "note": result.get("note", "")[:200],
            "http_status": result.get("status", 0),
            "action": action,
        })
        if verdict in ("PATTERN_FAILURE", "INFRA_ERROR_PERSISTENT") and not args.dry_run_writes:
            mark_deferred_in_master_todo(code, f"reverify_{verdict.lower()}")
        time.sleep(args.sleep)

    report_path = TRACKING_DIR / f"REVERIFY_INFRA_ERROR_{RUN_DATE}.json"
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print(f"\n[SUMMARY]")
    for k, v in sorted(report["summary"].items()):
        print(f"  {k}: {v}")
    print(f"\nReport: {report_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
