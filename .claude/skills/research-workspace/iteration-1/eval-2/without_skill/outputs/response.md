# Etat complet de la recherche - Module Discovery

**Source :** `_alire/research_discovery/` (INDEX.md, RESEARCH_LOG.md, discovery/INDEX.md)
**Date du rapport :** 2026-03-02

---

## Status global

**VALIDATED - Production-ready**

Le Fingerprinting Engine (LiaProbe) est operationnel comme scanner reseau autonome. 15 719 patterns actifs (4 sources), probe progressif fast/broad, layer filtering 70-80%, lab 30/30 detection.

---

## Ce qui est VALIDE (fonctionne, avec preuve)

| Fonctionnalite | Fichier(s) | Date | Commit |
|----------------|-----------|------|--------|
| LiaProbe scanner autonome (subdomain crt.sh + TCP connect + probes + fingerprinting + PostgreSQL) | `discovery_scanner_engine.go` | 2026-02-28 | d0ba5ebdfb |
| Migration Nmap -> LiaProbe complete (~750 LOC mort supprime, frontend mis a jour) | Multiple | 2026-02-28 | 867d2d780e |
| 15 719 patterns JSON (20 LIA + 7945 Nmap + 1710 Recog + 886 Nuclei + 5147 Wappalyzer), 65 MB | `data/fingerprints/` | 2026-03-01 | Multiple |
| Fingerprint loader (normalizePattern, priorite ByTaxonomy, CPE23, 28 doublons supprimes) | `fingerprint_pattern_loader.go` | 2026-03-01 | 0a8130d468 |
| Probe progressif fast/broad (PortServiceHints 47 mappings, Pass1 top10, Pass2 si echec) | `fingerprint_port_hints.go` | 2026-03-01 | 82d3f4cdd3 |
| Layer filtering (ByLayer index, 70-80% reduction evaluations sur ports non-HTTP) | Loader + matcher | 2026-03-01 | 1f71e0d673 |
| Conversion Nmap service-probes -> 7945 JSON LIA | `scripts/tools/convert_nmap_probes_to_lia.py` | 2026-03-01 | 1f71e0d673 |
| Conversion Nuclei templates -> 886 JSON LIA | `scripts/tools/convert_nuclei_to_lia.py` | 2026-03-01 | 1f71e0d673 |
| Audit qualite + cleanup (695 doublons/UNKNOWN supprimes) | - | 2026-03-01 | cc4b01ef3d |
| Plugin architecture (ScannerPlugin interface) | `discovery_plugin_interface.go`, `discovery_plugin_liaprobe.go` | 2026-02-28 | aa560ac9ab |
| CMDB PostgreSQL (asset_inventory, change_history) | `discovery_cmdb.go`, `asset_inventory_db.go` | 2026-02-26 | 83121b08ad |
| AD/LDAP Discovery | `discovery_ldap.go`, `discovery_plugin_ldap.go` | 2026-02-26 | - |
| CVE Processor (service -> CVE linking) | `discovery_cve_processor.go` | 2026-02-26 | - |
| Asset reconciler + change tracking | `asset_reconciler.go` | 2026-02-26 | - |
| WebSocket streaming temps reel | `discovery_scan_handler.go` | avant 2026-02-26 | - |
| Discovery Lab COUCHE 5 (30 banners, 30/30 detection 100%) | `docker/discovery-lab/` | 2026-03-02 | 3b82e8bfe5 |
| Import XML Nmap externe (conserve) | `ingester_nmap.go` | avant 2026-02-26 | - |
| Discovery AI non-regression (DEFAUT_001 SQL `?`->`$1`, prompts PostgreSQL, 9 tests non-reg) | `discovery_ai_wrapper.go`, `ai_prompt_templates_postgres.go` | 2026-03-01 | 4061790e5c |

---

## Ce qui est ABANDONNE (ne pas re-essayer)

| Fonctionnalite | Raison | Date |
|----------------|--------|------|
| WMI Discovery | Code incomplet, non teste, credentials JSON non securises. Remplace par LDAP. | 2026-02-26 |

---

## BACKLOG - Ce qui reste a faire

### Critique (bloque le pipeline E2E)

| Item | Pistes disponibles | Effort estime |
|------|-------------------|---------------|
| **Discovery -> Collect Bridge** | Piste A (heuristique ports), B (table PostgreSQL configurable), C (UI manuelle + suggestion). Choix utilisateur requis avant de coder. | Piste A: 2-3j / B: 1 sem / C: 5-7j |
| **Inventaire UI (tableau CISO)** | Non demarre. Tableau: IP / OS / Techno / Script dispo / Actions | - |
| **Collect Launcher (execution PS1/SH)** | Non demarre. exec.Command via SSH/WinRM ou agent ou copier-coller | - |

### Haute priorite

| Item | Status |
|------|--------|
| RegisterScanAIAnalysisRoutes non enregistree (ai-recommendations + ai-chat retournent 404, absent de backend_8081.go) | Non demarre |
| Cloud AWS/Azure | Non demarre |
| Kubernetes/Docker | Non demarre |
| Unit tests >70% | Non demarre |

### Moyenne priorite

| Item | Status |
|------|--------|
| SNMP discovery | Non demarre |
| NetBIOS/VMware | Non demarre |

### Hors scope (pour rappel)

- Completion scripts de collecte (142 taxonomies vs 100 repertoires) - traite par skill `/create-collect-script`

---

## Pipeline cible (architecture)

```
[CISO : plages IPs]
      |
[1. SCAN + IDENTIFICATION]  <- FAIT (LiaProbe, 15 719 patterns, 30/30 lab)
      |
[2. INVENTAIRE UI]          <- A CREER (tableau CISO)
      |
[3. VALIDATION CISO]        <- Action humaine UI
      |
[4. COLLECT LAUNCHER]       <- A CREER (exec PS1/SH via SSH/WinRM)
      |
[5. ANALYSE]                <- EXISTE (moteur LIA-Scan, 9000+ regles YAML)
      |
[6. RAPPORTS]               <- EXISTE (ReportRules JSON + remediation)
```

Etapes 1, 5 et 6 sont operationnelles. Etapes 2, 3 et 4 restent a construire.

---

## Questions ouvertes bloquantes

1. **[CRITIQUE]** Quelle approche pour le Collect Launcher ? (Piste A/B/C - voir `backlog/discovery-to-collect-bridge.md`)
2. **[CRITIQUE]** Comment stocker les credentials de maniere securisee ?
3. **[HAUTE]** Le taxonomy_mapper couvre 28 technos. Comment etendre aux 142 taxonomies ?
4. **[HAUTE]** L'orchestrateur (scan -> mapping -> UI -> collect -> analyse) est-il un composant separe ?

---

## Chiffres cles (etat au 2026-03-02)

- Patterns fingerprint : **15 719** (20 LIA + 7945 Nmap + 1710 Recog + 886 Nuclei + 5147 Wappalyzer), 65 MB
- Detection lab banner-server COUCHE 5 : **30/30 (100%)**
- Scan lab #131 : 15/24 services en 164s (fast mode)
- Taxonomies LIA regles : 142
- Scripts de collecte : 100 repertoires
- Regles YAML : 9000+
- Commits fingerprinting : 10+

---

## Fichiers de reference

- Index principal : `_alire/research_discovery/discovery/INDEX.md`
- Journal : `_alire/research_discovery/RESEARCH_LOG.md`
- Doc ingenierie v2.0 : `_alire/research_discovery/discovery/investigated/2026-03-01_DOCUMENTATION-INGENIERIE-FINGERPRINTING-ENGINE-v2.md`
- Synthese recherche : `_alire/research_discovery/discovery/investigated/2026-02-28_SYNTHESE-RECHERCHE-FINGERPRINTING.md`
- Tracking : `_alire/tracking/FINGERPRINTING_ENGINE_2026-02-28.md`
- Backlog bridge : `_alire/research_discovery/discovery/backlog/discovery-to-collect-bridge.md`
