# Runbook -- live eBPF capture (privileged discoveryprobe broker)

> Goal: run the **real** kernel eBPF capture (mode `live`) instead of the default
> non-privileged **replay** broker, so `/discovery-exchange` (eBPF source) and the
> Probe view show what the discoveryprobe Rust engine observes on the wire/exec
> tracepoints for a real agent.
>
> Status: the live path is BUILT and verified to compile/load-attempt in this
> repo. The only thing this runbook needs that an unprivileged agent cannot do is
> **CAP_BPF** -- loading/attaching an eBPF program requires it. Run the broker
> with privilege as below.

## Fast path (automated, reproducible) -- prefer this

The launcher now wires live end-to-end; no manual env. One-time host provisioning,
then `platform up` selects the live broker by itself (it reads the file-caps via
`_probe_live_capable` and records the chosen mode in `.run/probe.mode`, which the
API honours -- no `INSPECT_IA_AGENTS_PROBE_SOCKET`/`_MODE` to export):

```
./recette.sh discovery-build && ./recette.sh probe-ebpf-build
./recette.sh probe-grant-caps     # ONE-TIME (sudo): CAP_BPF on the broker binary
./recette.sh platform up          # auto-starts the LIVE broker, mode=live
curl -s http://127.0.0.1:8090/probe/status                 # -> "mode":"live"
curl -s -X POST http://127.0.0.1:8090/probe/process-capture -H 'content-type: application/json' -d '{"agent_id":"dx-live-bot","duration_ms":4000}'
# -> surfaces.ebpf_wire=["connect:127.0.0.1:9101"], scorecard.ok=true (PID-precise)
```

A broker rebuild drops the file-caps -> re-run `probe-grant-caps`. The manual
operator-socket path below stays valid (e.g. a broker on a different socket) but
is no longer required.

## Why a runbook (not automated)

The default platform launches the **replay** broker (Python,
`recette.platform.probe.replay_broker`, mode `replay`) -- deterministic, no
privilege (`cicd/platform.sh::probe_broker_start`). The **live** broker is the
Rust `discoveryprobe-broker`, the only CAP_BPF component. It does a real
`aya::Ebpf::load` + tracepoint attach (`discoveryprobe/src/probe.rs`). Without
CAP_BPF the load fails fail-safe -- **verified** here:

```
WARN discoveryprobe_broker::server: connection failed
  error="load bpf object: map error: failed to create map `CONNECT_EVENTS`
  ... Operation not permitted (os error 1)"
```

That EPERM is the proof there is no fabricated capture (R13/R14): no privilege ->
no capture, never a fake one.

## Prerequisites (verified present on the dev host)

- Linux with BTF: `/sys/kernel/btf/vmlinux` exists.
- Rust nightly + `bpf-linker` (the eBPF crate pins nightly via
  `discoveryprobe/discoveryprobe-ebpf/rust-toolchain.toml`).
- Ability to gain CAP_BPF (root via `sudo`, or `setcap` on the broker binary).

## 1. Build the eBPF object + the broker

```
./recette.sh probe-ebpf-build
```

Produces (paths are stable):
- eBPF object: `discoveryprobe/discoveryprobe-ebpf/target/bpfel-unknown-none/release/discoveryprobe-trace` (ELF eBPF, relocatable)
- broker: `discoveryprobe/target/release/discoveryprobe-broker`

## 2. Run the live broker with CAP_BPF

Pick a socket OUTSIDE the launcher's replay socket so the two never clash
(`.run/probe.sock` is the replay broker's). Use a manifest declaring the agents
you will capture by their process `comm` (`discoveryprobe-broker/manifest.example.json`
is a template: `{ "max_duration_ms": 5000, "agents": { "<id>": { "comm_marker": "<comm>" } } }`).

Option A -- least privilege (grant only the caps, then run unprivileged):

```
sudo setcap cap_bpf,cap_perfmon,cap_net_admin,cap_dac_read_search+ep discoveryprobe/target/release/discoveryprobe-broker
discoveryprobe/target/release/discoveryprobe-broker --socket /run/inspect_ia_agents/probe-live.sock --manifest discoveryprobe/discoveryprobe-broker/manifest.example.json --audit .run/probe-live.audit.jsonl --bpf-object discoveryprobe/discoveryprobe-ebpf/target/bpfel-unknown-none/release/discoveryprobe-trace
```

Option B -- run under sudo (simplest):

```
sudo discoveryprobe/target/release/discoveryprobe-broker --socket /run/inspect_ia_agents/probe-live.sock --manifest discoveryprobe/discoveryprobe-broker/manifest.example.json --audit .run/probe-live.audit.jsonl --bpf-object discoveryprobe/discoveryprobe-ebpf/target/bpfel-unknown-none/release/discoveryprobe-trace
```

The broker logs `broker listening socket=...` once ready. It detaches the eBPF
program on exit (Ctrl-C); nothing persists in the kernel.

## 3. Point the API at the live broker, restart

The API resolves the broker socket env-first; `INSPECT_IA_AGENTS_PROBE_MODE=live`
tags it live so the console never presents a replay as a live capture
(`recette/api/routers/probe.py::_resolve_socket`).

```
export INSPECT_IA_AGENTS_PROBE_SOCKET=/run/inspect_ia_agents/probe-live.sock
export INSPECT_IA_AGENTS_PROBE_MODE=live
./recette.sh api restart
curl -s http://127.0.0.1:8090/probe/status      # -> {"configured":true,...,"mode":"live"}
```

## 4. Drive it from the UX (recette agents only have the UX)

1. Run an agent whose process `comm` matches a manifest `comm_marker` (the agent
   must actually exec on the host so the exec/connect tracepoints fire).
2. Open `/discovery-exchange`, click the **eBPF** source toggle (now enabled,
   labelled `eBPF (live)`). The agents panel renders the broker's
   `DetectionScorecard`: an agent captured on no surface shows as **GHOST**.
3. Probe view (`/probe`) shows the raw broker recording.

## 5. Teardown

```
# stop the broker (Ctrl-C or kill its pid) -- the eBPF program detaches
unset INSPECT_IA_AGENTS_PROBE_SOCKET INSPECT_IA_AGENTS_PROBE_MODE
./recette.sh api restart      # back to the replay broker (default)
```

## Process-mode dashboard agents (the full live chain)

A dashboard/Lane B agent runs IN-PROCESS, invisible to eBPF. To capture one live:

1. **Make it eBPF-observable + make real connects.** Bind the agent to a
   `mock_local` server (so each action is a real localhost TCP connect) and
   launch it in PROCESS mode -- the console `/discovery-exchange` "Mode process
   (eBPF)" picker, or `POST /runs {"kind":"lane_b_process","params":{"agent_id":...}}`.
   The child process runs `recette.agent_proc`, sets its `comm` to the agent id
   (`prctl`), and (server-bound) goes through `ProxyForge` = real outbound TCP.
2. **Generate a matching manifest** so the broker allowlists that agent by the
   `comm` it will carry on its connect events:

   ```
   python -m recette.platform.probe.manifest_gen --agents <id1>,<id2> --out .run/probe-manifest.json
   export INSPECT_IA_AGENTS_PROBE_MANIFEST=$PWD/.run/probe-manifest.json
   ```

3. Grant caps once (step 2 above), `./recette.sh platform up` (the launcher
   starts the LIVE broker with that manifest, mode=live), then from the UX:
   eBPF toggle on `/discovery-exchange` -> capture around a process-mode run.

**PID-based capture (precise) -- DONE.** `POST /probe/process-capture
{"agent_id":...}` spawns the child, captures it by its exact pid (no reliance on
the 15-byte `comm`), and scores it. Verified live: `dx-live-bot` ->
`ebpf_wire: connect:127.0.0.1:9101`. The console "Mode process (eBPF)" picker on
`/discovery-exchange` drives the same path. Design:
docs/plans/2026-06-20-ebpf-live-process-mode-design.md.

## Notes

- Determinism (I4) applies to the pure judge, not to this measurement: a live
  capture is non-deterministic by nature; the source-agnostic judge
  (`recette/surface`) scores both the live recording and the deterministic
  replay identically.
- The console eBPF wiring (toggle -> `POST /probe/capture` -> broker ->
  `score_recording`) is already exercised against the replay broker in the
  Probe-view tests/fixtures; this runbook only swaps the broker for the
  privileged one.
- Single entry point (R19): build via `./recette.sh probe-ebpf-build`; the
  privileged launch is the only step outside `recette.sh`, by design (it needs
  CAP_BPF the launcher does not hold).
```
