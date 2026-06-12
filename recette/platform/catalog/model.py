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


@dataclass(frozen=True)
class ActionSpec:
    """One sensitive action and its expected governance posture."""

    target_system: str
    action_type: str
    risk_level: RiskLevel
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
            "verdict_privileged": self.verdict_privileged,
            "verdict_default": self.verdict_default,
            "privileged_roles": list(self.privileged_roles),
            "description": self.description,
        }
