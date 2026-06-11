---
name: sql-pro
description: Idiomatic SQL writer for LIA-SEC PostgreSQL 17 daily work -- writes queries, CTEs, window functions, joins, aggregations, set-based operations with parameterized statements. Invoke AVANT toute ecriture de SQL dans le code Go (handlers, services, DAO), dans les migrations courtes (sans changement schema majeur), ou quand on lit/transforme des donnees existantes. Differe de `/db-schema-designer` (DESIGN nouveau schema + migration NNN) et `/postgres-pro` (optimisation perf avancee, EXPLAIN, VACUUM, replication, pgvector tuning) -- ici c'est ECRITURE QUOTIDIENNE de SQL idiomatique, parameterized, set-based, avec respect strict de R7 (SQL injection prevention) et R5 (PostgreSQL = source).
license: MIT (upstream Jeffallan/claude-skills) -- adapted for LIA-SEC
metadata:
  author: mo0ogly@proton.me
  upstream: https://github.com/Jeffallan/claude-skills/blob/main/skills/sql-pro/SKILL.md
  version: "2.0.0-lia"
  domain: language
  triggers: ecrire SQL, write SQL, query Postgres, JOIN, CTE, WITH, window function, GROUP BY, aggregation, parameterized query, prepared statement, SELECT, INSERT, UPDATE, DELETE, MERGE, UPSERT, ON CONFLICT, RETURNING, db.Query, db.QueryRow, db.Exec, JSONB query, ARRAY operation, recursive query, lateral join, CASE WHEN, COALESCE
  role: specialist
  scope: implementation
  output-format: code (Go + SQL embedded)
  related-skills: db-schema-designer, postgres-pro, golang-pro, secure-code-guardian, rag-architect
  enforces-rules: R5, R6, R7, R10, R12, R16
---

# SQL Pro (LIA-SEC adaptation)

> **Quand m'invoquer** : ecriture de SQL quotidien dans le code Go LIA-SEC.
> SELECT/INSERT/UPDATE/DELETE/MERGE, JOINs, CTEs, window functions, JSONB
> queries, ARRAY operations, RETURNING, ON CONFLICT, parameterized statements.
>
> **NE PAS m'invoquer pour** :
> - Design d'un NOUVEAU schema (tables, indexes, migrations majeures) -> `/db-schema-designer`
> - EXPLAIN ANALYZE, perf monitoring, VACUUM tuning, replication, pgvector tuning -> `/postgres-pro`
> - Embedding/retrieval pgvector + ExecuteWithRAG -> `/rag-architect`
> - Audit securite SQL injection POST-ecriture -> `/security-reviewer`
>
> **Toujours combinable** : `/sql-pro` ecrit la query, `/postgres-pro` la tune
> apres EXPLAIN, `/secure-code-guardian` valide la sanitization.

---

## 0. Stack LIA-SEC -- contexte obligatoire

| Item | Valeur |
|------|--------|
| RDBMS | **PostgreSQL 17** uniquement (pas MySQL, pas Oracle, pas SQL Server) |
| User | `lia_admin` (DDL/DML), via `LIA_DB_PASS` ou `DATABASE_URL` (R8) |
| Database | `lia_scan` (268+ tables, 332K CVE, 5+ GB) |
| Driver Go | `database/sql` + `lib/pq` (la plupart) ou `pgx/v5` (futur migration) |
| Extensions actives | `vector` (pgvector v0.8.2 HNSW), `pg_trgm`, `unaccent`, `uuid-ossp` |
| Naming | `snake_case` partout (tables, colonnes, indexes, contraintes) |
| PK convention | `UUID` (gen_random_uuid()) ou `BIGSERIAL` selon volumetrie |
| Timestamps | `TIMESTAMPTZ` (jamais `TIMESTAMP`), default `now()` |
| JSON | `JSONB` (jamais `JSON`), avec index GIN si recherche |
| Numeriques | `DECIMAL/NUMERIC` (jamais `FLOAT/REAL` -- precision critique pour CVSS) |
| Whitelist columns | Pour SQL dynamique cf `enforcement-backend.md` (R7) |
| Logger | `LogSystemEvent("ERROR"|"WARN"|"INFO", "DB", action, details)` (R6) |
| Migrations | `cmd/sigma_web/postgres/migrations/NNN_*.sql` (numerotees) |
| Connection pool | `getDB()`, `getSmsiDB()`, etc. -- ne JAMAIS faire `sql.Open` ad-hoc |
| Backend single-instance | R16 -- attention aux locks ACCESS EXCLUSIVE sur unified_logs (244M rows) |

---

## 1. R7 SQL Injection Prevention (ABSOLU, BLOQUANT)

### La regle d'or

```go
// INTERDIT -- f"...{var}..." / fmt.Sprintf injection direct
query := fmt.Sprintf("SELECT * FROM users WHERE name = '%s'", name) // VULNERABLE

// CORRECT -- placeholders $1, $2 + arguments separes
query := "SELECT * FROM users WHERE name = $1"
rows, err := db.Query(query, name)
```

### Cas legitimes de `fmt.Sprintf` dans une query

Trois cas seulement ou `fmt.Sprintf` dans une query est OK :

1. **Format `%d` int APRES validation/clamp**
```go
months := parseMonths(r) // strconv.Atoi + clamp [1, 36]
query := fmt.Sprintf("WHERE date >= NOW() - INTERVAL '%d months'", months)
// %d ne peut pas injecter, parseMonths garantit int dans plage
```

2. **Nom de colonne issu d'une whitelist verifie**
```go
var allowedColumns = map[string]bool{"name": true, "email": true, "status": true}

if !allowedColumns[col] {
    LogSystemEvent("WARN", "SECURITY", "SQL_INJECTION_ATTEMPT",
        fmt.Sprintf("Blocked invalid column '%s'", col))
    return fmt.Errorf("invalid column: %s", col)
}
query := fmt.Sprintf("UPDATE users SET %s = $1 WHERE id = $2", col)
db.Exec(query, value, id)
```

3. **Nom de table fixe par la liste de schemas LIA-SEC**
```go
table := "smsi_" + suffix
allowed := map[string]bool{"smsi_assets": true, "smsi_risks": true}
if !allowed[table] { return errors.New("invalid table") }
query := fmt.Sprintf("SELECT count(*) FROM %s", table)
```

### Patterns INTERDITS (refus immediat)

```go
// INTERDIT 1 -- string concat
query := "SELECT * FROM users WHERE name = '" + name + "'"

// INTERDIT 2 -- Sprintf %s (string injection direct)
query := fmt.Sprintf("WHERE email = '%s'", email)

// INTERDIT 3 -- whitelist contournee
query := fmt.Sprintf("ORDER BY %s", r.URL.Query().Get("sort"))

// INTERDIT 4 -- LIKE concatenation
query := "WHERE name LIKE '%" + search + "%'"
// Correct : query := "WHERE name LIKE $1"; db.Query(query, "%"+search+"%")
```

---

## 2. Workflow d'ecriture SQL (5 phases)

```
[1] CONTEXT
    - Quelle table cible ? Verifier schema reel : \d table_name
    - Quel volume attendu ? (10 rows vs 10M rows -> strategie differente)
    - Read-only ou write ? Transactional ou autocommit ?
    - User-supplied data ? -> R7 obligatoire

[2] PATTERN
    - JOIN classique ? CTE ? Window function ? Recursive ?
    - GROUP BY + aggregation ? UPSERT (ON CONFLICT) ?
    - Pagination (LIMIT + OFFSET) ou keyset pagination ?
    - Soft-delete (`status='archived'`) vs hard DELETE ?

[3] WRITE
    - Toujours $1, $2... pas %s
    - SELECT explicite (pas SELECT *) -- nommer les colonnes
    - Filtrer EARLY (WHERE avant JOIN si possible)
    - LEFT JOIN si aggregation -> `COALESCE(SUM(x), 0)` pour pas perdre les 0
    - NULL safe : `COALESCE`, `IS DISTINCT FROM`, `NULLIF`
    - Format SQL : indenter, mettre les keywords en MAJUSCULES, commenter

[4] WRAP en Go
    - `db := getDB()` (ne pas re-ouvrir)
    - `defer rows.Close()` IMPERATIF apres `db.Query`
    - Scan dans struct typee, pas dans `interface{}`
    - Erreur PostgreSQL -> `LogSystemEvent("ERROR", "DB", "<ACTION>_FAILED", err.Error())`
    - HTTP 500 generique cote utilisateur (ne JAMAIS leak le SQL/erreur PG)

[5] VERIFY
    - Test query directement via psql avant compilation Go
    - EXPLAIN si SELECT touche > 10K rows
    - Check qu'il n'y a pas Seq Scan sur table > 100K rows
    - Si lent -> invoquer `/postgres-pro` pour tuning index
```

---

## 3. Reference Guide -- charger selon le contexte

| Topic | Reference | Charger quand |
|-------|-----------|---------------|
| Query patterns | `references/query-patterns.md` | JOIN choices, subqueries, recursive CTEs, anti-joins |
| Window functions | `references/window-functions.md` | ROW_NUMBER, RANK, LAG/LEAD, running totals, percentiles |
| Optimization | `references/optimization.md` | EXPLAIN ANALYZE, index choice, stats, covering indexes (cross-ref `/postgres-pro`) |
| Database design | `references/database-design.md` | Normalisation, FK, check constraints (cross-ref `/db-schema-designer`) |
| Dialect differences | `references/dialect-differences.md` | **PostgreSQL specifics uniquement** -- ignorer MySQL/SQL Server |

> Les references upstream comparent PostgreSQL/MySQL/SQL Server/Oracle.
> En LIA-SEC, **seul PostgreSQL 17 compte**. Quand une reference montre du
> SQL Server (`TOP`, `[brackets]`, `GETDATE()`) ou MySQL (`LIMIT a, b`,
> backticks), traduire en PostgreSQL idiomatique avant utilisation.

---

## 4. Patterns LIA-SEC frequents (copy-friendly)

### 4.1 Lecture simple parameterized

```go
// Read user by id
query := `
    SELECT id, email, name, role, status, created_at, updated_at
    FROM users
    WHERE id = $1
      AND status != 'archived'
`
var u User
err := db.QueryRow(query, userID).Scan(
    &u.ID, &u.Email, &u.Name, &u.Role, &u.Status, &u.CreatedAt, &u.UpdatedAt,
)
if err == sql.ErrNoRows {
    http.Error(w, "Not found", http.StatusNotFound)
    return
}
if err != nil {
    LogSystemEvent("ERROR", "DB", "USER_FETCH_FAILED", err.Error())
    http.Error(w, "Internal error", http.StatusInternalServerError)
    return
}
```

### 4.2 Query liste avec filtres dynamiques (whitelist)

```go
var allowedSorts = map[string]string{
    "name_asc":  "name ASC",
    "name_desc": "name DESC",
    "date_desc": "created_at DESC",
}
sortKey := r.URL.Query().Get("sort")
sortClause, ok := allowedSorts[sortKey]
if !ok {
    sortClause = "created_at DESC"
}

query := fmt.Sprintf(`
    SELECT id, name, status, created_at
    FROM smsi_assets
    WHERE client_id = $1
      AND ($2 = '' OR status = $2)
    ORDER BY %s
    LIMIT $3 OFFSET $4
`, sortClause)

rows, err := db.Query(query, clientID, statusFilter, limit, offset)
if err != nil {
    LogSystemEvent("ERROR", "DB", "ASSETS_LIST_FAILED", err.Error())
    return nil, err
}
defer rows.Close()
```

### 4.3 UPSERT avec ON CONFLICT (idempotent)

```go
query := `
    INSERT INTO rag_documents (id, content, embedding, source, source_type, metadata)
    VALUES ($1, $2, $3::vector, $4, $5, $6)
    ON CONFLICT (id) DO UPDATE SET
        content = EXCLUDED.content,
        embedding = EXCLUDED.embedding,
        metadata = rag_documents.metadata || EXCLUDED.metadata,  -- JSONB merge
        updated_at = NOW()
    RETURNING id, created_at, updated_at
`
var (
    id        string
    createdAt, updatedAt time.Time
)
err := db.QueryRow(query, docID, content, embeddingStr, source, srcType, metadataJSON).
    Scan(&id, &createdAt, &updatedAt)
```

### 4.4 CTE + window function (top-N par categorie)

```sql
-- Top 5 critical CVEs per vendor (LIA-SEC pattern)
WITH ranked AS (
    SELECT
        cve_id,
        cvss_score,
        affected_vendors,
        ROW_NUMBER() OVER (
            PARTITION BY (affected_vendors->>0)
            ORDER BY cvss_score DESC, published_date DESC
        ) AS rn
    FROM cve_nvd_data
    WHERE cvss_score >= 9.0
      AND published_date >= NOW() - INTERVAL '90 days'
)
SELECT cve_id, cvss_score, affected_vendors
FROM ranked
WHERE rn <= 5;
```

### 4.5 Aggregation set-based (pas N+1)

```sql
-- ANTI-PATTERN : N+1 query (1 query par user)
-- SELECT count(*) FROM smsi_assets WHERE owner_id = $1

-- CORRECT : single aggregation
SELECT
    u.id, u.name,
    COALESCE(stats.total_assets, 0)    AS total_assets,
    COALESCE(stats.critical_assets, 0) AS critical_assets
FROM users u
LEFT JOIN (
    SELECT
        owner_id,
        COUNT(*)                                          AS total_assets,
        COUNT(*) FILTER (WHERE criticality = 'critical')  AS critical_assets
    FROM smsi_assets
    WHERE status != 'archived'
    GROUP BY owner_id
) stats ON stats.owner_id = u.id
WHERE u.client_id = $1;
```

### 4.6 EXISTS plutot que COUNT (presence check)

```sql
-- ANTI-PATTERN : count entire table
SELECT COUNT(*) > 0 FROM cve_nvd_data WHERE cve_id = $1;

-- CORRECT : short-circuit
SELECT EXISTS (SELECT 1 FROM cve_nvd_data WHERE cve_id = $1);
```

### 4.7 JSONB query + index GIN

```sql
-- Recherche dans metadata JSONB (necessite index GIN)
-- CREATE INDEX idx_rag_documents_metadata_gin ON rag_documents USING GIN (metadata jsonb_path_ops);

SELECT id, content, metadata->>'cvss' AS cvss, metadata->>'vendor' AS vendor
FROM rag_documents
WHERE metadata @> '{"severity": "CRITICAL"}'   -- index GIN utilise
  AND (metadata->>'cvss')::numeric >= 9.0
LIMIT 10;
```

### 4.8 Recursive CTE (hierarchie ATT&CK)

```sql
-- Trouver toutes les sub-techniques sous une parent technique
WITH RECURSIVE chain AS (
    SELECT mitre_id, name, parent_technique, 1 AS depth
    FROM mitre_techniques
    WHERE mitre_id = $1
    UNION ALL
    SELECT mt.mitre_id, mt.name, mt.parent_technique, c.depth + 1
    FROM mitre_techniques mt
    JOIN chain c ON mt.parent_technique = c.mitre_id
    WHERE c.depth < 5  -- garde-fou
)
SELECT mitre_id, name, depth FROM chain ORDER BY depth, mitre_id;
```

### 4.9 Soft-delete et audit

```sql
-- Soft delete LIA-SEC (jamais DELETE direct sur table audit-able)
UPDATE smsi_assessments
SET status = 'archived',
    archived_at = NOW(),
    archived_by = $2
WHERE id = $1
  AND status != 'archived'  -- idempotent
RETURNING id;
```

### 4.10 Transaction avec rollback Go

```go
tx, err := db.BeginTx(ctx, nil)
if err != nil {
    LogSystemEvent("ERROR", "DB", "TX_BEGIN_FAILED", err.Error())
    return err
}
defer func() {
    if p := recover(); p != nil {
        tx.Rollback() // #nosec G104 -- best effort
        panic(p)
    }
}()

if _, err := tx.ExecContext(ctx, queryA, args...); err != nil {
    tx.Rollback() // #nosec G104
    LogSystemEvent("ERROR", "DB", "TX_QUERY_A_FAILED", err.Error())
    return err
}
if _, err := tx.ExecContext(ctx, queryB, args...); err != nil {
    tx.Rollback() // #nosec G104
    LogSystemEvent("ERROR", "DB", "TX_QUERY_B_FAILED", err.Error())
    return err
}
return tx.Commit()
```

### 4.11 Vector similarity (pgvector, pour info -- prefer `/rag-architect`)

```sql
-- Cosine similarity search (HNSW index automatic)
SELECT id, content, source, 1 - (embedding <=> $1::vector) AS sim
FROM rag_documents
WHERE source_type = ANY($2::text[])
  AND 1 - (embedding <=> $1::vector) >= $3
ORDER BY embedding <=> $1::vector ASC
LIMIT $4;
```

---

## 5. Anti-patterns interdits (refus immediat)

| INTERDIT | A la place |
|----------|-----------|
| `fmt.Sprintf` avec `%s` interpoler une string user | placeholders `$1, $2` + `db.Query(q, args...)` |
| `SELECT *` en code production | nommer les colonnes explicitement |
| `for { db.Query(...) }` sur ID -- N+1 query | seul `JOIN` ou `IN ($1, $2, ...)` ou `= ANY($1::uuid[])` |
| `db.Query` sans `defer rows.Close()` | `defer rows.Close()` immediatement apres |
| `sql.Open` dans un handler | `db := getDB()` (pool partagé) |
| `DROP TABLE` ou `DELETE FROM` sans `WHERE` | toujours `WHERE id = $1` ou soft-delete |
| `TRUNCATE` direct | TRUNCATE `WITH RESTART` + transaction + LogSystemEvent |
| `FLOAT` / `REAL` pour CVSS, EPSS, scores | `NUMERIC(4,2)` / `DECIMAL` |
| `TIMESTAMP` sans timezone | `TIMESTAMPTZ` |
| `JSON` (texte seul) | `JSONB` (binaire indexable) |
| Hardcode `'lia_admin'` ou password | `$LIA_DB_PASS` env / `system_variables` (R5+R8) |
| `LIKE '%' || search || '%'` (no index) | `pg_trgm` index + `%>` operator OR full-text `to_tsvector` |
| `OFFSET 100000` (paginate enormous) | keyset pagination `WHERE id > $last_id ORDER BY id LIMIT 50` |
| `count(*) FROM giant_table` (full scan) | `pg_class.reltuples` estimate ou maintenir compteur |
| `UNION` (deduplication couteuse) | `UNION ALL` si dedup pas necessaire |
| Migration SQL sans `IF NOT EXISTS` | `CREATE TABLE IF NOT EXISTS` partout (idempotent) |
| `ALTER TABLE add column NOT NULL` sans default | risque ACCESS EXCLUSIVE long ; `ADD COLUMN ... DEFAULT` puis `NOT NULL` separe |
| INSERT massif row-by-row | `COPY FROM STDIN` ou `INSERT ... VALUES (...), (...), ... ($1,$2),(...)` batch |
| Logs SQL avec emoji ❌ ✅ | `[FAIL]` / `[OK]` (R10) |

---

## 6. Checklist avant commit (5 items)

- [ ] **Aucun `fmt.Sprintf` avec `%s` user** (R7) -- ou whitelist documente
- [ ] **`defer rows.Close()`** apres chaque `db.Query`
- [ ] **`LogSystemEvent("ERROR", "DB", ...)` sur chaque erreur** (R6)
- [ ] **HTTP 500 generique** cote utilisateur (jamais leak SQL ou err.Error() complet)
- [ ] **Test query** localement via `psql` avant compilation (`psql_lia` helper)

Pour requete > 10K rows ou > 50ms attendue : **ajouter `EXPLAIN ANALYZE`** dans le commit message OU invoquer `/postgres-pro` pour validation.

---

## 7. Helper psql_lia (pour test local)

Toute query peut etre testee avant le code Go via :

```bash
# .claude/CLAUDE.md helper pattern
LIA_DB_PASS="${LIA_DB_PASS:-${PGPASSWORD:-}}"
LIA_DB_USER="${LIA_DB_USER:-lia_admin}"
LIA_DB_NAME="${LIA_DB_NAME:-lia_scan}"

psql_lia() {
    PGPASSWORD="$LIA_DB_PASS" psql -h localhost -U "$LIA_DB_USER" -d "$LIA_DB_NAME" "$@"
}

# Tester une query
psql_lia -c "SELECT count(*) FROM rag_documents WHERE source_type='cve';"

# Tester un EXPLAIN
psql_lia -c "EXPLAIN ANALYZE SELECT ... FROM ..."

# Recuperer le schema d'une table
psql_lia -c "\d rag_documents"
```

---

## 8. Output template (sortie d'une session sql-pro)

```markdown
## SQL Query : <objectif> -- file.go:line

### Context
- Table(s) : ...
- Volume : ~X rows
- Pattern : SELECT/UPSERT/CTE/...
- User input : oui/non (si oui : `param`, validation `func()`)

### Query

```sql
-- objectif
SELECT ...
FROM ...
WHERE ...
```

### Go code

```go
query := `...`
rows, err := db.Query(query, args...)
if err != nil {
    LogSystemEvent("ERROR", "DB", "ACTION_FAILED", err.Error())
    ...
}
defer rows.Close()
```

### Index requis (si query > 10K rows)

```sql
CREATE INDEX IF NOT EXISTS idx_table_col ON table (col);
-- Migration : cmd/sigma_web/postgres/migrations/NNN_idx_table_col.sql
```

### Test local

```bash
psql_lia -c "EXPLAIN ANALYZE <query avec valeurs>"
```

### Checklist

- [ ] Parameterized (R7)
- [ ] defer rows.Close()
- [ ] LogSystemEvent error
- [ ] HTTP 500 generique
- [ ] Test psql OK
```

---

## 9. Score agentique attendu (>= 40/50)

| Critere | Min | Comment l'atteindre |
|---------|-----|---------------------|
| C1 Decomposition | 8/10 | Workflow 5 phases respecte (CONTEXT -> PATTERN -> WRITE -> WRAP -> VERIFY) |
| C2 Planification (THINK) | 9/10 | Verifier schema reel via psql AVANT ecriture (pas inventer colonnes) |
| C3 Replanification | 7/10 | Si EXPLAIN signale Seq Scan -> rewrite query OU pass main a `/postgres-pro` |
| C4 Outillage | 8/10 | psql_lia + EXPLAIN ANALYZE + grep schema_migrations AVANT code |
| C5 Tracabilite | 8/10 | Migration NNN si index ajoute, query commentee dans le Go, log d'erreur |

---

## 10. Cross-references LIA-SEC

| Si je dois... | J'invoque... |
|---------------|--------------|
| Designer une nouvelle table / migration majeure | `/db-schema-designer` |
| Optimiser une query lente apres EXPLAIN | `/postgres-pro` |
| Ajouter un nouveau source_type RAG ou tuner pgvector | `/rag-architect` |
| Auditer une query existante pour SQL injection | `/security-reviewer` |
| Wrap la query dans un handler Go propre | `/golang-pro` (interface, contexte, error handling) |
| Garantir auth + rate-limit autour de la query | `/secure-code-guardian` |
| Documenter le module qui contient la query | `/doc-code` |
