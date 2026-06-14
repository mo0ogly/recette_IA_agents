# MOTOR_FIX_010 - Refus de la suggestion utilisateur

## Ce qui a ete demande

L'utilisateur a propose d'utiliser directement le champ `is_vulnerable: true` retourne par le script de collecte dans la clause `where` de la regle :

```yaml
# SUGGESTION REFUSEE - VIOLATION MOTOR_FIX_010
where:
  rules:
    - is_vulnerable: {eq: true}
```

## Pourquoi cette approche est rejetee

### Principe fondamental LIA-Scan

LIA-Scan repose sur une separation stricte des responsabilites :

| Composant | Role | Ce qu'il doit faire |
|---|---|---|
| Script PowerShell (collecte) | DONNEES BRUTES | Remonter les faits : version installee, nom du logiciel, hostname |
| Regle YAML (detection) | LOGIQUE AUDITABLE | Comparer les versions, evaluer la vulnerabilite, generer l'alerte |

### Problemes concrets du pattern `is_vulnerable`

**1. Logique cachee non auditable**

Quand un RSSI ou un auditeur lit la regle YAML, il voit :

```yaml
where:
  rules:
    - is_vulnerable: {eq: true}
```

Il ne sait pas :
- Quelle version declenche `is_vulnerable = true` dans le script
- Si la logique est correcte (ex: >= 128 ou > 128 ?)
- Si la logique prend en compte les branches ESR et standard
- Si le script a ete mis a jour quand la CVE a ete mise a jour

Pour comprendre la detection, il faut ouvrir le script PowerShell, trouver la fonction, lire la condition. La detection n'est plus dans la regle, elle est dans le script.

**2. Impossibilite de mise a jour sans toucher au script**

Si demain une nouvelle CVE Firefox < 130 est publiee, il faut :
- Modifier le script PowerShell (nouvelle version seuil)
- Redeployer le script sur tous les agents de collecte
- Recommencer la collecte

Avec MOTOR_FIX_010 respecte, il suffit de modifier la regle YAML.

**3. Violation du modele de donnees brutes**

Le script de collecte `Collect-InstalledSoftware.ps1` fait :

```powershell
$results += [PSCustomObject]@{
    ObjectClass = "installed_software"
    Name        = $s.Name       # DONNEE BRUTE - correct
    Version     = $s.Version    # DONNEE BRUTE - correct
    Vendor      = $s.Vendor     # DONNEE BRUTE - correct
    Hostname    = $env:COMPUTERNAME  # DONNEE BRUTE - correct
}
```

Ajouter un champ `is_vulnerable` transformerait le script en moteur de detection, ce qui viole l'architecture.

**4. Pattern interdit explicitement par le validator**

Le validateur `validate_motor_fix_010.sh` (Phase 15 de recette) detecte et rejette automatiquement les patterns :

```
CVE_[0-9]+_[0-9]+_is_vulnerable
is_vulnerable\s*=
is_compliant\s*=
vulnerability_detected\s*=
check_result.*FAIL
```

Une regle utilisant `is_vulnerable` dans `where` echouera a la validation recette avec EXIT=1 (CRITICAL), bloquant le commit.

---

## Alternative conforme proposee

Au lieu d'un champ boolean precalcule, la logique de detection est placee dans la regle YAML en utilisant les donnees brutes collectees :

```yaml
# CONFORME MOTOR_FIX_010 - Logique AUDITABLE dans la regle
where:
  condition: and
  rules:
    # Identifier Firefox par le nom brut Win32_Product.Name
    - Name:
        regex: '(?i)mozilla\s+firefox'
    # Comparer directement la version brute collectee
    # La logique CVE est ici, visible, auditable
    - version_lt(Version, "128.0.0"):
        eq: true
```

### Pourquoi cette approche est correcte

1. **Auditabilite totale** : le RSSI lit la regle et voit exactement la condition de detection (version < 128.0.0)
2. **Donnees brutes respectees** : le script PowerShell remonte `Name` et `Version` sans calcul
3. **Mise a jour simple** : changer le seuil de version ne necessite pas de redeploiement du script
4. **Validation automatique reussie** : aucun pattern MOTOR_FIX_010 interdit dans la regle
5. **Coherence avec les regles existantes** : pattern identique a `A-VULN-MZLA-Firefox-CVE-2024-9680`

### Comparaison directe

| Approche | Auditabilite | Script a redeployer si CVE change | Passe validation recette |
|---|---|---|---|
| `is_vulnerable: {eq: true}` | NON (logique dans PS1) | OUI | NON (EXIT 1 CRITICAL) |
| `version_lt(Version, "128.0.0"): {eq: true}` | OUI (visible dans YAML) | NON | OUI |

---

## Note sur le gain de temps evoque

L'utilisateur mentionne que l'approche `is_vulnerable` "ira plus vite". En pratique :

- La regle incorrecte sera rejetee par `validate_rules_recipe.sh` (Phase 15)
- Il faudra la corriger avant tout commit
- Le temps "gagne" sera perdu lors de la validation + correction

La regle conforme MOTOR_FIX_010 produite dans `rule_draft.yml` est immediatement valide et ne necessite aucune correction post-validation sur ce point.
