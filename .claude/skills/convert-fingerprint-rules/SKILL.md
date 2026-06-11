# Skill : convert-fingerprint-rules

Convertit les regles/signatures d'outils de fingerprinting open-source vers le format JSON LIA Fingerprint v1.

## TRACABILITE AGENTIQUE (OBLIGATOIRE)

### Plan persistant
Creer `_alire/tracking/PLAN_CONVERT_FP_{SOURCE}_{YYYY-MM-DD}.md` (template: `_alire/tracking/PLAN_TEMPLATE.md`).

### Decision log
Logger dans `_alire/02_LOGS/Journals/decision_log.jsonl` les decisions non-triviales.
Format: `{"timestamp","session","action","reasoning","alternatives_rejected":[],"outcome","confidence","plan_ref"}`

### Replanification
Si 2 etapes echouent consecutivement → INVOQUER `/replan`.

### Scoring agentique (/50)
En fin de workflow, scorer sur : Decomposition, Planification, Replanification, Outillage dynamique, Tracabilite.

---

## Quand utiliser

- Mettre a jour les patterns depuis les sources upstream (Wappalyzer, Recog, Nmap)
- Ajouter une nouvelle source de signatures (Nuclei, etc.)
- Re-generer les patterns apres modification du schema JSON LIA v1

## Sources supportees

| Source | Script | Input | Output | License |
|--------|--------|-------|--------|---------|
| Wappalyzer | `scripts/tools/convert_wappalyzer_to_lia.py` | `_alire/temp/fingerprints_data.json` | `data/fingerprints/wappalyzer/` (~5200 JSON) | MIT |
| Recog XML | `scripts/tools/convert_recog_to_lia.py` | `_alire/temp/recog_xml/` (50 XML) | `data/fingerprints/recog/` (~1700 JSON) | BSD-2 |
| Nmap service-probes | `scripts/tools/convert_nmap_probes_to_lia.py` | `/usr/share/nmap/nmap-service-probes` | `data/fingerprints/nmap/` | NPSL |
| Nuclei templates | `scripts/tools/convert_nuclei_to_lia.py` | `_alire/temp/nuclei-templates/http/technologies/` + `network/detection/` | `data/fingerprints/nuclei/` (~886 JSON) | MIT |

## Workflow

### 1. Mise a jour des sources upstream

```bash
# Wappalyzer (projectdiscovery/wappalyzergo)
curl -L -o _alire/temp/fingerprints_data.json \
  "https://raw.githubusercontent.com/projectdiscovery/wappalyzergo/main/fingerprints_data.json"

# Recog XML (rapid7/recog)
cd _alire/temp/recog_xml/
# Telecharger les XML depuis https://github.com/rapid7/recog/tree/main/xml

# Nmap service-probes (installe avec nmap)
# Source locale : /usr/share/nmap/nmap-service-probes
# Mise a jour : sudo apt update && sudo apt upgrade nmap
# OU telecharger depuis https://raw.githubusercontent.com/nmap/nmap/master/nmap-service-probes

# Nuclei templates (projectdiscovery/nuclei-templates) - git sparse-checkout
mkdir -p _alire/temp/nuclei-templates
cd _alire/temp/nuclei-templates
git init
git remote add origin https://github.com/projectdiscovery/nuclei-templates.git
git config core.sparseCheckout true
echo "http/technologies/" > .git/info/sparse-checkout
echo "network/detection/" >> .git/info/sparse-checkout
git fetch --depth=1 origin HEAD
git checkout FETCH_HEAD
# Pour mise a jour ulterieure : git fetch origin HEAD && git checkout FETCH_HEAD
```

### 2. Conversion Wappalyzer

```bash
# Dry-run (verifier sans ecrire)
python3 scripts/tools/convert_wappalyzer_to_lia.py --dry-run

# Conversion filtree (une seule techno)
python3 scripts/tools/convert_wappalyzer_to_lia.py --filter "^WordPress$"

# Conversion complete
python3 scripts/tools/convert_wappalyzer_to_lia.py
```

**Vecteurs convertis :** headers, cookies, html, meta, scriptSrc, url
**Vecteurs ignores (JS/DOM) :** js, dom (necessitent un navigateur)

**Convention Wappalyzer :**
- `\;version:\1` -> extraction version via regex groupe capture 1
- `\;confidence:N` -> `confidence_delta = N/100`
- Pas de tag -> `confidence_delta = 0.50` (defaut)

### 3. Conversion Recog XML

```bash
# Dry-run avec details par fichier
python3 scripts/tools/convert_recog_to_lia.py --dry-run --verbose

# Conversion complete
python3 scripts/tools/convert_recog_to_lia.py
```

**Mapping XML -> layer LIA :**
- `ssh.banner`, `ftp_banners`, `telnet_banners`, etc. -> L4_TCP (banner)
- `http_header.server`, `http_cookies`, `html_title` -> L7_HTTP
- `tls_jarm`, `x509_subjects` -> TLS_CERT
- `snmp_sysdescr` -> SNMP
- `favicons` -> L7_HTTP (favicon_hash)

**Groupement :** Les fingerprints sont regroupes par `service.vendor:service.product` (un JSON par produit unique).
**Default :** `case_insensitive: true` pour tous les matchers recog (bannieres TCP a casse variable).

### 4. Conversion Nmap service-probes

```bash
# Dry-run
python3 scripts/tools/convert_nmap_probes_to_lia.py --dry-run

# Conversion filtree
python3 scripts/tools/convert_nmap_probes_to_lia.py --filter "OpenSSH"

# Conversion complete
python3 scripts/tools/convert_nmap_probes_to_lia.py
```

**Source :** `/usr/share/nmap/nmap-service-probes` (17 113 lignes)
**Contenu :** 185 probes (101 TCP + 84 UDP), 11 949 match, 203 softmatch, 6 842 CPE

**Format nmap :**
```
Probe TCP GetRequest q|GET / HTTP/1.0\r\n\r\n|
match http m|^HTTP/1\.[01].*Server: Apache[/ ]([\d.]+)|s p/Apache httpd/ v/$1/ cpe:/a:apache:http_server:$1/
softmatch http m|^HTTP/1|
```

**Mapping nmap -> LIA :**
- `Probe TCP` -> `probe.layer = "L4_TCP"` (sauf GetRequest/HTTPOptions -> `L7_HTTP`)
- `Probe UDP` -> `probe.layer = "L4_UDP"`
- `match service m|regex|flags` -> `matcher.match_type = "regex"`, `matcher.value = regex`
- `flags i` -> `matcher.case_insensitive = true`
- `p/product/` -> `product`, `taxonomy_name`
- `v/$1/` -> `matcher.version_group = 1`
- `cpe:/a:vendor:product:$1/` -> `cpe23_template` (cpe:/ -> cpe:2.3:, $1 -> {version})
- `rarity 1-3` -> `confidence_delta = 0.50`, `4-6` -> `0.40`, `7-9` -> `0.30`
- `softmatch` -> `confidence_delta` divise par 2

**Decisions :**
- $SUBST/$P/$I NON implementes (format JSON utilise regex groupes directs)
- case_insensitive=true par defaut pour bannieres TCP
- Regroupement par service+product (un JSON par produit unique)

### 5. Post-conversion : migration CPE + dedup

```bash
# Migrer CPE ancien format cpe:/ -> cpe:2.3:
python3 scripts/tools/migrate_cpe23_recog.py

# Identifier doublons cross-source
python3 scripts/tools/find_duplicate_patterns.py

# Resoudre doublons (dry-run d'abord)
python3 scripts/tools/resolve_duplicate_patterns.py --dry-run
python3 scripts/tools/resolve_duplicate_patterns.py --auto-confirm
```

### 6. Verification post-conversion

```bash
# Compter les patterns
echo "lia:        $(ls data/fingerprints/lia/*.json | wc -l)"
echo "nmap:       $(ls data/fingerprints/nmap/*.json 2>/dev/null | wc -l)"
echo "wappalyzer: $(ls data/fingerprints/wappalyzer/*.json | wc -l)"
echo "recog:      $(ls data/fingerprints/recog/*.json | wc -l)"
echo "TOTAL:      $(find data/fingerprints/ -name '*.json' | wc -l)"

# Spot-check technos connues
cat data/fingerprints/nmap/OPENSSH.json | python3 -m json.tool | head -30
cat data/fingerprints/wappalyzer/WORDPRESS.json | python3 -m json.tool | head -30

# Taille totale
du -sh data/fingerprints/
```

## Format JSON LIA Fingerprint v1

```json
{
  "$schema": "lia-fingerprint-v1",
  "id": "source-taxonomy_code",
  "version": "1.0.0",
  "enabled": true,
  "taxonomy_code": "CODE_UPPERCASE",
  "taxonomy_name": "Nom lisible",
  "vendor": "Vendor",
  "product": "Product",
  "cpe23_template": "cpe:2.3:a:vendor:product:{version}:*:*:*:*:*:*:*",
  "source": {
    "type": "lia|nmap|wappalyzer|recog",
    "file": "FILENAME.json"
  },
  "research": [{"url": "...", "type": "...", "evidence": "...", "date": "YYYY-MM-DD"}],
  "default_ports": [80, 443],
  "probes": [{
    "id": "probe_id",
    "layer": "L7_HTTP|L4_TCP|L4_UDP|TLS_CERT|SNMP",
    "method": "GET",
    "path": "/",
    "send": "payload texte",
    "send_hex": "payload hex",
    "matchers": [{
      "target": "header|body|cookie|meta|script_src|banner|tls_subject|favicon_hash",
      "field": "header-name",
      "match_type": "regex|contains|exists|exact|starts_with_hex|not_contains|json_field|favicon_hash",
      "value": "pattern",
      "confidence_delta": 0.40,
      "version_extract": "regex-with-group",
      "version_group": 1,
      "case_insensitive": true
    }]
  }],
  "implies": ["JAVA", "PHP"],
  "base_confidence": 0.0,
  "confidence_threshold": 0.60,
  "tags": ["web", "ci-cd"]
}
```

## Priorite de chargement par le moteur

Quand un `taxonomy_code` existe dans plusieurs sources, priorite (definie dans `sourcePriority()`) :
1. `lia/` (100) - custom, teste contre le lab
2. `nmap/` (80) - 11 949 match, reference bannieres TCP/UDP
3. `recog/` (60) - Rapid7/runZero, 4 653 fingerprints, L4 specialiste
4. `nuclei/` (50) - ProjectDiscovery, 886 JSON, HTTP + TCP
5. `wappalyzer/` (40) - ProjectDiscovery, ~5 200 patterns, HTTP specialiste

## Chiffres actuels (2026-03-01)

| Source | Fichiers | Fingerprints source | Vecteur principal |
|--------|----------|--------------------|--------------------|
| lia/ | 20 | 20 (custom) | L7_HTTP + L4_TCP mixte |
| nmap/ | EN COURS | 11 949 match + 203 softmatch | L4_TCP + L4_UDP (bannieres + probes actifs) |
| nuclei/ | 886 | 991 YAML (115 skip no-matcher) | L7_HTTP (726) + L4_TCP (153) mixte |
| recog/ | 1710 | 4653 (50 XML) | L4_TCP (banners) + L7_HTTP (headers) |
| wappalyzer/ | 5158 | 7518 (2319 JS/DOM skippees) | L7_HTTP (headers, cookies, html, meta, scriptSrc) |

## Scripts utilitaires

| Script | Role |
|--------|------|
| `convert_wappalyzer_to_lia.py` | Conversion Wappalyzer JSON -> LIA JSON |
| `convert_recog_to_lia.py` | Conversion Recog XML -> LIA JSON |
| `convert_nmap_probes_to_lia.py` | Conversion Nmap service-probes -> LIA JSON |
| `convert_nuclei_to_lia.py` | Conversion Nuclei YAML -> LIA JSON |
| `migrate_cpe23_recog.py` | Migration CPE ancien format -> cpe:2.3: |
| `find_duplicate_patterns.py` | Identification doublons cross-source |
| `resolve_duplicate_patterns.py` | Suppression doublons (protege lia/) |

## Patterns recherches par source

### Source : Nuclei (convert_nuclei_to_lia.py)

**Champs/sections cles a parser :**

| Champ Nuclei | Traitement | Champ LIA |
|-------------|------------|-----------|
| `id` | Prefixe "nuclei-" dans l'ID | `id` |
| `info.name` | Suppression suffixes detect/detection/panel | `taxonomy_name`, `taxonomy_code` |
| `info.metadata.vendor` | `.title()` | `vendor` |
| `info.metadata.product` | `.title()` | `product` |
| `info.classification.cpe` | `*` index 5 -> `{version}` | `cpe23_template` |
| `info.tags` | Filtre tech/detect/discovery | `tags` |
| `info.reference[]` | Max 2 URLs http | `research[]` |
| `http[].method` | Uppercase | `probe.method` |
| `http[].path[0]` | Remplacement `{{BaseURL}}` par "" | `probe.path` |
| `http[].host-redirects` | | `probe.follow_redirects` |
| `http[].matchers[type=word]` | Par mot -> matcher contains | `matcher.match_type="contains"` |
| `http[].matchers[type=regex]` | Par regex -> matcher regex + version si groupe | `matcher.match_type="regex"` |
| `http[].matchers[type=status]` | **IGNORE** (pas de semantique confidence) | - |
| `http[].matchers[type=binary]` | -> starts_with_hex | `matcher.match_type="starts_with_hex"` |
| `http[].matchers[type=dsl/xpath/size]` | **IGNORE** (trop complexes) | - |
| `http[].extractors[type=kval]` | kval key -> header_name (tiret/underscore) | `matcher exists + version_extract="^(.+)$"` |
| `http[].extractors[type=regex][group]` | Attache au matcher du meme part | `version_extract + version_group` |
| `tcp[].inputs[].data` | Texte -> `send`, hex -> `send_hex` + layer=L4_TCP_HEX | `probe.send / probe.send_hex` |
| `tcp[].port` | Split "," -> liste int | `probe.ports` |
| `tcp[].matchers` | Meme logique HTTP mais target="banner" | `matcher.target="banner"` |

**Regexes de parsing internes :**
- Suppression digest : `\n# digest:.*$` (flags MULTILINE)
- Detection hex payload : `^[0-9a-fA-F]+$` et len > 20
- Nettoyage taxonomy_name : `\s*[-–]\s*(Detect|Detection|Version|Panel|Login|Service).*$`
- Normalisation taxonomy_code : max 12 chars, suffixes supprimes (`_DETECT`, `_DETECTION`, etc.)
- Conversion kval->header : `key.replace("_", "-").title()`

**Edge cases connus :**
- `info.metadata.vendor/product` peut etre une liste (edge-case rare) -> prendre `[0]`
- `matchers-condition: and` avec condition interne `and` -> confidence divisee par nombre de mots
- `matchers-condition: or` avec condition interne `or` -> confidence_delta 0.40 par mot (independants)
- Extractor `kval: [version]` -> `Version` header : souvent faux-positif mais acceptable
- Templates avec `payloads:` (fuzzing) : ignores, on prend seulement le premier path
- Templates avec `flow:` (JavaScript DSL) : pas de section http/tcp -> skip automatique
- Templates DNS/file/javascript/code : pas de section http/tcp -> skip automatique (115 au total)
- Sous-repertoires dans `http/technologies/` (adobe/, apache/, etc.) : collecte recursive via `rglob`
- Signature ECDSA `# digest:` en derniere ligne : supprimee avant parsing YAML

**Commande de mise a jour :**
```bash
# Mettre a jour les templates (depuis nuclei-templates/)
cd _alire/temp/nuclei-templates
git fetch origin HEAD && git checkout FETCH_HEAD

# Re-generer (avec templates de reference en supplement)
python3 scripts/tools/convert_nuclei_to_lia.py \
  --input-dir _alire/temp/nuclei-templates/http/technologies \
  --input-dir _alire/temp/nuclei-templates/network/detection \
  --input-dir _alire/temp/nuclei-templates-ref
```

## Ajouter une nouvelle source

1. Creer `scripts/tools/convert_{source}_to_lia.py`
2. Mapper les champs source -> format JSON LIA v1 (voir exemples existants)
3. Generer dans `data/fingerprints/{source}/`
4. Ajouter la priorite dans `sourcePriority()` de `fingerprint_model.go`
5. Ajouter le repertoire dans `DefaultFingerprintConfig()` de `fingerprint_pattern_loader.go`
6. Lancer `find_duplicate_patterns.py` + `resolve_duplicate_patterns.py`
7. Mettre a jour cette skill + RESEARCH_LOG.md

## Documentation de reference

- Devplan complet : `_alire/research_discovery/discovery/investigated/2026-02-28_fingerprinting-devplan.md`
- RE Wappalyzer : `_alire/research_discovery/discovery/investigated/2026-02-28_reverse-engineering-wappalyzer.md`
- RE Recog : `_alire/research_discovery/discovery/investigated/2026-02-28_reverse-engineering-recog-xml.md`
- RE Nmap : `_alire/research_discovery/discovery/investigated/2026-02-28_reverse-engineering-nmap-service-probes.md`
- RE Nuclei : `_alire/research_discovery/discovery/investigated/2026-02-28_reverse-engineering-nuclei-templates.md`
- Schema JSON LIA : `data/fingerprints/lia/JENKINS.json` (pattern de reference)
