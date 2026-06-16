# RailNode Surface Detection Recette -- Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Prove, deterministically and per observation surface, that a discovery tool (RailNode) SEES a simulated agent -- and make "seen on no surface" a red test.

**Architecture:** A pure surface-projection maps one simulated run (its `ProxyTrace` hook view + its `WireFlow` network view) onto RailNode's observation surfaces (subprocess/MCP/SDK = hook family; eBPF/wire = network family). A `SurfaceDiscoveryAdapter` protocol is the seam where the real RailNode plugs in; a reference adapter is the correct offline oracle. A detection scorecard reports detection rate per surface and flags any agent detected on NO surface (the thesis failure). The ghost agent (native egress, bypasses the SDK) is the keystone subject: invisible on the hook surface, visible on the wire surface.

**Tech Stack:** Python stdlib (`unittest`, `dataclasses`, `enum`); zero new dependency. Reuses `recette/platform/proxy/tracing.py::ProxyTrace`, `recette/platform/proxy/wire.py::WireFlow`, the `DiscoveryResult` shape from `recette/adapters.py`. Gates: `.venv/bin/python -m unittest discover -s tests`, `make recette`, `.venv-pyaudit/bin/ruff check` + `mypy`.

**Design reference:** `docs/plans/2026-06-16-railnode-discovery-recette-host-docker-design.md` (the founding doc; §2 surfaces, §5 the two views, §7 per-surface coverage, Annexe A eBPF/hook).

**Branch policy:** Work on `main`, no branches (project rule). `git status` before each commit; stage ONLY files you create/own -- never `config/inspect_ia_agents.config.json` or any file another session is editing (R21). Commit small after each task.

**Invariants:** I4 (projection + detection are pure, replay-stable; a replay test is mandatory), I3 (a detected agent still carries a bound identity downstream -- not re-judged here), I2/I5 (the wire/audit duality is the same one `reconcile_run` uses).

---

## Background the executor needs

- **The bench already has two views of a run** and we REUSE them, we do not capture anew:
  - `ProxyTrace` (`recette/platform/proxy/tracing.py:45`) -- the in-app mediated side effect: `action_type`, `resource`, `target`, `ok`, ... This is the **hook** view (the structured call the agent made through the SDK/MCP/subprocess shim).
  - `WireFlow` (`recette/platform/proxy/wire.py:71`) -- one intercepted request/response at the network level: `method`, `host`, `port`, `path`, `status_code`, ... This is the **eBPF/wire** view (the bytes a syscall/eBPF probe sees).
- **The ghost agent** (founding doc Annexe A.4): an agent that talks straight to a DB/disk in native code bypasses the SDK, so it produces a `WireFlow` but NO `ProxyTrace`. The same wire-vs-audit duality powers `recette/platform/proxy/reconcile.py::reconcile_run`. Detection must therefore be PER SURFACE: the hook surface misses the ghost, the wire surface catches it.
- **The seam** mirrors `recette/adapters.py`: a `Protocol` + a `Reference*` correct oracle. The real RailNode is wired later by implementing the protocol (like `recette/http_adapter.py` does for `SourceScanAdapter`). We build the oracle now.
- **Determinism (I4):** projection and detection are pure functions of their inputs -- no clock, no random, stable (sorted) ordering. A replay test asserts a byte-stable scorecard.
- **New package:** everything lands under a new `recette/surface/` subpackage so it is cohesive and does not bloat `adapters.py`.

---

## Task 1: Surface projection -- run views -> per-surface observation (pure)

**Files:**
- Create: `recette/surface/__init__.py`
- Create: `recette/surface/surfaces.py`
- Test: `tests/test_surface_projection.py`

**Step 1: Write the failing test**

```python
# tests/test_surface_projection.py
"""Surface projection: map a run's hook (ProxyTrace) + wire (WireFlow) views onto
RailNode observation surfaces. Pure, deterministic (I4)."""
from __future__ import annotations

import unittest

from recette.surface.surfaces import (
    HOOK_SURFACES,
    ObservationSurface,
    project_surfaces,
)

# One mediated call (hook view) AND its wire flow (network view): a normal agent.
TRACES = [{"action_type": "open_pr", "resource": "acme/web#42"}]
FLOWS = [{"seq": 0, "method": "POST", "host": "api.github.com", "port": 443, "path": "/repos/acme/web/pulls"}]
# A ghost: wire egress to a DB, with NO matching mediated trace.
GHOST_FLOWS = [{"seq": 0, "method": "POST", "host": "shadow-db.acme.internal", "port": 5432, "path": "/write"}]


class TestProjectSurfaces(unittest.TestCase):
    def test_hook_surfaces_see_the_mediated_call(self) -> None:
        surfaces = project_surfaces(proxy_traces=TRACES, wire_flows=FLOWS)
        for s in HOOK_SURFACES:
            self.assertEqual(surfaces[s].visible, ("open_pr:acme/web#42",))

    def test_wire_surface_sees_the_network_flow(self) -> None:
        surfaces = project_surfaces(proxy_traces=TRACES, wire_flows=FLOWS)
        self.assertEqual(
            surfaces[ObservationSurface.EBPF_WIRE].visible,
            ("POST api.github.com:443/repos/acme/web/pulls",),
        )

    def test_ghost_is_invisible_on_hook_visible_on_wire(self) -> None:
        surfaces = project_surfaces(proxy_traces=[], wire_flows=GHOST_FLOWS)
        for s in HOOK_SURFACES:
            self.assertEqual(surfaces[s].visible, ())  # SDK bypassed -> hook blind
        self.assertEqual(
            surfaces[ObservationSurface.EBPF_WIRE].visible,
            ("POST shadow-db.acme.internal:5432/write",),
        )

    def test_projection_is_deterministic_and_sorted(self) -> None:
        flows = [
            {"seq": 1, "method": "GET", "host": "b.com", "port": 443, "path": "/2"},
            {"seq": 0, "method": "GET", "host": "a.com", "port": 443, "path": "/1"},
        ]
        a = project_surfaces(proxy_traces=[], wire_flows=flows)
        b = project_surfaces(proxy_traces=[], wire_flows=flows)
        self.assertEqual(a, b)
        # sorted by the stable visible string, not input order
        self.assertEqual(
            a[ObservationSurface.EBPF_WIRE].visible,
            ("GET a.com:443/1", "GET b.com:443/2"),
        )


if __name__ == "__main__":
    unittest.main()
```

**Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m unittest tests.test_surface_projection -v`
Expected: FAIL (`ModuleNotFoundError: recette.surface`).

**Step 3: Write minimal implementation**

```python
# recette/surface/__init__.py
"""Per-surface discovery recette: does RailNode SEE the agent on each surface?"""
```

```python
# recette/surface/surfaces.py
"""Project one run's two views onto RailNode's observation surfaces (pure, I4).

A run yields two deterministic views (founding doc 2026-06-16, sec. 5):
- the HOOK view = the mediated/structured calls (``ProxyTrace`` dicts): what an
  in-process shim (subprocess / MCP / SDK) sees.
- the WIRE view = the network flows (``WireFlow`` dicts): what an eBPF / syscall
  probe sees on the wire.

A ghost agent that bypasses the SDK produces a WIRE flow with no HOOK trace, so
it is invisible to the hook surfaces and visible to the wire surface. Projection
is a pure function of (proxy_traces, wire_flows): no clock, no random, sorted
output, replay-stable.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ObservationSurface(str, Enum):
    """The surfaces RailNode can observe an agent on (AgentRail RFC + diagram)."""

    HOOK_SUBPROCESS = "hook_subprocess"
    HOOK_MCP = "hook_mcp"
    HOOK_SDK = "hook_sdk"
    EBPF_WIRE = "ebpf_wire"


# The inline hook family: all three see the same mediated/structured call.
HOOK_SURFACES: tuple[ObservationSurface, ...] = (
    ObservationSurface.HOOK_SUBPROCESS,
    ObservationSurface.HOOK_MCP,
    ObservationSurface.HOOK_SDK,
)


@dataclass(frozen=True)
class SurfaceObservation:
    """What is visible on one surface: a sorted tuple of stable identifiers."""

    surface: ObservationSurface
    visible: tuple[str, ...]


def _hook_key(trace: dict) -> str:
    """Stable identifier of a mediated call (the structured intent)."""
    return f"{trace.get('action_type', '')}:{trace.get('resource', '')}"


def _wire_key(flow: dict) -> str:
    """Stable identifier of a network flow (method host:port/path)."""
    return f"{flow.get('method', '')} {flow.get('host', '')}:{flow.get('port', '')}{flow.get('path', '')}"


def project_surfaces(
    *, proxy_traces: list[dict], wire_flows: list[dict]
) -> dict[ObservationSurface, SurfaceObservation]:
    """Map the two run views onto every observation surface (pure, sorted)."""
    hook_visible = tuple(sorted(_hook_key(t) for t in proxy_traces))
    wire_visible = tuple(sorted(_wire_key(f) for f in wire_flows))
    result: dict[ObservationSurface, SurfaceObservation] = {}
    for surface in HOOK_SURFACES:
        result[surface] = SurfaceObservation(surface=surface, visible=hook_visible)
    result[ObservationSurface.EBPF_WIRE] = SurfaceObservation(
        surface=ObservationSurface.EBPF_WIRE, visible=wire_visible
    )
    return result
```

**Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m unittest tests.test_surface_projection -v`
Expected: PASS (4 tests).

**Step 5: Commit**

```bash
git add recette/surface/__init__.py recette/surface/surfaces.py tests/test_surface_projection.py
git commit -m "feat(surface): project run views onto RailNode observation surfaces (pure, I4)"
```

---

## Task 2: Detection adapter -- the seam + reference oracle

**Files:**
- Create: `recette/surface/detect.py`
- Test: `tests/test_surface_detect.py`

**Step 1: Write the failing test**

```python
# tests/test_surface_detect.py
"""Per-surface detection: the SurfaceDiscoveryAdapter seam + reference oracle.
The ghost agent is the keystone: invisible on hook, detected on wire."""
from __future__ import annotations

import unittest

from recette.surface.detect import ReferenceSurfaceDiscoveryAdapter, detect_agent
from recette.surface.surfaces import ObservationSurface

NORMAL_TRACES = [{"action_type": "open_pr", "resource": "acme/web#42"}]
NORMAL_FLOWS = [{"seq": 0, "method": "POST", "host": "api.github.com", "port": 443, "path": "/p"}]
GHOST_FLOWS = [{"seq": 0, "method": "POST", "host": "shadow-db.acme.internal", "port": 5432, "path": "/w"}]


class TestReferenceAdapter(unittest.TestCase):
    def test_detects_when_something_is_visible(self) -> None:
        adapter = ReferenceSurfaceDiscoveryAdapter()
        from recette.surface.surfaces import SurfaceObservation

        obs = SurfaceObservation(ObservationSurface.HOOK_SDK, ("open_pr:acme/web#42",))
        self.assertTrue(adapter.detect_on(obs).detected)

    def test_blind_when_nothing_visible(self) -> None:
        adapter = ReferenceSurfaceDiscoveryAdapter()
        from recette.surface.surfaces import SurfaceObservation

        obs = SurfaceObservation(ObservationSurface.HOOK_SDK, ())
        self.assertFalse(adapter.detect_on(obs).detected)


class TestDetectAgent(unittest.TestCase):
    def test_normal_agent_detected_on_every_surface(self) -> None:
        result = detect_agent(
            agent_id="pr-bot",
            proxy_traces=NORMAL_TRACES,
            wire_flows=NORMAL_FLOWS,
            adapter=ReferenceSurfaceDiscoveryAdapter(),
        )
        self.assertTrue(result.detected_anywhere)
        self.assertTrue(all(d.detected for d in result.per_surface))

    def test_ghost_blind_on_hook_detected_on_wire(self) -> None:
        result = detect_agent(
            agent_id="ghost",
            proxy_traces=[],
            wire_flows=GHOST_FLOWS,
            adapter=ReferenceSurfaceDiscoveryAdapter(),
        )
        self.assertTrue(result.detected_anywhere)  # wire saved us
        by_surface = {d.surface: d.detected for d in result.per_surface}
        self.assertFalse(by_surface[ObservationSurface.HOOK_SDK])
        self.assertTrue(by_surface[ObservationSurface.EBPF_WIRE])

    def test_fully_invisible_agent_is_a_failure(self) -> None:
        result = detect_agent(
            agent_id="vanished",
            proxy_traces=[],
            wire_flows=[],
            adapter=ReferenceSurfaceDiscoveryAdapter(),
        )
        self.assertFalse(result.detected_anywhere)  # the thesis failure


if __name__ == "__main__":
    unittest.main()
```

**Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m unittest tests.test_surface_detect -v`
Expected: FAIL (`ModuleNotFoundError`).

**Step 3: Write minimal implementation**

```python
# recette/surface/detect.py
"""Per-surface discovery seam + reference oracle.

``SurfaceDiscoveryAdapter`` is the protocol a real discovery tool (RailNode)
implements -- given what is visible on one surface, does it detect an agent?
``ReferenceSurfaceDiscoveryAdapter`` is the correct offline oracle (detected iff
anything is visible). ``detect_agent`` runs every surface and aggregates: an
agent detected on NO surface is the thesis failure (founding doc, sec. 0).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from recette.adapters import DiscoveryResult

from .surfaces import ObservationSurface, SurfaceObservation, project_surfaces


@runtime_checkable
class SurfaceDiscoveryAdapter(Protocol):
    def detect_on(self, observation: SurfaceObservation) -> DiscoveryResult: ...


class ReferenceSurfaceDiscoveryAdapter:
    """Correct oracle: an agent is detected on a surface iff something is visible."""

    def detect_on(self, observation: SurfaceObservation) -> DiscoveryResult:
        return DiscoveryResult(detected=bool(observation.visible), signals=list(observation.visible))


@dataclass(frozen=True)
class SurfaceDetection:
    surface: ObservationSurface
    detected: bool


@dataclass(frozen=True)
class AgentDetection:
    agent_id: str
    per_surface: tuple[SurfaceDetection, ...]
    detected_anywhere: bool


def detect_agent(
    *,
    agent_id: str,
    proxy_traces: list[dict],
    wire_flows: list[dict],
    adapter: SurfaceDiscoveryAdapter,
) -> AgentDetection:
    """Project the run, run the adapter on each surface, aggregate (pure, I4)."""
    surfaces = project_surfaces(proxy_traces=proxy_traces, wire_flows=wire_flows)
    per_surface = tuple(
        SurfaceDetection(surface=surface, detected=adapter.detect_on(obs).detected)
        for surface, obs in sorted(surfaces.items(), key=lambda kv: kv[0].value)
    )
    return AgentDetection(
        agent_id=agent_id,
        per_surface=per_surface,
        detected_anywhere=any(d.detected for d in per_surface),
    )
```

**Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m unittest tests.test_surface_detect -v`
Expected: PASS (5 tests).

**Step 5: Commit**

```bash
git add recette/surface/detect.py tests/test_surface_detect.py
git commit -m "feat(surface): SurfaceDiscoveryAdapter seam + reference oracle + detect_agent"
```

---

## Task 3: Detection scorecard -- per-surface rate + false-negative gate

**Files:**
- Create: `recette/surface/scorecard.py`
- Test: `tests/test_surface_scorecard.py`

**Step 1: Write the failing test**

```python
# tests/test_surface_scorecard.py
"""Detection scorecard: per-surface detection rate + the false-negative gate
(any agent detected on no surface fails the recette)."""
from __future__ import annotations

import unittest

from recette.surface.detect import ReferenceSurfaceDiscoveryAdapter, detect_agent
from recette.surface.scorecard import DetectionScorecard, score_detections
from recette.surface.surfaces import ObservationSurface

NORMAL = detect_agent(
    agent_id="pr-bot",
    proxy_traces=[{"action_type": "open_pr", "resource": "acme/web#42"}],
    wire_flows=[{"seq": 0, "method": "POST", "host": "api.github.com", "port": 443, "path": "/p"}],
    adapter=ReferenceSurfaceDiscoveryAdapter(),
)
GHOST = detect_agent(
    agent_id="ghost",
    proxy_traces=[],
    wire_flows=[{"seq": 0, "method": "POST", "host": "shadow-db", "port": 5432, "path": "/w"}],
    adapter=ReferenceSurfaceDiscoveryAdapter(),
)
VANISHED = detect_agent(
    agent_id="vanished", proxy_traces=[], wire_flows=[], adapter=ReferenceSurfaceDiscoveryAdapter()
)


class TestScorecard(unittest.TestCase):
    def test_all_detected_anywhere_passes(self) -> None:
        card = score_detections([NORMAL, GHOST])
        self.assertTrue(card.ok)
        self.assertEqual(card.false_negatives, ())

    def test_a_vanished_agent_is_a_false_negative(self) -> None:
        card = score_detections([NORMAL, VANISHED])
        self.assertFalse(card.ok)
        self.assertEqual(card.false_negatives, ("vanished",))

    def test_per_surface_rate_exposes_the_hook_blind_spot(self) -> None:
        card = score_detections([NORMAL, GHOST])
        # 2 agents; hook sees only the normal one (1/2), wire sees both (2/2).
        self.assertEqual(card.detected_per_surface[ObservationSurface.HOOK_SDK.value], 1)
        self.assertEqual(card.detected_per_surface[ObservationSurface.EBPF_WIRE.value], 2)
        self.assertEqual(card.total_agents, 2)

    def test_scorecard_is_deterministic(self) -> None:
        self.assertEqual(score_detections([NORMAL, GHOST]), score_detections([NORMAL, GHOST]))


if __name__ == "__main__":
    unittest.main()
```

**Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m unittest tests.test_surface_scorecard -v`
Expected: FAIL (`ModuleNotFoundError`).

**Step 3: Write minimal implementation**

```python
# recette/surface/scorecard.py
"""Aggregate per-agent detections into a detection scorecard (pure, I4).

``ok`` is True iff EVERY agent is detected on at least one surface -- an agent
detected nowhere is a false negative and the thesis failure (founding doc sec. 0:
"si l'outil ne voit pas les agents, c'est un echec"). ``detected_per_surface``
exposes the blind spot of each surface (the hook surface misses the ghost).
"""
from __future__ import annotations

from dataclasses import dataclass

from .detect import AgentDetection


@dataclass(frozen=True)
class DetectionScorecard:
    ok: bool
    total_agents: int
    detected_per_surface: dict[str, int]
    false_negatives: tuple[str, ...]


def score_detections(detections: list[AgentDetection]) -> DetectionScorecard:
    per_surface: dict[str, int] = {}
    false_negatives: list[str] = []
    for det in detections:
        for d in det.per_surface:
            if d.detected:
                per_surface[d.surface.value] = per_surface.get(d.surface.value, 0) + 1
        if not det.detected_anywhere:
            false_negatives.append(det.agent_id)
    return DetectionScorecard(
        ok=(false_negatives == []),
        total_agents=len(detections),
        detected_per_surface=dict(sorted(per_surface.items())),
        false_negatives=tuple(sorted(false_negatives)),
    )
```

**Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m unittest tests.test_surface_scorecard -v`
Expected: PASS (4 tests).

**Step 5: Commit**

```bash
git add recette/surface/scorecard.py tests/test_surface_scorecard.py
git commit -m "feat(surface): detection scorecard -- per-surface rate + false-negative gate"
```

---

## Task 4: Reference subjects -- corpus fixtures + ground-truth consistency

**Files:**
- Create: `corpus/surface/pr-bot-sdk/run.json` (positive: visible everywhere)
- Create: `corpus/surface/pr-bot-sdk/ground-truth.json`
- Create: `corpus/surface/ghost-direct-db/run.json` (ghost: wire-only)
- Create: `corpus/surface/ghost-direct-db/ground-truth.json`
- Create: `recette/surface/corpus.py` (loader)
- Test: `tests/test_surface_corpus.py`

**Step 1: Write the failing test**

```python
# tests/test_surface_corpus.py
"""The surface corpus subjects: the reference adapter must reproduce each
subject's ground-truth per-surface detection exactly (self-consistency)."""
from __future__ import annotations

import unittest

from recette.surface.corpus import load_surface_subjects
from recette.surface.detect import ReferenceSurfaceDiscoveryAdapter, detect_agent


class TestSurfaceCorpus(unittest.TestCase):
    def test_two_subjects_load(self) -> None:
        subjects = load_surface_subjects()
        ids = sorted(s["agent_id"] for s in subjects)
        self.assertEqual(ids, ["ghost-direct-db", "pr-bot-sdk"])

    def test_reference_adapter_matches_each_ground_truth(self) -> None:
        for subject in load_surface_subjects():
            result = detect_agent(
                agent_id=subject["agent_id"],
                proxy_traces=subject["run"]["proxy_traces"],
                wire_flows=subject["run"]["wire_flows"],
                adapter=ReferenceSurfaceDiscoveryAdapter(),
            )
            expected = subject["ground_truth"]["expected"]
            self.assertEqual(
                result.detected_anywhere,
                expected["detected_anywhere"],
                f"{subject['agent_id']}: detected_anywhere mismatch",
            )
            by_surface = {d.surface.value: d.detected for d in result.per_surface}
            for surface, want in expected["per_surface"].items():
                self.assertEqual(by_surface[surface], want, f"{subject['agent_id']}:{surface}")

    def test_ghost_is_a_hook_blind_spot(self) -> None:
        ghost = next(s for s in load_surface_subjects() if s["agent_id"] == "ghost-direct-db")
        exp = ghost["ground_truth"]["expected"]["per_surface"]
        self.assertFalse(exp["hook_sdk"])
        self.assertTrue(exp["ebpf_wire"])


if __name__ == "__main__":
    unittest.main()
```

**Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m unittest tests.test_surface_corpus -v`
Expected: FAIL (`ModuleNotFoundError: recette.surface.corpus`).

**Step 3: Write the fixtures and the loader**

```json
// corpus/surface/pr-bot-sdk/run.json
{
  "proxy_traces": [
    {"action_type": "open_pr", "resource": "acme/web#42"}
  ],
  "wire_flows": [
    {"seq": 0, "method": "POST", "host": "api.github.com", "port": 443, "path": "/repos/acme/web/pulls"}
  ]
}
```

```json
// corpus/surface/pr-bot-sdk/ground-truth.json
{
  "agent_id": "pr-bot-sdk",
  "note": "A well-behaved PR bot acting through the SDK: visible on hook AND wire.",
  "expected": {
    "detected_anywhere": true,
    "per_surface": {
      "hook_subprocess": true,
      "hook_mcp": true,
      "hook_sdk": true,
      "ebpf_wire": true
    }
  }
}
```

```json
// corpus/surface/ghost-direct-db/run.json
{
  "proxy_traces": [],
  "wire_flows": [
    {"seq": 0, "method": "POST", "host": "shadow-db.acme.internal", "port": 5432, "path": "/write"}
  ]
}
```

```json
// corpus/surface/ghost-direct-db/ground-truth.json
{
  "agent_id": "ghost-direct-db",
  "note": "Ghost agent: native egress to a DB, bypasses the SDK. Invisible on the hook surface, caught only on the wire/eBPF surface. The keystone of the thesis.",
  "expected": {
    "detected_anywhere": true,
    "per_surface": {
      "hook_subprocess": false,
      "hook_mcp": false,
      "hook_sdk": false,
      "ebpf_wire": true
    }
  }
}
```

```python
# recette/surface/corpus.py
"""Load the surface-detection corpus subjects (run view + ground-truth).

Each subject lives in corpus/surface/<slug>/ as run.json (proxy_traces +
wire_flows) and ground-truth.json (expected per-surface detection). Pure read,
sorted by slug for a stable order (I4).
"""
from __future__ import annotations

import json
from pathlib import Path

_CORPUS_ROOT = Path(__file__).resolve().parents[2] / "corpus" / "surface"


def load_surface_subjects(root: Path | None = None) -> list[dict]:
    base = root or _CORPUS_ROOT
    subjects: list[dict] = []
    for subject_dir in sorted(p for p in base.iterdir() if p.is_dir()):
        run = json.loads((subject_dir / "run.json").read_text())
        ground_truth = json.loads((subject_dir / "ground-truth.json").read_text())
        subjects.append(
            {"agent_id": ground_truth["agent_id"], "run": run, "ground_truth": ground_truth}
        )
    return subjects
```

**Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m unittest tests.test_surface_corpus -v`
Expected: PASS (3 tests).

**Step 5: Commit**

```bash
git add corpus/surface/ recette/surface/corpus.py tests/test_surface_corpus.py
git commit -m "feat(surface): reference subjects (sdk pr-bot + ghost-direct-db) + ground-truth consistency"
```

---

## Task 5: Replay determinism (I4) -- the scorecard is byte-stable

**Files:**
- Test: `tests/test_surface_replay.py`

**Step 1: Write the failing test**

```python
# tests/test_surface_replay.py
"""I4: running the full surface recette twice over the corpus yields a byte-
identical scorecard JSON. Guards against any non-determinism creeping in."""
from __future__ import annotations

import json
import unittest
from dataclasses import asdict

from recette.surface.corpus import load_surface_subjects
from recette.surface.detect import ReferenceSurfaceDiscoveryAdapter, detect_agent
from recette.surface.scorecard import score_detections


def _run_once() -> str:
    adapter = ReferenceSurfaceDiscoveryAdapter()
    detections = [
        detect_agent(
            agent_id=s["agent_id"],
            proxy_traces=s["run"]["proxy_traces"],
            wire_flows=s["run"]["wire_flows"],
            adapter=adapter,
        )
        for s in load_surface_subjects()
    ]
    return json.dumps(asdict(score_detections(detections)), sort_keys=True)


class TestSurfaceReplay(unittest.TestCase):
    def test_scorecard_is_byte_stable(self) -> None:
        self.assertEqual(_run_once(), _run_once())

    def test_corpus_has_no_false_negative(self) -> None:
        card = json.loads(_run_once())
        self.assertTrue(card["ok"])
        self.assertEqual(card["false_negatives"], [])


if __name__ == "__main__":
    unittest.main()
```

**Step 2: Run test to verify it fails or passes**

Run: `.venv/bin/python -m unittest tests.test_surface_replay -v`
Expected: PASS (the implementation from Tasks 1-4 already satisfies it). If it FAILS, a non-determinism leaked in (unsorted dict/iteration) -- fix the offending sort, do not weaken the test.

**Step 3: (only if red) fix the non-determinism**

Trace the diff between the two JSON dumps; the cause is an unsorted collection. Sort it at the source (projection or scorecard), never in the test.

**Step 4: Re-run**

Run: `.venv/bin/python -m unittest tests.test_surface_replay -v`
Expected: PASS (2 tests).

**Step 5: Commit**

```bash
git add tests/test_surface_replay.py
git commit -m "test(surface): I4 byte-stable detection scorecard over the corpus"
```

---

## Task 6: CLI subcommand + runbook + memory

**Files:**
- Modify: `recette/__main__.py` (add a `surface` subcommand)
- Create: `docs/runbooks/surface-detection-recette.md`
- Test: `tests/test_surface_cli.py`

**Step 1: Write the failing test**

```python
# tests/test_surface_cli.py
"""The `surface` CLI subcommand prints the detection scorecard and exits 0 when
the corpus has no false negative."""
from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stdout

from recette.__main__ import _cmd_surface


class TestSurfaceCli(unittest.TestCase):
    def test_cmd_surface_prints_scorecard_and_exits_zero(self) -> None:
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = _cmd_surface()
        self.assertEqual(rc, 0)
        payload = json.loads(buf.getvalue())
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["total_agents"], 2)


if __name__ == "__main__":
    unittest.main()
```

**Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m unittest tests.test_surface_cli -v`
Expected: FAIL (`ImportError: cannot import name '_cmd_surface'`).

**Step 3: Implement the subcommand**

In `recette/__main__.py`, add the command function (near the other `_cmd_*`) and wire an argparse subparser `surface` that calls it. Keep imports lazy inside the function to honor the existing cheap-import style:

```python
def _cmd_surface() -> int:
    """Run the per-surface detection recette over the corpus, print the scorecard."""
    import json
    from dataclasses import asdict

    from .surface.corpus import load_surface_subjects
    from .surface.detect import ReferenceSurfaceDiscoveryAdapter, detect_agent
    from .surface.scorecard import score_detections

    adapter = ReferenceSurfaceDiscoveryAdapter()
    detections = [
        detect_agent(
            agent_id=s["agent_id"],
            proxy_traces=s["run"]["proxy_traces"],
            wire_flows=s["run"]["wire_flows"],
            adapter=adapter,
        )
        for s in load_surface_subjects()
    ]
    card = score_detections(detections)
    print(json.dumps(asdict(card), sort_keys=True, indent=2))
    return 0 if card.ok else 1
```

Wire it where the other subparsers are declared (mirror the `discovery` subparser): add
`sub.add_parser("surface", help="per-surface detection recette (RailNode visibility)")`
and in the dispatch block add `if args.command == "surface": return _cmd_surface()`.

**Step 4: Run test + the command**

Run: `.venv/bin/python -m unittest tests.test_surface_cli -v`
Expected: PASS.
Run: `.venv/bin/python -m recette surface`
Expected: prints the scorecard JSON (`"ok": true`, `"total_agents": 2`), exit 0.

**Step 5: Write the runbook + commit**

Create `docs/runbooks/surface-detection-recette.md` summarizing: the thesis (sec. 0 of
the design), the 4 surfaces, the two views (ProxyTrace/WireFlow), the ghost keystone, how
to run (`python -m recette surface`), and how a real RailNode plugs in (implement
`SurfaceDiscoveryAdapter`, like `http_adapter.py` does for `SourceScanAdapter`).

```bash
git add recette/__main__.py tests/test_surface_cli.py docs/runbooks/surface-detection-recette.md
git commit -m "feat(surface): `recette surface` CLI scorecard + runbook"
```

Then add a memory pointer (outside the repo) summarizing the surface-detection recette and
linking `[[private-dns-resolver]]` / the lab memories, and update `MEMORY.md`.

---

## Task 7: Gates -- full suite + recette + lint/type, then push

**Step 1: Run every gate**

```bash
.venv/bin/python -m unittest discover -s tests
make recette
.venv-pyaudit/bin/ruff check recette/ tests/
.venv-pyaudit/bin/ruff format --check recette/ tests/
.venv-pyaudit/bin/mypy recette/
```

Expected: all green. Fix any failure at the source (not by weakening a test).

**Step 2: Confirm the new tests are collected**

Run: `.venv/bin/python -m unittest discover -s tests 2>&1 | tail -3`
Expected: the run count rose by the ~18 new tests; `OK`.

**Step 3: `git status` -- only your files**

Run: `git status --short`
Expected: clean except files YOU created this plan. If a foreign dirty file appears
(another session, R21), do NOT stage it.

**Step 4: Push (work on main)**

```bash
git fetch origin && git rev-list --left-right --count origin/main...HEAD
git push origin main
```

Expected: clean fast-forward.

---

## Done criteria

- `recette/surface/` builds the per-surface detection recette: pure projection (Task 1),
  adapter seam + reference oracle (Task 2), scorecard with the false-negative gate (Task 3),
  reference subjects incl. the ghost keystone (Task 4), I4 replay (Task 5), CLI + runbook
  (Task 6), all gates green (Task 7).
- The thesis is now a test: an agent detected on NO surface turns the scorecard RED.
- The ghost agent proves per-surface coverage matters: hook-blind, wire-detected.
- The real RailNode plugs in by implementing `SurfaceDiscoveryAdapter` -- the reference
  oracle is the template (mirrors `recette/adapters.py` + `recette/http_adapter.py`).
- No new dependency; everything stdlib + deterministic (I4); mono-axis subjects.

## Out of scope (explicit YAGNI)

- A live eBPF probe or a real mitmproxy capture in the loop (the corpus models the two
  views deterministically; live wiring is the smoke's job, a later task).
- Re-judging the 4 identification dimensions here (that lives in `recette/harness.py`;
  this plan is about DETECTION -- being seen -- not identification correctness).
- A real RailNode HTTP/gRPC adapter implementation (the seam is defined; wiring the actual
  Rust tool is a follow-up once its invocation interface is known).
```
