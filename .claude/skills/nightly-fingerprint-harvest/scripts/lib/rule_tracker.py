"""Cross-night rule tracker.

Two artefacts under <session_root>/nightly/.state/:

  rules_progress.jsonl  -- append-only event stream
      one line per rule visit; survives partial writes; audit trail
      schema per line:
        {
          "ts": "ISO 8601 UTC",
          "run_date": "YYYY-MM-DD",
          "rule_id": "...",
          "sources_attempted": ["netlas","crtsh",...],
          "sources_succeeded": ["netlas"],
          "captures_count": int,
          "best_match_score": float,
          "any_probe_matched": bool,
          "outcome": "captured"|"no_match"|"quota_exhausted"|"error",
          "error": str|null
        }

  rules_status.json  -- latest aggregated state per rule_id (rebuild from
      progress jsonl any time; cached so report_status is fast)
      {
        "<rule_id>": {
          "first_queried_at": "...",
          "last_queried_at": "...",
          "total_visits": int,
          "total_captures": int,
          "best_score": float,
          "sources_succeeded": ["netlas",...],
          "outcome_latest": "captured",
          "promotion_ready": bool,           # best_score >= threshold
          "drift_detected": bool,
          "queried_dates": ["YYYY-MM-DD",...]
        }, ...
      }
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional


@dataclass
class RuleVisit:
    rule_id: str
    run_date: str
    sources_attempted: list[str] = field(default_factory=list)
    sources_succeeded: list[str] = field(default_factory=list)
    captures_count: int = 0
    best_match_score: float = 0.0
    any_probe_matched: bool = False
    outcome: str = "no_match"
    error: Optional[str] = None
    promotion_ready: bool = False
    drift_detected: bool = False


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def state_dir(session_root: Path) -> Path:
    d = session_root / "nightly" / ".state"
    d.mkdir(parents=True, exist_ok=True)
    return d


def progress_path(session_root: Path) -> Path:
    return state_dir(session_root) / "rules_progress.jsonl"


def status_path(session_root: Path) -> Path:
    return state_dir(session_root) / "rules_status.json"


def record_visit(session_root: Path, visit: RuleVisit) -> None:
    line = {
        "ts": _now_iso(),
        "run_date": visit.run_date,
        "rule_id": visit.rule_id,
        "sources_attempted": visit.sources_attempted,
        "sources_succeeded": visit.sources_succeeded,
        "captures_count": visit.captures_count,
        "best_match_score": visit.best_match_score,
        "any_probe_matched": visit.any_probe_matched,
        "outcome": visit.outcome,
        "error": visit.error,
        "promotion_ready": visit.promotion_ready,
        "drift_detected": visit.drift_detected,
    }
    with progress_path(session_root).open("a") as fh:
        fh.write(json.dumps(line) + "\n")


def iter_events(session_root: Path) -> Iterable[dict]:
    path = progress_path(session_root)
    if not path.exists():
        return
    with path.open() as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                # Tolerate partial trailing writes.
                continue


def rebuild_status(session_root: Path) -> dict:
    """Rebuild rules_status.json by replaying progress events."""
    status: dict[str, dict] = {}
    for event in iter_events(session_root):
        rid = event.get("rule_id")
        if not rid:
            continue
        entry = status.setdefault(rid, {
            "first_queried_at": event["ts"],
            "last_queried_at": event["ts"],
            "total_visits": 0,
            "total_captures": 0,
            "best_score": 0.0,
            "sources_succeeded": [],
            "outcome_latest": "no_match",
            "promotion_ready": False,
            "drift_detected": False,
            "queried_dates": [],
        })
        entry["last_queried_at"] = event["ts"]
        entry["total_visits"] += 1
        entry["total_captures"] += int(event.get("captures_count") or 0)
        if float(event.get("best_match_score") or 0) > entry["best_score"]:
            entry["best_score"] = float(event["best_match_score"])
        for src in event.get("sources_succeeded") or []:
            if src not in entry["sources_succeeded"]:
                entry["sources_succeeded"].append(src)
        entry["outcome_latest"] = event.get("outcome") or entry["outcome_latest"]
        entry["promotion_ready"] = entry["promotion_ready"] or bool(event.get("promotion_ready"))
        entry["drift_detected"] = entry["drift_detected"] or bool(event.get("drift_detected"))
        rd = event.get("run_date")
        if rd and rd not in entry["queried_dates"]:
            entry["queried_dates"].append(rd)

    status_path(session_root).write_text(json.dumps(status, indent=2))
    return status


def load_status(session_root: Path) -> dict:
    path = status_path(session_root)
    if path.exists():
        try:
            return json.loads(path.read_text())
        except json.JSONDecodeError:
            pass
    return rebuild_status(session_root)


def is_recently_queried(session_root: Path, rule_id: str, within_days: int = 7) -> bool:
    """Return True if rule was queried in the last N days (cooldown)."""
    status = load_status(session_root)
    entry = status.get(rule_id)
    if not entry:
        return False
    last = entry.get("last_queried_at")
    if not last:
        return False
    try:
        last_dt = datetime.fromisoformat(last.replace("Z", "+00:00"))
    except ValueError:
        return False
    delta = datetime.now(timezone.utc) - last_dt
    return delta.days < within_days
