#!/usr/bin/env python3
# reverify_no_http_gate.py
#
# Re-verify vendor_self_host rules that have never been live-tested
# (no http_gate field at all on disk). These are pre-pipeline rules from
# earlier nightly runs that escaped the http-gate audit.
#
# Strategy: same as reverify_infra_error_rules.py, but with a different
# selector. Reuses http_verify_rule for HTTP testing.
#
# Outcomes per rule:
#   VERIFIED                   -> keep enabled, set http_gate.verified=true,
#                                 capture body_sha256 -> html_sha256
#   PATTERN_FAILURE            -> disable + disabled_reason="reverify2_pattern_failure"
#   INFRA_ERROR_PERSISTENT     -> disable + disabled_reason="reverify2_infra_persistent"
#                                 + write vendor_dead block inline (this is
#                                   the correct pattern: marked ONLY after a
#                                   real http_verify_rule outcome, not a slug
#                                   URL guess -- see main loop below)
#
# Usage:
#   python3 reverify_no_http_gate.py --sample 5
#   python3 reverify_no_http_gate.py --apply --sleep 0.5

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
NOW_ISO = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
PASS_ID = "2026-05-12_apex_c5_no_http_gate"


def is_target(rule: dict) -> bool:
    """Target: enabled vendor_self_host with NO http_gate field at all."""
    if not rule.get("enabled", False):
        return False
    arts = rule.get("artifacts", {})
    if arts.get("observation_provenance") != "vendor_self_host":
        return False
    auth = rule.get("_lia_independent_authoring", {})
    return "http_gate" not in auth


def scan_targets() -> list:
    targets = []
    for path in sorted(PATTERNS_DIR.glob("*.json")):
        try:
            rule = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        if is_target(rule):
            targets.append((path, rule))
    return targets


def classify(result: dict) -> str:
    if result.get("verified"):
        return "VERIFIED"
    if not result.get("tested"):
        return "NOT_TESTABLE"
    note = (result.get("note") or "").lower()
    if "fetch error" in note:
        return "INFRA_ERROR_PERSISTENT"
    if "no match" in note:
        return "PATTERN_FAILURE"
    return "UNKNOWN"


def update_rule(path: Path, rule: dict, verdict: str, result: dict, dry: bool) -> str:
    auth = rule.setdefault("_lia_independent_authoring", {})
    gate = auth.setdefault("http_gate", {})
    gate["date"] = RUN_DATE
    gate["verified"] = result.get("verified", False)
    gate["http_status"] = result.get("status", 0)
    gate["note"] = result.get("note", "")
    gate["reverify_pass"] = PASS_ID

    if verdict == "VERIFIED":
        arts = rule.setdefault("artifacts", {})
        # Capture body hash ONLY from header/cookie matches (proof of self-host).
        # Body/title matches do not prove the captured page IS the product.
        signal_class = result.get("verified_signal_class")
        if signal_class in ("header", "cookie") and result.get("body_sha256") and not arts.get("html_sha256"):
            arts["html_sha256"] = result["body_sha256"]
            gate["html_sha256_source"] = "live_capture_header_match"
    elif verdict == "PATTERN_FAILURE":
        rule["enabled"] = False
        gate["disabled_reason"] = "reverify2_pattern_failure"
    elif verdict == "INFRA_ERROR_PERSISTENT":
        rule["enabled"] = False
        gate["disabled_reason"] = "reverify2_infra_persistent"
        # Mark vendor_dead in same pass
        auth["vendor_dead"] = {
            "since": NOW_ISO,
            "reason": "infra_persistent",
            "evidence": result.get("note", "")[:240],
            "marked_by": f"reverify_no_http_gate.py {PASS_ID}",
        }
    else:
        return "unchanged"

    if dry:
        return "dry-run"
    path.write_text(json.dumps(rule, indent=2, ensure_ascii=False) + "\n")
    return "modified"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--sample", type=int, default=5)
    p.add_argument("--apply", action="store_true")
    p.add_argument("--dry-run-writes", action="store_true")
    p.add_argument("--sleep", type=float, default=0.5)
    args = p.parse_args()

    targets = scan_targets()
    total = len(targets)
    print(f"[INFO] Found {total} target rules (vendor_self_host + enabled + no http_gate field)")

    if not args.apply:
        import random
        random.seed(42)
        sample = random.sample(targets, min(args.sample, total))
        print(f"[INFO] Sample mode: verifying {len(sample)} rules (no writes)\n")
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
            v = classify(r)
            vc[v] = vc.get(v, 0) + 1
            print(f"    -> {v} :: {r.get('note', '')[:120]}")
            time.sleep(args.sleep)
        print("\n[SUMMARY]")
        for k, v in sorted(vc.items()):
            print(f"  {k}: {v}")
        print(f"\nRun with --apply to process all {total} targets.")
        return 0

    print(f"[INFO] Apply mode: processing all {total} targets")
    if args.dry_run_writes:
        print("[INFO] --dry-run-writes: no files will be modified")

    report = {
        "schema": "lia-reverify-no-http-gate-v1",
        "run_date": RUN_DATE,
        "pass_id": PASS_ID,
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
            r = http_verify_rule(rule)
        except Exception as e:
            report["results"].append({"code": code, "verdict": "EXCEPTION", "note": str(e)})
            continue
        v = classify(r)
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

    report_path = TRACKING_DIR / f"REVERIFY_NO_HTTP_GATE_{RUN_DATE}.json"
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print("\n[SUMMARY]")
    for k, v in sorted(report["summary"].items()):
        print(f"  {k}: {v}")
    print(f"\nReport: {report_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
