"""Deterministic fault injection for the mock lab (I4-safe resilience recette).

Why this exists: the mock lab answered 200 to every request, so the whole
`failure-modes.md` spec (proxy/dependency down -> the agent must freeze/retry,
never execute optimistically; I5/I6) was UNRECETTABLE -- a dependency that never
fails never exercises fail-safe behaviour. This module lets the lab return INFRA
faults (429 rate-limit, 503 unavailable, 504 timeout, connection-reset-as-503) on
a configured fraction of requests.

Determinism (I4): the fault decision is a PURE function of
(seed, event_id, target_system, action_type) -- no clock, no random -- so a
recette run is replayable: the same logical event always faults (or not)
identically, and the chosen status is stable. `event_id` is sequence-derived in
this system, so the fault pattern is reproducible across runs. Timeout is modelled
as HTTP 504 (no real `sleep`), so the deterministic suite stays fast and
byte-stable; a real latency injection belongs to a live-only mode, never the
decision/judge path.

Off by default (R5 config-first). Enable via `INSPECT_IA_AGENTS_LAB_CHAOS`: either
an inline JSON object or a path to a JSON file with the shape:

    {
      "seed": "rec-2026-06-24",
      "systems": {
        "okta":    {"error_rate": 0.25, "statuses": [429, 503]},
        "finance": {"error_rate": 0.5,  "statuses": [503, 504]},
        "*":       {"error_rate": 0.1,  "statuses": [503]}
      }
    }

`"*"` is the default applied to any system without an explicit entry. A system
with no entry and no `"*"` never faults. `error_rate` is clamped to [0, 1].
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass

_ENV = "INSPECT_IA_AGENTS_LAB_CHAOS"

# Fault status -> (envelope code, human detail). 504 models a timeout WITHOUT a
# real sleep so the deterministic path stays byte-stable; 503 covers both
# "service unavailable" and a connection reset surfaced to the caller.
_FAULT_META: dict[int, tuple[str, str]] = {
    429: ("rate_limited", "rate limit exceeded, retry after backoff"),
    503: ("service_unavailable", "upstream dependency unavailable"),
    504: ("upstream_timeout", "upstream dependency timed out"),
}
_DEFAULT_STATUSES: tuple[int, ...] = (503,)


@dataclass(frozen=True)
class _SystemChaos:
    error_rate: float
    statuses: tuple[int, ...]


@dataclass(frozen=True)
class ChaosPolicy:
    """A loaded, validated chaos configuration. Pure: `fault_for` has no I/O."""

    seed: str
    systems: dict[str, _SystemChaos]

    def _spec_for(self, target_system: str) -> _SystemChaos | None:
        return self.systems.get(target_system) or self.systems.get("*")

    def fault_for(
        self, target_system: str, action_type: str, event_id: str
    ) -> tuple[int, str, str] | None:
        """Return `(status_code, code, detail)` to inject, or None to pass through.

        Deterministic: keyed on (seed, event_id, target, action). The same logical
        event always yields the same decision and the same status."""
        spec = self._spec_for(target_system)
        if spec is None or spec.error_rate <= 0 or not spec.statuses:
            return None
        digest = hashlib.sha256(
            f"{self.seed}|{event_id}|{target_system}|{action_type}".encode()
        ).hexdigest()
        bucket = int(digest[:8], 16) % 10_000
        if bucket >= int(spec.error_rate * 10_000):
            return None
        status = spec.statuses[int(digest[8:12], 16) % len(spec.statuses)]
        code, detail = _FAULT_META.get(status, ("fault", "injected fault"))
        return status, code, detail


def _coerce_system(raw: object) -> _SystemChaos | None:
    if not isinstance(raw, dict):
        return None
    rate = raw.get("error_rate", 0)
    try:
        rate = max(0.0, min(1.0, float(rate)))
    except (TypeError, ValueError):
        rate = 0.0
    statuses_raw = raw.get("statuses")
    statuses: tuple[int, ...]
    if isinstance(statuses_raw, list) and statuses_raw:
        statuses = tuple(int(s) for s in statuses_raw if isinstance(s, (int, float)))
    else:
        statuses = _DEFAULT_STATUSES
    return _SystemChaos(error_rate=rate, statuses=statuses or _DEFAULT_STATUSES)


def policy_from_dict(data: dict) -> ChaosPolicy | None:
    """Build a ChaosPolicy from a parsed config dict. None if it disables chaos."""
    systems_raw = data.get("systems")
    if not isinstance(systems_raw, dict):
        return None
    systems: dict[str, _SystemChaos] = {}
    for name, spec in systems_raw.items():
        coerced = _coerce_system(spec)
        if coerced is not None and coerced.error_rate > 0:
            systems[str(name)] = coerced
    if not systems:
        return None
    seed = str(data.get("seed", "chaos"))
    return ChaosPolicy(seed=seed, systems=systems)


def load_policy(env_value: str | None = None) -> ChaosPolicy | None:
    """Load from the env var (inline JSON or a file path). None when unset/empty/
    malformed -- fault injection is opt-in, so any ambiguity falls back to OFF
    (never crash the lab on a bad chaos config; the lab must still serve 200)."""
    raw = env_value if env_value is not None else os.environ.get(_ENV, "")
    raw = (raw or "").strip()
    if not raw:
        return None
    text = raw
    if not raw.startswith("{"):
        try:
            with open(raw, encoding="utf-8") as fh:
                text = fh.read()
        except OSError:
            return None
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None
    return policy_from_dict(data) if isinstance(data, dict) else None
