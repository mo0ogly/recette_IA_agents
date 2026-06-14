# Reprise Discovery - Etat du travail

**Contexte compresse. Relecture complete effectuee (9 etapes REGLE ABSOLUE N.0).**

---

## Annonce formelle (etape 9)

**Phase actuelle : Phase 5 (Implementation) - PARTIELLE**
**Gate bloquante : Tests 14 et 16 CRITIQUES (CMDB routes non enregistrees)**
**Decisions utilisateur respectees :**
1. Scanner reseau AUTONOME (pas un complement Nmap) - DONE
2. Option A extension moteur existant - PARTIEL (Option B livree mais decouplee)
3. Parser TOUT (pas de filtre taxonomie) - DONE
4. Nomenclature LIA (LiaProbe, LiaPattern) - DONE
5. Vecteur L_FILE - BACKLOG (pas encore implemente)
6. Pas de $SUBST/$P/$I (format JSON propre) - DONE
7. Subdomain Discovery via crt.sh - DONE

---

## Ou on en etait - Resume complet

### Ce qui est VALIDE et operationnel

Le Fingerprinting Engine LiaProbe est en production avec :
- **15 719 patterns** (20 LIA + 7945 Nmap + 1710 Recog + 886 Nuclei + 5158 Wappalyzer), 65 MB
- **9 fichiers Go** : scanner engine, model, loader, probe executor, matcher, API, plugins, taxonomy
- **Scan #148** : 30/30 banners COUCHE 5 detectes (100%)
- Migration Nmap complete (14 fichiers supprimes, 0 regression frontend)
- Probe progressif fast/broad (Pass 1 top-10 hints, Pass 2 broad si < 0.80 ou mode thorough)
- Layer filtering (70-80% reduction evaluations sur ports non-HTTP)
- Discovery Lab COUCHE 5 : 30 banners (9001-9030) tous valides

Commits cles : d0ba5ebdfb, 867b2d780e, f3a78163e4, 79cff8c8b9, 0a8130d468, cc4b01ef3d, 1f71e0d673, 82d3f4cdd3, 3b82e8bfe5, 8eae40d4b2

### Ce qui est BLOQUE (gate actuelle)

**Tests API (2026-03-01) :**
- Test 14 : 15 PASS / 5 FAIL (75%) - EXIT=1 CRITICAL
- Test 16 : 3 PASS / 11 FAIL (21%) - EXIT=1 CRITICAL
- Test 17 : 13 PASS / 1 FAIL (93%) - EXIT=0
- Test 19 : 8 PASS / 0 FAIL + 1 WARN (89%) - EXIT=0

**Cause racine des echecs critiques :**
1. CMDB routes non enregistrees dans `backend_8081.go` → GET /api/discovery/cmdb/assets retourne HTTP 404
2. UUID validation manquante → retourne HTTP 500 au lieu de 400
3. ADDS taxonomy mismatch pour ldap:389

**RegisterScanAIAnalysisRoutes absent** de `backend_8081.go` → ai-recommendations + ai-chat retournent 404

### Backlog CRITIQUE (non demarre)

| Fonctionnalite | Priorite | Effort estime |
|----------------|----------|---------------|
| CMDB routes registration fix | CRITIQUE | 10 min |
| UUID validation fix | CRITIQUE | 5 min |
| ADDS taxonomy fix | HAUTE | 20 min |
| RegisterScanAIAnalysisRoutes | HAUTE | 15 min |
| Discovery -> Collect Bridge | CRITIQUE | 2 jours, 6 endpoints |
| Inventaire UI CISO | CRITIQUE | 4 jours |
| Collect Launcher (PS1/SH) | CRITIQUE | 8 jours |
| Vecteur L_FILE | MOYENNE | non estime |

### Questions ouvertes non resolues

1. Quelle approche pour le Collect Launcher ? (Piste A/B/C dans backlog)
2. Comment stocker les credentials de maniere securisee ?
3. L'orchestrateur scan -> mapping -> UI -> collect est-il un composant separe ?

---

## Prochaine action recommandee

**Action 1 (10 min, CRITIQUE) :** Enregistrer les routes CMDB dans `backend_8081.go`
```go
router.HandleFunc("/api/discovery/cmdb/assets", discoveryHandler.ListAssets).Methods("GET")
router.HandleFunc("/api/discovery/cmdb/assets/{id}", discoveryHandler.GetAsset).Methods("GET")
router.HandleFunc("/api/discovery/cmdb/assets/{id}/history", discoveryHandler.AssetHistory).Methods("GET")
router.HandleFunc("/api/discovery/cmdb/stats", discoveryHandler.GetCMDBStats).Methods("GET")
```

**Objectif immediat :** Passer Test 14 et 16 a 100% PASS pour debloquer la gate Phase 5.

**Apres correction Tests 14/16/17/19 a 100% :** Demarrer le Discovery -> Collect Bridge (backlog CRITIQUE, 2 jours).

---

## Fichiers de reference

- Tracking principal : `_alire/tracking/FINGERPRINTING_ENGINE_2026-02-28.md`
- Action plan detaille : `_alire/tracking/DISCOVERY_ACTION_PLAN_2026-03-01.md`
- Audit complet : `_alire/tracking/DISCOVERY_AUDIT_2026-03-01.md`
- INDEX sujet : `_alire/research_discovery/discovery/INDEX.md`
- Synthese recherche : `_alire/research_discovery/discovery/investigated/2026-02-28_SYNTHESE-RECHERCHE-FINGERPRINTING.md`
