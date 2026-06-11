# Quality Gate - Validation par port

Gate BLOQUANT : un port ne passe pas tant que TOUTES les conditions ne sont pas verifiees.

## Checklist (TOUTES obligatoires)

```
[ ] DETECTION : la bonne techno est le service avec la plus haute confidence
[ ] CONFIDENCE : conf >= 0.90 pour la bonne techno
[ ] VERSION : extraite si la techno l'expose (verifier avec curl)
[ ] ZERO FP : aucun autre pattern ne matche au-dessus du threshold sur ce port
[ ] CLEAN : seuls les patterns legitimes apparaissent (Apache, PHP sont OK car sous-jacents)
```

## Services sous-jacents autorises (pas des FP)

Ces detections sont normales quand la techno tourne sur Apache+PHP :
- `lia-apache-httpd` / `recog-apache_httpd` (serveur web sous-jacent)
- `recog-php_php` (runtime PHP)
- `recog-nextcloud_nextcloud_server` / `recog-phpmyadmin_phpmyadmin` (duplicats recog du meme produit)
- Tout pattern `recog-*` qui detecte la meme techno ou son stack sous-jacent

Tout le reste est un FP a traiter.

## Comment atteindre 0 FP

### 1. Identifier les FP sur le port
```bash
timeout 30 ./liaprobe/bin/liaprobe --mode specific --ports PORT 127.0.0.1 2>/dev/null | \
  grep -E '"name"|"pattern_id"|"confidence"' | paste - - - | \
  grep -v "apache-httpd\|APACHE_HTTPD\|php_php\|lia-EXPECTED_TAXO"
```

### 2. Lire les matchers du FP (references/code-exploration.md Section C)

### 3. Desactiver si generique
```bash
python3 -c "
import json
f='data/fingerprints/lia/FP_TAXO.json'
d=json.load(open(f)); d['enabled']=False; json.dump(d,open(f,'w'),indent=2)
print(f'Disabled: {f}')
"
```

### 4. Re-sync + rebuild + re-scan

### 5. Verifier 0 FP

## Patterns FP recurrents a desactiver en debut de vague

Avant de commencer une vague, desactiver ces patterns connus pour etre trop generiques :

| Pattern | Fichier | Raison |
|---------|---------|--------|
| lia-truenas | TRNAS.json | status_code 200 + body generic |
| lia-rancher | RNCHR.json | header exists trop large |
| lia-matomo | MATMO.json | body "js" generique |
| lia-plausible | PLAUS.json | body script generique |
| lia-onvif | ONVIF.json | body XML generique |
| nuclei-detect_redmine* | DETECT_REDMI*.json | cookie generique |
| nuclei-kubelet_healthz | KUBELET_HEAL*.json | status_code 200 only |
| nuclei-jira_rest_api* | JIRA_REST*.json | JSON generic |
| nuclei-nacos | NACOS.json | status_code generic |
| nuclei-tyk_api_gateway | TYK_API*.json | JSON generic |
| nuclei-couchdb | COUCHDB.json | JSON generic |
| nuclei-matrix_homeserver | MATRIX_HOME*.json | JSON generic |
| nuclei-citrix_xenmobile_version | CITRIX_XENMOBILE_VERSION.json | version header generique |
| nuclei-oqtane_cms_database | OQTANE_CMS_DATABASE.json | path generique CMS |
| nuclei-torchserve_api_description | TORCHSERVE_API_DESCRIPTION.json | JSON API generique |
| nuclei-metatag_cms_detection | METATAG_CMS_DETECTION.json | metatag HTML generique |

## Seuils

| Critere | Seuil | Justification |
|---------|-------|---------------|
| Confidence bonne techno | >= 0.90 | Doit etre dominant, pas ambigu |
| Confidence max FP autorise | < threshold du pattern | Ne doit pas apparaitre dans les services |
| Version | Presente si exposee | Verifier avec curl que la version est visible |
