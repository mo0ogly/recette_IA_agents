# python_recette

Static recette scorer for inspect_ia_agents Python code. Python counterpart of
the Rust `inspect_ia_agents_recette` binary and the executable backend of the
`/python-recette` command.

Automates the pattern-based blocs (A conventions, B OWASP, C arch/perf,
F invariants I1-I6), orchestrates the static-analysis bloc (D: ruff, pip-audit,
mypy, bandit), and emits a scored report plus a CI exit code.

## Setup

```bash
scripts/install_python_audit.sh      # creates .venv-pyaudit with ruff/mypy/bandit/pip-audit/pytest
```

A missing tool marks its bloc `N/A` (never a fabricated result).

## Usage

```bash
python -m python_recette <file|dir>             # text report
python -m python_recette --format json <dir>    # JSON (for apex / audit-pdca)
python -m python_recette --skip-tools <dir>     # blocs A/B/C/F only (fast, no tools)
python -m python_recette --min-score 39 <dir>   # exit 0 iff gate passes
```

Run from this directory (or set `PYTHONPATH` to it).

## Tool mapping (Go -> Python)

| Go (/go-recette) | Python | Bloc |
|------------------|--------|------|
| go vet | `ruff check` (+ flake8-bandit S-rules) | D1 |
| govulncheck | `pip-audit` (OSV / PyPI advisory) | D2 |
| gofmt | `ruff format --check` | D3 |
| (types) | `mypy` | D4 |
| gosec | `bandit` (MEDIUM+) | D5 |
| go test | `pytest` | C10 |

## Scoring

A/B/C = 10 each, D = 5, E = 4, F = 5 (nominal /44). `N/A` checks are excluded and
the bloc renormalized; the global score is reported raw and normalized to /44.
Any critical failure, any bloc E failure, or any bloc F violation forces a
blocking verdict.

## Development (dogfood)

```bash
V=../../.venv-pyaudit/bin
$V/ruff check . && $V/ruff format --check . && $V/mypy python_recette && PYTHONPATH=. $V/pytest -q
```

## Limitations (v1)

- Pattern checks are line-regex based; a few carry a "verify manually" note.
- Semantic checks (auth/identity, async cleanup, control-plane mediation,
  approval blocking, R17 contract gate) are surfaced as `N/A` for human review.
- A linter scanning its own `patterns.py` matches its own rule source strings;
  inspect with `--skip-tools` only, do not gate the tool on itself.
