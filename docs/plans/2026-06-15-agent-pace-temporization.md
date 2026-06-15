# Agent Action Pacing (Temporization) Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a configurable per-agent / per-server delay between a Lane B agent's actions, editable from the cockpit, that slows real execution and the cockpit stream without touching the judged event stream (I4).

**Architecture:** A pacing delay is operational metadata, never a decision input. The sleep lives ONLY in the ops layer (`recette/api/runners.py`) inside a wrapper around the existing `on_step` callback; `recette/lane_b.py` stays pure (no `time` import). Resolution is `agent.pace_ms ?? server.pace_ms ?? 0`, clamped to a max. The live runners (dashboard + campaign) get paced; the REPLAY runner stays bare so deterministic verification never sleeps. Spacing the server-side `emit("step")` calls spaces the SSE frames, so the cockpit is paced with no client buffering.

**Tech Stack:** Python 3 (stdlib `unittest`, `time.sleep`), FastAPI config router (already present), React/TS console (vitest), `jsonschema` validation.

**Reference docs:**
- Design: `docs/plans/2026-06-15-agent-pace-temporization-design.md`
- Constraints: `.claude/rules/recette-and-test-constraints.md` (R20), `.claude/rules/determinism-replay.md` (I4), `.claude/rules/maf-standard.md` (ops metadata vs decision data), `.claude/rules/frontend-contract-gate.md` (R16), `.claude/rules/recette-sh-single-entrypoint.md` (R19).

**Ground-truth facts (verified):**
- `run_lane_b_agent` is called in 3 places in `recette/api/runners.py`: `make_lane_b_runner` (~line 308, dashboard single agent), `make_campaign_runner` (~line 436, gateway loop), `make_replay_runner` (~line 474, REPLAY — must NOT pace).
- The `on_step` hook signature is `on_step(i: int, step) -> None`, called after each recorded action.
- Runners run in a worker thread (`recette/api/runs.py::_execute`), so `time.sleep` there does NOT block the async API loop.
- Server entry shape: `{id, system, mode, port}` in `config/inspect_ia_agents.config.json` under `servers`. Agent entries under `agents`. `config_store.list_servers()` returns the list; `ConfigStore.update_agent`/`update_server` apply a patch.
- Config router: `PUT /config/agents/{agent_id}` and server routes already accept a patch dict — adding `pace_ms` needs no new endpoint.
- Test runner is stdlib `unittest` (`python3 -m unittest discover -s tests`), NOT pytest. Only hard dep is `jsonschema`.

**Constants:** `MAX_PACE_MS = 30000`, `PACE_SLICE_MS = 100` — define ONCE in `recette/api/runners.py` (R5, no scattered literals).

---

## Task 1: Pure pace-resolution helper

**Files:**
- Modify: `recette/api/runners.py` (add `resolve_pace` + constants near the top, after imports)
- Test: `tests/test_pace.py` (create)

**Step 1: Write the failing test**

Create `tests/test_pace.py`:

```python
"""Pace resolution + slicing are pure ops helpers (I4: never on the judged path)."""

import unittest

from recette.api.runners import MAX_PACE_MS, resolve_pace


class ResolvePaceTest(unittest.TestCase):
    def _server(self, sid, pace=None):
        s = {"id": sid, "system": "github", "mode": "mock_local", "port": 9101}
        if pace is not None:
            s["pace_ms"] = pace
        return s

    def test_agent_overrides_server(self):
        agent = {"server": "gh", "pace_ms": 2000}
        servers = [self._server("gh", 500)]
        self.assertEqual(resolve_pace(agent, servers), 2000)

    def test_inherits_server_when_agent_unset(self):
        agent = {"server": "gh"}
        servers = [self._server("gh", 500)]
        self.assertEqual(resolve_pace(agent, servers), 500)

    def test_defaults_zero_when_neither_set(self):
        agent = {"server": "gh"}
        servers = [self._server("gh")]
        self.assertEqual(resolve_pace(agent, servers), 0)

    def test_defaults_zero_when_server_missing(self):
        agent = {"server": "ghost"}
        self.assertEqual(resolve_pace(agent, []), 0)

    def test_clamped_to_max(self):
        agent = {"server": "gh", "pace_ms": 10**9}
        self.assertEqual(resolve_pace(agent, [self._server("gh")]), MAX_PACE_MS)

    def test_negative_clamped_to_zero(self):
        agent = {"server": "gh", "pace_ms": -5}
        self.assertEqual(resolve_pace(agent, [self._server("gh")]), 0)

    def test_non_int_falls_back_to_zero(self):
        agent = {"server": "gh", "pace_ms": "fast"}
        self.assertEqual(resolve_pace(agent, [self._server("gh")]), 0)


if __name__ == "__main__":
    unittest.main()
```

**Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_pace -v`
Expected: FAIL with `ImportError: cannot import name 'resolve_pace'`.

**Step 3: Write minimal implementation**

In `recette/api/runners.py`, after the imports block (after the last `from ..` import, before the first class/function), add:

```python
# Pacing is operational metadata, never a decision input (I4 / R20): the delay
# lives here in the ops layer, never inside lane_b's pure execution loop.
MAX_PACE_MS = 30000
PACE_SLICE_MS = 100


def resolve_pace(agent_cfg: dict, servers: list[dict]) -> int:
    """Resolve the inter-action delay for an agent: agent ?? server ?? 0.

    Clamped to [0, MAX_PACE_MS]. Any malformed value falls back to 0 (fail-safe
    to instant -- a bad pace never crashes or freezes a run).
    """

    def _coerce(value: object) -> int | None:
        if isinstance(value, bool) or not isinstance(value, int):
            return None
        return value

    pace = _coerce(agent_cfg.get("pace_ms"))
    if pace is None:
        server_id = agent_cfg.get("server")
        server = next((s for s in servers if s.get("id") == server_id), None)
        pace = _coerce(server.get("pace_ms")) if server is not None else None
    if pace is None:
        return 0
    return max(0, min(pace, MAX_PACE_MS))
```

**Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_pace -v`
Expected: PASS (7 tests).

**Step 5: Commit**

```bash
git add recette/api/runners.py tests/test_pace.py
git commit -m "feat(pace): pure resolve_pace helper (agent ?? server ?? 0, clamped)"
```

---

## Task 2: Sliced sleep that respects should_stop

**Files:**
- Modify: `recette/api/runners.py` (add `_paced_on_step`)
- Test: `tests/test_pace.py` (extend)

**Step 1: Write the failing test**

Append to `tests/test_pace.py`:

```python
class PacedOnStepTest(unittest.TestCase):
    def test_calls_inner_then_sleeps_total_pace(self):
        slept = []
        calls = []
        from recette.api import runners

        original = runners.time.sleep
        runners.time.sleep = lambda s: slept.append(s)
        try:
            wrapped = runners._paced_on_step(
                lambda i, step: calls.append(i), pace_ms=250, should_stop=lambda: False
            )
            wrapped(0, object())
        finally:
            runners.time.sleep = original

        self.assertEqual(calls, [0])           # inner ran first
        self.assertAlmostEqual(sum(slept), 0.25, places=3)  # total slept == pace

    def test_stop_breaks_sleep_early(self):
        slept = []
        from recette.api import runners

        original = runners.time.sleep
        runners.time.sleep = lambda s: slept.append(s)
        try:
            wrapped = runners._paced_on_step(
                lambda i, step: None, pace_ms=5000, should_stop=lambda: True
            )
            wrapped(0, object())
        finally:
            runners.time.sleep = original

        self.assertLessEqual(sum(slept), 0.1)  # bailed within one slice

    def test_zero_pace_never_sleeps(self):
        from recette.api import runners

        original = runners.time.sleep

        def boom(_):
            raise AssertionError("should not sleep at pace 0")

        runners.time.sleep = boom
        try:
            wrapped = runners._paced_on_step(lambda i, step: None, pace_ms=0, should_stop=lambda: False)
            wrapped(0, object())  # must not raise
        finally:
            runners.time.sleep = original
```

**Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_pace -v`
Expected: FAIL — `_paced_on_step` and/or `runners.time` not found.

**Step 3: Write minimal implementation**

Add `import time` to the top imports of `recette/api/runners.py` (alphabetical, in the stdlib group — there is currently only `from __future__` and `from collections.abc`; add a plain `import time` after `from __future__ import annotations` and a blank line, before the `from collections.abc` line so stdlib stays grouped).

Then add, near `resolve_pace`:

```python
def _paced_on_step(inner, pace_ms: int, should_stop):
    """Wrap an on_step callback so it sleeps ``pace_ms`` AFTER emitting, in
    PACE_SLICE_MS ticks, bailing as soon as should_stop() is true. At pace 0 it
    is a transparent pass-through (never sleeps)."""
    if pace_ms <= 0:
        return inner

    def wrapped(i: int, step) -> None:
        inner(i, step)
        remaining = pace_ms
        while remaining > 0:
            if should_stop():
                return
            tick = min(PACE_SLICE_MS, remaining)
            time.sleep(tick / 1000)
            remaining -= tick

    return wrapped
```

**Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_pace -v`
Expected: PASS (10 tests).

**Step 5: Commit**

```bash
git add recette/api/runners.py tests/test_pace.py
git commit -m "feat(pace): sliced sleep wrapper that respects should_stop"
```

---

## Task 3: Wire pacing into the dashboard runner

**Files:**
- Modify: `recette/api/runners.py` (`make_lane_b_runner` runner body, ~line 298-321)
- Test: `tests/test_runners.py` (extend — it already imports the lane_b runner)

**Step 1: Write the failing test**

First read `tests/test_runners.py` to match its existing style/fixtures. Add a test asserting that when the agent has `pace_ms`, the runner wraps on_step (observable: `time.sleep` is called once per step). Pattern:

```python
def test_lane_b_runner_paces_when_pace_set(self):
    # build a config_store stub with one server carrying pace_ms, an agent_cfg
    # referencing it, and a StubLlm producing 1 action; monkeypatch
    # recette.api.runners.time.sleep to record calls; run the runner with a
    # no-op emit + should_stop=lambda: False; assert sleep was called.
```

Use the existing helpers in `tests/test_runners.py` for the StubLlm + emit collector. Keep it deterministic (StubLlm, no real key).

**Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_runners -v`
Expected: FAIL — sleep not called (pacing not wired yet).

**Step 3: Write minimal implementation**

In `make_lane_b_runner`'s `runner` body, the `servers` list is already fetched. Replace the `on_step=lambda ...` argument so it is wrapped:

```python
        pace_ms = resolve_pace(agent_cfg, servers)
        base_on_step = lambda i, step: emit("step", {"index": i, **step.to_dict()})
        result = run_lane_b_agent(
            ...
            on_step=_paced_on_step(base_on_step, pace_ms, should_stop),
            should_stop=should_stop,
        )
```

(Keep the existing F2 comment above `base_on_step`.)

**Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_runners -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add recette/api/runners.py tests/test_runners.py
git commit -m "feat(pace): dashboard lane_b runner honours resolved pace"
```

---

## Task 4: Wire pacing into the campaign (gateway) runner

**Files:**
- Modify: `recette/api/runners.py` (`make_campaign_runner` loop, ~line 436-448)
- Test: `tests/test_runners.py` (extend)

**Step 1: Write the failing test**

Add a test mirroring Task 3 but for the campaign runner: a campaign with one agent whose server carries `pace_ms`; assert `time.sleep` is called during the run. Reuse campaign fixtures already in `tests/test_runners.py` if present; otherwise build a minimal campaign dict.

**Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_runners -v`
Expected: FAIL — campaign path not paced.

**Step 3: Write minimal implementation**

Inside the campaign loop (where `servers`/`forge` are resolved per agent), compute `pace_ms = resolve_pace(agent_cfg, servers)` and wrap the existing emitter:

```python
            on_step=_paced_on_step(_lane_b_step_emit(emit, agent_id), resolve_pace(agent_cfg, servers), should_stop),
```

Confirm `servers` is in scope at that point; if the campaign loop fetches servers under a different name, use that. Do NOT touch `make_replay_runner`.

**Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_runners -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add recette/api/runners.py tests/test_runners.py
git commit -m "feat(pace): campaign runner honours per-agent resolved pace"
```

---

## Task 5: I4 byte-identical replay guard + lane_b purity guard

**Files:**
- Test: `tests/test_pace_determinism.py` (create)

**Step 1: Write the failing test**

Create `tests/test_pace_determinism.py`:

```python
"""Pace must not change the judged output (I4) and must stay out of lane_b."""

import pathlib
import unittest

from recette.api import runners


class PaceDeterminismTest(unittest.TestCase):
    def test_lane_b_module_has_no_time_import(self):
        src = pathlib.Path("recette/lane_b.py").read_text()
        self.assertNotIn("import time", src)
        self.assertNotIn("time.sleep", src)

    def test_action_log_byte_identical_regardless_of_pace(self):
        # Run the SAME StubLlm-driven agent twice through the dashboard runner:
        # once with pace 0, once with pace 500 (time.sleep monkeypatched to
        # no-op). Collect the "result" frame's actions + recording for both.
        # Assert the two JSON payloads are byte-identical.
        original = runners.time.sleep
        runners.time.sleep = lambda s: None
        try:
            payload_fast = _run_collect_result(pace_ms=0)
            payload_slow = _run_collect_result(pace_ms=500)
        finally:
            runners.time.sleep = original
        self.assertEqual(payload_fast, payload_slow)


# _run_collect_result: build the dashboard runner with a StubLlm agent (reuse
# the helper/fixtures from tests/test_runners.py), capture the "result" emit
# frame, json.dumps(sort_keys=True) it. Factor the helper so both tests share it.
```

Implement `_run_collect_result` using the same StubLlm/emit pattern as `tests/test_runners.py` (import or duplicate the minimal builder). Keep it deterministic.

**Step 2: Run test to verify it fails (or passes purity, fails equality if a bug)**

Run: `python3 -m unittest tests.test_pace_determinism -v`
Expected: the purity test PASSES immediately (lane_b untouched). The equality test PASSES once Tasks 3 wiring is correct — if it FAILS, pacing leaked into the judged path: fix before continuing.

**Step 3: (no impl unless equality fails)**

If equality fails, the regression is that `_paced_on_step` mutated the step or the action order — review Task 2/3. The wrapper must call `inner` unchanged and only sleep after.

**Step 4: Run full suite**

Run: `python3 -m unittest discover -s tests`
Expected: all green.

**Step 5: Commit**

```bash
git add tests/test_pace_determinism.py
git commit -m "test(pace): I4 byte-identical judged output + lane_b purity guard"
```

---

## Task 6: Agent + server schema field

**Files:**
- Modify: the agent schema validating `config/inspect_ia_agents.config.json` entries (locate with `grep -rln '"capability_scope"' config/ corpus/schemas/` — likely `corpus/schemas/agent-manifest.schema.json` or a config-specific schema; confirm which schema `ConfigStore` validates against by reading `recette/api/config_store.py` around `update_agent`/`update_server`).
- Test: `tests/test_config_store.py` if present, else `tests/test_pace.py`

**Step 1: Write the failing test**

Add a test that `ConfigStore.update_agent(id, {"pace_ms": 800})` succeeds and persists, and `update_agent(id, {"pace_ms": -1})` is rejected if the store validates (if it does not validate ranges, rely on `resolve_pace` clamping and assert persistence only). Mirror for `update_server`.

**Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_config_store -v` (or the file you added to)
Expected: FAIL if the schema rejects the unknown `pace_ms` property (when `additionalProperties: false`).

**Step 3: Write minimal implementation**

Add to the agent properties and the server properties in the relevant schema:

```json
"pace_ms": { "type": "integer", "minimum": 0 }
```

If the schema sets `"additionalProperties": false`, this is REQUIRED for persistence to work. If `additionalProperties` is not false, the field still flows through but add it for documentation + validation.

**Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_config_store -v`
Expected: PASS.

**Step 5: Commit**

```bash
git add corpus/schemas/ tests/
git commit -m "feat(pace): pace_ms optional field on agent + server schema"
```

---

## Task 7: Coverage guard + full Python gates

**Files:**
- Possibly modify: `tests/test_coverage_guard.py` (only if it asserts an exhaustive agent/server field set that now needs `pace_ms` acknowledged)

**Step 1: Run the recette + coverage guard**

Run: `make recette`
Expected: green. If `test_coverage_guard.py` turns RED because it enumerates known config fields, update the explicit constant there (never silence by hand — see the no-silent-recette-gaps lesson).

**Step 2: Run the full gates**

Run: `make gates && python3 -m unittest discover -s tests`
Expected: ruff/mypy/bandit clean, all tests pass.

**Step 3: Commit (only if a guard constant changed)**

```bash
git add tests/test_coverage_guard.py
git commit -m "test(pace): acknowledge pace_ms in coverage guard"
```

---

## Task 8: Cockpit "Cadence (ms)" field — agent editor (R16)

**Files:**
- Modify: `console/src/pages/agents/index.tsx` (`AgentFormValues` ~line 75, form mapping ~line 180 and ~line 202, the form UI, and the table ~line 531)
- Modify: the agent service type (find with `grep -rn "capability_scope" console/src/services`)
- Fixture: `console/src/pages/agents/__fixtures__/agent-with-pace.fixture.json` (create — a REAL `GET /config/agents` payload captured from the running API, including `pace_ms`)
- Test: `console/src/pages/agents/index.test.tsx` or a co-located render test

**Step 1: Capture the real fixture (R16 — no invented payload)**

Start services via the single entry point (R19) and curl the real endpoint:

```bash
./recette.sh platform up
curl -s http://127.0.0.1:8090/config/agents > console/src/pages/agents/__fixtures__/agent-with-pace.fixture.json
```

Set `pace_ms` on one agent first (via the API or by editing config then reloading) so the fixture actually contains the field. Do NOT hand-write the payload.

**Step 2: Write the failing render-and-assert test**

Add a test that renders the agent editor with the fixture and asserts the "Cadence (ms)" input shows the agent's `pace_ms`, and that submitting a changed value calls the update service with `{ pace_ms: <n> }`. Run: `./recette.sh console-test` — expected FAIL (field not rendered).

**Step 3: Implement the field**

- Add `pace_ms?: number` to `AgentFormValues` and the agent service interface.
- Map it in the form load (`actions: agent.capability_scope ?? []` block, ~line 202): `pace_ms: agent.pace_ms`.
- Map it on save (~line 180): include `pace_ms: values.pace_ms` (omit/undefined = inherit).
- Add a numeric input labelled "Cadence (ms)" with placeholder "hérite du serveur / instant".
- Show it in the table row (~line 531).
- Ensure the service unwraps `{ success, data }` (R16) — reuse the existing unwrap.

**Step 4: Run console test**

Run: `./recette.sh console-test`
Expected: PASS.

**Step 5: Commit**

```bash
git add console/src/pages/agents/
git commit -m "feat(pace): cockpit agent editor Cadence (ms) field (R16 fixture+render)"
```

---

## Task 9: Cockpit "Cadence (ms)" field — server editor (R16)

**Files:**
- Modify: the server editor component (find with `grep -rln "add_server\|/config/servers\|interface Server" console/src`)
- Fixture: `console/src/.../__fixtures__/server-with-pace.fixture.json` (real `GET /config/servers` payload)
- Test: co-located render test

**Step 1–5:** Mirror Task 8 for the server editor: capture real `GET /config/servers` fixture (with `pace_ms` set on one server), write the failing render test, add a numeric "Cadence (ms)" field saving `{ pace_ms }` via the server update route, unwrap the envelope, run `./recette.sh console-test`, commit.

```bash
git commit -m "feat(pace): cockpit server editor Cadence (ms) field (R16 fixture+render)"
```

---

## Task 10: Cockpit active-pace badge (legibility-first)

**Files:**
- Modify: cockpit/live view (`console/src/pages/cockpit/index.tsx` or `console/src/pages/live/index.tsx` — confirm which renders the running-agent header)
- Test: co-located render test

**Step 1: Write the failing test**

Render the cockpit with a run whose agent has `pace_ms > 0` in the fixture; assert a badge like "pace 800ms" is shown. Run `./recette.sh console-test` — expected FAIL.

**Step 2–4: Implement**

Show a small badge next to the agent when its resolved `pace_ms > 0`. Hide it when 0/undefined. Run `./recette.sh console-test` — PASS.

**Step 5: Commit**

```bash
git add console/src/pages/
git commit -m "feat(pace): cockpit shows active pace badge (legibility-first)"
```

---

## Task 11: Console build + live smoke proof (R14/R20)

**Files:**
- Possibly modify: `scripts/smoke_console.py` (add a deterministic assertion that a paced agent's steps arrive spaced, using a StubLlm backend — no real key)

**Step 1: Console build**

Run: `./recette.sh console-build`
Expected: tsc + vite clean.

**Step 2: Live smoke**

Run: `./recette.sh smoke`
Expected: green. If adding a pacing assertion, make it deterministic (mock/StubLlm backend) and put it in the VERSIONED smoke, never `/tmp` (R20). A small pace (e.g. 200ms) keeps the smoke fast while proving the SSE frames are spaced.

**Step 3: Commit (if smoke changed)**

```bash
git add scripts/smoke_console.py
git commit -m "test(pace): smoke proves paced steps arrive spaced over SSE"
```

---

## Task 12: Final gate sweep + push

**Step 1: Run every gate**

Run in order (R20 gate table):

```bash
make gates
./recette.sh test
make recette
./recette.sh console-test
./recette.sh console-build
```

Expected: all green.

**Step 2: Push to main**

Per the work-on-main rule (no branches), `git status` first; if clean and all yours:

```bash
git status
git push origin main
```

**Done when:** every gate is green, the cockpit lets an operator set Cadence (ms) on an agent and on a server, a too-fast agent visibly slows in the live view, and the judged event stream / replay is byte-identical to the unpaced run.
