# TODO APEX -- Platform gaps vers enterprise-ready

Date : 2026-06-13
Statut : TODO (backlog priorise, a executer par APEX, 1 vague = 1 gap)
Perimetre : la PLATEFORME de gouvernance (pas le track recette RAG-KB, qui est clos).
Source : audit factuel du repo le 2026-06-13 (commandes executees, R13/R18 -- pas de
gap suppose). Chaque item cite l'etat reel verifie.

## Etat reel verifie (baseline -- ce qui EXISTE deja)

Le coeur de gouvernance est implemente en **Python** (`recette/platform/`), fonctionnel :
- Gateway (`platform/gateway.py`), Policy engine `decide()` deterministe (I4), Risk,
  Catalog (12 domaines, 124 actions, 12 roles).
- Proxy mediatise : `ExternalSystemProxy` (protocol) + `RealForgeProxy` + `side_effect_hash` (I5).
- Event store : `SqliteEventStore` append-only + triggers anti-UPDATE/DELETE (I1) +
  `hashchain`, `InMemoryEventStore`, trait `protocol.py`.
- Approval : `platform/approvals/state_machine.py` (machine d'etat des `approval_state`).
- API console (FastAPI, extra `[api]`) : 15 routers, et la recette (corpus, campagnes,
  discovery, MAF, RAG poisoning) -- 713 tests verts.

Donc : reference/banc-de-test de qualite. Les gaps ci-dessous separent ca d'un
**runtime de gouvernance deployable en entreprise**.

## Gaps priorises

### G1 -- AuthN/AuthZ sur l'API (I3) -- CRITIQUE
- Constat verifie : `grep Depends|Security recette/api/routers/` = **0 hit**. Toutes les
  routes (`/actions/execute`, `/config/*`, `/policies`, `/rag/*`, `/approvals`...) sont
  **non authentifiees**. I3 (liaison crypto a une identite) n'est pas applique sur la
  surface HTTP.
- Cible : middleware d'auth (mTLS ou JWT signe via `AGENTRAIL_JWT_SIGNING_KEY`), resolution
  d'`agent_id`/operateur, refus par defaut, echec d'auth audite (evenement). Operateur de
  la console = identite distincte d'un agent.
- Done : route non authentifiee -> 401 ; identite liee a chaque `PlatformActionEvent` ;
  test d'echec d'auth -> evenement d'audit.
- Pipeline : PYTHON. Invariants : I3, I2.

### G2 -- Approbation durable (I6) -- HAUTE
- Constat verifie : `temporalio>=1.7` est un extra optionnel ; `approvals/__init__.py` dit
  "Temporal durable workflow; ApprovalService is the interface Temporal would [implement]".
  La durabilite n'est pas cablee -> une approbation `escalate` ne survit pas a un redemarrage.
- Cible : implementer `ApprovalService` sur un workflow durable (Temporal), timeout =>
  comportement explicite (escalate/freeze/deny, jamais auto-approve), zero sleep en memoire.
- Done : kill du process pendant un `pending` -> l'approbation reprend ; test de timeout.
- Pipeline : PYTHON (+ Temporal). Invariant : I6.

### G3 -- Event store Phase 2 PostgreSQL -- [FAIT 2026-06-13, OPTION dormante, branch feat/g3-postgres-eventstore]
- IMPORTANT : SQLite RESTE LE DEFAUT. Postgres est une option opt-in, code dormant tant
  que `AGENTRAIL_EVENT_STORE=postgres` n'est pas mis. Aujourd'hui = 100% SQLite, inchange.
- Livre : `PostgresEventStore` derriere le meme trait `EventStore` (parite append/read_from/
  get_by_event_id/verify_chain), `seq BIGSERIAL` (ordre total I4), triggers anti UPDATE/DELETE
  (I1), hash chain byte-identique (chain_hash canonicalise), `pg_advisory_xact_lock` sur
  l'append -> chaine non-forkee sous ecrivains concurrents (la vraie valeur Phase 2).
  Bascule `build_event_store_from_env()` via `AGENTRAIL_EVENT_STORE=sqlite|postgres`, DSN
  `AGENTRAIL_DATABASE_URL` (R8). psycopg = extra optionnel `[postgres]`.
- Verifie : `tests/test_eventstore_postgres.py` 9/9 contre un VRAI Postgres 16 (docker
  ephemere) -- mirror suite SQLite + immutabilite + tamper + concurrence multi-writer.
  Skip si pas de `AGENTRAIL_TEST_POSTGRES_DSN` (suite par defaut sans Postgres). Runbook
  `docs/runbooks/event-store-postgres.md` + 2 mermaid.
- RESIDUEL : la MIGRATION du flux SQLite existant vers Postgres (replay du log) est un acte
  operateur, non automatise. A faire au cutover reel.
- Pipeline : PYTHON. Invariants : I1, I4.

### G4 -- Transport temps reel NATS JetStream -- MOYENNE
- Constat verifie : NATS/JetStream seulement mentionnes (docs/enums), aucune dep ni client.
- Cible : bus JetStream pour la diffusion des evenements (jamais source de verite, I1) ;
  degradation -> buffer local borne + retry, AUCUNE execution externe entre-temps
  (failure-modes.md). Realtime vers la console.
- Done : un evenement emis arrive a un consumer ; chaos-test (kill bus) -> buffer, pas de perte.
- Pipeline : PYTHON. Invariants : I1, I5.

### G5 -- Proxies reels par domaine (I5) -- MOYENNE
- Constat verifie : `RealForgeProxy` couvre la forge (git). Les 11 autres domaines
  (okta, crm, finance, data_platform, slack, support_desk, cloud, hris, legal_dms,
  product_cms, knowledge_base) n'ont pas de proxy reel (lab seulement).
- Cible : un `ExternalSystemProxy` par systeme externe cible, detenteur exclusif des
  credentials (via env/secret store, R8), `side_effect_hash` calcule, mockable en test.
- Done : 1 proxy reel supplementaire bout-en-bout + son test de replay ; credentials hors code.
- Pipeline : PYTHON. Invariant : I5, R8.

### G6 -- Ops : CI gates + observabilite + secrets -- MOYENNE
- Constat : gates `ruff/mypy/bandit` existent localement (Makefile), mais pas de pipeline CI
  qui les bloque ; pas de stack tracing/metrics ; secrets via env seulement.
- Cible : CI (gates + 713 tests + system-recette en bloquant), tracing structure correle
  par `event_id`/`agent_id` (R6), secret manager branche aux proxies.
- Done : CI rouge bloque un merge ; un trace forensique correle un flux ; secret hors env brut.
- Pipeline : INFRA/PYTHON.

### G7 -- Runtime Rust de production (strategique) -- STRATEGIQUE
- Constat verifie : le seul Rust est `cmd/agentrail_recette` (scanner discovery). Le stack
  cible (CLAUDE.md) = Gateway Axum + planes en Rust. Le coeur tourne aujourd'hui en Python.
- Cible : decider explicitement -- (a) Python reference reste la prod, OU (b) port Rust/Axum
  des planes critiques (gateway/policy/risk) pour perf/garanties. Decision a tracer
  (`decision_log.jsonl`) AVANT tout port.
- Done : decision documentee ; si port, parite de comportement prouvee par replay sur un
  stream commun Python<->Rust.
- Pipeline : DECISION puis RUST. Invariants : tous (parite I1-I6).

## Ordre d'execution recommande

1. **G1 (auth)** -- bloquant securite, surface deja exposee.
2. **G2 (approbation durable)** -- I6 est un invariant, actuellement non durable.
3. **G3 (Postgres)** -- des qu'un 2e hote/ecrivain entre en jeu.
4. G6 (CI/observabilite) en parallele (transverse).
5. G5 (proxies), G4 (NATS) selon les domaines vises.
6. G7 (Rust) -- decision strategique, pas avant que le comportement Python soit fige.

## A executer

```
/apex -t -b G1 auth middleware (I3) sur l'API : JWT/mTLS, agent_id lie, deny-by-default, echec audite
```
(puis une vague APEX par gap, en suivant l'ordre ci-dessus.)
