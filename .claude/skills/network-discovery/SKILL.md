# Network Discovery Skill - LAN Complete Scan

**Orchestrate a complete network discovery pipeline: Phase 1 (Host/Port Discovery) + Phase 2 (Technology Fingerprinting)**

## Problem Fixed

❌ **LiaProbe Backend** was broken:
- Scans returned 0 results
- Stuck at "running" state indefinitely
- Did NOT perform proper Phase 1 (host discovery)

✅ **This skill provides:**
- Phase 1: Complete host + port discovery (nmap)
- Phase 2: Technology identification (LiaProbe patterns)
- Unified inventory output

---

## TRACABILITE AGENTIQUE (OBLIGATOIRE)

### Plan persistant
Creer `_alire/tracking/PLAN_NETWORK_DISCOVERY_{NETWORK}_{YYYY-MM-DD}.md` (template: `_alire/tracking/PLAN_TEMPLATE.md`).

### Decision log
Logger dans `_alire/02_LOGS/Journals/decision_log.jsonl` les decisions non-triviales.
Format: `{"timestamp","session","action","reasoning","alternatives_rejected":[],"outcome","confidence","plan_ref"}`

### Replanification
Si 2 etapes echouent consecutivement → INVOQUER `/replan`.

### Scoring agentique (/50)
En fin de workflow, scorer sur : Decomposition, Planification, Replanification, Outillage dynamique, Tracabilite.

---

## Usage

```bash
/network-discovery <network> [options]
```

### Examples

```bash
# Full network scan 192.168.0.0/24
/network-discovery 192.168.0.0/24

# Verbose mode with service detection
/network-discovery 192.168.0.0/24 -sV

# Specific port range
/network-discovery 192.168.0.0/24 -p 22,80,443,3306,5432

# Large network (192.168.0.0/16)
/network-discovery 192.168.0.0/16

# Single host fingerprinting
/network-discovery 192.168.0.1 -A
```

---

## PHASE 1: Host & Port Discovery

Using `nmap` for reliable host detection:

```bash
nmap -v -sn 192.168.0.0/24              # Ping sweep - find all active IPs
nmap -p 1-10000 192.168.0.0/24           # Port scan on active IPs
nmap -sV -p- 192.168.0.1                 # Service detection on specific host
```

**Output:** List of active IPs + open ports + services

---

## PHASE 2: Fingerprinting with LiaProbe

For each IP:port found in Phase 1, apply LiaProbe patterns:

```bash
curl -X POST http://localhost:8081/api/discovery/fingerprint \
  -H "Content-Type: application/json" \
  -d '{"ip": "192.168.0.1", "port": 80, "service": "http"}'
```

Expected: Taxonomy + confidence + source (LIA/Nmap/Recog/etc)

---

## Output Format

```json
{
  "scan_summary": {
    "network": "192.168.0.0/24",
    "timestamp": "2026-03-06T22:30:00Z",
    "phase1_duration_sec": 45,
    "phase2_duration_sec": 120,
    "total_hosts_discovered": 7,
    "total_services_found": 15
  },
  "hosts": [
    {
      "ip": "192.168.0.1",
      "hostname": "router.local",
      "os": "Linux",
      "services": [
        {
          "port": 80,
          "protocol": "tcp",
          "service": "http",
          "version": "BusyBox 1.19.4",
          "taxonomy": "TPLINK",
          "confidence": 0.95,
          "source": "lia"
        }
      ]
    }
  ]
}
```

---

## Implementation Notes

**DO NOT use LiaProbe alone** - it has bugs:
- ❌ Discovery endpoint returns 0 results
- ❌ Scans hang at "running" state
- ❌ No proper host enumeration

**ALWAYS use 2-phase approach:**
1. **Phase 1 (nmap)** → Reliable host/port discovery
2. **Phase 2 (LiaProbe)** → Technology identification on known services

---

## Backend Issues to Fix (discovery_scanner_engine.go)

1. **broadPassMaxCandidates** limiting results
2. **tcpConnect()** filtering non-printable chars (breaks binary protocols)
3. **Shared timeout context** blocking subsequent probes
4. **Missing probe matchers** for target:"banner"

See `_alire/tracking/BANNER_SERVER_WAVES_2026-03-06.md` for architectural bugs.

---

## Quick Reference

| Command | What It Does |
|---------|------------|
| `nmap -sn 192.168.0.0/24` | Find all active hosts (ping sweep) |
| `nmap -p- 192.168.0.1` | Scan ALL ports on single host |
| `nmap -sV -p 80,443 192.168.0.0/24` | Detect services on ports 80,443 |
| `/network-discovery 192.168.0.0/24` | Full 2-phase scan (this skill) |

---

**Status:** ACTIVE - Ready for production use
**Author:** LIA-SEC Platform
**Version:** 1.0
