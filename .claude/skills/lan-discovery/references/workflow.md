# Workflow LAN Discovery CISO - Reference

## Pipeline complet

```
                    AUDIT CISO - PIPELINE DECOUVERTE
                    ==================================

 CLIENT fournit :            PHASE 1                PHASE 2
 - Plages IP              +----------+           +------------+
 - Perimetre autorise --->| SCAN     |---------->| INVENTAIRE |
                          | LiaProbe |           | UI/API     |
                          +----------+           +------------+
                          ~30s (fast)                  |
                          ~5min (thorough)             v
                                                +------------+
                                                |FINGERPRINT |
                                                | 15719 ptns |
                                                +------------+
                                                      |
                                                      v
                                                +------------+       +----------+
                                                | COLLECT    |------>| LIA-SCAN |
                                                | PS1/SH     |       | Engine   |
                                                +------------+       +----------+
                                                                          |
                                                                     Rapports RSSI
```

## Etape par etape

### Phase 0 : Prerequis

```bash
# Verifier que les services tournent
./cleanup_services.sh status

# Ports requis
# 8081 = Backend Go
# 3000 = Frontend React
# 5432 = PostgreSQL
```

### Phase 1 : Scan LiaProbe

```bash
# Lancer le scan
SCAN_ID=$(curl -s -X POST http://localhost:8081/api/discovery/scan/start \
  -H "Content-Type: application/json" \
  -d '{"targets":["10.0.0.0/24"],"scan_mode":"fast"}' | jq -r '.scan_id')

echo "Scan ID: $SCAN_ID"

# Attendre completion
while true; do
  STATUS=$(curl -s "http://localhost:8081/api/discovery/scan/status/$SCAN_ID" | jq -r '.status')
  echo "Status: $STATUS"
  [ "$STATUS" = "completed" ] && break
  sleep 5
done

# Recuperer les resultats
curl -s "http://localhost:8081/api/discovery/scan/results/$SCAN_ID" | jq '.assets | length'
```

### Phase 2 : Inventaire

Apres le scan, les assets sont automatiquement persistes dans `asset_inventory` (PostgreSQL).

```bash
# Vue globale
curl -s "http://localhost:8081/api/inventory/dashboard/summary" | jq .

# Liste des assets avec technologies
curl -s "http://localhost:8081/api/inventory/assets?sort_by=last_seen&sort_order=desc&limit=100" \
  | jq '.assets[] | {ip: .primary_ip, hostname: .primary_hostname, os: .os_name, techs: (.technologies | length)}'
```

**Tables PostgreSQL concernees :**
- `asset_inventory` - Assets decouverts
- `asset_services` - Ports/services par asset
- `asset_technologies` - Technologies identifiees (taxonomy_quadrigram)
- `asset_sources` - Source de la decouverte

### Phase 3 : Fingerprinting

Le fingerprinting enrichit `asset_technologies` avec les codes taxonomie LIA.

```bash
# Lancer le fingerprinting batch
curl -s -X POST http://localhost:8081/api/inventory/fingerprint/run | jq .

# Voir couverture audit par technologie
curl -s http://localhost:8081/api/inventory/dashboard/coverage | jq \
  '.items[] | select(.has_rules == true) | {tech: .taxonomy_code, assets: .asset_count}'
```

**Reload des patterns (hot reload sans recompilation) :**
```bash
curl -s -X POST http://localhost:8081/api/fingerprints/reload | jq .
```

### Phase 4 : Resolution scripts de collecte

Pour chaque asset avec des technologies identifiees :

```bash
# Recuperer tous les assets avec technologies
ASSETS=$(curl -s "http://localhost:8081/api/inventory/assets?limit=500" | jq -r '.assets[] | select(.technologies != null and (.technologies | length) > 0) | .id')

# Pour chaque asset, resoudre les scripts
for ASSET_ID in $ASSETS; do
  echo "=== Asset $ASSET_ID ==="
  curl -s -X POST "http://localhost:8081/api/inventory/assets/$ASSET_ID/launch-collection" \
    | jq '{ip: .asset_ip, scripts: [.scripts[].script_name], total: .total}'
done
```

### Phase 5 : LIA-Scan (apres collecte)

Une fois les scripts PS1/SH executes sur les cibles :

```bash
# Lancer le moteur LIA-Scan avec les donnees collectees
bin/lia_scan_engine \
  -multi \
  -rules lia_rules/rule_analysis/ \
  -events test_data.json \
  -quadrigramme <TECH> \
  -date $(date +%Y%m%d)
```

---

## Mapping technologies -> scripts de collecte

| Taxonomie | Repertoire collect | Type |
|-----------|-------------------|------|
| ADDS | `scripts/collect/active_directory/` | PS1 |
| WS22 | `scripts/collect/windows/` | PS1 |
| EXCH19 | `scripts/collect/exchange/` | PS1 |
| FORTIGATE | `scripts/collect/fortinet/` | PS1 |
| CISC | `scripts/collect/cisco/` | PS1 |
| CITR | `scripts/collect/citrix/` | PS1 |
| UB22 | `scripts/collect/ubuntu/` | SH |
| DOCK | `scripts/collect/docker/` | SH |
| POSTGRESQL | `scripts/collect/postgresql/` | SH |
| APACHE | `scripts/collect/apache/` | SH |
| GITLAB | `scripts/collect/gitlab/` | SH |
| GRAFANA | `scripts/collect/grafana/` | SH |
| K8S | `scripts/collect/kubernetes/` | SH |
| VMWA | `scripts/collect/vmware/` | PS1 |
| MSSQL | `scripts/collect/mssql/` | PS1 |
| SPLUNK | `scripts/collect/splunk/` | PS1/SH |
| ELASTIC | `scripts/collect/elastic/` | SH |
| JENKINS | `scripts/collect/jenkins/` | SH |
| ZABBIX | `scripts/collect/zabbix/` | SH |
| AWSC | `scripts/collect/aws/` | PS1/SH |
| AZURE | `scripts/collect/azure/` | PS1 |
| M365 | `scripts/collect/m365/` | PS1 |

---

## Troubleshooting

### Scan ne demarre pas
```bash
# Verifier backend
curl -s http://localhost:8081/api/health | jq .

# Verifier format cible (CIDR, IP ou FQDN obligatoire)
# Mauvais : "192.168.1.*"  Bon : "192.168.1.0/24"
```

### Technologies (0) apres scan
```bash
# Relancer le fingerprinting
curl -s -X POST http://localhost:8081/api/inventory/fingerprint/run | jq .

# Verifier les patterns charges
curl -s http://localhost:8081/api/fingerprints/patterns | jq length
```

### Scripts de collecte (0) apres launch-collection
```bash
# Verifier que l'asset a des technologies
curl -s http://localhost:8081/api/inventory/assets/<uuid> | jq '.technologies'

# Verifier le mapping taxonomy -> repertoire dans
# cmd/sigma_web/asset_inventory_collection.go (taxonomyToCollectDir map)

# Verifier que les scripts existent dans scripts/collect/
ls scripts/collect/active_directory/*.ps1
```

### Env variable pour surcharger le chemin des scripts
```bash
export LIA_SCRIPTS_PATH=/chemin/vers/scripts/collect
./sigma_web_backend
```
