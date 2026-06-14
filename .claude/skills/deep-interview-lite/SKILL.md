---
name: deep-interview-lite
description: Gate de clarte numerique des exigences AVANT de lancer un cycle apex/audit-pdca couteux. Score la requete sur 5 axes (livrable, perimetre, criteres done, contraintes, consommateur), calcule un score /100, et BLOQUE le lancement si < 70 en posant les questions manquantes via AskUserQuestion. Se declenche sur "/deep-interview-lite", "clarifie avant apex", "la demande est-elle claire", ou automatiquement en apex Phase 0 INIT si la requete est vague. Micro-version locale (pas de CLI externe) inspiree du /deep-interview OMC mais sans dependance plugin.
---

# Deep Interview Lite -- Gate de clarte avant cycle couteux

Micro-skill qui empeche de lancer un cycle apex/audit-pdca (cher : swarms,
build pipelines, recette) sur une requete floue. Score la clarte, bloque si
insuffisant, pose UNIQUEMENT les questions manquantes.

Origine : brainstorm OMC 2026-06-04 (RETEX_OMC_INTEGRATION). Le `/deep-interview`
OMC apportait un scoring de clarte additif ; cette version le reimplemente en
local sans dependance plugin ni CLI externe.

## REGLE ABSOLUE

Le gate produit un SCORE NUMERIQUE et une DECISION explicite (GO / CLARIFY).
Pas de "ca a l'air clair" implicite. Si CLARIFY, poser les questions via
AskUserQuestion AVANT toute action, jamais supposer (BLOC 0 CLAUDE.md, >= 95%).

## Quand l'invoquer

- Avant `/apex` ou `/audit-pdca` quand la requete tient en une phrase vague
  ("ameliore le module X", "fix le truc", "fais le dashboard")
- Sur demande explicite : "/deep-interview-lite", "clarifie avant apex"
- Auto en apex Phase 0 INIT si la description < 12 mots OU sans livrable nomme

Ne PAS l'invoquer si la requete est deja precise (livrable + perimetre + done
explicites) -- ce serait de la friction inutile.

## Les 5 axes (BLOC 1 CLAUDE.md), 20 points chacun

| Axe | Question gate | 0 | 10 | 20 |
|-----|---------------|---|----|----|
| 1 Livrable | Quel fichier/format/destination exact ? | inconnu | type connu | chemin+format exacts |
| 2 Perimetre | Quels fichiers/composants touches ? backend/front/moteur ? | flou | zone connue | liste fichiers + bornes |
| 3 Done | Critere de fin (compile/test/health/screenshot/help) ? | absent | partiel | mesurable + verifiable |
| 4 Contraintes | Naming, MUI v7, R-rules, build whitelist, perf ? | aucune citee | generiques | specifiques LIA-SEC |
| 5 Consommateur | Pour qui (dev/RSSI/auditeur/equipe) ? | inconnu | suppose | confirme |

Score = somme /100.

## Decision

```
score >= 70  -> GO    : lancer le cycle, injecter les reponses dans le PLAN
score <  70  -> CLARIFY : poser via AskUserQuestion UNIQUEMENT les axes < 15,
                          recalculer, re-decider. Max 2 tours de questions.
```

Apres 2 tours sans atteindre 70 : livrer 80% sur l'interpretation la plus
probable (BLOC 2 "reduire le scope") + lister explicitement les hypotheses
prises, plutot que bloquer indefiniment.

## Workflow

1. Lire la requete utilisateur.
2. Scorer les 5 axes (afficher le tableau avec le score par axe + total).
3. Si GO : annoncer "Clarte {N}/100 >= 70 -> GO" et enchainer le cycle demande.
4. Si CLARIFY : 1 seule question AskUserQuestion regroupant les axes faibles
   (1 sous-question par axe < 15, max 4). Recalculer. Re-decider.
5. Tracer la decision dans `_alire/02_LOGS/Journals/decision_log.jsonl`
   (action `CLARITY_GATE`, le score, GO/CLARIFY).

## Sortie type

```
## Gate clarte -- {requete}
| Axe | Score |
|-----|-------|
| Livrable | 20 |
| Perimetre | 10 |
| Done | 5 |
| Contraintes | 15 |
| Consommateur | 20 |
Total : 70/100 -> GO

Reponses injectees dans PLAN_*.md : ...
```

## Ce que ce skill NE fait PAS

- Pas de CLI externe (codex/gemini), pas de dependance OMC plugin.
- Pas de remplacement d'apex/audit-pdca -- c'est un GATE en amont, pas un cycle.
- Pas de questionnaire long facon `/interview` -- max 2 tours, axes manquants seulement.

## Reference

- BLOC 0 + BLOC 1 CLAUDE.md (seuil 95%, exigences avant tache)
- RETEX origine : `_alire/02_LOGS/Journals/retex/RETEX_OMC_INTEGRATION_2026-06-04.md`
- Complement : `/replan` (quand un plan derive en cours), `/prompt-builder` (genere les prompts agents)
