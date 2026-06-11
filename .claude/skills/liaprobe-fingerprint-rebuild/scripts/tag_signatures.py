#!/usr/bin/env python3
"""Tag legacy externally-derived rules with explicit dette marker.

Walks all rules in patterns/web-signatures/ that do NOT have
`_lia_independent_authoring` block (= still externally-derived per audit
2026-05-07). Adds `_legacy_external_derived: true` and tags `_audit_status`
according to matcher target distribution.

Output:
- Patches each rule.json in-place with explicit dette markers
- Writes legacy_tagging.jsonl audit log

Usage:
    python3 tag_signatures.py [--dry-run] [--limit N]
"""

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

PATTERNS_ROOT = Path("/opt/lia-sec/liaprobe/patterns/web-signatures")
AUDIT_LOG = Path(
    "/opt/lia-sec/dev/_alire/tracking/"
    "PLAN_LIAPROBE_AUDIT_RETROACTIF_2026-05-07_legacy_tagging.jsonl"
)


def tag_rule(rule_path, dry_run=False):
    """Tag a single rule as legacy externally-derived if applicable.

    Returns dict with outcome.
    """
    try:
        with rule_path.open("r", encoding="utf-8") as f:
            rule = json.load(f)
    except Exception as e:
        return {"file": str(rule_path), "verdict": "READ_ERROR", "error": str(e)}

    if rule.get("_lia_independent_authoring") is not None:
        return {"file": rule_path.name, "verdict": "SKIP_INDEPENDENT_AUTHORED"}

    rule_id = rule.get("id", rule_path.stem)
    probes = rule.get("probes", []) or []
    targets = []
    matcher_count = 0
    null_value_count = 0
    for p in probes:
        for m in p.get("matchers", []) or []:
            matcher_count += 1
            t = m.get("target")
            if t:
                targets.append(t)
            v = m.get("value")
            if v is None or v == "":
                null_value_count += 1

    target_set = sorted(set(targets))

    if matcher_count == 0:
        audit_status = "DEAD_NO_MATCHERS"
    elif null_value_count == matcher_count:
        audit_status = "DEAD_NULL_VALUES"
    elif target_set == ["script_src"]:
        audit_status = "LEGACY_SCRIPT_SRC_ONLY"
    elif target_set == ["cookie"]:
        audit_status = "LEGACY_COOKIE_ONLY"
    elif target_set == ["meta"]:
        audit_status = "LEGACY_META_ONLY"
    elif target_set == ["body"]:
        audit_status = "LEGACY_BODY_ONLY"
    elif target_set == ["header"]:
        audit_status = "LEGACY_HEADER_ONLY"
    elif "header" in target_set:
        audit_status = "LEGACY_WITH_HEADER"
    else:
        audit_status = "LEGACY_MIXED"

    rule["_legacy_external_derived"] = True
    rule["_audit_status"] = audit_status
    rule["_audit_date"] = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    rule["_audit_note"] = (
        "Marked legacy externally-derived during retroactif audit 2026-05-07. "
        "Pending: re-author with direct public observation per "
        ".claude/skills/liaprobe-fingerprint-rebuild/SKILL.md"
    )

    if not dry_run:
        try:
            rule_path.write_text(
                json.dumps(rule, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
        except Exception as e:
            return {
                "file": rule_path.name,
                "verdict": "WRITE_ERROR",
                "error": str(e),
            }

    return {
        "file": rule_path.name,
        "rule_id": rule_id,
        "matcher_count": matcher_count,
        "null_value_count": null_value_count,
        "target_set": target_set,
        "audit_status": audit_status,
        "verdict": "TAGGED" if not dry_run else "DRY_RUN_TAG",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    if not PATTERNS_ROOT.is_dir():
        print(f"FATAL: {PATTERNS_ROOT} not found", file=sys.stderr)
        sys.exit(2)

    rules = sorted(PATTERNS_ROOT.glob("*.json"))
    if args.limit:
        rules = rules[: args.limit]

    counts = {}
    status_counts = {}

    AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
    with AUDIT_LOG.open("w", encoding="utf-8") as audit:
        for r in rules:
            outcome = tag_rule(r, dry_run=args.dry_run)
            outcome["timestamp"] = datetime.now(timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%SZ"
            )
            audit.write(json.dumps(outcome, ensure_ascii=False) + "\n")
            v = outcome.get("verdict", "UNKNOWN")
            counts[v] = counts.get(v, 0) + 1
            s = outcome.get("audit_status")
            if s:
                status_counts[s] = status_counts.get(s, 0) + 1

    print("=== Tagging summary ===")
    print(f"Rules scanned: {len(rules)}")
    for k, v in sorted(counts.items()):
        print(f"  {k}: {v}")
    print()
    print("=== Audit status distribution (legacy rules only) ===")
    for k, v in sorted(status_counts.items(), key=lambda x: -x[1]):
        print(f"  {k}: {v}")
    print()
    print(f"Audit log: {AUDIT_LOG}")
    print(f"Mode: {'DRY-RUN' if args.dry_run else 'WRITE'}")


if __name__ == "__main__":
    main()
