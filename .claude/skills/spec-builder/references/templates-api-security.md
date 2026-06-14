# API & Security Templates -- Spec-Builder Reference

## API Contract Template (Phase 4)

For each endpoint group:

```markdown
## {Entity} Management

### POST /api/grc/{module}/{entity}
- **Description :** Create new {entity}
- **Auth :** JWT required (fetchWithConfig)
- **Request body :**
  ```json
  {
    "name": "string (required, max 200)",
    "description": "string (optional)",
    "status": "string (enum: draft|in_progress|review|validated)"
  }
  ```
- **Response 201 :**
  ```json
  {
    "id": "uuid",
    "name": "string",
    "created_at": "ISO 8601"
  }
  ```
- **Errors :** 400 (validation), 401 (no token), 500 (db error)
- **Handler Go :** `handle{Module}Create{Entity}(w, r)`
- **Trace :** REQ-001, REQ-003
```

### Mandatory Special Endpoints

Each module MUST include:
- `GET .../summary` -- Aggregated statistics
- `GET .../export/json` -- Full JSON export
- `GET .../export/csv` -- CSV export
- `POST .../export/report` -- PPTX export (if applicable)

### CRUD Matrix by Role

| Endpoint | RSSI | Auditeur | Admin | Viewer |
|----------|------|----------|-------|--------|
| POST /create | W | W | W | - |
| GET /list | R | R | R | R |
| PUT /update | W | W | W | - |
| DELETE /archive | - | - | W | - |

---

## Threat Model STRIDE Template (Phase 5a)

```markdown
## Threat Model -- {Module}

| Menace | Applicable | Scenario | Mitigation |
|--------|-----------|----------|------------|
| **S**poofing (usurpation identite) | Oui/Non | Ex: un viewer se fait passer pour admin | JWT + RBAC middleware |
| **T**ampering (falsification donnees) | Oui/Non | Ex: modification du risk score via API | Parameterized queries + audit trail |
| **R**epudiation (deni d'action) | Oui/Non | Ex: nier avoir accepte un risque | RecordAuditEvent() sur chaque mutation |
| **I**nformation disclosure (fuite) | Oui/Non | Ex: export CSV avec donnees confidentielles | RBAC sur export, filtrage colonnes |
| **D**enial of service (deni de service) | Oui/Non | Ex: requete risk-matrix sur 10K scenarios | Pagination obligatoire, timeout |
| **E**levation of privilege (escalade) | Oui/Non | Ex: viewer accede a DELETE | Middleware role-check par endpoint |
```

## Data Classification Template (Phase 5b)

```markdown
## Classification des donnees

| Table/Champ | Sensibilite | Justification | Protection |
|-------------|-------------|---------------|------------|
| {prefix}_assessments.name | INTERNE | Nom du projet audit | JWT required |
| {prefix}_risk_scenarios.description | CONFIDENTIEL | Details vulnerabilites | RBAC + audit |
| {prefix}_treatments.cost_estimate | RESTREINT | Donnees financieres | RBAC admin only |
| {prefix}_acceptance.accepted_by | INTERNE | Tracabilite | Immutable (audit trail) |
```

Levels: `PUBLIC` < `INTERNE` < `CONFIDENTIEL` < `RESTREINT`

## RBAC Matrix Template (Phase 5c)

```markdown
## RBAC -- {Module}

| Endpoint | Admin | RSSI | Auditeur | Viewer | Non-auth |
|----------|-------|------|----------|--------|----------|
| POST /create | W | W | W | DENY | 401 |
| GET /list | R | R | R | R | 401 |
| GET /{id} | R | R | R | R | 401 |
| PUT /{id} | W | W | W | DENY | 401 |
| DELETE /{id} | W | DENY | DENY | DENY | 401 |
| POST /export | R | R | R | DENY | 401 |
| PUT /accept | W | W | DENY | DENY | 401 |
```

**RBAC Rules LIA-SEC:**
- All endpoints under `/api/*` are JWT-protected by default (deny-by-default)
- Roles are checked in the Go handler (not in global middleware)
- `RecordAuditEvent()` on EVERY mutation (create, update, delete, accept)
- Exports filter columns by role

## Input Validation Template (Phase 5d)

```markdown
## Input Validation

| Champ | Type | Validation | Pattern/Range | OWASP |
|-------|------|-----------|---------------|-------|
| name | VARCHAR(200) | Required, max 200 chars | `^[\\w\\s\\-\\.]{1,200}$` | A03:Injection |
| description | TEXT | Optional, max 5000 chars | Sanitize HTML (DOMPurify frontend) | A03:Injection |
| status | VARCHAR(20) | Enum whitelist | CHECK constraint SQL | A03:Injection |
| score | SMALLINT | Range check | `CHECK (score BETWEEN 0 AND 100)` | A04:Insecure Design |
| column_name | dynamic | Whitelist columns | `allowedColumns map[string]bool` | A03:Injection |
```

**Mandatory Go patterns:**
```go
// Dynamic SQL: ALWAYS whitelist
var allowedColumns = map[string]bool{"name": true, "status": true}
if !allowedColumns[column] {
    LogSystemEvent("WARN", "SECURITY", "SQL_INJECTION_ATTEMPT", ...)
    return
}

// Parameterized queries: ALWAYS $1, $2
db.Query("SELECT * FROM table WHERE id = $1", id)

// NEVER fmt.Sprintf with user data in SQL
```

## Security Checklist (Phase 5e)

```markdown
## Checklist Securite

- [ ] Tous les endpoints sont sous /api/* (JWT par defaut)
- [ ] Aucun endpoint dans publicRoutes sauf justification documentee
- [ ] Parameterized queries ($1, $2) pour TOUTES les requetes SQL
- [ ] Whitelist pour SQL dynamique (colonnes triables/filtrables)
- [ ] RecordAuditEvent() sur toutes les mutations
- [ ] LogSystemEvent("WARN", "SECURITY", ...) sur tentatives invalides
- [ ] Input validation (longueur, format, enum) sur chaque champ
- [ ] DOMPurify sur tout contenu HTML affiche cote frontend
- [ ] Pas de dangerouslySetInnerHTML sans sanitization
- [ ] Export CSV/JSON filtre selon le role
- [ ] Pas de secrets hardcodes (ConfigurationService / env vars)
- [ ] Rate limiting sur les endpoints couteux (export, calcul)
```
