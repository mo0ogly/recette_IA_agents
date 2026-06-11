---
name: analyze-repo
description: Analyse un repo externe (GitHub, code source, lib) pour identifier ce qui est reutilisable et planifier la transposition vers Go/React LIA-SEC. Se declenche sur "analyse ce repo", "regarde ce code", "on peut reprendre ca", "transpose ca", "porte ca en Go", "adapte ce code". INTERDIT de coder avant validation de chaque phase par l'utilisateur.
---

# Analyze Repo v3.0 - Analyse et transposition de code externe

Analyse un repo/code externe pour identifier ce qui est reutilisable
et planifier la transposition vers la stack LIA-SEC (Go/React/PostgreSQL).

---

## Architecture Multi-Agent

| Etape | Role | Responsabilite |
|-------|------|---------------|
| Phase 1 Inventaire | COLLECTOR | Lire repo, lister structure, compter fichiers/LOC, identifier stack |
| Phase 2 Analyse fonctionnelle | ANALYST | Extraire fonctionnalites, E/S, logique metier, deps critiques |
| Phase 3 Delta LIA-SEC | ANALYST | Grep/Glob codebase LIA-SEC, classifier EXISTE/SIMILAIRE/ABSENT |
| Phase 4 Plan transposition | PLANNER | Mapping langage/libs, adaptations LIA-SEC, ordre implementation |
| Phase 5 Implementation | EXECUTOR | Coder une fonctionnalite a la fois, build gates, montrer diffs |
| Tracabilite | LIBRARIAN | Plan persistant, decision_log, preuves de recette, RETEX |

---

## Quality Hooks

| Hook | Declenchement | Action |
|------|--------------|--------|
| GATE_USER_VALIDATION | Fin de chaque phase (1-4) | STOP, presenter livrable, attendre validation explicite |
| BUILD_GATE | Apres chaque transposition (Phase 5) | `build_secure_lia.sh` (Go) + `vite build` (React) -- BLOQUANT |
| REGRESSION_GATE | Apres chaque transposition (Phase 5) | Tests existants ne cassent pas, imports valides |
| DELTA_FRESHNESS | Debut Phase 3 | Grep/Glob sur LIA-SEC actuel (pas de cache) |

---

## Niveaux d'autonomie

| Niveau | Quand | Comportement |
|--------|-------|-------------|
| SUPERVISED | Par defaut | Gate utilisateur apres chaque phase |
| SEMI-AUTO | Utilisateur dit "continue" | Phases 1-3 enchainees, gate avant Phase 4 |
| AUTONOMOUS | Utilisateur dit "fais tout" | Phases 1-4 enchainees, gate avant Phase 5 (implementation) |

L'implementation (Phase 5) requiert TOUJOURS une validation avant de coder.

---

## Adaptation et Replanification

Si 2 etapes echouent consecutivement (repo inaccessible, build casse, pattern incompatible) :
1. Logger l'echec dans `decision_log.jsonl` avec `confidence: low`
2. INVOQUER `/replan` -- ne pas improviser
3. Le nouveau plan remplace l'ancien dans `_alire/tracking/`

Cas typiques de replanification :
- Repo prive sans acces -> demander credentials ou URL alternative
- Lib source sans equivalent Go -> proposer implementation from scratch vs lib tierce
- Conflit d'architecture -> redefinir le scope avec l'utilisateur

---

## Tracabilite (OBLIGATOIRE)

### Plan persistant
Creer `_alire/tracking/PLAN_ANALYZE_{REPO}_{YYYY-MM-DD}.md` (template: `_alire/tracking/PLAN_TEMPLATE.md`).

### Decision log
Logger dans `_alire/02_LOGS/Journals/decision_log.jsonl` les decisions non-triviales.
Format: `{"timestamp","session","action","reasoning","alternatives_rejected":[],"outcome","confidence","plan_ref"}`

### Action journal
Chaque phase terminee -> une ligne dans le plan persistant avec :
- Horodatage
- Phase completee
- Livrable produit
- Decision prise (si applicable)

### Scoring agentique (/50)

| Critere | Points | Description |
|---------|--------|-------------|
| C1 Decomposition | /10 | Inventaire structure, identification modules, separation fonctionnalites |
| C2 Planification | /10 | Plan de transposition coherent, ordre d'implementation justifie |
| C3 Replanification | /10 | Adaptation face aux blocages, /replan invoque si necessaire |
| C4 Outillage dynamique | /10 | Utilisation Grep/Glob/WebSearch/WebFetch selon le besoin |
| C5 Tracabilite | /10 | Plan, decision_log, action journal, RETEX complets |

---

## REGLE ABSOLUE

**INTERDICTION DE CODER AVANT QUE L'UTILISATEUR AIT VALIDE CHAQUE PHASE.**

Pas de "je commence a implementer". Pas de "voici le code". Pas de raccourci.
Chaque phase produit un LIVRABLE ECRIT que l'utilisateur valide ou corrige
AVANT de passer a la phase suivante.

---

## Phase 1 : INVENTAIRE (COLLECTOR)

**Creer `_alire/tracking/TRACKER_ANALYZE_{REPO}_{YYYY-MM-DD}.json`** (schema `lia-file-tracker-v1`, voir `audit-pdca/references/file-tracker-spec.md`). Peupler `files[]` avec les fichiers du repo analyses, tous en `status=PENDING`, `action=AUDIT`.

### Ce que tu fais
1. Lire le README / documentation du repo
2. Lister la structure des fichiers (`tree` ou Glob)
3. Identifier : langage, framework, dependances, architecture
4. Compter : nombre de fichiers, lignes de code, modules

### Ce que tu livres
```
=== INVENTAIRE ===
REPO     : [nom/url]
LANGAGE  : [Python/JS/Rust/...]
FRAMEWORK: [Flask/Express/Actix/...]
STRUCTURE:
  - [dossier1/] : [description, N fichiers]
  - [dossier2/] : [description, N fichiers]
DEPENDANCES EXTERNES : [liste]
TAILLE   : [N fichiers, ~N lignes]
```

### GATE : Presenter l'inventaire. Demander a l'utilisateur :
> "Voici l'inventaire. Quel(s) module(s) t'interessent ? Tout ? Une partie ?"

**ATTENDRE LA REPONSE. NE PAS CONTINUER.**

---

## Phase 2 : ANALYSE FONCTIONNELLE (ANALYST)

### Ce que tu fais (uniquement sur les modules valides en Phase 1)
1. Lire le code des modules selectionnes
2. Identifier les FONCTIONNALITES (pas le code, les fonctionnalites)
3. Documenter les entrees/sorties de chaque fonctionnalite
4. Identifier les algorithmes/logiques metier cles
5. Reperer les dependances externes critiques (API, libs specifiques)

### Ce que tu livres
```
=== ANALYSE FONCTIONNELLE ===

FONCTIONNALITE 1 : [nom]
  Ce que ca fait : [description en 2-3 lignes]
  Entree         : [format, type]
  Sortie         : [format, type]
  Logique cle    : [algo, pattern, heuristique]
  Deps externes  : [lib X pour Y, API Z pour W]

FONCTIONNALITE 2 : [nom]
  ...
```

### GATE : Presenter l'analyse. Demander a l'utilisateur :
> "Voici ce que fait le code. Qu'est-ce que tu veux reprendre exactement ?
> Tout ? Certaines fonctionnalites ? Avec des modifications ?"

**ATTENDRE LA REPONSE. NE PAS CONTINUER.**

---

## Phase 3 : DELTA LIA-SEC (ANALYST)

### Ce que tu fais (uniquement sur les fonctionnalites validees en Phase 2)
1. Chercher dans LIA-SEC si on a deja quelque chose de similaire
   - Glob + Grep dans `cmd/sigma_web/`, `pkg/`, `sigma-react-frontend/src/`
2. Pour chaque fonctionnalite voulue, classifier :
   - **EXISTE** : on a deja ca (fichier:ligne)
   - **SIMILAIRE** : on a un truc proche qu'on peut etendre
   - **ABSENT** : a creer de zero
3. Identifier les conflits potentiels (conventions, architecture, nommage)

### Ce que tu livres
```
=== DELTA LIA-SEC ===

FONCTIONNALITE 1 : [nom]
  Statut LIA-SEC : EXISTE | SIMILAIRE | ABSENT
  Fichier existant : [path:ligne] (si existe/similaire)
  Ce qui manque    : [description precise]
  Conflit potentiel: [convention, archi, nommage]

FONCTIONNALITE 2 : [nom]
  ...

RESUME :
  - N EXISTE (rien a faire)
  - N SIMILAIRE (a etendre)
  - N ABSENT (a creer)
```

### GATE : Presenter le delta. Demander a l'utilisateur :
> "Voici ce qui existe deja et ce qui manque. On continue sur les ABSENT
> et SIMILAIRE ? Tu veux ajuster le scope ?"

**ATTENDRE LA REPONSE. NE PAS CONTINUER.**

---

## Phase 4 : PLAN DE TRANSPOSITION (PLANNER)

### Ce que tu fais (uniquement sur le scope valide en Phase 3)
Pour chaque fonctionnalite a transposer :
1. **Mapping langage** : equivalences syntaxiques et idiomatiques
   - Python dict -> Go map/struct
   - JS async/await -> Go goroutines/channels
   - Python list comprehension -> Go for range
2. **Mapping libs** : equivalences de dependances
   - requests (Python) -> net/http (Go)
   - express (JS) -> net/http handlers (Go)
   - pandas (Python) -> database/sql (Go)
   - React hooks (JS) -> React hooks (TS, memes patterns)
3. **Adaptation LIA-SEC** : ce qu'on change par rapport au source
   - Logger : `logger.LogSystemEvent()` pas `print()`
   - Config : `ConfigurationService` pas de hardcode
   - API : `fetchWithConfig()` pas `fetch()`
   - SQL : requetes parametrees
   - Error handling : Go style (`if err != nil`)
4. **Ordre d'implementation** : par quoi commencer

### Ce que tu livres
```
=== PLAN DE TRANSPOSITION ===

FONCTIONNALITE 1 : [nom]
  Source       : [langage/fichier]
  Cible LIA-SEC: [fichier Go/TS a creer ou modifier]
  Transpositions :
    - [pattern source] -> [pattern Go/TS]
    - [lib source] -> [lib Go/TS]
  Adaptations LIA-SEC :
    - [ce qui change par rapport au source]
  Estimation : [petit/moyen/gros]

ORDRE D'IMPLEMENTATION :
  1. [fonctionnalite X] (pas de dependance)
  2. [fonctionnalite Y] (depend de X)
  ...
```

### GATE : Presenter le plan. Demander a l'utilisateur :
> "Voici le plan de transposition. Ca correspond a ce que tu veux ?
> Des ajustements ? On lance l'implementation ?"

**ATTENDRE LA REPONSE. NE PAS CONTINUER.**

---

## Phase 5 : IMPLEMENTATION (EXECUTOR)

Seulement apres validation explicite des 4 phases precedentes.

1. Implementer UNE fonctionnalite a la fois
2. Gate apres chaque fonctionnalite : `go build` / `npm run build`
3. Montrer le diff a l'utilisateur
4. Passer a la suivante seulement apres validation

### VERIFICATION GATE TRANSPOSITION (BLOQUANT)

Apres chaque transposition de code vers Go/React LIA-SEC, AVANT de declarer "termine" :

1. **BUILD GATE** : `bash cmd/sigma_web/build_secure_lia.sh` (Go) + `cd sigma-react-frontend && node node_modules/.bin/vite build` (React)
2. **TEST GATE** : `cd sigma-react-frontend && npx vitest run` (tests existants ne cassent pas)
3. **IMPORT GATE** : Verifier imports manquants (alpha, useTheme, fetchWithConfig, customLogger)
4. **REGRESSION GATE** : Le code transpose ne doit pas introduire de nouveaux bugs
5. **SMOKE TEST** : Verifier que les endpoints/pages fonctionnent

Si une gate echoue : STOP, corriger, re-gate. JAMAIS declarer "termine" sans les 5 gates vertes.
Incident de reference : 188 fichiers casses par imports manquants (2026-03-17).

---

## Anti-patterns de cette skill

| INTERDIT | CORRECT |
|----------|---------|
| Lire le README et commencer a coder | Lire le README et presenter l'inventaire |
| "Je vais adapter tout le repo" | "Quelles parties t'interessent ?" |
| Copier-coller du code source | Transposer avec les conventions LIA-SEC |
| Creer de nouveaux fichiers sans demander | Presenter le plan de fichiers AVANT |
| "Ca devrait marcher comme ca" | Montrer le build qui passe |
| Reinventer ce qui existe deja | Chercher dans LIA-SEC d'abord (Phase 3) |
| Sauter les phases | CHAQUE phase a une gate utilisateur |

## Declencheurs

- "Analyse ce repo [url/path]"
- "Regarde ce code, on peut reprendre quelque chose ?"
- "Transpose ca en Go"
- "Adapte ce code pour LIA-SEC"
- "Porte cette lib en Go/React"
- "Y a un truc similaire dans [repo], regarde"
