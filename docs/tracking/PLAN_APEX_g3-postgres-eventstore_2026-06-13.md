# Plan : G3 -- Event store Phase 2 PostgreSQL (option dormante)

Date : 2026-06-13
Status : TERMINE
Branch : feat/g3-postgres-eventstore (depuis main)
Invariants : I1 (append-only, triggers), I4 (ordre total seq, replay), R8 (DSN env)

## Objectif

Phase 2 de event-store-decision.md : `PostgresEventStore` derriere le meme trait
`EventStore`, bascule par config. SQLite RESTE LE DEFAUT (option dormante).

## Decision

Alternative A (skip-guard sans vrai Postgres) REJETEE : R14 interdit de livrer non
verifie. Alternative B RETENUE : impl mirror du SqliteEventStore + verif contre un VRAI
Postgres (docker ephemere), bascule config, defaut SQLite inchange. psycopg = extra opt.

## Etapes

- [x] S1 `recette/platform/eventstore/postgres_store.py` : PostgresEventStore (BIGSERIAL,
      triggers I1, hash chain, advisory-lock append multi-writer, read_from/get/verify).
- [x] S2 factory `build_event_store_from_env()` (switch sqlite|postgres) + wire app.py
      (psycopg lazy -> reste optionnel).
- [x] S3 extra `[postgres]` (psycopg) + override mypy psycopg.
- [x] S4 `tests/test_eventstore_postgres.py` : 9/9 contre Postgres 16 reel (mirror SQLite +
      immutabilite + tamper + concurrence). REPLAN : DDL sur chaque init -> "tuple
      concurrently updated" sous 2 writers -> serialise par advisory lock schema.
- [x] S5 doc runbook + 2 mermaid ; correction TODO G3 ; defaut SQLite confirme.

## Ecarts et replanification

- S4 REPLAN : le `_SCHEMA` (CREATE OR REPLACE FUNCTION + DROP/CREATE TRIGGER) sur chaque
  construction de store provoquait `tuple concurrently updated` sous inits concurrents
  (catalogues systeme). Fix : `pg_advisory_xact_lock(_SCHEMA_LOCK_KEY)` autour du setup
  schema. 9/9 apres fix.

## Resultat

PostgresEventStore livre, dormant (defaut SQLite). 9/9 contre un vrai Postgres ; suite
complete verte (tests Postgres skip sans DSN) ; gates delta clean. Bascule config-only.
