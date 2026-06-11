"""Bloc D: shell out to the Python static-analysis toolchain.

ruff (lint + format), mypy (types), bandit (SAST), pip-audit (deps).
"""

from __future__ import annotations

import subprocess  # noqa: S404 - we run a fixed, non-shell allowlist of tools
from pathlib import Path

from . import model
from .model import CheckResult, Severity

_TOOLS = ("ruff", "mypy", "bandit", "pip-audit")


def _tool_path(name: str, root: Path) -> str | None:
    """Locate a tool: prefer the project venv, then PATH."""
    for base in (root, *root.parents):
        candidate = base / ".venv-pyaudit" / "bin" / name
        if candidate.is_file():
            return str(candidate)
    import shutil

    return shutil.which(name)


def _run(args: list[str], cwd: Path) -> tuple[int, str]:
    try:
        proc = subprocess.run(  # noqa: S603 - args are tool-controlled, shell=False
            args, cwd=cwd, capture_output=True, text=True, check=False
        )
    except OSError as exc:  # pragma: no cover - spawn failure
        return 1, f"failed to run {args[0]}: {exc}"
    return proc.returncode, proc.stdout + proc.stderr


def run_all(target: Path, root: Path) -> list[CheckResult]:
    """Run the full Bloc D gate against ``target`` from ``root``."""
    paths = {name: _tool_path(name, root) for name in _TOOLS}
    tgt = str(target)
    out: list[CheckResult] = []

    # D1 -- ruff check (lint + security S-rules).
    ruff = paths["ruff"]
    if ruff:
        code, _ = _run([ruff, "check", tgt], root)
        out.append(
            model.passed("D1", "ruff check", "D", Severity.CRITICAL)
            if code == 0
            else model.failed("D1", "ruff check", "D", Severity.CRITICAL, note="ruff reported findings")
        )
    else:
        out.append(model.not_applicable("D1", "ruff check", "D", Severity.CRITICAL, "ruff not installed"))

    # D2 -- pip-audit (govulncheck equivalent).
    pa = paths["pip-audit"]
    if pa:
        code, text = _run([pa, "--progress-spinner", "off"], root)
        vulns = text.lower().count("vulnerability") + text.count("PYSEC-") + text.count("GHSA-")
        out.append(
            model.passed("D2", "pip-audit", "D", Severity.CRITICAL)
            if code == 0
            else model.failed(
                "D2", "pip-audit", "D", Severity.CRITICAL,
                note=f"vulnerable dependency advisories detected ({vulns} markers)",
            )
        )
    else:
        out.append(model.not_applicable("D2", "pip-audit", "D", Severity.CRITICAL, "pip-audit not installed"))

    # D3 -- ruff format --check (gofmt).
    if ruff:
        code, _ = _run([ruff, "format", "--check", tgt], root)
        out.append(
            model.passed("D3", "ruff format", "D", Severity.MAJOR)
            if code == 0
            else model.failed("D3", "ruff format", "D", Severity.MAJOR, note="not formatted (run ruff format)")
        )
    else:
        out.append(model.not_applicable("D3", "ruff format", "D", Severity.MAJOR, "ruff not installed"))

    # D4 -- mypy (types).
    mypy = paths["mypy"]
    if mypy:
        code, _ = _run([mypy, tgt], root)
        out.append(
            model.passed("D4", "mypy", "D", Severity.MAJOR)
            if code == 0
            else model.failed("D4", "mypy", "D", Severity.MAJOR, note="type errors reported")
        )
    else:
        out.append(model.not_applicable("D4", "mypy", "D", Severity.MAJOR, "mypy not installed"))

    # D5 -- bandit (deep SAST).
    bandit = paths["bandit"]
    if bandit:
        code, text = _run([bandit, "-q", "-r", tgt], root)
        high = text.count("Severity: High")
        out.append(
            model.passed("D5", "bandit", "D", Severity.CRITICAL)
            if code == 0 and high == 0
            else model.failed("D5", "bandit", "D", Severity.CRITICAL, note=f"bandit issues ({high} HIGH)")
        )
    else:
        out.append(model.not_applicable("D5", "bandit", "D", Severity.CRITICAL, "bandit not installed"))

    return out


def skipped_bloc_d() -> list[CheckResult]:
    """Bloc D entries when ``--skip-tools`` is set."""
    names = [("D1", "ruff check"), ("D2", "pip-audit"), ("D3", "ruff format"), ("D4", "mypy"), ("D5", "bandit")]
    return [
        model.not_applicable(i, n, "D", Severity.CRITICAL, "skipped (--skip-tools)") for i, n in names
    ]
