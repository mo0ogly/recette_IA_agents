# Build Pipeline Python -- Reference partagee APEX & PDCA

> Mandatory pipeline for every Python file created or modified in AgentRail.
> Python is the secondary backend language (Rust primary, see build-pipeline-rust.md).
> Integrates: ruff, mypy, bandit, pip-audit, pytest.

---

## Mandatory tooling (install via scripts/install_python_audit.sh)

| Tool | Role | Go (/go-recette) equivalent |
|------|------|------------------------------|
| `ruff check` | lint (800+ rules) + flake8-bandit `S` security rules | go vet + part of gosec |
| `ruff format --check` | formatting | gofmt |
| `mypy` | static type checking | (no direct Go equiv) |
| `bandit` | deep security SAST | gosec |
| `pip-audit` | vulnerable dependency scan (OSV / PyPI advisory) | govulncheck |
| `pytest` | test runner | go test |

Tools live in the project venv `.venv-pyaudit/bin/`. A missing tool marks its
bloc `N/A` (never invent a result, R18).

---

## Sequential pipeline (each `.py` file)

```
EDIT/WRITE .py
    |
    v
STEP 1: ruff check (lint + security S-rules)
    |-- .venv-pyaudit/bin/ruff check {file}  -> 0 findings = PASS
    |-- FAIL -> fix (ruff --fix for autofixable)
    |
    v
STEP 2: ruff format --check
    |-- .venv-pyaudit/bin/ruff format --check {file}  -> 0 diff
    |-- FAIL -> ruff format {file}
    |
    v
STEP 3: mypy (types)
    |-- .venv-pyaudit/bin/mypy {file or package}  -> 0 errors
    |-- type hints on all public functions
    |
    v
STEP 4: bandit (security SAST)
    |-- .venv-pyaudit/bin/bandit -q -r {package}  -> 0 HIGH/MEDIUM
    |
    v
STEP 5: pytest (test-first)
    |-- create tests/test_{module}.py BEFORE merge
    |-- .venv-pyaudit/bin/pytest -q  -> green
    |
    v
STEP 6: pip-audit (deps, at package/repo level)
    |-- .venv-pyaudit/bin/pip-audit  -> 0 known vulns
    |
    v
GATE PASSED -> file ready for RECETTE phase
```

---

## Python construction rules

### Logging
```python
# CORRECT
import logging
logger = logging.getLogger(__name__)
logger.info("parser ready", extra={"component": "PARSER"})

# FORBIDDEN
print("processing:", id)            # not application logging
```

### Error handling
- No bare `except:` and no `except Exception: pass` that swallows errors.
- Raise typed exceptions; chain with `raise NewError(...) from err`.
- No `assert` for validation in non-test code (`python -O` strips asserts).

### Security (OWASP, bandit + ruff S-rules)
```python
# CORRECT: parameterized query
cur.execute("SELECT * FROM users WHERE id = %s", (user_id,))

# FORBIDDEN
cur.execute(f"SELECT * FROM users WHERE id = {user_id}")   # SQL injection
os.system(f"ping {host}")                                   # command injection
subprocess.run(cmd, shell=True)                             # shell injection
eval(user_input); pickle.loads(data)                        # RCE / unsafe deser
requests.get(url, verify=False)                             # TLS bypass
```

### Types
- Type hints on every public function signature; `-> None` included.
- `mypy --strict` for new packages where practical.

### Tests (pytest)
```python
def test_parse_returns_record_on_valid_input():
    out = parse("HDR\nbody")
    assert out.kind == RecordKind.HEADER

def test_parse_raises_on_empty():
    with pytest.raises(ParseError):
        parse("")
```

---

## Score pipeline Python /5

| Critere | Points | Quand 1 point |
|---------|--------|---------------|
| ruff check clean | /1 | 0 findings |
| ruff format --check clean | /1 | 0 diff |
| mypy clean | /1 | 0 errors |
| bandit clean | /1 | 0 HIGH/MEDIUM |
| pytest + pip-audit | /1 | tests green AND 0 known vuln deps |

---

## Security score /20 (PDCA security domain, Python files)

Start at 20, subtract per finding:
- pip-audit HIGH/CRITICAL vulnerable dependency: -6 each
- bandit HIGH severity: -4 each
- ruff `S` (flake8-bandit) finding: -2 each
- mypy error on a security-relevant boundary: -2 each

Floor at 0. Any pip-audit HIGH/CRITICAL or bandit HIGH is a hard gate (CRITICAL FAIL).
