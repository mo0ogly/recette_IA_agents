# Post-Creation Gates and Tracking

## VERIFICATION GATE POST-CREATION (BLOQUANT)

**Apres creation de la regle ET apres recette exit 0, AVANT le commit :**

```bash
# 1. COHERENCE GATE -- les fichiers existent et sont lies
ls {RULE_DIR}/rule.yml                     # YAML existe
ls {RULE_DIR}/R-*.json                     # ReportRule existe
ls {RULE_DIR}/test_data.json               # Test data existe
ls {RULE_DIR}/test_rule.sh                 # Test script existe

# 2. IMPORT GATE -- le test moteur fonctionne reellement
bash {RULE_DIR}/test_rule.sh 2>&1 | tail -5    # Doit afficher des hits

# 3. CROSS-REFERENCE GATE -- ObjectClass coherent partout
OBJCLASS=$(grep "ObjectClass:" {RULE_DIR}/rule.yml | head -1 | awk '{print $NF}')
grep -q "$OBJCLASS" {RULE_DIR}/test_data.json || echo "MISMATCH ObjectClass!"

# 4. ZERO-PLACEHOLDER GATE -- pas de TODO, placeholder, example.com
grep -ri "TODO\|placeholder\|example\.com\|lorem\|FIXME" {RULE_DIR}/ && echo "PLACEHOLDER FOUND!"

# 5. SELF-SCORING -- recette score stable
# Le rapport recette doit etre dans {RULE_DIR}/recette/ avec exit 0
```

**Si une gate echoue :** STOP. Corriger. Re-executer la gate ET la recette. JAMAIS commiter avec une gate rouge.

**Incident de reference :** Des agents ont cree des regles avec des ObjectClass inventes, des test_data
incoherents, ou des placeholders non remplaces. Cette gate previent ces regressions.

---

## Phase 8: Tracking PostgreSQL (OBLIGATOIRE apres recette exit 0)

**Apres recette exit 0 ET commit, mettre a jour la table `lia_cve_rules_coverage` :**

> **SCOPE:** Cette phase s'applique UNIQUEMENT aux regles CVE (type `cve`).
> Pour les regles compliance/bank/hunting, cette phase est ignoree.

```bash
# Upsert dans lia_cve_rules_coverage
# Variables a remplacer: {CVE_ID}, {RULE_ID}, {RULE_PATH}, {TECHNOLOGY}, {CVSS}, {SEVERITY}, {IS_KEV}
psql_lia << 'SQL'
INSERT INTO lia_cve_rules_coverage (
    cve_id, lia_technology, cvss_score, cvss_severity, is_kev,
    status, rule_id, rule_path, priority, notes,
    recette_exit, recette_summary, attempt_count, updated_at
)
VALUES (
    '{CVE_ID}',
    '{TECHNOLOGY}',
    {CVSS},
    '{SEVERITY}',
    {IS_KEV},
    'completed',
    '{RULE_ID}',
    'rule_analysis/{TECHNOLOGY}/VULN/{RULE_ID}/',
    'P1',
    'Created by create-lia-rule skill - recette exit 0',
    0,
    'ALL PASS - recipe + ultimate + reportrule',
    1,
    NOW()
)
ON CONFLICT (cve_id) DO UPDATE SET
    status = 'completed',
    rule_id = EXCLUDED.rule_id,
    rule_path = EXCLUDED.rule_path,
    lia_technology = EXCLUDED.lia_technology,
    recette_exit = 0,
    recette_summary = 'ALL PASS - recipe + ultimate + reportrule',
    attempt_count = lia_cve_rules_coverage.attempt_count + 1,
    updated_at = NOW();
SQL
echo "Coverage PostgreSQL mis a jour pour {CVE_ID} -> {RULE_ID}"
```

**Verification post-upsert :**
```bash
psql_lia -t -A \
  -c "SELECT cve_id, status, rule_id, recette_exit FROM lia_cve_rules_coverage WHERE cve_id = '{CVE_ID}';"
```

**INTERDIT :** Marquer `status = 'completed'` si recette exit != 0.

---

## RESEARCH_EVIDENCE.md Template (Phase 6)

> **HARD GATE (2026-03-05):** Ce fichier DOIT contenir le **contenu reel** des recherches web,
> pas juste des liens. Chaque WebSearch/WebFetch doit etre trace avec son resultat.
> Si le fichier ne contient que du metadata PostgreSQL sans contenu web = REJET.

**Workflow obligatoire :**
1. Executer les WebSearch/WebFetch de la Phase 0 (Gate Niveau 3)
2. Copier le contenu pertinent de chaque resultat dans RESEARCH_EVIDENCE.md
3. Inclure: extraits NVD, advisories vendor, versions affectees, workarounds

```markdown
# Research Evidence - {RULE_ID}

## Date: YYYY-MM-DD

## 1. PostgreSQL (lia_scan database)
- CVE ID: {cve_id}
- CVSS Score: {score} ({severity})
- CISA KEV: {yes/no}
- Exploit Maturity: {WEAPONIZED/FUNCTIONAL/POC/NONE}

## 2. NVD (WebFetch: https://nvd.nist.gov/vuln/detail/{CVE_ID})
**Contenu extrait:**
- Description: {COPIER LA DESCRIPTION COMPLETE}
- CVSS Vector: {COPIER LE VECTEUR}
- CWE: {CWE-XXX} - {nom}
- References: {LISTER LES URLS DU NVD}
- Affected versions: {COPIER LES CPE/VERSIONS}

## 3. Vendor Advisory (WebFetch: {URL_ADVISORY})
**Contenu extrait:**
- Titre: {titre de l'advisory}
- Versions corrigees: {versions}
- Workaround: {workaround si disponible}
- Recommendations: {COPIER LES RECOMMENDATIONS}

## 4. CISA KEV (si applicable)
- Date added: {date}
- Due date: {date}
- Action required: {action}

## 5. Exploit Intelligence (WebSearch: "{CVE_ID} exploit PoC")
- Metasploit module: {oui/non + nom}
- GitHub PoCs: {nombre + qualite}
- Maturity: {WEAPONIZED/FUNCTIONAL/POC/NONE}

## 6. Compliance Mapping
| Framework | Controle | Description |
|-----------|----------|-------------|
| PCI-DSS | X.Y | ... |
| ANSSI | RXX | ... |
| MITRE ATT&CK | TXXXX | {technique name} |
```

**REGLES STRICTES:**
- Chaque section "WebFetch" doit contenir du contenu **copie depuis la page**, pas inventee
- Si WebFetch echoue, documenter l'echec et utiliser WebSearch comme fallback
- Minimum 2 sources web reelles (NVD + 1 autre)
- Le fichier doit etre suffisamment detaille pour qu'un auditeur puisse verifier les sources

---

## AUDIT SCRIPTS MANQUANTS

Pour connaitre l'etat global des scripts de collecte manquants sur toutes les regles :

```bash
# Rapport complet (147 technologies, 474 scripts a creer)
python3 .claude/skills/create-lia-rule/scripts/audit_missing_collect_scripts.py \
    --output TODO_collect_scripts.md
# Sortie : _alire/temp/TODO_collect_scripts.md

# Filtrer sur une techno en particulier
python3 .claude/skills/create-lia-rule/scripts/audit_missing_collect_scripts.py \
    --tech NGINX

# Regenerer apres avoir cree des scripts (pour mesurer la progression)
python3 .claude/skills/create-lia-rule/scripts/audit_missing_collect_scripts.py \
    --output TODO_collect_scripts_$(date +%Y%m%d).md
```

Le rapport liste par technologie : script a creer, effort estime (S/M/L), nombre de regles impactees, commande `/create-collect-script` a invoquer.
