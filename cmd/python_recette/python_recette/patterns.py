"""Pattern-based checks for blocs A, B, C and F, plus structural and manual checks.

Each automated check is "target zero": any match is a finding and fails the check.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from . import model, scan
from .model import CheckResult, Finding, Severity


@dataclass(frozen=True)
class PatternCheck:
    """A single 'target zero' regex check."""

    id: str
    name: str
    bloc: str
    severity: Severity
    regex: re.Pattern[str]
    exclude_test: bool
    allow_markers: tuple[str, ...]
    note: str | None


def _c(  # noqa: PLR0913 - a check definition naturally has many fields
    id_: str,
    name: str,
    bloc: str,
    severity: Severity,
    pattern: str,
    *,
    exclude_test: bool = True,
    allow_markers: tuple[str, ...] = (),
    note: str | None = None,
) -> PatternCheck:
    return PatternCheck(id_, name, bloc, severity, re.compile(pattern), exclude_test, allow_markers, note)


def _checks() -> list[PatternCheck]:
    return [
        _c("A1", "logging not print", "A", Severity.CRITICAL, r"\bprint\(", note="use the logging module, not print()"),
        _c(
            "A2",
            "No bare except",
            "A",
            Severity.MAJOR,
            r"except\s*:|except\s+Exception\s*:\s*(#.*)?$",
            note="no bare/blanket except that swallows errors",
        ),
        _c(
            "A3",
            "No hardcoded secret",
            "A",
            Severity.CRITICAL,
            r"""(?i)(api_key|password|secret|token)\s*=\s*['"][^'"]+['"]|['"](gsk_|sk-|eyJ)""",
        ),
        _c(
            "A5",
            "Comments in English",
            "A",
            Severity.MINOR,
            r"#.*\b(le|la|les|une|des|avec|pour|donnee|donnees|fichier|nous|vous)\b",
            exclude_test=False,
            note="heuristic: French words in comments",
        ),
        _c(
            "A6",
            "No open-source attribution",
            "A",
            Severity.MAJOR,
            r"(?i)\b(nuclei|wappalyzer|nmap|recog)\b",
            exclude_test=False,
        ),
        _c(
            "A7",
            "Type hints on def",
            "A",
            Severity.MINOR,
            r"^\s*(async\s+)?def\s+\w+\s*\([^)]*\)\s*:",
            note="heuristic: function without -> return annotation",
        ),
        _c(
            "A10",
            "Fail-safe default",
            "A",
            Severity.MINOR,
            r"\.get\(\s*['\"]\w+['\"]\s*,\s*True\s*\)",
            note="verify this default does not open access on error",
        ),
        _c(
            "B1",
            "No SQL injection",
            "B",
            Severity.CRITICAL,
            r"""execute\(\s*f['"]|execute\([^)]*%[^)]*%|execute\([^)]*\.format\(""",
        ),
        _c(
            "B2",
            "No command injection",
            "B",
            Severity.CRITICAL,
            r"os\.system\(|subprocess\.[A-Za-z_]+\([^)]*shell\s*=\s*True",
        ),
        _c(
            "B5",
            "Path traversal guard",
            "B",
            Severity.MAJOR,
            r"=\s*open\(",
            note="verify path is validated against an allowed root",
        ),
        _c(
            "B6",
            "No eval/exec/unsafe deser",
            "B",
            Severity.CRITICAL,
            r"\beval\(|\bexec\(|pickle\.load|yaml\.load\(\s*[^)]*\)",
            allow_markers=("Loader=", "SafeLoader"),
        ),
        _c("B9", "TLS verification", "B", Severity.CRITICAL, r"verify\s*=\s*False|_create_unverified_context"),
        _c(
            "B10",
            "No assert for security",
            "B",
            Severity.MAJOR,
            r"^\s*assert\b",
            note="asserts are stripped under python -O; validate explicitly",
        ),
        _c("C1", "No stub", "C", Severity.MAJOR, r"raise NotImplementedError|^\s*\.\.\.\s*$|pass\s*#\s*TODO"),
        _c(
            "C7",
            "No manual JSON string",
            "C",
            Severity.MINOR,
            r"""json\s*=\s*f?['"].*\{""",
            note="build payloads with json.dumps, not f-strings",
        ),
        _c("F1", "Event store immutability (I1)", "F", Severity.CRITICAL, r"(?i)(UPDATE|DELETE)\b.{0,40}event"),
        _c(
            "F4",
            "Deterministic replay (I4)",
            "F",
            Severity.CRITICAL,
            r"datetime\.now\(|time\.time\(|random\.|uuid\.uuid4\(",
            note="forbidden in the decision path unless captured in the event",
        ),
    ]


def run_all(files: list[Path], root: Path) -> list[CheckResult]:
    """Run every check (pattern, structural, manual) over the scanned files."""
    loaded: list[tuple[str, list[str], list[bool]]] = []
    for p in files:
        content = scan.read_file(p)
        if content is None:
            continue
        flags = [True] * len(content.splitlines()) if scan.is_test_path(p) else scan.test_lines(content)
        loaded.append((_rel(p, root), content.splitlines(), flags))

    results: list[CheckResult] = []
    for check in _checks():
        findings: list[Finding] = []
        for path, lines, flags in loaded:
            for idx, line in enumerate(lines):
                if check.exclude_test and idx < len(flags) and flags[idx]:
                    continue
                if any(m in line for m in check.allow_markers):
                    continue
                if check.regex.search(line):
                    findings.append(Finding(path, idx + 1, line.strip()[:120]))
        if findings:
            results.append(model.failed(check.id, check.name, check.bloc, check.severity, findings))
        else:
            results.append(model.passed(check.id, check.name, check.bloc, check.severity, check.note))

    results.extend(_structural(files, root))
    results.extend(_manual())
    return results


def _structural(files: list[Path], root: Path) -> list[CheckResult]:
    locks = ("requirements.txt", "poetry.lock", "uv.lock", "Pipfile.lock", "pdm.lock")
    if any((root / m).is_file() for m in locks):
        a9 = model.passed("A9", "Dependency lockfile committed", "A", Severity.MAJOR)
    else:
        a9 = model.not_applicable(
            "A9",
            "Dependency lockfile committed",
            "A",
            Severity.MAJOR,
            "no requirements/lock file at project root (needed for pip-audit determinism)",
        )

    has_tests = any(scan.is_test_path(p) for p in files) or any(
        (scan.read_file(p) or "").find("def test_") >= 0 for p in files
    )
    if has_tests:
        c10 = model.passed("C10", "Tests present", "C", Severity.MAJOR)
    else:
        c10 = model.failed(
            "C10",
            "Tests present",
            "C",
            Severity.MAJOR,
            note="no test_*.py / tests/ found in scope",
        )
    return [a9, c10]


def _manual() -> list[CheckResult]:
    manual = [
        ("A4", "ruff format clean", "A", Severity.MAJOR, "covered by Bloc D3 (ruff format --check)"),
        ("A8", "Context managers for resources", "A", Severity.MAJOR, "manual: open()/locks via with-statement"),
        ("B3", "Hardcoded secrets", "B", Severity.CRITICAL, "covered by A3"),
        (
            "B4",
            "AuthN/Z + identity binding (I3)",
            "B",
            Severity.CRITICAL,
            "manual: protected routes; action tied to agent_id",
        ),
        ("B7", "Security logging", "B", Severity.MAJOR, "manual: attacks logged via logger.warning"),
        ("B8", "Input validation at boundary", "B", Severity.MAJOR, "manual: pydantic / explicit validation"),
        ("C2", "No mock data", "C", Severity.MAJOR, "manual: values from real data, not literals"),
        ("C3", "Async task cleanup", "C", Severity.MAJOR, "manual: tasks awaited / cancelled, no orphan create_task"),
        ("C4", "Exception chaining (raise from)", "C", Severity.MAJOR, "manual: raise NewError(...) from err"),
        ("C5", "No needless copies", "C", Severity.MINOR, "manual: covered by ruff/perf review"),
        ("C6", "Pool / client reuse", "C", Severity.MINOR, "manual: shared connection pool, not per-request"),
        ("C8", "IDs typed (UUID/ULID)", "C", Severity.MAJOR, "manual: parse at boundary before use"),
        ("C9", "Pagination on list endpoints", "C", Severity.MINOR, "manual: limit/offset or cursor"),
        ("E1", "R17 test file present", "E", Severity.CRITICAL, "manual: test invoking the route (TestClient)"),
        ("E2", "R17 test execution", "E", Severity.CRITICAL, "manual: pytest green (see Bloc D)"),
        ("E3", "R17 live smoke curl", "E", Severity.CRITICAL, "manual: real curl on the running service"),
        ("E4", "R17 response envelope", "E", Severity.MAJOR, "manual: frontend unwraps .data"),
        ("F2", "Control-plane mediation (I2)", "F", Severity.CRITICAL, "manual: no direct agent->external bypass"),
        ("F3", "Side-effects mediated (I5)", "F", Severity.CRITICAL, "manual: external effects via controlled proxies"),
        ("F5", "Approval blocking (I6)", "F", Severity.CRITICAL, "manual: action blocks until resolution or timeout"),
    ]
    return [model.not_applicable(i, n, b, s, note) for i, n, b, s, note in manual]


def _rel(p: Path, root: Path) -> str:
    try:
        return str(p.relative_to(root))
    except ValueError:
        return str(p)
