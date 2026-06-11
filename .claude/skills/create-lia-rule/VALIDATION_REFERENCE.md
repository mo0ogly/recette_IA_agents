# Reference Rapide - Validation LIA-Scan

## Commandes de Validation

```bash
cd /home/mo0ogly/Bureau/vscode_lia_audit/recette

# Validation COMPLETE (128 checks) - Recommande
./validate_rules_ALL.sh ../lia_rules/rule_analysis/{TECH}/{AXIS}/{BLOCKSHORT}/A-RULE-NAME/

# Validation Recipe (41 checks - donnees reelles)
./validate_rules_recipe.sh ../lia_rules/rule_analysis/{TECH}/{AXIS}/{BLOCKSHORT}/A-RULE-NAME/

# Validation Ultimate (91 checks - YAML compliance)
./validate_rules_ultimate.sh ../lia_rules/rule_analysis/{TECH}/{AXIS}/{BLOCKSHORT}/A-RULE-NAME/

# Validation ReportRule (8 checks - JSON remediation)
./validate_reportrules.sh ../lia_rules/rule_analysis/{TECH}/{AXIS}/{BLOCKSHORT}/A-RULE-NAME/R-*.json
```

## Exit Codes

| Code | Niveau | Action |
|------|--------|--------|
| 0 | PASS | Commit autorise |
| 1 | CRITICAL | FIX OBLIGATOIRE |
| 2 | HIGH | Review recommandee (commit acceptable) |
| 3 | MEDIUM | Corrections optionnelles |

## Test Moteur

```bash
# Dans le repertoire de la regle
chmod +x test_rule.sh
./test_rule.sh

# Ou manuellement
ENGINE="/home/mo0ogly/Bureau/vscode_lia_audit/bin/lia_scan_engine"
$ENGINE -multi \
  -rules . \
  -events test_data.json \
  -quadrigramme TEST \
  -date $(date +%Y%m%d)
```

## Erreurs Frequentes et Corrections

### 1. output.include -> output.fields (FORMAT V2)
```yaml
# AVANT (ancien format)
output:
  include:
    - Hostname

# APRES (FORMAT V2)
output:
  fields:
    Hostname: Hostname
```

### 2. Compliance mapping uppercase
```yaml
# ERREUR
compliance_mapping:
  ANSSI:
  PCI_DSS:

# CORRECT
compliance_mapping:
  anssi:
  pci_dss:
```

### 3. Computed field string statique sans if()
```yaml
# ERREUR - provoque ERROR moteur
Impact: "Remote code execution"

# CORRECT
Impact: "if(Version != '', 'Remote code execution', 'Unknown')"
```

### 4. Version comparison sans 3 segments
```yaml
# ERREUR
- Version: {version_lt: "16.10"}

# CORRECT
- Version: {version_lt: "16.10.0"}
```

### 5. Renommage output fields
```yaml
# ERREUR - peut donner null
output:
  fields:
    Server_Name: Hostname

# CORRECT
output:
  fields:
    Hostname: Hostname
```

### 6. taxonomy manquant technology/category
```yaml
# ERREUR
taxonomy:
  taxonomy: DOCKER
  taxonomy_short: DOCK

# CORRECT
taxonomy:
  taxonomy: DOCKER
  taxonomy_short: DOCK
  technology: "Docker Engine"
  category: "Container Security"
```

### 7. metadata.date manquant
```yaml
# ERREUR - pas de metadata
id: A-VULN-XXX

# CORRECT
metadata:
  author: "LIA-Scan Rules Team"
  date: "2026-02-15"
  version: "1.0"
```

### 8. MOTOR_FIX_010 violation
```yaml
# VIOLATION - logique cachee
where:
  rules:
    - is_compliant: {eq: false}
    - CVE_2025_1234_is_vulnerable: {eq: true}

# CONFORME - logique auditable
where:
  condition: and
  rules:
    - version_lt(Version, "12.8.0.0"): {eq: true}
```

## Phases de Validation Recipe (41 checks)

| Phase | Description | Points |
|-------|-------------|--------|
| 1 | Fichiers obligatoires | CRITICAL |
| 2 | data_source documentee | HIGH |
| 3 | Script de collecte | HIGH |
| 4 | Qualite donnees test | HIGH |
| 5 | Execution moteur | CRITICAL |
| 6 | Faux positifs/negatifs | HIGH |
| 7 | Computed fields | HIGH |
| 8 | References | MEDIUM |
| 9 | Tags | MEDIUM |
| 10 | Match Sigma | INFO |
| 11 | CVE Metadata | CVE only |
| 12 | Test data ratio | MEDIUM |
| 13 | Compliance mapping | HIGH |
| 14 | Taxonomy coherence | CRITICAL |

## Phases Validation Ultimate (91 checks)

- Bash V6: 76 checks (format, champs, MOTOR_FIX, compliance)
- Python V5: 15 checks (moteur, operators, functions)

## Phases Validation ReportRule (8 checks)

| Phase | Points | Description |
|-------|--------|-------------|
| 1 CRITICAL | 65 | JSON syntax + champs requis + remediation |
| 2 HIGH | 25 | Compliance + references |
| 3 MEDIUM | 10 | Metadata + coherence |
| 4 CROSS | 15 | Coherence YAML <-> JSON |

## Debug

```bash
# Verbose mode
VERBOSE=1 ./validate_rules_recipe.sh /path/to/rule/

# YAML syntax check
python3 -c "import yaml; yaml.safe_load(open('rule.yml'))"

# JSON syntax check
python3 -m json.tool test_data.json > /dev/null
python3 -m json.tool R-*.json > /dev/null
```

## Scoring

- >= 95%: Excellent (production ready)
- 85-94%: Bon (acceptable)
- 70-84%: Moyen (review necessaire)
- < 70%: Mauvais (refonte)

Seuil pre-commit hook: 85% minimum
