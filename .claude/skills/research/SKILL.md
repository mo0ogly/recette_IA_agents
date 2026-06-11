---
name: research
description: >
  Use when a technical topic requires sustained multi-session R&D research, or for
  any /research command (status, close, update, schema, gaps, mapping). Also use
  when resuming work on an ongoing research topic after context compression.
metadata:
  user_invocable: "true"
  argument_hint: "[topic] | status | close | update | schema | gaps | mapping"
compatibility: "Referentiel: _alire/research_discovery/. Outils: WebSearch, Glob, Read, Write, Grep, mcp__claude_ai_Mermaid_Chart."
---

# Research Skill v2.3 - Methodologie de Recherche Technique LIA-Scan

> **PREMIERE ACTION OBLIGATOIRE (avant tout) :** Annoncer "Using research skill. Reading state files..." comme premiere ligne de reponse.

Ce skill fonctionne comme un **cahier de laboratoire** persistant.
Chaque session repart de l'etat exact ou la precedente s'est arretee.

**Philosophie :** On etudie longuement avant de se jeter dans un developpement
qu'on devra refaire. On documente au fil de l'eau. On ne perd jamais une information.

---

## TRACABILITE AGENTIQUE (OBLIGATOIRE)

### Plan persistant
Creer `_alire/tracking/PLAN_RESEARCH_{TOPIC}_{YYYY-MM-DD}.md` (template: `_alire/tracking/PLAN_TEMPLATE.md`).

### Decision log
Logger dans `_alire/02_LOGS/Journals/decision_log.jsonl` les decisions non-triviales.
Format: `{"timestamp","session","action","reasoning","alternatives_rejected":[],"outcome","confidence","plan_ref"}`

### Replanification
Si 2 etapes echouent consecutivement → INVOQUER `/replan`.

### Scoring agentique (/50)
En fin de workflow, scorer sur : Decomposition, Planification, Replanification, Outillage dynamique, Tracabilite.

---

## THE IRON LAW

```
NO PHASE SKIP WITHOUT GATE PROOF
NO GATE WITHOUT DOCUMENTED DELIVERABLE
NO CLAIM WITHOUT FRESH EVIDENCE
```

**Violating the letter of this process is violating the spirit of this process.**

---

## RATIONALISATIONS INVALIDES (observees en tests — toutes rejetees)

Ces rationalisations ont ete documentees lors d'evaluations reelles. Elles sont toutes FAUSSES.

| Rationalisation observee | Pourquoi c'est faux |
|--------------------------|---------------------|
| "Je suis en train de lire SKILL.md, l'annonce est implicite." | L'annonce est EXPLICITE, dite en premiere ligne avant toute autre action. Lire le skill n'est pas l'annoncer. |
| "Je connais deja l'etat du projet depuis MEMORY.md / le contexte." | Le referentiel (`_alire/research_discovery/`) est la seule source de verite. MEMORY.md peut etre perime. Lire les fichiers est obligatoire. |
| "Le contexte est clair, je peux proposer une solution directement." | Aucune proposition de code ou d'architecture avant que les 9 etapes de relecture ne soient completees. Periode. |
| "Ce cas est simple, les gates ne s'appliquent pas." | Les gates s'appliquent TOUJOURS. La simplicite apparente est un symptome de mauvaise analyse, pas une exemption. |
| "J'ai deja mentionne le commit, [COMMIT] est redondant." | Le tag `[COMMIT]` est explicite dans le RESEARCH_LOG, pas inline dans un paragraphe. Format = `[COMMIT] abc123`. |

---

## REGLE ABSOLUE N.0 : RELECTURE OBLIGATOIRE APRES COMPRESSION DE CONTEXTE

Apres chaque compression de contexte, RELIRE CE SKILL EN ENTIER avant de continuer.

**Procedure obligatoire (9 etapes, TOUTES requises) :**
1. Lire ce SKILL.md en entier
2. Lire le INDEX.md du topic en cours (phase actuelle)
3. Lire le RESEARCH_LOG.md (dernieres entrees)
4. Lire le fichier tracking actif dans `_alire/tracking/` (le plus recent)
5. Lire la SYNTHESE du sujet (`investigated/YYYY-MM-DD_SYNTHESE-*.md`)
6. Lire le mapping existant (`investigated/YYYY-MM-DD_mapping-existant.md`)
7. Identifier la phase actuelle + gate bloquante
8. Lister TOUTES les decisions utilisateur (tags `[DECISION]` dans RESEARCH_LOG.md)
9. Annoncer : "Contexte compresse. Phase : {N}. Gate : {bloquant}. Decisions : {liste}."

**NE RIEN CODER tant que les 9 etapes ne sont pas completees.**

**Violation = brouillon invalide.** Tout travail produit sans relecture sera refait.

Pourquoi 9 etapes : sans lire le tracking et les decisions, le comportement derive vers :
- Implementer Option B apres avoir choisi A
- Oublier des decisions critiques (nomenclature, scanner autonome, vecteur L_FILE)
- Inventer des champs de struct au lieu de lire le modele existant

---

## REGLE ABSOLUE N.1 : INTERNET AVANT TOUTE AFFIRMATION

Si la question est factuelle (prix, features, version, disponibilite) → WebSearch FIRST.

INTERDIT de repondre de memoire sur : prix/quotas, existence de features, benchmarks, performances.

**Violation = erreur grave.** Corriger immediatement + faire la recherche + documenter l'erreur.

---

## REGLE ABSOLUE N.2 : MAPPER L'EXISTANT AVANT DE CONCEVOIR

Avant tout design, creer la matrice HAVE / ADAPT / NEED dans un fichier.

**OBLIGATOIRE :**
1. Lire les fichiers existants (Glob pour confirmer qu'ils existent encore)
2. Creer matrice HAVE / ADAPT / NEED
3. Documenter dans `{topic}/investigated/YYYY-MM-DD_mapping-existant.md`
4. Presenter a l'utilisateur AVANT de proposer une architecture

**INTERDIT** de citer un fichier par nom sans avoir verifie qu'il existe (les fichiers bougent a chaque refactoring).

---

## REGLE ABSOLUE N.3 : DOCUMENTER AU FIL DE L'EAU

Chaque decouverte → fichier immediatement. La doc finale est une COMPILATION, pas une reecriture.

Chaque fichier de recherche contient OBLIGATOIREMENT :
```
## Recherches Internet effectuees
- Query : "{termes exacts}" -> {resultats} ({URL})

## Preuves conservees
- {description} -> {chemin ou URL}
```

---

## REGLE ABSOLUE N.4 : JOURNAL TRACKING APRES CHAQUE ETAPE

Avant de passer a l'etape N+1 :
1. `_alire/tracking/NOM_DU_TRACKING.md` → entree journal
2. `RESEARCH_LOG.md` → entree avec tag
3. `{topic}/INDEX.md` → statuts et phase mis a jour

**INTERDICTION de commencer l'etape N+1 sans avoir fait les 3 fichiers.**

Tags RESEARCH_LOG :

| Tag | Quand |
|-----|-------|
| `[DECISION]` | Choix structurant pris par l'utilisateur |
| `[VALIDATED]` | Element confirme en production |
| `[COMMIT]` | Commit cle avec hash complet |
| `[INVESTIGATED]` | Exploration documentee sans resultat definitif |
| `[ABANDONED]` | Piste fermee avec raison |
| `[BACKLOG]` | Piste future ajoutee |

---

## REGLE ABSOLUE N.5 : PHASES OBLIGATOIRES AVEC GATES

```
PHASE 0 : ETUDE DE L'EXISTANT INTERNE
    | gate: matrice HAVE/ADAPT/NEED ecrite + presentee
    v
PHASE 1 : RECHERCHE EXTERNE (outils, libs, patterns)
    | gate: synthese avec >= 3 solutions + sources verifiables
    v
PHASE 2 : ANALYSE DES GAPS (ce que les users demandent)
    | gate: >= 5 gaps documentes avec sources
    v
PHASE 3 : CONCEPTION (architecture, format, decisions)
    | gate: conception validee par l'utilisateur
    v
PHASE 4 : PLAN DE DEV (etapes, fichiers, criteres)
    | gate: plan approuve par l'utilisateur
    v
PHASE 5 : IMPLEMENTATION (code, tests, validation)
    | gate: code compile + tests passent + lab valide
    | VERIFICATION-BEFORE-COMPLETION OBLIGATOIRE :
    |   1. Identifier la commande qui PROUVE l'assertion (ex: scan #N, exit code 0)
    |   2. L'executer MAINTENANT, pas referencier un run precedent
    |   3. Examiner l'output complet ET les exit codes
    |   4. Confirmer que l'output supporte l'assertion (pas "devrait marcher")
    |   5. Formuler la conclusion avec citation d'evidence (scan #N : N/N detectes)
    | Disqualifie : "devrait", "probablement", "semble", run precedent, check partiel
    v
PHASE 6 : DOCUMENTATION FINALE (compilation, referentiel)
    | gate: referentiel mis a jour, status VALIDATED avec preuve
```

Descriptions detaillees → `references/phases.md`

---

## Referentiel

```
BASE = /home/mo0ogly/Bureau/vscode_lia_audit/_alire/research_discovery/

{BASE}/
+-- RESEARCH_INDEX.md          # Index global de tous les sujets
+-- RESEARCH_LOG.md            # Journal chronologique (toutes sessions)
+-- {topic}/
    +-- INDEX.md               # Etat synthetique du sujet
    +-- validated/             # Confirme, avec preuve
    +-- investigated/          # Explore, resultats documentes
    +-- abandoned/             # Abandonne, AVEC le pourquoi
    +-- backlog/               # Futures pistes
```

---

## Etats possibles

| Etat | Signification | Preuve requise |
|------|---------------|----------------|
| VALIDATED | Fonctionne en production | commit ou test passe |
| INVESTIGATED | Explore, resultats partiels | fichier dans investigated/ |
| IN_PROGRESS | Session en cours | - |
| ABANDONED | Abandonne definitivement | raison documentee obligatoire |
| BACKLOG | Piste future | priorite + effort estimes |

---

## Workflow selon l'argument

### `/research` ou `/research status`

1. Lire `RESEARCH_INDEX.md`
2. Pour chaque sujet : lire `{topic}/INDEX.md`
3. Determiner la phase actuelle (0-6)
4. Generer schema Mermaid
5. Afficher prochaines actions prioritaires

Format reponse :
```
ETAT DE LA RECHERCHE - {date}
[TOPIC: {topic}]
  Phase actuelle : {N} - {nom}
  Gate bloquante : {ce qui manque}
  Validated: N | Investigated: N | Abandoned: N | Backlog: N
PROCHAINE ACTION : [1 action claire avec raison]
```

### `/research [topic]` - Focus sujet

1. Lire `{topic}/INDEX.md` + tous les sous-repertoires
2. Determiner la phase actuelle selon les gates
3. Generer schema Mermaid du sujet
4. Identifier la gate bloquante
5. Proposer la prochaine action

A la fin : MAJ fichiers → MAJ INDEX.md → MAJ RESEARCH_LOG.md → resume session

### `/research schema [topic]`

Flowchart Mermaid : pistes (couleurs etat), dependances, blocages, phase actuelle en surbrillance.

Couleurs :
- VALIDATED `fill:#2d8a4e,color:#fff`
- INVESTIGATED `fill:#b35900,color:#fff`
- ABANDONED `fill:#8b0000,color:#fff`
- BACKLOG `fill:#555,color:#fff`
- IN_PROGRESS `fill:#0066cc,color:#fff`
- CRITIQUE MANQUANT `fill:#cc0000,color:#fff,stroke:#ff0000,stroke-width:3px`

### `/research update [topic] [etat] [nom]`

1. Creer/MAJ `{topic}/{etat}/YYYY-MM-DD_{nom}.md` (templates → `references/templates.md`)
2. MAJ `{topic}/INDEX.md`
3. Entree dans `RESEARCH_LOG.md`

### `/research gaps [topic]`

WebSearch : "{outil} limitations", "{outil} missing features github issues", "{outil} vs {autre}"
Livrable : `{topic}/investigated/YYYY-MM-DD_{sujet}-gaps.md`

### `/research mapping [topic]`

Lire code Go existant → matrice HAVE / ADAPT / NEED
Livrable : `{topic}/investigated/YYYY-MM-DD_mapping-existant.md`

### `/research close [topic]`

Dans cet ordre :
1. Tracking → entree journal dans `_alire/tracking/`
2. RESEARCH_LOG.md → entree cloture avec tags (format ci-dessous)
3. `{topic}/validated/YYYY-MM-DD_{nom}.md` → creer ce fichier avec commit hash
4. INDEX.md → statuts + chiffres mis a jour
5. Annoncer : "Session close. Tracking, RESEARCH_LOG et INDEX mis a jour."

**INTERDIT de clore sans les 4 fichiers (tracking + RESEARCH_LOG + validated/ + INDEX).**

Format entree RESEARCH_LOG (obligatoire) :
```
[TOPIC] [VALIDATED] [COMMIT] {hash_complet} - {Nom du composant} en production (YYYY-MM-DD)
Contexte : {pourquoi c'est valide}
Preuves : {scan #N / test pass / screenshot / endpoint}
```

Exemple :
```
[DISCOVERY] [VALIDATED] [COMMIT] 3b82e8bfe5 - Banner-server COUCHE 5 30/30 detectes (2026-03-02)
Contexte : 30 banners TCP/HTTP sur ports 9001-9030 detects par LiaProbe en production.
Preuves : scan #145 (23/23) + scan #148 (7/7). Commit 3b82e8bfe5 en prod.
```

---

## Regles d'or

1. Internet avant toute affirmation factuelle.
2. Matrice HAVE/ADAPT/NEED avant toute conception.
3. Documenter au fil de l'eau (pas a la fin).
4. Garder les preuves : URLs, queries exactes, commits.
5. Phases avec gates : ne pas sauter. Chaque gate a un livrable.
6. Jamais supprimer VALIDATED ou ABANDONED : archiver seulement.
7. ABANDONED = raison obligatoire. Sans raison = invalide.
8. VALIDATED = preuve obligatoire. Commit, test, screenshot, endpoint.
9. Une seule source de verite : le referentiel.
10. Pas d'abandon premature : epuiser les alternatives.

---

## Question directrice

A chaque session : **"Si cette session s'arrete maintenant, est-ce que la prochaine peut reprendre sans perdre d'information ?"**

Si non → mettre a jour le referentiel avant de repondre.

---

## Sujets connus

| Topic | Repertoire | Etat |
|-------|-----------|------|
| discovery | `discovery/` | Voir `discovery/INDEX.md` |

Pour ajouter un sujet : creer `{nouveau_topic}/INDEX.md` + ligne dans `RESEARCH_INDEX.md`.

---

## References

| Fichier | Contenu |
|---------|---------|
| `references/phases.md` | Descriptions detaillees phases 0-6 |
| `references/templates.md` | Templates VALIDATED / INVESTIGATED / ABANDONED / BACKLOG |
| `references/principles.md` | Principes fondamentaux + anti-patterns |
