---
name: sql-pro
description: Idiomatic SQL writer for inspect_ia_agents daily work -- writes queries, CTEs, window functions, joins, aggregations, set-based operations with parameterized statements over the `sqlx` event-store layer (SQLite Phase 1 -> PostgreSQL Phase 2 behind the `EventStore` trait). Invoke AVANT toute ecriture de SQL dans le code Rust (event store impl, read-model projections, queries), dans les migrations courtes (sans changement schema majeur), ou quand on lit/transforme des donnees existantes. Differe de `/db-schema-designer` (DESIGN nouveau schema + migration NNN) et `/postgres-pro` (optimisation perf avancee, EXPLAIN, VACUUM, replication) -- ici c'est ECRITURE QUOTIDIENNE de SQL idiomatique, parameterized, set-based, avec respect strict de R7 (SQL injection prevention), R5 (config source unique) et des invariants I1 (append-only) / I4 (ordre de replay deterministe).
license: MIT (upstream Jeffallan/claude-skills) -- adapted for inspect_ia_agents
metadata:
  author: inspect_ia_agents
  upstream: https://github.com/Jeffallan/claude-skills/blob/main/skills/sql-pro/SKILL.md
  version: "2.0.0-inspect_ia_agents"
  domain: language
  triggers: ecrire SQL, write SQL, query Postgres, query SQLite, sqlx, JOIN, CTE, WITH, window function, GROUP BY, aggregation, parameterized query, prepared statement, SELECT, INSERT, UPDATE, DELETE, MERGE, UPSERT, ON CONFLICT, RETURNING, query_as, fetch_one, fetch_all, execute, JSONB query, ARRAY operation, recursive query, lateral join, CASE WHEN, COALESCE
  role: specialist
  scope: implementation
  output-format: code (Rust + SQL embedded)
  related-skills: db-schema-designer, postgres-pro, rust-best-practices, secure-code-guardian
  enforces-rules: R5, R6, R7, R10, R12, R16
---

# SQL Pro (inspect_ia_agents adaptation)

> **Quand m'invoquer** : ecriture de SQL quotidien dans le code Rust
> inspect_ia_agents (event store, read-model projections, queries forensiques).
> SELECT/INSERT/UPDATE/DELETE/MERGE, JOINs, CTEs, window functions, JSONB
> queries, ARRAY operations, RETURNING, ON CONFLICT, parameterized statements.
>
> **NE PAS m'invoquer pour** :
> - Design d'un NOUVEAU schema (tables, indexes, migrations majeures) -> `/db-schema-designer`
> - EXPLAIN ANALYZE, perf monitoring, VACUUM tuning, replication -> `/postgres-pro`
> - Audit securite SQL injection POST-ecriture -> `/security-reviewer`
>
> **Rappel invariants (event store)** : le log d'evenements est append-only (I1) --
> JAMAIS d'`UPDATE`/`DELETE` sur la table `events` ; une correction = un evenement
> compensatoire. L'ordre de replay est porte par `seq` monotone (I4). Detail :
> `.claude/rules/event-store-decision.md`, `.claude/rules/invariants.md`.
>
> **Toujours combinable** : `/sql-pro` ecrit la query, `/postgres-pro` la tune
> apres EXPLAIN, `/secure-code-guardian` valide la sanitization.

---

## 0. Stack inspect_ia_agents -- contexte obligatoire

| Item | Valeur |
|------|--------|
| RDBMS | **SQLite** (Phase 1, mono-hote) -> **PostgreSQL** (Phase 2, distribue) derriere le trait `EventStore` (cf `.claude/rules/event-store-decision.md`) |
| Connection string | via `INSPECT_IA_AGENTS_DATABASE_URL` / `INSPECT_IA_AGENTS_EVENT_STORE=sqlite\|postgres` (R5/R8) -- jamais en dur |
| Event log | table `events` INSERT-only, `seq INTEGER PRIMARY KEY AUTOINCREMENT` (ordre total monotone, I4) |
| Immutabilite | ENFORCEE par triggers anti-`UPDATE`/`DELETE` (I1), pas seulement par discipline |
| Integrite | hash chain `prev_hash` + `side_effect_hash` calcules a l'append |
| Driver Rust | `sqlx` (queries verifiees a la compilation ; supporte SQLite et PostgreSQL) |
| Pragmas SQLite | `PRAGMA journal_mode=WAL;` `PRAGMA foreign_keys=ON;` |
| Naming | `snake_case` partout (tables, colonnes, indexes, contraintes) |
| PK convention | `seq` monotone (ordre) + `event_id` ULID/UUIDv7 (identite ordonnable) |
| Timestamps | en Postgres `TIMESTAMPTZ` ; le `timestamp` d'un evenement est un INPUT capture, jamais `now()` dans la decision (I4) |
| JSON | `JSONB` en Postgres (index GIN si recherche) ; `TEXT`/`json` en SQLite |
| Acces SQL | UNIQUEMENT derriere le trait `EventStore` -- aucune query SQLite/PG directe hors de l'impl du trait |
| Logger | `tracing` structure (spans + fields), correle par `event_id`/`agent_id` (R6) |
| Migrations | `migrations/NNN_*.sql` (numerotees, idempotentes) via `sqlx migrate` |
| Dialect portable | une query doit fonctionner SQLite ET PostgreSQL ; isoler les specificites de dialecte dans l'impl du trait |

---

## 1. R7 SQL Injection Prevention (ABSOLU, BLOQUANT)

### La regle d'or

```rust
// INTERDIT -- format!() injection direct dans la query
let query = format!("SELECT * FROM events WHERE agent_id = '{agent_id}'"); // VULNERABLE

// CORRECT -- bind parameters (sqlx echappe et type-check a la compilation)
let rows = sqlx::query_as::<_, EventRow>(
    "SELECT seq, event_id, agent_id FROM events WHERE agent_id = $1",
)
.bind(&agent_id)
.fetch_all(pool)
.await?;
```

### Cas legitimes de `format!()` dans une query

Trois cas seulement ou `format!()` dans une query est OK :

1. **Format `{}` int APRES validation/clamp**
```rust
let days: i64 = parse_days(req).clamp(1, 365); // i64 garanti dans la plage
let query = format!("WHERE timestamp >= NOW() - INTERVAL '{days} days'");
// {} sur un i64 valide ne peut pas injecter
```

2. **Nom de colonne issu d'une whitelist verifiee**
```rust
const ALLOWED_COLUMNS: &[&str] = &["agent_id", "action_type", "target_system"];

if !ALLOWED_COLUMNS.contains(&col) {
    tracing::warn!(column = %col, "SQL_INJECTION_ATTEMPT: invalid column blocked");
    return Err(StoreError::InvalidColumn(col.to_string()));
}
let query = format!("SELECT seq, {col} FROM events WHERE seq = $1");
```

3. **Nom de table fixe par une whitelist de read-models**
```rust
let table = format!("projection_{suffix}");
const ALLOWED: &[&str] = &["projection_approvals", "projection_risk"];
if !ALLOWED.contains(&table.as_str()) {
    return Err(StoreError::InvalidTable(table));
}
let query = format!("SELECT count(*) FROM {table}");
```

### Patterns INTERDITS (refus immediat)

```rust
// INTERDIT 1 -- string concat
let query = "SELECT * FROM events WHERE agent_id = '".to_string() + &agent_id + "'";

// INTERDIT 2 -- format! interpolant une string user (string injection direct)
let query = format!("WHERE target_system = '{target}'");

// INTERDIT 3 -- whitelist contournee (tri pilote par l'utilisateur)
let query = format!("ORDER BY {}", req.sort_param());

// INTERDIT 4 -- LIKE concatenation
let query = format!("WHERE action_type LIKE '%{search}%'");
// Correct : "WHERE action_type LIKE $1" puis .bind(format!("%{search}%"))
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

[4] WRAP en Rust (derriere le trait EventStore)
    - utiliser le `Pool` partage du store, ne pas re-ouvrir une connexion ad-hoc
    - `query_as::<_, Row>(...)` map directement dans une struct typee (`FromRow`), pas de scan manuel
    - propager l'erreur avec `?` ; type d'erreur explicite (`thiserror`), pas de `.unwrap()`/`.expect()` en prod (R7)
    - log d'erreur structure : `tracing::error!(error = %e, %event_id, "...")` (R6)
    - cote frontiere (Gateway) : erreur generique vers l'appelant, ne JAMAIS leak le SQL/erreur driver

[5] VERIFY
    - sqlx verifie les queries a la compilation -- `cargo build` doit etre propre
    - Test query directement via la CLI du moteur (`sqlite3` / `psql`) avant le code Rust
    - EXPLAIN si SELECT touche > 10K rows
    - Check qu'il n'y a pas de scan complet sur une table volumineuse
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
> En inspect_ia_agents, **seuls SQLite (Phase 1) et PostgreSQL (Phase 2)
> comptent**. Une query doit rester portable entre les deux ; isoler toute
> specificite de dialecte dans l'impl du trait `EventStore`. Quand une
> reference montre du SQL Server (`TOP`, `[brackets]`, `GETDATE()`) ou MySQL
> (`LIMIT a, b`, backticks), traduire en SQL standard / PostgreSQL idiomatique
> avant utilisation, et verifier que l'equivalent SQLite tient.

---

## 4. Patterns inspect_ia_agents frequents (copy-friendly)

> Domaine : la table append-only `events` (modele canonique `AgentActionEvent`),
> les read-models/projections reconstruits depuis le log, et les queries
> forensiques. Toutes ces queries vivent DERRIERE le trait `EventStore`.

### 4.1 Lecture simple parameterized (un evenement par id)

```rust
// Read one event by event_id
let row = sqlx::query_as::<_, EventRow>(
    "SELECT seq, event_id, timestamp, agent_id, action_type, target_system, \
            policy_decision, approval_state \
     FROM events \
     WHERE event_id = $1",
)
.bind(&event_id)
.fetch_optional(pool)            // None si absent, pas d'erreur
.await
.map_err(|e| {
    tracing::error!(error = %e, %event_id, "EVENT_FETCH_FAILED");
    StoreError::Query(e)
})?;
```

### 4.2 Query liste avec filtres dynamiques (whitelist)

```rust
// Sort whitelisted; user input only via bind parameters
let sort_clause = match sort_key {
    "seq_asc"  => "seq ASC",
    "seq_desc" => "seq DESC",
    _          => "seq ASC",      // default deterministe (I4)
};

let query = format!(
    "SELECT seq, event_id, agent_id, action_type, policy_decision \
     FROM events \
     WHERE agent_id = $1 \
       AND ($2 = '' OR action_type = $2) \
     ORDER BY {sort_clause} \
     LIMIT $3 OFFSET $4"
);

let rows = sqlx::query_as::<_, EventRow>(&query)
    .bind(&agent_id)
    .bind(&action_filter)
    .bind(limit)
    .bind(offset)
    .fetch_all(pool)
    .await
    .map_err(|e| {
        tracing::error!(error = %e, %agent_id, "EVENTS_LIST_FAILED");
        StoreError::Query(e)
    })?;
```

### 4.3 UPSERT avec ON CONFLICT (idempotent -- read-model, PAS le log)

```rust
// Read-models/projections are rebuildable and MAY be upserted.
// The append-only `events` log is NEVER upserted (I1).
let query = r#"
    INSERT INTO projection_approvals (agent_id, pending_count, last_event_seq, metadata)
    VALUES ($1, $2, $3, $4)
    ON CONFLICT (agent_id) DO UPDATE SET
        pending_count  = EXCLUDED.pending_count,
        last_event_seq = EXCLUDED.last_event_seq,
        metadata       = projection_approvals.metadata || EXCLUDED.metadata
    RETURNING agent_id, last_event_seq
"#;
let updated = sqlx::query_as::<_, ProjectionRow>(query)
    .bind(&agent_id)
    .bind(pending_count)
    .bind(last_event_seq)
    .bind(&metadata_json)
    .fetch_one(pool)
    .await?;
```

### 4.4 CTE + window function (dernier evenement par agent)

```sql
-- Latest event per agent, ordered by the monotone seq (deterministic, I4)
WITH ranked AS (
    SELECT
        seq,
        event_id,
        agent_id,
        action_type,
        policy_decision,
        ROW_NUMBER() OVER (
            PARTITION BY agent_id
            ORDER BY seq DESC
        ) AS rn
    FROM events
)
SELECT seq, event_id, agent_id, action_type, policy_decision
FROM ranked
WHERE rn = 1;
```

### 4.5 Aggregation set-based (pas N+1)

```sql
-- ANTI-PATTERN : N+1 query (1 query par agent)
-- SELECT count(*) FROM events WHERE agent_id = $1

-- CORRECT : single aggregation -- decisions par agent
SELECT
    agent_id,
    COUNT(*)                                              AS total_events,
    COUNT(*) FILTER (WHERE policy_decision = 'deny')      AS deny_count,
    COUNT(*) FILTER (WHERE approval_state = 'pending')    AS pending_count
FROM events
GROUP BY agent_id;
```

### 4.6 EXISTS plutot que COUNT (presence check)

```sql
-- ANTI-PATTERN : count entire table
SELECT COUNT(*) > 0 FROM events WHERE event_id = $1;

-- CORRECT : short-circuit
SELECT EXISTS (SELECT 1 FROM events WHERE event_id = $1);
```

### 4.7 JSON payload query (JSONB + index GIN en Postgres)

```sql
-- Postgres: filter on the canonical event payload (needs a GIN index)
-- CREATE INDEX idx_events_payload_gin ON events USING GIN (payload jsonb_path_ops);

SELECT seq, event_id, agent_id, payload->>'resource' AS resource
FROM events
WHERE payload @> '{"action_type": "merge_pr"}'   -- GIN index used
  AND policy_decision = 'escalate'
LIMIT 10;
-- SQLite Phase 1 equivalent: json_extract(payload, '$.action_type') = 'merge_pr'
```

### 4.8 Recursive CTE (chaine de compensation)

```sql
-- Walk the chain of compensating events that correct a prior one (I1: no mutation)
WITH RECURSIVE chain AS (
    SELECT event_id, corrects_event_id, 1 AS depth
    FROM events
    WHERE event_id = $1
    UNION ALL
    SELECT e.event_id, e.corrects_event_id, c.depth + 1
    FROM events e
    JOIN chain c ON e.corrects_event_id = c.event_id
    WHERE c.depth < 16  -- garde-fou
)
SELECT event_id, corrects_event_id, depth FROM chain ORDER BY depth, event_id;
```

### 4.9 Correction via evenement compensatoire (JAMAIS d'UPDATE/DELETE, I1)

```sql
-- WRONG (I1 violation): UPDATE events SET payload = ... WHERE event_id = $1;
-- RIGHT: append a NEW compensating event that references the one it corrects.
INSERT INTO events (event_id, timestamp, agent_id, action_type, payload, corrects_event_id, prev_hash, side_effect_hash)
VALUES ($1, $2, $3, 'compensation', $4, $5, $6, $7)
RETURNING seq, event_id;
```

### 4.10 Transaction avec rollback Rust (sqlx)

```rust
// sqlx transaction: explicit commit; drop without commit rolls back automatically.
let mut tx = pool.begin().await.map_err(|e| {
    tracing::error!(error = %e, "TX_BEGIN_FAILED");
    StoreError::Query(e)
})?;

sqlx::query("INSERT INTO events (event_id, agent_id, action_type, prev_hash) VALUES ($1, $2, $3, $4)")
    .bind(&event_id).bind(&agent_id).bind(&action_type).bind(&prev_hash)
    .execute(&mut *tx)
    .await
    .map_err(|e| { tracing::error!(error = %e, %event_id, "TX_APPEND_FAILED"); StoreError::Query(e) })?;

sqlx::query("UPDATE projection_approvals SET last_event_seq = $1 WHERE agent_id = $2")
    .bind(last_seq).bind(&agent_id)
    .execute(&mut *tx)
    .await
    .map_err(|e| { tracing::error!(error = %e, %agent_id, "TX_PROJECTION_FAILED"); StoreError::Query(e) })?;

tx.commit().await.map_err(StoreError::Query)?;
```

### 4.11 Replay : lire le log dans l'ordre (I4)

```sql
-- Read the event stream from a checkpoint, in stable monotone seq order.
-- This ordering is what makes replay deterministic (I4).
SELECT seq, event_id, timestamp, agent_id, action_type, target_system, payload, policy_decision
FROM events
WHERE seq > $1
ORDER BY seq ASC
LIMIT $2;
```

---

## 5. Anti-patterns interdits (refus immediat)

| INTERDIT | A la place |
|----------|-----------|
| `format!` avec `{}` interpolant une string user | bind parameters `$1, $2` + `.bind(arg)` (sqlx) |
| `UPDATE` / `DELETE` sur la table `events` (viole I1) | evenement compensatoire (`corrects_event_id`), jamais de mutation |
| `now()` dans le chemin de decision (viole I4) | `timestamp` capture en amont = INPUT de l'evenement |
| `SELECT *` en code production | nommer les colonnes explicitement |
| `for { fetch_all(...) }` sur ID -- N+1 query | `JOIN` ou `IN ($1, $2, ...)` ou `= ANY($1::text[])` (Postgres) |
| connexion `sqlx` ad-hoc dans la logique metier | le `Pool` partage derriere le trait `EventStore` |
| query SQL directe hors de l'impl du trait `EventStore` | toute query passe par le trait (decouplage, replay) |
| `DROP TABLE` ou `DELETE FROM` sans `WHERE` | sur les read-models seulement ; jamais sur `events` (I1) |
| `TIMESTAMP` sans timezone (Postgres) | `TIMESTAMPTZ` |
| `JSON` (texte seul, Postgres) | `JSONB` (binaire indexable) |
| Hardcode connection string ou password | `INSPECT_IA_AGENTS_DATABASE_URL` env (R5+R8) |
| `LIKE '%' || search || '%'` (no index) | `pg_trgm` index + operator OR full-text `to_tsvector` (Postgres) |
| `OFFSET 100000` (paginate enormous) | keyset pagination `WHERE seq > $last_seq ORDER BY seq LIMIT 50` |
| `count(*) FROM giant_table` (full scan) | `pg_class.reltuples` estimate (Postgres) ou compteur maintenu |
| `UNION` (deduplication couteuse) | `UNION ALL` si dedup pas necessaire |
| Migration SQL sans `IF NOT EXISTS` | `CREATE TABLE IF NOT EXISTS` partout (idempotent) |
| Query specifique a un seul dialecte sans equivalent | garder la portabilite SQLite <-> PostgreSQL, sinon l'isoler dans l'impl du trait |
| INSERT massif row-by-row | batch `INSERT ... VALUES ($1,$2),($3,$4),...` (ou `COPY` en Postgres) |
| Logs SQL avec emoji | `[FAIL]` / `[OK]` (R10) |

---

## 6. Checklist avant commit (5 items)

- [ ] **Aucun `format!` interpolant une string user** (R7) -- ou whitelist documente
- [ ] **Aucun `UPDATE`/`DELETE` sur `events`** (I1) -- correction = evenement compensatoire
- [ ] **Aucun `now()` dans le chemin de decision** (I4) -- `timestamp` capture en INPUT
- [ ] **Query derriere le trait `EventStore`** (pas de SQL direct hors de l'impl)
- [ ] **`tracing::error!(error = %e, ...)` sur chaque erreur** (R6) ; pas de `.unwrap()`/`.expect()` en prod (R7)
- [ ] **Erreur generique** cote appelant (jamais leak SQL ou message driver complet)
- [ ] **Test query** localement via `sqlite3` / `psql` avant le code Rust ; `cargo build` propre (sqlx compile-check)

Pour requete > 10K rows ou > 50ms attendue : **ajouter `EXPLAIN ANALYZE`** dans le commit message OU invoquer `/postgres-pro` pour validation.

---

## 7. Test local (avant le code Rust)

Toute query peut etre testee avant le code Rust, selon la phase active.

Phase 1 (SQLite) -- via la CLI `sqlite3` sur le fichier de l'event store :

```bash
# Tester une query
sqlite3 data/events.db "SELECT count(*) FROM events WHERE policy_decision='deny';"

# Inspecter le schema d'une table
sqlite3 data/events.db ".schema events"

# Verifier le plan
sqlite3 data/events.db "EXPLAIN QUERY PLAN SELECT ... FROM events WHERE seq > 0;"
```

Phase 2 (PostgreSQL) -- via `psql` sur la connexion configuree :

```bash
# Connexion via l'URL configuree (R5/R8), jamais de password en dur
psql "$INSPECT_IA_AGENTS_DATABASE_URL" -c "SELECT count(*) FROM events WHERE policy_decision='deny';"
psql "$INSPECT_IA_AGENTS_DATABASE_URL" -c "EXPLAIN ANALYZE SELECT ... FROM events"
psql "$INSPECT_IA_AGENTS_DATABASE_URL" -c "\d events"
```

`sqlx` verifie en plus les queries a la compilation : un `cargo build` propre
attrape un mismatch de colonne/type avant tout run.

---

## 8. Output template (sortie d'une session sql-pro)

```markdown
## SQL Query : <objectif> -- file.rs:line

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

### Rust code (sqlx, derriere le trait EventStore)

```rust
let rows = sqlx::query_as::<_, Row>("...")
    .bind(arg)
    .fetch_all(pool)
    .await
    .map_err(|e| {
        tracing::error!(error = %e, "ACTION_FAILED");
        StoreError::Query(e)
    })?;
```

### Index requis (si query > 10K rows)

```sql
CREATE INDEX IF NOT EXISTS idx_events_col ON events (col);
-- Migration : migrations/NNN_idx_events_col.sql (sqlx migrate, idempotent)
```

### Test local

```bash
# Phase 1 SQLite
sqlite3 data/events.db "EXPLAIN QUERY PLAN <query>"
# Phase 2 PostgreSQL
psql "$INSPECT_IA_AGENTS_DATABASE_URL" -c "EXPLAIN ANALYZE <query avec valeurs>"
```

### Checklist

- [ ] Parameterized (R7)
- [ ] Pas d'UPDATE/DELETE sur `events` (I1)
- [ ] Pas de `now()` dans la decision (I4)
- [ ] tracing::error! structure
- [ ] Erreur generique cote appelant
- [ ] Test sqlite3/psql OK
```

---

## 9. Score agentique attendu (>= 40/50)

| Critere | Min | Comment l'atteindre |
|---------|-----|---------------------|
| C1 Decomposition | 8/10 | Workflow 5 phases respecte (CONTEXT -> PATTERN -> WRITE -> WRAP -> VERIFY) |
| C2 Planification (THINK) | 9/10 | Verifier schema reel via sqlite3/psql AVANT ecriture (pas inventer colonnes) |
| C3 Replanification | 7/10 | Si EXPLAIN signale un scan complet -> rewrite query OU pass main a `/postgres-pro` |
| C4 Outillage | 8/10 | sqlite3/psql + EXPLAIN + `cargo build` (sqlx compile-check) AVANT code |
| C5 Tracabilite | 8/10 | Migration NNN si index ajoute, query commentee dans le Rust, log d'erreur structure |

---

## 10. Cross-references inspect_ia_agents

| Si je dois... | J'invoque... |
|---------------|--------------|
| Designer une nouvelle table / migration majeure | `/db-schema-designer` |
| Optimiser une query lente apres EXPLAIN | `/postgres-pro` |
| Auditer une query existante pour SQL injection | `/security-reviewer` |
| Wrap la query dans une impl Rust propre (trait, erreurs) | `/rust-best-practices` (ownership, `Result`, error handling) |
| Garantir auth + rate-limit autour de la query | `/secure-code-guardian` |
| Documenter le module qui contient la query | `/doc-code` |
