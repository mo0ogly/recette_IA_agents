---
name: db-schema-designer
version: "1.0"
description: "Design and evolve PostgreSQL 17 schemas for LIA-SEC. Produces production-ready DDL (tables, indexes, constraints), numbered migration files (cmd/sigma_web/migrations/NNN_*.sql), Mermaid ERD, and apply commands. Enforces LIA-SEC conventions: UUID PK, TIMESTAMPTZ, JSONB, GIN, IF NOT EXISTS, no FLOAT for numerics, system_variables patterns. Triggers on: design schema, creer table, migration pour, nouveau module PostgreSQL, schema pour, add column, index strategy, review schema, ERD."
---

# DB Schema Designer v1.0 -- PostgreSQL 17 LIA-SEC

Conçoit des schémas PostgreSQL 17 production-ready avec les conventions LIA-SEC intégrées.
Produit le fichier de migration numéroté, les commandes d'application, et optionnellement le diagramme ERD.

**Mode:** No-chat. Analyse -> Produit le fichier -> Affiche la commande psql.
**Cible:** PostgreSQL 17, base `lia_scan`, user `lia_admin`.
**Output:** `cmd/sigma_web/migrations/{NNN}_{description}.sql`

---

## Syntax

```
/db-schema-designer <description> [flags]
```

| Flag | Description |
|------|-------------|
| `--new-module` | Nouveau module complet (plusieurs tables liées) |
| `--add-column` | Ajout zero-downtime de colonnes sur table existante |
| `--index` | Stratégie d'indexation uniquement (pas de CREATE TABLE) |
| `--review` | Audit d'un schéma existant (tables passées en argument) |
| `--erd` | Génère aussi un diagramme Mermaid ERD |
| `--system-variables` | Ajoute INSERT dans `system_variables` pour la config du module |

**Exemples:**
```
/db-schema-designer "module suivi des actifs physiques" --new-module --erd
/db-schema-designer "ajouter champ owner_id a smsi_assets" --add-column
/db-schema-designer "indexes pour remediation_tracking" --index
/db-schema-designer --review smsi_risk_assessments smsi_risk_scenarios
```

---

## Triggers

| Déclencheur | Exemple |
|-------------|---------|
| `design schema` | "design schema for physical assets module" |
| `creer table` | "creer table pour tracking des contrats" |
| `migration pour` | "migration pour ajouter la colonne deadline" |
| `nouveau module PostgreSQL` | "nouveau module alerting avec 3 tables" |
| `schema pour` | "schema pour un système de ticketing interne" |
| `add column` | "add column risk_level to smsi_assets" |
| `index strategy` | "index strategy for cve_nvd_data" |
| `review schema` | "review schema de la table iso27005_threats" |
| `ERD` / `diagramme` | "ERD du module remediation" |

---

## Decomposition des sous-taches

Au demarrage, decomposer toute demande en sous-taches independantes :

- [ ] Sous-tache 1 : reads / greps pour detecter conflits de noms, schema existant, dernier NNN
- [ ] Sous-tache 2 : conception du schema (entites, relations, access patterns, volume attendu)
- [ ] Sous-tache 3 : ecriture migration `NNN_*.sql` (Pattern A R27 -- pas de BEGIN/COMMIT top-level)
- [ ] Sous-tache 4 : dry-run via `scripts/psql_dry_run.sh` + verification idempotence
- [ ] Sous-tache 5 : ERD Mermaid si `--erd`; system_variables si `--system-variables`
- [ ] Sous-tache 6 : afficher commande psql d'application + commandes de verification

Utiliser `TaskCreate` pour tracker si > 3 sous-taches.

## Plan d'execution

Pour tout schema non trivial (nouveau module, > 2 tables, ou ALTER sur table volumineuse) :

1. Creer `_alire/tracking/PLAN_DB_SCHEMA_{FEATURE}_{YYYY-MM-DD}.md` avant d'ecrire la migration.
2. Template : `_alire/tracking/PLAN_TEMPLATE.md`.
3. Cocher chaque sous-tache a la completion.
4. Si replanification : Status -> REPLANIFIE + lien vers nouveau plan.

Pour une modification ponctuelle (1 colonne, 1 index) : plan inline suffit.

## Adaptation et replanification

Si 2 etapes consecutives echouent (ex: dry-run echoue + correction qui casse une FK, ou conflit de numero NNN) :

- STOP
- Invoquer `/replan` -> produit `PLAN_DB_SCHEMA_*_REPLAN_*.md`
- NE PAS improviser un contournement

Declencheurs typiques :
- Dry-run echoue (exit 3 psql_dry_run.sh) -> REPLAN (Pattern A ? contrainte FK ?)
- Nom de table deja existant -> REPLAN (renommage, module existant a etendre ?)
- Conflit NNN (deux migrations avec meme numero) -> REPLAN (re-scanner `ls migrations/*.sql`)
- ALTER sur `unified_logs` avec lock detecte -> REPLAN (R16 -- utiliser CONCURRENTLY + ADD COLUMN IF NOT EXISTS)

## Outils declares

| Outil | Usage | Retry policy |
|-------|-------|--------------|
| `Read`, `Grep`, `Glob` | Scanner migrations existantes, schema tables, FK existantes | N/A |
| `Bash psql_lia()` | Lister tables, colonnes, indexes, FK pour detecter conflits | echec -> verifier connexion |
| `Bash scripts/psql_dry_run.sh` | Dry-run migration Pattern A (R27) -- OBLIGATOIRE avant application | exit 3 -> corriger, jamais bypasser |
| `Write` | Creer `cmd/sigma_web/migrations/NNN_*.sql` | N/A |
| `Bash python3 generate_mermaid.py` | Generer ERD `.mmd` depuis descripteur `.json` | N/A |
| `TaskCreate` | Tracking si > 3 sous-taches | N/A |
| `Skill(postgres-pro)` | Strategie d'indexation avancee si volume > 100K lignes | Invoquer si `--index` complexe |
| `Skill(sql-pro)` | Rédiger les queries Go qui exploitent le nouveau schema | Obligatoire si nouveau handler suit |

Selection dynamique : dry-run TOUJOURS avant application, `CONCURRENTLY` si table volumineuse, ERD seulement si `--erd`.

## Tracabilite agentique

Logger dans `_alire/02_LOGS/Journals/decision_log.jsonl` chaque decision non triviale :

- Choix de type de relation (CASCADE vs RESTRICT vs SET NULL) + justification metier
- Rejet d'une structure (normalisation vs denormalisation, JSONB vs colonnes separees)
- Decisions de soft-delete vs hard delete
- Trade-offs (UUID vs SERIAL, index partiel vs index complet)

Format :
```json
{"timestamp":"...","session":"db-schema-{feature}","action":"...","reasoning":"...","alternatives_rejected":["..."],"outcome":"...","confidence":"high","plan_ref":"PLAN_DB_SCHEMA_*.md"}
```

RETEX en fin de session si score agentique < 40/50 -> `_alire/02_LOGS/Journals/retex/RETEX_DB_SCHEMA_YYYY-MM-DD.md`.

## Workflow d'exécution

### Étape 0 -- Numéro de migration suivant

```bash
# Détecter le numéro de migration suivant
ls cmd/sigma_web/migrations/*.sql | grep -E '/[0-9]{3}_' | sort | tail -1
# Incrémenter de 1 -> NNN
```

**Règle naming:** `NNN_module_action.sql` (3 chiffres, snake_case, pas de majuscules).
Ex: `098_physical_assets.sql`, `099_smsi_assets_owner.sql`.

### Étape 1 -- Analyser l'existant

```bash
# Vérifier les conflits de noms de tables
PGPASSWORD="$LIA_DB_PASS" psql -h localhost -U lia_admin -d lia_scan -c "
  SELECT tablename FROM pg_tables 
  WHERE schemaname='public' 
  ORDER BY tablename;" 2>/dev/null | grep -i "{keyword}"

# Voir le schéma d'une table existante si le flag --add-column ou --review
PGPASSWORD="$LIA_DB_PASS" psql -h localhost -U lia_admin -d lia_scan -c "
  SELECT column_name, data_type, is_nullable, column_default
  FROM information_schema.columns
  WHERE table_name='{table}'
  ORDER BY ordinal_position;" 2>/dev/null

# Voir les indexes existants
PGPASSWORD="$LIA_DB_PASS" psql -h localhost -U lia_admin -d lia_scan -c "
  SELECT indexname, indexdef FROM pg_indexes
  WHERE tablename='{table}';" 2>/dev/null

# Voir les FK existantes
PGPASSWORD="$LIA_DB_PASS" psql -h localhost -U lia_admin -d lia_scan -c "
  SELECT tc.constraint_name, kcu.column_name, ccu.table_name AS foreign_table, ccu.column_name AS foreign_column
  FROM information_schema.table_constraints AS tc
  JOIN information_schema.key_column_usage AS kcu ON tc.constraint_name = kcu.constraint_name
  JOIN information_schema.constraint_column_usage AS ccu ON ccu.constraint_name = tc.constraint_name
  WHERE tc.constraint_type = 'FOREIGN KEY' AND tc.table_name='{table}';" 2>/dev/null
```

### Étape 2 -- Concevoir le schéma

Appliquer les règles LIA-SEC (section "Conventions obligatoires" ci-dessous).
Identifier : entités, relations, access patterns, volume attendu.

### Étape 3 -- Écrire le fichier de migration

Créer `cmd/sigma_web/migrations/{NNN}_{description}.sql` avec le template standard.

### Étape 4 -- ERD (si `--erd`)

Générer le descripteur JSON puis le diagramme Mermaid :
```bash
python3 .claude/skills/doc-code/scripts/generate_mermaid.py er \
  _alire/01_DOCUMENTATION/diagrams/{module}_er.json \
  -o _alire/01_DOCUMENTATION/diagrams/{module}_er.mmd --theme dark
```

### Étape 5 -- Afficher la commande d'application

```bash
# Toujours afficher cette commande à la fin (ne pas l'exécuter automatiquement)
PGPASSWORD="$LIA_DB_PASS" psql -h localhost -U lia_admin -d lia_scan \
  -f cmd/sigma_web/migrations/{NNN}_{description}.sql
```

---

## Template de migration

```sql
-- ============================================================================
-- Migration {NNN}: {Module Name}
-- Created: {YYYY-MM-DD}
-- Description: {one-line description}
-- Tables: {list of tables created or altered}
-- ============================================================================

-- ============================================================================
-- Table: {table_name}
-- Purpose: {what this table stores}
-- ============================================================================
CREATE TABLE IF NOT EXISTS {table_name} (
    -- Primary key (UUID for new modules)
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Foreign keys (always NOT NULL unless optional relationship)
    {parent_id} UUID NOT NULL REFERENCES {parent_table}(id) ON DELETE CASCADE,

    -- Domain columns
    name         VARCHAR(255) NOT NULL,
    description  TEXT,
    status       VARCHAR(50)  NOT NULL DEFAULT 'active'
                              CHECK (status IN ('active', 'inactive', 'archived')),
    score        NUMERIC(5,2) NOT NULL DEFAULT 0
                              CHECK (score >= 0 AND score <= 100),
    metadata     JSONB        NOT NULL DEFAULT '{}',

    -- Audit timestamps
    created_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    updated_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
    deleted_at   TIMESTAMPTZ  -- NULL = active, non-NULL = soft-deleted

    -- Optional: UNIQUE constraints
    -- UNIQUE({column1}, {column2})
);

-- Indexes
-- Rule: every FK column gets an index
CREATE INDEX IF NOT EXISTS idx_{table_name}_{parent_id} ON {table_name}({parent_id});

-- Rule: frequent WHERE columns
CREATE INDEX IF NOT EXISTS idx_{table_name}_status ON {table_name}(status) WHERE deleted_at IS NULL;

-- Rule: JSONB fields queried by key -> GIN index
CREATE INDEX IF NOT EXISTS idx_{table_name}_metadata ON {table_name} USING GIN(metadata);

-- Rule: composite index if multi-column WHERE pattern
CREATE INDEX IF NOT EXISTS idx_{table_name}_{col1}_{col2} ON {table_name}({col1}, {col2} DESC);
```

---

## Conventions obligatoires LIA-SEC

### Clés primaires

```sql
-- TOUJOURS UUID pour les nouveaux modules (jamais BIGSERIAL sur une nouvelle table)
id UUID PRIMARY KEY DEFAULT gen_random_uuid()

-- SERIAL/BIGSERIAL : réservé aux tables legacy uniquement
-- Ne JAMAIS utiliser AUTO_INCREMENT (MySQL syntax, invalide en PostgreSQL)
```

### Types de données

| Besoin | Type PostgreSQL | Interdit |
|--------|----------------|---------|
| Entier | `INTEGER` / `BIGINT` | `INT(11)`, `TINYINT` |
| Décimal exact | `NUMERIC(p, s)` | `FLOAT`, `REAL`, `DOUBLE PRECISION` pour valeurs métier |
| Monétaire | `NUMERIC(14, 2)` | `FLOAT`, `MONEY` |
| Chaîne courte | `VARCHAR(n)` | `VARCHAR(255)` systématique sans réfléchir |
| Texte long | `TEXT` | `VARCHAR(4000)`, `MEDIUMTEXT` |
| Date+heure | `TIMESTAMPTZ` | `TIMESTAMP WITHOUT TIME ZONE`, `DATETIME` |
| Date seule | `DATE` | stocker en `TEXT` |
| Booléen | `BOOLEAN` | `TINYINT(1)`, `INTEGER` |
| UUID | `UUID` | `CHAR(36)`, `VARCHAR(36)` |
| JSON flexible | `JSONB` | `JSON` (non indexable), `TEXT` |
| Tableau | `TEXT[]`, `UUID[]` | colonne CSV `'a,b,c'` |
| Pourcentage | `NUMERIC(5,2)` | `FLOAT` |
| Score 0-100 | `NUMERIC(5,2)` avec CHECK | sans contrainte |
| Vecteur (RAG) | `vector(384)` (pgvector) | `TEXT` |

### Timestamps standard

```sql
-- Toujours ces deux colonnes sur toutes les tables
created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()

-- Soft delete (si le module l'utilise)
deleted_at  TIMESTAMPTZ   -- NULL = actif
```

### Foreign keys

```sql
-- ON DELETE strategy OBLIGATOIRE (ne jamais omettre)
-- CASCADE : les enfants suivent la suppression du parent (order_items -> orders)
-- RESTRICT : bloque la suppression si des enfants existent (données importantes)
-- SET NULL : la FK devient NULL quand le parent est supprimé (relation optionnelle)

-- Exemples LIA-SEC :
assessment_id UUID NOT NULL REFERENCES smsi_risk_assessments(id) ON DELETE CASCADE,
client_id     UUID REFERENCES clients(id) ON DELETE SET NULL,
created_by    UUID REFERENCES users(id) ON DELETE RESTRICT
```

### Indexes obligatoires

```sql
-- 1. Chaque colonne FK DOIT avoir un index
CREATE INDEX IF NOT EXISTS idx_{table}_{fk_col} ON {table}({fk_col});

-- 2. Colonnes WHERE fréquentes
CREATE INDEX IF NOT EXISTS idx_{table}_{col} ON {table}({col});

-- 3. Colonnes JSONB interrogées par clé -> GIN
CREATE INDEX IF NOT EXISTS idx_{table}_metadata ON {table} USING GIN(metadata);
CREATE INDEX IF NOT EXISTS idx_{table}_tags ON {table} USING GIN(tags);

-- 4. Soft-delete : index partiel pour exclure les supprimés
CREATE INDEX IF NOT EXISTS idx_{table}_active ON {table}(status) WHERE deleted_at IS NULL;

-- 5. Recherche texte plein -> GIN avec tsvector
CREATE INDEX IF NOT EXISTS idx_{table}_search ON {table} USING GIN(
  to_tsvector('english', coalesce(name,'') || ' ' || coalesce(description,''))
);

-- 6. Composite pour ORDER BY fréquent
CREATE INDEX IF NOT EXISTS idx_{table}_{col1}_{col2} ON {table}({col1}, {col2} DESC);
```

### IF NOT EXISTS partout

```sql
-- OBLIGATOIRE sur tous les CREATE TABLE et CREATE INDEX
-- Les migrations peuvent être rejouées sans erreur
CREATE TABLE IF NOT EXISTS ...
CREATE INDEX IF NOT EXISTS ...
ALTER TABLE ... ADD COLUMN IF NOT EXISTS ...  -- PostgreSQL 9.6+
```

### Contraintes CHECK

```sql
-- Préférer les CHECK à la place des commentaires pour les valeurs autorisées
status     VARCHAR(50) NOT NULL CHECK (status IN ('draft', 'active', 'closed', 'archived')),
severity   VARCHAR(20) NOT NULL CHECK (severity IN ('critical', 'high', 'medium', 'low', 'info')),
score      NUMERIC(5,2)         CHECK (score BETWEEN 0 AND 100),
```

### system_variables (flag `--system-variables`)

```sql
-- Insérer les variables de config du nouveau module dans system_variables
-- Utiliser ON CONFLICT DO NOTHING : idempotent, ne casse pas les valeurs existantes
INSERT INTO system_variables (key, value, description, category)
VALUES
  ('{MODULE}_ENABLED',        'true',   'Enable {module} module',        '{module}'),
  ('{MODULE}_RETENTION_DAYS', '90',     'Data retention in days',        '{module}'),
  ('{MODULE}_MAX_ITEMS',      '1000',   'Maximum items per entity',      '{module}')
ON CONFLICT (key) DO NOTHING;
```

---

## Patterns de relations LIA-SEC

### One-to-Many (le plus courant)

```sql
CREATE TABLE IF NOT EXISTS {parent}s (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS {child}s (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    {parent}_id UUID NOT NULL REFERENCES {parent}s(id) ON DELETE CASCADE,
    -- ...
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_{child}s_{parent}_id ON {child}s({parent}_id);
```

### Many-to-Many (table de jonction)

```sql
CREATE TABLE IF NOT EXISTS {a}_{b}_mappings (
    {a}_id UUID NOT NULL REFERENCES {a}s(id) ON DELETE CASCADE,
    {b}_id UUID NOT NULL REFERENCES {b}s(id) ON DELETE CASCADE,
    -- métadonnées de la relation
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY ({a}_id, {b}_id)
);
CREATE INDEX IF NOT EXISTS idx_{a}_{b}_mappings_{b}_id ON {a}_{b}_mappings({b}_id);
```

### Auto-référence (hiérarchie)

```sql
CREATE TABLE IF NOT EXISTS {entity}s (
    id        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    parent_id UUID REFERENCES {entity}s(id) ON DELETE SET NULL,  -- NULL = racine
    name      VARCHAR(255) NOT NULL,
    depth     INTEGER NOT NULL DEFAULT 0,  -- 0 = racine, pour requêtes récursives
    path      TEXT NOT NULL DEFAULT '',    -- ex: '/root/child/grandchild'
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
-- Index sur parent_id pour traversée de l'arbre
CREATE INDEX IF NOT EXISTS idx_{entity}s_parent_id ON {entity}s(parent_id);
-- Index sur path pour LIKE '{prefix}%' queries
CREATE INDEX IF NOT EXISTS idx_{entity}s_path ON {entity}s(path text_pattern_ops);
```

### Soft-delete (module avec corbeille)

```sql
-- La colonne deleted_at suffit, pas besoin de table séparée
-- Dans le Go handler : WHERE deleted_at IS NULL
-- Convention LIA-SEC : JAMAIS supprimer physiquement, toujours soft-delete
```

---

## Ajout de colonne zero-downtime (flag `--add-column`)

Procédure obligatoire pour les tables volumineuses (>100K lignes) :

```sql
-- ============================================================================
-- Migration {NNN}: Add {column} to {table}
-- Zero-downtime: nullable first, backfill, then constrain
-- ============================================================================

-- Étape 1: Ajouter nullable (instantané, pas de lock table)
ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {type};

-- Étape 2: Backfill (UPDATE par batch si table volumineuse)
-- Pour unified_logs et tables >1M lignes : utiliser des batches de 10K
-- UPDATE {table} SET {column} = {default_value}
-- WHERE {column} IS NULL AND id IN (
--   SELECT id FROM {table} WHERE {column} IS NULL LIMIT 10000
-- );
-- Répéter jusqu'à 0 rows affected.

-- Étape 3: Ajouter la contrainte NOT NULL (seulement après backfill complet)
-- ALTER TABLE {table} ALTER COLUMN {column} SET NOT NULL;
-- ALTER TABLE {table} ALTER COLUMN {column} SET DEFAULT {value};

-- Index si nécessaire
CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_{table}_{column} ON {table}({column});
-- Note: CONCURRENTLY évite le lock exclusif sur les tables volumineuses
```

**Règle spéciale `unified_logs`:** JAMAIS ALTER TABLE sur `unified_logs` avec lock.
Cette table contient 244M+ lignes. Tout DDL exclusif cause un deadlock (incident R16).

---

## Stratégie d'indexation avancée (flag `--index`)

### Diagnostiquer les requêtes lentes

```bash
# Tables sans index sur FK (à corriger)
PGPASSWORD="$LIA_DB_PASS" psql -h localhost -U lia_admin -d lia_scan -c "
SELECT tc.table_name, kcu.column_name
FROM information_schema.table_constraints tc
JOIN information_schema.key_column_usage kcu
  ON tc.constraint_name = kcu.constraint_name
WHERE tc.constraint_type = 'FOREIGN KEY'
  AND NOT EXISTS (
    SELECT 1 FROM pg_indexes pi
    WHERE pi.tablename = tc.table_name
      AND pi.indexdef LIKE '%' || kcu.column_name || '%'
  )
ORDER BY tc.table_name;" 2>/dev/null

# Tables séquentielles fréquentes (candidates à l'indexation)
PGPASSWORD="$LIA_DB_PASS" psql -h localhost -U lia_admin -d lia_scan -c "
SELECT relname, seq_scan, seq_tup_read, idx_scan, n_live_tup
FROM pg_stat_user_tables
WHERE seq_scan > 100
ORDER BY seq_tup_read DESC LIMIT 20;" 2>/dev/null
```

### Types d'index PostgreSQL 17

| Type | Quand | Exemple |
|------|-------|---------|
| **B-tree** (défaut) | `=`, `<`, `>`, `BETWEEN`, `ORDER BY` | `idx ON t(created_at DESC)` |
| **GIN** | `JSONB @> {}`, `@?`, `@@`, tableau `&&`, texte FTS | `USING GIN(metadata)` |
| **GiST** | Géométrie, texte flou (pg_trgm), ranges | `USING GIST(geom)` |
| **BRIN** | Très grande table, colonnes monotones (timestamps) | `USING BRIN(created_at)` |
| **Hash** | Égalité stricte uniquement (rare avantage vs B-tree) | `USING HASH(session_id)` |
| **Partiel** | Sous-ensemble de lignes (soft-delete, status actif) | `WHERE deleted_at IS NULL` |
| **CONCURRENTLY** | Création sans lock (tables volumineuses en prod) | `CREATE INDEX CONCURRENTLY` |

---

## Audit de schéma (flag `--review`)

Checks appliqués lors d'un audit :

```
SCHEMA-01 : Chaque table a une clé primaire
SCHEMA-02 : Toutes les FK ont une stratégie ON DELETE explicite
SCHEMA-03 : Chaque FK a un index correspondant
SCHEMA-04 : Colonnes FLOAT/REAL/DOUBLE PRECISION -> bannies sauf données scientifiques
SCHEMA-05 : Dates stockées en TIMESTAMP/TIMESTAMPTZ (pas en TEXT)
SCHEMA-06 : Colonnes JSON -> doivent être JSONB (pas JSON)
SCHEMA-07 : Tables volumineuses ont des indexes BRIN sur created_at
SCHEMA-08 : Pas de VARCHAR(255) systématique sans raison documentée
SCHEMA-09 : created_at et updated_at présents
SCHEMA-10 : Contraintes CHECK présentes pour enum-like columns (status, severity)
SCHEMA-11 : UNIQUE constraints présentes où la donnée doit l'être
SCHEMA-12 : Tables avec JSONB ont un index GIN sur la colonne JSONB
```

---

## ERD Mermaid (flag `--erd`)

Génération via le script doc-code existant :

```bash
# 1. Créer le descripteur JSON
cat > _alire/01_DOCUMENTATION/diagrams/{module}_er.json << 'EOF'
{
  "type": "er",
  "title": "{Module} Entity-Relationship Diagram",
  "entities": [
    {
      "name": "{table_name}",
      "attributes": [
        {"name": "id", "type": "UUID", "key": "PK"},
        {"name": "{fk_col}", "type": "UUID", "key": "FK"},
        {"name": "name", "type": "VARCHAR(255)"},
        {"name": "created_at", "type": "TIMESTAMPTZ"}
      ]
    }
  ],
  "relationships": [
    {
      "from": "{child_table}",
      "to": "{parent_table}",
      "type": "many-to-one",
      "label": "belongs to"
    }
  ]
}
EOF

# 2. Générer le .mmd
python3 .claude/skills/doc-code/scripts/generate_mermaid.py er \
  _alire/01_DOCUMENTATION/diagrams/{module}_er.json \
  -o _alire/01_DOCUMENTATION/diagrams/{module}_er.mmd --theme dark
```

---

## Anti-patterns interdits

| Anti-pattern | Problème | Correct |
|--------------|----------|---------|
| `FLOAT` / `REAL` pour valeurs métier | Erreurs d'arrondi | `NUMERIC(p,s)` |
| `VARCHAR(255)` partout | Cache l'intention, gaspille | Dimensionner au besoin réel |
| `TIMESTAMP` sans TZ | Problèmes DST, ambiguïté | `TIMESTAMPTZ` |
| Date en `TEXT` | Pas triable, pas comparable | `DATE` ou `TIMESTAMPTZ` |
| `JSON` au lieu de `JSONB` | Non indexable | `JSONB` |
| FK sans `ON DELETE` | Comportement implicite dangereux | Toujours spécifier |
| FK sans index | JOIN O(n) | `CREATE INDEX IF NOT EXISTS` |
| `CREATE TABLE` sans `IF NOT EXISTS` | Migration non idempotente | `IF NOT EXISTS` obligatoire |
| `AUTO_INCREMENT` | Syntax MySQL invalide en PostgreSQL | `SERIAL` ou `gen_random_uuid()` |
| `ALTER TABLE unified_logs` avec lock | Deadlock 244M lignes (R16) | `ADD COLUMN IF NOT EXISTS` + `CONCURRENTLY` |
| `DECIMAL` → OK en PostgreSQL (`= NUMERIC`) | Pas d'erreur, juste alias | Préférer `NUMERIC(p,s)` par convention |
| `MONEY` type PostgreSQL | Sensible aux paramètres de locale | `NUMERIC(14,2)` |
| Vrai DELETE sur données métier | Perte irréversible | Soft-delete avec `deleted_at` |
| INSERT sans `ON CONFLICT` dans system_variables | Casse la valeur existante | `ON CONFLICT (key) DO NOTHING` |

---

## Commandes d'application

```bash
# Appliquer la migration (afficher TOUJOURS cette commande, ne pas l'exécuter auto)
PGPASSWORD="$LIA_DB_PASS" psql -h localhost -U lia_admin -d lia_scan \
  -f cmd/sigma_web/migrations/{NNN}_{description}.sql

# Vérifier que les tables ont bien été créées
PGPASSWORD="$LIA_DB_PASS" psql -h localhost -U lia_admin -d lia_scan -c "
  SELECT tablename, pg_size_pretty(pg_total_relation_size(tablename::regclass)) AS size
  FROM pg_tables
  WHERE tablename IN ('{table1}', '{table2}')
  ORDER BY tablename;" 2>/dev/null

# Vérifier les indexes
PGPASSWORD="$LIA_DB_PASS" psql -h localhost -U lia_admin -d lia_scan -c "
  SELECT indexname, indexdef FROM pg_indexes
  WHERE tablename IN ('{table1}', '{table2}')
  ORDER BY tablename, indexname;" 2>/dev/null
```

---

## Intégration avec les autres skills

| Situation | Enchaînement |
|-----------|-------------|
| Nouveau module Go complet | `/db-schema-designer --new-module --erd` → `/apex {module}` |
| Endpoint API nouveau | `/db-schema-designer` → `/api-handoff {feature} --r17` → implémenter frontend |
| Après migration complexe | `/doc-code {module} --update --scope=back` pour mettre à jour la doc |
| Audit performance | `/db-schema-designer --review {tables} --index` |
| Module avec config | `/db-schema-designer --new-module --system-variables` |

---

## Checklist de vérification (BLOQUANTE avant commit)

- [ ] Numéro de migration vérifié (pas de collision avec l'existant)
- [ ] `IF NOT EXISTS` sur tous les `CREATE TABLE` et `CREATE INDEX`
- [ ] UUID PK avec `gen_random_uuid()` pour les nouvelles tables
- [ ] `TIMESTAMPTZ` (pas `TIMESTAMP`) pour toutes les dates
- [ ] `NUMERIC` (pas `FLOAT`) pour toutes les valeurs métier
- [ ] `JSONB` (pas `JSON`) pour les champs JSON
- [ ] `ON DELETE` explicite sur toutes les FK
- [ ] Index présent pour chaque colonne FK
- [ ] Contraintes `CHECK` pour les colonnes enum-like (status, severity...)
- [ ] Commande `psql` d'application affichée (pas exécutée automatiquement)
- [ ] Commandes de vérification (`pg_tables`, `pg_indexes`) fournies
- [ ] ERD `.json` + `.mmd` générés si `--erd`
- [ ] `system_variables` avec `ON CONFLICT DO NOTHING` si `--system-variables`
- [ ] Aucun DDL dans les fichiers `.go` sans migration SQL correspondante (hook `check_migration.sh`)
- [ ] Si colonne ajoutée sur table volumineuse : procédure zero-downtime documentée

---

## VERIFICATION GATE (BLOQUANT)

Apres execution, AVANT de declarer termine (complement a la "Checklist de vérification" ci-dessus) :

- [ ] Dry-run migration via `scripts/psql_dry_run.sh` exit 0 (Pattern A R27 -- pas de BEGIN/COMMIT top-level)
- [ ] Migration idempotente : `IF NOT EXISTS` sur tous les `CREATE TABLE` et `CREATE INDEX`
- [ ] UUID PK avec `gen_random_uuid()`, `TIMESTAMPTZ`, `NUMERIC` (pas FLOAT), `JSONB` (pas JSON)
- [ ] `ON DELETE` explicite sur toutes les FK + index sur chaque colonne FK
- [ ] Commande psql d'application affichee + commandes de verification (`pg_tables`, `pg_indexes`)
- [ ] Aucun DDL embarque dans un fichier `.go` sans migration SQL correspondante (hook `check_migration.sh`)
- [ ] Si `--system-variables` : INSERT avec `ON CONFLICT (key) DO NOTHING`
- [ ] `unified_logs` non touche avec lock exclusif (R16)
- [ ] ERD `.json` + `.mmd` generes et commites si `--erd`

Si un gate echoue : STOP, fix, re-gate. JAMAIS declarer "done" avec un gate rouge.

## Scoring agentique

| Critere | Score |
|---------|-------|
| C1 Decomposition : sous-taches identifiees ? | /10 |
| C2 Planification : PLAN_DB_SCHEMA_*.md cree et suivi ? | /10 |
| C3 Replanification : /replan declenche sur echecs consecutifs ? | /10 |
| C4 Outillage : psql_dry_run + psql_lia + /postgres-pro invoques selon contexte ? | /10 |
| C5 Tracabilite : decision_log + RETEX produits ? | /10 |

Score total /50 -- >= 40 : Exemplaire | 30-39 : Acceptable | < 30 : RETEX obligatoire

## Référence rapide des types LIA-SEC

```sql
-- Identifiants
id              UUID        PRIMARY KEY DEFAULT gen_random_uuid()
session_id      UUID        UNIQUE NOT NULL DEFAULT gen_random_uuid()
external_ref    VARCHAR(100) UNIQUE  -- référence externe (CVE-ID, MITRE-ID, etc.)

-- Textes
name            VARCHAR(255) NOT NULL
slug            VARCHAR(100) UNIQUE NOT NULL
description     TEXT
content         TEXT
summary         TEXT

-- Numériques
score           NUMERIC(5,2)  NOT NULL DEFAULT 0 CHECK (score BETWEEN 0 AND 100)
severity_score  NUMERIC(5,2)  NOT NULL DEFAULT 0 CHECK (severity_score BETWEEN 0 AND 10)
amount          NUMERIC(14,2) NOT NULL DEFAULT 0 CHECK (amount >= 0)
count           INTEGER       NOT NULL DEFAULT 0 CHECK (count >= 0)
percentage      NUMERIC(5,2)  CHECK (percentage BETWEEN 0 AND 100)

-- Statuts / enums
status          VARCHAR(50)   NOT NULL DEFAULT 'active'
                              CHECK (status IN ('draft', 'active', 'archived', 'deleted'))
severity        VARCHAR(20)   NOT NULL DEFAULT 'medium'
                              CHECK (severity IN ('critical', 'high', 'medium', 'low', 'info'))
priority        VARCHAR(20)   NOT NULL DEFAULT 'medium'
                              CHECK (priority IN ('critical', 'high', 'medium', 'low'))

-- Timestamps
created_at      TIMESTAMPTZ   NOT NULL DEFAULT NOW()
updated_at      TIMESTAMPTZ   NOT NULL DEFAULT NOW()
deleted_at      TIMESTAMPTZ   -- NULL = actif
expires_at      TIMESTAMPTZ
last_seen_at    TIMESTAMPTZ

-- JSON
metadata        JSONB         NOT NULL DEFAULT '{}'
config          JSONB         NOT NULL DEFAULT '{}'
tags            JSONB         NOT NULL DEFAULT '[]'   -- tableau JSON
evidence        JSONB         NOT NULL DEFAULT '[]'

-- Vecteurs (RAG / embeddings)
embedding       vector(384)   -- pgvector, modèle all-minilm

-- Booléens
is_active       BOOLEAN       NOT NULL DEFAULT TRUE
is_verified     BOOLEAN       NOT NULL DEFAULT FALSE
```
