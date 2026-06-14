# Etat de la Recherche - Module Discovery

**Date :** 2026-03-02
**Source :** Referentiel `_alire/research_discovery/discovery/`
**Methode :** Research Skill v2.3 - workflow `/research [topic]`

---

## Etat Global

**Topic :** Discovery - Identification des Assets Reseau
**Phase actuelle :** Phase 6 - DOCUMENTATION FINALE (engineering doc v2.0 ecrite)
**Status :** VALIDATED - LiaProbe scanner autonome operationnel et optimise

Le module Discovery a atteint son objectif principal : le **Fingerprinting Engine (LiaProbe)** est un scanner reseau autonome qui remplace completement Nmap, ProjectDiscovery et TechnologyFingerprinter. Il identifie les technologies reseau via des probes actifs (HTTP/TCP/TLS) et 15 719 patterns JSON issues de 4 sources.

---

## Pipeline Cible

```
[CISO : "voici mes plages IPs"]
       |
  [1. SCAN + IDENTIFICATION]  -- VALIDATED : LiaProbe (scanner autonome)
       |
  [2. INVENTAIRE UI]          -- BACKLOG CRITIQUE : tableau IP/OS/Techno/Scripts
       |
  [3. VALIDATION CISO]        -- BACKLOG : action humaine UI
       |
  [4. COLLECT LAUNCHER]       -- BACKLOG CRITIQUE : execute PS1/SH avec credentials
       |
  [5. ANALYSE]                -- EXISTE : moteur LIA-Scan + 9000+ regles YAML
       |
  [6. RAPPORTS]               -- EXISTE : ReportRules JSON + remediation
```

Etapes 1, 5, 6 operationnelles. Etapes 2, 3, 4 = backlog critique.

---

## VALIDATED (fonctionne en production, avec preuve)

| Fonctionnalite | Commits cles | Date |
|---|---|---|
| LiaProbe scanner autonome (subdomain crt.sh + TCP connect + probes + fingerprinting + PostgreSQL) | d0ba5ebdfb | 2026-02-28 |
| Migration Nmap -> LiaProbe complete (14 fichiers Go supprimes, ~750 LOC mort) | d0ba5ebdfb + 867b2d780e | 2026-02-28 |
| Discovery Lab 14/14 = 100% identification (fix base_confidence 0.0->0.5) | b89322aec4 | 2026-02-28 |
| 15 719 patterns fingerprint (20 lia + 7945 nmap + 1710 recog + 886 nuclei + 5158 wappalyzer, 65 MB) | 1f71e0d673 + cc4b01ef3d + 0a8130d468 + 79cff8c8b9 + f3a78163e4 | 2026-03-01 |
| Layer filtering (~70-80% reduction evaluations sur ports non-HTTP) | 1f71e0d673 | 2026-03-01 |
| Probe progressif fast/broad (47 PortServiceHints, Pass 1 stop si confidence >= 0.80) | 82d3f4cdd3 | 2026-03-01 |
| CMDB PostgreSQL (asset_inventory, change_history) | 83121b08ad | 2026-02-26 |
| AD/LDAP Discovery | aa560ac9ab | 2026-02-26 |
| CVE Processor (service -> CVE linking) | - | 2026-02-26 |
| Plugin architecture (ScannerPlugin interface) | aa560ac9ab | 2026-02-26 |
| WebSocket streaming temps reel | - | avant 2026-02-26 |
| Import XML Nmap externe (ingester_nmap.go conserve) | - | avant 2026-02-26 |
| Discovery AI non-regression (DEFAUT_001 corrige, prompts PostgreSQL, 9 tests) | 4061790e5c | 2026-03-01 |
| Documentation Ingenierie v2.0 (6 diagrammes Mermaid, Phase 5 DONE) | sans commit (doc only) | 2026-03-01 |

**Chiffres cles du scanner :**
- 15 719 patterns JSON (4 sources : LIA, Nmap, Recog, Nuclei, Wappalyzer)
- 65 MB de fingerprints
- 7 scripts Python de conversion (Wappalyzer, Recog, Nmap, Nuclei, migrate_cpe23, find/resolve_duplicates)
- 10 fichiers Go (scanner, model, loader, probes, matcher, API, plugin, liaprobe, taxonomy, port_hints)
- Priorite sources : lia(100) > nmap(80) > recog(60) > nuclei(50) > wappalyzer(40)

---

## INVESTIGATED (explore, resultats documentes, pas definitif)

| Element | Verdict |
|---|---|
| ProjectDiscovery Docker integration | Bon code, isole du pipeline - non connecte |
| Taxonomy Mapper (28 mappings service -> LIA-Scan) | Pivot central a connecter au bridge |
| Panorama outils ASM (PD, Siemens GoScans) | Analyse complete, decision : scanner autonome |
| Fingerprinting engine 4 moteurs (Wappalyzer/Recog/Nuclei/Nmap) | RE complete, 4 rapports dans investigated/ |
| Gaps utilisateurs (Evidence Gap Matrix) | LIA adresse 6/9 gaps. Hors scope : SPA/JS, CDN, IoT |
| Non-regression frontend (28 composants, 22 routes) | Matrice complete : 4 routes critiques reimplementees |

---

## ABANDONED (ne pas re-essayer sans lire pourquoi)

| Element | Raison | Date |
|---|---|---|
| WMI Discovery | Code incomplet, non teste, credentials JSON non securises. Remplace par LDAP. | 2026-02-26 |

---

## BACKLOG (par priorite)

| Fonctionnalite | Priorite | Status |
|---|---|---|
| **Inventaire UI CISO** (tableau IP/OS/Techno/Scripts) | CRITIQUE | Non demarre |
| **Collect Launcher** (execute PS1/SH avec credentials depuis inventaire) | CRITIQUE | Non demarre |
| **Discovery -> Collect Bridge** (chainon manquant : asset detecte -> script collecte) | CRITIQUE | Pistes A/B/C definies |
| **RegisterScanAIAnalysisRoutes non enregistree** (ai-recommendations + ai-chat = 404) | HAUTE | Non demarre |
| Cloud AWS/Azure | HAUTE | Non demarre |
| Kubernetes/Docker | HAUTE | Non demarre |
| Vecteur L_FILE (detection par fichiers systeme) | HAUTE | Non demarre |
| Unit tests >70% | HAUTE | Non demarre |
| SNMP | MOYENNE | Non demarre |
| Bridge compareValues() (fingerprint_matcher -> pkg/engine) | MOYENNE | Non demarre |
| Scripts collecte completion (142 taxonomies vs 100 dirs) | HAUTE | HORS SCOPE |

---

## Questions Ouvertes (non resolues)

1. **[CRITIQUE]** Quelle approche pour le Collect Launcher ? Pistes A (heuristique ports), B (table PostgreSQL configurable), C (UI manuelle avec suggestion). Choix utilisateur requis AVANT de coder.
2. **[CRITIQUE]** Comment stocker les credentials de maniere securise ? (SSH keys, WinRM, API tokens)
3. **[HAUTE]** Le taxonomy_mapper couvre 28 technos. Comment etendre aux 142 taxonomies LIA ?
4. **[HAUTE]** Faut-il un orchestrateur separe (scan -> mapping -> UI -> collect -> analyse) ?

---

## Ce qui bloque le pipeline complet

Le scanner (etape 1) est production-ready. La chaine de valeur complete est bloquee par :

1. **Inventaire UI** : le CISO ne peut pas voir les assets decouverts de maniere exploitable
2. **Collect Bridge** : aucun lien entre les assets detectes et les 100 scripts de collecte existants
3. **Collect Launcher** : aucun mecanisme pour declencher les PS1/SH avec credentials

Les etapes 5 et 6 (analyse LIA-Scan + rapports) existent et sont matures (9000+ regles, 142 taxonomies). Le gap est dans la connexion discovery <-> collecte.

---

## Fichiers de Reference

- `_alire/research_discovery/discovery/INDEX.md` : source de verite
- `_alire/research_discovery/discovery/investigated/2026-03-01_DOCUMENTATION-INGENIERIE-FINGERPRINTING-ENGINE-v2.md` : doc ingenierie v2.0 (6 diagrammes)
- `_alire/research_discovery/discovery/backlog/discovery-to-collect-bridge.md` : detail pistes A/B/C
- `_alire/tracking/FINGERPRINTING_ENGINE_2026-02-28.md` : journal complet implementation
- `_alire/research_discovery/RESEARCH_LOG.md` : journal chronologique toutes sessions
