# Runs Explorer Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. This plan is executed by the `apex` skill (all-in autonomous cycle).

**Goal:** Store every run (agent, campaign, mega-campaign, discovery, recette-full) in an eurodated, 3-level-grouped registry under `docs/tracking/runs/`, browsable from a console treeview + Monaco viewer, with full CRUD on the run/annotation layer and one-click replay for replayable surfaces.

**Architecture:** A pure Python registry module (`recette/runs/registry.py`) is the single writer of the eurodated dir tree; a FastAPI router (`recette/api/routers/runs_registry.py`, prefix `/results`) serves it as RAW JSON (this API has NO `{success,data}` envelope); a new console page (`console/src/pages/runs/`) renders an in-house treeview + the existing Monaco dep; replay re-uses govscore/ReplayLlm/mock-lab. Frozen artifacts + sha256 chain (reused from `scripts/export_anssi_bundle.py`) keep raw traces immutable (I1); only `annotations.json` mutates; delete purges work-memory (R25), never the audit store.

**Tech Stack:** Python stdlib + jsonschema (R20), FastAPI `[api]` extra, React/TS, `@monaco-editor/react` (already a dep), vitest, unittest.

**Hard facts verified in repo (do not re-derive):**
- API is RAW JSON, no envelope (`console/src/api/client.ts:6`). Do NOT add `.data` unwrap.
- `/runs` prefix is TAKEN by `recette/api/routers/runs.py` (launch/stop). New router uses `/results`.
- Router wiring: import in `recette/api/app.py` (~line 50 block) + `app.include_router(...)` (~line 373 block), kept alphabetical (a stray order broke `make gates` before -- ruff isort).
- Console route in `console/src/App.tsx:134+` (`<Route>`), nav `<NavLink>` block at `App.tsx:74+`.
- Help topics: `console/src/components/help/helpTopics.tsx` (array of `{title, ...}` topics).
- sha256 + chained root hash pattern: `scripts/export_anssi_bundle.py:48` (`_sha256`) and `:71` (`_chain`).
- API tests skip without `[api]` extra (guard `_HAS_FASTAPI`, see `tests/test_api_behavior.py`).
- Eurodate = OPERATIONAL metadata (wall clock), allowed like `runs.py created_at` (maf-standard rule); MUST be passed in as a parameter to keep the registry's pure ops testable (I4) -- the registry never calls the clock itself.

---

## Task 1: Registry core -- dir model + create/seal

**Files:**
- Create: `recette/runs/__init__.py`
- Create: `recette/runs/registry.py`
- Test: `tests/test_runs_registry.py`

**Step 1: Write the failing test**

```python
# tests/test_runs_registry.py
from __future__ import annotations
import json, tempfile, unittest
from pathlib import Path
from recette.runs.registry import RunRegistry

class TestRegistryCreateSeal(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.reg = RunRegistry(self.root)
    def tearDown(self):
        self._tmp.cleanup()

    def test_new_group_then_run_then_seal_is_hash_stable(self):
        # eurodate is injected (I4: registry never reads the clock)
        g = self.reg.new_group(category="skynet", group_id="megacamp", eurodate="2026-06-25T14-30-00", label="SKYNET mega")
        r = self.reg.new_run(group=g, run_id="agent-1", kind="agent", eurodate="2026-06-25T14-30-01")
        self.reg.write_artifact(r, "agents.jsonl", '{"agent_id":"a","ok":true}\n')
        meta = self.reg.seal(r)
        # sealed -> status + per-file sha256 + chained root_hash
        self.assertEqual(meta["status"], "sealed")
        self.assertIn("agents.jsonl", {a["file"] for a in meta["artifacts"]})
        self.assertEqual(len(meta["root_hash"]), 64)
        # byte-stable: same input -> same root_hash on a fresh registry
        reg2 = RunRegistry(Path(self._tmp.name) / "b")
        g2 = reg2.new_group(category="skynet", group_id="megacamp", eurodate="2026-06-25T14-30-00", label="SKYNET mega")
        r2 = reg2.new_run(group=g2, run_id="agent-1", kind="agent", eurodate="2026-06-25T14-30-01")
        reg2.write_artifact(r2, "agents.jsonl", '{"agent_id":"a","ok":true}\n')
        self.assertEqual(reg2.seal(r2)["root_hash"], meta["root_hash"])
```

**Step 2: Run to verify it fails**

Run: `python3 -m unittest tests.test_runs_registry -v`
Expected: FAIL `ModuleNotFoundError: No module named 'recette.runs'`

**Step 3: Implement minimal `recette/runs/registry.py`**

Implement `RunRegistry(root: Path)` with:
- `new_group(category, group_id, eurodate, label) -> GroupRef` -> mkdir `root/<category>/<eurodate>_<group_id>/`, write `_group.json` `{category, group_id, eurodate, label, status:"open", runs:[]}`.
- `new_run(group, run_id, kind, eurodate, replay_of=None) -> RunRef` -> mkdir `<group>/<run_id>/artifacts/`, write `meta.json` `{id, kind, eurodate, parent_group, status:"running", replay_of}` + empty `annotations.json` `{tags:[], comment:"", label:"", retention:"keep"}`; append run_id to `_group.json.runs`.
- `write_artifact(run, name, content)` -> write `<run>/artifacts/<name>` (reject names with `/` or `..`).
- `seal(run) -> meta` -> compute `_sha256` per artifact, fold `_chain` into `root_hash`, set `status:"sealed"`, persist meta. COPY `_sha256`/`_chain` logic from `scripts/export_anssi_bundle.py:48,71` (DRY -- import them if cleanly importable, else replicate the 6 lines).

No clock calls anywhere (eurodate is a param).

**Step 4: Run to verify it passes**

Run: `python3 -m unittest tests.test_runs_registry -v`  ->  Expected: PASS

**Step 5: Commit**

```bash
git add recette/runs/__init__.py recette/runs/registry.py tests/test_runs_registry.py
git commit -m "feat(runs): eurodated run registry core -- new_group/new_run/seal with sha256 chain"
```

---

## Task 2: Registry read/index + tree

**Files:**
- Modify: `recette/runs/registry.py`
- Test: `tests/test_runs_registry.py` (add cases)

**Step 1: Failing tests** -- `test_tree_groups_by_category`, `test_read_run_returns_meta_annotations_artifacts`, `test_read_artifact_rejects_path_escape`.

```python
    def test_tree_groups_by_category(self):
        g = self.reg.new_group(category="campaigns", group_id="b1", eurodate="2026-06-25T10-00-00", label="batch")
        self.reg.seal(self.reg.new_run(group=g, run_id="r1", kind="campaign", eurodate="2026-06-25T10-00-01"))
        tree = self.reg.tree()
        self.assertIn("campaigns", {n["category"] for n in tree["categories"]})

    def test_read_artifact_rejects_path_escape(self):
        g = self.reg.new_group(category="agents", group_id="g", eurodate="2026-06-25T10-00-00", label="x")
        r = self.reg.new_run(group=g, run_id="r", kind="agent", eurodate="2026-06-25T10-00-01")
        with self.assertRaises(ValueError):
            self.reg.read_artifact(r, "../../../etc/passwd")
```

**Step 2-4:** implement `tree() -> {categories:[{category, groups:[{group_id, eurodate, label, runs:[{id,kind,eurodate,status}]}]}]}` (walk dirs, sort by eurodate desc), `read_run(run_id) -> {meta, annotations, artifacts:[names]}`, `read_artifact(run, name) -> str` (realpath-guard against the run's artifacts dir, raise `ValueError` on escape), `find_run(run_id) -> RunRef|None`. Cache nothing; cheap dir walk. Tests PASS.

**Step 5: Commit** `feat(runs): registry tree/read with path-traversal guard`

---

## Task 3: Registry update/delete/replay-spawn

**Files:** Modify `recette/runs/registry.py`; add tests.

**Step 1: Failing tests**
- `test_annotate_mutates_only_annotations` -- `annotate(run_id, tags=[...], comment=..., retention=...)` changes `annotations.json`; assert `meta.json` + `artifacts/*` bytes unchanged (compare sha256 before/after).
- `test_delete_archives_then_purges` -- `delete(run_id)` tars the dir into `root/_archive/<id>.tar.gz` then removes the live dir; `find_run` returns None; archive exists.
- `test_spawn_replay_child_links_parent_and_leaves_parent_intact` -- `spawn_replay(parent_id, eurodate) -> RunRef` creates a new run with `meta.replay_of==parent_id`; parent meta untouched.

**Step 2-4:** implement; the U mutates only `annotations.json`; delete uses `tarfile` + `shutil.rmtree`; replay-spawn creates a sibling run under the parent's group with a `replay_of` link. Tests PASS.

**Step 5: Commit** `feat(runs): registry annotate/delete-archive/replay-spawn (I1-safe CRUD)`

---

## Task 4: API router `/results` (read endpoints)

**Files:**
- Create: `recette/api/routers/runs_registry.py`
- Modify: `recette/api/app.py` (import ~line 50 alpha block; include ~line 373 alpha block)
- Test: `tests/test_api_runs_registry.py`

**Step 1: Failing test** (guard `_HAS_FASTAPI` like `tests/test_api_behavior.py`): build `create_app()`, `TestClient`, point the registry root at a tmp dir seeded with one sealed run (set via `app.state` or an env override the router reads), assert:
- `GET /results/tree` -> 200, json has `categories`.
- `GET /results/{id}` -> 200 meta+annotations+artifacts.
- `GET /results/{id}/artifact/agents.jsonl` -> 200 raw text.
- `GET /results/{id}/artifact/..%2f..%2fetc%2fpasswd` -> 400.

**Step 2: fails** (router missing). **Step 3:** implement `runs_registry.py` (`router = APIRouter(prefix="/results", tags=["results"])`), RAW JSON returns (no envelope). Resolve the registry root from a config helper (default `docs/tracking/runs/`, override env `INSPECT_IA_AGENTS_RUNS_ROOT` -- R5). Map `ValueError`(escape) -> `HTTPException(400)`, missing run -> 404. Wire imports in `app.py` ALPHABETICALLY (ruff isort gate). **Step 4: PASS** via `.venv` python (`[api]` extra). **Step 5: Commit** `feat(api): /results read endpoints (tree/run/artifact) raw JSON`

---

## Task 5: API router `/results` (write endpoints)

**Files:** Modify `recette/api/routers/runs_registry.py`; add tests.

**Step 1: Failing tests** -- `POST /results` (register), `PATCH /results/{id}` (annotations -> 200, only annotations change), `DELETE /results/{id}` (requires `?confirm=true`; without it 400; with it archives+purges -> 200, then `GET` 404), `POST /results/{id}/replay` (-> 201 with child id, `replay_of` set; dispatch stubbed/whitelisted by kind). **Step 2-4:** implement; DELETE confirm-guard; replay dispatch table by kind (govscore recompute / `agent replay` / exchange) -- for kinds without a replayer return 422 `not replayable`. PASS. **Step 5: Commit** `feat(api): /results CRUD + replay-spawn endpoints`

---

## Task 6: Runner migration helper (write into the registry)

**Files:**
- Create: `recette/runs/capture.py` (thin: `capture_surface(category, group_id, eurodate, runs:{run_id:{kind,artifacts:{name:content}}})` -> seals a group of runs via `RunRegistry`)
- Modify: `scripts/recette_full.py` + ONE skynet runner (`scripts/run_agents_live_skynet.py`) to ALSO register a run dir (keep the flat-file write + a `latest/` symlink for back-compat).
- Test: `tests/test_runs_capture.py`

**Step 1: Failing test** -- call `capture_surface(...)` with two runs, assert a sealed group exists with both runs readable via `RunRegistry.tree()`. **Step 2-4:** implement; wire the two runners behind a guard so a missing registry never breaks a live run (fail-safe: capture errors are logged, not fatal). PASS. **Step 5: Commit** `feat(runs): capture helper + migrate recette_full + agents-live runner to the registry`

> NOTE for APEX: migrate ONLY these two runners in this cycle (proves the pattern). The remaining `run_*_skynet.py` migrations go on the backlog -- do not fan out silently (R20 no-silent-cap: log what was deferred in the RETEX).

---

## Task 7: Console API client

**Files:** Modify `console/src/api/client.ts`; Modify `console/src/api/client.test.ts` (if present) or add a small fetch test.

**Step 1:** Add types `RunNode`, `RunDetail`, `RunTree` and functions `fetchRunTree()`, `fetchRun(id)`, `fetchRunArtifact(id,name)`, `patchRunAnnotations(id, body)`, `deleteRun(id)`, `replayRun(id)` -- all RAW JSON (the file's `request<T>` helper, no unwrap). **Step 2-4:** type-check `./recette.sh console-build`. **Step 5: Commit** `feat(console): /results api client (raw JSON)`

---

## Task 8: Console `RunTree` component (in-house, no new dep)

**Files:**
- Create: `console/src/pages/runs/RunTree.tsx`
- Create: `console/src/pages/runs/__fixtures__/runs-tree.fixture.json` (REAL payload: `curl -s "$API/results/tree"` after Task 6 seeds a run; R16)
- Test: `console/src/pages/runs/RunTree.test.tsx`

**Step 1 (R16 PRE-BUILD GATE):** capture the real `/results/tree` payload to the fixture FIRST. **Step 2: failing render-and-assert test** -- render `<RunTree data={fixture} ... />`, assert a category label, a group eurodate, and a run node are in the DOM; clicking a run fires `onSelect(runId)`. **Step 3:** implement a tiny recursive collapsible tree (category > group > run), status badge, kind icon, no external tree lib. **Step 4: PASS** `./recette.sh console-test`. **Step 5: Commit** `feat(console): RunTree recursive treeview + fixture (R16)`

---

## Task 9: Console `RunsExplorer` page (Monaco + tabs + CRUD)

**Files:**
- Create: `console/src/pages/runs/index.tsx`
- Create: `console/src/pages/runs/__fixtures__/run-detail.fixture.json` (real `/results/{id}` payload)
- Test: `console/src/pages/runs/index.test.tsx`

**Step 1 (R16):** capture real `/results/{id}` fixture. **Step 2: failing test** -- mock the client fns (incl. all CRUD/replay returning resolved values; mirror the `correlateBehavior: vi.fn(...)` lesson so no mock is missing), render the page, assert: tree present, selecting a run shows Monaco content + Meta tab (sha256/eurodate), Annotations tab edits + calls `patchRunAnnotations`, Delete calls `deleteRun` after confirm, Replay calls `replayRun`. Cover empty/running/sealed states. **Step 3:** implement: left `<RunTree>`, right Monaco (`@monaco-editor/react`, `readOnly`, language json) + tabs Content/Meta/Annotations/Replay; CRUD controls. Auto-fetch tree on mount; null-guard every fetch (`if (!r) return`). **Step 4: PASS** console-test. **Step 5: Commit** `feat(console): RunsExplorer page -- Monaco viewer + CRUD + replay (R16)`

---

## Task 10: Wire route + nav

**Files:** Modify `console/src/App.tsx` (add `<Route path="/runs" element={<RunsExplorerPage/>}/>` near line 152; add a `<NavLink to="/runs">` in the nav block ~line 86; import the page). 

**Step 1-4:** add lazy import + route + nav link; `console-build` clean; navigate with Playwright, snapshot zero Component Error (APEX react pipeline gate 8). **Step 5: Commit** `feat(console): mount Runs Explorer route + nav link`

---

## Task 11: UI help topic

**Files:** Modify `console/src/components/help/helpTopics.tsx` (add a `title: "Aide — Explorateur de runs"` topic: tree, Monaco, replay, CRUD, eurodate grouping, the immutability rule -- frozen artifacts vs mutable annotations, delete=work-memory purge not audit-store). Wire the page's HelpButton to the new topic key. **Step 5: Commit** `docs(help): Runs Explorer help topic (fr)`

---

## Task 12: Docusaurus runbook fr + en

**Files:**
- Create: `docs/runbooks/runs-explorer.md` (FRENCH source)
- Create: `docs-site/i18n/en/docusaurus-plugin-content-docs/current/runbooks/runs-explorer.md` (EN mirror)

Content: what the Runs Explorer is (web-only researcher surface), the eurodated 3-level layout, how a run is sealed (sha256 chain), CRUD semantics + the I1/R25 reconciliation, replay (which kinds, pure recompute), the `/results` API surface. `./recette.sh docs-build` clean. **Step 5: Commit** `docs(runbook): Runs Explorer fr+en`

---

## Task 13: Gates + coverage + RETEX

**Steps:**
1. `make gates` (ruff/mypy/bandit) green -- watch isort on `app.py`.
2. `./recette.sh test` (registry + capture unittests) green; `.venv` run for the `[api]` suite (Task 4/5 tests).
3. `./recette.sh console-build` + `./recette.sh console-test` green.
4. If a new category/kind needs coverage-guard wiring, extend `tests/test_coverage_guard.py`; else note N/A.
5. Run the recette-full strict gate (`scripts/recette_full.py --quick --json | scripts/recette_score.py --target 90`); REPLAN on any red.
6. Fill the RETEX `docs/tracking/recette/RETEX_runs-explorer_2026-06-25.md` (gitignored): per-task verdict + the deferred-runner-migration backlog item (no-silent-cap).

**Step: Final commit** `test(runs): gates + coverage + RETEX for Runs Explorer`

---

## Definition of done (gate before COMPLETE)

- [ ] Registry: create/seal/tree/read/annotate/delete/replay-spawn, sha256 chain byte-stable (I4).
- [ ] `/results` API: read + CRUD + replay, raw JSON, path-traversal guarded, DELETE confirm-guarded.
- [ ] Console: RunTree + RunsExplorer (Monaco), route + nav, R16 fixtures + render-and-assert, zero Component Error.
- [ ] Two runners migrated to the registry; deferred ones logged in RETEX.
- [ ] Docs fr+en + UI help topic (P1-done rule).
- [ ] `make gates` + unittest + console-build + console-test green; recette-full strict gate PASS.
- [ ] No new npm/py hard dep (Monaco already present; jsonschema only).
