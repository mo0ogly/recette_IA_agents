"""Policy documents: versioned, append-only, generated baseline.

A PolicyVersion is immutable once published; edits publish a new version and
old events keep the version they were decided under (I1/I4). Rules match on
exact (target_system, action_type, role) -- no globs in v1, deterministic.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..catalog import Catalog
from ..catalog.model import RISK_SCORE, RiskLevel
from ..events import PolicyVerdict

DEFAULT_APPROVAL_TIMEOUT_SECONDS = 3600


@dataclass(frozen=True)
class PolicyRule:
    rule_id: str
    target_system: str
    action_type: str
    role: str
    verdict: PolicyVerdict
    risk_level: RiskLevel

    def to_dict(self) -> dict:
        return {
            "rule_id": self.rule_id,
            "target_system": self.target_system,
            "action_type": self.action_type,
            "role": self.role,
            "verdict": self.verdict,
            "risk_level": self.risk_level,
        }

    @staticmethod
    def from_dict(data: dict) -> PolicyRule:
        return PolicyRule(
            rule_id=data["rule_id"],
            target_system=data["target_system"],
            action_type=data["action_type"],
            role=data["role"],
            verdict=PolicyVerdict(data["verdict"]),
            risk_level=RiskLevel(data["risk_level"]),
        )


@dataclass(frozen=True)
class PolicyVersion:
    version: str
    rules: tuple[PolicyRule, ...]
    approval_timeout_seconds: int = DEFAULT_APPROVAL_TIMEOUT_SECONDS
    default: str = "deny"  # informational; the engine is deny-by-default regardless

    def rule_for(self, target_system: str, action_type: str, role: str) -> PolicyRule | None:
        for rule in self.rules:
            if (
                rule.target_system == target_system
                and rule.action_type == action_type
                and rule.role == role
            ):
                return rule
        return None

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "default": self.default,
            "approval_timeout_seconds": self.approval_timeout_seconds,
            "rules": [r.to_dict() for r in self.rules],
        }

    @staticmethod
    def from_dict(data: dict) -> PolicyVersion:
        return PolicyVersion(
            version=data["version"],
            rules=tuple(PolicyRule.from_dict(r) for r in data["rules"]),
            approval_timeout_seconds=data.get(
                "approval_timeout_seconds", DEFAULT_APPROVAL_TIMEOUT_SECONDS
            ),
            default=data.get("default", "deny"),
        )


@dataclass(frozen=True)
class Decision:
    """Engine output, recorded with the event (carries the policy version, I4)."""

    verdict: PolicyVerdict
    policy_version: str
    rule_id: str | None
    risk_level: RiskLevel

    @property
    def risk_score(self) -> int:
        return RISK_SCORE[self.risk_level]


def baseline_from_catalog(catalog: Catalog, *, version: str = "v1") -> PolicyVersion:
    """Deterministic baseline policy: one rule per (action, privileged role).

    Only privileged-role rules are materialized; every other (action, role)
    pair falls through to default-deny in the engine. Rule ids are stable so
    the generated document is byte-identical across runs (I4).
    """
    rules: list[PolicyRule] = []
    for spec in catalog.all():
        for role in spec.privileged_roles:
            rules.append(
                PolicyRule(
                    rule_id=f"{spec.target_system}.{spec.action_type}.{role}",
                    target_system=spec.target_system,
                    action_type=spec.action_type,
                    role=role,
                    verdict=spec.verdict_privileged,
                    risk_level=spec.risk_level,
                )
            )
    return PolicyVersion(version=version, rules=tuple(rules))
