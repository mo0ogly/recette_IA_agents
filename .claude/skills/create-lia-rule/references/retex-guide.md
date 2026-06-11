# RETEX - Capitalisation et erreurs frequentes

## 5 Questions RETEX obligatoires

A la fin de chaque session de creation de regles, raisonner systematiquement sur les 5 questions
suivantes et noter les reponses dans `_alire/tracking/RETEX_TOOLING_2026-02-17.md` :

**1. Quels checks ont echoue que le skill aurait pu prevenir ?**
   → Corriger le template du skill (prevention en amont)
   Exemple : "date: sans guillemets" → ajouter instruction dans SKILL.md

**2. Quels checks ont echoue qui necessitent un nouveau validator ?**
   → Ajouter un script dans le catalogue recette/tools/ ou recette/validators/
   Exemple : "output.include au lieu de output.fields" → nouveau check Phase04

**3. Le check existe-t-il dans les DEUX moteurs (Python + Go) ?**
   → Si non, creer un TODO pour porter dans l'autre moteur
   Commande : `bash recette/tools/compare_engines.sh <rule_dir>`

**4. Les deux moteurs sont-ils coherents sur ce check ?**
   → Si divergence : identifier lequel est canonique et aligner l'autre
   Format canonique : Go (lia_recette) est la reference

**5. Effort du fix :**
   → S (<30min) : faire maintenant dans la session
   → M (1-2h) : ajouter dans le plan RETEX
   → L (>2h) : planifier en sprint dedié

**Outils disponibles :**
```bash
# Diagnostic complet d'un package regle (lecture seule)
python3 recette/tools/scan_rule_package.py <rule_dir>

# Comparaison Python vs Go sur meme regle
bash recette/tools/compare_engines.sh <rule_dir>

# Validation batch R-*.json
bash recette/validate_reportrules_batch.sh <dir> --recursive
```

---

## Erreurs frequentes a ne pas repeter

- `date:` sans guillemets au niveau racine (YAML parse comme time.Time)
- `taxonomy.technology` et `taxonomy.category` manquants
- `output.include:` est l'ANCIEN format → utiliser `output.fields:` (FORMAT V2, seul valide)
- `pkg/bin/lia_scan_engine` (chemin obsolete) → utiliser `bin/lia_scan_engine`
- `pci_dss` avec cle `control` au lieu de `requirement`
- Remediation en tableau (format legacy) au lieu d'objet `{duration, steps}`
- Pattern arithmetique `N - N` dans computed fields (Phase07 false positive)
- `|exists: eq: false` seul insuffisant → utiliser `or[|exists: eq: false, isempty: true]`
  (Voir references/yaml-format.md section "Attributs AD optionnels")
- Regles ADDS: utiliser `target: ADDS` (pas `ActiveDirectory`) - ADDS est dans platforms.json
- Computed fields: eviter `mot (` dans les textes statiques → validator detecte comme fonction
  Exemple piege: "endpoint (gpupdate" / "populated (Get-AD" / "installed (Get-Item"
- ReportRule: champ `author` doit etre un email (ex: `mo0ogly@proton.me`)
- ReportRule: champ `technology` doit etre le short code taxonomie (ex: `ADDS` pas `ActiveDirectory`)
- Section `classification:` est redondante avec `taxonomy:` → ne pas inclure
- Section `stig` dans compliance_mapping n'est pas supportee → integrer dans `nist_800_53`
- `risk_score` a deux echelles DIFFERENTES selon le fichier:
  - YAML `A-*.yml` : echelle 0-10 (ex: `risk_score: 7` pour HIGH)
  - JSON `R-*.json` : echelle 0-100 (ex: `"risk_score": 75` pour HIGH)
  Plages JSON: CRITICAL=90-100, HIGH=70-89, MEDIUM=40-69, LOW=1-39 (validator RR06)
- Erreurs courantes taxonomie (corrigees en masse): USERS→UGRI, LOGG→PERM, SYSTEM→SYSC,
  AUDT→SYSC, FIREWALL→NETW, VULN→SYSC, FILES→PERM
- INTERDIT de renseigner collection_script avec un fichier absent (ex: Collect-Ubuntu-Packages.sh)
  Toujours confirmer: `ls /home/mo0ogly/Bureau/vscode_lia_audit/scripts/collect/{technology}/`
- ObjectClass incorrect dans le prompt (ex: panos_instance) → la gate Niveau 1 corrige via OBJECTCLASS_REFERENCE.md
  (panos_instance → paloalto_device confirme par OBJECTCLASS_REFERENCE.md en iter 3 2026-03-03)
  Ce cas doit etre documente en Q1 du RETEX : "objectclass corrige par la gate"
