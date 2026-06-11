# Downstream contract

The nightly harvest produces evidence packages. Two consumers picked it up:

## 1. APEX cycle (current target)

Plan file: `_alire/tracking/PLAN_APEX_LIAPROBE_FINGERPRINT_REBUILD_CYCLE<N>_<DATE>.md`

The APEX cycle decides whether each evidence row should be promoted into
the actual JSON rule. Workflow:

1. Read `nightly_manifest.jsonl` of yesterday's run.
2. For every (rule_id, source) tuple with `any_probe_matched=true` and
   `match_score >= confidence_threshold`:
   - Open the rule JSON.
   - Update `artifacts.html_sha256`, `artifacts.headers_sha256`,
     `artifacts.capture_url`, `artifacts.capture_date`.
   - Set `_lia_independent_authoring.http_gate = {date, verified: true,
     http_status, note}`.
   - Drop `_lia_independent_authoring.wild_traffic_unconfirmed`.
3. Run the recette (`/recette-lia-rule` or APEX recette gate).
4. Commit the JSON update referencing the manifest path as evidence.

## 2. liaprobe-rule-enrich (optional downstream)

After promotion, `/liaprobe-rule-enrich` adds CVE awareness, MITRE ATT&CK,
D3FEND mapping using the now-real `vendor` + `product` confirmed by the
nightly capture (vendor names verified against actual deployments).

## Failure handling

If `any_probe_matched=false` despite a 200 OK capture:

- The rule's regex does not match the live response.
- Options: (a) widen the regex, (b) the rule is FP-prone, (c) the
  technology changed (deprecation, rebranding).
- The evidence MUST stay archived for at least 30 days for adversarial
  review.

## Non-goals

- The nightly skill DOES NOT modify any JSON rule directly. It produces
  evidence. Promotion is always a deliberate APEX action.
- The nightly skill DOES NOT call private vendor APIs. Only public free
  tier endpoints and offline datasets.
