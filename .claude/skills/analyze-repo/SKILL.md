---
name: analyze-repo
description: Analyse un repo externe (GitHub, code source, lib) pour identifier ce qui est reutilisable et planifier la transposition vers Rust/React inspect_ia_agents (Axum + React console + Python recette). Se declenche sur "analyse ce repo", "regarde ce code", "on peut reprendre ca", "transpose ca", "porte ca en Rust", "adapte ce code". INTERDIT de coder avant validation de chaque phase par l'utilisateur.
---

# Analyze Repo v3.0 - Analyse et transposition de code externe

Analyse un repo/code externe pour identifier ce qui est reutilisable
et planifier la transposition vers la stack inspect_ia_agents (Rust/Axum + React console + Python recette).

---

## Architecture Multi-Agent

| Etape | Role | Responsabilite |
|-------|------|---------------|
| Phase 1 Inventaire | COLLECTOR | Lire repo, lister structure, compter fichiers/LOC, identifier stack |
| Phase 2 Analyse fonctionnelle | ANALYST | Extraire fonctionnalites, E/S, logique metier, deps critiques |
| Phase 3 Delta inspect_ia_agents | ANALYST | Grep/Glob codebase inspect_ia_agents, classifier EXISTE/SIMILAIRE/ABSENT |
| Phase 4 Plan transposition | PLANNER | Mapping langage/libs, adaptations inspect_ia_agents, ordre implementation |
| Phase 5 Implementation | EXECUTOR | Coder une fonctionnalite a la fois, build gates, montrer diffs |
| Tracabilite | LIBRARIAN | Plan persistant, decision_log, preuves de recette, RETEX |

---

## Quality Hooks

| Hook | Declenchement | Action |
|------|--------------|--------|
| GATE_USER_VALIDATION | Fin de chaque phase (1-4) | STOP, presenter livrable, attendre validation explicite |
| BUILD_GATE | Apres chaque transposition (Phase 5) | `cargo build` + `cargo clippy --all-targets -- -D warnings` (Rust) + `vite build` (React console) -- BLOQUANT |
| REGRESSION_GATE | Apres chaque transposition (Phase 5) | Tests existants ne cassent pas, imports valides |
| DELTA_FRESHNESS | Debut Phase 3 | Grep/Glob sur inspect_ia_agents actuel (pas de cache) |

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
3. Le nouveau plan remplace l'ancien dans `docs/tracking/`

Cas typiques de replanification :
- Repo prive sans acces -> demander credentials ou URL alternative
- Lib source sans equivalent Rust (crates.io) -> proposer implementation from scratch vs crate tiers
- Conflit d'architecture -> redefinir le scope avec l'utilisateur

---

## Tracabilite (OBLIGATOIRE)

### Plan persistant
Creer `docs/tracking/PLAN_ANALYZE_{REPO}_{YYYY-MM-DD}.md` (template: `docs/tracking/PLAN_TEMPLATE.md`).

### Decision log
Logger dans `docs/tracking/decision_log.jsonl` les decisions non-triviales.
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

**Creer `docs/tracking/TRACKER_ANALYZE_{REPO}_{YYYY-MM-DD}.json`** (schema `lia-file-tracker-v1`, voir `audit-pdca/references/file-tracker-spec.md`). Peupler `files[]` avec les fichiers du repo analyses, tous en `status=PENDING`, `action=AUDIT`.

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

## Phase 3 : DELTA inspect_ia_agents (ANALYST)

### Ce que tu fais (uniquement sur les fonctionnalites validees en Phase 2)
1. Chercher dans inspect_ia_agents si on a deja quelque chose de similaire
   - Glob + Grep dans `src/`, `cmd/`, `discoveryprobe/`, `recette/`, `console/src/`
2. Pour chaque fonctionnalite voulue, classifier :
   - **EXISTE** : on a deja ca (fichier:ligne)
   - **SIMILAIRE** : on a un truc proche qu'on peut etendre
   - **ABSENT** : a creer de zero
3. Identifier les conflits potentiels (conventions, architecture, nommage)

### Ce que tu livres
```
=== DELTA inspect_ia_agents ===

FONCTIONNALITE 1 : [nom]
  Statut inspect_ia_agents : EXISTE | SIMILAIRE | ABSENT
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
   - Python dict -> Rust struct/HashMap
   - JS async/await -> Rust async/.await (tokio)
   - Python list comprehension -> Rust iterator chains (`.iter().map().collect()`)
2. **Mapping libs** : equivalences de dependances
   - requests (Python) -> reqwest (Rust)
   - express (JS) -> axum handlers (Rust)
   - pandas (Python) -> sqlx / SQL (Rust)
   - React hooks (JS) -> React hooks (TS, memes patterns)
3. **Adaptation inspect_ia_agents** : ce qu'on change par rapport au source
   - Logger : `tracing` structure (spans + fields) pas `print()` (R6)
   - Config : env + fichier de config versionne pas de hardcode (R5)
   - API : enveloppe de reponse `{success,data}` cote console pas `fetch()` brut
   - Persistance : event store derriere le trait `EventStore` (SQLite phase 1 -> PostgreSQL phase 2), requetes parametrees
   - Error handling : Rust `Result<T,E>` + operateur `?`, `thiserror`/`anyhow` en frontiere (R7)
4. **Ordre d'implementation** : par quoi commencer

### Ce que tu livres
```
=== PLAN DE TRANSPOSITION ===

FONCTIONNALITE 1 : [nom]
  Source       : [langage/fichier]
  Cible inspect_ia_agents: [fichier Rust .rs / TS .tsx a creer ou modifier]
  Transpositions :
    - [pattern source] -> [pattern Rust/TS]
    - [lib source] -> [lib Rust (crate) / TS]
  Adaptations inspect_ia_agents :
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
2. Gate apres chaque fonctionnalite : `cargo build` / `npm run build`
3. Montrer le diff a l'utilisateur
4. Passer a la suivante seulement apres validation

### VERIFICATION GATE TRANSPOSITION (BLOQUANT)

Apres chaque transposition de code vers Rust/React inspect_ia_agents, AVANT de declarer "termine" :

1. **BUILD GATE** : `cargo build` + `cargo clippy --all-targets -- -D warnings` (Rust) + `cd console && node node_modules/.bin/vite build` (React console)
2. **TEST GATE** : `cargo test` (Rust) + `python3 -m unittest discover -s tests` (recette Python) + `cd console && npx vitest run` (tests existants ne cassent pas)
3. **IMPORT GATE** : Verifier imports/usages manquants (modules Rust `use`, hooks React, enveloppe de reponse)
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
| Copier-coller du code source | Transposer avec les conventions inspect_ia_agents |
| Creer de nouveaux fichiers sans demander | Presenter le plan de fichiers AVANT |
| "Ca devrait marcher comme ca" | Montrer le build qui passe |
| Reinventer ce qui existe deja | Chercher dans inspect_ia_agents d'abord (Phase 3) |
| Sauter les phases | CHAQUE phase a une gate utilisateur |

## Declencheurs

- "Analyse ce repo [url/path]"
- "Regarde ce code, on peut reprendre quelque chose ?"
- "Transpose ca en Rust"
- "Adapte ce code pour inspect_ia_agents"
- "Porte cette lib en Rust/React"
- "Y a un truc similaire dans [repo], regarde"
