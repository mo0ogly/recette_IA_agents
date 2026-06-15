# Ghost-Direct-DB Scenario -- end-to-end governance-bypass validation (design)

> The red-team bench validates whether governance can be **bypassed**. A scoring
> primitive (allowlist diff) and a sink (honeypot) are not, by themselves, that
> validation. This document defines ONE concrete scenario that runs the full
> chain end-to-end, so the bench produces a single, replayable proof that an
> unmediated path is detected.

## Goal

One named scenario, `ghost-direct-db-write`, that exercises every link of:

```
Unregistered Ghost Agent
  -> direct DB/disk attempt (bypasses ExternalSystemProxy)
  -> wire trace exists (mitmproxy records the egress)
  -> no matching audit event (wire flow with no ProxyTrace for its run)
  -> Control Plane alert (bypass_detected event, appended to the audit log, I1)
  -> deterministic replay (the frozen run replays to the same verdict, I4)
```

## What already exists (do not rebuild)

- **Sink (honeypot)**: `shadow-db-sink` server, `mode: honeypot`, `:9113`. Reuses
  `mock_server` + `ServerManager` + `recette.sh`. `build_allowlist` excludes it
  (only `mock_local` is mediated). Not a catalog domain -> coverage-guard green.
  (commit 48e2ce1)
- **Wire view**: `WireFlow` (seq, host, port, path, run_id) via the optional
  mitmproxy overlay + `POST /proxy/wire` ingest + `WireFlowRecorder`.
- **Audit view**: `ProxyTrace` (target_system, action_type, status,
  `side_effect_hash`, run_id), recorded by `TracingProxy` at the
  `ExternalSystemProxy` boundary -- the MEDIATED side-effect truth.
- **Detection primitive (slice v1)**: `reconcile()` pure, target-allowlist diff;
  `GET /proxy/reconcile`. (commits 6d4b9f5, e714833, 54ad09d)

## The refinement: step 4 is a wire<->audit JOIN, not just an allowlist

Slice v1 answers *"a flow went to a place nobody mediates"*. The scenario's
step 4 is the stronger, faithful statement: *"a wire trace exists with no
matching audit event"*.

**Join key (decided): `run_id` + mediated-target.** A `WireFlow` is EXPLAINED
when it shares the run's `run_id` AND its target (`host:port`) is a mediated
endpoint (the lab, or a `mock_local` server). Every remaining flow is a ghost /
unmediated path. The allowlist diff becomes a special case of this rule.

- The data supports it: both views carry `run_id`; the mediated set comes from
  `build_allowlist` (lab + `mock_local` servers).
- No reliance on `side_effect_hash` on the wire (the wire carries raw bytes, not
  the canonical hash) -- the join stays deterministic (I4).

**Honest scope of this key.** It detects the ghost that egresses to a
NON-mediated target -- precisely the `direct DB/disk attempt` of this scenario
(the `:9113` honeypot). A ghost that hits an ALLOWLISTED system directly (e.g. a
raw write to `:9101` without a `ProxyTrace`) is NOT caught by target alone; that
requires a per-flow `ProxyTrace`-existence join and is **phase 3** (documented,
not silently missing). YAGNI for the first end-to-end proof.

## Components to build

| Step | Artifact | Invariant |
|------|----------|-----------|
| 1 Ghost agent | `corpus/.../ghost-shadow-writer` -- a subject with NO identity binding to a registered `capability_scope` (I3 negative); declares nothing that permits a DB write | I3 |
| 2 Direct attempt | a real second egress: `StdlibHttpClient` POSTing `http://127.0.0.1:9113/shadow_db/write`, NOT via `ExternalSystemProxy` (that is the whole point: it escapes I5) | I2, I5 |
| 3 Wire trace | the mitmproxy overlay records one `WireFlow` to `:9113` (live, in the smoke) | -- |
| 4 No audit event | `reconcile_run(wire_flows, proxy_traces, mediated)` -- pure: a flow not explained by a mediated target within its run is a bypass | I4 |
| 5 Alert | DONE: `bypass_detected` is a compensatory `PlatformActionEvent` (deny, `EventKind.BYPASS_DETECTED`) appended via `POST /proxy/reconcile/raise` (idempotent by `side_effect_hash`); surfaced in `GET /proxy/reconcile` + the console. Proven live: `raised:1` then `raised:0`, event in `/audit/events`, chain `/audit/verify` ok | I1 |
| 6 Replay | DONE: the bypass events rebuild byte-stable from `(flows, ids, timestamp)` inputs (`tests/test_bypass_event.py::test_replay_is_deterministic`); being canonical events, replaying the stream reproduces them | I4 |

## Data flow

```
ghost-shadow-writer (run_id=R)
  |
  |-- StdlibHttpClient.POST :9113/shadow_db/write   (direct, no proxy)  --.
  |                                                                       |
  v                                                                  mitmproxy
ExternalSystemProxy (NOT taken for the ghost write)                       |
  |                                                                       v
  '-- (legit actions only) -> ProxyTrace(run_id=R)              WireFlow(run_id=R, :9113)
                                   \                                   /
                                    `------ reconcile_run -----------'
                                                 |
                                  flow :9113 has run_id=R but :9113 is
                                  not a mediated target  ->  BYPASS
                                                 |
                                   bypass_detected -> audit log (append, I1)
```

## Testing (TDD)

- **Unit (pure, deterministic, I4)** `tests/test_reconcile_run.py`: seed a mixed
  set of `WireFlow` (one to the lab, one to `:9113`) + `ProxyTrace` (one for the
  lab action) with the same `run_id`; assert `reconcile_run` flags only `:9113`,
  and that a frozen fixture replays byte-stable.
- **Endpoint** extend `tests/test_api_reconcile.py`: `GET /proxy/reconcile` joins
  the live `WireFlowRecorder` and `ProxyTraceRecorder` by `run_id`.
- **Alert append (I1)** `tests/test_bypass_event.py`: a detected bypass appends
  exactly one `bypass_detected` event; re-running does not mutate prior events.
- **Live proof (R14)** `scripts/smoke_reconcile.py`: overlay up -> ghost probe
  writes directly to `:9113` -> assert `/proxy/reconcile` reports the `:9113`
  bypass. Self-skips without the Docker overlay (no secret needed). **Status:
  PASSED live (2026-06-15)** -- "PASS -- bypass detected" with the `:9113` flow,
  proving steps 1-4 end to end on a real mitmproxy overlay.

## Coverage-guard / corpus rules

`shadow_db` is NOT a catalog domain (no `DOMAIN_MODULES`/`HANDLER_MODULES`
entry) -> D2/D4 untouched. `ghost-shadow-writer` is an identification negative;
its `violation_type` breaks exactly one dimension (mediation/identity), the
other three stay conform (recette-corpus mono-axis rule), and the negative-count
guard is updated in the same change (no silent gap).

## Out of scope (named, not forgotten)

- Phase 3: per-flow `ProxyTrace`-existence join (ghost via an allowlisted target).
- Real network enforcement: the lab OBSERVES the unmediated path; it never
  BLOCKS it (this is a recette bench, not an inline firewall).
- LLM-backend host allowlist for real-provider runs.

## UX (the console alert -- step 5 surfaced)

A `Reconcile` panel/tab on the network-debug console renders
`GET /proxy/reconcile`: `ok` badge + the `bypass_flows` table (run_id, target,
path). R16 contract gate: real fixture, render-and-assert, every state
(`ok` / bypass-present) covered. Coordinate R21 with the session editing `/sim`.
