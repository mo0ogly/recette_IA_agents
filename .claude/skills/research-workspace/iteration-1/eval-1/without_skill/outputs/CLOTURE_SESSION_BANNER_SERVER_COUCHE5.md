# Cloture Session Research Discovery - Banner-Server COUCHE 5

**Date :** 2026-03-02
**Sujet :** Discovery - Banner-Server COUCHE 5 (ports 9001-9030)
**Commit de reference :** 3b82e8bfe5
**Resultat :** 30/30 banners detectes par LiaProbe (100%)

---

## Ce qui a ete accompli

### COUCHE 5 Banner-Server - Etat FINAL

La couche 5 du Discovery Lab est completement terminee et en production depuis le commit `3b82e8bfe5`.

**30 banners implantes :** ports 9001-9030 sur le conteneur `172.30.0.33`

Types de banners :
- `tcp_init` : le serveur envoie une banniere a la connexion
- `tcp_respond` : le serveur repond a un payload specifique
- `http` : reponses HTTP avec headers caracteristiques
- `hex_respond` : reponses en format hexadecimal (protocoles binaires)

**Banners 9001-9023 (DONE, scan #145) :**
- Technologies : Nginx, Apache, Redis, MySQL, PostgreSQL, SSH OpenSSH, FTP vsftpd, SMTP Postfix, Memcached, MongoDB, Elasticsearch, RabbitMQ, Grafana, Prometheus, Jenkins, Tomcat, Zabbix, IMAP Dovecot, POP3 Dovecot, OpenVPN, SNMP, VNC, Telnet

**Banners 9024-9030 (DONE, scan #148) :**
- 9024 : MSSQL (TDS PreLogin response)
- 9025 : WINSV/RDP (X.224 Connection Confirm)
- 9026 : LDAP (BindResponse ASN.1)
- 9027 : PRNT/IPP (TwistedWeb HTTP 405)
- 9028 : ORCL (TNS Refuse)
- 9029 : PRNT/PJL (Printer Job Language)
- 9030 : SCAD/MODBUS (Modbus exception response)

### Recette formelle

**30/30 fichiers PROBE JSON** avec `verdict` + `liaprobe_taxonomy` dans `docker/discovery-lab/recette/`.
RECETTE_INDEX.md mis a jour : `docker/discovery-lab/recette/RECETTE_INDEX.md`

### Fixes LiaProbe associes

- `isHTTPPort()` : ajout des ports 9001-9023 pour que LiaProbe envoie des probes HTTP
- `PortServiceHints` : ajout de mappings pour les ports 9014-9023
- Probe `grafana_root` : ajout pour detection Grafana via HTTP
- Detection IPP : matcher `header.Server contains TwistedWeb` dans probe `ipp_cups_web`
- `banners.json` : regenere via `scripts/tools/build_banners_json.py`

### Pieges documentes (pour eviter regression)

1. **globalPatternIndex** : modifier un JSON fingerprint -> REBUILD + RESTART obligatoire. Sans ca, les nouvelles probes ne sont pas chargees.
2. **PortServiceHints piege** : hint `"sqlserver"` ne match PAS `"SQL Server"` (espace). Utiliser `"sql"`.
3. **API ports format** : utiliser CSV `"9024,9025"` et NON range `"9024-9030"` (le range est ignore).

---

## Artefacts en production

| Artefact | Chemin | Status |
|----------|--------|--------|
| Banner definitions | `docker/discovery-lab/banner_analysis/{id}/banner.json` | DONE |
| Probe scripts | `docker/discovery-lab/banner_analysis/{id}/probe.sh` | DONE |
| Recette JSON | `docker/discovery-lab/recette/*.json` | 30 fichiers DONE |
| Recette index | `docker/discovery-lab/recette/RECETTE_INDEX.md` | DONE |
| banners.json | `docker/discovery-lab/banners.json` | DONE (genere) |
| LiaProbe fixes | `cmd/sigma_web/fingerprint_*.go` | DONE |

---

## Commits cles

- `3b82e8bfe5` : feat(banner): 30/30 COUCHE 5 - 7 nouveaux banners 9024-9030
- `8eae40d4b2` : fix(banner/recette): fix PROBE JSON write - null->None + guillemets Python
- `5272136a11` : fix(skill/recette-banner): v2.1 - globalPatternIndex + PortServiceHints + isHTTPPort

---

## Entree RESEARCH_LOG.md a ajouter (reference)

```
## 2026-03-02

- `[DISCOVERY]` `[VALIDATED]` - **Banner-Server COUCHE 5 complete. 30/30 banners detectes. Commit 3b82e8bfe5.**
  - 30 banners sur ports 9001-9030 (172.30.0.33)
  - Scan #148 : 30/30 detection LiaProbe (100%)
  - Recette formelle : 30 PROBE JSON avec verdict + liaprobe_taxonomy
  - Fixes : isHTTPPort (9001-9023) + PortServiceHints + probe grafana_root + IPP TwistedWeb matcher
  - Pieges documentes : globalPatternIndex rebuild, hint sans espace, ports CSV pas range
  - SESSION CLOSE : COUCHE 5 terminee, production-ready.
```

---

## Prochaine etape suggere

La COUCHE 5 est close. Les items ouverts dans le backlog Discovery restent :
- Discovery -> Collect Bridge (`backlog/discovery-to-collect-bridge.md`) - CRITIQUE
- Inventaire UI (tableau CISO) - CRITIQUE
- Collect Launcher (PS1/SH execution) - CRITIQUE
- RegisterScanAIAnalysisRoutes non enregistree (ai-recommendations retournent 404) - HAUTE
