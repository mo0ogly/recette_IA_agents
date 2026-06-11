#!/usr/bin/env python3
"""Fill html_sha256 in active LiaProbe web-signature rules.

For each active rule missing html_sha256, performs a GET request to
capture_url, computes sha256 of the response body, and writes it to
artifacts.html_sha256 + artifacts.capture_date.

Handles two artifacts locations:
  - _lia_independent_authoring.artifacts  (new-schema rules)
  - top-level artifacts                   (legacy v2 rules)

Usage:
    python3 fill_html_sha256.py [--dry-run] [--verbose] [--limit N]
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
AUDIT_LOG = Path(
    "/opt/lia-sec/dev/_alire/tracking/"
    "PLAN_LIAPROBE_AUDIT_RETROACTIF_2026-05-07_fill_sha256.jsonl"
)
SHA256_CACHE_PATH = Path(
    "/opt/lia-sec/dev/_alire/tracking/"
    "PLAN_LIAPROBE_AUDIT_RETROACTIF_2026-05-07_sha256_cache.json"
)

HTTP_TIMEOUT_SEC = 12
HTTP_DELAY_SEC = 0.5
HTTP_MAX_REDIRECTS = 5
HTTP_MAX_BYTES = 10 * 1024 * 1024  # 10 MB cap — avoids huge downloads
CACHE_SAVE_INTERVAL = 25


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


def fetch_sha256(url: str) -> tuple:
    """GET url, return (sha256_hex, error_str).

    Returns (sha256, None) on success, (None, reason) on failure.
    """
    if not url:
        return None, "empty_url"
    try:
        result = subprocess.run(
            [
                "curl", "-sL",
                "--max-redirs", str(HTTP_MAX_REDIRECTS),
                "--max-time", str(HTTP_TIMEOUT_SEC),
                "--max-filesize", str(HTTP_MAX_BYTES),
                "--output", "-",
                url,
            ],
            capture_output=True,
            timeout=HTTP_TIMEOUT_SEC + 5,
        )
        if result.returncode not in (0, 63):  # 63 = max-filesize hit (still has body)
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
    """Return (artifacts_dict, location_str) or (None, 'none').

    location_str: 'authoring' | 'top_level'
    """
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
    dry_run: bool,
    verbose: bool,
) -> dict:
    try:
        rule = json.loads(rule_path.read_text(encoding="utf-8"))
    except Exception as e:
        return {"file": rule_path.name, "verdict": "READ_ERROR", "error": str(e)}

    artifacts, location = _find_artifacts(rule)

    if artifacts is None:
        return {"file": rule_path.name, "verdict": "NO_ARTIFACTS"}

    existing = artifacts.get("html_sha256")
    if existing and existing not in (None, "null", ""):
        return {"file": rule_path.name, "verdict": "SKIP_HAS_SHA256", "sha256": existing}

    capture_url = artifacts.get("capture_url", "")
    if not capture_url:
        return {"file": rule_path.name, "verdict": "SKIP_NO_URL", "location": location}

    rule_id = rule.get("id", rule_path.stem)
    provenance = artifacts.get("observation_provenance", "")
    cache_key = capture_url.lower().rstrip("/")

    # cache hit
    if cache_key in cache:
        entry = cache[cache_key]
        sha256 = entry.get("sha256")
        if not sha256:
            return {
                "file": rule_path.name,
                "verdict": "SKIP_CACHED_FAIL",
                "error": entry.get("error"),
                "capture_url": capture_url,
            }
        if not dry_run:
            artifacts["html_sha256"] = sha256
            artifacts["capture_date"] = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            try:
                _write_back(rule, rule_path, artifacts, location)
            except Exception as e:
                return {"file": rule_path.name, "verdict": "WRITE_ERROR", "error": str(e)}
        if verbose:
            print(f"  CACHE  {rule_path.name}: {sha256[:16]}... ({capture_url[:60]})")
        return {
            "file": rule_path.name,
            "rule_id": rule_id,
            "observation_provenance": provenance,
            "capture_url": capture_url,
            "html_sha256": sha256,
            "source": "cache",
            "verdict": "DRY_RUN" if dry_run else "PATCHED",
        }

    # live fetch
    sha256, error = fetch_sha256(capture_url)
    time.sleep(HTTP_DELAY_SEC)

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    if sha256 is None:
        cache[cache_key] = {"sha256": None, "error": error, "checked_at": ts}
        if verbose:
            print(f"  FAIL   {rule_path.name}: {error} ({capture_url[:60]})")
        return {
            "file": rule_path.name,
            "rule_id": rule_id,
            "observation_provenance": provenance,
            "capture_url": capture_url,
            "verdict": "FETCH_FAILED",
            "error": error,
        }

    cache[cache_key] = {"sha256": sha256, "checked_at": ts}

    if verbose:
        print(f"  FETCH  {rule_path.name}: {sha256[:16]}... ({capture_url[:60]})")

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
        "observation_provenance": provenance,
        "capture_url": capture_url,
        "html_sha256": sha256,
        "source": "live",
        "verdict": "DRY_RUN" if dry_run else "PATCHED",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Do not write changes")
    parser.add_argument("--verbose", "-v", action="store_true")
    parser.add_argument("--limit", type=int, default=0, help="Process at most N rules")
    args = parser.parse_args()

    if not PATTERNS_ROOT.is_dir():
        print(f"FATAL: {PATTERNS_ROOT} not found", file=sys.stderr)
        sys.exit(2)

    cache = load_cache(SHA256_CACHE_PATH)
    print(f"SHA256 cache loaded: {len(cache)} entries")

    rule_files = sorted(PATTERNS_ROOT.glob("*.json"))
    total = len(rule_files)
    if args.limit:
        rule_files = rule_files[: args.limit]
        print(f"Scanning {len(rule_files)} of {total} rule files (limit={args.limit})...")
    else:
        print(f"Scanning {total} rule files...")

    counts: dict[str, int] = {}
    results = []
    rules_since_save = 0

    for i, rp in enumerate(rule_files):
        outcome = process_rule(rp, cache, args.dry_run, args.verbose)
        outcome["timestamp"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        results.append(outcome)

        v = outcome.get("verdict", "UNKNOWN")
        counts[v] = counts.get(v, 0) + 1

        rules_since_save += 1
        if rules_since_save >= CACHE_SAVE_INTERVAL and not args.dry_run:
            save_cache(cache, SHA256_CACHE_PATH)
            rules_since_save = 0

        if (i + 1) % 100 == 0:
            done = counts.get("PATCHED", 0) + counts.get("DRY_RUN", 0)
            failed = counts.get("FETCH_FAILED", 0)
            print(f"  [{i+1}/{len(rule_files)}] patched/dry={done} failed={failed}")

    if not args.dry_run:
        save_cache(cache, SHA256_CACHE_PATH)

    AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
    with AUDIT_LOG.open("a", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    mode = "DRY-RUN" if args.dry_run else "WRITE"
    print(f"\n=== fill_html_sha256 summary ({mode}) ===")
    print(f"Total scanned: {len(rule_files)}")
    for k, v in sorted(counts.items(), key=lambda x: -x[1]):
        print(f"  {k}: {v}")
    print(f"\nSHA256 cache entries: {len(cache)}")
    print(f"Audit log: {AUDIT_LOG}")


if __name__ == "__main__":
    main()
