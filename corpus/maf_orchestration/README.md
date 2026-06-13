# MAF multi-agent handoff orchestration corpus

Test subjects where the judged unit is a **team**, not a single agent. Three
orchestration styles, mirroring the microsoft/agent-framework builders, selected
by `team.style`:

- `handoff` (default) -- a mesh routed by `handoff_to` (`HandoffBuilder`:
  participants + `with_start_agent` + a per-source `HandoffConfiguration` set; a
  transfer outside that set raises `ValueError("attempted to handoff to unknown
  target")`; a `termination_condition` bounds the run). The run is `hops`.
- `sequential` -- an ordered chain, each participant once in declared order
  (`SequentialBuilder`). The run is `order`.
- `concurrent` -- fan-out/fan-in, each participant once on the same input
  (`ConcurrentBuilder`, aggregating in participant order). The run is `order`.

Each subject directory holds:

- `team.json` -- what the orchestration DECLARES (participants, start agent,
  handoff graph, tools per participant). Validated against
  `corpus/schemas/maf-orchestration.schema.json`.
- `run.json` -- what it ACTUALLY did (ordered handoff hops + per-participant tool
  calls). Validated against `corpus/schemas/maf-orchestration-run.schema.json`.
- `ground-truth.json` -- the four-dimension verdict the recette expects
  (`corpus/schemas/ground-truth.schema.json`).

The judge is `recette.maf_orchestration.judge_orchestration` (deterministic, I4):

1. **identity (I3)** -- each participant's tool calls use its declared provider+model.
2. **capabilities** -- handoff: every hop edge is in the source's declared
   handoff set (the unknown-target rule); sequential/concurrent: every executed
   participant is declared. Plus every tool call is in the participant's tools.
3. **policy (I6)** -- an approval-gated tool is approved before invocation.
4. **behavior** -- handoff: starts at the declared start agent, within the
   termination bound, no loop; sequential: the executed order equals the declared
   participant order; concurrent: each declared participant ran exactly once.

A correct team conforms on all four. Each incorrect team breaks **exactly one**
dimension (its `violation_type`); the other three stay conformant, so per-axis
accuracy is measurable.

CLI: `python3 -m recette validate` (schema) and `python3 -m recette report`
(scored as the `orchestration` area of the aggregate verdict).
