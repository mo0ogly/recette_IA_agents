# Private DNS Resolver Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Give lab servers stable internal names (fqdn/aliases) that the proxy resolves deterministically, surface the name in ProxyTrace (trace realism), and add an allowlist containment gate that denies+audits undeclared names -- all operator-configurable from the console.

**Architecture:** A pure resolver (`recette/platform/netname/resolver.py`) maps a name to a server registry entry by `fqdn` -> `alias` -> `id`, honoring a global `containment` flag (deny-by-default on unknown when on, legacy id fallback when off). It sits in the Data Plane in front of the existing pure `resolve_proxy`, never in `decide()` (I4). The proxy records the resolved name as `ProxyTrace.target` and emits an audited `resolution_denied` event on a blocked name (fail-safe, no network call). The config server table is the single source of truth, edited via the existing server CRUD + console servers page.

**Tech Stack:** Python (stdlib `unittest`, `jsonschema`), FastAPI (`recette/api`), React/TS console (`vitest`). Gates: `.venv/bin/python -m unittest discover -s tests`, ruff/mypy in `.venv-pyaudit/bin/`, `./recette.sh console-test`.

**Branch policy:** Work on `main`, no branches (project rule). `git status` before any commit; do NOT stage `config/inspect_ia_agents.config.json` (other-session WIP) or any file you did not create (R28/R21). Commit small after each task.

---

## Background the executor needs

- **Server registry entry shape** (config, validated by `recette/api/config_store.py`):
  `{"id": str, "system": str, "mode": "mock_local|honeypot|declared_url|real_saas", "port": int (mock_local/honeypot) | "base_url": str (declared_url)}`.
- **`recette/platform/proxy/router.py::resolve_proxy(agent, servers, default, ...)`** is a PURE
  function that already maps a server entry to a `LabHttpProxy`. It looks up the server by the
  agent's `server` field (a server `id`). This is where name resolution plugs in: resolve the
  name to a server `id` BEFORE `resolve_proxy`, or extend it to accept a name.
- **`recette/platform/proxy/lab_proxy.py::LabHttpProxy.execute(event)`** builds
  `ProxyTrace.from_response(event.target_system, event.action_type, event.resource, response)`.
  `target` currently = `target_system`. We add the resolved `fqdn` as the trace target.
- **`recette/platform/events.py`** holds `PlatformActionEvent` and the platform event types --
  add the `resolution_denied` event here.
- Determinism (I4): the resolver does NO socket/clock/random; it is a pure function of
  `(name, servers, containment)`. A replay test asserts byte-stability.

---

## Task 1: Resolver core -- name -> server entry (pure)

**Files:**
- Create: `recette/platform/netname/__init__.py`
- Create: `recette/platform/netname/resolver.py`
- Test: `tests/test_netname_resolver.py`

**Step 1: Write the failing test**

```python
# tests/test_netname_resolver.py
"""netname resolver: pure name -> server entry, fqdn/alias/id, containment (I4)."""
from __future__ import annotations

import unittest

from recette.platform.netname.resolver import ResolutionDenied, resolve_name

SERVERS = [
    {"id": "gh-mock", "system": "github", "mode": "mock_local", "port": 9101,
     "fqdn": "api.github.com", "aliases": ["github.lab.internal"]},
    {"id": "finance-mock", "system": "finance", "mode": "mock_local", "port": 9103},
]


class TestResolveName(unittest.TestCase):
    def test_resolves_by_fqdn(self) -> None:
        self.assertEqual(resolve_name("api.github.com", SERVERS, containment=True)["id"], "gh-mock")

    def test_resolves_by_alias(self) -> None:
        self.assertEqual(
            resolve_name("github.lab.internal", SERVERS, containment=True)["id"], "gh-mock"
        )

    def test_resolves_by_id_when_no_fqdn(self) -> None:
        self.assertEqual(resolve_name("finance-mock", SERVERS, containment=True)["id"], "finance-mock")

    def test_unknown_name_denied_when_containment_on(self) -> None:
        with self.assertRaises(ResolutionDenied) as ctx:
            resolve_name("evil.com", SERVERS, containment=True)
        self.assertEqual(ctx.exception.name, "evil.com")

    def test_unknown_name_falls_back_to_id_when_containment_off(self) -> None:
        # containment off: unknown name returns None (caller uses legacy path), never raises
        self.assertIsNone(resolve_name("evil.com", SERVERS, containment=False))

    def test_resolution_is_deterministic(self) -> None:
        a = resolve_name("api.github.com", SERVERS, containment=True)
        b = resolve_name("api.github.com", SERVERS, containment=True)
        self.assertEqual(a, b)


if __name__ == "__main__":
    unittest.main()
```

**Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m unittest tests.test_netname_resolver -v`
Expected: FAIL (`ModuleNotFoundError: recette.platform.netname`).

**Step 3: Write minimal implementation**

```python
# recette/platform/netname/__init__.py
"""Private DNS resolver (Data Plane): config-driven, pure name -> server entry."""
```

```python
# recette/platform/netname/resolver.py
"""Pure name resolution over the server registry (I4).

A name resolves to a server entry by fqdn -> alias -> id. With containment ON,
an unknown name is DENIED (fail-safe). With containment OFF, an unknown name
returns None so the caller keeps the legacy id-based path (realism-only mode).

Purity: no socket, no clock, no random -- a pure function of (name, servers,
containment). Resolution is deterministic and replay-stable. This module lives
in the Data Plane and is NEVER called from the decision path (decide()).
"""
from __future__ import annotations


class ResolutionDenied(Exception):
    """A name is not in the allowlist and containment is enforced (fail-safe deny)."""

    def __init__(self, name: str) -> None:
        super().__init__(f"name not in private DNS allowlist: {name}")
        self.name = name


def resolve_name(
    name: str, servers: list[dict], *, containment: bool
) -> dict | None:
    """Resolve a name to its server entry, or None (containment off + unknown).

    Raises ResolutionDenied when containment is on and the name is unknown.
    """
    for server in servers:
        if name == server.get("fqdn"):
            return server
    for server in servers:
        if name in (server.get("aliases") or []):
            return server
    for server in servers:
        if name == server.get("id"):
            return server
    if containment:
        raise ResolutionDenied(name)
    return None
```

**Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m unittest tests.test_netname_resolver -v`
Expected: PASS (6 tests).

**Step 5: Lint + commit**

```bash
.venv-pyaudit/bin/ruff check recette/platform/netname/ tests/test_netname_resolver.py && .venv-pyaudit/bin/ruff format --check recette/platform/netname/ tests/test_netname_resolver.py
git add recette/platform/netname/ tests/test_netname_resolver.py
git commit -m "feat(netname): pure config-driven name resolver (fqdn/alias/id + containment)"
```

---

## Task 2: Replay test -- resolution is byte-stable

**Files:**
- Test: `tests/test_netname_resolver.py` (add a class)

**Step 1: Write the failing test**

```python
class TestResolveReplay(unittest.TestCase):
    """I4: same (name, table) yields the same result across replays, incl. denial."""

    def test_denied_name_is_stable_across_replays(self) -> None:
        for _ in range(3):
            with self.assertRaises(ResolutionDenied) as ctx:
                resolve_name("nope.example", SERVERS, containment=True)
            self.assertEqual(ctx.exception.name, "nope.example")

    def test_alias_resolves_to_same_entry_as_fqdn(self) -> None:
        self.assertEqual(
            resolve_name("api.github.com", SERVERS, containment=True),
            resolve_name("github.lab.internal", SERVERS, containment=True),
        )
```

**Step 2: Run** `.venv/bin/python -m unittest tests.test_netname_resolver -v` -> PASS (no impl change needed; this pins I4).

**Step 3: Commit**

```bash
git add tests/test_netname_resolver.py
git commit -m "test(netname): pin deterministic replay-stable resolution (I4)"
```

---

## Task 3: config_store -- validate fqdn/aliases + collision

**Files:**
- Modify: `recette/api/config_store.py` (server validation path)
- Test: `tests/test_config_store_netname.py`

**Step 1: Write the failing test**

```python
# tests/test_config_store_netname.py
"""config_store: fqdn/aliases are optional, syntactic, and collision-free."""
from __future__ import annotations

import unittest

from recette.api.config_store import validate_server_netname  # new helper


class TestServerNetnameValidation(unittest.TestCase):
    def test_accepts_server_without_fqdn(self) -> None:
        validate_server_netname({"id": "a", "mode": "mock_local", "port": 9101}, others=[])

    def test_accepts_valid_fqdn_and_aliases(self) -> None:
        validate_server_netname(
            {"id": "a", "mode": "mock_local", "port": 9101,
             "fqdn": "api.github.com", "aliases": ["gh.lab.internal"]},
            others=[],
        )

    def test_rejects_duplicate_fqdn(self) -> None:
        existing = [{"id": "a", "fqdn": "api.github.com"}]
        with self.assertRaises(ValueError):
            validate_server_netname(
                {"id": "b", "mode": "mock_local", "port": 9102, "fqdn": "api.github.com"},
                others=existing,
            )

    def test_rejects_alias_colliding_with_other_fqdn(self) -> None:
        existing = [{"id": "a", "fqdn": "api.github.com"}]
        with self.assertRaises(ValueError):
            validate_server_netname(
                {"id": "b", "mode": "mock_local", "port": 9102, "aliases": ["api.github.com"]},
                others=existing,
            )

    def test_rejects_malformed_fqdn(self) -> None:
        with self.assertRaises(ValueError):
            validate_server_netname(
                {"id": "a", "mode": "mock_local", "port": 9101, "fqdn": "not a host!"},
                others=[],
            )


if __name__ == "__main__":
    unittest.main()
```

**Step 2: Run** `.venv/bin/python -m unittest tests.test_config_store_netname -v` -> FAIL (`ImportError: validate_server_netname`).

**Step 3: Write minimal implementation** in `recette/api/config_store.py`

```python
import re

_HOSTNAME_RE = re.compile(r"^(?=.{1,253}$)([a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?\.)*[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$")


def validate_server_netname(server: dict, *, others: list[dict]) -> None:
    """Validate a server's optional fqdn/aliases: syntactic hostnames, no
    collision with any name already declared by another server. Fail-safe:
    raise ValueError (mapped to 422 by the router) before persistence."""
    names = []
    fqdn = server.get("fqdn")
    if fqdn is not None:
        names.append(fqdn)
    names.extend(server.get("aliases") or [])
    for name in names:
        if not isinstance(name, str) or not _HOSTNAME_RE.match(name):
            raise ValueError(f"invalid hostname: {name!r}")
    taken: set[str] = set()
    for other in others:
        if other.get("id") == server.get("id"):
            continue
        if other.get("fqdn"):
            taken.add(other["fqdn"])
        taken.update(other.get("aliases") or [])
    clash = taken.intersection(names)
    if clash:
        raise ValueError(f"name already declared by another server: {sorted(clash)}")
```

Then call `validate_server_netname(server, others=existing_servers)` in the create/update server
path of `config_store.py` (where servers are added/patched, alongside `_check_runtime`).

**Step 4: Run** `.venv/bin/python -m unittest tests.test_config_store_netname -v` -> PASS.

**Step 5: Lint + commit**

```bash
.venv-pyaudit/bin/ruff check recette/api/config_store.py tests/test_config_store_netname.py && .venv-pyaudit/bin/mypy recette/api/config_store.py
git add recette/api/config_store.py tests/test_config_store_netname.py
git commit -m "feat(config): validate server fqdn/aliases (syntactic + collision 422)"
```

---

## Task 4: resolution_denied audited event

**Files:**
- Modify: `recette/platform/events.py` (add event type/builder)
- Test: `tests/test_resolution_denied_event.py`

**Step 1: Write the failing test** -- assert a `resolution_denied` event carries the denied name,
agent_id, and is a first-class platform event (mirror an existing event's shape in that module;
read `recette/platform/events.py` first to match the actual constructor/fields, e.g.
`PlatformActionEvent`). Example skeleton:

```python
# tests/test_resolution_denied_event.py
from __future__ import annotations

import unittest

from recette.platform.events import build_resolution_denied  # new builder


class TestResolutionDeniedEvent(unittest.TestCase):
    def test_carries_name_and_agent(self) -> None:
        evt = build_resolution_denied(agent_id="agent-1", name="evil.com", reason="not_in_allowlist")
        self.assertEqual(evt.agent_id, "agent-1")
        self.assertEqual(evt.name, "evil.com")
        self.assertEqual(evt.reason, "not_in_allowlist")

    def test_is_deterministic_given_inputs(self) -> None:
        a = build_resolution_denied(agent_id="x", name="n", reason="r")
        b = build_resolution_denied(agent_id="x", name="n", reason="r")
        self.assertEqual(a, b)
```

**Step 2: Run** -> FAIL (`ImportError`).

**Step 3: Implement** a minimal frozen dataclass + `build_resolution_denied(...)` in
`recette/platform/events.py`, following that module's existing style (no clock in the builder --
any timestamp is an injected input, I4). Keep it append-only / immutable (I1).

**Step 4: Run** -> PASS.

**Step 5: Lint + commit**

```bash
.venv-pyaudit/bin/ruff check recette/platform/events.py tests/test_resolution_denied_event.py && .venv-pyaudit/bin/mypy recette/platform/events.py
git add recette/platform/events.py tests/test_resolution_denied_event.py
git commit -m "feat(events): resolution_denied audited event (containment signal, I1/I4)"
```

---

## Task 5: ProxyTrace.target = resolved fqdn (trace realism, A)

**Files:**
- Modify: `recette/platform/proxy/lab_proxy.py` (pass resolved name to ProxyTrace)
- Modify: `recette/platform/proxy/router.py` (resolve name -> server before building proxy; thread the resolved fqdn)
- Test: `tests/test_proxy_target_fqdn.py`

**Step 1: Write the failing test** -- drive a `LabHttpProxy` against a fake transport (reuse the
pattern already used in the existing proxy tests; read `tests/` for the current lab_proxy test to
copy its HTTP stub) and assert `ProxyTrace.target` equals the server's `fqdn` when one is declared,
and falls back to `target_system` when none is. Example shape:

```python
def test_trace_target_is_fqdn_when_declared(self) -> None:
    # proxy built for a server with fqdn="api.github.com"
    result = proxy.execute(event)  # event.target_system == "github"
    self.assertEqual(result.trace.target, "api.github.com")

def test_trace_target_falls_back_to_target_system(self) -> None:
    result = proxy.execute(event)  # server without fqdn
    self.assertEqual(result.trace.target, "github")
```

**Step 2: Run** -> FAIL (target is still `target_system`).

**Step 3: Implement** -- add an optional `target_name: str | None` to `LabHttpProxy.__init__`
(set by `resolve_proxy` from the resolved server's `fqdn`), and use
`self._target_name or event.target_system` when building the ProxyTrace target. In
`resolve_proxy`, when the agent's `server` field is a name, resolve it via
`recette.platform.netname.resolver.resolve_name(...)` to the server entry, pass the entry's
`fqdn` as `target_name`. Keep `resolve_proxy` pure (resolver is pure).

**Step 4: Run** -> PASS.

**Step 5: Lint + commit**

```bash
.venv-pyaudit/bin/ruff check recette/platform/proxy/ tests/test_proxy_target_fqdn.py && .venv-pyaudit/bin/mypy recette/platform/proxy/
git add recette/platform/proxy/ tests/test_proxy_target_fqdn.py
git commit -m "feat(proxy): ProxyTrace.target carries resolved fqdn (trace realism)"
```

---

## Task 6: Containment in resolve_proxy -- deny undeclared + audit (C)

**Files:**
- Modify: `recette/platform/proxy/router.py` (containment flag -> ResolutionDenied -> fail-safe)
- Modify: the call-site that builds the proxy and can emit the event (likely
  `recette/api/runners.py` and/or `recette/api/routers/config.py`; grep for `resolve_proxy` callers)
- Test: `tests/test_proxy_containment.py`

**Step 1: Write the failing test**

```python
# tests/test_proxy_containment.py
"""Containment (C): an undeclared server name is denied fail-safe, no proxy built."""
from __future__ import annotations

import unittest

from recette.platform.netname.resolver import ResolutionDenied
from recette.platform.proxy.router import resolve_proxy


class _Default:  # stand-in default proxy; must NEVER be returned for an unknown name
    pass


class TestContainment(unittest.TestCase):
    SERVERS = [{"id": "gh-mock", "system": "github", "mode": "mock_local", "port": 9101,
                "fqdn": "api.github.com"}]

    def test_unknown_name_denied_when_containment_on(self) -> None:
        agent = {"server": "evil.com"}
        with self.assertRaises(ResolutionDenied):
            resolve_proxy(agent, self.SERVERS, _Default(), containment=True)

    def test_known_fqdn_resolves_when_containment_on(self) -> None:
        agent = {"server": "api.github.com"}
        proxy = resolve_proxy(agent, self.SERVERS, _Default(), containment=True)
        self.assertIsNotNone(proxy)

    def test_unknown_name_uses_legacy_when_containment_off(self) -> None:
        # containment off + name == an existing id still resolves; a non-id raises
        # ValueError (dangling reference) exactly as today -- containment changes
        # nothing for the off path.
        agent = {"server": "gh-mock"}
        proxy = resolve_proxy(agent, self.SERVERS, _Default(), containment=False)
        self.assertIsNotNone(proxy)


if __name__ == "__main__":
    unittest.main()
```

**Step 2: Run** -> FAIL (`resolve_proxy` has no `containment` kwarg).

**Step 3: Implement** -- add a keyword-only `containment: bool = False` to `resolve_proxy`. When
the agent's `server` is set, first `resolve_name(server, servers, containment=containment)`:
- a resolved entry -> proceed with that entry (existing mode dispatch), pass `fqdn` as target_name (Task 5);
- `ResolutionDenied` -> propagate (fail-safe, the function builds NO proxy);
- `None` (containment off, unknown name) -> fall through to the existing id lookup, which raises
  ValueError on a dangling reference exactly as today.
At the call-site (grep `resolve_proxy` callers), wrap the call: on `ResolutionDenied`, emit
`build_resolution_denied(...)` to the audit sink and return a fail-safe error WITHOUT executing
(no HTTP call). Read the existing call-site to mirror how other platform events are recorded.

**Step 4: Run** -> PASS. Then full suite: `.venv/bin/python -m unittest discover -s tests` -> green.

**Step 5: Lint + commit**

```bash
.venv-pyaudit/bin/ruff check recette/platform/proxy/router.py recette/api/runners.py tests/test_proxy_containment.py && .venv-pyaudit/bin/mypy recette/platform/proxy/router.py
git add recette/platform/proxy/router.py recette/api/runners.py tests/test_proxy_containment.py
git commit -m "feat(proxy): containment gate -- deny+audit undeclared name (fail-safe, C)"
```

---

## Task 7: API -- accept fqdn/aliases + POST /config/resolve

**Files:**
- Modify: `recette/api/routers/config.py` (server CRUD body accepts fqdn/aliases; map ValueError->422; new resolve endpoint)
- Test: `tests/test_api_config_resolve.py`

**Step 1: Write the failing test** -- use FastAPI `TestClient` over `create_app` (copy the
existing API test setup in `tests/`). Assert:
- creating/updating a server with `fqdn`/`aliases` persists them;
- a duplicate fqdn returns 422;
- `POST /config/resolve {"name": "api.github.com"}` returns the endpoint; `{"name": "evil.com"}`
  with containment on returns a `denied` result (not a 500).

**Step 2: Run** -> FAIL (no `/config/resolve`; fqdn dropped).

**Step 3: Implement** -- thread `fqdn`/`aliases` through the server create/update handlers (they
already pass arbitrary fields to `config_store`; ensure validation via Task 3 runs and ValueError
maps to `HTTPException(422)`). Add:

```python
@router.post("/resolve")
def resolve_endpoint(request: Request, body: dict = Body(...)) -> dict:
    store = _store(request)
    servers = store.list_servers()  # use the actual accessor
    name = body.get("name", "")
    containment = bool(body.get("containment", store.get_containment()))  # global flag accessor
    from ...platform.netname.resolver import ResolutionDenied, resolve_name
    try:
        entry = resolve_name(name, servers, containment=containment)
    except ResolutionDenied:
        return {"name": name, "resolved": False, "reason": "not_in_allowlist"}
    if entry is None:
        return {"name": name, "resolved": False, "reason": "unknown_legacy"}
    return {"name": name, "resolved": True, "server_id": entry["id"], "fqdn": entry.get("fqdn")}
```

(Use the real store accessors; grep `config_store` for `list_servers`/equivalent and add a
`containment` global flag getter/setter if one does not exist -- store it in the same versioned
config file, default False.)

**Step 4: Run** -> PASS.

**Step 5: Lint + commit**

```bash
.venv-pyaudit/bin/ruff check recette/api/routers/config.py tests/test_api_config_resolve.py && .venv-pyaudit/bin/mypy recette/api/routers/config.py
git add recette/api/routers/config.py recette/api/config_store.py tests/test_api_config_resolve.py
git commit -m "feat(api): server fqdn/aliases CRUD + POST /config/resolve probe"
```

---

## Task 8: Console -- fqdn/aliases fields + containment toggle (R16)

**Files:**
- Modify: `console/src/pages/servers/index.tsx` (form fields + toggle)
- Create/Modify: `console/src/pages/servers/__fixtures__/servers.fixture.json` (real payload with fqdn/aliases)
- Test: `console/src/pages/servers/index.test.tsx`

**Step 1: Write the failing test** (vitest render-and-assert, R16) -- render the servers page with
a real fixture that includes `fqdn`/`aliases`; assert the fqdn input renders the value and the
containment toggle reflects both states. Capture the real payload first:

```bash
# with the platform up (./recette.sh platform up), capture a real server list:
curl -s http://localhost:8090/config/servers > console/src/pages/servers/__fixtures__/servers.fixture.json
```

(Then hand-add `fqdn`/`aliases` to one entry to reflect the new shape, or set one via the UI/API
and re-capture -- the fixture MUST be a real backend payload, R16.)

**Step 2: Run** `./recette.sh console-test` -> FAIL (no fqdn field rendered).

**Step 3: Implement** -- add `fqdn` (text) and `aliases` (comma-separated text -> string[]) inputs
to the server form, and a global "Enforce private DNS allowlist (containment)" toggle wired to the
containment flag via the service. Unwrap the response envelope in the service (R16). Follow the
existing form + service patterns in the file.

**Step 4: Run** `./recette.sh console-test` -> PASS. Then `./recette.sh console-build` -> green (tsc + vite).

**Step 5: Commit**

```bash
git add console/src/pages/servers/
git commit -m "feat(console): server fqdn/aliases fields + containment toggle (R16)"
```

---

## Task 9: Console -- resolve probe in ServerTestPanel (R16)

**Files:**
- Modify: `console/src/components/ServerTestPanel.tsx` (a "resolve name" probe calling POST /config/resolve)
- Modify: `console/src/components/__fixtures__/serverTest.fixture.json` (real resolve payload)
- Test: `console/src/components/ServerTestPanel.test.tsx`

**Step 1: Write the failing test** -- render with a real resolve fixture (resolved + denied),
assert the panel shows the resolved endpoint and a `denied` badge for an undeclared name.

**Step 2: Run** `./recette.sh console-test` -> FAIL.

**Step 3: Implement** -- a name input + "Resolve" button hitting `POST /config/resolve` via the
service (envelope unwrapped), rendering resolved/denied. Capture the real fixture from the live
endpoint (R16, both outcomes).

**Step 4: Run** `./recette.sh console-test` + `./recette.sh console-build` -> green.

**Step 5: Commit**

```bash
git add console/src/components/ServerTestPanel.tsx console/src/components/ServerTestPanel.test.tsx console/src/components/__fixtures__/serverTest.fixture.json
git commit -m "feat(console): resolve-name probe in ServerTestPanel (R16)"
```

---

## Task 10: Live proof + docs + memory

**Files:**
- Modify: `docs/runbooks/lab-realistic-doubles.md` (or a new `docs/runbooks/private-dns.md`) -- the name model, containment toggle, resolve probe.
- Optionally extend `scripts/smoke_console.py` with a resolve-probe step (deterministic, no real key).
- Update memory `lab-entity-model-derive-by-id` cross-link, add a `private-dns-resolver` memory if warranted.

**Step 1: Live wiring proof (R14)** -- with `./recette.sh platform up` + console up:
- set a server `fqdn` from the UI, run an agent against it, confirm the trace shows the fqdn
  (screenshot / DOM assert);
- turn containment on, point an agent's `server` at an undeclared name, confirm `resolution_denied`
  in the audit + NO call made.

**Step 2: Run all gates**

```bash
.venv/bin/python -m unittest discover -s tests
make recette        # coverage guard stays green
./recette.sh console-test
./recette.sh console-build
.venv-pyaudit/bin/ruff check recette/ tests/ && .venv-pyaudit/bin/mypy recette/
```

Expected: all green.

**Step 3: Commit docs + memory**

```bash
git add docs/ scripts/smoke_console.py
git commit -m "docs(netname): private DNS resolver runbook + live proof"
```

---

## Done criteria

- Resolver pure + replay-stable (Tasks 1-2), config validation + 422 (Task 3),
  audited `resolution_denied` (Task 4), trace realism (Task 5), containment fail-safe (Task 6),
  API CRUD + resolve probe (Task 7), console fields/toggle/probe with R16 fixtures (Tasks 8-9),
  live proof + green gates + docs (Task 10).
- Invariants: I4 (resolution pure, outside decide(), replay test), I2/I5 (proxy still mediates),
  fail-safe deny-by-default, I1 (event immutable).
- `git status` clean of foreign files at each commit; only files you created/own staged.
```
