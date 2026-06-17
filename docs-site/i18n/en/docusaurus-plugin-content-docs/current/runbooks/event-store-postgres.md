# Event store Phase 2 -- PostgreSQL (optional, SQLite stays default)

Implements the Phase 2 of `.claude/rules/event-store-decision.md`: a PostgreSQL
event store behind the SAME `EventStore` trait, selected by config. **SQLite remains
the default** -- nothing changes until you explicitly switch.

## When (and only when) to switch

Stay on SQLite (Phase 1) until ONE threshold falls (per the decision doc):
1. Control / Data / Audit planes on **separate hosts** (a SQLite file is not shared
   over the network);
2. need for **several concurrent writers** on the event store;
3. sustained append throughput beyond a few thousand/s.

Until then: do nothing. `INSPECT_IA_AGENTS_EVENT_STORE` unset -> SQLite.

## The switch

```
INSPECT_IA_AGENTS_EVENT_STORE=sqlite     # default -- file at INSPECT_IA_AGENTS_EVENT_STORE_PATH
INSPECT_IA_AGENTS_EVENT_STORE=postgres   # PostgresEventStore at INSPECT_IA_AGENTS_DATABASE_URL (R8)
```

`build_event_store_from_env()` (recette/platform/eventstore) reads the switch. The
gateway, approvals, replay -- everything else -- is unchanged: they depend only on
the `EventStore` trait, never on a concrete store.

```mermaid
flowchart LR
  ENV{"INSPECT_IA_AGENTS_EVENT_STORE"} -->|unset / sqlite| SQ["SqliteEventStore (Phase 1, default)"]
  ENV -->|postgres| PG["PostgresEventStore (Phase 2, opt-in)"]
  SQ --> T["EventStore trait"]
  PG --> T
  T --> GW["Gateway / approvals / replay (unchanged)"]
```

## What Postgres adds over SQLite

Same contract (append-only I1, monotone `seq` total order I4, sha256 hash chain),
plus the property SQLite cannot give over a network:

- **`seq BIGSERIAL`** -> monotone total replay order across hosts.
- **Immutability by triggers** (plpgsql `RAISE` on UPDATE/DELETE) -- parity with the
  SQLite triggers, enforced in the engine not by discipline (I1).
- **Concurrent multi-writer correctness**: every append takes a transaction-scoped
  `pg_advisory_xact_lock` before reading the last hash and inserting. Two writers on
  two hosts therefore cannot fork the hash chain. This is the whole point of Phase 2.

```mermaid
sequenceDiagram
  participant A as Writer A (host 1)
  participant DB as PostgreSQL
  participant B as Writer B (host 2)
  A->>DB: BEGIN + pg_advisory_xact_lock(K)
  B->>DB: BEGIN + pg_advisory_xact_lock(K) waits
  A->>DB: read last hash -> chain_hash -> INSERT -> COMMIT (lock released)
  DB-->>B: lock granted
  B->>DB: read last hash (now A's) -> chain_hash -> INSERT -> COMMIT
  Note over DB: one linear, unforked hash chain
```

## Install + run

```
pip install '.[postgres]'                       # the optional psycopg dependency
export INSPECT_IA_AGENTS_EVENT_STORE=postgres
export INSPECT_IA_AGENTS_DATABASE_URL=postgresql://user:pass@host:5432/inspect_ia_agents
```

Credentials live in the DSN, resolved from env / secret store (R8), never hardcoded.
Migrating off SQLite is the operator's job (the log is append-only -- replay the old
SQLite stream into the new store, or run Postgres fresh from a cutover point).

## Tests

`tests/test_eventstore_postgres.py` mirrors the SQLite suite against a REAL Postgres,
plus immutability triggers, tamper detection, and a concurrent-writer test proving the
chain stays linear under two simultaneous writers. It runs only when
`INSPECT_IA_AGENTS_TEST_POSTGRES_DSN` is set (skipped otherwise -- the default suite needs no
Postgres). Verified once against Postgres 16: 9/9.

```
INSPECT_IA_AGENTS_TEST_POSTGRES_DSN=postgresql://postgres:pw@127.0.0.1:5432/inspect_ia_agents_test \
  python -m unittest tests.test_eventstore_postgres
```

## Failure mode

A store error raises -- the gateway treats an unaudited action as not executable
(fail-safe). A misconfigured `postgres` backend (missing DSN, psycopg absent) raises
`EventStoreConfigError` at startup rather than silently falling back.
