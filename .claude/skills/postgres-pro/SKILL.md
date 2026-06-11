---
name: postgres-pro
description: Use when optimizing PostgreSQL queries, configuring replication, or implementing advanced database features. Invoke for EXPLAIN analysis, JSONB operations, extension usage, VACUUM tuning, performance monitoring.
license: MIT
metadata:
  author: https://github.com/Jeffallan
  version: "1.1.0"
  domain: infrastructure
  triggers: PostgreSQL, Postgres, EXPLAIN ANALYZE, pg_stat, JSONB, streaming replication, logical replication, VACUUM, PostGIS, pgvector
  role: specialist
  scope: implementation
  output-format: code
  related-skills: database-optimizer, devops-engineer, sre-engineer
---

# PostgreSQL Pro (LIA-SEC Edition)

## LIA-SEC Adaptations (MANDATORY)

- **Stack** : PostgreSQL 17, user `lia_admin`, base `lia_scan`, 268 tables, 332K CVE rows,
  extensions : `pgvector` (embeddings 384 dims `all-minilm`), `pg_trgm`, `btree_gin`
- **Credentials** : NEVER hardcode ; read from systemd unit env `DATABASE_URL`
  (`systemctl cat lia-backend | grep Environment=DATABASE_URL`) or `$LIA_DB_PASS` / `psql_lia()` helper
  (see `.claude/rules/no-hardcoded-secrets.md`)
- **Schema changes** : TOUJOURS passer par une migration `cmd/sigma_web/migrations/NNN_*.sql` --
  jamais d'ALTER direct en prod. Utiliser `/db-schema-designer` pour créer la migration
- **JSONB + GIN** : pour `liaprobe_agent_results`, `ui_help_content.content`, `unified_logs.metadata`,
  etc. Index GIN systématique quand recherche dans JSONB
- **No FLOAT** for numerics (scores, amounts) -- use NUMERIC(p,s) or INTEGER (convention LIA-SEC)
- **UUID PK + TIMESTAMPTZ** by default
- **R5** : toute config tunable vit dans `system_variables` (éditable UI Admin > Variables),
  pas dans le code
- **unified_logs** : table 244M rows -- R16, attention au lock ACCESS EXCLUSIVE sur
  `CREATE INDEX IF NOT EXISTS` au boot backend (voir `backend-single-instance.md`)
- **Backups** : cron 2h AM, 7j retention, `/opt/lia-sec/backups/` -- ne pas supprimer un
  `.dump` sans en garder 2 de plus
- **n8n pipeline** : enrichissement CVE (NVD + EPSS + KEV + Exploit-DB) tourne via n8n --
  coordonner avec `/rag-architect` si tu touches aux tables RAG
- **Companion skills** : `/db-schema-designer` (schema + migration), `/rag-architect` (pipeline
  RAG pgvector), `/debug-go` (SQL errors côté backend)

---

## When to Use This Skill

- Analyzing and optimizing slow queries with EXPLAIN
- Implementing JSONB storage and indexing strategies
- Setting up streaming or logical replication
- Configuring and using PostgreSQL extensions
- Tuning VACUUM, ANALYZE, and autovacuum
- Monitoring database health with pg_stat views
- Designing indexes for optimal performance

## Decomposition des sous-taches

Au demarrage, decomposer toute demande en sous-taches independantes :

- [ ] Sous-tache 1 : reads / greps pour cartographier tables, indexes, volume, context existant
- [ ] Sous-tache 2 : `EXPLAIN (ANALYZE, BUFFERS)` sur la requete cible -- identifier le bottleneck reel
- [ ] Sous-tache 3 : concevoir et appliquer le fix (index, réécriture query, VACUUM, tuning autovacuum)
- [ ] Sous-tache 4 : dry-run migration si DDL implique (via `scripts/psql_dry_run.sh`)
- [ ] Sous-tache 5 : verification post-fix (`EXPLAIN` avant/apres, `pg_stat_user_tables`, latence mesurée)
- [ ] Sous-tache 6 : doc + `LogSystemEvent` si changement de comportement observable cote backend

Utiliser `TaskCreate` pour tracker si > 3 sous-taches.

## Plan d'execution

Pour toute optimisation non triviale (> 2 tables, migration DDL, ou replication) :

1. Creer `_alire/tracking/PLAN_POSTGRES_PRO_{FEATURE}_{YYYY-MM-DD}.md` avant d'ecrire une ligne.
2. Template : `_alire/tracking/PLAN_TEMPLATE.md`.
3. Cocher chaque sous-tache a la completion.
4. Si replanification : Status -> REPLANIFIE + lien vers nouveau plan.

Pour une optimisation ponctuelle (1 index, 1 query rewrite) : plan inline suffit.

## Adaptation et replanification

Si 2 etapes consecutives echouent (ex: index n'est pas utilise apres creation, VACUUM ne reduit pas le bloat) :

- STOP
- Invoquer `/replan` -> produit `PLAN_POSTGRES_PRO_*_REPLAN_*.md`
- NE PAS improviser un contournement

Declencheurs typiques :
- `EXPLAIN` apres creation d'index montre toujours un Seq Scan -> REPLAN (index partiel ? statistiques obsoletes ? requete non SARGable ?)
- Dry-run migration echoue -> REPLAN (verifier Pattern A R27, contrainte FK, lock)
- VACUUM VERBOSE signale toujours du bloat apres execution -> REPLAN (autovacuum trop lent ? wrapping XID ?)
- Un fix introduit un nouveau bottleneck (`pg_stat_statements`) -> REPLAN

## Outils declares

| Outil | Usage | Retry policy |
|-------|-------|--------------|
| `Read`, `Grep`, `Glob` | Cartographier handlers Go, migrations existantes, schema | N/A |
| `Bash psql_lia()` | Executer EXPLAIN / pg_stat / VACUUM / queries de diagnostic | echec -> verifier connexion / credentials |
| `Bash scripts/psql_dry_run.sh` | Dry-run migration Pattern A (R27) avant application | echec (exit 3) -> corriger la migration, jamais ignorer |
| `Write`, `Edit` | Creer/modifier `cmd/sigma_web/migrations/NNN_*.sql` | N/A |
| `TaskCreate` | Tracking si > 3 sous-taches | N/A |
| `Skill(db-schema-designer)` | Conception schema + migration NNN_*.sql | Obligatoire pour nouveau module |
| `Skill(sql-pro)` | Réécriture queries dans handlers Go | Obligatoire avant modification SQL applicatif |

Selection dynamique : outil choisi selon le contexte (diagnostic = psql_lia, DDL = dry-run d'abord, tuning = pg_stat).

## Tracabilite agentique

Logger dans `_alire/02_LOGS/Journals/decision_log.jsonl` chaque decision non triviale :

- Choix d'index type (B-tree vs GIN vs partiel) + justification EXPLAIN
- Rejet d'une approche (ex: index rejected -> réécriture CTE choisie)
- Decisions de migration (Pattern A vs backfill par batch, CONCURRENTLY ou pas)
- Trade-offs (perf vs lock duration, index size vs query speedup)

Format :
```json
{"timestamp":"...","session":"postgres-pro-{feature}","action":"...","reasoning":"...","alternatives_rejected":["..."],"outcome":"...","confidence":"high","plan_ref":"PLAN_POSTGRES_PRO_*.md"}
```

RETEX en fin de session si score agentique < 40/50 -> `_alire/02_LOGS/Journals/retex/RETEX_POSTGRES_PRO_YYYY-MM-DD.md`.

## Core Workflow

1. **Analyze performance** — Run `EXPLAIN (ANALYZE, BUFFERS)` to identify bottlenecks
2. **Design indexes** — Choose B-tree, GIN, GiST, or BRIN based on workload; verify with `EXPLAIN` before deploying
3. **Optimize queries** — Rewrite inefficient queries, run `ANALYZE` to refresh statistics
4. **Setup replication** — Streaming or logical based on requirements; monitor lag continuously
5. **Monitor and maintain** — Track VACUUM, bloat, and autovacuum via `pg_stat` views; verify improvements after each change

### End-to-End Example: Slow Query → Fix → Verification

```sql
-- Step 1: Identify slow queries
SELECT query, mean_exec_time, calls
FROM pg_stat_statements
ORDER BY mean_exec_time DESC
LIMIT 10;

-- Step 2: Analyze a specific slow query
EXPLAIN (ANALYZE, BUFFERS, FORMAT TEXT)
SELECT * FROM orders WHERE customer_id = 42 AND status = 'pending';
-- Look for: Seq Scan (bad on large tables), high Buffers hit, nested loops on large sets

-- Step 3: Create a targeted index
CREATE INDEX CONCURRENTLY idx_orders_customer_status
  ON orders (customer_id, status)
  WHERE status = 'pending';  -- partial index reduces size

-- Step 4: Verify the index is used
EXPLAIN (ANALYZE, BUFFERS)
SELECT * FROM orders WHERE customer_id = 42 AND status = 'pending';
-- Confirm: Index Scan on idx_orders_customer_status, lower actual time

-- Step 5: Update statistics if needed after bulk changes
ANALYZE orders;
```

## Reference Guide

Load detailed guidance based on context:

| Topic | Reference | Load When |
|-------|-----------|-----------|
| Performance | `references/performance.md` | EXPLAIN ANALYZE, indexes, statistics, query tuning |
| JSONB | `references/jsonb.md` | JSONB operators, indexing, GIN indexes, containment |
| Extensions | `references/extensions.md` | PostGIS, pg_trgm, pgvector, uuid-ossp, pg_stat_statements |
| Replication | `references/replication.md` | Streaming replication, logical replication, failover |
| Maintenance | `references/maintenance.md` | VACUUM, ANALYZE, pg_stat views, monitoring, bloat |

## Common Patterns

### JSONB — GIN Index and Query

```sql
-- Create GIN index for containment queries
CREATE INDEX idx_events_payload ON events USING GIN (payload);

-- Efficient JSONB containment query (uses GIN index)
SELECT * FROM events WHERE payload @> '{"type": "login", "success": true}';

-- Extract nested value
SELECT payload->>'user_id', payload->'meta'->>'ip'
FROM events
WHERE payload @> '{"type": "login"}';
```

### VACUUM and Bloat Monitoring

```sql
-- Check tables with high dead tuple counts
SELECT relname, n_dead_tup, n_live_tup,
       round(n_dead_tup::numeric / NULLIF(n_live_tup + n_dead_tup, 0) * 100, 2) AS dead_pct,
       last_autovacuum
FROM pg_stat_user_tables
ORDER BY n_dead_tup DESC
LIMIT 20;

-- Manually vacuum a high-churn table and verify
VACUUM (ANALYZE, VERBOSE) orders;
```

### Replication Lag Monitoring

```sql
-- On primary: check standby lag
SELECT client_addr, state, sent_lsn, write_lsn, flush_lsn, replay_lsn,
       (sent_lsn - replay_lsn) AS replication_lag_bytes
FROM pg_stat_replication;
```

## Constraints

### MUST DO
- Use `EXPLAIN (ANALYZE, BUFFERS)` for query optimization
- Verify indexes are actually used with `EXPLAIN` before and after creation
- Use `CREATE INDEX CONCURRENTLY` to avoid table locks in production
- Run `ANALYZE` after bulk data changes to refresh statistics
- Monitor autovacuum; tune `autovacuum_vacuum_scale_factor` for high-churn tables
- Use connection pooling (pgBouncer, pgPool)
- Monitor replication lag via `pg_stat_replication`
- Use prepared statements to prevent SQL injection
- Use `uuid` type for UUIDs, not `text`

### MUST NOT DO
- Disable autovacuum globally
- Create indexes without first analyzing query patterns
- Use `SELECT *` in production queries
- Ignore replication lag alerts
- Skip VACUUM on high-churn tables
- Store large BLOBs in the database (use object storage)
- Deploy index changes without verifying the planner uses them

## Output Templates

When implementing PostgreSQL solutions, provide:
1. Query with `EXPLAIN (ANALYZE, BUFFERS)` output and interpretation
2. Index definitions with rationale and pre/post verification
3. Configuration changes with before/after values
4. Monitoring queries for ongoing health checks
5. Brief explanation of performance impact

## VERIFICATION GATE (BLOQUANT)

Apres execution, AVANT de declarer termine :

- [ ] `EXPLAIN (ANALYZE, BUFFERS)` apres fix montre Index Scan (ou Hash Join) -- plus de Seq Scan non voulu
- [ ] Migration dry-run via `scripts/psql_dry_run.sh` exit 0 avant application (R27 Pattern A)
- [ ] Migration appliquee et tables/indexes verifies (`pg_tables`, `pg_indexes`)
- [ ] `VACUUM (ANALYZE, VERBOSE)` confirme la reduction du bloat si tuning autovacuum
- [ ] Aucune valeur `FLOAT`/`REAL` introduite -- `NUMERIC(p,s)` uniquement (convention LIA-SEC)
- [ ] Config tunable ajoutee dans `system_variables` si nouveau parametre (R5)
- [ ] `unified_logs` non touche avec lock exclusif (R16 -- `ADD COLUMN IF NOT EXISTS` + `CONCURRENTLY`)
- [ ] Latence mesurée avant/apres via `pg_stat_statements` ou `EXPLAIN actual time`

Si un gate echoue : STOP, fix, re-gate. JAMAIS declarer "done" avec un gate rouge.

## Scoring agentique

| Critere | Score |
|---------|-------|
| C1 Decomposition : sous-taches identifiees ? | /10 |
| C2 Planification : PLAN_POSTGRES_PRO_*.md cree et suivi ? | /10 |
| C3 Replanification : /replan declenche sur echecs consecutifs ? | /10 |
| C4 Outillage : psql_lia + dry-run + /db-schema-designer + /sql-pro invoques selon contexte ? | /10 |
| C5 Tracabilite : decision_log + RETEX produits ? | /10 |

Score total /50 -- >= 40 : Exemplaire | 30-39 : Acceptable | < 30 : RETEX obligatoire

## Knowledge Reference

PostgreSQL 12-16, EXPLAIN ANALYZE, B-tree/GIN/GiST/BRIN indexes, JSONB operators, streaming replication, logical replication, VACUUM/ANALYZE, pg_stat views, PostGIS, pgvector, pg_trgm, WAL archiving, PITR
