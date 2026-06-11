---
name: guided-risk-assessment
description: |
  Guide users through a complete risk assessment in the LIA-SEC SMSI / ISO 27005 / EBIOS RM module, from perimeter and asset identification to scenario creation and treatment. Use when:
  (1) User wants to start a risk assessment from scratch
  (2) User mentions "risk assessment", "analyse de risque", "scenarios de risque", "risk register", "appreciation des risques", "ISO 27005", "EBIOS RM"
  (3) User asks how to identify assets, threats, vulnerabilities, or build risk scenarios
  (4) User needs help choosing between the ISO 27005 qualitative approach and EBIOS RM

  Covers: methodology selection (ISO 27005 qualitative vs EBIOS RM), organizational context gathering, perimeter creation, primary/support asset identification, threat-vulnerability cataloguing, data-driven scenario scoring via TruRisk (CVSS+EPSS+KEV+exploits), risk matrix selection, inherent/current/residual risk levels, treatment and risk acceptance.

  This is a guided workflow over the LIA-SEC SMSI backend. It does NOT replace /spec-builder (new module design) or /import-framework (compliance questionnaire import).
---

# Guided Risk Assessment (LIA-SEC SMSI / ISO 27005 / EBIOS RM)

Guide users through a structured risk assessment using the LIA-SEC SMSI module:
real PostgreSQL-backed perimeters, assets, threats, and risk scenarios scored
against a configurable risk matrix and enriched with TruRisk CVE intelligence.

## Where this lives in LIA-SEC

- **UI**: Compliance & GRC > Risk (`SmsiRiskManager.tsx`, `RiskScenarioDialog.tsx`,
  `RiskAcceptanceDialog.tsx`, `UnifiedRiskDashboard.tsx`).
- **Backend**: `cmd/sigma_web/smsi_risk_api.go`, `smsi_risk_db.go`,
  `smsi_asset_api.go`, `iso27005_*.go`, `ebios_rm_v2_risk.go`.
- **Types**: `pkg/compliance/types/smsi_types.go`
  (`SmsiPerimeter`, `SmsiAsset`, `SmsiRiskAssessment`, `SmsiRiskScenario`, `SmsiRiskMatrix`).
- **Tables**: `smsi_perimeters`, `smsi_assets`, `smsi_asset_classes`,
  `smsi_risk_matrices`, `smsi_risk_assessments`, `smsi_risk_scenarios`,
  `iso27005_threats`, `iso27005_vulnerabilities`.

The ISO 27005 and EBIOS RM systems share the `smsi_risk_*` tables. The
`methodology` field on `smsi_risk_assessments` distinguishes `iso27005` from
`ebios_rm` (EBIOS RM additionally links an `ebios_study_id`).

## Prerequisites

1. **Backend reachable** -- `GET /api/health` returns `{"status":"ok"}`.
2. **Authenticated session** -- all `/api/smsi/*` routes are JWT-protected
   (deny-by-default middleware). In the UI, `fetchWithConfig` injects the
   Bearer token. For API automation, export `LIA_API_TOKEN` and send
   `Authorization: Bearer $LIA_API_TOKEN` (never hardcode the token -- R8).
3. **A risk matrix exists** -- `GET /api/smsi/risk-matrices` must return at
   least one matrix (a default 5x5 is seeded by migration). The matrix UUID
   drives automatic risk-level computation.

---

## Key Principles

### Always scope to a perimeter

Every asset and assessment belongs to a perimeter (`perimeter_id`). Create the
perimeter first; pass its UUID to every downstream object so lookups stay
unambiguous when multiple clients or scopes coexist.

### Risk levels are computed, not entered

Do NOT invent a risk-level string. Submit `*_probability` + `*_impact`
integers; the backend (`smsiRiskCalculateLevel`) resolves the level from the
assessment's risk matrix. Three layers exist:

| Layer | Fields | Meaning |
|-------|--------|---------|
| Inherent | `inherent_probability`, `inherent_impact` | Risk before any control |
| Current | `current_probability`, `current_impact` | Risk with controls in place today |
| Residual | `residual_probability`, `residual_impact` | Risk after planned treatment |

### Prefer data-driven scoring over guesswork (TruRisk)

When a scenario maps to known CVEs, do NOT hand-wave probability/impact. Link
the CVEs (`linked_cve_ids`) and call the TruRisk suggestion endpoint, which
derives a suggested probability/impact from CVSS + EPSS + CISA KEV + exploit
maturity. This is the LIA-SEC differentiator over a static relevance table.

```
POST /api/grc/iso27005/scenarios/{id}/suggest-risk
```

### Explain relevance in every scenario description

State why the scenario matters for THIS organization (regulation, business
value, exposure). Example:

```
"Ransomware encrypting the production customer database, causing service
outage. Relevance: GDPR personal-data breach (72h notification, fines up to
4% of annual revenue); customer database rated C5/I5/A5."
```

---

## Workflow

### Step 1 -- Choose the methodology

Ask which methodology the user wants. LIA-SEC supports two qualitative methods
sharing the same risk store:

| Methodology | `methodology` value | Best for |
|-------------|---------------------|----------|
| **ISO 27005 (qualitative)** | `iso27005` | Standard ISMS risk register, probability x impact on a matrix, control linkage |
| **EBIOS RM** | `ebios_rm` | French ANSSI method: strategic/operational scenarios, feared events, stakeholder ecosystem (drives an `ebios_study_id`) |

There is no Monte-Carlo quantitative mode in LIA-SEC; quantitative depth comes
from TruRisk CVE scoring feeding the qualitative probability/impact.

### Step 2 -- Gather organizational context

Ask about:
- **Industry**: healthcare, financial, tech/SaaS, retail, manufacturing, public sector
- **Size**: small (1-50), medium (50-500), large (500+)
- **Region / regulation**: EU -> GDPR, FR -> ANSSI/NIS2, health -> HDS/HIPAA, payments -> PCI-DSS
- **Hosting**: cloud (AWS/Azure/GCP), SaaS-heavy, on-premise, hybrid
- **Frameworks in scope**: ISO 27001, NIS2, ANSSI guides, SecNumCloud

Use [references/typical-assets.md](references/typical-assets.md) to suggest
assets and threat families from this context.

### Step 3 -- Create the perimeter

```bash
curl -sS -X POST "$LIA_BASE/api/smsi/perimeters" -H "Authorization: Bearer $LIA_API_TOKEN" -H "Content-Type: application/json" -d '{"name":"ACME Platform","description":"ACME Corp - Tech/SaaS, EU-based","perimeter_type":"organization","client_id":"ACME"}'
```

Capture the returned `id` (perimeter UUID) for the next steps.

### Step 4 -- Identify and create assets

Use [references/typical-assets.md](references/typical-assets.md) to propose
assets when the user is unsure.

| Asset type (`asset_type`) | Meaning | Examples |
|---------------------------|---------|----------|
| `primary` | Business value (data, processes) | Customer data, financial records, source code, API secrets |
| `support` | Infrastructure supporting primary assets | Production database, cloud infra, CI/CD pipeline, endpoints, email |

CIA ratings are integers 1-5 (`confidentiality_level`, `integrity_level`,
`availability_level`). `business_value` is `low|medium|high`; `sensitivity`
e.g. `public|internal|confidential|restricted`. Optional `asset_class_id` from
`GET /api/smsi/asset-classes`.

```bash
curl -sS -X POST "$LIA_BASE/api/smsi/assets" -H "Authorization: Bearer $LIA_API_TOKEN" -H "Content-Type: application/json" -d '{"name":"Customer Database","description":"Customer PII - GDPR relevant","asset_type":"primary","business_value":"high","sensitivity":"confidential","confidentiality_level":5,"integrity_level":5,"availability_level":4,"perimeter_id":"<PERIMETER_UUID>","owner":"DPO"}'
```

### Step 5 -- Review the threat / vulnerability catalogue

LIA-SEC ships ISO 27005 threat and vulnerability catalogues:

```bash
psql_lia -c "SELECT id, ref_id, name FROM iso27005_threats ORDER BY ref_id;"
psql_lia -c "SELECT id, name, linked_cve_id FROM iso27005_vulnerabilities WHERE linked_cve_id IS NOT NULL;"
```

Vulnerabilities can carry a `linked_cve_id`, which is the bridge to TruRisk
scoring in Step 6/8. See [references/typical-assets.md](references/typical-assets.md)
for the threat-family-to-asset relevance guidance.

### Step 6 -- Select the risk matrix

```bash
curl -sS "$LIA_BASE/api/smsi/risk-matrices" -H "Authorization: Bearer $LIA_API_TOKEN"
```

Pick the matrix UUID (default is a 5x5). It governs how probability x impact
maps to a level for every scenario in the assessment.

### Step 7 -- Create the assessment container

```bash
curl -sS -X POST "$LIA_BASE/api/smsi/risk-assessments" -H "Authorization: Bearer $LIA_API_TOKEN" -H "Content-Type: application/json" -d '{"perimeter_id":"<PERIMETER_UUID>","title":"ACME Risk Assessment 2026","methodology":"iso27005","risk_matrix_id":"<MATRIX_UUID>","status":"in_progress","assessed_by":"RSSI"}'
```

For EBIOS RM, set `"methodology":"ebios_rm"` and link the EBIOS study via the
EBIOS RM workshops flow (`ebios_rm_v2_risk.go`); the study UUID populates
`ebios_study_id`.

### Step 8 -- Build risk scenarios

Naming convention: `[Threat] on [Asset]` ("Ransomware on Customer Database",
"Phishing targeting Finance Team", "Cloud Misconfiguration on Production Infra").

Submit threat, vulnerability, asset and the probability/impact integers. The
backend computes `*_risk_level` from the matrix.

```bash
curl -sS -X POST "$LIA_BASE/api/smsi/risk-scenarios" -H "Authorization: Bearer $LIA_API_TOKEN" -H "Content-Type: application/json" -d '{"risk_assessment_id":"<ASSESSMENT_UUID>","title":"Ransomware on Customer Database","description":"Ransomware encrypts the customer DB. Relevance: GDPR breach, 72h notification.","threat":"Ransomware","vulnerability":"Unpatched RDP exposed to internet","asset":"Customer Database","inherent_probability":4,"inherent_impact":5,"current_probability":3,"current_impact":5,"treatment":"reduce","residual_probability":2,"residual_impact":4,"strength_of_knowledge":2,"risk_owner":"CISO","status":"open","linked_cve_ids":["CVE-2019-0708"]}'
```

When `linked_cve_ids` is set, ask TruRisk for a data-driven probability/impact
suggestion instead of guessing:

```bash
curl -sS -X POST "$LIA_BASE/api/grc/iso27005/scenarios/<SCENARIO_UUID>/suggest-risk" -H "Authorization: Bearer $LIA_API_TOKEN"
```

Optionally link the scenario back to the asset for the asset-coverage view:

```bash
curl -sS -X POST "$LIA_BASE/api/smsi/assets/<ASSET_UUID>/link-scenario" -H "Authorization: Bearer $LIA_API_TOKEN" -H "Content-Type: application/json" -d '{"scenario_id":"<SCENARIO_UUID>"}'
```

### Step 9 -- Treat, accept, and review

1. **Rate** every scenario (inherent -> current -> residual) -- done in Step 8 or in the UI dialog.
2. **Link controls / requirements** via `linked_requirements` on the scenario.
3. **Treatment** field: `reduce | accept | avoid | transfer` (ISO 27005 options).
4. **Formal risk acceptance** for residual risk the org tolerates:
   ```bash
   curl -sS -X POST "$LIA_BASE/api/smsi/risk-scenarios/<SCENARIO_UUID>/accept" -H "Authorization: Bearer $LIA_API_TOKEN" -H "Content-Type: application/json" -d '{"accepted_by":"CISO","justification":"Residual risk within appetite"}'
   ```
5. **Visualize** the register heatmap:
   ```bash
   curl -sS "$LIA_BASE/api/smsi/risk-scenarios/heatmap" -H "Authorization: Bearer $LIA_API_TOKEN"
   ```
6. **AI synthesis** (executive summary, treatment roadmap) is available through
   the SMSI AI endpoints (`SmsiAIService.ts` -> `smsi_ai_api.go`), which run on
   the canonical `ExecuteWithRAG` path (R22).

---

## Quick Reference -- LIA-SEC API

| Step | Method + Route | Key fields |
|------|----------------|------------|
| Perimeter | `POST /api/smsi/perimeters` | name, description, perimeter_type, client_id |
| Asset | `POST /api/smsi/assets` | name, asset_type (`primary`/`support`), business_value, sensitivity, confidentiality_level, integrity_level, availability_level, perimeter_id, owner |
| Asset classes | `GET /api/smsi/asset-classes` | - |
| Risk matrices | `GET /api/smsi/risk-matrices` | (pick UUID) |
| Assessment | `POST /api/smsi/risk-assessments` | perimeter_id, title, methodology (`iso27005`/`ebios_rm`), risk_matrix_id, status, assessed_by |
| Scenario | `POST /api/smsi/risk-scenarios` | risk_assessment_id, title, description, threat, vulnerability, asset, inherent/current/residual probability+impact, treatment, strength_of_knowledge, risk_owner, status, linked_cve_ids, linked_requirements |
| TruRisk suggest | `POST /api/grc/iso27005/scenarios/{id}/suggest-risk` | (uses linked CVEs) |
| Link scenario to asset | `POST /api/smsi/assets/{id}/link-scenario` | scenario_id |
| Accept risk | `POST /api/smsi/risk-scenarios/{id}/accept` | accepted_by, justification |
| Heatmap | `GET /api/smsi/risk-scenarios/heatmap` | - |
| List scenarios | `GET /api/smsi/risk-assessments/{id}/scenarios` | - |

Set `LIA_BASE` to `http://localhost:8081` (local) or `https://liascan.tech`
(prod). Export `LIA_API_TOKEN` from an authenticated session -- never hardcode.

---

## When to invoke / when NOT

Invoke when the user wants to BUILD or POPULATE a risk assessment (assets,
scenarios, treatment) in the SMSI module.

Do NOT invoke for:
- Designing a brand-new module or schema -> `/spec-builder`.
- Importing a compliance questionnaire framework -> `/import-framework`.
- Pure CVE triage without an ISMS context -> CVE Explorer / TruRisk UI.
- Frontend component work on the risk screens -> `/react-expert` + R17 gate.

## Anti-patterns (forbidden)

- Hardcoding a `*_risk_level` string instead of submitting probability/impact.
- Inventing threat/vulnerability records -- read `iso27005_threats` /
  `iso27005_vulnerabilities`, or create them through the catalogue, never mock (R4).
- Guessing probability/impact for a CVE-backed scenario instead of calling the
  TruRisk suggestion endpoint.
- Embedding the JWT in examples or committing it (R8).
- Backslash line-continuation in copy-paste curl commands (R24): keep each
  command on one line.

## Decomposition des sous-taches

Au demarrage, identifier les sous-taches independantes avant toute action :

- [ ] Sous-tache 1 : recueillir le contexte organisationnel (industrie, taille, region, cadres reglementaires)
- [ ] Sous-tache 2 : choisir la methodologie (`iso27005` ou `ebios_rm`) et verifier la matrice de risque
- [ ] Sous-tache 3 : creer le perimetre + identifier les actifs primaires et supports
- [ ] Sous-tache 4 : passer en revue le catalogue menaces/vulnerabilites (`iso27005_threats`, `iso27005_vulnerabilities`)
- [ ] Sous-tache 5 : construire les scenarios de risque (inherent -> current -> residual) avec TruRisk si CVE lies
- [ ] Sous-tache 6 : traitement, acceptation, heatmap + synthese AI optionnelle

Les sous-taches 3 a 5 peuvent etre iterees. La 6 depend de la 5. Utiliser `TaskCreate` si > 5 scenarios a creer en parallele.

## Plan d'execution

Pour toute session d'appreciation des risques (> 3 scenarios ou nouveau perimetre) :

1. Creer `_alire/tracking/PLAN_RISK_ASSESSMENT_{CLIENT}_{YYYY-MM-DD}.md` avant tout INSERT en base.
2. Template : `_alire/tracking/PLAN_TEMPLATE.md`.
3. Noter les UUID crees (perimetre, assessment, scenarios) dans le plan pour reproductibilite.
4. Cocher chaque sous-tache a la completion.
5. Si replanification : Status -> REPLANIFIE + lien vers nouveau plan.

Pour une session courte (1-2 scenarios, perimetre existant) : plan inline suffit avec UUIDs notes.

## Adaptation et replanification

Si 2 etapes consecutives echouent (ex: POST /api/smsi/risk-assessments retourne 4xx + POST scenario echoue) :

- STOP
- Invoquer `/replan` -> produit `PLAN_RISK_ASSESSMENT_*_REPLAN_*.md`
- NE PAS inventer des valeurs de remplacement ni contourner la validation backend

Declencheurs typiques :
- Matrice de risque absente en base (`GET /api/smsi/risk-matrices` = vide) -> REPLAN pour migration seed
- `suggest-risk` retourne une erreur (CVE non resolue en TruRisk) -> REPLAN avec scoring manuel documente
- Assertion d'integration methodologie/UUID echoue deux fois de suite -> REPLAN

Escalade : si 3 replans sur la meme etape echouent -> STOP, escalader a l'utilisateur avec diagnostic.

## Outils declares

| Outil | Usage | Retry policy |
|-------|-------|--------------|
| `Read`, `Glob`, `Grep` | Explorer smsi_risk_*.go, iso27005_*.go, types existants | N/A |
| `Bash psql_lia` | Lire catalogue menaces/vulnerabilites, verifier UUID en base | 1 retry si connexion flaky |
| `Bash curl` | Appels API REST (POST perimetre, asset, scenario, accept, heatmap) | 1 retry sur 5xx ; 4xx = analyser |
| `Write` | Generer un fichier de plan ou un rapport de session | N/A |
| `TaskCreate` | Tracker si > 5 scenarios a creer en parallele | N/A |
| `Skill(react-expert)` | Si modification de composant React risk screens requise | Invoquer AVANT ecriture .tsx |

Selection dynamique : `psql_lia` pour lire le catalogue (lecture seule). `curl` pour tout INSERT/POST (jamais INSERT direct SQL sur les tables smsi_risk_* depuis le skill -- passer par l'API). `Bash` uniquement, jamais `fmt.Println` ou `console.log`.

## Tracabilite agentique

### Decision log

Logger dans `_alire/02_LOGS/Journals/decision_log.jsonl` pour toute decision non-triviale :
- Choix de methodologie (`iso27005` vs `ebios_rm`) et justification
- Selection de la matrice de risque (UUID, dimensions choisies)
- Rejet d'un score TruRisk au profit d'un scoring manuel (et raison)
- Replanifications declenchees

Format :
```json
{"timestamp":"...","session":"risk-assessment-{client}","action":"...","reasoning":"...","alternatives_rejected":["..."],"outcome":"...","confidence":"high","plan_ref":"PLAN_RISK_ASSESSMENT_*.md"}
```

### Persistance des UUIDs

Tous les UUID crees (perimetre, assessment, scenarios) DOIVENT etre notes dans le fichier de plan pour reproductibilite inter-sessions. Un scenario sans UUID trace dans le plan n'est pas traçable.

RETEX en fin de session si score agentique < 40/50 -> `_alire/02_LOGS/Journals/retex/RETEX_RISK_ASSESSMENT_YYYY-MM-DD.md`.

---

## VERIFICATION GATE (BLOQUANT)

Avant de declarer une session d'appreciation des risques terminee :

- [ ] Tous les scenarios ont un `*_risk_level` calcule (non null) -- verifie via `GET /api/smsi/risk-assessments/{id}/scenarios`
- [ ] La methodologie est coherente (`methodology` = `iso27005` ou `ebios_rm` -- pas de melange dans un meme assessment)
- [ ] Chaque scenario avec `linked_cve_ids` a beneficie d'un appel TruRisk `suggest-risk` (ou justification manuelle documentee)
- [ ] Les actifs sont traces vers au moins un scenario (`link-scenario` appele)
- [ ] Aucun UUID invente ou mock (R4) -- tous les UUIDs proviennent de reponses API reelles
- [ ] Les UUIDs cles (perimetre, assessment, scenarios principaux) sont notes dans le plan

Un scenario sans `*_risk_level` = assessment INCOMPLET. Une methodologie incoherente = REPLAN obligatoire.

---

## Scoring agentique

| Critere | Score |
|---------|-------|
| C1 Decomposition : sous-taches identifiees (contexte -> perimetre -> actifs -> scenarios -> traitement) ? | /10 |
| C2 Planification : PLAN_RISK_ASSESSMENT_*.md cree avec UUIDs traces ? | /10 |
| C3 Replanification : /replan declenche sur 2+ echecs API ou incoherence methodologie ? | /10 |
| C4 Outillage : psql_lia pour lecture / curl pour INSERT / pas de SQL direct sur smsi_risk_* ? | /10 |
| C5 Tracabilite : decision_log alimente (methodologie, matrice) + RETEX si score < 40 ? | /10 |

Score total /50 -- >= 40 : Exemplaire | 30-39 : Acceptable | < 30 : RETEX obligatoire
