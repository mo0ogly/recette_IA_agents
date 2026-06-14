# Infrastructure Compliance LIA-SEC -- Reference

## Tables PostgreSQL centrales

### compliance_frameworks (registre central)
```sql
id SERIAL PK, code VARCHAR(50) UNIQUE, name TEXT, description TEXT,
category VARCHAR(50), version VARCHAR(20), icon VARCHAR(50), color VARCHAR(20),
priority INTEGER DEFAULT 50, is_active BOOLEAN, total_questions INTEGER DEFAULT 0,
survey_config JSONB DEFAULT '{}', metadata JSONB DEFAULT '{}'
```

### framework_surveys (questionnaires par framework)
```sql
id SERIAL PK, framework_id INTEGER FK -> compliance_frameworks(id) CASCADE,
title TEXT, part_number INTEGER, total_questions INTEGER DEFAULT 0,
questions JSONB DEFAULT '[]', domains JSONB DEFAULT '[]',
is_active BOOLEAN, version VARCHAR(20)
UNIQUE(framework_id, part_number)
```

### smsi_framework_mappings (correspondances inter-referentiels)
```sql
id UUID PK,
source_framework VARCHAR(50) FK -> compliance_frameworks(code) RESTRICT,
source_control VARCHAR(100),
target_framework VARCHAR(50) FK -> compliance_frameworks(code) RESTRICT,
target_control VARCHAR(100),
mapping_type VARCHAR(20),  -- 'equivalent', 'partial', 'related'
confidence FLOAT DEFAULT 0.8,
source_file VARCHAR(255)
UNIQUE(source_framework, source_control, target_framework, target_control)
```

### smsi_assessments (evaluation d'un framework sur un perimetre)
```sql
id UUID PK, perimeter_id UUID FK, framework_id INTEGER FK,
framework_code VARCHAR(50), status VARCHAR(20),
overall_score FLOAT, maturity_level INTEGER,
score_method VARCHAR(20)  -- 'average', 'weighted', 'max_penalty', 'min_penalty'
```

### smsi_requirement_assessments (evaluation par exigence)
```sql
id UUID PK, assessment_id UUID FK CASCADE,
requirement_ref VARCHAR(100), requirement_title VARCHAR(500),
domain_id VARCHAR(100), assessable BOOLEAN,
workflow_status VARCHAR(20), result_status VARCHAR(30),
score FLOAT, justification TEXT, mapping_inference JSONB
UNIQUE(assessment_id, requirement_ref)
```

## Fichiers et repertoires

### Survey frameworks (JSON)
```
config/survey/frameworks/<CODE>/
  <code>_master_config.json     # Framework ID, Name, Domains[], scoring
  <code>_part<N>.json            # Questions[] avec id, title, control_reference, weight
```

### Mapping files (JSON)
```
config/mappings/
  cis_unified_mappings.json
  iso27001_unified_mappings.json
  nis2_unified_mappings.json
  <nouveau>_unified_mappings.json   # A creer pour chaque nouveau referentiel
```

### Format master_config.json et part_N.json

**NE PAS INVENTER LE FORMAT.** Toujours se baser sur les fichiers existants comme reference :

```
# References a lire AVANT de generer les JSON :
config/survey/frameworks/ISO27001_2022/iso27001_2022_master_config.json    # master_config de reference
config/survey/frameworks/ISO27001_2022/iso27001_2022_part01_context_scope.json  # part de reference
config/survey/frameworks/NIS2_DIRECTIVE/nis2_directive_master_config.json  # autre exemple
config/survey/frameworks/ANNEX_NIS2_REGULATION_2024_2690/master_config.json  # annexe ENISA
```

Champs obligatoires dans chaque question (part_N.json) :
- `id` : identifiant unique (format: `{domain}__{section}__{slug}`)
- `type` : `radio` (standard)
- `required` : `true`
- `title` : texte complet de l'exigence EN
- `section` : nom du domaine
- `control_reference` : ref_id du controle source
- `weight` : poids 1-10
- `weight_justification` : justification du poids
- `implementation_groups` : `["ALL"]` ou groupes specifiques
- `options[]` : 6 niveaux standard (`fully_implemented`, `largely_implemented`, `partially_implemented`, `planned`, `not_implemented`, `not_applicable`)
- `sources[]` : references officielles avec URL
- `preuves_attendues[]` : liste des preuves attendues EN

**270 frameworks existants** dans `config/survey/frameworks/`. Toujours s'aligner sur le format constate, pas sur une documentation externe.

### Format unified_mappings.json
```json
{
  "metadata": {
    "source_framework": "{CODE}",
    "version": "2.5",
    "created_date": "2026-03-21"
  },
  "framework_mappings": [
    {
      "source_control": "1.1",
      "target_frameworks": {
        "ISO_27001": {
          "mappings": [
            {"target_control": "A.5.9", "type": "equivalent", "confidence": 0.9}
          ]
        },
        "NIS2": {
          "mappings": [
            {"target_control": "Art21.2.a", "type": "partial", "confidence": 0.7}
          ]
        }
      }
    }
  ]
}
```

## Code Go a modifier pour un nouveau framework

### 1. framework_loader.go (pkg/compliance/loader/)
```go
// Ajouter dans getFrameworkFilename()
case "{CODE}":
    return "{CODE}"

// Ajouter dans extractFrameworkID()
case "{code}":
    return "{CODE}"

// Ajouter dans normalizeControlRef()
// Pattern: "1.1", "2.A.1", "10.B.5"
case "{CODE}":
    return strings.TrimSpace(ref)

// Ajouter dans buildTagPattern()
case "{CODE}":
    return regexp.MustCompile(`(?i){code}[._-]` + regexp.QuoteMeta(ref))
```

### 2. compliance_score_models.go (cmd/sigma_web/)
```go
// Ajouter dans SupportedFrameworks
var SupportedFrameworks = map[string]FrameworkDefinition{
    // ...existants...
    "{CODE}": {
        Code: "{CODE}",
        Name: "{Framework Name EN}",
        Category: "regulatory",
    },
}
```

### 3. Migration SQL (cmd/sigma_web/migrations/)
```sql
-- Creer 0XX_{code}.sql
INSERT INTO compliance_frameworks (code, name, description, category, version, is_active, priority)
VALUES ('{CODE}', '{Framework Name EN} v2.5', '...', 'regulatory', '2.5', true, 30)
ON CONFLICT (code) DO NOTHING;
```

### 4. smsi_framework_seed.go
Le seed est AUTOMATIQUE : quand un assessment est cree avec `framework_code = '{CODE}'`,
`smsiSeedRequirementsFromFramework()` cree les `smsi_requirement_assessments` depuis
les `framework_surveys.questions` JSONB.

### 5. Import des mappings
```go
// API existante : POST /api/smsi/mappings/import
// -> smsiImportMappingsFromJSON()
// -> INSERT INTO smsi_framework_mappings ... ON CONFLICT DO NOTHING
```

## Format Source YAML (source)

### {code}.yaml (referentiel)
```yaml
urn: urn:framework:risk:library:{code}
locale: fr
ref_id: {CODE}
name: "{CODE} : REFERENTIEL CYBER France - Version 2.5"
objects:
  framework:
    urn: urn:framework:risk:framework:{code}
    implementation_groups_definition:
      - ref_id: EI
        name: Entite Importante
      - ref_id: EE
        name: Entite Essentielle
    requirement_nodes:
      - urn: urn:framework:risk:req_node:{code}:1.1
        assessable: true
        depth: 2
        parent_urn: urn:framework:risk:req_node:{code}:1
        ref_id: '1.1'
        description: "Texte de l'exigence..."
        implementation_groups: [EI, EE]
```

### mapping-*.yaml (mappings)
```yaml
objects:
  requirement_mapping_sets:
    - urn: urn:framework:risk:req_mapping_set:mapping-{code}-and-iso27001-2022
      source_framework_urn: urn:framework:risk:framework:{code}
      target_framework_urn: urn:framework:risk:framework:iso27001-2022
      requirement_mappings:
        - source_requirement_urn: urn:framework:risk:req_node:{code}:1.1
          target_requirement_urn: urn:framework:risk:req_node:iso27001-2022:a.5.9
          relationship: intersect
          strength_of_relationship: 90
```

## Conversion Source YAML -> LIA-SEC

### Mapping des champs

| Source YAML | LIA-SEC Survey JSON |
|---|---|
| `requirement_node.ref_id` | `question.control_reference` |
| `requirement_node.description` | `question.title` |
| `requirement_node.assessable: true` | inclus dans `questions[]` |
| `requirement_node.assessable: false` | devient `section` ou `domain` |
| `requirement_node.depth: 1` | `domain_info` dans `part_N.json` |
| `requirement_node.depth: 2+` | `question` dans `sections[].questions[]` |
| `implementation_groups` | `question.implementation_groups` (champ custom) |

### Mapping des relations

| Source YAML | LIA-SEC smsi_framework_mappings |
|---|---|
| `relationship: intersect` + `strength: 90` | `mapping_type: 'equivalent'`, `confidence: 0.9` |
| `relationship: intersect` + `strength: 50` | `mapping_type: 'partial'`, `confidence: 0.5` |
| `relationship: subset` | `mapping_type: 'partial'`, `confidence: 0.7` |
| `relationship: superset` | `mapping_type: 'related'`, `confidence: 0.6` |
| `relationship: equivalent` | `mapping_type: 'equivalent'`, `confidence: 1.0` |
| `relationship: related` | `mapping_type: 'related'`, `confidence: 0.5` |

### Extraction ref_id depuis URN
```
urn:framework:risk:req_node:{code}:1.1 -> ref_id = "1.1"
urn:framework:risk:req_node:iso27001-2022:a.5.9 -> ref_id = "A.5.9"
urn:framework:risk:req_node:annex-technical-...:12.4.2 -> ref_id = "12.4.2"
```
Pattern: dernier segment apres le dernier `:` du URN.
