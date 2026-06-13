# Plan : Multi-agent handoff orchestration recette (MAF)
Date : 2026-06-13
Status : TERMINE
Invariants concernes : I3 (identity), I4 (deterministic replay), I6 (approval gate)

## Objectif
Add multi-agent handoff orchestration to the recette: a TEAM of MAF agents
(participants + start agent + handoff graph) judged on the four dimensions.
Grounded on the real microsoft/agent-framework handoff model (HandoffBuilder,
HandoffConfiguration, unknown-target ValueError, termination_condition) -- not
invented. Closes the "Multi-agent handoff scenarios" TODO item.

## Real MAF model reused (python/packages/orchestrations/.../_handoff.py)
- `HandoffBuilder(name, participants, termination_condition).with_start_agent(x).build()`
- `HandoffConfiguration(target_id, description)` ; registry `_handoff_config: dict[source_id, set[target]]`
- Routing: response carries `handoff_to` -> route to target.
- Rule: handoff to a target NOT registered for the source -> `ValueError "attempted to handoff to unknown target"`.
- Termination: `termination_condition` callable on the full conversation.

## Mapping to recette (judged unit = team)
- Dim 1 identity (I3): every per-agent action's provider+model matches that participant's declared identity.
- Dim 2 capabilities: every hop (from,to) edge in from-agent's declared handoff targets (MAF unknown-target analog) + each invoke_tool in the participant's declared tools.
- Dim 3 policy (I6): a gated tool (approval=always) is approved before invocation.
- Dim 4 behavior: first hop source == declared start_agent ; no handoff loop beyond threshold ; within termination max_hops.
- Returns the existing `IdentificationResult` -> same ground-truth comparison as the single-subject MAF harness.

## Etapes
- [x] Schema `corpus/schemas/maf-orchestration.schema.json` (team) + `maf-orchestration-run.schema.json` (run)
- [x] `recette/maf_orchestration.py` : dataclasses + `judge_orchestration(team, run) -> IdentificationResult` (pure, I4)
- [x] `recette/maf_orchestration_harness.py` : discover + judge + Scorecard (mirror maf_harness)
- [x] Corpus `corpus/maf_orchestration/` : 1 correct + 4 negatives (one per violation_type, mono-axis)
- [x] Wire `recette/report.py` (FullReport.orchestration) + `recette/__main__.py` + subjects router
- [x] Frontend: Discovery scorecard page surfaces the orchestration row (fixture + render-assert), no new CSS/HTML
- [x] Tests `tests/test_maf_orchestration.py` (4 dims, single-axis orthogonality, determinism)

## Decisions prises
- Team is self-contained (participants embed declared identity/handoffs/tools) -> no cross-file refs, deterministic.
- Reuse IdentificationResult + ground-truth.schema.json -> zero new verdict contract.

## Resultat
Done. 693 backend tests + 203 console tests green; ruff/mypy/bandit clean on new
Python; tsc clean. `python3 -m recette report` -> orchestration 5/5 teams PASS,
aggregate PASS. judge_orchestration is a pure function of (team, run) -> replays
identically (I4). Single-axis orthogonality enforced by
test_each_negative_breaks_exactly_one_dimension.
