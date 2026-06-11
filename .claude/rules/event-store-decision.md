# Event Store -- decision de persistance (PHASEE)

> Statut : PHASE 1 = SQLite (debut, mono-hote). PHASE 2 = PostgreSQL (quand distribue).
> Decide le 2026-06-11. La couche persistance DOIT rester derriere le trait `EventStore`
> pour que le passage Phase 1 -> Phase 2 ne touche que l'implementation, pas le reste du systeme.

## Contraintes imposees par les invariants

Quel que soit le choix, le store DOIT garantir :
- **I1** : append-only, immuable apres commit (pas d'UPDATE/DELETE du log).
- **I4** : ordre stable et reproductible des evenements (replay deterministe).
- Reconstruction des projections/read-models depuis le log seul.
- Integrite verifiable (hash chain / `side_effect_hash`).

## Decision phasee (retenue)

### PHASE 1 -- SQLite (debut, mono-hote) [ACTIVE]

- Log = table `events` INSERT-only, `seq INTEGER PRIMARY KEY AUTOINCREMENT` (ordre total monotone).
- Immutabilite ENFORCEE par triggers, pas seulement par discipline :
  ```sql
  CREATE TRIGGER events_no_update BEFORE UPDATE ON events
    BEGIN SELECT RAISE(ABORT, 'events are immutable (I1)'); END;
  CREATE TRIGGER events_no_delete BEFORE DELETE ON events
    BEGIN SELECT RAISE(ABORT, 'events are immutable (I1)'); END;
  ```
- `PRAGMA journal_mode=WAL;` (lecteurs concurrents pendant l'ecriture).
- Integrite : colonne `prev_hash` (hash chain) + `side_effect_hash`.
- Atout : SQLite est mono-ecrivain -> ordre total deterministe GRATUIT (I4), sans coordination.
- Pour : zero composant a operer, ecosysteme Rust mur (`sqlx` sqlite / `rusqlite`), demarrage immediat.
- Contre / limites = criteres de bascule Phase 2 (voir plus bas).

### PHASE 2 -- PostgreSQL event-sourcing [TRIGGERED WHEN...]

Migrer vers PostgreSQL (cf. Option A) des qu'UN de ces seuils tombe :
1. Control / Data / Audit Plane sur des **hotes separes** (un fichier SQLite ne se partage pas en reseau).
2. Besoin de **plusieurs ecrivains concurrents** sur l'event store.
3. Throughput d'append soutenu > ~quelques milliers/s.

Migration indolore car `EventStore` est un trait : ecrire `PostgresEventStore`, garder le reste.
`sqlx` supporte les deux moteurs (queries verifiees a la compilation). Attention aux
differences de dialecte (AUTOINCREMENT vs BIGSERIAL, types) -- isolees dans l'impl du trait.

NATS JetStream reste le transport temps reel dans les deux phases (jamais la source de verite).

## Autres options (non retenues, conservees pour reference)

### Option A -- PostgreSQL event-sourcing
- Log = table append-only `events` (PK `event_id` ULID, ordre par sequence monotone).
- Projections = tables read-model reconstruites par des handlers.
- NATS JetStream pour le transport temps reel (pas la source de verite).
- Pour : ecosysteme Rust mur (`sqlx`), transactions, requetes riches, ops simples.
- Contre : ordre global a gerer (sequence), throughput d'append a surveiller.

### Option B -- EventStoreDB (Kurrent)
- Store dedie event-sourcing : streams, immutabilite, subscriptions natives.
- PostgreSQL pour les read-models/projections.
- Pour : semantique event-sourcing native, ordering par stream, replay first-class.
- Contre : composant supplementaire a operer, ecosysteme Rust moins mur.

### Option C -- NATS JetStream comme source de verite
- Stream persistant JetStream = event log ; projections materialisees ailleurs.
- Pour : un seul systeme pour transport + persistance.
- Contre : garanties d'immutabilite/retention a configurer finement, requetage historique limite, risque de purge.

## Criteres de decision

1. Garanties d'immutabilite et de retention illimitee du log.
2. Ordering deterministe (global ou par stream) exploitable au replay.
3. Maturite de l'ecosysteme Rust (driver, tests, ops).
4. Cout operationnel (nombre de composants a maintenir).
5. Capacite de requetage forensique sur l'historique.

## Checklist d'implementation Phase 1 (SQLite)

- [ ] Trait `EventStore` defini AVANT toute impl (append, read_from_seq, replay).
- [ ] `SqliteEventStore` : table `events` INSERT-only + triggers anti-UPDATE/DELETE (I1).
- [ ] `seq` monotone + `event_id` ULID/UUIDv7 ; ordre de replay base sur `seq` (I4).
- [ ] `PRAGMA journal_mode=WAL`, `PRAGMA foreign_keys=ON`.
- [ ] hash chain `prev_hash` calcule a l'append, verifiable par le pipeline de validation.
- [ ] Test de replay deterministe (cf. `determinism-replay.md`).
- [ ] Aucune requete SQLite directe hors de l'impl du trait (pas de couplage).

## Quand basculer en Phase 2

Inscrire ici la date + le seuil declencheur atteint, livrer `PostgresEventStore`, basculer la
construction du trait par config (`AGENTRAIL_EVENT_STORE=sqlite|postgres`).
