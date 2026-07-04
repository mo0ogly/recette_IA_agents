# discoveryprobe-inventory Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** A Rust discovery tool that identifies AI agents in detail: parses the agent passport (`.inspect_ia_agents/manifest.json`), surfaces its absence (shadow agent) or invalidity, cross-checks declared vs observed behaviour, and detects multi-agent communication (declared handoff graph vs observed IPC edges).

**Architecture:** New workspace crate `discoveryprobe-inventory` with a pure correlator (`(declared, observed) -> AgentInventory`, I4). eBPF crate gains listen/accept/AF_UNIX events for inter-agent comm. Python harness maps `AgentInventory` to `DiscoveryRisk` (+`passport_status`); corpus gains ground-truth subjects; console gains an inventory panel (R16).

**Tech Stack:** Rust (serde, existing discoveryprobe workspace), aya eBPF (existing toolchain), Python stdlib unittest, React/TS console.

**Design doc:** `docs/plans/2026-07-04-discoveryprobe-inventory-design.md` (read it first).

**Verified facts the plan relies on (do not re-derive):**
- Workspace members: `discoveryprobe/Cargo.toml` (`discoveryprobe-ebpf` is EXCLUDED, built separately).
- Repo passport shape (verified `corpus/repos/gh-pr-bot/repo/.inspect_ia_agents/manifest.json`): `{schema_version, agent: {name, description, target_system, identity: {auth_method, principal}, capabilities: [{action, mode, resources}]}}`.
- Unified corpus manifest schema (kind git_agent|maf_agent, handoff capability): `corpus/schemas/agent-manifest.schema.json`.
- Reference oracle for declared-vs-observed logic to mirror: `recette/adapters.py` (`ReferenceSourceScanAdapter`, `DiscoveryRisk`, `CapabilityViolation` kinds `undeclared_action|mode_escalation|out_of_scope_resource`).
- Discovery harness invariants: `recette/discovery_harness.py` (detection, determinism, count, actions, target, policy, ordering).
- Event struct pattern (repr(C), from_bytes, host tests): `discoveryprobe/discoveryprobe-common/src/lib.rs`.
- Deterministic recording pattern (BTreeMap, normalise, to_json): `discoveryprobe/discoveryprobe-core/src/lib.rs`.
- Console probe page: `console/src/pages/probe/` (panel + test + `__fixtures__/` pattern).
- Build entry: `cicd/checks.sh` case `discovery-build` (line ~42) builds the host workspace.

**Rules in force:** R2 (fmt+clippy -D warnings), R3/TDD, R12 (code+comments English), R20 (mono-axis corpus, invariant ground-truth, stdlib unittest), R16 (console contract gate), R10 (no emoji), file-size ceiling 800 LOC .rs / 400 .tsx. Commit after every green task.

---

## Phase 1 -- crate skeleton + passport parsing (static)

### Task 1: Create the crate, wire the workspace

**Files:**
- Create: `discoveryprobe/discoveryprobe-inventory/Cargo.toml`
- Create: `discoveryprobe/discoveryprobe-inventory/src/lib.rs`
- Modify: `discoveryprobe/Cargo.toml` (add member)

**Step 1:** Add `"discoveryprobe-inventory"` to `[workspace] members` in `discoveryprobe/Cargo.toml`.

**Step 2:** Create `discoveryprobe/discoveryprobe-inventory/Cargo.toml`:

```toml
[package]
name = "discoveryprobe-inventory"
version = "0.1.0"
edition = "2021"
description = "Agent inventory: passport recognition, shadow-agent surfacing, declared-vs-observed conformity, multi-agent comm graph"

[dependencies]
serde = { version = "1", features = ["derive"] }
serde_json = "1"
discoveryprobe-core = { path = "../discoveryprobe-core" }

[[bin]]
name = "discoveryprobe-inventory"
path = "src/main.rs"
```

(Check the serde versions used by sibling crates -- e.g. `discoveryprobe-core/Cargo.toml` -- and match them exactly.)

**Step 3:** Create `src/lib.rs` with the module skeleton and a doc-comment stating purpose + failure mode (static-only scan can never conclude `Conform`; missing runtime input -> `NotObserved`, fail-safe):

```rust
//! Agent inventory: identifies AI agents from source (passport + code heuristics),
//! cross-checks declared vs observed behaviour, and maps multi-agent communication.
//!
//! Failure mode (fail-safe): when no runtime capture is provided, conformity is
//! `NotObserved` -- never `Conform` by default.
pub mod manifest;
pub mod scan;
pub mod graph;
pub mod correlate;
pub mod report;
```

Create empty `src/manifest.rs`, `src/scan.rs`, `src/graph.rs`, `src/correlate.rs`, `src/report.rs`, and a stub `src/main.rs` (`fn main() {}` for now).

**Step 4:** Run: `cargo build --manifest-path discoveryprobe/Cargo.toml -p discoveryprobe-inventory`
Expected: builds clean.

**Step 5:** Commit: `git commit -m "feat(inventory): scaffold discoveryprobe-inventory crate in the probe workspace"` (add only the new/modified files -- the shared tree carries other sessions' WIP, R21).

### Task 2: manifest.rs -- parse the repo passport (both shapes)

**Files:**
- Modify: `discoveryprobe/discoveryprobe-inventory/src/manifest.rs`
- Fixtures: use the REAL corpus files as test inputs via relative path (`../../corpus/repos/gh-pr-bot/repo/.inspect_ia_agents/manifest.json`) -- no invented payloads.

**Step 1: Write the failing tests** (in `#[cfg(test)] mod tests` at the bottom of `manifest.rs`):

```rust
#[test]
fn parses_the_gh_pr_bot_repo_passport() {
    let raw = std::fs::read_to_string(corpus_path("repos/gh-pr-bot/repo/.inspect_ia_agents/manifest.json")).expect("read");
    let m = Passport::parse(&raw).expect("valid passport");
    assert_eq!(m.principal(), "acme-dependency-pr-bot[bot]");
    assert_eq!(m.target_system(), "github");
    assert_eq!(m.actions(), vec!["open_pr".to_string(), "read_repo".to_string()]); // sorted
}

#[test]
fn invalid_json_yields_invalid_with_errors() {
    let err = Passport::parse("{not json").unwrap_err();
    assert!(!err.to_string().is_empty());
}

#[test]
fn structurally_wrong_manifest_reports_missing_fields() {
    // present file, wrong shape: no agent.identity.principal
    let err = Passport::parse(r#"{"schema_version":"1.0","agent":{"name":"x"}}"#).unwrap_err();
    assert!(err.to_string().contains("identity"));
}
```

Helper `fn corpus_path(rel: &str) -> PathBuf` resolves from `CARGO_MANIFEST_DIR` up to the repo `corpus/` dir.

**Step 2:** Run: `cargo test --manifest-path discoveryprobe/Cargo.toml -p discoveryprobe-inventory` -- expected FAIL (types missing).

**Step 3: Implement.** Serde types for the repo passport shape (top-level `schema_version` + `agent{...}`), with typed accessors. Validation = serde strictness + explicit checks for required fields (principal, target_system, at least one capability) returning a `PassportError` (`thiserror`-style enum or manual `Display`; no `.unwrap()` outside tests). Also support the unified corpus shape (`kind` at top level, `declared_identity`, `capability_scope` with git AND maf variants incl. `action: "handoff", target`) behind one entry point: `Passport::parse` tries repo shape, then unified shape, and reports both errors on failure. Keep `actions()` sorted (I4).

**Step 4:** Run tests -- PASS. Run `cargo clippy --manifest-path discoveryprobe/Cargo.toml -p discoveryprobe-inventory --all-targets -- -D warnings` and `cargo fmt`.

**Step 5:** Commit: `feat(inventory): parse agent passport (repo + unified shapes) with explicit validation errors`

### Task 3: scan.rs -- filesystem walk: passport present / absent / invalid + shadow-agent evidence

**Files:**
- Modify: `discoveryprobe/discoveryprobe-inventory/src/scan.rs`
- Create test fixture tree: `discoveryprobe/discoveryprobe-inventory/tests/fixtures/shadow-agent/agent/main.py` (agent code, NO `.inspect_ia_agents/`) and `tests/fixtures/invalid-passport/.inspect_ia_agents/manifest.json` (broken JSON). Small, committed, explicitly test-scoped (R4 ok).

**Step 1: Failing tests:**

```rust
#[test]
fn corpus_pr_bot_scans_as_passport_present() {
    let found = scan_tree(&corpus_path("repos/gh-pr-bot/repo")).expect("scan");
    assert_eq!(found.len(), 1);
    assert!(matches!(found[0].passport, PassportStatus::Present(_)));
}

#[test]
fn corpus_no_agent_scans_empty() {
    let found = scan_tree(&corpus_path("repos/gh-no-agent/repo")).expect("scan");
    assert!(found.is_empty()); // true negative: no agent claim without evidence (R13)
}

#[test]
fn agent_code_without_manifest_is_passport_absent_with_evidence() {
    let found = scan_tree(&fixture_path("shadow-agent")).expect("scan");
    assert_eq!(found.len(), 1);
    match &found[0].passport {
        PassportStatus::Absent { evidence } => assert!(!evidence.is_empty()),
        other => panic!("expected Absent, got {other:?}"),
    }
}

#[test]
fn broken_manifest_is_invalid_with_errors() {
    let found = scan_tree(&fixture_path("invalid-passport")).expect("scan");
    assert!(matches!(found[0].passport, PassportStatus::Invalid { .. }));
}
```

**Step 2:** Run -- FAIL.

**Step 3: Implement.** `PassportStatus { Present(Passport), Absent { evidence: Vec<String> }, Invalid { errors: Vec<String> } }` (serde-serialisable). `scan_tree(root)`:
1. `.inspect_ia_agents/manifest.json` exists -> parse -> `Present` or `Invalid` (with parse errors).
2. else agent-code heuristics, MIRRORING `ReferenceSourceScanAdapter` in `recette/adapters.py` (read it before coding): an `agent/` dir whose `.py` files contain `import github`/`from github import` (git agent), or temporalio `@activity.defn`, or provider env-var/SDK needles (reuse the needle idea from `discoveryprobe-detect/src/lib.rs` SIGNATURES). Each match becomes an `evidence` string (`"agent/main.py: import github"`). Evidence non-empty -> `Absent { evidence }`.
3. no evidence -> empty result (never report an agent without proof).
Walk in sorted order (I4). No panics; I/O errors propagate as `Result`.

**Step 4:** Tests PASS + clippy + fmt.

**Step 5:** Commit: `feat(inventory): scan tree for passports and shadow agents with explicit evidence`

### Task 4: graph.rs -- declared handoff graph

**Files:**
- Modify: `discoveryprobe/discoveryprobe-inventory/src/graph.rs`

**Step 0 (verify first, R13):** Read `corpus/maf_orchestration/correct/finance-approval-handoff-correct/team.json` to get the EXACT handoff field names (participants, start agent, per-source handoff sets). Do not invent field names; the test below loads that real file.

**Step 1: Failing tests:** load the real handoff `team.json`, assert `declared_edges` contains the expected `(from, to)` pairs (copy the pairs from the file you just read), sorted (I4). Also: a unified manifest with `capability_scope: [{action: "handoff", target: "agent-b"}]` yields edge `(self, agent-b)`.

**Step 2:** FAIL. **Step 3:** Implement `DeclaredGraph { edges: Vec<Edge> }`, `Edge { from: String, to: String }`, builders `from_team_json(&str)` and `from_passport(&Passport)`. **Step 4:** PASS + gates. **Step 5:** Commit: `feat(inventory): declared handoff graph from team.json and passport handoffs`

### Task 5: correlate.rs -- the pure correlator

**Files:**
- Modify: `discoveryprobe/discoveryprobe-inventory/src/correlate.rs`

The heart. PURE function, zero I/O, zero clock:

```rust
pub fn correlate(
    scanned: &[ScannedAgent],          // from scan.rs
    declared_graph: &DeclaredGraph,    // from graph.rs
    observed: Option<&ObservedInput>,  // CaptureRecording(s) + IpcEvents, parsed from input files
) -> AgentInventory
```

**Step 1: Failing tests** (all inputs are in-memory literals or committed fixtures -- deterministic):

```rust
#[test] fn static_only_scan_is_not_observed_never_conform() { /* observed=None -> every record Conformity::NotObserved */ }
#[test] fn shadow_agent_yields_passport_absent_violation() { /* Absent -> Violation::PassportAbsent listed */ }
#[test] fn observed_action_outside_scope_is_undeclared_action() { /* capture surface key implies action not in passport actions() */ }
#[test] fn observed_edge_outside_declared_graph_is_undeclared_handoff() {}
#[test] fn declared_edge_also_observed_is_not_a_violation() {}
#[test] fn output_is_sorted_by_agent_id() {}
```

**Step 2:** FAIL. **Step 3:** Implement the data model FROM THE DESIGN DOC section 2 (`AgentInventory`, `AgentRecord`, `Violation`, `CommGraph`, `Conformity { Conform, NotObserved, Violations(Vec<Violation>) }`), serde-serialisable, `BTreeMap`/sorted `Vec` everywhere. Observed-action extraction: map capture surface keys back to canonical actions only when the key encodes one (the CaptureRecording keys are strings like `"open_pr:acme/web#42"` -- split on `:`; a key with no canonical action prefix is egress evidence, not an action violation). Mirror the violation kinds of `recette/adapters.py::CapabilityViolation` for the git axes; add `PrincipalMismatch`, `UndeclaredHandoff`, `PassportAbsent`. If `correlate.rs` approaches the 800-LOC ceiling, split the model into `src/model.rs`.

**Step 4:** PASS + clippy + fmt. **Step 5:** Commit: `feat(inventory): pure correlator -- declared vs observed conformity and comm-graph violations`

### Task 6: report.rs + replay determinism test

**Step 1: Failing test:**

```rust
#[test]
fn inventory_json_is_byte_identical_across_two_runs_on_the_same_inputs() {
    let a = run_full(&corpus_path("repos/gh-pr-bot/repo"));
    let b = run_full(&corpus_path("repos/gh-pr-bot/repo"));
    assert_eq!(a, b); // byte-identical JSON (I4)
}
```

**Step 2-4:** Implement `report::to_json(&AgentInventory) -> String` (serde_json on already-sorted structures; assert stability). PASS + gates.

**Step 5:** Commit: `test(inventory): replay determinism -- byte-identical inventory JSON (I4)`

### Task 7: CLI (main.rs)

**Step 1:** Implement `src/main.rs`: `discoveryprobe-inventory scan <path> [--capture <file.json>] [--team <dir>] [--out <file>]`. Hand-rolled arg parsing (match the style of `discoveryprobe-catalog/src/main.rs` -- read it first; the workspace avoids clap unless it is already a dependency). Errors to stderr + non-zero exit; JSON to stdout or `--out`.

**Step 2:** Smoke by hand: `cargo run --manifest-path discoveryprobe/Cargo.toml -p discoveryprobe-inventory -- scan corpus/repos/gh-pr-bot/repo` -- expect one Present agent, `NotObserved`.

**Step 3:** Add an integration test in `tests/cli.rs` invoking the binary via `env!("CARGO_BIN_EXE_discoveryprobe-inventory")` asserting exit 0 + parseable JSON.

**Step 4:** Gates. Verify `bash cicd/checks.sh discovery-build` (or `./recette.sh discovery-build`) still builds the whole workspace including the new crate.

**Step 5:** Commit: `feat(inventory): CLI scan entrypoint producing AgentInventory JSON`

---

## Phase 2 -- eBPF extension: inter-agent comm events

### Task 8: New event structs in discoveryprobe-common

**Files:** Modify `discoveryprobe/discoveryprobe-common/src/lib.rs` (follow the existing struct pattern EXACTLY: repr(C), consts, `from_bytes`, `*_str()`, host tests).

**Step 1: Failing tests** (mirror the existing test style): size, round-trip, short-slice rejection for:

```rust
pub const UNIX_PATH_LEN: usize = 108; // sockaddr_un.sun_path

#[repr(C)] pub struct ListenEvent { pub pid: u32, pub port: [u8; 2], pub _pad: [u8; 2], pub comm: [u8; COMM_LEN] }
#[repr(C)] pub struct AcceptEvent { pub pid: u32, pub comm: [u8; COMM_LEN] }
#[repr(C)] pub struct UnixConnectEvent { pub pid: u32, pub comm: [u8; COMM_LEN], pub path: [u8; UNIX_PATH_LEN] }
```

**Step 2-4:** TDD as before. This crate is no_std-compatible -- zero deps, core only.

**Step 5:** Commit: `feat(probe-common): listen/accept/unix-connect event layouts for inter-agent comm`

### Task 9: Kernel side (discoveryprobe-ebpf) + loader drain

**Files:**
- Modify: `discoveryprobe/discoveryprobe-ebpf/src/main.rs` (new tracepoints + ring buffers, following the existing five: `sys_enter_listen` reading the socket's bound port needs `sys_enter_bind` capture keyed by pid -- read the existing `sys_enter_connect` handler first and copy its structure and verifier-safe patterns)
- Modify: `discoveryprobe/discoveryprobe/src/lib.rs` (loader: attach + drain new ring buffers into an `IpcEvents` JSON: lists of listen/accept/unix-connect + existing connect events, sorted, per capture window)

**Step 1:** Extend the eBPF program: `sys_enter_bind` (record pid->port for AF_INET, pid->path for AF_UNIX), `sys_enter_listen` (emit ListenEvent from the recorded bind), `sys_exit_accept4` (AcceptEvent), extend the connect handler to also emit `UnixConnectEvent` on AF_UNIX. Ring buffers 256 KiB like the others; drop-on-full; zero alloc.

**Step 2:** Build: `./recette.sh probe-ebpf-build` -- expected: compiles for bpfel-unknown-none. (The verifier is the real gate; if a probe read is rejected, bound it with a masked index like the DNS qname parse does.)

**Step 3:** Loader: drain + serialise `IpcEvents` (serde types in `discoveryprobe-core` or a new `ipc.rs` module there, with host unit tests on `from_bytes` fixtures -- the loader logic that formats events into strings is testable without a kernel).

**Step 4:** Host gates: `cargo test/clippy/fmt` on the workspace. Live verification of the kernel path needs CAP_BPF (`./recette.sh probe-grant-caps`); if unavailable in this session, mark the live-attach check explicitly as "livre, a verifier par toi" with the exact command -- do NOT claim live-verified (R14).

**Step 5:** Commit: `feat(probe-ebpf): capture listen/accept/AF_UNIX connect -- the inter-agent comm surface`

### Task 10: Correlator consumes IpcEvents -> observed edges

**Files:** Modify `correlate.rs` (+ `ObservedInput` gains `ipc: IpcEvents`, `forks: Vec<(u32,u32)>`, `pid_agents: BTreeMap<u32, String>`).

**Step 1: Failing tests** (synthetic in-memory events, no kernel):

```rust
#[test] fn localhost_connect_matching_a_listen_becomes_an_observed_edge() {
    // pid 10 (agent-a) connect 127.0.0.1:9000 ; pid 20 (agent-b) listen :9000 -> edge a->b tcp_localhost
}
#[test] fn unix_socket_path_match_becomes_an_observed_edge() {}
#[test] fn fork_tree_attributes_child_pid_activity_to_the_parent_agent() {}
#[test] fn edge_to_a_known_gateway_process_is_marked_via_gateway_not_inferred() {}
```

**Step 2-4:** Implement pairing (connect dport == listen port on loopback; unix path equality), fork-tree resolution (walk parent chain to a pid mapped to an agent), `via_gateway` flag when the destination comm matches a configured gateway list (input, not hardcoded -- R5: the list arrives in `ObservedInput`). Undeclared observed edge -> `Violation::UndeclaredHandoff`.

**Step 5:** Commit: `feat(inventory): correlate IPC events into observed comm edges with fork-tree attribution`

---

## Phase 3 -- corpus + Python harness

### Task 11: New corpus subjects (mono-axis, invariant ground-truth)

**Files:**
- Create: `corpus/repos/gh-shadow-agent/repo/agent/main.py` (REAL small agent code importing `github`, entrypoint; README) + `corpus/repos/gh-shadow-agent/discovery-ground-truth.json`
- Create: `corpus/repos/gh-invalid-passport/repo/.inspect_ia_agents/manifest.json` (schema-broken: e.g. missing `identity`) + agent code + ground-truth
- Create: `discoveryprobe/discoveryprobe-inventory/tests/fixtures/undeclared-handoff/{team.json, ipc_events.json}` (frozen deterministic capture: one observed edge outside the declared set) -- exercised by a Rust test asserting `UndeclaredHandoff`.

Ground-truth files follow the existing shape (`gh-pr-bot/discovery-ground-truth.json`) and ADD one optional invariant field:

```json
{ "agent_repo": "gh-shadow-agent", "target_system": "github", "detected": true,
  "agent_count": 1, "action_patterns": ["open_pr", "read_repo"], "risk_rank": 2,
  "policy_generated": true, "passport_status": "absent",
  "notes": "Agent code with NO .inspect_ia_agents manifest: the shadow agent. A scanner must still detect it AND surface the missing passport." }
```

`gh-invalid-passport` gets `"passport_status": "invalid"`; existing subjects are NOT edited (absent field = not asserted; adding `"present"` to them is a follow-up, not this wave).

**Steps:** write files -> run `python3 -m recette validate` (schema-validate; ground-truth schema may need the optional `passport_status` enum added in `corpus/schemas/` -- check `ground-truth.schema.json` vs the discovery ground-truth validator in `recette/` first, follow whichever validates discovery ground-truth today) -> commit: `feat(corpus): gh-shadow-agent + gh-invalid-passport discovery subjects (passport_status invariant)`

### Task 12: Python -- DiscoveryRisk.passport_status + reference adapter + harness assertion

**Files:**
- Modify: `recette/adapters.py`
- Modify: `recette/discovery_harness.py`
- Test: `tests/test_discovery_passport.py` (stdlib unittest)

**Step 1: Failing tests:**

```python
class PassportStatusTests(unittest.TestCase):
    def test_reference_adapter_reports_present_for_manifest_repo(self):
        risks = scan("corpus/repos/gh-pr-bot/repo")
        self.assertTrue(all(r.passport_status == "present" for r in risks))

    def test_reference_adapter_reports_absent_for_shadow_agent(self):
        risks = scan("corpus/repos/gh-shadow-agent/repo")
        self.assertTrue(risks)  # still detected
        self.assertTrue(all(r.passport_status == "absent" for r in risks))

    def test_harness_scores_passport_invariant(self):
        card = run_discovery_recette()
        self.assertTrue(card.all_pass())  # exact API: read discovery_scorecard.py first
```

**Step 2:** FAIL (no field).

**Step 3:** Implement: add `passport_status: str | None = None` to `DiscoveryRisk` (frozen dataclass -- new optional field keeps every existing constructor call valid). `ReferenceSourceScanAdapter._from_manifest` sets `"present"`; the invalid-manifest branch (manifest exists but `json.loads`/shape fails -- add a guarded try) sets `"invalid"` and still derives risks from code fallback; `_from_code`/`_from_temporal_code`/`_from_openapi` set `"absent"`. In `discovery_harness.run_discovery_recette`, when `gt` has `passport_status`, add `matches["passport"] = all(r.passport_status == gt["passport_status"] for r in risks)`.

**Step 4:** `./recette.sh test` green, `make recette` green (the reference oracle must pass its own corpus, including the two new subjects). If the coverage guard (`tests/test_coverage_guard.py`) tracks discovery subjects, extend it so an unwired passport subject turns red -- read the guard's constants first.

**Step 5:** Commit: `feat(recette): passport_status invariant through DiscoveryRisk, reference adapter and discovery harness`

### Task 13: Bridge contract test -- Rust JSON consumed by Python

**Files:**
- Create: `tests/fixtures/agent_inventory.fixture.json` -- generated by ACTUALLY RUNNING the Rust CLI on `corpus/repos/gh-shadow-agent/repo` (capture real output, R4/R16 spirit: no invented payload), committed.
- Create: `tests/test_inventory_bridge.py`
- Create: `recette/inventory_bridge.py` -- parse `AgentInventory` JSON -> `list[DiscoveryRisk]` (thin, stdlib only).

**Steps (TDD):** failing test asserts the fixture parses, maps `passport: {"absent": ...}` to `passport_status="absent"`, violations surface, and mapping is deterministic. Implement. `./recette.sh test` green. Commit: `feat(recette): inventory bridge -- AgentInventory JSON to DiscoveryRisk mapping with real fixture`

---

## Phase 4 -- console + docs + final gates

### Task 14: Console inventory panel (R16 full)

**Files:**
- Create: `console/src/pages/probe/InventoryPanel.tsx` (+ entry in `console/src/pages/probe/index.tsx`)
- Create: `console/src/pages/probe/__fixtures__/inventory-panel.fixture.json` -- REAL payload captured from the API (see step 1)
- Create: `console/src/pages/probe/InventoryPanel.test.tsx`

**Step 0 (read first):** `console/src/pages/probe/index.tsx` + one existing panel (`CorrelationPanel.tsx`) and its test + `recette/api/routers/probe.py` -- follow the exact existing pattern for: service call, envelope unwrap, fixture import, render-and-assert.

**Step 1:** API side: add an inventory endpoint to `recette/api/routers/probe.py` following the router's existing import/store/serve pattern (the probe router already serves capture JSON -- mirror it; do not invent a new storage mechanism). Unittest for the route (see how existing probe routes are tested in `tests/`).

**Step 2:** Capture the real response (curl the running API started via `./recette.sh platform up`, or the router unit-test client) into `__fixtures__/inventory-panel.fixture.json`.

**Step 3: Failing vitest:** render `InventoryPanel` with the fixture; assert: agent row visible, passport badge text for EVERY variant (`present`, `absent`, `invalid` -- fixture must contain all three, so scan a tree containing all three subjects), violations list, comm edges with undeclared edge flagged. No console errors.

**Step 4:** Implement the panel (badge + violations table + declared/observed/undeclared edges list; theme tokens, no hardcoded colors, no emoji). Service unwraps the response envelope explicitly.

**Step 5:** `./recette.sh console-build` + `./recette.sh console-test` green. Commit: `feat(console): probe inventory panel -- passport badge, violations, comm graph (R16)`

**Step 6:** Extend `scripts/smoke_console.py` with the panel flow (open probe page, assert badge DOM) -- run `./recette.sh smoke`. Commit.

### Task 15: Docs + help (P1 done = docs + help)

- Runbook: `docs/runbooks/inventory-recette.md` (CLI usage, capture input, corpus subjects, how the harness consumes it) -- follow `docs/runbooks/github-discovery-recette.md` structure.
- Docusaurus fr+en pages (find the docs tree via `./recette.sh docs-build` config) + console help-topic entry for the new panel (find the existing help-modal data source -- grep `help-modal` usage in `console/src/`).
- Commit: `docs(inventory): runbook + fr/en docs + console help topic`

### Task 16: Final gates (all must be green before "done")

```
cargo fmt --all --manifest-path discoveryprobe/Cargo.toml -- --check
cargo clippy --manifest-path discoveryprobe/Cargo.toml --all-targets -- -D warnings
cargo test --manifest-path discoveryprobe/Cargo.toml
./recette.sh probe-ebpf-build
make gates
./recette.sh test
make recette
./recette.sh console-build
./recette.sh console-test
./recette.sh smoke        # if console flow touched
```

Any red = the wave is not done. Live eBPF attach needs CAP_BPF: if not verifiable in-session, state exactly what was verified (build + host tests + synthetic-event correlation) and what remains ("livre, a verifier par toi": grant caps + run the broker capture against a lane_b run).

---

## Execution notes

- One commit per green task, small; push the branch often (R21). Work on a feature branch (or a dedicated worktree: `git worktree add ../recette_inventory -b feat/discoveryprobe-inventory`).
- Never edit files another session left dirty (screenshots, unrelated fixtures in `git status`).
- Read-first steps are BLOCKING: field names for team.json handoffs, probe router pattern, scorecard API -- verify in source before writing code that names them (R13).
- YAGNI guard: no IPv6, no payload capture, no gateway auto-detection beyond the configured list, no editing of existing corpus subjects in this wave.
