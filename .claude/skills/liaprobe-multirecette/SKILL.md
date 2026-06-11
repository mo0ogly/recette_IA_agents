---
name: liaprobe-multirecette
description: Agentic OODA closed-loop recette of a LiaProbe fingerprint rule. Not just validation -- OBSERVE (detect app + extract exact version on live hosts + Onyphe corpora) -> ORIENT (coverage gaps, missing high-signal matchers, version->CPE->CVE exposure, engine capability gaps) -> DECIDE -> ACT (evolve the rule matchers through the recette-onyphe regression gate, correlate CVE from PostgreSQL, capture signed live evidence, surface engine evolutions). Per-rule durable working directory with a multi-session resumable SESSION journal -- NEVER _alire/temp. Keeps R4 (matchers changed only behind the recette-onyphe gate), R18 (verify facts), R10 (no emoji). Use when a fingerprint rule MISSes real hosts, when a rule must be driven up the recette_level ladder (DOCUMENTED->VERIFIED), to identify app+version and map to CVEs, or to evolve detection content safely. Triggers on "/liaprobe-multirecette", "multirecette", "recette cette rule", "pourquoi la rule rate ce host", "identifie version et CVE", "fais evoluer la rule", "valide le fingerprint sur du reel".
---

# LiaProbe Multirecette (agentic OODA)

Closed-loop recette of ONE LiaProbe fingerprint rule. Validates against multiple
real evidence sources, then ACTS: evolve the rule (gate-protected), extract the
version, correlate CVEs, capture signed evidence, surface engine gaps. Every run
persists to a per-rule durable directory and appends a multi-session journal so
work survives across sessions and is never lost in `_alire/temp`.

Tool: `scripts/multirecette.py`. Engine matcher mirror: `_alire/tracking/liaprobe-legal-provenance/tooling/onyphe_match.py`.

## Per-rule working directory (durable, multi-session) -- MANDATORY

All durable artifacts live under, NEVER in `_alire/temp`:

```
_alire/tracking/liaprobe-multirecette/rules/<rule_id>/
  PLAN.md                  # the OODA plan for THIS rule (persistent, step-checked)
  SESSION.md               # multi-session journal (auto-appended each run; resume here)
  contribution_*.md        # user's marker model / contribution for this rule
  verdict_<ts>.json        # each multirecette run (machine state)
  captures/                # live banner + sha (signed evidence, durable)
  recette/                 # recette-onyphe before/after runs
```

`multirecette.py` resolves this directory from the rule `id` automatically and
writes the verdict + capture + SESSION entry there. To RESUME a rule across
sessions: read its `SESSION.md` (newest entry at the bottom) and `PLAN.md` first.
`_alire/temp` is scratch only -- nothing durable goes there (user directive 2026-05-30).

### ONE trace file-set PER RULE -- audit at scale (thousands of rules)

The corpus has thousands of rules, so the audit unit is the RULE, never a
project-level monolith. EVERY `multirecette.py` invocation (OBSERVE, VERSION,
CVE, SUGGEST, and `--evolve`) auto-writes, keyed by `rule.id`, into
`rules/<rule_id>/` (no manual step, `main()` -> `workdir_for` + `append_session`
+ `verdict_<ts>.json`):

- `SESSION.md` : one multi-session line per run (newest at bottom). For an
  `--evolve` run the line carries `evolve: <STATUS> (CORRECT +d WRONG +d MISS +d)`.
- `verdict_<ts>.json` : full machine state of that run, incl. the `evolve` block
  (candidates, before/after, delta, regression, status).
- `recette/evolve_before.txt` + `recette/evolve_after.txt` : the raw BEFORE/AFTER
  recette-onyphe tables for that rule's gate.

So N rules under recette = N independent `rules/<id>/` trace dirs, each
self-contained + resumable. The project-root `PLAN.md` / `SESSION.md` are
skill-DEVELOPMENT meta only (tool evolution), NOT the per-rule audit -- the
per-rule files are the audit of record.

## USER contributions (marker model) -- ingested, persisted, multi-session

The user provides a CONTRIBUTION: a marker model (empreinte paths/headers/
cookies/generator, recon facets, ground-truth corpus, CVE/KEV) that frames the
audit. The skill INGESTS it durably and BINDS it to rule ids, then auto-loads it
on every run so the markers persist across sessions and are never lost.

```bash
# ingest a contribution doc and BIND it to a rule (+ optional section of a
# multi-CMS doc). Persisted verbatim in contributions/, bound via manifest.json.
multirecette.py --rule <rule.json> \
  --contribution _alire/tracking/liaprobe-multirecette/contributions/<doc>.md \
  --contribution-section WORDPRESS

# list the contributions bound to a rule (and exit)
multirecette.py --rule <rule.json> --contributions
```

- Store: `_alire/tracking/liaprobe-multirecette/contributions/` (raw docs +
  `manifest.json` bindings {rule_id, doc, section, sha256} + `INDEX.md` roadmap).
- A SINGLE doc may cover MANY rules (e.g. a multi-CMS corpus): bind it once per
  rule with `--contribution-section`.
- EVERY run (OBSERVE/VERSION/CVE/SUGGEST/evolve) auto-loads the bound
  contributions -> `verdict.contributions[]` + a `contribution(s):` line in the
  rule SESSION.md. So any future session knows which marker model frames the rule.
- Ingest is idempotent (same content + same binding = no duplicate). The raw doc
  is copied verbatim so it survives if the original source path vanishes
  (durable-work-in-temp loss class).

## OODA loop

```
OBSERVE  detect + extract version, on live host(s) and/or Onyphe corpora
   |       multirecette.py --rule R --live URL --corpus C --version --cve
   v
ORIENT   DETECT vs MISS ; fired/missing matchers ; suggested high-signal headers ;
   |       version -> CPE -> CVE exposure (KEV) ; is a needed capability missing
   |       in the engine (a probe path, a target) ?
   v
DECIDE   which matcher/probe to add (per the user marker model + engine schema) ;
   |       or which engine capability to drive ; or capture evidence if DETECT
   v
ACT      evolve the rule (edit matchers) -> recette-onyphe regression gate
   |       (keep ONLY if zero regression, else REPLAN) ; correlate CVE ;
   |       --apply signed capture on a genuine DETECT ; flag engine gap
   v
LOOP     re-OBSERVE until DETECT + version + CVE closed, or REPLAN on 2 failures
```

## Sources (one pass)

| Source | Network | Proves |
|---|---|---|
| OFFLINE | no | matchers vs real Onyphe banner corpora -> corroboration + FP-rate flag |
| LIVE | GET | fetch real host, score vs `confidence_threshold` -> DETECT/MISS + sha capture |
| VERSION | no | extract exact version (rule version matcher / X-Generator / CHANGELOG) |
| CVE | PostgreSQL | version -> CPE -> `cve_nvd_data` + KEV (read-only) |
| SUGGEST | no | high-signal headers the rule ignores (advice; R4 -- never auto-edits matchers) |

## Decomposition des sous-taches

Au demarrage, decomposer en sous-taches independantes :
- [ ] OBSERVE : run multirecette (offline + live + version + cve) -> verdict
- [ ] ORIENT : lire DETECT/MISS, suggestions, CVE exposure, engine gap
- [ ] DECIDE : choisir les matchers/probes a ajouter (modele user + schema engine)
- [ ] ACT : editer la rule + gate recette-onyphe + corroborer CVE + capture
- [ ] VERIFY : schema + zero regression + SESSION/PLAN a jour
Utiliser `TaskCreate` si > 3 sous-taches.

## Plan d'execution

Avant toute action, ouvrir/creer le PLAN per-rule :
`_alire/tracking/liaprobe-multirecette/rules/<rule_id>/PLAN.md`
(Status, OBSERVE/ORIENT/DECIDE/ACT/Result, Next). Cocher chaque etape.
Si REPLANIFIE : Status -> REPLANIFIE + raison. C'est aussi le point de reprise
multi-session (lire PLAN.md + SESSION.md avant de continuer).

## Adaptation et replanification

Si 2 etapes consecutives echouent (gate rouge 2x, MISS persistant apres 2 fixes) :
STOP -> invoquer `/replan` -> NE PAS improviser. Un matcher qui regresse au gate
recette-onyphe est TOUJOURS reverte (R4), jamais force.

## Outils declares

- `multirecette.py` (OBSERVE/VERSION/CVE/SUGGEST/--apply) -- choisi par defaut
- `bin/recette-onyphe -http-layer` (liaprobe) -- gate de regression ACT (BLOQUANT)
- `bin/lia-rule-validate -q -allow-disabled` -- schema gate
- `onyphe_match.py` -- moteur de match offline (mirror engine targets+field)
- `psql` via DATABASE_URL du systemd (jamais cache/log, R8) -- correlation CVE
- Retry policy : echec transitoire -> 1 retry -> sinon log + stop + signaler

Selection dynamique selon le contexte (live dispo ? corpus ? cpe23_template ?).

## ACT -- evolve a matcher (R4 gate, the only way matchers change)

1. Read the user marker model (`contribution_*.md`) + verify the engine supports
   the target (R18 -- grep `pkg/fingerprint/matcher.go` / `model.go`):
   - header value: `target:header, field:<Name>` (case-insensitive fallback)
   - cookie NAME pattern: `target:cookie` + empty field + regex value
   - body: `target:body` regex
   - exact version: `version_extract` + `version_group` (any matcher) ; multi-path
     active probe via `paths[]` + `stop_at_first_match`
2. Edit the rule. Add an audit block `matcher_change_multirecette`
   (removed/added/reason/model_source/date/marked_by). Never touch unrelated matchers.
3. GATE (BLOCKING): `bin/lia-rule-validate` schema PASS, then
   `bin/recette-onyphe -f <corpus> -http-layer -src all` BEFORE vs AFTER
   (stash the change for the baseline). Keep ONLY if CORRECT/WRONG/MISS do not
   regress. Any regression -> revert + REPLAN.
4. Re-OBSERVE: multirecette confirms DETECT on the previously-MISSed host.

## ACT -- automated evolve (`--evolve`, the gate-driven shortcut for step 1-3)

`multirecette.py --evolve` automates ACT step 1-3 for the high-signal HEADER
matchers that SUGGEST proposes. It turns each suggested header into a matcher
`{target:header, field:<Name>, match_type:regex, value:".+", confidence_delta}`
(header-exists fingerprint), then drives the R4 recette-onyphe regression gate
itself -- keep ONLY on zero regression, else auto-revert. No manual matcher
editing, the gate is the only path matchers change (R4).

```bash
# dry-run (default): build candidates -> gate BEFORE/AFTER -> ALWAYS revert + report
python3 .claude/skills/liaprobe-multirecette/scripts/multirecette.py \
  --rule /opt/lia-sec/liaprobe/patterns/web-signatures/JENKINS.json --suggest --evolve

# apply: KEEP the change on disk when the gate is green (then safe_commit)
python3 .claude/skills/liaprobe-multirecette/scripts/multirecette.py \
  --rule <rule.json> --suggest --evolve --evolve-apply
```

Flags:
- `--evolve` : build matchers from SUGGEST + run the gate (dry-run, always reverts).
- `--evolve-apply` : with `--evolve`, KEEP a green change on disk (else reverts + reports).
- `--evolve-delta` : `confidence_delta` per evolved header matcher (default 0.5).
- `--gt-corpus` : recette-onyphe `-f` corpus (default: durable HTTP appgt,
  `_alire/tracking/liaprobe-multirecette/_gt_corpus/http_appgt_3502.jsonl` --
  3502 HTTP banners ; the canonical `*.appgt.jsonl.zst` are RAW BINARY banners
  -> 100% NO_PATTERN under `-http-layer`, NOT usable for web-signature evolve).
- `--liaprobe-root` : repo root for recette-onyphe + lia-rule-validate
  (default `/opt/lia-sec/liaprobe` -- recette-onyphe loads `patterns/` relative
  to CWD, so the gate ALWAYS runs from there).

Gate mechanics (per run): backup rule -> recette BEFORE (on-disk) -> inject
matchers + `lia-rule-validate -q -allow-disabled` (REVERT on schema fail) ->
recette AFTER -> regression = `after.CORRECT<before.CORRECT OR after.WRONG>before.WRONG
OR after.MISS>before.MISS`. BEFORE/AFTER tables written to `<workdir>/recette/`.
Audit block `_lia_independent_authoring.matcher_evolve_multirecette` records the
added matchers + container + model_source. Cost ~6-8 min (two full recette runs,
each reloads 10712 patterns). E2E proven 2026-05-30 (JENKINS no-op candidate:
BEFORE==AFTER 2616/486/183, delta +0, byte-identical revert).

## ACT -- engine evolution (when a capability gap blocks detection)

If a needed marker has no engine support (a target type, a path-fetch behavior),
do NOT fake it. Record the gap in the verdict + PLAN (`engine_gap`), and drive a
Go change through `liaprobe-fingerprint-rebuild` (build_secure equivalent + the
recette-onyphe baseline). The skill surfaces the gap; the engine change is a
separate, gated Go task.

## Tracabilite agentique

- Each run auto-appends `SESSION.md` (multi-session resume) + writes `verdict_<ts>.json`.
- Log non-trivial decisions (matcher chosen, alternative rejected, engine gap) in
  `_alire/02_LOGS/Journals/decision_log.jsonl`.
- End-of-session RETEX in `_alire/02_LOGS/Journals/retex/` if score < 40/50.

## VERIFICATION GATE (BLOQUANT)

Avant de declarer termine :
- [ ] `bin/lia-rule-validate -q -allow-disabled <rule>` -> PASS
- [ ] recette-onyphe BEFORE vs AFTER -> zero regression (CORRECT/WRONG/MISS)
- [ ] `--apply` ecrit verified=true UNIQUEMENT sur un DETECT live reel (jamais sur MISS)
- [ ] version extraite coherente (ou fallback documente) ; CVE correle si cpe23_template
- [ ] PLAN.md + SESSION.md du rule a jour (rien de durable dans `_alire/temp`)
Si un gate echoue : STOP, fix, re-gate.

## RESUME (state of record -- a new session CONTINUES, never restarts)

This is an ONGOING program. Everything is committed (tooling, SKILL, gate hook,
ledger, per-rule evidence) -- a new session resumes from disk, it does NOT redo
the build-up. To continue the drain in ONE autonomous self-committing loop:

```bash
cd /opt/lia-sec/dev
export DATABASE_URL="$(systemctl cat lia-backend | sed -n 's/^Environment=DATABASE_URL=//p')"
PY=/home/liadev/.local/share/pipx/venvs/scrapling/bin/python
TOOL=_alire/tracking/liaprobe-multirecette/tooling
$PY $TOOL/rule_recette_status.py            # regen ledger (stamped rules leave NONE)
$PY $TOOL/wave_recette.py --deployable-only --no-evolve --commit --loop \
    --wave-size 8 --throttle 10              # drains until queue empty, self-commits
```

- STATE OF RECORD: `reports/PROGRESS.md` (auto-refreshed each wave: totals, queue,
  ETA, LIVE roster, per-wave heartbeat). Read it FIRST to see where we are.
- `--loop` runs waves back-to-back, cleaning orphaned chromium BETWEEN waves
  (the exit-144 SIGTERM cause), so it is a single durable background job -- no
  per-turn relaunch. Watch `reports/PROGRESS.md` + `reports/wave_heartbeat.jsonl`.
- A full multi-agent Workflow is NOT needed here: the bottleneck is SERP/HTTP I/O,
  not reasoning -- one looping python process is the right tool, agents would only
  add overhead.

## Online discovery + live verification (Scrapling, optional premium tier)

The offline loop drives NONE -> DOCUMENTED at scale (CVE + matcher audit, no host
traffic). To reach LIVE_VERIFIED, `online_verify.py` EXECUTES a discovery dork to
find real running deployments, then GET-verifies each:

```
rule -> synth_dork (AUTO, from the rule's own matchers -- NO hardcoded dork)
     -> stealth_google.py SERP engine chain: SearXNG -> DuckDuckGo -> Bing
     -> candidate host URLs -> editorial filter -> multirecette --live <url> (GET)
     -> first signed DETECT >= threshold = LIVE_VERIFIED (else stays DOCUMENTED)
```

```bash
# ONE rule, full auto (synth_dork + ladder + SearXNG). No --dork hardcode.
python3 _alire/tracking/liaprobe-multirecette/tooling/online_verify.py \
  --rule <rule.json> --candidates 8
# re-recette KNOWN hosts (no fresh SERP)
python3 .../online_verify.py --rule <rule.json> --reuse
# SCALE: drain the deployable NONE backlog in bounded self-committing waves
python3 _alire/tracking/liaprobe-multirecette/tooling/wave_recette.py \
  --deployable-only --no-evolve --commit --wave-size 8 --throttle 40 --offset 0
```

NO HARDCODED DORKS (user directive 2026-05-31, repeated). The dork is SYNTHESIZED
from the rule's own fingerprint by `synth_dork(rule)` in online_verify.py -- never
typed by hand, never per-product in code. `dork_map.json` is an OPTIONAL curated
override (claude_dork) tried first if present, but the pipeline runs fully without
it. Hand-typing a dork to "test" a product burns tokens for nothing -- always go
through `online_verify.py --rule` so the AUTO path is exercised.

SERP ENGINE -- SearXNG primary (the real unblock, verified 2026-05-31):
- `stealth_google.py --engine searxng` (DEFAULT) queries a chain of public SearXNG
  instances (`_SEARXNG_INSTANCES`: search.disroot.org, search.hbubli.cc, paulgo.io,
  opnxng.com). Each PROXIES the upstream Google index from ITS OWN server IP, so
  it returns Google's RICH index AND honors Google operators (`inurl:`, `intitle:`,
  `intext:`, quoted phrases), while being reachable from a VPS that Google 429s
  directly. First instance that returns results wins; a 429/503/short page rolls to
  the next instance, then to DuckDuckGo lite, then Bing.
- Google DIRECT (`--engine google`) is 429-walled on the VPS datacenter IP (hard,
  not just burst -- a single query 429s once the IP is flagged). It is NOT the
  primary. SearXNG sidesteps this because the query egresses from the instance IP.
- DuckDuckGo lite (`lite.duckduckgo.com/lite/`) and Bing are fallbacks: reachable
  (no /sorry wall) but THIN index for niche products and they do NOT honor Google
  operators (online_verify `_plainify` strips operators for them). Good as a net,
  weak as a primary.
- Proof (full auto path, zero hardcode): abantecart synth_dork
  `"Powered by AbanteCart"` via SearXNG returned 8 REAL storefronts
  (`index.php?rt=...` runtime URLs) -> one fired the matcher -> LIVE_VERIFIED.

DORK LADDER (online_verify, auto -- surface the RUNTIME, not the name).
ORDER MATTERS (fixed 2026-05-31, see UPTIME_KUMA incident below):
1. the rule's own synth_dork MARKER (inurl/intitle/intext built from the
   matchers, e.g. `inurl:"/status" intitle:"Uptime Kuma"`) -- the deployment-
   specific query that anchors on the RUNTIME signature and hits a RUNNING
   instance. This is rung 1 because it is robust to common-word products.
2. `"Powered by <Product>"` footer string -- works for storefronts that print
   it (e.g. AbanteCart), but DEMOTED to rung 2: with a multi-word / common-word
   product the SERP loose-matches a common token ("powered") and returns
   DICTIONARY pages, never an instance.
3. broad `"<Product>"` name -- last resort, editorial-heavy.
First rung that yields REAL (post-filter) candidates wins; stop there.

UPTIME_KUMA INCIDENT (2026-05-31, R18 -- proven by command): with rung 1 =
`"Powered by Uptime Kuma"`, SearXNG returned 8 DICTIONARY definitions of the word
"powered" (merriam-webster, dictionary.com, oxford...) -> 0 LIVE. Reordering to
marker-dork rung 1 (`inurl:"/status" intitle:"Uptime Kuma"`) returned 8 REAL
status pages (status.kuma.pet, status.10101.io...) -> LIVE_VERIFIED on first.
A whole STRONG-front wave went 0% -> 25% LIVE after the reorder.

EDITORIAL FILTER (online_verify `_keep` + stealth_google `_SKIP_HOST`) drops the
pages that DISCUSS a product instead of RUNNING it, so the live-GET reaches a real
instance: CVE/vuln DBs (nvd.nist.gov, cvedetails, vulners), software directories /
review aggregators (g2, capterra, sourceforge, softwareadvice, slashdot), app
stores (appadvice, apps.apple, play.google), install-tutorial / hosting blogs
(geekrewind, hostpapa, howtoforge, digitalocean), TECH-FINGERPRINT / LEADS
aggregators (whatruns, storeleads, builtwith, similartech, publicwww, netcraft,
similarweb, datanyze -- they LIST sites running the product, they don't RUN it),
DICTIONARIES / reference (merriam-webster, dictionary.com, thefreedictionary,
wiktionary -- a loose-matched common word lands here), and content PATHS (/blog,
/install, /setup, /how-to, /docs, /review, /cve...). SearXNG infra hosts
(searx*, disroot, web.archive, ko-fi) are skipped too.

QUEUE RANK -- STRONG self-hosted FIRST (wave_recette `_hosting_rank`, 2026-05-31):
deployable web-sig NONE are ranked 2=STRONG (self-hosted app a dork resolves to a
RUNNING instance: cms/portal/store/admin/monitoring/git/wiki/forum/crm...),
1=WEAK (generic ecommerce/platform), 0=EMBED (theme/plugin/widget/tag/analytics/
affiliate -- a JS snippet loaded on someone ELSE's site, NOT dork-resolvable to an
instance -> EXCLUDED from deployable). Token-matched (NOT substring: "erp" must
not match "interpretation"); EMBED DOMINATES (a "cms"-tagged theme is still a
theme -> rank 0). select_todo sorts STRONG before WEAK so the LIVE-able apps are
drained first. ~151 STRONG self-hosted apps were the real LIVE headroom; the tail
was widget-flooded (0-LIVE) before this rank.

COMMIT (wave_recette `--commit`): safe_commit (R28) requires paths RELATIVE to the
-C root -- the loop passes `os.path.relpath(p, LIAPROBE_ROOT)`, NOT the absolute
path (an absolute path makes safe_commit abort on an empty exact-match set, so
stamps silently never commit). Fixed 2026-05-31 (244-stamp backlog had
accumulated uncommitted, incl. 12 real LIVE).

DORK DOCTRINE -- anchor on the RUNTIME (app/asset/footer), NOT the name or login:
- a dork is a DISCOVERY anchor (find a host where the product RUNS), not a source
  of fingerprint info. The info comes from the VERIFY step on the host ROOT
  (headers, cookies, meta generator) -- online_verify always GETs the host root.
- a "Powered by <Product>" footer or a unique runtime PATH (`index.php?rt=`,
  `/wp-json/`, `/-/media/`, `/secure/Dashboard.jspa`, `/content/dam`) outranks a
  bare product name (which surfaces articles) and a bare `/login` (minimal,
  WAF/SSO-gated, content-indexed). synth_dork prefers visible-text / path markers
  for exactly this reason.

WILD INDEX IS REAL, NOT A LIMIT (R18-corrected, verified 2026-05-31). A prior
version of this skill claimed (a) devops tools "are not Google-indexed" and
(b) "editorial dominance is a hard limit, near-zero LIVE yield". BOTH were FALSE
DEDUCTIONS, retracted. Verified by command: SearXNG + auto synth_dork lands real
deployments at ~12%/wave LIVE (abantecart, afterpay, the_events_calendar via the
auto path, zero manual host). The earlier 0-LIVE waves were the Google 429 + thin
DDG-index + weak name-dork stack BEFORE the SearXNG/ladder/filter fixes -- a
TOOLING gap, not a no-index reality. NEVER bake "blocked / not indexed / hard
limit" into a RETEX from a failed run: fix the channel (engine, dork, filter)
and re-verify.

USER-PROVIDED HOST = first-class LIVE channel (no SERP needed). When the user
gives a host (or a vendor demo / owned host), verify the ROOT directly with
multirecette `--live <url>` (GET passive, read-only, never auth/POST). Fastest
path to a signed DETECT; immune to any SERP throttle. The devops LIVE wins
(SonarQube sonarcloud.io, Grafana play.grafana.org, Jenkins ci.jenkins.io,
Nexus ec.europa.eu, GitLab invent.kde.org) used this channel; some also needed a
matcher evolve (a hardened instance strips the version header but always returns a
product-token header, e.g. Artifactory `X-Artifactory-Id`) via SUGGEST +
`--evolve --evolve-apply` through the recette-onyphe R4 zero-regression gate.

HOST SCRUB (never leak a third-party host to the PUBLIC liaprobe repo). The rule
stamp carries ONLY the signed sha256 evidence + a private-evidence ref pointing at
`_alire/tracking/liaprobe-multirecette/rules/<id>` (dev repo, internal). The live
host string is NEVER written into the public rule (capture_url / verified_url =
the private ref). multirecette `--apply` scrubs the host automatically; the
pre-commit multirecette anti-leak gate blocks a leak.

SCALE (wave_recette.py). Drives bounded waves over the deployable NONE backlog:
`--deployable-only` keeps web-signatures whose tags/product look like a real
deployable (CMS/portal/ecommerce/monitoring), drops embed-only (cdn/widget/lib);
dorkability ranking front-loads rules whose synth_dork has a path/body anchor;
`--commit` self-commits each wave (safe_commit exact-file, R28, host-scrubbed).
Run in BOUNDED waves (size ~5-8) per turn, clean orphaned chromium BETWEEN waves
(never mid-wave -- orphan chromium accumulation = memory pressure = exit-144
SIGTERM), relaunch on completion until drained.

### Discovered-host inventory (durable, per rule) -- audit / re-recette

Every `online_verify` run persists the candidate hosts it found into
`rules/<id>/discovered_hosts.json` (schema `lia-discovered-hosts-v1`, URLs only,
NO bodies -- private dev tracking, never the public liaprobe repo). Each host:
`{first_seen, last_checked, last_level, detected, dork}`. This inventory is
COMMITTED (not gitignored) so an audit or a future re-recette REUSES the known
hosts (`--reuse`) instead of re-discovering them. A host that MISSed today is kept
-- a later rule tightening or a host change may DETECT it next pass.

## Tracking map -- where proof / engine-test / status live

Single source: `_alire/tracking/liaprobe-multirecette/TRACKING_MAP.md`. Two axes,
do not confuse: RECETTE (this skill) vs AUTHORING (fingerprint-rebuild nightly).

| What | Where |
|------|-------|
| per-rule proof (hashes, favicon, version, CVE) | `rules/<id>/verdict_*.json` + `captures/` |
| per-rule engine test (recette-onyphe) | `rules/<id>/recette/evolve_*.txt` |
| GLOBAL status list (1 row/rule) | `reports/RULE_RECETTE_STATUS_<date>.csv` + `.md` |
| regen the list | `tooling/rule_recette_status.py` |

## Status stamp IN the rule JSON (default ON)

Each durable run writes `_lia_independent_authoring.recette` INTO the rule JSON
so the status is visible in the rule itself, not only in tracking. The stamp is
the ledger's authoritative source (read first, else derived from verdicts).

- level ladder: `DOCUMENTED` (offline/version/evidence) -> `LIVE_VERIFIED` (live DETECT).
- NON-DOWNGRADING: a run never lowers an already-stamped higher level.
- LEAK-SAFE: stamp = `{level, verified_at, tool, evidence_ref}` where
  `evidence_ref` is the dev-private workdir relpath -- NEVER a host / IP / body.
- disable per run with `--no-stamp`.
- backfill the whole corpus: `rule_recette_status.py --stamp` (writes the derived
  level into every processed rule; mutates the liaprobe repo, archive copies skipped).

## Anti-leak GATE (BLOCKING) -- no rule's recette escapes tracking

```bash
python3 _alire/tracking/liaprobe-multirecette/tooling/rule_recette_status.py --gate
```

Exit 0 = clean. Exit 3 = LEAK. A leak is any of:
1. durable artifact (`verdict_*.json` / `capture_*.jsonl` / `evolve_*.txt`) found
   under `_alire/temp` or `/tmp` instead of `rules/<id>/` (work would be lost);
2. a per-rule workdir with no verdict (effort done, proof invisible in the list);
3. a verdict for an id absent from the live corpus (dangling -- archived/renamed).
Run `--gate` before closing a recette session; fix the leak, never bypass.

ENFORCED at pre-commit: `.githooks/pre-commit` (+ live `.git/hooks/pre-commit`,
byte-identical twins) runs the gate automatically, delta-scoped -- only when a
`_alire/tracking/liaprobe-multirecette/` file is staged. A leak BLOCKS the commit
(exit 1). Tracking-only commits are covered (gate runs before the Go/TS early-exit).

## Finding live hosts (recon passif, user-authorized)

URL fournie par l'utilisateur ou dork (l'utilisateur autorise). GET only, lecture
seule, jamais d'auth/POST/exploit, jamais vers un tiers au-dela de l'inventaire.
NE PAS committer une IP tierce dans un repo public (liaprobe public) : capturer
sur un host possede ou une demo vendeur pour promouvoir VERIFIED.

### Per-rule evidence contract (MANDATORY, auto-enforced) -- hashes + favicon + version + CVE + final engine test

Every `--live` run now records a full evidence bundle into the per-rule workdir
and writes an explicit `TODO.md` for whatever is missing, so nothing is silently
skipped (user directive 2026-05-30):

| Signal | How | Where |
|---|---|---|
| Capture hashes | sha256 + md5 of body AND headers (`multi_hash`) | `verdict.evidence` + `captures/*.jsonl` `hashes` block |
| Favicon hash | `<origin>/favicon.ico` -> sha256 + md5 + mmh3 (Shodan-style) | `verdict.evidence.favicon`, SESSION line (default ON; `--no-favicon` to skip) |
| Version | `--version` (rule version matcher / X-Generator / CHANGELOG) | `verdict.version`; if absent -> TODO |
| CVE | `--cve` -> PostgreSQL `cve_nvd_data` + `cve_product` + KEV (R5, CVEs live in PG) | `verdict.cve`; if absent/no cpe -> TODO |
| Final engine test | recette-onyphe `-http-layer` BEFORE/AFTER (zero regression) | manual gate; absence -> TODO |

`build_todo()` emits a TODO for: LIVE MISS, VERSION not extracted, CVE not
correlated, FAVICON missing, FINAL ENGINE TEST not run. `write_todo_md()`
persists them to `rules/<id>/TODO.md` (newest at bottom). The TODO survives
across sessions -- the audit gap is never lost.

If a needed signal has no engine support (e.g. a favicon-hash matcher target),
that is an ENGINE GAP: record it in TODO.md and drive the Go change through
`liaprobe-fingerprint-rebuild` (the engine must learn to match the signal --
favicon sha256/md5/mmh3 targets). The skill surfaces the gap; the engine change
is a separate gated Go task.

### Anti-bot live fetch (`--stealth`) -- reach WAF-protected hosts

The default `--live` fetch (urllib, browser-like UA) is HTTP 403'd by Cloudflare
managed challenge / Akamai on a large share of real CMS hosts, so a genuine
DETECT could never be observed there. `--stealth` routes the fetch through the
anti-bot stealth engine (Scrapling StealthyFetcher, solves the Cloudflare
turnstile) and returns the rendered response, so the live recette gate can score
the rule against a WAF host.

```bash
# WAF host: default fetch 403 -> stealth 200, real verdict
python3 .claude/skills/liaprobe-multirecette/scripts/multirecette.py \
  --rule <rule.json> --live "https://<waf-host>/" --stealth --version
```

Backend: `tooling/stealth_fetch.py` runs in the Scrapling pipx venv
(`~/.local/share/pipx/venvs/scrapling`); multirecette subprocesses it and reads
JSON `{status, headers, body, html_sha256}`. One-time setup:
`pipx install scrapling && python -m playwright install chromium`. GET-only,
read-only -- no auth/POST/exploit. The rendered body of a third-party host is
durable evidence under the PRIVATE LIA-SEC tracking tree only (rules/<id>/
captures/), NEVER committed to the public liaprobe repo.

Proven 2026-05-30 (dnn): `commongroundalliance.com` urllib 403 -> stealth 200 ->
MISS 0.5/0.65 surfaced a real meta-generator precision bug (3 causes observed in
the capture) -> fixed + recette-onyphe gate zero regression -> live re-verify
DETECT 1.25/0.65.

### Passive discovery dorks DERIVED from the rule (scale to thousands of rules)

Hand-writing discovery dorks per rule never finishes on a corpus of thousands.
The skill GENERATES them from the rule's own matchers (clean-room R13, no
third-party catalog) so a candidate-host list exists for every fingerprint:

```bash
# first-class: emit the sheet into the durable per-rule workdir (audited, multi-session)
python3 .claude/skills/liaprobe-multirecette/scripts/multirecette.py \
  --rule <rule.json> --dorks
# -> rules/<id>/discovery_dorks.md + verdict + SESSION line

# standalone (one rule, many rules, or a whole dir):
python3 _alire/tracking/liaprobe-multirecette/tooling/gen_discovery_dorks.py \
  --dir /opt/lia-sec/liaprobe/patterns/web-signatures \
  --out _alire/tracking/liaprobe-multirecette/reports/DISCOVERY_DORKS_<scope>.md
```

What it derives, per engine, from `probes[].matchers` + `banner/service_matchers`:
- body/title path literals -> Google `inurl:<path>` + Shodan `http.html:"<path>"`
- body content tokens -> Google `intext:"<tok>"` (generic stopwords dropped)
- header `field` names -> Shodan `"<Name>:"` + ONYPHE `category:datascan "<Name>"`
- response/banner tokens -> Shodan / ONYPHE banner search
- product (`product`/`taxonomy_name`/cpe) -> Shodan `http.component`/`product`,
  ONYPHE `category:datascan product:"<P>"`

PASSIVE ONLY: every query hits a SEARCH ENGINE that already collected the data --
zero request reaches a candidate host. NO admin/login/console paths are emitted
(`_FORBIDDEN_PATH` strips admin/login/console/install/manager/...). The hosts a
dork returns are then fed to `--live <url>` (GET-only) for the detection gate.
The product line (Shodan `http.component` / ONYPHE `product`) is the most
reliable passive path -- prefer it over Google for clean, reproducible,
exportable host lists per fingerprint.

## Scoring agentique (/50)

| Critere | Score |
|---------|-------|
| C1 Decomposition : sous-taches OODA identifiees ? | /10 |
| C2 Planification : PLAN.md per-rule cree et suivi ? | /10 |
| C3 Replanification : /replan + revert au gate sur echec ? | /10 |
| C4 Outillage : multirecette + recette-onyphe + psql choisis selon contexte ? | /10 |
| C5 Tracabilite : SESSION.md multi-session + decision_log + verdict ? | /10 |

>= 40 Exemplaire | 30-39 Acceptable | < 30 RETEX obligatoire.

## Worked example -- drupal_drpl (2026-05-30)

`rules/drupal_drpl/PLAN.md` + `SESSION.md`. OBSERVE: favicon_hash matcher is
theme-dependent (misses most instances). ORIENT: robust model = headers + SESS
cookie + body paths + CHANGELOG exact version; engine supports all. DECIDE+ACT:
removed favicon, added `^S?SESS[0-9a-f]{32}$` cookie + `Drupal.settings` +
`/core/misc/drupal.js` body + `drupal_changelog` multi-path version probe. GATE:
recette-onyphe A139 zero regression (CORRECT 2616 before==after). CVE: 15
(7 KEV incl Drupalgeddon2/3, CVE-2019-6340). Jenkins precedent (rules/jenkins_jenkins):
MISS on anon-dashboard -> added X-Jenkins header -> engine CORRECT.

## Related

- `liaprobe-fingerprint-rebuild` (engine Go changes + recette-onyphe baseline)
- `liaprobe-rule-enrich` (cpe23 -> known_cves enrichment cycles)
- `_alire/tracking/liaprobe-legal-provenance/tooling/` (onyphe_match, evidence_strength, build_rule_tracking)
- `.claude/rules/agentic-traceability.md`, `.claude/skills/replan/SKILL.md`
