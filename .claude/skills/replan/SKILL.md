---
name: replan
description: Replanification formelle quand un plan derive. Observe l'etat actuel, compare au plan initial, identifie les ecarts, et produit un plan ajuste. Se declenche sur "/replan", "le plan a change", "ca ne marche pas comme prevu", "on replanifie", "ecart", "deviation". Aussi declenchable automatiquement quand 2+ etapes echouent consecutivement.
---

# Replan -- Boucle de replanification agentique

Quand un plan derive ou qu'un blocage survient, cette skill formalise
la boucle OBSERVE -> COMPARE -> DECIDE -> AJUSTE au lieu de replanifier implicitement.

## REGLE ABSOLUE

**Chaque replanification produit un LIVRABLE ECRIT** (nouveau PLAN_*.md).
Pas de replanification silencieuse. Le raisonnement est trace.

---

## Phase 1 : OBSERVE (etat actuel)

### Ce que tu fais
1. Lire le plan en cours (`_alire/tracking/PLAN_*.md` le plus recent pour ce sujet)
2. Verifier l'etat reel :
   - `git status` + `git diff --stat` (modifications en cours)
   - Build status (`build_secure_lia.sh` ou `npm run build`)
   - Tests en echec (si applicable)
   - Erreurs ou blocages rencontres
3. Lister les etapes completees vs non completees

### Ce que tu livres
```
=== OBSERVATION ===
PLAN INITIAL  : {lien vers PLAN_*.md}
ETAPES FAITES : {N}/{total}
  [x] Etape 1 : OK
  [x] Etape 2 : OK
  [ ] Etape 3 : BLOQUEE - {raison}
  [ ] Etape 4 : NON COMMENCEE
ETAT BUILD    : {OK | ECHEC (erreur)}
ETAT TESTS    : {N pass / N fail}
BLOCAGES      : {liste}
```

### Attendre validation utilisateur avant de continuer.

---

## Phase 2 : COMPARE (ecarts)

### Ce que tu fais
1. Pour chaque etape non completee, identifier la cause :
   - **Blocage technique** : API indisponible, erreur compilation, dependance manquante
   - **Hypothese invalide** : le format/API/version n'est pas celui prevu
   - **Scope creep** : la tache est plus complexe que prevu
   - **Prerequis manquant** : une etape aurait du etre faite avant
2. Classer les ecarts par severite :
   - **CRITIQUE** : empeche de continuer (bloquant)
   - **MAJEUR** : necessite changement d'approche
   - **MINEUR** : contournable sans changer le plan

### Ce que tu livres
```
=== ANALYSE DES ECARTS ===
| # | Etape | Ecart | Severite | Cause racine |
|---|-------|-------|----------|-------------|
| 3 | ... | BLOQUEE | CRITIQUE | ... |
| 4 | ... | RETARDEE | MINEUR | ... |

VERDICT : {CONTINUER | AJUSTER | PIVOTER | ABANDONNER}
```

### Attendre validation utilisateur avant de continuer.

---

## Phase 3 : DECIDE (alternatives)

### Ce que tu fais
1. Pour chaque ecart CRITIQUE ou MAJEUR, proposer 2-3 alternatives :
   - **Plan B** : approche differente pour le meme objectif
   - **Plan C** : scope reduit (livrer 80%)
   - **Plan D** : contournement temporaire + dette technique tracee
2. Evaluer chaque alternative : effort, risque, resultat attendu
3. Recommander une option (avec justification)

### Ce que tu livres
```
=== ALTERNATIVES ===
ECART #3 : {description}
  A) {alternative A} -- effort: 30min, risque: faible, resultat: 100%
  B) {alternative B} -- effort: 10min, risque: moyen, resultat: 80%
  C) {alternative C} -- effort: 5min, risque: eleve, resultat: 60%
  RECOMMANDATION : {A|B|C} car {justification}

ECART #4 : ...
```

### Attendre validation utilisateur avant de continuer.

---

## Phase 4 : AJUSTE (nouveau plan)

### Ce que tu fais
1. Creer un nouveau fichier plan : `_alire/tracking/PLAN_{TASK}_REPLAN_{YYYY-MM-DD}.md`
2. Lier au plan precedent (champ "Replanifie depuis")
3. Marquer l'ancien plan comme REPLANIFIE
4. Ecrire une entree dans `decision_log.jsonl` avec :
   - action: "REPLAN"
   - reasoning: cause racine des ecarts
   - alternatives_rejected: les options non retenues
   - plan_ref: le nouveau plan
5. Presenter le nouveau plan a l'utilisateur

### Ce que tu livres
- Nouveau `PLAN_*_REPLAN_*.md` ecrit dans `_alire/tracking/`
- Ancien plan mis a jour (Status: REPLANIFIE)
- Entree decision_log.jsonl
- Resume pour l'utilisateur :

```
=== REPLANIFICATION ===
ANCIEN PLAN : {lien}
NOUVEAU PLAN : {lien}
CHANGEMENTS :
  - Etape 3 : {ancienne approche} -> {nouvelle approche}
  - Etape 5 ajoutee : {nouvelle etape}
ESTIMATION : {effort restant}
```

### Attendre validation utilisateur avant d'executer.

---

## Declenchement automatique

Cette skill DEVRAIT etre invoquee automatiquement quand :
- 2+ etapes d'un plan echouent consecutivement
- Un build echoue 3+ fois sur la meme erreur
- L'utilisateur dit "ca ne marche pas", "on change d'approche", "c'est bloque"
- Le scope reel depasse 2x le scope initial estime

## Integration avec les autres skills

- `/apex` : replan s'integre a l'etape eXamine (Phase 4 d'APEX)
- `/audit-pdca` : replan correspond au "Check" du cycle PDCA
- `/brainstorm-agents` : peut lancer N agents pour explorer les alternatives en Phase 3

## Fichiers associes

| Fichier | Role |
|---------|------|
| `_alire/tracking/PLAN_*.md` | Plans persistants |
| `_alire/02_LOGS/Journals/decision_log.jsonl` | Journal de decisions |
| `.claude/rules/agentic-traceability.md` | Regles de tracabilite |
