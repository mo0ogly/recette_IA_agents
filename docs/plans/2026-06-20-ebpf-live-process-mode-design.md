# Design -- live eBPF capture of agents from the UX (process-mode + auto broker)

Date: 2026-06-20
Status: DESIGN (chantier 2). Chantier 1 (hook-surface live discovery from the UX)
is DONE and shipped (see below).

## Context

We want, from the console only (recette agents have nothing but the UX), to
launch an agent, see its agent<->server exchanges, and have the discovery engine
identify it -- including the **eBPF (wire)** surface of the native Rust probe,
not only the hook surface.

### What already works (chantier 1, shipped)

The HOOK surface is live from the UX for the in-process Lane B agents:
- launch from `/campaigns` (or `/agents`) -> `GatewayForge`/`ProxyForge` record a
  `ProxyTrace` per governed action (commit a0af01c made the server-less governed
  path traced too);
- `/proxy` shows the real exchange (app + wire double console);
- `/discovery-exchange` shows the agent **DETECTE** and each exchange
  **identified** vs a wire-only **ghost** (commits 4bfc211, a0af01c).

This is the correct "discovery sees our agent" signal for **in-process** agents.

### The hard limitation this chantier must solve

The eBPF surface (`discoveryprobe/src/probe.rs`) attaches to the `sched_process_exec`
and `tcp connect` tracepoints and reports, per **OS process**, `(pid, comm)` and
outbound `(daddr:dport)`. The broker matches an agent by its **`comm`** (the
kernel process name, <= 15 bytes; `discoveryprobe-broker/src/manifest.rs`,
`comm_marker`).

Our dashboard / Lane B agents run **in-process** inside the API's Python process.
They never `exec` as a distinct process, so the eBPF tracepoints see `python3`,
not a per-agent `comm`. **Therefore the eBPF surface cannot attribute an
in-process agent, regardless of CAP_BPF.** This is architectural, not a
privilege issue. (Verified: broker does a real `aya::Ebpf::load`; without CAP_BPF
it fails fail-safe with EPERM on the `CONNECT_EVENTS` map -- no fabricated
capture, R13/R14.)

To make eBPF observe an agent, the agent must run as a **separate OS process with
a known `comm`**. The corpus surface subjects already model this; the dashboard
launch does not.

## The chantier (coupled -- both halves or neither)

### Part A -- process-mode agent launch (so eBPF can see it)

Add a launch mode where a Lane B agent runs as its own OS process whose `comm`
is the agent id, captured by the broker by `pid` (precise) and/or `comm`.

- New entrypoint `python -m recette.agent_proc --agent-id <id> [--stub <file>]`
  that runs the SAME `recette.lane_b.run_agent` loop the in-process runner uses
  (one engine, no fork of logic; I4 unchanged).
- `comm` mechanism (MUST be verified on the host, needs a real capture):
  - the exec tracepoint reads `comm` AT exec = the interpreter basename
    (`python3`), so argv tricks (`exec -a`) do NOT change `comm`;
  - `prctl(PR_SET_NAME, <id>)` right after start changes `comm` for events AFTER
    it (the `connect` tracepoint), but the exec event keeps `python3`;
  - robust option: launch via a per-agent argv0/binary or a renamed hardlink of
    the interpreter to `<id>` (<=15 bytes) so the exec event itself carries the
    id. DECISION DEFERRED until measured under CAP_BPF (do not guess -- R13).
  - precise alternative: match by **pid** (the launcher knows the child pid) and
    add a `pid`-based capture request to the broker, sidestepping `comm`
    truncation/collision entirely. PREFERRED if the broker protocol can carry a
    pid (small broker change).
- The launcher hands the live broker a manifest generated from the launched
  process (`{agent_id: {comm_marker | pid}}`), bounded to the run window.

### Part B -- launcher auto-selects the live broker (one-time grant, then UX)

- One-time provisioning (irreducible kernel requirement, NOT per-use bricolage):
  `./recette.sh probe-grant-caps` -> `sudo setcap cap_bpf,cap_perfmon,cap_net_admin+ep`
  on `discoveryprobe/target/release/discoveryprobe-broker`. The operator runs it
  once; afterwards the broker runs unprivileged (caps on the file).
- `cicd/platform.sh::probe_broker_start` chooses:
  - LIVE Rust broker on the canonical socket IF the binary exists, the eBPF
    object is built, AND `getcap` shows `cap_bpf` -> write `.run/probe.mode=live`;
  - else the Python REPLAY broker (today's default).
- API mode wiring: `recette/api/routers/probe.py::_resolve_socket` reports the
  live mode for the canonical socket by reading `.run/probe.mode` (today it
  hardcodes `replay` for the canonical socket). Then `/probe/status.mode = live`
  and the console eBPF toggle is enabled and truthful.

### Part C -- console (no new bricolage)

- `/agents` / `/campaigns` launch gains a "process mode (eBPF-observable)"
  option that posts the process-mode run.
- `/discovery-exchange` eBPF toggle drives `POST /probe/capture` around the run
  window and renders the broker `DetectionScorecard` (the existing wiring; only
  the broker swaps from replay to live).

## Verification gates (what proves each part -- no claim without these)

1. Part A determinism: a process-mode run produces the SAME judged action log as
   the in-process run (replay test, I4). VERIFIABLE WITHOUT CAP_BPF.
2. Launcher selection: unit/shell test that `probe_broker_start` picks live iff
   `getcap` shows the cap, else replay; `.run/probe.mode` reflects it.
   VERIFIABLE WITHOUT CAP_BPF (mock getcap).
3. API mode: `/probe/status.mode == "live"` when `.run/probe.mode=live`.
   VERIFIABLE WITHOUT CAP_BPF.
4. **Real kernel capture: REQUIRES the one-time `probe-grant-caps`.** Then, from
   the UX: launch a process-mode agent, eBPF toggle on `/discovery-exchange`
   shows it (or a ghost) from the live broker. This final proof is the
   operator's one-time-grant gate -- it cannot be produced by an unprivileged
   session (honest boundary, R14).

## Out of scope / non-goals

- Changing the hook surface (chantier 1 stands as the in-process live signal).
- Making the in-process agent eBPF-observable without a process (impossible by
  the kernel surface definition).

## Findings during implementation (A+B+C shipped)

A+B+C are implemented and verified without CAP_BPF (process entrypoint + replay
test; launcher live/replay auto-select + `/probe/status` mode; `/runs`
kind=lane_b_process + UX picker). Two further limitations surfaced that gate a
*meaningful* live capture (beyond the irreducible one-time cap grant):

1. **No real connects from the in-memory lab.** The process-mode agent runs the
   deterministic `dry_run_lane_b` against the in-memory `LabForge`, so it makes
   NO real outbound TCP -- the eBPF `connect` surface would be empty. A
   meaningful wire capture needs the process to make real connects (bind it to a
   `mock_local` HTTP server so each action is a real localhost TCP connect, or
   real_mode). Follow-up: a process-mode variant that uses `ProxyForge` over a
   real socket.
2. **Attribution still by `comm`.** The broker manifest matches `comm_marker`;
   `prctl(PR_SET_NAME)` only renames AFTER exec (the exec event keeps the
   interpreter name). A generated manifest must carry the agent's real `comm`,
   or -- preferred -- add a **pid-based** capture request (the launcher knows the
   child pid). Until then a live capture matches coarsely.

So the shipped A+B+C is the verified scaffolding; a fully meaningful live eBPF
capture of a dashboard agent additionally needs: the one-time grant + a
pid/comm-correct manifest + the agent making real connects.

### Both gaps now ADDRESSED (verified without CAP_BPF)

1. **Real connects** -- `recette.agent_proc` / `run_agent_process(agent_cfg, servers)`
   runs a SERVER-BOUND agent through the real `ProxyForge` (HTTP to the bound
   `mock_local` server), so each action is a real outbound TCP connect. Verified:
   `test_agent_proc.AgentProcServerBoundTest` asserts a stub lab received the real
   POSTs. `make_process_run_runner` passes the servers registry; the server-less
   path stays the deterministic in-memory run (replay test intact).
2. **comm match** -- `recette.platform.probe.manifest_gen.build_manifest` emits
   `comm_marker = agent_id[:15]`; `agent_proc` sets `comm` via `prctl` BEFORE the
   run, so the connect events captured during the run carry that name and match.
   Verified: `test_probe_manifest_gen`. The runbook wires
   `INSPECT_IA_AGENTS_PROBE_MANIFEST` to the generated file.

Remaining (not blocking): pid-based capture request (more precise than comm).

### LIVE PROVEN FROM THE UX (2026-06-20)

After the one-time `probe-grant-caps` (caps: `cap_bpf,cap_perfmon,cap_net_admin,
cap_dac_read_search+ep` -- the last needed because the tracepoint id under
`/sys/kernel/tracing` is root-only and caps do not bypass filesystem DAC), the
launcher started the LIVE broker (`/probe/status.mode=live`). From the console
`/discovery-exchange`, picking `dx-live-bot` and clicking "Lancer (process)"
launched the process-mode run AND captured it in one window. The Rust eBPF
broker captured a REAL connect:

    recording: {"agent_id":"dx-live-bot","surfaces":{"ebpf_wire":["connect:127.0.0.1:9101"]}}
    scorecard: ok, detected_per_surface={ebpf_wire:1}, false_negatives=[]

rendered in the UX as "ebpf_wire DETECTE 1 agent(s) vu(s) (capture noyau)"
(docs/screenshots/sim/dx-ebpf-live.png). The discovery engine SEES a real agent's
real network connect, live, entirely from the UX after a one-time host grant.

## Sequencing

B and C are inert/no-op until A lands and caps are granted, so order: A (process
entrypoint + replay test) -> broker pid/comm matching -> B (launcher + API mode)
-> C (console) -> operator grant -> live UX proof.
