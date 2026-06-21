# Enrich discoveryprobe kernel vision -- Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make the native Rust eBPF engine render a real agent's kernel activity more legible -- v1: name the captured wire (declared server + undeclared-host ghost), pure/deterministic; v2: add three kernel surfaces (ppid process-tree, file_open, dns_query).

**Architecture:** v1 is a PURE userspace annotation layer over the already-captured broker recording -- the `connect:ip:port` token is untouched (the judge keeps counting), an annotation carries the declared name + an `undeclared` flag. v2 adds, surface by surface, a `#[repr(C)]` event + ring buffer + tracepoint in the eBPF program, drained and mapped into a new surface category the pure judge scores by presence/coverage.

**Tech Stack:** Python 3.11 (stdlib unittest, jsonschema), FastAPI, React/TS (vitest), Rust + aya (eBPF), the existing `recette/surface` judge and `discoveryprobe/` engine.

**Design:** `docs/plans/2026-06-21-ebpf-kernel-vision-enrichment-design.md`.

**Repo rules in force:** work on `main`, no branches/worktree (memory `work-on-main-no-branches`). One launcher `./recette.sh` (R19). Gates before done (R20): `make gates`, `./recette.sh test`, `make recette`, `./recette.sh console-build`, `./recette.sh console-test`, `./recette.sh smoke`. Determinism I4 (pure judge, replay test). Discovery ground-truth = invariant properties only. Conventional Commits, NO "Co-Authored-By: Claude".

---

# PHASE v1 -- userspace named-wire enrichment (no new eBPF, deterministic)

### Task 1: Pure endpoint map -- `build_endpoint_map`

**Files:**
- Create: `recette/surface/netmap.py`
- Test: `tests/test_surface_netmap.py`

Server registry entry shape (verified): `{id, system, mode: "mock_local"|"declared_url"|"real_saas", port?, url?, fqdn?, aliases?}`. A `mock_local` server runs on `127.0.0.1:{port}`; a `declared_url`/`real_saas` server carries a `url` (`host[:port]`, default port 443 for https).

**Step 1: Write the failing test**

```python
# tests/test_surface_netmap.py
"""v1 named-wire enrichment: map a captured connect endpoint to the declared
server, flag an undeclared host. Pure (I4) -- no clock, byte-stable on replay."""

from __future__ import annotations

import unittest

from recette.surface.netmap import (
    annotate_connect,
    annotate_recording,
    build_endpoint_map,
)

SERVERS = [
    {"id": "gh-mock", "system": "github", "mode": "mock_local", "port": 9101},
    {"id": "okta-mock", "system": "okta", "mode": "mock_local", "port": 9102},
    {"id": "real-oai", "system": "openai", "mode": "declared_url", "url": "https://api.openai.com"},
]


class BuildEndpointMapTest(unittest.TestCase):
    def test_mock_local_maps_loopback_port_to_id(self) -> None:
        m = build_endpoint_map(SERVERS)
        self.assertEqual(m["127.0.0.1:9101"], "gh-mock")
        self.assertEqual(m["127.0.0.1:9102"], "okta-mock")

    def test_declared_url_maps_host_default_https_port(self) -> None:
        m = build_endpoint_map(SERVERS)
        self.assertEqual(m["api.openai.com:443"], "real-oai")

    def test_empty_registry_is_empty_map(self) -> None:
        self.assertEqual(build_endpoint_map([]), {})
```

**Step 2: Run, verify it fails**

Run: `.venv/bin/python -m unittest tests.test_surface_netmap.BuildEndpointMapTest -v`
Expected: FAIL `ModuleNotFoundError: recette.surface.netmap`.

**Step 3: Minimal implementation**

```python
# recette/surface/netmap.py
"""Pure named-wire enrichment for the eBPF surface (v1).

The broker captures outbound connects as ``connect:ip:port`` tokens. This module
maps each endpoint back to a DECLARED server (the server registry / private DNS
names) so the cockpit shows ``gh-mock (127.0.0.1:9101)`` instead of a bare IP,
and flags a connect to an UNDECLARED host as a hardened ghost signal. Pure (I4):
no clock, no random, stable ordering -- byte-stable on replay. It NEVER changes
the detection verdict; it annotates alongside it.
"""

from __future__ import annotations

from urllib.parse import urlsplit

_DEFAULT_HTTPS_PORT = 443


def build_endpoint_map(servers: list[dict]) -> dict[str, str]:
    """Map ``"host:port" -> server id`` from the server registry. mock_local ->
    loopback ``127.0.0.1:{port}``; declared_url/real_saas -> the URL host:port
    (default 443 for https). Stable, deterministic."""
    out: dict[str, str] = {}
    for server in servers:
        sid = str(server.get("id") or "")
        if not sid:
            continue
        mode = server.get("mode")
        if mode == "mock_local" and server.get("port"):
            out[f"127.0.0.1:{int(server['port'])}"] = sid
        else:
            url = server.get("url")
            if not url:
                continue
            parts = urlsplit(url if "//" in url else f"//{url}")
            host = parts.hostname
            if not host:
                continue
            port = parts.port or _DEFAULT_HTTPS_PORT
            out[f"{host}:{port}"] = sid
    return out
```

**Step 4: Run, verify pass**

Run: `.venv/bin/python -m unittest tests.test_surface_netmap.BuildEndpointMapTest -v`
Expected: PASS (3 tests).

**Step 5: Commit**

```bash
git add recette/surface/netmap.py tests/test_surface_netmap.py
git commit -m "feat(surface): build_endpoint_map -- declared server endpoints for named wire (v1)"
```

---

### Task 2: `annotate_connect` + `annotate_recording`

**Files:**
- Modify: `recette/surface/netmap.py`
- Test: `tests/test_surface_netmap.py`

**Step 1: Write the failing tests** (append)

```python
class AnnotateConnectTest(unittest.TestCase):
    def setUp(self) -> None:
        self.m = build_endpoint_map(SERVERS)

    def test_known_endpoint_is_named_not_undeclared(self) -> None:
        a = annotate_connect("connect:127.0.0.1:9101", self.m)
        self.assertEqual(a, {"raw": "connect:127.0.0.1:9101", "name": "gh-mock", "undeclared": False})

    def test_unknown_endpoint_is_undeclared(self) -> None:
        a = annotate_connect("connect:203.0.113.7:443", self.m)
        self.assertEqual(a, {"raw": "connect:203.0.113.7:443", "name": None, "undeclared": True})

    def test_non_connect_token_is_passthrough_not_undeclared(self) -> None:
        # exec / future surface tokens are not connects: never flagged undeclared.
        a = annotate_connect("exec:dx-live-bot:42", self.m)
        self.assertEqual(a, {"raw": "exec:dx-live-bot:42", "name": None, "undeclared": False})


class AnnotateRecordingTest(unittest.TestCase):
    def test_groups_named_endpoints_per_agent_and_lists_undeclared(self) -> None:
        recording = {
            "status": "ok",
            "recordings": [
                {"agent_id": "dx-live-bot", "surfaces": {"ebpf_wire": ["connect:127.0.0.1:9101"]}},
                {"agent_id": "leak-bot", "surfaces": {"ebpf_wire": ["connect:203.0.113.7:443"]}},
            ],
        }
        out = annotate_recording(recording, SERVERS)
        self.assertEqual(out["wire_named"]["dx-live-bot"][0]["name"], "gh-mock")
        self.assertTrue(out["wire_named"]["leak-bot"][0]["undeclared"])
        self.assertEqual(out["undeclared_hosts"], ["203.0.113.7:443"])

    def test_replay_byte_stable(self) -> None:
        import json

        recording = {
            "status": "ok",
            "recordings": [
                {"agent_id": "b", "surfaces": {"ebpf_wire": ["connect:127.0.0.1:9102"]}},
                {"agent_id": "a", "surfaces": {"ebpf_wire": ["connect:203.0.113.7:443"]}},
            ],
        }
        first = json.dumps(annotate_recording(recording, SERVERS), sort_keys=True)
        second = json.dumps(annotate_recording(recording, SERVERS), sort_keys=True)
        self.assertEqual(first, second)

    def test_skipped_recording_is_empty_annotation(self) -> None:
        out = annotate_recording({"status": "skipped", "recordings": []}, SERVERS)
        self.assertEqual(out, {"wire_named": {}, "undeclared_hosts": []})
```

**Step 2: Run, verify fail** (`annotate_connect` not defined).

**Step 3: Implement** (append to `netmap.py`)

```python
def annotate_connect(token: str, endpoint_map: dict[str, str]) -> dict:
    """Annotate one surface token. A ``connect:host:port`` token resolves to a
    declared server name or is flagged ``undeclared``; any other token (exec,
    future surfaces) passes through un-flagged. Never raises."""
    if not token.startswith("connect:"):
        return {"raw": token, "name": None, "undeclared": False}
    endpoint = token[len("connect:") :]
    name = endpoint_map.get(endpoint)
    return {"raw": token, "name": name, "undeclared": name is None}


def annotate_recording(recording: dict, servers: list[dict]) -> dict:
    """Per-agent named wire annotations + the run-level undeclared-host list.
    Pure, deterministic, fail-safe (a malformed recording -> empty annotation)."""
    endpoint_map = build_endpoint_map(servers)
    wire_named: dict[str, list[dict]] = {}
    undeclared: list[str] = []
    for rec in recording.get("recordings", []) or []:
        agent_id = str(rec.get("agent_id") or "")
        tokens = (rec.get("surfaces") or {}).get("ebpf_wire") or []
        anns = [annotate_connect(str(t), endpoint_map) for t in tokens]
        if agent_id:
            wire_named[agent_id] = anns
        for ann in anns:
            if ann["undeclared"]:
                undeclared.append(ann["raw"][len("connect:") :])
    return {"wire_named": wire_named, "undeclared_hosts": sorted(set(undeclared))}
```

**Step 4: Run, verify pass**

Run: `.venv/bin/python -m unittest tests.test_surface_netmap -v`
Expected: PASS (all).

**Step 5: Commit**

```bash
git add recette/surface/netmap.py tests/test_surface_netmap.py
git commit -m "feat(surface): annotate_recording -- named wire + undeclared-host ghost (v1, pure I4)"
```

---

### Task 3: Attach `wire_named` + `undeclared_hosts` to the three capture endpoints

**Files:**
- Modify: `recette/api/routers/probe.py` (the `/capture`, `/process-capture`, `/process-capture-campaign` handlers)
- Test: `tests/test_process_capture_campaign.py` (extend) or `tests/test_api_probe.py`

DRY: add ONE private helper in `probe.py` and call it from all three handlers.

**Step 1: Write the failing test** (extend `tests/test_api_probe.py`'s capture test, or add a focused one): after a successful `/probe/capture`, the response carries `wire_named` and `undeclared_hosts`. Use the existing `_StubBroker` returning a recording with one known loopback connect (declare a matching server via `config_store`) and one undeclared connect; assert the response has `wire_named[agent]` named and `undeclared_hosts` non-empty.

> Note: `_StubBroker` recordings use `ebpf_wire` tokens. Seed a server through `app.state.config_store` (or use the default config) so `build_endpoint_map` has a matching endpoint. Verify the exact `list_servers()` content the test app exposes.

**Step 2: Run, verify fail** (response has no `wire_named`).

**Step 3: Implement** -- helper + wiring:

```python
# in recette/api/routers/probe.py
from ...surface.netmap import annotate_recording

def _attach_wire_names(result: dict, request: Request) -> dict:
    """Attach the v1 named-wire annotation (declared server + undeclared host)
    to a capture result. Pure/fail-safe: never changes the scorecard, never
    raises. config_store is the server registry source."""
    recording = result.get("recording")
    if isinstance(recording, dict):
        servers = request.app.state.config_store.list_servers()
        result.update(annotate_recording(recording, servers))
    return result
```

Then in each handler, wrap the returned dict:
- `/capture`: `out = ...; return _attach_wire_names(out, ...)` -- NOTE `/capture` currently has no `Request` param; add `request: Request` to its signature.
- `/process-capture`: `return _attach_wire_names(run_process_capture(...), request)`.
- `/process-capture-campaign`: `return _attach_wire_names(run_campaign_process_capture(...), request)`.

**Step 4: Run, verify pass**

Run: `.venv/bin/python -m unittest tests.test_api_probe -v`
Expected: PASS.

**Step 5: gates + commit**

```bash
make gates
git add recette/api/routers/probe.py tests/test_api_probe.py
git commit -m "feat(probe): attach named-wire annotations to capture endpoints (v1)"
```

---

### Task 4: Frontend types + client

**Files:**
- Modify: `console/src/api/client.ts` (extend `ProbeCaptureResult`)

**Step 1: Extend the type** (no test yet -- types verified by the render test in Task 5)

```typescript
export interface WireEndpoint {
  raw: string;
  name: string | null;
  undeclared: boolean;
}

export interface ProbeCaptureResult {
  recording: BrokerRecording;
  scorecard?: DetectionScorecard;
  wire_named?: Record<string, WireEndpoint[]>;
  undeclared_hosts?: string[];
}
```

(`ProbeCampaignCaptureResult extends ProbeCaptureResult` already, so it inherits.)

**Step 2: Build to verify types**

Run: `./recette.sh console-build`
Expected: tsc + vite OK.

**Step 3: Commit**

```bash
git add console/src/api/client.ts
git commit -m "feat(console): WireEndpoint type for named-wire capture result (v1)"
```

---

### Task 5: Render named endpoints + undeclared badge on `/discovery-exchange`

**Files:**
- Modify: `console/src/pages/discovery-exchange/index.tsx` (eBPF column), `discovery-exchange.css`
- Modify/Create fixture: `console/src/pages/discovery-exchange/__fixtures__/exchange-ebpf-named.fixture.json` (capture-result fixture with `wire_named` + an undeclared host)
- Test: `console/src/pages/discovery-exchange/index.test.tsx`

**Step 1: Write the failing render test** -- broker live, `processCapture`/`captureProbe` resolves a result carrying `wire_named: { "dx-live-bot": [{raw, name:"gh-mock", undeclared:false}], "leak-bot": [{raw, name:null, undeclared:true}] }` and `undeclared_hosts: ["203.0.113.7:443"]`. Assert: the named endpoint text `gh-mock` is rendered, and an `undeclared`/`host non declare` badge appears.

**Step 2: Run, verify fail** (`npx vitest run src/pages/discovery-exchange/index.test.tsx`).

**Step 3: Implement** -- store the capture result (not only the scorecard) in state; in the eBPF column, for each agent render its `wire_named` endpoints (`name (host:port)` or raw if `name` null) and render an `undeclared` badge for any `undeclared` endpoint / when `undeclared_hosts` is non-empty. Use existing CSS tokens (no hardcoded color, R16).

**Step 4: Run, verify pass** -- vitest green.

**Step 5: Commit**

```bash
git add console/src/pages/discovery-exchange/
git commit -m "feat(console): show named wire endpoints + undeclared-host badge (v1, R16)"
```

---

### Task 6: v1 gates + live proof in the smoke

**Files:**
- Modify: `scripts/smoke_console.py` (`_verify_discovery_exchange`)

**Steps:**
1. Extend the campaign/process launch check: after the eBPF capture, assert a NAMED endpoint (e.g. the seeded server id) appears in the eBPF column. Live broker present -> the named wire renders; replay fallback -> skip the named assertion gracefully.
2. Run the full gate set:
   - `make gates`
   - `./recette.sh test`
   - `make recette` (coverage guard -- v1 adds no surface category, so it must stay green unchanged)
   - `./recette.sh console-build` and `./recette.sh console-test`
   - With the live broker (`./recette.sh probe-grant-caps` once, `platform up`): `.venv/bin/python scripts/smoke_console.py --api http://127.0.0.1:$(cat .run/api.port) --console http://localhost:5173 --server-port 9131` -> SMOKE PASS, named endpoint visible.
3. Commit the smoke change.
4. Write a RETEX: `docs/tracking/retex/RETEX_named-wire-v1_2026-06-21.md` (memory rule `always-write-a-retex`; `docs/tracking/` is gitignored, R25 -- do NOT git add it).

```bash
git add scripts/smoke_console.py
git commit -m "test(smoke): assert named wire endpoint on /discovery-exchange (v1)"
```

**v1 DONE when:** all gates green + smoke shows a named endpoint live.

---

# PHASE v2 -- new kernel surfaces (privileged eBPF, one surface per increment)

> Each surface is a self-contained, gated, live-verified increment. Shared
> pattern per surface (do them in order: ppid, file_open, dns_query):
>
> 1. **common**: add the `#[repr(C)]` event struct + `from_bytes` + a size const in
>    `discoveryprobe/discoveryprobe-common/src/lib.rs`; Rust unit test for the
>    byte round-trip. `cargo test -p discoveryprobe-common`.
> 2. **eBPF**: add a `RingBuf` map + `#[tracepoint]` in
>    `discoveryprobe/discoveryprobe-ebpf/src/main.rs`; every fallible read drops
>    the event (do fallible reads BEFORE `reserve`, then unconditionally
>    write+submit -- the verifier rejects a leaked reserved entry). Build:
>    `./recette.sh probe-ebpf-build`.
> 3. **drain**: read the new ring buffer in `discoveryprobe/discoveryprobe/src/probe.rs`
>    `Session::drain`.
> 4. **map**: aggregate into `surfaces.<category>` in
>    `discoveryprobe/discoveryprobe/src/mapping.rs`; PURE Rust unit tests (no
>    kernel) for the new attribution/surfacing. `cargo test -p discoveryprobe`.
> 5. **judge**: accept the new surface category in `recette/surface` (scored by
>    presence/coverage, NOT opaque value); Python replay test (byte-stable).
> 6. **coverage guard**: wire the new surface so a missing one turns
>    `tests/test_coverage_guard.py` RED (no silent gap).
> 7. **UX**: a column/line on `/discovery-exchange` (R16 fixture + render-assert).
> 8. **live proof**: capture an agent exercising the surface; assert it. eBPF
>    load+attach on the CAP_BPF host (re-`probe-grant-caps` after the rebuild --
>    a rebuild drops file-caps).
> 9. Commit per surface; gates per surface.

### Task 7: surface `ppid` (process tree)

- **common**: `ExecEvent` gains `ppid: u32` (bump `EXEC_EVENT_SIZE`, update
  `from_bytes`). Round-trip test.
- **eBPF**: read `task->real_parent->tgid` via CO-RE
  (`aya_ebpf::helpers::bpf_get_current_task_btf` + vmlinux bindings, generated
  with `aya-tool` if not present). BTF verified present (`/sys/kernel/btf/vmlinux`).
- **map**: `mapping.rs` builds parent->children; a `connect` whose pid is a child
  of a matched agent pid is attributed to that agent. Extend `AgentProcessSpec`
  attribution. Pure tests: `ppid_chain_attributes_child_connect`.
- **judge/UX**: surface a `process_tree` hint (parent/child) on the agent line.
- **gates + live**: a child process of the launched agent that connects is still
  attributed. Commit `feat(probe): ppid process-tree attribution (v2)`.

### Task 8: surface `file_open`

- **common**: `FileEvent { pid, comm, path: [u8; 128] }` + round-trip test.
- **eBPF**: `#[tracepoint]` on `syscalls:sys_enter_openat`;
  `bpf_probe_read_user_str` the filename into the bounded buffer; drop on error.
- **drain/map**: new ring buffer -> `surfaces.file_open = [path,...]` per agent.
  Pure mapping test.
- **judge**: new surface category `file_open` (presence/coverage). Replay test.
- **coverage guard**: wire `file_open`.
- **UX**: a "fichiers" line per agent (R16 fixture + render-assert).
- **gates + live**: capture an agent that opens a known file; assert the path
  surfaces. Commit `feat(probe): file_open data-access surface (v2)`.

### Task 9: surface `dns_query` (last -- highest verifier risk)

- **common**: `DnsEvent { pid, comm, qname: [u8; 256] }` + round-trip test.
- **eBPF**: `#[tracepoint]` on `syscalls:sys_enter_sendto`/`sendmsg`, filter UDP
  dest port 53, parse the DNS question name with a BOUNDED, verifier-friendly
  loop (fixed max labels/length); drop on any read/parse failure.
- **drain/map**: `surfaces.dns_query = [qname,...]`. Link to the resolver: a qname
  that resolves to a declared server is named, else `undeclared` (reuse v1
  `netmap` semantics on names). Pure mapping test.
- **judge**: surface category `dns_query` (presence/coverage). Replay test.
- **coverage guard**: wire `dns_query`.
- **UX**: a "DNS" line per agent + undeclared flag (R16).
- **gates + live**: capture an agent resolving a known name; assert the qname
  surfaces. Prove eBPF load+attach on the host. Commit
  `feat(probe): dns_query qname surface (v2)`.

### Task 10: docs + RETEX (v2)

- Update `docs/runbooks/ebpf-live-capture.md` and `docs/runbooks/installation.md`
  with the new surfaces (what the engine now sees).
- RETEX under `docs/tracking/retex/` (gitignored, do NOT git add -- R25).
- Update memory `discoveryprobe-ebpf-reference` / `surface-detection-recette` if
  the surface set changed (verify the named files still exist first, R13).

---

## Verification (whole feature, before declaring done)

```
make gates
./recette.sh test
make recette
./recette.sh console-build
./recette.sh console-test
cargo test -p discoveryprobe-common && cargo test -p discoveryprobe   # from discoveryprobe/
./recette.sh probe-grant-caps      # one-time, re-run after any broker rebuild
./recette.sh platform up
.venv/bin/python scripts/smoke_console.py --api http://127.0.0.1:$(cat .run/api.port) --console http://localhost:5173 --server-port 9131
```

Live proof per phase: v1 -> a named endpoint (`gh-mock (127.0.0.1:9101)`) and an
undeclared-host badge on `/discovery-exchange`; v2 -> each new surface visible
for an agent that exercised it, captured by the live broker.
