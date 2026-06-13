# Plan APEX : MCP discovery surface
Date : 2026-06-13
Status : EN_COURS
Invariants : I4 (determinisme scan), I5 (MCP = side-effect surface), deny-by-default

## Objectif
Surface discovery "mcp" : scanner les serveurs MCP declares par un agent (mcp.json),
emettre des DiscoveryRisk (target=mcp), scorer sur les invariants discovery. End-to-end :
backend + corpus + API + frontend console + doc.

## Alternatives
- A [CHOISI] : enum action_patterns etendu (invoke_tool/handoff) + _from_mcp + corpus/manifests.
- B [rejete] : module scanner mcp separe (plus de fichiers, aucun gain).

## Subtasks
- [ ] S1 schema : ajouter invoke_tool/handoff a discovery-ground-truth action_patterns enum.
- [ ] S2 scanner : ReferenceSourceScanAdapter._from_mcp (mcp.json -> risks, level approval-driven).
- [ ] S3 corpus : corpus/manifests/<slug> (1 detecte gated, 1 detecte bounded, 1 true-negative).
- [ ] S4 tests : tests/test_discovery_mcp.py (scan, determinisme, surface dans report).
- [ ] S5 API : verifier /subjects/scorecard expose mcp (auto via SURFACE_ORDER) + test.
- [ ] S6 frontend : console/ composant Discovery scorecard (surfaces incl mcp) + contract test.
- [ ] S7 doc : runbook docs/ + README corpus/manifests.

## Gate
audit-pdca --fix + recette validate + recette report + unittest (venv) + vite build + vitest.
Baseline tests: 650 (venv).
