# Track U / U1 — Recette API layer (FastAPI) Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Expose every recette CLI capability over a FastAPI HTTP + WebSocket API, so the Track U console can list/register agents, launch/stop runs, stream run events live, and read scorecards — reusing the `recette` package directly with no business logic duplicated.

**Architecture:** A new `recette/api/` subpackage holds a FastAPI app factory (`create_app()`). A `RunManager` keeps in-memory `Run` objects; each launched run executes in a worker thread (so the event loop stays free) and pushes JSON event frames onto per-run subscriber queues. Identification/discovery runs reuse `recette.harness`/`recette.report` and emit one event per agent + a final scorecard frame; Lane B runs reuse `recette.lane_b.run_agent`, which gains two optional, side-effect-only hooks (`on_step`, `should_stop`) that preserve its existing deterministic behaviour. Config (registered Lane B agents + AI backends) persists to a single versioned JSON file (R5); secrets are never stored — provider keys resolve from env at run time (R8). Real-time transport is **WebSocket** (decision 2026-06-12, overrides the plan's SSE recommendation).

**Tech Stack:** Python 3.11, FastAPI + Starlette (WebSocket), uvicorn (server), httpx + `fastapi.testclient.TestClient` (tests), stdlib `unittest` (matches the repo), `threading` + `asyncio.Queue` for run streaming. New optional extra `[api]`; `[dev]` gains the same so the suite can exercise the API.

---

## Conventions for every task

- TDD: write the failing test first, run it red, implement minimally, run it green, commit.
- Tests are stdlib `unittest` under `tests/`, named `test_api_*.py`. API tests import FastAPI lazily and `skipUnless(_HAS_FASTAPI)` so the suite still runs where the `[api]` extra is absent.
- Run a single test: `python3 -m unittest tests.test_api_health -v`
- Full suite: `make test` (`python3 -m unittest discover -s tests`)
- Gates (must stay green): `make gates` → ruff check + ruff format --check + mypy + bandit, all over `recette` (covers `recette/api/` automatically).
- The core `recette` package MUST NEVER import `recette.api` (keeps FastAPI optional). Only the reverse.
- Commit after each task with a `feat(api):` / `test(api):` / `chore:` message.

---

## Task 0: Packaging + app skeleton + /health

**Files:**
- Modify: `pyproject.toml` (add `[api]` extra, extend `[dev]`, add `recette.api` to packages, add mypy overrides for fastapi/starlette/uvicorn)
- Create: `recette/api/__init__.py`
- Create: `recette/api/app.py`
- Create: `tests/test_api_health.py`

**Step 1: Write the failing test**

```python
# tests/test_api_health.py
"""U1: app factory + health endpoint."""

from __future__ import annotations

import unittest

try:
    from fastapi.testclient import TestClient

    from recette.api.app import create_app

    _HAS_FASTAPI = True
except ImportError:  # pragma: no cover - exercised only without the [api] extra
    _HAS_FASTAPI = False


@unittest.skipUnless(_HAS_FASTAPI, "requires the [api] extra (fastapi)")
class TestHealth(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(create_app())

    def test_health_ok(self) -> None:
        resp = self.client.get("/health")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {"status": "ok"})
```

**Step 2: Run it red**

Run: `python3 -m unittest tests.test_api_health -v`
Expected: FAIL — `ModuleNotFoundError: recette.api` (or skipped if fastapi missing → install `[dev]` first: `python3 -m pip install -e '.[dev]'`).

**Step 3: pyproject changes**

In `pyproject.toml` add to `[project.optional-dependencies]`:

```toml
# Track U console API layer (FastAPI). The core recette/CLI need none of this.
api = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.30",
]
```

Append the API + test deps to the existing `dev` list: `"fastapi>=0.115"`, `"uvicorn[standard]>=0.30"`, `"httpx>=0.27"`.

Change `[tool.setuptools]`:

```toml
[tool.setuptools]
packages = ["recette", "recette.api"]
```

Add a mypy override so gates pass without the extra installed in `.venv-pyaudit`:

```toml
[[tool.mypy.overrides]]
# FastAPI/uvicorn are the optional [api] extra; not present in the audit venv where mypy runs.
module = ["fastapi", "fastapi.*", "starlette", "starlette.*", "uvicorn", "uvicorn.*"]
ignore_missing_imports = true
```

**Step 4: Implement the skeleton**

```python
# recette/api/__init__.py
"""Track U / U1 — FastAPI layer over the recette package (optional [api] extra)."""
```

```python
# recette/api/app.py
"""U1 app factory. Wires the routers onto a FastAPI instance.

The core recette package never imports this module — FastAPI stays an optional extra.
"""

from __future__ import annotations

from fastapi import FastAPI


def create_app() -> FastAPI:
    app = FastAPI(title="AgentRail Recette API", version="0.1.0")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app
```

**Step 5: Run it green**

Run: `python3 -m unittest tests.test_api_health -v`
Expected: PASS.

**Step 6: Gates + commit**

Run: `make gates` → expect `gates: PASS`.

```bash
git add pyproject.toml recette/api/__init__.py recette/api/app.py tests/test_api_health.py
git commit -m "feat(api): U1 app factory + /health + [api] extra"
```

---

## Task 1: Config store (versioned, atomic, secret-free)

**Files:**
- Create: `recette/api/config_store.py`
- Create: `tests/test_api_config_store.py`

**Design:** One JSON file, default `config/agentrail.config.json` at the repo root, override via env `AGENTRAIL_CONFIG_PATH`. Shape:

```json
{"schema_version": "1.0", "agents": [], "ai_backends": []}
```

- `agents[]` (Lane B): `{id, principal, target_system, goal, capability_scope: [..], ai_backend_id, runtime}` where `runtime ∈ {"lab","real"}`.
- `ai_backends[]`: `{id, provider, model}` — **no keys** (R8: keys come from env at run time).
- Writes are atomic (write temp + `os.replace`). Unknown/missing file → returns the empty default (does not create until first write).

**Step 1: Write the failing test**

```python
# tests/test_api_config_store.py
"""U1: versioned config store for Lane B agents + AI backends."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from recette.api.config_store import ConfigStore


class TestConfigStore(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "cfg.json"
        self.store = ConfigStore(self.path)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_missing_file_reads_empty_default(self) -> None:
        cfg = self.store.read()
        self.assertEqual(cfg["schema_version"], "1.0")
        self.assertEqual(cfg["agents"], [])
        self.assertEqual(cfg["ai_backends"], [])
        self.assertFalse(self.path.exists())  # read never creates

    def test_add_agent_persists_and_roundtrips(self) -> None:
        agent = {
            "id": "a1",
            "principal": "acme-bot@github",
            "target_system": "github",
            "goal": "bump deps",
            "capability_scope": ["read_repo", "open_pr"],
            "ai_backend_id": "b1",
            "runtime": "lab",
        }
        self.store.add_agent(agent)
        on_disk = json.loads(self.path.read_text())
        self.assertEqual(on_disk["agents"], [agent])
        # a fresh store over the same file sees it
        self.assertEqual(ConfigStore(self.path).get_agent("a1"), agent)

    def test_add_ai_backend_rejects_key_fields(self) -> None:
        with self.assertRaises(ValueError):
            self.store.add_ai_backend({"id": "b1", "provider": "anthropic",
                                       "model": "x", "api_key": "sekret"})

    def test_duplicate_id_rejected(self) -> None:
        self.store.add_ai_backend({"id": "b1", "provider": "openai", "model": "gpt"})
        with self.assertRaises(ValueError):
            self.store.add_ai_backend({"id": "b1", "provider": "openai", "model": "gpt"})

    def test_update_and_delete_agent(self) -> None:
        self.store.add_agent({"id": "a1", "principal": "p", "target_system": "github",
                              "goal": "g", "capability_scope": [], "ai_backend_id": "b1",
                              "runtime": "lab"})
        self.store.update_agent("a1", {"goal": "g2"})
        self.assertEqual(self.store.get_agent("a1")["goal"], "g2")
        self.store.delete_agent("a1")
        self.assertIsNone(self.store.get_agent("a1"))
```

**Step 2: Run it red** — `python3 -m unittest tests.test_api_config_store -v` → FAIL (no module).

**Step 3: Implement**

```python
# recette/api/config_store.py
"""U1 config store: one versioned JSON file for Lane B agents + AI backends.

Secrets are never stored (R8) — AI-backend entries carry only provider + model; the
provider key is resolved from env at run time. Writes are atomic (temp + os.replace).
The file is created lazily on first write; reads of a missing file return the empty default.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

SCHEMA_VERSION = "1.0"
_FORBIDDEN_BACKEND_FIELDS = {"api_key", "key", "token", "secret"}
_RUNTIMES = {"lab", "real"}


def _default() -> dict:
    return {"schema_version": SCHEMA_VERSION, "agents": [], "ai_backends": []}


def default_config_path() -> Path:
    env = os.environ.get("AGENTRAIL_CONFIG_PATH")
    if env:
        return Path(env)
    return Path(__file__).resolve().parent.parent.parent / "config" / "agentrail.config.json"


class ConfigStore:
    def __init__(self, path: Path | str | None = None) -> None:
        self.path = Path(path) if path is not None else default_config_path()

    def read(self) -> dict:
        if not self.path.exists():
            return _default()
        cfg = json.loads(self.path.read_text(encoding="utf-8"))
        cfg.setdefault("schema_version", SCHEMA_VERSION)
        cfg.setdefault("agents", [])
        cfg.setdefault("ai_backends", [])
        return cfg

    def _write(self, cfg: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp, self.path)

    # --- agents ---
    def get_agent(self, agent_id: str) -> dict | None:
        return next((a for a in self.read()["agents"] if a["id"] == agent_id), None)

    def add_agent(self, agent: dict) -> dict:
        if agent.get("runtime") not in _RUNTIMES:
            raise ValueError(f"runtime must be one of {_RUNTIMES}")
        cfg = self.read()
        if any(a["id"] == agent["id"] for a in cfg["agents"]):
            raise ValueError(f"agent id {agent['id']!r} already exists")
        cfg["agents"].append(agent)
        self._write(cfg)
        return agent

    def update_agent(self, agent_id: str, patch: dict) -> dict:
        cfg = self.read()
        for a in cfg["agents"]:
            if a["id"] == agent_id:
                a.update(patch)
                self._write(cfg)
                return a
        raise ValueError(f"no agent {agent_id!r}")

    def delete_agent(self, agent_id: str) -> None:
        cfg = self.read()
        cfg["agents"] = [a for a in cfg["agents"] if a["id"] != agent_id]
        self._write(cfg)

    # --- ai backends ---
    def get_ai_backend(self, backend_id: str) -> dict | None:
        return next((b for b in self.read()["ai_backends"] if b["id"] == backend_id), None)

    def add_ai_backend(self, backend: dict) -> dict:
        leaked = _FORBIDDEN_BACKEND_FIELDS & set(backend)
        if leaked:
            raise ValueError(f"secrets must not be stored (R8): drop {sorted(leaked)}")
        cfg = self.read()
        if any(b["id"] == backend["id"] for b in cfg["ai_backends"]):
            raise ValueError(f"ai_backend id {backend['id']!r} already exists")
        cfg["ai_backends"].append(backend)
        self._write(cfg)
        return backend

    def delete_ai_backend(self, backend_id: str) -> None:
        cfg = self.read()
        cfg["ai_backends"] = [b for b in cfg["ai_backends"] if b["id"] != backend_id]
        self._write(cfg)
```

**Step 4: Run it green** — `python3 -m unittest tests.test_api_config_store -v` → PASS.

**Step 5: Gates + commit**

```bash
git add recette/api/config_store.py tests/test_api_config_store.py
git commit -m "feat(api): U1 versioned secret-free config store"
```

---

## Task 2: Config CRUD endpoints (U4 backend)

**Files:**
- Create: `recette/api/routers/__init__.py`
- Create: `recette/api/routers/config.py`
- Modify: `recette/api/app.py` (include the config router, hold a `ConfigStore` on `app.state`)
- Create: `tests/test_api_config_routes.py`

**Endpoints:**
- `GET /config/agents` → list; `POST /config/agents` → create (201); `PUT /config/agents/{id}` → patch; `DELETE /config/agents/{id}` (204)
- `GET /config/ai-backends`, `POST /config/ai-backends`, `DELETE /config/ai-backends/{id}`
- `ValueError` from the store → HTTP 400 (duplicate / secret leak / bad runtime); missing id on PUT/DELETE agent → 404.

**Step 1: Write the failing test**

```python
# tests/test_api_config_routes.py
"""U1/U4: config CRUD over HTTP."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

try:
    from fastapi.testclient import TestClient

    from recette.api.app import create_app
    from recette.api.config_store import ConfigStore

    _HAS_FASTAPI = True
except ImportError:  # pragma: no cover
    _HAS_FASTAPI = False


@unittest.skipUnless(_HAS_FASTAPI, "requires the [api] extra (fastapi)")
class TestConfigRoutes(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        store = ConfigStore(Path(self.tmp.name) / "cfg.json")
        self.client = TestClient(create_app(config_store=store))

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_ai_backend_crud(self) -> None:
        self.assertEqual(self.client.get("/config/ai-backends").json(), [])
        r = self.client.post("/config/ai-backends",
                             json={"id": "b1", "provider": "anthropic", "model": "claude"})
        self.assertEqual(r.status_code, 201)
        self.assertEqual(len(self.client.get("/config/ai-backends").json()), 1)
        self.assertEqual(self.client.delete("/config/ai-backends/b1").status_code, 204)

    def test_post_secret_rejected_400(self) -> None:
        r = self.client.post("/config/ai-backends",
                             json={"id": "b", "provider": "openai", "model": "x",
                                   "api_key": "leak"})
        self.assertEqual(r.status_code, 400)

    def test_agent_crud_and_404(self) -> None:
        self.client.post("/config/ai-backends",
                         json={"id": "b1", "provider": "anthropic", "model": "c"})
        r = self.client.post("/config/agents", json={
            "id": "a1", "principal": "p", "target_system": "github", "goal": "g",
            "capability_scope": ["read_repo"], "ai_backend_id": "b1", "runtime": "lab"})
        self.assertEqual(r.status_code, 201)
        r = self.client.put("/config/agents/a1", json={"goal": "g2"})
        self.assertEqual(r.json()["goal"], "g2")
        self.assertEqual(self.client.put("/config/agents/nope", json={"goal": "x"}).status_code, 404)
        self.assertEqual(self.client.delete("/config/agents/a1").status_code, 204)
```

**Step 2: Run it red** → FAIL (no router / `create_app` has no `config_store` kwarg).

**Step 3: Implement the router**

```python
# recette/api/routers/__init__.py
"""U1 API routers."""
```

```python
# recette/api/routers/config.py
"""U1/U4: config CRUD endpoints (Lane B agents + AI backends)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response

router = APIRouter(prefix="/config", tags=["config"])


def _store(request: Request):
    return request.app.state.config_store


@router.get("/agents")
def list_agents(request: Request) -> list[dict]:
    return _store(request).read()["agents"]


@router.post("/agents", status_code=201)
def create_agent(request: Request, agent: dict[str, Any]) -> dict:
    try:
        return _store(request).add_agent(agent)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put("/agents/{agent_id}")
def update_agent(request: Request, agent_id: str, patch: dict[str, Any]) -> dict:
    try:
        return _store(request).update_agent(agent_id, patch)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/agents/{agent_id}", status_code=204)
def delete_agent(request: Request, agent_id: str) -> Response:
    _store(request).delete_agent(agent_id)
    return Response(status_code=204)


@router.get("/ai-backends")
def list_ai_backends(request: Request) -> list[dict]:
    return _store(request).read()["ai_backends"]


@router.post("/ai-backends", status_code=201)
def create_ai_backend(request: Request, backend: dict[str, Any]) -> dict:
    try:
        return _store(request).add_ai_backend(backend)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/ai-backends/{backend_id}", status_code=204)
def delete_ai_backend(request: Request, backend_id: str) -> Response:
    _store(request).delete_ai_backend(backend_id)
    return Response(status_code=204)
```

Update `create_app` in `recette/api/app.py`:

```python
from __future__ import annotations

from fastapi import FastAPI

from .config_store import ConfigStore
from .routers import config as config_router


def create_app(*, config_store: ConfigStore | None = None) -> FastAPI:
    app = FastAPI(title="AgentRail Recette API", version="0.1.0")
    app.state.config_store = config_store or ConfigStore()

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(config_router.router)
    return app
```

**Step 4: Run it green** — `python3 -m unittest tests.test_api_config_routes -v` → PASS.

**Step 5: Gates + commit**

```bash
git add recette/api/routers/__init__.py recette/api/routers/config.py recette/api/app.py tests/test_api_config_routes.py
git commit -m "feat(api): U1 config CRUD endpoints (agents + ai-backends)"
```

---

## Task 3: Agent catalog — GET /agents

**Files:**
- Create: `recette/api/catalog.py`
- Create: `recette/api/routers/catalog.py`
- Modify: `recette/api/app.py` (include router)
- Create: `tests/test_api_catalog.py`

**Design:** Read-only catalog of what can be run, reusing the harness discovery helpers (no new file walking logic):
- `identification`: every Lane A agent dir → `{agent_id, category, dir}` from `recette.harness.discover_agent_dirs` + `recette.manifest.load_ground_truth` for category.
- `discovery`: per surface, the repo slugs from `recette.discovery_harness.discover_repo_dirs(SURFACE_CORPUS[s])`.
- `lane_b`: registered agents from the config store.

**Step 1: Write the failing test**

```python
# tests/test_api_catalog.py
"""U1: GET /agents catalog reuses the harness corpus discovery."""

from __future__ import annotations

import unittest

try:
    from fastapi.testclient import TestClient

    from recette.api.app import create_app

    _HAS_FASTAPI = True
except ImportError:  # pragma: no cover
    _HAS_FASTAPI = False


@unittest.skipUnless(_HAS_FASTAPI, "requires the [api] extra (fastapi)")
class TestCatalog(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(create_app())

    def test_catalog_lists_corpus(self) -> None:
        body = self.client.get("/agents").json()
        ident_ids = {a["agent_id"] for a in body["identification"]}
        # known Lane A golden from corpus/agents/correct
        self.assertIn("gh-issue-triager", ident_ids)
        # discovery surfaces include github with the readonly-reporter repo slug
        self.assertIn("github", body["discovery"])
        self.assertIn("gh-readonly-reporter", body["discovery"]["github"])
        self.assertIn("lane_b", body)
```

**Step 2: Run it red** → FAIL (no /agents).

**Step 3: Implement**

```python
# recette/api/catalog.py
"""U1: read-only catalog of runnable subjects, built from the existing corpus helpers."""

from __future__ import annotations

from ..discovery_harness import SURFACE_CORPUS, SURFACE_ORDER, discover_repo_dirs
from ..harness import discover_agent_dirs
from ..manifest import load_ground_truth
from .config_store import ConfigStore


def build_catalog(store: ConfigStore) -> dict:
    identification = []
    for d in discover_agent_dirs():
        gt = load_ground_truth(d / "ground-truth.json")
        identification.append(
            {"agent_id": gt["agent_id"], "category": gt["category"], "dir": d.name}
        )
    discovery = {
        s: [d.name for d in discover_repo_dirs(SURFACE_CORPUS[s])]
        for s in SURFACE_ORDER
        if discover_repo_dirs(SURFACE_CORPUS[s])
    }
    return {
        "identification": identification,
        "discovery": discovery,
        "lane_b": store.read()["agents"],
    }
```

```python
# recette/api/routers/catalog.py
"""U1: GET /agents catalog router."""

from __future__ import annotations

from fastapi import APIRouter, Request

from ..catalog import build_catalog

router = APIRouter(tags=["catalog"])


@router.get("/agents")
def get_catalog(request: Request) -> dict:
    return build_catalog(request.app.state.config_store)
```

Add `from .routers import catalog as catalog_router` and `app.include_router(catalog_router.router)` in `create_app`.

**Step 4: Run it green** → PASS.

**Step 5: Gates + commit**

```bash
git add recette/api/catalog.py recette/api/routers/catalog.py recette/api/app.py tests/test_api_catalog.py
git commit -m "feat(api): U1 GET /agents catalog over the corpus"
```

---

## Task 4: Lane B core hooks (on_step + should_stop) — deterministic, backward-compatible

**Files:**
- Modify: `recette/lane_b.py:39-85` (add two optional params)
- Modify: `tests/test_lane_b.py` (add hook + stop tests; existing tests must still pass unchanged)

**Why:** Streaming live Lane B steps and cooperative stop need observation points in the loop. Both params default to `None`, so existing behaviour and determinism are byte-for-byte unchanged (the existing `test_lane_b` suite is the regression guard).

**Step 1: Write the failing tests** (append to `tests/test_lane_b.py`)

```python
    def test_on_step_called_per_recorded_step(self):
        seen = []
        run_agent(
            agent_id="a1", principal="p", target_system="github", goal="g",
            capability_scope=["read_repo", "open_pr"], llm=_script(),
            on_step=lambda i, step: seen.append((i, step.action is not None)),
        )
        # 2 tool-call steps (action) + 1 final step (no action)
        self.assertEqual(seen, [(0, True), (1, True), (2, False)])

    def test_should_stop_halts_before_next_step(self):
        result = run_agent(
            agent_id="a1", principal="p", target_system="github", goal="g",
            capability_scope=["read_repo", "open_pr"], llm=_script(),
            should_stop=lambda: True,  # stop before the very first step
        )
        self.assertEqual(result.actions, [])
        self.assertEqual(result.recording.steps, [])
```

**Step 2: Run it red** — `python3 -m unittest tests.test_lane_b -v` → 2 FAIL (`run_agent() got an unexpected keyword argument`).

**Step 3: Implement** — change the signature and loop in `recette/lane_b.py`:

```python
from collections.abc import Callable
...
def run_agent(
    *,
    agent_id: str,
    principal: str,
    target_system: str,
    goal: str,
    capability_scope: list[str],
    llm: LlmBackend,
    forge: GitForge | None = None,
    provider: str = "stub",
    model: str = "",
    max_steps: int = 10,
    on_step: Callable[[int, RecordedStep], None] | None = None,
    should_stop: Callable[[], bool] | None = None,
) -> LaneBResult:
```

In the loop, gate on stop at the top and emit after appending each step:

```python
    for i in range(max_steps):
        if should_stop is not None and should_stop():
            break
        decision = llm.decide(system=system, history=history, tools=tools)
        if not decision.is_tool_call:
            step = RecordedStep(decision=decision, action=None)
            recording.steps.append(step)
            if on_step is not None:
                on_step(i, step)
            break
        action = execute_tool(
            forge, agent_id=agent_id, principal=principal,
            target_system=target_system, decision=decision,
        )
        actions.append(action)
        step = RecordedStep(decision=decision, action=action.to_dict())
        recording.steps.append(step)
        if on_step is not None:
            on_step(i, step)
        history.append(Message("assistant", f"calling {decision.tool_name}"))
        history.append(Message("tool", _result_text(action), tool_name=decision.tool_name))
```

**Step 4: Run it green** — `python3 -m unittest tests.test_lane_b -v` → all PASS (new + pre-existing).

**Step 5: Commit**

```bash
git add recette/lane_b.py tests/test_lane_b.py
git commit -m "feat(lane-b): optional on_step/should_stop hooks (default None, behaviour unchanged)"
```

---

## Task 5: RunManager — in-memory runs, threaded execution, event frames

**Files:**
- Create: `recette/api/runs.py`
- Create: `tests/test_api_runs.py`

**Design:**
- `Run`: `id, kind, status, params, events: list[dict], result: dict | None, error: str | None`. `status ∈ {pending, running, completed, failed, stopped}`. Terminal = `{completed, failed, stopped}`.
- Event frame: `{"seq": int, "type": str, "data": {...}}`. Types: `start`, `agent_result` (identification/discovery per subject), `step` (Lane B per step), `scorecard`/`result` (final payload), `end` (`{status}`), `error`.
- `RunManager.create(kind, params) -> Run` (status `pending`); `start(run, runner)` runs `runner(emit, should_stop)` in a worker thread (`threading.Thread`); `emit(type, data)` appends to `run.events` and notifies async subscribers; `stop(run_id)` sets the stop flag.
- Subscriber bridge for WebSocket: `subscribe(run_id) -> asyncio.Queue`; the manager records the running loop via `asyncio.get_running_loop()` when a subscriber attaches and uses `loop.call_soon_threadsafe(queue.put_nowait, frame)` from the worker thread. Already-buffered events are replayed into a new subscriber queue on subscribe.
- This task tests the **synchronous core** (create/emit/run-to-completion/stop) without the event loop; the WebSocket bridge is Task 7.

**Runners** (pure functions, reuse recette):
- `identification_runner`: iterate `discover_agent_dirs()`, call `recette.harness.run_agent(dir, discovery=ReferenceDiscoveryAdapter(), identification=ReferenceIdentificationAdapter())`, emit `agent_result` per agent (`{agent_id, passed, predicted_verdict, expected_verdict}`), honour `should_stop` between agents, then build a `Scorecard`, emit `scorecard` with its metrics.
- `discovery_runner(surface)`: similar, reuse `run_discovery_recette` per surface (emit one `scorecard` per surface; for "all", loop surfaces).
- `lane_b_runner(agent_cfg, llm)`: call `recette.lane_b.run_agent(..., on_step=emit_step, should_stop=should_stop)`; emit `result` with the action log + recording dict.

**Step 1: Write the failing test**

```python
# tests/test_api_runs.py
"""U1: RunManager core (threaded run, event frames, stop) — no event loop here."""

from __future__ import annotations

import unittest

from recette.api.runs import RunManager
from recette.api.runners import identification_runner


class TestRunManager(unittest.TestCase):
    def setUp(self) -> None:
        self.mgr = RunManager()

    def test_identification_run_completes_with_scorecard(self) -> None:
        run = self.mgr.create("identification", {})
        self.mgr.run_blocking(run, identification_runner)  # test helper: run inline, no thread
        self.assertEqual(run.status, "completed")
        types = [e["type"] for e in run.events]
        self.assertEqual(types[0], "start")
        self.assertIn("agent_result", types)
        self.assertEqual(types[-1], "end")
        scorecard = next(e for e in run.events if e["type"] == "scorecard")
        self.assertIn("passed", scorecard["data"])
        self.assertIn("total", scorecard["data"])

    def test_event_seq_is_monotonic(self) -> None:
        run = self.mgr.create("identification", {})
        self.mgr.run_blocking(run, identification_runner)
        seqs = [e["seq"] for e in run.events]
        self.assertEqual(seqs, sorted(seqs))
        self.assertEqual(len(seqs), len(set(seqs)))

    def test_stop_flag_halts_identification(self) -> None:
        run = self.mgr.create("identification", {})
        self.mgr.request_stop(run.id)  # stop before it starts
        self.mgr.run_blocking(run, identification_runner)
        self.assertEqual(run.status, "stopped")
```

Put the runners in a separate module so they import cleanly without FastAPI:

**Step 2: Run it red** → FAIL (no `recette.api.runs` / `recette.api.runners`).

**Step 3: Implement** `recette/api/runners.py` then `recette/api/runs.py`.

```python
# recette/api/runners.py
"""U1 run bodies — thin wrappers that reuse recette and emit event frames.

A runner has signature runner(params, emit, should_stop) -> None, where
emit(type: str, data: dict) records one frame and should_stop() -> bool is cooperative.
Runners never touch HTTP or asyncio — they are pure orchestration over recette.
"""

from __future__ import annotations

from collections.abc import Callable

from ..adapters import ReferenceDiscoveryAdapter, ReferenceIdentificationAdapter
from ..discovery_harness import SURFACE_CORPUS, SURFACE_ORDER, discover_repo_dirs
from ..discovery_harness import run_discovery_recette
from ..harness import discover_agent_dirs, run_agent as run_ident_agent
from ..scorecard import Scorecard

Emit = Callable[[str, dict], None]
ShouldStop = Callable[[], bool]


def identification_runner(params: dict, emit: Emit, should_stop: ShouldStop) -> None:
    disc = ReferenceDiscoveryAdapter()
    ident = ReferenceIdentificationAdapter()
    scorecard = Scorecard()
    for d in discover_agent_dirs():
        if should_stop():
            return
        result = run_ident_agent(d, discovery=disc, identification=ident)
        scorecard.add(result)
        emit("agent_result", {
            "agent_id": result.agent_id, "passed": result.passed,
            "predicted_verdict": result.predicted_verdict,
            "expected_verdict": result.expected_verdict,
        })
    emit("scorecard", _scorecard_data(scorecard))


def discovery_runner(params: dict, emit: Emit, should_stop: ShouldStop) -> None:
    surface = params.get("surface", "all")
    surfaces = (
        [s for s in SURFACE_ORDER if discover_repo_dirs(SURFACE_CORPUS[s])]
        if surface == "all" else [surface]
    )
    for s in surfaces:
        if should_stop():
            return
        sc = run_discovery_recette(corpus_root=SURFACE_CORPUS[s])
        emit("scorecard", {
            "surface": s, "total": sc.total, "passed": sc.passed_count,
            "false_positives": sc.false_positives, "false_negatives": sc.false_negatives,
            "all_passed": sc.all_passed,
        })


def _scorecard_data(sc: Scorecard) -> dict:
    return {
        "total": sc.total, "passed": sc.passed_count,
        "false_positives": sc.false_positives, "false_negatives": sc.false_negatives,
        "detection_rate": sc.detection_rate, "all_passed": sc.all_passed,
    }
```

```python
# recette/api/runs.py
"""U1 RunManager: in-memory runs executed in worker threads, emitting event frames.

A run's frames are buffered on the Run (so a late WebSocket subscriber can replay them)
and pushed live to any attached asyncio subscriber queues (the WS bridge, Task 7).
Run ids are uuid4 — operational identifiers, not recette ground-truth artifacts.
"""

from __future__ import annotations

import asyncio
import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field

Runner = Callable[[dict, Callable[[str, dict], None], Callable[[], bool]], None]
_TERMINAL = {"completed", "failed", "stopped"}


@dataclass
class Run:
    id: str
    kind: str
    params: dict
    status: str = "pending"
    events: list[dict] = field(default_factory=list)
    error: str | None = None
    _seq: int = 0
    _stop: threading.Event = field(default_factory=threading.Event)
    _lock: threading.Lock = field(default_factory=threading.Lock)
    # asyncio subscriber queues + the loop they live on (set by the WS bridge)
    _subscribers: list[asyncio.Queue] = field(default_factory=list)
    _loop: asyncio.AbstractEventLoop | None = None

    @property
    def terminal(self) -> bool:
        return self.status in _TERMINAL


class RunManager:
    def __init__(self) -> None:
        self._runs: dict[str, Run] = {}

    def create(self, kind: str, params: dict) -> Run:
        run = Run(id=uuid.uuid4().hex, kind=kind, params=params)
        self._runs[run.id] = run
        return run

    def get(self, run_id: str) -> Run | None:
        return self._runs.get(run_id)

    def request_stop(self, run_id: str) -> bool:
        run = self._runs.get(run_id)
        if run is None:
            return False
        run._stop.set()
        return True

    def _emit(self, run: Run, type_: str, data: dict) -> None:
        with run._lock:
            frame = {"seq": run._seq, "type": type_, "data": data}
            run._seq += 1
            run.events.append(frame)
            subs = list(run._subscribers)
            loop = run._loop
        for q in subs:
            if loop is not None:
                loop.call_soon_threadsafe(q.put_nowait, frame)

    def _execute(self, run: Run, runner: Runner) -> None:
        run.status = "running"
        self._emit(run, "start", {"kind": run.kind})
        try:
            runner(run.params, lambda t, d: self._emit(run, t, d), run._stop.is_set)
            run.status = "stopped" if run._stop.is_set() else "completed"
        except Exception as exc:  # noqa: BLE001 - surfaced as an error frame
            run.status = "failed"
            run.error = str(exc)
            self._emit(run, "error", {"message": str(exc)})
        self._emit(run, "end", {"status": run.status})

    def start(self, run: Run, runner: Runner) -> threading.Thread:
        thread = threading.Thread(target=self._execute, args=(run, runner), daemon=True)
        thread.start()
        return thread

    def run_blocking(self, run: Run, runner: Runner) -> None:
        """Test/inline helper: execute in the calling thread (no background thread)."""
        self._execute(run, runner)
```

**Step 4: Run it green** — `python3 -m unittest tests.test_api_runs -v` → PASS.

**Step 5: Gates + commit**

```bash
git add recette/api/runs.py recette/api/runners.py tests/test_api_runs.py
git commit -m "feat(api): U1 RunManager + identification/discovery runners"
```

---

## Task 6: Run endpoints — POST /runs, GET /runs/{id}, stop, events

**Files:**
- Create: `recette/api/routers/runs.py`
- Modify: `recette/api/app.py` (hold a `RunManager` on `app.state`, include router)
- Create: `tests/test_api_run_routes.py`

**Endpoints:**
- `POST /runs` body `{kind, params}` where `kind ∈ {identification, discovery, lane_b}`. Resolves the runner, `mgr.create`, `mgr.start`, returns `201 {run_id, status}`. Unknown kind → 400. (Lane B runner wiring — registered-agent lookup + `build_llm` — lands in Task 8; for now `lane_b` returns 400 "not yet wired" so this task stays small and green.)
- `GET /runs/{id}` → `{id, kind, status, error}` (404 if unknown).
- `GET /runs/{id}/events` → buffered frames (the polling fallback to the WebSocket).
- `POST /runs/{id}/stop` → `202 {stopped: bool}` (404 if unknown).
- Tests join the worker thread by polling `GET /runs/{id}` until terminal (bounded loop, no `sleep` reliance beyond a short `time.sleep` budget) — or call a `mgr` test hook. Simplest: expose `app.state.run_manager` and, in the test, `start` then `thread.join()` via a returned handle. Since the route starts the thread internally, the test polls `GET /runs/{id}/events` for an `end` frame with a bounded retry.

**Step 1: Write the failing test**

```python
# tests/test_api_run_routes.py
"""U1: launch/inspect/stop runs over HTTP."""

from __future__ import annotations

import time
import unittest

try:
    from fastapi.testclient import TestClient

    from recette.api.app import create_app

    _HAS_FASTAPI = True
except ImportError:  # pragma: no cover
    _HAS_FASTAPI = False


def _wait_terminal(client, run_id, tries=200):
    for _ in range(tries):
        body = client.get(f"/runs/{run_id}").json()
        if body["status"] in {"completed", "failed", "stopped"}:
            return body
        time.sleep(0.01)
    raise AssertionError("run did not terminate")


@unittest.skipUnless(_HAS_FASTAPI, "requires the [api] extra (fastapi)")
class TestRunRoutes(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(create_app())

    def test_launch_identification_then_scorecard(self) -> None:
        r = self.client.post("/runs", json={"kind": "identification", "params": {}})
        self.assertEqual(r.status_code, 201)
        run_id = r.json()["run_id"]
        body = _wait_terminal(self.client, run_id)
        self.assertEqual(body["status"], "completed")
        events = self.client.get(f"/runs/{run_id}/events").json()
        self.assertTrue(any(e["type"] == "scorecard" for e in events))

    def test_unknown_kind_400(self) -> None:
        self.assertEqual(
            self.client.post("/runs", json={"kind": "nope", "params": {}}).status_code, 400
        )

    def test_get_unknown_run_404(self) -> None:
        self.assertEqual(self.client.get("/runs/deadbeef").status_code, 404)

    def test_stop_unknown_run_404(self) -> None:
        self.assertEqual(self.client.post("/runs/deadbeef/stop").status_code, 404)
```

**Step 2: Run it red** → FAIL.

**Step 3: Implement** `recette/api/routers/runs.py`:

```python
"""U1: run launch/inspect/stop endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

from ..runners import discovery_runner, identification_runner

router = APIRouter(prefix="/runs", tags=["runs"])

_RUNNERS = {
    "identification": identification_runner,
    "discovery": discovery_runner,
}


@router.post("", status_code=201)
def launch(request: Request, body: dict[str, Any]) -> dict:
    kind = body.get("kind")
    if kind == "lane_b":
        raise HTTPException(status_code=400, detail="lane_b runs land in Task 8")
    runner = _RUNNERS.get(kind)
    if runner is None:
        raise HTTPException(status_code=400, detail=f"unknown run kind {kind!r}")
    mgr = request.app.state.run_manager
    run = mgr.create(kind, body.get("params", {}))
    mgr.start(run, runner)
    return {"run_id": run.id, "status": run.status}


@router.get("/{run_id}")
def get_run(request: Request, run_id: str) -> dict:
    run = request.app.state.run_manager.get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="no such run")
    return {"id": run.id, "kind": run.kind, "status": run.status, "error": run.error}


@router.get("/{run_id}/events")
def get_events(request: Request, run_id: str) -> list[dict]:
    run = request.app.state.run_manager.get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="no such run")
    return list(run.events)


@router.post("/{run_id}/stop", status_code=202)
def stop_run(request: Request, run_id: str) -> dict:
    ok = request.app.state.run_manager.request_stop(run_id)
    if not ok:
        raise HTTPException(status_code=404, detail="no such run")
    return {"stopped": True}
```

In `create_app`: `from .runs import RunManager`; `app.state.run_manager = RunManager()`; `from .routers import runs as runs_router`; `app.include_router(runs_router.router)`.

**Step 4: Run it green** → PASS.

**Step 5: Gates + commit**

```bash
git add recette/api/routers/runs.py recette/api/app.py tests/test_api_run_routes.py
git commit -m "feat(api): U1 run launch/inspect/stop endpoints (identification + discovery)"
```

---

## Task 7: WebSocket live stream — /runs/{id}/ws

**Files:**
- Modify: `recette/api/runs.py` (add async subscribe/unsubscribe that replays buffered frames + registers the loop)
- Modify: `recette/api/routers/runs.py` (add the WebSocket route)
- Create: `tests/test_api_ws.py`

**Design:** On WS connect: register the current event loop on the run (if not set), create an `asyncio.Queue`, replay every already-buffered frame into it, then loop `await queue.get()` and `websocket.send_json(frame)`; close after sending the `end` frame. If the run is already terminal at connect, replay the buffer and close. `TestClient.websocket_connect` drives it in tests.

**Step 1: Write the failing test**

```python
# tests/test_api_ws.py
"""U1: WebSocket streams a run's event frames to completion."""

from __future__ import annotations

import unittest

try:
    from fastapi.testclient import TestClient

    from recette.api.app import create_app

    _HAS_FASTAPI = True
except ImportError:  # pragma: no cover
    _HAS_FASTAPI = False


@unittest.skipUnless(_HAS_FASTAPI, "requires the [api] extra (fastapi)")
class TestRunWebSocket(unittest.TestCase):
    def setUp(self) -> None:
        self.client = TestClient(create_app())

    def test_ws_streams_until_end(self) -> None:
        run_id = self.client.post(
            "/runs", json={"kind": "identification", "params": {}}
        ).json()["run_id"]
        frames = []
        with self.client.websocket_connect(f"/runs/{run_id}/ws") as ws:
            while True:
                frame = ws.receive_json()
                frames.append(frame)
                if frame["type"] == "end":
                    break
        types = [f["type"] for f in frames]
        self.assertEqual(types[0], "start")
        self.assertIn("scorecard", types)
        self.assertEqual(types[-1], "end")
        self.assertEqual(frames[-1]["data"]["status"], "completed")
```

**Step 2: Run it red** → FAIL (no ws route).

**Step 3: Implement.** Add to `RunManager` in `recette/api/runs.py`:

```python
    async def subscribe(self, run: Run) -> asyncio.Queue:
        """Attach an asyncio queue, replaying buffered frames; registers the loop once."""
        queue: asyncio.Queue = asyncio.Queue()
        loop = asyncio.get_running_loop()
        with run._lock:
            if run._loop is None:
                run._loop = loop
            for frame in run.events:  # replay buffer for a late subscriber
                queue.put_nowait(frame)
            run._subscribers.append(queue)
        return queue

    def unsubscribe(self, run: Run, queue: asyncio.Queue) -> None:
        with run._lock:
            if queue in run._subscribers:
                run._subscribers.remove(queue)
```

> Note: `_emit` already reads `run._loop` and `call_soon_threadsafe`s into each subscriber queue. There is a benign race if the worker thread emits before the first subscriber sets `_loop`; those early frames are still in `run.events` and are replayed on subscribe, so no frame is lost — the WS just receives them via the buffer replay rather than live. The `end` frame is always observed because subscribe runs while the run can still be live, and if the run is already terminal the full buffer (including `end`) is replayed.

Add the WS route to `recette/api/routers/runs.py`:

```python
from fastapi import WebSocket, WebSocketDisconnect


@router.websocket("/{run_id}/ws")
async def run_ws(websocket: WebSocket, run_id: str) -> None:
    mgr = websocket.app.state.run_manager
    run = mgr.get(run_id)
    if run is None:
        await websocket.close(code=4404)
        return
    await websocket.accept()
    queue = await mgr.subscribe(run)
    try:
        while True:
            frame = await queue.get()
            await websocket.send_json(frame)
            if frame["type"] == "end":
                break
    except WebSocketDisconnect:
        pass
    finally:
        mgr.unsubscribe(run, queue)
```

**Step 4: Run it green** — `python3 -m unittest tests.test_api_ws -v` → PASS. If flaky on the race, the buffer-replay path guarantees the `end` frame; confirm by re-running 5×: `for i in $(seq 5); do python3 -m unittest tests.test_api_ws -v || break; done`.

**Step 5: Gates + commit**

```bash
git add recette/api/runs.py recette/api/routers/runs.py tests/test_api_ws.py
git commit -m "feat(api): U1 WebSocket live event stream for runs"
```

---

## Task 8: Lane B run wiring + POST /agents/register

**Files:**
- Modify: `recette/api/runners.py` (add `make_lane_b_runner`)
- Modify: `recette/api/routers/runs.py` (wire `lane_b` kind)
- Modify: `recette/api/routers/config.py` **or** add `recette/api/routers/register.py` (POST /agents/register — convenience alias that validates a Lane B manifest then stores it)
- Modify: `recette/api/app.py` if a new router is added
- Create: `tests/test_api_lane_b_run.py`

**Design:**
- `make_lane_b_runner(agent_cfg, llm)` returns a runner that calls `recette.lane_b.run_agent(..., on_step=lambda i, step: emit("step", {"index": i, "action": step.action}), should_stop=should_stop)` then `emit("result", {"actions": [...], "recording": result.recording.to_dict()})`.
- Lab is the default forge (no side effects). **Real mode is guarded** (R8 + LB6 allowlist): the API only builds a `RealForge` when `params.real` is true AND env `AGENTRAIL_REAL_ALLOWLIST` is set — reuse `recette.realmode.build_real_forge`; otherwise lab.
- For deterministic tests, `POST /runs {kind:"lane_b"}` accepts an optional `params.stub_script` (list of decisions) used to build a `StubLlm`; without it, the runner resolves the agent's `ai_backend_id` → provider/model from the config store and calls `recette.llm.build_llm` (live; key from env). The test uses `stub_script` so no network/key is needed.
- `POST /runs` lane_b: load the registered agent by `params.agent_id` from the config store (404→400 if missing), build the llm (stub or live), `make_lane_b_runner`, start.

**Step 1: Write the failing test**

```python
# tests/test_api_lane_b_run.py
"""U1: a registered Lane B agent runs via the API and streams step frames (stubbed LLM)."""

from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path

try:
    from fastapi.testclient import TestClient

    from recette.api.app import create_app
    from recette.api.config_store import ConfigStore

    _HAS_FASTAPI = True
except ImportError:  # pragma: no cover
    _HAS_FASTAPI = False


def _wait_terminal(client, run_id, tries=200):
    for _ in range(tries):
        s = client.get(f"/runs/{run_id}").json()["status"]
        if s in {"completed", "failed", "stopped"}:
            return s
        time.sleep(0.01)
    raise AssertionError("no terminate")


@unittest.skipUnless(_HAS_FASTAPI, "requires the [api] extra (fastapi)")
class TestLaneBRun(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        store = ConfigStore(Path(self.tmp.name) / "cfg.json")
        store.add_agent({
            "id": "a1", "principal": "acme-bot@github", "target_system": "github",
            "goal": "bump deps", "capability_scope": ["read_repo", "open_pr"],
            "ai_backend_id": "b1", "runtime": "lab",
        })
        self.client = TestClient(create_app(config_store=store))

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_lane_b_run_streams_steps(self) -> None:
        stub = [
            {"kind": "tool_call", "tool_name": "read_repo", "tool_args": {"resource": "acme/x"}},
            {"kind": "final", "text": "done"},
        ]
        r = self.client.post("/runs", json={
            "kind": "lane_b", "params": {"agent_id": "a1", "stub_script": stub}})
        self.assertEqual(r.status_code, 201)
        run_id = r.json()["run_id"]
        self.assertEqual(_wait_terminal(self.client, run_id), "completed")
        events = self.client.get(f"/runs/{run_id}/events").json()
        self.assertTrue(any(e["type"] == "step" for e in events))
        self.assertTrue(any(e["type"] == "result" for e in events))

    def test_register_agent_then_in_catalog(self) -> None:
        r = self.client.post("/agents/register", json={
            "id": "a2", "principal": "p", "target_system": "github", "goal": "g",
            "capability_scope": ["read_repo"], "ai_backend_id": "b1", "runtime": "lab"})
        self.assertEqual(r.status_code, 201)
        lane_b_ids = {a["id"] for a in self.client.get("/agents").json()["lane_b"]}
        self.assertIn("a2", lane_b_ids)
```

**Step 2: Run it red** → FAIL.

**Step 3: Implement.** In `recette/api/runners.py`:

```python
from ..llm import LlmDecision, StubLlm
from ..lane_b import run_agent as run_lane_b_agent


def make_lane_b_runner(agent_cfg: dict, llm) -> Callable[[dict, Emit, ShouldStop], None]:
    def runner(params: dict, emit: Emit, should_stop: ShouldStop) -> None:
        result = run_lane_b_agent(
            agent_id=agent_cfg["id"], principal=agent_cfg["principal"],
            target_system=agent_cfg["target_system"], goal=agent_cfg["goal"],
            capability_scope=agent_cfg["capability_scope"], llm=llm,
            on_step=lambda i, step: emit("step", {"index": i, "action": step.action}),
            should_stop=should_stop,
        )
        emit("result", {
            "actions": [a.to_dict() for a in result.actions],
            "recording": result.recording.to_dict(),
        })
    return runner


def build_stub_llm(script: list[dict]) -> StubLlm:
    return StubLlm([
        LlmDecision(kind=d["kind"], tool_name=d.get("tool_name"),
                    tool_args=d.get("tool_args", {}) or {}, text=d.get("text", ""))
        for d in script
    ])
```

In `recette/api/routers/runs.py` `launch()`, replace the `lane_b` stub branch:

```python
    if kind == "lane_b":
        store = request.app.state.config_store
        params = body.get("params", {})
        agent_cfg = store.get_agent(params.get("agent_id", ""))
        if agent_cfg is None:
            raise HTTPException(status_code=400, detail="unknown lane_b agent_id")
        from ..runners import build_stub_llm, make_lane_b_runner

        if "stub_script" in params:
            llm = build_stub_llm(params["stub_script"])
        else:
            backend = store.get_ai_backend(agent_cfg["ai_backend_id"])
            if backend is None:
                raise HTTPException(status_code=400, detail="unknown ai_backend_id")
            from ...llm import build_llm

            llm = build_llm(backend["provider"], backend["model"])  # live; key from env (R8)
        mgr = request.app.state.run_manager
        run = mgr.create("lane_b", params)
        mgr.start(run, make_lane_b_runner(agent_cfg, llm))
        return {"run_id": run.id, "status": run.status}
```

Add a register route — extend `recette/api/routers/config.py` with an alias mounted at `/agents/register` (a thin wrapper over `add_agent`). Simplest: add to the **catalog** router (already unprefixed) so the path is exactly `/agents/register`:

```python
# in recette/api/routers/catalog.py
from fastapi import HTTPException
from typing import Any


@router.post("/agents/register", status_code=201)
def register_agent(request: Request, agent: dict[str, Any]) -> dict:
    try:
        return request.app.state.config_store.add_agent(agent)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
```

**Step 4: Run it green** — `python3 -m unittest tests.test_api_lane_b_run -v` → PASS.

**Step 5: Gates + commit**

```bash
git add recette/api/runners.py recette/api/routers/runs.py recette/api/routers/catalog.py tests/test_api_lane_b_run.py
git commit -m "feat(api): U1 Lane B run wiring (stub+live) + POST /agents/register"
```

---

## Task 9: Server entrypoint, Make/docs, decision log, plan status, full suite

**Files:**
- Create: `recette/api/__main__.py` (uvicorn entrypoint: `python -m recette.api`)
- Modify: `Makefile` (add `api` target + help line)
- Modify: `README.md` (Track U / API section)
- Create: `docs/runbooks/api.md` (run, endpoints table, WebSocket usage, real-mode guard)
- Create: `docs/tracking/decision_log.jsonl` (first entry: WebSocket transport decision)
- Modify: `docs/plans/MASTER_recette-platform_2026-06-11.md` (mark U1 DONE; record transport = WebSocket at line ~277)

**Step 1: Server entrypoint**

```python
# recette/api/__main__.py
"""Run the U1 API: python -m recette.api  (host/port via env, lab is the default)."""

from __future__ import annotations

import os

import uvicorn

from .app import create_app


def main() -> None:
    uvicorn.run(
        create_app(),
        host=os.environ.get("AGENTRAIL_API_HOST", "127.0.0.1"),
        port=int(os.environ.get("AGENTRAIL_API_PORT", "8090")),
    )


if __name__ == "__main__":
    main()
```

**Step 2: Makefile** — add target + help line:

```make
	@echo "  make api          run the Track U API (uvicorn, needs the [api] extra)"
...
api:
	python3 -m recette.api
```
(Add `api` to the `.PHONY` list.)

**Step 3: decision_log.jsonl** — single line (no wall-clock value invented beyond the resolved date):

```json
{"date": "2026-06-12", "id": "U1-transport", "decision": "Track U real-time transport = WebSocket", "context": "U1 OPEN item (SSE recommended). Chosen WebSocket for a single bidirectional channel the console can grow into (interactive control later).", "supersedes": "MASTER plan SSE recommendation"}
```

**Step 4: README + runbook** — document: install `pip install -e '.[api]'`, `make api`, the endpoint table (`/health`, `/agents`, `/agents/register`, `/config/*`, `/runs` POST, `/runs/{id}`, `/runs/{id}/events`, `/runs/{id}/stop`, `/runs/{id}/ws`), a WebSocket example, and the real-mode guard (lab default; real only with `params.real` + `AGENTRAIL_REAL_ALLOWLIST`; keys via env — R8).

**Step 5: MASTER plan status** — change `### U1 -- Recette API layer  [TODO]` → `[DONE 2026-06-12]` with a one-line shipped note; change the transport decision line from `OPEN: SSE ... vs WebSocket ... Decide at U1.` to `RESOLVED 2026-06-12: WebSocket.`

**Step 6: Full suite + gates**

Run: `make test` → all green (new `test_api_*` + the full pre-existing suite, including `test_lane_b`).
Run: `make gates` → `gates: PASS`.
Run (optional, if Docker available): `make docker-gates && make docker-test`.

**Step 7: Commit**

```bash
git add recette/api/__main__.py Makefile README.md docs/runbooks/api.md docs/tracking/decision_log.jsonl docs/plans/MASTER_recette-platform_2026-06-11.md
git commit -m "feat(api): U1 server entrypoint, make api, docs, decision log; mark U1 DONE"
```

---

## Definition of Done (U1)

- Every CLI capability reachable over the API: `validate`/`run`→identification run; `discovery`→discovery run (per surface / all); `report` metrics surfaced in scorecard frames; `agent run`→Lane B run streaming steps; config CRUD for agents + AI backends; catalog for discovery.
- A launched run streams events live over **WebSocket**, with an HTTP `/events` polling fallback and a `/stop`.
- Secrets never persisted (R8); lab is the default; real mode guarded (allowlist + env).
- `make test` green (API suite + full regression), `make gates` PASS.
- MASTER plan U1 marked DONE; transport decision logged.

## Out of scope (later Track U tasks)

- U2 React/Vite console, U3 Monaco debug view, U4 config UI (this is their **backend**).
- M6 real API wiring (blocked on the colleague's routes).
- Auth on the API (single-user lab assumption for U1; note it in the runbook as a follow-up).
