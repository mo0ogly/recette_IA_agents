# RETEX -- RAG-KB finition (T1-T5 + doc mermaid + audit-pdca)

Date : 2026-06-13
Scope : recette/rag_store.py, corpus/rag, tests RAG, runbook RAG-KB, console favicon
Plan : docs/tracking/PLAN_APEX_rag-kb-finition-t4t5-doc_2026-06-13.md (TERMINE)
Statut : TERMINE -- reliquat RAG-KB = 0

## Objectif

Fermer le reliquat de finition de la feature RAG-KB CRUD + poisoning : guard
scenario decide-based (T4), durcissement id (T5), doc mermaid pour l'equipe de
recette, smoke navigateur reel (T1), audit-pdca, coherence avec rules/campagnes/maf.

## Livre

| Item | Preuve |
|------|--------|
| T4 guard scenario poisonne | `test_scenario_guard_every_poisoned_doc_is_blocked_by_the_gateway` -- decide(rag_agent, injected_action) == injected_expect et in {deny,escalate}. Negative-prouve ROUGE sur scenario menteur, reverte vert. |
| T5 durcissement id | `KnowledgeBaseStore._validate` rejette un id hors slug `^[a-z0-9][a-z0-9-]{1,63}$` (`test_add_rejects_invalid_id_slug`). Ids legitimes kb-*/scn-* intacts. |
| Doc mermaid | runbook + 3 diagrammes valides via `mmdc` : frontiere I2 (operator vs agent path), sequence poisoning, double guard CI. |
| T1 smoke navigateur | headless puppeteer sur /rag : flux load 8 -> apply exfil-finance -> 9 (scn-exfil-finance) -> reset -> 8, zero erreur console app, screenshot. R26 satisfait. |
| favicon.ico | A monogram cyan/navy multi-taille, console/public + link index.html ; sert 200, resout le 404 du smoke. |
| audit-pdca | security 20/20, testing 14/15, doc 10/10 (apres docstrings CRUD), arch 14/15 -> ~96/100 >= target 90. |

## Coherence verifiee

- rules : I2 anti-backdoor (store hors chemin agent, ingest_document escalate), I4
  reset/decide deterministe, recette-corpus negatifs mono-axe.
- campagnes : 4 campagnes rag vertes (8 paires role/action, 0 mismatch), guards
  alignent scenarios <-> decide.
- maf (autre session) : `validate` = 11 orchestration teams valid, system-recette
  LEG A3 = 0 dup catalogue cross-famille. Pas touche (R28 flag-not-sweep).

## Mesures finales (faits, R13)

- Suite : 713 tests OK (9 skip = SDK [real]).
- system-recette : PASS (LEG A coherence + B smoke + C flux).
- gates : ruff + mypy (119 fichiers) + bandit clean sur le delta.
- 4 commits scope-only pushes : dd10e3b, e6cf0d2, 0516d64 (+ favicon), zero fichier
  flux/maf de l'autre session touche.

## Agentic score

APEX 45/50, PDCA 44/50. C2 limite par audit inline (pas de swarm -- choix cout).

## Ce qui a marche

- Guard decide-based : exact-by-construction (le policy engine decide sur le role),
  donc le guard prouve le blocage sans flottement.
- Smoke navigateur reel malgre absence de Playwright MCP : puppeteer global (mmdc),
  contournement IPv6/CORS par `--host-resolver-rules` + CORS origin dedie.

## Ce qui a coince (et resolu)

- Browser ERR_CONNECTION_REFUSED : chrome resout localhost -> ::1, API en IPv4 ->
  `--host-resolver-rules=MAP localhost 127.0.0.1`.
- CORS 5174 : origin dedie via AGENTRAIL_CORS_ORIGINS.
- Double-comptage du 404 favicon dans le gate : gate reseau autoritatif `bad` (avec
  URL, favicon exclu) + filtre du message console generique.

## Reste / hors-scope

- Aucun reliquat RAG-KB.
- Hors-scope (plateforme, pas ce track) : voir verdict enterprise ci-dessous.
