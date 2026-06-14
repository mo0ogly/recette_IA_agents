---
name: code-reviewer
description: Analyzes code diffs and files to identify bugs, security vulnerabilities (SQL injection, XSS, insecure deserialization), code smells, N+1 queries, naming issues, and architectural concerns, then produces a structured review report with prioritized, actionable feedback. Use when reviewing pull requests, conducting code quality audits, identifying refactoring opportunities, or checking for security issues. Invoke for PR reviews, code quality checks, refactoring suggestions, review code, code quality. Complements specialized skills (security-reviewer, test-master) by providing broad-scope review across correctness, performance, maintainability, and test coverage in a single pass.
license: MIT
allowed-tools: Read, Grep, Glob
metadata:
  author: https://github.com/Jeffallan
  version: "1.1.0"
  domain: quality
  triggers: code review, PR review, pull request, review code, code quality
  role: specialist
  scope: review
  output-format: report
  related-skills: security-reviewer, test-master, architecture-designer
---

# Code Reviewer (LIA-SEC Edition)

## LIA-SEC Adaptations (MANDATORY)

- **Scope de review** : diff staged/unstaged + fichiers modifiés de la session. Ne jamais
  reviewer TOUT le repo (613 fichiers Go, 400+ TSX) -- se limiter au changeset
- **Rules R1-R24** : enforcer systématiquement (voir `.claude/rules/`) :
  - R1 Git Protocol (conventional commits, pas de "Co-Authored-By: Claude")
  - R5 PostgreSQL First (pas de hardcoding, utiliser `system_variables`)
  - R6 Custom Loggers (LogSystemEvent Go, customLogger React -- JAMAIS fmt.Println/console.log)
  - R8 UI Help English Only (aide contextuelle via `/create-ui-help`)
  - R10 No Emoji (zero emoji dans code/UI/docs/commits)
  - R12 Code Comments English Only
  - R17 Frontend Contract Gate (fixture + render-test + Playwright smoke)
  - R18 Verify Facts (pas d'affirmation sans commande exécutée)
  - R20 Doc After Code (maj `_alire/01_DOCUMENTATION/` dans la même passe)
  - R21 Dialog No Truncation, R23 Chart External Labels, R24 No Backslash Copy-Paste
- **Complémentaire** : `/code-reviewer` = broad-scope (correctness/perf/maintainability) ;
  `/security-reviewer` = deep-dive security CVSS ; `/go-recette` = SAST Go
  (gosec+govulncheck) ; `/react-recette` = SAST React. Utiliser les 4 en combo dans
  `/audit-pdca` Phase CHECK
- **Output format** : rapport structuré avec prio (CRITICAL / HIGH / MEDIUM / LOW),
  file:line refs, remediation concrète. Sauvegarder dans
  `_alire/02_LOGS/Journals/code_review/YYYY-MM-DD_{module}.md`
- **Anti-patterns LIA-SEC à détecter systématiquement** :
  - `<Grid item xs={...}>` (MUI v6 legacy -- doit être `<Grid size={{xs:...}}>`)
  - `fetch('/api/...')` brut (doit être `fetchWithConfig`)
  - `const API_URL = 'http://localhost:8081'` (R5 : `getBackendUrl()`)
  - `fontFamily: 'monospace'` hardcodé (doit être `'inherit'`)
  - Service qui `return resp.json()` sans unwrap `.data` (R17)
  - HelpButton pointant vers un `ui_help_content` vide
- **Companion skills** : `/go-recette`, `/react-recette`, `/security-reviewer`,
  `/test-master` (coverage), `/commit-check` (pre-commit final)

---

Senior engineer conducting thorough, constructive code reviews that improve quality and share knowledge.

## When to Use This Skill

- Reviewing pull requests
- Conducting code quality audits
- Identifying refactoring opportunities
- Checking for security vulnerabilities
- Validating architectural decisions

## Core Workflow

1. **Context** — Read PR description, understand the problem being solved. **Checkpoint:** Summarize the PR's intent in one sentence before proceeding. If you cannot, ask the author to clarify.
2. **Structure** — Review architecture and design decisions. Ask: Does this follow existing patterns in the codebase? Are new abstractions justified?
3. **Details** — Check code quality, security, and performance. Apply the checks in the Reference Guide below. Ask: Are there N+1 queries, hardcoded secrets, or injection risks?
4. **Tests** — Validate test coverage and quality. Ask: Are edge cases covered? Do tests assert behavior, not implementation?
5. **Feedback** — Produce a categorized report using the Output Template. If critical issues are found in step 3, note them immediately and do not wait until the end.

> **Disagreement handling:** If the author has left comments explaining a non-obvious choice, acknowledge their reasoning before suggesting an alternative. Never block on style preferences when a linter or formatter is configured.

## Reference Guide

Load detailed guidance based on context:

<!-- Spec Compliance and Receiving Feedback rows adapted from obra/superpowers by Jesse Vincent (@obra), MIT License -->

| Topic | Reference | Load When |
|-------|-----------|-----------|
| Review Checklist | `references/review-checklist.md` | Starting a review, categories |
| Common Issues | `references/common-issues.md` | N+1 queries, magic numbers, patterns |
| Feedback Examples | `references/feedback-examples.md` | Writing good feedback |
| Report Template | `references/report-template.md` | Writing final review report |
| Spec Compliance | `references/spec-compliance-review.md` | Reviewing implementations, PR review, spec verification |
| Receiving Feedback | `references/receiving-feedback.md` | Responding to review comments, handling feedback |

## Review Patterns (Quick Reference)

### N+1 Query — Bad vs Good
```python
# BAD: query inside loop
for user in users:
    orders = Order.objects.filter(user=user)  # N+1

# GOOD: prefetch in bulk
users = User.objects.prefetch_related('orders').all()
```

### Magic Number — Bad vs Good
```python
# BAD
if status == 3:
    ...

# GOOD
ORDER_STATUS_SHIPPED = 3
if status == ORDER_STATUS_SHIPPED:
    ...
```

### Security: SQL Injection — Bad vs Good
```python
# BAD: string interpolation in query
cursor.execute(f"SELECT * FROM users WHERE id = {user_id}")

# GOOD: parameterized query
cursor.execute("SELECT * FROM users WHERE id = %s", [user_id])
```

## Constraints

### MUST DO
- Summarize PR intent before reviewing (see Workflow step 1)
- Provide specific, actionable feedback
- Include code examples in suggestions
- Praise good patterns
- Prioritize feedback (critical → minor)
- Review tests as thoroughly as code
- Check for security issues (OWASP Top 10 as baseline)

### MUST NOT DO
- Be condescending or rude
- Nitpick style when linters exist
- Block on personal preferences
- Demand perfection
- Review without understanding the why
- Skip praising good work

## Output Template

Code review report must include:
1. **Summary** — One-sentence intent recap + overall assessment
2. **Critical issues** — Must fix before merge (bugs, security, data loss)
3. **Major issues** — Should fix (performance, design, maintainability)
4. **Minor issues** — Nice to have (naming, readability)
5. **Positive feedback** — Specific patterns done well
6. **Questions for author** — Clarifications needed
7. **Verdict** — Approve / Request Changes / Comment

## Decomposition des sous-taches

Au demarrage, decomposer toute review en sous-taches independantes (READ-ONLY -- aucune mutation) :

- [ ] Sous-tache 1 : identifier le perimetre exact (git diff, fichiers staged, changeset session)
- [ ] Sous-tache 2 : lecture + grep des fichiers modifies (correctness, securite, N+1)
- [ ] Sous-tache 3 : verification des anti-patterns LIA-SEC (Grid legacy, fetch brut, fontFamily, etc.)
- [ ] Sous-tache 4 : verification conformite R1-R24 (logs, CORS, envelope unwrap, UI help)
- [ ] Sous-tache 5 : redaction du rapport structure avec findings rated CRITICAL/HIGH/MEDIUM/LOW + file:line
- [ ] Sous-tache 6 : sauvegarde dans `_alire/02_LOGS/Journals/code_review/YYYY-MM-DD_{module}.md`

Sous-taches 2-4 parallelisables par fichier. Sous-tache 5 depend de 2-4.

## Plan d'execution

Pour toute review de PR / module complet (> 5 fichiers) :

1. Creer `_alire/tracking/PLAN_CODE_REVIEW_{MODULE}_{YYYY-MM-DD}.md` avant de lire le premier fichier.
2. Template : `_alire/tracking/PLAN_TEMPLATE.md`.
3. Cocher chaque fichier/domaine inspecte.
4. Si perimetre depasse en cours de review : Status -> REPLANIFIE + restreindre au changeset.

Pour une review ponctuelle (1-2 fichiers) : plan inline suffit.

## Adaptation et replanification

Si 2 fichiers consecutifs produisent des findings contradictoires ou si le scope derive :

- STOP
- Invoquer `/replan` -> restreindre au changeset initial ou clarifier le perimetre
- NE PAS etendre la review a tout le repo en improvisant

Declencheurs typiques :
- Finding contredit le pattern etabli dans un autre fichier -> REPLAN (verifier le pattern)
- Scope creep (begin reviewing unmodified files) -> REPLAN -> restriction
- Finding "Critical" implique un audit securite complet -> deleguer a `/security-reviewer`

## Outils declares

| Outil | Usage | Retry policy |
|-------|-------|--------------|
| `Read` | Lire un fichier du changeset (chemin exact) | N/A |
| `Grep` | Rechercher un pattern dans les fichiers modifies | N/A |
| `Glob` | Cartographier les fichiers du changeset | N/A |
| `Bash git diff` | Obtenir le diff staged/unstaged pour borner le scope | N/A |
| `Skill(go-recette)` | SAST Go apres review manuelle si code Go modifie | Obligatoire si .go |
| `Skill(react-recette)` | SAST React apres review manuelle si .tsx modifie | Obligatoire si .tsx |
| `Skill(security-reviewer)` | Deep-dive CVSS si finding auth/jwt/injection detecte | Obligatoire si Critical |

INTERDIT : `Write`, `Edit`, `Bash` non-lecture. Cette skill est READ-ONLY. Aucune mutation de code.

Selection dynamique : outil choisi selon le type de fichier (Go vs TSX vs SQL vs YAML).

## Tracabilite agentique

Logger dans `_alire/02_LOGS/Journals/decision_log.jsonl` chaque decision non triviale :

- Choix de scope (pourquoi tel fichier inclus / exclu)
- Findings ambigus (faux positif probable vs reel) + justification
- Delegation a `/security-reviewer` ou `/go-recette` + raison

Format :
```json
{"timestamp":"...","session":"code-reviewer-{module}","action":"...","reasoning":"...","alternatives_rejected":["..."],"outcome":"...","confidence":"high","plan_ref":"PLAN_CODE_REVIEW_*.md"}
```

RETEX en fin de session si score agentique < 40/50 -> `_alire/02_LOGS/Journals/retex/RETEX_CODE_REVIEW_YYYY-MM-DD.md`.

## VERIFICATION GATE (COMPLETUDE DE REVIEW)

Avant de declarer la review terminee :

- [ ] Chaque fichier du changeset a ete inspecte (pas de fichier omis silencieusement)
- [ ] Chaque finding a un niveau de severite (CRITICAL / HIGH / MEDIUM / LOW) + file:line ref
- [ ] Anti-patterns LIA-SEC verifies (Grid v6 legacy, fetch brut, hardcoded URL, fontFamily, envelope unwrap)
- [ ] R1-R24 verifies sur le changeset (logs, CORS, R17 fixture, R10 no emoji, R12 comments anglais)
- [ ] Rapport sauvegarde dans `_alire/02_LOGS/Journals/code_review/YYYY-MM-DD_{module}.md`
- [ ] Verdict explicite : Approve / Request Changes / Comment

Si un gate est incomplet : continuer la review, ne pas declarer "done".

## Scoring agentique

| Critere | Score |
|---------|-------|
| C1 Decomposition : sous-taches identifiees + perimetre borne ? | /10 |
| C2 Planification : PLAN_*.md cree et suivi ? | /10 |
| C3 Replanification : /replan declenche sur scope-creep ou contradiction ? | /10 |
| C4 Outillage : Read/Grep/Glob + skills SAST deleguees selon type fichier ? | /10 |
| C5 Tracabilite : decision_log + rapport code_review + RETEX produits ? | /10 |

Score total /50 -- >= 40 : Exemplaire | 30-39 : Acceptable | < 30 : RETEX obligatoire

## Knowledge Reference

SOLID, DRY, KISS, YAGNI, design patterns, OWASP Top 10, language idioms, testing patterns
