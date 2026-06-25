# P2 -- Discovery-derived wave cohort -- Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Let a behavioral wave run over exactly the agents a discovery scan surfaced -- `detected` (all discovered) or `flagged` (high-risk) -- by deriving `cohort.agents` from discovery through the P1 identity map.

**Architecture:** A pure edge-resolver `discovery_cohort(links, mode)` returns the agent_ids from a discovery scan (via the P1 `build_discovery_facts`). The engine is UNCHANGED -- its `_cohort_match` already filters on `cohort.agents`. The CLI / API edge resolves the new `cohort.discovery` profile key into `cohort.agents` before `run_wave`, so the engine stays pure and byte-stable. The UI adds a cohort selector.

**Tech Stack:** Python 3.13 stdlib unittest (+ `.venv` fastapi for API), React 18 + TS + vitest, the P1 `recette/behavior/correlate.py` + `links.py`.

**Design reference:** `docs/plans/2026-06-25-p2-discovery-cohort-design.md`

**Conventions (read before coding):**
- Stdlib unittest: `python3 -m unittest tests.<module> -v`. API tests need fastapi: `./.venv/bin/python -m unittest ...`.
- Determinism I4: `discovery_cohort` pure (the scan is deterministic), sorted+deduped output; engine unchanged so the wave stays byte-stable.
- Fail-loud (R13): always surface the resolved cohort (mode + agent_ids + count); a cohort that matches no runtime agent is rendered explicitly, never a blank success.
- Pre-commit hook enforces ruff isort/format: alphabetical imports, stdlib separated.
- Baseline: ONE pre-existing unrelated failure `test_api_discovery...surface_corpus_pillar`. Any OTHER new failure is yours.
- No emoji. English code/comments. French UI/help/runbook text (match siblings).
- Definition of done includes docs (fr + en mirror) + a help-topic note (P1 lesson).

---

### Task 1: Pure resolver `discovery_cohort`

**Files:**
- Modify: `recette/behavior/correlate.py` (add `discovery_cohort`)
- Test: `tests/test_behavior_correlate.py`

**Step 1: Failing test**

```python
# add to tests/test_behavior_correlate.py
    def test_discovery_cohort_detected_and_flagged(self):
        from recette.behavior.correlate import discovery_cohort
        from recette.behavior.links import load_links
        links = load_links()
        detected = discovery_cohort(links, "detected")
        flagged = discovery_cohort(links, "flagged")
        # both sorted + deduped
        self.assertEqual(detected, sorted(set(detected)))
        self.assertEqual(flagged, sorted(set(flagged)))
        # flagged is a subset of detected
        self.assertTrue(set(flagged).issubset(set(detected)))
        # admin-overreach is the high-risk repo -> in flagged
        self.assertIn("admin-overreach", flagged)
        # replay-stable
        self.assertEqual(discovery_cohort(links, "flagged"), flagged)

    def test_discovery_cohort_bad_mode_raises(self):
        from recette.behavior.correlate import discovery_cohort
        from recette.behavior.links import load_links
        with self.assertRaises(ValueError):
            discovery_cohort(load_links(), "bogus")
```

**Step 2: Run** `python3 -m unittest tests.test_behavior_correlate -v` -> FAIL (no `discovery_cohort`).

**Step 3: Implement** in `recette/behavior/correlate.py`:

```python
def discovery_cohort(links, mode, corpus_root=None):
    """Resolve a wave cohort from a discovery scan: the agent_ids whose
    discovery_subject is detected (mode="detected") or flagged (mode="flagged").
    Pure given the corpus (build_discovery_facts is deterministic); sorted+deduped
    so the cohort is byte-stable across runs (I4)."""
    if mode not in ("detected", "flagged"):
        raise ValueError(f"unknown cohort mode: {mode!r} (expected detected|flagged)")
    facts = build_discovery_facts(links, corpus_root)
    out = set()
    for ln in links:
        subj = ln.discovery_subject
        fact = facts.get(subj or "")
        if fact and fact.get(mode if mode == "detected" else "flagged"):
            out.add(ln.agent_id)
    return sorted(out)
```

**Step 4: Run** -> PASS (2 new tests). **Step 5: Commit** `recette/behavior/correlate.py` + `tests/test_behavior_correlate.py` -- `feat(behavior): discovery_cohort resolver (detected|flagged)`.

---

### Task 2: CLI `--cohort-discovery`

**Files:**
- Modify: `recette/cli/behavior_cmds.py` (`_cmd_analyze_wave` + a resolve helper)
- Modify: `recette/cli/parser.py` (add `--cohort-discovery` to the `wave` subparser, and thread it through `recette/__main__.py` dispatch if the dispatch passes explicit args)
- Test: `tests/test_behavior_correlate.py`

**Step 1: Failing test** (unit-test the resolve helper, pure):

```python
    def test_resolve_cohort_into_profile(self):
        from recette.cli.behavior_cmds import resolve_discovery_cohort
        from recette.behavior import AnalysisProfile
        prof = AnalysisProfile.from_dict({"threat": "exfil"})
        resolved = resolve_discovery_cohort(prof, "flagged")
        self.assertIn("admin-overreach", prof.cohort.get("agents", []))
        self.assertEqual(resolved["mode"], "flagged")
        self.assertEqual(sorted(resolved["agents"]), sorted(prof.cohort["agents"]))
```

**Step 2: Run** -> FAIL.

**Step 3: Implement.** In `recette/cli/behavior_cmds.py`:

```python
def resolve_discovery_cohort(profile, mode):
    """Fill profile.cohort['agents'] from a discovery scan; return the resolved
    cohort echo {mode, agents}. No-op echo when mode is falsy."""
    if not mode:
        return {"mode": None, "agents": profile.cohort.get("agents", ["*"])}
    from ..behavior.correlate import discovery_cohort
    from ..behavior.links import load_links

    agents = discovery_cohort(load_links(), mode)
    profile.cohort["agents"] = agents
    return {"mode": mode, "agents": agents}
```

Thread `cohort_discovery` into `_cmd_analyze_wave`: read `--cohort-discovery`, call `resolve_discovery_cohort(prof, cohort_discovery)` after building `prof` and BEFORE `run_wave`, and print the echo line (`cohort: {mode} -> {agents} ({n})`) so it is fail-loud. Add `--cohort-discovery` (choices `detected`,`flagged`) to the `wave` subparser in `recette/cli/parser.py`, and pass `args.cohort_discovery` in the `__main__.py` dispatch call to `_cmd_analyze_wave` (read the current call + signature first and extend both consistently).

**Step 4: Run** the unit test -> PASS. Then VERIFY live: `python3 -m recette analyze wave --evidence <a real bundle> --cohort-discovery flagged` echoes the resolved cohort. (Find a real evidence bundle path with `python3 -m recette analyze --help` / existing fixtures; if none handy, the unit test is the gate and note it.)

**Step 5: Commit** the 3 files -- `feat(behavior): analyze wave --cohort-discovery`.

---

### Task 3: API resolves `cohort.discovery`

**Files:**
- Modify: `recette/api/routers/behavior.py` (`/behavior/wave` and `/behavior/correlate`)
- Test: `tests/test_api_behavior.py`

**Step 1: Failing test** (model on existing wave test; use the file's real client + `_RECORDING`):

```python
    def test_wave_with_discovery_cohort_flagged_echoes_cohort(self):
        body = {"recording": _RECORDING, "profile": {"threat": "exfil", "cohort": {"discovery": "flagged"}}}
        resp = self.client.post("/behavior/wave", json=body)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["cohort"]["mode"], "flagged")
        self.assertIn("admin-overreach", data["cohort"]["agents"])
```

**Step 2: Run** `./.venv/bin/python -m unittest tests.test_api_behavior -v` -> FAIL.

**Step 3: Implement.** In both `/behavior/wave` and `/behavior/correlate`, after building `profile`, resolve the cohort before `run_wave`:

```python
    cohort_echo = {"mode": None, "agents": profile.cohort.get("agents", ["*"])}
    mode = profile.cohort.get("discovery")
    if mode:
        if mode not in ("detected", "flagged"):
            raise HTTPException(status_code=400, detail=f"invalid cohort.discovery: {mode}")
        from ...behavior.correlate import discovery_cohort
        from ...behavior.links import load_links
        agents = discovery_cohort(load_links(), mode)
        profile.cohort["agents"] = agents
        cohort_echo = {"mode": mode, "agents": agents}
```

Add `"cohort": cohort_echo` to BOTH responses. (Verify `AnalysisProfile.from_dict` preserves an unknown `cohort.discovery` key -- read `recette/behavior/profile.py`; it stores `cohort` as a dict, so the key survives.)

**Step 4: Run** the venv suite -> PASS (new test + only the 1 baseline failure remains).

**Step 5: Commit** `recette/api/routers/behavior.py` + `tests/test_api_behavior.py` -- `feat(behavior): API resolves cohort.discovery into cohort.agents`.

---

### Task 4: UI cohort selector in BehaviorWavePanel

**Files:**
- Modify: `console/src/api/client.ts` (the `BehaviorProfile` type: add optional `cohort?: { discovery?: "detected" | "flagged" }`; the wave result type: add optional `cohort?: { mode, agents }`)
- Modify: `console/src/pages/probe/BehaviorWavePanel.tsx` (selector + render resolved cohort)
- Modify: `console/src/pages/probe/BehaviorWavePanel.test.tsx`
- Modify: `console/src/pages/probe/probe.css` (selector style, theme tokens only -- reuse existing)

**Step 1: Failing test** -- add to `BehaviorWavePanel.test.tsx`: selecting "Flagged" and running posts a profile whose `cohort.discovery === "flagged"` (mock `runBehaviorWave`, assert the arg). Run: `cd console && node_modules/.bin/vitest run src/pages/probe/BehaviorWavePanel.test.tsx` -> fail.

**Step 2: Implement.** Add a `cohort` state (`"all" | "detected" | "flagged"`, default `"all"`) and a labelled `<select>` (All / Discovered / Flagged) in the existing knobs fieldset. When building the posted profile, set `cohort: cohort === "all" ? undefined : { discovery: cohort }`. After a result, if `result.cohort?.mode`, render a line `cohort: {mode} -> {agents.length} agent(s)` (fail-loud) listing the agents. Keep CSS tokens (no hex).

**Step 3: Run** vitest -> pass. `node_modules/.bin/tsc --noEmit` -> 0. Run the FULL probe suite (`vitest run src/pages/probe`) to catch sibling regressions (P1 lesson: a mount/mock drift can break index.test).

**Step 4: Commit** the 4 console files -- `feat(console): cohort selector (all/discovered/flagged) in BehaviorWavePanel`.

---

### Task 5: Docs (fr + en) + help

**Files:**
- Modify: `docs/runbooks/behavior-discovery-research.md` (fr) -- add a "Cohorte depuis discovery (P2)" section: the two modes, the CLI flag, the API key, the UI selector, the fail-loud echo, the "0 matched" P1 frontier.
- Modify: `docs-site/i18n/en/docusaurus-plugin-content-docs/current/runbooks/behavior-discovery-research.md` -- mirror in English.
- Modify: `console/src/components/help/helpTopics.tsx` -- add one sentence to the `probe` topic's correlation/behavioral section noting the cohort selector (All/Discovered/Flagged).

**Step 1:** Write the three edits. **Step 2:** `./recette.sh docs-build` -> must show `[SUCCESS]` + `docs-build OK` (the only known broken link is the pre-existing `recette-sh` one). `cd console && node_modules/.bin/tsc --noEmit` -> 0. **Step 3: Commit** the 3 files -- `docs(behavior): P2 cohort section (fr+en) + help note`.

---

### Task 6: Final gates + live proof

**Step 1:** `python3 -m unittest discover -s tests` then `./.venv/bin/python -m unittest discover -s tests 2>&1 | grep -E "^Ran|FAILED"` -- only the 1 baseline failure.
**Step 2:** `make gates` (ruff + mypy + bandit) on the new code; fix findings.
**Step 3:** Console: `cd console && node_modules/.bin/tsc --noEmit && node_modules/.bin/vitest run` -- green.
**Step 4 (live, R14):** platform up; POST `/behavior/wave` with `profile.cohort.discovery="flagged"` and confirm the response echoes the resolved cohort; drive the Probe page, pick "Flagged" in the cohort selector, run, screenshot the resolved-cohort line. Capture proof; clean any /tmp scratch.
**Step 5:** RETEX (gitignored) + display.

---

## Out of scope (P3)

1:1 twin evidence bundles per discovery subject -- so a flagged cohort has runtime evidence to score (closes the "0 matched" frontier).
