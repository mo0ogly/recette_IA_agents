#!/usr/bin/env python3
"""Retry html_sha256 fill for SSL and HTTP/2 failures.

Targets rules previously failed with:
  curl_rc_35 (SSL handshake)
  curl_rc_60 (SSL cert verification)
  curl_rc_92 (HTTP/2 stream error)

Retries with --insecure and --proto '=https,http' --http1.1 to bypass
SSL cert errors and HTTP/2 negotiation failures.

Usage:
    python3 fill_html_sha256_retry.py [--dry-run] [--verbose] [--limit N]
"""

import argparse
import hashlib
import json
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

PATTERNS_ROOT = Path("/opt/lia-sec/liaprobe/patterns/web-signatures")
AUDIT_LOG_IN = Path(
    "/opt/lia-sec/dev/_alire/tracking/"
    "PLAN_LIAPROBE_AUDIT_RETROACTIF_2026-05-07_fill_sha256.jsonl"
)
AUDIT_LOG_OUT = Path(
    "/opt/lia-sec/dev/_alire/tracking/"
    "PLAN_LIAPROBE_AUDIT_RETROACTIF_2026-05-07_fill_sha256_retry.jsonl"
)
SHA256_CACHE_PATH = Path(
    "/opt/lia-sec/dev/_alire/tracking/"
    "PLAN_LIAPROBE_AUDIT_RETROACTIF_2026-05-07_sha256_cache.json"
)

# Errors targeted by this retry script
RETRY_ERRORS = {"curl_rc_35", "curl_rc_60", "curl_rc_92"}

HTTP_TIMEOUT_SEC = 18
HTTP_DELAY_SEC = 0.5
HTTP_MAX_REDIRECTS = 5
HTTP_MAX_BYTES = 10 * 1024 * 1024
CACHE_SAVE_INTERVAL = 10


def load_cache(path: Path) -> dict:
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_cache(cache: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cache, indent=2, sort_keys=True), encoding="utf-8")


def load_retry_targets(log_path: Path) -> dict[str, str]:
    """Return {cache_key: error} for FETCH_FAILED entries matching RETRY_ERRORS."""
    targets: dict[str, str] = {}
    if not log_path.exists():
        return targets
    with log_path.open(encoding="utf-8") as f:
        for line in f:
            try:
                r = json.loads(line)
            except Exception:
                continue
            if r.get("verdict") == "FETCH_FAILED" and r.get("error") in RETRY_ERRORS:
                url = r.get("capture_url", "")
                if url:
                    key = url.lower().rstrip("/")
                    targets[key] = r.get("error", "unknown")
    return targets


def fetch_sha256_insecure(url: str) -> tuple:
    """GET url with --insecure and --http1.1. Return (sha256_hex, error_str)."""
    if not url:
        return None, "empty_url"
    try:
        result = subprocess.run(
            [
                "curl", "-sL",
                "--insecure",
                "--http1.1",
                "--max-redirs", str(HTTP_MAX_REDIRECTS),
                "--max-time", str(HTTP_TIMEOUT_SEC),
                "--max-filesize", str(HTTP_MAX_BYTES),
                "--output", "-",
                url,
            ],
            capture_output=True,
            timeout=HTTP_TIMEOUT_SEC + 5,
        )
        if result.returncode not in (0, 63):
            return None, f"curl_rc_{result.returncode}"
        body = result.stdout
        if not body:
            return None, "empty_body"
        return hashlib.sha256(body).hexdigest(), None
    except subprocess.TimeoutExpired:
        return None, "timeout"
    except Exception as e:
        return None, str(e)[:80]


def _find_artifacts(rule: dict) -> tuple:
    auth = rule.get("_lia_independent_authoring")
    if isinstance(auth, dict):
        art = auth.get("artifacts")
        if isinstance(art, dict):
            return art, "authoring"
    art = rule.get("artifacts")
    if isinstance(art, dict):
        return art, "top_level"
    return None, "none"


def _write_back(rule: dict, path: Path, artifacts: dict, location: str) -> None:
    if location == "authoring":
        rule["_lia_independent_authoring"]["artifacts"] = artifacts
    else:
        rule["artifacts"] = artifacts
    path.write_text(
        json.dumps(rule, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def process_rule(
    rule_path: Path,
    cache: dict,
    retry_targets: dict,
    dry_run: bool,
    verbose: bool,
) -> dict | None:
    """Process a rule only if its capture_url is a retry target. Returns None to skip."""
    try:
        rule = json.loads(rule_path.read_text(encoding="utf-8"))
    except Exception as e:
        return {"file": rule_path.name, "verdict": "READ_ERROR", "error": str(e)}

    artifacts, location = _find_artifacts(rule)
    if artifacts is None:
        return None

    # Skip if already has sha256
    existing = artifacts.get("html_sha256")
    if existing and existing not in (None, "null", ""):
        return None

    capture_url = artifacts.get("capture_url", "")
    if not capture_url:
        return None

    cache_key = capture_url.lower().rstrip("/")
    if cache_key not in retry_targets:
        return None  # not a retry target

    original_error = retry_targets[cache_key]
    rule_id = rule.get("id", rule_path.stem)

    if verbose:
        print(f"  RETRY  {rule_path.name} ({original_error}): {capture_url[:60]}")

    # Clear stale cache entry so we force re-fetch
    if cache_key in cache:
        del cache[cache_key]

    sha256, error = fetch_sha256_insecure(capture_url)
    time.sleep(HTTP_DELAY_SEC)

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    if sha256 is None:
        cache[cache_key] = {"sha256": None, "error": error, "checked_at": ts}
        if verbose:
            print(f"    FAIL: {error}")
        return {
            "file": rule_path.name,
            "rule_id": rule_id,
            "capture_url": capture_url,
            "original_error": original_error,
            "verdict": "FETCH_FAILED",
            "error": error,
        }

    cache[cache_key] = {"sha256": sha256, "checked_at": ts}

    if verbose:
        print(f"    OK: {sha256[:16]}...")

    if not dry_run:
        artifacts["html_sha256"] = sha256
        artifacts["capture_date"] = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        try:
            _write_back(rule, rule_path, artifacts, location)
        except Exception as e:
            return {"file": rule_path.name, "verdict": "WRITE_ERROR", "error": str(e)}

    return {
        "file": rule_path.name,
        "rule_id": rule_id,
        "capture_url": capture_url,
        "html_sha256": sha256,
        "original_error": original_error,
        "source": "retry_insecure",
        "verdict": "DRY_RUN" if dry_run else "PATCHED",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Do not write changes")
    parser.add_argument("--verbose", "-v", action="store_true")
    parser.add_argument("--limit", type=int, default=0, help="Process at most N candidates")
    args = parser.parse_args()

    if not PATTERNS_ROOT.is_dir():
        print(f"FATAL: {PATTERNS_ROOT} not found", file=sys.stderr)
        sys.exit(2)

    retry_targets = load_retry_targets(AUDIT_LOG_IN)
    print(f"Retry targets loaded: {len(retry_targets)} URLs ({', '.join(sorted(set(retry_targets.values())))})")

    cache = load_cache(SHA256_CACHE_PATH)
    print(f"SHA256 cache loaded: {len(cache)} entries")

    rule_files = sorted(PATTERNS_ROOT.glob("*.json"))
    print(f"Scanning {len(rule_files)} rule files for retry candidates...")

    counts: dict[str, int] = {}
    results = []
    rules_since_save = 0
    candidates_processed = 0

    for rp in rule_files:
        outcome = process_rule(rp, cache, retry_targets, args.dry_run, args.verbose)
        if outcome is None:
            continue  # not a retry target

        candidates_processed += 1
        outcome["timestamp"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        results.append(outcome)

        v = outcome.get("verdict", "UNKNOWN")
        counts[v] = counts.get(v, 0) + 1

        rules_since_save += 1
        if rules_since_save >= CACHE_SAVE_INTERVAL and not args.dry_run:
            save_cache(cache, SHA256_CACHE_PATH)
            rules_since_save = 0

        if args.limit and candidates_processed >= args.limit:
            print(f"  Limit {args.limit} reached.")
            break

    if not args.dry_run:
        save_cache(cache, SHA256_CACHE_PATH)

    AUDIT_LOG_OUT.parent.mkdir(parents=True, exist_ok=True)
    with AUDIT_LOG_OUT.open("a", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    mode = "DRY-RUN" if args.dry_run else "WRITE"
    print(f"\n=== fill_html_sha256_retry summary ({mode}) ===")
    print(f"Retry targets found: {len(retry_targets)}")
    print(f"Candidates processed: {candidates_processed}")
    for k, v in sorted(counts.items(), key=lambda x: -x[1]):
        print(f"  {k}: {v}")
    print(f"\nSHA256 cache entries: {len(cache)}")
    print(f"Retry audit log: {AUDIT_LOG_OUT}")


if __name__ == "__main__":
    main()
