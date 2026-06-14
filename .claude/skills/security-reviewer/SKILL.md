---
name: security-reviewer
description: Adversarial security reviewer for LIA-SEC -- consolidates /go-recette + /react-recette findings, adds manual review (auth, input handling, crypto, race conditions, business logic), produces CVSS-rated report with file:line references and concrete remediation. Invoke in /audit-pdca Phase CHECK (C.1bis) as the security domain deep-dive, before /apex merges a risky feature, on user request for "security audit", or when gosec/govulncheck raise a HIGH finding that needs context. Does NOT replace /go-recette or /react-recette -- it augments them with adversarial reasoning and structured reporting.
license: MIT (upstream Jeffallan/claude-skills) -- adapted for LIA-SEC
allowed-tools: Read, Grep, Glob, Bash
metadata:
  author: mo0ogly@proton.me
  upstream: https://github.com/Jeffallan/claude-skills/tree/main/skills/security-reviewer
  version: "2.0.0-lia"
  domain: security
  triggers: security review, security audit, pentest, review securite, audit securite, CVSS rating, find vulns, exploitability, adversarial review, risky feature review, pre-merge security
  role: specialist
  scope: review + report
  output-format: CVSS-scored findings table + remediation
  related-skills: secure-code-guardian, go-recette, react-recette, apex, audit-pdca
  enforces-rules: R1, R5, R6, R7, R8, R10, R12, R17, R18
---

# Security Reviewer (LIA-SEC adaptation)

> **Complement** -- ne remplace PAS :
> - `secure-code-guardian` (préventif, AVANT écriture)
> - `/go-recette` (gosec + govulncheck + OWASP Go)
> - `/react-recette` (OWASP React + Vercel best practices)
> - `security-review` (check PR rapide)
>
> **Ce skill** = reviewer adversarial POST-scan : consolide les findings SAST
> + ajoute revue manuelle (auth, business logic, race conditions, crypto) +
> produit un rapport CVSS-rated exploitable en PDCA ou PR.

---

## 0. Stack LIA-SEC -- outils et conventions

| Domaine | Outil | Commande |
|---------|-------|----------|
| Go SAST | gosec | `cd cmd/sigma_web && gosec -fmt=json ./...` |
| Go vuln deps | govulncheck | `cd cmd/sigma_web && govulncheck ./...` |
| Go lint | `/go-recette` BLOC B+D | via Skill tool |
| React/TS SAST | `/react-recette` BLOC B (eslint-plugin-security + semgrep) | via Skill tool |
| React vuln deps | npm audit | `cd sigma-react-frontend && npm audit --production --audit-level=high` |
| Secrets scan | gitleaks | `gitleaks detect --source=. --redact --no-banner` |
| Hook Write | `security_check.sh` | automatique sur .go/.ts/.py |
| Filesystem vuln | trivy | `trivy fs --severity HIGH,CRITICAL .` |
| Docker image | trivy image | (si Dockerfile present) |
| DB SQL check | `.claude/rules/enforcement-backend.md` whitelist patterns | grep manuel |

**Ne JAMAIS** lancer :
- `bandit` (on n'a pas de Python en prod)
- `npm audit fix --force` (R1 -- modif masse sans accord)
- tests actifs sur `inspect-ia-agents.tech` (prod, ROE explicite requise)
- `go build ./...` ou `go test ./...` (R16 -- utiliser `build_secure_lia.sh`)

---

## 1. Avant de reviewer -- lecture obligatoire

| Source de verite | Chemin | Pourquoi |
|------------------|--------|----------|
| Règles sécurité projet | `.claude/rules/enforcement-backend.md` + `enforcement-frontend.md` | Whitelist SQL, CORS, JWT, SSRF |
| R7 SQL Injection | `cmd/sigma_web/CLAUDE.md` section 7 | Patterns autorisés/interdits |
| R8 Hardcoded secrets | `.claude/rules/no-hardcoded-secrets.md` | `LIA_DB_PASS` / helper pattern |
| R17 Frontend Contract Gate | `.claude/rules/frontend-contract-gate.md` | Fixture + render-assert |
| R22 AI call pattern | `.claude/rules/ai-call-pattern.md` | `ExecuteWithRAG` canonique |
| Auth JWT middleware | `cmd/sigma_web/auth_session_middleware.go` | `publicRoutes` whitelist |
| Rate limiter | `cmd/sigma_web/rate_limiter.go` | 60 req/min/IP |
| Audit log API | `cmd/sigma_web/security_audit_db.go` | `LogSecurityAuditEvent()` |

Si une règle est absente ou contredite par le code -> arrêter, corriger la doc (R18), puis reviewer.

---

## 2. Workflow agentique (7 phases)

```
[1] SCOPE
    - Cibles exactes (fichiers, routes, migrations, composants React)
    - Confirmer que la prod (inspect-ia-agents.tech) est HORS scope (sauf ROE signée)
    - Identifier publicRoutes vs routes JWT-protected
    - Lister les entrées utilisateur (req.Body, query params, headers, form files)

[2] AUTOMATED SCAN (parallèle)
    - gosec + govulncheck   -> JSON report
    - /go-recette BLOC B+D  -> script report
    - /react-recette BLOC B -> script report
    - npm audit --production -> vulns deps React
    - gitleaks detect       -> secrets leakes
    - trivy fs              -> lib vulns + IaC
    - grep manuel patterns LIA-SEC (voir section 4)

[3] TRIAGE
    - Dedup (gosec + /go-recette peuvent remonter le meme pattern)
    - Noise filtering (false positives, generator files, _test.go)
    - Severity prior (CVSS 3.1) : Critical >= 9.0, High 7-8.9, Medium 4-6.9, Low 0.1-3.9, Info 0
    - Exploitability check : reachable code ? user input path ? auth requis ?

[4] MANUAL REVIEW (SAST ne voit pas)
    - Auth : JWT middleware applique ? publicRoutes minimale et justifiee ?
    - AuthZ : role check apres auth ? IDOR ? tenant isolation ?
    - Input validation : whitelist vs blacklist ? regex anchors (^$) ?
    - Error handling : pas de stack trace leak dans response ?
    - Business logic : race conditions, TOCTOU, replay, negative values, int overflow
    - Crypto : bcrypt cost >= 10, JWT secret rotation, HTTPS enforce
    - File handling : path traversal (filepath.Clean), size limits, MIME check
    - AI endpoints : prompt injection ? rag_documents isolation tenant ?
    - CORS : allowlist origins, pas de wildcard sur endpoints auth
    - Logging : pas de PII/secret dans unified_logs, pas d'emoji (R10)

[5] PROOF-OF-CONCEPT (optionnel, scope ROE)
    - Curl local avec payload malveillant -> 400/403 attendu
    - Render-assert frontend avec fixture manipulee (R17)
    - Jamais sur inspect-ia-agents.tech sans autorisation ecrite

[6] CVSS RATING
    - Vector CVSS 3.1 complet pour chaque finding HIGH/CRITICAL
    - AV (Attack Vector), AC, PR, UI, S, C, I, A
    - Justifier le score (pas de "8.1 parce que SQL")

[7] REPORT
    - Executive summary + findings table + details par finding
    - Sauvegarder dans _alire/02_LOGS/Journals/security_audit/YYYY-MM-DD_review.md
    - LogSystemEvent("INFO", "SECURITY_REVIEW", "COMPLETED", "N findings") via psql
    - Librarian Gate : commit plan + report dans le meme commit
```

---

## 3. Reference Guide -- charger selon le contexte

| Topic | Reference | Charger quand |
|-------|-----------|---------------|
| SAST tools playbook | `references/sast-tools.md` | Choix d'outils, integration CI |
| Vulnerability patterns | `references/vulnerability-patterns.md` | Review manuelle OWASP Top 10, patterns commun |
| Secret scanning | `references/secret-scanning.md` | gitleaks / trufflehog config, faux positifs |
| Penetration testing | `references/penetration-testing.md` | Scope ROE, outils (nmap, burp, sqlmap) |
| Infrastructure security | `references/infrastructure-security.md` | IaC, Docker, nginx, PostgreSQL hardening |
| Report template | `references/report-template.md` | Format livrable final |

> Les references upstream contiennent du Python (bandit) et des outils non-LIA
> (Burp, sqlmap). **Ne pas executer** ces commandes brutes : les transposer
> en equivalents Go/React (voir section 0).

---

## 4. Grep patterns specifiques LIA-SEC (manual review)

### 4.1 Anti-patterns Go

```bash
# R7 SQL Injection
grep -rn 'fmt\.Sprintf.*SELECT\|fmt\.Sprintf.*INSERT\|fmt\.Sprintf.*UPDATE\|fmt\.Sprintf.*DELETE' cmd/sigma_web/ --include='*.go' | grep -v _test.go

# R7 exec.Command user input
grep -rn 'exec\.Command.*request\|exec\.Command.*r\.URL\|exec\.Command.*input' cmd/sigma_web/

# R8 Hardcoded secrets
grep -rnE '(api_key|password|secret|token)\s*[:=]\s*"[A-Za-z0-9+/]{16,}"' cmd/sigma_web/ --include='*.go'

# R6 fmt.Println dans le code metier
grep -rn 'fmt\.Println\|log\.Printf' cmd/sigma_web/ --include='*.go' | grep -v 'backend_8081.go\|app_config\|campaign_comparison_api.go'

# CORS wildcard sur endpoints auth
grep -rn 'Access-Control-Allow-Origin.*\*' cmd/sigma_web/ | grep -iE '(auth|login|admin)'

# AuthN bypass -- route non couverte par middleware
grep -rn 'HandleFunc.*"/api/' cmd/sigma_web/ | awk '{print $1}' | sort -u  # comparer a publicRoutes

# R22 BYPASS (16 sites connus au 2026-04-18)
grep -rn 'manager\.CallAI\|callGrcAI(\|callSmsiAIWithFallback(' cmd/sigma_web/ --include='*.go' | grep -v _test.go
```

### 4.2 Anti-patterns React/TS

```bash
# XSS dangerouslySetInnerHTML sans DOMPurify
grep -rn 'dangerouslySetInnerHTML' sigma-react-frontend/src/ --include='*.tsx' | grep -v 'DOMPurify.sanitize'

# R17 fetch brut (viole JWT middleware)
grep -rn 'await fetch(' sigma-react-frontend/src/components sigma-react-frontend/src/services --include='*.ts*' | grep -v fetchWithConfig

# ConfigurationService bypass (hardcode URL)
grep -rn "http://localhost\|http://127\." sigma-react-frontend/src/ --include='*.ts*'

# console.log production
grep -rn 'console\.log(' sigma-react-frontend/src/ --include='*.ts*' | grep -v customLogger

# Hardcoded API key / token frontend
grep -rnE '(api[_-]?key|token|secret)\s*=\s*["'\''][A-Za-z0-9]{16,}' sigma-react-frontend/src/ --include='*.ts*'
```

### 4.3 Secrets et credentials

```bash
# Secrets en clair dans le repo (commit history inclus)
gitleaks detect --source=. --redact --no-banner

# .env files committes
git ls-files | grep -E '\.env$|\.env\.'

# .claude/settings.local.json leake
git ls-files | grep settings.local.json
```

### 4.4 Config PostgreSQL

```bash
# Passwords en dur dans migrations ou .sql
grep -rnE "password.*=.*'[^']+'" cmd/sigma_web/postgres/migrations/

# DATABASE_URL hardcode
grep -rn "postgresql://.*:.*@" /opt/lia-sec/dev/ --include='*.go' --include='*.sh' --include='*.ts*' | grep -v '\$\|env'
```

---

## 5. CVSS scoring -- cheat sheet LIA-SEC

| Vulnerabilite typique | AV/AC/PR/UI/S/C/I/A | Score | Criticite |
|-----------------------|---------------------|-------|-----------|
| SQL injection handler admin authentifie | N/L/H/N/U/H/H/H | 7.2 | High |
| SQL injection route publique | N/L/N/N/U/H/H/H | 9.8 | Critical |
| Path traversal lecture fichier auth | N/L/L/N/U/H/N/N | 6.5 | Medium |
| XSS stocke sur page dashboard | N/L/L/R/U/L/L/N | 5.4 | Medium |
| IDOR sur endpoint compliance | N/L/L/N/U/H/N/N | 6.5 | Medium |
| Broken auth -- JWT faiblement signe | N/L/N/N/U/H/H/N | 9.1 | Critical |
| Secret commite dans git history | N/L/N/N/U/H/H/N | 9.1 | Critical (si non rotate) |
| Missing rate limiter sur login | N/L/N/N/U/L/N/A | 6.5 | Medium |
| CORS wildcard sur auth endpoint | N/L/L/N/U/H/H/N | 8.1 | High |
| Prompt injection sans sanitization | N/L/L/N/U/L/L/N | 5.4 | Medium |

Toujours inclure le vector CVSS 3.1 complet (`CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H`).

---

## 6. Integration PDCA -- Phase CHECK C.1bis

Declencher `/security-reviewer` en Phase CHECK du cycle `/audit-pdca`, apres le STATIC
(`/go-recette` + `/react-recette`) et avant le RUNTIME, pour le **domaine security**
du SCORING_CONFIG (20% du score /100).

### Entree

- Reports `/go-recette` et `/react-recette` en JSON
- Liste des fichiers touches par le cycle (diff vs cycle N-1)
- Contexte cycle : mode (fix/score-only), target score, domaines actifs

### Sortie

- `_alire/02_LOGS/Journals/security_audit/YYYY-MM-DD_cycle-N_review.md`
- Update `SCORING_CONFIG.json` : ajuster checks SEC-01..10 si necessaire
- Ajouter findings Critical/High dans `swarm_memory.json` > `discoveries[]`
- Retourner verdict : `COMPLETE` | `PARTIAL` (Critical trouves, PDCA doit REPLAN) | `FAILURE`

### Regle de gating

- 1+ finding Critical non fix -> cycle **FAILURE**, REPLAN obligatoire
- 3+ finding High non fix -> cycle **PARTIAL**, target_score -= 15
- 0 Critical, <= 2 High -> cycle peut continuer en C.2 RUNTIME

---

## 7. Integration APEX -- Phase 4 RECETTE

Declencher `/security-reviewer` en Phase 4 RECETTE de `/apex`, en plus des 4 etapes
existantes (STATIC / RUNTIME / CONTRACT / REGRESSION), quand le flag `-x / --examine`
est actif OU quand le cycle touche :

- `auth_*`, `jwt_*`, `session_*`, `middleware_*` (authN/authZ)
- Un nouveau handler `/api/*` en route publique
- Une migration SQL avec GRANT / ALTER USER / CREATE ROLE
- Un composant frontend avec `dangerouslySetInnerHTML`
- Un nouvel appel `exec.Command` ou `os/exec`
- Une lecture/ecriture de fichier avec chemin user-controlled

Verdict FAILURE -> retour Phase 3 BUILD + REPLAN.

---

## 8. Output template -- rapport final

```markdown
# Security Review : <scope> -- YYYY-MM-DD

## Executive Summary
- Scope : <files/routes/migrations>
- Methodology : SAST (gosec + govulncheck + eslint-security + semgrep) + Manual Review + Grep patterns
- Duration : N minutes
- Findings : X Critical, Y High, Z Medium, W Low, V Info
- Recommendation : ACCEPT | ACCEPT WITH FIX | REJECT (details infra)

## Findings Table

| ID | Severity | CVSS | Title | File:Line |
|----|----------|------|-------|-----------|
| SEC-001 | Critical | 9.8 | SQL injection public route | cmd/sigma_web/foo_api.go:42 |
| SEC-002 | High | 8.1 | CORS wildcard on auth endpoint | cmd/sigma_web/cors_utils.go:18 |
| ... | | | | |

## Detailed Findings

### SEC-001 -- Critical (CVSS 9.8)
**Vector**: `CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:U/C:H/I:H/A:H`
**File**: `cmd/sigma_web/foo_api.go:42`
**Description**: User-supplied `name` parameter concatenated into SQL query without parameterization. Route `/api/foo/search` is in `publicRoutes` (no JWT required).
**Impact**: Unauthenticated attacker reads/modifies/deletes database. Tenant isolation bypass possible.
**Remediation**:
```go
// AVANT (vulnerable)
query := fmt.Sprintf("SELECT * FROM foo WHERE name='%s'", name)

// APRES (secure)
query := "SELECT * FROM foo WHERE name = $1"
rows, err := db.Query(query, name)
```
**Validation**: `curl "http://localhost:8081/api/foo/search?name=';DROP TABLE foo;--"` -> doit retourner 400 ou 0 row.
**References**: CWE-89, OWASP A03:2021, R7 enforcement-backend.md

### SEC-002 -- High (CVSS 8.1)
...

## Prioritized Action Plan
1. **Immediate (before next merge)** : fix SEC-001, SEC-003
2. **Short term (this sprint)** : SEC-002, SEC-004
3. **Medium term** : SEC-005, SEC-006

## Compliance Mapping
- OWASP Top 10 2021 : A01 (x), A03 (1), A05 (0), A07 (0)
- CWE : CWE-89, CWE-352, CWE-798
- ANSSI : (si applicable)
- ISO 27001 A.12.2, A.14.2 (si applicable)

## Cross-references
- Plan : _alire/tracking/PLAN_SEC_REVIEW_YYYY-MM-DD.md
- PDCA cycle : (si applicable)
- Rules enforced : R5, R7, R8, R10, R17, R22
```

---

## 9. Librarian Gate (obligatoire fin de session)

```
[ ] Report ecrit _alire/02_LOGS/Journals/security_audit/YYYY-MM-DD_*.md
[ ] Plan _alire/tracking/PLAN_SEC_REVIEW_*.md ajoute a INDEX.md
[ ] RETEX _alire/02_LOGS/Journals/retex/RETEX_SEC_REVIEW_*.md si cycle PDCA
[ ] decision_log.jsonl : 1 entree par finding Critical/High
[ ] Findings Critical consignes dans `unified_logs` via LogSystemEvent
[ ] Commit unique : report + plan + findings + fixes (si --fix)
[ ] Push (max 5 commits non pushes, R1)
```

---

## 10. Anti-patterns (refus immediat)

| INTERDIT | A la place |
|----------|-----------|
| Tester exploit sur `inspect-ia-agents.tech` sans ROE signee | Local (`http://localhost:8081`) uniquement |
| `npm audit fix --force` | Lister vulns, proposer upgrade, attendre accord utilisateur (R1) |
| Publier exploit detaille | Fournir PoC minimal + remediation, pas weaponise |
| Reviewer sans lancer les outils automatiques d'abord | 2 heures de manual review sans gosec = 10 minutes de manual review avec gosec (signal/bruit) |
| Considerer un finding "Low" comme ignorable | Low peut etre Critical en chaine (ex: info disclosure + path traversal = RCE) |
| Truster framework ("Gorilla Mux gere ca") | Verifier par curl / tests (R18) |
| Cacher un finding parce que le code n'est pas a nous | Le committer = c'est a nous. Noter la dette, lever un ticket |
| Proposer upgrade Go 1.25 -> 1.25.1 sans verifier release officielle | R19 fetch latest from https://go.dev/dl/ |

---

## 11. Score agentique attendu (>= 40/50)

| Critere | Min | Comment l'atteindre |
|---------|-----|---------------------|
| C1 Decomposition | 8/10 | Workflow 7 phases respecte, sous-taches par domaine |
| C2 Planification (THINK) | 9/10 | Scope ecrit AVANT scan, ROE confirmee |
| C3 Replanification | 8/10 | REPLAN sur Critical non mitigable + 2+ alternatives (patch / workaround / config) |
| C4 Outillage | 8/10 | gosec/govulncheck/gitleaks/trivy AVANT grep manuel |
| C5 Tracabilite | 8/10 | Report + plan + decision_log + RETEX + Librarian Gate |
