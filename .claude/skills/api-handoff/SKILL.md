---
name: api-handoff
version: "1.0"
description: "Generates a structured API handoff document after backend implementation, giving the frontend developer (or AI) the full contract: endpoints, Go->TS interfaces, validation rules, business logic gotchas, fetchWithConfig integration notes, R17 fixture checklist. Triggers on: create handoff, document API for frontend, api handoff, contrat API, handoff frontend, generate handoff."
---

# API Handoff v1.0 -- Backend → Frontend Contract

Generates a focused, structured handoff document after backend Go work is complete.
Gives the frontend developer everything needed to build the integration WITHOUT back-and-forth questions.

**Mode:** No-chat. Single execution. Produces the document, no discussion.
**Scope:** One feature or one logical group of endpoints.
**Output:** `_alire/01_DOCUMENTATION/api/{feature}_handoff_api_en.md`

---

## Syntax

```
/api-handoff <feature-or-file> [flags]
```

| Flag | Description |
|------|-------------|
| `--update` | Update an existing handoff after API changes (bumps version) |
| `--minimal` | Simple CRUD only -- skip business logic / integration sections |
| `--r17` | Append R17 fixture capture commands after the document |

**Examples:**
```
/api-handoff remediation_tracking
/api-handoff iso27005_export --r17
/api-handoff anssi_coverage --update
/api-handoff cve_apt_crosslink --minimal
```

---

## Trigger Conditions

Use this skill when:
- Backend `*_api.go` file is complete (routes registered, handlers implemented)
- A feature requires Go → React handoff before frontend work starts
- Frontend reports "I don't understand the shape of the response"
- R17 Contract Gate is needed and no handoff exists yet
- User says: "create handoff", "document API for frontend", "contrat API", "handoff frontend"

**Timing:** After `build_secure_lia.sh` passes. Before frontend implementation.

---

## What NOT to Include

Deliberately excluded (frontend doesn't need these):
- Internal Go package names, struct field tags, DB queries
- PostgreSQL schema or migration details
- Backend test strategies
- Deployment or infrastructure details
- File paths inside `cmd/sigma_web/`

---

## Decomposition des sous-taches

Au demarrage, decomposer toute demande en sous-taches independantes :

- [ ] Sous-tache 1 : localiser le fichier `*_api.go` cible + verifier si un handoff existe deja
- [ ] Sous-tache 2 : lire les handlers et extraire routes, structs request/response, auth, error codes
- [ ] Sous-tache 3 : generer les interfaces TypeScript (Go -> TS mapping, envelope `{success,data}`)
- [ ] Sous-tache 4 : ecrire le document handoff dans `_alire/01_DOCUMENTATION/api/{feature}_handoff_api_en.md`
- [ ] Sous-tache 5 : initialiser metadata (`doc_classifier.py`) + reindexer (`doc_librarian.py`)
- [ ] Sous-tache 6 : appender les commandes de capture fixture R17 si `--r17` ou API complexe

Utiliser `TaskCreate` pour tracker si > 3 sous-taches.

## Plan d'execution

Pour tout handoff non trivial (> 4 endpoints, state machine, flux multi-etapes) :

1. Creer `_alire/tracking/PLAN_API_HANDOFF_{FEATURE}_{YYYY-MM-DD}.md` avant d'ecrire le document.
2. Template : `_alire/tracking/PLAN_TEMPLATE.md`.
3. Cocher chaque sous-tache a la completion.
4. Si replanification : Status -> REPLANIFIE + lien vers nouveau plan.

Pour un handoff simple (1-3 endpoints CRUD standard) : plan inline suffit.

## Adaptation et replanification

Si 2 etapes consecutives echouent (ex: interface TS ne matche pas le payload live, ou struct Go introuvable dans le fichier) :

- STOP
- Invoquer `/replan` -> produit `PLAN_API_HANDOFF_*_REPLAN_*.md`
- NE PAS inventer des types ou des champs -- R18 : verifier par curl live

Declencheurs typiques :
- Interface TS generee mais fixture R17 capturee montre un champ manquant -> REPLAN (re-lire handler Go)
- Handoff existant mais `--update` non passe et structure a change -> REPLAN (demander confirmation ou utiliser `--update`)
- Backend en cours de modification au moment du handoff -> REPLAN (attendre build stable)

## Outils declares

| Outil | Usage | Retry policy |
|-------|-------|--------------|
| `Read`, `Grep`, `Glob` | Lire `*_api.go`, `auth_session_middleware.go` (publicRoutes), structs request/response | N/A |
| `Write` | Creer `_alire/01_DOCUMENTATION/api/{feature}_handoff_api_en.md` | N/A |
| `Edit` | Mettre a jour handoff existant (`--update`) | N/A |
| `Bash curl live capture` | Capturer payload reel pour fixture R17 (JWT depuis browser DevTools ou `lia_capture_fixture`) | echec 401 -> verifier token / publicRoutes |
| `Bash doc_classifier.py` | Init/bump metadata `.doc-meta.json` | N/A |
| `Bash doc_librarian.py reindex` | Reindexer `INDEX.md` apres creation | N/A |
| `TaskCreate` | Tracking si > 3 sous-taches | N/A |
| `Skill(react-expert)` | Apres livraison du handoff, si composant React doit etre cree | Invoquer apres cloture handoff |

Selection dynamique : curl live si backend disponible, `lia_capture_fixture` si endpoint JWT-protege, `--minimal` auto-detecte si API simple.

## Tracabilite agentique

Logger dans `_alire/02_LOGS/Journals/decision_log.jsonl` chaque decision non triviale :

- Choix de mapping type (ex: `*string` -> `string | null`, Go `time.Time` -> `string ISO 8601`)
- Rejet d'un champ comme "non necessaire frontend" (ex: champ DB interne non expose)
- Decisions de complexite (minimal vs full handoff)
- Trade-offs de contrat (pagination offset vs cursor, optional vs required)

Format :
```json
{"timestamp":"...","session":"api-handoff-{feature}","action":"...","reasoning":"...","alternatives_rejected":["..."],"outcome":"...","confidence":"high","plan_ref":"PLAN_API_HANDOFF_*.md"}
```

RETEX en fin de session si score agentique < 40/50 -> `_alire/02_LOGS/Journals/retex/RETEX_API_HANDOFF_YYYY-MM-DD.md`.

## Execution Workflow

### Step 0 -- Locate the backend file

```bash
# Find the target *_api.go file
ls cmd/sigma_web/{feature}*_api.go 2>/dev/null
grep -l "RegisterXxx" cmd/sigma_web/*.go | head -5

# Check if a handoff already exists (NEVER duplicate)
find _alire/01_DOCUMENTATION/api/ -name "*{feature}*handoff*"
```

If handoff exists AND `--update` not passed → ask user before overwriting.

### Step 1 -- Read the backend source

Read the target `*_api.go` file(s). Extract:
- All `HandleFunc` route paths and HTTP methods
- Request struct fields (required vs optional, types, constraints)
- Response struct fields (full shape including nested)
- Auth requirements (check `auth_session_middleware.go` publicRoutes list)
- Error codes returned (404, 403, 422, 409, 500)
- Business logic in handlers (not DB queries -- the WHAT, not the HOW)
- Cross-cutting concerns: pagination, filtering, sorting patterns

### Step 2 -- Detect API complexity

**Simple API** (use `--minimal` or auto-detect):
- 1-3 endpoints, standard CRUD shape
- No complex business logic or state machine
- No multi-step flows or ordering constraints
- Response is a straightforward list or single object

→ Generate minimal handoff: endpoints + example JSON + error codes only.

**Complex API** (default):
- 4+ endpoints or non-obvious ordering
- Business rules (role checks, state transitions, idempotency)
- Multi-step flows (create → configure → validate → activate)
- Special edge cases (soft deletes, concurrent write guards, etc.)

→ Generate full handoff with all sections.

### Step 3 -- Build Go → TypeScript interfaces

For every request/response struct in the handler file:

```typescript
// Rule: Go bool -> boolean, int/int64 -> number, *string -> string | null
// Rule: time.Time -> string (ISO 8601), uuid.UUID -> string
// Rule: json:"omitempty" -> optional field (add ?)
// Rule: []T -> T[] (never null, use [] as empty default)
// Rule: map[string]interface{} -> Record<string, unknown>
// Rule: The {success, data} envelope MUST be shown -- never omit
```

Show the full response including the LIA-SEC standard envelope:
```typescript
interface ApiResponse<T> {
  success: boolean;
  data: T;           // unwrap this in service layer
  message?: string;
  error?: string;
}
```

### Step 4 -- Write the handoff document

Save to `_alire/01_DOCUMENTATION/api/{feature}_handoff_api_en.md`.

Follow the template below exactly. Skip sections marked OPTIONAL if `--minimal`.

### Step 5 -- Initialize metadata

```bash
python3 .claude/skills/doc-code/scripts/doc_classifier.py init \
  _alire/01_DOCUMENTATION/api/{feature}_handoff_api_en.md --type api

python3 .claude/skills/doc-code/scripts/doc_librarian.py reindex \
  _alire/01_DOCUMENTATION/ -o _alire/01_DOCUMENTATION/INDEX.md
```

If `--update`: run `doc_classifier.py bump` instead of `init`.

### Step 6 -- R17 fixture commands (if `--r17` or complex API)

Append after the document a ready-to-run fixture capture block.

---

## Handoff Document Template

```markdown
# API Handoff: {Feature Name}

> Generated: {YYYY-MM-DD} | Version: 1.0.0 | Status: CURRENT
> Backend file: `cmd/sigma_web/{feature}_api.go`

## Business Context

{2-4 sentences: what problem this solves, who uses it, domain terms frontend must know}

**Domain vocabulary:**
| Term | Meaning |
|------|---------|
| {term} | {meaning} |

---

## Authentication

| Route pattern | Auth required | Role |
|--------------|---------------|------|
| `GET /api/{path}` | Yes (JWT Bearer) | Any authenticated user |
| `POST /api/{path}` | Yes (JWT Bearer) | Admin only |

Auth header injected automatically by `fetchWithConfig`. No manual header needed.
Public routes (no token): list only if present in `auth_session_middleware.go` publicRoutes.

---

## Endpoints

### {METHOD} /api/{path}

**Purpose:** {one line}
**Auth:** {required / public}

**Request:**
```typescript
interface {Name}Request {
  field: type;        // Required. {constraint: max 500 chars, enum values...}
  optionalField?: type; // Optional. Default: {value}
}
```

**Response (success `200`):**
```typescript
// Always unwrap .data in the service layer (fetchWithConfig returns raw response)
interface ApiResponse<{Name}Data> {
  success: true;
  data: {Name}Data;
}

interface {Name}Data {
  id: number;
  // ... all fields with types
  createdAt: string; // ISO 8601
}
```

**Response (error):**
| Status | When | Body |
|--------|------|------|
| `400` | Malformed JSON | `{ success: false, error: "..." }` |
| `403` | Insufficient role | `{ success: false, error: "Forbidden" }` |
| `404` | Resource not found | `{ success: false, error: "not found" }` |
| `422` | Validation failure | `{ success: false, error: "{field} is required" }` |
| `409` | Conflict / duplicate | `{ success: false, error: "already exists" }` |

**Edge cases:**
- {non-obvious behavior 1}
- {non-obvious behavior 2}

---

## Data Models / TypeScript Interfaces

```typescript
// Complete interfaces for all entities used across endpoints

interface {MainEntity} {
  id: number;
  status: 'pending' | 'active' | 'closed'; // use string union, not enum
  // ...
}
```

---

## Enums and Constants [OPTIONAL -- skip for --minimal]

```typescript
// Values accepted by the API (not just frontend display)
type {StatusField} = 'pending' | 'approved' | 'rejected';

// Map for display labels
const {STATUS_LABELS}: Record<{StatusField}, string> = {
  pending: 'Pending Review',
  approved: 'Approved',
  rejected: 'Rejected',
};
```

---

## Validation Rules [OPTIONAL -- skip for --minimal]

Frontend should mirror these for immediate UX feedback (do not rely on backend-only validation).

| Field | Rule | UX guidance |
|-------|------|-------------|
| `name` | Required, max 255 chars | Show char counter |
| `email` | Valid email format | Validate on blur |
| `score` | Integer 0-100 | Numeric input with min/max |

---

## Business Logic and Edge Cases [OPTIONAL -- skip for --minimal]

{Non-obvious behaviors discovered in the handler -- things frontend cannot infer from the interface alone}

- **State machine:** {entity} transitions: `draft -> submitted -> reviewed -> closed`. Cannot skip states.
- **Idempotency:** POST `/api/{path}` is idempotent on `external_id`. Returns existing resource if found.
- **Soft delete:** DELETE marks `deleted_at`, does not remove. GET list excludes soft-deleted by default.
- **Role enforcement:** Only `admin` role can change `owner_id`. Other roles get 403 silently.
- **Concurrent write guard:** PATCH uses `updated_at` optimistic lock. 409 if stale.

---

## Integration Notes [OPTIONAL -- skip for --minimal]

### fetchWithConfig pattern

```typescript
// CORRECT -- fetchWithConfig injects JWT Bearer, handles retry, resolves baseUrl
import { fetchWithConfig } from '../config/apiConfig';

const response = await fetchWithConfig('/api/{path}');
const json = await response.json() as ApiResponse<{Name}Data>;

if (!json.success) {
  customLogger.error('{COMPONENT}', 'API error', { error: json.error });
  return;
}
const data = json.data; // always unwrap .data
```

### Recommended flow

1. {Step 1 -- e.g., fetch list on mount}
2. {Step 2 -- e.g., open detail modal on row click}
3. {Step 3 -- e.g., submit form via POST, refresh list on success}

### Caching strategy

{None / Cache 5min / Invalidate on POST or DELETE}

### Real-time / polling

{No WebSocket / SSE at `/api/{path}/events` / Poll every 30s}

### AI response rendering

{If any field contains AI-generated text: use `<AIMarkdownView content={field} />` -- never `<Typography>` or `<pre>`}

---

## Test Scenarios

| # | Scenario | Expected |
|---|----------|----------|
| 1 | Happy path: {action} | 200, data shape matches interface |
| 2 | Validation error: missing required field | 422, error message shown |
| 3 | Unauthorized: no token | 401 redirect to login |
| 4 | Not found: invalid ID | 404, empty state shown |
| 5 | {Edge case specific to this feature} | {expected behavior} |

---

## Open Questions / TODOs

- [ ] {Unresolved item 1 -- e.g., pagination not yet implemented, ETA unknown}
- [ ] {Item 2}

---

## R17 Fixture Capture [appended when --r17 flag or complex API]

Run these after the backend is live to capture real payloads for integration tests:

```bash
# Replace TOKEN with a real JWT (copy from browser DevTools -> Network -> Authorization header)
TOKEN="eyJ..."

# Capture each endpoint
curl -s -H "Authorization: Bearer $TOKEN" \
  http://localhost:8081/api/{path} \
  | python3 -m json.tool \
  > sigma-react-frontend/src/components/{Component}/__fixtures__/{Component}.fixture.json

# Verify the fixture is non-empty and has success: true
python3 -c "
import json, sys
d = json.load(open('sigma-react-frontend/src/components/{Component}/__fixtures__/{Component}.fixture.json'))
assert d.get('success') == True, 'API returned success=false'
assert d.get('data') is not None, 'No data field -- check envelope unwrap'
print('Fixture OK:', list(d.keys()))
"
```

Then write a render-and-assert test in `{Component}.test.tsx` using this fixture (R17 gate).
```
```

---

## Verification Gate (BLOCKING before declaring done)

- [ ] All endpoints from the `*_api.go` file are documented
- [ ] TypeScript interfaces match actual Go struct field types (verified by reading source)
- [ ] Error codes table is complete (no invented status codes)
- [ ] Business logic section covers at least one non-obvious behavior (or marked N/A)
- [ ] `fetchWithConfig` usage example is present
- [ ] AI text fields use `AIMarkdownView` guidance if applicable (R22)
- [ ] `.doc-meta.json` initialized via `doc_classifier.py`
- [ ] `INDEX.md` regenerated via `doc_librarian.py reindex`
- [ ] Zero placeholders, TODO, or invented data in the document

## Scoring agentique

| Critere | Score |
|---------|-------|
| C1 Decomposition : sous-taches identifiees ? | /10 |
| C2 Planification : PLAN_API_HANDOFF_*.md cree et suivi ? | /10 |
| C3 Replanification : /replan declenche sur echecs consecutifs ? | /10 |
| C4 Outillage : curl live capture + doc_classifier + /react-expert invoques selon contexte ? | /10 |
| C5 Tracabilite : decision_log + RETEX produits ? | /10 |

Score total /50 -- >= 40 : Exemplaire | 30-39 : Acceptable | < 30 : RETEX obligatoire

---

## Integration with Other Skills

| Situation | Chain |
|-----------|-------|
| After `/apex` backend phase | `/api-handoff {feature} --r17` before frontend phase |
| R17 Contract Gate required | `/api-handoff {feature} --r17` then write fixture + render test |
| API changed after feedback | `/api-handoff {feature} --update` |
| Full module documentation | `/api-handoff {feature}` then `/doc-code {feature} --update --scope=back` |
| New UI component needed | `/api-handoff` → `/create-ui-help` → build component |

---

## LIA-SEC Conventions Reminder (embedded for no-lookup execution)

| Convention | Rule |
|------------|------|
| API calls | `fetchWithConfig` (never raw `fetch()`) |
| Response envelope | Always `{success, data}` -- unwrap `.data` in service layer |
| AI text rendering | `<AIMarkdownView content={field} />` (never `<Typography>` for AI output) |
| MUI Grid | `<Grid size={{ xs: 12, md: 6 }}>` (never `<Grid item xs>`) |
| Chip style | `<Chip sx={{ borderRadius: 4 }} />` (never default oval) |
| Logging | `customLogger.info('COMPONENT', 'msg', {data})` (never `console.log`) |
| Backend URL | `getBackendUrl()` from `ConfigurationService` (never hardcode) |
| Font family | `fontFamily: 'inherit'` in sx props (never hardcode font name) |
| Hex colors | Use `theme.palette.*` or constants from `constants/colors.ts` |
