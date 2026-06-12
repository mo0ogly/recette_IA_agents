# Plan : APEX smoke-wiring -- recette.sh smoke + console Playwright smoke
Date : 2026-06-13
Status : TERMINE
Invariants concernes : I4 (replay), I5 (proxy mediate)

## Objectif
Cloturer la chaine de preuve console -> API -> serveur mock -> replay.
(1) faire de scripts/smoke_lab.py un reflexe d'equipe (sous-commande recette.sh + make).
(2) prouver le maillon navigateur reel : UI Serveurs start/stop + lancement campagne + audit.

## Etapes
- [ ] S1 cicd/smoke.sh : assure l'API up (api.sh), lance smoke_lab.py contre API_HOST:API_PORT.
- [ ] S1 recette.sh : case `smoke)` -> SMOKE_SH ; entree menu ; doc header.
- [ ] S1 Makefile : cible `smoke`.
- [ ] S2 scripts/smoke_console.py : playwright.sync_api (python3.11), navigateur reel.
      Seed serveur+agent+campagne via API, puis pilote l'UI : /servers Start->dot up,
      Stop->dot down ; /campaigns Lancer -> run completed ; /audit events visibles.
- [ ] S2 doc runbook + reflexe (recette.sh console-smoke optionnel).

## Decisions prises
- python3.11 porte playwright 1.54 (browsers en cache ms-playwright) ; .venv/system py 3.13 ne l'ont pas.
- console base URL = VITE_AGENTRAIL_API_URL (defaut localhost:8080) -> injecte vers l'API de test.
- Seed via API (backend deja prouve) + pilotage UI : isole le maillon non prouve (navigateur->API).

## Resultat
TERMINE. S1: `./recette.sh smoke` + `make smoke` -> SMOKE PASS live (API auto-start
sur 8094, flux lab complet). Bug `set -e` du wrapper corrige (capture de _rc).
S2: scripts/smoke_console.py pilote Chromium reel -> SMOKE PASS x2 (servers Start->up,
campagne Lancer->completed, Stop->down, recording visible, Replay->completed I4).
2 bugs de test reels trouves par la verif live: (a) CORS bloque un port console non
defaut -> documente ; (b) ordre serveur/campagne -- l'agent bindе exige le serveur UP
pour ses actions proxifiees (I5) -> reordonne. /audit ecarte (event store gouverne,
pas les action-logs de campagne) au profit de la table Enregistrements (trace UI reelle).
Gates: mypy clean (override playwright), ruff clean, suite 515 OK.
