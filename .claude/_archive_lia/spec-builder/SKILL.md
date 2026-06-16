---
name: spec-builder
description: Specification fonctionnelle structuree pour un module LIA-SEC. Genere requirements (EARS), schema conceptuel (MCD Mermaid ERD), schema logique (SQL DDL PostgreSQL), API contract, wireframes textuels, et taches atomiques. Se declenche sur "spec", "specification", "definir le besoin", "schema conceptuel", "MCD", "cahier des charges", "requirements".
---

> **PREMIERE ACTION OBLIGATOIRE :** Annoncer "Using spec-builder skill. Analyzing context..." comme premiere ligne de reponse.

# Spec-Builder v3.0 -- Specification fonctionnelle et schema conceptuel

Tu es un architecte logiciel senior specialise en conception de systemes GRC/cybersecurite.
Tu produis des specifications formelles, exploitables directement par les developpeurs.

**Sources d'inspiration :** GitHub Spec Kit (MIT), cc-sdd/Kiro (MIT), designing-database-schemas, IEEE 830.

---

## Architecture Multi-Agent

| Etape | Role | Responsabilite |
|-------|------|----------------|
| Phase 0 : Analyse OSS | COLLECTOR | Rechercher repos, extraire schemas, catalogues, licences |
| Phase 1 : Contexte | ANALYST | Cadrer perimetre, parties prenantes, rattachement client |
| Phase 2 : Requirements | ANALYST | Rediger EARS, priorites MoSCoW, criteres d'acceptation |
| Phase 3 : Schema | PLANNER | MCD ERD Mermaid, SQL DDL, dictionnaire, verification gate |
| Phase 4 : API Contract | PLANNER | Endpoints REST, payloads, CRUD matrix par role |
| Phase 5 : Securite | ANALYST | STRIDE, RBAC, classification donnees, OWASP |
| Phase 6 : Wireframes | EXECUTOR | Layouts ASCII, composants MUI v7, UI Help specs |
| Phase 7 : Taches | PLANNER | Decoupage atomique, vagues, estimations |
| Phase 8 : Review | LIBRARIAN | Quality gates, traces, documentation, decision log |

---

## Quality Hooks

| Hook | Declenchement | Action |
|------|---------------|--------|
| **SQL-GATE** | Apres Phase 3 (migration.sql) | `psql -d lia_scan -f migration.sql` exit 0 + idempotency + FK + rollback |
| **TRACE-GATE** | Apres Phase 7 (tasks.md) | Chaque requirement trace vers schema, API, wireframe, tache |
| **CHECKPOINT** | Fin de chaque vague d'implementation | UI Help + menu + routes + build + commit verifies |
| **REVIEW-GATE** | Fin de chaque vague 2+ | `/review` execute, CRITICAL/HIGH = bloquant |

---

## Niveaux d'Autonomie

| Niveau | Condition | Comportement |
|--------|-----------|-------------|
| **AUTO** | Phases 0-2 (recherche, cadrage, requirements) | Executer sans demander, livrer les fichiers |
| **SEMI** | Phases 3-5 (schema SQL, API, securite) | Annoncer le plan, executer apres accord implicite |
| **MANUAL** | Phases 6-8 (wireframes, taches, review) | Valider avec l'utilisateur avant de finaliser |
| **GATE** | Verification SQL, checkpoint vague | Bloquer si gate echoue, ne pas contourner |

---

## Arguments

- `$ARGUMENTS[0]` - Nom du module (ex: `iso27005`, `nist-rmf`, `asset-management`)
- `--phase` - Phase a executer : `all` (defaut), `requirements`, `schema`, `api`, `tasks`
- `--output` - Repertoire de sortie (defaut: `_alire/specs/{module}/`)

---

## CONTEXTE LIA-SEC

Read `references/lia-sec-constraints.md` for the full technical constraints table and context files to load.

---

## WORKFLOW EN 8 PHASES

### Phase 0 : ANALYSE OPEN SOURCE (COLLECTOR -- via `/analyze-repo`)

**OBLIGATOIRE si le module a des equivalents OSS connus.**

1. Rechercher sur GitHub : `"{domain}" risk management open source`
2. Prioriser : licence permissive (MIT, Apache 2.0) > AGPL (donnees OK, code non copiable)
3. Maximum 3 repos a analyser. Lancer `/analyze-repo` sur chaque.
4. Pour chaque repo, extraire : schema de donnees, formules de calcul, catalogues/seed data, API patterns, licence.
5. Produire la **matrice de reutilisation** :

| Source | Licence | Donnees importables | Schema transposable | Formules portables | Effort import |
|--------|---------|--------------------|--------------------|-------------------|---------------|

6. **Regles de licence** :
   - **MIT / Apache 2.0 / CC0** : code et donnees copiables directement
   - **AGPL** : donnees (YAML, JSON, CSV) importables, code NON copiable -> portage clean-room en Go
   - **GPL** : incompatible avec LIA-SEC commercial, reference seulement
   - **Donnees standards** (ISO, NIST, MITRE) : toujours domaine public, importables
7. Decider pour chaque element : `IMPORT` | `PORT` | `INSPIRE` | `SKIP`

**Livrable :** `{output}/opensource_analysis.md`

---

### Phase 1 : CONTEXTE, PARTIES PRENANTES ET RATTACHEMENT CLIENT (ANALYST)

1. Identifier le perimetre du module (quel probleme, pour qui, modules impactes)
2. Lister les parties prenantes et leurs besoins (Role | Besoin | Priorite)
3. Identifier les modules existants connectes (tables, endpoints, composants reutilisables)

#### Rattachement Client (OBLIGATOIRE)

LIA-SEC est multi-tenant. Chaque module produit des donnees liees a un client.
La chaine de rattachement existante est :

```
clients (table)                  -- Le client (quadrigramme, nom, industrie, pays)
  |   API : GET /api/clients
  |
  +-- smsi_perimeters            -- Le perimetre d'audit du client
       |   FK : client_id -> clients.id
       |
       +-- {module_entity}       -- Les entites du module (assessments, analyses...)
            FK : perimeter_id -> smsi_perimeters.id
```

**Pour chaque nouveau module, specifier :**

| Question | Reponse |
|----------|---------|
| L'entite principale est-elle liee a un client ? | OUI (obligatoire) |
| Via quelle FK ? | perimeter_id -> smsi_perimeters -> clients |
| Le selecteur client apparait-il dans l'UI ? | OUI : dropdown en haut de chaque ecran |
| Le filtre client est-il dans l'API ? | OUI : ?client_id= sur les endpoints list |
| Le quadrigramme apparait-il dans les exports ? | OUI : header PPTX, footer Excel, nom fichier CSV |
| Peut-on voir les donnees de tous les clients ? | OUI pour Admin, filtre obligatoire pour autres roles |

**Tables existantes a reutiliser (NE PAS recreer) :**
- `clients` (id, quadrigramme, name, industry, country, status, tier)
- `smsi_perimeters` (id, name, client_id, perimeter_type, status)
- API : `GET /api/clients`, `GET /api/clients/{id}`, `POST /api/clients`

**Livrable :** Section "Contexte" + "Rattachement Client" dans `requirements.md`

---

### Phase 2 : REQUIREMENTS -- format EARS (ANALYST)

Utiliser le format **EARS** (Easy Approach to Requirements Syntax) :

| Type | Pattern |
|------|---------|
| Ubiquitous | The system shall [action] |
| Event-driven | When [event], the system shall [action] |
| State-driven | While [state], the system shall [action] |
| Unwanted | If [condition], the system shall [action] |
| Optional | Where [feature], the system shall [action] |

Chaque requirement : ID unique `REQ-NNN`, type (Functional/Non-functional/Constraint), priorite MoSCoW, pattern EARS, criteres d'acceptation testables, dependances, trace (table/endpoint).

**Regles :** Minimum 15 requirements. Chaque requirement testable. Dependances explicites.

**Livrable :** `{output}/requirements.md`

---

### Phase 3 : SCHEMA CONCEPTUEL -- MCD + MLD (PLANNER)

1. **MCD (3a)** : Identifier entites, attributs, relations (1:1, 1:N, M:N), cardinalites. Normaliser 1NF -> 2NF -> 3NF. Generer ERD Mermaid. Verifier contre tables existantes, documenter FK croisees, prefixer nouvelles tables.
2. **MLD (3b)** : Generer SQL DDL PostgreSQL complet, pret pour `cmd/sigma_web/migrations/`.
3. **Dictionnaire de donnees (3c)** : Table | Colonne | Type | Nullable | Description | Exemple.

Read `references/templates-schema.md` for ERD template, SQL DDL template, SQL rules LIA-SEC, and data dictionary format.

**Livrables :**
- `{output}/schema.md` (MCD ERD Mermaid + dictionnaire)
- `{output}/migration.sql` (SQL DDL pret pour `cmd/sigma_web/migrations/`)

### VERIFICATION GATE SQL (BLOQUANT)

Apres generation d'une migration SQL, AVANT de passer a la phase suivante :

1. **SYNTAX GATE** : `sudo -u postgres psql -d lia_scan -f {output}/migration.sql` doit reussir (exit code 0)
2. **IDEMPOTENCY GATE** : Executer la migration 2 fois de suite ne doit pas echouer (utiliser IF NOT EXISTS, CREATE OR REPLACE)
3. **FK GATE** : Verifier que toutes les FK referent des tables existantes (`\dt` dans psql)
4. **ROLLBACK GATE** : Un script de rollback (`DROP TABLE IF EXISTS ... CASCADE`) doit exister

Si une gate echoue : STOP, corriger le SQL, re-gate. JAMAIS livrer une migration qui ne s'applique pas.

---

### Phase 4 : API CONTRACT (PLANNER)

Pour chaque groupe d'endpoints, specifier : description, auth, request body (JSON), response (JSON), errors, handler Go name, trace requirements.

Chaque module DOIT inclure : `GET .../summary`, `GET .../export/json`, `GET .../export/csv`, `POST .../export/report` (si applicable).

Inclure la matrice CRUD par role.

Read `references/templates-api-security.md` for API contract template and CRUD matrix format.

**Livrable :** `{output}/api_contract.md`

---

### Phase 5 : SECURITE -- OWASP + RBAC + Donnees sensibles (ANALYST)

**LIRE D'ABORD :** `.claude/rules/anti-patterns.md` (section OWASP Quick Reference)

5 sous-phases :
- **5a. Threat Modeling STRIDE** : Evaluer S/T/R/I/D/E pour chaque entite
- **5b. Classification des donnees** : PUBLIC, INTERNE, CONFIDENTIEL, RESTREINT
- **5c. Matrice RBAC** : Permissions par endpoint et par role
- **5d. Input Validation** : Chaque champ utilisateur avec pattern/range/OWASP ref
- **5e. Checklist securite pre-implementation**

Read `references/templates-api-security.md` for STRIDE template, data classification, RBAC matrix, input validation patterns, and security checklist.

**Livrable :** `{output}/security.md`

---

### Phase 6 : WIREFRAMES TEXTUELS + UI HELP (EXECUTOR)

3 sous-phases :
- **6a. Wireframes textuels** : Layout ASCII, composants MUI v7, DataGrid colonnes, composants reutilisables vs nouveaux, estimation LOC, endpoints appeles
- **6b. UI Help Content** : Table bilingue EN+FR pour chaque ecran/tab, integration `/create-ui-help`
- **6c. Design Guidelines** : Theme, responsive, composants MUI v7, accessibilite, animations

Read `references/templates-wireframes-review.md` for wireframe template, wireframe rules, UI Help bilingual format, HelpButton pattern, design guidelines template.

**REGLE CRITIQUE :** UI Help DOIT etre insere dans la MEME vague que les composants frontend, PAS dans une vague separee.

**Livrable :** `{output}/wireframes.md` (wireframes + UI Help specs + design guidelines)

---

### Phase 7 : TACHES ATOMIQUES (PLANNER)

Chaque tache : ID `TASK-NNN`, phase, effort (heures), dependances, fichiers (max 3), criteres d'acceptation, trace requirements.

**Regles de decoupage :**
- Max 3 fichiers par tache
- Testable independamment
- Estimation d'effort en heures
- Dependances explicites
- Tri : schema -> backend -> frontend -> tests

**Vagues de livraison :**
- Vague 1 : Fondations (migration SQL, CRUD handlers, routes, build)
- Vague 2 : Frontend (dashboard, wizard, routing, menu)
- Vague 3 : Integrations (export, enrichissement, tests e2e)

**Livrable :** `{output}/tasks.md`

---

### Phase 8 : REVIEW AND DESIGN QUALITY (LIBRARIAN)

3 sous-phases :
- **8a. Code Review** (`/review`) : plan par vague, focus par type de fichier
- **8b. Frontend Design** (`/frontend-design`) : checklist qualite design production-grade
- **8c. React Best Practices** (`/react-recette`) : checklist performance React

Read `references/templates-wireframes-review.md` for code review plan template, design quality checklist, and React performance checklist.

**Gates :** `/review` apres CHAQUE vague (CRITICAL/HIGH = bloquant). `/frontend-design` apres vague frontend. `/react-recette` pour patterns React.

**Livrable :** Section "Review and Design Quality" dans `{output}/tasks.md`

---

## Adaptation et Replanification

- **2 echecs consecutifs** (gate SQL, build, trace incoherente) -> INVOQUER `/replan` immediatement
- **Ne JAMAIS improviser** : si une phase bloque, revenir a la phase precedente et corriger
- **Schema SQL ne compile pas** : corriger le DDL, re-gate, ne pas avancer avec un schema casse
- **Requirements incomplets** : revenir Phase 1 et reclarifier le perimetre avant de specifier
- **Escalade** : si 3 tentatives echouent sur une phase, documenter le blocage et demander validation utilisateur

---

## SKILLS CHAINEES -- VUE PIPELINE COMPLET

```
/spec-builder {module}
  |
  |-- Phase 0 : /analyze-repo (OSS research)
  |-- Phase 1 : Contexte + Client
  |-- Phase 2 : Requirements (EARS)
  |-- Phase 3 : Schema (MCD + SQL) -> SQL-GATE
  |-- Phase 4 : API Contract
  |-- Phase 5 : Securite (STRIDE + RBAC + OWASP)
  |-- Phase 6 : Wireframes + /create-ui-help (EN+FR) + /frontend-design
  |-- Phase 7 : Taches atomiques
  |-- Phase 8 : Review plan (/review + /frontend-design + /react-best-practices)
  |
  +-- IMPLEMENTATION (par vagues) :
       |-- Vague N : Coder -> /review -> /frontend-design -> /create-ui-help -> CHECKPOINT -> commit
       +-- Apres toutes les vagues : /audit-pdca {module} -> Documentation technique
```

---

## CHECKPOINT FIN DE VAGUE (OBLIGATOIRE)

**A chaque fin de vague, AVANT de passer a la suivante, afficher ce bloc :**

```markdown
## Checkpoint Vague N terminee

### Fait dans cette vague
- [ ] TASK-001 : ...
- [ ] TASK-002 : ...

### Vague N+1 a venir
- [ ] TASK-005 : ...
- [ ] TASK-006 : ...

### Actions transversales a verifier MAINTENANT
- [ ] UI Help inseree EN + FR pour chaque ecran ET chaque tab ? (0 = BLOQUANT)
- [ ] HelpButton present dans CHAQUE tab ?
- [ ] Menu navigation mis a jour pour les composants crees ?
- [ ] Routes App.tsx ajoutees pour chaque entree menu ?
- [ ] Build backend OK ? (build_secure_lia.sh)
- [ ] Build frontend OK ? (npm run build)
- [ ] Commit effectue ? (R1)

### Vagues restantes apres N+1
Effort restant estime : XXh
```

**Regles checkpoint :**
1. **UI Help = gate bloquante.** Si des ecrans ont ete crees et que le UI Help n'a pas ete insere, NE PAS passer a la vague suivante.
2. **Menu + Routes = gate bloquante.** Chaque composant DOIT avoir son entree menu et sa route.
3. **Build = gate bloquante.** Backend ET frontend doivent passer.
4. **Commit = gate bloquante.** Chaque vague terminee = 1 commit minimum (R1).
5. **Code Review = gate bloquante (Vague 2+).** CRITICAL et HIGH = fix avant vague suivante.
6. **Frontend Design = gate qualite (Vague frontend).** Production-grade, pas du boilerplate.

---

## LIVRABLES FINAUX

```
{output}/
  opensource_analysis.md  -- Repos OSS analyses, matrice reutilisation, licences
  requirements.md        -- 15+ requirements EARS avec criteres d'acceptation
  schema.md              -- MCD Mermaid ERD + dictionnaire de donnees
  migration.sql          -- SQL DDL PostgreSQL pret pour migrations/
  api_contract.md        -- Endpoints REST avec payloads JSON
  security.md            -- Threat model STRIDE, RBAC, input validation, checklist OWASP
  wireframes.md          -- Wireframes textuels par ecran + UI Help content specs
  tasks.md               -- Taches atomiques avec estimations et vagues
  SPEC_SUMMARY.md        -- Resume executif (1 page)
```

Le fichier `SPEC_SUMMARY.md` est un one-pager :

| Metrique | Valeur |
|----------|--------|
| Requirements | N |
| Tables PostgreSQL | N |
| Endpoints API | N |
| Composants React | N (dont N reutilises) |
| Taches | N |
| Effort total estime | Nh |
| Vagues de livraison | N |

---

## VALIDATION

Avant de livrer, verifier :

- [ ] Chaque requirement a un ID, une priorite MoSCoW, et des criteres d'acceptation
- [ ] L'ERD Mermaid est syntaxiquement correct
- [ ] Le SQL DDL utilise UUID, TIMESTAMPTZ, CHECK constraints, gen_random_uuid()
- [ ] Les endpoints API suivent les patterns existants (setCORSHeaders, LogSystemEvent, RecordAuditEvent)
- [ ] Les wireframes referent des composants MUI v7 reels
- [ ] Les taches sont atomiques (max 3 fichiers chacune)
- [ ] Les traces requirement -> schema -> API -> wireframe -> tache sont coherentes
- [ ] Aucun emoji dans aucun fichier
- [ ] **CLIENT :** Entite principale liee a un client via perimeter_id
- [ ] **CLIENT :** Selecteur client dropdown present sur chaque ecran principal
- [ ] **CLIENT :** Filtre ?client_id= sur tous les endpoints list
- [ ] **CLIENT :** Quadrigramme client dans les exports
- [ ] **DASHBOARD :** Au moins 4 KPI cards + 2 graphes detailles
- [ ] **EXPORT :** Chaque format detaille (colonnes Excel, slides PPTX, contenu CSV)
- [ ] **MENU :** Entrees menuConfig.tsx et routes App.tsx specifiees

---

## Tracabilite Agentique (OBLIGATOIRE)

### Plan persistant
Creer `_alire/tracking/PLAN_SPEC_{MODULE}_{YYYY-MM-DD}.md` (template: `_alire/tracking/PLAN_TEMPLATE.md`).

### Decision log
Logger dans `_alire/02_LOGS/Journals/decision_log.jsonl` les decisions non-triviales.
```bash
echo '{"timestamp":"'$(date -u +%Y-%m-%dT%H:%M:%SZ)'","session":"spec-{MODULE}","action":"SCHEMA_DESIGN","reasoning":"...","alternatives_rejected":["..."],"outcome":"...","confidence":"high","plan_ref":"PLAN_SPEC_{MODULE}"}' >> _alire/02_LOGS/Journals/decision_log.jsonl
```

### Action journal
A chaque phase, consigner dans le plan : action effectuee, resultat observe, decision prise.

---

## Scoring Agentique (/50)

| Critere | Points | Description |
|---------|--------|-------------|
| **C1 Decomposition** | /10 | Module correctement decoupe en phases, entites bien isolees |
| **C2 Planification** | /10 | Vagues coherentes, estimations realistes, dependances explicites |
| **C3 Replanification** | /10 | Adaptation apres echec gate (2 fails -> /replan), pas d'acharnement |
| **C4 Outillage dynamique** | /10 | Bons skills chaines (/analyze-repo, /review, /create-ui-help, /frontend-design) |
| **C5 Tracabilite** | /10 | Decision log rempli, plan mis a jour, traces requirement->code completes |
| **TOTAL** | **/50** | |
