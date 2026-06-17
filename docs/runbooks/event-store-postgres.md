# Event store Phase 2 -- PostgreSQL (optionnel, SQLite reste le defaut)

Implemente la Phase 2 de `.claude/rules/event-store-decision.md` : un event store
PostgreSQL derriere le MEME trait `EventStore`, selectionne par config. **SQLite reste
le defaut** -- rien ne change tant que vous ne basculez pas explicitement.

## Quand (et seulement quand) basculer

Restez sur SQLite (Phase 1) jusqu'a ce qu'UN seuil tombe (selon le document de decision) :
1. Plans Control / Data / Audit sur des **hotes separes** (un fichier SQLite ne se partage
   pas sur le reseau) ;
2. besoin de **plusieurs ecrivains concurrents** sur l'event store ;
3. throughput d'append soutenu au-dela de quelques milliers/s.

D'ici la : ne rien faire. `INSPECT_IA_AGENTS_EVENT_STORE` non defini -> SQLite.

## La bascule

```
INSPECT_IA_AGENTS_EVENT_STORE=sqlite     # default -- file at INSPECT_IA_AGENTS_EVENT_STORE_PATH
INSPECT_IA_AGENTS_EVENT_STORE=postgres   # PostgresEventStore at INSPECT_IA_AGENTS_DATABASE_URL (R8)
```

`build_event_store_from_env()` (recette/platform/eventstore) lit la bascule. La
gateway, les approbations, le replay -- tout le reste -- est inchange : ils ne dependent
que du trait `EventStore`, jamais d'un store concret.

```mermaid
flowchart LR
  ENV{"INSPECT_IA_AGENTS_EVENT_STORE"} -->|unset / sqlite| SQ["SqliteEventStore (Phase 1, defaut)"]
  ENV -->|postgres| PG["PostgresEventStore (Phase 2, opt-in)"]
  SQ --> T["trait EventStore"]
  PG --> T
  T --> GW["Gateway / approbations / replay (inchanges)"]
```

## Ce que Postgres ajoute par rapport a SQLite

Meme contrat (append-only I1, ordre total monotone `seq` I4, hash chain sha256),
plus la propriete que SQLite ne peut pas offrir sur un reseau :

- **`seq BIGSERIAL`** -> ordre total monotone de replay a travers les hotes.
- **Immutabilite par triggers** (`RAISE` plpgsql sur UPDATE/DELETE) -- parite avec les
  triggers SQLite, imposee dans le moteur et non par discipline (I1).
- **Correction multi-ecrivain concurrent** : chaque append prend un
  `pg_advisory_xact_lock` au scope de la transaction avant de lire le dernier hash et
  d'inserer. Deux ecrivains sur deux hotes ne peuvent donc pas forker la hash chain.
  C'est tout l'interet de la Phase 2.

```mermaid
sequenceDiagram
  participant A as Ecrivain A (hote 1)
  participant DB as PostgreSQL
  participant B as Ecrivain B (hote 2)
  A->>DB: BEGIN + pg_advisory_xact_lock(K)
  B->>DB: BEGIN + pg_advisory_xact_lock(K) attend
  A->>DB: lit dernier hash -> chain_hash -> INSERT -> COMMIT (verrou libere)
  DB-->>B: verrou accorde
  B->>DB: lit dernier hash (celui de A) -> chain_hash -> INSERT -> COMMIT
  Note over DB: une seule hash chain lineaire, non forkee
```

## Installation + execution

```
pip install '.[postgres]'                       # the optional psycopg dependency
export INSPECT_IA_AGENTS_EVENT_STORE=postgres
export INSPECT_IA_AGENTS_DATABASE_URL=postgresql://user:pass@host:5432/inspect_ia_agents
```

Les credentials vivent dans le DSN, resolus depuis l'env / le secret store (R8), jamais
en dur. Migrer hors de SQLite est le travail de l'operateur (le log est append-only --
rejouer l'ancien stream SQLite dans le nouveau store, ou demarrer Postgres a neuf depuis
un point de bascule).

## Tests

`tests/test_eventstore_postgres.py` reproduit la suite SQLite contre un VRAI Postgres,
plus les triggers d'immutabilite, la detection d'alteration, et un test d'ecrivains
concurrents prouvant que la chaine reste lineaire sous deux ecrivains simultanes. Il ne
s'execute que lorsque `INSPECT_IA_AGENTS_TEST_POSTGRES_DSN` est defini (ignore sinon -- la
suite par defaut n'a pas besoin de Postgres). Verifie une fois contre Postgres 16 : 9/9.

```
INSPECT_IA_AGENTS_TEST_POSTGRES_DSN=postgresql://postgres:pw@127.0.0.1:5432/inspect_ia_agents_test \
  python -m unittest tests.test_eventstore_postgres
```

## Mode de defaillance

Une erreur du store leve une exception -- la gateway traite une action non auditee comme
non executable (fail-safe). Un backend `postgres` mal configure (DSN manquant, psycopg
absent) leve `EventStoreConfigError` au demarrage plutot que de retomber silencieusement
sur un fallback.
