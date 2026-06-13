# Plan : HTTP side-effect proxy -- debug mode + real_saas wiring + Monaco trace console
Date : 2026-06-13
Status : TERMINE
Invariants concernes : I1 (traces are a read-only view, never mutate the log), I4 (no wall-clock in trace records -> deterministic), I5 (every side effect stays behind a proxy), R5 (config), R8 (real token via env), R16 (frontend contract gate)

## Objectif
Rendre le proxy HTTP side-effect (I5) debuggable et parametrable : un mode debug qui
trace chaque execute() (request + response + side_effect_hash), le branchement real_saas
manquant (router rendait ValueError), une console Monaco read-only cote frontend, plus
tests, docs et aide UI.

## Alternatives (THINK 2b)
- A (RETENUE) Decorateur TracingProxy enveloppant tout ExternalSystemProxy + RingTraceRecorder.
  real_saas via factory injectee dans resolve_proxy (purete du router preservee). Pros: SRP,
  debug uniforme lab+real, retro-compatible. Cons: un sink de traces a exposer.
- B (REJETEE) Flag debug interne a LabHttpProxy. Cons: duplique dans le real proxy, viole SRP,
  pas uniforme.

## Etapes
- [x] S1 TracingProxy + RingTraceRecorder (recette/platform/proxy/tracing.py) + tests (10)
- [x] S2 RealForgeProxy real_saas adapter (recette/platform/proxy/real_proxy.py) + tests (7)
- [x] S3 resolve_proxy real_proxy_factory injection (router.py) + tests (retro-compat, +3)
- [x] S4 Config parametrable AGENTRAIL_PROXY_DEBUG (debug_enabled_from_env, hors router)
- [x] S5 API GET/DELETE /proxy/traces + /proxy/debug (routers/proxy.py) + contract tests (5)
- [x] S5-bis Lane B + campaign wiring : forge_for_agent wrappe le proxy resolu (real agents traces)
- [x] S6 Frontend ProxyPage (Monaco read-only) + proxyTraceModel + R16 fixture reel + tests (13)
- [x] S7 Docs runbook (docs/runbooks/proxy-debug-console.md) + UI help (topic proxy + maj servers)
- [x] S8 RECETTE : ruff/mypy clean (9 fichiers), 579 backend + 175 frontend tests, live uvicorn smoke

## Ecarts et replanification
- ECART (souleve par feedback utilisateur "il fonctionne avec nos agents?") : le chemin Lane B
  reel (ProxyForge via forge_for_agent) n'etait PAS trace -- seul le chemin gateway l'etait.
  Correction S5-bis : recorder injecte dans forge_for_agent + make_lane_b_runner + make_campaign_runner.
  Preuve : tests/test_api_proxy_traces_lane_b.py (agent reel read_repo+open_pr -> traces).

## Decisions prises
- Traces sans horloge murale (seq monotone only) -> I4 determinisme.
- router reste pur : real_saas branche via factory injectee au call-site (runners/api), pas dans le router.
- Recording fail-safe : une erreur d'enregistrement ne casse jamais execute() (failure-modes).
- Decorateur (pas flag interne) -> trace uniforme lab + real, SRP.

## Resultat
Livre et verifie. Backend (decorateur + real proxy + wiring gateway ET lane B + API) +
frontend (page Monaco read-only, route, aide) + docs. Mode debug parametrable par
AGENTRAIL_PROXY_DEBUG, fail-safe, I1/I4/I5 respectes. Zero regression (579 + 175 tests verts).
