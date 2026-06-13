# RETEX APEX -- G3 PostgreSQL event store (Phase 2, dormant option)

Date : 2026-06-13
Branch : feat/g3-postgres-eventstore
Agentic score : 44/50

| Criterion | Score | Comment |
|-----------|-------|---------|
| C1 Decomposition | 9/10 | 5 sous-taches SRP (store, factory, extra, tests, doc) |
| C2 Planning (THINK) | 9/10 | feasibilite verifiee AVANT (psycopg + docker pg) ; 2 alternatives (skip-guard rejete car R14, vs verif reelle) |
| C3 Replanning | 9/10 | 1 REPLAN diagnostique (R13) : "tuple concurrently updated" -> advisory lock schema |
| C4 Tooling | 9/10 | docker pg ephemere pour verif R14, .venv/.venv-pyaudit, mmdc |
| C5 Traceability | 9/10 | PLAN + RETEX + runbook + TODO corrige + commit branche |

Sous-taches : 5 SUCCESS / 0 PARTIAL / 0 FAILURE / 1 REPLAN

## Livre

- `PostgresEventStore` derriere le meme trait `EventStore` : `seq BIGSERIAL` (ordre total
  I4), triggers plpgsql anti UPDATE/DELETE (I1), hash chain byte-identique (chain_hash
  canonicalise), `pg_advisory_xact_lock` sur l'append -> chaine non-forkee multi-writer.
- `build_event_store_from_env()` : bascule `AGENTRAIL_EVENT_STORE=sqlite|postgres`, DSN
  `AGENTRAIL_DATABASE_URL` (R8). psycopg lazy -> dependance optionnelle (extra [postgres]).
- `tests/test_eventstore_postgres.py` : 9 tests contre un VRAI Postgres 16.
- `docs/runbooks/event-store-postgres.md` + 2 mermaid (switch, sequence multi-writer).

## Preuves (faits, R14)

- 9/9 contre Postgres 16 reel (docker), incl. immutabilite triggers, tamper detection,
  concurrence multi-writer (50 events 2 writers -> 1 chaine lineaire, verify_chain ok).
- Suite complete 730 (tests Postgres skip sans DSN) ; defaut confirme SqliteEventStore.
- gates : ruff + mypy delta clean, bandit 0 (B608 = nosec justifie : fragments statiques
  + %s, jamais d'interpolation).

## Le point cle : SQLite reste le defaut

L'utilisateur a (legitimement) demande "on est sur SQLite ??". Confirme : oui, defaut
inchange. Postgres = code DORMANT, opt-in par une variable d'env. C'est exactement la
Phase 2 PHASEE de event-store-decision.md, pas un switch impose.

## REPLAN (R13, pas de deduction)

`__init__` executait le DDL (`CREATE OR REPLACE FUNCTION` + DROP/CREATE TRIGGER) a chaque
construction -> deux inits concurrents -> `tuple concurrently updated` sur les catalogues.
Diagnostic par instrumentation (compte par writer + erreur de thread), pas par hypothese.
Fix : advisory lock dedie autour du setup schema. 9/9 apres.

## R28 flag-not-sweep

`recette/run_view.py` + `tests/test_run_view.py` (untracked, autre session, import
`recette.viz` inexistant) provoquent 1 ERROR de collecte hors scope -- FLAGGES, ni
corriges, ni commites.

## Evolutions

- Quick win : un script de migration `replay SQLite -> Postgres` (le log est append-only).
- Notable : pool de connexions (psycopg_pool) pour le multi-host a vrai throughput.
- Refactor : pytest-postgresql / testcontainers en CI pour exercer le backend Postgres
  automatiquement (aujourd'hui verifie manuellement via docker).
