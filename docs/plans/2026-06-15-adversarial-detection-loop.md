# Adversarial Detection Loop Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Prove, end to end, that an unmediated (ghost-agent) network path is detected by comparing the mitmproxy wire against a target-allowlist of mediated systems.

**Architecture:** A `reconcile()` pure function flags any wire flow whose target host is outside the allowlist of mediated targets (lab + mock_local servers + LLM backends). A honeypot `direct-sink` server on `:9113` is a never-legitimate target; a `probe-bypass` agent reaches it via a real second egress (StdlibHttpClient routed through the wire overlay but NOT through the ExternalSystemProxy), so it appears on the wire with no audit event. The pure function is unit-tested on seeded flows (I4); the live path is proven only in a smoke.

**Tech Stack:** Python 3.11+ stdlib, unittest, FastAPI (`[api]` extra), mitmproxy overlay (optional, smoke only), `recette/platform/proxy/` (WireFlowRecorder, ProxyRouteRegistry), `recette/_http_client.py` (StdlibHttpClient).

**Boundary:** the lab OBSERVES the unmediated path; it does not ENFORCE a network block (that is the target platform's job). reconcile is allowlist-only in this slice; an audit-event join is phase 2.

---

### Task 1: `reconcile()` pure function -- allowlist set-diff

**Files:**
- Create: `recette/platform/proxy/reconcile.py`
- Test: `tests/test_reconcile.py`

**Step 1: Write the failing test**

```python
# tests/test_reconcile.py
from __future__ import annotations

import unittest

from recette.platform.proxy.reconcile import ReconcileReport, reconcile


def _flow(seq: int, host: str) -> dict:
    """Minimal wire-flow view: only host + seq matter for the allowlist diff."""
    return {"seq": seq, "host": host}


class TestReconcile(unittest.TestCase):
    def test_clean_run_has_no_bypass(self) -> None:
        flows = [_flow(1, "127.0.0.1:8082"), _flow(2, "127.0.0.1:9101")]
        allow = {"127.0.0.1:8082", "127.0.0.1:9101"}
        report = reconcile(flows, allow)
        self.assertIsInstance(report, ReconcileReport)
        self.assertTrue(report.ok)
        self.assertEqual(report.bypass_flows, [])

    def test_flow_outside_allowlist_is_a_bypass(self) -> None:
        flows = [_flow(1, "127.0.0.1:8082"), _flow(2, "127.0.0.1:9113")]
        allow = {"127.0.0.1:8082"}
        report = reconcile(flows, allow)
        self.assertFalse(report.ok)
        self.assertEqual([f["host"] for f in report.bypass_flows], ["127.0.0.1:9113"])

    def test_unclassifiable_empty_host_is_suspect_not_allowed(self) -> None:
        # Fail-safe classification: an empty/garbage host is never silently allowed.
        report = reconcile([_flow(1, "")], {"127.0.0.1:8082"})
        self.assertFalse(report.ok)
        self.assertEqual(len(report.bypass_flows), 1)

    def test_is_deterministic(self) -> None:
        flows = [_flow(2, "x:1"), _flow(1, "127.0.0.1:8082")]
        allow = {"127.0.0.1:8082"}
        a = reconcile(flows, allow)
        b = reconcile(flows, allow)
        self.assertEqual(a.to_dict(), b.to_dict())
        # ordering is by seq, stable
        self.assertEqual([f["seq"] for f in a.bypass_flows], [2])
```

**Step 2: Run test to verify it fails**

Run: `.venv/bin/python -m unittest tests.test_reconcile -v`
Expected: FAIL with `ModuleNotFoundError: recette.platform.proxy.reconcile`

**Step 3: Write minimal implementation**

```python
# recette/platform/proxy/reconcile.py
"""Wire-vs-audit reconciliation (allowlist slice).

A legitimate run only talks to MEDIATED targets (the lab, the mock_local
servers, the configured LLM backends). Any wire flow whose target host is
outside that allowlist is an UNMEDIATED path -- the ghost-agent signal. Pure:
given the flows and the allowlist it returns the same report, byte for byte
(I4). An empty/garbage host is treated as SUSPECT (flagged), never allowed
(deny-by-default classification).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ReconcileReport:
    ok: bool
    bypass_flows: list[dict]

    def to_dict(self) -> dict:
        return {"ok": self.ok, "bypass_flows": self.bypass_flows}


def reconcile(wire_flows: list[dict], allowlist: set[str]) -> ReconcileReport:
    """Flag every wire flow whose host is not an allowlisted mediated target."""
    bypass = [
        f
        for f in sorted(wire_flows, key=lambda f: f.get("seq", 0))
        if str(f.get("host", "")) not in allowlist or not f.get("host")
    ]
    return ReconcileReport(ok=(bypass == []), bypass_flows=bypass)
```

**Step 4: Run test to verify it passes**

Run: `.venv/bin/python -m unittest tests.test_reconcile -v`
Expected: PASS (4 tests)

**Step 5: Commit**

```bash
git add recette/platform/proxy/reconcile.py tests/test_reconcile.py
git commit -m "feat(proxy): reconcile() -- wire-vs-audit allowlist diff (pure, I4)"
```

---

### Task 2: Allowlist builder from the server registry + LLM backends

**Files:**
- Modify: `recette/platform/proxy/reconcile.py`
- Test: `tests/test_reconcile.py` (add a class)

**Step 1: Write the failing test**

```python
class TestAllowlistFromConfig(unittest.TestCase):
    def test_allowlist_includes_lab_mock_local_and_llm_hosts(self) -> None:
        from recette.platform.proxy.reconcile import build_allowlist

        servers = [
            {"id": "gh-mock", "system": "github", "mode": "mock_local", "port": 9101},
            {"id": "direct-sink", "system": "direct_sink", "mode": "honeypot", "port": 9113},
        ]
        allow = build_allowlist(
            servers=servers,
            lab_host="127.0.0.1:8082",
            llm_hosts={"api.groq.com:443"},
        )
        self.assertIn("127.0.0.1:8082", allow)      # the lab
        self.assertIn("127.0.0.1:9101", allow)      # a mock_local server
        self.assertIn("api.groq.com:443", allow)    # an LLM backend
        self.assertNotIn("127.0.0.1:9113", allow)   # the honeypot is NEVER allowlisted
```

**Step 2: Run to verify it fails**

Run: `.venv/bin/python -m unittest tests.test_reconcile.TestAllowlistFromConfig -v`
Expected: FAIL with `ImportError: cannot import name 'build_allowlist'`

**Step 3: Implement**

```python
# add to recette/platform/proxy/reconcile.py
def build_allowlist(
    *,
    servers: list[dict],
    lab_host: str,
    llm_hosts: set[str],
) -> set[str]:
    """Allowlisted mediated targets: the lab, every mock_local server (host:port),
    and the configured LLM backend hosts. A honeypot (mode != mock_local) is
    deliberately excluded -- it is never a legitimate target."""
    allow = {lab_host} | set(llm_hosts)
    for s in servers:
        if s.get("mode") == "mock_local" and s.get("port"):
            allow.add(f"127.0.0.1:{s['port']}")
    return allow
```

**Step 4: Run to verify it passes**

Run: `.venv/bin/python -m unittest tests.test_reconcile -v`
Expected: PASS (5 tests total)

**Step 5: Commit**

```bash
git add recette/platform/proxy/reconcile.py tests/test_reconcile.py
git commit -m "feat(proxy): build_allowlist from server registry + LLM hosts"
```

---

### Task 3: `GET /proxy/reconcile` endpoint

**Files:**
- Modify: `recette/api/routers/proxy.py` (add a route mirroring `GET /wire`)
- Test: `tests/test_api_reconcile.py`

**Step 1: Write the failing test**

```python
# tests/test_api_reconcile.py -- mirror tests/test_api_wire.py setup
# Seed the wire recorder with one allowlisted flow + one honeypot flow,
# assert GET /proxy/reconcile?run_id=R returns ok=false and the :9113 flow.
```
(Model the app fixture on `tests/test_api_wire.py`: build the app with a
`WireFlowRecorder`, POST two flows to `/proxy/wire` (one host `127.0.0.1:8082`,
one `127.0.0.1:9113`), then GET `/proxy/reconcile`.)

**Step 2: Run -> FAIL** (404, route absent).

**Step 3: Implement** -- add to `recette/api/routers/proxy.py`:

```python
@router.get("/reconcile")
def get_reconcile(request: Request, run_id: str | None = None) -> dict:
    """Wire-vs-audit reconciliation: wire flows with a target outside the
    allowlist of mediated systems are unmediated paths (ghost-agent signal)."""
    from ...platform.proxy.reconcile import build_allowlist, reconcile

    flows = request.app.state.wire_flow_recorder.snapshot()
    if run_id is not None:
        flows = [f for f in flows if f.run_id == run_id]
    allow = build_allowlist(
        servers=request.app.state.config_store.list_servers(),
        lab_host=request.app.state.lab_host,           # add to app.state at startup
        llm_hosts=request.app.state.llm_hosts,         # add to app.state at startup
    )
    report = reconcile([f.to_dict() for f in flows], allow)
    return {"run_id": run_id, **report.to_dict()}
```
(Wire `lab_host` and `llm_hosts` into `app.state` in `recette/api/app.py` next to
`wire_proxy_url`; derive `lab_host` from the lab URL, `llm_hosts` from the
resolved backend base_urls. If `config_store.list_servers()` differs, adapt.)

**Step 4: Run -> PASS.**

**Step 5: Commit**

```bash
git add recette/api/routers/proxy.py recette/api/app.py tests/test_api_reconcile.py
git commit -m "feat(api): GET /proxy/reconcile -- expose the wire-vs-audit report"
```

---

### Task 4: Honeypot `direct-sink` server on :9113

**Files:**
- Investigate: `cicd/platform.sh` (how mock_local servers boot), `recette/lab/mock_server.py`
- Modify: `config/inspect_ia_agents.config.json` (add the server), `recette/lab/domains/__init__.py` ONLY if a handler is required
- Create: a minimal sink handler if the mock server dispatches by `system`
- Test: `tests/test_direct_sink.py`

**Step 1: Decide the form (investigation step, 5 min).** Read how a `mock_local`
server is launched and how it resolves its handler. Two options:
- (a) reuse the mock server with a `direct_sink` handler whose `handle()` records
  the hit and returns 200, registered in `HANDLER_MODULES` but NOT in the catalog
  `DOMAIN_MODULES` (so coverage-guard D2/D4, which iterate CATALOG domains, never
  touch it);
- (b) a standalone tiny HTTP server with its own `recette.sh` lifecycle entry.
Pick (a) if the mock server already dispatches by `system`; else (b).

**Step 2: Write the failing test** -- assert the sink records a hit and is NOT a
catalog domain:

```python
# tests/test_direct_sink.py
from recette.platform.catalog import load_catalog

def test_direct_sink_is_not_a_governed_domain() -> None:
    domains = {s.target_system for s in load_catalog().all()}
    assert "direct_sink" not in domains  # honeypot is never governed
```

**Step 3..4: Implement + run** the sink handler/server; add the registry entry
`{"id": "direct-sink", "system": "direct_sink", "mode": "mock_local", "port": 9113}`
(or `mode: "honeypot"` for option b). Verify `./recette.sh platform status` lists it.

**Step 5: Run coverage-guard** to confirm still green:
Run: `.venv/bin/python -m unittest tests.test_coverage_guard -v` -> PASS.

**Step 6: Commit**

```bash
git add config/inspect_ia_agents.config.json recette/lab tests/test_direct_sink.py
git commit -m "feat(lab): direct-sink honeypot on :9113 (non-governed, records hits)"
```

---

### Task 5: `probe-bypass` agent with a real second egress

**Files:**
- Create: probe definition (corpus/sim subject + a runtime agent in the config, or a
  small script `scripts/run_probe_bypass.py` that drives it)
- Reference: `recette/_http_client.py` (`StdlibHttpClient(proxy_url=...)`)
- Test: covered by the smoke (Task 6); a unit test asserts the probe builds a
  client pointed at the honeypot, routed through the wire overlay, not the proxy.

**Key code (the second egress):**

```python
from recette._http_client import StdlibHttpClient

# Routed through the mitmproxy overlay (so it appears on the wire) but NOT through
# the ExternalSystemProxy (so NO ProxyTrace / audit event is emitted). This is the
# unmediated path the validator must catch.
client = StdlibHttpClient(proxy_url=wire_proxy_url)  # e.g. http://127.0.0.1:8083
client.post("http://127.0.0.1:9113/write", body=b'{"table":"users"}')
```

**Commit**

```bash
git add scripts/run_probe_bypass.py corpus/sim config/inspect_ia_agents.config.json
git commit -m "feat(redteam): probe-bypass -- direct egress to the honeypot (unmediated)"
```

---

### Task 6: `scripts/smoke_reconcile.py` -- live end-to-end proof

**Files:**
- Create: `scripts/smoke_reconcile.py` (model on `scripts/smoke_wire.py`)

**Behaviour:** self-skip without Docker/overlay; else bring the wire overlay up
(`./recette.sh wire up`), set `INSPECT_IA_AGENTS_WIRE_PROXY`, run the probe-bypass,
then GET `/proxy/reconcile` and assert `ok == false` and a bypass flow to
`127.0.0.1:9113` is present.

**Step: Run it**

Run: `./recette.sh smoke` (or `python scripts/smoke_reconcile.py`)
Expected: the reconcile report flags the `:9113` flow.

**Commit**

```bash
git add scripts/smoke_reconcile.py
git commit -m "test(smoke): live wire-vs-audit -- probe-bypass flagged by reconcile"
```

---

### Task 7: Gates + docs + close

**Steps:**
1. `make gates` (ruff + ruff format --check + mypy + bandit) -> clean.
2. `.venv/bin/python -m unittest discover -s tests` -> only the known pre-existing
   `test_api_server_test` env failures remain.
3. `make recette` -> coverage-guard D1-D7 green (honeypot excluded).
4. Update `docs/runbooks/proxy-debug-console.md`: move the wire-vs-audit section
   from "forward-looking" to "implemented (allowlist slice)"; update
   `docs/plans/2026-06-15-adversarial-verification-apex.md` Status of the slice.
5. Commit docs; push.

```bash
git add docs/
git commit -m "docs: wire-vs-audit reconciliation implemented (allowlist slice)"
git push origin main
```

---

## Notes for the executor

- **R21 (shared tree):** another session edits the red-team `sim` UX + `campaign.py`.
  Touch ONLY the files listed per task; never stage their WIP.
- **R19:** the honeypot is started by `./recette.sh` only; never hand-launch on :9113.
- **I4:** `reconcile()` and `build_allowlist()` stay pure; no clock, no network. The
  only network is the smoke (Task 6).
- **Phase 2 (out of scope here):** audit-event join (detect a forged event), extended
  ghost-identity negatives, capability-overreach scorecard, fault-injection (chaos),
  Meta-Governance of probes, the console tab. See the APEX plan.
