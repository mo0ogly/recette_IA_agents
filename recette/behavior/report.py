"""AnalysisReport -- the deterministic output of a wave.

A finding is the atomic signal a lens emits; an agent report bundles an agent's
findings + three-way (PLANNED/SAID/DONE) + behavioral score + coherence; the
analysis report adds provenance ``(evidence_hash, profile_hash, tool_version)`` so
it is a replayable, citable artifact. All ``to_dict`` outputs use sorted/stable
order -- the report serializes byte-identically on replay (I4).
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Tool contract version: bump when the report schema changes (part of the
# experiment_id, so a reproduced run pins the engine version too).
TOOL_VERSION = "behavior-engine/1"

_SEVERITY_ORDER = {"alert": 0, "warn": 1, "info": 2}


@dataclass(frozen=True)
class Finding:
    """One signal from one lens about one agent."""

    lens: str
    severity: str
    log: str
    why: str
    owasp_asi: str | None = None
    mitre_atlas: str | None = None

    def to_dict(self) -> dict:
        return {
            "lens": self.lens,
            "severity": self.severity,
            "log": self.log,
            "why": self.why,
            "owasp_asi": self.owasp_asi,
            "mitre_atlas": self.mitre_atlas,
        }


@dataclass(frozen=True)
class AgentReport:
    agent_id: str
    identified: bool
    coherent: bool
    behavioral_score: int
    planned: dict
    said: dict | None
    done: dict
    findings: list[Finding] = field(default_factory=list)

    def to_dict(self) -> dict:
        ordered = sorted(
            self.findings,
            key=lambda f: (_SEVERITY_ORDER.get(f.severity, 9), f.lens, f.log),
        )
        return {
            "agent_id": self.agent_id,
            "identified": self.identified,
            "coherent": self.coherent,
            "behavioral_score": self.behavioral_score,
            "planned": self.planned,
            "said": self.said,
            "done": self.done,
            "findings": [f.to_dict() for f in ordered],
        }


@dataclass(frozen=True)
class AnalysisReport:
    profile_name: str
    threat: str
    evidence_hash: str
    profile_hash: str
    tool_version: str
    agents: list[AgentReport] = field(default_factory=list)

    def experiment_id(self) -> str:
        """The reproducibility key: evidence + profile + engine version."""
        return f"{self.evidence_hash}|{self.profile_hash}|{self.tool_version}"

    def to_dict(self) -> dict:
        return {
            "profile_name": self.profile_name,
            "threat": self.threat,
            "evidence_hash": self.evidence_hash,
            "profile_hash": self.profile_hash,
            "tool_version": self.tool_version,
            "experiment_id": self.experiment_id(),
            "agents": [a.to_dict() for a in sorted(self.agents, key=lambda a: a.agent_id)],
        }
