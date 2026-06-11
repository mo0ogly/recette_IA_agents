# Agentic Requirements - 5 Structural Criteria

Reference for the "Inject Agentic Structure" checklist in Step 4 of skill-creator.
Each criterion maps to a mandatory section that must appear in every LIA-SEC skill SKILL.md.

## Table of Contents

1. C1 - Decomposition d'objectif
2. C2 - Planification
3. C3 - Replanification (adaptation)
4. C4 - Utilisation dynamique d'outils
5. C5 - Memoire et tracabilite
6. Scoring agentique
7. Anti-patterns a eviter

---

## C1 - Decomposition d'objectif

**Principe:** Si le skill repond directement sans identifier de sous-taches independantes, il n'y a pas de comportement agentique. Un agent doit decomposer l'objectif general avant d'agir.

**Exigence:** La skill DOIT contenir une section qui enumere les sous-taches identifiees au demarrage, avant toute action.

**Mauvais exemple (passif) :**
```markdown
## Workflow
1. Lire le fichier
2. Appliquer les corrections
3. Sauvegarder
```

**Bon exemple (agentique) :**
```markdown
## Decomposition des sous-taches

Au demarrage, identifier les sous-taches independantes avant toute action :
- Sous-tache A : analyser la structure du projet (Read, Glob)
- Sous-tache B : identifier les violations (Grep)
- Sous-tache C : appliquer les corrections par fichier (Edit)
- Sous-tache D : verifier le build (Bash)
- Sous-tache E : produire le rapport (Write)

Sous-taches B et C peuvent paralleliser sur des fichiers differents.
Sous-tache D depend de C. Sous-tache E depend de D.
```

**Indicateur de conformite:** La section existe, liste >= 3 sous-taches, identifie les dependances.

---

## C2 - Planification

**Principe:** Un agent sans plan ne peut pas mesurer sa progression, detecter les derives, ni reprendre apres une interruption. Le plan persistant est le mecanisme de continuite inter-session.

**Exigence:** La skill DOIT imposer la creation d'un fichier `PLAN_*.md` avant toute action, et sa mise a jour a chaque etape.

**Format du fichier plan :**
```
_alire/tracking/PLAN_{SKILL_NAME}_{YYYY-MM-DD}.md
```

**Section minimale dans le SKILL.md :**
```markdown
## Plan d'execution

Avant toute action, creer le plan persistant :
```bash
cat > _alire/tracking/PLAN_{SKILL}_{YYYY-MM-DD}.md << 'EOF'
# Plan : {TITRE}
Date : {YYYY-MM-DD}
Status : EN_COURS

## Objectif
{1-2 phrases}

## Etapes
- [ ] Etape 1 : {description}
- [ ] Etape 2 : {description}
- [ ] Etape 3 : {description}

## Decisions prises
## Ecarts et replanification
## Resultat
EOF
```

Cocher chaque etape a la completion `[x]`.
Si replanification : changer Status en REPLANIFIE, creer PLAN_*_REPLAN_*.md avec lien.
A la cloture : Status -> TERMINE + Resultat.
```

**Indicateur de conformite:** La section existe, inclut le chemin `_alire/tracking/PLAN_*.md`, impose la mise a jour etape par etape.

### Format PLAN step (optionnel mais recommande pour les etapes complexes)

Pour les etapes COMPLEX ou MODERATE, documenter dans le PLAN_*.md :

```markdown
### Plan - Etape {N}: {nom}

Goal: {objectif specifique de cette etape}
Tools: {outil_1} (raison), {outil_2} (raison)
Expected output: {description du livrable attendu}
Success criteria: {check mesurable - ex: "build retourne exit 0"}
Failure signal: {ce qui declenche une replanification}
```

### Working Memory (tracking intra-session)

Apres chaque transition de phase, mettre a jour le PLAN_*.md :

```markdown
### Working Memory

Completed: [1, 2, 3]
Current: Etape 4
Pending: [5, 6]
Key findings: {resultats importants jusqu'ici}
Blockers: {si applicable}
```

---

## C3 - Replanification (adaptation)

**Principe:** Un workflow rigide qui continue en cas d'echec est un anti-pattern. L'agent doit detecter les echecs consecutifs et declencher une replanification formelle via `/replan`, pas improviser.

**Exigence:** La skill DOIT specifier le seuil de declenchement (2 echecs consecutifs) et interdire l'improvisation.

**Section minimale dans le SKILL.md :**
```markdown
## Adaptation et replanification

Regles d'adaptation :
- Si 1 etape echoue : retry une fois, puis log et continuer si non-bloquant
- Si 2 etapes consecutives echouent : STOP -> invoquer /replan
- Si une etape modifie > 10 fichiers sans verification intermediaire : STOP -> re-verification
- JAMAIS improviser un contournement sans /replan

Procedure /replan :
1. OBSERVE : etat actuel vs plan initial (quelles etapes completees, lesquelles ont echoue)
2. COMPARE : ecart entre prevu et reel
3. DECIDE : ajustement du plan (scope reduit, approche alternative, abandon partiel)
4. AJUSTE : creer PLAN_*_REPLAN_*.md avec lien vers plan original

Logger la replanification dans decision_log.jsonl avec action="REPLAN_TRIGGERED".
```

### Format REPLAN structuré

Dans le PLAN_*_REPLAN_*.md, documenter systematiquement :

```markdown
### Replan - Etape {N}

Failure cause: {diagnostic - mauvais outil / mauvaise hypothese / donnee manquante / erreur externe}
Alternatives considerees:
  A. {approche A} — rejetee parce que {raison}
  B. {approche B} — selectionnee parce que {raison}
  C. {approche C} — fallback si B echoue
New plan: {etapes mises a jour}
```

**Regle critique:** Ne jamais retenter exactement la meme action qui a echoue. Changer au minimum un parametre (outil, approche, source de donnee).

**Escalade utilisateur:** Si 3 tentatives de replanification sur la meme etape echouent -> STOP, escalader a l'utilisateur avec le diagnostic complet. Ne pas continuer en improvisant.

**Indicateur de conformite:** La section existe, cite le seuil de 2 echecs, interdit l'improvisation, reference /replan, inclut le format REPLAN et la regle d'escalade apres 3 tentatives.

---

## C4 - Utilisation dynamique d'outils

**Principe:** Une liste d'outils executee lineairement n'est pas de l'outillage dynamique. L'agent doit choisir l'outil selon le contexte (fichier existant ou non, taille, type, etat du build, etc.).

**Exigence:** La skill DOIT declarer ses outils et specifier les criteres de selection dynamique.

**Section minimale dans le SKILL.md :**
```markdown
## Outils declares

Outils disponibles pour cette skill :
- Read : lire un fichier connu (chemin exact disponible)
- Glob : trouver des fichiers par pattern (chemin inconnu ou multiple)
- Grep : rechercher du contenu dans des fichiers
- Edit : modifier un fichier existant (preferer sur Write pour les modifications)
- Write : creer un nouveau fichier ou reecriture complete
- Bash : executer des commandes (build, tests, scripts)

Criteres de selection dynamique :
- Fichier existe + modification partielle -> Edit (pas Write)
- Chemin inconnu -> Glob d'abord, puis Read
- Recherche de pattern dans N fichiers -> Grep (pas N appels Read)
- Build/test -> Bash avec timeout explicite

Retry policy :
- Outil echoue -> 1 retry avec parametres ajustes
- 2eme echec -> logger dans decision_log.jsonl + stop + signaler a l'utilisateur
- JAMAIS ignorer silencieusement un echec d'outil
```

**Indicateur de conformite:** La section existe, liste >= 4 outils avec criteres de choix, inclut une retry policy.

---

## C5 - Memoire et tracabilite

**Principe:** Sans journal auditable, les decisions disparaissent entre sessions. Sans RETEX, les patterns d'echec se repetent. La tracabilite est le mecanisme de capitalisation agentique.

**Exigence:** La skill DOIT imposer l'alimentation de decision_log.jsonl pour les decisions non-triviales ET la production d'un RETEX en fin de session si le score agentique est < 40/50.

**Section minimale dans le SKILL.md :**
```markdown
## Tracabilite agentique

### Decision log
Logger dans `_alire/02_LOGS/Journals/decision_log.jsonl` pour toute decision non-triviale :
- Choix d'architecture ou de strategie (quel outil, quelle approche)
- Alternatives rejetees et pourquoi
- Corrections appliquees apres echec
- Replanifications declenchees

Format (1 ligne JSON par decision) :
```bash
echo '{"timestamp":"'$(date -u +%Y-%m-%dT%H:%M:%SZ)'","session":"{SKILL}","action":"ACTION","reasoning":"...","alternatives_rejected":["..."],"outcome":"...","confidence":"high|medium|low","plan_ref":"PLAN_*.md ou null"}' >> _alire/02_LOGS/Journals/decision_log.jsonl
```

Ce qu'on NE trace PAS : actions mecaniques (build, test), formatage, renommage simple.

### RETEX
En fin de session, si score agentique < 40/50 :
- Identifier les criteres en echec
- Documenter les actions correctives pour le prochain cycle
- Sauvegarder dans `_alire/02_LOGS/RETEX_{SKILL}_{YYYY-MM-DD}.md`
```

**Indicateur de conformite:** La section existe, inclut le chemin decision_log.jsonl, le format JSON, et la condition de declenchement du RETEX.

---

## Scoring agentique

A inclure dans chaque skill pour l'auto-evaluation en fin de workflow :

```markdown
## Scoring agentique (auto-evaluation en fin de workflow)

| Critere | Description | Score |
|---------|-------------|-------|
| C1 Decomposition | Sous-taches identifiees et independantes au demarrage | /10 |
| C2 Planification | PLAN_*.md cree, suivi etape par etape, cloture | /10 |
| C3 Replanification | /replan declenche sur 2+ echecs consecutifs | /10 |
| C4 Outillage | Outils choisis dynamiquement selon contexte | /10 |
| C5 Tracabilite | decision_log.jsonl alimente + RETEX si score < 40 | /10 |

Score total : /50
- >= 40 : Exemplaire
- 30-39 : Acceptable
- < 30 : RETEX obligatoire avec actions correctives
```

---

## Anti-patterns a eviter

Ces patterns indiquent une skill non-agentique :

| Anti-pattern | Symptome | Correction |
|---|---|---|
| Workflow lineaire sans adaptation | "Step 1... Step 2... Step 3..." sans condition d'echec | Ajouter C3 (declencheur /replan) |
| Outil unique pour tous les cas | Toujours `Bash` ou toujours `Read` | Declarer C4 avec criteres de selection |
| Pas de plan persistant | Progres perdu si session interrompue | Ajouter C2 (PLAN_*.md) |
| Decision implicite | L'agent choisit sans tracer pourquoi | Ajouter C5 (decision_log.jsonl) |
| Objectif = action directe | "Fais X" -> "X fait" sans decomposition | Ajouter C1 (sous-taches) |
| "Done" sans verification | Pas de gate avant declaration de succes | Ajouter VERIFICATION GATE (Rule 4) |

---

## Exemple de skill avec les 5 criteres (squelette)

```markdown
## Decomposition des sous-taches
- A : analyser l'etat initial (Read, Glob, Grep)
- B : identifier les cibles (Grep)
- C : appliquer les modifications (Edit)
- D : verifier le resultat (Bash)
- E : produire le rapport (Write)
Dependances : D depend de C, E depend de D.

## Plan d'execution
Creer `_alire/tracking/PLAN_{SKILL}_{YYYY-MM-DD}.md` avant toute action.
Template : `_alire/tracking/PLAN_TEMPLATE.md`.

## Adaptation et replanification
2 echecs consecutifs -> STOP -> /replan -> PLAN_*_REPLAN_*.md.
JAMAIS improviser sans /replan.

## Outils declares
- Read/Glob/Grep : exploration | Edit : modification | Bash : execution
- Selection dynamique selon type de fichier et contexte
- Retry : 1 fois puis log + stop

## Tracabilite agentique
decision_log.jsonl : decisions non-triviales uniquement.
RETEX si score < 40/50.

## VERIFICATION GATE (BLOQUANT)
- [ ] Build passe
- [ ] Tests passent
- [ ] Pas de regression

## Scoring agentique
| Critere | Score |
| C1 Decomposition | /10 |
| C2 Planification | /10 |
| C3 Replanification | /10 |
| C4 Outillage | /10 |
| C5 Tracabilite | /10 |
```
