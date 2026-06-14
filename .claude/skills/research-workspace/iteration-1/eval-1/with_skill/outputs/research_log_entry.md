# RESEARCH_LOG.md - Entree de cloture

**Fichier cible :** `_alire/research_discovery/RESEARCH_LOG.md`
**Position :** A inserer EN TETE du journal (apres le header), section ## 2026-03-02

---

## Entree a ajouter dans RESEARCH_LOG.md

```markdown
## 2026-03-02 (suite - cloture banner-server COUCHE 5)

- `[DISCOVERY]` `[VALIDATED]` - **COUCHE 5 banner-server : 30/30 banners detectes. Production. Commit 3b82e8bfe5.**
  - Banners 9001-9023 (23 banners) : 23/23 detection LiaProbe (scan #145, 100%). Commit 3b82e8bfe5.
  - Banners 9024-9030 (7 banners) : 7/7 detection LiaProbe (scan #148, 100%). Commit 3b82e8bfe5.
  - Recette formelle 30 PROBE JSON avec verdict + liaprobe_taxonomy : commit 8eae40d4b2.
  - Fixes moteur necessaires : GRAFANA probe grafana_root (GET /), PortServiceHints 9014-9023,
    isHTTPPort granulaire (8 ports HTTP uniquement), fix null->None Python banner_menu.sh.
  - Nouveaux banners (9024-9030) : MSSQL/TDS-PreLogin, WINSV/RDP-X224, LDAP/BindResponse,
    PRNT/IPP-TwistedWeb, ORCL/TNS-Refuse, PRNT/PJL, SCAD/MODBUS.
  - Skill /create-banner SKILL.md mis a jour (commit e1ec663fb5).
  - banner_state.json : 30 entrees, etat sync production.
  - RECETTE_INDEX.md mis a jour dans docker/discovery-lab/recette/ (scan #148 reference).
  - Piege PortServiceHints : hint "sqlserver" ne match PAS "SQL Server" (espace). Utiliser "sql".
  - Piege globalPatternIndex : modifier un JSON fingerprint -> REBUILD + RESTART obligatoire.
  - Piege API : ports doit etre CSV "9024,9025" et non range "9024-9030" (range ignore).
  - BACKLOG : skill /recette-banner v2, SOCKS5/IRC (honeypots indetectables par conception).

- `[DISCOVERY]` `[VALIDATED]` - **Skill /create-banner v2.2 livre. Commit e1ec663fb5.**
  - SKILL.md mis a jour avec section recette, globalPatternIndex warning, isHTTPPort patterns.
  - banner_state.json : 30 entrees synchronisees.
```

---

**Tags utilises :**
- `[VALIDATED]` : element confirme en production (commits + scans LiaProbe)
- `[DISCOVERY]` : scope module discovery
