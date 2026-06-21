# Design -- enrich the discoveryprobe kernel vision (named wire + new surfaces)

Date: 2026-06-21
Status: APPROVED (brainstorm), implementation pending
Invariants touched: I4 (deterministic judge), I5 (passive observation), discovery
ground-truth = invariant properties only.

## Goal

Deepen what the native Rust eBPF engine (`discoveryprobe/`) renders LEGIBLE about
a real agent, from least-privileged to deepest, without breaking the pure judge
(I4) or the passive fail-safe (a failed read drops the event, never disturbs the
traced process). Today the engine sees `exec` (pid+comm) and outbound `connect`
(ip:port). This design adds a named/declared view of the wire, then three new
kernel surfaces.

## Non-goals / boundary (repo law)

- Discovery ground-truth stays INVARIANT properties (detection, count/dedup,
  action/surface coverage, ghost, relative risk order, determinism, policy
  presence) -- NEVER opaque values (`canonical_agent_id`, exact score). v2 adds
  surface CATEGORIES, not hard-judged values.
- The judge is a pure function of the recording (no clock/random). A live
  capture is non-deterministic by nature (kernel measurement); the judge scores
  a FIXED recording byte-stably.
- One launcher (R19), zero hard dep beyond jsonschema (R20). The privileged
  broker is the only CAP_BPF component; v1 needs no new privilege.

## Phase v1 -- userspace enrichment (no new eBPF, deterministic)

Do NOT touch the eBPF program or the judge's counting logic. Add a PURE
annotation layer on top of the already-captured recording: the
`connect:127.0.0.1:9101` token stays as-is (the judge keeps counting the same);
alongside it we attach the DECLARED server name + an `undeclared` flag.

### Component: `recette/surface/netmap.py` (pure, I4)

- `build_endpoint_map(servers) -> dict[str, str]`: from `config_store.list_servers()`.
  `mock_local` -> `"127.0.0.1:{port}": id`; `declared_url`/`real_saas` -> `host:port`
  parsed from the URL. Stable order.
- `annotate_connect(token, endpoint_map) -> {raw, name|None, undeclared: bool}`:
  `connect:127.0.0.1:9101` -> `{raw, name:"gh-mock", undeclared:false}`; an endpoint
  absent from the registry -> `{name:null, undeclared:true}`.
- `annotate_recording(recording, servers) -> {wire_named: {agent_id: [annotation]},
  undeclared_hosts: [...]}`. Pure, no clock.

### Data flow

```
broker -> recording {ebpf_wire:["connect:127.0.0.1:9101"]}
  -> score_recording (UNCHANGED: counts surfaces)
  -> annotate_recording(recording, servers)  [NEW, pure]
  -> response: {recording, scorecard, wire_named:{agent:[{raw,name,undeclared}]},
                undeclared_hosts:[]}
```

Wired into the three capture endpoints (`/probe/capture`,
`/probe/process-capture`, `/probe/process-capture-campaign`): attach `wire_named`
+ `undeclared_hosts` to the response; the scorecard is unchanged.

### UX (`/discovery-exchange`, eBPF column)

Per agent, show the NAMED endpoint `gh-mock (127.0.0.1:9101)` instead of the bare
IP; a connect to an `undeclared` host -> a distinct badge `host non declare`
(hardened ghost, on top of the existing GHOST-agent verdict).

### Fail-safe

Empty registry or an unparsable token -> annotation `name:null` (never an
exception, never a 500). Never alters the detection verdict.

### Tests v1

- `tests/test_surface_netmap.py` (unittest stdlib): loopback port->id, declared_url
  host:port, unknown endpoint -> undeclared, REPLAY byte-stable (I4).
- R16: a capture fixture carrying `wire_named` + an undeclared host -> render-assert
  (named endpoint shown, undeclared badge).

## Phase v2 -- new kernel surfaces (privileged, BTF/CO-RE)

Common pattern per surface: a `#[repr(C)]` event in `discoveryprobe-common`
(+ `from_bytes` round-trip) -> a `RingBuf` map + tracepoint in `main.rs` (fallible
read -> drop, never disturb the traced process) -> drain in `Session` (`probe.rs`)
-> `mapping.rs` aggregates into `surfaces.<category>` -> a surface category in the
Python judge -> a UX column.

- **ppid (process tree)** -- at exec, read `task->real_parent->tgid` via CO-RE
  (`bpf_get_current_task_btf` + vmlinux bindings; BTF present on the host,
  verified `/sys/kernel/btf/vmlinux`). `ExecEvent` gains `ppid`. `mapping` builds
  parent->children; a `connect` from a pid that is a child of a matched agent pid
  is attributed to that agent. Hardens pid-match (a child with a different `comm`
  is still attributed).
- **file_open** -- tracepoint `syscalls:sys_enter_openat`, `bpf_probe_read_user_str`
  of the bounded path (128 bytes). `FileEvent{pid, comm, path}`. New surface
  `file_open` = data-access.
- **dns_query** -- tracepoint `sys_enter_sendto`/`sendmsg` filtered to UDP :53, parse
  the DNS query name (a bounded, verifier-friendly loop). `DnsEvent{pid, comm,
  qname}`. Linked to the resolver: qname -> declared server, else `undeclared`.
  SHIPPED LAST (highest verifier risk; prove load+attach on a CAP_BPF host).

### Determinism / ground-truth (v2)

The judge stays pure: surfaces are scored by presence/coverage, byte-stable on a
fixed recording. New surface categories enter the INVARIANT discovery
ground-truth (presence/coverage), never opaque values.

### Tests v2

- `mapping.rs` Rust unit tests: ppid-chain attribution, file_open surfacing, dns
  qname mapping (pure, no kernel).
- `discoveryprobe-common`: `from_bytes` round-trip for each new struct.
- Python judge: new surface categories scored (coverage); replay byte-stable.
- Coverage guard wired (no silent gap -- a new surface uncovered turns it RED).
- Live proof: smoke/runbook captures an agent that opens a file + resolves a name,
  asserts the surfaces; eBPF load+attach verified on the host (CAP_BPF).

### Risks (R13)

- ppid -> BTF required (present on host, verified). 
- dns parse -> the biggest verifier risk -> phased last, fail-safe drop.
- file_open path read -> bounded buffer, fallible read drops the event.

## Delivery order

v1 (userspace, deterministic) first, end-to-end with gates + live proof. Then v2
surface by surface: ppid, file_open, dns_query (last). Each surface is its own
small, gated, live-verified increment.
