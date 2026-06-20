# Orchestration graph -- runbook

> A multi-agent orchestration run (MAF team) seen as a **directed graph**:
> nodes = participants, edges = handoffs weighted by the number of transfers.
> The subsystem computes graph signals (in/out degrees, tool-call volume,
> weighted PageRank) as observability/risk indicators on what the team ACTUALLY
> did, and renders a Mermaid visualization of the declared structure and of the
> path actually taken.
>
> Code (pure, deterministic I4):
> - `recette/orchestration_graph.py` -- interaction graph + metrics (PageRank).
> - `recette/viz.py` -- Mermaid rendering (`team_mermaid`, `run_mermaid`).
> - `recette/run_view.py` -- step-by-step view (timeline + verdict + diagram).
> - `recette/maf_orchestration.py` -- run model + 4-dimension verdict.

## Why this subsystem exists

The orchestration recette judges a TEAM (no longer an isolated agent) on the 4
usual dimensions. But a `correct`/`incorrect` verdict does not tell where the run
transited nor which agent concentrates control. The orchestration graph makes
this structure **legible** (legibility-first principle): a third party who did
not write the team can see, from the UI/CLI alone, the participant mesh, the
weight of each handoff, and which agent carries the most flow.

The mechanism is borrowed from the AgentMonitor approach (graph attributes on
agent exchanges); the heavy ML "predict-before-execute" regressor is
deliberately NOT borrowed (it would add a non-stdlib dependency, R20 -- see the
docstring of `recette/orchestration_graph.py`).

## The data model (inputs / outputs)

The subsystem feeds on an orchestration subject from the corpus, under
`corpus/maf_orchestration/correct/<slug>/` or `.../incorrect/<slug>/`:

- `team.json` -- what the team DECLARES: `agent_id`, `name`, `style`,
  `participants` (each with `agent_id`, `handoffs`, `tools`, `declared_identity`),
  `start_agent`, `termination`. Validated against the `maf_orchestration` schema
  (`recette/manifest.py`).
- `run.json` -- what the team ACTUALLY did. Loaded by
  `run_from_doc(doc)` (`recette/maf_orchestration.py`) into an `OrchestrationRun`:
  - `hops`: list of `HandoffHop(seq, source, target)` -- the control transfers
    (`from`/`to` fields in the document).
  - `order`: the ordered list of executed participants (sequential chain,
    concurrent fan-out, or group_chat/magentic rounds).
  - `actions` -> `calls`: list of `ToolCall(seq, agent_id, provider, model,
    target, tool_kind, approved)` -- the tool invocations.

`interaction_graph(run)` produces the graph:

```json
{
  "nodes": [
    {"id": "...", "in_degree": 0, "out_degree": 0, "tool_calls": 0, "pagerank": 0.0}
  ],
  "edges": [
    {"source": "...", "target": "...", "weight": 1}
  ]
}
```

- `nodes` covers the sorted union of `run.order`, the sources/targets of the hops
  and the `agent_id` of the tool calls.
- `in_degree` / `out_degree` are the sum of the weights of the incoming/outgoing edges.
- `tool_calls` is the number of tool calls per agent.
- `pagerank` is a weighted PageRank (by power iteration), rounded to 4 decimals.

### Determinism (I4)

PageRank is computed by power iteration with a FIXED iteration count
(`_ITERATIONS = 60`) and a fixed damping (`_DAMPING = 0.85`), over **sorted**
nodes, with no clock and no randomness; nodes with no outgoing edge (dangling)
redistribute their mass uniformly. `interaction_graph`, `team_mermaid`,
`run_mermaid` and `build_run_view` are PURE functions of their inputs -- same
input => same byte-stable output (I4).

## The flow

```mermaid
flowchart TD
    corpus["corpus/maf_orchestration/<slug>/<br/>team.json + run.json"];
    runfromdoc["run_from_doc()<br/>-> OrchestrationRun"];
    graph["interaction_graph()<br/>nodes + weighted edges + PageRank"];
    viz["viz.team_mermaid / viz.run_mermaid<br/>Mermaid diagram"];
    view["run_view.build_run_view<br/>timeline + 4-dimension verdict"];
    api["GET /subjects/orchestration/{agent_id}/graph"];
    cli["python -m recette orchestrate viz"];
    page["Console /graph (Interaction graph)"];

    corpus --> runfromdoc;
    runfromdoc --> graph;
    runfromdoc --> viz;
    runfromdoc --> view;
    graph --> api;
    viz --> cli;
    api --> page;
```

## Concrete touchpoints

### API (FastAPI, router `recette/api/routers/subjects.py`, prefix `/subjects`)

| Verb | Route | Returns |
|------|-------|---------|
| GET | `/subjects/orchestration/{agent_id}/graph` | the interaction graph: `nodes` + weighted `edges` + per-node metrics |
| GET | `/subjects/orchestration/{agent_id}` | the step-by-step view: `steps` (timeline) + `verdict` + `dimensions` + `violations` + `mermaid` |
| GET | `/subjects` | the list of subjects; an orchestration subject carries `family: "maf_orchestration"` |

The handler `orchestration_graph(agent_id)` delegates to
`build_orchestration_graph(agent_id)`, which iterates over
`discover_orchestration_dirs()`, loads and validates `run.json`, then calls
`interaction_graph(run)`. The step-by-step view goes through
`build_orchestration_view` -> `build_run_view` (`recette/run_view.py`), which
includes the Mermaid diagram of the routed path (`run_mermaid`).

There is no global `/api` prefix: these routes are served as-is by the governed
API (canonical port `8090`, launched only via `./recette.sh`, R19).

### CLI (`python -m recette orchestrate viz`)

The Mermaid rendering is exposed on the command line (`recette/cli/parser.py`,
dispatch in `recette/__main__.py`, implementation in
`recette/cli/orchestrate_cmds.py::_cmd_orchestrate_viz`):

```
python -m recette orchestrate viz <team.json>
python -m recette orchestrate viz <recording.json> --run
```

- Without `--run`, the target is a `team.json`: `team_mermaid` draws the DECLARED
  structure according to the `style` (`handoff`, `sequential`, `concurrent`,
  `group_chat`, `magentic`).
- With `--run`, the target is a recording (`OrchestrationRecording`):
  `run_mermaid` draws the path ACTUALLY taken (hops numbered by `seq`, tool calls
  as dotted edges).

The interaction graph itself (degrees / PageRank) is consumed via the API and the
console; it has no dedicated CLI subcommand.

### Console (page `/graph`, "Interaction graph")

`console/src/pages/graph/index.tsx`, mounted on the `/graph` route
(`console/src/App.tsx`). The page:

1. lists the subjects via `listSubjects()` and keeps only those whose
   `family === "maf_orchestration"`,
2. fetches the graph of the selected subject via
   `getOrchestrationGraph(agentId)` (`console/src/api/client.ts` ->
   `GET /subjects/orchestration/{id}/graph`),
3. renders a `flowchart LR` Mermaid (weighted edges + isolated nodes) and a table
   sorted by descending `pagerank` (`agent`, `in`, `out`, `tool calls`,
   `pagerank`).

It is a **read-only, deterministic** page (I4): no external action, no write.

## Failure mode (fail-safe)

- Unknown subject: `build_orchestration_graph` / `build_orchestration_view`
  return `None`, the API handler raises `HTTPException(status_code=404, ...)`
  (`no orchestration subject '...'`). No partial or invented graph.
- `team.json` / `run.json` invalid against the schema: `load_validated` raises,
  the error propagates -- never a silent analysis of malformed data.
- Empty team (0 participants): `_pagerank` returns `{}` (guards `n == 0`), no
  division by zero.
- The subsystem is purely observational: it triggers no external side effect, so
  there is no possible "fail-open" path.

## Invariants upheld

- **I4 (deterministic replay)** -- the core of the subsystem: PageRank with fixed
  iterations over sorted nodes, Mermaid renderings and step-by-step view all PURE
  of their inputs, no clock / no randomness. Same `(team, run)` => same output.
- **I6 (blocking on approval)** -- relayed by the view/verdict: a tool with
  `approval: "always"` invoked without `approved == true` breaks the policy
  dimension (`_check_policy` in `recette/maf_orchestration.py`), never an
  optimistic execution.
- **I3 (identity binding)** -- relayed by the verdict: `_check_identity` verifies
  that each tool call uses the participant's declared `provider`/`model`. The
  graph exposes the flow; the adjacent verdict carries the identity judgment.

The subsystem belongs to the Audit plane (truth/observability/replay): it reads
the corpus and re-presents it, it neither decides nor executes anything.
