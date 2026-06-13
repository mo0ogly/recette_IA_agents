# Plan : APEX -- Server Test action (lancer/arreter/tester/debuger from UX)
Date : 2026-06-13
Status : EN_COURS
Invariants concernes : I5 (side-effects via proxy), I4 (diagnostic path, not decision -- documented)

## Objectif
Add the missing "Test" verb to the Servers UX: fire a chosen action at a running
mock_local/declared_url server and show its raw JSON response + http status.
Lancer/Arreter/Debug already exist; Test is the gap.

## Decision (alternatives)
A [CHOSEN]: reuse resolve_proxy + LabHttpProxy; new endpoint builds a minimal
  PlatformActionEvent, calls proxy.execute, returns ExecutionResult dict (fail-safe).
  Frontend: dedicated ServerTestPanel.tsx (new, <400 LOC, SRP), wired via Test button,
  reuses getCatalog(system) for the action dropdown.
B [REJECTED]: inline urllib + giant inline panel in index.tsx (575 LOC already).
  Rejected: duplicates proxy/I5 logic (DRY), grows over-ceiling file, no SRP.

## Etapes
- [ ] S1 [PY]  POST /config/servers/{id}/test endpoint (config.py) -- fail-safe, 404 unknown, 400 real_saas
- [ ] S2 [PY]  backend tests (live mock up, dangling, real_saas, unknown id)
- [ ] S3 [TS]  types ServerTestResult + client testServer()
- [ ] S4 [TSX] ServerTestPanel.tsx (action dropdown via getCatalog, resource, payload, response+status)
- [ ] S5 [TSX] wire Test button into ServersPage + servers.css
- [ ] S6 [R16] fixture captured live + ServerTestPanel.test.tsx render-and-assert

## Resultat
(en cours)
