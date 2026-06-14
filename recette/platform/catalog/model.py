"""Action catalog model: the catalog is data, not an enum.

Each of the 11 domain modules under catalog/domains/ exports TARGET_SYSTEM and
a tuple of ActionSpec. The "DENY/ESC depends on role" rule from the tracking
plan is encoded as two verdicts: a privileged role gets verdict_privileged,
any other role gets verdict_default (deny-by-default).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from ..events import PolicyVerdict


class RiskLevel(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


# Deterministic integer mapping used as risk_score (no Risk Engine yet -- documented
# limitation; integers keep the decision path float-free, R11).
RISK_SCORE: dict[RiskLevel, int] = {
    RiskLevel.LOW: 1,
    RiskLevel.MEDIUM: 2,
    RiskLevel.HIGH: 3,
    RiskLevel.CRITICAL: 4,
}


class Criticality(StrEnum):
    """AgentRail default governance posture per governed action (Annex C levels).

    This is the DECLARED default position of the product, the starting point that
    is tuned with the client during the simulation phase. It is a SEPARATE axis
    from `risk_level` (severity) and from the implemented policy `verdict`
    (allow/escalate/deny): a C1 action may currently be `escalate` for a
    privileged role while its default posture remains "refuse". The catalog
    records both -- the posture (criticality) and the implemented verdict -- so
    the gap between declared and enforced is auditable, not hidden.

    - C1: refuse by default (the most sensitive / irreversible actions).
    - C2: systematic escalation (human approval required, I6).
    - C3: conditional authorization (thresholds and context decide).
    - C4: authorization with logging (routine, authorized, fully audited).
    """

    C1 = "C1"
    C2 = "C2"
    C3 = "C3"
    C4 = "C4"


# Human-readable label per criticality level (UI / audit surface).
CRITICALITY_LABEL: dict[Criticality, str] = {
    Criticality.C1: "refuse by default",
    Criticality.C2: "systematic escalation",
    Criticality.C3: "conditional authorization",
    Criticality.C4: "authorization with logging",
}


@dataclass(frozen=True)
class ActionSpec:
    """One sensitive action and its expected governance posture."""

    target_system: str
    action_type: str
    risk_level: RiskLevel
    criticality: Criticality  # AgentRail default governance posture (Annex C)
    verdict_privileged: PolicyVerdict  # role in privileged_roles -> this
    verdict_default: PolicyVerdict  # any other role -> this (deny for the whole catalog)
    privileged_roles: tuple[str, ...]
    description: str

    def verdict_for_role(self, role: str) -> PolicyVerdict:
        if role in self.privileged_roles:
            return self.verdict_privileged
        return self.verdict_default

    def to_dict(self) -> dict:
        return {
            "target_system": self.target_system,
            "action_type": self.action_type,
            "risk_level": self.risk_level,
            "risk_score": RISK_SCORE[self.risk_level],
            "criticality": self.criticality,
            "criticality_label": CRITICALITY_LABEL[self.criticality],
            "verdict_privileged": self.verdict_privileged,
            "verdict_default": self.verdict_default,
            "privileged_roles": list(self.privileged_roles),
            "description": self.description,
        }
