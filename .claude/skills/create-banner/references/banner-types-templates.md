# Banner Types and Templates Reference

## Banner Type Decision Tree

```
Le service repond a une connexion TCP ?
+-- OUI, immediatement (sans rien envoyer)
|   +-- La reponse est du texte lisible ? -> tcp_init
|   +-- La reponse est du binaire ? -> hex_respond (avec banner_hex, sans trigger_hex)
+-- NON, il attend que le client envoie quelque chose
    +-- Le service comprend HTTP (GET /) ?
    |   +-- OUI -> http (headers + body configurables)
    +-- Le service attend une commande texte specifique (PING, stats, etc.) ?
    |   +-- OUI -> tcp_respond (trigger = commande, banner = reponse)
    +-- Le service attend un payload binaire specifique ?
        +-- Handshake exact connu (SOCKS5 050100, S7comm 0300...) -> hex_respond avec trigger_hex
        +-- Reponse a n'importe quelle donnee (TDS PreLogin, TNS, RDP) -> hex_respond avec probe_hex (sans trigger_hex)
```

## Type Summary

| Type | Comportement | Exemples | Champs banner.json |
|------|-------------|----------|-------------------|
| `tcp_init` | Connexion TCP -> banniere envoyee immediatement | SSH, FTP, SMTP, POP3, IMAP, IRC, VNC, Telnet | `banner` (string avec `\r\n`) |
| `tcp_respond` | Connexion TCP -> client envoie commande -> serveur repond | Redis (PING->PONG), Memcache (stats->STAT) | `banner` (string reponse) |
| `http` | Client envoie GET HTTP -> serveur repond headers+body | Nginx, Apache, Grafana, Jenkins, PaloAlto | `http_status`, `http_headers`, `http_body` |
| `hex_respond` | Client envoie payload binaire (hex) -> serveur repond binaire | SOCKS5, S7comm, MSSQL, RDP, LDAP | `trigger_hex` or `probe_hex`, `banner_hex` |

## trigger_hex vs probe_hex (CRITICAL)

| Champ | Lu par le serveur | Comportement |
|-------|------------------|--------------|
| `trigger_hex` | OUI | Le serveur attend EXACTEMENT ce hex avant de repondre |
| `probe_hex` | NON | Documentaire uniquement - le serveur repond a n'importe quelle donnee |

Use `trigger_hex` for protocols with known specific handshake (SOCKS5 `050100`).
Use `probe_hex` for simulated responses without trigger matching (TDS PreLogin, TNS Refuse).

---

## banner.json Templates

### tcp_init

```json
{
  "id": "lia-{taxonomy_lower}",
  "port": 9XXX,
  "taxonomy": "{TAXONOMY}",
  "type": "tcp_init",
  "banner": "{banniere_exacte}\\r\\n",
  "note": "{description courte du service}",
  "fingerprint_source": "data/fingerprints/lia/{TAXONOMY}.json",
  "added_date": "YYYY-MM-DD"
}
```

### tcp_respond

```json
{
  "id": "lia-{taxonomy_lower}",
  "port": 9XXX,
  "taxonomy": "{TAXONOMY}",
  "type": "tcp_respond",
  "banner": "{reponse_exacte}\\r\\n",
  "note": "{protocole} {commande} -> {reponse}",
  "fingerprint_source": "data/fingerprints/lia/{TAXONOMY}.json",
  "added_date": "YYYY-MM-DD"
}
```

### http

```json
{
  "id": "lia-{taxonomy_lower}",
  "port": 9XXX,
  "taxonomy": "{TAXONOMY}",
  "type": "http",
  "http_status": "200 OK",
  "http_headers": {
    "Server": "{ProductName}/{version}",
    "Content-Type": "text/html"
  },
  "http_body": "<html>...</html>",
  "note": "{description de la detection HTTP}",
  "fingerprint_source": "data/fingerprints/lia/{TAXONOMY}.json",
  "added_date": "YYYY-MM-DD"
}
```

### hex_respond (trigger exact)

```json
{
  "id": "lia-{taxonomy_lower}",
  "port": 9XXX,
  "taxonomy": "{TAXONOMY}",
  "type": "hex_respond",
  "trigger_hex": "{hex_trigger_sans_espaces}",
  "banner_hex": "{hex_reponse_sans_espaces}",
  "note": "{protocole} handshake description",
  "fingerprint_source": "data/fingerprints/lia/{TAXONOMY}.json",
  "added_date": "YYYY-MM-DD"
}
```

### hex_respond (respond-any)

```json
{
  "id": "lia-{taxonomy_lower}",
  "port": 9XXX,
  "taxonomy": "{TAXONOMY}",
  "type": "hex_respond",
  "probe_hex": "{hex_a_envoyer_pour_tester}",
  "banner_hex": "{hex_reponse_sans_espaces}",
  "note": "{protocole} description",
  "fingerprint_source": "data/fingerprints/lia/{TAXONOMY}.json",
  "added_date": "YYYY-MM-DD"
}
```

### Required fields (ALL types)

- `id` : unique identifier (format `lia-{taxonomy_lower}[-qualifier]`)
- `port` : TCP port in range 9001-9099
- `taxonomy` : LIA taxonomy code 4 letters (UPPERCASE)
- `type` : one of 4 types (`tcp_init`, `tcp_respond`, `http`, `hex_respond`)
- `note` : short description (English)
- `fingerprint_source` : relative path to LIA fingerprint JSON
- `added_date` : date YYYY-MM-DD

---

## probe.sh Templates

### tcp_init

```bash
#!/bin/bash
# Probe test for {TAXONOMY} ({id}) on port {PORT}
# Type: tcp_init
set -euo pipefail
PORT={PORT}
HOST="${BANNER_HOST:-localhost}"
EXPECTED_TAXONOMY="{TAXONOMY}"
echo "=== TCP INIT probe: $HOST:$PORT ==="
RESULT=$(timeout 2 nc -w1 "$HOST" "$PORT" 2>/dev/null || true)
if [ -z "$RESULT" ]; then
    echo "FAIL: no banner received from $HOST:$PORT"
    exit 1
fi
echo "--- Banner received ---"
echo "$RESULT"
if echo "$RESULT" | grep -qi "{pattern_attendu}"; then
    echo "PASS: '{pattern_attendu}' detecte (banner_matcher OK)"
else
    echo "WARN: '{pattern_attendu}' absent de la reponse"
fi
echo ""
echo "Taxonomy attendue: $EXPECTED_TAXONOMY"
echo "Port: $PORT"
echo "Type: tcp_init"
```

### tcp_respond

```bash
#!/bin/bash
# Probe test for {TAXONOMY} ({id}) on port {PORT}
# Type: tcp_respond
set -euo pipefail
PORT={PORT}
HOST="${BANNER_HOST:-localhost}"
EXPECTED_TAXONOMY="{TAXONOMY}"
echo "=== TCP RESPOND probe: $HOST:$PORT ==="
echo "--- Sending trigger: {commande} ---"
RESULT=$(printf "{commande}\r\n" | timeout 2 nc -w1 "$HOST" "$PORT" 2>/dev/null || true)
if [ -z "$RESULT" ]; then
    echo "FAIL: no response from $HOST:$PORT"
    exit 1
fi
echo "--- Response ---"
echo "$RESULT"
if echo "$RESULT" | grep -qi "{pattern_reponse}"; then
    echo "PASS: '{pattern_reponse}' detecte dans la reponse (banner_matcher OK)"
else
    echo "WARN: '{pattern_reponse}' absent de la reponse"
fi
echo ""
echo "Taxonomy attendue: $EXPECTED_TAXONOMY"
echo "Port: $PORT"
echo "Type: tcp_respond"
```

### http

```bash
#!/bin/bash
# Probe test for {TAXONOMY} ({id}) on port {PORT}
# Type: http
set -euo pipefail
PORT={PORT}
HOST="${BANNER_HOST:-localhost}"
EXPECTED_TAXONOMY="{TAXONOMY}"
echo "=== HTTP probe: http://$HOST:$PORT/ ==="
RESPONSE=$(curl -si --connect-timeout 3 "http://$HOST:$PORT/" 2>/dev/null || true)
if [ -z "$RESPONSE" ]; then
    echo "FAIL: no HTTP response from $HOST:$PORT"
    exit 1
fi
echo "--- Response headers ---"
echo "$RESPONSE" | head -15
echo ""
echo "--- Response body ---"
BODY=$(echo "$RESPONSE" | awk '/^\r?$/{found=1; next} found{print}')
echo "$BODY" | head -5
if echo "$RESPONSE" | grep -qi "{header_ou_body_pattern}"; then
    echo "PASS: '{header_ou_body_pattern}' detecte (banner_matcher OK)"
else
    echo "WARN: '{header_ou_body_pattern}' absent de la reponse"
fi
echo ""
echo "Taxonomy attendue: $EXPECTED_TAXONOMY"
echo "Port: $PORT"
echo "Type: http"
```

### hex_respond

```bash
#!/bin/bash
# Probe test for {TAXONOMY} ({id}) on port {PORT}
# Type: hex_respond
set -euo pipefail
PORT={PORT}
HOST="${BANNER_HOST:-localhost}"
EXPECTED_TAXONOMY="{TAXONOMY}"
echo "=== HEX RESPOND probe: $HOST:$PORT ==="
echo "--- Sending hex trigger: {trigger_hex} ---"
RESULT=$(printf '{trigger_bytes}' | timeout 2 nc -w1 "$HOST" "$PORT" 2>/dev/null | xxd -p | tr -d '\n')
if [ -z "$RESULT" ]; then
    echo "FAIL: no response from $HOST:$PORT"
    exit 1
fi
echo "--- Hex response: $RESULT ---"
EXPECTED="{expected_hex}"
if echo "$RESULT" | grep -qi "$EXPECTED"; then
    echo "PASS: expected response $EXPECTED detected"
else
    echo "WARN: expected $EXPECTED but got $RESULT"
fi
echo ""
echo "Taxonomy attendue: $EXPECTED_TAXONOMY"
echo "Port: $PORT"
echo "Type: hex_respond"
```

---

## PROBE_*.json Format (Manual)

```json
{
  "banner_id": "lia-{taxonomy_lower}",
  "port_lab": 90XX,
  "probe_date": "2026-03-02T14:30:00Z",
  "probe_type": "tcp_init|tcp_respond|http|hex_respond",
  "host_tested": "172.30.0.33",
  "probe_status": "PASS|FAIL|PARTIAL",
  "banner_captured": "{banniere brute recue par probe.sh}",
  "banner_expected": "{banniere attendue depuis banner.json}",
  "match": true,
  "notes": "{details complementaires}"
}
```

## PROBE_*.json Format (Auto-generated by banner_menu.sh, 14 fields)

```json
{
  "id": "lia-cisco-ssh",
  "taxonomy": "CISC",
  "port": 9001,
  "type": "tcp_init",
  "probe_command": "bash probe.sh",
  "probe_result": "PASS",
  "probe_detail": "PASS: SSH-2.0-Cisco-1.25 detecte (banner_matcher OK)",
  "liaprobe_scan_id": 145,
  "liaprobe_taxonomy_detected": "CISC",
  "liaprobe_version": "1.25",
  "liaprobe_verdict": "PASS",
  "liaprobe_skip_reason": "",
  "verdict": "PASS",
  "date": "2026-03-02",
  "notes": ""
}
```

## Verdict Table

| Verdict | Condition | Signification |
|---------|-----------|---------------|
| `PASS` | probe=PASS ET liaprobe=PASS | Banner OK + LiaProbe detecte correctement |
| `PARTIAL_SCAN_SKIP` | probe=PASS ET liaprobe=SKIP | Banner OK mais LiaProbe n'a pas teste le port |
| `MISMATCH` | probe=PASS ET liaprobe=MISMATCH | Banner OK mais LiaProbe detecte une taxonomy differente |
| `WARN` | probe=WARN | Banner repond mais pattern attendu absent |
| `FAIL` | probe=FAIL | Pas de reponse ou mismatch complet |
| `PARTIAL` | autre combinaison | Resultat ambigu |

## FINGERPRINT_ANALYSIS.md Template

```markdown
# Analyse Fingerprint - {TAXONOMY}

## Banner capture

- Type: {tcp_init|tcp_respond|http|hex_respond}
- Port lab: {PORT}
- Source: `data/fingerprints/lia/{TAXONOMY}.json`
- Probe envoyee: `{commande ou hex trigger}`
- Banner recu: `{banniere exacte recue par probe.sh}`

## Fingerprint source

- Fichier : `data/fingerprints/lia/{TAXONOMY}.json`
- banner_matchers : [{liste des matchers}]
- ports : [{liste des ports dans le JSON}]
- layers : [{liste des layers}]

## Status detection LiaProbe

- Date: YYYY-MM-DD
- Status: DETECTED | NOT_DETECTED | PARTIAL | SKIP
- Methode attendue: banner_matcher | L7_HTTP | L4_TCP | L4_TCP_HEX
- Taxonomy detectee : {TAXONOMY} (ou N/A)
- Confidence obtenue : {score} (ou N/A)
- Scan ID : {scan_id} (ou N/A)

## Banner matchers requis

- {type=regex value=SSH-2\.0-Cisco}
- {type=contains value=Cisco}

## Notes protocole

- {Note specifique au protocole}
- {Note LiaProbe}

## Actions requises

- {Action si NOT_DETECTED}
- Aucune (si DETECTED avec confidence >= 0.60)
```

CRITICAL: Section names must match EXACTLY for generate_banner_readme.py parsing:
- `## Banner capture` (not "Banner brut capture")
- `## Status detection LiaProbe` (not "Status detection")
- `## Banner matchers requis`
- `## Notes protocole`
