---
name: liaprobe-rule-enrich
description: Enrichit une LiaProbe fingerprint JSON avec metadata LIA-original (CVE awareness via PostgreSQL, lifecycle EOL via endoflife.date, MITRE ATT&CK + D3FEND mapping) pour transformer le contenu en oeuvre derivee non-attaquable. Se declenche sur "/liaprobe-rule-enrich <path>", "enrichis cette signature", "ajoute CVE et MITRE a la rule", "transformative work signature", ou quand /apex orchestre cycle 4/5/7 du PLAN_LIAPROBE_SIGNATURES_ENRICHMENT.
---

# LiaProbe Rule Enrich

Enrichit une fingerprint JSON LiaProbe (schema `lia-fingerprint-v1`) avec metadata LIA-originale qui ne provient PAS des outils tiers (Wappalyzer, Recog, Nuclei). Objectif : rendre chaque signature substantiellement plus riche que upstream pour soutenir un argument legal d'oeuvre transformative.

## Contexte

Audit similarity 2026-05-02 a revele 10 234 LIA web-signatures HIGH similarity vs Wappalyzer GPL-3. Cette skill ajoute des sections LIA-only par signature (pas de suppression, pas de reecriture des regex existants -- seulement enrichissement).

Plan parent : `_alire/tracking/PLAN_LIAPROBE_SIGNATURES_ENRICHMENT_2026-05-02.md` (cycles 4 a 12).

Cette skill couvre les 3 cycles AUTO :
- Cycle 4 : CVE awareness (PostgreSQL `cve_nvd_data` + `cisa_kev` + `exploit_db`)
- Cycle 5 : Lifecycle EOL (endoflife.date API)
- Cycle 7 : MITRE ATT&CK + D3FEND (PostgreSQL `cve_attack_mapping`)

## Decomposition des sous-taches

Au demarrage identifier ces sous-taches :

1. **VALIDATE INPUT** : path JSON existe, schema `lia-fingerprint-v1`, champs requis presents
2. **BACKUP** : copy original to .bak (rollback safe)
3. **ENRICH CVE** (cycle 4) : query PG via `cpe23_template`, inject `known_cves[]`
4. **ENRICH LIFECYCLE** (cycle 5) : query endoflife.date via product slug, inject `lifecycle{}`
5. **ENRICH MITRE** (cycle 7) : depend cycle 4, query `cve_attack_mapping`, inject `attack_surface{}`
6. **COMPUTE SIMILARITY** : audit BEFORE et AFTER pour mesurer transformative gain
7. **VALIDATE OUTPUT** : JSON valide, schema preserve, regex existants intacts
8. **WRITE BACK + LOG** : ecriture en place + decision_log.jsonl

Dependances :
- 5 et 7 dependent de 1+2
- 7 depend de 3 (CVE list)
- 6 depend de 3+4+5
- 8 depend de 7

## Mode batch (c20+, recommande pour cron-driven enrichment)

Quand la skill est invoquee par auto-chain depuis `nightly_fingerprint_batch.sh -> consume_enrich_queue.py` :

```bash
# Mode A : derive cycles + inline actions du batch automatiquement (c21)
python3 run_enrich.py \
  --batch /opt/lia-sec/dev/_alire/temp/apex/enrich_batches/enrich_batch_<DATE>_<batch_id>.json \
  --from-batch-actions \
  --liaprobe-root /opt/lia-sec/liaprobe

# Mode B : OODA agentic (default si cycles inconnus dans batch)
python3 run_enrich.py --batch <file> --ooda --liaprobe-root /opt/lia-sec/liaprobe

# Mode C : cycles explicites
python3 run_enrich.py --batch <file> --cycles 4,5,7 --liaprobe-root /opt/lia-sec/liaprobe
```

`--from-batch-actions` lit `batch.batches` action types et derive les cycles via `BATCH_ACTION_TO_CYCLE` :
- `cve_lookup` -> `cycle_4_cve`
- `version_compare` -> `cycle_5_eol`
- `eol_check` -> `cycle_5_eol`
- `mitre_attack` -> `cycle_7_mitre`
- `default_creds_check` -> `cycle_8_default_creds`
- `cert_patterns` -> `cycle_9_cert_patterns`
- `compliance_mapping` -> `cycle_6_compliance`

Actions inline (mutations directes, pas de cycle) :
- `cpe23_template_fill` : si `rule.cpe23_template` vide ET `action_params.proposed` non vide -> ecrit la valeur + audit `inline_action_history`

Workflow complet consume -> enrich (cron + interactive) :
1. Nightly (cron) : `consume_enrich_queue.py --emit --mark` -> batch JSON archive
2. Session interactive : `run_enrich.py --batch <file> --from-batch-actions`
3. Skill enrichit + summary -> next cycle classifie outcomes

Idempotence : rules deja flagees `_meta_enrichment` riches sautent automatiquement (verifie par enrich_lib).

## Plan d'execution

Avant toute action, creer `_alire/tracking/PLAN_RULE_ENRICH_{ruleId}_{YYYY-MM-DD}.md` :

```markdown
# Plan -- Enrich {ruleId}
Status : EN_COURS
Etapes :
- [ ] 1. Validate input JSON schema
- [ ] 2. Backup original (cp .bak)
- [ ] 3. Cycle 4 : CVE awareness (PG query)
- [ ] 4. Cycle 5 : Lifecycle EOL (endoflife.date)
- [ ] 5. Cycle 7 : MITRE ATT&CK (PG query depend CVE)
- [ ] 6. Compute similarity before/after
- [ ] 7. Validate output JSON
- [ ] 8. Write back + log decisions
- [ ] VERIFICATION GATE
```

Cocher chaque etape `[x]` a la completion. Si replanification : Status -> REPLANIFIE.

## Adaptation et replanification

- 1 echec : retry une fois avec params ajustes (timeout +50%, query simplifiee). Log non-bloquant.
- 2 echecs consecutifs : STOP -> invoquer `/replan` -> NE PAS improviser fallback non-trace
- `/replan` produit `PLAN_RULE_ENRICH_{ruleId}_REPLAN_*.md` avec plan ajuste

Cas non-fail mais ambigu (skip + log) :
- Pas de `cpe23_template` -> skip cycle 4 (CVE), continuer 5 et 7 si possible
- Pas de match endoflife.date -> skip cycle 5
- Pas de CVE matched -> skip cycle 7 (depend CVE)

## Outils declares

Selection dynamique selon contexte :
- `Read` : lire le JSON input
- `Bash` : invoke scripts Python (PG queries, API calls)
- `Edit` / `Write` : ecrire JSON enrichi
- Scripts dedies : `scripts/enrich_cycle_4_cve.py`, `scripts/enrich_cycle_5_eol.py`, `scripts/enrich_cycle_7_mitre.py`, `scripts/run_enrich.py` (orchestrator), `scripts/quality_gate.py` (17 gates G1-G17), `scripts/ooda_engine.py` (OODA loop), `scripts/enrich_lib.py` (atomic write, lock, schema, http cache, pg, state, evidence), `scripts/update_enriched_index.py` (auto-rebuild ENRICHED_RULES.md tracking dashboard), `scripts/corpus_count.py` (real top-level vs phantom nested rule count -- anti `find` over-count)
- PostgreSQL via env `LIA_DB_PASS` + helper `psql_lia` (R8)
- `endoflife.date` API publique (no key required, cache local 7 jours)

Retry policy :
- API timeout : 1 retry avec backoff 2s
- PG connection refused : 1 retry, then log + skip
- 2 echecs consecutifs : STOP -> /replan

## Tracabilite agentique

Logger dans `_alire/02_LOGS/Journals/decision_log.jsonl` pour chaque cycle :

```json
{
  "timestamp": "2026-05-02T14:30:00Z",
  "session": "rule-enrich-kibana",
  "action": "ENRICH_CYCLE_4_CVE",
  "reasoning": "cpe23_template=cpe:2.3:a:elasticsearch:kibana matched 23 CVE in cve_nvd_data (8 KEV-listed, 3 with exploit_db_id)",
  "alternatives_rejected": ["skip if no CPE", "limit to severity HIGH only"],
  "outcome": "23 CVE injected in known_cves[], 8 KEV flagged, 3 exploitable",
  "confidence": "high",
  "plan_ref": "_alire/tracking/PLAN_RULE_ENRICH_kibana_2026-05-02.md"
}
```

Produire RETEX en fin de session si transformative_score gain < 30 points :
- `_alire/02_LOGS/Journals/retex/RETEX_RULE_ENRICH_{ruleId}_{date}.md`

## Workflow detaille

### Etape 1 : Validate input

```bash
python3 scripts/run_enrich.py --validate-only <path>
```

Erreurs rejetees : file not found, invalid JSON, schema != "lia-fingerprint-v1", missing `id|taxonomy_code|product`.

### Etape 2 : Backup

```bash
cp <path> <path>.bak
```

### Etape 3 : Cycle 4 -- CVE awareness

Voir `references/cycle4_cve_format.md` pour schema cible.

```bash
python3 scripts/run_enrich.py --rule <path> --cycles 4
```

Le script :
- Lit `cpe23_template`, parse vendor + product
- Query PG : `SELECT * FROM cve_nvd_data WHERE cpe23 LIKE 'cpe:2.3:a:vendor:product:%'`
- LEFT JOIN `cisa_kev` ON cve_id, LEFT JOIN `exploit_db_meta` ON cve_id
- Limite : 50 entries max, sorted by CVSS desc + KEV first
- Inject `known_cves[]`

### Etape 4 : Cycle 5 -- Lifecycle EOL

Voir `references/cycle5_lifecycle_format.md`.

```bash
python3 scripts/run_enrich.py --rule <path> --cycles 5
```

Le script :
- Slugify `product` field -> endoflife.date slug
- Cache local `_alire/temp/eol_cache/` (7 jours TTL)
- GET `https://endoflife.date/api/{slug}.json`
- Inject `lifecycle{released, eol, is_eol_now, active_support_until, ...}`
- Skip si pas de match (produits niche)

### Etape 5 : Cycle 7 -- MITRE ATT&CK

Voir `references/cycle7_mitre_format.md`.

```bash
python3 scripts/run_enrich.py --rule <path> --cycles 7
```

### Mode agentique (OODA loop, recommande)

Au lieu de lancer cycles individuellement, utiliser OODA mode pour boucle auto avec gates G1-G17, dependency management (cycle 7 attend cycle 4) et tracking dashboard auto-update :

```bash
python3 scripts/run_enrich.py --rule <path> --ooda --target 50 --max-iter 5
```

Batch sur tous patterns :

```bash
python3 scripts/run_enrich.py --rules-dir patterns/lia --ooda --target 50 --summary _alire/temp/batch.json
```

Le script :
- Lit `known_cves[]` (depend cycle 4)
- Query PG : `SELECT DISTINCT technique_id FROM cve_attack_mapping WHERE cve_id = ANY(...)`
- JOIN `mitre_techniques` pour name + tactic
- Inject `attack_surface{techniques, tactics, d3fend_countermeasures, kill_chain_phase}`

### Etape 6 : Similarity score

```bash
python3 scripts/similarity_score_diff.py <path> <path>.bak
```

Output :
- BEFORE : score similarity vs upstream Wappalyzer (e.g. 100%)
- AFTER : score similarity (regex unchanged so should rester ~100%)
- TRANSFORMATIVE : ratio LIA-only content / total content (target >= 40%)

### Etape 7 : Validate output

```bash
python3 scripts/run_enrich.py --validate-only <path>
```

### Etape 8 : Write back + log

JSON ecrit en place. `decision_log.jsonl` appended.

## VERIFICATION GATE (BLOQUANT)

Apres execution, AVANT de declarer termine :

- [ ] JSON parse OK (`--validate-only` = **schema check Python**, PAS le validateur Go pre-commit)
- [ ] Schema `lia-fingerprint-v1` preserve
- [ ] Regex existants non-modifies (diff sur `probes[].matchers[].value`, `banner_matchers[].value`, `service_matchers[].value`)
- [ ] Au moins UNE des 3 sections injectees : `known_cves[]`, `lifecycle{}`, `attack_surface{}`
- [ ] transformative_score gain >= 20 points
- [ ] Validateur Go pre-commit (optionnel mais recommande avant commit) :
      `python3 scripts/run_enrich.py --rules-dir <dir> --cycles 4,5,7 --go-validate`
      lance `bin/lia-rule-validate -q -allow-disabled` (rebuild auto si binaire absent,
      meme gate que le hook pre-commit) -> surface une rupture de schema AVANT le commit.
- [ ] Pas de regression Go loader (test optionnel : `go test ./pkg/fingerprint/... -run TestLoad`)

Deux validations distinctes -- ne pas confondre :
- `--validate-only` : check schema `lia-fingerprint-v1` cote Python (rapide, sans build Go).
- `--go-validate` / pre-commit `bin/lia-rule-validate` : validateur Go source de verite
  du hook. Binaire gitignore -> rebuild via `go build -o bin/lia-rule-validate
  ./cmd/lia-rule-validate/` depuis le repo liaprobe (fait auto par `--go-validate`).

Compter le corpus reel AVANT de chasser un nombre `find` trompeur :
`python3 scripts/corpus_count.py <patterns/tier>` -> `real=N phantom=M` (top-level
*.json = regles reelles ; nested captures/todo/_generated_onyphe = metadata, PAS des
regles). Le moteur et l'orchestrateur ne scannent que le top-level (`dir.glob('*.json')`).

Skip reasons cycle 4 (CVE) -- classification riche (RETEX wave 6) :
`no_cpe`, `cpe_part_os` (:o: OS host -> `needs_cpe_correction`, classe QTSS),
`cpe_unparseable` (2.2 / non a-h -> `needs_cpe_correction`), `no_nvd_entry`
(produit absent du corpus NVD -> `dead_product_candidate`, rien a enrichir sans
fabrication R4), `no_match` (produit connu, 0 CVE), `pg_down`.

Si gate fail : STOP, restore .bak, fix, re-run.

## Scoring agentique

| Critere | Score |
|---------|-------|
| C1 Decomposition : 8 sous-taches identifiees ? | /10 |
| C2 Planification : PLAN_*.md cree et coche ? | /10 |
| C3 Replanification : /replan declenche sur 2+ echecs ? | /10 |
| C4 Outillage : scripts dedies + PG + endoflife API ? | /10 |
| C5 Tracabilite : decision_log + RETEX produits ? | /10 |

Total /50 -- >= 40 Exemplaire | 30-39 Acceptable | < 30 RETEX obligatoire

## Authoritative external sources (sourced + tracked)

Toute donnee external integree dans rules DOIT etre tracee : `source.url` + `source.sha256` + `source.fetched_at` + ligne exacte. Permet replay + drift detection.

### Cycle 4 -- CVE awareness
- **PostgreSQL LIA-SEC** `lia_scan` DB : `cve_nvd_data` + `cve_product` + `product` + `kev_cisa_vulnerabilities`
- DSN env : `DATABASE_URL` ou `LIA_DB_*` (R8 secrets via env)

### Cycle 5 -- Lifecycle EOL
- **endoflife.date public API** : `https://endoflife.date/api/{slug}.json`
- Master CSV slug mapping : `_alire/tracking/liaprobe-enrich-v2/master_data/endoflife_slug_mapping.csv`

### Cycle 7 -- MITRE ATT&CK
- **PostgreSQL LIA-SEC** `lia_scan` DB : `cve_attack_mapping` (technique_name embedded)
- Cross-link via `known_cves[]` (depend cycle 4)

### Cycle 8 -- Default credentials

Ne PAS s'appuyer sur une seule source. Cross-check recommande sur 2+ sources pour chaque produit.

**Primary -- DefaultCreds-cheat-sheet** (currently integrated)
- URL : `https://raw.githubusercontent.com/ihebski/DefaultCreds-cheat-sheet/main/DefaultCreds-Cheat-Sheet.csv`
- Repo : `https://github.com/ihebski/DefaultCreds-cheat-sheet`
- License : MIT
- 3764 entries, 15+ products mapped via `scripts/build_default_creds_master.py`
- Cached at `master_data/sources/defaultcreds_cheat_sheet/DefaultCreds-Cheat-Sheet.csv`

**Secondary -- SecLists default-passwords.csv** (TODO integrate)
- URL : `https://raw.githubusercontent.com/danielmiessler/SecLists/master/Passwords/Default-Credentials/default-passwords.csv`
- Repo : `https://github.com/danielmiessler/SecLists`
- License : MIT
- Largest curated default creds CSV (Cisco, Citrix, networking gear...)
- Companion list : `https://raw.githubusercontent.com/danielmiessler/SecLists/master/Usernames/cirt-default-usernames.txt`

**Tertiary -- BetterDefaultPasslist** (TODO integrate)
- URL : `https://github.com/govolution/betterdefaultpasslist`
- License : check repo
- Specialise NAS / ERP / ICS / MSSQL / VNC / Oracle (industrial systems coverage)

**Cross-check / authoritative reference**
- cirt.net Passwords DB : `https://cirt.net/passwords/` (canonical reference, web UI; programmatic via `passdb` Ruby gem `https://github.com/securityroots/passdb`)
- The Hacker Recipes : `https://www.thehacker.recipes/web/config/default-credentials` (curated examples)
- OWASP WSTG default creds : `https://owasp.org/www-project-web-security-testing-guide/latest/4-Web_Application_Security_Testing/04-Authentication_Testing/02-Testing_for_Default_Credentials` (methodology + curated)

**Vendor docs (per-product, mandatory cross-check)**
- Jenkins, Kibana, Grafana, Elasticsearch, MongoDB, GitLab, etc.
- URLs officiels stockes dans `master_data/sources/vendor_docs/<product>.url.txt` + cache HTML/MD avec sha256

**Out of scope (different scope, breached credentials != default credentials)**
- HaveIBeenPwned Passwords v7 (226M breached passwords) -- NOT per-product defaults
- Specops password policy (5.5B breached) -- same caveat

**Build workflow** : `scripts/build_default_creds_master.py --cache <csv> --manifest <json> --out <output>`

Pipeline complet documente dans `_alire/tracking/liaprobe-enrich-v2/MASTER_DATA_FORMAT.md`.

### Cycle 6 -- Compliance (TODO)

Sources a venir (sessions futures, recherche dediee) :
- **ANSSI** : `https://cyber.gouv.fr/publications/...` PA-088, R39 (PDF officiel FR)
- **NIS2** : `https://eur-lex.europa.eu/eli/dir/2022/2555` annexes I/II (texte directive EU)
- **ISO 27001:2022** : crosswalk public NIST CSF ou achat ISO PDF
- **EBIOS RM v2** : `https://cyber.gouv.fr/publications/ebios-risk-manager` (guide ANSSI PDF)

## References modulaires

- `references/cycle4_cve_format.md` -- schema `known_cves[]` + SQL query templates
- `references/cycle5_lifecycle_format.md` -- schema `lifecycle{}` + endoflife.date mapping
- `references/cycle7_mitre_format.md` -- schema `attack_surface{}` + MITRE STIX query
- `references/error_handling.md` -- fallback strategies par cycle

## Composition avec autres skills

- `/apex` : orchestre cette skill sur batch de N rules (parallele via Agent)
- `/replan` : declenche si 2+ echecs consecutifs
- `/konrad-kurze` : meta-cognitive auditor si replan loop
- Pas de `/test-first` (skill ne produit pas de code Go/React, juste edit JSON)

## Triggers

- Direct : `/liaprobe-rule-enrich <path>`
- Phrase : "enrichis cette signature", "ajoute CVE/MITRE a cette rule", "transformative signature"
- APEX cycle 4-12 du PLAN_LIAPROBE_SIGNATURES_ENRICHMENT auto-invoque

---

## Sub-mode : Vendor sync (canonical vendor mapping)

Mode separe de l'enrichissement. Synchronise chaque rule LiaProbe avec
PostgreSQL `vendor` + `vendor_alias` pour produire `lia_signature_key`
canonique (e.g. `lia_v2716_p4521`) + remplacer `id`/`taxonomy_code` legacy
par formes `vendor_product` (preserve `legacy_id`/`legacy_taxonomy_code`
pour audit). Different objet : ENRICHMENT injecte metadata, VENDOR SYNC
remappe identifiants.

Workflow 8-phases :

```
A1 SETUP    : pg_trgm extension + product indexes (lower_name, GIN trgm) verified
              (migration NNN_*.sql obligatoire si absents)
A2 AUDIT    : dry-run categorize 16,937 rules -> v_baseline.csv
              measure CONFIDENT/DOUBTFUL/SKIP distribution
A3 PHASE_A  : CPE :a: + :h: trust + CPE 2.2 parser
              skip :o: (incident 2026-05-03, 521 misattribution Microsoft)
              -> v_phaseA.csv
A4 PHASE_B  : product_only fallback (no CPE -> rule.product ILIKE product table)
              auto bucket=DOUBTFUL (R4 protection)
              -> v_phaseB.csv
A5 BRAIN    : 6 agents brainstorm Phase C strategies SI SKIP > 50%
              5 strategists (id slug, filename, banner, notes/tags, taxonomy)
              + 1 adversarial OBLIGATOIRE (concrete FP examples mandatory)
              -> brainstorm_phase_c/{agent_N_*.md, CONSOLIDATED.md}
A6 WAVES    : C1 -> C2 -> C3 sequential
              regression sample 20 random DOUBTFUL/wave -> manual verify
              FP > 10% -> ROLLBACK + tighten guards
A7 APPLY    : --apply CONFIDENT only (preserve legacy_id, legacy_taxonomy_code)
              DOUBTFUL/SKIP keep legacy untouched
A8 COMMIT   : RETEX + CSV + INDEX maj + tests greens
```

### Resolver classification contract (INVARIANT)

```
CONFIDENT  -> CPE :a: or :h: AND alias_exact match
DOUBTFUL   -> fuzzy_trgm | product_only | sub_product | no_cpe-but-product
              | banner_literal | notes_capword | id_slug | taxonomy_token
              | filename_token
SKIP       -> no_cpe AND no_match
```

Tout `method` autre que `alias_exact` avec CPE :a:/:h: DOIT bucket=DOUBTFUL.
Aucune auto-CONFIDENT pour : product_only_*, banner_*, notes_*, id_slug_*,
filename_*, taxonomy_*. R4 + R18 enforcement.

### CPE classification (R18 enforcement)

| Part | Trust | Reason |
|------|-------|--------|
| `:a:` | YES | application = service vendor authoritative |
| `:h:` | YES | hardware = device vendor (Bosch/Motorola/Cisco) authoritative |
| `:o:` | NO  | OS host = misattribution risk (e.g. cpe:2.3:o:microsoft:windows for any service running on Windows). Incident 2026-05-03: 521 rules wrongly attributed to Microsoft when :o: was trusted |

### Pre-flight gates (BLOCKING before A2)

- [ ] `pg_trgm` extension exists (`SELECT extname FROM pg_extension WHERE extname='pg_trgm'`)
- [ ] `product` table has `idx_product_lower_name` btree
- [ ] `product` table has `idx_product_name_trgm` GIN
- [ ] `vendor_alias` table has `idx_vendor_alias_lower_unique`
- [ ] `vendor_alias` table has `idx_vendor_alias_trgm` GIN
- [ ] Migration NNN_product_name_indexes.sql applied (template: `migrations/147_product_name_indexes.sql`)

### Phase C strategies + adversarial guards

| # | Strategy | Bucket | Required guard |
|---|----------|--------|----------------|
| 1 | id slug parser | DOUBTFUL | tcp-probes only, proto blacklist, alias_exact |
| 2 | filename parser | DOUBTFUL | Method A only (kill ILIKE B/C), generic stoplist, alias_exact |
| 3 | banner regex literal | DOUBTFUL | conf >= 0.80, supplementary only, NEVER primary |
| 4 | notes/tags capword | DOUBTFUL | STOPWORDS + GENERIC_TAGS denylist, alias_exact, conf >= 0.85 |
| 5 | taxonomy_code first-token | DOUBTFUL | exact match only, blacklist THE/EASY/ABLE/GRAPHQL/GENERIC/UNKNOWN/MISC |
| 6 | adversarial auditor | N/A | mandatory before merge of strategies 1-5 |

### Phase D strategies (post-Phase-C, 2026-05-04)

| # | Strategy | Bucket | Required guard |
|---|----------|--------|----------------|
| D1 | website domain root | DOUBTFUL | NO-GO standalone (4.4% yield + 25-30% FP). Defer to manual curation |
| D2 | taxonomy_name first capword | DOUBTFUL | alias_exact + extended TAXONOMY_NOISE_FIRST_TOKENS (Coin/Cookie/Daily/Smart/Simple/Modern/Pro/Plus...). Solo verify 20/20 TP. |
| D3 | taxonomy_name bigram | DOUBTFUL | not implemented (low yield estimated, blocked by rate limit) |
| D4 | implies array | N/A | NO-GO standalone (mirror of notes_capword incident, runtime trap) |

### Regression test corpus (mandatory before any new resolver method)

Each new method MUST add tests for these confirmed false-positive cases :
- `CHKMK.json` (vendor=tribe29) -- "Apache" in notes MUST NOT resolve to Apache
- `BAMBO.json` (vendor=Atlassian) -- "Tomcat" in notes MUST NOT resolve to Tomcat
- `LIA_PRINTER_NETSARANG_XLPD.json` (vendor=NetSarang) -- "hp LaserJet" in banner MUST NOT resolve to HP
- `FTPD.json` (filename FTPD) -- generic protocol name MUST NOT resolve to vendor
- taxonomy first-tokens THE / EASY / ABLE / GRAPHQL MUST NOT resolve

### Sub-mode : Vendor alias scoring (Phase F1+)

Mode complementaire au vendor sync. Score chaque proposition de
`vendor_alias` AVANT INSERT, avec decision automatique apply/review/defer/
reject + persistance trail PostgreSQL. Objectif : empecher l'inflation
silencieuse d'aliases low-confidence qui polluent les fuzzy matches.

#### Session layout (BLOCKING from 2026-05-04)

UN subdir par session sous `_alire/tracking/liaprobe-enrich-v2/sessions/<YYYY-MM-DD>_<slug>/`.
Chaque subdir contient :
- `SESSION.md` : manifest unique de la session (verdict, KPI cumul, links
  vers tous les artifacts). Point d'entree obligatoire.
- `proposals_phase_*.json` : manifests de wave SESSION-LOCAUX
- `phase_*_applied_scores.json` : applied trails SESSION-LOCAUX

Les artifacts cross-cutting RESTENT a leur location projet conventionnelle :
- RETEX `_alire/02_LOGS/Journals/retex/RETEX_*.md` (R15)
- Migrations `cmd/sigma_web/migrations/NNN_*.sql` (R5)
- Skill code `.claude/skills/<skill>/` (this dir)
- INDEX entry `_alire/tracking/INDEX.md`
- decision_log `_alire/02_LOGS/Journals/decision_log.jsonl`

Mais ils DOIVENT etre lies depuis `SESSION.md` (relative paths).

Le fichier `_alire/tracking/liaprobe-enrich-v2/SESSIONS_INDEX.md` est la
table maitresse listant toutes les sessions avec verdict + closure cumul.

INTERDIT :
- Subdirs ad-hoc en dehors de `sessions/` (cf. `feedback_skill_workdir.md`)
- Melange d'artifacts de 2 sessions dans le meme subdir
- Duplication d'artifact deja en location conventionnelle (toujours lier)

#### Pipeline

```
1. Build proposals JSON (Phase F1+ wave manifest)
   path: _alire/tracking/liaprobe-enrich-v2/recettes/.../proposals_<wave>.json
2. Dry-run: score_aliases.py --proposals X --wave-id Y --no-match-total N
   -> outputs decisions table + writes to vendor_alias_score
3. Inspect: total_score >= 0.85 = apply, 0.65-0.84 = review, etc.
4. Sample-verify 20 random apply rows manually (psql lookup vendor.product_id)
5. If FP rate <= 10%: re-run with --apply
   -> INSERTs into vendor_alias, links via alias_id
6. Update enrich_wave_runs verdict (GO/PARTIAL/FAIL) post-verify
```

#### Rubric (sourced agent6_adversarial_report.md, Phase F)

| Component | Weight | Labels |
|-----------|--------|--------|
| source    | 0.35   | vendor_docs 1.0 / nvd_cpe_direct 0.95 / mitre_stix 0.90 / cisa_kev 0.85 / github_org 0.85 / manual_curation 0.70 / fuzzy_pgtrgm 0.55 / community 0.40 / lia_internal 0.30 |
| match     | 0.25   | exact_lower 1.0 / alias_known 0.90 / fuzzy_high 0.75 (sim>=0.85) / fuzzy_medium 0.50 / fuzzy_low 0.20 |
| evidence  | 0.25   | products>=10 1.0 / 3-9 0.80 / 1-2 0.60 / 0 or vendor_absent 0.10-0.20 |
| penalty   | 0.15   | clean 1.0 / brand_confusion 0.60 / personal_author 0.50 / white_label_oem 0.40 / low_info_generic 0.20 |

Decision thresholds : apply >= 0.85, review 0.65-0.84, defer 0.40-0.64, reject < 0.40.

#### Tables (migration 149)

- `vendor_alias_score`     : per-proposal trail (alias_id NULL until applied)
- `enrich_wave_runs`       : per-wave KPIs (closure_rate, fp_rate, regression, verdict)
- `vendor_alias_score_latest` : view dedup most recent score per (alias_name, vendor_id)

#### Tooling

- `scripts/score_aliases.py` (PGClient via DATABASE_URL or LIA_DB_PASS env)
  - `--proposals <path>`        proposals JSON manifest
  - `--wave-id <id>`            wave label (e.g. `phase_f1_2026-05-04`)
  - `--phase <label>`           defaults to wave-id
  - `--operator <name>`         audit trail
  - `--no-match-total <N>`      corpus size for closure_rate calc
  - `--apply`                   INSERT decision='apply' rows into vendor_alias
  - `--allow-synthetic`         (with --apply) force-INSERT proposals targeting
                                vendors prefixed `lia-*` regardless of decision
                                threshold. Score trail gets `[SYNTHETIC_OVERRIDE
                                wave=X: bypassed decision=Y gate via --allow-
                                synthetic]` suffix auto-appended to rationale
  - `--out-json <path>`         dump scored proposals JSON (for RETEX)
  - `--max-reject-rate <f>`     abort if reject ratio > threshold (default 0.50)
  - exit 7 = reject ratio breach (audit needed before re-run)

`insert_alias()` returns `(alias_id, status)` where status is one of :
- `inserted`        new row created, alias_id linked to score row
- `duplicate_same`  alias exists pointing to SAME vendor_id (linked, dedup_note added)
- `duplicate_other` alias exists pointing to DIFFERENT vendor_id (NOT linked, WARN suffix added to score row notes -- closes the F1 Pivotal silent class of bug)
- `no_vendor`       proposed vendor not found in vendor table

#### Pre-flight gates (BLOCKING before --apply)

- [ ] Migration 149 applied (`SELECT 1 FROM information_schema.tables WHERE table_name='vendor_alias_score'`)
- [ ] vendor_alias source whitelist matches proposals (`manual` is the safe default)
- [ ] Backup `vendor_alias` + `vendor` if proposed apply count > 100
      (`pg_dump -t vendor_alias -t vendor`)
- [ ] Each proposal has `rationale` non-empty (R18 verifiability)
- [ ] Each proposal targets an existing `vendor_name` (vendor_absent -> evidence_score 0.10 forces reject)

#### Wave verdict scoring (rebalanced 2026-05-04 post F1+F2 retex)

```
wave_score = closure_rate * 0.20 + (1 - fp_rate) * 0.50 + regression_inverse * 0.30
```

(Previous weights 0.40 / 0.40 / 0.20 capped warmup waves at PARTIAL even with
0% FP. Quality-first formula honors the FP/regression dimensions.)

| Metric            | GO seuil | FAIL seuil |
|-------------------|----------|------------|
| closure_rate      | >= 5%    | < 1%       |
| fp_rate (sample)  | <= 10%   | > 25%      |
| regression_count  | 0        | > 5        |
| wave_score final  | >= 0.70  | < 0.50     |

Update `enrich_wave_runs.verdict` after sample verification :
```sql
UPDATE enrich_wave_runs
SET fp_sample_size=20, fp_sample_failures=N, fp_rate=N::float/20,
    regression_count=R,
    wave_score=closure_rate*0.40 + (1-fp_rate)*0.40 + (CASE WHEN regression_count=0 THEN 1 ELSE 0 END)*0.20,
    verdict=CASE WHEN wave_score>=0.70 THEN 'GO' WHEN wave_score>=0.50 THEN 'PARTIAL' ELSE 'FAIL' END
WHERE wave_id='<id>';
```

### Triggers (sub-mode)

- Phrase : "vendor sync", "canonical vendor mapping", "remap legacy_id", "skip recovery liaprobe"
- Phrase scoring : "score vendor alias", "phase f1", "scoring proposals", "wave gate"
- Auto-invoque par `/apex` lors d'un cycle vendor_sync (separe enrichment)

### References

- `references/vendor_sync_workflow.md` -- workflow detaille 8-phases
- `references/cpe_classification.md` -- :a:/:h:/:o: trust table + incident 2026-05-03
- `references/skip_recovery_strategies.md` -- 5 strategies + adversarial guards
- `references/false_positive_corpus.md` -- regression test cases (CHKMK/BAMBO/NETSARANG)
- `migrations/147_product_name_indexes.sql` -- template indexes pre-flight
- `migrations/149_vendor_alias_score.sql` -- vendor_alias_score + enrich_wave_runs tables (Phase F1+ scoring)
- `scripts/score_aliases.py` -- scoring engine (4-component rubric + auto decision)
- `_alire/tracking/liaprobe-enrich-v2/recettes/pilot_50_kev_2026-05-03/brainstorm_phase_c/CONSOLIDATED.md` -- 6-agent brainstorm consolidated
- `_alire/tracking/liaprobe-enrich-v2/recettes/pilot_50_kev_2026-05-03/brainstorm_phase_f/agent6_adversarial_report.md` -- scoring rubric source
