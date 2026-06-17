---
name: retex-analyzer
description: Genere automatiquement le RETEX d'un cycle PDCA et les ameliorations pour le cycle suivant. Analyse les scores, les prompts agents, les regressions, et met a jour SCORING_CONFIG + DASHBOARD. Se declenche sur "/retex-analyzer", "retex", "retrospective", "ameliorations cycle", ou quand audit-pdca appelle A.3.
---

# RETEX-ANALYZER -- Retrospective automatisee + ameliorations cycle suivant

Analyse les resultats d'un cycle PDCA, identifie ce qui a marche/rate,
propose des ameliorations pour les prompts/scoring/pipeline, et met a jour
SCORING_CONFIG.json et DASHBOARD.md.

Inspire de DSPy MIPROv2 (bootstrap -> proposal -> search) pour l'amelioration
automatique des prompts entre cycles.

## TRACABILITE AGENTIQUE (OBLIGATOIRE)

### Plan persistant
Creer `docs/tracking/PLAN_RETEX_{CYCLE}_{YYYY-MM-DD}.md` (template: `docs/tracking/PLAN_TEMPLATE.md`).

### Decision log
Logger dans `docs/tracking/decision_log.jsonl` les decisions non-triviales.
Format: `{"timestamp","session","action","reasoning","alternatives_rejected":[],"outcome","confidence","plan_ref"}`

### Replanification
Si 2 etapes echouent consecutivement → INVOQUER `/replan`.

### Scoring agentique (/50)
En fin de workflow, scorer sur : Decomposition, Planification, Replanification, Outillage dynamique, Tracabilite.

---

## Syntaxe

```
/retex-analyzer --cycle-dir=<dir> --config=<scoring_config> --dashboard=<file> [--prev-cycle=<dir>] [--auto-apply]
```

| Argument | Description | Defaut |
|----------|-------------|--------|
| `--cycle-dir` | Repertoire du cycle courant | obligatoire |
| `--config` | SCORING_CONFIG.json | obligatoire |
| `--dashboard` | DASHBOARD.md | obligatoire |
| `--prev-cycle` | Repertoire du cycle precedent | optionnel (cycle 1 = sans) |
| `--auto-apply` | Appliquer les ameliorations automatiquement | false (preview) |

---

## WORKFLOW -- 5 etapes (pattern DSPy)

### Etape 1 : BOOTSTRAP -- Collecte des traces du cycle

```
CHARGER depuis {cycle-dir}/ :
  P_PLAN.md         -> objectifs, prompts generes, score cible
  D_BRAINSTORM/*.md  -> rapports agents (les "traces" DSPy)
  C_SECURITY.md      -> findings securite
  C_TESTS.md         -> couverture tests
  C_SCORECARD.json   -> scores finaux

SI --prev-cycle fourni :
  CHARGER depuis {prev-cycle}/ :
    C_SCORECARD.json  -> scores precedents
    A_IMPROVEMENTS.md -> ameliorations proposees au cycle precedent
    A_RETEX.md        -> retex precedent

CALCULER metriques :
  - objectif_atteint = score_global >= score_cible (oui/non)
  - delta_score = score_global - score_precedent (si cycle > 1)
  - domaines_en_progres = [domaines ou delta > 5]
  - domaines_stagnants = [domaines ou -5 <= delta <= 5]
  - domaines_en_regression = [domaines ou delta < -5]
  - ameliorations_appliquees = [lesquelles du cycle N-1 ont ete implementees]
  - ameliorations_ignorees = [lesquelles du cycle N-1 n'ont PAS ete implementees]
```

### Etape 2 : GROUNDED PROPOSAL -- Analyse des prompts agents

C'est la phase cle du self-improvement. Chaque prompt agent est evalue
sur la qualite de son rapport.

```
Pour chaque domaine :
  LIRE le prompt utilise (dans P_PLAN.md section "Prompts par domaine")
  LIRE le rapport agent produit (D_BRAINSTORM/{domaine}.md)

  EVALUER :
    - pertinence : le rapport repond-il a la question ? (0-5)
    - precision : chiffres exacts, fichiers cites, lignes ? (0-5)
    - exhaustivite : tous les aspects couverts ? (0-5)
    - actionabilite : les gaps sont-ils concrets et corrigeables ? (0-5)
    - bruit : y a-t-il des faux positifs ou du hors-sujet ? (0-5 inverse)

  score_prompt_efficacite = moyenne(pertinence, precision, exhaustivite, actionabilite, 5-bruit)

  SI score_prompt_efficacite < 3 :
    IDENTIFIER la faiblesse du prompt :
      - Trop vague ? -> "Preciser le scope a {repertoires}"
      - Mauvais repertoire ? -> "Corriger le scope de X a Y"
      - Manque comptages ? -> "Ajouter instruction : compter les occurrences"
      - Trop de bruit ? -> "Ajouter instruction : pas de generalites"
      - Pas de score ? -> "Renforcer le format obligatoire ## Score"
    AJOUTER a prompt_improvements[]
```

### Etape 3 : ANALYSE SCORING_CONFIG

```
Pour chaque domaine dans SCORING_CONFIG :
  EVALUER chaque check :
    - Check atteint target depuis 2+ cycles ? -> CANDIDAT SUPPRESSION (check resolu)
    - Check jamais evalue ? -> CANDIDAT SUPPRESSION (check mort)
    - Check avec score = 0 depuis 2+ cycles ? -> VERIFIER si check pertinent
    - Check produit faux positifs ? -> CANDIDAT AJUSTEMENT target

  EVALUER poids du domaine :
    - Domaine toujours a 100% ? -> BAISSER poids (pas discriminant)
    - Domaine toujours a 0% ? -> VERIFIER si poids realiste
    - Domaine avec plus grand delta ? -> AJUSTER poids si sous-evalue

  DETECTER domaines manquants :
    - Gaps identifies dans D_BRAINSTORM qui ne correspondent a aucun domaine
    - Exemple : "i18n" mentionne dans les gaps mais pas de domaine i18n

GENERER scoring_improvements[] :
  - AJOUTER checks : {id, name, type, pattern, target, justification}
  - RETIRER checks : {id, raison}
  - AJUSTER poids : {domaine, ancien, nouveau, justification}
  - NOUVEAU domaine : {nom, poids, checks_initiaux}
```

### Etape 4 : ANALYSE PIPELINE

```
EVALUER l'efficacite de chaque skill utilisee dans le cycle :

  Pour chaque skill chainee :
    - A-t-elle produit un output exploitable ? (oui/non)
    - L'output a-t-il ete utilise dans la phase suivante ? (oui/non)
    - A-t-elle consomme beaucoup de temps/tokens pour peu de valeur ? (oui/non)

  IDENTIFIER :
    - Skills utiles a conserver
    - Skills inutiles dans ce contexte (a retirer du pipeline)
    - Skills manquantes (gap dans le pipeline identifie)
    - Ordre des phases a modifier (si une phase aurait du preceder une autre)
```

### Etape 5 : GENERATION OUTPUTS

**A_RETEX.md :**

```markdown
# RETEX Cycle {N} -- {perimetre}

**Date :** {date}
**Score :** {score_global}/100 (objectif : {score_cible})
**Verdict :** {ATTEINT | PARTIELLEMENT | RATE}

## Objectifs du cycle
- Score vise : {score_cible} -> Atteint : {score_global} ({delta})
- Domaines en progres : {liste avec delta}
- Domaines stagnants : {liste}
- Regressions : {liste avec analyse cause}

## Efficacite des prompts agents
| Domaine | Score efficacite | Pertinence | Precision | Exhaustivite | Bruit |
|---------|-----------------|------------|-----------|--------------|-------|
(1 ligne par domaine)

Prompts a ameliorer :
- {domaine} : {faiblesse identifiee} -> {amelioration proposee}

## Efficacite du pipeline
| Skill | Output | Utilise | Valeur |
|-------|--------|---------|--------|
(1 ligne par skill)

## Ameliorations du cycle precedent
| Amelioration | Appliquee | Impact |
|-------------|-----------|--------|
(si cycle > 1)

## Surprises
- {fonctionnalites deja faites non detectees}
- {bugs non prevus}
- {dependances cachees}

## Metriques DORA du processus
| Metrique | Valeur |
|----------|--------|
| Frequence cycles | {N cycles en X semaines} |
| Lead time detection -> fix | {jours moyen} |
| Rework rate | {% de checks qui regressent} |
| Change failure rate | {% remediations causant regression} |
```

**A_IMPROVEMENTS.md :**

```markdown
# Ameliorations pour Cycle {N+1}

## 1. Ameliorations SCORING_CONFIG
### Checks a ajouter
| ID | Nom | Type | Pattern | Target | Justification |
(lignes)

### Checks a retirer
| ID | Raison |
(lignes)

### Poids a ajuster
| Domaine | Ancien | Nouveau | Justification |
(lignes)

### Nouveaux domaines
| Domaine | Poids | Checks initiaux |
(lignes)

## 2. Ameliorations prompts agents
| Domaine | Faiblesse | Amelioration |
(lignes)

Pour chaque prompt a ameliorer :
  RECOMMANDER d'utiliser /prompt-builder AUDIT sur le prompt existant
  au debut du cycle N+1 (phase P.3)

## 3. Ameliorations pipeline
- Skills a ajouter : {liste}
- Skills a retirer : {liste}
- Ordre a modifier : {detail}

## 4. Quick wins pour cycle N+1
| Quick win | Effort | Impact score | Domaine |
(lignes triees par ratio impact/effort)

## 5. Objectifs cycle N+1
- Score cible : {score_current + delta_realiste}
- Focus areas : {domaines avec plus grand potentiel}
- Risques : {regressions possibles}
- Quality gates a activer : {domaines prets pour --gate}
```

**Mise a jour SCORING_CONFIG.json :**

```
SI --auto-apply :
  APPLIQUER les modifications scoring_improvements[] :
    - Ajouter nouveaux checks
    - Retirer checks obsoletes
    - Ajuster poids
    - Ajouter nouveaux domaines
  INCREMENTER version

SINON :
  AFFICHER les modifications proposees
  DEMANDER confirmation avant application
```

**Mise a jour DASHBOARD.md :**

```
AJOUTER ligne dans le tableau de progression :
  | {N} | {date} | {score}/100 | {delta} | {objectif} | {tendance} |

AJOUTER lignes dans tendances par domaine :
  | Domaine | ... | C{N} |

SI regressions :
  AJOUTER dans section "Regressions detectees"

AJOUTER dans section "Ameliorations du processus" :
  - C{N-1} -> C{N} : {resume des ameliorations appliquees}

AJOUTER metriques DORA
```

---

## EXEMPLES

```bash
# RETEX cycle 1 (baseline, pas de precedent)
/retex-analyzer --cycle-dir=docs/tracking/pdca/gateway/cycle_001/ --config=docs/tracking/pdca/gateway/SCORING_CONFIG.json --dashboard=docs/tracking/pdca/gateway/DASHBOARD.md

# RETEX cycle 2 (avec comparaison cycle 1, auto-apply)
/retex-analyzer --cycle-dir=docs/tracking/pdca/gateway/cycle_002/ --config=docs/tracking/pdca/gateway/SCORING_CONFIG.json --dashboard=docs/tracking/pdca/gateway/DASHBOARD.md --prev-cycle=docs/tracking/pdca/gateway/cycle_001/ --auto-apply

# RETEX sur module Discovery
/retex-analyzer --cycle-dir=docs/tracking/pdca/discovery/cycle_001/ --config=docs/tracking/pdca/discovery/SCORING_CONFIG.json --dashboard=docs/tracking/pdca/discovery/DASHBOARD.md
```

---

## BOUCLE D'APPRENTISSAGE (vue complete)

```
Cycle 1:
  P.3 : prompt-builder genere prompt v1
  D.2 : agent produit rapport R1
  C.3 : scorecard S1
  A.3 : retex-analyzer ->
         - Evalue prompt v1 efficacite = 3.2/5
         - Identifie : "prompt security trop vague, pas de scope"
         - Propose : "Ajouter scope src/ (gateway Axum) + console/src/services/"
         - Ecrit A_IMPROVEMENTS.md

Cycle 2:
  P.1 : CHARGE A_IMPROVEMENTS.md du cycle 1
  P.3 : prompt-builder AUDIT prompt v1 -> regenere prompt v2 (avec scope precis)
  D.2 : agent produit rapport R2 (plus precis grace au prompt v2)
  C.3 : scorecard S2 (delta mesurable)
  A.3 : retex-analyzer ->
         - Evalue prompt v2 efficacite = 4.1/5 (+0.9)
         - Identifie : "domaine i18n manque dans SCORING_CONFIG"
         - Ajoute domaine i18n (poids 5%)
         - Ecrit A_IMPROVEMENTS.md

Cycle 3:
  P.1 : CHARGE A_IMPROVEMENTS (nouveau domaine i18n)
  P.3 : prompt-builder genere prompt i18n + re-AUDIT prompt v2 -> v3
  ...
```

Chaque cycle ameliore 3 choses :
1. **Les prompts** (plus precis, moins de bruit)
2. **Le scoring** (nouveaux domaines, checks ajustes)
3. **Le pipeline** (skills ajoutees/retirees, ordre optimise)

---

## REGLES

1. **RETEX obligatoire.** Meme si score = 100, le processus peut s'ameliorer.
2. **Prompt efficacite < 3/5 = prompt a rewriter.** Feedback dans A_IMPROVEMENTS.
3. **Check resolu 2+ cycles = candidat suppression.** Evite l'accumulation de checks morts.
4. **Regression = alerte rouge.** Pas juste une ligne dans le rapport -- stop et analyse.
5. **Auto-apply avec prudence.** Seulement si les modifications sont clairement benefiques.
6. **DORA metrics sur le processus.** Meta-amelioration : le PDCA s'optimise lui-meme.
7. **Pas d'amelioration inventee.** Chaque proposition est justifiee par une trace du cycle.

---

## ENCHAINEMENT AUTOMATIQUE (OBLIGATOIRE)

A la fin du RETEX, TOUJOURS annoncer et executer la prochaine etape sans demander :

```
SI score_global < 85 sur le meme module :
  ANNONCER : "Prochaine etape : /audit-pdca {module} --cycle={N+1} (score {score} < 85)"
  EXECUTER : /audit-pdca {module} --cycle={N+1}

SI score_global >= 85 ET score_global < 95 :
  ANNONCER : "Module {module} stabilise a {score}/100. Prochaine etape : identifier le module avec le score le plus bas."
  LISTER les autres modules pdca/ avec leurs scores
  EXECUTER : /audit-pdca {module_plus_bas} --cycle=1 (ou N+1 si existant)

SI score_global >= 95 :
  ANNONCER : "Module {module} excellent a {score}/100. Maintenance uniquement."
  PROPOSER : veille regressions ou nouveau module

JAMAIS :
  - Proposer un menu de choix ("voulez-vous A, B, ou C ?")
  - Demander "quelle est la suite ?"
  - Attendre une instruction pour enchainer
```
