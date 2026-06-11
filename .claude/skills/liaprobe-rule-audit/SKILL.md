---
name: liaprobe-rule-audit
description: Consolidated quality audit of a LiaProbe fingerprint rule (or a whole tier) across 7 dimensions -- schema, id-collision, CPE validity, enrichment coverage, provenance/legal clean-room, matcher sanity, lifecycle state -- producing a per-rule findings report (CRITICAL/HIGH/MEDIUM/LOW/INFO) + 0-100 score + letter grade. Read-only, never mutates rules. Triggers on "/liaprobe-rule-audit <path>", "audite cette rule liaprobe", "audit fingerprint rule", "qualite d'une signature liaprobe", "rule audit report", or when the editor UX requests an audit. Differs from /liaprobe-rule-enrich (mutates: adds CVE/EOL/MITRE) and /liaprobe-fingerprint-rebuild (mutates: clean-room re-author) -- this skill only READS and REPORTS.
---

# LiaProbe Rule Audit

Read-only consolidated quality audit. Reuses the dimensions that were
scattered across three places: `bin/lia-rule-validate` (schema),
`/liaprobe-rule-enrich` (CPE classification + enrichment coverage), and
`/liaprobe-fingerprint-rebuild` (provenance/legal clean-room + matcher
signal preference + id-collision Gate 5). One pass, one report.

## When to use

- Before committing a hand-authored / AI-assisted rule (editor UX gate).
- To triage a whole tier ("which rules are worst?").
- As the data source for the frontend `RuleAuditPanel` in the editor.

NEVER use to mutate a rule -- this skill is strictly read-only. Mutating
enrichment is `/liaprobe-rule-enrich`; clean-room re-author is
`/liaprobe-fingerprint-rebuild`.

## The 7 dimensions

| Dim | Checks | Worst severity |
|-----|--------|----------------|
| D1 SCHEMA | parse, `$schema` tag, `id` + (`product` or `taxonomy_name`) | CRITICAL |
| D2 ID_COLLISION | generic id (unknown/nginx/...), corpus id shared by 2+ rules (engine picks one winner -> TP=0 risk) | HIGH |
| D3 CPE_VALIDITY | no_cpe (MEDIUM) / `:o:` OS-host (HIGH) / `$1`\|`*` placeholder product (HIGH) / unparseable (MEDIUM) | HIGH |
| D4 ENRICH_COVERAGE | known_cves / lifecycle / attack_surface / `_meta_enrichment` presence | LOW |
| D5 PROVENANCE_LEGAL | `_lia_independent_authoring` block, `third_party_catalog_references_consulted == NONE`, `capture_url` when html_sha256, no `vendor_marketing_site` | HIGH |
| D6 MATCHER_SANITY | >=1 matcher (CRITICAL if zero), strong signal class (header/cookie/banner > body-only) | CRITICAL |
| D7 LIFECYCLE_STATE | `enabled=false` + disable audit marker | INFO |

Scoring: 100 minus per-finding weight (CRITICAL 40, HIGH 20, MEDIUM 8,
LOW 3, INFO 0). Grade A>=90 B>=75 C>=60 D>=40 F<40.

## Tooling

- `scripts/audit_rule.py` -- the auditor (pure stdlib, no external deps).
  - `audit_rule.py <rule.json> [--corpus-root <patterns/>] [--json]`
  - `audit_rule.py --tier <patterns/tier> [--json]` (aggregate)
  - `--corpus-root` enables D2 id-collision (scans corpus once, cached).
- `scripts/test_audit_rule.py` -- 15 unit tests (TDD red-green).
- Backend endpoint `GET /api/liaprobe/rules/{tier}/{id}/audit` -- Go-native
  per-rule audit (same dimensions, no Python dep) consumed by the editor UX.

## Decomposition (agentic)

1. RESOLVE_TARGET   : single rule path OR tier dir
2. RUN_AUDIT        : audit_rule.py (build id-index once if corpus-root given)
3. CLASSIFY         : group findings by dimension + severity
4. PRIORITIZE       : CRITICAL/HIGH first, file:line where applicable
5. REPORT           : JSON (machine) or table (human); never mutate

## Model selection

- haiku: tier triage, grep/scan-style aggregation.
- sonnet: interpreting findings, proposing fixes (which dimension to act on,
  whether a CPE :o: is a real correction candidate vs dead product).
- opus: orchestration only.

## Traceability

Log non-trivial audit verdicts (a tier batch, a FAILURE verdict feeding a
PDCA gate) to `_alire/02_LOGS/Journals/decision_log.jsonl`. A per-rule audit
in the editor UX is interactive and need not be logged.

## False-positive discipline (R18)

The auditor was validated on the real corpus before shipping. Incident
2026-05-29: an initial `missing_product` CRITICAL fired on all 907
service-detectors (they carry `taxonomy_name`, not `product`) -- a schema-
variant false positive, fixed by accepting either field. Always validate a
new dimension against a real tier (`--tier`) before trusting its counts;
never bake an unverified rule into the auditor.

## Score agentique /50

| C1 Decomposition | 5 sous-taches | /10 |
| C2 Planification | PLAN.md cree | /10 |
| C3 Replanification | fix faux-positif sur donnees reelles | /10 |
| C4 Outillage | auditor stdlib + tests + endpoint Go | /10 |
| C5 Tracabilite | decision_log si batch/gate | /10 |

## Related

- `/liaprobe-rule-enrich` -- mutating CVE/EOL/MITRE enrichment (D4 is its output).
- `/liaprobe-fingerprint-rebuild` -- mutating clean-room re-author (D5 is its concern).
- `bin/lia-rule-validate` -- schema-only Go validator (D1 subset).
- `/code-reviewer` -- analogous adversarial review, but for source code.
