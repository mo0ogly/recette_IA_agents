# Plan : G4 -- Realtime transport (Data Plane) + console live feed

Date : 2026-06-13
Status : TERMINE
Invariants concernes : I1 (bus jamais source de verite), I5 (transport mediatise), failure-modes (buffer borne + retry, aucune execution externe entre-temps).

## Objectif

Diffuser en temps reel chaque evenement gouverne (executed/denied/requested/resolved/error)
vers la console, SANS jamais faire du transport la source de verite. L'event store reste la
verite durable (I1) ; le realtime est un fan-out derive, rejouable depuis le store.

## Decision d'architecture

Seam = decorateur `PublishingEventStore` autour du trait `EventStore` (mirror du `TracingProxy`
qui decore le proxy). append() ecrit dans le store (verite, I1) PUIS publie best-effort. Gateway
et impls de store (sqlite/postgres) INCHANGES. La publication n'est jamais dans le chemin de
decision (`decide()` reste pur, I4) -- elle est post-append.

Phasage (mirror G3 SQLite/Postgres) :
- Phase 1 defaut : `InProcessTransport` -- transport pub/sub REEL en process (mono-hote), pas un
  stub. Comme SQLite est le store reel Phase 1.
- Phase 2 opt-in : `NatsJetStreamTransport` derriere le meme protocol, `AGENTRAIL_REALTIME=nats`,
  `AGENTRAIL_NATS_URL` (R5/R8), extra `[nats]`. Verifie contre un vrai NATS (docker) ou flag residuel.

"No loss" garanti par le STORE (durable, I1), pas par le buffer : un overflow buffer ne perd pas
d'evenement car il est deja persiste -- le realtime est rejouable depuis le log. Le buffer borne +
retry (`BoundedRetryBuffer`) couvre la degradation du downstream (failure-modes) sans jamais lever
dans la gateway ni bloquer l'append.

## Etapes
- [x] protocol.py : `RealtimeTransport` Protocol + `Subscription`
- [x] inproc.py : `InProcessTransport` (defaut Phase 1, fan-out borne par abonne)
- [x] buffer.py : `BoundedRetryBuffer` (degradation downstream, borne + retry, jamais raise gateway)
- [x] publishing_store.py : `PublishingEventStore` decorateur (store first, publish best-effort)
- [x] __init__.py : `build_realtime_transport_from_env()` (inproc defaut | nats opt-in)
- [x] tests unit : protocol/inproc/buffer/decorator + CHAOS (transport down -> buffer, store intact)
- [x] SSE router `GET /events/stream` + wiring app.py (decore le store, expose le transport)
- [x] console : page Live Events (EventSource) + api client + fixture + contract test (R16) + smoke live
- [x] NATS adapter + verif docker REELLE (3/3 contre nats:2.10 -js)
- [x] runbook `docs/runbooks/realtime-transport.md` + 2 mermaid (mmdc valides)
- [x] RETEX (RETEX_APEX_g4-realtime-transport_2026-06-13.md)

## Decisions prises
- Decorateur store (pas hook gateway) -> impls store + gateway intactes, mirror TracingProxy.
- In-process transport = Phase 1 reel (pas stub), NATS = Phase 2 opt-in mirror G3.
- No-loss porte par le store durable, pas le buffer.

## Ecarts et replanification
- (a remplir)

## Resultat
- (a remplir)
