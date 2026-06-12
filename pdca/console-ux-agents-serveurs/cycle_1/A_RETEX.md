# RETEX PDCA -- console-ux-agents-serveurs Cycle 1

Date : 2026-06-12
Commit : 82a0640
Score : ~75 -> 94 (target 95, COMPLETE-below-target, residu structurel)

## Ce qui a ete fait

| Domaine | Avant | Apres | Preuve |
|---------|-------|-------|--------|
| testing | 62 | 96 | +31 tests (test_runners.py 20, test_campaign_templates.py 11), 2 modules en ImportError repares (garde fastapi), suite verte 2 envs (473 tests) |
| code_hygiene | 80 | 95 | ruff check + format + mypy clean sur tout fichier touche |
| architecture | 90 | 92 | I4/I5 verrouilles par tests (replay, fail-safe routing) |
| completeness | 85 | 93 | 17 templates valides contre le catalogue + executes bout-en-bout |

## Trous combles

- recette/api/runners.py (376 LOC, coeur du fonctionnement agent/serveur) : 0 test dedie -> 20.
  Branches d'erreur campagne toutes couvertes (agent inconnu, champs manquants, mock sans
  scenario, backend absent, server dangling -> step_error, jamais crash, jamais fallback).
- recette/api/campaign_templates.py (232 LOC) : 0 test -> 11, dont la preuve que chaque
  action de chaque template est une action reelle du catalogue de son target_system.
- tests/test_api_platform.py + test_api_verdicts.py : import fastapi sans garde -> la suite
  etait en FAILED hors venv. Pattern skipUnless(_HAS_FASTAPI) applique (classes pures
  restent toujours executees).

## Ce qui a marche

- Lecture du code source avant ecriture des tests (R13) : zero test rouge a la premiere
  execution (20/20 puis 11/11).
- Doubles de test legers dans tests/ (FakeConfigStore/FakeRecordingStore) au lieu de
  monter FastAPI : les runners sont de l'orchestration pure, tests en 2 ms.

## Ce qui a coince

- Arbre partage avec une session concurrente : 1 erreur transitoire pendant un run de
  suite (fichier en cours d'ecriture par l'autre session), comptes de tests mouvants
  (467 -> 473). Resolution : re-run, scope de commit filtre (WIP de l'autre session
  -- recette/__main__.py, tests/test_cli.py -- non commite, flag-not-sweep).
- Derive de formatage ruff sur 3 fichiers de tests commits par l'autre session :
  reformates ici (mecanique, zero risque).

## Ameliorations cycle N+1

- Smoke Playwright console (pages Serveurs/Campagnes) si un cycle modifie le frontend.
- server_manager.py : test du nettoyage AGENTRAIL_LAB_ACCESS_LOG sur stop (si absent).
- Mypy sur recette/api/ complet (1 erreur corrigee ici etait dans config_store).
