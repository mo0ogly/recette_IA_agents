#!/usr/bin/env python3
"""Validate a Konrad-Kurze memory candidate before writing it to the main log.

Enforces 3 rules from references/memory-schema.md:
  Rule A: Internally generated (evidence_refs valid format and non-empty).
  Rule B: No contradiction with prior entries on the same cluster_id.
  Rule C: Recurring pattern relevance (occurrences >= 2 OR cluster known OR explicit override).

Exits 0 on success, 1 on validation failure (with the candidate written to quarantine).

Usage:
  validate_memory.py \
    --candidate /path/to/candidate.json \
    --log /opt/lia-sec/dev/_alire/02_LOGS/Journals/meta/K_KURZE_LEARNING_LOG.json \
    --evidence /opt/lia-sec/dev/_alire/02_LOGS/Journals/decision_log.jsonl \
    [--quarantine-dir /opt/lia-sec/dev/_alire/02_LOGS/Journals/meta/quarantine]
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

EVIDENCE_PATTERNS = [
    re.compile(r"^[a-zA-Z0-9_/.\-]+:\d+$"),
    re.compile(r"^scorecard:[A-Z]+-\d+$"),
    re.compile(r"^decision_log:\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$"),
    re.compile(r"^cycle_\d+/[a-zA-Z0-9_.\-]+$"),
]

CLUSTER_ID_RE = re.compile(r"^FS-[0-9a-f]{8}$")


def load_json(path: Path):
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as fh:
        try:
            return json.load(fh)
        except json.JSONDecodeError as exc:
            sys.stderr.write(f"ERROR: {path} is not valid JSON: {exc}\n")
            sys.exit(2)


def write_quarantine(quarantine_dir: Path, rule: str, details: str, candidate: dict) -> Path:
    quarantine_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = quarantine_dir / f"{ts}_quarantine.json"
    payload = {
        "quarantined_at": ts,
        "rule_failed": rule,
        "details": details,
        "candidate": candidate,
    }
    with out.open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, ensure_ascii=False)
    return out


def evidence_ref_valid(ref: str) -> bool:
    return any(p.match(ref) for p in EVIDENCE_PATTERNS)


def rule_a(candidate: dict) -> tuple[bool, str]:
    """Internally generated: evidence_refs present and well-formed."""
    refs = candidate.get("evidence_refs")
    if not isinstance(refs, list) or not refs:
        return False, "evidence_refs missing or empty"
    bad = [r for r in refs if not isinstance(r, str) or not evidence_ref_valid(r)]
    if bad:
        return False, f"malformed evidence_refs: {bad}"
    return True, ""


def rule_b(candidate: dict, log: dict) -> tuple[bool, str]:
    """No contradiction with prior entries on the same cluster_id."""
    cluster = candidate.get("failure_cluster") or {}
    cid = cluster.get("cluster_id")
    if not cid:
        return False, "failure_cluster.cluster_id missing"
    if not CLUSTER_ID_RE.match(cid):
        return False, f"cluster_id format invalid: {cid}"
    prior = log.get(cid)
    if not prior:
        return True, ""
    cand_cls = set(candidate.get("classifications", []))
    prior_cls = set(prior.get("classifications", []))
    if cand_cls.isdisjoint(prior_cls) and "supersedes" not in (candidate.get("notes") or ""):
        return False, (
            f"classifications {sorted(cand_cls)} disjoint from prior "
            f"{sorted(prior_cls)} without 'supersedes' note"
        )
    cand_outcomes = candidate.get("outcomes") or {}
    prior_outcomes = prior.get("outcomes") or {}
    for k, v in cand_outcomes.items():
        if k in prior_outcomes and v < prior_outcomes[k]:
            return False, f"outcomes.{k} decremented ({prior_outcomes[k]} -> {v})"
    if (
        candidate.get("global_learning_mode") is False
        and prior.get("global_learning_mode") is True
        and prior.get("occurrences", 0) >= 3
    ):
        return False, "cannot reset global_learning_mode while occurrences >= 3"
    return True, ""


def rule_c(candidate: dict, log: dict) -> tuple[bool, str]:
    """Recurring pattern relevance."""
    cluster = candidate.get("failure_cluster") or {}
    cid = cluster.get("cluster_id")
    occ = cluster.get("occurrences", 0)
    if occ >= 2:
        return True, ""
    if cid in log:
        return True, ""
    notes = (candidate.get("notes") or "").lower()
    if "first-occurrence override" in notes:
        return True, ""
    return False, (
        "first occurrence without override; expected occurrences>=2 OR known cluster "
        "OR explicit 'first-occurrence override' in notes"
    )


def evidence_refs_resolve(candidate: dict, evidence_log: Path) -> list[str]:
    """Best-effort check that file:line refs point at real files (warning, not failure)."""
    warnings = []
    for ref in candidate.get("evidence_refs", []):
        if ":" not in ref:
            continue
        head, tail = ref.split(":", 1)
        if head.startswith("scorecard") or head.startswith("decision_log") or head.startswith("cycle_"):
            continue
        if not tail.isdigit():
            continue
        candidate_path = Path(head)
        if not candidate_path.is_absolute():
            candidate_path = Path.cwd() / candidate_path
        if not candidate_path.exists():
            warnings.append(f"file not found on disk: {ref}")
    if not evidence_log.exists():
        warnings.append(f"evidence log not found: {evidence_log}")
    return warnings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--candidate", required=True, help="path to candidate JSON file")
    parser.add_argument("--log", required=True, help="path to K_KURZE_LEARNING_LOG.json")
    parser.add_argument("--evidence", required=True, help="path to decision_log.jsonl")
    parser.add_argument(
        "--quarantine-dir",
        default=str(Path("_alire/02_LOGS/Journals/meta/quarantine").resolve()),
        help="directory to write quarantine entries",
    )
    args = parser.parse_args()

    candidate_path = Path(args.candidate)
    log_path = Path(args.log)
    evidence_path = Path(args.evidence)
    quarantine_dir = Path(args.quarantine_dir)

    if not candidate_path.exists():
        sys.stderr.write(f"ERROR: candidate file not found: {candidate_path}\n")
        return 2

    candidate = load_json(candidate_path)
    log = load_json(log_path)

    for rule_name, rule_fn in (("A", rule_a), ("B", rule_b), ("C", rule_c)):
        if rule_name == "A":
            ok, detail = rule_fn(candidate)
        else:
            ok, detail = rule_fn(candidate, log)
        if not ok:
            quarantine_path = write_quarantine(quarantine_dir, rule_name, detail, candidate)
            sys.stderr.write(f"FAIL rule {rule_name}: {detail}\n")
            sys.stderr.write(f"quarantined: {quarantine_path}\n")
            return 1

    warnings = evidence_refs_resolve(candidate, evidence_path)
    for w in warnings:
        sys.stderr.write(f"WARN: {w}\n")

    print("OK: candidate passed rules A, B, C")
    return 0


if __name__ == "__main__":
    sys.exit(main())
