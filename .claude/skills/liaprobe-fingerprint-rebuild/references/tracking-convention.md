# Tracking Convention -- liaprobe-fingerprint-rebuild

## Root structure

All artifacts for this skill live under ONE root :

```
_alire/tracking/liaprobe-fingerprint-rebuild/
|-- SESSIONS_INDEX.md                    Master table of all batches
`-- sessions/
    `-- <YYYY-MM-DD>_<batch_slug>/       1 batch = 1 subdir, NEVER mix
        |-- SESSION.md                   Batch manifest (REQUIRED)
        |-- PLAN_<batch>.md              Initial plan (REQUIRED)
        |-- PLAN_<batch>_REPLAN_<N>.md   On REPLAN trigger (optional)
        |-- journal.jsonl                Append-only per-rule audit
        |-- decisions.md                 Architectural decisions per batch
        |-- proposals_<batch>.json       Input rule list with priority
        `-- captures/                    Transient artifacts (gitignored)
            `-- <PRODUCT_SLUG>/
                |-- page.html
                |-- favicon.ico
                |-- headers.txt
                `-- mmh3.txt
```

## SESSIONS_INDEX.md format

```markdown
# liaprobe-fingerprint-rebuild -- Sessions Index

| Date | Batch | Verdict | Rules Authored | Cumul | SESSION |
|------|-------|---------|----------------|-------|---------|
| 2026-05-06 | batch_001_top100_critical | GO 8/10 | 8 | 8/3500 | [link] |
| 2026-05-07 | batch_002_long_tail | PARTIAL 6/10 | 6 | 14/3500 | [link] |
```

## SESSION.md per-batch template

```markdown
# Batch <NNN> -- <slug> -- <YYYY-MM-DD>

## Goal

Re-author <N> rules from `patterns/web-signatures/`. Selection criteria:
<priority criteria, e.g. "top 10 high-priority enterprise customers">.

## Input proposals

See `proposals_<batch>.json` for ordered list with priority + vendor_website.

## Outcome

| Metric | Value |
|--------|-------|
| Proposed | <N> |
| AUTHORED | <X> |
| DEFERRED | <Y> (vendor_unreachable) |
| SKIPPED | <Z> (regex_too_generic) |
| FALSE_POSITIVE during verify | <FP> |
| Verdict | GO / PARTIAL / FAILURE |
| Wave score | /50 (per agentic) |

## Files modified

- `patterns/web-signatures/<X1>.json` (overwrite v1 -> v2-independent)
- `patterns/web-signatures/<X2>.json` ...

## Decisions

See `decisions.md` for architectural decisions made during this batch.

## Cross-repo commits

- LIA-SEC : `<commit_hash>` -- tracking + audit
- LiaProbe : `<commit_hash>` -- rule files updated

## Lessons (RETEX-light)

<3-5 bullet points if score < 40>
```

## journal.jsonl format

Append-only, one line per rule processed :

```json
{"timestamp":"<ISO8601Z>","product":"<slug>","vendor_website":"<url>","html_sha256":"<64hex>","favicon_sha256":"<64hex_or_null>","favicon_mmh3":<int_or_null>,"matchers_count":<N>,"fp_test_pages":[<5_urls>],"verdict":"AUTHORED|DEFERRED|UNREACHABLE|SKIPPED","note":"<short>"}
```

Example :

```json
{"timestamp":"2026-05-06T10:32:18Z","product":"adform","vendor_website":"https://site.adform.com","html_sha256":"abc123...","favicon_sha256":"def456...","favicon_mmh3":-1234567890,"matchers_count":1,"fp_test_pages":["https://www.example.com","https://en.wikipedia.org/wiki/Main_Page","https://github.com","https://www.cloudflare.com","https://stackoverflow.com"],"verdict":"AUTHORED","note":"script_src adform.net domain unique"}
```

## decisions.md format

Per-batch architectural decisions (medium freedom) :

```markdown
# Batch <NNN> Decisions

## Decision 1: How to handle CDN-served products

For products like Adform / Cloudflare CDN, multiple legit domains exist.
Solution : pick the most stable one (legal domain, not a CDN edge URL).

## Decision 2: SPA vs static page

For Vue.ai / similar SPAs : curl returns minimal shell, real fingerprint
needs Playwright DOM render. Tag rule with `_lia_independent_authoring.method`
= "playwright_rendered" instead of "direct_curl".

## Decision 3: Favicon hash strategy

Compute MMH3 (Shodan-style int32 signed) instead of MD5 (legacy BSD-2 catalog tied).
mmh3.hash on base64-encoded favicon, output int32 signed.
```

## decision_log.jsonl integration

Append to `_alire/02_LOGS/Journals/decision_log.jsonl` for batch-level decisions :

```bash
echo '{"timestamp":"'$(date -u +%Y-%m-%dT%H:%M:%SZ)'","session":"liaprobe-fingerprint-rebuild-<batch>","action":"BATCH_COMPLETED","reasoning":"<batch summary>","alternatives_rejected":[],"outcome":"<X>/<N> authored","confidence":"high","plan_ref":"sessions/<DATE>_<batch>/SESSION.md"}' >> _alire/02_LOGS/Journals/decision_log.jsonl
```

## Cross-repo discipline

Per `liaprobe-dual-repo.md` :

1. LiaProbe commit (rule .json files modified)
2. LIA-SEC commit (tracking + audit) referencing LiaProbe commit hash
3. Both pushed

```bash
# LiaProbe side
cd /opt/lia-sec/liaprobe
git add patterns/web-signatures/*.json
git commit -m "feat(patterns): rebuild batch <NNN> independent observation"
LIA_PROBE_HASH=$(git rev-parse --short HEAD)
git push

# LIA-SEC side
cd /opt/lia-sec/dev
git add _alire/tracking/liaprobe-fingerprint-rebuild/sessions/<DATE>_<batch>/
git commit -m "docs(rebuild): batch <NNN> tracking (liaprobe ${LIA_PROBE_HASH})"
git push
```

## STRICT RULES

1. **1 batch = 1 subdir** : never reopen closed batch
2. **append-only journal.jsonl** : never edit past entries (only append)
3. **captures/** gitignored after batch close (transient)
4. **proposals_<batch>.json** kept for replay
5. **REPLAN** triggers new `PLAN_<batch>_REPLAN_<N>.md` in same subdir, original PLAN preserved
6. **Stale batches** (open > 7 days without progress) : flag in SESSIONS_INDEX as STALE, do NOT reuse subdir, start fresh

## .gitignore additions (LIA-SEC tracking dir)

```gitignore
# Skill liaprobe-fingerprint-rebuild transient captures
_alire/tracking/liaprobe-fingerprint-rebuild/sessions/*/captures/
```

The structure (SESSION.md, journal.jsonl, decisions.md, PLAN_*.md, proposals_*.json) IS committed for full audit traceability.
