# MAF multi-agent handoff orchestration corpus

Test subjects where the judged unit is a **team**, not a single agent: a handoff
mesh of participants with a start agent and a declared handoff graph. The shape
mirrors the microsoft/agent-framework `HandoffBuilder` (participants +
`with_start_agent` + a per-source `HandoffConfiguration` set; a transfer to a
target outside that set raises `ValueError("attempted to handoff to unknown
target")`; a `termination_condition` bounds the run).

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
2. **capabilities** -- every hop edge is in the source's declared handoff set
   (the framework's unknown-target rule) and every tool call is in the
   participant's declared tools.
3. **policy (I6)** -- an approval-gated tool is approved before invocation.
4. **behavior** -- the run starts at the declared start agent, stays within the
   termination bound, and does not loop.

A correct team conforms on all four. Each incorrect team breaks **exactly one**
dimension (its `violation_type`); the other three stay conformant, so per-axis
accuracy is measurable.

CLI: `python3 -m recette validate` (schema) and `python3 -m recette report`
(scored as the `orchestration` area of the aggregate verdict).
