#!/usr/bin/env python3
"""Retrofit artifacts.capture_url and artifacts.observation_provenance into rules.

Walks all rules in patterns/web-signatures/ that have _lia_independent_authoring
block but missing artifacts.capture_url. For each rule:

1. Look for captures/{PRODUCT}/MANIFEST.json -- read URL from any field in URL_KEYS
2. Fallback to rule.vendor_website if no MANIFEST.json
3. Mark SUSPECT if no provenance evidence available

Output:
- Patches each rule.json in-place with artifacts.capture_url + observation_provenance
- Writes audit_retroactif.jsonl with one line per rule classified

Usage:
    python3 retrofit_capture_url.py [--dry-run] [--limit N] [--verify-http]
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from http_verifier import load_http_cache, save_http_cache, verify_vendor_self_host
from provenance_classifier import classify_provenance
from url_extractor import find_capture_url

PATTERNS_ROOT = Path("/opt/lia-sec/liaprobe/patterns/web-signatures")
CAPTURES_ROOT = PATTERNS_ROOT / "captures"
AUDIT_LOG = Path(
    "/opt/lia-sec/dev/_alire/tracking/"
    "PLAN_LIAPROBE_AUDIT_RETROACTIF_2026-05-07_audit_retroactif.jsonl"
)
HTTP_VERIFICATION_CACHE = Path(
    "/opt/lia-sec/dev/_alire/tracking/"
    "PLAN_LIAPROBE_AUDIT_RETROACTIF_2026-05-07_http_verification_cache.json"
)


def retrofit_rule(
    rule_path: Path,
    dry_run: bool = False,
    http_cache: dict | None = None,
    verify_http: bool = False,
) -> dict:
    """Patch a single rule with capture_url + observation_provenance.

    Returns dict with retrofit outcome.
    """
    try:
        with rule_path.open("r", encoding="utf-8") as f:
            rule = json.load(f)
    except Exception as e:
        return {"file": str(rule_path), "verdict": "READ_ERROR", "error": str(e)}

    auth = rule.get("_lia_independent_authoring")
    if not isinstance(auth, dict):
        return {"file": rule_path.name, "verdict": "NOT_AUTHORED"}

    artifacts = auth.get("artifacts") or rule.get("artifacts") or {}
    if not isinstance(artifacts, dict):
        artifacts = {}

    rule_id = rule.get("id", rule_path.stem)
    vendor_website = rule.get("vendor_website") or auth.get("vendor_website")
    existing_url = artifacts.get("capture_url") or rule.get("artifacts", {}).get(
        "capture_url"
    )

    capture_url, url_source, manifest_path = find_capture_url(
        rule_id,
        CAPTURES_ROOT,
        existing_url=existing_url,
        vendor_website=vendor_website,
    )

    provenance = classify_provenance(rule_id, vendor_website, capture_url, url_source)

    server_header = None
    http_status = 0
    if (
        verify_http
        and provenance in ("UNVERIFIED_FALLBACK", "SUSPECT_MARKETING")
        and http_cache is not None
    ):
        verified, server_header, http_status = verify_vendor_self_host(
            rule_id, vendor_website, http_cache
        )
        if verified in ("vendor_self_host", "SUSPECT_MARKETING", "UNREACHABLE", "INDETERMINATE"):
            provenance = verified

    artifacts["capture_url"] = capture_url or ""
    artifacts["observation_provenance"] = provenance

    if "artifacts" in auth:
        auth["artifacts"] = artifacts
    if "artifacts" in rule:
        rule["artifacts"] = artifacts

    rule["_lia_independent_authoring"] = auth

    if not dry_run:
        try:
            rule_path.write_text(
                json.dumps(rule, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
        except Exception as e:
            return {"file": rule_path.name, "verdict": "WRITE_ERROR", "error": str(e)}

    verdict = (
        "PATCHED" if not dry_run and capture_url else
        "PATCHED_NO_URL" if not dry_run else
        "DRY_RUN_PATCH" if capture_url else "DRY_RUN_NO_URL"
    )

    return {
        "file": rule_path.name,
        "rule_id": rule_id,
        "vendor_website": vendor_website,
        "capture_url": capture_url,
        "url_source": url_source,
        "manifest_path": str(manifest_path) if manifest_path else None,
        "observation_provenance": provenance,
        "verified_server": server_header,
        "verified_status": http_status,
        "verdict": verdict,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Do not write changes")
    parser.add_argument(
        "--limit", type=int, default=0, help="Process at most N rules (0 = all)"
    )
    parser.add_argument(
        "--verify-http",
        action="store_true",
        help="HTTP verify Server header for UNVERIFIED_FALLBACK rules (cached)",
    )
    args = parser.parse_args()

    if not PATTERNS_ROOT.is_dir():
        print(f"FATAL: {PATTERNS_ROOT} not found", file=sys.stderr)
        sys.exit(2)

    rules = sorted(PATTERNS_ROOT.glob("*.json"))
    if args.limit:
        rules = rules[: args.limit]

    counts = {
        "PATCHED": 0,
        "PATCHED_NO_URL": 0,
        "DRY_RUN_PATCH": 0,
        "DRY_RUN_NO_URL": 0,
        "NOT_AUTHORED": 0,
        "READ_ERROR": 0,
        "WRITE_ERROR": 0,
    }
    provenance_counts = {
        "vendor_self_host": 0,
        "real_deployment_third_party": 0,
        "documented_default_behavior": 0,
        "UNVERIFIED_FALLBACK": 0,
        "SUSPECT_MARKETING": 0,
        "SUSPECT_NO_CAPTURE": 0,
        "UNREACHABLE": 0,
        "INDETERMINATE": 0,
    }

    http_cache = load_http_cache(HTTP_VERIFICATION_CACHE) if args.verify_http else None

    AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
    with AUDIT_LOG.open("w", encoding="utf-8") as audit:
        for i, r in enumerate(rules):
            outcome = retrofit_rule(
                r,
                dry_run=args.dry_run,
                http_cache=http_cache,
                verify_http=args.verify_http,
            )
            outcome["timestamp"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            audit.write(json.dumps(outcome, ensure_ascii=False) + "\n")

            v = outcome.get("verdict")
            if v in counts:
                counts[v] += 1
            p = outcome.get("observation_provenance")
            if p in provenance_counts:
                provenance_counts[p] += 1

            if args.verify_http and (i + 1) % 25 == 0:
                save_http_cache(http_cache, HTTP_VERIFICATION_CACHE)
                print(f"  ... {i+1}/{len(rules)} rules processed", file=sys.stderr)

    if args.verify_http and http_cache is not None:
        save_http_cache(http_cache, HTTP_VERIFICATION_CACHE)

    print("=== Retrofit summary ===")
    print(f"Rules scanned: {len(rules)}")
    for k, v in counts.items():
        print(f"  {k}: {v}")
    print()
    print("=== Provenance distribution ===")
    for k, v in provenance_counts.items():
        print(f"  {k}: {v}")
    print()
    print(f"Audit log: {AUDIT_LOG}")
    print(f"Mode: {'DRY-RUN' if args.dry_run else 'WRITE'}")


if __name__ == "__main__":
    main()
