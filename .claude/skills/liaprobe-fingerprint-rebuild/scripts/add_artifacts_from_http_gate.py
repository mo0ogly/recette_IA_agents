#!/usr/bin/env python3
"""Add artifacts block to authored LiaProbe rules that are missing it.

Walks all rules in patterns/web-signatures/ that have _lia_independent_authoring
but NO artifacts sub-block. Derives observation_provenance from:
  - http_gate.verified=true  -> vendor_self_host
  - http_gate.verified=false, status=200 -> INDETERMINATE
  - http_gate.verified=false, status!=200 -> UNREACHABLE
  - no http_gate -> live HTTP verify via http_verifier (or UNVERIFIED_FALLBACK if --no-http)

CRITICAL: sets auth["artifacts"] unconditionally (retrofit_capture_url.py bug fix:
that script only updates if key already exists, so it cannot patch old-schema rules).

Usage:
    python3 add_artifacts_from_http_gate.py [--dry-run] [--no-http] [--verbose]
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

# Import HTTP verifier from the same scripts/ directory
sys.path.insert(0, str(Path(__file__).parent))
from http_verifier import load_http_cache, save_http_cache, verify_vendor_self_host

PATTERNS_ROOT = Path("/opt/lia-sec/liaprobe/patterns/web-signatures")
AUDIT_LOG = Path(
    "/opt/lia-sec/dev/_alire/tracking/"
    "PLAN_LIAPROBE_AUDIT_RETROACTIF_2026-05-07_audit_retroactif.jsonl"
)
HTTP_CACHE_PATH = Path(
    "/opt/lia-sec/dev/_alire/tracking/"
    "PLAN_LIAPROBE_AUDIT_RETROACTIF_2026-05-07_http_verification_cache.json"
)

HTTP_CACHE_SAVE_INTERVAL = 50


def provenance_from_http_gate(http_gate: dict | None) -> str:
    """Derive observation_provenance from existing http_gate dict."""
    if not http_gate:
        return "UNVERIFIED_FALLBACK"
    if http_gate.get("verified") is True:
        return "vendor_self_host"
    status = http_gate.get("http_status", 0)
    if status == 200:
        return "INDETERMINATE"
    return "UNREACHABLE"


def patch_rule(
    rule_path: Path,
    http_cache: dict,
    dry_run: bool,
    verbose: bool,
    no_http: bool,
) -> dict:
    """Add artifacts block to a single rule. Returns outcome dict."""
    try:
        with rule_path.open("r", encoding="utf-8") as f:
            rule = json.load(f)
    except Exception as e:
        return {"file": rule_path.name, "verdict": "READ_ERROR", "error": str(e)}

    auth = rule.get("_lia_independent_authoring")
    if not isinstance(auth, dict):
        return {"file": rule_path.name, "verdict": "NOT_AUTHORED"}

    # Skip rules that already have a proper artifacts block
    existing_artifacts = auth.get("artifacts")
    if isinstance(existing_artifacts, dict) and existing_artifacts.get("observation_provenance"):
        return {
            "file": rule_path.name,
            "verdict": "SKIPPED_HAS_ARTIFACTS",
            "reason": f"provenance={existing_artifacts['observation_provenance']!r}",
        }

    rule_id = rule.get("id", rule_path.stem)
    vendor_website = auth.get("vendor_website") or rule.get("vendor_website", "")
    http_gate = auth.get("http_gate") if isinstance(auth.get("http_gate"), dict) else None

    provenance = provenance_from_http_gate(http_gate)
    http_status = http_gate.get("http_status") if http_gate else None
    server_header = http_gate.get("note", "") if http_gate else ""

    # For UNVERIFIED_FALLBACK (no http_gate), do live HTTP verify if allowed
    if provenance == "UNVERIFIED_FALLBACK" and not no_http and vendor_website:
        live_verdict, live_server, live_status = verify_vendor_self_host(
            rule_id, vendor_website, http_cache
        )
        provenance = live_verdict
        server_header = live_server or ""
        http_status = live_status

    # Unconditionally set artifacts (fixes retrofit_capture_url.py conditional bug)
    artifacts: dict = {
        "capture_url": vendor_website,
        "observation_provenance": provenance,
    }

    auth["artifacts"] = artifacts
    rule["_lia_independent_authoring"] = auth

    if verbose:
        print(f"  {rule_path.name}: {provenance} (url={vendor_website[:60]})")

    if not dry_run:
        try:
            rule_path.write_text(
                json.dumps(rule, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
        except Exception as e:
            return {"file": rule_path.name, "verdict": "WRITE_ERROR", "error": str(e)}

    return {
        "file": rule_path.name,
        "rule_id": rule_id,
        "vendor_website": vendor_website,
        "observation_provenance": provenance,
        "source": "http_gate" if http_gate else ("http_live" if not no_http else "no_http"),
        "verdict": "DRY_RUN" if dry_run else "PATCHED",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Do not write changes")
    parser.add_argument("--no-http", action="store_true", help="Skip live HTTP verification")
    parser.add_argument("--verbose", "-v", action="store_true", help="Print each patched rule")
    args = parser.parse_args()

    if not PATTERNS_ROOT.is_dir():
        print(f"FATAL: {PATTERNS_ROOT} not found", file=sys.stderr)
        sys.exit(2)

    http_cache = load_http_cache(HTTP_CACHE_PATH)
    print(f"HTTP cache loaded: {len(http_cache)} entries")

    counts: dict[str, int] = {
        "PATCHED": 0,
        "DRY_RUN": 0,
        "SKIPPED_HAS_ARTIFACTS": 0,
        "NOT_AUTHORED": 0,
        "READ_ERROR": 0,
        "WRITE_ERROR": 0,
    }
    provenance_counts: dict[str, int] = {}
    results = []
    rules_since_save = 0

    rule_files = sorted(PATTERNS_ROOT.glob("*.json"))
    total = len(rule_files)
    print(f"Scanning {total} rule files...")

    for i, rule_path in enumerate(rule_files):
        outcome = patch_rule(rule_path, http_cache, args.dry_run, args.verbose, args.no_http)
        outcome["timestamp"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        results.append(outcome)

        v = outcome.get("verdict", "")
        if v in counts:
            counts[v] += 1

        prov = outcome.get("observation_provenance")
        if prov:
            provenance_counts[prov] = provenance_counts.get(prov, 0) + 1

        rules_since_save += 1
        if rules_since_save >= HTTP_CACHE_SAVE_INTERVAL and not args.dry_run:
            save_http_cache(http_cache, HTTP_CACHE_PATH)
            rules_since_save = 0

        if (i + 1) % 500 == 0:
            done = counts["PATCHED"] + counts["DRY_RUN"]
            print(f"  [{i+1}/{total}] patched/dry: {done}, skipped: {counts['SKIPPED_HAS_ARTIFACTS']}")

    # Final cache save
    if not args.dry_run:
        save_http_cache(http_cache, HTTP_CACHE_PATH)

    # Append to audit log (never overwrite)
    AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
    with AUDIT_LOG.open("a", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    mode_label = "DRY-RUN" if args.dry_run else "WRITE"
    print(f"\n=== add_artifacts_from_http_gate summary ({mode_label}) ===")
    print(f"Total rule files scanned: {total}")
    for k, v in counts.items():
        if v > 0:
            print(f"  {k}: {v}")
    print("\nProvenance distribution (patched rules):")
    for prov, cnt in sorted(provenance_counts.items(), key=lambda x: -x[1]):
        print(f"  {prov}: {cnt}")
    print(f"\nAudit log: {AUDIT_LOG}")
    print(f"HTTP cache: {len(http_cache)} entries")


if __name__ == "__main__":
    main()
