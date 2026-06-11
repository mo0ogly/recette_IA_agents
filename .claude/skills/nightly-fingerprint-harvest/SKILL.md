---
name: nightly-fingerprint-harvest
description: Run a nightly batch that picks LiaProbe JSON fingerprint rules still missing real-world evidence (artifacts.html_sha256 or capture_url empty, http_gate.verified=false) and captures fresh HTTP responses, TCP banners, and TLS-cert hostnames from free-tier external sources (Netlas, Censys, ZoomEye, crt.sh, PublicWWW, Rapid7 Sonar offline). Stores per-rule evidence packages with SHA-256 hashes under _alire/tracking/liaprobe-fingerprint-rebuild/nightly/DATE/RULE_ID/SOURCE_HOST/ plus an append-only manifest, ready for downstream consumption by the APEX cycle or /liaprobe-rule-enrich and /recette-lia-rule skills to promote artifacts fields and flip http_gate.verified=true. Use this skill when the user says "nightly harvest", "harvest fingerprints", "collecte des preuves nightly", "alimente le rebuild liaprobe", "trouve des serveurs reels pour ces JSON", or when scheduling a recurring resource discovery job that feeds the LiaProbe fingerprint rebuild pipeline (cycle 39+).
---

# Nightly Fingerprint Harvest

## Overview

The LiaProbe fingerprint corpus (`patterns/lia/*.json`,
`patterns/web-signatures/*.json`, `patterns/banner-signatures/*.json` plus
`_alire/tracking/liaprobe-fingerprint-rebuild/master_data/*.json`) contains
~16 900 rules. Many lack a verified real-world capture
(`artifacts.html_sha256 = null`, `_lia_independent_authoring.http_gate.verified = false`).

This skill runs a nightly batch that, for a budget-controlled subset of
rules, queries free / paid-low-tier external sources to capture fresh
evidence (HTTP body, headers, TCP banner, hostname pool from TLS certs).

The skill does NOT modify any rule JSON. It produces evidence packages
that the next APEX cycle (or the `/liaprobe-rule-enrich` and
`/recette-lia-rule` skills) read to promote `artifacts.*` fields and
flip `_lia_independent_authoring.http_gate.verified` to `true`.

## Architecture (multi-agent)

| Step | Role | Responsibility |
|------|------|----------------|
| 1. Plan | PLANNER | Read scoring config, create `PLAN_nightly-fingerprint-harvest_<DATE>.md`, identify rule selection criteria |
| 2. Selection | OBSERVER | Iterate 4 target dirs, keep rules where `needs_capture(rule) == true`, sort by vendor/product |
| 3. Quota check | GUARD | Read `.state/quotas.json`, skip sources that hit daily/monthly cap |
| 4. Harvest | EXECUTOR | For each (rule, source) tuple, call collector.search(), enforce timeouts, never raise |
| 5. Match | ANALYST | Apply rule's probes against captured body/headers/banner, score per matcher |
| 6. Persist | LIBRARIAN | Write evidence package + append to `nightly_manifest.jsonl` + persist quota state |
| 7. Verify | AUDITOR | Run VERIFICATION GATE (smoke test manifest readable, captures non-empty) |

## Quick start

Dry-run (no live calls, prints what would be queried):
```bash
python3 .claude/skills/nightly-fingerprint-harvest/scripts/nightly_run.py \
    --dry-run --max-rules 3 --sources netlas,crtsh
```

Live nightly with default budget:
```bash
# Sources requiring auth use env vars (NETLAS_API_KEY etc.)
python3 .claude/skills/nightly-fingerprint-harvest/scripts/nightly_run.py \
    --max-rules 30 --max-hosts 3 \
    --sources netlas,crtsh,publicwww,censys,zoomeye,rapid7_sonar
```

## Source priority and quotas

| Source | Auth env var | Free quota | Notes |
|--------|--------------|------------|-------|
| netlas | `NETLAS_API_KEY` | 50/day | Tier 1, best body+headers |
| crtsh | none | unlimited | Tier 1, hostnames only |
| publicwww | none | 50/day | Tier 2, literal-needle search |
| censys | `CENSYS_API_ID`+`CENSYS_API_SECRET` | 250/month | Tier 2, deep TLS |
| zoomeye | `ZOOMEYE_API_KEY` | 500/month | Tier 3, banner+headers |
| rapid7_sonar | `RAPID7_SONAR_PATH` | offline | Tier 4, bulk historical |

Quota tracker auto-skips sources that hit daily/monthly cap. See
`references/sources/<name>.md` for syntax and full API doc per source.

## Rule selection criteria

A rule is harvested tonight if ANY of:

1. `artifacts.html_sha256` is `null` or missing.
2. `artifacts.capture_url` is empty or starts with `documented_`.
3. `_lia_independent_authoring.http_gate.verified` is not `true`.
4. The rule has at least one `L7_HTTP` or `L4_TCP` probe (so we have a
   pattern to validate the captured response against).

Implementation: `scripts/lib/rule_loader.py::needs_capture()`.

## Evidence layout

See `references/evidence-schema.md` for full details. Summary:

```
_alire/tracking/liaprobe-fingerprint-rebuild/nightly/
  <YYYY-MM-DD>/
    nightly_manifest.jsonl      # append-only index of all captures
    <rule_id>/
      <source>_<host_sha8>/
        meta.json               # capture_url, sha256, http_status, banner...
        raw.bin                 # HTTP body or TCP payload
        headers.txt             # HTTP headers
        derived.json            # rule probes applied -> match_score
  .state/
    quotas.json
```

## Downstream contract

See `references/downstream-contract.md`. Summary:

- APEX cycle reads `nightly_manifest.jsonl`.
- For each row with `any_probe_matched=true`, promote `meta.html_sha256`
  + `meta.capture_url` into the rule's `artifacts.*` block.
- Set `_lia_independent_authoring.http_gate.verified=true`.
- Drop `wild_traffic_unconfirmed`.
- Commit the JSON update with the manifest path referenced as evidence.

## Scheduling

See `references/scheduling.md`. Recommended: systemd timer firing
`nightly_run.py` at 02:00 with `--max-rules 30 --max-hosts 3`.

## Configuration

API keys live in environment variables, never in committed files.

Template `.env` (gitignored, sit next to SKILL.md):
```env
NETLAS_API_KEY=
CENSYS_API_ID=
CENSYS_API_SECRET=
ZOOMEYE_API_KEY=
RAPID7_SONAR_PATH=/opt/lia-sec/datasets/sonar_https_443.json.gz
```

R8 enforced: API keys must come from env or PostgreSQL `system_variables`,
never literals in source code.

## Decomposition des sous-taches

When invoked, decompose into:

- **S-A Inventaire** : `iter_rules()` across 4 dirs, filter via `needs_capture()` (Read/Glob).
- **S-B Quota check** : load `quotas.json`, compute remaining budget per source (Read).
- **S-C Per-rule loop** : for each rule, iterate sources by priority, call collector.search() (Bash python3).
- **S-D Match** : apply rule probes via `run_match()`, compute `match_score` (Bash python3).
- **S-E Persist** : `write_evidence()` per capture, append manifest, save quota state (Write).
- **S-F Verify** : VERIFICATION GATE below (Bash).

Dependencies: B depends on A. C/D/E run in a per-rule pipeline. F depends on E completing for all rules.

## Plan d'execution

Before any harvest run, create the persistent plan:
```bash
DATE=$(date +%Y-%m-%d)
cp _alire/tracking/PLAN_TEMPLATE.md \
   _alire/tracking/PLAN_nightly-fingerprint-harvest_${DATE}.md
```
Tick each step `[x]` on completion. If 2 collectors return only errors,
mark Status = REPLANIFIE and invoke `/replan`. On clean run, mark
Status = TERMINE and append the `Resultat` block:
- rules selected
- captures persisted
- per-source success/error counts
- top 5 unmatched rules (potential FP candidates)

## Adaptation et replanification

- **1 echec** par source: retry once with `max_hosts=1`, then continue.
- **2 echecs consecutifs** sur la meme source: skip cette source pour le
  run, log `action="SOURCE_DISABLED_RUN"` dans `decision_log.jsonl`.
- **Toutes les sources echouent** sur > 30% des rules: STOP, invoquer
  `/replan`, NE PAS improviser de fix ad-hoc.
- **Quota exhausted mid-run**: continue avec les autres sources, sauve
  `quotas.json` au moment de l'epuisement.
- **JSON rule failing to parse**: log via warning, ne PAS supprimer le
  fichier, ne PAS bloquer le batch.

`/replan` produces `PLAN_nightly-fingerprint-harvest_REPLAN_<DATE>.md`.

## Outils declares

- **Read** : rule JSON files (paths known after `iter_rules()`).
- **Glob** : `patterns/**/*.json` initial scan.
- **Bash** : invoke `nightly_run.py`, post-run verification, view
  manifest tail.
- **Edit** : nightly skill code patches (rare).
- **Write** : evidence files (handled by `evidence_writer.py`, not direct).

Selection rules:
- Path connu + lecture seule -> Read
- Pattern dir -> Glob
- Execution scripts -> Bash (python3)
- Modification d'un script existant -> Edit

Retry policy : 1 retry sur Bash timeout pour les collectors. 2eme echec
=> skip source pour ce run et log.

## Tracabilite agentique

Log non-trivial decisions in `_alire/02_LOGS/Journals/decision_log.jsonl`:

```bash
echo '{"timestamp":"'$(date -u +%Y-%m-%dT%H:%M:%SZ)'","session":"nightly-harvest","action":"SOURCE_DISABLED_RUN","reasoning":"...","alternatives_rejected":[],"outcome":"...","confidence":"high","plan_ref":"PLAN_nightly-fingerprint-harvest_*.md"}' \
  >> _alire/02_LOGS/Journals/decision_log.jsonl
```

Emit a RETEX in `_alire/02_LOGS/Journals/retex/RETEX_nightly-harvest_<DATE>.md`
when:
- Score agentique < 40/50, OR
- Any source produced zero captures despite > 5 attempts, OR
- A rule looped through > 3 sources without a single matching capture.

## VERIFICATION GATE (BLOQUANT)

After `nightly_run.py` exits, BEFORE declaring done:

- [ ] Manifest file `nightly/<DATE>/nightly_manifest.jsonl` exists and
      has at least 1 line, OR the run was dry-run.
- [ ] `quotas.json` has been updated (mtime newer than run start).
- [ ] For each captured rule directory, `meta.json`, `derived.json` are
      readable JSON (no parse error).
- [ ] No collector raised an unhandled exception (orchestrator catches
      and turns into `CollectorResult.error`; manual inspection of the
      log shows zero `Traceback`).
- [ ] `quota_tracker.QUOTAS` table is in sync with actual tier limits.

If ANY gate fails: STOP, fix, re-run.

## Scoring agentique

| Critere | Description | Score |
|---------|-------------|-------|
| C1 Decomposition | S-A..S-F identified before run | /10 |
| C2 Planification | `PLAN_*.md` created and ticked | /10 |
| C3 Replanification | Failures triggered REPLAN, no silent fix | /10 |
| C4 Outillage | Python collectors with shared base contract, env-driven auth | /10 |
| C5 Tracabilite | `decision_log.jsonl` + manifest + per-rule meta.json | /10 |

Total : /50 — >= 40 : Exemplaire | 30-39 : Acceptable | < 30 : RETEX
obligatoire.

## Files

- `scripts/nightly_run.py` — orchestrator entry point
- `scripts/lib/quota_tracker.py` — daily/monthly call budget per source
- `scripts/lib/rule_loader.py` — JSON rule iteration + selection
- `scripts/lib/match_runner.py` — apply rule probes to captures
- `scripts/lib/evidence_writer.py` — persist evidence + manifest
- `scripts/collectors/` — one file per source (netlas, censys,
  zoomeye, crtsh, publicwww, rapid7_sonar)
- `references/sources/*.md` — auth, quotas, query syntax per source
- `references/evidence-schema.md` — output layout contract
- `references/downstream-contract.md` — what APEX / recette read
- `references/scheduling.md` — systemd timer / cron template
