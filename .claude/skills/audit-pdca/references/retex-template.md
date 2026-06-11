# RETEX TEMPLATE -- Templates A_RETEX.md, A_IMPROVEMENTS.md et DASHBOARD.md

> Ce fichier contient les templates complets pour la phase A.4 du cycle PDCA.
> Utiliser /retex-analyzer en priorite. Si indisponible, generer manuellement avec ces templates.

## Template A_RETEX.md

```markdown
# RETEX -- Cycle {N} -- {perimetre}

Date : {YYYY-MM-DD}
Score global : {score}/100 (objectif : {objectif})
Cout cycle : {cost_tokens} tokens (~${cost_estimate_usd}) -- relever depuis la statusline (claude-hud session-cost) ; ferme le gap cout inter-session

## Objectifs du cycle
- Score vise : X -> Atteint : Y (delta +/-Z)
- Domaines en progres : [liste avec delta]
- Domaines en stagnation : [liste]
- Regressions : [liste avec analyse cause]

## Efficacite du processus
- Temps estime : Xh -> Temps reel : Yh
- Nombre de findings : X (dont Y faux positifs)
- Agents lances : N (dont M utiles, P redondants)
- Skills chainees : [liste avec resultat]

## Dead code triage (C.0)
- Fichiers audites : X
- ACTIF : X (scores dans scorecard)
- PROTOTYPE : X (exclus, signales)
- DEAD : X (exclus, proposes .disabled)
- Ratio dead code : X% (target < 10%)

## Surprises
- Fonctionnalites deja faites non detectees avant
- Bugs non prevus decouverts
- Dependances cachees

## Decisions
- Bien marche : [liste]
- Mal marche : [liste avec pourquoi]
```

## Template A_IMPROVEMENTS.md

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

## Quick wins pour cycle N+1
- [liste des quick wins identifies mais pas encore faits]

## Objectifs cycle N+1
- Score cible : current + delta_realiste
- Focus : [domaines avec plus grand potentiel]
- Risques : [regressions possibles a surveiller]
- Prompts a regenerer : [domaines dont le prompt doit evoluer]
```

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
```

## Mise a jour post-cycle

Apres generation du RETEX :

1. **METTRE A JOUR SCORING_CONFIG.json** avec les ameliorations de A_IMPROVEMENTS.md
   - Incrementer le champ `version`
   - Appliquer les ajouts/retraits/ajustements de checks
   - Appliquer les modifications de poids

2. **METTRE A JOUR DASHBOARD.md** :
   - Ajouter la ligne du cycle courant
   - Mettre a jour les tendances par domaine
   - Lister les regressions detectees
   - Logger l'evolution du SCORING_CONFIG
