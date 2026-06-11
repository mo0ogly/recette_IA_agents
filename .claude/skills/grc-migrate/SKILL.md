---
name: grc-migrate
description: Bidirectional migration skill between EBIOS RM studies and ISO 27005 assessments. Generates a gap-tracked migration plan, creates the target artefact, maps data fields, and tracks remaining gaps with a green check per resolved item. Marks "Migration FULL" when all gaps are closed.
---

# grc-migrate -- EBIOS RM <-> ISO 27005 migration skill (APEX-style)

Bidirectional migration between an EBIOS RM study (`ebios_rm_studies` + workshops W1-W5) and an ISO 27005:2022 assessment (`smsi_risk_assessments` + `iso27005_*`). Produces:

1. A **migration plan** (`_alire/tracking/PLAN_GRC_MIGRATE_{direction}_{source_id}_{YYYY-MM-DD}.md`) with a gap checklist.
2. The **target artefact** (new EBIOS study OR new ISO assessment) pre-filled from source data.
3. A **gap tracker** -- each unresolved gap is `- [ ]`, each resolved gap is `- [x]` with a green check. When all gaps are `[x]`, the plan footer flips to `Status: MIGRATION FULL`.

## Syntax

```
/grc-migrate <direction> <source_id> [--client=UUID] [--dry-run] [--resume]
```

| Arg | Values | Description |
|-----|--------|-------------|
| `direction` | `ebios-to-iso` \| `iso-to-ebios` | Migration direction |
| `source_id` | UUID | Source study (EBIOS) or assessment (ISO) id |
| `--client` | UUID | Target client; defaults to source's client |
| `--dry-run` | flag | Only produce the plan + gap analysis, do not INSERT |
| `--resume` | flag | Continue an existing migration plan (re-check gaps, flip boxes) |

## Phases (APEX-like, autonomous)

### P0 -- INIT

1. Load source: `SELECT * FROM ebios_rm_studies WHERE id=...` OR `SELECT * FROM smsi_risk_assessments WHERE id=...`.
2. Create `PLAN_GRC_MIGRATE_{direction}_{source_id}_{DATE}.md` from template below.
3. Build `swarm_memory.json` with: source payload, target schema, known gap catalogue (see `references/gap-catalogue.md`).

### P1 -- OBSERVE (cartography + completeness)

Run these queries against source and populate `Source Inventory` section of the plan:

**EBIOS source inventory (ebios-to-iso):**
- W1: feared_events, business_values, supporting_assets
- W2: risk_sources, target_objectives, roto, stakeholders, stakeholder_rs_links
- W3: strategic_scenarios
- W4: operational_scenarios, attack_paths, attack_techniques, elementary_actions
- W5: security_measures, risk_treatment_plans, risk_assessments

**ISO source inventory (iso-to-ebios):**
- `smsi_risk_scenarios`, `smsi_risk_assessments`, `smsi_assets`
- `iso27005_threats`, `iso27005_vulnerabilities`, `iso27005_threat_sources`
- `iso27005_controls`, `iso27005_soa_entries`
- `iso27005_control_scenario_mapping`, `iso27005_monitoring_events`

### P2 -- GAP ANALYSIS

Emit one row per gap in `## Migration Gap Tracker`. Reference catalogue in `references/gap-catalogue.md` for canonical mappings. Each row:

```
- [ ] G{nn} -- {short title}
      Source field(s) : {list}
      Target field(s) : {list}
      Strategy        : DIRECT | ADAPT | DERIVE | MANUAL | DROP
      Status          : PENDING
```

### P3 -- DO (execute mappings)

For each gap with Strategy in {DIRECT, ADAPT, DERIVE}:
1. Execute mapping (INSERT into target tables, idempotent via ON CONFLICT or existence check).
2. If successful: flip `- [ ]` to `- [x]` and append ` ✓ {ISO timestamp}` at the end of the Status line.
3. If failed: leave unchecked, append ` -- ERROR: {reason}` and continue (do not block).

For MANUAL gaps: leave unchecked with `Status : MANUAL -- {instruction}`. User must resolve later and rerun with `--resume`.

For DROP gaps: flip to `[x]` immediately with Status `DROPPED -- {reason}` (they cannot block FULL).

### P4 -- VERIFY

Recompute checklist. Count `- [x]` / total.

- All boxes checked -> flip file-level footer to `Status: MIGRATION FULL ✓` and log `grc_migrate_full` event via `LogSystemEvent`.
- Otherwise -> `Status: PARTIAL ({checked}/{total})`.

### P5 -- FINALIZE

1. `git add` the plan + any migration SQL generated.
2. Print summary to user with checklist progress + next manual steps.

## Resume mode

`--resume` re-runs P3 only for gaps whose Status is still PENDING or ERROR or MANUAL. Re-evaluates each; flips boxes when resolvable. Useful after user resolved a MANUAL gap externally (UI edits, evidence upload).

## Plan template

Stored at `references/plan-template.md`. Minimum sections:

```markdown
# GRC Migration -- {direction}
Source : {source_id} ({source_name})
Target : {target_id or "to be created"}
Client : {client_id}
Date   : {YYYY-MM-DD}
Status : IN_PROGRESS

## Source Inventory
(auto-populated from P1 queries)

## Target Schema
(auto-populated: which tables will receive INSERTs)

## Migration Gap Tracker
- [ ] G01 -- ...
- [ ] G02 -- ...

## Decision Log
(REPLAN entries, ERROR escalations)

## Footer
Checked: {N}/{total}
Status : IN_PROGRESS | PARTIAL (N/total) | MIGRATION FULL ✓
```

## Gap catalogue (extract -- see `references/gap-catalogue.md`)

### EBIOS -> ISO 27005

| Gap | EBIOS field | ISO field | Strategy |
|-----|-------------|-----------|----------|
| G01 | ebios_rm_studies.name | smsi_risk_assessments.name | DIRECT |
| G02 | ebios_rm_feared_events | smsi_risk_scenarios.impact | ADAPT (4-level severity -> 5-level impact) |
| G03 | ebios_rm_risk_sources (M×R×A 1-3) | iso27005_threat_sources (MxOxCxR) | ADAPT |
| G04 | ebios_rm_strategic_scenarios | smsi_risk_scenarios | DIRECT |
| G05 | ebios_rm_security_measures (baseline/complementary) | iso27005_soa_entries (Annex A 93) | MANUAL -- no auto-mapping |
| G06 | ebios_rm_risk_assessments.severity_likelihood (4×4) | smsi_risk_assessments prob×impact (5×5) | ADAPT |
| G07 | ebios_rm_stakeholders | -- | DROP (no ISO equivalent) |
| G08 | ebios_rm_attack_paths | -- | DROP |

### ISO 27005 -> EBIOS RM

| Gap | ISO field | EBIOS field | Strategy |
|-----|-----------|-------------|----------|
| H01 | smsi_risk_assessments.name | ebios_rm_studies.name | DIRECT |
| H02 | smsi_risk_scenarios.impact (1-5) | ebios_rm_feared_events.severity (1-4) | ADAPT |
| H03 | iso27005_threat_sources | ebios_rm_risk_sources | ADAPT + DERIVE (M/R/A) |
| H04 | iso27005_soa_entries (Annex A) | ebios_rm_security_measures (baseline) | ADAPT (all -> baseline) |
| H05 | ISO prob×impact 5×5 | EBIOS likelihood×severity 4×4 | ADAPT |
| H06 | -- | ebios_rm_stakeholders | MANUAL -- user creates in W2 |
| H07 | -- | ebios_rm_operational_scenarios (W4) | MANUAL |

## Decomposition des sous-taches

Au demarrage, identifier les sous-taches independantes avant toute action :

- [ ] Sous-tache 1 : charger la source (`SELECT` etude EBIOS ou assessment ISO) et verifier son existence
- [ ] Sous-tache 2 : dry-run (`--dry-run`) pour produire le plan + gap analysis sans INSERT
- [ ] Sous-tache 3 : valider le plan avec l'utilisateur (ou continuer en autonomie si `--resume`)
- [ ] Sous-tache 4 : executer les mappings DIRECT/ADAPT/DERIVE (P3 -- transactions par gap)
- [ ] Sous-tache 5 : verifier l'integrite des donnees inserees + compter les gaps resolus (P4)
- [ ] Sous-tache 6 : finaliser le plan (P5 -- git add, impression resumee a l'utilisateur)

Les sous-taches 4 et 5 forment une boucle si `--resume`. La 6 depend de la 5. Les gaps MANUAL et DROP n'entrent pas en 4.

## Adaptation et replanification

Si 2 gaps consecutifs echouent (INSERT rejete + correction qui echoue aussi) :

- STOP
- Invoquer `/replan` -> produit `PLAN_GRC_MIGRATE_*_REPLAN_*.md`
- NE PAS improviser un contournement SQL qui bypasse la validation

Declencheurs typiques :
- Assertion `ON CONFLICT` echoue deux fois sur le meme gap (schema mismatch) -> REPLAN
- Source introuvable en base (`source_id` inexistant) -> REPLAN avec verification UUID
- Dry-run produit un gap MANUAL sur > 50% des lignes -> STOP, consulter l'utilisateur avant live
- Donnees DB-owned menacees d'ecrasement (clobber detecte) -> REPLAN avec sauvegarde prealable

Escalade : si 3 replans sur le meme gap echouent -> STOP, escalader a l'utilisateur avec diagnostic + dump SQL du gap.

## Outils declares

| Outil | Usage | Retry policy |
|-------|-------|--------------|
| `Read`, `Glob` | Lire le plan existant, les references gap-catalogue.md, plan-template.md | N/A |
| `Edit`, `Write` | Mettre a jour le PLAN_GRC_MIGRATE_*.md (flip checkboxes, Status) | N/A |
| `Bash psql_lia` | Lire source, verifier donnees cibles, compter gaps post-INSERT | 1 retry si connexion flaky |
| `Bash scripts/psql_dry_run.sh` | Dry-run de toute migration SQL generee (R27 -- Pattern A obligatoire) | Echec -> diagnose, pas de retry aveugle |
| `TaskCreate` | Tracker si > 10 gaps en cours simultanement | N/A |
| `Skill(sql-pro)` | Si une migration NNN_*.sql doit etre ecrite pour le gap | Obligatoire AVANT ecriture SQL |

Selection dynamique : `Edit` pour flip de checkbox dans le plan (pas réécriture). `Write` uniquement si nouveau fichier plan. `psql_dry_run.sh` AVANT tout INSERT live (R27). Jamais `INSERT` direct sans dry-run prealable.

## Autonomy + gates

- Dry-run is non-destructive; always run once before live.
- Live mode: each INSERT in a transaction per gap; rollback on error, continue to next gap.
- Never overwrite existing target data without `--force` (not implemented in v1).

## Traceability

- Decision log: `_alire/02_LOGS/Journals/decision_log.jsonl` with `action: GRC_MIGRATE_*`

Format :
```json
{"timestamp":"...","session":"grc-migrate-{direction}-{source_id}","action":"GRC_MIGRATE_*","reasoning":"...","alternatives_rejected":["..."],"outcome":"...","confidence":"high","plan_ref":"PLAN_GRC_MIGRATE_*.md"}
```

Logger notamment : choix de strategie sur un gap ADAPT (quand plusieurs mappings possibles), replanifications, gaps droppes et pourquoi.

- UnifiedLogs: `LogSystemEvent("INFO", "GRC_MIGRATE", "{event}", ...)`
- RETEX on MIGRATION FULL: obligatoire si score agentique < 40/50, appender dans `_alire/02_LOGS/Journals/retex/`

---

## VERIFICATION GATE (BLOQUANT)

Avant de declarer une migration FULL ou PARTIAL terminee :

- [ ] Dry-run (`--dry-run`) a passe sans erreur de schema avant le live
- [ ] `scripts/psql_dry_run.sh` a retourne exit 0 sur toute migration SQL generee (R27)
- [ ] Integrite verifiee : COUNT(*) source vs COUNT(*) cible sur les tables principales du gap
- [ ] Aucune donnee DB-owned ecrasee (clobber check : lignes existantes en cible inchangees si `ON CONFLICT DO NOTHING`)
- [ ] Rollback path documente dans le plan (quelle requete DELETE/TRUNCATE inverse le live si besoin)
- [ ] Gaps MANUAL listes clairement avec instruction utilisateur (rien de laisse implicite)

Une migration live sans dry-run prealable = BLOQUANT (R27). Un gap ADAPT non verifie par COUNT = PARTIEL.

---

## Scoring agentique

| Critere | Score |
|---------|-------|
| C1 Decomposition : sous-taches identifiees (dry-run -> gaps -> live -> verify) ? | /10 |
| C2 Planification : PLAN_GRC_MIGRATE_*.md cree en P0, suivi etape par etape ? | /10 |
| C3 Replanification : /replan declenche sur 2+ gaps consecutifs en echec ? | /10 |
| C4 Outillage : psql_dry_run.sh avant live / sql-pro pour migrations / Edit pour flip checkboxes ? | /10 |
| C5 Tracabilite : decision_log alimente (strategies ADAPT, replans) + RETEX si score < 40 ? | /10 |

Score total /50 -- >= 40 : Exemplaire | 30-39 : Acceptable | < 30 : RETEX obligatoire

## Backend endpoint (to be implemented separately)

This skill file is the contract. A backend handler `cmd/sigma_web/grc_migrate_api.go` will expose:

- `POST /api/grc/migrate/ebios-to-iso` body `{source_id, client_id?, dry_run?, resume_plan_path?}`
- `POST /api/grc/migrate/iso-to-ebios` body `{source_id, client_id?, dry_run?, resume_plan_path?}`
- `GET  /api/grc/migrate/plans?client_id=UUID` list active plans + status
- `PATCH /api/grc/migrate/plans/{path}/recheck` re-evaluate gaps (resume)

Frontend surfaces a "Migrate to ISO/EBIOS" button on each study/assessment card with a side panel showing the live checklist.

## Out of scope (v1)

- Automatic control mapping via NLP (ISO Annex A <-> EBIOS baseline measures): MANUAL in v1.
- Evidence file migration: MANUAL (user re-attaches).
- Multi-source merge (combining 2 EBIOS studies into 1 ISO): not supported.
