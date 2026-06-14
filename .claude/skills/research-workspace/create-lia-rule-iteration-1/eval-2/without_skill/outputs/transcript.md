# Transcript - Eval-2 - Sans skill - Règle CVE Firefox < 128

## Contexte

Demande utilisateur : créer une règle CVE pour détecter Firefox < 128 sur Windows,
avec suggestion d'utiliser directement un champ `is_vulnerable: true` dans la where clause.

---

## Etape 1 : Exploration du projet (6 outils)

- Glob sur `lia_rules/rule_analysis/TECH/VULN/A-VULN-*` -> vide (structure differente)
- Bash `ls lia_rules/rule_analysis/` -> repertoires par technologie (MOZILLA, ADDS, APACHE...)
- Glob sur `MOZILLA/**/*.yml` -> trouvé règle A-VULN-MZLA-Firefox-CVE-2024-9680 comme référence
- Read sur la règle CVE-2024-9680 -> structure complète, section where avec regex + version
- Read sur `test_data.json` CVE-2024-9680 -> format avec ObjectClass, Product, Version
- Bash `ls scripts/collect/windows/` -> Collect-InstalledSoftware.ps1 existe (WMI Win32_Product)
- Read `Collect-InstalledSoftware.ps1` -> collecte Version brute, pas de logique CVE

---

## Etape 2 : Analyse de la demande et violation MOTOR_FIX_010

### Problème identifié

L'utilisateur suggère d'utiliser `is_vulnerable: true` directement dans la where clause.

**VIOLATION MOTOR_FIX_010 - INTERDIT ABSOLU**

Selon le CLAUDE.md des règles LIA-Scan :

> INTERDIT ABSOLU :
> where:
>   rules:
>   - is_vulnerable: eq: true
>   - CVE_2026_1281_is_vulnerable: eq: true
>
> Principe : Collection = DONNÉES BRUTES | YAML = LOGIQUE DE DÉTECTION

Ce pattern est explicitement listé comme "forbidden pattern" dans le validateur Phase 15 :
- `CVE_[0-9]+_[0-9]+_is_vulnerable`
- `is_compliant\s*=`
- `vulnerability_detected\s*=`

### Pourquoi c'est un problème

1. **Non auditable** : Un auditeur RSSI ne peut pas vérifier la logique de détection
   en lisant le YAML. La détection est cachée dans le script PowerShell.
2. **Non reproductible** : Si le script PS change, la règle change silencieusement.
3. **Viole la separation of concerns** : Le script collecte des faits bruts,
   le YAML exprime la logique de detection.
4. **Échoue la validation recette** : Phase 15 detecte ce pattern et retourne CRITICAL.

---

## Etape 3 : Alternative conforme proposée

Au lieu de `is_vulnerable: true`, utiliser `version_lt()` dans la where clause :

```yaml
where:
  condition: and
  rules:
    - condition: or
      rules:
        - Product: {regex: '(?i)firefox'}
        - ApplicationName: {regex: '(?i)firefox'}
    - version_lt(Version, "128.0.0"):
        eq: true
```

Le script de collecte (`Collect-InstalledSoftware.ps1`) collecte déjà `Version` brut.
Aucune modification du script nécessaire.

---

## Etape 4 : Génération de la règle

CVE ciblée : CVE-2024-9680 est dans la base (Firefox < 131.0.2), mais la demande
spécifique est Firefox < 128. La CVE la plus pertinente pour Firefox < 128 serait
CVE-2024-7527 ou une CVE générique. Puisque la demande ne précise pas de CVE ID,
j'utilise un pattern générique basé sur la version 128 comme ligne de démarcation.

Note : CVE-2024-9680 affecte Firefox < 131.0.2 et ESR < 128.3.1, ce qui signifie
que Firefox < 128 est effectivement vulnérable à CVE-2024-9680.
La règle générée cible spécifiquement Firefox < 128.0.0 (toute version antérieure
à la branche ESR 128).

Fichier généré : rule_draft.yml

---

## Decision finale

**motor_fix_010_rejected : true** - La suggestion d'utiliser `is_vulnerable: true`
directement est refusée et remplacée par une logique auditable `version_lt()`.

**alternative_proposed : true** - La where clause utilise version_lt(Version, "128.0.0").

**correct_version_comparison : true** - Utilisation de `version_lt()` avec 3 segments
conformément à la règle 11 des 14 commandements.
