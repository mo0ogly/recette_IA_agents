---
name: create-ui-help
description: Creer ou mettre a jour le contenu d'aide UI pour un composant/tab. Insere dans PostgreSQL table ui_help_content. Utiliser quand un HelpButton est vide, quand un nouvel ecran est cree, ou quand l'aide existante doit etre mise a jour.
---

# Skill : Create UI Help Content v3.0

Methodologie multi-agent pour creer/mettre a jour l'aide contextuelle UI dans PostgreSQL.
Principe : **R8 UI Help English Only -- tout contenu en anglais, stocke dans ui_help_content.**

---

## Architecture Multi-Agent

| Etape | Role | Responsabilite |
|-------|------|----------------|
| 1. Identification composant/tabs | COLLECTOR | Inspecter le composant React, lister les onglets, verifier l'existant en base |
| 2. Analyse du contenu existant | ANALYST | Evaluer la qualite de l'aide existante, identifier les manques, proposer le plan |
| 3. Planification contenu | PLANNER | Definir la structure Markdown, les sections, le ton, la longueur par tab |
| 4. Generation SQL + insertion | EXECUTOR | Ecrire le fichier SQL, executer l'insertion PostgreSQL, verifier via API |
| 5. Documentation + tracabilite | LIBRARIAN | Mettre a jour le tracking, le decision log, archiver le plan |

---

## Quality Hooks

| Hook | Declenchement | Action |
|------|---------------|--------|
| `verify-help-exists` | Apres insertion SQL | `curl -s http://127.0.0.1:8081/api/ui-help/{component}/{tab}?lang=en` -- verifier 200 + contenu non vide |
| `check-english-only` | Avant insertion | Verifier que le contenu ne contient pas de francais (mots-cles : "Cliquer", "Voir", "Aide") |
| `validate-markdown` | Avant insertion | Verifier structure Markdown valide (titres H1/H2, listes, pas de HTML brut) |
| `check-on-conflict` | Avant insertion | Verifier que chaque INSERT contient ON CONFLICT DO UPDATE (idempotence) |

---

## Niveaux d'autonomie

| Niveau | Quand | Comportement |
|--------|-------|--------------|
| FULL_AUTO | Composant existant, ajout de tab manquant | Inserer sans confirmation |
| SEMI_AUTO | Nouveau composant (premier ajout) | Proposer le plan, attendre validation du contenu |
| SUPERVISED | Mise a jour de contenu existant en production | Montrer le diff avant/apres, attendre validation |
| MANUAL | Composant critique (auth, security audit) | Plan detaille + validation chaque etape |

---

## Quand utiliser

- Un `HelpButton` affiche "No help available"
- Un nouvel ecran/tab est cree et n'a pas d'aide
- L'aide existante doit etre mise a jour
- Le hook `security_check.sh` detecte un HelpButton sans contenu

## Architecture du systeme d'aide (2026-03-16)

```
USER (COMPOSANTS)              ADMIN (GESTION)         BACKEND                 DATABASE
LiascanHelpSystem.tsx       HelpContentEditor.tsx    ui_help_api.go        PostgreSQL
  |                          |                          |                  ui_help_content
  | GET /api/ui-help/        | GET /api/admin/ui-help   |                      |
  | {component}/{tab}        | (toutes les langues) |-GetAllUIHelp() ------->|
  |--- JSON response --------|--- JSON array ----------|                     |
  | (default: en,            | (onglets dynamiques)     |                     |
  |  fallback auto)          | (filtres langue)         |                     |
  |                          | (Markdown preview)       |                     |
  |                          |                          |                     |
  |                          | POST/PUT /api/admin/     |                     |
  |                          | ui-help                  |-- UpsertUIHelp() ->|
```

Changement cle 2026-03-16 : **HelpContentEditor refondee** avec onglets dynamiques depuis PostgreSQL (plus de dictionnaire hardcode COMPONENT_TABS).

## Table PostgreSQL : ui_help_content

```sql
CREATE TABLE ui_help_content (
    id SERIAL PRIMARY KEY,
    component VARCHAR(100) NOT NULL,    -- 'cve_explorer', 'discovery', 'report_editor'
    tab_key VARCHAR(100) NOT NULL,      -- 'advanced-search', 'overview', 'detection'
    language VARCHAR(10) DEFAULT 'en',  -- 'en' (R8: UI Help English Only)
    title VARCHAR(255) NOT NULL,
    content TEXT NOT NULL,              -- Markdown
    is_active BOOLEAN DEFAULT true,
    version VARCHAR(20) DEFAULT '1.0.0',
    updated_by VARCHAR(100) DEFAULT 'system',
    last_updated TIMESTAMP DEFAULT NOW(),
    UNIQUE(component, tab_key, language)
);
```

## Workflow de creation

### Etape 1 : Identifier le composant et tab (COLLECTOR)

Trouver le composant et ses onglets/sections :
```tsx
// Dans le composant React
const COMPONENT_NAME = "cve_explorer";
const TABS = ["overview", "advanced-search", "cvss-filters"];
```

Les valeurs `component` et `tab_key` (kebab-case) sont les cles pour PostgreSQL.

**Remarque 2026-03-16 :** Avec la nouvelle architecture, tout composant ajoute en base apparait **automatiquement** dans HelpContentEditor (Admin). Plus besoin de modifier le code React.

Verifier l'existant :
```bash
psql_lia -c "SELECT component, tab_key, title FROM ui_help_content WHERE component = '{component}'"
```

### Etape 2 : Creer le contenu SQL (EXECUTOR)

Fichier : `cmd/sigma_web/sql/ui_help_{component}.sql`

Exemple :

```sql
INSERT INTO ui_help_content (component, tab_key, language, title, content, is_active, version, updated_by)
VALUES
('{component}', '{tab_key}', 'en', '{Title}',
'# {Title}

{Description du composant/tab}

## Features

- **Feature 1**: Description
- **Feature 2**: Description

## How to use

1. Step 1
2. Step 2
3. Step 3

## Tips

- Tip 1
- Tip 2', true, '1.0.0', 'system')
ON CONFLICT (component, tab_key, language) DO UPDATE
SET content = EXCLUDED.content, title = EXCLUDED.title, last_updated = NOW();
```

### Etape 3 : Executer le SQL

```bash
psql_lia < cmd/sigma_web/sql/ui_help_{component}.sql
```

### Etape 4 : Verifier (Quality Hook verify-help-exists)

```bash
psql_lia -c "SELECT component, tab_key, title FROM ui_help_content WHERE component = '{component}'"
```

Ou tester via API :
```bash
curl -s http://127.0.0.1:8081/api/ui-help/{component}/{tab_key}?lang=en
```

## Regles

1. **R8 : UI Help English Only** -- Tout le contenu d'aide est en anglais
2. **Contenu Markdown** -- Le champ `content` est du Markdown rendu par ReactMarkdown
3. **Fichier SQL separe** -- Un fichier par composant dans `cmd/sigma_web/sql/`
4. **ON CONFLICT** -- Toujours utiliser `ON CONFLICT DO UPDATE` pour l'idempotence
5. **Pas de hardcode dans le composant** -- L'aide vient TOUJOURS de PostgreSQL
6. **Admin editable** -- Le contenu est editable via Administration > Help Editor
7. **INTERDIT : HelpButton sans contenu en base** -- Ajouter un HelpButton SANS inserer le contenu dans `ui_help_content` est un PLACEHOLDER (R4 violation). "No help available" = interdit. Le workflow OBLIGATOIRE est : (1) creer le contenu SQL, (2) inserer en base, (3) verifier via API, (4) SEULEMENT ALORS ajouter le HelpButton au composant React.
8. **INTERDIT : helpId= prop** -- TOUJOURS utiliser `component="xxx" tabKey="yyy"` comme props separees. JAMAIS `helpId="xxx_yyy"`. Le format helpId ne matche PAS le split component/tab_key de l'API `/api/ui-help/{component}/{tab}`. Seul le format `component=` + `tabKey=` fonctionne.
9. **POST API : tab_key pas tab** -- Le endpoint `POST /api/admin/ui-help` attend le champ `tab_key` (pas `tab`). Un POST avec `"tab":"overview"` retourne `success:true` mais n'insere RIEN.
10. **Verification OBLIGATOIRE apres insertion** -- Apres chaque INSERT, verifier avec `GET /api/ui-help/{component}/{tab_key}?lang=en` que le contenu est bien retourne (pas "No help available").

## Composants existants (2026-03-16)

**Total : 37 composants, 165+ entrees UI Help**

| Composant | Entrees | Fichier SQL | Statut |
|-----------|---------|-------------|--------|
| `cve_explorer` | 29 | `sql/ui_help_cve_explorer.sql` | Production |
| `compliance_audit_analysis` | 20 | `sql/ui_help_compliance_audit_analysis.sql` | Production |
| `validation_dashboard` | 10 | `sql/ui_help_validation_dashboard.sql` | Production |
| `attack_chain_visualizer` | 5 | `sql/ui_help_attack_chain_visualizer.sql` | Production |
| `recette` (validation rules) | 14 | `migrations/004_recette_help.sql` | Production |
| Autres composants | ~87 | Divers SQL + migrations | Production |

Pour la liste complete :
```sql
SELECT DISTINCT component, COUNT(*) as entries
FROM ui_help_content
GROUP BY component
ORDER BY entries DESC;
```

## Edition via Administration UI (2026-03-16)

**Interface HelpContentEditor completement refondee**

1. Menu Administration > Help Editor
2. **Les onglets se chargent dynamiquement** depuis PostgreSQL (buildComponentTabs)
3. Selectionner le composant (dropdown)
4. Selectionner l'onglet dans le composant (charge auto)
5. Voir les **badges de langue** (FR / EN) indiquant les langues disponibles
6. Cliquer "View" pour voir l'apercu **Markdown rendu complet**
7. Cliquer "Edit" depuis le dialog pour modifier
8. Sauvegarder (PUT /api/admin/ui-help/{id})
9. Le compteur dynamique en header se met a jour auto (X composants | Y entrees)

**Avantages :**
- Tout nouveau composant ajoute en base apparait **automatiquement** (zero code React a modifier)
- Filtres multi-langue (All / FR / EN) pour filtrer les entrees
- Apercu Markdown complet avec styles (titres, listes, code blocks, tables, blockquotes)
- Historique versionne et consultable

Le contenu est auto-indexe dans HelpManager (user) avec recherche full-text.

---

## Adaptation et Replanification

- **2 echecs consecutifs** (ex: SQL echoue + API retourne 404) -> invoquer `/replan`
- **Jamais improviser** : si le composant React n'existe pas, verifier avant de creer du contenu
- **Fallback** : si PostgreSQL est down, NE PAS creer le SQL sans le tester -- attendre que la base soit disponible
- **Replanification documentee** : chaque changement de plan est trace dans le decision log

---

## Tracabilite (OBLIGATOIRE)

### Plan persistant
Creer `_alire/tracking/PLAN_UI_HELP_{COMPONENT}_{YYYY-MM-DD}.md` (template: `_alire/tracking/PLAN_TEMPLATE.md`).

### Decision log
Logger dans `_alire/02_LOGS/Journals/decision_log.jsonl` les decisions non-triviales.
```bash
echo '{"timestamp":"'$(date -u +%Y-%m-%dT%H:%M:%SZ)'","session":"ui-help-{component}","action":"ACTION","reasoning":"...","alternatives_rejected":["..."],"outcome":"...","confidence":"high","plan_ref":"PLAN_UI_HELP_{COMPONENT}_{DATE}.md"}' >> _alire/02_LOGS/Journals/decision_log.jsonl
```

### Action journal
Maintenir un journal d'actions dans le plan persistant :
```
[HH:MM] COLLECTOR - Inspecte composant X, 3 tabs trouves, 1 manquant
[HH:MM] EXECUTOR - SQL insere pour tab "overview", verification API OK
[HH:MM] LIBRARIAN - Plan clos, RETEX ecrit
```

---

## Scoring Agentique (/50)

| Critere | Points | Description |
|---------|--------|-------------|
| C1 Decomposition | /10 | Identification correcte du composant, tabs, contenu manquant |
| C2 Planification | /10 | Plan coherent avant execution, structure Markdown adaptee |
| C3 Replanification | /10 | Gestion des echecs (SQL, API), adaptation sans improvisation |
| C4 Outillage dynamique | /10 | Utilisation correcte des hooks (verify-help-exists, check-english-only) |
| C5 Tracabilite | /10 | Plan persistant, decision log, action journal complets |
