#!/usr/bin/env python3
"""Evaluate declared workflow evidence. Never execute evidence or infer its truth."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path
from typing import Any, cast

METHOD = "2"
STATUSES = {"PASS", "FAIL", "PARTIEL", "NON TESTÉ", "NON APPLICABLE"}
SEVERITIES = ("none", "minor", "major", "critical")
PHASES = {
    "entry": {"entry"},
    "validation": {"entry", "validation"},
    "delivery": {"entry", "validation", "delivery"},
    "audit": {"entry", "validation", "delivery"},
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def number(value: Any, name: str) -> float:
    require(
        type(value) in (int, float) and math.isfinite(value) and value >= 0,
        f"{name}: expected finite nonnegative number",
    )
    return float(value)


def digest(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False).encode()
    ).hexdigest()


def local_file(root: Path, name: Any) -> Path:
    require(isinstance(name, str) and bool(name), "Expected relative file path")
    path = (root / name).resolve()
    require(
        not Path(name).is_absolute() and path.is_relative_to(root),
        f"Path outside evidence root: {name}",
    )
    require(path.is_file(), f"Missing file: {name}")
    return path


def records(value: Any, name: str) -> dict[str, dict[str, Any]]:
    require(isinstance(value, list), f"{name}: expected list")
    output = {}
    for row in value:
        require(isinstance(row, dict), f"{name}: expected object")
        key = row.get("id")
        require(
            isinstance(key, str) and bool(key.strip()) and key not in output,
            f"{name}: missing or duplicate id",
        )
        output[key] = row
    return output


def evaluate(document: dict[str, Any], root: Path, phase: str = "delivery") -> dict[str, Any]:
    """Validate a complete inventory, calculate scores and fail closed on gaps."""
    root = root.resolve()
    require(phase in PHASES, "Unknown phase")
    require(document.get("method_version") == METHOD, "Unsupported method_version")
    require(
        isinstance(document.get("scope_id"), str) and bool(document["scope_id"].strip()),
        "Missing scope_id",
    )
    artifacts = document.get("artifacts")
    require(isinstance(artifacts, dict) and bool(artifacts), "Missing artifact fingerprints")
    artifacts = cast(dict[str, str], artifacts)
    protected_paths = set()
    for name, expected in artifacts.items():
        protected_paths.add(local_file(root, name))
        actual = hashlib.sha256(local_file(root, name).read_bytes()).hexdigest()
        require(actual == expected, f"Stale artifact fingerprint: {name}")
    domains = document.get("domains")
    require(isinstance(domains, dict) and bool(domains), "Missing weighted domains")
    domains = cast(dict[str, Any], domains)
    for name, weight in domains.items():
        require(isinstance(name, str) and bool(name.strip()), "Invalid domain name")
        require(number(weight, name) > 0, f"{name}: weight must be positive")
    checks = records(document.get("checks"), "checks")
    require(bool(checks), "Empty check inventory")
    observations = records(document.get("results"), "results")
    require(set(observations) <= set(checks), "Unknown result id")
    rows = []
    for key, check in checks.items():
        require(check.get("domain") is None or check["domain"] in domains, f"{key}: unknown domain")
        require(type(check.get("mandatory")) is bool, f"{key}: mandatory must be boolean")
        require(check.get("gate") in PHASES["delivery"], f"{key}: invalid gate")
        require(check.get("severity") in SEVERITIES, f"{key}: invalid severity")
        number(check.get("penalty"), f"{key}.penalty")
        number(check.get("max_penalty"), f"{key}.max_penalty")
        row = observations.get(key, {"id": key, "status": "NON TESTÉ", "count": 0})
        require(
            set(row) <= {"id", "status", "count", "evidence", "reason"},
            f"{key}: result must not override check configuration",
        )
        status = row.get("status")
        require(status in STATUSES, f"{key}: invalid status")
        count = number(row.get("count"), f"{key}.count")
        require(status != "FAIL" or count > 0, f"{key}: FAIL requires positive count")
        require(
            status not in ("PASS", "NON APPLICABLE") or count == 0,
            f"{key}: PASS/NA requires zero count",
        )
        if status == "NON APPLICABLE":
            require(
                isinstance(row.get("reason"), str) and bool(row["reason"].strip()),
                f"{key}: NA requires justification",
            )
        evidence = row.get("evidence", [])
        require(isinstance(evidence, list), f"{key}: evidence must be a list")
        require(status not in ("PASS", "FAIL") or bool(evidence), f"{key}: missing evidence")
        for item in evidence:
            require(
                local_file(root, item) in protected_paths,
                f"{key}: evidence is missing from artifact fingerprints: {item}",
            )
        rows.append({**check, **row})
    applicable = [r for r in rows if r["status"] != "NON APPLICABLE"]
    relevant = [r for r in applicable if r["gate"] in PHASES[phase]]
    scores = {}
    for domain in domains:
        subset = [r for r in applicable if r["domain"] == domain]
        if subset:
            penalty = sum(
                min(r["count"] * r["penalty"], r["max_penalty"])
                for r in subset
                if r["status"] == "FAIL"
            )
            scores[domain] = max(0.0, 100.0 - penalty)
    provisional = any(
        r["domain"] is not None and r["status"] not in ("PASS", "FAIL") for r in applicable
    )
    quality = (
        sum(scores[d] * domains[d] for d in scores) / sum(domains[d] for d in scores)
        if scores
        else None
    )
    blockers = []
    for row in relevant:
        terminal = row["status"] in ("PASS", "FAIL")
        if phase == "audit":
            if not terminal or (
                row["domain"] is None and row["mandatory"] and row["status"] != "PASS"
            ):
                blockers.append(row["id"])
        elif row["mandatory"] and row["status"] != "PASS":
            blockers.append(row["id"])
        if (
            phase != "audit"
            and row["status"] == "FAIL"
            and row["severity"] in ("critical", "major")
        ):
            blockers.append(row["id"])
    maximum = max(
        (r["severity"] for r in relevant if r["status"] == "FAIL"),
        key=SEVERITIES.index,
        default="none",
    )
    if not relevant:
        blockers.append("empty-applicable-inventory")
    if phase == "delivery":
        if provisional or quality is None:
            blockers.append("quality-incomplete")
        if quality is not None and quality < 70:
            blockers.append("quality-below-70")
        if any(score < 50 for score in scores.values()):
            blockers.append("domain-below-50")
    band = (
        "INCOMPLETE"
        if quality is None or provisional
        else "OK"
        if quality >= 80
        else "WARN"
        if quality >= 70
        else "BLOQUÉ"
        if quality >= 50
        else "STOP"
    )
    passed = sum(r["status"] == "PASS" for r in relevant)
    config = {"domains": domains, "checks": sorted(checks.values(), key=lambda r: r["id"])}
    return {
        "method_version": METHOD,
        "scope_id": document["scope_id"],
        "phase": phase,
        "config_digest": digest(config),
        "applicability_digest": digest(sorted(r["id"] for r in applicable)),
        "artifacts": artifacts,
        "domain_scores": scores,
        "quality": round(quality, 2) if quality is not None else None,
        "provisional": provisional,
        "quality_band": band,
        "progress": {
            "passed": passed,
            "applicable": len(relevant),
            "percent": round(100 * passed / len(relevant), 2) if relevant else None,
        },
        "max_severity": maximum,
        "blockers": sorted(set(blockers)),
        "allowed": not blockers,
        "ship_allowed": phase == "delivery" and not blockers,
    }


def compare(previous: dict[str, Any], current: dict[str, Any]) -> float | None:
    """Return quality delta only for complete, comparable evaluations."""
    keys = ("method_version", "scope_id", "config_digest", "applicability_digest", "phase")
    if any(not previous.get(k) or previous[k] != current.get(k) for k in keys):
        return None
    if previous.get("provisional") or current.get("provisional"):
        return None
    if any(type(d.get("quality")) not in (int, float) for d in (previous, current)):
        return None
    return round(current["quality"] - previous["quality"], 2)


def read_json(path: Path) -> dict[str, Any]:
    result = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(result, dict), "Expected JSON object")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--phase", choices=PHASES, default="delivery")
    parser.add_argument("--previous", type=Path)
    args = parser.parse_args()
    try:
        result = evaluate(read_json(args.input), args.root, args.phase)
        if args.previous:
            result["quality_delta"] = compare(read_json(args.previous), result)
        print(json.dumps(result, ensure_ascii=False, allow_nan=False, indent=2))
        return 0 if result["allowed"] else 1
    except (ValueError, OSError, TypeError, KeyError) as exc:
        print(f"Invalid evaluation: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
