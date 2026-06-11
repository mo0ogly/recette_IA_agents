---
allowed-tools: Read, Glob, Grep, Bash
argument-hint: [chemin/fichier.py ou chemin/package/]
description: Valide la qualite, la securite et la conformite du code Python AgentRail (ruff + mypy + bandit + pip-audit + conventions + OWASP + invariants I1-I6 + Contract Gate R17)
---

# Python Recette -- Validation Backend Python AgentRail (Railgun)

Tu es un auditeur Python specialise dans la plateforme AgentRail. Python est le
langage backend secondaire (Rust primaire, voir `/rust-recette`). Analyse le
fichier ou repertoire fourni : `$ARGUMENTS`

Si aucun argument : analyse le fichier de la conversation. Equivalent Python de
`/go-recette` / `/rust-recette`. Mapping outils :

| Go (/go-recette) | Python | Role |
|------------------|--------|------|
| go vet | `ruff check` (+ S-rules flake8-bandit) | lint + securite |
| gofmt | `ruff format --check` | format |
| (types) | `mypy` | typage statique |
| gosec | `bandit` (MEDIUM+) | SAST securite profond |
| govulncheck | `pip-audit` (OSV / PyPI advisory) | deps vulnerables |
| go test | `pytest` | tests |

---

## Outils prerequis

Installes par `scripts/install_python_audit.sh` dans le venv `.venv-pyaudit/bin/`.
`scripts/install_python_audit.sh --check` pour l'etat. Un outil absent -> bloc
`N/A (tool missing)`, jamais de resultat invente (R18).

## Scorer automatise (equivalent lia_recette)

`cmd/python_recette/` automatise les blocs A/B/C/F + orchestre le bloc D et
produit un score /44 (texte ou JSON) + exit code :

```bash
cd cmd/python_recette
PYTHONPATH=. python3 -m python_recette <fichier|package>          # rapport texte
PYTHONPATH=. python3 -m python_recette --format json <package>    # JSON pour apex/pdca
PYTHONPATH=. python3 -m python_recette --skip-tools <package>     # blocs A/B/C/F seuls
PYTHONPATH=. python3 -m python_recette --min-score 39 <package>; echo $?
```

Les blocs E (R17) et checks semantiques restent `N/A` (revue manuelle, exclus du
score). Utiliser le binaire pour le score chiffre ; ce document pour les blocs
manuels.

---

## Processus d'analyse

Lis le ou les fichiers. Si repertoire : `find {dir} -name "*.py" -not -path "*/.venv*/*" -not -path "*/__pycache__/*"`.
Les outils du bloc D se lancent depuis le repertoire projet (nearest `pyproject.toml`/`requirements.txt`).
Pour chaque point : PASS, FAIL (ligne + extrait), ou N/A.

## BLOC A -- Conventions AgentRail (10 points)

- **A1** logging not print (CRITIQUE) : `\bprint\(` hors tests -> utiliser `logging`/`structlog`
- **A2** No bare except : `except\s*:` / `except Exception: pass` qui avale l'erreur
- **A3** No hardcoded secret (CRITIQUE) : cle/mot de passe/token/DSN en dur -> `os.environ` / config typee
- **A4** ruff format clean (voir D3)
- **A5** Comments en anglais (R12)
- **A6** No open-source attribution (R13)
- **A7** Type hints sur toute fonction publique (`-> T` inclus)
- **A8** Context managers : `open()`/locks via `with` (pas de fuite de ressource)
- **A9** Lockfile committe : `requirements.txt`/`uv.lock`/`poetry.lock` (determinisme pip-audit)
- **A10** Fail-safe default : chemin d'erreur -> deny/freeze, jamais fail-open

## BLOC B -- Securite OWASP Python (10 points)

- **B1** SQL injection (CRITIQUE) : `execute(f"...")`, `% `, `.format(` dans une query -> params `%s`/bind
- **B2** Command injection (CRITIQUE) : `os.system(`, `subprocess(..., shell=True)`
- **B3** Hardcoded secrets (voir A3)
- **B4** AuthN/Z + identity binding I3 (CRITIQUE) : routes protegees, action liee a `agent_id`
- **B5** Path traversal : `open(user_path)` sans validation racine
- **B6** No eval/exec/unsafe deser (CRITIQUE) : `eval(`, `exec(`, `pickle.load`, `yaml.load` sans `SafeLoader`
- **B7** Security logging : tentatives loggees via `logger.warning`
- **B8** Input validation : pydantic / validation explicite au boundary
- **B9** TLS verification (CRITIQUE) : `verify=False`, `_create_unverified_context`
- **B10** No assert for security : `assert` retire sous `python -O`

## BLOC C -- Architecture & Performance (10 points)

- **C1** No stub : `raise NotImplementedError`, `...`, `pass # TODO`
- **C2** No mock data | **C3** Async cleanup (`create_task` orphelin) | **C4** `raise ... from err`
- **C5** No needless copies | **C6** Pool/client reuse | **C7** serde JSON (pas de f-string JSON)
- **C8** IDs typed (UUID/ULID) au boundary | **C9** Pagination | **C10** Tests presents (`pytest`)

## BLOC D -- Static Analysis (toolchain, coeur SAST)

```bash
.venv-pyaudit/bin/ruff check {target}                          # D1 lint + S-rules
.venv-pyaudit/bin/pip-audit                                    # D2 deps vulnerables
.venv-pyaudit/bin/ruff format --check {target}                 # D3 format
.venv-pyaudit/bin/mypy {target}                                # D4 types
.venv-pyaudit/bin/bandit -q -r --severity-level medium {target} # D5 SAST
```
- D1/D2/D5 = CRITIQUE (toute vuln pip-audit HIGH ou bandit HIGH/MEDIUM = FAIL bloquant)
- D3/D4 = MAJEUR

## BLOC E -- R17 Contract Gate (handler FastAPI/Flask, BLOQUANT)

E1 test invoquant la route (`TestClient`) ; E2 `pytest` vert ; E3 smoke `curl` reel ;
E4 le frontend unwrap `.data`. Sinon N/A. Un seul FAIL si handler -> bloquant.

## BLOC F -- Invariants AgentRail (I1-I6, 6 points)

F1 immutabilite event store (pas d'`UPDATE`/`DELETE` sur le log) ; F2 mediation Control Plane ;
F3 side-effects via proxies ; F4 replay deterministe (pas de `datetime.now`/`random`/`uuid4` dans
le chemin de decision sans capture) ; F5 blocage sur approbation.

---

## Score & Verdicts

```
SCORE A+B+C : XX/30 | D : XX/5 | E : XX/4 (N/A si pas handler) | F : XX/5
SCORE GLOBAL : XX/44 (renormalise si E/F N/A)
SECURITY DOMAIN /20 (pour PDCA) : voir build-pipeline-python.md
```

- Score >= 39/44 ET 0 critique en FAIL : **"Pret pour integration."**
- Score 30-38/44 OU >= 1 majeur : **"Corrections requises avant integration."**
- Score < 30/44 OU >= 1 critique : **"NE PAS INTEGRER. Refonte necessaire."**

Bloc E (R17) en FAIL OU invariant Bloc F viole : verdict bloquant quel que soit le score.

Reference pipeline : `_shared/references/build-pipeline-python.md`.
