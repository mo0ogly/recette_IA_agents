# Banner Inventory & Troubleshooting — COUCHE 5

## Inventaire complet (30 banners)

| Port | Banner ID | Taxonomy | Type | Categorie |
|------|-----------|----------|------|-----------|
| 9001 | lia-cisco-ssh | CISC | tcp_init | RESEAU |
| 9002 | lia-juniper-ssh | JUNI | tcp_init | RESEAU |
| 9003 | lia-openssh | OSSH | tcp_init | SSH_TELNET |
| 9004 | lia-hpilo | HPIL | tcp_init | RESEAU |
| 9005 | lia-vnc | VNC | tcp_init | SSH_TELNET |
| 9006 | lia-ftp | FTP | tcp_init | PROTOCOLES |
| 9007 | lia-smtp | SMTP | tcp_init | MAIL |
| 9008 | lia-pop3 | POP3 | tcp_init | MAIL |
| 9009 | lia-imap | IMAP | tcp_init | MAIL |
| 9010 | lia-telnet-fortigate | FORTI | tcp_init | RESEAU |
| 9011 | lia-irc | IRC | tcp_init | SSH_TELNET |
| 9012 | lia-memcache | MEMC | tcp_respond | PROTOCOLES |
| 9013 | lia-redis | REDIS | tcp_respond | PROTOCOLES |
| 9014 | lia-nginx | NGINX | http | WEB |
| 9015 | lia-apache | APACH | http | WEB |
| 9016 | lia-grafana | GRAFNA | http | WEB |
| 9017 | lia-jenkins | JENKINS | http | WEB |
| 9018 | lia-elasticsearch | ELAST | http | WEB |
| 9019 | lia-siemens-http | SIEM | http | ICS_SCADA |
| 9020 | lia-socks5 | PRXY | hex_respond | PROTOCOLES |
| 9021 | lia-paloalto | PALOA | http | RESEAU |
| 9022 | lia-fortinet-ssh | FORTI | tcp_init | RESEAU |
| 9023 | lia-zabbix | ZABBIX | http | WEB |
| 9024 | lia-mssql | MSSQL | hex_respond | PROTOCOLES |
| 9025 | lia-rdp | WINSV | hex_respond | PROTOCOLES |
| 9026 | lia-ldap | LDAP | hex_respond | PROTOCOLES |
| 9027 | lia-ipp | PRNT | http | PROTOCOLES |
| 9028 | lia-oracle | ORCL | hex_respond | PROTOCOLES |
| 9029 | lia-pjl-printer | PRNT | tcp_respond | PROTOCOLES |
| 9030 | lia-modbus | SCAD | hex_respond | ICS_SCADA |

**Ports HTTP COUCHE 5 (isHTTPPort()) :** 9014, 9015, 9016, 9017, 9018, 9019, 9021, 9023, 9027

---

## Causes frequentes de SKIP LiaProbe

| # | Symptome | Cause | Fix |
|---|---------|-------|-----|
| 1 | `LAYER_FILTER "Port XXXX: 0 candidates"` | pattern.json a `ports:[]` | Ajouter `"ports": [PORT_REEL, 9XXX]` dans `data/fingerprints/lia/{TAXONOMY}.json` |
| 2 | `LAYER_FILTER "Port 9014: 0 candidates"` (NGINX) | isHTTPPort() ne connait pas le port | Ajouter le port EXACT dans `discovery_scanner_engine.go` ~1285 |
| 3 | Pattern en broadCandidates -> SKIP fast | PortServiceHints[port] = nil | Ajouter hint dans `fingerprint_port_hints.go` |
| 4 | Pattern en broadCandidates malgre hint | `strings.Contains(productLower, hint)` echoue (espaces) | Utiliser sous-chaine simple : "sql" pas "sqlserver" |
| 5 | Fix JSON applique mais scan SKIP/FAIL | globalPatternIndex charge au demarrage | `build_secure_lia.sh` + `cleanup_services.sh backend` |
| 6 | `"Ignored invalid port '9001-9023'"` | API n'accepte PAS les ranges | CSV uniquement : `"9001,9002,9003"` |

---

## Validation d'un nouveau banner

### Etape 1 : Pattern LIA

```json
// data/fingerprints/lia/{TAXONOMY}.json
{
  "ports": [PORT_REEL, 9XXX],
  "probes": [{
    "id": "{taxonomy_lower}_root",
    "ports": [PORT_REEL, 9XXX],
    "matchers": [{"target": "header", "field": "Server", "match_type": "contains", "value": "{product}", "confidence_delta": 0.6}]
  }]
}
```

### Etape 2a : isHTTPPort() (http banners uniquement)

```go
// cmd/sigma_web/discovery_scanner_engine.go ~1285
case 9014, 9015, 9016, 9017, 9018, 9019, 9021, 9023, 9027:
    return true
```

### Etape 2b : PortServiceHints (Fast Pass)

```go
// cmd/sigma_web/fingerprint_port_hints.go
9XXX: {"keyword1", "keyword2"},
```

**Piege:** hints avec espaces. `"SQL Server"` ne matche pas `"sqlserver"`. Utiliser `"sql"`.

### Etape 3 : banner_state.json

```bash
python3 -c "
import json
with open('banner_state.json') as f: s = json.load(f)
s['lia-nouveau'] = True
with open('banner_state.json', 'w') as f: json.dump(s, f, indent=2, sort_keys=True)
"
```

### Etape 4 : REBUILD obligatoire

```bash
cd cmd/sigma_web && ./build_secure_lia.sh
./cleanup_services.sh backend
curl -s http://localhost:8081/api/health
cd docker/discovery-lab/banner-server && ./banner_menu.sh recette {id}
```

---

## Debug : PROBE JSON non cree

Si `banner_menu.sh recette` PASS mais fichier absent :

| Symptome Python | Cause bash | Fix |
|----------------|------------|-----|
| `NameError: name 'null'` | `echo 'null'` -> Python voit `null` | `echo 'None'` |
| `SyntaxError: unexpected character` | `echo '\"'$var'\"'` | `echo '"'$var'"'` |

Retirer `2>/dev/null` dans banner_menu.sh pour voir l'erreur.

---

## Integration Discovery Lab

```
Discovery Lab (172.30.0.0/24)
  172.30.0.10-.23  Services reels
  172.30.0.30      OpenCanary honeypot
  172.30.0.33      Banner-server (COUCHE 5)
```

Scan regression global : `cd docker/discovery-lab && ./lab.sh scan`
