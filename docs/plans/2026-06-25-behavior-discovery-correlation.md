# Behavior <-> Discovery Correlation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Join the discovery engine (static source risk) and the behavioral-analysis engine (runtime behavioral_score) through a thin identity map, classify each agent into a clean/dirty x source/runtime quadrant, and surface the `static_blind` quadrant (clean source, dirty runtime) in CLI, API, and a first-class console panel.

**Architecture:** A pure core `correlate(discovery_facts, behavior_reports, links, thresholds) -> report` does the quadrant classification with zero IO (testable, byte-stable, I4). Two thin edge builders feed it real data: one runs the reference discovery adapter over the linked repos to produce `discovery_facts`, the other is the existing behavior wave. CLI, API, and the `CorrelationPanel` console UI are shells over the pure core. A hand-maintained `corpus/agent_links.json` is the only new ground-truth until P3 builds 1:1 twin evidence bundles.

**Tech Stack:** Python 3.13 stdlib `unittest` (core + CLI tests, zero install), `.venv` fastapi TestClient (API test), React 18 + TypeScript + vitest (console), `recette/behavior/*` engine, `recette/discovery_harness.py` reference adapter.

**Design reference:** `docs/plans/2026-06-25-behavior-discovery-correlation-design.md`

**Conventions (read before coding):**
- Tests are stdlib `unittest`, run `python3 -m unittest tests.<module> -v`. API tests need fastapi: run with `./.venv/bin/python -m unittest ...`.
- Determinism I4: `correlate` is pure -- no `time`/`datetime.now`/`random`, sorted/stable dict order, byte-identical on replay. Mandatory replay test.
- Discovery ground-truth rule: `static_flagged` uses INVARIANT properties only (detection + risk level/rank + action_pattern), NEVER an opaque static score.
- Fail-loud: an unresolved link or an uncovered discovery subject is reported in `unresolved[]` / `coverage_gaps[]`, never a phantom quadrant.
- R16 console contract gate: real captured fixture + render-and-assert + envelope unwrap.
- No emoji anywhere. Comments/code in English.

---

### Task 1: The identity map `corpus/agent_links.json` + loader

**Files:**
- Create: `corpus/agent_links.json`
- Create: `recette/behavior/links.py`
- Test: `tests/test_behavior_links.py`

**Step 1: Write the failing test**

```python
# tests/test_behavior_links.py
import unittest
from recette.behavior.links import load_links, Link


class TestAgentLinks(unittest.TestCase):
    def test_load_links_returns_parsed_entries(self):
        links = load_links()
        self.assertTrue(links, "agent_links.json must declare at least one link")
        first = links[0]
        self.assertIsInstance(first, Link)
        self.assertTrue(first.agent_id)
        # every link names at least a discovery subject OR a runtime subject
        for ln in links:
            self.assertTrue(ln.discovery_subject or ln.runtime_subject)

    def test_links_have_unique_agent_ids(self):
        ids = [ln.agent_id for ln in load_links()]
        self.assertEqual(len(ids), len(set(ids)), "agent_id must be unique")
```

**Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_behavior_links -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'recette.behavior.links'`

**Step 3: Write `corpus/agent_links.json`**

Pair the existing discovery subject `gh-pr-bot` with an existing runtime subject. Use the real slugs found in the corpus (`corpus/repos/gh-pr-bot`, `corpus/sim/rt-prbot-context-poisoning.git-scenario.json`). `evidence_bundle` stays null until P3.

```json
{
  "version": 1,
  "links": [
    {
      "agent_id": "pr-bot",
      "discovery_subject": "gh-pr-bot",
      "runtime_subject": "corpus/sim/rt-prbot-context-poisoning.git-scenario.json",
      "evidence_bundle": null,
      "expected": { "static_flagged": false, "runtime_dirty": true, "quadrant": "static_blind" }
    },
    {
      "agent_id": "admin-overreach",
      "discovery_subject": "gh-admin-overreach",
      "runtime_subject": null,
      "evidence_bundle": null,
      "expected": { "static_flagged": true, "runtime_dirty": null, "quadrant": null }
    }
  ]
}
```

**Step 4: Write `recette/behavior/links.py`**

```python
"""The agent identity map -- links a discovery subject (source repo) to its
runtime evidence so a behavioral wave can be correlated with the static scan.

Hand-maintained ground-truth until P3 builds 1:1 twin evidence bundles. Pure:
loading is a deterministic parse, no clock/random.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

DEFAULT_LINKS = Path(__file__).resolve().parents[2] / "corpus" / "agent_links.json"


@dataclass(frozen=True)
class Link:
    """One agent's coupling between its discovery subject and its runtime."""

    agent_id: str
    discovery_subject: str | None
    runtime_subject: str | None
    evidence_bundle: str | None
    expected: dict


def load_links(path: Path | str = DEFAULT_LINKS) -> list[Link]:
    """Parse the identity map into Link records, sorted by agent_id (I4)."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    links = [
        Link(
            agent_id=str(e["agent_id"]),
            discovery_subject=e.get("discovery_subject"),
            runtime_subject=e.get("runtime_subject"),
            evidence_bundle=e.get("evidence_bundle"),
            expected=e.get("expected") or {},
        )
        for e in data.get("links", [])
    ]
    return sorted(links, key=lambda ln: ln.agent_id)
```

**Step 5: Run test to verify it passes**

Run: `python3 -m unittest tests.test_behavior_links -v`
Expected: PASS (2 tests)

**Step 6: Commit**

```bash
git add corpus/agent_links.json recette/behavior/links.py tests/test_behavior_links.py
git commit -m "feat(behavior): agent identity map linking discovery subject to runtime"
```

---

### Task 2: The pure correlation core (quadrant classification)

**Files:**
- Create: `recette/behavior/correlate.py`
- Test: `tests/test_behavior_correlate.py`

The core takes ALREADY-BUILT inputs so it is pure and unit-testable with fixtures (no adapter, no IO):
- `discovery_facts: dict[discovery_subject -> {"detected": bool, "flagged": bool}]`
- `behavior_reports: dict[agent_id -> behavior agent-report dict]` (the `agents[]` items from an AnalysisReport)
- `links: list[Link]`
- `thresholds: dict` (e.g. `{"runtime_dirty": 50}`)

**Step 1: Write the failing test**

```python
# tests/test_behavior_correlate.py
import json
import unittest

from recette.behavior.correlate import correlate
from recette.behavior.links import Link


def _link(agent_id, disc, runtime, expected):
    return Link(agent_id=agent_id, discovery_subject=disc, runtime_subject=runtime,
                evidence_bundle=None, expected=expected)


class TestCorrelate(unittest.TestCase):
    def setUp(self):
        # source clean (not flagged), runtime dirty (score 80 > 50) -> static_blind
        self.discovery_facts = {
            "gh-pr-bot": {"detected": True, "flagged": False},
            "gh-admin-overreach": {"detected": True, "flagged": True},
        }
        self.behavior_reports = {
            "pr-bot": {"agent_id": "pr-bot", "behavioral_score": 80, "coherent": False},
            "admin-overreach": {"agent_id": "admin-overreach", "behavioral_score": 90, "coherent": False},
        }
        self.links = [
            _link("pr-bot", "gh-pr-bot", "x", {}),
            _link("admin-overreach", "gh-admin-overreach", "x", {}),
            _link("ghost", "gh-missing", "x", {}),  # discovery_facts has no gh-missing
        ]
        self.thresholds = {"runtime_dirty": 50}

    def test_static_blind_quadrant(self):
        rep = correlate(self.discovery_facts, self.behavior_reports, self.links, self.thresholds)
        row = next(r for r in rep["rows"] if r["agent_id"] == "pr-bot")
        self.assertFalse(row["static_flagged"])
        self.assertTrue(row["runtime_dirty"])
        self.assertEqual(row["quadrant"], "static_blind")
        self.assertIn("pr-bot", rep["quadrants"]["static_blind"])

    def test_agree_dirty_quadrant(self):
        rep = correlate(self.discovery_facts, self.behavior_reports, self.links, self.thresholds)
        row = next(r for r in rep["rows"] if r["agent_id"] == "admin-overreach")
        self.assertEqual(row["quadrant"], "agree_dirty")
        self.assertTrue(row["agreement"])

    def test_unresolved_link_is_loud_not_a_quadrant(self):
        rep = correlate(self.discovery_facts, self.behavior_reports, self.links, self.thresholds)
        reasons = {u["agent_id"]: u["reason"] for u in rep["unresolved"]}
        self.assertEqual(reasons.get("ghost"), "discovery_missing")
        # the ghost agent never appears in any quadrant
        all_quadrant_ids = sum(
            (v for v in rep["quadrants"].values() if isinstance(v, list)), []
        )
        self.assertNotIn("ghost", all_quadrant_ids)

    def test_replay_byte_identical(self):
        a = correlate(self.discovery_facts, self.behavior_reports, self.links, self.thresholds)
        b = correlate(self.discovery_facts, self.behavior_reports, self.links, self.thresholds)
        self.assertEqual(json.dumps(a, sort_keys=True), json.dumps(b, sort_keys=True))
```

**Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_behavior_correlate -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'recette.behavior.correlate'`

**Step 3: Write `recette/behavior/correlate.py`**

```python
"""Correlate the static discovery scan with the runtime behavioral wave.

Discovery PREDICTS risk from source; the behavioral engine MEASURES it at
runtime. correlate() joins them through the agent identity map and classifies
each agent into a 2x2 quadrant. The headline research signal is ``static_blind``
-- a source the scanner called clean that behaves dirty at runtime.

Pure (I4): a function of (discovery_facts, behavior_reports, links, thresholds);
no clock, no random, sorted/stable output -> byte-identical on replay.
"""

from __future__ import annotations

from .links import Link
from .report import TOOL_VERSION

_QUADRANT = {
    (False, False): "agree_clean",
    (False, True): "static_blind",
    (True, False): "static_overflag",
    (True, True): "agree_dirty",
}


def correlate(
    discovery_facts: dict[str, dict],
    behavior_reports: dict[str, dict],
    links: list[Link],
    thresholds: dict,
) -> dict:
    """Classify each linked agent into a quadrant. Fail-loud on missing sides."""
    dirty_threshold = int(thresholds.get("runtime_dirty", 50))
    rows: list[dict] = []
    unresolved: list[dict] = []
    quadrants: dict[str, list[str] | int] = {
        "agree_clean": 0,
        "agree_dirty": 0,
        "static_blind": [],
        "static_overflag": [],
    }

    for ln in sorted(links, key=lambda x: x.agent_id):
        disc = discovery_facts.get(ln.discovery_subject or "")
        beh = behavior_reports.get(ln.agent_id)
        if disc is None:
            unresolved.append({"agent_id": ln.agent_id, "reason": "discovery_missing"})
            continue
        if beh is None:
            unresolved.append({"agent_id": ln.agent_id, "reason": "evidence_missing"})
            continue

        static_flagged = bool(disc.get("flagged"))
        runtime_dirty = int(beh.get("behavioral_score", 0)) >= dirty_threshold
        quadrant = _QUADRANT[(static_flagged, runtime_dirty)]
        rows.append(
            {
                "agent_id": ln.agent_id,
                "discovery_subject": ln.discovery_subject,
                "static_flagged": static_flagged,
                "runtime_dirty": runtime_dirty,
                "behavioral_score": int(beh.get("behavioral_score", 0)),
                "quadrant": quadrant,
                "agreement": static_flagged == runtime_dirty,
            }
        )
        if quadrant in ("agree_clean", "agree_dirty"):
            quadrants[quadrant] += 1  # type: ignore[operator]
        else:
            quadrants[quadrant].append(ln.agent_id)  # type: ignore[union-attr]

    # coverage: discovery subjects present in facts but linked to no agent
    linked_subjects = {ln.discovery_subject for ln in links if ln.discovery_subject}
    coverage_gaps = [
        {"discovery_subject": s} for s in sorted(discovery_facts) if s not in linked_subjects
    ]

    return {
        "rows": sorted(rows, key=lambda r: r["agent_id"]),
        "quadrants": quadrants,
        "unresolved": sorted(unresolved, key=lambda u: u["agent_id"]),
        "coverage_gaps": coverage_gaps,
        "thresholds": {"runtime_dirty": dirty_threshold},
        "tool_version": TOOL_VERSION,
    }
```

**Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_behavior_correlate -v`
Expected: PASS (4 tests)

**Step 5: Commit**

```bash
git add recette/behavior/correlate.py tests/test_behavior_correlate.py
git commit -m "feat(behavior): pure correlation core -- quadrant classification (I4)"
```

---

### Task 3: The discovery-facts edge builder (IO at the boundary)

**Files:**
- Modify: `recette/behavior/correlate.py` (add `build_discovery_facts`)
- Test: `tests/test_behavior_correlate.py` (add one integration test)

`build_discovery_facts` runs the reference discovery adapter over the repos named in the links and reduces each to `{detected, flagged}`. `flagged` = detected AND the repo carries a high-risk signal (max risk level above the corpus median, derived from the existing harness risk levels -- invariant property, not a score).

**Step 1: Write the failing test**

```python
# add to tests/test_behavior_correlate.py
    def test_build_discovery_facts_over_corpus(self):
        from recette.behavior.correlate import build_discovery_facts
        from recette.behavior.links import load_links
        facts = build_discovery_facts(load_links())
        # gh-pr-bot is a detected agent repo in the corpus
        self.assertIn("gh-pr-bot", facts)
        self.assertTrue(facts["gh-pr-bot"]["detected"])
        # gh-admin-overreach is the high-risk overreach repo -> flagged
        self.assertTrue(facts["gh-admin-overreach"]["flagged"])
```

**Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_behavior_correlate.TestCorrelate.test_build_discovery_facts_over_corpus -v`
Expected: FAIL with `ImportError: cannot import name 'build_discovery_facts'`

**Step 3: Add `build_discovery_facts` to `recette/behavior/correlate.py`**

Read `recette/discovery_harness.py` for the exact adapter API (`ReferenceSourceScanAdapter`, `register/scan/await_run/risks`, risk objects expose a level via `_max_level`). Implement:

```python
def build_discovery_facts(links, corpus_root=None):
    """Run the reference source-scan adapter over each link's discovery subject
    and reduce it to {detected, flagged}. Pure given the corpus (the adapter is
    deterministic, proven in discovery_harness). flagged uses the invariant risk
    LEVEL, never an opaque score (discovery ground-truth rule)."""
    from pathlib import Path
    from ..discovery_harness import DEFAULT_REPO_CORPUS, _max_level
    from ..discovery_mock import ReferenceSourceScanAdapter

    root = Path(corpus_root or DEFAULT_REPO_CORPUS)
    adapter = ReferenceSourceScanAdapter()
    facts: dict[str, dict] = {}
    levels: dict[str, int] = {}
    for ln in links:
        subj = ln.discovery_subject
        if not subj or subj in facts:
            continue
        repo_tree = str(root / subj / "repo")
        if not Path(repo_tree).exists():
            facts[subj] = {"detected": False, "flagged": False}
            continue
        sid = adapter.register(repo_tree)
        adapter.await_run(adapter.scan(sid))
        risks = adapter.risks(sid)
        facts[subj] = {"detected": len(risks) > 0}
        levels[subj] = _max_level(risks) if risks else 0
    # flagged = detected AND max level strictly above the median detected level
    detected_levels = sorted(v for k, v in levels.items() if facts[k]["detected"])
    median = detected_levels[len(detected_levels) // 2] if detected_levels else 0
    for subj in facts:
        facts[subj]["flagged"] = facts[subj]["detected"] and levels.get(subj, 0) > median
    return dict(sorted(facts.items()))
```

NOTE: verify `ReferenceSourceScanAdapter` import path (`recette/discovery_mock.py` vs `recette/discovery_harness.py`) and `_max_level` return shape before finalizing -- run a quick `python3 -c "..."` probe. Adjust the median/flagged derivation if `_max_level` is ordinal text rather than int.

**Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_behavior_correlate -v`
Expected: PASS (5 tests)

**Step 5: Commit**

```bash
git add recette/behavior/correlate.py tests/test_behavior_correlate.py
git commit -m "feat(behavior): discovery-facts builder over reference scan adapter"
```

---

### Task 4: CLI `recette analyze correlate`

**Files:**
- Modify: `recette/cli/behavior_cmds.py` (add `_cmd_analyze_correlate`)
- Modify: `recette/__main__.py` (subparser + dispatch)
- Test: `tests/test_behavior_correlate.py` (add a CLI smoke that asserts a rendered line)

**Step 1: Write the failing test**

```python
# add to tests/test_behavior_correlate.py
    def test_cli_correlate_renders_static_blind(self):
        from recette.cli.behavior_cmds import correlate_summary
        rep = {
            "rows": [{"agent_id": "pr-bot", "static_flagged": False, "runtime_dirty": True,
                      "behavioral_score": 80, "quadrant": "static_blind", "agreement": False}],
            "quadrants": {"agree_clean": 0, "agree_dirty": 0,
                          "static_blind": ["pr-bot"], "static_overflag": []},
            "unresolved": [], "coverage_gaps": [], "thresholds": {"runtime_dirty": 50},
            "tool_version": "behavior-engine/1",
        }
        text = correlate_summary(rep)
        self.assertIn("static_blind", text)
        self.assertIn("pr-bot", text)
```

**Step 2: Run** `python3 -m unittest tests.test_behavior_correlate.TestCorrelate.test_cli_correlate_renders_static_blind -v` -> FAIL (no `correlate_summary`).

**Step 3:** Add to `recette/cli/behavior_cmds.py`:

```python
def correlate_summary(rep: dict) -> str:
    """Human render of a correlation report. Pure string build."""
    q = rep["quadrants"]
    lines = [
        "=== Behavior <-> Discovery correlation ===",
        f"agree_clean={q['agree_clean']}  agree_dirty={q['agree_dirty']}  "
        f"static_blind={len(q['static_blind'])}  static_overflag={len(q['static_overflag'])}",
        "",
    ]
    for r in rep["rows"]:
        lines.append(
            f"  {r['agent_id']:<24} static_flagged={str(r['static_flagged']):<5} "
            f"runtime_dirty={str(r['runtime_dirty']):<5} score={r['behavioral_score']:>3}  "
            f"-> {r['quadrant']}"
        )
    if rep["unresolved"]:
        lines.append("")
        lines.append("UNRESOLVED (fail-loud):")
        for u in rep["unresolved"]:
            lines.append(f"  {u['agent_id']}: {u['reason']}")
    if rep["coverage_gaps"]:
        lines.append("COVERAGE GAPS: " + ", ".join(g["discovery_subject"] for g in rep["coverage_gaps"]))
    return "\n".join(lines)


def _cmd_analyze_correlate(profile_path, threat, as_json):
    """`recette analyze correlate` -- build discovery facts + a behavioral wave
    over each linked runtime, then classify into quadrants."""
    import json as _json
    from ..behavior.correlate import build_discovery_facts, correlate
    from ..behavior.links import load_links

    links = load_links()
    discovery_facts = build_discovery_facts(links)
    # P1: behavior reports come from the wave the analyst already ran; here we
    # accept them from --profile's referenced reports dir, or empty (fail-loud).
    behavior_reports: dict = {}  # wired in Task 6 from the live wave; empty -> all evidence_missing
    thresholds = {"runtime_dirty": 50}
    rep = correlate(discovery_facts, behavior_reports, links, thresholds)
    if as_json:
        print(_json.dumps(rep, sort_keys=True, indent=2))
    else:
        print(correlate_summary(rep))
    return 0
```

In `recette/__main__.py`, mirror the existing `analyze` subparsers (find where `analyze_cmd == "export"` is registered) and add:

```python
        if args.analyze_cmd == "correlate":
            return _cmd_analyze_correlate(args.profile, args.threat, args.json)
```

plus the argparse subparser `correlate` with `--profile`, `--threat`, `--json` (copy the `export` subparser block). Import `_cmd_analyze_correlate` in the `from .cli.behavior_cmds import (...)` list.

**Step 4: Run** `python3 -m unittest tests.test_behavior_correlate -v` -> PASS. Then smoke the CLI: `python3 -m recette analyze correlate` -> prints the quadrant table (all rows `evidence_missing` until Task 6, which is the honest P1 state).

**Step 5: Commit**

```bash
git add recette/cli/behavior_cmds.py recette/__main__.py tests/test_behavior_correlate.py
git commit -m "feat(behavior): recette analyze correlate CLI"
```

---

### Task 5: API `POST /behavior/correlate`

**Files:**
- Modify: `recette/api/routers/behavior.py`
- Test: `tests/test_api_behavior.py`

The endpoint accepts the recording + profile (same as `/wave`), runs the wave to get behavior reports keyed by agent_id, builds discovery facts from the links, and returns the correlation report. This is where behavior reports become non-empty (the wave supplies them).

**Step 1: Write the failing test** (mirror the existing `[api]`-skipped tests in `tests/test_api_behavior.py`):

```python
    def test_correlate_returns_quadrants(self):
        client = self._client()  # reuse the existing TestClient helper
        body = {"recording": self._sample_recording(), "profile": {"threat": "exfil"}}
        resp = client.post("/behavior/correlate", json=body)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("quadrants", data["correlation"])
        self.assertIn("static_blind", data["correlation"]["quadrants"])
```

(Reuse whatever recording/client helpers already exist in the file; do not invent a new fixture if one is present.)

**Step 2: Run** `./.venv/bin/python -m unittest tests.test_api_behavior -v` -> FAIL (404 / missing route).

**Step 3:** Add to `recette/api/routers/behavior.py`:

```python
@router.post("/correlate")
def correlate_endpoint(request: Request, body: dict[str, Any]) -> dict:
    """Run a wave, then correlate its behavioral reports with the static
    discovery scan through the agent identity map. Returns the quadrant report.
    400 on a missing recording or invalid profile (same contract as /wave)."""
    from ...behavior.correlate import build_discovery_facts, correlate
    from ...behavior.links import load_links

    recording = body.get("recording")
    if not isinstance(recording, dict):
        raise HTTPException(status_code=400, detail="recording (object) is required")
    try:
        profile = AnalysisProfile.from_dict(body.get("profile") or {})
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"invalid profile: {exc}") from exc

    store = request.app.state.config_store
    bundle = EvidenceBundle.from_dict(
        {
            "recording": recording,
            "servers": store.list_servers(),
            "declared": _declared_for(recording, store),
            "ground_truth": {},
        }
    )
    report = run_wave(bundle, profile)
    behavior_reports = {a["agent_id"]: a for a in report.to_dict()["agents"]}
    links = load_links()
    discovery_facts = build_discovery_facts(links)
    thresholds = body.get("thresholds") or {"runtime_dirty": 50}
    corr = correlate(discovery_facts, behavior_reports, links, thresholds)
    return {"report": report.to_dict(), "correlation": corr}
```

**Step 4: Run** `./.venv/bin/python -m unittest tests.test_api_behavior -v` -> PASS (all, including new test).

**Step 5: Commit**

```bash
git add recette/api/routers/behavior.py tests/test_api_behavior.py
git commit -m "feat(behavior): POST /behavior/correlate -- wave + static scan -> quadrants"
```

---

### Task 6: The Lux -- `CorrelationPanel` console UI (R16 gate)

**Files:**
- Modify: `console/src/api/client.ts` (types + `correlateBehavior` call, unwrap envelope)
- Create: `console/src/pages/probe/CorrelationPanel.tsx`
- Create: `console/src/pages/probe/__fixtures__/correlation.fixture.json`
- Create: `console/src/pages/probe/CorrelationPanel.test.tsx`
- Modify: `console/src/pages/probe/index.tsx` (mount the panel)
- Modify: `console/src/pages/probe/probe.css` (quadrant grid tokens, theme-aware)

Use the `frontend-design` skill for the visual pass. Model the component and its test on the existing `BehaviorWavePanel.tsx` / `BehaviorWavePanel.test.tsx` -- same fetch/unwrap pattern, same CSS-token discipline (no hardcoded colors).

**Step 1: Capture a real fixture.** Start the platform (`./recette.sh platform up`), POST a sample recording to `/behavior/correlate` (copy the body from `BehaviorWavePanel`'s wave call), save the `correlation` object to `console/src/pages/probe/__fixtures__/correlation.fixture.json`. This is the R16 real payload -- not invented.

**Step 2: Write the failing render test**

```tsx
// console/src/pages/probe/CorrelationPanel.test.tsx
import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import CorrelationPanel from "./CorrelationPanel";
import fixture from "./__fixtures__/correlation.fixture.json";

describe("CorrelationPanel", () => {
  it("renders the four quadrants and highlights static_blind", () => {
    render(<CorrelationPanel correlation={fixture as any} />);
    expect(screen.getByText(/static.?blind/i)).toBeTruthy();
  });

  it("lists unresolved links loud (not hidden)", () => {
    const withGap = { ...fixture, unresolved: [{ agent_id: "x", reason: "evidence_missing" }] };
    render(<CorrelationPanel correlation={withGap as any} />);
    expect(screen.getByText(/evidence_missing/i)).toBeTruthy();
  });
});
```

**Step 3: Run** `cd console && node_modules/.bin/vitest run src/pages/probe/CorrelationPanel.test.tsx` -> FAIL (no component).

**Step 4: Build `CorrelationPanel.tsx`** -- a 2x2 grid (`agree_clean` / `static_blind` / `static_overflag` / `agree_dirty`), `static_blind` cell in the alert accent, each cell lists its agent_ids; a thresholds knob (`runtime_dirty`) that re-fetches; a provenance line (`tool_version` + thresholds); an explicit `unresolved[]` + `coverage_gaps[]` block. Add the matching `correlateBehavior(req)` to `client.ts` with typed `CorrelationReport` and envelope unwrap (`.correlation`). Add the quadrant CSS to `probe.css` using existing theme tokens.

**Step 5: Run** the vitest again -> PASS. Mount in `index.tsx` next to `BehaviorWavePanel` (`<CorrelationPanel .../>`). Run `node_modules/.bin/tsc --noEmit` -> exit 0.

**Step 6: Commit**

```bash
git add console/src/api/client.ts console/src/pages/probe/CorrelationPanel.tsx console/src/pages/probe/CorrelationPanel.test.tsx console/src/pages/probe/__fixtures__/correlation.fixture.json console/src/pages/probe/index.tsx console/src/pages/probe/probe.css
git commit -m "feat(console): CorrelationPanel -- discovery<->behavior quadrants (R16)"
```

---

### Task 7: The research runbook

**Files:**
- Create: `docs/runbooks/behavior-discovery-research.md`

**Step 1:** Write the day-to-day flow (lift the six steps from the design doc's "Team runbook" section): discovery -> build evidence -> wave -> `analyze correlate` -> inspect `static_blind` -> metrology (sweep/ablate/export) -> console panel. Include the exact commands and the `static_blind` interpretation. Note the P1 coverage state (which links resolve, which are `evidence_missing`) so the team knows the honest boundary.

**Step 2: Commit**

```bash
git add docs/runbooks/behavior-discovery-research.md
git commit -m "docs(runbook): behavior<->discovery correlation research flow"
```

---

### Task 8: Final gates + live proof

**Step 1:** Full Python suite: `python3 -m unittest discover -s tests` (then `./.venv/bin/python -m unittest discover -s tests` for the `[api]` paths). Expected: green.

**Step 2:** `make gates` (ruff + mypy + bandit). Fix any lint/type findings in the new modules.

**Step 3:** Console: `cd console && node_modules/.bin/tsc --noEmit && node_modules/.bin/vitest run`. Expected: green.

**Step 4 (live proof, R14):** `./recette.sh platform up`, open the Probe page, run a capture, confirm the CorrelationPanel renders the quadrants and the `static_blind` drill-in shows the source-clean/runtime-dirty agent. Capture the final state (screenshot or ARIA snapshot). Add the reproducible flow to `scripts/smoke_console.py` if a new flow is involved (R20: live proof in the versioned smoke, not /tmp).

**Step 5:** Update `MEMORY.md` only if a non-obvious project fact emerged (e.g. the static_blind framing). Commit nothing to `docs/tracking/` as a deliverable.

---

## P2 / P3 (out of scope for this plan, recorded for continuity)

- **P2:** discovery output (detected agent IDs) feeds a profile `cohort` selector so a wave runs over exactly the discovered set.
- **P3:** build 1:1 twin evidence bundles per discovery subject (`evidence_bundle` non-null in `agent_links.json`), closing the `evidence_missing` gaps; harden the coverage guard so an unlinked discovery subject turns it red.
