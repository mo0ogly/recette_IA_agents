"""Quota tracker for nightly external source queries.

Tracks daily and monthly call counts per source.
State persisted in <session_root>/.state/quotas.json.

Quotas hardcoded per source -- update here when tier changes.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

# Free / paid tier limits.
# Update only when account tier changes.
QUOTAS: dict[str, dict[str, int]] = {
    "netlas":         {"daily": 50,  "monthly": 1500},
    "publicwww":      {"daily": 50,  "monthly": 1500},
    "censys":         {"daily": 0,   "monthly": 250},
    "zoomeye":        {"daily": 0,   "monthly": 500},
    "crtsh":          {"daily": 5000, "monthly": 150000},  # crt.sh free, no hard limit
    "rapid7_sonar":   {"daily": 0,   "monthly": 0},        # offline dataset, no quota
    "shodan":         {"daily": 0,   "monthly": 100},      # if membership
}


@dataclass
class SourceUsage:
    today: str = ""
    month: str = ""
    daily_count: int = 0
    monthly_count: int = 0
    last_call_iso: Optional[str] = None
    last_error: Optional[str] = None


@dataclass
class QuotaState:
    sources: dict[str, SourceUsage] = field(default_factory=dict)

    @classmethod
    def load(cls, path: Path) -> "QuotaState":
        if not path.exists():
            return cls()
        with path.open() as fh:
            raw = json.load(fh)
        sources = {
            name: SourceUsage(**data) for name, data in raw.get("sources", {}).items()
        }
        return cls(sources=sources)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "sources": {
                name: usage.__dict__ for name, usage in self.sources.items()
            },
            "saved_at": datetime.now(timezone.utc).isoformat(),
        }
        with path.open("w") as fh:
            json.dump(payload, fh, indent=2)


def _today() -> str:
    return date.today().isoformat()


def _month() -> str:
    return date.today().strftime("%Y-%m")


def check_budget(state: QuotaState, source: str) -> tuple[bool, str]:
    """Return (allowed, reason)."""
    if source not in QUOTAS:
        return False, f"unknown source {source}"
    quota = QUOTAS[source]
    usage = state.sources.setdefault(source, SourceUsage())

    if usage.today != _today():
        usage.today = _today()
        usage.daily_count = 0
    if usage.month != _month():
        usage.month = _month()
        usage.monthly_count = 0

    if quota["daily"] and usage.daily_count >= quota["daily"]:
        return False, f"daily quota exhausted {usage.daily_count}/{quota['daily']}"
    if quota["monthly"] and usage.monthly_count >= quota["monthly"]:
        return False, f"monthly quota exhausted {usage.monthly_count}/{quota['monthly']}"
    return True, "ok"


def record_call(state: QuotaState, source: str, error: Optional[str] = None) -> None:
    usage = state.sources.setdefault(source, SourceUsage())
    usage.daily_count += 1
    usage.monthly_count += 1
    usage.last_call_iso = datetime.now(timezone.utc).isoformat()
    usage.last_error = error
