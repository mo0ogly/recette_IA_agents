# Plan APEX : MCP discovery surface
Date : 2026-06-13
Status : TERMINE (REPLAN: backend mcp existait deja -> recentre sur API/frontend/doc)
Invariants : I4 (determinisme scan), I5 (MCP = side-effect surface), deny-by-default

## Objectif
Surface discovery "mcp" : scanner les serveurs MCP declares par un agent (mcp.json),
emettre des DiscoveryRisk (target=mcp), scorer sur les invariants discovery. End-to-end :
backend + corpus + API + frontend console + doc.

## Alternatives
- A [CHOISI] : enum action_patterns etendu (invoke_tool/handoff) + _from_mcp + corpus/manifests.
- B [rejete] : module scanner mcp separe (plus de fichiers, aucun gain).

## REPLAN (S1-S4 annules)
Decouverte en Phase 1 (R18) : la surface mcp EXISTE DEJA, committee (d3a7f03 feat(mcp): M1).
Elle utilise corpus/manifests/<slug>/repo/.agentrail/manifest.json (target_system=mcp, actions
git) via _from_manifest. Mon S2 _from_mcp (mcp.json-with-tools) detectait A TORT le leurre
true-negative mcp-no-agent -> surface 6/6 -> 5/6. REVERT total backend (scanner + enum + 2 dirs).
Recentrage sur le vrai gap : API/frontend/doc.

## Subtasks (apres replan)
- [x] S1-S4 backend : ANNULES (deja existant, mes ajouts revertes, surface mcp 4/4 PASS).
- [x] S5 API : /subjects/scorecard expose mcp (verifie live, 5 surfaces).
- [x] S6 frontend : console/src/pages/discovery (page + contract test R16 + fixture reelle). tsc 0, vitest 5/5.
- [x] S7 doc : docs/runbooks/mcp-discovery-recette.md.

## Resultat
mcp discovery cable end-to-end (backend existant -> API -> console). Zero regression :
652 tests python, recette report PASS, frontend tsc clean + vitest 5/5. Commit 2d3b92b.

## Gate
audit-pdca --fix + recette validate + recette report + unittest (venv) + vite build + vitest.
Baseline tests: 650 (venv).
