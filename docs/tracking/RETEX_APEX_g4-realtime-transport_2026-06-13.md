# RETEX : G4 -- Realtime transport (Data Plane) + console live feed

Date : 2026-06-13
Status : TERMINE
Branch : feat/g4-realtime-transport (commits 6fd83a7 transport core, 80c7a94 SSE+console)
Invariants : I1 (bus jamais source de verite), I5 (transport mediatise), failure-modes.

## Objectif livre

Diffusion temps reel des evenements gouvernes vers la console, sans jamais faire
du transport la source de verite. L'event store reste la verite durable (I1) ; le
realtime est une vue derivee rejouable depuis le log.

## Ce qui a ete construit

| Couche | Livrable |
|--------|----------|
| Protocol | `RealtimeTransport` + `Subscription` (defini avant impl, comme `EventStore`) |
| Phase 1 | `InProcessTransport` -- pub/sub reel mono-hote, fan-out borne par abonne |
| Failure mode | `BoundedRetryBuffer` -- backlog borne + retry FIFO, ne leve jamais |
| Seam | `PublishingEventStore` decorateur (store first I1, puis publish best-effort) |
| Phase 2 | `NatsJetStreamTransport` opt-in [nats], async->sync via loop dediee |
| Factory | `build_realtime_transport_from_env()` (inproc defaut / nats) |
| API | `GET /events/stream` (SSE) + `GET /events/status` |
| Console | page "Temps reel" (EventSource, badges verdict/approbation/degrade) |

## Preuves (R14)

- Offline core : `tests/test_realtime_transport.py` 20/20 (fan-out, chaos
  degradation/recovery, ordering, factory).
- NATS REEL : `tests/test_realtime_nats.py` 3/3 contre `nats:2.10 -js` (docker),
  publish + consumer round-trip + buffer wrap. Container retire apres.
- API : `tests/test_api_events.py` 3/3 (executed + denied diffuses, status shape).
- SSE socket live : `curl -sN /events/stream` -> `: connected`, keepalive, puis
  `data: {...}` reel lors d'une execution -- capture sauvee comme fixture R16.
- Console R16 : `src/pages/live/index.test.tsx` 6/6 contre le payload reel.
- Smoke navigateur : puppeteer /live -> badge "Connecte", action declenchee ->
  ligne rendue (action_denied, deny, critical), zero erreur console, screenshot.
- Gates : ruff + ruff format + mypy (.venv ET .venv-pyaudit) + bandit clean ;
  tsc --noEmit clean + vite build OK ; 2 mermaid valides (mmdc).

## Decisions cles

1. **Decorateur store, pas hook gateway** : `PublishingEventStore` mirror du
   `TracingProxy` -> gateway et impls de store intacts, `decide()` reste pur (I4).
2. **No-loss porte par le store, pas le buffer** : tout evenement publie est deja
   persiste ; un overflow buffer ne perd qu'une copie rejouable. Ca resout la
   tension "borne MAIS sans perte" de failure-modes.md.
3. **Phasage mirror G3** : in-proc reel = Phase 1 defaut (pas un stub, comme
   SQLite), NATS = Phase 2 opt-in derriere le meme protocol. Verifie contre un
   vrai NATS avant de livrer (jamais d'adapter non verifie en repo).

## Bug rencontre et corrige (R13, pas de deduction)

Test NATS : 2/3 en echec `NotFoundError` au `subscribe`. Diagnostic par lecture
du code (pas hypothese) : nom de stream FIXE `AGENTRAIL_EVENTS` reutilise pour
des subjects de test uniques -> le stream gardait le 1er subject, les suivants
n'etaient couverts par aucun stream. Fix : `stream` parametrable
(`AGENTRAIL_NATS_STREAM`), unique par test. 3/3 ensuite.

## Residuels (honnetes, non-bloquants)

- `/events/stream` auth-allowliste : EventSource ne pose pas de header Bearer.
  Une prod a cle doit le fronter par token-in-query/cookie. Tracke.
- `BoundedRetryBuffer.flush()` pas encore branche a un scheduler : un bus retabli
  draine au prochain publish. Meme classe de residuel que le sweep des timeouts
  d'approbation (G2).
- Migration : aucune (transport sans persistance ; le store reste la verite).

## Ecart vs plan

Aucun ecart majeur. Le seul ajustement : nom de stream parametrable (decouvert au
test NATS reel). Tout le perimetre planifie (protocol, in-proc, buffer, decorateur,
NATS verifie, SSE, UX, docs) livre.

## R28 (multi-session)

- `config/agentrail.config.json` (nouveaux agents de test, autre session) : flag,
  jamais commit/revert.
- Commit `a75e4c6` (autre session, scripts/ OTel) atterri sur la branche entre mes
  deux commits ; zero overlap avec mes fichiers, laisse tel quel.
- Routeur `sim` et fichiers flux/LogConsole/viz : non touches.
