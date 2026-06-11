#!/usr/bin/env python3
"""Strip legacy field names violating R13 from all rule.json.

R13 rule : never reference open-source tool names in code/fields.
This script removes any top-level key matching pattern *wappalyzer* /
*nuclei* / *recog* / *whatweb* / *nmap_signatures* / *vendor_attribution*
and any `_audit_status` value that contains those names.

Usage:
    python3 strip_legacy_field_names.py [--dry-run]
"""

import json
import re
import sys
import argparse
from pathlib import Path

PATTERNS_ROOT = Path("/opt/lia-sec/liaprobe/patterns/web-signatures")
FORBIDDEN_KEY_PATTERN = re.compile(
    r"wappalyzer|whatweb|recog|nuclei|nmap_signatures",
    re.IGNORECASE,
)
FORBIDDEN_TOKEN_PATTERN = re.compile(
    r"\b(wappalyzer|whatweb|recog|nuclei)\b",
    re.IGNORECASE,
)


def scrub_string(s):
    """Replace forbidden tool name tokens with neutral 'external'."""
    return FORBIDDEN_TOKEN_PATTERN.sub("external", s)


def deep_scrub(obj):
    """Recursively scrub forbidden tokens in all string values."""
    if isinstance(obj, dict):
        return {k: deep_scrub(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [deep_scrub(x) for x in obj]
    if isinstance(obj, str):
        return scrub_string(obj)
    return obj


def strip_rule(rule_path, dry_run=False):
    try:
        rule = json.loads(rule_path.read_text(encoding="utf-8"))
    except Exception as e:
        return {"file": rule_path.name, "verdict": "READ_ERROR", "error": str(e)}

    removed_keys = []
    for k in list(rule.keys()):
        if FORBIDDEN_KEY_PATTERN.search(k):
            removed_keys.append(k)
            del rule[k]

    original = json.dumps(rule, sort_keys=True)
    rule = deep_scrub(rule)
    scrubbed = json.dumps(rule, sort_keys=True)
    string_changed = original != scrubbed

    if not removed_keys and not string_changed:
        return {"file": rule_path.name, "verdict": "NO_CHANGE"}

    if not dry_run:
        rule_path.write_text(
            json.dumps(rule, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )

    return {
        "file": rule_path.name,
        "removed_keys": removed_keys,
        "string_scrubbed": string_changed,
        "verdict": "STRIPPED" if not dry_run else "DRY_RUN_STRIP",
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    counts = {}
    rules = sorted(PATTERNS_ROOT.glob("*.json"))
    for r in rules:
        outcome = strip_rule(r, dry_run=args.dry_run)
        v = outcome.get("verdict", "UNKNOWN")
        counts[v] = counts.get(v, 0) + 1

    for k, v in sorted(counts.items()):
        print(f"{k}: {v}")


if __name__ == "__main__":
    main()
