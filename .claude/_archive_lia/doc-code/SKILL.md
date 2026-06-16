---
name: doc-code
version: "2.0"
description: "Documentation engine for LIA-SEC with swarm orchestration (6 agents), OODA loop, standardized templates, and anomaly surfacing. Generates English docs (.md), Mermaid diagrams (.mmd + .json sources), Word (.docx), and Python-generated XML. Triggers on: document this module, godoc, doc architecture, generate diagram, doc-code, create documentation, update docs. Covers Go backend, React frontend, PostgreSQL schema, cross-cutting architecture. Integrates with /apex, /audit-pdca, /retex-analyzer."
---

# Doc-Code v2.0 -- Swarm Documentation Engine

Generate, update, and maintain LIA-SEC documentation through a 6-agent swarm
orchestrated by the Program Director following an OODA loop.

**Output:** English .md + .mmd sources + .json descriptors + .docx exports
**Organization:** Librarian pattern (by type, not chronology) -- see `references/doc-template-standard.md`

---

## Syntax

```
/doc-code <module> [flags]
```

| Flag | Description |
|------|-------------|
| `--update` | Update existing docs (detect deltas, bump version) |
| `--swarm` | Force full swarm (6 agents). Default: auto-detect complexity |
| `--no-swarm` | Economy mode, single-agent execution |
| `--scope=back\|front\|full` | Limit scope (default: auto-detect) |
| `--export=docx` | Also generate Word export |
| `--diagrams-only` | Only generate/update Mermaid diagrams |

---

## Architecture

```
SKILL.md (this file)         -- Orchestrator: syntax, workflow, gates
references/
  swarm-roles.md             -- 6 agent roles with exact prompts
  doc-template-standard.md   -- Mandatory template + librarian file organization
  ooda-protocol.md           -- OODA loop: Observe -> Orient -> Decide -> Act
  integration-apex-pdca.md   -- How doc-code chains with /apex, /audit-pdca, /replan
  retex-anomaly-protocol.md  -- Anomaly surfacing during documentation
  doc-classification.md      -- Types, levels, SemVer, status workflow, metadata schema
  mermaid-templates.md       -- JSON descriptor examples for all diagram types
scripts/
  generate_mermaid.py        -- Mermaid diagram generator (architecture/sequence/er/component/flow/gantt)
  generate_word_doc.py       -- Word .docx generator from Markdown
  doc_classifier.py          -- Metadata manager (init/bump/status/show/list/index)
  doc_librarian.py           -- Documentation health: audit, organize, rename, freshness, reindex, fix
  setup.sh                   -- Install Python dependencies
```

---

## Swarm Roles (6 Agents)

| # | Role | Scope | Phase | Details |
|---|------|-------|-------|---------|
| 0 | **Program Director** | All | Orchestrator | Runs in main context. OODA loop, launches agents, consolidates. |
| 1 | **Backend Specialist** | `cmd/sigma_web/*.go`, `pkg/**/*.go` | Phase 1 (parallel) | Extracts handlers, functions, structs, dependencies. |
| 2 | **Frontend Specialist** | `sigma-react-frontend/src/**` | Phase 1 (parallel) | Extracts components, hooks, services, component tree. |
| 3 | **Architect** | Cross-cutting | Phase 2 (after 1+2) | Generates Mermaid diagrams from agent reports. |
| 4 | **QA** | All docs | Phase 4 (after writing) | Validates accuracy, template compliance, cross-references code. |
| 5 | **Recette** | Final | Phase 5 (after QA) | Produces the audit trail: what was done, coverage, anomalies. |

**Exact prompts and launch commands:** `references/swarm-roles.md`

**Launch pattern (MANDATORY):**
```
Phase 1: 1 message, 2 Agent tool calls (BackendSpec + FrontendSpec), run_in_background: true
Phase 2: After Phase 1 completes -> Architect agent
Phase 3: Program Director writes/updates docs
Phase 4: QA agent
Phase 5: Recette agent
```

All agents use `subagent_type: general-purpose`, `mode: auto`.
NEVER use `action-agent` (too lightweight, no skills access).

**Model Selection (MANDATORY -- cost optimization):**

| Agent | Model | Rationale |
|-------|-------|-----------|
| Backend Specialist | `haiku` | Code extraction = grep/read patterns, no generation |
| Frontend Specialist | `haiku` | Code extraction = grep/read patterns, no generation |
| Architect | `sonnet` | Diagram generation requires architectural reasoning |
| QA | `haiku` | Checklist validation, template compliance check |
| Recette | `haiku` | Report consolidation, anomaly cataloging |

JAMAIS lancer un agent extraction/validation sur opus. Cout x25 pour zero gain.

---

## OODA Loop

Every execution follows: **OBSERVE -> ORIENT -> DECIDE -> ACT -> OBSERVE(post)**

**Full protocol:** `references/ooda-protocol.md`

**Quick reference:**

| Phase | Goal | Key Action |
|-------|------|------------|
| OBSERVE | Gather facts | Check existing docs, read code, compare freshness |
| ORIENT | Analyze | CREATE vs UPDATE vs ARCHIVE vs SKIP + complexity scoring |
| DECIDE | Plan | Which agents, which sections, success criteria |
| ACT | Execute | Launch swarm, write docs, generate diagrams |
| POST-OBSERVE | Verify | QA score >= 80, all docs on disk, anomalies cataloged |

**Complexity auto-detection:**
- Score 1-3: TRIVIAL -> no swarm, single agent
- Score 4-7: MODERATE -> full swarm minus optional roles
- Score 8+: COMPLEX -> full swarm, all 6 roles

---

## Existing Docs Protocol

**ALWAYS check before creating.** See `references/integration-apex-pdca.md` for full protocol.

```bash
# Step 1: Find existing docs
find _alire/01_DOCUMENTATION/ -name "*{module}*" -type f 2>/dev/null
find _alire/01_DOCUMENTATION/ -name "*{module}*" -type f 2>/dev/null

# Step 2: Decide action
# CREATE | UPDATE | ARCHIVE | SKIP | FIX | CONSOLIDATE

# Step 3: Archive obsolete (NEVER delete)
mv _alire/01_DOCUMENTATION/old.md _alire/01_DOCUMENTATION/archive/old_v1.0.0_archived_2026-03-28.md
```

---

## Output Formats

### 1. Markdown (.md) -- Primary

Structure: `references/doc-template-standard.md`
Organization: librarian pattern (_alire/01_DOCUMENTATION/api/, _alire/01_DOCUMENTATION/architecture/, _alire/01_DOCUMENTATION/technical/, etc.)
Language: **English only**

### 2. Mermaid Diagrams (.mmd + .json)

Each diagram produces TWO files:
- `{module}_{type}.json` -- Input descriptor (reusable, editable)
- `{module}_{type}.mmd` -- Generated Mermaid source

Types: architecture, sequence, er, component, flow, gantt
Templates: `references/mermaid-templates.md`

```bash
python3 .claude/skills/doc-code/scripts/generate_mermaid.py {type} {input.json} \
  -o {output.mmd} --theme dark
```

### 3. Word (.docx) -- On demand

```bash
python3 .claude/skills/doc-code/scripts/generate_word_doc.py {input.md} \
  --meta {.doc-meta.json} -o {output.docx}
```

### 4. Metadata (.doc-meta.json) -- Automatic

Every .md gets a sidecar metadata file via `doc_classifier.py init`.
Schema: `references/doc-classification.md`

---

## Inline Code Documentation

When the target is code comments (not standalone docs):

### Go (godoc)

```go
// ValidateRule checks a YAML rule against the 13 validation phases.
// Returns errors sorted by severity (CRITICAL > HIGH > MEDIUM > LOW).
func ValidateRule(rulePath string) ([]ValidationError, error) {
```

### React/TypeScript (JSDoc/TSDoc)

```typescript
/**
 * Dashboard for AI compatibility status across 5 subsystems.
 * @requires fetchWithConfig - API calls via JWT middleware
 * @requires ConfigurationService - backend URL resolution
 */
const AICompatibilityDashboard: React.FC<Props> = ({ onRefresh }) => {
```

### Rules

- **WHY > WHAT**: explain the reason, not the obvious
- **English only** (R12)
- **No emoji** (R10)
- **Skip trivial**: `func GetID()` does not need a comment
- **Handlers**: include route, method, params, response codes
- **Build gate**: `build_secure_lia.sh` (Go), `vite build` (React) after edits

---

## Anomaly Surfacing (RETEX)

Every agent reports anomalies discovered while reading code.
The Recette agent consolidates them into a severity-classified report.

**Categories:** DEAD_CODE, SECURITY, COMPLIANCE, ARCHITECTURE, PERFORMANCE, INCONSISTENCY, MISSING_TEST, TECH_DEBT

**Escalation:**
- CRITICAL: alert user immediately, block commit
- HIGH: include in RETEX, fix next cycle
- MEDIUM/LOW: log for awareness

**Full protocol:** `references/retex-anomaly-protocol.md`

---

## Integration with Other Skills

| Trigger | Chain |
|---------|-------|
| `/apex` completes | `/doc-code {module} --update` |
| `/audit-pdca` Phase A | `/doc-code {fixed_modules} --update` |
| New handler API | `/api-handoff {feature} --r17` then `/doc-code {module} --update` |
| New React component | `/doc-code` + `/create-ui-help` |
| PDCA cycle | Documentation task MANDATORY in every cycle |
| Backend done, frontend starting | `/api-handoff {feature}` -- targeted contract for frontend dev |
| New PostgreSQL tables needed | `/db-schema-designer --new-module --erd` before any Go handler |

**Full integration guide:** `references/integration-apex-pdca.md`

---

## Workflow Summary

```
1. OBSERVE   : Check existing docs, read code, assess freshness
2. ORIENT    : CREATE | UPDATE | ARCHIVE | SKIP + complexity score
3. DECIDE    : Plan agents, sections, success criteria
4. ACT       :
   4a. Launch BackendSpec + FrontendSpec (parallel)
   4b. Launch Architect (after 4a)
   4c. Write/update docs using standard template
   4d. Launch QA
   4e. Launch Recette
5. GATE      : QA >= 80, all docs exist, metadata initialized, anomalies cataloged
6. COMPLETE  : Archive old versions, commit, announce next steps
```

---

## Decomposition des sous-taches

Au demarrage, decomposer la demande en sous-taches independantes :

- [ ] Sous-tache 1 : `find _alire/01_DOCUMENTATION/ -name "*{module}*"` -- docs existantes ?
- [ ] Sous-tache 2 : lire code source du module (Backend/Frontend Specialist)
- [ ] Sous-tache 3 : generer diagrammes Mermaid (.json + .mmd)
- [ ] Sous-tache 4 : ecrire/mettre a jour le fichier .md (template standard, EN only)
- [ ] Sous-tache 5 : `doc_classifier.py init` + `doc_librarian.py reindex`
- [ ] Sous-tache 6 : QA agent -- validation template + accuracy + anomalies

Utiliser `TaskCreate` pour tracker si > 3 sous-taches.

## Plan d'execution

Pour tout module non trivial (nouveau doc ou mise a jour > 2 sections) :

1. Creer `_alire/tracking/PLAN_DOC_CODE_{MODULE}_{YYYY-MM-DD}.md` avant tout ecriture.
2. Template : `_alire/tracking/PLAN_TEMPLATE.md`.
3. Cocher chaque sous-tache a la completion.
4. Si replanification : Status -> REPLANIFIE + lien vers nouveau plan.

Pour une mise a jour ponctuelle (< 2 sections, doc existante) : plan inline suffit.

## Adaptation et replanification

Si 2 etapes consecutives echouent (ex: doc_librarian audit echoue + fix qui casse naming) :

- STOP
- Invoquer `/replan` -> produit `PLAN_DOC_CODE_*_REPLAN_*.md`
- NE PAS retailler le template sans audit prealable

Declencheurs typiques :
- `doc_librarian.py audit` exit != 0 apres fix -> REPLAN
- Naming convention violee apres renommage -> REPLAN
- Swarm agent retourne anomalie CRITICAL -> REPLAN (correction avant ecriture doc)

## Outils declares

| Outil | Usage | Retry policy |
|-------|-------|--------------|
| `Read`, `Grep`, `Glob` | Explorer code source + docs existantes avant ecriture | N/A |
| `Write`, `Edit` | Creer/modifier .md, .mmd, .json, .doc-meta.json | N/A |
| `Bash doc_librarian.py audit` | Health check complet (naming, metadata, fraicheur) | 1 retry apres fix |
| `Bash doc_librarian.py reindex` | Regenerer INDEX.md apres creation/MAJ | Obligatoire post-ecriture |
| `Bash doc_classifier.py init/bump` | Initialiser / bumper metadata .doc-meta.json | Obligatoire |
| `Bash generate_mermaid.py` | Generer diagrammes depuis descripteur .json | N/A |
| `TaskCreate` | Tracking si > 3 sous-taches | N/A |
| `Skill(create-ui-help)` | Si composant React documente + nouvel ecran | Obligatoire |

Selection dynamique : outil choisi selon le contexte, pas de liste figee.

## Tracabilite agentique

### Plan persistant
```
_alire/tracking/PLAN_DOC_CODE_{MODULE}_{YYYY-MM-DD}.md
```

### Decision log
```bash
echo '{"timestamp":"'$(date -u +%Y-%m-%dT%H:%M:%SZ)'","session":"doc-code","action":"ACTION","reasoning":"...","alternatives_rejected":["..."],"outcome":"...","confidence":"high","plan_ref":"PLAN_DOC_CODE_*.md"}' >> _alire/02_LOGS/Journals/decision_log.jsonl
```

Logger chaque decision non triviale : choix CREATE vs UPDATE, choix de type doc (api/arch/tech/user), rejet d'un template, archivage d'une version.

RETEX en fin de session si score agentique < 40/50 -> `_alire/02_LOGS/Journals/retex/RETEX_DOC_CODE_{MODULE}_{YYYY-MM-DD}.md`.

### Replanification
If 2+ steps fail consecutively -> invoke `/replan`.
Never retry the same action identically. Always change at least one variable.

---

## Verification Gate (BLOCKING)

Before declaring done:

- [ ] All planned docs exist on disk
- [ ] Metadata `.doc-meta.json` initialized for each doc
- [ ] Diagrams generated (.json descriptor + .mmd source)
- [ ] QA score >= 80/100
- [ ] Build passes (Go: `build_secure_lia.sh`, React: `vite build`)
- [ ] Zero emoji, zero TODO, zero placeholder in final docs
- [ ] English only in .md files and code comments (R12)
- [ ] Old versions archived in `_alire/01_DOCUMENTATION/archive/` (never deleted)
- [ ] Anomaly report produced (even if empty)
- [ ] `_alire/01_DOCUMENTATION/INDEX.md` regenerated via `doc_classifier.py index`
- [ ] DOCS-SITE rebuilt: `cd docs-site && npm run build:search` then `rsync -avz --delete docs-site/build/ /opt/lia-sec/source/docs-site/` -- verify HTTP 200 on inspect-ia-agents.tech/docs/
- [ ] If React component: `/create-ui-help` verified
- [ ] If API handler: `api-reference.md` updated

---

## Scoring agentique

| Critere | Score |
|---------|-------|
| C1 Decomposition : sous-taches identifiees (find + read + write + librarian) ? | /10 |
| C2 Planification : PLAN_DOC_CODE_*.md cree et suivi ? | /10 |
| C3 Replanification : /replan declenche sur echecs consecutifs (audit exit != 0, CRITICAL) ? | /10 |
| C4 Outillage : doc_librarian.py + doc_classifier.py + generate_mermaid.py invoques dynamiquement ? | /10 |
| C5 Tracabilite : decision_log + RETEX produits ? | /10 |

Score total /50 -- >= 40 : Exemplaire | 30-39 : Acceptable | < 30 : RETEX obligatoire

---

## Librarian (Documentation Health)

The librarian guarantees: naming convention, correct directory placement,
versioning, anti-obsolescence, and indexation.

```bash
# Full health audit (naming, organization, metadata, staleness, duplicates)
python3 .claude/skills/doc-code/scripts/doc_librarian.py audit _alire/01_DOCUMENTATION/

# Check freshness (detect stale/obsolete docs, default 90 days threshold)
python3 .claude/skills/doc-code/scripts/doc_librarian.py freshness _alire/01_DOCUMENTATION/ --max-age=90

# Rename non-compliant files to {module}_{type}_en.md (dry-run first)
python3 .claude/skills/doc-code/scripts/doc_librarian.py rename _alire/01_DOCUMENTATION/ --dry-run
python3 .claude/skills/doc-code/scripts/doc_librarian.py rename _alire/01_DOCUMENTATION/

# Move files to correct type directories (dry-run first)
python3 .claude/skills/doc-code/scripts/doc_librarian.py organize _alire/01_DOCUMENTATION/ --dry-run
python3 .claude/skills/doc-code/scripts/doc_librarian.py organize _alire/01_DOCUMENTATION/

# Regenerate INDEX.md with health indicators (Current/Stale/Obsolete)
python3 .claude/skills/doc-code/scripts/doc_librarian.py reindex _alire/01_DOCUMENTATION/ -o _alire/01_DOCUMENTATION/INDEX.md

# Auto-fix everything: metadata + naming + organization + index
python3 .claude/skills/doc-code/scripts/doc_librarian.py fix _alire/01_DOCUMENTATION/ --dry-run
python3 .claude/skills/doc-code/scripts/doc_librarian.py fix _alire/01_DOCUMENTATION/ --auto
```

**The librarian is called automatically at the end of every doc-code execution (step 6 COMPLETE).**

Naming convention enforced: `{module}_{type}_en.md`
- Type inferred from: metadata > directory > filename keywords > fallback TECH
- Keyword inference: plan/design -> SPEC, guide/howto -> USER, arch/overview -> ARCH, api/reference -> API, security/hardening -> SEC
- Date prefixes stripped: `2026-03-06-smsi-plan.md` -> `smsi_plan_spec_en.md`

---

## Quick Commands

```bash
# Generate full module documentation
/doc-code discovery

# Update existing docs after code changes
/doc-code compliance --update

# Diagrams only
/doc-code cve_explorer --diagrams-only

# With Word export
/doc-code remediation --export=docx

# Economy mode (no swarm)
/doc-code maturity_scoring --no-swarm

# Backend only
/doc-code ai_engine --scope=back
```
