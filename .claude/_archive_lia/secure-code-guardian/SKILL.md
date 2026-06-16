---
name: secure-code-guardian
description: Use when implementing or reviewing authentication/authorization, securing user input, or preventing OWASP Top 10 vulnerabilities in LIA-SEC code -- bcrypt/argon2 hashing, parameterized SQL queries (pgx / database/sql), CORS/CSP headers, Zod / Go validator, JWT middleware, rate limiting, session management. Adapted to LIA-SEC stack (Go backend + React/TS + PostgreSQL) and existing conventions (LogSecurityAuditEvent, rate_limiter.go, auth_session_middleware.go, system_variables, fetchWithConfig). For standalone audits use /go-recette or /react-recette; for CVE-driven fixes use /create-lia-rule.
license: MIT (upstream), adapted for LIA-SEC
metadata:
  author: https://github.com/Jeffallan (upstream), LIA-SEC adaptation by mo0ogly
  version: "1.1.0-liasec"
  domain: security
  triggers: security, authentication, authorization, encryption, OWASP, vulnerability, secure coding, password, bcrypt, JWT, OAuth, CORS, CSP, rate limit, SQL injection, XSS, CSRF, JWT middleware, session fixation
  role: specialist
  scope: implementation
  output-format: code
  related-skills: go-recette, react-recette, debug-go, debug-react, create-lia-rule, golang-pro, react-expert
---

# Secure Code Guardian (LIA-SEC Edition)

Senior security engineer specialised in OWASP Top 10 prevention for the LIA-SEC
stack: Go 1.25.1 backend (`cmd/sigma_web/`, 560+ routes), React 19 / TS 4.9
frontend (`sigma-react-frontend/`), PostgreSQL 17 (268 tables).

## When to Use This Skill

- Writing or reviewing any authentication / authorization code
- Touching `auth_session_middleware.go`, `auth_jwt.go`, `auth_addon.go`
- Adding a new API endpoint that handles user input (body / query / path)
- Adding a new React form / upload / search input
- Configuring CORS, CSP, HSTS, rate limiting, security headers
- Any change to `rate_limiter.go`, nginx config, systemd env vars
- Password reset / credential rotation workflows (see `admin-tool-pwreset.md`)
- Reviewing a PR for OWASP Top 10 compliance
- Hardening an endpoint that returns sensitive data (CVE, compliance, secrets)

## When NOT to Use This Skill

- CVE rule creation -> `/create-lia-rule`
- Pure static audit / scan -> `/go-recette` or `/react-recette`
- Debugging a runtime auth failure -> `/debug-go` or `/debug-react`
- Writing a new Go package scaffold -> `/golang-pro` (invoke `/secure-code-guardian`
  AFTER the package exists if it handles sensitive data)
- Writing a new React component scaffold -> `/react-expert` (invoke this skill
  AFTER for auth / input validation hardening)

## Core Workflow

1. **Threat model** -- identify attack surface, threats, trust boundaries
2. **Design** -- plan security controls (defense in depth, fail closed)
3. **Implement** -- write secure code, NEVER trust input, ALWAYS log security events
4. **Validate** -- run the checkpoints below
5. **Audit trail** -- log with `logSecurityAuditEvent()` (not just LogSystemEvent)
6. **Document** -- record decisions in `_alire/01_DOCUMENTATION/security/`
   (R15 naming: `{module}_sec_en.md`)

### Validation Checkpoints (after each step)

- **Authentication**: test brute-force protection triggers, session-fixation
  resistance, token expiration, `Invalid credentials` generic message (no user
  enumeration via error text OR via response time).
- **Authorization**: verify horizontal (user A -> user B data) AND vertical
  (user -> admin) escalation paths are blocked. Test with JWTs of different
  roles.
- **Input**: confirm `' OR 1=1--`, `<script>alert(1)</script>`,
  `../../../etc/passwd`, `$(whoami)` are rejected / escaped / parameterized.
- **Headers/CORS**: `curl -I https://inspect-ia-agents.tech/` must show CSP, HSTS,
  X-Frame-Options, X-Content-Type-Options; CORS must NOT be `*` on authenticated
  endpoints (see `setCORSHeaders`).
- **Rate limiting**: hit `/api/auth/login` 60+ times/min from same IP -> 429
  expected (see `rate_limiter.go`).

## Decomposition des sous-taches

Au demarrage, decomposer toute demande en sous-taches independantes :

- [ ] Sous-tache 1 : reads / greps pour cartographier la surface d'attaque (handlers, middleware, auth flows, inputs)
- [ ] Sous-tache 2 : threat model rapide (qui attaque, quel vecteur, quelles donnees exposees)
- [ ] Sous-tache 3 : implementation des controles securite (auth, input validation, CORS, rate limit, headers)
- [ ] Sous-tache 4 : tests adversariaux (curl, brute-force sim, injection payloads, role escalation)
- [ ] Sous-tache 5 : `gosec` + verification checklist OWASP Top 10 sur les fichiers modifies
- [ ] Sous-tache 6 : `logSecurityAuditEvent()` sur toutes les branches auth/privilege + doc securite

Utiliser `TaskCreate` pour tracker si > 3 sous-taches.

## Plan d'execution

Pour tout hardening non trivial (nouveau handler auth, refactor middleware, changement JWT) :

1. Creer `_alire/tracking/PLAN_SECURE_GUARDIAN_{FEATURE}_{YYYY-MM-DD}.md` avant d'ecrire une ligne.
2. Template : `_alire/tracking/PLAN_TEMPLATE.md`.
3. Cocher chaque sous-tache a la completion.
4. Si replanification : Status -> REPLANIFIE + lien vers nouveau plan.

Pour un fix ponctuel (1 endpoint, 1 header manquant) : plan inline suffit.

## Adaptation et replanification

Si 2 etapes consecutives echouent (ex: `gosec` trouve un nouveau finding apres fix, ou un test adversarial passe encore) :

- STOP
- Invoquer `/replan` -> produit `PLAN_SECURE_GUARDIAN_*_REPLAN_*.md`
- NE PAS improviser un contournement

Declencheurs typiques :
- Fix d'un finding `gosec` introduit un autre finding de classe differente -> REPLAN
- Test brute-force passe encore apres ajout rate limit -> REPLAN (verifier IP extraction, token bucket)
- Parameterization ajoutee mais injection possible via path/header non valide -> REPLAN
- Nouveau endpoint en `publicRoutes` sans justification documentee -> REPLAN (R5 authz review)

## Outils declares

| Outil | Usage | Retry policy |
|-------|-------|--------------|
| `Read`, `Grep`, `Glob` | Cartographier handlers, middleware, `publicRoutes`, `auth_session_middleware.go` | N/A |
| `Write`, `Edit` | Implementer controles securite dans `.go` / `.tsx` | N/A |
| `Bash gosec ./...` | SAST Go -- trouver CWE-89 (injection), CWE-798 (hardcode), CWE-276 (permissions) | 1 retry si faux positif documente |
| `Bash curl` | Tests adversariaux (injection, brute-force, escalation de role, CORS misconfiguration) | N/A |
| `TaskCreate` | Tracking si > 3 sous-taches | N/A |
| `Skill(go-recette)` | Audit SAST complet post-implementation (41 checks) | Obligatoire avant commit |
| `Skill(react-recette)` | Audit OWASP frontend (dangerouslySetInnerHTML, fetch brut, XSS) | Obligatoire si composant React touche |
| `Skill(security-reviewer)` | Review CVSS consolidee si auth/JWT/middleware touche | Obligatoire si trigger C.1bis |

Selection dynamique : `gosec` apres chaque modification `.go`, `curl` adversarial apres implementation, skills invoquees selon perimetre.

## Tracabilite agentique

Logger dans `_alire/02_LOGS/Journals/decision_log.jsonl` chaque decision non triviale :

- Choix de controle securite (bcrypt cost 10 vs 12, JWT TTL, rate limit threshold)
- Rejet d'une approche (ex: CSP `unsafe-inline` rejete, alternative trouvee)
- Decisions de `publicRoutes` (pourquoi un endpoint est exempte JWT)
- Trade-offs (securite vs perf, strictness vs UX)

Format :
```json
{"timestamp":"...","session":"secure-guardian-{feature}","action":"...","reasoning":"...","alternatives_rejected":["..."],"outcome":"...","confidence":"high","plan_ref":"PLAN_SECURE_GUARDIAN_*.md"}
```

RETEX en fin de session si score agentique < 40/50 -> `_alire/02_LOGS/Journals/retex/RETEX_SECURE_GUARDIAN_YYYY-MM-DD.md`.

## Reference Guide

Load detailed guidance based on context:

| Topic | Reference | Load When |
|-------|-----------|-----------|
| OWASP Top 10 | `references/owasp-prevention.md` | Broad secure-coding patterns |
| Authentication | `references/authentication.md` | Password hashing, JWT, MFA |
| Input Validation | `references/input-validation.md` | Zod, Go validator, SQL injection |
| XSS/CSRF | `references/xss-csrf.md` | React rendering, CSRF tokens |
| Headers | `references/security-headers.md` | CSP, HSTS, CORS, rate limiting |

LIA-SEC companion docs:
- `.claude/rules/no-hardcoded-secrets.md` (env vars + system_variables)
- `.claude/rules/backend-single-instance.md` (R16)
- `.claude/rules/enforcement-backend.md` (SQL injection audit status, CORS)
- `.claude/rules/admin-tool-pwreset.md` (emergency password reset workflow)
- `_alire/01_DOCUMENTATION/dev/OWASP_PREVENTION_PATTERNS.md` (canonical patterns)

## LIA-SEC Security Primitives (use these, do NOT reinvent)

### Backend Go

| Primitive | File | Purpose |
|-----------|------|---------|
| `setCORSHeaders(w)` | `cmd/sigma_web/cors.go` | MANDATORY at every handler start; sets CORS headers once (no duplicates) |
| `AuthMiddleware` | `cmd/sigma_web/auth_session_middleware.go` | JWT Bearer validation; DENY by default. `publicRoutes` is the ONLY allowlist |
| `AdminAuditMiddleware` | same | Wraps admin endpoints; logs every privileged action |
| `logSecurityAuditEvent(...)` | `cmd/sigma_web/security_audit_db.go` | Records auth events, privilege escalation, suspicious patterns (table `security_audit_events`) |
| `LogSystemEvent(level, component, action, details)` | `logger_api.go` | Non-security log path (R6); NEVER `fmt.Println` |
| `rate_limiter.go` | token bucket 60 req/min/IP on `/api/cve/*`, `/api/mitre/*` | Add to new endpoints that accept unauth traffic |
| `pwreset` CLI | `cmd/lia_admin_pwreset/` | Emergency password reset; uses `bcrypt.DefaultCost=10` to match login path |
| `ConfigurationService` (`system_variables` table) | `cmd/sigma_web/ai_config_db_postgres.go` etc. | Secrets / URLs / thresholds -- NEVER hardcode |

### Frontend React

| Primitive | File | Purpose |
|-----------|------|---------|
| `fetchWithConfig` | `src/config/apiConfig.ts` | Injects JWT Bearer, retry, timeout, baseUrl. NEVER use `fetch()` brut on protected endpoints |
| `getBackendUrl()` | `src/services/ConfigurationService.ts` | For download URLs / websockets that need the raw backend URL |
| `customLogger` | `src/services/loggerService.ts` | Client-side log, sent to backend (R6) |
| `AIMarkdownView` | `src/components/common/AIMarkdownView.tsx` | SAFE markdown rendering (strips `<script>`, `<think>`, HTML sanitized) |

### Infrastructure (VPS inspect-ia-agents.tech)

- TLS: Let's Encrypt, auto-renewal (certbot)
- Nginx: HTTPS only, HSTS 1y includeSubDomains, CSP (see nginx conf)
- ufw: ports 22 / 80 / 443 only
- fail2ban: SSH brute-force protection
- PostgreSQL 17: listen only on 127.0.0.1; auth via env var `DATABASE_URL`
  (`systemctl cat lia-backend | grep Environment`)
- Backups: cron 2h AM, 7-day retention, `/opt/lia-sec/backups/`

## Constraints

### MUST DO
- Hash passwords with **bcrypt cost >= 10** (match `auth_jwt.go` / `pwreset`)
- **Parameterized queries only** (`$1`, `$2` placeholders via `pgx` / `database/sql`)
- Validate user input at the boundary (body, query, path, headers)
- Rate-limit auth endpoints and public search endpoints (`rate_limiter.go`)
- Security headers at nginx + Helmet-equivalent at Go (see `setCORSHeaders`)
- Log security events via `logSecurityAuditEvent()` (not just LogSystemEvent)
- Store secrets in `system_variables` (R5) or env vars, NEVER hardcode
- Return generic error messages (`Invalid credentials`) -- no user enumeration
- Set cookies `httpOnly`, `secure`, `sameSite=strict` when applicable
- JWT: explicit `algorithms: ['HS256']` allowlist, `iss` + `aud` claims, short TTL
- Token in `Authorization: Bearer` header (existing LIA-SEC convention), NOT in query string

### MUST NOT DO
- Store passwords plaintext or reversible-encrypted
- Trust user input (body, query, headers, cookies, file uploads)
- Interpolate strings into SQL (`fmt.Sprintf("... WHERE id='%s'", id)`)
- Use `eval`, `exec.Command("sh", "-c", ...)` with user input
- Log secrets / full JWT / session IDs / passwords / PII in plaintext
- Use `MD5`, `SHA-1`, `DES`, `ECB` for passwords / sensitive data
- Hardcode API keys, URLs, DB passwords in source (R5, R14)
- Return `CORS: *` on authenticated endpoints
- Skip `OPTIONS` handling in CORS (returns 405 = misconfigured CORS)
- Skip hooks via `--no-verify` unless user explicitly authorizes (R1)

## Code Examples -- Adapted to LIA-SEC Stack

### Password Hashing (Go -- matches auth_jwt.go + pwreset)

```go
// cmd/sigma_web/auth_jwt.go pattern
import "golang.org/x/crypto/bcrypt"

const BcryptCost = 10 // matches DefaultCost; pwreset CLI uses the same

func HashPassword(plaintext string) (string, error) {
    if len(plaintext) < 12 || len(plaintext) > 128 {
        return "", errors.New("password length out of bounds")
    }
    h, err := bcrypt.GenerateFromPassword([]byte(plaintext), BcryptCost)
    if err != nil {
        return "", err
    }
    return string(h), nil
}

func VerifyPassword(plaintext, hash string) bool {
    return bcrypt.CompareHashAndPassword([]byte(hash), []byte(plaintext)) == nil
}
```

### Parameterized SQL (Go -- database/sql + pgx)

```go
// CORRECT -- positional parameters, NO interpolation
func GetUserByEmail(ctx context.Context, db *sql.DB, email string) (*User, error) {
    const q = `SELECT id, email, role, password_hash, status
               FROM users WHERE email = $1 AND deleted_at IS NULL`
    row := db.QueryRowContext(ctx, q, email)

    var u User
    if err := row.Scan(&u.ID, &u.Email, &u.Role, &u.PasswordHash, &u.Status); err != nil {
        if errors.Is(err, sql.ErrNoRows) {
            return nil, nil // caller must NOT reveal "user not found" (avoid enumeration)
        }
        return nil, err
    }
    return &u, nil
}

// FORBIDDEN -- direct interpolation = SQL injection
// query := fmt.Sprintf("SELECT * FROM users WHERE email = '%s'", email)
```

For ORDER BY / dynamic columns, use a **hardcoded whitelist map** (see audit
2026-03-17 in `enforcement-backend.md`, pattern A -- `isValidColumn()`).

### Input Validation (Go)

```go
import "regexp"

var emailRE = regexp.MustCompile(`^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$`)

type LoginRequest struct {
    Email    string `json:"email"`
    Password string `json:"password"`
}

func (r *LoginRequest) Validate() error {
    if len(r.Email) == 0 || len(r.Email) > 254 {
        return errors.New("invalid input")
    }
    if !emailRE.MatchString(r.Email) {
        return errors.New("invalid input")
    }
    if len(r.Password) < 12 || len(r.Password) > 128 {
        return errors.New("invalid input")
    }
    return nil
}
```

### JWT -- matches auth_session_middleware.go

```go
import "github.com/golang-jwt/jwt/v5"

func VerifyToken(tokenStr string) (*jwt.RegisteredClaims, error) {
    secret := os.Getenv("JWT_SECRET") // NEVER hardcode; read from systemd unit env
    if secret == "" {
        return nil, errors.New("JWT secret not configured")
    }

    claims := &jwt.RegisteredClaims{}
    token, err := jwt.ParseWithClaims(tokenStr, claims, func(t *jwt.Token) (interface{}, error) {
        // MANDATORY allowlist -- prevents alg=none and alg confusion attacks
        if t.Method.Alg() != jwt.SigningMethodHS256.Name {
            return nil, fmt.Errorf("unexpected signing method: %v", t.Method.Alg())
        }
        return []byte(secret), nil
    }, jwt.WithValidMethods([]string{"HS256"}),
       jwt.WithIssuer("lia-sec"),
       jwt.WithAudience("lia-sec"))

    if err != nil || !token.Valid {
        return nil, errors.New("invalid token")
    }
    return claims, nil
}
```

### Securing a Login Handler -- Full LIA-SEC Flow

```go
func handleLogin(w http.ResponseWriter, r *http.Request) {
    // 1. CORS + method (mandatory at every handler start)
    setCORSHeaders(w)
    if r.Method == "OPTIONS" {
        w.WriteHeader(http.StatusOK)
        return
    }
    if r.Method != "POST" {
        http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
        return
    }

    // 2. Rate limit (built-in for public endpoints)
    if !globalRateLimiter.Allow(clientIP(r)) {
        logSecurityAuditEvent(r, "AUTH_RATE_LIMIT", "login rate limit triggered", nil)
        http.Error(w, "too many requests", http.StatusTooManyRequests)
        return
    }

    // 3. Parse + validate
    var req LoginRequest
    if err := json.NewDecoder(io.LimitReader(r.Body, 10*1024)).Decode(&req); err != nil {
        http.Error(w, "invalid request", http.StatusBadRequest)
        return
    }
    if err := req.Validate(); err != nil {
        http.Error(w, "invalid request", http.StatusBadRequest)
        return
    }

    // 4. Authenticate (constant work even on miss to blunt timing side-channel)
    user, err := GetUserByEmail(r.Context(), db, req.Email)
    if err != nil {
        LogSystemEvent("ERROR", "AUTH", "DB_LOOKUP_FAILED", err.Error())
        http.Error(w, "internal error", http.StatusInternalServerError)
        return
    }
    var hash string
    if user != nil {
        hash = user.PasswordHash
    } else {
        hash = "$2a$10$invalidhashtokeepconstanttimeXXXXXXXXXXXXXXXXXXXXXXXX"
    }
    ok := VerifyPassword(req.Password, hash)
    if user == nil || !ok {
        logSecurityAuditEvent(r, "AUTH_FAIL", "invalid credentials", map[string]any{
            "email_hash": sha256hex(req.Email), // NEVER log the raw email/password
        })
        // Generic message -- no enumeration
        http.Error(w, "invalid credentials", http.StatusUnauthorized)
        return
    }

    // 5. Issue short-lived JWT
    token, err := issueToken(user.ID, user.Role, 15*time.Minute)
    if err != nil {
        LogSystemEvent("ERROR", "AUTH", "TOKEN_ISSUE_FAILED", err.Error())
        http.Error(w, "internal error", http.StatusInternalServerError)
        return
    }

    // 6. Audit success + return
    logSecurityAuditEvent(r, "AUTH_SUCCESS", "user logged in", map[string]any{
        "user_id": user.ID,
        "role":    user.Role,
    })
    w.Header().Set("Content-Type", "application/json")
    _ = json.NewEncoder(w).Encode(map[string]any{
        "success": true,
        "token":   token,
    })
}
```

### React -- Safe Input & Rendering

```tsx
import DOMPurify from 'dompurify';
import { fetchWithConfig } from '../config/apiConfig';
import { customLogger } from '../services/loggerService';

// CORRECT -- React escapes by default when using {value}
<Typography>{user.name}</Typography>

// CORRECT -- when you MUST render HTML (e.g. AI markdown), sanitize first
// Prefer <AIMarkdownView> which wraps this pattern
const safe = DOMPurify.sanitize(rawHtml, { USE_PROFILES: { html: true } });
<div dangerouslySetInnerHTML={{ __html: safe }} />

// FORBIDDEN
<div dangerouslySetInnerHTML={{ __html: userInput }} />  // XSS

// Calls go through fetchWithConfig -- never raw fetch on auth endpoints
const resp = await fetchWithConfig('/api/ai/models');
const body = await resp.json();
if (!body.success) {
  customLogger.warn('AI_STATUS', 'API rejected', { error: body.error });
  throw new Error('Request failed');
}
```

### Nginx / Security Headers (reference only -- deploy via ansible/manual)

```
# /etc/nginx/sites-enabled/lia-sec
add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
add_header X-Content-Type-Options "nosniff" always;
add_header X-Frame-Options "DENY" always;
add_header Referrer-Policy "strict-origin-when-cross-origin" always;
add_header Content-Security-Policy "default-src 'self'; script-src 'self' 'wasm-unsafe-eval'; style-src 'self' 'unsafe-inline'; img-src 'self' data: https:; connect-src 'self' wss:; frame-ancestors 'none';" always;

# Rate limit login specifically
limit_req_zone $binary_remote_addr zone=login:10m rate=30r/m;
location /api/auth/login { limit_req zone=login burst=10 nodelay; proxy_pass http://127.0.0.1:8081; }
```

Every nginx change MUST be documented in
`_alire/01_DOCUMENTATION/user-guides/vps_deployment_guide_user_en.md` (R14)
BEFORE execution.

## Output Templates

When implementing a security feature, provide:
1. Secure implementation code (Go or TSX) following LIA-SEC primitives
2. Matching unit/integration test demonstrating the control blocks the attack
3. `logSecurityAuditEvent()` calls on every auth / privilege branch
4. Config requirements (env var name, `system_variables` row to add, nginx diff)
5. Testing recommendations (curl commands for boundary cases)
6. Doc update in `_alire/01_DOCUMENTATION/security/` (R15 + R20)
7. `Evolutions possibles` block (BLOC 9)

## VERIFICATION GATE (BLOQUANT)

Apres execution, AVANT de declarer termine :

- [ ] `gosec ./cmd/sigma_web/...` (depuis `cmd/sigma_web/`) -- zero HIGH non documente
- [ ] Checklist OWASP Top 10 validee (injection, broken auth, XSS, CSRF, misconfiguration, secrets)
- [ ] Aucun secret hardcode (`grep -rn 'password\s*=' cmd/sigma_web/*.go` -- zero hit non-parameterize)
- [ ] `setCORSHeaders(w)` + `OPTIONS` handler present en premiere ligne de tout nouveau handler
- [ ] `logSecurityAuditEvent()` appele sur chaque branche auth success/fail et privilege change
- [ ] Rate limit verifie si endpoint public ou endpoint auth (`curl` 61 fois/min -> 429)
- [ ] Nouveaux endpoints dans `publicRoutes` justifies dans le decision_log (sinon deny-by-default)
- [ ] `/go-recette` score >= 36/41 zero CRITIQUE si Go touche ; `/react-recette` si TSX touche
- [ ] Doc securite mise a jour dans `_alire/01_DOCUMENTATION/security/` (R15 + R20)

Si un gate echoue : STOP, fix, re-gate. JAMAIS declarer "done" avec un gate rouge.

## Scoring agentique

| Critere | Score |
|---------|-------|
| C1 Decomposition : sous-taches identifiees ? | /10 |
| C2 Planification : PLAN_SECURE_GUARDIAN_*.md cree et suivi ? | /10 |
| C3 Replanification : /replan declenche sur echecs consecutifs (nouveau vuln class apres fix) ? | /10 |
| C4 Outillage : gosec + curl adversarial + /go-recette + /react-recette invoques selon perimetre ? | /10 |
| C5 Tracabilite : decision_log + RETEX produits ? | /10 |

Score total /50 -- >= 40 : Exemplaire | 30-39 : Acceptable | < 30 : RETEX obligatoire

## Knowledge Reference

OWASP Top 10 (2021), OWASP API Security Top 10, bcrypt / argon2, JWT (RFC 7519),
OAuth 2.0 / OIDC, CSP Level 3, CORS, rate limiting, input validation, output
encoding, TLS 1.3, HSTS, fail2ban, LIA-SEC security primitives
(`setCORSHeaders`, `logSecurityAuditEvent`, `rate_limiter.go`,
`auth_session_middleware.go`, `system_variables`, `pwreset` CLI).
