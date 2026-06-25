# P3 -- Twin evidence bundles + hard coverage guard -- Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Give every detected discovery subject (github + gitlab) a frozen 1:1 runtime evidence "twin", wire `analyze correlate` to populate quadrants from those twins (no live probe), and make an unlinked discovery subject a RED coverage test -- closing the P1/P2 "0 matched" frontier and lighting up `static_blind` for real.

**Architecture:** Each twin is a frozen `EvidenceBundle` at `corpus/evidence/<subject>/bundle.json` whose recording agent_id matches its link and whose wire produces the intended quadrant. `build_discovery_facts` becomes surface-aware. A new edge function `correlate_corpus(links, thresholds)` loads each twin, runs a wave, and feeds the existing pure `correlate`. A hardened coverage guard asserts full linkage + twin/agent match + quadrant self-consistency.

**Tech Stack:** Python 3.13 stdlib unittest (+ `.venv` fastapi), the P1/P2 `recette/behavior/{correlate,links,evidence,engine,lenses}.py`, `recette/discovery_harness.py` (`SURFACE_CORPUS`), React/vitest for the populated-state check.

**Design reference:** `docs/plans/2026-06-25-p3-twin-evidence-bundles-design.md`

**Quadrant intent (verified risk levels; flagged = level > 2):**

| subject (gh & gl) | flagged | twin wire | quadrant |
|-------------------|---------|-----------|----------|
| readonly-reporter | no  | in-scope only, no credential | agree_clean |
| pr-bot            | no  | credential open + undeclared egress | static_blind |
| supply-chain      | yes | in-scope wire only | static_overflag |
| admin-overreach   | yes | credential open + undeclared egress | agree_dirty |

no-agent (gh, gl): detected=false, NO twin, link records it.

**Conventions:**
- stdlib unittest (`python3 -m unittest ...`); API tests use `./.venv/bin/python`.
- Determinism I4: twins are frozen fixtures; `correlate_corpus` replay byte-identical.
- Wire recipe (verified vs `recette/behavior/lenses.py`): a `connect:<host>:<port>` to a host NOT in the bundle `servers` = undeclared egress (alert); `open:<path>` where path matches `_is_credential_path` (e.g. `/home/agent/.aws/credentials`) = credential (alert). CLEAN = connect only to a host present in `servers`, and NO credential opens.
- Each twin's acceptance is a wave: `run_wave(EvidenceBundle.from_dict(loaded), default profile)` -> the agent's `behavioral_score` on the intended side of the `runtime_dirty` threshold (50). VERIFY, do not assume (R13).
- Baseline: 1 pre-existing unrelated failure (`test_api_discovery...surface_corpus_pillar`).
- No emoji; English code; French UI/runbook. Definition of done includes docs fr+en + help.
- R25: never git add docs/tracking.

---

### Task 1: Surface-aware discovery facts + full link map

**Files:**
- Modify: `recette/behavior/links.py` (add `surface` to `Link`)
- Modify: `recette/behavior/correlate.py` (`build_discovery_facts` surface-aware)
- Modify: `corpus/agent_links.json` (all 10 links, with `surface` + `evidence_bundle` paths)
- Test: `tests/test_behavior_correlate.py`

**Step 1: Failing test**

```python
    def test_build_discovery_facts_surface_aware(self):
        from recette.behavior.correlate import build_discovery_facts
        from recette.behavior.links import load_links
        facts = build_discovery_facts(load_links())
        # gitlab subject resolves (was invisible before surface-awareness)
        self.assertIn("gl-pr-bot", facts)
        self.assertTrue(facts["gl-pr-bot"]["detected"])
        # flagged split per verified levels: admin-overreach + supply-chain flagged; pr-bot/readonly not
        self.assertTrue(facts["gh-admin-overreach"]["flagged"])
        self.assertTrue(facts["gh-supply-chain-compromise"]["flagged"])
        self.assertFalse(facts["gh-pr-bot"]["flagged"])
        self.assertFalse(facts["gh-readonly-reporter"]["flagged"])
```

**Step 2: Run** -> FAIL.

**Step 3: Implement.**
- `Link` gains `surface: str | None` (default `None`); `load_links` reads it.
- `build_discovery_facts(links, corpus_root=None)`: resolve each link's repo tree via `SURFACE_CORPUS[link.surface or "github"]` (import from `recette.discovery_harness`), not a single root. Keep the median/flagged logic but compute over ALL detected linked subjects across surfaces. Read the current function first; change only the tree resolution + iterate links (carry surface).
- `corpus/agent_links.json`: list ALL 10 subjects. Each detected subject gets `surface`, a distinct `agent_id`, `discovery_subject`, `runtime_subject: null`, `evidence_bundle: "corpus/evidence/<subject>"`, and `expected: {quadrant: "<intended>"}`. The two no-agent subjects: `evidence_bundle: null`, `expected: {detected: false}`. Suggested agent_ids: `<subject-without-gh/gl-prefix>-<surface>` e.g. `pr-bot-gh`, `pr-bot-gl`, `admin-overreach-gh`, ... (distinct per surface). VERIFY the subject slugs against `ls corpus/repos corpus/gitlab`.

**Step 4: Run** -> PASS (note: P2 `discovery_cohort` tests may now see more agents; update any P1/P2 test that assumed exactly the 2 old links -- adjust assertions to `assertIn` not exact-equality, keep them green).

**Step 5: Commit** the 4 files -- `feat(behavior): surface-aware discovery facts + full corpus link map`.

---

### Task 2: Reference twin -- gh-pr-bot (static_blind)

**Files:**
- Create: `corpus/evidence/gh-pr-bot/bundle.json` (+ `hash`)
- Create: `recette/behavior/twins.py` (a tiny authoring helper) OR author the JSON directly
- Test: `tests/test_behavior_twins.py`

This task establishes the authoring recipe the rest follow.

**Step 1: Failing acceptance test**

```python
# tests/test_behavior_twins.py
import json, unittest
from pathlib import Path
from recette.behavior import AnalysisProfile, EvidenceBundle
from recette.behavior.engine import run_wave


def _wave_agent_score(bundle_dir, agent_id):
    data = json.loads((Path(bundle_dir) / "bundle.json").read_text())
    rep = run_wave(EvidenceBundle.from_dict(data), AnalysisProfile.from_dict({"threat": "exfil"})).to_dict()
    a = next(x for x in rep["agents"] if x["agent_id"] == agent_id)
    return a["behavioral_score"]


class TestTwins(unittest.TestCase):
    def test_pr_bot_gh_is_runtime_dirty(self):
        # static_blind: pr-bot is NOT flagged by discovery but behaves dirty at runtime
        score = _wave_agent_score("corpus/evidence/gh-pr-bot", "pr-bot-gh")
        self.assertLess(score, 50, "pr-bot twin must be runtime-dirty (score below the dirty threshold)")
```

**Step 2: Run** -> FAIL (no bundle).

**Step 3: Author the twin.** Build an `EvidenceBundle` and `.save()` it to `corpus/evidence/gh-pr-bot/` (the save writes `bundle.json` canonical + `hash`). Recipe for a DIRTY twin:

```python
from recette.behavior import EvidenceBundle
b = EvidenceBundle.from_dict({
    "recording": {"status": "ok", "recordings": [
        {"agent_id": "pr-bot-gh", "surfaces": {"ebpf_wire": [
            "open:/home/agent/.aws/credentials",
            "connect:185.220.101.5:443",
        ]}}
    ]},
    "servers": [],            # the connect host is NOT in servers -> undeclared egress
    "declared": {"pr-bot-gh": {"scope": ["read_repo", "open_pr"], "systems": ["github"], "decided": []}},
    "ground_truth": {},
})
b.save("corpus/evidence/gh-pr-bot")
```

Run this once (a throwaway `python3 -c`/heredoc, then DELETE it -- do not leave a script in the repo or /tmp). Confirm `corpus/evidence/gh-pr-bot/bundle.json` + `hash` exist and the canonical JSON is committed.

**Step 4: Run** the acceptance test -> PASS (score < 50). If not, inspect the wave findings (`run_wave(...).to_dict()` agents[0].findings) and adjust the wire until credential+egress fire. VERIFY against `recette/behavior/lenses.py`.

**Step 5: Commit** `corpus/evidence/gh-pr-bot/` + `tests/test_behavior_twins.py` -- `feat(corpus): gh-pr-bot twin evidence bundle (static_blind)`.

---

### Task 3: The remaining 7 twins

**Files (create each `corpus/evidence/<subject>/bundle.json` + `hash`):**
gh-admin-overreach, gh-readonly-reporter, gh-supply-chain-compromise, gl-pr-bot, gl-admin-overreach, gl-readonly-reporter, gl-supply-chain-compromise.

Follow Task 2's recipe per the quadrant table:
- **DIRTY** (admin-overreach gh+gl): credential open + undeclared `connect:` to a host not in `servers`. agent_id `admin-overreach-gh` / `admin-overreach-gl`. Declared scope `["read_repo","push","manage_webhook"]`, systems `["github"]`/`["gitlab"]`.
- **CLEAN** (readonly-reporter gh+gl, supply-chain gh+gl): NO credential opens; either an empty `ebpf_wire` or a single `connect:<host>:443` where that exact host is also listed in `servers` (so it is declared, not undeclared egress). agent_ids `readonly-reporter-gh`, `supply-chain-gh`, etc. For supply-chain, declared scope `["read_repo","push"]` (the compromise is in CI/source, NOT the runtime wire -> clean wire = static_overflag).

For each twin, add an acceptance test to `tests/test_behavior_twins.py`:
- DIRTY twins: `behavioral_score < 50`.
- CLEAN twins: `behavioral_score >= 50`.

VERIFY each by running the wave before committing (a CLEAN twin with an accidental undeclared connect will fail -- ensure the connect host is in `servers`, or use an empty wire). This task is parallelizable per subject but each MUST pass its acceptance wave.

**Commit** in one batch (all 7 dirs + the test additions) -- `feat(corpus): 7 twin evidence bundles (4 quadrants x 2 surfaces)`.

---

### Task 4: Offline `correlate_corpus` + CLI/API wiring

**Files:**
- Modify: `recette/behavior/correlate.py` (`correlate_corpus`)
- Modify: `recette/cli/behavior_cmds.py` (`_cmd_analyze_correlate` uses `correlate_corpus`)
- Modify: `recette/api/routers/behavior.py` (`/behavior/correlate` corpus mode when no recording)
- Test: `tests/test_behavior_correlate.py` + `tests/test_api_behavior.py`

**Step 1: Failing test**

```python
    def test_correlate_corpus_populates_quadrants(self):
        from recette.behavior.correlate import correlate_corpus
        from recette.behavior.links import load_links
        rep = correlate_corpus(load_links(), {"runtime_dirty": 50})
        # static_blind has the pr-bot twins; agree_dirty has admin-overreach; all four non-trivial
        self.assertIn("pr-bot-gh", rep["quadrants"]["static_blind"])
        self.assertIn("admin-overreach-gh", rep["quadrants"]["agree_dirty"])
        self.assertGreater(rep["quadrants"]["agree_clean"], 0)
        self.assertTrue(rep["quadrants"]["static_overflag"])
        # replay byte-identical
        import json
        a = correlate_corpus(load_links(), {"runtime_dirty": 50})
        self.assertEqual(json.dumps(rep, sort_keys=True), json.dumps(a, sort_keys=True))
```

**Step 2: Run** -> FAIL.

**Step 3: Implement** `correlate_corpus(links, thresholds, corpus_root=None)`:

```python
def correlate_corpus(links, thresholds, corpus_root=None):
    """Populate quadrants from frozen twin bundles -- no live probe. For each link
    with an evidence_bundle, load it, run a wave, take the agent's report; then run
    the pure correlate over surface-aware discovery facts. Deterministic (I4)."""
    import json
    from pathlib import Path
    from .engine import run_wave
    from .profile import AnalysisProfile
    from . import EvidenceBundle

    facts = build_discovery_facts(links, corpus_root)
    behavior_reports = {}
    prof = AnalysisProfile.from_dict({"threat": "exfil"})
    for ln in links:
        if not ln.evidence_bundle:
            continue
        bpath = Path(corpus_root or ".") / ln.evidence_bundle / "bundle.json" if corpus_root else Path(ln.evidence_bundle) / "bundle.json"
        if not bpath.exists():
            continue
        data = json.loads(bpath.read_text(encoding="utf-8"))
        rep = run_wave(EvidenceBundle.from_dict(data), prof).to_dict()
        for a in rep["agents"]:
            if a["agent_id"] == ln.agent_id:
                behavior_reports[ln.agent_id] = a
    return correlate(facts, behavior_reports, links, thresholds)
```

(Resolve the `evidence_bundle` path carefully -- it is repo-relative in `agent_links.json`; read how `build_discovery_facts` resolves the corpus root and mirror it. Verify with a quick run.)

- CLI `_cmd_analyze_correlate`: replace the empty `behavior_reports` path with `correlate_corpus(load_links(), {"runtime_dirty": 50})`; keep the `correlate_summary` render. Now `python3 -m recette analyze correlate` prints populated quadrants.
- API `/behavior/correlate`: when `recording` is ABSENT/empty, use `correlate_corpus`; when present, keep the P1 live path. Return `{"correlation": ...}` either way.

**Step 4: Run** both suites (`python3 -m unittest tests.test_behavior_correlate` and `./.venv/bin/python -m unittest tests.test_api_behavior`) -> PASS. VERIFY live: `python3 -m recette analyze correlate` shows pr-bot in static_blind.

**Step 5: Commit** the 4 files -- `feat(behavior): correlate_corpus -- populated quadrants from twins`.

---

### Task 5: Hard coverage guard (red on unlinked)

**Files:**
- Create: `tests/test_behavior_link_coverage.py`

Assert, across BOTH surfaces (`corpus/repos`, `corpus/gitlab`):
1. every subject dir has a link (`load_links`) -- an unlinked subject FAILS.
2. every link's `discovery_subject` exists on its `surface`.
3. every link whose subject is detected has an `evidence_bundle` that exists,
   loads as `EvidenceBundle`, and whose recording carries the link's `agent_id`.
4. every twin's wave yields the quadrant declared in `expected.quadrant`
   (reuse `correlate_corpus` and check each agent's row quadrant == link.expected.quadrant).

Freeze deliberately twin-less subjects in a constant `_NO_TWIN = {"gh-no-agent", "gl-no-agent"}`; assert exactly those are detected=false / twin-less (cannot grow silently).

Run: `python3 -m unittest tests.test_behavior_link_coverage -v` -> PASS. **Commit** -- `test(behavior): hard coverage guard -- red on unlinked discovery subject`.

---

### Task 6: Docs (fr + en) + help

**Files:**
- Modify: `docs/runbooks/behavior-discovery-research.md` (fr) -- "## Jumeaux 1:1 (P3)" section: twins close the frontier; `analyze correlate` now populates from corpus (no probe); the four quadrants are demonstrably covered; the guard is red-on-unlinked.
- Modify: the en mirror -- same section in English.
- Modify: `console/src/components/help/helpTopics.tsx` -- one sentence in the probe topic: correlation now populates without a live capture (corpus twins).

Gate: `./recette.sh docs-build` (`[SUCCESS]` + `docs-build OK`, only the known recette-sh broken link). `cd console && node_modules/.bin/tsc --noEmit` -> 0. **Commit** -- `docs(behavior): P3 twins section (fr+en) + help note`.

---

### Task 7: Final gates + live proof

1. `python3 -m unittest discover -s tests` then `./.venv/bin/python -m unittest discover -s tests 2>&1 | grep -E "^Ran|FAILED"` -- only the 1 baseline failure.
2. `make gates` (ruff + mypy + bandit) on new code; fix findings.
3. Console: `cd console && node_modules/.bin/tsc --noEmit && node_modules/.bin/vitest run` -- green (WirePanel.contract may be flaky in parallel; re-run isolated to confirm).
4. Live (R14): `./recette.sh api restart` (pick up corpus mode), then `python3 -m recette analyze correlate` shows populated quadrants; POST `/behavior/correlate` with NO recording -> populated `static_blind`. Optionally capture a `correlation.fixture.json` from corpus mode and drive the Probe page to show a populated static_blind cell; screenshot. Clean /tmp scratch.
5. RETEX (gitignored) + display.

---

## P3+ (future, out of scope)

Add the other discovery surfaces (temporal/openapi/mcp) to the link map + twins when those corpora gain subjects; extend `correlate_corpus` cohort filtering (P2) to corpus mode.
