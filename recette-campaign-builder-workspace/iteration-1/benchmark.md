# Benchmark -- recette-campaign-builder, iteration 1

Two test cases, each run with the skill and without (baseline = same prompt, no skill).
Grading is programmatic (see grade_eval.py): verdict mapping correct, help fields present,
deterministic harness reports PASS with no MISMATCH.

| Config | eval-0 (crm-deny) | eval-1 (soc-allow) | pass rate | avg time | avg tokens |
|--------|-------------------|--------------------|-----------|----------|------------|
| with_skill    | 3/3 | 4/4 | 100% | 97.1 s  | 56,808 |
| without_skill | 3/3 | 4/4 | 100% | 123.0 s | 53,061 |

Delta: pass-rate parity; with_skill ~21% less wall time (97 vs 123 s), ~7% more tokens.

## Per-eval

- **eval-0 crm-export-deny** (deny-by-default, no catalog/bundle edit needed): both configs
  produced a non-privileged `crm_agent` with `export_customer_base` + `bulk_modify_contacts`
  expect=deny, help fields filled, harness PASS. Non-discriminating.
- **eval-1 soc-allow-escalate** (ALLOW via bundle rule + catalog a missing action): both configs
  produced `suspend_user` allow (executes) + `isolate_host` escalate (pends). The baseline
  succeeded by reusing the `bnp-v1` EXTRA_RULES/EXTRA_SPECS already committed in
  run_bnp_scenarios.py -- i.e. the answer was already in the repo.

## Analyst note (honest)

This eval set does NOT discriminate on correctness: a capable baseline (sonnet) matches the skill
because the repo already contains 10 worked campaigns and the harness already encodes the SOC
verdict rules the second case needs. The skill's measured value here is **speed and consistency**
(less exploration, ~21% faster, help fields enforced), not correctness.

To actually stress the skill, iteration 2 should use cases whose answer is NOT in the repo:
- a C4-ALLOW trap (engine denies an uncatalogued C4 action -> the naive answer fails the harness);
- a threshold scenario ("freeze if amount > X") that tempts adding non-deterministic engine logic
  (the skill forbids it; a baseline may try and break I4);
- a brand-new domain with no existing example to crib from.
