# Plan de validation - A-S-WFTP-WingFTP-CVE-2025-47812

## Séquence de validation retenue

### Etape 0: Exploration et localisation (pre-flight)

Avant toute validation, vérifier que la règle existe et identifier les fichiers présents.

```bash
ls -la lia_rules/rule_analysis/WFTP/SECU/A-S-WFTP-WingFTP-CVE-2025-47812/
```

Fichiers obligatoires:
- `A-*.yml` (règle YAML)
- `R-*.json` (ReportRule)
- `test_data.json` (données de test)
- `test_rule.sh` (script moteur)

### Etape 1: Test moteur (engine test first)

Raison: Valider en premier que la logique de détection fonctionne avant de lancer les validateurs.
Un moteur qui ne détecte rien rend les autres validations sans intérêt.

```bash
bash lia_rules/rule_analysis/WFTP/SECU/A-S-WFTP-WingFTP-CVE-2025-47812/test_rule.sh
```

Critères de succès:
- Exit code 0
- Matches = 10 (62.5% des 16 cas)
- 0 false positives sur les 6 cas safe

### Etape 2: Validation Recipe (après moteur)

Raison: Valide la qualité de la règle (structure, données de test, references, tags, ratio 60/40).

```bash
cd recette/recette_rule_cli && bash validate_rules_recipe.sh \
  ../../lia_rules/rule_analysis/WFTP/SECU/A-S-WFTP-WingFTP-CVE-2025-47812/
```

Critères: Exit 0 ou 2 (pas de CRITICAL). Score >= 80/100.

### Etape 3: Validation Ultimate (après recipe)

Raison: Valide la conformité YAML (76 checks Bash + 15 checks Python), MOTOR_FIX, sigmarule.go.

```bash
cd recette && bash validate_rules_ultimate.sh \
  ../lia_rules/rule_analysis/WFTP/SECU/A-S-WFTP-WingFTP-CVE-2025-47812/
```

Critères: Exit 0. Score >= 95/100.

### Etape 4: Validation ReportRule (après ultimate)

Raison: Valide la remédiation JSON (syntax, required fields, steps, compliance, alignement YAML).

```bash
cd recette/recette_rule_remediation_cli && \
  bash orchestrators/validate_reportrules_v1.sh \
  ../../lia_rules/rule_analysis/WFTP/SECU/A-S-WFTP-WingFTP-CVE-2025-47812/R-S-WFTP-WingFTP-CVE-2025-47812.json
```

Critères: Exit 0 ou 2. 0 CRITICAL. Score >= 80/115 pts.

### Etape 5: Validation ALL (synthese complete)

Raison: Orchestre les 4 étapes précédentes + RETEX pre-check + exports. Produit le rapport final dans `recette/`.

```bash
cd recette && bash validate_rules_ALL.sh \
  ../lia_rules/rule_analysis/WFTP/SECU/A-S-WFTP-WingFTP-CVE-2025-47812/
```

Critères: 0 CRITICAL. Score global >= 90/100 pour commit autorisé.

## Résultats obtenus

| Etape | Outil | Checks | Score | Exit |
|-------|-------|--------|-------|------|
| 1 - Moteur | test_rule.sh | 16 events | 10/10 PASS | 0 |
| 2 - Recipe | validate_rules_recipe.sh | 43 | 83/100 | 2 |
| 3 - Ultimate | validate_rules_ultimate.sh | 91 | 98/100 | 0 |
| 4 - ReportRule | validate_reportrules_v1.sh | 11 | 87/115 pts | 2 |
| 5 - ALL | validate_rules_ALL.sh | 164 | 92/100 | 2 |

## Issues détectées (non bloquantes pour prod, à corriger)

### HIGH - Recipe
- `RESEARCH_EVIDENCE.md` manquant (preuve données test_data réelles)
- `required_fields` non documentés dans data_source
- `data_source.description` format V1 (migration V2 recommandée)

### HIGH - ReportRule
- `compliance_mapping` format: nist_csf/iso_27001/pci_dss/anssi contiennent des strings au lieu d'objets JSON
  ```json
  // Actuel (incorrect)
  "nist_csf": ["ID.RA-1", "PR.IP-12", "DE.CM-8"]

  // Attendu (correct)
  "nist_csf": [{"id": "ID.RA-1", "name": "..."}, ...]
  ```
- Titre YAML vs JSON: tiret manquant dans le JSON title
- `vulnerability.rationale` absent

### MEDIUM (non bloquants)
- `example.com` dans hostnames test_data (domaines fictifs)
- Champs CVE optionnels absents: `epss_score`, `kev_date_added`, `exploit_counts`
- Compliance IDs format PCI DSS: `6.3.3` au lieu de `Req-6.3.3`
