# Plan de Validation - A-S-WFTP-WingFTP-CVE-2025-47812
## Ordre obligatoire: moteur -> recipe -> ultimate -> reportrule

---

## Variables

```bash
BASE="/home/mo0ogly/Bureau/vscode_lia_audit"
RULE_DIR="$BASE/lia_rules/rule_analysis/WFTP/SECU/A-S-WFTP-WingFTP-CVE-2025-47812"
RECETTE_DIR="$BASE/recette"
```

---

## Etape 1 - Test Moteur (OBLIGATOIRE EN PREMIER)

```bash
cd "$RULE_DIR"
chmod +x test_rule.sh
./test_rule.sh
```

**Ce que ca teste:**
- Chargement du YAML par le moteur LIA-Scan
- Evaluation de `version_lt(VersionNormalized, "7.4.4.0")` sur 16 objets
- Comparaison avec `_expected_match` de chaque cas dans test_data.json
- Génération des outputs dans `analyse/`

**Résultat attendu:**
- Exit code: 0
- Matches: 10 (versions < 7.4.4: 7.4.3, 7.4.2, 7.4.0, 7.3.9, 7.3.0, 7.2.5, 7.0.0, 6.2.8, 7.4.1+anon, null)
- Safe: 6 (7.4.4 exact, 7.4.5, 7.5.0, 8.0.0, OtherFTPServer, macOS 7.4.4)

**Résultat réel (exécution 2026-03-02):**
- Exit code: **0** - PASS
- Matches: **10/16** - conforme
- Structured matches: 10 | Classic matches: 0
- Duration: 0.01s

---

## Etape 2 - Recipe Validation (41 checks)

```bash
cd "$RECETTE_DIR"
bash recette_rule_cli/validate_rules_recipe.sh "$RULE_DIR"
```

**Ce que ca valide (phases 1-17):**
- Phase 1: Fichiers obligatoires (yml, test_data, test_rule)
- Phase 2: data_source documentée
- Phase 3: Script de collecte existe
- Phase 4: Qualité données de test (16 cas, pas de mock, RESEARCH_EVIDENCE.md)
- Phase 5: Moteur s'exécute
- Phase 6: Ratio faux positifs/negatifs
- Phase 7: 5 computed fields obligatoires
- Phase 8: Références NVD/CISA/ATT&CK
- Phase 9: Tags
- Phase 10: Section match ObjectClass
- Phase 11: Metadata CVE (cve_id, cvss, is_kev)
- Phase 12: Ratio 60/40 test data
- Phase 13: Compliance mapping
- Phase 14: Taxonomie cohérente (WFTP/SECU)
- Phase 17: test_rule.sh valide

**Résultat réel (exécution 2026-03-02):**
- Exit code: **2** (HIGH warnings - pas CRITICAL)
- Score: 83/100
- CRITICAL: 0
- HIGH: 3 (required_fields, RESEARCH_EVIDENCE.md, domaines fictifs)
- MEDIUM: 11

**Commit autorisé si exit <= 2?** NON - HIGH warnings doivent être corrigés selon les instructions projet.

---

## Etape 3 - Ultimate Validation (91 checks)

```bash
# Note: set -euo pipefail dans le script, ne pas utiliser de pipe
"$RECETTE_DIR/validate_rules_ultimate.sh" "$RULE_DIR" > /tmp/ultimate_out.txt 2>&1
echo "Exit: $?"
cat /tmp/ultimate_out.txt | strings | tail -40
```

**Ce que ca valide:**
- V6 Bash (76 checks): format YAML, MOTOR_FIX_003/010, compliance format, sigmarule structure, checklist 14 commandements
- V5 Python (15 validators): yaml_syntax, basic_fields, format_v2, motor_fix_010, operators_functions, version_operators, computed_fields, output_format, compliance_mapping, references, taxonomy_coherence, taxonomy_pollution, cross_references, test_infrastructure, rule_descriptions

**Résultat réel (exécution 2026-03-02):**
- Exit code: **0** - ALL PASS
- V6 Bash: 76/76 - Score 98.7%
- V5 Python: 15/15
- CRITICAL: 0 | HIGH: 0 | MEDIUM: 0
- ULTIMATE Score: **98/100**

**Commit autorisé?** Oui (exit=0)

---

## Etape 4 - ReportRule Validation (R-S-WFTP-WingFTP-CVE-2025-47812.json)

```bash
REPORTRULE=$(find "$RULE_DIR" -maxdepth 1 -name "R-*.json" -type f | head -1)
if [ -n "$REPORTRULE" ]; then
    cd "$RECETTE_DIR"
    ./recette_rule_remediation_cli/orchestrators/validate_reportrules_v1.sh "$RULE_DIR"
fi

# Alternative: exécution directe des validators Python
VALIDATORS="$RECETTE_DIR/recette_rule_remediation_cli/validators"
for v in "$VALIDATORS"/*.py; do
    python3 "$v" "$REPORTRULE" 2>&1
done
```

**Ce que ca valide (9 checks):**
1. validate_json_syntax: JSON parseable
2. validate_required_fields: Champs obligatoires présents
3. validate_references: URLs valides et pertinentes
4. validate_remediation_steps: Etapes de remédiation structurées
5. validate_compliance_mapping: Frameworks en format objet {id, name, description}
6. validate_cve_metadata: vulnerability.cve_id présent
7. validate_metadata: Technology dans la taxonomie
8. validate_severity_coherence: risk_level présent
9. validate_vulnerability: vulnerability.rationale présent

**Résultat réel (exécution 2026-03-02):**
- validate_json_syntax: PASS
- validate_required_fields: PASS
- validate_references: PASS
- validate_remediation_steps: PASS
- validate_compliance_mapping: **FAIL (CRITICAL)** - 10 erreurs format objet
- validate_cve_metadata: **FAIL (CRITICAL)** - vulnerability.cve_id manquant
- validate_metadata: FAIL (MEDIUM) - technology non reconnue
- validate_severity_coherence: FAIL (HIGH) - risk_level absent
- validate_vulnerability: FAIL (HIGH) - vulnerability.rationale manquant

**Summary: 4 passed, 5 failed**
**Commit autorisé?** NON (2 CRITICAL)

---

## Résumé Exécution

| Etape | Commande | Exit | Verdict |
|-------|---------|------|---------|
| 1. Moteur | `./test_rule.sh` | 0 | PASS |
| 2. Recipe | `bash validate_rules_recipe.sh "$RULE_DIR"` | 2 | HIGH - corriger |
| 3. Ultimate | `./validate_rules_ultimate.sh "$RULE_DIR"` | 0 | ALL PASS |
| 4. ReportRule | `python3 validators/*.py "$RR_FILE"` | 1 | CRITICAL - blocker |

**COMMIT AUTORISÉ?** NON - 2 CRITICAL dans ReportRule + 3 HIGH dans Recipe

---

## Actions Correctives Prioritaires

### P0 - Bloquant (CRITICAL ReportRule)

1. Reformater `compliance_mapping` dans `R-S-WFTP-WingFTP-CVE-2025-47812.json`:
   - De: `"nist_csf": ["ID.RA-1", "PR.IP-12", "DE.CM-8"]`
   - Vers: `"nist_csf": [{"id": "ID.RA-1", "name": "Risk Assessment", "description": "..."}]`

2. Ajouter `vulnerability.cve_id` dans la section `vulnerability` du JSON:
   - `"cve_id": "CVE-2025-47812"`

### P1 - Recommandé (HIGH Recipe + HIGH ReportRule)

3. Créer `RESEARCH_EVIDENCE.md` dans `$RULE_DIR/` avec proof des versions testées
4. Ajouter `required_fields` dans data_source du YAML
5. Ajouter `risk_level: "critical"` dans `R-*.json`

### P2 - Optionnel (MEDIUM)

6. Ajouter `kev_date_added` dans cve_info
7. Ajouter exploit counts depuis PostgreSQL
8. Reformater PCI DSS IDs en `Req-X.Y.Z`
9. Reformater NIST CSF en NIST 800-53 IDs (SI-2, AC-3...)
