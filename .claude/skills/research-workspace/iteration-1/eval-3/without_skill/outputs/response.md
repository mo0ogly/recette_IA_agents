# Reprise Discovery - Etat au 2026-03-02

## Contexte reconstitue depuis les sources

Oui, je me souviens de l'etat. Voici la synthese complete.

---

## Ce qui est TERMINE (VALIDATED)

### Fingerprinting Engine - LiaProbe (PRODUCTION-READY)
- **15 719 patterns JSON** actifs (20 LIA + 7945 Nmap + 1710 Recog + 886 Nuclei + 5158 Wappalyzer), 65 MB
- Layer filtering (ByLayer index) : reduction ~70-80% des evaluations
- Probe progressif fast/broad (Pass 1 top-10 hints, Pass 2 si < 0.80)
- Conversion 4 sources : scripts Python dans `scripts/tools/`
- Nmap supprime (750 LOC), LiaProbePlugin actif
- CPE23 migration, deduplication 695 doublons/UNKNOWN supprimes

### Discovery Lab - COUCHE 5 (30/30 BANNERS DETECTES)
- 30 banners banner-server (ports 9001-9030) : **detection 100%** (scan 145 + scan 148)
- 23/23 anciens banners : scan 145, 2026-03-02, thorough, 2.5s
- 7 nouveaux banners (9024-9030 : MSSQL/RDP/LDAP/IPP/ORACLE/PJL/MODBUS) : commit 3b82e8bfe5
- Recette formelle 30/30 avec PROBE JSON + verdict (commit 8eae40d4b2)
- Skills : `/create-banner` (v3.2) + `/recette-banner` (v2.2)

### Backend Discovery - Autres composants (PROD)
- LDAP/AD Discovery : operationnel
- CVE Processor : operationnel
- Asset Reconciler : operationnel
- WebSocket streaming temps reel : operationnel
- AI Enrichment : operationnel (warning SQLite non-bloquant connu)
- Discovery AI non-regression : 8/9 tests pass (commit 4061790e5c)

### CVE Pipeline API (DERNIER COMMIT)
- `cve_pipeline_api.go` ajoute au build
- Worker URL via `getCVEWorkerURL()` + env `CVE_WORKER_URL`
- Commit : `6020f012fd`

---

## Ce qui est EN ATTENTE (BACKLOG CRITIQUE)

### 1. CMDB Routes non enregistrees (CRITICAL)
- Tests 14 + 16 : HTTP 404 sur `/api/discovery/cmdb/assets` et `/api/discovery/cmdb/stats`
- Root cause : `RegisterCMDBRoutes()` probablement absent de `backend_8081.go`
- Fix estime : 10 min (3-4 lignes dans backend_8081.go)
- Fichiers : `discovery_routes_registry.go`, `discovery_cmdb.go`, `backend_8081.go`

### 2. UUID Validation manquante (CRITICAL)
- Test 16 : invalid UUID retourne HTTP 500 au lieu de 400
- Fix : ajouter `uuid.Parse(id)` check au debut des handlers
- Fichier : `discovery_scan_handler.go`

### 3. RegisterScanAIAnalysisRoutes non enregistree (HAUTE)
- `GET /api/discovery/scan/{id}/ai-recommendations` et `POST /api/discovery/scan/{id}/ai-chat` retournent 404
- `RegisterScanAIAnalysisRoutes` absent de `backend_8081.go`

### 4. Discovery -> Collect Bridge (CRITIQUE - Backlog long terme)
- Chainon manquant : detection asset -> lancement script de collecte PS1/SH
- 3 pistes definies : A (heuristique ports), B (table mapping PostgreSQL), C (UI manuelle)
- Choix d'approche non fait - decision utilisateur requise
- Effort : 2-14 jours selon piste

### 5. Inventaire UI CISO (CRITIQUE - Backlog)
- Tableau : IP / OS / Techno / Script dispo / Actions
- Non demarre

### 6. Collect Launcher (CRITIQUE - Backlog)
- Execution PS1/SH depuis backend Go
- Credential management
- Non demarre

---

## Tests API - Etat au 2026-03-01

| Test | Resultats | Status |
|------|-----------|--------|
| 14_test_discovery_phase2.sh | 15 PASS / 5 FAIL | 75% |
| 16_test_discovery_cmdb.sh | 3 PASS / 11 FAIL | 21% |
| 17_test_discovery_nmap_parallel.sh | 13 PASS / 1 FAIL | 93% |
| 19_test_discovery_ai_nonregression.sh | 8 PASS / 0 FAIL + 1 WARN | 89% |

Les 2 fails critiques (tests 14 + 16) sont dus aux routes CMDB non enregistrees.

---

## Ce qu'on a fait en dernier (2026-03-02)

La derniere session s'est focalisee sur la **COUCHE 5 du Discovery Lab** (banner-server) :
1. Detection 23/23 banners existants (scan 145, fix GRAFANA.json + PortServiceHints)
2. Creation 7 nouveaux banners 9024-9030 (commit 3b82e8bfe5)
3. Recette formelle 30/30 (commit 8eae40d4b2)
4. Skill `/recette-banner` v2.2 + `/create-banner` v3.2
5. Ajout CVE Pipeline API (commit 6020f012fd)

---

## Prochaine action recommandee

**Option A - Corriger les tests API Discovery (1-2h) :**
1. Fix CMDB routes dans `backend_8081.go` (10 min, Critical)
2. Fix UUID validation dans `discovery_scan_handler.go` (5 min, Critical)
3. Fix ADDS taxonomy dans `discovery_taxonomy_liaprobe.go` (20 min, High)
4. Fix input sanitization validate-target (15 min, Medium)
5. Objectif : passer Tests 14 et 16 a 100%

**Option B - Collect Bridge (choix d'approche d'abord) :**
Choisir piste A, B ou C pour le bridge Discovery->Collect avant de coder

**Option C - Inventaire UI CISO (frontend) :**
Tableau de bord des assets detectes, prerequis pour le CISO

Quelle direction prendre ?

---

## Fichiers cles

- Index discovery : `_alire/research_discovery/discovery/INDEX.md`
- Tracking banner : `_alire/tracking/BANNER_INTEGRATION_2026-03-02.md`
- Plan d'action : `_alire/tracking/DISCOVERY_ACTION_PLAN_2026-03-01.md`
- Audit technique : `_alire/tracking/DISCOVERY_AUDIT_2026-03-01.md`
- Code Go : `cmd/sigma_web/discovery_*.go`, `cmd/sigma_web/asset_*.go`
- Fingerprints : `data/fingerprints/` (15 719 JSON, 65 MB)
- Scripts collecte : `scripts/collect/` (100 repertoires)
