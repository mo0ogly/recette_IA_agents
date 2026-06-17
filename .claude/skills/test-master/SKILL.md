---
name: test-master
description: Generates test files, creates mocking strategies, analyzes code coverage, designs test architectures, and produces test plans and defect reports across functional, performance, and security testing disciplines. Use when writing unit tests, integration tests, or E2E tests; creating test strategies or automation frameworks; analyzing coverage gaps; performance testing with k6 or Artillery; security testing with OWASP methods; debugging flaky tests; or working on QA, regression, test automation, quality gates, shift-left testing, or test maintenance.
license: MIT
metadata:
  author: https://github.com/Jeffallan
  version: "1.1.1"
  domain: quality
  triggers: test, testing, QA, unit test, integration test, E2E, coverage, performance test, security test, regression, test strategy, test automation, test framework, quality metrics, defect, exploratory, usability, accessibility, localization, manual testing, shift-left, quality gate, flaky test, test maintenance
  role: specialist
  scope: testing
  output-format: report
  related-skills: fullstack-guardian, playwright-expert, devops-engineer, debugging-wizard, code-reviewer, feature-forge
---

# Test Master (inspect_ia_agents Edition)

## inspect_ia_agents Adaptations (MANDATORY)

- **Stack tests** :
  - Backend Rust : `cargo test` / `cargo nextest run` (gateway Axum dans `cmd/*`,
    eBPF + broker dans `discoveryprobe/`) -- depuis le crate cible
  - Harnais Python : `python3 -m unittest discover -s tests` (aussi `./recette.sh test`,
    `make test`) ; lint/format/type/security via `make gates`
  - Frontend : Vitest + React Testing Library dans `console/src/**/*.test.tsx` via
    `npx vitest run` ou `./recette.sh console-test` (JAMAIS `npx vitest` hand-launch hors
    `./recette.sh` -- single entry point R19)
  - E2E : Playwright (voir `/playwright-expert`) ; smoke live versionne `scripts/smoke_*.py`
    via `./recette.sh smoke`
  - Coverage guard recette : `tests/test_coverage_guard.py` (aussi `make recette`) -- un trou
    de recette = test rouge, jamais a trouver a la main
- **R16 Contract Gate (BLOCKING)** : tout composant React appelant une API doit avoir (1) fixture réelle
  `__fixtures__/{component}.fixture.json`, (2) render-and-assert test, (3) Playwright smoke
  post-build. Cycle PDCA / APEX ne peut clôturer sans ces 3 éléments
- **Test-first enforcement** : utiliser `/test-first` qui wrap la création de test obligatoire
  après toute modif handler Rust / module Python recette / composant React / hook / service --
  AVANT de déclarer "terminé"
- **Coverage targets** : harnais Python recette + Rust backend ≥ 70% lignes, frontend services
  ≥ 60%, chemins critiques (decision policy/risk, identite, approbation) ≥ 80%
- **Determinisme (I4 / R11)** : pas de `time.time()`/`datetime.now()`/`random` dans l'execution
  d'un agent, le chemin de decision, ou un juge ; horloge logique injectee
  (`recette.events.LogicalClock`), `event_id` derive d'une sequence. Tout chemin de
  decision/juge ajoute embarque un test de replay byte-stable
- **Mock policy** : les fixtures sont explicites et confinees a `tests/` (Python) /
  `__fixtures__/` (console) ; elles ne fuient jamais dans `recette/` runtime. Pas de mock du
  proxy/lab dans un chemin de production (R4)
- **Performance testing** : k6 / Artillery pour les endpoints de la Gateway gouvernee
  (ex `/probe/capture`, `/discovery/check`) servis par `./recette.sh platform up`
- **Security testing** : déléguer à `/secure-code-guardian` (prévention) + `/code-reviewer`
  (audit) ; `/test-master` couvre le fonctionnel / perf / régression
- **Flaky tests** : interdit -- si un test flake, investiguer (pas de retry en CI sans fix
  sous-jacent)
- **Companion skills** : `/test-first` (enforcement), `/playwright-expert` (E2E),
  `/rust-recette` (SAST Rust), `/react-recette` (SAST React), `/python-recette` (gates Python),
  `/systematic-debugging` (fix)

---

## Core Workflow

1. **Define scope** — Identify what to test and which testing types apply
2. **Create strategy** — Plan the test approach across functional, performance, and security perspectives
3. **Write tests** — Implement tests with proper assertions (see example below)
4. **Execute** — Run tests and collect results
   - If tests fail: classify the failure (assertion error vs. environment/flakiness), fix root cause, re-run
   - If tests are flaky: isolate ordering dependencies, check async handling, add retry or stabilization logic
5. **Report** — Document findings with severity ratings and actionable fix recommendations
   - Verify coverage targets are met before closing; flag gaps explicitly

## Quick-Start Example

A minimal Jest unit test illustrating the key patterns this skill enforces:

```js
// ✅ Good: meaningful description, specific assertion, isolated dependency
describe('calculateDiscount', () => {
  it('applies 10% discount for premium users', () => {
    const result = calculateDiscount({ price: 100, userTier: 'premium' });
    expect(result).toBe(90); // specific outcome, not just truthy
  });

  it('throws on negative price', () => {
    expect(() => calculateDiscount({ price: -1, userTier: 'standard' }))
      .toThrow('Price must be non-negative');
  });
});
```

Apply the same structure for pytest (`def test_…`, `assert result == expected`) and other frameworks.

## Reference Guide

Load detailed guidance based on context:

<!-- TDD Iron Laws and Testing Anti-Patterns adapted from obra/superpowers by Jesse Vincent (@obra), MIT License -->

| Topic | Reference | Load When |
|-------|-----------|-----------|
| Unit Testing | `references/unit-testing.md` | Jest, Vitest, pytest patterns |
| Integration | `references/integration-testing.md` | API testing, Supertest |
| E2E | `references/e2e-testing.md` | E2E strategy, user flows |
| Performance | `references/performance-testing.md` | k6, load testing |
| Security | `references/security-testing.md` | Security test checklist |
| Reports | `references/test-reports.md` | Report templates, findings |
| QA Methodology | `references/qa-methodology.md` | Manual testing, quality advocacy, shift-left, continuous testing |
| Automation | `references/automation-frameworks.md` | Framework patterns, scaling, maintenance, team enablement |
| TDD Iron Laws | `references/tdd-iron-laws.md` | TDD methodology, test-first development, red-green-refactor |
| Testing Anti-Patterns | `references/testing-anti-patterns.md` | Test review, mock issues, test quality problems |

## Constraints

**MUST DO**
- Test happy paths AND error/edge cases (e.g., empty input, null, boundary values)
- Mock external dependencies — never call real APIs or databases in unit tests
- Use meaningful `it('…')` descriptions that read as plain-English specifications
- Assert specific outcomes (`expect(result).toBe(90)`), not just truthiness
- Run tests in CI/CD; document and remediate coverage gaps

**MUST NOT**
- Skip error-path testing (e.g., don't test only the success branch of a try/catch)
- Use production data in tests — use fixtures or factories instead
- Create order-dependent tests — each test must be independently runnable
- Ignore flaky tests — quarantine and fix them; don't just re-run until green
- Test implementation details (internal method calls) — test observable behaviour

## Output Templates

When creating test plans, provide:
1. Test scope and approach
2. Test cases with expected outcomes
3. Coverage analysis
4. Findings with severity (Critical/High/Medium/Low)
5. Specific fix recommendations

## Decomposition des sous-taches

Au demarrage, decomposer toute strategie de tests en sous-taches independantes :

- [ ] Sous-tache 1 : cartographier les tests existants (Glob `**/*_test.rs`, `tests/**/*.py`, `**/*.test.{tsx,ts}`, `**/*.spec.ts`)
- [ ] Sous-tache 2 : identifier les gaps de coverage (backend 70%, frontend 60%, critique 80%)
- [ ] Sous-tache 3 : verifier les 3 pieces R16 (fixture, render-and-assert, Playwright smoke)
- [ ] Sous-tache 4 : ecrire les tests manquants (unit + integration + E2E selon scope)
- [ ] Sous-tache 5 : executer `cargo test`/`cargo nextest run` (Rust) + `python3 -m unittest discover -s tests` (harnais) + `./recette.sh console-test` (frontend)
- [ ] Sous-tache 6 : verifier absence de flaky + determinisme (replay byte-stable) + rapport de coverage

Sous-taches 1-3 parallelisables. Sous-tache 5 depend de 4.

## Plan d'execution

Pour toute strategie de test ou refactor de suite de tests (> 3 fichiers) :

1. Creer `docs/tracking/PLAN_TEST_MASTER_{MODULE}_{YYYY-MM-DD}.md` avant d'ecrire un test.
2. Template : `docs/tracking/PLAN_TEMPLATE.md`.
3. Cocher chaque sous-tache a la completion.
4. Si replanification : Status -> REPLANIFIE + lien vers nouveau plan.

Pour un test ponctuel (1 handler ou 1 composant) : plan inline suffit.

## Adaptation et replanification

Si 2 etapes consecutives echouent (ex: test echoue + fix qui casse un autre test) :

- STOP
- Invoquer `/replan` -> produit `PLAN_TEST_MASTER_*_REPLAN_*.md`
- NE PAS ajouter des retries ou des mocks pour contourner -- corriger la cause

Declencheurs typiques :
- Test flaky detecte -> REPLAN (isoler la cause -- async, ordre, env)
- Coverage cible non atteinte apres ajout de tests -> REPLAN (revoir le scope)
- R16 fixture ne matche pas le backend live -> REPLAN (re-capturer la reponse via curl/DevTools)

## Outils declares

| Outil | Usage | Retry policy |
|-------|-------|--------------|
| `Read`, `Grep`, `Glob` | Cartographier tests existants + handler/module cible avant d'ecrire | N/A |
| `Write`, `Edit` | Creer/modifier `*_test.rs`, `tests/**/*.py`, `*.test.tsx`, `*.spec.ts` | N/A |
| `Bash cargo test` / `cargo nextest run` | Gate backend Rust (depuis le crate cible) | 1 retry flakiness env |
| `Bash python3 -m unittest discover -s tests` | Gate harnais Python (aussi `./recette.sh test`) | 1 retry flakiness env |
| `Bash ./recette.sh console-test` | Gate frontend Vitest+RTL -- JAMAIS `npx vitest` hand-launch (R19) | 1 retry flakiness |
| `Bash make recette` | Coverage guard recette (`tests/test_coverage_guard.py`) | N/A |
| `Bash k6 run` | Load tests endpoints Gateway gouvernee | N/A |
| `Bash ./recette.sh smoke` | Preuve live versionnee (`scripts/smoke_*.py`), jamais dans `/tmp` | N/A |
| `TaskCreate` | Tracking si > 3 sous-taches | N/A |
| `Skill(playwright-expert)` | E2E smoke tests + R16 E3 | Obligatoire si composant API |
| `Skill(test-first)` | Enforcement test AVANT merge | Obligatoire sur nouveaux handlers/modules |

Selection dynamique : outil choisi selon le type de test (unit vs integration vs E2E vs perf).

## Tracabilite agentique

Logger dans `docs/tracking/decision_log.jsonl` chaque decision non triviale :

- Choix de strategie de mock (stub vs spy vs real DB) + justification
- Seuil de coverage choisi pour un composant critique
- Delegation a `/playwright-expert` pour E2E + raison

Format :
```json
{"timestamp":"...","session":"test-master-{module}","action":"...","reasoning":"...","alternatives_rejected":["..."],"outcome":"...","confidence":"high","plan_ref":"PLAN_TEST_MASTER_*.md"}
```

RETEX en fin de session si score agentique < 40/50 -> `docs/tracking/retex/RETEX_TEST_MASTER_YYYY-MM-DD.md`.

## VERIFICATION GATE (BLOQUANT)

Apres execution, AVANT de declarer termine :

- [ ] `cargo test` / `cargo nextest run` passe (depuis le crate cible) -- zero test en echec
- [ ] `python3 -m unittest discover -s tests` passe + `make gates` clean -- zero test en echec
- [ ] `./recette.sh console-test` passe (frontend `console/`) -- zero test en echec
- [ ] Coverage backend (Rust + harnais Python) >= 70% lignes (chemins critiques decision/identite/approbation >= 80%)
- [ ] Coverage frontend services >= 60%
- [ ] R16 3 pieces presentes : fixture reelle + render-and-assert + Playwright smoke
- [ ] Determinisme (I4) : chemin de decision/juge ajoute a un test de replay byte-stable
- [ ] Zero test flaky detecte (executer 2x si doute)

Si un gate echoue : STOP, fix la cause racine, re-gate. JAMAIS retry CI sans fix sous-jacent.

## Scoring agentique

| Critere | Score |
|---------|-------|
| C1 Decomposition : sous-taches identifiees + coverage gaps cartographies ? | /10 |
| C2 Planification : PLAN_*.md cree et suivi ? | /10 |
| C3 Replanification : /replan declenche sur test flaky ou coverage miss ? | /10 |
| C4 Outillage : cargo test + unittest/make gates + recette.sh console-test + k6 + playwright-expert invoques selon scope ? | /10 |
| C5 Tracabilite : decision_log + RETEX produits ? | /10 |

Score total /50 -- >= 40 : Exemplaire | 30-39 : Acceptable | < 30 : RETEX obligatoire
