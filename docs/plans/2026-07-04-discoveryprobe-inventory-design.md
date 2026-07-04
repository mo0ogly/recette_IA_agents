# Design: discoveryprobe-inventory -- detailed AI-agent identification, passport recognition, multi-agent communication detection

Date: 2026-07-04
Status: VALIDATED (brainstorm approved section by section)
Invariants concerned: I1 (broker audit unchanged), I3 (principal cross-check), I4 (pure correlator, byte-stable output), I5 (probe observes, never mediates), I6 (approval-gate violation surfaced)

## Goal

Extend the Rust discovery tooling so it:

1. identifies AI agents in detail (static source scan + runtime observation, correlated);
2. recognizes the agent passport (`.inspect_ia_agents/manifest.json`) when present, parses it fully, and checks declared vs observed conformity;
3. surfaces the ABSENCE of a passport (shadow agent: agent code or live agent with no manifest) and invalid passports (schema failures);
4. extracts the remaining identity/capability information (kind, declared identity, capability_scope, runtime, metadata);
5. detects multi-agent communication: declared handoff graph (manifests + MAF team.json) vs observed inter-process communication (eBPF), undeclared edge = violation.

## Decisions taken (brainstorm answers)

- Surface: static AND runtime, correlated (live agent without passport = shadow agent surfaced).
- Passport depth: full parse + declared/observed conformity check (not just presence).
- Multi-agent: declared graph + runtime comm, cross-checked.
- Consumers: recette harness (DiscoveryAdapter) AND console (probe/discovery page), with new corpus ground-truth subjects.
- Architecture: approach A -- one central correlator crate (`discoveryprobe-inventory`), existing crates minimally touched. Rejected: B (logic scattered across catalog/detect/ebpf/broker; business logic in the privileged broker is a bad boundary), C (Rust stays a raw sensor, intelligence lives in Python -- fails the "Rust tool identifies in detail" goal).

## Section 1 -- Architecture

New crate `discoveryprobe/discoveryprobe-inventory` (lib + bin), modules kept under the LOC ceiling:

```
discoveryprobe-inventory/
  src/
    lib.rs          # orchestration + public types
    manifest.rs     # parse .inspect_ia_agents/manifest.json (serde, kind git|maf)
    scan.rs         # filesystem walk: manifests + agent-code-without-passport heuristics
    graph.rs        # declared graph: manifest handoffs + MAF team.json
    correlate.rs    # PURE function: (declared, observed) -> AgentInventory
    report.rs       # deterministic JSON output (stable sorts, I4)
  src/main.rs       # CLI: inventory scan <path> [--capture recording.json] [--team dir]
```

Flow:

```
scan.rs  --> parsed manifests + passport-less agents --+
graph.rs --> declared handoff graph -------------------+--> correlate.rs (pure) --> AgentInventory JSON
CaptureRecording + IpcEvents (input files) ------------+
```

Boundaries:

- `correlate.rs` is pure: zero I/O, zero clock (I4). All observed data arrives as file input.
- eBPF extension lives in `discoveryprobe-ebpf` (new events), drained by the existing loader; inventory never touches the kernel.
- Broker unchanged (capture-only; no business logic in the privileged daemon).
- Runtime absent is a first-class mode: static-only scan, observed fields empty, conformity marked `not_observed` (never a false "conform").

## Section 2 -- Data model (AgentInventory output)

```rust
pub struct AgentInventory {
    schema_version: String,              // "1.0"
    agents: Vec<AgentRecord>,            // sorted by agent_id (I4)
    comm_graph: CommGraph,
    summary: InventorySummary,           // totals: with_passport, without, violations
}

pub struct AgentRecord {
    agent_id: String,                    // from passport, or derived id (path/principal hash) when absent
    passport: PassportStatus,            // Present(Manifest) | Absent{evidence} | Invalid{errors}
    kind: Option<AgentKind>,             // GitAgent | MafAgent (None without passport)
    declared: Option<Declared>,          // identity + capability_scope + handoffs (from manifest)
    observed: Observed,                  // actions/egress/subprocess/ipc (from CaptureRecording); empty when static-only
    conformity: Conformity,              // Conform | NotObserved | Violations(Vec<Violation>)
    evidence: Vec<Evidence>,             // file paths, detected SDK imports, pids
}

pub enum Violation {
    PassportAbsent,                      // agent code detected, zero manifest -- the shadow agent
    UndeclaredAction { action, source }, // observed outside capability_scope
    ModeEscalation { declared, observed },
    PrincipalMismatch { declared, observed },
    UndeclaredHandoff { from, to },      // comm edge outside declared graph
    ApprovalBypass { tool },             // approval=always tool invoked without gate (when trace available)
}

pub struct CommGraph {
    declared_edges: Vec<Edge>,           // manifest handoffs + team.json
    observed_edges: Vec<Edge>,           // IPC/localhost correlated pid->agent
    undeclared_edges: Vec<Edge>,         // observed - declared = violations
}
```

Key points:

- `PassportStatus::Absent` carries EVIDENCE (why we believe it is an agent: PyGithub/LLM SDK imports, entrypoint, provider env vars) -- no machine claim without proof (R13 applied to the tool).
- `Invalid` means a manifest exists but fails `corpus/schemas/agent-manifest.schema.json`; validation errors are surfaced, not a bare boolean.
- `NotObserved` is distinct from `Conform`: a static-only scan can NEVER conclude conformity.
- Everything sorted/deduplicated: two identical scans produce byte-identical JSON (replay test).
- Python side: a thin adapter maps `AgentRecord` -> `DiscoveryRisk` plus a new `passport_status` field; corpus ground-truth stays invariant-based (presence/absence, count, expected violation kinds -- never opaque values, R20).

## Section 3 -- eBPF extension: seeing inter-agent communication

Today only outbound `connect` is traced: we see an agent talk, never who listens. Additions in `discoveryprobe-ebpf`:

| New tracepoint | Event (discoveryprobe-common) | Purpose |
|---|---|---|
| `sys_enter_bind` / `sys_enter_listen` | `ListenEvent { pid, comm, port \| unix_path }` | which pid serves which local port/socket |
| `sys_exit_accept4` | `AcceptEvent { pid, comm }` | confirm the active server side |
| `connect` extended to AF_UNIX | `UnixConnectEvent { pid, comm, path[108] }` | Unix-socket comm (local MCP, gRPC) |

Correlation (in `correlate.rs`, userspace, pure):

```
client: ConnectEvent pid_A -> 127.0.0.1:8xxx
server: ListenEvent pid_B on :8xxx
fork tree: pid_A -> agent_X, pid_B -> agent_Y
=> observed_edge { from: agent_X, to: agent_Y, transport: tcp_localhost }
```

Same for AF_UNIX by `path` match. An observed edge absent from the declared graph -> `UndeclaredHandoff`.

Assumed limits (documented, not hidden):

- We see the EDGE, not the content (TLS/payload invisible -- topology is enough for "is there multi-agent comm" + handoff conformity).
- Two agents behind a shared localhost proxy/gateway produce edges to the proxy, not between each other. Marked `via_gateway` when the destination pid is a known gateway process (LiteLLM, mitmproxy) -- never silently inferred.
- `#[repr(C)]` structs, ring buffers like the existing ones, drop-on-full (never block the agent), zero kernel alloc.
- Failure mode: probe unavailable / missing caps -> `observed` empty + `conformity: NotObserved` (fail-safe, never "conform by default").

## Section 4 -- Integration: recette + console + corpus

Corpus (new ground-truth subjects, mono-axis R20):

- `corpus/repos/gh-shadow-agent/` -- real agent code (SDK imports, entrypoint) WITHOUT `.inspect_ia_agents/` -> expected `PassportAbsent`.
- `corpus/repos/gh-invalid-passport/` -- manifest present but schema-broken -> expected `Invalid`.
- Multi-agent subject: a team with one observed handoff outside the declared graph -> expected `UndeclaredHandoff` (frozen deterministic `CaptureRecording` + IPC events fixture).
- Ground-truth = invariants only: `passport_status`, violation kinds, counts -- never exact hashes/scores.

Python harness:

- `recette/adapters.py`: `AgentInventory` -> extended `DiscoveryRisk` mapping (+ `passport_status`). The reference adapter is updated to produce the same fields (Rust tool and reference must converge on the same ground-truth).
- `discovery_harness`: new invariant assertions (passport, violations, edges).
- Coverage guard extended: an unwired passport/comm subject = red test.

Console (full R16):

- Enriched probe/discovery page: agents table with passport badge (present/absent/invalid), violations, comm graph (declared vs observed edges, undeclared in red).
- REAL captured fixture payload in `__fixtures__/`, render-and-assert, envelope unwrap, all badge variants covered.

Build/CLI wiring:

- `cicd/checks.sh discovery-build` covers the new crate (same workspace).
- CLI: `discoveryprobe-inventory scan <path> [--capture f.json]` -- a workspace binary, launched via recette.sh/make like the others.

Gates before done: `cargo fmt` + `clippy -D warnings` + `cargo test` (incl. byte-identical replay test), `./recette.sh test`, `make recette`, `console-build`/`console-test`, smoke when a console flow is touched. Docs: runbook + Docusaurus fr+en + UI help topic (P1 done = docs + help).

## Testing summary

- Rust: unit tests per module; replay test asserting byte-identical `AgentInventory` on a frozen fixture pair (scan tree + capture file); schema-validation tests for `manifest.rs` (valid git, valid maf, invalid).
- Python: unittest for the adapter mapping + harness assertions; coverage-guard extension.
- Console: vitest render-and-assert on the real fixture; smoke flow for the enriched page.
