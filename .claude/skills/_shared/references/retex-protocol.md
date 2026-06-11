# RETEX Protocol -- Reference partagee APEX & PDCA v6.0

> Templates RETEX, DASHBOARD, IMPROVEMENTS. Utiliser /retex-analyzer en priorite.

---

## Template RETEX APEX

```markdown
## RETEX APEX -- {titre}
Date : {YYYY-MM-DD}
Score agentique : {N}/50
Cout session : {cost_tokens} tokens (~${cost_estimate_usd}) -- relever depuis la statusline (claude-hud session-cost) en fin de cycle ; ferme le gap cout inter-session

| Critere | Score | Commentaire |
|---------|-------|-------------|
| C1 Decomposition | /10 | Sous-taches 3-7, complexite scoree, dependances |
| C2 Planification (THINK) | /10 | Research + 2+ alternatives + critique adversariale |
| C3 Replanification | /10 | REPLAN sur FAILURE, 2+ alternatives |
| C4 Outillage | /10 | Model haiku/sonnet selectionne, skills invoquees |
| C5 Tracabilite | /10 | action_journal + decision_log + RETEX affiche |

Sous-taches : {N} total, {S} SUCCESS, {P} PARTIAL, {F} FAILURE, {R} REPLAN
Boucles OODA : {N} cycles total
Build pipeline Rust : {score}/5
Build pipeline Python : {score}/5
Build pipeline React : {score}/8

Ce qui a fonctionne : ...
Ce qui a echoue : ...
Ameliorations : ...

## Recette corpus delta (c{prev} -> c{curr})  -- si le cycle touche le corpus d'agents de test

> If the cycle added/removed/modified test-agent manifests, scenarios or
> ground-truth under `corpus/agents/`, run `python3 -m recette validate`
> and paste the agent counts here. If the cycle is tooling/docs/audit-only,
> state explicitly "zero corpus modification expected -- delta +0 confirmed".

- corpus.agents.total: {delta}
- corpus.correct: {delta}
- corpus.incorrect: {delta}
- detection_rate / accuracy-per-dimension: {unchanged vs c{prev} | regressed | improved}
```

---

## Template RETEX PDCA

```markdown
## RETEX PDCA -- {perimetre} Cycle {N}
Date : {YYYY-MM-DD}
Score : {avant} -> {apres} (+{delta})
Score agentique : {N}/50
Cout cycle : {cost_tokens} tokens (~${cost_estimate_usd}) -- relever depuis la statusline (claude-hud session-cost) en fin de cycle ; ferme le gap cout inter-session

| Domaine | Avant | Apres | Delta |
|---------|-------|-------|-------|

| Critere | Score |
|---------|-------|
| C1 Decomposition | /10 |
| C2 Planification (THINK) | /10 |
| C3 Replanification | /10 |
| C4 Outillage | /10 |
| C5 Tracabilite | /10 |

Boucles OODA : {N} cycles
Build pipeline Rust : {score}/5
Build pipeline Python : {score}/5
Build pipeline React : {score}/8

Ce qui a fonctionne : ...
Ce qui a echoue : ...
Ameliorations cycle N+1 : ...

## Recette corpus delta (c{prev} -> c{curr})  -- si le cycle touche le corpus d'agents de test

> Same rule as APEX template. Generate via `python3 -m recette validate`.
> If cycle is tooling/docs/audit-only, state explicitly "zero corpus
> modification expected -- delta +0 confirmed".

- corpus.agents.total: {delta}
- corpus.correct: {delta}
- corpus.incorrect: {delta}
- detection_rate / accuracy-per-dimension: {unchanged | regressed | improved}
```

---

## Template A_IMPROVEMENTS.md (PDCA)

```markdown
# IMPROVEMENTS -- Cycle {N} -> Cycle {N+1} -- {perimetre}

## Ameliorations SCORING_CONFIG
- AJOUTER checks : [nouveau check ID, nom, query, justification]
- RETIRER checks : [check ID, raison (faux positif, obsolete)]
- AJUSTER poids : [domaine, ancien poids -> nouveau poids, justification]
- NOUVEAU domaine : [nom, poids, checks initiaux]

## Ameliorations prompts agents
- Agent "{domaine}" : prompt trop vague sur X -> ajouter instruction Y
- Agent "{domaine}" : a cherche dans le mauvais repertoire -> preciser scope
- Agent "{domaine}" : rapport manquait le comptage de Z -> ajouter dans le prompt

## Ameliorations pipeline
- Skill X a ete utile / inutile dans ce contexte
- Ajouter skill Y au pipeline pour le prochain cycle
- L'ordre des phases devrait etre modifie : [justification]

## Ameliorations swarm_memory
- Les agents ont/n'ont pas utilise les known_issues -> ajuster le protocole
- Les discoveries ont/n'ont pas ete croisees efficacement -> ajuster le seuil de relance

## Quick wins pour cycle N+1
- [liste des quick wins identifies mais pas encore faits]

## Objectifs cycle N+1
- Score cible : current + delta_realiste
- Focus : [domaines avec plus grand potentiel]
- Risques : [regressions possibles a surveiller]
- Prompts a regenerer : [domaines dont le prompt doit evoluer]
```

---

## Template DASHBOARD.md

```markdown
# DASHBOARD PDCA -- {perimetre}

## Progression multi-cycles

| Cycle | Date | Score | Delta | Objectif | Status |
|-------|------|-------|-------|----------|--------|
| 001   | YYYY-MM-DD | XX/100 | baseline | baseline | done |
| 002   | YYYY-MM-DD | XX/100 | +/-N | XX/100 | done |

## Tendances par domaine

| Domaine | Cycle 1 | Cycle 2 | ... | Tendance |
|---------|---------|---------|-----|----------|
| security | XX | XX | ... | improving/stable/declining |
| testing  | XX | XX | ... | improving/stable/declining |

## Regressions detectees

| Cycle | Domaine | Score avant | Score apres | Cause | Action |
|-------|---------|-------------|-------------|-------|--------|

## SCORING_CONFIG evolution

| Version | Cycle | Changements |
|---------|-------|-------------|
| 1 | 001 | Initial (defaut) |
| 2 | 002 | +check SEC-07, poids security 20->25 |

## Swarm memory evolution

| Cycle | Agents | Known issues injectees | Discoveries croisees | Relances |
|-------|--------|----------------------|---------------------|----------|
```

---

## Post-cycle (mise a jour)

1. **METTRE A JOUR SCORING_CONFIG.json** avec A_IMPROVEMENTS.md
   - Incrementer `version`
   - Appliquer ajouts/retraits/ajustements
2. **METTRE A JOUR DASHBOARD.md** :
   - Ajouter ligne du cycle courant
   - Mettre a jour tendances par domaine
   - Lister regressions detectees
   - Logger evolution SCORING_CONFIG
   - Logger evolution swarm memory
3. **AFFICHER le RETEX** dans la conversation (pas juste ecrire le fichier)
