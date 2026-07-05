# Runbook -- Agent inventory (discoveryprobe-inventory)

How a developer uses the `discoveryprobe-inventory` tool to identify AI agents in a
source tree in detail, recognize their **passport**
(`.inspect_ia_agents/manifest.json`), surface **shadow agents** (agent code with no
passport), and detect **multi-agent communication** (declared vs observed graph).

> Founding design (source of truth):
> `docs/plans/2026-07-04-discoveryprobe-inventory-design.md`. This tool complements the
> surface-detection recette (`docs/runbooks/surface-detection-recette.md`): the eBPF probe
> proves an agent is SEEN; the inventory says in detail WHO it is, what it DECLARES, and
> whether it is CONFORM.

## What the tool does

`discoveryprobe-inventory` is a **central correlator** (Rust crate, lib + binary) that
produces a deterministic (I4) `AgentInventory` report from three inputs:

1. a **static scan** of the source tree (parsed passports + agent code without a passport,
   detected by heuristics: SDK imports, entrypoint);
2. the **declared graph** of handoffs (manifests + MAF orchestration `team.json` files);
3. an optional **runtime observation** (`--capture`), the `ObservedInput` JSON drained
   from the probe (actions, egress, inter-agent IPC).

Correlation (`correlate.rs`) is a **pure function**: zero I/O, zero clock (I4). All
observed data arrives as a file input. Two identical scans produce byte-identical JSON
(replay test).

### The three passport states (central invariant)

Every agent carries a `passport.kind` -- the **single source of truth** the scanner
emits, never re-derived elsewhere:

| State | Meaning | Signal |
|-------|---------|--------|
| `present` | `.inspect_ia_agents/manifest.json` present AND valid against `corpus/schemas/agent-manifest.schema.json` | the manifest is fully parsed (kind, identity, capability_scope, handoffs) |
| `absent` | agent code detected, NO manifest anywhere in the tree -- the **shadow agent** | `Absent` carries the **evidence** (PyGithub / LLM SDK imports, entrypoint, provider env): no claim without proof (R13) |
| `invalid` | a manifest exists but fails schema validation | the validation **errors** are surfaced, never a bare boolean |

`present` does not mean `Conform`. Conformity is a distinct axis:
`Conform` | `NotObserved` | `Violations`. A **static-only** scan (no `--capture`) can
NEVER conclude `Conform` -- it yields `NotObserved` (fail-safe, never a false "conform").

### Multi-agent communication

The report carries a `comm_graph` with four lists:

- `declared_edges`: handoffs from manifests + `team.json` (the deduped union);
- `observed_edges`: inter-agent edges correlated from runtime IPC (pid -> agent via the
  fork tree);
- `undeclared_edges`: `observed - declared` = the **undeclared handoffs** (violation
  `UndeclaredHandoff`);
- `via_gateway_edges`: an edge whose destination is a known **gateway** agent (LiteLLM,
  mitmproxy -- config input R5, never hardcoded) is recorded here, not as an undeclared
  direct handoff.

Documented limit (never hidden): the probe sees the **edge**, not the content (TLS/payload
invisible -- topology is enough for "is there multi-agent comm" + handoff conformity).

## The CLI

A workspace binary, no arg-parsing dependency (JSON on stdout, errors on stderr; exit
codes 0 success, 2 usage, 1 other):

```
discoveryprobe-inventory scan <path> [--capture <file.json>] [--team <dir>] [--out <file>] [--trust <pubkeys.json>] [--now <rfc3339>]
```

| Argument | Role |
|----------|------|
| `<path>` | the source tree to scan (`scan::scan_tree_attested`) |
| `--capture <file.json>` | an `ObservedInput` JSON file (runtime observation). Absent = static-only scan, whose conformity can never be `Conform` |
| `--team <dir>` | a directory walked recursively (sorted) for its `team.json` files. The declared graph = passports + teams |
| `--out <file>` | write the JSON to that file instead of stdout |
| `--trust <pubkeys.json>` / `--now <rfc3339>` | OPTIONAL keyring + injected clock for the **attestation** axis (signed passport). Without both, a present `passport.json` is the fail-safe `untrusted`. Detail: `docs/runbooks/passport-recette.md` |

The binary also carries two passport subcommands (`passport issue`, `passport verify`)
documented in `docs/runbooks/passport-recette.md`.

Flags verified in `discoveryprobe/discoveryprobe-inventory/src/main.rs` (const `USAGE`
and `parse_args`).

### Shape of the `--capture` input (ObservedInput)

The `--capture` file is an `ObservedInput` (see `src/model.rs`): `recordings` (per-agent
captures), `observed_edges` (pre-correlated edges, unioned with those derived from IPC),
`observed_principals` (`(agent_id, observed principal)`), `ipc` (the reconciled
`IpcEvents`), `forks` (`(parent_pid, child_pid)`), `pid_agents` (`pid -> agent_id`),
`gateways` (agents treated as gateways). All optional (`#[serde(default)]`) except
`recordings`: a hook-only capture carries no IPC.

### Shape of the output (AgentInventory)

```
AgentInventory {
  schema_version,                       // "1.0"
  agents: [ AgentRecord {
    agent_id, passport, kind, declared, observed, conformity, evidence
  } ],                                  // sorted by agent_id (I4)
  comm_graph { declared_edges, observed_edges, undeclared_edges, via_gateway_edges },
  summary { with_passport, without_passport, invalid_passport, violation_count }
}
```

Every enum value is a **kind-tagged** object (the passport, the conformity, the
violations): the consumer dispatches on `value["kind"]`, never by shape guessing.

## Examples (verified in the CLI tests)

Static scan of the corpus PR-bot (one agent, never `Conform` when static):

```
discoveryprobe-inventory scan corpus/repos/gh-pr-bot/repo
```

Add a declared graph from a MAF team directory:

```
discoveryprobe-inventory scan corpus/repos/gh-pr-bot/repo --team corpus/maf_orchestration/correct/finance-approval-handoff-correct
```

Correlate with a runtime observation (the agent becomes `Conform` when the observed action
is within its scope):

```
discoveryprobe-inventory scan corpus/repos/gh-pr-bot/repo --capture discoveryprobe/discoveryprobe-inventory/tests/fixtures/capture-pr-bot.json
```

## How the recette consumes the inventory

- **The Python bridge** `recette/inventory_bridge.py` (`parse_inventory`) is a boundary:
  it maps the `AgentInventory` into `DiscoveryRisk` objects + a `passport_status` field
  (straight from `passport.kind`, never re-derived). Malformed input raises a clear
  `ValueError` -- never a silent empty list (fail-safe).
- **The reference adapter** (`ReferenceSourceScanAdapter`) produces the same fields: the
  Rust tool and the reference oracle must converge on the same ground-truth.
- **The discovery ground-truth** carries the `passport_status` invariant (never an opaque
  value like `canonical_agent_id` or an exact score -- R20). The harness asserts passport
  presence/absence, violation kinds, and edge counts.

### The corpus subjects

Two mono-axis (R20) ground-truth subjects exercise passport recognition:

- `corpus/repos/gh-shadow-agent/` -- real GitHub agent code (reads repos, opens PRs) with
  NO `.inspect_ia_agents/` -> expected `passport_status: "absent"`. The scanner must detect
  the agent via the code fallback AND report the passport absent: detecting the code but
  silently trusting the missing passport is the miss this subject guards.
- `corpus/repos/gh-invalid-passport/` -- a `manifest.json` present but stripped (missing
  `agent.identity` object): it parses as JSON but fails validation -> expected
  `passport_status: "invalid"`. A broken manifest reported as invalid, never silently
  trusted as a valid declaration.

## The second axis: attestation (signed passport)

The inventory carries TWO orthogonal axes. The manifest passport above (`present` /
`absent` / `invalid`) states what the agent DECLARES. A **second, independent axis**
states what an AUTHORITY attests: the `attestation` of a SIGNED
`.inspect_ia_agents/passport.json`, with four states `trusted` / `untrusted` /
`unsigned` / `malformed`. The scan emits it per agent when given a keyring and an
injected clock (`scan --trust <pubkeys.json> --now <rfc3339>`); without both, a present
passport is the fail-safe `untrusted` (never `trusted` without a keyring). The two axes
are independent: a shadow agent (`absent`) can carry a `trusted` credential, a `present`
manifest can be `unsigned`.

Emission (`passport issue`), verification (`passport verify`, with its exit-code
contract and the scope-overreach check via `--declared`), the attestation corpus
subjects (4 `trusted` positives + 3 mono-axis negatives), and the Rust/Python
equivalence oracle are covered in a dedicated runbook:
`docs/runbooks/passport-recette.md`.

## The API and the console

- **Endpoint**: `GET /probe/inventory` (`recette/api/routers/probe.py`) serves an
  `AgentInventory` under the `inventory` key (the client unwraps one key). It validates the
  output via `parse_inventory` before serving it: a malformed inventory is a 500, never a
  fabricated inventory.
- **Console**: the `InventoryPanel` (page **Probe eBPF**) renders, per agent: its id, the
  scanned code **evidence**, the **passport badge** (present / absent / invalid -- keyed off
  `passport.kind` alone, never off a non-empty violations list), the **attestation badge**
  (trusted / untrusted / unsigned / malformed -- a second orthogonal axis keyed off
  `attestation.kind` alone, `docs/runbooks/passport-recette.md`), the subject kind, and the
  conformity verdict. Below the table: the violations list and the communication graph
  (declared vs observed edges, undeclared in red, via-gateway apart). UI help: the panel's
  **? Aide** button (topic `inventory`).

## Building the tool

The inventory is a member of the `discoveryprobe/` workspace (see
`discoveryprobe/Cargo.toml`). The native host build compiles it:

```
./recette.sh discovery-build
```

This runs `cargo build --release` in `discoveryprobe/` and produces the binary
`discoveryprobe/target/release/discoveryprobe-inventory` (alongside
`discoveryprobe-catalog`). The privileged eBPF crate (`discoveryprobe-ebpf`) is EXCLUDED
from this host build (different target).

### The eBPF caveat (live inter-agent comm)

The static scan and `--capture` from a file need **no privilege**. To feed `--capture`
with live inter-agent comm, you need the eBPF probe, which needs `CAP_BPF` (and
`cap_dac_read_search`: aya attaches a tracepoint by reading a root-only file). Two steps,
once:

```
./recette.sh probe-ebpf-build
./recette.sh probe-grant-caps
```

`probe-ebpf-build` compiles the eBPF object + the CAP_BPF broker (never loads, no privilege
to compile). `probe-grant-caps` grants the caps to the broker (sudo -- the one privileged
step, a kernel requirement) so the launcher runs it unprivileged afterward. Without caps,
the runtime observation stays empty and conformity stays `NotObserved` (fail-safe, never
"conform by default"). Detail: `docs/runbooks/ebpf-live-capture.md`.

## Notes

- The inventory never mediates: the probe OBSERVES, it does not execute (I5). The broker
  stays capture-only; no business logic in the privileged daemon.
- Determinism (I4): `correlate.rs` is pure, everything is sorted/deduplicated, two scans
  give byte-identical JSON (replay test over a frozen fixture pair).
- Runtime absence is a first-class mode: static-only scan, observed fields empty,
  conformity `NotObserved` -- never a false `Conform`.
