#!/usr/bin/env python3
# mark_vendor_dead.py
#
# DEPRECATED (c68 / A99 -- retired 2026-05-15). DO NOT USE.
#
# Cycle 52 audit (verify_vendor_alive.py) proved this Cycle 5 script
# classified vendors as "dead" using FAKE vendor_website URLs (template
# https://www.<product_slug>.com) WITHOUT any real HTTP fetch. A 5-sample
# spot-check found 5/5 of those "dead" vendors actually ALIVE under their
# correct URLs (a 79% false-positive class). The marking is destructive:
# the nightly batch SKIPS any rule carrying the vendor_dead block, so a
# falsely-marked rule is frozen out of the re-author loop permanently.
#
# This is an R18 violation (classification asserted without verification).
# It is superseded by:
#   - scripts/verify_vendor_alive.py    (c52 -- real URL-guessing re-audit)
#   - scripts/reverify_no_http_gate.py  (correct live-verify pattern:
#                                         marks vendor_dead ONLY after a
#                                         real http_verify_rule outcome)
#
# main() now hard-exits with code 2 before parsing args or scanning any
# file. The original logic is preserved below, unrun, for git history /
# forensic only. Do not remove the guard.
#
# --- ORIGINAL HEADER (historical) ---
# Add a `vendor_dead` block to rules whose http_gate.disabled_reason marks
# the vendor as permanently unreachable. The nightly batch skips rules
# carrying this block to avoid re-author loops on dead vendors.
#
# Schema added under `_lia_independent_authoring`:
#   "vendor_dead": {
#       "since": "<ISO8601>",
#       "reason": "infra_persistent",
#       "evidence": "<http_gate.note copied>",
#       "marked_by": "mark_vendor_dead.py <pass_id>"
#   }
#
# Future audit can reconsider: scan rules where (now - vendor_dead.since) > N days,
# re-run http_verify_rule, remove block if vendor responds.
#
# Usage:
#   python3 mark_vendor_dead.py --dry-run        # print actions, no writes
#   python3 mark_vendor_dead.py --apply          # write changes
#   python3 mark_vendor_dead.py --apply --reason-prefix reverify_pass_infra
#       (default reason-prefix matches c4 reverify pass)

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

LIAPROBE_DIR = Path("/opt/lia-sec/liaprobe")
PATTERNS_DIR = LIAPROBE_DIR / "patterns/web-signatures"

NOW_ISO = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def is_dead_vendor_candidate(rule: dict, reason_prefix: str) -> bool:
    """Rule already disabled with infra_persistent reason and no vendor_dead block."""
    if rule.get("enabled", True):
        return False
    auth = rule.get("_lia_independent_authoring", {})
    if auth.get("vendor_dead"):
        return False  # already marked
    gate = auth.get("http_gate", {})
    reason = gate.get("disabled_reason", "")
    return reason.startswith(reason_prefix)


def add_vendor_dead_block(rule: dict, pass_id: str) -> dict:
    """Add vendor_dead block in-place, return modified rule."""
    auth = rule.setdefault("_lia_independent_authoring", {})
    gate = auth.get("http_gate", {})
    auth["vendor_dead"] = {
        "since": NOW_ISO,
        "reason": "infra_persistent",
        "evidence": gate.get("note", "")[:240],
        "marked_by": f"mark_vendor_dead.py {pass_id}",
    }
    return rule


def main():
    # DEPRECATED c68 / A99. Unconditional hard-exit BEFORE arg parse,
    # file scan, or any write. Neither --apply nor --dry-run can bypass
    # this guard. See module header for the c52 79%-FP rationale.
    print(
        "mark_vendor_dead.py is DEPRECATED (c68 / A99, retired 2026-05-15) "
        "and refuses to run.\n"
        "Reason: c52 proved it classified vendors dead on fake "
        "vendor_website URLs without a real HTTP fetch (79% FP, "
        "destructive vendor_dead write).\n"
        "Use scripts/verify_vendor_alive.py (re-audit) or "
        "scripts/reverify_no_http_gate.py (correct live-verify pattern) "
        "instead.",
        file=sys.stderr,
    )
    return 2

    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--apply", action="store_true", help="Write changes to disk")
    parser.add_argument("--dry-run", action="store_true", help="Print actions only")
    parser.add_argument("--reason-prefix", default="reverify_pass_infra",
                        help="http_gate.disabled_reason prefix selector (default: reverify_pass_infra)")
    parser.add_argument("--pass-id", default="2026-05-12_apex_c5",
                        help="Identifier stored in vendor_dead.marked_by")
    args = parser.parse_args()

    if not args.apply and not args.dry_run:
        parser.error("Must specify --apply or --dry-run")

    targets = []
    for path in sorted(PATTERNS_DIR.glob("*.json")):
        try:
            rule = json.loads(path.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        if is_dead_vendor_candidate(rule, args.reason_prefix):
            targets.append((path, rule))

    print(f"[INFO] Found {len(targets)} dead-vendor candidates "
          f"(disabled + reason starts with {args.reason_prefix!r} + no vendor_dead block yet)")

    if not targets:
        return 0

    modified = 0
    for path, rule in targets:
        code = rule.get("taxonomy_code", path.stem)
        if args.dry_run:
            gate_note = rule.get("_lia_independent_authoring", {}).get("http_gate", {}).get("note", "")
            print(f"  DRY-RUN  {code}: would mark vendor_dead (evidence: {gate_note[:80]})")
            continue
        add_vendor_dead_block(rule, args.pass_id)
        path.write_text(json.dumps(rule, indent=2, ensure_ascii=False) + "\n")
        modified += 1

    if args.apply:
        print(f"[SUMMARY] modified {modified} rule files")
    else:
        print(f"[SUMMARY] would modify {len(targets)} rule files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
