---
name: api-designer
description: Designs new REST endpoints for LIA-SEC backend Go (cmd/sigma_web, 560+ routes). Produces resource model, URI patterns, mux.Router signatures, JSON envelope `{success,data}`, RFC 7807 error responses, OpenAPI 3.1 spec, JWT auth wiring (auth_session_middleware.go), rate-limit decisions (rate_limiter.go), pagination strategy. Invoke AVANT toute creation d'un nouveau handler `/api/*` ou redesign d'une route existante. Differe de `/api-handoff` (genere le contrat backend->frontend APRES implementation). Workflow : analyze -> resource model -> endpoint spec -> OpenAPI 3.1 -> auth/rate-limit decision -> handoff a `/golang-pro` pour code Go + `/sql-pro` pour queries.
license: MIT (upstream Jeffallan/claude-skills) -- adapted for LIA-SEC
allowed-tools: Read, Grep, Glob, Bash, Write
metadata:
  author: mo0ogly@proton.me
  upstream: https://github.com/Jeffallan/claude-skills/tree/main/skills/api-designer
  version: "2.0.0-lia"
  domain: api-architecture
  triggers: design API, nouveau endpoint, REST design, OpenAPI, contract API, resource modeling, URI design, pagination, error format, RFC 7807, ajouter route /api/, redesign route, versioning API
  role: architect
  scope: design
  output-format: spec + OpenAPI YAML
  related-skills: api-handoff, golang-pro, sql-pro, secure-code-guardian, security-reviewer
  enforces-rules: R5, R6, R7, R10, R12, R17
---

# API Designer (LIA-SEC adaptation)

> **Quand m'invoquer** : DESIGN d'un nouvel endpoint REST avant ecriture du code Go.
> Resource modeling, URI patterns, JSON envelope, RFC 7807 errors, OpenAPI 3.1,
> auth/rate-limit decisions.
>
> **Differe de** :
> - `/api-handoff` -- genere le contrat backend->frontend APRES implementation
> - `/golang-pro` -- ecrit le code Go (handler, mux.Router, types) APRES design
> - `/sql-pro` -- ecrit les queries APRES design
> - `/secure-code-guardian` -- durcit l'auth APRES design
> - `/security-reviewer` -- audite l'endpoint APRES merge

---

## 0. Stack LIA-SEC -- conventions API obligatoires

| Item | Convention |
|------|------------|
| Routing | `gorilla/mux` -- `r.HandleFunc("/api/...", h).Methods("GET","OPTIONS")` |
| Auth defaut | JWT deny-by-default via `auth_session_middleware.go` |
| Routes publiques | Whitelist explicite dans `publicRoutes` map (justification documentee) |
| Rate limit | `rate_limiter.go` 60 req/min/IP sur endpoints sensibles (CVE search, MITRE) |
| CORS | `setCORSHeaders(w)` + handle OPTIONS au debut de chaque handler |
| Format reponse SUCCESS | `{ "success": true, "data": <payload> }` (envelope) |
| Format reponse ERROR | RFC 7807 Problem Details (voir section 4) |
| Logging | `LogSystemEvent("INFO"\|"ERROR", "<DOMAIN>", "<ACTION>", details)` (R6) |
| Audit | `LogSecurityAuditEvent(...)` pour auth/admin/sensitive |
| Build | Ajouter le fichier dans `build_secure_lia.sh` ; appeler `RegisterXxxRoutes(r)` dans `backend_8081.go` |
| Frontend client | `fetchWithConfig` (pas `fetch` brut) -- voir R17 |
| Doc OpenAPI | `_alire/01_DOCUMENTATION/api/REST_API_REFERENCE.md` (a maintenir) |

---

## 1. Workflow agentique (6 phases)

```
[1] ANALYZE
    - Cas d'usage : qui appelle ? frequence ? read/write ? batch ?
    - Donnees existantes (table PostgreSQL, vue, jointure ?)
    - Contraintes : multi-tenant ? client_id filter ? role admin only ?
    - Volumetrie attendue (10 rows ? 10K ? paginate ?)

[2] RESOURCE MODEL
    - Nommer la ressource (NOUN, pas VERB) : /assets, pas /getAssets
    - Sous-ressources : /assets/{id}/risks (relation 1-N)
    - Identifier : UUID prefere, sinon BIGSERIAL si volumetrie justifiee
    - Filtrage : query params standardises (?status=, ?client_id=, ?limit=, ?cursor=)

[3] ENDPOINT DESIGN
    - URI snake_case : /api/smsi/risk-assessments (pas /api/smsiRiskAssessments)
    - HTTP methods strictement : GET (read), POST (create), PUT (replace), PATCH (partial), DELETE
    - Idempotence : GET, PUT, DELETE = idempotent ; POST = non
    - Status codes : 200 OK, 201 Created (POST + Location header), 204 No Content (DELETE),
      400 Validation, 401 Unauthorized, 403 Forbidden, 404 Not Found, 409 Conflict,
      422 Unprocessable Entity, 429 Rate Limit, 500 Internal

[4] CONTRACT (OpenAPI 3.1)
    - Schema requis pour request body et response
    - Response wrapping {success, data} obligatoire (envelope LIA-SEC)
    - Errors via RFC 7807 application/problem+json
    - Tags par module (Compliance, GRC, CVE, Discovery, AI, etc.)
    - operationId stable pour SDK generation future

[5] AUTH + RATE-LIMIT DECISION
    - Public ? Justifier dans publicRoutes whitelist (sinon JWT auto)
    - Admin only ? Check role apres JWT (middleware AdminAuditMiddleware)
    - Sensitive ? Add rate-limiter (60 req/min/IP) + LogSecurityAuditEvent
    - Multi-tenant ? Inclure client_id dans le filtre + verifier dans le handler

[6] HANDOFF
    - Specs ecrites dans `_alire/01_DOCUMENTATION/api/<module>_api_reference_en.md`
    - Invoquer `/golang-pro` pour le code Go (handler, types, mux registration)
    - Invoquer `/sql-pro` pour les queries (parameterized + R7)
    - Invoquer `/api-handoff --r17` apres implementation pour le contrat frontend
```

---

## 2. Reference Guide -- charger selon le contexte

| Topic | Reference | Charger quand |
|-------|-----------|---------------|
| REST patterns | `references/rest-patterns.md` | Resource modeling, URI design, HTTP methods |
| Versioning | `references/versioning.md` | API v1/v2 split, deprecation strategy |
| Pagination | `references/pagination.md` | Choix cursor vs offset vs keyset |
| Error handling | `references/error-handling.md` | RFC 7807 Problem Details, status codes |
| OpenAPI | `references/openapi.md` | OpenAPI 3.1 spec, redocly lint, prism mock |

> Les references upstream sont generiques (Stripe-like). Pour LIA-SEC, **toujours**
> appliquer le wrapper `{success,data}` LIA-SEC en plus du Problem Details RFC 7807.

---

## 3. Templates LIA-SEC

### 3.1 Endpoint Go template (a passer ensuite a `/golang-pro`)

```go
// File: cmd/sigma_web/<module>_api.go
// Routes: /api/<module>/<resource>

func RegisterMyModuleRoutes(r *mux.Router) {
    r.HandleFunc("/api/mymodule/items", listItemsHandler).Methods("GET", "OPTIONS")
    r.HandleFunc("/api/mymodule/items", createItemHandler).Methods("POST", "OPTIONS")
    r.HandleFunc("/api/mymodule/items/{id}", getItemHandler).Methods("GET", "OPTIONS")
    r.HandleFunc("/api/mymodule/items/{id}", updateItemHandler).Methods("PUT", "OPTIONS")
    r.HandleFunc("/api/mymodule/items/{id}", deleteItemHandler).Methods("DELETE", "OPTIONS")
    LogSystemEvent("INFO", "MYMODULE", "ROUTES_REGISTERED", "5 endpoints registered")
}

func listItemsHandler(w http.ResponseWriter, r *http.Request) {
    setCORSHeaders(w)
    if r.Method == "OPTIONS" { w.WriteHeader(200); return }
    // Use /sql-pro for parameterized query, /golang-pro for Go idioms
    // ...
    writeJSONSuccess(w, items, paginationMeta)
}
```

### 3.2 JSON envelope LIA-SEC (success)

```json
{
  "success": true,
  "data": {
    "items": [ ... ],
    "pagination": {
      "cursor": "eyJpZCI6MTAwMH0=",
      "next_cursor": "eyJpZCI6MTAyMH0=",
      "has_more": true,
      "limit": 20
    }
  }
}
```

### 3.3 RFC 7807 Problem Details (error)

```json
{
  "type": "https://liascan.tech/errors/validation-error",
  "title": "Validation Error",
  "status": 422,
  "detail": "The 'cvss_score' field must be between 0.0 and 10.0",
  "instance": "/api/cve/trurisk/req-abc123",
  "errors": [
    { "field": "cvss_score", "message": "must be between 0 and 10" }
  ]
}
```

Always set `Content-Type: application/problem+json` for error responses.

### 3.4 OpenAPI 3.1 endpoint template (LIA-SEC envelope)

```yaml
openapi: "3.1.0"
info:
  title: LIA-SEC API
  version: "2.0.0"
servers:
  - url: https://liascan.tech
  - url: http://localhost:8081
security:
  - BearerAuth: []
paths:
  /api/smsi/assets:
    get:
      summary: List SMSI assets
      operationId: listSmsiAssets
      tags: [SMSI]
      parameters:
        - { name: client_id, in: query, required: true, schema: { type: string, format: uuid } }
        - { name: status, in: query, schema: { type: string, enum: [active, archived] } }
        - { name: cursor, in: query, schema: { type: string } }
        - { name: limit, in: query, schema: { type: integer, default: 20, maximum: 100 } }
      responses:
        "200":
          description: Assets list
          content:
            application/json:
              schema: { $ref: "#/components/schemas/ListResponse_Asset" }
        "401": { $ref: "#/components/responses/Unauthorized" }
        "429": { $ref: "#/components/responses/TooManyRequests" }
components:
  schemas:
    ListResponse_Asset:
      type: object
      required: [success, data]
      properties:
        success: { type: boolean, const: true }
        data:
          type: object
          required: [items, pagination]
          properties:
            items:
              type: array
              items: { $ref: "#/components/schemas/Asset" }
            pagination: { $ref: "#/components/schemas/CursorPagination" }
    Asset:
      type: object
      required: [id, name, criticality, client_id, created_at]
      properties:
        id:           { type: string, format: uuid }
        client_id:    { type: string, format: uuid }
        name:         { type: string }
        criticality:  { type: string, enum: [low, medium, high, critical] }
        created_at:   { type: string, format: date-time }
        updated_at:   { type: string, format: date-time }
    CursorPagination:
      type: object
      required: [cursor, has_more]
      properties:
        cursor:      { type: string, nullable: true }
        next_cursor: { type: string, nullable: true }
        has_more:    { type: boolean }
        limit:       { type: integer }
    Problem:
      type: object
      required: [type, title, status]
      properties:
        type:     { type: string, format: uri }
        title:    { type: string }
        status:   { type: integer }
        detail:   { type: string }
        instance: { type: string, format: uri }
  responses:
    Unauthorized:
      description: Missing or invalid JWT
      content:
        application/problem+json:
          schema: { $ref: "#/components/schemas/Problem" }
    TooManyRequests:
      description: Rate limit exceeded (60 req/min/IP)
      headers:
        Retry-After: { schema: { type: integer } }
      content:
        application/problem+json:
          schema: { $ref: "#/components/schemas/Problem" }
  securitySchemes:
    BearerAuth: { type: http, scheme: bearer, bearerFormat: JWT }
```

---

## 4. Anti-patterns interdits (refus immediat)

| INTERDIT | A la place |
|----------|-----------|
| URI avec verbe : `/api/getUsers`, `/api/createAsset` | Resource noun : `/api/users`, `/api/assets` |
| `GET /api/users?action=delete&id=42` | `DELETE /api/users/42` |
| Reponse sans `{success,data}` envelope | Toujours wrapper |
| Erreur retournant texte plain ou HTML | RFC 7807 `application/problem+json` |
| Public route sans justification dans `publicRoutes` map | Documenter la justification |
| Pagination par OFFSET sur table > 100K rows | Cursor pagination keyset |
| `?sort=arbitrary_column` sans whitelist | Whitelist explicite (R7) |
| Endpoint admin sans `LogSecurityAuditEvent` | Logger TOUJOURS les actions admin |
| Breaking change sans versioning | `/api/v2/...` + deprecation policy |
| Skip rate-limit sur `/api/*/search` | Activer rate_limiter (60 req/min/IP) |
| `application/x-www-form-urlencoded` ou XML | JSON only |
| Plain int IDs auto-incrementables exposes | UUID (limite IDOR + scraping) |
| 200 OK avec `{success: false}` | Status code HTTP correspondant + Problem JSON |

---

## 5. Output template (livrable d'une session api-designer)

```markdown
# API Design : <module>/<resource> -- YYYY-MM-DD

## 1. Contexte
- Module : ...
- Cas d'usage : ...
- Volumetrie : ... rows attendues
- Multi-tenant : oui (client_id filter) | non
- Sensitive : oui -> admin + audit log + rate limit | non

## 2. Resource model
- Ressource : `Asset` (UUID PK)
- Relations : 1-N avec `Risk`, N-1 avec `Owner`
- Tables PostgreSQL : `smsi_assets` (existante)

## 3. Endpoints
| Method | URI | Auth | Rate-limit | Status codes |
|--------|-----|------|-----------|--------------|
| GET    | /api/smsi/assets | JWT | non | 200, 400, 401, 429 |
| POST   | /api/smsi/assets | JWT+admin | oui | 201, 400, 401, 403, 422 |
| ...    | ... | ... | ... | ... |

## 4. OpenAPI 3.1 spec
(voir `_alire/01_DOCUMENTATION/api/<module>_api_reference_en.md`)

## 5. Auth + rate-limit decisions
- Routes : toutes JWT
- Admin only : POST/PUT/DELETE -> AdminAuditMiddleware
- Rate limit : non (faible volume), oui sur /search

## 6. Pagination strategy
- Cursor (keyset) sur `created_at` DESC, ULID-like cursor opaque base64

## 7. Error catalog
- 400 validation -> "https://liascan.tech/errors/validation-error"
- 401 -> "https://liascan.tech/errors/unauthorized"
- 403 -> "https://liascan.tech/errors/forbidden"
- 404 -> "https://liascan.tech/errors/not-found"
- 422 unprocessable -> "https://liascan.tech/errors/unprocessable"

## 8. Versioning
- Premiere version v2 (cohabitation v1 deprecated)
- Header : `LIA-API-Version: 2`

## 9. Handoff
- /golang-pro : Go handler + mux.Router + types + LogSystemEvent
- /sql-pro : queries parameterized + R7
- /api-handoff --r17 : contrat frontend post-implementation
```

---

## 6. Validation (avant handoff)

```bash
# Lint OpenAPI 3.1
npx @redocly/cli lint _alire/01_DOCUMENTATION/api/<module>_api.yaml

# Mock server pour tester les contrats
npx @stoplight/prism-cli mock _alire/01_DOCUMENTATION/api/<module>_api.yaml &
curl http://localhost:4010/api/smsi/assets?client_id=<uuid> | jq

# Generer le markdown de reference (optionnel)
npx @redocly/cli build-docs _alire/01_DOCUMENTATION/api/<module>_api.yaml \
  --output=_alire/01_DOCUMENTATION/api/<module>_api_html.html
```

---

## 7. Score agentique attendu (>= 40/50)

| Critere | Min | Comment l'atteindre |
|---------|-----|---------------------|
| C1 Decomposition | 8/10 | Workflow 6 phases respecte |
| C2 Planification (THINK) | 9/10 | 2+ alternatives evaluees (cursor vs offset, public vs auth, v1 vs v2) |
| C3 Replanification | 7/10 | Si OpenAPI lint KO -> rewrite spec ; si volumetrie change -> revoir pagination |
| C4 Outillage | 8/10 | redocly lint + prism mock AVANT handoff au code |
| C5 Tracabilite | 8/10 | Spec ecrite dans `_alire/01_DOCUMENTATION/api/`, plan + decision_log + Librarian Gate |
