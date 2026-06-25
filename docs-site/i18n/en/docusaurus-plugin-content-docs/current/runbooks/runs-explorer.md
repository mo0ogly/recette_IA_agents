# Runs Explorer -- web-only researcher surface for runs, logs, results

> For the research and recette teams. A web-only surface for browsing, reading,
> and replaying every run (agent, campaign, mega-campaign, discovery, recette-full)
> without terminal access or manual parsing of flat files on disk.

## The problem solved

Recette results used to be written as flat files under `docs/tracking/recette/`
and **overwritten on every launch** (the `.PRE.bak` clobber problem). Two concrete
failures:

1. No history -- a new run destroyed the previous one (no eurodate, no grouping).
2. A researcher with web access only cannot reach a flat file on disk and cannot
   manually parse mega-campaign output. The result has to be browsable, readable,
   and replayable from a modern web surface (tree + Monaco), not from a terminal.

Legibility-first principle (CLAUDE.md): a surface that a third party who did not
run the job cannot observe is not recettable. The Runs Explorer is that observable
surface.

## Web-only surface: why this constraint

Researchers evaluating agents generally only have browser access to the console.
They cannot SSH in or run shell commands. The raw output of a SKYNET mega-campaign
can span hundreds of JSONL files that are impossible to read manually. The Runs
Explorer is the answer to this constraint: everything the recette produces is
organized, dated, browsable, and replayable via the web interface -- no disk access
required.

## Eurodated 3-level storage layout

Runs live under `docs/tracking/runs/` (a gitignored directory, operator work-memory,
see R25):

```
docs/tracking/runs/
  <category>/                          level 1: skynet | campaigns | agents | discovery | recette-full
    <YYYY-MM-DDTHH-MM-SS>_<group-id>/  level 2: group = one launch / batch
      _group.json                      group meta: eurodate, label, run list, status
      <run-id>/                        level 3: individual run
        meta.json                      id, kind, eurodate, status, artifacts + sha256, root_hash, replay_of
        annotations.json               MUTABLE layer: tags, comment, label, retention
        artifacts/                     FROZEN surfaces once sealed (*.jsonl, *.json)
        replay.json                    replay descriptor if the run is replayable
  latest/<category> -> ...             symlink to the most recent group per category (back-compat)
```

A SKYNET mega-campaign is a **single group** containing as many runs as agents
launched. Recognized categories: `skynet`, `campaigns`, `agents`, `discovery`,
`recette-full`.

### Eurodate as operational metadata

The eurodate (`YYYY-MM-DDTHH-MM-SS`) is **operational** metadata (wall clock),
analogous to the `created_at` on existing runs in `recette/api/runs.py` (maf-standard
rule). It never enters a decision or replay path -- the registry never reads the clock
itself; the eurodate is passed in as a parameter by the caller (I4).

## How a run is sealed (sha256 chain)

At the end of its execution the producer (runner) seals the run:

1. Compute a `sha256` for every artifact under `artifacts/`.
2. Concatenate the hashes ordered by filename and fold them into a chained
   `root_hash`. Same logic as `scripts/export_anssi_bundle.py` (functions
   `_sha256` / `_chain`).
3. `meta.status` is set to `"sealed"`, the `artifacts[].sha256` fields and
   `root_hash` are persisted in `meta.json`.

The `root_hash` is **tamper-evident**: modifying any artifact changes its sha256,
which changes the root_hash, which makes a comparison fail. A sealed run is
integrity-protected.

## CRUD semantics and I1 / R25 reconciliation (critical)

| Operation | What mutates | What stays frozen |
|-----------|-------------|-------------------|
| Read (`GET`) | -- | everything |
| Annotate (`PATCH`) | `annotations.json` only | `meta.json`, `artifacts/*` unchanged |
| Delete (`DELETE`) | archives the run directory as `.tar.gz`, then purges it | archive remains under `docs/tracking/runs/_archive/` |
| Replay (`POST .../replay`) | creates a NEW eurodated run | parent run unchanged |

**Reconciliation with I1:** artifacts and the `root_hash` in `meta.json` are
treated as frozen (same principle as the append-only event store). The only mutable
layer is `annotations.json` (tags, comment, label, retention) -- the U in CRUD.
Deletion is legitimate because `docs/tracking/` is **gitignored work-memory**
(R25), not the committed audit-plane event store (which stays append-only, I1).
A DELETE never erases an event from the event store -- it archives and purges a
local working copy.

## Replay -- pure recompute, never a live call

A run is replayable if its `kind` has a registered replayer:

| Kind | Replayer |
|------|----------|
| `scorecard` / `govscore` | `recette_govscore.py` -- pure score recompute |
| `agent` | `recette agent replay <recording>` with `ReplayLlm` -- no key, no network call |
| `exchange` | Deterministic mock-lab re-drive + comparison against `proxy_traces` |

Replay **never mutates the parent run**. It creates a eurodated child run whose
`meta.replay_of` points to the parent. Replay is a **pure function**: same
(artifact, policy version) => identical result (I4).

Kinds without a registered replayer return `422 not replayable`.

## `/results` API surface (raw JSON, no envelope)

The API returns raw JSON -- no `{success, data}` envelope (consistent with
`console/src/api/client.ts`).

| Verb + path | Role |
|-------------|------|
| `GET /results/tree` | category > group > run tree |
| `GET /results/{id}` | meta + annotations + artifact list |
| `GET /results/{id}/artifact/{name}` | raw artifact bytes (loaded into Monaco) |
| `POST /results` | register a run or group (called by runners) |
| `PATCH /results/{id}` | update `annotations.json` (tags/comment/label/retention) |
| `DELETE /results/{id}?confirm=true` | archive then purge the run (confirm required) |
| `POST /results/{id}/replay` | spawn a eurodated child run with `meta.replay_of` |

Path-traversal guard: the artifact name is resolved against the `realpath` of the
run's `artifacts/` directory; any attempt to escape it returns `400`.

The prefix `/results` is used (not `/runs`) because `/runs` is already taken by
`recette/api/routers/runs.py` (agent launch / stop).

The registry root is configured via the environment variable
`INSPECT_IA_AGENTS_RUNS_ROOT` (default: `docs/tracking/runs/`) -- never hardcoded
(R5).

## Console interface -- `/runs` route

The page is accessible from the main navigation under the **Runs** link.

### Left pane -- treeview

A recursive `RunTree` component displays the hierarchy:

```
skynet
  2026-06-25T14-30-00_megacamp  [sealed, 12 runs]
    agent-1  [sealed]
    agent-2  [sealed]
    ...
campaigns
  2026-06-25T09-00-00_sec-1
    run-1    [sealed]
```

Each node carries a status badge (`running` / `sealed`) and a kind icon. Clicking
a run loads it in the right pane.

### Right pane -- Monaco + tabs

| Tab | Content |
|-----|---------|
| Content | Monaco (read-only, json/jsonl) on the selected artifact |
| Meta | id, eurodate, kind, per-artifact sha256, root_hash, parent_group, replay_of |
| Annotations | tags, comment, label, retention -- editable (PATCH) |
| Replay | replay button + descriptor; link to the spawned child run |

CRUD controls: rename/tag/retention (PATCH), delete (DELETE, confirmation dialog),
replay (POST). Lazy artifact loading on selection (safe on large JSONL files).
Null-guard on every fetch: a run being written displays without crashing.

## Immutability vs annotations -- the rule to remember

- `artifacts/` and the sha256/root_hash fields in `meta.json`: **frozen, never
  modified** after sealing.
- `annotations.json`: **mutable** -- the only metadata layer researchers can
  enrich (classification tags, notes, retention policy).
- Deleting a run (`DELETE`) archives the local working copy -- it has no effect on
  the committed audit-plane event store.

## Related

- `docs/plans/2026-06-25-runs-explorer-design.md` -- reference design.
- `docs/plans/2026-06-25-runs-explorer.md` -- implementation plan (Tasks 1-13).
- `.claude/rules/agentic-traceability.md` (R25) -- `docs/tracking/` is gitignored
  work-memory, never committed.
- `.claude/rules/recette-and-test-constraints.md` (R20) -- recette gates.
- `docs/runbooks/platform.md` -- launching services via `./recette.sh`.
