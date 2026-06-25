# Runs Explorer -- web-only researcher surface for runs, logs, results

Date: 2026-06-25
Status: APPROVED (design) -- next: writing-plans -> all-in APEX cycle

## Problem

The recette produces logs and result surfaces (agent action-logs, proxy traces,
eBPF captures, campaign results, scorecards, SKYNET mega-campaign launches). Today
they are written as FLAT files in `docs/tracking/recette/` and OVERWRITTEN on each
run (the `.PRE.bak` clobber problem). Two failures:

1. No history -- a new run destroys the previous one (no eurodate, no grouping).
2. A researcher with web access ONLY cannot reach a flat file on disk and cannot
   manually parse mega-campaign output. The result has to be browsable, readable,
   and replayable from a modern web surface (tree + Monaco), not from a terminal.

Legibility-first (CLAUDE.md): a surface that cannot be observed by a third party
who did not run it is not recettable. The Runs Explorer is that observable surface.

## Goal

One sentence: every run (agent, campaign, mega-campaign, discovery, recette-full)
is stored in an eurodated, hierarchically grouped registry, browsable via a console
treeview + Monaco viewer, with full CRUD on the run/annotation layer and one-click
replay for the replayable surfaces.

## Constraints (non-negotiable)

- **I1 immutability** -- the committed audit-plane event store stays append-only.
  CRUD never mutates a committed event stream.
- **R25** -- `docs/tracking/` is gitignored work-memory; run dirs live there, never
  committed, and are operator-deletable (they are NOT the audit-plane store).
- **I4 determinism** -- the eurodate is OPERATIONAL metadata (wall clock), allowed
  like `recette/api/runs.py::created_at` (maf-standard rule), and never enters a
  decision/judge/replay path. Replay itself is pure (govscore recompute, ReplayLlm,
  deterministic mock lab).
- **R20** -- stdlib unittest, zero new hard dep; jsonschema only.
- **R16** -- every new React component that calls the API ships a real fixture +
  render-and-assert + envelope unwrap, covering every state.
- **R19** -- services only via `./recette.sh`; canonical ports.
- **P1-done rule** -- the panel ships with Docusaurus fr+en runbook AND a UI help
  topic section, not just code+tests.

## Storage layout (eurodated, 3-level grouping)

`docs/tracking/runs/` (gitignored):

```
docs/tracking/runs/
  <category>/                            level 1: kind = skynet | campaigns | agents | discovery | recette-full
    <YYYY-MM-DDTHH-MM-SS>_<group-id>/    level 2: group = one launch/batch (a mega-campaign = one group)
      _group.json                        group meta: eurodate, kind, label, child run ids, status, sha256 roll-up
      <subrun-id>/                       level 3: individual run
        meta.json                        id, kind, eurodate, status (running|sealed), llm, parent_group,
                                         artifact list + per-file sha256 + chained root_hash, replay_of (optional)
        annotations.json                 MUTABLE layer: tags[], comment, label, retention (keep|purge-after)
        artifacts/                       FROZEN surfaces once sealed
          *.jsonl | *.json               agents/traced/proxy/ebpf/scorecard/campaigns/...
        replay.json                      replay descriptor (kind, command, input hashes) if replayable
  index.json                             top index (category>group>run tree) the API reads without walking disk
  latest/<category> -> ...               symlink to the most recent group per category (back-compat)
```

- **Frozen vs mutable**: `artifacts/*` + `meta.sha256/root_hash` are sealed and
  never edited (same hash-chain idea as `export_anssi_bundle.py`). `annotations.json`
  is the only mutable file -- the U in CRUD.
- A run is SEALED when its producing runner finishes: write `meta.status=sealed` +
  the per-file sha256 + a chained `root_hash`. Tamper-evident, replayable.

## API -- `recette/api/routers/runs_registry.py`

Response envelope `{success, data}` (R16). Endpoints:

| Verb + path | Role |
|-------------|------|
| `GET /runs/tree?category=&group=` | category>group>run tree from `index.json` |
| `GET /runs/{id}` | run meta + annotations + artifact list |
| `GET /runs/{id}/artifact/{name}` | raw artifact bytes (-> Monaco), guarded to the run dir |
| `POST /runs` | register a run/group (used by runners; create) |
| `PATCH /runs/{id}` | update `annotations.json` (tag/comment/label/retention) |
| `DELETE /runs/{id}` | archive (tar to `docs/tracking/runs/_archive/`) then purge dir; emits audit event; confirm-guarded |
| `POST /runs/{id}/replay` | replay -> spawns a NEW eurodated run with `meta.replay_of=<id>` |

Replay dispatch by run kind: scorecard/govscore -> `recette_govscore.py` pure
recompute; agent action-log -> `recette agent replay <recording>` (ReplayLlm, no
key); exchange -> deterministic mock-lab re-drive diffed against `proxy_traces`.
A replay NEVER mutates the parent; it writes a child run.

Path-traversal guard: artifact name resolved against the run dir realpath; reject
anything escaping it.

## UI -- console page `console/src/pages/runs/`

"Results Explorer", added to the nav:

- **Left pane**: treeview category > group > run. Tiny in-house recursive component
  (`RunTree.tsx`) -- NO new dep (react-arborist avoided, YAGNI). Eurodate + status
  badge per node, kind icon, group roll-up count.
- **Right pane**: Monaco (`@monaco-editor/react`, already a dep) read-only, json/
  jsonl language, large-file safe (lazy fetch on select). Tabs:
  - Content (Monaco on the selected artifact)
  - Meta (id, eurodate, llm, sha256/root_hash, parent_group, replay_of)
  - Annotations (tags/comment/label/retention -- editable -> PATCH)
  - Replay (button + descriptor; result links to the spawned child run)
- CRUD controls: rename·tag·retention (PATCH), delete (DELETE, confirm dialog),
  replay (POST). Service unwraps `{success,data}` (R16).
- Auto-refresh tree on mount; null guards on every fetch result.

## Migration

Wrap the existing runners so each writes into a run dir instead of overwriting a
flat file:
- `scripts/run_*_skynet.py` (the surface runners) + `scripts/recette_full.py` +
  `scripts/export_anssi_bundle.py` register a group + per-surface runs.
- A shared helper `recette/runs/registry.py` (pure registry ops: new_group,
  new_run, seal, index, list, read, annotate, archive_purge) is the single writer;
  runners call it. Keeping the flat-file `latest/` symlink preserves back-compat for
  the current scripts that read `docs/tracking/recette/*.jsonl`.

## Tests (definition of done)

- `tests/test_runs_registry.py` -- create group/run, seal (sha256/root_hash byte-
  stable for fixed input = I4), list/tree, read artifact, annotate (PATCH mutates
  only annotations.json), delete (archive+purge), replay spawns a child with
  `replay_of` and never touches the parent.
- `tests/test_api_runs_registry.py` -- endpoint contract, envelope, path-traversal
  guard rejects escape, DELETE confirm guard.
- Console: `__fixtures__/runs-tree.fixture.json` + `__fixtures__/run-detail.fixture.json`,
  `RunTree.test.tsx` + `RunsExplorer.test.tsx` render-and-assert (R16), every run
  status + annotation state covered.
- Coverage guard extended if a new category/kind must be wired.

## Docs (definition of done)

- `docs/runbooks/runs-explorer.md` (FRENCH source) + EN mirror under
  `docs-site/i18n/en/.../runbooks/runs-explorer.md`.
- UI help topic section under `console/src/components/help/helpTopics.tsx` (the runs
  topic: tree, Monaco, replay, CRUD, eurodate grouping, immutability rule).

## Out of scope (YAGNI)

- No new tree/grid npm dependency.
- No editing of frozen artifacts (I1).
- No real-time streaming of a running run (poll/refresh is enough for v1).
- No multi-user auth model beyond what the console already has.

## Approach chosen

All-in one APEX cycle (operator decision): storage helper + API router + console
page + replay wiring + CRUD + migration of runners + docs fr/en + help, gated by
the build pipelines (python + react) and the recette gates before COMPLETE.
