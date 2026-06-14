# MAF Standard Alignment -- Microsoft Agent Framework subjects in the recette

> The recette corpus has TWO agent families behind ONE model: **git agents**
> (github/gitlab) and **standard-aligned agents** following the **Microsoft
> Agent Framework (MAF, `microsoft/agent-framework`)**. This rule fixes the MAF
> conventions so new subjects, judges, and UI stay aligned with the standard and
> with each other. Ground truth in code: `recette/maf_judge.py`,
> `recette/maf_orchestration.py`, `recette/simulate.py`,
> `corpus/schemas/agent-manifest.schema.json`, `corpus/maf_agents/`,
> `corpus/maf_orchestration/`.

## Unified agent model (one schema, `kind` discriminator)

- A single manifest schema covers both families. `kind` is the discriminator:
  `"git_agent"` | `"maf_agent"` (`agent-manifest.schema.json`). NEVER fork the
  schema per family -- extend the shared one.
- Provenance of an imported standard agent lives under `source`:
  `source.standard = "microsoft-agent-framework"`, `source.maf_kind` (the MAF
  top-level `kind`, e.g. `Prompt`), `connection_kind` (MAF
  `model.connection.kind`, e.g. `remote`). Preserve these on import; do not
  invent values.
- A `maf_agent` declares **tool/handoff** capabilities, not git actions:
  `tool_kind ∈ {mcp, function, web_search, file_search, code_interpreter}` and
  `approval ∈ {never, always}`. A git agent declares `action`/`mode`/resources.
  The two capability shapes are mutually exclusive per `kind`.

## MAF execution semantics to honour

- **Single subject** (`recette/simulate.py`): a multi-turn loop drives the
  subject; every tool call is captured as a `MafAction` against the declared
  agent-spec. `approval=always` tools count as approved ONLY if the injected
  approver grants it -- never optimistically (I6). `judge_maf` scores the action
  log on the 4 dimensions.
- **Orchestration / teams** (`recette/maf_orchestration.py`): grounds on the
  real `HandoffBuilder` model -- `participants` + `with_start_agent` + a
  per-source `HandoffConfiguration` set. A transfer to a target OUTSIDE that set
  is an error (`ValueError("attempted to handoff to unknown target")`), and a
  `termination_condition` bounds the run. Model a team as `team.json` (declared)
  + `run.json` (ordered hops + per-participant tool calls). Judge the TEAM on the
  same 4 dimensions as a single subject.
- One judge vocabulary: the four recette dimensions (identity, capabilities,
  policy, behavior) + `violation_type` for negatives apply identically to
  `maf_agent` and orchestration. Route by `kind` through the
  `judge_subject` dispatcher; do not write a parallel verdict shape.

## Determinism (I4) -- non-negotiable for MAF judges

- MAF judgement is a **pure function** of `(spec/team, action-log/run)`: no
  clock, no random, stable iteration order (see the module docstrings, which
  state this explicitly). A real provider is used only in `real_mode`, where the
  run is **recorded, not replayed**; replay uses `StubLlm`/`ReplayLlm` for a
  byte-stable result.
- Never introduce `time.time()`/`datetime.now()`/`random` into a MAF
  decision/judge path. See `determinism-replay.md`.

## Operational metadata vs event/judge data (the timestamp rule)

- The MAF/standard **decision** records (AgentActionEvent, MafAction, the judged
  run) carry a **captured** `timestamp` as an INPUT (logical clock, I4) -- never
  read from the wall clock during judging.
- **Operational** records ABOUT a run (the ephemeral `Run` in
  `recette/api/runs.py`: `id` uuid4, `created_at`, `status`) MAY carry wall-clock
  metadata for the operator UI. These are NOT AgentActionEvent fields and never
  enter the decision/replay path, so a wall-clock `created_at` there is allowed
  and expected (MAF/ops run records are timestamped). Surface it in the console
  (e.g. the run-history journal), keep it out of the judged event stream.

## Checklist for a new MAF subject / judge / UI

- [ ] Manifest uses the shared schema with `kind: "maf_agent"` + `source.*`.
- [ ] Capabilities are tool/handoff shaped (`tool_kind`, `approval`), not git.
- [ ] Negatives break EXACTLY one dimension (`violation_type`), like every other
      corpus agent (`recette-corpus.md`).
- [ ] Judge is deterministic (pure, no clock/random) + has a replay test (I4).
- [ ] Approval-gated tools enforce I6 (no optimistic execution).
- [ ] Orchestration handoffs stay inside the declared `HandoffConfiguration`
      set; out-of-set transfer is an error, not a silent allow.
- [ ] UI for runs shows operational metadata (`created_at`, status) without
      treating it as ground truth.

## Related

- `canonical-event-model.md` -- AgentActionEvent (the captured `timestamp`).
- `recette-corpus.md` -- 4 dimensions, positives + negatives, mono-axis rule.
- `determinism-replay.md` (I4), `invariants.md` (I6 approval blocking).
- `docs/runbooks/orchestration-recette.md` -- running the MAF orchestration recette.
