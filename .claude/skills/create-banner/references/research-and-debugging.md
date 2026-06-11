# Research Sources and Debugging Reference

## Phase 0.0 - Source Research (MANDATORY)

### Fingerprint Database Research (data/fingerprints/)

```bash
# Search converted patterns for the target technology
grep -r '"type": "recog"' data/fingerprints/ --include="*.json" -l | grep -i "{technology_lower}"

# Extract content from a LIA fingerprint file
python3 -c "
import json
fp = json.load(open('data/fingerprints/lia/{TAXONOMY}.json'))
print('=== Sources ===')
for r in fp.get('research', []):
    if r.get('source', '').lower() == 'recog':
        print(f\"  URL: {r.get('url', 'N/A')}\")
        print(f\"  Evidence: {r.get('evidence', '')[:300]}\")
for bm in fp.get('banner_matchers', []):
    if bm.get('source', {}).get('type') == 'recog':
        print(f\"  Matcher: type={bm.get('type')} value={bm.get('value','')[:120]}\")
"
```

### GitHub Fingerprint Sources (by protocol)

TCP banners:
- ssh_banners.xml - SSH
- ftp_banners.xml - FTP
- smtp_banners.xml - SMTP
- telnet_banners.xml - Telnet
- irc_banners.xml - IRC

HTTP:
- http_headers.xml - All HTTP headers
- http_body.xml - HTTP body content

Databases:
- mssql_responses.xml - MSSQL
- oracle_tns.xml - Oracle
- ldap_searchresult.xml - LDAP

### Official Documentation Search

```bash
WebSearch: "{technology} official TCP banner format site:docs.{vendor}.com"
WebSearch: "{technology} SSH/FTP/HTTP banner specification RFC"
WebSearch: "{technology} service announcement protocol documentation"
```

Reference sources by protocol:
- SSH -> RFC 4253 Section 4.2
- FTP -> RFC 959 Section 4.1.2
- SMTP -> RFC 5321 Section 4.2
- POP3 -> RFC 1939 Section 3
- IMAP -> RFC 3501 Section 7.1
- HTTP -> Official product documentation

### RECOG_SOURCE.md Template

```markdown
# RECOG_SOURCE.md - Sources for {banner_id}

## Service
- Taxonomy : {TAXONOMY}
- Service : {service_description}
- Port banner-server : {PORT}

## Research Sources

### Fingerprint Database File
- File : xml/{file}.xml
- URL : (source URL)
- Pattern : `{pattern_regex}`
- Certainty : {certainty}

### Extract
(paste relevant XML/JSON extract)

## Official Documentation
- URL : {url_doc_officielle}
- Section : {section_pertinente}
- Format confirmed : {yes/no}

## Banner Selected
- Type : {tcp_init | tcp_respond | http | hex_respond}
- Value : `{banniere_exacte}`
- Justification : {why this banner represents the service}

## Validation
- [ ] Banner matches source pattern
- [ ] Banner matches official documentation
- [ ] Banner testable (probe.sh PASS expected)
- Date : {YYYY-MM-DD}
```

---

## Banner Verification by Protocol

### tcp_init formats

```
SSH : "SSH-2.0-{implementation}_{version}\r\n"
FTP : "220 {message}\r\n"
SMTP : "220 {hostname} ESMTP\r\n"
POP3 : "+OK {message}\r\n"
IMAP : "* OK {message}\r\n"
VNC : "RFB {version}\n"
IRC : ":{server} 001 {nick} :{welcome}\r\n"
```

### tcp_respond formats

```
Redis : trigger "PING\r\n" -> response "+PONG\r\n"
Memcache : trigger "stats\r\n" -> response "STAT pid...\r\nEND\r\n"
```

### http detection targets

```
Nginx : Server: nginx/{version}
Apache : Server: Apache/{version}
Grafana : X-Grafana-Version: {version}
Jenkins : X-Jenkins: {version}
Elasticsearch : body JSON with "tagline":"You Know, for Search"
IPP/CUPS : Server: TwistedWeb/{version} + HTTP 405 Method Not Allowed
```

### hex_respond handshakes

```
SOCKS5 : trigger 050100 -> response 0500
S7comm (Siemens) : trigger 0300001611e000... -> response 0300001611d0...
```

### Capture commands

```bash
# tcp_init
timeout 2 nc -w1 {HOST} {PORT}
# tcp_respond
printf "PING\r\n" | timeout 2 nc -w1 {HOST} {PORT}
# http
curl -si --connect-timeout 3 "http://{HOST}:{PORT}/"
# hex_respond
printf '\x05\x01\x00' | timeout 2 nc -w1 {HOST} {PORT} | xxd -p
```

---

## Debugging LiaProbe Detection

### Check pattern content

```bash
python3 -c "
import json
fp = json.load(open('data/fingerprints/lia/{TAXONOMY}.json'))
print('ports:', fp.get('ports', []))
print('layers:', fp.get('layers', []))
print('banner_matchers:', len(fp.get('banner_matchers', [])))
for m in fp.get('banner_matchers', []):
    print(f\"  {m}\")
"
```

### Common fixes

- `ports: []` empty -> add real service ports (22, 80, 443, etc.)
- `banner_matchers` absent -> add matchers for passive detection
- HTTP port not in `isHTTPPort()` -> check `cmd/sigma_web/discovery_scanner_engine.go`
- `layers: []` empty -> add appropriate layers (L4_TCP, L7_HTTP, L4_TCP_HEX, etc.)
- HTTP port absent from `PortServiceHints` -> add in `cmd/sigma_web/fingerprint_port_hints.go`

### PortServiceHints (CRITICAL for Fast Pass)

```go
// cmd/sigma_web/fingerprint_port_hints.go
901X:  {"taxonomy_hint"},   // Description - banner-server Discovery Lab COUCHE 5
```

Without this entry: pattern goes to broadCandidates (Pass 2 only).
With entry: pattern goes to fastCandidates (Pass 1, detected in fast AND thorough mode).

Hint value MUST match a substring of the taxonomy name. No spaces:
```go
// WRONG - space in value
9024: {"SQL Server"},   // Won't match "mssql" or "sqlserver"

// CORRECT - short lowercase
9024: {"sql"},          // Matches "mssql", "sql server", "sqlserver"
```

### globalPatternIndex: rebuild + restart MANDATORY

The `globalPatternIndex` is a singleton loaded at backend startup.
Modifying `data/fingerprints/lia/*.json` only takes effect after:
```bash
cd cmd/sigma_web && ./build_secure_lia.sh  # Rebuild binary
./cleanup_services.sh backend              # Restart backend
```

### HTTP_PROBE_FAILED diagnosis via PostgreSQL

```bash
psql_lia -t -A -c "SELECT message FROM unified_logs
  WHERE action='HTTP_PROBE_FAILED'
  AND created_at > NOW() - INTERVAL '30 minutes'
  ORDER BY created_at DESC LIMIT 10"
```

---

## Anti-Patterns

- NEVER edit banners.json directly (source of truth = banner_analysis/{id}/banner.json)
- NEVER use port range in scan API ("9001-9023" silently ignored, use CSV: "9001,9013,9014")
- NEVER create banner without probe.sh (proof of working)
- NEVER create banner without recette/ directory
- NEVER copy-paste a banner.json without adapting all fields
- NEVER use port outside range 9001-9099+
- NEVER use placeholder/TODO banners
- NEVER include `Transfer-Encoding: chunked` in http_headers (causes LiaProbe unexpected EOF)

## Lessons Learned

### Transfer-Encoding: chunked FORBIDDEN in http_headers
The banner-server injects Content-Length automatically. If banner.json also has Transfer-Encoding: chunked, both headers coexist causing EOF (RFC 7230 incompatibility).

### Version numbers
Avoid latest versions. Slightly outdated versions (nginx/1.24.0 vs latest) are more representative of real deployments.

### Batch workflow (5 agents x 3 banners)

For mass creation, Go modifications (fingerprint_port_hints.go + isHTTPPort()) should be done in ONE PASS after ALL agents finish. No intermediate rebuilds.

```bash
# 1. Check all banner_analysis/ created
ls docker/discovery-lab/banner-server/banner_analysis/ | wc -l
# 2. Update fingerprint_port_hints.go (all ports at once)
# 3. Update isHTTPPort() (HTTP ports only)
# 4. Rebuild backend (ONCE): cd cmd/sigma_web && ./build_secure_lia.sh
# 5. Restart: ./cleanup_services.sh backend
# 6. Rebuild banners.json: python3 scripts/tools/build_banners_json.py
# 7. Restart banner-server: cd docker/discovery-lab && docker rm -f lab-banner-server && docker-compose up -d --build banner-server
# 8. Parallel recette
```
