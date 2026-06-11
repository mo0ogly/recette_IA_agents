# Regles RETEX cumulatives (fingerprint detection)

Fichier vivant : chaque session ajoute ses regles. Lire AVANT de toucher un pattern.

## Session 2026-03-22 (Tomcat, WordPress, Drupal)

| # | Regle | Cause racine |
|---|-------|-------------|
| R1 | `"ports": []` dans les probes | probe.go:91 skip si port pas dans la liste |
| R2 | `80, 443` dans default_ports HTTP | executor emprunte ByPort[80] pour ports non-standard |
| R3 | Matcher body EN PLUS du header | meta tags souvent dans body HTML, pas en header HTTP |
| R4 | Chercher CSS/JS uniques dans pages erreur | wp-die-message, Tomcat #525D76, easter eggs |
| R5 | Sync 3 copies apres modification | lia/ + by-taxonomy/ + liaprobe/data/ (script: sync_fingerprints.sh) |
| R6 | Candidats tries par confidence | executor.go sort.Slice evite que maxProbes=10 coupe les bons |
| R7 | Sources open source EN LOCAL | `data/fingerprints/repositories/nuclei-templates/` + `data/fingerprints/wappalyzer/` |

## Recherche locale (ordre)

```bash
# 1. Nuclei (matchers body/header, paths specifiques)
find data/fingerprints/repositories/nuclei-templates -iname "*TECHNO*detect*" -name "*.yaml"

# 2. Wappalyzer (headers, meta, DOM, cookies, JS)
find data/fingerprints/wappalyzer -iname "*TECHNO*"

# 3. Nmap/Recog (banners TCP, service probes)
find data/fingerprints/{nmap,recog} -iname "*TECHNO*"
```

## Session 2026-03-22 Vague 2B (Nextcloud, phpMyAdmin, Adminer, RabbitMQ, Vault)

| # | Regle | Cause racine |
|---|-------|-------------|
| R8 | Desactiver FP recurrents AVANT de commencer | TrueNAS, Rancher, Matomo, Plausible matchent sur tout |
| R9 | LIRE le code source open source (pas juste chercher) | Appliquer mecaniquement sans comprendre = FP non detectes |
| R10 | LIRE le code LiaProbe si FP persiste | Comprendre le flow executor -> matcher pour diagnostiquer |
| R11 | Gate qualite 0 FP par port avant de passer au suivant | Travail bacle = FP accumules non-detectes |

## Checklist pattern (appliquer systematiquement)

- [ ] `"ports": []` dans chaque probe
- [ ] `80, 443` dans default_ports (si HTTP)
- [ ] Au moins 1 matcher body (pas seulement header)
- [ ] confidence_delta >= 0.5 pour le matcher principal
- [ ] Probe sur path specifique si la techno en a un (login, install, API)
- [ ] `sync_fingerprints.sh TAXONOMY.json` apres modification
- [ ] Test : `timeout 30 ./liaprobe/bin/liaprobe --mode specific --ports PORT 127.0.0.1 2>/dev/null`
- [ ] **0 FP sur le port** (voir references/quality-gate.md)
- [ ] **conf >= 0.90** pour la bonne techno
- [ ] **Version extraite** si exposee par le service

## Session 2026-03-22 Vague 3 TCP + RETEX final

| # | Regle | Cause racine |
|---|-------|-------------|
| R12 | Repos de reference EN LOCAL d'abord (`data/fingerprints/repositories/`), websearch OK pour autres sources | 3 agents websearch pour re-telecharger Nuclei/Wappalyzer = gaspillage, mais websearch OK pour docs vendeur, CVE, forums |
| R13 | Verification desactivation obligatoire (scan apres disable) | FP marques [x] mais enabled=true dans by-taxonomy/ |
| R14 | TCP : banner detect dans executor suffit souvent | MySQL/Redis/PostgreSQL corriges avec banner_matchers |
| R15 | Version extract dans URLs CSS/JS (?v=, &version=) | phpMyAdmin v=5.2.3, Adminer version=5.4.2 |

## Session 2026-03-22 Qualification lab (19 ports)

| # | Regle | Cause racine |
|---|-------|-------------|
| R16 | banner_matchers target DOIT etre "banner" (ou deplacer en probe) | Bug M1 : 111 patterns ignores par evaluateBannerMatchers |
| R17 | Matchers generiques (JSON "version":) ne doivent JAMAIS avoir delta > 0.5 | Bug M2 : FP GitLab sur Grafana |
| R18 | Valider ByPort[80] coherent avec default_ports apres BuildIndex | Bug M3 : Consul invisible |

## Session 2026-03-22/23 Qualification IPs reelles (44 cibles)

| # | Regle | Cause racine |
|---|-------|-------------|
| R19 | Tester sur IPs DIRECTES (pas CDN) -- 70% des MISS = CDN masque | live_targets.csv avait des IPs Cloudflare/Akamai |
| R20 | isKnownHTTPPort : forcer probe HTTP sur 80/443/8080/8443/8888/3000 | Fix M4 : auto_http ne se declenchait pas sur port 443 distant |
| R21 | Probes HTTP : utiliser hostname (pas IP brute) pour Host header + TLS SNI | Fix M5 : virtual hosting 400/421 sur serveurs distants |
| R22 | Probes redirect-sensitive : follow_redirects=false | Fix P1 : X-Gitlab-Meta dans 302 perdu apres redirect |
| R23 | Sync ALL copies y compris sous-repertoires (ssh/, web/) | Bug sync : ssh/OPENSSH.json ecrasait OSSH.json mis a jour |

## Session 2026-03-23 Fix moteur multiplicateurs (inspire repos open source)

| # | Regle | Source | Impact |
|---|-------|--------|--------|
| R24 | Fix moteur > fix pattern (1:N vs 1:1) | RETEX qualification | 16000+ patterns |
| R25 | LIRE le code des repos open source AVANT de coder un fix moteur | Nuclei matchers-condition, Wappalyzer implies, Recog banner XML | Evite de reinventer |
| R26 | Utiliser les parsers standard Go (http.ReadResponse, bufio) au lieu de parser manuellement | Go stdlib | Moins de bugs, plus robuste |
| R27 | ParseHTTPBanner : auto-parser les banners HTTP en headers+body synthetiques | Fix E1 : 264 patterns debloques en phase passive | Multiplicateur |
| R28 | Required matcher : if required=true et pas de match -> pattern rejete | Nuclei matchers-condition:and | Anti-FP structural |

## Session 2026-03-23 RETEX session complete (22% -> 86.9%)

| # | Regle | Cause racine | Impact |
|---|-------|-------------|--------|
| R29 | Fix moteur 1:N > fix pattern 1:1 (PRIORITE ABSOLUE) | Temps perdu sur corrections individuelles vs fix moteur qui debloque 264+ patterns | 12000+ patterns |
| R30 | Chercher un convertisseur dans `scripts/tools/` AVANT de creer patterns | `convert_recog_to_lia.py` existait deja, a permis 2404 patterns en 1 commande | 2404 patterns |
| R31 | Mode recette OBLIGATOIRE apres chaque fix moteur | Avant : test port par port (30s chacun). Apres : 5406 cas en 29s | Regression impossible |
| R32 | Score recette NON-REGRESSION (ne doit JAMAIS baisser) | Pas de baseline avant cette session, fix pouvaient casser d'autres detections | 5406 cas valides |
| R33 | Agents INTERDITS de git add -A | Agent a stage 19K fichiers wappalyzer, commit pollue | Commits propres |
| R34 | liacheckscanner_go = 8eme source (datascan_recette.jsonl, 5406 ground truth) | Dataset pas connu au debut, decouvert en cours de session | 5406 cas offline |

## Erreurs de session corrigees

| Erreur | Quand | Fix applique |
|--------|-------|-------------|
| Fix moteur code sans lire repos (M4, M5) | Debut session | R25 renforce en contrainte 8 BLOQUANTE |
| Fix patterns 1:1 avant fix moteur 1:N | Milieu session | R29 ajoutee contrainte 9 |
| ParseHTTPBanner code a la main | Milieu session | Remplace par `http.ReadResponse` Go stdlib (R26) |
| ssh/OPENSSH.json ecrase OSSH.json mis a jour | Qualification lab | R23 renforce : verifier sous-repertoires |
| DECOMPOSE pas ecrite avant agents | Debut session | Phase 1 renforcee : "INTERDIT de lancer agents sans decomposition ecrite" |
| Working Memory pas maintenue | Toute session | Ajoutee comme OBLIGATOIRE dans la skill |
| Agents font git add -A | Agent TCP restants | R33 ajoutee |
