# Runbook -- Proxy debug console (side-effect tracing, I5)

The side-effect proxy is the only path from agent logic to an external system
(invariant I5). This runbook covers the **debug tracing** layer that records each
proxy `execute()` and the **Monaco console** that displays it, plus the
**real_saas** wiring that lets a run execute through an allowlisted real forge.

## What it does

- A `TracingProxy` decorates ANY `ExternalSystemProxy` (lab or real) and records
  one `ProxyTrace` per `execute()`: the request intent (event id, agent, action,
  target system, resource, payload) and the outcome (`ok`, status code,
  `side_effect_hash`, error).
- Traces live in the SQLite debug store (`SqliteTraceRecorder` on
  `SqliteProxyStore`, retention by prune). The store is a **throwaway view** --
  the durable truth stays in the append-only audit log (I1).
- The console (`/proxy`) renders traces read-only in Monaco: a list on the left,
  a JSON inspector / JSONL stream on the right.

Determinism (I4): a trace carries no wall-clock value of its own. Ordering comes
from a monotone `seq`; `timestamp` is the event's already-captured logical clock.

## Enable it (parameterizable, R5)

Tracing is off by default (zero overhead). Turn it on with an environment
variable read at app startup:

```
INSPECT_IA_AGENTS_PROXY_DEBUG=on
```

Truthy values: `1`, `true`, `yes`, `on` (case-insensitive). Anything else is off.
When off, the proxy executes normally and **nothing is recorded** -- the console
shows a banner saying so rather than an empty list that looks like steady state.

## What gets traced

Two paths feed the same shared recorder:

1. **Gateway path** -- `POST /actions/execute` (and approval-driven execution).
   The gateway's side-effect proxy is wrapped at app construction.
2. **Lane B agent path** -- a registered agent bound to a `server` entry runs its
   tool calls through `ProxyForge`; that resolved proxy is wrapped too. So a real
   agent's side effects show up in the console.

An agent with **no** `server` binding uses the in-memory `LabForge`, which
produces no external side effect and is therefore not traced.

## The SQLite debug store (retention, persistence, fail-safe)

Both buffers (app traces AND wire flows) live in ONE SQLite database
(`SqliteProxyStore`, two tables, independent `seq` counters) replacing the
old in-memory rings:

| Variable | Default | Purpose |
|----------|---------|---------|
| `INSPECT_IA_AGENTS_PROXY_DB` | `.run/proxy_traces.db` | SQLite file path |
| `INSPECT_IA_AGENTS_PROXY_DB_MAX_ROWS` | `50000` | retention ceiling PER TABLE (`<= 0` disables the prune; an unparseable value falls back to the default, fail-safe) |

- **Retention by amortized prune**: after a committed insert whose rowid lands
  on the prune cadence, the oldest rows beyond `max_rows` are deleted. A prune
  failure is logged and swallowed (the insert already committed) and never
  sets `store_error`.
- **Persistence across restart**: the file survives an API restart -- a long
  campaign keeps its traces. Client cursors resync via `reset` (see the
  delta-poll contract below).
- **Hash at insert (wire)**: a governed flow's `side_effect_hash` is computed
  ONCE at insert and persisted as a column -- `GET /proxy/wire` reads it, it
  no longer recomputes it on every call.
- **Fail-safe `store_error`**: a broken store (full disk, corrupted database)
  NEVER blocks execution (I5) -- the recording fails, the trace / flow is
  dropped (it is a debug buffer), the failure message is surfaced as
  `store_error` on `GET /proxy/debug` (the console flags the degraded
  buffer), and it is cleared on the next successful insert.
- **DELETE keeps its purge semantics**: `DELETE /proxy/traces` /
  `DELETE /proxy/wire` empty the debug table; `seq` stays monotone
  (AUTOINCREMENT survives DELETE); the append-only audit log is untouched
  (I1). This store is the DEBUG buffer, never the event store.

## API

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/proxy/debug` | `{debug_enabled, trace_count, store_error}` (`trace_count` = SQL COUNT, never a full snapshot; `store_error` = last store failure, `null` when healthy) |
| POST | `/proxy/debug` | toggles tracing at runtime `{enabled: bool}` -> `{debug_enabled}` (operator action, logged via tracing, never written to the event store; 422 if non-bool) |
| GET | `/proxy/traces` | delta-poll: `since_seq` (cursor) + server-side filters `run_id`/`agent_id`/`target`/`outcome`/`q` + `limit` (`tail` for compat) -> envelope `{debug_enabled, traces, last_seq, total, reset}` |
| DELETE | `/proxy/traces` | discard the buffer (the audit log is untouched, I1) |
| GET | `/proxy/sessions/delta` | coalesced sessions-panel poll: traces + wire + reconcile in ONE call (see below) |

Example:

```
curl -s http://127.0.0.1:8080/proxy/debug
curl -s -X POST http://127.0.0.1:8080/proxy/debug -H 'Content-Type: application/json' -d '{"enabled":true}'
curl -s "http://127.0.0.1:8080/proxy/traces?since_seq=42&outcome=fail&limit=100"
curl -s -X DELETE http://127.0.0.1:8080/proxy/traces
```

### Delta-poll contract (since_seq / last_seq / total / reset)

`GET /proxy/traces` and `GET /proxy/wire` share the same incremental-poll
contract, evaluated in SQL (never a full snapshot re-filtered in Python):

- `since_seq`: the client cursor; only rows strictly newer than it are
  returned (ascending delta, oldest first).
- `last_seq`: the UNFILTERED table MAX(seq) -- the client's next cursor.
- `total`: the count of the FILTERED set ignoring `since_seq`/`limit`/`tail`
  (header counters without shipping the rows).
- `reset`: true when the client cursor is AHEAD of the server (buffer emptied
  by DELETE or store recreated); the server then re-serves the full current
  selection WITHOUT the cursor and the client resyncs in one round trip.
- `limit` keeps the first N rows of the ascending delta; `tail` (compat)
  keeps the last N, wins over `limit` and ignores `since_seq`.

Server-side filters per endpoint (AND-combined; `q` = case-insensitive
substring):

| Endpoint | Filters |
|----------|---------|
| `GET /proxy/traces` | `run_id`, `agent_id`, `target`, `outcome` (`ok` \| `fail`, any other value -> 422), `q` (action_type + resource + request_payload + response) |
| `GET /proxy/wire` | `run_id`, `host`, `method`, `status`, `q` (path + bodies) |

The source-menu badges are fed by the LIGHTWEIGHT status endpoints
(`GET /proxy/debug` -> `trace_count`, `GET /proxy/wire/status` ->
`flow_count`, `GET /proxy/reconcile/status` -> `{ok, bypass_count}`): SQL
COUNTs, never the full payload.

### GET /proxy/sessions/delta -- the coalesced sessions-panel poll

Replaces the sessions panel's three parallel requests per tick
(`/proxy/traces` + `/proxy/wire` + `/proxy/reconcile`) with ONE round trip:

```
GET /proxy/sessions/delta?since_seq=..&wire_since_seq=..&run_id=..&strict=true
-> {debug_enabled, traces, last_seq, reset,
    wire_flows, wire_last_seq, wire_reset,
    reconcile: {run_id, strict, ...}}
```

- INDEPENDENT cursors per side: `since_seq` for traces, `wire_since_seq` for
  wire -- each with the same `reset` semantics as the per-source endpoints; a
  stale cursor on one side never forces a resync of the other.
- The `run_id` asymmetry is BY DESIGN (mirroring the panel exactly): `run_id`
  scopes only the WIRE delta and the reconcile join; traces stay UNFILTERED
  (the panel groups all traces client-side).
- `strict` defaults to `true` (the strict per-flow hash join; `reconcile`
  carries the same shape as `GET /proxy/reconcile`).
- No `tail`/`limit` (the panel does not use them); both views go through
  redaction; read-only (I1).
- Reconcile takes its OWN recorder snapshots: a new wire flow may appear in
  the reconcile badge one poll tick before the wire delta -- benign, resolves
  on the next tick.

`POST /proxy/debug` lets you **toggle tracing from the UI** (a switch in the
"app traces" source sub-header) without restarting the app: it flips both the
`app.state` flag and the live `TracingProxy` (`set_enabled`). The boot default
stays `INSPECT_IA_AGENTS_PROXY_DEBUG` (R5).

## real_saas wiring

The proxy `router` (`resolve_proxy`) is pure: it reads no env and holds no
credentials, so a `real_saas` server entry raised `ValueError` by default. It now
accepts an injected `real_proxy_factory`:

- `recette/platform/proxy/real_proxy.py` provides `RealForgeProxy` (adapts a forge
  to `ExternalSystemProxy.execute`) and `build_real_proxy_factory(*, enable_writes=False)`.
- The factory builds an **allowlisted** real forge from the environment
  (`recette.realmode.build_real_forge`): token via `INSPECT_IA_AGENTS_<SYSTEM>_TOKEN`,
  allowlist via `INSPECT_IA_AGENTS_REAL_ALLOWLIST`, writes disabled unless explicitly
  enabled (R8).

Fail-safe (failure-modes): an allowlist rejection, a blocked write, a missing SDK
or any forge error is mapped to `ExecutionResult(ok=False, ...)` -- the proxy never
raises through the gateway and never falls back to the wrong target (I5).

Wire it at an impure call-site:

```python
from recette.platform.proxy.router import resolve_proxy
from recette.platform.proxy.real_proxy import build_real_proxy_factory

proxy = resolve_proxy(
    agent, servers, default_proxy,
    real_proxy_factory=build_real_proxy_factory(enable_writes=False),
)
```

Lab stays the default everywhere; real mode is opt-in and only ever touches
allowlisted test orgs.

## Tests

| Test | Proves |
|------|--------|
| `tests/test_proxy_tracing.py` | decorator records/returns verbatim, fail-safe, env toggle (retention now lives in the store) |
| `tests/test_proxy_store.py` | SQLite store: golden-field mapping, `store_error` (failure -> never raised, recovery), wire hash-at-insert, delta/filter/tail queries, clear + monotone `seq` |
| `tests/test_api_proxy_sessions_delta.py` | `GET /proxy/sessions/delta`: full snapshot without cursors, incremental deltas, `run_id` scopes wire not traces, independent resets, `strict` default, redaction |
| `tests/test_real_proxy.py` | success -> hash; allowlist/write/forge errors -> fail-safe |
| `tests/test_proxy_router.py` | real_saas uses the injected factory; no factory -> error (backward compat) |
| `tests/test_api_proxy_traces.py` | `/proxy/*` endpoints; debug on/off; tail; clear |
| `tests/test_api_proxy_traces_lane_b.py` | a REAL Lane B agent's side effects are traced (debug on) / not (off) |
| `console/src/pages/proxy/*.test.{ts,tsx}` | model helpers + R16 page contract against a real fixture |

## Failure modes

- Recording exception -> swallowed; `execute()` always returns the wrapped result
  (observability must never break the I5 path).
- Debug off -> no recording, no console data, banner shown.
- Retention reached -> the oldest rows are pruned
  (`INSPECT_IA_AGENTS_PROXY_DB_MAX_ROWS`); `seq` stays monotone; the audit
  log remains complete.
- Broken SQLite store -> execution is NEVER blocked: the trace / flow is
  dropped (debug buffer), the failure is surfaced as `store_error` on
  `GET /proxy/debug` and cleared on the next successful insert.

## Wire interception overlay (mitmproxy) -- the network-level view

The `ProxyTrace` above is the **application-level** view (the agent's intent at
the `ExternalSystemProxy` boundary). The **wire overlay** adds the
**network-level** view: the bytes actually on the wire of the agent -> target
traffic, captured by a real interception proxy (**mitmproxy**) running as an
OPTIONAL Docker overlay. Two altitudes of the same I5 side effect.

It is **off by default** and an ADD-ON, never a replacement: the deterministic
recette never routes through it (I4 unchanged), the home-grown `TracingProxy`
stays the default.

### In the UX

The `/proxy` page is driven by a source registry (top-of-page menu, deep-link
`?source=`). Four read-only sources:

- **app traces** -- the `ProxyTrace` list (intent + response),
  agent/target/run filters, Monaco viewer, plus a **recording on/off switch**
  (POST `/proxy/debug`, replacing the old passive banner).
- **wire (mitmproxy)** -- `WirePanel`: status, flow list, request/response
  detail, clear, plus an **overlay on/off button** (POST `/proxy/wire/overlay`).
  When the overlay is not configured the panel shows how to enable it.
- **reconciliation** -- the wire<->audit join (see below).
- **sessions** -- the agent<->server exchanges **grouped into sessions** (see
  the dedicated section below).

At the top of the page, a **mini-launcher** (`LaunchPanel`) launches a configured
runtime agent (POST `/runs` lane_b) and auto-switches to the **sessions** source
preselected on that run -- "launch an agent and watch it live in the proxy" in
one screen. From the cockpit, a "View in proxy" button deep-links a run to its
session (`/proxy?source=sessions&run=<id>`).

### Sessions view -- grouped exchanges + wire fusion

The **sessions** source (`SessionsPanel`) groups `ProxyTrace`s into SESSIONS
selectable by key (`run` / `agent` / `agent->target`). The grouping is PURE and
deterministic (I4: stable sort by `seq`, no clock; it handles concurrent runs
interleaved in the global buffer without cross-contamination). Each session lists
its exchanges; expanding an exchange shows the **request<->response** pair (intent
`action_type`+`resource`+`payload` AND the server response), and "full JSON"
opens the raw trace in Monaco.

**Wire fusion**: when the overlay is active, an exchange whose network bytes were
captured carries a **`wire (bytes)`** badge; clicking it opens the raw bytes
(method/host/path/status + bodies) in Monaco. The exchange<->flow join is keyed on
the canonical `side_effect_hash` (see run correlation below). Overlay off -> no
badge, the rest of the view is intact (graceful degradation).

Live: **1s** coalesced delta poll -- ONE `GET /proxy/sessions/delta` per tick
(traces + wire + reconcile, two independent cursors; see the contract in the
API section) instead of three parallel requests. Near real-time; no SSE push.
Read-only end to end (I1).

### Choosing the transport route (proxy selector)

A shared **`ProxySelector`** lets an operator pick the transport agent side
effects take -- **Direct (no proxy)** or **Wire (mitmproxy)** -- from the
windows that have a network console: the `/proxy` wire panel and the per-run
**Network logs** (cockpit `AgentRunModal`). It is backed by `GET`/`POST
/proxy/route`; the selection is held server-side (so every console reflects the
same active route) and applies to runs started afterwards. Transport only: the
route never changes the decision (allow/deny/escalate) or the recorded action
log (I4). Backed by `recette/platform/proxy/route.py` (`ProxyRouteRegistry`);
the run routers pass the active route's `wire_proxy_url` into the runner. The
initial route is `wire` when `INSPECT_IA_AGENTS_WIRE_PROXY` is set, else `direct`.

The console **AI backends** form (Agents tab) also carries a **LiteLLM gateway
(local)** preset that one-clicks an `openai_compat` backend pointing at the
LiteLLM overlay (`http://127.0.0.1:4000`); see `llm-gateway-litellm.md`.

### Architecture

```
agent --(HTTP proxy)--> [mitmproxy container] --> lab / real system
                             | addon POSTs each flow
                             v
                     API POST /proxy/wire --> SqliteWireRecorder (bounded debug store, I1)
                             ^
                Proxy page <--GET /proxy/wire (status + flows)
```

- `recette/platform/proxy/wire.py` -- `WireFlow` + `normalize_flow` pure function;
  the buffer is `SqliteWireRecorder` (store.py: bounded, monotone `seq`, throwaway).
- `scripts/mitm_wire_addon.py` -- mitmdump addon: normalizes each flow and POSTs
  it to the API ingest (fail-safe, never alters traffic).
- Endpoints: `POST /proxy/wire` (ingest), `GET /proxy/wire` (delta-poll:
  `since_seq` + filters `run_id`/`host`/`method`/`status`/`q` + `limit`,
  `tail` for compat -> envelope `{enabled, proxy_url, flows, last_seq, total,
  reset}`; each flow carries its PERSISTED `side_effect_hash`, computed at
  insert, for the sessions fusion), `DELETE /proxy/wire`,
  `GET /proxy/wire/status` (`flow_count` = SQL COUNT),
  `POST /proxy/wire/overlay {action: up|down}` (controls the overlay from the UI;
  see below).

### Run correlation (x-inspect-run-id)

So that the network bytes attach to a run/agent/session, the lab proxy injects
the request header **`x-inspect-run-id`** (the run's `run_id`). The mitmproxy
addon reads it and tags each `WireFlow` with that `run_id`. Wiring:
`resolve_proxy(run_id=...)` -> `LabHttpProxy(run_id=...)` -> the HTTP client's
default header. This is transport metadata: it never enters the decision path
(I4) and the lab ignores an unknown header. So `GET /proxy/wire?run_id=` returns
only one run's flows, and the reconciliation + sessions fusion correlate by run.

### Overlay control from the UI (POST /proxy/wire/overlay)

The wire panel's on/off button calls `POST /proxy/wire/overlay {action}`, which
runs `./recette.sh wire up|down`. **Deny by default** (fail-safe, R5): the API
starts docker ONLY if `INSPECT_IA_AGENTS_ALLOW_WIRE_CONTROL` is truthy (otherwise
403); an invalid action -> 422; the operator action is logged via tracing (never
into the event store). HONEST: the script STARTS/STOPS the container; routing the
agent traffic through it still requires the API to run with
`INSPECT_IA_AGENTS_WIRE_PROXY` (or the `wire` transport route, below) + CA trust
-- reported in `next_step`.

### Bring it up (R19, never hand-launch)

```
./recette.sh wire up
export INSPECT_IA_AGENTS_WIRE_PROXY=http://127.0.0.1:8083
./recette.sh api restart
```

The agent's lab-mode side effects (mock_local / declared_url) then route through
mitmproxy and show up in the wire panel. `./recette.sh wire down|status|logs`
manage the container; `wire ca` prints the CA path.

**Without restart**: the transport route registry already carries a `wire` target
(proxy_url `:8083`). After `./recette.sh wire up`, selecting the `wire` route
(`POST /proxy/route {target:"wire"}` or the `ProxySelector` in the UI) is enough
to route runs STARTED AFTERWARDS through the overlay -- no need for
`INSPECT_IA_AGENTS_WIRE_PROXY` + restart for the lab's HTTP traffic. (The restart
+ env stays necessary for real-system HTTPS via the CA, below.)

### HTTPS to real systems (real_saas)

mitmproxy decrypts HTTPS only if the client trusts its CA:

```
export INSPECT_IA_AGENTS_WIRE_CA="$(./recette.sh wire ca)"
# SDK forges (PyGithub / python-gitlab) honour the standard env instead:
export HTTPS_PROXY=http://127.0.0.1:8083 REQUESTS_CA_BUNDLE="$(./recette.sh wire ca)"
./recette.sh api restart
```

- `StdlibHttpClient` gained a `ca_bundle` seam; `RealSlackProxy` (Slack over
  StdlibHttpClient) routes through the overlay + CA from `INSPECT_IA_AGENTS_WIRE_*`.
- TLS verification stays ON -- the CA is **added**, never disabled.

### Determinism (I4)

The overlay is OFF in every deterministic recette and never sits in the
decision/replay path. A `WireFlow` carries no wall-clock value; ordering is the
recorder's monotone `seq`, exactly like `ProxyTrace`.

### Live proof

`scripts/smoke_wire.py` -- self-skips without Docker; otherwise brings the
overlay up, drives a request through it to the lab, and asserts the flow reaches
`GET /proxy/wire`.

### Wire tests

| Test | Proves |
|------|--------|
| `tests/test_wire_proxy.py` | WireFlow normalize/clamp, immutability (retention + monotone seq: `test_proxy_store.py`) |
| `tests/test_api_wire.py` | `/proxy/wire*` endpoints; ingest/list/clear/status; tail; run_id; 422 |
| `tests/test_api_wire_overlay.py` | `POST /proxy/wire/overlay`: deny by default (403), 422 invalid action, validation-before-gate ordering, subprocess mocked |
| `tests/test_wire_run_correlation.py` | `LabHttpProxy(run_id=...)` sets the `x-inspect-run-id` header; `resolve_proxy(run_id=...)` threads it; absent otherwise |
| `tests/test_api_wire_session_hash.py` | `GET /proxy/wire` enriches each flow with a `side_effect_hash` (governed -> str, else null) -- the sessions fusion key |
| `tests/test_api_proxy_debug_toggle.py` | `POST /proxy/debug` toggles the state + the TracingProxy at runtime; 422 on non-bool |

### Wire-vs-audit reconciliation -- detecting an unmediated (ghost-agent) path

Holding the two altitudes side by side turns the overlay into a detector for the
"ghost agent" / shadow-AI threat: an unregistered agent that talks straight to an
external system via native code, bypassing the `ExternalSystemProxy` (and thus the
Control Plane). Such a call produces a **network side effect with no audit event**.

The two views make it visible:

- the **audit chain** (append-only log, fed by the mediated `ProxyTrace`, I1/I5)
  is what went *through* the gateway;
- the **mitmproxy wire** is what was actually *on the network*.

So every flow seen on the wire should have a matching mediated event in the audit
log. A wire flow with **no audit counterpart** (a non-mediated target within its
run) is an **unmediated path** -- the loophole -- and is the signal to raise to the
Control Plane.

Status (implemented, allowlist + run-scoped join): `recette/platform/proxy/reconcile.py`
joins the wire view (`WireFlow`) with the audit view (`ProxyTrace`) by `run_id`
(`reconcile_run`); a flow to a non-mediated target (e.g. the `shadow-db-sink`
honeypot on `:9113`) is flagged as a bypass. Surfaced at `GET /proxy/reconcile` and
in the console (Proxy page, "reconciliation" tab). Proven end to end by the live
smoke `scripts/smoke_reconcile.py` (mitmproxy overlay up -> ghost probe writes
directly to `:9113` -> reconcile reports `ok:false` with the `:9113` bypass) and by
the deterministic unit/contract suites (`tests/test_reconcile.py`,
`test_api_reconcile.py`, `test_ghost_probe.py`, `ReconcilePanel.contract.test.tsx`).
The per-flow `side_effect_hash` join (ghost via an *allowlisted* target) is now
IMPLEMENTED (`reconcile_strict`, `GET /proxy/reconcile?strict=true` + a "strict"
toggle on the panel): every flow governed toward a mediated target must also
carry a `side_effect_hash` matching a `ProxyTrace`, otherwise
`bypass_reason=no_audit_event`. This stays a recette LAB: it *observes* the
unmediated path, it does not *enforce* a network block. Hard-blocking the direct outbound path (pod network isolation, plus
the boot-time identity handshake of I3) is the platform's job, not the simulation's.
The lab prepares and scores; enforcement is a separate layer.
| `tests/test_wire_routing.py` | proxy_url + ca_bundle seam; resolve_proxy threading; Slack wire env |
| `tests/test_mitm_addon.py` | addon flow normalization + fail-safe guards (no mitmproxy runtime) |
| `console/src/pages/proxy/WirePanel.contract.test.tsx` | R16 panel contract (real fixture, enabled/disabled) |

## Expert-debug toolkit (cockpit for debugging an agent comm)

Beyond the views, the `/proxy` console is a cockpit for debugging an agent
communication. Everything is client-side, pure (I4) and read-only (I1); the two
backend exceptions (latency, redaction) are VIEW transforms that never touch the
audit log.

### 1s delta poll + virtualized lists
- The app traces / wire / sessions panels poll in **1s deltas**
  (`useDeltaFeed`: full fetch on mount, then `since_seq` per tick, pure
  client-side merge, automatic resync on `reset`). Each tick only ships the
  NEW rows, never the whole buffer.
- The app traces and wire lists are **windowed** (`VirtualList`, fixed row
  height): only the visible window is rendered in the DOM, so a buffer of
  tens of thousands of rows stays smooth.
- **Smart follow**: when the operator scrolls away from the tail, tail-follow
  stops and a badge counts what lands ("N nouvelles traces -- reprendre le
  suivi" / "N nouveaux flux -- reprendre le suivi"); one click jumps back to
  live.
- The menu badges (per-source counters) come from the COUNT status endpoints
  (5s poll), never the full payload.

### Record, freeze, export
- **Recording toggle** ("app traces" source sub-header): `POST /proxy/debug
  {enabled}` -- start/stop hot, no restart.
- **Pause / Resume** (page-level button, `PAUSE` badge): freezes the poll of all
  3 sources to inspect cold; the backend store keeps recording, Resume catches
  up through the delta cursor.
- **Follow (tail -f)** on the app traces and wire lists: auto-scroll to the
  latest row (off when paused); see smart follow above.
- **Export**: `Export JSONL` on any source + `Export HAR` on wire (importable in
  devtools/Charles/Fiddler). Exports the current filter.
- **Copy as curl** per wire flow / per exchange: replays the call in one paste
  (safe shell escaping).

### Target the packets of interest
- **Filters + search**: wire (host/method/status/run + text in path+bodies), app
  traces (agent/target/run/outcome + text), sessions (run/agent/target grouping +
  text). The wire and app-traces filters are evaluated **server-side** (indexed
  SQL, see the delta-poll contract); changing a clause invalidates the cursor
  and restarts the feed. Filters are **deep-linkable** in the URL
  (`/proxy?source=wire&host=...&q=...`), shareable.
- **Pretty-print** of bodies + a **size indicator (UTF-8 bytes)** + a
  `(truncated)` marker when the body was clamped.

### See the detail + correlate
- **Latency** per exchange: `WireFlow.duration_ms` (computed by the mitm addon) +
  a waterfall bar. Wall-clock metadata on the wire view, never in the judge (I4).
- **Diff** two wire flows side by side (failure vs success).
- **Secret redaction** (default ON, `INSPECT_IA_AGENTS_PROXY_REDACT`): masks
  `Bearer`/`ghp_`/`sk-`/`xox`/`AKIA` + known `key:value` pairs on `GET
  /proxy/wire` + `/proxy/traces`. The audit log stays intact (I1),
  `side_effect_hash` preserved. Best-effort; the content-free receipts remain the
  cryptographic path.
- **Ghost / non-mediated badge** on a session exchange whose wire flow has no
  audit event (strict reconcile within the session).

### Read the agent at 3 altitudes (legibility-first)
Per exchange in the sessions view: **DECLARED** (manifest: target/capability) /
**DECIDED** (the LLM action-log: the chosen tool + the "why", via `GET
/runs/{id}/events`) / **DID** (application intent + server response + wire bytes).
See `docs/screenshots/sim/proxy-three-altitude-decision.png`.

### Replay-diff (regression debug, determinism I4)
The 5th source **replay-diff** replays a recording twice and diffs the
action-logs: an **IDENTICAL (I4)** badge if byte-stable, otherwise a left/right
line + `regression`. Proof on a real recording (`camp-pr.00.gh-pr-bot`) in
`docs/screenshots/sim/proxy-replay-diff.png`.

### Persistence (long run)
Traces and wire flows are persisted in the SQLite debug store
(`INSPECT_IA_AGENTS_PROXY_DB`, default `.run/proxy_traces.db`) and survive an
API restart; retention by `INSPECT_IA_AGENTS_PROXY_DB_MAX_ROWS` (default
50000 rows per table, amortized prune of oldest rows). A long run thus keeps
its packets without a JSONL rotation mechanism. A debug convenience, not a
second event store (I1) -- detail in the "SQLite debug store" section at the
top of this runbook.

### Reference screenshots
- `proxy-sessions-launch.png` -- launch an agent and land on its live session.
- `proxy-toolkit-filter-pause.png` -- text filter + Pause.
- `proxy-three-altitude-decision.png` -- the 3 altitudes per exchange.
- `proxy-replay-diff.png` -- replay-diff IDENTICAL (I4) on a real recording.

### Deferred (infra-gated, not built -- honest)
- **Live eBPF source in the session**: needs `CAP_BPF` + a probe; the `recording
  -> recette/surface` bridge exists for the recorded path.
- **SSE `/proxy/stream`**: known SSE-hang gotcha; the 1s delta poll + pause
  cover the need. Poll stays the deterministic default.
