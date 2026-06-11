---
name: liaprobe-fingerprint-rebuild
description: Independently rebuild web-tech fingerprint patterns by direct public observation, replacing third-party-derived rules with defensible factual patterns (clean-room rebuild for license compliance). Strict tracking discipline -- every batch lives in a per-session subdirectory under `_alire/tracking/liaprobe-fingerprint-rebuild/sessions/` with SESSION.md, journal.jsonl, decisions.md, captures/. Use when LIA-SEC needs to remove derivative work risk on web-signatures (third-party GPL-v3 catalog) or banner-signatures (third-party BSD-2 catalog with retain-notice) by replacing them with patterns authored from independent HTTP observation. Triggers on "/liaprobe-fingerprint-rebuild", "rebuild les fingerprints", "remplace les patterns externes", "audit legal signatures", "indep re-observe rules".
---

# LiaProbe Fingerprint Rebuild -- Independent Public Observation

## Canonical filename rule (c23+, naming convention)

Source : user preference 2026-05-13 (apex c23+c24 session). Replaces
legacy LIA-Scan 5-letter quadrigramme stems (WGARD, OPENSSH, MARIADB...)
with canonical product names.

### Single source -- NVD CPE vendor + product

Canonical name = NVD CPE `vendor.vendor_name` + `product.product_name`.
Already resolved per rule in `_meta_enrichment.canonical_vendor` block
(populated by c11 canonical resolution).

LiaProbe fingerprints legitimate software, infrastructure, network
services. Attacker tool names (MITRE ATT&CK malware / intrusion-set /
campaign) are NEVER used as rule filenames -- they belong in detection
rules (LIA-Scan), not in fingerprint rules.

Format :

| Case | Format | Example |
|------|--------|---------|
| Same vendor + product | `{Product}.json` | `WireGuard.json` |
| Distinct vendor + product | `{Vendor}_{Product}.json` | `Oracle_MySQL.json`, `Apache_HTTP_Server.json` |
| Multi-product per vendor | `{Vendor}_{Product}.json` | `Microsoft_IIS.json`, `Microsoft_Exchange.json` |

Casing : PascalCase or CPE case preserved. Brand caps preserved when
top-level `vendor`/`product` field matches the canonical case-insensitively
(`WireGuard` stays `WireGuard`, `MariaDB` stays `MariaDB`). Underscores
between vendor and product. No spaces. No emojis (R10).

### FORBIDDEN

- Attacker tool names (MITRE ATT&CK malware / tool / intrusion-set /
  campaign) as fingerprint rule filenames. These belong in LIA-Scan
  detection rules, not in LiaProbe fingerprint catalog.
- 5-letter quadrigramme stems for NEW files (legacy taxonomy_code naming)
- Emojis (R10) or open-source attribution (R13) in filenames

### Migration plan (c24+ mass rename)

1. Scan `patterns/**/*.json` for non-canonical stems
2. Compute proposed name from `_meta_enrichment.canonical_vendor.{vendor_name, product_name_db}` (CONFIDENT bucket, not ambiguous)
3. Preserve brand caps from top-level `vendor`/`product` when case-insensitive match
4. Collision detection : two rules -> same name = disambiguator (sub-product, version)
5. In-JSON sync : ONLY `source.file` body field is patched. Top-level
   `vendor` + `product` fields are NEVER touched (see "NEVER patch
   vendor/product" rule below).
6. Dry-run output : `RENAME_PROPOSALS_<DATE>.json` schema `lia-rename-proposals-v1`
7. Selective apply : `git mv` + source.file patch + audit
   `_lia_independent_authoring.filename_rename_c{N}`
8. Engine smoke + onyphe regression (loader uses `id` not filename, transparent)
9. Grep cross-refs for hard-coded filename strings (test_data, vendor_url cache)

### NEVER patch vendor / product top-level fields

Incident c25 ST3 (2026-05-13): apply_renames.py initially normalized
top-level `vendor` and `product` fields to PG canonical form (e.g.
"Apache HTTP Server" -> "Http_Server"). This broke 1658 onyphe
verdicts (CORRECT -> WRONG) because the engine uses `rule.product` as
the **detected_product label** in its output, and the Onyphe ground-truth
still carries human-friendly strings.

Rule (BLOCKING in apply_renames.py + rename_proposals.py):
- `field_updates` may patch `source.file` only.
- `vendor` and `product` fields stay at their original wild-friendly
  values that the engine emits at scan time.
- Canonical normalized values live in `_meta_enrichment.canonical_vendor`
  (sole source of truth for naming-canonicalization purposes).
- A hard-coded `FORBIDDEN_FIELD_UPDATES = {"vendor", "product"}` guard
  in apply_renames._patch_rule drops any incoming bad updates.

### Audit trail per renamed file

```json
"_lia_independent_authoring": {
  "filename_rename_c{N}": {
    "date": "YYYY-MM-DDTHH:MM:SSZ",
    "from_basename": "WGARD.json",
    "to_basename": "WireGuard.json",
    "tier": "1a_canonical_vendor",
    "vendor_id": 66564,
    "product_id": 231903,
    "field_updates_applied": {"source.file": {"from": "WGARD.json", "to": "WireGuard.json"}},
    "reason": "Canonical NVD CPE vendor+product name. Legacy stem replaced per fingerprint-naming convention.",
    "marked_by": "apex_c{N}_rename_<DATE>"
  }
}
```

### Verification script

```bash
# legacy stems remaining
for f in /opt/lia-sec/liaprobe/patterns/lia/*.json; do
  name=$(basename "$f" .json)
  [[ "$name" =~ ^[A-Z0-9]{4,5}$ ]] && echo "LEGACY: $f"
done | head -20
```

c23 first concrete rename : WGARD.json -> WireGuard.json (validated,
engine still loads 489 patterns, zero onyphe regression).

c24 dry-run script : `scripts/rename_proposals.py` (TODO -- emits the
JSON for review BEFORE mass apply).

---

## Mature pipeline (c1-c28 state, 2026-05-13)

Skill state after 28 cycles (14 nightly authoring + 14 apex naming/cleanup batches):

### c24-c28 marathon contributions (script suite: rename + collision + revendor)

8 new scripts in `scripts/` shipped during 5-cycle marathon on 2026-05-13:

| Script | LOC | Cycle | Role |
|--------|-----|-------|------|
| `rename_proposals.py` | 385 | c24 | Tier 1a/1b canonical NVD CPE filename proposals + collision detection + DOUBTFUL flag. Schema `lia-rename-proposals-v1`. |
| `apply_renames.py` | 215 | c25 | git mv + audit `filename_rename_c{N}` + hard-coded `FORBIDDEN_FIELD_UPDATES = {vendor, product}` guard. |
| `revert_field_patches.py` | 150 | c25 | REPLAN tool : restore vendor/product from BACKUP_DIR keeping renames + audit. |
| `apply_collision_triage.py` | 385 | c26 | Hardcoded TRIAGE list (12 MERGE + 6 SPLIT + 3 REVENDOR) + audit `collision_triage_c{N}`. |
| `merge_loser_matchers.py` | 170 | c26 | SHA256-stable dedupe absorbs loser banner_matchers + probes into winner pre-archive. |
| `audit_merge_coverage.py` | 140 | c27 | Per-banner key (port+protocol+banner[:80]) compare pre/post engine output. |
| `unarchive_merge_losers.py` | 140 | c27 | Reverts MERGE -> SPLIT for losers with non-recoverable detection. |
| `revendor_via_db.py` | 270 | c28 | R18 strict alias_exact PG lookup for DOUBTFUL bucket (no fuzzy fallback). |

Total : 1855 LOC. All pure stdlib + psql subprocess. Zero external deps. Each script audit-replayable via per-rule JSON artifact (RENAME_PROPOSALS, REVENDOR_RESULTS, MERGE_COVERAGE_AUDIT).

### Marathon engine state (c24 baseline -> c28 final)

| Stage | CORRECT | WRONG | MISS |
|-------|---------|-------|------|
| c24 baseline | 15296 | 324 | 706 |
| c25 (264 renames) | 15297 | 324 | 705 |
| c26 (collision triage) | 15282 | 322 | 722 |
| c27 (unarchive 4 sub-products) | 15299 | 322 | 705 |
| c28 (strict revendor, 0/53 RESOLVED) | 15299 | 322 | 705 |

Net delta over marathon : **+3 CORRECT, -2 WRONG, -1 MISS** while 264 renames + 19 collision triages + 4 unarchives applied. Zero regression discipline preserved via BACKUP_DIR per cycle + recette-onyphe gate after each phase.

### REPLAN-within-cycle pattern (validated 2x in marathon)

Pattern reusable in any apex skill with destructive ops :

```
1. Detect regression via measurable gate (recette-onyphe ground-truth)
2. BACKUP_DIR per phase enables non-destructive revert (shutil.copy2 before write)
3. Build remediation script mid-cycle (~150-200 LOC)
4. Re-test against same gate
5. Harden source-of-regression with guard (FORBIDDEN_FIELD_UPDATES, enabled-check, etc.)
6. Update SKILL.md with new rule + incident reference
```

Validated incidents :
- c25 ST3 : 1658 verdict regression caught -> built revert_field_patches.py + FORBIDDEN_FIELD_UPDATES guard
- c26 ST1-bis/ter : -89 CORRECT regression -> built merge_loser_matchers.py + enabled_after_merge fix

REPLAN is cheaper than session restart. Multi-level BACKUP_DIR makes REPLAN safe.

### Anti-patterns hard-coded in scripts (c24-c28 incident origins)

- **A1** : NEVER patch top-level `vendor` / `product` fields (engine break). Enforced by `FORBIDDEN_FIELD_UPDATES = {vendor, product}` in apply_renames._patch_rule.
- **A2** : NEVER use MITRE ATT&CK names in fingerprint naming (false positives via substring match). SKILL.md "Single source -- NVD CPE vendor + product" enforces this.
- **A3** : NEVER archive without checking `enabled` field (silent winner loss). c26 ST1-ter incident -> queue c30 enabled-aware winner selection.
- **A4** : NEVER archive without data-driven audit (engine cluster routing breaks detection). c27 audit_merge_coverage built BEFORE deciding which losers to unarchive.
- **A5** : NEVER `INSERT INTO vendor` without also INSERTing the matching `vendor_alias` row with `alias_name = vendor_name`. Resolution paths (revendor_via_db strict alias_exact) look up via `vendor_alias` only, so a vendor with no alias-of-itself row is UNRESOLVABLE despite existing in the vendor table. c31 incident : migration 157 added vendor `Keil` but omitted alias `Keil` -- KEILEWEB candidate `Keil|Keil EWEB` failed resolution until manual hotfix.

### Migration convention -- auto-alias pattern (c32 retrofit)

Every new vendor INSERT in a migration MUST be paired with an idempotent `vendor_alias` INSERT whose `alias_name` matches the vendor name. Template :

```sql
-- 1. Insert vendor (vendor.added_at + updated_at default to now())
INSERT INTO vendor (vendor_name, seed_source)
VALUES ('Acme', 'manual')
ON CONFLICT (LOWER(vendor_name)) DO NOTHING;

-- 2. Insert self-alias (CRITICAL -- enables strict alias_exact resolution)
--    vendor_alias.added_at + updated_at default to now() too. Do NOT pass created_at.
INSERT INTO vendor_alias (vendor_id, alias_name, source, alias_type, confidence_score)
SELECT vendor_id, 'Acme', 'lia_manual', 'official_name', 1.0
FROM vendor WHERE LOWER(vendor_name) = LOWER('Acme')
ON CONFLICT (LOWER(alias_name)) DO NOTHING;

-- 3. Then INSERT product rows tied to the vendor_id (product.created_at exists; check schema)
```

Skip this and revendor_via_db.py (and any future strict-lookup script) cannot resolve banners that match the vendor name. Idempotent via UNIQUE(LOWER(alias_name)) -- safe to re-run.

### Canonical_vendor buckets (c34 update)

The `_meta_enrichment.canonical_vendor.bucket` field carries one of:

| Bucket | Meaning | Resolution path | Re-process on next revendor pass |
|--------|---------|-----------------|---------------------------------|
| `CONFIDENT` | Full vendor+product match against PG (strict alias_exact or fuzzy_trgm >= 0.6) | revendor_via_db `--apply` | No |
| `VENDOR_ONLY_CONFIDENT` | (c34) Vendor matched but product not in PG. Product info kept from rule. | revendor_via_db `--vendor-only-fuzzy` (vscore >= 0.9 + non-junk filter) | No |
| `DOUBTFUL` | Pre-c32 fuzzy guess kept as fallback (e.g. product_ilike_dominant, alias_only_fuzzy_trgm with junk vendor name) | revendor_via_db will re-attempt | Yes |
| `PERMANENT_DOUBTFUL` | (c32) DARKCOMET/GSHD-style junk-vendor rules. Set explicitly via `permanent_doubtful=true`. No canonical exists. | None | No (skip) |

The `classification_c34` block (c34 A29) tags 61 rules with no canonical_vendor at all into 3 sub-categories: `JUNK_VENDOR`, `PROTOCOL`, `UNKNOWN_VENDOR`. The first two have `permanent_doubtful=true`, the last has `pending_enrichment=true` (c35+ targets for manual canonical INSERT pass).

**revendor scan rule**: `_scan_doubtful_rules` (revendor_via_db.py) processes `bucket=DOUBTFUL` only. Skips `CONFIDENT`, `VENDOR_ONLY_CONFIDENT`, `PERMANENT_DOUBTFUL`, and `classification_c34.permanent_doubtful=true`. `--include-non-canonical` flag additionally picks up rules with no canonical_vendor block AND bare top-level vendor+product (Tier 1b).

### permanent_doubtful is METADATA, not engine-scan-skip (c36 A34 lesson)

**Critical insight from c36 A34 REPLAN incident**: `canonical_vendor.permanent_doubtful` and `classification_c34.permanent_doubtful` are tags for *audit and sync workflows* (revendor scripts skip them, /liaprobe-rule-enrich classifies them, audit_downstream tracks them). They are NOT signals that the engine should skip these patterns at scan time.

c36 attempted to filter permanent_doubtful patterns at engine load in `pkg/fingerprint/loader.go`. Result: dropped 39 patterns -> engine CORRECT 15200 -> 12267 (regression -2933). DARKCOMET still detects DarkComet banners. POP3/TELNET/MODBUS protocol fingerprints still produce CORRECT generic-banner matches. The filter was reverted in the same cycle.

**Rule**: if a future evolution wants engine-level skip, add an EXPLICIT `engine_scan: disabled` field to the rule schema, not a derived inference from permanent_doubtful. The `MetaEnrichment` Go struct in `pkg/fingerprint/model.go` remains available for audit scripts to read these tags without affecting scan behavior.

### Placeholder orphan aliases policy (c38 A42+A43)

The `lia-declined` placeholder vendor (vendor_id=202726) holds 186 lia_internal aliases that don't resolve to any real vendor. Additional 4 in `lia-meta` + 1 in `Unknown-O` = 191 total truly-orphan aliases.

**Policy**: KEEP_AS_IS. NEVER auto-DELETE.

Rationale (c38 spot-check of top 10 fuzzy candidates at vscore 0.5-0.55 = 0/10 validated):
- pg_trgm at threshold >= 0.5 is NOT a viable auto-classifier for these orphans (substring coincidences + typo proximities + placeholder-to-placeholder noise).
- DELETE = irreversible audit-trail loss. lia-declined is the curated catch-all for unresolved `rule.vendor` strings.
- Future enrichment value: per-orphan WebFetch + vendor documentation research can produce canonical vendor (e.g. `serome technology, inc.` -> Serome Technology Inc. Korean firm). Manual workflow appropriate.
- DELETE forces re-discovery if an orphan later proves resolvable.

**Optional future workflow** (c39+):
- Build `/enrich-placeholder-orphan` skill: per-orphan WebFetch -> PG lookup -> manual confirmation -> mig 16N reassign.
- Target 5-10 highest-value orphans per cycle (priority: orphans with active CVEs in NVD).
- HARD RULE: never DELETE vendor_alias without explicit user authorization.

Reference scripts:
- `audit_alias_collisions.py` (c36 A35): scans all vendor_alias for shadow patterns.
- `audit_placeholder_orphans.py` (c37 A41): pg_trgm fuzzy lookup per orphan, multi-threshold.
- `audit_truly_orphan_distribution.py` (c38 A43): groups by placeholder + source + alias category for targeted research.

### Data-driven audit-before-decide

When archive/delete operation has unclear downstream impact, build data-driven audit BEFORE the operation (not after). c27 validated : built `audit_merge_coverage.py` first, identified exactly 4 groups with 16 lost banners via per-banner key matching, then unarchived only those 4. Zero guesswork. Pattern baked into `apply_collision_triage.py` c32 (A21) via `--audit-coverage` flag.

### Default-ON pattern for c33+ (A25)

When invoking `apply_collision_triage.py` in any future cycle, **always pass `--audit-coverage`** unless explicitly justified otherwise in the cycle PLAN. Cost: ~2 minutes (two recette-onyphe runs). Benefit: pre/post per-banner key audit + automatic non-zero exit if CORRECT banner loss detected.

```bash
# RECOMMENDED for c33+ MERGE/SPLIT operations
python3 .claude/skills/liaprobe-fingerprint-rebuild/scripts/apply_collision_triage.py --apply --audit-coverage

# Skip only for emergency rollback (e.g. recovering from a known-bad merge)
# Document the skip reason in the cycle PLAN.md
```

### c1-c52 mature pipeline state (consolidated, last updated c53)

- **Engine-validated wild detection** : 98.0% real corpus precision
  (16326 clean Onyphe banners, 8080 TP, 149 Onyphe-gt-mismatch, 171 true FP)
<!-- LIAPROBE_BASELINE_AUTO_START -- auto-generated by scripts/propagate_baseline_to_skill.py from latest _alire/tracking/liaprobe-fingerprint-rebuild/inventory/ENGINE_BASELINE_C*_SUMMARY.json -->
- **Engine-reported** : 91.3% / 2.4% / 6.2% (CORRECT / WRONG / MISS) -- measured
  baseline 15200/407/1034 since c67 (c46-c58 cycles quoted 15200/407/1034
  via legacy PASS/FAIL/ERROR labelling -- c59 R18 audit exposed the actual
  engine verdicts are CORRECT/WRONG/MISS/NO_PATTERN ; corpus 16641 stable
  across c46-c67 ; delta +0/+0/+0 = 0.00% noise floor / corpus,
  attributable to c52-c66 cumulative rule churn, notably c57 5-rule
  promotion altering match priority ordering)

_Last updated c67 at 2026-05-15 (build_commit c90bc5c2e)._
<!-- LIAPROBE_BASELINE_AUTO_END -->

- **30+ dedicated scripts** + nightly orchestrator (counting c1-c52 additions
  beyond initial 22)
- **5 BLOCKING reliability gates** (Gate 1-5) + 1 traceability gate (c53+)
- **62/62 unit tests** (test_wave_validator + test_wave_processor +
  test_nightly_skip + test_onyphe_audit) + 28 classifier tests (test_classify_tier)
- **Postgres canonical** integration at authoring time
  (44566 vendors / 44856 aliases / 1M+ products / MITRE STIX links)
- **Cross-skill handoff** with /liaprobe-rule-enrich via cpe23_template
- **Forensic audit trail** : 20+ block types per rule
  (vendor_dead, vendor_dead_reverted_c52, unarchived, http_gate,
   disabled_low_precision, disabled_cluster_fp, proven_by_onyphe,
   wild_traffic_unconfirmed, rebrand_history, vendor_rebrand_history,
   fp_audit_c13, fp_audit_c14, fp_audit_c15, dedupe_rename,
   onyphe_canonical_resolution, onyphe_canonical_rename,
   ibm_domino_rebrand_*, filename_rename_c{N}, collision_unarchive_c27,
   classification_c34)

### Traceability gap c10-c14 (DOCUMENTED c53)

**Hole in formal tracking** : cycles c10-c14 ran on 2026-05-13 but produced
NO PLAN_APEX_*.md and NO RETEX_PDCA_*_CYCLE{10..14}_*.md files. Only audit
blocks inside rule JSON files preserved evidence :

| Cycle | Inferred scope | Audit-block footprint |
|-------|----------------|----------------------|
| c10 | Postgres canonical resolution + dedupe dry-run | 0 audit blocks, 1 backup dir (`dedupe_backup`) |
| c11 | Dedupe apply (rename 450 generic ids -> 2666 file-level renames) + skip-spip filter | 2666 files marked `c11_dedupe` |
| c12 | Nightly cron wiring (validate_new_rules.py + skip-spip default) | 0 audit blocks (workflow-only) |
| c13 | 4 streams : net_snmp cluster disable + manual vendor rebrand + IBM Domino rebrand + GFI Kerio audit | 36 files marked `apex_c13_*` |
| c14 | Multi-product FP audit (gfi_kerio 133 WRONG split into 106 gt mismatch + 27 unknown) | 2 files marked `apex_c14_multiproduct_fp` |

Reconstruction reference :
`_alire/tracking/liaprobe-fingerprint-rebuild/TRACEABILITY_GAP_C10_C14_2026-05-14.md`

Meta-analysis (RETEX-Analyzer level) does exist :
`_alire/02_LOGS/Journals/retex/RETEX_ANALYZER_LIAPROBE_FINGERPRINT_C9_C14_2026-05-13.md`

Engine net delta c9 baseline -> c15 pre-baseline : CORRECT -48, WRONG -331,
MISS -129 (strict precision improvement via dedupe + multi-product reclassification).

### Cycle traceability gate (c53+, BLOCKING)

Before declaring a cycle CLOSED, run :

```bash
python3 scripts/verify_cycle_traceability.py --scope LIAPROBE_FINGERPRINT_REBUILD --from-cycle <N-1> --to-cycle <N>
```

Exit 0 = full coverage. Exit 1 = partial (PLAN xor RETEX). Exit 2 = consecutive
gap (BLOCKING -- cycle CANNOT close).

Enforcement rule :
- Every cycle whose PLAN_APEX_*.md exists MUST produce a matching RETEX_PDCA_*.md
- Every cycle that modifies > 1 rule file MUST inject an audit-block
  `marked_by` referencing the cycle id (`apex_c{N}_*`) AND produce a RETEX
- Workflow-only cycles (no rule modif, like c12) STILL need a RETEX --
  scoped as "delta +0 expected, justification : workflow automation only"
  per c52 retex-protocol.md template

Recurrence prevention : verify_cycle_traceability.py is invoked as Phase 0
pre-flight on every new cycle. If `--from-cycle <previous>` returns exit 2,
the new cycle MUST first backfill or document the missing pair before
proceeding.

Pipeline overview:

```
[MASTER_TODO]
     |
     v
[wave_ai.py] -- postgres canonical (vendor+product+cpe23) + ID collision check
     |         + model heuristic (haiku|sonnet per postgres coverage)
     v
[LLM author rules] (claude-haiku-4-5 default, sonnet escalate on parse fail)
     |
     v
[wave_validator.py] -- R17 contract + 4 provenances + html_sha256 + http_gate
     |
     v
[wave_processor.py] -- auto-upgrade gate + signal_class filter
     |
     v
[nightly git commit] -- liaprobe repo
     |
     +----> [validate_new_rules.py] -- post-authoring engine validation
     |
     +----> [audit_multiproduct_fp.py] -- distinguish gt errors vs true FP
     |
     +----> [audit_duplicate_ids.py] -- cluster detection
     |
     +----> [audit_rebrands.py] -- taxonomy drift detection
     |
     v
[/liaprobe-rule-enrich] -- (separate skill, post) CVE + EOL + MITRE injection
```

References:
- `_alire/02_LOGS/Journals/retex/RETEX_ANALYZER_LIAPROBE_FINGERPRINT_C1_C8_2026-05-13.md` (gates 1-5 origin)
- `_alire/02_LOGS/Journals/retex/RETEX_ANALYZER_LIAPROBE_FINGERPRINT_C9_C14_2026-05-13.md` (skill maturation Onyphe baseline 98.0%)
- `_alire/02_LOGS/Journals/retex/RETEX_ANALYZER_LIAPROBE_FINGERPRINT_C24_C28_2026-05-13.md` (rename/triage marathon)
- `_alire/tracking/liaprobe-fingerprint-rebuild/TRACEABILITY_GAP_C10_C14_2026-05-14.md` (c53 gap audit)

## RELIABILITY GATES (BLOCKING -- run at start of EVERY cycle, source: RETEX_ANALYZER 2026-05-13)

These gates exist because 5 recurring failure patterns were detected across
cycles 1-8 (see `RETEX_ANALYZER_LIAPROBE_FINGERPRINT_C1_C8_2026-05-13.md`).
The cycle score stayed 100/100 while real reliability dropped : silent bugs,
scope estimation errors, FP rules undetected, Python re-implementation
instead of using the Go engine, tests passing by accident.

### Gate 1 -- Existing tools first (prevents Python re-impl of Go binary)

```bash
ls /opt/lia-sec/liaprobe/bin/                       # Go binaries: liaprobe, recette-onyphe, recette-banners
ls /opt/lia-sec/liaprobe/cmd/                       # Go sources for inspection
find _alire/01_DOCUMENTATION/ -iname "*liaprobe*"   # existing docs
find _alire/temp/ -iname "*onyphe*" -o -iname "*recette*"  # existing datasets
```
If a Go binary exists for the audit operation -> USE IT via subprocess.
Do NOT re-implement in Python unless the Go tool is missing or insufficient.
Incident c6 : Python evaluator loaded 767 patterns vs Go engine 10102 = 13x miss,
plus a `.*`-on-absent-header bug that produced universal FPs.

### Gate 2 -- Pre-flight scope validation (prevents estimation drift)

For each ST that targets N rules, write the exact scan and count BEFORE
writing the modification script:
```bash
python3 -c "<actual scan logic from upcoming script>"
```
Document estimated count + verify on disk. If estimate != reality by >20%,
revisit selector logic.
Incident c5 : estimated 405 vendor_self_host without hash, real was 127
due to ST overlap (10x off). c6 : 152 estimated vs 142 real.

### Gate 3 -- Onyphe ground-truth check after every modification (prevents silent FP)

After any rule modification (create/disable/rename/unarchive):
```bash
cd /opt/lia-sec/liaprobe && bin/recette-onyphe \
    -f /opt/lia-sec/dev/_alire/temp/onyphe_merged_unique_*.jsonl \
    -out table -src all | head -10
```
Record CORRECT/WRONG/MISS counts. Compare to previous baseline.
Any regression > 0.1% triggers REPLAN. Any new FP > 5 on a single rule
must be investigated before commit.
Incident c8 : net_snmp had 241 FP / 0 TP undetected for many cycles.

### Gate 4 -- TDD red-green discipline (prevents tests passing by accident)

For each unit test created :
1. Write test, run it -- MUST FAIL first (red phase)
2. Write code that makes it pass
3. Re-run, verify GREEN
If a new test passes immediately without the red phase, the test is wrong.
Rewrite the test fixture until it would fail on the unmodified code.
Incident c5 : test_skip_count_logged passed without testing skip logic
(master_todo had 2 spaces while regex required 1, no rule was ever matched
so log line was never emitted, assertion checked empty array).

### Gate 5 -- ID uniqueness across corpus (prevents silent winner-loser conflict)

Engine identifies a rule by its `id` field (lowercase), NOT filename.
When multiple rule files share the same id, engine picks ONE winner per
banner based on confidence_delta priority. Other rules score TP=0
silently even if they would have matched.

Before creating or renaming a rule :
```bash
# 1. Check current id usage
python3 -c "
import json, glob
ids = {}
for p in glob.glob('/opt/lia-sec/liaprobe/patterns/**/*.json', recursive=True):
    if '/archive/' in p: continue
    try: r = json.load(open(p))
    except: continue
    pid = (r.get('id') or '').lower()
    if pid: ids.setdefault(pid, []).append(p)
# Pass desired id as argv
import sys
target = sys.argv[1].lower()
print(ids.get(target, []))" '<desired_id>'
```

If the desired id is already used, choose ONE of :
- Append suffix `_lia` or `_v2` (e.g. `iis` -> `iis_lia`)
- Use vendor-product form (e.g. `microsoft_iis` instead of `iis`)
- Audit colliding rules first via `audit_duplicate_ids.py` -- one may need
  to be retired

NEVER author a new rule with a generic id like `unknown`, `cisco`, `microsoft`,
`hp`, `python`, `dlink`, `ibm`, `sun`, `apple`, `google`, `amazon` --
these are vendor-only and ALWAYS collide.

Incident c9 : corpus has 670 ids used by 2+ files, worst is `id="unknown"`
in 681 files. Most rules with generic ids will score TP=0 forever on Onyphe
because a sibling rule with the same id wins on every banner.

### Educational note -- Filename != id != winning rule

Three independent identifiers for a rule :
1. **Filename** (e.g. `AMAZON_S3.json`) -- physical disk path, no engine meaning
2. **`id` field** in JSON (e.g. `amazon_s3`) -- what engine reports in
   verdict.PatternID
3. **Winning rule per banner** -- engine picks ONE rule per banner, others
   are silently skipped even if their matchers would have triggered

A rule with TP=0 on Onyphe ground-truth does NOT mean the rule is broken.
It can mean :
- Another rule with the same id (or competing id) wins on the same banners
- The product simply isn't in the Onyphe corpus (wild traffic gap)
- The rule targets a niche/historical product

To assess a rule's standalone effectiveness, use
`scripts/validate_new_rules.py` or run engine with the rule's siblings
disabled.

### Pareto principle in wild traffic (c6 finding)

Onyphe ground-truth analysis revealed extreme distribution:
- TOP 5 rules detect 33.7% of all wild banners
- TOP 50 rules detect 88.1%
- 9891/10102 patterns produce 0 TP

When authoring new rules :
1. PRIORITIZE wild-popular products (check
   `ONYPHE_RULE_EVIDENCE_ENGINE_*.json` for high-TP exemplars; copy their
   matcher style)
2. PREFER header/cookie matchers (proof of self-host) over body matchers
   (often marketing-content match)
3. AVOID inventing rules for niche/historical products without wild evidence
4. After mass batch authoring, validate via `bin/recette-onyphe`

### Multi-product FP audit (c14 -- real corpus precision)

`scripts/audit_multiproduct_fp.py` distinguishes between rule bugs and
Onyphe ground-truth errors. For each WRONG verdict, checks if any token
from rule.product (filtered for generic words) appears in the full banner
content.

Discovery on current corpus (16326 clean banners):
- Reported FP : 325
- Onyphe gt mismatch (banner contains product, gt mis-categorized) : 149 (45.8%)
- True FP (rule actually wrong) : 171 (54.2%)
- **Real corpus precision : 98.0%** (vs 93.7% engine-reported)

Pattern : multi-product hosting (one IP runs N services). Onyphe metadata
records only ONE product per IP. Rules correctly detect other services
running on same IP, but verdict logic flags them WRONG.

Rules with gt_mismatch >= 3 get audit block injected automatically
(`_lia_independent_authoring.fp_audit_c14`). Lower-count gt_mismatch
documented in tracking report only.

Use this audit to :
- Distinguish true FPs (needing pattern fix) from gt errors
- Estimate real wild-traffic precision
- Avoid disabling correctly-functioning rules

`scripts/audit_rebrands.py` detects taxonomy drift between rule.product and
postgres canonical product_name. Discovers cases like:
- "Lotus Domino" -> "Domino" (IBM 2018 rebrand)
- "GHost" -> "AkamaiGHost"

Workflow:
```bash
python3 scripts/audit_rebrands.py --dry-run               # report only
python3 scripts/audit_rebrands.py --apply --min-confidence 0.9
```

Filters applied (in order):
1. Exact-letters match (case + punctuation insensitive) -> aligned, skip
2. Token-set equality (word reorder) -> aligned, skip
3. similarity >= --min-confidence -> proposal

Output: `REBRAND_PROPOSALS_<DATE>.json` per rule:
- current_product, proposed_product, confidence
- proposed_vendor (from postgres `vendor` table)
- all_candidates (top-3 trgm matches for review)

**Caveat (c13 finding)** : postgres `product` table has noise (truncation,
typos, ALL_CAPS_TITLE_CASE). Review proposals manually before --apply.
Many "proposals" are postgres data quality issues, not real rebrands.

Real rebrand examples already applied:
- IBM Lotus Domino -> IBM Domino (24 files, manual c13 pass per user note
  referencing https://fr.wikipedia.org/wiki/IBM_Domino)
- Apply via inline Python script with audit trail
  `_lia_independent_authoring.rebrand_history[]`

### Onyphe corpus filtering (c12)

Default merged Onyphe set contained 508 multi-port concatenation artifacts
(banners with `Composed-By: SPIP` marker) that produce false WRONG/MISS
verdicts. Always merge with `--skip-spip` for canonical baseline :

```bash
python3 scripts/merge_onyphe_sources.py --skip-spip \
    --out _alire/temp/onyphe_merged_clean_<DATE>.jsonl
```

Clean baseline on 16326 banners (vs 16834 raw) :
- CORRECT 93.7% (vs 91.3% raw)
- WRONG 3.5% (vs 3.9%)
- MISS 2.8% (vs 4.8%)

The 508 SPIP artifacts hid 426 false verdicts (-2.4pp CORRECT distortion).
Use clean baseline for engine validation. Use raw for inclusivity checks.

### Model selection heuristic (c11 -- cost optimization)

Nightly authoring uses `claude-haiku-4-5` by default (cost optimal) with
`claude-sonnet-4-6` as escalate fallback on parse failure or empty output.

In c11 the model selection now also considers postgres coverage of the wave :
- If >= 50% of products in the wave have a canonical_vendor+product resolved
  by postgres -> stay on haiku (LLM has reliable context)
- If < 50% resolved -> start directly at sonnet (skip haiku, niche/obscure
  products require deeper LLM knowledge that haiku may not have)

This avoids burning haiku tokens on a wave that will likely fail parse +
re-cost sonnet anyway. Postgres coverage is computed from the LIA-SEC
CANONICAL RESOLUTION section presence in user_msg.

opus is NEVER used for batch authoring (orchestration only).

### Cross-skill chain (c10+ -- handoff with /liaprobe-rule-enrich)

The two LiaProbe skills run sequentially:

```
nightly authoring (this skill)            -> POST authoring enrichment
                                              (/liaprobe-rule-enrich)
- wave_ai.py resolves canonical              - reads rule.cpe23_template
  vendor+product+cpe23 from postgres         - queries cve_nvd_data, cisa_kev,
- LLM authors rule with cpe23 pre-filled       exploit_db, cve_attack_mapping
- writes rule.vendor + rule.cpe23_template   - injects _meta_enrichment.canonical_vendor,
                                                known_cves[], lifecycle, attack_surface
```

Field handoff is `cpe23_template` (NVD CPE 2.3 URI). If wave_ai populates
it correctly, /liaprobe-rule-enrich can skip its own vendor_alias resolution.

Both skills query the SAME postgres database (LIA-SEC `lia_scan`) but
different table sets :
- wave_ai (c10+) : `vendor`, `vendor_alias`, `product`, `vendor_mitre_link`
- rule-enrich : `cve_nvd_data`, `cisa_kev`, `exploit_db`, `cve_attack_mapping`,
  `vendor_alias` (fallback resolution)

### LIA-SEC canonical postgres base integration (c10)

The skill now queries LIA-SEC postgres `vendor` + `vendor_alias` + `product`
tables at authoring time (`wave_ai.py:_resolve_canonical_vendors`):
- Resolves `vendor_id`, `vendor_name` (44856 aliases, 44566 distinct vendors)
- Resolves `product_id`, `product_name`, `cpe23` URI (1M+ products from NVD CPE)
- Attaches MITRE STIX object links from `vendor_mitre_link` when available

Output injected into LLM user_msg as `LIA-SEC CANONICAL RESOLUTION` section.
LLM is instructed to copy `vendor` + `product` values verbatim and the
`cpe23` URI into the generated rule (with `{version}` placeholder).

Graceful no-op : if postgres unreachable, nightly batch continues with
product-list values (no failure). DB URL discovered from systemd unit
(`lia-backend.service` Environment=DATABASE_URL).

### Skill invocation discipline (c4-c8 recurring lapse)

Cycles 4-8 skipped `/test-first`, `/code-reviewer`, `/replan` skill
invocations despite CLAUDE.md mandate. Required invocations :
- After ANY Python script creation in this skill -> `/test-first` via Skill tool
- After 2+ consecutive REPLAN on same ST -> `/replan` via Skill tool
- Before declaring a cycle COMPLETE -> `/code-reviewer` via Skill tool
- After 3 cycles same domain -> `/retex-analyzer` (done at c8)

---

## Mission

Replace existing `patterns/web-signatures/*.json` (currently derived from a third-party GPL-v3 catalog) and `patterns/banner-signatures/*.json` (third-party BSD-2 catalog) with INDEPENDENTLY OBSERVED fingerprint patterns. Each output rule is defensible in court as result of direct public HTTP observation, not copied from any third-party catalog.

## Why this skill exists

Audit legal 2026-05-05 revealed:
- `patterns/web-signatures/` ~3500 patterns derived from external GPL-v3 catalog (categories[], notes verbatim, structure)
- GPL v3 + EU sui generis Directive 96/9/EC = non-compliant for closed-source commercial product
- Risk: GPL enforcement / IP litigation
- Mitigation: rebuild each rule from independent observation of public vendor websites

## Decomposition des sous-taches

Each batch invocation processes 10-50 rules. Per rule, 6 sub-tasks (see references/workflow.md):

```
1. RESOLVE_CANONICAL_URL  : WebFetch / WebSearch official vendor URL
2. CAPTURE_ARTIFACTS      : curl HTML + favicon + headers + sha256
3. EXTRACT_SIGNALS        : independent inspection DOM/cookies/headers
4. AUTHOR_REGEX           : creative regex from observation
5. VERIFY_UNIQUENESS      : test against 5+ control pages (no FP)
6. WRITE_RULE_V2          : output JSON with _lia_independent_authoring block
```

## PRE-FLIGHT DEDUP GATE (BLOQUANT, added 2026-05-07 post-RETEX 065+066)

**BEFORE any other action**, regenerate the master tracking files and run
the duplicate check against the proposed product list. If the gate fails,
DO NOT proceed -- revise proposals or mark dups as SKIPPED in SESSION.md.

```bash
ROOT="_alire/tracking/liaprobe-fingerprint-rebuild"

# 1. Refresh MASTER_LIST.md + MASTER_TODO_LIST.md from all journal.jsonl
${ROOT}/scripts/build_master_list.sh

# 2. Refresh CATEGORY_TRACKER.md (theme rotation guide)
${ROOT}/scripts/build_category_tracker.sh

# 3. Pre-flight dedup gate on proposals
${ROOT}/scripts/check_duplicates.sh ${ROOT}/sessions/<DATE>_<batch>/proposals_<batch>.json
# exit 0 = OK, exit 1 = REJECT (>= 30% dups OR --strict and >= 1 dup)
```

Why this exists : RETEX batches 065+066 (2026-05-07) revealed batch_066 was
9/10 duplicates of batch_064 (same Wiki/KB theme 3 batches earlier on same
day). The cumul column in SESSIONS_INDEX double-counted re-writes. The fix
is structural: never trust the user-suggested theme alone; always check
MASTER_LIST.md and CATEGORY_TRACKER.md first. See
`_alire/02_LOGS/Journals/retex/RETEX_LIAPROBE_REBUILD_065_066_2026-05-07.md`
(historical filename predates rename; future RETEX use `RETEX_LIAPROBE_REBUILD_*`).

Theme rotation rule (see CATEGORY_TRACKER.md):
- Avoid the 3 categories with HIGHEST count
- Pick categories with < 50 products and not touched in last 5 batches
- If proposing >= 3 products from same crowded category -> reject batch

## PRE-FLIGHT VENDOR-SELF-HOST CHECK (BLOQUANT, added 2026-05-07 post-audit retroactif)

**BEFORE capturing artifacts from a vendor URL**, verify that the vendor
*actually runs its own product* on that URL. If not, the captured signals
are MARKETING-SITE-SPECIFIC and useless for fingerprinting real deployments.

```bash
# Step 1 : Extract Server header from vendor URL
SERVER=$(curl -sI --max-time 10 "$VENDOR_URL" | grep -i "^server:" | head -1)
echo "Server: $SERVER"

# Step 2 : Decision matrix
# Web/app server (apache, nginx, lighttpd, openresty, litespeed, passenger, gunicorn, ...)
#   -> vendor MUST self-host (Server header == product name)
#   -> if not, REJECT this URL, find a real deployment
# CMS/app/SaaS (zimbra, mailman, mediawiki, jira, confluence, ...)
#   -> vendor often does NOT self-host on marketing site
#   -> REQUIRE: find a real deployment (university webmail, public list,
#      community wiki, public bugtracker, etc.) and capture from there

# Step 3 : Tag observation_provenance in MANIFEST.json
# - "vendor_self_host" : vendor URL serves its own product (Server header matches)
# - "real_deployment_third_party" : capture URL is a known third-party deployment
# - "documented_default_behavior" : vendor doesn't have public test instance,
#                                   patterns derived from open-source default templates
# REJECT : "vendor_marketing_site" -- never accept this provenance
```

Why this exists : Audit retroactif 2026-05-07 revealed 24/37 captures
(65%) came from `vendor_website == capture_url` where the vendor does NOT
self-host its own product (e.g. zimbra.com runs nginx+Pantheon, not Zimbra ;
gunicorn.org runs GitHub Pages, not Gunicorn ; cherokee-project.com runs
Cloudflare). Such captures produce **signal volatile** that does not match
real Zimbra/Gunicorn/Cherokee deployments. See
`_alire/tracking/PLAN_LIAPROBE_AUDIT_RETROACTIF_2026-05-07.md`.

## Plan d'execution

Avant tout batch :

1. **PASS the pre-flight dedup gate** (section above)
2. **PASS the pre-flight vendor-self-host check** (section above) for each proposed product
3. Creer `_alire/tracking/liaprobe-fingerprint-rebuild/sessions/<YYYY-MM-DD>_<batch_slug>/`
3. Initialize :
   - `SESSION.md` (manifest batch + cumul cible + verdict)
   - `journal.jsonl` (1 line per rule processed, append-only)
   - `decisions.md` (architectural decisions, source attestations)
   - `captures/` (transient HTML/favicon/headers, gitignored after batch close)
4. Tracking file : `PLAN_LIAPROBE_REBUILD_<DATE>_<batch>.md` in tracking root

```bash
# Bootstrap a new batch session
DATE=$(date +%Y-%m-%d)
BATCH_SLUG="batch_$(printf '%03d' 1)"  # increment per batch
DIR="_alire/tracking/liaprobe-fingerprint-rebuild/sessions/${DATE}_${BATCH_SLUG}"
mkdir -p "$DIR/captures"
echo "# Session $BATCH_SLUG -- $DATE" > "$DIR/SESSION.md"
touch "$DIR/journal.jsonl" "$DIR/decisions.md"
```

**STOP rule**: never start a 2nd batch in the same subdir. Each batch = own subdir. Cf. `feedback_skill_workdir.md`.

## Adaptation et replanification

If 2 consecutive rules fail (vendor unreachable / no unique signal / regex always FP) :
- STOP batch
- Invoke `/replan` with batch context
- Output: `PLAN_LIAPROBE_REBUILD_<DATE>_<batch>_REPLAN.md` adjusted

Modification of > 10 rules without intermediate verification : STOP -> re-verification before continuing.

NEVER improvise. Either continue clean batches OR REPLAN.

Logger action="REPLAN_TRIGGERED" dans `_alire/02_LOGS/Journals/decision_log.jsonl`.

## Outils declares

| Tool | Use case | Selection criteria |
|------|----------|--------------------|
| `WebFetch` | Resolve canonical vendor URL initial | Always |
| `WebSearch` | Find official URL when uncertain | URL not provided OR HTTP failure |
| `curl` (Bash) | Artifact capture (HTML/favicon/headers) | Direct observation |
| `sha256sum` (Bash) | Artifact integrity hash | Always |
| `mmh3` Python lib (Bash) | Favicon hash Shodan-style int32 signed | When favicon present |
| `Playwright MCP` | DOM-rendered SPA detection | If curl shows empty body / SPA |
| `jq` (Bash) | JSON validation/manipulation | Output write + verification |
| `Read/Write` | Rule files + audit trail | Always |
| `Grep` | False-positive testing across control pages | Verification step |

Retry policy: 1 retry on HTTP 5xx -> if fail -> DEFER (mark journal `vendor_unreachable`).
Si 2eme echec : log decision_log.jsonl + stop + signaler.

## Tracabilite agentique

Logger systematique dans :

1. **Per-rule** : `sessions/<DATE>_<batch>/journal.jsonl` (append-only)
   ```json
   {"timestamp":"<ISO>","product":"<X>","vendor_website":"<url>",
    "html_sha256":"<...>","favicon_sha256":"<...>","favicon_mmh3":<int>,
    "matchers_count":<N>,"fp_test_pages":[<5_urls>],
    "verdict":"AUTHORED|DEFERRED|UNREACHABLE|SKIPPED","note":"<short>"}
   ```

2. **Per-decision** : `_alire/02_LOGS/Journals/decision_log.jsonl`
   ```bash
   echo '{"timestamp":"'$(date -u +%Y-%m-%dT%H:%M:%SZ)'","session":"liaprobe-fingerprint-rebuild-<batch>","action":"AUTHORED_INDEPENDENT_RULE","reasoning":"...","alternatives_rejected":[],"outcome":"...","confidence":"high","plan_ref":"sessions/<DATE>_<batch>/SESSION.md"}' >> _alire/02_LOGS/Journals/decision_log.jsonl
   ```

3. **End-of-batch** : RETEX `_alire/02_LOGS/Journals/retex/RETEX_LIAPROBE_REBUILD_<DATE>_<batch>.md` if score < 40/50 OR if first batch.

## Per-rule workflow

See [references/workflow.md](references/workflow.md) for detailed 6-step procedure with examples.

## Output schema (lia-fingerprint-v2-independent)

See [references/output-schema.md](references/output-schema.md) for full JSON schema.

Key requirements :
- `_lia_independent_authoring` block MANDATORY with all sub-fields
- `third_party_catalog_references_consulted` MUST be `"NONE"`
- `artifacts.html_sha256` AND `favicon_mmh3` (when favicon present)
- **`artifacts.capture_url` MANDATORY** (added 2026-05-07 post-audit) -- the exact URL captured. Must NEVER be empty when `html_sha256` is present. Audit retroactif found 469/506 ré-authoreées rules without `capture_url` = unverifiable provenance.
- **`artifacts.observation_provenance` MANDATORY** -- one of `vendor_self_host` / `real_deployment_third_party` / `documented_default_behavior` (never `vendor_marketing_site`)
- `supersedes_prior_rule` references the path of the rule being replaced

## MANIFEST.json STANDARDIZED schema (BLOQUANT, added 2026-05-07 post-audit)

`patterns/web-signatures/captures/{PRODUCT}/MANIFEST.json` MUST follow this schema (audit revealed 8 different schemas across batches 001-066 -- standardize forward) :

```json
{
  "schema": "lia-capture-manifest-v1",
  "product": "<UPPER_SNAKE>",
  "captured_at": "<ISO8601>",
  "capture_url": "<exact URL captured>",
  "observation_provenance": "vendor_self_host|real_deployment_third_party|documented_default_behavior",
  "vendor_website": "<canonical vendor home URL, may differ from capture_url>",
  "html_sha256": "<64hex>",
  "favicon_sha256": "<64hex|null>",
  "favicon_mmh3": "<int32_signed|null>",
  "headers_sha256": "<64hex>",
  "files": ["observation.html", "headers.txt", "favicon.ico"],
  "signals": ["server: nginx header", "/zimbra/ path", "..."]
}
```

- `capture_url` MUST be propagated to `JSON.artifacts.capture_url` of the rule output
- `observation_provenance` MUST be propagated to `JSON.artifacts.observation_provenance`
- All other fields stay in MANIFEST only (audit trail)

## Forbidden actions

- INTERDIT : Open / Read existing `patterns/web-signatures/<X>.json` BEFORE writing new rule
- INTERDIT : Reference any third-party fingerprint catalog name in code/comments (R13)
- INTERDIT : Copy any regex from a third-party catalog
- INTERDIT : Reuse any third-party catalog category IDs (rebuild own taxonomy)
- INTERDIT : Include `notes` field copied verbatim from a third-party catalog description
- INTERDIT : Mix 2 batches in the same session subdir
- INTERDIT : **Skip the pre-flight dedup gate** (see top of file). Lancer
  un batch sans `check_duplicates.sh` PASS = re-write d'une rule deja
  authoree (incident batches 065+066 du 2026-05-07).

### Critical: Write mechanism

The Claude Code `Write` tool requires `Read` first, which would VIOLATE the
"do not open prior rule" forbidden action. Use ONE of these write mechanisms
that bypass `Read`:

```bash
# Option A : cat heredoc (recommended)
cat > /opt/lia-sec/liaprobe/patterns/web-signatures/CODEIGNITER.json <<'EOF'
{
  "$schema": "lia-fingerprint-v2-independent",
  ...
}
EOF

# Option B : tee
echo '{"$schema":"lia-fingerprint-v2-independent",...}' \
  | tee /opt/lia-sec/liaprobe/patterns/web-signatures/CODEIGNITER.json > /dev/null

# Option C : python script in scripts/
python3 -c "
import json
rule = {...}  # built from observation only
with open('/opt/lia-sec/liaprobe/patterns/web-signatures/X.json','w') as f:
    json.dump(rule, f, indent=2, ensure_ascii=False)
"
```

After write, validate with jq + check NO forbidden field present (categories,
notes, source.original_name, source.file).

## Quality gates per rule (BLOCKING)

```
[ ] artifacts.html_sha256 present and verifiable
[ ] artifacts.capture_url present (MANDATORY, audit 2026-05-07)
[ ] artifacts.observation_provenance set to one of vendor_self_host /
    real_deployment_third_party / documented_default_behavior
    (never vendor_marketing_site)
[ ] MANIFEST.json under captures/{PRODUCT}/ follows lia-capture-manifest-v1 schema
[ ] If observation_provenance == vendor_self_host : verified Server header matches product
[ ] If observation_provenance == real_deployment_third_party : capture_url != vendor_website
[ ] If observation_provenance == documented_default_behavior : signals derived from
    open-source default templates (e.g. Mailman /images/mailman/mailman.jpg footer),
    NOT from running marketing site
[ ] regex tested against 5+ unrelated control pages (all NEGATIVE)
[ ] regex tested against actual vendor page (POSITIVE match)
[ ] vendor_website verified HTTP 200 OR vendor_unreachable documented
[ ] _lia_independent_authoring.third_party_catalog_references_consulted == "NONE"
[ ] NO field copied verbatim from prior rule
[ ] Output schema lia-fingerprint-v2-independent valid (jq parse OK)
[ ] PRIMARY SIGNAL preference order :
    1. Server / X-Powered-By HTTP header regex (universal across deployments)
    2. Default cookie names (universal, set by default config)
    3. Canonical paths (e.g. /zimbra/, /mailman/listinfo, /pipermail/)
    4. Body content from default templates (NOT marketing-specific copy)
    5. script_src / favicon_mmh3 (LAST RESORT, marker-only confidence)
```

## VERIFICATION GATE (BLOQUANT)

Apres batch, AVANT de declarer termine :
- [ ] Toutes les rules processed ont entry dans journal.jsonl
- [ ] Sample 3 rules : verify regex matches vendor page (curl + grep)
- [ ] Sample 2 rules : verify regex DOES NOT match unrelated control page
- [ ] **Sample 3 rules : verify `JSON.artifacts.capture_url` matches `MANIFEST.json` capture_url** (no propagation drift)
- [ ] **Sample 3 rules : verify `JSON.artifacts.observation_provenance` is set** (no `vendor_marketing_site`)
- [ ] SESSION.md mis a jour avec cumul + verdict
- [ ] decision_log.jsonl entry ecrit
- [ ] Cross-repo discipline : commit liaprobe + LIA-SEC tracking
- [ ] Build liaprobe ne casse pas (loader.go skip todo/ + load v2 schema)

Si gate echoue : STOP, fix, re-gate. NEVER declarer "done" with red gate.

## Session subdir convention (IMPORTANT)

```
_alire/tracking/liaprobe-fingerprint-rebuild/
|-- SESSIONS_INDEX.md          (master table all batches)
`-- sessions/
    `-- <YYYY-MM-DD>_<batch_slug>/
        |-- SESSION.md         (batch manifest + verdict)
        |-- PLAN_<batch>.md    (initial plan, REPLAN'd if needed)
        |-- journal.jsonl      (per-rule append-only audit)
        |-- decisions.md       (architectural decisions per batch)
        |-- proposals_*.json   (input rule list with priority order)
        `-- captures/          (transient artifacts, gitignored after close)
```

**STRICT** : 1 batch = 1 subdir. Never reopen closed batch. New batch = new subdir.

## Closure / Librarian Gate

End of batch :
1. Update `SESSIONS_INDEX.md` with new batch row (cumul / verdict)
2. Update `_alire/tracking/INDEX.md` with batch entry
3. Append `decision_log.jsonl` entry
4. Write RETEX if score < 40/50 OR if first batch
5. Commit dual-repo (liaprobe + LIA-SEC)
6. Push both repos

## Batch sizing recommendation

- **First-time use** : batch of 10 rules to validate workflow
- **Steady-state** : batch of 30-50 rules
- **Final long-tail** : batch of 100+ for low-priority fingerprints

Time budget per rule : 10-15 min observation + 5 min audit = ~15-20 min/rule.
Batch of 30 = ~10h human-equivalent or ~3h Claude agent (sonnet).

## Scoring agentique

| Critere | Description | Score |
|---------|-------------|-------|
| C1 Decomposition | 6 sous-taches per-rule clairement isolees | /10 |
| C2 Planification | SESSION.md + PLAN_*.md crees avant batch | /10 |
| C3 Replanification | /replan declenche sur 2+ failures consecutifs | /10 |
| C4 Outillage | Tools selectionnes selon contexte (curl vs Playwright) | /10 |
| C5 Tracabilite | journal.jsonl + decision_log + RETEX produits | /10 |

Score total /50 -- >= 40 : Exemplaire | 30-39 : Acceptable | < 30 : RETEX obligatoire

## Resources

- [references/workflow.md](references/workflow.md) -- 6-step per-rule procedure with examples
- [references/output-schema.md](references/output-schema.md) -- lia-fingerprint-v2-independent JSON schema
- [references/legal-context.md](references/legal-context.md) -- Why this skill exists, GPL/MIT/BSD/sui generis
- [references/tracking-convention.md](references/tracking-convention.md) -- Session subdir + journal format
- [scripts/init_batch.sh](scripts/init_batch.sh) -- Bootstrap new batch session subdir
- [scripts/check_duplicates.sh](scripts/check_duplicates.sh) -- **Pre-flight dedup gate (BLOQUANT)** added 2026-05-07
- [scripts/build_master_list.sh](scripts/build_master_list.sh) -- Regenerate MASTER_LIST.md + MASTER_TODO_LIST.md from all journal.jsonl
- [scripts/build_category_tracker.sh](scripts/build_category_tracker.sh) -- Regenerate CATEGORY_TRACKER.md (theme rotation guide)
- [scripts/verify_rule.py](scripts/verify_rule.py) -- Verify a single rule's quality gates
- [scripts/nightly_fingerprint_batch.sh](scripts/nightly_fingerprint_batch.sh) -- **Nightly automation orchestrator** (w01-w10 waves, runs continuously; also accessible at `scripts/nightly_fingerprint_batch.sh` via symlink)
- [scripts/mark_vendor_dead.py](scripts/mark_vendor_dead.py) -- **DEPRECATED c68 (A99), hard-exits if invoked**. Cycle 5 script; c52 proved it classified vendors dead on fake `vendor_website` URLs with no real HTTP fetch (79% FP, destructive). Superseded by [scripts/verify_vendor_alive.py](scripts/verify_vendor_alive.py) (re-audit) + [scripts/reverify_no_http_gate.py](scripts/reverify_no_http_gate.py) (correct live-verify pattern)
- [scripts/reverify_no_http_gate.py](scripts/reverify_no_http_gate.py) -- Cycle 5: re-verify rules with no http_gate field (sample-of-5 gate + --apply)
- [scripts/backfill_html_sha256.py](scripts/backfill_html_sha256.py) -- Cycle 5: backfill artifacts.html_sha256 from live capture (header/cookie match ONLY per "hash=solution not vendor" rule)
- [scripts/archive_vendor_dead.py](scripts/archive_vendor_dead.py) -- Cycle 5: move vendor_dead rules to `patterns/web-signatures/archive/` (not loaded by runtime)
- [scripts/onyphe_engine_audit.py](scripts/onyphe_engine_audit.py) -- **Cycle 6: REAL liaprobe Go engine audit via `bin/recette-onyphe`**. Loads 10102 patterns, audits 6265 Onyphe ground-truth banners, outputs ONYPHE_RULE_EVIDENCE_ENGINE + ONYPHE_RENAME_PROPOSALS
- [scripts/onyphe_audit_web.py](scripts/onyphe_audit_web.py) -- Cycle 6: Python evaluator audit (fast iteration, web-signatures only). Complements engine audit -- engine = source of truth.
- [scripts/plan_backfill_gen.py](scripts/plan_backfill_gen.py) -- **c69 (A105)**: tracked+tested successor of the c55 one-shot `_alire/temp/c55_plan_backfill_gen.py`. Generates BACKFILLED PLAN stubs for retex_only cycles. Unified score/date regex handles every legacy RETEX header format (`Score agentique : N/50`, `**Score :** N/100`, `**Agentic score** : N/50`, `Score: **N/50**`, `**Date**  :` variants). `--dry-run` default-safe (a real `--apply` writes >5 files, R3-gated). Any future tool that backfills PLAN stubs from RETEX MUST reuse this format-agnostic extractor -- never re-introduce an `agentique`-only regex (root cause of the 14-cycle A105 carry).
- [scripts/test_*.py](scripts/) -- Unit tests: test_wave_validator (18), test_wave_processor (9), test_nightly_skip (4), test_onyphe_audit (31), test_plan_backfill_gen (9) = **71 total**. Run from the SKILL dir: `cd .claude/skills/liaprobe-fingerprint-rebuild && python3 -m unittest discover -s scripts -p "test_*.py"` -> `Ran 71 tests OK`. NOTE (A125, c72): this is the SKILL scripts suite. The repo-root `/opt/lia-sec/dev/scripts/` is a SEPARATE suite (test_classify_tier + test_rules_inventory + test_verify_vendor_alive_v3 ; **62 tests as of c74 2026-05-15**, was 52 at c72 / 56 at c73 -- it grows as the vendor-alive verifier hardens) -- do NOT conflate the two ; c71 mis-attributed the repo-root count to this line while building A124's `scripts/test_rules_inventory.py`. Line count here (71, the SKILL suite) verified exact 2026-05-15.
- `scripts/verify_cycle_traceability.py` -- **c53 BLOCKING gate** : scans tracking/ + retex/ for PLAN+RETEX pair completeness per PDCA scope. Exit 2 on consecutive gap. Run as Phase 0 pre-flight every new cycle.
- `scripts/rules_inventory.py` -- **c50 inventory tool** : `--snapshot --cycle N` writes per-cycle JSON snapshot, `--history` lists snapshots chronologically, `--diff --from X --to Y` shows per-scope/per-directory delta, `--retex-stub --cycle N` (c52) emits markdown-ready delta section. **c71 (A124) per-session scoping** : `--session <slug>` writes `RULES_INVENTORY_<date>_c<N>__<slug>.json` + embeds `session` in the record + filters `--history`/`--diff`/`--retex-stub` + computes the delta against the SAME session's previous snapshot. MANDATORY when `git log` shows a concurrent rule-writing track (e.g. `fingerprint-lab-4patches`) so the two tracks stop overwriting each other's cN snapshot (c70 falsified-`+1` incident). Legacy `_c<N>.json` form (no `--session`) stays valid byte-identical, opt-in. Unit test: `scripts/test_rules_inventory.py` (13 tests). Detail: `.claude/rules/liaprobe-rules-inventory.md` section "Per-session scoping (A124)".
- `scripts/verify_vendor_alive.py` + `scripts/reset_vendor_dead_alive.py` -- **c52 vendor_dead re-audit tools** : 3-priority URL candidate generation (vendor_slug > product_slug > original), HTTP probe classification (reset_alive / manual_review / keep_dead). Reset script has `--dry-run` mandate.
- `scripts/verify_vendor_alive_v2.py` -- **c55 v2** : HTML title + body vendor-name match (kills v1 slug-only FP class). Output `VENDOR_DEAD_AUDIT_V2_*.json`.
- `scripts/verify_vendor_alive_v3.py` -- **c70 (A104)** : v3 verifier importing v2 helpers (DRY). Fixes the 4 v2 weaknesses: tld_brand weighted LOWER (alone -> `confirmed_alive_weak`, not `_high`), generic/placeholder titles ("Redirecting"/"Site Title"/"STRATO parked"/empty) ignored as signal, `product_slug` accepted as alternate match key (lifts product-named pages e.g. Verizon DMS -> EdgeCast), `<meta http-equiv=refresh>` follow. `--reclassify` (default) is DETERMINISTIC + NO network (reads a v2 audit JSON, recomputes, emits `VENDOR_DEAD_AUDIT_V3_*.json` with v2->v3 delta); `--live` (network) re-fetches WEAK+unverified subset with meta-refresh follow. Unit test: `scripts/test_verify_vendor_alive_v3.py` (**21 tests** : 15 c70/c73 + 6 c74). Audit-only -- never mutates rules (the `vendor_dead` reset stays the `--dry-run`-gated `reset_vendor_dead_alive.py`). Any future vendor-liveness verifier MUST keep tld_brand-alone below high and accept the product axis. **c73 (A104-followup)** : `--live` now PERSISTS a `VENDOR_DEAD_AUDIT_V3_LIVE_<date>.json` (`build_live_report()` pure fn, shared module-level `RANK`, honors `--out`, default inventory path) -- c70 had `--live` print to stdout and write nothing. **c74 (A126) CLOSED** : the `--live` subset filter is now a pure testable fn `live_subset(data)` that accepts BOTH a V2-json shape (legacy predicate byte-identical) AND a V3-json shape -- the v3 clause (`recommendation_v3` in {confirmed_alive_weak, alive_unverified}) is **schema-gated** on `data["schema"]=="vendor-dead-audit-v3"` so a re-saved V2-json carrying a stray `recommendation_v3` cannot silently widen the subset (R3, adversarial-critique-driven). Live re-run on the c70 V3 json : subset **14** (was 5 at c73 = the 13 v3-rec entries + Verizon via legacy clause A ; the "13" in the A126 plan omitted that legacy-A overlap, reality is 14 -- R26 in-place corrected), the 9 `confirmed_alive_weak` meta-refresh entries now actually live-tested, **4 recovered** weak->medium (Frontstory/Elevio/CookieBAR/Claspo : live body found product tokens the c70 deterministic missed on empty/redirect titles), **0 downgraded** (no false-promote). ibm.io/litespeed.ai stay `confirmed_alive_weak` -- `meta_refresh=False` observed : their "Redirecting..." is a JS redirect with NO `<meta http-equiv=refresh>`, so `live_follow` correctly does not follow and stays conservative (R18 observed, not the A127 hypothetical). NEW KNOWN LIMITATION (queued **A127**) : `v2.absolutize` does not resolve a meta-refresh `content="url=relative.html"` (no leading slash) -> `fetch_page` ValueError -> silent `dead_now`. Hypothetical for this subset (c70 fixtures show absolute `url=https://`), and `v2.*` helpers are byte-identical contract, so flagged + queued, NOT bodged here (R3/R18/feedback_never_delete_code).

## Nightly Automation Mode

The skill supports a fully automated nightly mode via `scripts/nightly_fingerprint_batch.sh`.

**Cadence:** script runs all 10 waves (w01-w10) sequentially and repeatedly overnight.
**Session IDs:** `nightly_YYYYMMDD_wNN` (no session subdir created).
**Progress tracking:** MASTER_TODO_LIST.md tags (`nightly-batch`, `nightly-obsolete`).
**Symlink:** `scripts/nightly_fingerprint_batch.sh` in the repo root points to this file.

Wave configuration: each wave targets a distinct product slice from MASTER_TODO_LIST.md
(FILE_ONLY entries) and converts them to AUTHORED via the 6-step per-rule workflow.

## Tracking artifacts (auto-generated, in `_alire/tracking/liaprobe-fingerprint-rebuild/`)

- `MASTER_LIST.md` -- deduplicated AUTHORED products from all journals
- `MASTER_TODO_LIST.md` -- full inventory with checkbox state per product
- `CATEGORY_TRACKER.md` -- count + samples per category for theme rotation
- `SESSIONS_INDEX.md` -- per-batch table (verdict, declared cumul)

## Related skills

- `/liaprobe-rule-enrich` (vendor alias scoring) -- complementary, vendor canonical_id resolution
- `/fingerprint-lab-improve` -- offline recette validation (5406 cas), composes with this skill for validate-after-author flow
- `/replan` -- invoked on 2+ consecutive failures
- `/retex-analyzer` -- end-of-batch retrospective if score < 40

## Onyphe Ground-Truth Audit (Cycle 6 -- 2026-05-12)

Liaprobe ships a dedicated Go tool that runs the real engine against Onyphe ground-truth banners:

```bash
cd /opt/lia-sec/liaprobe
bin/recette-onyphe -f /opt/lia-sec/dev/_alire/temp/onyphe_recette_full_6265.jsonl \
    -out json -src all -limit 0
```

Wrapper Python: `scripts/onyphe_engine_audit.py` -- parses engine JSON output and produces:

1. **`ONYPHE_ENGINE_AUDIT_<DATE>.json`** -- global verdict summary (CORRECT/WRONG/MISS/NO_PATTERN)
2. **`ONYPHE_RULE_EVIDENCE_ENGINE_<DATE>.json`** -- per-rule TP proof:
   - `pattern_id`, `rule_file`, `current_product`
   - `tp_count`, `gt_products_seen` (Onyphe canonical names + counts)
   - `samples` (up to 10: gt_product, gt_version, port, protocol, det_conf, banner snippet)
   - `canonical_onyphe_product` (dominant GT product across TP samples)
3. **`ONYPHE_RENAME_PROPOSALS_<DATE>.json`** -- where rule.product != Onyphe canonical:
   - `pattern_id`, `rule_file`, `current_product`, `proposed_product`
   - `tp_count_supporting`, `gt_distribution`

### Sample run (200 banners): 99.5% CORRECT, 0.5% MISS, 11 proven rules, 4 rename proposals

Example rename proposal:
```json
{
  "pattern_id": "akamai_akamaighost",
  "current_product": "GHost",
  "proposed_product": "AkamaiGHost",
  "tp_count_supporting": 2
}
```

### Why this matters

- **Authoritative validation** : uses real Go engine, not Python re-implementation
- **Real-traffic proof** : a rule with TP > 0 is provably effective on wild banners
- **Taxonomy unification** : align rule product names with Onyphe's canonical naming for easier downstream integration (CVE matching, vendor alias resolution via `/liaprobe-rule-enrich`)

### Pre-flight ordering

When auditing patterns:
1. Run `onyphe_audit_web.py --sample 5` (Python, fast) for iteration / debugging
2. Run `onyphe_engine_audit.py --apply` (Go engine) for canonical audit & evidence

### Rename rule workflow (proposed, cycle 7 candidate)

When a rule has `tp_count_supporting >= N` AND `proposed_product` is consistent across all GT samples:
- Update `rule.product` to `proposed_product`
- Add `_lia_independent_authoring.onyphe_canonical_name = "<proposed>"`
- Add `_lia_independent_authoring.onyphe_evidence = {tp_count, samples_ref}`

Apply via dedicated script `apply_onyphe_rename.py` (not yet implemented).
