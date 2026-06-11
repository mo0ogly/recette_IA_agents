# Exploration code pour fingerprint detection

Guide pour comprendre POURQUOI un pattern matche ou pas. Lire AVANT de corriger.

## A. Code LiaProbe (fichiers cles)

### Flow d'un port non-standard (ex: 18891)

```
executor.go : executeFingerprint()
  1. patterns = index.ByPort[18891]                    -> VIDE (port non-standard)
  2. banner non-vide + HTTP/ prefix?
     -> patterns = index.ByPort[80]                    -> EMPRUNTE port 80
  3. isHTTPBanner? -> auto HTTP probe (GET /)
     -> collected.HTTPResponses["_auto_http"] = reponse
  4. Phase 1 : EvaluatePattern sur chaque pattern
     -> sort par confidence decroissante               -> [Nextcloud 1.0, Apache 0.6, ...]
     -> candidates = top maxProbes (10)
  5. Phase 2 : ExecuteProbes sur candidates (GET /login, /status.php, etc.)
  6. Phase 3 : EvaluatePattern final -> AddService si conf >= threshold
```

### Fichiers a lire selon le probleme

| Probleme | Fichier | Quoi chercher |
|----------|---------|--------------|
| Pattern pas teste | `executor.go:248-360` | ByPort indexation, candidats, maxProbes limit |
| Probe skip | `probe.go:86-93` | `containsInt(probe.Ports, port)` |
| Matcher no match | `matcher.go:190-280` | `resolveHTTP()`, target switch (body/header/cookie/status_code) |
| Pattern non charge | `loader.go:83-124` | `LoadDir`, `ValidatePattern`, `normalizePattern` |
| Confidence trop basse | `matcher.go:34-98` | `EvaluatePattern`, `BaseConfidence`, `ConfidenceThreshold` |
| FP pattern trop generique | `matcher.go` + le JSON du pattern FP | Quels matchers matchent, pourquoi |

### Commandes de diagnostic rapide

```bash
# Quel patterns sont dans ByPort[80] pour une techno ?
grep -l '"default_ports"' data/fingerprints/lia/*.json | \
  xargs grep -l '"80"' | head -20

# Quels matchers a un pattern ?
python3 -c "import json; d=json.load(open('data/fingerprints/lia/TAXO.json')); \
  [print(f'  {p[\"id\"]}: {[m[\"target\"]+\":\"+m.get(\"value\",m.get(\"field\",\"\"))[:30] for m in p.get(\"matchers\",[])]}') \
  for p in d.get('probes',[])]"

# Pourquoi un FP matche ? Lire ses matchers :
python3 -c "import json; d=json.load(open('data/fingerprints/lia/RNCHR.json')); \
  [print(f'  {m[\"target\"]} {m[\"match_type\"]} {m.get(\"value\",m.get(\"field\",\"\"))} delta={m[\"confidence_delta\"]}') \
  for p in d.get('probes',[]) for m in p.get('matchers',[])]"
```

### Targets supportes par le matcher (IMPORTANT)

| Target | Supporte | Source de la valeur |
|--------|----------|-------------------|
| `body` | OUI | httpResp.Body |
| `header` | OUI | httpResp.Headers[field] (case-insensitive) |
| `cookie` | OUI | httpResp.Cookies[field] (case-sensitive!) |
| `status_code` | OUI | httpResp.StatusCode (string) |
| `response` | OUI | Raw TCP/HTTP complet |
| `response_hex` | OUI | TCP hex |
| `json_field` | OUI | JSON path extraction |
| `favicon_hash` | OUI | MMH3 du body |
| `ssl_cn` | OUI | TLS Common Name |
| `meta` | NON | Pas supporte. Convertir en body regex |
| `dom` | NON | Pas supporte. Convertir en body regex |
| `js` | NON | Pas supporte. Ignorer |
| `scriptSrc` | NON | Pas supporte. Convertir en body regex |

**Si un pattern Wappalyzer utilise `meta`, `dom`, `js`, `scriptSrc` : convertir en `target: body` avec regex equivalent.**

### Flow d'un port TCP non-standard (ex: 16379 Redis)

```
executor.go : executeFingerprint()
  1. patterns = index.ByPort[16379]                    -> VIDE
  2. banner non-vide?
     -> LiaProbe banner grab envoie des probes TCP (PING, INFO, etc.)
     -> banner = "redis_version:7.4.8\r\nredis_mode:standalone..."
  3. Switch banner detection :
     case contains("redis_version") -> patterns = index.ByPort[6379]
     case contains("caching_sha2_password") -> patterns = index.ByPort[3306]
     case startsWith("PostgreSQL SSL:") -> patterns = index.ByPort[5432]
  4. Pattern Redis emprunte -> EvaluatePattern avec banner
  5. banner_matchers matchent -> confidence directe
```

**R14 : Pour TCP, le banner detect dans l'executor suffit souvent.**
Si la banner contient un identifiant de protocole, l'executor emprunte les patterns du port standard. Il suffit d'ajouter un `banner_matcher` dans le pattern lia.

### Cookie matching (attention case-sensitive)

```go
// probe.go:267-270 -- cookies parses depuis Set-Cookie headers
cookies := make(map[string]string)
for _, c := range resp.Cookies() {
    cookies[c.Name] = c.Value  // Name est CASE-SENSITIVE
}

// matcher.go:254-257 -- cookie lookup
case "cookie":
    targetValue = httpResp.Cookies[m.Field]  // Field doit matcher le Name exact
```

**Le `field` dans le matcher cookie DOIT correspondre exactement au nom du cookie (case-sensitive).**
Exemple : cookie `phpMyAdmin` -> field `"phpMyAdmin"` (pas `"phpmyadmin"`).

**Quand utiliser cookie vs header :**
- `target: "cookie"` + `match_type: "exists"` : verifie que le cookie existe (prefere)
- `target: "header"` + `field: "Set-Cookie"` + `match_type: "contains"` : cherche dans le header brut (fallback si cookie pas parse)

## B. Sources open source (comment lire)

### Template Nuclei (.yaml)

```yaml
# Structure a chercher :
http:
  path: ["{{BaseURL}}/specific-path"]     # Paths probes (adapter dans nos probes)
  matchers:
    - type: word                           # contains exact
      part: body                           # target: body
      words: ["string_to_match"]           # value
    - type: regex                          # regex
      part: header                         # target: header
      regex: ["pattern"]
    - type: dsl                            # expression complexe
      dsl: ["contains(body, 'x')"]
  extractors:
    - type: regex                          # version_extract
      group: 1
      regex: ["version.*?([0-9.]+)"]
```

**Traduction Nuclei -> LIA fingerprint :**
| Nuclei | LIA fingerprint |
|--------|----------------|
| `type: word, part: body` | `"target": "body", "match_type": "contains"` |
| `type: regex, part: header` | `"target": "header", "match_type": "regex"` |
| `type: dsl, contains(body, 'x')` | `"target": "body", "match_type": "contains"` |
| `extractors.regex` | `"version_extract": "regex"` |

### Pattern Wappalyzer (.json)

```json
{
  "headers": {"X-Custom": "regex"},       // target: header, field: X-Custom
  "cookies": {"session_name": ""},        // target: cookie, field: session_name, match_type: exists
  "meta": {"generator": "^Product (\\d+)"},// target: body, regex sur <meta name="generator" content="...">
  "html": ["pattern_in_body"],            // target: body, match_type: regex
  "dom": ["css_selector"],               // NON SUPPORTE par LiaProbe (ignorer)
  "js": {"Obj.property": ""},            // NON SUPPORTE (ignorer)
  "scriptSrc": ["pattern"],              // NON SUPPORTE (ignorer)
  "url": ["path_pattern"]                // probe path si pertinent
}
```

**ATTENTION : `meta`, `dom`, `js`, `scriptSrc` ne sont PAS supportes par le matcher LiaProbe.**
Toujours convertir en `target: body` avec regex equivalent.

### Nmap service-probes

```
match http m|regex_pattern|s p/Product/ v/$1/ cpe:/a:vendor:product:$1/
```
Extraire : le regex, le groupe de version ($1), le CPE. Utile surtout pour TCP.

## C. Diagnostiquer un FP

### Workflow

1. **Identifier** : quel pattern FP matche sur ce port ?
   ```bash
   timeout 30 ./liaprobe/bin/liaprobe --mode specific --ports PORT 127.0.0.1 2>/dev/null | \
     grep '"pattern_id"'
   ```

2. **Comprendre** : lire les matchers du pattern FP
   ```bash
   # Trouver le fichier
   find data/fingerprints -name "PATTERN_TAXO.json" | head -3
   # Lire les matchers
   cat data/fingerprints/lia/TAXO.json | python3 -c "..." (voir commande ci-dessus)
   ```

3. **Decider** :
   - Pattern FP matche sur un signal GENERIQUE (status_code 200, header exists) -> **DESACTIVER**
   - Pattern FP matche sur un signal SPECIFIQUE mais faux -> **CORRIGER** (augmenter specificite)
   - Pattern FP matche correctement (la techno est reellement presente) -> **GARDER**

4. **Agir** :
   ```bash
   # Desactiver un FP
   python3 -c "import json; d=json.load(open('FILE')); d['enabled']=False; json.dump(d,open('FILE','w'),indent=2)"
   # Sync apres
   .claude/skills/fingerprint-lab-improve/scripts/sync_fingerprints.sh --all
   ```

### FP recurrents connus (a desactiver systematiquement)

| Pattern | Pourquoi FP | Action |
|---------|------------|--------|
| lia-truenas | Matche sur status_code 200 + body generic | DESACTIVER |
| lia-rancher | Matche sur header exists trop large | DESACTIVER |
| lia-matomo | Matche sur body contient "js" generique | DESACTIVER |
| lia-plausible | Matche sur body contient script generique | DESACTIVER |
| lia-onvif | Matche sur body XML generique | DESACTIVER |
| nuclei-detect_redmine* | Matche sur cookie generique | DESACTIVER |
| nuclei-kubelet_healthz | Matche sur status_code 200 | DESACTIVER |
