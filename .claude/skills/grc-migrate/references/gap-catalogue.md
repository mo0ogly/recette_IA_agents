# Gap Catalogue -- EBIOS RM <-> ISO 27005

Canonical mapping used by `/grc-migrate`. Each gap has a stable ID (Gxx for ebios-to-iso, Hxx for iso-to-ebios).

## Strategies

- **DIRECT**   : 1-1 field copy
- **ADAPT**    : value transformation (scale, enum, unit)
- **DERIVE**   : computed from multiple source fields
- **MANUAL**   : no deterministic mapping; user input required
- **DROP**     : no equivalent in target; safely ignored

## EBIOS RM -> ISO 27005 (direction: ebios-to-iso)

### Identity + scope

| ID | Source | Target | Strategy | Notes |
|----|--------|--------|----------|-------|
| G01 | `ebios_rm_studies.name` | `smsi_risk_assessments.name` | DIRECT | |
| G02 | `ebios_rm_studies.description` | `smsi_risk_assessments.scope` | DIRECT | |
| G03 | `ebios_rm_studies.client_id` | `smsi_risk_assessments.client_id` | DIRECT | |
| G04 | `ebios_rm_studies.created_by` | `smsi_risk_assessments.created_by` | DIRECT | |

### Feared events -> Risk scenarios (impact side)

| ID | Source | Target | Strategy | Notes |
|----|--------|--------|----------|-------|
| G10 | `ebios_rm_feared_events.name` | `smsi_risk_scenarios.name` | DIRECT | |
| G11 | `ebios_rm_feared_events.severity (1-4)` | `smsi_risk_scenarios.impact (1-5)` | ADAPT | `1->1, 2->2, 3->4, 4->5` (skip 3 to keep criticality gap) |
| G12 | `ebios_rm_business_values.name` | `smsi_assets.name` | ADAPT | Upsert per unique business_value |
| G13 | `ebios_rm_supporting_assets.name` | `smsi_assets.name` (type=technical) | ADAPT | |

### Risk sources -> Threat sources

| ID | Source | Target | Strategy | Notes |
|----|--------|--------|----------|-------|
| G20 | `ebios_rm_risk_sources.name` | `iso27005_threat_sources.name` | DIRECT | |
| G21 | `ebios_rm_risk_sources.motivation (1-3) + resources (1-3) + activity (1-3)` | `iso27005_threat_sources.capability,intent,resources` | ADAPT+DERIVE | Project 1-3 scale onto 1-5 via `round(v * 5/3)` |
| G22 | `ebios_rm_risk_sources.category` | `iso27005_threat_sources.source_type` | ADAPT | Enum remap (state_sponsored, hacktivist, insider, ...) |

### Scenarios

| ID | Source | Target | Strategy | Notes |
|----|--------|--------|----------|-------|
| G30 | `ebios_rm_strategic_scenarios.*` | `smsi_risk_scenarios.*` | DIRECT | 1-1 insert with threat_source_id, feared_event_id mapping |
| G31 | `ebios_rm_risk_assessments.likelihood (1-4)` | `smsi_risk_assessments.probability (1-5)` | ADAPT | `1->1, 2->2, 3->4, 4->5` |
| G32 | `ebios_rm_risk_assessments.severity (1-4)` | `smsi_risk_assessments.impact (1-5)` | ADAPT | same as G11 |

### Security measures -> SoA

| ID | Source | Target | Strategy | Notes |
|----|--------|--------|----------|-------|
| G40 | `ebios_rm_security_measures` | `iso27005_soa_entries` | MANUAL | No deterministic Annex A mapping; user picks A.5-A.8.* |
| G41 | `ebios_rm_risk_treatment_plans` | `smsi_action_items` | ADAPT | Extract actions |

### Drops

| ID | Source | Strategy | Reason |
|----|--------|----------|--------|
| G90 | `ebios_rm_stakeholders` | DROP | No ISO equivalent (EBIOS W2 ecosystem) |
| G91 | `ebios_rm_attack_paths` | DROP | ISO 27005 does not model kill chain |
| G92 | `ebios_rm_operational_scenarios` | DROP | EBIOS W4 only |

---

## ISO 27005 -> EBIOS RM (direction: iso-to-ebios)

### Identity + scope

| ID | Source | Target | Strategy | Notes |
|----|--------|--------|----------|-------|
| H01 | `smsi_risk_assessments.name` | `ebios_rm_studies.name` | DIRECT | |
| H02 | `smsi_risk_assessments.scope` | `ebios_rm_studies.description` | DIRECT | |
| H03 | `smsi_risk_assessments.client_id` | `ebios_rm_studies.client_id` | DIRECT | |

### Scenarios -> Feared events + Strategic scenarios

| ID | Source | Target | Strategy | Notes |
|----|--------|--------|----------|-------|
| H10 | `smsi_risk_scenarios.name` | `ebios_rm_strategic_scenarios.name` | DIRECT | |
| H11 | `smsi_risk_scenarios.impact (1-5)` | `ebios_rm_feared_events.severity (1-4)` | ADAPT | `1->1, 2->2, 3->2, 4->3, 5->4` |
| H12 | `smsi_risk_scenarios` (derive business value) | `ebios_rm_business_values` | DERIVE | Cluster by asset |

### Threat sources -> Risk sources

| ID | Source | Target | Strategy | Notes |
|----|--------|--------|----------|-------|
| H20 | `iso27005_threat_sources.name` | `ebios_rm_risk_sources.name` | DIRECT | |
| H21 | `iso27005_threat_sources.capability,intent,resources (1-5 each)` | `ebios_rm_risk_sources.motivation,resources,activity (1-3 each)` | ADAPT | `ceil(v * 3/5)` |
| H22 | `iso27005_threat_sources.source_type` | `ebios_rm_risk_sources.category` | ADAPT | |

### SoA -> Security measures

| ID | Source | Target | Strategy | Notes |
|----|--------|--------|----------|-------|
| H30 | `iso27005_soa_entries` applicable=true | `ebios_rm_security_measures` (type=baseline) | ADAPT | Name = Annex A ref + title |

### Risk assessments

| ID | Source | Target | Strategy | Notes |
|----|--------|--------|----------|-------|
| H40 | `smsi_risk_assessments.probability (1-5)` | `ebios_rm_risk_assessments.likelihood (1-4)` | ADAPT | `1->1, 2->2, 3->2, 4->3, 5->4` |
| H41 | `smsi_risk_assessments.impact (1-5)` | `ebios_rm_risk_assessments.severity (1-4)` | ADAPT | same as H11 |

### Manual (EBIOS-only content to be authored by user)

| ID | Target | Strategy | Reason |
|----|--------|----------|--------|
| H80 | `ebios_rm_stakeholders` (W2) | MANUAL | ISO has no ecosystem |
| H81 | `ebios_rm_attack_paths` (W4) | MANUAL | ISO has no kill chain |
| H82 | `ebios_rm_operational_scenarios` (W4) | MANUAL | |
| H83 | `ebios_rm_roto` (risk source x target objective) | MANUAL | |

---

## Scale projection reference

### 1-4 -> 1-5 (EBIOS to ISO)

| EBIOS (1-4) | ISO (1-5) | Rationale |
|-------------|-----------|-----------|
| 1 | 1 | Low |
| 2 | 2 | Medium |
| 3 | 4 | High (skip 3 to preserve critical gap) |
| 4 | 5 | Critical |

### 1-5 -> 1-4 (ISO to EBIOS)

| ISO (1-5) | EBIOS (1-4) |
|-----------|-------------|
| 1 | 1 |
| 2 | 2 |
| 3 | 2 |
| 4 | 3 |
| 5 | 4 |

### 1-3 -> 1-5 (EBIOS M/R/A to ISO capability)

`iso_value = round(ebios_value * 5 / 3)` -> 1->2, 2->3, 3->5

### 1-5 -> 1-3 (ISO capability to EBIOS M/R/A)

`ebios_value = ceil(iso_value * 3 / 5)` -> 1->1, 2->2, 3->2, 4->3, 5->3
