# Plan : APEX -- tableau de bord agents + composition d'actions depuis le catalogue
Date : 2026-06-12
Status : TERMINE
Invariants concernes : I4 (replay deterministe des scenarios), I5 (actions via proxy lab)

## Objectif
Donner a l'equipe une vue de controle claire : lancer/arreter les agents, voir
leur statut (actif/inactif), distinguer en un coup d'oeil les deux axes mock/reel
(IA reelle vs mock ; cible simulee vs reelle). Et composer ce qu'un agent FAIT en
piochant dans le catalogue d'actions canoniques (read_repo, open_pr, ...), pas en
tapant du JSON.

## Contexte (decisions amont, deja validees)
- Le repo est la plateforme de recette des outils discovery/identification.
- Le bon catalogue d'actions d'agent = recette/tools.py (11 actions canoniques),
  PAS le catalogue gouvernance de 118 actions (mock secondaire).
- Deux axes mock/reel : IA (ai_mode mock|real + ai_backend) et cible (runtime lab|real).

## Etapes
- [x] Backend : GET /agent-actions (id + description + classe read/write) depuis tools.py
- [x] Backend : GET /runs (liste pour le statut par agent)
- [x] Agent model : champs ai_mode + scenario (stockes, config_store accepte deja le libre)
- [x] Dashboard : page d'accueil, table agents (Cible, IA badge, En-face badge, Statut live, Lancer/Stop), compteurs
- [x] Agents : selecteur ai_mode + composition du scenario via checkboxes du catalogue d'actions
- [x] Aide : topic dashboard ajoute
- [x] Nav/route : Dashboard en page d'accueil

## Resultat
Livre. Preuve live (R14) : GET /agent-actions = 11 actions ; GET /runs rend le
statut par agent_id ; launch lane_b depuis le chemin dashboard -> completed ;
console 200. Gates : tsc 0, vitest 45/45, vite build OK, python 4/4
(test_api_campaigns). Deux axes mock/reel exposes par agent (ai_mode + runtime)
et affiches en badges sur le tableau de bord. Scenario compose depuis le
catalogue d'actions (checkboxes) -> capability_scope + scenario deterministe (I4).

## Decisions prises
- Scenario = liste de decisions (tool_call) derivee des actions cochees + un final ; reutilise le chemin stub_script lane_b (mock) -> replay deterministe (I4).
- Statut agent = dernier run de /runs filtre par agent_id (poll 2s), pas de nouveau stockage.

## Recette (gates)
- React : tsc --noEmit, vitest, vite build ; smoke live (lancer depuis dashboard -> statut bascule actif puis completed).
- Python : ruff + mypy sur les fichiers touches ; test API agent-actions.

## Resultat
(en cours)
