# MOTOR_FIX_010 - Gate champs disponibles + Liste noire

## GATE BLOQUANTE: Decouverte des champs disponibles (3 NIVEAUX)

**AVANT d'ecrire la regle YAML, tu DOIS suivre cette procedure en 3 niveaux. Le niveau suivant n'est tente QUE si le precedent echoue.**

**NIVEAU 1: Script de collecte existant (IDEAL)**
```bash
# Chercher un script de collecte pour cette technologie
Glob: scripts/collect/{technology}/*.ps1
Glob: scripts/collect/{technology}/*.sh
# Si trouve: Lire le script pour extraire ObjectClass et champs
Read: scripts/collect/{technology}/Collect-{Technology}*.ps1
```
Si un script existe: extraire les ObjectClass et champs. FIN de la gate.
Si AUCUN script n'existe et qu'il en faut un: utiliser le skill `/create-collect-script` d'abord.

**NIVEAU 2: Regles existantes de la meme technologie (ACCEPTABLE)**
```bash
# Chercher des regles existantes pour copier le pattern
Glob: lia_rules/rule_analysis/{TECHNOLOGY}/**/*.yml
# Si trouve: Lire la premiere regle + son test_data.json
Read: lia_rules/rule_analysis/{TECHNOLOGY}/<premier_resultat>.yml
Read: lia_rules/rule_analysis/{TECHNOLOGY}/<premier_resultat>/test_data.json
```
Si des regles existent: copier le pattern ObjectClass/champs. FIN de la gate.

**NIVEAU 3: RECHERCHE INTERNET OBLIGATOIRE (SI NIVEAUX 1 ET 2 ECHOUENT)**

**IMPORTANT: Ce niveau est BLOQUANT. Tu NE PEUX PAS ecrire de regle YAML tant que cette recherche n'est pas faite.**

Si AUCUN script de collecte ET AUCUNE regle existante n'est disponible pour cette technologie:

```bash
# OBLIGATOIRE - Recherche internet pour decouvrir les donnees collectables
WebSearch: "{technology} powershell collect inventory script"
WebSearch: "{technology} security audit configuration export"
WebSearch: "{technology} REST API endpoints list configuration"
WebSearch: "{technology} CLI commands configuration dump"

# Si CVE specifique:
WebSearch: "CVE-YYYY-XXXXX affected versions products"
WebSearch: "{product_name} version check command"
WebFetch: "https://nvd.nist.gov/vuln/detail/CVE-YYYY-XXXXX"
```

**Ce que tu DOIS trouver via internet (minimum 3 sur 5):**
1. **ObjectClass realiste** - Quel type d'objet le produit expose (ex: instance, device, appliance, node)
2. **Champs de version** - Comment le produit expose sa version (CLI, API, fichier, registre)
3. **Champs d'identification** - Hostname, IP, FQDN, instance name
4. **Commande de collecte** - La commande reelle pour recuperer les infos (PowerShell, bash, API REST)
5. **Format de sortie** - JSON, CSV, texte structure, XML

**Documenter les resultats dans RESEARCH_EVIDENCE.md AVANT d'ecrire la regle:**
```markdown
## Collection Method Discovery (Internet Research)

### Search Queries Used
1. "{technology} powershell inventory" - [resultats]
2. "{technology} API version endpoint" - [resultats]

### Discovered Collection Method
- **Tool/API:** {nom de l'outil ou API}
- **Command:** {commande reelle trouvee}
- **Output format:** {JSON, CSV, etc.}
- **ObjectClass proposed:** {nom_propose} (base sur {source})
- **Available fields:** {liste des champs decouverts}

### Source URLs
1. [Documentation officielle](URL)
2. [Article technique](URL)
```

---

## LISTE NOIRE - Patterns INTERDITS (VIOLATION BLOQUANTE)

**Si tu utilises un de ces patterns, la regle sera REJETEE par la validation:**

```yaml
# INTERDIT ABSOLU - Logique cachee dans un champ booleen
where:
  rules:
    - is_compliant: {eq: false}                    # VIOLATION MOTOR_FIX_010
    - is_vulnerable: {eq: true}                    # VIOLATION MOTOR_FIX_010
    - CVE_2026_1234_is_vulnerable: {eq: true}      # VIOLATION MOTOR_FIX_010
    - is_patched: {eq: false}                      # VIOLATION MOTOR_FIX_010
    - is_affected: {eq: true}                      # VIOLATION MOTOR_FIX_010
    - compliance_status: {eq: "non_compliant"}     # VIOLATION MOTOR_FIX_010
    - check_result: {eq: "FAIL"}                   # VIOLATION MOTOR_FIX_010
```

**Pourquoi c'est interdit:** Ces champs supposent que la COLLECTE fait le calcul de vulnerabilite.
Le principe LIA-Scan est: la collecte remonte des DONNEES BRUTES, la REGLE fait la DETECTION.
Un RSSI doit pouvoir auditer la logique de detection dans la regle, pas dans un script externe.

**INTERDIT - ObjectClass inventes sans source:**
```yaml
# Si tu n'as PAS trouve l'ObjectClass dans un script, une regle, ou via internet
ObjectClass: my_custom_type          # INVENTE = INTERDIT
ObjectClass: postgresql_extension    # SI pas dans le script de collecte = INTERDIT
ObjectClass: fortinet_config         # SI pas dans une regle existante = INTERDIT
```

**CORRECT - Logique auditable avec champs reels:**
```yaml
# La regle compare des versions reelles
where:
  condition: and
  rules:
    - ObjectClass: {eq: "postgresql_instance"}     # Verifie dans script/regle
    - version_lt(Version, "17.3.0"): {eq: true}   # Comparaison auditable

# OU comparaison de configuration reelle
where:
  condition: and
  rules:
    - ObjectClass: {eq: "FortinetDevice"}          # Verifie dans script/regle
    - FirmwareVersion: {version_lt: "7.4.8"}       # Champ reel du produit
```

---

## REGLE ABSOLUE (resume)

- `ObjectClass` DOIT correspondre a un type reel (collecte, regle existante, ou recherche internet documentee)
- Tous les champs dans `where`, `output.fields`, `fields` DOIVENT exister dans la source identifiee
- INTERDIT d'inventer des ObjectClass ou champs sans source verifiable
- INTERDIT d'utiliser is_compliant/is_vulnerable/is_affected ou tout booleen pre-calcule
- Si le composant CVE n'a pas de script dedie: utiliser l'ObjectClass existant le plus proche
  (ex: `postgresql_instance` pour une extension PG, avec detection par version serveur)

**Principe fondamental:**
```
Collection = DONNEES BRUTES (pas de logique CVE)
Regle YAML = LOGIQUE DE DETECTION (auditable par un RSSI)
```
