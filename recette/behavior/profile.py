"""AnalysisProfile -- the *wave*: the four tunable knobs of an analysis pass.

A profile is hashed (``profile_hash``) so a wave's provenance is
``(evidence_hash, profile_hash, tool_version)``. Pure data; no clock/random.

The four knobs:
  - ``lenses``    -- which detector families run (enable/disable).
  - ``thresholds``-- per-lens severity / tolerance (e.g. credential=alert|warn,
                     ghost_host_tolerance=N, scope=strict|lax).
  - ``cohort``    -- which agents / surfaces enter the wave.
  - ``threat``    -- a named hypothesis that REWEIGHTS the lenses (a finding from a
                     lens the threat cares about weighs more in the behavioral score).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field

# Every lens the registry knows. A profile's `lenses` is a subset; an unknown name
# is rejected at validation so a typo never silently disables a detector.
ALL_LENSES = (
    "egress",
    "dns",
    "credential",
    "doh",
    "process",
    "said_scope",
    "sequence",
    "baseline",
)

# Named threat hypotheses: per-lens weight multipliers applied to the behavioral
# score. A weight of 0 keeps the finding visible (still logged) but un-scored under
# that hypothesis; >1 amplifies it. "neutral" weighs every lens equally (1.0).
THREAT_WEIGHTS: dict[str, dict[str, float]] = {
    "neutral": {},  # all lenses 1.0
    "exfil": {"egress": 2.0, "doh": 2.5, "credential": 2.5, "dns": 2.0, "sequence": 2.0},
    "escalation": {"said_scope": 2.5, "credential": 2.0, "baseline": 1.5},
    "tunneling": {"doh": 3.0, "dns": 2.5, "egress": 1.5},
    "supply_chain": {"process": 2.5, "egress": 1.5, "baseline": 2.0},
}

# Default per-lens severity, overridable per profile. "off" disables the finding.
DEFAULT_THRESHOLDS: dict[str, object] = {
    "credential": "alert",
    "doh": "alert",
    "egress": "alert",
    "dns": "alert",
    "said_scope": "warn",
    "process": "info",
    "sequence": "alert",
    "baseline": "warn",
    "ghost_host_tolerance": 0,  # how many undeclared egress hosts are tolerated
    "scope": "strict",  # strict: any said-out-of-scope is a finding
}


@dataclass(frozen=True)
class AnalysisProfile:
    """One analysis wave. ``validate`` enforces a known lens set and a known threat."""

    name: str = "default"
    lenses: tuple[str, ...] = ALL_LENSES
    thresholds: dict = field(default_factory=dict)
    cohort: dict = field(default_factory=dict)
    threat: str = "neutral"

    def validate(self) -> None:
        unknown = [lens_ for lens_ in self.lenses if lens_ not in ALL_LENSES]
        if unknown:
            raise ValueError(f"unknown lens(es): {sorted(unknown)}")
        if self.threat not in THREAT_WEIGHTS:
            raise ValueError(f"unknown threat hypothesis: {self.threat}")

    def threshold(self, key: str) -> object:
        """The effective threshold for ``key`` (profile override else default)."""
        if key in self.thresholds:
            return self.thresholds[key]
        return DEFAULT_THRESHOLDS.get(key)

    def lens_weight(self, lens_name: str) -> float:
        """The behavioral-score weight of ``lens_name`` under this threat (default 1.0)."""
        return float(THREAT_WEIGHTS.get(self.threat, {}).get(lens_name, 1.0))

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "lenses": list(self.lenses),
            "thresholds": self.thresholds,
            "cohort": self.cohort,
            "threat": self.threat,
        }

    @classmethod
    def from_dict(cls, data: dict) -> AnalysisProfile:
        lenses = data.get("lenses")
        prof = cls(
            name=str(data.get("name", "default")),
            lenses=tuple(lenses) if lenses is not None else ALL_LENSES,
            thresholds=dict(data.get("thresholds", {}) or {}),
            cohort=dict(data.get("cohort", {}) or {}),
            threat=str(data.get("threat", "neutral")),
        )
        prof.validate()
        return prof

    def profile_hash(self) -> str:
        """Stable ``sha256:<hex>`` over the canonical profile (provenance)."""
        canonical = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))
        return "sha256:" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()
