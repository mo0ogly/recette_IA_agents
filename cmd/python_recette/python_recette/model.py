"""Core data model: verdicts, severities, findings, and check results."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class Verdict(StrEnum):
    """Outcome of a single check."""

    PASS = "PASS"
    FAIL = "FAIL"
    NA = "N/A"


class Severity(StrEnum):
    """Severity tier of a check."""

    CRITICAL = "critical"
    MAJOR = "major"
    MINOR = "minor"


@dataclass(frozen=True)
class Finding:
    """A single location where a check matched."""

    file: str
    line: int
    excerpt: str


@dataclass
class CheckResult:
    """Result of evaluating one check across the scanned files."""

    id: str
    name: str
    bloc: str
    severity: Severity
    verdict: Verdict
    findings: list[Finding] = field(default_factory=list)
    note: str | None = None

    @property
    def is_critical_fail(self) -> bool:
        """True when a critical check failed (forces a blocking verdict)."""
        return self.verdict is Verdict.FAIL and self.severity is Severity.CRITICAL

    def to_dict(self) -> dict[str, object]:
        """JSON-serializable representation."""
        return {
            "id": self.id,
            "name": self.name,
            "bloc": self.bloc,
            "severity": self.severity.value,
            "verdict": self.verdict.value,
            "findings": [{"file": f.file, "line": f.line, "excerpt": f.excerpt} for f in self.findings],
            "note": self.note,
        }


def passed(id_: str, name: str, bloc: str, severity: Severity, note: str | None = None) -> CheckResult:
    """Build a passing result."""
    return CheckResult(id_, name, bloc, severity, Verdict.PASS, note=note)


def failed(
    id_: str,
    name: str,
    bloc: str,
    severity: Severity,
    findings: list[Finding] | None = None,
    note: str | None = None,
) -> CheckResult:
    """Build a failing result."""
    return CheckResult(id_, name, bloc, severity, Verdict.FAIL, findings or [], note)


def not_applicable(id_: str, name: str, bloc: str, severity: Severity, note: str) -> CheckResult:
    """Build a not-applicable result with an explanatory note."""
    return CheckResult(id_, name, bloc, severity, Verdict.NA, note=note)
