# Reponse au prompt : Phase 14 CRITICAL - block_short 'VULN' not found in UBUNTU taxonomy

Using recette-lia-rule skill. Reading reference files...

---

## 1. Diagnostic precis de l'erreur

L'erreur Phase 14 est generee par le validateur `validate_taxonomy_directory_coherence.py` (invoque via `phase14_taxonomy_coherence.sh`). Ce validateur verifie la coherence entre trois sources de verite :

1. Le repertoire physique (`rule_analysis/UBUNTU/VULN/A-VULN-UB22-KernelLocalPrivilege/`)
2. Le fichier JSON de taxonomie (`config/taxonomy/UBUNTU_taxonomy.json`)
3. Le champ `block_short` dans le YAML de la regle

**Ce que dit l'erreur :**
```
Phase 14 [CRITICAL] Taxonomy Directory Coherence
  block_short 'VULN' not found in UBUNTU taxonomy
  Valid blocks for UBUNTU: SECU, ARCM, CGOV, HEAL, SYSC, NETW, PERM, PACK
  Rule block_short: VULN
  Directory path contains: VULN
  Expected path: UBUNTU/{AXIS}/SYSC/ (suggested)
```

Le validateur confirme que `VULN` n'est pas un block valide dans la taxonomie UBUNTU. La liste des blocks valides est `SECU, ARCM, CGOV, HEAL, SYSC, NETW, PERM, PACK`. Le validateur suggere `SYSC` comme block de substitution pour les regles de type kernel/systeme.

---

## 2. Identification du block_short correct

Le mapping documente dans le CORRECTIONS_REFERENCE.md du skill recette-lia-rule est le suivant :

| block_short invalide | block_short correct | Contexte |
|---------------------|---------------------|----------|
| VULN | SYSC | CVE kernel, privilege escalation, vuln systeme |
| USERS | UGRI | Gestion utilisateurs |
| LOGG | PERM | Logs/permissions |
| SYSTEM | SYSC | Composants systeme |
| AUDT | SYSC | Audit systeme |
| FIREWALL | NETW | Reseau |
| FILES | PERM | Fichiers/permissions |

**Pour `A-VULN-UB22-KernelLocalPrivilege` :** le block_short correct est **`SYSC`** (System Components). Une CVE de privilege escalation local sur le kernel Linux est semantiquement un composant systeme (`SYSC`), pas un block `VULN` qui n'existe pas dans la taxonomie UBUNTU.

Pour confirmer les blocks disponibles dans la taxonomie UBUNTU :

```bash
python3 -c "
import json
d = json.load(open('config/taxonomy/UBUNTU_taxonomy.json'))
for t in d.get('taxonomies', []):
    for a in t.get('axes', []):
        print(a['quadrigram'], [b['quadrigram'] for b in a.get('blocks', [])])
"
```

---

## 3. Corrections a appliquer

### Correction 1 : Modifier le YAML de la regle

Dans le fichier `lia_rules/rule_analysis/UBUNTU/VULN/A-VULN-UB22-KernelLocalPrivilege/A-VULN-UB22-KernelLocalPrivilege.yml`, modifier le champ `block_short` :

```yaml
# AVANT (invalide)
taxonomy:
  taxonomy: UBUNTU
  taxonomy_short: UBUNTU
  axis: vulnerability
  axis_short: VULN
  block: Vulnerability
  block_short: VULN        # Invalide dans taxonomie UBUNTU
  component: CVE Detection
  component_short: CVE

# APRES (correct)
taxonomy:
  taxonomy: UBUNTU
  taxonomy_short: UBUNTU
  axis: vulnerability
  axis_short: VULN
  block: System Components
  block_short: SYSC        # Block valide dans taxonomie UBUNTU
  component: CVE Detection
  component_short: CVE
```

### Correction 2 : Renommer le repertoire

Le chemin physique doit etre coherent avec le `block_short`. Le repertoire actuel contient `VULN` dans son chemin :

```
AVANT : lia_rules/rule_analysis/UBUNTU/VULN/A-VULN-UB22-KernelLocalPrivilege/
APRES : lia_rules/rule_analysis/UBUNTU/SYSC/A-VULN-UB22-KernelLocalPrivilege/
```

Commande de renommage :

```bash
# Depuis la racine du projet
cd /home/mo0ogly/Bureau/vscode_lia_audit

# Creer le repertoire SYSC s'il n'existe pas
mkdir -p lia_rules/rule_analysis/UBUNTU/SYSC/

# Deplacer la regle
mv lia_rules/rule_analysis/UBUNTU/VULN/A-VULN-UB22-KernelLocalPrivilege/ \
   lia_rules/rule_analysis/UBUNTU/SYSC/A-VULN-UB22-KernelLocalPrivilege/

# Supprimer le repertoire VULN si vide
rmdir lia_rules/rule_analysis/UBUNTU/VULN/ 2>/dev/null || true
```

**Important :** Ne pas modifier le JSON de taxonomie `config/taxonomy/UBUNTU_taxonomy.json` pour y ajouter `VULN` comme nouveau block. La regle impose d'utiliser un block existant. `SYSC` est le bon choix semantique pour les CVE kernel.

---

## 4. Commande de re-validation

Apres avoir applique les deux corrections (YAML + repertoire), relancer la recette sur le nouveau chemin :

```bash
cd /home/mo0ogly/Bureau/vscode_lia_audit/recette

# Re-validation complete (3 scripts)
./validate_rules_ALL.sh ../lia_rules/rule_analysis/UBUNTU/SYSC/A-VULN-UB22-KernelLocalPrivilege/

# Ou les 3 scripts separement si validate_rules_ALL.sh n'est pas disponible :
./validate_rules_recipe.sh ../lia_rules/rule_analysis/UBUNTU/SYSC/A-VULN-UB22-KernelLocalPrivilege/
./validate_rules_ultimate.sh ../lia_rules/rule_analysis/UBUNTU/SYSC/A-VULN-UB22-KernelLocalPrivilege/
./validate_reportrules.sh ../lia_rules/rule_analysis/UBUNTU/SYSC/A-VULN-UB22-KernelLocalPrivilege/R-*.json
```

Resultat attendu apres correction :

```
Phase 14 [PASS] Taxonomy Directory Coherence
  block_short 'SYSC' found in UBUNTU taxonomy
  Directory path: UBUNTU/SYSC/ - coherent
```

---

## Recap des actions

| Etape | Action | Fichier/Chemin |
|-------|--------|----------------|
| 1 | Modifier `block_short: VULN` en `block_short: SYSC` | `UBUNTU/SYSC/A-VULN-UB22-KernelLocalPrivilege/A-VULN-UB22-KernelLocalPrivilege.yml` |
| 2 | Renommer le repertoire `VULN/` en `SYSC/` | `lia_rules/rule_analysis/UBUNTU/VULN/` -> `UBUNTU/SYSC/` |
| 3 | Re-valider avec validate_rules_recipe.sh | Verification Phase 14 PASS |

**Ne pas ajouter `VULN` dans le JSON taxonomie.** Utiliser `SYSC` qui est le block existant et semantiquement correct pour les vulnerabilites kernel/systeme dans la taxonomie UBUNTU.
